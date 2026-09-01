#!/usr/bin/env python3
"""Fail-closed postflight: prove a dispatched worker's diff matches its value contract.

Reads the same spec consumed by dispatch-value-gate.py, inspects a supplied
Git base/head diff or a patch file, and requires verification evidence.
A zero diff is only valid for a declared merge_gate with a concrete decision.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from typing import Any


EXIT_REJECTED = 2
HEAD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _load_gate():
    gate_path = Path(__file__).resolve().parent / "dispatch-value-gate.py"
    spec_loader = importlib.util.spec_from_file_location("dispatch_value_gate", gate_path)
    module = importlib.util.module_from_spec(spec_loader)
    spec_loader.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _load_json(path: Path, label: str, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label} is unreadable or invalid JSON: {exc}")
        return None


def _resolve_git_head(repo: str, head: str, errors: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", repo, "rev-parse", "--verify", f"{head}^{{commit}}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"git rev-parse failed: {exc}")
        return None
    if result.returncode != 0:
        errors.append(f"head does not resolve to a commit: {head}")
        return None
    resolved = result.stdout.strip().casefold()
    if not HEAD_SHA_RE.match(resolved):
        errors.append(f"resolved head is not a 40-hex commit: {head}")
        return None
    return resolved


def _git_changed_paths(repo: str, base: str, head: str, errors: list[str]) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", repo, "diff", "--name-only", base, head],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"git diff failed: {exc}")
        return []
    if result.returncode != 0:
        errors.append(f"git diff failed: {result.stderr.strip() or result.stdout.strip()}")
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _patch_changed_paths(patch: str, errors: list[str]) -> list[str]:
    if "diff --git " not in patch:
        errors.append("patch file contains no 'diff --git' headers")
        return []
    paths: list[str] = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            marker = " b/"
            position = line.rfind(marker)
            if position == -1:
                errors.append(f"unparsable diff header: {line}")
                continue
            paths.append(line[position + len(marker):].strip())
    return paths


def _matches(asset: str, path: str) -> bool:
    normalized = asset.strip().rstrip("/")
    return path == normalized or path.startswith(normalized + "/")


def _evidence_errors(
    task: dict[str, Any],
    evidence: dict[str, Any],
    resolved_head: str | None,
    errors: list[str],
) -> None:
    # Head binding applies to every accepted postflight: the evidence must pin
    # an immutable 40-hex revision that equals the resolved delivery head.
    verified_head = evidence.get("verified_head")
    if not isinstance(verified_head, str) or not HEAD_SHA_RE.match(verified_head.strip().casefold()):
        errors.append("evidence must record an immutable 40-hex verified_head")
        verified_head = None
    elif resolved_head is not None and verified_head.strip().casefold() != resolved_head:
        errors.append("evidence verified_head does not match the resolved delivery head")

    if task.get("value_kind") == "merge_gate":
        gate_head = str((task.get("gate_target") or {}).get("head_sha", "")).strip().casefold()
        if resolved_head is not None and resolved_head != gate_head:
            errors.append("delivery head does not match gate_target.head_sha")
        decision = evidence.get("decision")
        if decision not in {"accept", "reject"}:
            errors.append("merge gate evidence must record decision accept or reject")

    required = task.get("verification_commands") or []
    if task.get("value_kind") == "merge_gate" and not required:
        return
    executed = evidence.get("executed")
    if not isinstance(executed, list) or not executed:
        errors.append("verification evidence missing: executed[] with command/exit_code is required")
        return
    for command in required:
        wanted = str(command).strip()
        match = next(
            (item for item in executed if isinstance(item, dict) and str(item.get("command", "")).strip() == wanted),
            None,
        )
        if match is None:
            errors.append(f"verification evidence missing for command: {wanted}")
        elif match.get("exit_code") != 0:
            errors.append(f"verification command failed (exit_code={match.get('exit_code')}): {wanted}")


def _postflight(
    task: dict[str, Any],
    changed: list[str],
    is_document_path,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    value_kind = task["value_kind"]
    engineering = [str(item).strip() for item in (task.get("engineering_assets") or [])]
    doc_assets = [str(item).strip() for item in (task.get("doc_assets") or [])]

    report: dict[str, Any] = {
        "task_id": task.get("task_id"),
        "value_kind": value_kind,
        "changed_paths": changed,
        "matched_engineering_assets": [],
        "matched_doc_assets": [],
        "outside_contract_paths": [],
    }

    if value_kind == "merge_gate":
        if changed:
            errors.append(
                "declared no_worker_pr merge gate must produce a zero diff; "
                f"{len(changed)} changed path(s) found"
            )
        return errors, report

    if not changed:
        errors.append(
            "zero diff: only an explicitly declared merge_gate may deliver no changes; "
            "generic zero-diff review is not engineering value"
        )
        return errors, report

    for path in changed:
        # A documentation path can never satisfy matched_engineering_assets,
        # even when it sits below a declared engineering directory; it may
        # only count as accompanying documentation via doc_assets.
        if is_document_path(path):
            engineering_hit = None
        else:
            engineering_hit = next((asset for asset in engineering if _matches(asset, path)), None)
        doc_hit = next((asset for asset in doc_assets if _matches(asset, path)), None)
        if engineering_hit is not None:
            if engineering_hit not in report["matched_engineering_assets"]:
                report["matched_engineering_assets"].append(engineering_hit)
        elif doc_hit is not None:
            if doc_hit not in report["matched_doc_assets"]:
                report["matched_doc_assets"].append(doc_hit)
        else:
            report["outside_contract_paths"].append(path)
    if report["outside_contract_paths"]:
        errors.append(
            "changed paths outside declared engineering_assets/doc_assets: "
            + ", ".join(report["outside_contract_paths"])
        )
    if not report["matched_engineering_assets"]:
        errors.append(
            "no declared non-document engineering asset actually changed; "
            "a documentation-only diff is not implementation value"
        )
    return errors, report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True, help="dispatch-value-gate spec JSON")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--repo", help="Git repository for base/head diff inspection")
    parser.add_argument("--base", help="base revision (with --repo/--head)")
    parser.add_argument("--head", help="head revision (with --repo/--base)")
    parser.add_argument("--diff", type=Path, help="unified diff / patch file to inspect instead")
    parser.add_argument(
        "--delivery-head",
        help="immutable 40-hex delivery revision the patch was produced against (patch mode)",
    )
    parser.add_argument("--evidence", type=Path, required=True, help="verification evidence JSON")
    return parser


def main() -> int:
    args = _parser().parse_args()
    errors: list[str] = []

    diff_sources = [bool(args.repo), bool(args.base), bool(args.head)]
    if any(diff_sources) and not all(diff_sources):
        errors.append("--repo, --base and --head must be supplied together")
    if args.diff and any(diff_sources):
        errors.append("use either --diff or --repo/--base/--head, not both")
    if not args.diff and not all(diff_sources):
        errors.append("a diff source is required: --diff or --repo/--base/--head")

    spec_data = _load_json(args.spec, "spec", errors)
    evidence_data = _load_json(args.evidence, "evidence", errors)
    gate = _load_gate()
    task: dict[str, Any] | None = None
    if isinstance(spec_data, dict):
        errors.extend(gate.validate(spec_data, datetime.now(timezone.utc)))
        tasks = spec_data.get("tasks")
        if isinstance(tasks, list):
            task = next((item for item in tasks if isinstance(item, dict) and item.get("task_id") == args.task_id), None)
        if task is None:
            errors.append(f"task_id '{args.task_id}' not found in spec tasks")

    changed: list[str] = []
    resolved_head: str | None = None
    diff_source = None
    if args.diff is not None:
        if args.delivery_head is None:
            errors.append("--delivery-head (immutable 40-hex delivery revision) is required in patch mode")
        elif not HEAD_SHA_RE.match(args.delivery_head.strip().casefold()):
            errors.append("--delivery-head must be an immutable 40-hex revision")
        else:
            resolved_head = args.delivery_head.strip().casefold()
        try:
            changed = _patch_changed_paths(args.diff.read_text(encoding="utf-8", errors="replace"), errors)
            diff_source = f"patch:{args.diff}"
        except OSError as exc:
            errors.append(f"patch unreadable: {exc}")
    elif args.repo is not None and all(diff_sources):
        resolved_head = _resolve_git_head(args.repo, args.head, errors)
        changed = _git_changed_paths(args.repo, args.base, args.head, errors)
        diff_source = f"git:{args.repo} {args.base}..{args.head}"

    report: dict[str, Any] = {
        "task_id": args.task_id,
        "diff_source": diff_source,
        "delivery_head": resolved_head,
        "changed_paths": changed,
    }
    if task is not None and task.get("value_kind") in {"implementation", "reusable_verification", "merge_gate"}:
        gate_errors, gate_report = _postflight(task, changed, gate.is_document_path)
        errors.extend(gate_errors)
        report.update(gate_report)
        if isinstance(evidence_data, dict):
            _evidence_errors(task, evidence_data, resolved_head, errors)
            report["verification"] = {
                "required": len(task.get("verification_commands") or []),
                "evidence_commands": len(evidence_data.get("executed") or []),
            }
            if task["value_kind"] == "merge_gate":
                report["decision"] = evidence_data.get("decision")
                report["decision_consumer"] = task.get("consumer")
                report["gate_target"] = task.get("gate_target")

    ok = not errors
    print(json.dumps({"ok": ok, "errors": errors, "report": report}, ensure_ascii=False))
    return 0 if ok else EXIT_REJECTED


if __name__ == "__main__":
    raise SystemExit(main())
