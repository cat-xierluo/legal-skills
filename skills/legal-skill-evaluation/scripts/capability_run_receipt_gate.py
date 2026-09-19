#!/usr/bin/env python3
"""Bind capability-suite execution states to structured, reproducible run receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from capability_suite_gate import validate as validate_suite
from evaluation_package_gate import (
    GateInputError,
    canonical_hash,
    file_hash,
    is_sha256,
    load_package,
)


CONSTRAINT_ID = "EVAL-RUN-RECEIPT-BINDING"
EVIDENCE_LEVELS = {"artifact-backed", "digest-only"}
EXECUTED_STATUSES = {"executed-pass", "executed-fail"}
OBSERVED_STATUSES = {"pass", "fail"}


def emit(payload: dict[str, Any], exit_code: int) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    raise SystemExit(exit_code)


def add_error(errors: list[dict[str, str]], code: str, message: str) -> None:
    errors.append({"constraint_id": CONSTRAINT_ID, "code": code, "message": message})


def nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def resolve_evidence_path(root: Path, raw_path: Any) -> Path:
    if not nonempty_text(raw_path):
        raise GateInputError("evidence path must be a non-empty string")
    candidate = (root / str(raw_path)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise GateInputError(f"evidence path escapes evidence root: {raw_path}") from exc
    if not candidate.is_file():
        raise GateInputError(f"evidence file does not exist: {raw_path}")
    return candidate


def validate_artifacts(
    run: dict[str, Any],
    case: dict[str, Any],
    evidence_root: Path,
    errors: list[dict[str, str]],
    label: str,
) -> int:
    artifacts = run.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        add_error(errors, "RECEIPT-031", f"{label} artifact-backed run lacks artifacts")
        return 0

    seen_roles: dict[str, set[str]] = {"input": set(), "output": set()}
    checked = 0
    for index, artifact in enumerate(artifacts):
        artifact_label = f"{label}.artifacts[{index}]"
        if not isinstance(artifact, dict):
            add_error(errors, "RECEIPT-032", f"{artifact_label} must be an object")
            continue
        role = artifact.get("role")
        if role not in {"input", "output", "supporting"}:
            add_error(errors, "RECEIPT-033", f"{artifact_label}.role is invalid")
            continue
        expected_sha = artifact.get("sha256")
        if not is_sha256(expected_sha):
            add_error(errors, "RECEIPT-034", f"{artifact_label}.sha256 is invalid")
            continue
        try:
            path = resolve_evidence_path(evidence_root, artifact.get("path"))
        except (GateInputError, OSError) as exc:
            add_error(errors, "RECEIPT-035", f"{artifact_label}: {exc}")
            continue
        actual_sha = file_hash(path)
        if actual_sha != expected_sha:
            add_error(errors, "RECEIPT-036", f"{artifact_label} hash does not match file")
            continue
        checked += 1
        if role in seen_roles:
            seen_roles[role].add(actual_sha)

    if case.get("input_sha256") not in seen_roles["input"]:
        add_error(errors, "RECEIPT-037", f"{label} lacks the suite-bound input artifact")
    if case.get("output_sha256") not in seen_roles["output"]:
        add_error(errors, "RECEIPT-038", f"{label} lacks the suite-bound output artifact")
    return checked


def validate(
    suite: dict[str, Any],
    receipts: dict[str, Any],
    *,
    suite_path: Path,
    receipts_path: Path,
    candidate_root: Path,
    evidence_root: Path,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    base_result = validate_suite(suite, candidate_root)
    for item in base_result["errors"]:
        errors.append(item)

    if receipts.get("schema_version") != "1.0":
        add_error(errors, "RECEIPT-001", "receipt schema_version must be 1.0")
    if receipts.get("suite_id") != suite.get("suite_id"):
        add_error(errors, "RECEIPT-002", "receipt suite_id does not match the suite")

    suite_candidate = suite.get("candidate") if isinstance(suite.get("candidate"), dict) else {}
    receipt_candidate = (
        receipts.get("candidate") if isinstance(receipts.get("candidate"), dict) else {}
    )
    if receipt_candidate.get("sha256") != suite_candidate.get("sha256"):
        add_error(errors, "RECEIPT-003", "receipt candidate SHA-256 does not match the suite")
    if receipt_candidate.get("hash_scope") != suite_candidate.get("hash_scope"):
        add_error(errors, "RECEIPT-004", "receipt candidate scope does not match the suite")

    runs = receipts.get("runs")
    if not isinstance(runs, list):
        runs = []
        add_error(errors, "RECEIPT-005", "runs must be an array")

    runs_by_id: dict[str, dict[str, Any]] = {}
    case_ids_in_receipts: set[str] = set()
    for index, run in enumerate(runs):
        label = f"runs[{index}]"
        if not isinstance(run, dict):
            add_error(errors, "RECEIPT-006", f"{label} must be an object")
            continue
        run_id = run.get("id")
        if not nonempty_text(run_id):
            add_error(errors, "RECEIPT-007", f"{label}.id is required")
            continue
        if run_id in runs_by_id:
            add_error(errors, "RECEIPT-008", f"duplicate run id: {run_id}")
            continue
        runs_by_id[str(run_id)] = run
        case_id = run.get("case_id")
        if not nonempty_text(case_id):
            add_error(errors, "RECEIPT-009", f"{label}.case_id is required")
        elif case_id in case_ids_in_receipts:
            add_error(errors, "RECEIPT-010", f"duplicate receipt case id: {case_id}")
        else:
            case_ids_in_receipts.add(str(case_id))

    suite_cases = suite.get("cases") if isinstance(suite.get("cases"), list) else []
    executed_cases = {
        str(case.get("id")): case
        for case in suite_cases
        if isinstance(case, dict) and case.get("execution_status") in EXECUTED_STATUSES
    }
    referenced_run_ids: set[str] = set()
    evidence_levels: dict[str, str] = {}
    artifact_count = 0

    for case_id, case in executed_cases.items():
        label = f"case[{case_id}]"
        receipt_refs = case.get("run_receipts")
        if not isinstance(receipt_refs, list) or len(receipt_refs) != 1:
            add_error(
                errors,
                "RECEIPT-011",
                f"{label} must reference exactly one structured run receipt",
            )
            continue
        receipt_ref = receipt_refs[0]
        if not isinstance(receipt_ref, dict):
            add_error(errors, "RECEIPT-012", f"{label} uses an unstructured run receipt")
            continue
        try:
            manifest_path = resolve_evidence_path(evidence_root, receipt_ref.get("manifest"))
        except (GateInputError, OSError) as exc:
            add_error(errors, "RECEIPT-013", f"{label}: {exc}")
            continue
        if manifest_path != receipts_path:
            add_error(errors, "RECEIPT-014", f"{label} points to a different receipt manifest")

        run_id = receipt_ref.get("run_id")
        if not nonempty_text(run_id) or run_id not in runs_by_id:
            add_error(errors, "RECEIPT-015", f"{label} references an unknown run")
            continue
        referenced_run_ids.add(str(run_id))
        run = runs_by_id[str(run_id)]
        record_sha = receipt_ref.get("record_sha256")
        if not is_sha256(record_sha) or record_sha != canonical_hash(run):
            add_error(errors, "RECEIPT-016", f"{label} run record hash is stale or invalid")

        if run.get("case_id") != case_id:
            add_error(errors, "RECEIPT-017", f"{label} receipt is bound to another case")
        if run.get("candidate_sha256") != suite_candidate.get("sha256"):
            add_error(errors, "RECEIPT-018", f"{label} receipt candidate is stale")
        if run.get("input_sha256") != case.get("input_sha256"):
            add_error(errors, "RECEIPT-019", f"{label} receipt input does not match the suite")
        if run.get("output_sha256") != case.get("output_sha256"):
            add_error(errors, "RECEIPT-020", f"{label} receipt output does not match the suite")
        if run.get("execution_status") != case.get("execution_status"):
            add_error(errors, "RECEIPT-021", f"{label} receipt status does not match the suite")

        runner = run.get("runner")
        if not isinstance(runner, dict):
            add_error(errors, "RECEIPT-022", f"{label} lacks runner metadata")
        else:
            if not nonempty_text(runner.get("id")) or not nonempty_text(runner.get("command")):
                add_error(errors, "RECEIPT-023", f"{label} runner metadata is incomplete")
            if not isinstance(runner.get("exit_code"), int):
                add_error(errors, "RECEIPT-024", f"{label} runner exit_code must be an integer")

        run_assertions = run.get("assertions")
        if not isinstance(run_assertions, list):
            run_assertions = []
            add_error(errors, "RECEIPT-025", f"{label} receipt assertions must be an array")
        run_assertion_map: dict[str, dict[str, Any]] = {}
        for assertion in run_assertions:
            if not isinstance(assertion, dict) or not nonempty_text(assertion.get("id")):
                add_error(errors, "RECEIPT-026", f"{label} has a malformed receipt assertion")
                continue
            assertion_id = str(assertion["id"])
            if assertion_id in run_assertion_map:
                add_error(errors, "RECEIPT-027", f"{label} duplicates assertion {assertion_id}")
            run_assertion_map[assertion_id] = assertion

        suite_assertions = case.get("assertions") if isinstance(case.get("assertions"), list) else []
        suite_assertion_map = {
            str(assertion.get("id")): assertion
            for assertion in suite_assertions
            if isinstance(assertion, dict) and nonempty_text(assertion.get("id"))
        }
        if set(run_assertion_map) != set(suite_assertion_map):
            add_error(errors, "RECEIPT-028", f"{label} receipt assertion set is incomplete")
        for assertion_id, suite_assertion in suite_assertion_map.items():
            receipt_assertion = run_assertion_map.get(assertion_id, {})
            if receipt_assertion.get("observed") not in OBSERVED_STATUSES:
                add_error(errors, "RECEIPT-029", f"{label} assertion {assertion_id} is invalid")
            elif receipt_assertion.get("observed") != suite_assertion.get("observed"):
                add_error(errors, "RECEIPT-030", f"{label} assertion {assertion_id} disagrees")
            if not nonempty_text(receipt_assertion.get("evidence")):
                add_error(errors, "RECEIPT-039", f"{label} assertion {assertion_id} lacks evidence")

        evidence_level = run.get("evidence_level")
        if evidence_level not in EVIDENCE_LEVELS:
            add_error(errors, "RECEIPT-040", f"{label} evidence_level is invalid")
        else:
            evidence_levels[case_id] = str(evidence_level)
            if evidence_level == "artifact-backed":
                artifact_count += validate_artifacts(
                    run, case, evidence_root, errors, label
                )

    orphan_runs = set(runs_by_id) - referenced_run_ids
    if orphan_runs:
        add_error(errors, "RECEIPT-041", f"unreferenced run records: {sorted(orphan_runs)}")
    missing_case_records = set(executed_cases) - case_ids_in_receipts
    if missing_case_records:
        add_error(
            errors,
            "RECEIPT-042",
            f"executed cases lack receipt records: {sorted(missing_case_records)}",
        )

    if suite.get("status") == "verified":
        weak_cases = sorted(
            case_id for case_id, level in evidence_levels.items() if level != "artifact-backed"
        )
        if weak_cases:
            add_error(
                errors,
                "RECEIPT-043",
                f"verified suite contains digest-only evidence: {weak_cases}",
            )
        domain_receipts = suite.get("domain_receipts")
        if not isinstance(domain_receipts, list) or not domain_receipts or any(
            not isinstance(item, dict) for item in domain_receipts
        ):
            add_error(
                errors,
                "RECEIPT-044",
                "verified suite requires structured domain receipt artifacts",
            )
        else:
            for index, domain_receipt in enumerate(domain_receipts):
                label = f"domain_receipts[{index}]"
                if domain_receipt.get("candidate_sha256") != suite_candidate.get("sha256"):
                    add_error(errors, "RECEIPT-045", f"{label} candidate is stale")
                if domain_receipt.get("suite_id") != suite.get("suite_id"):
                    add_error(errors, "RECEIPT-046", f"{label} suite_id does not match")
                expected_sha = domain_receipt.get("sha256")
                if not is_sha256(expected_sha):
                    add_error(errors, "RECEIPT-047", f"{label}.sha256 is invalid")
                    continue
                try:
                    path = resolve_evidence_path(evidence_root, domain_receipt.get("path"))
                except (GateInputError, OSError) as exc:
                    add_error(errors, "RECEIPT-048", f"{label}: {exc}")
                    continue
                if file_hash(path) != expected_sha:
                    add_error(errors, "RECEIPT-049", f"{label} hash does not match file")

    measurements = {
        "executed_case_count": len(executed_cases),
        "receipt_record_count": len(runs_by_id),
        "referenced_record_count": len(referenced_run_ids),
        "artifact_backed_count": sum(
            1 for level in evidence_levels.values() if level == "artifact-backed"
        ),
        "digest_only_count": sum(
            1 for level in evidence_levels.values() if level == "digest-only"
        ),
        "verified_artifact_count": artifact_count,
    }
    observables = {
        "suite_sha256": file_hash(suite_path),
        "receipt_manifest_sha256": file_hash(receipts_path),
        "candidate_sha256": suite_candidate.get("sha256"),
        "executed_case_ids": sorted(executed_cases),
        "evidence_levels": evidence_levels,
    }
    return {"errors": errors, "measurements": measurements, "observables": observables}


def command_check(args: argparse.Namespace) -> None:
    suite_path = Path(args.suite).expanduser().resolve()
    receipts_path = Path(args.receipts).expanduser().resolve()
    evidence_root = Path(args.evidence_root).expanduser().resolve()
    candidate_root = Path(args.candidate_root).expanduser().resolve()
    try:
        suite = load_package(suite_path)
        receipts = load_package(receipts_path)
        result = validate(
            suite,
            receipts,
            suite_path=suite_path,
            receipts_path=receipts_path,
            candidate_root=candidate_root,
            evidence_root=evidence_root,
        )
    except (GateInputError, OSError) as exc:
        emit({"status": "error", "message": str(exc)}, 2)

    failed = bool(result["errors"])
    if args.stability_protocol:
        artifact_sha = {
            "capability-suite": file_hash(suite_path),
            "run-receipts": file_hash(receipts_path),
        }
        measurements = {
            "receipt-binding-consistent": not failed,
            "executed-case-count": result["measurements"]["executed_case_count"],
        }
        if failed:
            emit(
                {
                    "failed_constraint_ids": [CONSTRAINT_ID],
                    "artifact_sha256": artifact_sha,
                    "measurements": {CONSTRAINT_ID: measurements},
                },
                3,
            )
        emit(
            {
                "passed_constraint_ids": [CONSTRAINT_ID],
                "artifact_sha256": artifact_sha,
                "measurements": {CONSTRAINT_ID: measurements},
                "observables": {"receipt-binding": result["observables"]},
            },
            0,
        )

    emit(
        {
            "status": "fail" if failed else "pass",
            "artifact_sha256": canonical_hash(
                {"suite": suite, "receipts": receipts}
            ),
            "passed_constraint_ids": [] if failed else [CONSTRAINT_ID],
            "failed_constraint_ids": [CONSTRAINT_ID] if failed else [],
            "measurements": result["measurements"],
            "observables": result["observables"],
            "errors": result["errors"],
        },
        3 if failed else 0,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate capability-suite execution receipts against real evidence."
    )
    parser.add_argument("--suite", required=True)
    parser.add_argument("--receipts", required=True)
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--stability-protocol", action="store_true")
    return parser


def main() -> None:
    command_check(build_parser().parse_args())


if __name__ == "__main__":
    main()
