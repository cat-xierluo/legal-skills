#!/usr/bin/env bash
# check-dependencies.sh — report local dependencies for multi-agent orchestration.

set -euo pipefail

CHECK_BACKENDS=()
CHECK_GH=0
CHECK_TERMINAL_SPLIT=0
STRICT=0

usage() {
  cat >&2 <<'USAGE'
Usage:
  check-dependencies.sh [options]

Options:
  --backend NAME             Check backend CLI: claude-code | claude-oauth | codex | opencode |
                             codebuddy | qoderwork-cn | custom
                             Repeat for multiple backends.
  --check-gh                 Check GitHub CLI for PR/mergeability workflows.
  --check-terminal-split     Check terminal split helper dependencies for current terminal.
  --strict                   Exit non-zero on WARN as well as MISSING.

Default checks core script dependencies only. The script does not install tools,
start workers, write files, or change configuration.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend)
      CHECK_BACKENDS+=("$2")
      shift 2
      ;;
    --check-gh)
      CHECK_GH=1
      shift
      ;;
    --check-terminal-split)
      CHECK_TERMINAL_SPLIT=1
      shift
      ;;
    --strict)
      STRICT=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 64
      ;;
  esac
done

missing=0
warn=0

report_ok() {
  printf 'DEPENDENCY_OK: %s%s\n' "$1" "${2:+ ($2)}"
}

report_warn() {
  printf 'DEPENDENCY_WARN: %s%s\n' "$1" "${2:+ ($2)}"
  warn=1
}

report_missing() {
  printf 'DEPENDENCY_MISSING: %s%s\n' "$1" "${2:+ ($2)}"
  missing=1
}

check_cmd() {
  local cmd="$1"
  local why="${2:-}"
  if command -v "$cmd" >/dev/null 2>&1; then
    local path
    path=$(command -v "$cmd")
    report_ok "$cmd" "$path${why:+; $why}"
  else
    report_missing "$cmd" "$why"
  fi
}

check_optional_cmd() {
  local cmd="$1"
  local why="${2:-}"
  if command -v "$cmd" >/dev/null 2>&1; then
    local path
    path=$(command -v "$cmd")
    report_ok "$cmd" "$path${why:+; $why}"
  else
    report_warn "$cmd" "$why"
  fi
}

# check_app_bundle_binary — 多源检测: PATH + 已知 .app bundle 绝对路径
# 用法: check_app_bundle_binary <cmd> <bundle_path_1> [bundle_path_2 ...]
# 行为:
#   - cmd 在 PATH 中 → 静默(前置 check_optional_cmd 已 OK, 不重复)
#   - cmd 不在 PATH 但在某个 bundle 中 → WARN, 列出路径, 建议 spawn 传绝对路径或 sudo ln -s
#   - cmd 既不在 PATH 也不在 bundle → WARN, 提示安装桌面端
# 解决 false-negative: 桌面端已装但没建 symlink 时 `which codebuddy` 报 not found
check_app_bundle_binary() {
  local cmd="$1"
  shift
  local bundle_paths=("$@")
  local found_in_bundle=""

  if command -v "$cmd" >/dev/null 2>&1; then
    return 0  # 已 PATH 内, 不重复报告
  fi

  for bundle_path in "${bundle_paths[@]}"; do
    if [ -x "$bundle_path" ]; then
      found_in_bundle="$bundle_path"
      break
    fi
  done

  if [ -n "$found_in_bundle" ]; then
    report_warn "$cmd" "PATH 无 symlink; 但 $found_in_bundle 存在。可 (a) spawn-worker.sh --command 直接传绝对路径, 或 (b) sudo ln -s $found_in_bundle /usr/local/bin/$cmd 永久 symlink"
  else
    report_warn "$cmd" "PATH 无 symlink, 已知 .app bundle 路径中也未找到; 需安装 $cmd 对应桌面端(WorkBuddy / QoderWork) 或自定义 CLI"
  fi
}

check_bash_version() {
  local major="${BASH_VERSINFO[0]:-0}"
  if [ "$major" -ge 4 ]; then
    report_ok "bash>=4" "current=$BASH_VERSION"
  else
    report_warn "bash>=4" "current=${BASH_VERSION:-unknown}; pm-monitor.sh requires bash 4+"
  fi
}

echo "DEPENDENCY_CHECK: core"
check_cmd bash "scripts use bash"
check_bash_version
check_cmd git "worktree, branch, commit and diff checks"
check_cmd jq "STATUS/METADATA JSON parsing and rendering"
check_cmd awk "worktree lookup and lint checks"
check_cmd sed "timestamp cleanup and pane filtering"
check_cmd find "progress signal checks"
check_cmd date "stale and timestamp checks"
check_cmd mktemp "smoke tests and temporary files"

if command -v stat >/dev/null 2>&1; then
  report_ok "stat" "$(command -v stat)"
else
  report_missing "stat" "mtime checks"
fi

check_optional_cmd tmux "required for spawn-worker.sh and tmux diagnostics"

if [ "$CHECK_GH" -eq 1 ]; then
  echo "DEPENDENCY_CHECK: github"
  check_optional_cmd gh "PR and mergeability checks; run gh auth status separately if needed"
fi

for backend in "${CHECK_BACKENDS[@]}"; do
  case "$backend" in
    claude-code|claude-oauth)
      echo "DEPENDENCY_CHECK: backend=$backend"
      check_optional_cmd claude "Claude Code worker backend"
      ;;
    codex)
      echo "DEPENDENCY_CHECK: backend=codex"
      check_optional_cmd codex "Codex worker backend"
      ;;
    opencode)
      echo "DEPENDENCY_CHECK: backend=opencode"
      check_optional_cmd opencode "OpenCode worker backend"
      ;;
    codebuddy)
      echo "DEPENDENCY_CHECK: backend=codebuddy"
      check_optional_cmd codebuddy "WorkBuddy/CodeBuddy worker backend"
      check_app_bundle_binary codebuddy \
        "/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy"
      ;;
    qoderwork-cn|qoderclicn)
      echo "DEPENDENCY_CHECK: backend=$backend"
      check_optional_cmd qoderclicn "QoderWork CN worker backend"
      # 国际版二进制是 qodercli(不是 qoderclicn), 但用户脚本可能 alias — 同时报
      # 旧 Qoder 编辑器(已废弃) /usr/local/bin/qoder 不可作为 agent CLI
      check_app_bundle_binary qoderclicn \
        "/Applications/QoderWork CN.app/Contents/Resources/bin/qoderclicn" \
        "/Applications/QoderWork.app/Contents/Resources/bin/qodercli"
      ;;
    custom)
      echo "DEPENDENCY_CHECK: backend=custom"
      report_ok "custom" "PM must provide --command"
      ;;
    *)
      report_warn "backend=$backend" "unknown backend; no CLI check available"
      ;;
  esac
done

if [ "$CHECK_TERMINAL_SPLIT" -eq 1 ]; then
  echo "DEPENDENCY_CHECK: terminal-split"
  terminal="${TERMINAL_OVERRIDE:-${TERM_PROGRAM:-unknown}}"
  report_ok "terminal-detected" "$terminal"
  case "$terminal" in
    iTerm.app|iterm2|WarpTerminal|warp|ghostty|Ghostty|Apple_Terminal|terminal_app|Zed|zed)
      check_optional_cmd osascript "macOS GUI terminal automation"
      check_optional_cmd pbpaste "clipboard restore for GUI terminal fallback"
      check_optional_cmd pbcopy "clipboard restore for GUI terminal fallback"
      check_optional_cmd swift "mouse click fallback for some GUI terminals"
      ;;
    xterm-kitty|kitty)
      check_optional_cmd kitty "Kitty remote control API"
      ;;
    WezTerm|wezterm)
      check_optional_cmd wezterm "WezTerm CLI"
      ;;
    *)
      report_warn "terminal-split" "unknown terminal; set TERMINAL_OVERRIDE if needed"
      ;;
  esac
fi

if [ "$missing" -eq 0 ] && { [ "$warn" -eq 0 ] || [ "$STRICT" -eq 0 ]; }; then
  echo "DEPENDENCY_CHECK_OK"
  exit 0
fi

if [ "$missing" -ne 0 ]; then
  echo "DEPENDENCY_CHECK_FAILED"
  exit 1
fi

echo "DEPENDENCY_CHECK_WARNINGS"
exit 2
