#!/usr/bin/env python3
"""Regression tests for lossless PDF content-stream deskew."""

import io
import unittest
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from pdf_preprocess_skew import SkewDetector
from pdf_stream_deskew import deskew_pdf_content_streams


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
        with fitz.open(stream=make_rotated_scan(1.4), filetype="pdf") as source:
            original_xref = source[0].get_images(full=True)[0][0]
            original_image = source.xref_stream_raw(original_xref)

        output_path = Path("/tmp/pdf-stream-deskew-regression.pdf")
        with fitz.open(stream=make_rotated_scan(1.4), filetype="pdf") as source:
            source.save(output_path)

        result = deskew_pdf_content_streams(
            output_path,
            output_path.with_suffix(".out.pdf"),
            detection_dpi=72,
            quiet=True,
        )

        self.assertEqual(result["deskewed_pages"], 1)
        with fitz.open(output_path) as source, fitz.open(
            output_path.with_suffix(".out.pdf")
        ) as output:
            output_xref = output[0].get_images(full=True)[0][0]
            self.assertEqual(output.xref_stream_raw(output_xref), original_image)
            self.assertEqual(output[0].rect, source[0].rect)

            pixmap = output[0].get_pixmap(dpi=72, alpha=False)
            rendered = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            residual = detector.detect(rendered).angle
            self.assertLess(abs(residual), 0.31)

    def test_blank_page_is_copied_without_rewrite(self):
        output_path = Path("/tmp/pdf-stream-deskew-blank.pdf")
        document = fitz.open()
        document.new_page(width=595, height=842)
        document.save(output_path)
        document.close()
        original_bytes = output_path.read_bytes()

        result = deskew_pdf_content_streams(
            output_path,
            output_path.with_suffix(".out.pdf"),
            detection_dpi=72,
            quiet=True,
        )

        self.assertEqual(result["deskewed_pages"], 0)
        self.assertEqual(
            output_path.with_suffix(".out.pdf").read_bytes(),
            original_bytes,
        )


if __name__ == "__main__":
    unittest.main()
