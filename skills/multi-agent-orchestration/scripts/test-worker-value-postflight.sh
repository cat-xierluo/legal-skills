#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 - "${SCRIPT_DIR}/worker-value-postflight.py" <<'PY'
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile


postflight = Path(sys.argv[1])
work = Path(tempfile.mkdtemp(prefix="worker-value-postflight-"))
repo = work / "repo"

passed = 0
failed = 0


def git(*args: str, cwd: Path = repo) -> str:
    result = subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


git("init", "-q", str(repo), cwd=work)
git("config", "user.email", "postflight-test@example.invalid")
git("config", "user.name", "postflight test")
(repo / "skills" / "foo" / "scripts").mkdir(parents=True)
(repo / "skills" / "foo" / "docs").mkdir(parents=True)
(repo / "skills" / "foo" / "scripts" / "retry.py").write_text("def retry():\n    return False\n", encoding="utf-8")
git("add", ".")
git("commit", "-q", "-m", "base")
BASE = git("rev-parse", "HEAD")

(repo / "skills" / "foo" / "scripts" / "retry.py").write_text("def retry():\n    return True\n", encoding="utf-8")
(repo / "skills" / "foo" / "CHANGELOG.md").write_text("# fixed retry\n", encoding="utf-8")
git("add", ".")
git("commit", "-q", "-m", "fix retry + changelog")
HEAD = git("rev-parse", "HEAD")

impl_task = {
    "task_id": "TASK-IMPL",
    "status": "READY",
    "kind": "bugfix",
    "value_kind": "implementation",
    "value_identity": "retry-flag-fix",
    "problem_target": "scripts/retry.py retry flag never set",
    "consumer": "TASK-CONSUMER integration wave",
    "decision_or_gate_changed": "retry loop actually re-enters on failure",
    "engineering_assets": ["skills/foo/scripts/retry.py"],
    "doc_assets": ["skills/foo/CHANGELOG.md"],
    "verification_commands": ["python3 skills/foo/scripts/test_retry.py"],
    "worker_pr_policy": "worker_pr",
    "consume_by": "current wave",
    "expiry": "archive if consumer cancelled",
    "observable_acceptance": "test_retry.py green",
    "starts_external_resources": False,
    "resource_owner": "none",
    "state_transition": "",
}
gate_task = {
    "task_id": "TASK-GATE",
    "status": "READY",
    "kind": "merge-verification",
    "value_kind": "merge_gate",
    "problem_target": "PR #135 zero-diff merge verification",
    "consumer": "PM merge decision for PR #135",
    "decision_or_gate_changed": "accept or reject merge of PR #135",
    "gate_target": {"pr": "#135", "head_sha": HEAD},
    "engineering_assets": [],
    "worker_pr_policy": "no_worker_pr",
    "consume_by": "current wave",
    "expiry": "decision recorded then archived",
    "observable_acceptance": "decision reported against pinned head",
    "starts_external_resources": False,
    "resource_owner": "none",
    "state_transition": "",
}

_spec_counter = 0
_evidence_counter = 0


def spec(*tasks: dict) -> Path:
    global _spec_counter
    _spec_counter += 1
    payload = {
        "schema_version": "dispatch-value-gate.v2",
        "mode": "converge",
        "pending_acceptance_prs": 0,
        "tasks": list(tasks),
    }
    path = work / f"spec-{_spec_counter}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def evidence(payload: dict) -> Path:
    global _evidence_counter
    _evidence_counter += 1
    path = work / f"evidence-{_evidence_counter}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def patch_file(name: str, *headers: tuple[str, str]) -> Path:
    path = work / name
    lines = []
    for old, new in headers:
        lines += [
            f"diff --git a/{old} b/{new}",
            f"--- a/{old}",
            f"+++ b/{new}",
            "@@ -1 +1 @@",
            "-a",
            "+b",
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def check(name, spec_path, task_id, evidence_path, expected_ok, contains="", extra=None):
    global passed, failed
    result = subprocess.run(
        [
            sys.executable, str(postflight),
            "--spec", str(spec_path),
            "--task-id", task_id,
            "--evidence", str(evidence_path),
            *(extra or []),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise AssertionError(
                f"non-JSON output (rc={result.returncode})\nstdout={result.stdout[-800:]}\nstderr={result.stderr[-1200:]}"
            )
        assert "ok" in payload and "errors" in payload and "report" in payload, payload
        assert payload["ok"] is expected_ok, payload
        assert (result.returncode == 0) is expected_ok, result
        if contains:
            assert any(contains in error for error in payload["errors"]), payload
        passed += 1
        return payload
    except AssertionError as exc:
        failed += 1
        print(f"FAIL {name}: {exc}")
        return {}


ok_evidence = evidence({"executed": [{"command": "python3 skills/foo/scripts/test_retry.py", "exit_code": 0}]})

payload = check(
    "implementation diff + evidence passes",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL", ok_evidence, True,
    extra=["--repo", str(repo), "--base", BASE, "--head", HEAD],
)
if payload and payload["report"]["matched_engineering_assets"] != ["skills/foo/scripts/retry.py"]:
    failed += 1
    print(f"FAIL engineering asset match: {payload['report']}")
else:
    passed += 1

docs_only = patch_file(
    "docs-only.diff",
    ("skills/foo/CHANGELOG.md", "skills/foo/CHANGELOG.md"),
)
check(
    "docs-only actual diff fails",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL", ok_evidence, False, "engineering asset",
    extra=["--diff", str(docs_only)],
)

outside = patch_file(
    "outside.diff",
    ("undeclared/src.py", "undeclared/src.py"),
    ("skills/foo/scripts/retry.py", "skills/foo/scripts/retry.py"),
)
check(
    "changed path outside declared assets fails",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL", ok_evidence, False, "outside declared",
    extra=["--diff", str(outside)],
)

empty = work / "empty.diff"
empty.write_text("", encoding="utf-8")
check(
    "zero diff without merge gate fails",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL", ok_evidence, False, "zero diff",
    extra=["--diff", str(empty)],
)

check(
    "merge gate zero diff + decision passes",
    spec(copy.deepcopy(gate_task)), "TASK-GATE",
    evidence({"decision": "accept", "verified_head": HEAD}), True,
    extra=["--repo", str(repo), "--base", BASE, "--head", BASE],
)
payload = check(
    "merge gate reports decision consumer",
    spec(copy.deepcopy(gate_task)), "TASK-GATE",
    evidence({"decision": "reject"}), True,
    extra=["--repo", str(repo), "--base", BASE, "--head", BASE],
)
if payload and (payload["report"].get("decision") != "reject"
                or payload["report"].get("decision_consumer") != "PM merge decision for PR #135"):
    failed += 1
    print(f"FAIL decision consumer: {payload['report']}")
else:
    passed += 1

noisy = patch_file(
    "noisy.diff",
    ("skills/foo/scripts/retry.py", "skills/foo/scripts/retry.py"),
)
check(
    "merge gate with non-zero diff fails",
    spec(copy.deepcopy(gate_task)), "TASK-GATE",
    evidence({"decision": "accept", "verified_head": HEAD}), False, "zero diff",
    extra=["--diff", str(noisy)],
)

floating = copy.deepcopy(gate_task)
floating["gate_target"]["head_sha"] = "release-branch"
check(
    "merge gate floating head fails",
    spec(floating), "TASK-GATE",
    evidence({"decision": "accept"}), False, "40-hex",
    extra=["--repo", str(repo), "--base", BASE, "--head", BASE],
)

mismatch = copy.deepcopy(gate_task)
mismatch["gate_target"]["head_sha"] = "0" * 40
check(
    "verified_head mismatch fails",
    spec(mismatch), "TASK-GATE",
    evidence({"decision": "accept", "verified_head": HEAD}), False, "verified_head",
    extra=["--repo", str(repo), "--base", BASE, "--head", BASE],
)

check(
    "unexecuted verification command fails",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL",
    evidence({"executed": [{"command": "python3 other.py", "exit_code": 0}]}), False,
    "verification evidence missing",
    extra=["--repo", str(repo), "--base", BASE, "--head", HEAD],
)

check(
    "failed verification exit code fails",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL",
    evidence({"executed": [{"command": "python3 skills/foo/scripts/test_retry.py", "exit_code": 1}]}), False,
    "exit_code=1",
    extra=["--repo", str(repo), "--base", BASE, "--head", HEAD],
)

bad_json = work / "bad.json"
bad_json.write_text("{not json", encoding="utf-8")
check(
    "malformed evidence fails closed",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL", bad_json, False, "invalid JSON",
    extra=["--repo", str(repo), "--base", BASE, "--head", HEAD],
)

generic = copy.deepcopy(impl_task)
generic.pop("value_kind")
generic["engineering_assets"] = []
check(
    "generic review task fails contract revalidation",
    spec(generic), "TASK-IMPL", ok_evidence, False, "value_kind must be one of",
    extra=["--repo", str(repo), "--base", BASE, "--head", HEAD],
)

check(
    "incomplete diff source fails",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL", ok_evidence, False, "--repo, --base and --head",
    extra=["--repo", str(repo)],
)

check(
    "unknown task id fails",
    spec(copy.deepcopy(impl_task)), "TASK-NOPE", ok_evidence, False, "not found in spec",
    extra=["--repo", str(repo), "--base", BASE, "--head", HEAD],
)

print(f"worker value postflight tests: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
