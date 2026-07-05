#!/usr/bin/env python3
"""scope-guard.py — PreToolUse hook: deny out-of-scope file writes.

Reads stdin JSON (tool_name + tool_input), checks tool_input.file_path
against SCOPE_GUARD_ALLOW glob patterns (colon-separated).

Designed for both codebuddy and qoder (stdin/stdout JSON format identical).
Based on ref 07 §9.3 (qoder PreToolUse hook, unbypassable even in bypass_permissions)
and ref 08 §12.3 (codebuddy PreToolUse hook, semantic parity expected).

Exit 0 + no output = allow (passes through to next hook / permission pipeline).
Exit 0 + deny JSON on stdout = hard block (permissionDecision: deny, short-circuits).
Exit non-zero = hook error (treated as allow by most CLI implementations for safety).

No SCOPE_GUARD_ALLOW → no-op (backward compatible, scope-guard not active).
"""

import fnmatch
import json
import os
import sys


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


def main():
    # ---- no SCOPE_GUARD_ALLOW → no-op (backward compatible) ----
    allow_env = os.environ.get("SCOPE_GUARD_ALLOW", "").strip()
    if not allow_env:
        return  # exit 0, no output → allow

    allowed_patterns = [p.strip() for p in allow_env.split(":") if p.strip()]

    # ---- read stdin JSON ----
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return  # empty stdin → allow (safety)
        data = json.loads(raw)
    except (json.JSONDecodeError, IOError):
        return  # unparseable → allow (safety)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    # ---- only check Edit/Write/NotebookEdit ----
    if tool_name not in ("Edit", "Write", "NotebookEdit"):
        return  # not a write tool → allow

    # ---- extract file path ----
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not file_path:
        return  # no file path → allow (other tool usage, unlikely)

    # ---- get worktree root for path normalization ----
    worktree_root = get_worktree_root()

    # ---- check against allow list ----
    if match_any_pattern(file_path, allowed_patterns, worktree_root):
        return  # matched → allow

    # ---- out of scope → deny ----
    deny_output = {
        "hookSpecificOutput": {
            "permissionDecision": "deny",
            "permissionDecisionReason": f"out of scope: 仅允许 {allow_env} (tried {file_path})"
        }
    }
    print(json.dumps(deny_output), file=sys.stdout)
    # Exit 0: codebuddy interprets JSON permissionDecision (ref: codebuddy.cn/docs/cli/permissions)
    sys.exit(0)


if __name__ == "__main__":
    main()
