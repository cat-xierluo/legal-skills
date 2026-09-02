#!/usr/bin/env bash
# spawn-worker-flags.sh — usage text and argument parsing for spawn-worker.sh.
# This file is sourced after spawn-worker.sh initializes its defaults and arrays.

usage() {
  cat >&2 <<'USAGE'
Usage:
  spawn-worker.sh --project PATH --branch NAME --session NAME [options]

Options:
  --worktree PATH   Worktree path. Defaults to .claude/worktrees/tmux-{branch}
  --base-ref REF    Base ref for new branches. Default: main
  --command CMD     Command to run. Default: the executable for the verified backend
  --worker-backend NAME
                   Worker backend: claude-code, codex, codebuddy, qoderwork-cn or zcode
                   (zcode has no TUI — spawn runs the zcode-worker-driver.py wrapper).
  --pm-harness NAME
                   Optional assertion for the current PM harness. Runtime evidence remains
                   authoritative: a conflicting assertion fails and can never elevate access.
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
  --no-external-imports-auto  (v1.20.2 Task-020) Skip "external imports" dialog
                   auto-accept for claude-code workers. Default: claude-code ON,
                   other backends OFF. claude-code with CLAUDE.md @import triggers a
                   "Yes allow external imports" dialog on first start; this watches
                   and selects option 1 (default) so the worker is not blocked.
  --external-imports-auto  (v1.20.2) Force external-imports dialog watcher ON for
                   non-claude-code backends if they surface the same dialog.
  --quota-preflight-override TEXT
                   (v2.11.0, P0-①) Explicitly override a denied quota preflight
                   (missing/stale summary, below stop line, provider-lane
                   mismatch...). TEXT records the non-empty user/project
                   authorization source and is written to METADATA.json and the
                   authority receipt. Without this flag a denied preflight
                   fails closed before any side effect; there is no default
                   manual-lock pass-through.
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
  --role ROLE       (v2.14.0) Worker role in role-separated acceptance waves.
                   implementer (default, unchanged behavior) or reviewer.
                   reviewer 强制写范围纪律：默认只允许写自身 Session Context
                   （.claude/agent-sessions/<session>/**）；任何 config/*.local.yaml
                   （安装 Skill 的本地运行配置）永远不可写。要写被审分支必须有
                   --review-repair-grant 显式授权；无授权时传 --allow-paths 直接
                   fail-closed 拒绝 spawn。角色与授权写入 METADATA runtime.role。
  --review-repair-grant TEXT
                   (v2.14.0) 任务合同显式授予 reviewer 修复被审分支的授权来源
                   （如任务卡 ID / dispatch 记录）。仅 --role reviewer 有效；
                   授予后 --allow-paths 才会被采纳，但 config/*.local.yaml
                   硬拒绝仍然生效。写入 METADATA runtime.role。
  --no-worktree     (v2.0) 显式启用轻量模式：不建 git worktree、不切分支、不算 base ref；
                   worker tmux cwd 直接指向 --project 目录。METADATA 记
                   `isolation_mode: "lightweight"`，branch/base_ref/base_sha 留空。
                   当 --project 不是 git 仓时本 flag 可省（脚本自动检测并打印
                   `SPAWN_WORKER_LIGHTWEIGHT_AUTO`）。多 worker 共享同仓时按
                   SKILL §2.1.1 配 --allow-paths 做 scope 硬护栏。详见 SKILL §2.1.1。
  --no-orca-mode    显式 opt-out ORCA 终端模式：强制走原 tmux + git worktree路径，
                   不调任何 orca CLI。auto-detect 默认以 `orca worktree current --json`
                   确认 PROJECT_DIR 是当前 Orca worktree，不依赖 TERM_PROGRAM / ORCA_WORKTREE_ID。
                   命中后用 `orca worktree create` + `orca terminal create --command`，保留 provider env /
                   runtime profile / wrapper / 超长 prompt 投递等所有现有能力；ORCA UI 直接反映
                   worker 生命周期（spawn 完 ORCA 列表多一张卡，sentinel 终态自动切 workspace-status）。
                   --no-worktree 与 ORCA 模式互斥（ORCA worktree 必须有 git 仓）。详见 SKILL §6.5。
  --orca-supervised 建立 Orca 原生 Run/Task/Dispatch。传 --task-spec 创建单 Task，
                   或同时传 --orca-run-id + --orca-task-id 复用 Wave 预创建 Task；
                   worker-start 是该路径唯一的任务注入器，worker 必须发送一次 worker_done。
  --orca-run-id ID  复用现有 Run；同一 Wave 的所有 supervised worker 应传同一个 Run ID。
  --orca-task-id ID 复用 `orca-wave-prepare.sh` 预创建的 Task；必须同时传 --orca-run-id
                   与 --orca-coordinator-handle。
  --orca-coordinator-handle ID
                   复用 Wave receipt 的 coordinator_handle，避免并发 worker 重复 run-use。
  --task-spec TEXT  supervised Task 的完整任务说明。
  --task-title TEXT supervised Task 的简短标题。
  --allow-install-command CMD
                   Explicitly authorize this exact dependency-install/environment-mutation
                   command (repeatable). Requires --install-authorization-source.
                   All detected install commands are denied by default.
  --install-authorization-source TEXT
                   Auditable source for allowed install commands, e.g. an exact user approval,
                   project rule or task ID. A command list without this field fails closed.
  --python-runtime-symlink PATH
                   (v2.7, Task-061) Explicitly share the main repo's .runtime (venv/models)
                   into the worktree via symlink for Python projects. Opt-in because venv
                   paths are layout-sensitive; fail-closed when the source interpreter is
                   missing or a 0-byte placeholder, or the worktree already has .runtime.
  --deps-mode MODE  node_modules dependency mode for the worktree. auto (default):
                   symlink, except it auto-selects local when --allow-install-command
                   is passed (a task authorized to install will mutate dependencies;
                   a symlinked node_modules breaks pnpm add and vite server.fs.allow).
                   symlink = force the main-repo node_modules symlink (legacy behavior).
                   local = never symlink; the worker installs locally inside the worktree
                   before first verification (install authorization still goes through
                   the --allow-install-command + --install-authorization-source channel).
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
                   PreToolUse hooks (currently codex/zcode), or a command mode that
                   disables hooks (for example Claude Code --bare; since v2.11.0 the
                   former --bare auto-degrade is removed, so this flag is the only
                   degradation channel). TEXT records the user or project authorization
                   source. Without this flag degraded paths fail closed.
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
parse_spawn_worker_args() {
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
      --pm-harness)
        PM_HARNESS_ASSERTION="$2"
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
      --no-external-imports-auto)  # v1.20.2 Task-020：opt-out external imports dialog 监控
        EXTERNAL_IMPORTS_AUTO=0
        EXTERNAL_IMPORTS_AUTO_OVERRIDE=1
        shift
        ;;
      --external-imports-auto)  # v1.20.2：显式 opt-in（其他 backend 如需监控 external imports）
        EXTERNAL_IMPORTS_AUTO=1
        EXTERNAL_IMPORTS_AUTO_OVERRIDE=1
        shift
        ;;
      --quota-preflight-override)  # v2.11.0 P0-①：显式绕过被拒的配额预检（须带非空授权来源）
        QUOTA_PREFLIGHT_OVERRIDE=1
        QUOTA_PREFLIGHT_OVERRIDE_SOURCE="$2"
        shift 2
        ;;
      --add-dir)
        ADD_DIRS+=("$2")
        shift 2
        ;;
      --allow-paths)
        ALLOW_PATHS+=("$2")
        shift 2
        ;;
      --role)  # v2.14.0：worker 角色（implementer 默认 | reviewer 触发写范围纪律）
        ROLE="$2"
        shift 2
        ;;
      --review-repair-grant)  # v2.14.0：任务合同显式授予 reviewer 被审分支修复权（须带授权来源）
        REVIEW_REPAIR_GRANT="$2"
        shift 2
        ;;
      --no-worktree)  # v2.0：显式启用轻量模式（SKILL §2.1.1）
        LIGHTWEIGHT_OVERRIDE=1
        LIGHTWEIGHT_MODE=1
        shift
        ;;
      --no-orca-mode)  # v2.1（DEC-114）：显式 opt-out ORCA 终端模式，强制走 tmux 路径
        NO_ORCA_MODE=1
        shift
        ;;
      --orca-supervised)  # ORCA 模式 spawn 后纳入原生 Run/Task/Dispatch 生命周期
        ORCA_SUPERVISED=1
        shift
        ;;
      --task-spec)  # v2.1.1（Task-033）：supervised task 的 spec（--orca-supervised 时必填）
        TASK_SPEC="$2"
        shift 2
        ;;
      --task-title)  # v2.1.1（Task-033）：supervised task 的 title
        TASK_TITLE="$2"
        shift 2
        ;;
      --orca-run-id)  # 同一 Wave 的 worker 复用一个 Run；未传时 helper 为单 worker 新建 Run
        ORCA_RUN_ID="$2"
        shift 2
        ;;
      --orca-task-id)  # Wave 预创建 Task；避免并发 spawn 同时 run-use/task-create
        ORCA_TASK_ID="$2"
        shift 2
        ;;
      --orca-coordinator-handle)  # Wave receipt 中已绑定的 coordinator；并发启动时直接复用
        ORCA_COORDINATOR_HANDLE="$2"
        shift 2
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
      --python-runtime-symlink)
        PYTHON_RUNTIME_SYMLINK="$2"
        shift 2
        ;;
      --deps-mode)  # node_modules 依赖补偿模式；auto=默认（有 --allow-install-command 时自动 local，否则软链）
        case "$2" in
          auto|symlink|local)
            DEPS_MODE="$2"
            ;;
          *)
            echo "ERROR: --deps-mode only accepts auto|symlink|local (got: $2)" >&2
            usage
            exit 64
            ;;
        esac
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
}
