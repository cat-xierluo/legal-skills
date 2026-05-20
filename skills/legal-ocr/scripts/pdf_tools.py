from __future__ import annotations

from pathlib import Path

try:
    import pypdfium2 as pdfium
except ImportError as error:
    print("缺少依赖: pypdfium2")
    print("请使用: uv run scripts/convert.py <input>")
    print("或安装: pip install pypdfium2")
    raise SystemExit(1) from error


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
