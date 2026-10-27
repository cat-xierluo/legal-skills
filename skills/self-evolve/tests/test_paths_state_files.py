from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import self_evolve_paths as sep  # noqa: E402


class IgnoredStateFilesTests(unittest.TestCase):
    """macOS .DS_Store 被 Finder 自动改写，纳入会让 migration marker flaky 失效
    （Finder 改写 → 指纹变 → marker invalid → migration_required 又 True）。
    这些 OS 元数据文件必须从 legacy state 指纹里排除（2026-08-06 实测坑）。"""

    def test_ds_store_is_ignored(self):
        self.assertTrue(sep.is_ignored_state_file(Path("runtime/.DS_Store")))

    def test_real_state_file_is_not_ignored(self):
        self.assertFalse(sep.is_ignored_state_file(Path("runtime/skill-inventory.json")))

    def test_legacy_state_files_excludes_ignored_names(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = Path(d) / "runtime"
            runtime.mkdir()
            (runtime / "real.json").write_text("{}", encoding="utf-8")
            (runtime / ".DS_Store").write_text("finder metadata", encoding="utf-8")
            orig_rt = sep.LEGACY_RUNTIME_ROOT
            orig_rv = sep.LEGACY_REVIEW_ROOT
            sep.LEGACY_RUNTIME_ROOT = runtime
            sep.LEGACY_REVIEW_ROOT = Path(d) / "no-review"
            try:
                names = [p.name for p in sep.legacy_state_files()]
            finally:
                sep.LEGACY_RUNTIME_ROOT = orig_rt
                sep.LEGACY_REVIEW_ROOT = orig_rv
        self.assertIn("real.json", names)
        self.assertNotIn(".DS_Store", names)


class LegacyActiveArtifactTests(unittest.TestCase):
    """v1.0.0: legacy 源码树的活跃产出（dreaming/session-summaries/panel/logs/
    scheduler/learning-candidates + 顶层活跃日志 + review/output）不算冻结 state，
    不参与 migration marker sha256 校验。这些 v0.7.0 后应全部写 external，残留或
    路径 bug 误写不触发迁移门禁——根治 marker flaky（2026-08-08 实测 legacy
    source-index 被一次 backfill 写入致 marker 反复失效）。"""

    def test_is_legacy_active_artifact_classifies_paths(self):
        rt = sep.LEGACY_RUNTIME_ROOT
        rv = sep.LEGACY_REVIEW_ROOT
        # runtime 活跃子树
        self.assertTrue(sep.is_legacy_active_artifact(rt / "dreaming" / "source-index.json"))
        self.assertTrue(sep.is_legacy_active_artifact(rt / "session-summaries" / "2608" / "codex_x.json"))
        self.assertTrue(sep.is_legacy_active_artifact(rt / "panel" / "self-evolve-panel.html"))
        self.assertTrue(sep.is_legacy_active_artifact(rt / "logs" / "a.log"))
        self.assertTrue(sep.is_legacy_active_artifact(rt / "scheduler" / "runs.jsonl"))
        self.assertTrue(sep.is_legacy_active_artifact(rt / "learning-candidates" / "c.md"))
        # runtime 顶层活跃日志
        self.assertTrue(sep.is_legacy_active_artifact(rt / "evaluation-log.jsonl"))
        self.assertTrue(sep.is_legacy_active_artifact(rt / "hook-runs.jsonl"))
        self.assertTrue(sep.is_legacy_active_artifact(rt / "skill-inventory.json"))
        # review/output 整子树
        self.assertTrue(sep.is_legacy_active_artifact(rv / "output" / "articles" / "z.md"))
        self.assertTrue(sep.is_legacy_active_artifact(rv / "output" / "upgrade-direction" / "u.md"))
        # 非活跃 = 冻结 state，仍参与校验
        self.assertFalse(sep.is_legacy_active_artifact(rt / "some-frozen-state.json"))

    def test_runtime_active_subtree_excluded_from_legacy_state_files(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = Path(d) / "runtime"
            review = Path(d) / "review"
            runtime.mkdir()
            review.mkdir()
            (runtime / "dreaming").mkdir()
            (runtime / "dreaming" / "source-index.json").write_text("{}", encoding="utf-8")
            (runtime / "session-summaries").mkdir()
            (runtime / "session-summaries" / "2608").mkdir()
            (runtime / "session-summaries" / "2608" / "codex_x.json").write_text("{}", encoding="utf-8")
            (runtime / "real-frozen.json").write_text("{}", encoding="utf-8")
            orig_rt, orig_rv = sep.LEGACY_RUNTIME_ROOT, sep.LEGACY_REVIEW_ROOT
            sep.LEGACY_RUNTIME_ROOT, sep.LEGACY_REVIEW_ROOT = runtime, review
            try:
                names = [p.name for p in sep.legacy_state_files()]
            finally:
                sep.LEGACY_RUNTIME_ROOT, sep.LEGACY_REVIEW_ROOT = orig_rt, orig_rv
        self.assertIn("real-frozen.json", names)
        self.assertNotIn("source-index.json", names)
        self.assertNotIn("codex_x.json", names)

    def test_runtime_active_top_files_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = Path(d) / "runtime"
            review = Path(d) / "review"
            runtime.mkdir()
            review.mkdir()
            (runtime / "evaluation-log.jsonl").write_text("[]", encoding="utf-8")
            (runtime / "hook-runs.jsonl").write_text("[]", encoding="utf-8")
            (runtime / "skill-inventory.json").write_text("{}", encoding="utf-8")
            (runtime / "skill-inventory.md").write_text("# inv", encoding="utf-8")
            (runtime / "extraction_sessions.json").write_text("{}", encoding="utf-8")
            (runtime / "real.json").write_text("{}", encoding="utf-8")
            orig_rt, orig_rv = sep.LEGACY_RUNTIME_ROOT, sep.LEGACY_REVIEW_ROOT
            sep.LEGACY_RUNTIME_ROOT, sep.LEGACY_REVIEW_ROOT = runtime, review
            try:
                names = [p.name for p in sep.legacy_state_files()]
            finally:
                sep.LEGACY_RUNTIME_ROOT, sep.LEGACY_REVIEW_ROOT = orig_rt, orig_rv
        self.assertEqual(names, ["real.json"])

    def test_review_output_and_placeholder_yield_empty_state(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = Path(d) / "runtime"
            review = Path(d) / "review"
            runtime.mkdir()
            review.mkdir()
            (review / "output").mkdir()
            (review / "output" / "articles").mkdir()
            (review / "output" / "articles" / "draft.md").write_text("x", encoding="utf-8")
            (review / "archive").mkdir()
            (review / "archive" / "README.md").write_text("placeholder", encoding="utf-8")
            orig_rt, orig_rv = sep.LEGACY_RUNTIME_ROOT, sep.LEGACY_REVIEW_ROOT
            sep.LEGACY_RUNTIME_ROOT, sep.LEGACY_REVIEW_ROOT = runtime, review
            try:
                files = sep.legacy_state_files()
                present = sep.legacy_state_present()
            finally:
                sep.LEGACY_RUNTIME_ROOT, sep.LEGACY_REVIEW_ROOT = orig_rt, orig_rv
        self.assertEqual(files, [])
        self.assertFalse(present)

    def test_only_active_artifacts_not_present(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = Path(d) / "runtime"
            review = Path(d) / "review"
            runtime.mkdir()
            review.mkdir()
            (runtime / "dreaming").mkdir()
            (runtime / "dreaming" / "x.json").write_text("{}", encoding="utf-8")
            (review / "output").mkdir()
            (review / "output" / "a.md").write_text("x", encoding="utf-8")
            orig_rt, orig_rv = sep.LEGACY_RUNTIME_ROOT, sep.LEGACY_REVIEW_ROOT
            sep.LEGACY_RUNTIME_ROOT, sep.LEGACY_REVIEW_ROOT = runtime, review
            try:
                present = sep.legacy_state_present()
            finally:
                sep.LEGACY_RUNTIME_ROOT, sep.LEGACY_REVIEW_ROOT = orig_rt, orig_rv
        self.assertFalse(present)


if __name__ == "__main__":
    unittest.main()
