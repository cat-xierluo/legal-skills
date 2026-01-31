#!/usr/bin/env python3
"""
Generate conventional commit messages based on change type and content.

支持标准化中文前缀：
- Docs：文档变更
- Feat：新功能
- Fix：Bug 修复
- Refactor：代码重构
- Style：代码风格调整
- Chore：构建工具、依赖更新
- Test：测试变更
- Config：配置变更
- License：许可证文件更新
"""

import subprocess
import re
import argparse
from typing import List, Dict


# Category to commit type mapping (中文)
CATEGORY_TO_TYPE = {
    'deps': 'Chore',
    'docs': 'Docs',
    'license': 'License',
    'config': 'Config',
    'test': 'Test',
    'chore': 'Chore',
    'feat': 'Feat',
    'fix': 'Fix',
    'refactor': 'Refactor',
    'style': 'Style',
    'code': 'Style',  # Default for uncategorized code
    'other': 'Chore',
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
    生成约定式提交信息。

    格式：<Type>：<描述>

    Args:
        category: 变更类别 (deps, docs, feat 等)
        files: 该类别中的变更文件列表

    Returns:
        格式化的提交信息
    """
    # Get commit type
    commit_type = CATEGORY_TO_TYPE.get(category, 'Chore')

    # Generate description
    description = analyze_changes(files, category)

    # Format: Type：Description (使用中文冒号)
    return f"{commit_type}：{description}"


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
