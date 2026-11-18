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
MAX_STREAM_SKEW = 5.0
MIN_INK_RATIO = 0.00002


def _render_page(page: fitz.Page, dpi: int) -> Image.Image:
    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
    mode = {1: "L", 3: "RGB"}.get(pixmap.n)
    if mode is None:
        raise RuntimeError(f"不支持的 PDF 渲染通道数: {pixmap.n}")
    return Image.frombytes(mode, (pixmap.width, pixmap.height), pixmap.samples)


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
    width = float(box.width)
    height = float(box.height)
    radians = math.radians(angle)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    rotated_width = width * abs(cosine) + height * abs(sine)
    rotated_height = height * abs(cosine) + width * abs(sine)
    scale_x = (width - 0.4) / rotated_width
    scale_y = (height - 0.4) / rotated_height
    scale = min(scale_x, scale_y)
    if not math.isfinite(scale) or scale <= 0.0 or scale > 1.0:
        return None

    a = scale * cosine
    b = scale * sine
    center_x = width / 2.0
    center_y = height / 2.0
    e = center_x - a * center_x + b * center_y
    f = center_y - b * center_x - a * center_y
    return (
        f"{a:.10f} {b:.10f} {-b:.10f} {a:.10f} "
        f"{e:.10f} {f:.10f} cm\n"
    ).encode("ascii")


def deskew_pdf_content_streams(
    input_path: str | Path,
    output_path: str | Path,
    *,
    skew_threshold: float = 0.3,
    detection_dpi: int = DETECTION_DPI,
    skip_pages: set[int] | None = None,
    quiet: bool = False,
) -> dict:
    """Detect page skew and rotate original content streams without re-encoding."""
    skipped_pages = set(skip_pages or ())
    detector = SkewDetector(
        skew_threshold=skew_threshold,
        max_reasonable_skew=MAX_STREAM_SKEW,
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
            }
            records.append(record)

            if page_number in skipped_pages:
                record["method"] = "skipped_page"
                continue

            if int(page.rotation or 0) != 0:
                if not hasattr(page, "remove_rotation"):
                    record["method"] = "unsupported_rotation"
                    continue
                page.remove_rotation()
                normalized_pages += 1
                document_changed = True

            try:
                image = _render_page(page, detection_dpi)
                detection = detector.detect(image)
                reliable_ink = _has_reliable_ink(image)
            except Exception as exc:
                record.update(
                    {
                        "method": "detection_error",
                        "reason": str(exc),
                    }
                )
                continue

            record.update(
                {
                    "detected_angle": detection.angle,
                    "method": detection.method,
                    "hough_confidence": detection.hough_confidence,
                    "projection_angle": detection.projection_angle,
                }
            )

            if detection.method == "none":
                continue
            if not reliable_ink:
                record["reason"] = "insufficient_ink"
                continue
            if abs(detection.angle) < skew_threshold:
                record["reason"] = "below_threshold"
                continue
            if abs(detection.angle) > MAX_STREAM_SKEW:
                record["reason"] = "above_safe_limit"
                continue
            if not _has_simple_page_box(page):
                record["reason"] = "non_standard_page_box"
                continue

            content_xrefs = page.get_contents()
            if not content_xrefs:
                record["reason"] = "no_content_stream"
                continue
            matrix = _content_rotation_matrix(page.mediabox, detection.angle)
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

        if document_changed:
            document.save(output_path, garbage=3, deflate=True)
        else:
            shutil.copy2(input_path, output_path)

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
            reason = record.get("reason")
            suffix = f"；原因: {reason}" if reason else ""
            print(
                f"  第 {record['page']} 页: {angle:+.2f}° / "
                f"{record.get('method', 'unknown')} / {record['action']}{suffix}"
            )
    return result
