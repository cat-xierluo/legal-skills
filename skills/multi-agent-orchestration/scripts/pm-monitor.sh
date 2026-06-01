#!/bin/bash
# pm-monitor.sh — PM Monitor v4（Agent Teams inbox 通信 + Git SHA 轮询双维度）
#
# 用法:
#   pm-monitor.sh --project /path/to/repo --team-dir ~/.claude/teams/{name} \
#     [--tasks-dir ~/.claude/tasks/{uuid}] \
#     --branch feat/X:session-1 [--branch feat/Y:session-2] ...
#
# 在 Claude Code 的 Monitor 工具中启动，或直接在终端运行。
# 30s 间隔轮询，输出事件行。
#
# 事件说明:
#   AGENT_HEALTH session status phase progress
#     Agent 通过 inbox 发送 health_report
#   AGENT_STALE session (Ns)
#     health_report 超过 5 分钟未更新
#   AGENT_BLOCKED session (reason)
#     Agent 报告阻塞
#   AGENT_DONE session
#     Agent 完成
#   AGENT_FAILED session
#     Agent 失败
#   NEW_COMMIT branch-name prev_sha -> cur_sha
#     分支有新提交
#   PR_STATE_CHANGE #pr-num (branch-name) prev_state -> cur_state
#     PR 状态变化
#   BRANCH_MERGED branch-name
#     远程分支已删除
#   SESSION_GONE session-name (branch branch-name)
#     tmux session 已退出
#   PM_MONITOR_COMPLETE: all branches merged at <timestamp>
#     全部分支已合并

set -euo pipefail

# ========== 参数解析 ==========
PROJECT_DIR=""
TEAM_DIR=""
TASKS_DIR=""
STALE_THRESHOLD=300  # 5 分钟
declare -A BRANCHES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT_DIR="$2"
      shift 2
      ;;
    --team-dir)
      TEAM_DIR="$2"
      shift 2
      ;;
    --tasks-dir)
      TASKS_DIR="$2"
      shift 2
      ;;
    --branch)
      IFS=':' read -r branch session <<< "$2"
      if [ -z "$branch" ] || [ -z "$session" ]; then
        echo "用法: --branch 分支名:session名 (例: --branch feat/dark-theme:worker-1)" >&2
        exit 1
      fi
      BRANCHES["$branch"]="$session"
      shift 2
      ;;
    *)
      echo "未知参数: $1" >&2
      echo "用法: pm-monitor.sh --project /path/to/repo [--team-dir ~/.claude/teams/{name}] --branch feat/X:session-1" >&2
      exit 1
      ;;
  esac
done

if [ -z "$PROJECT_DIR" ]; then
  echo "错误: 必须指定 --project 参数" >&2
  exit 1
fi

if [ ${#BRANCHES[@]} -eq 0 ]; then
  echo "错误: 必须指定至少一个 --branch 参数" >&2
  exit 1
fi

cd "$PROJECT_DIR" || { echo "错误: 目录不存在 $PROJECT_DIR" >&2; exit 1; }

# ========== 状态缓存 ==========
declare -A last_sha
declare -A last_pr_state
declare -A last_agent_status
declare -A last_health_ts

# ========== 辅助函数 ==========

# 从 PM inbox 中提取 health_report 消息
check_agent_health() {
  [ -z "$TEAM_DIR" ] && return

  local pm_inbox="$TEAM_DIR/inboxes/team-lead.json"
  [ ! -f "$pm_inbox" ] && return

  for branch in "${!BRANCHES[@]}"; do
    local session="${BRANCHES[$branch]}"

    # 从 PM inbox 中找最新来自该 agent 的 unread health_report
    local report
    report=$(jq -r --arg from "$session" '
      [.[] | select(.from == $from and .read == false and (.text | startswith("{\"type\":\"health_report\"")))]
      | last
      | if . then .text else "" end
    ' "$pm_inbox" 2>/dev/null || echo "")

    [ -z "$report" ] && continue

    # 解析 health_report
    local status phase progress sha issues ts
    status=$(echo "$report" | jq -r '.status // empty' 2>/dev/null || echo "")
    phase=$(echo "$report" | jq -r '.phase // empty' 2>/dev/null || echo "")
    progress=$(echo "$report" | jq -r '.progress // empty' 2>/dev/null || echo "")
    sha=$(echo "$report" | jq -r '.last_commit_sha // empty' 2>/dev/null || echo "")
    issues=$(echo "$report" | jq -r '.issues // [] | if length > 0 then join(", ") else "" end' 2>/dev/null || echo "")

    # 获取消息时间戳
    ts=$(jq -r --arg from "$session" '
      [.[] | select(.from == $from and .read == false and (.text | startswith("{\"type\":\"health_report\"")))]
      | last
      | if . then .timestamp else "" end
    ' "$pm_inbox" 2>/dev/null || echo "")

    [ -z "$status" ] && continue

    local prev="${last_agent_status[$session]:-unknown}"

    # 状态变化事件
    if [ "$status" != "$prev" ]; then
      echo "AGENT_HEALTH: $session $status $phase $progress"

      # 特殊状态
      case "$status" in
        done)   echo "AGENT_DONE: $session" ;;
        failed) echo "AGENT_FAILED: $session" ;;
        blocked) echo "AGENT_BLOCKED: $session ($issues)" ;;
      esac
    fi

    # 过时检测
    if [ -n "$ts" ] && [ "$status" != "done" ]; then
      local ts_clean
      ts_clean=$(echo "$ts" | sed 's/[+-][0-9][0-9]:..$//' | sed 's/Z$//' | sed 's/\..*$//')
      local cur_epoch
      cur_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%S" "$ts_clean" "+%s" 2>/dev/null || echo "0")
      if [ "$cur_epoch" -gt 0 ]; then
        local stale=$(( $(date +%s) - cur_epoch ))
        if [ "$stale" -gt "$STALE_THRESHOLD" ]; then
          echo "AGENT_STALE: $session (${stale}s since last health_report)"
        fi
        last_health_ts[$session]=$cur_epoch
      fi
    fi

    last_agent_status[$session]="$status"
  done
}

# 检查任务列表状态变化
declare -A last_task_status
check_task_states() {
  local hw
  hw=$(cat "$TASKS_DIR/.highwatermark" 2>/dev/null || echo "0")

  for task_file in "$TASKS_DIR"/*.json; do
    [ -f "$task_file" ] || continue

    local task_id task_status task_subject prev_ts
    task_id=$(jq -r '.id' "$task_file" 2>/dev/null || echo "")
    task_status=$(jq -r '.status' "$task_file" 2>/dev/null || echo "")
    task_subject=$(jq -r '.subject' "$task_file" 2>/dev/null || echo "")

    [ -z "$task_id" ] && continue

    prev_ts="${last_task_status[$task_id]:-none}"

    if [ "$task_status" != "$prev_ts" ]; then
      echo "TASK_STATUS: #$task_id $task_status ($task_subject)"
    fi

    # 任务完成 → 自动删除 JSON + 更新 highwatermark
    if [ "$task_status" = "completed" ] && [ "$prev_ts" != "completed" ]; then
      echo "TASK_COMPLETED: #$task_id ($task_subject) — cleaning up"
      rm -f "$task_file"
      echo "$task_id" > "$TASKS_DIR/.highwatermark"
    fi

    last_task_status[$task_id]="$task_status"
  done
}

# ========== 主循环 ==========
echo "PM_MONITOR_STARTED at $(date)"
echo "Tracking ${#BRANCHES[@]} branches: ${!BRANCHES[*]}"
[ -n "$TEAM_DIR" ] && echo "Team inbox: $TEAM_DIR/inboxes/"

while true; do
  git fetch origin --no-tags --quiet 2>/dev/null || true

  # 维度 1: Agent Teams inbox 通信
  check_agent_health

  # 维度 1.5: 任务列表状态监控
  if [ -n "$TASKS_DIR" ] && [ -d "$TASKS_DIR" ]; then
    check_task_states
  fi

  # 维度 2: Git SHA / PR / Session 轮询
  all_merged=1

  for branch in "${!BRANCHES[@]}"; do
    session="${BRANCHES[$branch]}"

    # 检查远程分支是否还存在
    cur_sha=$(git log "origin/$branch" -1 --format="%h" 2>/dev/null || echo "")
    if [ -z "$cur_sha" ]; then
      if [ "${last_sha[$branch]:-}" != "MERGED" ]; then
        echo "BRANCH_MERGED: $branch"
        last_sha[$branch]="MERGED"
      fi
      continue
    fi

    all_merged=0
    prev="${last_sha[$branch]:-}"

    if [ -n "$prev" ] && [ "$cur_sha" != "$prev" ] && [ "$prev" != "MERGED" ]; then
      echo "NEW_COMMIT: $branch $prev -> $cur_sha"
    fi
    last_sha[$branch]=$cur_sha

    # PR 状态检测
    pr_info=$(gh pr list --head "$branch" --json number,state --jq '.[0] | "\(.number)|\(.state)"' 2>/dev/null || echo "")
    if [ -n "$pr_info" ]; then
      pr_num=$(echo "$pr_info" | cut -d'|' -f1)
      pr_state=$(echo "$pr_info" | cut -d'|' -f2)
      prev_pr="${last_pr_state[$branch]:-}"
      if [ "$pr_state" != "$prev_pr" ]; then
        echo "PR_STATE_CHANGE: #$pr_num ($branch) ${prev_pr:-NONE} -> $pr_state"
      fi
      last_pr_state[$branch]=$pr_state
    fi

    # tmux session 存活检测
    if ! tmux has-session -t "$session" 2>/dev/null; then
      echo "SESSION_GONE: $session (branch $branch)"
    fi
  done

  # 全部合并 → 自动停止
  if [ $all_merged -eq 1 ]; then
    echo "PM_MONITOR_COMPLETE: all branches merged at $(date)"
    break
  fi

  sleep 30
done
