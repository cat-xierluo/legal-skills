#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文本格式化模块
处理文本格式解析、段落格式设置、字体样式应用
"""

import re
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn

# 导入配置模块
from config import Config, get_config


def convert_quotes_to_chinese(text):
    """将英文引号转换为中文引号（交替状态机版）
    规则：
    - 将直双引号 " 转为中文开/闭引号 " "（交替状态：开→闭→开→闭...）
    - 将直单引号 ' 转为中文开/闭引号 ' '，但保留英文缩写/所有格中的撇号（如 don't, John's）
    - 避免转换代码片段中的引号（由反引号 ` 包裹）
    """
    if not text:
        return text

    original_text = text

    # 若无需要处理的引号，直接返回
    if ('"' not in text) and ("'" not in text):
        return text

    result = []
    i = 0
    in_code = False  # 是否处于 `code` 片段中

    # 交替状态机：0=等待开引号，1=等待闭引号
    double_quote_state = 0
    single_quote_state = 0

    while i < len(text):
        ch = text[i]

        # 处理反引号包裹的代码片段，保持原样
        if ch == '`':
            # 统计连续反引号的数量（支持 ``` 块 及 ` 行内`）
            j = i + 1
            while j < len(text) and text[j] == '`':
                j += 1
            backtick_count = j - i
            result.append('`' * backtick_count)
            in_code = not in_code  # 简化处理：遇到成组反引号时翻转状态
            i = j
            continue

        if in_code:
            # 代码片段内不做引号更换
            result.append(ch)
            i += 1
            continue

        if ch == '"':
            # 使用交替状态机：第一个是开引号，第二个是闭引号，以此类推
            if double_quote_state == 0:
                result.append('\u201c')  # 中文开双引号 "
                double_quote_state = 1  # 下一个是闭引号
            else:
                result.append('\u201d')  # 中文闭双引号 "
                double_quote_state = 0  # 重置，下一个是开引号
            i += 1
            continue

        if ch == "'":
            # 保留英文缩写/所有格中的撇号：字母-撇号-字母
            prev_c = text[i - 1] if i > 0 else ''
            next_c = text[i + 1] if i + 1 < len(text) else ''
            if prev_c.isalpha() and next_c.isalpha():
                result.append("'")
                i += 1
                continue

            # 使用交替状态机
            if single_quote_state == 0:
                result.append('\u2018')  # 中文开单引号 '
                single_quote_state = 1
            else:
                result.append('\u2019')  # 中文闭单引号 '
                single_quote_state = 0
            i += 1
            continue

        # 其它字符保持
        result.append(ch)
        i += 1

    text = ''.join(result)

    if text != original_text:
        print(f"✅ 引号转换: {original_text} → {text}")

    return text


def parse_text_formatting(paragraph, text, title_level=0, is_quote=False):
    """解析文本格式（支持加粗、斜体、下划线，转换引号为中文）"""

    # 转换英文引号为中文引号
    text = convert_quotes_to_chinese(text)

    # 先处理<br>标签为段内换行
    segments = re.split(r'<br\s*/?>', text, flags=re.IGNORECASE)

    # 使用正则表达式解析所有格式标记
    format_patterns = [
        (r'\*\*\*(.*?)\*\*\*', {'bold': True, 'italic': True}),
        (r'___(.*?)___', {'bold': True, 'italic': True}),
        (r'\*\*(.*?)\*\*', {'bold': True}),
        (r'__(.*?)__', {'bold': True}),
        (r'(?<!\*)\*([^*\n]+?)\*(?!\*)', {'italic': True}),
        (r'(?<!_)_([^_\n]+?)_(?!_)', {'italic': True}),
        (r'<u>(.*?)</u>', {'underline': True}),
        (r'~~(.*?)~~', {'strikethrough': True}),
        (r'`([^`\n]+)`', {'code': True}),
        (r'\$([^$\n]+?)\$', {'math': True}),  # LaTeX数学公式支持
    ]

    for idx, segment in enumerate(segments):
        text_parts = parse_formatted_text(segment, format_patterns)
        for part_text, formats in text_parts:
            if part_text:  # 只有非空文本才创建run
                run = paragraph.add_run(part_text)
                set_run_format_with_styles(run, formats, title_level=title_level, is_quote=is_quote)
        if idx < len(segments) - 1:
            paragraph.add_run().add_break()


def parse_formatted_text(text, format_patterns):
    """解析带格式的文本，返回(文本, 格式)的列表"""

    if not text:
        return []

    parts = []
    current_pos = 0

    # 查找所有格式标记的位置
    all_matches = []
    for pattern, format_dict in format_patterns:
        for match in re.finditer(pattern, text):
            all_matches.append({
                'start': match.start(),
                'end': match.end(),
                'text': match.group(1),
                'format': format_dict,
                'full_match': match.group(0)
            })

    # 按开始位置排序
    all_matches.sort(key=lambda x: x['start'])

    # 处理重叠的匹配（选择最长的匹配）
    filtered_matches = []
    for match in all_matches:
        # 检查是否与已有匹配重叠
        overlap = False
        for existing in filtered_matches:
            if (match['start'] < existing['end'] and match['end'] > existing['start']):
                # 有重叠，选择更长的匹配
                if len(match['full_match']) > len(existing['full_match']):
                    filtered_matches.remove(existing)
                    filtered_matches.append(match)
                overlap = True
                break
        if not overlap:
            filtered_matches.append(match)

    # 重新按位置排序
    filtered_matches.sort(key=lambda x: x['start'])

    # 构建文本部分列表
    for match in filtered_matches:
        # 添加前面的普通文本
        if current_pos < match['start']:
            normal_text = text[current_pos:match['start']]
            if normal_text:
                parts.append((normal_text, {}))

        # 添加格式化文本
        parts.append((match['text'], match['format']))
        current_pos = match['end']

    # 添加剩余的普通文本
    if current_pos < len(text):
        remaining_text = text[current_pos:]
        if remaining_text:
            parts.append((remaining_text, {}))

    # 如果没有找到任何格式，返回整个文本作为普通文本
    if not parts:
        parts.append((text, {}))

    return parts


def set_run_format(run, title_level=0):
    """设置文本运行格式（基础版本，用于标题）"""
    config = get_config()
    font_config = config.get('fonts.default', {})

    font = run.font
    font.name = font_config.get('ascii', 'Times New Roman')
    font.color.rgb = RGBColor(0, 0, 0)
    font.bold = False
    font.italic = False
    font.underline = False

    # 设置字体映射
    run._element.rPr.rFonts.set(qn('w:ascii'), font_config.get('ascii', 'Times New Roman'))
    run._element.rPr.rFonts.set(qn('w:hAnsi'), font_config.get('ascii', 'Times New Roman'))
    run._element.rPr.rFonts.set(qn('w:eastAsia'), font_config.get('name', '仿宋_GB2312'))
    run._element.rPr.rFonts.set(qn('w:cs'), font_config.get('ascii', 'Times New Roman'))

    # 根据标题级别设置字号和加粗
    if title_level == 1:
        title_config = config.get('titles.level1', {})
        font.size = Pt(title_config.get('size', 15))
        font.bold = title_config.get('bold', True)
    elif title_level == 2:
        title_config = config.get('titles.level2', {})
        font.size = Pt(title_config.get('size', 12))
        font.bold = title_config.get('bold', True)
    elif title_level == 3:
        title_config = config.get('titles.level3', {})
        font.size = Pt(title_config.get('size', 12))
        font.bold = title_config.get('bold', False)
    elif title_level == 4:
        title_config = config.get('titles.level4', {})
        font.size = Pt(title_config.get('size', 12))
        font.bold = title_config.get('bold', False)
    else:
        font.size = Pt(font_config.get('size', 12))
        font.bold = False


def set_run_format_with_styles(run, formats, title_level=0, is_quote=False):
    """设置文本运行格式（支持多种样式）"""
    config = get_config()
    font_config = config.get('fonts.default', {})

    font = run.font
    font.name = font_config.get('ascii', 'Times New Roman')
    font.color.rgb = RGBColor(0, 0, 0)

    # 设置字体映射
    run._element.rPr.rFonts.set(qn('w:ascii'), font_config.get('ascii', 'Times New Roman'))
    run._element.rPr.rFonts.set(qn('w:hAnsi'), font_config.get('ascii', 'Times New Roman'))
    run._element.rPr.rFonts.set(qn('w:eastAsia'), font_config.get('name', '仿宋_GB2312'))
    run._element.rPr.rFonts.set(qn('w:cs'), font_config.get('ascii', 'Times New Roman'))

    # 设置基础格式
    if title_level == 1:
        title_config = config.get('titles.level1', {})
        font.size = Pt(title_config.get('size', 15))
        font.bold = title_config.get('bold', True)
    elif title_level == 2:
        title_config = config.get('titles.level2', {})
        font.size = Pt(title_config.get('size', 12))
        font.bold = title_config.get('bold', True)
    elif is_quote:
        # 引用使用较小字号
        font.size = Pt(9)
        font.bold = False
    else:
        font.size = Pt(font_config.get('size', 12))
        font.bold = False

    # 应用Markdown格式
    if formats.get('code', False):
        code_config = config.get('inline_code', {})
        font.name = code_config.get('font', 'Times New Roman')
        font.size = Pt(code_config.get('size', 10))
        font.color.rgb = hex_to_rgb(code_config.get('color', '#333333'))
        run._element.rPr.rFonts.set(qn('w:ascii'), font.name)
        run._element.rPr.rFonts.set(qn('w:hAnsi'), font.name)
        run._element.rPr.rFonts.set(qn('w:eastAsia'), font.name)
    elif formats.get('math', False):
        math_config = config.get('math', {})
        font.name = math_config.get('font', 'Times New Roman')
        font.size = Pt(math_config.get('size', 11))
        font.italic = math_config.get('italic', True)
        font.color.rgb = hex_to_rgb(math_config.get('color', '#00008B'))
        run._element.rPr.rFonts.set(qn('w:ascii'), font.name)
        run._element.rPr.rFonts.set(qn('w:hAnsi'), font.name)
        run._element.rPr.rFonts.set(qn('w:eastAsia'), font.name)
    else:
        if formats.get('bold', False):
            font.bold = True
        if formats.get('italic', False):
            font.italic = True
        if formats.get('underline', False):
            font.underline = True
        if formats.get('strikethrough', False):
            font.strike = True


def set_paragraph_format(paragraph, title_level=0, is_quote=False):
    """设置段落格式"""
    config = get_config()
    paragraph_config = config.get('paragraph', {})

    # 设置段落格式
    paragraph_format = paragraph.paragraph_format
    paragraph_format.line_spacing = paragraph_config.get('line_spacing', 1.5)

    if title_level == 1:
        # 一级标题配置
        title_config = config.get('titles.level1', {})
        align_str = title_config.get('align', 'center')
        paragraph_format.alignment = parse_alignment(align_str)
        paragraph_format.space_before = Pt(title_config.get('space_before', 6))
        paragraph_format.space_after = Pt(title_config.get('space_after', 6))
        paragraph_format.first_line_indent = Pt(title_config.get('indent', 0))
    elif title_level == 2:
        # 二级标题配置
        title_config = config.get('titles.level2', {})
        align_str = title_config.get('align', 'justify')
        paragraph_format.alignment = parse_alignment(align_str)
        paragraph_format.space_before = Pt(0)
        paragraph_format.space_after = Pt(0)
        paragraph_format.first_line_indent = Pt(title_config.get('indent', 24))
    elif title_level == 3:
        # 三级标题配置
        title_config = config.get('titles.level3', {})
        align_str = title_config.get('align', 'justify')
        paragraph_format.alignment = parse_alignment(align_str)
        paragraph_format.space_before = Pt(0)
        paragraph_format.space_after = Pt(0)
        paragraph_format.first_line_indent = Pt(title_config.get('indent', 24))
    elif title_level == 4:
        # 四级标题配置
        title_config = config.get('titles.level4', {})
        align_str = title_config.get('align', 'justify')
        paragraph_format.alignment = parse_alignment(align_str)
        paragraph_format.space_before = Pt(0)
        paragraph_format.space_after = Pt(0)
        paragraph_format.first_line_indent = Pt(title_config.get('indent', 24))
    elif is_quote:
        # 引用：两端对齐，无首行缩进
        paragraph_format.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
        paragraph_format.space_before = Pt(0)
        paragraph_format.space_after = Pt(0)
        paragraph_format.first_line_indent = Pt(0)
    else:
        # 正文段落配置
        align_str = paragraph_config.get('align', 'justify')
        paragraph_format.alignment = parse_alignment(align_str)
        paragraph_format.space_before = Pt(0)
        paragraph_format.space_after = Pt(0)
        paragraph_format.first_line_indent = Pt(paragraph_config.get('first_line_indent', 24))

    # 确保所有runs都有正确的格式
    for run in paragraph.runs:
        if not hasattr(run.font, 'name') or not run.font.name:
            set_run_format(run, title_level)


def parse_alignment(align_str: str):
    """将字符串对齐方式转换为 WD_PARAGRAPH_ALIGNMENT 常量"""
    align_str = align_str.lower()
    if align_str == 'left':
        return WD_PARAGRAPH_ALIGNMENT.LEFT
    elif align_str == 'center':
        return WD_PARAGRAPH_ALIGNMENT.CENTER
    elif align_str == 'right':
        return WD_PARAGRAPH_ALIGNMENT.RIGHT
    else:  # justify
        return WD_PARAGRAPH_ALIGNMENT.JUSTIFY


def hex_to_rgb(hex_color: str):
    """将十六进制颜色转换为 RGBColor"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return RGBColor(r, g, b)
    return RGBColor(0, 0, 0)  # 默认黑色
