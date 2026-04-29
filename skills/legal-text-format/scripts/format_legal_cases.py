#!/usr/bin/env python3
"""
Format legal case compilation files according to legal-text-format skill rules.
"""
import re
import sys
import os

def format_text(text, court_name, source_url, title, keep_from_marker=None):
    """
    Format legal text according to skill rules:
    - Convert English punctuation to Chinese
    - Add ## for case titles, ### for case sections
    - Clean up excessive blank lines (max 1 consecutive)
    - Convert numbers to half-width
    - Remove content scope (intro/QR codes/promotion)
    - Keep case content intro paragraph
    """
    
    # Find where actual cases start (look for first case marker)
    # Cases typically start with patterns like "案例1", "案例一", "/** 案例", etc.
    
    # If keep_from_marker specified, start from there
    if keep_from_marker:
        idx = text.find(keep_from_marker)
        if idx != -1:
            text = text[idx:]
    
    # Remove top matter (frontmatter, headers with source info, etc.)
    # Keep the first meaningful paragraph about the announcement
    
    # Find first case indicator
    case_patterns = [
        r'案例\s*\d+',  # 案例1, 案例 1
        r'案例一', r'案例二', r'案例三',
        r'/\*\*/\s*案例',  # /** 案例 **/
        r'^\d+、',  # 1、 at line start
        r'^\[案例',  # [案例
    ]
    
    first_case_pos = len(text)
    for pattern in case_patterns:
        matches = list(re.finditer(pattern, text, re.MULTILINE))
        if matches:
            # Find earliest match that's likely a case header (not in middle of text)
            for m in matches:
                # Check if this looks like a case header (line start, or has context)
                start_line = text[:m.start()].count('\n')
                # Get the line containing this match
                line_start = text.rfind('\n', 0, m.start()) + 1
                line_end = text.find('\n', m.start())
                line = text[line_start:line_end].strip()
                if line.startswith(('案例', '/**', '[案例', '1、', '2、', '3、')) or \
                   re.match(r'案例\s*\d+', line):
                    if m.start() < first_case_pos:
                        first_case_pos = m.start()
                        break
    
    # Also look for case names like "涉...案" or "XXX与XXX...案"
    case_name_pattern = r'(?:涉|侵害|侵害|假冒|确认|某.*与某.*)\S{0,30}?(?:纠纷案|侵权案|不正当竞争案|发明专利侵权案|实用新型专利侵权案|外观设计专利侵权案)'
    name_matches = list(re.finditer(case_name_pattern, text))
    for m in name_matches:
        # Check context - should be near start
        if m.start() < first_case_pos and m.start() < 5000:
            # Verify it's a case header (preceded by newlines)
            before = text[max(0, m.start()-100):m.start()]
            if '\n\n' in before or before.strip() == '':
                first_case_pos = m.start()
                break
    
    # Find intro paragraph (e.g., "4月23日...")
    intro_marker = None
    for marker in ['4月23日', '4月24日', '4月22日']:
        idx = text.find(marker)
        if idx != -1 and idx < first_case_pos:
            intro_marker = marker
            # Find start of that line
            line_start = text.rfind('\n', 0, idx) + 1
            intro_marker = text[line_start:idx]
            first_case_pos = line_start
            break
    
    if first_case_pos == len(text):
        first_case_pos = 0
    
    text = text[first_case_pos:]
    
    # Now find where cases END (before footer "来源", QR codes, etc.)
    end_patterns = [
        r'来源\s*[:：]\s*上海市高级人民法院',
        r'来源\s*[:：]\s*天津高院',
        r'来源\s*[:：]\s*青岛中院',
        r'来源\s*[:：]\s*湖南高院',
        r'来源\s*[:：]\s*宁波中院',
        r'来源\s*[:：]\s*江苏高院',
        r'来源\s*[:：]\s*南京中院',
        r'扫码获取',
        r'查看.*专题',
        r'浏览知产财经',
        r'联系我们',
        r'知产财经官网',
        r'^\s*END\s*$',
    ]
    
    last_case_pos = len(text)
    for pattern in end_patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if matches:
            for m in matches:
                if m.start() < last_case_pos:
                    # Go back to find a good break point
                    last_case_pos = m.start()
    
    # Find a good paragraph break before the footer
    for i in range(last_case_pos, max(0, last_case_pos - 2000), -1):
        if text[i] == '\n' and text[i-1] == '\n':
            # Check if we're in a case section or footer
            snippet = text[max(0, i-200):i]
            if not re.search(r'典型意义|裁判结果|案情摘要|基本案情|裁判内容', snippet):
                last_case_pos = i
                break
            # If we are in a case section, keep going back to find end of that section
            if re.search(r'典型意义', snippet):
                # Find end of this case
                end_match = re.search(r'(?:▴|典型意义)', text[i:])
                if end_match:
                    last_case_pos = i + end_match.end()
                    break
    
    # Find the actual last "典型意义" section
    all_meanings = list(re.finditer(r'典型意义', text))
    if all_meanings:
        last_meaning = all_meanings[-1]
        # Find end of that section
        end_search = text[last_meaning.end():last_meaning.end()+500]
        # Find next case or footer
        next_case = re.search(r'(?:/**|案例\s*\d+|案例[一二三四五六七八九十]+|来源|扫码|END)', end_search)
        if next_case:
            last_case_pos = last_meaning.end() + next_case.start()
        else:
            last_case_pos = last_meaning.end() + 300
    
    text = text[:last_case_pos]
    
    # Convert English punctuation to Chinese
    replacements = [
        (r'\(', '（'), (r'\)', '）'),
        (r',', '，'), (r'\.', '。'), (r':', '：'), (r';', '；'),
        (r'!', '！'), (r'\?', '？'),
        (r'"', '"'), (r'"', '"'),
        (r'''\ '''', '''‘'), (r'''\ ''', '''’'),
    ]
    
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)
    
    # Convert numbers to half-width (already mostly half-width, but ensure)
    # Full-width digits: ０１２３４５６７８９ -> 0123456789
    fw_digits = '０１２３４５６７８９'
    hw_digits = '0123456789'
    for i, fd in enumerate(fw_digits):
        text = text.replace(fd, hw_digits[i])
    
    # Clean up excessive blank lines (max 1 consecutive)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove image/QR code references that are just placeholders
    text = re.sub(r'!\[.*?\]\(.*?(?:qr|QR|二维码|扫码).*?\)', '', text)
    
    # Build output with metadata header
    output = f"""# {title}

- **来源**：{court_name}
- **原文**：[点击查看]({source_url})

"""
    
    # Process case structure
    lines = text.split('\n')
    result_lines = []
    i = 0
    in_case = False
    in_section = False
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Skip obviously promotional/footer content
        if any(kw in stripped for kw in ['扫码获取', '知产财经', '联系我们', '订阅我们', '点分享', '点收藏', '点在看', '点点赞', '浏览知产财经', '查看.*专题', '往期热文', '文章原文']):
            i += 1
            continue
        
        # Case title detection - various formats
        is_case_title = False
        
        # Pattern: /** 案例1 **/ or /** 案例 **/
        if re.match(r'/\*\*\s*案例', stripped) or re.match(r'\*\*\s*案例', stripped):
            # Clean up and add as case header
            case_name = re.sub(r'/\*\*|\*\*|案例\s*\d+\s*[/\*]*|/', '', stripped).strip()
            result_lines.append(f'\n## {case_name}\n')
            is_case_title = True
        
        # Pattern: "案例1" or "案例一" as standalone
        elif re.match(r'^案例[一二三四五六七八九十\d]+$', stripped):
            # Look ahead for the actual case name
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not next_line.startswith('#'):
                    result_lines.append(f'\n## {next_line}\n')
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
        elif re.match(r'^\d+[.、]', stripped) or re.match(r'^[一二三四五六七八九十]+[.、]', stripped):
            # Clean up and add
            case_name = re.sub(r'^\d+[.、]\s*', '', stripped)
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
        
        # Skip page navigation markers
        elif '▴ 向上滑动查看更多 ▴' in stripped or '▴' in stripped:
            i += 1
            continue
        
        # Skip lines that are just decorative
        elif re.match(r'^[*\s\-—–|]+$', stripped):
            i += 1
            continue
        
        # Skip image tags
        elif stripped.startswith('![') or stripped.startswith('![](http'):
            i += 1
            continue
        
        # Skip lines with just source attribution
        elif re.match(r'^来源\s*[:：]', stripped):
            i += 1
            continue
        
        # Skip "来源：|上海市高级人民法院" style lines
        elif re.match(r'^\s*来源\s*\|?\s*上海', stripped):
            i += 1
            continue
        elif re.match(r'^\s*来源\s*\|?\s*天津', stripped):
            i += 1
            continue
        elif re.match(r'^\s*来源\s*\|?\s*青岛', stripped):
            i += 1
            continue
        elif re.match(r'^\s*来源\s*\|?\s*湖南', stripped):
            i += 1
            continue
        elif re.match(r'^\s*来源\s*\|?\s*宁波', stripped):
            i += 1
            continue
        elif re.match(r'^\s*来源\s*\|?\s*江苏', stripped):
            i += 1
            continue
        elif re.match(r'^\s*来源\s*\|?\s*南京', stripped):
            i += 1
            continue
        elif re.match(r'^\s*来源\s*\|?\s*最高', stripped):
            i += 1
            continue
        
        else:
            result_lines.append(line)
        
        i += 1
    
    # Clean up excessive blank lines again
    formatted_content = '\n'.join(result_lines)
    formatted_content = re.sub(r'\n{3,}', '\n\n', formatted_content)
    
    # Clean up lines that are just whitespace
    lines = formatted_content.split('\n')
    lines = [l for l in lines if l.strip() != '' or l == '']
    
    # Remove trailing blank lines from content
    while lines and lines[-1].strip() == '':
        lines.pop()
    
    formatted_content = '\n'.join(lines)
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
    
    # Extract just the body content (after the FreshRSS metadata block)
    # Find where the actual content starts (after the --- frontmatter)
    parts = content.split('---')
    body_start = 0
    for i, part in enumerate(parts):
        if '4月' in part and ('日，' in part or '上午' in part or '下午' in part):
            body_start = content.find(part)
            break
    else:
        # Try to find first meaningful content
        for marker in ['4月23日', '4月24日', '4月22日']:
            idx = content.find(marker)
            if idx != -1:
                body_start = idx
                break
    
    body = content[body_start:]
    
    # Remove trailing content
    end_markers = ['---', '*由 FreshRSS', '*[由 FreshRSS']
    for marker in end_markers:
        idx = body.rfind(marker)
        if idx > len(body) - 500:
            body = body[:idx]
            break
    
    formatted = format_text(body, court_name, source_url, title)
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(formatted)
    
    print(f"Formatted: {output_file}")
