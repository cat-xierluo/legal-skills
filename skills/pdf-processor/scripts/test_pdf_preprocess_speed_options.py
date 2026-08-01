#!/usr/bin/env python3
"""Regression tests for preprocessing speed options."""

import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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
quality_check = load_module("pdf_ocr_quality_check", "pdf-ocr-quality-check.py")


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

    def test_tesseract_osd_lowercase_dict_maps_to_pil_rotation(self):
        preprocessor = preprocess_core.PDFPreprocessor()
        image = Image.new("RGB", (300, 400), "white")
        osd = {"orientation": 90, "rotate": 270, "orientation_conf": 12.5}
        with mock.patch.object(preprocess_core.pytesseract, "image_to_osd", return_value=osd):
            angle, confidence = preprocessor._tesseract_osd(image)
        self.assertEqual(angle, 90.0)
        self.assertEqual(confidence, 1.0)

    def test_preprocess_dpi_defaults_to_compression_profile(self):
        self.assertEqual(preprocess_ocr.resolve_preprocess_dpi(None, False, "low"), 300)
        self.assertEqual(preprocess_ocr.resolve_preprocess_dpi(None, False, "medium"), 200)
        self.assertEqual(preprocess_ocr.resolve_preprocess_dpi(None, False, "high"), 150)
        self.assertEqual(preprocess_ocr.resolve_preprocess_dpi(None, True, "medium"), 300)
        self.assertEqual(preprocess_ocr.resolve_preprocess_dpi(240, False, "medium"), 240)

    def test_preprocess_pixel_guard_keeps_normal_page_dpi(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "normal.pdf"
            doc = fitz.open()
            doc.new_page(width=595, height=842)
            doc.save(pdf_path)
            doc.close()

            result = preprocess_ocr.resolve_bounded_preprocess_dpi(
                pdf_path,
                requested_dpi=200,
                max_megapixels=25,
            )

            self.assertEqual(result["effective_dpi"], 200)
            self.assertFalse(result["capped"])
            self.assertLess(result["predicted_megapixels"], 25)

    def test_preprocess_pixel_guard_caps_abnormal_page_dpi(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "oversized-canvas.pdf"
            doc = fitz.open()
            doc.new_page(width=2305, height=3310)
            doc.save(pdf_path)
            doc.close()

            result = preprocess_ocr.resolve_bounded_preprocess_dpi(
                pdf_path,
                requested_dpi=200,
                max_megapixels=25,
            )

            self.assertEqual(result["effective_dpi"], 130)
            self.assertTrue(result["capped"])
            self.assertGreater(result["predicted_megapixels"], 50)
            self.assertLessEqual(result["effective_megapixels"], 25)

    def test_preprocess_pixel_guard_can_be_disabled(self):
        result = preprocess_ocr.resolve_bounded_preprocess_dpi(
            "not-opened-when-disabled.pdf",
            requested_dpi=300,
            max_megapixels=0,
        )
        self.assertEqual(result["effective_dpi"], 300)
        self.assertFalse(result["capped"])
        self.assertEqual(result["reason"], "disabled")

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

    def test_local_ocr_prefers_ocrmypdf_native_preprocess(self):
        base = {
            "backend": "auto",
            "local_only": True,
            "external_backend_configured": True,
            "skip_preprocess": False,
            "preprocess_only": False,
            "enable_crop": False,
            "force_raster_preprocess": False,
        }
        self.assertTrue(preprocess_ocr.should_use_ocrmypdf_native_preprocess(**base))
        self.assertTrue(
            preprocess_ocr.should_use_ocrmypdf_native_preprocess(
                **{**base, "backend": "local_ocrmypdf", "local_only": False}
            )
        )
        self.assertTrue(
            preprocess_ocr.should_use_ocrmypdf_native_preprocess(
                **{
                    **base,
                    "local_only": False,
                    "external_backend_configured": False,
                }
            )
        )

    def test_local_native_preprocess_respects_explicit_overrides(self):
        base = {
            "backend": "local_ocrmypdf",
            "local_only": False,
            "external_backend_configured": False,
            "skip_preprocess": False,
            "preprocess_only": False,
            "enable_crop": False,
            "force_raster_preprocess": False,
        }
        for override in (
            {"skip_preprocess": True},
            {"preprocess_only": True},
            {"enable_crop": True},
            {"force_raster_preprocess": True},
        ):
            with self.subTest(override=override):
                self.assertFalse(
                    preprocess_ocr.should_use_ocrmypdf_native_preprocess(
                        **{**base, **override}
                    )
                )

        self.assertFalse(
            preprocess_ocr.should_use_ocrmypdf_native_preprocess(
                **{
                    **base,
                    "backend": "auto",
                    "external_backend_configured": True,
                }
            )
        )

    def test_configured_external_order_defaults_to_paddle(self):
        self.assertEqual(
            preprocess_ocr.resolve_configured_external_order(
                None, paddle_configured=True, mineru_configured=True,
            ),
            ["paddle", "mineru"],
        )
        self.assertEqual(
            preprocess_ocr.resolve_configured_external_order(
                "mineru,paddle", paddle_configured=True, mineru_configured=True,
            ),
            ["mineru", "paddle"],
        )

    def test_paddle_prefers_original_pdf_input(self):
        base = {
            "backend": "paddle_api",
            "local_only": False,
            "paddle_selected_by_auto": True,
            "skip_preprocess": False,
            "preprocess_only": False,
            "enable_crop": False,
            "force_raster_preprocess": False,
        }
        self.assertTrue(preprocess_ocr.should_use_paddle_original_input(**base))
        self.assertTrue(
            preprocess_ocr.should_use_paddle_original_input(
                **{**base, "backend": "auto"}
            )
        )
        self.assertFalse(
            preprocess_ocr.should_use_paddle_original_input(
                **{
                    **base,
                    "backend": "auto",
                    "paddle_selected_by_auto": False,
                }
            )
        )

    def test_paddle_original_pdf_respects_explicit_preprocess_requests(self):
        base = {
            "backend": "paddle_api",
            "local_only": False,
            "paddle_selected_by_auto": True,
            "skip_preprocess": False,
            "preprocess_only": False,
            "enable_crop": False,
            "force_raster_preprocess": False,
        }
        for override in (
            {"skip_preprocess": True},
            {"preprocess_only": True},
            {"enable_crop": True},
            {"force_raster_preprocess": True},
        ):
            with self.subTest(override=override):
                self.assertFalse(
                    preprocess_ocr.should_use_paddle_original_input(
                        **{**base, **override}
                    )
                )

    def test_layer_classifier_protects_digital_and_hybrid_pdfs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            digital_path = Path(tmpdir) / "digital.pdf"
            hybrid_path = Path(tmpdir) / "hybrid.pdf"

            doc = fitz.open()
            page = doc.new_page(width=200, height=300)
            page.insert_text((20, 40), "digital text")
            doc.save(digital_path)
            doc.close()

            image = Image.new("RGB", (20, 20), "white")
            image_bytes = io.BytesIO()
            image.save(image_bytes, format="PNG")
            doc = fitz.open()
            page = doc.new_page(width=200, height=300)
            page.insert_text((20, 40), "hybrid text")
            page.insert_image(fitz.Rect(20, 60, 80, 120), stream=image_bytes.getvalue())
            page.add_rect_annot(fitz.Rect(15, 15, 100, 50))
            doc.save(hybrid_path)
            doc.close()

            digital = preprocess_ocr.classify_pdf_layer_content(digital_path)
            hybrid = preprocess_ocr.classify_pdf_layer_content(hybrid_path)
            self.assertEqual(digital["kind"], "digital")
            self.assertEqual(hybrid["kind"], "hybrid")
            self.assertEqual(hybrid["annotation_pages"], 1)

    def test_preprocess_only_preserves_hybrid_pdf_bytes_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "hybrid.pdf"
            output_path = Path(tmpdir) / "output.pdf"
            image = Image.new("RGB", (20, 20), "white")
            image_bytes = io.BytesIO()
            image.save(image_bytes, format="PNG")
            doc = fitz.open()
            page = doc.new_page(width=200, height=300)
            page.insert_text((20, 40), "preserve text")
            page.insert_image(fitz.Rect(20, 60, 80, 120), stream=image_bytes.getvalue())
            page.add_rect_annot(fitz.Rect(15, 15, 100, 50))
            doc.save(input_path)
            doc.close()

            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT_DIR / "pdf-preprocess-ocr.py"),
                    "-i", str(input_path), "-o", str(output_path),
                    "--preprocess-only", "--quiet",
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(output_path.read_bytes(), input_path.read_bytes())
            with fitz.open(output_path) as output_doc:
                self.assertIn("preserve text", output_doc[0].get_text("text"))
                self.assertEqual(len(output_doc[0].get_images(full=True)), 1)
                self.assertIsNotNone(output_doc[0].first_annot)

    def test_pdf_merge_works_with_current_pypdf(self):
        pdf_merge = load_module("pdf_merge_current", "pdf-merge.py")
        with tempfile.TemporaryDirectory() as tmpdir:
            first = Path(tmpdir) / "first.pdf"
            second = Path(tmpdir) / "second.pdf"
            output = Path(tmpdir) / "merged.pdf"
            for path, pages in ((first, 1), (second, 2)):
                doc = fitz.open()
                for _ in range(pages):
                    doc.new_page(width=200, height=300)
                doc.save(path)
                doc.close()
            pdf_merge.merge_pdfs_with_numbering(
                [str(first), str(second)], str(output), add_numbers=False,
            )
            with fitz.open(output) as merged:
                self.assertEqual(len(merged), 3)

    def test_quality_gate_fails_closed_and_accepts_valid_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.pdf"
            valid_path = Path(tmpdir) / "valid.pdf"
            invalid_path = Path(tmpdir) / "invalid.pdf"

            doc = fitz.open()
            doc.new_page(width=200, height=300)
            doc.save(input_path)
            doc.close()

            doc = fitz.open()
            page = doc.new_page(width=200, height=300)
            page.insert_text((20, 40), "searchable contract text")
            doc.save(valid_path)
            doc.close()

            doc = fitz.open()
            doc.new_page(width=200, height=300)
            doc.new_page(width=200, height=300)
            doc.save(invalid_path)
            doc.close()

            checker = SCRIPT_DIR / "pdf-ocr-quality-check.py"
            valid = subprocess.run(
                [sys.executable, str(checker), "-i", str(input_path), "-o", str(valid_path)],
                capture_output=True, text=True,
            )
            invalid = subprocess.run(
                [sys.executable, str(checker), "-i", str(input_path), "-o", str(invalid_path)],
                capture_output=True, text=True,
            )
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            self.assertEqual(invalid.returncode, 2, invalid.stdout + invalid.stderr)

    def test_quality_keyword_matching_ignores_ocr_whitespace_and_width(self):
        self.assertTrue(
            quality_check.keyword_matches_text(
                "医疗损害缴费通知",
                "医 疗 损 害\n缴 费 通 知",
            )
        )
        self.assertTrue(quality_check.keyword_matches_text("ABC合同", "ＡＢＣ 合 同"))

    def test_auto_backend_uses_configured_paddle_by_default(self):
        pdf_ocr = load_module("pdf_ocr_auto_default", "pdf-ocr.py")
        args = SimpleNamespace(
            external_api_order=["paddle"], paddle_api_endpoint="https://example.invalid/ocr",
            mineru_api_base=None, allow_external_upload=False, local_only=False, quiet=True,
            no_paddle_fallback_local=False,
        )
        calls = []
        with mock.patch.object(pdf_ocr, "run_paddle_api_backend", side_effect=lambda _args: calls.append("api")), \
             mock.patch.object(pdf_ocr, "run_local_ocrmypdf_backend", side_effect=lambda _args: calls.append("local")):
            pdf_ocr.run_auto_backend(args)
        self.assertEqual(calls, ["api"])

    def test_auto_backend_local_only_never_uploads(self):
        pdf_ocr = load_module("pdf_ocr_auto_local_only", "pdf-ocr.py")
        args = SimpleNamespace(
            external_api_order=["paddle"], paddle_api_endpoint="https://example.invalid/ocr",
            mineru_api_base=None, allow_external_upload=True, local_only=True, quiet=True,
            no_paddle_fallback_local=False,
        )
        calls = []
        with mock.patch.object(pdf_ocr, "run_paddle_api_backend", side_effect=lambda _args: calls.append("api")), \
             mock.patch.object(pdf_ocr, "run_local_ocrmypdf_backend", side_effect=lambda _args: calls.append("local")):
            pdf_ocr.run_auto_backend(args)
        self.assertEqual(calls, ["local"])

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
