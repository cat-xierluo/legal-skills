#!/usr/bin/env python3
"""Snapshot/recovery evidence tests; only disposable real Git repositories."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("main-directory-snapshot.py")
SPEC = importlib.util.spec_from_file_location("main_snapshot", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ENV = dict(os.environ, GIT_AUTHOR_NAME="snapshot-fixture", GIT_COMMITTER_NAME="snapshot-fixture",
           GIT_AUTHOR_EMAIL="snapshot@example.invalid", GIT_COMMITTER_EMAIL="snapshot@example.invalid",
           GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_OPTIONAL_LOCKS="0")
for key in MODULE.ROUTING:
    ENV.pop(key, None)


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="main-snapshot-")
        self.base = Path(self.tmp.name)
        self.repo = self.base / "primary"
        self.repo.mkdir()
        self.raw("init", "-b", "main")
        (self.repo / "tracked.txt").write_text("committed\n")
        (self.repo / "deleted.txt").write_text("keep deletion\n")
        (self.repo / ".gitignore").write_text("ignored/\n")
        self.raw("add", "--", "tracked.txt", "deleted.txt", ".gitignore")
        self.raw("commit", "-m", "initial")
        self.safety = self.base / "safety"

    def tearDown(self):
        self.tmp.cleanup()

    def raw(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], env=ENV)

    def run_snapshot(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo),
                               "--safety-root", str(self.safety), *extra], env=ENV,
                              capture_output=True, text=True)

    def create(self, *extra):
        result = self.run_snapshot(*extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["status"], "PASS")
        return Path(data["snapshot_dir"])

    def verify(self, out):
        ledger = self.safety / self.repo.name / "MANIFESTS.jsonl"
        return subprocess.run([sys.executable, str(SCRIPT), "--verify", str(out),
                               "--ledger", str(ledger)],
                              capture_output=True, text=True, env=ENV)

    def test_working_text_links_deleted_and_nonascii_odd_paths(self):
        (self.repo / "tracked.txt").write_text("unstaged\n")
        (self.repo / "deleted.txt").unlink()
        names = ['模型 空格.md', 'a"b\\c\n.md']
        for name in names:
            (self.repo / name).write_text(name)
        os.symlink("missing-target", self.repo / "dangling")
        out = self.create()
        states = json.loads((out / "states.json").read_bytes())
        self.assertEqual(states["deleted.txt"]["kind"], "absent")
        self.assertEqual(os.readlink(out / "working-tree/dangling"), "missing-target")
        for name in names:
            self.assertEqual((out / "working-tree" / name).read_text(), name)
        self.assertEqual(self.verify(out).returncode, 0)

    def test_staged_added_renamed_and_unstaged_versions_are_preserved(self):
        (self.repo / "tracked.txt").write_text("staged\n")
        (self.repo / "added.txt").write_text("added version\n")
        self.raw("add", "--", "tracked.txt", "added.txt")
        (self.repo / "tracked.txt").write_text("later unstaged\n")
        self.raw("mv", "deleted.txt", "renamed.txt")
        out = self.create()
        stages = json.loads((out / "staged-objects.json").read_bytes())
        stage = next(e for e in stages if e["path"] == "tracked.txt")
        self.assertEqual((out / stage["file"]).read_text(), "staged\n")
        self.assertEqual((out / "working-tree/tracked.txt").read_text(), "later unstaged\n")
        self.assertIn("added.txt", {e["path"] for e in stages})
        states = json.loads((out / "states.json").read_bytes())
        self.assertEqual(states["deleted.txt"]["kind"], "absent")
        self.assertEqual(states["renamed.txt"]["kind"], "file")

    def test_no_repository_write_and_late_mutation_cannot_change_snapshot(self):
        (self.repo / "tracked.txt").write_text("before\n")
        before = MODULE.capture_git(self.repo)
        out = self.create()
        self.assertEqual(MODULE.capture_git(self.repo), before)
        (self.repo / "tracked.txt").write_text("after\n")
        self.assertEqual((out / "working-tree/tracked.txt").read_text(), "before\n")
        self.assertEqual(self.verify(out).returncode, 0)

    def test_unmerged_index_all_three_stages(self):
        self.raw("switch", "-c", "side")
        (self.repo / "tracked.txt").write_text("side\n")
        self.raw("commit", "-am", "side")
        self.raw("switch", "main")
        (self.repo / "tracked.txt").write_text("main\n")
        self.raw("commit", "-am", "main")
        r = subprocess.run(["git", "-C", str(self.repo), "merge", "side"], env=ENV,
                           capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        out = self.create()
        entries = json.loads((out / "staged-objects.json").read_bytes())
        self.assertEqual({e["stage"] for e in entries}, {"1", "2", "3"})
        self.assertEqual(self.verify(out).returncode, 0)

    def test_deleted_tracked_replaced_by_directory_copies_children(self):
        path = self.repo / "tracked.txt"
        path.unlink()
        path.mkdir()
        (path / "child.txt").write_text("local content\n")
        out = self.create()
        self.assertEqual((out / "working-tree/tracked.txt/child.txt").read_text(), "local content\n")

    def test_symlink_to_external_directory_is_not_followed(self):
        external = self.base / "external"
        external.mkdir()
        (external / "secret.txt").write_text("outside\n")
        os.symlink(str(external), self.repo / "external-link")
        out = self.create()
        states = json.loads((out / "states.json").read_bytes())
        self.assertEqual(states["external-link"]["kind"], "symlink")
        self.assertNotIn("external-link/secret.txt", states)
        self.assertEqual((external / "secret.txt").read_text(), "outside\n")

    def test_ignored_is_an_explicit_choice_and_same_label_never_overwrites(self):
        ignored = self.repo / "ignored"
        ignored.mkdir()
        (ignored / "local.bin").write_bytes(b"ignored bytes")
        a = self.create()
        b = self.create("--include-ignored")
        self.assertNotEqual(a, b)
        self.assertFalse(json.loads((a / "snapshot.json").read_bytes())["include_ignored"])
        self.assertTrue((b / "working-tree/ignored/local.bin").is_file())
        self.assertFalse((a / "working-tree/ignored/local.bin").exists())

    def test_tampered_working_bytes_index_and_metadata_fail_verification(self):
        (self.repo / "tracked.txt").write_text("unfinished\n")
        for target in ("working-tree/tracked.txt", "index.bin", "states.json"):
            with self.subTest(target=target):
                out = self.create()
                (out / target).write_bytes(b"changed")
                self.assertNotEqual(self.verify(out).returncode, 0)

    def test_same_status_source_drift_or_copy_failure_never_passes(self):
        (self.repo / "tracked.txt").write_text("unfinished\n")
        original = MODULE.shutil.copy2

        def drift(src, dst, **kwargs):
            result = original(src, dst, **kwargs)
            if Path(src).name == "tracked.txt":
                Path(src).write_text("changed during copy\n")
            return result

        with patch.dict(os.environ, ENV, clear=True), patch.object(MODULE.shutil, "copy2", side_effect=drift):
            with self.assertRaisesRegex(ValueError, "drift"):
                MODULE.snapshot(self.repo, self.safety, "drift")
        markers = list(self.safety.rglob("INCOMPLETE.json"))
        self.assertEqual(len(markers), 1)
        with patch.dict(os.environ, ENV, clear=True), patch.object(MODULE.shutil, "copy2", side_effect=OSError("copy failed")):
            with self.assertRaises(OSError):
                MODULE.snapshot(self.repo, self.safety, "failure")
        self.assertEqual(len(list(self.safety.rglob("INCOMPLETE.json"))), 2)

    def test_inside_repo_output_and_invalid_label_fail_before_creation(self):
        r = self.run_snapshot("--safety-root", str(self.repo / "backup"))
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.repo / "backup").exists())
        r = self.run_snapshot("--label", "../escape")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.safety.exists())

    def test_dirty_submodule_is_recorded_not_silently_dropped(self):
        sub = self.base / "sub"
        sub.mkdir()
        subprocess.run(["git", "-C", str(sub), "init", "-q", "-b", "main"], env=ENV, check=True)
        (sub / "f.txt").write_text("sub base\n")
        subprocess.run(["git", "-C", str(sub), "add", "-A"], env=ENV, check=True, capture_output=True)
        subprocess.run(["git", "-C", str(sub), "commit", "-qm", "sub"], env=ENV, check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "sub"], env=ENV, check=True, capture_output=True)
        (sub / "f.txt").write_text("sub local edit\n")
        out = self.create()
        skipped = json.loads((out / "skipped.json").read_bytes())
        self.assertEqual({e["path"] for e in skipped}, {"sub"})
        self.assertIn("submodule", skipped[0]["reason"])
        self.assertEqual(self.verify(out).returncode, 0)

    def test_verify_scope_states_it_does_not_prove_preincident_equality(self):
        out = self.create()
        report = json.loads(self.verify(out).stdout)
        self.assertIn("does not prove", report["scope"])

    def test_path_through_symlinked_directory_is_captured_with_chain(self):
        (self.repo / "real").mkdir()
        (self.repo / "real" / "inner.txt").write_text("behind symlink\n")
        self.raw("add", "--", "real/inner.txt")
        self.raw("commit", "-m", "real")
        # Track a path that resolves through the symlinked directory, the shape the
        # private-skills repository actually has.
        blob = subprocess.check_output(["git", "-C", str(self.repo), "hash-object", "-w", "real/inner.txt"], env=ENV, text=True).strip()
        subprocess.run(["git", "-C", str(self.repo), "update-index", "--add", "--cacheinfo", "100644," + blob + ",alias/inner.txt"], env=ENV, check=True, capture_output=True)
        os.symlink("real", self.repo / "alias")
        out = self.create()
        states = json.loads((out / "states.json").read_bytes())
        self.assertIn("alias", states)
        self.assertEqual(states["alias"]["kind"], "symlink")
        # A tracked path that resolves through the symlinked directory keeps its chain.
        chain_states = [v for v in states.values() if v.get("via_symlink")]
        self.assertTrue(chain_states)
        beyond = out / "working-tree-beyond-symlink"
        self.assertTrue(beyond.exists())
        self.assertEqual(self.verify(out).returncode, 0)

    def test_empty_state(self):
        out = self.create()
        self.assertEqual(json.loads((out / "snapshot.json").read_bytes())["entries"], 0)
        self.assertEqual(self.verify(out).returncode, 0)

    def test_parent_or_symlinked_output_cannot_resolve_into_repository(self):
        r = self.run_snapshot("--safety-root", str(self.repo.parent))
        self.assertNotEqual(r.returncode, 0)
        self.safety.mkdir()
        (self.safety / self.repo.name).symlink_to(self.repo, target_is_directory=True)
        r = self.run_snapshot()
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(list(self.repo.glob("*pre-main-adoption*")))

    def test_coordinated_manifest_change_and_dropped_entries_fail_external_anchor(self):
        (self.repo / "tracked.txt").write_text("unique unfinished\n")
        for drop in (False, True):
            out = self.create()
            states = json.loads((out / "states.json").read_bytes())
            if drop:
                del states["tracked.txt"]
            else:
                (out / "working-tree/tracked.txt").write_text("substituted\n")
                states["tracked.txt"] = MODULE.read_state(out / "working-tree/tracked.txt")
            (out / "states.json").write_bytes(MODULE.encode(states))
            meta = json.loads((out / "snapshot.json").read_bytes())
            meta["files"]["states.json"] = MODULE.sha((out / "states.json").read_bytes())
            meta["manifest_digest"] = MODULE.manifest_digest(meta)
            (out / "snapshot.json").write_bytes(MODULE.encode(meta))
            self.assertNotEqual(self.verify(out).returncode, 0)

    def test_missing_ledger_never_verifies_and_size_budget_fails(self):
        out = self.create()
        r = subprocess.run([sys.executable, str(SCRIPT), "--verify", str(out)],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["status"], "NOT_VERIFIED")
        (self.repo / "large.txt").write_bytes(b"x" * 4096)
        r = self.run_snapshot("--max-bytes", "100")
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(list(self.safety.rglob("INCOMPLETE.json")))

    def test_untracked_nested_repository_is_explicitly_skipped(self):
        nested = self.repo / "nested"
        nested.mkdir()
        subprocess.check_call(["git", "-C", str(nested), "init", "-q", "-b", "main"], env=ENV)
        (nested / "unfinished.txt").write_text("other repository\n")
        out = self.create()
        meta = json.loads((out / "snapshot.json").read_bytes())
        self.assertTrue(meta["skipped"])
        self.assertIn("nested", {e["path"] for e in meta["skipped"]})
        self.assertEqual(self.verify(out).returncode, 0)


if __name__ == "__main__":
    unittest.main()
