#!/usr/bin/env python3
"""Fail-closed preflight for value-backed multi-agent dispatch specs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


SCHEMA = "dispatch-value-gate.v1"
REQUIRED_VALUE_FIELDS = (
    "consumer",
    "decision_or_gate_changed",
    "consume_by",
    "expiry",
    "observable_acceptance",
    "resource_owner",
)
PLACEHOLDERS = {"", "tbd", "todo", "unknown", "n/a", "na", "-"}
DOC_KINDS = {"docs", "research"}
DOC_TRANSITIONS = {
    "draft_to_ready",
    "decision_closed",
    "executable_gate_consumed",
}


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
        if kind in DOC_KINDS and task.get("state_transition") not in DOC_TRANSITIONS:
            allowed = ", ".join(sorted(DOC_TRANSITIONS))
            errors.append(f"{prefix}.state_transition must be one of {allowed} for {kind}")
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
