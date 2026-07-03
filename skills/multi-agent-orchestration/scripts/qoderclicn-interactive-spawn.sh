#!/usr/bin/env bash
# scripts/qoderclicn-interactive-spawn.sh — 长任务（10+ tool call）专用：交互式 REPL + tmux send-keys
#
# 用法:
#   bash scripts/qoderclicn-interactive-spawn.sh \
#     --session <tmux-session-name> \
#     --workdir <worktree-path> \
#     --prompt-file <absolute-path-to-prompt> \
#     [--model <qmodel_latest|qmodel|dmodel|dfmodel|kmodel|gm51model|q36fmodel|auto>]
#     [--trust-auto]   # 跳过 trust-folder 确认（默认会按 1 接受）
#
# 输出: 纯 session 名称（stdout），便于 caller 拿 sentinel 探针 / 后续 send-keys 用
#
# 为什么需要这个 helper（DEC-042 决策依据）：
#   - qoderclicn batch `-p` 走 SDK/bare 模式 → HeadlessSession 1-2s 内 `gemini.exitHeadlessMode`
#     主动 idle-exit，固不能跑长任务。
#   - qoderclicn 不带 -p 时是 true REPL + TTY，能跑多 tool call 不退（实测 pwd / ls -la / Read / Edit
#     等 5+ tool call 后稳定在 `>` prompt 待下一条消息）。
#   - 2026-07-03 doc-curator-iter Wave 1 W2 已验证：交互模式 + tmux send-keys 投递 prompt 是
#     长任务的 canonical pattern（ref 07 §6.2）。
#
# 限制与注意：
#   - helper 不读任务/不写 STATUS.json。Sentinel/cron 行为与 spawn-worker.sh 流程相同。
#     caller 应在外层同时起 sentinel 监听 .claude/agent-sessions/<session>/STATUS.json。
#   - helper 不动 skill 源文件 / scripts/，只创建 tmux session + 注入 prompt。
#   - spawned worker 没有 commit/push gate。caller 决定 commit 节奏。

set -euo pipefail

# --------- arg parse ----------
SESSION=""
WORKDIR=""
PROMPT_FILE=""
MODEL="qmodel_latest"
TRUST_AUTO=1   # 默认按 1 接受（短回车交互自动化）

usage() {
  cat >&2 <<'USAGE'
Usage:
  qoderclicn-interactive-spawn.sh --session NAME --workdir DIR --prompt-file FILE [--model MODEL] [--no-trust-auto]

Backstory:
  此 helper 走 interactive 模式（不传 -p），让 qoderclicn 作为真 REPL 跑；通过
  tmux send-keys 投递 prompt 文件内容，自动回复 trust-folder 确认。配合多 Agent
  编排 ref 07 §6.2 + DEC-042：长任务=交互模式（避免 batch -p SDK/bare 模式的
  HeadlessSession 1-2s idle-exit）。输出 session name 到 stdout。
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --session) SESSION="$2"; shift 2 ;;
    --workdir) WORKDIR="$2"; shift 2 ;;
    --prompt-file) PROMPT_FILE="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --no-trust-auto) TRUST_AUTO=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown arg: $1" >&2; usage; exit 64 ;;
  esac
done

[ -n "$SESSION" ] || { echo "ERROR: --session required" >&2; usage; exit 64; }
[ -n "$WORKDIR" ] || { echo "ERROR: --workdir required" >&2; usage; exit 64; }
[ -n "$PROMPT_FILE" ] || { echo "ERROR: --prompt-file required" >&2; usage; exit 64; }
[ -f "$PROMPT_FILE" ] || { echo "ERROR: prompt file not found: $PROMPT_FILE" >&2; exit 64; }
[ -d "$WORKDIR" ] || { echo "ERROR: workdir not found: $WORKDIR" >&2; exit 64; }

QODER="/Applications/QoderWork CN.app/Contents/Resources/bin/qoderclicn"
[ -x "$QODER" ] || { echo "ERROR: qoderclicn binary missing: $QODER" >&2; exit 64; }

# 不允许覆盖已有 session
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "ERROR: tmux session already exists: $SESSION" >&2
  exit 64
fi

# --------- spawn ----------
# 用 argv 形式（无字符串 wrap），让 tmux 直接 exec，避免 sh 把路径里含空格的
# "QoderWork CN.app" 当两个 arg 拆。DEC-042 验证后 fix。
tmux new-session -d -s "$SESSION" -c "$WORKDIR" \
  env -u QODER_AGENT_SDK_ENTRYPOINT \
      -u QODER_AGENT_SDK_VERSION \
      -u QODER_WORK_INTEGRATION_MODE \
      -u QODERWORK_SOURCE_CHAT_ID \
      -u QODERWORK_AWARENESS_SINK \
      -u QODERWORK_AWARENESS_SINK_MEMORY \
      "$QODER" \
      -m "$MODEL" \
      --permission-mode auto

# 等待 qoderclicn TUI 起来（trust prompt + 后续 ready 指示符）
# 实测经验: 干净空目录 ~3s 就出来 trust 提示；非空目录 ~5s。
wait_for_pane_match() {
  local pattern="$1"
  local timeout="${2:-60}"
  local start_ts
  start_ts=$(date +%s)
  while (( $(date +%s) - start_ts < timeout )); do
    if tmux capture-pane -t "$SESSION:0" -p 2>/dev/null | grep -qE "$pattern"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

if [[ $TRUST_AUTO -eq 1 ]]; then
  # 1) 等 trust prompt 出现
  if ! wait_for_pane_match "Do you trust the files|Trust folder|信任文件夹" 30; then
    echo "ERROR: trust prompt never appeared in session $SESSION" >&2
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    exit 1
  fi
  # 2) 选 "1. Trust folder"（默认第一项即接受）
  tmux send-keys -t "$SESSION:0" "1"
  tmux send-keys -t "$SESSION:0" Enter
fi

# 3) 等 ready 提示（"Type your message or @path/to/file"）
if ! wait_for_pane_match "Type your message|@path/to/file|> " 30; then
  echo "ERROR: ready prompt never appeared in session $SESSION" >&2
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  exit 1
fi

# --------- inject prompt ----------
# 用 tmux send-keys -l 投递 prompt 全文（literal 模式保留多行/特殊字符）
# PROMPT_FILE 可能很长，分多行发送避免 buffer overflow。
PROMPT_CONTENT="$(cat "$PROMPT_FILE")"
PROMPT_BYTES=$(printf '%s' "$PROMPT_CONTENT" | wc -c | tr -d ' ')

# 单次 send-keys 通常支持 ~8KB；prompt 超过 16KB 走 send-buffer 分段
if (( PROMPT_BYTES < 12000 )); then
  tmux send-keys -t "$SESSION:0" -l -- "$PROMPT_CONTENT"
  tmux send-keys -t "$SESSION:0" Enter
else
  # 分段：用 load-buffer / paste-buffer 把 prompt 一次性灌入 pane
  tmux load-buffer -t "$SESSION" < "$PROMPT_FILE"
  tmux paste-buffer -t "$SESSION:0"
  tmux send-keys -t "$SESSION:0" Enter
fi

# 4) 等 worker 开始吃 prompt（看到 thinking 或 tool_use 输出）
if ! wait_for_pane_match "Thinking|tool_use|Reading|Reading|assistant|Okay, let me" 60; then
  echo "WARN: worker hasn't started processing after 60s. Check tmux attach -t $SESSION." >&2
fi

# --------- exit ----------
echo "$SESSION"
