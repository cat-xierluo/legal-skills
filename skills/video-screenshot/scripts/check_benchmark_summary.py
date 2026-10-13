#!/usr/bin/env python3
"""独立检查公开基准摘要的隐私字段与不夸大结论合同。"""

import argparse
import hashlib
import json
from pathlib import Path


CONSTRAINT = "PRIVATE-BENCHMARK-NO-OVERCLAIM"


def valid(data):
    if not isinstance(data, dict) or data.get("schema_version") != "video-screenshot-benchmark-summary/v1":
        return False
    privacy = data.get("privacy")
    if privacy != {"source_paths_stored": False, "ocr_text_stored": False, "annotation_intervals_stored": False, "frame_filenames_stored": False}:
        return False
    if data.get("accuracy_improvement_claim_allowed") is not False:
        return False
    corpus = data.get("corpus") or {}
    real = corpus.get("kind") == "real"
    complete = data.get("baseline_complete") is True
    required = {"xiaohongshu", "wechat_chat", "product_work", "qualification_document", "long_scroll"}
    categories = corpus.get("distinct_categories")
    if not isinstance(categories, list):
        return False
    ready = real and complete and required.issubset(categories)
    status = data.get("real_baseline_status")
    if status not in {"not_verified", "recorded_requires_human_review"}:
        return False
    if (status == "recorded_requires_human_review" or data.get("comparative_evaluation_ready") is True) and not ready:
        return False
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        return False
    if data.get("comparative_evaluation_ready") is True:
        for case in cases:
            results = case.get("profiles") or {}
            required_status = "scored" if case.get("expected_outcome") == "success" else "passed"
            if any((results.get(profile) or {}).get("status") != required_status for profile in ("visual", "ocr")):
                return False
    forbidden = {"video_path", "input", "filename", "output_relative", "diagnostic", "start_seconds", "end_seconds", "ocr_text"}
    def private(value):
        if isinstance(value, dict):
            return bool(forbidden.intersection(value)) or any(private(item) for item in value.values())
        if isinstance(value, list):
            return any(private(item) for item in value)
        return isinstance(value, str) and (value.startswith(("/", "~/")) or ":\\" in value or "frame_" in value)
    return not private(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = args.input.read_bytes()
        passed = valid(json.loads(payload))
    except (OSError, ValueError, TypeError, AttributeError):
        print("BENCHMARK_SUMMARY_INVALID")
        return 2
    key = "passed_constraint_ids" if passed else "failed_constraint_ids"
    result = {
        key: [CONSTRAINT],
        "artifact_sha256": {"benchmark-summary": hashlib.sha256(payload).hexdigest()},
        "measurements": {CONSTRAINT: {"private-benchmark-no-overclaim-passed": passed}},
    }
    if passed:
        result["observables"] = {"benchmark-conclusion-status": [json.loads(payload)["real_baseline_status"]]}
    print("BENCHMARK_SUMMARY_PASSED" if passed else "BENCHMARK_SUMMARY_BLOCKED")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
