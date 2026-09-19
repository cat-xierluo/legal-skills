#!/usr/bin/env bash
# Explicit PM identity shared by Wave preparation, spawn preflight and PM control.
# Source after orca-runtime.sh. No terminal-current/focus/pane fallback is allowed.

orca_coordinator_select() {
  local explicit="${1:-}" recorded="${2:-}" allow_environment="${3:-0}"
  ORCA_PM_SENDER="${explicit:-$recorded}"
  if [ -z "$ORCA_PM_SENDER" ] && [ "$allow_environment" = 1 ]; then
    ORCA_PM_SENDER="${ORCA_TERMINAL_HANDLE:-}"
  fi
  [ -n "$ORCA_PM_SENDER" ] || {
    echo "ORCA_COORDINATOR_MISSING: provide --from / --orca-coordinator-handle; no proven session sender is available" >&2
    return 3
  }
}

orca_coordinator_probe() {
  local expected_runtime="${1:-}" terminal_out
  orca_runtime_init || return $?
  orca_runtime_current_runtime_id || {
    echo "ORCA_COORDINATOR_UNVERIFIED: current runtime identity is unavailable" >&2
    return 3
  }
  [ -z "$expected_runtime" ] || [ "$expected_runtime" = "$ORCA_RUNTIME_ID_NOW" ] || {
    echo "ORCA_COORDINATOR_STALE: recorded runtime differs from current runtime" >&2
    return 3
  }
  ORCA_PM_RUNTIME_ID="$ORCA_RUNTIME_ID_NOW"
  terminal_out=$(orca_cli terminal show --terminal "$ORCA_PM_SENDER" --json 2>&1) || {
    echo "ORCA_COORDINATOR_UNVERIFIED: terminal show failed for the selected sender: $terminal_out" >&2
    return 3
  }
  printf '%s' "$terminal_out" | jq -e --arg sender "$ORCA_PM_SENDER" --arg runtime "$ORCA_PM_RUNTIME_ID" '
    .ok == true and ._meta.runtimeId == $runtime
    and (.result.terminal | .handle == $sender and .connected == true
      and .writable == true and .orphaned == false and .exitCause == null)
  ' >/dev/null 2>&1 || {
    echo "ORCA_COORDINATOR_UNVERIFIED: sender handle/runtime must match a connected, writable, non-orphaned terminal" >&2
    return 3
  }
}

orca_coordinator_validate_run() {
  local receipt="$1" expected_run="$2"
  printf '%s' "$receipt" | jq -e --arg sender "$ORCA_PM_SENDER" \
    --arg run "$expected_run" --arg runtime "$ORCA_PM_RUNTIME_ID" '
      .ok == true and ._meta.runtimeId == $runtime
      and (.result.run | .id == $run
        and (.coordinator_handle // .coordinatorHandle) == $sender)
    ' >/dev/null 2>&1 || {
      echo "ORCA_COORDINATOR_RUN_MISMATCH: receipt must prove the exact Run, sender and runtime" >&2
      return 3
    }
}

orca_coordinator_current() {
  local expected_run="$1" current_out
  current_out=$(orca_cli orchestration run-current --from "$ORCA_PM_SENDER" --json 2>&1) || {
    echo "ORCA_COORDINATOR_UNVERIFIED: run-current failed: $current_out" >&2
    return 3
  }
  orca_coordinator_validate_run "$current_out" "$expected_run"
}

# mode=create/use performs one requested binding; mode=verify is entirely read-only.
# Exports the frozen identity and original mutation receipt only after read-back.
orca_coordinator_prepare() {
  local mode="$1" expected_run="${2:-}" expected_runtime="${3:-}" objective="${4:-}"
  orca_coordinator_probe "$expected_runtime" || return $?
  local frozen_runtime="$ORCA_PM_RUNTIME_ID"
  ORCA_PM_RUN_ID="$expected_run"
  ORCA_PM_RUN_RECEIPT=""
  case "$mode" in
    create)
      ORCA_PM_RUN_RECEIPT=$(orca_cli orchestration run-create --objective "$objective" --from "$ORCA_PM_SENDER" --json 2>&1) || {
        echo "ORCA_COORDINATOR_BIND_FAILED: run-create outcome requires inspection: $ORCA_PM_RUN_RECEIPT" >&2
        return 3
      }
      ORCA_PM_RUN_ID=$(printf '%s' "$ORCA_PM_RUN_RECEIPT" | jq -er '.result.run.id | select(type == "string" and length > 0)' 2>/dev/null) || return 3
      ;;
    use)
      [ -n "$expected_run" ] || return 3
      ORCA_PM_RUN_RECEIPT=$(orca_cli orchestration run-use --id "$expected_run" --from "$ORCA_PM_SENDER" --json 2>&1) || {
        echo "ORCA_COORDINATOR_BIND_FAILED: run-use outcome requires inspection: $ORCA_PM_RUN_RECEIPT" >&2
        return 3
      }
      ;;
    verify) [ -n "$expected_run" ] || return 3 ;;
    *) echo "ERROR: unknown coordinator preparation mode: $mode" >&2; return 64 ;;
  esac
  if [ "$mode" != verify ]; then
    orca_coordinator_validate_run "$ORCA_PM_RUN_RECEIPT" "$ORCA_PM_RUN_ID" || return $?
  fi
  orca_coordinator_current "$ORCA_PM_RUN_ID" || return $?
  # Binding may succeed while the terminal closes or the runtime restarts.
  orca_coordinator_probe "$frozen_runtime" || return $?
}
