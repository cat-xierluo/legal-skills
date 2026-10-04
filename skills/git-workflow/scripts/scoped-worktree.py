#!/usr/bin/env python3
"""创建仅检出指定目录的 Git worktree；不启动 Agent，不复制 ignored 文件。"""
import argparse
import json
import os
import pathlib
import subprocess
import sys


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--base", required=True, help="明确指定基准，例如 origin/main 或集成分支")
    parser.add_argument("--branch", required=True, help="新分支名称；已有分支会拒绝")
    parser.add_argument("--scope", action="append", required=True, help="仓库相对目录；可重复")
    parser.add_argument("--existing-branch", action="store_true", help="显式检出未占用的已有分支；要求其 tip 与冻结 base 一致")
    args = parser.parse_args()
    if any(os.environ.get(key) for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_NAMESPACE")):
        parser.error("检测到 Git 仓库/索引环境覆盖，拒绝操作；请在普通任务环境重试")
    repo = pathlib.Path(args.repo).resolve(strict=True)
    requested = pathlib.Path(args.path).expanduser()
    if requested.exists() or requested.is_symlink():
        parser.error("目标路径已存在，拒绝覆盖")
    target = requested.resolve()
    git(repo, "check-ref-format", "--branch", args.branch)
    oid = git(repo, "rev-parse", "--verify", args.base + "^{commit}")
    scopes = []
    for scope in args.scope:
        scope = scope.rstrip("/")
        p = pathlib.PurePosixPath(scope)
        if not scope or p.is_absolute() or any(x in scope.split("/") for x in ("", ".", "..")) or any(c in scope for c in "\r\n\\"):
            parser.error("scope 必须是仓库相对目录，不能包含 ..、反斜杠或换行")
        if git(repo, "cat-file", "-t", oid + ":" + scope) != "tree":
            parser.error("基准中不存在指定目录：" + scope)
        if scope not in scopes:
            scopes.append(scope)
    # 不先检出全仓；Git 对象库继续由各工作树共享。
    if args.existing_branch:
        if git(repo, "rev-parse", "refs/heads/" + args.branch) != oid:
            parser.error("已有分支 tip 与冻结 base 不一致，拒绝创建")
        git(repo, "worktree", "add", "--no-checkout", str(target), args.branch)
    else:
        git(repo, "worktree", "add", "--no-checkout", "--no-track", "-b", args.branch, str(target), oid)
    try:
        # 保留完整 index，以兼容尚不支持 sparse index 的外部工具。
        git(target, "sparse-checkout", "set", "--cone", "--no-sparse-index", "--", *scopes)
        # --no-checkout 的新树尚无 index；按稀疏规则首次填充，避免所有文件显示删除。
        git(target, "read-tree", "-mu", oid)
        if git(target, "rev-parse", "HEAD") != oid:
            raise RuntimeError("新工作树 HEAD 已漂移，已保留供排查")
        if git(target, "status", "--porcelain"):
            raise RuntimeError("新工作树不干净，请检查目标路径；已保留供排查")
    except Exception:
        print("配置失败，已保留工作树与分支：" + str(target), file=sys.stderr)
        raise
    print(json.dumps({"path": str(target), "branch": args.branch, "base_oid": oid,
                      "scopes": scopes, "root_AGENTS_present": (target / "AGENTS.md").exists(),
                      "root_CLAUDE_present": (target / "CLAUDE.md").exists()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
