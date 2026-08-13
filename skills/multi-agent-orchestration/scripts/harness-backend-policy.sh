#!/usr/bin/env bash
# Resolve the current PM harness from verifiable runtime evidence and enforce
# which worker backend that harness may dispatch.

set -euo pipefail

POLICY_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HARNESS_BACKEND_POLICY_FILE="$POLICY_SCRIPT_DIR/../config/harness-backend-policy.json"
# shellcheck source=orca-runtime.sh
source "$POLICY_SCRIPT_DIR/orca-runtime.sh"

canonical_harness_backend() {
  case "${1:-}" in
    claude|claude-code|claude_code) printf '%s\n' "claude-code" ;;
    codex) printf '%s\n' "codex" ;;
    codebuddy|workbuddy) printf '%s\n' "codebuddy" ;;
    qoder|qoderwork|qoderwork-cn|qoderclicn) printf '%s\n' "qoderwork-cn" ;;
    *) return 1 ;;
  esac
}

pm_harness_from_orca() {
  command -v jq >/dev/null 2>&1 || return 1
  orca_runtime_init >/dev/null 2>&1 || return 1

  local project_path="${1:-}" current_path ps_json agent_type agent_type_count match_count
  current_path=$(orca_cli worktree current --json 2>/dev/null \
    | jq -r '.result.worktree.path // empty' 2>/dev/null) || return 1
  [ -n "$current_path" ] || return 1
  if [ -n "$project_path" ]; then
    project_path=$(cd "$project_path" 2>/dev/null && pwd -P) || return 1
    [ "$current_path" = "$project_path" ] || return 1
  fi

  ps_json=$(orca_cli worktree ps --limit 100 --json 2>/dev/null) || return 1
  match_count=$(printf '%s' "$ps_json" | jq --arg path "$current_path" \
    '[.result.worktrees[]? | select(.path == $path)] | length' 2>/dev/null) || return 1
  [ "$match_count" = "1" ] || {
    [ "$match_count" = "0" ] && return 1
    return 65
  }
  agent_type_count=$(printf '%s' "$ps_json" | jq -r --arg path "$current_path" '
    [.result.worktrees[]? | select(.path == $path) | .agents[]? | select(.state == "working") | .agentType]
    | unique
    | length
  ' 2>/dev/null) || return 1
  [ "$agent_type_count" = "1" ] || {
    [ "$agent_type_count" = "0" ] && return 1
    return 65
  }
  agent_type=$(printf '%s' "$ps_json" | jq -r --arg path "$current_path" '
    [.result.worktrees[]? | select(.path == $path) | .agents[]? | select(.state == "working") | .agentType]
    | unique
    | if length == 1 then .[0] else empty end
  ' 2>/dev/null) || return 1
  [ -n "$agent_type" ] || return 1
  canonical_harness_backend "$agent_type" || return 66
}

pm_harness_from_process() {
  local pid="${1:-$PPID}" depth=0 ppid executable args normalized candidate="" nearest="" last=""
  local chain=()
  while [ "$pid" -gt 1 ] 2>/dev/null && [ "$depth" -lt 24 ]; do
    ppid=$(ps -p "$pid" -o ppid= 2>/dev/null | tr -d ' ') || return 67
    executable=$(ps -p "$pid" -o comm= 2>/dev/null) || return 67
    args=$(ps -p "$pid" -o args= 2>/dev/null) || return 67
    # Only inspect the executable and, for Node, its script path. Never scan the
    # full argument string: task/prompt text can contain backend names.
    normalized=$(python3 - "$executable" "$args" <<'PY'
import os, shlex, sys
executable, args = sys.argv[1:]
parts = [executable]
try:
    argv = shlex.split(args, posix=True)
except ValueError:
    argv = []
if os.path.basename(executable).lower() in {"node", "nodejs"} and len(argv) > 1:
    parts.append(argv[1])
print(" ".join(parts).lower())
PY
)
    candidate=""
    case "$normalized" in
      *"qoderclicn"*|*"qoderwork cn"*) candidate="qoderwork-cn" ;;
      *"codebuddy"*|*"workbuddy"*) candidate="codebuddy" ;;
      *"/codex"*|codex) candidate="codex" ;;
      *"/claude"*|claude) candidate="claude-code" ;;
    esac
    [ -z "$candidate" ] || {
      if [ -z "$nearest" ]; then
        nearest="$candidate"
      fi
      # Keep the complete recognized ancestry. Consecutive duplicate frames
      # come from launch wrappers and do not change the authority intersection.
      if [ "$candidate" != "$last" ]; then
        chain+=("$candidate")
        last="$candidate"
      fi
    }
    case "$ppid" in ''|*[!0-9]*) return 67 ;; esac
    pid="$ppid"
    depth=$((depth + 1))
  done
  # A truncated chain cannot prove that there is no weaker outer harness.
  [ "$pid" -le 1 ] 2>/dev/null || return 67
  [ -n "$nearest" ] || return 1
  printf '%s\n' "$nearest"
  printf '%s\n' "${chain[@]}" | jq -R . | jq -c -s .
}

allowed_worker_backends_for_chain_json() {
  local chain_json="$1"
  [ -f "$HARNESS_BACKEND_POLICY_FILE" ] || {
    echo "ERROR: harness backend policy file is missing: $HARNESS_BACKEND_POLICY_FILE" >&2
    return 64
  }
  jq -er --argjson chain "$chain_json" '
    select(.schema == "multi-agent-orchestration.harness-backend-policy.v1")
    | select(.policy == "deny_by_default")
    | . as $policy
    | select(($chain | type) == "array" and ($chain | length) > 0)
    | select(all($chain[]; ($policy.hosts[.] | type) == "array" and ($policy.hosts[.] | length) > 0))
    | reduce $chain[] as $host (
        null;
        if . == null then $policy.hosts[$host]
        else [.[] as $candidate | select($policy.hosts[$host] | index($candidate)) | $candidate]
        end
      )
    | select(type == "array" and length > 0)
    | join(" ")
  ' "$HARNESS_BACKEND_POLICY_FILE" 2>/dev/null || {
    printf 'ERROR: Harness ancestry has no valid least-privilege intersection: %s (fail-closed)\n' \
      "$chain_json" >&2
    return 64
  }
}

detect_pm_harness() {
  local project_path="${1:-}" process_host="" process_evidence="" process_chain_json=""
  local orca_host="" orca_rc=0 process_rc=0 effective_allowed=""
  process_evidence=$(pm_harness_from_process "$PPID" 2>/dev/null) || process_rc=$?
  if [ "$process_rc" -eq 67 ]; then
    echo "ERROR: process ancestry is incomplete; cannot prove the least-privilege harness chain (fail-closed)" >&2
    return 64
  fi
  process_host=$(printf '%s\n' "$process_evidence" | sed -n '1p')
  process_chain_json=$(printf '%s\n' "$process_evidence" | sed -n '2p')
  orca_host=$(pm_harness_from_orca "$project_path" 2>/dev/null) || orca_rc=$?

  if [ "$orca_rc" -eq 66 ]; then
    echo "ERROR: Orca reports an unsupported working-agent identity for the current worktree (fail-closed)" >&2
    return 64
  fi
  if [ "$orca_rc" -eq 65 ] && [ -z "$process_host" ]; then
    echo "ERROR: Orca reports multiple working-agent identities and process ancestry cannot identify the current PM (fail-closed)" >&2
    return 64
  fi
  if [ "$orca_rc" -eq 65 ] && [ -n "$process_host" ]; then
    echo "HARNESS_BACKEND_POLICY_ORCA_AMBIGUOUS: multiple working agents; process ancestry remains authoritative" >&2
    orca_host=""
  fi

  if [ -n "$process_host" ] && [ -n "$orca_host" ] && [ "$process_host" != "$orca_host" ]; then
    printf 'ERROR: PM harness evidence conflicts: process=%s orca=%s (fail-closed)\n' \
      "$process_host" "$orca_host" >&2
    return 64
  fi
  if [ -n "$process_host" ]; then
    effective_allowed=$(allowed_worker_backends_for_chain_json "$process_chain_json") || return $?
    PM_HARNESS_SOURCE="process_ancestry_least_privilege"
    DETECTED_PM_HARNESS="$process_host"
    PM_HARNESS_CHAIN_JSON="$process_chain_json"
    return 0
  fi
  if [ -n "$orca_host" ]; then
    process_chain_json=$(jq -cn --arg host "$orca_host" '[$host]')
    effective_allowed=$(allowed_worker_backends_for_chain_json "$process_chain_json") || return $?
    PM_HARNESS_SOURCE="orca_working_agent"
    DETECTED_PM_HARNESS="$orca_host"
    PM_HARNESS_CHAIN_JSON="$process_chain_json"
    return 0
  fi
  echo "ERROR: cannot prove the current PM harness from process ancestry or Orca working-agent state (fail-closed)" >&2
  return 64
}

allowed_worker_backends_for_pm() {
  local pm_harness
  pm_harness=$(canonical_harness_backend "$1") || return 1
  [ -f "$HARNESS_BACKEND_POLICY_FILE" ] || {
    echo "ERROR: harness backend policy file is missing: $HARNESS_BACKEND_POLICY_FILE" >&2
    return 64
  }
  jq -er --arg host "$pm_harness" '
    select(.schema == "multi-agent-orchestration.harness-backend-policy.v1")
    | select(.policy == "deny_by_default")
    | .hosts[$host]
    | select(type == "array" and length > 0)
    | join(" ")
  ' "$HARNESS_BACKEND_POLICY_FILE" 2>/dev/null || {
    echo "ERROR: invalid or missing policy for PM harness: $pm_harness" >&2
    return 64
  }
}

enforce_harness_backend_policy() {
  local pm_harness worker_backend chain_json
  pm_harness=$(canonical_harness_backend "$1") || {
    echo "ERROR: unsupported PM harness identity: ${1:-<empty>} (fail-closed)" >&2
    return 64
  }
  chain_json=$(jq -cn --arg host "$pm_harness" '[$host]')
  enforce_harness_backend_policy_chain "$pm_harness" "$chain_json" "$2"
}

enforce_harness_backend_policy_chain() {
  local pm_harness="$1" chain_json="$2" worker_backend allowed item
  worker_backend=$(canonical_harness_backend "$3") || {
    echo "ERROR: worker backend is outside the configured harness policy: ${3:-<empty>} (fail-closed)" >&2
    return 64
  }
  allowed=$(allowed_worker_backends_for_chain_json "$chain_json") || return $?
  for item in $allowed; do
    if [ "$item" = "$worker_backend" ]; then
      PM_HARNESS="$pm_harness"
      PM_HARNESS_CHAIN_JSON="$chain_json"
      WORKER_BACKEND_CANONICAL="$worker_backend"
      PM_ALLOWED_WORKER_BACKENDS="$allowed"
      return 0
    fi
  done
  printf 'ERROR: harness backend policy denied pm=%s worker=%s allowed=%s (fail-closed)\n' \
    "$pm_harness" "$worker_backend" "$allowed" >&2
  return 64
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  project_path=""
  pm_harness=""
  worker_backend=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --project) project_path="$2"; shift 2 ;;
      --pm-harness) pm_harness="$2"; shift 2 ;;
      --worker-backend) worker_backend="$2"; shift 2 ;;
      *) echo "Usage: $0 [--project PATH] [--pm-harness NAME] --worker-backend NAME" >&2; exit 64 ;;
    esac
  done
  [ -n "$worker_backend" ] || { echo "ERROR: --worker-backend is required" >&2; exit 64; }
  DETECTED_PM_HARNESS=""
  detect_pm_harness "$project_path" || exit $?
  detected_pm="$DETECTED_PM_HARNESS"
  if [ -n "$pm_harness" ]; then
    asserted_pm=$(canonical_harness_backend "$pm_harness") || {
      echo "ERROR: unsupported --pm-harness: $pm_harness" >&2; exit 64;
    }
    [ "$asserted_pm" = "$detected_pm" ] || {
      echo "ERROR: --pm-harness=$asserted_pm conflicts with detected harness=$detected_pm; assertion cannot elevate authority" >&2
      exit 64
    }
  fi
  enforce_harness_backend_policy_chain "$detected_pm" "$PM_HARNESS_CHAIN_JSON" "$worker_backend"
  printf 'HARNESS_BACKEND_POLICY_OK pm=%s worker=%s allowed=%s chain=%s source=%s\n' \
    "$PM_HARNESS" "$WORKER_BACKEND_CANONICAL" "$PM_ALLOWED_WORKER_BACKENDS" \
    "$PM_HARNESS_CHAIN_JSON" "${PM_HARNESS_SOURCE:-verified_runtime}"
fi
