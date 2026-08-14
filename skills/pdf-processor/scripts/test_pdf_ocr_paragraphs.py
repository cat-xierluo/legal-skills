#!/usr/bin/env python3

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from pdf_ocr_paragraphs import (  # noqa: E402
    generate_semantic_text,
    normalize_inline_text,
    reconstruct_paragraphs,
)
from pdf_ocr_corrections import dump_page_entries, load_page_entries  # noqa: E402
import fitz  # noqa: E402
import pdf_ocr_layered as layered  # noqa: E402


def row(text, x0, y0, x1, y1, score=1.0):
    return (text, score, [[x0, y0], [x1, y0], [x1, y1], [x0, y1]])


class TestInlineNormalization(unittest.TestCase):
    def test_removes_cjk_internal_spaces(self):
        self.assertEqual(normalize_inline_text("医疗 过错 评 定费"), "医疗过错评定费")

    def test_keeps_latin_word_space(self):
        self.assertEqual(normalize_inline_text("Paddle OCR V6"), "Paddle OCR V6")

    def test_adds_space_after_compact_clause_number(self):
        self.assertEqual(normalize_inline_text("5-4甲方应付款"), "5-4 甲方应付款")


class TestGeometryParagraphs(unittest.TestCase):
    def test_wraps_full_lines_but_keeps_centered_title_separate(self):
        entries = [{
            "width": 1000,
            "height": 1400,
            "rows": [
                row("标题", 400, 100, 600, 150),
                row("第一行写到右侧", 180, 180, 900, 230),
                row("第二行继续", 100, 240, 900, 290),
                row("末行", 100, 300, 350, 350),
            ],
        }]
        paragraphs, diagnostics = reconstruct_paragraphs(entries)
        self.assertEqual([item["row_indices"] for item in paragraphs], [[0], [1, 2, 3]])
        self.assertEqual(diagnostics["paragraphs"], 2)

    def test_page_boundary_never_merges(self):
        entries = [
            {"width": 1000, "height": 1400, "rows": [row("第一页", 100, 100, 900, 150)]},
            {"width": 1000, "height": 1400, "rows": [row("第二页", 100, 100, 900, 150)]},
        ]
        self.assertEqual(generate_semantic_text(entries), "第一页\n\n第二页")

    def test_body_width_open_line_continues_without_reaching_right_edge(self):
        entries = [{
            "width": 1000,
            "height": 1400,
            "rows": [
                row("第一行末尾为编号1004", 100, 100, 720, 150),
                row("第二行继续等待审", 100, 160, 700, 210),
                row("查。", 100, 220, 180, 270),
                row("后续独立段落。", 100, 500, 900, 550),
                row("再一段。", 100, 700, 900, 750),
                row("末段。", 100, 900, 900, 950),
            ],
        }]
        paragraphs, _ = reconstruct_paragraphs(entries)
        self.assertEqual(paragraphs[0]["row_indices"], [0, 1, 2])
        self.assertEqual(paragraphs[0]["text"], "第一行末尾为编号1004第二行继续等待审查。")

    def test_numbered_paragraph_start_is_not_joined_to_open_body_line(self):
        entries = [{
            "width": 1000,
            "height": 1400,
            "rows": [
                row("上一段未带句号", 100, 100, 700, 150),
                row("1. 新的编号段落", 100, 160, 400, 210),
                row("参考宽行。", 100, 500, 900, 550),
                row("另一宽行。", 100, 700, 900, 750),
            ],
        }]
        paragraphs, _ = reconstruct_paragraphs(entries)
        self.assertEqual(paragraphs[0]["row_indices"], [0])
        self.assertEqual(paragraphs[1]["row_indices"], [1])

    def test_output_has_single_blank_line_only(self):
        entries = [{
            "width": 1000,
            "height": 1400,
            "rows": [
                row("第一段", 100, 100, 300, 150),
                row("第二段", 100, 300, 300, 350),
            ],
        }]
        text = generate_semantic_text(entries)
        self.assertNotIn("\n\n\n", text)
        self.assertEqual(text.count("\n\n"), 1)


class TestLayoutFusion(unittest.TestCase):
    def _text_page(self):
        return {
            "width": 1000,
            "height": 1400,
            "rows": [
                row("正文第一行", 100, 100, 900, 150),
                row("正文末行", 100, 160, 350, 210),
                row("印章噪声", 700, 250, 900, 320),
                row("地址", 100, 1100, 450, 1150),
                row("电话", 100, 1160, 300, 1210),
            ],
        }

    def _layout_page(self):
        return {
            "width": 500,
            "height": 700,
            "layout_blocks": [
                {"bbox": [45, 45, 460, 110], "label": "text", "content": "错误块文本", "index": 0},
                {"bbox": [340, 120, 470, 170], "label": "seal", "content": "章", "index": 1},
                {"bbox": [45, 540, 240, 620], "label": "footnote", "content": "错误脚注", "index": 2},
            ],
        }

    def test_layout_filters_seal_and_never_uses_block_content(self):
        paragraphs, diagnostics = reconstruct_paragraphs(
            [self._text_page()], [self._layout_page()],
        )
        self.assertEqual([item["text"] for item in paragraphs], ["正文第一行正文末行", "地址", "电话"])
        self.assertEqual(diagnostics["excluded_rows"], 1)
        self.assertEqual(diagnostics["pages"][0]["excluded_row_indices"], [2])
        self.assertEqual(diagnostics["layout_coverage"], 1.0)
        self.assertNotIn("错误", generate_semantic_text([self._text_page()], [self._layout_page()]))

    def test_low_layout_coverage_falls_back_to_geometry(self):
        layout = {
            "width": 1000,
            "height": 1400,
            "layout_blocks": [
                {"bbox": [100, 100, 900, 150], "label": "text", "index": 0},
            ],
        }
        paragraphs, diagnostics = reconstruct_paragraphs([self._text_page()], [layout])
        self.assertEqual(diagnostics["pages"][0]["strategy"], "geometry_fallback")
        self.assertGreaterEqual(len(paragraphs), 3)

    def test_empty_layout_uses_geometry(self):
        paragraphs, diagnostics = reconstruct_paragraphs(
            [self._text_page()], [{"layout_blocks": []}],
        )
        self.assertTrue(paragraphs)
        self.assertEqual(diagnostics["pages"][0]["strategy"], "geometry")

    def test_explicit_segment_flags_join_adjacent_blocks(self):
        text = {
            "width": 1000,
            "height": 1400,
            "rows": [
                row("跨块第一行", 100, 100, 900, 150),
                row("跨块末行", 100, 160, 350, 210),
            ],
        }
        layout = {
            "width": 1000,
            "height": 1400,
            "layout_blocks": [
                {"bbox": [90, 90, 910, 155], "label": "text", "index": 0, "seg_end": False},
                {"bbox": [90, 155, 400, 220], "label": "text", "index": 1, "seg_start": False},
            ],
        }
        paragraphs, diagnostics = reconstruct_paragraphs([text], [layout])
        self.assertEqual([item["row_indices"] for item in paragraphs], [[0, 1]])
        self.assertEqual(diagnostics["layout_coverage"], 1.0)

    def test_layout_text_block_allows_wide_line_spacing(self):
        text = {
            "width": 1000,
            "height": 1400,
            "rows": [
                row("条款第一行写到右侧", 100, 100, 900, 130),
                row("条款第二行写到右侧", 100, 162, 900, 192),
                row("条款末行。", 100, 224, 300, 254),
            ],
        }
        layout = {
            "width": 1000,
            "height": 1400,
            "rows": text["rows"],
            "layout_blocks": [
                {"bbox": [90, 90, 910, 260], "label": "text", "index": 0},
            ],
        }
        paragraphs, diagnostics = reconstruct_paragraphs([text], [layout])
        self.assertEqual([item["row_indices"] for item in paragraphs], [[0, 1, 2]])
        self.assertEqual(diagnostics["paragraphs"], 1)

    def test_same_visual_line_fragments_follow_horizontal_order(self):
        text = {
            "width": 1000,
            "height": 1400,
            "rows": [
                row("】项目资料清单", 300, 102, 600, 132),
                row("【", 100, 106, 125, 130),
            ],
        }
        layout = {
            "width": 1000,
            "height": 1400,
            "rows": text["rows"],
            "layout_blocks": [
                {"bbox": [90, 90, 610, 140], "label": "paragraph_title", "index": 0},
            ],
        }
        paragraphs, _ = reconstruct_paragraphs([text], [layout])
        self.assertEqual(paragraphs[0]["text"], "【】项目资料清单")
        self.assertEqual(paragraphs[0]["row_indices"], [1, 0])

    def test_table_cells_on_same_visual_row_use_pipe_separator(self):
        text = {
            "width": 1000,
            "height": 1400,
            "rows": [
                row("序号", 100, 100, 180, 130),
                row("资料名称", 300, 101, 430, 131),
                row("备注", 700, 100, 780, 130),
                row("1", 100, 160, 120, 190),
            ],
        }
        layout = {
            "width": 1000,
            "height": 1400,
            "rows": text["rows"],
            "layout_blocks": [
                {"bbox": [90, 90, 800, 200], "label": "table", "index": 0},
            ],
        }
        paragraphs, _ = reconstruct_paragraphs([text], [layout])
        self.assertEqual([item["text"] for item in paragraphs], ["序号 | 资料名称 | 备注", "1"])

    def test_adjacent_text_blocks_merge_until_numbered_boundary(self):
        text = {
            "width": 1000,
            "height": 1400,
            "rows": [
                row("1-1 服务内容包括：", 100, 100, 900, 130),
                row("□一般家务；", 100, 162, 850, 192),
                row("□照料老人；", 100, 224, 850, 254),
                row("1-2 服务地点", 100, 286, 400, 316),
            ],
        }
        layout = {
            "width": 1000,
            "height": 1400,
            "rows": text["rows"],
            "layout_blocks": [
                {"bbox": [90, 90, 910, 140], "label": "text", "index": 0},
                {"bbox": [90, 152, 910, 202], "label": "text", "index": 1},
                {"bbox": [90, 214, 910, 264], "label": "text", "index": 2},
                {"bbox": [90, 276, 910, 326], "label": "text", "index": 3},
            ],
        }
        paragraphs, diagnostics = reconstruct_paragraphs([text], [layout])
        self.assertEqual(
            [item["row_indices"] for item in paragraphs],
            [[0, 1, 2], [3]],
        )
        self.assertEqual(diagnostics["layout_boundary_merges"], 2)

    def test_structure_rows_only_replace_low_confidence_exact_overlap(self):
        text = {
            "width": 1000,
            "height": 1400,
            "rows": [row("K", 100, 100, 125, 130, score=0.4)],
        }
        layout = {
            "width": 1000,
            "height": 1400,
            "rows": [row("【", 101, 100, 126, 130, score=0.99)],
            "layout_blocks": [
                {"bbox": [90, 90, 140, 140], "label": "text", "index": 0},
            ],
        }
        paragraphs, diagnostics = reconstruct_paragraphs([text], [layout])
        self.assertEqual(paragraphs[0]["text"], "【")
        self.assertEqual(diagnostics["structure_text_fallbacks"], 1)
        self.assertEqual(diagnostics["pages"][0]["structure_text_fallback_indices"], [0])


class TestSemanticPdfMetadata(unittest.TestCase):
    def test_dump_resume_preserves_semantic_paragraphs(self):
        entries = [{
            "width": 1000,
            "height": 1400,
            "rows": [row("第一行", 100, 100, 900, 150)],
            "semantic_paragraphs": [{"text": "第一行", "row_indices": [0]}],
        }]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dump.json"
            dump_page_entries(entries, path, model="PP-OCRv6")
            loaded, metadata = load_page_entries(path)
        self.assertEqual(loaded[0]["semantic_paragraphs"], entries[0]["semantic_paragraphs"])
        self.assertEqual(metadata["model"], "PP-OCRv6")

    def test_actualtext_wraps_physical_rows_without_changing_render(self):
        doc = fitz.open()
        page = doc.new_page(width=300, height=300)
        font = fitz.Font("cjk")
        rows = [
            row("第一行", 30, 30, 160, 60),
            row("第二行", 30, 70, 160, 100),
        ]
        before = page.get_pixmap(alpha=False).samples
        inserted = layered._insert_text_blocks(
            page,
            font,
            rows,
            scale_x=1.0,
            scale_y=1.0,
            min_score=0.5,
            cjk_normalize=True,
            page_rotation=0,
            source_name="test",
            pno=1,
            total_pages=1,
            quiet=True,
            semantic_paragraphs=[{"text": "第一行第二行", "row_indices": [0, 1]}],
        )
        streams = b"\n".join(doc.xref_stream(xref) for xref in page.get_contents())
        after = page.get_pixmap(alpha=False).samples
        self.assertEqual(inserted, 2)
        self.assertIn(b"/ActualText", streams)
        self.assertEqual(before, after)
        reopened = fitz.open(stream=doc.tobytes(), filetype="pdf")
        self.assertEqual(reopened[0].get_text("text").replace("\n", ""), "第一行第二行")
        reopened.close()
        doc.close()

    def test_incomplete_actualtext_mapping_fails_closed(self):
        doc = fitz.open()
        page = doc.new_page(width=300, height=300)
        font = fitz.Font("cjk")
        with self.assertRaises(layered.TextLayerIntegrityError):
            layered._insert_text_blocks(
                page,
                font,
                [row("第一行", 30, 30, 160, 60)],
                scale_x=1.0,
                scale_y=1.0,
                min_score=0.5,
                cjk_normalize=True,
                page_rotation=0,
                source_name="test",
                pno=1,
                total_pages=1,
                quiet=True,
                semantic_paragraphs=[{"text": "第一行", "row_indices": [9]}],
            )
        doc.close()


if __name__ == "__main__":
    unittest.main()
