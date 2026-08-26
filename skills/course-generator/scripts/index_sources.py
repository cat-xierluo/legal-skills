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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def discover_sources(input_path: Path, output_path: Path) -> tuple[Path, list[Path]]:
    resolved = input_path.expanduser().resolve()
    output_resolved = output_path.expanduser().resolve()
    if resolved.is_file():
        if resolved.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"不支持的来源文件类型: {resolved.suffix}")
        return resolved.parent, [resolved]
    if not resolved.is_dir():
        raise ValueError(f"输入不存在: {resolved}")
    excluded_output_dir: Path | None = None
    try:
        output_resolved.relative_to(resolved)
        if output_resolved.parent != resolved:
            excluded_output_dir = output_resolved.parent
    except ValueError:
        pass
    sources = []
    for path in resolved.rglob("*"):
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
        relative = path.relative_to(resolved)
        if any(part.startswith(".") or part in {"__pycache__", "node_modules", "archive"} for part in relative.parts):
            continue
        sources.append(path_resolved)
    sources.sort(key=lambda item: item.relative_to(resolved).as_posix())
    if not sources:
        raise ValueError("输入范围内没有 .md 或 .txt 来源文件")
    return resolved, sources


def build_index(input_path: Path, output_path: Path) -> dict:
    input_root, sources = discover_sources(input_path, output_path)
    block_ordinal = 0
    source_records = []
    for source_ordinal, path in enumerate(sources, 1):
        source_id = f"SRC-{source_ordinal:03d}"
        relative = path.relative_to(input_root).as_posix()
        blocks = []
        for kind, start_line, end_line, text in iter_file_blocks(path):
            block_ordinal += 1
            block_id = f"BLK-{block_ordinal:05d}"
            source_ref = f"{source_id}#L{start_line:04d}-L{end_line:04d}"
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
    result = {"schema_version": "1.1", "sources": source_records}
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为课程来源建立稳定段落级 source-index.json")
    parser.add_argument("--input", required=True, help="单个 .md/.txt 文件或来源目录")
    parser.add_argument("--output", required=True, help="source-index.json 输出路径")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = build_index(Path(args.input), Path(args.output))
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
                "output": str(Path(args.output).expanduser().resolve()),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
