#!/usr/bin/env python3
"""Normalize photographed document pages into regular PDFs."""

import argparse
import json
import os
from collections.abc import Callable
from contextlib import ExitStack
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    import cv2
    import numpy as np
    from PIL import Image, ImageOps
except ImportError as exc:
    from pdf_runtime import exit_for_missing_dependencies

    exit_for_missing_dependencies(
        "拍照件规整 PDF",
        missing_python=["opencv-python", "pillow", "numpy"],
        install_commands=["pip install opencv-python pillow numpy"],
        extra_notes=[f"原始错误: {exc}"],
    )

from pdf_preprocess_skew import SkewDetector


PAGE_SIZES_MM = {
    "a4": (210, 297),
    "letter": (215.9, 279.4),
}
DEFAULT_PAGE_SIZE = "a4"
DEFAULT_CONTRAST_STRENGTH = 0.7
DEFAULT_BINARIZE_HIGH = 235.0
DEFAULT_BINARIZE_LOW = 195.0
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
TEXT_TILT_TOLERANCE_DEG = 0.3
BAND_ANGLE_TOLERANCE_DEG = 1.2
MAX_RESIDUAL_TILT_DEG = 5.0
COLUMN_ANGLE_TOLERANCE_DEG = 0.6


def load_photo(path: str | Path) -> Image.Image:
    """Load an image and bake its EXIF orientation into pixels."""
    source = Path(path)
    if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支持的拍照件格式: {source.suffix or '(无后缀)'}")
    with Image.open(source) as image:
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("拍照件入口只接受单帧图像，请先拆分多页或多帧输入")
        return ImageOps.exif_transpose(image).convert("RGB")


def _order_quad(points: np.ndarray) -> np.ndarray:
    """Order perspective points as top-left, top-right, bottom-right, bottom-left."""
    center = points.mean(axis=0)
    offsets = points - center
    top_left = points[np.argmin(offsets[:, 0] + offsets[:, 1])]
    bottom_right = points[np.argmax(offsets[:, 0] + offsets[:, 1])]
    top_right = points[np.argmax(offsets[:, 0] - offsets[:, 1])]
    bottom_left = points[np.argmin(offsets[:, 0] - offsets[:, 1])]
    return np.array([top_left, top_right, bottom_right, bottom_left], dtype=np.float32)


def _quad_is_convex(ordered_points: np.ndarray) -> bool:
    return cv2.isContourConvex(ordered_points.astype(np.float32))


def _order_quad_clockwise(points: np.ndarray) -> np.ndarray:
    """Order corners clockwise from the top-left-most one, robust to ties."""
    center = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    ordered = points[np.argsort(angles)]
    start = int(np.argmin(ordered[:, 0] + ordered[:, 1]))
    return np.roll(ordered, -start, axis=0).astype(np.float32)


def parse_quad(value: str) -> list[list[float]]:
    """Parse ``x1,y1,x2,y2,x3,y3,x4,y4`` corner text, accepting Chinese commas."""
    try:
        numbers = [float(item) for item in value.replace("，", ",").split(",")]
    except ValueError as exc:
        raise ValueError(f"无法解析手动四角: {value}") from exc
    if len(numbers) != 8:
        raise ValueError("手动四角必须是 8 个数字：x1,y1,x2,y2,x3,y3,x4,y4")
    return [[numbers[index], numbers[index + 1]] for index in range(0, 8, 2)]


def _manual_quad(
    points, image_size: tuple[int, int],
) -> np.ndarray:
    """Validate normalized manual corners and scale them to image pixels."""
    array = np.asarray(points, dtype=np.float32)
    if array.shape != (4, 2):
        raise ValueError("手动四角必须是 4 个 (x, y) 点")
    if not np.all(np.isfinite(array)):
        raise ValueError("手动四角坐标必须是有限数值")
    if np.any(array < 0) or np.any(array > 1):
        raise ValueError("手动四角使用 0-1 归一化坐标")
    ordered = _order_quad_clockwise(array)
    if not _quad_is_convex(ordered) or cv2.contourArea(ordered) <= 0:
        raise ValueError("手动四角必须是凸四边形")
    return ordered * np.array(
        (image_size[0] - 1, image_size[1] - 1), dtype=np.float32,
    )


def _has_document_edges(gray: np.ndarray, quad: np.ndarray) -> bool:
    """Require visible transitions from the paper to a darker exterior."""
    height, width = gray.shape
    fractions = np.linspace(0.14, 0.86, 25)[:, None]
    distance = max(3, 0.018 * min(height, width))
    bounds = np.array([width, height])
    supported_edges = 0
    for start, end in zip(quad, np.roll(quad, -1, axis=0)):
        direction = end - start
        inward = np.array([-direction[1], direction[0]]) / np.linalg.norm(direction)
        edge_points = start + fractions * direction
        inside = np.rint(edge_points + distance * inward).astype(int)
        outside = np.rint(edge_points - distance * inward).astype(int)
        valid = np.all((inside >= 0) & (inside < bounds), axis=1)
        valid &= np.all((outside >= 0) & (outside < bounds), axis=1)
        if np.count_nonzero(valid) < 12:
            continue
        paper = gray[inside[valid, 1], inside[valid, 0]].astype(np.int16)
        surround = gray[outside[valid, 1], outside[valid, 0]].astype(np.int16)
        if np.mean((paper - surround >= 16) & (surround <= 175)) >= 0.52:
            supported_edges += 1
    return supported_edges >= 3


def _has_exterior_ink(gray: np.ndarray, quad: np.ndarray) -> bool:
    """Treat concentrated dark marks beyond the candidate as possible content."""
    short_edge = min(gray.shape)
    paper_mask = np.zeros_like(gray)
    cv2.fillConvexPoly(paper_mask, np.rint(quad).astype(np.int32), 255)
    edge_padding = 2 * round(0.012 * short_edge) + 1
    paper_mask = cv2.dilate(
        paper_mask, np.ones((edge_padding, edge_padding), dtype=np.uint8)
    )

    background_span = max(15, 2 * round(0.024 * short_edge) + 1)
    local_contrast = cv2.morphologyEx(
        gray, cv2.MORPH_BLACKHAT,
        np.ones((background_span, background_span), dtype=np.uint8),
    )
    marks = ((paper_mask == 0) & (gray <= 100) & (local_contrast >= 35)).astype(np.float32)
    window = max(7, round(0.07 * short_edge))
    ink_counts = cv2.boxFilter(
        marks, -1, (window, window), normalize=False, borderType=cv2.BORDER_CONSTANT
    )
    return bool(ink_counts.max() >= max(12, 0.045 * window ** 2))


def detect_document_quad(image: Image.Image) -> np.ndarray | None:
    """Detect the dominant bright, low-saturation document quadrilateral."""
    image_array = np.asarray(image)
    max_detection_size = 1200
    scale = min(1.0, max_detection_size / max(image.size))
    detection_size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    resized = cv2.resize(image_array, detection_size, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(resized, cv2.COLOR_RGB2HSV)
    _, saturation, value = cv2.split(hsv)
    value_floor = max(70.0, float(np.percentile(value, 10)))

    candidates = []
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    for saturation_threshold in (20, 30, 40):
        mask = ((saturation <= saturation_threshold) & (value >= value_floor)).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area_ratio = cv2.contourArea(contour) / mask.size
            if not 0.12 <= area_ratio <= 0.96:
                continue
            perimeter = cv2.arcLength(contour, True)
            for epsilon_ratio in (0.01, 0.02, 0.03):
                approx = cv2.approxPolyDP(contour, epsilon_ratio * perimeter, True)
                if len(approx) != 4:
                    continue
                points = _order_quad(approx.reshape(-1, 2).astype(np.float32))
                if not _quad_is_convex(points):
                    continue
                candidates.append((area_ratio, epsilon_ratio, points))
                break

    if not candidates:
        return None
    _, _, best_points = max(candidates, key=lambda item: item[0])
    gray = cv2.cvtColor(resized, cv2.COLOR_RGB2GRAY)
    if not _has_document_edges(gray, best_points) or _has_exterior_ink(gray, best_points):
        return None
    return best_points / scale


def _text_line_components(image: Image.Image) -> list[dict[str, int]]:
    image_array = np.asarray(image)
    gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
    ink = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 9
    )
    line_mask = cv2.morphologyEx(
        ink,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (19, 3)),
    )
    line_mask = cv2.morphologyEx(line_mask, cv2.MORPH_OPEN, np.ones((2, 2), dtype=np.uint8))
    component_count, _, stats, _ = cv2.connectedComponentsWithStats(line_mask)
    width, height = image.size
    components = []
    for index in range(1, component_count):
        left, top, component_width, component_height, area = map(int, stats[index])
        if (
            component_width >= width * 0.035
            and 2 <= component_height <= height * 0.08
            and area >= 30
        ):
            if _is_ground_block(
                left,
                top,
                component_width,
                component_height,
                area,
                width,
                height,
            ):
                continue
            components.append({
                "index": index,
                "left": left,
                "top": top,
                "width": component_width,
                "height": component_height,
                "area": area,
            })
    return components


def _is_ground_block(
    left: int,
    top: int,
    component_width: int,
    component_height: int,
    area: int,
    width: int,
    height: int,
) -> bool:
    """Spot the wide dark desk slab that reaches the bottom of the frame."""
    if top + component_height < height * 0.97:
        return False
    if component_width < width * 0.6:
        return False
    if component_height > height * 0.08:
        return False
    density = area / max(component_width * component_height, 1)
    return 0.25 <= density <= 0.55


def _paper_bottom_edge(
    gray: np.ndarray,
    column_left: int,
    column_right: int,
    start_row: int,
    paper_level: float,
) -> int | None:
    """Find where the bright paper surface ends and the darker desk begins."""
    height = gray.shape[0]
    column = gray[:, max(0, column_left):max(column_left + 1, column_right)]
    if column.size == 0:
        return None
    threshold = paper_level * 0.45
    previous = paper_level
    for row in range(min(start_row, height - 1), height):
        current = float(np.median(column[row]))
        if current < threshold and previous >= threshold:
            if all(
                float(np.median(column[index])) < threshold
                for index in range(row, height)
            ):
                return row
        previous = current
    return None


def _cluster_text_lines(
    components: list[dict[str, int]], seed: dict[str, int], image_height: int
) -> list[dict[str, int]]:
    selected = {seed["index"]}
    changed = True
    while changed:
        changed = False
        selected_components = [item for item in components if item["index"] in selected]
        bounds = (
            min(item["left"] for item in selected_components),
            min(item["top"] for item in selected_components),
            max(item["left"] + item["width"] for item in selected_components),
            max(item["top"] + item["height"] for item in selected_components),
        )
        for item in components:
            if item["index"] in selected:
                continue
            overlap = (
                min(bounds[2], item["left"] + item["width"])
                - max(bounds[0], item["left"])
            )
            center_inside = bounds[0] <= item["left"] + item["width"] / 2 <= bounds[2]
            vertical_gap = max(
                0,
                bounds[1] - item["top"] - item["height"],
                item["top"] - bounds[3],
            )
            if (
                overlap >= seed["width"] * 0.18 or center_inside
            ) and vertical_gap <= image_height * 0.22:
                selected.add(item["index"])
            changed = changed or item["index"] in selected
    return [item for item in components if item["index"] in selected]


def _overlapping_page_components(
    primary: list[dict[str, int]],
    secondary: list[dict[str, int]],
    width: int,
    height: int,
) -> list[dict[str, int]]:
    """Return a reliable text cluster from a horizontally adjacent page."""
    if not secondary:
        return []
    primary_left = min(item["left"] for item in primary)
    primary_right = max(item["left"] + item["width"] for item in primary)
    line_like = [
        item for item in secondary
        if item["height"] <= height * 0.05
        and item["width"] / max(item["height"], 1) >= 1.5
    ]
    left_page = [
        item for item in line_like
        if item["left"] + item["width"] <= primary_left + width * 0.04
    ]
    right_page = [
        item for item in line_like
        if item["left"] >= primary_right - width * 0.04
    ]
    if len(left_page) >= 2:
        return left_page
    if len(right_page) >= 2:
        return right_page
    return []


def _distance_to_nearest_box(
    left: int,
    top: int,
    right: int,
    bottom: int,
    boxes: list[tuple[int, int, int, int]],
) -> float:
    return min(
        (
            max(0, box[0] - right, left - box[2]) ** 2
            + max(0, box[1] - bottom, top - box[3]) ** 2
        ) ** 0.5
        for box in boxes
    )


def _nearby_artifact_components(
    image: Image.Image,
    primary: list[dict[str, int]],
    secondary: list[dict[str, int]],
) -> list[dict[str, int]]:
    """Keep colored seals that belong to the page holding the primary text block."""
    image_array = np.asarray(image)
    hue, saturation, value = cv2.split(cv2.cvtColor(image_array, cv2.COLOR_RGB2HSV))
    red_seal = (
        ((hue <= 10) | (hue >= 170)) & (saturation >= 90) & (value >= 70)
    )
    blue_seal = (
        (hue >= 95) & (hue <= 130) & (saturation >= 90) & (value >= 70)
    )
    red_mask = cv2.morphologyEx(
        red_seal.astype(np.uint8) * 255,
        cv2.MORPH_OPEN,
        np.ones((2, 2), dtype=np.uint8),
    )
    blue_mask = cv2.morphologyEx(
        blue_seal.astype(np.uint8) * 255,
        cv2.MORPH_OPEN,
        np.ones((2, 2), dtype=np.uint8),
    )

    width, height = image.size
    text_left = min(item["left"] for item in primary)
    text_top = min(item["top"] for item in primary)
    text_right = max(item["left"] + item["width"] for item in primary)
    text_bottom = max(item["top"] + item["height"] for item in primary)
    text_boxes = [
        (
            item["left"],
            item["top"],
            item["left"] + item["width"],
            item["top"] + item["height"],
        )
        for item in primary
    ]
    nearby_x = max(8, round(width * 0.12))
    nearby_y = max(8, round(height * 0.16))
    colored_nearby_x = max(nearby_x, round(width * 0.24))
    minimum_area = max(70, round(width * height * 0.00012))
    maximum_area = round(width * height * 0.03)
    overlapping_page = _overlapping_page_components(
        primary, secondary, width, height
    )
    artifacts = []
    for mask, artifact_nearby_x in (
        (red_mask, colored_nearby_x),
        (blue_mask, colored_nearby_x),
    ):
        component_count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        for index in range(1, component_count):
            left, top, component_width, component_height, area = map(int, stats[index])
            right, bottom = left + component_width, top + component_height
            if (
                area < minimum_area
                or area > maximum_area
                or component_width > width * 0.68
                or component_height > height * 0.60
                or component_width > width * 0.38
                or component_height > height * 0.38
                or left <= 2
                or top <= 2
                or right >= width - 3
                or bottom >= height - 3
            ):
                continue
            component_area = component_width * component_height
            duplicate = any(
                (
                    max(0, min(right, box[2]) - max(left, box[0]))
                    * max(0, min(bottom, box[3]) - max(top, box[1]))
                ) >= component_area * 0.72
                for box in text_boxes
            )
            if duplicate:
                continue
            gap_x = max(0, text_left - right, left - text_right)
            gap_y = max(0, text_top - bottom, top - text_bottom)
            if gap_x <= artifact_nearby_x and gap_y <= nearby_y:
                if overlapping_page:
                    primary_distance = _distance_to_nearest_box(
                        left, top, right, bottom, text_boxes
                    )
                    secondary_boxes = [
                        (
                            item["left"],
                            item["top"],
                            item["left"] + item["width"],
                            item["top"] + item["height"],
                        )
                        for item in overlapping_page
                    ]
                    secondary_distance = _distance_to_nearest_box(
                        left, top, right, bottom, secondary_boxes
                    )
                    if primary_distance >= secondary_distance * 0.5:
                        continue
                artifacts.append({
                    "left": left,
                    "top": top,
                    "width": component_width,
                    "height": component_height,
                    "area": area,
                })
    return artifacts


def _structural_table_components(
    image: Image.Image, primary: list[dict[str, int]]
) -> list[dict[str, int]]:
    """Find sparse line networks left by blank tables below or beside text."""
    image_array = np.asarray(image)
    gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
    ink = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 9
    )
    line_mask = cv2.morphologyEx(
        ink,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (19, 3)),
    )
    line_mask = cv2.morphologyEx(line_mask, cv2.MORPH_OPEN, np.ones((2, 2), dtype=np.uint8))
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(line_mask)

    width, height = image.size
    text_left = min(item["left"] for item in primary)
    text_right = max(item["left"] + item["width"] for item in primary)
    text_bottom = max(item["top"] + item["height"] for item in primary)
    text_width = max(1, text_right - text_left)
    components = []
    for index in range(1, component_count):
        left, top, component_width, component_height, area = map(int, stats[index])
        right, bottom = left + component_width, top + component_height
        horizontal_overlap = min(text_right, right) - max(text_left, left)
        density = area / max(component_width * component_height, 1)
        if (
            component_width < text_width * 0.45
            or component_height < height * 0.08
            or component_width / max(component_height, 1) < 1.2
            or horizontal_overlap < component_width * 0.35
            or density > 0.35
        ):
            continue
        extends_subject = (
            bottom > text_bottom + height * 0.02
            or right > text_right + width * 0.02
            or left < text_left - width * 0.02
        )
        touches_frame_side = left <= 2 or top <= 2 or right >= width - 3
        bbox_area_ratio = component_width * component_height / (width * height)
        if not extends_subject or touches_frame_side or bbox_area_ratio > 0.3:
            continue
        component_mask = (labels == index).astype(np.uint8)
        vertical_kernel = max(25, round(component_height * 0.3))
        vertical_support = cv2.morphologyEx(
            component_mask,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (1, vertical_kernel)),
        )
        if np.count_nonzero(vertical_support) < 50:
            continue
        components.append({
            "left": left,
            "top": top,
            "width": component_width,
            "height": component_height,
            "area": area,
        })
    return components


def detect_content_subject(image: Image.Image) -> dict | None:
    """Find a reliable visible text block when the full paper edge is absent."""
    max_detection_size = 1200
    scale = min(1.0, max_detection_size / max(image.size))
    detection_size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    resized = image.resize(detection_size, Image.Resampling.BILINEAR)
    components = _text_line_components(resized)
    if len(components) < 5:
        return None

    clusters = [
        _cluster_text_lines(components, seed, resized.height)
        for seed in components
    ]
    primary = max(
        clusters,
        key=lambda cluster: (sum(item["area"] for item in cluster), len(cluster)),
    )
    total_area = sum(item["area"] for item in components)
    primary_area = sum(item["area"] for item in primary)
    coverage = primary_area / total_area
    if coverage < 0.55:
        return None
    primary_ids = {item["index"] for item in primary}
    secondary = [
        item for item in components if item["index"] not in primary_ids
    ]
    artifacts = _nearby_artifact_components(resized, primary, secondary)
    expansion_artifacts = [
        item for item in artifacts
        if 0.25 <= item["width"] / max(item["height"], 1) <= 4.0
        and item["width"] >= 10
        and item["height"] >= 10
    ]
    structural_tables = _structural_table_components(resized, primary)

    width, height = resized.size
    margin_x = round(width * 0.035)
    top_margin = round(height * 0.045)
    bottom_margin = round(height * 0.015)
    primary_bounds = [
        {
            "left": item["left"],
            "top": item["top"],
            "right": item["left"] + item["width"],
            "bottom": item["top"] + item["height"],
        }
        for item in primary
    ]
    bounds_components = [
        {
            "left": item["left"],
            "top": item["top"],
            "right": item["left"] + item["width"],
            "bottom": item["top"] + item["height"],
        }
        for item in [*primary, *expansion_artifacts]
    ]
    structural_bounds = [
        {
            "left": item["left"],
            "top": item["top"],
            "right": item["left"] + item["width"],
            "bottom": item["top"] + item["height"],
        }
        for item in structural_tables
    ]
    bounds_components.extend(structural_bounds)
    left = max(0, min(item["left"] for item in bounds_components) - margin_x)
    top = max(0, min(item["top"] for item in bounds_components) - top_margin)
    right = min(
        width,
        max(item["right"] for item in bounds_components) + margin_x,
    )
    text_bottom = max(item["bottom"] for item in primary_bounds)
    content_bottom = max(item["bottom"] for item in bounds_components)
    gray = cv2.cvtColor(np.asarray(resized), cv2.COLOR_RGB2GRAY)
    paper_level = float(
        np.percentile(
            gray[
                max(0, min(item["top"] for item in bounds_components)):
                min(height, text_bottom + 1)
            ],
            75,
        )
    )
    paper_edge = None
    if content_bottom >= height * 0.9:
        paper_edge = _paper_bottom_edge(
            gray,
            left,
            right,
            max(0, min(item["top"] for item in primary_bounds)),
            paper_level,
        )
    bottom = content_bottom + bottom_margin
    if paper_edge is not None and paper_edge < height:
        bottom = min(bottom, paper_edge + bottom_margin)
    bottom = min(height, bottom)
    subject_width = right - left
    subject_height = bottom - top
    area_ratio = subject_width * subject_height / (width * height)
    aspect_ratio = subject_width / subject_height
    if (
        subject_width < width * 0.22
        or subject_height < height * 0.18
        or not 0.35 <= aspect_ratio <= 2.8
        or not 0.15 <= area_ratio <= 0.92
    ):
        return None

    quad = np.float32([
        [left, top],
        [right - 1, top],
        [right - 1, bottom - 1],
        [left, bottom - 1],
    ]) / scale
    return {
        "quad": quad,
        "component_count": len(primary),
        "total_component_count": len(components),
        "artifact_component_count": len(artifacts),
        "ink_coverage": round(float(coverage), 4),
        "area_coverage": round(float(area_ratio), 4),
        "bbox": [left, top, right, bottom],
        "secondary_component_count": len(components) - len(primary),
        "structural_table_component_count": len(structural_tables),
    }


def _quad_dimensions(ordered_points: np.ndarray) -> tuple[int, int]:
    top_width = np.linalg.norm(ordered_points[1] - ordered_points[0])
    bottom_width = np.linalg.norm(ordered_points[2] - ordered_points[3])
    left_height = np.linalg.norm(ordered_points[3] - ordered_points[0])
    right_height = np.linalg.norm(ordered_points[2] - ordered_points[1])
    return round(float(max(top_width, bottom_width))), round(float(max(left_height, right_height)))


def _paper_projection(
    image_size: tuple[int, int],
    quad: np.ndarray | None,
) -> tuple[np.ndarray, tuple[int, int], dict]:
    """Map the detected paper corners to a rectangular page."""
    if quad is not None:
        size = _quad_dimensions(quad)
        if min(size) >= 2:
            return (
                cv2.getPerspectiveTransform(quad, _image_corners(size)),
                size,
                {"quad_detected": True, "quad": quad.round(2).tolist(), "detected_size": size},
            )
    return (
        np.eye(3),
        image_size,
        {"quad_detected": False, "quad": None, "detected_size": image_size},
    )


def _image_corners(size: tuple[int, int]) -> np.ndarray:
    width, height = size
    return np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])


def _resize_matrix(source: tuple[int, int], target: tuple[int, int]) -> np.ndarray:
    scale_x, scale_y = np.divide(target, source)
    return np.array([
        [scale_x, 0, (scale_x - 1) / 2],
        [0, scale_y, (scale_y - 1) / 2],
        [0, 0, 1],
    ])


def _warp_image(image: Image.Image, transform: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    return cv2.warpPerspective(
        np.asarray(image),
        transform,
        size,
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def _expand_projected_canvas(
    matrix: np.ndarray, projected_corners: np.ndarray,
) -> tuple[np.ndarray, tuple[int, int]]:
    offset = np.floor(projected_corners.min(axis=0))
    width, height = (np.ceil(projected_corners.max(axis=0)) - offset + 1).astype(int)
    matrix[:2] -= offset[:, None] * matrix[2]
    return matrix, (int(width), int(height))


def _table_frame(preview: Image.Image) -> np.ndarray | None:
    """Find a large, connected frame whose four sides have continuous support."""
    width, height = preview.size
    if min(preview.size) < 120:
        return None

    gray = cv2.cvtColor(np.asarray(preview), cv2.COLOR_RGB2GRAY)
    ink = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 8
    )
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((3, 3), dtype=np.uint8))
    margin_x, margin_y = round(width * 0.05), round(height * 0.05)
    inset = ink[margin_y:height - margin_y, margin_x:width - margin_x]
    contours, hierarchy = cv2.findContours(
        inset, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE, offset=(margin_x, margin_y)
    )
    if hierarchy is None:
        return None
    parents = hierarchy[0, :, 3]
    frame_index = max(np.flatnonzero(parents < 0), key=lambda index: cv2.contourArea(contours[index]))
    contour = contours[frame_index]
    area = cv2.contourArea(contour)
    if not 0.13 <= area / (width * height) <= 0.75:
        return None

    left, top, frame_width, frame_height = cv2.boundingRect(contour)
    if (
        left <= margin_x or top <= margin_y
        or left + frame_width >= width - margin_x
        or top + frame_height >= height - margin_y
        or frame_width < 0.35 * width or frame_height < 0.30 * height
    ):
        return None

    cell_count = sum(
        cv2.contourArea(contours[index]) >= 0.01 * area
        for index in np.flatnonzero(parents == frame_index)
    )
    if cell_count < 2:
        return None

    hull = cv2.convexHull(contour)
    corners = cv2.approxPolyDP(hull, 0.012 * cv2.arcLength(hull, True), True)
    if len(corners) != 4 or area < 0.95 * cv2.contourArea(hull):
        return None
    frame = _order_quad(corners.reshape(-1, 2).astype(np.float32))
    if not _quad_is_convex(frame):
        return None

    max_edge_gap = max(2, 0.006 * min(width, height))
    fractions = np.linspace(0.05, 0.95, 40)
    for start, end in zip(frame, np.roll(frame, -1, axis=0)):
        samples = start + fractions[:, None] * (end - start)
        distances = [abs(cv2.pointPolygonTest(contour, tuple(point), True)) for point in samples]
        if np.quantile(distances, 0.9) > max_edge_gap:
            return None
    return frame


def _merged_horizontal_coverage(
    segments: list[tuple[float, int, int, int, int, float]], width: int
) -> int:
    """Measure deduplicated horizontal coverage instead of Hough repeat count."""
    intervals = sorted((min(item[1], item[3]), max(item[1], item[3])) for item in segments)
    if not intervals:
        return 0
    merged: list[list[int]] = [list(intervals[0])]
    gap_tolerance = max(6, round(width * 0.01))
    for start, end in intervals[1:]:
        if start <= merged[-1][1] + gap_tolerance:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(end - start for start, end in merged)


def _sparse_rule_group(
    ink: np.ndarray,
    group: list[tuple[float, int, int, int, int, float]],
) -> bool:
    """Reject clusters formed by the two edges of dense text bars."""
    densities = []
    half_window = 15
    sampled_segments = sorted(group, key=lambda item: item[0], reverse=True)[:32]
    for _, x1, y1, x2, y2, _ in sampled_segments:
        start_x, end_x = min(x1, x2), max(x1, x2)
        span = max(1, end_x - start_x)
        for sample_x in (
            start_x + round(span * 0.25),
            start_x + round(span * 0.5),
            start_x + round(span * 0.75),
        ):
            sample_y = y1 + (y2 - y1) * (sample_x - x1) / span
            top = max(0, round(sample_y - half_window))
            bottom = min(ink.shape[0], top + 2 * half_window + 1)
            densities.append(float(ink[top:bottom, sample_x].mean() / 255))
    return bool(densities) and float(np.median(densities)) <= 0.32


def _structural_table_frame(preview: Image.Image) -> np.ndarray | None:
    """Recover a blank-table quad from parallel clusters of long horizontal rules."""
    width, height = preview.size
    gray = cv2.cvtColor(np.asarray(preview), cv2.COLOR_RGB2GRAY)
    ink = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 9
    )
    raw_lines = cv2.HoughLinesP(
        ink,
        1,
        np.pi / 180,
        60,
        minLineLength=round(width * 0.12),
        maxLineGap=15,
    )
    if raw_lines is None:
        return None
    raw_lines = np.asarray(raw_lines).reshape(-1, 4)

    segments = []
    vertical_segments = []
    for x1, y1, x2, y2 in raw_lines:
        dx, dy = int(x2) - int(x1), int(y2) - int(y1)
        length = float(np.hypot(dx, dy))
        angle = float(np.degrees(np.arctan2(dy, dx)))
        if abs(angle) <= 6:
            segments.append((length, int(x1), int(y1), int(x2), int(y2), angle))
        elif 84 <= abs(angle) <= 96 and length >= max(20, height * 0.08):
            vertical_segments.append((length, int(x1), int(y1), int(x2), int(y2), angle))
    if len(segments) < 2:
        return None

    groups: list[list[tuple[float, int, int, int, int, float]]] = []
    for segment in sorted(segments, key=lambda item: (item[2] + item[4]) / 2):
        center = (segment[2] + segment[4]) / 2
        for group in groups:
            group_center = np.mean([(item[2] + item[4]) / 2 for item in group])
            group_angle = np.mean([item[5] for item in group])
            if (
                abs(center - group_center) <= height * 0.03
                and abs(segment[5] - group_angle) <= 3
            ):
                group.append(segment)
                break
        else:
            groups.append([segment])

    rows = []
    for group in groups:
        points = []
        for _, x1, y1, x2, y2, _ in group:
            points.extend(((x1, y1), (x2, y2)))
        left = min(point[0] for point in points)
        right = max(point[0] for point in points)
        center_y = float(np.mean([point[1] for point in points]))
        coverage = _merged_horizontal_coverage(group, width)
        if (
            right - left < width * 0.35
            or coverage < width * 0.35
            or not _sparse_rule_group(ink, group)
        ):
            continue
        rows.append({
            "left": left,
            "right": right,
            "center_y": center_y,
            "length": float(coverage),
            "group": group,
        })
    if len(rows) < 3:
        return None

    candidates = []
    for upper in rows:
        for lower in rows:
            vertical_gap = lower["center_y"] - upper["center_y"]
            horizontal_overlap = (
                min(upper["right"], lower["right"])
                - max(upper["left"], lower["left"])
            )
            if vertical_gap < height * 0.18 or horizontal_overlap < width * 0.25:
                continue
            score = (
                min(upper["length"], lower["length"])
                + horizontal_overlap
                + vertical_gap
            )
            candidates.append((score, upper, lower))
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            item[0],
        ),
        reverse=True,
    )
    for _, upper, lower in candidates:
        if (
            abs(upper["left"] - lower["left"]) > width * 0.2
            or abs(upper["right"] - lower["right"]) > width * 0.2
        ):
            continue
        selected_top = min(upper["center_y"], lower["center_y"])
        selected_bottom = max(upper["center_y"], lower["center_y"])
        boundary_tolerance = height * 0.04

        def aligned_spans(upper_x: int, lower_x: int) -> list[list[int]]:
            spans = []
            minimum_x = min(upper_x, lower_x) - round(width * 0.01)
            maximum_x = max(upper_x, lower_x) + round(width * 0.01)
            for segment in vertical_segments:
                _, x1, y1, x2, y2, _ = segment
                top, bottom = min(y1, y2), max(y1, y2)
                center_x = (x1 + x2) / 2
                if (
                    center_x < minimum_x
                    or center_x > maximum_x
                ):
                    continue
                overlap_start = max(top, round(selected_top))
                overlap_end = min(bottom, round(selected_bottom))
                overlap = overlap_end - overlap_start
                if overlap < max(8, min(segment[0] * 0.3, height * 0.04)):
                    continue
                spans.append([overlap_start, overlap_end])
            return spans

        def side_is_supported(spans: list[list[int]]) -> bool:
            if not spans:
                return False
            spans.sort()
            merged = [list(spans[0])]
            for start, end in spans[1:]:
                if start <= merged[-1][1] + height * 0.03:
                    merged[-1][1] = max(merged[-1][1], end)
                else:
                    merged.append([start, end])
            coverage = sum(end - start for start, end in merged)
            return (
                merged[0][0] <= selected_top + boundary_tolerance
                and merged[-1][1] >= selected_bottom - boundary_tolerance
                and coverage >= (selected_bottom - selected_top) * 0.75
            )

        supported_sides = set()
        if side_is_supported(aligned_spans(upper["left"], lower["left"])):
            supported_sides.add("left")
        if side_is_supported(aligned_spans(upper["right"], lower["right"])):
            supported_sides.add("right")
        if supported_sides != {"left", "right"}:
            continue

        def fit_line(group):
            points = []
            for _, x1, y1, x2, y2, _ in group:
                points.extend(((x1, y1), (x2, y2)))
            return np.polyfit(
                [point[0] for point in points],
                [point[1] for point in points],
                1,
            )

        upper_line = fit_line(upper["group"])
        lower_line = fit_line(lower["group"])
        left = min(upper["left"], lower["left"])
        right = max(upper["right"], lower["right"])
        top = np.polyval(upper_line, (left, right))
        bottom = np.polyval(lower_line, (left, right))
        frame = np.float32([
            [left, top[0]],
            [right, top[1]],
            [right, bottom[1]],
            [left, bottom[0]],
        ])
        if (
            not np.isfinite(frame).all()
            or np.any(frame[:, 0] < 0)
            or np.any(frame[:, 0] >= width)
            or np.any(frame[:, 1] < 0)
            or np.any(frame[:, 1] >= height)
        ):
            continue
        if not _quad_is_convex(frame):
            continue
        frame = _order_quad(frame)
        return frame
    return None


def _table_projection(preview: Image.Image) -> tuple[np.ndarray, tuple[int, int], dict]:
    """Rectify a trusted frame while retaining the full paper extent."""
    frame = _table_frame(preview)
    frame_source = "connected_frame"
    if frame is None:
        frame = _structural_table_frame(preview)
        frame_source = "line_cluster"
    if frame is None:
        return np.eye(3), preview.size, {"status": "no_reliable_frame"}

    horizontal = frame[[1, 2]] - frame[[0, 3]]
    vertical = frame[[3, 2]] - frame[[0, 1]]
    angles = np.degrees(np.arctan2(
        np.concatenate((horizontal[:, 1], vertical[:, 0])),
        np.concatenate((horizontal[:, 0], vertical[:, 1])),
    ))
    max_tilt = float(np.max(np.abs(angles)))
    report = dict(zip(
        ("top_angle_deg", "bottom_angle_deg", "left_angle_deg", "right_angle_deg"),
        [round(float(angle), 3) for angle in angles],
    ))
    report["source"] = frame_source
    if max_tilt <= 0.15 or max_tilt > MAX_RESIDUAL_TILT_DEG:
        report["status"] = "within_tolerance" if max_tilt <= 0.15 else "outside_safe_limit"
        return np.eye(3), preview.size, report

    half_width = float(np.mean(horizontal[:, 0])) / 2
    half_height = float(np.mean(vertical[:, 1])) / 2
    target_frame = frame.mean(axis=0) + np.float32([
        [-half_width, -half_height], [half_width, -half_height],
        [half_width, half_height], [-half_width, half_height],
    ])
    matrix = cv2.getPerspectiveTransform(frame, target_frame)
    page_corners = _image_corners(preview.size)
    projected = cv2.perspectiveTransform(page_corners[None], matrix)[0]
    if (
        not np.isfinite(projected).all()
        or not cv2.isContourConvex(projected)
        or np.any(np.abs(projected - page_corners) > np.array(preview.size) * 0.08)
    ):
        report["status"] = "outside_safe_limit"
        return np.eye(3), preview.size, report

    report["status"] = "applied"
    matrix, size = _expand_projected_canvas(matrix, projected)
    return matrix, size, report


def _text_column_angles(
    mask: np.ndarray, centers: np.ndarray, angle: float, detector: SkewDetector,
) -> tuple[float, float] | None:
    """Look for a persistent gutter and measure the two text columns separately."""
    height, width = mask.shape
    matrix = cv2.getRotationMatrix2D(((width - 1) / 2, (height - 1) / 2), angle, 1.0)
    aligned = cv2.warpAffine(
        mask, matrix, (width, height), flags=cv2.INTER_NEAREST, borderValue=255,
    )
    ink_per_column = np.count_nonzero(aligned == 0, axis=0)
    inner_start, inner_stop = width // 4, 3 * width // 4
    low_ink = ink_per_column[inner_start:inner_stop] <= max(1, ink_per_column.max() * 0.04)
    edges = np.flatnonzero(np.diff(low_ink, prepend=False, append=False)) + inner_start
    left, right = max(
        zip(edges[::2], edges[1::2]), key=lambda gap: gap[1] - gap[0], default=(0, 0),
    )
    if right - left < max(6, round(width * 0.02)):
        return None

    positions = cv2.transform(centers[None], matrix)[0]
    boundaries = np.linspace(0, height, 4)
    populated_bands = 0
    for top, bottom in zip(boundaries, boundaries[1:]):
        band_x = positions[(positions[:, 1] >= top) & (positions[:, 1] < bottom), 0]
        if np.count_nonzero(band_x < left) >= 20 and np.count_nonzero(band_x >= right) >= 20:
            populated_bands += 1
    if populated_bands < 2:
        return None

    left_angle = detector.projection_profile_angle(Image.fromarray(aligned[:, :left]))
    right_angle = detector.projection_profile_angle(Image.fromarray(aligned[:, right:]))
    return angle + left_angle, angle + right_angle


def _text_skew_angles(
    preview: Image.Image, *, check_columns: bool = True,
) -> tuple[float | None, list[float | None], tuple[float, float] | None]:
    """Measure glyph-sized ink across the page, in three bands and on either side of a gutter."""
    gray_preview = preview.convert("L")
    gray_preview.thumbnail((1100, 1100), Image.Resampling.BILINEAR)
    width, height = gray_preview.size
    if min(width, height) < 120:
        return None, [], None

    pad_x, pad_y = round(width * 0.06), round(height * 0.06)
    gray = np.asarray(gray_preview)[pad_y:height - pad_y, pad_x:width - pad_x]
    ink = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 9
    )
    _, labels, stats, centers = cv2.connectedComponentsWithStats(ink)
    widths = stats[:, cv2.CC_STAT_WIDTH]
    heights = stats[:, cv2.CC_STAT_HEIGHT]
    areas = stats[:, cv2.CC_STAT_AREA]
    short_edge = min(gray.shape)
    glyphs = (
        (widths >= 2)
        & (widths <= gray.shape[1] * 0.065)
        & (heights >= max(3, round(short_edge * 0.007)))
        & (heights <= short_edge * 0.08)
        & (heights >= widths * 0.25)
        & (areas >= 7)
        & (areas < widths * heights * 0.93)
    )
    glyphs[0] = False
    if np.count_nonzero(glyphs) < 60:
        return None, [], None

    mask = np.where(glyphs[labels], 0, 255).astype(np.uint8)
    detector = SkewDetector()
    angle = detector.projection_profile_angle(Image.fromarray(mask))
    band_angles = []
    boundaries = np.rint(np.linspace(0, mask.shape[0], 4)).astype(int)
    for top, bottom in zip(boundaries, boundaries[1:]):
        band_glyphs = glyphs & (centers[:, 1] >= top) & (centers[:, 1] < bottom)
        band_angle = (
            detector.projection_profile_angle(Image.fromarray(mask[top:bottom]))
            if np.count_nonzero(band_glyphs) >= 20 else None
        )
        band_angles.append(band_angle)
    column_angles = (
        _text_column_angles(mask, centers[glyphs], angle, detector) if check_columns else None
    )
    return angle, band_angles, column_angles


def _text_rotation_projection(
    size: tuple[int, int], angle: float | None, band_angles: list[float | None],
    *, column_angles: tuple[float, float] | None = None,
) -> tuple[np.ndarray, tuple[int, int], dict]:
    report = {"status": "insufficient_text"}
    if angle is None:
        return np.eye(3), size, report

    available_bands = [band for band in band_angles if band is not None]
    measurements = column_angles if column_angles is not None else available_bands
    selected_angle = float(np.median(measurements)) if len(measurements) >= 2 else angle
    magnitude = abs(round(selected_angle, 2))
    report.update(
        angle_deg=round(selected_angle, 2),
        detected_angle_deg=round(angle, 2),
        band_angles_deg=[round(band, 2) if band is not None else None for band in band_angles],
    )
    if column_angles is not None:
        report["column_angles_deg"] = [round(value, 2) for value in column_angles]
    if column_angles is not None and round(abs(column_angles[0] - column_angles[1]), 2) > COLUMN_ANGLE_TOLERANCE_DEG:
        report["status"] = "inconsistent_text_angles"
    elif magnitude <= TEXT_TILT_TOLERANCE_DEG:
        report["status"] = "within_tolerance"
    elif magnitude > MAX_RESIDUAL_TILT_DEG:
        report["status"] = "outside_safe_limit"
    elif (
        any(value * selected_angle <= 0 for value in measurements)
        or sum(
            abs(value - selected_angle) <= BAND_ANGLE_TOLERANCE_DEG
            for value in measurements
        ) < 2
    ):
        report["status"] = "inconsistent_text_angles"
    else:
        center = ((size[0] - 1) / 2, (size[1] - 1) / 2)
        matrix = np.vstack((cv2.getRotationMatrix2D(center, selected_angle, 1.0), [0, 0, 1]))
        projected = cv2.perspectiveTransform(_image_corners(size)[None], matrix)[0]
        matrix, expanded_size = _expand_projected_canvas(matrix, projected)
        report["status"] = "applied"
        return matrix, expanded_size, report
    return np.eye(3), size, report


def _refine_page_geometry(
    preview: Image.Image, clockwise: int,
) -> tuple[np.ndarray, tuple[int, int], dict, dict]:
    matrix, size, table_report = _table_projection(preview)
    table_applied = table_report["status"] == "applied"
    if table_applied and table_report["source"] == "connected_frame":
        return matrix, size, table_report, {"status": "table_aligned"}

    angle, band_angles, column_angles = _text_skew_angles(_rotate_clockwise(preview, clockwise))
    if table_applied:
        if angle is not None:
            table_preview = Image.fromarray(_warp_image(preview, matrix, size))
            after_angle, _, _ = _text_skew_angles(
                _rotate_clockwise(table_preview, clockwise), check_columns=False,
            )
            if after_angle is not None and abs(after_angle) > TEXT_TILT_TOLERANCE_DEG:
                table_report.update(
                    status="rejected_text_residual",
                    text_angle_before_deg=round(angle, 2),
                    text_angle_candidate_deg=round(after_angle, 2),
                )
        if table_report["status"] == "applied":
            return matrix, size, table_report, {"status": "table_aligned"}

    matrix, size, text_report = _text_rotation_projection(
        preview.size, angle, band_angles, column_angles=column_angles,
    )
    return matrix, size, table_report, text_report


def normalize_illumination(
    image: Image.Image,
    strength: float = 0.78,
    contrast_strength: float = DEFAULT_CONTRAST_STRENGTH,
) -> Image.Image:
    """Reduce soft shadows and color casts while preserving ink and stamps."""
    image_array = np.asarray(image)
    lab = cv2.cvtColor(image_array, cv2.COLOR_RGB2LAB)
    lightness, _, _ = cv2.split(lab)

    small_width = max(64, image.width // 8)
    small_height = max(64, image.height // 8)
    small_lightness = cv2.resize(
        lightness,
        (small_width, small_height),
        interpolation=cv2.INTER_AREA,
    )
    kernel_size = max(15, min(61, min(small_width, small_height) // 6))
    if kernel_size % 2 == 0:
        kernel_size += 1
    background = cv2.medianBlur(small_lightness, kernel_size)
    background = cv2.resize(
        background,
        (image.width, image.height),
        interpolation=cv2.INTER_CUBIC,
    )
    flat_lightness = cv2.divide(lightness, background, scale=255)
    balanced_lightness = cv2.addWeighted(
        flat_lightness,
        strength,
        lightness,
        1.0 - strength,
        0,
    )
    contrast = cv2.createCLAHE(clipLimit=1.2, tileGridSize=(8, 8))
    enhanced_lightness = contrast.apply(balanced_lightness)
    if contrast_strength:
        levels = np.arange(256)
        curve = np.interp(levels, [0, 96, 168, 212, 238, 255], [0, 71, 137, 201, 249, 255])
        lookup = np.rint(levels + contrast_strength * (curve - levels)).astype(np.uint8)
        enhanced_lightness = cv2.LUT(enhanced_lightness, lookup)
    green_red = lab[:, :, 1].astype(np.int16)
    blue_yellow = lab[:, :, 2].astype(np.int16)
    green_red_shift = 128 - int(np.median(green_red))
    blue_yellow_shift = 128 - int(np.median(blue_yellow))
    balanced_green_red = np.clip(
        green_red + round(green_red_shift * 0.65),
        0,
        255,
    ).astype(np.uint8)
    balanced_blue_yellow = np.clip(
        blue_yellow + round(blue_yellow_shift * 0.65),
        0,
        255,
    ).astype(np.uint8)
    enhanced_lab = cv2.merge(
        (enhanced_lightness, balanced_green_red, balanced_blue_yellow)
    )
    return Image.fromarray(cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2RGB))


def binarize_page(
    image: Image.Image,
    *,
    high: float = DEFAULT_BINARIZE_HIGH,
    low: float = DEFAULT_BINARIZE_LOW,
) -> Image.Image:
    """Flatten the paper background and map ink to black, keeping stroke edges."""
    gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    short_edge = min(gray.shape)
    kernel_size = max(15, int(round(short_edge * 0.025)) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    background = cv2.GaussianBlur(background, (0, 0), kernel_size / 3.4)
    normalized = cv2.divide(gray, np.maximum(background, 1), scale=255)
    ink = np.clip(
        (high - normalized.astype(np.float32)) / (high - low), 0.0, 1.0
    )
    return Image.fromarray((255 * (1.0 - ink)).astype(np.uint8)).convert("RGB")


def _rotate_clockwise(image: Image.Image, angle: int) -> Image.Image:
    if angle == 0:
        return image
    if angle == 90:
        return image.transpose(Image.Transpose.ROTATE_270)
    if angle == 180:
        return image.transpose(Image.Transpose.ROTATE_180)
    if angle == 270:
        return image.transpose(Image.Transpose.ROTATE_90)
    raise ValueError("旋转角度只支持 0、90、180、270")


def detect_auto_rotation(image: Image.Image) -> tuple[int, str]:
    """Detect coarse orientation with Tesseract OSD when available."""
    try:
        import pytesseract
    except ImportError:
        return 0, "pytesseract_unavailable"

    preview = image.copy()
    preview.thumbnail((1200, 1200))
    try:
        osd = pytesseract.image_to_osd(
            preview,
            config="--psm 0 --oem 1",
            output_type=pytesseract.Output.DICT,
        )
        clockwise = int(float(osd.get("rotate", osd.get("Rotate", 0)) or 0))
        confidence = float(
            osd.get("orientation_conf", osd.get("Orientation confidence", 0)) or 0
        )
        if confidence < 3.0:
            return 0, f"osd_low_confidence:{confidence:.2f}"
        return clockwise % 360, f"osd:{confidence:.2f}"
    except Exception as exc:
        return 0, f"osd_failed:{type(exc).__name__}"


def resolve_page_size(
    image_size: tuple[int, int],
    page_size: str,
    dpi: int,
) -> tuple[tuple[int, int], str]:
    """Resolve the final raster size and explain whether a standard page was used."""
    if page_size == "auto":
        ratio = max(image_size) / min(image_size)
        page_size = "auto_a4" if 1.25 <= ratio <= 1.55 else "auto_detected"
    dimensions = _paper_dimensions_mm(page_size, image_size)
    if dimensions is None:
        return image_size, page_size
    width_mm, height_mm = dimensions
    return (round(width_mm * dpi / 25.4), round(height_mm * dpi / 25.4)), page_size


def _paper_dimensions_mm(
    page_size: str, image_size: tuple[int, int]
) -> tuple[float, float] | None:
    dimensions = PAGE_SIZES_MM.get(page_size.removeprefix("auto_"))
    if dimensions is None or image_size[0] <= image_size[1]:
        return dimensions
    return dimensions[::-1]


def _contained_size(
    source: tuple[int, int], canvas: tuple[int, int]
) -> tuple[int, int]:
    scale = min(np.divide(canvas, source))
    return max(1, round(source[0] * scale)), max(1, round(source[1] * scale))


def _shadow_score(image: Image.Image) -> float:
    lightness = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2LAB)[:, :, 0]
    means = []
    for row in np.array_split(lightness, min(4, image.height), axis=0):
        for block in np.array_split(row, min(4, image.width), axis=1):
            means.append(float(block.mean()))
    return float(np.std(means))


def _check_output_paths(source: Path, destinations: list[Path]) -> None:
    claimed = {source.resolve()}
    for destination in destinations:
        resolved = destination.resolve()
        if resolved in claimed:
            raise ValueError("输出不能覆盖原始拍照件或与其他输出共用路径")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"输出已存在，请选择新文件名: {destination}")
        claimed.add(resolved)


def _save_new_outputs(outputs: list[tuple[Path, Callable[[Path], object]]]) -> None:
    """Prepare all outputs before publishing each file without clobbering."""
    with ExitStack() as stack:
        staged = []
        for destination, save in outputs:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary_dir = stack.enter_context(
                TemporaryDirectory(prefix=".pdf-photo-", dir=destination.parent)
            )
            temporary = Path(temporary_dir) / destination.name
            save(temporary)
            staged.append((temporary, destination))

        published = []
        try:
            for temporary, destination in staged:
                os.link(temporary, destination)
                published.append((temporary, destination))
        except OSError:
            for temporary, destination in reversed(published):
                try:
                    if os.path.samestat(temporary.stat(), destination.lstat()):
                        destination.unlink()
                except FileNotFoundError:
                    continue
            raise


def normalize_photo_pdf(
    input_path: str | Path,
    output_path: str | Path,
    *,
    dpi: int = 300,
    jpeg_quality: int = 90,
    page_size: str = DEFAULT_PAGE_SIZE,
    rotation: str = "auto",
    illumination_strength: float = 0.78,
    contrast_strength: float = DEFAULT_CONTRAST_STRENGTH,
    quad: list[list[float]] | None = None,
    binarize: bool = False,
    binarize_high: float = DEFAULT_BINARIZE_HIGH,
    binarize_low: float = DEFAULT_BINARIZE_LOW,
    debug_image: str | Path | None = None,
    report_file: str | Path | None = None,
) -> dict:
    """Run the complete photo-to-regular-PDF pipeline."""
    source_path = Path(input_path)
    target_path = Path(output_path)
    debug_path = Path(debug_image) if debug_image is not None else None
    report_path = Path(report_file) if report_file is not None else None
    _check_output_paths(source_path, [
        destination for destination in (target_path, debug_path, report_path)
        if destination is not None
    ])
    if not 0 <= binarize_low < binarize_high <= 255:
        raise ValueError("黑白化阈值必须满足 0 <= 下阈值 < 上阈值 <= 255")

    photo = load_photo(source_path)
    content_subject = None
    if quad is not None:
        detected_quad = _manual_quad(quad, photo.size)
        quad_source = "manual"
    else:
        detected_quad = detect_document_quad(photo)
        quad_source = "paper_edges" if detected_quad is not None else "full_image"
        if detected_quad is None:
            content_subject = detect_content_subject(photo)
            if content_subject is not None:
                detected_quad = content_subject["quad"]
                quad_source = "content_subject"
    paper_matrix, paper_size, quad_meta = _paper_projection(photo.size, detected_quad)
    quad_meta["source"] = quad_source
    if content_subject is not None:
        quad_meta["content_subject"] = {
            key: value for key, value in content_subject.items() if key != "quad"
        }
    else:
        quad_meta["content_subject"] = {"status": "not_detected"}
    preview_size = _contained_size(paper_size, (1600, 1600)) if max(paper_size) > 1600 else paper_size
    preview_matrix = _resize_matrix(paper_size, preview_size) @ paper_matrix
    preview = Image.fromarray(_warp_image(photo, preview_matrix, preview_size))

    if rotation == "auto":
        clockwise, rotation_reason = detect_auto_rotation(preview)
    else:
        clockwise = int(rotation)
        rotation_reason = "explicit"

    if quad_meta["quad_detected"]:
        refinement_matrix, refined_preview_size, table_report, text_report = (
            _refine_page_geometry(preview, clockwise)
        )
    else:
        refinement_matrix, refined_preview_size = np.eye(3), preview_size
        table_report = {"status": "no_paper_quad"}
        text_report = {"status": "no_document_region"}
    corrected_size = tuple(
        round(refined * paper / preview_edge)
        for refined, paper, preview_edge in zip(refined_preview_size, paper_size, preview_size)
    )
    swaps_axes = clockwise in (90, 270)
    oriented_size = corrected_size[::-1] if swaps_axes else corrected_size
    final_size, resolved_page_size = resolve_page_size(oriented_size, page_size, dpi)
    if quad_source in ("paper_edges", "manual") and resolved_page_size in ("a4", "auto_a4"):
        content_size = final_size
    else:
        content_size = _contained_size(oriented_size, final_size)
    render_size = content_size[::-1] if swaps_axes else content_size
    composed = _resize_matrix(refined_preview_size, render_size) @ refinement_matrix
    raster = _warp_image(photo, composed @ preview_matrix, render_size)
    oriented = _rotate_clockwise(Image.fromarray(raster), clockwise)

    if binarize:
        enhanced = binarize_page(oriented, high=binarize_high, low=binarize_low)
    else:
        enhanced = normalize_illumination(
            oriented,
            strength=illumination_strength,
            contrast_strength=contrast_strength,
        )
    if table_report["status"] == "applied" or text_report["status"] == "applied":
        clip_points = cv2.perspectiveTransform(_image_corners(preview_size)[None], composed)[0]
        clip_mask = np.zeros(raster.shape[:2], dtype=np.uint8)
        cv2.fillConvexPoly(clip_mask, np.rint(clip_points).astype(np.int32), 255)
        oriented_mask = _rotate_clockwise(Image.fromarray(clip_mask), clockwise)
        white = Image.new("RGB", content_size, "white")
        oriented = Image.composite(oriented, white, oriented_mask)
        enhanced = Image.composite(enhanced, white, oriented_mask)

    canvas = enhanced
    if content_size != final_size:
        canvas = Image.new("RGB", final_size, "white")
        left = (canvas.width - enhanced.width) // 2
        top = (canvas.height - enhanced.height) // 2
        canvas.paste(enhanced, (left, top))

    outputs = []
    if debug_path is not None:
        debug_array = np.asarray(photo).copy()
        if detected_quad is not None:
            cv2.polylines(
                debug_array,
                [np.round(detected_quad).astype(np.int32)],
                True,
                (255, 0, 0) if quad_source in ("paper_edges", "manual") else (0, 160, 0),
                max(1, round(max(photo.size) / 600)),
            )
        outputs.append((debug_path, partial(Image.fromarray(debug_array).save, quality=95)))

    dimensions_mm = _paper_dimensions_mm(resolved_page_size, final_size)
    physical_dpi = (
        tuple(pixels * 25.4 / mm for pixels, mm in zip(final_size, dimensions_mm))
        if dimensions_mm else (dpi, dpi)
    )
    illumination_report = {
        "strength": illumination_strength,
        "contrast_strength": contrast_strength,
        "before_shadow_score": _shadow_score(oriented),
        "after_shadow_score": _shadow_score(enhanced),
    }
    if binarize:
        illumination_report["status"] = "binarized"
    report = {
        "input": str(source_path),
        "output": str(target_path),
        "exif_transposed_size": photo.size,
        "quad": quad_meta,
        "rotation_clockwise": clockwise,
        "rotation_reason": rotation_reason,
        "table_alignment": table_report,
        "text_deskew": text_report,
        "illumination": illumination_report,
        "page_size": resolved_page_size,
        "output_size": final_size,
        "content_size": content_size,
        "dpi": dpi,
    }
    if binarize:
        report["binarization"] = {
            "status": "applied",
            "high": binarize_high,
            "low": binarize_low,
        }
    if report_path is not None:
        report_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        outputs.append((report_path, lambda path: path.write_text(report_text, encoding="utf-8")))
    outputs.append((target_path, partial(canvas.save, format="PDF", dpi=physical_dpi, quality=jpeg_quality)))
    _save_new_outputs(outputs)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="将拍照文书转正、透视裁边、去阴影并输出规整 PDF",
    )
    parser.add_argument("-i", "--input", required=True, help="输入拍照件")
    parser.add_argument("-o", "--output", required=True, help="输出 PDF")
    parser.add_argument("--dpi", type=int, default=300, help="输出 DPI，默认 300")
    parser.add_argument("--jpeg-quality", type=int, default=90, help="PDF JPEG 质量，默认 90")
    parser.add_argument(
        "--page-size",
        choices=["auto", "a4", "letter", "original"],
        default=DEFAULT_PAGE_SIZE,
        help="默认 A4，可靠纸面铺满页框。auto 按纸面比例选尺寸，original 保留纸面比例",
    )
    parser.add_argument(
        "--rotate",
        choices=["auto", "0", "90", "180", "270"],
        default="auto",
        help="粗方向；auto 使用 Tesseract OSD，输入 EXIF 方向会先自动转正",
    )
    parser.add_argument(
        "--illumination-strength",
        type=float,
        default=0.78,
        help="阴影归一化强度 0-1，默认 0.78",
    )
    parser.add_argument(
        "--contrast-strength",
        type=float,
        default=DEFAULT_CONTRAST_STRENGTH,
        help="附加对比度增强强度 0-1，默认 0.7",
    )
    parser.add_argument(
        "--quad",
        help=(
            "手动指定纸面四角，格式 x1,y1,x2,y2,x3,y3,x4,y4；"
            "使用 0-1 归一化坐标（相对 EXIF 转正后的画面），用于纸边检测不可靠的拍照件"
        ),
    )
    parser.add_argument(
        "--bw",
        "--black-white",
        dest="bw",
        action="store_true",
        help="输出黑白页面：背景归一后把墨迹映射为纯黑，保留签名与印章边缘",
    )
    parser.add_argument(
        "--bw-high",
        type=float,
        default=DEFAULT_BINARIZE_HIGH,
        help="黑白化上阈值，高于该值视为纸面，默认 235",
    )
    parser.add_argument(
        "--bw-low",
        type=float,
        default=DEFAULT_BINARIZE_LOW,
        help="黑白化下阈值，低于该值视为墨迹，默认 195",
    )
    parser.add_argument("--debug-image", help="另存检测边框调试图")
    parser.add_argument("--report", help="以 JSON 保存处理报告")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not 1 <= args.dpi <= 600:
        raise ValueError("输出 DPI 必须在 1-600")
    if not 1 <= args.jpeg_quality <= 100:
        raise ValueError("JPEG 质量必须在 1-100")
    if not 0 <= args.illumination_strength <= 1:
        raise ValueError("阴影归一化强度必须在 0-1")
    if not 0 <= args.contrast_strength <= 1:
        raise ValueError("对比度增强强度必须在 0-1")
    if not 0 <= args.bw_low < args.bw_high <= 255:
        parser.error("黑白化阈值必须满足 0 <= 下阈值 < 上阈值 <= 255")
    manual_quad = None
    if args.quad:
        try:
            manual_quad = parse_quad(args.quad)
        except ValueError as exc:
            parser.error(str(exc))

    try:
        report = normalize_photo_pdf(
            args.input,
            args.output,
            dpi=args.dpi,
            jpeg_quality=args.jpeg_quality,
            page_size=args.page_size,
            rotation=args.rotate,
            illumination_strength=args.illumination_strength,
            contrast_strength=args.contrast_strength,
            quad=manual_quad,
            binarize=args.bw,
            binarize_high=args.bw_high,
            binarize_low=args.bw_low,
            debug_image=args.debug_image,
            report_file=args.report,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("拍照件规整完成")
    print(f"EXIF 转正尺寸: {report['exif_transposed_size'][0]}×{report['exif_transposed_size'][1]}")
    quad_source = report["quad"]["source"]
    print(
        "纸面四角: 手动指定" if quad_source == "manual"
        else "纸面四边检测: 失败；内容主体 fallback: 成功" if quad_source == "content_subject"
        else "纸面四边检测: 成功" if quad_source == "paper_edges"
        else "纸面四边检测: 失败，保留整幅图像"
    )
    print(f"粗方向旋转: {report['rotation_clockwise']}°（{report['rotation_reason']}）")
    print(f"表框校正: {report['table_alignment']['status']}")
    text_report = report["text_deskew"]
    text_angle = f"（检测 {text_report['angle_deg']}°）" if "angle_deg" in text_report else ""
    print(f"正文纠斜: {text_report['status']}{text_angle}")
    print(
        "阴影块亮度离散: "
        f"{report['illumination']['before_shadow_score']:.2f} → "
        f"{report['illumination']['after_shadow_score']:.2f}"
    )
    print(f"页面策略: {report['page_size']}；输出尺寸: {report['output_size'][0]}×{report['output_size'][1]}")
    if report.get("binarization", {}).get("status") == "applied":
        print(
            f"黑白化: 上阈值 {report['binarization']['high']}，"
            f"下阈值 {report['binarization']['low']}"
        )
    print(f"输出文件: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
