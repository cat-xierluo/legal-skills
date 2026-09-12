#!/usr/bin/env python3
"""Real-process registration races with fake CLI; no live Orca mutations."""

from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
HELPER = SCRIPT_DIR / "orca-register-project.py"
LOCK_NAME = "mao-orca-register.lock"
_spec = importlib.util.spec_from_file_location("orca_registration", HELPER)
registration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(registration)

FAKE_ORCA = r'''#!/usr/bin/env python3
import fcntl, hashlib, json, os, pathlib, sys, time

top = pathlib.Path.cwd().resolve()
args = sys.argv[1:]
operation = " ".join(args[:2])
# Orca status is runtime-global, unlike cwd-scoped worktree current. The
# production detector legitimately asks status from its caller's directory.
if operation == "status --json" and os.environ.get("REGISTRATION_TEST_PROJECT"):
    top = pathlib.Path(os.environ["REGISTRATION_TEST_PROJECT"]).resolve()
root = pathlib.Path(os.environ["REGISTRATION_TEST_STATE"])
key = hashlib.sha256(str(top).encode()).hexdigest()
state = root / key
def record_exception(kind, value, tb):
    with (root / "fake-errors.jsonl").open("a") as log:
        log.write(json.dumps({"cwd": str(top), "argv": sys.argv, "error": str(value), "type": kind.__name__}) + "\n")
sys.excepthook = record_exception
config = json.loads((state / "config.json").read_text())
lock_path = top / ".git" / "mao-orca-register.lock"
held = False
if lock_path.is_file():
    with lock_path.open("r+") as probe:
        try:
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            held = True
event = {"args": args, "lock_held": held}
with (state / "calls.jsonl").open("a") as log:
    log.write(json.dumps(event) + "\n")

def emit(payload, code=0):
    print(json.dumps(payload))
    raise SystemExit(code)

def wait_for(predicate):
    deadline = time.monotonic() + 8
    while not predicate():
        if time.monotonic() > deadline:
            emit({"ok": False, "error": {"code": "fixture_barrier_timeout"}}, 9)
        time.sleep(0.01)

if operation == "worktree current":
    registered = (state / "registered").exists()
    participants = config.get("initial_barrier", 0)
    if participants and not held:
        (state / ("initial-" + str(os.getpid()))).touch()
        wait_for(lambda: len(list(state.glob("initial-*"))) >= participants)
        # Preserve the observation made BEFORE the barrier. All contenders
        # therefore reach the helper with the same stale not-found evidence.
    mode = config.get("post_mode" if registered else "current_mode", "ok")
    if mode == "timeout": time.sleep(2)
    if mode == "malformed":
        print("not json")
        raise SystemExit(0)
    if mode == "unknown": emit({"ok": False, "error": {"code": "runtime_unavailable"}}, 1)
    if mode == "missing_ok": emit({"result": {"worktree": {"id": "repo-test::" + str(top), "path": str(top)}}})
    if mode == "error_with_result": emit({"ok": False, "error": {"code": "selector_not_found"}, "result": {"worktree": {"path": str(top)}}}, 1)
    if not registered or mode == "not_found":
        emit({"ok": False, "error": {"code": "selector_not_found"}}, config.get("missing_rc", 1))
    path = str(top) if mode != "wrong_path" else str(top.parent / "other")
    identity_path = str(top) if mode != "wrong_id_path" else str(top.parent / "other")
    repo_id = "repo-other" if mode == "wrong_repo" else "repo-test"
    emit({"ok": True, "result": {"worktree": {"id": repo_id + "::" + identity_path, "path": path}}})

if operation == "status --json":
    mode = config.get("status_mode", "ok")
    if mode == "timeout": time.sleep(2)
    if mode == "fail": emit({"ok": False, "error": {"code": "offline"}}, 1)
    if mode == "false": emit({"ok": False, "result": {"runtime": {}}})
    if mode == "malformed":
        print("not json")
        raise SystemExit(0)
    emit({"ok": True, "result": {"runtime": {"reachable": True, "appVersion": "1.4.200", "capabilities": ["terminal.multiplex.v1"]}}})

if operation == "repo add":
    if args != ["repo", "add", "--path", str(top), "--json"]:
        emit({"ok": False, "error": {"code": "wrong_argv"}}, 1)
    if not held: emit({"ok": False, "error": {"code": "unlocked_mutation"}}, 1)
    pending = json.loads(lock_path.read_text())
    if pending.get("state") != "pending" or pending.get("project") != str(top):
        emit({"ok": False, "error": {"code": "missing_durable_intent"}}, 1)
    (state / "add-started").touch()
    participants = config.get("add_barrier", 0)
    if participants:
        (root / ("add-enter-" + key)).touch()
        wait_for(lambda: len(list(root.glob("add-enter-*"))) >= participants)
    mode = config.get("add_mode", "ok")
    if mode == "timeout": time.sleep(2)
    if mode == "fail": emit({"ok": False, "error": {"code": "write_failed"}}, 1)
    (state / "registered").touch()
    payload = {"ok": True, "result": {"repo": {"id": "repo-test", "path": str(top)}}}
    if mode == "missing_ok": del payload["ok"]
    if mode == "false": payload["ok"] = False
    if mode == "missing_id": del payload["result"]["repo"]["id"]
    if mode == "wrong_path": payload["result"]["repo"]["path"] = str(top.parent / "other")
    if mode == "malformed":
        print("not json")
        raise SystemExit(0)
    emit(payload)

emit({"ok": False, "error": {"code": "unexpected_command"}}, 1)
'''

BASH_DETECT = r'''
set -euo pipefail
source "$1/orca-runtime.sh"
source "$1/spawn-worker-orca.sh"
PROJECT_DIR="$2"
export REGISTRATION_TEST_PROJECT
REGISTRATION_TEST_PROJECT=$(git -C "$PROJECT_DIR" rev-parse --show-toplevel)
LIGHTWEIGHT_MODE=0 NO_ORCA_MODE=0 DRY_RUN="${TEST_DRY_RUN:-0}" ORCA_SUPERVISED=0
ORCA_MODE="" ORCA_WORKTREE_ID=""
detect_orca_mode
printf '%s\n' "${ORCA_CURRENT_WORKTREE_JSON:-}"
[ "$ORCA_MODE" = auto ]
'''


class RegistrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="orca-registration-")
        self.root = Path(self.temp.name).resolve()
        self.state_root = self.root / "state"
        self.state_root.mkdir()
        self.cli = self.root / "fake orca"
        self.cli.write_text(FAKE_ORCA)
        self.cli.chmod(0o755)
        self.env = {**os.environ, "REGISTRATION_TEST_STATE": str(self.state_root), "ORCA_CLI_COMMAND": str(self.cli)}
        self.processes: list[subprocess.Popen[str]] = []

    def tearDown(self) -> None:
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)
        self.temp.cleanup()

    def state(self, repo: Path) -> Path:
        return self.state_root / hashlib.sha256(str(repo.resolve()).encode()).hexdigest()

    def repo(self, name: str = "project with spaces", **config: object) -> Path:
        repo = self.root / name
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True, timeout=10)
        state = self.state(repo)
        state.mkdir()
        (state / "config.json").write_text(json.dumps(config))
        return repo

    def command(self, repo: Path, *extra: str) -> list[str]:
        return [sys.executable, str(HELPER), "--project", str(repo), "--orca-cli", str(self.cli), *extra]

    def run_helper(self, repo: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(self.command(repo, *extra), env=self.env, capture_output=True, text=True, timeout=20)

    def spawn(self, command: list[str]) -> subprocess.Popen[str]:
        process = subprocess.Popen(command, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append(process)
        return process

    def collect(self, process: subprocess.Popen[str]) -> tuple[int, str, str]:
        stdout, stderr = process.communicate(timeout=20)
        return process.returncode, stdout, stderr

    def calls(self, repo: Path, prefix: tuple[str, ...] = ()) -> list[dict[str, object]]:
        path = self.state(repo) / "calls.jsonl"
        entries = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [item for item in entries if item["args"][:len(prefix)] == list(prefix)]

    def assert_failure(self, result: subprocess.CompletedProcess[str], reason: str, code: int = 1) -> None:
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], reason)

    def test_three_real_spawn_processes_with_stale_not_found_register_once(self) -> None:
        repo = self.repo(initial_barrier=3)
        child = repo / "subdirectory"
        child.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(repo, target_is_directory=True)
        contenders = [self.spawn(["bash", "-c", BASH_DETECT, "_", str(SCRIPT_DIR), str(path)]) for path in (repo, child, alias)]
        for process in contenders:
            code, stdout, stderr = self.collect(process)
            errors = self.state_root / "fake-errors.jsonl"
            diagnostics = errors.read_text() if errors.exists() else ""
            self.assertEqual(code, 0, stdout + stderr + diagnostics + json.dumps(self.calls(repo)))
        adds = self.calls(repo, ("repo", "add"))
        self.assertEqual(len(adds), 1)
        self.assertTrue(adds[0]["lock_held"])
        current = self.calls(repo, ("worktree", "current"))
        self.assertEqual(sum(not item["lock_held"] for item in current), 3)
        self.assertEqual(sum(item["lock_held"] for item in current), 4)
        self.assertEqual(len(list(self.state(repo).glob("initial-*"))), 3)

    def test_different_repositories_enter_registration_concurrently(self) -> None:
        repos = [self.repo("repo-a", add_barrier=2), self.repo("repo-b", add_barrier=2)]
        contenders = [self.spawn(self.command(repo)) for repo in repos]
        for process in contenders:
            code, stdout, stderr = self.collect(process)
            self.assertEqual(code, 0, stdout + stderr)
        # The fake mutation rendezvous could only complete if both independent
        # Git common-dir critical sections were entered at the same time.
        self.assertEqual(len(list(self.state_root.glob("add-enter-*"))), 2)
        for repo in repos:
            self.assertEqual(len(self.calls(repo, ("repo", "add"))), 1)

    def test_already_registered_is_rechecked_without_mutation(self) -> None:
        repo = self.repo()
        (self.state(repo) / "registered").touch()
        result = self.run_helper(repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["registration"]["status"], "already_registered")
        self.assertEqual(self.calls(repo, ("repo", "add")), [])
        self.assertEqual(len(self.calls(repo)), 1)
        self.assertTrue(self.calls(repo)[0]["lock_held"])

    def test_dry_run_creates_no_lock_and_performs_no_cli_call(self) -> None:
        repo = self.repo()
        self.assert_failure(self.run_helper(repo, "--dry-run"), "registration_dry_run")
        self.assertFalse((repo / ".git" / LOCK_NAME).exists())
        self.assertEqual(self.calls(repo), [])
        env = {**self.env, "TEST_DRY_RUN": "1"}
        result = subprocess.run(["bash", "-c", BASH_DETECT, "_", str(SCRIPT_DIR), str(repo)], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ORCA_RUN: orca repo add --path", result.stderr)
        self.assertFalse((repo / ".git" / LOCK_NAME).exists())
        self.assertEqual(self.calls(repo, ("repo", "add")), [])

    def test_busy_lock_times_out_without_queries_and_is_not_removed(self) -> None:
        repo = self.repo()
        path = repo / ".git" / LOCK_NAME
        with path.open("w") as lock:
            path.chmod(0o600)
            inode = path.stat().st_ino
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assert_failure(self.run_helper(repo, "--lock-timeout", "0.1"), "registration_lock_busy", 75)
            self.assertEqual(path.stat().st_ino, inode)
            self.assertEqual(self.calls(repo), [])
        # Kernel release permits the next attempt; no age-based unlink needed.
        result = self.run_helper(repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.stat().st_ino, inode)

    def test_linked_worktree_uses_the_same_git_common_dir_lock(self) -> None:
        repo = self.repo()
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "fixture"], check=True, capture_output=True, timeout=10)
        linked = self.root / "linked"
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-qb", "linked", str(linked)], check=True, capture_output=True, timeout=10)
        with (repo / ".git" / LOCK_NAME).open("w") as lock:
            os.fchmod(lock.fileno(), 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assert_failure(self.run_helper(linked, "--lock-timeout", "0.1"), "registration_lock_busy", 75)
        self.assertEqual(self.calls(linked), [])

    def test_unsafe_lock_files_are_preserved_without_cli_calls(self) -> None:
        for kind in ("symlink", "fifo", "permissions", "hardlink"):
            with self.subTest(kind=kind):
                repo = self.repo(kind)
                path = repo / ".git" / LOCK_NAME
                original = self.root / (kind + "-target")
                original.write_text("untouched")
                original.chmod(0o600)
                if kind == "symlink": path.symlink_to(original)
                elif kind == "fifo": os.mkfifo(path, mode=0o600)
                elif kind == "hardlink": os.link(original, path)
                else:
                    path.write_text("untouched lock")
                    path.chmod(0o644)
                before = path.lstat()
                self.assert_failure(self.run_helper(repo), "registration_lock_unsafe", 74)
                self.assertEqual(path.lstat().st_ino, before.st_ino)
                self.assertEqual(original.read_text(), "untouched")
                self.assertEqual(self.calls(repo), [])

    def test_only_explicit_not_found_allows_registration(self) -> None:
        modes = {"unknown": "current_query_failed", "malformed": "cli_invalid_json", "missing_ok": "current_query_failed", "error_with_result": "current_contract_conflict"}
        for mode, reason in modes.items():
            with self.subTest(mode=mode):
                repo = self.repo(mode, current_mode=mode)
                self.assert_failure(self.run_helper(repo), reason)
                self.assertEqual(self.calls(repo, ("repo", "add")), [])
        repo = self.repo("zero-exit-not-found", missing_rc=0)
        self.assertEqual(self.run_helper(repo).returncode, 0)

    def test_existing_wrong_project_or_id_never_registers(self) -> None:
        for mode in ("wrong_path", "wrong_id_path"):
            with self.subTest(mode=mode):
                repo = self.repo(mode, post_mode=mode)
                (self.state(repo) / "registered").touch()
                result = self.run_helper(repo)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls(repo, ("repo", "add")), [])

    def test_status_failure_never_registers(self) -> None:
        for mode in ("fail", "false", "malformed"):
            with self.subTest(mode=mode):
                repo = self.repo(mode, status_mode=mode)
                result = self.run_helper(repo)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("SPAWN_WORKER_ORCA_AUTO_REGISTER_SKIPPED", result.stderr)
                self.assertEqual(self.calls(repo, ("repo", "add")), [])

    def test_add_requires_explicit_ok_and_repo_identity_without_retry(self) -> None:
        for mode in ("missing_ok", "false", "missing_id", "wrong_path", "malformed", "fail"):
            with self.subTest(mode=mode):
                repo = self.repo(mode, add_mode=mode)
                result = self.run_helper(repo)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("orca repo add 失败", result.stderr)
                self.assertEqual(len(self.calls(repo, ("repo", "add"))), 1)
                self.assertEqual(len(self.calls(repo, ("worktree", "current"))), 1)
                self.assertEqual(json.loads((repo / ".git" / LOCK_NAME).read_text())["state"], "pending")
                if mode != "fail": self.assertTrue((self.state(repo) / "registered").exists())

    def test_post_add_identity_mismatch_preserves_registration_and_releases_lock(self) -> None:
        for mode in ("wrong_path", "wrong_id_path", "wrong_repo", "not_found", "missing_ok"):
            with self.subTest(mode=mode):
                repo = self.repo(mode, post_mode=mode)
                result = self.run_helper(repo)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("复验失败", result.stderr)
                self.assertTrue((self.state(repo) / "registered").exists())
                self.assertEqual(len(self.calls(repo, ("repo", "add"))), 1)
                self.assertEqual(json.loads((repo / ".git" / LOCK_NAME).read_text())["repo_id"], "repo-test")
                with (repo / ".git" / LOCK_NAME).open("r+") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_uncertain_add_blocks_next_process_until_exact_identity_is_observed(self) -> None:
        repo = self.repo(add_mode="timeout")
        first = self.spawn(self.command(repo, "--cli-timeout", "1"))
        deadline = time.monotonic() + 10
        while not (self.state(repo) / "add-started").exists():
            if first.poll() is not None or time.monotonic() >= deadline:
                self.fail("first process did not reach the mutating RPC")
            time.sleep(0.01)
        marker = repo / ".git" / LOCK_NAME
        pending_before = marker.read_bytes()
        second = self.spawn(self.command(repo))
        first_code, first_out, first_err = self.collect(first)
        second_code, second_out, second_err = self.collect(second)
        self.assertEqual(first_code, 75, first_out + first_err)
        self.assertEqual(json.loads(first_out)["error"]["code"], "cli_timeout")
        self.assertEqual(second_code, 75, second_out + second_err)
        self.assertEqual(json.loads(second_out)["error"]["code"], "registration_prior_outcome_unknown")
        self.assertEqual(len(self.calls(repo, ("repo", "add"))), 1)
        self.assertEqual(marker.read_bytes(), pending_before)
        # Model a later server-side result becoming observable. The next
        # invocation may reuse this exact identity but must not submit again.
        (self.state(repo) / "registered").touch()
        resolved = self.run_helper(repo)
        self.assertEqual(resolved.returncode, 0, resolved.stdout + resolved.stderr)
        self.assertEqual(json.loads(resolved.stdout)["registration"]["status"], "already_registered")
        self.assertEqual(marker.read_bytes(), b"")
        self.assertEqual(len(self.calls(repo, ("repo", "add"))), 1)

    def test_acknowledged_repo_identity_cannot_be_reconciled_to_another_repo(self) -> None:
        repo = self.repo(post_mode="wrong_repo")
        first = self.run_helper(repo)
        self.assertNotEqual(first.returncode, 0)
        marker = repo / ".git" / LOCK_NAME
        pending_before = marker.read_bytes()
        self.assert_failure(self.run_helper(repo), "registration_pending_identity_mismatch", 75)
        self.assert_failure(self.run_helper(repo, "--probe-only"), "registration_pending_identity_mismatch", 75)
        detector = subprocess.run(["bash", "-c", BASH_DETECT, "_", str(SCRIPT_DIR), str(repo)], env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(detector.returncode, 1, detector.stdout + detector.stderr)
        self.assertEqual(marker.read_bytes(), pending_before)
        self.assertEqual(len(self.calls(repo, ("repo", "add"))), 1)

    def test_foreign_marker_is_not_cleared_or_used_for_registration(self) -> None:
        repo = self.repo()
        marker = repo / ".git" / LOCK_NAME
        marker.write_text("unknown owner state")
        marker.chmod(0o600)
        self.assert_failure(self.run_helper(repo), "registration_marker_unknown", 74)
        self.assertEqual(marker.read_text(), "unknown owner state")
        self.assertEqual(self.calls(repo), [])

    def test_each_critical_cli_phase_is_bounded(self) -> None:
        # Inject TimeoutExpired at the actual subprocess boundary, checking its
        # timeout argument. A 0.2-second fake-process timer previously expired
        # during interpreter startup, before reaching the intended phase. The
        # separate uncertain-add test retains a genuinely hanging CLI process.
        expected_counts = {"current_mode": (1, 0, 0), "status_mode": (1, 1, 0), "add_mode": (1, 1, 1), "post_mode": (2, 1, 1)}
        for phase in ("current_mode", "status_mode", "add_mode", "post_mode"):
            with self.subTest(phase=phase):
                repo = self.repo(phase)
                commands = []
                real_run = subprocess.run

                def fault_at_phase(argv, **kwargs):
                    self.assertEqual(kwargs.get("timeout"), 10)
                    commands.append(argv[1:])
                    current_count = sum(command[:2] == ["worktree", "current"] for command in commands)
                    operation = tuple(argv[1:3])
                    reached = (
                        (phase == "current_mode" and operation == ("worktree", "current"))
                        or (phase == "status_mode" and operation == ("status", "--json"))
                        or (phase == "add_mode" and operation == ("repo", "add"))
                        or (phase == "post_mode" and operation == ("worktree", "current") and current_count == 2)
                    )
                    if reached:
                        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
                    return real_run(argv, **kwargs)

                with mock.patch.dict(os.environ, self.env), mock.patch.object(registration.subprocess, "run", side_effect=fault_at_phase):
                    with self.assertRaises(registration.RegistrationError) as caught:
                        registration.register(str(self.cli), repo, repo / ".git", 10, 5)
                self.assertEqual((caught.exception.reason, caught.exception.code), ("cli_timeout", 75))
                counts = tuple(sum(command[:len(prefix)] == list(prefix) for command in commands) for prefix in (("worktree", "current"), ("status",), ("repo", "add")))
                self.assertEqual(counts, expected_counts[phase], "timeout must occur in the intended phase")
                with (repo / ".git" / LOCK_NAME).open("r+") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_pending_fsync_failure_prevents_mutating_rpc(self) -> None:
        repo = self.repo()
        with mock.patch.dict(os.environ, self.env), mock.patch.object(registration.os, "fsync", side_effect=OSError("injected fsync failure")):
            with self.assertRaises(registration.RegistrationError) as caught:
                registration.register(str(self.cli), repo, repo / ".git", 10, 5)
        self.assertEqual((caught.exception.reason, caught.exception.code), ("registration_marker_write_failed", 74))
        self.assertEqual(self.calls(repo, ("repo", "add")), [])
        self.assertEqual(json.loads((repo / ".git" / LOCK_NAME).read_text())["state"], "pending")

    def test_probe_mode_never_creates_lock_or_accepts_missing_ok(self) -> None:
        repo = self.repo(current_mode="missing_ok")
        self.assert_failure(self.run_helper(repo, "--probe-only"), "current_query_failed")
        self.assertFalse((repo / ".git" / LOCK_NAME).exists())
        self.assertEqual(self.calls(repo, ("repo", "add")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
