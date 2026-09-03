#!/usr/bin/env python3
"""scope-guard.py — PreToolUse hook: deny out-of-scope file writes.

Reads stdin JSON (tool_name + tool_input), checks tool_input.file_path
against SCOPE_GUARD_ALLOW glob patterns (colon-separated).
覆盖写工具 Edit/Write/NotebookEdit 与 Claude Code 的 Update（Task-114）。

Designed for both codebuddy and qoder (stdin/stdout JSON format identical).
Based on ref 07 §9.3 (qoder PreToolUse hook, unbypassable even in bypass_permissions)
and ref 08 §12.3 (codebuddy PreToolUse hook, semantic parity expected).

Exit 0 + no output = allow (passes through to next hook / permission pipeline).
Exit 0 + deny JSON on stdout = hard block (permissionDecision: deny, short-circuits).
Exit non-zero = hook error (treated as allow by most CLI implementations for safety).

No SCOPE_GUARD_ALLOW → no-op (backward compatible, scope-guard not active).

Reviewer role (v2.14.0, role-separated acceptance waves):
SCOPE_GUARD_ROLE=reviewer 激活 reviewer 写范围纪律——

- 默认可写范围只有 reviewer 自己的 Session Context
  （SCOPE_GUARD_SESSION_ROOT 指向的前缀），任务合同未显式授予被审分支
  修复权（SCOPE_GUARD_REVIEW_REPAIR_GRANT=1）时，Session Context 之外的
  一律拒绝；
- 即便授予了修复权，任何 `*/config/*.local.yaml`（安装 Skill 的本地运行
  配置，如 orchestration-personal.local.yaml）永远拒绝——修复权不覆盖
  本机配置写入；
- 非 reviewer 角色完全走既有 allowlist 行为（向后兼容）。

Task-114-R2B（独立 reviewer 在真实 Claude Code 2.1.237 负探针中的回归）：

- deny() 按 WORKER_GUARD_BACKEND 区分协议：backend 为 claude-code/
  claude_code/claude 时，deny JSON 的 hookSpecificOutput 必须带精确
  hookEventName="PreToolUse"，否则 Claude Code 不承认这是权限决策——
  报 `PreToolUse:Edit hook error` 后照常执行写入（负探针实证：reviewer
  对根 README.md 的 Update 落盘）；其他 backend 保持现有协议不变；
- deny 真正生效后，非 reviewer 角色在 SCOPE_GUARD_SESSION_ROOT 自身
  目录内的控制面写入（STATUS/RESULT 等）保持可达——严格前缀，不含
  父目录、兄弟 session、仓库代码，config/*.local.yaml 明确排除。
"""

import fnmatch
import json
import os
import sys


REVIEWER_ROLE = "reviewer"


def is_config_local_yaml(path: str) -> bool:
    """True when the path writes a *.local.yaml inside any config/ directory."""
    normalized = path.replace("\\", "/")
    parts = [segment for segment in normalized.split("/") if segment not in ("", ".")]
    if len(parts) < 2:
        return False
    filename = parts[-1]
    parent_segments = parts[:-1]
    return filename.endswith(".local.yaml") and "config" in parent_segments


def get_worktree_root():
    """Get the git worktree root for path normalization."""
    cwd = os.environ.get("PWD", os.getcwd())
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return cwd


def match_any_pattern(file_path, patterns, worktree_root):
    """Check if file_path matches any glob pattern.
    
    Tries multiple forms of the path:
    1. As-is (relative or absolute)
    2. Relative to worktree root (strip worktree prefix from absolute paths)
    3. Without leading ./ if present
    """
    # Try exact match first
    for pattern in patterns:
        if fnmatch.fnmatch(file_path, pattern):
            return True

    # Strip worktree root prefix from absolute paths
    if file_path.startswith(worktree_root + "/"):
        rel_path = file_path[len(worktree_root) + 1:]
        for pattern in patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True

    # Strip leading ./
    if file_path.startswith("./"):
        clean = file_path[2:]
        for pattern in patterns:
            if fnmatch.fnmatch(clean, pattern):
                return True

    # Try basename match (edge case for simple filenames)
    basename = os.path.basename(file_path)
    for pattern in patterns:
        if fnmatch.fnmatch(basename, pattern):
            return True

    return False


def deny(permissionDecisionReason: str) -> None:
    hook_specific_output = {
        "permissionDecision": "deny",
        "permissionDecisionReason": permissionDecisionReason,
    }
    # Claude Code（实证 2.1.237）要求 hookEventName 精确等于 "PreToolUse"
    # 才把该 JSON 当权限决策；缺字段时报 hook error 后继续写入。
    backend = os.environ.get("WORKER_GUARD_BACKEND", "").strip().lower()
    if backend in ("claude-code", "claude_code", "claude"):
        hook_specific_output["hookEventName"] = "PreToolUse"
    deny_output = {"hookSpecificOutput": hook_specific_output}
    print(json.dumps(deny_output), file=sys.stdout)
    # Exit 0: codebuddy interprets JSON permissionDecision (ref: codebuddy.cn/docs/cli/permissions)
    # claude-code 额外要求上方 hookEventName 才承认 deny。
    sys.exit(0)


def main():
    # ---- read stdin JSON (needed for both legacy allowlist and reviewer layer) ----
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return  # empty stdin → allow (safety)
        data = json.loads(raw)
    except (json.JSONDecodeError, IOError):
        return  # unparseable → allow (safety)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    # ---- only check Edit/Write/NotebookEdit/Update ----
    # Update 是 Claude Code（≥2.x）的文件编辑工具名。Task-114 实证事故：
    # 工具集与 spawn 生成的 PreToolUse matcher 漏 Update，reviewer 对
    # Session Context 外文件的 Update 写入完全绕过 scope guard。Update
    # 的 tool_input 与 Edit 同构（file_path），必须走同一条 fail-closed 路径。
    if tool_name not in ("Edit", "Write", "NotebookEdit", "Update"):
        return  # not a write tool → allow

    # ---- extract file path ----
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not file_path:
        return  # no file path → allow (other tool usage, unlikely)

    # ---- get worktree root for path normalization ----
    worktree_root = get_worktree_root()

    # ---- reviewer role discipline (v2.14.0) ----
    role = os.environ.get("SCOPE_GUARD_ROLE", "").strip()
    if role == REVIEWER_ROLE:
        # 硬拒绝：任何 config/ 目录下的 *.local.yaml（安装 Skill 的本地运行
        # 配置）对 reviewer 永远不可写——授予修复权也不改变这一条。
        if is_config_local_yaml(file_path):
            deny(
                "reviewer role: config/*.local.yaml 是安装 Skill 的本地运行配置，"
                f"reviewer 永远不可写 (tried {file_path})"
            )
            return
        grant = os.environ.get("SCOPE_GUARD_REVIEW_REPAIR_GRANT", "").strip() == "1"
        if not grant:
            session_root = os.environ.get("SCOPE_GUARD_SESSION_ROOT", "").strip()
            if session_root:
                tried_abs = os.path.abspath(file_path)
                root_abs = os.path.abspath(session_root)
                inside = tried_abs == root_abs or tried_abs.startswith(root_abs + os.sep)
                if inside:
                    return  # own Session Context → allow
            deny(
                "reviewer role: 默认可写范围只有自身 Session Context；"
                "写被审分支需要任务合同显式授予修复权"
                f" (tried {file_path})"
            )
            return
        # 授予修复权 → 继续走下方 allowlist（spawn 已为 reviewer 注入allowlist）。

    # ---- 非 reviewer 角色：自身 Session Context 控制面保持可达（Task-114-R2B）----
    # deny 真正生效（Claude backend 补齐 hookEventName）后，窄 --allow-paths
    # 的 implementer 会被硬挡在 .claude/agent-sessions/<session>/ 之外，无法写
    # 任务合同要求的 STATUS/RESULT。这里放行 Session Context 自身目录内的写入；
    # 父目录、兄弟 session、仓库代码都不在严格前缀内；config/*.local.yaml 即使
    # 落在 session 目录内也明确排除。reviewer 层语义不受影响（上方已 return）。
    if role != REVIEWER_ROLE:
        session_root = os.environ.get("SCOPE_GUARD_SESSION_ROOT", "").strip()
        if session_root and not is_config_local_yaml(file_path):
            tried_abs = os.path.abspath(file_path)
            root_abs = os.path.abspath(session_root)
            if tried_abs == root_abs or tried_abs.startswith(root_abs + os.sep):
                return  # own Session Context → allow

    # ---- no SCOPE_GUARD_ALLOW → no-op (backward compatible) ----
    allow_env = os.environ.get("SCOPE_GUARD_ALLOW", "").strip()
    if not allow_env:
        return  # exit 0, no output → allow

    allowed_patterns = [p.strip() for p in allow_env.split(":") if p.strip()]

    # ---- check against allow list ----
    if match_any_pattern(file_path, allowed_patterns, worktree_root):
        return  # matched → allow

    # ---- out of scope → deny ----
    deny(f"out of scope: 仅允许 {allow_env} (tried {file_path})")


if __name__ == "__main__":
    main()
