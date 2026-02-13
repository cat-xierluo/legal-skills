#!/usr/bin/env python3
"""
Categorize Git changes by type for batch committing.

Analyzes git diff to group modifications by logical categories:
- deps: Dependency management (package.json, requirements.txt, go.mod, etc.)
- docs: Documentation changes
- license: LICENSE file updates
- config: Configuration files
- test: Test files
- chore: Build scripts, tooling
- feat: New features in source code
- fix: Bug fixes in source code
- refactor: Code refactoring
- style: Code style changes
"""

import subprocess
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple


# File pattern to category mapping
FILE_PATTERNS = {
    'deps': [
        r'package\.json',
        r'package-lock\.json',
        r'yarn\.lock',
        r'pnpm-lock\.yaml',
        r'requirements\.txt',
        r'poetry\.lock',
        r'Pipfile',
        r'pyproject\.toml',
        r'go\.mod',
        r'go\.sum',
        r'Gemfile',
        r'Gemfile\.lock',
        r'Cargo\.toml',
        r'Cargo\.lock',
        r'composer\.json',
        r'composer\.lock',
        r'\.gradle',
    ],
    'license': [
        r'LICENSE',
        r'LICENSE\.txt',
        r'LICENSE\.md',
        r'COPYING',
    ],
    'docs': [
        r'\.md$',
        r'\.rst$',
        r'\.txt$',
        r'docs/.*',
        r'DOC.*',
        r'README.*',
        r'CHANGELOG.*',
        r'CONTRIBUTING.*',
    ],
    'config': [
        r'\.env\.',
        r'\.conf',
        r'\.config',
        r'\.yaml$',
        r'\.yml$',
        r'\.toml$',
        r'\.json$',
        r'\.xml$',
        r'\.ini$',
        r'config/.*',
    ],
    'test': [
        r'test_.*\.py$',
        r'.*_test\.go$',
        r'.*\.test\.ts$',
        r'.*\.test\.js$',
        r'.*\.spec\.ts$',
        r'.*\.spec\.js$',
        r'tests?/.*',
        r'__tests?__/.*',
        r'test/.*',
    ],
    'chore': [
        r'Makefile',
        r'Dockerfile',
        r'\.dockerignore',
        r'\.gitignore',
        r'\.gitattributes',
        r'\.github/.*',
        r'\.gitlab-ci\.yml',
        r'\travis\.yml',
        r'jenkinsfile',
        r'\.editorconfig',
    ],
}

# Skill core files that should be treated as code, not docs
# These define behavior/functionality, not just documentation
SKILL_CORE_FILES = [
    r'SKILL\.md$',           # Skill definition file (defines behavior)
    r'skills/.*/SKILL\.md$', # Skill files in skills directory
]

# Source code extensions
SOURCE_EXTENSIONS = [
    r'\.py$', r'\.js$', r'\.ts$', r'\.tsx$', r'\.jsx$',
    r'\.go$', r'\.rs$', r'\.java$', r'\.kt$', r'\.swift$',
    r'\.c$', r'\.cpp$', r'\.h$', r'\.hpp$',
    r'\.cs$', r'\.php$', r'\.rb$', r'\.scala$',
]


def get_staged_files() -> List[str]:
    """Get list of staged files using git diff --cached --name-only."""
    result = subprocess.run(
        ['git', 'diff', '--cached', '--name-only'],
        capture_output=True,
        text=True,
        check=True
    )
    files = result.stdout.strip().split('\n')
    return [f for f in files if f]


def get_unstaged_files() -> List[str]:
    """Get list of unstaged modified files using git diff --name-only."""
    result = subprocess.run(
        ['git', 'diff', '--name-only'],
        capture_output=True,
        text=True,
        check=True
    )
    files = result.stdout.strip().split('\n')
    return [f for f in files if f]


def categorize_file(filepath: str) -> str:
    """Categorize a file based on its path and patterns."""
    # Special handling for skill core files
    # SKILL.md defines behavior/functionality, should be treated as code, not docs
    for pattern in SKILL_CORE_FILES:
        if re.search(pattern, filepath):
            return 'code'

    # Check each category's patterns
    for category, patterns in FILE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, filepath):
                return category

    # Check if it's a source file
    for ext_pattern in SOURCE_EXTENSIONS:
        if re.search(ext_pattern, filepath):
            return 'code'

    # Default to 'other'
    return 'other'


def detect_code_change_type(filepath: str) -> str:
    """
    Detect if a source code change is feat, fix, refactor, or style.
    This analyzes the git diff content.
    """
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', filepath],
            capture_output=True,
            text=True,
            check=True
        )
        diff_content = result.stdout

        # Simple heuristic based on diff patterns
        # Additions dominate -> likely a feature
        # Deletions dominate -> likely a cleanup/refactor
        # 'fix' or 'bug' in added lines -> likely a fix
        added_lines = len([l for l in diff_content.split('\n') if l.startswith('+')])
        removed_lines = len([l for l in diff_content.split('\n') if l.startswith('-')])

        # Check for fix-related keywords (English + Chinese)
        fix_keywords = ['fix', 'bug', 'issue', 'error', 'patch', 'hotfix',
                        '修复', '错误', '问题', '补丁']
        if any(keyword in diff_content.lower() for keyword in fix_keywords):
            return 'fix'

        # Check for feature-related keywords (English + Chinese)
        feat_keywords = ['add', 'new', 'implement', 'feature', 'support',
                         '添加', '新增', '实现', '功能', '支持', '增加']
        if any(keyword in diff_content.lower() for keyword in feat_keywords):
            return 'feat'

        # Based on line changes
        if added_lines > removed_lines * 1.5:
            return 'feat'
        elif removed_lines > added_lines * 1.5:
            return 'refactor'
        else:
            return 'style'

    except Exception:
        return 'style'


def extract_skill_name(filepath: str) -> str:
    """
    Extract skill name from a file path if it's under skills/ directory.

    Returns skill name if found, None otherwise.
    """
    match = re.match(r'skills/([^/]+)/', filepath)
    if match:
        return match.group(1)
    return None


def group_changes(files: List[str], staged: bool = True) -> Dict[str, List[str]]:
    """
    Group files by category.

    Special handling for skill directories: all files under the same skill
    directory are grouped together as they represent a single logical change.

    Args:
        files: List of file paths
        staged: Whether files are staged (True) or unstaged (False)

    Returns:
        Dictionary mapping category to list of files
    """
    groups = {}
    skill_groups = {}  # Temporary storage for skill-based grouping

    # First pass: separate skill files from others
    for filepath in files:
        skill_name = extract_skill_name(filepath)
        if skill_name:
            if skill_name not in skill_groups:
                skill_groups[skill_name] = []
            skill_groups[skill_name].append(filepath)
        else:
            # Non-skill files: categorize normally
            category = categorize_file(filepath)

            # For source code, further categorize
            if category == 'code' and staged:
                subcategory = detect_code_change_type(filepath)
                category = subcategory

            if category not in groups:
                groups[category] = []
            groups[category].append(filepath)

    # Second pass: process skill groups
    for skill_name, skill_files in skill_groups.items():
        # Determine the change type based on the most significant change
        # If any file has 'feat' keywords, use 'feat'
        # Else if any file has 'fix' keywords, use 'fix'
        # Else use 'style'
        change_type = 'style'

        for filepath in skill_files:
            if staged:
                file_type = detect_code_change_type(filepath)
                if file_type == 'feat':
                    change_type = 'feat'
                    break
                elif file_type == 'fix' and change_type != 'feat':
                    change_type = 'fix'

        # Use skill:<name> as the category key
        category_key = f'skill:{skill_name}:{change_type}'
        groups[category_key] = skill_files

    return groups


def main():
    """Main entry point for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Categorize Git changes for batch committing'
    )
    parser.add_argument(
        '--unstaged',
        action='store_true',
        help='Analyze unstaged changes instead of staged'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON'
    )

    args = parser.parse_args()

    # Get files
    if args.unstaged:
        files = get_unstaged_files()
    else:
        files = get_staged_files()

    if not files:
        print("No changes found.")
        return

    # Group files
    groups = group_changes(files, staged=not args.unstaged)

    if args.json:
        print(json.dumps(groups, indent=2))
    else:
        print("Categorized changes:")
        print("-" * 40)
        for category, file_list in sorted(groups.items()):
            print(f"\n{category.upper()}:")
            for f in file_list:
                print(f"  - {f}")


if __name__ == '__main__':
    main()
