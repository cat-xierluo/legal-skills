#!/usr/bin/env bash
# Shared Orca CLI resolution and runtime detection helpers.
# Source this file; do not execute it directly.

ORCA_CLI_BIN="${ORCA_CLI_BIN:-}"
ORCA_RUNTIME_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

orca_runtime_resolve_cli() {
  local candidate=""
  if [ -n "${ORCA_CLI_COMMAND:-}" ]; then
    candidate="$ORCA_CLI_COMMAND"
  elif [ -n "${ORCA_DEV_REPO_ROOT:-}" ]; then
    candidate="orca-dev"
  elif [ "$(uname -s 2>/dev/null || true)" = "Linux" ]; then
    candidate="orca-ide"
  else
    candidate="orca"
  fi

  if [[ "$candidate" = /* ]]; then
    [ -x "$candidate" ] || {
      echo "ERROR: selected Orca CLI is not executable: $candidate" >&2
      return 64
    }
    ORCA_CLI_BIN="$candidate"
    return 0
  fi

  if command -v "$candidate" >/dev/null 2>&1; then
    ORCA_CLI_BIN=$(command -v "$candidate")
    return 0
  fi

  # Packaged macOS fallback for the same production CLI selected above.
  if [ "$candidate" = "orca" ] && [ -x "/Applications/Orca.app/Contents/Resources/bin/orca" ]; then
    ORCA_CLI_BIN="/Applications/Orca.app/Contents/Resources/bin/orca"
    return 0
  fi

  echo "ERROR: selected Orca CLI is unavailable: $candidate" >&2
  return 64
}

orca_runtime_init() {
  [ -n "$ORCA_CLI_BIN" ] && [ -x "$ORCA_CLI_BIN" ] && return 0
  orca_runtime_resolve_cli
}

orca_cli() {
  orca_runtime_init || return $?
  "$ORCA_CLI_BIN" "$@"
}

# Resolve exactly one supervised worker row inside its authoritative Run.
#
# The Orca fleet view is paginated (at most 100 rows per page), and an
# unscoped worker-list may inherit an unrelated terminal-bound Run.  Cleanup
# callers therefore must provide both lifecycle IDs and exhaust the opaque
# cursor chain before making any release/terminal/filesystem mutation.
#
# Success sets ORCA_WORKER_ROW_JSON.  Any malformed page, cursor loop, page
# budget exhaustion, missing row, duplicate Dispatch or cross-Run row fails
# closed and leaves the caller responsible for preserving all resources.
orca_runtime_worker_row_exact() {
  local dispatch_id="$1"
  local run_id="$2"
  local cursor=""
  local next_cursor=""
  local response=""
  local page_matches="[]"
  local page_match_count=0
  local total_matches=0
  local page_worker_count=0
  local page_total=0
  local observed_workers=0
  local expected_total=""
  local page_count=0
  local seen_cursor=""
  local -a worker_list_args=()
  # Bash 3.2 with `set -u` errors when expanding a truly empty array.  Keep one
  # ignored sentinel so the same helper works on the macOS system Bash.
  local -a seen_cursors=("")

  ORCA_WORKER_ROW_JSON=""
  if [ -z "$dispatch_id" ] || [ -z "$run_id" ]; then
    echo "ORCA_WORKER_LIST_REFUSED: exact dispatch and run are required" >&2
    return 2
  fi

  while [ "$page_count" -lt 100 ]; do
    worker_list_args=(orchestration worker-list --run "$run_id" --limit 100)
    if [ -n "$cursor" ]; then
      worker_list_args+=(--cursor "$cursor")
    fi
    worker_list_args+=(--json)

    if ! response=$(orca_cli "${worker_list_args[@]}" 2>/dev/null); then
      echo "ORCA_WORKER_LIST_REFUSED: worker-list read failed run=$run_id page=$page_count" >&2
      return 2
    fi
    if ! printf '%s' "$response" | jq -e --arg run "$run_id" '
      .ok == true
      and (.result | type == "object")
      and (.result.workers | type == "array")
      and (.result.workers | length <= 100)
      and (.result.scope | type == "object")
      and .result.scope.source == "flag"
      and ((.result.scope.runId // .result.scope.run_id // "") == $run)
      and all(.result.workers[]?;
        ((.dispatchId? | type) == "string")
        and (.dispatchId | length > 0)
        and ((.runId? | type) == "string")
        and (.runId == $run))
      and (.result.page | type == "object")
      and .result.page.limit == 100
      and ((.result.page.total | type == "number")
        and .result.page.total >= 0
        and .result.page.total <= 10000
        and (.result.page.total | floor) == .result.page.total)
      and (.result.page.hasMore | type == "boolean")
      and (
        if .result.page.hasMore
        then ((.result.page.nextCursor | type == "string") and (.result.page.nextCursor | length > 0))
        else ((.result.page.nextCursor? == null) or .result.page.nextCursor == "")
        end
      )
    ' >/dev/null 2>&1; then
      echo "ORCA_WORKER_LIST_REFUSED: malformed worker-list page run=$run_id page=$page_count" >&2
      return 2
    fi

    page_worker_count=$(printf '%s' "$response" | jq -r '.result.workers | length') || return 2
    observed_workers=$((observed_workers + page_worker_count))
    page_total=$(printf '%s' "$response" | jq -r '.result.page.total') || return 2
    if [ -z "$expected_total" ]; then
      expected_total="$page_total"
    elif [ "$page_total" -ne "$expected_total" ]; then
      echo "ORCA_WORKER_LIST_REFUSED: page total drift run=$run_id expected=$expected_total actual=$page_total" >&2
      return 2
    fi
    if [ "$observed_workers" -gt "$expected_total" ]; then
      echo "ORCA_WORKER_LIST_REFUSED: observed rows exceed total run=$run_id observed=$observed_workers total=$expected_total" >&2
      return 2
    fi

    page_matches=$(printf '%s' "$response" | jq -c --arg dispatch "$dispatch_id" '
      [.result.workers[]?
        | select(.dispatchId == $dispatch)]
    ' 2>/dev/null) || {
      echo "ORCA_WORKER_LIST_REFUSED: cannot parse worker rows run=$run_id page=$page_count" >&2
      return 2
    }
    page_match_count=$(printf '%s' "$page_matches" | jq -r 'length' 2>/dev/null) || return 2
    total_matches=$((total_matches + page_match_count))
    if [ "$total_matches" -gt 1 ]; then
      echo "ORCA_WORKER_LIST_REFUSED: duplicate dispatch=$dispatch_id run=$run_id" >&2
      return 2
    fi
    if [ "$page_match_count" -eq 1 ]; then
      ORCA_WORKER_ROW_JSON=$(printf '%s' "$page_matches" | jq -c '.[0]') || return 2
    fi

    next_cursor=$(printf '%s' "$response" | jq -r '
      if .result.page.hasMore == false
      then ""
      else .result.page.nextCursor
      end
    ' 2>/dev/null) || {
      echo "ORCA_WORKER_LIST_REFUSED: cannot parse next cursor run=$run_id page=$page_count" >&2
      return 2
    }
    if [ -z "$next_cursor" ]; then
      if [ "$observed_workers" -ne "$expected_total" ]; then
        echo "ORCA_WORKER_LIST_REFUSED: terminal page does not exhaust total run=$run_id observed=$observed_workers total=$expected_total" >&2
        return 2
      fi
      break
    fi
    if [ "$observed_workers" -ge "$expected_total" ]; then
      echo "ORCA_WORKER_LIST_REFUSED: hasMore contradicts total run=$run_id observed=$observed_workers total=$expected_total" >&2
      return 2
    fi
    for seen_cursor in "${seen_cursors[@]}"; do
      [ -n "$seen_cursor" ] || continue
      if [ "$seen_cursor" = "$next_cursor" ]; then
        echo "ORCA_WORKER_LIST_REFUSED: cursor loop run=$run_id cursor=$next_cursor" >&2
        return 2
      fi
    done
    seen_cursors+=("$next_cursor")
    cursor="$next_cursor"
    page_count=$((page_count + 1))
  done

  if [ -n "$next_cursor" ] && [ "$page_count" -ge 100 ]; then
    echo "ORCA_WORKER_LIST_REFUSED: page budget exceeded run=$run_id" >&2
    return 2
  fi
  if [ "$total_matches" -ne 1 ] || [ -z "$ORCA_WORKER_ROW_JSON" ]; then
    echo "ORCA_WORKER_LIST_REFUSED: dispatch=$dispatch_id not found exactly once in run=$run_id" >&2
    return 2
  fi
}

# runtimeId binds a receipt to one runtime, not to a live coordinator terminal.
# A matching id cannot prove handle liveness; worker-start still owns fencing.
orca_runtime_current_runtime_id() {
  local status_json
  ORCA_RUNTIME_ID_NOW=""
  status_json=$(orca_cli status --json 2>/dev/null) || return 1
  ORCA_RUNTIME_ID_NOW=$(printf '%s' "$status_json" | jq -er '
    select(.ok == true and .result.runtime.reachable == true)
    | .result.runtime.runtimeId
    | select(type == "string" and length > 0 and . != "none")
  ' 2>/dev/null) || { ORCA_RUNTIME_ID_NOW=""; return 1; }
}

orca_runtime_require_identity() {
  local expected="$1"
  if [ -z "$expected" ]; then
    echo "SPAWN_COORDINATOR_RUNTIME_UNVERIFIED: legacy handle has no runtime identity; runtime drift is not checked. Re-prepare a receipt and pass its _meta.runtimeId." >&2
    return 0
  fi
  if ! orca_runtime_current_runtime_id; then
    echo "SPAWN_COORDINATOR_RUNTIME_UNVERIFIED: current runtime identity is unavailable; refusing dispatch." >&2
    return 3
  fi
  if [ "$expected" != "$ORCA_RUNTIME_ID_NOW" ]; then
    echo "SPAWN_COORDINATOR_STALE: receipt runtime differs from the current runtime; refusing dispatch. Inspect the existing Run/Tasks and rebind the coordinator on the current runtime; do not blindly recreate Tasks." >&2
    return 3
  fi
}

# Detect whether PROJECT_DIR is the current Orca-managed worktree. This is the
# source of truth; TERM_PROGRAM and ORCA_WORKTREE_ID are optional hints only.
# On success it fills ORCA_CURRENT_WORKTREE_JSON/ID/PATH.
# On failure the reason is exposed in ORCA_WORKTREE_CURRENT_ERROR:
#   selector_not_found — Orca 返回了该结构化错误码：仓库未注册（2026-09-01 custom-skills
#                        实测事故形态，唯一允许 orca_runtime_register_current_project
#                        自动修复的情况）
#   path_mismatch      — worktree current 命中了别的仓/路径
#   其他错误或空值       — 非 Git / runtime 不可达 / 身份或 pending 状态未知，禁止注册
orca_runtime_accept_current_project() {
  local project_top="$1" current_json="$2"
  local current_path current_id
  ORCA_WORKTREE_CURRENT_ERROR=""
  printf '%s' "$current_json" | jq -e '.ok == true' >/dev/null 2>&1 || return 1
  current_path=$(printf '%s' "$current_json" | jq -r '.result.worktree.path // empty' 2>/dev/null)
  current_id=$(printf '%s' "$current_json" | jq -r '.result.worktree.id // empty' 2>/dev/null)
  if [ -n "$current_path" ] && [ -n "$current_id" ]; then
    if [ "$current_path" = "$project_top" ] && [[ "$current_id" == *::"$project_top" ]] && [ -n "${current_id%%::*}" ]; then
      ORCA_CURRENT_WORKTREE_JSON="$current_json"
      ORCA_CURRENT_WORKTREE_ID="$current_id"
      ORCA_CURRENT_WORKTREE_PATH="$current_path"
      return 0
    fi
    ORCA_WORKTREE_CURRENT_ERROR="path_mismatch"
    return 1
  fi
  return 1
}

orca_runtime_current_project() {
  local project_dir="$1" project_top current_json probe_rc=0
  ORCA_WORKTREE_CURRENT_ERROR=""
  project_top=$(git -C "$project_dir" rev-parse --show-toplevel 2>/dev/null) || return 1
  project_top=$(cd "$project_top" && pwd -P) || return 1
  orca_runtime_init || return 1
  # The Python argv-only adapter bounds each CLI call and requires explicit
  # success/error contracts. It creates no lock or registration in probe mode.
  current_json=$(python3 "$ORCA_RUNTIME_SCRIPT_DIR/orca-register-project.py" \
    --project "$project_top" --orca-cli "$ORCA_CLI_BIN" --probe-only 2>/dev/null) || probe_rc=$?
  if [ "$probe_rc" -eq 0 ]; then
    orca_runtime_accept_current_project "$project_top" "$current_json"
    return $?
  fi
  ORCA_WORKTREE_CURRENT_ERROR=$(printf '%s' "$current_json" | jq -r '.error.code // empty' 2>/dev/null)
  return 1
}

# 2026-09-01 实测事故：仓库是有效 Git 仓、Orca runtime 健康，但 repo 未注册时，
# `orca worktree current --json` 只返回 {ok:false,error:{code:"selector_not_found"}}，
# Orca 模式被静默降级为 tmux；`orca repo add --path <git toplevel> --json` 注册后
# worktree current 立即返回精确主 worktree。
#
# 本 helper 只在以下条件全部成立时执行一次注册（fail-closed）：
#   1. ORCA_WORKTREE_CURRENT_ERROR 精确等于 selector_not_found（path_mismatch、
#      runtime 不可达、非 Git、其他错误码一律不注册）；
#   2. PROJECT_DIR 仍是可解析的 Git 仓，注册目标锁定为唯一 canonical toplevel；
#   3. `orca status --json` 可达（runtime 不可用时不做 mutation；版本/capability
#      兼容性由 detect_orca_mode 的 status 预检兜底，不兼容会 missing_orca 失败关闭，
#      早于任何 branch/worktree/provider 副作用）。
# repo add 失败、返回合同非 ok、或注册后 worktree current 复验不精确
# 返回该 toplevel + repo 身份，都返回 1，由调用方回退 tmux，绝不假装 Orca 管理成功。
# Git common-dir 下的普通锁文件保留 pending；副作用前 fsync，结果未知不得重复
# add。只有同项目的精确身份（已收到 repo.id 时还须一致）才可解除该 pending。
#
# 授权边界（references/13 §3）：仅 Orca-first worker 路径（detect_orca_mode）调用，
# 只授权把「当前这一个 Git 仓库」注册进 Orca；不授权移动/克隆/删除仓库或改动其他
# Orca 项目。--no-orca-mode 在更早处 return，永不注册；已注册仓库 worktree current
# 直接成功，也永不进入本 helper。
orca_runtime_register_current_project() {
  local project_dir="$1"
  local project_top registered_json

  [ "${ORCA_WORKTREE_CURRENT_ERROR:-}" = "selector_not_found" ] || return 1

  project_top=$(git -C "$project_dir" rev-parse --show-toplevel 2>/dev/null) || return 1
  project_top=$(cd "$project_top" && pwd -P) || return 1

  if [ "${DRY_RUN:-0}" -eq 1 ]; then
    # dry-run 不做 mutation；没有注册就无法复验身份，只能 fail-closed 回退 tmux。
    printf 'ORCA_RUN: orca repo add --path %q --json\n' "$project_top" >&2
    return 1
  fi

  orca_runtime_init || return 1
  # The same common-dir flock remains held through re-probe, mutation and
  # post-add identity verification. Never run a second, unlocked repo add here.
  registered_json=$(python3 "$ORCA_RUNTIME_SCRIPT_DIR/orca-register-project.py" \
    --project "$project_top" --orca-cli "$ORCA_CLI_BIN") || {
    ORCA_WORKTREE_CURRENT_ERROR=$(printf '%s' "$registered_json" | jq -r '.error.code // empty' 2>/dev/null)
    return 1
  }
  # Hydrate the globals from the exact snapshot already verified under lock.
  orca_runtime_accept_current_project "$project_top" "$registered_json" || {
    echo "ERROR: repo add 后 worktree current 复验失败（error=${ORCA_WORKTREE_CURRENT_ERROR:-unknown}），不进入 Orca 模式（回退 tmux；请人工核对 Orca repo 注册状态）" >&2
    return 1
  }
  return 0
}
