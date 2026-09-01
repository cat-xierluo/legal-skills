#!/usr/bin/env python3
"""Fail-closed preflight for value-backed multi-agent dispatch specs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any


SCHEMA = "dispatch-value-gate.v2"
REQUIRED_VALUE_FIELDS = (
    "consumer",
    "decision_or_gate_changed",
    "consume_by",
    "expiry",
    "observable_acceptance",
    "resource_owner",
)
PLACEHOLDERS = {"", "tbd", "todo", "unknown", "n/a", "na", "-", "*", "**", "none"}
DOC_KINDS = {"docs", "research"}
VALUE_KINDS = {"implementation", "reusable_verification", "merge_gate"}
PR_POLICIES = {"worker_pr", "integration_pr", "no_worker_pr"}
DOC_EXTENSIONS = {".md", ".markdown", ".rst", ".txt", ".adoc"}
DOC_DIR = "docs/"
HEAD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _parse_time(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _missing(value: Any, *, allow_none: bool = False) -> bool:
    if not isinstance(value, str):
        return True
    stripped = value.strip()
    if stripped.startswith("{{") and stripped.endswith("}}"):
        return True
    if allow_none and stripped.casefold() == "none":
        return False
    return stripped.casefold() in PLACEHOLDERS or stripped.casefold() == "none"


def is_document_path(path: str) -> bool:
    """Shared document-path semantics: preflight asset rules and postflight
    classification must use this single table to avoid drift."""
    normalized = path.strip().replace("\\", "/")
    lowered = normalized.casefold()
    if lowered.endswith(tuple(DOC_EXTENSIONS)):
        return True
    return lowered == DOC_DIR.rstrip("/") or lowered.startswith(DOC_DIR)


def _norm_identity(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _asset_list_errors(prefix: str, value: Any, field: str) -> tuple[list[str], list[str]]:
    """Validate an asset list; returns (errors, entries)."""
    errors: list[str] = []
    if value is None:
        return errors, []
    if not isinstance(value, list):
        return [f"{prefix}.{field} must be an array of paths"], []
    for index, entry in enumerate(value):
        if _missing(entry):
            errors.append(f"{prefix}.{field}[{index}] is a placeholder, not a real path")
    return errors, [str(entry).strip() for entry in value]


def _validate_task(task: dict[str, Any], prefix: str, errors: list[str]) -> None:
    for field in REQUIRED_VALUE_FIELDS:
        allow_none = field == "resource_owner" and task.get("starts_external_resources") is False
        if _missing(task.get(field), allow_none=allow_none):
            errors.append(f"{prefix}.{field} is required and cannot be a placeholder")
    starts_resources = task.get("starts_external_resources")
    if not isinstance(starts_resources, bool):
        errors.append(f"{prefix}.starts_external_resources must be boolean")
    elif starts_resources and _missing(task.get("resource_owner")):
        errors.append(f"{prefix}.resource_owner must name the external resource owner")

    kind = task.get("kind")
    if kind in DOC_KINDS:
        errors.append(
            f"{prefix}.kind '{kind}' is not a dispatchable value task; "
            "declare value_kind implementation/reusable_verification/merge_gate instead"
        )

    value_kind = task.get("value_kind")
    if value_kind not in VALUE_KINDS:
        allowed = ", ".join(sorted(VALUE_KINDS))
        errors.append(f"{prefix}.value_kind must be one of {allowed}")
        value_kind = None

    if _missing(task.get("problem_target")):
        errors.append(f"{prefix}.problem_target must name the concrete problem, module, or PR")

    if _missing(task.get("value_identity")):
        errors.append(f"{prefix}.value_identity is required for in-wave dedupe and cannot be a placeholder")

    asset_errors, engineering_assets = _asset_list_errors(prefix, task.get("engineering_assets"), "engineering_assets")
    errors.extend(asset_errors)
    doc_errors, doc_assets = _asset_list_errors(prefix, task.get("doc_assets"), "doc_assets")
    errors.extend(doc_errors)

    verification = task.get("verification_commands")
    if verification is not None and not isinstance(verification, list):
        errors.append(f"{prefix}.verification_commands must be an array of commands")
        verification = None
    for index, command in enumerate(verification or []):
        if _missing(command):
            errors.append(f"{prefix}.verification_commands[{index}] is a placeholder")

    policy = task.get("worker_pr_policy")
    if policy not in PR_POLICIES:
        allowed = ", ".join(sorted(PR_POLICIES))
        errors.append(f"{prefix}.worker_pr_policy must be one of {allowed}")
        policy = None

    if value_kind == "merge_gate":
        if engineering_assets:
            errors.append(f"{prefix}.merge_gate declares no_worker_pr and must not declare engineering_assets")
        if doc_assets:
            errors.append(f"{prefix}.merge_gate must not declare doc_assets")
        if policy in {"worker_pr", "integration_pr"}:
            errors.append(f"{prefix}.merge_gate requires worker_pr_policy no_worker_pr")
        gate_target = task.get("gate_target")
        if not isinstance(gate_target, dict):
            errors.append(f"{prefix}.merge_gate requires gate_target object with pr and head_sha")
        else:
            if _missing(gate_target.get("pr")):
                errors.append(f"{prefix}.gate_target.pr must name the PR/change under decision")
            head_sha = gate_target.get("head_sha")
            if not isinstance(head_sha, str) or not HEAD_SHA_RE.match(head_sha.strip().casefold()):
                errors.append(f"{prefix}.gate_target.head_sha must be an immutable 40-hex revision")
    else:
        if value_kind is not None:
            if policy == "no_worker_pr":
                errors.append(f"{prefix}.worker_pr_policy no_worker_pr is only valid for merge_gate")
            if policy == "integration_pr" and _missing(task.get("integration_target")):
                errors.append(
                    f"{prefix}.integration_target must name the integration PR/branch "
                    "when worker_pr_policy is integration_pr"
                )
            non_doc_assets = [path for path in engineering_assets if not is_document_path(path)]
            if not non_doc_assets:
                errors.append(
                    f"{prefix}.{value_kind} requires at least one non-document engineering_assets entry; "
                    "docs-only deliverables cannot be dispatched"
                )
            if not isinstance(verification, list) or not verification:
                errors.append(f"{prefix}.{value_kind} requires verification_commands to be declared")


def validate(spec: Any, now: datetime) -> list[str]:
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["spec must be a JSON object"]
    if spec.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must equal {SCHEMA}")

    mode = spec.get("mode")
    if mode not in {"converge", "explore"}:
        errors.append("mode must be converge or explore")

    pending = spec.get("pending_acceptance_prs")
    if not isinstance(pending, int) or isinstance(pending, bool) or pending < 0:
        errors.append("pending_acceptance_prs must be a non-negative integer")
    elif pending > 2:
        errors.append("acceptance backpressure: pending_acceptance_prs exceeds 2")

    if mode == "explore":
        authorized_by = spec.get("explore_authorized_by")
        expires_at = spec.get("explore_expires_at")
        if _missing(authorized_by):
            errors.append("explore mode requires explore_authorized_by")
        try:
            expiry_time = _parse_time(expires_at) if isinstance(expires_at, str) else None
        except ValueError as exc:
            errors.append(f"invalid explore_expires_at: {exc}")
            expiry_time = None
        if expiry_time is None:
            errors.append("explore mode requires a timezone-aware explore_expires_at")
        elif expiry_time <= now:
            errors.append("explore window is expired")

    tasks = spec.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("tasks must be a non-empty array")
        return errors

    if mode == "converge" and len(tasks) > 3:
        errors.append("converge mode permits at most 3 active workers")
    doc_count = sum(
        1 for item in tasks if isinstance(item, dict) and item.get("kind") in DOC_KINDS
    )
    if mode == "converge" and doc_count > 1:
        errors.append("converge mode permits at most 1 research/docs task")

    seen_ids: set[str] = set()
    seen_identities: dict[str, str] = {}
    seen_targets: dict[str, str] = {}
    for index, task in enumerate(tasks):
        prefix = f"tasks[{index}]"
        if not isinstance(task, dict):
            errors.append(f"{prefix} must be an object")
            continue
        task_id = task.get("task_id")
        if _missing(task_id):
            errors.append(f"{prefix}.task_id is required")
        elif task_id in seen_ids:
            errors.append(f"{prefix}.task_id duplicates {task_id}")
        else:
            seen_ids.add(task_id)
        if task.get("status") != "READY":
            errors.append(f"{prefix}.status must be READY for a new dispatch")
        if _missing(task.get("kind")):
            errors.append(f"{prefix}.kind is required")
        _validate_task(task, prefix, errors)

        value_kind = task.get("value_kind")
        problem_target = task.get("problem_target")
        if isinstance(value_kind, str) and isinstance(problem_target, str) and not _missing(problem_target):
            target_key = f"{value_kind}:{_norm_identity(problem_target)}"
            owner = seen_targets.get(target_key)
            if owner is not None:
                errors.append(
                    f"{prefix} is subsumed by {owner}: same value_kind targeting the same problem"
                )
            else:
                seen_targets[target_key] = str(task_id)

        identity = task.get("value_identity")
        if isinstance(identity, str) and not _missing(identity):
            identity_key = _norm_identity(identity)
            owner = seen_identities.get(identity_key)
            if owner is not None:
                errors.append(f"{prefix} duplicates value identity of {owner}")
            else:
                seen_identities[identity_key] = str(task_id)
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--now", help="RFC3339 evaluation time for deterministic tests")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        now = _parse_time(args.now) if args.now else datetime.now(timezone.utc)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 2
    errors = validate(spec, now)
    print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
