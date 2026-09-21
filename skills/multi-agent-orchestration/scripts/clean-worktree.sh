#!/usr/bin/env bash
# clean-worktree.sh — safe cleanup for one worker tmux session and worktree.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=orca-runtime.sh
source "$SCRIPT_DIR/orca-runtime.sh"
# shellcheck source=provider-lease-root.sh
source "$SCRIPT_DIR/provider-lease-root.sh"

PROJECT_DIR=""
BRANCH=""
SESSION=""
WORKTREE=""
EXECUTE=0
KEEP_SESSION=0
KEEP_WORKTREE=0
DELETE_BRANCH=0
FORCE_DIRTY=0
FORCE_DELETE_BRANCH=0

usage() {
  cat >&2 <<'USAGE'
Usage:
  clean-worktree.sh --project PATH --branch NAME --session NAME [options]

Default is dry-run. It prints planned cleanup and makes no changes.

Options:
  --worktree PATH        Override worktree path if branch lookup is unavailable
  --execute             Actually kill tmux/remove worktree
  --keep-session        Do not kill tmux session
  --keep-worktree       Do not remove git worktree
  --delete-branch       Delete local branch after worktree removal
  --force-remove-dirty  Allow removing a dirty worktree
  --force-delete-branch Escalate to git branch -D when safe -d refuses; only for
                        callers holding independent MERGED+head evidence (e.g.
                        post-merge-cleanup.sh). Never use it to "align with remote".

This script never deletes a remote branch and never runs git reset.
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
    --session)
      SESSION="$2"
      shift 2
      ;;
    --worktree)
      WORKTREE="$2"
      shift 2
      ;;
    --execute)
      EXECUTE=1
      shift
      ;;
    --keep-session)
      KEEP_SESSION=1
      shift
      ;;
    --keep-worktree)
      KEEP_WORKTREE=1
      shift
      ;;
    --delete-branch)
      DELETE_BRANCH=1
      shift
      ;;
    --force-remove-dirty)
      FORCE_DIRTY=1
      shift
      ;;
    --force-delete-branch)
      FORCE_DELETE_BRANCH=1
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
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }

PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd -P)
case "$WORKTREE" in
  "") ;;
  /*) ;;
  *) WORKTREE="$PROJECT_DIR/$WORKTREE" ;;
esac

if [ -z "$WORKTREE" ]; then
  WORKTREE=$(git -C "$PROJECT_DIR" worktree list --porcelain 2>/dev/null | awk -v target="refs/heads/$BRANCH" '
    /^worktree / { wt = substr($0, 10) }
    /^branch / {
      if (substr($0, 8) == target) {
        print wt
        exit
      }
    }
  ')
fi

run() {
  printf 'CLEAN_WORKTREE_RUN: %s\n' "$*"
  [ "$EXECUTE" -eq 1 ] || return 0
  "$@"
}

echo "CLEAN_WORKTREE_MODE: $([ "$EXECUTE" -eq 1 ] && echo execute || echo dry-run)"
echo "CLEAN_WORKTREE_TARGET: branch=$BRANCH session=$SESSION worktree=${WORKTREE:-missing}"

if [ -n "$WORKTREE" ] && [ -f "$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json" ]; then
  metadata_file="$WORKTREE/.claude/agent-sessions/$SESSION/METADATA.json"
  if ! jq -e 'type == "object"' "$metadata_file" >/dev/null 2>&1; then
      echo "CLEAN_WORKTREE_REFUSED: invalid METADATA.json; retain worktree and provider quota for recovery: $metadata_file" >&2
      [ "$EXECUTE" -eq 0 ] || exit 2
  else
    metadata_base_ref=$(jq -r '.base_ref // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_created_at=$(jq -r '.created_at // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_backend=$(jq -r '.runtime.worker_backend // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_profile=$(jq -r '.runtime.runtime_profile // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_env_isolation=$(jq -r '.runtime.env_isolation // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_pr=$(jq -r '.pr.url // ""' "$metadata_file" 2>/dev/null || echo "")
    # v2.1（DEC-114）：读 ORCA worktree_id，用于后续 orca worktree rm 同步清理。
    metadata_orca_worktree_id=$(jq -r '.session.orca.worktree_id // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_orca_mode=$(jq -r '.session.orca.mode // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_orca_terminal_handle=$(jq -r '.session.orca.terminal_handle // ""' "$metadata_file" 2>/dev/null || echo "")
    # Orca supervised Dispatch 必须先按生命周期结算，文件清理不能隐式 stop active worker。
    metadata_orca_dispatch_id=$(jq -r '.session.orca.supervised.dispatch_id // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_orca_run_id=$(jq -r '.session.orca.supervised.run_id // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_provider_lease_file=$(jq -r '.runtime.provider_lease.file // ""' "$metadata_file" 2>/dev/null || echo "")
    metadata_session_id=$(jq -r '.session.id // ""' "$metadata_file" 2>/dev/null || echo "")
    echo "CLEAN_WORKTREE_METADATA: base=${metadata_base_ref:-n/a} created_at=${metadata_created_at:-n/a} backend=${metadata_backend:-n/a} profile=${metadata_profile:-n/a} env_isolation=${metadata_env_isolation:-n/a} pr=${metadata_pr:-n/a} orca_mode=${metadata_orca_mode:-n/a}"
  fi
else
  echo "CLEAN_WORKTREE_METADATA: missing"
fi

release_provider_lease() {
  local lease_root orca_path=""
  [ -n "${metadata_provider_lease_file:-}" ] || return 0
  [ -n "${metadata_session_id:-}" ] || return 0
  lease_root=$(provider_lease_root_for_project "$PROJECT_DIR") || {
    echo "CLEAN_WORKTREE_REFUSED: cannot derive trusted provider lease root" >&2
    [ "$EXECUTE" -eq 0 ] || exit 2
    return 0
  }
  if [ "$EXECUTE" -eq 0 ]; then
    echo "CLEAN_WORKTREE_RUN: provider lease release file=$metadata_provider_lease_file session=$metadata_session_id"
    return 0
  fi
  orca_runtime_init >/dev/null 2>&1 && orca_path="$ORCA_CLI_BIN"
  python3 "$SCRIPT_DIR/provider-lease.py" release \
    --root "$lease_root" \
    --lease-file "$metadata_provider_lease_file" --session "$metadata_session_id" \
    --resource-settled --orca-cli "$orca_path" >/dev/null || {
    echo "CLEAN_WORKTREE_REFUSED: exact provider lease release failed" >&2
    exit 2
  }
  echo "CLEAN_WORKTREE_PROVIDER_LEASE_RELEASED: session=$metadata_session_id"
}

close_retained_external_terminal() {
  local worker_row="$1"
  local worker_state dispatch_status ownership_state retained_reason resource_handle
  local close_json="" close_rc=0 show_json

  worker_state=$(printf '%s' "$worker_row" | jq -r '.workerState // .worker_state // "unknown"')
  dispatch_status=$(printf '%s' "$worker_row" | jq -r '.dispatchStatus // .dispatch_status // "unknown"')
  ownership_state=$(printf '%s' "$worker_row" | jq -r '.resource.ownershipState // .resource.ownership_state // "unknown"')
  retained_reason=$(printf '%s' "$worker_row" | jq -r '.resource.retainedReason // .resource.retained_reason // "unknown"')
  resource_handle=$(printf '%s' "$worker_row" | jq -r '.agentTerminalHandle // .agent_terminal_handle // .resource.terminalHandle // .resource.terminal_handle // empty')
  if ! [[ "$worker_state" =~ ^(succeeded|failed)$ ]] || [ "$dispatch_status" != "completed" ] || \
     [ "$ownership_state" != "external" ] || [ "$retained_reason" != "external_terminal" ] || \
     [ -z "$resource_handle" ] || [ "$resource_handle" != "${metadata_orca_terminal_handle:-}" ]; then
    echo "CLEAN_WORKTREE_REFUSED: retained terminal is not a proven settled external resource (worker=$worker_state dispatch=$dispatch_status ownership=$ownership_state reason=$retained_reason)" >&2
    return 2
  fi

  echo "CLEAN_WORKTREE_ORCA_SUPERVISED: dispatch=$metadata_orca_dispatch_id terminal=retained/external; closing exact creator-owned handle=$resource_handle"
  close_json=$(orca_cli terminal close --terminal "$resource_handle" --json 2>&1) || close_rc=$?
  show_json=$(orca_cli terminal show --terminal "$resource_handle" --json 2>/dev/null) || {
    echo "CLEAN_WORKTREE_REFUSED: cannot prove exact external terminal disconnected after close (close_rc=$close_rc): $close_json" >&2
    return 2
  }
  if ! printf '%s' "$show_json" | jq -e --arg handle "$resource_handle" '
    .ok == true
    and ((.result.terminal.handle // "") == $handle)
    and .result.terminal.connected == false
    and .result.terminal.writable == false
  ' >/dev/null 2>&1; then
    echo "CLEAN_WORKTREE_REFUSED: exact external terminal disconnect is not proven after close (close_rc=$close_rc): $show_json" >&2
    return 2
  fi
  if [ "$close_rc" -eq 0 ]; then
    printf '%s\n' "$close_json"
  else
    echo "CLEAN_WORKTREE_ORCA_SUPERVISED: exact external handle already disconnected after close race"
  fi
}

# Supervised cleanup is conditional: release a settled worker; do not translate an
# active/unknown Dispatch into worker-stop just because filesystem cleanup was requested.
# This gate must run before tmux/terminal/filesystem/Git mutation.
settle_supervised_cleanup() {
  [ -n "${metadata_orca_dispatch_id:-}" ] || return 0
  if [ "$KEEP_WORKTREE" -eq 1 ] && [ "$KEEP_SESSION" -eq 1 ]; then
    return 0
  fi
  if orca_runtime_init >/dev/null 2>&1; then
    if [ "$EXECUTE" -eq 0 ]; then
      echo "CLEAN_WORKTREE_RUN: exact worker-list preflight run=${metadata_orca_run_id:-missing} dispatch=$metadata_orca_dispatch_id; release only reclaimable accounting; continue only after released or proven retained/external"
    else
      [ -n "${metadata_orca_run_id:-}" ] || {
        echo "CLEAN_WORKTREE_REFUSED: supervised metadata lacks run_id; recover authoritative Run identity before cleanup" >&2
        return 2
      }
      if ! orca_runtime_worker_row_exact "$metadata_orca_dispatch_id" "$metadata_orca_run_id"; then
        echo "CLEAN_WORKTREE_REFUSED: exact WorkerList preflight failed; no lifecycle or cleanup mutation performed" >&2
        return 2
      fi
      worker_row="$ORCA_WORKER_ROW_JSON"
      terminal_state=$(printf '%s' "$worker_row" | jq -r '.terminalState // .terminal_state // .accountingState // .accounting_state // "unknown"')
      case "$terminal_state" in
        released)
          echo "CLEAN_WORKTREE_ORCA_SUPERVISED: dispatch=$metadata_orca_dispatch_id terminal=released"
          ;;
        retained)
          close_retained_external_terminal "$worker_row" || return 2
          ;;
        reclaimable)
          release_json=$(orca_cli orchestration worker-release --dispatch "$metadata_orca_dispatch_id" --json) || {
            echo "CLEAN_WORKTREE_REFUSED: worker-release outcome unknown; no direct terminal or filesystem cleanup performed" >&2
            return 2
          }
          if ! printf '%s' "$release_json" | jq -e --arg dispatch "$metadata_orca_dispatch_id" '
            .ok == true
            and ((.result.release.dispatchId // .result.release.dispatch_id // .result.dispatchId // .result.dispatch_id // "") == $dispatch)
          ' >/dev/null 2>&1; then
            echo "CLEAN_WORKTREE_REFUSED: worker-release receipt is not bound to dispatch=$metadata_orca_dispatch_id" >&2
            return 2
          fi
          printf '%s\n' "$release_json"
          if ! orca_runtime_worker_row_exact "$metadata_orca_dispatch_id" "$metadata_orca_run_id"; then
            echo "CLEAN_WORKTREE_REFUSED: post-release accounting unreadable; release may have occurred, but no direct terminal or filesystem cleanup was attempted" >&2
            return 2
          fi
          worker_row="$ORCA_WORKER_ROW_JSON"
          terminal_state=$(printf '%s' "$worker_row" | jq -r '.terminalState // .terminal_state // .accountingState // .accounting_state // "unknown"')
          case "$terminal_state" in
            released)
              echo "CLEAN_WORKTREE_ORCA_SUPERVISED: dispatch=$metadata_orca_dispatch_id terminal=released"
              ;;
            retained)
              close_retained_external_terminal "$worker_row" || return 2
              ;;
            *)
              echo "CLEAN_WORKTREE_REFUSED: worker-release did not settle terminal accounting (state=$terminal_state); no direct terminal or filesystem cleanup performed" >&2
              return 2
              ;;
          esac
          ;;
        active|release_pending|release_unknown|unknown|"")
          echo "CLEAN_WORKTREE_REFUSED: supervised terminal accounting is $terminal_state; no lifecycle or cleanup mutation performed" >&2
          return 2
          ;;
        *)
          echo "CLEAN_WORKTREE_REFUSED: unsupported terminal accounting state=$terminal_state" >&2
          return 2
          ;;
      esac
    fi
  else
    echo "CLEAN_WORKTREE_ORCA_SUPERVISED: Orca CLI not found; cannot account dispatch=$metadata_orca_dispatch_id"
    [ "$EXECUTE" -eq 0 ] || return 2
  fi
}

settle_supervised_cleanup || exit 2

if [ "$KEEP_SESSION" -eq 0 ]; then
  if command -v tmux >/dev/null 2>&1 && tmux has-session -t "$SESSION" 2>/dev/null; then
    run tmux kill-session -t "$SESSION"
  elif [ -n "${metadata_orca_terminal_handle:-}" ] && [ -z "${metadata_orca_dispatch_id:-}" ]; then
    if orca_runtime_init >/dev/null 2>&1; then
      if [ "$EXECUTE" -eq 0 ]; then
        echo "CLEAN_WORKTREE_RUN: $ORCA_CLI_BIN terminal close --terminal $metadata_orca_terminal_handle"
      else
        close_rc=0
        close_json=$(orca_cli terminal close --terminal "$metadata_orca_terminal_handle" --json 2>&1) || close_rc=$?
        show_json=$(orca_cli terminal show --terminal "$metadata_orca_terminal_handle" --json 2>/dev/null) || {
          echo "CLEAN_WORKTREE_REFUSED: cannot prove terminal-managed handle disconnected after close (close_rc=$close_rc): $close_json" >&2
          exit 2
        }
        if ! printf '%s' "$show_json" | jq -e --arg handle "$metadata_orca_terminal_handle" '
          .ok == true
          and ((.result.terminal.handle // "") == $handle)
          and .result.terminal.connected == false
          and .result.terminal.writable == false
        ' >/dev/null 2>&1; then
          echo "CLEAN_WORKTREE_REFUSED: terminal-managed Orca handle disconnect is not proven: $show_json" >&2
          exit 2
        fi
        echo "CLEAN_WORKTREE_ORCA_TERMINAL_CLOSED: handle=$metadata_orca_terminal_handle"
      fi
    else
      echo "CLEAN_WORKTREE_REFUSED: cannot close Orca terminal because selected CLI is unavailable" >&2
      [ "$EXECUTE" -eq 0 ] || exit 2
    fi
  else
    echo "CLEAN_WORKTREE_SESSION: missing session=$SESSION"
  fi
else
  echo "CLEAN_WORKTREE_SESSION: kept session=$SESSION"
fi

# Task-045 / G31：worktree 删除前安全 unlink node_modules 软链（spawn-worker-deps 注入）。
# -L 确认是软链、rm -f 不带尾斜杠——绝不跟随软链误删主仓 node_modules。
if [ -n "$WORKTREE" ] && [ -L "$WORKTREE/node_modules" ]; then
  if [ "$EXECUTE" -eq 0 ]; then
    echo "CLEAN_WORKTREE_RUN: rm -f $WORKTREE/node_modules (symlink unlink)"
  else
    rm -f "$WORKTREE/node_modules"
    echo "CLEAN_WORKTREE_DEPS_UNLINKED: node_modules symlink"
  fi
fi

# Task-061：同模式安全 unlink .runtime 软链（--python-runtime-symlink 注入）。
# git worktree remove 视 untracked 内容为脏；不先 unlink 会让 tmux 路径的清理
# 被拒或需要 --force。绝不跟随软链触碰主仓 .runtime（venv/models 所在）。
if [ -n "$WORKTREE" ] && [ -L "$WORKTREE/.runtime" ]; then
  if [ "$EXECUTE" -eq 0 ]; then
    echo "CLEAN_WORKTREE_RUN: rm -f $WORKTREE/.runtime (symlink unlink)"
  else
    rm -f "$WORKTREE/.runtime"
    echo "CLEAN_WORKTREE_DEPS_UNLINKED: .runtime symlink"
  fi
fi

# v2.1（DEC-114）：ORCA 模式下额外清理 ORCA 跟踪的 worktree（tmux 路径不会自动同步）。
# 用 run() 包装保持 dry-run 友好；ORCA 不可用 / 无 worktree_id 时跳过（不阻塞 git 清理）。
if [ -n "${metadata_orca_worktree_id:-}" ] && [ "$KEEP_WORKTREE" -eq 0 ]; then
  if orca_runtime_init >/dev/null 2>&1; then
    if [ "$EXECUTE" -eq 0 ]; then
      echo "CLEAN_WORKTREE_RUN: $ORCA_CLI_BIN worktree rm --worktree id:$metadata_orca_worktree_id --force"
    else
      orca_cli worktree rm --worktree "id:$metadata_orca_worktree_id" --force --json
    fi
  else
    echo "CLEAN_WORKTREE_ORCA: orca CLI not found, skip ORCA worktree rm (worktree_id=$metadata_orca_worktree_id)"
  fi
fi

# The worker process/terminal has been closed or the entire Orca worktree has
# been removed at this point. Release only the exact metadata-bound lease.
if [ "$KEEP_SESSION" -eq 0 ] || \
   { [ -n "${metadata_orca_worktree_id:-}" ] && [ "$KEEP_WORKTREE" -eq 0 ]; }; then
  release_provider_lease
fi

if [ "$KEEP_WORKTREE" -eq 0 ]; then
  if [ -n "$WORKTREE" ] && [ -d "$WORKTREE" ]; then
    dirty_count=$(git -C "$WORKTREE" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    echo "CLEAN_WORKTREE_DIRTY: $dirty_count"
    if [ "$dirty_count" != "0" ] && [ "$FORCE_DIRTY" -eq 0 ]; then
      echo "CLEAN_WORKTREE_REFUSED: dirty worktree; rerun with --force-remove-dirty after review" >&2
      [ "$EXECUTE" -eq 1 ] && exit 2
    elif [ "$FORCE_DIRTY" -eq 1 ]; then
      run git -C "$PROJECT_DIR" worktree remove --force "$WORKTREE"
    else
      run git -C "$PROJECT_DIR" worktree remove "$WORKTREE"
    fi
  else
    echo "CLEAN_WORKTREE_WORKTREE: missing"
  fi
else
  echo "CLEAN_WORKTREE_WORKTREE: kept"
fi

if [ "$DELETE_BRANCH" -eq 1 ]; then
  if git -C "$PROJECT_DIR" show-ref --verify --quiet "refs/heads/$BRANCH"; then
    if [ "$EXECUTE" -eq 0 ]; then
      echo "CLEAN_WORKTREE_RUN: git -C $PROJECT_DIR branch -d $BRANCH"
    elif git -C "$PROJECT_DIR" branch -d "$BRANCH" >/dev/null 2>&1; then
      echo "CLEAN_WORKTREE_BRANCH_DELETED: branch=$BRANCH"
    elif [ "$FORCE_DELETE_BRANCH" -eq 1 ]; then
      # squash/rebase merge 后分支 tip 不可达 main，安全 -d 必拒。只有调用方已独立
      # 证明 MERGED + head 精确一致（如 post-merge-cleanup.sh 的门禁）才允许 -D。
      echo "CLEAN_WORKTREE_BRANCH_FORCE_DELETED: branch=$BRANCH reason=safe_delete_refused_caller_merge_evidence"
      git -C "$PROJECT_DIR" branch -D "$BRANCH" >/dev/null
      echo "CLEAN_WORKTREE_BRANCH_DELETED: branch=$BRANCH mode=force"
    else
      echo "CLEAN_WORKTREE_BRANCH_REFUSED: git branch -d refused branch=$BRANCH; escalate with --force-delete-branch only after independent MERGED evidence" >&2
      exit 2
    fi
  else
    echo "CLEAN_WORKTREE_BRANCH: missing branch=$BRANCH"
  fi
else
  echo "CLEAN_WORKTREE_BRANCH: kept branch=$BRANCH"
fi

[ "$EXECUTE" -eq 1 ] && echo "CLEAN_WORKTREE_DONE" || echo "CLEAN_WORKTREE_DRY_RUN_DONE"
