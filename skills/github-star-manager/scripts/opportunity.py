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
import os
import json
import argparse
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from star_tracker import StarTracker  # noqa: E402
from lockutil import write_lock  # noqa: E402

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
CARD_SCHEMA = "opportunity-card/1.1"
DECISION_SCOPES = {"direction", "repo", "component"}

# 状态短词白名单（R5/J2：明确列举，避免 "somedir" 这类目录名被误豁免）
_STATUS_WORDS = {"ok", "pass", "passed", "fail", "failed", "done", "true", "false",
                 "yes", "no", "n/a", "na", "none", "null"}


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


def _resolve_evidence_path(val: str, base_dir: Path) -> Path:
    """证据路径解析（上游 J2）：相对路径以**卡文件所在目录**为基准（不是 cwd），
    ~ 展开，符号链接解析到实际目标。"""
    p = Path(os.path.expanduser(val))
    if not p.is_absolute():
        p = base_dir / p
    try:
        return p.resolve(strict=False)   # 解析符号链接与相对段
    except OSError:
        return p


def _verify_evidence_paths(block: Dict, label: str,
                           errors: List[str], warnings: List[str],
                           base_dir: Optional[Path] = None) -> None:
    """R5/J2 证据块实质校验（上游复审要求重做）：

    - 类型：只接受字符串/字符串列表；bool/数字/None 拒绝（此前 `run_evidence: true`
      直接跳过）；嵌套数组逐项递归
    - 路径：必须是**存在的普通文件**且非空；目录拒绝；符号链接解析到实际目标校验
    - 基准：相对路径以卡文件目录（base_dir）为基准，不是 cwd（避免漂移误判）
    - URL：仅候选线索，不构成 tested/adopted 证据（warning，不阻断）
    - 豁免：状态短词（ok/pass/done）与含中文散文说明不算路径主张
    """
    checked = 0

    def _walk(v, path_key: str, in_list: bool = False):
        nonlocal checked
        if isinstance(v, bool) or isinstance(v, (int, float)) or v is None:
            errors.append(f"{path_key} 类型不支持（{type(v).__name__}）——"
                          f"证据必须是路径字符串或字符串列表")
            return
        if isinstance(v, list):
            if not v:
                warnings.append(f"{path_key} 为空列表")
            for i, item in enumerate(v):
                _walk(item, f"{path_key}[{i}]", in_list=True)
            return
        if isinstance(v, dict):
            if not v:
                warnings.append(f"{path_key} 为空对象")
            for k2, v2 in v.items():
                _walk(v2, f"{path_key}.{k2}")
            return
        if not isinstance(v, str):
            errors.append(f"{path_key} 类型不支持（{type(v).__name__}）")
            return
        val = v.strip()
        if not val:
            return
        if val.startswith(("http://", "https://")):
            warnings.append(f"{path_key}=URL 无法离线核验，仅作候选线索，"
                            f"不构成 tested/adopted 证据")
            return
        if re.search(r"[\u4e00-\u9fff]", val) and not in_list:
            return  # 中文散文说明（仅限顶层标量字段；列表元素是路径主张，不豁免——R9/J2）
        if in_list and re.search(r"[\u4e00-\u9fff]", val) and ("/" in val or "\\" in val or Path(val).suffix):
            # 列表中的中文路径：按路径校验（上游反例：合法文件旁夹带不存在的中文路径）
            pass  # 落入下方路径校验
        elif re.search(r"[\u4e00-\u9fff]", val) and in_list:
            return  # 列表中的中文散文仍豁免（不是路径形态）
        # 状态短词白名单（明确列举，不用通配——否则 "somedir" 这类目录名会被误豁免）
        if val.lower() in _STATUS_WORDS:
            return
        p = _resolve_evidence_path(val, base_dir or Path.cwd())
        checked += 1
        if not p.exists():
            errors.append(f"{path_key} 指向不存在的路径: {val}——"
                          f"虚构运行产物/回执不能作为 tested/adopted 证据")
        elif p.is_dir():
            errors.append(f"{path_key} 指向目录而非文件: {val}——目录不构成可核实产物")
        elif p.is_file() and p.stat().st_size == 0:
            errors.append(f"{path_key} 指向空文件: {val}——空产物不构成可核实证据")
        elif p.is_file():
            _verify_evidence_content(p, path_key, errors)
            # R9/J2 最小结构绑定：tested/adopted 的产物文件须含可识别的运行结论行
            # （上游反例：普通会议议程被当运行证据——议程不含 exit_code/verdict 等结构）
            _verify_run_conclusion(p, path_key, errors)

    for k, v in block.items():
        _walk(v, f"{label}.{k}")

    if checked == 0:
        # 上游 J2：URL/状态词/散文都不构成完成证据——整块无可核验文件时必须拒，
        # 不能仅 warning 后继续签 tested/adopted
        errors.append(f"{label} 未含任何可核验的本地文件——"
                      f"URL/状态词/散文不足以支撑 tested/adopted，"
                      f"请补真实产物路径或降级为 experiment_proposed")


# R9/J2 运行结论结构模式（要求 tested/adopted 的证据文件含至少一行结构化结论）
_RUN_CONCLUSION_RE = re.compile(
    r"exit[_\s]?code\s*[=:]\s*\d+"          # exit_code=0 / exit code: 1
    r"|exit[_\s]?status\s*[=:]"               # exit_status=
    r"|verdict\s*[=:]\s*\w+"                  # verdict=pass
    r"|tests?\s+\d+\s+(?:passed|failed)"      # tests 5 passed
    r"|RESULT\s*[=:]"                         # RESULT=PASS
    r"|STATUS\s*[=:]\s*(?:PASS|FAIL|OK|SUCCESS|FAILED)"  # STATUS=PASS
    r"|\b(?:passed|failed)\s*[:：]?\s*\d+"    # passed: 5
, re.I)

# R9/J2 失败指标（出现即拒——上游反例：exit_code=1/verdict=failed 的回执）
_FAILURE_RE = re.compile(
    r"exit[_\s]?code\s*[=:]\s*[^0\s]"         # exit_code=非零
    r"|verdict\s*[=:]\s*(?:fail\w*|error\w*)"  # verdict=failed/error
    r"|exit[_\s]?status\s*[=:]\s*(?:fail\w*|error\w*)"
    r"|\bFAILED\s*$"                           # 行尾 FAILED（避免误中 FAILED 案例——限定行尾）
    r"|STATUS\s*[=:]\s*FAIL"
, re.I | re.M)


def _verify_run_conclusion(path: Path, path_key: str, errors: List[str]) -> None:
    """R9/J2：tested/adopted 的产物文件须含可识别的运行结论行（最小结构）。"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    if not _RUN_CONCLUSION_RE.search(text):
        errors.append(f"{path_key} 文件无运行结论结构（缺 exit_code/verdict/tests/RESULT/"
                      f"STATUS 等模式）——会议议程或散文不构成运行产物证据")
    elif _FAILURE_RE.search(text):
        errors.append(f"{path_key} 文件含失败指标（exit_code 非零/verdict=failed）——"
                      f"失败回执不能签 tested/adopted，请降级或修复后重试")


def _verify_code_evidence(evidence: Dict, errors: List[str],
                          warnings: List[str], base_dir: Optional[Path] = None) -> None:
    """R5/J2：源码证据须可回查且**绑定**——带文件/行号/锚点/摘录/commit 哈希，
    且形如 `path:line` 时该文件须真实存在（上游反例：`missing/source.py:999
    fabricated quote` 的路径不存在却通过）。"""
    ce = evidence.get("code_evidence")
    if ce in (None, "", {}, []):
        return
    if isinstance(ce, str):
        m = re.match(r"^([^\s:]+)[:#](\d+)", ce.strip())
        if m:
            src = _resolve_evidence_path(m.group(1), base_dir or Path.cwd())
            if not src.exists():
                errors.append(f"evidence.code_evidence 引用的源码不存在: {m.group(1)}"
                              f"——虚构源码摘录不能作为代码证据")
            elif src.is_dir():
                errors.append(f"evidence.code_evidence 引用的是目录: {m.group(1)}")
            elif src.is_file():
                # R9/J2 行界核验：path:line 的行号不得超文件实际行数
                try:
                    n_lines = sum(1 for _ in src.open(encoding="utf-8", errors="replace"))
                    line_no = int(m.group(2))
                    if line_no > n_lines:
                        errors.append(
                            f"evidence.code_evidence 行号越界: {m.group(1)}:{line_no}"
                            f"（文件仅 {n_lines} 行）——虚构摘录不能作为代码证据")
                except OSError:
                    pass
            return
        if not re.search(r"@[0-9a-f]{7,}|\b[0-9a-f]{7,40}\b", ce):
            errors.append("evidence.code_evidence 无可回查锚点"
                          "（须 path:line / commit 哈希 / 结构化锚点对象）——"
                          "一句「某处有实现」不构成代码证据")
        return
    if isinstance(ce, dict):
        anchor = None
        for k in ("path", "file"):
            if ce.get(k):
                anchor = ce[k]
                break
        if anchor:
            src = _resolve_evidence_path(str(anchor), base_dir or Path.cwd())
            if not src.exists():
                errors.append(f"evidence.code_evidence.{k} 引用的源码不存在: {anchor}")
        elif not any(ce.get(k) for k in ("commit", "sha", "hash", "excerpt", "anchor")):
            errors.append("evidence.code_evidence 缺锚点字段"
                          "（path/file/line/commit/sha/excerpt/hash 至少其一）")
        return
    errors.append("evidence.code_evidence 类型不支持（须字符串或对象）")


# 证据内容须非纯占位/无关文本（上游反例：'unrelated nonempty text' 通过）
_PLACEHOLDER_RE = re.compile(
    r"^(unrelated|placeholder|todo|tbd|fake|dummy|test|sample|example|"
    r"lorem ipsum)\b", re.I)


def _verify_evidence_content(path: Path, path_key: str, errors: List[str]) -> None:
    """R5/J2 内容绑定（最小可行）：证据文件内容不能是明显占位/无关文本。"""
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:200].strip()
    except OSError:
        return
    if not head:
        return  # 空文件已由上层拒收
    if _PLACEHOLDER_RE.match(head):
        errors.append(f"{path_key} 内容疑似占位/无关文本（{head[:40]!r}）——"
                      f"任意非空文件不构成产物证据，须为真实运行输出")


def validate_card(card: Dict, base_dir: Optional[Path] = None) -> Tuple[bool, List[str], List[str]]:
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
        repo_id = signal.get("repo_id")
        if repo_id is not None and (isinstance(repo_id, bool) or not isinstance(repo_id, int) or repo_id <= 0):
            errors.append("signal.repo_id 必须是正整数")

    # 3. target：必须有 project_id 与目标能力
    target = card["target"]
    if not isinstance(target, dict):
        errors.append("target 必须是对象")
    else:
        if not target.get("project_id"):
            errors.append("target.project_id 缺失")
        if not target.get("capability"):
            errors.append("target.capability 缺失（目标能力/需求描述）")
        capability_key = target.get("capability_key")
        if capability_key is not None and (
                not isinstance(capability_key, str)
                or not re.fullmatch(r"[a-z0-9\u4e00-\u9fff][a-z0-9\u4e00-\u9fff-]{0,63}",
                                    capability_key)):
            errors.append("target.capability_key 必须是稳定 slug（小写字母/数字/中文/连字符，≤64字符）")

    # 4. evidence：必须区分证据类型 + R5/J2 源码证据可回查
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
        _verify_code_evidence(evidence, errors, warnings, base_dir)

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
                continue
            # R5/J2：证据字段做实质校验（类型/目录/嵌套/符号链接/相对路径基准）。
            # 非 dict/str 的一切类型（bool/数字/None/数组）也交给校验器拒收，
            # 不能因形态不匹配而跳过检查。
            if req in ("run_evidence", "adoption_evidence"):
                _verify_evidence_paths({req: decision[req]}, f"decision",
                                       errors, warnings, base_dir)

    scope = card.get("scope") or (card.get("target") or {}).get("scope")
    capability_key = (card.get("target") or {}).get("capability_key")
    if scope is None and capability_key:
        scope = "direction"
        card["scope"] = scope
    if scope is not None and scope not in DECISION_SCOPES:
        errors.append(f"scope 必须是 {sorted(DECISION_SCOPES)} 之一")
    if scope == "direction" and not (card.get("target") or {}).get("capability_key"):
        errors.append("scope=direction 缺少 target.capability_key")

    return len(errors) == 0, errors, warnings


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def save_card(card: Dict) -> Path:
    """持久化机会卡到 output/feedback/（显式本地写）

    文件名含毫秒级时间戳；同候选同毫秒重复反馈时追加序号，不覆盖既有记录。
    """
    d = feedback_dir()
    d.mkdir(parents=True, exist_ok=True)
    project_id = card["target"]["project_id"]
    repo_id = card["signal"].get("repo_id")
    repo_slug = str(repo_id) if isinstance(repo_id, int) else str(card["signal"]["repo"]).replace("/", "__")
    target = card.get("target") or {}
    scope = card.get("scope") or target.get("scope") or "legacy"
    direction = ""
    if scope == "direction":
        direction = "__" + str(target.get("capability_key") or "unaligned")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
    stem = f"{project_id}__{repo_slug}__{scope}{direction}__{ts}"
    path = d / f"{stem}.json"
    card["_recorded_at"] = datetime.now(timezone.utc).isoformat()
    card["_schema"] = CARD_SCHEMA
    with write_lock(d):
        seq = 0
        candidate = path
        while candidate.exists():  # 防同毫秒碰撞覆盖
            seq += 1
            candidate = d / f"{stem}_{seq}.json"
        atomic_json(candidate, card)
        path = candidate
    return path


def existing_decisions(project_id: str, repo: str) -> List[Dict]:
    """某项目对某 repo 的既有反馈（按卡片内容匹配，文件名仅兼容旧布局）"""
    out = []
    if feedback_dir().exists():
        for p in sorted(feedback_dir().glob("*.json")):
            try:
                card = json.loads(p.read_text(encoding="utf-8"))
                target = card.get("target") or {}
                signal = card.get("signal") or {}
                if (target.get("project_id") != project_id
                        or signal.get("repo") != repo):
                    continue
                out.append(card)
            except Exception:
                continue
    return out


def decision_scope(card: Dict) -> str:
    return card.get("scope") or (card.get("target") or {}).get("scope") or "legacy"


def decision_capability(card: Dict):
    target = card.get("target") or {}
    return target.get("capability_key") or target.get("decision_capability_key")


# ==================== 子命令 ====================

def cmd_validate(args) -> int:
    card = load_card(args.input)
    if card is None:
        return 1
    ok, errors, warnings = validate_card(card, base_dir=Path(args.input).resolve().parent)
    result = {"valid": ok, "errors": errors, "warnings": warnings,
              "decision_status": (card.get("decision") or {}).get("status")}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def cmd_record(args) -> int:
    card = load_card(args.input)
    if card is None:
        return 1

    ok, errors, warnings = validate_card(card, base_dir=Path(args.input).resolve().parent)
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
    prior = [p for p in prior if getattr(args, "repo_id", None) is None
             or (p.get("signal") or {}).get("repo_id") in (None, args.repo_id)]
    requested_direction = getattr(args, "direction", None)
    if requested_direction:
        prior = [p for p in prior if decision_scope(p) in {"direction", "legacy"}
                 and decision_capability(p) in (None, requested_direction)]
    rejected = [p for p in prior if (p.get("decision") or {}).get("status") == "rejected"]
    result = {
        "repo": args.repo,
        "project": args.project,
        "total_records": len(prior),
        "rejected_count": len(rejected),
        # 抑制语义：有拒绝记录 → 默认跳过推荐；携带新 repo revision/需求版本时可重新评估
        "suppressed": len(rejected) > 0,
        "scope": "direction" if requested_direction else "legacy/repository",
        "direction": requested_direction,
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
    p.add_argument("--repo-id", type=int)
    p.add_argument("--direction", help="stable capability_key")
    p.set_defaults(func=cmd_suppress)

    for command in sub.choices.values():
        command.add_argument("--data-dir", type=Path, help="私有运行目录（与自动发现使用同一个目录）")
    args = parser.parse_args()
    if args.data_dir:
        StarTracker.CACHE_DIR = args.data_dir.expanduser().resolve()
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except Exception as e:
        print(f"❌ 操作失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
