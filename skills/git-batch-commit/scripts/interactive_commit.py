#!/usr/bin/env python3
"""
Interactive batch commit tool for Git.

Groups changes by type and helps create multiple focused commits
instead of one large mixed commit.
"""

import subprocess
import sys
import os
import tempfile
from pathlib import Path
from typing import Dict, List

# Import sibling scripts
sys.path.insert(0, str(Path(__file__).parent))
from categorize_changes import group_changes
from generate_commit_message import add_issue_reference, generate_commit_messages

# One shared implementation; an incomplete standalone installation fails closed.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'git-workflow' / 'scripts'))
    from privacy_check import Checker, PrivacyError
except ImportError:
    print('PRIVACY_CHECKER_MISSING: 请同时安装同级 git-workflow 技能', file=sys.stderr)
    raise SystemExit(1)


def current_head(checker):
    refs = checker.git('rev-parse', '--verify', 'HEAD^{commit}').decode('ascii').strip()
    return refs


def create_commit(checker, snapshot, files, message, expected_head):
    """Commit only snapshot bytes through a temporary index, never git-add worktree."""
    if current_head(checker) != expected_head or checker.git('write-tree').decode().strip() != snapshot:
        raise PrivacyError('PRIVACY_SNAPSHOT_CHANGED: HEAD 或暂存区变化，请重新预检')
    with tempfile.TemporaryDirectory(prefix='batch-commit-') as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / 'index'), GIT_LITERAL_PATHSPECS='1')
        checker.git('read-tree', expected_head, env=env)
        checker.git('restore', '--staged', '--source=' + snapshot,
                    '--pathspec-from-file=-', '--pathspec-file-nul',
                    input=b''.join(os.fsencode(path) + b'\0' for path in files), env=env)
        expected_tree = checker.git('write-tree', env=env).decode().strip()
        # --cleanup=verbatim and stdin bind the checked full message to the command.
        checker.git('commit', '--cleanup=verbatim', '-F', '-', input=message.encode('utf-8'), env=env)
        new_head = current_head(checker)
        if checker.git('show', '-s', '--format=%T', new_head).decode().strip() != expected_tree:
            raise PrivacyError('PRIVACY_COMMIT_CHANGED: hook 改变提交树，已停止；不得发布')
        actual = checker.git('show', '-s', '--format=%B', new_head).decode('utf-8')
        if actual.rstrip('\n') != message.rstrip('\n'):
            raise PrivacyError('PRIVACY_COMMIT_CHANGED: hook 改变提交说明，已停止；不得发布')
        return new_head


def prepare(issue=None, local_ref=None):
    checker = Checker()
    # Require an existing base so ambiguous unborn history cannot partially commit.
    head = current_head(checker)
    snapshot = checker.scan_staged()
    staged = [os.fsdecode(path) for path in checker.git(
        'diff', '--cached', '--no-renames', '--name-only', '-z').split(b'\0') if path]
    if not staged:
        return checker, head, snapshot, {}, {}
    groups = group_changes(staged, staged=True)
    if sorted(path for files in groups.values() for path in files) != sorted(staged):
        raise PrivacyError('PRIVACY_GROUP_MISMATCH: 分组未精确覆盖暂存文件')
    messages = decorate_messages(groups, generate_commit_messages(groups), issue, local_ref)
    for index, category in enumerate(sorted(groups), 1):
        if category not in messages:
            raise PrivacyError('PRIVACY_MESSAGE_MISSING: 缺少最终完整提交说明')
        checker.scan_text(messages[category], f'commit-message:{index}')
    # ALL groups and references pass before any preview, index edits or commits.
    checker.finish()
    if current_head(checker) != head or checker.git('write-tree').decode().strip() != snapshot:
        raise PrivacyError('PRIVACY_SNAPSHOT_CHANGED: 预检期间 HEAD 或暂存区变化')
    return checker, head, snapshot, groups, messages


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

    while True:
        try:
            response = input("\n是否继续创建这些提交？ [y/n]: ").strip().lower()
        except (EOFError, OSError):
            print("\n检测到非交互式环境，已取消操作。")
            print("提示：使用 --yes 参数跳过确认，或使用 --dry-run 仅查看分组")
            return False

        if response in ['y', 'yes', '是']:
            return True
        elif response in ['n', 'no', '否']:
            return False
        else:
            print("请输入 'y' 或 'n'。")


def decorate_messages(
    groups: Dict[str, List[str]],
    messages: Dict[str, str],
    issue: str | None = None,
    local_ref: str | None = None,
) -> Dict[str, str]:
    """Add issue/task references to generated commit messages."""
    if not issue and not local_ref:
        return messages

    decorated = {}
    for category, message in messages.items():
        decorated[category] = add_issue_reference(
            message,
            github_issue=issue,
            local_ref=local_ref,
        )
    return decorated


def batch_commit(
    skip_confirm: bool = False,
    issue: str | None = None,
    local_ref: str | None = None,
):
    """Main function to perform batch commit.

    Args:
        skip_confirm: If True, skip confirmation and proceed automatically
    """
    print("Git 批量提交工具")
    print("=" * 60)

    try:
        checker, head, snapshot, groups, messages = prepare(issue, local_ref)
        if not groups:
            print('未发现已暂存的变更。')
            return 1
        display_groups(groups, messages)
        if not confirm_groups(skip_confirm=skip_confirm):
            print('已取消。')
            return 0
        for category, files in sorted(groups.items()):
            head = create_commit(checker, snapshot, files, messages[category], head)
        print(f'批量提交完成：{len(groups)} 个提交已创建，原暂存快照与工作区内容保留')
        return 0
    except (PrivacyError, UnicodeError, subprocess.CalledProcessError, OSError):
        # Do not print command arguments, stderr, filenames, or generated messages.
        error = sys.exc_info()[1]
        print(str(error) if isinstance(error, PrivacyError) else
              'PRIVACY_PREFLIGHT_FAILED: 未完整读取提交输入，已停止', file=sys.stderr)
        return 1


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
    parser.add_argument(
        '--issue',
        type=str,
        help='关联的 GitHub Issue 编号，例如 13 或 #13；每个提交标题会追加 (#13)'
    )
    parser.add_argument(
        '--local-ref',
        type=str,
        help='关联的本地任务引用，例如 "project-task Issue #13"，不会关闭 GitHub Issue'
    )

    args = parser.parse_args()

    if args.dry_run:
        try:
            _, _, _, groups, messages = prepare(args.issue, args.local_ref)
            display_groups(groups, messages)
            return 0
        except (PrivacyError, UnicodeError, subprocess.CalledProcessError, OSError) as error:
            print(str(error) if isinstance(error, PrivacyError) else
                  'PRIVACY_PREFLIGHT_FAILED: 未完整读取提交输入，已停止', file=sys.stderr)
            return 1
    else:
        return batch_commit(
            skip_confirm=args.yes,
            issue=args.issue,
            local_ref=args.local_ref,
        )


if __name__ == '__main__':
    sys.exit(main())
