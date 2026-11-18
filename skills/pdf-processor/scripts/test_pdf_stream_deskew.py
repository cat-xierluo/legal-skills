#!/usr/bin/env python3
"""Regression tests for lossless PDF content-stream deskew."""

import io
import math
import tempfile
import unittest
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from pdf_preprocess_skew import SkewDetector
from pdf_stream_deskew import (
    _bounded_detection_dpi,
    _content_rotation_matrix,
    deskew_pdf_content_streams,
)


def make_rotated_scan(rotation_angle: float) -> bytes:
    image = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(image)
    for y in range(240, 1500, 90):
        draw.rectangle((160, y, 1080, y + 12), fill="black")
    image = image.rotate(rotation_angle, fillcolor="white")

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=buffer.getvalue())
    document_bytes = document.tobytes()
    document.close()
    return document_bytes


class PdfStreamDeskewTest(unittest.TestCase):
    def test_rotates_content_stream_and_preserves_image_bytes(self):
        detector = SkewDetector(skew_threshold=0.3)
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.pdf"
            output_path = Path(tmpdir) / "output.pdf"
            with fitz.open(stream=make_rotated_scan(1.4), filetype="pdf") as source:
                original_xref = source[0].get_images(full=True)[0][0]
                original_image = source.xref_stream_raw(original_xref)
                source.save(input_path)

            result = deskew_pdf_content_streams(
                input_path,
                output_path,
                detection_dpi=72,
                quiet=True,
            )

            self.assertEqual(result["deskewed_pages"], 1)
            self.assertLess(abs(result["pages"][0]["residual_angle"]), 0.3)
            with fitz.open(input_path) as source, fitz.open(output_path) as output:
                output_xref = output[0].get_images(full=True)[0][0]
                self.assertEqual(output.xref_stream_raw(output_xref), original_image)
                self.assertEqual(output[0].rect, source[0].rect)

                pixmap = output[0].get_pixmap(dpi=72, alpha=False)
                rendered = Image.frombytes(
                    "RGB", (pixmap.width, pixmap.height), pixmap.samples
                )
                self.assertLessEqual(abs(detector.detect(rendered).angle), 0.3)

    def test_blank_page_is_copied_without_rewrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "blank.pdf"
            output_path = Path(tmpdir) / "output.pdf"
            document = fitz.open()
            document.new_page(width=595, height=842)
            document.save(input_path)
            document.close()
            original_bytes = input_path.read_bytes()

            result = deskew_pdf_content_streams(
                input_path,
                output_path,
                detection_dpi=72,
                quiet=True,
            )

            self.assertEqual(result["deskewed_pages"], 0)
            self.assertEqual(output_path.read_bytes(), original_bytes)

    def test_large_skew_is_reported_instead_of_collapsing_to_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "large-skew.pdf"
            output_path = Path(tmpdir) / "output.pdf"
            with fitz.open(stream=make_rotated_scan(6.0), filetype="pdf") as source:
                source.save(input_path)

            result = deskew_pdf_content_streams(
                input_path,
                output_path,
                detection_dpi=72,
                quiet=True,
            )

            record = result["pages"][0]
            self.assertGreater(abs(record["detected_angle"]), 5.0)
            self.assertEqual(record["reason"], "above_safe_limit")
            self.assertEqual(record["action"], "not_changed")

    def test_rotation_preserves_media_box_centre_with_nonzero_origin(self):
        box = fitz.Rect(1000, 0, 1595, 842)
        matrix = _content_rotation_matrix(box, 1.4)
        self.assertIsNotNone(matrix)
        a, b, c, _d, e, f = [float(value) for value in matrix.split()[:6]]
        center_x = (box.x0 + box.x1) / 2
        center_y = (box.y0 + box.y1) / 2
        transformed_x = a * center_x + c * center_y + e
        transformed_y = b * center_x + _d * center_y + f
        self.assertAlmostEqual(transformed_x, center_x, delta=1e-6)
        self.assertAlmostEqual(transformed_y, center_y, delta=1e-6)
        self.assertAlmostEqual(math.hypot(a, b), 1.0, delta=0.05)

    def test_detection_render_is_pixel_bounded(self):
        normal = fitz.Rect(0, 0, 595, 842)
        self.assertEqual(_bounded_detection_dpi(normal, 150, 25_000_000), (150, None))

        oversized = fitz.Rect(0, 0, 7200, 7200)
        dpi, reason = _bounded_detection_dpi(oversized, 150, 25_000_000)
        self.assertLessEqual(dpi, 150)
        self.assertEqual(reason, "detection_dpi_reduced")
        pixels = oversized.width * dpi / 72.0 * (oversized.height * dpi / 72.0)
        self.assertLessEqual(pixels, 25_000_000)

        impossible = fitz.Rect(0, 0, 1_000_000, 1_000_000)
        self.assertEqual(
            _bounded_detection_dpi(impossible, 150, 25_000_000),
            (0, "page_too_large_for_detection"),
        )


if __name__ == "__main__":
    unittest.main()
