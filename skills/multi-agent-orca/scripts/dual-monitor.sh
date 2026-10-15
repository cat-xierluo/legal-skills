#!/bin/bash
# dual-monitor.sh — 双信号 worker 完成检测（PM Monitor 双维度精简版）
# 信号 1（primary）：STATUS.json 进入 done/failed/blocked/stopped
# 信号 2（silent_done 兜底）：worker 分支出现新 commit（超出 base）+ tmux pane 回到提示符（idle）
# 任一信号命中即退出 → harness task-notification 唤醒 PM。
# 用法：dual-monitor.sh <worktree> <session> <status_file> <base_sha> [poll_interval]
set -u
WT="$1"; SESS="$2"; STATUS="$3"; BASE="${4:-}"; INTERVAL="${5:-20}"
# 把 base 解析成完整 SHA，避免短 SHA vs 完整 SHA 的字符串误判（false silent_done）
[ -n "$BASE" ] && BASE="$(git -C "$WT" rev-parse "$BASE" 2>/dev/null || echo "$BASE")"
for i in "$WT" "$SESS" "$STATUS"; do :; done
while true; do
  # 信号 1：STATUS 终态
  if [ -f "$STATUS" ] && jq -e '.status | test("done|failed|blocked|stopped")' "$STATUS" >/dev/null 2>&1; then
    echo "DUAL_MONITOR_TERMINAL via STATUS ($(jq -r .status "$STATUS" 2>/dev/null))"
    break
  fi
  # 信号 2：silent_done = 新 commit + pane idle
  CUR="$(git -C "$WT" rev-parse HEAD 2>/dev/null || true)"
  if [ -n "$CUR" ] && [ "$CUR" != "$BASE" ] && [ -n "$BASE" ]; then
    PANE="$(tmux capture-pane -p -t "$SESS" 2>/dev/null | tail -4 || true)"
    # claude REPL 回到提示符（❯ / $ / ❯ 后空白）= idle；或 session 已不在
    if echo "$PANE" | grep -qE '❯[[:space:]]*$|^[[:space:]]*\$[[:space:]]*$|bypass permissions on'; then
      echo "DUAL_MONITOR_TERMINAL via silent_done (new commit $CUR + pane idle)"
      break
    fi
    ! tmux has-session -t "$SESS" 2>/dev/null && { echo "DUAL_MONITOR_TERMINAL via silent_done (new commit $CUR + session gone)"; break; }
  fi
  sleep "$INTERVAL"
done
echo "worktree=$WT session=$SESS base=$BASE cur=${CUR:-?}"
