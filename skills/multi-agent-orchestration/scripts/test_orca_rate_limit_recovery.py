#!/usr/bin/env python3
"""Deterministic fake-Orca regression matrix for rate-limit recovery."""

from __future__ import annotations

import hashlib
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
TARGET = SCRIPT_DIR / "orca_rate_limit_recovery.py"
MANIFEST_CONTRACT = "multi-agent-orchestration.orca-rate-limit-workers.v1"


FAKE_ORCA = r'''#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import time

root = Path(__file__).resolve().parent
config_path = root / "fake-config.json"
log_path = root / "fake-log.jsonl"
config = json.loads(config_path.read_text())
args = sys.argv[1:]
with log_path.open("a") as log:
    log.write(json.dumps({"args": args, "at": time.time_ns()}) + "\n")

def worker(handle):
    for item in config["workers"]:
        if item["handle"] == handle:
            return item
    return None

def value_after(flag):
    return args[args.index(flag) + 1]

def emit(value, code=0):
    print(json.dumps(value))
    raise SystemExit(code)

if args[:2] == ["terminal", "list"]:
    mode = config.get("list_mode", "ok")
    if mode == "fail":
        emit({"ok": False, "error": {"code": "runtime"}}, 1)
    if mode == "malformed":
        print("not-json")
        raise SystemExit(0)
    terminals = []
    for item in config["workers"]:
        terminals.append({
            "handle": item["handle"],
            "incarnationId": item["incarnation"],
            "connected": item.get("connected", True),
            "writable": item.get("writable", True),
            "lastOutputAt": item.get("last_output_at"),
        })
    emit({"ok": True, "result": {"terminals": terminals, "totalCount": len(terminals),
         "truncated": mode == "truncated"}})

handle = value_after("--terminal") if "--terminal" in args else ""
item = worker(handle)
if item is None:
    emit({"ok": False, "error": {"code": "selector_not_found"}}, 1)

if args[:2] == ["terminal", "show"]:
    count_path = root / ("show-count-" + handle)
    count = int(count_path.read_text()) + 1 if count_path.exists() else 1
    count_path.write_text(str(count))
    mode = item.get("show_mode", "ok")
    if mode == "fail":
        emit({"ok": False, "error": {"code": "runtime"}}, 1)
    if mode == "malformed":
        emit({"ok": True, "result": {"terminal": "bad"}})
    incarnation = item["incarnation"]
    if mode == "drift_pre" and count >= 2:
        incarnation = "incarnation-drifted"
    if mode == "drift_post" and count == 3:
        incarnation = "incarnation-drifted"
    if item.get("break_state_after_post") and count == 3:
        Path(config["state_dir"]).chmod(0o500)
    emit({"ok": True, "result": {"terminal": {
        "handle": handle,
        "incarnationId": incarnation,
        "connected": item.get("connected", True),
        "writable": item.get("writable", True),
        "lastOutputAt": item.get("last_output_at"),
    }}})

if args[:2] == ["terminal", "read"]:
    mode = item.get("read_mode", "ok")
    if mode == "fail":
        emit({"ok": False, "error": {"code": "runtime"}}, 1)
    if mode == "malformed":
        emit({"ok": True, "result": {"terminal": {"handle": handle, "tail": "bad"}}})
    if "--cursor" in args:
        cursor = value_after("--cursor")
        if mode == "drift_cursor":
            emit({"ok": True, "result": {"terminal": {"handle": handle,
                 "latestCursor": str(int(cursor) + 1), "nextCursor": str(int(cursor) + 1),
                 "tail": ["new output"], "source": "stream"}}})
        emit({"ok": True, "result": {"terminal": {"handle": handle,
             "latestCursor": cursor, "nextCursor": cursor, "tail": [], "source": "stream"}}})
    emit({"ok": True, "result": {"terminal": {"handle": handle,
         "latestCursor": item["cursor"], "nextCursor": item["cursor"],
         "tail": item["tail"], "source": item.get("source", "stream")}}})

if args[:2] == ["terminal", "wait"]:
    mode = item.get("wait_mode", "idle")
    if mode == "retrying":
        emit({"ok": False, "error": {"code": "timeout", "message": "timeout"}}, 1)
    if mode == "fail":
        emit({"ok": False, "error": {"code": "runtime"}}, 1)
    if mode == "malformed":
        emit({"ok": True, "result": {"wait": {"handle": handle, "satisfied": False}}})
    if mode == "idle_missing_status":
        emit({"ok": True, "result": {"wait": {"handle": handle, "condition": "tui-idle",
             "satisfied": True, "exitCode": None}}})
    if mode == "idle_exited":
        emit({"ok": True, "result": {"wait": {"handle": handle, "condition": "tui-idle",
             "satisfied": True, "status": "exited", "exitCode": 0}}})
    emit({"ok": True, "result": {"wait": {"handle": handle, "condition": "tui-idle",
         "satisfied": True, "status": "running", "exitCode": None}}})

if args[:2] == ["terminal", "send"]:
    mode = item.get("send_mode", "ok")
    if mode == "fail":
        emit({"ok": False, "error": {"code": "runtime"}}, 1)
    if mode == "malformed":
        print("not-json")
        raise SystemExit(0)
    emit({"ok": True, "result": {"sent": True}})

emit({"ok": False, "error": {"code": "unsupported"}}, 1)
'''


def worker(
    handle: str,
    *,
    group: str = "account-a",
    provider: str = "glm",
    age_seconds: int = 600,
    cursor: int = 10,
    tail: list[str] | None = None,
    **extra: object,
) -> dict[str, object]:
    value: dict[str, object] = {
        "handle": handle,
        "incarnation": f"inc-{handle}",
        "provider": provider,
        "group": group,
        "last_output_at": int(time.time() * 1000) - age_seconds * 1000,
        "cursor": cursor,
        "tail": tail or ["HTTP 429 Too Many Requests: usage limit reached"],
        "wait_mode": "idle",
    }
    value.update(extra)
    return value


class RecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="orca-recovery-test-", dir="/private/tmp")
        self.root = Path(self.temp.name)
        self.fake = self.root / "orca"
        self.fake.write_text(FAKE_ORCA)
        self.fake.chmod(0o755)
        self.config = self.root / "fake-config.json"
        self.log = self.root / "fake-log.jsonl"
        self.state_dir = self.root / "private-state"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_case(self, items: list[dict[str, object]], **top: object) -> Path:
        payload = {"workers": items, **top}
        self.config.write_text(json.dumps(payload))
        manifest = {
            "contract": MANIFEST_CONTRACT,
            "workers": [
                {
                    "source": "orca",
                    "terminal_handle": item["handle"],
                    "incarnation_id": item["incarnation"],
                    "provider": item["provider"],
                    "account_group": item["group"],
                }
                for item in items
            ],
        }
        path = self.root / "workers.json"
        path.write_text(json.dumps(manifest))
        return path

    def run_target(self, manifest: Path, *, execute: bool = False, extra: list[str] | None = None) -> subprocess.CompletedProcess[str]:
        command = [
            "python3", str(TARGET), "--manifest", str(manifest), "--state-dir", str(self.state_dir),
            "--terminal-delay-ms", "100", "--group-delay-ms", "200", "--json",
        ]
        if execute:
            command.append("--execute")
        if extra:
            command.extend(extra)
        env = {"PATH": os.environ["PATH"], "ORCA_CLI_COMMAND": str(self.fake)}
        return subprocess.run(command, capture_output=True, text=True, env=env, check=False)

    def calls(self, command: tuple[str, str]) -> list[dict[str, object]]:
        if not self.log.exists():
            return []
        entries = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [entry for entry in entries if entry["args"][:2] == list(command)]

    def receipt(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        return json.loads(result.stdout)

    def test_dry_run_is_read_only_and_idle_is_candidate(self) -> None:
        manifest = self.write_case([worker("term-a")])
        result = self.run_target(manifest)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        item = self.receipt(result)["workers"][0]
        self.assertEqual(item["state"], "RATE_LIMIT_IDLE")
        self.assertEqual(item["action"], "resume_candidate")
        self.assertFalse(self.state_dir.exists())
        self.assertEqual(self.calls(("terminal", "send")), [])

    def test_retrying_and_running_are_not_sent(self) -> None:
        items = [
            worker("term-retry", age_seconds=5, wait_mode="retrying"),
            worker("term-running", age_seconds=5, wait_mode="retrying", tail=["working on tests"]),
        ]
        result = self.run_target(self.write_case(items), execute=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        states = [item["state"] for item in self.receipt(result)["workers"]]
        self.assertEqual(states, ["RATE_LIMIT_RETRYING", "RUNNING"])
        self.assertEqual(self.calls(("terminal", "send")), [])

    def test_idle_executes_once_and_new_evidence_can_execute_again(self) -> None:
        item = worker("term-idle")
        manifest = self.write_case([item])
        first = self.run_target(manifest, execute=True)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(len(self.calls(("terminal", "send"))), 1)
        second = self.run_target(manifest, execute=True)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(len(self.calls(("terminal", "send"))), 1)
        self.assertEqual(self.receipt(second)["workers"][0]["action"], "already_handled")

        item["cursor"] = 11
        item["last_output_at"] = int(time.time() * 1000) - 600_000
        manifest = self.write_case([item])
        third = self.run_target(manifest, execute=True)
        self.assertEqual(third.returncode, 0, third.stdout + third.stderr)
        self.assertEqual(len(self.calls(("terminal", "send"))), 2)

    def test_mixed_auth_configuration_text_is_not_quota_and_is_redacted(self) -> None:
        private_marker = "private-marker-should-not-print"
        item = worker("term-mixed", tail=[f"HTTP 429; invalid api key {private_marker}; configuration error"])
        result = self.run_target(self.write_case([item]), execute=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.receipt(result)["workers"][0]["reason"], "provider_auth_not_quota")
        self.assertNotIn(private_marker, result.stdout + result.stderr)
        self.assertEqual(self.calls(("terminal", "send")), [])

    def test_discussion_or_test_output_about_429_is_not_actionable(self) -> None:
        items = [
            worker("term-expected", tail=["The expected response is HTTP 429 Too Many Requests"]),
            worker("term-provider-returns", tail=["Provider returns HTTP 429 under load"]),
            worker("term-discussion", tail=["Analyzing rate limit behavior and retry design"]),
            worker("term-design-note", tail=["Design note: quota exceeded responses should be retried"]),
            worker("term-account-doc", tail=["The account hit your limit according to the documentation"]),
        ]
        result = self.run_target(self.write_case(items), execute=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(
            all(item["reason"] == "no_actionable_quota_evidence" for item in self.receipt(result)["workers"])
        )
        self.assertEqual(self.calls(("terminal", "send")), [])

    def test_quota_followed_by_substantive_progress_is_not_tail_anchored(self) -> None:
        item = worker("term-progress", tail=["HTTP 429 Too Many Requests", "completed retry and editing files"])
        result = self.run_target(self.write_case([item]), execute=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.receipt(result)["workers"][0]["reason"], "no_actionable_quota_evidence")
        self.assertEqual(self.calls(("terminal", "send")), [])

    def test_unwritable_and_stale_evidence_are_unknown(self) -> None:
        items = [worker("term-readonly", writable=False), worker("term-stale", age_seconds=30000)]
        result = self.run_target(self.write_case(items), execute=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        reasons = [item["reason"] for item in self.receipt(result)["workers"]]
        self.assertEqual(reasons, ["terminal_not_writable", "quota_evidence_stale"])
        self.assertEqual(self.calls(("terminal", "send")), [])

    def test_malformed_orca_failure_and_truncated_list_fail_closed(self) -> None:
        cases = [
            ({"list_mode": "truncated"}, "terminal_list_truncated_or_invalid"),
            ({"list_mode": "malformed"}, "terminal_list_malformed"),
            ({"list_mode": "fail"}, "terminal_list_failed"),
            ({"worker_extra": {"show_mode": "malformed"}}, "terminal_show_malformed"),
            ({"worker_extra": {"read_mode": "malformed"}}, "terminal_read_malformed"),
            ({"worker_extra": {"wait_mode": "malformed"}}, "terminal_wait_malformed"),
            ({"worker_extra": {"wait_mode": "idle_missing_status"}}, "terminal_wait_malformed"),
            ({"worker_extra": {"wait_mode": "idle_exited"}}, "terminal_wait_malformed"),
            ({"worker_extra": {"wait_mode": "fail"}}, "terminal_wait_failed"),
        ]
        for index, (settings, expected_reason) in enumerate(cases):
            with self.subTest(index=index):
                self.log.unlink(missing_ok=True)
                item = worker(f"term-fault-{index}", **settings.get("worker_extra", {}))
                manifest = self.write_case([item], **{k: v for k, v in settings.items() if k != "worker_extra"})
                result = self.run_target(manifest, execute=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.receipt(result)["reason"], expected_reason)
                self.assertEqual(self.calls(("terminal", "send")), [])

    def test_manifest_and_tmux_arguments_are_rejected(self) -> None:
        manifest = self.write_case([worker("term-a")])
        value = json.loads(manifest.read_text())
        value["workers"][0]["source"] = "tmux"
        manifest.write_text(json.dumps(value))
        result = self.run_target(manifest, execute=True)
        self.assertEqual(result.returncode, 65)
        self.assertEqual(self.calls(("terminal", "send")), [])
        result = self.run_target(manifest, execute=True, extra=["--tmux", "x"])
        self.assertEqual(result.returncode, 64)

    def test_group_staggering_is_deterministic(self) -> None:
        items = [worker("term-c", group="group-b"), worker("term-b", group="group-a"), worker("term-a", group="group-a")]
        result = self.run_target(self.write_case(items), execute=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        sends = self.calls(("terminal", "send"))
        key = lambda item: (hashlib.sha256((item["provider"] + "\0" + item["group"]).encode()).hexdigest()[:16], item["handle"])
        expected = [item["handle"] for item in sorted(items, key=key)]
        actual = [entry["args"][entry["args"].index("--terminal") + 1] for entry in sends]
        self.assertEqual(actual, expected)
        ordered = sorted(items, key=key)
        for index in range(1, len(sends)):
            expected_ms = 100 if ordered[index - 1]["group"] == ordered[index]["group"] else 200
            elapsed_ms = (sends[index]["at"] - sends[index - 1]["at"]) / 1_000_000
            self.assertGreaterEqual(elapsed_ms, expected_ms - 10)

    def test_pre_send_identity_drift_blocks_without_send(self) -> None:
        result = self.run_target(self.write_case([worker("term-drift", show_mode="drift_pre")]), execute=True)
        self.assertEqual(result.returncode, 75)
        self.assertEqual(self.receipt(result)["reason"], "terminal_identity_drift")
        self.assertEqual(self.calls(("terminal", "send")), [])

    def test_send_or_postcheck_uncertainty_is_idempotently_suppressed(self) -> None:
        for mode, expected_sends in (("fail", 1), ("post", 1)):
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                self.state_dir = self.root / f"private-state-{mode}"
                extra = {"send_mode": "fail"} if mode == "fail" else {"show_mode": "drift_post"}
                manifest = self.write_case([worker(f"term-{mode}", **extra)])
                first = self.run_target(manifest, execute=True)
                self.assertNotEqual(first.returncode, 0)
                self.assertEqual(len(self.calls(("terminal", "send"))), expected_sends)
                first_receipt = self.receipt(first)
                self.assertEqual(first_receipt["status"], "SEND_OUTCOME_UNKNOWN")
                self.assertEqual(first_receipt["workers"][0]["action"], "outcome_unknown")
                second = self.run_target(manifest, execute=True)
                self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
                self.assertEqual(len(self.calls(("terminal", "send"))), expected_sends)
                self.assertEqual(self.receipt(second)["workers"][0]["action"], "already_handled")

    def test_wake_accepted_state_commit_failure_preserves_intent(self) -> None:
        item = worker("term-state-commit", break_state_after_post=True)
        manifest = self.write_case([item], state_dir=str(self.state_dir))
        first = self.run_target(manifest, execute=True)
        self.assertEqual(first.returncode, 74, first.stdout + first.stderr)
        first_receipt = self.receipt(first)
        self.assertEqual(first_receipt["status"], "WAKE_ACCEPTED_STATE_COMMIT_FAILED")
        self.assertEqual(first_receipt["summary"]["wake_accepted"], 1)
        self.assertEqual(first_receipt["workers"][0]["action"], "wake_accepted_state_commit_failed")
        self.assertEqual(len(self.calls(("terminal", "send"))), 1)
        self.state_dir.chmod(0o700)
        second = self.run_target(manifest, execute=True)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(len(self.calls(("terminal", "send"))), 1)
        self.assertEqual(self.receipt(second)["workers"][0]["action"], "already_handled")

    def test_state_symlink_and_insecure_permissions_fail_closed(self) -> None:
        manifest = self.write_case([worker("term-state")])
        real = self.root / "real-state"
        real.mkdir(mode=0o700)
        self.state_dir.symlink_to(real, target_is_directory=True)
        result = self.run_target(manifest, execute=True)
        self.assertEqual(result.returncode, 74)
        self.assertEqual(self.calls(("terminal", "send")), [])
        self.state_dir.unlink()
        self.state_dir.mkdir(mode=0o755)
        result = self.run_target(manifest, execute=True)
        self.assertEqual(result.returncode, 74)
        self.assertEqual(self.calls(("terminal", "send")), [])

    def test_busy_state_lock_fails_immediately_without_send(self) -> None:
        manifest = self.write_case([worker("term-lock")])
        self.state_dir.mkdir(mode=0o700)
        lock_path = self.state_dir / "lock"
        with lock_path.open("w") as lock:
            lock_path.chmod(0o600)
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            started = time.monotonic()
            result = self.run_target(manifest, execute=True)
            elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 75)
        self.assertLess(elapsed, 2)
        self.assertEqual(self.receipt(result)["reason"], "state_lock_busy")
        self.assertEqual(self.calls(("terminal", "send")), [])

    def test_non_regular_state_lock_is_rejected(self) -> None:
        manifest = self.write_case([worker("term-fifo")])
        self.state_dir.mkdir(mode=0o700)
        os.mkfifo(self.state_dir / "lock", mode=0o600)
        result = self.run_target(manifest, execute=True)
        self.assertEqual(result.returncode, 74)
        self.assertEqual(self.receipt(result)["reason"], "state_file_not_private")
        self.assertEqual(self.calls(("terminal", "send")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
