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
import project_context as pc  # noqa: E402


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
                meta(), branch(), tree(paths), readme, skill, dependency, []]), patch.object(rp, "now_utc", return_value=__import__("datetime").datetime(2026,10,23,tzinfo=__import__("datetime").timezone.utc)):
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
        with patch.object(rp, "github_get", side_effect=[meta(), branch(), tree(paths), readme, skill, dependency, []]):
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
                {"path": path, "type": "blob"} for path in paths]}, row] + [row] * 4 + [[]]):
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
        with patch.object(rp, "github_get", side_effect=[meta(), branch(), tree(paths), readme, skill, dependency, []]):
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

    def test_profile_and_daily_bind_same_release_content_revision(self):
        readme = {"path": "README.md", "sha": "readme-sha",
                  "encoding": "none", "text": "video timeline"}
        release = [{"tag_name": "v2", "body": "New caption feature",
                    "published_at": "2026-10-23T00:00:00Z", "html_url": "https://example.test/v2"}]
        with patch.object(rp, "github_get", side_effect=[
                meta(), branch(), tree(["README.md"]), readme, release]):
            profile, _ = rp.build_profile("owner/repo", self.data, [self.skills])
        import auto_discover as ad
        daily = {"head_sha": branch()["commit"]["sha"], "readme": {"blob_sha": "readme-sha"},
                 "release": ad.release_record(release)}
        self.assertEqual(profile["evidence_revision"], ad.evidence_revision(daily))
        self.assertTrue(profile["evidence_revision_complete"])
        self.assertEqual(profile["repo_revision"], ad.repo_revision(meta()))

    def test_scope_warning_uses_actual_upstream_and_same_commit_is_current(self):
        directory = self.skills / "video-skill"
        (directory / "SKILL.md").write_text(
            "---\nname: video-skill\ndescription: 视频制作。不要用于法律检索。\n---\n", encoding="utf-8")
        matches, _ = rp.local_matches("owner/repo", "video timeline", [], [self.skills])
        self.assertEqual(matches[0]["scope_conflicts"], [])
        self.assertEqual(rp.compare_snapshot_commit("a" * 40, "a" * 40), "same")

    def test_reference_manifest_precedes_catalog_without_git_metadata(self):
        library = self.skills / "video-skill" / "reference-library"
        (library / "sources" / "owner--repo").mkdir(parents=True)
        (library / "manifests").mkdir()
        (library / "README.md").write_text("| [source](sources/owner--repo/) | `bbbbbbb` |\n")
        manifest = library / "manifests" / "owner--repo.json"
        manifest.write_text(json.dumps({"repo": "owner/repo", "commit": "a" * 40}))
        rows = rp.local_reference_snapshots("owner/repo", [self.skills])
        self.assertEqual(rows[0]["commit"], "a" * 40)
        self.assertEqual(rows[0]["manifest_path"], str(manifest))
        self.assertEqual(rows[0]["manifest_status"], "read")
        self.assertIsNone(rows[0]["git_commit"])

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
                readme, []]):
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


class ScopeExclusionTests(unittest.TestCase):
    """A scope conflict must follow the component's own exclusion sentence.

    The historical extractor cut the text at the exclusion marker and kept
    the whole remainder, so a React UI library looked like a conflict with
    the publishing skill because the rest of that skill's own documentation
    mentioned "video" and "cover".
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.skills = self.root / "skills"
        self.skills.mkdir()

    def skill(self, name, description, tasks=None):
        directory = self.skills / name
        directory.mkdir()
        (directory / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n# Demo\n", encoding="utf-8")
        if tasks is not None:
            (directory / "TASKS.md").write_text(tasks, encoding="utf-8")
        return directory

    def profile(self, name, description, tasks=None):
        self.skill(name, description, tasks)
        profiles, _ = rp.discover([self.skills])
        return next(p for p in profiles if p["project_id"] == name)

    def test_exclusion_clause_does_not_swallow_the_whole_document(self):
        profile = self.profile(
            "douyin-video-publish",
            "将律师 IP 成片与封面通过抖音创作者中心上传，填写标题与话题标签。"
            "不用于剪辑、生图、代写未经核验的法律结论或账号复盘。")
        for clause in profile["exclusion_clauses"]:
            self.assertLess(len(clause), 200, clause)
        self.assertTrue(any("剪辑" in clause for clause in profile["exclusion_clauses"]))

    def test_react_ui_upstream_is_not_a_conflict_with_the_publishing_skill(self):
        # R7: an unrelated React/view/component repository must not be
        # reported as conflicting with douyin-video-publish.
        profile = self.profile(
            "douyin-video-publish",
            "将律师 IP 成片与封面通过抖音创作者中心上传。"
            "不用于剪辑、生图、代写未经核验的法律结论或账号复盘。")
        upstream = pc.terms_for(
            "react component library view ui browser render cover layout subtitle")
        conflicts = pc.scope_conflicts(profile, upstream)
        self.assertEqual(conflicts, [], conflicts)
        self.assertEqual(pc.scope_status(profile, conflicts), "no_stated_scope_conflict")

    def test_real_exclusion_still_creates_a_conflict(self):
        # The functionality must not be blinded: a real exclusion sentence
        # still triggers the conflict.
        profile = self.profile(
            "video-skill",
            "维护角色静帧素材。不承担配音或视频短片生产。")
        upstream = pc.terms_for("short film production voice audio video")
        conflicts = pc.scope_conflicts(profile, upstream)
        self.assertTrue(conflicts, "The real exclusion no longer triggers")
        self.assertTrue(any("视频" in row["exclusion"] for row in conflicts))
        self.assertEqual(pc.scope_status(profile, conflicts), "conflicts_with_stated_scope")

    def test_task_marker_does_not_swallow_the_following_task_lines(self):
        # A marker inside a task line must not turn the rest of the task
        # excerpt into one long exclusion fragment.
        profile = self.profile(
            "motion-animator",
            "Motion Composer 的既有 HTML/CSS 录制兼容入口。",
            tasks=('## 当前\n'
                   '- [ ] 音频对齐能力评估：当前明确"不用于需要音频同步的复杂后期"，'
                   '但口播稿配套动画与口播音频的对齐是高频需求，需评估是否纳入或明确交接给 '
                   '`video-creator`\n'
                   '- [ ] 字幕 / 标题动画预设库，把常见动效沉淀为可复用片段\n'
                   '- [ ] 三种模式在 1920x1080 下的渲染质量回归\n'))
        for clause in profile["exclusion_clauses"]:
            self.assertLess(len(clause), 120, clause)
        self.assertTrue(any("音频同步" in clause for clause in profile["exclusion_clauses"]))
        self.assertFalse(any("字幕" in clause for clause in profile["exclusion_clauses"]))

    def test_component_without_a_readable_exclusion_is_reported_as_unparsed(self):
        # Silence must not be read as "no conflict": the status distinguishes
        # the unparsed case and says a human has to confirm.
        profile = self.profile("code-livephoto",
                               "调用 code-video 的导演方法，制作动态卡片与 Live Photo。")
        self.assertEqual(profile["exclusion_clauses"], [])
        conflicts = pc.scope_conflicts(profile, pc.terms_for("video animation render"))
        self.assertEqual(conflicts, [])
        self.assertEqual(pc.scope_status(profile, conflicts), "stated_scope_unparsed")
        note = pc.scope_note(profile)
        self.assertTrue(note and "人工确认" in note)

    def test_explicit_scope_limit_is_read_as_a_stated_boundary(self):
        profile = self.profile(
            "code-livephoto",
            "调用 code-video 的导演方法。本 Skill 只维护卡片场景的适配。")
        self.assertTrue(any("只维护" in clause for clause in profile["exclusion_clauses"]))

    def test_component_can_declare_its_exclusions_explicitly(self):
        directory = self.skill("declared-skill", "生成视频成片。")
        (directory / "scope.json").write_text(
            json.dumps({"exclusions": ["不承担配音", "不用于字幕翻译"]}), encoding="utf-8")
        profiles, _ = rp.discover([self.skills])
        profile = next(p for p in profiles if p["project_id"] == "declared-skill")
        self.assertEqual(profile["exclusion_source"], "declared")
        self.assertIn("不承担配音", profile["exclusion_clauses"])
        upstream = pc.terms_for("voice dubbing subtitle translation video")
        conflicts = pc.scope_conflicts(profile, upstream)
        self.assertTrue(conflicts, "The declared exclusions must still create a conflict")

    def test_tasks_file_can_declare_its_exclusions_explicitly(self):
        directory = self.skill("declared-tasks-skill", "生成视频成片。")
        (directory / "TASKS.md").write_text(
            "## 当前\ndeclared_exclusions:\n- 不承担配音\n- 不用于字幕翻译\n",
            encoding="utf-8")
        profiles, _ = rp.discover([self.skills])
        profile = next(p for p in profiles if p["project_id"] == "declared-tasks-skill")
        self.assertEqual(profile["exclusion_source"], "declared")
        self.assertIn("不承担配音", profile["exclusion_clauses"])

    def test_profile_output_exposes_the_judgement_basis(self):
        # The Agent has to see the sentence the judgement is based on.
        directory = self.skill("video-static-skill",
                               "维护角色静帧素材。不承担配音或视频短片生产。")
        matches, _ = rp.local_matches("owner/repo", "voice short film video",
                                      [], [self.skills])
        row = matches[0]
        self.assertTrue(row["exclusion_clauses"])
        self.assertTrue(row["scope_conflicts"])
        self.assertEqual(row["scope_status"], "conflicts_with_stated_scope")
        self.assertTrue(any("视频短片生产" in clause for clause in row["exclusion_clauses"]))

    def test_dai_ti_marker_is_read_as_an_exclusion(self):
        # "不代替" states the same boundary as "不用于" and must be readable,
        # otherwise a real exclusion looks like an unparsable scope.
        profile = self.profile(
            "legal-ai-hot",
            "监测行业更新并交付候选素材。用于找近期选题；不代替法律检索、原文核验或写稿发布。")
        self.assertTrue(any("法律检索" in clause for clause in profile["exclusion_clauses"]))
        self.assertNotEqual(pc.scope_status(profile, []), "stated_scope_unparsed")

    def test_routing_statement_is_not_an_exclusion(self):
        # "完整视频走 code-video" is routing, not a statement of negative
        # scope. It must not become an exclusion clause.
        profile = self.profile(
            "ascii-art-generator",
            "Code Slides 的字符视觉层。完整卡片、视频、课件与 Live Photo 配对仍由对应制作 Skill 负责。")
        self.assertEqual(profile["exclusion_clauses"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
