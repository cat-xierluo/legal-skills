#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 Word 模板提取 md2word（python-docx 引擎）可用的 YAML 配置。"""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from docx import Document
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT


BASE_CONFIG: Dict[str, Any] = {
    "name": "模板提取配置",
    "description": "从 DOCX 模板提取的配置",
    "page": {
        "width": 21.0,
        "height": 29.7,
        "margin_top": 2.54,
        "margin_bottom": 2.54,
        "margin_left": 3.18,
        "margin_right": 3.18,
    },
    "fonts": {
        "default": {
            "name": "仿宋_GB2312",
            "ascii": "Times New Roman",
            "size": 12,
            "color": "#000000",
        }
    },
    "titles": {
        "level1": {
            "size": 15,
            "bold": True,
            "align": "center",
            "space_before": 6,
            "space_after": 6,
            "indent": 0,
        },
        "level2": {
            "size": 12,
            "bold": True,
            "align": "justify",
            "indent": 24,
        },
        "level3": {
            "size": 12,
            "bold": False,
            "align": "justify",
            "indent": 24,
        },
        "level4": {
            "size": 12,
            "bold": False,
            "align": "justify",
            "indent": 24,
        },
    },
    "paragraph": {
        "line_spacing": 1.5,
        "first_line_indent": 24,
        "align": "justify",
    },
    "page_number": {
        "enabled": True,
        "format": "1/x",
        "font": "Times New Roman",
        "size": 10.5,
        "position": "center",
    },
    "quotes": {
        "convert_to_chinese": True,
    },
    "table": {
        "border_enabled": True,
        "border_color": "#000000",
        "border_width": 4,
        "line_spacing": 1.2,
        "row_height_cm": 0.8,
        "alignment": "center",
        "cell_margin": {
            "top": 30,
            "bottom": 30,
            "left": 60,
            "right": 60,
        },
        "vertical_align": "center",
        "header": {
            "font": "Times New Roman",
            "size": 10.5,
            "bold": True,
            "color": "#000000",
        },
        "body": {
            "font": "仿宋_GB2312",
            "size": 10.5,
            "color": "#000000",
        },
    },
    "code_block": {
        "label": {
            "font": "Times New Roman",
            "size": 10,
            "color": "#808080",
        },
        "content": {
            "font": "Times New Roman",
            "size": 10,
            "color": "#333333",
            "left_indent": 24,
            "line_spacing": 1.2,
        },
    },
    "inline_code": {
        "font": "Times New Roman",
        "size": 10,
        "color": "#333333",
    },
    "quote": {
        "background_color": "#EAEAEA",
        "left_indent_inches": 0.2,
        "font_size": 9,
        "line_spacing": 1.5,
    },
    "math": {
        "font": "Times New Roman",
        "size": 11,
        "italic": True,
        "color": "#00008B",
    },
    "image": {
        "display_ratio": 0.92,
        "max_width_cm": 14.2,
        "target_dpi": 260,
        "show_caption": True,
    },
    "horizontal_rule": {
        "character": "─",
        "repeat_count": 55,
        "font": "Times New Roman",
        "size": 12,
        "color": "#808080",
        "alignment": "center",
    },
    "lists": {
        "bullet": {
            "marker": "•",
            "indent": 24,
        },
        "numbered": {
            "indent": 24,
            "preserve_format": True,
        },
        "task": {
            "unchecked": "☐",
            "checked": "☑",
        },
    },
}


PROFILE_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "law-firm": {
        "name": "律所主题（模板同步）",
        "description": "基于 law-firm 主题文档说明的配置覆盖",
        "fonts": {
            "default": {
                "name": "宋体",
                "ascii": "Times New Roman",
                "size": 12,
            }
        },
        "titles": {
            "level1": {"size": 16, "color": "#1A1A2E", "align": "center"},
            "level2": {"size": 14, "color": "#1A1A2E"},
            "level3": {"size": 12, "color": "#1A1A2E"},
        },
        "paragraph": {
            "line_spacing": 1.5,
            "first_line_indent": 24,
        },
    },
    "tech-doc": {
        "name": "技术文档主题（模板同步）",
        "description": "基于 tech-doc 主题文档说明的配置覆盖",
        "fonts": {
            "default": {
                "name": "微软雅黑",
                "ascii": "Source Sans Pro",
                "size": 10.5,
            }
        },
        "titles": {
            "level1": {"size": 18, "color": "#2196F3"},
            "level2": {"size": 16, "color": "#2196F3"},
            "level3": {"size": 14, "color": "#2196F3"},
        },
        "paragraph": {
            "line_spacing": 1.3,
            "first_line_indent": 0,
        },
        "code_block": {
            "content": {
                "font": "Fira Code",
            }
        },
        "inline_code": {
            "font": "Fira Code",
        },
    },
    "minimal": {
        "name": "极简主题（模板同步）",
        "description": "基于 minimal 主题文档说明的配置覆盖",
        "fonts": {
            "default": {
                "name": "宋体",
                "ascii": "Times New Roman",
                "size": 11,
            }
        },
        "titles": {
            "level1": {"size": 16, "color": "#000000"},
            "level2": {"size": 14, "color": "#000000"},
            "level3": {"size": 12, "color": "#000000"},
        },
        "paragraph": {
            "line_spacing": 1.0,
            "first_line_indent": 0,
        },
    },
}


CJK_FONT_HINTS = {
    "simsun",
    "kaiti",
    "fangsong",
    "songti",
    "simhei",
    "microsoft yahei",
    "microsoft jhenghei",
    "pingfang",
    "heiti",
    "source han",
    "noto serif cjk",
    "noto sans cjk",
}


def _cm(value: Optional[int]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value) / 360000, 2)


def _pt(value: Any) -> Optional[float]:
    if value is None:
        return None
    pt_val = getattr(value, "pt", None)
    if pt_val is None:
        return None
    return round(float(pt_val), 2)


def _alignment_to_str(alignment: Any) -> Optional[str]:
    if alignment is None:
        return None
    mapping = {
        WD_PARAGRAPH_ALIGNMENT.LEFT: "left",
        WD_PARAGRAPH_ALIGNMENT.CENTER: "center",
        WD_PARAGRAPH_ALIGNMENT.RIGHT: "right",
        WD_PARAGRAPH_ALIGNMENT.JUSTIFY: "justify",
    }
    return mapping.get(alignment)


def _to_hex(color_rgb: Any) -> Optional[str]:
    if color_rgb is None:
        return None
    return f"#{str(color_rgb)}"


def _style(document: Document, name: str):
    for style in document.styles:
        if style.name == name:
            return style
    return None


def _default_ascii(font_name: Optional[str]) -> str:
    if not font_name:
        return "Times New Roman"
    lower_name = font_name.lower()
    if any(ord(ch) > 127 for ch in font_name):
        return "Times New Roman"
    if any(hint in lower_name for hint in CJK_FONT_HINTS):
        return "Times New Roman"
    return font_name


def deep_update(target: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            deep_update(target[key], value)
        else:
            target[key] = value
    return target


def extract_template_config(template_path: Path) -> Dict[str, Any]:
    config = deepcopy(BASE_CONFIG)
    document = Document(template_path)

    section = document.sections[0]
    page = config["page"]
    page["width"] = _cm(section.page_width) or page["width"]
    page["height"] = _cm(section.page_height) or page["height"]
    page["margin_top"] = _cm(section.top_margin) or page["margin_top"]
    page["margin_bottom"] = _cm(section.bottom_margin) or page["margin_bottom"]
    page["margin_left"] = _cm(section.left_margin) or page["margin_left"]
    page["margin_right"] = _cm(section.right_margin) or page["margin_right"]

    normal = _style(document, "Normal")
    if normal is not None:
        normal_font = normal.font
        normal_para = normal.paragraph_format
        font_name = normal_font.name or config["fonts"]["default"]["name"]
        config["fonts"]["default"]["name"] = font_name
        config["fonts"]["default"]["ascii"] = _default_ascii(normal_font.name)
        config["fonts"]["default"]["size"] = _pt(normal_font.size) or config["fonts"]["default"]["size"]
        config["fonts"]["default"]["color"] = _to_hex(normal_font.color.rgb) or config["fonts"]["default"]["color"]
        config["paragraph"]["line_spacing"] = (
            float(normal_para.line_spacing)
            if isinstance(normal_para.line_spacing, (int, float))
            else config["paragraph"]["line_spacing"]
        )
        config["paragraph"]["first_line_indent"] = (
            _pt(normal_para.first_line_indent) or config["paragraph"]["first_line_indent"]
        )
        config["paragraph"]["align"] = _alignment_to_str(normal_para.alignment) or config["paragraph"]["align"]
        config["table"]["body"]["font"] = font_name
        config["table"]["body"]["size"] = config["fonts"]["default"]["size"]

    for level, style_name in enumerate(["Heading 1", "Heading 2", "Heading 3", "Heading 4"], start=1):
        style = _style(document, style_name)
        if style is None:
            continue
        key = f"level{level}"
        info = config["titles"][key]
        style_font = style.font
        style_para = style.paragraph_format

        size = _pt(style_font.size)
        if size:
            info["size"] = size
        if style_font.bold is not None:
            info["bold"] = bool(style_font.bold)
        color = _to_hex(style_font.color.rgb)
        if color:
            info["color"] = color
        align = _alignment_to_str(style_para.alignment)
        if align:
            info["align"] = align
        space_before = _pt(style_para.space_before)
        if space_before is not None:
            info["space_before"] = space_before
        space_after = _pt(style_para.space_after)
        if space_after is not None:
            info["space_after"] = space_after
        indent = _pt(style_para.first_line_indent)
        if indent is not None:
            info["indent"] = indent

    code_style = _style(document, "Code Block")
    if code_style is not None:
        code_font = code_style.font
        code_para = code_style.paragraph_format
        config["code_block"]["content"]["font"] = code_font.name or config["code_block"]["content"]["font"]
        config["code_block"]["content"]["size"] = _pt(code_font.size) or config["code_block"]["content"]["size"]
        config["code_block"]["content"]["color"] = _to_hex(code_font.color.rgb) or config["code_block"]["content"]["color"]
        config["code_block"]["content"]["line_spacing"] = (
            float(code_para.line_spacing)
            if isinstance(code_para.line_spacing, (int, float))
            else config["code_block"]["content"]["line_spacing"]
        )

    quote_style = _style(document, "Block Quote")
    if quote_style is not None:
        quote_font = quote_style.font
        quote_para = quote_style.paragraph_format
        config["quote"]["font_size"] = _pt(quote_font.size) or config["quote"]["font_size"]
        config["quote"]["line_spacing"] = (
            float(quote_para.line_spacing)
            if isinstance(quote_para.line_spacing, (int, float))
            else config["quote"]["line_spacing"]
        )
        left_indent_pt = _pt(quote_para.left_indent)
        if left_indent_pt is not None:
            config["quote"]["left_indent_inches"] = round(left_indent_pt / 72.0, 3)

    return config


def main() -> int:
    parser = argparse.ArgumentParser(description="从 docx 模板提取 md2word YAML 配置")
    parser.add_argument("--template", default=None, help="模板文件路径（.docx），默认使用 assets/templates/ 目录下第一个 .docx 文件")
    parser.add_argument("--output", required=True, help="输出 YAML 路径")
    parser.add_argument("--name", default=None, help="配置名称")
    parser.add_argument("--description", default=None, help="配置描述")
    parser.add_argument(
        "--profile",
        default=None,
        choices=["law-firm", "tech-doc", "minimal"],
        help="在提取结果上应用主题说明覆盖",
    )
    args = parser.parse_args()

    # 相对路径相对于 skill 根目录（脚本上级目录）解析
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    templates_dir = skill_dir / "assets" / "templates"

    if args.template:
        template_path = (skill_dir / args.template).resolve()
    else:
        # 自动查找 templates 目录下第一个 .docx
        docx_files = sorted(templates_dir.glob("*.docx"))
        if not docx_files:
            raise FileNotFoundError(
                f"未找到模板文件，请将 .docx 模板放入 {templates_dir}，或使用 --template 指定路径"
            )
        template_path = docx_files[0]
        print(f"自动选择模板: {template_path.name}")

    output_path = (skill_dir / args.output).resolve()

    if not template_path.exists():
        raise FileNotFoundError(f"模板不存在: {template_path}")

    config = extract_template_config(template_path)

    if args.name:
        config["name"] = args.name
    if args.description:
        config["description"] = args.description

    if args.profile:
        deep_update(config, PROFILE_OVERRIDES[args.profile])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)

    print(f"已生成配置: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
