#!/usr/bin/env python3
"""Shared output and stable figure-id parsing for SVG generators."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


FIGURE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def valid_figure_id(value: str) -> str:
    if not FIGURE_ID_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "必须是 1-128 位安全值，仅含字母、数字、点、下划线或连字符"
        )
    return value


def parse_output_and_figure_id(default_output: str) -> tuple[Path, str]:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", type=Path, default=Path(default_output))
    parser.add_argument(
        "--figure-id",
        type=valid_figure_id,
        help="Stable project-unique data-figure-id; defaults to the output filename stem.",
    )
    args = parser.parse_args()
    candidate = args.figure_id if args.figure_id is not None else args.output.stem
    try:
        figure_id = valid_figure_id(candidate)
    except argparse.ArgumentTypeError as exc:
        parser.error(
            f"无法从输出文件名得到安全 data-figure-id（{candidate!r}）：{exc}；"
            "请显式传入 --figure-id"
        )
    return args.output, figure_id
