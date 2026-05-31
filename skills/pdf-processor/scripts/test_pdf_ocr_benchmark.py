#!/usr/bin/env python3
"""Regression tests for OCR benchmark helpers."""

import argparse
import importlib.util
import tempfile
import unittest
from pathlib import Path

import fitz

SCRIPT_DIR = Path(__file__).parent


def load_module(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_DIR / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark = load_module("pdf_ocr_benchmark", "pdf-ocr-benchmark.py")


def make_text_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=200, height=300)
    page.insert_text((20, 40), "Rehab Hospital PAGE 1")
    page = doc.new_page(width=300, height=200)
    page.insert_text((20, 40), "Suzhou Hospital PAGE 2")
    doc.save(path)
    doc.close()


class PdfOcrBenchmarkTest(unittest.TestCase):
    def test_pdf_metrics_collects_text_size_and_keyword_hits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "input.pdf"
            make_text_pdf(pdf_path)

            metrics = benchmark.pdf_metrics(pdf_path, keywords=["Rehab", "missing"])

            self.assertEqual(metrics["pages"], 2)
            self.assertTrue(metrics["searchable"])
            self.assertEqual(metrics["pages_with_text"], 2)
            self.assertGreater(metrics["text_chars"], 0)
            self.assertEqual(metrics["keyword_hits"]["Rehab"], 1)
            self.assertEqual(metrics["keyword_hits"]["missing"], 0)

    def test_create_sample_pdf_keeps_first_n_pages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            pdf_path = tmpdir_path / "input.pdf"
            make_text_pdf(pdf_path)

            sample_path = benchmark.create_sample_pdf(pdf_path, tmpdir_path, 1)
            metrics = benchmark.pdf_metrics(sample_path)

            self.assertEqual(metrics["pages"], 1)
            self.assertEqual(metrics["page_sizes"], [(200.0, 300.0)])

    def test_build_ocr_command_includes_preprocess_flags_and_passthrough(self):
        args = argparse.Namespace(
            backend="local_ocrmypdf",
            mode="redo",
            language="chi_sim+eng",
            output_type="pdf",
            optimize=0,
            compress_level="medium",
            tesseract_timeout=180,
            no_env_file=True,
            env_file=None,
            api_order=None,
            jobs=4,
            skip_preprocess=False,
            skip_coarse_rotation=True,
            preprocess_jobs=6,
            preprocess_chunk_pages=80,
            dpi=None,
            skew_threshold=None,
            pdf_jpeg_quality=None,
            enable_crop=False,
            no_compress=False,
            no_merge_preprocess_compress=False,
            passthrough=["--", "--skip-pages", "1"],
        )

        command = benchmark.build_ocr_command(
            args,
            Path("/tmp/in.pdf"),
            Path("/tmp/out.pdf"),
        )

        self.assertIn("--skip-coarse-rotation", command)
        self.assertIn("--preprocess-jobs", command)
        self.assertIn("6", command)
        self.assertIn("--preprocess-chunk-pages", command)
        self.assertIn("80", command)
        self.assertIn("--skip-pages", command)
        self.assertNotIn("--", command)


if __name__ == "__main__":
    unittest.main()
