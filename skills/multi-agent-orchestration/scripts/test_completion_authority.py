#!/usr/bin/env python3
"""Exercise the real hook with launch-bound receipts and an isolated CLI."""

import hashlib
import base64
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent


class CompletionAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.directory = self.root / "agent-authority"
        self.directory.mkdir()
        self.authority = self.directory / "worker.json"
        self.write_json(self.authority, {"schema": "multi-agent-orchestration.authority-receipt.v1"})
        self.sha = hashlib.sha256(self.authority.read_bytes()).hexdigest()
        self.receipt = self.directory / "worker.completion.json"
        self.capability = "dcap_test_nonsecret"
        self.data = {
            "schema": "multi-agent-orchestration.completion-authority.v1",
            "state": "active", "task_id": "task_test", "dispatch_id": "ctx_test",
            "terminal_handle": "term_test", "run_id": "run_test",
            "process_incarnation": "process_test", "runtime_id": "runtime_test",
            "capability_hash": hashlib.sha256(self.capability.encode()).hexdigest(),
            "authority_receipt_file": str(self.authority), "authority_receipt_sha256": self.sha,
        }
        self.write_json(self.receipt, self.data)
        self.live = {"ok": True, "_meta": {"runtimeId": "runtime_test"}, "result": {"dispatch": {
            "id": "ctx_test", "task_id": "task_test", "assignee_handle": "term_test",
            "run_id": "run_test", "process_incarnation": "process_test",
            "capability_hash": self.data["capability_hash"],
        }}}
        self.live_file = self.root / "live.json"
        self.write_json(self.live_file, self.live)
        self.cli = self.root / "orca"
        self.cli.write_text("#!/bin/sh\n[ \"$*\" = 'orchestration dispatch-show --task task_test --json' ] || exit 64\n"
                            + "cat " + shlex.quote(str(self.live_file)) + "\n")
        self.cli.chmod(0o700)
        self.auth = self.root / "authorization.json"
        self.command = (
            "orca orchestration send --from term_test --dispatch-capability dcap_test_nonsecret \\\n"
            "  --type worker_done --subject done \\\n"
            "  --body summary --task-id task_test --dispatch-id ctx_test --outcome succeeded --json"
        )
        self.write_json(self.auth, {"policy": "deny_by_default", "authorized_commands": [],
                                   "allowed_shell_commands": [], "authorization_source": ""})
        self.env = dict(os.environ, WORKER_INSTALL_AUTH_FILE=str(self.auth), WORKER_INSTALL_AUTH_B64="",
                        WORKER_AUTHORITY_RECEIPT_FILE=str(self.authority),
                        WORKER_AUTHORITY_RECEIPT_CONTENT_SHA256=self.sha,
                        WORKER_COMPLETION_AUTHORITY_FILE=str(self.receipt), WORKER_ORCA_CLI_BIN=str(self.cli),
                        WORKER_GUARD_BACKEND="claude-code")

    def write_json(self, path, value):
        path.write_text(json.dumps(value))
        path.chmod(0o600)

    def hook(self, command=None):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "dependency-install-guard.py")],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command or self.command}}),
            env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def assert_denied(self, command=None):
        self.assertIn("ORCA_COMPLETION_AUTHORITY_INVALID", self.hook(command))

    def test_native_continued_command(self):
        self.assertIn("\\\n", self.command)
        self.assertEqual(self.hook(), "")

    def test_native_continuation_splits_join_command_words(self):
        commands = [
            self.command.replace("orca", "or\\\nca", 1),
            self.command.replace("orchestration", "orches\\\ntration", 1),
            self.command.replace("orca", '"or\\\nca"', 1),
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.hook(command), "")

    def test_restart_rejects_old_receipt(self):
        self.live["_meta"]["runtimeId"] = "runtime_restarted"
        self.write_json(self.live_file, self.live)
        self.assert_denied()

    def test_process_replaced(self):
        self.live["result"]["dispatch"]["process_incarnation"] = "process_replaced"
        self.write_json(self.live_file, self.live)
        self.assert_denied()

    def test_live_run_mismatch(self):
        self.live["result"]["dispatch"]["run_id"] = "run_other"
        self.write_json(self.live_file, self.live)
        self.assert_denied()

    def test_malformed_runtime_fails_closed(self):
        self.write_json(self.live_file, {"ok": True, "_meta": [], "result": []})
        self.assert_denied()

    def test_authority_content_is_pinned(self):
        self.write_json(self.authority, {"schema": "multi-agent-orchestration.authority-receipt.v1", "forged": True})
        self.assert_denied()

    def test_receipt_cannot_claim_another_authority(self):
        self.data["authority_receipt_file"] = str(self.directory / "other.json")
        self.write_json(self.receipt, self.data)
        self.assert_denied()

    def test_symlinked_authority_directory(self):
        outside = self.root / "outside"
        self.directory.rename(outside)
        self.directory.symlink_to(outside, target_is_directory=True)
        self.assert_denied()

    def test_symlinked_receipt(self):
        saved = self.root / "saved.json"
        self.receipt.rename(saved)
        self.receipt.symlink_to(saved)
        self.assert_denied()

    def test_shell_allowlist_cannot_override_completion_rejection(self):
        invalid = self.command.replace("ctx_test", "ctx_other")
        self.write_json(self.auth, {"policy": "deny_by_default", "authorized_commands": [],
                                   "allowed_shell_commands": [invalid], "authorization_source": ""})
        self.assert_denied(invalid)

    def test_protocol_variants_cannot_fall_through_exact_allowlist(self):
        native = self.command.replace("\\\n", " ").replace("ctx_test", "ctx_wrong")
        variants = [
            native + " 2>/dev/null", native + "; true", "true && " + native,
            native + " | cat", "true\n" + native, "command " + native,
            "env TEST=1 " + native, "exec " + native, "(" + native + ")",
            "2>/dev/null " + native, native.replace("orca ", '"orca" ', 1) + " 2>/dev/null",
            native.replace("orca ", 'o"rc"a ', 1) + "; true",
            native + ' --unknown "unterminated',
            "bash -c " + shlex.quote(native), "eval " + shlex.quote(native),
            "env -S " + shlex.quote(native),
            "echo `" + native + "`", 'echo "$(' + native + ')"',
            native.replace("orca", "or\\\nca", 1),
            native.replace("orchestration", "orches\\\ntration", 1),
            native.replace("orca", '"or\\\nca"', 1),
        ]
        self.env.update(WORKER_COMPLETION_AUTHORITY_FILE="", WORKER_AUTHORITY_RECEIPT_FILE="",
                        WORKER_AUTHORITY_RECEIPT_CONTENT_SHA256="")
        for command in variants:
            with self.subTest(command=command):
                snapshot = {"policy": "deny_by_default", "authorization_source": "",
                            "authorized_commands": [], "allowed_shell_commands": [command]}
                self.env["WORKER_INSTALL_AUTH_B64"] = base64.b64encode(json.dumps(snapshot).encode()).decode()
                self.assert_denied(command)

    def test_install_grant_cannot_override_protocol_authority(self):
        invalid = self.command.replace("ctx_test", "ctx_other") + "; npm install test-package"
        self.write_json(self.auth, {"policy": "deny_by_default", "authorized_commands": [invalid],
                                   "allowed_shell_commands": [], "authorization_source": "test fixture grant"})
        self.assert_denied(invalid)

    def test_ordinary_exact_commands_and_protocol_text_remain_allowed(self):
        commands = [
            "python3 scripts/check_case.py --case focused 2>/dev/null",
            "cd subproject && python3 -m unittest focused_test",
            "printf '%s\\n' 'orca orchestration send --type worker_done'",
            "echo orca orchestration send --type worker_done",
            "printf '%s\\n' '$(orca orchestration send --type worker_done)'",
            "'or\\\nca' orchestration send --type worker_done",
            "or\\\\\nca orchestration send --type worker_done",
            "or\\\n  ca orchestration send --type worker_done",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.write_json(self.auth, {"policy": "deny_by_default", "authorized_commands": [],
                                           "allowed_shell_commands": [command], "authorization_source": ""})
                self.assertEqual(self.hook(command), "")

    def test_arbitrary_executable_named_orca_is_denied(self):
        self.assert_denied(self.command.replace("orca orchestration", "/tmp/untrusted/orca orchestration"))

    def test_group_writable_receipt_is_denied(self):
        self.receipt.chmod(0o660)
        self.assert_denied()

    def test_temp_directory_does_not_allow_receipt_overwrite(self):
        before = self.receipt.read_bytes()
        self.assertIn("SHELL_COMMAND_NOT_ALLOWLISTED", self.hook("echo forged > " + shlex.quote(str(self.receipt))))
        self.assertEqual(self.receipt.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
