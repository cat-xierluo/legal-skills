#!/usr/bin/env python3
"""
Interactive batch commit tool for Git.

Groups changes by type and helps create multiple focused commits
instead of one large mixed commit.
"""

import subprocess
import sys
import json
from pathlib import Path
from typing import Dict, List

# Import sibling scripts
sys.path.insert(0, str(Path(__file__).parent))
from categorize_changes import get_staged_files, group_changes
from generate_commit_message import generate_commit_messages


def stage_files(files: List[str]) -> bool:
    """Stage files for commit."""
    if not files:
        return True
    try:
        subprocess.run(
            ['git', 'add'] + files,
            capture_output=True,
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"暂存文件时出错: {e}", file=sys.stderr)
        return False


def unstage_files(files: List[str]) -> bool:
    """Unstage files to reorganize commits."""
    if not files:
        return True
    try:
        subprocess.run(
            ['git', 'reset', 'HEAD'] + files,
            capture_output=True,
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"取消暂存文件时出错: {e}", file=sys.stderr)
        return False


def create_commit(message: str) -> bool:
    """Create a git commit with the given message."""
    try:
        subprocess.run(
            ['git', 'commit', '-m', message],
            capture_output=True,
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"创建提交时出错: {e}", file=sys.stderr)
        print(f"stderr: {e.stderr.decode()}", file=sys.stderr)
        return False


def display_groups(groups: Dict[str, List[str]], messages: Dict[str, str]):
    """Display grouped changes with proposed commit messages."""
    print("\n" + "=" * 60)
    print("提议的提交分组")
    print("=" * 60)

    for i, (category, files) in enumerate(sorted(groups.items()), 1):
        msg = messages.get(category, f"{category.title()}: 更新文件")
        print(f"\n[分组 {i}] {msg}")
        print(f"类别: {category}")
        print(f"文件 ({len(files)} 个):")
        for f in sorted(files):
            print(f"  - {f}")

    print("\n" + "=" * 60)


def is_interactive() -> bool:
    """Check if running in an interactive terminal."""
    return sys.stdin.isatty()


def confirm_groups(skip_confirm: bool = False) -> bool:
    """Ask user to confirm the proposed grouping.

    Args:
        skip_confirm: If True, skip confirmation and proceed automatically
    """
    if skip_confirm:
        return True

    print("\n选项:")
    print("  y - 是，创建这些提交")
    print("  n - 否，取消")
    print("  e - 编辑分组（手动模式）")

    while True:
        try:
            response = input("\n是否继续创建这些提交？ [y/n/e]: ").strip().lower()
        except (EOFError, OSError):
            print("\n检测到非交互式环境，已取消操作。")
            print("提示：使用 --yes 参数跳过确认，或使用 --dry-run 仅查看分组")
            return False

        if response in ['y', 'yes', '是']:
            return True
        elif response in ['n', 'no', '否']:
            return False
        elif response in ['e', 'edit', '编辑']:
            print("\n编辑模式尚未实现。请重新运行。")
            return False
        else:
            print("请输入 'y'、'n' 或 'e'。")


def batch_commit(skip_confirm: bool = False):
    """Main function to perform batch commit.

    Args:
        skip_confirm: If True, skip confirmation and proceed automatically
    """
    print("Git 批量提交工具")
    print("=" * 60)

    # Get currently staged files
    staged = get_staged_files()

    if not staged:
        print("未发现已暂存的变更。")
        print("请先使用 git add <files> 暂存一些变更")
        return 1

    print(f"发现 {len(staged)} 个已暂存文件")

    # Unstage everything first to regroup
    if not unstage_files(staged):
        print("错误：无法取消暂存文件。")
        return 1

    # Group changes by category
    groups = group_changes(staged, staged=True)

    # Generate commit messages for each group
    messages = generate_commit_messages(groups)

    # Display proposed groups
    display_groups(groups, messages)

    # Confirm with user
    if not confirm_groups(skip_confirm=skip_confirm):
        print("\n已取消。正在重新暂存原始文件...")
        stage_files(staged)
        return 0

    # Create commits for each group
    print("\n正在创建提交...")
    success_count = 0
    total_count = len(groups)

    for category, files in sorted(groups.items()):
        msg = messages.get(category, f"{category.title()}: 更新文件")

        # Stage files for this commit
        print(f"\n  → {msg}")
        if not stage_files(files):
            print(f"    无法为 {category} 暂存文件")
            continue

        # Create commit
        if create_commit(msg):
            print(f"    ✓ 已提交 {len(files)} 个文件")
            success_count += 1
        else:
            print(f"    ✗ 提交失败")

    # Summary
    print("\n" + "=" * 60)
    print(f"批量提交完成：{success_count}/{total_count} 个提交已创建")
    print("=" * 60)

    return 0 if success_count == total_count else 1


def main():
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Interactive batch commit tool for Git',
        epilog='示例: %(prog)s --yes    # 自动确认并创建提交'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='显示将要提交的内容而不实际提交'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='跳过交互式确认，自动创建提交（适用于 CI/CD 或非交互式环境）'
    )

    args = parser.parse_args()

    if args.dry_run:
        # Just show grouping without committing
        staged = get_staged_files()
        if not staged:
            print("未发现已暂存的变更。")
            return 0

        groups = group_changes(staged, staged=True)
        messages = generate_commit_messages(groups)
        display_groups(groups, messages)
        return 0
    else:
        return batch_commit(skip_confirm=args.yes)


if __name__ == '__main__':
    sys.exit(main())
