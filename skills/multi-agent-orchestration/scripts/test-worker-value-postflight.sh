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
    "value_identity": "pr-135-zero-diff-verify",
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


ok_evidence = evidence({
    "executed": [{"command": "python3 skills/foo/scripts/test_retry.py", "exit_code": 0}],
    "verified_head": HEAD,
})
stale_evidence = evidence({
    "executed": [{"command": "python3 skills/foo/scripts/test_retry.py", "exit_code": 0}],
    "verified_head": BASE,
})
no_head_evidence = evidence({
    "executed": [{"command": "python3 skills/foo/scripts/test_retry.py", "exit_code": 0}],
})

payload = check(
    "implementation diff + bound evidence passes",
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
noisy = patch_file(
    "noisy.diff",
    ("skills/foo/scripts/retry.py", "skills/foo/scripts/retry.py"),
)
check(
    "docs-only actual diff fails",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL", ok_evidence, False, "engineering asset",
    extra=["--diff", str(docs_only), "--delivery-head", HEAD],
)

readme_only = patch_file(
    "readme-only.diff",
    ("skills/foo/README.md", "skills/foo/README.md"),
)
mixed_docs = patch_file(
    "mixed-docs.diff",
    ("skills/foo/scripts/retry.py", "skills/foo/scripts/retry.py"),
    ("skills/foo/README.md", "skills/foo/README.md"),
)
broad = copy.deepcopy(impl_task)
broad["engineering_assets"] = ["skills/foo"]
broad["value_identity"] = "broad-dir-fix"

check(
    "broad engineering dir cannot rescue docs-only diff",
    spec({**copy.deepcopy(broad), "doc_assets": ["skills/foo/README.md"]}), "TASK-IMPL", ok_evidence, False,
    "engineering asset",
    extra=["--diff", str(readme_only), "--delivery-head", HEAD],
)

payload = check(
    "broad engineering dir + real source + declared accompanying README passes",
    spec({**copy.deepcopy(broad), "doc_assets": ["skills/foo/README.md"]}), "TASK-IMPL", ok_evidence, True,
    extra=["--diff", str(mixed_docs), "--delivery-head", HEAD],
)
if payload and payload["report"]["matched_engineering_assets"] != ["skills/foo"]:
    failed += 1
    print(f"FAIL broad dir engineering match: {payload['report']}")
else:
    passed += 1

check(
    "undeclared actual document path stays outside-contract",
    spec({**copy.deepcopy(broad), "doc_assets": ["skills/foo/CHANGELOG.md"]}), "TASK-IMPL", ok_evidence, False,
    "outside declared",
    extra=["--diff", str(readme_only), "--delivery-head", HEAD],
)

outside = patch_file(
    "outside.diff",
    ("undeclared/src.py", "undeclared/src.py"),
    ("skills/foo/scripts/retry.py", "skills/foo/scripts/retry.py"),
)
check(
    "changed path outside declared assets fails",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL", ok_evidence, False, "outside declared",
    extra=["--diff", str(outside), "--delivery-head", HEAD],
)

empty = work / "empty.diff"
empty.write_text("", encoding="utf-8")
check(
    "zero diff without merge gate fails",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL", ok_evidence, False, "zero diff",
    extra=["--diff", str(empty), "--delivery-head", HEAD],
)

check(
    "patch-mode delivery with evidence head bound to --delivery-head passes",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL", ok_evidence, True,
    extra=["--diff", str(noisy), "--delivery-head", HEAD],
)

check(
    "merge gate pinned target compared to itself passes",
    spec(copy.deepcopy(gate_task)), "TASK-GATE",
    evidence({"decision": "accept", "verified_head": HEAD}), True,
    extra=["--repo", str(repo), "--base", HEAD, "--head", HEAD],
)

payload = check(
    "merge gate reports decision consumer",
    spec(copy.deepcopy(gate_task)), "TASK-GATE",
    evidence({"decision": "reject", "verified_head": HEAD}), True,
    extra=["--repo", str(repo), "--base", HEAD, "--head", HEAD],
)
if payload and (payload["report"].get("decision") != "reject"
                or payload["report"].get("decision_consumer") != "PM merge decision for PR #135"):
    failed += 1
    print(f"FAIL decision consumer: {payload['report']}")
else:
    passed += 1

check(
    "merge gate with non-zero diff fails",
    spec(copy.deepcopy(gate_task)), "TASK-GATE",
    evidence({"decision": "accept", "verified_head": HEAD}), False, "zero diff",
    extra=["--diff", str(noisy), "--delivery-head", HEAD],
)

check(
    "evidence without verified_head fails",
    spec(copy.deepcopy(gate_task)), "TASK-GATE",
    evidence({"decision": "accept"}), False, "verified_head",
    extra=["--repo", str(repo), "--base", HEAD, "--head", HEAD],
)

check(
    "stale evidence head fails in patch mode",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL", stale_evidence, False,
    "verified_head does not match the resolved delivery head",
    extra=["--diff", str(noisy), "--delivery-head", HEAD],
)

check(
    "git head different from merge target fails",
    spec(copy.deepcopy(gate_task)), "TASK-GATE",
    evidence({"decision": "accept", "verified_head": BASE}), False,
    "gate_target.head_sha",
    extra=["--repo", str(repo), "--base", BASE, "--head", BASE],
)

mismatch = copy.deepcopy(gate_task)
mismatch["gate_target"]["head_sha"] = "0" * 40
check(
    "evidence/target head mismatch fails",
    spec(mismatch), "TASK-GATE",
    evidence({"decision": "accept", "verified_head": HEAD}), False,
    "gate_target.head_sha",
    extra=["--repo", str(repo), "--base", HEAD, "--head", HEAD],
)

check(
    "patch mode without --delivery-head fails",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL", ok_evidence, False, "--delivery-head",
    extra=["--diff", str(noisy)],
)

check(
    "non-hex --delivery-head fails",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL", ok_evidence, False, "40-hex",
    extra=["--diff", str(noisy), "--delivery-head", "release-branch"],
)

floating = copy.deepcopy(gate_task)
floating["gate_target"]["head_sha"] = "release-branch"
check(
    "merge gate floating head fails",
    spec(floating), "TASK-GATE",
    evidence({"decision": "accept", "verified_head": HEAD}), False, "40-hex",
    extra=["--repo", str(repo), "--base", HEAD, "--head", HEAD],
)

check(
    "unexecuted verification command fails",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL",
    evidence({"executed": [{"command": "python3 other.py", "exit_code": 0}], "verified_head": HEAD}), False,
    "verification evidence missing",
    extra=["--repo", str(repo), "--base", BASE, "--head", HEAD],
)

check(
    "failed verification exit code fails",
    spec(copy.deepcopy(impl_task)), "TASK-IMPL",
    evidence({"executed": [{"command": "python3 skills/foo/scripts/test_retry.py", "exit_code": 1}], "verified_head": HEAD}), False,
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
