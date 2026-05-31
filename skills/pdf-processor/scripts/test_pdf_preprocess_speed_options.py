#!/usr/bin/env python3
"""Regression tests for preprocessing speed options."""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

import fitz
from PIL import Image

SCRIPT_DIR = Path(__file__).parent


def load_module(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_DIR / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preprocess_core = load_module("pdf_preprocess_core", "pdf-preprocess-core.py")
preprocess_ocr = load_module("pdf_preprocess_ocr", "pdf-preprocess-ocr.py")


class PreprocessSpeedOptionsTest(unittest.TestCase):
    def test_process_page_skips_unused_page_analysis_by_default(self):
        preprocessor = preprocess_core.PDFPreprocessor(enable_coarse_rotation=False)
        image = Image.new("RGB", (300, 400), "white")

        def fail_if_called(_image):
            self.fail("unused page analysis should be skipped")

        preprocessor.analyze_page = fail_if_called

        _processed, result = preprocessor.process_page(
            image,
            enable_crop=False,
            restore_original_size=True,
        )

        self.assertEqual(result.method_used, "none")

    def test_can_skip_coarse_rotation_detection(self):
        preprocessor = preprocess_core.PDFPreprocessor(enable_coarse_rotation=False)
        image = Image.new("RGB", (300, 400), "white")

        def fail_if_called(_image):
            self.fail("coarse rotation detection should be skipped")

        preprocessor.coarse_rotation_detect = fail_if_called

        _processed, result = preprocessor.process_page(
            image,
            enable_crop=False,
            restore_original_size=True,
        )

        self.assertEqual(result.rotation_angle, 0.0)
        self.assertEqual(result.confidence, 0.0)

    def test_preprocess_dpi_defaults_to_compression_profile(self):
        self.assertEqual(preprocess_ocr.resolve_preprocess_dpi(None, False, "low"), 300)
        self.assertEqual(preprocess_ocr.resolve_preprocess_dpi(None, False, "medium"), 200)
        self.assertEqual(preprocess_ocr.resolve_preprocess_dpi(None, False, "high"), 150)
        self.assertEqual(preprocess_ocr.resolve_preprocess_dpi(None, True, "medium"), 300)
        self.assertEqual(preprocess_ocr.resolve_preprocess_dpi(240, False, "medium"), 240)

    def test_merged_preprocess_output_uses_compression_profile(self):
        options = preprocess_ocr.resolve_preprocess_output_options(
            explicit_dpi=None,
            explicit_jpeg_quality=None,
            no_compress=False,
            compress_level="medium",
            merge_preprocess_compress=True,
        )

        self.assertEqual(options["dpi"], 200)
        self.assertEqual(options["pdf_jpeg_quality"], 72)
        self.assertEqual(options["pdf_jpeg_subsampling"], 1)
        self.assertTrue(options["pdf_jpeg_optimize"])

    def test_explicit_preprocess_output_options_are_preserved(self):
        options = preprocess_ocr.resolve_preprocess_output_options(
            explicit_dpi=240,
            explicit_jpeg_quality=82,
            no_compress=False,
            compress_level="medium",
            merge_preprocess_compress=True,
        )

        self.assertEqual(options["dpi"], 240)
        self.assertEqual(options["pdf_jpeg_quality"], 82)

    def test_standalone_compress_is_skipped_only_after_merged_preprocess(self):
        self.assertFalse(
            preprocess_ocr.should_run_standalone_compress(
                no_compress=False,
                preprocessed=True,
                merge_preprocess_compress=True,
            )
        )
        self.assertTrue(
            preprocess_ocr.should_run_standalone_compress(
                no_compress=False,
                preprocessed=False,
                merge_preprocess_compress=True,
            )
        )

    def test_preprocess_only_output_copies_file_and_uses_original_timestamp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            original_path = tmpdir_path / "original.pdf"
            source_path = tmpdir_path / "working.pdf"
            output_path = tmpdir_path / "output.pdf"

            original_path.write_bytes(b"original")
            source_path.write_bytes(b"processed")
            original_mtime = 1_700_000_000
            os.utime(original_path, (original_mtime, original_mtime))

            preprocess_ocr.write_preprocess_only_output(
                source_path,
                output_path,
                original_path,
            )

            self.assertEqual(output_path.read_bytes(), b"processed")
            self.assertAlmostEqual(output_path.stat().st_mtime, original_mtime, delta=1)

    def test_preprocess_only_output_dry_run_does_not_write_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            original_path = tmpdir_path / "original.pdf"
            source_path = tmpdir_path / "working.pdf"
            output_path = tmpdir_path / "output.pdf"

            original_path.write_bytes(b"original")
            source_path.write_bytes(b"processed")

            preprocess_ocr.write_preprocess_only_output(
                source_path,
                output_path,
                original_path,
                dry_run=True,
            )

            self.assertFalse(output_path.exists())

    def test_save_images_as_pdf_preserves_explicit_page_sizes(self):
        image = Image.new("RGB", (1656, 2340), "white")
        page_size = (595.92, 842.4)

        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            preprocess_core.save_images_as_pdf(
                [image],
                tmp.name,
                dpi=200,
                jpeg_quality=90,
                jpeg_subsampling=0,
                jpeg_optimize=False,
                page_sizes=[page_size],
            )

            with fitz.open(tmp.name) as doc:
                self.assertEqual(len(doc), 1)
                self.assertAlmostEqual(doc[0].rect.width, page_size[0], places=2)
                self.assertAlmostEqual(doc[0].rect.height, page_size[1], places=2)

    def test_preprocess_jobs_default_serial_and_auto_is_bounded(self):
        self.assertEqual(preprocess_core.resolve_preprocess_jobs(None, 10), 1)
        self.assertEqual(preprocess_core.resolve_preprocess_jobs(1, 10), 1)
        self.assertEqual(preprocess_core.resolve_preprocess_jobs(99, 3), 3)
        self.assertGreaterEqual(preprocess_core.resolve_preprocess_jobs(0, 10), 1)
        self.assertLessEqual(preprocess_core.resolve_preprocess_jobs(0, 10), 10)

    def test_preprocess_chunk_pages_default_disabled_and_bounded(self):
        self.assertEqual(preprocess_core.resolve_preprocess_chunk_pages(None, 10), 0)
        self.assertEqual(preprocess_core.resolve_preprocess_chunk_pages(0, 10), 0)
        self.assertEqual(preprocess_core.resolve_preprocess_chunk_pages(99, 3), 3)
        self.assertEqual(preprocess_core.resolve_preprocess_chunk_pages(2, 10), 2)

    def test_chunked_process_pdf_preserves_page_sizes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.pdf"
            output_path = Path(tmpdir) / "output.pdf"

            doc = fitz.open()
            page = doc.new_page(width=200, height=300)
            page.insert_text((20, 40), "PAGE 1")
            page = doc.new_page(width=300, height=200)
            page.insert_text((20, 40), "PAGE 2")
            doc.save(input_path)
            doc.close()

            stats = preprocess_core.process_pdf(
                str(input_path),
                str(output_path),
                dpi=72,
                enable_coarse_rotation=False,
                enable_crop=False,
                pdf_jpeg_quality=70,
                pdf_jpeg_subsampling=2,
                pdf_jpeg_optimize=False,
                preprocess_jobs=1,
                preprocess_chunk_pages=1,
                verbose=False,
            )

            with fitz.open(output_path) as out_doc:
                self.assertEqual(len(out_doc), 2)
                self.assertAlmostEqual(out_doc[0].rect.width, 200, places=2)
                self.assertAlmostEqual(out_doc[0].rect.height, 300, places=2)
                self.assertAlmostEqual(out_doc[1].rect.width, 300, places=2)
                self.assertAlmostEqual(out_doc[1].rect.height, 200, places=2)

            self.assertEqual(stats["preprocess_chunk_pages"], 1)
            self.assertEqual(stats["total_pages"], 2)

    def test_single_page_pdf_with_chunk_request_still_writes_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.pdf"
            output_path = Path(tmpdir) / "output.pdf"

            doc = fitz.open()
            page = doc.new_page(width=200, height=300)
            page.insert_text((20, 40), "PAGE 1")
            doc.save(input_path)
            doc.close()

            stats = preprocess_core.process_pdf(
                str(input_path),
                str(output_path),
                dpi=72,
                enable_coarse_rotation=False,
                enable_crop=False,
                pdf_jpeg_quality=70,
                pdf_jpeg_subsampling=2,
                pdf_jpeg_optimize=False,
                preprocess_jobs=1,
                preprocess_chunk_pages=1,
                verbose=False,
            )

            self.assertEqual(stats["preprocess_chunk_pages"], 0)
            with fitz.open(output_path) as out_doc:
                self.assertEqual(len(out_doc), 1)
                self.assertAlmostEqual(out_doc[0].rect.width, 200, places=2)
                self.assertAlmostEqual(out_doc[0].rect.height, 300, places=2)
            self.assertEqual(stats["total_pages"], 1)


if __name__ == "__main__":
    unittest.main()
