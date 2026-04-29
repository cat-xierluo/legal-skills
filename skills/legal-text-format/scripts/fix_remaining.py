#!/usr/bin/env python3
"""Targeted fixes for remaining problematic files."""
import re

def fix_shanghai(filepath):
    """Fix Shanghai trade secrets file."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    result = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Fix: ## *案例目录** -> remove this line entirely
        if stripped == '## *案例目录**' or stripped == '## **案例目录**':
            i += 1
            continue
        
        # Fix: ## 案情摘要 -> ### 案情摘要
        if stripped in ['## 案情摘要', '## 案情摘要']:
            result.append('### 案情摘要')
            i += 1
            continue
        
        # Fix: ## 裁判结果 -> ### 裁判结果
        if stripped in ['## 裁判结果', '## 裁判结果']:
            result.append('### 裁判结果')
            i += 1
            continue
        
        # Fix: ## 典型意义 -> ### 典型意义
        if stripped in ['## 典型意义', '## 典型意义']:
            result.append('### 典型意义')
            i += 1
            continue
        
        # Fix: ## ****专利代理师...**** -> ## 专利代理师...
        if stripped.startswith('## ****') and stripped.endswith('****'):
            case_name = stripped[6:-4].strip()
            result.append(f'## {case_name}')
            i += 1
            continue
        
        # Fix: ## 【基本案情】 etc -> ### 【基本案情】
        if stripped.startswith('## 【') and stripped.endswith('】'):
            result.append(stripped.replace('## ', '### '))
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
    """Fix Nanjing file."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    result = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Fix: ## ****专利代理师...**** -> ## 专利代理师擅自处分专利权属纠纷案
        if stripped.startswith('## ****') and '****' in stripped[4:]:
            # Extract case name from ****name****
            inner = stripped[4:]  # Remove '## '
            if inner.startswith('****') and inner.endswith('****'):
                case_name = inner[4:-4].strip()
                result.append(f'## {case_name}')
                i += 1
                continue
        
        # Fix: case name lines like "**Case Name**" that should be ## Case Name
        if stripped.startswith('**') and stripped.endswith('**'):
            case_name = stripped[2:-2].strip()
            # Check if it looks like a case name
            if case_name and (case_name.endswith('案') or '【' in case_name):
                if '【' in case_name:
                    result.append(f'### {case_name}')
                else:
                    result.append(f'## {case_name}')
                i += 1
                continue
        
        # Fix: ## 【案件索引】 or ## 【基本案情】 etc -> ### 
        if stripped.startswith('## 【') and ('】' in stripped):
            result.append(stripped.replace('## ', '### '))
            i += 1
            continue
        
        result.append(line)
        i += 1
    
    output = '\n'.join(result)
    output = re.sub(r'\n{3,}', '\n\n', output)
    output = output.rstrip() + '\n'
    
    with open(filepath, 'w') as f:
        f.write(output)

def fix_jiangsu(filepath):
    """Fix Jiangsu file - extract case names from 案例X pattern."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    result = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Fix: case lines starting with 案例X、 or 案例X——
        m = re.match(r'^案例(\d+)[、、、](.+)', stripped)
        if m:
            case_num = m.group(1)
            rest = m.group(2).strip()
            # Extract case name after —— if present, else use full rest
            if '——' in rest:
                # Get the part after ——
                case_name = rest.split('——')[-1].strip()
            else:
                case_name = rest.strip()
            result.append(f'## {case_name}')
            i += 1
            continue
        
        result.append(line)
        i += 1
    
    output = '\n'.join(result)
    output = re.sub(r'\n{3,}', '\n\n', output)
    output = output.rstrip() + '\n'
    
    with open(filepath, 'w') as f:
        f.write(output)

def fix_shanghai_white_paper(filepath):
    """Fix Shanghai white paper file."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    result = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Remove scope artifacts
        if stripped in ['**/**', '/** **/**', '**/** **/**', '/**/', '**/**', 
                        '**/** **/**', '**典型案例**', '**目录**', '/** 案例',
                        '**/**', '**/', '/**']:
            i += 1
            continue
        
        # Fix: ## ****xxx**** -> ## xxx
        if stripped.startswith('## ****') and '****' in stripped[4:]:
            inner = stripped[4:]
            if inner.startswith('****') and inner.endswith('****'):
                case_name = inner[4:-4].strip()
                result.append(f'## {case_name}')
                i += 1
                continue
        
        # Fix: ## 【xxx】 -> ### 【xxx】
        if stripped.startswith('## 【') and '】' in stripped:
            result.append(stripped.replace('## ', '### '))
            i += 1
            continue
        
        # Fix: case name bold lines -> ## case name
        if stripped.startswith('**') and stripped.endswith('**'):
            case_name = stripped[2:-2].strip()
            if case_name and case_name.endswith('案') and len(case_name) > 5:
                result.append(f'## {case_name}')
                i += 1
                continue
            elif case_name and '【' in case_name:
                result.append(f'### {case_name}')
                i += 1
                continue
        
        result.append(line)
        i += 1
    
    output = '\n'.join(result)
    output = re.sub(r'\n{3,}', '\n\n', output)
    output = output.rstrip() + '\n'
    
    with open(filepath, 'w') as f:
        f.write(output)

def fix_shanghai_main(filepath):
    """Fix Shanghai main file - ensure 14 case headers."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    result = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Handle remaining case names without ## 
        if (stripped and 
            not stripped.startswith('#') and
            not stripped.startswith('**') and
            stripped.endswith('案') and 
            5 < len(stripped) < 120):
            prefixes = ['侵害', '涉', '确认', '假冒', '走秀', '误导', 'AI', '人工智能',
                       '卡牌', '在先权益', '恶意', '爬取', 'B服', '供热', '改编',
                       '虚构', '传播', '反向', '某种', '某移动', '某实业', '某科技',
                       '某酒店', '某生物', '杜某', '某化', '某网络', '某文化', '某传媒']
            for prefix in prefixes:
                if stripped.startswith(prefix):
                    # Check if prev line is already a ## header
                    if result and result[-1].strip().startswith('## '):
                        pass  # Already has header
                    else:
                        result.append(f'## {stripped}')
                        i += 1
                        continue
        
        result.append(line)
        i += 1
    
    output = '\n'.join(result)
    output = re.sub(r'\n{3,}', '\n\n', output)
    output = output.rstrip() + '\n'
    
    with open(filepath, 'w') as f:
        f.write(output)

# Run fixes
base = '/Users/maoking/.openclaw/skills/legal-text-format/archive/'

fix_shanghai(base + '20260425_120006_上海高院涉商业秘密保护典型案例/20260425_上海高院涉商业秘密保护典型案例_formatted.md')
print("Fixed Shanghai trade secrets")

fix_nanjing(base + '20260425_120007_南京中院2025年南京法院知识产权十大案例/20260425_南京中院2025年南京法院知识产权十大案例_formatted.md')
print("Fixed Nanjing")

fix_jiangsu(base + '20260425_120005_江苏高院2025年服务保障科技创新和产业创新融合知产典型案例/20260425_江苏高院2025年服务保障科技创新和产业创新融合知产典型案例_formatted.md')
print("Fixed Jiangsu")

fix_shanghai_white_paper(base + '20260425_120008_上海法院知识产权审判白皮书和典型案例/20260425_上海法院知识产权审判白皮书和典型案例_formatted.md')
print("Fixed Shanghai white paper")

fix_shanghai_main(base + '20260425_120000_上海高院2025年知识产权司法保护典型案例/20260425_上海高院2025年知识产权司法保护典型案例_formatted.md')
print("Fixed Shanghai main")
