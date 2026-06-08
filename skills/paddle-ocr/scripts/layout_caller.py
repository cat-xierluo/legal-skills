#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "httpx>=0.27.0",
# ]
# ///

"""底层接口调用脚本：输出稳定 JSON envelope。"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import parse_document  # noqa: E402


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    short_id = uuid.uuid4().hex[:8]
    return (
        Path(tempfile.gettempdir())
        / "paddleocr"
        / "legal-doc-parsing"
        / f"result_{timestamp}_{short_id}.json"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="调用 PaddleOCR 接口并输出稳定 JSON envelope"
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--file-path", help="本地 PDF / 图片路径")
    source_group.add_argument("--file-url", help="远程 PDF / 图片 URL")
    parser.add_argument(
        "--file-type",
        type=int,
        choices=[0, 1],
        help="显式指定文件类型：0=PDF，1=图片",
    )
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument("--stdout", action="store_true", help="直接打印 JSON")
    output_group.add_argument("--output", help="写入指定 JSON 文件")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    envelope = parse_document(
        file_path=args.file_path,
        file_url=args.file_url,
        file_type=args.file_type,
    )
    json_text = json.dumps(
        envelope,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
    )

    if args.stdout:
        print(json_text)
    else:
        output_path = Path(args.output).expanduser().resolve() if args.output else default_output_path()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_text, encoding="utf-8")
        print(f"Result saved to: {output_path}", file=sys.stderr)

    return 0 if envelope.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
