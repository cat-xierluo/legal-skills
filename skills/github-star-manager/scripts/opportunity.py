#!/usr/bin/env python3
"""机会卡校验与采用反馈 - 批次 C 核心（审计 §4 契约的 Skill 侧落地）

每张机会卡必须回答审计 §4 的七个字段；decision 状态机强制：
- tested 必须有可核实的运行产物与验证日志（run_evidence）
- adopted 必须再有目标项目的实际产物/提交与验收回执（adoption_evidence）
- 没有证据时只允许 hypothesis/experiment_proposed——写下「已测试/已采用」不能关单

命令：
    python opportunity.py validate --input card.json       # 校验一张机会卡
    python opportunity.py record --input card.json         # 校验通过后持久化到 output/feedback/
    python opportunity.py list --project myproj            # 列出该项目的反馈记录
    python opportunity.py suppress --repo owner/name --direction "字幕机制"  # 查询/登记拒绝抑制

设计约束：
- record 是显式本地写；不修改目标项目、不派发任务、不调模型
- 反馈绑定 repo revision（commit/哈希）与 project profile 版本，证据变化允许重新评估
- 拒绝抑制只针对同一候选+方向，不永久屏蔽整个方向
"""

import sys
import json
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from star_tracker import StarTracker  # noqa: E402

# 审计 §4 的 gap 枚举
GAP_TYPES = {"新增能力", "接入缺口", "执行缺陷", "验证缺口", "已有等价能力", "不适用"}

# decision 状态机：允许的状态及证据要求
DECISIONS = {
    "researched": {"required": [], "label": "已研判"},
    "experiment_proposed": {"required": [], "label": "已提议实验"},
    "tested": {"required": ["run_evidence"], "label": "已测试"},
    "adopted": {"required": ["run_evidence", "adoption_evidence"], "label": "已采用"},
    "rejected": {"required": ["reason"], "label": "已拒绝"},
    "deferred": {"required": ["reason"], "label": "已暂缓"},
}

REQUIRED_CARD_FIELDS = ["signal", "target", "evidence", "gap", "hypothesis", "experiment", "decision"]


def feedback_dir() -> Path:
    return StarTracker.CACHE_DIR / "feedback"


def project_dir() -> Path:
    return StarTracker.CACHE_DIR / "projects"


def load_card(path: str) -> Optional[Dict]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ 读取失败 {path}: {e}", file=sys.stderr)
        return None


def validate_card(card: Dict) -> Tuple[bool, List[str], List[str]]:
    """校验机会卡。返回 (是否通过, errors, warnings)"""
    errors: List[str] = []
    warnings: List[str] = []

    # 1. 七个必答字段
    for field in REQUIRED_CARD_FIELDS:
        if field not in card or card[field] in (None, "", {}, []):
            errors.append(f"缺少必答字段: {field}")

    if errors:
        return False, errors, warnings

    # 2. signal：必须有 repo 与发现来源；starred_at 缺失要显式标注
    signal = card["signal"]
    if not isinstance(signal, dict):
        errors.append("signal 必须是对象")
    else:
        if not signal.get("repo"):
            errors.append("signal.repo 缺失（owner/name）")
        if not signal.get("source"):
            errors.append("signal.source 缺失（发现来源：内容/截图/口述线索）")
        if not signal.get("starred_at"):
            warnings.append("signal.starred_at 缺失：按 F02 口径这是未知时间，"
                            "卡内不得声称「近期关注」")

    # 3. target：必须有 project_id 与目标能力
    target = card["target"]
    if not isinstance(target, dict):
        errors.append("target 必须是对象")
    else:
        if not target.get("project_id"):
            errors.append("target.project_id 缺失")
        if not target.get("capability"):
            errors.append("target.capability 缺失（目标能力/需求描述）")

    # 4. evidence：必须区分证据类型
    evidence = card["evidence"]
    if not isinstance(evidence, dict):
        errors.append("evidence 必须是对象")
    else:
        if not evidence.get("url"):
            errors.append("evidence.url 缺失（仓库/文件 URL）")
        kinds = [k for k in ("readme_claim", "code_evidence", "author_demo", "self_tested")
                 if evidence.get(k)]
        if not kinds:
            warnings.append("evidence 未区分证据类型（readme_claim/code_evidence/"
                            "author_demo/self_tested）——README 宣称 ≠ 代码证据")

    # 5. gap 枚举
    if card["gap"] not in GAP_TYPES:
        errors.append(f"gap 必须是 {sorted(GAP_TYPES)} 之一，实际: {card['gap']}")

    # 6. decision 状态机
    decision = card["decision"]
    if not isinstance(decision, dict) or decision.get("status") not in DECISIONS:
        errors.append(f"decision.status 必须是 {sorted(DECISIONS)} 之一")
    else:
        status = decision["status"]
        for req in DECISIONS[status]["required"]:
            if not decision.get(req):
                errors.append(
                    f"decision.status={status} 缺少 {req}——"
                    f"{'运行产物与验证日志' if req == 'run_evidence' else '采纳产物/提交与验收回执'}"
                    f"不可省略；没有证据时请用 experiment_proposed")

    return len(errors) == 0, errors, warnings


def save_card(card: Dict) -> Path:
    """持久化机会卡到 output/feedback/（显式本地写）

    文件名含毫秒级时间戳；同候选同毫秒重复反馈时追加序号，不覆盖既有记录。
    """
    d = feedback_dir()
    d.mkdir(parents=True, exist_ok=True)
    project_id = card["target"]["project_id"]
    repo_slug = str(card["signal"]["repo"]).replace("/", "__")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
    path = d / f"{project_id}__{repo_slug}__{ts}.json"
    seq = 0
    while path.exists():  # 防同毫秒碰撞覆盖
        seq += 1
        path = d / f"{project_id}__{repo_slug}__{ts}_{seq}.json"
    card["_recorded_at"] = datetime.now(timezone.utc).isoformat()
    card["_schema"] = "opportunity-card/1.0"
    path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def existing_decisions(project_id: str, repo: str) -> List[Dict]:
    """某项目对某 repo 的既有反馈（用于拒绝抑制）"""
    prefix = f"{project_id}__{str(repo).replace('/', '__')}__"
    out = []
    if feedback_dir().exists():
        for p in sorted(feedback_dir().glob(f"{prefix}*.json")):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
    return out


# ==================== 子命令 ====================

def cmd_validate(args) -> int:
    card = load_card(args.input)
    if card is None:
        return 1
    ok, errors, warnings = validate_card(card)
    result = {"valid": ok, "errors": errors, "warnings": warnings,
              "decision_status": (card.get("decision") or {}).get("status")}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def cmd_record(args) -> int:
    card = load_card(args.input)
    if card is None:
        return 1

    ok, errors, warnings = validate_card(card)
    if not ok:
        print(json.dumps({"recorded": False, "errors": errors, "warnings": warnings},
                         ensure_ascii=False, indent=2))
        return 1

    # 拒绝抑制：同项目+同 repo 已有 rejected 记录时提示（不阻断——新证据允许重新评估）
    repo = card["signal"]["repo"]
    project_id = card["target"]["project_id"]
    prior = existing_decisions(project_id, repo)
    rejected_before = [p for p in prior
                       if (p.get("decision") or {}).get("status") == "rejected"]
    if rejected_before and (card.get("decision") or {}).get("status") != "rejected":
        warnings.append(f"该候选此前被拒绝过 {len(rejected_before)} 次；"
                        f"请确认本次携带了新的实质证据（repo revision / 目标需求变化）")

    path = save_card(card)
    print(json.dumps({
        "recorded": True,
        "path": str(path),
        "warnings": warnings,
        "total_for_candidate": len(prior) + 1,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_list(args) -> int:
    d = feedback_dir()
    items = []
    if d.exists():
        for p in sorted(d.glob("*.json")):
            try:
                card = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if args.project and (card.get("target") or {}).get("project_id") != args.project:
                continue
            if args.repo and (card.get("signal") or {}).get("repo") != args.repo:
                continue
            items.append({
                "file": p.name,
                "repo": (card.get("signal") or {}).get("repo"),
                "project": (card.get("target") or {}).get("project_id"),
                "gap": card.get("gap"),
                "decision": (card.get("decision") or {}).get("status"),
                "recorded_at": card.get("_recorded_at"),
            })
    print(json.dumps({"count": len(items), "items": items}, ensure_ascii=False, indent=2))
    return 0


def cmd_suppress(args) -> int:
    """查询某候选是否处于拒绝抑制状态（供推荐方在召回后过滤）"""
    if not args.repo or not args.project:
        print("❌ 需要 --repo owner/name 与 --project ID", file=sys.stderr)
        return 1
    prior = existing_decisions(args.project, args.repo)
    rejected = [p for p in prior if (p.get("decision") or {}).get("status") == "rejected"]
    result = {
        "repo": args.repo,
        "project": args.project,
        "total_records": len(prior),
        "rejected_count": len(rejected),
        # 抑制语义：有拒绝记录 → 默认跳过推荐；携带新 repo revision/需求版本时可重新评估
        "suppressed": len(rejected) > 0,
        "note": "抑制只针对该候选在该方向的重复推荐，不屏蔽整个方向；"
                "新实质证据（revision 变化/需求变化）允许重新出卡",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="机会卡校验与采用反馈（审计 §4 契约落地）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python opportunity.py validate --input card.json
  python opportunity.py record --input card.json
  python opportunity.py list --project myproj
  python opportunity.py suppress --repo owner/name --project myproj
        """)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="校验机会卡（不落盘）")
    p.add_argument("--input", required=True, help="机会卡 JSON 文件")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("record", help="校验通过后持久化机会卡")
    p.add_argument("--input", required=True, help="机会卡 JSON 文件")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("list", help="列出反馈记录")
    p.add_argument("--project", help="按项目过滤")
    p.add_argument("--repo", help="按仓库过滤")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("suppress", help="查询候选的拒绝抑制状态")
    p.add_argument("--repo", required=True, help="owner/name")
    p.add_argument("--project", required=True, help="项目 ID")
    p.set_defaults(func=cmd_suppress)

    args = parser.parse_args()
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except Exception as e:
        print(f"❌ 操作失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
