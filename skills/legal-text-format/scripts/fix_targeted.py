#!/usr/bin/env python3
"""Targeted fixes for remaining problem files - more careful approach."""
import re

def fix_shanghai_ts(filepath):
    """Fix Shanghai trade secrets: add ## to case names, fix section headers."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    result = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Case names in bold: **Case Name** (standalone or with subtitle on next line)
        if stripped.startswith('**') and stripped.endswith('**'):
            inner = stripped[2:-2].strip()
            if '【' in inner:
                # Section header like **【基本案情】** -> ### 【基本案情】
                result.append(f'### {inner}')
                i += 1
                continue
            elif inner.endswith('案') and len(inner) > 4:
                # Case name like **涉红外遥控技术秘密侵权纠纷案** -> ## 
                result.append(f'## {inner}')
                i += 1
                continue
            elif '——' in inner or '"' in inner:
                # Split case name, check next line
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line.startswith('**') and next_line.endswith('**'):
                        # Combine with next bold line
                        next_inner = next_line[2:-2].strip()
                        full_name = f"{inner}——{next_inner}"
                        result.append(f'## {full_name}')
                        i += 2
                        continue
                result.append(f'## {inner}')
                i += 1
                continue
        
        result.append(line)
        i += 1
    
    output = '\n'.join(result)
    output = re.sub(r'\n{3,}', '\n\n', output)
    output = output.rstrip() + '\n'
    
    with open(filepath, 'w') as f:
        f.write(output)

def fix_nanjing(filepath):
    """Fix Nanjing: clean case headers, remove extra asterisks."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    result = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Fix: ## ****case name**** -> ## case name
        if '****' in stripped and stripped.startswith('## '):
            # Remove all **** occurrences
            cleaned = stripped.replace('****', '').strip()
            result.append(f'## {cleaned}')
            i += 1
            continue
        
        # Fix: Bold case name lines
        if stripped.startswith('**') and stripped.endswith('**'):
            inner = stripped[2:-2].strip()
            if inner.endswith('案') and len(inner) > 4:
                result.append(f'## {inner}')
                i += 1
                continue
            elif '【' in inner:
                result.append(f'### {inner}')
                i += 1
                continue
        
        # Fix: Split case name on multiple lines (like "# **寄生**" + "# **"生意参谋"**...")
        if stripped.startswith('# **') or stripped.startswith('## **'):
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith('**'):
                    # Combine lines
                    combined = stripped + next_line
                    combined_clean = combined.replace('# ', '').replace('## ', '').replace('****', '').replace('**', '').strip()
                    if combined_clean.endswith('案'):
                        result.append(f'## {combined_clean}')
                        i += 2
                        continue
        
        result.append(line)
        i += 1
    
    output = '\n'.join(result)
    output = re.sub(r'\n{3,}', '\n\n', output)
    output = output.rstrip() + '\n'
    
    with open(filepath, 'w') as f:
        f.write(output)

def fix_white_paper(filepath):
    """Fix Shanghai white paper."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    result = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Remove scope artifacts
        skip_patterns = ['**/**', '/** **/**', '**/** **/**', '/**/', 
                        '**/**', '**/** **/**', '**典型案例**', '**目录**', 
                        '/** 案例', '/**', '**/']
        if stripped in skip_patterns:
            continue
        
        # Fix: ## ****case**** -> ## case
        if '****' in stripped and stripped.startswith('##'):
            cleaned = stripped.replace('****', '').strip()
            result.append(cleaned)
            continue
        
        # Fix: bold case names
        if stripped.startswith('**') and stripped.endswith('**'):
            inner = stripped[2:-2].strip()
            if inner.endswith('案') and len(inner) > 4:
                result.append(f'## {inner}')
                continue
            elif '【' in inner:
                result.append(f'### {inner}')
                continue
        
        # Fix: bold headers like **【案件索引】**
        if stripped.startswith('**') and '【' in stripped and '】' in stripped:
            inner = stripped[2:-2].strip()
            result.append(f'### {inner}')
            continue
        
        result.append(line)
    
    output = '\n'.join(result)
    output = re.sub(r'\n{3,}', '\n\n', output)
    output = output.rstrip() + '\n'
    
    with open(filepath, 'w') as f:
        f.write(output)

def fix_shanghai_main(filepath):
    """Fix Shanghai main - add missing ## to any remaining plain text case names."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    result = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Check if this is a case name without ## 
        if (stripped and 
            not stripped.startswith('#') and
            not stripped.startswith('**') and
            stripped.endswith('案') and 
            5 < len(stripped) < 120):
            prefixes = ['侵害', '涉', '确认', '假冒', '走秀', '误导', 'AI', '人工智能',
                       '卡牌', '在先权益', '恶意', '爬取', 'B服', '供热', '改编',
                       '虚构', '传播', '反向', '某种', '某移动', '某实业', '某科技',
                       '某酒店', '某生物', '杜某', '某化', '某网络', '某文化', '某传媒',
                       '某钢', '某制', '某光', '某医药', '某服装', '某电器', '某机械']
            is_case = any(stripped.startswith(p) for p in prefixes)
            
            if is_case:
                # Check if previous added line is already a ## header for this
                if result and result[-1].strip().startswith('## '):
                    pass  # Already has header
                else:
                    result.append(f'## {stripped}')
                    continue
        
        result.append(line)
    
    output = '\n'.join(result)
    output = re.sub(r'\n{3,}', '\n\n', output)
    output = output.rstrip() + '\n'
    
    with open(filepath, 'w') as f:
        f.write(output)

base = '/Users/maoking/.openclaw/skills/legal-text-format/archive/'

fix_shanghai_ts(base + '20260425_120006_上海高院涉商业秘密保护典型案例/20260425_上海高院涉商业秘密保护典型案例_formatted.md')
print("Fixed Shanghai trade secrets")

fix_nanjing(base + '20260425_120007_南京中院2025年南京法院知识产权十大案例/20260425_南京中院2025年南京法院知识产权十大案例_formatted.md')
print("Fixed Nanjing")

fix_white_paper(base + '20260425_120008_上海法院知识产权审判白皮书和典型案例/20260425_上海法院知识产权审判白皮书和典型案例_formatted.md')
print("Fixed Shanghai white paper")

fix_shanghai_main(base + '20260425_120000_上海高院2025年知识产权司法保护典型案例/20260425_上海高院2025年知识产权司法保护典型案例_formatted.md')
print("Fixed Shanghai main")
