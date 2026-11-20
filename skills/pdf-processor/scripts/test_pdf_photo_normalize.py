#!/usr/bin/env python3
"""Regression tests for photographed document normalization."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


def make_partial_document_photo() -> Image.Image:
    image = Image.new("RGB", (1200, 800), "steelblue")
    draw = ImageDraw.Draw(image)
    for top in range(150, 510, 45):
        draw.rectangle((410, top, 880, top + 18), fill="black")
    return image


def make_overlapping_document_photo() -> Image.Image:
    image = Image.new("RGB", (1200, 800), "steelblue")
    draw = ImageDraw.Draw(image)
    for top in range(120, 530, 50):
        draw.rectangle((620, top, 940, top + 20), fill="black")
    for top in (120, 170):
        draw.rectangle((80, top, 270, top + 20), fill="black")
    return image


def make_overlapping_document_photo_with_secondary_stamp() -> Image.Image:
    image = make_overlapping_document_photo()
    draw = ImageDraw.Draw(image)
    draw.ellipse((95, 220, 255, 380), outline=(190, 25, 25), width=14)
    return image


def make_document_photo_with_bottom_text() -> Image.Image:
    image = Image.new("RGB", (1200, 800), "steelblue")
    draw = ImageDraw.Draw(image)
    for top in range(150, 720, 45):
        draw.rectangle((410, top, 880, top + 18), fill="black")
    draw.rectangle((410, 780, 880, 790), fill="black")
    return image


def make_document_photo_with_ground_band() -> Image.Image:
    image = Image.new("RGB", (1200, 800), "steelblue")
    draw = ImageDraw.Draw(image)
    for top in range(150, 620, 45):
        draw.rectangle((410, top, 880, top + 18), fill="black")
    draw.rectangle((0, 770, 1200, 800), fill="black")
    return image


def make_partial_document_with_blank_table() -> Image.Image:
    image = Image.new("RGB", (1200, 800), "steelblue")
    draw = ImageDraw.Draw(image)
    for top in range(150, 430, 45):
        draw.rectangle((410, top, 880, top + 18), fill="black")
    draw.rectangle((360, 500, 940, 735), outline="black", width=3)
    for top in (555, 610, 665):
        draw.line((360, top, 940, top), fill="black", width=3)
    for left in (500, 640, 780):
        draw.line((left, 500, left, 735), fill="black", width=3)
    return image


def make_document_photo_with_wide_bottom_text() -> Image.Image:
    image = Image.new("RGB", (1200, 800), "steelblue")
    draw = ImageDraw.Draw(image)
    for top in range(150, 620, 45):
        draw.rectangle((240, top, 970, top + 18), fill="black")
    draw.rectangle((240, 780, 970, 793), fill="black")
    return image


def make_document_photo_with_stamp_near_overlapping_page() -> Image.Image:
    image = Image.new("RGB", (1200, 800), "steelblue")
    draw = ImageDraw.Draw(image)
    for top in range(150, 620, 50):
        draw.rectangle((150, top, 800, top + 20), fill="black")
    for top in (120, 170):
        draw.rectangle((900, top, 1100, top + 20), fill="black")
    draw.ellipse((820, 580, 980, 740), outline=(185, 35, 35), width=14)
    return image


def make_partial_document_photo_with_stamp() -> Image.Image:
    image = make_partial_document_photo()
    draw = ImageDraw.Draw(image)
    draw.ellipse((925, 540, 1075, 690), outline=(175, 30, 30), width=14)
    return image


def make_partial_document_photo_with_distant_stamp() -> Image.Image:
    image = make_partial_document_photo()
    draw = ImageDraw.Draw(image)
    draw.ellipse((80, 80, 250, 250), outline=(185, 30, 30), width=13)
    return image


def make_partial_document_photo_with_faded_stamp() -> Image.Image:
    image = make_partial_document_photo()
    draw = ImageDraw.Draw(image)
    draw.ellipse((80, 80, 250, 250), outline=(162, 72, 72), width=14)
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

    def test_detects_content_subject_without_full_paper_edges(self):
        subject = photo_normalize.detect_content_subject(make_partial_document_photo())

        self.assertIsNotNone(subject)
        self.assertEqual(subject["component_count"], 8)
        self.assertEqual(subject["total_component_count"], 8)
        self.assertGreater(subject["ink_coverage"], 0.99)
        left, top, right, bottom = subject["bbox"]
        self.assertGreaterEqual(left, 350)
        self.assertGreaterEqual(top, 100)
        self.assertLessEqual(right, 940)
        self.assertLessEqual(bottom, 560)

    def test_content_subject_prefers_dominant_page_in_overlapping_photo(self):
        subject = photo_normalize.detect_content_subject(make_overlapping_document_photo())

        self.assertIsNotNone(subject)
        self.assertEqual(subject["secondary_component_count"], 2)
        left, _, right, _ = subject["bbox"]
        self.assertGreaterEqual(left, 550)
        self.assertLessEqual(right, 1000)

    def test_content_subject_excludes_stamp_on_overlapping_page(self):
        subject = photo_normalize.detect_content_subject(
            make_overlapping_document_photo_with_secondary_stamp()
        )

        self.assertIsNotNone(subject)
        self.assertEqual(subject["artifact_component_count"], 0)
        self.assertGreaterEqual(subject["bbox"][0], 550)

    def test_content_subject_keeps_text_at_the_frame_bottom(self):
        subject = photo_normalize.detect_content_subject(
            make_document_photo_with_bottom_text()
        )

        self.assertIsNotNone(subject)
        self.assertEqual(subject["component_count"], 14)
        self.assertGreaterEqual(subject["bbox"][3], 780)

    def test_content_subject_drops_wide_ground_band(self):
        subject = photo_normalize.detect_content_subject(
            make_document_photo_with_ground_band()
        )

        self.assertIsNotNone(subject)
        self.assertGreaterEqual(subject["bbox"][3], 760)
        self.assertLessEqual(subject["bbox"][3], 790)

    def test_content_subject_keeps_blank_table_below_text(self):
        subject = photo_normalize.detect_content_subject(
            make_partial_document_with_blank_table()
        )

        self.assertIsNotNone(subject)
        self.assertGreaterEqual(subject["structural_table_component_count"], 1)
        self.assertGreaterEqual(subject["bbox"][3], 735)

    def test_line_cluster_corrects_tilted_blank_table(self):
        page = make_partial_document_with_blank_table()
        corners = photo_normalize._image_corners(page.size)
        camera = photo_normalize.cv2.getPerspectiveTransform(
            corners,
            np.float32([[12, 8], [1190, 18], [1185, 792], [8, 784]]),
        )
        captured = Image.fromarray(photo_normalize._warp_image(page, camera, page.size))

        frame = photo_normalize._structural_table_frame(captured)
        matrix, size, report = photo_normalize._table_projection(captured)

        self.assertIsNotNone(frame)
        self.assertEqual(report["source"], "line_cluster")
        self.assertEqual(report["status"], "applied")
        self.assertFalse(np.array_equal(matrix, np.eye(3)))
        self.assertGreater(size[0], 0)
        self.assertGreater(size[1], 0)

    def test_merged_horizontal_coverage_does_not_count_repeated_hough_segments(self):
        segments = [
            (400, 100, 200, 500, 200, 0),
            (400, 101, 201, 499, 201, 0),
            (300, 495, 200, 795, 200, 0),
        ]

        coverage = photo_normalize._merged_horizontal_coverage(segments, 1200)

        self.assertEqual(coverage, 695)
        self.assertLess(coverage, sum(segment[0] for segment in segments))

    def test_three_isolated_horizontal_rules_do_not_trigger_line_cluster(self):
        page = Image.new("RGB", (1200, 800), "steelblue")
        draw = ImageDraw.Draw(page)
        for top in (150, 390, 630):
            draw.line((180, top, 1020, top), fill="black", width=4)

        self.assertIsNone(photo_normalize._structural_table_frame(page))

    def test_mismatched_horizontal_rule_endpoints_do_not_trigger_line_cluster(self):
        page = Image.new("RGB", (1200, 800), "steelblue")
        draw = ImageDraw.Draw(page)
        draw.line((80, 150, 900, 150), fill="black", width=4)
        draw.line((420, 390, 1140, 390), fill="black", width=4)
        draw.line((180, 630, 920, 630), fill="black", width=4)
        draw.line((60, 150, 60, 630), fill="black", width=4)
        draw.line((1150, 150, 1150, 630), fill="black", width=4)

        self.assertIsNone(photo_normalize._structural_table_frame(page))

    def test_dense_text_rules_do_not_trigger_line_cluster(self):
        page = Image.new("RGB", (1200, 800), "steelblue")
        draw = ImageDraw.Draw(page)
        for top in range(150, 691, 45):
            draw.rectangle((300, top, 900, top + 18), fill="black")
        draw.line((300, 150, 300, 690), fill="black", width=4)
        draw.line((900, 150, 900, 690), fill="black", width=4)

        self.assertIsNone(photo_normalize._structural_table_frame(page))

    def test_line_cluster_prefers_supported_table_over_earlier_page_rule(self):
        page = Image.new("RGB", (1200, 800), "steelblue")
        draw = ImageDraw.Draw(page)
        draw.line((80, 80, 1120, 80), fill="black", width=4)
        draw.rectangle((300, 450, 900, 750), outline="black", width=4)
        for top in (550, 650):
            draw.line((300, top, 900, top), fill="black", width=4)

        frame = photo_normalize._structural_table_frame(page)

        self.assertIsNotNone(frame)
        self.assertGreater(frame[:, 1].min(), 350)

    def test_content_subject_keeps_dense_wide_text_at_the_frame_bottom(self):
        subject = photo_normalize.detect_content_subject(
            make_document_photo_with_wide_bottom_text()
        )

        self.assertIsNotNone(subject)
        self.assertGreaterEqual(subject["bbox"][3], 793)

    def test_content_subject_keeps_primary_stamp_near_overlapping_page(self):
        subject = photo_normalize.detect_content_subject(
            make_document_photo_with_stamp_near_overlapping_page()
        )

        self.assertIsNotNone(subject)
        self.assertGreaterEqual(subject["artifact_component_count"], 1)
        self.assertGreaterEqual(subject["bbox"][2], 970)

    def test_content_subject_requires_multiple_lines(self):
        image = Image.new("RGB", (640, 860), (145, 115, 85))
        draw = ImageDraw.Draw(image)
        draw.rectangle((174, 124, 336, 133), fill="black")

        self.assertIsNone(photo_normalize.detect_content_subject(image))

    def test_content_subject_keeps_adjacent_stamp_outside_text_bounds(self):
        subject = photo_normalize.detect_content_subject(
            make_partial_document_photo_with_stamp()
        )

        self.assertIsNotNone(subject)
        self.assertGreaterEqual(subject["artifact_component_count"], 1)
        _, _, right, bottom = subject["bbox"]
        self.assertGreaterEqual(right, 1040)
        self.assertGreaterEqual(bottom, 670)

    def test_content_subject_keeps_distant_colored_stamp(self):
        subject = photo_normalize.detect_content_subject(
            make_partial_document_photo_with_distant_stamp()
        )

        self.assertIsNotNone(subject)
        self.assertGreaterEqual(subject["artifact_component_count"], 1)
        self.assertLessEqual(subject["bbox"][0], 80)

    def test_content_subject_keeps_faded_stamp_that_creates_secondary_components(self):
        subject = photo_normalize.detect_content_subject(
            make_partial_document_photo_with_faded_stamp()
        )

        self.assertIsNotNone(subject)
        self.assertGreaterEqual(subject["artifact_component_count"], 1)
        self.assertLessEqual(subject["bbox"][0], 80)

    def test_photo_pipeline_uses_content_subject_after_paper_edge_failure(self):
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "partial.png"
            target = Path(tempdir) / "partial.pdf"
            report_target = Path(tempdir) / "partial.json"
            make_partial_document_photo().save(source)

            with patch.object(photo_normalize, "detect_document_quad", return_value=None):
                metadata = photo_normalize.normalize_photo_pdf(
                    source,
                    target,
                    rotation="0",
                    dpi=110,
                    report_file=report_target,
                )

            self.assertEqual(metadata["quad"]["source"], "content_subject")
            self.assertEqual(metadata["quad"]["content_subject"]["component_count"], 8)
            self.assertEqual(metadata["page_size"], "a4")
            content_width, content_height = metadata["content_size"]
            self.assertLessEqual(content_width, metadata["output_size"][0])
            self.assertLessEqual(content_height, metadata["output_size"][1])
            self.assertAlmostEqual(content_width / content_height, 555 / 382, delta=0.01)
            saved_metadata = json.loads(report_target.read_text(encoding="utf-8"))
            self.assertEqual(saved_metadata["quad"]["source"], "content_subject")
            with fitz.open(target) as document:
                self.assertEqual(len(document), 1)
                self.assertAlmostEqual(document[0].rect.width * 25.4 / 72, 297, places=3)
                self.assertAlmostEqual(document[0].rect.height * 25.4 / 72, 210, places=3)

    def test_photo_pipeline_preserves_stamp_found_by_content_subject(self):
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "partial-with-stamp.png"
            target = Path(tempdir) / "partial-with-stamp.pdf"
            make_partial_document_photo_with_stamp().save(source)

            with patch.object(photo_normalize, "detect_document_quad", return_value=None):
                metadata = photo_normalize.normalize_photo_pdf(
                    source, target, rotation="0", dpi=110
                )

            self.assertEqual(metadata["quad"]["source"], "content_subject")
            self.assertGreaterEqual(
                metadata["quad"]["content_subject"]["artifact_component_count"], 1
            )
            with fitz.open(target) as document:
                rendered = document[0].get_pixmap(dpi=110, colorspace=fitz.csRGB)
                pixels = np.frombuffer(rendered.samples, dtype=np.uint8).reshape(
                    rendered.height, rendered.width, 3
                )
            stamp_pixels = (
                pixels[:, :, 0].astype(np.int16) - pixels[:, :, 1].astype(np.int16)
            ) > 40
            self.assertGreater(int(stamp_pixels.sum()), 100)

    def test_photo_pipeline_preserves_distant_stamp_found_by_content_subject(self):
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "distant-stamp.png"
            target = Path(tempdir) / "distant-stamp.pdf"
            make_partial_document_photo_with_distant_stamp().save(source)

            with patch.object(photo_normalize, "detect_document_quad", return_value=None):
                metadata = photo_normalize.normalize_photo_pdf(
                    source, target, rotation="0", dpi=110
                )

            self.assertGreaterEqual(
                metadata["quad"]["content_subject"]["artifact_component_count"], 1
            )
            with fitz.open(target) as document:
                rendered = document[0].get_pixmap(dpi=110, colorspace=fitz.csRGB)
                pixels = np.frombuffer(rendered.samples, dtype=np.uint8).reshape(
                    rendered.height, rendered.width, 3
                )
            stamp_pixels = (
                pixels[:, :, 0].astype(np.int16) - pixels[:, :, 1].astype(np.int16)
            ) > 40
            self.assertGreater(int(stamp_pixels.sum()), 100)

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

    def test_detected_paper_fills_a4_and_keeps_corner_ink(self):
        photo = Image.new("RGB", (860, 1040), "steelblue")
        draw = ImageDraw.Draw(photo)
        draw.rectangle((110, 100, 749, 939), fill="white")
        for left, top in ((130, 120), (704, 120), (130, 894), (704, 894)):
            draw.rectangle((left, top, left + 25, top + 25), fill="black")

        dpi = 90
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "photo.png"
            photo.save(source)
            for rotation, options, dimensions_mm in (
                ("0", {}, (210, 297)),
                ("90", {"page_size": "auto"}, (297, 210)),
            ):
                with self.subTest(rotation=rotation):
                    target = Path(tempdir) / f"output-{rotation}.pdf"
                    report = photo_normalize.normalize_photo_pdf(
                        source, target, dpi=dpi, rotation=rotation, **options,
                    )
                    self.assertTrue(report["quad"]["quad_detected"])
                    self.assertEqual(report["content_size"], report["output_size"])
                    with fitz.open(target) as document:
                        self.assertAlmostEqual(document[0].rect.width * 25.4 / 72, dimensions_mm[0], places=3)
                        self.assertAlmostEqual(document[0].rect.height * 25.4 / 72, dimensions_mm[1], places=3)
                        raster = document[0].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
                        pixels = np.frombuffer(raster.samples, dtype=np.uint8).reshape(
                            raster.height, raster.width,
                        )
                    corner_height = round(raster.height * 0.05)
                    corner_width = round(raster.width * 0.05)
                    for rows in (slice(corner_height), slice(-corner_height, None)):
                        for columns in (slice(corner_width), slice(-corner_width, None)):
                            self.assertGreater(np.count_nonzero(pixels[rows, columns] < 90), 30)

    def test_default_pdf_canvas_is_exact_a4_without_detected_paper(self):
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

    def test_ambiguous_paper_edge_preserves_heading_outside_white_panel(self):
        self._assert_heading_outside_panel_is_preserved((223, 191, 145))

    def test_ink_outside_panel_preserved_on_darker_paper(self):
        self._assert_heading_outside_panel_is_preserved((145, 115, 85))

    def _assert_heading_outside_panel_is_preserved(self, paper_color):
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "photo.png"
            target = Path(tempdir) / "output.pdf"
            report_file = Path(tempdir) / "report.json"
            photo = Image.new("RGB", (640, 860), paper_color)
            draw = ImageDraw.Draw(photo)
            draw.rectangle((142, 204, 504, 699), fill="white")
            draw.rectangle((174, 124, 336, 133), fill="black")
            photo.save(source)

            photo_normalize.normalize_photo_pdf(
                source, target, rotation="0", page_size="original", dpi=100, report_file=report_file
            )

            metadata = json.loads(report_file.read_text(encoding="utf-8"))
            self.assertFalse(metadata["quad"]["quad_detected"])
            self.assertEqual(metadata["output_size"], [640, 860])
            with fitz.open(target) as document:
                rendered = document[0].get_pixmap(dpi=100, colorspace=fitz.csGRAY)
                pixels = np.frombuffer(rendered.samples, dtype=np.uint8).reshape(
                    rendered.height, rendered.width
                )
                self.assertLess(pixels[126:130, 200:300].mean(), 90)

    def test_pipeline_rejects_overwriting_source(self):
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "photo.jpg"
            make_document_photo().save(source)

            with self.assertRaisesRegex(ValueError, "不能覆盖"):
                photo_normalize.normalize_photo_pdf(source, source)

    def test_sidecar_paths_cannot_alias_source_or_each_other(self):
        with tempfile.TemporaryDirectory() as tempdir:
            folder = Path(tempdir)
            source = folder / "photo.png"
            target = folder / "output.pdf"
            debug_target = folder / "debug.png"
            make_document_photo().save(source)
            original = source.read_bytes()
            alias = folder / "alias.png"
            alias.symlink_to(source)
            cases = (
                {"report_file": source},
                {"debug_image": alias},
                {"report_file": target},
                {"debug_image": debug_target, "report_file": debug_target},
            )
            for options in cases:
                with self.subTest(options=options):
                    with self.assertRaisesRegex(ValueError, "不能覆盖"):
                        photo_normalize.normalize_photo_pdf(source, target, **options)
                    self.assertEqual(source.read_bytes(), original)
                    self.assertFalse(any(path.exists() for path in (debug_target, target)))

    def test_existing_outputs_remain_intact(self):
        with tempfile.TemporaryDirectory() as tempdir:
            folder = Path(tempdir)
            source = folder / "photo.png"
            target = folder / "output.pdf"
            debug_target = folder / "debug.png"
            report_target = folder / "report.json"
            make_document_photo().save(source)
            for existing in (target, debug_target, report_target):
                with self.subTest(path=existing):
                    existing.write_bytes(b"previous output")
                    with self.assertRaisesRegex(FileExistsError, "输出已存在"):
                        photo_normalize.normalize_photo_pdf(
                            source, target, debug_image=debug_target, report_file=report_target
                        )
                    self.assertEqual(existing.read_bytes(), b"previous output")
                    existing.unlink()

    def test_output_created_during_publish_is_preserved(self):
        with tempfile.TemporaryDirectory() as tempdir:
            folder = Path(tempdir)
            source = folder / "photo.png"
            target = folder / "output.pdf"
            report_target = folder / "report.json"
            Image.new("RGB", (120, 160), "white").save(source)
            publish = os.link

            def race(staged, destination):
                if destination == target:
                    target.write_bytes(b"other process output")
                publish(staged, destination)

            with patch.object(photo_normalize.os, "link", side_effect=race):
                with self.assertRaises(FileExistsError):
                    photo_normalize.normalize_photo_pdf(
                        source, target, rotation="0", dpi=35, report_file=report_target
                    )
            self.assertEqual(target.read_bytes(), b"other process output")
            self.assertFalse(report_target.exists())
            self.assertEqual(set(folder.iterdir()), {source, target})

    def test_multipage_tiff_requires_splitting(self):
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "pages.tiff"
            target = Path(tempdir) / "output.pdf"
            first = Image.new("RGB", (160, 220), "white")
            second = Image.new("RGB", first.size, "black")
            first.save(source, save_all=True, append_images=[second])

            with self.assertRaisesRegex(ValueError, "只接受单帧"):
                photo_normalize.normalize_photo_pdf(source, target)
            self.assertFalse(target.exists())
            with Image.open(source) as image:
                self.assertEqual(image.n_frames, 2)


if __name__ == "__main__":
    unittest.main()
