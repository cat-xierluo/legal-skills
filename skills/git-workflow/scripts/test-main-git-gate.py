#!/usr/bin/env python3
"""Real Git regression for command-entry protection, in disposable fixtures."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

GATE = Path(__file__).with_name("main-git-gate.py")
GIT = shutil.which("git")


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="main-git-gate-test-")
        self.base = Path(self.tmp.name)
        self.root = self.base / "primary"
        self.root.mkdir()
        self.raw("init", "-b", "main")
        self.raw("config", "user.name", "guard-fixture")
        self.raw("config", "user.email", "guard-fixture@example.invalid")
        (self.root / "skill").mkdir()
        self.file = self.root / "skill" / "a.txt"
        self.file.write_text("main content\n")
        self.raw("add", "skill/a.txt")
        self.raw("commit", "-m", "initial")
        self.raw("switch", "-c", "other")
        self.file.write_text("different branch content\n")
        self.raw("commit", "-am", "other")
        self.raw("switch", "main")

    def tearDown(self):
        self.tmp.cleanup()

    def raw(self, *args, cwd=None):
        r = subprocess.run([GIT, *args], cwd=cwd or self.root,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def run_gate(self, *args, cwd=None, env=None, integration=False, expected=None):
        options = ["--integration-owner", "fixture-owner", "--expected-head",
                   expected or self.raw("rev-parse", "HEAD")] if integration else []
        return subprocess.run([sys.executable, str(GATE), "--repo", str(self.root),
                               "--git", GIT, *options, "--", *args], cwd=cwd or self.root,
                              capture_output=True, text=True, env=env)

    def snapshot(self):
        paths = [self.file, self.root / ".git/HEAD", self.root / ".git/index",
                 self.root / ".git/refs/heads/main"]
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

    def deny_unchanged(self, *args, **kwargs):
        before = self.snapshot()
        r = self.run_gate(*args, **kwargs)
        self.assertEqual(r.returncode, 73, r.stderr)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.raw("branch", "--show-current"), "main")

    def test_named_integration_add_commit_and_read(self):
        old = self.raw("rev-parse", "HEAD")
        self.file.write_text("normal Skill edit\n")
        for args in [("add", "skill/a.txt"), ("commit", "-m", "normal"),
                     ("status", "--short"), ("diff",), ("log", "-1", "--oneline")]:
            r = self.run_gate(*args, integration=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotEqual(old, self.raw("rev-parse", "HEAD"))
        self.assertEqual(self.file.read_text(), "normal Skill edit\n")
        self.assertFalse((self.root / ".git/index.lock").exists())

    def test_main_development_denied_by_default(self):
        self.file.write_text("unrelated unfinished edit\n")
        for args in [("add", "skill/a.txt"), ("commit", "-am", "worker"),
                     ("restore", "--staged", "skill/a.txt")]:
            self.deny_unchanged(*args)

    def test_named_integration_head_drift_and_switch_denied(self):
        self.deny_unchanged("add", "skill/a.txt", integration=True,
                            expected="0" * 40)
        self.deny_unchanged("switch", "other", integration=True)
        self.deny_unchanged("reset", "--hard", "other", integration=True)

    def test_check_only_does_not_stage(self):
        self.file.write_text("candidate\n")
        before = self.snapshot()
        args = [sys.executable, str(GATE), "--repo", str(self.root), "--git", GIT,
                "--integration-owner", "fixture-owner", "--expected-head",
                self.raw("rev-parse", "HEAD"), "--check-only", "--", "add", "skill/a.txt"]
        result = subprocess.run(args, cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_switch_checkout_and_file_restore_before_any_change(self):
        for args in [("switch", "other"), ("switch", "--detach", "HEAD"),
                     ("checkout", "other"), ("checkout", "other", "--", "skill"),
                     ("restore", "--source=other", "skill/a.txt"),
                     ("restore", "skill/a.txt"), ("checkout-index", "-af")]:
            with self.subTest(args=args):
                self.deny_unchanged(*args)

    def test_history_bulk_overwrite_and_alias_rejected(self):
        for args in [("reset", "--hard", "other"), ("merge", "other"),
                     ("pull",), ("rebase", "other"), ("clean", "-fd"),
                     ("stash",), ("read-tree", "-u", "other"),
                     ("update-ref", "refs/heads/main", "other"),
                     ("symbolic-ref", "HEAD", "refs/heads/other"),
                     ("commit", "--amend", "-m", "rewrite"), ("co", "other"),
                     ("branch", "-m", "main", "new")]:
            with self.subTest(args=args):
                self.deny_unchanged(*args)

    def test_C_routing_repeated_and_config_bypass(self):
        self.deny_unchanged("-C", str(self.root), "switch", "other", cwd=self.base)
        self.deny_unchanged("-C", str(self.root / "skill"), "-C", "..", "switch", "other")
        self.deny_unchanged("-c", "alias.s=!git switch other", "s")
        self.deny_unchanged("--work-tree=" + str(self.root), "switch", "other")
        self.deny_unchanged("--git-dir=" + str(self.root / ".git"), "switch", "other")

    def test_environment_routing_bypass(self):
        for key, value in {"GIT_INDEX_FILE": str(self.root / ".git/index"),
                           "GIT_DIR": str(self.root / ".git"),
                           "GIT_CONFIG_COUNT": "1"}.items():
            env = dict(os.environ, **{key: value})
            self.deny_unchanged("status", env=env)

    def test_unstage_without_file_overwrite(self):
        self.file.write_text("keep working file\n")
        self.raw("add", "skill/a.txt")
        r = self.run_gate("restore", "--staged", "skill/a.txt", integration=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.file.read_text(), "keep working file\n")
        self.deny_unchanged("restore", "--staged", "--worktree", "skill/a.txt")

    def test_integration_rejects_commit_option_variants_before_change(self):
        self.file.write_text("preserve unfinished edit\n")
        for option in ("--amend", "--amen", "--am", "--no-no-amend",
                       "--no-verify", "-n"):
            with self.subTest(option=option):
                self.deny_unchanged("commit", option, "-m", "rewrite", integration=True)

    def test_integration_rejects_restore_option_variants_before_change(self):
        self.file.write_text("preserve unfinished edit\n")
        self.raw("add", "skill/a.txt")
        for option in ("--worktree", "--work", "-W", "-SW", "-WS", "-Wq",
                       "-sother", "--source=other", "--sour=other", "--no-staged"):
            with self.subTest(option=option):
                self.deny_unchanged("restore", "--staged", option,
                                    "skill/a.txt", integration=True)

    def test_commit_messages_and_pathspecs_are_not_options(self):
        for options in (("-am", "--amend"), ("--message=--amend", "--all"),
                        ("-qm--amend", "--all")):
            self.file.write_text(repr(options) + "\n")
            result = self.run_gate("commit", *options, integration=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        odd = self.root / "--worktree"
        odd.write_text("keep\n")
        self.raw("add", "--", odd.name)
        result = self.run_gate("restore", "-S", "--", odd.name, integration=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(odd.read_text(), "keep\n")

    def test_reflog_output_cannot_overwrite_files(self):
        self.file.write_text("preserve unfinished edit\n")
        for args in (("reflog", "show", "--output=skill/a.txt"),
                     ("reflog", "show", "--output", "skill/a.txt")):
            self.deny_unchanged(*args)
        result = self.run_gate("reflog", "show", "-1")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_non_main_identity_fails_closed(self):
        self.raw("switch", "other")
        before = self.snapshot()
        r = self.run_gate("add", "skill/a.txt")
        self.assertEqual(r.returncode, 73)
        self.assertEqual(before, self.snapshot())

    def test_sparse_worktree_remains_usable(self):
        wt = self.base / "worker"
        self.raw("worktree", "add", "--no-checkout", "-b", "worker", str(wt))
        self.raw("sparse-checkout", "set", "--cone", "skill", cwd=wt)
        self.raw("checkout", cwd=wt)
        (wt / "skill/a.txt").write_text("worker edit\n")
        for args in [("add", "skill/a.txt"), ("commit", "-m", "worker"),
                     ("switch", "--detach", "HEAD")]:
            r = self.run_gate(*args, cwd=wt)
            self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.file.read_text(), "main content\n")

    def test_readonly_options_and_identity_config(self):
        for args in [("branch", "--show-current"), ("config", "--get", "user.name"),
                     ("-c", "user.name=guard-fixture", "status", "--short")]:
            self.assertEqual(self.run_gate(*args).returncode, 0)
        self.deny_unchanged("log", "--output=skill/a.txt")
        self.deny_unchanged("config", "core.hooksPath", "/tmp")


if __name__ == "__main__":
    if not GIT:
        print("缺少 Git；请安装系统 Git 后运行", file=sys.stderr)
        sys.exit(2)
    unittest.main()
