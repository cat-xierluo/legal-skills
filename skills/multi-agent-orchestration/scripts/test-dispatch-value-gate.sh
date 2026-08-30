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
    "schema_version": "dispatch-value-gate.v1",
    "mode": "converge",
    "pending_acceptance_prs": 0,
    "tasks": [{
        "task_id": "TASK-1",
        "status": "READY",
        "kind": "fixture",
        "consumer": "TASK-2 implementation",
        "decision_or_gate_changed": "closes A1",
        "consume_by": "current wave",
        "expiry": "archive if TASK-2 is cancelled",
        "observable_acceptance": "consumer test invokes fixture",
        "starts_external_resources": False,
        "resource_owner": "none",
        "state_transition": "",
    }],
}


def run(spec, expected_ok, contains=""):
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
        json.dump(spec, handle)
        handle.flush()
        result = subprocess.run(
            [sys.executable, str(gate), handle.name, "--now", "2026-08-30T00:00:00Z"],
            check=False,
            capture_output=True,
            text=True,
        )
    payload = json.loads(result.stdout)
    assert payload["ok"] is expected_ok, payload
    assert (result.returncode == 0) is expected_ok, result
    if contains:
        assert any(contains in error for error in payload["errors"]), payload


run(base, True)

missing_consumer = copy.deepcopy(base)
missing_consumer["tasks"][0]["consumer"] = "{{named_consumer}}"
run(missing_consumer, False, "consumer")

draft = copy.deepcopy(base)
draft["tasks"][0]["status"] = "DRAFT"
run(draft, False, "status must be READY")

docs = copy.deepcopy(base)
docs["tasks"][0]["kind"] = "research"
run(docs, False, "state_transition")

too_many = copy.deepcopy(base)
too_many["tasks"] = []
for index in range(4):
    item = copy.deepcopy(base["tasks"][0])
    item["task_id"] = f"TASK-{index}"
    too_many["tasks"].append(item)
run(too_many, False, "at most 3")

backpressure = copy.deepcopy(base)
backpressure["pending_acceptance_prs"] = 3
run(backpressure, False, "acceptance backpressure")

unowned_service = copy.deepcopy(base)
unowned_service["tasks"][0]["starts_external_resources"] = True
unowned_service["tasks"][0]["resource_owner"] = "none"
run(unowned_service, False, "resource_owner")

explore = copy.deepcopy(too_many)
explore["mode"] = "explore"
explore["explore_authorized_by"] = "user 2026-08-30"
explore["explore_expires_at"] = "2026-08-31T00:00:00+00:00"
run(explore, True)

expired = copy.deepcopy(explore)
expired["explore_expires_at"] = "2026-08-29T00:00:00+00:00"
run(expired, False, "expired")

print("dispatch value gate tests: 9 passed, 0 failed")
PY
