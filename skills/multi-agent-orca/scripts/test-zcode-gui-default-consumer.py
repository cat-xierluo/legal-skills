#!/usr/bin/env python3
"""Exercise the installed sibling dependency path with synthetic SQLite data."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent
FLAGS = {"pmAccepted": False, "orcaSupervised": False, "livenessAuthoritative": False}


class DefaultConsumer(unittest.TestCase):
    def observe(self, case, wrong_input=False):
        env = dict(os.environ)
        for name in ("ZCODE_GUI_COLLECTOR", "ZCODE_GUI_ADAPTER"):
            env.pop(name, None)
        with tempfile.TemporaryDirectory(prefix="gui-default-consumer-") as tmp:
            db = Path(tmp) / "synthetic.sqlite"
            fixture = subprocess.run(
                [sys.executable, str(SCRIPTS / "zcode-gui-pipeline-fixtures.py"),
                 "--case", case, "--out", str(db)],
                env=env, capture_output=True, timeout=10, check=True,
            )
            binding = json.loads(fixture.stdout)
            before = hashlib.sha256(db.read_bytes()).hexdigest()
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "zcode-gui-observe.py"),
                 "--db", str(db), "--session-id", binding["sessionId"],
                 "--input-id", "absent-input" if wrong_input else binding["inputId"]],
                env=env, capture_output=True, timeout=10,
            )
            self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before)
            self.assertEqual(len(result.stdout.splitlines()), 1)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["flags"], FLAGS)
            for canary in (b"CANARY-", str(db).encode()):
                self.assertNotIn(canary, result.stdout + result.stderr)
            return result.returncode, payload

    def test_completed_ready_without_dependency_env_or_flags(self):
        code, payload = self.observe("completed_ready_for_review")
        self.assertEqual(code, 0)
        self.assertEqual(payload["state"], "READY_FOR_PM_REVIEW")

    def test_latest_error_without_dependency_env_or_flags(self):
        code, payload = self.observe("completed_latest_error_wins")
        self.assertEqual(code, 0)
        self.assertEqual(payload["state"], "DELIVERY_ERROR")

    def test_wrong_binding_without_dependency_env_or_flags(self):
        code, payload = self.observe("completed_ready_for_review", wrong_input=True)
        self.assertEqual(code, 1)
        self.assertIsNone(payload["state"])
        self.assertEqual(payload["error"], {"code": "INPUT_NOT_FOUND"})


if __name__ == "__main__":
    unittest.main()
