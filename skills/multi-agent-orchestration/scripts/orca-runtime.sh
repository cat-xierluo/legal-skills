#!/usr/bin/env bash
# Shared Orca CLI resolution and runtime detection helpers.
# Source this file; do not execute it directly.

ORCA_CLI_BIN="${ORCA_CLI_BIN:-}"

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

# Detect whether PROJECT_DIR is the current Orca-managed worktree. This is the
# source of truth; TERM_PROGRAM and ORCA_WORKTREE_ID are optional hints only.
# On success it fills ORCA_CURRENT_WORKTREE_JSON/ID/PATH.
# On failure the reason is exposed in ORCA_WORKTREE_CURRENT_ERROR:
#   selector_not_found — Orca 返回了该结构化错误码：仓库未注册（2026-09-01 custom-skills
#                        实测事故形态，唯一允许 orca_runtime_register_current_project
#                        自动修复的情况）
#   path_mismatch      — worktree current 命中了别的仓/路径
#   ""                 — 非 Git / runtime 不可达 / 输出不可解析（禁止据此注册）
orca_runtime_current_project() {
  local project_dir="$1"
  local project_top current_json current_path current_id probe_rc

  ORCA_WORKTREE_CURRENT_ERROR=""

  project_top=$(git -C "$project_dir" rev-parse --show-toplevel 2>/dev/null) || return 1
  # worktree current is cwd-scoped; ask from the project top even when the PM
  # invokes spawn-worker from another directory.
  current_json=""
  probe_rc=0
  current_json=$(cd "$project_top" && orca_cli worktree current --json 2>/dev/null) || probe_rc=$?
  current_path=$(printf '%s' "$current_json" | jq -r '.result.worktree.path // empty' 2>/dev/null)
  current_id=$(printf '%s' "$current_json" | jq -r '.result.worktree.id // empty' 2>/dev/null)
  if [ "$probe_rc" -eq 0 ] && [ -n "$current_path" ] && [ -n "$current_id" ]; then
    if [ "$current_path" = "$project_top" ]; then
      ORCA_CURRENT_WORKTREE_JSON="$current_json"
      ORCA_CURRENT_WORKTREE_ID="$current_id"
      ORCA_CURRENT_WORKTREE_PATH="$current_path"
      return 0
    fi
    ORCA_WORKTREE_CURRENT_ERROR="path_mismatch"
    return 1
  fi
  # CLI 非零退出时 stdout 仍可能是合法错误合同（如 {ok:false,error:{code:...}}），
  # 继续解析结构化错误码供调用方区分。
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
# repo add 失败、返回合同非 ok、或注册后 orca_runtime_current_project 复验不精确
# 返回该 toplevel + repo 身份，都返回 1，由调用方回退 tmux，绝不假装 Orca 管理成功。
#
# 授权边界（references/13 §3）：仅 Orca-first worker 路径（detect_orca_mode）调用，
# 只授权把「当前这一个 Git 仓库」注册进 Orca；不授权移动/克隆/删除仓库或改动其他
# Orca 项目。--no-orca-mode 在更早处 return，永不注册；已注册仓库 worktree current
# 直接成功，也永不进入本 helper。
orca_runtime_register_current_project() {
  local project_dir="$1"
  local project_top add_out

  [ "${ORCA_WORKTREE_CURRENT_ERROR:-}" = "selector_not_found" ] || return 1

  project_top=$(git -C "$project_dir" rev-parse --show-toplevel 2>/dev/null) || return 1

  if [ "${DRY_RUN:-0}" -eq 1 ]; then
    # dry-run 不做 mutation；没有注册就无法复验身份，只能 fail-closed 回退 tmux。
    printf 'ORCA_RUN: orca repo add --path %q --json\n' "$project_top" >&2
    return 1
  fi

  orca_cli status --json >/dev/null 2>&1 || {
    echo "SPAWN_WORKER_ORCA_AUTO_REGISTER_SKIPPED: worktree current=selector_not_found 但 orca status 不可达，跳过自动注册（回退 tmux）" >&2
    return 1
  }

  echo "SPAWN_WORKER_ORCA_AUTO_REGISTER: 仓库未注册 Orca，注册当前 Git toplevel: $project_top" >&2
  add_out=$(orca_cli repo add --path "$project_top" --json 2>&1) || {
    echo "ERROR: orca repo add 失败，不进入 Orca 模式（回退 tmux）: $add_out" >&2
    return 1
  }
  printf '%s' "$add_out" | jq -e '(.ok // true) != false' >/dev/null 2>&1 || {
    echo "ERROR: orca repo add 返回非 ok 合同，不进入 Orca 模式（回退 tmux）: $add_out" >&2
    return 1
  }

  orca_runtime_current_project "$project_dir" || {
    echo "ERROR: repo add 后 worktree current 复验失败（error=${ORCA_WORKTREE_CURRENT_ERROR:-unknown}），不进入 Orca 模式（回退 tmux；请人工核对 Orca repo 注册状态）" >&2
    return 1
  }
  return 0
}
