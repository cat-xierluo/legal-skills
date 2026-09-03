#!/usr/bin/env python3
"""Classify open pull requests against one frozen worker contribution.

The helper is deliberately read-only.  It binds the audit to a local Git common
directory and one origin remote, then asks ``gh`` for open PR metadata.  Its
single JSON document is intended to be consumed by pm-closeout.sh.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from urllib.parse import urlsplit
from typing import Any


SCHEMA = "pr-audit.v1"
HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")


class AuditError(RuntimeError):
    pass


def redact_sensitive(text: str) -> str:
    """Redact URL userinfo/query credentials before anything reaches stderr."""
    value = re.sub(
        r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s]+@",
        r"\1***@",
        text,
    )
    value = re.sub(
        r"(?i)([?&](?:access_token|token|password|secret)=)[^&\s]+",
        r"\1***",
        value,
    )
    value = re.sub(r"(?i)\b[^\s/@:]+:[^\s@]+@([^\s/:]+)", r"***@\1", value)
    return value


def run(argv: list[str], *, cwd: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    label = " ".join(argv[:3])
    try:
        proc = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, shell=False)
    except FileNotFoundError as exc:
        raise AuditError(f"dependency_missing command={argv[0]}") from exc
    except OSError as exc:
        raise AuditError(f"command_start_failed command={label} error={redact_sensitive(str(exc))}") from exc
    if check and proc.returncode != 0:
        detail = redact_sensitive((proc.stderr or proc.stdout).strip())
        raise AuditError(f"command_failed command={label} exit={proc.returncode} detail={detail or 'none'}")
    return proc


def git(repo: str, *args: str) -> str:
    return run(["git", *args], cwd=repo).stdout.strip()


def canonical_remote(url: str) -> str:
    """Return credential-free HOST/OWNER/REPO for gh --repo."""
    value = url.strip().rstrip("/")
    host = ""
    path = ""
    if re.match(r"^[^/@:]+@[^/:]+:.+$", value):
        authority, path = value.split(":", 1)
        host = authority.split("@", 1)[1]
    elif "://" in value:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        path = parsed.path.lstrip("/")
    else:
        # Deterministic throwaway/local remotes are supported without exposing
        # their filesystem path in JSON or gh argv.
        leaf = os.path.basename(value)
        if leaf.endswith(".git"):
            leaf = leaf[:-4]
        if not leaf:
            raise AuditError("origin remote identity is empty")
        return f"local/repository/{leaf}"
    if path.endswith(".git"):
        path = path[:-4]
    path = path.strip("/")
    if not host or len(path.split("/")) < 2:
        raise AuditError("origin must identify a credential-free GitHub/GHE host and owner/repo")
    return f"{host}/{path}"


def fingerprint(raw: str) -> str:
    # Normalize only Git's transport/object-id decoration.  Content lines,
    # including trailing spaces, are preserved byte-for-byte.
    kept: list[str] = []
    for line in raw.splitlines(keepends=True):
        kept.append(re.sub(r"^index [0-9a-f]+\.\.[0-9a-f]+", "index <oids>", line))
    return hashlib.sha256("".join(kept).encode("utf-8")).hexdigest()


def ownership_evidence(row: dict[str, Any], task_id: str, agent_id: str) -> dict[str, Any]:
    body = row.get("body") if isinstance(row.get("body"), str) else ""

    def trailers(label: str) -> list[str]:
        return [value.strip() for value in re.findall(rf"(?mi)^{label}:[ \t]*(.+?)[ \t]*$", body)]

    task_trailers = trailers("Task")
    agent_trailers = trailers("Agent")
    task_match = not task_id or task_trailers == [task_id]
    agent_match = not agent_id or agent_trailers == [agent_id]
    return {
        "task_id": task_id,
        "agent_id": agent_id,
        "task_trailers": task_trailers,
        "agent_trailers": agent_trailers,
        "task_match": task_match,
        "agent_match": agent_match,
        "match": task_match and agent_match,
    }


def row_receipt(
    row: dict[str, Any],
    *,
    classification: str,
    reasons: list[str],
    ownership: dict[str, Any],
    diff_fp: str | None,
) -> dict[str, Any]:
    checks = row.get("statusCheckRollup")
    if isinstance(checks, list):
        checks = sorted(checks, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
    raw_head_owner = row.get("headRepositoryOwner")
    if isinstance(raw_head_owner, dict):
        head_owner = raw_head_owner.get("login") or raw_head_owner.get("name")
    else:
        head_owner = raw_head_owner
    return {
        "number": row.get("number"),
        "url": row.get("url"),
        "title": row.get("title"),
        "base_ref": row.get("baseRefName"),
        "base_sha": row.get("baseRefOid"),
        "head_ref": row.get("headRefName"),
        "head_sha": row.get("headRefOid"),
        "head_repository_owner": head_owner,
        "is_cross_repository": row.get("isCrossRepository"),
        "classification": classification,
        "reasons": reasons,
        "ownership": ownership,
        "diff_fingerprint": diff_fp,
        "checks_review_fingerprint": hashlib.sha256(
            json.dumps(
                {
                    "reviewDecision": row.get("reviewDecision"),
                    "statusCheckRollup": checks,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base-ref", default="main")
    parser.add_argument("--head-ref", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--task-id", default="")
    parser.add_argument("--agent-id", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not HEX40.fullmatch(args.head_sha):
        raise AuditError("--head-sha must be a full 40-hex commit id")

    repo = os.path.realpath(args.repo)
    top = os.path.realpath(git(repo, "rev-parse", "--show-toplevel"))
    common_raw = git(repo, "rev-parse", "--git-common-dir")
    common = os.path.realpath(common_raw if os.path.isabs(common_raw) else os.path.join(top, common_raw))
    resolved_head = git(repo, "rev-parse", "--verify", f"{args.head_sha}^{{commit}}")
    if resolved_head.lower() != args.head_sha.lower():
        raise AuditError("--head-sha does not resolve to the frozen commit")
    current_head = git(repo, "rev-parse", "--verify", "HEAD^{commit}")
    if current_head != resolved_head:
        raise AuditError(f"frozen head is not the worktree HEAD: expected={resolved_head} actual={current_head}")
    current_branch = git(repo, "branch", "--show-current")
    if current_branch != args.head_ref:
        raise AuditError(f"head ref is not the worktree branch: expected={args.head_ref} actual={current_branch}")

    run(["git", "fetch", "origin", "--quiet"], cwd=repo)
    base_tip = git(repo, "rev-parse", "--verify", f"origin/{args.base_ref}^{{commit}}")
    base_commit = git(repo, "merge-base", resolved_head, base_tip)
    local_diff = run(
        ["git", "diff", "--binary", "--full-index", "--no-ext-diff", base_commit, resolved_head],
        cwd=repo,
    ).stdout
    expected_fp = fingerprint(local_diff)
    remote_url = git(repo, "remote", "get-url", "origin")
    remote = canonical_remote(remote_url)
    if not remote:
        raise AuditError("origin remote identity is empty")

    fields = "number,url,baseRefName,baseRefOid,headRefName,headRefOid,headRepositoryOwner,isCrossRepository,title,body,reviewDecision,statusCheckRollup"
    listed = run(
        ["gh", "pr", "list", "--repo", remote, "--state", "open", "--limit", "101", "--json", fields],
        cwd=repo,
    )
    try:
        rows = json.loads(listed.stdout)
    except json.JSONDecodeError as exc:
        raise AuditError(f"gh pr list returned invalid JSON: {exc}") from exc
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise AuditError("gh pr list must return a JSON array of objects")

    truncated = len(rows) >= 101
    expected_owner = remote.split("/")[-2]
    buckets: dict[str, list[dict[str, Any]]] = {"exact": [], "suspected": [], "unrelated": []}
    for row in rows:
        base_match = row.get("baseRefName") == args.base_ref
        base_sha_match = str(row.get("baseRefOid") or "").lower() == base_tip.lower()
        head_match = row.get("headRefName") == args.head_ref
        sha_match = str(row.get("headRefOid") or "").lower() == resolved_head.lower()
        raw_head_owner = row.get("headRepositoryOwner")
        if isinstance(raw_head_owner, dict):
            head_owner = raw_head_owner.get("login") or raw_head_owner.get("name")
        else:
            head_owner = raw_head_owner
        repository_match = head_owner == expected_owner and row.get("isCrossRepository") is False
        owner = ownership_evidence(row, args.task_id, args.agent_id)
        pr_fp: str | None = None
        same_content = False
        diff_unknown = False
        if base_match or head_match:
            number = row.get("number")
            if isinstance(number, int) or (isinstance(number, str) and number.isdigit()):
                diff_proc = run(
                    ["gh", "pr", "diff", str(number), "--repo", remote],
                    cwd=repo,
                    check=False,
                )
                if diff_proc.returncode == 0:
                    pr_fp = fingerprint(diff_proc.stdout)
                    same_content = pr_fp == expected_fp
                else:
                    diff_unknown = True

        reasons: list[str] = []
        if base_match and base_sha_match and head_match and sha_match and repository_match and owner["match"] and same_content and not diff_unknown:
            classification = "exact"
            reasons.append("base_ref_oid_head_ref_oid_repository_task_agent_match")
        elif head_match or (base_match and same_content) or diff_unknown or owner["task_match"] and owner["agent_match"] and (args.task_id or args.agent_id):
            classification = "suspected"
            if base_match and head_match and not sha_match:
                reasons.append("same_head_different_sha")
            if base_match and same_content and not head_match:
                reasons.append("same_content_different_head")
            if diff_unknown:
                reasons.append("diff_unknown")
            if head_match and not base_match:
                reasons.append("same_head_different_base")
            if base_match and not base_sha_match:
                reasons.append("same_base_ref_different_base_sha")
            if base_match and head_match and sha_match and pr_fp is not None and not same_content:
                reasons.append("pr_diff_mismatch")
            if base_match and head_match and sha_match and not owner["match"]:
                reasons.append("ownership_mismatch")
            if base_match and head_match and sha_match and not repository_match:
                reasons.append("head_repository_mismatch_or_cross_repository")
            if owner["match"] and (args.task_id or args.agent_id):
                reasons.append("ownership_related")
            if not reasons:
                reasons.append("related_but_not_exact")
        else:
            classification = "unrelated"
            reasons.append("no_exact_or_suspected_relation")
        buckets[classification].append(
            row_receipt(
                row,
                classification=classification,
                reasons=reasons,
                ownership=owner,
                diff_fp=pr_fp,
            )
        )

    exact_count = len(buckets["exact"])
    suspected_count = len(buckets["suspected"])
    if truncated:
        decision = "ambiguous"
    elif exact_count == 1 and suspected_count == 0:
        decision = "adopt"
    elif exact_count == 0 and suspected_count == 0:
        decision = "create"
    else:
        decision = "ambiguous"

    result = {
        "schema_version": SCHEMA,
        "repository": {"top": top, "common_dir": common, "remote": remote},
        "expected": {
            "base_ref": args.base_ref,
            "base_tip": base_tip,
            "base_commit": base_commit,
            "head_ref": args.head_ref,
            "head_sha": resolved_head,
            "task_id": args.task_id,
            "agent_id": args.agent_id,
            "head_repository_owner": expected_owner,
            "is_cross_repository": False,
            "diff_fingerprint": expected_fp,
        },
        "counts": {name: len(values) for name, values in buckets.items()},
        "candidate_set_truncated": truncated,
        "decision": decision,
        **buckets,
    }
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditError as exc:
        print(f"PR_AUDIT_ERROR: {redact_sensitive(str(exc))}", file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:  # Defensive CLI boundary: never leak traceback/credentials.
        print(f"PR_AUDIT_ERROR: unexpected_error detail={redact_sensitive(str(exc))}", file=sys.stderr)
        raise SystemExit(2)
