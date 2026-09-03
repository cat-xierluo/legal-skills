#!/usr/bin/env python3
"""Offline fault-injection selftest for Task-066's L2 runtime core."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable

from autopilot_runtime import (
    ADAPTER_RECEIPT_CONTRACT,
    ControllerError,
    EXIT_CONFIG,
    EXIT_CONFLICT,
    EXIT_DATA,
    EXIT_USAGE,
    FACTS_CONTRACT,
    RuntimeContext,
    acquire_lease,
    atomic_write_json,
    collect_and_reconcile,
    execute_tick,
    init_runtime,
    load_state_snapshot,
    pending_intent_converged,
    reconcile,
    renew_lease,
    runtime_lock,
    status,
    write_ahead_transition,
)


POLICY = "a" * 40
PROJECT = "project-selftest"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


class Scenario:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="autopilot-l2-selftest-")
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Autopilot Selftest")
        git(self.repo, "config", "user.email", "autopilot@example.invalid")
        (self.repo / "README.md").write_text("fixture\n", encoding="utf-8")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-qm", "fixture")
        self.ctx = RuntimeContext(self.repo, create=True)
        self.fact_sequence = 0
        self.now = dt.datetime.now(dt.timezone.utc)
        self.item = {
            "task_id": "Task-X", "attempt": 1, "branch": "feat/task-x",
            "worktree": str(self.repo.resolve()), "dispatch_id": None,
            "provider": "fixture/provider", "pr_number": None,
            "last_heartbeat_at": None, "retry_at": None,
            "next_action": "inspect_dispatch", "status": "RUNNING",
        }
        init_runtime(self.ctx, PROJECT, POLICY, "wave-1", "run_fixture", [self.item])
        self.lease = acquire_lease(
            self.ctx, PROJECT, POLICY, "pm-a", 60,
            takeover=False, reason=None, now=self.now,
        )

    @property
    def token(self) -> int:
        return int(self.lease["fencing_token"])

    def close(self) -> None:
        self.temp.cleanup()

    def facts(
        self, *, dispatch: str = "active", dirty: Any = False,
        worktree_count: Any = 1, branch_matches: Any = True,
        published: Any = False, pr_state: str = "none",
        checks: str = "not_applicable", project_status: str = "in_progress",
        writeback: Any = False, provider: str = "available",
        verified: bool = False, merge_commit: str | None = None,
        ambiguous: bool = False,
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "contract": FACTS_CONTRACT,
            "repo_identity": self.ctx.repo_identity,
            "project_id": PROJECT,
            "policy_commit": POLICY,
            "observed_at": "2026-08-30T10:00:00Z",
            "ambiguous": ambiguous,
            "items": [{
                "task_id": "Task-X",
                "dispatch": {"status": dispatch},
                "git": {
                    "dirty": dirty, "worktree_count": worktree_count,
                    "branch_matches": branch_matches, "published": published,
                    "local_oid": "b" * 40, "remote_oid": "b" * 40 if published else None,
                },
                "pr": {
                    "state": pr_state, "checks": checks,
                    "number": 17 if pr_state != "none" else None,
                    "merge_commit": merge_commit,
                },
                "project": {"status": project_status, "writeback_applied": writeback},
                "provider": {"status": provider, "retry_at": "2026-08-31T00:00:00Z" if provider == "waiting_reset" else None},
                "verification": {"passed": verified},
            }],
        }


def expect_error(code: int, operation: Callable[[], Any]) -> str:
    try:
        operation()
    except ControllerError as exc:
        assert exc.code == code, f"expected exit {code}, got {exc.code}: {exc.message}"
        return exc.message
    raise AssertionError(f"expected ControllerError exit {code}")


def file_digest(path: Path) -> str | None:
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink():
        return f"symlink:{os.readlink(path)}"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_snapshot(scenario: Scenario) -> dict[str, Any]:
    return {
        name: file_digest(path)
        for name, path in {
            "state": scenario.ctx.state_path,
            "lease": scenario.ctx.lease_path,
            "events": scenario.ctx.events_path,
        }.items()
    }


def make_adapter(scenario: Scenario) -> tuple[Path, Path]:
    adapter = scenario.root / "adapter.py"
    counter = scenario.root / "adapter-count.txt"
    adapter.write_text(
        """#!/usr/bin/env python3
import json, os, pathlib, sys
request = json.load(sys.stdin)
counter = pathlib.Path(os.environ['AUTOPILOT_SELFTEST_COUNTER'])
count = int(counter.read_text() if counter.exists() else '0') + 1
counter.write_text(str(count))
print(json.dumps({
  'schema_version': 1,
  'contract': 'multi-agent-orchestration.autopilot-adapter-receipt.v1',
  'idempotency_key': request['intent']['idempotency_key'],
  'fencing_token': request['fencing_token'],
  'accepted': True,
  'receipt_id': 'receipt-' + str(count),
}))
""",
        encoding="utf-8",
    )
    adapter.chmod(0o700)
    return adapter, counter


def case_kill_takeover_adopts_without_spawn() -> dict[str, Any]:
    s = Scenario()
    try:
        before = status(s.ctx, PROJECT, POLICY)["state"]
        s.lease = acquire_lease(
            s.ctx, PROJECT, POLICY, "pm-b", 60, takeover=True,
            reason="previous PM process terminated", now=s.now + dt.timedelta(seconds=61),
        )
        result = reconcile(s.ctx, PROJECT, POLICY, "pm-b", s.token, s.facts(dispatch="missing"))
        after = status(s.ctx, PROJECT, POLICY)["state"]
        assert result["planned_action"]["action"] == "adopt"
        assert result["planned_action"]["external_mutation"] is False
        assert after["pending_intent"] is None
        assert after["fencing_token"] == before["fencing_token"] + 1
        return {"before_token": before["fencing_token"], "after_token": after["fencing_token"], "action": "adopt", "spawn_count": 0}
    finally:
        s.close()


def case_double_pm_and_old_token_zero_write() -> dict[str, Any]:
    s = Scenario()
    try:
        expect_error(EXIT_CONFLICT, lambda: acquire_lease(
            s.ctx, PROJECT, POLICY, "pm-b", 60, takeover=False, reason=None, now=s.now,
        ))
        old_token = s.token
        s.lease = acquire_lease(
            s.ctx, PROJECT, POLICY, "pm-b", 60, takeover=True,
            reason="lease expired after PM crash", now=s.now + dt.timedelta(seconds=61),
        )
        before = runtime_snapshot(s)
        expect_error(EXIT_CONFLICT, lambda: reconcile(
            s.ctx, PROJECT, POLICY, "pm-a", old_token, s.facts(dispatch="missing"),
        ))
        assert runtime_snapshot(s) == before
        return {"old_token": old_token, "new_token": s.token, "old_owner_runtime_writes": 0}
    finally:
        s.close()


def case_lost_message_completed_goes_verify() -> dict[str, Any]:
    s = Scenario()
    try:
        result = reconcile(s.ctx, PROJECT, POLICY, "pm-a", s.token, s.facts(dispatch="completed"))
        pending = status(s.ctx, PROJECT, POLICY)["state"]["pending_intent"]
        assert result["planned_action"]["action"] == "verify"
        assert pending["action"] == "verify" and pending["status"] == "planned"
        return {"dispatch_fact": "completed", "planned_action": "verify", "spawn_count": 0}
    finally:
        s.close()


def case_receipt_waits_for_external_fact() -> dict[str, Any]:
    s = Scenario()
    previous = os.environ.get("AUTOPILOT_SELFTEST_COUNTER")
    try:
        reconcile(s.ctx, PROJECT, POLICY, "pm-a", s.token, s.facts(dispatch="completed"))
        adapter, counter = make_adapter(s)
        os.environ["AUTOPILOT_SELFTEST_COUNTER"] = str(counter)
        tick = execute_tick(s.ctx, PROJECT, POLICY, "pm-a", s.token, adapter)
        second = execute_tick(s.ctx, PROJECT, POLICY, "pm-a", s.token, adapter)
        same_facts = reconcile(s.ctx, PROJECT, POLICY, "pm-a", s.token, s.facts(dispatch="completed"))
        current = status(s.ctx, PROJECT, POLICY)["state"]
        assert tick["mutation_count"] == 1 and second["mutation_count"] == 0
        assert counter.read_text() == "1"
        assert same_facts["disposition"] == "await_external_fact"
        assert current["state"] == "VERIFYING"
        return {"adapter_calls": 1, "state_after_receipt": current["state"], "external_fact_converged": False}
    finally:
        if previous is None:
            os.environ.pop("AUTOPILOT_SELFTEST_COUNTER", None)
        else:
            os.environ["AUTOPILOT_SELFTEST_COUNTER"] = previous
        s.close()


def case_writeback_crash_recovers_once() -> dict[str, Any]:
    s = Scenario()
    previous = os.environ.get("AUTOPILOT_SELFTEST_COUNTER")
    try:
        before = status(s.ctx, PROJECT, POLICY)["state"]
        planned = reconcile(s.ctx, PROJECT, POLICY, "pm-a", s.token, s.facts(
            dispatch="completed", published=True, pr_state="merged", checks="pass",
            writeback=False, merge_commit="c" * 40,
        ))
        assert planned["planned_action"]["action"] == "writeback"
        adapter, counter = make_adapter(s)
        os.environ["AUTOPILOT_SELFTEST_COUNTER"] = str(counter)

        class SimulatedCrash(Exception):
            pass

        try:
            execute_tick(
                s.ctx, PROJECT, POLICY, "pm-a", s.token, adapter,
                after_adapter_hook=lambda: (_ for _ in ()).throw(SimulatedCrash()),
            )
        except SimulatedCrash:
            pass
        else:
            raise AssertionError("simulated crash did not fire")
        assert counter.read_text() == "1"
        recovered = reconcile(s.ctx, PROJECT, POLICY, "pm-a", s.token, s.facts(
            dispatch="completed", published=True, pr_state="merged", checks="pass",
            project_status="complete", writeback=True, merge_commit="c" * 40,
        ))
        after = status(s.ctx, PROJECT, POLICY)["state"]
        assert recovered["planned_action"]["action"] == "complete"
        assert execute_tick(s.ctx, PROJECT, POLICY, "pm-a", s.token, adapter)["mutation_count"] == 0
        assert counter.read_text() == "1"
        return {"before_state": before["state"], "after_state": after["state"], "writeback_adapter_calls": 1}
    finally:
        if previous is None:
            os.environ.pop("AUTOPILOT_SELFTEST_COUNTER", None)
        else:
            os.environ["AUTOPILOT_SELFTEST_COUNTER"] = previous
        s.close()


def case_duplicate_worktree_adopt_then_reject() -> dict[str, Any]:
    s = Scenario()
    try:
        adopted = reconcile(s.ctx, PROJECT, POLICY, "pm-a", s.token, s.facts(dispatch="missing", worktree_count=1))
        rejected = reconcile(s.ctx, PROJECT, POLICY, "pm-a", s.token, s.facts(dispatch="missing", worktree_count=2))
        current = status(s.ctx, PROJECT, POLICY)["state"]
        assert adopted["planned_action"]["action"] == "adopt"
        assert rejected["planned_action"]["action"] == "reject_duplicate"
        assert current["state"] == "ERROR_RECONCILE_REQUIRED" and current["pending_intent"] is None
        return {"unique": "adopt", "duplicate": "reject_duplicate", "spawn_count": 0}
    finally:
        s.close()


def case_dirty_and_unknown_checks_fail_closed_without_delete() -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for label, facts_factory in (
        ("dirty", lambda s: s.facts(dirty=True)),
        ("unknown_checks", lambda s: s.facts(pr_state="open", checks="unknown")),
        ("ambiguous", lambda s: s.facts(ambiguous=True)),
    ):
        s = Scenario()
        try:
            marker = s.repo / f"keep-{label}.txt"
            marker.write_text("must remain\n", encoding="utf-8")
            result = reconcile(s.ctx, PROJECT, POLICY, "pm-a", s.token, facts_factory(s))
            current = status(s.ctx, PROJECT, POLICY)["state"]
            assert result["planned_action"]["action"] == "hard_park"
            assert current["state"] == "ERROR_RECONCILE_REQUIRED"
            assert marker.exists() and s.repo.exists()
            evidence[label] = {"action": "hard_park", "delete_count": 0}
        finally:
            s.close()
    return evidence


def case_future_corrupt_symlink_and_event_damage_rejected() -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for label in ("future", "corrupt", "symlink", "corrupt_event"):
        s = Scenario()
        try:
            if label == "future":
                payload = json.loads(s.ctx.state_path.read_text(encoding="utf-8"))
                payload["schema_version"] = 2
                atomic_write_json(s.ctx.state_path, payload)
            elif label == "corrupt":
                s.ctx.state_path.write_text("{broken", encoding="utf-8")
            else:
                if label == "symlink":
                    target = s.root / "outside.json"
                    target.write_text("{}\n", encoding="utf-8")
                    s.ctx.state_path.unlink()
                    s.ctx.state_path.symlink_to(target)
                else:
                    with s.ctx.events_path.open("ab") as stream:
                        stream.write(b"{broken\n")
            code = EXIT_CONFIG if label == "symlink" else EXIT_DATA
            message = expect_error(code, lambda: status(s.ctx, PROJECT, POLICY))
            evidence[label] = {"exit_code": code, "message": message}
        finally:
            s.close()
    return evidence


def case_repo_and_project_identity_mismatch_zero_write() -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for label in ("project", "repository"):
        s = Scenario()
        try:
            if label == "project":
                before = runtime_snapshot(s)
                message = expect_error(EXIT_CONFIG, lambda: status(s.ctx, "different-project", POLICY))
            else:
                payload = json.loads(s.ctx.state_path.read_text(encoding="utf-8"))
                payload["repo_identity"] = "0" * 64
                atomic_write_json(s.ctx.state_path, payload)
                before = runtime_snapshot(s)
                message = expect_error(EXIT_CONFIG, lambda: status(s.ctx, PROJECT, POLICY))
            assert runtime_snapshot(s) == before
            evidence[label] = {"exit_code": EXIT_CONFIG, "runtime_writes": 0, "message": message}
        finally:
            s.close()
    return evidence


def case_policy_identity_change_zero_write() -> dict[str, Any]:
    s = Scenario()
    try:
        before = runtime_snapshot(s)
        message = expect_error(EXIT_CONFIG, lambda: status(s.ctx, PROJECT, "d" * 40))
        assert runtime_snapshot(s) == before
        return {"exit_code": EXIT_CONFIG, "runtime_writes": 0, "message": message}
    finally:
        s.close()


def case_waiting_provider_reset_does_not_auto_resume() -> dict[str, Any]:
    s = Scenario()
    try:
        waiting = reconcile(s.ctx, PROJECT, POLICY, "pm-a", s.token, s.facts(provider="waiting_reset"))
        available = reconcile(s.ctx, PROJECT, POLICY, "pm-a", s.token, s.facts(provider="available"))
        current = status(s.ctx, PROJECT, POLICY)["state"]
        assert waiting["planned_action"]["action"] == "retry_later"
        assert available["planned_action"]["action"] == "retry_later"
        assert current["state"] == "WAITING_PROVIDER_RESET" and current["pending_intent"] is None
        return {"stored_state": current["state"], "auto_resume_count": 0}
    finally:
        s.close()


def case_status_is_pure_read_only() -> dict[str, Any]:
    s = Scenario()
    try:
        before = runtime_snapshot(s)
        result = status(s.ctx, PROJECT, POLICY)
        after = runtime_snapshot(s)
        assert result["read_only"] is True and before == after
        return {"read_only": True, "runtime_writes": 0}
    finally:
        s.close()


def case_cli_contract_and_exit_codes() -> dict[str, Any]:
    s = Scenario()
    try:
        controller = Path(__file__).with_name("autopilot-controller.py")
        success = subprocess.run([
            sys.executable, str(controller), "status", "--repo", str(s.repo),
            "--project-id", PROJECT, "--policy-commit", POLICY,
        ], capture_output=True, text=True, check=False)
        usage = subprocess.run([sys.executable, str(controller), "status"], capture_output=True, text=True, check=False)
        assert success.returncode == 0 and json.loads(success.stdout)["read_only"] is True
        assert usage.returncode == 64
        return {"status_exit": success.returncode, "usage_exit": usage.returncode}
    finally:
        s.close()


CASES: list[tuple[str, Callable[[], dict[str, Any]]]] = [
    ("kill/takeover adopts without spawn", case_kill_takeover_adopts_without_spawn),
    ("double PM and stale token produce zero writes", case_double_pm_and_old_token_zero_write),
    ("lost completion message plans verify", case_lost_message_completed_goes_verify),
    ("adapter receipt waits for external fact", case_receipt_waits_for_external_fact),
    ("writeback crash recovers exactly once", case_writeback_crash_recovers_once),
    ("duplicate worktree adopts or rejects", case_duplicate_worktree_adopt_then_reject),
    ("dirty/unknown/ambiguous facts never delete", case_dirty_and_unknown_checks_fail_closed_without_delete),
    ("future/corrupt/symlink/event damage is rejected", case_future_corrupt_symlink_and_event_damage_rejected),
    ("repository/project identity mismatch produces zero writes", case_repo_and_project_identity_mismatch_zero_write),
    ("policy identity change produces zero writes", case_policy_identity_change_zero_write),
    ("provider reset state never auto-resumes", case_waiting_provider_reset_does_not_auto_resume),
    ("status is pure read-only", case_status_is_pure_read_only),
    ("CLI contract uses stable exit codes", case_cli_contract_and_exit_codes),
]


def main() -> int:
    evidence: list[dict[str, Any]] = []
    failures = 0
    for index, (name, operation) in enumerate(CASES, start=1):
        try:
            detail = operation()
        except Exception as exc:
            failures += 1
            print(f"not ok {index} - {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok {index} - {name}")
            evidence.append({"case": name, "evidence": detail})
    print(json.dumps({
        "contract": "multi-agent-orchestration.autopilot-selftest.v1",
        "passed": len(CASES) - failures,
        "failed": failures,
        "network_calls": 0,
        "external_orca_github_calls": 0,
        "evidence": evidence,
        "not_verified": [
            "real Orca/GitHub adapter integration",
            "host durable scheduler (Task-067)",
            "cross-machine filesystem crash semantics beyond local fsync/rename",
        ],
    }, ensure_ascii=False, sort_keys=True))
    return 1 if failures else 0


class ScenarioV2:
    def __init__(
        self, *, acquire: bool = True, linked_worktree: bool = False, lease_ttl: int = 60,
    ) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="autopilot-controller-v2-")
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Autopilot Controller Selftest")
        git(self.repo, "config", "user.email", "controller@example.invalid")
        (self.repo / "README.md").write_text("fixture\n", encoding="utf-8")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-qm", "fixture")
        self.policy = git(self.repo, "rev-parse", "HEAD")
        if linked_worktree:
            self.worktree = self.root / "worker"
            git(self.repo, "worktree", "add", "-q", "-b", "feat-task-x", str(self.worktree), self.policy)
        else:
            git(self.repo, "switch", "-qc", "feat-task-x")
            self.worktree = self.repo
        self.facts_adapter = self.root / "facts-adapter.py"
        self.facts_adapter.write_text("#!/usr/bin/env python3\nraise SystemExit(70)\n", encoding="utf-8")
        self.facts_adapter.chmod(0o700)
        self.facts_manifest = self.root / "facts-manifest.json"
        self.facts_manifest.write_text("{}\n", encoding="utf-8")
        self.ctx = RuntimeContext(self.repo, create=True)
        self.fact_sequence = 0
        self.item = {
            "task_id": "Task-X", "attempt": 1, "branch": "feat-task-x",
            "worktree": str(self.worktree.resolve()), "dispatch_id": None,
            "orca_task_id": "task-orca-x",
            "provider": "fixture/provider", "pr_number": None, "pr_head_oid": None,
            "status": "RUNNING", "next_action": "inspect_dispatch",
        }
        init_runtime(
            self.ctx, PROJECT, self.policy, "wave-1", "run-fixture", [self.item],
            self.facts_adapter, self.facts_manifest,
        )
        self.now = dt.datetime.now(dt.timezone.utc)
        self.lease: dict[str, Any] | None = None
        if acquire:
            self.lease = acquire_lease(
                self.ctx, PROJECT, self.policy, "pm-a", lease_ttl,
                takeover=False, reason=None, now=self.now,
            )

    @property
    def token(self) -> int:
        assert self.lease is not None
        return int(self.lease["fencing_token"])

    def facts(
        self, *, dispatch: str = "active", dispatch_id: str | None = "ctx-task-x",
        liveness: str = "active", dirty: Any = False, worktree_count: Any = 1,
        worktree: str | None = None, branch_matches: Any = True,
        published: Any = False, pr_state: str = "none", checks: str = "not_applicable",
        mergeable: Any = "not_applicable", approvals: Any = 0,
        approvals_known: bool = True, required_approvals: int = 1,
        required_checks: list[str] | None = None,
        project_status: str = "in_progress", writeback: Any = False,
        provider: str = "available", verified: Any = False,
        merge_commit: str | None = None, ambiguous: bool = False,
        issued_offset_seconds: int = 0, deadline_offset_seconds: int = 30,
    ) -> dict[str, Any]:
        if dispatch == "missing":
            dispatch_id = None
            liveness = "unknown"
        if worktree is None and worktree_count == 1:
            worktree = str(self.worktree.resolve())
        branch = "feat-task-x"
        evidence_sha256 = "e" * 64
        gate_contract_sha256 = "d" * 64
        self.fact_sequence += 1
        request_id = f"request-selftest-{self.fact_sequence}"
        base_time = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        issued = base_time + dt.timedelta(seconds=issued_offset_seconds)
        deadline = base_time + dt.timedelta(seconds=deadline_offset_seconds)
        issued_at = issued.strftime("%Y-%m-%dT%H:%M:%SZ")
        deadline_at = deadline.strftime("%Y-%m-%dT%H:%M:%SZ")
        adapter_sha256 = hashlib.sha256(self.facts_adapter.read_bytes()).hexdigest()
        manifest_sha256 = hashlib.sha256(self.facts_manifest.read_bytes()).hexdigest()
        self.last_request = {
            "schema_version": 1,
            "contract": "multi-agent-orchestration.autopilot-facts-request.v1",
            "request_id": request_id,
            "adapter_sha256": adapter_sha256,
            "manifest_sha256": manifest_sha256,
            "issued_at": issued_at,
            "deadline": deadline_at,
            "repo": {
                "root": str(self.ctx.repo), "common_dir": str(self.ctx.common_dir),
                "identity": self.ctx.repo_identity,
            },
            "project": {"project_id": PROJECT, "policy_commit": self.policy},
            "run_id": "run-fixture",
            "items": [{
                "task_id": "Task-X", "attempt": 1, "dispatch_id": dispatch_id,
                "orca_task_id": "task-orca-x", "branch": branch,
                "worktree": str(self.worktree.resolve()), "provider": "fixture/provider",
                "pr_number": 17 if pr_state != "none" else None,
                "pr_head_oid": self.policy if pr_state != "none" else None,
            }],
        }
        return {
            "schema_version": 1,
            "contract": FACTS_CONTRACT,
            "request_id": request_id,
            "adapter_sha256": adapter_sha256,
            "manifest_sha256": manifest_sha256,
            "repo_identity": self.ctx.repo_identity,
            "project_id": PROJECT,
            "policy_commit": self.policy,
            "run_id": "run-fixture",
            "issued_at": issued_at,
            "deadline": deadline_at,
            "started_at": issued_at,
            "finished_at": issued_at,
            "observed_at": issued_at,
            "ambiguous": ambiguous,
            "items": [{
                "task_id": "Task-X", "attempt": 1,
                "dispatch": {"id": dispatch_id, "status": dispatch, "liveness": liveness},
                "git": {
                    "worktree": worktree, "worktree_count": worktree_count,
                    "branch": branch, "branch_matches": branch_matches, "dirty": dirty,
                    "remote": "origin",
                    "local_oid": self.policy, "remote_oid": self.policy if published else None,
                    "published": published,
                },
                "pr": {
                    "number": 17 if pr_state != "none" else None,
                    "state": pr_state, "checks": checks, "mergeable": mergeable,
                    "approvals": approvals, "approvals_known": approvals_known,
                    "required_approvals": required_approvals,
                    "required_checks": ["ci/test"] if required_checks is None else required_checks,
                    "head_oid": self.policy if pr_state != "none" else None,
                    "head_branch": branch if pr_state != "none" else None,
                    "base_branch": "main", "merge_commit": merge_commit,
                },
                "project": {
                    "status": project_status, "writeback_applied": writeback,
                    "evidence_sha256": evidence_sha256,
                    "writeback_target": {
                        "task_id": "Task-X", "merge_commit": merge_commit,
                        "policy_commit": self.policy, "evidence_sha256": evidence_sha256,
                    } if writeback is True else None,
                },
                "provider": {"identity": "fixture/provider", "status": provider, "retry_at": None},
                "verification": {
                    "passed": verified, "local_oid": self.policy,
                    "evidence_sha256": evidence_sha256,
                    "gate_contract_sha256": gate_contract_sha256,
                },
            }],
        }

    def run_reconcile(
        self, *, owner: str = "pm-a", token: int | None = None, **facts_kwargs: Any,
    ) -> dict[str, Any]:
        facts = self.facts(**facts_kwargs)
        return reconcile(
            self.ctx, PROJECT, self.policy, owner, self.token if token is None else token,
            facts, request=self.last_request,
        )

    def close(self) -> None:
        self.temp.cleanup()


def make_v2_adapter(s: ScenarioV2, *, mode: str = "good", sleep_seconds: float = 0.0) -> tuple[Path, Path, Path, Path]:
    adapter = s.root / f"mutation-{mode}-{sleep_seconds}.py"
    counter = s.root / f"counter-{mode}-{sleep_seconds}.txt"
    request_log = s.root / f"request-{mode}-{sleep_seconds}.json"
    marker = s.root / f"marker-{mode}-{sleep_seconds}.txt"
    adapter.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys, time\n"
        "request=json.load(sys.stdin)\n"
        f"counter=pathlib.Path({str(counter)!r})\n"
        "counter.write_text(str(int(counter.read_text() if counter.exists() else '0')+1))\n"
        f"pathlib.Path({str(request_log)!r}).write_text(json.dumps(request, sort_keys=True))\n"
        f"pathlib.Path({str(marker)!r}).write_text('started')\n"
        f"time.sleep({sleep_seconds!r})\n"
        + ("raise SystemExit(0)\n" if mode == "lost" else "")
        + (
            "print(json.dumps({'schema_version':1,'contract':'multi-agent-orchestration.autopilot-adapter-receipt.v1',"
            "'request_id':request['request_id'],'idempotency_key':request['intent']['idempotency_key'],"
            f"'target_digest':{'\"0\"*64' if mode == 'bad-digest' else 'request[\"intent\"][\"target_digest\"]'},"
            "'fencing_token':request['fencing_token'],'accepted':True,'receipt_id':'receipt-1'}))\n"
            if mode != "lost" else ""
        ),
        encoding="utf-8",
    )
    adapter.chmod(0o700)
    return adapter, counter, request_log, marker


def _mp_acquire(repo: str, policy: str, owner: str, start: Any, queue: Any) -> None:
    start.wait()
    try:
        lease = acquire_lease(
            RuntimeContext(Path(repo), create=False), PROJECT, policy, owner, 60,
            takeover=False, reason=None,
        )
    except ControllerError as exc:
        queue.put((owner, "error", exc.code))
    else:
        queue.put((owner, "ok", lease["fencing_token"]))


def _mp_tick(repo: str, policy: str, token: int, adapter: str, timeout: int, queue: Any) -> None:
    try:
        result = execute_tick(
            RuntimeContext(Path(repo), create=False), PROJECT, policy, "pm-a", token,
            Path(adapter), timeout_seconds=timeout,
        )
    except ControllerError as exc:
        queue.put(("error", exc.code, exc.message))
    else:
        queue.put(("ok", result))


def _mp_hold_writer(repo: str, policy: str, ready: Any, release: Any, queue: Any) -> None:
    try:
        ctx = RuntimeContext(Path(repo), create=False)
        with runtime_lock(ctx):
            state, _ = load_state_snapshot(ctx, PROJECT, policy, recover=True)
            after = json.loads(json.dumps(state))
            after["parking_detail"] = "writer-finished"

            def hold() -> None:
                ready.set()
                release.wait(10)

            write_ahead_transition(ctx, state, after, "writer_hold_fixture", {}, after_event_hook=hold)
        queue.put(("ok", None))
    except Exception as exc:
        queue.put(("error", f"{type(exc).__name__}:{exc}"))


def case_v2_multiprocess_acquire() -> dict[str, Any]:
    s = ScenarioV2(acquire=False)
    try:
        context = mp.get_context("fork")
        start, queue = context.Event(), context.Queue()
        workers = [context.Process(target=_mp_acquire, args=(str(s.repo), s.policy, owner, start, queue)) for owner in ("pm-a", "pm-b")]
        for worker in workers:
            worker.start()
        start.set()
        results = [queue.get(timeout=10) for _ in workers]
        for worker in workers:
            worker.join(10)
            assert worker.exitcode == 0
        assert sum(result[1] == "ok" for result in results) == 1
        assert sum(result[1] == "error" and result[2] == EXIT_CONFLICT for result in results) == 1
        snapshot = status(s.ctx, PROJECT, s.policy)
        assert snapshot["state"]["fencing_token"] == 1
        return {"contenders": 2, "winners": 1, "token": 1}
    finally:
        s.close()


def case_v2_takeover_active_dispatch() -> dict[str, Any]:
    s = ScenarioV2()
    try:
        old = s.token
        s.lease = acquire_lease(
            s.ctx, PROJECT, s.policy, "pm-b", 60, takeover=True,
            reason="previous PM terminated", now=s.now + dt.timedelta(seconds=61),
        )
        result = s.run_reconcile(owner="pm-b", dispatch="active", dirty=True)
        item = status(s.ctx, PROJECT, s.policy)["state"]["items"][0]
        assert result["planned_action"]["action"] == "observe"
        assert result["pending_intent"] is None
        assert item["dispatch_id"] == "ctx-task-x" and item["dispatch_status"] == "active"
        assert item["observed_at"] and item["next_action"] == "observe"
        return {"old_token": old, "new_token": s.token, "dispatch": item["dispatch_id"], "spawn_count": 0}
    finally:
        s.close()


def case_v2_wal_gap_and_mutation_recovery() -> dict[str, Any]:
    s = ScenarioV2()
    try:
        before_disk = file_digest(s.ctx.state_path)

        class CrashAfterEvent(Exception):
            pass

        with runtime_lock(s.ctx):
            state, _ = load_state_snapshot(s.ctx, PROJECT, s.policy, recover=True)
            after = json.loads(json.dumps(state))
            after["parking_detail"] = "event-ahead"
            try:
                write_ahead_transition(
                    s.ctx, state, after, "event_state_gap_fixture", {},
                    after_event_hook=lambda: (_ for _ in ()).throw(CrashAfterEvent()),
                )
            except CrashAfterEvent:
                pass
        assert file_digest(s.ctx.state_path) == before_disk
        readonly = status(s.ctx, PROJECT, s.policy)
        assert readonly["recovery_needed"] is True
        assert readonly["state"]["parking_detail"] == "event-ahead"
        assert file_digest(s.ctx.state_path) == before_disk
        recovered = s.run_reconcile(dispatch="active")
        final = status(s.ctx, PROJECT, s.policy)
        assert recovered["recovered"] is True and final["recovery_needed"] is False
        return {"status_writes": 0, "recovered_by_mutation": True}
    finally:
        s.close()


def case_v2_lease_state_gap_recovery() -> dict[str, Any]:
    evidence: dict[str, Any] = {}

    class CrashAfterLease(Exception):
        pass

    s = ScenarioV2(acquire=False)
    try:
        state_before = file_digest(s.ctx.state_path)
        try:
            acquire_lease(
                s.ctx, PROJECT, s.policy, "pm-gap", 60,
                takeover=False, reason=None,
                after_lease_hook=lambda: (_ for _ in ()).throw(CrashAfterLease()),
            )
        except CrashAfterLease:
            pass
        else:
            raise AssertionError("acquire lease gap was not injected")
        readonly = status(s.ctx, PROJECT, s.policy)
        assert readonly["recovery_needed"] is True
        assert readonly["state"]["fencing_token"] == 1 and readonly["lease"]["fencing_token"] == 1
        assert file_digest(s.ctx.state_path) == state_before
        recovered = s.run_reconcile(owner="pm-gap", token=1, dispatch="active")
        assert recovered["recovered"] is True
        assert status(s.ctx, PROJECT, s.policy)["recovery_needed"] is False
        evidence["acquire_gap"] = {"token": 1, "token_increment_repeated": False, "mutation_recovered": True}
    finally:
        s.close()

    s = ScenarioV2()
    try:
        old_expiry = s.lease["expires_at"]
        state_before = file_digest(s.ctx.state_path)
        try:
            renew_lease(
                s.ctx, PROJECT, s.policy, "pm-a", s.token, 120,
                after_lease_hook=lambda: (_ for _ in ()).throw(CrashAfterLease()),
            )
        except CrashAfterLease:
            pass
        else:
            raise AssertionError("renew lease gap was not injected")
        readonly = status(s.ctx, PROJECT, s.policy)
        assert readonly["recovery_needed"] is True
        assert readonly["lease"]["expires_at"] != old_expiry
        assert readonly["state"]["lease_expires_at"] == readonly["lease"]["expires_at"]
        assert file_digest(s.ctx.state_path) == state_before
        recovered = s.run_reconcile(dispatch="active")
        assert recovered["recovered"] is True
        assert status(s.ctx, PROJECT, s.policy)["recovery_needed"] is False
        evidence["renew_gap"] = {"token": s.token, "token_changed": False, "mutation_recovered": True}
    finally:
        s.close()
    return evidence


def case_v2_adapter_lock_blocks_takeover() -> dict[str, Any]:
    s = ScenarioV2()
    try:
        s.run_reconcile(dispatch="completed")
        adapter, _, _, marker = make_v2_adapter(s, sleep_seconds=1.4)
        context = mp.get_context("fork")
        queue = context.Queue()
        process = context.Process(target=_mp_tick, args=(str(s.repo), s.policy, s.token, str(adapter), 3, queue))
        process.start()
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists(), "adapter did not start"
        started = time.monotonic()
        takeover = acquire_lease(
            s.ctx, PROJECT, s.policy, "pm-b", 60, takeover=True,
            reason="expired while adapter held lock", now=s.now + dt.timedelta(seconds=61),
        )
        elapsed = time.monotonic() - started
        result = queue.get(timeout=10)
        process.join(10)
        assert result[0] == "ok" and process.exitcode == 0
        assert elapsed >= 1.0 and takeover["fencing_token"] == 2
        return {"takeover_blocked_seconds": round(elapsed, 2), "post_adapter_token": 2}
    finally:
        s.close()


def case_v2_exact_target_and_receipt() -> dict[str, Any]:
    s = ScenarioV2()
    try:
        planned = s.run_reconcile(dispatch="completed")
        target = planned["planned_action"]["target"]
        pending = planned["pending_intent"]
        assert target == {
            "task_id": "Task-X", "attempt": 1, "run_id": "run-fixture",
            "dispatch_id": "ctx-task-x",
            "worktree": str(s.worktree.resolve()), "local_oid": s.policy,
            "evidence_sha256": "e" * 64, "gate_contract_sha256": "d" * 64,
        }
        assert pending["target"] == target and len(pending["target_digest"]) == 64
        adapter, counter, request_log, _ = make_v2_adapter(s)
        tick = execute_tick(s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter, timeout_seconds=5)
        request = json.loads(request_log.read_text(encoding="utf-8"))
        assert tick["mutation_count"] == 1 and counter.read_text() == "1"
        assert request["intent"]["target"] == target
        assert request["intent"]["target_digest"] == pending["target_digest"]
        assert execute_tick(s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter, timeout_seconds=5)["mutation_count"] == 0
        return {"action": "verify", "target_digest": pending["target_digest"], "adapter_calls": 1}
    finally:
        s.close()


def case_v2_bad_target_receipt_is_uncertain_once() -> dict[str, Any]:
    s = ScenarioV2()
    try:
        s.run_reconcile(dispatch="completed")
        adapter, counter, _, _ = make_v2_adapter(s, mode="bad-digest")
        expect_error(EXIT_DATA, lambda: execute_tick(
            s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter, timeout_seconds=5,
        ))
        assert counter.read_text() == "1"
        expect_error(EXIT_CONFLICT, lambda: execute_tick(
            s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter, timeout_seconds=5,
        ))
        assert counter.read_text() == "1"
        return {"bad_target_digest": "rejected", "adapter_calls": 1, "retry_calls": 0}
    finally:
        s.close()


def case_v2_pending_transients_never_resubmit_merge() -> dict[str, Any]:
    s = ScenarioV2()
    try:
        planned = s.run_reconcile(
            dispatch="completed", published=True, verified=True, pr_state="open",
            checks="pass", mergeable=True, approvals=1, approvals_known=True,
        )
        original = planned["pending_intent"]
        assert original["action"] == "merge" and "approvals" not in original["target"]
        adapter, counter, _, _ = make_v2_adapter(s)

        transient = s.run_reconcile(
            dispatch="completed", published=True, verified=True, pr_state="open",
            checks="pending", mergeable=True, approvals=0, approvals_known=True,
        )
        held = transient["pending_intent"]
        assert transient["disposition"] == "await_revalidation"
        assert held["idempotency_key"] == original["idempotency_key"] and held["ready"] is False
        expect_error(EXIT_CONFLICT, lambda: execute_tick(
            s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter, timeout_seconds=5,
        ))
        assert not counter.exists()

        revalidated = s.run_reconcile(
            dispatch="completed", published=True, verified=True, pr_state="open",
            checks="pass", mergeable=True, approvals=2, approvals_known=True,
        )
        assert revalidated["pending_intent"]["ready"] is True
        assert revalidated["pending_intent"]["idempotency_key"] == original["idempotency_key"]
        execute_tick(s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter, timeout_seconds=5)
        assert counter.read_text() == "1"

        for checks, approvals in (("pending", 0), ("pass", 3)):
            waiting = s.run_reconcile(
                dispatch="completed", published=True, verified=True, pr_state="open",
                checks=checks, mergeable=True, approvals=approvals, approvals_known=True,
            )
            assert waiting["pending_intent"]["status"] == "receipt_recorded"
            assert waiting["pending_intent"]["idempotency_key"] == original["idempotency_key"]
            assert waiting["disposition"] == "await_external_fact"
        assert execute_tick(
            s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter, timeout_seconds=5,
        )["mutation_count"] == 0

        converged = s.run_reconcile(
            dispatch="completed", published=True, verified=True, pr_state="merged",
            checks="pass", mergeable=True, approvals=3, approvals_known=True,
            merge_commit=s.policy, writeback=False,
        )
        assert converged["converged_intent"]["action"] == "merge"
        assert converged["pending_intent"]["action"] == "writeback"
        assert counter.read_text() == "1"
        events = [json.loads(line) for line in s.ctx.events_path.read_text(encoding="utf-8").splitlines()]
        convergence_event = next(event for event in reversed(events) if event["kind"] == "pending_intent_converged")
        assert len(convergence_event["detail"]["before_evidence_sha256"]) == 64
        assert len(convergence_event["detail"]["after_evidence_sha256"]) == 64
        assert convergence_event["detail"]["after_evidence"]["facts"]["pr"]["state"] == "merged"
        ledger = status(s.ctx, PROJECT, s.policy)["state"]["items"][0]
        assert ledger["checks"] == "pass" and ledger["approvals"] == 3
        assert ledger["verification_passed"] is True and ledger["provider_status"] == "available"
        return {
            "merge_adapter_calls": 1, "transient_pending_preserved": True,
            "actual_approval_not_in_key": True, "next_action": "writeback",
            "before_after_evidence_persisted": True,
        }
    finally:
        s.close()


def case_v2_expired_planned_requires_fresh_reconcile() -> dict[str, Any]:
    s = ScenarioV2()
    try:
        planned = s.run_reconcile(
            dispatch="completed", published=True, verified=True, pr_state="open",
            checks="pass", mergeable=True, approvals=1, approvals_known=True,
            issued_offset_seconds=-2, deadline_offset_seconds=-1,
        )
        original = planned["pending_intent"]
        assert original["action"] == "merge" and original["ready"] is True
        adapter, counter, _, _ = make_v2_adapter(s)
        expect_error(EXIT_CONFLICT, lambda: execute_tick(
            s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter, timeout_seconds=5,
        ))
        expired = status(s.ctx, PROJECT, s.policy)["state"]
        assert expired["pending_intent"]["ready"] is False
        assert expired["mutation_adapter"] is None and not counter.exists()

        refreshed = s.run_reconcile(
            dispatch="completed", published=True, verified=True, pr_state="open",
            checks="pass", mergeable=True, approvals=2, approvals_known=True,
        )
        current = refreshed["pending_intent"]
        assert current["ready"] is True
        assert current["idempotency_key"] == original["idempotency_key"]
        assert current["facts_request_id"] != original["facts_request_id"]
        assert current["facts_deadline"] != original["facts_deadline"]
        execute_tick(s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter, timeout_seconds=5)
        assert counter.read_text() == "1"
        assert execute_tick(
            s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter, timeout_seconds=5,
        )["mutation_count"] == 0
        return {
            "expired_adapter_calls": 0, "fresh_reconcile_required": True,
            "post_revalidate_adapter_calls": 1,
        }
    finally:
        s.close()


def case_v2_mutation_specific_convergence_matrix() -> dict[str, Any]:
    s = ScenarioV2()
    try:
        anchor = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

        def pending(action: str, target: dict[str, Any]) -> dict[str, Any]:
            return {
                "action": action, "task_id": "Task-X", "target": target,
                "status": "receipt_recorded", "planned_at": anchor,
                "receipt_recorded_at": anchor, "facts_request_id": "request-before-mutation",
            }

        common = {"task_id": "Task-X", "attempt": 1, "run_id": "run-fixture"}
        cases: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
            ("spawn", pending("spawn", {**common, "orca_task_id": "task-orca-x", "branch": "feat-task-x",
                                        "worktree": str(s.worktree), "provider": "fixture/provider"}),
             s.facts(dispatch="active")),
            ("settle", pending("settle", {**common, "dispatch_id": "ctx-task-x", "provider": "fixture/provider"}),
             s.facts(dispatch="completed", liveness="settled")),
            ("verify", pending("verify", {**common, "dispatch_id": "ctx-task-x", "worktree": str(s.worktree),
                                          "local_oid": s.policy, "evidence_sha256": "e" * 64,
                                          "gate_contract_sha256": "d" * 64}),
             s.facts(dispatch="completed", verified=True)),
            ("push", pending("push", {**common, "worktree": str(s.worktree), "branch": "feat-task-x",
                                      "remote": "origin", "local_oid": s.policy}),
             s.facts(dispatch="completed", verified=True, published=True)),
            ("open_pr", pending("open_pr", {**common, "head_branch": "feat-task-x", "base_branch": "main",
                                             "head_oid": s.policy}),
             s.facts(dispatch="completed", verified=True, published=True, pr_state="open", checks="pending")),
            ("merge", pending("merge", {**common, "pr_number": 17, "head_oid": s.policy,
                                         "head_branch": "feat-task-x", "base_branch": "main",
                                         "required_checks": ["ci/test"], "required_approvals": 1,
                                         "evidence_sha256": "e" * 64, "gate_contract_sha256": "d" * 64}),
             s.facts(dispatch="completed", verified=True, published=True, pr_state="merged", checks="pass",
                     mergeable=True, approvals=1, merge_commit=s.policy)),
            ("writeback", pending("writeback", {**common, "merge_commit": s.policy,
                                                 "policy_commit": s.policy, "evidence_sha256": "e" * 64}),
             s.facts(dispatch="completed", verified=True, published=True, pr_state="merged", checks="pass",
                     mergeable=True, approvals=1, merge_commit=s.policy, writeback=True)),
        ]
        for name, intent, facts in cases:
            assert pending_intent_converged(intent, facts), name

        stale_settle = s.facts(dispatch="failed", liveness="dead")
        assert not pending_intent_converged(cases[1][1], stale_settle)
        wrong_remote = s.facts(dispatch="completed", verified=True, published=True)
        wrong_remote["items"][0]["git"]["remote"] = "upstream"
        assert not pending_intent_converged(cases[3][1], wrong_remote)
        replay = cases[2][2]
        replay["request_id"] = cases[2][1]["facts_request_id"]
        assert not pending_intent_converged(cases[2][1], replay)
        return {"converged_actions": [name for name, _, _ in cases], "replay_rejected": True}
    finally:
        s.close()


def case_v2_takeover_refences_planned_intent() -> dict[str, Any]:
    s = ScenarioV2()
    try:
        planned = s.run_reconcile(dispatch="completed")
        old_token = s.token
        old_key = planned["pending_intent"]["idempotency_key"]
        s.lease = acquire_lease(
            s.ctx, PROJECT, s.policy, "pm-b", 60, takeover=True,
            reason="planned intent owner terminated", now=s.now + dt.timedelta(seconds=61),
        )
        refenced = s.run_reconcile(owner="pm-b", dispatch="completed")
        pending = refenced["pending_intent"]
        assert pending["idempotency_key"] == old_key
        assert pending["fencing_token"] == s.token == old_token + 1 and pending["ready"] is True
        adapter, counter, _, _ = make_v2_adapter(s)
        expect_error(EXIT_CONFLICT, lambda: execute_tick(
            s.ctx, PROJECT, s.policy, "pm-a", old_token, adapter, timeout_seconds=5,
        ))
        assert not counter.exists()
        executed = execute_tick(
            s.ctx, PROJECT, s.policy, "pm-b", s.token, adapter, timeout_seconds=5,
        )
        assert executed["mutation_count"] == 1 and counter.read_text() == "1"
        return {"old_token": old_token, "new_token": s.token, "same_idempotency_key": True}
    finally:
        s.close()


def case_v2_dirty_active_and_single_adopt() -> dict[str, Any]:
    s = ScenarioV2()
    try:
        active = s.run_reconcile(dispatch="active", dirty=True)
        assert active["planned_action"]["action"] == "observe"
        first = s.run_reconcile(dispatch="missing", dirty=False)
        second = s.run_reconcile(dispatch="missing", dirty=False)
        assert first["planned_action"]["action"] == "adopt"
        assert second["planned_action"]["action"] == "observe"
        return {"dirty_active": "observe", "adopt_count": 1}
    finally:
        s.close()


def case_v2_acceptance_failure_repairs_before_park() -> dict[str, Any]:
    """回归（v2.14.0）：checks=="fail" 不再无条件 hard_park。

    内部可恢复验收失败按 acceptance-recovery 分类：预算内规划
    repair_acceptance（不泊车，state 保持 RUNNING），按「失败 episode」
    计数（同一 episode 重复 reconcile 不重复计数）；预算耗尽才
    hard_park（internal_recoverable 类）。checks=="unknown" 仍 fail-closed。
    """
    evidence: dict[str, Any] = {}

    s = ScenarioV2()
    try:
        first = s.run_reconcile(
            dispatch="completed", published=True, verified=True,
            pr_state="open", checks="fail",
        )
        assert first["planned_action"]["action"] == "repair_acceptance", first["planned_action"]
        assert first["planned_action"]["external_mutation"] is False
        assert first["planned_action"]["target"]["repair_step"] == "repair"
        assert first["pending_intent"] is None
        snapshot = status(s.ctx, PROJECT, s.policy)["state"]
        assert snapshot["state"] == "RUNNING", snapshot
        assert snapshot["parking_code"] is None
        item = next(item for item in snapshot["items"] if item["task_id"] == "Task-X")
        assert item["repair_attempts"] == 1 and item["next_action"] == "repair_acceptance"
        evidence["first_episode"] = {"action": "repair_acceptance", "state": "RUNNING", "attempts": 1}

        repeat = s.run_reconcile(
            dispatch="completed", published=True, verified=True,
            pr_state="open", checks="fail",
        )
        assert repeat["planned_action"]["action"] == "repair_acceptance"
        snapshot = status(s.ctx, PROJECT, s.policy)["state"]
        item = next(item for item in snapshot["items"] if item["task_id"] == "Task-X")
        assert item["repair_attempts"] == 1, "同一 episode 的重复 reconcile 不得重复计数"
        evidence["same_episode_repeat"] = {"attempts": 1}

        observed = s.run_reconcile(
            dispatch="completed", published=True, verified=True,
            pr_state="open", checks="pending",
        )
        assert observed["planned_action"]["action"] == "observe"

        second = s.run_reconcile(
            dispatch="completed", published=True, verified=True,
            pr_state="open", checks="fail",
        )
        assert second["planned_action"]["action"] == "repair_acceptance"
        assert second["planned_action"]["target"]["repair_step"] == "re_review"
        snapshot = status(s.ctx, PROJECT, s.policy)["state"]
        item = next(item for item in snapshot["items"] if item["task_id"] == "Task-X")
        assert item["repair_attempts"] == 2
        evidence["second_episode"] = {"action": "repair_acceptance", "step": "re_review", "attempts": 2}

        observed = s.run_reconcile(
            dispatch="completed", published=True, verified=True,
            pr_state="open", checks="pending",
        )
        assert observed["planned_action"]["action"] == "observe"

        exhausted = s.run_reconcile(
            dispatch="completed", published=True, verified=True,
            pr_state="open", checks="fail",
        )
        assert exhausted["planned_action"]["action"] == "hard_park"
        assert exhausted["planned_action"]["failure_class"] == "internal_recoverable"
        assert "repair_budget_exhausted" in exhausted["planned_action"]["reason"]
        snapshot = status(s.ctx, PROJECT, s.policy)["state"]
        assert snapshot["state"] == "ERROR_RECONCILE_REQUIRED"
        evidence["exhausted"] = {"action": "hard_park", "state": "ERROR_RECONCILE_REQUIRED"}
    finally:
        s.close()

    s = ScenarioV2()
    try:
        unknown = s.run_reconcile(
            dispatch="completed", published=True, verified=True,
            pr_state="open", checks="unknown",
        )
        assert unknown["planned_action"]["action"] == "hard_park"
        assert unknown["planned_action"]["failure_class"] == "safety_unknown"
        snapshot = status(s.ctx, PROJECT, s.policy)["state"]
        assert snapshot["state"] == "ERROR_RECONCILE_REQUIRED"
        evidence["unknown_checks"] = {"action": "hard_park", "failure_class": "safety_unknown"}
    finally:
        s.close()
    return evidence


def case_v2_unknown_duplicate_and_waiting_fail_closed() -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    variants = {
        "dirty": {"dispatch": "completed", "dirty": True},
        "dirty_unknown": {"dispatch": "completed", "dirty": "unknown"},
        "worktree_unknown": {"dispatch": "missing", "worktree_count": "unknown"},
        "ambiguous": {"dispatch": "missing", "ambiguous": True},
        "duplicate": {"dispatch": "missing", "worktree_count": 2},
    }
    for label, facts_kwargs in variants.items():
        s = ScenarioV2()
        try:
            result = s.run_reconcile(**facts_kwargs)
            expected = "reject_duplicate" if label == "duplicate" else "hard_park"
            assert result["planned_action"]["action"] == expected
            assert result["pending_intent"] is None and s.worktree.exists()
            evidence[label] = {"action": expected, "deletions": 0, "adapter_calls": 0}
        finally:
            s.close()

    s = ScenarioV2()
    try:
        waiting = s.run_reconcile(dispatch="missing", provider="waiting_reset")
        available = s.run_reconcile(dispatch="missing", provider="available")
        snapshot = status(s.ctx, PROJECT, s.policy)
        assert waiting["planned_action"]["action"] == "retry_later"
        assert available["planned_action"]["action"] == "retry_later"
        assert snapshot["state"]["state"] == "WAITING_PROVIDER_RESET"
        assert snapshot["state"]["pending_intent"] is None
        evidence["provider_reset"] = {"saved": True, "automatic_resume": False, "adapter_calls": 0}
    finally:
        s.close()
    return evidence


def case_v2_facts_binding_and_freshness_fail_closed() -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for label in ("manifest", "request_id", "expired"):
        s = ScenarioV2()
        try:
            facts = s.facts(dispatch="active")
            request = json.loads(json.dumps(s.last_request))
            if label == "manifest":
                facts["manifest_sha256"] = "0" * 64
                expected = EXIT_CONFIG
            elif label == "request_id":
                facts["request_id"] = "untrusted-request"
                expected = EXIT_CONFIG
            else:
                now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
                issued = (now - dt.timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
                deadline = (now - dt.timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
                for payload in (facts, request):
                    payload["issued_at"] = issued
                    payload["deadline"] = deadline
                facts["started_at"] = issued
                facts["finished_at"] = deadline
                facts["observed_at"] = deadline
                expected = EXIT_CONFLICT
            before = runtime_snapshot(s)
            expect_error(expected, lambda: reconcile(
                s.ctx, PROJECT, s.policy, "pm-a", s.token, facts, request=request,
            ))
            assert runtime_snapshot(s) == before
            evidence[label] = {"exit_code": expected, "runtime_writes": 0}
        finally:
            s.close()
    return evidence


def case_v2_complete_allows_cleaned_worktree() -> dict[str, Any]:
    s = ScenarioV2(linked_worktree=True)
    try:
        result = s.run_reconcile(
            dispatch="completed", worktree_count=0, worktree=None, published=True,
            pr_state="merged", checks="pass", mergeable=True, approvals=1,
            project_status="complete", writeback=True, verified=True,
            merge_commit="f" * 40,
        )
        assert result["planned_action"]["action"] == "complete"
        git(s.repo, "worktree", "remove", "--force", str(s.worktree))
        snapshot = status(s.ctx, PROJECT, s.policy)
        assert snapshot["state"]["state"] == "COMPLETE"
        return {"state": "COMPLETE", "worktree_exists": False}
    finally:
        s.close()


def case_v2_timeout_and_lost_receipt() -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for mode in ("timeout", "lost"):
        s = ScenarioV2()
        try:
            s.run_reconcile(dispatch="completed")
            adapter, counter, _, _ = make_v2_adapter(
                s, mode="lost" if mode == "lost" else "good",
                sleep_seconds=2.0 if mode == "timeout" else 0.0,
            )
            code = EXIT_CONFLICT if mode == "timeout" else EXIT_DATA
            expect_error(code, lambda: execute_tick(
                s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter,
                timeout_seconds=1 if mode == "timeout" else 5,
            ))
            assert counter.read_text() == "1"
            before = counter.read_text()
            expect_error(EXIT_CONFLICT, lambda: execute_tick(
                s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter, timeout_seconds=5,
            ))
            assert counter.read_text() == before
            pending = status(s.ctx, PROJECT, s.policy)["state"]["pending_intent"]
            assert pending["status"] == "started"
            evidence[mode] = {"adapter_calls": 1, "pending": "started"}
        finally:
            s.close()
    s = ScenarioV2()
    try:
        adapter, _, _, _ = make_v2_adapter(s)
        expect_error(EXIT_USAGE, lambda: execute_tick(s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter, timeout_seconds=0))
        expect_error(EXIT_USAGE, lambda: execute_tick(s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter, timeout_seconds=3601))
        evidence["timeout_bounds"] = [1, 3600]
    finally:
        s.close()
    s = ScenarioV2(lease_ttl=10)
    try:
        s.run_reconcile(dispatch="completed")
        adapter, counter, _, _ = make_v2_adapter(s)
        expect_error(EXIT_CONFLICT, lambda: execute_tick(
            s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter, timeout_seconds=5,
        ))
        assert not counter.exists()
        evidence["lease_budget_gate"] = {"required_remaining": "> timeout+safety", "adapter_calls": 0}
    finally:
        s.close()
    return evidence


def case_v2_lease_monotonic_and_adapter_seal() -> dict[str, Any]:
    s = ScenarioV2()
    try:
        before = runtime_snapshot(s)
        expect_error(EXIT_USAGE, lambda: renew_lease(
            s.ctx, PROJECT, s.policy, "pm-a", s.token, 10, now=s.now,
        ))
        assert runtime_snapshot(s) == before
        extended = renew_lease(
            s.ctx, PROJECT, s.policy, "pm-a", s.token, 120, now=s.now,
        )
        assert extended["expires_at"] > s.lease["expires_at"]
    finally:
        s.close()

    s = ScenarioV2()
    try:
        adapter_a, counter_a, _, _ = make_v2_adapter(s, mode="good")
        adapter_b, counter_b, _, _ = make_v2_adapter(s, mode="lost")
        empty = execute_tick(
            s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter_a, timeout_seconds=5,
        )
        assert empty["mutation_count"] == 0
        assert status(s.ctx, PROJECT, s.policy)["state"]["mutation_adapter"] is None
        s.run_reconcile(dispatch="completed")
        execute_tick(s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter_a, timeout_seconds=5)
        sealed = status(s.ctx, PROJECT, s.policy)["state"]["mutation_adapter"]
        assert sealed["path"] == str(adapter_a.resolve()) and counter_a.read_text() == "1"
        expect_error(EXIT_CONFIG, lambda: execute_tick(
            s.ctx, PROJECT, s.policy, "pm-a", s.token, adapter_b, timeout_seconds=5,
        ))
        assert not counter_b.exists()
        return {
            "non_mutating_tick_sealed": False, "first_ready_tick_sealed": True,
            "adapter_swap_calls": 0, "renewal_monotonic": True,
        }
    finally:
        s.close()


def case_v2_sensitive_initial_fields_rejected() -> dict[str, Any]:
    temporary = tempfile.TemporaryDirectory(prefix="autopilot-sensitive-init-")
    root = Path(temporary.name).resolve()
    try:
        repo = root / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.name", "Sensitive Init Selftest")
        git(repo, "config", "user.email", "sensitive@example.invalid")
        (repo / "README.md").write_text("fixture\n", encoding="utf-8")
        git(repo, "add", "README.md")
        git(repo, "commit", "-qm", "fixture")
        policy = git(repo, "rev-parse", "HEAD")
        adapter = root / "facts.py"
        adapter.write_text("#!/usr/bin/env python3\nraise SystemExit(0)\n", encoding="utf-8")
        adapter.chmod(0o700)
        manifest = root / "manifest.json"
        manifest.write_text("{}\n", encoding="utf-8")
        ctx = RuntimeContext(repo, create=True)
        bad_item = {
            "task_id": "Task-X", "attempt": 1, "orca_task_id": "task-orca-x",
            "branch": "feat-task-x", "worktree": str(repo), "provider": "fixture/provider",
            "status": "RUNNING", "next_action": "verify",
            "pending_intent": {"idempotency_key": "attacker-controlled"},
        }
        expect_error(EXIT_DATA, lambda: init_runtime(
            ctx, PROJECT, policy, "wave-1", "run-fixture", [bad_item], adapter, manifest,
        ))
        assert not ctx.state_path.exists() and not ctx.events_path.exists() and not ctx.lease_path.exists()
        return {"sensitive_field": "pending_intent", "durable_runtime_writes": 0}
    finally:
        temporary.cleanup()


def case_v2_status_shared_lock_snapshot() -> dict[str, Any]:
    s = ScenarioV2()
    try:
        context = mp.get_context("fork")
        ready, release, queue = context.Event(), context.Event(), context.Queue()
        writer = context.Process(target=_mp_hold_writer, args=(str(s.repo), s.policy, ready, release, queue))
        writer.start()
        assert ready.wait(5)
        result: dict[str, Any] = {}

        def read_status() -> None:
            result["value"] = status(s.ctx, PROJECT, s.policy)

        reader = threading.Thread(target=read_status)
        reader.start()
        time.sleep(0.25)
        assert reader.is_alive(), "status did not wait for exclusive writer"
        release.set()
        reader.join(10)
        writer_result = queue.get(timeout=10)
        writer.join(10)
        assert writer_result[0] == "ok" and writer.exitcode == 0
        assert result["value"]["state"]["parking_detail"] == "writer-finished"
        assert result["value"]["recovery_needed"] is False
        return {"reader_saw_torn_state": False, "shared_lock_waited": True}
    finally:
        s.close()


def case_v2_merge_exact_gate() -> dict[str, Any]:
    s = ScenarioV2()
    try:
        passed = s.run_reconcile(
            dispatch="completed", published=True, verified=True,
            pr_state="open", checks="pass", mergeable=True, approvals=1,
            approvals_known=True, required_approvals=1, required_checks=["ci/test"],
        )
        assert passed["planned_action"]["action"] == "merge"
        assert passed["planned_action"]["target"] == {
            "task_id": "Task-X", "attempt": 1, "run_id": "run-fixture", "pr_number": 17,
            "head_oid": s.policy, "head_branch": "feat-task-x", "base_branch": "main",
            "required_checks": ["ci/test"], "required_approvals": 1,
            "evidence_sha256": "e" * 64, "gate_contract_sha256": "d" * 64,
        }
    finally:
        s.close()
    s = ScenarioV2()
    try:
        refused = s.run_reconcile(
            dispatch="completed", published=True, verified=True,
            pr_state="open", checks="pass", mergeable=True, approvals=0,
            approvals_known=True, required_approvals=1, required_checks=["ci/test"],
        )
        assert refused["planned_action"]["action"] == "hard_park"
        return {
            "checks": "pass", "mergeable": True, "approvals": 1,
            "exact_head_base": True, "insufficient_approval": "hard_park",
        }
    finally:
        s.close()


def case_v2_settle_requires_dead_exact_dispatch() -> dict[str, Any]:
    s = ScenarioV2()
    try:
        dead = s.run_reconcile(
            dispatch="failed", liveness="dead",
        )
        assert dead["planned_action"]["action"] == "settle"
        assert dead["planned_action"]["target"]["dispatch_id"] == "ctx-task-x"
    finally:
        s.close()
    s = ScenarioV2()
    try:
        alive = s.run_reconcile(
            dispatch="failed", liveness="active",
        )
        assert alive["planned_action"]["action"] == "hard_park"
        return {"dead": "settle", "active": "hard_park", "exact_dispatch": True}
    finally:
        s.close()


def case_v2_corrupt_symlink_and_policy_fail_closed() -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for label in ("future", "event_corrupt", "state_symlink", "policy_mismatch"):
        s = ScenarioV2()
        try:
            if label == "future":
                payload = json.loads(s.ctx.state_path.read_text(encoding="utf-8"))
                payload["schema_version"] = 2
                atomic_write_json(s.ctx.state_path, payload)
                code = EXIT_DATA
                operation = lambda: status(s.ctx, PROJECT, s.policy)
            elif label == "event_corrupt":
                with s.ctx.events_path.open("ab") as stream:
                    stream.write(b"{broken\n")
                code = EXIT_DATA
                operation = lambda: status(s.ctx, PROJECT, s.policy)
            elif label == "state_symlink":
                outside = s.root / "outside.json"
                outside.write_text("{}\n", encoding="utf-8")
                s.ctx.state_path.unlink()
                s.ctx.state_path.symlink_to(outside)
                code = EXIT_CONFIG
                operation = lambda: status(s.ctx, PROJECT, s.policy)
            else:
                git(s.repo, "commit", "--allow-empty", "-qm", "new policy")
                other = git(s.repo, "rev-parse", "HEAD")
                code = EXIT_CONFIG
                operation = lambda: status(s.ctx, PROJECT, other)
            before = runtime_snapshot(s)
            expect_error(code, operation)
            assert runtime_snapshot(s) == before
            evidence[label] = {"exit_code": code, "runtime_writes": 0}
        finally:
            s.close()
    return evidence


def case_v2_real_facts_collector_integration() -> dict[str, Any]:
    module_path = Path(__file__).with_name("test-autopilot-facts.py")
    spec = importlib.util.spec_from_file_location("autopilot_facts_selftest_fixture", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixture = module.Fixture()
    try:
        ctx = RuntimeContext(fixture.repo, create=True)
        item = {
            "task_id": "Task-X", "attempt": 1, "dispatch_id": "ctx-task-x",
            "orca_task_id": "task-orca-x",
            "branch": "feat-task-x", "worktree": str(fixture.repo),
            "provider": "fixture/provider", "pr_number": 17,
            "pr_head_oid": fixture.oid,
            "status": "RUNNING", "next_action": "inspect_dispatch",
        }
        init_runtime(
            ctx, "project-fixture", fixture.oid, "wave-fixture", "run-fixture",
            [item], Path(module.COLLECTOR), fixture.manifest_path,
        )
        lease = acquire_lease(
            ctx, "project-fixture", fixture.oid, "pm-fixture", 60,
            takeover=False, reason=None,
        )
        result = collect_and_reconcile(
            ctx, "project-fixture", fixture.oid, "pm-fixture",
            lease["fencing_token"], timeout_seconds=10,
        )
        snapshot = status(ctx, "project-fixture", fixture.oid)
        assert result["planned_action"]["action"] == "complete"
        assert snapshot["state"]["items"][0]["dispatch_id"] == "ctx-task-x"
        return {"collector": "autopilot-facts.py", "action": "complete", "external_calls": "fake-only"}
    finally:
        fixture.close()


def case_v2_cli_surface() -> dict[str, Any]:
    controller = Path(__file__).with_name("autopilot-controller.py")
    help_result = subprocess.run([sys.executable, str(controller), "init", "--help"], capture_output=True, text=True, check=False)
    reconcile_help = subprocess.run([sys.executable, str(controller), "reconcile", "--help"], capture_output=True, text=True, check=False)
    usage = subprocess.run([sys.executable, str(controller), "status"], capture_output=True, text=True, check=False)
    assert help_result.returncode == 0 and "--facts-adapter" in help_result.stdout and "--facts-manifest" in help_result.stdout
    assert reconcile_help.returncode == 0 and "--facts-file" not in reconcile_help.stdout and "--timeout-seconds" in reconcile_help.stdout
    assert usage.returncode == 64
    return {"init_pins_facts": True, "reconcile_collects_pinned": True, "usage_exit": 64}


V2_CASES: list[tuple[str, Callable[[], dict[str, Any]]]] = [
    ("multiprocess acquire elects one PM", case_v2_multiprocess_acquire),
    ("takeover observes exact active Dispatch", case_v2_takeover_active_dispatch),
    ("WAL event-ahead gap is read-only visible and mutation-recovered", case_v2_wal_gap_and_mutation_recovery),
    ("acquire/renew lease-state gaps roll forward once", case_v2_lease_state_gap_recovery),
    ("adapter lock blocks takeover until post-fence", case_v2_adapter_lock_blocks_takeover),
    ("exact target and digest are receipt-bound", case_v2_exact_target_and_receipt),
    ("bad target receipt is uncertain and never retried", case_v2_bad_target_receipt_is_uncertain_once),
    ("pending transients preserve merge idempotency", case_v2_pending_transients_never_resubmit_merge),
    ("expired planned facts require fresh reconcile", case_v2_expired_planned_requires_fresh_reconcile),
    ("all mutations require exact after-fact convergence", case_v2_mutation_specific_convergence_matrix),
    ("takeover re-fences a planned intent", case_v2_takeover_refences_planned_intent),
    ("dirty active observes and worktree adopts once", case_v2_dirty_active_and_single_adopt),
    ("unknown/duplicate/reset states fail closed without deletion", case_v2_unknown_duplicate_and_waiting_fail_closed),
    ("验收失败按分类修复预算内不泊车，耗尽才 park", case_v2_acceptance_failure_repairs_before_park),
    ("facts binding and freshness failures produce zero writes", case_v2_facts_binding_and_freshness_fail_closed),
    ("complete item tolerates cleaned worktree", case_v2_complete_allows_cleaned_worktree),
    ("timeout and lost receipt never repeat mutation", case_v2_timeout_and_lost_receipt),
    ("lease renewal and mutation adapter seal are monotonic", case_v2_lease_monotonic_and_adapter_seal),
    ("sensitive initial fields are rejected", case_v2_sensitive_initial_fields_rejected),
    ("status shared lock sees no torn writer state", case_v2_status_shared_lock_snapshot),
    ("merge requires exact checks/approval/head/base", case_v2_merge_exact_gate),
    ("settle requires dead exact Dispatch", case_v2_settle_requires_dead_exact_dispatch),
    ("future/corrupt/symlink/policy drift fail closed", case_v2_corrupt_symlink_and_policy_fail_closed),
    ("pinned first-party facts collector integrates", case_v2_real_facts_collector_integration),
    ("CLI pins and invokes facts collector", case_v2_cli_surface),
]


def main_v2() -> int:
    evidence: list[dict[str, Any]] = []
    failures = 0
    for index, (name, operation) in enumerate(V2_CASES, start=1):
        try:
            detail = operation()
        except Exception as exc:
            failures += 1
            print(f"not ok {index} - {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok {index} - {name}")
            evidence.append({"case": name, "evidence": detail})
    print(json.dumps({
        "contract": "multi-agent-orchestration.autopilot-controller-selftest.v2",
        "passed": len(V2_CASES) - failures, "failed": failures,
        "network_calls": 0, "real_orca_github_calls": 0,
        "evidence": evidence,
        "not_verified": [
            "real Orca/GitHub mutation adapter integration",
            "Task-067 durable scheduler/automatic resume/delete",
            "power-loss behavior beyond local fsync/rename fault injection",
        ],
    }, ensure_ascii=False, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main_v2())
