#!/usr/bin/env python3
"""Isolated regression for post-cleanup GC and recovery release gates."""

from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("repo_gc_gate.py")
CLEANUP_SCRIPT = Path(__file__).with_name("multi_repo_branch_cleanup.py")
GIT = subprocess.check_output(["which", "git"], text=True).strip()


class RepoGcGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="repo-gc-gate-test-")
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / "repository"
        self.repo.mkdir()
        self.recovery = self.root / "recovery"
        self.environment = dict(
            os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
            GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
            GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid",
            PYTHONDONTWRITEBYTECODE="1",
        )
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_NAMESPACE"):
            self.environment.pop(key, None)
        self.git("init", "-b", "main")
        (self.repo / "file.txt").write_text("base\n")
        self.git("add", "file.txt")
        self.git("commit", "-m", "base")
        self.base = self.git_text("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        self.git("branch", "docs/delivered")

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *args):
        return subprocess.run([GIT, "-C", str(self.repo), *args], env=self.environment, text=True, capture_output=True, check=True)

    def git_text(self, *args):
        return self.git(*args).stdout.strip()

    def tool(self, *args):
        return subprocess.run(["python3", str(SCRIPT), *args], env=self.environment, text=True, capture_output=True, cwd=self.root)

    def cleanup_tool(self, *args):
        return subprocess.run(["python3", str(CLEANUP_SCRIPT), *args], env=self.environment, text=True, capture_output=True, cwd=self.root)

    def json_file(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        return path

    def sha256(self, path):
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()

    def prepare_deleted_branch(self):
        manifest = self.json_file("candidates.json", {
            "schema_version": 1,
            "repositories": [{
                "name": "fixture", "root": str(self.repo),
                "base_ref": "refs/remotes/origin/main", "base_oid": self.base,
                "pr_check": "none",
                "branches": [{
                    "branch": "docs/delivered", "tip": self.base,
                    "evidence": {"kind": "ancestor", "baseline_oid": self.base},
                }],
            }],
        })
        prepared = self.cleanup_tool("prepare", str(manifest), str(self.recovery), "--quiet-seconds", "0")
        self.assertEqual(0, prepared.returncode, prepared.stdout + prepared.stderr)
        approval = self.json_file("cleanup-approval.json", {
            "manifest_sha256": self.sha256(manifest), "authorization": "cleanup fixture",
            "approved_by": "test",
        })
        applied = self.cleanup_tool("apply", str(self.recovery), "--approval", str(approval), "--skip-pr-check")
        self.assertEqual(0, applied.returncode, applied.stdout + applied.stderr)

    def gc_approval(self, baseline, **overrides):
        value = {
            "action": "git-gc", "baseline_sha256": self.sha256(baseline),
            "accepted_fsck_warnings": [], "approved_by": "test",
            "authorization": "GC after verified cleanup",
            "cleanup_recovery_paths": [str(self.recovery.resolve())],
        }
        value.update(overrides)
        return self.json_file("gc-approval.json", value)

    def test_gc_requires_bound_approval_and_preserves_identity(self):
        self.prepare_deleted_branch()
        baseline = self.root / "baseline.json"
        audited = self.tool("audit", str(self.repo), "--output", str(baseline))
        self.assertEqual(0, audited.returncode, audited.stdout + audited.stderr)
        wrong = self.gc_approval(baseline, baseline_sha256="0" * 64)
        rejected = self.tool("gc", str(self.repo), "--baseline", str(baseline), "--approval", str(wrong), "--receipt", str(self.root / "receipt.json"))
        self.assertEqual(1, rejected.returncode)
        self.assertEqual(self.base, self.git_text("rev-parse", "HEAD"))

        approval = self.gc_approval(baseline)
        receipt = self.root / "receipt.json"
        passed = self.tool("gc", str(self.repo), "--baseline", str(baseline), "--approval", str(approval), "--receipt", str(receipt))
        self.assertEqual(0, passed.returncode, passed.stdout + passed.stderr)
        verified = self.tool("verify", str(self.repo), "--baseline", str(baseline), "--receipt", str(receipt))
        self.assertEqual(0, verified.returncode, verified.stdout + verified.stderr)
        self.assertEqual(self.base, self.git_text("rev-parse", "HEAD"))

    def test_gc_rejects_drift_after_baseline(self):
        self.prepare_deleted_branch()
        baseline = self.root / "baseline.json"
        self.assertEqual(0, self.tool("audit", str(self.repo), "--output", str(baseline)).returncode)
        self.git("branch", "docs/new")
        approval = self.gc_approval(baseline)
        result = self.tool("gc", str(self.repo), "--baseline", str(baseline), "--approval", str(approval), "--receipt", str(self.root / "receipt.json"))
        self.assertEqual(1, result.returncode)
        self.assertIn("Baseline drift: refs", result.stderr)
        self.assertEqual(self.base, self.git_text("rev-parse", "HEAD"))

    def test_recovery_release_requires_cleanup_and_gc_confirmation(self):
        self.prepare_deleted_branch()
        baseline = self.root / "baseline.json"
        self.assertEqual(0, self.tool("audit", str(self.repo), "--output", str(baseline)).returncode)
        gc_receipt = self.root / "gc-receipt.json"
        gc = self.tool("gc", str(self.repo), "--baseline", str(baseline), "--approval", str(self.gc_approval(baseline)), "--receipt", str(gc_receipt))
        self.assertEqual(0, gc.returncode, gc.stdout + gc.stderr)

        prepared_digest = self.sha256(self.recovery / "prepared.json")
        wrong = self.json_file("release-approval.json", {
            "action": "release-recovery", "recovery_path": str(self.recovery),
            "prepared_sha256": "0" * 64,
            "approved_by": "test", "authorization": "release",
        })
        rejected = self.tool("release", str(self.recovery), "--approval", str(wrong), "--receipt", str(self.root / "release.json"))
        self.assertEqual(1, rejected.returncode)
        self.assertTrue(self.recovery.exists())

        approval = self.json_file("release-approval.json", {
            "action": "release-recovery", "recovery_path": str(self.recovery.resolve()),
            "prepared_sha256": prepared_digest,
            "gc_receipts": {str(self.repo.resolve()): str(gc_receipt.resolve())},
            "approved_by": "test", "authorization": "release after verified GC",
        })
        receipt = self.root / "release.json"
        released = self.tool("release", str(self.recovery), "--approval", str(approval), "--receipt", str(receipt))
        self.assertEqual(0, released.returncode, released.stdout + released.stderr)
        self.assertFalse(self.recovery.exists())
        self.assertEqual(1, json.loads(receipt.read_text())["operation_count"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
