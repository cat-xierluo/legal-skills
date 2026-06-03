#!/bin/bash
# pm-monitor.sh — PM Monitor v4（Agent Teams inbox 通信 + Git SHA 轮询双维度）
#
# 用法:
#   pm-monitor.sh --project /path/to/repo --team-dir ~/.claude/teams/{name} \
#     [--tasks-dir ~/.claude/tasks/{uuid}] \
#     [--claude-agents-cwd /path/to/repo] \
#     [--interval 30] [--stale-threshold 300] [--once] [--log-file /path/to/events.log] \
#     --branch feat/X:session-1 [--branch feat/Y:session-2] ...
#
# 在 Claude Code 的 Monitor 工具中启动，或直接在终端运行。
# 默认 30s 间隔轮询，输出事件行；--once 只巡检一次，适合 PM 低成本按需读取。
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
#   CHECKPOINT_STATUS session status phase progress
#     worker 写入 .claude/agent-sessions/{session}/STATUS.json
#   CHECKPOINT_STALE session Ns path
#     STATUS.json 的 updated_at 超过阈值未刷新
#   AGENT_NEEDS_INPUT session reason
#     STATUS.json 报告 needs_input 或 pm_action_required
#   CHECKPOINT_TEST_FAILURE session tests
#     STATUS.json 中有失败测试
#   CHECKPOINT_RESULT session path
#     worker 写入 .claude/agent-sessions/{session}/RESULT.md
#   CHECKPOINT_PATCH session path
#     worker 写入 .claude/agent-sessions/{session}/PATCH_SUMMARY.md
#   CLAUDE_AGENT_STATE name/session status kind cwd
#     Claude Code 官方后台 session 状态变化（来自 claude agents --json）
#   SESSION_GONE session-name (branch branch-name)
#     tmux session 已退出
#   PM_MONITOR_COMPLETE: all branches merged at <timestamp>
#     全部分支已合并

set -euo pipefail

# ========== 参数解析 ==========
PROJECT_DIR=""
TEAM_DIR=""
TASKS_DIR=""
CLAUDE_AGENTS_CWD=""
INTERVAL=30
ONCE=0
LOG_FILE=""
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
    --claude-agents-cwd)
      CLAUDE_AGENTS_CWD="$2"
      shift 2
      ;;
    --interval)
      INTERVAL="$2"
      shift 2
      ;;
    --stale-threshold)
      STALE_THRESHOLD="$2"
      shift 2
      ;;
    --once)
      ONCE=1
      shift
      ;;
    --log-file)
      LOG_FILE="$2"
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
      echo "用法: pm-monitor.sh --project /path/to/repo [--team-dir ~/.claude/teams/{name}] [--once] [--interval 30] [--log-file /path/to/events.log] --branch feat/X:session-1" >&2
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

[ -n "$LOG_FILE" ] && mkdir -p "$(dirname "$LOG_FILE")"

# ========== 状态缓存 ==========
declare -A last_sha
declare -A last_pr_state
declare -A last_agent_status
declare -A last_health_ts
declare -A last_checkpoint_status
declare -A last_checkpoint_stale
declare -A last_checkpoint_result_mtime
declare -A last_checkpoint_patch_mtime
declare -A last_claude_agent_status

# ========== 辅助函数 ==========

emit() {
  local line="$*"
  echo "$line"
  if [ -n "$LOG_FILE" ]; then
    printf '%s\n' "$line" >> "$LOG_FILE"
  fi
}

parse_iso_epoch() {
  local ts="$1"
  [ -z "$ts" ] && { echo "0"; return; }

  local ts_clean
  ts_clean=$(echo "$ts" | sed 's/[+-][0-9][0-9]:..$//' | sed 's/Z$//' | sed 's/\..*$//')
  date -j -f "%Y-%m-%dT%H:%M:%S" "$ts_clean" "+%s" 2>/dev/null \
    || date -d "$ts" "+%s" 2>/dev/null \
    || echo "0"
}

worktree_for_branch() {
  local branch="$1"
  git worktree list --porcelain 2>/dev/null | awk -v target="refs/heads/$branch" '
    /^worktree / { wt = substr($0, 10) }
    /^branch / {
      if (substr($0, 8) == target) {
        print wt
        exit
      }
    }
  '
}

checkpoint_dir_for_session() {
  local wt="$1"
  local session="$2"
  local preferred="$wt/.claude/agent-sessions/$session"
  local legacy="$wt/.agent-context"

  if [ -d "$preferred" ] || [ ! -d "$legacy" ]; then
    echo "$preferred"
  else
    echo "$legacy"
  fi
}

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
      emit "AGENT_HEALTH: $session $status $phase $progress"

      # 特殊状态
      case "$status" in
        done)   emit "AGENT_DONE: $session" ;;
        failed) emit "AGENT_FAILED: $session" ;;
        blocked) emit "AGENT_BLOCKED: $session ($issues)" ;;
      esac
    fi

    # 过时检测
    if [ -n "$ts" ] && [ "$status" != "done" ]; then
      local cur_epoch
      cur_epoch=$(parse_iso_epoch "$ts")
      if [ "$cur_epoch" -gt 0 ]; then
        local stale=$(( $(date +%s) - cur_epoch ))
        if [ "$stale" -gt "$STALE_THRESHOLD" ]; then
          emit "AGENT_STALE: $session (${stale}s since last health_report)"
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
      emit "TASK_STATUS: #$task_id $task_status ($task_subject)"
    fi

    # 任务完成 → 自动删除 JSON + 更新 highwatermark
    if [ "$task_status" = "completed" ] && [ "$prev_ts" != "completed" ]; then
      emit "TASK_COMPLETED: #$task_id ($task_subject) — cleaning up"
      rm -f "$task_file"
      echo "$task_id" > "$TASKS_DIR/.highwatermark"
    fi

    last_task_status[$task_id]="$task_status"
  done
}

# 检查 worker checkpoint 文件状态变化
check_file_checkpoints() {
  for branch in "${!BRANCHES[@]}"; do
    local session="${BRANCHES[$branch]}"
    local wt
    wt=$(worktree_for_branch "$branch")
    [ -n "$wt" ] || continue

    local checkpoint_dir
    checkpoint_dir=$(checkpoint_dir_for_session "$wt" "$session")
    local status_file="$checkpoint_dir/STATUS.json"
    local result_file="$checkpoint_dir/RESULT.md"
    local patch_file="$checkpoint_dir/PATCH_SUMMARY.md"

    if [ -f "$status_file" ]; then
      local status phase progress issues updated_at needs_input pm_action_required key prev
      local task_id current_action next_action last_commit_sha pr_url failed_tests test_summary heartbeat threshold stale_key
      status=$(jq -r '.status // empty' "$status_file" 2>/dev/null || echo "")
      phase=$(jq -r '.phase // empty' "$status_file" 2>/dev/null || echo "")
      progress=$(jq -r '.progress // empty' "$status_file" 2>/dev/null || echo "")
      issues=$(jq -r '.issues // [] | if length > 0 then join(", ") else "" end' "$status_file" 2>/dev/null || echo "")
      updated_at=$(jq -r '.updated_at // empty' "$status_file" 2>/dev/null || echo "")
      needs_input=$(jq -r '.needs_input // false' "$status_file" 2>/dev/null || echo "false")
      pm_action_required=$(jq -r '.pm_action_required // false' "$status_file" 2>/dev/null || echo "false")
      task_id=$(jq -r '.task_source.id // .task_source // empty' "$status_file" 2>/dev/null || echo "")
      current_action=$(jq -r '.current_action // empty' "$status_file" 2>/dev/null || echo "")
      next_action=$(jq -r '.next_action // empty' "$status_file" 2>/dev/null || echo "")
      last_commit_sha=$(jq -r '.git.last_commit_sha // .last_commit_sha // empty' "$status_file" 2>/dev/null || echo "")
      pr_url=$(jq -r '.git.pr_url // .pr_url // empty' "$status_file" 2>/dev/null || echo "")
      test_summary=$(jq -r '[.tests[]? | "\(.command):\(.status)"] | join(", ")' "$status_file" 2>/dev/null || echo "")
      failed_tests=$(jq -r '[.tests[]? | select((.status // "") | test("fail|failed|error"; "i")) | .command] | join(", ")' "$status_file" 2>/dev/null || echo "")
      [ -n "$status" ] || continue

      key="$status|$phase|$progress|$issues|$needs_input|$pm_action_required|$current_action|$next_action|$last_commit_sha|$pr_url|$test_summary"
      prev="${last_checkpoint_status[$session]:-}"
      if [ "$key" != "$prev" ]; then
        emit "CHECKPOINT_STATUS: $session $status $phase $progress task=${task_id:-n/a} action=${current_action:-n/a} next=${next_action:-n/a} commit=${last_commit_sha:-n/a}"
        case "$status" in
          done)    emit "AGENT_DONE: $session" ;;
          failed)  emit "AGENT_FAILED: $session" ;;
          blocked) emit "AGENT_BLOCKED: $session ($issues)" ;;
        esac
        if [ "$needs_input" = "true" ] || [ "$pm_action_required" = "true" ]; then
          emit "AGENT_NEEDS_INPUT: $session ${issues:-check STATUS.json}"
        fi
        if [ -n "$failed_tests" ]; then
          emit "CHECKPOINT_TEST_FAILURE: $session $failed_tests"
        fi
        if [ -n "$pr_url" ]; then
          emit "CHECKPOINT_PR: $session $pr_url"
        fi
      fi
      last_checkpoint_status[$session]="$key"

      if [ -n "$updated_at" ] && [ "$status" != "done" ]; then
        local cur_epoch
        cur_epoch=$(parse_iso_epoch "$updated_at")
        if [ "$cur_epoch" -gt 0 ]; then
          local stale=$(( $(date +%s) - cur_epoch ))
          heartbeat=$(jq -r '.heartbeat_interval_seconds // empty' "$status_file" 2>/dev/null || echo "")
          threshold="$STALE_THRESHOLD"
          if [[ "$heartbeat" =~ ^[0-9]+$ ]] && [ "$heartbeat" -gt "$threshold" ]; then
            threshold="$heartbeat"
          fi
          if [ "$stale" -gt "$threshold" ]; then
            stale_key="$updated_at|$(( stale / threshold ))"
            if [ "$stale_key" != "${last_checkpoint_stale[$session]:-}" ]; then
              emit "CHECKPOINT_STALE: $session ${stale}s $status_file"
            fi
            last_checkpoint_stale[$session]="$stale_key"
          fi
        fi
      fi
    fi

    if [ -f "$result_file" ]; then
      local mtime prev_mtime
      mtime=$(stat -f "%m" "$result_file" 2>/dev/null || stat -c "%Y" "$result_file" 2>/dev/null || echo "")
      prev_mtime="${last_checkpoint_result_mtime[$session]:-}"
      if [ -n "$mtime" ] && [ "$mtime" != "$prev_mtime" ]; then
        emit "CHECKPOINT_RESULT: $session $result_file"
      fi
      last_checkpoint_result_mtime[$session]="$mtime"
    fi

    if [ -f "$patch_file" ]; then
      local mtime prev_mtime
      mtime=$(stat -f "%m" "$patch_file" 2>/dev/null || stat -c "%Y" "$patch_file" 2>/dev/null || echo "")
      prev_mtime="${last_checkpoint_patch_mtime[$session]:-}"
      if [ -n "$mtime" ] && [ "$mtime" != "$prev_mtime" ]; then
        emit "CHECKPOINT_PATCH: $session $patch_file"
      fi
      last_checkpoint_patch_mtime[$session]="$mtime"
    fi
  done
}

# 检查 Claude Code 官方后台会话状态变化
check_claude_agents() {
  [ -z "$CLAUDE_AGENTS_CWD" ] && return
  command -v claude >/dev/null 2>&1 || return
  command -v jq >/dev/null 2>&1 || return

  local agents_json
  agents_json=$(claude agents --cwd "$CLAUDE_AGENTS_CWD" --json 2>/dev/null || echo "[]")

  while IFS= read -r row; do
    [ -n "$row" ] || continue

    local id name status kind cwd key prev
    id=$(echo "$row" | jq -r '.sessionId // (.pid | tostring) // empty' 2>/dev/null || echo "")
    [ -n "$id" ] || continue
    name=$(echo "$row" | jq -r '.name // .sessionId // (.pid | tostring) // "unknown"' 2>/dev/null || echo "unknown")
    status=$(echo "$row" | jq -r '.status // "unknown"' 2>/dev/null || echo "unknown")
    kind=$(echo "$row" | jq -r '.kind // "unknown"' 2>/dev/null || echo "unknown")
    cwd=$(echo "$row" | jq -r '.cwd // ""' 2>/dev/null || echo "")

    key="$status|$kind|$cwd|$name"
    prev="${last_claude_agent_status[$id]:-}"
    if [ "$key" != "$prev" ]; then
      emit "CLAUDE_AGENT_STATE: $name $status $kind $cwd"
    fi
    last_claude_agent_status[$id]="$key"
  done < <(echo "$agents_json" | jq -c '.[]?' 2>/dev/null)
}

# ========== 主循环 ==========
emit "PM_MONITOR_STARTED at $(date)"
emit "Tracking ${#BRANCHES[@]} branches: ${!BRANCHES[*]}"
[ -n "$TEAM_DIR" ] && emit "Team inbox: $TEAM_DIR/inboxes/"
[ -n "$CLAUDE_AGENTS_CWD" ] && emit "Claude agents cwd: $CLAUDE_AGENTS_CWD"
[ "$ONCE" -eq 1 ] && emit "Mode: once"
[ -n "$LOG_FILE" ] && emit "Log file: $LOG_FILE"

while true; do
  git fetch origin --no-tags --quiet 2>/dev/null || true

  # 维度 1: Agent Teams inbox 通信
  check_agent_health

  # 维度 1.2: worker checkpoint 文件
  check_file_checkpoints

  # 维度 1.3: Claude Code 官方后台 session
  check_claude_agents

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
        emit "BRANCH_MERGED: $branch"
        last_sha[$branch]="MERGED"
      fi
      continue
    fi

    all_merged=0
    prev="${last_sha[$branch]:-}"

    if [ -n "$prev" ] && [ "$cur_sha" != "$prev" ] && [ "$prev" != "MERGED" ]; then
      emit "NEW_COMMIT: $branch $prev -> $cur_sha"
    fi
    last_sha[$branch]=$cur_sha

    # PR 状态检测
    pr_info=$(gh pr list --head "$branch" --json number,state --jq 'if length > 0 then .[0] | "\(.number)|\(.state)" else "" end' 2>/dev/null || echo "")
    if [ -n "$pr_info" ]; then
      pr_num=$(echo "$pr_info" | cut -d'|' -f1)
      pr_state=$(echo "$pr_info" | cut -d'|' -f2)
      prev_pr="${last_pr_state[$branch]:-}"
      if [ "$pr_state" != "$prev_pr" ]; then
        emit "PR_STATE_CHANGE: #$pr_num ($branch) ${prev_pr:-NONE} -> $pr_state"
      fi
      last_pr_state[$branch]=$pr_state
    fi

    # tmux session 存活检测
    if ! tmux has-session -t "$session" 2>/dev/null; then
      emit "SESSION_GONE: $session (branch $branch)"
    fi
  done

  # 全部合并 → 自动停止
  if [ $all_merged -eq 1 ]; then
    emit "PM_MONITOR_COMPLETE: all branches merged at $(date)"
    break
  fi

  if [ "$ONCE" -eq 1 ]; then
    emit "PM_MONITOR_ONCE_COMPLETE at $(date)"
    break
  fi

  sleep "$INTERVAL"
done
