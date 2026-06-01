#!/usr/bin/env python3
"""Arrange images or PDF pages into a new PDF with N items per A4 page."""

from __future__ import annotations

import argparse
import io
import sys
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


def process(paths: list[str], output: str | None, per_page: int, margin: float, orientation: str, sort: str, dry_run: bool) -> int:
    load_deps()

    collected = collect_inputs(paths, sort)
    if not collected:
        print("No image or PDF files found.", file=sys.stderr)
        return 1

    print(f"Found {len(collected)} item(s)")

    # Convert all inputs to (page_obj, w, h) tuples
    items: list[tuple[Any, float, float]] = []
    for p in collected:
        if p.suffix.lower() == ".pdf":
            items.extend(pdf_to_page_readers(p))
        else:
            items.append(img_to_pdf_page(p))

    if not items:
        print("No valid pages to process.", file=sys.stderr)
        return 1

    # Auto per-page: portrait majority → 3/page, landscape majority → 1/page
    if per_page == 0:
        portrait_count = sum(1 for _, w, h in items if h > w)
        landscape_count = len(items) - portrait_count
        per_page = 3 if portrait_count >= landscape_count else 1
        print(f"Auto: 竖版{portrait_count}张、横版{landscape_count}张 → 每页{per_page}张")

    # Determine output path
    if output:
        out_path = Path(output).expanduser().resolve()
    else:
        first = collected[0]
        if len(collected) == 1 and first.is_dir():
            out_path = first / "output.pdf"
        else:
            out_path = first.parent / f"{first.stem}_编排.pdf"

    result = build_pdf(items, out_path, per_page, margin, orientation, dry_run)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Arrange images/PDF pages into a multi-per-page A4 PDF.")
    parser.add_argument("--input", "-i", nargs="+", required=True, help="Image files, PDF files, or directories")
    parser.add_argument("--output", "-o", help="Output PDF path (default: <first_input>_编排.pdf)")
    parser.add_argument("--per-page", "-n", type=int, default=0, help="Items per page: 1/2/3/4, or omit for auto (default: auto, 3 for portrait images, 2 for landscape)")
    parser.add_argument("--margin", "-m", type=float, default=25, help="Page margin in pt (default: 25)")
    parser.add_argument("--orientation", choices=["auto", "landscape", "portrait"], default="auto", help="Page orientation (default: auto)")
    parser.add_argument("--sort", choices=["name", "time", "none"], default="name", help="Sort order for directory inputs (default: name)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    if args.margin < 0:
        parser.error("--margin must be >= 0")
    if args.per_page not in (0, 1, 2, 3, 4):
        parser.error("--per-page must be 1, 2, 3, 4, or omit for auto")

    return process(args.input, args.output, args.per_page, args.margin, args.orientation, args.sort, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
