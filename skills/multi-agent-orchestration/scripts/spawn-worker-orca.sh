#!/usr/bin/env bash
# spawn-worker-orca.sh — Orca runtime detection and terminal/worktree helpers.
# This file is sourced after spawn-worker.sh initializes globals and orca-runtime.sh.

# v2.3：Orca runtime auto-detect + terminal helper。
#
# detect_orca_mode 输出 4 选 1：
#   auto                    — worktree current 证明 PROJECT_DIR 是当前 Orca worktree
#   force_tmux              — --no-orca-mode 显式 opt-out / 非 Orca-managed repo
#   lightweight_forces_tmux — --no-worktree 强制走 tmux（ORCA worktree 必须有 git 仓）
#   missing_orca            — 已选择 Orca 路径但 CLI/runtime 不可用（fail-loud）
#
# 命中 auto 时填充 ORCA_WORKTREE_ID / ORCA_WORKTREE_PATH / ORCA_TERMINAL_HANDLE /
# ORCA_APP_VERSION / ORCA_CAPABILITIES_JSON 全局变量，供 ORCA 分支与 METADATA 写入使用。
detect_orca_mode() {
  # 直接设全局 ORCA_MODE（不用 echo + $() 捕获），否则 ORCA_APP_VERSION /
  # ORCA_CAPABILITIES_JSON / ORCA_WORKTREE_PATH 在 $() 子 shell 赋值会丢失。
  if [ "$LIGHTWEIGHT_MODE" -eq 1 ]; then
    echo "SPAWN_WORKER_ORCA_LIGHTWEIGHT_FORCES_TMUX: --no-worktree 与 ORCA 模式互斥，走原 tmux 路径" >&2
    ORCA_MODE="force_tmux"; return 0
  fi

  if [ "$NO_ORCA_MODE" -eq 1 ]; then
    echo "SPAWN_WORKER_ORCA_FORCED_TMUX: --no-orca-mode 显式 opt-out" >&2
    ORCA_MODE="force_tmux"; return 0
  fi

  # Orca 的 worktree current RPC 才能证明当前项目属于运行中的 Orca；环境变量仅用于
  # CLI 缺失时区分“普通 shell”与“旧版 Orca session 明确要求 fail-loud”。
  if ! orca_runtime_init >/dev/null 2>&1; then
    if [ "${TERM_PROGRAM:-}" = "Orca" ] || [ -n "${ORCA_WORKTREE_ID:-}" ]; then
      echo "ERROR: Orca session hint exists but selected Orca CLI is unavailable (--no-orca-mode 可强制走 tmux)" >&2
      ORCA_MODE="missing_orca"; return 0
    fi
    ORCA_MODE="force_tmux"; return 0
  fi
  if ! orca_runtime_current_project "$PROJECT_DIR"; then
    # v2.10.3：仓库未注册（结构化 error.code=selector_not_found）时先自动
    # `orca repo add` + 复验（orca_runtime_register_current_project，fail-closed）；
    # 其余失败形态（runtime 不可达 / path_mismatch / 非 Git / 未知错误码）不注册，
    # 保持原有静默回退 tmux 行为。
    if [ "${ORCA_WORKTREE_CURRENT_ERROR:-}" = "selector_not_found" ]; then
      if ! orca_runtime_register_current_project "$PROJECT_DIR"; then
        ORCA_MODE="force_tmux"; return 0
      fi
    else
      ORCA_MODE="force_tmux"; return 0
    fi
  fi

  local project_toplevel
  project_toplevel="$ORCA_CURRENT_WORKTREE_PATH"
  ORCA_WORKTREE_ID="$ORCA_CURRENT_WORKTREE_ID"
  case "$ORCA_CURRENT_WORKTREE_ID" in
    *::*) ORCA_EXPECTED_REPO_ID="${ORCA_CURRENT_WORKTREE_ID%%::*}" ;;
    *)
      echo "ERROR: orca worktree current 返回的 worktree id 无法解析 repoId: $ORCA_CURRENT_WORKTREE_ID" >&2
      ORCA_MODE="missing_orca"; return 0
      ;;
  esac
  if [ -z "$ORCA_EXPECTED_REPO_ID" ]; then
    echo "ERROR: orca worktree current 返回空 repoId: $ORCA_CURRENT_WORKTREE_ID" >&2
    ORCA_MODE="missing_orca"; return 0
  fi
  ORCA_PROJECT_TOPLEVEL="$project_toplevel"

  local status_json
  if ! status_json=$(orca_cli status --json 2>/dev/null); then
    echo "ERROR: orca status --json 失败（ORCA app 未运行？请跑 'orca open' 或传 --no-orca-mode）" >&2
    ORCA_MODE="missing_orca"; return 0
  fi

  local app_version capabilities_json
  app_version=$(printf '%s' "$status_json" | jq -r '.result.runtime.appVersion // empty' 2>/dev/null)
  capabilities_json=$(printf '%s' "$status_json" | jq -c '.result.runtime.capabilities // []' 2>/dev/null)
  if [ -z "$app_version" ] || [ "$app_version" = "null" ]; then
    echo "ERROR: orca status --json 缺少 appVersion（ORCA CLI 版本不兼容）" >&2
    ORCA_MODE="missing_orca"; return 0
  fi

  local has_terminal_multiplex
  has_terminal_multiplex=$(printf '%s' "$capabilities_json" | jq -r 'any(. == "terminal.multiplex.v1")' 2>/dev/null)
  if [ "$has_terminal_multiplex" != "true" ]; then
    echo "ERROR: ORCA $app_version 缺少 terminal.multiplex.v1 capability（需要 ≥1.4.x）" >&2
    ORCA_MODE="missing_orca"; return 0
  fi

  # 全局变量赋值（主 shell，不丢失）
  ORCA_APP_VERSION="$app_version"
  ORCA_CAPABILITIES_JSON="$capabilities_json"
  ORCA_WORKTREE_PATH="$project_toplevel"
  echo "SPAWN_WORKER_ORCA_AUTO: orca worktree current 与 PROJECT_DIR 匹配，ORCA $app_version" >&2
  ORCA_MODE="auto"
}

# 返回 Git common-dir 的物理路径；无法证明目标属于 Git 仓时返回非零。
orca_git_common_dir() {
  local worktree_path="$1" common_dir
  common_dir=$(git -C "$worktree_path" rev-parse --git-common-dir 2>/dev/null) || return 1
  case "$common_dir" in
    /*) ;;
    *) common_dir="$worktree_path/$common_dir" ;;
  esac
  common_dir=$(cd "$common_dir" 2>/dev/null && pwd -P) || return 1
  printf '%s\n' "$common_dir"
}

# create 已产生副作用但 repo identity 校验失败时，只回滚能够精确证明归属的资源。
# worktree 始终按 runtime 返回的精确 id/path 删除；branch 仅在以下条件同时成立时删除：
#   1. created worktree 与 PROJECT_DIR 属于同一 Git common-dir；
#   2. create 前该 branch 不存在；
#   3. 删除时 branch 仍指向 create 后立即记录的同一 oid。
# 这样既能清掉本次新建 branch，也不会误删错仓中碰巧同名的预存 branch。
orca_rollback_created_worktree() {
  local worktree_id="$1" worktree_path="$2" name="$3"
  local branch_preexisting="$4" expected_common_dir="$5"
  local selector actual_common_dir="" created_branch_oid="" cleanup_ok=1

  if [ -n "$worktree_path" ] && [ -d "$worktree_path" ]; then
    actual_common_dir=$(orca_git_common_dir "$worktree_path" 2>/dev/null || true)
    if [ -n "$actual_common_dir" ]; then
      created_branch_oid=$(git --git-dir="$actual_common_dir" show-ref --hash --verify "refs/heads/$name" 2>/dev/null || true)
    fi
  fi
  if [ "$actual_common_dir" != "$expected_common_dir" ]; then
    # 错仓的同名 branch 在 create 前不可观察，不能证明归本次 spawn 所有。
    # worktree 仍精确回滚，但把整体 cleanup 标为 partial 并保留 branch。
    cleanup_ok=0
    echo "SPAWN_WORKER_ORCA_ROLLBACK_BRANCH_UNPROVEN: branch=$name oid=${created_branch_oid:-unknown} actual_common_dir=${actual_common_dir:-unknown}（拒绝误删）" >&2
  fi

  case "$worktree_id" in
    *::*) selector="id:$worktree_id" ;;
    *)
      if [ -n "$worktree_path" ]; then
        selector="path:$worktree_path"
      else
        echo "ERROR: repoId 校验失败且 runtime 未返回可精确清理的 worktree id/path；保留现场" >&2
        return 1
      fi
      ;;
  esac

  if ! orca_cli worktree rm --worktree "$selector" --force --json >&2; then
    echo "ERROR: repoId 校验失败后的 Orca worktree 回滚失败，资源保留: selector=$selector" >&2
    return 1
  fi

  if [ "$branch_preexisting" -eq 0 ] \
     && [ -n "$expected_common_dir" ] \
     && [ "$actual_common_dir" = "$expected_common_dir" ] \
     && [ -n "$created_branch_oid" ]; then
    # update-ref 携带旧 oid：ref 已由 Orca 一并清掉时是幂等成功；当前 oid 不同时拒绝删除。
    # Git ref 只按 oid 做 CAS，无法区分“删除后以相同 oid 重建”的 ABA；调用方仍须使用唯一 worker name。
    if ! git --git-dir="$actual_common_dir" update-ref -d "refs/heads/$name" "$created_branch_oid"; then
      echo "ERROR: worktree 已回滚，但本次新建 branch 未能按原 oid 安全删除: branch=$name oid=$created_branch_oid" >&2
      cleanup_ok=0
    fi
  fi

  if [ "$cleanup_ok" -eq 1 ]; then
    return 0
  fi
  return 1
}

# ORCA worktree create helper。返回 ORCA worktreeId (含完整 <repoId>::<path>)。
# 失败时打印 ERROR 并 return 64。--dry-run 模式只打印计划不真调。
orca_worktree_create() {
  local name="$1" base_branch="$2"
  local project_toplevel="${ORCA_PROJECT_TOPLEVEL:-}"
  local expected_repo_id="${ORCA_EXPECTED_REPO_ID:-}"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'ORCA_RUN: (cd %q && orca worktree create --name %q --no-parent --base-branch %q --setup inherit --json)\n' \
      "$project_toplevel" "$name" "$base_branch"
    echo "orca_worktree_id_placeholder"
    return 0
  fi
  if [ -z "$project_toplevel" ] || [ -z "$expected_repo_id" ]; then
    echo "ERROR: Orca create 缺少已验证的 PROJECT_DIR top/repoId（fail-closed）" >&2
    return 64
  fi

  local out worktree_id worktree_path actual_repo_id
  local expected_common_dir="" branch_preexisting=0
  expected_common_dir=$(orca_git_common_dir "$project_toplevel" 2>/dev/null || true)
  [ -n "$expected_common_dir" ] || {
    echo "ERROR: 已验证的 Orca PROJECT_DIR 不再是 Git worktree: $project_toplevel" >&2
    return 64
  }
  if git --git-dir="$expected_common_dir" show-ref --verify --quiet "refs/heads/$name"; then
    branch_preexisting=1
  fi

  # worktree create 的 repo inference 是 cwd-scoped。把这一条有副作用的调用局部绑定到
  # 已由 `orca worktree current` 验证的 PROJECT_DIR git top，避免符号链接技能目录把
  # create 路由到其物理目标仓库；不全局 cd，保持 lightweight/相对参数语义不变。
  out=$(cd "$project_toplevel" && \
    orca_cli worktree create --name "$name" --no-parent --base-branch "$base_branch" --setup inherit --json 2>&1) || {
    echo "ERROR: orca worktree create 失败: $out" >&2
    return 64
  }
  if ! printf '%s' "$out" | jq -e '.result.worktree | type == "object"' >/dev/null 2>&1; then
    echo "ERROR: orca worktree create 返回非法 JSON/合同；无法从响应证明资源身份，保留现场: $out" >&2
    return 64
  fi
  worktree_id=$(printf '%s' "$out" | jq -r '.result.worktree.id // empty')
  worktree_path=$(printf '%s' "$out" | jq -r '.result.worktree.path // empty')
  if [ -z "$worktree_id" ] && [ -z "$worktree_path" ]; then
    echo "ERROR: orca worktree create 响应缺可精确回滚的 worktree id/path: $out" >&2
    return 64
  fi
  case "$worktree_id" in
    *::*)
      actual_repo_id="${worktree_id%%::*}"
      [ -n "$worktree_path" ] || worktree_path="${worktree_id#*::}"
      ;;
    *) actual_repo_id="" ;;
  esac

  if [ -z "$actual_repo_id" ] || [ "$actual_repo_id" != "$expected_repo_id" ]; then
    local rollback_status="completed"
    if ! orca_rollback_created_worktree \
        "$worktree_id" "$worktree_path" "$name" "$branch_preexisting" "$expected_common_dir"; then
      rollback_status="failed_or_partial_resources_retained"
    fi
    echo "ERROR: Orca worktree repoId mismatch (fail-closed): expected_repoId=$expected_repo_id actual_repoId=${actual_repo_id:-malformed} project=$project_toplevel created_id=$worktree_id created_path=${worktree_path:-unknown} rollback=$rollback_status" >&2
    return 64
  fi
  printf '%s\n' "$worktree_id"
}

# ORCA terminal create + tui-idle wait helper。只有非 supervised 模式才发送普通 prompt；
# supervised 模式由 worker-start 注入唯一的生命周期 preamble + TASK，禁止双重投递。
# 输入：worktree id、title、worker command。
# 输出：写入 ORCA_TERMINAL_HANDLE 全局变量。
# --dry-run 模式只打印计划不真调，ORCA_TERMINAL_HANDLE 设占位符。
orca_terminal_create_and_send() {
  local worktree_id="$1" title="$2" command="$3"
  local prompt="${4:-请按你的任务开始工作}"

  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'ORCA_RUN: orca terminal create --worktree id:%q --title %q --command %q --json\n' \
      "$worktree_id" "$title" "$command"
    printf 'ORCA_RUN: orca terminal wait --terminal <handle> --for tui-idle --timeout-ms 60000 --json\n'
    if [ "$ORCA_SUPERVISED" -ne 1 ]; then
      printf 'ORCA_RUN: orca terminal send --terminal <handle> --text %q --enter --json\n' "$prompt"
    else
      printf 'ORCA_RUN: supervised prompt will be injected by orchestration worker-start\n'
    fi
    ORCA_TERMINAL_HANDLE="orca_terminal_handle_placeholder"
    return 0
  fi

  local out handle
  out=$(orca_cli terminal create --worktree "id:$worktree_id" --title "$title" --command "$command" --json 2>&1) || {
    echo "ERROR: orca terminal create 失败: $out" >&2
    exit 64
  }
  handle=$(printf '%s' "$out" | jq -r '.result.terminal.handle // empty')
  if [ -z "$handle" ]; then
    echo "ERROR: orca terminal create 响应缺 handle: $out" >&2
    exit 64
  fi
  ORCA_TERMINAL_HANDLE="$handle"

  orca_cli terminal wait --terminal "$handle" --for tui-idle --timeout-ms 60000 --json >/dev/null 2>&1 || {
    echo "SPAWN_WORKER_ORCA_TUI_WAIT_TIMEOUT: tui-idle 60s 内未就绪，继续投 prompt（不阻塞）" >&2
  }

  if [ "$ORCA_SUPERVISED" -ne 1 ]; then
    orca_cli terminal send --terminal "$handle" --text "$prompt" --enter --json >/dev/null 2>&1 || {
      echo "ERROR: orca terminal send 失败（worker 已开但 prompt 没投；PM 需用 pm-orchestrate send 重投）" >&2
      exit 64
    }
  fi
}
