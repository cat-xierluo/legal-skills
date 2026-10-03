"""纯合成证据测试，不访问法院平台或真实案件。"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from check_service_evidence import assess_service


def valid_record():
    return {
        "document_id": "DEMO-RULING", "recipient_id": "DEMO-RECIPIENT",
        "service_basis": {"checked": True, "ref": "demo/consent.pdf#page=1"},
        "conflict_checked": True, "has_conflict": False,
        "evidence": [{"kind": "court_delivery_receipt", "event": "delivered",
                      "date": "2026-09-30", "document_ids": ["DEMO-RULING"],
                      "recipient_id": "DEMO-RECIPIENT", "checked": True,
                      "ref": "demo/receipt.pdf#page=1"}],
    }


class ServiceEvidenceTests(unittest.TestCase):
    def assert_pending(self, record, reason=None):
        result = assess_service(record)
        self.assertEqual(result["status"], "pending")
        self.assertIsNone(result["served_on"])
        if reason:
            self.assertEqual(result["reason"], reason)

    def test_valid_receipt(self):
        self.assertEqual(assess_service(valid_record())["served_on"], "2026-09-30")

    def test_actual_success_event(self):
        r = valid_record()
        r["evidence"][0].update(kind="court_system_record", event="sent_success")
        self.assertEqual(assess_service(r)["status"], "confirmed")

    def test_recipient_arrival_evidence(self):
        r = valid_record()
        r["evidence"][0].update(kind="recipient_arrival_proof", event="arrived")
        self.assertEqual(assess_service(r)["status"], "confirmed")

    def test_explicit_multi_document_receipt(self):
        r = valid_record()
        r["evidence"][0]["document_ids"].append("DEMO-NOTICE")
        self.assertEqual(assess_service(r)["status"], "confirmed")

    def test_qr_issue_sms_and_download_times_are_not_service(self):
        for kind in ("document_qrcode_time", "document_issue_date", "sms_gateway",
                     "download_time", "unknown"):
            with self.subTest(kind=kind):
                r = valid_record()
                r["evidence"][0]["kind"] = kind
                self.assert_pending(r, "no_qualifying_service_evidence")

    def test_qr_cannot_override_real_receipt(self):
        r = valid_record()
        qr = copy.deepcopy(r["evidence"][0])
        qr.update(kind="document_qrcode_time", date="2026-09-29")
        r["evidence"].append(qr)
        self.assertEqual(assess_service(r)["served_on"], "2026-09-30")

    def test_other_document_cannot_supply_date(self):
        r = valid_record()
        r["evidence"][0]["document_ids"] = ["DEMO-NOTICE"]
        self.assert_pending(r, "document_or_recipient_mismatch")

    def test_other_recipient_cannot_supply_date(self):
        r = valid_record()
        r["evidence"][0]["recipient_id"] = "DEMO-OTHER"
        self.assert_pending(r, "document_or_recipient_mismatch")

    def test_basis_missing_or_unchecked(self):
        for basis in (None, {}, {"checked": "true", "ref": "demo"},
                      {"checked": True, "ref": " "}):
            r = valid_record()
            r["service_basis"] = basis
            self.assert_pending(r)

    def test_conflict_must_be_explicitly_checked(self):
        for key, value in (("conflict_checked", False), ("conflict_checked", "true"),
                           ("has_conflict", True), ("has_conflict", None)):
            r = valid_record()
            r[key] = value
            self.assert_pending(r, "conflict_unresolved")

    def test_conflicting_dates_remain_pending(self):
        r = valid_record()
        other = copy.deepcopy(r["evidence"][0])
        other.update(date="2026-10-01", ref="demo/other.pdf")
        r["evidence"].append(other)
        self.assert_pending(r, "conflicting_service_dates")

    def test_creation_event_rejected(self):
        r = valid_record()
        r["evidence"][0]["event"] = "created"
        self.assert_pending(r, "missing_delivery_event_or_ref")

    def test_evidence_unchecked_or_no_reference(self):
        for key, value in (("checked", False), ("checked", 1), ("ref", "")):
            r = valid_record()
            r["evidence"][0][key] = value
            self.assert_pending(r)

    def test_invalid_dates(self):
        for day in ("2026-02-30", "2026-9-30", "2026-09-30T00:00:00Z", None, 20260930):
            r = valid_record()
            r["evidence"][0]["date"] = day
            self.assert_pending(r, "invalid_service_date")

    def test_legacy_sent_at_not_promoted(self):
        self.assert_pending({"sent_at": "2026-09-30", "sent_at_source": "短信网关时间"})

    def test_malformed_records(self):
        for record in (None, [], "text", {}, {"document_id": []}):
            self.assert_pending(record)
        for field, value in (("evidence", {}), ("evidence", [None]), ("evidence", [])):
            r = valid_record()
            r[field] = value
            self.assert_pending(r)

    def test_malformed_evidence(self):
        for field, value in (("kind", []), ("event", []), ("document_ids", "DEMO-RULING"),
                             ("document_ids", []), ("document_ids", [None])):
            r = valid_record()
            r["evidence"][0][field] = value
            self.assert_pending(r)

    def test_input_unchanged(self):
        r = valid_record()
        before = copy.deepcopy(r)
        assess_service(r)
        self.assertEqual(r, before)

    def test_cli_exit_codes(self):
        script = Path(__file__).with_name("check_service_evidence.py")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.json"
            for payload, code in ((json.dumps(valid_record()), 0), ("{}", 2), ("broken", 1)):
                path.write_text(payload, encoding="utf-8")
                p = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True)
                self.assertEqual(p.returncode, code)
                self.assertIn("status", json.loads(p.stdout))


if __name__ == "__main__":
    unittest.main()
