#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 - "${SCRIPT_DIR}/dispatch-value-gate.py" <<'PY'
from __future__ import annotations

import copy
import json
import os
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


def run(spec, expected_ok, contains="", label="", receipt=None):
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
        if receipt is not None:
            for key, value in receipt.items():
                assert payload["capacity"][key] == value, payload
        passed += 1
    except AssertionError as exc:
        failed += 1
        print(f"FAIL {label or contains}: {exc}")


run(base, True, label="valid implementation passes")
run({**copy.deepcopy(base), "tasks": base["tasks"] + [copy.deepcopy(merge_gate_task)]}, True, label="valid merge gate passes")


def distinct_tasks(count):
    tasks = []
    for index in range(count):
        item = copy.deepcopy(base["tasks"][0])
        item["task_id"] = f"TASK-{index}"
        item["value_identity"] = f"identity-{index}"
        item["problem_target"] = f"module-{index} distinct defect"
        tasks.append(item)
    return tasks

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

converge_at_cap = copy.deepcopy(base)
converge_at_cap["tasks"] = distinct_tasks(8)
run(converge_at_cap, True, label="legacy converge permits 8 candidate workers", receipt={"count_scope": "candidate_only", "active_workers": None, "candidate_workers": 8, "planned_total": 8, "effective_worker_limit": 8, "inventory_verified": False, "atomic_reservation": False})

too_many = copy.deepcopy(base)
too_many["tasks"] = distinct_tasks(9)
run(too_many, False, "at most 8 candidate workers", "converge candidate cap")

pending_at_cap = copy.deepcopy(base)
pending_at_cap["pending_acceptance_prs"] = 4
run(pending_at_cap, True, label="pending acceptance PRs at 4 passes")

backpressure = copy.deepcopy(base)
backpressure["pending_acceptance_prs"] = 5
run(backpressure, False, "acceptance backpressure", "acceptance backpressure")

unowned_service = copy.deepcopy(base)
unowned_service["tasks"][0]["starts_external_resources"] = True
unowned_service["tasks"][0]["resource_owner"] = "none"
run(unowned_service, False, "resource_owner", "unowned external resource")

explore = copy.deepcopy(base)
explore["mode"] = "explore"
explore["explore_authorized_by"] = "user 2026-09-01"
explore["explore_expires_at"] = "2026-09-02T00:00:00+00:00"
explore["tasks"] = distinct_tasks(10)
run(explore, True, label="explore window permits 10 workers")

explore_over_cap = copy.deepcopy(explore)
explore_over_cap["tasks"] = distinct_tasks(11)
run(explore_over_cap, False, "at most 10 candidate workers", "explore candidate cap")

expired = copy.deepcopy(explore)
expired["explore_expires_at"] = "2026-08-31T00:00:00+00:00"
run(expired, False, "expired", "expired explore window")

old_schema = copy.deepcopy(base)
old_schema["schema_version"] = "dispatch-value-gate.v1"
run(old_schema, False, "schema_version must equal", "v1 spec fails closed")


# Optional inventory is a declaration, never a live observation/reservation.
capacity_base = copy.deepcopy(base)
capacity_base["capacity"] = {
    "active_workers": 7, "worker_limit": 8,
    "scope": "Shared PMs: platform + project-a",
    "inventory_ref": "PM inventory snapshot receipt 2026-09-01",
}
run(capacity_base, True, label="declared active plus candidate at 8", receipt={
    "count_scope": "pm_declared_shared_inventory", "candidate_workers": 1,
    "active_workers": 7, "planned_total": 8, "effective_worker_limit": 8,
    "inventory_verified": False, "atomic_reservation": False,
    "scope": capacity_base["capacity"]["scope"],
    "inventory_ref": capacity_base["capacity"]["inventory_ref"],
})
active_over = copy.deepcopy(capacity_base)
active_over["capacity"]["active_workers"] = 8
run(active_over, False, "declared total 9", "existing active workers consume capacity")
small_cap = copy.deepcopy(capacity_base)
small_cap["capacity"].update(active_workers=1, worker_limit=2)
run(small_cap, True, label="project smaller cap boundary", receipt={"planned_total": 2, "effective_worker_limit": 2})
small_over = copy.deepcopy(small_cap)
small_over["tasks"] = distinct_tasks(2)
run(small_over, False, "effective limit 2", "project cap applies to active plus wave")
zero_cap = copy.deepcopy(capacity_base)
zero_cap["capacity"].update(active_workers=0, worker_limit=0)
run(zero_cap, False, "effective limit 0", "zero project cap parks nonempty wave")
zero_active = copy.deepcopy(capacity_base)
zero_active["capacity"]["active_workers"] = 0
run(zero_active, True, label="zero active is valid", receipt={"active_workers": 0, "planned_total": 1})
explore_capacity = copy.deepcopy(explore)
explore_capacity["tasks"] = distinct_tasks(2)
explore_capacity["capacity"] = {**capacity_base["capacity"], "active_workers": 8, "worker_limit": 10}
run(explore_capacity, True, label="authorized explore declared total at 10", receipt={"planned_total": 10, "effective_worker_limit": 10})
explore_capacity_over = copy.deepcopy(explore_capacity)
explore_capacity_over["capacity"]["active_workers"] = 9
run(explore_capacity_over, False, "declared total 11", "explore declared total cap")
explore_unauthorized = copy.deepcopy(explore_capacity)
explore_unauthorized.pop("explore_authorized_by")
run(explore_unauthorized, False, "requires explore_authorized_by", "inventory cannot authorize explore")
capacity_pending = copy.deepcopy(capacity_base)
capacity_pending["pending_acceptance_prs"] = 5
run(capacity_pending, False, "acceptance backpressure", "inventory cannot bypass pending backpressure")

for bad in (None, [], "inventory", False, 0):
    invalid = copy.deepcopy(base)
    invalid["capacity"] = bad
    run(invalid, False, "capacity must be an object", f"reject capacity {bad!r}", receipt={"count_scope": "invalid_capacity"})
for field in capacity_base["capacity"]:
    missing = copy.deepcopy(capacity_base)
    missing["capacity"].pop(field)
    run(missing, False, "capacity missing fields", f"missing capacity {field}")
for field in ("active_workers", "worker_limit"):
    for bad in (-1, True, False, "1", 1.0, None, [], {}):
        invalid = copy.deepcopy(capacity_base)
        invalid["capacity"][field] = bad
        run(invalid, False, f"capacity.{field} must be", f"reject {field} {bad!r}")
for field in ("scope", "inventory_ref"):
    for bad in ("", "tbd", "{{name}}", "bad\ncontrol", True, 1, [], None):
        invalid = copy.deepcopy(capacity_base)
        invalid["capacity"][field] = bad
        run(invalid, False, f"capacity.{field} must name", f"reject {field} {bad!r}")
for mode, oversized_limit in (("converge", 9), ("explore", 11)):
    invalid = copy.deepcopy(capacity_base if mode == "converge" else explore_capacity)
    invalid["capacity"]["worker_limit"] = oversized_limit
    run(invalid, False, "cannot exceed", f"reject {mode} limit widening")
extra = copy.deepcopy(capacity_base)
extra["capacity"]["override"] = True
run(extra, False, "unsupported fields", "inventory rejects extra bypass field")
# No new time-based capacity expiry: replaying the declaration preserves its
# arithmetic result, while its scope/evidence remain explicitly unverified.
replay = copy.deepcopy(capacity_base)
replay["capacity"]["inventory_ref"] = "Historical PM inventory receipt 2020-01-01, replay-only evidence"
run(replay, True, label="inventory declaration has no invented freshness gate", receipt={"inventory_verified": False})

# Actual no-spec CLI, with poisoned local configuration and missing spec:
# a read would fail, and the fixture filesystem must remain unchanged.
with tempfile.TemporaryDirectory(prefix="policy-description-") as temporary:
    root = Path(temporary)
    (root / ".claude").mkdir()
    (root / ".claude" / "orchestration.config.json").write_text("INVALID JSON")
    (root / "config").mkdir()
    (root / "config" / "orchestration-personal.json").write_text("INVALID JSON")
    before = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    for args in (("--describe-policy",),):
        result = subprocess.run(
            [sys.executable, str(gate), *args], cwd=root,
            env={**os.environ, "HOME": str(root), "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, check=False,
        )
        try:
            payload = json.loads(result.stdout)
            assert result.returncode == 0 and payload["ok"] is True, result
            assert payload["status"] == "policy_description", payload
            assert payload["contract_evaluated"] is False and payload["accepted"] is False, payload
            policy = payload["policy"]
            assert policy["worker_limits"] == {"converge": 8, "explore": 10}, policy
            assert policy["max_pending_acceptance_prs"] == 4, policy
            assert set(policy["count_scopes"]) == {"candidate_only", "pm_declared_shared_inventory"}, policy
            assert policy["inventory_verified"] is False and policy["atomic_reservation"] is False, policy
            assert "active_workers excludes this wave" in policy["count_scopes"]["pm_declared_shared_inventory"], policy
            assert policy["limitations"], policy
            after = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            assert before == after, (before, after)
            assert sorted(str(path.relative_to(root)) for path in root.rglob("*")) == [".claude", ".claude/orchestration.config.json", "config", "config/orchestration-personal.json"]
            passed += 1
        except (AssertionError, ValueError) as exc:
            failed += 1
            print(f"FAIL read-only policy description {args}: {exc}")

    for args in ((str(root / "missing-spec.json"), "--describe-policy"), ("--describe-policy", "--now", "invalid-time"), ()):
        result = subprocess.run([sys.executable, str(gate), *args], cwd=root,
            env={**os.environ, "HOME": str(root), "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, check=False)
        try:
            assert result.returncode == 2, result
            assert not result.stdout, result
            assert "cannot be combined" in result.stderr if args else "required: spec" in result.stderr, result
            assert before == {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            passed += 1
        except AssertionError as exc:
            failed += 1
            print(f"FAIL policy/contract separation {args}: {exc}")

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
