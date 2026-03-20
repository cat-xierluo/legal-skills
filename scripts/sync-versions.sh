#!/bin/bash
# sync-versions.sh - 从 CHANGELOG 提取版本并更新 SKILL.md frontmatter

set -e

SKILLS_DIR="skills"
FIXED_AUTHOR="杨卫薪律师（微信ywxlaw）"
FIXED_HOMEPAGE="https://github.com/cat-xierluo/legal-skills"
FIXED_SOURCE="https://github.com/cat-xierluo/legal-skills"

python3 << 'PYTHON_SCRIPT'
import re
import os
import sys

skills_dir = "skills"
fixed_author = "杨卫薪律师（微信ywxlaw）"
fixed_homepage = "https://github.com/cat-xierluo/legal-skills"
fixed_source = "https://github.com/cat-xierluo/legal-skills"

for skill_name in os.listdir(skills_dir):
    skill_dir = os.path.join(skills_dir, skill_name)
    if not os.path.isdir(skill_dir):
        continue
    
    changelog = os.path.join(skill_dir, "CHANGELOG.md")
    skill_md = os.path.join(skill_dir, "SKILL.md")
    
    if not os.path.exists(changelog):
        print(f"⚠️  {skill_name}: 缺少 CHANGELOG.md，跳过")
        continue
    
    if not os.path.exists(skill_md):
        print(f"⚠️  {skill_name}: 缺少 SKILL.md，跳过")
        continue
    
    # 提取版本号
    with open(changelog, 'r', encoding='utf-8') as f:
        changelog_content = f.read()
    
    version = None
    # Try [x.y.z] or [vx.y.z] format
    match = re.search(r'^## \[v?([\d.]+)\]', changelog_content, re.MULTILINE)
    if match:
        version = match.group(1)
    else:
        # Try vx.y.z format (no brackets)
        match = re.search(r'^## v([\d.]+)', changelog_content, re.MULTILINE)
        if match:
            version = match.group(1)
    
    if not version:
        print(f"⚠️  {skill_name}: 无法提取版本号，跳过")
        continue
    
    print(f"📝 {skill_name}: {version}")
    
    # 读取并更新 SKILL.md
    with open(skill_md, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 解析 frontmatter
    frontmatter_match = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
    if not frontmatter_match:
        print(f"⚠️  {skill_name}: 无法解析 frontmatter")
        continue
    
    frontmatter = frontmatter_match.group(1)
    rest = content[frontmatter_match.end():]
    
    def update_field(fm, key, value):
        if re.search(rf'^{key}:', fm, re.MULTILINE):
            return re.sub(rf'^{key}:.*', f'{key}: {value}', fm, flags=re.MULTILINE)
        else:
            lines = fm.split('\n')
            lines.insert(1, f'{key}: {value}')
            return '\n'.join(lines)
    
    frontmatter = update_field(frontmatter, 'version', f'"{version}"')
    frontmatter = update_field(frontmatter, 'author', fixed_author)
    frontmatter = update_field(frontmatter, 'homepage', fixed_homepage)
    frontmatter = update_field(frontmatter, 'source', fixed_source)
    
    new_content = f'---\n{frontmatter}\n---\n{rest}'
    with open(skill_md, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"✅ {skill_name}: 已更新")

print("\n完成！运行 'clawhub sync --dry-run' 预览发布内容。")
PYTHON_SCRIPT
