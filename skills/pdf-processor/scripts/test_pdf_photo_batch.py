#!/usr/bin/env python3
"""Regression tests for batch photo normalization."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz
from PIL import Image, ImageDraw


SCRIPT_DIR = Path(__file__).parent


def load_module():
    spec = importlib.util.spec_from_file_location(
        "pdf_photo_batch", SCRIPT_DIR / "pdf-photo-batch.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load pdf-photo-batch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


photo_batch = load_module()


def make_partial_page(label: str) -> Image.Image:
    image = Image.new("RGB", (900, 650), "steelblue")
    draw = ImageDraw.Draw(image)
    for top in range(130, 430, 45):
        draw.rectangle((220, top, 690, top + 18), fill="black")
    draw.rectangle((250, 475, 530, 493), fill=(20, 20, 140))
    draw.text((270, 90), label, fill="black")
    return image


class PhotoBatchTest(unittest.TestCase):
    def test_collects_directory_photos_in_natural_order(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "b2.jpg").touch()
            (root / "a.jpg").touch()
            (root / "a10.jpg").touch()
            (root / "a2.png").touch()
            (root / "notes.txt").touch()

            photos = photo_batch.collect_photo_paths([str(root)])

        self.assertEqual(
            [path.name for path in photos],
            ["a.jpg", "a2.png", "a10.jpg", "b2.jpg"],
        )

    def test_rejects_directory_without_photos(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(ValueError, "未找到"):
                photo_batch.collect_photo_paths([tempdir])

    def test_batch_outputs_one_ordered_page_per_photo(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            for name in ("record-2.png", "record-10.png"):
                make_partial_page(name).save(root / name)
            output = root / "merged.pdf"
            report_path = root / "report.json"

            report = photo_batch.normalize_photo_batch(
                [str(root)], output, dpi=80, rotation="0", report_file=report_path,
            )

            self.assertEqual(report["photo_count"], 2)
            self.assertEqual(report["page_count"], 2)
            self.assertEqual(
                [item["page_number"] for item in report["photos"]], [1, 2]
            )
            self.assertTrue(all(
                item["quad"]["source"] == "content_subject" for item in report["photos"]
            ))
            saved = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["page_count"], 2)
            with fitz.open(output) as document:
                self.assertEqual(len(document), 2)
                for page in document:
                    self.assertAlmostEqual(page.rect.width * 25.4 / 72, 297, places=2)
                    self.assertAlmostEqual(page.rect.height * 25.4 / 72, 210, places=2)

    def test_batch_does_not_write_partial_pdf_when_any_page_fails(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "01-broken.jpg").write_bytes(b"not an image")
            make_partial_page("valid").save(root / "02-valid.png")
            output = root / "merged.pdf"
            report_path = root / "report.json"

            with self.assertRaises(OSError):
                photo_batch.normalize_photo_batch(
                    [str(root)], output, dpi=60, rotation="0", report_file=report_path,
                )

            self.assertFalse(output.exists())
            self.assertFalse(report_path.exists())

    def test_batch_rolls_back_pdf_when_report_publish_fails(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            make_partial_page("single").save(root / "record.png")
            output = root / "merged.pdf"
            report_path = root / "report.json"

            def fail_report(source, destination):
                if destination == report_path:
                    raise OSError("disk full")
                return original_publish(source, destination)

            original_publish = photo_batch._publish_exclusive
            with patch.object(
                photo_batch, "_publish_exclusive", side_effect=fail_report
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    photo_batch.normalize_photo_batch(
                        [str(root)], output, dpi=60, rotation="0", report_file=report_path,
                    )

            self.assertFalse(output.exists())
            self.assertFalse(report_path.exists())

    def test_publish_failure_does_not_delete_existing_destination(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            source = root / "source.bin"
            destination = root / "destination.bin"
            source.write_bytes(b"ours")
            destination.write_bytes(b"external")

            with self.assertRaises(FileExistsError):
                photo_batch._publish_exclusive(source, destination)

            self.assertEqual(destination.read_bytes(), b"external")


if __name__ == "__main__":
    unittest.main()
