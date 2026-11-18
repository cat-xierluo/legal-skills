#!/usr/bin/env python3
"""Lossless content-stream deskew for original-input OCR paths."""

from __future__ import annotations

import math
import shutil
from pathlib import Path

import fitz
from PIL import Image

from pdf_preprocess_skew import SkewDetector


DETECTION_DPI = 150
MIN_DETECTION_DPI = 36
MAX_DETECTION_SKEW = 15.0
MAX_STREAM_SKEW = 5.0
MIN_INK_RATIO = 0.00002
MAX_CORRECTION_PASSES = 3
MAX_DETECTION_PIXELS = 25_000_000


def _render_page(page: fitz.Page, dpi: int) -> Image.Image:
    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
    mode = {1: "L", 3: "RGB"}.get(pixmap.n)
    if mode is None:
        raise RuntimeError(f"不支持的 PDF 渲染通道数: {pixmap.n}")
    return Image.frombytes(mode, (pixmap.width, pixmap.height), pixmap.samples)


def _page_pixels(box: fitz.Rect, dpi: int) -> int:
    width_px = box.width * dpi / 72.0
    height_px = box.height * dpi / 72.0
    return int(width_px * height_px)


def _bounded_detection_dpi(
    box: fitz.Rect,
    requested_dpi: int,
    max_pixels: int,
) -> tuple[int, str | None]:
    """Lower the detection DPI so one page stays inside the pixel budget."""
    if not all(math.isfinite(value) for value in (box.x0, box.y0, box.x1, box.y1)):
        return 0, "invalid_page_box"
    if box.width <= 0 or box.height <= 0:
        return 0, "invalid_page_box"
    if max_pixels <= 0:
        return requested_dpi, None
    if _page_pixels(box, requested_dpi) <= max_pixels:
        return requested_dpi, None

    area_points = max(box.width * box.height, 1.0)
    safe_dpi = int(math.floor(math.sqrt(max_pixels * 72.0 * 72.0 / area_points)))
    safe_dpi = max(MIN_DETECTION_DPI, min(safe_dpi, requested_dpi))
    if _page_pixels(box, safe_dpi) > max_pixels:
        return 0, "page_too_large_for_detection"
    return safe_dpi, "detection_dpi_reduced"


def _has_reliable_ink(image: Image.Image) -> bool:
    import numpy as np

    gray = np.asarray(image.convert("L"))
    height, width = gray.shape
    body = gray[int(height * 0.1):int(height * 0.9), :]
    dark_pixels = int((body < 160).sum())
    minimum_pixels = max(32, int(body.size * MIN_INK_RATIO))
    return dark_pixels >= minimum_pixels


def _has_simple_page_box(page: fitz.Page) -> bool:
    media_box = page.mediabox
    crop_box = page.cropbox
    return all(
        abs(first - second) <= 0.1
        for first, second in (
            (media_box.x0, crop_box.x0),
            (media_box.y0, crop_box.y0),
            (media_box.x1, crop_box.x1),
            (media_box.y1, crop_box.y1),
        )
    )


def _content_rotation_matrix(box: fitz.Rect, angle: float) -> bytes | None:
    """Build one rotation+scale matrix around the visible page-box centre."""
    width = float(box.width)
    height = float(box.height)
    radians = math.radians(angle)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    rotated_width = width * abs(cosine) + height * abs(sine)
    rotated_height = height * abs(cosine) + width * abs(sine)
    if width <= 0 or height <= 0 or rotated_width <= 0 or rotated_height <= 0:
        return None
    margin = min(0.4, width * 0.002, height * 0.002)
    scale = min(
        (width - margin) / rotated_width,
        (height - margin) / rotated_height,
    )
    if not math.isfinite(scale) or scale <= 0.0 or scale > 1.0:
        return None

    a = scale * cosine
    b = scale * sine
    center_x = (float(box.x0) + float(box.x1)) / 2.0
    center_y = (float(box.y0) + float(box.y1)) / 2.0
    e = center_x - a * center_x + b * center_y
    f = center_y - b * center_x - a * center_y
    return (
        f"{a:.10f} {b:.10f} {-b:.10f} {a:.10f} "
        f"{e:.10f} {f:.10f} cm\n"
    ).encode("ascii")


def _best_reported_angle(detection) -> float:
    """Return the most trustworthy angle estimate for reporting."""
    if detection.method != "none":
        return float(detection.angle)
    hough = float(detection.hough_angle)
    projection = float(detection.projection_angle)
    if abs(hough) == 0.0 and abs(projection) == 0.0:
        return 0.0
    if abs(hough) >= abs(projection):
        return hough
    return projection


def _estimate_correction_angle(
    image: Image.Image,
    detector: SkewDetector,
    threshold: float,
) -> tuple[float, float]:
    """Accumulate the correction angle until the simulated residual is small."""
    working = image
    total = 0.0
    residual = 0.0
    for _ in range(MAX_CORRECTION_PASSES):
        residual = float(detector.detect(working).angle)
        if abs(residual) <= threshold:
            break
        total += residual
        working = working.rotate(
            residual,
            resample=Image.BICUBIC,
            expand=False,
            fillcolor="white",
        )
    return total, residual


def deskew_pdf_content_streams(
    input_path: str | Path,
    output_path: str | Path,
    *,
    skew_threshold: float = 0.3,
    detection_dpi: int = DETECTION_DPI,
    max_pixels: int = MAX_DETECTION_PIXELS,
    skip_pages: set[int] | None = None,
    quiet: bool = False,
) -> dict:
    """Detect page skew and rotate original content streams without re-encoding."""
    skipped_pages = set(skip_pages or ())
    detector = SkewDetector(
        skew_threshold=skew_threshold,
        max_reasonable_skew=MAX_DETECTION_SKEW,
    )
    records: list[dict] = []
    deskewed_pages = 0
    normalized_pages = 0
    document_changed = False

    with fitz.open(input_path) as document:
        total_pages = len(document)
        for page_number, page in enumerate(document, start=1):
            record = {
                "page": page_number,
                "detected_angle": 0.0,
                "method": "skipped",
                "action": "not_changed",
                "residual_angle": None,
                "reason": None,
            }
            records.append(record)

            if page_number in skipped_pages:
                record["method"] = "skipped_page"
                continue

            if int(page.rotation or 0) != 0:
                if not hasattr(page, "remove_rotation"):
                    record["method"] = "unsupported_rotation"
                    record["reason"] = "unsupported_rotation"
                    continue
                page.remove_rotation()
                normalized_pages += 1
                document_changed = True

            effective_dpi, dpi_reason = _bounded_detection_dpi(
                page.mediabox,
                detection_dpi,
                max_pixels,
            )
            if effective_dpi <= 0:
                record["method"] = "detection_skipped"
                record["reason"] = dpi_reason
                continue
            if dpi_reason:
                record["reason"] = dpi_reason

            try:
                image = _render_page(page, effective_dpi)
                detection = detector.detect(image)
                reliable_ink = _has_reliable_ink(image)
            except Exception as exc:
                record.update(
                    {
                        "method": "detection_error",
                        "reason": f"detection_error:{type(exc).__name__}",
                    }
                )
                continue

            reported_angle = _best_reported_angle(detection)
            record.update(
                {
                    "detected_angle": reported_angle,
                    "method": detection.method,
                    "hough_confidence": detection.hough_confidence,
                    "projection_angle": detection.projection_angle,
                    "detection_dpi": effective_dpi,
                }
            )

            if not reliable_ink:
                record["reason"] = "insufficient_ink"
                continue
            if abs(reported_angle) > MAX_STREAM_SKEW:
                record["reason"] = "above_safe_limit"
                continue
            if detection.method == "none" or abs(reported_angle) < skew_threshold:
                record["reason"] = record["reason"] or "below_threshold"
                continue
            if not _has_simple_page_box(page):
                record["reason"] = "non_standard_page_box"
                continue

            content_xrefs = page.get_contents()
            if not content_xrefs:
                record["reason"] = "no_content_stream"
                continue
            correction_angle, _simulated_residual = _estimate_correction_angle(
                image,
                detector,
                skew_threshold,
            )
            if abs(correction_angle) > MAX_STREAM_SKEW:
                record["reason"] = "above_safe_limit"
                continue
            matrix = _content_rotation_matrix(page.mediabox, correction_angle)
            if matrix is None:
                record["reason"] = "unsafe_rotation_scale"
                continue

            original_contents = page.read_contents()
            wrapped_contents = b"q\n" + matrix + original_contents + b"\nQ\n"
            document.update_stream(content_xrefs[0], wrapped_contents)
            page.set_contents(content_xrefs[0])
            document_changed = True
            deskewed_pages += 1
            record["action"] = "content_stream_rotated"
            record["correction_angle"] = correction_angle

        if document_changed:
            document.save(output_path, garbage=3, deflate=True)
        else:
            shutil.copy2(input_path, output_path)

    residuals = _measure_output_residuals(
        output_path,
        records,
        detector,
        skew_threshold,
        detection_dpi,
        max_pixels,
    )
    for record, residual in zip(records, residuals):
        if record["action"] == "content_stream_rotated":
            record["residual_angle"] = residual
            if residual is None:
                record["reason"] = "residual_unverified"
            elif abs(residual) > skew_threshold:
                record["reason"] = "residual_above_threshold"

    result = {
        "total_pages": total_pages,
        "deskewed_pages": deskewed_pages,
        "normalized_rotation_pages": normalized_pages,
        "pages": records,
    }
    if not quiet:
        print("\n[原图倾斜矫正] 内容流无损旋正:")
        print(f"  检测页数: {total_pages}")
        print(f"  矫正页数: {deskewed_pages}")
        for record in records:
            angle = float(record.get("detected_angle", 0.0))
            residual = record.get("residual_angle")
            residual_text = (
                f"；残余 {float(residual):+.2f}°" if residual is not None else ""
            )
            reason = record.get("reason")
            suffix = f"；原因: {reason}" if reason else ""
            print(
                f"  第 {record['page']} 页: 检出 {angle:+.2f}° / "
                f"{record.get('method', 'unknown')} / {record['action']}"
                f"{residual_text}{suffix}"
            )
    return result


def _measure_output_residuals(
    output_path: str | Path,
    records: list[dict],
    detector: SkewDetector,
    skew_threshold: float,
    detection_dpi: int,
    max_pixels: int,
) -> list[float | None]:
    """Measure the real post-rotation skew for every corrected page."""
    residuals: list[float | None] = [None] * len(records)
    corrected_pages = [
        record["page"]
        for record in records
        if record["action"] == "content_stream_rotated"
    ]
    if not corrected_pages:
        return residuals

    with fitz.open(output_path) as document:
        for page_number in corrected_pages:
            page = document[page_number - 1]
            effective_dpi, _reason = _bounded_detection_dpi(
                page.mediabox,
                detection_dpi,
                max_pixels,
            )
            if effective_dpi <= 0:
                continue
            try:
                image = _render_page(page, effective_dpi)
                detection = detector.detect(image)
                residual = (
                    float(detection.angle)
                    if detection.method != "none"
                    else _best_reported_angle(detection)
                )
                residuals[page_number - 1] = (
                    residual if abs(residual) >= skew_threshold else 0.0
                )
            except Exception:
                residuals[page_number - 1] = None
    return residuals
