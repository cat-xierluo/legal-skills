from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import sys
import tempfile
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import dream_sweep as ds  # noqa: E402
import deep_dream as dd  # noqa: E402


def summary(
    session_id: str,
    keywords: list[str],
    *,
    source: str = "codex",
    source_variant: str = "codex_active",
    skills: list[str] | None = None,
) -> ds.SessionSummary:
    now = "2026-07-18 12:00:00"
    return ds.SessionSummary(
        source=source,
        source_variant=source_variant,
        session_id=session_id,
        transcript_path=f"/tmp/{session_id}.jsonl",
        started_at=now,
        ended_at=now,
        cwd=f"/tmp/{session_id}",
        cwd_label=session_id,
        agent_context={},
        topic_title=session_id,
        topic_keywords=keywords,
        session_class="substantive",
        summary_policy="summarize_candidate",
        noise_reasons=[],
        related_skills=skills or [],
        work_stage="workflow_design",
        agent_collaboration_mode="single_agent",
        decisions=[],
        open_questions=[],
        upgrade_signals=[],
        article_signals=[],
        timeline_signals=[],
        sensitive_risk=False,
        redaction_notes=[],
        evidence_snippets=[],
    )


def configure_runtime_roots(root: Path) -> None:
    ds.SESSION_SUMMARY_DIR = root / "session-summaries"
    ds.DREAMING_DIR = root / "dreaming"
    ds.DREAM_RUN_DIR = ds.DREAMING_DIR / "runs"
    ds.BACKFILL_STATE_PATH = ds.DREAMING_DIR / "backfill-state.json"
    ds.RAW_SESSIONS_DIR = root / "raw-sessions"


def index_args(index_mode: str = "recent") -> argparse.Namespace:
    return argparse.Namespace(
        mode="dry-run",
        index_mode=index_mode,
        max_sessions=10,
        cluster_similarity=0.4,
        since="14d",
    )


def concurrent_index_writer(root: str, session_id: str, ready: object) -> None:
    configure_runtime_roots(Path(root))
    ready.wait(timeout=10)
    item = summary(session_id, ["alpha-specific", "shared-specific"])
    item.evidence_snippets = [f"{session_id} synthetic evidence"]
    ds.update_runtime_indexes(
        [item],
        {"task_id": f"task-{session_id}", "sources": {}},
        index_args("recent"),
        f"run-{session_id}",
    )


class JsonlReaderTests(unittest.TestCase):
    def test_read_counters_are_persisted_on_session_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "counters.jsonl"
            path.write_bytes(
                b'{"type":"session_meta","payload":{"id":"counter-1","cwd":"/tmp"}}\n'
                b'not-json\n'
                b'{"type":"event_msg","payload":{"type":"user_message","message":"counter test workflow"}}\n'
            )
            records, stats = ds.read_jsonl_with_stats(path, max_lines=10, max_tool_line_bytes=256)
            result = ds.summarize_records(
                path,
                "codex",
                records,
                [],
                [],
                source_variant="codex_active",
                read_stats=stats,
            )
            self.assertIsNotNone(result)
            assert result is not None
            persisted = asdict(result)
            self.assertEqual(persisted["total_line_count"], 3)
            self.assertEqual(persisted["parsed_line_count"], 2)
            self.assertEqual(persisted["invalid_line_count"], 1)
            self.assertEqual(persisted["selected_line_count"], 2)
            self.assertEqual(persisted["skipped_line_count"], 1)

    def test_stream_keeps_head_and_final_tail_while_skipping_large_tool_line(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "long.jsonl"
            records = [
                {"type": "session_meta", "payload": {"id": "s-1", "cwd": "/tmp"}},
                *[
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user" if index % 2 else "assistant",
                            "content": [{"type": "input_text", "text": f"message-{index}"}],
                        },
                    }
                    for index in range(1, 80)
                ],
                {
                    "type": "response_item",
                    "payload": {"type": "function_call_output", "output": "x" * 5000},
                },
                {
                    "type": "event_msg",
                    "payload": {"type": "verification", "message": "FINAL_VERIFICATION_OK"},
                },
            ]
            path.write_bytes(b"".join((json.dumps(item) + "\n").encode() for item in records))

            selected, stats = ds.read_jsonl_with_stats(path, max_lines=12, max_tool_line_bytes=256)

            self.assertLessEqual(len(selected), 12)
            self.assertEqual(selected[0]["type"], "session_meta")
            self.assertIn("FINAL_VERIFICATION_OK", json.dumps(selected, ensure_ascii=False))
            self.assertEqual(stats.skipped_oversized_tool_lines, 1)
            self.assertEqual(stats.total_lines, len(records))

    def test_bounded_reader_drains_generic_oversized_line_and_keeps_next_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "generic-long.jsonl"
            huge = json.dumps({"type": "user", "message": {"content": "x" * 5000}}).encode()
            final = json.dumps(
                {"type": "assistant", "message": {"content": "FINAL_AFTER_GENERIC_LONG_LINE"}}
            ).encode()
            path.write_bytes(huge + b"\n" + final + b"\n")
            selected, stats = ds.read_jsonl_with_stats(path, max_lines=5, max_tool_line_bytes=128)
            self.assertEqual(stats.skipped_oversized_lines, 1)
            self.assertIn("FINAL_AFTER_GENERIC_LONG_LINE", json.dumps(selected))


class AdapterTests(unittest.TestCase):
    def test_claude_top_level_content_fixture_is_supported(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "claude_top_level_transcript.jsonl"
        records = ds.read_jsonl(fixture, 20)
        result = ds.summarize_records(
            fixture,
            "claude-code",
            records,
            ["验收"],
            [],
            source_variant="claude_transcript",
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.agent_context["human_event_count"], 1)
        self.assertIn("顶层 transcript", result.topic_title)
        self.assertNotIn("SYNTHETIC_TOOL_OUTPUT", " ".join(result.evidence_snippets))
    def test_claude_tool_result_is_not_counted_as_human(self) -> None:
        records = [
            {
                "type": "user",
                "sessionId": "claude-1",
                "timestamp": "2026-07-18T01:00:00Z",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "content": "TOOL_ONLY_SECRET 怎么升级 skill"}
                    ],
                },
            },
            {
                "type": "user",
                "sessionId": "claude-1",
                "timestamp": "2026-07-18T01:01:00Z",
                "message": {"role": "user", "content": "请沉淀这套证据工作流"},
            },
            {
                "type": "assistant",
                "timestamp": "2026-07-18T01:02:00Z",
                "message": {"role": "assistant", "content": "已完成方法论整理"},
            },
        ]
        result = ds.summarize_records(
            Path("/tmp/claude.jsonl"),
            "claude-code",
            records,
            ["证据"],
            [],
            source_variant="claude_project",
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.agent_context["human_event_count"], 1)
        self.assertNotIn("TOOL_ONLY_SECRET", result.topic_title)
        self.assertNotIn("TOOL_ONLY_SECRET", " ".join(result.evidence_snippets))

    def test_codex_mirrored_user_event_is_deduplicated(self) -> None:
        message = [{"type": "input_text", "text": "请升级这个 skill 的验证流程"}]
        records = [
            {"type": "session_meta", "payload": {"id": "codex-1", "cwd": "/tmp"}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": message[0]["text"]}},
            {
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": message},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "验证完成"}],
                },
            },
        ]
        result = ds.summarize_records(
            Path("/tmp/codex.jsonl"), "codex", records, [], [], source_variant="codex_active"
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.source, "codex")
        self.assertEqual(result.source_variant, "codex_active")
        self.assertEqual(result.agent_context["human_event_count"], 1)
        self.assertEqual(result.agent_context["deduplicated_text_events"], 1)

    def test_repeated_feedback_after_assistant_reply_is_retained(self) -> None:
        records = [
            {"type": "session_meta", "payload": {"id": "codex-repeat", "cwd": "/tmp"}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": "请补充失败回退"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "已经补充"}],
                },
            },
            {"type": "event_msg", "payload": {"type": "user_message", "message": "请补充失败回退"}},
        ]
        result = ds.summarize_records(
            Path("/tmp/codex-repeat.jsonl"), "codex", records, [], [], source_variant="codex_active"
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.agent_context["human_event_count"], 2)
        self.assertEqual(result.agent_context["deduplicated_text_events"], 0)

    def test_codex_discovers_active_and_archived_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            active = home / ".codex" / "sessions" / "2026" / "07" / "active.jsonl"
            archived = home / ".codex" / "archived_sessions" / "archived.jsonl"
            active.parent.mkdir(parents=True)
            archived.parent.mkdir(parents=True)
            active.write_text("{}\n", encoding="utf-8")
            archived.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(ds.Path, "home", return_value=home):
                items = ds.discover_source_transcripts({"codex"}, None, False)
            self.assertEqual({item.path for item in items}, {active, archived})
            self.assertEqual(
                {item.source_variant for item in items}, {"codex_active", "codex_archived"}
            )

    def test_transcripts_exempt_from_recent_cutoff(self) -> None:
        """transcripts 总量小、豁免 recent cutoff；projects 老 mtime 仍被过滤。"""
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            projects_old = home / ".claude" / "projects" / "slug" / "old.jsonl"
            transcript_old = home / ".claude" / "transcripts" / "ses_old.jsonl"
            projects_old.parent.mkdir(parents=True)
            transcript_old.parent.mkdir(parents=True)
            projects_old.write_text("{}\n", encoding="utf-8")
            transcript_old.write_text("{}\n", encoding="utf-8")
            old_ts = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
            os.utime(projects_old, (old_ts, old_ts))
            os.utime(transcript_old, (old_ts, old_ts))
            cutoff = datetime(2026, 7, 1, tzinfo=timezone.utc)
            with mock.patch.object(ds.Path, "home", return_value=home):
                items = ds.discover_source_transcripts({"claude-code"}, cutoff, False)
            paths = {item.path for item in items}
            self.assertIn(transcript_old, paths)
            self.assertNotIn(projects_old, paths)

    def test_extract_message_text_strips_framework_injection(self) -> None:
        """框架注入（system-reminder/CRON_TASK/observed_from_primary_session）被剥离，不进下游。"""
        msg = {
            "type": "user",
            "message": {"content": [
                {"type": "text", "text": "<system-reminder>hidden instructions</system-reminder>真实用户输入"},
                {"type": "text", "text": "<CRON_TASK cronTaskId=\"x\">task prompt</CRON_TASK>"},
                {"type": "text", "text": "<observed_from_primary_session><what_happened>Read</what_happened><occurred_at>2026-05-06</occurred_at></observed_from_primary_session>"},
                {"type": "text", "text": "干净文本"},
            ]},
        }
        texts = ds.extract_claude_text(msg)
        joined = "\n".join(texts)
        self.assertNotIn("<system-reminder>", joined)
        self.assertNotIn("CRON_TASK", joined)
        self.assertNotIn("observed_from_primary_session", joined)
        self.assertNotIn("what_happened", joined)
        self.assertNotIn("hidden instructions", joined)
        self.assertIn("真实用户输入", joined)
        self.assertIn("干净文本", joined)
        self.assertTrue(all(t.strip() for t in texts))

    def test_extract_decisions_pulls_decision_sentences(self) -> None:
        """decisions 按决策 cue 词切句抽取，不再是 3 条硬编码模板。"""
        texts = [
            "这一段是普通描述，没有决策语义。",
            "我决定把检测阈值从0.45改为0.55，采用合并而非新建。",
            "问个问题？这不算决策。",
            "最终选定 backfill 驱动。",
        ]
        decisions = ds.extract_decisions(texts)
        joined = " ".join(decisions)
        self.assertTrue(len(decisions) >= 2)
        self.assertTrue(any("决定" in d or "改为" in d for d in decisions))
        self.assertTrue(any("选定" in d or "最终" in d for d in decisions))
        self.assertNotIn("问个问题？这不算决策", joined)
        self.assertNotIn("普通描述", joined)

    def test_extract_decisions_excludes_conversational_and_vague(self) -> None:
        """decisions 排除对话碎片：句首口语词+短 / vague 对话词 / "精确"误匹配"确定"。"""
        texts = [
            "我读这些，给最终结论。",  # conversational 句首"我" + 短
            "你确定它已经能查看到所有 session 了吗",  # vague "你确定"
            "精确定位（行号又偏移了）。",  # "精确"含"确定"子串，但无真 cue
            "我先定位文档在哪，决定落点。",  # vague "在哪"
        ]
        decisions = ds.extract_decisions(texts)
        joined = " ".join(decisions)
        self.assertNotIn("我读这些", joined)
        self.assertNotIn("你确定", joined)
        self.assertNotIn("精确", joined)
        self.assertNotIn("在哪", joined)

    def test_evidence_snippets_samples_across_session(self) -> None:
        """命中数 > limit 时等间距抽样，覆盖头/尾（不只前几条）。"""
        texts = [f"方法论 信号 {i}" for i in range(20)]  # 20 条命中 signal
        result = ds.evidence_snippets(texts, limit=4)
        self.assertEqual(len(result), 4)
        joined = " ".join(result)
        self.assertIn("信号 0", joined)   # 头部命中
        self.assertIn("信号 15", joined)  # 等间距末点（索引 15 > 前 4，证明跨时段）

    def test_source_variant_for_codex_quarantine(self) -> None:
        """Codex _quarantine 隔离区标 codex_quarantine（v1.1.3 补盲区）。"""
        from pathlib import Path
        quar = Path.home() / ".codex" / "_quarantine" / "sub" / "x.jsonl"
        self.assertEqual(ds.source_variant_for_path("codex", quar), "codex_quarantine")
        active = Path.home() / ".codex" / "sessions" / "2026" / "08" / "x.jsonl"
        self.assertEqual(ds.source_variant_for_path("codex", active), "codex_active")
        archived = Path.home() / ".codex" / "archived_sessions" / "x.jsonl"
        self.assertEqual(ds.source_variant_for_path("codex", archived), "codex_archived")

    def test_stable_session_dedupe_prefers_active_codex(self) -> None:
        archived = summary("same", ["alpha"], source_variant="codex_archived")
        active = summary("same", ["alpha"], source_variant="codex_active")
        selected, count = ds.dedupe_session_summaries([archived, active])
        self.assertEqual(count, 1)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].source_variant, "codex_active")


class SkillCandidateCatalogTests(unittest.TestCase):
    def test_inventory_skill_outside_core_is_matchable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            inventory = Path(temporary) / "skill-inventory.json"
            inventory.write_text(
                json.dumps(
                    {
                        "skills": [
                            {
                                "skill_key": "hearing-minutes:abc123",
                                "id": "hearing-minutes",
                                "name": "庭审纪要专家",
                                "description": "把庭审录音整理成争议焦点和待办清单",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            core = {
                "core_skills": [
                    {
                        "id": "self-evolve",
                        "display_name": "Self Evolve",
                        "domain_keywords": ["自迭代"],
                        "priority": "high",
                    }
                ]
            }
            with mock.patch.object(ds, "load_yaml", return_value=core):
                _, candidates, status = ds.collect_core_skill_data(
                    inventory_path=inventory,
                    portraits_path=Path(temporary) / "missing-portraits.json",
                )
            self.assertEqual(status["status"], "inventory_complete")
            self.assertEqual([item["id"] for item in candidates], ["hearing-minutes"])
            self.assertEqual(
                ds.match_related_skills("请使用庭审纪要专家整理今天的录音", candidates),
                ["hearing-minutes"],
            )

    def test_missing_inventory_reports_core_only_degraded_mode(self) -> None:
        core = {
            "core_skills": [
                {"id": "self-evolve", "domain_keywords": ["自迭代"], "priority": "high"}
            ]
        }
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(ds, "load_yaml", return_value=core):
                _, candidates, status = ds.collect_core_skill_data(
                    inventory_path=Path(temporary) / "missing.json",
                    portraits_path=Path(temporary) / "missing-portraits.json",
                )
        self.assertEqual(status["status"], "core_fallback")
        self.assertEqual(status["candidate_scope"], "core_only_degraded")
        self.assertEqual([item["id"] for item in candidates], ["self-evolve"])


class SelectionAndCacheTests(unittest.TestCase):
    def test_since_all_selects_unbounded_history(self) -> None:
        self.assertIsNone(ds.parse_since("all"))

    def test_content_fingerprint_detects_same_size_same_mtime_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            transcript = Path(temporary) / "session.jsonl"
            transcript.write_text("alpha\n", encoding="utf-8")
            first = ds.transcript_fingerprint(transcript)
            original_mtime_ns = transcript.stat().st_mtime_ns
            transcript.write_text("bravo\n", encoding="utf-8")
            os.utime(transcript, ns=(original_mtime_ns, original_mtime_ns))
            second = ds.transcript_fingerprint(transcript)
            self.assertEqual(first["transcript_size"], second["transcript_size"])
            self.assertNotEqual(first["transcript_fingerprint"], second["transcript_fingerprint"])

    def test_global_cap_reserves_each_source(self) -> None:
        candidates = [
            (float(100 - index), ds.SourceTranscript("claude-code", "claude_project", Path(f"/c/{index}")))
            for index in range(10)
        ]
        candidates.append((1.0, ds.SourceTranscript("codex", "codex_active", Path("/x/only"))))
        selected, _ = ds.select_with_source_quota(candidates, 4)
        self.assertEqual(len(selected), 4)
        self.assertEqual({item.source for _, item in selected}, {"claude-code", "codex"})

    def test_source_quota_never_exceeds_tiny_or_zero_budget(self) -> None:
        candidates = [
            (10.0, ds.SourceTranscript("claude-code", "claude_project", Path("/c/1"))),
            (9.0, ds.SourceTranscript("codex", "codex_active", Path("/x/1"))),
        ]
        selected_one, limited_one = ds.select_with_source_quota(candidates, 1)
        self.assertEqual(len(selected_one), 1)
        self.assertEqual(len(limited_one), 1)
        selected_zero, limited_zero = ds.select_with_source_quota(candidates, 0)
        self.assertEqual(selected_zero, [])
        self.assertEqual(len(limited_zero), 2)

    def test_recent_mode_reuses_unchanged_summary_without_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            transcript = Path(temporary) / "session.jsonl"
            transcript.write_text("{}\n", encoding="utf-8")
            cached = summary("cached", ["alpha"])
            cached.transcript_path = str(transcript)
            cached.ended_at = datetime.now(timezone.utc).isoformat()
            fingerprint = ds.transcript_fingerprint(transcript)
            cached.transcript_mtime = fingerprint["transcript_mtime"]
            cached.transcript_size = fingerprint["transcript_size"]
            cached.transcript_fingerprint = fingerprint["transcript_fingerprint"]
            existing = {
                str(transcript): {"path": "/summary.json", "summary_mtime": 1, "data": asdict(cached)}
            }
            args = argparse.Namespace(
                since="14d",
                sources="codex",
                index_mode="recent",
                include_subagents=False,
                max_sessions=10,
                max_lines_per_session=20,
            )
            source = ds.SourceTranscript("codex", "codex_active", transcript)
            with (
                mock.patch.object(ds, "discover_source_transcripts", return_value=[source]),
                mock.patch.object(ds, "build_existing_summary_index", return_value=existing),
                mock.patch.object(ds, "read_jsonl_with_stats", side_effect=AssertionError("must not read")),
            ):
                items, index = ds.build_summaries(args, [], [])
            self.assertEqual([item.session_id for item in items], ["cached"])
            self.assertEqual(index["sources"]["codex"]["reused_unchanged"], 1)


class RuntimeIndexTransactionTests(unittest.TestCase):
    def test_recent_and_backfill_batches_merge_without_overwriting_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = (
                ds.SESSION_SUMMARY_DIR,
                ds.DREAMING_DIR,
                ds.DREAM_RUN_DIR,
                ds.BACKFILL_STATE_PATH,
            )
            try:
                configure_runtime_roots(root)
                first_a = summary("a", ["alpha-specific", "shared-specific"])
                first_b = summary("b", ["alpha-specific", "shared-specific"])
                first_a.topic_title = "a-old"
                _, _, first_clusters = ds.update_runtime_indexes(
                    [first_a, first_b], {"sources": {}}, index_args("recent"), "run-1"
                )
                first_cluster = first_clusters[0]

                updated_a = summary("a", ["alpha-specific", "shared-specific"])
                updated_a.topic_title = "a-updated"
                new_c = summary("c", ["alpha-specific", "shared-specific"])
                paths, merged, clusters = ds.update_runtime_indexes(
                    [updated_a, new_c], {"sources": {}}, index_args("backfill"), "run-2"
                )

                self.assertEqual({item.session_id for item in merged}, {"a", "b", "c"})
                self.assertEqual(
                    next(item.topic_title for item in merged if item.session_id == "a"),
                    "a-updated",
                )
                persisted = json.loads(Path(paths["session_index"]).read_text(encoding="utf-8"))
                self.assertEqual({item["session_id"] for item in persisted}, {"a", "b", "c"})
                timeline = json.loads(Path(paths["timeline_index"]).read_text(encoding="utf-8"))
                self.assertEqual(timeline["session_count"], 3)
                self.assertEqual(timeline["index_scope"], "merged_history")
                self.assertEqual(sum(len(item.sessions) for item in clusters), 3)
                self.assertEqual(clusters[0].cluster_id, first_cluster.cluster_id)
                self.assertEqual(clusters[0].topic_key, first_cluster.topic_key)
                self.assertNotEqual(clusters[0].member_digest, first_cluster.member_digest)
                self.assertNotEqual(clusters[0].revision, first_cluster.revision)
                source_index = json.loads(Path(paths["source_index"]).read_text(encoding="utf-8"))
                self.assertEqual(
                    source_index["merge"],
                    {
                        "batch_session_count": 2,
                        "merged_session_count": 3,
                        "added_session_count": 1,
                        "updated_session_count": 1,
                        "preserved_session_count": 1,
                    },
                )
            finally:
                (
                    ds.SESSION_SUMMARY_DIR,
                    ds.DREAMING_DIR,
                    ds.DREAM_RUN_DIR,
                    ds.BACKFILL_STATE_PATH,
                ) = original

    @unittest.skipUnless(hasattr(multiprocessing, "get_context"), "multiprocessing unavailable")
    def test_two_processes_cannot_lose_each_others_index_update(self) -> None:
        try:
            context = multiprocessing.get_context("fork")
        except ValueError:
            self.skipTest("fork context unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            ready = context.Event()
            processes = [
                context.Process(target=concurrent_index_writer, args=(temporary, item, ready))
                for item in ("parallel-a", "parallel-b")
            ]
            for process in processes:
                process.start()
            ready.set()
            for process in processes:
                process.join(timeout=20)
                self.assertEqual(process.exitcode, 0)
            persisted = json.loads(
                (Path(temporary) / "dreaming" / "session-index.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                {item["session_id"] for item in persisted}, {"parallel-a", "parallel-b"}
            )
            self.assertFalse(
                list((Path(temporary) / "dreaming").glob(".session-index.json.*"))
            )


class BackfillRetryTests(unittest.TestCase):
    def test_failed_summary_keeps_backfill_incomplete_and_is_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transcript = root / "retry.jsonl"
            transcript.write_text("{}\n", encoding="utf-8")
            source = ds.SourceTranscript("codex", "codex_active", transcript)
            args = argparse.Namespace(
                sources="codex",
                include_subagents=False,
                backfill_order="newest-first",
                backfill_batch_size=2,
                backfill_refresh_existing=False,
                reset_backfill=True,
                max_lines_per_session=20,
            )
            original = (
                ds.SESSION_SUMMARY_DIR,
                ds.DREAMING_DIR,
                ds.DREAM_RUN_DIR,
                ds.BACKFILL_STATE_PATH,
            )
            try:
                configure_runtime_roots(root)
                with (
                    mock.patch.object(ds, "discover_source_transcripts", return_value=[source]),
                    mock.patch.object(ds, "build_existing_summary_index", return_value={}),
                    mock.patch.object(ds, "summarize_records", return_value=None),
                ):
                    first, first_index = ds.build_backfill_summaries(args, [], [], "retry-1")
                self.assertEqual(first, [])
                self.assertEqual(first_index["backfill"]["retry_pending"], 1)
                self.assertIn(str(transcript), first_index["backfill"]["failed_paths"])

                args.reset_backfill = False
                recovered = summary("retry-session", ["retry-specific"])
                recovered.transcript_path = str(transcript)
                with (
                    mock.patch.object(ds, "discover_source_transcripts", return_value=[source]),
                    mock.patch.object(ds, "build_existing_summary_index", return_value={}),
                    mock.patch.object(ds, "summarize_records", return_value=recovered),
                ):
                    second, second_index = ds.build_backfill_summaries(args, [], [], "retry-2")
                # 熔断：已标 failed 的 transcript 第二次被跳过，不再无限重试死循环
                self.assertEqual(second, [])
                self.assertEqual(second_index["backfill"]["skipped_failed"], 1)
                self.assertEqual(second_index["backfill"]["indexed"], 0)
            finally:
                (
                    ds.SESSION_SUMMARY_DIR,
                    ds.DREAMING_DIR,
                    ds.DREAM_RUN_DIR,
                    ds.BACKFILL_STATE_PATH,
                ) = original

    def test_summarize_records_transcripts_empty_texts_returns_placeholder(self) -> None:
        """transcripts 无 user/assistant text 时（OpenClaw/web 工具调用为主）仍返回 placeholder，让索引覆盖 42/42。"""
        records = [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]
        summary = ds.summarize_records(
            path=Path("/tmp/test.jsonl"),
            source="claude-code",
            records=records,
            core_keywords=[],
            skills=[],
            source_variant="claude_transcript",
        )
        self.assertIsNotNone(summary)
        self.assertEqual(summary.source_variant, "claude_transcript")
        # 其他 source 也产 placeholder（v1.1.1 扩展 v0.9.0 transcripts 宽容到所有 source）
        summary_other = ds.summarize_records(
            path=Path("/tmp/test.jsonl"),
            source="claude-code",
            records=records,
            core_keywords=[],
            skills=[],
            source_variant="claude_project",
        )
        self.assertIsNotNone(summary_other)
        self.assertEqual(summary_other.summary_policy, "index_only")
        self.assertIn("empty_texts_metadata_only", summary_other.noise_reasons)

    def test_compute_coverage_metrics(self) -> None:
        """覆盖率对账：raw_total/unindexed_total/coverage_ratio。"""
        mock_items = [mock.Mock(path=f"/p/{i}") for i in range(10)]
        existing = {f"/p/{i}": {} for i in range(7)}
        with mock.patch.object(ds, "discover_source_transcripts", return_value=mock_items):
            metrics = ds.compute_coverage_metrics({"claude-code"}, False, existing)
        self.assertEqual(metrics["raw_total"], 10)
        self.assertEqual(metrics["unindexed_total"], 3)
        self.assertEqual(metrics["coverage_ratio"], 70.0)


class ClusteringTests(unittest.TestCase):
    def test_centroid_and_minimum_gate_prevent_bridge_snowball(self) -> None:
        a = summary("a", ["alpha", "shared-one", "shared-two"])
        b = summary("b", ["alpha", "shared-one", "shared-two", "bridge"])
        c = summary("c", ["bridge", "shared-two", "gamma"])
        clusters = ds.build_clusters([a, b, c], min_similarity=0.35)
        sizes = sorted(len(cluster.sessions) for cluster in clusters)
        self.assertEqual(sizes, [1, 2])
        self.assertTrue(all(cluster.cohesion_minimum >= 0 for cluster in clusters))

    def test_cluster_id_is_stable_across_input_order(self) -> None:
        first = summary("a", ["alpha", "shared"])
        second = summary("b", ["alpha", "shared"])
        ids_one = [item.cluster_id for item in ds.build_clusters([first, second], 0.4)]
        ids_two = [item.cluster_id for item in ds.build_clusters([second, first], 0.4)]
        self.assertEqual(ids_one, ids_two)

    def test_cluster_id_stays_stable_when_membership_grows(self) -> None:
        a = summary("a", ["alpha", "shared"])
        b = summary("b", ["alpha", "shared"])
        c = summary("c", ["alpha", "shared"])
        initial = ds.build_clusters([a, b], 0.4)[0]
        expanded = ds.build_clusters([a, b, c], 0.4)[0]

        self.assertEqual(expanded.cluster_id, initial.cluster_id)
        self.assertEqual(expanded.topic_key, initial.topic_key)
        self.assertEqual(expanded.semantic_digest, initial.semantic_digest)
        self.assertNotEqual(expanded.member_digest, initial.member_digest)
        self.assertNotEqual(expanded.revision, initial.revision)
        self.assertNotIn(initial.member_digest, initial.cluster_id)

    def test_persisted_lineage_survives_an_earlier_sorting_new_member(self) -> None:
        a = summary("a", ["alpha", "shared"])
        b = summary("b", ["alpha", "shared"])
        c = summary("c", ["alpha", "shared"])
        initial = ds.build_clusters([b, c], 0.4)[0]
        fresh_expansion = ds.build_clusters([a, b, c], 0.4)[0]
        reconciled = ds.build_clusters(
            [a, b, c],
            0.4,
            previous_clusters=ds.serialize_clusters([initial]),
        )[0]

        self.assertNotEqual(fresh_expansion.cluster_id, initial.cluster_id)
        self.assertEqual(reconciled.cluster_id, initial.cluster_id)
        self.assertEqual(reconciled.topic_key, initial.topic_key)
        self.assertNotEqual(reconciled.revision, initial.revision)

    def test_legacy_member_bound_id_is_migrated_to_auditable_alias(self) -> None:
        a = summary("a", ["alpha", "shared"])
        b = summary("b", ["alpha", "shared"])
        c = summary("c", ["alpha", "shared"])
        initial = ds.build_clusters([a, b], 0.4)[0]
        legacy_id = (
            f"clu-{initial.semantic_digest[:8]}-{initial.member_digest[:12]}-"
            f"{ds.safe_slug(initial.title)}"
        )
        legacy_record = ds.serialize_clusters([initial])[0]
        legacy_record["cluster_id"] = legacy_id
        for field in (
            "id_schema",
            "topic_key",
            "semantic_digest",
            "member_digest",
            "revision",
            "legacy_cluster_ids",
        ):
            legacy_record.pop(field, None)

        migrated = ds.build_clusters(
            [a, b, c],
            0.4,
            previous_clusters=[legacy_record],
        )[0]
        serialized = ds.serialize_clusters([migrated])[0]

        self.assertEqual(migrated.cluster_id, initial.cluster_id)
        self.assertNotEqual(migrated.cluster_id, legacy_id)
        self.assertEqual(migrated.legacy_cluster_ids, [legacy_id])
        self.assertEqual(serialized["id_schema"], ds.CLUSTER_ID_SCHEMA)
        self.assertEqual(serialized["legacy_cluster_ids"], [legacy_id])

    def test_quality_gate_requires_cohesion_and_evidence(self) -> None:
        first = summary("a", ["alpha", "shared"])
        second = summary("b", ["alpha", "shared"])
        first.evidence_snippets = ["用户要求沉淀 alpha 验收流程"]
        second.evidence_snippets = ["alpha 验收已在第二次会话复现"]
        cluster = ds.build_clusters([first, second], 0.4)[0]
        self.assertEqual(cluster.quality_gate, "deep_eligible")
        self.assertGreaterEqual(cluster.purity, 0.55)
        self.assertLessEqual(cluster.uncertainty, 0.7)

    def test_merge_similar_clusters_combines_high_centroid_pairs(self) -> None:
        """质心相似度超阈的两个具体词簇应合并为一。"""
        ca = ds.TopicCluster(
            cluster_id="ca", title="ca",
            sessions=[summary("a1", ["alpha-specific", "shared-specific"]),
                      summary("a2", ["alpha-specific", "shared-specific"])],
        )
        cb = ds.TopicCluster(
            cluster_id="cb", title="cb",
            sessions=[summary("b1", ["alpha-specific", "shared-specific"]),
                      summary("b2", ["alpha-specific", "shared-specific"])],
        )
        merged = ds._merge_similar_clusters([ca, cb], min_similarity=0.4, cluster_cap=24)
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0].sessions), 4)

    def test_merge_skips_generic_clusters(self) -> None:
        """泛词簇不合并（防桥接雪球）。"""
        g1 = ds.TopicCluster(cluster_id="g1", title="g1", sessions=[summary("g1a", ["工作流", "模板"])])
        g2 = ds.TopicCluster(cluster_id="g2", title="g2", sessions=[summary("g2a", ["工作流", "复用"])])
        merged = ds._merge_similar_clusters([g1, g2], min_similarity=0.4, cluster_cap=24)
        self.assertEqual(len(merged), 2)

    def test_merge_respects_cluster_cap(self) -> None:
        """合并后不超 cluster_cap（保护大簇确定性分片）。"""
        sessions_a = [summary(f"a{i}", ["alpha-specific", "shared-specific"]) for i in range(20)]
        sessions_b = [summary(f"b{i}", ["alpha-specific", "shared-specific"]) for i in range(20)]
        ca = ds.TopicCluster(cluster_id="ca", title="ca", sessions=sessions_a)
        cb = ds.TopicCluster(cluster_id="cb", title="cb", sessions=sessions_b)
        merged = ds._merge_similar_clusters([ca, cb], min_similarity=0.4, cluster_cap=24)
        self.assertEqual(len(merged), 2)

    def test_choose_cluster_title_requires_two_generic_hits(self) -> None:
        """单泛词命中不再强制同名（收紧，避免异质簇被改名掩盖成同标题副本）。"""
        cluster_one = ds.TopicCluster(
            cluster_id="c1", title="c1",
            sessions=[summary(f"s{i}", ["error"]) for i in range(10)],
        )
        cluster_one.topic_keywords = ["error", "alpha-specific"]
        self.assertNotEqual(
            ds.choose_cluster_title(cluster_one), "法律 Skill 运维与内容沉淀聚合"
        )
        cluster_two = ds.TopicCluster(
            cluster_id="c2", title="c2",
            sessions=[summary(f"t{i}", ["error"]) for i in range(10)],
        )
        cluster_two.topic_keywords = ["error", "失败", "OCR"]
        self.assertEqual(
            ds.choose_cluster_title(cluster_two), "法律 Skill 运维与内容沉淀聚合"
        )

    def test_hundred_generic_sessions_do_not_form_giant_cluster(self) -> None:
        sessions = [summary(f"generic-{index:03d}", ["工作流", "模板", "复用"]) for index in range(120)]
        clusters = ds.build_clusters(sessions, 0.35)
        self.assertEqual(max(len(cluster.sessions) for cluster in clusters), 1)
        self.assertTrue(all(cluster.score <= 100 for cluster in clusters))
        self.assertEqual(len({cluster.cluster_id for cluster in clusters}), 120)

    def test_large_coherent_cluster_is_deterministically_sharded_and_score_capped(self) -> None:
        sessions = [summary(f"specific-{index:03d}", ["alpha-specific", "shared-specific"]) for index in range(120)]
        clusters = ds.build_clusters(sessions, 0.4)
        reversed_clusters = ds.build_clusters(list(reversed(sessions)), 0.4)
        self.assertEqual(len(clusters), 5)
        self.assertEqual(sum(len(cluster.sessions) for cluster in clusters), 120)
        self.assertTrue(all(len(cluster.sessions) <= ds.DEFAULT_MAX_CLUSTER_SIZE for cluster in clusters))
        self.assertTrue(all(cluster.cohesion_minimum >= 0.7 for cluster in clusters))
        self.assertTrue(all(cluster.score <= 100 for cluster in clusters))
        self.assertEqual(len({cluster.topic_key for cluster in clusters}), 1)
        self.assertEqual(len({cluster.cluster_id for cluster in clusters}), 5)
        self.assertEqual(len({cluster.member_digest for cluster in clusters}), 5)
        self.assertEqual(
            [cluster.cluster_id for cluster in clusters],
            [cluster.cluster_id for cluster in reversed_clusters],
        )

    def test_cluster_size_cap_is_configurable(self) -> None:
        sessions = [summary(f"cap-{index:02d}", ["cap-specific", "shared-specific"]) for index in range(11)]
        clusters = ds.build_clusters(sessions, 0.4, max_cluster_size=4)
        self.assertEqual(sorted(len(cluster.sessions) for cluster in clusters), [3, 4, 4])


class DeepDreamTests(unittest.TestCase):
    def test_preview_and_failure_preserve_last_successful_deep_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status_root = Path(temporary) / "status"
            with mock.patch.object(dd, "STATUS_ROOT", status_root):
                available = dd.persist_deep_attempt(
                    {
                        "cluster_id": "stable-cluster",
                        "analysis_status": "available",
                        "artifact_ref": "review/inbox/deep-analysis/stable.md",
                        "proposal_ids": ["prp-stable"],
                        "updated_at": "2026-07-18 12:00:00",
                    },
                    success=True,
                )
                preview = dd.prepared(
                    "stable-cluster", Path("stable-cluster.json")
                )
                failure = dd.unavailable("stable-cluster", "claude_cli_failed")

            durable = json.loads(
                (status_root / "stable-cluster.json").read_text(encoding="utf-8")
            )
            self.assertEqual(available["analysis_status"], "available")
            self.assertEqual(preview["analysis_status"], "prepared")
            self.assertEqual(failure["analysis_status"], "analysis_unavailable")
            self.assertTrue(preview["last_success_available"])
            self.assertTrue(failure["last_success_available"])
            self.assertEqual(durable["analysis_status"], "available")
            self.assertEqual(
                durable["artifact_ref"], "review/inbox/deep-analysis/stable.md"
            )
            self.assertEqual(durable["proposal_ids"], ["prp-stable"])
            self.assertEqual(
                durable["last_attempt"]["analysis_status"], "analysis_unavailable"
            )
            self.assertEqual(
                durable["last_success"]["artifact_ref"],
                "review/inbox/deep-analysis/stable.md",
            )

    def test_direct_cli_rejects_non_finite_and_unbounded_budgets(self) -> None:
        for flag, value in (
            ("--max-budget-usd", "nan"),
            ("--max-budget-usd", "inf"),
            ("--max-budget-usd", "-inf"),
            ("--max-budget-usd", "1000"),
            ("--per-call-budget-usd", "inf"),
            ("--per-call-budget-usd", "10"),
        ):
            with self.subTest(flag=flag, value=value), mock.patch.object(
                sys, "argv", ["deep_dream.py", flag, value]
            ), mock.patch("sys.stderr"):
                with self.assertRaises(SystemExit) as raised:
                    dd.main()
                self.assertEqual(raised.exception.code, 2)

    def test_per_call_budget_cannot_exceed_total_budget(self) -> None:
        argv = [
            "deep_dream.py",
            "--max-budget-usd",
            "0.05",
            "--per-call-budget-usd",
            "0.10",
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(dd, "assert_runtime_ready"),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(dd.main(), 2)

    def test_load_clusters_accepts_wrapped_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "clusters.json"
            path.write_text(json.dumps({"clusters": [{"cluster_id": "c1"}]}), encoding="utf-8")
            self.assertEqual(dd.load_clusters(path), [{"cluster_id": "c1"}])

    def test_catalog_exposes_current_core_but_not_old_hash_enhanced_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory_path = root / "skill-inventory.json"
            portraits_path = root / "skill-portraits.json"
            current_hash = "b" * 64
            inventory_path.write_text(
                json.dumps(
                    {
                        "skills": [
                            {
                                "skill_key": "demo:abc",
                                "id": "demo",
                                "name": "demo",
                                "version": "1.2.3",
                                "content_hash": current_hash,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            core = {
                "capability": "当前核心能力",
                "inputs": [],
                "outputs": [],
                "depends_on": [],
                "can_chain_to": [],
                "not_for": [],
            }
            portraits_path.write_text(
                json.dumps(
                    {
                        "portraits": {
                            "demo:abc": {
                                "content_hash": current_hash,
                                "core": core,
                                "stale": False,
                                "last_error": "enhanced_distill_failed",
                                "enhanced": {
                                    "distilled_at": 1,
                                    "triggers": ["旧触发词"],
                                    "field_metadata": {
                                        "triggers": {
                                            "content_hash": "a" * 64,
                                            "distilled_at": 1,
                                        }
                                    },
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            catalog = dd.load_skill_catalog(inventory_path, portraits_path)

            current = json.loads(catalog[0]["current_text"])["portrait"]
            self.assertEqual(core, current["core"])
            self.assertEqual({}, current["enhanced"])

    def test_catalog_filters_enhanced_fields_independently_and_fails_closed_for_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory_path = root / "skill-inventory.json"
            portraits_path = root / "skill-portraits.json"
            current_hash = "c" * 64
            inventory_path.write_text(
                json.dumps(
                    {
                        "skills": [
                            {
                                "skill_key": "demo:abc",
                                "id": "demo",
                                "content_hash": current_hash,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            portraits_path.write_text(
                json.dumps(
                    {
                        "portraits": {
                            "demo:abc": {
                                "content_hash": current_hash,
                                "core": None,
                                "stale": True,
                                "enhanced": {
                                    "triggers": ["当前触发词"],
                                    "extension_points": ["未绑定的旧字段"],
                                    "field_metadata": {
                                        "triggers": {
                                            "content_hash": current_hash,
                                            "distilled_at": 2,
                                        }
                                    },
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            catalog = dd.load_skill_catalog(inventory_path, portraits_path)

            current = json.loads(catalog[0]["current_text"])["portrait"]
            self.assertIsNone(current["core"])
            self.assertEqual({"triggers": ["当前触发词"]}, current["enhanced"])

    def test_structured_result_rejects_unknown_evidence_id(self) -> None:
        payload = {
            "cluster_id": "c1",
            "analysis_status": "available",
            "summary": "摘要",
            "observations": [{"claim": "观察", "evidence_ids": ["ev-unknown"]}],
            "counter_evidence": [{"point": "反证", "evidence_ids": ["ev-1"]}],
            "upgrade_candidates": [],
            "uncertainties": ["样本有限"],
        }
        self.assertIsNone(dd.parse_cli_result(json.dumps(payload), "c1", {"ev-1"}))

    def test_structured_result_rejects_noncanonical_target_skill(self) -> None:
        payload = {
            "cluster_id": "c1",
            "analysis_status": "available",
            "summary": "摘要",
            "observations": [{"claim": "观察", "evidence_ids": ["ev-1"]}],
            "counter_evidence": [{"point": "反证", "evidence_ids": ["ev-1"]}],
            "upgrade_candidates": [
                {
                    "target_skill": "demo",
                    "change_points": ["新增审批"],
                    "rationale": "重复需求",
                    "evidence_ids": ["ev-1"],
                    "acceptance_tests": ["可追溯"],
                }
            ],
            "uncertainties": ["样本有限"],
        }
        self.assertIsNone(
            dd.parse_cli_result(json.dumps(payload), "c1", {"ev-1"}, {"demo:abc"})
        )

    def test_optional_deep_command_has_all_safety_and_budget_flags(self) -> None:
        packet = {
            "cluster_id": "c1",
            "evidence": [{"evidence_id": "ev-1", "text": "脱敏证据"}],
        }
        valid = {
            "cluster_id": "c1",
            "analysis_status": "available",
            "summary": "摘要",
            "observations": [{"claim": "观察", "evidence_ids": ["ev-1"]}],
            "counter_evidence": [{"point": "反证", "evidence_ids": ["ev-1"]}],
            "upgrade_candidates": [],
            "uncertainties": ["样本有限"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            packet_path = Path(temporary) / "packet.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            completed = mock.Mock(returncode=0, stdout=json.dumps({"structured_output": valid}))
            with (
                mock.patch.object(dd.shutil, "which", return_value="/usr/bin/claude"),
                mock.patch.object(dd.subprocess, "run", return_value=completed) as runner,
            ):
                result, reason = dd.run_claude(
                    packet_path, "claude", 30, model="sonnet", max_budget_usd=0.25
                )
            self.assertEqual(reason, "")
            self.assertIsNotNone(result)
            command = runner.call_args.args[0]
            for flag in (
                "--safe-mode",
                "--disable-slash-commands",
                "--strict-mcp-config",
                "--mcp-config",
                "--json-schema",
                "--tools",
                "--no-session-persistence",
                "--model",
                "--max-budget-usd",
            ):
                self.assertIn(flag, command)

    def test_target_resolution_uses_inventory_version_hash_and_current_portrait(self) -> None:
        catalog = [
            {
                "skill_key": "demo:abc",
                "id": "demo",
                "name": "demo",
                "version": "1.2.3",
                "content_hash": "a" * 64,
                "current_text": "支持批量核验与稳定指纹",
            }
        ]
        target, resolution = dd.resolve_target(catalog, "demo")
        self.assertEqual(resolution, "resolved")
        self.assertEqual(target["version"], "1.2.3")
        self.assertTrue(dd.current_state_covers(["支持批量核验与稳定指纹"], target))
        self.assertFalse(dd.current_state_covers(["全新审批工作流"], target))

    def test_process_cluster_binds_proposal_to_inventory_state(self) -> None:
        cluster = {
            "cluster_id": "c1",
            "quality_gate": "deep_eligible",
            "evidence": [
                {
                    "evidence_id": "ev-1",
                    "source_session_id_hash": "1" * 16,
                    "text": "重复出现新的验收诉求",
                }
            ],
            "sessions": [],
        }
        analysis = {
            "cluster_id": "c1",
            "analysis_status": "available",
            "summary": "摘要",
            "observations": [{"claim": "观察", "evidence_ids": ["ev-1"]}],
            "counter_evidence": [{"point": "反证", "evidence_ids": ["ev-1"]}],
            "upgrade_candidates": [
                {
                    "target_skill": "demo",
                    "change_points": ["新增审批工作流"],
                    "rationale": "重复需求",
                    "evidence_ids": ["ev-1"],
                    "acceptance_tests": ["审批事件可追溯"],
                }
            ],
            "uncertainties": ["样本有限"],
        }
        catalog = [
            {
                "skill_key": "demo:abc",
                "id": "demo",
                "name": "demo",
                "version": "1.2.3",
                "content_hash": "b" * 64,
                "current_text": "当前只支持基础索引",
            }
        ]
        args = argparse.Namespace(
            execute=True,
            claude_bin="claude",
            timeout=30,
            model="sonnet",
            max_budget_usd=0.25,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = mock.Mock()
            store.upsert.return_value = (
                {"proposal_id": "prp-0123456789abcdef", "machine_disposition": "candidate"},
                True,
            )
            with (
                mock.patch.object(dd, "PACKET_ROOT", root / "packets"),
                mock.patch.object(dd, "STATUS_ROOT", root / "status"),
                mock.patch.object(dd, "DEEP_OUTPUT_ROOT", root / "inbox"),
                mock.patch.object(dd, "load_skill_catalog", return_value=catalog),
                mock.patch.object(dd, "run_claude", return_value=(analysis, "")),
                mock.patch.object(
                    dd,
                    "write_review_artifact",
                    return_value={
                        "status": "published",
                        "content_sha256": "c" * 64,
                        "destination": "deep-analysis/c-deep-analysis-cccccccccccccccc.md",
                    },
                ),
                mock.patch.object(dd, "ProposalStore", return_value=store),
            ):
                result = dd.process_cluster(cluster, args)
        self.assertEqual(result["analysis_status"], "available")
        kwargs = store.upsert.call_args.kwargs
        self.assertEqual(kwargs["target_version"], "1.2.3")
        self.assertEqual(kwargs["target_content_sha256"], "b" * 64)
        self.assertEqual(kwargs["target_resolution"], "resolved")
        self.assertEqual(kwargs["machine_disposition"], "candidate")
        self.assertEqual(
            kwargs["artifact_paths"],
            ["review/inbox/deep-analysis/c-deep-analysis-cccccccccccccccc.md"],
        )

    def test_covered_candidate_is_not_written_as_actionable_proposal(self) -> None:
        cluster = {
            "cluster_id": "c-covered",
            "quality_gate": "deep_eligible",
            "evidence": [{"evidence_id": "ev-1", "text": "支持批量核验与稳定指纹"}],
            "sessions": [],
        }
        analysis = {
            "cluster_id": "c-covered",
            "analysis_status": "available",
            "summary": "摘要",
            "observations": [{"claim": "观察", "evidence_ids": ["ev-1"]}],
            "counter_evidence": [{"point": "反证", "evidence_ids": ["ev-1"]}],
            "upgrade_candidates": [
                {
                    "target_skill": "demo:abc",
                    "change_points": ["支持批量核验与稳定指纹"],
                    "rationale": "已覆盖",
                    "evidence_ids": ["ev-1"],
                    "acceptance_tests": ["保持现状"],
                }
            ],
            "uncertainties": ["样本有限"],
        }
        catalog = [
            {
                "skill_key": "demo:abc",
                "id": "demo",
                "name": "demo",
                "version": "1.2.3",
                "content_hash": "b" * 64,
                "current_text": "支持批量核验与稳定指纹",
            }
        ]
        args = argparse.Namespace(
            execute=True, claude_bin="claude", timeout=30, model="sonnet", max_budget_usd=0.10
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = mock.Mock()
            with (
                mock.patch.object(dd, "PACKET_ROOT", root / "packets"),
                mock.patch.object(dd, "STATUS_ROOT", root / "status"),
                mock.patch.object(dd, "DEEP_OUTPUT_ROOT", root / "inbox"),
                mock.patch.object(dd, "load_skill_catalog", return_value=catalog),
                mock.patch.object(dd, "run_claude", return_value=(analysis, "")),
                mock.patch.object(
                    dd,
                    "write_review_artifact",
                    return_value={
                        "status": "published",
                        "content_sha256": "c" * 64,
                        "destination": "deep-analysis/c-covered_deep-analysis-cccccccccccccccc.md",
                    },
                ),
                mock.patch.object(dd, "ProposalStore", return_value=store),
            ):
                result = dd.process_cluster(cluster, args)
        store.upsert.assert_not_called()
        self.assertEqual(result["proposal_ids"], [])
        self.assertEqual(result["proposal_gates"][0]["machine_disposition"], "covered")

    def test_execute_reserves_global_budget_and_fails_when_all_unavailable(self) -> None:
        clusters = [
            {"cluster_id": f"c-{index}", "quality_gate": "deep_eligible"}
            for index in range(4)
        ]
        unavailable_result = {"analysis_status": "analysis_unavailable", "reason": "cli_missing"}
        argv = [
            "deep_dream.py",
            "--execute",
            "--max-clusters",
            "4",
            "--max-budget-usd",
            "0.25",
            "--per-call-budget-usd",
            "0.10",
            "--max-calls",
            "5",
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(dd, "assert_runtime_ready"),
            mock.patch.object(dd, "load_clusters", return_value=clusters),
            mock.patch.object(dd, "process_cluster", return_value=unavailable_result) as process,
            mock.patch.object(dd, "unavailable", return_value=unavailable_result),
            mock.patch("builtins.print"),
        ):
            exit_code = dd.main()
        self.assertEqual(exit_code, 2)
        self.assertEqual(process.call_count, 2)


class GenerateCompatibilityTests(unittest.TestCase):
    def test_generate_publishes_only_deterministic_packets(self) -> None:
        item = summary("a", ["alpha", "shared"])
        cluster = ds.build_clusters([item], 0.4)[0]
        args = argparse.Namespace(since="14d", mode="generate", min_cluster_size=1, max_reports=2)
        captured: list[str] = []

        def fake_publish(destination: Path, content: str, **_: object) -> dict[str, object]:
            captured.append(content)
            return {"status": "published", "destination": str(destination), "content_sha256": "a" * 64}

        with mock.patch.object(ds, "write_review_artifact", side_effect=fake_publish):
            result = ds.write_reports([item], [cluster], args)
        self.assertEqual(result["analysis_layer"], "deterministic_index")
        self.assertEqual(result["upgrade_directions"], [])
        self.assertEqual(result["articles"], [])
        self.assertEqual(result["context_updates"], [])
        self.assertNotIn("核心方法论（一句话）", "\n".join(captured))


class RawBackupTests(unittest.TestCase):
    """raw-backup 双保险：dream_sweep 写 summary 时同步 cp 原文到 RAW_SESSIONS_DIR。

    CC 默认 cleanupPeriodDays 会删除旧会话原文，DATA_ROOT 里的 raw 副本是原文
    消失后的字节级留存（summary 是结构化留存，raw 是无损留存，互为双保险）。
    """

    def _item(self, src: Path, *, source_variant: str = "claude_project") -> ds.SessionSummary:
        item = summary(
            "raw-backup-session",
            ["raw-backup-marker"],
            source="claude-code",
            source_variant=source_variant,
        )
        item.transcript_path = str(src)
        item.started_at = "2026-08-08 10:00:00"
        item.evidence_snippets = ["raw-backup evidence"]
        return item

    def test_archive_writes_copy_to_variant_month_bucket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            configure_runtime_roots(Path(tmp))
            src = Path(tmp) / "abc123.jsonl"
            payload = '{"v":1}\n{"v":2}\n'
            src.write_text(payload, encoding="utf-8")
            self.assertEqual(ds.archive_raw_session(self._item(src)), "archived")
            dest = ds.RAW_SESSIONS_DIR / "claude_project" / "2608" / "abc123.jsonl"
            self.assertTrue(dest.exists())
            self.assertEqual(dest.read_text(encoding="utf-8"), payload)
            # 原子写：无 .tmp 残留
            self.assertEqual(list(ds.RAW_SESSIONS_DIR.rglob("*.tmp")), [])

    def test_archive_skipped_when_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            configure_runtime_roots(Path(tmp))
            src = Path(tmp) / "abc.jsonl"
            src.write_text("payload\n", encoding="utf-8")
            ds.archive_raw_session(self._item(src))
            dest = ds.RAW_SESSIONS_DIR / "claude_project" / "2608" / "abc.jsonl"
            mtime_before = dest.stat().st_mtime
            self.assertEqual(ds.archive_raw_session(self._item(src)), "skipped")
            self.assertEqual(dest.stat().st_mtime, mtime_before)

    def test_archive_updated_when_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            configure_runtime_roots(Path(tmp))
            src = Path(tmp) / "abc.jsonl"
            src.write_text("short\n", encoding="utf-8")
            ds.archive_raw_session(self._item(src))
            src.write_text("short\nappended much longer content here\n", encoding="utf-8")
            self.assertEqual(ds.archive_raw_session(self._item(src)), "updated")
            dest = ds.RAW_SESSIONS_DIR / "claude_project" / "2608" / "abc.jsonl"
            self.assertIn("appended", dest.read_text(encoding="utf-8"))

    def test_archive_source_missing_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            configure_runtime_roots(Path(tmp))
            self.assertEqual(
                ds.archive_raw_session(self._item(Path(tmp) / "nope.jsonl")),
                "source_missing",
            )
            self.assertEqual(list(ds.RAW_SESSIONS_DIR.rglob("*")), [])

    def test_archive_routes_transcripts_to_separate_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            configure_runtime_roots(Path(tmp))
            src = Path(tmp) / "ses_xyz.jsonl"
            src.write_text("transcript\n", encoding="utf-8")
            self.assertEqual(
                ds.archive_raw_session(self._item(src, source_variant="claude_transcript")),
                "archived",
            )
            self.assertTrue(
                (ds.RAW_SESSIONS_DIR / "claude_transcript" / "2608" / "ses_xyz.jsonl").exists()
            )
            # projects 与 transcripts 分目录，互不串台
            self.assertFalse((ds.RAW_SESSIONS_DIR / "claude_project").exists())

    def test_update_runtime_indexes_records_raw_backup_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            configure_runtime_roots(Path(tmp))
            src = Path(tmp) / "live.jsonl"
            src.write_text("live payload\n", encoding="utf-8")
            paths, _, _ = ds.update_runtime_indexes(
                [self._item(src)],
                {"task_id": "raw-task", "sources": {}},
                index_args("recent"),
                "run-raw",
            )
            with open(paths["source_index"], encoding="utf-8") as handle:
                idx = json.load(handle)
            self.assertEqual(idx["raw_backup"], {"archived": 1})
            self.assertTrue(
                (ds.RAW_SESSIONS_DIR / "claude_project" / "2608" / "live.jsonl").exists()
            )


class SubagentCollectionTests(unittest.TestCase):
    """subagent 采集：标 claude_subagent variant + 不进聚类（仍索引 + raw-backup 原文）
    + 去重让位主会话。subagent 是主会话子任务，内容重叠主会话，进聚类只会 flood。"""

    def test_source_variant_for_subagent_path(self):
        sub_path = Path.home() / ".claude" / "projects" / "slug" / "subagents" / "sub-abc.jsonl"
        self.assertEqual(ds.source_variant_for_path("claude-code", sub_path), "claude_subagent")
        main_path = Path.home() / ".claude" / "projects" / "slug" / "abc.jsonl"
        self.assertEqual(ds.source_variant_for_path("claude-code", main_path), "claude_project")
        transcript_path = Path.home() / ".claude" / "transcripts" / "ses_x.jsonl"
        self.assertEqual(ds.source_variant_for_path("claude-code", transcript_path), "claude_transcript")

    def test_cluster_candidate_excludes_subagent_even_if_summarize_candidate(self):
        sub = summary("sub-1", ["x"], source="claude-code", source_variant="claude_subagent")
        sub.summary_policy = "summarize_candidate"
        self.assertFalse(ds.cluster_candidate(sub))
        main = summary("main-1", ["x"], source="claude-code", source_variant="claude_project")
        main.summary_policy = "summarize_candidate"
        self.assertTrue(ds.cluster_candidate(main))

    def test_dedupe_prefers_main_over_subagent_same_session_id(self):
        sub = summary("dup-1", ["x"], source="claude-code", source_variant="claude_subagent")
        sub.selected_record_count = 100
        main = summary("dup-1", ["x"], source="claude-code", source_variant="claude_project")
        main.selected_record_count = 10
        result, _dup = ds.dedupe_session_summaries([sub, main])
        variants = [item.source_variant for item in result]
        self.assertIn("claude_project", variants)
        self.assertNotIn("claude_subagent", variants)


if __name__ == "__main__":
    unittest.main()
