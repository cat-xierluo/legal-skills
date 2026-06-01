#!/usr/bin/env python3
"""Organize legal PDF documents according to a manifest."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


INVALID_FILENAME_CHARS = r'<>:"/\\|?*'
SKILL_DIR = Path(__file__).resolve().parent.parent
ARCHIVE_ROOT = SKILL_DIR / "archive"
SPECIFIC_TITLE_PATTERN = re.compile(
    r"(专项法律服务合同|委托代理合同|授权委托书|律师事务所函|民事起诉状|起诉状|"
    r"证据目录|答辩状|申请书|告知书|通知书|裁定书|判决书|调解书|决定书)"
)
GENERIC_TITLE_PATTERN = re.compile(r"(合同|协议|函)$")
DATE_PATTERN = re.compile(r"(?:19|20)\d{2}\s*[年./-]\s*\d{1,2}\s*[月./-]\s*\d{1,2}\s*日?")
PAGE_TOTAL_PATTERN = re.compile(r"第\s*(\d{1,3})\s*页\s*共\s*(\d{1,3})\s*页")
SLASH_PAGE_PATTERN = re.compile(r"(?<!\d)(\d{1,3})\s*/\s*(\d{1,3})(?!\d)")
COMPANY_PATTERN = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9（）()]{2,30}(?:公司|律所|事务所|委员会|法院|检察院))")


def load_pypdf():
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        print("Missing dependency: pypdf", file=sys.stderr)
        print("Install it with: python3 -m pip install -r scripts/requirements.txt", file=sys.stderr)
        raise SystemExit(1)
    return PdfReader, PdfWriter


def read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Manifest root must be a JSON object.")
    return data


def resolve_path(value: str | None, base_dir: Path) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def parse_pages(spec: str, total_pages: int | None = None) -> list[int]:
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


def sanitize_filename(name: str, fallback: str) -> str:
    stem = str(name or "").strip()
    if not stem:
        stem = fallback
    stem = stem.replace("\n", " ").replace("\r", " ")
    stem = stem.replace("_", " ")
    for char in INVALID_FILENAME_CHARS:
        stem = stem.replace(char, " ")
    stem = re.sub(r"\s+", " ", stem)
    stem = stem.strip(" ._")
    if not stem:
        stem = fallback
    if not stem.lower().endswith(".pdf"):
        stem += ".pdf"
    if len(stem) > 140:
        suffix = ".pdf"
        stem = stem[:-len(suffix)]
        stem = stem[: 140 - len(suffix)].rstrip(" ._") + suffix
    return stem


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} {counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def safe_name(name: str, fallback: str = "run") -> str:
    value = sanitize_filename(name, fallback)
    if value.lower().endswith(".pdf"):
        value = value[:-4]
    return value.strip(" ._") or fallback


def build_archive_subdir(archive_root: Path, source_pdf: Path | None, output_dir: Path, manifest_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if source_pdf:
        base_name = source_pdf.stem
    elif output_dir:
        base_name = output_dir.name
    else:
        base_name = manifest_path.stem
    base_name = safe_name(base_name)
    candidate = archive_root / f"{stamp}_{base_name}"
    index = 1
    while candidate.exists():
        candidate = archive_root / f"{stamp}_{base_name}_{index}"
        index += 1
    return candidate


def segment_filename(segment: dict[str, Any], index: int) -> str:
    fallback_title = segment.get("title") or segment.get("document_type") or f"segment_{index:02d}"
    fallback = str(fallback_title)
    raw = segment.get("filename") or segment.get("suggested_filename") or fallback
    return sanitize_filename(str(raw), sanitize_filename(fallback, f"segment_{index:02d}"))


def normalize_angle(angle: Any) -> int:
    try:
        value = int(angle)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid rotation angle: {angle}") from exc
    value %= 360
    if value not in {0, 90, 180, 270}:
        raise ValueError("Rotation angle must be one of 0, 90, 180, 270.")
    return value


def sample_page_indexes(total_pages: int, max_pages: int) -> list[int]:
    if total_pages <= 0 or max_pages <= 0:
        return []
    if total_pages <= max_pages:
        return list(range(total_pages))

    candidates = [0, 1, 2, total_pages // 2, total_pages - 1]
    indexes: list[int] = []
    for candidate in candidates:
        if 0 <= candidate < total_pages and candidate not in indexes:
            indexes.append(candidate)
        if len(indexes) >= max_pages:
            return indexes

    for candidate in range(total_pages):
        if candidate not in indexes:
            indexes.append(candidate)
        if len(indexes) >= max_pages:
            break
    return indexes


def check_pdf_text_layer(pdf_path: Path, max_pages: int = 5, min_chars: int = 20) -> dict[str, Any]:
    PdfReader, _ = load_pypdf()
    info: dict[str, Any] = {
        "file": str(pdf_path),
        "exists": pdf_path.exists(),
        "page_count": 0,
        "checked_pages": [],
        "text_chars": 0,
        "has_text_layer": False,
        "status": "missing",
    }
    if not pdf_path.exists():
        info["status"] = "error"
        info["error"] = "file does not exist"
        return info

    try:
        reader = PdfReader(str(pdf_path))
        page_count = len(reader.pages)
        info["page_count"] = page_count
        checked_indexes = sample_page_indexes(page_count, max_pages)
        info["checked_pages"] = [index + 1 for index in checked_indexes]

        text_chars = 0
        for index in checked_indexes:
            try:
                text = reader.pages[index].extract_text() or ""
            except Exception as exc:  # noqa: BLE001
                info["status"] = "error"
                info["error"] = f"page {index + 1}: {exc}"
                return info
            text_chars += len(re.sub(r"\s+", "", text))

        info["text_chars"] = text_chars
        info["has_text_layer"] = text_chars >= min_chars
        info["status"] = "ok" if info["has_text_layer"] else "missing"
        return info
    except Exception as exc:  # noqa: BLE001
        info["status"] = "error"
        info["error"] = str(exc)
        return info


def format_text_layer_check(results: list[dict[str, Any]], mode: str) -> list[str]:
    lines = [
        f"- Mode: {mode}",
        "",
        "| PDF | Pages | Checked pages | Text chars | Result |",
        "|-----|-------|---------------|------------|--------|",
    ]
    if not results:
        lines.append("| 未检测 | 0 |  | 0 | off |")
        return lines

    for result in results:
        path = Path(str(result.get("file", "")))
        checked_pages = ",".join(str(page) for page in result.get("checked_pages", []))
        status = str(result.get("status") or "")
        if status == "ok":
            label = "ok"
        elif status == "missing":
            label = "missing text layer"
        else:
            label = f"error: {result.get('error', '')}"
        lines.append(
            f"| `{path.name}` | {result.get('page_count', 0)} | {checked_pages} | "
            f"{result.get('text_chars', 0)} | {label} |"
        )
    return lines


def text_layer_failures(results: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    for result in results:
        if result.get("status") == "ok":
            continue
        path = result.get("file")
        if result.get("status") == "missing":
            failures.append(f"{path}: no searchable text layer detected")
        else:
            failures.append(f"{path}: text layer check failed: {result.get('error', '')}")
    return failures


def clean_extracted_text(text: str) -> str:
    value = (text or "").replace("\u3000", " ")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def significant_lines(text: str, limit: int = 12) -> list[str]:
    lines: list[str] = []
    for raw_line in clean_extracted_text(text).splitlines():
        line = raw_line.strip(" \t-—")
        if not line:
            continue
        line = re.sub(r"\s+", " ", line)
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def detect_page_label(text: str) -> dict[str, int] | None:
    compact = compact_text(text)
    match = PAGE_TOTAL_PATTERN.search(compact)
    if not match:
        match = SLASH_PAGE_PATTERN.search(compact)
    if not match:
        return None
    current = int(match.group(1))
    total = int(match.group(2))
    if current <= 0 or total <= 0 or current > total or total > 300:
        return None
    return {"current": current, "total": total}


def detect_title(lines: list[str]) -> str | None:
    for line in lines:
        compact = compact_text(line)
        if len(compact) > 80:
            continue
        if "PowerOfAttorney" in compact or "授权委托书" in compact:
            return "授权委托书"
        match = SPECIFIC_TITLE_PATTERN.search(compact)
        if match:
            value = match.group(1)
            if value == "律师事务所函":
                return value
            if value == "民事起诉状" and "侵害著作权" in compact:
                return "民事起诉状（侵害著作权及邻接权纠纷）"
            return value
        if len(compact) <= 25 and not re.search(r"[，,。；;：:、]", compact):
            generic = GENERIC_TITLE_PATTERN.search(compact)
            if generic:
                if compact == "函" or compact.endswith("函"):
                    return "函"
                if compact.endswith("合同") or compact.endswith("协议"):
                    return compact
    return None


def detect_document_type(title: str | None, text: str) -> str:
    body = compact_text((title or "") + "\n" + text[:2000])
    if title == "函" or "律师事务所函" in body or "律师函" in body:
        return "律师事务所函"
    if "专项法律服务合同" in body:
        return "专项法律服务合同"
    if "委托代理合同" in body:
        return "委托代理合同"
    if "授权委托书" in body or "PowerOfAttorney" in body:
        return "授权委托书"
    if "民事起诉状" in body or "起诉状" in body:
        if "要素式" in body or "当事人信息" in body:
            return "要素式民事起诉状"
        return "民事起诉状"
    if "证据目录" in body:
        return "证据目录"
    if "合同" in body:
        return "合同"
    if "协议" in body:
        return "协议"
    if "答辩状" in body:
        return "答辩状"
    if "申请书" in body:
        return "申请书"
    return title or "待确认"


def detect_signals(text: str, title: str | None, page_label: dict[str, int] | None) -> list[str]:
    body = compact_text(text)
    signals: list[str] = []
    if title:
        signals.append("title")
    if page_label and page_label.get("current") == 1:
        signals.append("page-reset")
    if page_label and page_label.get("current") == page_label.get("total"):
        signals.append("page-end")
    if any(keyword in body for keyword in ["以下无正文", "具状人", "此致", "签订日期", "签约日期", "委托人签字", "盖章"]):
        signals.append("closing")
    if any(keyword in body for keyword in ["要素式", "当事人信息", "诉讼请求的依据", "证据和证据来源"]):
        signals.append("form-like")
    return signals


def detect_dates(text: str, limit: int = 3) -> list[str]:
    dates: list[str] = []
    for match in DATE_PATTERN.finditer(text):
        value = re.sub(r"\s+", "", match.group(0))
        if value not in dates:
            dates.append(value)
        if len(dates) >= limit:
            break
    return dates


def detect_party_candidates(text: str, limit: int = 6) -> list[str]:
    candidates: list[str] = []
    for line in significant_lines(text, limit=80):
        for match in COMPANY_PATTERN.finditer(line):
            value = match.group(1).strip(" ：:，,。；;、")
            if value not in candidates and 4 <= len(value) <= 35:
                candidates.append(value)
            if len(candidates) >= limit:
                return candidates
    for prefix in ["原告", "被告", "甲方", "乙方", "委托人", "委托方"]:
        pattern = re.compile(prefix + r"[:：]?\s*([\u4e00-\u9fa5A-Za-z0-9（）()]{2,20})")
        for line in significant_lines(text, limit=80):
            match = pattern.search(line)
            if not match:
                continue
            value = match.group(1).strip(" ：:，,。；;、")
            if value and value not in candidates:
                candidates.append(value)
            if len(candidates) >= limit:
                return candidates
    return candidates


def inspect_pdf(pdf_path: Path, include_text: bool = False) -> dict[str, Any]:
    PdfReader, _ = load_pypdf()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF does not exist: {pdf_path}")

    reader = PdfReader(str(pdf_path))
    pages: list[dict[str, Any]] = []
    missing_text_pages: list[int] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            raw_text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            raw_text = ""
            extraction_error = str(exc)
        else:
            extraction_error = ""

        text = clean_extracted_text(raw_text)
        lines = significant_lines(text)
        page_label = detect_page_label(text)
        title = detect_title(lines)
        text_chars = len(compact_text(text))
        if text_chars < 20:
            missing_text_pages.append(index)
        item: dict[str, Any] = {
            "page": index,
            "rotation": page.get("/Rotate") or 0,
            "text_chars": text_chars,
            "first_lines": lines[:8],
            "title_candidate": title,
            "document_type_candidate": detect_document_type(title, text),
            "page_label": page_label,
            "date_candidates": detect_dates(text),
            "party_candidates": detect_party_candidates(text),
            "signals": detect_signals(text, title, page_label),
        }
        if extraction_error:
            item["extraction_error"] = extraction_error
        if include_text:
            item["text"] = text
        pages.append(item)

    return {
        "file": str(pdf_path),
        "page_count": len(reader.pages),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "text_layer": {
            "has_text_layer": bool(pages) and len(missing_text_pages) < len(pages),
            "missing_or_low_text_pages": missing_text_pages,
            "min_text_chars": min((page["text_chars"] for page in pages), default=0),
            "max_text_chars": max((page["text_chars"] for page in pages), default=0),
        },
        "pages": pages,
    }


def page_range_label(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"


def title_key(title: str | None) -> str:
    if not title:
        return ""
    value = compact_text(title)
    value = re.sub(r"[（(].*?[）)]", "", value)
    return value[:30]


def should_start_new_segment(current_page: dict[str, Any], previous_page: dict[str, Any], current_title: str | None) -> bool:
    page_no = int(current_page.get("page") or 0)
    if page_no <= 1:
        return True

    page_label = current_page.get("page_label")
    title = current_page.get("title_candidate")
    signals = set(current_page.get("signals") or [])
    previous_signals = set(previous_page.get("signals") or [])

    if page_label and page_label.get("current", 0) > 1:
        return False
    if page_label and page_label.get("current") == 1 and page_no != 1:
        return True
    if title and title_key(title) != title_key(current_title):
        return True
    if title and ("closing" in previous_signals or "page-end" in previous_signals):
        return True
    if "form-like" in signals and current_title and "form-like" not in previous_signals:
        return True
    return False


def guess_segment_filename(pages: list[dict[str, Any]], index: int) -> tuple[str, str, list[str]]:
    first_page = pages[0]
    segment_text = "\n".join("\n".join(page.get("first_lines") or []) for page in pages)
    doc_type = detect_document_type(first_page.get("title_candidate"), segment_text)
    if doc_type == "民事起诉状" and (
        any("form-like" in (page.get("signals") or []) for page in pages)
        or any((page.get("page_label") or {}).get("total", 0) >= 5 for page in pages)
    ):
        doc_type = "要素式民事起诉状"
    parties: list[str] = []
    for page in pages[:2]:
        for party in page.get("party_candidates") or []:
            if party not in parties:
                parties.append(party)
    subject = "待确认"
    if doc_type == "专项法律服务合同" and parties:
        subject = parties[0]
    if not subject or len(subject) > 28 or any(token in subject for token in ["与", "就甲方", "本表", "法院法院"]):
        subject = "待确认"

    filename_type = doc_type
    suffix = ""
    if doc_type == "要素式民事起诉状":
        filename_type = "民事起诉状"
        suffix = " 要素式"
    elif doc_type == "民事起诉状":
        suffix = " 普通版"

    evidence_parts = []
    if first_page.get("title_candidate"):
        evidence_parts.append(f"第 {first_page.get('page')} 页疑似标题为“{first_page.get('title_candidate')}”")
    page_label = first_page.get("page_label")
    if page_label:
        evidence_parts.append(f"页码显示 {page_label.get('current')}/{page_label.get('total')}")
    if not evidence_parts:
        evidence_parts.append(f"第 {first_page.get('page')} 页有拆分信号")

    filename = sanitize_filename(f"{filename_type} {subject}{suffix}.pdf", f"D{index:03d}.pdf")
    return filename, doc_type, evidence_parts


def suggest_manifest_from_inspection(inspection: dict[str, Any], output_dir: Path | None = None) -> dict[str, Any]:
    pages = inspection.get("pages") or []
    segments: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_title: str | None = None

    for page in pages:
        if not current:
            current = [page]
            current_title = page.get("title_candidate")
            continue
        previous_page = current[-1]
        if should_start_new_segment(page, previous_page, current_title):
            segments.append(current)
            current = [page]
            current_title = page.get("title_candidate")
        else:
            current.append(page)
            if not current_title and page.get("title_candidate"):
                current_title = page.get("title_candidate")
    if current:
        segments.append(current)

    manifest_segments: list[dict[str, Any]] = []
    for index, segment_pages in enumerate(segments, start=1):
        start = int(segment_pages[0]["page"])
        end = int(segment_pages[-1]["page"])
        filename, doc_type, evidence_parts = guess_segment_filename(segment_pages, index)
        low_text_pages = [page["page"] for page in segment_pages if page.get("text_chars", 0) < 20]
        confidence = "medium" if not low_text_pages else "low"
        needs_review = True
        manifest_segments.append(
            {
                "id": f"D{index:03d}",
                "pages": page_range_label(start, end),
                "suggested_filename": filename,
                "title": segment_pages[0].get("title_candidate") or doc_type,
                "document_type": doc_type,
                "confidence": confidence,
                "needs_review": needs_review,
                "evidence": "；".join(evidence_parts),
                "notes": "自动草稿，请复核边界、主体和文件名。"
                + (f" 低文字量页：{low_text_pages}。" if low_text_pages else ""),
            }
        )

    manifest: dict[str, Any] = {
        "source_pdf": inspection.get("file"),
        "text_check": "strict",
        "notes": "由 pdf_organizer.py --suggest-manifest 自动生成的草稿；执行前需人工复核。",
        "segments": manifest_segments,
    }
    if output_dir:
        manifest["output_dir"] = str(output_dir)
    return manifest


def write_json_output(data: dict[str, Any], output_path: str | None) -> None:
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if output_path:
        path = Path(output_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(path)
    else:
        print(content, end="")


def copy_pdf(input_file: Path, output_file: Path, dry_run: bool) -> None:
    if dry_run:
        return
    output_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_file, output_file)


def split_pdf(source_pdf: Path, output_file: Path, pages: list[int], dry_run: bool) -> None:
    if dry_run:
        return
    PdfReader, PdfWriter = load_pypdf()
    reader = PdfReader(str(source_pdf))
    writer = PdfWriter()
    total_pages = len(reader.pages)
    for page in pages:
        if page > total_pages:
            raise ValueError(f"Page out of bounds: {page} > {total_pages}")
        writer.add_page(reader.pages[page - 1])
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("wb") as f:
        writer.write(f)


def merge_pdf_items(items: list[dict[str, Any]], output_file: Path, base_dir: Path, dry_run: bool) -> str:
    labels: list[str] = []
    if dry_run:
        for item in items:
            file_path = resolve_path(item.get("file") or item.get("input_file"), base_dir)
            pages = str(item.get("pages") or "")
            labels.append(f"{file_path}{':' + pages if pages else ''}")
        return "; ".join(labels)

    PdfReader, PdfWriter = load_pypdf()
    writer = PdfWriter()
    for item in items:
        file_path = resolve_path(item.get("file") or item.get("input_file"), base_dir)
        if not file_path or not file_path.exists():
            raise FileNotFoundError(f"Input PDF does not exist: {file_path}")
        reader = PdfReader(str(file_path))
        pages_spec = item.get("pages")
        if pages_spec:
            page_numbers = parse_pages(str(pages_spec), len(reader.pages))
        else:
            page_numbers = list(range(1, len(reader.pages) + 1))
        for page_number in page_numbers:
            writer.add_page(reader.pages[page_number - 1])
        labels.append(f"{file_path}{':' + str(pages_spec) if pages_spec else ''}")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("wb") as f:
        writer.write(f)
    return "; ".join(labels)


def normalize_source_items(segment: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = segment.get("source_items")
    if raw_items is None:
        raw_items = segment.get("input_files")
    if raw_items is None:
        raw_items = segment.get("source_files")
    if raw_items is None:
        return []
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("source_items/input_files must be a non-empty array.")

    items: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, str):
            items.append({"file": item})
        elif isinstance(item, dict):
            items.append(dict(item))
        else:
            raise ValueError("source_items entries must be strings or objects.")
    return items


def collect_text_check_paths(segments: list[Any], source_pdf: Path | None, manifest_dir: Path) -> list[Path]:
    paths: list[Path] = []

    def add(path: Path | None) -> None:
        if path and path not in paths:
            paths.append(path)

    for segment in segments:
        if not isinstance(segment, dict):
            continue
        source_items = normalize_source_items(segment)
        input_file = resolve_path(segment.get("input_file"), manifest_dir)
        if source_items:
            for item in source_items:
                add(resolve_path(item.get("file") or item.get("input_file"), manifest_dir))
        elif input_file:
            add(input_file)
        elif segment.get("pages"):
            add(source_pdf)

    return paths


def resolve_text_check_mode(args: argparse.Namespace, manifest: dict[str, Any]) -> str:
    if args.text_check:
        return args.text_check
    manifest_mode = manifest.get("text_check")
    if manifest_mode:
        mode = str(manifest_mode).lower()
        if mode not in {"strict", "warn", "off"}:
            raise SystemExit("Manifest text_check must be one of: strict, warn, off.")
        return mode
    if manifest.get("require_text_layer") is False:
        return "off"
    return "strict"


def run_text_layer_checks(paths: list[Path], max_pages: int) -> list[dict[str, Any]]:
    return [check_pdf_text_layer(path, max_pages=max_pages) for path in paths]


def rotate_pdf(input_file: Path, output_file: Path, angle: int) -> None:
    angle = normalize_angle(angle)
    if angle == 0:
        if input_file != output_file:
            shutil.copy2(input_file, output_file)
        return
    PdfReader, PdfWriter = load_pypdf()
    reader = PdfReader(str(input_file))
    writer = PdfWriter()
    for page in reader.pages:
        page.rotate(angle)
        writer.add_page(page)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("wb") as f:
        writer.write(f)


def deskew_pdf(input_file: Path, output_file: Path) -> None:
    ocrmypdf = shutil.which("ocrmypdf")
    if not ocrmypdf:
        raise RuntimeError("Deskew requires ocrmypdf. Install it first or use pdf-processor for full preprocessing.")
    cmd = [
        ocrmypdf,
        "--deskew",
        "--rotate-pages",
        "--skip-text",
        str(input_file),
        str(output_file),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"ocrmypdf deskew failed: {message}")


def apply_transforms(output_file: Path, segment: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    transforms: list[str] = []
    rotation = segment.get("rotate") if "rotate" in segment else segment.get("rotation")
    if rotation is None:
        rotation = manifest.get("rotate") if "rotate" in manifest else manifest.get("rotation")
    deskew = bool(segment.get("deskew", manifest.get("deskew", False)))

    if rotation is not None:
        angle = normalize_angle(rotation)
        if angle:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                rotate_pdf(output_file, tmp_path, angle)
                shutil.move(str(tmp_path), output_file)
            finally:
                tmp_path.unlink(missing_ok=True)
            transforms.append(f"rotate {angle}")

    if deskew:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            deskew_pdf(output_file, tmp_path)
            shutil.move(str(tmp_path), output_file)
        finally:
            tmp_path.unlink(missing_ok=True)
        transforms.append("deskew")

    return transforms


def suggested_downstream_skills(segment: dict[str, Any]) -> list[str]:
    """根据文书类别返回路由标签，不绑定具体 Skill 名称。"""
    doc_type = str(segment.get("document_type") or segment.get("title") or "")
    filename = Path(str(segment.get("output_file") or segment.get("suggested_filename") or "")).name
    text = f"{doc_type} {filename}"
    categories: list[str] = []

    if any(keyword in text for keyword in ["合同", "协议"]):
        categories.append("合同审查")
    if any(keyword in text for keyword in ["起诉状", "判决书", "裁定书", "答辩状", "申请书", "证据目录", "庭审笔录"]):
        categories.append("诉讼分析")
    if any(keyword in text for keyword in ["律师事务所函", "函", "授权委托书"]):
        categories.append("材料整理")
    if not categories:
        categories.append("材料整理")
    if segment.get("needs_review") or str(segment.get("confidence", "")).lower() == "low":
        categories.insert(0, "复核")

    deduped: list[str] = []
    for cat in categories:
        if cat not in deduped:
            deduped.append(cat)
    return deduped


def build_handoff(resolved: dict[str, Any]) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    for segment in resolved.get("segments", []):
        if not isinstance(segment, dict):
            continue
        output_file = segment.get("output_file")
        document = {
            "id": segment.get("id"),
            "file": output_file,
            "filename": Path(str(output_file)).name if output_file else segment.get("suggested_filename"),
            "document_type": segment.get("document_type"),
            "title": segment.get("title"),
            "source_pages": segment.get("pages") or segment.get("resolved_pages"),
            "resolved_source": segment.get("resolved_source"),
            "parties": segment.get("parties", []),
            "date": segment.get("date"),
            "document_no": segment.get("document_no"),
            "confidence": segment.get("confidence"),
            "needs_review": bool(segment.get("needs_review", False)),
            "status": segment.get("status"),
            "evidence": segment.get("evidence"),
            "suggested_downstream": suggested_downstream_skills(segment),
        }
        documents.append(document)

    review_required = any(
        document.get("needs_review") or str(document.get("confidence", "")).lower() == "low"
        for document in documents
    )
    return {
        "schema": "pdf-organizer-handoff/v1",
        "created_at": resolved.get("resolved_at"),
        "source_pdf": resolved.get("source_pdf"),
        "output_dir": resolved.get("output_dir"),
        "archive_dir": resolved.get("archive_dir"),
        "dry_run": resolved.get("dry_run"),
        "review_required": review_required,
        "document_count": len(documents),
        "documents": documents,
        "recommended_next_steps": [
            "如 review_required 为 true，先复核文件名、主体和边界。",
            "合同/协议类建议走合同审查流程。",
            "起诉状、判决书、裁定书等诉讼文书建议走诉讼分析流程。",
            "其余材料按材料整理流程归类。",
        ],
    }


def write_archive(archive_dir: Path, manifest: dict[str, Any], resolved: dict[str, Any], report_lines: list[str]) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    input_path = archive_dir / "organize_manifest.input.json"
    resolved_path = archive_dir / "organize_manifest.resolved.json"
    report_path = archive_dir / "organize_report.md"
    handoff_path = archive_dir / "handoff.json"
    run_meta_path = archive_dir / "run_meta.json"
    with input_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with resolved_path.open("w", encoding="utf-8") as f:
        json.dump(resolved, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with report_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(report_lines).rstrip() + "\n")
    with handoff_path.open("w", encoding="utf-8") as f:
        json.dump(build_handoff(resolved), f, ensure_ascii=False, indent=2)
        f.write("\n")
    run_meta = {
        "created_at": resolved.get("resolved_at"),
        "source_pdf": resolved.get("source_pdf"),
        "output_dir": resolved.get("output_dir"),
        "archive_dir": str(archive_dir),
        "segment_count": len(resolved.get("segments", [])),
        "handoff_file": str(handoff_path),
        "dry_run": resolved.get("dry_run"),
    }
    with run_meta_path.open("w", encoding="utf-8") as f:
        json.dump(run_meta, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build_report_header(
    manifest_path: Path,
    output_dir: Path,
    archive_dir: Path | None,
    dry_run: bool,
    text_check_lines: list[str] | None = None,
) -> list[str]:
    mode = "dry-run" if dry_run else "executed"
    lines = [
        "# PDF organizer report",
        "",
        f"- Mode: {mode}",
        f"- Manifest: {manifest_path}",
        f"- Output directory: {output_dir}",
        f"- Time: {datetime.now().isoformat(timespec='seconds')}",
    ]
    if archive_dir:
        lines.append(f"- Archive directory: {archive_dir}")
    if text_check_lines:
        lines.extend(["", "## Text layer check", ""])
        lines.extend(text_check_lines)
    lines.extend(
        [
            "",
            "| # | Segment | Source | Pages | Output | Action | Confidence | Review | Status |",
            "|---|---------|--------|-------|--------|--------|------------|--------|--------|",
        ]
    )
    return lines


def process_manifest(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest_dir = manifest_path.parent
    manifest = read_json(manifest_path)

    source_pdf = resolve_path(args.source, Path.cwd()) or resolve_path(manifest.get("source_pdf"), manifest_dir)
    output_dir = resolve_path(args.output_dir, Path.cwd()) or resolve_path(manifest.get("output_dir"), manifest_dir)
    if output_dir is None:
        output_dir = manifest_dir / "output"
    archive_root = resolve_path(args.archive_root, Path.cwd()) or resolve_path(manifest.get("archive_root"), manifest_dir)
    if archive_root is None:
        archive_root = ARCHIVE_ROOT
    archive_dir = None if args.dry_run else build_archive_subdir(archive_root, source_pdf, output_dir, manifest_path)

    segments = manifest.get("segments")
    if not isinstance(segments, list) or not segments:
        raise SystemExit("Manifest must contain a non-empty segments array.")

    needs_source_split = any(
        isinstance(segment, dict) and segment.get("pages") and not segment.get("input_file")
        for segment in segments
    )
    total_pages: int | None = None
    if source_pdf and not source_pdf.exists():
        raise SystemExit(f"Source PDF does not exist: {source_pdf}")

    text_check_mode = resolve_text_check_mode(args, manifest)
    text_check_results: list[dict[str, Any]] = []
    if text_check_mode != "off":
        text_check_paths = collect_text_check_paths(segments, source_pdf, manifest_dir)
        text_check_results = run_text_layer_checks(text_check_paths, args.text_check_pages)
    text_check_lines = format_text_layer_check(text_check_results, text_check_mode)
    failures = text_layer_failures(text_check_results)

    if failures and text_check_mode == "strict":
        report_lines = build_report_header(
            manifest_path,
            output_dir,
            archive_dir,
            args.dry_run,
            text_check_lines,
        )
        report_lines.extend(["", "## Errors", ""])
        report_lines.extend(f"- {failure}" for failure in failures)
        resolved = dict(manifest)
        resolved["source_pdf"] = str(source_pdf) if source_pdf else manifest.get("source_pdf")
        resolved["output_dir"] = str(output_dir)
        resolved["archive_dir"] = str(archive_dir) if archive_dir else None
        resolved["resolved_at"] = datetime.now().isoformat(timespec="seconds")
        resolved["dry_run"] = bool(args.dry_run)
        resolved["text_layer_check"] = {
            "mode": text_check_mode,
            "sample_pages": args.text_check_pages,
            "results": text_check_results,
        }
        resolved["segments"] = []
        if archive_dir:
            write_archive(archive_dir, manifest, resolved, report_lines)
        print("\n".join(report_lines))
        return 1

    if source_pdf and needs_source_split and not args.dry_run:
        PdfReader, _ = load_pypdf()
        total_pages = len(PdfReader(str(source_pdf)).pages)

    resolved_segments: list[dict[str, Any]] = []
    report_lines = build_report_header(manifest_path, output_dir, archive_dir, args.dry_run, text_check_lines)
    warnings: list[str] = failures[:] if text_check_mode == "warn" else []
    errors: list[str] = []

    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            errors.append(f"Segment {index} must be an object.")
            continue

        segment_id = str(segment.get("id") or f"D{index:03d}")
        input_file = resolve_path(segment.get("input_file"), manifest_dir)
        source_items = normalize_source_items(segment)
        pages_spec = segment.get("pages")
        target_name = segment_filename(segment, index)
        target_path = unique_path(output_dir / target_name)
        confidence = str(segment.get("confidence") or "")
        needs_review = bool(segment.get("needs_review", False))
        status = "planned" if args.dry_run else "ok"
        action = "copy"
        source_label = ""
        pages_label = str(pages_spec or "")
        transforms: list[str] = []

        try:
            if source_items:
                action = "merge"
                source_label = merge_pdf_items(source_items, target_path, manifest_dir, args.dry_run)
                pages_label = "mixed"
            elif input_file:
                if not input_file.exists():
                    raise FileNotFoundError(f"Input PDF does not exist: {input_file}")
                source_label = str(input_file)
                copy_pdf(input_file, target_path, args.dry_run)
            elif pages_spec:
                if not source_pdf:
                    raise ValueError("source_pdf is required when segment uses pages.")
                pages = parse_pages(str(pages_spec), total_pages)
                source_label = str(source_pdf)
                pages_label = ",".join(str(page) for page in pages)
                split_pdf(source_pdf, target_path, pages, args.dry_run)
                action = "split"
            else:
                raise ValueError("Segment must contain input_file, source_items/input_files, or pages.")
            if not args.dry_run:
                transforms = apply_transforms(target_path, segment, manifest)
                if transforms:
                    action = f"{action}+{'+'.join(transforms)}"
        except Exception as exc:  # noqa: BLE001
            status = f"error: {exc}"
            errors.append(f"{segment_id}: {exc}")

        resolved_segment = dict(segment)
        resolved_segment.update(
            {
                "id": segment_id,
                "output_file": str(target_path),
                "resolved_source": source_label,
                "resolved_pages": pages_label,
                "action": action,
                "transforms": transforms,
                "status": status,
            }
        )
        resolved_segments.append(resolved_segment)
        report_lines.append(
            f"| {index} | {segment_id} | `{source_label}` | {pages_label} | "
            f"`{target_path.name}` | {action} | {confidence} | {needs_review} | {status} |"
        )

    resolved = dict(manifest)
    resolved["source_pdf"] = str(source_pdf) if source_pdf else manifest.get("source_pdf")
    resolved["output_dir"] = str(output_dir)
    resolved["archive_dir"] = str(archive_dir) if archive_dir else None
    resolved["resolved_at"] = datetime.now().isoformat(timespec="seconds")
    resolved["dry_run"] = bool(args.dry_run)
    resolved["text_layer_check"] = {
        "mode": text_check_mode,
        "sample_pages": args.text_check_pages,
        "results": text_check_results,
    }
    resolved["segments"] = resolved_segments

    if warnings:
        report_lines.extend(["", "## Warnings", ""])
        report_lines.extend(f"- {warning}" for warning in warnings)

    if errors:
        report_lines.extend(["", "## Errors", ""])
        report_lines.extend(f"- {error}" for error in errors)

    review_items = [
        seg for seg in resolved_segments if seg.get("needs_review") or str(seg.get("confidence", "")).lower() == "low"
    ]
    if review_items:
        report_lines.extend(["", "## Needs review", ""])
        for seg in review_items:
            report_lines.append(f"- {seg.get('id')}: {Path(str(seg.get('output_file', ''))).name}")

    if archive_dir:
        write_archive(archive_dir, manifest, resolved, report_lines)

    print("\n".join(report_lines))
    return 1 if errors else 0


def check_text_layer_command(paths: list[str], max_pages: int) -> int:
    pdf_paths = [Path(path).expanduser().resolve() for path in paths]
    results = run_text_layer_checks(pdf_paths, max_pages)
    lines = ["# PDF text layer check", ""]
    lines.extend(format_text_layer_check(results, "standalone"))
    failures = text_layer_failures(results)
    if failures:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {failure}" for failure in failures)
    print("\n".join(lines))
    return 1 if failures else 0


def inspect_command(pdf_path: str, output_path: str | None, include_text: bool) -> int:
    inspection = inspect_pdf(Path(pdf_path).expanduser().resolve(), include_text=include_text)
    write_json_output(inspection, output_path)
    missing_pages = inspection.get("text_layer", {}).get("missing_or_low_text_pages") or []
    return 1 if len(missing_pages) == inspection.get("page_count") else 0


def suggest_manifest_command(pdf_path: str, output_dir: str | None, output_path: str | None) -> int:
    source_pdf = Path(pdf_path).expanduser().resolve()
    inspection = inspect_pdf(source_pdf, include_text=False)
    missing_pages = inspection.get("text_layer", {}).get("missing_or_low_text_pages") or []
    if len(missing_pages) == inspection.get("page_count"):
        print(
            f"No searchable text layer detected in {source_pdf}. "
            "Run PDF Processor OCR before suggesting an organize manifest.",
            file=sys.stderr,
        )
        return 1
    resolved_output_dir = Path(output_dir).expanduser().resolve() if output_dir else None
    manifest = suggest_manifest_from_inspection(inspection, resolved_output_dir)
    write_json_output(manifest, output_path)
    return 0


A4_PORTRAIT = (595.0, 842.0)
A4_LANDSCAPE = (842.0, 595.0)


def normalize_a4_pdf(input_file: Path, output_file: Path | None = None) -> dict[str, Any]:
    """将 PDF 每页标准化为 A4 尺寸：横图→A4 横版，竖图→A4 竖版，等比缩放居中。"""
    from pypdf import PdfReader, PdfWriter, Transformation

    reader = PdfReader(str(input_file))
    writer = PdfWriter()
    page_stats: list[dict[str, Any]] = []

    for page_idx, page in enumerate(reader.pages):
        box = page.mediabox
        w = float(box.width)
        h = float(box.height)

        is_landscape = w > h
        target_w, target_h = A4_LANDSCAPE if is_landscape else A4_PORTRAIT

        scale = min(target_w / w, target_h / h)
        scaled_w = w * scale
        scaled_h = h * scale
        tx = (target_w - scaled_w) / 2
        ty = (target_h - scaled_h) / 2

        new_page = writer.add_blank_page(width=target_w, height=target_h)
        op = Transformation().scale(scale, scale).translate(tx, ty)
        new_page.merge_transformed_page(page, op)

        page_stats.append({
            "page": page_idx + 1,
            "original_size": f"{w:.0f}x{h:.0f}",
            "orientation": "landscape" if is_landscape else "portrait",
            "target_size": f"{target_w:.0f}x{target_h:.0f}",
            "scale": round(scale, 4),
        })

    target = output_file or input_file
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as f:
        writer.write(f)

    return {
        "input_file": str(input_file),
        "output_file": str(target),
        "total_pages": len(reader.pages),
        "pages": page_stats,
    }


def normalize_a4_command(paths: list[str], in_place: bool, output_dir: str | None) -> int:
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for raw_path in paths:
        pdf_path = Path(raw_path).expanduser().resolve()
        if not pdf_path.exists():
            errors.append(f"{raw_path}: file not found")
            continue
        try:
            if output_dir:
                out_path = Path(output_dir).expanduser().resolve() / pdf_path.name
            elif in_place:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                result = normalize_a4_pdf(pdf_path, tmp_path)
                shutil.move(str(tmp_path), str(pdf_path))
                result["output_file"] = str(pdf_path)
                results.append(result)
                continue
            else:
                out_path = pdf_path
            result = normalize_a4_pdf(pdf_path, out_path)
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{raw_path}: {exc}")

    lines = ["# PDF A4 标准化结果", ""]
    for result in results:
        landscape_count = sum(1 for p in result["pages"] if p["orientation"] == "landscape")
        portrait_count = result["total_pages"] - landscape_count
        lines.append(f"- `{Path(result['output_file']).name}`: {result['total_pages']} 页"
                     f"（横版 {landscape_count}，竖版 {portrait_count}）")
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {e}" for e in errors)
    print("\n".join(lines))
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Organize legal PDF documents according to a manifest.")
    parser.add_argument("--manifest", help="Path to organize_manifest.json")
    parser.add_argument("--source", help="Override source PDF path")
    parser.add_argument("--output-dir", help="Override output directory")
    parser.add_argument("--manifest-output", help="Write suggested manifest JSON to this path.")
    parser.add_argument("--inspect-output", help="Write page inspection JSON to this path.")
    parser.add_argument(
        "--archive-root",
        help="Archive root directory for manifests and reports. Defaults to this skill's archive/ directory.",
    )
    parser.add_argument(
        "--text-check",
        choices=["strict", "warn", "off"],
        help="Searchable text layer check mode. Defaults to strict unless manifest disables it.",
    )
    parser.add_argument(
        "--text-check-pages",
        type=int,
        default=5,
        help="Number of representative pages to sample when checking for a text layer.",
    )
    parser.add_argument(
        "--check-text-layer",
        nargs="+",
        help="Only check whether the given PDF files have a searchable text layer.",
    )
    parser.add_argument("--inspect", help="Inspect one PDF and output page-level evidence as JSON.")
    parser.add_argument("--include-text", action="store_true", help="Include full extracted page text in --inspect output.")
    parser.add_argument("--suggest-manifest", help="Generate a draft organize_manifest.json from one OCR PDF.")
    parser.add_argument("--dry-run", action="store_true", help="Preview planned outputs without writing PDFs")
    parser.add_argument(
        "--normalize-a4",
        nargs="+",
        help="Normalize PDF pages to A4: landscape pages to A4 landscape, portrait pages to A4 portrait.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        default=True,
        help="Overwrite input files in place (default behavior for --normalize-a4).",
    )
    parser.add_argument(
        "--normalize-output-dir",
        help="Output directory for --normalize-a4 (defaults to in-place overwrite).",
    )
    args = parser.parse_args()

    if args.text_check_pages < 1:
        parser.error("--text-check-pages must be greater than 0")
    if args.check_text_layer:
        return check_text_layer_command(args.check_text_layer, args.text_check_pages)
    if args.normalize_a4:
        return normalize_a4_command(args.normalize_a4, args.in_place, args.normalize_output_dir)
    if args.inspect:
        return inspect_command(args.inspect, args.inspect_output, args.include_text)
    if args.suggest_manifest:
        return suggest_manifest_command(args.suggest_manifest, args.output_dir, args.manifest_output)
    if not args.manifest:
        parser.error("--manifest is required unless --check-text-layer, --inspect, or --suggest-manifest is used")
    return process_manifest(args)


if __name__ == "__main__":
    raise SystemExit(main())
