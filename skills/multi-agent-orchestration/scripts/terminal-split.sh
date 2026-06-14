#!/bin/bash
# terminal-split.sh — 跨终端/编辑器分屏并执行命令
#
# 支持:
#   iTerm2       — 原生 AppleScript (最佳)
#   Kitty        — kitty @ 远程控制 API
#   WezTerm      — wezterm cli
#   Warp         — 快捷键分屏 + 剪贴板
#   Ghostty      — 菜单点击 + 剪贴板
#   Zed          — 菜单点击 + 剪贴板
#   Terminal.app — 菜单点击 + 剪贴板 (不支持分屏，退化为新标签页)
#
# 用法: terminal-split.sh [方向] [命令]
# 方向: right (默认), left, down, up, tab
#       tab = 新建标签页（而非分屏）
# 命令: 要在新 pane/tab 中执行的命令
#
# 示例:
#   terminal-split.sh right "tmux attach -t worker-1"
#   terminal-split.sh tab "tmux attach -t worker-2"
#   terminal-split.sh down "htop"
#   terminal-split.sh          # 仅分屏，不执行命令
#
# 检测原理:
#   各终端通过 TERM_PROGRAM 环境变量标识自己:
#     WarpTerminal   → Warp
#     iTerm.app      → iTerm2
#     ghostty        → Ghostty
#     Apple_Terminal → Terminal.app
#     xterm-kitty    → Kitty
#     WezTerm        → WezTerm
#     Zed / zed      → Zed
#
#   也可通过 TERMINAL_OVERRIDE 环境变量强制指定。

set -euo pipefail

DIRECTION="${1:-right}"
COMMAND="${2:-}"

if [ "$DIRECTION" = "--help" ] || [ "$DIRECTION" = "-h" ]; then
  cat <<'USAGE'
terminal-split.sh — 跨终端/编辑器分屏并执行命令

用法: terminal-split.sh [方向] [命令]
方向: right (默认), left, down, up, tab
      tab = 新建标签页（而非分屏）
命令: 要在新 pane/tab 中执行的命令

示例:
  terminal-split.sh right "tmux attach -t worker-1"
  terminal-split.sh tab  "tmux attach -t worker-2"
  terminal-split.sh down "htop"
  terminal-split.sh             # 仅分屏，不执行命令

终端检测: TERM_PROGRAM (WarpTerminal/iTerm.app/ghostty/...)
         可用 TERMINAL_OVERRIDE=warp|iterm2|kitty|wezterm|ghostty|zed|terminal_app 强制指定

Warp 分屏快捷键: Cmd+D = 右分屏, Cmd+Shift+D = 下分屏
USAGE
  exit 0
fi

# ========== 检测当前终端 ==========
detect_terminal() {
  if [ -n "${TERMINAL_OVERRIDE:-}" ]; then
    echo "$TERMINAL_OVERRIDE"
    return
  fi

  local tp="${TERM_PROGRAM:-}"

  case "$tp" in
    iTerm.app)                echo "iterm2" ;;
    WarpTerminal)             echo "warp" ;;
    ghostty)                  echo "ghostty" ;;
    Apple_Terminal)           echo "terminal_app" ;;
    xterm-kitty|kitty)        echo "kitty" ;;
    WezTerm)                  echo "wezterm" ;;
    Zed|zed)                  echo "zed" ;;
    *)                        echo "unknown" ;;
  esac
}

# ========== 剪贴板辅助 ==========
paste_command() {
  local cmd="$1"
  local process_name="$2"
  local focus_action="$3"

  local orig_clipboard
  orig_clipboard=$(pbpaste 2>/dev/null || true)

  # 获取进程名对应的应用名（用于激活窗口）
  local app_name="$process_name"

  osascript <<EOF
tell application "${app_name}" to activate
delay 0.2
tell application "System Events"
  tell process "${process_name}"
    delay 0.3
    ${focus_action}
    delay 0.2
    set the clipboard to "${cmd}"
    keystroke "v" using command down
    delay 0.2
    keystroke return
  end tell
end tell
EOF

  if [ -n "$orig_clipboard" ]; then
    (sleep 1 && printf '%s' "$orig_clipboard" | pbcopy) &>/dev/null &
  fi
}

# ========== 鼠标点击辅助 ==========
# 使用 Swift + CoreGraphics 点击指定屏幕坐标
# 某些终端（如 Warp）分屏后无法通过菜单/键盘可靠切换面板焦点
# （TUI 应用会捕获键盘事件），因此使用鼠标点击定位到新面板
click_at() {
  local x="$1" y="$2"
  swift -e "
import Foundation
import CoreGraphics
let p = CGPoint(x: CGFloat($x), y: CGFloat($y))
let s = CGEventSource(stateID: .hidSystemState)
CGEvent(mouseEventSource: s, mouseType: .mouseMoved, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
Thread.sleep(forTimeInterval: 0.15)
CGEvent(mouseEventSource: s, mouseType: .leftMouseDown, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
Thread.sleep(forTimeInterval: 0.05)
CGEvent(mouseEventSource: s, mouseType: .leftMouseUp, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
" 2>/dev/null
}

# ========== iTerm2: 原生 AppleScript ==========
split_iterm2() {
  local dir="$1" cmd="$2"
  local method
  case "$dir" in right|left) method="horizontally" ;; down|up) method="vertically" ;; esac

  if [ -n "$cmd" ]; then
    osascript <<EOF
tell application "iTerm2"
  tell current window
    set newSplit to (split ${method} with default profile session of current tab)
    tell newSplit
      write text "${cmd}"
    end tell
  end tell
end tell
EOF
  else
    osascript <<EOF
tell application "iTerm2"
  tell current window
    split ${method} with default profile session of current tab
  end tell
end tell
EOF
  fi
}

# ========== Kitty: kitty @ 远程控制 API ==========
split_kitty() {
  local dir="$1" cmd="$2"
  local loc
  case "$dir" in right) loc="vsplit" ;; left) loc="vsplit left" ;; down) loc="split" ;; up) loc="split top" ;; esac

  local pane_id
  pane_id=$(kitty @ launch --location="$loc" --no-response 2>/dev/null || kitty @ launch --location="$loc" 2>/dev/null)

  if [ -n "$cmd" ] && [ -n "$pane_id" ]; then
    kitty @ send-text --match "id:$pane_id" "$cmd"$'\n'
  elif [ -n "$cmd" ]; then
    # fallback: 用剪贴板
    paste_command "$cmd" "Ghostty" 'keystroke "]" using command down'
  fi
}

# ========== WezTerm: wezterm cli ==========
split_wezterm() {
  local dir="$1" cmd="$2"
  local split_dir
  case "$dir" in right) split_dir="--right" ;; left) split_dir="--left" ;; down) split_dir="--bottom" ;; up) split_dir="--top" ;; esac

  local pane_id
  pane_id=$(wezterm cli split-pane "$split_dir" 2>/dev/null)

  if [ -n "$cmd" ] && [ -n "$pane_id" ]; then
    wezterm cli send-text --pane-id "$pane_id" "$cmd"$'\n'
  fi
}

# ========== Warp: 窗口定位 + 快捷键分屏 + 剪贴板 ==========
# 分两步，缺一不可：
#   1. 先通过 pwd basename 匹配 Warp 窗口标题并前置正确窗口，
#      否则多个 Warp 窗口时 Cmd+D 会分屏到别的窗口。
#   2. 再在（已前置的）主窗口用应用层快捷键分屏（不依赖菜单名、不受 Block 输入模式影响）：
#        Cmd+D        = Split Pane Right (right/left)
#        Cmd+Shift+D  = Split Pane Down  (down/up)
#   3. 分屏后新 pane 自动获焦，用 set clipboard + Cmd+V 粘贴命令再回车提交。
# 局限：窗口前置到「窗口级」；若同一窗口有多个 tab，需保证 PM 在当前 tab（通常成立）。
#       匹配不到窗口标题时静默跳过，可能在非目标窗口分屏——此时改用 tab 模式或手动。
split_warp() {
  local dir="$1" cmd="$2"
  local ks
  case "$dir" in
    right|left) ks='keystroke "d" using command down' ;;
    down|up)    ks='keystroke "d" using {command down, shift down}' ;;
    *) echo "warp: 未知方向 '$dir' (支持 right/left/down/up)" >&2; exit 1 ;;
  esac

  # 1. 定位到当前项目的 Warp 窗口（pwd basename 匹配窗口标题，前置）
  local project_name
  project_name=$(basename "$(pwd)")
  osascript <<EOF 2>/dev/null || true
tell application "System Events"
  tell process "Warp"
    set windowCount to count of windows
    repeat with i from 1 to windowCount
      if name of window i contains "${project_name}" then
        set index of window i to 1
        exit repeat
      end if
    end repeat
  end tell
end tell
EOF

  # 2. 激活 Warp 并在（已前置的）主窗口当前 tab 触发分屏快捷键
  osascript <<EOF
tell application "Warp" to activate
delay 0.3
tell application "System Events"
  ${ks}
end tell
EOF

  # 分屏后在当前（新）pane 粘贴命令并提交
  if [ -n "$cmd" ]; then
    local orig_clipboard
    orig_clipboard=$(pbpaste 2>/dev/null || true)
    osascript <<EOF
tell application "Warp" to activate
delay 0.4
tell application "System Events"
  set the clipboard to "${cmd}"
  delay 0.1
  keystroke "v" using command down
  delay 0.2
  keystroke return
end tell
EOF
    if [ -n "$orig_clipboard" ]; then
      (sleep 1 && printf '%s' "$orig_clipboard" | pbcopy) &>/dev/null &
    fi
  fi
}

# ========== Ghostty: 菜单点击 + 剪贴板 ==========
split_ghostty() {
  local dir="$1" cmd="$2"
  local menu_item
  case "$dir" in
    right) menu_item="New Pane to the Right" ;; left) menu_item="New Pane to the Left" ;;
    down)  menu_item="New Pane Below"        ;; up)   menu_item="New Pane Above" ;;
  esac

  osascript <<EOF
tell application "Ghostty" to activate
delay 0.2
tell application "System Events"
  tell process "Ghostty"
    click menu item "${menu_item}" of menu "Shell" of menu bar 1
  end tell
end tell
EOF

  if [ -n "$cmd" ]; then
    paste_command "$cmd" "Ghostty" 'keystroke "]" using command down'
  fi
}

# ========== Zed: 菜单点击 + 剪贴板 ==========
split_zed() {
  local dir="$1" cmd="$2"
  local menu_item
  case "$dir" in
    right) menu_item="Split Right" ;; left) menu_item="Split Left" ;;
    down)  menu_item="Split Down"  ;; up)   menu_item="Split Up" ;;
  esac

  osascript <<EOF
tell application "Zed" to activate
delay 0.2
tell application "System Events"
  tell process "Zed"
    click menu item "${menu_item}" of menu "Editor Layout" of menu item "Editor Layout" of menu "View" of menu bar 1
  end tell
end tell
EOF

  if [ -n "$cmd" ]; then
    osascript <<'EOF'
tell application "System Events"
  tell process "Zed"
    click menu item "Terminal Panel" of menu "View" of menu bar 1
  end tell
end tell
EOF
    paste_command "$cmd" "Zed" 'keystroke "`" using control down'
  fi
}

# ========== Terminal.app: 新标签页 + 剪贴板 ==========
# Terminal.app 不支持分屏，退化为新标签页
split_terminal_app() {
  local _dir="$1"  # 方向参数忽略，Terminal.app 不支持分屏
  local cmd="$2"

  # 新建标签页
  osascript <<'EOF'
tell application "Terminal" to activate
delay 0.2
tell application "System Events"
  tell process "Terminal"
    keystroke "t" using command down
  end tell
end tell
EOF

  if [ -n "$cmd" ]; then
    local orig_clipboard
    orig_clipboard=$(pbpaste 2>/dev/null || true)

    osascript <<EOF
tell application "System Events"
  tell process "Terminal"
    delay 0.3
    set the clipboard to "${cmd}"
    keystroke "v" using command down
    delay 0.2
    keystroke return
  end tell
end tell
EOF

    if [ -n "$orig_clipboard" ]; then
      (sleep 1 && printf '%s' "$orig_clipboard" | pbcopy) &>/dev/null &
    fi
  fi
}

# ========== 新标签页模式 ==========
# 用 tab 命令打开新标签页（而非分屏），每个标签页独立全屏

open_tab_iterm2() {
  local cmd="$1"
  if [ -n "$cmd" ]; then
    osascript <<EOF
tell application "iTerm2"
  tell current window
    set newTab to (create tab with default profile)
    tell current session of newTab
      write text "${cmd}"
    end tell
  end tell
end tell
EOF
  else
    osascript <<'EOF'
tell application "iTerm2"
  tell current window
    create tab with default profile
  end tell
end tell
EOF
  fi
}

open_tab_kitty() {
  local cmd="${1:-}"
  kitty @ launch --type=tab $cmd
}

open_tab_wezterm() {
  local cmd="${1:-}"
  wezterm cli spawn --new-window $cmd
}

open_tab_warp() {
  local cmd="$1"
  osascript <<'EOF'
tell application "Warp" to activate
delay 0.2
tell application "System Events"
  tell process "Warp"
    click menu item "New Tab" of menu "File" of menu bar 1
  end tell
end tell
EOF

  if [ -n "$cmd" ]; then
    local orig_clipboard
    orig_clipboard=$(pbpaste 2>/dev/null || true)
    osascript <<EOF
tell application "System Events"
  tell process "Warp"
    delay 0.5
    set the clipboard to "${cmd}"
    keystroke "v" using command down
    delay 0.2
    keystroke return
  end tell
end tell
EOF
    if [ -n "$orig_clipboard" ]; then
      (sleep 1 && printf '%s' "$orig_clipboard" | pbcopy) &>/dev/null &
    fi
  fi
}

open_tab_ghostty() {
  local cmd="$1"
  osascript <<'EOF'
tell application "Ghostty" to activate
delay 0.2
tell application "System Events"
  tell process "Ghostty"
    click menu item "New Tab" of menu "Shell" of menu bar 1
  end tell
end tell
EOF

  if [ -n "$cmd" ]; then
    local orig_clipboard
    orig_clipboard=$(pbpaste 2>/dev/null || true)
    osascript <<EOF
tell application "System Events"
  tell process "Ghostty"
    delay 0.5
    set the clipboard to "${cmd}"
    keystroke "v" using command down
    delay 0.2
    keystroke return
  end tell
end tell
EOF
    if [ -n "$orig_clipboard" ]; then
      (sleep 1 && printf '%s' "$orig_clipboard" | pbcopy) &>/dev/null &
    fi
  fi
}

open_tab_terminal_app() {
  split_terminal_app "tab" "$1"
}

# ========== 主逻辑 ==========
TERMINAL=$(detect_terminal)

# tab 模式：新建标签页
if [ "$DIRECTION" = "tab" ]; then
  case "$TERMINAL" in
    iterm2)       echo "iTerm2 — 新标签页"; open_tab_iterm2 "$COMMAND" ;;
    kitty)        echo "Kitty — 新标签页"; open_tab_kitty "$COMMAND" ;;
    wezterm)      echo "WezTerm — 新标签页"; open_tab_wezterm "$COMMAND" ;;
    warp)         echo "Warp — 新标签页"; open_tab_warp "$COMMAND" ;;
    ghostty)      echo "Ghostty — 新标签页"; open_tab_ghostty "$COMMAND" ;;
    terminal_app) echo "Terminal.app — 新标签页"; open_tab_terminal_app "$COMMAND" ;;
    *)            echo "未检测到支持的终端" >&2; exit 1 ;;
  esac
  exit 0
fi

# 分屏模式
case "$TERMINAL" in
  iterm2)       echo "iTerm2 — 原生 AppleScript"; split_iterm2 "$DIRECTION" "$COMMAND" ;;
  kitty)        echo "Kitty — kitty @ API"; split_kitty "$DIRECTION" "$COMMAND" ;;
  wezterm)      echo "WezTerm — wezterm cli"; split_wezterm "$DIRECTION" "$COMMAND" ;;
  warp)         echo "Warp — 快捷键分屏 + 剪贴板"; split_warp "$DIRECTION" "$COMMAND" ;;
  ghostty)      echo "Ghostty — 菜单点击 + 剪贴板"; split_ghostty "$DIRECTION" "$COMMAND" ;;
  zed)          echo "Zed — 菜单点击 + 剪贴板"; split_zed "$DIRECTION" "$COMMAND" ;;
  terminal_app) echo "Terminal.app — 新标签页 (不支持分屏)"; split_terminal_app "$DIRECTION" "$COMMAND" ;;
  *)
    echo "未检测到支持的终端 (iTerm2/Kitty/WezTerm/Warp/Ghostty/Zed/Terminal.app)" >&2
    echo "当前 TERM_PROGRAM=${TERM_PROGRAM:-未设置}" >&2
    echo "可设置 TERMINAL_OVERRIDE=iterm2|kitty|wezterm|warp|ghostty|zed|terminal_app 强制指定" >&2
    exit 1
    ;;
esac
