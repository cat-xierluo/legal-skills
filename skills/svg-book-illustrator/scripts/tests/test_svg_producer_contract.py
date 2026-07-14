#!/usr/bin/env python3
"""Regression contract for SVG producers and published template examples."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
LAYOUT_TEMPLATES = SKILL_ROOT / "references" / "layout-templates.md"
GENERATORS = tuple(path.name for path in sorted(SCRIPTS_DIR.glob("gen-*.py")))


def local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def parse_number(value: str) -> float:
    normalized = value.strip()
    if normalized.endswith("px"):
        normalized = normalized[:-2]
    return float(normalized)


class SvgContractMixin:
    def assert_svg_contract(self, svg_text: str, source: str) -> None:
        try:
            root = ET.fromstring(svg_text)
        except ET.ParseError as exc:
            self.fail(f"{source}: XML 不可解析：{exc}")

        self.assertEqual(local_name(root.tag), "svg", f"{source}: 根元素必须是 <svg>")

        view_box = root.attrib.get("viewBox")
        self.assertIsNotNone(view_box, f"{source}: SVG 根缺少 viewBox")
        try:
            min_x, min_y, view_width, view_height = map(float, view_box.split())
        except (AttributeError, TypeError, ValueError):
            self.fail(f"{source}: viewBox 必须包含 4 个数值")
        self.assertGreater(view_width, 0, f"{source}: viewBox 宽度必须大于 0")
        self.assertGreater(view_height, 0, f"{source}: viewBox 高度必须大于 0")

        self.assertIn("width", root.attrib, f"{source}: SVG 根缺少 width")
        self.assertIn("height", root.attrib, f"{source}: SVG 根缺少 height")
        try:
            width = parse_number(root.attrib["width"])
            height = parse_number(root.attrib["height"])
        except ValueError:
            self.fail(f"{source}: width/height 必须是显式数值尺寸")
        self.assertAlmostEqual(width, view_width, msg=f"{source}: width 必须与 viewBox 宽度一致")
        self.assertAlmostEqual(height, view_height, msg=f"{source}: height 必须与 viewBox 高度一致")

        root_attributes = {local_name(key): value for key, value in root.attrib.items()}
        self.assertNotIn("font-family", root_attributes, f"{source}: SVG 根不得设置 font-family")
        for key, value in root_attributes.items():
            self.assertNotIn("background", key.lower(), f"{source}: SVG 根不得设置背景属性")
            self.assertNotIn("background", value.lower(), f"{source}: SVG 根不得设置背景样式")

        for element in root.iter():
            tag = local_name(element.tag)
            self.assertNotEqual(tag, "style", f"{source}: 不得包含 <style> 块")

            attributes = {local_name(key): value for key, value in element.attrib.items()}
            self.assertNotIn("class", attributes, f"{source}: 不得用 class 引用样式")
            serialized_values = list(attributes.values())
            if element.text:
                serialized_values.append(element.text)
            for value in serialized_values:
                lowered = value.lower()
                self.assertNotIn("var(--", lowered, f"{source}: 不得使用 CSS 变量")
                self.assertNotIn("currentcolor", lowered, f"{source}: 颜色必须使用显式内联值")

            if tag != "rect":
                continue
            fill = attributes.get("fill", "").strip().lower()
            fill_opacity = attributes.get("fill-opacity", "1").strip()
            if fill in {"none", "transparent"} or fill_opacity in {"0", "0.0"}:
                continue

            x = parse_number(attributes.get("x", "0"))
            y = parse_number(attributes.get("y", "0"))
            rect_width = attributes.get("width", "0").strip()
            rect_height = attributes.get("height", "0").strip()
            covers_width = rect_width == "100%" or parse_number(rect_width) >= view_width
            covers_height = rect_height == "100%" or parse_number(rect_height) >= view_height
            covers_origin = x <= min_x and y <= min_y
            self.assertFalse(
                covers_origin and covers_width and covers_height,
                f"{source}: 不得用全画布 <rect> 绘制背景",
            )


class GeneratorContractTests(SvgContractMixin, unittest.TestCase):
    def test_all_generators_emit_contract_compliant_svg(self) -> None:
        self.assertGreaterEqual(len(GENERATORS), 5, "不得静默遗漏或删除现有 SVG 生成器")
        with tempfile.TemporaryDirectory() as tmpdir:
            for generator_name in GENERATORS:
                with self.subTest(generator=generator_name):
                    output = Path(tmpdir) / f"{Path(generator_name).stem}.svg"
                    result = subprocess.run(
                        [sys.executable, str(SCRIPTS_DIR / generator_name), str(output)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    self.assertEqual(
                        result.returncode,
                        0,
                        f"{generator_name}: 生成失败\nstdout: {result.stdout}\nstderr: {result.stderr}",
                    )
                    self.assertTrue(output.is_file(), f"{generator_name}: 未生成输出文件")
                    self.assert_svg_contract(output.read_text(encoding="utf-8"), generator_name)


class TemplateContractTests(SvgContractMixin, unittest.TestCase):
    def test_all_published_svg_code_blocks_follow_contract(self) -> None:
        markdown = LAYOUT_TEMPLATES.read_text(encoding="utf-8")
        blocks = re.findall(r"```svg\s*\n(.*?)\n```", markdown, flags=re.DOTALL)
        self.assertGreaterEqual(len(blocks), 10, "layout-templates.md 应保留全部 SVG 模板示例")
        for index, svg_text in enumerate(blocks, start=1):
            with self.subTest(svg_block=index):
                self.assert_svg_contract(svg_text, f"layout-templates.md svg block #{index}")


if __name__ == "__main__":
    unittest.main()
