#!/usr/bin/env python3
"""Regression contract for SVG producers and published template examples."""

from __future__ import annotations

import math
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
FIGURE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
OVERLAP_CONTAINER_TAGS = frozenset({"rect", "circle", "ellipse", "polygon", "path"})
OVERLAP_CONTRACT_ATTRIBUTES = frozenset({
    "id",
    "data-overlap-role",
    "data-overlap-note",
    "data-allow-overlap",
    "data-allow-overlap-note",
})
GENERIC_CONTAINER_NOTES = frozenset({
    "允许重叠",
    "允许覆盖",
    "容器",
    "container",
    "overlap",
    "allow overlap",
})
CONTAINER_RELATION_TERMS = (
    "承载",
    "容纳",
    "包含",
    "包裹",
    "收纳",
    "承托",
    "contains",
    "hosts",
    "encloses",
    "wraps",
)
NON_LITERAL_OR_INVISIBLE_FILLS = frozenset({
    "none",
    "transparent",
    "inherit",
    "initial",
    "unset",
    "revert",
    "revert-layer",
    "currentcolor",
    "context-fill",
    "context-stroke",
})


def local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def parse_number(value: str) -> float:
    normalized = value.strip()
    if normalized.endswith("px"):
        normalized = normalized[:-2]
    return float(normalized)


def parse_css_alpha(value: str) -> float:
    normalized = value.strip()
    if normalized.endswith("%"):
        alpha = float(normalized[:-1]) / 100
    else:
        alpha = float(normalized)
    if not math.isfinite(alpha) or not 0 <= alpha <= 1:
        raise ValueError("alpha must be finite and between 0 and 1")
    return alpha


def parse_css_channel(value: str, maximum: float) -> float:
    normalized = value.strip()
    if normalized.endswith("%"):
        channel = float(normalized[:-1])
        if not math.isfinite(channel) or not 0 <= channel <= 100:
            raise ValueError("percentage channel must be between 0 and 100")
        return channel
    channel = float(normalized)
    if not math.isfinite(channel) or not 0 <= channel <= maximum:
        raise ValueError(f"channel must be between 0 and {maximum}")
    return channel


def parse_css_hue(value: str) -> float:
    normalized = value.strip()
    match = re.fullmatch(
        r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)(deg|grad|rad|turn)?",
        normalized,
    )
    if not match:
        raise ValueError("invalid hue")
    hue = float(match.group(1))
    if not math.isfinite(hue):
        raise ValueError("hue must be finite")
    return hue


def parse_css_color_function(function_name: str, body: str) -> float:
    if body.count("/") > 1:
        raise ValueError("multiple alpha separators")
    if "/" in body:
        channels_text, alpha_text = body.rsplit("/", 1)
        if "," in channels_text:
            raise ValueError("slash alpha syntax requires space-separated channels")
        alpha = parse_css_alpha(alpha_text)
    else:
        channels_text = body
        alpha = 1.0

    if "," in channels_text:
        channels = [part.strip() for part in channels_text.split(",")]
    else:
        channels = channels_text.split()
    if any(not channel for channel in channels):
        raise ValueError("empty color channel")

    if "/" not in body and function_name in {"rgba", "hsla"}:
        if "," not in channels_text:
            raise ValueError("legacy alpha syntax requires comma-separated channels")
        if len(channels) != 4:
            raise ValueError("legacy alpha function requires four comma channels")
        alpha = parse_css_alpha(channels.pop())
    if len(channels) != 3:
        raise ValueError("color function requires exactly three channels")

    if function_name in {"rgb", "rgba"}:
        for channel in channels:
            parse_css_channel(channel, 255)
    else:
        parse_css_hue(channels[0])
        for channel in channels[1:]:
            if not channel.strip().endswith("%"):
                raise ValueError("hsl saturation and lightness must be percentages")
            parse_css_channel(channel, 100)
    return alpha


def has_statically_visible_fill(value: str) -> bool:
    fill = value.strip().casefold()
    if not fill or fill in NON_LITERAL_OR_INVISIBLE_FILLS:
        return False

    if fill.startswith("#"):
        if not re.fullmatch(r"#[0-9a-f]+", fill):
            return False
        if len(fill) in {4, 7}:
            return True
        if len(fill) == 5:
            return int(fill[-1], 16) > 0
        if len(fill) == 9:
            return int(fill[-2:], 16) > 0
        return False

    color_function = re.fullmatch(r"(rgb|rgba|hsl|hsla)\(([^()]*)\)", fill)
    if color_function:
        function_name, body = color_function.groups()
        try:
            return parse_css_color_function(function_name, body) > 0
        except ValueError:
            return False

    # Restrict container fills to auditable hex/rgb/hsl literals. Named colors,
    # paint servers, variables and inheritance would require a CSS renderer to
    # distinguish a visible value from an invalid or transparent one.
    return False


class SvgContractMixin:
    def assert_svg_contract(self, svg_text: str, source: str) -> str:
        try:
            root = ET.fromstring(svg_text)
        except ET.ParseError as exc:
            self.fail(f"{source}: XML 不可解析：{exc}")

        self.assertEqual(local_name(root.tag), "svg", f"{source}: 根元素必须是 <svg>")

        figure_id = root.attrib.get("data-figure-id")
        self.assertIsNotNone(figure_id, f"{source}: SVG 根缺少 data-figure-id")
        self.assertRegex(
            figure_id or "",
            FIGURE_ID_PATTERN,
            f"{source}: data-figure-id 必须是非空安全值",
        )

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

        element_ids: set[str] = set()
        for element in root.iter():
            tag = local_name(element.tag)
            self.assertNotEqual(tag, "style", f"{source}: 不得包含 <style> 块")

            attributes = {local_name(key): value for key, value in element.attrib.items()}
            for raw_name in element.attrib:
                name = local_name(raw_name)
                if name in OVERLAP_CONTRACT_ATTRIBUTES:
                    self.assertEqual(
                        raw_name,
                        name,
                        f"{source}: {name} 必须是无 namespace 的原生 SVG 属性",
                    )
            element_id = element.attrib.get("id")
            if element_id is not None:
                self.assertNotIn(
                    element_id,
                    element_ids,
                    f"{source}: 元素 id 必须在单张 SVG 内唯一：{element_id}",
                )
                element_ids.add(element_id)
            self.assertNotIn(
                "data-allow-overlap",
                attributes,
                f"{source}: 候选 SVG 不得自发声明通用重叠豁免",
            )
            self.assertNotIn(
                "data-allow-overlap-note",
                attributes,
                f"{source}: 候选 SVG 不得保留通用重叠豁免说明",
            )
            overlap_role = element.attrib.get("data-overlap-role")
            overlap_note_attribute = element.attrib.get("data-overlap-note")
            if overlap_role is None:
                self.assertIsNone(
                    overlap_note_attribute,
                    f"{source}: data-overlap-note 不能脱离 container role 单独存在",
                )
            if overlap_role is not None:
                self.assertEqual(
                    overlap_role,
                    "container",
                    f"{source}: data-overlap-role 只允许窄语义 container，不能声明装饰或任意豁免",
                )
                self.assertIn(
                    tag,
                    OVERLAP_CONTAINER_TAGS,
                    f"{source}: container 只能标在 writing-reviewer 可审计的外层 area shape",
                )
                container_id = element.attrib.get("id", "")
                self.assertRegex(
                    container_id,
                    FIGURE_ID_PATTERN,
                    f"{source}: container 必须绑定非空安全稳定 id",
                )
                overlap_note = (overlap_note_attribute or "").strip()
                normalized_note = " ".join(overlap_note.casefold().split())
                self.assertGreaterEqual(
                    len(overlap_note),
                    6,
                    f"{source}: container note 必须具体说明外层承载对象",
                )
                self.assertNotIn(
                    normalized_note,
                    GENERIC_CONTAINER_NOTES,
                    f"{source}: container note 不能只写通用“允许重叠/覆盖”",
                )
                self.assertTrue(
                    any(term in normalized_note for term in CONTAINER_RELATION_TERMS),
                    f"{source}: container note 必须明确说明外层与内层的承载关系",
                )
                fill = element.attrib.get("fill", "")
                self.assertTrue(
                    has_statically_visible_fill(fill),
                    f"{source}: container 必须用可静态证明非透明的显式 fill",
                )
                for opacity_name in ("opacity", "fill-opacity"):
                    opacity = element.attrib.get(opacity_name, "1").strip()
                    try:
                        opacity_value = float(opacity)
                    except ValueError:
                        self.fail(f"{source}: container {opacity_name} 必须是数值")
                    self.assertGreater(
                        opacity_value,
                        0,
                        f"{source}: container {opacity_name} 必须大于 0",
                    )
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
        return figure_id

    def assert_unique_figure_ids(self, entries: list[tuple[str, str]]) -> None:
        seen: dict[str, str] = {}
        for source, figure_id in entries:
            self.assertNotIn(
                figure_id,
                seen,
                f"{source}: data-figure-id 与 {seen.get(figure_id)} 重复：{figure_id}",
            )
            seen[figure_id] = source


class GeneratorContractTests(SvgContractMixin, unittest.TestCase):
    def test_all_generators_emit_contract_compliant_svg(self) -> None:
        self.assertGreaterEqual(len(GENERATORS), 5, "不得静默遗漏或删除现有 SVG 生成器")
        figure_ids: list[tuple[str, str]] = []
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
                    figure_id = self.assert_svg_contract(
                        output.read_text(encoding="utf-8"), generator_name
                    )
                    self.assertEqual(figure_id, output.stem, f"{generator_name}: 默认 ID 应来自输出 stem")
                    figure_ids.append((generator_name, figure_id))

                    explicit_output = Path(tmpdir) / f"explicit-{Path(generator_name).stem}.svg"
                    explicit_id = f"fig-ch01-s1-{len(figure_ids):02d}"
                    explicit_result = subprocess.run(
                        [
                            sys.executable,
                            str(SCRIPTS_DIR / generator_name),
                            str(explicit_output),
                            "--figure-id",
                            explicit_id,
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    self.assertEqual(explicit_result.returncode, 0, explicit_result.stderr)
                    explicit_root = ET.fromstring(explicit_output.read_text(encoding="utf-8"))
                    self.assertEqual(explicit_root.attrib.get("data-figure-id"), explicit_id)

                    for invalid_index, invalid_id in enumerate(("", "unsafe figure id"), start=1):
                        invalid_output = (
                            Path(tmpdir)
                            / f"invalid-{invalid_index}-{Path(generator_name).stem}.svg"
                        )
                        invalid_result = subprocess.run(
                            [
                                sys.executable,
                                str(SCRIPTS_DIR / generator_name),
                                str(invalid_output),
                                "--figure-id",
                                invalid_id,
                            ],
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=15,
                        )
                        self.assertNotEqual(invalid_result.returncode, 0)
                        self.assertFalse(invalid_output.exists())

                    unsafe_stem_output = Path(tmpdir) / f"unsafe {Path(generator_name).stem}.svg"
                    unsafe_stem_result = subprocess.run(
                        [
                            sys.executable,
                            str(SCRIPTS_DIR / generator_name),
                            str(unsafe_stem_output),
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    self.assertNotEqual(unsafe_stem_result.returncode, 0)
                    self.assertFalse(unsafe_stem_output.exists())
        self.assert_unique_figure_ids(figure_ids)


class TemplateContractTests(SvgContractMixin, unittest.TestCase):
    def test_all_published_svg_code_blocks_follow_contract(self) -> None:
        markdown = LAYOUT_TEMPLATES.read_text(encoding="utf-8")
        blocks = re.findall(r"```svg\s*\n(.*?)\n```", markdown, flags=re.DOTALL)
        self.assertGreaterEqual(len(blocks), 10, "layout-templates.md 应保留全部 SVG 模板示例")
        figure_ids: list[tuple[str, str]] = []
        for index, svg_text in enumerate(blocks, start=1):
            with self.subTest(svg_block=index):
                source = f"layout-templates.md svg block #{index}"
                figure_id = self.assert_svg_contract(svg_text, source)
                self.assertTrue(figure_id.startswith("fig-template-"), source)
                figure_ids.append((source, figure_id))
        self.assert_unique_figure_ids(figure_ids)


class ContractRuleTests(SvgContractMixin, unittest.TestCase):
    def test_shape_container_declarations_are_narrow_and_auditable(self) -> None:
        valid_root = (
            '<svg viewBox="0 0 720 400" width="720" height="400" '
            'data-figure-id="fig-test">'
        )
        valid = (
            valid_root
            + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
            'fill="#EDF2F7" data-overlap-role="container" '
            'data-overlap-note="外层卡片承载内层信息卡"/>'
            '<rect x="60" y="70" width="180" height="90" fill="#D6E4F0"/>'
            '</svg>'
        )
        self.assertEqual(self.assert_svg_contract(valid, "valid container"), "fig-test")
        for label, fill in (
            ("valid rgba container", "rgba(237,242,247,0.2)"),
            ("valid hsl container", "hsl(210 22% 95% / 20%)"),
            ("valid alpha hex container", "#EDF2F701"),
        ):
            with self.subTest(fill=fill):
                variant = (
                    valid_root
                    + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                    f'fill="{fill}" data-overlap-role="container" '
                    'data-overlap-note="外层卡片承载内层信息卡"/>'
                    '</svg>'
                )
                self.assertEqual(self.assert_svg_contract(variant, label), "fig-test")

        for invalid_fill in (
            "rgba(0,0,0 / 0.5)",
            "rgba(0 0 0 0.5)",
            "rgb(256,0,0)",
            "rgb(NaN,0,0)",
            "rgba(0,0,0,2)",
            "rgba(0,0,0,-0.1)",
            "hsl(0,50,50)",
            "hsl(0 101% 50%)",
        ):
            with self.subTest(invalid_fill=invalid_fill):
                self.assertFalse(has_statically_visible_fill(invalid_fill))

        bad_svgs = {
            "container missing id": (
                valid_root
                + '<rect x="40" y="40" width="220" height="160" fill="#EDF2F7" '
                'data-overlap-role="container" data-overlap-note="承载内层卡片"/>'
                '</svg>'
            ),
            "container unsafe id": (
                valid_root
                + '<rect id="outer card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-overlap-role="container" '
                'data-overlap-note="承载内层卡片"/>'
                '</svg>'
            ),
            "container padded id": (
                valid_root
                + '<rect id=" outer-card " x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-overlap-role="container" '
                'data-overlap-note="承载内层卡片"/>'
                '</svg>'
            ),
            "container missing note": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-overlap-role="container"/>'
                '</svg>'
            ),
            "container blank note": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-overlap-role="container" data-overlap-note="   "/>'
                '</svg>'
            ),
            "decoration role": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-overlap-role="decoration" '
                'data-overlap-note="装饰底纹"/>'
                '</svg>'
            ),
            "arbitrary role": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-overlap-role="background" '
                'data-overlap-note="背景面板"/>'
                '</svg>'
            ),
            "decoration disguised as container": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-overlap-role="container" '
                'data-overlap-note="外层作为装饰底纹"/>'
                '</svg>'
            ),
            "generic overlap escape hatch": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-allow-overlap="true" '
                'data-allow-overlap-note="允许覆盖"/>'
                '</svg>'
            ),
            "non-shape container": (
                valid_root
                + '<g id="outer-card" data-overlap-role="container" '
                'data-overlap-note="分组承载内层卡片">'
                '<rect x="40" y="40" width="220" height="160" fill="#EDF2F7"/>'
                '</g></svg>'
            ),
            "duplicate container id": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-overlap-role="container" '
                'data-overlap-note="外层卡片承载第一张信息卡"/>'
                '<rect id="outer-card" x="300" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-overlap-role="container" '
                'data-overlap-note="外层卡片承载第二张信息卡"/>'
                '</svg>'
            ),
            "namespaced identity": (
                '<svg xmlns:x="urn:test" viewBox="0 0 720 400" width="720" height="400" '
                'data-figure-id="fig-test">'
                '<rect x:id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-overlap-role="container" '
                'data-overlap-note="外层卡片承载内层信息卡"/>'
                '</svg>'
            ),
            "namespaced note": (
                '<svg xmlns:x="urn:test" viewBox="0 0 720 400" width="720" height="400" '
                'data-figure-id="fig-test">'
                '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-overlap-role="container" '
                'x:data-overlap-note="外层卡片承载内层信息卡"/>'
                '</svg>'
            ),
            "container rect without visible fill": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="none" stroke="#2D3436" data-overlap-role="container" '
                'data-overlap-note="外层卡片承载内层信息卡"/>'
                '</svg>'
            ),
            "container open path without visible fill": (
                valid_root
                + '<path id="outer-card" d="M40 40 L260 40 L260 200" '
                'fill="none" stroke="#2D3436" data-overlap-role="container" '
                'data-overlap-note="外层路径承载内层信息卡"/>'
                '</svg>'
            ),
            "container zero fill opacity": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" fill-opacity="0" data-overlap-role="container" '
                'data-overlap-note="外层卡片承载内层信息卡"/>'
                '</svg>'
            ),
            "container zero opacity": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" opacity="0" data-overlap-role="container" '
                'data-overlap-note="外层卡片承载内层信息卡"/>'
                '</svg>'
            ),
            "container zero alpha hex fill": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#00000000" data-overlap-role="container" '
                'data-overlap-note="外层卡片承载内层信息卡"/>'
                '</svg>'
            ),
            "container zero alpha rgba fill": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="rgba(0,0,0,0)" data-overlap-role="container" '
                'data-overlap-note="外层卡片承载内层信息卡"/>'
                '</svg>'
            ),
            "container inherited fill": (
                valid_root
                + '<g fill="none"><rect id="outer-card" x="40" y="40" '
                'width="220" height="160" fill="inherit" '
                'data-overlap-role="container" '
                'data-overlap-note="外层卡片承载内层信息卡"/></g>'
                '</svg>'
            ),
            "container paint server fill": (
                valid_root
                + '<defs><linearGradient id="panel-fill">'
                '<stop offset="0" stop-color="#EDF2F7"/>'
                '<stop offset="1" stop-color="#D6E4F0"/>'
                '</linearGradient></defs>'
                '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="url(#panel-fill)" data-overlap-role="container" '
                'data-overlap-note="外层卡片承载内层信息卡"/>'
                '</svg>'
            ),
            "container unknown named fill": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="notacolor" data-overlap-role="container" '
                'data-overlap-note="外层卡片承载内层信息卡"/>'
                '</svg>'
            ),
            "container invalid rgb fill": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="rgb(nonsense)" data-overlap-role="container" '
                'data-overlap-note="外层卡片承载内层信息卡"/>'
                '</svg>'
            ),
            "container empty rgb fill": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="rgb()" data-overlap-role="container" '
                'data-overlap-note="外层卡片承载内层信息卡"/>'
                '</svg>'
            ),
            "container invalid hsl fill": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="hsl(nonsense)" data-overlap-role="container" '
                'data-overlap-note="外层卡片承载内层信息卡"/>'
                '</svg>'
            ),
            "generic overlap note": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-overlap-role="container" '
                'data-overlap-note="允许重叠"/>'
                '</svg>'
            ),
            "padded generic overlap note": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-overlap-role="container" '
                'data-overlap-note="这里允许重叠"/>'
                '</svg>'
            ),
            "orphan overlap note": (
                valid_root
                + '<rect id="outer-card" x="40" y="40" width="220" height="160" '
                'fill="#EDF2F7" data-overlap-note="外层卡片承载内层信息卡"/>'
                '</svg>'
            ),
        }
        for rule, svg_text in bad_svgs.items():
            with self.subTest(rule=rule):
                with self.assertRaises(AssertionError):
                    self.assert_svg_contract(svg_text, rule)

    def test_known_bad_contract_variants_are_rejected(self) -> None:
        valid_root = (
            '<svg viewBox="0 0 720 400" width="720" height="400" '
            'data-figure-id="fig-test">'
        )
        bad_svgs = {
            "malformed XML": valid_root,
            "missing figure id": '<svg viewBox="0 0 720 400" width="720" height="400"></svg>',
            "empty figure id": (
                '<svg viewBox="0 0 720 400" width="720" height="400" '
                'data-figure-id=""></svg>'
            ),
            "unsafe figure id": (
                '<svg viewBox="0 0 720 400" width="720" height="400" '
                'data-figure-id="unsafe figure id"></svg>'
            ),
            "missing viewBox": (
                '<svg width="720" height="400" data-figure-id="fig-test"></svg>'
            ),
            "missing dimensions": (
                '<svg viewBox="0 0 720 400" data-figure-id="fig-test"></svg>'
            ),
            "noncanonical canvas geometry": (
                '<svg viewBox="10 20 860 400" width="860" height="400" '
                'data-figure-id="fig-test"></svg>'
            ),
            "style block": (
                valid_root +
                '<style>text{fill:#000}</style></svg>'
            ),
            "inline style attribute": (
                valid_root +
                '<text x="40" y="40" style="fill:#2D3436">文本</text></svg>'
            ),
            "root font-family": (
                '<svg viewBox="0 0 720 400" width="720" height="400" '
                'data-figure-id="fig-test" font-family="sans-serif"></svg>'
            ),
            "element font-family": (
                valid_root +
                '<text x="40" y="40" font-family="sans-serif">文本</text></svg>'
            ),
            "class selector": (
                valid_root +
                '<rect class="node" x="40" y="40" width="100" height="40"/></svg>'
            ),
            "CSS variable": (
                valid_root +
                '<rect x="40" y="40" width="100" height="40" fill="var(--node-fill)"/></svg>'
            ),
            "currentColor": (
                valid_root +
                '<path d="M0 0L10 10" stroke="currentColor"/></svg>'
            ),
            "canvas background rect": (
                valid_root +
                '<rect width="720" height="400" fill="#FFFFFF"/></svg>'
            ),
        }
        for rule, svg_text in bad_svgs.items():
            with self.subTest(rule=rule):
                with self.assertRaises(AssertionError):
                    self.assert_svg_contract(svg_text, rule)

        with self.assertRaisesRegex(AssertionError, "重复"):
            self.assert_unique_figure_ids(
                [("first.svg", "fig-duplicate"), ("second.svg", "fig-duplicate")]
            )


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
        self.assertIn("figure_id_AE", equivalence_check)
        self.assertIn("renderFontCss", browser_renderer)
        self.assertIn("document.fonts.ready", browser_renderer)


if __name__ == "__main__":
    unittest.main()
