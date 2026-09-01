#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 - "${SCRIPT_DIR}/dispatch-value-gate.py" <<'PY'
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile


gate = Path(sys.argv[1])
base = {
    "schema_version": "dispatch-value-gate.v2",
    "mode": "converge",
    "pending_acceptance_prs": 0,
    "tasks": [{
        "task_id": "TASK-1",
        "status": "READY",
        "kind": "bugfix",
        "value_kind": "implementation",
        "value_identity": "quota-retry-double-charge",
        "problem_target": "scripts/quota-retry.py double-charges on 429 retry",
        "consumer": "TASK-2 integration wave",
        "decision_or_gate_changed": "retry no longer double-charges provider quota",
        "engineering_assets": ["skills/foo/scripts/quota-retry.py"],
        "doc_assets": ["skills/foo/CHANGELOG.md"],
        "verification_commands": ["bash skills/foo/scripts/test-quota-retry.sh"],
        "worker_pr_policy": "worker_pr",
        "consume_by": "current wave",
        "expiry": "archive fix branch if TASK-2 is cancelled",
        "observable_acceptance": "test-quota-retry.sh green on failing replay case",
        "starts_external_resources": False,
        "resource_owner": "none",
        "state_transition": "",
    }],
}

merge_gate_task = {
    "task_id": "TASK-GATE",
    "status": "READY",
    "kind": "merge-verification",
    "value_kind": "merge_gate",
    "value_identity": "pr-135-zero-diff-verify",
    "problem_target": "PR #135 zero-diff merge verification",
    "consumer": "PM merge decision for PR #135",
    "decision_or_gate_changed": "accept or reject merge of PR #135",
    "gate_target": {
        "pr": "#135",
        "head_sha": "11ce3e04b6348327d3447a367f4decb6ad2e80f9",
    },
    "engineering_assets": [],
    "worker_pr_policy": "no_worker_pr",
    "consume_by": "current wave",
    "expiry": "decision recorded then task archived",
    "observable_acceptance": "dispatch reports accept/reject against the pinned head",
    "starts_external_resources": False,
    "resource_owner": "none",
    "state_transition": "",
}


passed = 0
failed = 0


def run(spec, expected_ok, contains="", label=""):
    global passed, failed
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
        json.dump(spec, handle)
        handle.flush()
        result = subprocess.run(
            [sys.executable, str(gate), handle.name, "--now", "2026-09-01T00:00:00Z"],
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


run(base, True, label="valid implementation passes")
run({**copy.deepcopy(base), "tasks": base["tasks"] + [copy.deepcopy(merge_gate_task)]}, True, label="valid merge gate passes")

fixture = copy.deepcopy(base)
fixture["tasks"][0].update({
    "value_kind": "reusable_verification",
    "kind": "fixture",
    "value_identity": "wave-replay-fixture",
    "problem_target": "replayable 429 retry fixture for consumer tests",
    "decision_or_gate_changed": "consumer test suite gains deterministic retry fixture",
    "engineering_assets": ["skills/foo/tests/fixtures/retry_429.json"],
    "verification_commands": ["python3 skills/foo/tests/test_fixture_contract.py"],
})
run(fixture, True, label="reusable fixture asset passes")

integration = copy.deepcopy(base)
integration["tasks"][0].update({
    "worker_pr_policy": "integration_pr",
    "integration_target": "integration/wave-2026-09-01",
})
run(integration, True, label="implementation folded into named integration PR passes")

missing_consumer = copy.deepcopy(base)
missing_consumer["tasks"][0]["consumer"] = "{{named_consumer}}"
run(missing_consumer, False, "consumer", "missing consumer")

draft = copy.deepcopy(base)
draft["tasks"][0]["status"] = "DRAFT"
run(draft, False, "status must be READY", "draft task")

docs_kind = copy.deepcopy(base)
docs_kind["tasks"][0]["kind"] = "docs"
run(docs_kind, False, "not a dispatchable value task", "docs kind")

research_kind = copy.deepcopy(base)
research_kind["tasks"][0]["kind"] = "research"
run(research_kind, False, "not a dispatchable value task", "research kind")

generic = copy.deepcopy(base)
generic["tasks"][0].pop("value_kind")
run(generic, False, "value_kind must be one of", "generic investigation without value_kind")

cleanup = copy.deepcopy(base)
cleanup["tasks"][0].update({
    "value_kind": "cleanup",
    "kind": "cleanup",
})
run(cleanup, False, "value_kind must be one of", "format cleanup value_kind rejected")

missing_identity = copy.deepcopy(base)
missing_identity["tasks"][0].pop("value_identity")
run(missing_identity, False, "value_identity is required", "missing value_identity")

placeholder_identity = copy.deepcopy(base)
placeholder_identity["tasks"][0]["value_identity"] = "tbd"
run(placeholder_identity, False, "value_identity is required", "placeholder value_identity")

missing_target = copy.deepcopy(base)
missing_target["tasks"][0]["problem_target"] = "tbd"
run(missing_target, False, "problem_target", "placeholder problem target")

docs_only_assets = copy.deepcopy(base)
docs_only_assets["tasks"][0]["engineering_assets"] = ["skills/foo/README.md", "skills/foo/docs/guide.md"]
run(docs_only_assets, False, "non-document engineering_assets", "docs-only deliverable plan")

placeholder_asset = copy.deepcopy(base)
placeholder_asset["tasks"][0]["engineering_assets"] = ["{{code_path}}"]
run(placeholder_asset, False, "placeholder", "placeholder engineering asset")

no_verification = copy.deepcopy(base)
no_verification["tasks"][0]["verification_commands"] = []
run(no_verification, False, "requires verification_commands", "implementation without verification")

integration_no_target = copy.deepcopy(base)
integration_no_target["tasks"][0].update({
    "worker_pr_policy": "integration_pr",
    "integration_target": "tbd",
})
run(integration_no_target, False, "integration_target", "integration_pr without named target")

gate_floating_head = copy.deepcopy(base)
gate_task = copy.deepcopy(merge_gate_task)
gate_task["gate_target"]["head_sha"] = "release-branch-head"
gate_floating_head["tasks"].append(gate_task)
run(gate_floating_head, False, "40-hex", "merge gate floating head")

gate_worker_pr = copy.deepcopy(base)
gate_worker_pr["tasks"].append({**copy.deepcopy(merge_gate_task), "worker_pr_policy": "worker_pr"})
run(gate_worker_pr, False, "no_worker_pr", "merge gate with worker PR")

gate_integration_pr = copy.deepcopy(base)
gate_integration_pr["tasks"].append({**copy.deepcopy(merge_gate_task), "worker_pr_policy": "integration_pr"})
run(gate_integration_pr, False, "no_worker_pr", "merge gate with integration_pr")

gate_with_assets = copy.deepcopy(base)
gate_task_assets = copy.deepcopy(merge_gate_task)
gate_task_assets["engineering_assets"] = ["scripts/verify-pr.py"]
gate_with_assets["tasks"].append(gate_task_assets)
run(gate_with_assets, False, "must not declare engineering_assets", "merge gate with assets")

impl_no_pr = copy.deepcopy(base)
impl_no_pr["tasks"][0]["worker_pr_policy"] = "no_worker_pr"
run(impl_no_pr, False, "only valid for merge_gate", "implementation with no_worker_pr")

duplicate_identity = copy.deepcopy(base)
twin = copy.deepcopy(base["tasks"][0])
twin["task_id"] = "TASK-TWIN"
duplicate_identity["tasks"].append(twin)
run(duplicate_identity, False, "subsumed", "duplicate value identity")

subsumed_target = copy.deepcopy(base)
cousin = copy.deepcopy(base["tasks"][0])
cousin["task_id"] = "TASK-COUSIN"
cousin["value_identity"] = "different-explicit-id"
subsumed_target["tasks"].append(cousin)
run(subsumed_target, False, "subsumed", "subsumed problem target")

too_many = copy.deepcopy(base)
too_many["tasks"] = []
for index in range(4):
    item = copy.deepcopy(base["tasks"][0])
    item["task_id"] = f"TASK-{index}"
    item["value_identity"] = f"identity-{index}"
    item["problem_target"] = f"module-{index} distinct defect"
    too_many["tasks"].append(item)
run(too_many, False, "at most 3", "converge concurrency cap")

backpressure = copy.deepcopy(base)
backpressure["pending_acceptance_prs"] = 3
run(backpressure, False, "acceptance backpressure", "acceptance backpressure")

unowned_service = copy.deepcopy(base)
unowned_service["tasks"][0]["starts_external_resources"] = True
unowned_service["tasks"][0]["resource_owner"] = "none"
run(unowned_service, False, "resource_owner", "unowned external resource")

explore = copy.deepcopy(too_many)
explore["mode"] = "explore"
explore["explore_authorized_by"] = "user 2026-09-01"
explore["explore_expires_at"] = "2026-09-02T00:00:00+00:00"
run(explore, True, label="explore window permits 4 workers")

expired = copy.deepcopy(explore)
expired["explore_expires_at"] = "2026-08-31T00:00:00+00:00"
run(expired, False, "expired", "expired explore window")

old_schema = copy.deepcopy(base)
old_schema["schema_version"] = "dispatch-value-gate.v1"
run(old_schema, False, "schema_version must equal", "v1 spec fails closed")

template = gate.parent.parent / "templates" / "dispatch-value-gate.example.json"
result = subprocess.run(
    [sys.executable, str(gate), str(template), "--now", "2026-09-01T00:00:00Z"],
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

print(f"dispatch value gate tests: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
