#!/usr/bin/env bash
# ensure-claude-path.sh - 在当前 shell 上下文前置补齐 CLI 所在 PATH。
#
# 用法（其它脚本 source 本文件）：
#   source "$(dirname "${BASH_SOURCE[0]}")/ensure-claude-path.sh"
#   ensure_in_path claude     # 通用版（v2.0+），按需探测指定二进制
#   ensure_in_path orca       # ORCA CLI 探测（spawn-worker.sh ORCA 模式用）
#   ensure_claude_in_path     # 向后兼容别名，等价于 ensure_in_path claude
#
# 覆盖布局（按顺序探测，命中即用）：
#   - macOS (Homebrew)：/opt/homebrew/bin（Apple Silicon）、/usr/local/bin（Intel）
#   - Linux 用户级：~/.local/bin（官方安装器）、~/.cargo/bin（rust 系少见）
#   - ORCA 桌面端（macOS）：/Applications/Orca.app/Contents/Resources/bin
#   - 兜底：未找到时仅打 SPAWN_WORKER_PATH_WARN（不报错；可能 PM 装了别的 wrapper）
#
# 设计：不动 PATH 之外的 env；只 prepend，找不到时静默回退。
# 来源：2026-07-12 PM 双 worker（云南 P5 + 南通律协半天版）实测
#       `which claude` 在 wrapper 后 = 未找到；claude 实际在
#       `~/.local/bin/claude`（软链到 ~/.local/share/claude/versions/<ver>）。
#       当时 spawn PM 改用 `export PATH="$HOME/.local/bin:$PATH"` 临时解决，
#       沉淀为本 helper，让所有 launch 脚本 startup 时一键注入。
# v2.0（2026-08-12）：参数化为 ensure_in_path <bin_name>，候选目录追加 ORCA 桌面端
#       路径，spawn-worker.sh ORCA 模式可直接 ensure_in_path orca；保留
#       ensure_claude_in_path 别名保持向后兼容。

set -euo pipefail

# 公共函数：检测 `which $1`，命中直接返回；不命中则按 macOS/Linux/ORCA 顺序
# 依次尝试 ~/.local/bin / /opt/homebrew/bin / /usr/local/bin / ~/.cargo/bin /
# /Applications/Orca.app/Contents/Resources/bin，命中的目录 prepend 到 PATH，
# 打 SPAWN_WORKER_PATH_INJECT 日志到 stderr。
ensure_in_path() {
  local bin_name="${1:-claude}"

  # 已能找到：不做事，幂等
  if command -v "$bin_name" >/dev/null 2>&1; then
    return 0
  fi

  local candidate=""
  for dir in \
    "$HOME/.local/bin" \
    /opt/homebrew/bin \
    /usr/local/bin \
    "$HOME/.cargo/bin" \
    /Applications/Orca.app/Contents/Resources/bin; do
    if [ -x "$dir/$bin_name" ]; then
      candidate="$dir"
      break
    fi
  done

  if [ -z "$candidate" ]; then
    echo "SPAWN_WORKER_PATH_WARN: $bin_name binary not found in ~/.local/bin / /opt/homebrew/bin / /usr/local/bin / ~/.cargo/bin / /Applications/Orca.app/Contents/Resources/bin (continuing with current PATH)" >&2
    return 0
  fi

  export PATH="$candidate:$PATH"
  echo "SPAWN_WORKER_PATH_INJECT: prepended $candidate ($bin_name=$candidate/$bin_name)" >&2
}

# 向后兼容：v2.0 之前的旧函数名，等价于 ensure_in_path claude。
ensure_claude_in_path() {
  ensure_in_path claude
}

# 若脚本直接执行（非被 source），也支持 `bash ensure-claude-path.sh [bin_name]`
# 单跑一次注入并打印当前 PATH 中的 CLI 解析路径，方便 PM 排障。
# 默认 bin_name=claude（保持 v2.0 之前行为）；显式传 orca 等探测 ORCA CLI。
if [ "${BASH_SOURCE[0]:-$0}" = "${0}" ]; then
  bin_arg="${1:-claude}"
  ensure_in_path "$bin_arg"
  if command -v "$bin_arg" >/dev/null 2>&1; then
    echo "ensure-claude-path: $bin_arg resolved to $(command -v "$bin_arg")"
  else
    echo "ensure-claude-path: $bin_arg still not resolvable in PATH" >&2
    exit 64
  fi
fi
