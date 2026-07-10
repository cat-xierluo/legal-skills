#!/usr/bin/env bash
# spawn-worker.sh — create an isolated worktree and tmux session for one worker.
#
# PM 派活前必带 skill 路径清单（task #7 / §3.7）：
#   非 Claude Code 的 worker（codebuddy / qoderwork / 跨工具 backend）跑在独立 cwd，
#   默认看不到 Claude Code skills 目录。PM 在调本脚本 spawn 之前，应先收集本项目
#   相关 sibling skill 的绝对路径，校验存在后追加到 --command 后的 worker prompt 的
#   "Project Skills" 段（标准模板见 SKILL.md §3.7）：
#     ls <project-root>/<sibling-skill>/SKILL.md   # 逐个校验路径存在
#   任何涉及验证码的任务，PM 必须把 captcha-auto 的 SKILL.md 绝对路径写进该段——
#   这是 §3.6「worker 必须自动调 captcha-auto、禁止用户手动输入」的前置条件。
#   本脚本只负责隔离与启动，不自动探测/注入 skill 路径；路径收集是 PM 的派发前职责。
#
# Trust + permission dialog 兜底（v1.18.3 + v1.18.4）：
#   - 启动后可能弹 trust dialog（选 1 = Trust folder only）：trust_auto() 同步处理 30s。
#   - 即便 --permission-mode acceptEdits -y，每个工具调用仍弹 "Do you want to proceed?"：
#     - permission_auto() 同步处理 60s（v1.18.3 起改用 `2 Enter` 数字键）。
#     - permission_auto_bg() 后台 watcher 持续 7200s（disown 到后台），覆盖首次 dialog
#       出现在 60s 之后的情况。
#   - v1.18.4：默认行为按 backend 分支化（DEC-112）：
#     * claude-code 实测 `--permission-mode auto --bare` 不弹 dialog，默认全关
#       （spawn 秒级返回，避免 trust_auto 30s + permission_auto 60s 共 90s 空等，
#       见 2026-07-10 某多 worker Wave 实战 follow-up + DEC-112）；
#     * 其他 backend（codebuddy / qoderwork-cn / codex / opencode）仍默认启
#       （这些 backend 真弹 dialog）。
#   - 6 个 --*/--no-* flag 均可 force override 默认值，详见 usage 段与 DEC-112。

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

PROJECT_DIR=""
BRANCH=""
WORKTREE=""
SESSION=""
BASE_REF="main"
COMMAND=""
DRY_RUN=0
WORKER_BACKEND=""
RUNTIME_PROFILE=""
API_PROVIDER=""
MODEL=""
PROVIDER_SLOT=""
ENV_ISOLATION=""
WAVE_ID=""
WAVE_WORKER_ID=""
VERIFY_COMMANDS=()
WITH_SENTINEL=0
SENTINEL_POLL_INTERVAL=5
SENTINEL_MAX_WAIT=7200
KEEP_TMUX_ON_TERMINAL=0
# v1.18.4：trust/permission dialog 监控默认值改 backend 分支化（DEC-112）
# - *_OVERRIDE 标志在 flag 解析时被置 1，由 resolve_backend_defaults() 检查并跳过
# - claude-code 默认全关：实测 --permission-mode auto + --bare 不弹 dialog，省 90s 空等
# - 其他 backend 默认全开：codebuddy/qoderwork-cn/codex/opencode 真弹 dialog
TRUST_AUTO_OVERRIDE=0
TRUST_AUTO=1
PERMISSION_AUTO_OVERRIDE=0
PERMISSION_AUTO=1
PERMISSION_AUTO_BG_OVERRIDE=0
PERMISSION_AUTO_BG=1  # v1.18.4：bg watcher 独立控制；与 sync permission_auto 解耦
ADD_DIRS=()
ALLOW_PATHS=()

usage() {
  cat >&2 <<'USAGE'
Usage:
  spawn-worker.sh --project PATH --branch NAME --session NAME [options]

Options:
  --worktree PATH   Worktree path. Defaults to .claude/worktrees/tmux-{branch}
  --base-ref REF    Base ref for new branches. Default: main
  --command CMD     Command to run in tmux. Default: login shell
  --worker-backend NAME
                   Worker backend, e.g. claude-code, codex, opencode, custom
  --runtime-profile NAME
                   Runtime/settings/profile name used by the worker
  --api-provider NAME
                   API/provider name used by the worker
  --model NAME     Model name used by the worker
  --provider-slot SLOT
                   Provider concurrency slot for this worker
  --env-isolation DESC
                   Provider/env isolation strategy recorded in METADATA.json
  --wave-id ID     Wave ID for this worker
  --wave-worker-id ID
                   Worker ID within the wave
  --verify-cmd CMD Expected verification command; repeat for multiple commands
  --with-sentinel   Print recommended sentinel.sh command (does NOT start sentinel itself)
  --sentinel-poll-interval N
                   Default 5; passed to the recommended sentinel command
  --sentinel-max-wait SECONDS
                   Default 7200; passed to the recommended sentinel command
  --keep-tmux-on-terminal
                   Pass --keep-tmux-on-terminal to the recommended sentinel command
  --no-trust-auto   Skip trust-folder auto-accept for codebuddy/qoder CLI workers.
                   Default (v1.18.4): claude-code backend = ON, other backends = ON.
                   Use --no-trust-auto to force OFF; --trust-auto to force ON.
                   Default action: auto-select 'Trust folder and all subdirectories'
                   (option 3) to avoid both initial and subdir trust prompts.
  --trust-auto     (v1.18.4 new) Force trust dialog auto-accept ON, overriding
                   backend default. Use after Claude Code upgrades that
                   re-introduce the trust dialog in --permission-mode auto.
  --no-permission-auto  (v1.18.3) Skip runtime permission auto-accept (both sync 60s
                   and background 7200s watcher). Default (v1.18.4): claude-code = OFF,
                   other backends = ON. Default action when ON: auto-select option 2
                   (Yes, and don't ask again for session) on every "Do you want to
                   proceed?" dialog. Use only if you intentionally want to handle
                   permission prompts manually.
  --permission-auto     (v1.18.4 new) Force BOTH sync + bg permission auto-accept ON,
                   overriding backend default. Use after Claude Code upgrades that
                   re-introduce runtime permission dialog.
  --no-permission-auto-bg  (v1.18.4 new) Only skip background 7200s watcher; sync
                   permission_auto unchanged. Use when sync dialogs are wanted but
                   the bg resource cost (1 shell / 5s poll) is not.
  --permission-auto-bg     (v1.18.4 new) Force background 7200s watcher ON,
                   overriding backend default. Useful when sync dialogs are off
                   but late dialogs (after initial 60s) still expected.
  --add-dir DIR     Extra directories for codebuddy to access outside the worktree
                   (repeatable). Passed through to codebuddy's --add-dir flag.
                   Use when task files/assets are outside the worktree, e.g.:
                   --add-dir /tmp --add-dir ../shared-assets
  --allow-paths GLOB
                   Scope guard: only allow file writes matching GLOB patterns.
                   Repeatable, accumulated into SCOPE_GUARD_ALLOW env var (: separated).
                   Writes .codebuddy/settings.local.json (or .qoder/settings.local.json)
                   with PreToolUse hook pointing to scripts/scope-guard.py.
                   When set, spawned worker cannot write files outside these globs
                   even with -y/--dangerously-skip-permissions (PreToolUse hook unbypassable).
                   Use when PM wants to hard-guard against worker scope violations,
                   e.g. --allow-paths 'skills/my-skill/**' --allow-paths 'skills/another-skill/**'
  --dry-run         Print actions without changing anything

The script only creates isolation and starts the session. The PM must still send
the Bootstrap-only or Full worker prompt and confirm STATUS.json appears.
When --with-sentinel is set, spawn-worker.sh outputs the sentinel command but
does NOT start the sentinel itself. The PM must run that command with
run_in_background=true so the harness re-invokes PM on sentinel exit.

Troubleshooting: if 'which codebuddy' returns 'not found', the CLI binary may
still exist in the .app bundle. Use:
  bash scripts/check-dependencies.sh --backend codebuddy --strict
for multi-source detection, or get the absolute path directly:
  bash scripts/check-dependencies.sh --print-bundle-path codebuddy
then pass it to spawn-worker via --command or --bin.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT_DIR="$2"
      shift 2
      ;;
    --branch)
      BRANCH="$2"
      shift 2
      ;;
    --worktree)
      WORKTREE="$2"
      shift 2
      ;;
    --session)
      SESSION="$2"
      shift 2
      ;;
    --base-ref)
      BASE_REF="$2"
      shift 2
      ;;
    --command)
      COMMAND="$2"
      shift 2
      ;;
    --worker-backend)
      WORKER_BACKEND="$2"
      shift 2
      ;;
    --runtime-profile)
      RUNTIME_PROFILE="$2"
      shift 2
      ;;
    --api-provider)
      API_PROVIDER="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    --provider-slot)
      PROVIDER_SLOT="$2"
      shift 2
      ;;
    --env-isolation)
      ENV_ISOLATION="$2"
      shift 2
      ;;
    --wave-id)
      WAVE_ID="$2"
      shift 2
      ;;
    --wave-worker-id)
      WAVE_WORKER_ID="$2"
      shift 2
      ;;
    --verify-cmd)
      VERIFY_COMMANDS+=("$2")
      shift 2
      ;;
    --with-sentinel)
      WITH_SENTINEL=1
      shift
      ;;
    --sentinel-poll-interval)
      SENTINEL_POLL_INTERVAL="$2"
      shift 2
      ;;
    --sentinel-max-wait)
      SENTINEL_MAX_WAIT="$2"
      shift 2
      ;;
    --keep-tmux-on-terminal)
      KEEP_TMUX_ON_TERMINAL=1
      shift
      ;;
    --no-trust-auto)
      TRUST_AUTO=0
      TRUST_AUTO_OVERRIDE=1
      shift
      ;;
    --trust-auto)  # v1.18.4：显式 opt-in 强制启
      TRUST_AUTO=1
      TRUST_AUTO_OVERRIDE=1
      shift
      ;;
    --no-permission-auto)  # v1.18.3：兼容 v1.18.3 行为，同时关 sync + bg
      PERMISSION_AUTO=0
      PERMISSION_AUTO_BG=0
      PERMISSION_AUTO_OVERRIDE=1
      PERMISSION_AUTO_BG_OVERRIDE=1
      shift
      ;;
    --permission-auto)  # v1.18.4：显式 opt-in 强制启 sync + bg
      PERMISSION_AUTO=1
      PERMISSION_AUTO_BG=1
      PERMISSION_AUTO_OVERRIDE=1
      PERMISSION_AUTO_BG_OVERRIDE=1
      shift
      ;;
    --no-permission-auto-bg)  # v1.18.4：精细 opt-out 只关 bg watcher
      PERMISSION_AUTO_BG=0
      PERMISSION_AUTO_BG_OVERRIDE=1
      shift
      ;;
    --permission-auto-bg)  # v1.18.4：精细 opt-in 强制启 bg watcher
      PERMISSION_AUTO_BG=1
      PERMISSION_AUTO_BG_OVERRIDE=1
      shift
      ;;
    --add-dir)
      ADD_DIRS+=("$2")
      shift 2
      ;;
    --allow-paths)
      ALLOW_PATHS+=("$2")
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 64
      ;;
  esac
done

[ -n "$PROJECT_DIR" ] || { usage; exit 64; }
[ -n "$BRANCH" ] || { usage; exit 64; }
[ -n "$SESSION" ] || { usage; exit 64; }
command -v git >/dev/null 2>&1 || { echo "ERROR: git is required" >&2; exit 64; }
command -v tmux >/dev/null 2>&1 || { echo "ERROR: tmux is required" >&2; exit 64; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }

PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd -P)
safe_branch=$(printf '%s' "$BRANCH" | tr '/[:space:]' '-' | tr -cd 'A-Za-z0-9._-')
if [ -z "$WORKTREE" ]; then
  WORKTREE=".claude/worktrees/tmux-$safe_branch"
fi
case "$WORKTREE" in
  /*) ;;
  *) WORKTREE="$PROJECT_DIR/$WORKTREE" ;;
esac

SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
METADATA_FILE="$SESSION_CONTEXT/METADATA.json"
[ -n "$COMMAND" ] || COMMAND="${SHELL:-/bin/bash} -l"

run() {
  printf 'SPAWN_WORKER_RUN: %s\n' "$*"
  [ "$DRY_RUN" -eq 1 ] || "$@"
}

# v1.18.4：backend 分支化 trust/permission dialog 监控默认值（DEC-112）。
# 仅在 *_OVERRIDE 标志为 0 时（即用户没显式传 flag）才按 backend 默认。
# claude-code backend 默认全关，省 trust_auto 30s + permission_auto 60s 共 90s 空等；
# 其他 backend 默认全开。
resolve_backend_defaults() {
  if [ "$TRUST_AUTO_OVERRIDE" -eq 0 ]; then
    case "$WORKER_BACKEND" in
      claude-code|claude_code) TRUST_AUTO=0 ;;
      *) TRUST_AUTO=1 ;;
    esac
  fi
  if [ "$PERMISSION_AUTO_OVERRIDE" -eq 0 ]; then
    case "$WORKER_BACKEND" in
      claude-code|claude_code) PERMISSION_AUTO=0 ;;
      *) PERMISSION_AUTO=1 ;;
    esac
  fi
  if [ "$PERMISSION_AUTO_BG_OVERRIDE" -eq 0 ]; then
    case "$WORKER_BACKEND" in
      claude-code|claude_code) PERMISSION_AUTO_BG=0 ;;
      *) PERMISSION_AUTO_BG=1 ;;
    esac
  fi
}
resolve_backend_defaults

if ! git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: --project is not a git work tree: $PROJECT_DIR" >&2
  exit 64
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "ERROR: tmux session already exists: $SESSION" >&2
  exit 1
fi

if ! git -C "$PROJECT_DIR" rev-parse --verify --quiet "$BASE_REF^{commit}" >/dev/null; then
  echo "ERROR: base ref not found: $BASE_REF" >&2
  exit 1
fi
BASE_SHA=$(git -C "$PROJECT_DIR" rev-parse "$BASE_REF^{commit}")

existing_wt=$(git -C "$PROJECT_DIR" worktree list --porcelain | awk -v target="refs/heads/$BRANCH" '
  /^worktree / { wt = substr($0, 10) }
  /^branch / {
    if (substr($0, 8) == target) {
      print wt
      exit
    }
  }
')

if [ -n "$existing_wt" ]; then
  WORKTREE="$existing_wt"
  SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
  METADATA_FILE="$SESSION_CONTEXT/METADATA.json"
  echo "SPAWN_WORKER_REUSE_WORKTREE: $WORKTREE"
elif [ -d "$WORKTREE" ]; then
  echo "ERROR: worktree path exists but is not registered for branch $BRANCH: $WORKTREE" >&2
  exit 1
elif git -C "$PROJECT_DIR" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  run git -C "$PROJECT_DIR" worktree add "$WORKTREE" "$BRANCH"
else
  run git -C "$PROJECT_DIR" worktree add "$WORKTREE" -b "$BRANCH" "$BASE_REF"
fi

if [ "$DRY_RUN" -eq 0 ]; then
  WORKTREE=$(cd "$WORKTREE" && pwd -P)
  SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
  METADATA_FILE="$SESSION_CONTEXT/METADATA.json"
fi

run mkdir -p "$SESSION_CONTEXT"

write_metadata() {
  created_at=$(date -u "+%Y-%m-%dT%H:%M:%SZ")
  if [ "${#VERIFY_COMMANDS[@]}" -gt 0 ]; then
    verify_json=$(printf '%s\n' "${VERIFY_COMMANDS[@]}" | jq -R . | jq -s .)
  else
    verify_json="[]"
  fi

  echo "SPAWN_WORKER_METADATA: $METADATA_FILE"
  if [ "$DRY_RUN" -eq 1 ]; then
    return 0
  fi

  jq -n \
    --arg schema "multi-agent-orchestration.worktree-metadata.v1" \
    --arg created_at "$created_at" \
    --arg project "$PROJECT_DIR" \
    --arg worktree "$WORKTREE" \
    --arg branch "$BRANCH" \
    --arg base_ref "$BASE_REF" \
    --arg base_sha "$BASE_SHA" \
    --arg session "$SESSION" \
    --arg session_context "$SESSION_CONTEXT" \
    --arg command "$COMMAND" \
    --arg worker_backend "$WORKER_BACKEND" \
    --arg runtime_profile "$RUNTIME_PROFILE" \
    --arg api_provider "$API_PROVIDER" \
    --arg model "$MODEL" \
    --arg provider_slot "$PROVIDER_SLOT" \
    --arg env_isolation "$ENV_ISOLATION" \
    --arg wave_id "$WAVE_ID" \
    --arg wave_worker_id "$WAVE_WORKER_ID" \
    --argjson verification_commands "$verify_json" \
    --argjson add_dirs "$(printf '%s\n' "${ADD_DIRS[@]}" | jq -R . | jq -s .)" \
    --argjson allow_paths "$(printf '%s\n' "${ALLOW_PATHS[@]}" | jq -R . | jq -s .)" \
    '{
      schema: $schema,
      created_at: $created_at,
      project: $project,
      worktree: $worktree,
      branch: $branch,
      base_ref: $base_ref,
      base_sha: $base_sha,
      session: {
        id: $session,
        context: $session_context
      },
      runtime: {
        worker_backend: $worker_backend,
        runtime_profile: $runtime_profile,
        api_provider: $api_provider,
        model: $model,
        provider_slot: $provider_slot,
        env_isolation: $env_isolation,
        command: $command
      },
      wave: {
        id: $wave_id,
        worker_id: $wave_worker_id
      },
      verification: {
        commands: $verification_commands
      },
      add_dirs: $add_dirs,
      allow_paths: $allow_paths,
      pr: {
        number: null,
        url: "",
        state: ""
      }
    }' > "$METADATA_FILE"
}

# Trust folder auto-accept for headless codebuddy/qoder CLI workers.
# Default: auto-select "Trust folder and all subdirectories" (option 3) to
# avoid both the initial trust prompt AND subsequent subdir trust prompts.
# Polls the tmux pane for trust dialog text, then sends Down×3+Enter.
trust_auto() {
  local session="$1"
  local max_wait=30
  local poll_interval=1
  local waited=0

  while [ "$waited" -lt "$max_wait" ]; do
    if ! tmux has-session -t "$session" 2>/dev/null; then
      return 1  # session died, trust-auto skipped
    fi

    local content
    content=$(tmux capture-pane -t "$session" -p -S -50 2>/dev/null || echo "")

    # codebuddy trust dialog:
    #   Do you want to proceed?
    #   1. Trust folder only / 2. Trust parent folder / 3. Trust folder and all subdirectories / 4. No, exit
    if echo "$content" | grep -q "Trust folder and all subdirectories"; then
      echo "SPAWN_WORKER_TRUST_AUTO: trust dialog detected, selecting Trust folder and all subdirectories (option 3)"
      tmux send-keys -t "$session" Down Down Down Enter
      sleep 2  # wait for trust to take effect
      return 0
    fi

    # Generic fallback: match other trust/Do you trust dialogs
    if echo "$content" | grep -qE "Trust folder|Do you trust" 2>/dev/null; then
      echo "SPAWN_WORKER_TRUST_AUTO: trust dialog detected (generic), selecting last trust option (Down×3+Enter)"
      tmux send-keys -t "$session" Down Down Down Enter
      sleep 2
      return 0
    fi

    sleep "$poll_interval"
    waited=$((waited + poll_interval))
  done

  echo "SPAWN_WORKER_TRUST_AUTO: no trust dialog seen within ${max_wait}s, continuing"
  return 0
}

# Permission auto-accept for runtime "Do you want to proceed?" prompts.
# v1.18.3 关键修复：旧版用 Down Enter（按箭头 + Enter 选 option 2），在某些 TUI 状态
# 不稳。PM 2026-07-08 wave-1 实测：直接发数字键 `2` 选 option 2 (Yes, and don't ask
# again for this session) 稳定 work。改用 `2` 数字键（不再 Down Enter）。
# Polls the tmux pane for the runtime permission prompt (appears when codebuddy
# tries to access files outside the worktree) and auto-selects option 2.
# Runs with a longer timeout (60s) since runtime prompts appear later.
# opt-out: --no-permission-auto (v1.18.3 精细 opt-out) 或共享 --no-trust-auto。
permission_auto() {
  local session="$1"
  local max_wait=60
  local poll_interval=2
  local waited=0

  while [ "$waited" -lt "$max_wait" ]; do
    if ! tmux has-session -t "$session" 2>/dev/null; then
      return 1  # session died, permission-auto skipped
    fi

    local content
    content=$(tmux capture-pane -t "$session" -p -S -50 2>/dev/null || echo "")

    # Match "Do you want to proceed?" dialog with session-allow option:
    #   Do you want to proceed?
    #     1. Yes
    #   > 2. Yes, and don't ask again for session (shift + tab)
    #     3. No, and tell CodeBuddy what to do differently (escape)
    if echo "$content" | grep -q "Do you want to proceed"; then
      echo "SPAWN_WORKER_PERMISSION_AUTO: 'Do you want to proceed' dialog detected, selecting session-allow (option 2, key '2')"
      tmux send-keys -t "$session" "2"  # v1.18.3: 改用数字键 2（PM 实测 work）
      sleep 2
      return 0
    fi

    sleep "$poll_interval"
    waited=$((waited + poll_interval))
  done

  echo "SPAWN_WORKER_PERMISSION_AUTO: no runtime permission prompt seen within ${max_wait}s, continuing"
  return 0
}

# v1.18.3 新加：后台 watcher 持续监控 + 自动按 2 兜底，覆盖同步 60s 窗口外的 dialog。
# 由 spawn-worker.sh 主流程 `permission_auto_bg &` 启 disown，7200s 自动退出。
# 实现：每 SPAWN_PERMISSION_BG_POLL 秒 (默认 5) capture pane 检测 "Do you want to proceed"，
# 命中发数字键 2；如 spawn-worker.sh 退出，watcher 独立继续到 max_wait。
permission_auto_bg() {
  local session="$1"
  local max_wait="${SPAWN_PERMISSION_BG_MAX_WAIT:-7200}"  # 默认 2h，与 sentinel --max-wait 对齐
  local poll_interval="${SPAWN_PERMISSION_BG_POLL:-5}"
  local waited=0
  local hits=0

  while [ "$waited" -lt "$max_wait" ]; do
    if ! tmux has-session -t "$session" 2>/dev/null; then
      echo "SPAWN_WORKER_PERMISSION_BG: session $session ended after ${waited}s, watcher exits (hits=$hits)"
      return 0
    fi

    local content
    content=$(tmux capture-pane -t "$session" -p -S -50 2>/dev/null || echo "")

    if echo "$content" | grep -q "Do you want to proceed"; then
      hits=$((hits + 1))
      echo "SPAWN_WORKER_PERMISSION_BG: 'Do you want to proceed' detected (hit $hits at ${waited}s), sending '2'"
      tmux send-keys -t "$session" "2"
      sleep 2  # 让 dialog 关闭
    fi

    sleep "$poll_interval"
    waited=$((waited + poll_interval))
  done

  echo "SPAWN_WORKER_PERMISSION_BG: max_wait ${max_wait}s reached, watcher exits (hits=$hits)"
  return 0
}

# Scope guard setup: write settings.local.json with PreToolUse hook + inject
# SCOPE_GUARD_ALLOW env var into the tmux command so scope-guard.py can enforce
# write-path whitelist even under -y/--dangerously-skip-permissions.
# Based on ref 07 §9 (qoder PreToolUse hook unbypassable) and ref 08 §12
# (codebuddy PreToolUse hook semantic parity expected).
# Only active when --allow-paths is set; otherwise no-op (backward compatible).
scope_guard_setup() {
  if [ "${#ALLOW_PATHS[@]}" -eq 0 ]; then
    return 0  # no scope guard
  fi

  # Find scope-guard-hook.sh (wrapper) + scope-guard.py (in skill scripts dir)
  # wrapper 必需:codebuddy/qoder 直接调 `python3 scope-guard.py` 时 stdin 不传
  # (实测 2026-07-05 stdin 丢失 → scope-guard no-op → 越界不拦);wrapper 用 cat 中转 stdin。
  local scope_guard_hook="$SCRIPT_DIR/scope-guard-hook.sh"
  local scope_guard_py="$SCRIPT_DIR/scope-guard.py"
  if [ ! -f "$scope_guard_hook" ] || [ ! -f "$scope_guard_py" ]; then
    echo "SPAWN_WORKER_SCOPE_GUARD_WARN: scope-guard-hook.sh or scope-guard.py not found, skipping" >&2
    return 1
  fi

  # Build SCOPE_GUARD_ALLOW env var (: separated glob list)
  local scope_env
  scope_env=$(IFS=:; echo "${ALLOW_PATHS[*]}")
  export SCOPE_GUARD_ALLOW="$scope_env"
  echo "SPAWN_WORKER_SCOPE_GUARD_ALLOW: $SCOPE_GUARD_ALLOW"

  # Inject SCOPE_GUARD_ALLOW into the tmux command via wrapper
  COMMAND="env SCOPE_GUARD_ALLOW='$SCOPE_GUARD_ALLOW' $COMMAND"

  # Write settings.local.json for both codebuddy and qoder backends
  # codebuddy: .codebuddy/settings.local.json
  # qoder:     .qoder/settings.local.json
  local settings_json
  # Use printf to safely embed the quoted path (handles spaces in path)
  settings_json=$(printf '{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Edit|Write|NotebookEdit",
      "hooks": [{
        "type": "command",
        "command": "bash '\''%s'\''"
      }]
    }]
  }
}' "$scope_guard_hook")

  # Write to codebuddy settings if backend is codebuddy or unspecified
  if [ "$WORKER_BACKEND" = "codebuddy" ] || [ -z "$WORKER_BACKEND" ]; then
    local cb_settings_dir="$WORKTREE/.codebuddy"
    run mkdir -p "$cb_settings_dir"
    local cb_settings_file="$cb_settings_dir/settings.local.json"
    if [ "$DRY_RUN" -eq 0 ]; then
      echo "$settings_json" > "$cb_settings_file"
      echo "SPAWN_WORKER_SCOPE_GUARD_SETTINGS: $cb_settings_file"
    else
      echo "SPAWN_WORKER_SCOPE_GUARD_DRY_RUN: would write $cb_settings_file"
    fi
  fi

  # Write to qoder settings if backend is qoderwork-cn
  if [ "$WORKER_BACKEND" = "qoderwork-cn" ]; then
    local qw_settings_dir="$WORKTREE/.qoder"
    run mkdir -p "$qw_settings_dir"
    local qw_settings_file="$qw_settings_dir/settings.local.json"
    if [ "$DRY_RUN" -eq 0 ]; then
      echo "$settings_json" > "$qw_settings_file"
      echo "SPAWN_WORKER_SCOPE_GUARD_SETTINGS: $qw_settings_file"
    else
      echo "SPAWN_WORKER_SCOPE_GUARD_DRY_RUN: would write $qw_settings_file"
    fi
  fi

  return 0
}

scope_guard_setup
write_metadata

exclude_file=$(git -C "$WORKTREE" rev-parse --git-path info/exclude)
if [ "$DRY_RUN" -eq 0 ] && ! grep -qxF ".claude/agent-sessions/" "$exclude_file" 2>/dev/null; then
  printf '\n.claude/agent-sessions/\n' >> "$exclude_file"
fi

# Launch.sh auto-wrap: COMMAND 含空格时(路径拆词风险,如 qoder BIN
# /Applications/QoderWork CN.app 含空格),tmux new-session 的 command 解析
# 会吃掉 %q 反斜杠转义 → env 127(command not found)。
# 修复(2026-07-05 实测):写 launch.sh(launch.sh 内 `exec bash -c %q` 在 bash
# 下正确解析转义),tmux 只跑 `bash launch.sh`(无空格),绕过 tmux command 解析。
# 通用:codebuddy(qoderclicn)/ qoder / 任何含空格路径或特殊字符的 COMMAND 都受益。
if [[ "$COMMAND" == *' '* ]]; then
  LAUNCH_SH="$WORKTREE/.claude/agent-sessions/$SESSION/launch.sh"
  mkdir -p "$(dirname "$LAUNCH_SH")"
  printf '#!/bin/bash\n# spawn-worker 自动生成:绕过 tmux command 解析(路径空格/特殊字符)\n# 原始 COMMAND 在 bash -c 下正确解析 %%q 转义(tmux 的 command parser 会吃反斜杠)\nexec bash -c %q\n' "$COMMAND" > "$LAUNCH_SH"
  chmod +x "$LAUNCH_SH"
  COMMAND="bash $(printf '%q' "$LAUNCH_SH")"
fi

run tmux new-session -d -s "$SESSION" -c "$WORKTREE" "$COMMAND"

# Trust-auto + Permission-auto: headless CLI workers need trust-folder permission
# and runtime permission prompts auto-accepted.
# trust_auto: Selects "Trust folder and all subdirectories" (option 3) to avoid
# both the initial trust prompt and subsequent subdir trust prompts.
# permission_auto: Selects "Yes, and don't ask again for session" (option 2)
# for "Do you want to proceed?" runtime prompts (cross-directory access).
# permission_auto_bg (v1.18.3): 后台 watcher 持续 7200s，覆盖同步 60s 窗口外的 dialog。
# v1.18.4: 默认值按 backend 分支（resolve_backend_defaults），claude-code 默认全关省 90s 空等；
# 其他 backend 默认全开。flag --*/--no-* 均可 force override 默认值（详见 usage）。
if [ "$DRY_RUN" -eq 0 ] && [ "$TRUST_AUTO" -eq 1 ]; then
  trust_auto "$SESSION"
fi
if [ "$DRY_RUN" -eq 0 ] && [ "$PERMISSION_AUTO" -eq 1 ]; then
  permission_auto "$SESSION"
fi
if [ "$DRY_RUN" -eq 0 ] && [ "$PERMISSION_AUTO_BG" -eq 1 ]; then
  # v1.18.4: bg watcher 独立 gate（与 sync permission_auto 解耦），claude-code 默认不启
  # disown 让 spawn-worker.sh 退出不影响 watcher
  ( permission_auto_bg "$SESSION" & disown ) &
fi

if [ "$DRY_RUN" -eq 0 ]; then
  pane_cwd=$(tmux display-message -p -t "$SESSION" '#{pane_current_path}' 2>/dev/null || echo "")
  pane_cwd_physical="$pane_cwd"
  if [ -n "$pane_cwd" ] && [ -d "$pane_cwd" ]; then
    pane_cwd_physical=$(cd "$pane_cwd" && pwd -P)
  fi
  current_branch=$(git -C "$WORKTREE" branch --show-current 2>/dev/null || echo "")
  echo "SPAWN_WORKER_SESSION: $SESSION"
  echo "SPAWN_WORKER_WORKTREE: $WORKTREE"
  echo "SPAWN_WORKER_CONTEXT: $SESSION_CONTEXT"
  echo "SPAWN_WORKER_GATE: cwd=$pane_cwd_physical branch=$current_branch expected_cwd=$WORKTREE expected_branch=$BRANCH"
  if [ "$pane_cwd_physical" != "$WORKTREE" ] || [ "$current_branch" != "$BRANCH" ]; then
    echo "SPAWN_WORKER_GATE_FAILED" >&2
    exit 2
  fi
fi

echo "SPAWN_WORKER_NEXT: send worker prompt, then wait for $SESSION_CONTEXT/STATUS.json"

if [ "$WITH_SENTINEL" -eq 1 ] && [ "$DRY_RUN" -eq 0 ]; then
  SENTINEL_SCRIPT="$SCRIPT_DIR/sentinel.sh"
  SENTINEL_CMD="bash $SENTINEL_SCRIPT --status-file $SESSION_CONTEXT/STATUS.json --tmux-session $SESSION --poll-interval $SENTINEL_POLL_INTERVAL --max-wait $SENTINEL_MAX_WAIT"
  if [ "$KEEP_TMUX_ON_TERMINAL" -eq 1 ]; then
    SENTINEL_CMD="$SENTINEL_CMD --keep-tmux-on-terminal"
  fi
  echo "SPAWN_WORKER_SENTINEL_CMD: $SENTINEL_CMD"
  echo "SPAWN_WORKER_RECOMMENDED_NEXT: run the above command with Bash run_in_background=true (NOT from inside spawn-worker). Sentinel exit triggers harness task-notification and wakes PM."
fi
