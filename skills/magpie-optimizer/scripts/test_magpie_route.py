#!/usr/bin/env python3
"""Offline fault checks; --real-cli adds isolated real Magpie persistence checks."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import magpie_route as m

REAL = "--real-cli" in sys.argv
if REAL:
    sys.argv.remove("--real-cli")


def data():
    return {"providers": [{"id": "example", "models": ["strong", "efficient"], "key": "SECRET_SENTINEL"}], "groups": []}


def policy():
    return {"schema": "magpie-route-policy.v1", "groups": [{"id": "mpr-test", "members": ["example/strong", "example/efficient"],
             "routing": "order", "stays": "auto", "rules": [{"pause": "example/efficient", "time": "14:00-18:00"}]}]}


class Tests(unittest.TestCase):
    def test_allowlist(self):
        d = data()
        d["providers"][0]["accountConcurrency"] = {"PRIVATE_ACCOUNT": 1}
        d["groups"] = [{"id": "x", "rules": [{"use": "example/strong", "folders": ["SECRET_PATH"], "intent": "SECRET_TEXT"}]}]
        s = json.dumps(m.inventory(d))
        for secret in ["SECRET_SENTINEL", "PRIVATE_ACCOUNT", "SECRET_PATH", "SECRET_TEXT"]:
            self.assertNotIn(secret, s)

    def test_collision(self):
        d = data()
        d["groups"] = [{"id": "mpr-test", "members": ["example/strong"]}]
        with self.assertRaisesRegex(m.Refused, "collision"):
            m.validate(policy(), d)

    def test_disabled_provider(self):
        d = data()
        d["providers"][0]["off"] = True
        with self.assertRaises(m.Refused):
            m.validate(policy(), d)

    def test_rule_escape_and_bad_time(self):
        for rule in [{"pause": "example/efficient", "time": "24:00-26:00"},
                     {"use": "unknown/model", "time": "14:00-18:00"},
                     {"use": "example/strong", "shell": "anything"},
                     {"use": "example/strong", "pause": "example/efficient", "time": "14:00-18:00"}]:
            with self.subTest(rule=rule):
                p = policy()
                p["groups"][0]["rules"] = [rule]
                with self.assertRaises(m.Refused):
                    m.validate(p, data())

    def test_fake_success_rejected(self):
        with self.assertRaisesRegex(m.Refused, "readback"):
            m.verify_state(data(), data(), policy()["groups"])

    def test_unrelated_mutation(self):
        after = data()
        after["providers"][0]["key"] = "CHANGED"
        with self.assertRaisesRegex(m.Refused, "unrelated"):
            m.verify_state(data(), after, [])

    def test_extra_classifier_is_not_ignored(self):
        desired = dict(policy()["groups"][0], rules=[])
        for field, value in [("classifier", "paid/router"), ("levels", ["max"]), ("off", [])]:
            after = data()
            after["groups"] = [dict(desired, **{field: value})]
            with self.subTest(field=field), self.assertRaisesRegex(m.Refused, "unexpected_created"):
                m.verify_state(data(), after, [desired])

    def test_drift_and_expiry(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "providers.json"
            f.write_text(json.dumps(data()))
            with patch.object(m, "cli", return_value="magpie fixture"):
                plan = m.make_plan(policy(), f)
                old = copy.deepcopy(plan)
                old["created_epoch"] -= 901
                with self.assertRaisesRegex(m.Refused, "expired"):
                    m.apply(old, f)
                f.write_text(json.dumps(dict(data(), noAutoGroups=True)))
                with self.assertRaisesRegex(m.Refused, "drift"):
                    m.apply(plan, f)

    def test_private_exclusive_output(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "out.json"
            m.save_new(p, {"x": 1})
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                m.save_new(p, {"x": 2})
            self.assertEqual(m.load(p), {"x": 1})

    def test_drift_during_version_check(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "providers.json"
            f.write_text(json.dumps(data()))
            with patch.object(m, "cli", return_value="magpie fixture"):
                plan = m.make_plan(policy(), f)
            def changed(_):
                f.write_text(json.dumps(dict(data(), noAutoGroups=True)))
                return "magpie fixture"
            with patch.object(m, "cli", side_effect=changed):
                with self.assertRaisesRegex(m.Refused, "drift"):
                    m.apply(plan, f)

    @unittest.skipUnless(REAL, "explicit --real-cli required")
    def test_real_cli(self):
        original = m.config_path()
        original_hash = m.sha(original) if original.exists() else None
        with tempfile.TemporaryDirectory(prefix="magpie-route-test-") as td:
            root = Path(td)
            env = {"HOME": td, "USERPROFILE": td, "XDG_CONFIG_HOME": str(root / ".config"),
                   "XDG_CACHE_HOME": str(root / ".cache"), "MAGPIE_NO_ACCOUNTS": "1", "MAGPIE_ADDR": "127.0.0.1:39425"}
            with patch.dict(os.environ, env):
                m.cli(["provider", "add", "example", "url=http://127.0.0.1:9/v1", "models=strong,efficient"])
                f = m.config_path()
                self.assertTrue(str(f).startswith(td))
                before = m.load(f)
                pp, planpath, receipt = root / "policy.json", root / "plan.json", root / "receipt.json"
                m.save_new(pp, policy())
                script = str(Path(m.__file__))
                def run(*args):
                    result = subprocess.run([sys.executable, script, *args], capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                run("plan", "--policy", str(pp), "--output", str(planpath))
                run("apply", "--plan", str(planpath), "--plan-sha256", m.sha(planpath), "--execute", "--receipt", str(receipt))
                result = m.load(receipt)
                self.assertEqual(result["status"], "CONFIG_READBACK_VERIFIED")
                m.verify_state(before, m.load(f), policy()["groups"])
                with self.assertRaisesRegex(m.Refused, "collision"):
                    m.make_plan(policy(), f)
                # Native edit contract and global queue persistence.
                m.cli(["provider", "queue", "example", "2", "15"])
                s = m.cli(["provider", "queue", "example"])
                self.assertIn("2", s)
                self.assertIn("15", s)
        if original_hash is not None:
            self.assertEqual(m.sha(original), original_hash)


if __name__ == "__main__":
    if "--fault-probe" in sys.argv:
        # Directly exercise a rejected input for the external evidence gate.
        bad = policy()
        bad["groups"][0]["members"] = ["unavailable/model"]
        try:
            m.validate(bad, data())
        except m.Refused:
            print("REJECTED_UNKNOWN_MODEL")
            sys.exit(2)
        print("FAULT_ESCAPED")
        sys.exit(0)
    unittest.main(verbosity=2)
