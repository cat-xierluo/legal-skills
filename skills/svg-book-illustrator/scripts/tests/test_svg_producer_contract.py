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
RENDER_FONT_CSS = SKILL_ROOT / "assets" / "render-fonts.css"
RSVG_WRAPPER = SCRIPTS_DIR / "render_svg.py"
RENDER_EQUIVALENCE_CHECK = SCRIPTS_DIR / "verify_render_font_equivalence.py"
BROWSER_RENDERER = SCRIPTS_DIR / "svg2png.js"


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
        self.assertEqual(min_x, 0, f"{source}: viewBox min-x 必须为 0")
        self.assertEqual(min_y, 0, f"{source}: viewBox min-y 必须为 0")
        self.assertEqual(view_width, 720, f"{source}: viewBox 宽度必须固定为 720")
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
            self.assertNotIn("style", attributes, f"{source}: 不得使用 style 属性")
            self.assertNotIn("font-family", attributes, f"{source}: 字体只能来自受控外部 CSS")
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


class ContractRuleTests(SvgContractMixin, unittest.TestCase):
    def test_known_bad_contract_variants_are_rejected(self) -> None:
        bad_svgs = {
            "malformed XML": '<svg viewBox="0 0 720 400" width="720" height="400">',
            "missing viewBox": '<svg width="720" height="400"></svg>',
            "missing dimensions": '<svg viewBox="0 0 720 400"></svg>',
            "noncanonical canvas geometry": (
                '<svg viewBox="10 20 860 400" width="860" height="400"></svg>'
            ),
            "style block": (
                '<svg viewBox="0 0 720 400" width="720" height="400">'
                '<style>text{fill:#000}</style></svg>'
            ),
            "inline style attribute": (
                '<svg viewBox="0 0 720 400" width="720" height="400">'
                '<text x="40" y="40" style="fill:#2D3436">文本</text></svg>'
            ),
            "root font-family": (
                '<svg viewBox="0 0 720 400" width="720" height="400" font-family="sans-serif"></svg>'
            ),
            "element font-family": (
                '<svg viewBox="0 0 720 400" width="720" height="400">'
                '<text x="40" y="40" font-family="sans-serif">文本</text></svg>'
            ),
            "class selector": (
                '<svg viewBox="0 0 720 400" width="720" height="400">'
                '<rect class="node" x="40" y="40" width="100" height="40"/></svg>'
            ),
            "CSS variable": (
                '<svg viewBox="0 0 720 400" width="720" height="400">'
                '<rect x="40" y="40" width="100" height="40" fill="var(--node-fill)"/></svg>'
            ),
            "currentColor": (
                '<svg viewBox="0 0 720 400" width="720" height="400">'
                '<path d="M0 0L10 10" stroke="currentColor"/></svg>'
            ),
            "canvas background rect": (
                '<svg viewBox="0 0 720 400" width="720" height="400">'
                '<rect width="720" height="400" fill="#FFFFFF"/></svg>'
            ),
        }
        for rule, svg_text in bad_svgs.items():
            with self.subTest(rule=rule):
                with self.assertRaises(AssertionError):
                    self.assert_svg_contract(svg_text, rule)


class RenderFontSourceTests(unittest.TestCase):
    def test_all_renderers_share_one_controlled_font_stylesheet(self) -> None:
        self.assertTrue(RENDER_FONT_CSS.is_file(), "缺少受控字体样式源")
        self.assertTrue(RSVG_WRAPPER.is_file(), "缺少受控 librsvg wrapper")
        self.assertTrue(RENDER_EQUIVALENCE_CHECK.is_file(), "缺少字体像素等价验证器")

        css_files = tuple(
            path
            for path in SKILL_ROOT.rglob("*.css")
            if "node_modules" not in path.parts
        )
        self.assertEqual(css_files, (RENDER_FONT_CSS,), "字体 CSS 必须保持单一权威源")
        font_css = RENDER_FONT_CSS.read_text(encoding="utf-8")
        self.assertIn("font-family", font_css)
        self.assertIn("text", font_css)

        wrapper = RSVG_WRAPPER.read_text(encoding="utf-8")
        equivalence_check = RENDER_EQUIVALENCE_CHECK.read_text(encoding="utf-8")
        browser_renderer = BROWSER_RENDERER.read_text(encoding="utf-8")
        for source_name, source_text in (
            ("render_svg.py", wrapper),
            ("verify_render_font_equivalence.py", equivalence_check),
            ("svg2png.js", browser_renderer),
        ):
            self.assertIn("render-fonts.css", source_text, f"{source_name} 未读取统一字体 CSS")
            self.assertNotIn("font-family", source_text, f"{source_name} 不得复制字体栈")

        self.assertIn("--stylesheet", wrapper)
        self.assertIn('"720"', wrapper)
        self.assertIn("renderFontCss", browser_renderer)
        self.assertIn("document.fonts.ready", browser_renderer)


if __name__ == "__main__":
    unittest.main()
