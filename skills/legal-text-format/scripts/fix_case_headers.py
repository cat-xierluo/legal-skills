#!/usr/bin/env python3
"""
Fix case headers across all 9 formatted files.
Main fix: "##\n**Case Name**" -> "## Case Name"
"""
import re

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    result = []
    i = 0
    n = len(lines)
    
    while i < n:
        line = lines[i]
        stripped = line.strip()
        
        # Pattern: "##" or "## " on its own line, followed by bold case name
        if stripped == '##' or stripped == '##':
            if i + 1 < n:
                next_stripped = lines[i + 1].strip()
                # Check if next line is **Case Name** (bold)
                if next_stripped.startswith('**') and next_stripped.endswith('**'):
                    case_name = next_stripped[2:-2].strip()
                    if case_name:
                        result.append(f'## {case_name}')
                        i += 2
                        continue
                # Check if next line is a plain case name (starts with known prefix)
                elif next_stripped:
                    prefixes = ['侵害', '涉', '确认', '假冒', '走秀', '误导', 'AI', '人工智能',
                               '卡牌', '在先权益', '恶意', '某种', '某移动', '某实业', '某科技',
                               '某酒店', '某生物', '杜某', '某化', '某网络', '某文化', '某传媒',
                               '某钢', '某化', '某制', '某光', '某医药', '某服装', '某电器']
                    for prefix in prefixes:
                        if next_stripped.startswith(prefix):
                            result.append(f'## {next_stripped}')
                            i += 2
                            continue
                    # It was a standalone ## with nothing meaningful after
                    result.append(line)
                    i += 1
                    continue
        
        # Remove scope artifacts
        skip_patterns = ['**/**', '/** **/**', '**/** **/**', '/**/', '**/**', 
                        '**/** **/**', '**典型案例**', '**目录**', '/** 案例']
        if stripped in skip_patterns:
            i += 1
            continue
        
        # Handle lines that are just bold markers
        if stripped in ['/**', '**/', '/**', '**']:
            i += 1
            continue
        
        result.append(line)
        i += 1
    
    output = '\n'.join(result)
    
    # Clean excessive blank lines
    output = re.sub(r'\n{3,}', '\n\n', output)
    output = output.rstrip() + '\n'
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(output)

def main():
    base = '/Users/maoking/.openclaw/skills/legal-text-format/archive/'
    
    files = [
        '20260425_120000_上海高院2025年知识产权司法保护典型案例/20260425_上海高院2025年知识产权司法保护典型案例_formatted.md',
        '20260425_120001_天津高院2025年天津法院知识产权典型案例/20260425_天津高院2025年天津法院知识产权典型案例_formatted.md',
        '20260425_120002_青岛中院2025年青岛法院知识产权司法保护典型案例/20260425_青岛中院2025年青岛法院知识产权司法保护典型案例_formatted.md',
        '20260425_120003_湖南高院2025年知识产权司法保护状况及服务保障新质生产力发展典型案例/20260425_湖南高院2025年知识产权司法保护状况及服务保障新质生产力发展典型案例_formatted.md',
        '20260425_120004_宁波中院2025年度宁波法院知识产权审判典型案例/20260425_宁波中院2025年度宁波法院知识产权审判典型案例_formatted.md',
        '20260425_120005_江苏高院2025年服务保障科技创新和产业创新融合知产典型案例/20260425_江苏高院2025年服务保障科技创新和产业创新融合知产典型案例_formatted.md',
        '20260425_120006_上海高院涉商业秘密保护典型案例/20260425_上海高院涉商业秘密保护典型案例_formatted.md',
        '20260425_120007_南京中院2025年南京法院知识产权十大案例/20260425_南京中院2025年南京法院知识产权十大案例_formatted.md',
        '20260425_120008_上海法院知识产权审判白皮书和典型案例/20260425_上海法院知识产权审判白皮书和典型案例_formatted.md',
    ]
    
    for f in files:
        try:
            fix_file(base + f)
            print(f"Fixed: {f}")
        except Exception as e:
            print(f"Error: {f}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    main()
