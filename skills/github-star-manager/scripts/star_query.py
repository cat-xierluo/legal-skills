#!/usr/bin/env python3
"""Star Manager 只读查询接口 - 批次 B（审计 §3 接口草案的 Skill 侧落地）

为「对话中的 Agent」提供事实与候选：无需面板、无需模型 Key，
当前 Agent 用已有推理能力消费 JSON envelope 自行判断。

设计约束（审计 §3）：
- 只读本地库，不联网；查询只查询，不做隐式写
- stdout 只写 JSON，日志走 stderr；失败返回非零
- 部分数据必须显式标 partial，不能伪装完整
- 缓存内容新鲜度与数据本身分开表达（fetched_at/completeness）
- 无主题分析时明确返回缺少分析，不暗中调模型

命令：
    python star_query.py recent --since 2026-09-15 --until 2026-10-15
    python star_query.py interests --window 30 --compare previous
    python star_query.py match --project myproj --query "字幕 时间轴"
    python star_query.py evidence --repo owner/name
    python star_query.py research --project myproj --limit 5
"""

import sys
import json
import contextlib
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from star_tracker import StarTracker  # noqa: E402
from common import load_value_config  # noqa: E402


# ==================== JSON envelope ====================

def envelope(items: List[Dict], snapshot: Optional[Dict] = None,
             coverage: Optional[Dict] = None,
             warnings: Optional[List[str]] = None,
             errors: Optional[List[str]] = None,
             extra: Optional[Dict] = None) -> Dict:
    """统一 JSON envelope（审计 §3 建议格式）"""
    meta = (snapshot or {}).get("snapshot_meta") or {}
    data = {
        "schema_version": "1.0",
        "account_id": meta.get("account_id"),
        "snapshot_id": (snapshot or {}).get("timestamp"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial" if (meta.get("complete") is not True or errors) else "ok",
        "snapshot_completeness": meta.get("completeness", "unknown"),
        "coverage": coverage or {},
        "items": items,
        "warnings": warnings or [],
        "errors": errors or [],
    }
    if extra:
        data.update(extra)
    return data


def emit(data: Dict, exit_code: int = 0) -> int:
    """stdout 只写 JSON；日志类信息一律走 stderr"""
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return exit_code


def warn(msg: str) -> None:
    print(msg, file=sys.stderr)


def load_snapshot_or_fail() -> tuple[Optional[Dict], int]:
    """加载本地快照；缺失/不可读时返回带 errors 的空 envelope"""
    tracker = StarTracker.__new__(StarTracker)
    tracker.CACHE_DIR = StarTracker.CACHE_DIR
    snap = StarTracker.load_latest(tracker)
    if not snap:
        return None, 1
    return snap, 0


def parse_dt(s: Optional[str]) -> Optional[datetime]:
    """解析 ISO 时间串；失败返回 None（消费方应把该项归未知）"""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


# ==================== recent：任意时间窗的新关注 ====================

def cmd_recent(args) -> int:
    """近期关注：按 starred_at 的真实时间窗过滤；未知时间单独列出，不冒充"""
    snap, fail = load_snapshot_or_fail()
    if not snap:
        return emit(envelope([], errors=["无本地快照，请先运行 --init"]), 1)

    now = datetime.now(timezone.utc)
    since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc) if args.since else now - timedelta(days=30)
    until = datetime.fromisoformat(args.until).replace(tzinfo=timezone.utc) if args.until else now

    matched, unknown_time = [], []
    repos = snap.get("repos", [])
    for repo in repos:
        starred = parse_dt(repo.get("starred_at"))
        if starred is None:
            unknown_time.append(_brief(repo))
        elif since <= starred <= until:
            matched.append({**_brief(repo), "starred_at": repo.get("starred_at")})

    matched.sort(key=lambda r: r.get("starred_at") or "", reverse=True)

    return emit(envelope(
        items=matched,
        snapshot=snap,
        coverage={
            "window_since": since.isoformat(),
            "window_until": until.isoformat(),
            "total_repos": len(repos),
            "matched": len(matched),
            "unknown_starred_at": len(unknown_time),
        },
        warnings=(["快照抓取不完整，recent 结果可能遗漏"] if snap.get("snapshot_meta", {}).get("complete") is not True else []),
        extra={"unknown_time_items": unknown_time},
    ))


def _brief(repo: Dict) -> Dict:
    """仓库摘要字段（供 Agent 消费的最小事实集）"""
    return {
        "repo": repo.get("full_name"),
        "description": repo.get("description"),
        "language": repo.get("language"),
        "topics": repo.get("topics", []),
        "stars": repo.get("stargazers_count", 0),
        "updated_at": repo.get("updated_at"),
    }


# ==================== interests：可比时间窗的主题计数 ====================

def cmd_interests(args) -> int:
    """主题兴趣分布：从已有分类/关键词复算，不调模型。

    compare=previous 时给出相邻前一窗口计数，供 Agent 判断趋势；
    无分类数据时明确返回 needs_analysis，不暗中生成。
    """
    snap, fail = load_snapshot_or_fail()
    if not snap:
        return emit(envelope([], errors=["无本地快照，请先运行 --init"]), 1)

    now = datetime.now(timezone.utc)
    days = args.window
    cur_start = now - timedelta(days=days)
    prev_start = cur_start - timedelta(days=days)

    tracker = StarTracker.__new__(StarTracker)
    tracker.CACHE_DIR = StarTracker.CACHE_DIR
    tracker.CONFIG_DIR = StarTracker.CONFIG_DIR
    tracker.CATEGORIES_FILE = StarTracker.CONFIG_DIR / "categories.yaml"
    tracker.TAGS_FILE = StarTracker.CONFIG_DIR / "tags.json"
    tracker.SETTINGS_FILE = StarTracker.CONFIG_DIR / "user_settings.json"
    tracker.github_token = None
    tracker._client = None
    tracker._use_ai = False
    tracker.last_fetch_meta = None
    tracker.settings = {}
    # 区分「用户生成过分类」与「只有内置默认」——后者不能冒充已分析的主题数据
    if not tracker.CATEGORIES_FILE.exists():
        return emit(envelope([], snapshot=snap,
                             warnings=["未找到分类配置（output/categories.yaml）"],
                             errors=["needs_analysis: 请先运行 generate_categories.py 生成分类"]), 1)
    # _load_categories 的警告必须走 stderr：stdout 只写 JSON（envelope 合同）
    with contextlib.redirect_stdout(sys.stderr):
        categories = StarTracker._load_categories(tracker)
    if not categories:
        return emit(envelope([], snapshot=snap,
                             errors=["needs_analysis: 分类配置为空，请运行 generate_categories.py"]), 1)

    def bucket_count(start: datetime, end: datetime) -> tuple[Dict[str, int], int, int]:
        counts: Dict[str, int] = {}
        unknown = 0
        total = 0
        for repo in snap.get("repos", []):
            starred = parse_dt(repo.get("starred_at"))
            if starred is None or not (start <= starred <= end):
                if starred is None:
                    unknown += 1
                continue
            total += 1
            cat = repo.get("category")
            cat_id = cat.get("id") if isinstance(cat, dict) else cat
            if not cat_id:
                # 快照里无 category 时按关键词匹配一次（只读）
                cat = StarTracker._match_category(tracker, repo, {c["id"]: c for c in categories})
                cat_id = cat.get("id") if cat else "uncategorized"
            counts[cat_id] = counts.get(cat_id, 0) + 1
        return counts, total, unknown

    cur_counts, cur_total, cur_unknown = bucket_count(cur_start, now)
    prev_counts, prev_total, prev_unknown = bucket_count(prev_start, cur_start)

    themes = []
    all_ids = sorted(set(cur_counts) | set(prev_counts),
                     key=lambda k: -(cur_counts.get(k, 0)))
    for cat_id in all_ids:
        cur, prev = cur_counts.get(cat_id, 0), prev_counts.get(cat_id, 0)
        themes.append({
            "theme": cat_id,
            "current": cur,
            "previous": prev,
            "delta": cur - prev,
            "share": round(cur / cur_total, 3) if cur_total else 0.0,
        })

    return emit(envelope(
        items=themes,
        snapshot=snap,
        coverage={
            "window_days": days,
            "current_window": {"start": cur_start.isoformat(), "count": cur_total,
                               "unknown_starred_at": cur_unknown},
            "previous_window": {"start": prev_start.isoformat(), "count": prev_total,
                                "unknown_starred_at": prev_unknown},
        },
        warnings=(["快照抓取不完整，主题计数可能偏低"] if snap.get("snapshot_meta", {}).get("complete") is not True else []),
    ))


# ==================== match：项目需求 ↔ 收藏召回 ====================

def cmd_match(args) -> int:
    """按项目需求关键词召回候选收藏（无模型，纯字段匹配）。

    分数只是召回依据，不是适用性证明（审计 §1 F08 的边界）。
    项目需求登记在 output/projects/<project_id>.json。
    """
    snap, fail = load_snapshot_or_fail()
    if not snap:
        return emit(envelope([], errors=["无本地快照，请先运行 --init"]), 1)

    query_terms = [t.strip().lower() for t in args.query.split() if t.strip()]
    if not query_terms:
        return emit(envelope([], errors=["query 为空"]), 1)

    project_profile = _load_project_profile(args.project)
    warnings = []
    if args.project and project_profile is None:
        warnings.append(f"项目 {args.project} 未登记（output/projects/{args.project}.json），"
                        f"只做了通用召回，未对齐项目需求")

    scored = []
    for repo in snap.get("repos", []):
        haystack = " ".join(filter(None, [
            (repo.get("description") or "").lower(),
            " ".join(repo.get("topics", [])).lower(),
            (repo.get("language") or "").lower(),
            (repo.get("full_name") or "").lower(),
        ]))
        hits = [t for t in query_terms if t in haystack]
        if not hits:
            continue
        entry = _brief(repo)
        entry.update({
            "matched_terms": hits,
            "score": len(hits),
            "starred_at": repo.get("starred_at"),
            "html_url": repo.get("html_url"),
        })
        scored.append(entry)

    scored.sort(key=lambda x: (-x["score"], -(x.get("stars") or 0)))
    limit = args.limit or 20
    truncated = len(scored) > limit
    scored = scored[:limit]

    return emit(envelope(
        items=scored,
        snapshot=snap,
        coverage={
            "query_terms": query_terms,
            "project": args.project,
            "project_profile_found": project_profile is not None,
            "total_repos": len(snap.get("repos", [])),
            "matched": len(scored),
            "truncated": truncated,
        },
        warnings=warnings,
    ))


def _load_project_profile(project_id: Optional[str]) -> Optional[Dict]:
    if not project_id:
        return None
    path = StarTracker.CACHE_DIR / "projects" / f"{project_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        warn(f"项目配置读取失败 {path}: {e}")
        return None


# ==================== evidence：单仓库缓存证据 ====================

def cmd_evidence(args) -> int:
    """导出单仓库的缓存证据包（只读，缺缓存显式标记 stale/missing）。

    证据来源限本地缓存：快照元数据 + evidence/ 目录下此前抓取的 README/Release。
    不自动联网取证——联网走 main.py --export 等显式命令。
    """
    snap, fail = load_snapshot_or_fail()
    if not snap:
        return emit(envelope([], errors=["无本地快照，请先运行 --init"]), 1)

    repo_full = args.repo
    repo_entry = next((r for r in snap.get("repos", []) if r.get("full_name") == repo_full), None)

    evidence_dir = StarTracker.CACHE_DIR / "evidence" / repo_full.replace("/", "__")
    cached_files = []
    if evidence_dir.exists():
        cached_files = sorted(p.name for p in evidence_dir.iterdir() if p.is_file())

    has_snapshot_entry = repo_entry is not None
    warnings = []
    if not has_snapshot_entry:
        warnings.append(f"仓库 {repo_full} 不在本地快照中（可能未 star 或快照过旧）")
    if not cached_files:
        warnings.append(f"无缓存证据（{evidence_dir}），需要 README/Release 原文时请先显式取证")

    item = {
        "repo": repo_full,
        "in_snapshot": has_snapshot_entry,
        "snapshot_entry": _brief(repo_entry) if has_snapshot_entry else None,
        "starred_at": repo_entry.get("starred_at") if has_snapshot_entry else None,
        "cached_evidence_files": cached_files,
        "evidence_dir": str(evidence_dir),
        "cache_status": "present" if cached_files else "missing",
    }
    return emit(envelope(
        items=[item],
        snapshot=snap,
        warnings=warnings,
    ))


# ==================== research：供 Agent 分析的最小候选+证据包 ====================

def cmd_research(args) -> int:
    """research prepare：为当前 Agent 组装最小分析包（候选 + 目标需求 + 使用说明）。

    只读。产出是「供判断的材料」，不是结论——适用性判断由当前 Agent 做。
    """
    snap, fail = load_snapshot_or_fail()
    if not snap:
        return emit(envelope([], errors=["无本地快照，请先运行 --init"]), 1)

    profile = _load_project_profile(args.project)
    if profile is None:
        return emit(envelope([], snapshot=snap,
                             errors=[f"项目 {args.project} 未登记：请先在 output/projects/{args.project}.json "
                                     f"登记目标需求（capabilities/needs/constraints）"]), 1)

    # 用项目需求做召回（复用 match 逻辑）
    needs = profile.get("needs", [])
    query = " ".join(needs) if needs else " ".join(profile.get("capabilities", []))
    if not query:
        return emit(envelope([], snapshot=snap,
                             errors=["项目配置缺 needs/capabilities，无法召回"]), 1)

    class MatchArgs:
        pass

    margs = MatchArgs()
    margs.query = query
    margs.project = args.project
    margs.limit = args.limit

    # 直接调用 match 的内部逻辑（不重复 emit）
    from io import StringIO
    import contextlib
    buf = StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cmd_match(margs)
    match_result = json.loads(buf.getvalue())

    pkg = {
        "project": profile,
        "candidates": match_result.get("items", []),
        "coverage": match_result.get("coverage", {}),
        "usage_note": (
            "本包只是召回结果（分数=关键词命中数），不是适用性证明。"
            "请逐个核对仓库 README/代码与项目需求的真实差距，产出机会卡（见 opportunity.py validate）。"
            "允许结论是「已有等价能力，无需吸收」。"
        ),
        "opportunity_card_schema": {
            "signal": "repo id、真实 starred_at、发现来源",
            "target": "project_id、目标能力、当前任务或约束引用",
            "evidence": "仓库 URL、commit OID/响应哈希、获取时间；区分 README 宣称/代码证据/亲自实测",
            "gap": "新增能力 | 接入缺口 | 执行缺陷 | 验证缺口 | 已有等价能力 | 不适用",
            "hypothesis": "可借鉴机制、适用条件、代价与不确定性",
            "experiment": "单一消费者、有限输入、预算、预期产物、反例与验收",
            "decision": "researched | experiment_proposed | tested | adopted | rejected | deferred",
        },
    }
    return emit(envelope(
        items=[pkg],
        snapshot=snap,
        warnings=match_result.get("warnings", []),
    ))


# ==================== CLI ====================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Star Manager 只读查询接口（stdout 只输出 JSON，日志走 stderr）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python star_query.py recent --since 2026-09-15 --until 2026-10-15
  python star_query.py interests --window 30 --compare previous
  python star_query.py match --project myproj --query "字幕 时间轴"
  python star_query.py evidence --repo owner/name
  python star_query.py research --project myproj --limit 5
        """)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("recent", help="按 starred_at 时间窗列新关注")
    p.add_argument("--since", help="开始日期 YYYY-MM-DD（默认 30 天前）")
    p.add_argument("--until", help="结束日期 YYYY-MM-DD（默认今天）")
    p.set_defaults(func=cmd_recent)

    p = sub.add_parser("interests", help="主题窗口计数（可比窗口对比）")
    p.add_argument("--window", type=int, default=30, help="窗口天数（默认 30）")
    p.add_argument("--compare", choices=["previous"], default="previous",
                   help="对比相邻前一窗口")
    p.set_defaults(func=cmd_interests)

    p = sub.add_parser("match", help="按需求关键词召回候选收藏")
    p.add_argument("--project", help="项目 ID（登记在 output/projects/<id>.json，可选）")
    p.add_argument("--query", required=True, help="空格分隔的需求关键词")
    p.add_argument("--limit", type=int, default=20, help="返回上限（默认 20）")
    p.set_defaults(func=cmd_match)

    p = sub.add_parser("evidence", help="单仓库缓存证据包")
    p.add_argument("--repo", required=True, help="owner/name")
    p.set_defaults(func=cmd_evidence)

    p = sub.add_parser("research", help="组装供 Agent 分析的最小候选+证据包")
    p.add_argument("--project", required=True, help="项目 ID（必须已登记）")
    p.add_argument("--limit", type=int, default=5, help="候选上限（默认 5）")
    p.set_defaults(func=cmd_research)

    args = parser.parse_args()
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except Exception as e:
        warn(f"查询失败: {type(e).__name__}: {e}")
        return emit(envelope([], errors=[f"{type(e).__name__}: {e}"]), 1)


if __name__ == "__main__":
    sys.exit(main())
