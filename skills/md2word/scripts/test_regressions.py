#!/usr/bin/env python3
"""md2word 已知出版逃逸的回归测试。"""

from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
import zipfile

from docx import Document


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from formatter import convert_quotes_to_chinese  # noqa: E402
from footnote_handler import (  # noqa: E402
    FootnoteManager,
    _footnote_text_to_runs_xml,
    _inject_footnotes_into_docx,
)


class Md2WordRegressionTest(unittest.TestCase):
    def test_cjk_ascii_quotes_convert_but_english_apostrophes_survive(self):
        converted = convert_quotes_to_chinese("标注'需律师现场确认'，don't、O'Brien 与 API's 保留。")
        self.assertIn("‘需律师现场确认’", converted)
        self.assertIn("don't", converted)
        self.assertIn("O'Brien", converted)
        self.assertIn("API's", converted)

    def test_footnote_inline_markers_become_word_properties(self):
        xml = _footnote_text_to_runs_xml("*模型概览* 与 **重点**，命令 `book-gate verify`")
        self.assertNotIn("*模型概览*", xml)
        self.assertNotIn("**重点**", xml)
        self.assertNotIn("`book-gate verify`", xml)
        self.assertIn("<w:i/>", xml)
        self.assertIn("<w:b/>", xml)
        self.assertIn('w:ascii="Consolas"', xml)

    def test_injected_footnotes_xml_has_no_literal_markdown(self):
        with TemporaryDirectory() as temp:
            docx_path = Path(temp) / "footnotes.docx"
            Document().save(docx_path)
            _inject_footnotes_into_docx(
                str(docx_path),
                [(1, "*模型概览*"), (2, "**需律师确认**"), (3, "`Skill`")],
            )
            with zipfile.ZipFile(docx_path) as archive:
                xml = archive.read("word/footnotes.xml").decode("utf-8")
            self.assertNotIn("*模型概览*", xml)
            self.assertNotIn("**需律师确认**", xml)
            self.assertNotIn("`Skill`", xml)
            self.assertIn("<w:i/>", xml)
            self.assertIn("<w:b/>", xml)

    def test_endnotes_path_also_removes_markdown_markers(self):
        document = Document()
        manager = FootnoteManager(mode="endnote")
        manager.refs = [(1, "*模型概览* 与 **重点**，命令 `Skill`")]
        manager.append_endnotes_section(document)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        self.assertIn("模型概览 与 重点，命令 Skill", text)
        self.assertNotIn("*", text)
        self.assertNotIn("`", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

