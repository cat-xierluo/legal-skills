#!/usr/bin/env python3
"""Regression tests for skew angle decision logic."""

import unittest

from PIL import Image, ImageDraw

from pdf_preprocess_skew import SkewDetector


def make_synthetic_text_page(rotation_angle: float) -> Image.Image:
    image = Image.new("RGB", (900, 1200), "white")
    draw = ImageDraw.Draw(image)
    for y in range(160, 1000, 70):
        draw.rectangle((120, y, 780, y + 10), fill="black")
    return image.rotate(
        rotation_angle,
        resample=Image.Resampling.BICUBIC,
        expand=False,
        fillcolor="white",
    )


class SkewDetectorDecisionTest(unittest.TestCase):
    def setUp(self):
        self.detector = SkewDetector(skew_threshold=0.3)

    def test_projection_wins_when_hough_is_low_confidence_outlier(self):
        angle, method = self.detector.decide_angle(
            hough_angle=4.54,
            hough_confidence=0.15,
            projection_angle=0.40,
        )

        self.assertAlmostEqual(angle, 0.40, places=2)
        self.assertEqual(method, "projection")

    def test_projection_wins_when_hough_and_projection_disagree(self):
        angle, method = self.detector.decide_angle(
            hough_angle=-1.83,
            hough_confidence=1.0,
            projection_angle=0.60,
        )

        self.assertAlmostEqual(angle, 0.60, places=2)
        self.assertEqual(method, "projection_conflict")

    def test_close_hough_and_projection_are_averaged(self):
        angle, method = self.detector.decide_angle(
            hough_angle=0.62,
            hough_confidence=1.0,
            projection_angle=0.60,
        )

        self.assertAlmostEqual(angle, 0.61, places=2)
        self.assertEqual(method, "hough_projection_average")

    def test_unsupported_hough_without_projection_is_skipped(self):
        angle, method = self.detector.decide_angle(
            hough_angle=1.2,
            hough_confidence=1.0,
            projection_angle=0.2,
        )

        self.assertEqual(angle, 0.0)
        self.assertEqual(method, "none")

    def test_projection_profile_supports_fast_two_stage_search(self):
        detector = SkewDetector(
            projection_coarse_step=0.5,
            projection_fine_step=0.1,
            projection_fine_window=0.5,
        )

        angle = detector.projection_profile_angle(make_synthetic_text_page(1.3))

        self.assertAlmostEqual(angle, -1.3, delta=0.2)

    def test_default_projection_search_keeps_legacy_angle_grid(self):
        angle = self.detector.projection_profile_angle(make_synthetic_text_page(1.3))

        self.assertAlmostEqual(angle / 0.2, round(angle / 0.2), places=6)


if __name__ == "__main__":
    unittest.main()
