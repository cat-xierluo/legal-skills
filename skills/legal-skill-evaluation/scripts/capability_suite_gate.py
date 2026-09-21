#!/usr/bin/env python3
"""Validate a layered legal capability suite without executing its cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evaluation_package_gate import (
    GateInputError,
    candidate_snapshot,
    canonical_hash,
    file_hash,
    is_sha256,
    load_package,
)


CONSTRAINT_ID = "EVAL-SUITE-STATE"
CASE_TYPES = {"familiar", "peer-unfamiliar", "missing-context", "micro"}
REQUIRED_CASE_TYPES = {"familiar", "peer-unfamiliar", "missing-context"}
# 命令式（合同/命令型）suite 必填 tier 集合（原硬编码约束，保持向后兼容）。
TIERS = {"full-e2e", "dynamic-micro", "static-contract"}
# 指令型（材料+LLM 运行）suite 可选 tier，不参与命令式必填校验。
INSTRUCTION_TIERS = {"material-driven"}
SOURCE_KINDS = {"current-run", "current-run-derived", "historical-derived", "reference-derived", "existing-real-run", "not-run"}
# 合法观测状态：pass/fail 为硬判定，warn 为语义 gate 的软提示（如条号来源无法机械区分），not-run 为未执行。
OBSERVED_STATUSES = {"pass", "fail", "warn", "not-run"}
CASE_BINDINGS = {"current-candidate", "historical-unbound"}
EXECUTION_STATUSES = {"executed-pass", "executed-fail", "not-run"}
SUITE_STATUSES = {"prepared-not-verified", "regression-detected", "verified"}
FORMAL_MARKERS = {"DOMAIN_VERIFIED", "NOT_VERIFIED"}
# 命令式（合同）suite 的必填能力集合（原硬编码约束，保持向后兼容）。
REQUIRED_CAPABILITIES_COMMAND = {
    "intake",
    "role-objective",
    "service-contract",
    "ip-contract",
    "output-integrity",
    "human-review",
    "regression-closure",
}
# 指令型（材料+LLM 运行）suite：不强制特定能力集合，由 bundle 自带 capabilities 表达。
REQUIRED_CAPABILITIES = REQUIRED_CAPABILITIES_COMMAND
MIN_CASES = 20
MAX_CASES = 50
# 指令型 suite 的宽松下限（真实运行成本高，3 例即可探路）。
MIN_CASES_INSTRUCTION = 3


def emit(payload: dict[str, Any], exit_code: int) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    raise SystemExit(exit_code)


def add_error(errors: list[dict[str, str]], code: str, message: str) -> None:
    errors.append({"constraint_id": CONSTRAINT_ID, "code": code, "message": message})


def nonempty_strings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def valid_run_receipts(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if isinstance(item, str) and item.strip():
            continue
        if not isinstance(item, dict):
            return False
        if not all(
            isinstance(item.get(key), str) and item[key].strip()
            for key in ("manifest", "run_id", "record_sha256")
        ):
            return False
        if not is_sha256(item["record_sha256"]):
            return False
    return True


def valid_domain_receipts(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if isinstance(item, str) and item.strip():
            continue
        if not isinstance(item, dict):
            return False
        if not all(
            isinstance(item.get(key), str) and item[key].strip()
            for key in ("path", "sha256", "candidate_sha256", "suite_id")
        ):
            return False
        if not is_sha256(item["sha256"]) or not is_sha256(item["candidate_sha256"]):
            return False
    return True


def validate(suite: dict[str, Any], candidate_root: Path | None) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    if suite.get("schema_version") != "1.0":
        add_error(errors, "SUITE-001", "schema_version must be 1.0")
    if not isinstance(suite.get("suite_id"), str) or not suite["suite_id"].strip():
        add_error(errors, "SUITE-050", "suite_id is required")

    # 接入模式：command-type（合同/命令式，原约束）或 instruction-type（材料+LLM 运行）。
    # 默认 command-type，保持对既有合同 bundle 的完全向后兼容。
    mode = suite.get("mode", "command-type")
    if mode not in {"command-type", "instruction-type"}:
        add_error(errors, "SUITE-051", f"mode must be command-type or instruction-type, got {mode!r}")
    is_instruction = mode == "instruction-type"

    candidate = suite.get("candidate")
    if not isinstance(candidate, dict):
        candidate = {}
        add_error(errors, "SUITE-002", "candidate must be an object")
    candidate_sha = candidate.get("sha256")
    candidate_scope = candidate.get("hash_scope")
    if not is_sha256(candidate_sha):
        add_error(errors, "SUITE-003", "candidate.sha256 must be a SHA-256 value")
    if candidate_scope not in {"full-directory", "git-tracked"}:
        add_error(errors, "SUITE-004", "candidate.hash_scope is invalid")

    recomputed_sha: str | None = None
    recomputed_file_count: int | None = None
    if candidate_root is not None and candidate_scope in {"full-directory", "git-tracked"}:
        try:
            snapshot = candidate_snapshot(candidate_root, candidate_scope)
            recomputed_sha = snapshot["candidate_sha256"]
            recomputed_file_count = snapshot["file_count"]
        except (GateInputError, OSError) as exc:
            add_error(errors, "SUITE-005", f"cannot recompute candidate: {exc}")
        if recomputed_sha and is_sha256(candidate_sha) and recomputed_sha != candidate_sha:
            add_error(errors, "SUITE-006", "candidate snapshot does not match the suite")

    cases = suite.get("cases")
    if not isinstance(cases, list):
        cases = []
        add_error(errors, "SUITE-007", "cases must be an array")
    min_cases = MIN_CASES_INSTRUCTION if is_instruction else MIN_CASES
    if not min_cases <= len(cases) <= MAX_CASES:
        bound = f"{min_cases} to {MAX_CASES}" if is_instruction else "20 to 50"
        add_error(errors, "SUITE-008", f"suite must contain {bound} cases")

    case_ids: set[str] = set()
    assertion_ids: set[str] = set()
    observed_case_types: set[str] = set()
    observed_tiers: set[str] = set()
    observed_capabilities: set[str] = set()
    executed_pass_count = 0
    executed_fail_count = 0
    not_run_count = 0
    current_bound_count = 0
    historical_unbound_count = 0

    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            add_error(errors, "SUITE-009", f"{label} must be an object")
            continue

        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            add_error(errors, "SUITE-010", f"{label}.id is required")
        elif case_id in case_ids:
            add_error(errors, "SUITE-011", f"duplicate case id: {case_id}")
        else:
            case_ids.add(case_id)
        if not isinstance(case.get("title"), str) or not case["title"].strip():
            add_error(errors, "SUITE-051", f"{label}.title is required")

        case_type = case.get("case_type")
        if case_type not in CASE_TYPES:
            add_error(errors, "SUITE-012", f"{label}.case_type is invalid")
        else:
            observed_case_types.add(case_type)

        tier = case.get("tier")
        # 指令型 suite 允许 material-driven 等专用 tier；命令式仅限 TIERS。
        allowed_tiers = TIERS | (INSTRUCTION_TIERS if is_instruction else set())
        if tier not in allowed_tiers:
            add_error(errors, "SUITE-013", f"{label}.tier is invalid")
        else:
            observed_tiers.add(tier)

        if case.get("source_kind") not in SOURCE_KINDS:
            add_error(errors, "SUITE-014", f"{label}.source_kind is invalid")

        capabilities = case.get("capabilities")
        if not nonempty_strings(capabilities):
            add_error(errors, "SUITE-015", f"{label}.capabilities must be non-empty")
        else:
            observed_capabilities.update(capabilities)

        if not is_instruction:
            if not isinstance(case.get("fixture_spec"), str) or not case["fixture_spec"].strip():
                add_error(errors, "SUITE-016", f"{label}.fixture_spec is required")
        if not nonempty_strings(case.get("input_refs")):
            add_error(errors, "SUITE-017", f"{label}.input_refs must be non-empty")

        binding = case.get("candidate_binding")
        if binding not in CASE_BINDINGS:
            add_error(errors, "SUITE-018", f"{label}.candidate_binding is invalid")
        elif binding == "current-candidate":
            current_bound_count += 1
            if case.get("candidate_sha256") != candidate_sha:
                add_error(errors, "SUITE-019", f"{label} is not bound to the suite candidate")
        else:
            historical_unbound_count += 1
            if (
                not isinstance(case.get("historical_candidate_ref"), str)
                or not case["historical_candidate_ref"].strip()
            ):
                add_error(errors, "SUITE-020", f"{label} lacks historical_candidate_ref")

        execution_status = case.get("execution_status")
        if execution_status not in EXECUTION_STATUSES:
            add_error(errors, "SUITE-021", f"{label}.execution_status is invalid")
        elif execution_status == "executed-pass":
            executed_pass_count += 1
        elif execution_status == "executed-fail":
            executed_fail_count += 1
        else:
            not_run_count += 1

        assertions = case.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            add_error(errors, "SUITE-022", f"{label}.assertions must be non-empty")
            assertions = []
        assertion_states: list[str] = []
        for assertion_index, assertion in enumerate(assertions):
            assertion_label = f"{label}.assertions[{assertion_index}]"
            if not isinstance(assertion, dict):
                add_error(errors, "SUITE-023", f"{assertion_label} must be an object")
                continue
            assertion_id = assertion.get("id")
            if not isinstance(assertion_id, str) or not assertion_id.strip():
                add_error(errors, "SUITE-024", f"{assertion_label}.id is required")
            elif assertion_id in assertion_ids:
                add_error(errors, "SUITE-025", f"duplicate assertion id: {assertion_id}")
            else:
                assertion_ids.add(assertion_id)
            observed = assertion.get("observed")
            if observed not in OBSERVED_STATUSES:
                add_error(errors, "SUITE-027", f"{assertion_label}.observed is invalid")
            else:
                assertion_states.append(observed)
            # 未执行（not-run）的断言在快速模式下允许缺 expected，待标准模式补；
            # warn 状态为语义 gate 软提示，也允许缺 expected（判定逻辑在 semantic gate 内）。
            if observed in {"not-run", "warn"}:
                continue
            if not isinstance(assertion.get("expected"), str) or not assertion["expected"].strip():
                add_error(errors, "SUITE-026", f"{assertion_label}.expected is required")
            if observed in {"pass", "fail"} and (
                not isinstance(assertion.get("evidence"), str)
                or not assertion["evidence"].strip()
            ):
                add_error(errors, "SUITE-028", f"{assertion_label} lacks evidence")

        if execution_status == "not-run":
            if any(state != "not-run" for state in assertion_states):
                add_error(errors, "SUITE-029", f"{label} is not-run but has observed results")
            if case.get("run_receipts"):
                add_error(errors, "SUITE-030", f"{label} is not-run but has run receipts")
        elif execution_status in {"executed-pass", "executed-fail"}:
            if not valid_run_receipts(case.get("run_receipts")):
                add_error(errors, "SUITE-031", f"{label} lacks run receipts")
            if not is_sha256(case.get("input_sha256")):
                add_error(errors, "SUITE-032", f"{label}.input_sha256 is required")
            if not is_sha256(case.get("output_sha256")):
                add_error(errors, "SUITE-033", f"{label}.output_sha256 is required")
            if any(state == "not-run" for state in assertion_states):
                add_error(errors, "SUITE-034", f"{label} has unexecuted assertions")
            if execution_status == "executed-pass" and any(
                state != "pass" for state in assertion_states
            ):
                add_error(errors, "SUITE-035", f"{label} pass status disagrees with assertions")
            if execution_status == "executed-fail" and "fail" not in assertion_states:
                add_error(errors, "SUITE-036", f"{label} fail status lacks a failed assertion")

    # 指令型 suite 不强制 case_type / tier / capability 覆盖（材料+LLM 运行范式不同）。
    if not is_instruction:
        missing_case_types = REQUIRED_CASE_TYPES - observed_case_types
        if missing_case_types:
            add_error(errors, "SUITE-037", f"missing case types: {sorted(missing_case_types)}")
        missing_tiers = TIERS - observed_tiers
        if missing_tiers:
            add_error(errors, "SUITE-038", f"missing tiers: {sorted(missing_tiers)}")
        missing_capabilities = REQUIRED_CAPABILITIES_COMMAND - observed_capabilities
        if missing_capabilities:
            add_error(errors, "SUITE-039", f"missing capabilities: {sorted(missing_capabilities)}")

    status = suite.get("status")
    if status not in SUITE_STATUSES:
        add_error(errors, "SUITE-040", "suite status is invalid")
    markers = suite.get("formal_markers")
    markers_valid = isinstance(markers, list) and all(
        isinstance(marker, str) for marker in markers
    )
    marker_set = set(markers) if markers_valid else set()
    if not markers_valid or not marker_set or not marker_set <= FORMAL_MARKERS:
        add_error(errors, "SUITE-041", "formal_markers are invalid")
    if "DOMAIN_VERIFIED" in marker_set and "NOT_VERIFIED" in marker_set:
        add_error(errors, "SUITE-042", "DOMAIN_VERIFIED and NOT_VERIFIED cannot coexist")

    if executed_fail_count and status != "regression-detected":
        add_error(errors, "SUITE-043", "failed cases require regression-detected status")
    if not executed_fail_count and not_run_count and status != "prepared-not-verified":
        add_error(errors, "SUITE-044", "unexecuted cases require prepared-not-verified status")
    if status == "regression-detected" and not executed_fail_count:
        add_error(errors, "SUITE-045", "regression-detected status lacks a failed case")
    if status == "verified":
        if executed_fail_count or not_run_count or historical_unbound_count:
            add_error(errors, "SUITE-046", "verified suite must be fully executed, passing and current-bound")
        if "DOMAIN_VERIFIED" not in marker_set:
            add_error(errors, "SUITE-047", "verified suite requires DOMAIN_VERIFIED")
        if not valid_domain_receipts(suite.get("domain_receipts")):
            add_error(errors, "SUITE-048", "verified suite requires domain receipts")
    elif marker_set != {"NOT_VERIFIED"}:
        add_error(errors, "SUITE-049", "non-verified suite must use only NOT_VERIFIED")

    measurements = {
        "case_count": len(cases),
        "assertion_count": len(assertion_ids),
        "executed_pass_count": executed_pass_count,
        "executed_fail_count": executed_fail_count,
        "not_run_count": not_run_count,
        "current_bound_count": current_bound_count,
        "historical_unbound_count": historical_unbound_count,
        "candidate_file_count": recomputed_file_count,
    }
    observables = {
        "suite_id": suite.get("suite_id"),
        "suite_status": status,
        "case_types": sorted(observed_case_types),
        "tiers": sorted(observed_tiers),
        "capabilities": sorted(observed_capabilities),
        "candidate_sha256": candidate_sha,
        "recomputed_candidate_sha256": recomputed_sha,
        "formal_markers": sorted(marker_set),
    }
    return {"errors": errors, "measurements": measurements, "observables": observables}


def command_check(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    try:
        suite = load_package(input_path)
        result = validate(suite, Path(args.candidate_root) if args.candidate_root else None)
    except (GateInputError, OSError) as exc:
        emit({"status": "error", "message": str(exc)}, 2)

    failed = bool(result["errors"])
    if args.stability_protocol:
        artifact_sha = {"capability-suite": file_hash(input_path.expanduser().resolve())}
        measurements = {
            "case-count": result["measurements"]["case_count"],
            "evidence-state-consistent": not failed,
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
                "observables": {"suite-state": result["observables"]},
            },
            0,
        )

    emit(
        {
            "status": "fail" if failed else "pass",
            "artifact_sha256": canonical_hash(suite),
            "passed_constraint_ids": [] if failed else [CONSTRAINT_ID],
            "failed_constraint_ids": [CONSTRAINT_ID] if failed else [],
            "measurements": result["measurements"],
            "observables": result["observables"],
            "errors": result["errors"],
        },
        3 if failed else 0,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a layered legal capability suite.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--candidate-root")
    parser.add_argument("--stability-protocol", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    command_check(args)


if __name__ == "__main__":
    main()
