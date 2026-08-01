#!/usr/bin/env python3
"""
Unit tests for v2.7 layered PDF alignment improvements.

Covers:
- calculate_font_size: cap-height model, multi-line bisection
- _split_text_to_lines: greedy wrap
- _layout_text_into_bbox: single-line, multi-line, narrow-punctuation (v2.7.1 fix)
- infer_page_scale: median-ratio fallback
- assess_ocr_coordinate_health: skew / drift / out-of-page detection
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

# Add scripts dir to import path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import fitz
import pdf_ocr_layered as L
import pdf_ocr_paddle_api as P


class TestCalculateFontSize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = fitz.Font("cjk")

    def test_empty_text_returns_h(self):
        self.assertEqual(L.calculate_font_size(self.font, "", 100, 20), 0.0)

    def test_zero_dimensions_returns_min(self):
        self.assertEqual(L.calculate_font_size(self.font, "abc", 0, 0), 0.0)

    def test_single_line_cjk(self):
        # CJK text "本院" at bbox 30x15: should fit single-line at ~h/cap ratio
        # 15 / 0.78 = 19.23 max; text_len(19.23) for 2 CJK = 38.46 > 30
        # → multi-line bisection → converges near 15
        fs = L.calculate_font_size(self.font, "本院", 30, 15)
        self.assertGreater(fs, 0.0)
        self.assertLessEqual(fs, 15 / (self.font.ascender - self.font.descender) + 0.01)

    def test_long_text_does_not_exceed_height(self):
        # 100 chars in 60x100 bbox: should not exceed h / cap ratio
        text = "本" * 100
        fs = L.calculate_font_size(self.font, text, 60, 100)
        # max_size = 100 / 0.78 = 128
        self.assertLessEqual(fs, 128.0)
        self.assertGreater(fs, 0.0)


class TestSplitTextToLines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = fitz.Font("cjk")

    def test_short_text_one_line(self):
        lines = L._split_text_to_lines(self.font, "abc", 10.0, 100.0)
        self.assertEqual(lines, ["abc"])

    def test_cjk_text_wraps_at_width(self):
        # 10 CJK chars at fontsize 10 = 100pt wide; max_width 30 → ~3 chars/line
        text = "本院认为原告" * 2  # 12 chars
        lines = L._split_text_to_lines(self.font, text, 10.0, 30.0)
        self.assertGreater(len(lines), 1)
        # All chars preserved
        joined = "".join(lines)
        self.assertEqual(joined, text)


class TestLayoutTextIntoBbox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = fitz.Font("cjk")

    def _new_page(self):
        doc = fitz.open()
        page = doc.new_page(width=400, height=400)
        page.insert_font(fontname="cjk", fontbuffer=self.font.buffer)
        return doc, page

    def test_single_line_short_text(self):
        doc, page = self._new_page()
        fs = L.calculate_font_size(self.font, "本院", 60, 15)
        n = L._layout_text_into_bbox(page, self.font, "本院", x0=50, y1=100, w=60, h=15, fontsize=fs)
        self.assertEqual(n, 1)
        text = page.get_text("text")
        self.assertIn("本院", text)
        doc.close()

    def test_multi_line_long_text(self):
        doc, page = self._new_page()
        # 4 chars at fontsize 15 = 60pt; bbox w=30 → multi-line
        fs = L.calculate_font_size(self.font, "本院认为", 30, 60)
        n = L._layout_text_into_bbox(page, self.font, "本院认为", x0=50, y1=100, w=30, h=60, fontsize=fs)
        self.assertGreaterEqual(n, 1)
        text = "".join(page.get_text("text").split())
        self.assertEqual(text, "本院认为")
        doc.close()

    def test_v27_1_narrow_punctuation_not_dropped(self):
        """v2.7.1 regression: punctuation in narrow bbox must not be dropped."""
        doc, page = self._new_page()
        # Comma in tiny bbox h=6
        fs = L.calculate_font_size(self.font, "，", 4, 6)
        n = L._layout_text_into_bbox(page, self.font, "，", x0=50, y1=100, w=4, h=6, fontsize=fs)
        self.assertGreaterEqual(n, 1)
        text = page.get_text("text")
        self.assertIn("，", text)
        doc.close()

    def test_inserted_span_respects_target_vertical_bbox(self):
        doc, page = self._new_page()
        fs = L.calculate_font_size(self.font, "本院", 100, 30)
        L._layout_text_into_bbox(
            page, self.font, "本院", x0=50, y1=130, w=100, h=30, fontsize=fs,
        )
        spans = [
            span
            for block in page.get_text("dict")["blocks"]
            for line in block.get("lines", [])
            for span in line.get("spans", [])
            if span.get("text")
        ]
        self.assertEqual(len(spans), 1)
        y0, y1 = spans[0]["bbox"][1], spans[0]["bbox"][3]
        self.assertAlmostEqual(y0, 100.0, delta=0.5)
        self.assertAlmostEqual(y1, 130.0, delta=0.5)
        doc.close()

    def test_single_line_span_expands_to_target_horizontal_bbox(self):
        doc, page = self._new_page()
        fs = L.calculate_font_size(self.font, "本院", 36, 15)
        L._layout_text_into_bbox(
            page, self.font, "本院", x0=50, y1=100, w=36, h=15, fontsize=fs,
        )
        word = page.get_text("words")[0]
        self.assertAlmostEqual(word[0], 50.0, delta=0.25)
        self.assertAlmostEqual(word[2], 86.0, delta=0.35)
        doc.close()

    def test_single_line_extreme_padding_is_not_stretched(self):
        doc, page = self._new_page()
        fs = L.calculate_font_size(self.font, "本院", 100, 15)
        L._layout_text_into_bbox(
            page, self.font, "本院", x0=50, y1=100, w=100, h=15, fontsize=fs,
        )
        word = page.get_text("words")[0]
        self.assertLess(word[2] - word[0], 100.0)
        doc.close()


class TestInferPageScale(unittest.TestCase):
    def test_explicit_source_dimensions(self):
        rect = fitz.Rect(0, 0, 595, 842)
        sx, sy = L.infer_page_scale(rect, [], 1190, 1684)
        self.assertAlmostEqual(sx, 0.5)
        self.assertAlmostEqual(sy, 0.5)

    def test_empty_rows_returns_unit(self):
        rect = fitz.Rect(0, 0, 595, 842)
        sx, sy = L.infer_page_scale(rect, [], None, None)
        self.assertEqual((sx, sy), (1.0, 1.0))

    def test_coords_within_page_returns_unit(self):
        rect = fitz.Rect(0, 0, 595, 842)
        rows = [("test", 1.0, [[100, 100], [200, 100], [200, 200], [100, 200]])]
        sx, sy = L.infer_page_scale(rect, rows, None, None)
        self.assertEqual((sx, sy), (1.0, 1.0))

    def test_unverifiable_coordinate_space_fails_closed(self):
        rect = fitz.Rect(0, 0, 595, 842)
        rows = [("test", 1.0, [[1000, 1000], [1200, 1000], [1200, 1100], [1000, 1100]])]
        sx, sy = L.infer_page_scale(rect, rows, None, None)
        self.assertEqual((sx, sy), (0.0, 0.0))
        health = L.assess_ocr_coordinate_health(rows, rect, sx, sy)
        self.assertEqual(health["fit_score"], 0.0)


class TestAssessCoordinateHealth(unittest.TestCase):
    def test_empty_rows(self):
        h = L.assess_ocr_coordinate_health([], fitz.Rect(0, 0, 595, 842), 1.0, 1.0)
        self.assertEqual(h["fit_score"], 0.0)
        self.assertEqual(h["n_rows"], 0)

    def test_well_aligned_axis_polys_score_high(self):
        rect = fitz.Rect(0, 0, 595, 842)
        rows = [
            ("text", 1.0, [[100, 100], [200, 100], [200, 130], [100, 130]]),
            ("text", 1.0, [[100, 150], [250, 150], [250, 180], [100, 180]]),
        ]
        h = L.assess_ocr_coordinate_health(rows, rect, 1.0, 1.0)
        self.assertGreater(h["fit_score"], 0.7)
        self.assertFalse(h["skew_warn"])

    def test_out_of_page_polys_low_score(self):
        rect = fitz.Rect(0, 0, 595, 842)
        # Polys at coordinates far outside page (after scale 1.0)
        rows = [
            ("text", 1.0, [[1000, 1000], [1200, 1000], [1200, 1100], [1000, 1100]]),
        ]
        h = L.assess_ocr_coordinate_health(rows, rect, 1.0, 1.0)
        self.assertLess(h["fit_score"], 0.7)
        self.assertGreater(h["out_of_page_ratio"], 0.5)

    def test_rotated_poly_sets_skew_warning(self):
        rect = fitz.Rect(0, 0, 595, 842)
        rows = [
            ("text", 1.0, [[100, 100], [198.5, 117.4], [193.3, 146.9], [94.8, 129.5]]),
            ("text", 1.0, [[100, 160], [198.5, 177.4], [193.3, 206.9], [94.8, 189.5]]),
        ]
        health = L.assess_ocr_coordinate_health(rows, rect, 1.0, 1.0)
        self.assertTrue(health["skew_warn"])
        self.assertGreater(health["median_skew_degrees"], 9.0)


class TestTransactionalLayering(unittest.TestCase):
    def _args(self, input_path, output_path, mode="skip"):
        return SimpleNamespace(
            input=str(input_path), output=str(output_path), mode=mode,
            paddle_skip_text_min_chars=1, no_paddle_cjk_space_normalize=False,
            paddle_min_score=0.5, quiet=True, layered_health_floor=0.5,
            layered_force=False,
        )

    def _make_pdf(self, path: Path, pages=1, text=None):
        doc = fitz.open()
        for _ in range(pages):
            page = doc.new_page(width=300, height=400)
            if text:
                page.insert_text((30, 40), text)
        doc.save(path)
        doc.close()

    def test_missing_page_entries_fail_without_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.pdf"
            output_path = Path(tmpdir) / "output.pdf"
            self._make_pdf(input_path, pages=1)
            entry = {"rows": [("完整", 1.0, [[20, 20], [80, 20], [80, 40], [20, 40]])],
                     "width": 300, "height": 400}
            ok = L.apply_page_entries_as_layered_pdf(
                [entry, entry], self._args(input_path, output_path), "test",
            )
            self.assertFalse(ok)
            self.assertFalse(output_path.exists())


    def test_empty_page_result_fails_without_copying_original(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.pdf"
            output_path = Path(tmpdir) / "output.pdf"
            self._make_pdf(input_path)
            ok = L.apply_page_entries_as_layered_pdf(
                [{"rows": [], "width": 300, "height": 400}],
                self._args(input_path, output_path), "test",
            )
            self.assertFalse(ok)
            self.assertFalse(output_path.exists())

    def test_long_text_is_preserved_completely(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.pdf"
            output_path = Path(tmpdir) / "output.pdf"
            self._make_pdf(input_path)
            content = "本院认为原告提交的全部证据能够形成完整证据链" * 4
            entry = {
                "rows": [(content, 1.0, [[20, 40], [180, 40], [180, 240], [20, 240]])],
                "width": 300, "height": 400,
            }
            ok = L.apply_page_entries_as_layered_pdf(
                [entry], self._args(input_path, output_path), "test",
            )
            self.assertTrue(ok)
            with fitz.open(output_path) as doc:
                extracted = "".join(doc[0].get_text("text").split())
            self.assertEqual(extracted, content)

    def test_redo_with_existing_text_fails_for_safe_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.pdf"
            output_path = Path(tmpdir) / "output.pdf"
            self._make_pdf(input_path, text="existing")
            entry = {"rows": [("新文字", 1.0, [[20, 20], [100, 20], [100, 50], [20, 50]])],
                     "width": 300, "height": 400}
            ok = L.apply_page_entries_as_layered_pdf(
                [entry], self._args(input_path, output_path, mode="redo"), "test",
            )
            self.assertFalse(ok)
            self.assertFalse(output_path.exists())


class TestPaddleApiModelParsing(unittest.TestCase):
    def test_ppocr_v6_is_default_and_v5_remains_supported(self):
        self.assertEqual(P.PADDLE_JOB_MODEL, "PP-OCRv6")
        self.assertEqual(P.SUPPORTED_PADDLE_MODELS[0], "PP-OCRv6")
        self.assertIn(P.PADDLE_OCR_V5_MODEL, P.SUPPORTED_PADDLE_MODELS)

    def test_flat_rec_boxes_are_converted_to_quad(self):
        rows = L.parse_paddle_predict_result({
            "rec_texts": ["法院"],
            "rec_scores": [0.98],
            "rec_boxes": [[10, 20, 110, 50]],
        })
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], [[10.0, 20.0], [110.0, 20.0], [110.0, 50.0], [10.0, 50.0]])

    @staticmethod
    def _vl_jsonl():
        return json.dumps({
            "result": {
                "dataInfo": {"pages": [{"width": 1000, "height": 1400}]},
                "layoutParsingResults": [{
                    "prunedResult": {
                        "width": 1000,
                        "height": 1400,
                        "parsing_res_list": [{
                            "block_label": "text",
                            "block_content": "借款合同",
                            "block_bbox": [10, 20, 210, 60],
                        }],
                    },
                }],
            },
        }, ensure_ascii=False)

    @staticmethod
    def _ppocr_jsonl():
        return json.dumps({
            "result": {
                "dataInfo": {"pages": [{"width": 1000, "height": 1400}]},
                "ocrResults": [{
                    "prunedResult": {
                        "width": 1000,
                        "height": 1400,
                        "rec_texts": ["借款合同"],
                        "rec_scores": [0.99],
                        "rec_polys": [[[10, 20], [210, 20], [210, 60], [10, 60]]],
                    },
                }],
            },
        }, ensure_ascii=False)

    @staticmethod
    def _structure_jsonl(pruned_as_string=False):
        pruned = {
            "width": 1000,
            "height": 1400,
            "overall_ocr_res": {
                "rec_texts": ["借款合同", "人民法院"],
                "rec_scores": [0.99, 0.97],
                "rec_polys": [],
                "dt_polys": [
                    [[10, 20], [210, 20], [210, 60], [10, 60]],
                    [[10, 80], [210, 80], [210, 120], [10, 120]],
                ],
            },
            "parsing_res_list": [{
                "block_label": "text",
                "block_content": "不得覆盖到行级坐标的整段长文本",
                "block_bbox": [5, 5, 900, 1300],
            }],
        }
        if pruned_as_string:
            pruned = json.dumps(pruned, ensure_ascii=False)
        return json.dumps({
            "result": {
                "dataInfo": {"pages": [{"width": 1000, "height": 1400}]},
                "layoutParsingResults": [{"prunedResult": pruned}],
            },
        }, ensure_ascii=False)

    def test_all_five_models_dispatch_to_supported_response_parser(self):
        fixtures = {
            P.PADDLE_JOB_MODEL: self._ppocr_jsonl(),
            P.PADDLE_OCR_V5_MODEL: self._ppocr_jsonl(),
            P.PADDLE_VL_15_MODEL: self._vl_jsonl(),
            P.PADDLE_VL_16_MODEL: self._vl_jsonl(),
            P.PADDLE_STRUCTURE_MODEL: self._structure_jsonl(),
        }
        self.assertEqual(tuple(fixtures), P.SUPPORTED_PADDLE_MODELS)
        for model, payload in fixtures.items():
            with self.subTest(model=model):
                entries = P._parse_jsonl(payload, model)
                self.assertEqual(len(entries), 1)
                self.assertGreaterEqual(len(entries[0]["rows"]), 1)
                self.assertEqual(entries[0]["width"], 1000.0)
                self.assertEqual(entries[0]["height"], 1400.0)

    def test_structure_uses_overall_line_rows_not_layout_block_text(self):
        entries = P.parse_ppstructure_jsonl_to_page_entries(
            self._structure_jsonl(pruned_as_string=True),
        )
        texts = [row[0] for row in entries[0]["rows"]]
        self.assertEqual(texts, ["借款合同", "人民法院"])
        self.assertNotIn("不得覆盖到行级坐标的整段长文本", texts)
        self.assertEqual(entries[0]["layout_blocks"][0]["label"], "text")
        self.assertEqual(
            entries[0]["layout_blocks"][0]["content"],
            "不得覆盖到行级坐标的整段长文本",
        )

    def test_layout_block_paragraph_flags_are_preserved(self):
        payload = json.loads(self._structure_jsonl())
        block = payload["result"]["layoutParsingResults"][0]["prunedResult"]["parsing_res_list"][0]
        block.update({
            "seg_start_flag": True,
            "seg_end_flag": False,
            "sub_label": "body_text",
            "sub_index": 3,
            "index": 7,
        })
        entries = P.parse_ppstructure_jsonl_to_page_entries(
            json.dumps(payload, ensure_ascii=False)
        )
        layout = entries[0]["layout_blocks"][0]
        self.assertTrue(layout["seg_start"])
        self.assertFalse(layout["seg_end"])
        self.assertEqual(layout["sub_label"], "body_text")
        self.assertEqual(layout["sub_index"], 3)
        self.assertEqual(layout["index"], 7)

    def test_model_payloads_keep_geometry_correction_off_by_default(self):
        for model in P.SUPPORTED_PADDLE_MODELS:
            with self.subTest(model=model):
                payload = P._build_default_payload(model)
                self.assertFalse(payload["useDocOrientationClassify"])
                self.assertFalse(payload["useDocUnwarping"])
        self.assertNotIn("useLayoutDetection", P._build_default_payload(P.PADDLE_VL_16_MODEL))
        self.assertNotIn("layoutShapeMode", P._build_default_payload(P.PADDLE_STRUCTURE_MODEL))


if __name__ == "__main__":
    unittest.main(verbosity=2)
