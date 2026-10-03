#!/usr/bin/env python3
"""Isolated actual Git/process consumers of engineering evidence and old gates."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
ADAPTER = ROOT / "verification-evidence.py"

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.repo = self.root / "repo"; self.repo.mkdir()
        self.env = dict(os.environ, GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                        GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
        self.git("init", "-q")
        (self.repo / "app.py").write_text("VALUE = 1\n")
        (self.repo / "verify.py").write_text("from app import VALUE\nassert VALUE == 2\nprint('verified fixture')\n")
        (self.repo / "fail.py").write_text("print('actual failure')\nraise SystemExit(7)\n")
        (self.repo / "slow.py").write_text("import time\ntime.sleep(5)\n")
        (self.repo / "large.py").write_text("print('x' * 300000)\n")
        self.git("add", "."); self.git("commit", "-q", "-m", "base"); self.base = self.git("rev-parse", "HEAD")
        (self.repo / "app.py").write_text("VALUE = 2\n")
        self.git("add", "app.py"); self.git("commit", "-q", "-m", "fix")
        self.head = self.git("rev-parse", "HEAD")
        self.spec = self.root / "dispatch.json"; self.output = self.root / "evidence"
        self.task = {"task_id":"TASK-ENGINEERING", "status":"READY", "kind":"bugfix", "value_kind":"implementation",
                     "value_identity":"actual-fixture-value", "problem_target":"app.py value fix", "consumer":"fixture integration",
                     "decision_or_gate_changed":"new app value accepted", "engineering_assets":["app.py", "verify.py"],
                     "doc_assets":[], "verification_commands":["python3 -B verify.py"], "worker_pr_policy":"worker_pr",
                     "consume_by":"this integration wave", "expiry":"archive after integration", "observable_acceptance":"real verification passes",
                     "starts_external_resources":False, "resource_owner":"none", "state_transition":""}
        self.save_spec()
    def git(self, *args):
        p = subprocess.run(["git", "-C", str(self.repo), *args], env=self.env, capture_output=True, text=True, check=True)
        return p.stdout.strip()
    def save_spec(self):
        self.spec.write_text(json.dumps({"schema_version":"dispatch-value-gate.v2", "mode":"converge", "pending_acceptance_prs":0, "tasks":[self.task]}))
    def cli(self, action, *extra):
        args = [sys.executable, "-B", str(ADAPTER), action, "--spec", str(self.spec), "--task-id", self.task["task_id"], "--repo", str(self.repo), "--head", self.head]
        args += ["--output-dir", str(self.output)] if action == "collect" else ["--evidence", str(self.output / "postflight-evidence.json")]
        return subprocess.run(args + list(extra), env=self.env, capture_output=True, text=True, timeout=15)
    def collect_ok(self):
        p = self.cli("collect"); self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        out = json.loads(p.stdout); self.assertTrue(out["usable_for_postflight"]); self.assertFalse(out["task_complete"])
        self.assertNotIn("verified fixture", p.stdout)
        return json.loads((self.output / "postflight-evidence.json").read_text())
    def test_actual_success_check_and_unchanged_postflight(self):
        evidence = self.collect_ok()
        self.assertEqual(evidence["verified_head"], self.head); self.assertEqual(evidence["executed"][0]["exit_code"], 0)
        self.assertEqual((self.output / "00.stdout.log").read_text(), "verified fixture\n")
        self.assertEqual(self.cli("check").returncode, 0)
        p = subprocess.run([sys.executable,"-B",str(ROOT / "worker-value-postflight.py"),"--spec",str(self.spec),"--task-id",self.task["task_id"],"--repo",str(self.repo),"--base",self.base,"--head",self.head,"--evidence",str(self.output / "postflight-evidence.json")],capture_output=True,text=True,timeout=15)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr); self.assertTrue(json.loads(p.stdout)["ok"])
    def test_failed_command_preserves_actual_exit_and_first_logs(self):
        self.task["verification_commands"] = ["python3 -B fail.py"]; self.save_spec()
        p = self.cli("collect"); self.assertEqual(p.returncode, 2)
        attempt = json.loads((self.output / "attempt.json").read_text()); self.assertEqual(attempt["executed"][0]["exit_code"], 7)
        self.assertFalse((self.output / "postflight-evidence.json").exists())
        before = (self.output / "attempt.json").read_bytes()
        self.assertEqual(self.cli("collect").returncode, 2); self.assertEqual(before,(self.output / "attempt.json").read_bytes())
        self.assertEqual(self.cli("check").returncode, 2)
    def test_old_head_and_later_source_commit_invalidate(self):
        self.collect_ok(); (self.repo / "app.py").write_text("VALUE = 3\n"); self.git("add","app.py");self.git("commit","-q","-m","later")
        self.assertEqual(self.cli("check").returncode,2)
        self.output = self.root / "old-evidence";self.assertEqual(self.cli("collect").returncode,2);self.assertFalse(self.output.exists())
    def test_dirty_untracked_ignored_and_hidden_source_refused(self):
        for kind in ("tracked", "untracked", "ignored", "assume-unchanged"):
            with self.subTest(kind=kind):
                if kind in ("tracked","assume-unchanged"):
                    if kind == "assume-unchanged":self.git("update-index","--assume-unchanged","app.py")
                    (self.repo / "app.py").write_text("VALUE = 9\n")
                elif kind == "untracked":(self.repo / "new.py").write_text("value=9\n")
                else:
                    (self.repo / ".git/info/exclude").write_text("secret-source.py\n")
                    (self.repo / "secret-source.py").write_text("value=9\n")
                self.assertEqual(self.cli("collect").returncode,2);self.assertFalse(self.output.exists())
                if kind in ("tracked","assume-unchanged"):
                    self.git("update-index","--no-assume-unchanged","app.py");(self.repo / "app.py").write_text("VALUE = 2\n")
                else:(self.repo / ("new.py" if kind == "untracked" else "secret-source.py")).unlink()
    def test_log_and_whole_spec_changes_invalidate(self):
        self.collect_ok(); p = self.output / "00.stdout.log"; old = p.read_bytes(); p.write_bytes(old + b"changed\n")
        self.assertEqual(self.cli("check").returncode,2);p.write_bytes(old)
        data = json.loads(self.spec.read_text()); data["source_note"] = "changed outside selected task"
        self.spec.write_text(json.dumps(data)); self.assertEqual(self.cli("check").returncode,2)
    def test_complex_shell_and_inline_wrappers_refused_before_execution(self):
        for command in ("python3 -B verify.py; true", "python3 -B verify.py | cat", "MODE=any python3 -B verify.py", "env python3 -B verify.py", "bash -c true", "bash -lc true", "python3 -c 'print(1)'", "python3 -B $(echo verify.py)"):
            with self.subTest(command=command):
                self.task["verification_commands"]=[command];self.save_spec();self.assertEqual(self.cli("collect").returncode,2);self.assertFalse(self.output.exists())
    def test_timeout_and_output_overflow_never_usable(self):
        for name, args, reason in (("slow",["--timeout-seconds","0.1"],"timeout"),("large",["--max-log-bytes","1024"],"log_limit")):
            with self.subTest(name=name):
                self.output=self.root/name;self.task["verification_commands"]=[f"python3 -B {name}.py"];self.save_spec()
                self.assertEqual(self.cli("collect",*args).returncode,2)
                attempt=json.loads((self.output/"attempt.json").read_text());row=attempt["executed"][0]
                self.assertFalse(row["complete"]);self.assertEqual(row["failure"],reason);self.assertFalse((self.output/"postflight-evidence.json").exists())
                self.assertLessEqual(sum(p.stat().st_size for p in self.output.glob("*.log")),1024 if name=="large" else 128*1024)
    def test_output_inside_checkout_and_unsupported_value_refused(self):
        self.output=self.repo/"ignored-evidence";self.assertEqual(self.cli("collect").returncode,2);self.assertFalse(self.output.exists())
        self.output=self.root/"evidence";self.task["value_kind"]="merge_gate";self.save_spec();self.assertEqual(self.cli("collect").returncode,2)
    def test_source_mutation_during_actual_command_invalidates(self):
        (self.repo / "mutate.py").write_text("from pathlib import Path\nPath('app.py').write_text('VALUE = 9\\n')\n")
        self.git("add","mutate.py");self.git("commit","-q","-m","mutation fixture");self.head=self.git("rev-parse","HEAD")
        self.task["verification_commands"]=["python3 -B mutate.py"];self.save_spec()
        self.assertEqual(self.cli("collect").returncode,2);attempt=json.loads((self.output/"attempt.json").read_text())
        self.assertEqual(attempt["executed"][0]["exit_code"],0);self.assertEqual(attempt["failure"],"binding_changed");self.assertFalse((self.output/"postflight-evidence.json").exists())

if __name__ == "__main__": unittest.main()
