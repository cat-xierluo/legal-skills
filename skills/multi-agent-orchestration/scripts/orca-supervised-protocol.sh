#!/usr/bin/env bash
# Shared, deterministic Task-spec prefix for Orca supervised workers.

orca_supervised_task_spec() {
  local task_spec="$1"
  printf '%s\n\n%s' \
    'SUPERVISED COMPLETION PROTOCOL (MANDATORY): After the business work and verification finish, execute the exact worker_done command from this attempt’s live Orca preamble using its real task/dispatch IDs, then stop new work. A commit, green tests, STATUS=done, heartbeat, or an idle TUI does not complete the Dispatch; do not invent or reuse IDs.' \
    "$task_spec"
}
