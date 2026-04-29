#!/usr/bin/env python3
"""Fix Nanjing file - convert the comment-format case names to proper ## headers."""
import re

filepath = '/Users/maoking/.openclaw/skills/legal-text-format/archive/20260425_120007_南京中院2025年南京法院知识产权十大案例/20260425_南京中院2025年南京法院知识产权十大案例_formatted.md'

with open(filepath) as f:
    lines = f.readlines()

result = []
i = 0
while i < len(lines):
    line = lines[i]
    stripped = line.strip()
    
    # Pattern: "# **CaseName**" followed by "#  ——FullCaseName" or "#  FullDescription"
    if stripped.startswith('# **') and not stripped.startswith('###'):
        # Extract case name from the bold section
        # Try to combine with next line(s) that are also comment-style
        case_name_parts = []
        if '**' in stripped:
            # Extract text between ** ** 
            m = re.search(r'\*\*([^*]+)\*\*', stripped)
            if m:
                case_name_parts.append(m.group(1).strip())
        
        # Check next lines for continuation (the "——" line)
        j = i + 1
        while j < min(i + 3, len(lines)):
            next_stripped = lines[j].strip()
            if next_stripped.startswith('#  ——'):
                # Full case name with parties
                full = next_stripped[5:].strip()  # Remove '#  ——'
                case_name_parts.append(full)
                j += 1
                break
            elif next_stripped.startswith('# ') and not next_stripped.startswith('###'):
                case_name_parts.append(next_stripped[2:].strip())
                j += 1
                break
            elif next_stripped.startswith('#'):
                break
            else:
                break
        
        if case_name_parts:
            full_name = ' '.join(case_name_parts)
            result.append(f'## {full_name}\n')
            i = j
            continue
    
    result.append(line)
    i += 1

output = ''.join(result)
output = re.sub(r'\n{3,}', '\n\n', output)
output = output.rstrip() + '\n'

with open(filepath, 'w') as f:
    f.write(output)

print("Fixed Nanjing case headers")

# Verify
with open(filepath) as f:
    content = f.read()
headers = re.findall(r'^## (.+)$', content, re.MULTILINE)
print(f"Total ## headers: {len(headers)}/10")
for h in headers:
    print(f"  ## {h[:70]}")
