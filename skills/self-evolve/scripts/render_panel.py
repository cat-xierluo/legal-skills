#!/usr/bin/env python3
"""Render the privacy-bounded Self Evolve review panel.

The static snapshot is read-only. When served by panel.py, the same UI exposes
read-only task state plus explicit human proposal decisions; it never executes tasks.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import time
import webbrowser
from pathlib import Path
from typing import Any

from legacy_hook import inspect_session_end, load_settings
from privacy_gate import sanitize_text, validate_text, validate_untrusted_source
from proposal_store import ProposalStore
from workmode_ledger import WorkmodeLedger
from self_evolve_paths import (
    PANEL_ROOT,
    PROPOSALS_ROOT,
    REVIEW_INBOX_ROOT,
    RUNTIME_ROOT,
    SKILL_ROOT,
    assert_external_write_path,
    assert_runtime_ready,
)


CONFIG_PATH = SKILL_ROOT / "config" / "scheduled_tasks.yaml"
INVENTORY_PATH = RUNTIME_ROOT / "skill-inventory.json"
CLUSTERS_PATH = RUNTIME_ROOT / "dreaming" / "topic-clusters.json"


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not match:
        return {}
    output: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line or line[:1].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        output[key.strip()] = value.strip().strip("'\"")
    return output


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def read_jsonl_tail(path: Path, limit: int = 80) -> list[dict[str, Any]]:
    """Read a bounded JSONL tail without loading an unbounded log."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            window = min(size, 512 * 1024)
            handle.seek(size - window)
            raw = handle.read(window)
    except OSError:
        return []
    lines = raw.splitlines()
    if size > window and lines:
        lines = lines[1:]
    output: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            item = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(item, dict):
            output.append(item)
    return output


def safe_text(value: Any, *, max_chars: int = 320) -> str:
    text = str(value or "")[: max_chars * 4]
    if validate_untrusted_source(text):
        return "<content-quarantined>"
    sanitized, _ = sanitize_text(text)
    if validate_text(sanitized):
        return "<content-quarantined>"
    return sanitized[:max_chars]


def collect_legacy_hook_status(settings_path: Path | None = None) -> dict[str, Any]:
    """Treat no SessionEnd hook as healthy; expose residue without its command."""
    path = settings_path or Path.home() / ".claude" / "settings.json"
    try:
        settings = load_settings(path)
    except ValueError:
        return {
            "status": "error",
            "status_label": "无法读取 Hook 设置",
            "residue_count": 0,
            "entries": [],
            "error": "settings_unreadable",
        }
    matches = inspect_session_end(settings)
    residue = [
        {
            "kind": "legacy-self-evolve",
            "event": "SessionEnd",
            "group_index": match["group_index"],
            "hook_index": match["hook_index"],
        }
        for match in matches
    ]
    return {
        "status": "warning" if residue else "healthy",
        "status_label": "发现旧 Hook 残留" if residue else "Cron-only 正常",
        "residue_count": len(residue),
        "entries": residue,
    }


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "未配置", "tasks": []}
    try:
        import yaml
    except ImportError:
        return {"error": "缺少 pyyaml：pip install pyyaml", "tasks": []}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"error": "scheduled_tasks.yaml 不存在", "tasks": []}
    except Exception as exc:
        return {"error": safe_text(exc), "tasks": []}
    return payload if isinstance(payload, dict) else {"error": "任务配置不是对象", "tasks": []}


def scheduler_log_paths() -> list[Path]:
    root = RUNTIME_ROOT / "scheduler"
    paths = [*root.glob("task-runs*.jsonl"), *(root / "task-runs").glob("*.jsonl")]
    return sorted(set(paths), key=lambda item: item.name)


def collect_scheduler(limit: int = 80) -> dict[str, Any]:
    config = load_yaml(CONFIG_PATH)
    tasks: list[dict[str, Any]] = []
    for raw in config.get("tasks", []) if isinstance(config.get("tasks"), list) else []:
        if not isinstance(raw, dict):
            continue
        runner = raw.get("runner") if isinstance(raw.get("runner"), dict) else {}
        schedule = raw.get("recommended_schedule")
        if not isinstance(schedule, dict):
            schedule = raw.get("schedule") if isinstance(raw.get("schedule"), dict) else {}
        command = raw.get("command") if isinstance(raw.get("command"), dict) else {}
        enabled = bool(runner.get("enabled", raw.get("enabled", False)))
        external_only = bool(runner.get("external_only", raw.get("external_only", False)))
        tasks.append(
            {
                "id": safe_text(raw.get("id"), max_chars=80),
                "name": safe_text(raw.get("name") or raw.get("id"), max_chars=120),
                "runner_enabled": enabled,
                "external_only": external_only,
                "schedule": {
                    "cron": safe_text(schedule.get("cron"), max_chars=80),
                    "timezone": safe_text(schedule.get("timezone"), max_chars=80),
                },
                "command_type": safe_text(command.get("type"), max_chars=80),
            }
        )
    runs: list[dict[str, Any]] = []
    for path in scheduler_log_paths():
        runs.extend(read_jsonl_tail(path, limit=limit))
    # 按时间戳排序后取最新 limit:否则历史遗留的单一 JSONL 文件会排在按月
    # 分片文件之后,[-limit:] 会把最新记录挤掉,运行记录永远停在旧日期。
    runs.sort(key=lambda item: str(item.get("timestamp") or item.get("started_at") or ""))
    safe_runs = [
        {
            "timestamp": safe_text(item.get("timestamp") or item.get("started_at"), max_chars=32),
            "task_id": safe_text(item.get("task_id") or item.get("id"), max_chars=80),
            "status": safe_text(item.get("status") or item.get("result"), max_chars=32),
            "reason": safe_text(item.get("reason") or item.get("error") or item.get("summary")),
        }
        for item in runs[-limit:]
    ]
    return {
        "schema_version": safe_text(config.get("schema_version") or config.get("version"), max_chars=16),
        "config_label": "config/scheduled_tasks.yaml",
        "config_error": safe_text(config.get("error")),
        "config_status": safe_text(config.get("status")),
        "tasks": tasks,
        "runs": safe_runs,
    }


def collect_proposals(store: ProposalStore | None = None) -> list[dict[str, Any]]:
    records = (store or ProposalStore(PROPOSALS_ROOT)).list()
    output: list[dict[str, Any]] = []
    for item in records:
        paths = [safe_text(path, max_chars=180) for path in item.get("artifact_paths", [])]
        paths = [path for path in paths if path and not Path(path).is_absolute() and ".." not in Path(path).parts]
        output.append(
            {
                "proposal_id": safe_text(item.get("proposal_id"), max_chars=24),
                "revision_hash": safe_text(item.get("revision_hash"), max_chars=64),
                "target_skill": safe_text(item.get("target_skill"), max_chars=100),
                "target_version": safe_text(item.get("target_version"), max_chars=32),
                "proposal_type": safe_text(item.get("proposal_type"), max_chars=40),
                "summary": safe_text(item.get("summary"), max_chars=400),
                "change_points": [safe_text(point, max_chars=180) for point in item.get("change_points", [])[:12]],
                "machine_disposition": safe_text(item.get("machine_disposition"), max_chars=32),
                "privacy_status": safe_text(item.get("privacy_status"), max_chars=32),
                "artifact_content_sha256": safe_text(item.get("artifact_content_sha256"), max_chars=64),
                "artifact_paths": paths,
                "human_decision": safe_text(item.get("human_decision"), max_chars=32),
                "decision_reason": safe_text(item.get("decision_reason"), max_chars=260),
                "outcome": safe_text(item.get("outcome"), max_chars=32),
                "updated_at": safe_text(item.get("updated_at"), max_chars=32),
            }
        )
    return output


def collect_workmode_candidates(store: WorkmodeLedger | None = None) -> dict[str, Any]:
    """只读投影工作模式偏好候选(供 panel Preference tab)。"""
    ledger = store or WorkmodeLedger()
    try:
        candidates = ledger.list_candidates()
    except (OSError, ValueError):
        return {"candidates": [], "counts": {}, "total": 0, "error": "ledger_unreadable"}
    counts = {"pending": 0, "accepted": 0, "rejected": 0, "observe": 0}
    safe_items: list[dict[str, Any]] = []
    for c in candidates:
        safe_items.append(
            {
                "candidate_id": safe_text(c.get("candidate_id"), max_chars=24),
                "revision": safe_text(c.get("revision"), max_chars=20),
                "scope": safe_text(c.get("scope"), max_chars=40),
                "claim": safe_text(c.get("claim"), max_chars=400),
                "polarity": safe_text(c.get("polarity"), max_chars=32),
                "confidence": c.get("confidence", 0),
                "support_session_count": c.get("support_session_count", 0),
                "rationale": safe_text(c.get("rationale"), max_chars=300),
                "human_decision": safe_text(c.get("human_decision"), max_chars=32),
                "decision_reason": safe_text(c.get("decision_reason"), max_chars=260),
                "decided_at": safe_text(c.get("decided_at"), max_chars=32),
                "application": safe_text(c.get("application"), max_chars=32),
            }
        )
        d = c.get("human_decision", "pending")
        if d in counts:
            counts[d] += 1
    return {"candidates": safe_items, "counts": counts, "total": len(safe_items)}


def _md_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return safe_text(stripped[2:], max_chars=120)
    return safe_text(fallback, max_chars=120)


def _md_summary(text: str) -> str:
    """第一个 blockquote 或 H1 后的首个正文行。"""
    for line in text.splitlines()[1:20]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("> "):
            return safe_text(stripped[2:], max_chars=240)
        if stripped.startswith(("#", "|", "---", "- ")):
            continue
        return safe_text(stripped, max_chars=240)
    return ""


def _md_stamp(name: str) -> str:
    """文件名 YYMMDD 前缀 → YYYY-MM-DD,失败回退空。"""
    m = re.match(r"^(\d{6})", name)
    if not m:
        return ""
    s = m.group(1)
    return f"20{s[:2]}-{s[2:4]}-{s[4:6]}"


def _doc_kind(rel_parts: tuple[str, ...], name: str) -> str:
    if len(rel_parts) > 1:
        return rel_parts[0]
    m = re.match(r"^\d{6}_([a-z_]+)", name)
    return m.group(1) if m else "document"


def _doc_metrics(all_meta: list[tuple[str, float]]) -> dict[str, Any]:
    """全集元数据 → {total, this_week, by_kind};不受 limit/kind/sort 影响。"""
    by_kind: dict[str, int] = {}
    one_week_ago = time.time() - 7 * 86400
    this_week = 0
    for doc_kind, mtime in all_meta:
        by_kind[doc_kind] = by_kind.get(doc_kind, 0) + 1
        if mtime >= one_week_ago:
            this_week += 1
    return {"total": len(all_meta), "this_week": this_week, "by_kind": by_kind}


def collect_review_documents(
    limit: int = 50, kind: str | None = None, sort: str = "newest"
) -> dict[str, Any]:
    """读 review/inbox 下的脱敏 md 报告,只读投影。

    kind: 过滤(iteration/deep-analysis/...);None 不过滤。
    sort: newest(默认,mtime 降序) | oldest(mtime 升序)。
    metrics: 全集统计(total/this_week/by_kind),不受 limit/kind 影响。
    """
    docs: list[dict[str, Any]] = []
    if not REVIEW_INBOX_ROOT.is_dir():
        return {
            "documents": docs,
            "total": 0,
            "metrics": {"total": 0, "this_week": 0, "by_kind": {}},
        }
    all_meta: list[tuple[str, float]] = []
    file_metas: list[tuple[Path, str, float]] = []
    for md in REVIEW_INBOX_ROOT.rglob("*.md"):
        try:
            mtime = md.stat().st_mtime
        except OSError:
            continue
        rel = md.relative_to(REVIEW_INBOX_ROOT)
        doc_kind = _doc_kind(rel.parts, md.name)
        all_meta.append((doc_kind, mtime))
        if kind is None or doc_kind == kind:
            file_metas.append((md, doc_kind, mtime))
    file_metas.sort(key=lambda x: x[2], reverse=(sort != "oldest"))
    for md, doc_kind, mtime in file_metas[:limit]:
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = md.relative_to(REVIEW_INBOX_ROOT)
        docs.append(
            {
                "id": safe_text(str(rel), max_chars=120),
                "kind": safe_text(doc_kind, max_chars=40),
                "title": _md_title(text, md.stem),
                "generated_at": _md_stamp(md.name),
                "summary": _md_summary(text),
                "body": safe_text(text, max_chars=20000),
                "mtime": mtime,
            }
        )
    return {"documents": docs, "total": len(docs), "metrics": _doc_metrics(all_meta)}


def collect_inventory() -> dict[str, Any]:
    payload = read_json(INVENTORY_PATH)
    if not isinstance(payload, dict):
        return {"count": 0, "generated_at": ""}
    skills = payload.get("skills") if isinstance(payload.get("skills"), list) else []
    return {
        "count": len(skills),
        "generated_at": safe_text(payload.get("generated_at"), max_chars=32),
        "schema_version": safe_text(payload.get("schema_version"), max_chars=16),
    }


def collect_clusters() -> dict[str, Any]:
    payload = read_json(CLUSTERS_PATH)
    if isinstance(payload, list):
        clusters = payload
        generated_at = ""
    elif isinstance(payload, dict):
        clusters = payload.get("clusters") if isinstance(payload.get("clusters"), list) else []
        generated_at = safe_text(payload.get("generated_at"), max_chars=32)
    else:
        clusters, generated_at = [], ""
    quality: dict[str, int] = {}
    for item in clusters:
        if not isinstance(item, dict):
            continue
        gate = safe_text(item.get("quality_gate") or "legacy", max_chars=32)
        quality[gate] = quality.get(gate, 0) + 1
    return {"count": len(clusters), "generated_at": generated_at, "quality": quality}


def build_panel_data(limit: int = 80) -> dict[str, Any]:
    try:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        skill_text = ""
    frontmatter = parse_frontmatter(skill_text)
    hook = collect_legacy_hook_status()
    scheduler = collect_scheduler(limit)
    proposals = collect_proposals()
    inventory = collect_inventory()
    clusters = collect_clusters()
    proposal_counts: dict[str, int] = {}
    for item in proposals:
        state = item.get("human_decision") or "pending"
        proposal_counts[state] = proposal_counts.get(state, 0) + 1
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "skill": {
            "name": safe_text(frontmatter.get("name") or "self-evolve", max_chars=80),
            "version": safe_text(frontmatter.get("version"), max_chars=20),
            "mode": "cron-only",
        },
        "legacy_hook": hook,
        "scheduler": scheduler,
        "proposals": proposals,
        "inventory": inventory,
        "clusters": clusters,
        "metrics": {
            "proposal_total": len(proposals),
            "proposal_pending": proposal_counts.get("pending", 0),
            "inventory_count": inventory["count"],
            "cluster_count": clusters["count"],
            "task_count": len(scheduler["tasks"]),
        },
    }


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <link rel="icon" href="data:,">
  <title>Self Evolve</title>
  <style>
    :root{color-scheme:light;--bg:#f4f6f8;--card:#fff;--ink:#17202a;--muted:#667085;--line:#dfe4ea;--blue:#155eef;--green:#067647;--amber:#b54708;--red:#b42318}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    .shell{max-width:1180px;margin:auto;padding:28px 20px 60px}header{display:flex;justify-content:space-between;align-items:end;gap:16px;margin-bottom:18px}h1{margin:0;font-size:28px}h2{font-size:17px;margin:0 0 14px}.muted{color:var(--muted)}
    nav{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}button,.button{border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:8px;padding:8px 11px;cursor:pointer;font:inherit}button:hover{border-color:#aeb8c4}button.primary{background:var(--blue);border-color:var(--blue);color:#fff}button.danger{color:var(--red)}button:disabled{opacity:.45;cursor:not-allowed}nav button.active{background:#e8efff;border-color:#b9cbff;color:#1649a6}
    .tab{display:none}.tab.active{display:block}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 1px 2px #1018280a}.metric strong{font-size:26px;display:block}.badge{display:inline-block;border-radius:999px;padding:2px 8px;background:#eef2f6;color:#344054;font-size:12px}.badge.healthy{background:#e7f6ec;color:var(--green)}.badge.warning{background:#fff1df;color:var(--amber)}.badge.error{background:#feeceb;color:var(--red)}
    table{width:100%;border-collapse:collapse}th,td{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:10px 8px}th{font-size:12px;color:var(--muted)}tr:last-child td{border-bottom:0}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}.actions{display:flex;gap:6px;flex-wrap:wrap}.summary{color:var(--muted);margin-top:3px}.empty{padding:16px;background:#f8fafc;border-radius:8px;color:var(--muted)}
    .toast{position:fixed;right:18px;bottom:18px;background:#111827;color:#fff;padding:9px 12px;border-radius:8px;display:none}.toast.show{display:block}
    .pref-card .bar{height:6px;background:#eef2f6;border-radius:4px;overflow:hidden;margin-top:6px}.pref-card .bar span{display:block;height:100%;background:var(--blue)}
    @media(max-width:800px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}header{display:block}table{display:block;overflow:auto}.shell{padding:18px 12px 40px}}
  /* 沉淀报告 tab:dashboard 设计系统(局部 .sed-*,不动其他 tab) */
  .sed{--sed-paper:#efece8;--sed-surface:#fbf9f5;--sed-surface-soft:#f4f0ea;--sed-ink:#2b2622;--sed-muted:#6e635a;--sed-faint:#9c9087;--sed-line:#ddd5cb;--sed-moss:#a24f36;--sed-moss-dark:#7a3a26;--sed-moss-soft:#f4e4dc;--sed-clay:#8b6a27;--sed-clay-soft:#f6edcf;--sed-amber:#6e635a;--sed-amber-soft:#ece6df;--sed-radius:14px;--sed-shadow:0 14px 40px rgba(59,49,35,.07);--sed-serif:"Songti SC","STSong","Noto Serif CJK SC",Georgia,serif;color:var(--sed-ink)}
  .sed h2,.sed h3{font-family:var(--sed-serif);font-weight:600;letter-spacing:-.01em;margin:0}
  .sed-hero{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(360px,.7fr);background:var(--sed-surface);border:1px solid var(--sed-line);border-radius:20px;box-shadow:var(--sed-shadow);overflow:hidden;margin-bottom:18px}
  .sed-hero-copy{padding:clamp(20px,3vw,36px);background:linear-gradient(145deg,rgba(255,253,248,.95),rgba(244,239,225,.74))}
  .sed-eyebrow{margin-bottom:4px;color:var(--sed-moss);font-size:11px;font-weight:700;letter-spacing:.16em;text-transform:uppercase}
  .sed-hero-copy h2{margin:8px 0 8px;font:600 clamp(22px,3vw,34px)/1.18 var(--sed-serif);letter-spacing:-.025em}
  .sed-hero-copy>p{max-width:560px;color:var(--sed-muted);font-size:13px;line-height:1.55}
  .sed-hero-metrics{display:grid;grid-template-columns:repeat(3,1fr);border-left:1px solid var(--sed-line);background:var(--sed-paper)}
  .sed-metric{min-width:0;padding:22px 16px;border-left:1px solid rgba(125,112,91,.16);display:flex;flex-direction:column;justify-content:flex-end}
  .sed-metric:first-child{border-left:0}
  .sed-metric .num{color:var(--sed-ink);font:600 30px/1 var(--sed-serif);font-variant-numeric:tabular-nums}
  .sed-metric .lbl{margin-top:6px;color:var(--sed-muted);font-size:12px}
  .sed-metric .hint{margin-top:4px;color:var(--sed-faint);font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .sed-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:12px 14px;background:var(--sed-surface);border:1px solid var(--sed-line);border-radius:12px;margin-bottom:14px;color:var(--sed-muted);font-size:12px}
  .sed-toolbar input{min-height:36px;padding:7px 10px;background:#fffefa;border:1px solid var(--sed-line);border-radius:8px;font-size:12px;color:var(--sed-ink);flex:1;min-width:135px}
  .sed-count{margin-left:auto;color:var(--sed-muted);font-size:12px}
  .sed-lib-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}
  .sed-lib-card{min-height:140px;display:grid;grid-template-columns:52px minmax(0,1fr);gap:14px;padding:16px;background:var(--sed-surface);border:1px solid var(--sed-line);border-radius:13px;cursor:pointer;transition:transform .16s,box-shadow .16s,border-color .16s}
  .sed-lib-card:hover{transform:translateY(-1px);border-color:#c2b8a7;box-shadow:0 8px 22px rgba(59,49,35,.07)}
  .sed-lib-card .lc-score{padding-top:2px;font:600 22px/1 var(--sed-serif);text-align:center;color:var(--sed-moss);text-transform:uppercase;letter-spacing:.02em}
  .sed-lib-card .lc-title{margin-bottom:5px;color:var(--sed-ink);font:600 15px/1.42 var(--sed-serif)}
  .sed-lib-card .lc-sum{margin-bottom:8px;color:var(--sed-muted);font-size:11px;line-height:1.55;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .sed-lib-card .lc-meta{color:var(--sed-faint);font-size:10px}
  .sed-paper-panel{background:var(--sed-surface);border:1px solid var(--sed-line);border-radius:var(--sed-radius);box-shadow:0 8px 24px rgba(59,49,35,.045);overflow:hidden;margin-bottom:14px}
  .sed-panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:18px 20px 14px;border-bottom:1px solid var(--sed-line)}
  .sed-panel-head h3{font:600 18px/1.25 var(--sed-serif);margin:0}
  .sed-panel-head p{margin-top:3px;color:var(--sed-muted);font-size:12px;margin-bottom:0}
  .sed-panel-body{padding:18px 22px}
  .sed-empty{padding:42px 24px;color:var(--sed-muted);text-align:center}
  .sed-md{font:14px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;color:var(--sed-ink);max-width:none}
  .sed-md h1,.sed-md h2,.sed-md h3{font-family:var(--sed-serif);font-weight:600;letter-spacing:-.01em;margin:18px 0 10px;color:var(--sed-ink)}
  .sed-md h1{font-size:22px;border-bottom:1px solid var(--sed-line);padding-bottom:6px}
  .sed-md h2{font-size:18px}
  .sed-md h3{font-size:15px}
  .sed-md p{margin:10px 0;color:var(--sed-ink)}
  .sed-md blockquote{margin:12px 0;padding:10px 16px;color:var(--sed-muted);border-left:3px solid var(--sed-moss);background:var(--sed-paper);border-radius:0 8px 8px 0}
  .sed-md ul,.sed-md ol{margin:10px 0;padding-left:24px}
  .sed-md li{margin:4px 0}
  .sed-md table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13px;background:var(--sed-surface);border:1px solid var(--sed-line);border-radius:8px;overflow:hidden}
  .sed-md th,.sed-md td{padding:9px 12px;border-bottom:1px solid var(--sed-line);text-align:left;vertical-align:top}
  .sed-md th{background:var(--sed-paper);color:var(--sed-muted);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
  .sed-md tbody tr:last-child td{border-bottom:0}
  .sed-md code{background:var(--sed-paper);padding:1px 6px;border-radius:4px;font:12px ui-monospace,monospace;color:var(--sed-clay)}
  .sed-md strong{font-weight:700;color:var(--sed-ink)}
  .sed-md pre{max-height:380px;overflow:auto;padding:12px;background:#253129;color:#dfe6dd;border-radius:8px;font:12px ui-monospace,monospace;white-space:pre-wrap}
  /* sidebar 布局(参照 dashboard.html)+ main.app 暖灰主区;暖灰+赤陶配色(和 info-evaluator 米色+moss 区分) */
  .sidebar{position:fixed;inset:0 auto 0 0;width:238px;padding:24px 18px 18px;display:flex;flex-direction:column;z-index:60;color:#f0ebe3;background:#3d3530;border-right:1px solid #574b44;overflow-y:auto}
  .sidebar-brand{display:flex;gap:12px;align-items:center;padding:0 7px 18px}
  .brand-mark{width:40px;height:40px;display:grid;place-items:center;color:#f4d9c8;border:1px solid #7a5c4d;border-radius:12px;background:#4a3f38;font:600 16px "Songti SC",serif}
  .sb-name{display:block;font:600 17px/1.15 "Songti SC",serif;letter-spacing:.02em;color:#fbf6ee}
  .sb-caption{display:block;margin-top:4px;color:#b8a99c;font-size:10px;letter-spacing:.14em;text-transform:uppercase}
  .sidebar-sub{min-height:40px;padding:12px 8px;color:#c2b3a4;border-top:1px solid #574b44;border-bottom:1px solid #574b44;font-size:11px;line-height:1.6}
  .sidebar-nav{display:grid;gap:4px;padding:16px 0;flex:1;align-content:start}
  .sidebar-nav button{width:100%;display:flex;align-items:center;gap:10px;padding:10px 12px;color:#c2b3a4;background:transparent;border:1px solid transparent;border-radius:10px;cursor:pointer;font-weight:550;text-align:left;font:inherit;color:inherit;transition:color .18s,background .18s,border-color .18s}
  .sidebar-nav button:hover{color:#fbf6ee;background:#4a3f38}
  .sidebar-nav button.active{color:#fbf6ee;background:#54453c;border-color:#6e574a;box-shadow:inset 3px 0 0 #c97a5a}
  .sidebar-footer{padding:12px 8px 0;border-top:1px solid #574b44;color:#a89889;font-size:10px;line-height:1.5}
  main.app{margin-left:238px;min-height:100vh;padding:28px clamp(20px,3vw,48px) 70px;background:#efece8;box-sizing:border-box}
  .app .topbar{max-width:1240px;margin:0 auto 22px;display:flex;align-items:flex-end;justify-content:space-between;gap:20px;flex-wrap:wrap}
  .app .topbar h1{font:600 28px/1.12 "Songti SC",serif;margin:0;letter-spacing:-.01em;color:#2b2622}
  .app .eyebrow{color:#a24f36;font-size:11px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;margin-bottom:5px}
  .view{display:none;max-width:1240px;margin:0 auto;animation:reveal .2s ease both}
  .view.show{display:block}
  @keyframes reveal{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
  @media(max-width:800px){.sidebar{position:static;width:auto;flex-direction:row;flex-wrap:wrap;gap:8px}.sidebar-nav{display:flex;flex-wrap:wrap;gap:4px}.sidebar-nav button{width:auto}main.app{margin-left:0}}
  /* dashboard 通用 view 组件(所有 view 统一 moss serif 风格) */
  main.app{--d-paper:#efece8;--d-surface:#fbf9f5;--d-surface-soft:#f4f0ea;--d-ink:#2b2622;--d-muted:#6e635a;--d-faint:#9c9087;--d-line:#ddd5cb;--d-moss:#a24f36;--d-moss-dark:#7a3a26;--d-moss-soft:#f4e4dc;--d-clay:#8b6a27;--d-clay-soft:#f6edcf;--d-amber:#6e635a;--d-amber-soft:#ece6df;--d-serif:"Songti SC","STSong","Noto Serif CJK SC",Georgia,serif;color:var(--d-ink)}
  .d-section-heading{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:0 0 14px}
  .d-section-heading h2{font:600 21px/1.2 var(--d-serif);color:var(--d-ink);margin:0}
  .d-section-heading p{margin-top:4px;color:var(--d-muted);font-size:12px;margin-bottom:0}
  .d-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:20px}
  .d-card{padding:18px;background:var(--d-surface);border:1px solid var(--d-line);border-radius:12px}
  .d-card .num{color:var(--d-ink);font:600 28px/1 var(--d-serif);font-variant-numeric:tabular-nums}
  .d-card .lbl{margin-top:6px;color:var(--d-muted);font-size:12px}
  .d-card .hint{margin-top:4px;color:var(--d-faint);font-size:10px}
  .d-card.moss .num{color:var(--d-moss)} .d-card.amber .num{color:var(--d-amber)} .d-card.clay .num{color:var(--d-clay)} .d-card.faint .num{color:var(--d-faint)}
  .d-panel{background:var(--d-surface);border:1px solid var(--d-line);border-radius:14px;box-shadow:0 8px 24px rgba(59,49,35,.045);overflow:hidden;margin-bottom:18px}
  .d-panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:18px 20px 14px;border-bottom:1px solid var(--d-line)}
  .d-panel-head h3{font:600 18px/1.25 var(--d-serif);margin:0;color:var(--d-ink)}
  .d-panel-head p{margin-top:3px;color:var(--d-muted);font-size:12px;margin-bottom:0}
  .d-panel-body{padding:14px}
  .d-table{width:100%;border-collapse:collapse;background:var(--d-surface);font-size:12px}
  .d-table thead th{padding:11px 14px;color:var(--d-muted);background:var(--d-surface-soft);border-bottom:1px solid var(--d-line);text-align:left;font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase}
  .d-table tbody td{padding:12px 14px;border-top:1px solid #eee8dc;vertical-align:top;color:var(--d-ink)}
  .d-table tbody tr:hover{background:var(--d-surface-soft)}
  .d-badge{display:inline-flex;align-items:center;min-height:22px;padding:2px 9px;border-radius:99px;font-size:10px;font-weight:700;letter-spacing:.02em}
  .d-badge.moss{color:#7a3a26;background:var(--d-moss-soft)} .d-badge.amber{color:#5a4830;background:var(--d-amber-soft)} .d-badge.clay{color:#5a4830;background:var(--d-clay-soft)} .d-badge.muted{color:var(--d-muted);background:#e8e1d8} .d-badge.faint{color:var(--d-faint);background:#e8e1d8}
  .d-actions{display:flex;gap:6px;flex-wrap:wrap}
  .d-btn{min-height:34px;display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border:1px solid transparent;border-radius:8px;font-size:12px;font-weight:650;cursor:pointer;transition:transform .16s,background .16s,border-color .16s}
  .d-btn:hover{transform:translateY(-1px)}
  .d-btn:disabled{opacity:.45;cursor:not-allowed;transform:none}
  .d-btn-primary{color:#fffdf8;background:var(--d-moss);border-color:var(--d-moss)} .d-btn-primary:hover{background:var(--d-moss-dark)}
  .d-btn-sec{color:var(--d-ink);background:var(--d-surface);border-color:var(--d-line)} .d-btn-sec:hover{background:var(--d-surface-soft)}
  .d-btn-quiet{color:var(--d-moss);background:transparent;border-color:transparent} .d-btn-quiet:hover{background:var(--d-moss-soft)}
  .d-btn-danger{color:#fffdf8;background:var(--d-clay);border-color:var(--d-clay)}
  .d-empty{padding:42px 24px;color:var(--d-muted);text-align:center}
  .d-mono{font:11px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--d-faint)}
  .d-muted{color:var(--d-muted);font-size:12px}
  .d-row{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:5px}
  .d-pref{background:var(--d-surface);border:1px solid var(--d-line);border-radius:12px;padding:16px;margin-bottom:12px}
  .d-pref-head{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
  .d-pref-claim{margin:8px 0;color:var(--d-ink);font-size:14px;line-height:1.55}
  .d-pref-bar{height:6px;background:#e8e2d7;border-radius:99px;overflow:hidden;margin:6px 0}
  .d-pref-bar span{display:block;height:100%;background:var(--d-moss)}
  </style>
</head>
<body>
<aside class="sidebar">
  <div class="sidebar-brand"><div class="brand-mark">SE</div><div><span class="sb-name">Self Evolve</span><span class="sb-caption" id="sb-version">self-iteration</span></div></div>
  <div class="sidebar-sub" id="sb-sub">自我迭代 · Cron-only<br>从会话沉淀经验与偏好</div>
  <nav class="sidebar-nav">
    <button class="active" data-view="overview">总览</button>
    <button data-view="review">Review Inbox</button>
    <button data-view="preferences">偏好审阅</button>
    <button data-view="documents">沉淀报告</button>
    <button data-view="scheduler">Cron 任务</button>
    <button data-view="logs">运行记录</button>
  </nav>
  <div class="sidebar-footer" id="sb-footer">loopback only · 一次性 token<br>决定仅追加,不覆盖</div>
</aside>
<main class="app">
  <div class="topbar"><div><div class="eyebrow">SELF-EVOLVE PANEL</div><h1 id="tb-title">Self Evolve</h1></div><div class="muted" style="text-align:right"><div id="subtitle"></div><div id="generated"></div></div></div>
  <div id="overview" class="view show"></div>
  <div id="review" class="view"></div>
  <div id="preferences" class="view"></div>
  <div id="documents" class="view"></div>
  <div id="scheduler" class="view"></div>
  <div id="logs" class="view"></div>
</main>
<div id="toast" class="toast"></div>
<script__SCRIPT_NONCE_ATTR__>
let DATA=__PANEL_DATA__;const SERVER_MODE=__SERVER_MODE__;let NONCE=__REQUEST_NONCE__;let SESSION_TOKEN="";const SESSION_KEY="self-evolve.session";
const esc=v=>String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;");
const badge=(label,kind="")=>`<span class="badge ${esc(kind)}">${esc(label||"-")}</span>`;
const dB=(label,kind="muted")=>`<span class="d-badge ${esc(kind)}">${esc(label||"-")}</span>`;
function toast(message){const el=document.getElementById("toast");el.textContent=message;el.classList.add("show");setTimeout(()=>el.classList.remove("show"),1600)}
const sessionHeaders=()=>SESSION_TOKEN?{"Authorization":`Bearer ${SESSION_TOKEN}`}:{ };
async function authenticateServer(){SESSION_TOKEN=sessionStorage.getItem(SESSION_KEY)||"";if(location.hash){const fragment=new URLSearchParams(location.hash.slice(1)),tokens=fragment.getAll("token");if(fragment.size!==1||tokens.length!==1||!tokens[0])throw new Error("认证入口无效，请重启面板获取新 URL");const r=await fetch("/auth",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token:tokens[0]})});const payload=await r.json().catch(()=>({}));if(!r.ok||payload.ok!==true||!payload.session_token)throw new Error(payload.error||`HTTP ${r.status}`);SESSION_TOKEN=payload.session_token;sessionStorage.setItem(SESSION_KEY,SESSION_TOKEN);history.replaceState(null,"",location.pathname)}if(!SESSION_TOKEN)throw new Error("请使用面板启动命令输出的一次性完整 URL");const r=await fetch("/api/panel",{headers:sessionHeaders()});const payload=await r.json().catch(()=>({}));if(r.status===401)sessionStorage.removeItem(SESSION_KEY);if(!r.ok||payload.ok!==true||!payload.data||!payload.nonce)throw new Error(payload.error||`HTTP ${r.status}`);DATA=payload.data;NONCE=payload.nonce}
async function postJson(url,payload){const r=await fetch(url,{method:"POST",headers:{...sessionHeaders(),"Content-Type":"application/json","X-Self-Evolve-Nonce":NONCE},body:JSON.stringify(payload||{})});const data=await r.json().catch(()=>({}));if(r.status===401)sessionStorage.removeItem(SESSION_KEY);if(!r.ok||data.ok===false)throw new Error(data.error||`HTTP ${r.status}`);return data}
function stateKind(value){if(["healthy","passed","accepted","partially_accepted","verified","success","completed"].includes(value))return"healthy";if(["warning","candidate","observe","pending","skipped"].includes(value))return"warning";if(["failed","quarantined","rejected"].includes(value))return"error";return""}
async function decideProposal(id,decision,revisionHash,artifactHash){let reason="";if(decision==="rejected"){reason=prompt("请填写拒绝理由：")||"";if(!reason.trim())return}if(decision==="observe")reason=prompt("观察备注（可留空）：")||"";if(decision==="accepted"&&!confirm("确认接受当前版本的提案？"))return;try{await postJson(`/api/proposals/${encodeURIComponent(id)}/decision`,{decision,reason,revision_hash:revisionHash,artifact_sha256:artifactHash});toast("决定已记录");setTimeout(()=>location.reload(),500)}catch(err){toast(err.message||"写入失败")}}
function renderOverview(){const m=DATA.metrics,h=DATA.legacy_hook;document.getElementById("overview").innerHTML=`
  <div class="d-cards"><div class="d-card clay"><div class="num">${esc(m.proposal_pending)}</div><div class="lbl">待人工决定</div></div><div class="d-card moss"><div class="num">${esc(m.inventory_count)}</div><div class="lbl">Skill 库存</div></div><div class="d-card amber"><div class="num">${esc(m.cluster_count)}</div><div class="lbl">主题簇</div></div><div class="d-card faint"><div class="num">${esc(m.task_count)}</div><div class="lbl">登记任务</div></div></div>
  <div class="d-panel"><div class="d-panel-head"><div><h3>运行架构</h3><p>外部 Cron 只负责唤醒；所有任务统一进入受限执行器。</p></div>${dB("Cron-only","moss")}</div><div class="d-panel-body"><table class="d-table"><tbody><tr><td class="d-muted" style="width:140px">旧 Hook</td><td>${dB(h.status_label,h.status==="healthy"?"moss":h.status==="warning"?"amber":"clay")}</td></tr><tr><td class="d-muted">提案总数</td><td>${esc(m.proposal_total)}</td></tr><tr><td class="d-muted">Inventory</td><td>${esc(DATA.inventory.generated_at||"尚未生成")}</td></tr></tbody></table></div></div>
  <div class="d-panel"><div class="d-panel-head"><div><h3>Legacy Hook 诊断</h3></div></div><div class="d-panel-body">${h.residue_count?`<p class="d-muted">发现 ${esc(h.residue_count)} 条旧 SessionEnd 入口。先运行 <span class="d-mono">python3 scripts/legacy_hook.py status</span>；确认后 <span class="d-mono">remove --apply</span>。</p>`:`<div class="d-empty">未发现 SessionEnd Hook；Cron-only 架构正常。</div>`}</div></div>`}
function proposalActions(item){if(!SERVER_MODE||item.human_decision!=="pending")return"";const a=`data-action="proposal-decision" data-proposal-id="${esc(item.proposal_id)}" data-revision-hash="${esc(item.revision_hash||"")}" data-artifact-hash="${esc(item.artifact_content_sha256||"")}"`;return`<div class="d-actions"><button class="d-btn d-btn-primary" ${a} data-decision="accepted" ${item.privacy_status==="passed"?"":"disabled"}>接受</button><button class="d-btn d-btn-sec" ${a} data-decision="observe">观察</button><button class="d-btn d-btn-danger" ${a} data-decision="rejected">拒绝</button></div>`}
function renderReview(){const rows=(DATA.proposals||[]).map(item=>`<tr><td><div style="font-weight:600">${esc(item.target_skill||"未路由")}</div><div class="d-mono">${esc(item.proposal_id)}</div></td><td>${dB(item.proposal_type)} ${dB(item.machine_disposition,stateKind(item.machine_disposition))}<div class="d-muted" style="margin-top:4px">${esc(item.summary)}</div><div class="d-muted">${(item.change_points||[]).map(esc).join(" · ")}</div></td><td>${dB(item.privacy_status,stateKind(item.privacy_status))} ${dB(item.human_decision,stateKind(item.human_decision))}${item.decision_reason?`<div class="d-muted" style="margin-top:4px">${esc(item.decision_reason)}</div>`:""}</td><td class="d-mono">${esc(item.updated_at)}</td><td>${proposalActions(item)}</td></tr>`).join("");document.getElementById("review").innerHTML=`<div class="d-section-heading"><div><h2>Review Inbox</h2><p>机器只写推荐；接受/拒绝/观察只来自本地面板或 CLI。</p></div></div><div class="d-panel"><div class="d-panel-body">${rows?`<table class="d-table"><thead><tr><th>目标</th><th>提案</th><th>门控/人工</th><th>更新</th><th>操作</th></tr></thead><tbody>${rows}</tbody></table>`:`<div class="d-empty">暂无结构化提案。</div>`}</div></div>`}
function renderScheduler(){const s=DATA.scheduler;const rows=(s.tasks||[]).map(task=>`<tr><td><div style="font-weight:600">${esc(task.name)}</div><div class="d-mono">${esc(task.id)}</div></td><td>${dB(task.runner_enabled?"runner enabled":"kill switch off",task.runner_enabled?"moss":"clay")}</td><td>${task.external_only?dB("external Cron only","amber"):dB("external trigger","moss")}</td><td><span class="d-mono">${esc(task.schedule.cron||"-")}</span><div class="d-muted">${esc(task.schedule.timezone||"")}</div></td><td class="d-mono">${esc(task.command_type)}</td></tr>`).join("");document.getElementById("scheduler").innerHTML=`<div class="d-section-heading"><div><h2>Cron 任务</h2><p>外部 Cron 是注册与启停的唯一事实源；面板只读展示。</p></div></div><div class="d-panel"><div class="d-panel-body"><table class="d-table"><tbody><tr><td class="d-muted" style="width:140px">配置</td><td class="d-mono">${esc(s.config_label)}</td></tr><tr><td class="d-muted">Schema</td><td>${esc(s.schema_version||"-")}</td></tr>${s.config_status?`<tr><td class="d-muted">状态</td><td>${esc(s.config_status)}</td></tr>`:""}${s.config_error?`<tr><td class="d-muted">错误</td><td>${esc(s.config_error)}</td></tr>`:""}</tbody></table></div></div><div class="d-panel"><div class="d-panel-body">${rows?`<table class="d-table"><thead><tr><th>任务</th><th>Kill switch</th><th>触发</th><th>计划</th><th>命令</th></tr></thead><tbody>${rows}</tbody></table>`:`<div class="d-empty">暂无任务。</div>`}</div></div>`}
function renderLogs(){const rows=(DATA.scheduler.runs||[]).slice().reverse().map(r=>`<tr><td class="d-mono">${esc(r.timestamp)}</td><td class="d-mono">${esc(r.task_id)}</td><td>${dB(r.status,stateKind(r.status))}</td><td class="d-muted">${esc(r.reason)}</td></tr>`).join("");document.getElementById("logs").innerHTML=`<div class="d-section-heading"><div><h2>近期调度记录</h2></div></div><div class="d-panel"><div class="d-panel-body">${rows?`<table class="d-table"><thead><tr><th>时间</th><th>任务</th><th>状态</th><th>摘要</th></tr></thead><tbody>${rows}</tbody></table>`:`<div class="d-empty">尚无运行记录。</div>`}</div></div>`}
let WORKMODE=null;const SCOPE_LABEL={focus:"专注方向",correction:"纠错模式",sediment:"沉淀信号",recurrence:"反复 skill"};const POLARITY_LABEL={prefer:"偏好",avoid:"回避",constraint:"约束"};
async function loadWorkmode(){if(WORKMODE)return WORKMODE;const r=await fetch("/api/workmode-candidates",{headers:sessionHeaders()});const p=await r.json().catch(()=>({}));if(r.status===401)sessionStorage.removeItem(SESSION_KEY);if(!r.ok||p.ok!==true)throw new Error(p.error||`HTTP ${r.status}`);WORKMODE=p;return WORKMODE}
async function decidePreference(id,decision,revision){let reason="";if(decision==="rejected"){reason=prompt("拒绝这条偏好候选的理由:")||"";if(!reason.trim())return}if(decision==="observe")reason=prompt("观察备注(可留空):")||"";if(decision==="accepted"&&!confirm("确认接受这条工作模式偏好?"))return;try{await postJson(`/api/workmode-candidates/${encodeURIComponent(id)}/decision`,{decision,reason,revision});toast("偏好决定已记录");WORKMODE=null;await renderPreferences()}catch(err){toast(err.message||"写入失败")}}
async function renderPreferences(){const el=document.getElementById("preferences");el.innerHTML=`<div class="d-panel"><div class="d-panel-body"><p class="d-muted">加载偏好候选...</p></div></div>`;let data;try{data=await loadWorkmode()}catch(err){el.innerHTML=`<div class="d-panel"><div class="d-panel-body"><p class="d-muted">${esc(err.message||"加载失败")}</p></div></div>`;return}const items=data.candidates||[];const counts=data.counts||{};const cards=items.map(c=>{const conf=Math.round((c.confidence||0)*100);const acts=c.human_decision==="pending"?`<div class="d-actions" style="margin-top:10px"><button class="d-btn d-btn-primary" data-action="preference-decision" data-candidate-id="${esc(c.candidate_id)}" data-decision="accepted" data-revision="${esc(c.revision)}">接受</button><button class="d-btn d-btn-sec" data-action="preference-decision" data-candidate-id="${esc(c.candidate_id)}" data-decision="observe" data-revision="${esc(c.revision)}">观察</button><button class="d-btn d-btn-danger" data-action="preference-decision" data-candidate-id="${esc(c.candidate_id)}" data-decision="rejected" data-revision="${esc(c.revision)}">拒绝</button></div>`:`<div class="d-muted" style="margin-top:8px">${dB(c.human_decision,stateKind(c.human_decision))}${c.decision_reason?` ${esc(c.decision_reason)}`:""}</div>`;return `<div class="d-pref"><div class="d-pref-head">${dB(SCOPE_LABEL[c.scope]||c.scope,"moss")} ${dB(POLARITY_LABEL[c.polarity]||c.polarity)} ${dB(`${c.support_session_count||0} session`,"faint")} ${dB(c.human_decision,stateKind(c.human_decision))}</div><div class="d-pref-claim">${esc(c.claim)}</div><div class="d-pref-bar"><span style="width:${conf}%"></span></div><div class="d-muted">置信度 ${conf}%${c.rationale?` · ${esc(c.rationale)}`:""}</div>${acts}</div>`}).join("");el.innerHTML=`<div class="d-cards"><div class="d-card clay"><div class="num">${esc(counts.pending||0)}</div><div class="lbl">待审</div></div><div class="d-card moss"><div class="num">${esc(counts.accepted||0)}</div><div class="lbl">已接受</div></div><div class="d-card amber"><div class="num">${esc(counts.observe||0)}</div><div class="lbl">观察</div></div><div class="d-card faint"><div class="num">${esc(counts.rejected||0)}</div><div class="lbl">已拒绝</div></div></div><div class="d-section-heading"><div><h2>工作模式偏好</h2><p>专注/纠错/沉淀/反复调用模式;接受 ≠ 自动应用。</p></div></div>${cards||`<div class="d-panel"><div class="d-panel-body"><div class="d-empty">暂无偏好候选。运行 python3 scripts/workmode_pipeline.py --since 14d。</div></div></div>`}`}
let DOCS=null;let DOC_KIND_FILTER=null;let DOC_SORT="newest";let DOC_QUERY="";
async function loadDocuments(){if(DOCS)return DOCS;const r=await fetch("/api/review-documents",{headers:sessionHeaders()});const p=await r.json().catch(()=>({}));if(r.status===401)sessionStorage.removeItem(SESSION_KEY);if(!r.ok||p.ok!==true)throw new Error(p.error||`HTTP ${r.status}`);DOCS=p;return DOCS}
function renderMd(text){
  if(!text)return "";
  const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const inline=s=>esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
  const lines=text.split('\n');let html='';let i=0;
  while(i<lines.length){
    const line=lines[i];
    if(line.startsWith('|')&&i+1<lines.length&&/^\|[\s\-:|]+\|/.test(lines[i+1])){
      let tbl='<table><thead><tr>';
      line.split('|').slice(1,-1).forEach(c=>tbl+=`<th>${esc(c.trim())}</th>`);
      tbl+='</tr></thead><tbody>';
      i+=2;
      while(i<lines.length&&lines[i].startsWith('|')){
        tbl+='<tr>';
        lines[i].split('|').slice(1,-1).forEach(c=>tbl+=`<td>${inline(c.trim())}</td>`);
        tbl+='</tr>';
        i++;
      }
      tbl+='</tbody></table>';html+=tbl;continue;
    }
    const hm=line.match(/^(#{1,3})\s+(.*)/);
    if(hm){html+=`<h${hm[1].length}>${inline(hm[2])}</h${hm[1].length}>`;i++;continue;}
    if(line.startsWith('> ')){html+=`<blockquote>${inline(line.slice(2))}</blockquote>`;i++;continue;}
    if(/^[-*]\s/.test(line)){
      html+='<ul>';
      while(i<lines.length&&/^[-*]\s/.test(lines[i])){
        html+=`<li>${inline(lines[i].replace(/^[-*]\s/,''))}</li>`;
        i++;
      }
      html+='</ul>';continue;
    }
    if(/^\|[\s\-:|]+\|$/.test(line)){i++;continue;}
    if(!line.trim()){i++;continue;}
    let p=line;i++;
    while(i<lines.length&&lines[i].trim()&&!/^#{1,3}\s|^[-*]\s|^> |^\|/.test(lines[i])){p+=' '+lines[i];i++;}
    html+=`<p>${inline(p)}</p>`;
  }
  return html;
}

function showDocDetailById(id){
  if(!DOCS)return;
  const doc=(DOCS.documents||[]).find(d=>d.id===id);
  if(!doc)return;
  const el=document.getElementById("documents");
  el.innerHTML=`<div class="sed"><div style="margin-bottom:10px"><button class="button" data-action="doc-back">← 返回列表</button></div><div class="sed-paper-panel"><div class="sed-panel-head"><div><h3>${esc(doc.title)}</h3><p>${esc(doc.kind||'')} · ${esc(doc.generated_at||'')}</p></div></div><div class="sed-panel-body"><div class="sed-md">${renderMd(doc.body)}</div></div></div></div>`;
}

async function renderDocuments(){
  const el=document.getElementById("documents");
  el.innerHTML='<section class="card"><p class="muted">加载报告...</p></section>';
  let data;try{data=await loadDocuments()}catch(err){el.innerHTML=`<section class="card"><p>${esc(err.message||"加载失败")}</p></section>`;return}
  const metrics=data.metrics||{total:0,this_week:0,by_kind:{}};
  let items=(data.documents||[]).slice();
  if(DOC_KIND_FILTER)items=items.filter(d=>d.kind===DOC_KIND_FILTER);
  if(DOC_QUERY){const q=DOC_QUERY.toLowerCase();items=items.filter(d=>(d.title||'').toLowerCase().includes(q)||(d.summary||'').toLowerCase().includes(q));}
  if(DOC_SORT==="oldest")items.reverse();
  const allKinds=Object.keys(metrics.by_kind||{}).sort();
  const kindBtnStyle=(active)=>`min-height:34px;padding:7px 13px;color:${active?'#fffdf8':'var(--sed-muted)'};background:${active?'var(--sed-moss)':'transparent'};border:0;border-radius:8px;cursor:pointer;font-size:12px;font-weight:650`;
  const subnav=[`<button style="${kindBtnStyle(DOC_KIND_FILTER===null)}" data-action="doc-kind" data-doc-kind="">全部 ${metrics.total}</button>`].concat(
    allKinds.map(k=>`<button style="${kindBtnStyle(DOC_KIND_FILTER===k)}" data-action="doc-kind" data-doc-kind="${esc(k)}">${esc(k)} ${metrics.by_kind[k]||0}</button>`)
  ).join("");
  const hero=`<div class="sed-hero"><div class="sed-hero-copy"><div class="sed-eyebrow">沉淀报告</div><h2>${esc(metrics.total)} 份脱敏报告</h2><p>review/inbox 下的迭代周报 / deep-analysis / 提案历史。点击卡片展开全文(md 渲染);这是阅读视图,不做决定——决定类用 Review Inbox / 偏好审阅。</p><div style="margin-top:14px;display:inline-flex;gap:4px;padding:4px;background:rgba(255,253,248,.68);border:1px solid var(--sed-line);border-radius:11px">${subnav}</div></div><div class="sed-hero-metrics"><div class="sed-metric"><div class="num">${esc(metrics.total)}</div><div class="lbl">报告总数</div><div class="hint">review/inbox</div></div><div class="sed-metric"><div class="num">${esc(metrics.this_week)}</div><div class="lbl">本周新增</div><div class="hint">近 7 天</div></div><div class="sed-metric"><div class="num">${esc(allKinds.length)}</div><div class="lbl">类别</div><div class="hint">${esc(allKinds.join(' / ')||'-')}</div></div></div></div>`;
  const toolbar=`<div class="sed-toolbar"><input placeholder="搜索标题或摘要..." value="${esc(DOC_QUERY)}" data-doc-search><span class="sed-count">显示 ${items.length} / ${metrics.total}</span><button style="min-height:30px;padding:4px 10px;font-size:12px;border:1px solid var(--sed-line);background:var(--sed-surface);color:var(--sed-ink);border-radius:8px;cursor:pointer" data-action="doc-sort">${DOC_SORT==="newest"?"最新优先":"最早优先"}</button></div>`;
  const cards=items.map(d=>`<article class="sed-lib-card" data-action="doc-open" data-doc-id="${esc(d.id)}"><div class="lc-score">${esc((d.kind||'').slice(0,3))}</div><div class="lc-body"><div class="lc-title">${esc(d.title)}</div><div class="lc-sum">${esc(d.summary||'(无摘要)')}</div><div class="lc-meta">${esc(d.generated_at||'')} · ${Math.round((d.body||'').length/1000)}k chars</div></div></article>`).join("");
  el.innerHTML=`<div class="sed">${hero}${toolbar}<div class="sed-lib-grid">${cards||'<div class="sed-empty">暂无报告。运行 python3 scripts/iteration_report.py 生成迭代周报。</div>'}</div></div>`;
  el.querySelector('[data-doc-search]')?.addEventListener('input',e=>{DOC_QUERY=e.target.value;renderDocuments();});
}
document.querySelectorAll(".sidebar-nav button").forEach(button=>button.addEventListener("click",()=>{document.querySelectorAll(".sidebar-nav button").forEach(item=>item.classList.toggle("active",item===button));document.querySelectorAll(".view").forEach(item=>item.classList.toggle("show",item.id===button.dataset.view));history.replaceState(null,"",`#${button.dataset.view}`)}));
document.querySelector("main").addEventListener("click",event=>{if(!(event.target instanceof Element))return;const el=event.target.closest("[data-action]");if(!el)return;const a=el.dataset.action;if(a==="proposal-decision")void decideProposal(el.dataset.proposalId||"",el.dataset.decision||"",el.dataset.revisionHash||"",el.dataset.artifactHash||"");if(a==="preference-decision")void decidePreference(el.dataset.candidateId||"",el.dataset.decision||"",el.dataset.revision||"");if(a==="doc-kind"){DOC_KIND_FILTER=el.dataset.docKind||null;void renderDocuments()}if(a==="doc-sort"){DOC_SORT=DOC_SORT==="newest"?"oldest":"newest";void renderDocuments()}if(a==="doc-open")showDocDetailById(el.dataset.docId);if(a==="doc-back")void renderDocuments()});
function renderAll(){document.getElementById("subtitle").textContent=`${DATA.skill.name} ${DATA.skill.version} · ${DATA.skill.mode}`;document.getElementById("generated").textContent=`生成于 ${DATA.generated_at}`;renderOverview();renderReview();renderScheduler();renderLogs();renderPreferences();renderDocuments()}
async function initialize(){if(SERVER_MODE)await authenticateServer();renderAll()}
void initialize().catch(error=>{document.getElementById("subtitle").textContent="认证失败";document.getElementById("generated").textContent="";const target=document.getElementById("overview");target.textContent=error.message||"无法加载面板";target.classList.add("card")});
</script></body></html>"""


def render_html(
    data: dict[str, Any],
    *,
    server_mode: bool = False,
    nonce: str = "",
    script_nonce: str = "",
) -> str:
    if script_nonce and not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", script_nonce):
        raise ValueError("invalid CSP script nonce")
    panel_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    panel_json = panel_json.replace("<", "\\u003c").replace("</", "<\\/")
    request_nonce = json.dumps(nonce, ensure_ascii=True).replace("<", "\\u003c")
    script_nonce_attr = f' nonce="{script_nonce}"' if script_nonce else ""
    template = (
        HTML_TEMPLATE.replace("__SCRIPT_NONCE_ATTR__", script_nonce_attr)
        .replace("__SERVER_MODE__", "true" if server_mode else "false")
        .replace("__REQUEST_NONCE__", request_nonce)
    )
    return template.replace("__PANEL_DATA__", panel_json)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(path)
        os.chmod(path, 0o600)
    finally:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the Self Evolve read-only panel snapshot.")
    parser.add_argument("--output", type=Path, default=PANEL_ROOT / "self-evolve-panel.html")
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        assert_runtime_ready()
        output = assert_external_write_path(args.output, label="panel_output")
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    panel_root = PANEL_ROOT.expanduser().resolve()
    if output != panel_root and panel_root not in output.parents:
        print(json.dumps({"ok": False, "error": "output must be inside panel root"}, ensure_ascii=False))
        return 2
    data = build_panel_data(max(10, min(args.limit, 500)))
    atomic_write(output, render_html(data))
    if args.open:
        webbrowser.open(output.as_uri())
    result = {"ok": True, "output": str(output), "proposals": len(data["proposals"])}
    print(json.dumps(result, ensure_ascii=False) if args.json else f"Self Evolve panel rendered: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
