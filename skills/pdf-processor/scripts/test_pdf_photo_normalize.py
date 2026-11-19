#!/usr/bin/env python3
"""Regression tests for photographed document normalization."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
import fitz
from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).parent


def load_module():
    spec = importlib.util.spec_from_file_location(
        "pdf_photo_normalize",
        SCRIPT_DIR / "pdf-photo-normalize.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load pdf-photo-normalize.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


photo_normalize = load_module()


def make_document_photo(
    background: str = "steelblue",
    shadow: bool = False,
) -> Image.Image:
    image = Image.new("RGB", (900, 1200), background)
    draw = ImageDraw.Draw(image)
    draw.polygon(((170, 120), (800, 180), (740, 1080), (110, 1010)), fill="white")
    document = ImageDraw.Draw(image)
    for offset, y in enumerate((300, 370, 440, 510)):
        document.rectangle((240, y + offset * 4, 660, y + 22 + offset * 4), fill="black")
    if shadow:
        shadow_array = np.asarray(image).astype(np.int16)
        gradient = np.linspace(-170, 0, num=image.width, dtype=np.int16)
        shadow_array += gradient[None, :, None]
        image = Image.fromarray(np.clip(shadow_array, 0, 255).astype(np.uint8))
    return image


class PhotoNormalizeTest(unittest.TestCase):
    def test_load_photo_bakes_exif_orientation(self):
        image = make_document_photo()
        exif = image.getexif()
        exif[274] = 6
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "oriented.jpg"
            image.save(path, exif=exif)

            loaded = photo_normalize.load_photo(path)

        self.assertEqual(loaded.size, (1200, 900))

    def test_detects_document_quad(self):
        quad = photo_normalize.detect_document_quad(make_document_photo())

        self.assertIsNotNone(quad)
        self.assertEqual(quad.shape, (4, 2))
        self.assertTrue(photo_normalize._quad_is_convex(photo_normalize._order_quad(quad)))

    def test_perspective_normalize_outputs_rectangle(self):
        image = make_document_photo()
        quad = photo_normalize.detect_document_quad(image)

        transform, size, metadata = photo_normalize._paper_projection(image.size, quad)
        normalized = photo_normalize._warp_image(image, transform, size)

        self.assertTrue(metadata["quad_detected"])
        self.assertEqual(normalized.shape[:2], (size[1], size[0]))
        self.assertLess(size[0] / size[1], 1.0)
        self.assertGreater(size[0], 300)
        self.assertGreater(size[1], 400)

    def test_table_projection_corrects_an_inner_rule_and_keeps_the_paper(self):
        page = Image.new("RGB", (800, 1100), "white")
        draw = ImageDraw.Draw(page)
        draw.rectangle((140, 190, 680, 900), outline="black", width=3)
        for row in (335, 490, 720):
            draw.line((140, row, 680, row), fill="black", width=3)
        draw.line((240, 190, 240, 900), fill="black", width=3)

        cv2 = photo_normalize.cv2
        corners = photo_normalize._image_corners(page.size)
        camera = cv2.getPerspectiveTransform(
            corners, np.float32([[20, 7], [792, 24], [763, 1080], [4, 1092]])
        )
        captured = Image.fromarray(photo_normalize._warp_image(page, camera, page.size))
        correction, output_size, report = photo_normalize._table_projection(captured)
        self.assertEqual(report["status"], "applied")

        inner_rule = np.float32([[[240, 200], [240, 890]]])
        before = cv2.perspectiveTransform(inner_rule, camera)[0]
        after = cv2.perspectiveTransform(inner_rule, correction @ camera)[0]
        self.assertGreater(abs(before[1, 0] - before[0, 0]), 5)
        self.assertLess(abs(after[1, 0] - after[0, 0]), 2)

        projected_paper = cv2.perspectiveTransform(corners[None], correction)[0]
        self.assertTrue(np.all(projected_paper >= -0.001))
        self.assertTrue(np.all(projected_paper <= np.array(output_size) - 1 + 0.001))

    def test_single_tilted_outline_does_not_trigger_table_projection(self):
        page = Image.new("RGB", (800, 1100), "white")
        draw = ImageDraw.Draw(page)
        draw.polygon(((160, 180), (670, 200), (685, 885), (150, 900)), outline="black", width=3)

        matrix, size, report = photo_normalize._table_projection(page)

        self.assertEqual(report["status"], "no_reliable_frame")
        self.assertEqual(size, page.size)
        np.testing.assert_array_equal(matrix, np.eye(3))

    def test_shadow_normalization_reduces_block_variation(self):
        image = make_document_photo(shadow=True)

        enhanced = photo_normalize.normalize_illumination(image)

        self.assertLess(
            photo_normalize._shadow_score(enhanced),
            photo_normalize._shadow_score(image),
        )

    def test_shadow_normalization_reduces_color_cast(self):
        tinted_array = np.full((400, 300, 3), (226, 234, 245), dtype=np.uint8)
        image = Image.fromarray(tinted_array)

        enhanced = photo_normalize.normalize_illumination(image)
        enhanced_array = np.asarray(enhanced)

        self.assertLess(
            float(enhanced_array[:, :, 2].mean() - enhanced_array[:, :, 0].mean()),
            float(tinted_array[:, :, 2].mean() - tinted_array[:, :, 0].mean()),
        )

    def test_contrast_enhances_ink_and_preserves_faint_line_and_stamp(self):
        page = Image.new("RGB", (400, 540), (210, 210, 210))
        draw = ImageDraw.Draw(page)
        draw.line((70, 180, 330, 180), fill=(100, 100, 100), width=3)
        draw.line((70, 260, 330, 260), fill=(175, 175, 175), width=2)
        draw.ellipse((135, 355, 265, 485), outline=(157, 67, 67), width=3)

        base = np.asarray(photo_normalize.normalize_illumination(page, contrast_strength=0))
        boosted = np.asarray(photo_normalize.normalize_illumination(page))

        self.assertGreater(
            boosted[170, 200].mean() - boosted[180, 200].mean(),
            base[170, 200].mean() - base[180, 200].mean() + 10,
        )
        self.assertGreater(boosted[252, 200].mean() - boosted[260, 200].mean(), 12)
        self.assertGreater(int(boosted[355, 200, 0]) - int(boosted[355, 200, 1]), 30)

    def test_auto_page_size_uses_a4_for_document_ratio(self):
        portrait_size, portrait_policy = photo_normalize.resolve_page_size(
            (2480, 3508), "auto", 300
        )
        landscape_size, landscape_policy = photo_normalize.resolve_page_size(
            (3508, 2480), "auto", 300
        )

        self.assertEqual(portrait_size, (2480, 3508))
        self.assertEqual(portrait_policy, "auto_a4")
        self.assertEqual(landscape_size, (3508, 2480))
        self.assertEqual(landscape_policy, "auto_a4")
        narrow_size, narrow_policy = photo_normalize.resolve_page_size(
            (2480, 3224), "auto", 300
        )
        self.assertEqual(narrow_size, (2480, 3508))
        self.assertEqual(narrow_policy, "auto_a4")

    def test_default_pdf_canvas_is_exact_a4_with_undistorted_photo(self):
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "wide.png"
            target = Path(tempdir) / "output.pdf"
            Image.new("RGB", (720, 400), "white").save(source)

            metadata = photo_normalize.normalize_photo_pdf(source, target, dpi=110, rotation="0")
            self.assertEqual(metadata["page_size"], "a4")
            self.assertEqual(metadata["table_alignment"]["status"], "no_paper_quad")
            content_width, content_height = metadata["content_size"]
            self.assertAlmostEqual(content_width / content_height, 720 / 400, delta=0.004)
            self.assertLess(content_height, metadata["output_size"][1])
            with fitz.open(target) as document:
                self.assertEqual(len(document), 1)
                self.assertAlmostEqual(document[0].rect.width * 25.4 / 72, 297, places=3)
                self.assertAlmostEqual(document[0].rect.height * 25.4 / 72, 210, places=3)

    def test_pipeline_rejects_overwriting_source(self):
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "photo.jpg"
            make_document_photo().save(source)

            with self.assertRaisesRegex(ValueError, "不能覆盖"):
                photo_normalize.normalize_photo_pdf(source, source)


if __name__ == "__main__":
    unittest.main()
