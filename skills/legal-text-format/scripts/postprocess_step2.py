#!/usr/bin/env python3
"""Post-process formatted legal case files - clean up remaining formatting artifacts."""
import re
import os

def postprocess(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    result = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Skip known artifact lines
        skip_set = {
            '**典型案例**', '**目录**', '**/** **/**',
        }
        
        # Skip bold scope artifacts
        if stripped in skip_set:
            i += 1
            continue
        
        # Skip case separators like " /** 案例1 **/ " or " **/** **案例1** **/** "
        # Check for patterns containing "案例" in bold markers
        if ('案例' in stripped and stripped.count('*') >= 2 and 
            all(c in stripped for c in ['/**', '**'])):
            i += 1
            continue
        
        # Skip patterns like " /** **案例1** **/"
        if re.match(r'^/\*\*\s*案例', stripped) or re.match(r'^\*\*\s*案例', stripped):
            i += 1
            continue
        
        # Skip stray bold markers
        if stripped in ('/**', '**/', '/**/', '**/**', '/** **/**'):
            i += 1
            continue
        
        # Handle case separator /** 案例X **/ with case name on next line
        if re.search(r'/\*\*.*案例.*\*\*/', stripped) or re.search(r'\*\*.*案例.*\*\*', stripped):
            # Get case name from next line
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not next_line.startswith('#'):
                    result.append(f'\n## {next_line}\n')
                    i += 2
                    continue
            i += 1
            continue
        
        result.append(line)
        i += 1
    
    output = '\n'.join(result)
    
    # Clean excessive blank lines
    output = re.sub(r'\n{3,}', '\n\n', output)
    
    # Remove trailing blank lines
    output = output.rstrip() + '\n'
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(output)
    
    print(f"Post-processed: {filepath}")

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
            postprocess(base + f)
        except Exception as e:
            print(f"Error: {f}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    main()
