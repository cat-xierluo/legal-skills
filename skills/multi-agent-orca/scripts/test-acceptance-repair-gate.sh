#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 - "${SCRIPT_DIR}/acceptance-repair-gate.py" <<'PY'
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile


gate = Path(sys.argv[1])
work = Path(tempfile.mkdtemp(prefix="acceptance-repair-gate-"))
repo = work / "repo"
NOW = "2026-09-02T00:00:00Z"

passed = 0
failed = 0


def git(*args: str, cwd: Path = repo) -> str:
    result = subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


git("init", "-q", "-b", "main", str(repo), cwd=work)
git("config", "user.email", "repair-gate-test@example.invalid")
git("config", "user.name", "repair gate test")
docs = repo / "docs" / "badminton"
docs.mkdir(parents=True)
(repo / "docs" / "badminton" / "review.md").write_text("# review\n", encoding="utf-8")
(repo / "docs" / "badminton" / "usage.md").write_text("# usage\n", encoding="utf-8")
(repo / "scripts").mkdir()
(repo / "scripts" / "scoring.py").write_text("def score():\n    return 0\n", encoding="utf-8")
git("add", ".")
git("commit", "-q", "-m", "initial")
git("switch", "-qc", "fix-badminton-docs")
(docs / "review.md").write_text("# review v2\n", encoding="utf-8")
git("add", ".")
git("commit", "-q", "-m", "pr head at contract time")
PINNED = git("rev-parse", "HEAD")

# delivery：在 pinned 之上的真实修复 commit（改 scoped 文档）
(docs / "review.md").write_text("# review v3 — addresses BLOCKER-001\n", encoding="utf-8")
git("add", ".")
git("commit", "-q", "-m", "repair: address blocker docs")
DELIVERY = git("rev-parse", "HEAD")

_registry_counter = 0
_spec_counter = 0
_evidence_counter = 0


def registry_file(records: list | None = None) -> Path:
    global _registry_counter
    _registry_counter += 1
    path = work / f"registry-{_registry_counter}.json"
    path.write_text(json.dumps(records if records is not None else []), encoding="utf-8")
    return path


def spec_file(payload: dict) -> Path:
    global _spec_counter
    _spec_counter += 1
    path = work / f"spec-{_spec_counter}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def evidence_file(payload: dict) -> Path:
    global _evidence_counter
    _evidence_counter += 1
    path = work / f"evidence-{_evidence_counter}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


BASE_CONTRACT = {
    "schema_version": "acceptance-repair.v1",
    "target": {"pr": "#136", "branch": "fix-badminton-docs", "head_sha": PINNED},
    "integration_target": "fix-badminton-docs",
    "blockers": [
        {"id": "BLOCKER-001", "source": "review-acceptance-gate", "detail": "missing reviewer attribution section"},
        {"id": "BLOCKER-002", "source": "pm-rerun", "detail": "stale usage link"},
    ],
    "file_scope": ["docs/badminton/review.md", "docs/badminton/usage.md"],
    "consumer": "PR #136 acceptance closeout",
    "expiry": "2026-09-30T00:00:00+00:00",
    "verification_commands": ["bash scripts/check-docs.sh"],
    "repair_owner": "pm-badminton",
    "repair_attempts_used": 0,
    "re_review": {
        "worker_dispatch_id": "ctx_worker_1",
        "worker_session_id": "sess_worker_1",
        "reviewer_dispatch_id": "ctx_reviewer_1",
        "reviewer_session_id": "sess_reviewer_1",
    },
}

BASE_EVIDENCE = {
    "verified_head": DELIVERY,
    "repair_owner": "pm-badminton",
    "resolved_blockers": [
        {"id": "BLOCKER-001", "note": "reviewer attribution added to docs/badminton/review.md"},
        {"id": "BLOCKER-002", "note": "usage link refreshed"},
    ],
    "executed": [{"command": "bash scripts/check-docs.sh", "exit_code": 0}],
}


def run(mode: str, expected_ok: bool, contains: str = "", label: str = "", **kwargs) -> None:
    global passed, failed
    argv = [sys.executable, str(gate), mode]
    for key, value in kwargs.items():
        argv += [f"--{key.replace('_', '-')}", str(value)]
    argv += ["--now", NOW]
    result = subprocess.run(argv, check=False, capture_output=True, text=True)
    try:
        payload = json.loads(result.stdout)
        assert payload["ok"] is expected_ok, payload
        assert (result.returncode == 0) is expected_ok, result
        if contains:
            assert any(contains in error for error in payload["errors"]), (contains, payload)
        passed += 1
    except AssertionError as exc:
        failed += 1
        print(f"FAIL {label or contains}: {exc}")


def preflight(contract: dict, expected_ok: bool, contains: str = "", label: str = "", records=None) -> None:
    run("preflight", expected_ok, contains, label,
        spec=spec_file(contract), registry=registry_file(records))


def postflight(contract: dict, evidence: dict, expected_ok: bool, contains: str = "",
               label: str = "", records=None, **diff_kwargs) -> None:
    kwargs = {"spec": spec_file(contract), "registry": registry_file(records),
              "evidence": evidence_file(evidence)}
    kwargs.update(diff_kwargs)
    run("postflight", expected_ok, contains, label, **kwargs)


# -- preflight ------------------------------------------------------------------

preflight(BASE_CONTRACT, expected_ok=True, label="valid contract passes preflight")

bad = copy.deepcopy(BASE_CONTRACT)
bad["target"]["head_sha"] = "release-head"
preflight(bad, expected_ok=False, contains="40-hex", label="floating head")

bad = copy.deepcopy(BASE_CONTRACT)
del bad["consumer"]
preflight(bad, expected_ok=False, contains="missing required fields", label="missing consumer")

bad = copy.deepcopy(BASE_CONTRACT)
bad["expiry"] = "tbd"
preflight(bad, expected_ok=False, contains="expiry", label="placeholder expiry")

bad = copy.deepcopy(BASE_CONTRACT)
bad["integration_target"] = "docs-improvements"
preflight(bad, expected_ok=False, contains="integration_target must equal target.branch",
          label="independent integration branch")

bad = copy.deepcopy(BASE_CONTRACT)
bad["file_scope"] = ["skills/badminton/scripts/scoring.py"]
preflight(bad, expected_ok=False, contains="docs-only", label="non-document scope")

bad = copy.deepcopy(BASE_CONTRACT)
bad["file_scope"] = ["../outside/secret.md"]
preflight(bad, expected_ok=False, contains="traversal", label="path traversal scope")

bad = copy.deepcopy(BASE_CONTRACT)
bad["blockers"] = [
    {"id": "BLOCKER-001", "source": "review", "detail": "a"},
    {"id": "BLOCKER-001", "source": "review", "detail": "b"},
]
preflight(bad, expected_ok=False, contains="duplicates", label="duplicate blocker ids")

bad = copy.deepcopy(BASE_CONTRACT)
bad["blockers"] = [{"id": "BLOCKER-001", "source": "review"}]
preflight(bad, expected_ok=False, contains="detail is required", label="blocker without detail")

bad = copy.deepcopy(BASE_CONTRACT)
bad["repair_attempts_used"] = 2
preflight(bad, expected_ok=False, contains="repair_attempts_used=2 has exhausted",
          label="budget exhausted must park instead")

bad = copy.deepcopy(BASE_CONTRACT)
bad["re_review"]["reviewer_dispatch_id"] = "ctx_worker_1"
preflight(bad, expected_ok=False, contains="self-review", label="self-review rejected")

bad = copy.deepcopy(BASE_CONTRACT)
bad["extra_field"] = "not allowed"
preflight(bad, expected_ok=False, contains="unsupported fields", label="unsupported top-level field")

bad = copy.deepcopy(BASE_CONTRACT)
bad["expiry"] = "2026-09-01T00:00:00+00:00"
preflight(bad, expected_ok=False, contains="already in the past", label="expired contract")

active = [{
    "pr": "#136", "head_sha": PINNED, "blocker_ids": ["BLOCKER-001"],
    "owner": "pm-other", "status": "active", "recorded_at": "2026-09-01T00:00:00Z",
}]
preflight(BASE_CONTRACT, records=active, expected_ok=False, contains="duplicate repair",
          label="duplicate same-head repair")

preflight(BASE_CONTRACT, records=[{**active[0], "head_sha": "1" * 40, "blocker_ids": ["BLOCKER-009"]}],
          expected_ok=False, contains="serialized owner", label="another active owner blocks")

preflight(BASE_CONTRACT, records=[{**active[0], "head_sha": "1" * 40, "owner": "pm-badminton"}],
          expected_ok=False, contains="duplicate repair", label="active blocker overlap")

preflight(BASE_CONTRACT, records=[{**active[0], "status": "superseded"}],
          expected_ok=True, label="superseded same-head record does not block")

preflight(BASE_CONTRACT, records=[{"pr": "#136"}],
          expected_ok=False, contains="registry[0] must be an object", label="malformed registry")

# -- postflight（git 模式）--------------------------------------------------------

postflight(BASE_CONTRACT, BASE_EVIDENCE, expected_ok=True, label="valid delivery passes postflight",
           repo=repo, base=PINNED, head=DELIVERY)

# 零 diff：直接从 pinned head 分出的空 commit
git("switch", "-qc", "empty-delivery", PINNED)
git("commit", "-q", "--allow-empty", "-m", "empty delivery on pinned")
EMPTY = git("rev-parse", "HEAD")
git("switch", "-q", "fix-badminton-docs")
postflight(BASE_CONTRACT, {**BASE_EVIDENCE, "verified_head": EMPTY},
           expected_ok=False, contains="zero diff", label="empty delivery", repo=repo, base=PINNED, head=EMPTY)

# 范围外修改
(docs / "usage.md").write_text("# usage updated\n", encoding="utf-8")
(repo / "scripts" / "scoring.py").write_text("def score():\n    return 1\n", encoding="utf-8")
git("add", ".")
git("commit", "-q", "-m", "repair with out-of-scope edit")
DRIFTY = git("rev-parse", "HEAD")
postflight(BASE_CONTRACT, {**BASE_EVIDENCE, "verified_head": DRIFTY},
           expected_ok=False, contains="outside the declared file_scope",
           label="out-of-scope edit", repo=repo, base=DRIFTY + "~1", head=DRIFTY)

# 非文档修改（.py 即使在 scope 目录内也不行——本通道 docs-only）
postflight({**BASE_CONTRACT, "file_scope": ["docs/badminton", "scripts"]},
           {**BASE_EVIDENCE, "verified_head": DRIFTY},
           expected_ok=False, contains="non-document changes",
           label="non-doc edit inside scope dir", repo=repo, base=DRIFTY + "~1", head=DRIFTY)

# head 漂移：delivery 不从 pinned head 派生
git("switch", "-qc", "divergent", "main")
(docs / "review.md").write_text("# divergent repair\n", encoding="utf-8")
git("add", ".")
git("commit", "-q", "-m", "divergent delivery")
DIVERGED = git("rev-parse", "HEAD")
git("switch", "-q", "fix-badminton-docs")
postflight(BASE_CONTRACT, {**BASE_EVIDENCE, "verified_head": DIVERGED},
           expected_ok=False, contains="head drift", label="divergent head", repo=repo, base=PINNED, head=DIVERGED)

# delivery head == pinned head（无新 commit）
postflight(BASE_CONTRACT, BASE_EVIDENCE, expected_ok=False,
           contains="delivery head equals the pinned target head",
           label="no-op delivery", repo=repo, base=PINNED, head=PINNED)

# evidence 绑定失败
postflight(BASE_CONTRACT, {**BASE_EVIDENCE, "verified_head": PINNED},
           expected_ok=False, contains="verified_head does not match",
           label="stale evidence head", repo=repo, base=PINNED, head=DELIVERY)

postflight(BASE_CONTRACT, {**BASE_EVIDENCE, "repair_owner": "pm-someone-else"},
           expected_ok=False, contains="repair_owner must equal",
           label="owner mismatch", repo=repo, base=PINNED, head=DELIVERY)

postflight(BASE_CONTRACT, {**BASE_EVIDENCE, "resolved_blockers": BASE_EVIDENCE["resolved_blockers"][:1]},
           expected_ok=False, contains="unresolved blockers remain",
           label="unresolved blocker", repo=repo, base=PINNED, head=DELIVERY)

postflight(BASE_CONTRACT, {**BASE_EVIDENCE,
                           "resolved_blockers": BASE_EVIDENCE["resolved_blockers"]
                           + [{"id": "BLOCKER-404", "note": "not in contract"}]},
           expected_ok=False, contains="not declared in the contract",
           label="unknown resolved id", repo=repo, base=PINNED, head=DELIVERY)

postflight(BASE_CONTRACT, {**BASE_EVIDENCE,
                           "executed": [{"command": "bash scripts/check-docs.sh", "exit_code": 1}]},
           expected_ok=False, contains="verification command failed",
           label="failing verification", repo=repo, base=PINNED, head=DELIVERY)

postflight(BASE_CONTRACT, {**BASE_EVIDENCE, "executed": []},
           expected_ok=False, contains="executed[]",
           label="missing verification evidence", repo=repo, base=PINNED, head=DELIVERY)

# patch 模式：无法证明 head 谱系 → fail-closed 拒绝（head drift 机械拒绝）
patch_path = work / "delivery.patch"
patch = subprocess.run(["git", "-C", str(repo), "diff", PINNED, DELIVERY],
                       check=True, capture_output=True, text=True).stdout
patch_path.write_text(patch, encoding="utf-8")
postflight(BASE_CONTRACT, BASE_EVIDENCE, expected_ok=False, contains="head drift",
           label="patch mode cannot prove ancestry", diff=patch_path, delivery_head=DELIVERY)

# 缺 registry
run("preflight", False, contains="registry", label="registry is required",
    spec=spec_file(BASE_CONTRACT), registry=work / "does-not-exist.json")

# 示例模板自洽（用空 registry 过 preflight）
template = gate.parent.parent / "templates" / "acceptance-repair.example.json"
run("preflight", True, label="example template passes its own gate",
    spec=template, registry=registry_file())

print(f"acceptance repair gate tests: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
PY
