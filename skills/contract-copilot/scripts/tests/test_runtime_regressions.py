from __future__ import annotations

import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


SKILL_ROOT = Path(__file__).resolve().parents[2]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))


class RuntimeRegressionTests(unittest.TestCase):
    def test_docx_xml_editor_injects_timestamp_attributes(self) -> None:
        from scripts.docx.document import DocxXMLEditor

        fixed_timestamp = datetime(2026, 6, 4, 9, 30, tzinfo=timezone.utc)
        xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>party</w:t></w:r></w:p></w:body>"
            "</w:document>"
        )

        with TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "document.xml"
            xml_path.write_text(xml, encoding="utf-8")
            editor = DocxXMLEditor(
                xml_path,
                rsid="12345678",
                author="Reviewer",
                initials="RV",
                timestamp_provider=lambda: fixed_timestamp,
            )

            paragraph = editor.get_node(tag="w:p")
            editor.append_to(paragraph, '<w:ins><w:r><w:t> addition</w:t></w:r></w:ins>')

            inserted = editor.get_node(tag="w:ins")
            expected_timestamp = fixed_timestamp.astimezone().isoformat(
                timespec="seconds"
            )
            self.assertEqual(inserted.getAttribute("w:author"), "Reviewer")
            self.assertEqual(inserted.getAttribute("w:date"), expected_timestamp)
            self.assertEqual(
                inserted.getAttribute("w16du:dateUtc"),
                expected_timestamp,
            )

    def test_apply_review_plan_can_be_run_directly(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/review/apply_review_plan.py",
                "--help",
            ],
            cwd=SKILL_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--input", result.stdout)
        self.assertIn("--plan", result.stdout)

    def test_default_runtime_paths_point_to_skill_root(self) -> None:
        from scripts.review import archive_service, review_runtime

        self.assertEqual(review_runtime.SKILL_ROOT, SKILL_ROOT)
        self.assertEqual(review_runtime.DEFAULT_CONFIG_DIR, SKILL_ROOT / "config")
        self.assertEqual(
            review_runtime.PROFILE_TEMPLATE_PATH,
            SKILL_ROOT / "config" / "reviewer_profile.example.json",
        )
        self.assertEqual(archive_service.SKILL_ROOT, SKILL_ROOT)
        self.assertEqual(archive_service.DEFAULT_ARCHIVE_DIR, SKILL_ROOT / "archive")


if __name__ == "__main__":
    unittest.main()
