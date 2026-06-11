#!/usr/bin/env python3
"""Arrange images or PDF pages into a new PDF with N items per A4 page."""

from __future__ import annotations

import argparse
import io
import math
import shutil
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


def load_deps() -> None:
    try:
        import pypdf  # noqa: F401
        import fitz  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        print(f"Missing dependency: {exc}", file=sys.stderr)
        print("Install: python3 -m pip install -r scripts/requirements.txt", file=sys.stderr)
        raise SystemExit(1) from exc


# A4 sizes in points
A4_PORTRAIT = (595.0, 842.0)
A4_LANDSCAPE = (842.0, 595.0)
A4_RATIO = math.sqrt(2)  # height / width ≈ 1.414

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def collect_inputs(paths: list[str], sort: str) -> list[Path]:
    """Expand directories and filter to image/PDF files."""
    from PIL import Image as PILImage

    result: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if p.is_dir():
            for ext in IMAGE_EXTENSIONS:
                result.extend(p.glob(f"*{ext}"))
                result.extend(p.glob(f"*{ext.upper()}"))
        elif p.suffix.lower() in IMAGE_EXTENSIONS:
            result.append(p)
        elif p.suffix.lower() == ".pdf":
            result.append(p)
        else:
            print(f"Warning: skipping unsupported file: {p}", file=sys.stderr)

    if sort == "name":
        result.sort(key=lambda x: x.name)
    elif sort == "time":
        result.sort(key=lambda x: x.stat().st_mtime)

    return result


def compute_split_height(img_w: int, img_h: int, override: int | None) -> tuple[int, str]:
    """Compute the per-segment height in pixels.

    If override is given, use it directly. Otherwise, return (img_w * A4_RATIO)
    so that each cropped segment keeps the 1:√2 aspect ratio matching A4.
    Returns (height_px, source_label) where source_label is "explicit" or "a4_ratio".
    """
    if override is not None:
        if override <= 0:
            raise ValueError(f"--split-height must be a positive integer, got {override}")
        return int(override), "explicit"
    return int(round(img_w * A4_RATIO)), "a4_ratio"


def split_image(img_path: Path, split_height: int, tmp_dir: Path) -> list[Path]:
    """Split a single image into N segments of split_height pixels each.

    Short images (height <= split_height) are returned as-is (single element list).
    Output paths are inside tmp_dir; the caller is responsible for tmp_dir lifecycle.
    """
    from PIL import Image

    img = Image.open(img_path)
    w, h = img.size
    if h <= split_height:
        img.close()
        return [img_path]

    segments: list[Path] = []
    n_segments = math.ceil(h / split_height)
    stem = img_path.stem
    # Preserve original extension for the split files
    ext = img_path.suffix if img_path.suffix else ".png"
    for i in range(n_segments):
        top = i * split_height
        bottom = min(top + split_height, h)
        crop = img.crop((0, top, w, bottom))
        seg_path = tmp_dir / f"{stem}_{i + 1:03d}{ext}"
        crop.save(seg_path)
        segments.append(seg_path)
    img.close()
    return segments


def img_to_pdf_page(img_path: Path) -> tuple[Any, float, float]:
    """Convert an image file to a single-page PDF. Returns (page_object, width, height)."""
    import fitz
    from pypdf import PdfReader

    doc = fitz.open(str(img_path))
    img_page = doc[0]
    w, h = img_page.rect.width, img_page.rect.height

    pdf_doc = fitz.open()
    pdf_page = pdf_doc.new_page(width=w, height=h)
    pdf_page.insert_image(pdf_page.rect, filename=str(img_path))
    buf = io.BytesIO()
    pdf_doc.save(buf)
    pdf_doc.close()
    doc.close()
    buf.seek(0)

    reader = PdfReader(buf)
    page_obj = reader.pages[0]
    # Keep reader alive via page_obj attribute to prevent GC of BytesIO
    page_obj._reader_ref = reader  # type: ignore[attr-defined]
    page_obj._buf_ref = buf  # type: ignore[attr-defined]
    return page_obj, w, h


def pdf_to_page_readers(pdf_path: Path) -> list[tuple[Any, float, float]]:
    """Read each page of a PDF as a (reader, w, h) tuple."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        pages.append((page, w, h))
    return pages


def img_to_vertical_page(img_path: Path, page_w_pt: float, margin_pt: float) -> tuple[Any, float, float]:
    """Build a single-page PDF sized as page_w_pt wide × image-aspect-scaled tall.

    Treats image pixels as PDF points (1 px = 1 pt) — typical phone screenshot
    is 1080×5000 px, which becomes a 1080×5000 pt page when fully scaled. The image
    is scaled to fill the usable width (page_w_pt - 2*margin_pt), and the page
    height is the scaled image height + 2*margin_pt. Force portrait orientation
    (height is always >= usable_w because the source is a long screenshot).
    """
    from PIL import Image as PILImage
    import fitz
    from pypdf import PdfReader

    pil_img = PILImage.open(img_path)
    img_w, img_h = pil_img.size
    pil_img.close()

    usable_w = page_w_pt - 2 * margin_pt
    if usable_w <= 0:
        raise ValueError(f"margin={margin_pt} too large for page width={page_w_pt}")
    scale = usable_w / img_w
    scaled_h = img_h * scale
    page_h = scaled_h + 2 * margin_pt

    doc = fitz.open()
    page = doc.new_page(width=page_w_pt, height=page_h)
    img_rect = fitz.Rect(margin_pt, margin_pt, margin_pt + usable_w, margin_pt + scaled_h)
    page.insert_image(img_rect, filename=str(img_path))

    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    buf.seek(0)

    reader = PdfReader(buf)
    page_obj = reader.pages[0]
    page_obj._reader_ref = reader  # type: ignore[attr-defined]
    page_obj._buf_ref = buf  # type: ignore[attr-defined]
    return page_obj, page_w_pt, page_h


def build_pdf_vertical(
    image_paths: list[Path],
    output_path: Path,
    margin: float,
    dry_run: bool,
) -> dict[str, Any]:
    """Vertical mode: one image per page, page height follows image aspect ratio.

    image_paths: list of image file paths. PDF inputs are not supported in vertical
    mode (PDFs already have natural page boundaries — caller should split PDFs to
    images first if they want each PDF page to be its own long page).
    """
    from pypdf import PdfWriter

    writer = PdfWriter()
    page_w = A4_PORTRAIT[0]
    total = len(image_paths)
    output_pages = 0
    total_page_h = 0.0

    for img_path in image_paths:
        page_obj, pw, ph = img_to_vertical_page(img_path, page_w, margin)
        writer.add_page(page_obj)
        output_pages += 1
        total_page_h += ph

    if dry_run:
        avg_h = total_page_h / output_pages if output_pages else 0
        print(f"Dry run (vertical): {total} items → {output_pages} pages")
        print(f"  Page width: {page_w}pt, avg height: {avg_h:.0f}pt")
        return {"total_items": total, "output_pages": output_pages, "dry_run": True}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        writer.write(f)

    print(f"✅ {total}张 → {output_pages}页PDF（vertical 模式，每页一张，页面高度自适应）")
    print(f"   {output_path}")
    return {"total_items": total, "output_pages": output_pages, "output": str(output_path)}


def compute_grid(per_page: int, page_size: tuple[float, float], margin: float) -> dict[str, Any]:
    """Compute cell layout for given per-page count and page size."""
    a4_w, a4_h = page_size

    if per_page == 1:
        return {"cols": 1, "rows": 1, "cell_w": a4_w - 2 * margin, "cell_h": a4_h - 2 * margin}

    # For per_page >= 2, use columns layout
    cols = per_page
    gap = margin
    cell_w = (a4_w - (cols + 1) * gap) / cols
    cell_h = a4_h - 2 * margin

    return {"cols": cols, "gap": gap, "cell_w": cell_w, "cell_h": cell_h}


def pick_page_size(items: list[tuple[Any, float, float]], per_page: int, orientation: str) -> tuple[float, float]:
    """Determine output page size based on content orientation."""
    if orientation == "landscape":
        return A4_LANDSCAPE
    if orientation == "portrait":
        return A4_PORTRAIT

    # auto: for per_page >= 2, default landscape; for 1, match content majority
    if per_page >= 2:
        return A4_LANDSCAPE

    landscape_count = sum(1 for _, w, h in items if w > h)
    portrait_count = len(items) - landscape_count
    return A4_LANDSCAPE if landscape_count > portrait_count else A4_PORTRAIT


def build_pdf(
    items: list[tuple[Any, float, float]],
    output_path: Path,
    per_page: int,
    margin: float,
    orientation: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Build the output PDF with N items per page."""
    from pypdf import PdfWriter, Transformation

    writer = PdfWriter()
    total = len(items)
    output_pages = 0
    stats: dict[str, int] = {"landscape": 0, "portrait": 0}

    for start in range(0, total, per_page):
        chunk = items[start:start + per_page]

        # per-page=1 且 orientation=auto 时，每页独立判断横竖
        if per_page == 1 and orientation == "auto":
            _, img_w, img_h = chunk[0]
            if img_w > img_h:
                cur_page_size = A4_LANDSCAPE
            else:
                cur_page_size = A4_PORTRAIT
        else:
            cur_page_size = pick_page_size(items, per_page, orientation)

        grid = compute_grid(per_page, cur_page_size, margin)
        a4_w, a4_h = cur_page_size
        orient_label = "横版" if a4_w > a4_h else "竖版"
        stats[orient_label] = stats.get(orient_label, 0) + 1

        new_page = writer.add_blank_page(width=a4_w, height=a4_h)

        for col_idx, (page_obj, img_w, img_h) in enumerate(chunk):
            cell_w = grid["cell_w"]
            cell_h = grid["cell_h"]
            gap = grid.get("gap", margin)

            scale = min(cell_w / img_w, cell_h / img_h)
            scaled_w = img_w * scale
            scaled_h = img_h * scale

            tx = gap + col_idx * (cell_w + gap) + (cell_w - scaled_w) / 2
            ty = margin + (cell_h - scaled_h) / 2

            op = Transformation().scale(scale, scale).translate(tx, ty)
            new_page.merge_transformed_page(page_obj, op)

        output_pages += 1

    if dry_run:
        print(f"Dry run: {total} items → {output_pages} pages ({per_page}/page)")
        for orient, count in stats.items():
            if count:
                print(f"  A4 {orient}: {count} 页")
        return {"total_items": total, "output_pages": output_pages, "dry_run": True}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        writer.write(f)

    orient_summary = "、".join(f"{k}{v}页" for k, v in stats.items() if v)
    print(f"✅ {total}张 → {output_pages}页PDF（每页{per_page}张，{orient_summary}，margin={margin}pt）")
    print(f"   {output_path}")
    return {"total_items": total, "output_pages": output_pages, "output": str(output_path)}


def process(
    paths: list[str],
    output: str | None,
    per_page: int,
    margin: float,
    orientation: str,
    sort: str,
    dry_run: bool,
    mode: str = "nup",
    split: bool = False,
    split_height: int | None = None,
) -> int:
    load_deps()

    collected = collect_inputs(paths, sort)
    if not collected:
        print("No image or PDF files found.", file=sys.stderr)
        return 1

    print(f"Found {len(collected)} item(s)")

    # Determine output path (used by both modes)
    if output:
        out_path = Path(output).expanduser().resolve()
    else:
        first = collected[0]
        if len(collected) == 1 and first.is_dir():
            out_path = first / "output.pdf"
        else:
            out_path = first.parent / f"{first.stem}_编排.pdf"

    # --- Vertical mode (--mode vertical) ---
    if mode == "vertical":
        if split or split_height is not None:
            print("⚠️ vertical 模式不支持切割，--split / --split-height 被忽略")

        image_paths = [p for p in collected if p.suffix.lower() in IMAGE_EXTENSIONS]
        pdf_paths = [p for p in collected if p.suffix.lower() == ".pdf"]
        if pdf_paths:
            print(
                f"⚠️ vertical 模式不处理 PDF 输入（{len(pdf_paths)} 个 PDF 已跳过）："
                "PDF 自带分页，如需长页请先转图片"
            )
        if not image_paths:
            print("No image files to process in vertical mode.", file=sys.stderr)
            return 1

        build_pdf_vertical(image_paths, out_path, margin, dry_run)
        return 0

    # --- N-up mode (default) ---

    split_tmp_dir: Path | None = None
    processed_paths: list[Path] = list(collected)

    if split:
        try:
            split_tmp_dir = Path(tempfile.mkdtemp(prefix="img2pdf-splits-"))
        except OSError as exc:
            print(f"Failed to create temp dir: {exc}", file=sys.stderr)
            return 1

        from PIL import Image as PILImage

        new_paths: list[Path] = []
        for p in collected:
            if p.suffix.lower() == ".pdf":
                new_paths.append(p)
                continue
            try:
                with PILImage.open(p) as probe:
                    img_w, img_h = probe.size
            except Exception as exc:
                print(f"Warning: 跳过 {p}（{exc}）", file=sys.stderr)
                continue

            try:
                actual_h, source = compute_split_height(img_w, img_h, split_height)
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                if split_tmp_dir is not None:
                    shutil.rmtree(split_tmp_dir, ignore_errors=True)
                return 1

            if img_h <= actual_h:
                print(f"图片 {p.name} 高度 {img_h}px，未触发切割")
                new_paths.append(p)
                continue

            segments = split_image(p, actual_h, split_tmp_dir)
            print(
                f"  切割 {p.name} ({img_w}×{img_h}px) → {len(segments)} 段 "
                f"({source} 段高={actual_h}px)"
            )
            new_paths.extend(segments)

        if len(collected) > 0 and len(new_paths) > len(collected) * 5:
            print(
                f"⚠️ 切割后段数 {len(new_paths)} 远超原图数 {len(collected)} × 5，"
                "建议调大 --split-height"
            )

        processed_paths = new_paths

    try:
        items: list[tuple[Any, float, float]] = []
        for p in processed_paths:
            if p.suffix.lower() == ".pdf":
                items.extend(pdf_to_page_readers(p))
            else:
                items.append(img_to_pdf_page(p))

        if not items:
            print("No valid pages to process.", file=sys.stderr)
            return 1

        if per_page == 0:
            portrait_count = sum(1 for _, w, h in items if h > w)
            landscape_count = len(items) - portrait_count
            per_page = 3 if portrait_count >= landscape_count else 1
            print(f"Auto: 竖版{portrait_count}张、横版{landscape_count}张 → 每页{per_page}张")

        build_pdf(items, out_path, per_page, margin, orientation, dry_run)
        return 0
    finally:
        if split_tmp_dir is not None and split_tmp_dir.exists():
            shutil.rmtree(split_tmp_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Arrange images/PDF pages into a multi-per-page A4 PDF, or render a single long screenshot as one tall PDF page."
    )
    parser.add_argument("--input", "-i", nargs="+", required=True, help="Image files, PDF files, or directories")
    parser.add_argument("--output", "-o", help="Output PDF path (default: <first_input>_编排.pdf)")
    parser.add_argument("--mode", choices=["nup", "vertical"], default="nup", help="Layout mode: nup (N items/page) or vertical (one image/page, page height follows image aspect). Default: nup")
    parser.add_argument("--per-page", "-n", type=int, default=0, help="Items per page in nup mode: 1/2/3/4, or omit for auto (default: auto, 3 for portrait images, 1 for landscape)")
    parser.add_argument("--margin", "-m", type=float, default=25, help="Page margin in pt (default: 25)")
    parser.add_argument("--orientation", choices=["auto", "landscape", "portrait"], default="auto", help="Page orientation in nup mode (default: auto)")
    parser.add_argument("--sort", choices=["name", "time", "none"], default="name", help="Sort order for directory inputs (default: name)")
    parser.add_argument("--split", action="store_true", help="Split long screenshots into segments before layout (nup mode only)")
    parser.add_argument("--split-height", type=int, default=None, help="Override split segment height in px (default: A4 ratio = img_w × √2). Ignored in vertical mode.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    if args.margin < 0:
        parser.error("--margin must be >= 0")
    if args.per_page not in (0, 1, 2, 3, 4):
        parser.error("--per-page must be 1, 2, 3, 4, or omit for auto")
    if args.split_height is not None and args.split_height <= 0:
        parser.error("--split-height must be a positive integer")

    return process(
        args.input,
        args.output,
        args.per_page,
        args.margin,
        args.orientation,
        args.sort,
        args.dry_run,
        mode=args.mode,
        split=args.split,
        split_height=args.split_height,
    )


if __name__ == "__main__":
    raise SystemExit(main())
