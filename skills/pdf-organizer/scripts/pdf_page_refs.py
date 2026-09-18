#!/usr/bin/env python3
"""页引用模型：把 manifest 的拆分 / 复制 / 合并统一编译为「文件 + 页码」引用集合。

设计要点：
- 所有输出文书 = 有序页引用列表 [(file, page)]，物理 PDF 在执行前一个字节不动；
- 拆 / 合 / 删 / 跨源拼合都只是引用运算，manifest 即引用表，天然可 diff、可审计、可回滚；
- 执行器只消费引用表；整文件单源段保留字节级复制快路径；
- 覆盖审计报告每个源文件「总页 / 被引用 / 孤儿页 / 重复引用页」，让拆分完整性可验证。

本模块不依赖 pypdf（读取页数与写 PDF 按需延迟加载）。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


# ---------- 页码解析 ----------

def parse_pages_spec(spec: str, total_pages: int | None = None) -> list[int]:
    """把 "1-3,5" 形式的页码描述展开为升序无关的显式页码列表。"""
    pages: list[int] = []
    for raw_part in str(spec).split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            start_raw, end_raw = part.split("-", 1)
            start = int(start_raw.strip())
            end = int(end_raw.strip())
            if start > end:
                raise ValueError(f"Invalid descending page range: {part}")
            pages.extend(range(start, end + 1))
        else:
            pages.append(int(part))
    if not pages:
        raise ValueError("Page range is empty.")
    if any(page < 1 for page in pages):
        raise ValueError("Pages are 1-based and must be greater than 0.")
    if total_pages is not None:
        too_large = [page for page in pages if page > total_pages]
        if too_large:
            raise ValueError(f"Page out of bounds: {too_large[0]} > {total_pages}")
    return pages


# ---------- 页数缓存 ----------

class PageCountCache:
    """按路径缓存 PDF 页数，避免重复打开同一文件。"""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def get(self, path: Path) -> int:
        key = str(path)
        if key not in self._counts:
            from pypdf import PdfReader

            self._counts[key] = len(PdfReader(str(path)).pages)
        return self._counts[key]


# ---------- 段编译：manifest segment → 有序页引用 ----------

class RefsCompileError(ValueError):
    """段无法编译为页引用（字段缺失 / 文件不存在 / 页码越界）。"""


class SegmentRefs:
    """一个输出文书的页引用集合及其来源形态。"""

    def __init__(self, refs: list[tuple[Path, int]], kind: str) -> None:
        self.refs = refs
        self.kind = kind  # refs / split / copy / merge

    @property
    def files(self) -> list[Path]:
        seen: list[Path] = []
        for path, _ in self.refs:
            if path not in seen:
                seen.append(path)
        return seen

    @property
    def is_whole_single_file(self) -> bool:
        """引用是否恰好覆盖唯一源文件的全部页（字节级复制快路径条件）。"""
        files = self.files
        if len(files) != 1 or not self.refs:
            return False
        path = files[0]
        pages = [page for p, page in self.refs if p == path]
        return pages == list(range(1, len(pages) + 1)) and self.kind == "copy"


def _resolve_file(value: str | None, base_dir: Path) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _expand_ref_group(
    group: dict[str, Any],
    base_dir: Path,
    counts: PageCountCache,
) -> list[tuple[Path, int]]:
    file_path = _resolve_file(group.get("file") or group.get("input_file"), base_dir)
    if file_path is None:
        raise RefsCompileError("refs/source_items entry missing 'file'.")
    if not file_path.exists():
        raise RefsCompileError(f"Input PDF does not exist: {file_path}")
    total = counts.get(file_path)
    pages_spec = group.get("pages")
    pages = (
        parse_pages_spec(str(pages_spec), total)
        if pages_spec not in (None, "")
        else list(range(1, total + 1))
    )
    return [(file_path, page) for page in pages]


def compile_segment_refs(
    segment: dict[str, Any],
    *,
    base_dir: Path,
    source_pdf: Path | None,
    counts: PageCountCache,
) -> SegmentRefs:
    """
    把 manifest segment 的四种形态统一编译为有序页引用。

    优先级与既有执行器一致：refs → source_items/input_files → input_file → pages。
    """
    raw_refs = segment.get("refs")
    if raw_refs is not None:
        if not isinstance(raw_refs, list) or not raw_refs:
            raise RefsCompileError("refs must be a non-empty array of {file, pages?}.")
        refs: list[tuple[Path, int]] = []
        for entry in raw_refs:
            group = {"file": entry} if isinstance(entry, str) else dict(entry)
            refs.extend(_expand_ref_group(group, base_dir, counts))
        return SegmentRefs(refs, "refs")

    raw_items = None
    for key in ("source_items", "input_files"):
        if segment.get(key) is not None:
            raw_items = segment[key]
            break
    if raw_items is not None:
        if not isinstance(raw_items, list) or not raw_items:
            raise RefsCompileError("source_items/input_files must be a non-empty array.")
        refs = []
        for item in raw_items:
            group = {"file": item} if isinstance(item, str) else dict(item)
            refs.extend(_expand_ref_group(group, base_dir, counts))
        files = {path for path, _ in refs}
        if len(files) > 1:
            return SegmentRefs(refs, "merge")
        # 单源：整份覆盖按 copy，部分页提取按 split
        total = counts.get(next(iter(files)))
        covers_all = [page for _, page in refs] == list(range(1, total + 1))
        return SegmentRefs(refs, "copy" if covers_all else "split")

    input_file = _resolve_file(segment.get("input_file"), base_dir)
    if input_file is not None:
        if not input_file.exists():
            raise RefsCompileError(f"Input PDF does not exist: {input_file}")
        total = counts.get(input_file)
        return SegmentRefs([(input_file, p) for p in range(1, total + 1)], "copy")

    pages_spec = segment.get("pages")
    if pages_spec:
        if source_pdf is None:
            raise RefsCompileError("source_pdf is required when segment uses pages.")
        if not Path(source_pdf).exists():
            raise RefsCompileError(f"Source PDF does not exist: {source_pdf}")
        total = counts.get(Path(source_pdf))
        pages = parse_pages_spec(str(pages_spec), total)
        return SegmentRefs([(Path(source_pdf), p) for p in pages], "split")

    raise RefsCompileError("Segment must contain refs, source_items/input_files, input_file, or pages.")


# ---------- 引用标签 ----------

def refs_pages_label(refs: list[tuple[Path, int]]) -> str:
    """人读标签：单源 `P1-3,P5`，跨源 `甲.pdf P1-2 + 乙.pdf P3`。"""
    by_file: dict[Path, list[int]] = {}
    for path, page in refs:
        by_file.setdefault(path, []).append(page)
    single = len(by_file) == 1
    parts: list[str] = []
    for path, pages in by_file.items():
        ranges: list[str] = []
        start = prev = pages[0]
        for page in pages[1:]:
            if page == prev + 1:
                prev = page
                continue
            ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
            start = prev = page
        ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
        prefix = "" if single else f"{path.name} "
        parts.append(f"{prefix}P{','.join(ranges)}")
    return " + ".join(parts)


def refs_to_compact(refs: list[tuple[Path, int]]) -> list[dict[str, Any]]:
    """归一化引用的 JSON 形态：[{file, pages}]（供 resolved/handoff 记录溯源）。"""
    by_file: dict[Path, list[int]] = {}
    for path, page in refs:
        by_file.setdefault(path, []).append(page)
    return [{"file": str(path), "pages": pages} for path, pages in by_file.items()]


# ---------- 覆盖审计 ----------

def audit_page_coverage(
    segments_refs: dict[str, list[tuple[Path, int]]],
    counts: PageCountCache,
) -> dict[str, Any]:
    """
    审计页覆盖：每个源文件报告总页数、被引用页、孤儿页（未被任何段引用）
    与重复引用页（被多个段引用）。孤儿/重复是「提示」不是错误——
    删页与有意复用都是合法操作，但拆分场景下通常意味着遗漏或多切。
    """
    owners: dict[tuple[Path, int], list[str]] = {}
    for seg_id, refs in segments_refs.items():
        for ref in refs:
            owners.setdefault(ref, []).append(seg_id)

    per_file: list[dict[str, Any]] = []
    files = sorted({path for path, _ in owners})
    for path in files:
        try:
            total = counts.get(path)
        except Exception:  # noqa: BLE001
            total = None
        referenced = sorted({page for p, page in owners if p == path})
        orphans = ([p for p in range(1, total + 1) if p not in set(referenced)]
                   if total is not None else [])
        duplicated = sorted(
            page for p, page in owners if p == path and len(owners[(p, page)]) > 1
        )
        per_file.append(
            {
                "file": str(path),
                "total_pages": total,
                "referenced_pages": len(referenced),
                "orphan_pages": orphans,
                "duplicated_pages": [
                    {"page": page, "segments": owners[(path, page)]} for page in duplicated
                ],
            }
        )

    orphan_count = sum(len(f["orphan_pages"]) for f in per_file)
    duplicate_count = sum(len(f["duplicated_pages"]) for f in per_file)
    return {
        "per_file": per_file,
        "orphan_count": orphan_count,
        "duplicate_count": duplicate_count,
        "clean": orphan_count == 0 and duplicate_count == 0,
    }


def format_coverage_report(coverage: dict[str, Any]) -> list[str]:
    lines = [
        "| Source file | Pages | Referenced | Orphan pages | Duplicated pages |",
        "|-------------|-------|------------|--------------|------------------|",
    ]
    for item in coverage["per_file"]:
        orphans = (
            ",".join(str(p) for p in item["orphan_pages"][:12])
            + ("…" if len(item["orphan_pages"]) > 12 else "")
        ) or "-"
        dup = (
            "; ".join(f"P{d['page']}→{','.join(d['segments'])}" for d in item["duplicated_pages"][:6])
            + ("…" if len(item["duplicated_pages"]) > 6 else "")
        ) or "-"
        lines.append(
            f"| `{Path(item['file']).name}` | {item['total_pages']} | "
            f"{item['referenced_pages']} | {orphans} | {dup} |"
        )
    return lines


# ---------- 统一执行器 ----------

def write_refs_pdf(
    refs: list[tuple[Path, int]],
    output_file: Path,
    *,
    dry_run: bool = False,
) -> str:
    """按引用顺序写出 PDF；返回来源标签。整文件单源段建议先用快路径复制。"""
    if dry_run:
        return refs_pages_label(refs)
    from pypdf import PdfReader, PdfWriter

    readers: dict[str, PdfReader] = {}
    writer = PdfWriter()
    for path, page in refs:
        key = str(path)
        if key not in readers:
            readers[key] = PdfReader(key)
        reader = readers[key]
        if page > len(reader.pages):
            raise ValueError(f"Page out of bounds: {path} P{page} > {len(reader.pages)}")
        writer.add_page(reader.pages[page - 1])
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("wb") as f:
        writer.write(f)
    return refs_pages_label(refs)


def copy_refs_whole_file(refs: list[tuple[Path, int]], output_file: Path, *, dry_run: bool = False) -> None:
    """整文件单源段的字节级复制快路径（保留原文件全部字节与元数据）。"""
    if dry_run:
        return
    assert len({p for p, _ in refs}) == 1
    source = refs[0][0]
    output_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output_file)
