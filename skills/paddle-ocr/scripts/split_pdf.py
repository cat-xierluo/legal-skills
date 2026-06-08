#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "pypdfium2>=4.30.0",
# ]
# ///

"""PDF 页码提取与自动分批工具。"""

from __future__ import annotations

import argparse
from pathlib import Path

import pypdfium2 as pdfium


def get_pdf_page_count(input_path: Path) -> int:
    document = pdfium.PdfDocument(str(input_path))
    try:
        return len(document)
    finally:
        document.close()


def parse_pages_spec(pages_spec: str, total_pages: int) -> list[int]:
    if not pages_spec or not pages_spec.strip():
        raise ValueError("页码范围不能为空")

    selected: list[int] = []
    seen: set[int] = set()

    def add_page(page_number: int) -> None:
        if page_number < 1 or page_number > total_pages:
            raise ValueError(f"页码超出范围：{page_number}，有效范围是 1-{total_pages}")
        index = page_number - 1
        if index not in seen:
            seen.add(index)
            selected.append(index)

    for token in [part.strip() for part in pages_spec.split(",") if part.strip()]:
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            if not start_text.isdigit() or not end_text.isdigit():
                raise ValueError(f"非法页码范围：{token}")
            start_page, end_page = int(start_text), int(end_text)
            if start_page > end_page:
                raise ValueError(f"起始页不能大于结束页：{token}")
            for page_number in range(start_page, end_page + 1):
                add_page(page_number)
        else:
            if not token.isdigit():
                raise ValueError(f"非法页码：{token}")
            add_page(int(token))

    if not selected:
        raise ValueError("没有解析出有效页码")
    return selected


def format_pages_compact(page_indices: list[int]) -> str:
    if not page_indices:
        return "none"

    pages = sorted(index + 1 for index in page_indices)
    ranges: list[str] = []
    start = prev = pages[0]

    for page in pages[1:]:
        if page == prev + 1:
            prev = page
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = page

    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(ranges)


def extract_pages_to_pdf(input_path: Path, output_path: Path, page_indices: list[int]) -> None:
    source_pdf = pdfium.PdfDocument(str(input_path))
    try:
        output_pdf = pdfium.PdfDocument.new()
        try:
            output_pdf.import_pages(source_pdf, page_indices)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_pdf.save(str(output_path))
        finally:
            output_pdf.close()
    finally:
        source_pdf.close()


def split_pdf_by_batch_size(
    *,
    input_path: Path,
    output_dir: Path,
    batch_size: int,
    page_indices: list[int] | None = None,
) -> list[dict[str, Path | str]]:
    total_pages = get_pdf_page_count(input_path)
    selected_pages = page_indices or list(range(total_pages))
    if batch_size <= 0:
        raise ValueError("batch_size 必须大于 0")

    output_dir.mkdir(parents=True, exist_ok=True)
    batches: list[dict[str, Path | str]] = []

    for batch_index in range(0, len(selected_pages), batch_size):
        chunk = selected_pages[batch_index : batch_index + batch_size]
        label = format_pages_compact(chunk)
        filename = f"batch_{batch_index // batch_size + 1:03d}_{label.replace(',', '_')}.pdf"
        output_path = output_dir / filename
        extract_pages_to_pdf(input_path, output_path, chunk)
        batches.append({"label": label, "path": output_path})

    return batches


def main() -> int:
    parser = argparse.ArgumentParser(description="按页码范围提取 PDF")
    parser.add_argument("input_pdf", help="输入 PDF")
    parser.add_argument("output_pdf", help="输出 PDF")
    parser.add_argument("--pages", required=True, help='页码范围，例如 "1-5,8,10-12"')
    args = parser.parse_args()

    input_path = Path(args.input_pdf).expanduser().resolve()
    output_path = Path(args.output_pdf).expanduser().resolve()

    if not input_path.exists():
        print(f"错误：文件不存在：{input_path}")
        return 1
    if input_path.suffix.lower() != ".pdf":
        print(f"错误：输入必须是 PDF：{input_path}")
        return 1
    if output_path.suffix.lower() != ".pdf":
        print(f"错误：输出必须是 PDF：{output_path}")
        return 1

    total_pages = get_pdf_page_count(input_path)
    page_indices = parse_pages_spec(args.pages, total_pages)
    extract_pages_to_pdf(input_path, output_path, page_indices)

    print(f"已生成：{output_path}")
    print(f"原始总页数：{total_pages}")
    print(f"提取页码：{format_pages_compact(page_indices)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
