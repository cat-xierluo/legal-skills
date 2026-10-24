#!/usr/bin/env python3
"""Prepare current evidence for a scheduled Agent's opportunity review."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lockutil import write_lock
import daily_loop
from project_context import (capability_hints, compare_snapshot_commit, default_roots, digest, discover,
                             match_terms, terms_for, scope_conflicts,
                             shared_evidence_revision, shared_repo_revision)
from star_query import emit, envelope, parse_dt
from star_tracker import StarTracker

REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def now_utc():
    return datetime.now(timezone.utc)


def read_json(path, default=None):
    if not path.exists():
        return default
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path.name}")
    return value


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, path)
    except BaseException:
        # Only the private temp file created above may be removed; the target is
        # replaced atomically and is never deleted by this failure cleanup.
        Path(name).unlink(missing_ok=True)
        raise


def github_get(endpoint, paginate=False, accept="application/vnd.github+json"):
    command = ["gh", "api", "--method", "GET", "-H", f"Accept: {accept}", endpoint]
    if paginate:
        command += ["--paginate", "--slurp"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    if result.returncode:
        # Do not echo credential/proxy diagnostics into an analysis package.
        raise RuntimeError(f"GitHub GET failed: {endpoint} (exit {result.returncode})")
    if len(result.stdout) > 32_000_000:
        raise ValueError("GitHub response exceeds 32 MB budget")
    return json.loads(result.stdout)


class BudgetExceeded(RuntimeError):
    """The run's GitHub GET budget is exhausted."""


def budgeted_get(budget, endpoint, kind="get", **kwargs):
    """Count one GET against the run budget, then perform it."""
    if budget is not None and not budget.take(kind):
        raise BudgetExceeded(endpoint)
    return github_get(endpoint, **kwargs)


class RequestBudget:
    """Hard ceiling on GitHub GET calls issued in one run."""

    def __init__(self, limit):
        self.limit = limit
        self.used = 0
        self.by_kind = {}

    def take(self, kind, cost=1):
        if self.limit is not None and self.used + cost > self.limit:
            # Record the attempt so a saturated budget stays visible.
            self.by_kind[kind + "_denied"] = self.by_kind.get(kind + "_denied", 0) + 1
            return False
        self.used += cost
        self.by_kind[kind] = self.by_kind.get(kind, 0) + cost
        return True

    def report(self):
        return {"limit": self.limit, "used": self.used, "by_kind": dict(self.by_kind),
                "exhausted": self.limit is not None and self.used >= self.limit}


def refresh_snapshot(data_dir, old, request_budget=None):
    login = budgeted_get(request_budget, "user", kind="refresh").get("login")
    if not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9-]+", login):
        raise ValueError("Cannot identify authenticated GitHub account")
    old_account = (old or {}).get("snapshot_meta", {}).get("account_id")
    if old_account and old_account.lower() != login.lower():
        raise ValueError("Snapshot belongs to another account; use a separate --data-dir")
    pages, page_number = [], 1
    while True:
        endpoint = (f"user/starred?per_page=100&sort=created&direction=desc"
                    f"&page={page_number}")
        page = budgeted_get(request_budget, endpoint, kind="refresh",
                            accept="application/vnd.github.star+json")
        if not isinstance(page, list) or len(page) > 100:
            raise ValueError("Invalid starred page response; previous snapshot retained")
        pages.append(page)
        if len(page) < 100:
            break
        page_number += 1
    repos, ids = [], set()
    for page in pages:
        for entry in page:
            repo = entry.get("repo") if isinstance(entry, dict) else None
            if not isinstance(repo, dict) or not isinstance(repo.get("id"), int) or not REPO_PATTERN.fullmatch(repo.get("full_name", "")):
                raise ValueError("Malformed starred row; previous snapshot retained")
            if repo["id"] in ids:
                raise ValueError("Duplicate repository across pages; retry stable pagination")
            ids.add(repo["id"])
            repos.append({**repo, "starred_at": entry.get("starred_at")})
    tracker = StarTracker.__new__(StarTracker)
    tracker.CACHE_DIR = data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    tracker.save_latest(repos, fetch_meta={
        "account_id": login, "complete": True, "failed_pages": [],
        "fetched_at": now_utc().isoformat(), "starred_at_available": True,
        "limit_truncated": False,
    }, base_timestamp=(old or {}).get("timestamp"))
    return read_json(data_dir / "original_latest.json")


def repo_revision(repo):
    if repo.get("_repo_revision"):
        return repo["_repo_revision"]
    return shared_repo_revision(repo)


def feedback_index(data_dir):
    result, warnings = {}, []
    for path in sorted((data_dir / "feedback").glob("*.json")):
        try:
            card = read_json(path)
            card["_file"] = path.name
            project_id = card.get("target", {}).get("project_id")
            repo = card.get("signal", {}).get("repo")
            repo_id = card.get("signal", {}).get("repo_id")
            if not project_id or not repo:
                continue
            target = card.get("target") or {}
            capability = target.get("capability_key") or target.get("decision_capability_key")
            scope = card.get("scope") or target.get("scope") or (
                "direction" if capability else "legacy")
            for repo_key in ([f"id:{repo_id}", repo] if isinstance(repo_id, int) else [repo]):
                # Legacy 1.0 cards remain repository-wide for compatibility.
                # New explicit directions and repository-wide decisions expose
                # stable lookup keys without rewriting old files.
                if scope == "direction" and capability:
                    keys = [(scope, capability)]
                elif scope in {"repo", "component", "legacy"}:
                    keys = [(scope, None)]
                else:
                    keys = []
                for decision_scope, capability_key in keys:
                    result.setdefault((project_id, repo_key, decision_scope, capability_key), []).append(card)
        except (OSError, ValueError, AttributeError):
            warnings.append(f"Unreadable feedback: {path.name}")
    return result, warnings


def prior_for_direction(prior, capability_key):
    if not prior:
        return []
    directions = [card for card in prior
                  if ((card.get("scope") or (card.get("target") or {}).get("scope")) == "direction")
                  and ((card.get("target") or {}).get("capability_key")
                       or (card.get("target") or {}).get("decision_capability_key")) == capability_key]
    broad = [card for card in prior
             if ((card.get("scope") or (card.get("target") or {}).get("scope")) in {"repo", "legacy", "component"})
             or not ((card.get("scope") or (card.get("target") or {}).get("scope")) == "direction")]
    return directions + broad


def suppression(profile, repo, prior, now, requested_direction=None):
    if not prior:
        return None
    # A direction decision wins over broad compatibility only when it is newer
    # than the latest broad card. This preserves an explicit later repository
    # rejection while avoiding the old "latest card erases scope" behavior.
    requested_scope = requested_direction
    direction_cards = [card for card in prior
                       if ((card.get("scope") or (card.get("target") or {}).get("scope")) == "direction")
                       and ((card.get("target") or {}).get("capability_key")
                            or (card.get("target") or {}).get("decision_capability_key")) == requested_scope]
    broad_cards = [card for card in prior if card not in direction_cards]
    latest_direction = max(direction_cards, key=lambda c: c.get("_recorded_at", ""), default=None)
    latest_broad = max(broad_cards, key=lambda c: c.get("_recorded_at", ""), default=None)
    card = latest_direction
    if latest_broad and (not latest_direction
                         or latest_broad.get("_recorded_at", "") >= latest_direction.get("_recorded_at", "")):
        card = latest_broad
    if card is None:
        return None
    decision = card.get("decision") or {}
    status = decision.get("status")
    if status not in {"rejected", "deferred", "researched", "experiment_proposed", "tested", "adopted"}:
        return None
    recorded = parse_dt(card.get("_recorded_at"))
    due = parse_dt(decision.get("review_after"))
    if status == "deferred":
        due = due or (recorded + timedelta(days=1) if recorded else now)
        if due <= now:
            return None
    target = card.get("target") or {}
    signal = card.get("signal") or {}
    old_target = target.get("target_revision")
    old_repo = signal.get("repo_revision")
    old_evidence = signal.get("evidence_revision")
    current_evidence = repo.get("_evidence_revision")
    if repo.get("_evidence_unavailable") or (old_evidence and not current_evidence):
        return None
    if old_evidence and current_evidence and old_evidence != current_evidence:
        return None
    changed_at = parse_dt(repo.get("_evidence_changed_at"))
    if not old_evidence and changed_at and recorded and changed_at > recorded:
        return None
    if old_target and old_target != profile["target_revision"]:
        return None
    if old_repo and old_repo != repo_revision(repo):
        return None
    if recorded and not old_target:
        changed = parse_dt(profile["activity"].get("latest_at"))
        if changed and changed > recorded:
            return None
    if recorded and not old_repo:
        pushed = parse_dt(repo.get("pushed_at"))
        if pushed and pushed > recorded:
            return None
    return {"decision": status, "recorded_at": card.get("_recorded_at"),
            "review_after": due.isoformat() if due else None,
            "decision_scope": (card.get("scope") or target.get("scope")
                               or ("direction" if target.get("capability_key")
                                   or target.get("decision_capability_key") else "legacy")),
            "capability_key": target.get("capability_key") or target.get("decision_capability_key"),
            "binding": "revision" if old_target and old_repo else "legacy-time-fallback"}


def valid_recent(date, cutoff, now):
    parsed = parse_dt(date)
    return parsed is not None and cutoff <= parsed <= now


FOCUS_FILE = "repository-profiles/focus.json"
QUEUE_FILE = "auto-opportunities/review-queue.json"
QUEUE_SCHEMA = "review-queue/1.0"


def focus_repositories(data_dir, warnings=None):
    """Read the focused-repository list shared with the profile command."""
    try:
        value = read_json(data_dir / FOCUS_FILE, {"repositories": {}})
        if not isinstance(value.get("repositories"), dict):
            raise ValueError("Expected repositories object")
        if any(not REPO_PATTERN.fullmatch(name) or not isinstance(row, dict)
               for name, row in value["repositories"].items()):
            raise ValueError("Invalid focus entry")
        return value["repositories"]
    except (OSError, ValueError, TypeError):
        if warnings is not None:
            warnings.append("Unreadable focus state; ordinary Star discovery continues")
        return {}


def load_review_queue(data_dir, warnings):
    path = data_dir / QUEUE_FILE
    if path.exists() and not path.is_file():
        raise ValueError("Review queue path is not a file")
    try:
        value = read_json(path, {"schema_version": QUEUE_SCHEMA, "entries": {},
                                 "cursor": {"round_seq": 0, "last_round_at": None}}) or {
            "schema_version": QUEUE_SCHEMA, "entries": {}, "cursor": {"round_seq": 0, "last_round_at": None}}
        if value.get("schema_version") != QUEUE_SCHEMA or not isinstance(value.get("entries"), dict):
            raise ValueError("Invalid review queue")
        value["cursor"] = value.get("cursor") or {}
        return value
    except (OSError, ValueError, TypeError) as exc:
        if path.exists():
            backup = path.with_name(f"{path.name}.corrupt-{now_utc().strftime('%Y%m%dT%H%M%S.%fZ')}")
            try:
                backup.write_bytes(path.read_bytes())
            except OSError:
                pass
        warning = f"Unreadable review queue retained at {path}; queue unavailable and not cleared: {type(exc).__name__}"
        warnings.append(warning)
        return {"schema_version": QUEUE_SCHEMA, "entries": {}, "cursor": {},
                "state": "degraded", "source_path": str(path)}


def judged_decision(entry, feedback, now):
    """判断队列条目是否已有有效反馈卡（复用 suppression 判定，不另立一套）。

    返回 None 表示本条目尚无有效反馈卡；否则返回判定详情（含 judged_ref）。
    """
    project_id, repo_id, repo_name, capability = (entry.get("project_id"),
                                                   entry.get("repo_id"), entry.get("repo"),
                                                   entry.get("capability_key"))
    decisions = []
    if repo_id is not None:
        decisions += feedback.get((project_id, f"id:{repo_id}", "direction", capability), [])
        decisions += feedback.get((project_id, f"id:{repo_id}", "repo", None), [])
        decisions += feedback.get((project_id, f"id:{repo_id}", "legacy", None), [])
    decisions += feedback.get((project_id, repo_name, "direction", capability), [])
    decisions += feedback.get((project_id, repo_name, "repo", None), [])
    decisions += feedback.get((project_id, repo_name, "legacy", None), [])
    if not decisions:
        return None
    merged = prior_for_direction(list({digest(card): card for card in decisions}.values()), capability)
    state = suppression({"target_revision": entry.get("last_target_revision"),
                         "activity": {}},
                        {"id": repo_id, "full_name": repo_name,
                         "pushed_at": None, "description": None, "topics": None,
                         "_evidence_revision": entry.get("last_evidence_revision"),
                         "_repo_revision": entry.get("last_repo_revision")},
                        merged, now, requested_direction=capability)
    if not state:
        return None
    latest = max(merged, key=lambda card: card.get("_recorded_at", ""))
    return {"decision": state.get("decision"), "judged_ref": latest.get("_file"),
            "recorded_at": latest.get("_recorded_at"),
            "decision_scope": state.get("decision_scope"),
            "capability_key": state.get("capability_key")}


def judge_entries(entries, feedback, now):
    """把有有效反馈卡的队列条目更新为 judged；返回本轮变为 judged 的条目。

    没有反馈卡的条目保持原状态——不得因为"被展示过"就标成已处理。
    """
    newly = []
    for key, entry in entries.items():
        if not isinstance(entry, dict) or entry.get("state") == "stale":
            continue
        decision = judged_decision(entry, feedback, now)
        if not decision:
            continue
        previous = entry.get("state")
        entry["state"] = "judged"
        entry["judged_ref"] = decision.get("judged_ref")
        if previous != "judged":
            entry["judged_at"] = now.isoformat()
            newly.append({"candidate_key": key, "project_id": entry.get("project_id"),
                          "repo": entry.get("repo"), "repo_id": entry.get("repo_id"),
                          "capability_key": entry.get("capability_key"),
                          "decision": decision.get("decision"),
                          "judged_ref": decision.get("judged_ref")})
    return newly


def queue_backlog(entries):
    """未研判积压统计（pending / shown 都算还没写反馈卡）。"""
    pending = [entry for entry in entries.values()
               if isinstance(entry, dict) and entry.get("state") in {"pending", "shown"}]
    oldest = min((entry.get("first_seen_at", "") for entry in pending), default=None)
    by_project = {}
    for entry in pending:
        key = entry.get("project_id") or "unknown"
        by_project[key] = by_project.get(key, 0) + 1
    judged = [entry for entry in entries.values()
              if isinstance(entry, dict) and entry.get("state") == "judged"]
    return {"pending_total": len(pending),
            "shown_pending": sum(1 for entry in pending if entry.get("state") == "shown"),
            "judged_total": len(judged),
            "stale_total": sum(1 for entry in entries.values()
                               if isinstance(entry, dict) and entry.get("state") == "stale"),
            "oldest_pending_first_seen_at": oldest,
            "pending_by_project": dict(sorted(by_project.items()))}


def reconcile_queue(data_dir, now=None, since=None):
    """离线对账：重读 feedback/ 与 review-queue.json，把有反馈卡的条目置为 judged。

    零联网。返回 (result, exit_code)；队列损坏时显式降级且不写回。
    """
    now = now or now_utc()
    since = parse_dt(since) if isinstance(since, str) else since
    warnings = []
    queue = load_review_queue(data_dir, warnings)
    degraded = queue.get("state") == "degraded"
    feedback, feedback_warnings = feedback_index(data_dir)
    warnings += feedback_warnings
    entries = queue.get("entries") or {}
    newly = []
    changed = False
    if not degraded:
        before = {key: entry.get("state") for key, entry in entries.items()
                  if isinstance(entry, dict)}
        newly = judge_entries(entries, feedback, now)
        after = {key: entry.get("state") for key, entry in entries.items()
                 if isinstance(entry, dict)}
        changed = before != after
        if changed:
            value = {**queue, "entries": entries,
                     "last_reconciled_at": now.isoformat()}
            path = data_dir / QUEUE_FILE
            path.parent.mkdir(parents=True, exist_ok=True)
            with write_lock(path.parent):
                atomic_json(path, value)
    backlog = queue_backlog(entries)
    new_pending = 0
    new_unjudged = 0
    if since is not None:
        for entry in entries.values():
            if not isinstance(entry, dict) or entry.get("state") not in {"pending", "shown"}:
                continue
            first_seen = parse_dt(entry.get("first_seen_at"))
            if first_seen is not None and first_seen >= since:
                new_pending += 1
            last_shown = parse_dt(entry.get("last_shown_at"))
            if ((first_seen is not None and first_seen >= since)
                    or (last_shown is not None and last_shown >= since)):
                new_unjudged += 1
    backlog["new_pending_since"] = new_pending
    backlog["new_unjudged_since"] = new_unjudged
    result = {
        "schema_version": "reconcile/1.0",
        "generated_at": now.isoformat(),
        "data_dir": str(data_dir),
        "queue_state": queue.get("state", "healthy"),
        "degraded": degraded,
        "newly_judged": newly,
        "newly_judged_count": len(newly),
        "queue_changed": changed,
        "new_pending": new_pending,
        "new_unjudged": new_unjudged,
        "backlog": backlog,
        "entries": entries,
        "include_entries": True,
        "feedback_cards": sum(len(cards) for cards in feedback.values()),
        "warnings": warnings,
        "errors": ([f"研判队列不可读，已保留原文件且未写回：{queue.get('source_path')}"]
                   if degraded else []),
    }
    return result, (1 if degraded else 0)


def latest_run_context(data_dir):
    """读取最近一次准备阶段的运行包（离线），提取候选数与请求预算用量。"""
    path = daily_loop.latest_run_file(data_dir)
    context = {"run_path": str(path) if path else None, "run_found": bool(path),
               "generated_at": None, "candidates": 0, "request_budget": None,
               "status": None, "warnings": []}
    if not path:
        context["warnings"].append("没有找到准备阶段运行包——本轮候选数按 0 计")
        return context
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        context["warnings"].append(f"运行包不可读（{type(exc).__name__}）——本轮候选数按 0 计")
        return context
    if not isinstance(value, dict):
        context["warnings"].append("运行包格式异常——本轮候选数按 0 计")
        return context
    items = value.get("items")
    context["generated_at"] = value.get("generated_at")
    context["candidates"] = len(items) if isinstance(items, list) else 0
    context["status"] = value.get("status")
    coverage = value.get("coverage") or {}
    watch = coverage.get("watch_coverage") or {}
    if isinstance(watch.get("request_budget"), dict):
        context["request_budget"] = watch["request_budget"]
    return context


def cards_written_since(data_dir, since_iso=None):
    """统计本轮（准备阶段之后）写入的反馈卡数量。"""
    since = parse_dt(since_iso) if since_iso else None
    written = []
    if since is None:
        # 没有准备阶段运行包 → 没有"本轮"边界。历史卡片不能算作本轮写入。
        return written
    directory = Path(data_dir) / "feedback"
    if not directory.is_dir():
        return written
    for path in sorted(directory.glob("*.json")):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(card, dict):
            continue
        recorded = parse_dt(card.get("_recorded_at"))
        if since and (recorded is None or recorded < since):
            continue
        written.append({"file": path.name,
                        "decision": (card.get("decision") or {}).get("status"),
                        "repo": (card.get("signal") or {}).get("repo"),
                        "project_id": (card.get("target") or {}).get("project_id"),
                        "recorded_at": card.get("_recorded_at")})
    return written


def build_receipt(data_dir, outcome=None, errors=None, notify=None,
                  requested=None, now=None):
    """汇总一次每日闭环的回执事实（离线）。

    outcome:
    - "judged"：本轮有反馈卡写入或队列条目变为 judged。
    - "silent"：必须带正向证据（候选数=0、队列无新增待研判、无卡片写入）。
    - "failed"：Agent 崩溃/未研判/错误——不得记成静默。
    - None（自动判定）：按上面的事实推导。

    没有准备阶段运行包时，"本轮写入的卡片"无法界定（历史卡片不算本轮），
    但 reconcile 真实把条目判为 judged 仍是 judged 结局，缺运行包记为显式警告。
    """
    now = now or now_utc()
    run = latest_run_context(data_dir)
    run_at = parse_dt(run.get("generated_at"))
    reconcile, reconcile_code = reconcile_queue(data_dir, now=now, since=run_at)
    written = cards_written_since(data_dir, run.get("generated_at"))
    backlog = reconcile.get("backlog") or {}
    new_pending = reconcile.get("new_pending", 0)
    new_unjudged = reconcile.get("new_unjudged", 0)
    shown_pending = backlog.get("shown_pending", 0)
    facts = {
        "candidates": run.get("candidates", 0),
        "cards_written": len(written),
        "newly_judged": reconcile.get("newly_judged_count", 0),
        "pending_total": backlog.get("pending_total", 0),
        "new_pending": new_pending,
        "new_unjudged": new_unjudged,
        "shown_pending": shown_pending,
        "backlog_pending_total": backlog.get("pending_total", 0),
        "run_found": run.get("run_found"),
        "queue_state": reconcile.get("queue_state"),
    }
    actionable = [card for card in written
                  if card.get("decision") in {"tested", "adopted", "experiment_proposed"}]
    # 本轮写出的卡片中，已有对应队列条目被判为 judged 的数量。
    judged_cards = 0
    for card in written:
        for key, entry in (reconcile.get("entries") or {}).items():
            if not isinstance(entry, dict) or entry.get("state") != "judged":
                continue
            if (entry.get("project_id") == card.get("project_id")
                    and entry.get("repo") == card.get("repo")):
                judged_cards += 1
                break
    failures = list(errors or [])
    if reconcile_code:
        failures.extend(reconcile.get("errors") or [])
    resolved = outcome
    if resolved is None:
        if failures:
            resolved = "failed"
        elif facts["cards_written"] or facts["newly_judged"]:
            resolved = "judged"
        elif (facts["run_found"] and facts["candidates"] == 0
              and facts["new_unjudged"] == 0 and facts["cards_written"] == 0):
            resolved = "silent"
        else:
            resolved = "failed"
            if not facts["run_found"]:
                failures.append("没有准备阶段运行包，无法取得候选数=0 的正向证据"
                                "——不得记为静默")
            elif facts["candidates"] or facts["new_unjudged"]:
                failures.append("本轮存在候选或新增未研判条目，却没有写出任何反馈卡"
                                "——研判未完成，不得记为静默")
            else:
                failures.append("本轮有反馈卡写入但无法完成对账——不得记为静默")
    if resolved == "silent":
        evidence = {
            "candidates": facts["candidates"],
            "queue_new_pending": facts["new_pending"],
            "queue_new_unjudged": facts["new_unjudged"],
            "backlog_pending_total": facts["backlog_pending_total"],
            "cards_written": facts["cards_written"],
            "statement": "本轮候选数=0 且队列无新增未研判条目 且无卡片写入",
            "note": "历史积压只披露不阻断——相同未恢复问题不每天重报",
        }
        if (not facts["run_found"] or facts["candidates"] != 0
                or facts["new_unjudged"] != 0 or facts["cards_written"] != 0):
            return {"ok": False,
                    "error": "silent 需要正向证据，但本轮事实不支持："
                             f"run_found={facts['run_found']}, "
                             f"candidates={facts['candidates']}, "
                             f"new_unjudged={facts['new_unjudged']}, "
                             f"backlog_pending_total={facts['backlog_pending_total']}, "
                             f"cards_written={facts['cards_written']}",
                    "facts": facts}, 1
    else:
        evidence = {
            "cards_written": facts["cards_written"],
            "newly_judged": facts["newly_judged"],
            "actionable_cards": len(actionable),
            "statement": "本轮写出反馈卡并完成对账" if resolved == "judged"
                         else "本轮出现失败或未完成——不作为静默处理",
        }
    if notify is None:
        if resolved == "failed":
            notify = {"recommended": True, "reason": "本轮失败或研判未完成——需要人工介入"}
        elif resolved == "judged" and actionable:
            notify = {"recommended": True,
                      "reason": f"本轮有 {len(actionable)} 张可行动的机会卡（tested/adopted/experiment_proposed）"}
        elif resolved == "judged":
            notify = {"recommended": False, "reason": "本轮只有拒绝/暂缓类判断，无需打扰用户"}
        else:
            notify = {"recommended": False, "reason": "无变化静默"}
    receipt = {
        "schema_version": daily_loop.RECEIPT_SCHEMA,
        "generated_at": now.isoformat(),
        "outcome": resolved,
        "facts": facts,
        "evidence": evidence,
        "request_budget": run.get("request_budget"),
        "candidates": facts["candidates"],
        "cards_written": facts["cards_written"],
        "cards": written,
        "reconcile": {"newly_judged_count": reconcile.get("newly_judged_count"),
                      "newly_judged": reconcile.get("newly_judged"),
                      "judged_total": backlog.get("judged_total", 0),
                      "pending_total": backlog.get("pending_total", 0),
                      "new_pending": new_pending,
                      "cards_now_judged": judged_cards,
                      "backlog": backlog,
                      "queue_state": reconcile.get("queue_state"),
                      "degraded": reconcile.get("degraded")},
        "notification": notify,
        "errors": failures,
        "warnings": list(run.get("warnings") or []) + list(reconcile.get("warnings") or []),
        "requested_outcome": requested,
    }
    return {"ok": True, "receipt": receipt}, (1 if resolved == "failed" else 0)


def update_review_queue(data_dir, old, selected, all_candidates, snapshot, feedback, now):
    current_ids = {row.get("id") for row in snapshot.get("repos", [])}
    entries = {}
    for key, entry in (old.get("entries") or {}).items():
        if not isinstance(entry, dict):
            continue
        repo_id = entry.get("repo_id")
        if repo_id is not None and repo_id not in current_ids:
            entry = {**entry, "state": "stale",
                     "note": "Repository absent from the current snapshot; retained for audit"}
        entries[key] = entry
    for candidate in all_candidates:
        key = candidate["candidate_key"]
        old_entry = entries.get(key) or {}
        entry = {
            "candidate_key": key,
            "project_id": candidate["project_id"], "repo_id": candidate.get("repo_id"),
            "repo": candidate["repo"], "capability_key": candidate["capability"]["key"],
            "capability_label": candidate["capability"].get("label"),
            "scope": candidate["decision_scope"], "state": "pending",
            "first_seen_at": old_entry.get("first_seen_at") or now.isoformat(),
            "last_shown_at": old_entry.get("last_shown_at"),
            "shown_count": old_entry.get("shown_count", 0),
            "last_shown_project": old_entry.get("last_shown_project"),
            "last_evidence_revision": candidate.get("evidence_revision"),
            "last_target_revision": candidate.get("target_revision"),
            "last_repo_revision": candidate.get("repo_revision"),
        }
        entries[key] = entry
    selected_keys = {row["candidate_key"] for row in selected}
    for candidate in selected:
        entry = entries[candidate["candidate_key"]]
        entry["state"] = "shown"
        entry["last_shown_at"] = now.isoformat()
        entry["shown_count"] = entry.get("shown_count", 0) + 1
        entry["last_shown_project"] = candidate["project_id"]
    # Feedback remains the sole source of judged state. Do not mark shown items
    # complete merely because an Agent looked at them.
    judge_entries(entries, feedback, now)
    value = {"schema_version": QUEUE_SCHEMA, "entries": entries,
             "cursor": {"round_seq": int((old.get("cursor") or {}).get("round_seq", 0)) + 1,
                        "last_round_at": now.isoformat()},
             "last_run_selected_keys": sorted(selected_keys)}
    path = data_dir / QUEUE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with write_lock(path.parent):
        atomic_json(path, value)
    return value


OBSERVED_FIELDS = ("head", "release", "readme")

EVIDENCE_SUMMARY_LIMIT = 1200
RELEASE_RECALL_LIMIT = 2000


def evidence_summary(record, source="none", fetched_at=None, limit=EVIDENCE_SUMMARY_LIMIT):
    """A bounded, Agent-readable digest of one upstream evidence record.

    The Agent reviews a candidate from this digest instead of going back to
    GitHub. Every section is truncated so a single long README or Release
    body cannot crowd out the other observations.
    """
    record = record or {}
    readme_text = str((record.get("readme") or {}).get("text") or "")
    release = record.get("release") or {}
    release_body = str(release.get("body") or "")
    commit_lines = []
    for row in (record.get("commits") or [])[:5]:
        row = row or {}
        message = str(row.get("message") or "").strip()
        if message:
            commit_lines.append(f"- {(row.get('sha') or '')[:12]} {message}")
    commit_text = "\n".join(commit_lines)
    return {
        "source": source,
        "fetched_at": fetched_at or record.get("fetched_at"),
        "readme": readme_text[:limit],
        "readme_truncated": len(readme_text) > limit,
        "readme_blob_sha": (record.get("readme") or {}).get("blob_sha"),
        "release": release_body[:limit],
        "release_truncated": len(release_body) > limit,
        "release_tag": release.get("tag"),
        "release_url": release.get("url"),
        "release_published_at": release.get("published_at"),
        "commits": commit_text[:limit],
        "commits_truncated": len(commit_text) > limit,
        "head_sha": record.get("head_sha"),
        "observed": record.get("observed"),
        "probe": record.get("probe"),
        "scope": ("README text, the latest Release body and at most five commit subjects; "
                  "not a source diff and not proof of value"),
    }


EVIDENCE_RANK_THIS_RUN_DEEP = 4
EVIDENCE_RANK_THIS_RUN_CHEAP = 3
EVIDENCE_RANK_THIS_RUN_PARTIAL = 2
EVIDENCE_RANK_CACHE = 1
EVIDENCE_RANK_NONE = 0


def evidence_rank(status, source, probe=None):
    """The queue ordering dimension of one candidate's evidence.

    Evidence fetched in this run outranks a cache hit, which outranks a
    candidate with no evidence at all. A cheap probe ranks below a deep
    fetch of the same run because it only observed the Release.
    """
    if source == "this_run":
        if status == "complete":
            return (EVIDENCE_RANK_THIS_RUN_CHEAP if probe == "cheap"
                    else EVIDENCE_RANK_THIS_RUN_DEEP)
        if status == "partial":
            return EVIDENCE_RANK_THIS_RUN_PARTIAL
        return EVIDENCE_RANK_NONE
    if status == "cached":
        return EVIDENCE_RANK_CACHE
    return EVIDENCE_RANK_NONE


def candidate_evidence_fields(repo):
    """The evidence a candidate exposes to the reviewing Agent.

    The status is never a hard-coded "not_fetched": it reflects the evidence
    actually available for this repository. The summary carries the bounded
    README, Release and commit text so the Agent can judge the candidate
    without going back to GitHub.
    """
    record = repo.get("_evidence_record")
    source = repo.get("_evidence_source") or "none"
    status = repo.get("_evidence_status") or "not_fetched"
    if not record:
        return {"status": "not_fetched", "source": "none",
                "rank": EVIDENCE_RANK_NONE, "summary": None}
    summary = evidence_summary(record, source)
    fallback_note = repo.get("_evidence_fallback_note")
    if fallback_note:
        summary["fallback_note"] = fallback_note
    return {"status": status, "source": source,
            "rank": evidence_rank(status, source, record.get("probe")),
            "summary": summary}


def observed_fields(record):
    """Which upstream fields a stored evidence record actually observed.

    A field that was never observed is unknown, not "observed as empty". Cheap
    probes only observe the Release, so their baseline cannot answer whether
    HEAD or README changed.
    """
    record = record or {}
    if isinstance(record.get("observed"), dict):
        return {field: bool(record["observed"].get(field)) for field in OBSERVED_FIELDS}
    # Legacy caches without an explicit flag: presence of the field means it
    # was observed. A missing README blob or HEAD was never observed.
    return {"head": record.get("head_sha") is not None,
            "release": "release" in record,
            "readme": bool((record.get("readme") or {}).get("blob_sha"))}


def field_value(record, field):
    if field == "head":
        return (record or {}).get("head_sha")
    if field == "release":
        return (record or {}).get("release")
    return ((record or {}).get("readme") or {}).get("blob_sha")


def compare_observed(current, prior, current_observed):
    """Compare only fields both sides observed; unknown stays None."""
    prior_seen = observed_fields(prior)
    result = {}
    for field in OBSERVED_FIELDS:
        if prior_seen[field] and current_observed.get(field):
            result[field + "_changed"] = field_value(current, field) != field_value(prior, field)
        else:
            result[field + "_changed"] = None
    return result


def any_change(changed):
    return any(value is True for value in changed.values())


def evidence_delta(name, current, prior):
    complete = bool(current and current.get("status") == "complete")
    baseline = bool(prior and prior.get("status") == "complete")
    delta = {"repo": name, "baseline_available": baseline,
             "evidence_status": current.get("status") if current else "not_fetched",
             "changed": None, "new_commits": [],
             "commit_scope": "At most five messages; unobserved history is not inferred"}
    if complete and baseline:
        delta["changed"] = compare_observed(current, prior, observed_fields(current))
        if delta["changed"]["head_changed"]:
            old = {row.get("sha") for row in prior.get("commits", [])}
            old.add(prior.get("head_sha"))
            delta["new_commits"] = [
                {"sha": row.get("sha"), "message": row.get("message")}
                for row in current.get("commits", [])
                if row.get("sha") and row["sha"] not in old][:5]
    if complete:
        delta["evidence_revision"] = evidence_revision(current)
        delta["release"] = current.get("release")
    return delta


def prepare(snapshot, profiles, feedback, now, limit=12, per_project=2,
            recent_days=14, update_days=7, show_suppressed=False, focused=None,
            queue=None, queue_now=None):
    focused = focused or {}
    queue_now = queue_now or now
    candidates, suppressed = [], []
    indexed_repos = [{**repo, "_search_terms": terms_for(" ".join([
        repo.get("full_name") or "", repo.get("description") or "",
        repo.get("description_zh") or "", " ".join(repo.get("topics") or []),
        repo.get("_evidence_text") or "",
        repo.get("_release_text") or "",
    ]))} for repo in snapshot.get("repos", [])]
    for profile in profiles:
        for repo in indexed_repos:
            name = repo.get("full_name", "")
            if not REPO_PATTERN.fullmatch(name):
                continue
            hints = [hint for hint in repo.get("_capability_hints", [])
                     if set(hint.get("concepts", [])) & set(profile.get("search_terms", []))]
            hits = match_terms(profile, repo)
            # Capability hints form an independent, anchored recall channel.
            # They can surface a component when a new Release capability is not
            # present in stale README or repository metadata.
            if not hits and not hints:
                continue
            primary = match_terms({"search_terms": profile.get("primary_terms", profile["search_terms"])}, repo)
            if not primary and not hints:
                continue
            if not hits:
                hits = sorted({concept for hint in hints for concept in hint.get("concepts", [])})
            if not primary:
                primary = sorted({concept for hint in hints for concept in hint.get("concepts", [])})
            reasons = []
            if valid_recent(repo.get("starred_at"), now - timedelta(days=recent_days), now):
                reasons.append("recent_star")
            if valid_recent(repo.get("pushed_at"), now - timedelta(days=update_days), now):
                reasons.append("upstream_activity")
            if name in focused:
                reasons.append("focused_watch")
            repo_feedback = []
            if repo.get("id") is not None:
                repo_id_key = f"id:{repo['id']}"
                for decision_scope in ("direction", "repo", "legacy", "component"):
                    repo_feedback += feedback.get((profile["project_id"], repo_id_key,
                                                   decision_scope, None), [])
                    if decision_scope == "direction":
                        # Direction values are collected dynamically below from
                        # capability hints; broad decisions come first.
                        continue
            for decision_scope in ("direction", "repo", "legacy", "component"):
                repo_feedback += feedback.get((profile["project_id"], name,
                                               decision_scope, None), [])
            repo_feedback = list({digest(card): card for card in repo_feedback}.values())
            conflicts = scope_conflicts(profile, repo["_search_terms"])
            capability_rows = hints or [{"capability_key": None, "capability_label": None,
                                         "concepts": [], "source": "collection",
                                         "anchor": None, "text": None}]
            for hint in capability_rows:
                capability_key = hint.get("capability_key")
                if capability_key:
                    if repo.get("id") is not None:
                        prior = (feedback.get((profile["project_id"], f"id:{repo['id']}",
                                               "direction", capability_key), [])
                                 + feedback.get((profile["project_id"], f"id:{repo['id']}",
                                                 "repo", None), [])
                                 + feedback.get((profile["project_id"], f"id:{repo['id']}",
                                                 "legacy", None), []))
                    else:
                        prior = []
                    prior += (feedback.get((profile["project_id"], name,
                                            "direction", capability_key), [])
                              + feedback.get((profile["project_id"], name, "repo", None), [])
                              + feedback.get((profile["project_id"], name, "legacy", None), []))
                else:
                    prior = repo_feedback
                state = suppression(profile, repo, prior, now,
                                    requested_direction=capability_key)
                if state and not show_suppressed:
                    suppressed.append({"project_id": profile["project_id"], "repo": name,
                                       "repo_id": repo.get("id"), "capability_key": capability_key,
                                       "watch_scope": "focus" if name in focused else "collection", **state})
                    continue
                candidate_key = digest([profile["project_id"], repo.get("id") or name,
                                        capability_key or "repository"])[:24]
                fingerprint = digest([profile["target_revision"], repo_revision(repo),
                                      repo.get("_evidence_revision"), profile["project_id"],
                                      capability_key])
                entry = ((queue or {}).get("entries") or {}).get(candidate_key, {})
                last_shown = parse_dt(entry.get("last_shown_at"))
                cooldown_due = (not last_shown or last_shown + timedelta(days=1) <= queue_now
                                or entry.get("last_target_revision") != profile["target_revision"]
                                or entry.get("last_evidence_revision") != repo.get("_evidence_revision")
                                or entry.get("state") == "stale")
                evidence = candidate_evidence_fields(repo)
                candidates.append({
                    "candidate_key": candidate_key,
                    "snapshot_revision": fingerprint[:24], "project_id": profile["project_id"],
                    "skill_path": profile.get("skill_path"),
                    "repo": name, "repo_id": repo.get("id"), "description": repo.get("description"),
                    "matched_terms": hits, "signals": reasons or ["existing_collection_match"],
                    "primary_matches": primary,
                    "capability": {"key": capability_key, "label": hint.get("capability_label"),
                                   "concepts": hint.get("concepts", []),
                                   "source": hint.get("source"), "anchor": hint.get("anchor"),
                                   "text": hint.get("text")},
                    "decision_scope": "direction" if capability_key else "repo",
                    "starred_at": repo.get("starred_at"), "pushed_at": repo.get("pushed_at"),
                    "repo_revision": repo_revision(repo), "target_revision": profile["target_revision"],
                    "evidence_revision": repo.get("_evidence_revision"),
                    "target_activity": profile["activity"], "suppression": state,
                    "queue_state": {"first_seen_at": entry.get("first_seen_at", queue_now.isoformat()),
                                    "last_shown_at": entry.get("last_shown_at"),
                                    "shown_count": entry.get("shown_count", 0),
                                    "cooldown_due": cooldown_due},
                    "evidence_status": evidence["status"],
                    "evidence_source": evidence["source"],
                    "evidence_rank": evidence["rank"],
                    "evidence_summary": evidence["summary"],
                    "evidence_fetched_at": evidence["summary"].get("fetched_at")
                    if evidence["summary"] else None,
                    "archived": bool(repo.get("is_archived")),
                    "watch_scope": "focus" if name in focused else "collection",
                    "focus_reason": focused.get(name, {}).get("reason"),
                    "prior_decisions": [{"status": (card.get("decision") or {}).get("status"),
                                         "reason": (card.get("decision") or {}).get("reason"),
                                         "gap": card.get("gap"), "experiment": card.get("experiment"),
                                         "recorded_at": card.get("_recorded_at")}
                                        for card in sorted(prior, key=lambda row: row.get("_recorded_at", ""),
                                                           reverse=True)[:3]],
                    "scope_conflicts": conflicts,
                    "scope_status": "conflicts_with_stated_scope" if conflicts else "no_stated_scope_conflict",
                })
    candidates.sort(key=lambda c: (
        -int(c["queue_state"]["cooldown_due"]),
        -c.get("evidence_rank", 0),
        -int("recent_star" in c["signals"]), -int("focused_watch" in c["signals"]),
        -min(c["target_activity"]["commits"], 10),
        -len(c["primary_matches"]), -len(c["matched_terms"]),
        -(int("recent_star" in c["signals"]) + int("upstream_activity" in c["signals"])),
        c["project_id"], c["repo"]))
    return select_candidates(candidates, limit, per_project), suppressed, len(candidates)


def select_candidates(candidates, limit, per_project, per_repo=None):
    selected, counts, repo_counts = [], {}, {}
    # Cooled-down pending items get the first slice, then one item per project
    # in round-robin order, then remaining capacity by score. This prevents a
    # lexicographically early project from monopolising every round.
    #
    # Evidence fetched in this run is the first ordering dimension: a
    # repository the run already paid for must reach the Agent instead of
    # being pushed behind alphabetically earlier candidates. The fairness
    # rules are unchanged otherwise - per-project and per-repo caps still
    # apply, and the round-robin over projects is preserved.
    ordered = sorted(candidates, key=lambda c: (
        -c.get("evidence_rank", 0),
        -int(c["queue_state"]["cooldown_due"]), c["queue_state"].get("shown_count", 0),
        c["queue_state"].get("first_seen_at", ""), c["project_id"], c["repo"],
        c.get("capability", {}).get("key") or ""))
    def eligible(candidate):
        project = candidate["project_id"]
        return (per_project is None or counts.get(project, 0) < per_project) and (
            per_repo is None or repo_counts.get(candidate["repo"], 0) < per_repo)
    def take(candidate):
        selected.append(candidate)
        counts[candidate["project_id"]] = counts.get(candidate["project_id"], 0) + 1
        repo_counts[candidate["repo"]] = repo_counts.get(candidate["repo"], 0) + 1
    # First round: one per project, with cooled-down candidates preferred.
    first = {}
    for candidate in ordered:
        first.setdefault(candidate["project_id"], candidate)
    for candidate in sorted(first.values(), key=lambda c: ordered.index(c)):
        if limit is not None and len(selected) >= limit:
            break
        if eligible(candidate):
            take(candidate)
    for candidate in ordered:
        if limit is not None and len(selected) >= limit:
            break
        if candidate in selected or not eligible(candidate):
            continue
        take(candidate)
    return selected


def release_record(value):
    release = value[0] if value else None
    return ({"tag": release.get("tag_name"), "url": release.get("html_url"),
             "published_at": release.get("published_at"),
             "body": (release.get("body") or "")[:8000]} if release else None)


def fetch_evidence(candidate, data_dir, prior=None):
    name = candidate["repo"]
    if not REPO_PATTERN.fullmatch(name):
        raise ValueError("Invalid owner/repo")
    record = {"repo": name, "repo_id": candidate.get("repo_id"),
              "repo_revision": candidate["repo_revision"], "fetched_at": now_utc().isoformat(),
              "status": "complete", "errors": [], "previous": {
                  "head_sha": (prior or {}).get("head_sha"),
                  "release": (prior or {}).get("release"),
                  "readme": (prior or {}).get("readme"),
              }}
    for kind, endpoint in (("readme", f"repos/{name}/readme"),
                           ("releases", f"repos/{name}/releases?per_page=1"),
                           ("commits", f"repos/{name}/commits?per_page=5")):
        try:
            value = budgeted_get(candidate.get("budget"), endpoint)
            if kind == "readme":
                content = base64.b64decode(value.get("content", ""), validate=False).decode("utf-8", "replace")
                record["readme"] = {"blob_sha": value.get("sha"), "url": value.get("html_url"),
                                     "text": content[:6000], "truncated": len(content) > 6000}
            elif kind == "releases":
                record["release"] = release_record(value)
            else:
                record["commits"] = [{"sha": row.get("sha"), "url": row.get("html_url"),
                                      "message": row.get("commit", {}).get("message", "")[:1500]}
                                     for row in value[:5]]
                record["head_sha"] = value[0].get("sha") if value else None
        except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired,
                TypeError, KeyError, AttributeError) as exc:
            record["status"] = "partial"
            record["errors"].append(f"{kind}: {type(exc).__name__}")
            if isinstance(exc, BudgetExceeded):
                record["status"] = "skipped"
                break
    changed = (compare_observed(record, prior, {"head": True, "release": True, "readme": True})
               if prior else {"head_changed": None, "release_changed": None,
                              "readme_changed": None})
    record["change_summary"] = {
        "baseline_available": bool(prior),
        "observed": {"head": True, "release": True, "readme": True},
        "head_changed": changed["head_changed"],
        "release_changed": changed["release_changed"],
        "readme_changed": changed["readme_changed"],
        "scope": "Latest release and five commit messages; not a complete source diff or proof of value",
    }
    if record["status"] == "complete":
        record["observed"] = {"head": True, "release": True, "readme": True}
        record["content_revision"] = evidence_revision(record)
        record["changed_at"] = (record["fetched_at"] if any_change(changed)
                                else (prior or {}).get("changed_at", record["fetched_at"]))
    path = data_dir / "auto-opportunities" / "evidence" / (name.replace("/", "__") + ".json")
    if record["status"] == "complete":
        atomic_json(path, record)
    # A partial refresh never destroys the last complete evidence.
    return record


def fetch_cheap_evidence(candidate, data_dir, prior=None, budget=None):
    """One GET: the latest release, for background coverage rotation."""
    name = candidate["repo"]
    if not REPO_PATTERN.fullmatch(name):
        raise ValueError("Invalid owner/repo")
    record = {"repo": name, "repo_id": candidate.get("repo_id"),
              "repo_revision": candidate["repo_revision"], "fetched_at": now_utc().isoformat(),
              "status": "complete", "errors": [], "probe": "cheap",
              "previous": {"head_sha": (prior or {}).get("head_sha"),
                           "release": (prior or {}).get("release"),
                           "readme": (prior or {}).get("readme")}}
    try:
        value = budgeted_get(budget, f"repos/{name}/releases?per_page=1")
        record["release"] = release_record(value)
    except BudgetExceeded:
        record["status"] = "skipped"
        record["errors"].append("request budget exhausted")
        return record
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired,
            TypeError, KeyError, AttributeError) as exc:
        record["status"] = "partial"
        record["errors"].append(f"releases: {type(exc).__name__}")
        return record
    baseline = bool(prior and prior.get("status") == "complete")
    record["baseline_available"] = baseline
    record["observed"] = {"head": False, "release": True, "readme": False}
    release_changed = False
    if baseline:
        # A cheap probe only observes the Release. HEAD and README stay unknown
        # even when a previous deep probe recorded them.
        release_changed = compare_observed(record, prior,
                                          {"head": False, "release": True, "readme": False}
                                          )["release_changed"]
        record["changed"] = {"release_changed": release_changed,
                             "head_changed": None, "readme_changed": None}
    record["cheap_revision"] = shared_evidence_revision(
        {"head": None, "release": record.get("release"), "readme": {"blob_sha": None}})
    record["scope"] = ("Latest release only; README and commit evidence were not fetched "
                        "in this cheap probe")
    path = data_dir / "auto-opportunities" / "evidence" / (name.replace("/", "__") + ".json")
    if record["status"] == "complete" and prior and prior.get("status") == "complete":
        # A cheap probe must not destroy a richer previous record.
        merged = {**prior, **{key: record[key] for key in
                              ("release", "fetched_at", "changed", "baseline_available")},
                  "repo": name, "repo_id": record.get("repo_id"),
                  "repo_revision": record["repo_revision"], "status": "complete",
                  "errors": [], "probe": "cheap",
                  "cheap_revision": record["cheap_revision"]}
        merged["observed"] = {**observed_fields(prior), "release": True}
        merged["changed_at"] = (record["fetched_at"]
                                if release_changed
                                else prior.get("changed_at", record["fetched_at"]))
        merged["content_revision"] = evidence_revision(merged)
        atomic_json(path, merged)
        return merged
    if record["status"] == "complete":
        # The first cheap probe is the Release baseline; persist it so the next
        # run can detect a real Release-only change.
        record["changed_at"] = record["fetched_at"]
        record["content_revision"] = evidence_revision(record)
        atomic_json(path, record)
    return record


def evidence_revision(record):
    return shared_evidence_revision(record)


def evidence_cache(data_dir, name):
    return data_dir / "auto-opportunities/evidence" / (name.replace("/", "__") + ".json")


def load_evidence(snapshot, data_dir, warnings):
    cache = {}
    for repo in snapshot.get("repos", []):
        name = repo.get("full_name", "")
        if not REPO_PATTERN.fullmatch(name):
            continue
        try:
            value = read_json(evidence_cache(data_dir, name))
            if value and value.get("status") == "complete":
                cache[name] = value
        except (OSError, ValueError):
            warnings.append(f"Unreadable evidence cache: {name}; evidence remains unknown")
    return cache


def attach_cached_revisions(snapshot, data_dir, cache=None, unavailable=()):
    if cache is None:
        cache = load_evidence(snapshot, data_dir, [])
    rows = []
    for repo in snapshot.get("repos", []):
        # Re-attaching after a successful refresh must clear this run's earlier
        # unknown state, rather than carrying an old private flag forward.
        repo = {key: value for key, value in repo.items()
                if not key.startswith("_evidence_") and key not in
                ("_evidence_record", "_evidence_source", "_release_text",
                 "_capability_hints", "_evidence_text", "_evidence_revision",
                 "_evidence_changed_at", "_evidence_status",
                 "_evidence_fallback_note")}
        name = repo.get("full_name", "")
        cached = cache.get(name)
        if cached and cached.get("status") == "complete":
            blob_sha = (cached.get("readme") or {}).get("blob_sha")
            readme_text = (cached.get("readme") or {}).get("text", "")
            repo = {**repo, "_evidence_revision": evidence_revision(cached),
                    "_evidence_changed_at": cached.get("changed_at"),
                    "_evidence_text": readme_text,
                    "_evidence_record": cached,
                    "_evidence_source": "cache",
                    "_capability_hints": capability_hints(
                        readme_text, cached.get("release"), cached.get("commits", []),
                        readme_blob_sha=blob_sha)}
        if name in unavailable:
            repo = {**repo, "_evidence_unavailable": True}
        rows.append(repo)
    return {**snapshot, "repos": rows}


def resolve_evidence(run_record, cache_record, repo):
    """Choose the evidence a candidate is actually judged on.

    Fresh evidence from this run wins. A failed or skipped run falls back to
    the last complete cached record, but the status still reports the
    failure so the Agent is not told the upstream was re-checked
    successfully. Cached evidence is always labelled with its own source and
    fetch time, never as this run's work.

    The identity fields (revision, changed_at) always come from a complete
    record. A partial fetch must not renumber the upstream revision, because
    that revision is what a decision card binds to.
    """
    cache_complete = bool(cache_record) and cache_record.get("status") == "complete"
    if run_record and run_record.get("status") == "complete":
        return {"record": run_record, "identity": run_record, "source": "this_run",
                "status": "complete"}
    if run_record and run_record.get("status") == "partial":
        if cache_complete:
            return {"record": cache_record, "identity": cache_record, "source": "cache",
                    "status": "partial",
                    "fallback_note": "This run's fetch failed; the digest is the last complete cache."}
        return {"record": run_record, "identity": None, "source": "this_run",
                "status": "partial"}
    if run_record:
        if cache_complete:
            return {"record": cache_record, "identity": cache_record, "source": "cache",
                    "status": "not_fetched",
                    "fallback_note": "This run did not complete a fetch; the digest is the last complete cache."}
        return {"record": None, "identity": None, "source": "none", "status": "not_fetched"}
    if cache_complete:
        matched = cache_record.get("repo_revision") == repo_revision(repo)
        return {"record": cache_record, "identity": cache_record, "source": "cache",
                "status": "cached" if matched else "stale", "fallback": None}
    return {"record": None, "identity": None, "source": "none", "status": "not_fetched"}


def attach_run_evidence(snapshot, run_records, cache=None, unavailable=()):
    """Attach this run's freshly fetched evidence to the snapshot rows.

    The record is attached before candidates are generated so the candidate
    can carry the evidence text and the recall channels can use the README
    and Release text fetched in this very run.
    """
    cache = cache or {}
    unavailable = set(unavailable)
    rows = []
    for repo in snapshot.get("repos", []):
        # Rebuild the evidence state from scratch. A flag set by an earlier
        # pass (for example "the previous check failed") must not survive a
        # check that has now succeeded.
        repo = {key: value for key, value in repo.items()
                if not key.startswith("_evidence_") and key not in
                ("_release_text", "_capability_hints")}
        name = repo.get("full_name", "")
        run_record = (run_records or {}).get(name)
        cache_record = cache.get(name)
        resolved = resolve_evidence(run_record, cache_record, repo)
        record = resolved["record"]
        identity = resolved.get("identity")
        if record:
            blob_sha = (record.get("readme") or {}).get("blob_sha")
            readme_text = str((record.get("readme") or {}).get("text") or "")
            release_text = str((record.get("release") or {}).get("body") or "")
            repo = {**repo,
                    "_evidence_revision": (evidence_revision(identity) if identity else None),
                    "_evidence_changed_at": (identity or {}).get("changed_at"),
                    "_evidence_text": readme_text,
                    "_release_text": release_text[:RELEASE_RECALL_LIMIT],
                    "_evidence_record": record,
                    "_evidence_source": resolved["source"],
                    "_evidence_status": resolved["status"],
                    "_evidence_fallback_note": resolved.get("fallback_note"),
                    "_capability_hints": capability_hints(
                        readme_text, record.get("release"), record.get("commits", []),
                        readme_blob_sha=blob_sha)}
        else:
            repo = {**repo, "_evidence_record": None, "_evidence_source": "none",
                    "_evidence_status": resolved["status"],
                    "_evidence_fallback_note": resolved.get("fallback_note")}
        if name in unavailable:
            repo = {**repo, "_evidence_unavailable": True}
        rows.append(repo)
    return {**snapshot, "repos": rows}


def watch_state(data_dir, warnings):
    directory = data_dir / "auto-opportunities"
    try:
        value = read_json(directory / "watch.json", {}) or {}
        if any(not isinstance(row, dict) for row in value.values()):
            raise ValueError("Invalid watch state")
        return value
    except (OSError, ValueError):
        warnings.append("Unreadable watch state; rotation restarts without changing feedback")
        return {}


def probe_watched(snapshot, suppressed, data_dir, budget, *, focused=None,
                  candidates=(), prior=None, state=None, focus_limit=8, now=None,
                  metadata_changes=(), used_repos=(), request_budget=None,
                  cheap_budget=0):
    """Reserve at least half the budget for the oldest checks across all Stars.

    The other half prioritizes new interest, focus and relevant metadata changes.
    Even unmatched or already-judged Stars remain eligible for content checks.
    """
    focused, prior, state = focused or {}, prior or {}, state or {}
    now = now or now_utc()
    rows = {r["full_name"]: r for r in snapshot.get("repos", [])
            if REPO_PATTERN.fullmatch(r.get("full_name", ""))}
    relevant = {row["repo"] for row in candidates} | {row["repo"] for row in suppressed}
    metadata_changes = set(metadata_changes)
    used_repos = set(used_repos)
    def priority(name):
        row = rows[name]
        cached = prior.get(name)
        return (
            -int(name in metadata_changes),
            -int(name in used_repos),
            -int(bool(cached and cached.get("repo_revision") != repo_revision(row))),
            -int(valid_recent(row.get("starred_at"), now - timedelta(days=14), now)
                 and not state.get(name)),
            -int(name in focused),
            -int(name in relevant), name)
    def oldest(name):
        row = state.get(name, {})
        return max(row.get("checked_at", ""), row.get("last_attempt_at", ""))
    selected = []
    cheap_selected = []
    def take(ordered, count):
        for name in ordered:
            if count <= 0:
                break
            if name in selected:
                continue
            if name in focused and sum(n in focused for n in selected) >= focus_limit:
                continue
            selected.append(name)
            count -= 1
    take(sorted(rows, key=lambda n: (oldest(n), priority(n))), (budget + 1) // 2)
    take(sorted(rows, key=lambda n: (priority(n)[:-1], oldest(n), n)), budget - len(selected))
    # Cheap probes cover the background tail at one GET per repository.
    if cheap_budget:
        for name in sorted(rows, key=lambda n: (oldest(n), priority(n))):
            if len(cheap_selected) >= cheap_budget:
                break
            if name in selected:
                continue
            if name in focused and sum(n in focused for n in selected + cheap_selected) >= focus_limit:
                continue
            cheap_selected.append(name)
    results, updates = {}, {}
    for name in selected:
        row = rows[name]
        candidate = {"repo": name, "repo_id": row.get("id"), "repo_revision": repo_revision(row),
                     "budget": request_budget}
        value = fetch_evidence(candidate, data_dir, prior.get(name))
        results[name] = value
        checked_at = now_utc().isoformat()
        updates[name] = {"checked_at": (checked_at if value["status"] == "complete"
                                         else state.get(name, {}).get("checked_at", "")),
                         "last_attempt_at": checked_at, "status": value["status"],
                         "repo_id": row.get("id"), "repo": name,
                         "repo_revision": repo_revision(row)}
    for name in cheap_selected:
        row = rows[name]
        candidate = {"repo": name, "repo_id": row.get("id"), "repo_revision": repo_revision(row)}
        value = fetch_cheap_evidence(candidate, data_dir, prior.get(name), request_budget)
        results.setdefault(name, value)
        checked_at = now_utc().isoformat()
        updates.setdefault(name, {"checked_at": (checked_at if value["status"] == "complete"
                                                  else state.get(name, {}).get("checked_at", "")),
                                  "last_attempt_at": checked_at,
                                  "status": value["status"],
                                  "repo_id": row.get("id"), "repo": name,
                                  "repo_revision": repo_revision(row),
                                  "probe": "cheap"})
    if updates:
        directory = data_dir / "auto-opportunities"
        with write_lock(directory):
            current = watch_state(data_dir, [])
            for name, value in updates.items():
                if value["checked_at"] >= current.get(name, {}).get("checked_at", ""):
                    current[name] = value
            atomic_json(directory / "watch.json", current)
    return results


def fetch_comparison(name, base, head, request_budget=None):
    """At most one GET and 30 bounded patches, fixed to immutable commits."""
    if not all(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{7,40}", sha)
               for sha in (base, head)) or head.startswith(base):
        return None
    try:
        result = budgeted_get(request_budget, f"repos/{name}/compare/{base}...{head}",
                              kind="compare")
        files = result.get("files") or []
        return {"base": base, "head": head, "status": result.get("status"),
                "ahead_by": result.get("ahead_by"), "behind_by": result.get("behind_by"),
                "url": result.get("html_url"), "total_commits": result.get("total_commits"),
                "files_reported": len(files), "files_truncated": len(files) > 30 or len(files) >= 300,
                "files": [{"path": row.get("filename"), "previous_path": row.get("previous_filename"),
                           "status": row.get("status"), "additions": row.get("additions"),
                           "deletions": row.get("deletions"),
                           "patch": (row.get("patch") or "")[:1200],
                           "patch_truncated": len(row.get("patch") or "") > 1200}
                          for row in files[:30]],
                "scope": "GitHub compare; at most 30 files and 1200 patch characters per file"}
    except BudgetExceeded:
        return {"base": base, "head": head, "status": "not_fetched",
                "scope": "Request budget exhausted before this comparison"}
    except (RuntimeError, OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
        return {"base": base, "head": head, "status": "unavailable",
                "scope": "Compare failed; no complete source delta is claimed"}


def roots_for(args):
    if args.skills_root:
        return args.skills_root
    if args.repo_root:
        return [args.repo_root / "skills"]
    return default_roots()


def cmd_projects(args):
    profiles, warnings = discover(roots_for(args), args.project)
    return emit(envelope(profiles, coverage={"projects": len(profiles), "roots": [str(p) for p in roots_for(args)]},
                         warnings=warnings, extra={"status": "partial" if warnings else "ok"}))


def cmd_auto(args):
    data_dir = args.data_dir.expanduser().resolve() if args.data_dir else StarTracker.CACHE_DIR
    snapshot = read_json(data_dir / "original_latest.json")
    request_budget = RequestBudget(getattr(args, "request_budget", None))
    if args.refresh:
        snapshot = refresh_snapshot(data_dir, snapshot, request_budget)
    if not snapshot:
        return emit(envelope([], errors=["No snapshot; use auto-discover --refresh with authenticated gh"]), 1)
    profiles, warnings = discover(roots_for(args), args.project)
    if not profiles:
        return emit(envelope([], snapshot=snapshot, errors=["No readable target skills"], warnings=warnings), 1)
    feedback, feedback_warnings = feedback_index(data_dir)
    warnings += feedback_warnings
    current = now_utc()
    timestamp = parse_dt(snapshot.get("snapshot_meta", {}).get("fetched_at") or snapshot.get("timestamp"))
    if not timestamp or (current - timestamp).total_seconds() > 36 * 3600:
        warnings.append("Snapshot older than 36 hours or unknown; refresh before judging recent upstream changes")
    focused = focus_repositories(data_dir, warnings)
    state = watch_state(data_dir, warnings)
    queue = load_review_queue(data_dir, warnings)
    # Capture all baselines BEFORE any fetch can atomically replace the cache.
    prior = load_evidence(snapshot, data_dir, warnings)
    previous_failures = {name for name, row in state.items()
                         if row.get("status") in {"partial", "skipped"}}
    snapshot = attach_cached_revisions(snapshot, data_dir, prior, previous_failures)
    from repository_profile import local_reference_snapshots
    metadata_changes, used_repos = set(), set()
    for row in snapshot.get("repos", []):
        name = row.get("full_name", "")
        if not name:
            continue
        prior_meta = state.get(name) or next(
            (entry for entry in state.values()
             if isinstance(entry, dict) and entry.get("repo_id") == row.get("id")), {})
        if prior_meta.get("repo_revision") and prior_meta.get("repo_revision") != repo_revision(row):
            metadata_changes.add(name)
        if local_reference_snapshots(name, roots_for(args)):
            used_repos.add(name)
    def all_candidates(source, queue=None, queue_now=None):
        return prepare(source, profiles, feedback, current, None, None,
                       args.recent_days, args.update_days, args.show_suppressed, focused,
                       queue=queue, queue_now=queue_now)
    candidates, suppressed, eligible = all_candidates(snapshot, queue=queue, queue_now=current)
    unique = (probe_watched(snapshot, suppressed, data_dir, args.evidence_limit,
                           focused=focused, candidates=candidates, prior=prior, state=state,
                           focus_limit=getattr(args, "focus_limit", 8), now=current,
                           metadata_changes=metadata_changes, used_repos=used_repos,
                           request_budget=request_budget,
                           cheap_budget=getattr(args, "cheap_budget", 0))
              if args.fetch_evidence else {})
    failed_now = {name for name, row in unique.items() if row["status"] == "partial"}
    skipped_budget = {name for name, row in unique.items() if row["status"] == "skipped"}
    successful_now = {name for name, row in unique.items() if row["status"] == "complete"}
    # A skipped or failed attempt does not prove an earlier incomplete check
    # recovered. Keep it pending until a complete read succeeds.
    unavailable = (previous_failures - successful_now) | failed_now
    cache = {**prior, **{name: row for name, row in unique.items()
                        if row["status"] == "complete"}}
    # This run's freshly fetched evidence is attached before the candidates are
    # generated. The README and Release text fetched in this run therefore
    # take part in this run's recall, and the candidates can carry the
    # evidence the Agent has to judge.
    snapshot = attach_run_evidence(snapshot, unique, cache, unavailable)
    candidates, suppressed, eligible = all_candidates(snapshot, queue=queue, queue_now=current)
    for name in sorted(unavailable & {row.get("full_name") for row in snapshot.get("repos", [])}):
        warnings.append(f"Watched evidence incomplete: {name}; previous complete evidence retained")
    all_rows = candidates
    candidates = select_candidates(candidates, args.limit, args.per_project, getattr(args, "per_repo", 3))
    if args.write:
        queue = update_review_queue(data_dir, queue, candidates, all_rows, snapshot, feedback, current)
    snapshots_by_repo, observation_comparisons = {}, {}
    projects_by_path = {profile["skill_path"]: profile["project_id"] for profile in profiles}
    rows_by_name = {row.get("full_name"): row for row in snapshot.get("repos", [])}
    inspected = set(unique) | {row["repo"] for row in candidates} | set(focused)
    for name in inspected:
        snapshots = local_reference_snapshots(name, roots_for(args))
        head = (cache.get(name) or {}).get("head_sha")
        for local in snapshots:
            local["project_id"] = projects_by_path.get(local["skill_path"])
            local["upstream_head"] = head
            local["upstream_commit_comparison"] = compare_snapshot_commit(local.get("commit"), head)
        snapshots_by_repo[name] = snapshots
        if name in unique and unique[name]["status"] == "complete":
            observed_base = (prior.get(name) or {}).get("head_sha")
            observation_comparisons[name] = (fetch_comparison(name, observed_base, head, request_budget)
                                             if observed_base and observed_base != head else None)
            by_base = ({observed_base: observation_comparisons[name]}
                       if observation_comparisons[name] else {})
            for local in snapshots:
                pinned = local.get("commit")
                if not pinned or not head:
                    local["source_comparison"] = None
                elif local["upstream_commit_comparison"] in {"same", "same-prefix"}:
                    local["source_comparison"] = {"base": pinned, "head": head,
                                                   "status": "identical", "files": []}
                elif pinned in by_base:
                    local["source_comparison"] = by_base[pinned]
                elif len(by_base) < 2:
                    by_base[pinned] = fetch_comparison(name, pinned, head, request_budget)
                    local["source_comparison"] = by_base[pinned]
                else:
                    local["source_comparison"] = {
                        "base": pinned, "head": head, "status": "not_fetched",
                        "scope": "Shared per-repository compare budget exhausted; this component's delta is unknown"}
            if any(row and row["status"] == "unavailable"
                   for row in by_base.values()):
                warnings.append(f"Source comparison unavailable: {name}; content review remains incomplete")
    changes = [evidence_delta(name, value, prior.get(name)) for name, value in unique.items()]
    for delta in changes:
        name = delta["repo"]
        delta["observation_comparison"] = observation_comparisons.get(name)
        delta["local_snapshots"] = snapshots_by_repo.get(name, [])
    for candidate in candidates:
        name = candidate["repo"]
        cached = cache.get(name)
        value = unique.get(name)
        # The status was already resolved from the real evidence when the
        # candidate was built. This loop only attaches the raw record so the
        # Agent can inspect the full upstream object behind the digest.
        if value:
            candidate["upstream_evidence"] = value
        elif cached:
            candidate["upstream_evidence"] = cached
        candidate["local_snapshots"] = snapshots_by_repo[name]
        target_snapshots = [local for local in snapshots_by_repo[name]
                            if local["skill_path"] == candidate.get("skill_path")]
        candidate["target_snapshots"] = target_snapshots
        candidate["source_comparison"] = (target_snapshots[0].get("source_comparison")
                                           if target_snapshots else None)
        candidate["upstream_change"] = evidence_delta(name, value, prior.get(name))
        candidate["upstream_change"]["observation_comparison"] = observation_comparisons.get(name)
    focus_deltas_rows = []
    for name, entry in sorted(focused.items()):
        delta = evidence_delta(name, unique.get(name), prior.get(name))
        delta.update({"watch_scope": "focus", "reason": entry.get("reason"),
                      "local_snapshots": snapshots_by_repo.get(name, []),
                      "source_comparisons": [{"project_id": local["project_id"],
                                              "skill_path": local["skill_path"],
                                              "comparison": local.get("source_comparison")}
                                             for local in snapshots_by_repo.get(name, [])],
                      "observation_comparison": observation_comparisons.get(name),
                      "affected_targets": [{"project_id": row["project_id"],
                                            "target_revision": row["target_revision"]}
                                           for row in all_rows if row["repo"] == name],
                      "suppressed_targets": [row for row in suppressed if row["repo"] == name]})
        focus_deltas_rows.append(delta)
    present_focus = set(focused) & set(rows_by_name)
    focus_not_fetched = sorted(present_focus - set(unique))
    focus_unmatched = [{"repo": name, "reason": "not_in_star_collection"}
                       for name in sorted(set(focused) - set(rows_by_name))]
    deep_checked = sorted(name for name, row in unique.items()
                          if row.get("probe") != "cheap" and row["status"] == "complete")
    cheap_probed = sorted(name for name, row in unique.items()
                          if row.get("probe") == "cheap" and row["status"] == "complete")
    failed_deep = sorted(name for name, row in unique.items()
                         if row.get("probe") != "cheap" and row["status"] == "partial")
    failed_cheap = sorted(name for name, row in unique.items()
                          if row.get("probe") == "cheap" and row["status"] == "partial")
    checked_complete = set(deep_checked) | set(cheap_probed)
    watch_coverage = {
        "eligible_repos": len(rows_by_name),
        "checked": len(checked_complete),
        "checked_repos": sorted(checked_complete),
        "deep_checked": deep_checked,
        "cheap_probed": cheap_probed,
        "failed_deep": failed_deep,
        "failed_cheap": failed_cheap,
        "skipped_budget": sorted(skipped_budget),
        "complete": len(checked_complete),
        "failed": sorted(set(failed_deep) | set(failed_cheap)),
        "unresolved_previous_failures": sorted(unavailable - failed_now),
        "not_checked": len(rows_by_name) - len(checked_complete),
        "attempted_repos": sorted(unique),
        "metadata_changed_repos": sorted(metadata_changes),
        "used_repos_checked": sorted(checked_complete & used_repos),
        "used_repos": len(used_repos),
        "strategy": "at least half oldest-first across all Stars; remainder prioritizes metadata change, used source, new interest, focus and relevance",
        "request_budget": request_budget.report(),
    }
    # Disclosure of the evidence/queue split. A repository the run fetched is
    # not the same as a repository that reached the Agent: the queue caps can
    # leave a fetched repository out. "Not in the candidates" must not be read
    # as "nothing changed".
    fetched_now = {name for name, row in unique.items() if row.get("status") == "complete"}
    candidate_repos = {row["repo"] for row in candidates}
    fetched_in_candidates = sorted(fetched_now & candidate_repos)
    fetched_not_in_candidates = sorted(fetched_now - candidate_repos)
    candidates_with_evidence = [row for row in candidates
                                if row.get("evidence_summary")]
    watch_coverage["evidence_candidates"] = {
        "fetched_this_run": len(fetched_now),
        "fetched_in_candidates": len(fetched_in_candidates),
        "fetched_in_candidates_repos": fetched_in_candidates,
        "fetched_not_in_candidates": len(fetched_not_in_candidates),
        "fetched_not_in_candidates_repos": fetched_not_in_candidates,
        "candidates_with_evidence": len(candidates_with_evidence),
        "candidates_total": len(candidates),
        "candidates_without_evidence": len(candidates) - len(candidates_with_evidence),
        "note": ("A repository fetched this run but absent from the candidates was "
                 "dropped by the queue caps, not found unchanged."),
    }
    queue_entries = list((queue.get("entries") or {}).values())
    queue_pending = [entry for entry in queue_entries if entry.get("state") in {"pending", "shown"}]
    shown_pending = [entry for entry in queue_pending if entry.get("state") == "shown"]
    oldest_pending = min((entry.get("first_seen_at", "") for entry in queue_pending), default=None)
    queue_coverage = {
        "queue_state": queue.get("state", "healthy"),
        "pending_total": len(queue_pending), "shown_pending": len(shown_pending),
        "oldest_pending_first_seen_at": oldest_pending,
        "oldest_pending_age_days": (round((current - parse_dt(oldest_pending)).total_seconds() / 86400, 1)
                                    if oldest_pending and parse_dt(oldest_pending) else None),
        "cycle_days_estimate": (len(queue_pending) / max(1, len(candidates))
                                if args.write and queue.get("state") != "degraded" else None),
        "admitted_this_round": len(candidates),
        "starved_projects": sorted({entry.get("project_id") for entry in queue_pending}
                                   - {entry.get("project_id") for entry in candidates}),
    }
    selected_ids = {c["project_id"] for c in candidates}
    result = envelope(candidates, snapshot=snapshot, coverage={
        "projects": len(profiles), "repos": len(snapshot.get("repos", [])),
        "eligible": eligible, "returned": len(candidates), "suppressed": len(suppressed),
        "truncated": eligible > len(candidates), "evidence_fetched_repos": len(unique),
        "focused_repositories": len(focused),
        "focus_candidates": sum(row["watch_scope"] == "focus" for row in candidates),
        "focus_suppressed": sum(row["watch_scope"] == "focus" for row in suppressed),
        "focus_not_fetched": focus_not_fetched,
        "focus_deferred": len(focus_not_fetched),
        "watch_coverage": watch_coverage,
        "review_queue": queue_coverage,
        "focus_unmatched": focus_unmatched,
        "snapshot_age_hours": round((current-timestamp).total_seconds()/3600, 1) if timestamp else None,
    }, warnings=warnings, extra={
        "projects": [p for p in profiles if p["project_id"] in selected_ids],
        "suppressed": suppressed, "run_path": None,
        "focus_deltas": focus_deltas_rows,
        "upstream_changes": changes,
        "review_required": True,
        "usage_note": "Read current target implementation and upstream evidence; keep at most three valuable opportunities. Record real decisions with target_revision, repo_revision and evidence_revision via opportunity.py. No change can legitimately yield no recommendation.",
    })
    if warnings or any(c["evidence_status"] in ("partial", "stale") for c in candidates):
        result["status"] = "partial"
    if args.write:
        directory = data_dir / "auto-opportunities/runs"
        directory.mkdir(parents=True, exist_ok=True)
        with write_lock(directory):
            path = directory / (current.strftime("%Y%m%dT%H%M%S.%fZ") + ".json")
            result["run_path"] = str(path)
            atomic_json(path, result)
    return emit(result)


def positive(value):
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return n


def nonnegative(value):
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return n


def cmd_reconcile(args):
    """离线对账：反馈卡 → 队列 judged 状态。"""
    data_dir = args.data_dir.expanduser().resolve() if args.data_dir else StarTracker.CACHE_DIR
    result, code = reconcile_queue(data_dir)
    # CLI 输出保持精简：队列全量内容留在状态文件里，不回显到 stdout。
    return emit({key: value for key, value in result.items() if key != "entries"}, code)


def cmd_receipt(args):
    """写一次每日闭环的运行回执（judged / silent / failed）。"""
    data_dir = args.data_dir.expanduser().resolve() if args.data_dir else StarTracker.CACHE_DIR
    outcome = args.outcome
    errors = list(args.error or [])
    notify = None
    if args.notify is not None:
        notify = {"recommended": args.notify == "true",
                  "reason": args.notify_reason or "调用方显式指定"}
    payload, code = build_receipt(data_dir, outcome=outcome, errors=errors, notify=notify,
                                   requested=outcome)
    if not payload.get("ok"):
        return emit({"schema_version": "daily-receipt/1.0", "ok": False,
                     "error": payload.get("error"), "facts": payload.get("facts"),
                     "errors": [payload.get("error")]}, 1)
    receipt = payload["receipt"]
    path = daily_loop.write_receipt(data_dir, receipt)
    receipt = {**receipt, "receipt_path": str(path)}
    return emit(receipt, code)


def cmd_lease(args):
    """并发租约：acquire / release / status。"""
    data_dir = args.data_dir.expanduser().resolve() if args.data_dir else StarTracker.CACHE_DIR
    if args.lease_action == "acquire":
        try:
            lease, notes = daily_loop.acquire_lease(
                data_dir, args.owner, run_id=args.run_id,
                ttl_seconds=args.ttl)
        except daily_loop.LeaseConflict as exc:
            return emit({"schema_version": "daily-lease/1.0", "acquired": False,
                         "conflict": True, "error": str(exc),
                         "status": daily_loop.lease_status(data_dir)}, 1)
        except daily_loop.LeaseError as exc:
            return emit({"schema_version": "daily-lease/1.0", "acquired": False,
                         "error": str(exc)}, 1)
        return emit({"schema_version": "daily-lease/1.0", "acquired": True,
                     "lease": lease, "notes": notes,
                     "status": daily_loop.lease_status(data_dir)}, 0)
    if args.lease_action == "release":
        result = daily_loop.release_lease(data_dir, args.owner, run_id=args.run_id)
        code = 0 if result.get("released") else 1
        return emit({"schema_version": "daily-lease/1.0", **result,
                     "status": daily_loop.lease_status(data_dir)}, code)
    return emit({"schema_version": "daily-lease/1.0",
                 "status": daily_loop.lease_status(data_dir)}, 0)


def main():
    parser = argparse.ArgumentParser(description="Dynamic local targets and evidence for scheduled opportunity review")
    sub = parser.add_subparsers(dest="command", required=True)
    for command, function in (("projects", cmd_projects), ("auto-discover", cmd_auto)):
        p = sub.add_parser(command)
        p.add_argument("--project")
        p.add_argument("--repo-root", type=Path)
        p.add_argument("--skills-root", action="append", type=Path, help="Repeat for additional installed suites; no per-project registration")
        p.add_argument("--data-dir", type=Path, help="Private runtime state directory")
        p.set_defaults(func=function)
        if command == "auto-discover":
            p.add_argument("--recent-days", type=positive, default=14)
            p.add_argument("--update-days", type=positive, default=7)
            p.add_argument("--limit", type=positive, default=12)
            p.add_argument("--per-project", type=positive, default=2)
            p.add_argument("--per-repo", type=positive, default=3,
                           help="Maximum component opportunities from one repository per review queue")
            p.add_argument("--show-suppressed", action="store_true")
            p.add_argument("--refresh", action="store_true", help="Explicit GET via gh; atomically commit only a full same-account snapshot")
            p.add_argument("--fetch-evidence", action="store_true", help="Explicit bounded README/release/commit GETs")
            p.add_argument("--evidence-limit", type=nonnegative, default=4)
            p.add_argument("--request-budget", type=positive, default=60,
                           help="Maximum GitHub GET calls in this run (star refresh and evidence included; default 60)")
            p.add_argument("--cheap-budget", type=positive, default=0,
                           help="Additional one-GET release probes for background coverage rotation")
            p.add_argument("--focus-limit", type=positive, default=8,
                           help="Maximum focused repositories fetched per run within the shared evidence budget")
            p.add_argument("--write", action="store_true")

    p = sub.add_parser("reconcile",
                        help="离线对账：把有反馈卡的队列条目置为 judged（不联网）")
    p.add_argument("--data-dir", type=Path, help="私有运行状态目录")
    p.set_defaults(func=cmd_reconcile)

    p = sub.add_parser("receipt", help="写每日闭环运行回执（judged/silent/failed）")
    p.add_argument("--data-dir", type=Path, help="私有运行状态目录")
    p.add_argument("--outcome", choices=["judged", "silent", "failed"],
                   help="不指定时按本轮事实自动判定")
    p.add_argument("--error", action="append", help="失败原因（可重复）")
    p.add_argument("--notify", choices=["true", "false"], help="通知结论")
    p.add_argument("--notify-reason", help="通知结论的理由")
    p.set_defaults(func=cmd_receipt)

    p = sub.add_parser("lease", help="每日闭环并发租约")
    p.add_argument("--data-dir", type=Path, help="私有运行状态目录")
    p.add_argument("lease_action", choices=["acquire", "release", "status"])
    p.add_argument("--owner", default="", help="租约持有者标识")
    p.add_argument("--run-id", help="本轮运行 ID")
    p.add_argument("--ttl", type=positive, default=daily_loop.DEFAULT_TTL_SECONDS,
                   help="租约有效期秒数（默认 1800）")
    p.set_defaults(func=cmd_lease)
    args = parser.parse_args()
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return emit(envelope([], errors=[str(exc)]), 1)


if __name__ == "__main__":
    raise SystemExit(main())
