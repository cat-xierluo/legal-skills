#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中英文标点符号转换脚本

将 Markdown 文件中的英文标点符号转换为中文标点符号。
用于 AI 生成文章的后处理，确保中文语境下的标点正确。

用法：
  python3 fix_punctuation.py <input.md> [-o output.md]
  python3 fix_punctuation.py <input.md>  # 原地修改
"""

import re
import sys
import os


def is_chinese_char(ch):
    """判断是否是中文字符（CJK 统一汉字区间）"""
    cp = ord(ch)
    return (
        (0x4E00 <= cp <= 0x9FFF)
        or (0x3400 <= cp <= 0x4DBF)
        or (0x20000 <= cp <= 0x2A6DF)
        or (0x2A700 <= cp <= 0x2B73F)
        or (0x2B740 <= cp <= 0x2B81F)
        or (0x2B820 <= cp <= 0x2CEAF)
        or (0xF900 <= cp <= 0xFAFF)
        or (0x2F800 <= cp <= 0x2FA1F)
    )


def has_chinese_nearby(text, pos, window=3):
    """检查位置附近是否有中文字符"""
    start = max(0, pos - window)
    end = min(len(text), pos + window + 1)
    for i in range(start, end):
        if i != pos and is_chinese_char(text[i]):
            return True
    return False


def convert_quotes_to_chinese(text):
    """将英文引号转换为中文引号（交替状态机版）

    规则：
    - 将直双引号 " 转为中文开/闭引号（交替状态）
    - 将直单引号 ' 转为中文开/闭引号，但保留英文缩写/所有格中的撇号
    - 跳过代码片段中的引号
    """
    if not text:
        return text

    if ('"' not in text) and ("'" not in text):
        return text

    result = []
    i = 0
    in_code = False
    double_quote_state = 0  # 0=等待开引号, 1=等待闭引号
    single_quote_state = 0

    while i < len(text):
        ch = text[i]

        # 处理反引号包裹的代码片段
        if ch == '`':
            j = i + 1
            while j < len(text) and text[j] == '`':
                j += 1
            backtick_count = j - i
            result.append('`' * backtick_count)
            in_code = not in_code
            i = j
            continue

        if in_code:
            result.append(ch)
            i += 1
            continue

        if ch == '"':
            if double_quote_state == 0:
                result.append('“')  # "
            else:
                result.append('”')  # "
            double_quote_state = 1 - double_quote_state
            i += 1
            continue

        if ch == "'":
            # 保留英文缩写和所有格中的撇号
            prev_ch = text[i - 1] if i > 0 else ''
            next_ch = text[i + 1] if i + 1 < len(text) else ''
            if prev_ch.isalpha() and next_ch.isalpha():
                result.append("'")
            else:
                if single_quote_state == 0:
                    result.append('‘')  # '
                else:
                    result.append('’')  # '
                single_quote_state = 1 - single_quote_state
            i += 1
            continue

        result.append(ch)
        i += 1

    return ''.join(result)


def fix_punctuation(text):
    """将中文语境中的英文标点转换为中文标点

    转换规则：
    - 引号：用状态机交替转换（单独处理）
    - 逗号：中文字符附近的 , → ，
    - 句号：中文字符附近的 . → 。（排除数字小数点、英文缩写、URL）
    - 冒号：中文字符附近的 : → ：（排除 URL、时间格式）
    - 分号：中文字符附近的 ; → ；
    - 括号：中文字符附近的 () → （）
    - 问号：中文字符附近的 ? → ？
    - 感叹号：中文字符附近的 ! → ！
    """
    if not text:
        return text

    # 提取 YAML front matter，不转换
    yaml_block = ''
    body = text
    if text.startswith('---'):
        end = text.find('---', 3)
        if end != -1:
            yaml_block = text[:end + 3]
            body = text[end + 3:]

    # 占位符系统：保护不应转换的区域
    placeholders = []
    counter = [0]

    def replace_match(match):
        idx = counter[0]
        counter[0] += 1
        placeholders.append(match.group(0))
        return f'\x00PH{idx}\x00'

    # 提取围栏代码块
    body = re.sub(r'```[\s\S]*?```', replace_match, body)
    # 提取行内代码
    body = re.sub(r'`[^`]+`', replace_match, body)
    # 提取 Markdown 图片语法 ![alt](url)
    body = re.sub(r'!\[[^\]]*\]\([^)]+\)', replace_match, body)
    # 提取 Markdown 链接语法 [text](url)
    body = re.sub(r'\[[^\]]+\]\([^)]+\)', replace_match, body)
    # 提取 URL
    body = re.sub(r'https?://[^\s)\]）】）】]+', replace_match, body)

    # 转换引号（状态机）
    body = convert_quotes_to_chinese(body)

    # 逐字符转换标点
    result = []
    i = 0

    while i < len(body):
        ch = body[i]
        prev_ch = body[i - 1] if i > 0 else ''
        next_ch = body[i + 1] if i + 1 < len(body) else ''

        # 跳过占位符
        if ch == '\x00':
            j = i + 1
            while j < len(body) and body[j] != '\x00':
                j += 1
            result.append(body[i:j + 1])
            i = j + 1
            continue

        if ch == ',':
            if has_chinese_nearby(body, i):
                result.append('，')
            else:
                result.append(ch)
        elif ch == ';':
            if has_chinese_nearby(body, i):
                result.append('；')
            else:
                result.append(ch)
        elif ch == '?':
            if has_chinese_nearby(body, i):
                result.append('？')
            else:
                result.append(ch)
        elif ch == '!':
            if has_chinese_nearby(body, i):
                result.append('！')
            else:
                result.append(ch)
        elif ch == '(':
            if has_chinese_nearby(body, i, window=2):
                result.append('（')
            else:
                result.append(ch)
        elif ch == ')':
            if has_chinese_nearby(body, i, window=2):
                result.append('）')
            else:
                result.append(ch)
        elif ch == ':':
            # 排除时间格式 (14:30) 和数字比例
            if has_chinese_nearby(body, i):
                if not (prev_ch.isdigit() and next_ch.isdigit()):
                    result.append('：')
                else:
                    result.append(ch)
            else:
                result.append(ch)
        elif ch == '.':
            # 句号转换：只在中文字符后面转换，排除小数点和英文缩写
            if is_chinese_char(prev_ch):
                result.append('。')
            elif prev_ch == '。':
                # 已经是句号，跳过
                result.append(ch)
            else:
                result.append(ch)
        else:
            result.append(ch)

        i += 1

    body = ''.join(result)

    # 恢复占位符
    for idx, original in enumerate(placeholders):
        body = body.replace(f'\x00PH{idx}\x00', original)

    # 拼回 YAML front matter
    return yaml_block + body


def process_file(input_path, output_path=None):
    """处理 Markdown 文件"""
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    result = fix_punctuation(content)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f'已转换: {input_path} -> {output_path}')
    else:
        with open(input_path, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f'已转换: {input_path}')

    return result


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python3 fix_punctuation.py <input.md> [-o output.md]')
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = None

    if '-o' in sys.argv:
        idx = sys.argv.index('-o')
        if idx + 1 < len(sys.argv):
            output_file = sys.argv[idx + 1]

    if not os.path.exists(input_file):
        print(f'文件不存在: {input_file}')
        sys.exit(1)

    process_file(input_file, output_file)
