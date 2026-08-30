#!/usr/bin/env python3
"""Offline contract and fault-injection selftest for autopilot-facts.py."""

from __future__ import annotations

import hashlib
import json
import datetime as dt
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
COLLECTOR = HERE / "autopilot-facts.py"
REQUEST_CONTRACT = "multi-agent-orchestration.autopilot-facts-request.v1"
MANIFEST_CONTRACT = "multi-agent-orchestration.autopilot-facts-bindings.v1"
PROJECT_CONTRACT = "multi-agent-orchestration.autopilot-project-probe.v1"
PROVIDER_CONTRACT = "multi-agent-orchestration.autopilot-provider-probe.v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv: list[str], cwd: Path) -> str:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"command failed ({result.returncode}): {argv!r}: {result.stderr}")
    return result.stdout.strip()


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o700)


class Fixture:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="autopilot-facts-selftest-")
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.remote = self.root / "remote.git"
        self.repo.mkdir()
        run(["git", "init", "-q"], self.repo)
        run(["git", "config", "user.name", "Facts Selftest"], self.repo)
        run(["git", "config", "user.email", "facts@example.invalid"], self.repo)
        run(["git", "switch", "-qc", "feat-task-x"], self.repo)
        self.evidence = self.repo / "TASKS.fixture.json"
        self.evidence.write_text('{"Task-X":"complete"}\n', encoding="utf-8")
        self.gate_contract = self.repo / "VERIFY.fixture.json"
        self.gate_contract.write_text('{"gate":"fixture-v1"}\n', encoding="utf-8")
        (self.repo / "README.md").write_text("fixture\n", encoding="utf-8")
        run(["git", "add", "README.md", self.evidence.name, self.gate_contract.name], self.repo)
        run(["git", "commit", "-qm", "fixture"], self.repo)
        run(["git", "init", "--bare", "-q", str(self.remote)], self.root)
        run(["git", "remote", "add", "origin", str(self.remote)], self.repo)
        run(["git", "push", "-qu", "origin", "feat-task-x"], self.repo)
        run(["git", "push", "-q", "origin", "HEAD:main"], self.repo)
        self.oid = run(["git", "rev-parse", "HEAD"], self.repo)
        common_raw = run(["git", "rev-parse", "--git-common-dir"], self.repo)
        candidate = Path(common_raw)
        self.common = (self.repo / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        self.repo_identity = hashlib.sha256(str(self.common).encode("utf-8")).hexdigest()
        self.log = self.root / "calls.jsonl"
        self.orca_config = self.root / "orca.json"
        self.gh_config = self.root / "gh.json"
        self.project_config = self.root / "project.json"
        self.provider_config = self.root / "provider.json"
        self.git_wrapper = self.root / "git-wrapper.py"
        self.orca = self.root / "fake-orca.py"
        self.gh = self.root / "fake-gh.py"
        self.project_probe = self.root / "fake-project.py"
        self.provider_probe = self.root / "fake-provider.py"
        real_git = Path(shutil.which("git") or "").resolve()
        write_executable(
            self.git_wrapper,
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            f"log=pathlib.Path({str(self.log)!r})\n"
            "with log.open('a', encoding='utf-8') as f: f.write(json.dumps({'tool':'git','argv':sys.argv[1:]})+'\\n')\n"
            f"os.execv({str(real_git)!r}, [{str(real_git)!r}, *sys.argv[1:]])\n",
        )
        common_fake = (
            "#!/usr/bin/env python3\n"
            "import json, pathlib, subprocess, sys, time\n"
            "config=json.loads(pathlib.Path(sys.argv[1]).read_text())\n"
            "if config.get('state_path'): config.update(json.loads(pathlib.Path(config['state_path']).read_text()))\n"
            "log=pathlib.Path(config['log'])\n"
            "with log.open('a', encoding='utf-8') as f: f.write(json.dumps({'tool':config['tool'],'argv':sys.argv[2:]})+'\\n')\n"
            "if config.get('stderr'): print(config['stderr'], file=sys.stderr)\n"
            "if config.get('child_marker'):\n"
            "  code='import pathlib,time;time.sleep(1);pathlib.Path('+repr(config['child_marker'])+').write_text(\"survived\")'\n"
            "  subprocess.Popen([sys.executable,'-c',code])\n"
            "if config.get('sleep'): time.sleep(float(config['sleep']))\n"
            "if config.get('huge'): print('X'*int(config['huge'])); raise SystemExit(0)\n"
            "if config.get('malformed'): print('{broken'); raise SystemExit(0)\n"
            "key=' '.join(sys.argv[2:4])\n"
            "payload=config.get('responses',{}).get(key,config['payload'])\n"
            "print(json.dumps(payload))\n"
        )
        write_executable(self.orca, common_fake)
        write_executable(self.gh, common_fake)
        probe_fake = (
            "#!/usr/bin/env python3\n"
            "import json, pathlib, subprocess, sys, time\n"
            "config=json.loads(pathlib.Path(sys.argv[1]).read_text())\n"
            "request=json.load(sys.stdin)\n"
            "log=pathlib.Path(config['log'])\n"
            "with log.open('a', encoding='utf-8') as f: f.write(json.dumps({'tool':config['tool'],'request':request})+'\\n')\n"
            "if config.get('stderr'): print(config['stderr'], file=sys.stderr)\n"
            "if config.get('child_marker'):\n"
            "  code='import pathlib,time;time.sleep(1);pathlib.Path('+repr(config['child_marker'])+').write_text(\"survived\")'\n"
            "  subprocess.Popen([sys.executable,'-c',code])\n"
            "if config.get('sleep'): time.sleep(float(config['sleep']))\n"
            "if config.get('huge'): print('X'*int(config['huge'])); raise SystemExit(0)\n"
            "if config.get('malformed'): print('{broken'); raise SystemExit(0)\n"
            "payload=dict(config['payload'])\n"
            "for key in ('request_id','task_id'): payload[key]=request[key]\n"
            "if 'provider' in request: payload['provider']=request['provider']\n"
            "if 'evidence_sha256' in request: payload['evidence_sha256']=request['evidence_sha256']\n"
            "print(json.dumps(payload))\n"
        )
        write_executable(self.project_probe, probe_fake)
        write_executable(self.provider_probe, probe_fake)
        self._write_default_configs()
        self.manifest_path = self.root / "bindings.json"
        self.manifest = self._manifest()
        self.write_manifest()
        self.request = self._request()

    def _write_json(self, path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")

    def _write_default_configs(self) -> None:
        self._write_json(self.orca_config, {
            "tool": "orca", "log": str(self.log),
            "payload": {"ok": True, "result": {
                "dispatch": {"id": "ctx-task-x", "task_id": "task-orca-x",
                             "run_id": "run-fixture", "status": "completed"},
                "worker": {"dispatch_id": "ctx-task-x", "state": "succeeded"},
                "observation": {"status": "exited"},
            }},
        })
        self._write_json(self.gh_config, {
            "tool": "gh", "log": str(self.log),
            "payload": [{
                "number": 17, "state": "MERGED",
                "statusCheckRollup": [{"name": "ci/test", "conclusion": "SUCCESS"}],
                "mergeable": "MERGEABLE", "reviews": [{"state": "APPROVED",
                    "submittedAt": "2026-08-30T00:00:00Z", "author": {"login": "reviewer"},
                    "commit": {"oid": self.oid}}],
                "headRefOid": self.oid, "headRefName": "feat-task-x", "baseRefName": "main",
                "mergeCommit": {"oid": self.oid},
            }],
        })
        self._write_json(self.project_config, {
            "tool": "project", "log": str(self.log),
            "payload": {"schema_version": 1, "contract": PROJECT_CONTRACT,
                        "status": "complete", "writeback_applied": True,
                        "verification": {"passed": True, "local_oid": self.oid,
                                         "gate_contract_sha256": digest(self.gate_contract)},
                        "writeback": {"task_id": "Task-X", "merge_commit": self.oid,
                                      "policy_commit": self.oid}},
        })
        self._write_json(self.provider_config, {
            "tool": "provider", "log": str(self.log),
            "payload": {"schema_version": 1, "contract": PROVIDER_CONTRACT,
                        "status": "available", "retry_at": None},
        })

    def _manifest(self) -> dict[str, Any]:
        return {
            "schema_version": 1, "contract": MANIFEST_CONTRACT,
            "repo_identity": self.repo_identity, "project_id": "project-fixture",
            "policy_commit": self.oid, "run_id": "run-fixture",
            "repo": {"root": str(self.repo), "common_dir": str(self.common),
                     "github_repo": "example/fixture", "git_remote": "origin"},
            "tools": {
                "git": {"argv": [str(self.git_wrapper)], "sha256": digest(self.git_wrapper), "read_only": True},
                "orca": {"argv": [str(self.orca), str(self.orca_config)], "sha256": digest(self.orca),
                         "read_only": True, "pinned_files": [{"path": str(self.orca_config), "sha256": digest(self.orca_config)}]},
                "gh": {"argv": [str(self.gh), str(self.gh_config)], "sha256": digest(self.gh),
                       "read_only": True, "pinned_files": [{"path": str(self.gh_config), "sha256": digest(self.gh_config)}]},
            },
            "items": [{
                "task_id": "Task-X", "orca_task_id": "task-orca-x",
                "branch": "feat-task-x", "worktree": str(self.repo), "provider": "fixture/provider",
                "pr": {"base_branch": "main", "required_checks": ["ci/test"],
                       "required_approvals": 1},
                "project_probe": {"argv": [str(self.project_probe), str(self.project_config)],
                                  "sha256": digest(self.project_probe), "read_only": True,
                                  "pinned_files": [{"path": str(self.project_config), "sha256": digest(self.project_config)}],
                                  "evidence_path": str(self.evidence), "evidence_sha256": digest(self.evidence),
                                  "gate_contract_path": str(self.gate_contract),
                                  "gate_contract_sha256": digest(self.gate_contract)},
                "provider_probe": {"argv": [str(self.provider_probe), str(self.provider_config)],
                                   "sha256": digest(self.provider_probe), "read_only": True,
                                   "pinned_files": [{"path": str(self.provider_config), "sha256": digest(self.provider_config)}]},
            }],
        }

    def _request(self) -> dict[str, Any]:
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        return {
            "schema_version": 1, "contract": REQUEST_CONTRACT, "request_id": "request-fixture",
            "adapter_sha256": digest(COLLECTOR),
            "manifest_sha256": digest(self.manifest_path),
            "issued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "deadline": (now + dt.timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "repo": {"root": str(self.repo), "common_dir": str(self.common), "identity": self.repo_identity},
            "project": {"project_id": "project-fixture", "policy_commit": self.oid},
            "run_id": "run-fixture",
            "items": [{"task_id": "Task-X", "attempt": 1, "dispatch_id": "ctx-task-x",
                       "orca_task_id": "task-orca-x",
                       "branch": "feat-task-x", "worktree": str(self.repo),
                       "provider": "fixture/provider", "pr_number": 17, "pr_head_oid": self.oid}],
        }

    def write_manifest(self) -> None:
        self._write_json(self.manifest_path, self.manifest)
        if hasattr(self, "request"):
            self.request["manifest_sha256"] = digest(self.manifest_path)

    def repin_configs(self) -> None:
        self.manifest["tools"]["orca"]["pinned_files"][0]["sha256"] = digest(self.orca_config)
        self.manifest["tools"]["gh"]["pinned_files"][0]["sha256"] = digest(self.gh_config)
        for item in self.manifest["items"]:
            item["project_probe"]["pinned_files"][0]["sha256"] = digest(self.project_config)
            item["provider_probe"]["pinned_files"][0]["sha256"] = digest(self.provider_config)
        self.write_manifest()

    def invoke(self, *, timeout: float = 2.0, manifest_path: Path | None = None,
               request: dict[str, Any] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(COLLECTOR), "--manifest", str(manifest_path or self.manifest_path),
             "--timeout-seconds", str(timeout)],
            input=json.dumps(request or self.request), capture_output=True, text=True,
            cwd=self.repo, check=False,
        )

    def close(self) -> None:
        self.temp.cleanup()


def with_fixture(test: Callable[[Fixture], None]) -> None:
    fixture = Fixture()
    try:
        test(fixture)
    finally:
        fixture.close()


def case_happy_and_zero_mutation(f: Fixture) -> None:
    before = {path.name: digest(path) for path in (f.evidence, f.gate_contract, f.manifest_path)}
    before_git = run(["git", "status", "--porcelain=v1"], f.repo)
    result = f.invoke()
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["contract"] == "multi-agent-orchestration.autopilot-facts.v1"
    assert payload["request_id"] == "request-fixture" and payload["adapter_sha256"] == digest(COLLECTOR)
    assert payload["manifest_sha256"] == digest(f.manifest_path)
    assert payload["issued_at"] <= payload["started_at"] <= payload["finished_at"] <= payload["deadline"]
    assert all(source["started_at"] <= source["finished_at"] for source in payload["sources"])
    assert payload["ambiguous"] is False
    item = payload["items"][0]
    assert item["dispatch"]["status"] == "completed"
    assert item["git"]["dirty"] is False and item["git"]["published"] is True
    assert item["git"]["branch_matches"] is True and item["git"]["worktree_count"] == 1
    assert item["pr"]["state"] == "merged" and item["pr"]["checks"] == "pass"
    assert item["project"]["writeback_applied"] is True and item["verification"]["passed"] is True
    assert item["verification"]["local_oid"] == f.oid
    assert item["verification"]["gate_contract_sha256"] == digest(f.gate_contract)
    assert item["provider"]["status"] == "available"
    assert before == {path.name: digest(path) for path in (f.evidence, f.gate_contract, f.manifest_path)}
    assert before_git == run(["git", "status", "--porcelain=v1"], f.repo)
    calls = [json.loads(line) for line in f.log.read_text(encoding="utf-8").splitlines()]
    git_calls = [entry["argv"] for entry in calls if entry["tool"] == "git"]
    allowed_operations = {"rev-parse", "cat-file", "check-ref-format", "worktree", "symbolic-ref", "status", "remote", "ls-remote", "merge-base"}
    for argv in git_calls:
        assert len(argv) >= 3 and argv[0] == "-C"
        assert argv[2] in allowed_operations
        if argv[2] == "worktree":
            assert argv[3:] == ["list", "--porcelain", "-z"]
    assert any(entry["tool"] == "orca" and entry["argv"][:2] == ["orchestration", "worker-show"] for entry in calls)
    assert any(entry["tool"] == "gh" and entry["argv"][:2] == ["pr", "list"] for entry in calls)
    for entry in calls:
        if entry["tool"] in {"project", "provider"}:
            assert entry["request"]["mode"] == "read_only"


def case_unknown_checks(f: Fixture) -> None:
    config = json.loads(f.gh_config.read_text())
    config["payload"][0]["statusCheckRollup"] = [{}]
    f._write_json(f.gh_config, config)
    f.repin_configs()
    result = f.invoke()
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["items"][0]["pr"]["checks"] == "unknown"


def case_identity_drift(f: Fixture) -> None:
    config = json.loads(f.gh_config.read_text())
    config["payload"][0]["baseRefName"] = "release"
    f._write_json(f.gh_config, config)
    f.repin_configs()
    payload = json.loads(f.invoke().stdout)
    assert payload["ambiguous"] is True and payload["items"][0]["pr"]["state"] == "unknown"


def case_duplicate_pr(f: Fixture) -> None:
    config = json.loads(f.gh_config.read_text())
    duplicate = dict(config["payload"][0])
    duplicate["number"] = 18
    config["payload"].append(duplicate)
    f._write_json(f.gh_config, config)
    f.repin_configs()
    payload = json.loads(f.invoke().stdout)
    assert payload["ambiguous"] is True and "Task-X:pr_duplicate" in payload["ambiguity_codes"]


def case_timeout(f: Fixture) -> None:
    config = json.loads(f.project_config.read_text())
    config["sleep"] = 3
    f._write_json(f.project_config, config)
    f.repin_configs()
    result = f.invoke(timeout=1.0)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["items"][0]["project"]["status"] == "unknown"
    assert any(source["source"] == "project:Task-X" and source["status"] == "timeout" for source in payload["sources"])


def case_malformed_external_and_input(f: Fixture) -> None:
    config = json.loads(f.gh_config.read_text())
    config["malformed"] = True
    f._write_json(f.gh_config, config)
    f.repin_configs()
    result = f.invoke()
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["items"][0]["pr"]["state"] == "unknown" and payload["ambiguous"] is True
    malformed = f.root / "malformed.json"
    malformed.write_text("{broken", encoding="utf-8")
    result = f.invoke(manifest_path=malformed)
    assert result.returncode == 65


def case_symlink_rejected(f: Fixture) -> None:
    link = f.root / "bindings-link.json"
    link.symlink_to(f.manifest_path)
    assert f.invoke(manifest_path=link).returncode == 65
    real = f.root / "evidence-real.json"
    real.write_text("{}\n", encoding="utf-8")
    evidence_link = f.root / "evidence-link.json"
    evidence_link.symlink_to(real)
    f.manifest["items"][0]["project_probe"]["evidence_path"] = str(evidence_link)
    f.write_manifest()
    assert f.invoke().returncode == 65


def case_command_missing(f: Fixture) -> None:
    f.manifest["tools"]["gh"]["argv"][0] = str(f.root / "missing-gh")
    f.write_manifest()
    assert f.invoke().returncode == 69


def case_request_and_probe_identity(f: Fixture) -> None:
    request = json.loads(json.dumps(f.request))
    request["repo"]["identity"] = "0" * 64
    assert f.invoke(request=request).returncode == 66
    config = json.loads(f.orca_config.read_text())
    config["payload"]["result"]["worker"]["dispatch_id"] = "ctx-other"
    f._write_json(f.orca_config, config)
    f.repin_configs()
    payload = json.loads(f.invoke().stdout)
    assert payload["ambiguous"] is True and payload["items"][0]["dispatch"]["status"] == "unknown"


def case_manifest_and_config_digest_drift(f: Fixture) -> None:
    config = json.loads(f.gh_config.read_text())
    config["payload"] = []
    f._write_json(f.gh_config, config)
    result = f.invoke()
    assert result.returncode == 66 and "pinned file" in result.stderr
    f.repin_configs()
    pinned_request = json.loads(json.dumps(f.request))
    f.manifest_path.write_text(f.manifest_path.read_text() + " ", encoding="utf-8")
    result = f.invoke(request=pinned_request)
    assert result.returncode == 66 and "manifest digest mismatch" in result.stderr


def case_mutating_probe_argv_rejected(f: Fixture) -> None:
    f.manifest["items"][0]["project_probe"]["argv"].append("--write")
    f.write_manifest()
    result = f.invoke()
    assert result.returncode == 65 and "forbidden mutation argument" in result.stderr
    f.manifest["items"][0]["project_probe"]["argv"].pop()
    f.manifest["items"][0]["dispatch_id"] = "ctx-stale-manifest"
    f.write_manifest()
    result = f.invoke()
    assert result.returncode == 65 and "runtime-ledger dynamic fields" in result.stderr


def case_dispatch_contradiction_and_missing_echo(f: Fixture) -> None:
    config = json.loads(f.orca_config.read_text())
    config["payload"]["result"]["worker"]["state"] = "active"
    config["payload"]["result"]["observation"]["status"] = "active"
    f._write_json(f.orca_config, config)
    f.repin_configs()
    payload = json.loads(f.invoke().stdout)
    assert payload["ambiguous"] is True
    assert payload["items"][0]["dispatch"]["status"] == "unknown"
    config["payload"]["result"]["worker"]["state"] = "succeeded"
    config["payload"]["result"]["observation"]["status"] = "exited"
    del config["payload"]["result"]["dispatch"]["run_id"]
    f._write_json(f.orca_config, config)
    f.repin_configs()
    payload = json.loads(f.invoke().stdout)
    assert payload["items"][0]["dispatch"]["status"] == "unknown"
    assert "Task-X:dispatch_identity" in payload["ambiguity_codes"]
    discovered = config["payload"]["result"]["dispatch"]
    config["payload"] = {"ok": True, "result": {"dispatch": discovered,
        "dispatches": [discovered]}}
    f.request["items"][0]["dispatch_id"] = None
    f._write_json(f.orca_config, config)
    f.repin_configs()
    payload = json.loads(f.invoke().stdout)
    assert payload["items"][0]["dispatch"]["status"] == "unknown"
    assert "Task-X:dispatch_discovery_ambiguous" in payload["ambiguity_codes"]


def case_stale_verification_and_writeback(f: Fixture) -> None:
    config = json.loads(f.project_config.read_text())
    config["payload"]["verification"]["local_oid"] = "0" * 40
    f._write_json(f.project_config, config)
    f.repin_configs()
    payload = json.loads(f.invoke().stdout)
    assert payload["items"][0]["verification"]["passed"] == "unknown"
    assert payload["items"][0]["verification"]["local_oid"] is None
    assert payload["items"][0]["verification"]["gate_contract_sha256"] is None
    assert "Task-X:verification_stale" in payload["ambiguity_codes"]
    config["payload"]["verification"]["local_oid"] = f.oid
    config["payload"]["writeback"]["merge_commit"] = "1" * 40
    f._write_json(f.project_config, config)
    f.repin_configs()
    payload = json.loads(f.invoke().stdout)
    assert payload["items"][0]["project"]["writeback_applied"] == "unknown"
    assert "Task-X:writeback_stale" in payload["ambiguity_codes"]


def case_absent_expected_worktree(f: Fixture) -> None:
    absent = f.root / "absent-worker"
    item = f.manifest["items"][0]
    item["worktree"] = str(absent)
    item["branch"] = "feat-cleanup"
    request_item = f.request["items"][0]
    request_item.update({"worktree": str(absent), "branch": "feat-cleanup"})
    gh = json.loads(f.gh_config.read_text())
    gh["payload"][0]["headRefName"] = "feat-cleanup"
    f._write_json(f.gh_config, gh)
    f.repin_configs()
    result = f.invoke()
    assert result.returncode == 0, result.stderr
    facts = json.loads(result.stdout)["items"][0]
    assert facts["git"]["worktree_count"] == 0
    assert facts["git"]["dirty"] is False and facts["git"]["branch_matches"] is True
    assert facts["dispatch"]["status"] == "completed" and facts["pr"]["state"] == "merged"
    assert facts["project"]["writeback_applied"] is True


def case_secret_output_not_leaked(f: Fixture) -> None:
    secret = "SECRET-DO-NOT-LEAK-71d6"
    config = json.loads(f.gh_config.read_text())
    config["stderr"] = secret
    config["payload"] = {"unexpected": secret}
    f._write_json(f.gh_config, config)
    f.repin_configs()
    result = f.invoke()
    assert result.returncode == 0
    assert secret not in result.stdout and secret not in result.stderr
    assert json.loads(result.stdout)["items"][0]["pr"]["state"] == "unknown"


def case_required_gate_contract(f: Fixture) -> None:
    config = json.loads(f.gh_config.read_text())
    config["payload"][0]["statusCheckRollup"] = [{"name": "ci/other", "conclusion": "SUCCESS"}]
    f._write_json(f.gh_config, config)
    f.repin_configs()
    payload = json.loads(f.invoke().stdout)
    pr = payload["items"][0]["pr"]
    assert pr["checks"] == "unknown" and pr["required_checks"] == ["ci/test"]
    assert "Task-X:required_check_missing" in payload["ambiguity_codes"]
    config["payload"][0]["statusCheckRollup"] = [{"name": "ci/test", "conclusion": "SUCCESS"}]
    config["payload"][0]["reviews"] = []
    f._write_json(f.gh_config, config)
    f.repin_configs()
    pr = json.loads(f.invoke().stdout)["items"][0]["pr"]
    assert pr["checks"] == "pending" and pr["approvals"] == 0 and pr["required_approvals"] == 1


def case_pr_adopt_by_exact_identity(f: Fixture) -> None:
    f.request["items"][0]["pr_number"] = None
    f.request["items"][0]["pr_head_oid"] = None
    result = f.invoke()
    assert result.returncode == 0, result.stderr
    pr = json.loads(result.stdout)["items"][0]["pr"]
    assert pr["number"] == 17 and pr["adopted"] is True and pr["head_oid"] == f.oid


def case_freshness_retry_and_process_group(f: Fixture) -> None:
    expired = json.loads(json.dumps(f.request))
    expired["issued_at"] = "2026-01-01T00:00:00Z"
    expired["deadline"] = "2026-01-01T00:01:00Z"
    assert f.invoke(request=expired).returncode == 66
    config = json.loads(f.provider_config.read_text())
    config["payload"]["status"] = "waiting_reset"
    config["payload"]["retry_at"] = "tomorrow"
    f._write_json(f.provider_config, config)
    f.repin_configs()
    payload = json.loads(f.invoke().stdout)
    assert payload["items"][0]["provider"]["status"] == "unknown"
    project = json.loads(f.project_config.read_text())
    project["huge"] = 2 * 1024 * 1024
    f._write_json(f.project_config, project)
    f.repin_configs()
    payload = json.loads(f.invoke().stdout)
    assert payload["items"][0]["project"]["status"] == "unknown"
    assert any(source["source"] == "project:Task-X" and source["status"] == "output_limit" for source in payload["sources"])
    marker = f.root / "child-survived"
    project.pop("huge")
    project["child_marker"] = str(marker)
    project["sleep"] = 2
    f._write_json(f.project_config, project)
    f.repin_configs()
    result = f.invoke(timeout=0.5)
    assert result.returncode == 0, result.stderr
    time.sleep(1.2)
    assert not marker.exists()


def case_git_remote_and_ref_safety(f: Fixture) -> None:
    run(["git", "remote", "set-url", "origin", "ext::malicious-helper"], f.repo)
    payload = json.loads(f.invoke().stdout)
    git_facts = payload["items"][0]["git"]
    assert git_facts["published"] == "unknown"
    assert "Task-X:unsafe_remote_url" in payload["ambiguity_codes"]
    f.manifest["items"][0]["branch"] = "-unsafe"
    f.request["items"][0]["branch"] = "-unsafe"
    f.write_manifest()
    assert f.invoke().returncode == 65


def case_dynamic_dispatch_and_pr_lifecycle(f: Fixture) -> None:
    orca_config = json.loads(f.orca_config.read_text())
    gh_config = json.loads(f.gh_config.read_text())
    worker_payload = orca_config.pop("payload")
    pr_payload = gh_config.pop("payload")
    orca_state = f.root / "orca-state.json"
    gh_state = f.root / "gh-state.json"
    orca_config["state_path"] = str(orca_state)
    gh_config["state_path"] = str(gh_state)
    f._write_json(f.orca_config, orca_config)
    f._write_json(f.gh_config, gh_config)
    f._write_json(orca_state, {"payload": {"ok": True, "result": {"dispatch": None}}})
    f._write_json(gh_state, {"payload": []})
    f.repin_configs()
    f.request["items"][0]["dispatch_id"] = None
    f.request["items"][0]["pr_number"] = None
    f.request["items"][0]["pr_head_oid"] = None
    first = f.invoke()
    assert first.returncode == 0, first.stderr
    first_item = json.loads(first.stdout)["items"][0]
    assert first_item["dispatch"]["status"] == "missing" and first_item["pr"]["state"] == "none"
    discovered = worker_payload["result"]["dispatch"]
    f._write_json(orca_state, {"payload": worker_payload,
        "responses": {"orchestration dispatch-show": {"ok": True, "result": {"dispatch": discovered}},
                      "orchestration worker-show": worker_payload}})
    f._write_json(gh_state, {"payload": pr_payload})
    second = f.invoke()
    assert second.returncode == 0, second.stderr
    second_item = json.loads(second.stdout)["items"][0]
    assert second_item["dispatch"]["id"] == "ctx-task-x" and second_item["dispatch"]["status"] == "completed"
    assert second_item["pr"]["number"] == 17 and second_item["pr"]["adopted"] is True
    assert f.request["manifest_sha256"] == digest(f.manifest_path)


def case_request_subset_after_completed_item(f: Fixture) -> None:
    second = json.loads(json.dumps(f.manifest["items"][0]))
    second.update({"task_id": "Task-Y", "orca_task_id": "task-orca-y",
                   "branch": "feat-task-y", "worktree": str(f.root / "worker-y")})
    f.manifest["items"].append(second)
    orca = json.loads(f.orca_config.read_text())
    orca["payload"] = {"ok": True, "result": {"dispatch": None}}
    gh = json.loads(f.gh_config.read_text())
    gh["payload"] = []
    project = json.loads(f.project_config.read_text())
    project["payload"]["status"] = "in_progress"
    project["payload"]["writeback_applied"] = False
    f._write_json(f.orca_config, orca)
    f._write_json(f.gh_config, gh)
    f._write_json(f.project_config, project)
    f.request["items"] = [{
        "task_id": "Task-Y", "attempt": 1, "dispatch_id": None, "orca_task_id": "task-orca-y",
        "branch": "feat-task-y", "worktree": str(f.root / "worker-y"),
        "provider": "fixture/provider", "pr_number": None, "pr_head_oid": None,
    }]
    f.repin_configs()
    result = f.invoke()
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [item["task_id"] for item in payload["items"]] == ["Task-Y"]
    assert all("Task-X" not in source["source"] for source in payload["sources"])
    outside = json.loads(json.dumps(f.request))
    outside["items"][0]["task_id"] = "Task-Z"
    assert f.invoke(request=outside).returncode == 66


CASES: list[tuple[str, Callable[[Fixture], None]]] = [
    ("happy facts and zero mutation", case_happy_and_zero_mutation),
    ("unknown checks remain unknown", case_unknown_checks),
    ("PR identity drift fails closed", case_identity_drift),
    ("duplicate PR is ambiguous", case_duplicate_pr),
    ("probe timeout is bounded", case_timeout),
    ("malformed external/input JSON fails closed", case_malformed_external_and_input),
    ("symlink bindings/evidence rejected", case_symlink_rejected),
    ("missing command has stable exit", case_command_missing),
    ("request/probe identity drift rejected", case_request_and_probe_identity),
    ("manifest/config digests are pinned", case_manifest_and_config_digest_drift),
    ("mutating probe argv is rejected", case_mutating_probe_argv_rejected),
    ("Dispatch contradictions and missing echoes fail closed", case_dispatch_contradiction_and_missing_echo),
    ("stale verification/writeback cannot pass", case_stale_verification_and_writeback),
    ("absent expected worktree is observable", case_absent_expected_worktree),
    ("child output secrets are not leaked", case_secret_output_not_leaked),
    ("required checks and approvals are exact", case_required_gate_contract),
    ("unbound PR is adopted only by exact identity", case_pr_adopt_by_exact_identity),
    ("freshness, retry_at and process-group timeout", case_freshness_retry_and_process_group),
    ("Git remote helpers and unsafe refs are rejected", case_git_remote_and_ref_safety),
    ("null Dispatch and PR converge after external creation", case_dynamic_dispatch_and_pr_lifecycle),
    ("completed manifest items are filtered from request", case_request_subset_after_completed_item),
]


def main() -> int:
    passed = 0
    for name, case in CASES:
        try:
            with_fixture(case)
            print(f"PASS: {name}")
            passed += 1
        except Exception as exc:
            print(f"FAIL: {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
    print(f"autopilot facts tests: {passed}/{len(CASES)} passed")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
