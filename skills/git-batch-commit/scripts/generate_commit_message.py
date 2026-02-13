#!/usr/bin/env python3
"""
Generate conventional commit messages based on change type and content.

使用小写英文前缀 + 中文冒号 + 中文描述的格式：
- docs：文档变更
- feat：新功能
- fix：Bug 修复
- refactor：代码重构
- style：代码风格调整
- chore：构建工具、依赖更新
- test：测试变更
- config：配置变更
- license：许可证文件更新

注意：实际输出使用英文冒号 (:) 以支持 GitHub 彩色标签
"""

import subprocess
import re
import argparse
from typing import List, Dict


# Category to commit type mapping (小写英文)
CATEGORY_TO_TYPE = {
    'deps': 'chore',
    'docs': 'docs',
    'license': 'license',
    'config': 'config',
    'test': 'test',
    'chore': 'chore',
    'feat': 'feat',
    'fix': 'fix',
    'refactor': 'refactor',
    'style': 'style',
    'code': 'style',  # Default for uncategorized code
    'other': 'chore',
}

# Common commit message templates by category (中文)
MESSAGE_TEMPLATES = {
    'deps': {
        'patterns': [
            (r'package\.json', '更新 JavaScript 依赖'),
            (r'requirements\.txt', '更新 Python 依赖'),
            (r'go\.(mod|sum)', '更新 Go 依赖'),
            (r'Gemfile', '更新 Ruby 依赖'),
            (r'Cargo\.toml', '更新 Rust 依赖'),
            (r'pyproject\.toml', '更新 Python 项目配置'),
        ],
        'default': '更新依赖',
    },
    'docs': {
        'patterns': [
            (r'README', '更新 README 文档'),
            (r'CHANGELOG', '更新变更日志'),
            (r'CONTRIBUTING', '更新贡献指南'),
            (r'ARCHITECTURE', '更新架构文档'),
            (r'AGENTS\.md', '更新协作规范文档'),
            (r'SKILL-GUIDE\.md', '更新 Skill 开发指南'),
            (r'skills/([^/]+)/SKILL\.md', r'添加 \1 技能文档'),
        ],
        'default': '更新文档',
    },
    'license': {
        'default': '更新许可证文件',
    },
    'config': {
        'patterns': [
            (r'\.env\.example', '更新环境变量示例'),
            (r'\.yaml|\.yml', '更新 YAML 配置'),
            (r'toml', '更新 TOML 配置'),
        ],
        'default': '更新配置',
    },
    'test': {
        'default': '更新测试',
    },
    'chore': {
        'patterns': [
            (r'\.gitignore', '更新 gitignore 忽略规则'),
            (r'Dockerfile', '更新 Docker 配置'),
            (r'\.github/', '更新 GitHub 工作流'),
            (r'Makefile', '更新 Makefile'),
        ],
        'default': '更新工具配置',
    },
    'feat': {
        'patterns': [
            (r'skills/([^/]+)/', r'添加 \1 技能'),
            (r'scripts/([^/]+)', r'添加 \1 脚本'),
            (r'test/([^/]+)', r'添加 \1 测试'),
        ],
        'default': '添加新功能',
    },
    'fix': {
        'default': '修复 Bug',
    },
    'refactor': {
        'default': '重构代码',
    },
    'style': {
        'default': '调整代码风格',
    },
}


def get_file_changes(filepath: str) -> str:
    """Get git diff for a specific file."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', filepath],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return ""


def analyze_changes(files: List[str], category: str) -> str:
    """
    分析文件变更以生成具体的描述信息。

    返回变更的具体描述。
    """
    if not files:
        return ""

    # Try to match patterns
    if category in MESSAGE_TEMPLATES:
        templates = MESSAGE_TEMPLATES[category]
        if 'patterns' in templates:
            for pattern, message in templates['patterns']:
                for filepath in files:
                    if re.search(pattern, filepath):
                        # If message contains regex group reference, substitute it
                        if r'\1' in message or r'\2' in message:
                            match = re.search(pattern, filepath)
                            if match:
                                try:
                                    result = message
                                    for i in range(1, len(match.groups()) + 1):
                                        result = result.replace(f'\\{i}', match.group(i))
                                    return result
                                except IndexError:
                                    pass
                        return message

        # Use default template
        if 'default' in templates:
            base_msg = templates['default']

            # Enhance with file-specific info
            if len(files) == 1:
                filepath = files[0]
                filename = filepath.split('/')[-1]

                # For markdown docs, extract doc name
                if category == 'docs' and filename.endswith('.md'):
                    doc_name = filename.replace('.md', '')
                    # Handle special cases
                    if doc_name == 'README':
                        return '更新 README 文档'
                    elif doc_name == 'CHANGELOG':
                        return '更新变更日志'
                    elif doc_name == 'AGENTS':
                        return '更新协作规范文档'
                    elif doc_name == 'SKILL-GUIDE':
                        return '更新 Skill 开发指南'
                    else:
                        return f'更新 {doc_name} 文档'

                # For skill files
                if 'skills/' in filepath:
                    skill_name = filepath.split('skills/')[1].split('/')[0]
                    return f'添加 {skill_name} 技能'

                # For config files, mention specific config
                if category == 'config':
                    if filename.endswith(('.yaml', '.yml')):
                        return f'更新 {filename} 配置'
                    elif filename.endswith('.toml'):
                        return f'更新 {filename} 配置'

            # Multiple files: mention count
            return f'{base_msg}({len(files)} 个文件)'

    # Fallback: generic message based on category
    return f'更新 {category} 文件'


def generate_commit_message(category: str, files: List[str]) -> str:
    """
    生成约定式提交信息，包含详细信息。

    格式：
    <type>: <描述>

    - 详细变更说明1
    - 详细变更说明2

    Args:
        category: 变更类别 (deps, docs, feat 等)
        files: 该类别中的变更文件列表

    Returns:
        格式化的提交信息（包含详细信息）
    """
    # Get commit type
    commit_type = CATEGORY_TO_TYPE.get(category, 'chore')

    # Generate description
    description = analyze_changes(files, category)

    # Generate detailed body based on files
    detail_lines = generate_detail_lines(files, category)

    # Format: type: description (使用英文冒号以支持 GitHub 彩色标签)
    message = f"{commit_type}: {description}"

    # Add detail lines if available
    if detail_lines:
        message += "\n\n" + detail_lines

    return message


def get_file_diff(filepath: str) -> str:
    """Get git diff for a specific file."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', filepath],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return ""


def analyze_diff_content(diff: str, filename: str) -> str:
    """
    分析 diff 内容，生成具体的变更描述。

    Args:
        diff: git diff 内容
        filename: 文件名

    Returns:
        具体的变更描述
    """
    if not diff:
        return f"更新 {filename}"

    lines = diff.split('\n')
    added_lines = []
    removed_lines = []

    for line in lines:
        if line.startswith('+') and not line.startswith('+++'):
            content = line[1:].strip()
            if content and not content.startswith('\\'):
                added_lines.append(content)
        elif line.startswith('-') and not line.startswith('---'):
            content = line[1:].strip()
            if content and not content.startswith('\\'):
                removed_lines.append(content)

    # Analyze based on file type
    if filename.endswith('.md'):
        return analyze_markdown_changes(added_lines, removed_lines, filename)
    elif filename.endswith('.py'):
        return analyze_code_changes(added_lines, removed_lines, filename)
    elif '.gitignore' in filename:
        return analyze_gitignore_changes(added_lines, removed_lines)
    elif filename.endswith(('.yaml', '.yml', '.json', '.toml')):
        return analyze_config_changes(added_lines, removed_lines, filename)
    else:
        return analyze_generic_changes(added_lines, removed_lines, filename)


def analyze_markdown_changes(added: List[str], removed: List[str], filename: str) -> str:
    """分析 Markdown 文件变更。"""
    # Check for new sections/headers
    added_headers = [l for l in added if l.startswith('#')]

    if added_headers:
        header_text = added_headers[0].lstrip('#').strip()
        return f"更新 {filename} - 添加 {header_text} 部分"

    # Check for skill additions
    if 'skills/' in filename or 'SKILL' in filename:
        skill_name = filename.split('/')[-1].replace('.md', '')
        if '添加' in ' '.join(added) or '新增' in ' '.join(added):
            return f"添加 {skill_name} 技能文档"
        return f"更新 {skill_name} 技能文档"

    # Check for doc updates
    if added:
        return f"更新 {filename} 文档内容"
    elif removed:
        return f"修改 {filename} 文档内容"

    return f"更新 {filename}"


def analyze_code_changes(added: List[str], removed: List[str], filename: str) -> str:
    """分析代码文件变更。"""
    # Look for function/class definitions
    added_funcs = [l for l in added if 'def ' in l or 'class ' in l or 'function ' in l]
    added_imports = [l for l in added if 'import ' in l or 'from ' in l]

    # Look for specific keywords
    changes = []
    if any('fix' in l.lower() or 'bug' in l.lower() for l in added + removed):
        changes.append("修复问题")
    if any('add' in l.lower() or 'new' in l.lower() for l in added + removed):
        changes.append("添加新功能")
    if any('update' in l.lower() for l in added + removed):
        changes.append("更新功能")

    if added_funcs:
        func_name = added_funcs[0].strip()
        return f"更新 {filename} - 添加 {func_name}"
    elif changes:
        return f"更新 {filename} - {'、'.join(changes)}"
    elif added_imports:
        return f"更新 {filename} - 添加导入"

    return f"更新 {filename} 代码"


def analyze_gitignore_changes(added: List[str], removed: List[str]) -> str:
    """分析 .gitignore 变更。"""
    if added:
        # Extract patterns that were added
        patterns = [l.lstrip('#').strip() for l in added if l and not l.startswith('#')]
        if patterns:
            # Summarize the types of patterns
            summary = []
            for p in patterns[:3]:  # Show up to 3 patterns
                if '__pycache__' in p or '.pyc' in p:
                    summary.append('Python缓存')
                elif '.log' in p:
                    summary.append('日志文件')
                elif '.db' in p or 'sqlite' in p:
                    summary.append('数据库文件')
                elif 'node_modules' in p:
                    summary.append('Node依赖')
                elif 'logs' in p:
                    summary.append('日志目录')
                elif '.playwright' in p:
                    summary.append('Playwright数据')
                else:
                    summary.append(p)

            if summary:
                return f"更新 gitignore 忽略规则 - 添加 {', '.join(summary)}"

    return "更新 gitignore 忽略规则"


def analyze_config_changes(added: List[str], removed: List[str], filename: str) -> str:
    """分析配置文件变更。"""
    if added:
        # Look for key changes
        added_keys = [l.split(':')[0].strip() for l in added if ':' in l]
        if added_keys:
            return f"更新 {filename} - 添加 {', '.join(added_keys[:2])} 配置"

    return f"更新 {filename} 配置"


def analyze_generic_changes(added: List[str], removed: List[str], filename: str) -> str:
    """分析通用文件变更。"""
    if added:
        return f"更新 {filename}"
    elif removed:
        return f"删除 {filename} 中的内容"

    return f"修改 {filename}"


def generate_detail_lines(files: List[str], category: str) -> str:
    """
    根据变更文件生成详细信息行。

    Args:
        files: 变更文件列表
        category: 变更类别

    Returns:
        详细信息字符串
    """
    lines = []

    for filepath in files:
        filename = filepath.split('/')[-1]

        # Get diff content for analysis
        diff = get_file_diff(filepath)

        # Analyze and generate description
        description = analyze_diff_content(diff, filename)
        lines.append(f"- {description}")

    return "\n".join(lines)


def generate_commit_messages(groups: Dict[str, List[str]]) -> Dict[str, str]:
    """
    为所有分组生成提交信息。

    Args:
        groups: 变更类别到文件列表的映射

    Returns:
        类别到提交信息的映射
    """
    messages = {}
    for category, files in groups.items():
        messages[category] = generate_commit_message(category, files)
    return messages


def main():
    """命令行使用的主入口。"""
    parser = argparse.ArgumentParser(
        description='生成约定式提交信息'
    )
    parser.add_argument(
        '--category',
        type=str,
        help='变更类别 (deps, docs, feat 等)'
    )
    parser.add_argument(
        '--files',
        nargs='+',
        help='变更文件列表'
    )

    args = parser.parse_args()

    if args.category and args.files:
        msg = generate_commit_message(args.category, args.files)
        print(msg)
    else:
        print("用法: generate_commit_message.py --category <类型> --files <文件1> [文件2...]")


if __name__ == '__main__':
    main()
