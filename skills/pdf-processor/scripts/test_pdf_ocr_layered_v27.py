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

import os
import sys
import unittest
from pathlib import Path

# Add scripts dir to import path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import fitz
import pdf_ocr_layered as L


class TestCalculateFontSize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = fitz.Font("cjk")

    def test_empty_text_returns_h(self):
        self.assertEqual(L.calculate_font_size(self.font, "", 100, 20), 20)

    def test_zero_dimensions_returns_min(self):
        self.assertGreaterEqual(L.calculate_font_size(self.font, "abc", 0, 0), 5.0)

    def test_single_line_cjk(self):
        # CJK text "本院" at bbox 30x15: should fit single-line at ~h/cap ratio
        # 15 / 0.78 = 19.23 max; text_len(19.23) for 2 CJK = 38.46 > 30
        # → multi-line bisection → converges near 15
        fs = L.calculate_font_size(self.font, "本院", 30, 15)
        self.assertGreaterEqual(fs, 5.0)
        self.assertLessEqual(fs, 19.23)

    def test_long_text_does_not_exceed_height(self):
        # 100 chars in 60x100 bbox: should not exceed h / cap ratio
        text = "本" * 100
        fs = L.calculate_font_size(self.font, text, 60, 100)
        # max_size = 100 / 0.78 = 128
        self.assertLessEqual(fs, 128.0)
        self.assertGreaterEqual(fs, 5.0)


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
        n = L._layout_text_into_bbox(page, self.font, "本院", x0=50, y1=100, w=60, h=15, fontsize=15.0)
        self.assertEqual(n, 1)
        text = page.get_text("text")
        self.assertIn("本院", text)
        doc.close()

    def test_multi_line_long_text(self):
        doc, page = self._new_page()
        # 4 chars at fontsize 15 = 60pt; bbox w=30 → multi-line
        n = L._layout_text_into_bbox(page, self.font, "本院认为", x0=50, y1=100, w=30, h=60, fontsize=15.0)
        self.assertGreaterEqual(n, 1)
        text = page.get_text("text")
        self.assertIn("本", text)  # at least first char is written
        doc.close()

    def test_v27_1_narrow_punctuation_not_dropped(self):
        """v2.7.1 regression: punctuation in narrow bbox must not be dropped."""
        doc, page = self._new_page()
        # Comma in tiny bbox h=6
        n = L._layout_text_into_bbox(page, self.font, "，", x0=50, y1=100, w=4, h=6, fontsize=7.69)
        self.assertGreaterEqual(n, 1)
        text = page.get_text("text")
        self.assertIn("，", text)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
