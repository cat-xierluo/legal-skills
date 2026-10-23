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
from project_context import (CONCEPTS, default_roots, digest, discover, match_terms, terms_for,
                           scope_conflicts, shared_evidence_revision, shared_repo_revision)

CONCEPT_VOCABULARY = sorted({alias for aliases in CONCEPTS for alias in aliases},
                           key=len, reverse=True)
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


def focus_repositories(data_dir):
    """Read the focused-repository list shared with the profile command."""
    value = read_json(data_dir / FOCUS_FILE, {"repositories": {}})
    if not isinstance(value, dict) or not isinstance(value.get("repositories"), dict):
        return {}
    return value["repositories"]


def focus_deltas(focus_rows, evidence_by_repo, prior_evidence):
    """Describe what actually changed for each focused repository.

    The baseline must be captured before evidence fetching overwrites the cache,
    otherwise every change looks identical to the freshly written record.
    """
    deltas = []
    for row in focus_rows:
        name = row["repo"]
        cached = prior_evidence.get(name)
        current = evidence_by_repo.get(name)
        delta = {
            "repo": name, "project_id": row["project_id"],
            "watch_scope": "focus", "reason": row.get("focus_reason", ""),
            "repo_revision": row.get("repo_revision"),
            "evidence_revision": row.get("evidence_revision"),
            "baseline_available": bool(cached),
            "evidence_status": row.get("evidence_status", "not_fetched"),
            "suppression": row.get("suppression"),
        }
        if current and cached:
            delta["changed"] = {
                "head_changed": current.get("head_sha") != cached.get("head_sha"),
                "release_changed": current.get("release") != cached.get("release"),
                "readme_changed": ((current.get("readme") or {}).get("blob_sha")
                                   != (cached.get("readme") or {}).get("blob_sha")),
            }
            delta["new_commits"] = [
                {"sha": item.get("sha"), "message": item.get("message")}
                for item in (current.get("commits") or [])
                if item.get("sha") and item.get("sha") != (cached.get("head_sha"))
            ][:5]
            delta["release"] = current.get("release")
        else:
            delta["changed"] = None
        deltas.append(delta)
    return deltas


def focus_candidates(snapshot, profiles, feedback, data_dir, now, limit=12):
    """One row per focused repository, with the local targets it could affect.

    A focus entry means the user explicitly watches this project, so the
    keyword filter that gates ordinary candidates must not apply to it. The
    affected local targets are listed inside the row instead of being emitted
    as one candidate per target, which would multiply the queue.
    """
    watched = focus_repositories(data_dir)
    if not watched:
        return [], []
    rows = {repo.get("full_name"): repo for repo in snapshot.get("repos", [])}
    candidates, unmatched = [], []
    for name in sorted(watched):
        repo = rows.get(name)
        if not repo:
            unmatched.append({"repo": name, "reason": "not_in_star_collection"})
            continue
        upstream = terms_for(" ".join([
            repo.get("full_name") or "", repo.get("description") or "",
            " ".join(repo.get("topics") or [])]))
        affected = []
        for profile in profiles:
            hits = match_terms(profile, {"_search_terms": upstream})
            concepts = sorted(set(profile.get("primary_terms", [])) & set(upstream))
            conflicts = scope_conflicts(profile, CONCEPT_VOCABULARY)
            if not hits and not concepts and not conflicts:
                continue
            affected.append({
                "project_id": profile["project_id"],
                "matched_terms": hits, "domain_concepts": concepts,
                "scope_status": ("conflicts_with_stated_scope" if conflicts
                                 else "no_stated_scope_conflict"),
                "scope_conflicts": conflicts,
                "target_revision": profile["target_revision"],
                "target_activity": profile["activity"],
            })
        affected.sort(key=lambda row: (-len(row["domain_concepts"]), row["project_id"]))
        affected = affected[:12]
        prior = feedback.get(("*", name), [])
        if repo.get("id") is not None:
            prior = prior + feedback.get(("*", f"id:{repo['id']}"), [])
        candidates.append({
            "candidate_id": digest([name, "focus"])[:24],
            "project_id": "*", "repo": name, "repo_id": repo.get("id"),
            "description": repo.get("description"),
            "matched_terms": sorted({term for row in affected for term in row["matched_terms"]}),
            "primary_matches": sorted({concept for row in affected for concept in row["domain_concepts"]}),
            "signals": ["focused_watch"],
            "focus_reason": (watched.get(name) or {}).get("reason", ""),
            "affected_targets": affected,
            "starred_at": repo.get("starred_at"), "pushed_at": repo.get("pushed_at"),
            "repo_revision": repo_revision(repo),
            "target_revision": digest([row["target_revision"] for row in affected]),
            "evidence_revision": repo.get("_evidence_revision"),
            "target_activity": {"status": "focus_watch", "commits": 0, "latest_at": None,
                                 "latest_commit": None},
            "suppression": None, "evidence_status": "not_fetched",
            "archived": bool(repo.get("is_archived")),
            "watch_scope": "focus",
        })
    candidates.sort(key=lambda row: row["repo"])
    return candidates[:limit], unmatched


def prepare(snapshot, profiles, feedback, now, limit=12, per_project=2,
            recent_days=14, update_days=7, show_suppressed=False):
    candidates, suppressed = [], []
    indexed_repos = [{**repo, "_search_terms": terms_for(" ".join([
        repo.get("full_name") or "", repo.get("description") or "",
        repo.get("description_zh") or "", " ".join(repo.get("topics") or []),
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
            prior = feedback.get((profile["project_id"], name), [])
            if repo.get("id") is not None:
                prior = prior + feedback.get((profile["project_id"], f"id:{repo['id']}"), [])
            state = suppression(profile, repo, prior, now)
            if state and not show_suppressed:
                suppressed.append({"project_id": profile["project_id"], "repo": name, **state})
                continue
            fingerprint = digest([profile["target_revision"], repo_revision(repo), profile["project_id"]])
            candidates.append({
                "candidate_id": fingerprint[:24], "project_id": profile["project_id"],
                "repo": name, "repo_id": repo.get("id"), "description": repo.get("description"),
                "matched_terms": hits, "signals": reasons or ["existing_collection_match"],
                "primary_matches": primary,
                "starred_at": repo.get("starred_at"), "pushed_at": repo.get("pushed_at"),
                "repo_revision": repo_revision(repo), "target_revision": profile["target_revision"],
                "evidence_revision": repo.get("_evidence_revision"),
                "target_activity": profile["activity"], "suppression": state,
                "evidence_status": "not_fetched", "archived": bool(repo.get("is_archived")),
            })
    candidates.sort(key=lambda c: (
        -min(c["target_activity"]["commits"], 10),
        -len(c["primary_matches"]), -len(c["matched_terms"]),
        -(int("recent_star" in c["signals"]) + int("upstream_activity" in c["signals"])),
        c["project_id"], c["repo"]))
    eligible = len(candidates)
    selected, counts = [], {}
    for candidate in candidates:
        project = candidate["project_id"]
        if counts.get(project, 0) >= per_project:
            continue
        selected.append(candidate)
        counts[project] = counts.get(project, 0) + 1
        if len(selected) == limit:
            break
    return selected, suppressed, eligible


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
                release = value[0] if value else None
                record["release"] = ({"tag": release.get("tag_name"), "url": release.get("html_url"),
                    "published_at": release.get("published_at"), "body": (release.get("body") or "")[:8000]} if release else None)
            else:
                record["commits"] = [{"sha": row.get("sha"), "url": row.get("html_url"),
                                      "message": row.get("commit", {}).get("message", "")[:1500]}
                                     for row in value[:5]]
                record["head_sha"] = value[0].get("sha") if value else None
        except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired, TypeError, KeyError) as exc:
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


def attach_cached_revisions(snapshot, data_dir):
    rows = []
    for repo in snapshot.get("repos", []):
        name = repo.get("full_name", "")
        cached = read_json(evidence_cache(data_dir, name)) if REPO_PATTERN.fullmatch(name) else None
        if cached and cached.get("status") == "complete":
            repo = {**repo, "_evidence_revision": evidence_revision(cached),
                    "_evidence_changed_at": cached.get("changed_at")}
        rows.append(repo)
    return {**snapshot, "repos": rows}


def probe_watched(snapshot, suppressed, data_dir, budget):
    """Rotate a bounded evidence watch before applying feedback suppression."""
    names = {s["repo"] for s in suppressed}
    directory = data_dir / "auto-opportunities"
    state = read_json(directory / "watch.json", {}) or {}
    rows = {r.get("full_name"): r for r in snapshot.get("repos", [])}
    selected = sorted(names, key=lambda n: (state.get(n, {}).get("checked_at", ""), n))[:budget]
    results, updates = {}, {}
    for name in selected:
        row = rows[name]
        candidate = {"repo": name, "repo_id": row.get("id"), "repo_revision": repo_revision(row)}
        value = fetch_evidence(candidate, data_dir, read_json(evidence_cache(data_dir, name)))
        results[name] = value
        updates[name] = {"checked_at": now_utc().isoformat(), "status": value["status"]}
    if updates:
        with write_lock(directory):
            current = read_json(directory / "watch.json", {}) or {}
            for name, value in updates.items():
                if value["checked_at"] >= current.get(name, {}).get("checked_at", ""):
                    current[name] = value
            atomic_json(directory / "watch.json", current)
    return results


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
    snapshot = attach_cached_revisions(snapshot, data_dir)
    candidates, suppressed, eligible = prepare(snapshot, profiles, feedback, current,
        args.limit, args.per_project, args.recent_days, args.update_days, args.show_suppressed)
    focus_limit = getattr(args, "focus_limit", 8)
    focus_rows, focus_unmatched = focus_candidates(snapshot, profiles, feedback, data_dir,
                                                    current, focus_limit)
    eligible += len(focus_rows)
    unique = {}
    if args.fetch_evidence and suppressed:
        # Reserve some capacity for new candidates while rotating prior decisions.
        watch_budget = args.evidence_limit if not candidates else max(1, args.evidence_limit // 2)
        unique.update(probe_watched(snapshot, suppressed, data_dir, watch_budget))
        snapshot = attach_cached_revisions(snapshot, data_dir)
        candidates, suppressed, eligible = prepare(snapshot, profiles, feedback, current,
            args.limit, args.per_project, args.recent_days, args.update_days, args.show_suppressed)
        focus_rows, focus_unmatched = focus_candidates(snapshot, profiles, feedback, data_dir,
                                                        current, focus_limit)
        eligible += len(focus_rows)
        for name, value in unique.items():
            if value["status"] != "complete":
                warnings.append(f"Watched evidence incomplete: {name}; previous complete evidence retained")
    focus_prior = {row["repo"]: read_json(evidence_cache(data_dir, row["repo"]))
                   for row in focus_rows}
    focus_ids = {(row["project_id"], row["repo"]) for row in focus_rows}
    merged_candidates = candidates + [row for row in focus_rows
                                      if (row["project_id"], row["repo"]) not in
                                      {(c["project_id"], c["repo"]) for c in candidates}]
    candidates = merged_candidates
    # Focused repositories are watched on purpose, so they get evidence budget
    # first; ordinary candidates use whatever budget is left.
    focus_names = {row["repo"] for row in focus_rows}
    ordered = ([row for row in candidates if row["repo"] in focus_names]
               + [row for row in candidates if row["repo"] not in focus_names])
    for candidate in ordered:
        name = candidate["repo"]
        if name in unique:
            candidate["upstream_evidence"] = unique[name]
            candidate["evidence_status"] = unique[name]["status"]
            if unique[name]["status"] == "complete":
                candidate["evidence_revision"] = evidence_revision(unique[name])
            continue
        cached = read_json(data_dir / "auto-opportunities/evidence" / (name.replace("/", "__") + ".json"))
        if args.fetch_evidence and len(unique) < args.evidence_limit:
            value = fetch_evidence(candidate, data_dir, cached)
            unique[name] = value
            candidate["upstream_evidence"] = value
            candidate["evidence_status"] = value["status"]
            if value["status"] == "complete":
                candidate["evidence_revision"] = evidence_revision(value)
        elif cached:
            candidate["upstream_evidence"] = cached
            same = cached.get("repo_revision") == candidate["repo_revision"]
            candidate["evidence_status"] = "cached" if same else "stale"
    focus_deltas_rows = focus_deltas(focus_rows, unique, focus_prior)
    selected_ids = {c["project_id"] for c in candidates}
    result = envelope(candidates, snapshot=snapshot, coverage={
        "projects": len(profiles), "repos": len(snapshot.get("repos", [])),
        "eligible": eligible, "returned": len(candidates), "suppressed": len(suppressed),
        "truncated": eligible > len(candidates), "evidence_fetched_repos": len(unique),
        "focused_repositories": len(focus_repositories(data_dir)),
        "focus_candidates": len(focus_rows),
        "focus_unmatched": focus_unmatched,
        "snapshot_age_hours": round((current-timestamp).total_seconds()/3600, 1) if timestamp else None,
    }, warnings=warnings, extra={
        "projects": [p for p in profiles if p["project_id"] in selected_ids],
        "suppressed": suppressed, "run_path": None,
        "focus_deltas": focus_deltas_rows,
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
            p.add_argument("--show-suppressed", action="store_true")
            p.add_argument("--refresh", action="store_true", help="Explicit GET via gh; atomically commit only a full same-account snapshot")
            p.add_argument("--fetch-evidence", action="store_true", help="Explicit bounded README/release/commit GETs")
            p.add_argument("--evidence-limit", type=positive, default=4)
            p.add_argument("--focus-limit", type=positive, default=8,
                           help="Maximum focused-repository rows per run")
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
