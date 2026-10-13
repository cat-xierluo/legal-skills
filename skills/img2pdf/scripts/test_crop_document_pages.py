#!/usr/bin/env python3
"""Independent CLI/pixel checks with synthetic fixtures, not customer material."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("缺少 Pillow：python3 -m pip install 'Pillow>=10.0.0'", file=sys.stderr)
    raise SystemExit(1)

SCRIPT = Path(__file__).with_name("crop_document_pages.py")


class CropTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="img2pdf-crop-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.png"
        self.image = Image.new("RGB", (200, 500), "#eeeeee")
        draw = ImageDraw.Draw(self.image)
        # Adjacent page, target page with short content and footer, phone UI.
        draw.rectangle((10, 20, 189, 130), fill="white")
        draw.rectangle((30, 80, 160, 95), fill="blue")
        draw.rectangle((10, 140, 189, 394), fill="white")
        draw.rectangle((30, 185, 150, 201), fill="black")
        draw.rectangle((160, 360, 176, 376), fill="red")
        draw.rectangle((30, 30, 140, 45), fill="black")
        self.image.save(self.source)
        self.item = {"source": self.source.name, "source_size": [200, 500],
                     "source_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
                     "document": "synthetic-document", "page": "11",
                     "crop": [10, 140, 190, 395]}
        self.manifest = self.root / "manifest.json"
        self.output = self.root / "output"

    def run_cli(self, pages=None, extra=()):
        self.manifest.write_text(json.dumps({"schema_version": 1, "pages": [self.item] if pages is None else pages}))
        return subprocess.run([sys.executable, str(SCRIPT), "--manifest", str(self.manifest),
                               "--output-dir", str(self.output), *extra],
                              capture_output=True, text=True, timeout=30)

    def rejected(self, result):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.output.exists())

    def test_exact_crop_preserves_sparse_content_and_footer(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        with Image.open(self.output / "0001.png") as cropped:
            expected = self.image.crop((10, 140, 190, 395))
            self.assertEqual(cropped.size, (180, 255))
            self.assertEqual(cropped.tobytes(), expected.tobytes())
            self.assertEqual(cropped.getpixel((150, 220)), (255, 0, 0))
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.item["source_sha256"])
        receipt = json.loads((self.output / "crop_receipt.json").read_text())
        self.assertEqual(receipt["pages"][0]["page"], "11")
        self.assertEqual(receipt["pages"][0]["output_sha256"], hashlib.sha256((self.output / "0001.png").read_bytes()).hexdigest())

    def test_dry_run_writes_nothing(self):
        result = self.run_cli(extra=("--dry-run",))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.output.exists())

    def test_manifest_order_is_output_order(self):
        other = {**self.item, "page": "1", "crop": [10, 20, 190, 131]}
        result = self.run_cli([self.item, other])
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads((self.output / "crop_receipt.json").read_text())
        self.assertEqual([x["page"] for x in receipt["pages"]], ["11", "1"])

    def test_invalid_later_page_does_not_write_earlier_page(self):
        other = {**self.item, "page": "2", "crop": [0, 0, 201, 500]}
        self.rejected(self.run_cli([self.item, other]))

    def test_empty_list(self):
        self.rejected(self.run_cli([]))

    def test_duplicate_identity(self):
        self.rejected(self.run_cli([self.item, self.item]))

    def test_stale_source_hash(self):
        self.item["source_sha256"] = "0" * 64
        self.rejected(self.run_cli())

    def test_resized_coordinates(self):
        self.item["source_size"] = [100, 250]
        self.rejected(self.run_cli())

    def test_zero_area(self):
        self.item["crop"] = [10, 140, 10, 395]
        self.rejected(self.run_cli())

    def test_boolean_coordinates(self):
        self.item["crop"][0] = True
        self.rejected(self.run_cli())

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        old = self.output / "keep.txt"
        old.write_text("keep")
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(list(self.output.iterdir()), [old])
        self.assertEqual(old.read_text(), "keep")


if __name__ == "__main__":
    if sys.argv[1:] == ["--probe-invalid"]:
        # Propagate the actual producer exit status, for the evidence gate's fault case.
        with tempfile.TemporaryDirectory(prefix="img2pdf-crop-fault-") as temp:
            root = Path(temp)
            manifest = root / "empty.json"
            manifest.write_text('{"schema_version":1,"pages":[]}')
            completed = subprocess.run([sys.executable, str(SCRIPT), "--manifest", str(manifest),
                                        "--output-dir", str(root / "output")], timeout=30)
            raise SystemExit(completed.returncode)
    unittest.main()
