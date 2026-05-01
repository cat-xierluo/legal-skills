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
import yaml
from pathlib import Path
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

# Load configuration from YAML
_DATA_PATH = Path(__file__).parent.parent / 'references' / 'message-data.yaml'
with open(_DATA_PATH, encoding='utf-8') as _f:
    _DATA = yaml.safe_load(_f)

# Build FILE_TO_FUNCTION_MAP from YAML (list of {pattern, description})
FILE_TO_FUNCTION_MAP = _DATA['file_to_function_map']

# Build MESSAGE_TEMPLATES from YAML (convert patterns from list to tuple format)
MESSAGE_TEMPLATES = {}
for _cat, _tpl in _DATA['message_templates'].items():
    if 'patterns' in _tpl:
        MESSAGE_TEMPLATES[_cat] = {
            'patterns': [(p['pattern'], p['message']) for p in _tpl['patterns']],
            'default': _tpl['default'],
        }
    else:
        MESSAGE_TEMPLATES[_cat] = {'default': _tpl['default']}

FUNCTION_PREFIX_ACTIONS = _DATA['function_prefix_actions']
CONFIG_KEY_MEANINGS = _DATA['config_key_meanings']


def parse_skill_category(category: str):
    """
    Parse skill:<name>:<type> format.

    Returns (skill_name, commit_type) if skill category, else (None, None).
    """
    if category.startswith('skill:'):
        parts = category.split(':')
        if len(parts) == 3:
            return parts[1], parts[2]  # (skill_name, commit_type)
    return None, None


def detect_skill_name(files: List[str]) -> str | None:
    """
    检测文件是否属于某个技能，返回技能名称。

    Args:
        files: 文件列表

    Returns:
        技能名称，如果不属于任何技能则返回 None
    """
    if not files:
        return None

    for filepath in files:
        # Check if this is a skill file (skills/<skill-name>/...)
        if '/skills/' in filepath:
            parts = filepath.split('/skills/')
            if len(parts) > 1:
                skill_path = parts[1]
                skill_name = skill_path.split('/')[0]
                if skill_name and skill_name != 'skills':
                    return skill_name

    return None


def is_new_skill_being_added(skill_name: str, files: List[str]) -> bool:
    """
    检测是否正在添加新技能（而非更新现有技能）。

    判断逻辑：
    1. 检查 SKILL.md 文件是否已存在于 HEAD 提交中
    2. 如果不存在 → 新技能
    3. 否则 → 更新现有技能

    Args:
        skill_name: 技能名称
        files: 本次提交涉及的文件列表

    Returns:
        True 表示新技能，False 表示更新现有技能
    """
    # 检查 SKILL.md 是否是新文件（不存在于 HEAD 提交中）
    for filepath in files:
        if filepath.endswith('SKILL.md'):
            try:
                # 使用 git cat-file 检查文件是否在 HEAD 中存在
                result = subprocess.run(
                    ['git', 'cat-file', '-e', f'HEAD:{filepath}'],
                    capture_output=True,
                    text=True,
                )
                # 如果返回码非 0，说明文件不在 HEAD 中，是新技能
                if result.returncode != 0:
                    return True
            except Exception:
                # 出错时保守处理，视为更新
                pass

    return False


def analyze_changes(files: List[str], category: str) -> str:
    """
    分析文件变更以生成具体的描述信息。

    返回变更的具体描述。
    """
    if not files:
        return ""

    # Handle skill:<name>:<type> format - extract the actual type
    skill_name_parsed, actual_category = parse_skill_category(category)
    is_skill_format = skill_name_parsed is not None
    if not is_skill_format:
        actual_category = category

    # 优先处理技能文件（跳过通用 patterns 匹配）
    # 技能文件需要特殊处理，不能被 scripts/、test/ 等通用模式提前匹配
    if len(files) == 1:
        filepath = files[0]
        if 'skills/' in filepath:
            filename = filepath.split('/')[-1]
            skill_name_from_path = filepath.split('skills/')[1].split('/')[0]
            # 检测是否为新技能（SKILL.md 未被 git 跟踪）
            if is_new_skill_being_added(skill_name_from_path, files):
                return f'添加 {skill_name_from_path} 技能'
            else:
                # 分析具体变更内容，生成有意义的描述
                diff = get_file_diff(filepath)
                specific_change = analyze_diff_content(diff, filename)
                return specific_change

    # Try to match patterns
    if actual_category in MESSAGE_TEMPLATES:
        templates = MESSAGE_TEMPLATES[actual_category]
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
                if actual_category == 'docs' and filename.endswith('.md'):
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

                # For config files, mention specific config
                if actual_category == 'config':
                    if filename.endswith(('.yaml', '.yml')):
                        return f'更新 {filename} 配置'
                    elif filename.endswith('.toml'):
                        return f'更新 {filename} 配置'

            # Multiple files: mention count
            return f'{base_msg}({len(files)} 个文件)'

    # Fallback: generic message based on actual_category
    return f'更新 {actual_category} 文件'


def generate_commit_message(category: str, files: List[str]) -> str:
    """
    生成约定式提交信息，包含详细信息。

    格式：
    <type>(<技能名>): <描述>

    - 详细变更说明1
    - 详细变更说明2

    Args:
        category: 变更类别 (deps, docs, feat 等，或 skill:<name>:<type>)
        files: 该类别中的变更文件列表

    Returns:
        格式化的提交信息（包含详细信息）
    """
    # Check if this is a skill category
    skill_name, skill_type = parse_skill_category(category)

    if skill_name:
        # Skill-based commit: 使用 analyze_changes 生成具体描述
        commit_type = skill_type
        description = analyze_changes(files, category)
    else:
        # Regular category
        commit_type = CATEGORY_TO_TYPE.get(category, 'chore')
        description = analyze_changes(files, category)

    # Detect skill name from files for automatic formatting
    detected_skill = detect_skill_name(files)

    # Generate detailed body based on files
    detail_lines = generate_detail_lines(files, category)

    # Format: type(skill-name): description (使用英文冒号以支持 GitHub 彩色标签)
    # 如果已有 skill_name 或从文件中检测到技能名，则使用括号格式
    if skill_name:
        message = f"{commit_type}({skill_name}): {description}"
    elif detected_skill:
        message = f"{commit_type}({detected_skill}): {description}"
    else:
        message = f"{commit_type}: {description}"

    # Add detail lines if available
    if detail_lines:
        message += "\n\n" + detail_lines

    return message


_diff_cache: dict = {}

def get_file_diff(filepath: str) -> str:
    """Get git diff for a specific file (cached)."""
    if filepath in _diff_cache:
        return _diff_cache[filepath]
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', filepath],
            capture_output=True,
            text=True,
        )
        _diff_cache[filepath] = result.stdout
        return result.stdout
    except Exception:
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
    # Check for new sections/headers - collect all headers for better context
    added_headers = [l.lstrip('#').strip() for l in added if l.startswith('#')]

    # SKILL.md is a skill core file, treat differently from regular docs
    if filename == 'SKILL.md' or 'SKILL.md' in filename:
        # Extract skill name from path if available
        skill_name = ""
        if 'skills/' in filename:
            parts = filename.split('skills/')
            if len(parts) > 1:
                skill_name = parts[1].split('/')[0]

        # If we found added headers, generate specific description
        if added_headers:
            # Get the most important header (first h1 or h2)
            header_text = added_headers[0]
            if skill_name:
                return f"{skill_name} 技能 - 添加 {header_text} 部分"
            return f"添加 {header_text} 部分"

        # Check for bullet points or list items (often contain具体的变更内容)
        added_items = [l.strip() for l in added if l.strip().startswith('- ') or l.strip().startswith('* ')]
        if added_items:
            # Use first meaningful item as description
            item_text = added_items[0][2:].strip()[:50]  # Limit length
            if skill_name:
                return f"{skill_name} 技能 - {item_text}"
            return f"更新 {filename} - {item_text}"

        if skill_name:
            return f"更新 {skill_name} 技能"
        return f"更新技能定义文件"

    # For regular markdown files with headers
    if added_headers:
        header_text = added_headers[0]
        return f"更新 {filename} - 添加 {header_text} 部分"

    # Check for doc updates
    if added:
        return f"更新 {filename} 文档内容"
    elif removed:
        return f"修改 {filename} 文档内容"

    return f"更新 {filename}"


def get_function_description(filename: str) -> str | None:
    """
    根据文件名获取功能描述。

    优先使用预定义的映射，如果没有匹配则返回 None。
    """
    for entry in FILE_TO_FUNCTION_MAP:
        if re.search(entry['pattern'], filename, re.IGNORECASE):
            return entry['description']
    return None


def extract_class_names(added: List[str]) -> List[str]:
    """提取新增的类名。"""
    class_names = []
    for line in added:
        # Python/JavaScript/TypeScript: class ClassName
        match = re.search(r'class\s+(\w+)', line)
        if match:
            class_names.append(match.group(1))
    return class_names


def extract_function_names(added: List[str]) -> List[str]:
    """提取新增的函数名。"""
    func_names = []
    for line in added:
        # Python: def function_name(
        match = re.search(r'def\s+(\w+)\s*\(', line)
        if match:
            func_names.append(match.group(1))
    return func_names


def infer_intent_from_function_name(func_name: str) -> str | None:
    """根据函数名前缀推断意图。

    示例:
    - detect_skill_name -> 检测技能名
    - infer_intent -> 推断意图
    - analyze_code_changes -> 分析代码变更
    - extract_function_names -> 提取函数名
    - detect_modified_functions -> 检测被修改的函数
    """
    for prefix, action in FUNCTION_PREFIX_ACTIONS.items():
        if func_name.startswith(prefix):
            # 提取函数名中剩余的部分
            rest = func_name[len(prefix):]

            # 如果剩余部分很短（如单个词），直接返回动作描述
            if len(rest) < 4:
                return action

            # 常见的"新功能"类词组，这些情况下直接返回简洁动作
            simple_suffixes = ('new', 'test', 'feature', 'item')
            if rest.lower().endswith(simple_suffixes) or rest.lower() in simple_suffixes:
                return action

            # 按下划线分割
            parts = rest.split('_')
            # 过滤掉常见词，保留核心名词
            filtered = [p for p in parts
                       if p.lower() not in ('name', 'file', 'path', 'content',
                                          'data', 'message', 'lines', 'from',
                                          'function', 'the', 'a', 'an', 'list',
                                          'new', 'test', 'feature', 'removed',
                                          'changes', 'added', 'modified', 'items')]

            # 如果过滤后只剩通用词（names, functions），使用函数名本身
            generic_terms = ('names', 'functions', 'data', 'items', 'values')
            if not filtered or all(f.lower() in generic_terms for f in filtered):
                # 返回函数名的后半部分（去掉前缀后的部分），用更友好的格式
                return rest.replace('_', ' ')

            readable = '_'.join(filtered)  # 保留完整的剩余部分
            return f"{action}({readable})"

    return None


def extract_removed_function_names(removed: List[str]) -> List[str]:
    """提取被删除的函数名。"""
    func_names = []
    for line in removed:
        match = re.search(r'def\s+(\w+)\s*\(', line)
        if match:
            func_names.append(match.group(1))
    return func_names


def detect_modified_functions(added_funcs: List[str], removed_funcs: List[str]) -> List[str]:
    """检测被修改的函数（既被删除又新增的同名函数）。"""
    modified = []
    for func in added_funcs:
        if func in removed_funcs:
            modified.append(func)
    return modified


def analyze_code_changes(added: List[str], removed: List[str], filename: str) -> str:
    """分析代码文件变更，生成有意义的描述。"""
    # 先尝试获取功能描述
    func_desc = get_function_description(filename)

    # 提取新增和删除的类名和函数名
    added_classes = extract_class_names(added)
    removed_classes = extract_class_names(removed)
    added_funcs = extract_function_names(added)
    removed_funcs = extract_removed_function_names(removed)
    added_imports = [l for l in added if 'import ' in l or 'from ' in l]

    # 判断是否为修改（既有删除又有新增）
    is_modification = len(removed) > 0 and len(added) > 0
    has_new_funcs = len(added_funcs) > 0
    has_new_classes = len(added_classes) > 0

    # 检测被修改的函数
    modified_funcs = detect_modified_functions(added_funcs, removed_funcs)

    # 构建描述
    # 优先处理修改场景（既有新增又有删除）
    if is_modification:
        if modified_funcs:
            # 有函数被修改
            intent = infer_intent_from_function_name(modified_funcs[0])
            if intent:
                return f"改进 {modified_funcs[0]}() - {intent}"
            return f"改进 {modified_funcs[0]}() 函数"

        if has_new_funcs:
            # 新增了函数
            intent = infer_intent_from_function_name(added_funcs[0])
            if intent:
                return f"改进 {filename} - 新增 {intent}"
            return f"改进 {filename} - 新增 {added_funcs[0]}() 函数"

        if func_desc:
            return f"改进 {func_desc}"

        return f"改进 {filename} 代码"

    # 新增函数场景
    if has_new_funcs:
        intent = infer_intent_from_function_name(added_funcs[0])
        if intent:
            if len(added_funcs) == 1:
                return f"新增 {intent}"
            else:
                return f"新增 {len(added_funcs)} 个函数 - {intent}"
        return f"新增 {added_funcs[0]}() 函数"

    if has_new_classes:
        if func_desc:
            return f"新增 {added_classes[0]} 类到 {func_desc}"
        return f"新增 {added_classes[0]} 类"

    # 检查关键词 - 生成更具体的描述
    fix_keywords = ['fix', 'bug', '修复', '错误', '问题']
    if any(any(kw in l.lower() for kw in fix_keywords) for l in added + removed):
        if func_desc:
            return f"修复 {func_desc} 中的问题"
        return "修复代码问题"

    refactor_keywords = ['refactor', '重构', '优化', 'improve', 'optimize']
    if any(any(kw in l.lower() for kw in refactor_keywords) for l in added + removed):
        if func_desc:
            return f"重构 {func_desc}"
        return "重构代码"

    update_keywords = ['update', '改进', 'enhance', 'modify']
    if any(any(kw in l.lower() for kw in update_keywords) for l in added + removed):
        if func_desc:
            return f"改进 {func_desc}"
        return f"改进 {filename}"

    if added_imports and func_desc:
        return f"改进 {func_desc} - 新增导入"

    if func_desc:
        return f"改进 {func_desc}"

    return f"改进 {filename} 代码"


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
    """分析配置文件变更，生成具体的描述。"""
    if not added:
        if removed:
            removed_keys = [l.split(':')[0].strip() for l in removed if ':' in l]
            if removed_keys:
                return f"更新 {filename} - 移除 {', '.join(removed_keys[:2])} 配置"
        return f"更新 {filename} 配置"

    # 分析添加的配置项
    added_keys = []
    semantic_descriptions = []

    for line in added:
        if ':' in line:
            key = line.split(':')[0].strip()
            added_keys.append(key)

            # 查找语义描述
            key_lower = key.lower()
            for config_key, meaning in CONFIG_KEY_MEANINGS.items():
                if config_key in key_lower:
                    if meaning not in semantic_descriptions:
                        semantic_descriptions.append(meaning)
                    break

    # 分析上下文：查找配置所属的分组（如 level3, level4）
    context_info = []
    for line in added:
        line_stripped = line.strip()
        # 检测 YAML 层级标识（如 "level3:", "level4:"）
        if line_stripped and not line_stripped.startswith('#'):
            # 检测缩进级别，判断是否是子配置
            indent = len(line) - len(line.lstrip())
            if indent == 0 and line_stripped.endswith(':'):
                # 顶级配置项
                section_name = line_stripped[:-1]
                context_info.append(section_name)

    # 构建描述
    if semantic_descriptions:
        # 有语义描述
        desc = '、'.join(semantic_descriptions[:3])

        # 如果有上下文信息，添加到描述中
        if context_info:
            context = context_info[0]
            # 将 level3 转换为更友好的描述
            context_map = {
                'level1': '一级标题',
                'level2': '二级标题',
                'level3': '三级标题',
                'level4': '四级标题',
                'level5': '五级标题',
                'level6': '六级标题',
            }
            context_desc = context_map.get(context, context)
            return f"更新 {filename} - 为 {context_desc} 添加 {desc} 配置"

        return f"更新 {filename} - 添加 {desc} 配置"

    if added_keys:
        # 没有语义匹配，使用原始 key
        return f"更新 {filename} - 添加 {', '.join(added_keys[:3])} 配置"

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
