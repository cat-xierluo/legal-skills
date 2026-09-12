#!/usr/bin/env python3
"""真实 PM/Wave 入口的 sender 契约；fake 仅实现官方参数与已观察到的回执形状。"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent
FAKE = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
root = Path(os.environ["SENDER_FIXTURE"])
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as out:
    out.write(json.dumps(args) + "\n")
config = json.loads((root / "config.json").read_text())
command = tuple(args[:2])
allowed = {
 ("status", "--json"): set(),
 ("terminal", "show"): {"--terminal", "--json"},
 ("orchestration", "run-create"): {"--objective", "--from", "--json"},
 ("orchestration", "run-use"): {"--id", "--from", "--json"},
 ("orchestration", "run-current"): {"--from", "--json"},
 ("orchestration", "send"): {"--to", "--type", "--subject", "--body", "--from", "--json"},
 ("orchestration", "reply"): {"--id", "--body", "--from", "--json"},
 ("orchestration", "check"): {"--wait", "--types", "--timeout-ms", "--ack", "--terminal", "--json"},
 ("orchestration", "worker-release"): {"--dispatch", "--json"},
 ("orchestration", "worker-retain"): {"--dispatch", "--json"},
 ("orchestration", "worker-list"): {"--run", "--json"},
 ("orchestration", "worker-read"): {"--dispatch", "--limit", "--cursor", "--json"},
 ("orchestration", "worker-show"): {"--dispatch", "--json"},
 ("orchestration", "task-create"): {"--spec", "--task-title", "--run", "--from", "--json"},
}
if command not in allowed:
    raise SystemExit(96)
flags = {}
i = 2
while i < len(args):
    flag = args[i]
    if flag not in allowed[command]:
        raise SystemExit(95)
    if flag in ("--json", "--wait"):
        flags[flag] = True
        i += 1
    else:
        flags[flag] = args[i + 1]
        i += 2
runtime = config.get("runtime", "runtime-test")
response = {"ok": True, "result": {}, "_meta": {"runtimeId": runtime}}
state_file = root / "binding.json"
binding = json.loads(state_file.read_text())
if command == ("status", "--json"):
    if config.get("drift_after_bind") and (root / "bound").exists():
        runtime = "restarted"
    response["result"] = {"runtime": {"reachable": True, "runtimeId": runtime}}
elif command == ("terminal", "show"):
    sender = flags["--terminal"]
    terminal = {"handle": sender, "connected": True, "writable": True,
                "orphaned": False, "exitCause": None}
    terminal.update(config.get("terminal", {}))
    if sender == "term-closed":
        terminal.update(connected=False, writable=False, exitCause={"kind": "operator_close"})
    response["result"] = {"terminal": terminal}
    response["_meta"]["runtimeId"] = config.get("terminal_runtime", runtime)
elif command[1] in ("run-use", "run-create"):
    binding = {"id": flags.get("--id", "run-new"), "coordinator_handle": flags["--from"]}
    state_file.write_text(json.dumps(binding))
    (root / "bound").touch()
    response["result"] = {"run": {**binding, **config.get("bind_receipt", {})}}
    response["ok"] = config.get("bind_ok", True)
elif command[1] == "run-current":
    response["result"] = {"run": {**binding, **config.get("current", {})}}
elif command[1] == "task-create":
    response["result"] = {"task": {"id": "task-new"}}
elif command[1] == "worker-list":
    response["result"] = {"workers": [{"dispatch_id": "ctx-test", "terminal_state": "retained"}]}
if config.get("fail_command") == list(command):
    response = {"ok": False, "error": {"code": "fixture_failure"}}
    print(json.dumps(response))
    raise SystemExit(1)
print(json.dumps(response))
'''


class SenderBindingTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pm sender ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.fake = self.root / "fake-orca"
        self.fake.write_text(FAKE)
        self.fake.chmod(0o700)
        self.config = self.root / "config.json"
        self.config.write_text("{}")
        self.binding = self.root / "binding.json"
        self.binding.write_text(json.dumps({"id": "run-test", "coordinator_handle": "term-recorded"}))
        self.log = self.root / "calls.jsonl"
        self.log.touch()
        self.metadata = self.root / ".claude/agent-sessions/worker/METADATA.json"
        self.metadata.parent.mkdir(parents=True)
        self.data = {"session": {"orca": {"runtime_id": "runtime-test", "terminal_handle": "term-worker",
                     "supervised": {"run_id": "run-test", "coordinator_handle": "term-recorded", "dispatch_id": "ctx-test"}}}}
        self.save_metadata()
        self.env = dict(os.environ, ORCA_CLI_COMMAND=str(self.fake), SENDER_FIXTURE=str(self.root),
                        ORCA_TERMINAL_HANDLE="term-wrong-environment")

    def save_metadata(self):
        self.metadata.write_text(json.dumps(self.data))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def invoke(self, script, *args):
        return subprocess.run(["bash", str(SCRIPTS / script), *args], cwd=self.root, env=self.env,
                              capture_output=True, text=True, timeout=20)

    def pm(self, command, *args):
        return self.invoke("pm-orchestrate.sh", command, "--worktree", str(self.root), "--session", "worker", *args)

    def test_explicit_sender_routes_control_and_is_persisted_after_readback(self):
        commands = [("send", ["--text", "guidance"], "send", "--from"),
                    ("reply", ["--message-id", "msg", "--text", "answer"], "reply", "--from"),
                    ("wait", ["--timeout", "0"], "check", "--terminal"),
                    ("ack", ["--delivery-id", "delivery"], "check", "--terminal"),
                    ("release", [], "worker-release", None), ("retain", [], "worker-retain", None)]
        for command, args, verb, sender_flag in commands:
            with self.subTest(command=command):
                self.log.write_text("")
                result = self.pm(command, "--from", "term-explicit", *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = self.calls()
                use = ["orchestration", "run-use", "--id", "run-test", "--from", "term-explicit", "--json"]
                current = ["orchestration", "run-current", "--from", "term-explicit", "--json"]
                self.assertLess(calls.index(use), calls.index(current))
                last = calls[-1]
                self.assertEqual(last[:2], ["orchestration", verb])
                if sender_flag:
                    self.assertEqual(last[last.index(sender_flag) + 1], "term-explicit")
                else:
                    self.assertEqual(last, ["orchestration", verb, "--dispatch", "ctx-test", "--json"])
                self.assertNotIn("--run", last)
                print("SENDER_ROUTE: " + json.dumps(last))
                persisted = json.loads(self.metadata.read_text())["session"]["orca"]
                self.assertEqual(persisted["supervised"]["coordinator_handle"], "term-explicit")
                self.assertEqual(persisted["runtime_id"], "runtime-test")

    def test_accounting_list_uses_explicit_run_and_preserves_unreleased_lease(self):
        lease = self.root / "lease.json"
        lease.write_text("preserve\n")
        self.data["runtime"] = {"provider_lease": {"file": str(lease)}}
        self.save_metadata()
        result = self.pm("release")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls()[-1], ["orchestration", "worker-list", "--run", "run-test", "--json"])
        self.assertEqual(lease.read_text(), "preserve\n")
        print("SENDER_ACCOUNTING_SCOPE: " + json.dumps(self.calls()[-1]))

    def test_recorded_sender_wins_over_wrong_environment(self):
        before = self.metadata.read_bytes()
        result = self.pm("send", "--text", "test")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls()[-1][-3:], ["--from", "term-recorded", "--json"])
        self.assertEqual(self.metadata.read_bytes(), before)

    def test_missing_recorded_sender_never_uses_environment(self):
        self.data["session"]["orca"]["supervised"].pop("coordinator_handle")
        self.save_metadata()
        self.assertNotEqual(self.pm("wait", "--timeout", "0").returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_invalid_sender_runtime_or_binding_blocks_control_and_metadata(self):
        cases = [{"terminal": {"connected": False}}, {"terminal": {"writable": False}},
                 {"terminal": {"orphaned": True}}, {"terminal": {"handle": "term-other"}},
                 {"terminal": {"exitCause": {"kind": "operator_close"}}},
                 {"runtime": "other"}, {"runtime": None}, {"terminal_runtime": "other"},
                 {"bind_receipt": {"id": "wrong"}}, {"bind_receipt": {"coordinator_handle": "wrong"}},
                 {"bind_ok": False}, {"current": {"id": "wrong"}},
                 {"current": {"coordinator_handle": "wrong"}}, {"drift_after_bind": True},
                 {"fail_command": ["orchestration", "run-current"]}]
        for config in cases:
            with self.subTest(config=config):
                self.log.write_text("")
                self.config.write_text(json.dumps(config))
                before = self.metadata.read_bytes()
                result = self.pm("send", "--from", "term-explicit", "--text", "blocked")
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertFalse(any(call[:2] == ["orchestration", "send"] for call in self.calls()))
                self.assertEqual(self.metadata.read_bytes(), before)

    def test_legacy_runtime_requires_current_binding_before_migration(self):
        self.data["session"]["orca"].pop("runtime_id")
        self.save_metadata()
        result = self.pm("wait", "--timeout", "0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("historical continuity NOT_VERIFIED", result.stderr)
        calls = self.calls()
        verbs = [call[1] for call in calls]
        self.assertLess(verbs.index("run-current"), verbs.index("run-use"))
        self.assertEqual(json.loads(self.metadata.read_text())["session"]["orca"]["runtime_id"], "runtime-test")

    def test_legacy_wrong_binding_refuses_rebind(self):
        self.data["session"]["orca"].pop("runtime_id")
        self.save_metadata()
        self.config.write_text(json.dumps({"current": {"id": "other-run"}}))
        before = self.metadata.read_bytes()
        self.assertNotEqual(self.pm("wait", "--timeout", "0").returncode, 0)
        self.assertFalse(any(call[1] == "run-use" for call in self.calls()))
        self.assertEqual(self.metadata.read_bytes(), before)

    def test_read_only_routes_never_bind_or_rewrite_metadata(self):
        self.config.write_text(json.dumps({"terminal": {"connected": False}}))
        self.data["session"]["orca"].pop("runtime_id")
        self.save_metadata()
        before = self.metadata.read_bytes()
        for command in ("read", "peek", "show"):
            result = self.pm(command, "--from", "term-closed")
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(call[1] in ("worker-read", "worker-show") for call in self.calls()))
        self.assertEqual(self.metadata.read_bytes(), before)
        self.log.write_text("")
        result = self.pm("pr-audit", "--head-ref", "branch", "--head-sha", "0" * 40, "--from", "term-closed")
        self.assertNotEqual(result.returncode, 0)  # Invalid Git fixture; still no sender/metadata work.
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.metadata.read_bytes(), before)

    def test_new_run_explicit_and_injected_sender_and_missing_sender(self):
        for args, sender in ((["--from", "term-explicit"], "term-explicit"), ([], "term-wrong-environment")):
            with self.subTest(sender=sender):
                result = self.invoke("pm-orchestrate.sh", "run-create", "--objective", "new wave", *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["result"]["run"]["coordinator_handle"], sender)
        self.env.pop("ORCA_TERMINAL_HANDLE")
        self.log.write_text("")
        self.assertNotEqual(self.invoke("pm-orchestrate.sh", "run-create", "--objective", "missing").returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_new_run_with_session_context_prefers_recorded_sender(self):
        before = self.metadata.read_bytes()
        result = self.pm("run-create", "--objective", "next wave")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"]["run"]["coordinator_handle"], "term-recorded")
        self.assertEqual(self.metadata.read_bytes(), before)

    def test_wave_closed_injected_sender_creates_no_run_task_or_receipt(self):
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({"objective": "wave", "tasks": [{"key": "a", "spec": "task"}]}))
        receipt = self.root / "receipt.json"
        self.env["ORCA_TERMINAL_HANDLE"] = "term-closed"
        result = self.invoke("orca-wave-prepare.sh", "--manifest", str(manifest), "--receipt", str(receipt))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(receipt.exists())
        self.assertFalse(any(call[0] == "orchestration" for call in self.calls()))


if __name__ == "__main__":
    unittest.main()
