#!/usr/bin/env bash
# ensure-claude-path.sh - 在当前 shell 上下文前置补齐 Claude CLI 所在 PATH。
#
# 用法（其它脚本 source 本文件）：
#   source "$(dirname "${BASH_SOURCE[0]}")/ensure-claude-path.sh"
#   ensure_claude_in_path   # 静默检测+注入；幂等，可多次调用
#
# 覆盖布局：
#   - macOS (Homebrew)：/opt/homebrew/bin（Apple Silicon）、/usr/local/bin（Intel）
#   - Linux 用户级：~/.local/bin（官方安装器）、~/.cargo/bin（rust 系少见）
#   - WSL：与 Linux 同布局
#   - 兜底：未找到时仅打 SPAWN_WORKER_PATH_WARN（不报错；可能 PM 装了别的 wrapper）
#
# 设计：不动 PATH 之外的 env；只 prepend，找不到时静默回退。
# 来源：2026-07-12 PM 双 worker（云南 P5 + 南通律协半天版）实测
#       `which claude` 在 wrapper 后 = 未找到；claude 实际在
#       `~/.local/bin/claude`（软链到 ~/.local/share/claude/versions/<ver>）。
#       当时 spawn PM 改用 `export PATH="$HOME/.local/bin:$PATH"` 临时解决，
#       沉淀为本 helper，让所有 launch 脚本 startup 时一键注入。

set -euo pipefail

# 公共函数：检测 `which claude`，命中直接返回；不命中则按 macOS/Linux 顺序
# 依次尝试 ~/.local/bin / /opt/homebrew/bin / /usr/local/bin / ~/.cargo/bin，
# 命中的目录 prepend 到 PATH，打 SPAWN_WORKER_PATH_INJECT 日志到 stderr。
ensure_claude_in_path() {
  # 已能找到：不做事，幂等
  if command -v claude >/dev/null 2>&1; then
    return 0
  fi

  local candidate=""
  for dir in \
    "$HOME/.local/bin" \
    /opt/homebrew/bin \
    /usr/local/bin \
    "$HOME/.cargo/bin"; do
    if [ -x "$dir/claude" ]; then
      candidate="$dir"
      break
    fi
  done

  if [ -z "$candidate" ]; then
    echo "SPAWN_WORKER_PATH_WARN: claude binary not found in ~/.local/bin / /opt/homebrew/bin / /usr/local/bin / ~/.cargo/bin (continuing with current PATH)" >&2
    return 0
  fi

  export PATH="$candidate:$PATH"
  echo "SPAWN_WORKER_PATH_INJECT: prepended $candidate (claude=$candidate/claude)" >&2
}

# 若脚本直接执行（非被 source），也支持 `bash ensure-claude-path.sh` 单跑
# 一次注入并打印当前 PATH 中的 claude 解析路径，方便 PM 排障。
if [ "${BASH_SOURCE[0]:-$0}" = "${0}" ]; then
  ensure_claude_in_path
  if command -v claude >/dev/null 2>&1; then
    echo "ensure-claude-path: claude resolved to $(command -v claude)"
  else
    echo "ensure-claude-path: claude still not resolvable in PATH" >&2
    exit 64
  fi
fi
