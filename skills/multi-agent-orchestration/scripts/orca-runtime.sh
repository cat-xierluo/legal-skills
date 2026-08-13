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
orca_runtime_current_project() {
  local project_dir="$1"
  local project_top current_json current_path current_id

  project_top=$(git -C "$project_dir" rev-parse --show-toplevel 2>/dev/null) || return 1
  # worktree current is cwd-scoped; ask from the project top even when the PM
  # invokes spawn-worker from another directory.
  current_json=$(cd "$project_top" && orca_cli worktree current --json 2>/dev/null) || return 1
  current_path=$(printf '%s' "$current_json" | jq -r '.result.worktree.path // empty' 2>/dev/null)
  current_id=$(printf '%s' "$current_json" | jq -r '.result.worktree.id // empty' 2>/dev/null)
  [ -n "$current_path" ] && [ -n "$current_id" ] || return 1
  [ "$current_path" = "$project_top" ] || return 1

  ORCA_CURRENT_WORKTREE_JSON="$current_json"
  ORCA_CURRENT_WORKTREE_ID="$current_id"
  ORCA_CURRENT_WORKTREE_PATH="$current_path"
  return 0
}
