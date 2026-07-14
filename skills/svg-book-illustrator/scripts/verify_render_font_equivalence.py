#!/usr/bin/env python3
"""Verify that the controlled external font stylesheet preserves legacy pixels."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
FONT_STYLESHEET = SKILL_ROOT / "assets" / "render-fonts.css"
CONTROLLED_RENDERER = SCRIPTS_DIR / "render_svg.py"
GENERATORS = tuple(sorted(SCRIPTS_DIR.glob("gen-*.py")))
CANVAS_WIDTH = "720"


def require_program(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise SystemExit(f"缺少依赖: {name}（未执行安装）")
    return executable


def run_checked(command: list[str], label: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"{label}失败（exit={result.returncode}）\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def embed_legacy_style(svg_text: str, stylesheet: str) -> str:
    """Build a temporary legacy-style baseline without changing source SVG files."""
    opening_tag = re.search(r"<svg\b[^>]*>", svg_text, flags=re.DOTALL)
    if opening_tag is None:
        raise SystemExit("生成产物缺少 <svg> 根元素")
    insertion = f"\n<style>\n{stylesheet.rstrip()}\n</style>"
    return svg_text[: opening_tag.end()] + insertion + svg_text[opening_tag.end() :]


def remove_figure_id(svg_text: str) -> str:
    """Build a temporary pre-identity baseline for metadata pixel comparison."""
    updated, replacements = re.subn(
        r'\sdata-figure-id="[^"]+"',
        "",
        svg_text,
        count=1,
    )
    if replacements != 1:
        raise SystemExit("生成产物缺少唯一 data-figure-id，无法构造身份基线")
    return updated


def compare_ae(magick: str, expected: Path, actual: Path, label: str) -> str:
    comparison = subprocess.run(
        [
            magick,
            "compare",
            "-metric",
            "AE",
            str(expected),
            str(actual),
            "null:",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    metric = (comparison.stderr or comparison.stdout).strip()
    metric_match = re.match(r"^([0-9]+(?:\.[0-9]+)?)", metric)
    metric_value = float(metric_match.group(1)) if metric_match else None
    if comparison.returncode != 0 or metric_value != 0:
        raise SystemExit(
            f"{label}: 像素不等价（AE={metric or 'unknown'}, "
            f"exit={comparison.returncode}）"
        )
    return metric


def main() -> int:
    if not FONT_STYLESHEET.is_file():
        raise SystemExit(f"受控字体样式不存在: {FONT_STYLESHEET}")
    if not CONTROLLED_RENDERER.is_file():
        raise SystemExit(f"受控渲染器不存在: {CONTROLLED_RENDERER}")
    if not GENERATORS:
        raise SystemExit("未找到 gen-*.py 生成器")

    rsvg_convert = require_program("rsvg-convert")
    magick = require_program("magick")
    stylesheet = FONT_STYLESHEET.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="svg-font-equivalence-") as tmpdir:
        temp_root = Path(tmpdir)
        for generator in GENERATORS:
            stem = generator.stem
            source_svg = temp_root / f"{stem}.svg"
            baseline_svg = temp_root / f"{stem}.legacy.svg"
            without_id_svg = temp_root / f"{stem}.without-id.svg"
            baseline_png = temp_root / f"{stem}.legacy.png"
            without_id_png = temp_root / f"{stem}.without-id.png"
            controlled_png = temp_root / f"{stem}.controlled.png"

            run_checked(
                [sys.executable, str(generator), str(source_svg)],
                f"{generator.name} 生成",
            )
            source_text = source_svg.read_text(encoding="utf-8")
            baseline_svg.write_text(embed_legacy_style(source_text, stylesheet), encoding="utf-8")
            without_id_svg.write_text(remove_figure_id(source_text), encoding="utf-8")
            run_checked(
                [
                    rsvg_convert,
                    "-w",
                    CANVAS_WIDTH,
                    str(baseline_svg),
                    "-o",
                    str(baseline_png),
                ],
                f"{generator.name} 旧式基线渲染",
            )
            run_checked(
                [sys.executable, str(CONTROLLED_RENDERER), str(source_svg), str(controlled_png)],
                f"{generator.name} 受控渲染",
            )
            run_checked(
                [
                    sys.executable,
                    str(CONTROLLED_RENDERER),
                    str(without_id_svg),
                    str(without_id_png),
                ],
                f"{generator.name} 无身份基线渲染",
            )

            font_metric = compare_ae(
                magick,
                baseline_png,
                controlled_png,
                f"{generator.name} 字体交付方式",
            )
            figure_id_metric = compare_ae(
                magick,
                without_id_png,
                controlled_png,
                f"{generator.name} 身份元数据",
            )
            print(
                f"{generator.name}: font_delivery_AE={font_metric}; "
                f"figure_id_AE={figure_id_metric}"
            )

    print(
        f"PASS: {len(GENERATORS)}/{len(GENERATORS)} generators font- and identity-equivalent"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
