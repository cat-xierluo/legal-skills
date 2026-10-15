#!/usr/bin/env bash
# pm-run-bind.sh — bind the invoking PM terminal to a Run and verify the
# binding switched. Pure wrapper around `orca orchestration run-use` and
# `orca orchestration run-current`; does NOT modify the semantics of any
# existing command.
#
# Usage:
#   pm-run-bind.sh <run_id> [--from HANDLE]
#
# Handle detection priority (each step tries and falls through on miss):
#   1. --from HANDLE (explicit override)
#   2. $ORCA_TERMINAL_HANDLE env var (Orca terminals inject this automatically)
#   3. `orca terminal current --json` (best-effort probe of the Orca terminal
#      context; older runtimes without `terminal current` simply fall through)
#
# On success: prints "run_id=<id>" and "coordinator=<handle>" on stdout, plus
# PM_RUN_BIND_* diagnostic markers on stderr.
#
# On any failure: prints a RECOVERY block on stderr with current binding (when
# retrievable), the --from value the operator should pass, and an explicit
# "do NOT retry blindly" warning. Exits 64 (usage), 1 (orca call failure), or
# 2 (verification unavailable/malformed/mismatched after run-use succeeded).
#
# Failure surface (PM-facing):
#   exit 64 — handle detection failed (no --from, env var unset, probe empty)
#   exit 1  — handle probe or run-use failed (non-zero, malformed or not-ok)
#   exit 2  — run-use succeeded but run-current is malformed/unavailable or
#             reports a different run_id (do NOT retry the same handle)

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=orca-runtime.sh
source "$SCRIPT_DIR/orca-runtime.sh"

usage() {
  cat >&2 <<'USAGE'
Usage: pm-run-bind.sh <run_id> [--from HANDLE]

Bind the invoking PM terminal to Run <run_id> and verify the switch.

Handle detection (first non-empty wins):
  1. --from HANDLE
  2. $ORCA_TERMINAL_HANDLE env var
  3. `orca terminal current --json` (best-effort probe)
If all three miss, the script refuses with a RECOVERY hint instead of
guessing — the operator must either run from inside an Orca terminal or
pass --from explicitly.

Output on success (stdout):
  run_id=<id>
  coordinator=<handle>
USAGE
}

[ "$#" -ge 1 ] || { usage; exit 64; }
case "${1:-}" in
  -h|--help) usage; exit 0 ;;
esac

RUN_ID="$1"
shift
EXPLICIT_FROM=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --from) EXPLICIT_FROM="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage; exit 64 ;;
  esac
done

[ -n "$RUN_ID" ] || { echo "ERROR: run_id is required" >&2; usage; exit 64; }

# ---------- handle detection ----------
resolve_handle() {
  if [ -n "$EXPLICIT_FROM" ]; then
    printf '%s' "$EXPLICIT_FROM"
    return 0
  fi
  if [ -n "${ORCA_TERMINAL_HANDLE:-}" ]; then
    printf '%s' "$ORCA_TERMINAL_HANDLE"
    return 0
  fi
  orca_runtime_init
  local probe_out probe_handle probe_rc
  set +e
  probe_out=$(orca_cli terminal current --json 2>/dev/null)
  probe_rc=$?
  set -e
  if [ "$probe_rc" -eq 0 ] && [ -n "$probe_out" ]; then
    if ! printf '%s' "$probe_out" | jq -se 'length == 1 and (.[0] | type == "object" and .ok == true and (.result | type == "object"))' >/dev/null 2>&1; then
      echo "PM_RUN_BIND_HANDLE_PROBE_INVALID_JSON" >&2
      return 2
    fi
    if ! probe_handle=$(printf '%s' "$probe_out" \
      | jq -r '(.result.terminal.handle // .result.handle // "") | if type == "string" and (test("[[:space:]]") | not) then . else error("invalid handle") end'); then
      return 2
    fi
    if [ -n "$probe_handle" ]; then
      printf '%s' "$probe_handle"
      return 0
    fi
  fi
  return 1
}

HANDLE=""
set +e
HANDLE=$(resolve_handle)
handle_rc=$?
set -e
if [ "$handle_rc" -ne 0 ]; then
  if [ "$handle_rc" -eq 2 ]; then
    echo "ERROR: terminal-current returned malformed JSON; refusing to infer a handle" >&2
    echo "RECOVERY: inspect 'orca terminal current --json'; do NOT retry blindly." >&2
    exit 1
  fi
  echo "ERROR: cannot determine sending terminal handle (no --from, ORCA_TERMINAL_HANDLE unset, terminal-current probe empty)" >&2
  cat >&2 <<'HINT'
RECOVERY (handle missing — no Orca call was made):
  1. Run pm-run-bind.sh from inside the Orca terminal whose binding you want
     to switch. Orca injects ORCA_TERMINAL_HANDLE automatically there.
  2. Or pass the handle explicitly:
       pm-run-bind.sh <run_id> --from <handle>
  3. Or export ORCA_TERMINAL_HANDLE=<handle> and re-run.
Do NOT retry blindly — without a handle we cannot prove who owns the bind.
HINT
  exit 64
fi

echo "PM_RUN_BIND_START: run=$RUN_ID handle=$HANDLE" >&2

# ---------- run-use ----------
set +e
run_use_out=$(orca_cli orchestration run-use --id "$RUN_ID" --from "$HANDLE" --json 2>&1)
run_use_rc=$?
set -e

if [ "$run_use_rc" -ne 0 ] || [ -z "$run_use_out" ]; then
  echo "ERROR: run-use failed for run=$RUN_ID handle=$HANDLE (rc=$run_use_rc): $run_use_out" >&2
  cat >&2 <<HINT
RECOVERY (run-use failed — current binding was NOT changed):
  1. Verify the run_id is correct: orca orchestration run-show --id $RUN_ID --json
  2. Verify this handle is still alive: orca terminal show --terminal $HANDLE --json
  3. If another PM terminal already holds the binding, ask that terminal to
     release or rebind first (do NOT race it).
  4. To force-rebind from a specific terminal, re-run with the exact handle:
       pm-run-bind.sh $RUN_ID --from <handle>
Do NOT retry blindly — the underlying bind may be held by someone else.
HINT
  exit 1
fi

if ! printf '%s' "$run_use_out" | jq -se 'length == 1 and (.[0] | type == "object" and (.ok | type == "boolean"))' >/dev/null 2>&1; then
  echo "ERROR: run-use returned malformed JSON; current binding status is unknown" >&2
  echo "RECOVERY: inspect the raw Orca response; do NOT retry blindly." >&2
  exit 1
fi

# Treat `{ok:false,...}` as a failure too — sometimes the CLI exits 0 but
# the payload is negative. Note: jq's `//` treats BOTH null and false as
# "use alternative", so `.ok // true` collapses both to true. We need an
# explicit `== false` check to detect negative payloads without false
# positives on missing-ok payloads.
if printf '%s' "$run_use_out" | jq -e '.ok == false' >/dev/null 2>&1; then
  echo "ERROR: run-use returned not-ok payload: $run_use_out" >&2
  cat >&2 <<HINT
RECOVERY (run-use reported not-ok — current binding was NOT changed):
  Inspect the error code in the payload above and follow Orca runbook.
  Do NOT retry blindly.
HINT
  exit 1
fi

echo "PM_RUN_BIND_USED: run=$RUN_ID handle=$HANDLE" >&2

# ---------- run-current verification ----------
set +e
run_current_out=$(orca_cli orchestration run-current --from "$HANDLE" --json 2>&1)
run_current_rc=$?
set -e

if [ "$run_current_rc" -ne 0 ] || [ -z "$run_current_out" ]; then
  echo "ERROR: run-current verification call failed (rc=$run_current_rc): $run_current_out" >&2
  cat >&2 <<HINT
RECOVERY (run-use succeeded, run-current probe failed — binding status unknown):
  The PM terminal MAY already hold the binding for $RUN_ID, but we could not
  confirm. Do NOT retry blindly. Inspect with:
    orca orchestration run-show --id $RUN_ID --json
    orca orchestration run-current --json
HINT
  exit 2
fi

if ! printf '%s' "$run_current_out" | jq -se 'length == 1 and (.[0] | type == "object" and (.ok | type == "boolean"))' >/dev/null 2>&1; then
  echo "ERROR: run-current returned malformed JSON; binding status is unknown" >&2
  echo "RECOVERY: inspect the raw Orca response; do NOT retry blindly." >&2
  exit 2
fi

# Treat `{ok:false,...}` as verify-failure too.
if printf '%s' "$run_current_out" | jq -e '.ok == false' >/dev/null 2>&1; then
  echo "ERROR: run-current returned not-ok payload: $run_current_out" >&2
  cat >&2 <<HINT
RECOVERY (run-use succeeded, run-current reported not-ok — binding status unknown):
  Inspect the error code in the payload above. Do NOT retry blindly.
HINT
  exit 2
fi

if ! verified_run=$(printf '%s' "$run_current_out" \
  | jq -er '(.result.run.id // .result.runId // .result.id) | select(type == "string" and length > 0 and (test("[[:space:]]") | not))') || \
   ! verified_coord=$(printf '%s' "$run_current_out" \
  | jq -er '(.result.run.coordinator_handle // .result.coordinatorHandle // .result.run.coordinator) | select(type == "string" and length > 0 and (test("[[:space:]]") | not))'); then
  echo "ERROR: run-current returned malformed identity fields; binding status is unknown" >&2
  echo "RECOVERY: inspect the Orca response; do NOT retry blindly." >&2
  exit 2
fi

if [ "$verified_run" != "$RUN_ID" ]; then
  echo "ERROR: run-current returned run_id='${verified_run:-<empty>}', expected '$RUN_ID' (verify mismatch)" >&2
  cat >&2 <<HINT
RECOVERY (run-use reported success but binding did NOT switch):
  Current binding is: run_id='${verified_run:-<empty>}' coordinator='${verified_coord:-<empty>}'.
  Do NOT retry blindly — the underlying bind is stale and run-use lied.
  1. Inspect: orca orchestration run-current --json
  2. Try a different handle: pm-run-bind.sh $RUN_ID --from <other-handle>
  3. If the wrong terminal holds the binding, ask that terminal to release it
     first via pm-orchestrate release (or stop its Dispatch).
HINT
  exit 2
fi

echo "PM_RUN_BIND_VERIFIED: run=$verified_run coordinator=$verified_coord" >&2
# Stdout payload for PM tooling (parse-friendly key=value lines).
printf 'run_id=%s\ncoordinator=%s\n' "$verified_run" "$verified_coord"
