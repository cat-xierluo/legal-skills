#!/usr/bin/env python3

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from validate_release import validate_candidate


SKILL_ROOT = Path(__file__).resolve().parent.parent


class ValidateReleaseTest(unittest.TestCase):
    def test_current_candidate_passes(self) -> None:
        self.assertEqual(validate_candidate(SKILL_ROOT), [])

    def test_archive_payload_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / SKILL_ROOT.name
            shutil.copytree(SKILL_ROOT, candidate, ignore=shutil.ignore_patterns("__pycache__"))
            payload = candidate / "archive" / "真实材料.pdf"
            payload.parent.mkdir(parents=True, exist_ok=True)
            payload.write_bytes(b"%PDF-1.4")
            findings = validate_candidate(candidate)
            self.assertTrue(any(item["rule"] == "ARCHIVE_PAYLOAD" for item in findings))

    def test_ds_store_is_blocked_in_non_git_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / SKILL_ROOT.name
            shutil.copytree(
                SKILL_ROOT,
                candidate,
                ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"),
            )
            (candidate / ".DS_Store").write_bytes(b"finder metadata")
            findings = validate_candidate(candidate)
            self.assertTrue(any(item["rule"] == "BANNED_FILE" for item in findings))

    def test_privacy_anchors_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / SKILL_ROOT.name
            shutil.copytree(
                SKILL_ROOT,
                candidate,
                ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"),
            )
            payload = candidate / "examples" / "privacy.txt"
            synthetic_case_number = "".join(("（", "2026", "）", "沪01民初", "1234", "号"))
            synthetic_legacy_id = "".join(("110101", "900101", "001"))
            payload.write_text(
                "示例机构：某某有限公司\n内部记录：DEC-123\n联系：someone@example.com\n"
                f"座机：{''.join(('010', '12345678'))}\n旧证件：{synthetic_legacy_id}\n案号：{synthetic_case_number}\n"
                "账号：wxid_example_001\n",
                encoding="utf-8",
            )
            findings = validate_candidate(candidate)
            rules = {item["rule"] for item in findings}
            self.assertIn("PRIVACY_ORGANIZATION", rules)
            self.assertIn("PRIVACY_INTERNAL_ID", rules)
            self.assertIn("PRIVACY_EMAIL", rules)
            self.assertIn("PRIVACY_LANDLINE", rules)
            self.assertIn("PRIVACY_LEGACY_ID_NUMBER", rules)
            self.assertIn("PRIVACY_CASE_NUMBER", rules)
            self.assertIn("PRIVACY_WECHAT_ID", rules)

    def test_url_files_are_scanned_for_privacy_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / SKILL_ROOT.name
            shutil.copytree(
                SKILL_ROOT,
                candidate,
                ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"),
            )
            payload = candidate / "examples" / "privacy.url"
            payload.write_text("备注：wxid_example_001\n", encoding="utf-8")
            findings = validate_candidate(candidate)
            self.assertTrue(any(item["rule"] == "PRIVACY_WECHAT_ID" for item in findings))


if __name__ == "__main__":
    unittest.main()
