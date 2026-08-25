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
#     * 其他白名单 backend（codebuddy / qoderwork-cn / codex）仍默认启
#       （这些 backend 真弹 dialog）。
#   - 6 个 --*/--no-* flag 均可 force override 默认值，详见 usage 段与 DEC-112。
#   - v1.20.2（Task-019/020/021，2026-08-05 folia Wave-1 实战）：
#     * Task-019：claude-code provider-isolation 默认 --bare（render-runtime-profile.sh）
#       与 install-guard fail-closed 互斥。spawn-worker 检测到 --bare 自动降级 prompt-only
#       + 内置来源（CLAUDE_CODE_BARE_AUTO_DEGRADE=1），不再要求 PM 手写
#       --allow-prompt-only-install-guard；--no-claude-code-bare-auto-degrade opt-out。
#       --safe-mode / --setting-sources 排除 local / 缺 claude token 仍 fail-closed（非 --bare 不自动降级）。
#     * Task-020：claude-code worker 首启弹 "external imports" dialog（CLAUDE.md @import 触发），
#       v1.18.4 默认关 trust/permission 不覆盖此类。external_imports_auto() 单独监控（option 1 默认放行），
#       claude-code 默认开（EXTERNAL_IMPORTS_AUTO=1，--no-external-imports-auto opt-out）。
#     * Task-021：permission_auto_bg 启动改 setsid（macOS 无 setsid 时 fallback nohup+disown），
#       spawn-worker 被 SIGTERM 时 watcher 尽量存活；codebuddy 同步监控逼近 PM Bash 2min timeout，
#       文档建议 PM Bash timeout 调到 180s+（SKILL §6）。

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# v2.0：PATH 注入 helper（2026-07-12 实战坑：claude 在 ~/.local/bin，wrapper 后
# which 不到）。在 flag 解析之前注入，确保后续 tmux 内 wrapper 派 Claude Code
# 也能复用同一 PATH。
# shellcheck source=ensure-claude-path.sh
source "$SCRIPT_DIR/ensure-claude-path.sh"
ensure_claude_in_path
# Orca 的当前 worktree RPC 是运行时事实来源；不要依赖 TERM_PROGRAM / ORCA_WORKTREE_ID
# 是否被宿主传入。CLI 选择顺序与版本匹配的 orca-cli skill 保持一致。
# shellcheck source=orca-runtime.sh
source "$SCRIPT_DIR/orca-runtime.sh"
# shellcheck source=harness-backend-policy.sh
source "$SCRIPT_DIR/harness-backend-policy.sh"
# shellcheck source=provider-lease-root.sh
source "$SCRIPT_DIR/provider-lease-root.sh"
# shellcheck source=spawn-worker-deps.sh
source "$SCRIPT_DIR/spawn-worker-deps.sh"

PROJECT_DIR=""
BRANCH=""
WORKTREE=""
SESSION=""
BASE_REF="main"
COMMAND=""
DRY_RUN=0
WORKER_BACKEND=""
PM_HARNESS_ASSERTION=""
PM_HARNESS=""
PM_HARNESS_SOURCE=""
PM_HARNESS_CHAIN_JSON="[]"
PM_ALLOWED_WORKER_BACKENDS=""
WORKER_BACKEND_CANONICAL=""
WORKER_COMMAND_SHA256=""
RUNTIME_PROFILE=""
API_PROVIDER=""
MODEL=""
PROVIDER_SLOT=""
PROVIDER_LEASE_FILE=""
PROVIDER_LEASE_ROOT=""
PROVIDER_LEASE_LIMIT=""
PROVIDER_LEASE_KEY=""
PROVIDER_LEASE_ACQUIRED=0
PERSONAL_CONFIG_FILE="${MULTI_AGENT_ORCHESTRATION_PERSONAL_CONFIG:-$SCRIPT_DIR/../config/orchestration-personal.json}"
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
# - 其他白名单 backend 默认全开：codebuddy/qoderwork-cn/codex 真弹 dialog
TRUST_AUTO_OVERRIDE=0
TRUST_AUTO=1
PERMISSION_AUTO_OVERRIDE=0
PERMISSION_AUTO=1
PERMISSION_AUTO_BG_OVERRIDE=0
PERMISSION_AUTO_BG=1  # v1.18.4：bg watcher 独立控制；与 sync permission_auto 解耦
# v1.20.2 Task-020：external imports dialog 监控（claude-code CLAUDE.md @import 触发的第三类 dialog）。
# claude-code 默认开（v1.18.4 关掉了 trust/permission，但 external imports 是 claude 特有的另一类）；
# 其他 backend 无此 dialog，默认关省空等。
EXTERNAL_IMPORTS_AUTO_OVERRIDE=0
EXTERNAL_IMPORTS_AUTO=0
# v1.20.2 Task-019：claude-code --bare 自动降级 prompt-only install-guard（render 默认 --bare 与
# install-guard fail-closed 互斥）。只对 --bare 自动降级；--safe-mode/setting-sources 仍 fail-closed。
CLAUDE_CODE_BARE_AUTO_DEGRADE=1
ADD_DIRS=()
ALLOW_PATHS=()
# v2.0：轻量模式（无 worktree）。默认 0 (走 worktree 隔离)；--no-worktree 显式置 1，
# 或自动检测 --project 不是 git 仓时置 1 并打印 SPAWN_WORKER_LIGHTWEIGHT_AUTO。
# 详见 SKILL.md §2.1.1 + references/09-parallel-lessons.md T6 实战坑。
LIGHTWEIGHT_OVERRIDE=0
LIGHTWEIGHT_MODE=0
LIGHTWEIGHT_AUTO=0
# v2.3：Orca 终端模式 auto-detect。detect_orca_mode() 输出：
#   "auto"                    — worktree current 证明当前项目由 Orca 管理
#   "force_tmux"              — --no-orca-mode 显式 opt-out / 非 ORCA 终端 / 跨 repo
#   "lightweight_forces_tmux" --no-worktree 强制走 tmux（ORCA worktree 必须有 git 仓）
#   "missing_orca"            — 已选择 Orca 路径但 CLI/runtime 不可用（fail-loud）
ORCA_MODE=""
ORCA_WORKTREE_ID="${ORCA_WORKTREE_ID:-}"  # 兼容旧调用方；命中 auto 后以 worktree current 为准
ORCA_WORKTREE_PATH=""    # 仅 auto 时填（git rev-parse --show-toplevel）
ORCA_TERMINAL_HANDLE=""  # 形如 "term_xxx"，仅 auto 时填
ORCA_APP_VERSION=""      # 来自 orca status --json
ORCA_CAPABILITIES_JSON=""  # 来自 orca status --json capabilities 数组
ORCA_TUI_READY_METHOD="orca_terminal_wait_tui-idle"
NO_ORCA_MODE=0
# v2.1.1（Task-033）：ORCA supervised 注册（run-create + task-create + worker-start --terminal）。
# --orca-supervised 启用时，ORCA 模式 spawn 后把 worker terminal 纳入 supervised 体系。
# worker 出现在 worker-list，绑定 task + worktree resource，可被 send/reply/inbox + gate 管理。
ORCA_SUPERVISED=0
TASK_SPEC=""
TASK_TITLE=""
ORCA_RUN_ID=""
ORCA_TASK_ID=""
ORCA_COORDINATOR_HANDLE=""
ORCA_SUPERVISED_RUN_ID=""    # helper 输出，仅 --orca-supervised 时填
ORCA_SUPERVISED_COORDINATOR_HANDLE=""  # Run 绑定的 PM terminal，用于 consumer fencing
ORCA_SUPERVISED_TASK_ID=""   # helper 输出
ORCA_SUPERVISED_DISPATCH_ID=""  # helper 输出（ctx_xxx）
INSTALL_AUTHORIZATION_SOURCE=""
AUTHORIZED_INSTALL_COMMANDS=()
ALLOWED_SHELL_COMMANDS=()
PYTHON_RUNTIME_SYMLINK=""
EFFECTIVE_ALLOWED_SHELL_COMMANDS=()
ALLOW_PROMPT_ONLY_INSTALL_GUARD=0
INSTALL_GUARD_DEGRADATION_SOURCE=""
INSTALL_GUARD_MODE="hook"
INSTALL_AUTH_JSON=""
AUTHORITY_RECEIPT_FILE=""
AUTHORITY_RECEIPT_SHA256=""
INSTALL_GUARD_SETTINGS_FILE=""
GIT_EXPECTED_NAME=""
GIT_EXPECTED_EMAIL=""
GIT_INTEGRATION_BASE=""
GIT_PUSH_REMOTE="origin"
SAFE_PUSH_COMMAND=""
GUARD_ATTESTATION_FILE=""

# shellcheck source=spawn-worker-flags.sh
source "$SCRIPT_DIR/spawn-worker-flags.sh"
parse_spawn_worker_args "$@"

[ -n "$PROJECT_DIR" ] || { usage; exit 64; }
[ -n "$SESSION" ] || { usage; exit 64; }
command -v git >/dev/null 2>&1 || { echo "ERROR: git is required" >&2; exit 64; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required for dependency install guard; do not install it without user authorization" >&2; exit 64; }

DETECTED_PM_HARNESS=""
detect_pm_harness "$PROJECT_DIR" || exit $?
detected_pm_harness="$DETECTED_PM_HARNESS"
if [ -n "$PM_HARNESS_ASSERTION" ]; then
  asserted_pm_harness=$(canonical_harness_backend "$PM_HARNESS_ASSERTION") || {
    echo "ERROR: unsupported --pm-harness: $PM_HARNESS_ASSERTION (fail-closed)" >&2
    exit 64
  }
  if [ "$asserted_pm_harness" != "$detected_pm_harness" ]; then
    echo "ERROR: --pm-harness=$asserted_pm_harness conflicts with detected harness=$detected_pm_harness; assertion cannot elevate authority (fail-closed)" >&2
    exit 64
  fi
fi
enforce_harness_backend_policy_chain \
  "$detected_pm_harness" "$PM_HARNESS_CHAIN_JSON" "$WORKER_BACKEND" || exit $?
PM_HARNESS_SOURCE=${PM_HARNESS_SOURCE:-verified_runtime}
printf 'SPAWN_WORKER_HARNESS_POLICY: pm=%s worker=%s allowed=%s chain=%s source=%s\n' \
  "$PM_HARNESS" "$WORKER_BACKEND_CANONICAL" "$PM_ALLOWED_WORKER_BACKENDS" \
  "$PM_HARNESS_CHAIN_JSON" "$PM_HARNESS_SOURCE"

if [ "${#AUTHORIZED_INSTALL_COMMANDS[@]}" -gt 0 ] && [ -z "$INSTALL_AUTHORIZATION_SOURCE" ]; then
  echo "ERROR: --allow-install-command requires --install-authorization-source (fail-closed)" >&2
  exit 64
fi
if [ "${#AUTHORIZED_INSTALL_COMMANDS[@]}" -eq 0 ] && [ -n "$INSTALL_AUTHORIZATION_SOURCE" ]; then
  echo "ERROR: --install-authorization-source requires at least one --allow-install-command" >&2
  exit 64
fi
for install_command in "${AUTHORIZED_INSTALL_COMMANDS[@]}"; do
  [ -n "$install_command" ] || { echo "ERROR: --allow-install-command cannot be empty" >&2; exit 64; }
done
for shell_command in "${ALLOWED_SHELL_COMMANDS[@]}"; do
  [ -n "$shell_command" ] || { echo "ERROR: --allow-shell-command cannot be empty" >&2; exit 64; }
done
for verify_command in "${VERIFY_COMMANDS[@]}"; do
  if python3 "$SCRIPT_DIR/dependency-install-guard.py" --classify-install "$verify_command"; then
    echo "ERROR: --verify-cmd may acquire/install dependencies and cannot receive implicit Shell authority: $verify_command; use a separate explicitly authorized install step (fail-closed)" >&2
    exit 64
  fi
done
if [ "$ALLOW_PROMPT_ONLY_INSTALL_GUARD" -eq 1 ] && [ -z "$INSTALL_GUARD_DEGRADATION_SOURCE" ]; then
  echo "ERROR: --allow-prompt-only-install-guard requires a non-empty authorization source" >&2
  exit 64
fi
git_identity_field_count=0
[ -n "$GIT_EXPECTED_NAME" ] && git_identity_field_count=$((git_identity_field_count + 1))
[ -n "$GIT_EXPECTED_EMAIL" ] && git_identity_field_count=$((git_identity_field_count + 1))
[ -n "$GIT_INTEGRATION_BASE" ] && git_identity_field_count=$((git_identity_field_count + 1))
if [ "$git_identity_field_count" -ne 0 ] && [ "$git_identity_field_count" -ne 3 ]; then
  echo "ERROR: --git-expected-name, --git-expected-email and --git-integration-base must be provided together (fail-closed)" >&2
  exit 64
fi

case "$WORKER_BACKEND" in
  claude-code|claude_code|codebuddy|qoderwork-cn|qoderclicn)
    INSTALL_GUARD_MODE="hook"
    ;;
  codex)
    if [ "$ALLOW_PROMPT_ONLY_INSTALL_GUARD" -ne 1 ]; then
      echo "ERROR: backend $WORKER_BACKEND has no configured PreToolUse install guard; explicit --allow-prompt-only-install-guard is required (fail-closed)" >&2
      exit 64
    fi
    INSTALL_GUARD_MODE="prompt_only_degraded"
    ;;
  *)
    echo "ERROR: unknown backend cannot prove dependency-install enforcement: $WORKER_BACKEND" >&2
    exit 64
    ;;
esac

PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd -P)

# v2.0：轻量模式判定（SKILL §2.1.1）。
# 1. --no-worktree 显式：LIGHTWEIGHT_MODE=1，BRANCH 不必填。
# 2. --project 不是 git 仓 且用户没显式 --worktree/--branch：自动切轻量并打印
#    SPAWN_WORKER_LIGHTWEIGHT_AUTO（向后兼容 SKILL 文档承诺，不破老调用）。
# 3. --project 是 git 仓 且用户没 --no-worktree：保持默认 worktree 模式，BRANCH 必填。
PROJECT_IS_GIT=0
if git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  PROJECT_IS_GIT=1
fi
if [ "$LIGHTWEIGHT_OVERRIDE" -eq 0 ] && [ "$PROJECT_IS_GIT" -eq 0 ] && [ -z "$WORKTREE" ] && [ -z "$BRANCH" ]; then
  LIGHTWEIGHT_MODE=1
  LIGHTWEIGHT_AUTO=1
  echo "SPAWN_WORKER_LIGHTWEIGHT_AUTO: $PROJECT_DIR is not a git work tree, switching to lightweight mode"
fi

if [ "$LIGHTWEIGHT_MODE" -eq 1 ]; then
  # 轻量模式：清空 branch，把 worker cwd 直接指向 project_dir；--worktree 可显式覆盖子目录
  BRANCH=""
  if [ -z "$WORKTREE" ]; then
    WORKTREE="$PROJECT_DIR"
  fi
else
  # 默认 worktree 模式：--branch 必填
  [ -n "$BRANCH" ] || { echo "ERROR: --branch is required in worktree mode (or pass --no-worktree for lightweight)" >&2; usage; exit 64; }
fi

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
INSTALL_AUTH_FILE="$SESSION_CONTEXT/INSTALL_AUTHORIZATION.json"
if [ -z "$COMMAND" ]; then
  case "$WORKER_BACKEND_CANONICAL" in
    claude-code) COMMAND="claude" ;;
    codex) COMMAND="codex" ;;
    codebuddy) COMMAND="codebuddy" ;;
    qoderwork-cn) COMMAND="qoderclicn" ;;
    *) echo "ERROR: no default command for backend=$WORKER_BACKEND_CANONICAL" >&2; exit 64 ;;
  esac
  echo "SPAWN_WORKER_COMMAND_DEFAULT: backend=$WORKER_BACKEND_CANONICAL command=$COMMAND"
fi

# Bind the declared backend to the executable that will actually be launched.
# This identity gate is independent of the dependency install guard: degrading
# hooks to prompt-only can never authorize a differently labelled executable.
validate_worker_command_backend() {
  python3 "$SCRIPT_DIR/validate-worker-command.py" \
    --backend "$WORKER_BACKEND_CANONICAL" \
    --command "$COMMAND" \
    --trusted-claude-wrapper "$SCRIPT_DIR/claude-provider-env.sh"
}

if ! WORKER_COMMAND_SHA256=$(validate_worker_command_backend); then
  echo "ERROR: worker backend/command identity mismatch: $WORKER_COMMAND_SHA256 (fail-closed)" >&2
  exit 64
fi
printf 'SPAWN_WORKER_COMMAND_POLICY: backend=%s command_sha256=%s\n' \
  "$WORKER_BACKEND_CANONICAL" "$WORKER_COMMAND_SHA256"

# shellcheck source=spawn-worker-provider-lease.sh
source "$SCRIPT_DIR/spawn-worker-provider-lease.sh"

# Must happen before any branch/worktree/session side effect. EXIT releases only
# the provisional lease; a successful launch finalizes it and disables the trap.
acquire_provider_lease
if [ "$PROVIDER_LEASE_ACQUIRED" -eq 1 ]; then
  trap release_provisional_provider_lease EXIT
fi

# Claude Code 的 minimal/safe/config-source 模式可能跳过 local PreToolUse hook。
# 用 shlex 解析 wrapper 后的完整 command；无法证明含 claude 或 local settings 也 fail-closed。
claude_hook_disable_reason() {
  python3 - "$COMMAND" <<'PY'
import os, shlex, sys
command = sys.argv[1]
try:
    tokens = shlex.split(command, posix=True)
except ValueError as exc:
    print(f"unparseable command: {exc}")
    raise SystemExit(0)
if not any(os.path.basename(token) == "claude" for token in tokens):
    print("command does not expose a claude executable token")
    raise SystemExit(0)
for flag in ("--bare", "--safe-mode"):
    if flag in tokens:
        print(f"{flag} skips or may skip hooks")
        raise SystemExit(0)
if "CLAUDE_CODE_SIMPLE=1" in tokens:
    print("CLAUDE_CODE_SIMPLE=1 skips hooks")
    raise SystemExit(0)
sources = None
for index, token in enumerate(tokens):
    if token == "--setting-sources":
        if index + 1 >= len(tokens):
            print("--setting-sources is missing its value")
            raise SystemExit(0)
        sources = tokens[index + 1]
    elif token.startswith("--setting-sources="):
        sources = token.split("=", 1)[1]
if sources is not None and "local" not in {item.strip() for item in sources.split(",")}:
    print(f"--setting-sources excludes local ({sources})")
    raise SystemExit(0)
raise SystemExit(1)
PY
}

# v1.20.2 Task-019：检测 claude-code command 是否含 --bare token（provider-isolation 必需）。
# 用于在 install-guard fail-closed 分支里区分 --bare（自动降级）vs --safe-mode/setting-sources（仍 fail-closed）。
# 在 if 条件里调用；返回 0 = 含 --bare，非 0 = 不含。
claude_command_has_bare() {
  python3 - "$COMMAND" <<'PY'
import shlex, sys
try:
    tokens = shlex.split(sys.argv[1], posix=True)
except ValueError:
    raise SystemExit(1)
raise SystemExit(0 if "--bare" in tokens else 1)
PY
}

if [ "$INSTALL_GUARD_MODE" = "hook" ] && \
   { [ "$WORKER_BACKEND" = "claude-code" ] || [ "$WORKER_BACKEND" = "claude_code" ]; } && \
   hook_disable_reason=$(claude_hook_disable_reason); then
  if [ "$ALLOW_PROMPT_ONLY_INSTALL_GUARD" -eq 1 ]; then
    INSTALL_GUARD_MODE="prompt_only_degraded"
  elif [ "$CLAUDE_CODE_BARE_AUTO_DEGRADE" -eq 1 ] && claude_command_has_bare; then
    # v1.20.2 Task-019：claude-code + provider-isolation 默认 --bare（render-runtime-profile.sh）
    # 与 install-guard fail-closed 互斥。检测到 --bare 自动降级 prompt-only + 内置来源，
    # 不再要求 PM 手写 --allow-prompt-only-install-guard。PM 仍 review diff 兜底（SKILL §6）。
    ALLOW_PROMPT_ONLY_INSTALL_GUARD=1
    INSTALL_GUARD_DEGRADATION_SOURCE="claude-code provider-isolation 默认 --bare（render-runtime-profile.sh）跳过 PreToolUse hook；install-guard 自动降级 prompt-only，PM 仍 review diff 兜底（SKILL §6 / Task-019 / DEC-112 follow-up）"
    INSTALL_GUARD_MODE="prompt_only_degraded"
    echo "SPAWN_WORKER_BARE_AUTO_DEGRADE: claude-code --bare detected, install-guard auto prompt_only_degraded (source recorded); --safe-mode / setting-sources / no-claude-token 仍 fail-closed"
  else
    echo "ERROR: Claude Code command cannot prove local PreToolUse hook enforcement: $hook_disable_reason; fix the command, pass --allow-prompt-only-install-guard, or this non-bare disable (--safe-mode/--setting-sources/missing token) requires explicit --allow-prompt-only-install-guard (fail-closed)" >&2
    exit 64
  fi
fi

run() {
  printf 'SPAWN_WORKER_RUN: %s\n' "$*"
  [ "$DRY_RUN" -eq 1 ] || "$@"
}

array_to_json() {
  if [ "$#" -eq 0 ]; then
    printf '[]\n'
  else
    printf '%s\n' "$@" | jq -R . | jq -s .
  fi
}

# shellcheck source=spawn-worker-orca.sh
source "$SCRIPT_DIR/spawn-worker-orca.sh"

# v2.1（DEC-114）：ORCA 终端模式 auto-detect。必须在 detect_orca_mode / orca_worktree_create /
# orca_terminal_create_and_send 三个 helper 定义之后调用（bash 函数先定义后调用）。
# 命中 auto 时：
#   - ORCA_MODE=auto
#   - ORCA_WORKTREE_PATH = PROJECT_DIR 的 git toplevel
#   - ORCA_WORKTREE_ID 待 orca_worktree_create() 填充（worktree 创建阶段）
#   - ORCA_TERMINAL_HANDLE 待 orca_terminal_create_and_send() 填充（tmux 启动阶段）
#   - ORCA_APP_VERSION / ORCA_CAPABILITIES_JSON 已从 `orca status --json` 抓取
detect_orca_mode  # 直接调，设全局 ORCA_MODE + ORCA_APP_VERSION/CAPABILITIES_JSON/WORKTREE_PATH（不用 $() 子 shell）
if [ "$ORCA_MODE" = "missing_orca" ]; then
  exit 64
fi
if [ "$ORCA_SUPERVISED" -eq 1 ]; then
  [ -n "$TASK_SPEC" ] || [ -n "$ORCA_TASK_ID" ] || { echo "ERROR: --orca-supervised requires --task-spec or --orca-task-id" >&2; exit 64; }
  [ -z "$ORCA_TASK_ID" ] || [ -n "$ORCA_RUN_ID" ] || { echo "ERROR: --orca-task-id requires --orca-run-id" >&2; exit 64; }
  [ -z "$ORCA_TASK_ID" ] || [ -n "$ORCA_COORDINATOR_HANDLE" ] || { echo "ERROR: --orca-task-id requires --orca-coordinator-handle from the Wave receipt" >&2; exit 64; }
  [ "$ORCA_MODE" = "auto" ] || { echo "ERROR: --orca-supervised requires a current Orca-managed project" >&2; exit 64; }
  has_orchestration=$(printf '%s' "$ORCA_CAPABILITIES_JSON" | jq -r 'any(. == "orchestration.contract.v1")' 2>/dev/null)
  [ "$has_orchestration" = "true" ] || { echo "ERROR: Orca runtime lacks orchestration.contract.v1" >&2; exit 64; }
fi
if [ "$ORCA_MODE" != "auto" ] && ! command -v tmux >/dev/null 2>&1; then
  echo "ERROR: tmux is required outside Orca terminal mode" >&2
  exit 64
fi

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
    # v1.20.3 Task-026：codebuddy/qoderwork-cn/qoderclicn 默认 PERMISSION_AUTO=0（只 bg 不 sync）。
    # acceptEdits 仍弹 dialog（references/08 §14.1），同步监控空等浪费 + spawn-worker 主进程撞 PM Bash 2min timeout
    # （v1.20.2 W2 实战：trust_auto 30s + permission_auto 60s + checkout ~30s ≈ 120s 撞 120s，被 SIGTERM 后
    # bg 段未启 → dialog 卡死）。bg 段（permission_auto_bg setsid）独立处理 dialog，不依赖 sync。
    case "$WORKER_BACKEND" in
      claude-code|claude_code|codebuddy|qoderwork-cn|qoderclicn) PERMISSION_AUTO=0 ;;
      *) PERMISSION_AUTO=1 ;;
    esac
  fi
  if [ "$PERMISSION_AUTO_BG_OVERRIDE" -eq 0 ]; then
    case "$WORKER_BACKEND" in
      claude-code|claude_code) PERMISSION_AUTO_BG=0 ;;
      *) PERMISSION_AUTO_BG=1 ;;
    esac
  fi
  # v1.20.2 Task-020：external imports dialog 是 claude-code 特有（CLAUDE.md @import 触发），
  # 其他 backend 无此 dialog。claude-code 默认开（即使 trust/permission 关），其他默认关。
  if [ "$EXTERNAL_IMPORTS_AUTO_OVERRIDE" -eq 0 ]; then
    case "$WORKER_BACKEND" in
      claude-code|claude_code) EXTERNAL_IMPORTS_AUTO=1 ;;
      *) EXTERNAL_IMPORTS_AUTO=0 ;;
    esac
  fi
}
resolve_backend_defaults

# install-guard 的 authority receipt 依赖 git_common_dir，仅在 git 仓（worktree 模式）下计算。
# 轻量模式（非 git 项目）无 git 可绑：AUTHORITY_RECEIPT_FILE 留空，write_authority_receipt 自动跳过。
# git 仓判定由下方 worktree-setup 的 else 分支（PROJECT_IS_GIT 检查）兜底，此处不再重复 exit。
if [ "$PROJECT_IS_GIT" -eq 1 ]; then
  git_common_dir=$(git -C "$PROJECT_DIR" rev-parse --git-common-dir)
  case "$git_common_dir" in
    /*) ;;
    *) git_common_dir="$PROJECT_DIR/$git_common_dir" ;;
  esac
  git_common_dir=$(cd "$git_common_dir" && pwd -P)
  AUTHORITY_RECEIPT_FILE="$git_common_dir/agent-authority/$SESSION.json"
  if [ "$INSTALL_GUARD_MODE" = "hook" ]; then
    GUARD_ATTESTATION_FILE="$git_common_dir/agent-authority/$SESSION.hook-attested.json"
  fi
fi
if [ "$ORCA_MODE" != "auto" ] && tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "ERROR: tmux session already exists: $SESSION" >&2
  exit 1
fi

if [ "$LIGHTWEIGHT_MODE" -eq 1 ]; then
  # 轻量模式（SKILL §2.1.1）：不建 worktree、不切分支、不验 base ref；
  # WORKTREE 已指向 PROJECT_DIR（或 --worktree 覆盖的子目录）。
  BASE_SHA=""
  echo "SPAWN_WORKER_LIGHTWEIGHT: skip git worktree setup, worker cwd=$WORKTREE"
elif [ "$ORCA_MODE" = "auto" ]; then
  # v2.1（DEC-114）：ORCA 终端模式。每次都新建独立 ORCA worktree（--no-parent），
  # 不复用 git worktree（ORCA worktree 是独立概念，由 ORCA 桌面端跟踪）。
  # ORCA worktree 的 git branch 名不能含 '/'（ORCA --name 既作显示名又作 branch 名），
  # 必须用 safe_branch（BRANCH 的 safe 化版本）。把 BRANCH 统一设成 safe_branch，
  # 让下游 Isolation Gate / METADATA / orca --name 全部一致。
  BRANCH="$safe_branch"
  orca_base="$BASE_REF"
  if git -C "$PROJECT_DIR" show-ref --verify --quiet "refs/heads/$BRANCH" 2>/dev/null \
     || git -C "$PROJECT_DIR" show-ref --verify --quiet "refs/remotes/origin/$BRANCH" 2>/dev/null; then
    orca_base="$BRANCH"
  fi
  ORCA_WORKTREE_ID=$(orca_worktree_create "$BRANCH" "$orca_base")
  # ORCA worktree create 后实际 path 可能不是 PROJECT_DIR（ORCA 默认放 ~/orca/workspaces/<name>）；
  # 用 ORCA_WORKTREE_ID 解析的真实 path 覆盖 WORKTREE + ORCA_WORKTREE_PATH。
  if [ -n "$ORCA_WORKTREE_ID" ] && [ "$ORCA_WORKTREE_ID" != "orca_worktree_id_placeholder" ]; then
    orca_actual_path="${ORCA_WORKTREE_ID#*::}"
    if [ -n "$orca_actual_path" ] && [ -d "$orca_actual_path" ]; then
      WORKTREE="$orca_actual_path"
      ORCA_WORKTREE_PATH="$orca_actual_path"
    fi
  fi
  SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
  METADATA_FILE="$SESSION_CONTEXT/METADATA.json"
  INSTALL_AUTH_FILE="$SESSION_CONTEXT/INSTALL_AUTHORIZATION.json"
  BASE_SHA=$(git -C "$WORKTREE" rev-parse HEAD 2>/dev/null || echo "")
  echo "SPAWN_WORKER_ORCA_WORKTREE: id=$ORCA_WORKTREE_ID path=$WORKTREE"
else
  # 默认 worktree 模式：--project 必须是 git 仓，base ref / 分支都参与
  if [ "$PROJECT_IS_GIT" -eq 0 ]; then
    echo "ERROR: --project is not a git work tree: $PROJECT_DIR (pass --no-worktree for lightweight mode)" >&2
    exit 64
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
fi

if [ "$DRY_RUN" -eq 0 ]; then
  WORKTREE=$(cd "$WORKTREE" && pwd -P)
  SESSION_CONTEXT="$WORKTREE/.claude/agent-sessions/$SESSION"
  METADATA_FILE="$SESSION_CONTEXT/METADATA.json"
  INSTALL_AUTH_FILE="$SESSION_CONTEXT/INSTALL_AUTHORIZATION.json"
fi

# Task-045 / G31：worktree 创建并真实化后，按项目类型补偿依赖。
# Orca worktree 落在 ~/orca/workspaces/（独立路径树，不在主仓父链）→ Node 项目软链
# 主仓 node_modules，否则 npm/vitest/tsc 向上解析找不到依赖、worker 无法自验。
ensure_worktree_deps

run mkdir -p "$SESSION_CONTEXT"

if [ "$git_identity_field_count" -eq 3 ]; then
  safe_push_script="$SCRIPT_DIR/../../git-workflow/scripts/safe-push.sh"
  [ -x "$safe_push_script" ] || {
    echo "ERROR: identity-bound safe-push script is missing or not executable: $safe_push_script" >&2
    exit 64
  }
  printf -v SAFE_PUSH_COMMAND 'bash %q --repo %q --base %q --remote %q --branch %q --expected-name %q --expected-email %q' \
    "$safe_push_script" "$WORKTREE" "$GIT_INTEGRATION_BASE" "$GIT_PUSH_REMOTE" "$BRANCH" \
    "$GIT_EXPECTED_NAME" "$GIT_EXPECTED_EMAIL"
fi

write_install_authorization() {
  local commands_json shell_commands_json
  # Task-046 / G31：PM 未显式传 --verify-cmd 时，按 package.json scripts 注入
  # 默认 verify 命令（npm run typecheck/lint/test/build）到 VERIFY_COMMANDS，
  # 让 worker 默认能跑验证门（否则 allowed_shell 仅 3 条，worker 无法自验）。
  inject_default_verify_commands
  commands_json=$(array_to_json "${AUTHORIZED_INSTALL_COMMANDS[@]}")
  EFFECTIVE_ALLOWED_SHELL_COMMANDS=(
    "pwd"
    "git branch --show-current"
    "git status --short"
  )
  [ -z "$SAFE_PUSH_COMMAND" ] || EFFECTIVE_ALLOWED_SHELL_COMMANDS+=("$SAFE_PUSH_COMMAND")
  EFFECTIVE_ALLOWED_SHELL_COMMANDS+=("${VERIFY_COMMANDS[@]}" "${ALLOWED_SHELL_COMMANDS[@]}")
  shell_commands_json=$(array_to_json "${EFFECTIVE_ALLOWED_SHELL_COMMANDS[@]}" | jq 'unique')
  INSTALL_AUTH_JSON=$(jq -cn \
    --arg schema "multi-agent-orchestration.install-authorization.v1" \
    --arg policy "deny_by_default" \
    --arg source "$INSTALL_AUTHORIZATION_SOURCE" \
    --argjson commands "$commands_json" \
    --argjson shell_commands "$shell_commands_json" \
    '{
      schema: $schema,
      policy: $policy,
      authorization_source: $source,
      authorized_commands: $commands,
      allowed_shell_commands: $shell_commands
    }')
  echo "SPAWN_WORKER_INSTALL_AUTH: $INSTALL_AUTH_FILE mode=$INSTALL_GUARD_MODE"
  if [ "$DRY_RUN" -eq 1 ]; then
    return 0
  fi
  printf '%s\n' "$INSTALL_AUTH_JSON" > "$INSTALL_AUTH_FILE"
}

write_install_authorization

write_authority_receipt() {
  local receipt_dir receipt_tmp created_at
  AUTHORITY_RECEIPT_SHA256=$(printf '%s' "$INSTALL_AUTH_JSON" | python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')
  echo "SPAWN_WORKER_AUTHORITY_RECEIPT: $AUTHORITY_RECEIPT_FILE sha256=$AUTHORITY_RECEIPT_SHA256"
  if [ "$DRY_RUN" -eq 1 ]; then
    return 0
  fi
  receipt_dir=$(dirname "$AUTHORITY_RECEIPT_FILE")
  mkdir -p "$receipt_dir"
  [ ! -e "$AUTHORITY_RECEIPT_FILE" ] || {
    echo "ERROR: PM authority receipt already exists for session $SESSION; choose a unique session id (fail-closed)" >&2
    return 1
  }
  created_at=$(date -u "+%Y-%m-%dT%H:%M:%SZ")
  receipt_tmp="$AUTHORITY_RECEIPT_FILE.tmp.$$"
  umask 077
  jq -n \
    --arg schema "multi-agent-orchestration.authority-receipt.v1" \
    --arg created_at "$created_at" \
    --arg session "$SESSION" \
    --arg worktree "$WORKTREE" \
    --arg branch "$BRANCH" \
    --arg mode "$INSTALL_GUARD_MODE" \
    --arg degradation_source "$INSTALL_GUARD_DEGRADATION_SOURCE" \
    --arg authorization_sha256 "$AUTHORITY_RECEIPT_SHA256" \
    --argjson authorization "$INSTALL_AUTH_JSON" \
    '{
      schema: $schema,
      created_at: $created_at,
      session: $session,
      worktree: $worktree,
      branch: $branch,
      install_guard_mode: $mode,
      degradation_source: $degradation_source,
      authorization_sha256: $authorization_sha256,
      authorization_snapshot: $authorization
    }' > "$receipt_tmp"
  if ! ln "$receipt_tmp" "$AUTHORITY_RECEIPT_FILE" 2>/dev/null; then
    rm -f "$receipt_tmp"
    echo "ERROR: could not atomically create PM authority receipt: $AUTHORITY_RECEIPT_FILE" >&2
    return 1
  fi
  rm -f "$receipt_tmp"
}

# authority receipt 仅在 git 仓（worktree 模式）下生成；轻量模式 AUTHORITY_RECEIPT_FILE 为空，跳过。
if [ -n "$AUTHORITY_RECEIPT_FILE" ]; then
  write_authority_receipt
fi

# shellcheck source=spawn-worker-metadata.sh
source "$SCRIPT_DIR/spawn-worker-metadata.sh"

# Read/send one worker TUI through the active control plane. Orca external CLI
# terminals do not inherit tmux watchers, so CodeBuddy/Qoder confirmation dialogs
# must be observed and answered through terminal read/send.
worker_session_content() {
  local session="$1"
  if [ "$ORCA_MODE" = "auto" ]; then
    [ -n "$ORCA_TERMINAL_HANDLE" ] || return 1
    orca_cli terminal read --terminal "$ORCA_TERMINAL_HANDLE" --limit 50 --json 2>/dev/null \
      | jq -r '(.result.terminal.tail // .result.tail // []) | .[]? // empty' 2>/dev/null
  else
    tmux has-session -t "$session" 2>/dev/null || return 1
    tmux capture-pane -t "$session" -p -S -50 2>/dev/null
  fi
}

worker_session_send_choice() {
  local session="$1" choice="$2"
  if [ "$ORCA_MODE" = "auto" ]; then
    orca_cli terminal send --terminal "$ORCA_TERMINAL_HANDLE" --text "$choice" --enter --json >/dev/null
  else
    tmux send-keys -t "$session" "$choice"
  fi
}

worker_session_send_enter() {
  local session="$1"
  if [ "$ORCA_MODE" = "auto" ]; then
    orca_cli terminal send --terminal "$ORCA_TERMINAL_HANDLE" --text "" --enter --json >/dev/null
  else
    tmux send-keys -t "$session" Enter
  fi
}

# Trust folder auto-accept for interactive codebuddy/qoder CLI workers.
# Default: auto-select "Trust folder and all subdirectories" (option 3) to
# avoid both the initial trust prompt AND subsequent subdir trust prompts.
# Polls the tmux pane for trust dialog text, then sends Down×3+Enter.
trust_auto() {
  local session="$1"
  local max_wait=30
  # v1.20.3 Task-026：codebuddy/qoderwork-cn/qoderclicn 缩短 trust_auto timeout（acceptEdits 不弹 trust dialog，30s 空等浪费）
  case "$WORKER_BACKEND" in
    codebuddy|qoderwork-cn|qoderclicn) max_wait=15 ;;
  esac
  local poll_interval=1
  local waited=0

  while [ "$waited" -lt "$max_wait" ]; do
    if ! content=$(worker_session_content "$session"); then
      return 1  # session died, trust-auto skipped
    fi

    # codebuddy trust dialog:
    #   Do you want to proceed?
    #   1. Trust folder only / 2. Trust parent folder / 3. Trust folder and all subdirectories / 4. No, exit
    if echo "$content" | grep -q "Trust folder and all subdirectories"; then
      echo "SPAWN_WORKER_TRUST_AUTO: trust dialog detected, selecting Trust folder and all subdirectories (option 3)"
      if [ "$ORCA_MODE" = "auto" ]; then
        worker_session_send_choice "$session" "3"
      else
        tmux send-keys -t "$session" Down Down Down Enter
      fi
      sleep 2  # wait for trust to take effect
      return 0
    fi

    # Generic fallback: match other trust/Do you trust dialogs（v1.20.4 Task-031：backend-specific 选项处理）
    # codebuddy 4 选项 dialog 已被上面专门 match（"Trust folder and all subdirectories"）捕获；
    # 这里捕获 qoderclicn 等 2 选项 dialog（1=Trust folder / 2=Don't trust and exit，默认高亮 option 2 Don't trust）。
    if echo "$content" | grep -qE "Trust folder|Do you trust" 2>/dev/null; then
      case "$WORKER_BACKEND" in
        qoderwork-cn|qoderclicn)
          # qoderclicn 2 选项 dialog：发数字键 "1" 选 Trust folder（默认高亮 option 2 Don't trust，不能 Enter；与 permission_auto "2" 同数字键模式）
          echo "SPAWN_WORKER_TRUST_AUTO: trust dialog detected (qoder 2-option), selecting option 1 Trust folder (key '1')"
          worker_session_send_choice "$session" "1"
          ;;
        *)
          # 其他 backend 保守沿用 Down×3+Enter（codebuddy 4 选项选 option 3 的旧行为；新 backend 真机验证后按需加 case）
          echo "SPAWN_WORKER_TRUST_AUTO: trust dialog detected (generic), selecting last trust option (Down×3+Enter)"
          if [ "$ORCA_MODE" = "auto" ]; then
            worker_session_send_choice "$session" "3"
          else
            tmux send-keys -t "$session" Down Down Down Enter
          fi
          ;;
      esac
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
    if ! content=$(worker_session_content "$session"); then
      return 1  # session died, permission-auto skipped
    fi

    # Match "Do you want to proceed?" dialog with session-allow option:
    #   Do you want to proceed?
    #     1. Yes
    #   > 2. Yes, and don't ask again for session (shift + tab)
    #     3. No, and tell CodeBuddy what to do differently (escape)
    if echo "$content" | grep -q "Do you want to proceed"; then
      echo "SPAWN_WORKER_PERMISSION_AUTO: 'Do you want to proceed' dialog detected, selecting session-allow (option 2, key '2')"
      worker_session_send_choice "$session" "2"
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
    if ! content=$(worker_session_content "$session"); then
      echo "SPAWN_WORKER_PERMISSION_BG: session $session ended after ${waited}s, watcher exits (hits=$hits)"
      return 0
    fi

    if echo "$content" | grep -q "Do you want to proceed"; then
      hits=$((hits + 1))
      echo "SPAWN_WORKER_PERMISSION_BG: 'Do you want to proceed' detected (hit $hits at ${waited}s), sending '2'"
      worker_session_send_choice "$session" "2"
      sleep 2  # 让 dialog 关闭
    fi

    sleep "$poll_interval"
    waited=$((waited + poll_interval))
  done

  echo "SPAWN_WORKER_PERMISSION_BG: max_wait ${max_wait}s reached, watcher exits (hits=$hits)"
  return 0
}

# v1.20.2 Task-020：监控 claude-code worker 首启的 "external imports" dialog。
# CLAUDE.md 用 @import 引外部文件时，claude 首启弹 "Yes allow external imports" dialog（option 1 默认选中）。
# v1.18.4 默认关 trust/permission 不覆盖此类；本函数独立监控，option 1 放行
# （用户已在 CLAUDE.md @import = 已认可的全局规则；不自动 allow 未审视的运行期 import）。
# 默认只 claude-code 启用（resolve_backend_defaults）；--no-external-imports-auto opt-out。
external_imports_auto() {
  local session="$1"
  local max_wait="${EXTERNAL_IMPORTS_MAX_WAIT:-120}"
  local poll_interval=2
  local waited=0

  while [ "$waited" -lt "$max_wait" ]; do
    if ! content=$(worker_session_content "$session"); then
      return 1  # session died, external-imports-auto skipped
    fi
    if echo "$content" | grep -qiE "allow external import|external import"; then
      echo "SPAWN_WORKER_EXTERNAL_IMPORTS_AUTO: 'external imports' dialog detected, selecting option 1 (Yes allow, default)"
      worker_session_send_enter "$session"
      sleep 2
      return 0
    fi
    sleep "$poll_interval"
    waited=$((waited + poll_interval))
  done
  echo "SPAWN_WORKER_EXTERNAL_IMPORTS_AUTO: no external imports dialog within ${max_wait}s, continuing"
  return 0
}

# 将一个 PreToolUse command hook 合并进现有 settings.local.json，不覆盖项目已有 hooks。
merge_pretool_hook() {
  local settings_file="$1"
  local matcher="$2"
  local hook_command="$3"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "SPAWN_WORKER_HOOK_DRY_RUN: file=$settings_file matcher=$matcher command=$hook_command"
    return 0
  fi

  mkdir -p "$(dirname "$settings_file")"
  local input_file="$settings_file"
  local empty_file=""
  if [ ! -f "$input_file" ]; then
    empty_file=$(mktemp "${TMPDIR:-/tmp}/worker-settings.XXXXXX")
    printf '{}\n' > "$empty_file"
    input_file="$empty_file"
  fi

  local tmp_file="${settings_file}.tmp.$$"
  if ! jq \
    --arg matcher "$matcher" \
    --arg command "$hook_command" \
    '(.hooks.PreToolUse // []) as $existing
    | .hooks = (.hooks // {})
    | .hooks.PreToolUse = (
        ($existing
          | map(.hooks = ((.hooks // []) | map(select(.command != $command))))
          | map(select((.hooks | length) > 0)))
        + [{matcher: $matcher, hooks: [{type: "command", command: $command}]}]
      )' "$input_file" > "$tmp_file"; then
    rm -f "$tmp_file"
    [ -z "$empty_file" ] || rm -f "$empty_file"
    echo "ERROR: invalid settings JSON; refusing to install worker guard: $settings_file" >&2
    return 1
  fi
  mv "$tmp_file" "$settings_file"
  [ -z "$empty_file" ] || rm -f "$empty_file"
  echo "SPAWN_WORKER_HOOK_SETTINGS: $settings_file matcher=$matcher"
}

# 默认安装依赖安装/环境写入硬门禁。精确命令只有同时带可审计授权来源才放行。
dependency_install_guard_setup() {
  if [ "$INSTALL_GUARD_MODE" = "prompt_only_degraded" ]; then
    echo "SPAWN_WORKER_INSTALL_GUARD_DEGRADED: backend=$WORKER_BACKEND source=$INSTALL_GUARD_DEGRADATION_SOURCE" >&2
    return 0
  fi

  local guard_hook="$SCRIPT_DIR/dependency-install-guard-hook.sh"
  local guard_py="$SCRIPT_DIR/dependency-install-guard.py"
  if [ ! -f "$guard_hook" ] || [ ! -f "$guard_py" ]; then
    echo "ERROR: dependency install guard files are missing (fail-closed)" >&2
    return 1
  fi

  local auth_q auth_b64 auth_b64_q backend_q receipt_q settings_q attestation_q
  case "$WORKER_BACKEND" in
    claude-code|claude_code) INSTALL_GUARD_SETTINGS_FILE="$WORKTREE/.claude/settings.local.json" ;;
    codebuddy) INSTALL_GUARD_SETTINGS_FILE="$WORKTREE/.codebuddy/settings.local.json" ;;
    qoderwork-cn|qoderclicn) INSTALL_GUARD_SETTINGS_FILE="$WORKTREE/.qoder/settings.local.json" ;;
    *)
      echo "ERROR: backend lost dependency install guard routing: $WORKER_BACKEND" >&2
      return 1
      ;;
  esac
  printf -v auth_q '%q' "$INSTALL_AUTH_FILE"
  auth_b64=$(printf '%s' "$INSTALL_AUTH_JSON" | base64 | tr -d '\r\n')
  printf -v auth_b64_q '%q' "$auth_b64"
  printf -v backend_q '%q' "${WORKER_BACKEND:-claude-code}"
  printf -v receipt_q '%q' "$AUTHORITY_RECEIPT_FILE"
  printf -v settings_q '%q' "$INSTALL_GUARD_SETTINGS_FILE"
  printf -v attestation_q '%q' "$GUARD_ATTESTATION_FILE"
  COMMAND="env WORKER_INSTALL_AUTH_FILE=$auth_q WORKER_INSTALL_AUTH_B64=$auth_b64_q WORKER_AUTHORITY_RECEIPT_FILE=$receipt_q WORKER_GUARD_SETTINGS_FILE=$settings_q WORKER_GUARD_ATTESTATION_FILE=$attestation_q WORKER_GUARD_BACKEND=$backend_q $COMMAND"
  if [ -n "$GIT_EXPECTED_NAME" ]; then
    local git_name_q git_email_q
    printf -v git_name_q '%q' "$GIT_EXPECTED_NAME"
    printf -v git_email_q '%q' "$GIT_EXPECTED_EMAIL"
    COMMAND="env GIT_AUTHOR_NAME=$git_name_q GIT_AUTHOR_EMAIL=$git_email_q GIT_COMMITTER_NAME=$git_name_q GIT_COMMITTER_EMAIL=$git_email_q $COMMAND"
  fi

  local hook_command
  printf -v hook_command "bash '%s'" "$guard_hook"
  case "$WORKER_BACKEND" in
    claude-code|claude_code)
      merge_pretool_hook "$INSTALL_GUARD_SETTINGS_FILE" "Bash|Shell|Terminal|Edit|Write|NotebookEdit" "$hook_command"
      ;;
    codebuddy)
      merge_pretool_hook "$INSTALL_GUARD_SETTINGS_FILE" "Bash|Shell|Terminal|Edit|Write|NotebookEdit" "$hook_command"
      ;;
    qoderwork-cn|qoderclicn)
      merge_pretool_hook "$INSTALL_GUARD_SETTINGS_FILE" "Bash|Shell|Terminal|Edit|Write|NotebookEdit" "$hook_command"
      ;;
    *)
      echo "ERROR: backend lost dependency install guard routing: $WORKER_BACKEND" >&2
      return 1
      ;;
  esac
  echo "SPAWN_WORKER_INSTALL_GUARD: mode=hook policy=deny_by_default"
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

  local hook_command
  printf -v hook_command "bash '%s'" "$scope_guard_hook"

  # Write to codebuddy settings if backend is codebuddy or unspecified
  if [ "$WORKER_BACKEND" = "codebuddy" ] || [ -z "$WORKER_BACKEND" ]; then
    merge_pretool_hook "$WORKTREE/.codebuddy/settings.local.json" \
      "Edit|Write|NotebookEdit" "$hook_command"
  fi

  # Write to qoder settings if backend is qoderwork-cn
  if [ "$WORKER_BACKEND" = "qoderwork-cn" ] || [ "$WORKER_BACKEND" = "qoderclicn" ]; then
    merge_pretool_hook "$WORKTREE/.qoder/settings.local.json" \
      "Edit|Write|NotebookEdit" "$hook_command"
  fi

  return 0
}

dependency_install_guard_setup
scope_guard_setup
write_metadata

exclude_file=$(git -C "$WORKTREE" rev-parse --git-path info/exclude 2>/dev/null || echo "")
if [ "$DRY_RUN" -eq 0 ] && [ -n "$exclude_file" ] && [ -f "$exclude_file" ] && ! grep -qxF ".claude/agent-sessions/" "$exclude_file" 2>/dev/null; then
  printf '\n.claude/agent-sessions/\n' >> "$exclude_file"
fi

# shellcheck source=spawn-worker-launch.sh
source "$SCRIPT_DIR/spawn-worker-launch.sh"
launch_worker_session

if [ "$DRY_RUN" -eq 0 ]; then
  finalize_provider_lease
fi

# Trust-auto + Permission-auto: headless CLI workers need trust-folder permission
# and runtime permission prompts auto-accepted.
# trust_auto: Selects "Trust folder and all subdirectories" (option 3) to avoid
# both the initial trust prompt and subsequent subdir trust prompts.
# permission_auto: Selects "Yes, and don't ask again for session" (option 2)
# for "Do you want to proceed?" runtime prompts (cross-directory access).
# permission_auto_bg (v1.18.3): 后台 watcher 持续 7200s，覆盖同步 60s 窗口外的 dialog。
# v1.18.4: 默认值按 backend 分支（resolve_backend_defaults），claude-code 默认全关省 90s 空等；
# 其他 backend 默认全开。flag --*/--no-* 均可 force override 默认值（详见 usage）。
# Orca external argv terminals仍会出现 CLI 自己的 trust/permission 对话框；上述 watcher
# 用 terminal read/send 处理。tmux 路径继续使用 capture-pane/send-keys。
if [ "$DRY_RUN" -eq 0 ] && [ "$TRUST_AUTO" -eq 1 ]; then
  trust_auto "$SESSION"
fi
if [ "$DRY_RUN" -eq 0 ] && [ "$PERMISSION_AUTO" -eq 1 ]; then
  permission_auto "$SESSION"
fi
if [ "$DRY_RUN" -eq 0 ] && [ "$PERMISSION_AUTO_BG" -eq 1 ]; then
  # v1.20.3.1 hotfix（接 v1.20.2 Task-021）：v1.20.2 用 nohup/setsid（外部 binary）调用
  # permission_auto_bg（spawn-worker.sh bash 函数）是 bug — nohup/setsid 子进程找不到父 shell 函数，
  # 报 command not found，bg watcher 从未启（W2 真机撞坑 + v1.20.3 真机 throwaway 复测 ps 都空）。
  # 修复：v1.18.3 subshell 继承函数模式（subshell fork 继承父 shell 函数定义，能跑）。
  # 已知限制：spawn-worker SIGTERM 时同进程组 bg 会死（v1.18.3 限制）；mitigation = Task-026 让
  # spawn-worker 主进程 < 60s exit，bg 有时间跑（dialog 通常 30s 内弹，bg 60s max-wait 足够）。
  # 未来 Linux 装 util-linux（setsid）时：可用 `setsid bash -c "$(declare -f permission_auto_bg); permission_auto_bg '$SESSION'"` 真正脱离进程组。
  ( permission_auto_bg "$SESSION" & disown ) >/dev/null 2>&1 < /dev/null &
  echo "SPAWN_WORKER_PERMISSION_BG: launched (subshell inherit function v1.18.3 模式；v1.20.2 setsid/nohup bug hotfix)"
fi
if [ "$DRY_RUN" -eq 0 ] && [ "$EXTERNAL_IMPORTS_AUTO" -eq 1 ]; then
  # v1.20.3.1 hotfix（接 v1.20.2 Task-020）：同上 v1.20.2 setsid/nohup + 函数 bug 修复。
  ( external_imports_auto "$SESSION" & disown ) >/dev/null 2>&1 < /dev/null &
fi

if [ "$DRY_RUN" -eq 0 ]; then
  if [ "$ORCA_MODE" = "auto" ]; then
    # v2.1（DEC-114）：ORCA 模式。orca terminal create --worktree id:X 默认 cwd = worktree
    # 根；物理路径也相同（ORCA worktree 本身不解析 symlink）。
    pane_cwd="$ORCA_WORKTREE_PATH"
    pane_cwd_physical="$ORCA_WORKTREE_PATH"
  else
    pane_cwd=$(tmux display-message -p -t "$SESSION" '#{pane_current_path}' 2>/dev/null || echo "")
    pane_cwd_physical="$pane_cwd"
    if [ -n "$pane_cwd" ] && [ -d "$pane_cwd" ]; then
      pane_cwd_physical=$(cd "$pane_cwd" && pwd -P)
    fi
  fi
  if [ "$LIGHTWEIGHT_MODE" -eq 1 ]; then
    # v2.0：轻量模式隔离门禁只验 cwd == 目标文件夹，不验 branch
    current_branch=""
    expected_branch="-"
    expected_cwd="$WORKTREE"
  else
    current_branch=$(git -C "$WORKTREE" branch --show-current 2>/dev/null || echo "")
    expected_branch="$BRANCH"
    expected_cwd="$WORKTREE"
  fi
  echo "SPAWN_WORKER_SESSION: $SESSION"
  echo "SPAWN_WORKER_WORKTREE: $WORKTREE"
  echo "SPAWN_WORKER_CONTEXT: $SESSION_CONTEXT"
  echo "SPAWN_WORKER_ISOLATION_MODE: $isolation_mode_value"
  echo "SPAWN_WORKER_GATE: cwd=$pane_cwd_physical branch=$current_branch expected_cwd=$expected_cwd expected_branch=$expected_branch"
  if [ "$pane_cwd_physical" != "$expected_cwd" ] || [ "$current_branch" != "$expected_branch" ]; then
    echo "SPAWN_WORKER_GATE_FAILED" >&2
    exit 2
  fi
fi

echo "SPAWN_WORKER_NEXT: send worker prompt, then wait for $SESSION_CONTEXT/STATUS.json"

if [ "$WITH_SENTINEL" -eq 1 ] && [ "$DRY_RUN" -eq 0 ]; then
  SENTINEL_SCRIPT="$SCRIPT_DIR/sentinel.sh"
  if [ "$ORCA_MODE" = "auto" ]; then
    # v2.1（DEC-114）：ORCA 模式 sentinel 用 terminal-handle + worktree-id 路径；
    # sentinel.sh 收到后走 orca terminal read / orca terminal close / orca worktree set 路径。
    SENTINEL_CMD="bash $SENTINEL_SCRIPT --status-file $SESSION_CONTEXT/STATUS.json --terminal-handle $ORCA_TERMINAL_HANDLE --worktree-id $ORCA_WORKTREE_ID --poll-interval $SENTINEL_POLL_INTERVAL --max-wait $SENTINEL_MAX_WAIT"
    # supervised 时传 dispatch-id；sentinel 只观察/唤醒，不据 STATUS 结算生命周期。
    if [ -n "$ORCA_SUPERVISED_DISPATCH_ID" ]; then
      SENTINEL_CMD="$SENTINEL_CMD --dispatch-id $ORCA_SUPERVISED_DISPATCH_ID"
    fi
    # ORCA 模式下立即给 ORCA UI 设 in-progress（sentinel 终态会覆盖到 completed/failed）。
    if [ "$DRY_RUN" -eq 0 ]; then
      orca_cli worktree set --worktree "id:$ORCA_WORKTREE_ID" \
        --workspace-status in-progress \
        --comment "spawn-worker.sh ORCA mode: worker command launched, waiting STATUS.json" \
        --json >/dev/null 2>&1 || true
    fi
  else
    SENTINEL_CMD="bash $SENTINEL_SCRIPT --status-file $SESSION_CONTEXT/STATUS.json --tmux-session $SESSION --poll-interval $SENTINEL_POLL_INTERVAL --max-wait $SENTINEL_MAX_WAIT"
  fi
  if [ "$KEEP_TMUX_ON_TERMINAL" -eq 1 ]; then
    SENTINEL_CMD="$SENTINEL_CMD --keep-tmux-on-terminal"
  fi
  echo "SPAWN_WORKER_SENTINEL_CMD: $SENTINEL_CMD"
  echo "SPAWN_WORKER_RECOMMENDED_NEXT: run the above command with Bash run_in_background=true (NOT from inside spawn-worker). Sentinel exit triggers harness task-notification and wakes PM."
fi
