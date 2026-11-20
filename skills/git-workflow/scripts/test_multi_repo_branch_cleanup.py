#!/usr/bin/env python3
"""Isolated regression for multi-repo exact branch cleanup."""

from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("multi_repo_branch_cleanup.py")
GIT = subprocess.check_output(["which", "git"], text=True).strip()


class MultiRepoBranchCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="multi-repo-cleanup-test-")
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / "repository"
        self.repo.mkdir()
        self.recovery = self.root / "recovery"
        self.environment = dict(
            os.environ,
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_AUTHOR_NAME="Test",
            GIT_AUTHOR_EMAIL="test@example.invalid",
            GIT_COMMITTER_NAME="Test",
            GIT_COMMITTER_EMAIL="test@example.invalid",
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
        return subprocess.run(
            [GIT, "-C", str(self.repo), *args], env=self.environment, text=True,
            capture_output=True, check=True,
        )

    def git_text(self, *args):
        return self.git(*args).stdout.strip()

    def tool(self, *args):
        return subprocess.run(
            ["python3", str(SCRIPT), *args], env=self.environment, text=True,
            capture_output=True, cwd=self.root,
        )

    def manifest(self):
        return {
            "schema_version": 1,
            "repositories": [{
                "name": "fixture",
                "root": str(self.repo),
                "base_ref": "refs/remotes/origin/main",
                "base_oid": self.base,
                "pr_check": "none",
                "branches": [{
                    "branch": "docs/delivered",
                    "tip": self.base,
                    "evidence": {"kind": "ancestor", "baseline_oid": self.base},
                }],
            }],
        }

    def write_manifest(self):
        path = self.root / "candidates.json"
        path.write_text(json.dumps(self.manifest(), ensure_ascii=False, indent=2) + "\n")
        return path

    def approval(self, digest_value, authorization="approved for regression"):
        path = self.root / "approval.json"
        path.write_text(json.dumps({
            "manifest_sha256": digest_value,
            "authorization": authorization,
            "approved_by": "test",
        }, ensure_ascii=False, indent=2) + "\n")
        return path

    def test_prepare_requires_approval_and_deletes_only_after_binding(self):
        manifest = self.write_manifest()
        prepared = self.tool("prepare", str(manifest), str(self.recovery), "--quiet-seconds", "0")
        self.assertEqual(0, prepared.returncode, prepared.stdout + prepared.stderr)
        manifest_digest = digest_value(manifest)
        wrong = self.approval("0" * 64)
        rejected = self.tool("apply", str(self.recovery), "--approval", str(wrong), "--skip-pr-check")
        self.assertEqual(1, rejected.returncode)
        self.assertEqual(self.base, self.git_text("show-ref", "--verify", "--hash", "refs/heads/docs/delivered"))

        approved = self.approval(manifest_digest)
        applied = self.tool("apply", str(self.recovery), "--approval", str(approved), "--skip-pr-check")
        self.assertEqual(0, applied.returncode, applied.stdout + applied.stderr)
        verified = self.tool("verify", str(self.recovery))
        self.assertEqual(0, verified.returncode, verified.stdout + verified.stderr)
        self.assertIn("VERIFIED 1", verified.stdout)
        missing = subprocess.run(
            [GIT, "-C", str(self.repo), "show-ref", "--verify", "--quiet", "refs/heads/docs/delivered"],
            env=self.environment, capture_output=True,
        )
        self.assertEqual(1, missing.returncode)

    def test_tip_drift_after_prepare_is_retained(self):
        manifest = self.write_manifest()
        self.assertEqual(0, self.tool("prepare", str(manifest), str(self.recovery), "--quiet-seconds", "0").returncode)
        (self.repo / "drift.txt").write_text("drift\n")
        self.git("checkout", "docs/delivered")
        self.git("add", "drift.txt")
        self.git("commit", "-m", "drift")
        self.git("checkout", "main")
        approval = self.approval(digest_value(manifest))
        result = self.tool("apply", str(self.recovery), "--approval", str(approval), "--skip-pr-check")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        receipt = json.loads((self.recovery / "result.json").read_text())
        self.assertEqual(0, len(receipt["completed"]))
        self.assertEqual(1, len(receipt["retained"]))
        self.assertNotEqual(self.base, self.git_text("show-ref", "--verify", "--hash", "refs/heads/docs/delivered"))

    def test_incomplete_merged_pr_evidence_is_rejected(self):
        data = self.manifest()
        data["repositories"][0]["pr_check"] = "github"
        data["repositories"][0]["remote_repo"] = "fixture/repository"
        data["repositories"][0]["branches"][0]["evidence"] = {
            "kind": "merged-pr",
            "baseline_oid": self.base,
            "merge_oid": self.base,
        }
        manifest = self.root / "incomplete-merged-pr.json"
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        result = self.tool("prepare", str(manifest), str(self.recovery), "--quiet-seconds", "0", "--skip-pr-check")
        self.assertEqual(1, result.returncode)
        self.assertIn("Incomplete merged PR identity", result.stdout + result.stderr)
        self.assertEqual(self.base, self.git_text("show-ref", "--verify", "--hash", "refs/heads/docs/delivered"))


def digest_value(path: Path):
    import hashlib
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


if __name__ == "__main__":
    unittest.main(verbosity=2)
