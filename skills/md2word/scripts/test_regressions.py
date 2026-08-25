#!/usr/bin/env python3
"""md2word 已知出版逃逸的回归测试。"""

from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
import zipfile
import xml.etree.ElementTree as ET

from docx import Document
from docx.oxml.ns import qn


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from formatter import convert_quotes_to_chinese, parse_text_formatting  # noqa: E402
from footnote_handler import (  # noqa: E402
    FootnoteManager,
    _footnote_text_to_runs_xml,
    _inject_footnotes_into_docx,
)

import md2word  # noqa: E402


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

    def test_inline_code_markers_are_not_reinterpreted_as_emphasis(self):
        config = md2word.get_preset("book-publish")
        md2word.set_config(config)
        paragraph = Document().add_paragraph()
        parse_text_formatting(
            paragraph,
            "关键词检索（如 `law_keyword`）、语义 / 向量检索（如 `case_vector`）、"
            "精确详情（如 `law_detail`、`case_detail`），运算标识 `op*one` 与 `op*two`，"
            "另有 _下划线斜体_ 和 *星号斜体*。",
        )

        self.assertNotIn("`", paragraph.text)
        self.assertIn("law_keyword", paragraph.text)
        self.assertIn("case_vector", paragraph.text)
        self.assertIn("law_detail", paragraph.text)
        self.assertIn("case_detail", paragraph.text)

        code_names = {
            "law_keyword",
            "case_vector",
            "law_detail",
            "case_detail",
            "op*one",
            "op*two",
        }
        code_runs = [run for run in paragraph.runs if run.text in code_names]
        self.assertEqual({run.text for run in code_runs}, code_names)
        for run in code_runs:
            self.assertFalse(bool(run.italic))
            self.assertEqual(run.font.name, "Courier New")

        italic_runs = {
            run.text: run for run in paragraph.runs if run.text in {"下划线斜体", "星号斜体"}
        }
        self.assertEqual(set(italic_runs), {"下划线斜体", "星号斜体"})
        self.assertTrue(all(run.italic for run in italic_runs.values()))

    def test_repeated_footnote_label_creates_distinct_word_footnotes(self):
        with TemporaryDirectory() as temp:
            temp_dir = Path(temp)
            markdown = temp_dir / "repeated-footnote.md"
            output = temp_dir / "repeated-footnote.docx"
            markdown.write_text(
                "# 重复脚注\n\n第一次[^same]，第二次[^same]。\n\n[^same]: 相同脚注文本\n",
                encoding="utf-8",
            )
            config = md2word.get_preset("book-publish")
            md2word.set_config(config)

            md2word.create_word_document(str(markdown), str(output), config=config)

            with zipfile.ZipFile(output) as archive:
                document_root = ET.fromstring(archive.read("word/document.xml"))
                footnotes_root = ET.fromstring(archive.read("word/footnotes.xml"))
            reference_ids = [
                node.get(qn("w:id"))
                for node in document_root.iter(qn("w:footnoteReference"))
            ]
            footnotes = [
                node
                for node in footnotes_root.iter(qn("w:footnote"))
                if int(node.get(qn("w:id"))) > 0
            ]
            footnote_texts = [
                "".join(node.text or "" for node in footnote.iter(qn("w:t"))).strip()
                for footnote in footnotes
            ]
            self.assertEqual(len(reference_ids), 2)
            self.assertEqual(len(set(reference_ids)), 2, "每次原生脚注引用必须使用独立 w:id")
            self.assertEqual(len(footnotes), 2)
            self.assertEqual(footnote_texts, ["相同脚注文本", "相同脚注文本"])

    def test_adjacent_footnote_references_get_one_superscript_nbsp_separator(self):
        with TemporaryDirectory() as temp:
            temp_dir = Path(temp)
            markdown = temp_dir / "adjacent-footnotes.md"
            output = temp_dir / "adjacent-footnotes.docx"
            markdown.write_text(
                "# 相邻脚注\n\n"
                "相邻[^a][^b]；空格[^a] [^b]；逗号[^a]，[^b]；顿号[^a]、[^b]。\n\n"
                "[^a]: 脚注甲\n[^b]: 脚注乙\n",
                encoding="utf-8",
            )
            config = md2word.get_preset("book-publish")
            md2word.set_config(config)

            md2word.create_word_document(str(markdown), str(output), config=config)

            with zipfile.ZipFile(output) as archive:
                document_root = ET.fromstring(archive.read("word/document.xml"))
            nbsp_runs = []
            reference_paragraph_tokens = None
            for paragraph in document_root.iter(qn("w:p")):
                tokens = []
                reference_count = 0
                for run in paragraph.findall(qn("w:r")):
                    reference = run.find(qn("w:footnoteReference"))
                    if reference is not None:
                        tokens.append(("reference", reference.get(qn("w:id")), run))
                        reference_count += 1
                        continue
                    text = "".join(node.text or "" for node in run.iter(qn("w:t")))
                    if text:
                        tokens.append(("text", text, run))
                    if text == "\u00a0":
                        nbsp_runs.append(run)
                if reference_count == 8:
                    reference_paragraph_tokens = tokens

            self.assertEqual(len(nbsp_runs), 1, "只有源码直接相邻的脚注引用需要 NBSP")
            self.assertIsNotNone(reference_paragraph_tokens)
            nbsp_index = next(
                index
                for index, token in enumerate(reference_paragraph_tokens)
                if token[0] == "text" and token[1] == "\u00a0"
            )
            self.assertEqual(reference_paragraph_tokens[nbsp_index - 1][0], "reference")
            self.assertEqual(reference_paragraph_tokens[nbsp_index + 1][0], "reference")
            run_properties = nbsp_runs[0].find(qn("w:rPr"))
            self.assertEqual(
                run_properties.find(qn("w:vertAlign")).get(qn("w:val")), "superscript"
            )
            self.assertEqual(run_properties.find(qn("w:sz")).get(qn("w:val")), "18")

    def test_positive_footnote_paragraphs_have_compact_explicit_spacing(self):
        with TemporaryDirectory() as temp:
            docx_path = Path(temp) / "footnote-spacing.docx"
            Document().save(docx_path)
            _inject_footnotes_into_docx(
                str(docx_path), [(1, "第一条脚注"), (2, "第二条脚注")]
            )

            with zipfile.ZipFile(docx_path) as archive:
                footnotes_root = ET.fromstring(archive.read("word/footnotes.xml"))
            positive_footnotes = [
                node
                for node in footnotes_root.iter(qn("w:footnote"))
                if int(node.get(qn("w:id"))) > 0
            ]
            self.assertEqual(len(positive_footnotes), 2)
            for footnote in positive_footnotes:
                paragraph = footnote.find(qn("w:p"))
                spacing = paragraph.find(f"{qn('w:pPr')}/{qn('w:spacing')}")
                self.assertIsNotNone(spacing)
                self.assertEqual(spacing.get(qn("w:before")), "0")
                self.assertEqual(spacing.get(qn("w:after")), "0")
                self.assertEqual(spacing.get(qn("w:line")), "240")
                self.assertEqual(spacing.get(qn("w:lineRule")), "auto")

    def test_repeated_endnote_label_reuses_one_number_and_definition(self):
        with TemporaryDirectory() as temp:
            temp_dir = Path(temp)
            markdown = temp_dir / "repeated-endnote.md"
            output = temp_dir / "repeated-endnote.docx"
            markdown.write_text(
                "# 重复尾注\n\n第一次[^same]，第二次[^same]。\n\n[^same]: 相同尾注文本\n",
                encoding="utf-8",
            )
            config = md2word.get_preset("book-publish")
            md2word.set_config(config)

            md2word.create_word_document(
                str(markdown), str(output), config=config, notes_mode="endnote"
            )

            document = Document(output)
            paragraph_texts = [paragraph.text for paragraph in document.paragraphs]
            self.assertIn("第一次1，第二次1。", paragraph_texts)
            self.assertEqual(paragraph_texts.count("[1] 相同尾注文本"), 1)

    def test_external_image_download_function_exists(self):
        # 外链图片下载保持默认启用（原行为），download_external_image 可被直接调用
        self.assertTrue(callable(md2word.download_external_image))
        self.assertFalse(hasattr(md2word, "ALLOW_REMOTE_IMAGES"), "外链图片下载开关已移除，保持默认下载")

    def test_book_mode_keeps_in_chapter_hr_and_only_breaks_between_chapters(self):
        with TemporaryDirectory() as temp:
            temp_dir = Path(temp)
            chapter_one = temp_dir / "ch01.md"
            chapter_two = temp_dir / "ch02.md"
            output = temp_dir / "book.docx"
            chapter_one.write_text(
                "# 第一章\n\n正文一[^note]\n\n---\n\n章内分隔线后的正文。\n\n[^note]: 第一章脚注\n",
                encoding="utf-8",
            )
            chapter_two.write_text(
                "# 第二章\n\n正文二[^note]\n\n[^note]: 第二章脚注\n",
                encoding="utf-8",
            )
            config = md2word.get_preset("book-publish")
            md2word.set_config(config)

            md2word.create_book([str(chapter_one), str(chapter_two)], str(output), config)

            document = Document(output)
            horizontal_rule = "─" * config.get("horizontal_rule.repeat_count", 55)
            self.assertEqual(len(document.sections), 2, "两章合并应恰好产生两个 section")
            self.assertEqual(
                sum(paragraph.text == horizontal_rule for paragraph in document.paragraphs),
                1,
                "第一章内的 Markdown 水平线应保留",
            )
            for section in document.sections:
                footnote_properties = section._sectPr.find(qn("w:footnotePr"))
                self.assertIsNotNone(footnote_properties)
                restart = footnote_properties.find(qn("w:numRestart"))
                self.assertEqual(restart.get(qn("w:val")), "eachSec")
            self.assertIn("法律 AI Skill 实战", document.sections[0].header.paragraphs[0].text)
            self.assertTrue(document.sections[1].header.is_linked_to_previous)
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")
                settings_xml = archive.read("word/settings.xml").decode("utf-8")
            self.assertIn('TOC \\o "1-3" \\h \\z \\u', document_xml)
            self.assertIn("<w:updateFields", settings_xml)

    def test_single_document_first_hr_is_rendered_without_page_break(self):
        with TemporaryDirectory() as temp:
            temp_dir = Path(temp)
            markdown = temp_dir / "single.md"
            output = temp_dir / "single.docx"
            markdown.write_text(
                "# 单章\n\n首段。\n\n---\n\n第二段。\n\n***\n\n第三段。\n\n___\n\n末段。\n",
                encoding="utf-8",
            )
            config = md2word.get_preset("book-publish")
            md2word.set_config(config)

            md2word.create_word_document(str(markdown), str(output), config=config)

            document = Document(output)
            horizontal_rule = "─" * config.get("horizontal_rule.repeat_count", 55)
            self.assertEqual(len(document.sections), 1)
            self.assertEqual(
                sum(paragraph.text == horizontal_rule for paragraph in document.paragraphs),
                3,
                "---、***、___ 都应按 Markdown 语义渲染为水平线",
            )
            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")
            self.assertNotIn('<w:br w:type="page"', document_xml)


if __name__ == "__main__":
    unittest.main(verbosity=2)
