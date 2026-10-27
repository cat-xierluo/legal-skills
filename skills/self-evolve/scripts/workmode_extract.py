#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从会话摘要提炼工作模式偏好证据包(不调模型)。

把 iteration_report 已有的归因信号(focus / correction / sediment / recurrence)从
「一次性报告字符串」升级为「可入库的脱敏证据包」:按 (scope, sub_topic) 聚类,每个
cluster 必须跨 ≥2 个 session 且有 ≥2 条跨会话 evidence——这保证偏好是「反复出现」的
而非一次性,和 info-evaluator preference_ledger 的跨会话门槛一致。

不重构 iteration_report 的三个 _extract_*(保护 1.5.1 报告);只 import 归因常量。
session hash 用 sha256[:16](和 deep_dream.build_packet 一致),解决归因函数原本用
截断 UUID 与 evidence 包 sha256[:16] 词汇不匹配的问题。

产出 schema = self-evolve-preference-evidence-v1(复用 export_preference_evidence 契约),
字段对齐,供 workmode_ledger.analyze 消费,为将来与 info-evaluator 账本统一投影铺路。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from self_evolve_paths import RUNTIME_ROOT  # noqa: E402
from iteration_report import (  # noqa: E402
    gather,
    _focus_text,
    _SKILL_BOUNDARY_RE,
    _HIDDEN_CONSTRAINT_RE,
    _CORRECTION_PHRASE_RE,
    _Q_FORM_RE,
)
from workmode_config import load_focus_config, match_focus  # noqa: E402
from workmode_ledger import (  # noqa: E402
    EVIDENCE_SCHEMA,
    MAX_EVIDENCE_CHARS,
    _text_safe,
    canonical_json,
    digest,
    now_iso,
    validate_evidence_packet,
)

DEFAULT_PACKET = Path(
    os.environ.get(
        "SELF_EVOLVE_WORKMODE_PACKET", RUNTIME_ROOT / "preference-bridge" / "workmode-packet.json"
    )
)

_SCOPE_TITLE = {
    "focus": "专注方向",
    "correction": "纠错模式",
    "sediment": "沉淀信号",
    "recurrence": "反复 skill",
}
_CORRECTION_SUB = {
    "skill_boundary": "skill 边界",
    "hidden_constraint": "约束缺失",
    "correction_phrase": "纠正短语",
    "q_form": "问法",
}


def _session_hash(session_id: str) -> str:
    return hashlib.sha256(str(session_id).encode("utf-8", errors="replace")).hexdigest()[:16]


def _snippet(text: str, start: int, end: int, padding: int) -> str:
    s = max(0, start - padding)
    e = min(len(text), end + padding)
    snip = text[s:e].replace("\n", " ").strip()
    if s > 0:
        snip = "…" + snip
    if e < len(text):
        snip = snip + "…"
    return snip


def _attr_blob(s: dict) -> str:
    """decisions + upgrade_signals(skill 边界 / 约束缺失 正则用)。"""
    return " ".join(str(d) for d in (s.get("decisions") or []) + (s.get("upgrade_signals") or []))


def _full_blob(s: dict) -> str:
    """全字段 blob(纠正短语 / 问法 正则用,可能出现在 topic_title 或 open_questions)。"""
    return " ".join([
        str(s.get("topic_title") or ""),
        " ".join(str(d) for d in s.get("decisions") or []),
        " ".join(str(d) for d in s.get("upgrade_signals") or []),
        " ".join(str(d) for d in s.get("article_signals") or []),
        " ".join(str(q) for q in s.get("open_questions") or []),
        " ".join(str(ev) for ev in s.get("evidence_snippets") or []),
    ])


def _safe_text(*candidates) -> str:
    """返回第一个通过隐私门控的候选(截断到 MAX_EVIDENCE_CHARS),都没有则空串。"""
    for c in candidates:
        text = str(c or "").strip()
        if text:
            text = text[:MAX_EVIDENCE_CHARS]
            if _text_safe(text):
                return text
    return ""


def _collect_signals(sessions: list[dict]) -> list[tuple[str, str, str, str]]:
    """扫描 sessions → (scope, sub_topic, session_hash, evidence_text) 信号列表。"""
    categories = load_focus_config()
    signals: list[tuple[str, str, str, str]] = []
    for s in sessions:
        sid = s.get("session_id") or ""
        if not sid:
            continue
        shash = _session_hash(sid)
        snippets = s.get("evidence_snippets") or []
        first_snippet = str(snippets[0]) if snippets else ""
        topic = s.get("topic_title") or ""

        # focus:专注方向桶(多标签)
        ftext = _focus_text(s)
        if ftext.strip():
            hits = match_focus(ftext, categories)
            for h in hits:
                ev = _safe_text(first_snippet, topic)
                if ev:
                    signals.append(("focus", h, shash, ev))

        # correction:skill 边界 / 约束缺失(在 decisions + upgrade_signals)
        ab = _attr_blob(s)
        if ab:
            for m in _SKILL_BOUNDARY_RE.finditer(ab):
                signals.append(("correction", "skill_boundary", shash, _snippet(ab, m.start(), m.end(), 30)))
            for m in _HIDDEN_CONSTRAINT_RE.finditer(ab):
                signals.append(("correction", "hidden_constraint", shash, _snippet(ab, m.start(), m.end(), 30)))
        # correction:纠正短语 / 问法(在 full blob)
        fb = _full_blob(s)
        for m in _CORRECTION_PHRASE_RE.finditer(fb):
            signals.append(("correction", "correction_phrase", shash, _snippet(fb, m.start(), m.end(), 40)))
        for m in _Q_FORM_RE.finditer(fb):
            signals.append(("correction", "q_form", shash, _snippet(fb, m.start(), m.end(), 40)))

        # sediment:upgrade_signals + article_signals(第一期 sub=general,模型在 claim 细分)
        sig_texts = [
            str(sig).strip()
            for sig in (s.get("upgrade_signals") or []) + (s.get("article_signals") or [])
            if str(sig).strip()
        ]
        if sig_texts:
            ev = _safe_text(sig_texts[0])
            if ev:
                signals.append(("sediment", "general", shash, ev))

        # recurrence:related_skills(evidence 用 topic / decisions 首条)
        first_decision = str((s.get("decisions") or [""])[0])
        for skill_id in s.get("related_skills") or []:
            ev = _safe_text(topic, first_decision, skill_id)
            if ev:
                signals.append(("recurrence", str(skill_id), shash, ev))
    return signals


def _scope_title(scope: str, sub: str) -> str:
    base = _SCOPE_TITLE.get(scope, scope)
    if scope == "correction":
        return f"{base}:{_CORRECTION_SUB.get(sub, sub)}"
    return f"{base}:{sub}"


def _cluster_signals(signals: list[tuple[str, str, str, str]]) -> list[dict[str, Any]]:
    """按 (scope, sub_topic) 聚类;只保留跨 ≥2 session 且 ≥2 跨会话 evidence 的 cluster。"""
    # 先按 (scope, sub, session_hash, text) 去重:同 session 同子题里归因正则多次命中、
    # snippet 文本相同时只算一条,避免产生重复 evidence_id(eid = hash(shash+scope+sub+text))。
    seen: set[tuple[str, str, str, str]] = set()
    unique_signals: list[tuple[str, str, str, str]] = []
    for sig in signals:
        if sig in seen:
            continue
        seen.add(sig)
        unique_signals.append(sig)

    groups: dict[tuple[str, str], dict[str, list[dict[str, str]]]] = {}
    for scope, sub, shash, text in unique_signals:
        key = (scope, sub)
        bucket = groups.setdefault(key, {}).setdefault(shash, [])
        if len(bucket) < 2:  # 每 session 最多 2 evidence
            eid = "ev-" + hashlib.sha256(
                f"{shash}\0{scope}\0{sub}\0{text}".encode("utf-8", errors="replace")
            ).hexdigest()[:16]
            bucket.append({"evidence_id": eid, "source_session_id_hash": shash, "text": text})

    clusters: list[dict[str, Any]] = []
    for (scope, sub), sessions_map in groups.items():
        session_hashes = sorted(sessions_map.keys())
        if len(session_hashes) < 2:
            continue  # 跨会话门槛
        evidence: list[dict[str, str]] = []
        for sh in session_hashes:
            evidence.extend(sessions_map[sh])
        if len(evidence) < 2:
            continue
        evidence = evidence[:16]  # 上限 16(和 dream_sweep 一致)
        ev_sessions = {ev["source_session_id_hash"] for ev in evidence}
        if len(ev_sessions) < 2:
            continue
        cluster_id = "wmp-clu-" + hashlib.sha256(
            f"{scope}\0{sub}".encode("utf-8", errors="replace")
        ).hexdigest()[:20]
        clusters.append({
            "cluster_id": cluster_id,
            "topic_key": f"{scope}:{sub}"[:120],
            "title": _scope_title(scope, sub)[:200],
            "session_count": len(session_hashes),
            "source_session_id_hashes": session_hashes,
            "evidence": evidence,
        })
    clusters.sort(key=lambda c: c["cluster_id"])
    return clusters


def build_packet(clusters: list[dict[str, Any]]) -> dict[str, Any]:
    packet = {
        "schema_version": EVIDENCE_SCHEMA,
        "generated_at": now_iso(),
        "source_digest": digest(clusters),
        "clusters": clusters,
        "export_summary": {
            "cluster_count": len(clusters),
            "scope_counts": dict(Counter(c["topic_key"].split(":", 1)[0] for c in clusters)),
        },
    }
    validate_evidence_packet(packet)  # self-check:产出即符合 workmode_ledger 消费契约
    return packet


def extract(since: str, *, max_clusters: int | None = None) -> dict[str, Any]:
    data = gather(since)
    signals = _collect_signals(data["sessions"])
    clusters = _cluster_signals(signals)
    if max_clusters is not None:
        clusters = clusters[:max_clusters]
    return build_packet(clusters)


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o600)
        Path(name).replace(path)
    finally:
        try:
            Path(name).unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="从会话摘要提炼工作模式偏好证据包(不调模型)")
    ap.add_argument("--since", default="14d", help="时间窗:Nd/Nh/Nw 或 all(默认 14d)")
    ap.add_argument("--output", type=Path, default=DEFAULT_PACKET)
    ap.add_argument("--max-clusters", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    packet = extract(args.since, max_clusters=args.max_clusters)
    _atomic_write(args.output, packet)

    result = {
        "since": args.since,
        "path": str(args.output),
        "clusters": len(packet["clusters"]),
        "source_digest": packet["source_digest"],
        "scope_counts": packet["export_summary"]["scope_counts"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
