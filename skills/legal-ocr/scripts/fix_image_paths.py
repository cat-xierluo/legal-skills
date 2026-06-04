#!/usr/bin/env python3
"""Fix broken image src paths in legal-ocr markdown output.

When the PaddleOCR backend returns images, the markdown text keeps the
original `imgs/img_in_image_box_*.jpg` references, but the script saves
images with batch-based names like `1-40_001.jpg`. This script reads the
result.json from the archive, builds a source→filename map, and replaces
the broken references in the markdown.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def build_map(result_json_path: Path) -> dict[str, str]:
    data = json.loads(result_json_path.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for image in data.get("images", []):
        source = image.get("source")
        filename = image.get("filename")
        if source and filename:
            mapping[source] = filename
    return mapping


def fix_markdown(md_path: Path, mapping: dict[str, str]) -> tuple[int, int]:
    text = md_path.read_text(encoding="utf-8")
    pattern = re.compile(r"imgs/[A-Za-z0-9_\-]+\.(?:jpg|jpeg|png|gif|webp)")
    replaced = 0
    missing = 0

    def sub(match: re.Match[str]) -> str:
        nonlocal replaced, missing
        key = match.group(0)
        if key in mapping:
            replaced += 1
            return mapping[key]
        missing += 1
        return key

    new_text = pattern.sub(sub, text)
    if new_text != text:
        md_path.write_text(new_text, encoding="utf-8")
    return replaced, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path, help="Path to the markdown file to fix")
    parser.add_argument(
        "--result-json",
        type=Path,
        required=True,
        help="Path to result.json from the legal-ocr archive",
    )
    args = parser.parse_args()

    if not args.markdown.exists():
        print(f"Markdown not found: {args.markdown}", file=sys.stderr)
        return 1
    if not args.result_json.exists():
        print(f"result.json not found: {args.result_json}", file=sys.stderr)
        return 1

    mapping = build_map(args.result_json)
    if not mapping:
        print("No image mapping found in result.json", file=sys.stderr)
        return 1

    replaced, missing = fix_markdown(args.markdown, mapping)
    print(f"Image references replaced: {replaced}")
    if missing:
        print(f"Unresolved references: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
