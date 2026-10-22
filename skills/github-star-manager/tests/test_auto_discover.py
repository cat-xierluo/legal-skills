#!/usr/bin/env python3
"""Offline behavioral checks for the scheduled discovery path."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import auto_discover as ad
import project_context as pc
import star_query as sq

NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def write_skill(root, name, description="视频字幕渲染与时间轴", tasks=None):
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n# Demo\n", encoding="utf-8")
    if tasks:
        (directory / "TASKS.md").write_text(tasks, encoding="utf-8")
    return directory


def repo(name="sample/subtitle", push="2026-10-21T00:00:00Z"):
    return {"id": 1, "full_name": name, "description": "Subtitle timeline renderer",
            "starred_at": "2026-10-20T00:00:00Z", "pushed_at": push, "topics": ["video"]}


def snapshot(rows):
    return {"schema_version": 2, "timestamp": NOW.isoformat(), "repos": rows,
            "snapshot_meta": {"account_id": "sample", "complete": True,
                              "fetched_at": NOW.isoformat()}}


def capture(func, args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = func(args)
    return code, json.loads(out.getvalue())


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.skills = self.root / "skills"
        self.skills.mkdir()
        self.directory = write_skill(self.skills, "sample-video")
        self.data = self.root / "data"
        self.data.mkdir()

    def profiles(self):
        return pc.discover([self.skills])[0]

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                               "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout

    def args(self, **overrides):
        return SimpleNamespace(**dict(dict(project=None, skills_root=[self.skills], repo_root=None,
            data_dir=self.data, refresh=False, fetch_evidence=False, evidence_limit=2,
            limit=12, per_project=2, recent_days=14, update_days=7, write=False,
            show_suppressed=False), **overrides))

    def test_installed_links_deduplicate_without_recursing_archive(self):
        installed = self.root / "installed"
        installed.mkdir()
        (installed / "linked").symlink_to(self.directory, target_is_directory=True)
        write_skill(self.skills / "archive", "false-copy")
        profiles, warnings = pc.discover([self.skills, installed])
        self.assertEqual([p["project_id"] for p in profiles], ["sample-video"])
        self.assertFalse(warnings)

    def test_multiline_frontmatter_and_invalid_document_visible(self):
        result = pc.frontmatter("---\nname: example\ndescription: >-\n  video\n  subtitles\n---\n")
        self.assertEqual(result["description"], "video subtitles")
        bad = self.skills / "broken"
        bad.mkdir()
        (bad / "SKILL.md").write_text("# missing metadata")
        profiles, warnings = pc.discover([self.skills])
        self.assertEqual(len(profiles), 1)
        self.assertIn("Cannot read skill broken", warnings[0])

    def test_current_tasks_only_and_hash_refresh(self):
        tasks = self.directory / "TASKS.md"
        tasks.write_text("## 当前\n- 目标：完善口型\n## 历史\n- 目标：删除字幕\n", encoding="utf-8")
        first = self.profiles()[0]
        self.assertEqual(first["needs"], ["- 目标：完善口型"])
        tasks.write_text("## 当前\n- 目标：新增剪辑\n", encoding="utf-8")
        self.assertNotEqual(first["target_revision"], self.profiles()[0]["target_revision"])

    def test_git_activity_is_path_scoped(self):
        self.git("init", "-q")
        self.git("add", "skills")
        self.git("commit", "-qm", "video baseline")
        first = self.profiles()[0]
        write_skill(self.skills, "unrelated", "合同检索")
        self.git("add", "skills/unrelated")
        self.git("commit", "-qm", "other skill")
        second = next(p for p in self.profiles() if p["name"] == "sample-video")
        self.assertEqual(first["activity"]["commits"], 1)
        self.assertEqual(first["activity"], second["activity"])
        self.assertEqual(first["target_revision"], second["target_revision"])

    def test_git_root_skill_implementation_commit_changes_target(self):
        standalone = self.root / "standalone-skill"
        skill = write_skill(standalone.parent, standalone.name)
        self.assertIsNotNone(skill)
        implement = standalone / "engine.py"
        implement.write_text("VALUE = 1\n", encoding="utf-8")
        command = ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                   "-C", str(standalone)]
        subprocess.run([*command, "init", "-q"], check=True)
        subprocess.run([*command, "add", "."], check=True)
        subprocess.run([*command, "commit", "-qm", "initial engine"], check=True)
        first = pc.discover([standalone])[0][0]
        self.assertEqual(first["activity"]["commits"], 1)
        self.assertTrue(first["activity"]["latest_commit"])
        self.assertEqual(first["activity"]["scope"], ".")
        implement.write_text("VALUE = 2\n", encoding="utf-8")
        subprocess.run([*command, "add", "engine.py"], check=True)
        subprocess.run([*command, "commit", "-qm", "update engine"], check=True)
        second = pc.discover([standalone])[0][0]
        self.assertEqual(second["activity"]["commits"], 2)
        self.assertNotEqual(first["target_revision"], second["target_revision"])

    def test_chinese_targets_recall_english_and_exclude_unrelated_recent_star(self):
        profiles = self.profiles()
        unrelated = {**repo("food/recipes"), "description": "recipe manager", "topics": ["food"]}
        selected, _, _ = ad.prepare(snapshot([repo(), unrelated]), profiles, {}, NOW)
        self.assertEqual([c["repo"] for c in selected], ["sample/subtitle"])
        self.assertIn("subtitle", selected[0]["matched_terms"])

    def test_exclusions_do_not_become_positive_project_needs(self):
        (self.directory / "SKILL.md").write_text(
            "---\nname: pictures\ndescription: 维护角色静帧素材。不承担配音或口型动画。\n---\n",
            encoding="utf-8")
        profile = self.profiles()[0]
        self.assertNotIn("voice", profile["primary_terms"])
        self.assertNotIn("lipsync", profile["primary_terms"])

    def test_unknown_and_future_star_are_not_recent_interest(self):
        for starred in (None, "nonsense", "2099-01-01T00:00:00Z"):
            selected, _, _ = ad.prepare(snapshot([{**repo(), "starred_at": starred}]), self.profiles(), {}, NOW)
            self.assertNotIn("recent_star", selected[0]["signals"])
            self.assertIn("upstream_activity", selected[0]["signals"])

    def test_feedback_uses_revisions_not_30day_activity(self):
        profile = self.profiles()[0]
        profile["activity"] = {"commits": 999, "latest_at": NOW.isoformat()}
        card = {"target": {"project_id": profile["project_id"], "target_revision": profile["target_revision"]},
                "signal": {"repo": repo()["full_name"], "repo_revision": ad.repo_revision(repo())},
                "decision": {"status": "rejected"}, "_recorded_at": NOW.isoformat()}
        feedback = {(profile["project_id"], repo()["full_name"]): [card]}
        selected, suppressed, _ = ad.prepare(snapshot([repo()]), [profile], feedback, NOW)
        self.assertFalse(selected)
        self.assertEqual(len(suppressed), 1)
        changed = {**profile, "target_revision": "changed"}
        self.assertTrue(ad.prepare(snapshot([repo()]), [changed], feedback, NOW)[0])
        self.assertTrue(ad.prepare(snapshot([repo(push="2026-10-22T01:00:00Z")]), [profile], feedback, NOW)[0])

    def test_latest_feedback_wins_and_deferred_due_reopens(self):
        profile = self.profiles()[0]
        older = {"decision": {"status": "rejected"}, "_recorded_at": "2026-10-01T00:00:00Z"}
        newer = {"decision": {"status": "deferred", "review_after": NOW.isoformat()},
                 "_recorded_at": "2026-10-21T00:00:00Z"}
        self.assertIsNone(ad.suppression(profile, repo(), [newer, older], NOW))

    def test_deferred_without_date_retries_after_one_day(self):
        profile = self.profiles()[0]
        card = {"target": {"project_id": profile["project_id"],
                           "target_revision": profile["target_revision"]},
                "signal": {"repo": repo()["full_name"], "repo_revision": ad.repo_revision(repo())},
                "decision": {"status": "deferred", "reason": "source temporarily unavailable"},
                "_recorded_at": (NOW - timedelta(hours=23)).isoformat()}
        state = ad.suppression(profile, repo(), [card], NOW)
        self.assertEqual(state["decision"], "deferred")
        self.assertEqual(ad.parse_dt(state["review_after"]), NOW + timedelta(hours=1))
        self.assertIsNone(ad.suppression(profile, repo(), [card], NOW + timedelta(hours=1)))

    def test_offline_no_write_and_explicit_run_package(self):
        ad.atomic_json(self.data / "original_latest.json", snapshot([repo()]))
        before = list(self.data.iterdir())
        with patch.object(ad, "github_get", side_effect=AssertionError("offline called network")):
            rc, result = capture(ad.cmd_auto, self.args())
        self.assertEqual(rc, 0)
        self.assertEqual(list(self.data.iterdir()), before)
        self.assertIsNone(result["run_path"])
        rc, result = capture(ad.cmd_auto, self.args(write=True))
        saved = ad.read_json(Path(result["run_path"]))
        self.assertEqual(result["items"], saved["items"])
        self.assertTrue(saved["projects"][0]["hashes"])

    def test_coverage_reports_before_truncation_and_partial(self):
        rows = [{**repo(f"sample/subtitle{i}"), "id": i} for i in range(5)]
        ad.atomic_json(self.data / "original_latest.json", {**snapshot(rows), "snapshot_meta": {"complete": False}})
        rc, result = capture(ad.cmd_auto, self.args(limit=1))
        self.assertEqual(result["coverage"]["eligible"], 5)
        self.assertEqual(result["coverage"]["returned"], 1)
        self.assertTrue(result["coverage"]["truncated"])
        self.assertEqual(result["status"], "partial")

    def test_missing_snapshot_and_targets_fail(self):
        rc, result = capture(ad.cmd_auto, self.args())
        self.assertEqual(rc, 1)
        ad.atomic_json(self.data / "original_latest.json", snapshot([]))
        rc, result = capture(ad.cmd_auto, self.args(project="absent"))
        self.assertEqual(rc, 1)

    def test_full_refresh_real_writer_and_failure_retains_baseline(self):
        responses = [{"login": "sample"}, [[{"starred_at": repo()["starred_at"], "repo": repo()}]]]
        with patch.object(ad, "github_get", side_effect=responses):
            saved = ad.refresh_snapshot(self.data, None)
        self.assertEqual(saved["repos"][0]["id"], 1)
        original = (self.data / "original_latest.json").read_bytes()
        with patch.object(ad, "github_get", side_effect=[{"login": "sample"}, RuntimeError("page failure")]):
            with self.assertRaises(RuntimeError):
                ad.refresh_snapshot(self.data, saved)
        self.assertEqual(original, (self.data / "original_latest.json").read_bytes())
        with patch.object(ad, "github_get", return_value={"login": "other"}):
            with self.assertRaises(ValueError):
                ad.refresh_snapshot(self.data, saved)

    def test_evidence_contains_release_change_and_partial_does_not_overwrite(self):
        candidate = {"repo": "sample/subtitle", "repo_id": 1, "repo_revision": "rev2"}
        readme = {"content": "ZGVtbyByZWFkbWU=", "sha": "abc", "html_url": "https://github.com/sample/subtitle"}
        release = [{"tag_name": "v2", "body": "Adds word level timestamps", "html_url": "https://github.com/sample/subtitle/releases/tag/v2"}]
        commits = [{"sha": "def", "commit": {"message": "Add word timing"}}]
        prior = {"head_sha": "old", "release": {"tag": "v1"}}
        with patch.object(ad, "github_get", side_effect=[readme, release, commits]):
            evidence = ad.fetch_evidence(candidate, self.data, prior)
        self.assertEqual(evidence["release"]["body"], "Adds word level timestamps")
        self.assertTrue(evidence["change_summary"]["head_changed"])
        path = self.data / "auto-opportunities/evidence/sample__subtitle.json"
        original = path.read_bytes()
        with patch.object(ad, "github_get", side_effect=RuntimeError("offline")):
            failure = ad.fetch_evidence(candidate, self.data, evidence)
        self.assertEqual(failure["status"], "partial")
        self.assertEqual(original, path.read_bytes())

    def test_cached_evidence_with_metadata_unchanged_survives_next_offline_run(self):
        profile = self.profiles()[0]
        row = repo()
        cached = {"repo": row["full_name"], "repo_id": row["id"],
                  "repo_revision": ad.repo_revision(row), "status": "complete",
                  "head_sha": "head", "release": None,
                  "readme": {"blob_sha": "readme"}, "fetched_at": NOW.isoformat(),
                  "changed_at": "2026-10-01T00:00:00Z"}
        ad.atomic_json(ad.evidence_cache(self.data, row["full_name"]), cached)
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        rc, result = capture(ad.cmd_auto, self.args())
        self.assertEqual(rc, 0)
        self.assertEqual(result["items"][0]["evidence_status"], "cached")
        self.assertEqual(result["items"][0]["evidence_revision"],
                         ad.evidence_revision(cached))

    def test_release_only_change_probed_before_unchanged_feedback_is_suppressed(self):
        row = repo()
        profile = self.profiles()[0]
        release_v1 = {"tag": "v1", "body": "old", "url": "https://example.test/v1",
                      "published_at": "2026-10-01T00:00:00Z"}
        cached_v1 = {"head_sha": "head", "release": release_v1,
                     "readme": {"blob_sha": "readme-stable"},
                     "status": "complete", "changed_at": (NOW - timedelta(days=2)).isoformat()}
        ad.atomic_json(ad.evidence_cache(self.data, row["full_name"]), cached_v1)
        card = {"target": {"project_id": profile["project_id"],
                           "target_revision": profile["target_revision"]},
                "signal": {"repo": row["full_name"], "repo_id": row["id"],
                           "repo_revision": ad.repo_revision(row),
                           "evidence_revision": ad.evidence_revision(cached_v1)},
                "decision": {"status": "experiment_proposed"},
                "_recorded_at": (NOW - timedelta(days=1)).isoformat()}
        feedback = {(profile["project_id"], row["full_name"]): [card]}
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        readme = {"content": "ZGVtbyByZWFkbWU=", "sha": "readme-stable",
                  "html_url": "https://github.com/sample/subtitle"}
        releases = [
            [{"tag_name": "v1", "body": "old", "html_url": "https://example.test/v1",
              "published_at": "2026-10-01T00:00:00Z"}],
            [{"tag_name": "v2", "body": "new word timings", "html_url": "https://example.test/v2",
              "published_at": "2026-10-22T00:00:00Z"}],
        ]
        commits = [[{"sha": "head", "html_url": "https://example.test/commit",
                     "commit": {"message": "stable title"}}]]
        with patch.object(ad, "feedback_index", return_value=(feedback, [])), \
             patch.object(ad, "now_utc", side_effect=[NOW] * 20), \
             patch.object(ad, "github_get", side_effect=[readme, releases[0], commits[0],
                                                         readme, releases[1], commits[0]]):
            first_rc, first = capture(ad.cmd_auto, self.args(fetch_evidence=True))
            second_rc, second = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        self.assertEqual((first_rc, second_rc), (0, 0))
        self.assertEqual(first["items"], [])
        self.assertEqual(first["coverage"]["suppressed"], 1)
        self.assertEqual(len(second["items"]), 1)
        self.assertEqual(second["items"][0]["repo_id"], row["id"])
        _, third = capture(ad.cmd_auto, self.args(fetch_evidence=False))
        self.assertEqual(len(third["items"]), 1,
                         "an evidence change not yet recorded in feedback must survive the next run")

    def test_research_finds_dynamic_target_without_registration(self):
        with patch.object(pc, "default_roots", return_value=[self.skills]):
            profile = sq._load_project_profile("sample-video")
        self.assertEqual(profile["origin"], "dynamic-skill-scan/2")
        self.assertTrue(profile["source_ref"])
        self.assertIn("subtitle", profile["search_terms"])

    def test_cli_error_exit_is_not_hidden_by_json_pipeline(self):
        run = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
            "auto-discover", "--data-dir", str(self.data), "--skills-root", str(self.skills)],
            capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertTrue(json.loads(run.stdout)["errors"])
        invalid = subprocess.run([sys.executable, "-B", str(SCRIPTS / "auto_discover.py"),
            "auto-discover", "--limit", "0"], capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
