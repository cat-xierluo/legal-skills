#!/usr/bin/env python3
"""Offline behavioral checks for focused repository profiles."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import repository_profile as rp  # noqa: E402


def capture(func, args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = func(args)
    return code, json.loads(out.getvalue())


def write_skill(root, name="video-skill", description="代码驱动的视频、字幕、配音与时间轴生成"):
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n# Demo\n", encoding="utf-8")
    return directory


def meta():
    return {"id": 123, "default_branch": "main", "description": "Style toolbox for code-driven short films",
            "topics": ["video", "ffmpeg"], "license": {"spdx_id": "MIT"}, "pushed_at": "2026-10-22T00:00:00Z"}


def branch():
    return {"commit": {"sha": "a" * 40}}


def tree(paths):
    return {"truncated": False, "tree": [{"path": path, "type": "blob"} for path in paths]}


class RepositoryProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.skills = self.root / "skills"
        self.skills.mkdir()
        write_skill(self.skills)
        self.data = self.root / "state"
        self.data.mkdir()

    def args(self, **overrides):
        return SimpleNamespace(**dict(dict(repo="owner/repo", data_dir=self.data,
                                           skills_root=[self.skills], project=None), **overrides))

    def test_profile_build_classifies_runtime_and_matches_local_skill(self):
        paths = ["README.md", "plugin/skills/demo/SKILL.md", "core/renderer.py", "core/audio.py",
                 "styles/demo/style.json", "assets/scene.mp4", "package.json"]
        readme = {"path": "README.md", "sha": "readme-sha", "html_url": "https://example.test/readme",
                  "encoding": "base64", "content": "QSB0aW1lbGluZSwgY2FudmFzLCBGRm1wZWcsIFRUUyBhbmQgc3R5bGUgc3lzdGVt"}
        skill = {"path": "plugin/skills/demo/SKILL.md", "sha": "skill-sha",
                 "encoding": "base64", "content": "LS0tCm5hbWU6IGRlbW8KZGVzY3JpcHRpb246IENvZGUgdmlkZW8gc3R5bGVzCi0tLQ=="}
        dependency = {"path": "package.json", "sha": "dep-sha", "encoding": "base64",
                      "content": "eyJkZXBlbmRlbmNpZXMiOnsibW92aWQiOiIxIn19"}
        with patch.object(rp, "github_get", side_effect=[
                meta(), branch(), tree(paths), readme, skill, dependency]), patch.object(rp, "now_utc", return_value=__import__("datetime").datetime(2026,10,23,tzinfo=__import__("datetime").timezone.utc)):
            profile, warnings = rp.build_profile("owner/repo", self.data, [self.skills])
        self.assertEqual(profile["status"], "complete")
        self.assertEqual(profile["repository_kind_inferred"], "skill-backed runtime/repository")
        self.assertEqual(profile["skill_units"][0]["name"], "demo")
        self.assertIn("ffmpeg-composition", profile["capabilities_inferred"])
        self.assertIn("timeline", profile["capabilities_inferred"])
        self.assertEqual(profile["local_matches"][0]["project_id"], "video-skill")
        self.assertEqual(profile["local_matches"][0]["domain_concepts"], ["timeline", "video", "voice"])
        self.assertEqual(profile["reuse_assessment"]["status"], "needs_review")
        self.assertNotIn("candidate_conclusion_for_lemo_style_repositories", profile["reuse_assessment"])
        self.assertEqual(profile["source_package"]["recommended_strategy"], "bounded source package pinned to commit")
        self.assertIn("package.json", profile["source_package"]["recommended_paths"])
        self.assertIn("plugin/skills/demo", profile["source_package"]["recommended_paths"])
        self.assertEqual(profile["license_assessment"]["license_paths"], [])
        self.assertTrue(rp.cache_path(self.data, "owner/repo").exists())
        self.assertFalse(warnings)

    def test_invalid_repo_rejected_and_api_failure_retains_complete_cache(self):
        with self.assertRaises(ValueError):
            rp.build_profile("bad repo", self.data, [self.skills])
        for name in ("owner/..", "owner/.", "../repo", ".hidden/repo", "owner/.hidden"):
            self.assertFalse(rp.valid_repo(name))
        cached = {"schema_version": "repository-profile/1.0", "repo": "owner/repo",
                  "status": "complete", "profile_revision": "old"}
        rp.atomic_json(rp.cache_path(self.data, "owner/repo"), cached)
        paths = ["README.md"]
        with patch.object(rp, "github_get", side_effect=[meta(), RuntimeError("tree unavailable")]):
            with self.assertRaises(ValueError):
                rp.build_profile("owner/repo", self.data, [self.skills])
        self.assertEqual(rp.read_json(rp.cache_path(self.data, "owner/repo")), cached)

    def test_existing_local_reference_snapshot_supersedes_new_package(self):
        source = self.skills / "video-skill" / "reference-library" / "sources" / "owner--repo"
        source.mkdir(parents=True)
        (source / "README.md").write_text("demo snapshot\n", encoding="utf-8")
        library = self.skills / "video-skill" / "reference-library" / "README.md"
        library.write_text("| [owner/repo](sources/owner--repo/) | `bbbbbbb` | demo |", encoding="utf-8")
        paths = ["README.md", "plugin/skills/demo/SKILL.md", "core/engine.py", "package.json"]
        readme = {"path": "README.md", "sha": "sha", "encoding": "none", "text": "video timeline"}
        skill = {"path": "plugin/skills/demo/SKILL.md", "sha": "skill", "encoding": "none",
                 "text": "---\nname: demo\ndescription: code video styles\n---\n"}
        dependency = {"path": "package.json", "sha": "dep", "encoding": "none", "text": "{}"}
        with patch.object(rp, "github_get", side_effect=[meta(), branch(), tree(paths), readme, skill, dependency]):
            profile, _ = rp.build_profile("owner/repo", self.data, [self.skills])
        self.assertEqual(profile["source_package"]["recommended_strategy"].split(";")[0], "existing-local-snapshot")
        self.assertEqual(profile["local_snapshots"][0]["catalog_commit"], "bbbbbbb")
        self.assertEqual(profile["local_snapshots"][0]["upstream_commit_comparison"], "different-prefix")
        self.assertEqual(profile["source_package"]["recommended_paths"], [])

    def test_profile_refresh_failure_returns_last_complete_cache(self):
        cached = {"schema_version": "repository-profile/1.0", "repo": "owner/repo",
                  "status": "complete", "profile_revision": "old"}
        rp.atomic_json(rp.cache_path(self.data, "owner/repo"), cached)
        args = self.args(repo="owner/repo")
        with patch.object(rp, "build_profile", side_effect=RuntimeError("GitHub unavailable")):
            rc, result = capture(rp.cmd_profile, args)
        self.assertEqual(rc, 2)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["items"], [cached])
        self.assertIn("last complete cache", result["warnings"][0])

    def test_partial_profile_preserved_only_when_no_complete_cache(self):
        paths = ["README.md"]
        readme = {"path": "README.md", "sha": "readme-sha", "encoding": "base64", "content": "UmVhZG1l"}
        with patch.object(rp, "github_get", side_effect=[meta(), RuntimeError("tree unavailable")]):
            with self.assertRaises(ValueError):
                rp.build_profile("owner/repo", self.data, [self.skills])
        # Tree is mandatory, so no profile can be responsibly emitted without it.
        self.assertFalse(rp.cache_path(self.data, "owner/repo").exists())

    def test_tree_truncated_and_limited_skill_fetch_visible(self):
        paths = ["README.md"] + [f"plugin/skills/{i}/SKILL.md" for i in range(5)]
        row = {"sha": "sha", "encoding": "none", "text": "---\nname: demo\ndescription: demo\n---\n"}
        with patch.object(rp, "github_get", side_effect=[meta(), branch(), {"truncated": True, "tree": [
                {"path": path, "type": "blob"} for path in paths]}, row, row] + [row] * 4):
            profile, warnings = rp.build_profile("owner/repo", self.data, [self.skills])
        self.assertEqual(profile["status"], "partial")
        self.assertEqual(len(profile["skill_units"]), 4)
        self.assertTrue(any("Only first 4" in warning for warning in warnings))
        self.assertTrue(any("truncated" in warning for warning in warnings))

    def test_local_scope_exclusions_surface_as_conflicts(self):
        # A static-image skill must be flagged when the upstream offers short films.
        directory = self.skills / "video-skill"
        (directory / "SKILL.md").write_text(
            "---\nname: video-skill\ndescription: 维护角色静帧素材。不承担配音或视频短片生产。\n---\n",
            encoding="utf-8")
        paths = ["README.md", "plugin/skills/demo/SKILL.md", "core/renderer.py", "package.json"]
        readme = {"path": "README.md", "sha": "sha", "encoding": "none",
                  "text": "code driven short film with timeline and subtitles"}
        skill = {"path": "plugin/skills/demo/SKILL.md", "sha": "skill", "encoding": "none",
                 "text": "---\nname: demo\ndescription: short film production\n---\n"}
        dependency = {"path": "package.json", "sha": "dep", "encoding": "none", "text": "{}"}
        with patch.object(rp, "github_get", side_effect=[meta(), branch(), tree(paths), readme, skill, dependency]):
            profile, _ = rp.build_profile("owner/repo", self.data, [self.skills])
        row = profile["local_matches"][0]
        self.assertTrue(row["exclusions"], profile["local_matches"])
        self.assertEqual(row["scope_status"], "conflicts_with_stated_scope")
        self.assertTrue(any("视频" in conflict["exclusion"] for conflict in row["scope_conflicts"]))

    def test_focus_add_list_remove_persists(self):
        args = SimpleNamespace(action="add", repo="owner/repo", reason="video backend",
                               data_dir=self.data)
        _, first = capture(rp.cmd_focus, args)
        self.assertEqual(first["items"][0]["repo"], "owner/repo")
        _, listed = capture(rp.cmd_focus, SimpleNamespace(action="list", repo=None, reason=None, data_dir=self.data))
        self.assertEqual(listed["coverage"]["repositories"], 1)
        _, removed = capture(rp.cmd_focus, SimpleNamespace(action="remove", repo="owner/repo", reason=None, data_dir=self.data))
        self.assertEqual(removed["coverage"]["repositories"], 0)

    def test_non_snapshot_envelope_and_error_envelope_are_explicit(self):
        _, value = capture(rp.cmd_focus, SimpleNamespace(action="list", repo=None, reason=None,
                                                         data_dir=self.data))
        self.assertEqual((value["status"], value["snapshot_completeness"]),
                         ("ok", "not_applicable"))
        _, invalid = capture(rp.cmd_focus, SimpleNamespace(action="add", repo="bad repo",
                                                            reason=None, data_dir=self.data))
        self.assertEqual((invalid["status"], invalid["errors"]), ("partial", ["Invalid owner/repo"]))

    def test_license_files_without_suffix_are_detected(self):
        paths = ["LICENSE", "CREDITS.md", "README.md"]
        facts = rp.classify_tree({"truncated": False, "tree": [
            {"path": path, "type": "blob"} for path in paths]})
        self.assertEqual(facts["licenses"], ["CREDITS.md", "LICENSE"])

    def test_many_license_paths_are_bounded_in_profile(self):
        paths = [f"styles/style{i}/CREDITS" for i in range(25)]
        facts = rp.classify_tree({"truncated": False, "tree": [
            {"path": path, "type": "blob"} for path in paths]})
        meta_value = {**meta(), "default_branch": "main"}
        branch_value = branch()
        readme = {"path": "README.md", "sha": "sha", "encoding": "none", "text": "video"}
        with patch.object(rp, "github_get", side_effect=[meta_value, branch_value,
                {"truncated": False, "tree": [{"path": path, "type": "blob"} for path in paths]},
                readme]):
            profile = rp.build_profile("owner/repo", self.data, [self.skills])[0]
        self.assertEqual(len(profile["license_assessment"]["license_paths"]), 20)
        self.assertTrue(profile["license_assessment"]["license_paths_truncated"])
        self.assertEqual(profile["license_assessment"]["license_path_count"], 25)

    def test_recommended_paths_use_real_tree_paths(self):
        paths = ["LICENSE", "CREDITS.md", "README.md", "plugin/skills/demo/SKILL.md",
                 "core/engine.py", "package.json"]
        facts = rp.classify_tree({"truncated": False, "tree": [
            {"path": path, "type": "blob"} for path in paths]})
        recommended = rp.suggested_sparse_paths(facts)
        self.assertIn("LICENSE", recommended)
        self.assertIn("CREDITS.md", recommended)
        tree_paths = set(paths)
        allowed_prefixes = {path.rsplit("/", 1)[0] for path in paths}
        self.assertTrue(all(path in tree_paths or path in allowed_prefixes
                            for path in recommended))

    def test_source_package_manifest_create_status_and_drift_rejected(self):
        package = self.root / "package"
        manifest = {"schema_version": "source-package/1.0", "repo": "owner/repo",
                    "commit": "a" * 40, "previous_commit": None,
                    "target": str(package), "paths": ["core"], "executed_upstream_code": False}
        rp.atomic_json(rp.manifest_path(self.data, "owner/repo"), manifest)
        package.mkdir()
        def git(command, cwd=None, timeout=120):
            if command[-2:] == ["rev-parse", "HEAD"]:
                return manifest["commit"] if not package_dirty else "b" * 40
            if command[-2] == "status":
                return " M core/file\n" if package_dirty else ""
            if command[1] == "ls-remote":
                return "c" * 40 + "\tHEAD"
            raise AssertionError(command)
        package_dirty = False
        with patch.object(rp, "run_git", side_effect=git):
            _, status = capture(rp.cmd_package_status, self.args())
            self.assertEqual(status["items"][0]["status"], "clean")
            self.assertTrue(status["items"][0]["update_available"])
            package_dirty = True
            _, update = capture(rp.cmd_package_update, self.args())
        self.assertEqual(update["status"], "partial")
        self.assertIn("drifted", update["errors"][0])

    def test_source_package_create_missing_target_is_cli_error(self):
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "repository_profile.py"),
                              "source-package", "create", "owner/repo",
                              "--data-dir", str(self.data)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertIn("--target", json.loads(run.stdout)["errors"][0])

    def test_source_package_size_guard_uses_selected_tree_blobs(self):
        tree = {"truncated": False, "tree": [
            {"path": "core/engine.py", "type": "blob", "size": 20},
            {"path": "styles/full/poster.png", "type": "blob", "size": 100},
            {"path": "styles/full/scene.mp4", "type": "blob", "size": 300},
        ]}
        with patch.object(rp, "github_get", return_value=tree):
            size, count = rp.estimate_package_bytes("owner/repo", "a" * 40, ["core"])
        self.assertEqual((size, count), (20, 1))

    def test_source_package_size_guard_includes_sparse_root_files(self):
        tree_rows = [
            {"path": "README.md", "type": "blob", "size": 50},
            {"path": "big-model.bin", "type": "blob", "size": 200},
            {"path": "core/engine.py", "type": "blob", "size": 20},
            {"path": "styles/full/poster.png", "type": "blob", "size": 300},
        ]
        with patch.object(rp, "github_get", return_value={"truncated": False, "tree": tree_rows}):
            size, count = rp.estimate_package_bytes("owner/repo", "a" * 40, ["core"])
        self.assertEqual((size, count), (270, 3))

    def test_source_package_create_cleans_partial_target_and_rejects_unknown_path(self):
        target = self.root / "failed-package"
        tree_rows = [
            {"path": "README.md", "type": "blob", "size": 10},
            {"path": "core", "type": "tree"},
            {"path": "core/engine.py", "type": "blob", "size": 20},
        ]
        git_calls = []
        def git(command, cwd=None, timeout=120):
            git_calls.append(command)
            if command[1:3] == ["ls-remote", "https://github.com/owner/repo.git"]:
                return "a" * 40 + "\tHEAD"
            if command[1] == "clone":
                target.mkdir()
                (target / ".git").mkdir()
                return ""
            raise AssertionError(command)
        args = self.args(target=target, path=["does-not-exist"], max_bytes=1000)
        with patch.object(rp, "run_git", side_effect=git), \
             patch.object(rp, "github_get", return_value={"truncated": False, "tree": tree_rows}):
            rc, result = capture(rp.cmd_package_create, args)
        self.assertEqual(rc, 1)
        self.assertIn("not found", result["errors"][0])
        self.assertFalse(target.exists())

    def test_source_package_default_rejects_unbounded_style_media_bundle(self):
        target = self.root / "media-bundle"
        args = self.args(target=target, path=["styles"], max_bytes=100)
        tree = {"truncated": False, "tree": [
            {"path": "styles/demo.mp4", "type": "blob", "size": 200}]}
        with patch.object(rp, "run_git", return_value="a" * 40 + "\tHEAD"), \
             patch.object(rp, "github_get", return_value=tree):
            rc, result = capture(rp.cmd_package_create, args)
        self.assertEqual(rc, 1)
        self.assertIn("exceeding", result["errors"][0])
        self.assertFalse(target.exists())

    def test_clone_failure_cleans_partial_target(self):
        target = self.root / "clone-failure"
        tree_rows = [{"path": "README.md", "type": "blob", "size": 10}]
        def git(command, cwd=None, timeout=120):
            if command[1:3] == ["ls-remote", "https://github.com/owner/repo.git"]:
                return "a" * 40 + "\tHEAD"
            if command[1] == "clone":
                target.mkdir()
                (target / ".git").mkdir()
                (target / ".git" / "config").write_text("partial\n")
                raise RuntimeError("git failed (128): clone")
            raise AssertionError(command)
        args = self.args(target=target, path=None, max_bytes=1000)
        with patch.object(rp, "run_git", side_effect=git), \
             patch.object(rp, "github_get", return_value={"truncated": False, "tree": tree_rows}):
            rc, result = capture(rp.cmd_package_create, args)
        self.assertEqual(rc, 1)
        self.assertFalse(target.exists())

    def test_cli_invalid_names_do_not_touch_network(self):
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "repository_profile.py"),
                              "profile", "bad repo", "--data-dir", str(self.data)],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertTrue(json.loads(run.stdout)["errors"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
