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
from project_context import (compare_snapshot_commit, default_roots, digest, discover,
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


def refresh_snapshot(data_dir, old):
    login = github_get("user").get("login")
    if not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9-]+", login):
        raise ValueError("Cannot identify authenticated GitHub account")
    old_account = (old or {}).get("snapshot_meta", {}).get("account_id")
    if old_account and old_account.lower() != login.lower():
        raise ValueError("Snapshot belongs to another account; use a separate --data-dir")
    pages = github_get("user/starred?per_page=100&sort=created&direction=desc", True,
                       "application/vnd.github.star+json")
    if not isinstance(pages, list) or not pages or not all(isinstance(p, list) for p in pages):
        raise ValueError("Invalid starred pagination response; previous snapshot retained")
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
    return shared_repo_revision(repo)


def feedback_index(data_dir):
    result, warnings = {}, []
    for path in sorted((data_dir / "feedback").glob("*.json")):
        try:
            card = read_json(path)
            key = (card.get("target", {}).get("project_id"), card.get("signal", {}).get("repo"))
            if all(key):
                result.setdefault(key, []).append(card)
                repo_id = card.get("signal", {}).get("repo_id")
                if repo_id is not None:
                    result.setdefault((key[0], f"id:{repo_id}"), []).append(card)
        except (OSError, ValueError, AttributeError):
            warnings.append(f"Unreadable feedback: {path.name}")
    return result, warnings


def suppression(profile, repo, prior, now):
    if not prior:
        return None
    card = max(prior, key=lambda c: c.get("_recorded_at", ""))
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
            "binding": "revision" if old_target and old_repo else "legacy-time-fallback"}


def valid_recent(date, cutoff, now):
    parsed = parse_dt(date)
    return parsed is not None and cutoff <= parsed <= now


FOCUS_FILE = "repository-profiles/focus.json"


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


def evidence_delta(name, current, prior):
    complete = bool(current and current.get("status") == "complete")
    baseline = bool(prior and prior.get("status") == "complete")
    delta = {"repo": name, "baseline_available": baseline,
             "evidence_status": current.get("status") if current else "not_fetched",
             "changed": None, "new_commits": [],
             "commit_scope": "At most five messages; unobserved history is not inferred"}
    if complete and baseline:
        delta["changed"] = {
            "head_changed": current.get("head_sha") != prior.get("head_sha"),
            "release_changed": current.get("release") != prior.get("release"),
            "readme_changed": ((current.get("readme") or {}).get("blob_sha")
                               != (prior.get("readme") or {}).get("blob_sha")),
        }
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
            recent_days=14, update_days=7, show_suppressed=False, focused=None):
    focused = focused or {}
    candidates, suppressed = [], []
    indexed_repos = [{**repo, "_search_terms": terms_for(" ".join([
        repo.get("full_name") or "", repo.get("description") or "",
        repo.get("description_zh") or "", " ".join(repo.get("topics") or []),
        repo.get("_evidence_text") or "",
    ]))} for repo in snapshot.get("repos", [])]
    for profile in profiles:
        for repo in indexed_repos:
            name = repo.get("full_name", "")
            if not REPO_PATTERN.fullmatch(name):
                continue
            hits = match_terms(profile, repo)
            if not hits:
                continue
            primary = match_terms({"search_terms": profile.get("primary_terms", profile["search_terms"])}, repo)
            if not primary:
                continue
            reasons = []
            if valid_recent(repo.get("starred_at"), now - timedelta(days=recent_days), now):
                reasons.append("recent_star")
            if valid_recent(repo.get("pushed_at"), now - timedelta(days=update_days), now):
                reasons.append("upstream_activity")
            if name in focused:
                reasons.append("focused_watch")
            prior = feedback.get((profile["project_id"], name), [])
            if repo.get("id") is not None:
                prior = prior + feedback.get((profile["project_id"], f"id:{repo['id']}"), [])
            prior = list({digest(card): card for card in prior}.values())
            state = suppression(profile, repo, prior, now)
            if state and not show_suppressed:
                suppressed.append({"project_id": profile["project_id"], "repo": name,
                                   "watch_scope": "focus" if name in focused else "collection", **state})
                continue
            fingerprint = digest([profile["target_revision"], repo_revision(repo),
                                  repo.get("_evidence_revision"), profile["project_id"]])
            conflicts = scope_conflicts(profile, repo["_search_terms"])
            candidates.append({
                "candidate_id": fingerprint[:24], "project_id": profile["project_id"],
                "skill_path": profile.get("skill_path"),
                "repo": name, "repo_id": repo.get("id"), "description": repo.get("description"),
                "matched_terms": hits, "signals": reasons or ["existing_collection_match"],
                "primary_matches": primary,
                "starred_at": repo.get("starred_at"), "pushed_at": repo.get("pushed_at"),
                "repo_revision": repo_revision(repo), "target_revision": profile["target_revision"],
                "evidence_revision": repo.get("_evidence_revision"),
                "target_activity": profile["activity"], "suppression": state,
                "evidence_status": "not_fetched", "archived": bool(repo.get("is_archived")),
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
        -int("recent_star" in c["signals"]), -int("focused_watch" in c["signals"]),
        -min(c["target_activity"]["commits"], 10),
        -len(c["primary_matches"]), -len(c["matched_terms"]),
        -(int("recent_star" in c["signals"]) + int("upstream_activity" in c["signals"])),
        c["project_id"], c["repo"]))
    return select_candidates(candidates, limit, per_project), suppressed, len(candidates)


def select_candidates(candidates, limit, per_project, per_repo=None):
    selected, counts, repo_counts = [], {}, {}
    for candidate in candidates:
        project = candidate["project_id"]
        if per_project is not None and counts.get(project, 0) >= per_project:
            continue
        if per_repo is not None and repo_counts.get(candidate["repo"], 0) >= per_repo:
            continue
        selected.append(candidate)
        counts[project] = counts.get(project, 0) + 1
        repo_counts[candidate["repo"]] = repo_counts.get(candidate["repo"], 0) + 1
        if limit is not None and len(selected) == limit:
            break
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
            value = github_get(endpoint)
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
    record["change_summary"] = {
        "baseline_available": bool(prior),
        "head_changed": (record.get("head_sha") != prior.get("head_sha")) if prior else None,
        "release_changed": (record.get("release") != prior.get("release")) if prior else None,
        "readme_changed": ((record.get("readme") or {}).get("blob_sha")
                           != (prior.get("readme") or {}).get("blob_sha")) if prior else None,
        "scope": "Latest release and five commit messages; not a complete source diff or proof of value",
    }
    if record["status"] == "complete":
        record["content_revision"] = evidence_revision(record)
        before = evidence_revision(prior) if prior else None
        record["changed_at"] = (record["fetched_at"] if before != record["content_revision"]
                                else (prior or {}).get("changed_at", record["fetched_at"]))
    path = data_dir / "auto-opportunities" / "evidence" / (name.replace("/", "__") + ".json")
    if record["status"] == "complete":
        atomic_json(path, record)
    # A partial refresh never destroys the last complete evidence.
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
                if not key.startswith("_evidence_")}
        name = repo.get("full_name", "")
        cached = cache.get(name)
        if cached and cached.get("status") == "complete":
            repo = {**repo, "_evidence_revision": evidence_revision(cached),
                    "_evidence_changed_at": cached.get("changed_at"),
                    "_evidence_text": (cached.get("readme") or {}).get("text", "")}
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
                  candidates=(), prior=None, state=None, focus_limit=8, now=None):
    """Reserve at least half the budget for the oldest checks across all Stars.

    The other half prioritizes new interest, focus and relevant metadata changes.
    Even unmatched or already-judged Stars remain eligible for content checks.
    """
    focused, prior, state = focused or {}, prior or {}, state or {}
    now = now or now_utc()
    rows = {r["full_name"]: r for r in snapshot.get("repos", [])
            if REPO_PATTERN.fullmatch(r.get("full_name", ""))}
    relevant = {row["repo"] for row in candidates} | {row["repo"] for row in suppressed}
    def priority(name):
        row = rows[name]
        cached = prior.get(name)
        return (
            -int(valid_recent(row.get("starred_at"), now - timedelta(days=14), now)
                 and not state.get(name)),
            -int(name in focused),
            -int(bool(cached and cached.get("repo_revision") != repo_revision(row))),
            -int(name in relevant), name)
    def oldest(name):
        return state.get(name, {}).get("checked_at", "")
    selected = []
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
    results, updates = {}, {}
    for name in selected:
        row = rows[name]
        candidate = {"repo": name, "repo_id": row.get("id"), "repo_revision": repo_revision(row)}
        value = fetch_evidence(candidate, data_dir, prior.get(name))
        results[name] = value
        updates[name] = {"checked_at": now_utc().isoformat(), "status": value["status"]}
    if updates:
        directory = data_dir / "auto-opportunities"
        with write_lock(directory):
            current = watch_state(data_dir, [])
            for name, value in updates.items():
                if value["checked_at"] >= current.get(name, {}).get("checked_at", ""):
                    current[name] = value
            atomic_json(directory / "watch.json", current)
    return results


def fetch_comparison(name, base, head):
    """At most one GET and 30 bounded patches, fixed to immutable commits."""
    if not all(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{7,40}", sha)
               for sha in (base, head)) or head.startswith(base):
        return None
    try:
        result = github_get(f"repos/{name}/compare/{base}...{head}")
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
    if args.refresh:
        snapshot = refresh_snapshot(data_dir, snapshot)
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
    # Capture all baselines BEFORE any fetch can atomically replace the cache.
    prior = load_evidence(snapshot, data_dir, warnings)
    previous_failures = {name for name, row in state.items() if row.get("status") == "partial"}
    snapshot = attach_cached_revisions(snapshot, data_dir, prior, previous_failures)
    def all_candidates(source):
        return prepare(source, profiles, feedback, current, None, None,
                       args.recent_days, args.update_days, args.show_suppressed, focused)
    candidates, suppressed, eligible = all_candidates(snapshot)
    unique = (probe_watched(snapshot, suppressed, data_dir, args.evidence_limit,
                           focused=focused, candidates=candidates, prior=prior, state=state,
                           focus_limit=getattr(args, "focus_limit", 8), now=current)
              if args.fetch_evidence else {})
    failed_now = {name for name, row in unique.items() if row["status"] != "complete"}
    unavailable = (previous_failures - set(unique)) | failed_now
    cache = {**prior, **{name: row for name, row in unique.items()
                        if row["status"] == "complete"}}
    snapshot = attach_cached_revisions(snapshot, data_dir, cache, unavailable)
    candidates, suppressed, eligible = all_candidates(snapshot)
    for name in sorted(unavailable & {row.get("full_name") for row in snapshot.get("repos", [])}):
        warnings.append(f"Watched evidence incomplete: {name}; previous complete evidence retained")
    # Newly checked repositories must reach the review queue even when there
    # are many old, still-unjudged candidates with a higher lexical score.
    candidates.sort(key=lambda row: -int(row["repo"] in unique))
    all_rows = candidates
    candidates = select_candidates(candidates, args.limit, args.per_project, getattr(args, "per_repo", 3))
    from repository_profile import local_reference_snapshots
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
            observation_comparisons[name] = (fetch_comparison(name, observed_base, head)
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
                    by_base[pinned] = fetch_comparison(name, pinned, head)
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
        if value:
            candidate["upstream_evidence"] = value
            candidate["evidence_status"] = value["status"]
        elif cached:
            candidate["upstream_evidence"] = cached
            candidate["evidence_status"] = ("cached" if cached.get("repo_revision") == candidate["repo_revision"]
                                            else "stale")
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
    watch_coverage = {
        "eligible_repos": len(rows_by_name), "checked": len(unique),
        "complete": len(unique) - len(failed_now), "failed": sorted(failed_now),
        "unresolved_previous_failures": sorted(unavailable - failed_now),
        "not_checked": len(rows_by_name) - len(unique),
        "checked_repos": list(unique),
        "strategy": "at least half oldest-first across all Stars; remainder prioritizes new interest/focus/relevance",
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
            p.add_argument("--evidence-limit", type=positive, default=4)
            p.add_argument("--focus-limit", type=positive, default=8,
                           help="Maximum focused repositories fetched per run within the shared evidence budget")
            p.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return emit(envelope([], errors=[str(exc)]), 1)


if __name__ == "__main__":
    raise SystemExit(main())
