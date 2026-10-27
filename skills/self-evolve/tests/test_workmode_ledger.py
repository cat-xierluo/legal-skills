from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import workmode_ledger as wl  # noqa: E402


def packet() -> dict:
    clusters = [
        {
            "cluster_id": "wmp-clu-test1",
            "topic_key": "focus:律师IP制造",
            "title": "专注方向:律师IP制造",
            "session_count": 2,
            "source_session_id_hashes": ["0123456789abcdef", "fedcba9876543210"],
            "evidence": [
                {
                    "evidence_id": "ev-one",
                    "source_session_id_hash": "0123456789abcdef",
                    "text": "本周主要在处理商标侵权案件和合同审查。",
                },
                {
                    "evidence_id": "ev-two",
                    "source_session_id_hash": "fedcba9876543210",
                    "text": "知识产权方向的诉讼准备占了大部分时间。",
                },
            ],
        }
    ]
    return {
        "schema_version": wl.EVIDENCE_SCHEMA,
        "generated_at": "2026-08-10T12:00:00+08:00",
        "source_digest": wl.digest(clusters),
        "clusters": clusters,
        "export_summary": {"cluster_count": 1, "scope_counts": {"focus": 1}},
    }


def model_response(*, evidence_ids=None, scope="focus") -> str:
    return json.dumps(
        {
            "summary": "发现稳定的工作模式偏好",
            "candidates": [
                {
                    "scope": scope,
                    "claim": "用户稳定倾向在知识产权方向投入。",
                    "polarity": "prefer",
                    "evidence_ids": evidence_ids or ["ev-one", "ev-two"],
                    "confidence": 0.92,
                    "suggested_profile_targets": [
                        "iteration_report.focus_sections",
                        "unknown.target",
                    ],
                }
            ],
            "uncertainties": [],
        },
        ensure_ascii=False,
    )


class WorkmodeAnalysisTests(unittest.TestCase):
    def test_tolerant_optional_fields_keep_valid_candidate(self) -> None:
        analysis = wl.analyze_packet(packet(), response_text=model_response())
        self.assertEqual(len(analysis["candidates"]), 1)
        candidate = analysis["candidates"][0]
        self.assertEqual(candidate["support_session_count"], 2)
        self.assertEqual(candidate["scope"], "focus")
        self.assertEqual(
            candidate["suggested_profile_targets"], ["iteration_report.focus_sections"]
        )
        self.assertTrue(wl.CANDIDATE_ID.fullmatch(candidate["candidate_id"]))
        self.assertTrue(wl.REVISION_ID.fullmatch(candidate["revision"]))

    def test_single_session_candidate_is_filtered(self) -> None:
        analysis = wl.analyze_packet(
            packet(), response_text=model_response(evidence_ids=["ev-one"])
        )
        self.assertEqual(analysis["candidates"], [])
        self.assertIn(
            "insufficient_cross_session_support", analysis["filtered"][0]["issues"]
        )

    def test_unknown_scope_is_filtered(self) -> None:
        analysis = wl.analyze_packet(
            packet(), response_text=model_response(scope="content_value")
        )
        self.assertEqual(analysis["candidates"], [])
        self.assertIn("unknown_scope", analysis["filtered"][0]["issues"])

    def test_unknown_evidence_reference_is_filtered(self) -> None:
        analysis = wl.analyze_packet(
            packet(),
            response_text=model_response(evidence_ids=["ev-one", "ev-two", "invented"]),
        )
        self.assertEqual(analysis["candidates"], [])
        self.assertIn("unknown_evidence_reference", analysis["filtered"][0]["issues"])

    def test_receiver_rejects_raw_path(self) -> None:
        value = packet()
        value["clusters"][0]["evidence"][0]["text"] = "/Users/person/case.md"
        value["source_digest"] = wl.digest(value["clusters"])
        with self.assertRaisesRegex(ValueError, "privacy"):
            wl.validate_evidence_packet(value)


class WorkmodeLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.ledger_path = root / "ledger.json"
        self.events_path = root / "events.jsonl"
        self.ledger = wl.WorkmodeLedger(self.ledger_path, self.events_path)
        self.analysis = wl.analyze_packet(packet(), response_text=model_response())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_import_and_revision_bound_decision(self) -> None:
        imported = self.ledger.import_analysis(self.analysis)
        self.assertEqual(imported["imported"], 1)
        candidate = self.ledger.list_candidates("pending")[0]
        accepted = self.ledger.decide(
            candidate["candidate_id"], candidate["revision"], "accepted", "符合专注方向"
        )
        self.assertEqual(accepted["human_decision"], "accepted")
        self.assertEqual(accepted["application"], "not_applied")
        self.assertEqual(accepted["outcome"], "pending")
        self.assertEqual(len(self.ledger.list_candidates("pending")), 0)
        # events.jsonl 仅追加一行
        self.assertEqual(
            len(self.events_path.read_text(encoding="utf-8").splitlines()), 1
        )

    def test_stale_revision_fails_closed(self) -> None:
        self.ledger.import_analysis(self.analysis)
        candidate = self.ledger.list_candidates()[0]
        with self.assertRaisesRegex(ValueError, "revision changed"):
            self.ledger.decide(candidate["candidate_id"], "old-revision", "accepted")

    def test_new_revision_returns_to_pending(self) -> None:
        self.ledger.import_analysis(self.analysis)
        first = self.ledger.list_candidates()[0]
        self.ledger.decide(first["candidate_id"], first["revision"], "accepted")
        revised_packet = packet()
        revised_packet["clusters"][0]["evidence"].append(
            {
                "evidence_id": "ev-three",
                "source_session_id_hash": "0123456789abcdef",
                "text": "不要把商标和专利混在一起处理。",
            }
        )
        revised_packet["source_digest"] = wl.digest(revised_packet["clusters"])
        response = model_response(evidence_ids=["ev-one", "ev-two", "ev-three"])
        revised = wl.analyze_packet(revised_packet, response_text=response)
        self.ledger.import_analysis(revised)
        current = self.ledger.list_candidates()[0]
        self.assertNotEqual(current["revision"], first["revision"])
        self.assertEqual(current["human_decision"], "pending")

    def test_decide_does_not_modify_ledger_body(self) -> None:
        """decide 只追加 events.jsonl,不污染 ledger.json 主体(accepted ≠ applied)。"""
        self.ledger.import_analysis(self.analysis)
        before = hashlib.sha256(self.ledger_path.read_bytes()).hexdigest()
        candidate = self.ledger.list_candidates()[0]
        self.ledger.decide(candidate["candidate_id"], candidate["revision"], "accepted")
        after = hashlib.sha256(self.ledger_path.read_bytes()).hexdigest()
        self.assertEqual(before, after)

    def test_corrupt_event_log_blocks_mutation(self) -> None:
        self.ledger.import_analysis(self.analysis)
        self.events_path.write_text("not-json\n", encoding="utf-8")
        candidate = json.loads(self.ledger_path.read_text(encoding="utf-8"))["candidates"][0]
        with self.assertRaisesRegex(ValueError, "unreadable"):
            self.ledger.decide(candidate["candidate_id"], candidate["revision"], "accepted")

    def test_corrupt_candidate_identity_blocks_projection(self) -> None:
        self.ledger.import_analysis(self.analysis)
        payload = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        payload["candidates"][0]["candidate_id"] = "bad-id<script>"
        self.ledger_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "identity"):
            self.ledger.list_candidates()

    def test_reason_privacy_rejected(self) -> None:
        """decide 的 reason 含原始路径 → 隐私门控拒绝(复用 self-evolve privacy_gate)。"""
        self.ledger.import_analysis(self.analysis)
        candidate = self.ledger.list_candidates()[0]
        with self.assertRaisesRegex(ValueError, "privacy"):
            self.ledger.decide(
                candidate["candidate_id"],
                candidate["revision"],
                "rejected",
                "因为 /Users/person/secret.key 泄露",
            )


if __name__ == "__main__":
    unittest.main()
