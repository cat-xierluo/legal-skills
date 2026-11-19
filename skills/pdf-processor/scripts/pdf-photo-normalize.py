#!/usr/bin/env python3
"""Normalize photographed document pages into regular PDFs."""

import argparse
import json
from pathlib import Path

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


PAGE_SIZES_MM = {
    "a4": (210, 297),
    "letter": (215.9, 279.4),
}
DEFAULT_PAGE_SIZE = "a4"
DEFAULT_CONTRAST_STRENGTH = 0.7
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def load_photo(path: str | Path) -> Image.Image:
    """Load an image and bake its EXIF orientation into pixels."""
    source = Path(path)
    if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支持的拍照件格式: {source.suffix or '(无后缀)'}")
    with Image.open(source) as image:
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
    return best_points / scale


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


def _table_projection(preview: Image.Image) -> tuple[np.ndarray, tuple[int, int], dict]:
    """Rectify a trusted frame while retaining the full paper extent."""
    frame = _table_frame(preview)
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
    if max_tilt <= 0.15 or max_tilt > 5.0:
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

    offset = np.floor(projected.min(axis=0))
    width, height = (np.ceil(projected.max(axis=0)) - offset + 1).astype(int)
    matrix[:2] -= offset[:, None] * matrix[2]
    report["status"] = "applied"
    return matrix, (int(width), int(height)), report


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
    debug_image: str | Path | None = None,
) -> dict:
    """Run the complete photo-to-regular-PDF pipeline."""
    source_path = Path(input_path)
    target_path = Path(output_path)
    if source_path.resolve() == target_path.resolve():
        raise ValueError("输出文件不能覆盖原始拍照件")

    photo = load_photo(source_path)
    quad = detect_document_quad(photo)
    paper_matrix, paper_size, quad_meta = _paper_projection(photo.size, quad)
    preview_size = _contained_size(paper_size, (1600, 1600)) if max(paper_size) > 1600 else paper_size
    preview_matrix = _resize_matrix(paper_size, preview_size) @ paper_matrix
    preview = Image.fromarray(_warp_image(photo, preview_matrix, preview_size))

    if rotation == "auto":
        clockwise, rotation_reason = detect_auto_rotation(preview)
    else:
        clockwise = int(rotation)
        rotation_reason = "explicit"

    if quad_meta["quad_detected"]:
        table_matrix, refined_preview_size, table_report = _table_projection(preview)
    else:
        table_matrix, refined_preview_size = np.eye(3), preview_size
        table_report = {"status": "no_paper_quad"}
    corrected_size = tuple(
        round(refined * paper / preview_edge)
        for refined, paper, preview_edge in zip(refined_preview_size, paper_size, preview_size)
    )
    swaps_axes = clockwise in (90, 270)
    oriented_size = corrected_size[::-1] if swaps_axes else corrected_size
    final_size, resolved_page_size = resolve_page_size(oriented_size, page_size, dpi)
    content_size = _contained_size(oriented_size, final_size)
    render_size = content_size[::-1] if swaps_axes else content_size
    composed = _resize_matrix(refined_preview_size, render_size) @ table_matrix
    raster = _warp_image(photo, composed @ preview_matrix, render_size)
    oriented = _rotate_clockwise(Image.fromarray(raster), clockwise)

    enhanced = normalize_illumination(
        oriented,
        strength=illumination_strength,
        contrast_strength=contrast_strength,
    )
    if table_report["status"] == "applied":
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

    if debug_image is not None:
        debug_array = np.asarray(photo).copy()
        if quad is not None:
            cv2.polylines(
                debug_array,
                [np.round(quad).astype(np.int32)],
                True,
                (255, 0, 0),
                max(1, round(max(photo.size) / 600)),
            )
        Image.fromarray(debug_array).save(debug_image, quality=95)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    dimensions_mm = _paper_dimensions_mm(resolved_page_size, final_size)
    physical_dpi = (
        tuple(pixels * 25.4 / mm for pixels, mm in zip(final_size, dimensions_mm))
        if dimensions_mm else (dpi, dpi)
    )
    canvas.save(
        target_path,
        "PDF",
        dpi=physical_dpi,
        quality=jpeg_quality,
    )
    return {
        "input": str(source_path),
        "output": str(target_path),
        "exif_transposed_size": photo.size,
        "quad": quad_meta,
        "rotation_clockwise": clockwise,
        "rotation_reason": rotation_reason,
        "table_alignment": table_report,
        "illumination": {
            "strength": illumination_strength,
            "contrast_strength": contrast_strength,
            "before_shadow_score": _shadow_score(oriented),
            "after_shadow_score": _shadow_score(enhanced),
        },
        "page_size": resolved_page_size,
        "output_size": final_size,
        "content_size": content_size,
        "dpi": dpi,
    }


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
        help="默认 A4，按照片方向等比居中；auto 按纸面比例选尺寸；original 保留纸面比例",
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
    parser.add_argument("--debug-image", help="另存检测边框调试图")
    parser.add_argument("--report", help="以 JSON 保存处理报告")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.dpi <= 600:
        raise ValueError("输出 DPI 必须在 1-600")
    if not 1 <= args.jpeg_quality <= 100:
        raise ValueError("JPEG 质量必须在 1-100")
    if not 0 <= args.illumination_strength <= 1:
        raise ValueError("阴影归一化强度必须在 0-1")
    if not 0 <= args.contrast_strength <= 1:
        raise ValueError("对比度增强强度必须在 0-1")

    report = normalize_photo_pdf(
        args.input,
        args.output,
        dpi=args.dpi,
        jpeg_quality=args.jpeg_quality,
        page_size=args.page_size,
        rotation=args.rotate,
        illumination_strength=args.illumination_strength,
        contrast_strength=args.contrast_strength,
        debug_image=args.debug_image,
    )
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("拍照件规整完成")
    print(f"EXIF 转正尺寸: {report['exif_transposed_size'][0]}×{report['exif_transposed_size'][1]}")
    print(f"纸面四边检测: {'成功' if report['quad']['quad_detected'] else '失败，保留整幅图像'}")
    print(f"粗方向旋转: {report['rotation_clockwise']}°（{report['rotation_reason']}）")
    print(f"表框校正: {report['table_alignment']['status']}")
    print(
        "阴影块亮度离散: "
        f"{report['illumination']['before_shadow_score']:.2f} → "
        f"{report['illumination']['after_shadow_score']:.2f}"
    )
    print(f"页面策略: {report['page_size']}；输出尺寸: {report['output_size'][0]}×{report['output_size'][1]}")
    print(f"输出文件: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
