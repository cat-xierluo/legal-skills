#!/usr/bin/env bash
# spawn-worker-provider-lease.sh — provider concurrency lease lifecycle helpers.
# This file is sourced after spawn-worker.sh initializes provider/runtime globals.

resolve_provider_lease_limit() {
  [ -f "$PERSONAL_CONFIG_FILE" ] || return 1
  PROVIDER_LEASE_LIMIT=$(jq -er --arg backend "$WORKER_BACKEND_CANONICAL" '
    (.concurrency.per_backend[$backend] // .concurrency.max_per_provider // empty)
    | select(type == "number" and floor == . and . > 0)
  ' "$PERSONAL_CONFIG_FILE" 2>/dev/null) || return 1
  PROVIDER_LEASE_KEY="${API_PROVIDER:-backend:$WORKER_BACKEND_CANONICAL}"
  return 0
}

acquire_provider_lease() {
  resolve_provider_lease_limit || {
    echo "SPAWN_WORKER_PROVIDER_LEASE: provider=${API_PROVIDER:-backend:$WORKER_BACKEND_CANONICAL} limit=advisory_unconfigured"
    return 0
  }
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "SPAWN_WORKER_PROVIDER_LEASE: provider=$PROVIDER_LEASE_KEY max=$PROVIDER_LEASE_LIMIT state=dry-run-no-acquire"
    return 0
  fi
  local lease_out orca_path=""
  PROVIDER_LEASE_ROOT=$(provider_lease_root_for_project "$PROJECT_DIR") || {
    echo "ERROR: cannot derive the trusted provider lease root" >&2
    exit 64
  }
  orca_runtime_init >/dev/null 2>&1 && orca_path="$ORCA_CLI_BIN"
  lease_out=$(python3 "$SCRIPT_DIR/provider-lease.py" acquire \
    --root "$PROVIDER_LEASE_ROOT" --provider "$PROVIDER_LEASE_KEY" \
    --backend "$WORKER_BACKEND_CANONICAL" --session "$SESSION" \
    --project "$PROJECT_DIR" --max "$PROVIDER_LEASE_LIMIT" --owner-pid $$ \
    --orca-cli "$orca_path") || {
    echo "ERROR: provider concurrency lease denied before branch/worktree creation (provider=$PROVIDER_LEASE_KEY max=$PROVIDER_LEASE_LIMIT)" >&2
    exit 75
  }
  PROVIDER_LEASE_FILE=$(printf '%s' "$lease_out" | jq -r '.lease_file // empty')
  [ -n "$PROVIDER_LEASE_FILE" ] || { echo "ERROR: provider lease response missing lease_file" >&2; exit 64; }
  PROVIDER_LEASE_ACQUIRED=1
  echo "SPAWN_WORKER_PROVIDER_LEASE: provider=$PROVIDER_LEASE_KEY max=$PROVIDER_LEASE_LIMIT file=$PROVIDER_LEASE_FILE state=provisional"
}

release_provisional_provider_lease() {
  local exit_code=$?
  trap - EXIT
  if [ "$PROVIDER_LEASE_ACQUIRED" -eq 1 ] && [ -n "$PROVIDER_LEASE_FILE" ]; then
    python3 "$SCRIPT_DIR/provider-lease.py" release --root "$PROVIDER_LEASE_ROOT" \
      --lease-file "$PROVIDER_LEASE_FILE" \
      --session "$SESSION" --resource-settled --owner-pid $$ >/dev/null 2>&1 || true
  fi
  exit "$exit_code"
}

finalize_provider_lease() {
  [ "$PROVIDER_LEASE_ACQUIRED" -eq 1 ] || return 0
  local transport resource_handle
  if [ "$ORCA_MODE" = "auto" ]; then
    transport="orca_terminal"
    resource_handle="$ORCA_TERMINAL_HANDLE"
  else
    transport="tmux"
    resource_handle="$SESSION"
  fi
  python3 "$SCRIPT_DIR/provider-lease.py" finalize \
    --root "$PROVIDER_LEASE_ROOT" \
    --lease-file "$PROVIDER_LEASE_FILE" --session "$SESSION" \
    --transport "$transport" --resource-handle "$resource_handle" >/dev/null || {
    echo "ERROR: provider lease could not bind the launched worker resource" >&2
    exit 75
  }
  PROVIDER_LEASE_ACQUIRED=0
  echo "SPAWN_WORKER_PROVIDER_LEASE: provider=$PROVIDER_LEASE_KEY file=$PROVIDER_LEASE_FILE state=active transport=$transport"
}
