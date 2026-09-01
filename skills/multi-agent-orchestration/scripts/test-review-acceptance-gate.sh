#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 - "${SCRIPT_DIR}/review-acceptance-gate.py" <<'PY'
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile


gate = Path(sys.argv[1])
HEAD = "11ce3e04b6348327d3447a367f4decb6ad2e80f9"
OTHER_HEAD = "0f9e8d7c6b5a49382716054f3e2d1c0b9a897869"

base = {
    "schema_version": "review-acceptance-gate.v1",
    "delivery_head": HEAD,
    "implementation": {"dispatch_id": "ctx_impl_wave1", "session_id": "term_impl_wave1"},
    "reviewer": {"dispatch_id": "ctx_review_wave1", "session_id": "term_review_wave1"},
    "verdict": "ACCEPT",
    "reviewed_head": HEAD,
    "review_consumer": "PM 对 wave MAO-PM-ROLE-SEPARATION 的合并/收口决策",
    "review_expiry": "交付合并后随契约归档；重开深度审查必须签发新契约",
    "blocking_findings": [],
    "verification_evidence": [
        {"command": "bash skills/multi-agent-orchestration/scripts/test-review-acceptance-gate.sh", "exit_code": 0},
        {"command": "python3 skills/multi-agent-orchestration/scripts/review-acceptance-gate.py skills/multi-agent-orchestration/templates/review-acceptance.example.json", "exit_code": 0},
    ],
    "role_exception": None,
}

exception_contract = copy.deepcopy(base)
exception_contract["role_exception"] = {
    "kind": "pm_deep_review",
    "reason_code": "worker_failure",
    "reason": "reviewer worker dispatch died before producing a verdict; PM performed the deep review once",
    "authorized_by": "user authorization recorded in wave MAO-PM-ROLE-SEPARATION dispatch ctx_578569ebd55c",
}

passed = 0
failed = 0


def run(spec, expected_ok, contains="", label=""):
    global passed, failed
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
        json.dump(spec, handle)
        handle.flush()
        result = subprocess.run(
            [sys.executable, str(gate), handle.name],
            check=False,
            capture_output=True,
            text=True,
        )
    try:
        payload = json.loads(result.stdout)
        assert payload["ok"] is expected_ok, payload
        assert (result.returncode == 0) is expected_ok, result
        if contains:
            assert any(contains in error for error in payload["errors"]), payload
        passed += 1
    except AssertionError as exc:
        failed += 1
        print(f"FAIL {label or contains}: {exc}")


run(copy.deepcopy(base), True, label="valid role-separated closeout passes")

documented_exception = copy.deepcopy(exception_contract)
run(documented_exception, True, label="fully documented PM exception passes")

# A declared PM intervention must never count as ordinary delivery.
with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
    json.dump(exception_contract, handle)
    handle.flush()
    result = subprocess.run(
        [sys.executable, str(gate), handle.name],
        check=False,
        capture_output=True,
        text=True,
    )
try:
    payload = json.loads(result.stdout)
    assert payload["ok"] is True, payload
    assert payload["ordinary_delivery"] is False, payload
    assert payload["role_exception"] == "pm_deep_review", payload
    passed += 1
except AssertionError as exc:
    failed += 1
    print(f"FAIL exception output must be marked non-ordinary: {exc}")

self_review = copy.deepcopy(base)
self_review["reviewer"] = copy.deepcopy(base["implementation"])
run(self_review, False, "self-review", "identical implementation and reviewer identities")

same_dispatch = copy.deepcopy(base)
same_dispatch["reviewer"] = {
    "dispatch_id": base["implementation"]["dispatch_id"],
    "session_id": "term_review_other",
}
run(same_dispatch, False, "distinct dispatch_id", "reviewer reusing the implementation dispatch")

same_session = copy.deepcopy(base)
same_session["reviewer"] = {
    "dispatch_id": "ctx_review_other",
    "session_id": base["implementation"]["session_id"],
}
run(same_session, False, "distinct session_id", "reviewer reusing the implementation session")

missing_reviewer = copy.deepcopy(base)
missing_reviewer.pop("reviewer")
run(missing_reviewer, False, "reviewer must be an object", "missing reviewer section")

placeholder_identity = copy.deepcopy(base)
placeholder_identity["reviewer"]["session_id"] = "tbd"
run(placeholder_identity, False, "cannot be a placeholder", "placeholder reviewer identity")

missing_delivery_head = copy.deepcopy(base)
missing_delivery_head.pop("delivery_head")
run(missing_delivery_head, False, "delivery_head must be an immutable 40-hex", "missing delivery head")

floating_head = copy.deepcopy(base)
floating_head["reviewed_head"] = "release-branch-head"
run(floating_head, False, "reviewed_head must be an immutable 40-hex", "floating reviewed head")

mismatched_head = copy.deepcopy(base)
mismatched_head["reviewed_head"] = OTHER_HEAD
run(mismatched_head, False, "must equal delivery_head", "reviewed head drifting from delivery head")

rejection_verdict = copy.deepcopy(base)
rejection_verdict["verdict"] = "REJECT"
run(rejection_verdict, False, "ACCEPT", "REJECT verdict cannot close out")

lowercase_verdict = copy.deepcopy(base)
lowercase_verdict["verdict"] = "accept"
run(lowercase_verdict, False, "ACCEPT", "lowercase verdict fails closed")

prose_evidence = copy.deepcopy(base)
prose_evidence["verification_evidence"] = "all tests green; see reviewer chat log for details"
run(prose_evidence, False, "non-empty array", "prose-only evidence")

prose_entry = copy.deepcopy(base)
prose_entry["verification_evidence"] = [{"command": "bash scripts/test-suite.sh", "notes": "passed locally"}]
run(prose_entry, False, "exit_code", "narrative entry without recorded exit code")

empty_evidence = copy.deepcopy(base)
empty_evidence["verification_evidence"] = []
run(empty_evidence, False, "non-empty array", "missing verification evidence")

failed_verification = copy.deepcopy(base)
failed_verification["verification_evidence"] = [{"command": "bash scripts/test-suite.sh", "exit_code": 2}]
run(failed_verification, False, "must have passed", "failed verification command")

placeholder_consumer = copy.deepcopy(base)
placeholder_consumer["review_consumer"] = "tbd"
run(placeholder_consumer, False, "review_consumer", "placeholder review consumer")

placeholder_expiry = copy.deepcopy(base)
placeholder_expiry["review_expiry"] = "{{expiry}}"
run(placeholder_expiry, False, "review_expiry", "placeholder review expiry")

open_findings = copy.deepcopy(base)
open_findings["blocking_findings"] = [{"id": "F-1", "summary": "error path swallows exit codes"}]
run(open_findings, False, "unresolved blocking findings", "unresolved blocking finding")

findings_not_list = copy.deepcopy(base)
findings_not_list["blocking_findings"] = "none"
run(findings_not_list, False, "must be an array", "non-array blocking findings")

undocumented_exception = copy.deepcopy(exception_contract)
undocumented_exception["role_exception"]["reason"] = ""
run(undocumented_exception, False, "role_exception.reason", "exception with empty reason")

unauthorized_exception = copy.deepcopy(exception_contract)
del unauthorized_exception["role_exception"]["authorized_by"]
run(unauthorized_exception, False, "authorized_by", "exception without authorization source")

freeform_reason_code = copy.deepcopy(exception_contract)
freeform_reason_code["role_exception"]["reason_code"] = "reviewer was busy"
run(freeform_reason_code, False, "reason_code", "non-enumerated exception reason")

unknown_kind = copy.deepcopy(exception_contract)
unknown_kind["role_exception"]["kind"] = "pm_general_override"
run(unknown_kind, False, "role_exception.kind", "unknown exception kind")

old_schema = copy.deepcopy(base)
old_schema["schema_version"] = "review-acceptance-gate.v0"
run(old_schema, False, "schema_version must equal", "v0 contract fails closed")

template = gate.parent.parent / "templates" / "review-acceptance.example.json"
result = subprocess.run(
    [sys.executable, str(gate), str(template)],
    check=False,
    capture_output=True,
    text=True,
)
try:
    payload = json.loads(result.stdout)
    assert payload["ok"] is True, payload
    assert result.returncode == 0, result
    passed += 1
except AssertionError as exc:
    failed += 1
    print(f"FAIL example template must pass its own gate: {exc}")

print(f"review acceptance gate tests: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
