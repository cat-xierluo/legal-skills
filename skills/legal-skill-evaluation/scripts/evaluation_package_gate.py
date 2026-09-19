#!/usr/bin/env python3
"""Validate a legal-skill-evaluation package with only the Python standard library."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


CONSTRAINT_COVERAGE = "EVAL-REPORT-COVERAGE"
CONSTRAINT_BINDING = "EVAL-EVIDENCE-BINDING"
CONSTRAINT_CLOSURE = "EVAL-CLOSURE"
CONSTRAINT_IDS = [CONSTRAINT_COVERAGE, CONSTRAINT_BINDING, CONSTRAINT_CLOSURE]
CASE_TYPES = {"familiar", "peer-unfamiliar", "missing-context"}
DIMENSION_IDS = {f"DIM-{index}" for index in range(1, 7)}
TASTE_IDS = {f"TASTE-{index}" for index in range(1, 9)}
RECOMMENDATIONS = {"enter-workflow", "revise-and-retest", "blocked", "adopt-with-notes"}
# 进入工作流的推荐（不含 blocked/revise）：enter-workflow 需 DOMAIN_VERIFIED；
# adopt-with-notes 用于指令型/未签发 DOMAIN_VERIFIED 但运行已闭环的场景。
WORKFLOW_RECOMMENDATIONS = {"enter-workflow", "adopt-with-notes"}
FORMAL_MARKERS = {
    "HARNESS_REVIEW_VERIFIED",
    "INSTRUCTION_STABILITY_VERIFIED",
    "DOMAIN_VERIFIED",
}
EVIDENCE_MARKERS = FORMAL_MARKERS | {"NOT_VERIFIED"}
CANDIDATE_HASH_SCOPES = {"full-directory", "git-tracked"}
CASE_BINDINGS = {"current-candidate", "historical-unbound"}
FINDING_DISPOSITIONS = {"false-positive", "not-applicable", "out-of-scope"}
STATUS_BY_FIELD = {
    "harness_status": {"HARNESS_REVIEW_VERIFIED", "NOT_VERIFIED"},
    "instruction_stability_status": {
        "INSTRUCTION_STABILITY_VERIFIED",
        "NOT_VERIFIED",
    },
    "domain_status": {"DOMAIN_VERIFIED", "NOT_VERIFIED"},
}
IGNORED_PARTS = {".git", "__pycache__", ".DS_Store"}


class GateInputError(Exception):
    """Raised when the input cannot be parsed as an evaluation package."""


def emit(payload: dict[str, Any], exit_code: int) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    raise SystemExit(exit_code)


def is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in value)


def canonical_hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_files(root: Path, scope: str) -> tuple[Path, list[Path]]:
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        raise GateInputError(f"candidate root is not a directory: {resolved}")

    if scope not in CANDIDATE_HASH_SCOPES:
        raise GateInputError(f"unsupported candidate hash scope: {scope}")

    files: list[Path] = []
    if scope == "full-directory":
        for path in resolved.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(resolved)
            if any(part in IGNORED_PARTS for part in relative.parts):
                continue
            files.append(path)
        return resolved, files

    try:
        repo_result = subprocess.run(
            ["git", "-C", str(resolved), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise GateInputError(f"cannot inspect git-tracked scope: {exc}") from exc
    if repo_result.returncode != 0:
        raise GateInputError("git-tracked scope requires a candidate inside a Git worktree")

    repository = Path(repo_result.stdout.strip()).resolve()
    try:
        prefix = resolved.relative_to(repository)
    except ValueError as exc:
        raise GateInputError("candidate root is outside the detected Git worktree") from exc

    list_result = subprocess.run(
        ["git", "-C", str(repository), "ls-files", "-z", "--", prefix.as_posix()],
        capture_output=True,
        check=False,
    )
    if list_result.returncode != 0:
        raise GateInputError("failed to enumerate git-tracked candidate files")
    for raw_path in list_result.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = repository / raw_path.decode("utf-8", errors="surrogateescape")
        try:
            path.relative_to(resolved)
        except ValueError as exc:
            raise GateInputError(f"tracked path escapes candidate root: {path}") from exc
        if not path.is_file():
            continue
        files.append(path)
    if not files:
        raise GateInputError("git-tracked candidate scope contains no files")
    return resolved, files


def candidate_snapshot(root: Path, scope: str = "full-directory") -> dict[str, Any]:
    resolved, files = candidate_files(root, scope)
    digest = hashlib.sha256()

    for path in sorted(files, key=lambda item: item.relative_to(resolved).as_posix()):
        relative = path.relative_to(resolved).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return {
        "candidate_sha256": digest.hexdigest(),
        "hash_scope": scope,
        "file_count": len(files),
    }


def _navigate(container: Any, path: list[Any]) -> tuple[Any, Any]:
    if not path:
        raise GateInputError("mutation path cannot be empty")
    current = container
    for part in path[:-1]:
        try:
            current = current[part]
        except (KeyError, IndexError, TypeError) as exc:
            raise GateInputError(f"invalid mutation path: {path}") from exc
    return current, path[-1]


def apply_mutation(package: dict[str, Any], mutation: dict[str, Any]) -> None:
    operation = mutation.get("op")
    path = mutation.get("path")
    if not isinstance(path, list):
        raise GateInputError("mutation path must be a JSON array")

    parent, key = _navigate(package, path)
    if operation == "set":
        try:
            parent[key] = mutation.get("value")
        except (KeyError, IndexError, TypeError) as exc:
            raise GateInputError(f"invalid set mutation: {path}") from exc
        return

    if operation == "remove":
        try:
            if isinstance(parent, list):
                parent.pop(key)
            else:
                parent.pop(key)
        except (KeyError, IndexError, TypeError) as exc:
            raise GateInputError(f"invalid remove mutation: {path}") from exc
        return

    if operation == "remove_by_id":
        try:
            collection = parent[key]
        except (KeyError, IndexError, TypeError) as exc:
            raise GateInputError(f"invalid remove_by_id mutation: {path}") from exc
        target_id = mutation.get("id")
        if not isinstance(collection, list):
            raise GateInputError("remove_by_id target must be a list")
        filtered = [
            item
            for item in collection
            if not isinstance(item, dict) or item.get("id") != target_id
        ]
        if len(filtered) == len(collection):
            raise GateInputError(f"remove_by_id target not found: {target_id}")
        parent[key] = filtered
        return

    raise GateInputError(f"unsupported mutation operation: {operation}")


def load_package(
    path: Path,
    seen: set[Path] | None = None,
    fixture_root: Path | None = None,
) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    visited = set() if seen is None else seen
    if resolved in visited:
        raise GateInputError(f"fixture cycle detected at {resolved}")
    visited.add(resolved)

    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateInputError(f"input file not found: {resolved}") from exc
    except json.JSONDecodeError as exc:
        raise GateInputError(f"invalid JSON at line {exc.lineno}: {exc.msg}") from exc

    if not isinstance(raw, dict):
        raise GateInputError("top-level JSON value must be an object")
    if "fixture_base" not in raw:
        return raw

    base_value = raw.get("fixture_base")
    mutations = raw.get("mutations", [])
    if not isinstance(base_value, str) or not isinstance(mutations, list):
        raise GateInputError("fixture_base must be a string and mutations must be a list")
    # fixture_base 解析：优先相对输入文件所在目录（向后兼容），
    # 若在该处不存在且显式传入 --fixture-root，则回退到 fixture_root 解析。
    # 此改动解耦「fixture 必须和输入文件同目录」的路径耦合（F-5 误伤修复）。
    base_path = resolved.parent / base_value
    if not base_path.exists() and fixture_root is not None:
        base_path = Path(fixture_root).expanduser().resolve() / base_value
    base = load_package(base_path, visited, fixture_root)
    package = copy.deepcopy(base)
    for mutation in mutations:
        if not isinstance(mutation, dict):
            raise GateInputError("each mutation must be an object")
        apply_mutation(package, mutation)
    if isinstance(raw.get("fixture_metadata"), dict):
        package["_fixture_metadata"] = raw["fixture_metadata"]
    return package


def add_error(
    errors: list[dict[str, str]],
    constraint_id: str,
    code: str,
    message: str,
) -> None:
    errors.append(
        {
            "constraint_id": constraint_id,
            "code": code,
            "message": message,
        }
    )


def validate(package: dict[str, Any], candidate_root: Path | None) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    schema_version = package.get("schema_version")
    strict_provenance = schema_version == "1.1"
    if schema_version not in {"1.0", "1.1"}:
        add_error(
            errors,
            CONSTRAINT_COVERAGE,
            "COV-000",
            "schema_version must be 1.0 or 1.1",
        )
    mode = package.get("mode")
    if mode not in {"quick", "standard", "release"}:
        add_error(errors, CONSTRAINT_COVERAGE, "COV-001", "mode must be quick, standard, or release")

    candidate = package.get("candidate")
    generic = package.get("generic_gate")
    cases = package.get("cases")
    verdict = package.get("verdict")
    if not isinstance(candidate, dict):
        candidate = {}
        add_error(errors, CONSTRAINT_BINDING, "BIND-001", "candidate must be an object")
    if not isinstance(generic, dict):
        generic = {}
        add_error(errors, CONSTRAINT_BINDING, "BIND-002", "generic_gate must be an object")
    if not isinstance(cases, list):
        cases = []
        add_error(errors, CONSTRAINT_COVERAGE, "COV-002", "cases must be an array")
    if not isinstance(verdict, dict):
        verdict = {}
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-001", "verdict must be an object")

    candidate_sha = candidate.get("sha256")
    generic_sha = generic.get("candidate_sha256")
    candidate_scope = candidate.get("hash_scope", "full-directory")
    generic_scope = generic.get("candidate_hash_scope", candidate_scope)
    if candidate_scope not in CANDIDATE_HASH_SCOPES:
        add_error(errors, CONSTRAINT_BINDING, "BIND-010", "candidate.hash_scope is invalid")
        candidate_scope = "full-directory"
    if generic_scope not in CANDIDATE_HASH_SCOPES:
        add_error(
            errors,
            CONSTRAINT_BINDING,
            "BIND-011",
            "generic_gate.candidate_hash_scope is invalid",
        )
    elif generic_scope != candidate_scope:
        add_error(
            errors,
            CONSTRAINT_BINDING,
            "BIND-012",
            "candidate and generic gate hash scopes do not match",
        )
    if strict_provenance and "hash_scope" not in candidate:
        add_error(errors, CONSTRAINT_BINDING, "BIND-013", "schema 1.1 requires candidate.hash_scope")
    if strict_provenance and "candidate_hash_scope" not in generic:
        add_error(
            errors,
            CONSTRAINT_BINDING,
            "BIND-014",
            "schema 1.1 requires generic_gate.candidate_hash_scope",
        )
    if not is_sha256(candidate_sha):
        add_error(errors, CONSTRAINT_BINDING, "BIND-003", "candidate.sha256 is not a SHA-256 value")
    if not is_sha256(generic_sha):
        add_error(errors, CONSTRAINT_BINDING, "BIND-004", "generic_gate.candidate_sha256 is not a SHA-256 value")
    if is_sha256(candidate_sha) and is_sha256(generic_sha) and candidate_sha.lower() != generic_sha.lower():
        add_error(errors, CONSTRAINT_BINDING, "BIND-005", "candidate and generic gate hashes do not match")

    recomputed_sha: str | None = None
    recomputed_file_count: int | None = None
    if candidate_root is not None:
        try:
            snapshot = candidate_snapshot(candidate_root, candidate_scope)
            recomputed_sha = snapshot["candidate_sha256"]
            recomputed_file_count = snapshot["file_count"]
        except (GateInputError, OSError) as exc:
            add_error(errors, CONSTRAINT_BINDING, "BIND-006", str(exc))
        if recomputed_sha and is_sha256(candidate_sha) and recomputed_sha.lower() != candidate_sha.lower():
            add_error(errors, CONSTRAINT_BINDING, "BIND-007", "candidate root hash does not match the package")

    case_types: list[str] = []
    case_ids: list[str] = []
    input_hashes: list[str] = []
    unbound_case_count = 0
    dimension_coverage_count = 0
    taste_coverage_count = 0
    bound_hash_count = int(is_sha256(candidate_sha)) + int(is_sha256(generic_sha))
    weak_output = False
    legal_redline_count = 0

    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            add_error(errors, CONSTRAINT_COVERAGE, "COV-003", f"{label} must be an object")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            add_error(errors, CONSTRAINT_COVERAGE, "COV-018", f"{label}.id is required")
        else:
            case_ids.append(case_id)
        case_type = case.get("type")
        if isinstance(case_type, str):
            case_types.append(case_type)
        if case_type not in CASE_TYPES:
            add_error(errors, CONSTRAINT_COVERAGE, "COV-004", f"{label}.type is invalid")

        for field in ("input_sha256", "output_sha256"):
            value = case.get(field)
            if not is_sha256(value):
                add_error(errors, CONSTRAINT_BINDING, "BIND-008", f"{label}.{field} is not a SHA-256 value")
            else:
                bound_hash_count += 1
                if field == "input_sha256":
                    input_hashes.append(value.lower())

        case_binding = case.get("candidate_binding", "current-candidate")
        if case_binding not in CASE_BINDINGS:
            add_error(
                errors,
                CONSTRAINT_BINDING,
                "BIND-015",
                f"{label}.candidate_binding is invalid",
            )
        elif case_binding == "current-candidate":
            case_candidate_sha = case.get("candidate_sha256", candidate_sha)
            if not is_sha256(case_candidate_sha):
                add_error(
                    errors,
                    CONSTRAINT_BINDING,
                    "BIND-016",
                    f"{label}.candidate_sha256 is required for current-candidate evidence",
                )
            elif is_sha256(candidate_sha) and case_candidate_sha.lower() != candidate_sha.lower():
                add_error(
                    errors,
                    CONSTRAINT_BINDING,
                    "BIND-017",
                    f"{label}.candidate_sha256 does not match the package candidate",
                )
            else:
                bound_hash_count += 1
        else:
            unbound_case_count += 1
            historical_ref = case.get("historical_candidate_ref")
            if not isinstance(historical_ref, str) or not historical_ref.strip():
                add_error(
                    errors,
                    CONSTRAINT_BINDING,
                    "BIND-018",
                    f"{label}.historical_candidate_ref is required for historical-unbound evidence",
                )
        if strict_provenance and "candidate_binding" not in case:
            add_error(
                errors,
                CONSTRAINT_BINDING,
                "BIND-019",
                f"schema 1.1 requires {label}.candidate_binding",
            )
        if (
            strict_provenance
            and case_binding == "current-candidate"
            and "candidate_sha256" not in case
        ):
            add_error(
                errors,
                CONSTRAINT_BINDING,
                "BIND-020",
                f"schema 1.1 requires {label}.candidate_sha256",
            )

        receipts = case.get("run_receipts")
        if mode in {"standard", "release"} and (
            not isinstance(receipts, list)
            or not receipts
            or not all(isinstance(item, str) and item.strip() for item in receipts)
        ):
            add_error(errors, CONSTRAINT_BINDING, "BIND-009", f"{label}.run_receipts must contain a receipt")

        dimensions = case.get("dimensions")
        if not isinstance(dimensions, list):
            dimensions = []
            add_error(errors, CONSTRAINT_COVERAGE, "COV-005", f"{label}.dimensions must be an array")
        dimension_ids = {
            item.get("id")
            for item in dimensions
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        dimension_coverage_count += len(dimension_ids & DIMENSION_IDS)
        if mode in {"standard", "release"} and dimension_ids != DIMENSION_IDS:
            add_error(errors, CONSTRAINT_COVERAGE, "COV-006", f"{label} must cover DIM-1 through DIM-6 exactly")
        for item in dimensions:
            if not isinstance(item, dict):
                add_error(errors, CONSTRAINT_COVERAGE, "COV-007", f"{label} contains a non-object dimension")
                continue
            rating = item.get("rating")
            reason = item.get("not_applicable_reason")
            evidence = item.get("evidence")
            if rating is None:
                if not isinstance(reason, str) or not reason.strip():
                    add_error(errors, CONSTRAINT_COVERAGE, "COV-008", f"{label} N/A dimension needs a reason")
            elif isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
                add_error(errors, CONSTRAINT_COVERAGE, "COV-009", f"{label} dimension rating must be 1-5 or null")
            elif rating <= 2:
                weak_output = True
            if not isinstance(evidence, str) or not evidence.strip():
                add_error(errors, CONSTRAINT_COVERAGE, "COV-010", f"{label} dimension evidence is required")

        taste = case.get("taste")
        if not isinstance(taste, list):
            taste = []
            add_error(errors, CONSTRAINT_COVERAGE, "COV-011", f"{label}.taste must be an array")
        taste_ids = {
            item.get("id")
            for item in taste
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        taste_coverage_count += len(taste_ids & TASTE_IDS)
        if mode in {"standard", "release"} and taste_ids != TASTE_IDS:
            add_error(errors, CONSTRAINT_COVERAGE, "COV-012", f"{label} must cover TASTE-1 through TASTE-8 exactly")
        for item in taste:
            if not isinstance(item, dict):
                add_error(errors, CONSTRAINT_COVERAGE, "COV-013", f"{label} contains a non-object taste result")
                continue
            if item.get("status") not in {"pass", "fail"}:
                add_error(errors, CONSTRAINT_COVERAGE, "COV-014", f"{label} taste status must be pass or fail")
            if item.get("status") == "fail":
                weak_output = True
            if not isinstance(item.get("evidence"), str) or not item["evidence"].strip():
                add_error(errors, CONSTRAINT_COVERAGE, "COV-015", f"{label} taste evidence is required")

        redlines = case.get("legal_redlines", [])
        if not isinstance(redlines, list):
            add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-002", f"{label}.legal_redlines must be an array")
        else:
            legal_redline_count += len(redlines)

    unique_case_types = set(case_types)
    if len(set(case_ids)) != len(case_ids):
        add_error(errors, CONSTRAINT_COVERAGE, "COV-019", "case ids must be unique")
    if (
        strict_provenance
        and mode in {"standard", "release"}
        and len(set(input_hashes)) != len(input_hashes)
    ):
        add_error(
            errors,
            CONSTRAINT_BINDING,
            "BIND-021",
            "schema 1.1 requires distinct input bundles for the three case types",
        )
    if mode in {"standard", "release"} and unique_case_types != CASE_TYPES:
        add_error(errors, CONSTRAINT_COVERAGE, "COV-016", "standard and release modes require all three case types")
    if mode == "quick" and not cases:
        add_error(errors, CONSTRAINT_COVERAGE, "COV-017", "quick mode requires at least one case")

    for field, allowed in STATUS_BY_FIELD.items():
        if generic.get(field) not in allowed:
            add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-003", f"generic_gate.{field} has an invalid status")

    generic_findings = generic.get("hard_findings", [])
    raw_findings = generic.get("raw_hard_findings", [])
    adjudications = generic.get("finding_adjudications", [])
    hard_failures = package.get("hard_failures", [])
    if not isinstance(generic_findings, list):
        generic_findings = ["invalid hard_findings value"]
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-004", "generic_gate.hard_findings must be an array")
    if not isinstance(hard_failures, list):
        hard_failures = ["invalid hard_failures value"]
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-005", "hard_failures must be an array")

    def finding_ids(items: list[Any]) -> set[str]:
        result: set[str] = set()
        for item in items:
            if isinstance(item, str) and item.strip():
                result.add(item.strip())
            elif isinstance(item, dict) and isinstance(item.get("id"), str):
                result.add(item["id"].strip())
        return result

    if strict_provenance and "raw_hard_findings" not in generic:
        add_error(
            errors,
            CONSTRAINT_BINDING,
            "BIND-022",
            "schema 1.1 requires generic_gate.raw_hard_findings",
        )
    if strict_provenance and not isinstance(raw_findings, list):
        raw_findings = []
        add_error(
            errors,
            CONSTRAINT_BINDING,
            "BIND-022",
            "schema 1.1 requires generic_gate.raw_hard_findings to be an array",
        )
    if strict_provenance and "finding_adjudications" not in generic:
        add_error(
            errors,
            CONSTRAINT_BINDING,
            "BIND-023",
            "schema 1.1 requires generic_gate.finding_adjudications",
        )
    if strict_provenance and not isinstance(adjudications, list):
        adjudications = []
        add_error(
            errors,
            CONSTRAINT_BINDING,
            "BIND-023",
            "schema 1.1 requires generic_gate.finding_adjudications to be an array",
        )
    raw_ids = finding_ids(raw_findings) if isinstance(raw_findings, list) else set()
    unresolved_ids = finding_ids(generic_findings)
    adjudicated_ids: set[str] = set()
    out_of_scope_finding_count = 0
    if isinstance(adjudications, list):
        for index, adjudication in enumerate(adjudications):
            label = f"generic_gate.finding_adjudications[{index}]"
            if not isinstance(adjudication, dict):
                add_error(errors, CONSTRAINT_BINDING, "BIND-024", f"{label} must be an object")
                continue
            finding_id = adjudication.get("finding_id")
            disposition = adjudication.get("disposition")
            reason = adjudication.get("reason")
            evidence = adjudication.get("evidence")
            if not isinstance(finding_id, str) or not finding_id.strip():
                add_error(errors, CONSTRAINT_BINDING, "BIND-025", f"{label}.finding_id is required")
                continue
            if finding_id in adjudicated_ids:
                add_error(errors, CONSTRAINT_BINDING, "BIND-026", f"duplicate adjudication for {finding_id}")
            adjudicated_ids.add(finding_id)
            if disposition not in FINDING_DISPOSITIONS:
                add_error(errors, CONSTRAINT_BINDING, "BIND-027", f"{label}.disposition is invalid")
            elif disposition == "out-of-scope":
                out_of_scope_finding_count += 1
            if not isinstance(reason, str) or not reason.strip():
                add_error(errors, CONSTRAINT_BINDING, "BIND-028", f"{label}.reason is required")
            if not isinstance(evidence, str) or not evidence.strip():
                add_error(errors, CONSTRAINT_BINDING, "BIND-029", f"{label}.evidence is required")
    if strict_provenance:
        if not isinstance(raw_findings, list):
            raw_findings = []
        missing_disposition = raw_ids - unresolved_ids - adjudicated_ids
        if missing_disposition:
            add_error(
                errors,
                CONSTRAINT_BINDING,
                "BIND-030",
                "raw hard findings lack an unresolved status or adjudication: "
                + ", ".join(sorted(missing_disposition)),
            )
        if (unresolved_ids | adjudicated_ids) - raw_ids:
            add_error(
                errors,
                CONSTRAINT_BINDING,
                "BIND-031",
                "hard findings or adjudications are not present in raw_hard_findings",
            )
        if unresolved_ids & adjudicated_ids:
            add_error(
                errors,
                CONSTRAINT_BINDING,
                "BIND-032",
                "a raw finding cannot be both unresolved and adjudicated",
            )
    blocker_present = bool(generic_findings or hard_failures or legal_redline_count)

    repair_units = package.get("repair_units", [])
    if not isinstance(repair_units, list):
        repair_units = []
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-006", "repair_units must be an array")

    regression = package.get("regression", {})
    if not isinstance(regression, dict):
        regression = {}
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-007", "regression must be an object")
    valid_regression = {"pass", "fail", "not-run", "not-applicable"}
    regression_results = [
        regression.get("fail_to_pass"),
        regression.get("pass_to_pass"),
    ]
    if any(item not in valid_regression for item in regression_results):
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-008", "regression results use an invalid status")
    # "fail" 表示未闭环失败；"not-run" 是未测（无基线），不视为阻断工作流的 open failure。
    regression_open = any(item == "fail" for item in regression_results)

    recommendation = verdict.get("recommendation")
    if recommendation not in RECOMMENDATIONS:
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-009", "verdict.recommendation is invalid")
    if blocker_present and recommendation != "blocked":
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-010", "a blocker requires the blocked recommendation")
    if (weak_output or repair_units or regression_open) and recommendation in WORKFLOW_RECOMMENDATIONS:
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-011", "open failures cannot enter the workflow")
    if mode == "quick" and recommendation == "enter-workflow":
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-012", "quick mode cannot recommend enter-workflow")
    if mode == "release" and unbound_case_count:
        add_error(
            errors,
            CONSTRAINT_BINDING,
            "BIND-033",
            "release mode cannot use historical-unbound case evidence",
        )
    if unbound_case_count and recommendation in WORKFLOW_RECOMMENDATIONS:
        add_error(
            errors,
            CONSTRAINT_CLOSURE,
            "CLOSE-021",
            "historical-unbound case evidence cannot support enter-workflow",
        )
    if out_of_scope_finding_count and recommendation in WORKFLOW_RECOMMENDATIONS:
        add_error(
            errors,
            CONSTRAINT_CLOSURE,
            "CLOSE-023",
            "out-of-scope hard findings cannot support enter-workflow",
        )

    markers = verdict.get("formal_markers")
    if not isinstance(markers, list) or not markers:
        markers = []
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-013", "verdict.formal_markers must be a non-empty array")
    marker_set = set(markers) if all(isinstance(item, str) for item in markers) else set()
    if len(marker_set) != len(markers) or not marker_set <= EVIDENCE_MARKERS:
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-014", "formal markers are duplicated or invalid")
    if "NOT_VERIFIED" in marker_set and len(marker_set) > 1:
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-015", "NOT_VERIFIED cannot be combined with formal markers")
    if mode == "quick" and marker_set != {"NOT_VERIFIED"}:
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-016", "quick mode must remain NOT_VERIFIED")
    if recommendation == "enter-workflow" and "DOMAIN_VERIFIED" not in marker_set:
        add_error(
            errors,
            CONSTRAINT_CLOSURE,
            "CLOSE-017",
            "enter-workflow requires candidate-bound DOMAIN_VERIFIED evidence",
        )
    if unbound_case_count and "DOMAIN_VERIFIED" in marker_set:
        add_error(
            errors,
            CONSTRAINT_CLOSURE,
            "CLOSE-022",
            "historical-unbound case evidence cannot support DOMAIN_VERIFIED",
        )
    if mode == "release" and recommendation == "enter-workflow" and marker_set != FORMAL_MARKERS:
        add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-020", "release approval requires all three formal markers")

    status_marker_pairs = {
        "harness_status": "HARNESS_REVIEW_VERIFIED",
        "instruction_stability_status": "INSTRUCTION_STABILITY_VERIFIED",
        "domain_status": "DOMAIN_VERIFIED",
    }
    for field, marker in status_marker_pairs.items():
        if generic.get(field) == marker and marker not in marker_set:
            add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-018", f"{field} and formal_markers disagree")
        if marker in marker_set and generic.get(field) != marker:
            add_error(errors, CONSTRAINT_CLOSURE, "CLOSE-019", f"{marker} lacks a matching generic gate status")

    closure_errors = [
        item for item in errors if item["constraint_id"] == CONSTRAINT_CLOSURE
    ]
    measurements = {
        "case_type_count": len(unique_case_types),
        "dimension_coverage_count": dimension_coverage_count,
        "taste_coverage_count": taste_coverage_count,
        "bound_hash_count": bound_hash_count,
        "unbound_case_count": unbound_case_count,
        "candidate_file_count": recomputed_file_count,
        "raw_hard_finding_count": len(raw_ids),
        "adjudicated_finding_count": len(adjudicated_ids),
        "out_of_scope_finding_count": out_of_scope_finding_count,
        "blocker_count": len(generic_findings) + len(hard_failures) + legal_redline_count,
    }
    observables = {
        CONSTRAINT_COVERAGE: {
            "required_case_types": sorted(CASE_TYPES),
            "observed_case_types": sorted(unique_case_types),
        },
        CONSTRAINT_BINDING: {
            "candidate_sha256": candidate_sha,
            "generic_candidate_sha256": generic_sha,
            "recomputed_candidate_sha256": recomputed_sha,
            "candidate_hash_scope": candidate_scope,
            "generic_candidate_hash_scope": generic_scope,
            "unbound_case_count": unbound_case_count,
        },
        CONSTRAINT_CLOSURE: {
            "recommendation": recommendation,
            "blocker_present": blocker_present,
            "weak_output_present": weak_output,
            "regression_open": regression_open,
            "closure_consistent": not closure_errors,
        },
    }
    return {
        "errors": errors,
        "measurements": measurements,
        "observables": observables,
    }


def command_hash(args: argparse.Namespace) -> None:
    try:
        snapshot = candidate_snapshot(Path(args.candidate_root), args.scope)
    except (GateInputError, OSError) as exc:
        emit({"status": "error", "message": str(exc)}, 2)
    emit(
        {
            "status": "pass",
            "candidate_root": str(Path(args.candidate_root).expanduser().resolve()),
            **snapshot,
        },
        0,
    )


def command_check(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    fixture_root = Path(args.fixture_root) if args.fixture_root else None
    try:
        package = load_package(input_path, fixture_root=fixture_root)
        result = validate(
            package,
            Path(args.candidate_root) if args.candidate_root else None,
        )
    except (GateInputError, OSError) as exc:
        emit({"status": "error", "message": str(exc)}, 2)

    failed_ids = sorted({item["constraint_id"] for item in result["errors"]})
    passed_ids = [item for item in CONSTRAINT_IDS if item not in failed_ids]
    if args.stability_protocol:
        measurements = {
            CONSTRAINT_COVERAGE: {
                "dimension-coverage-count": result["measurements"][
                    "dimension_coverage_count"
                ]
            },
            CONSTRAINT_BINDING: {
                "candidate-hash-match": (
                    result["observables"][CONSTRAINT_BINDING]["candidate_sha256"]
                    == result["observables"][CONSTRAINT_BINDING][
                        "generic_candidate_sha256"
                    ]
                )
            },
            CONSTRAINT_CLOSURE: {
                "closure-consistent": result["observables"][CONSTRAINT_CLOSURE][
                    "closure_consistent"
                ]
            },
        }
        artifact_sha = {"evaluation-package": file_hash(input_path.expanduser().resolve())}
        if failed_ids:
            emit(
                {
                    "failed_constraint_ids": failed_ids,
                    "artifact_sha256": artifact_sha,
                    "measurements": {
                        constraint_id: measurements[constraint_id]
                        for constraint_id in failed_ids
                    },
                },
                3,
            )
        emit(
            {
                "passed_constraint_ids": CONSTRAINT_IDS,
                "artifact_sha256": artifact_sha,
                "measurements": measurements,
                "observables": {
                    "case-types": result["observables"][CONSTRAINT_COVERAGE][
                        "observed_case_types"
                    ],
                    "candidate-binding": result["observables"][CONSTRAINT_BINDING],
                    "closure-state": result["observables"][CONSTRAINT_CLOSURE],
                },
            },
            0,
        )

    artifact_sha = canonical_hash(package)
    payload = {
        "status": "fail" if failed_ids else "pass",
        "artifact_sha256": artifact_sha,
        "passed_constraint_ids": passed_ids,
        "failed_constraint_ids": failed_ids,
        "measurements": result["measurements"],
        "observables": result["observables"],
        "errors": result["errors"],
    }
    emit(payload, 3 if failed_ids else 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Hash a candidate Skill or validate a legal evaluation package."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    hash_parser = subparsers.add_parser("hash", help="hash a candidate Skill directory")
    hash_parser.add_argument("--candidate-root", required=True)
    hash_parser.add_argument(
        "--scope",
        choices=sorted(CANDIDATE_HASH_SCOPES),
        default="full-directory",
        help="hash every non-cache file or only Git-tracked publishable files",
    )
    hash_parser.set_defaults(handler=command_hash)

    check_parser = subparsers.add_parser("check", help="validate an evaluation package")
    check_parser.add_argument("--input", required=True)
    check_parser.add_argument("--candidate-root")
    check_parser.add_argument(
        "--fixture-root",
        help="解析 fixture_base 的备用根目录；当 fixture 不随输入文件同目录时用于解耦路径耦合",
    )
    check_parser.add_argument(
        "--stability-protocol",
        action="store_true",
        help="emit the strict skill-lint instruction-stability checker protocol",
    )
    check_parser.set_defaults(handler=command_check)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
