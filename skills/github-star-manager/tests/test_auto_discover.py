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
            show_suppressed=False, focus_limit=8, request_budget=60,
            cheap_budget=0), **overrides))

    def focus(self, names):
        ad.atomic_json(self.data / ad.FOCUS_FILE, {"repositories": {
            name: {"repo": name, "reason": "watched"} for name in names}})

    def github_evidence(self, endpoint, **kwargs):
        if "/readme" in endpoint:
            return {"content": "ZGVtbyByZWFkbWU=", "sha": "readme-stable"}
        if "/releases?" in endpoint:
            return []
        if "/commits?" in endpoint:
            return [{"sha": "head", "commit": {"message": "Stable title"}}]
        raise AssertionError(endpoint)

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

    def test_implementation_excerpt_adds_real_capability_and_respects_exclusions(self):
        (self.directory / "scripts").mkdir()
        (self.directory / "scripts" / "engine.py").write_text(
            "def transition_timeline(): pass\n", encoding="utf-8")
        static = write_skill(self.skills, "static-ip", "维护角色静帧素材。不承担配音或口型动画。")
        (static / "engine.py").write_text(
            "def render_static_avatar(): pass\n", encoding="utf-8")
        profiles = {p["project_id"]: p for p in self.profiles()}
        self.assertIn("transition", profiles["sample-video"]["search_terms"])
        self.assertTrue(profiles["sample-video"]["implementation_excerpt_refs"])
        self.assertIn("avatar", profiles["static-ip"]["search_terms"])
        for term in ("voice", "tts", "配音", "lipsync", "口型"):
            self.assertNotIn(term, profiles["static-ip"]["search_terms"])

    def test_exclusion_uses_word_boundaries_and_positive_claim_wins(self):
        boundary = write_skill(self.skills, "legal-search",
                               "法律检索。不要用于 academic research 场景。")
        positive = write_skill(self.skills, "voice-clips",
                               "负责配音的短视频工具。不承担长篇配音课程。")
        profiles = {p["project_id"]: p for p in self.profiles()}
        for term in ("search", "检索", "retrieval"):
            self.assertIn(term, profiles["legal-search"]["search_terms"])
        for term in ("voice", "tts", "配音", "语音合成"):
            self.assertIn(term, profiles["voice-clips"]["search_terms"])
        self.assertNotIn("cad", profiles["legal-search"]["search_terms"])
        self.assertTrue(boundary.is_dir() and positive.is_dir())

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
        feedback = {(profile["project_id"], repo()["full_name"], "legacy", None): [card]}
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
        responses = [{"login": "sample"}, [{"starred_at": repo()["starred_at"], "repo": repo()}]]
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
        feedback = {(profile["project_id"], row["full_name"], "legacy", None): [card]}
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

    def test_focus_repositories_are_checked_without_keyword_overlap(self):
        # A watched repository whose description shares no concept with the local
        # skill must still be reported, otherwise the watch channel is decorative.
        profile = self.profiles()[0]
        unrelated = {"id": 77, "full_name": "other/toolbox",
                     "description": "PDF invoice parsing utilities",
                     "topics": ["invoices"], "pushed_at": "2026-10-22T00:00:00Z",
                     "starred_at": "2026-10-01T00:00:00Z"}
        ad.atomic_json(self.data / "original_latest.json", snapshot([unrelated]))
        (self.data / "repository-profiles").mkdir(parents=True, exist_ok=True)
        (self.data / "repository-profiles" / "focus.json").write_text(
            json.dumps({"schema_version": "focus/1.0",
                        "repositories": {"other/toolbox": {"repo": "other/toolbox",
                                                          "reason": "watched by user"}}}),
            encoding="utf-8")
        rc, result = capture(ad.cmd_auto, self.args())
        self.assertEqual(rc, 0)
        self.assertEqual(result["items"], [], "No component match must not invent a wildcard target")
        watched = result["focus_deltas"]
        self.assertEqual(watched[0]["repo"], "other/toolbox")
        self.assertEqual(watched[0]["affected_targets"], [])
        self.assertEqual(result["coverage"]["focused_repositories"], 1)
        self.assertEqual(result["coverage"]["focus_not_fetched"], ["other/toolbox"])
        def github(endpoint, **kwargs):
            if "/releases?" in endpoint:
                return [{"tag_name": "v1", "body": "old"}]
            return self.github_evidence(endpoint, **kwargs)
        with patch.object(ad, "github_get", side_effect=github):
            _, fetched = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        self.assertEqual(fetched["focus_deltas"][0]["evidence_status"], "complete")
        self.assertEqual(fetched["coverage"]["focus_not_fetched"], [])

    def test_focus_delta_reports_actual_upstream_change(self):
        row = repo()
        profile = self.profiles()[0]
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        (self.data / "repository-profiles").mkdir(parents=True, exist_ok=True)
        (self.data / "repository-profiles" / "focus.json").write_text(
            json.dumps({"schema_version": "focus/1.0",
                        "repositories": {row["full_name"]: {"repo": row["full_name"],
                                                            "reason": "watched"}}}),
            encoding="utf-8")
        cached = {"repo": row["full_name"], "status": "complete", "head_sha": "old-head",
                  "release": {"tag": "v1"}, "readme": {"blob_sha": "old-readme"},
                  "fetched_at": "2026-10-20T00:00:00Z"}
        ad.atomic_json(ad.evidence_cache(self.data, row["full_name"]), cached)
        readme = {"content": "ZGVtbyByZWFkbWU=", "sha": "new-readme",
                  "html_url": "https://example.test/readme"}
        releases = [{"tag_name": "v2", "body": "new", "html_url": "https://example.test/v2"}]
        commits = [{"sha": "new-head", "html_url": "https://example.test/c",
                    "commit": {"message": "Fix captions"}}]
        with patch.object(ad, "github_get", side_effect=[readme, releases, commits]):
            rc, result = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        self.assertEqual(rc, 0)
        deltas = result["focus_deltas"]
        self.assertEqual(len(deltas), 1)
        self.assertTrue(deltas[0]["baseline_available"])
        self.assertTrue(deltas[0]["changed"]["head_changed"])
        self.assertTrue(deltas[0]["changed"]["release_changed"])
        self.assertTrue(deltas[0]["changed"]["readme_changed"])

    def test_focus_repository_absent_from_collection_is_reported(self):
        ad.atomic_json(self.data / "original_latest.json", snapshot([repo()]))
        (self.data / "repository-profiles").mkdir(parents=True, exist_ok=True)
        (self.data / "repository-profiles" / "focus.json").write_text(
            json.dumps({"schema_version": "focus/1.0",
                        "repositories": {"gone/repo": {"repo": "gone/repo", "reason": "watched"}}}),
            encoding="utf-8")
        rc, result = capture(ad.cmd_auto, self.args())
        self.assertEqual(rc, 0)
        unmatched = result["coverage"]["focus_unmatched"]
        self.assertEqual(unmatched[0]["repo"], "gone/repo")
        self.assertEqual(unmatched[0]["reason"], "not_in_star_collection")

    def test_focus_row_suppresses_ordinary_candidate_for_same_repo(self):
        row = repo("sample/subtitle")
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        (self.data / "repository-profiles").mkdir(parents=True, exist_ok=True)
        (self.data / "repository-profiles" / "focus.json").write_text(
            json.dumps({"schema_version": "focus/1.0",
                        "repositories": {row["full_name"]: {"repo": row["full_name"],
                                                            "reason": "watched"}}}),
            encoding="utf-8")
        rc, result = capture(ad.cmd_auto, self.args(limit=40, per_project=4))
        self.assertEqual(rc, 0)
        matching = [item for item in result["items"] if item["repo"] == row["full_name"]]
        self.assertEqual(len(matching), 1, matching)
        self.assertEqual(matching[0].get("watch_scope"), "focus")

    def test_judged_focus_repository_is_suppressed_until_it_changes(self):
        row = repo("sample/subtitle")
        profile = self.profiles()[0]
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        (self.data / "repository-profiles").mkdir(parents=True, exist_ok=True)
        (self.data / "repository-profiles" / "focus.json").write_text(
            json.dumps({"schema_version": "focus/1.0",
                        "repositories": {row["full_name"]: {"repo": row["full_name"],
                                                            "reason": "watched"}}}),
            encoding="utf-8")
        card = {"target": {"project_id": profile["project_id"], "target_revision": profile["target_revision"]},
                "signal": {"repo": row["full_name"], "repo_revision": ad.repo_revision(row)},
                "decision": {"status": "rejected", "reason": "no new value"},
                "_recorded_at": NOW.isoformat()}
        ad.atomic_json(self.data / "feedback" / "actual-component.json", card)
        rc, result = capture(ad.cmd_auto, self.args())
        self.assertEqual(rc, 0)
        watched = [item for item in result["items"] if item.get("watch_scope") == "focus"]
        self.assertFalse(watched, result["items"])
        self.assertEqual(result["coverage"]["focus_candidates"], 0)
        self.assertEqual(result["coverage"]["focus_suppressed"], 1)
        (self.directory / "TASKS.md").write_text("- 目标：新增声音时间轴\n", encoding="utf-8")
        _, changed = capture(ad.cmd_auto, self.args())
        self.assertEqual(changed["items"][0]["project_id"], profile["project_id"])

    def test_focus_preserves_distinct_component_decisions(self):
        write_skill(self.skills, "second-video")
        row = repo()
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        self.focus([row["full_name"]])
        profile = self.profiles()[0]
        ad.atomic_json(self.data / "feedback" / "decision.json", {
            "target": {"project_id": profile["project_id"], "target_revision": profile["target_revision"]},
            "signal": {"repo": row["full_name"], "repo_id": row["id"],
                       "repo_revision": ad.repo_revision(row)},
            "decision": {"status": "rejected"}, "_recorded_at": NOW.isoformat()})
        _, result = capture(ad.cmd_auto, self.args())
        self.assertEqual(len(result["items"]), 1)
        self.assertNotEqual(result["items"][0]["project_id"], profile["project_id"])
        self.assertTrue(result["items"][0]["target_revision"])
        self.assertEqual(len(result["suppressed"]), 1)

    def test_one_repository_cannot_fill_whole_review_queue(self):
        for index in range(5):
            write_skill(self.skills, f"video-{index}")
        rows = [repo(), {**repo("other/subtitle"), "id": 2}]
        ad.atomic_json(self.data / "original_latest.json", snapshot(rows))
        self.focus([rows[0]["full_name"]])
        _, result = capture(ad.cmd_auto, self.args(limit=12, per_project=2))
        from collections import Counter
        counts = Counter(item["repo"] for item in result["items"])
        self.assertEqual(set(counts), {row["full_name"] for row in rows})
        self.assertTrue(all(count <= 3 for count in counts.values()))
        self.assertTrue(result["coverage"]["truncated"])
        self.assertEqual(len(result["focus_deltas"][0]["affected_targets"]), 6)

    def test_focused_release_only_change_reopens_and_keeps_original_baseline(self):
        row = repo()
        self.focus([row["full_name"]])
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        def github(endpoint, **kwargs):
            if "/releases?" in endpoint:
                return [{"tag_name": "v1", "body": "old"}]
            return self.github_evidence(endpoint, **kwargs)
        with patch.object(ad, "github_get", side_effect=github):
            _, first = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        item = first["items"][0]
        ad.atomic_json(self.data / "feedback" / "decision.json", {
            "target": {"project_id": item["project_id"], "target_revision": item["target_revision"]},
            "signal": {"repo": row["full_name"], "repo_id": row["id"],
                       "repo_revision": item["repo_revision"], "evidence_revision": item["evidence_revision"]},
            "decision": {"status": "rejected"}, "_recorded_at": NOW.isoformat()})
        def github(endpoint, **kwargs):
            if "/releases?" in endpoint:
                return [{"tag_name": "v1", "body": "old"}]
            return self.github_evidence(endpoint, **kwargs)
        with patch.object(ad, "github_get", side_effect=github):
            _, same = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        self.assertFalse(same["items"])
        self.assertEqual(same["focus_deltas"][0]["new_commits"], [])
        def changed(endpoint, **kwargs):
            return ([{"tag_name": "v2", "body": "new value"}] if "/releases?" in endpoint
                    else self.github_evidence(endpoint, **kwargs))
        with patch.object(ad, "github_get", side_effect=changed):
            _, update = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        self.assertEqual(len(update["items"]), 1)
        self.assertTrue(update["focus_deltas"][0]["changed"]["release_changed"])
        self.assertFalse(update["focus_deltas"][0]["changed"]["head_changed"])
        _, unconsumed = capture(ad.cmd_auto, self.args())
        self.assertEqual(len(unconsumed["items"]), 1)

    def test_old_commit_messages_are_not_reported_as_new(self):
        prior = {"status": "complete", "head_sha": "h",
                 "commits": [{"sha": "h"}, {"sha": "old"}]}
        self.assertEqual(ad.evidence_delta("a/b", prior, prior)["new_commits"], [])
        current = {**prior, "head_sha": "new", "commits": [
            {"sha": "new"}, {"sha": "h"}, {"sha": "old"}]}
        self.assertEqual([row["sha"] for row in ad.evidence_delta("a/b", current, prior)["new_commits"]],
                         ["new"])

    def test_release_capability_recalls_new_component_direction(self):
        write_skill(self.skills, "transition-kit", "视频转场与动效")
        row = repo()
        cached = {"status": "complete", "head_sha": "head", "repo_id": row["id"],
                  "repo_revision": ad.repo_revision(row),
                  "readme": {"blob_sha": "readme-stable", "text": "stable readme"},
                  "release": {"tag": "v2", "url": "https://example.test/v2",
                              "body": "Added transition timeline export"},
                  "changed_at": (NOW - timedelta(hours=1)).isoformat()}
        ad.atomic_json(ad.evidence_cache(self.data, row["full_name"]), cached)
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        _, result = capture(ad.cmd_auto, self.args())
        rows = {(item["project_id"], item["capability"]["key"]): item for item in result["items"]}
        transition = next(key for key in rows if key[0] == "transition-kit")
        self.assertEqual(transition[1], "transition")
        self.assertEqual(rows[transition]["capability"]["anchor"], "v2")
        self.assertEqual(rows[transition]["decision_scope"], "direction")

    def test_direction_feedback_does_not_suppress_other_direction(self):
        write_skill(self.skills, "transition-kit", "视频转场与动效")
        row = repo()
        cached = {"status": "complete", "head_sha": "head", "repo_id": row["id"],
                  "repo_revision": ad.repo_revision(row),
                  "readme": {"blob_sha": "readme-stable", "text": "stable readme"},
                  "release": {"tag": "v2", "body": "Added subtitle support\nAdded transition export"},
                  "changed_at": (NOW - timedelta(hours=1)).isoformat()}
        ad.atomic_json(ad.evidence_cache(self.data, row["full_name"]), cached)
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        profiles = self.profiles()
        subtitle = next(p for p in profiles if p["project_id"] == "sample-video")
        ad.atomic_json(self.data / "feedback" / "direction.json", {
            "scope": "direction",
            "target": {"project_id": subtitle["project_id"],
                       "target_revision": subtitle["target_revision"],
                       "capability_key": "subtitle"},
            "signal": {"repo": row["full_name"], "repo_id": row["id"],
                       "repo_revision": ad.repo_revision(row),
                       "evidence_revision": ad.evidence_revision(cached)},
            "decision": {"status": "rejected", "reason": "no local gap"},
            "_recorded_at": NOW.isoformat(), "_schema": "opportunity-card/1.1"})
        _, result = capture(ad.cmd_auto, self.args(limit=20, per_project=4, per_repo=10))
        rows = [item for item in result["items"] if item["repo"] == row["full_name"]]
        keys = {(item["project_id"], item["capability"]["key"]) for item in rows}
        self.assertIn(("transition-kit", "transition"), keys)
        self.assertNotIn((subtitle["project_id"], "subtitle"), keys)
        self.assertEqual(result["suppressed"][0]["capability_key"], "subtitle")

    def test_capability_key_defaults_to_direction_without_suppressing_other_direction(self):
        write_skill(self.skills, "transition-kit", "视频转场与动效")
        row = {**repo(), "description": "database utilities", "topics": []}
        cached = {"status": "complete", "head_sha": "head", "repo_id": row["id"],
                  "repo_revision": ad.repo_revision(row),
                  "readme": {"blob_sha": "readme-stable", "text": "database utilities"},
                  "release": {"tag": "v2", "body": "Added subtitle support\nAdded transition export"}}
        ad.atomic_json(ad.evidence_cache(self.data, row["full_name"]), cached)
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        subtitle = next(p for p in self.profiles() if p["project_id"] == "sample-video")
        ad.atomic_json(self.data / "feedback" / "decision.json", {
            "target": {"project_id": subtitle["project_id"],
                       "target_revision": subtitle["target_revision"],
                       "capability_key": "subtitle"},
            "signal": {"repo": row["full_name"], "repo_id": row["id"],
                       "repo_revision": ad.repo_revision(row),
                       "evidence_revision": ad.evidence_revision(cached)},
            "decision": {"status": "rejected", "reason": "no local gap"},
            "_recorded_at": NOW.isoformat(), "_schema": "opportunity-card/1.1"})
        _, result = capture(ad.cmd_auto, self.args(limit=20, per_project=4, per_repo=10))
        rows = [item for item in result["items"] if item["repo"] == row["full_name"]]
        self.assertEqual([(row["project_id"], row["capability"]["key"]) for row in rows],
                         [("transition-kit", "transition")])
        suppressed = [row for row in result["suppressed"]
                      if row["project_id"] == subtitle["project_id"]]
        self.assertEqual(suppressed[0]["decision_scope"], "direction")
        self.assertEqual(suppressed[0]["capability_key"], "subtitle")

    def test_release_hint_recalls_when_metadata_and_readme_do_not_match(self):
        write_skill(self.skills, "transition-kit", "视频转场与动效")
        row = {**repo(), "description": "database utilities", "topics": []}
        cached = {"status": "complete", "head_sha": "head", "repo_id": row["id"],
                  "repo_revision": ad.repo_revision(row),
                  "readme": {"blob_sha": "readme-stable", "text": "database utilities"},
                  "release": {"tag": "v2", "body": "Added transition export"}}
        ad.atomic_json(ad.evidence_cache(self.data, row["full_name"]), cached)
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        _, result = capture(ad.cmd_auto, self.args())
        rows = [item for item in result["items"] if item["project_id"] == "transition-kit"]
        self.assertEqual(len(rows), 1)
        item = rows[0]
        self.assertEqual(item["project_id"], "transition-kit")
        self.assertEqual(item["capability"]["key"], "transition")
        self.assertEqual(item["capability"]["anchor"], "v2")

    def test_legacy_feedback_still_suppresses_repository_candidate(self):
        row = repo()
        profile = self.profiles()[0]
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        ad.atomic_json(self.data / "feedback" / "legacy.json", {
            "target": {"project_id": profile["project_id"],
                       "target_revision": profile["target_revision"]},
            "signal": {"repo": row["full_name"], "repo_id": row["id"],
                       "repo_revision": ad.repo_revision(row)},
            "decision": {"status": "rejected"}, "_recorded_at": NOW.isoformat(),
            "_schema": "opportunity-card/1.0"})
        _, result = capture(ad.cmd_auto, self.args())
        self.assertEqual(result["items"], [])
        self.assertEqual(result["coverage"]["suppressed"], 1)
        self.assertEqual(result["suppressed"][0]["decision_scope"], "legacy")

    def test_review_queue_persists_and_rotates_unjudged_components(self):
        for index in range(10):
            write_skill(self.skills, f"video-{index}", "视频字幕时间轴")
        row = repo()
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        seen = set()
        for day in range(4):
            with patch.object(ad, "now_utc", return_value=NOW + timedelta(days=day)):
                _, result = capture(ad.cmd_auto, self.args(
                write=True, limit=3, per_project=1, per_repo=3,
                data_dir=self.data))
            keys = [item["candidate_key"] for item in result["items"]]
            queue = ad.read_json(self.data / ad.QUEUE_FILE)
            self.assertEqual(queue["cursor"]["round_seq"], day + 1)
            self.assertEqual(set(queue["last_run_selected_keys"]), set(keys))
            seen.update(keys)
            # Advance persisted times without rewriting source clocks.
            for entry in queue["entries"].values():
                entry["last_shown_at"] = (NOW + timedelta(days=day)).isoformat()
            ad.atomic_json(self.data / ad.QUEUE_FILE, queue)
        self.assertGreaterEqual(len(seen), 10)

    def test_review_queue_marks_standard_direction_feedback_judged(self):
        row = repo()
        cached = {"status": "complete", "head_sha": "head", "repo_id": row["id"],
                  "repo_revision": ad.repo_revision(row),
                  "readme": {"blob_sha": "readme-stable", "text": "demo readme"},
                  "release": {"tag": "v2", "body": "Added subtitle support"},
                  "changed_at": (NOW - timedelta(hours=1)).isoformat()}
        ad.atomic_json(ad.evidence_cache(self.data, row["full_name"]), cached)
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        _, first = capture(ad.cmd_auto, self.args(write=True))
        item = first["items"][0]
        ad.atomic_json(self.data / "feedback" / "decision.json", {
            "scope": "direction",
            "target": {"project_id": item["project_id"],
                       "target_revision": item["target_revision"],
                       "capability_key": item["capability"]["key"]},
            "signal": {"repo": row["full_name"], "repo_id": row["id"],
                       "repo_revision": item["repo_revision"],
                       "evidence_revision": item["evidence_revision"]},
            "decision": {"status": "rejected", "reason": "no local gap"},
            "_recorded_at": NOW.isoformat(), "_schema": "opportunity-card/1.1"})
        _, second = capture(ad.cmd_auto, self.args(write=True))
        queue = ad.read_json(self.data / ad.QUEUE_FILE)
        entry = queue["entries"][item["candidate_key"]]
        self.assertEqual(entry["state"], "judged")
        self.assertEqual(entry["judged_ref"], "decision.json")
        self.assertFalse(second["items"])

    def test_request_budget_caps_get_calls_and_reports_usage(self):
        row = repo()
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        calls = []
        def counted(endpoint, **kwargs):
            calls.append(endpoint)
            return self.github_evidence(endpoint, **kwargs)
        with patch.object(ad, "github_get", side_effect=counted):
            _, result = capture(ad.cmd_auto, self.args(
                fetch_evidence=True, evidence_limit=2, request_budget=3))
        report = result["coverage"]["watch_coverage"]["request_budget"]
        self.assertEqual(report["limit"], 3)
        self.assertLessEqual(report["used"], 3)
        self.assertTrue(report["exhausted"] or report["used"] == 3)

    def test_refresh_counts_each_star_page_against_the_budget(self):
        rows = [{**repo(f"sample/subtitle{i}"), "id": i} for i in range(100)]
        pages = [rows[:100], [rows[0]]]  # synthetic second page triggers a duplicate
        ad.atomic_json(self.data / "original_latest.json", snapshot([]))
        calls = []
        def github(endpoint, **kwargs):
            calls.append(endpoint)
            if endpoint == "user":
                return {"login": "sample"}
            if endpoint.endswith("&page=1"):
                return pages[0]
            if endpoint.endswith("&page=2"):
                return pages[1]
            raise AssertionError(endpoint)
        with patch.object(ad, "github_get", side_effect=github):
            with self.assertRaises(ValueError):
                ad.refresh_snapshot(self.data, None, ad.RequestBudget(3))
        self.assertEqual(len(calls), 3)
        self.assertTrue(calls[1].endswith("&page=1"))
        self.assertTrue(calls[2].endswith("&page=2"))

    def test_refresh_and_compare_share_the_same_request_budget(self):
        row = repo()
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        ad.atomic_json(ad.evidence_cache(self.data, row["full_name"]), {
            "status": "complete", "head_sha": "a" * 40,
            "repo_revision": ad.repo_revision(row),
            "readme": {"blob_sha": "stable", "text": "stable"},
            "release": None})
        pinned, head = "a" * 40, "b" * 40
        library = self.directory / "reference-library"
        (library / "sources" / "sample--subtitle").mkdir(parents=True)
        ad.atomic_json(library / "manifests" / "sample--subtitle.json",
                       {"repo": row["full_name"], "commit": pinned})
        calls = []
        def github(endpoint, **kwargs):
            calls.append(endpoint)
            if endpoint == "user":
                return {"login": "sample"}
            if "user/starred" in endpoint:
                return [{"starred_at": row["starred_at"], "repo": row}]
            if "/commits?" in endpoint:
                return [{"sha": head, "commit": {"message": "new"}}]
            if "/compare/" in endpoint:
                return {"status": "ahead", "files": []}
            return self.github_evidence(endpoint, **kwargs)
        with patch.object(ad, "github_get", side_effect=github):
            _, result = capture(ad.cmd_auto, self.args(
                refresh=True, fetch_evidence=True, evidence_limit=1,
                request_budget=8))
        report = result["coverage"]["watch_coverage"]["request_budget"]
        self.assertLessEqual(report["used"], 8)
        self.assertEqual(report["used"], len(calls))
        self.assertGreater(report["by_kind"].get("refresh", 0), 0)
        self.assertGreater(report["by_kind"].get("compare", 0), 0)


    def test_budget_skip_does_not_advance_checked_or_release_suppression(self):
        row = repo()
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        cached = {"status": "complete", "head_sha": "head", "repo_id": row["id"],
                  "repo_revision": ad.repo_revision(row),
                  "readme": {"blob_sha": "readme-stable", "text": "stable readme"},
                  "release": {"tag": "v1", "body": "old", "url": None,
                              "published_at": None},
                  "fetched_at": (NOW - timedelta(days=2)).isoformat(),
                  "changed_at": (NOW - timedelta(days=2)).isoformat()}
        ad.atomic_json(ad.evidence_cache(self.data, row["full_name"]), cached)
        ad.atomic_json(self.data / "auto-opportunities" / "watch.json", {
            row["full_name"]: {"checked_at": (NOW - timedelta(days=2)).isoformat(),
                               "status": "complete", "repo_id": row["id"],
                               "repo": row["full_name"],
                               "repo_revision": ad.repo_revision(row)}})
        with patch.object(ad, "github_get", side_effect=ad.BudgetExceeded("test")):
            _, result = capture(ad.cmd_auto, self.args(
                fetch_evidence=True, evidence_limit=1, request_budget=1))
        # Deep evidence issues readme first and is skipped before any partial
        # data can replace the complete cache.
        coverage = result["coverage"]["watch_coverage"]
        self.assertEqual(coverage["skipped_budget"], [row["full_name"]])
        self.assertEqual(coverage["checked"], 0)
        self.assertEqual(coverage["not_checked"], 1)
        stored = ad.read_json(ad.evidence_cache(self.data, row["full_name"]))
        self.assertEqual(stored["changed_at"], cached["changed_at"])
        watch = ad.read_json(self.data / "auto-opportunities" / "watch.json")
        self.assertEqual(watch[row["full_name"]]["checked_at"],
                         (NOW - timedelta(days=2)).isoformat())
        self.assertTrue(watch[row["full_name"]]["last_attempt_at"])

    def test_first_cheap_probe_persists_release_baseline(self):
        row = repo()
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        release = [{"tag_name": "v1", "body": "initial", "html_url": "https://example.test/v1"}]
        def github(endpoint, **kwargs):
            return release if "/releases?" in endpoint else self.github_evidence(endpoint, **kwargs)
        with patch.object(ad, "github_get", side_effect=github):
            _, first = capture(ad.cmd_auto, self.args(
                fetch_evidence=True, evidence_limit=0,
                cheap_budget=1, request_budget=4))
        stored = ad.read_json(ad.evidence_cache(self.data, row["full_name"]))
        self.assertEqual(stored["release"]["tag"], "v1")
        self.assertEqual(stored["probe"], "cheap")
        self.assertTrue(stored.get("changed_at"))
        self.assertEqual(first["coverage"]["watch_coverage"]["cheap_probed"],
                         [row["full_name"]])

    def test_cheap_probe_uses_one_get_and_keeps_previous_evidence(self):
        row = repo()
        other = {**repo("sample/other", push="2026-10-21T00:00:00Z"), "id": 2}
        cached = {"status": "complete", "head_sha": "head", "repo_id": row["id"],
                  "repo_revision": ad.repo_revision(row),
                  "readme": {"blob_sha": "readme-stable", "text": "stable readme"},
                  "release": {"tag": "v1", "body": "old"}, "fetched_at": NOW.isoformat()}
        ad.atomic_json(ad.evidence_cache(self.data, row["full_name"]), cached)
        ad.atomic_json(self.data / "original_latest.json", snapshot([row, other]))
        calls = []
        def counted(endpoint, **kwargs):
            calls.append(endpoint)
            return self.github_evidence(endpoint, **kwargs)
        with patch.object(ad, "github_get", side_effect=counted):
            _, result = capture(ad.cmd_auto, self.args(fetch_evidence=True, evidence_limit=1,
                                                      request_budget=4, cheap_budget=1))
        cheap = result["coverage"]["watch_coverage"]["cheap_probed"]
        self.assertTrue(cheap)
        stored = ad.read_json(ad.evidence_cache(self.data, row["full_name"]))
        self.assertEqual(stored["readme"]["blob_sha"], "readme-stable")
        self.assertEqual(stored["probe"], "cheap")

    def test_cheap_probe_legacy_cache_does_not_refresh_changed_at(self):
        row = repo()
        cached = {"status": "complete", "head_sha": "head", "repo_id": row["id"],
                  "repo_revision": ad.repo_revision(row),
                  "readme": {"blob_sha": "readme-stable", "text": "stable readme"},
                  "release": None, "fetched_at": NOW.isoformat(),
                  "changed_at": "2026-10-01T00:00:00+00:00"}
        ad.atomic_json(ad.evidence_cache(self.data, row["full_name"]), cached)
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        def github(endpoint, **kwargs):
            if "/releases?" in endpoint:
                return [{"tag_name": "v1", "body": "old"}]
            return self.github_evidence(endpoint, **kwargs)
        with patch.object(ad, "github_get", side_effect=github):
            _, result = capture(ad.cmd_auto, self.args(
                fetch_evidence=True, evidence_limit=1,
                cheap_budget=1, request_budget=2))
        stored = ad.read_json(ad.evidence_cache(self.data, row["full_name"]))
        self.assertEqual(stored["changed_at"], cached["changed_at"])
        self.assertFalse(result["items"][0]["upstream_change"]["changed"] or {})

    def test_deep_probe_after_cheap_baseline_treats_missing_fields_as_unknown(self):
        row = repo()
        cached = {"status": "complete", "head_sha": None, "repo_id": row["id"],
                  "repo_revision": ad.repo_revision(row), "readme": None,
                  "release": {"tag": "v1", "url": None,
                              "published_at": None, "body": "old"},
                  "fetched_at": (NOW - timedelta(hours=2)).isoformat(),
                  "changed_at": (NOW - timedelta(hours=2)).isoformat(),
                  "probe": "cheap"}
        ad.atomic_json(ad.evidence_cache(self.data, row["full_name"]), cached)
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        def github(endpoint, **kwargs):
            if "/releases?" in endpoint:
                return [{"tag_name": "v1", "body": "old"}]
            return self.github_evidence(endpoint, **kwargs)
        with patch.object(ad, "github_get", side_effect=github):
            _, result = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        item = result["items"][0]
        changed = item["upstream_change"]["changed"]
        self.assertEqual((changed["head_changed"], changed["readme_changed"],
                          changed["release_changed"]), (None, None, False))
        stored = ad.read_json(ad.evidence_cache(self.data, row["full_name"]))
        self.assertEqual(stored["changed_at"], cached["changed_at"])

    def test_corrupt_review_queue_preserves_original_and_degrades(self):
        row = repo()
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        path = self.data / ad.QUEUE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{broken", encoding="utf-8")
        before = path.read_bytes()
        _, result = capture(ad.cmd_auto, self.args())
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["coverage"]["review_queue"]["queue_state"], "degraded")
        self.assertTrue(any("review queue" in warning.lower() for warning in result["warnings"]))
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(list(path.parent.glob("review-queue.json.corrupt-*")))

    def test_all_stars_and_focus_rotate_beyond_candidate_and_evidence_limits(self):
        rows = [{**repo(f"sample/subtitle{i}"), "id": i} for i in range(6)]
        rows[-1] = {**rows[-1], "description": "unrelated", "topics": []}
        ad.atomic_json(self.data / "original_latest.json", snapshot(rows))
        self.focus([row["full_name"] for row in rows[:4]])
        seen = set()
        for day in range(6):
            with patch.object(ad, "now_utc", return_value=NOW + timedelta(days=day)), \
                 patch.object(ad, "github_get", side_effect=self.github_evidence):
                _, result = capture(ad.cmd_auto, self.args(fetch_evidence=True, evidence_limit=2,
                                                           focus_limit=1, limit=1, per_project=1))
            coverage = result["coverage"]["watch_coverage"]
            self.assertLessEqual(coverage["checked"], 3)
            self.assertEqual(coverage["not_checked"], 6 - coverage["checked"])
            checked = coverage["checked_repos"]
            self.assertLessEqual(sum(name in {row["full_name"] for row in rows[:4]} for name in checked), 1)
            seen.update(checked)
        self.assertEqual(seen, {row["full_name"] for row in rows})

    def test_corrupt_focus_and_evidence_do_not_hide_ordinary_discovery(self):
        row = repo()
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        path = self.data / ad.FOCUS_FILE
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")
        cache = ad.evidence_cache(self.data, row["full_name"])
        cache.parent.mkdir(parents=True)
        cache.write_text("{broken", encoding="utf-8")
        _, result = capture(ad.cmd_auto, self.args())
        self.assertEqual(len(result["items"]), 1)
        self.assertTrue(any("focus" in warning for warning in result["warnings"]))
        self.assertTrue(any("evidence cache" in warning for warning in result["warnings"]))
        self.assertEqual(result["status"], "partial")

    def test_missing_or_failed_evidence_cannot_suppress_bound_decision(self):
        row = repo()
        profile = self.profiles()[0]
        card = {"signal": {"repo": row["full_name"], "repo_revision": ad.repo_revision(row),
                           "evidence_revision": "known-before"},
                "target": {"project_id": profile["project_id"], "target_revision": profile["target_revision"]},
                "decision": {"status": "rejected"}, "_recorded_at": NOW.isoformat()}
        self.assertIsNone(ad.suppression(profile, row, [card], NOW))
        self.assertIsNone(ad.suppression(profile, {**row, "_evidence_revision": "known-before",
                                                 "_evidence_unavailable": True}, [card], NOW))

    def test_failed_refresh_remains_pending_on_next_offline_run(self):
        row = repo()
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        with patch.object(ad, "github_get", side_effect=self.github_evidence):
            _, first = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        item = first["items"][0]
        ad.atomic_json(self.data / "feedback" / "decision.json", {
            "target": {"project_id": item["project_id"], "target_revision": item["target_revision"]},
            "signal": {"repo": row["full_name"], "repo_revision": item["repo_revision"],
                       "evidence_revision": item["evidence_revision"]},
            "decision": {"status": "rejected"}, "_recorded_at": NOW.isoformat()})
        with patch.object(ad, "github_get", side_effect=RuntimeError("temporary failure")):
            _, failed = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        self.assertEqual(len(failed["items"]), 1)
        _, offline = capture(ad.cmd_auto, self.args())
        self.assertEqual(len(offline["items"]), 1)
        self.assertEqual(offline["coverage"]["watch_coverage"]["unresolved_previous_failures"],
                         [row["full_name"]])
        with patch.object(ad, "github_get", side_effect=self.github_evidence):
            _, recovered = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        self.assertFalse(recovered["items"])

    def test_budget_skip_preserves_previous_failure_until_complete(self):
        row = repo()
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        with patch.object(ad, "github_get", side_effect=RuntimeError("temporary failure")):
            _, partial = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        self.assertTrue(partial["coverage"]["watch_coverage"]["failed_deep"])
        with patch.object(ad, "github_get", side_effect=ad.BudgetExceeded("test")):
            _, skipped = capture(ad.cmd_auto, self.args(fetch_evidence=True, request_budget=1))
        self.assertEqual(skipped["coverage"]["watch_coverage"]["skipped_budget"],
                         [row["full_name"]])
        _, offline = capture(ad.cmd_auto, self.args())
        self.assertEqual(offline["coverage"]["watch_coverage"]["unresolved_previous_failures"],
                         [row["full_name"]])

    def test_unrelated_scope_exclusions_do_not_create_components_or_conflicts(self):
        write_skill(self.skills, "browser-shell", "浏览器操作。不要用于法律检索。")
        row = {**repo("ui/react-kit"), "description": "React UI components", "topics": []}
        selected, _, _ = ad.prepare(snapshot([row]), self.profiles(), {}, NOW)
        self.assertEqual(selected, [])
        video = next(profile for profile in self.profiles() if profile["project_id"] == "sample-video")
        video["exclusions"] = ["法律检索"]
        relevant, _, _ = ad.prepare(snapshot([repo()]), [video], {}, NOW)
        self.assertTrue(relevant)
        self.assertEqual(relevant[0]["scope_conflicts"], [])

    def test_daily_reports_existing_snapshot_and_bounded_source_comparison(self):
        row = repo()
        library = self.directory / "reference-library"
        (library / "sources" / "sample--subtitle").mkdir(parents=True)
        pinned, head = "a" * 40, "b" * 40
        (library / "README.md").write_text(f"| [source](sources/sample--subtitle/) | `{pinned}` |\n")
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        def github(endpoint, **kwargs):
            if "/commits?" in endpoint:
                return [{"sha": head, "commit": {"message": "New engine"}}]
            if "/compare/" in endpoint:
                return {"status": "ahead", "ahead_by": 2, "total_commits": 2,
                        "files": [{"filename": f"core/{i}.py", "patch": "x" * 1400} for i in range(35)]}
            return self.github_evidence(endpoint, **kwargs)
        with patch.object(ad, "github_get", side_effect=github):
            _, result = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        item = result["items"][0]
        self.assertEqual(item["local_snapshots"][0]["commit"], pinned)
        self.assertEqual(item["local_snapshots"][0]["upstream_head"], head)
        compare = item["source_comparison"]
        self.assertEqual((compare["base"], compare["head"]), (pinned, head))
        self.assertEqual(len(compare["files"]), 30)
        self.assertTrue(compare["files_truncated"])
        self.assertTrue(compare["files"][0]["patch_truncated"])

    def test_observation_delta_and_pinned_source_delta_keep_separate_bases(self):
        row = repo()
        pinned, observed, head = "a" * 40, "b" * 40, "c" * 40
        library = self.directory / "reference-library"
        (library / "sources" / "sample--subtitle").mkdir(parents=True)
        (library / "manifests").mkdir()
        ad.atomic_json(library / "manifests" / "sample--subtitle.json",
                       {"repo": row["full_name"], "commit": pinned})
        ad.atomic_json(ad.evidence_cache(self.data, row["full_name"]), {
            "status": "complete", "head_sha": observed, "repo_revision": ad.repo_revision(row)})
        ad.atomic_json(self.data / "original_latest.json", snapshot([row]))
        def github(endpoint, **kwargs):
            if "/commits?" in endpoint:
                return [{"sha": head, "commit": {"message": "Updated engine"}}]
            if "/compare/" in endpoint:
                return {"status": "ahead", "files": []}
            return self.github_evidence(endpoint, **kwargs)
        with patch.object(ad, "github_get", side_effect=github):
            _, result = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        item = result["items"][0]
        self.assertEqual(item["source_comparison"]["base"], pinned)
        self.assertEqual(item["upstream_change"]["observation_comparison"]["base"], observed)
        self.assertEqual(item["local_snapshots"][0]["upstream_head"], head)

    def test_each_component_uses_its_own_pinned_version_or_explicit_unknown(self):
        other = write_skill(self.skills, "second-video")
        pinned, second, head = "a" * 40, "b" * 40, "c" * 40
        for directory, commit in ((self.directory, pinned), (other, second)):
            library = directory / "reference-library"
            (library / "sources" / "sample--subtitle").mkdir(parents=True)
            ad.atomic_json(library / "manifests/sample--subtitle.json",
                           {"repo": "sample/subtitle", "commit": commit})
        ad.atomic_json(self.data / "original_latest.json", snapshot([repo()]))
        def github(endpoint, **kwargs):
            if "/commits?" in endpoint:
                return [{"sha": head, "commit": {"message": "New engine"}}]
            if "/compare/" in endpoint:
                return {"status": "ahead", "files": []}
            return self.github_evidence(endpoint, **kwargs)
        with patch.object(ad, "github_get", side_effect=github) as api:
            _, result = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        rows = {item["project_id"]: item for item in result["items"]}
        self.assertEqual(rows["sample-video"]["source_comparison"]["base"], pinned)
        self.assertEqual(rows["second-video"]["source_comparison"]["base"], second)
        self.assertEqual(len(rows["second-video"]["target_snapshots"]), 1)
        self.assertEqual(len([call for call in api.call_args_list if "/compare/" in call.args[0]]), 2)
        # A new observed head uses one compare slot, leaving one pinned base
        # unexamined. It must not receive the other component's patch.
        with patch.object(ad, "github_get", side_effect=lambda endpoint, **kwargs:
                          [{"sha": "d" * 40, "commit": {"message": "Another update"}}]
                          if "/commits?" in endpoint else github(endpoint, **kwargs)):
            _, next_run = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        comparisons = [item["source_comparison"] for item in next_run["items"]]
        self.assertEqual({item["base"] for item in comparisons}, {pinned, second})
        self.assertEqual(sum(item["status"] == "not_fetched" for item in comparisons), 1)

    def test_component_already_at_head_has_no_other_components_diff(self):
        other = write_skill(self.skills, "second-video")
        head = "c" * 40
        for directory, commit in ((self.directory, "a" * 40), (other, head)):
            library = directory / "reference-library"
            (library / "sources/sample--subtitle").mkdir(parents=True)
            ad.atomic_json(library / "manifests/sample--subtitle.json",
                           {"repo": "sample/subtitle", "commit": commit})
        ad.atomic_json(self.data / "original_latest.json", snapshot([repo()]))
        def github(endpoint, **kwargs):
            if "/commits?" in endpoint:
                return [{"sha": head, "commit": {"message": "New engine"}}]
            if "/compare/" in endpoint:
                return {"status": "ahead", "files": []}
            return self.github_evidence(endpoint, **kwargs)
        with patch.object(ad, "github_get", side_effect=github):
            _, result = capture(ad.cmd_auto, self.args(fetch_evidence=True))
        current = next(item for item in result["items"] if item["project_id"] == "second-video")
        self.assertEqual(current["source_comparison"]["status"], "identical")
        self.assertEqual(current["source_comparison"]["base"], head)
        self.assertEqual(current["source_comparison"]["files"], [])

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
