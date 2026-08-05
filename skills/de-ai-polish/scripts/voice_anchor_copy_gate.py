#!/usr/bin/env python3
"""阻断改写后相对源稿新出现的 VoiceAnchor 长连续重合。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


CONSTRAINT_ID = "NO-NEW-VOICE-ANCHOR-COPY"
IMAGE_LINE = re.compile(r"^\s*!\[[^\]]*\]\(.+\)\s*$")


def markdown_paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    buffer: list[str] = []
    in_fence = False
    in_frontmatter = text.startswith("---\n")

    def flush() -> None:
        nonlocal buffer
        if buffer:
            paragraph = " ".join(item.strip() for item in buffer).strip()
            if paragraph:
                paragraphs.append(paragraph)
        buffer = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if line_number == 1 and stripped == "---":
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped or stripped.startswith("#") or IMAGE_LINE.match(line):
            flush()
            continue
        buffer.append(line)
    flush()
    return paragraphs


def normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(
        char
        for char in normalized
        if not char.isspace() and unicodedata.category(char)[0] not in {"P", "S"}
    )


def normalized_paragraphs(path: Path) -> list[str]:
    return [
        value
        for value in (normalize(item) for item in markdown_paragraphs(path.read_text(encoding="utf-8")))
        if value
    ]


def ngrams(paragraphs: list[str], size: int) -> set[str]:
    return {
        paragraph[index : index + size]
        for paragraph in paragraphs
        for index in range(max(0, len(paragraph) - size + 1))
    }


def sample_index(paragraphs: list[str], size: int) -> dict[str, list[tuple[int, int]]]:
    index: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for paragraph_index, paragraph in enumerate(paragraphs):
        for position in range(max(0, len(paragraph) - size + 1)):
            gram = paragraph[position : position + size]
            if len(index[gram]) < 16:
                index[gram].append((paragraph_index, position))
    return index


def expand_match(final: str, final_pos: int, sample: str, sample_pos: int, size: int) -> tuple[int, int, int]:
    left = 0
    while final_pos - left > 0 and sample_pos - left > 0:
        if final[final_pos - left - 1] != sample[sample_pos - left - 1]:
            break
        left += 1
    right = size
    while final_pos + right < len(final) and sample_pos + right < len(sample):
        if final[final_pos + right] != sample[sample_pos + right]:
            break
        right += 1
    return final_pos - left, sample_pos - left, left + right


def check(source: Path, final: Path, sample: Path, min_chars: int) -> tuple[bool, dict[str, object]]:
    source_paragraphs = normalized_paragraphs(source)
    final_paragraphs = normalized_paragraphs(final)
    sample_paragraphs = normalized_paragraphs(sample)
    source_grams = ngrams(source_paragraphs, min_chars)
    indexed_sample = sample_index(sample_paragraphs, min_chars)
    matches: dict[tuple[int, int, int, int, int], dict[str, object]] = {}

    for final_index, final_paragraph in enumerate(final_paragraphs):
        for final_pos in range(max(0, len(final_paragraph) - min_chars + 1)):
            gram = final_paragraph[final_pos : final_pos + min_chars]
            if gram in source_grams or gram not in indexed_sample:
                continue
            for sample_index_value, sample_pos in indexed_sample[gram]:
                final_start, sample_start, length = expand_match(
                    final_paragraph,
                    final_pos,
                    sample_paragraphs[sample_index_value],
                    sample_pos,
                    min_chars,
                )
                matched_text = final_paragraph[final_start : final_start + length]
                key = (final_index, final_start, sample_index_value, sample_start, length)
                matches[key] = {
                    "final_paragraph": final_index + 1,
                    "sample_paragraph": sample_index_value + 1,
                    "char_length": length,
                    "overlap_sha256": hashlib.sha256(matched_text.encode("utf-8")).hexdigest(),
                }

    findings = sorted(
        matches.values(),
        key=lambda item: (-int(item["char_length"]), int(item["final_paragraph"])),
    )[:20]
    common = {
        "constraint_id": CONSTRAINT_ID,
        "minimum_effective_chars": min_chars,
        "finding_count": len(findings),
        "findings": findings,
        "privacy": "输出只含位置、长度和重合片段哈希，不打印样本文字",
        "boundary": "只检测归一化后的连续重合；不证明没有同义复刻、结构模仿或事实泄漏",
    }
    if findings:
        return False, {"failed_constraint_ids": [CONSTRAINT_ID], **common}
    return True, {"passed_constraint_ids": [CONSTRAINT_ID], **common}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--final", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--min-chars", type=int, default=14)
    args = parser.parse_args()
    for path in (args.source, args.final, args.sample):
        if not path.is_file():
            parser.error(f"文件不存在: {path}")
    if args.min_chars < 8:
        parser.error("--min-chars 不能小于 8")
    passed, result = check(args.source, args.final, args.sample, args.min_chars)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
