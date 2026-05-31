#!/usr/bin/env python3
"""Skew detection helpers for PDF preprocessing."""

from dataclasses import dataclass
from typing import Tuple

try:
    import cv2
    import numpy as np
    from PIL import Image
except ImportError as e:
    from pdf_runtime import exit_for_missing_dependencies

    exit_for_missing_dependencies(
        "PDF 倾斜检测",
        missing_python=["opencv-python", "pillow", "numpy"],
        install_commands=["pip install opencv-python pillow numpy"],
        extra_notes=[f"原始错误: {e}"],
    )


@dataclass
class SkewDetectionResult:
    """Result from fine skew detection."""

    angle: float
    hough_angle: float
    hough_confidence: float
    projection_angle: float
    method: str


class SkewDetector:
    """Detect and decide fine page skew angle."""

    def __init__(
        self,
        skew_threshold: float = 0.3,
        max_reasonable_skew: float = 15.0,
        hough_confidence_threshold: float = 0.35,
        projection_coarse_step: float = 0.5,
        projection_fine_step: float = 0.2,
        projection_fine_window: float = 0.5,
    ):
        self.skew_threshold = skew_threshold
        self.max_reasonable_skew = max_reasonable_skew
        self.hough_confidence_threshold = hough_confidence_threshold
        self.projection_coarse_step = projection_coarse_step
        self.projection_fine_step = projection_fine_step
        self.projection_fine_window = projection_fine_window

    def detect(self, image: Image.Image) -> SkewDetectionResult:
        """Detect fine skew using Hough lines plus projection profile."""
        hough_angle, hough_confidence = self.hough_skew_angle(image)
        projection_angle = self.projection_profile_angle(image)
        angle, method = self.decide_angle(
            hough_angle=hough_angle,
            hough_confidence=hough_confidence,
            projection_angle=projection_angle,
        )
        return SkewDetectionResult(
            angle=float(angle),
            hough_angle=float(hough_angle),
            hough_confidence=float(hough_confidence),
            projection_angle=float(projection_angle),
            method=method,
        )

    def decide_angle(
        self,
        hough_angle: float,
        hough_confidence: float,
        projection_angle: float,
    ) -> tuple[float, str]:
        """Choose the final skew angle from Hough and projection candidates."""
        hough_valid = self._valid(hough_angle) and hough_confidence >= self.hough_confidence_threshold
        projection_valid = self._valid(projection_angle)

        if not hough_valid:
            if projection_valid:
                return float(projection_angle), "projection"
            return 0.0, "none"

        if not projection_valid:
            # Long-line-only angles are often caused by borders, footers, or image rectangles.
            return 0.0, "none"

        same_direction = hough_angle * projection_angle > 0
        if not same_direction:
            return float(projection_angle), "projection_conflict"

        delta = abs(hough_angle - projection_angle)
        if delta <= 0.75:
            return float((hough_angle + projection_angle) / 2.0), "hough_projection_average"

        return float(projection_angle), "projection_diverged"

    def _valid(self, angle: float) -> bool:
        return self.skew_threshold <= abs(angle) <= self.max_reasonable_skew

    def min_area_rect_angle(self, image: Image.Image) -> float:
        """Detect angle using a minimum enclosing rectangle."""
        img_array = np.array(image)

        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array

        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        coords = np.column_stack(np.where(binary > 0))

        if len(coords) == 0:
            return 0.0

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        return float(angle)

    def projection_profile_angle(self, image: Image.Image) -> float:
        """Detect skew by maximizing horizontal projection variance."""
        img_array = np.array(image)

        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array

        max_dim = 1000
        if max(gray.shape) > max_dim:
            scale = max_dim / max(gray.shape)
            new_shape = (int(gray.shape[1] * scale), int(gray.shape[0] * scale))
            gray = cv2.resize(gray, new_shape)

        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        h, w = binary.shape
        crop_top = int(h * 0.1)
        crop_bottom = int(h * 0.9)
        cropped = binary[crop_top:crop_bottom, :]

        def projection_variance(angle: float) -> float:
            center = (w // 2, h // 2)
            matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(cropped, matrix, (w, h), flags=cv2.INTER_NEAREST)
            horizontal_projection = np.sum(rotated, axis=1)
            return float(np.var(horizontal_projection))

        best_angle = self._best_projection_angle(
            np.arange(-10, 10 + self.projection_coarse_step, self.projection_coarse_step),
            projection_variance,
        )
        fine_start = self._align_projection_angle(
            best_angle - self.projection_fine_window,
            mode="ceil",
        )
        fine_end = self._align_projection_angle(
            best_angle + self.projection_fine_window,
            mode="floor",
        )
        best_angle = self._best_projection_angle(
            np.arange(fine_start, fine_end + self.projection_fine_step, self.projection_fine_step),
            projection_variance,
        )

        return float(best_angle)

    def _best_projection_angle(self, angles, score_func) -> float:
        max_variance = float("-inf")
        best_angle = 0.0
        for angle in angles:
            variance = score_func(float(angle))
            if variance > max_variance:
                max_variance = variance
                best_angle = float(angle)
        return best_angle

    def _align_projection_angle(self, angle: float, mode: str) -> float:
        ratio = angle / self.projection_fine_step
        if mode == "ceil":
            return float(np.ceil(ratio) * self.projection_fine_step)
        if mode == "floor":
            return float(np.floor(ratio) * self.projection_fine_step)
        return float(round(ratio) * self.projection_fine_step)

    def hough_skew_angle(self, image: Image.Image) -> Tuple[float, float]:
        """Detect skew angle with Hough line segments and confidence."""
        img_array = np.array(image)

        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array

        max_dim = 1500
        if max(gray.shape) > max_dim:
            scale = max_dim / max(gray.shape)
            new_shape = (int(gray.shape[1] * scale), int(gray.shape[0] * scale))
            gray = cv2.resize(gray, new_shape)

        edges = cv2.Canny(gray, 50, 150, apertureSize=3)

        page_w = gray.shape[1]
        min_line = max(50, int(page_w * 0.1))
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180,
            threshold=80,
            minLineLength=min_line,
            maxLineGap=10,
        )

        if lines is None or len(lines) < 3:
            return 0.0, 0.0

        weighted_angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            dx, dy = x2 - x1, y2 - y1
            length = np.sqrt(dx * dx + dy * dy)
            angle = np.degrees(np.arctan2(dy, dx))

            if abs(angle) < 15:
                weighted_angles.append((angle, length))
            elif abs(angle) > 75:
                deviation = 90.0 - abs(angle)
                lean_sign = -1.0 if dx * dy > 0 else 1.0
                weighted_angles.append((lean_sign * deviation, length))

        if not weighted_angles:
            return 0.0, 0.0

        capped = [(angle, min(length, page_w * 0.6)) for angle, length in weighted_angles]
        total_weight = sum(length for _, length in capped)
        if total_weight <= 0:
            return 0.0, 0.0

        sorted_by_angle = sorted(capped, key=lambda item: item[0])
        acc = 0.0
        median_angle = sorted_by_angle[-1][0]
        for angle, weight in sorted_by_angle:
            acc += weight
            if acc >= total_weight / 2.0:
                median_angle = angle
                break

        core = [(angle, length) for angle, length in capped if abs(angle - median_angle) <= 0.75]
        core_weight = sum(length for _, length in core)
        if core_weight > 0:
            weighted_angle = sum(angle * length for angle, length in core) / core_weight
        else:
            weighted_angle = median_angle

        sorted_by_len = sorted(core or capped, key=lambda item: item[1], reverse=True)
        top_lines = sorted_by_len[:max(5, len(sorted_by_len) // 3)]
        n_long = len(top_lines)
        avg_long = sum(length for _, length in top_lines) / n_long
        length_ratio = avg_long / page_w
        concentration = core_weight / total_weight if total_weight else 0.0
        base_confidence = min(1.0, (n_long / 6.0) * (length_ratio / 0.2))
        confidence = min(1.0, base_confidence * concentration)

        return float(weighted_angle), min(1.0, confidence)
