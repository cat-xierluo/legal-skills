#!/usr/bin/env python3
"""Command-entry guard: default main to read-only; named integration may add/commit.

Only commands routed through this entry are guarded. Not a security boundary,
Git hook, global executable replacement, or protection for native GUI clients.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

READ = {"status", "diff", "log", "show", "rev-parse", "ls-files", "ls-tree",
        "cat-file", "check-ignore", "describe", "merge-base", "for-each-ref",
        "show-ref", "rev-list", "version", "help"}
ROUTING_ENV = {"GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
               "GIT_NAMESPACE", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"}
SAFE_CONFIG = {"user.name", "user.email", "commit.gpgsign"}


def refuse(reason):
    raise ValueError("main-git-gate 拒绝：" + reason)


def parse_git(argv):
    """Resolve repeated -C; reject routing/config overrides before execution."""
    cwd = Path.cwd()
    i = 0
    while i < len(argv) and argv[i].startswith("-"):
        a = argv[i]
        if a == "-C":
            if i + 1 >= len(argv):
                refuse("-C 缺少路径")
            cwd = (cwd / argv[i + 1]).resolve()
            i += 2
        elif a == "-c":
            if i + 1 >= len(argv):
                refuse("-c 缺少配置")
            if argv[i + 1].split("=", 1)[0].lower() not in SAFE_CONFIG:
                refuse("配置覆写不在普通身份/签名范围")
            i += 2
        elif a in {"--no-pager", "--paginate", "--no-optional-locks"}:
            i += 1
        elif a == "--version" and i + 1 == len(argv):
            return cwd, "version", []
        else:
            refuse("不接受仓库路由、执行入口或未知全局选项：" + a)
    if i == len(argv):
        refuse("缺少 Git 命令")
    return cwd, argv[i], argv[i + 1:]


def query(git, cwd, *args):
    r = subprocess.run([git, "-C", str(cwd), *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def check_commit_options(args):
    """Accept explicit ordinary commit options; never Git's abbreviations."""
    flags = {"--all", "--quiet", "--verbose", "--no-edit", "--allow-empty",
             "--allow-empty-message", "--dry-run", "--signoff"}
    values = {"--message", "--file"}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            return  # Remaining tokens are pathspecs, not options.
        if arg in flags or not arg.startswith("-"):
            i += 1
            continue
        if arg.startswith("--"):
            key, sep, _ = arg.partition("=")
            if key not in values:
                refuse("commit 仅接受明确的普通提交选项：" + key)
            if not sep:
                i += 1
                if i == len(args):
                    refuse("commit 选项缺少值：" + key)
        elif arg.startswith("-") and arg != "-":
            # Git accepts -amVALUE / -qm VALUE. Value suffixes are opaque.
            for offset, char in enumerate(arg[1:], 1):
                if char in "aqvs":
                    continue
                if char in "mF":
                    if offset == len(arg) - 1:
                        i += 1
                        if i == len(args):
                            refuse("commit 选项缺少值：-" + char)
                    break
                refuse("commit 短选项不在普通提交范围：-" + char)
        else:
            refuse("commit 未知选项")
        i += 1


def check_unstage_options(args):
    """Only unstage from HEAD; reject abbreviations, sources and worktree flags."""
    options = args[:args.index("--")] if "--" in args else args
    if not any(arg in {"--staged", "-S"} for arg in options):
        refuse("restore 仅支持明确的 --staged 或 -S 取消暂存")
    for arg in options:
        if arg.startswith("-") and arg not in {"--staged", "-S", "--quiet", "-q"}:
            refuse("restore 未知或可能覆盖文件/来源的选项：" + arg)


def check(git, protected, argv, integration_owner=None, expected_head=None):
    for key in ROUTING_ENV:
        if os.environ.get(key):
            refuse("存在环境路由覆写 " + key)
    cwd, command, args = parse_git(argv)
    code, top = query(git, cwd, "rev-parse", "--show-toplevel")
    if code:
        return  # Outside a repository: real Git supplies its usual diagnostics.
    if Path(top).resolve() != protected:
        return  # Linked worktrees and unrelated repositories use their own policy.
    code, branch = query(git, cwd, "symbolic-ref", "-q", "HEAD")
    if code or branch != "refs/heads/main":
        refuse("受管主目录身份不是 main；保留现场，由具名 owner 处理")
    if command in READ or command == "reflog":
        if any(a == "--output" or a.startswith("--output=") for a in args):
            refuse("读取命令的文件输出覆写需单独维护")
    if command in READ:
        return
    if command in {"add", "commit", "restore"}:
        if not integration_owner or not integration_owner.strip() or not expected_head:
            refuse("主目录仅加载和集成；开发请使用独立 worktree，采用须具名 owner 与完整 expected HEAD")
        code, actual = query(git, cwd, "rev-parse", "HEAD")
        if code or len(expected_head) != 40 or actual != expected_head:
            refuse("集成基准已漂移；重新核验 owner、HEAD、索引及逐文件清单")
    if command == "add":
        return
    if command == "commit":
        check_commit_options(args)
        return
    if command == "restore":
        check_unstage_options(args)
        return
    if command == "config":
        if args and args[0] in {"--get", "--get-all", "--get-regexp", "--list", "-l"}:
            return
    if command == "branch":
        if not args or all(a in {"--list", "-l", "-a", "--all", "-r", "--remotes",
                                  "-v", "-vv", "--show-current"} for a in args):
            return
    if command == "reflog" and (not args or args[0] == "show"):
        return
    if command == "remote" and (not args or args[0] in {"-v", "--verbose", "get-url"}):
        return
    refuse("主目录不执行 " + command + "；切换/覆盖/历史维护请在独立树或具名窗口进行")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", required=True, help="受管主目录的真实绝对路径")
    p.add_argument("--git", required=True, help="已核真实 Git 二进制绝对路径，不能指回本门禁")
    p.add_argument("--integration-owner", help="已获授权的具名集成者；不是普通开发开关")
    p.add_argument("--expected-head", help="该次集成核验的完整主目录 HEAD；每次提交后重新核验")
    p.add_argument("--check-only", action="store_true", help="只核准命令，不执行 Git")
    p.add_argument("args", nargs=argparse.REMAINDER)
    ns = p.parse_args()
    protected = Path(ns.repo).resolve()
    git = Path(ns.git)
    if not git.is_absolute() or not git.is_file() or not os.access(git, os.X_OK):
        refuse("真实 Git 路径不可执行")
    if git.resolve() == Path(__file__).resolve():
        refuse("Git 二进制指回门禁，拒绝递归")
    if not (protected / ".git").is_dir():
        refuse("受管路径不是具名主检出")
    argv = ns.args[1:] if ns.args[:1] == ["--"] else ns.args
    if bool(ns.integration_owner) != bool(ns.expected_head):
        refuse("integration-owner 与 expected-head 必须同时提供")
    check(str(git), protected, argv, ns.integration_owner, ns.expected_head)
    if ns.check_only:
        return
    os.execv(str(git), [str(git), *argv])


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(73)
