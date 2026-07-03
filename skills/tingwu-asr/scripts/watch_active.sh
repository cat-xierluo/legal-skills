#!/usr/bin/env bash
# watch_active.sh — 高频轮询单任务并写入状态日志
#
# 用法: ./watch_active.sh <task_id> [--interval N] [--timeout N] [--no-notify]
#
# 行为:
#   - 每 --interval 秒调一次 poll_tasks.py --once --task-id <id>
#   - 状态变化才追加日志（避免重复刷屏）
#   - 完成/失败时退出；可选弹 macOS 原生通知
#
# 输出:
#   - config/task_<id>.log  持久化状态日志（可 tail -f）

set -euo pipefail

TASK_ID="${1:?用法: $0 <task_id> [--interval N] [--timeout N] [--no-notify]}"
INTERVAL=15
TIMEOUT=3600
NOTIFY=1

shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval) INTERVAL="$2"; shift 2;;
    --timeout)  TIMEOUT="$2"; shift 2;;
    --no-notify) NOTIFY=0; shift;;
    *) echo "忽略未知参数: $1"; shift;;
  esac
done

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SKILL_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
LOG_DIR="$SKILL_ROOT/config"
LOG_FILE="$LOG_DIR/task_${TASK_ID}.log"
mkdir -p "$LOG_DIR"

START=$(date +%s)
LAST_STATUS=""
HAS_SEEN_STATUS=0  # 是否曾经看到过该任务的状态（用于区分"未提交"和"已完成"）

log() {
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "[$ts] $*" | tee -a "$LOG_FILE"
}

log "▶ watcher 启动"
log "  task_id  : $TASK_ID"
log "  interval : ${INTERVAL}s"
log "  timeout  : ${TIMEOUT}s"
log "  日志文件 : $LOG_FILE"

while true; do
  NOW=$(date +%s)
  ELAPSED=$((NOW - START))
  if [[ $ELAPSED -ge $TIMEOUT ]]; then
    log "⏱  超时退出 (已等待 ${ELAPSED}s)"
    exit 1
  fi

  # 调用 poll_tasks.py --once，捕获所有输出
  OUTPUT="$(python3 "$SCRIPT_DIR/poll_tasks.py" --once --task-id "$TASK_ID" 2>&1)" || OUTPUT="(脚本异常退出)"

  # 取第一个方括号开头的状态行：[trans_id] xxx
  STATUS_LINE="$(echo "$OUTPUT" | grep -E '^\[' | head -1 || true)"

  if [[ -n "$STATUS_LINE" ]]; then
    HAS_SEEN_STATUS=1
    if [[ "$STATUS_LINE" != "$LAST_STATUS" ]]; then
      log "  $STATUS_LINE"
      LAST_STATUS="$STATUS_LINE"
    fi
  else
    # 没拿到状态行：可能是 pending 列表空（任务从未提交 / 已完成 / 尚未写入）
    if [[ $HAS_SEEN_STATUS -eq 0 ]]; then
      # 从未见过状态：可能是 watcher 启动早于 submit 写文件，耐心等待
      log "  ⏳ 等待任务进入 pending 列表... (${ELAPSED}s)"
    else
      # 曾经见过状态，现在空了 → 任务已被其他进程处理完
      log "  📭 pending 列表已清空（任务可能已完成）"
    fi
  fi

  # 完成信号 1：finish_task 跑了（status 0/3 → 进入生成输出阶段）
  if echo "$OUTPUT" | grep -qE '正在生成输出'; then
    log "✅ 任务已完成，开始生成输出文件..."
    FINAL_OUTPUT="$(python3 "$SCRIPT_DIR/poll_tasks.py" --once --task-id "$TASK_ID" 2>&1 || true)"
    log "  最终输出: $(echo "$FINAL_OUTPUT" | grep -E '转录完成|AI 总结' | head -3 | tr '\n' ' ')"
    if [[ $NOTIFY -eq 1 ]] && command -v osascript >/dev/null 2>&1; then
      osascript -e "display notification \"任务 ${TASK_ID:0:12}… 已完成\" with title \"通义听悟\" subtitle \"转录完成\"" 2>/dev/null || true
    fi
    log "✅ watcher 退出"
    exit 0
  fi

  # 完成信号 2：之前见过状态，现在 pending 列表已清空（被 archived 或 finish_task 走过）
  if [[ $HAS_SEEN_STATUS -eq 1 ]] && echo "$OUTPUT" | grep -qE '无待处理任务'; then
    log "✅ 任务已从 pending 移除，watcher 退出"
    exit 0
  fi

  # 失败信号
  if echo "$OUTPUT" | grep -qE '失败:'; then
    log "❌ 任务失败，退出"
    if [[ $NOTIFY -eq 1 ]] && command -v osascript >/dev/null 2>&1; then
      osascript -e "display notification \"任务 ${TASK_ID:0:12}… 转录失败\" with title \"通义听悟\"" 2>/dev/null || true
    fi
    exit 2
  fi

  sleep "$INTERVAL"
done