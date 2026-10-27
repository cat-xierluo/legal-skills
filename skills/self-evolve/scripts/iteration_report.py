#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迭代报告 v2:少而精 + 归因洞察(每周)。

从 self-evolve 已有确定性产出(timeline-index / topic-clusters /
session-summaries / proposals / skill-inventory)拼一份**用户口吻** digest。

报告 v2 重组(从堆事实 → 归因 + 用户相关洞察):
  §1 本周你专注什么(分类占比)
  §2 本周你反复纠错的地方(skill 边界 / 约束缺失 / 纠正短语归因)
  §3 本周反复调用的 skill(区分自动 cron vs 主动)
  §4 本周关键决策(top 5,带边界标签)
  §5 本周可沉淀的资产(proposals brief + 下一步)

双输出:
  - data_root 受控副本(review/inbox/iteration/):走 write_review_artifact 隐私门控
  - 桌面副本(默认 ~/Desktop/,可 --no-desktop 关):sanitize_structured_text 逐字段
    fail-closed 脱敏 + assert_external_write_path + 原子写
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from self_evolve_paths import (  # noqa: E402
    DATA_ROOT,
    RUNTIME_ROOT,
    REVIEW_INBOX_ROOT,
    assert_external_write_path,
)
from privacy_gate import sanitize_structured_text, write_review_artifact  # noqa: E402

DREAMING_DIR = RUNTIME_ROOT / "dreaming"
TIMELINE_INDEX_PATH = DREAMING_DIR / "timeline-index.json"
TOPIC_CLUSTERS_PATH = DREAMING_DIR / "topic-clusters.json"
SKILL_INVENTORY_PATH = RUNTIME_ROOT / "skill-inventory.json"
PROPOSALS_MACHINE_DIR = DATA_ROOT / "proposals" / "machine"
SESSION_SUMMARIES_DIR = RUNTIME_ROOT / "session-summaries"
ITERATION_INBOX_DIR = REVIEW_INBOX_ROOT / "iteration"

from workmode_config import DEFAULT_FOCUS_KEYWORDS, load_focus_config, match_focus  # noqa: E402

# Compatibility export; classification loads the local override at call time.
_FOCUS_KEYWORDS = DEFAULT_FOCUS_KEYWORDS

# 归因正则:只在 decisions + upgrade_signals 字段内匹配(避免上下文稀释)
# 注意:不用 \b(英文词边界),中文场景下「其实/边界」前后都是中文,\b 不匹配
_SKILL_BOUNDARY_RE = re.compile(r"(边界|端口|范围|明确|不该当|不要把|不采用|不应该|不该再|出屏)")
_HIDDEN_CONSTRAINT_RE = re.compile(r"(必须|不能是|限制是|要求是|唯一|不对的|不能直接|不能把|不能靠)")
_CORRECTION_PHRASE_RE = re.compile(r"(其实|应该是|我说的是|问题是|另外还有个问题|关键是|核心是|我应该先|应该先|我会先)")
_Q_FORM_RE = re.compile(r"(下次我|下次你|下次提|讲清楚|说得清楚|你看清楚|明确告诉|期望我|下次我应该)")

_PROPOSAL_TYPE_LABEL = {
    "skill_upgrade": "升级 skill",
    "article": "文章候选",
    "deep_dream_candidate": "深度分析候选",
}

_TOP_DECISIONS = 5
_TOP_REGION_SAMPLE = 5
_TOP_RECURRING_SKILLS = 10


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        Path(name).replace(path)
    finally:
        try:
            Path(name).unlink()
        except FileNotFoundError:
            pass


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        safe = [str(c).replace("\n", " ").replace("|", "\\|") for c in row]
        lines.append("| " + " | ".join(safe) + " |")
    return "\n".join(lines)


def _parse_since(since: str) -> float:
    if since == "all":
        return 0.0
    m = re.fullmatch(r"(\d{1,4})([dhw])", since)
    if not m:
        raise ValueError(f"bad --since: {since}(用 Nd/Nh/Nw 或 all)")
    n, unit = int(m.group(1)), m.group(2)
    return time.time() - n * {"d": 86400, "h": 3600, "w": 604800}[unit]


def _day_in_range(date_str: str, cutoff: float) -> bool:
    if not date_str or cutoff == 0:
        return cutoff == 0 and bool(date_str)
    try:
        return time.mktime(time.strptime(str(date_str)[:10], "%Y-%m-%d")) >= cutoff
    except Exception:
        return False


def _months_in_range(cutoff: float) -> list[str]:
    """涉及哪些 YYMM 月份目录(4 位,实际目录命名如 2608)。"""
    now = datetime.now(timezone.utc)
    months = [f"{now.year % 100}{now.month:02d}"]
    for delta in (1, 2):
        y, m = now.year, now.month - delta
        while m <= 0:
            m += 12
            y -= 1
        months.append(f"{y % 100}{m:02d}")
    return months


def _parse_session_ts(ts_raw) -> float:
    """SessionSummary.started_at 可能是 epoch(秒/毫秒)或字符串。"""
    if isinstance(ts_raw, (int, float)):
        ts = float(ts_raw)
        if ts > 1e12:  # 毫秒
            ts = ts / 1000.0
        return ts
    if isinstance(ts_raw, str) and ts_raw:
        try:
            return time.mktime(time.strptime(ts_raw[:19], "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            pass
    return 0.0


def gather(since: str) -> dict:
    cutoff = _parse_since(since)

    # §1 timeline-index 本周会话
    tl = _load_json(TIMELINE_INDEX_PATH, {})
    days = [d for d in (tl.get("days") or []) if _day_in_range(d.get("date", ""), cutoff)]
    week_sessions = sum(int(d.get("count", 0)) for d in days)
    week_classes: dict[str, int] = {}
    for d in days:
        for k, v in (d.get("classes") or {}).items():
            week_classes[k] = week_classes.get(k, 0) + int(v)

    # topic-clusters(备用,§1 不直接用,会在 _extract_focus 里重新按周过滤)
    tc = _load_json(TOPIC_CLUSTERS_PATH, [])
    clusters = tc if isinstance(tc, list) else (tc.get("clusters") or [])

    # §1-§5 主体:周内 substantive sessions
    sessions: list[dict] = []
    for yyyymm in _months_in_range(cutoff):
        d = SESSION_SUMMARIES_DIR / yyyymm
        if not d.is_dir():
            continue
        for f in d.glob("*.json"):
            s = _load_json(f, None)
            if not isinstance(s, dict):
                continue
            if s.get("summary_policy") not in ("summarize_candidate", "cluster_candidate"):
                continue
            ts = _parse_session_ts(s.get("started_at"))
            if ts and ts < cutoff:
                continue
            sessions.append(s)

    # §5 proposals 本周
    proposals = []
    if PROPOSALS_MACHINE_DIR.is_dir():
        for f in PROPOSALS_MACHINE_DIR.glob("*.json"):
            p = _load_json(f, None)
            if not isinstance(p, dict):
                continue
            ts_raw = p.get("created_at") or p.get("updated_at") or 0
            try:
                if float(ts_raw) >= cutoff:
                    proposals.append(p)
            except (TypeError, ValueError):
                proposals.append(p)

    # §3 inventory
    inv = _load_json(SKILL_INVENTORY_PATH, {})
    skills = {s["id"]: s for s in (inv.get("skills") or []) if isinstance(s, dict) and s.get("id")}

    return {
        "week_sessions": week_sessions,
        "week_classes": week_classes,
        "clusters": clusters,
        "sessions": sessions,
        "proposals": proposals,
        "skills": skills,
    }


def _focus_text(s: dict) -> str:
    """从 session 抽取用于专注度归类的文本(topic_title + decisions + evidence text)。"""
    parts = []
    if s.get("topic_title"):
        parts.append(str(s["topic_title"]))
    for d in s.get("decisions") or []:
        parts.append(str(d))
    for ev in s.get("evidence_snippets") or []:
        parts.append(str(ev))
    for ev in s.get("upgrade_signals") or []:
        parts.append(str(ev))
    for ev in s.get("article_signals") or []:
        parts.append(str(ev))
    return " ".join(parts)


def _extract_focus_distribution(sessions: list[dict]) -> dict:
    """§1 专注度归类:多标签关键词匹配、统计与示例。"""
    categories = load_focus_config()
    focus_counts: Counter[str] = Counter()
    matched = 0
    samples: dict[str, list[str]] = {}
    for s in sessions:
        text = _focus_text(s)
        if not text.strip():
            continue
        hits = match_focus(text, categories)
        if not hits:
            continue
        matched += 1
        for h in hits:
            focus_counts[h] += 1
            if len(samples.get(h, [])) < _TOP_RECURRING_SKILLS:
                topic = s.get("topic_title") or "(无主题)"
                samples.setdefault(h, []).append(topic[:60])
    focus_counts["未匹配"] = max(0, len(sessions) - matched)
    return {"counts": dict(focus_counts), "samples": samples, "matched_sessions": matched, "total": len(sessions)}


def _session_field_blob(s: dict) -> str:
    """把 session 里所有可能含归因语言的字段拼起来(仅用于归因正则)。"""
    return " ".join([
        str(s.get("topic_title") or ""),
        " ".join(str(d) for d in s.get("decisions") or []),
        " ".join(str(d) for d in s.get("upgrade_signals") or []),
        " ".join(str(d) for d in s.get("article_signals") or []),
        " ".join(str(q) for q in s.get("open_questions") or []),
        " ".join(str(ev) for ev in s.get("evidence_snippets") or []),
    ])


def _extract_attribution_signals(sessions: list[dict]) -> dict:
    """§2 三类归因 + 纠正短语:在 decisions + upgrade_signals 字段内正则,去重,sid 索引。"""
    # 用 sid(决策内可能含 sid 引用) 与 session_id 关联相对宽松;这里直接按 session 维度
    skill_boundary: list[tuple[str, str]] = []  # (cid, 原文)
    hidden_constraint: list[tuple[str, str]] = []
    q_form: list[tuple[str, str]] = []
    correction_phrases: list[tuple[str, str]] = []

    for s in sessions:
        sid = s.get("session_id") or "(无 sid)"
        # 只在 decisions + upgrade_signals 字段内匹配归因(避免上下文稀释)
        attr_blob = " ".join(
            str(d) for d in (s.get("decisions") or []) + (s.get("upgrade_signals") or [])
        )
        if attr_blob:
            for m in _SKILL_BOUNDARY_RE.finditer(attr_blob):
                ctx = _snippet(attr_blob, m.start(), m.end(), 30)
                skill_boundary.append((f"[{sid[:12]}]", ctx))
            for m in _HIDDEN_CONSTRAINT_RE.finditer(attr_blob):
                ctx = _snippet(attr_blob, m.start(), m.end(), 30)
                hidden_constraint.append((f"[{sid[:12]}]", ctx))
        # 纠正短语:用整 blob(可能出现在 topic_title 或 open_questions)
        full_blob = _session_field_blob(s)
        for m in _CORRECTION_PHRASE_RE.finditer(full_blob):
            ctx = _snippet(full_blob, m.start(), m.end(), 40)
            correction_phrases.append((f"[{sid[:12]}]", ctx))
        for m in _Q_FORM_RE.finditer(full_blob):
            ctx = _snippet(full_blob, m.start(), m.end(), 40)
            q_form.append((f"[{sid[:12]}]", ctx))

    return {
        "skill_boundary": skill_boundary,
        "hidden_constraint": hidden_constraint,
        "q_form": q_form,
        "correction_phrases": correction_phrases,
    }


def _snippet(text: str, start: int, end: int, padding: int) -> str:
    s = max(0, start - padding)
    e = min(len(text), end + padding)
    snip = text[s:e].replace("\n", " ").strip()
    if s > 0:
        snip = "…" + snip
    if e < len(text):
        snip = snip + "…"
    return snip


def _extract_skill_blob(s: dict) -> str:
    """session topic + decisions + evidence 文本,用于跟 skill 字典项做子串匹配(更严)."""
    parts = [str(s.get("topic_title") or "")]
    for d in s.get("decisions") or []:
        parts.append(str(d))
    for ev in s.get("evidence_snippets") or []:
        parts.append(str(ev))
    return " ".join(parts)


def _extract_recurring_skills(sessions: list[dict], skills: dict) -> list[dict]:
    """§3 反复调用的 skill:related_skills 触发 vs blob 主动提及。

    - related 高 + blob 低 → 大概率自动 cron 调度(用户没主动)
    - 两者都高 → 主动调用
    """
    counts: dict[str, dict[str, int]] = {}
    for s in sessions:
        blob = _extract_skill_blob(s)
        sid = s.get("session_id") or "(?)"
        for skill_id in s.get("related_skills") or []:
            if skill_id not in counts:
                counts[skill_id] = {"related": 0, "blob": 0}
            counts[skill_id]["related"] += 1
            # 在 blob 中是否也被用户主动提及(子串匹配,严)
            if skill_id in blob or (skills.get(skill_id, {}).get("title") or "") in blob:
                counts[skill_id]["blob"] += 1
    out = []
    for sid, c in counts.items():
        related, blob = c["related"], c["blob"]
        if related < 2:
            continue
        # 主动调用:blob 提及占比 >= 20%(用户原话里反复主动提及);否则视为自动 cron 调度
        ratio = blob / related if related else 0
        kind = "主动" if ratio >= 0.20 else "自动"
        out.append({
            "skill": sid,
            "title": (skills.get(sid, {}).get("title") or sid),
            "related": related,
            "blob": blob,
            "kind": kind,
        })
    out.sort(key=lambda x: (-x["related"], -x["blob"]))
    return out[:_TOP_RECURRING_SKILLS]


def _extract_top_decisions(sessions: list[dict], attribution: dict) -> list[str]:
    """§4 关键决策(top 5):优先从归因 sample 收集『含边界/约束关键词』的决策,再去重。"""
    keyword_re = re.compile(r"(边界|端口|范围|必须|不能|限制|明确|不该|不要|约束|其实|应该|问题是)")
    seen: set[str] = set()
    out: list[str] = []
    # 优先 sessions 中含 boundary/constraint 关键词的 decision
    for s in sessions:
        for d in s.get("decisions") or []:
            key = str(d).strip()[:60]
            if key in seen:
                continue
            if len(str(d)) < 8:
                continue
            if keyword_re.search(str(d)):
                seen.add(key)
                out.append(str(d).strip()[:200])
                if len(out) >= _TOP_DECISIONS:
                    return out
    # 补足:取高信号决策(evidence_snippets 长度 × 关键词)
    for s in sessions:
        for d in s.get("decisions") or []:
            key = str(d).strip()[:60]
            if key in seen:
                continue
            if len(str(d)) < 12:
                continue
            if keyword_re.search(str(d)):
                continue
            seen.add(key)
            out.append(str(d).strip()[:200])
            if len(out) >= _TOP_DECISIONS:
                return out
    return out


def _signal_attribution(attr: dict) -> dict:
    """归因信号编排:dedupe by snippet 短前缀,按 cid 排行取 top。"""
    out = {}
    for key in ("skill_boundary", "hidden_constraint", "correction_phrases", "q_form"):
        items = attr.get(key, [])
        seen = set()
        uniq = []
        for cid, snip in items:
            short = snip[:30]
            if short in seen:
                continue
            seen.add(short)
            uniq.append((cid, snip))
        out[key] = uniq[:_TOP_REGION_SAMPLE]
    return out


def _focus_summary(samples: dict, name: str) -> str:
    """1 句话倾向总结(从样本凑)。"""
    s = samples.get(name, [])
    if not s:
        return ""
    sample = s[0]
    return f"-> 主要工作是「{sample}」"


def render(data: dict, since: str, now: str) -> str:
    focus = _extract_focus_distribution(data["sessions"])
    attr = _extract_attribution_signals(data["sessions"])
    recurring = _extract_recurring_skills(data["sessions"], data["skills"])
    top_decisions = _extract_top_decisions(data["sessions"], attr)
    attr_view = _signal_attribution(attr)

    total = focus["total"]
    counts = focus["counts"]
    samples = focus["samples"]

    lines = [
        f"# Self Evolve 周报 · {now[:10]}",
        "",
        f"> 近 {since} 你的对话沉淀——专注方向、纠错模式、反复调用。事实摘要按需展开,本周重点看归因。",
        "",
    ]

    # §1 本周你专注什么(占比)
    lines.append("## 1. 本周你专注什么")
    if total:
        rows = []
        for name, n in sorted(counts.items(), key=lambda x: -x[1]):
            pct = round(n / total * 100)
            rows.append([name, f"{n}", f"{pct}%", _focus_summary(samples, name)])
        lines.append(markdown_table(["方向", "会话数", "占比", "1 句倾向"], rows))
        cover = round((total - counts.get("未匹配", 0)) / total * 100)
        lines.append(f"")
        lines.append(f"覆盖率 {cover}%——多标签会话按击中数加权(一个会话可同时归到多方向)。")
    else:
        lines.append("本周暂无会话数据。")
    lines.append("")

    # §2 本周你反复纠错的地方(归因 + 纠正短语)
    lines.append("## 2. 本周你反复纠错的地方(归因)")
    sig_summary = []
    for key, label in [
        ("skill_boundary", "skill 边界问题(反复纠正 skill 的边界/范围)"),
        ("hidden_constraint", "约束缺失(你没明说但模型必须知道的)"),
        ("correction_phrases", "纠正短语(其实/应该是/不是 X 是 Y)"),
        ("q_form", "问法问题(下次提需求要换句式)"),
    ]:
        items = attr_view[key]
        if items:
            sig_summary.append(f"- **{label}**: {len(items)}+ 条")
    if sig_summary:
        lines.extend(sig_summary)
    else:
        lines.append("- 本周没检测到强归因信号。")
    lines.append("")

    # 详细归因 sample(只在有信号时展开)
    for key, label in [
        ("skill_boundary", "skill 边界(反复纠正 skill 该不该/范围/边界)"),
        ("hidden_constraint", "约束缺失(你没说但模型要知道的)"),
        ("correction_phrases", "纠正短语(其实/应该是/不是 X 是 Y)"),
    ]:
        items = attr_view[key]
        if not items:
            continue
        lines.append(f"**{label}**— sample:")
        for cid, snip in items[:_TOP_REGION_SAMPLE]:
            lines.append(f"- {cid} {snip}")
        lines.append("")

    # 问法问题(信号稀薄,留 1 行 nudge)
    q_items = attr_view["q_form"]
    if q_items:
        lines.append("**问法问题(下次提需求要换句式)**:")
        for cid, snip in q_items[:3]:
            lines.append(f"- {cid} {snip}")
    else:
        lines.append("> 问法问题信号极稀薄(本周没明确写『下次该怎么问』)。要从『其实/问题是』这类隐晦句推断,或有意识地在遇到要重问时补一句『下次我该先说 X』。")
    lines.append("")

    # §3 本周反复调用的 skill
    lines.append("## 3. 本周反复调用的 skill(反思边界是否过宽/不足)")
    if recurring:
        rows = []
        for r in recurring:
            tag = "🤖 自动" if r["kind"] == "自动" else "👆 主动"
            rows.append([r["skill"], r["title"], f"{r['related']}", f"{r['blob']}", tag])
        lines.append(markdown_table(["skill", "名称", "相关×", "blob 提及", "性质"], rows))
        lines.append("")
        lines.append("相关× = dream_sweep 自动标注;blob 提及 = 用户原话里的主动提及。")
        lines.append("**两者差距大 = 自动 cron 调度多(不是你主动要的),反思边界是否过宽。**")
    else:
        lines.append("本周没检测到 skill 反复触发。")
    lines.append("")

    # §4 本周关键决策(top 5,带边界标签)
    lines.append("## 4. 本周关键决策(只 5 条,带边界标签)")
    if top_decisions:
        for i, d in enumerate(top_decisions, 1):
            tags = []
            if _SKILL_BOUNDARY_RE.search(d):
                tags.append("边界")
            if _HIDDEN_CONSTRAINT_RE.search(d):
                tags.append("约束")
            if _CORRECTION_PHRASE_RE.search(d):
                tags.append("纠正")
            tag_str = f"  `[{'/'.join(tags)}]`" if tags else ""
            lines.append(f"{i}. {d}{tag_str}")
    else:
        lines.append("本周没关键决策。")
    lines.append("")

    # §5 本周可沉淀的资产(proposals brief)
    lines.append("## 5. 本周可沉淀的资产")
    if data["proposals"]:
        for p in data["proposals"]:
            ptype = _PROPOSAL_TYPE_LABEL.get(p.get("proposal_type"), p.get("proposal_type", "-"))
            target = p.get("target_skill", "-")
            disp = p.get("machine_disposition", "-")
            summary = (p.get("summary") or "").strip()
            lines.append(f"### {target} — {ptype} [{disp}]")
            if summary:
                lines.append(f">{summary}")
            cps = p.get("change_points") or []
            if cps:
                lines.append("")
                lines.append("**改动点**:")
                for cp in cps:
                    lines.append(f"- {cp}")
            lines.append("")
    else:
        lines.append("本周没有新的资产 / 升级提案。")
    lines.append("")

    # 下一步(合并原 §8)
    lines.append("### 下一步")
    lines.append("- 哪个方向占比异常高(80%+)→ 反思是否需要分散赛道 / 减负")
    lines.append("- 哪类 skill 反复触发且 blob 提及 0 → 反思 skill 边界是否过宽")
    lines.append("- 哪类约束缺失反复出现 → 写成 skill 边界条件固化(避免下周再纠错)")
    lines.append("- 哪条 proposal 已起 → 进 review inbox 决定")
    lines.append("")
    lines.append("---")
    lines.append(f"_由 self-evolve iteration_report v2 生成于 {now}_")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成面向用户的迭代报告 v2(归因 + 专注度)")
    ap.add_argument("--since", default="7d", help="时间窗:Nd/Nh/Nw 或 all(默认 7d)")
    ap.add_argument("--output", default=None, help="桌面副本路径(默认 ~/Desktop/self-evolve-周报-YYYY-MM-DD.md)")
    ap.add_argument("--no-desktop", action="store_true", help="不写桌面副本(只写 review inbox)")
    ap.add_argument("--json", action="store_true", help="输出结构化结果")
    args = ap.parse_args()

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    stamp = time.strftime("%y%m%d%H%M%S")
    now_date = time.strftime("%Y-%m-%d")

    data = gather(args.since)
    digest = render(data, args.since, now)

    # ① review inbox 受控副本(必写,走隐私门控)
    ITERATION_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    inbox_dest = ITERATION_INBOX_DIR / f"{stamp}_weekly-iteration.md"
    inbox_result = write_review_artifact(inbox_dest, digest, artifact_id=f"iteration-{stamp}")

    # ② 桌面副本(默认写,fail-closed 脱敏 + 路径校验 + 原子写)
    desktop = {"path": None, "status": "skipped"}
    if not args.no_desktop:
        try:
            sanitized = sanitize_structured_text(digest)
            out = Path(args.output).expanduser() if args.output else Path.home() / "Desktop" / f"self-evolve-周报-{now_date}.md"
            resolved = assert_external_write_path(out, label="desktop_report")
            _atomic_write(resolved, sanitized)
            desktop = {"path": str(resolved), "status": "written"}
        except ValueError as exc:
            desktop = {"path": None, "status": f"blocked:{exc}"}

    if args.json:
        print(json.dumps(
            {"since": args.since, "sessions_total": len(data["sessions"]), "inbox": inbox_result, "desktop": desktop},
            ensure_ascii=False, indent=2,
        ))
    else:
        print(f"迭代报告 v2 已生成(近 {args.since},共 {len(data['sessions'])} 个 substantive 会话):")
        print(f"  review inbox: {inbox_result.get('destination')} [{inbox_result.get('status')}]")
        print(f"  桌面: {desktop['path'] or desktop['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
