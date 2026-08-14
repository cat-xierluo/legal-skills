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
    ORCA_MODE="force_tmux"; return 0
  fi

  local project_toplevel
  project_toplevel="$ORCA_CURRENT_WORKTREE_PATH"
  ORCA_WORKTREE_ID="$ORCA_CURRENT_WORKTREE_ID"

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

# ORCA worktree create helper。返回 ORCA worktreeId (含完整 <repoId>::<path>)。
# 失败时打印 ERROR 并 exit 64。--dry-run 模式只打印计划不真调。
orca_worktree_create() {
  local name="$1" base_branch="$2"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'ORCA_RUN: orca worktree create --name %q --no-parent --base-branch %q --setup inherit --json\n' "$name" "$base_branch"
    echo "orca_worktree_id_placeholder"
    return 0
  fi
  local out worktree_id
  out=$(orca_cli worktree create --name "$name" --no-parent --base-branch "$base_branch" --setup inherit --json 2>&1) || {
    echo "ERROR: orca worktree create 失败: $out" >&2
    exit 64
  }
  worktree_id=$(printf '%s' "$out" | jq -r '.result.worktree.id // empty')
  if [ -z "$worktree_id" ]; then
    echo "ERROR: orca worktree create 响应缺 worktreeId: $out" >&2
    exit 64
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
