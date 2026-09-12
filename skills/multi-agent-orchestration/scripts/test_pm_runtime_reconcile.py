"""真实 PM 入口复算本地证据，不要求 Session、不调用 Orca。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent


class PMRuntimeReconcileTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pm reconcile ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.sentinel = self.root / "unexpected-rpc"
        fake = self.root / "orca-fake"
        fake.write_text('#!/bin/sh\ntouch "$(dirname "$0")/unexpected-rpc"\nexit 97\n')
        fake.chmod(0o700)
        self.env = dict(os.environ, ORCA_CLI_COMMAND=str(fake), ORCA_TERMINAL_HANDLE="term-unrelated")
        binding = json.loads((SCRIPTS.parent / "templates/runtime-settlement-binding.example.json").read_text())
        raw = json.dumps(binding).encode()
        (self.root / "binding.json").write_bytes(raw)
        request = {"schema_version": "multi-agent-orchestration.runtime-observe-request.v1",
                   "observer_runtime_id": binding["runtime"]["observer_runtime_id"],
                   "binding": {"path": "binding.json", "sha256": hashlib.sha256(raw).hexdigest()},
                   "commands": {}, "lease_record": None, "lease_release": None}
        (self.root / "request.json").write_text(json.dumps(request))
        result = subprocess.run([sys.executable, str(SCRIPTS / "runtime-reconcile.py"), "observe",
                                 "--request", str(self.root / "request.json"), "--output", str(self.root / "snapshot.json")],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def call(self, *args):
        result = subprocess.run(["bash", str(SCRIPTS / "pm-orchestrate.sh"), *args], env=self.env,
                                cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertFalse(self.sentinel.exists(), "reconcile 不应发送 RPC")
        self.assertFalse((self.root / ".claude").exists(), "reconcile 不应创建 Session")
        return result

    def test_unsettled_is_valid_evidence_but_not_completion_and_is_idempotent(self):
        args = ["reconcile", "--snapshot", str(self.root / "snapshot.json"), "--output", str(self.root / "receipt.json"), "--from", "term-closed"]
        first = self.call(*args)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        result = json.loads(first.stdout)
        self.assertTrue(result["ok"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["settlement_state"], "UNSETTLED")
        self.assertTrue(result["missing_evidence"])
        self.assertFalse(result["lifecycle_mutations"])
        saved = (self.root / "receipt.json").read_bytes()
        repeat = self.call(*args)
        self.assertEqual(repeat.returncode, 0, repeat.stdout + repeat.stderr)
        self.assertEqual(json.loads(repeat.stdout)["action"], "UNCHANGED")
        self.assertEqual((self.root / "receipt.json").read_bytes(), saved)

    def test_missing_arguments_and_mutation_flags_are_rejected_without_rpc(self):
        for extra in ([], ["--snapshot"], ["--snapshot", str(self.root / "snapshot.json")],
                      ["--snapshot", str(self.root / "snapshot.json"), "--output", str(self.root / "r.json"), "--force"],
                      ["--snapshot", str(self.root / "snapshot.json"), "--output", str(self.root / "r.json"), "--destroy"]):
            with self.subTest(extra=extra):
                self.assertNotEqual(self.call("reconcile", *extra).returncode, 0)
        self.assertFalse((self.root / "r.json").exists())

    def test_drifted_capture_is_rejected_and_previous_receipt_preserved(self):
        args = ["reconcile", "--snapshot", str(self.root / "snapshot.json"), "--output", str(self.root / "receipt.json")]
        self.assertEqual(self.call(*args).returncode, 0)
        before = (self.root / "receipt.json").read_bytes()
        (self.root / "binding.json").write_text("{}\n")
        result = self.call(*args)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse(json.loads(result.stdout)["complete"])
        self.assertEqual((self.root / "receipt.json").read_bytes(), before)

    def test_snapshot_flags_cannot_route_another_command(self):
        result = self.call("release", "--snapshot", str(self.root / "snapshot.json"), "--output", str(self.root / "r.json"))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "r.json").exists())


if __name__ == "__main__":
    unittest.main()
