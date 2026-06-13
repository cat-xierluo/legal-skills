from __future__ import annotations

import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


SKILL_ROOT = Path(__file__).resolve().parents[2]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))


class RuntimeRegressionTests(unittest.TestCase):
    def _write_minimal_unpacked_docx(
        self,
        root: Path,
        *,
        include_comment_parts: bool = False,
    ) -> None:
        files = {
            "[Content_Types].xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                '<Override PartName="/word/settings.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
                "</Types>"
            ),
            "word/_rels/document.xml.rels": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                "</Relationships>"
            ),
            "word/settings.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "</w:settings>"
            ),
            "word/document.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>"
                "<w:p><w:r><w:t>第一条 合同目的</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>第二条 付款安排</w:t></w:r></w:p>"
                "</w:body>"
                "</w:document>"
            ),
        }
        if include_comment_parts:
            files.update(
                {
                    "word/comments.xml": (
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">'
                        "</w:comments>"
                    ),
                    "word/commentsExtended.xml": (
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<w15:commentsEx xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">'
                        "</w15:commentsEx>"
                    ),
                    "word/commentsIds.xml": (
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<w16cid:commentsIds xmlns:w16cid="http://schemas.microsoft.com/office/word/2016/wordml/cid">'
                        "</w16cid:commentsIds>"
                    ),
                    "word/commentsExtensible.xml": (
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<w16cex:commentsExtensible xmlns:w16cex="http://schemas.microsoft.com/office/word/2018/wordml/cex">'
                        "</w16cex:commentsExtensible>"
                    ),
                }
            )

        for relative_path, content in files.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

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
                fixed_timestamp.astimezone(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
            )

    def test_add_comment_creates_missing_comment_extensible_part(self) -> None:
        from scripts.docx.reviewer import ContractReviewer

        fixed_timestamp = datetime(2026, 6, 13, 10, 0, tzinfo=timezone.utc)
        with TemporaryDirectory() as temp_dir:
            unpacked = Path(temp_dir) / "unpacked"
            self._write_minimal_unpacked_docx(unpacked)

            reviewer = ContractReviewer(unpacked, author="Reviewer", initials="")
            reviewer.set_operation_timestamp(lambda: fixed_timestamp)
            reviewer.add_comment(reviewer.find_text("第一条"), "补充合同目的")

            extensible = reviewer.doc["word/commentsExtensible.xml"]
            comment_ext = extensible.get_node(tag="w16cex:commentExtensible")
            self.assertEqual(
                comment_ext.getAttribute("w16cex:dateUtc"),
                "2026-06-13T10:00:00Z",
            )

    def test_add_comment_consumes_one_timestamp_per_comment(self) -> None:
        from scripts.docx.reviewer import ContractReviewer

        fixed_timestamp = datetime(2026, 6, 13, 10, 0, tzinfo=timezone.utc)
        calls = []

        def provider():
            value = fixed_timestamp + timedelta(minutes=len(calls))
            calls.append(value)
            return value

        with TemporaryDirectory() as temp_dir:
            unpacked = Path(temp_dir) / "unpacked"
            self._write_minimal_unpacked_docx(unpacked, include_comment_parts=True)

            reviewer = ContractReviewer(unpacked, author="Reviewer", initials="")
            reviewer.set_operation_timestamp(provider)
            reviewer.add_comment(reviewer.find_text("第一条"), "补充合同目的")
            reviewer.add_comment(reviewer.find_text("第二条"), "补充付款安排")

            comments = reviewer.doc["word/comments.xml"].dom.getElementsByTagName(
                "w:comment"
            )
            extensible_comments = reviewer.doc[
                "word/commentsExtensible.xml"
            ].dom.getElementsByTagName("w16cex:commentExtensible")

            self.assertEqual(len(calls), 2)
            self.assertEqual(
                [item.getAttribute("w:date") for item in comments],
                [
                    fixed_timestamp.astimezone().isoformat(timespec="seconds"),
                    (fixed_timestamp + timedelta(minutes=1))
                    .astimezone()
                    .isoformat(timespec="seconds"),
                ],
            )
            self.assertEqual(
                [
                    item.getAttribute("w16cex:dateUtc")
                    for item in extensible_comments
                ],
                [
                    "2026-06-13T10:00:00Z",
                    "2026-06-13T10:01:00Z",
                ],
            )

    def test_review_timeline_starts_after_now_and_gaps_between_findings(self) -> None:
        from scripts.review import review_runtime

        class MinRandom:
            def randint(self, start, end):
                return start

        fixed_now = datetime(2026, 6, 13, 10, 0, 0, 123456, tzinfo=timezone.utc)
        original_get_local_now = review_runtime.get_local_now
        original_get_local_timezone = review_runtime.get_local_timezone
        try:
            review_runtime.get_local_now = lambda: fixed_now
            review_runtime.get_local_timezone = lambda: timezone.utc

            timeline = review_runtime.ReviewTimeline(rng=MinRandom())
            first_provider = timeline.start_finding()
            first = first_provider()
            timeline.complete_finding()

            second_provider = timeline.start_finding()
            second = second_provider()

            self.assertGreater(first, fixed_now)
            self.assertGreaterEqual(second - first, timedelta(minutes=5))
        finally:
            review_runtime.get_local_now = original_get_local_now
            review_runtime.get_local_timezone = original_get_local_timezone

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
