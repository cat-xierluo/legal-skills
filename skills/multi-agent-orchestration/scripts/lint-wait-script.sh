#!/usr/bin/env bash
# lint-wait-script.sh — lint wait/monitor shell scripts for fragile bash patterns.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

usage() {
  cat >&2 <<'USAGE'
Usage:
  lint-wait-script.sh [SCRIPT ...]

When no script is provided, checks the bundled wait/monitor scripts.
The lint runs bash -n and a focused check for malformed bash substring
expansions such as ${VAR:0:N] or ${VAR:0:N without a closing }.
USAGE
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

if [ "$#" -eq 0 ]; then
  set -- \
    "$SCRIPT_DIR/wait-worker.sh" \
    "$SCRIPT_DIR/pm-monitor.sh" \
    "$SCRIPT_DIR/worktree-status.sh"
fi

status=0

for script in "$@"; do
  if [ ! -f "$script" ]; then
    echo "LINT_WAIT_SCRIPT_MISSING: $script" >&2
    status=1
    continue
  fi

  if ! bash -n "$script"; then
    echo "LINT_WAIT_SCRIPT_BASH_N_FAILED: $script" >&2
    status=1
  fi

  awk -v file="$script" '
    {
      line = $0
      search = line
      offset = 0
      while ((pos = index(search, "${")) > 0) {
        segment = substr(search, pos)
        close_pos = index(segment, "}")
        newline_segment = segment
        if (close_pos > 0) {
          newline_segment = substr(segment, 1, close_pos)
        }
        if (newline_segment ~ /^\$\{[A-Za-z_][A-Za-z0-9_]*:[0-9]+:[^}]*$/) {
          printf("LINT_WAIT_SCRIPT_SUBSTRING_UNCLOSED: %s:%d: %s\n", file, NR, line) > "/dev/stderr"
          failed = 1
          break
        }
        if (newline_segment ~ /^\$\{[A-Za-z_][A-Za-z0-9_]*:[0-9]+:[^}]*\]/) {
          printf("LINT_WAIT_SCRIPT_SUBSTRING_BRACKET: %s:%d: %s\n", file, NR, line) > "/dev/stderr"
          failed = 1
          break
        }
        if (close_pos == 0) {
          break
        }
        search = substr(segment, close_pos + 1)
      }
    }
    END { exit failed ? 1 : 0 }
  ' "$script" || status=1
done

if [ "$status" -eq 0 ]; then
  echo "LINT_WAIT_SCRIPT_OK"
fi

exit "$status"
