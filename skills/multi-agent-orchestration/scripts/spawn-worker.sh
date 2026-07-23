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

# v2.0：PATH 注入 helper（2026-07-12 实战坑：claude 在 ~/.local/bin，wrapper 后
# which 不到）。在 flag 解析之前注入，确保后续 tmux 内 wrapper 派 Claude Code
# 也能复用同一 PATH。
# shellcheck source=ensure-claude-path.sh
source "$SCRIPT_DIR/ensure-claude-path.sh"
ensure_claude_in_path

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
# v2.0：轻量模式（无 worktree）。默认 0 (走 worktree 隔离)；--no-worktree 显式置 1，
# 或自动检测 --project 不是 git 仓时置 1 并打印 SPAWN_WORKER_LIGHTWEIGHT_AUTO。
# 详见 SKILL.md §2.1.1 + references/09-parallel-lessons.md T6 实战坑。
LIGHTWEIGHT_OVERRIDE=0
LIGHTWEIGHT_MODE=0
LIGHTWEIGHT_AUTO=0
INSTALL_AUTHORIZATION_SOURCE=""
AUTHORIZED_INSTALL_COMMANDS=()
ALLOWED_SHELL_COMMANDS=()
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
  --no-worktree     (v2.0) 显式启用轻量模式：不建 git worktree、不切分支、不算 base ref；
                   worker tmux cwd 直接指向 --project 目录。METADATA 记
                   `isolation_mode: "lightweight"`，branch/base_ref/base_sha 留空。
                   当 --project 不是 git 仓时本 flag 可省（脚本自动检测并打印
                   `SPAWN_WORKER_LIGHTWEIGHT_AUTO`）。多 worker 共享同仓时按
                   SKILL §2.1.1 配 --allow-paths 做 scope 硬护栏。详见 SKILL §2.1.1。
  --allow-install-command CMD
                   Explicitly authorize this exact dependency-install/environment-mutation
                   command (repeatable). Requires --install-authorization-source.
                   All detected install commands are denied by default.
  --install-authorization-source TEXT
                   Auditable source for allowed install commands, e.g. an exact user approval,
                   project rule or task ID. A command list without this field fails closed.
  --allow-shell-command CMD
                   Allow this exact non-install Shell command (repeatable). Verification commands
                   passed via --verify-cmd are included automatically. All other Shell commands
                   are denied by the PreToolUse hook; install-like commands must use the separate
                   --allow-install-command + authorization-source path.
  --git-expected-name NAME
  --git-expected-email EMAIL
  --git-integration-base REF
                   Enable the identity-bound safe-push command. All three fields are required;
                   REF must be the PR base remote-tracking ref (for example origin/main).
                   Raw git push remains denied by the Shell gate.
  --git-push-remote REMOTE
                   Push remote used by safe-push. Default: origin.
  --allow-prompt-only-install-guard TEXT
                   Explicitly accept degraded prompt-only enforcement for a backend without
                   PreToolUse hooks (currently codex/opencode/custom), or a command mode that
                   disables hooks (for example Claude Code --bare). TEXT records the user or
                   project authorization source. Without this flag degraded paths fail closed.
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
    --no-worktree)  # v2.0：显式启用轻量模式（SKILL §2.1.1）
      LIGHTWEIGHT_OVERRIDE=1
      LIGHTWEIGHT_MODE=1
      shift
      ;;
    --allow-install-command)
      AUTHORIZED_INSTALL_COMMANDS+=("$2")
      shift 2
      ;;
    --install-authorization-source)
      INSTALL_AUTHORIZATION_SOURCE="$2"
      shift 2
      ;;
    --allow-shell-command)
      ALLOWED_SHELL_COMMANDS+=("$2")
      shift 2
      ;;
    --git-expected-name)
      GIT_EXPECTED_NAME="$2"
      shift 2
      ;;
    --git-expected-email)
      GIT_EXPECTED_EMAIL="$2"
      shift 2
      ;;
    --git-integration-base)
      GIT_INTEGRATION_BASE="$2"
      shift 2
      ;;
    --git-push-remote)
      GIT_PUSH_REMOTE="$2"
      shift 2
      ;;
    --allow-prompt-only-install-guard)
      ALLOW_PROMPT_ONLY_INSTALL_GUARD=1
      INSTALL_GUARD_DEGRADATION_SOURCE="$2"
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
[ -n "$SESSION" ] || { usage; exit 64; }
command -v git >/dev/null 2>&1 || { echo "ERROR: git is required" >&2; exit 64; }
command -v tmux >/dev/null 2>&1 || { echo "ERROR: tmux is required" >&2; exit 64; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required for dependency install guard; do not install it without user authorization" >&2; exit 64; }

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
  ""|codex|opencode|custom)
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
[ -n "$COMMAND" ] || COMMAND="${SHELL:-/bin/bash} -l"

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

if [ "$INSTALL_GUARD_MODE" = "hook" ] && \
   { [ "$WORKER_BACKEND" = "claude-code" ] || [ "$WORKER_BACKEND" = "claude_code" ]; } && \
   hook_disable_reason=$(claude_hook_disable_reason); then
  if [ "$ALLOW_PROMPT_ONLY_INSTALL_GUARD" -ne 1 ]; then
    echo "ERROR: Claude Code command cannot prove local PreToolUse hook enforcement: $hook_disable_reason; fix the command or explicitly pass --allow-prompt-only-install-guard (fail-closed)" >&2
    exit 64
  fi
  INSTALL_GUARD_MODE="prompt_only_degraded"
fi

backend_command_token_missing() {
  python3 - "$WORKER_BACKEND" "$COMMAND" <<'PY'
import os, shlex, sys
backend, command = sys.argv[1:]
try:
    basenames = {os.path.basename(token).lower() for token in shlex.split(command, posix=True)}
except ValueError:
    print("unparseable command")
    raise SystemExit(0)
accepted = {
    "codebuddy": {"codebuddy"},
    "qoderwork-cn": {"qoderclicn"},
    "qoderclicn": {"qoderclicn"},
}.get(backend, set())
if accepted and not (basenames & accepted):
    print(f"command exposes none of the expected executable tokens: {sorted(accepted)}")
    raise SystemExit(0)
raise SystemExit(1)
PY
}
if [ "$INSTALL_GUARD_MODE" = "hook" ] && \
   { [ "$WORKER_BACKEND" = "codebuddy" ] || [ "$WORKER_BACKEND" = "qoderwork-cn" ] || [ "$WORKER_BACKEND" = "qoderclicn" ]; } && \
   backend_reason=$(backend_command_token_missing); then
  if [ "$ALLOW_PROMPT_ONLY_INSTALL_GUARD" -ne 1 ]; then
    echo "ERROR: $WORKER_BACKEND command cannot prove the configured backend is launched: $backend_reason (fail-closed)" >&2
    exit 64
  fi
  INSTALL_GUARD_MODE="prompt_only_degraded"
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
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "ERROR: tmux session already exists: $SESSION" >&2
  exit 1
fi

if [ "$LIGHTWEIGHT_MODE" -eq 1 ]; then
  # 轻量模式（SKILL §2.1.1）：不建 worktree、不切分支、不验 base ref；
  # WORKTREE 已指向 PROJECT_DIR（或 --worktree 覆盖的子目录）。
  BASE_SHA=""
  echo "SPAWN_WORKER_LIGHTWEIGHT: skip git worktree setup, worker cwd=$WORKTREE"
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

write_metadata() {
  local enforcement_source worker_mirror_authoritative
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

  # v2.0：写 isolation_mode（worktree 或 lightweight）+ lightweight_auto 标记
  if [ "$LIGHTWEIGHT_MODE" -eq 1 ]; then
    isolation_mode_value="lightweight"
  else
    isolation_mode_value="worktree"
  fi
  if [ "$INSTALL_GUARD_MODE" = "hook" ]; then
    enforcement_source="pretool_hook_settings_wired_process_snapshot_runtime_unproven"
    worker_mirror_authoritative=false
  else
    enforcement_source="prompt_only_no_mechanical_enforcement"
    worker_mirror_authoritative=false
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
    --arg isolation_mode "$isolation_mode_value" \
    --argjson lightweight_auto "$LIGHTWEIGHT_AUTO" \
    --argjson verification_commands "$verify_json" \
    --argjson add_dirs "$(array_to_json "${ADD_DIRS[@]}")" \
    --argjson allow_paths "$(array_to_json "${ALLOW_PATHS[@]}")" \
    --arg install_guard_mode "$INSTALL_GUARD_MODE" \
    --arg install_authorization_file "$INSTALL_AUTH_FILE" \
    --arg install_authorization_source "$INSTALL_AUTHORIZATION_SOURCE" \
    --arg install_guard_degradation_source "$INSTALL_GUARD_DEGRADATION_SOURCE" \
    --arg git_expected_name "$GIT_EXPECTED_NAME" \
    --arg git_expected_email "$GIT_EXPECTED_EMAIL" \
    --arg git_integration_base "$GIT_INTEGRATION_BASE" \
    --arg safe_push_command "$SAFE_PUSH_COMMAND" \
    --arg authority_receipt_file "$AUTHORITY_RECEIPT_FILE" \
    --arg authority_receipt_sha256 "$AUTHORITY_RECEIPT_SHA256" \
    --arg guard_attestation_file "$GUARD_ATTESTATION_FILE" \
    --arg enforcement_source "$enforcement_source" \
    --argjson worker_mirror_authoritative "$worker_mirror_authoritative" \
    --argjson authorized_install_commands "$(array_to_json "${AUTHORIZED_INSTALL_COMMANDS[@]}")" \
    --argjson allowed_shell_commands "$(array_to_json "${EFFECTIVE_ALLOWED_SHELL_COMMANDS[@]}" | jq 'unique')" \
    '{
      schema: $schema,
      created_at: $created_at,
      project: $project,
      worktree: $worktree,
      branch: $branch,
      base_ref: $base_ref,
      base_sha: $base_sha,
      isolation: {
        mode: $isolation_mode,
        lightweight_auto: $lightweight_auto
      },
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
      execution_authority: {
        environment_mutation_policy: "deny_by_default",
        install_guard_mode: $install_guard_mode,
        install_authorization_file: $install_authorization_file,
        install_authorization_source: $install_authorization_source,
        authorized_install_commands: $authorized_install_commands,
        allowed_shell_commands: $allowed_shell_commands,
        degradation_source: $install_guard_degradation_source,
        enforcement_source: $enforcement_source,
        authority_receipt_file: $authority_receipt_file,
        authority_receipt_sha256: $authority_receipt_sha256,
        guard_attestation_file: $guard_attestation_file,
        worker_mirror_authoritative: $worker_mirror_authoritative,
        git_identity: {
          expected_name: $git_expected_name,
          expected_email: $git_expected_email,
          integration_base: $git_integration_base,
          safe_push_command: $safe_push_command,
          raw_git_push_allowed: false,
          commit_environment_bound: ($git_expected_name != "" and $git_expected_email != "")
        }
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
  SENTINEL_CMD="bash $SENTINEL_SCRIPT --status-file $SESSION_CONTEXT/STATUS.json --tmux-session $SESSION --poll-interval $SENTINEL_POLL_INTERVAL --max-wait $SENTINEL_MAX_WAIT"
  if [ "$KEEP_TMUX_ON_TERMINAL" -eq 1 ]; then
    SENTINEL_CMD="$SENTINEL_CMD --keep-tmux-on-terminal"
  fi
  echo "SPAWN_WORKER_SENTINEL_CMD: $SENTINEL_CMD"
  echo "SPAWN_WORKER_RECOMMENDED_NEXT: run the above command with Bash run_in_background=true (NOT from inside spawn-worker). Sentinel exit triggers harness task-notification and wakes PM."
fi
