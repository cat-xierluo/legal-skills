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

HARNESS_PATH = SCRIPT_DIR.parent / "references" / "v27-alignment-baseline" / "research_harness.py"
_harness_spec = importlib.util.spec_from_file_location("pdf_alignment_research_harness", HARNESS_PATH)
if _harness_spec is None or _harness_spec.loader is None:
    raise RuntimeError("Unable to load alignment research harness")
alignment_harness = importlib.util.module_from_spec(_harness_spec)
_harness_spec.loader.exec_module(alignment_harness)


def make_text_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=200, height=300)
    page.insert_text((20, 40), "Rehab Hospital PAGE 1")
    page = doc.new_page(width=300, height=200)
    page.insert_text((20, 40), "Suzhou Hospital PAGE 2")
    doc.save(path)
    doc.close()


class PdfOcrBenchmarkTest(unittest.TestCase):
    def test_alignment_harness_aggregates_word_rows_to_line(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tsv_path = Path(tmpdir) / "page.tsv"
            tsv_path.write_text(
                "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
                "4\t1\t1\t1\t1\t0\t10\t20\t90\t20\t-1\t\n"
                "5\t1\t1\t1\t1\t1\t10\t20\t40\t20\t90\t合同\n"
                "5\t1\t1\t1\t1\t2\t55\t20\t45\t20\t100\t法院\n",
                encoding="utf-8",
            )
            rows = alignment_harness.parse_tsv(tsv_path, level=4)
            self.assertEqual(len(rows), 1)
            text, score, poly = rows[0]
            self.assertEqual(text, "合同 法院")
            self.assertAlmostEqual(score, 0.95)
            self.assertEqual(poly, [[10, 20], [100, 20], [100, 40], [10, 40]])

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

    def test_pdf_metrics_keyword_hits_ignore_ocr_spaces(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "spaced.pdf"
            doc = fitz.open()
            page = doc.new_page(width=200, height=300)
            page.insert_text((20, 40), "R e h a b  H o s p i t a l")
            doc.save(pdf_path)
            doc.close()

            metrics = benchmark.pdf_metrics(pdf_path, keywords=["Rehab Hospital"])

            self.assertEqual(metrics["keyword_hits"]["Rehab Hospital"], 1)

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
