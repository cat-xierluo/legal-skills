"""Offline contract/CLI tests. Every file and state directory is isolated."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import reuse_assessment as reuse
from opportunity import validate_card


class ReuseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "SKILL.md").write_text("Local contract: JSON frames, measured timing, Python. Missing scene validation.")
        self.candidate = {"candidate_key": "direction-a", "project_id": "dynamic-new-skill",
                          "skill_path": str(self.root), "repo": "sample/upstream", "repo_id": 42,
                          "repo_revision": "r1", "evidence_revision": "e1", "target_revision": "t1",
                          "capability": {"key": "scene-validation"},
                          "evidence_summary": {"readme": "JSON frames; measured timing; Python; MIT code; assets excluded; no service. Validate scenes by invariant.",
                                               "source": "cache", "observed": {"head": False}}}
        self.packet = reuse.prepare(self.candidate, self.root)
        self.review = {"binding": self.packet["binding"], "packet_sha256": self.packet["packet_sha256"],
                       "proposals": [{"id": "a", "category": "method_only", "mechanism": "Scene invariant validation",
                                      "transfer_type": "rule_only", "checks": {"mechanism": self.check("pass", "upstream"),
                                                                                "local_gap": self.check("pass", "local")}}]}

    def check(self, status, *sides):
        return {"status": status, "claim": "Agent semantic assessment of the cited contract",
                "refs": [{"source": s["id"], "sha256": s["sha256"], "excerpt": s["text"]}
                         for s in self.packet["sources"] if s["side"] in sides]}

    def result(self):
        return reuse.evaluate(self.packet, self.review)["proposals"][0]

    def test_dynamic_prepare_preserves_binding_and_cache_limits(self):
        self.assertEqual(self.packet["binding"]["target_revision"], "t1")
        self.assertEqual(self.packet["sources"][1]["anchor"]["carried_source"], "cache")
        self.assertEqual(self.packet["sources"][1]["anchor"]["observed"], {"head": False})
        self.assertIn("not per-field", self.packet["sources"][1]["anchor"]["freshness"])
        self.assertEqual(reuse.validate_packet(self.packet)["local-skill"]["text"], (self.root / "SKILL.md").read_text())

    def test_method_rule_only_experiment_ceiling(self):
        self.assertEqual(self.result()["category"], "method_only")
        self.assertEqual(self.result()["max_decision_status"], "experiment_proposed")

    def test_unknown_is_deferred_not_rejected_or_pass(self):
        self.review["proposals"][0]["checks"].pop("local_gap")
        self.assertEqual(self.result()["category"], "needs_evidence")
        self.assertEqual(self.result()["max_decision_status"], "deferred")

    def test_missing_reference_or_wrong_excerpt_is_error(self):
        for mutation in ("missing", "excerpt", "sha"):
            with self.subTest(mutation=mutation):
                review = copy.deepcopy(self.review)
                check = review["proposals"][0]["checks"]["mechanism"]
                if mutation == "missing":
                    check["refs"] = []
                else:
                    check["refs"][0]["excerpt" if mutation == "excerpt" else "sha256"] = "fabricated"
                with self.assertRaises(ValueError):
                    reuse.evaluate(self.packet, review)

    def test_method_transfer_requires_relevant_license(self):
        item = self.review["proposals"][0]
        for kind, name in (("code", "license_code"), ("asset", "license_assets"), ("interface", "license_service")):
            item["transfer_type"] = kind
            self.assertEqual(self.result()["category"], "needs_evidence")
            item["checks"][name] = self.check("pass", "upstream")
            self.assertEqual(self.result()["category"], "method_only")
        item["transfer_type"] = "entire_repository"
        with self.assertRaises(ValueError):
            self.result()

    def test_strong_requires_both_contracts_and_layered_license(self):
        item = self.review["proposals"][0]
        item["category"] = "backend_candidate"
        item["checks"] = {name: self.check("pass", "local", "upstream") for name in reuse.CHECKS}
        self.assertEqual(self.result()["category"], "backend_candidate")
        item["checks"]["runtime"] = self.check("pass", "upstream")
        self.assertEqual(self.result()["category"], "needs_evidence")
        item["checks"]["runtime"] = self.check("pass", "local", "upstream")
        item["checks"]["license_assets"] = {"status": "unknown"}
        self.assertIn("license_assets", self.result()["next_evidence"])

    def test_not_applicable_requires_counterexample_on_both_sides(self):
        item = self.review["proposals"][0]
        item["category"] = "not_applicable"
        item["checks"] = {"delivery": {"status": "unknown"}}
        self.assertEqual(self.result()["category"], "needs_evidence")
        item["checks"]["delivery"] = self.check("fail", "local", "upstream")
        self.assertEqual(self.result()["category"], "not_applicable")

    def test_independent_methods_same_repository(self):
        failed = {"id": "b", "category": "not_applicable", "checks": {"delivery": self.check("fail", "local", "upstream")}}
        self.review["proposals"].append(failed)
        self.assertEqual([x["category"] for x in reuse.evaluate(self.packet, self.review)["proposals"]],
                         ["method_only", "not_applicable"])

    def test_unknown_revision_and_cross_review_binding(self):
        self.candidate["evidence_revision"] = None
        packet = reuse.prepare(self.candidate, self.root)
        review = {**self.review, "binding": packet["binding"], "packet_sha256": packet["packet_sha256"]}
        self.assertEqual(reuse.evaluate(packet, review)["proposals"][0]["category"], "needs_evidence")
        with self.assertRaises(ValueError):
            reuse.evaluate(packet, self.review)

    def test_packet_and_recomputed_result_cannot_be_overridden(self):
        report = reuse.make_report(self.packet, self.review)
        report["result"]["proposals"][0]["category"] = "capability_package"
        with self.assertRaises(ValueError):
            reuse.validate_report(report)
        packet = copy.deepcopy(self.packet)
        packet["sources"][0]["text"] += " tampered"
        with self.assertRaises(ValueError):
            reuse.evaluate(packet, self.review)

    def card(self):
        report = reuse.make_report(self.packet, self.review)
        path = self.root / "report.json"
        path.write_text(json.dumps(report))
        b = self.packet["binding"]
        return {"candidate_key": b["candidate_key"],
                "signal": {**{k: b[k] for k in ("repo", "repo_id", "repo_revision", "evidence_revision")}, "source": "daily"},
                "target": {**{k: b[k] for k in ("project_id", "target_revision", "capability_key", "skill_path", "skill_sha256")},
                           "capability": "Scene validation"},
                "evidence": {"url": "https://github.com/sample/upstream", "readme_claim": "scene invariants"},
                "gap": "验证缺口", "hypothesis": "Validate scenes", "experiment": "Compare an invalid scene",
                "decision": {"status": "experiment_proposed"}, "reuse_category": "method_only",
                "reuse_assessment": {"path": "report.json", "sha256": reuse.sha(path.read_bytes()), "proposal_id": "a"}}

    def test_card_real_report_and_legacy_compatibility(self):
        card = self.card()
        self.assertTrue(validate_card(card, self.root)[0])
        del card["reuse_assessment"]
        self.assertTrue(validate_card(card, self.root)[0])

    def test_card_rejects_missing_sha_cross_binding_and_recomputed_category(self):
        baseline = self.card()
        for field in ("missing", "sha", "project_id", "repo_revision", "evidence_revision", "target_revision", "capability_key", "candidate_key", "category"):
            with self.subTest(field=field):
                card = copy.deepcopy(baseline)
                if field == "missing": card["reuse_assessment"]["path"] = "missing.json"
                elif field == "sha": card["reuse_assessment"]["sha256"] = "0" * 64
                elif field == "candidate_key": card[field] = "another"
                elif field == "category": card["reuse_category"] = "capability_package"
                elif field in ("repo_revision", "evidence_revision"): card["signal"][field] = "another"
                else: card["target"][field] = "another"
                self.assertFalse(validate_card(card, self.root)[0])

    def test_source_cannot_be_added_by_editing_report_and_rehashing(self):
        packet = copy.deepcopy(self.packet)
        packet["sources"][1]["text"] = "invented contract"
        packet["sources"][1]["sha256"] = reuse.sha(b"invented contract")
        packet["packet_sha256"] = reuse.digest({k: v for k, v in packet.items() if k != "packet_sha256"})
        review = {**self.review, "packet_sha256": packet["packet_sha256"]}
        with self.assertRaises(ValueError):
            reuse.evaluate(packet, review)

    def test_missing_report_and_unknown_decision_remain_controlled(self):
        card = self.card()
        card["target"] = "invalid"
        self.assertFalse(validate_card(card, self.root)[0])
        card = self.card()
        self.review["proposals"][0]["checks"] = {}
        report = reuse.make_report(self.packet, self.review)
        path = self.root / "report.json"
        path.write_text(json.dumps(report))
        card["reuse_assessment"]["sha256"] = reuse.sha(path.read_bytes())
        card["reuse_category"] = "needs_evidence"
        self.assertFalse(validate_card(card, self.root)[0])
        card["decision"] = {"status": "deferred", "reason": "入口未声明真实缺口，待核"}
        self.assertTrue(validate_card(card, self.root)[0])

    def test_report_does_not_replace_tested_evidence(self):
        card = self.card()
        card["decision"]["status"] = "tested"
        self.assertFalse(validate_card(card, self.root)[0])

    def test_recorded_relative_report_survives_directory_move(self):
        card = self.card()
        source = self.root / "card.json"
        source.write_text(json.dumps(card))
        state = self.root / "state"
        command = [sys.executable, str(SCRIPTS / "opportunity.py")]
        recorded = subprocess.run(command + ["record", "--input", str(source), "--data-dir", str(state)], capture_output=True, text=True)
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        saved = Path(json.loads(recorded.stdout)["path"])
        validated = subprocess.run(command + ["validate", "--input", str(saved)], cwd=state, capture_output=True, text=True)
        self.assertEqual(validated.returncode, 0, validated.stdout)
        self.assertTrue(Path(json.loads(saved.read_text())["reuse_assessment"]["path"]).is_absolute())

    def test_invalid_report_feedback_is_not_consumed_and_reopens_judged(self):
        import auto_discover as ad
        from datetime import datetime, timezone
        for invalidation in ("missing", "hash", "recompute"):
            with self.subTest(invalidation=invalidation):
                card = self.card()
                card["reuse_assessment"]["path"] = str(self.root / "report.json")
                source = self.root / "card.json"
                source.write_text(json.dumps(card))
                state = self.root / invalidation
                recorded = subprocess.run([sys.executable, str(SCRIPTS / "opportunity.py"), "record", "--input", str(source), "--data-dir", str(state)], capture_output=True, text=True)
                self.assertEqual(recorded.returncode, 0, recorded.stderr)
                saved = Path(json.loads(recorded.stdout)["path"])
                b = self.packet["binding"]
                entry = {"project_id": b["project_id"], "repo_id": b["repo_id"], "repo": b["repo"], "capability_key": b["capability_key"],
                         "last_repo_revision": b["repo_revision"], "last_evidence_revision": b["evidence_revision"], "last_target_revision": b["target_revision"],
                         "state": "shown", "last_shown_at": "2026-10-26T00:00:00Z", "shown_count": 1}
                candidate_snapshot = {"repos": [{"id": b["repo_id"], "full_name": b["repo"],
                    "description": "video scene validation", "_repo_revision": b["repo_revision"],
                    "_evidence_revision": b["evidence_revision"], "_capability_hints": [{
                        "capability_key": b["capability_key"], "concepts": ["video"],
                        "source": "readme", "anchor": "e1", "text": "video"}]}]}
                profiles = [{"project_id": b["project_id"], "skill_path": b["skill_path"],
                    "target_revision": b["target_revision"], "activity": {"commits": 0},
                    "description": "video validation", "search_terms": ["video"], "primary_terms": ["video"]}]
                feedback, warnings = ad.feedback_index(state)
                self.assertTrue(feedback)
                rows, _, _ = ad.prepare(candidate_snapshot, profiles, feedback, datetime.now(timezone.utc))
                self.assertEqual(rows, [])
                entries = {b["candidate_key"]: entry}
                ad.judge_entries(entries, feedback, datetime.now(timezone.utc))
                self.assertEqual(entry["state"], "judged")
                report_path = self.root / "report.json"
                if invalidation == "missing": report_path.unlink()
                elif invalidation == "hash": report_path.write_text(report_path.read_text() + " ")
                else:
                    report = json.loads(report_path.read_text())
                    report["result"]["proposals"][0]["category"] = "capability_package"
                    report_path.write_text(json.dumps(report))
                    stored = json.loads(saved.read_text())
                    stored["reuse_assessment"]["sha256"] = reuse.sha(report_path.read_bytes())
                    saved.write_text(json.dumps(stored))
                feedback, warnings = ad.feedback_index(state)
                self.assertFalse(feedback)
                self.assertTrue(any("reuse_assessment" in warning for warning in warnings))
                ad.atomic_json(state / ad.QUEUE_FILE, {"schema_version": ad.QUEUE_SCHEMA, "entries": entries, "cursor": {}})
                reconciled = subprocess.run([sys.executable, str(SCRIPTS / "auto_discover.py"), "reconcile", "--data-dir", str(state)], capture_output=True, text=True)
                self.assertEqual(reconciled.returncode, 0, reconciled.stderr)
                result = json.loads(reconciled.stdout)
                self.assertEqual(result["newly_judged_count"], 0)
                self.assertEqual(ad.read_json(state / ad.QUEUE_FILE)["entries"][b["candidate_key"]]["state"], "shown")
                self.assertTrue(result["warnings"])
                rows, _, _ = ad.prepare(candidate_snapshot, profiles, feedback, datetime.now(timezone.utc))
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["capability"]["key"], b["capability_key"])
                never_shown = {**entry, "state": "judged", "judged_ref": saved.name, "last_shown_at": None}
                ad.judge_entries({"unshown": never_shown}, feedback, datetime.now(timezone.utc))
                self.assertEqual(never_shown["state"], "pending")
                # An independent valid legacy decision still covers the entry.
                legacy = json.loads(saved.read_text())
                legacy.pop("reuse_assessment")
                ad.atomic_json(state / "feedback" / "legacy.json", legacy)
                covered, _ = ad.feedback_index(state)
                ad.judge_entries(entries, covered, datetime.now(timezone.utc))
                self.assertEqual(entry["state"], "judged")
                self.assertEqual(entry["judged_ref"], "legacy.json")

    def test_oversized_report_is_rejected_before_hash_read(self):
        from unittest.mock import patch
        card = self.card()
        path = self.root / "report.json"
        with path.open("wb") as stream:
            stream.truncate(reuse.MAX_BYTES + 1)
        with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded hash read")):
            ok, errors, _ = validate_card(card, self.root)
        self.assertFalse(ok)
        self.assertTrue(any("budget" in error for error in errors))

    def test_cli_prepare_daily_and_evaluate_and_controlled_failure(self):
        run = self.root / "run.json"
        run.write_text(json.dumps({"items": [self.candidate]}))
        packet = self.root / "packet.json"
        cmd = [sys.executable, str(SCRIPTS / "reuse_assessment.py")]
        prepared = subprocess.run(cmd + ["prepare", "--run", str(run), "--candidate-key", "direction-a", "--skill-path", str(self.root), "--output", str(packet)], capture_output=True, text=True)
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        review = self.root / "review.json"
        review.write_text(json.dumps(self.review))
        output = self.root / "report.json"
        evaluated = subprocess.run(cmd + ["evaluate", "--packet", str(packet), "--review", str(review), "--output", str(output)], capture_output=True, text=True)
        self.assertEqual(evaluated.returncode, 0, evaluated.stderr)
        self.assertEqual(json.loads(output.read_text())["result"]["proposals"][0]["category"], "method_only")
        failed = subprocess.run(cmd + ["prepare", "--run", str(run), "--candidate-key", "missing", "--skill-path", str(self.root), "--output", str(packet)], capture_output=True, text=True)
        self.assertEqual(failed.returncode, 2)
        self.assertNotIn("Traceback", failed.stderr)


if __name__ == "__main__":
    unittest.main()
