#!/usr/bin/env python3
"""
Format legal case compilation files according to legal-text-format skill rules.
"""
import re
import sys
import os


# Conservative suffix grammar: unknown lines remain part of the case. In
# particular, a quoted/contact/source keyword inside prose is never a boundary.
_SOURCE_LINE = re.compile(
    r'^来源\s*[:：]\s*(?:上海市高级人民法院|天津高院|青岛中院|湖南高院|'
    r'宁波中院|江苏高院|南京中院)\s*$'
)
_FRESHRSS_LINE = re.compile(r'^\*(?:\[)?由 FreshRSS[^*\n]*\*$')
_PROMO_LINE = re.compile(r'^(?:扫码获取|浏览知产财经|联系我们|知产财经官网|'
                        r'订阅我们|点分享|点收藏|点在看|点点赞|往期热文)\s*$')


def _trim_trailing_footer(text):
    lines = text.splitlines(keepends=True)
    fence = None
    literal_lines = set()
    for index, raw in enumerate(lines):
        marker = re.match(r'^\s*(`{3,}|~{3,})', raw)
        if fence:
            literal_lines.add(index)
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not raw[marker.end():].strip():
                fence = None
        elif marker:
            fence = marker[1]
            literal_lines.add(index)
    end = len(lines)
    while end and not lines[end - 1].strip():
        end -= 1
    # A promotional-looking line alone is ambiguous; require attribution,
    # FreshRSS signature, or END, and only a wholly recognized suffix.
    for i in range(end - 1, -1, -1):
        if i in literal_lines or lines[i].startswith((' ', '\t', '>')):
            break
        line = lines[i].strip()
        if not line or _PROMO_LINE.fullmatch(line) or line == '---':
            continue
        if _SOURCE_LINE.fullmatch(line) or _FRESHRSS_LINE.fullmatch(line) or (line == 'END' and any(_PROMO_LINE.fullmatch(item.strip()) for item in lines[i + 1:end])):
            return ''.join(lines[:i]).rstrip('\r\n')
        break
    return text


def _normalize_punctuation(text):
    # Preserve fenced exhibits verbatim, including incomplete fences.
    result = []
    fence = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if fence:
            result.append(line)
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not line[marker.end():].strip():
                fence = None
        elif marker:
            fence = marker[1]
            result.append(line)
        else:
            result.append(_normalize_prose_punctuation(line))
    return ''.join(result)


def _normalize_prose_punctuation(text):
    """Normalize prose without corrupting numbers, URLs or Markdown syntax."""
    protected = re.compile(
        r'(?m:^\s*(?:[０-９0-9]+|[一二三四五六七八九十]+)[.、])'
        r'|`+[^`\n]*`+'
        r'|!?\[[^\]\n]*\]\((?:[^()\n]|\([^()\n]*\))*\)'
        r'|[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}'
        r'|(?:https?://|mailto:|www\.)[^\s<>“”‘’，。；！？（）【】]+'
        r'|[０-９0-9]+(?:[.,][０-９0-9]+)+'
    )
    replacements = str.maketrans({'(': '（', ')': '）', ',': '，', '.': '。',
                                  ':': '：', ';': '；', '!': '！', '?': '？'})

    digits = str.maketrans('０１２３４５６７８９', '0123456789')

    def prose(value):
        value = value.translate(replacements).translate(digits)
        value = re.sub(r'"([^"\n]+)"', r'“\1”', value)
        return re.sub(r"'([^'\n]+)'", r'‘\1’', value)

    result = []
    cursor = 0
    for match in protected.finditer(text):
        value = match.group()
        if re.fullmatch(r'[０-９0-9一二三四五六七八九十\s.,、]+', value):
            value = value.translate(digits)
        result.extend((prose(text[cursor:match.start()]), value))
        cursor = match.end()
    result.append(prose(text[cursor:]))
    return ''.join(result)


def _collapse_blank_lines(text):
    result = []
    fence = None
    previous_blank = False
    for line in text.split('\n'):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if fence:
            result.append(line)
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not line[marker.end():].strip():
                fence = None
            previous_blank = False
        elif marker:
            fence = marker[1]
            result.append(line)
            previous_blank = False
        elif line.strip():
            result.append(line)
            previous_blank = False
        elif not previous_blank:
            result.append('')
            previous_blank = True
    return '\n'.join(result)


def format_text(text, court_name, source_url, title, keep_from_marker=None):
    """
    Format legal text according to skill rules:
    - Convert English punctuation to Chinese
    - Add ## for case titles, ### for case sections
    - Clean up excessive blank lines (max 1 consecutive)
    - Convert numbers to half-width
    - Trim only recognized trailing footer blocks
    - Preserve ambiguous content and literal evidence blocks
    """
    
    # Prefix boundaries must be supplied explicitly. Dates and case-like
    # phrases may also occur in substantive text, so do not guess a cutoff.
    if keep_from_marker:
        idx = text.find(keep_from_marker)
        if idx != -1:
            text = text[idx:]

    # Only remove an explicitly recognized trailing attribution/footer block.
    # Body keywords and paragraph lengths are not evidence that a case ended.
    text = _trim_trailing_footer(text)
    text = _normalize_punctuation(text)

    # Clean up excessive blank lines (max 1 consecutive)
    text = _collapse_blank_lines(text)
    
    # Build output with metadata header
    output = f"""# {title}

- **来源**：{court_name}
- **原文**：[点击查看]({source_url})

"""
    
    # Process case structure
    lines = text.split('\n')
    result_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Fenced source/exhibit blocks remain literal, even without a closing
        # fence. Do not interpret their labels as cases or section headings.
        fence_match = re.match(r'^\s*(`{3,}|~{3,})', line)
        if fence_match:
            fence = fence_match[1]
            result_lines.append(line)
            i += 1
            while i < len(lines):
                result_lines.append(lines[i])
                closing = re.match(r'^\s*(`{3,}|~{3,})\s*$', lines[i])
                i += 1
                if closing and closing[1][0] == fence[0] and len(closing[1]) >= len(fence):
                    break
            continue

        # Every detection branch must retain its line if formatting does not
        # apply; a tentative match alone is never permission to drop text.
        result_count = len(result_lines)
        # Case title detection - various formats
        is_case_title = False
        
        # Pattern: /** 案例1 **/ or /** 案例 **/
        if re.match(r'/\*\*\s*案例', stripped) or re.match(r'\*\*\s*案例', stripped):
            # Clean up and add as case header
            case_name = re.sub(r'^/?\*\*\s*|\s*\*\*/?$', '', stripped).strip()
            result_lines.append(f'\n## {case_name}\n')
            is_case_title = True
        
        # Pattern: "案例1" or "案例一" as standalone
        elif re.match(r'^案例[一二三四五六七八九十\d]+$', stripped):
            # Look ahead for the actual case name
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if (next_line.endswith('案')
                        and not re.match(r'^(?:[#>`~!\[\-*+]|案例|[０-９0-9一二三四五六七八九十]+[.、])', next_line)):
                    result_lines.append(f'\n## {stripped} {next_line}\n')
                    i += 1
                    is_case_title = True
                else:
                    result_lines.append(f'\n## {stripped}\n')
                    is_case_title = True
        
        # Pattern: Case name like "涉...案" or "XXX案" at section level
        elif re.match(r'^涉\S+案$', stripped) or \
             re.match(r'^[某\d]*(?:与|诉|等)[某\d\S]+案$', stripped) or \
             re.match(r'^[A-Za-z0-9某]+[与诉等][A-Za-z0-9某]+案$', stripped):
            # Check if this is a new case header
            if i > 0:
                prev = lines[i-1].strip()
                if prev == '' or prev.startswith('##') or '裁判结果' in prev or '典型意义' in prev:
                    result_lines.append(f'\n## {stripped}\n')
                    is_case_title = True
        
        # Pattern: numbered case like "1." or "一、" at start
        elif re.match(r'^\d+[.。、]', stripped) or re.match(r'^[一二三四五六七八九十]+[.。、]', stripped):
            # Clean up and add
            case_name = stripped
            if case_name and len(case_name) > 2:
                result_lines.append(f'\n## {case_name}\n')
                is_case_title = True
        
        # Section headers (案情摘要, 裁判结果, 典型意义, 基本案情, etc.)
        elif stripped in ['案情摘要', '基本案情', '裁判结果', '典型意义', '裁判内容', '【案情摘要】', '【基本案情】', '【裁判结果】', '【典型意义】', '【裁判内容】']:
            section_name = re.sub(r'【|】', '', stripped)
            result_lines.append(f'\n### {section_name}\n')
        
        # Clean up remaining markdown artifacts
        elif stripped.startswith('**') and stripped.endswith('**') and not is_case_title:
            # Bold text that might be a header
            inner = stripped.strip('*')
            if len(inner) < 50 and not any(c in inner for c in ['。', '，', '；']):
                result_lines.append(f'### {inner}\n')
            else:
                result_lines.append(line)
        
        else:
            result_lines.append(line)
        
        if len(result_lines) == result_count:
            result_lines.append(line)
        i += 1
    
    # Clean up excessive blank lines again
    formatted_content = '\n'.join(result_lines)
    formatted_content = _collapse_blank_lines(formatted_content)
    
    output += formatted_content
    
    return output


if __name__ == '__main__':
    if len(sys.argv) < 6:
        print("Usage: format_legal_cases.py <input_file> <output_file> <court_name> <source_url> <title>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    court_name = sys.argv[3]
    source_url = sys.argv[4]
    title = sys.argv[5]
    
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # The function owns formatting and conservative suffix cleanup. Passing
    # the complete input avoids date-based cuts and missing-marker -1 slices.
    body = content

    formatted = format_text(body, court_name, source_url, title)
    
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(formatted)
    
    print(f"Formatted: {output_file}")
