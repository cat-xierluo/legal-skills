#!/bin/bash
# scope-guard-hook.sh — PreToolUse hook wrapper for codebuddy/qoder
#
# Why this wrapper exists: codebuddy/qoder 调 hook command 时,直接 `python3 scope-guard.py`
# 的 stdin 不会传给 python3(实测 stdin 丢失 → scope-guard no-op → 越界不拦)。
# 用 `cat` 中转 stdin 后 pipe 给 scope-guard.py,stdin 才正确传递。
# 实测(2026-07-05):wrapper 工作(blocked/b.txt 被 hook deny 拦);直接 python3 不工作。
#
# scope-guard.py 的实际逻辑(读 SCOPE_GUARD_ALLOW env + stdin tool_input.file_path 匹配)
# 见 scripts/scope-guard.py。

INPUT=$(cat)
echo "$INPUT" | python3 "$(dirname "$0")/scope-guard.py"
