#!/usr/bin/env python3
"""Fail-closed gate for role-separated implementation/review closeout contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "review-acceptance-gate.v1"
HEAD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PLACEHOLDERS = {"", "tbd", "todo", "unknown", "n/a", "na", "-", "*", "**", "none"}
IDENTITY_FIELDS = ("dispatch_id", "session_id")
EXCEPTION_KINDS = ("pm_implementation", "pm_deep_review")
EXCEPTION_REASON_CODES = (
    "worker_failure",
    "conflicting_verdicts",
    "security_or_high_risk_evidence",
    "control_plane_recovery",
)


def _missing(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    stripped = value.strip()
    if stripped.startswith("{{") and stripped.endswith("}}"):
        return True
    return stripped.casefold() in PLACEHOLDERS


def _norm_identity(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _head(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    return normalized if HEAD_SHA_RE.match(normalized) else None


def validate(contract: Any) -> tuple[list[str], dict[str, Any]]:
    """Return (errors, report); report marks whether the closeout is ordinary
    role-separated delivery or a declared PM intervention."""
    errors: list[str] = []
    report: dict[str, Any] = {"ordinary_delivery": True, "role_exception": None}
    if not isinstance(contract, dict):
        return ["contract must be a JSON object"], report
    if contract.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must equal {SCHEMA}")

    delivery_head = _head(contract.get("delivery_head"))
    if delivery_head is None:
        errors.append("delivery_head must be an immutable 40-hex commit")
    reviewed_head = _head(contract.get("reviewed_head"))
    if reviewed_head is None:
        errors.append("reviewed_head must be an immutable 40-hex commit")
    elif delivery_head is not None and reviewed_head != delivery_head:
        errors.append(
            "reviewed_head must equal delivery_head: the reviewer attests the same "
            "immutable commit that is delivered"
        )

    identities: dict[str, dict[str, str]] = {}
    for role in ("implementation", "reviewer"):
        section = contract.get(role)
        if not isinstance(section, dict):
            errors.append(f"{role} must be an object with dispatch_id and session_id")
            continue
        for field in IDENTITY_FIELDS:
            value = section.get(field)
            if _missing(value):
                errors.append(f"{role}.{field} is required and cannot be a placeholder")
            else:
                identities.setdefault(role, {})[field] = _norm_identity(value)

    implementation = identities.get("implementation", {})
    reviewer = identities.get("reviewer", {})
    for field in IDENTITY_FIELDS:
        if field in implementation and field in reviewer:
            if implementation[field] == reviewer[field]:
                errors.append(
                    f"self-review: implementation and reviewer must carry distinct {field} identities"
                )

    if contract.get("verdict") != "ACCEPT":
        errors.append('verdict must be the literal "ACCEPT" from the independent reviewer')

    evidence = contract.get("verification_evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append(
            "verification_evidence must be a non-empty array of {command, exit_code} records; "
            "prose-only narratives are rejected"
        )
        evidence = []
    for index, entry in enumerate(evidence):
        prefix = f"verification_evidence[{index}]"
        if not isinstance(entry, dict):
            errors.append(
                f"{prefix} must be a record with command and exit_code, not a prose narrative"
            )
            continue
        if _missing(entry.get("command")):
            errors.append(f"{prefix}.command is required and cannot be a placeholder")
        exit_code = entry.get("exit_code")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            errors.append(f"{prefix}.exit_code must record the executed integer exit code")
        elif exit_code != 0:
            errors.append(
                f"{prefix}.exit_code is {exit_code}; every declared verification command must have passed"
            )

    if _missing(contract.get("review_consumer")):
        errors.append("review_consumer is required: name who consumes this review and cannot be a placeholder")
    if _missing(contract.get("review_expiry")):
        errors.append("review_expiry is required: name the expiry disposition and cannot be a placeholder")

    findings = contract.get("blocking_findings")
    if not isinstance(findings, list):
        errors.append("blocking_findings must be an array (empty when nothing is unresolved)")
    elif findings:
        errors.append(
            f"unresolved blocking findings remain: resolve all {len(findings)} entries before closeout"
        )

    exception = contract.get("role_exception")
    if exception is not None:
        report["ordinary_delivery"] = False
        if not isinstance(exception, dict):
            errors.append("role_exception must be an object or null")
        else:
            kind = exception.get("kind")
            if kind not in EXCEPTION_KINDS:
                errors.append("role_exception.kind must be one of " + ", ".join(EXCEPTION_KINDS))
            else:
                report["role_exception"] = kind
            if exception.get("reason_code") not in EXCEPTION_REASON_CODES:
                errors.append(
                    "role_exception.reason_code must be an enumerated reason: "
                    + ", ".join(EXCEPTION_REASON_CODES)
                )
            if _missing(exception.get("reason")):
                errors.append("role_exception.reason must be a non-empty enumerated justification")
            if _missing(exception.get("authorized_by")):
                errors.append(
                    "role_exception.authorized_by must name a non-empty authorization source"
                )
    return errors, report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        contract = json.loads(args.contract.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"ok": False, "errors": [str(exc)], "ordinary_delivery": True, "role_exception": None},
                ensure_ascii=False,
            )
        )
        return 2
    errors, report = validate(contract)
    print(json.dumps({"ok": not errors, "errors": errors, **report}, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
