#!/usr/bin/env python3
"""Build a deterministic paragraph-level source index for Course Generator."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Iterable


SUPPORTED_SUFFIXES = {".md", ".txt"}
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]\n]*\]\((?:[^()\\\n]|\\.|\([^()\n]*\))*\)")
SPEAKER_LINE_RE = re.compile(
    r"^(?:发言人|说话人|Speaker)\s*\d*\s+\d{1,2}:\d{2}(?::\d{2})?\s*$",
    re.IGNORECASE,
)
TIMESTAMP_LINE_RE = re.compile(r"^>\s*\*?\d{1,2}:\d{2}(?::\d{2})?\*?\s*$")
TRANSCRIPT_HEADING = "## 转录内容"
DERIVED_APPENDIX_HEADING = "## 关键词"
DERIVED_APPENDIX_MARKERS = {"## 议程摘要", "## 重点内容", "## Q&A 问答", "## PPT 章节标题"}
AUTHORITY_MODES = {"current", "historical"}
AUTHORITY_SIGNAL_RE = re.compile(
    r"不作为(?:现行|当前).{0,12}(?:规范|依据)"
    r"|(?:修订|勘误|编校|更正)(?:说明|口径)?.{0,100}(?:统一|应当?|必须).{0,8}(?:见|以).{0,80}(?:为准|勘误|修订口径)"
    r"|(?:统一|应当?|必须).{0,8}(?:见|以).{0,80}(?:勘误|修订口径)"
)
BOOK_TITLE_RE = re.compile(r"《([^》\n]{2,120})》")
SECTION_HINT_RE = re.compile(r"[“\"]([^”\"\n]{2,80}(?:勘误|修订|收束|归位)[^”\"\n]{0,40})[”\"]")
MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TABLE_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
ASCII_TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.+/#-]{1,39}|\d+(?:\.\d+)+")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_authority_notices(path: Path) -> list[dict[str, object]]:
    """Detect explicit editorial supersession notices near the start of a source."""
    lines = path.read_text(encoding="utf-8").splitlines()
    notices: list[dict[str, object]] = []
    for line_no, line in enumerate(lines[:120], 1):
        stripped = line.strip()
        if not stripped or not AUTHORITY_SIGNAL_RE.search(stripped):
            continue
        titles = list(dict.fromkeys(title.strip() for title in BOOK_TITLE_RE.findall(stripped) if title.strip()))
        section_match = SECTION_HINT_RE.search(stripped)
        notices.append(
            {
                "line": line_no,
                "titles": titles,
                "section_hint": section_match.group(1).strip() if section_match else None,
            }
        )
    return notices


def split_markdown_table_row(line: str) -> list[str] | None:
    """Split a simple Markdown table row while preserving inline Markdown."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in stripped[1:-1]:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            current.append(char)
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    return cells


def pure_deprecated_aliases(original_text: str, revised_text: str) -> list[str]:
    """Return aliases only when the old cell is itself just an alias list.

    Prose rows may legitimately quote the old wording to explain the correction, so
    they are not converted into global forbidden terms.
    """
    aliases = [item.strip() for item in INLINE_CODE_RE.findall(original_text) if item.strip()]
    if aliases:
        remainder = INLINE_CODE_RE.sub("", original_text)
        remainder = re.sub(r"[\s、，,；;：:/＋+与和或]+", "", remainder)
        if remainder:
            return []
    elif re.fullmatch(r"[A-Za-z0-9_.+#\-/\s、，,；;：:]+", original_text):
        aliases = [item.strip() for item in re.split(r"[、，,；;]+", original_text) if item.strip()]
    else:
        return []
    revised_folded = revised_text.casefold()
    return list(dict.fromkeys(alias for alias in aliases if alias.casefold() not in revised_folded))


def _compact_fidelity_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold())


def _character_ngrams(value: str, size: int = 2) -> set[str]:
    compact = _compact_fidelity_text(value)
    if len(compact) < size:
        return {compact} if compact else set()
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}


def correction_candidate_score(correction: dict[str, object], text: str) -> float:
    """Rank ordinary source blocks that may restate a superseded claim.

    This is deliberately a recall-oriented hint, not an automatic deletion rule.
    The plan must still confirm the exact block IDs before they are quarantined.
    """
    original = str(correction.get("original_text") or "")
    revised = str(correction.get("revised_text") or "")
    compact_text = _compact_fidelity_text(text)
    original_grams = _character_ngrams(original)
    revised_grams = _character_ngrams(revised)
    text_grams = _character_ngrams(text)
    if not compact_text or not original_grams or not text_grams:
        return 0.0
    old_overlap = len(original_grams & text_grams) / len(original_grams)
    revised_overlap = len(revised_grams & text_grams) / max(1, len(revised_grams))
    if _compact_fidelity_text(revised) in compact_text or revised_overlap >= max(0.58, old_overlap + 0.14):
        return 0.0

    signals = [
        item.strip()
        for item in INLINE_CODE_RE.findall(original)
        + ASCII_TERM_RE.findall(original)
        + list(correction.get("deprecated_terms") or [])
        if item.strip()
    ]
    unique_signals = list(dict.fromkeys(item.casefold() for item in signals))
    signal_hits = sum(signal in text.casefold() for signal in unique_signals)
    signal_ratio = signal_hits / max(1, len(unique_signals))
    if old_overlap < 0.28 and signal_hits == 0:
        return 0.0
    return round(0.72 * old_overlap + 0.28 * signal_ratio, 4)


def correction_table_rows(path: Path, section_hint: str | None) -> list[dict[str, object]]:
    """Extract explicit old→revised correction rows from the hinted section."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = 0
    end = len(lines)
    if section_hint:
        matched_level: int | None = None
        matched_index: int | None = None
        for index, line in enumerate(lines):
            match = MARKDOWN_HEADING_RE.match(line.strip())
            if not match:
                continue
            heading = match.group(2).strip()
            hint_section = re.search(r"第\s*([0-9一二三四五六七八九十]+)\s*节", section_hint)
            heading_section = re.search(r"第\s*([0-9一二三四五六七八九十]+)\s*节", heading)
            same_correction_section = (
                hint_section is not None
                and heading_section is not None
                and hint_section.group(1) == heading_section.group(1)
                and any(token in section_hint and token in heading for token in ("勘误", "修订", "更正"))
            )
            if heading == section_hint or section_hint in heading or heading in section_hint or same_correction_section:
                matched_level = len(match.group(1))
                matched_index = index
                break
        if matched_index is None or matched_level is None:
            return []
        start = matched_index + 1
        for index in range(start, len(lines)):
            match = MARKDOWN_HEADING_RE.match(lines[index].strip())
            if match and len(match.group(1)) <= matched_level:
                end = index
                break

    rows: list[dict[str, object]] = []
    index = start
    while index + 1 < end:
        header = split_markdown_table_row(lines[index])
        separator = split_markdown_table_row(lines[index + 1])
        if (
            header
            and separator
            and len(header) >= 2
            and len(separator) == len(header)
            and all(TABLE_SEPARATOR_CELL_RE.fullmatch(cell.replace(" ", "")) for cell in separator)
            and ("原" in header[0] or "旧" in header[0])
            and any(token in header[1] for token in ("修订", "现行", "新"))
        ):
            row_index = index + 2
            while row_index < end:
                cells = split_markdown_table_row(lines[row_index])
                if not cells or len(cells) < 2:
                    break
                original_text = cells[0].strip()
                revised_text = cells[1].strip()
                if original_text and revised_text:
                    rows.append(
                        {
                            "line": row_index + 1,
                            "original_text": original_text,
                            "revised_text": revised_text,
                            "deprecated_terms": pure_deprecated_aliases(original_text, revised_text),
                        }
                    )
                row_index += 1
            break
        index += 1
    return rows


def _candidate_source_files(root: Path, output_resolved: Path) -> list[Path]:
    sources: list[Path] = []
    excluded_output_dir: Path | None = None
    try:
        output_resolved.relative_to(root)
        if output_resolved.parent != root:
            excluded_output_dir = output_resolved.parent
    except ValueError:
        pass
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        path_resolved = path.resolve()
        if path_resolved == output_resolved:
            continue
        if excluded_output_dir is not None:
            try:
                path_resolved.relative_to(excluded_output_dir)
                continue
            except ValueError:
                pass
        relative = path.relative_to(root)
        if any(part.startswith(".") or part in {"__pycache__", "node_modules", "archive"} for part in relative.parts):
            continue
        sources.append(path_resolved)
    sources.sort(key=lambda item: item.relative_to(root).as_posix())
    return sources


def _resolve_controlling_paths(primary_paths: list[Path], search_paths: list[Path]) -> dict[Path, list[Path]]:
    by_stem: dict[str, list[Path]] = {}
    for path in search_paths:
        by_stem.setdefault(path.stem, []).append(path)
    resolved: dict[Path, list[Path]] = {}
    for primary in primary_paths:
        matches: list[Path] = []
        for notice in detect_authority_notices(primary):
            titles = notice["titles"]
            if not titles:
                raise ValueError(
                    f"检测到来源权威声明但未找到《控制文档》标题: {primary.name}:L{notice['line']}"
                )
            for title in titles:
                candidates = [path for path in by_stem.get(str(title), []) if path != primary]
                if len(candidates) != 1:
                    state = "未找到" if not candidates else "找到多个"
                    raise ValueError(
                        f"{state}编校说明指定的控制文档《{title}》；"
                        "请把唯一的同名 .md/.txt 文件放在来源同目录，或明确使用 --authority-mode historical"
                    )
                if candidates[0] not in matches:
                    matches.append(candidates[0])
        resolved[primary] = matches
    return resolved


def classify_special(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("#") and re.match(r"^#{1,6}\s+", stripped):
        return "heading"
    if TIMESTAMP_LINE_RE.fullmatch(stripped):
        return "timestamp"
    if SPEAKER_LINE_RE.fullmatch(stripped):
        return "speaker"
    if stripped == "---":
        return "separator"
    return None


def image_only_line(line: str) -> list[str]:
    """Return every Markdown image when a line contains images and whitespace only."""
    images = MARKDOWN_IMAGE_RE.findall(line.strip())
    if not images:
        return []
    remainder = MARKDOWN_IMAGE_RE.sub("", line).strip()
    return images if not remainder else []


def derived_appendix_start(lines: list[str]) -> int | None:
    """Detect platform-generated appendices in transcript bundles, conservatively."""
    stripped = [line.strip() for line in lines]
    try:
        transcript_index = stripped.index(TRANSCRIPT_HEADING)
        appendix_index = stripped.index(DERIVED_APPENDIX_HEADING, transcript_index + 1)
    except ValueError:
        return None
    if not any(marker in stripped[appendix_index + 1 :] for marker in DERIVED_APPENDIX_MARKERS):
        return None
    return appendix_index + 1  # one-based line number


def iter_file_blocks(path: Path) -> Iterable[tuple[str, int, int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    appendix_start = derived_appendix_start(lines)
    content_lines: list[str] = []
    content_start = 0

    def flush_content(end_line: int) -> tuple[str, int, int, str] | None:
        nonlocal content_lines, content_start
        if not content_lines:
            return None
        text = "\n".join(content_lines).strip()
        kind = "derived" if appendix_start is not None and content_start >= appendix_start else "content"
        result = (kind, content_start, end_line, text)
        content_lines = []
        content_start = 0
        return result

    for line_no, line in enumerate(lines, 1):
        images = image_only_line(line)
        if images:
            flushed = flush_content(line_no - 1)
            if flushed:
                yield flushed
            for markdown in images:
                yield "image", line_no, line_no, markdown
            continue
        special = classify_special(line)
        if not line.strip():
            flushed = flush_content(line_no - 1)
            if flushed:
                yield flushed
            continue
        if special:
            flushed = flush_content(line_no - 1)
            if flushed:
                yield flushed
            kind = special
            if appendix_start is not None and line_no >= appendix_start and special != "image":
                kind = "derived"
            yield kind, line_no, line_no, line.strip()
            continue
        if not content_lines:
            content_start = line_no
        content_lines.append(line)
    flushed = flush_content(len(lines))
    if flushed:
        yield flushed


def discover_sources(
    input_path: Path,
    output_path: Path,
    authority_mode: str = "current",
) -> tuple[Path, list[Path]]:
    resolved = input_path.expanduser().resolve()
    output_resolved = output_path.expanduser().resolve()
    if authority_mode not in AUTHORITY_MODES:
        raise ValueError(f"authority_mode 必须为 current 或 historical: {authority_mode!r}")
    if resolved.is_file():
        if resolved.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"不支持的来源文件类型: {resolved.suffix}")
        sources = [resolved]
        if authority_mode == "current" and detect_authority_notices(resolved):
            siblings = _candidate_source_files(resolved.parent, output_resolved)
            controls = _resolve_controlling_paths([resolved], siblings).get(resolved, [])
            sources.extend(path for path in controls if path not in sources)
        return resolved.parent, sources
    if not resolved.is_dir():
        raise ValueError(f"输入不存在: {resolved}")
    sources = _candidate_source_files(resolved, output_resolved)
    if not sources:
        raise ValueError("输入范围内没有 .md 或 .txt 来源文件")
    if authority_mode == "current":
        primary_with_notices = [path for path in sources if detect_authority_notices(path)]
        if primary_with_notices:
            _resolve_controlling_paths(primary_with_notices, sources)
    return resolved, sources


def build_index_data(
    input_path: Path,
    output_path: Path,
    authority_mode: str = "current",
) -> tuple[dict, dict[str, str]]:
    input_root, sources = discover_sources(input_path, output_path, authority_mode)
    notice_specs: list[tuple[Path, dict[str, object]]] = [
        (path, notice)
        for path in sources
        for notice in detect_authority_notices(path)
    ]
    controlling_paths: set[Path] = set()
    control_map: dict[Path, list[Path]] = {}
    if authority_mode == "current" and notice_specs:
        control_map = _resolve_controlling_paths(
            list(dict.fromkeys(path for path, _ in notice_specs)),
            _candidate_source_files(input_root, output_path.expanduser().resolve()),
        )
        controlling_paths = {item for values in control_map.values() for item in values}
    block_ordinal = 0
    source_records = []
    block_texts: dict[str, str] = {}
    source_id_by_path: dict[Path, str] = {}
    notice_block_ids: dict[tuple[Path, int], tuple[str, str]] = {}
    for source_ordinal, path in enumerate(sources, 1):
        source_id = f"SRC-{source_ordinal:03d}"
        source_id_by_path[path] = source_id
        relative = path.relative_to(input_root).as_posix()
        blocks = []
        for kind, start_line, end_line, text in iter_file_blocks(path):
            block_ordinal += 1
            block_id = f"BLK-{block_ordinal:05d}"
            if path in controlling_paths:
                kind = "control"
            elif any(start_line <= int(notice["line"]) <= end_line for source_path, notice in notice_specs if source_path == path):
                kind = "authority"
            source_ref = f"{source_id}#L{start_line:04d}-L{end_line:04d}"
            block_texts[block_id] = text
            if kind == "authority":
                for source_path, notice in notice_specs:
                    if source_path == path and start_line <= int(notice["line"]) <= end_line:
                        notice_block_ids[(path, int(notice["line"]))] = (block_id, source_ref)
            preview = re.sub(r"\s+", " ", text).strip()[:160]
            blocks.append(
                {
                    "id": block_id,
                    "source_ref": source_ref,
                    "kind": kind,
                    "char_count": len(text),
                    "sha256": sha256_bytes(text.encode("utf-8")),
                    "preview": preview,
                }
            )
        source_records.append(
            {
                "id": source_id,
                "path": relative,
                "sha256": sha256_file(path),
                "blocks": blocks,
            }
        )
    authority_notices: list[dict[str, object]] = []
    authority_corrections: list[dict[str, object]] = []
    for ordinal, (path, notice) in enumerate(notice_specs, 1):
        block_id, source_ref = notice_block_ids[(path, int(notice["line"]))]
        controls = control_map.get(path, []) if authority_mode == "current" else []
        authority_id = f"AUTH-{ordinal:03d}"
        authority_notices.append(
            {
                "id": authority_id,
                "source_block_id": block_id,
                "source_ref": source_ref,
                "controlling_titles": list(notice["titles"]),
                "controlling_source_ids": [source_id_by_path[item] for item in controls],
                "section_hint": notice["section_hint"],
            }
        )
        for control in controls:
            control_source_id = source_id_by_path[control]
            for row in correction_table_rows(control, notice["section_hint"]):
                line_no = int(row["line"])
                correction = {
                        "id": f"COR-{len(authority_corrections) + 1:03d}",
                        "authority_id": authority_id,
                        "source_id": control_source_id,
                        "source_ref": f"{control_source_id}#L{line_no:04d}-L{line_no:04d}",
                        "original_text": row["original_text"],
                        "revised_text": row["revised_text"],
                        "deprecated_terms": row["deprecated_terms"],
                    }
                candidates: list[tuple[float, str]] = []
                for candidate_source in source_records:
                    if candidate_source.get("id") in authority_notices[-1]["controlling_source_ids"]:
                        continue
                    for block in candidate_source.get("blocks") or []:
                        if block.get("kind") != "content":
                            continue
                        block_id = str(block.get("id"))
                        score = correction_candidate_score(correction, block_texts.get(block_id, ""))
                        if score >= 0.24:
                            candidates.append((score, block_id))
                candidates.sort(key=lambda item: (-item[0], item[1]))
                correction["superseded_candidate_block_ids"] = [block_id for _, block_id in candidates[:8]]
                authority_corrections.append(correction)
    result = {
        "schema_version": "1.4",
        "authority": {
            "mode": authority_mode,
            "notices": authority_notices,
            "corrections": authority_corrections,
        },
        "sources": source_records,
    }
    return result, block_texts


def build_index(input_path: Path, output_path: Path, authority_mode: str = "current") -> dict:
    result, _ = build_index_data(input_path, output_path, authority_mode)
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为课程来源建立稳定段落级 source-index.json")
    parser.add_argument("--input", required=True, help="单个 .md/.txt 文件或来源目录")
    parser.add_argument("--output", required=True, help="source-index.json 输出路径")
    parser.add_argument(
        "--authority-mode",
        choices=sorted(AUTHORITY_MODES),
        default="current",
        help="current 自动解析显式控制文档；historical 仅在用户明确要保留历史口径时使用",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = build_index(Path(args.input), Path(args.output), args.authority_mode)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"❌ 来源索引失败: {exc}")
        return 2
    content_count = sum(
        1 for source in result["sources"] for block in source["blocks"] if block["kind"] == "content"
    )
    block_count = sum(len(source["blocks"]) for source in result["sources"])
    print(
        json.dumps(
            {
                "status": "PASS",
                "source_count": len(result["sources"]),
                "block_count": block_count,
                "content_block_count": content_count,
                "authority_mode": result["authority"]["mode"],
                "authority_notice_count": len(result["authority"]["notices"]),
                "authority_correction_count": len(result["authority"]["corrections"]),
                "output": str(Path(args.output).expanduser().resolve()),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
