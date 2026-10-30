#!/usr/bin/env bash
# Optional local session probe; use a JSON parser instead of matching chat prose.
set -eu
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
command -v python3 >/dev/null 2>&1 || {
    printf 'probe-session-model.sh: Python 3 required for session probing; use --model instead.\n' >&2
    exit 2
}
exec python3 "${SCRIPT_DIR}/session-model.py" "$@"
