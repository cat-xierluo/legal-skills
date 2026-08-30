#!/usr/bin/env python3
"""独立复算 video-screenshot 五条关键交付不变量。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


CONSTRAINTS = (
    "BASE-HIGH-RECALL",
    "VISION-SUBTRACT-ONLY",
    "FINAL-COVERAGE-SURVIVAL",
    "EVIDENCE-LEADS-NON-DESTRUCTIVE",
    "TRANSACTIONAL-OUTPUT-SAFETY",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _string_set(value: Any, label: str) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} 必须是字符串列表")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} 不得包含重复项")
    return set(value)


def _evaluate(data: Any) -> tuple[dict[str, bool], dict[str, list[str]]]:
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise ValueError("schema_version 必须为 1.0")

    short_candidates = _string_set(
        data.get("short_motion_candidate_group_ids"),
        "short_motion_candidate_group_ids",
    )
    short_preserved = _string_set(
        data.get("short_motion_preserved_group_ids"),
        "short_motion_preserved_group_ids",
    )
    base_frames = _string_set(data.get("base_frame_ids"), "base_frame_ids")
    vision_frames = _string_set(data.get("vision_output_frame_ids"), "vision_output_frame_ids")
    final_frames = _string_set(data.get("final_frame_ids"), "final_frame_ids")
    operation = data.get("vision_operation")
    evidence_operation = data.get("evidence_lead_operation")
    evidence_base_frames_modified = data.get("evidence_base_frames_modified")
    output_transaction = data.get("output_transaction")
    failed_run_modified_previous_output = data.get("failed_run_modified_previous_output")
    output_marker_valid = data.get("output_marker_valid")
    mutations = data.get("mutations")
    if not isinstance(mutations, list):
        raise ValueError("mutations 必须是列表")

    mutation_targets: set[str] = set()
    mutation_coverage: set[str] = set()
    mutation_valid = True
    for index, mutation in enumerate(mutations, 1):
        if not isinstance(mutation, dict) or set(mutation) != {
            "target_id",
            "coverage_id",
            "confidence",
            "local_risk",
            "local_coverage_eligible",
        }:
            raise ValueError(f"mutation #{index} 字段不完整")
        target = mutation["target_id"]
        coverage = mutation["coverage_id"]
        confidence = mutation["confidence"]
        if not isinstance(target, str) or not isinstance(coverage, str):
            raise ValueError(f"mutation #{index} ID 非法")
        mutation_targets.add(target)
        mutation_coverage.add(coverage)
        mutation_valid = mutation_valid and (
            target in base_frames
            and coverage in base_frames
            and isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
            and confidence >= 0.90
            and mutation["local_risk"] is True
            and mutation["local_coverage_eligible"] is True
        )

    results = {
        "BASE-HIGH-RECALL": bool(short_candidates)
        and short_candidates.issubset(short_preserved),
        "VISION-SUBTRACT-ONLY": operation == "subtract_only"
        and vision_frames.issubset(base_frames),
        "FINAL-COVERAGE-SURVIVAL": mutation_valid
        and mutation_coverage.issubset(final_frames)
        and mutation_coverage.isdisjoint(mutation_targets),
        "EVIDENCE-LEADS-NON-DESTRUCTIVE": evidence_operation == "classify_and_summarize_only"
        and evidence_base_frames_modified is False,
        "TRANSACTIONAL-OUTPUT-SAFETY": output_transaction == "staged_replace"
        and failed_run_modified_previous_output is False
        and output_marker_valid is True,
    }
    observables = {
        "preserved-short-motion-groups": sorted(short_preserved),
        "vision-output-frame-set": sorted(vision_frames),
        "final-coverage-frame-set": sorted(mutation_coverage.intersection(final_frames)),
        "evidence-base-frame-set": sorted(base_frames),
        "output-transaction-mode": [str(output_transaction or "")],
    }
    return results, observables


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    artifact = Path(args.input).resolve()
    try:
        artifact_hash = {"pipeline-validation": _sha256(artifact)}
        data = json.loads(artifact.read_text(encoding="utf-8"))
        results, observables = _evaluate(data)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"STABILITY_ARTIFACT_INVALID: {exc}")
        return 2

    failed = [constraint for constraint in CONSTRAINTS if not results[constraint]]
    measurements = {
        constraint: {f"{constraint.lower()}-passed": results[constraint]}
        for constraint in CONSTRAINTS
    }
    if failed:
        print(f"STABILITY_CONSTRAINT_BLOCKED: {', '.join(failed)}")
        print(
            json.dumps(
                {
                    "failed_constraint_ids": failed,
                    "artifact_sha256": artifact_hash,
                    "measurements": {
                        constraint: measurements[constraint] for constraint in failed
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 3

    print("STABILITY_CONSTRAINTS_PASSED")
    print(
        json.dumps(
            {
                "passed_constraint_ids": list(CONSTRAINTS),
                "artifact_sha256": artifact_hash,
                "measurements": measurements,
                "observables": observables,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
