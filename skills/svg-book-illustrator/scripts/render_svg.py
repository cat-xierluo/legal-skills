#!/usr/bin/env python3
"""Render an SVG with the skill's controlled external font stylesheet."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
FONT_STYLESHEET = SKILL_ROOT / "assets" / "render-fonts.css"
CANVAS_WIDTH = "720"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use librsvg and the controlled font stylesheet to render SVG to PNG."
    )
    parser.add_argument("input", type=Path, help="Input SVG path")
    parser.add_argument("output", type=Path, help="Output PNG path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.is_file():
        raise SystemExit(f"输入 SVG 不存在: {args.input}")
    if not FONT_STYLESHEET.is_file():
        raise SystemExit(f"受控字体样式不存在: {FONT_STYLESHEET}")

    renderer = shutil.which("rsvg-convert")
    if renderer is None:
        raise SystemExit("缺少依赖: rsvg-convert（未执行安装）")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        renderer,
        "--stylesheet",
        str(FONT_STYLESHEET),
        "-w",
        CANVAS_WIDTH,
        str(args.input),
        "-o",
        str(args.output),
    ]
    subprocess.run(command, check=True)
    if not args.output.is_file() or args.output.stat().st_size == 0:
        raise SystemExit(f"渲染失败或输出为空: {args.output}")
    print(f"rendered {args.input} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
