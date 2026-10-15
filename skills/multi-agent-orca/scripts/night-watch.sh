#!/usr/bin/env bash
# Bounded overnight quota watcher for Wave Autopilot.
# A wake-up is legal only after this process has observed an explicit quota
# failure and a later probe reports availability.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=orca-runtime.sh
source "$SCRIPT_DIR/orca-runtime.sh"

PM_QUOTA_STALL="$SCRIPT_DIR/pm-quota-stall.sh"
DEFAULT_INTERVAL_MINUTES=15
DEFAULT_MAX_HOURS=12
DEFAULT_PROBE_TIMEOUT_SECONDS=120

usage() {
  cat <<'USAGE'
Usage:
  night-watch.sh <PM-terminal-handle> [interval-minutes] [max-hours] <model>
  night-watch.sh --terminal HANDLE --model MODEL [options]

Options:
  --interval-minutes N       Probe interval in minutes (default: 15)
  --interval-seconds N       Probe interval in seconds (useful for tests)
  --max-hours N              Maximum watch duration in hours (default: 12)
  --max-seconds N            Maximum watch duration in seconds (useful for tests)
  --probe-timeout-seconds N  Timeout for one probe (default: 120)
  --settings PATH            Required provider/account settings authority
  --setting-sources SOURCES  Must remain empty for automated wake
  --state-dir PATH           Private lock/log directory
  --wake-text TEXT           Wake-up text injected after quota -> available
  --help                     Show this help

The legacy positional form requires MODEL as the fourth argument and an
explicit NIGHT_WATCH_SETTINGS environment variable. There is no provider-
specific default model or settings authority.
USAGE
}

is_positive_integer() {
  [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

require_value() {
  local argc=$1 flag=$2
  [ "$argc" -ge 2 ] || { echo "ERROR: $flag requires a value" >&2; exit 64; }
}

HANDLE=""
MODEL=""
INTERVAL_SECONDS=$((DEFAULT_INTERVAL_MINUTES * 60))
MAX_SECONDS=$((DEFAULT_MAX_HOURS * 3600))
PROBE_TIMEOUT_SECONDS=$DEFAULT_PROBE_TIMEOUT_SECONDS
SETTINGS="${NIGHT_WATCH_SETTINGS:-}"
SETTING_SOURCES=""
STATE_DIR="${NIGHT_WATCH_STATE_DIR:-${TMPDIR:-/tmp}/multi-agent-orchestration-night-watch}"
WAKE_TEXT="【守夜脚本】已确认额度从受限恢复。请按看门狗清单继续 Autopilot：检查 Dispatch 权威状态，唤醒未完成的 idle worker，并重建 recurring 看门狗。"

if [ "$#" -gt 0 ] && [[ "$1" != --* ]]; then
  [ "$#" -le 4 ] || { usage >&2; exit 64; }
  HANDLE=${1:-}
  interval_minutes=${2:-$DEFAULT_INTERVAL_MINUTES}
  max_hours=${3:-$DEFAULT_MAX_HOURS}
  MODEL=${4:-}
  is_positive_integer "$interval_minutes" || { echo "ERROR: interval-minutes must be a positive integer" >&2; exit 64; }
  is_positive_integer "$max_hours" || { echo "ERROR: max-hours must be a positive integer" >&2; exit 64; }
  INTERVAL_SECONDS=$((interval_minutes * 60))
  MAX_SECONDS=$((max_hours * 3600))
else
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --terminal) require_value "$#" "$1"; HANDLE=$2; shift 2 ;;
      --model) require_value "$#" "$1"; MODEL=$2; shift 2 ;;
      --interval-minutes)
        require_value "$#" "$1"
        is_positive_integer "$2" || { echo "ERROR: interval-minutes must be a positive integer" >&2; exit 64; }
        interval_minutes=$2
        INTERVAL_SECONDS=$((interval_minutes * 60)); shift 2 ;;
      --interval-seconds)
        require_value "$#" "$1"
        is_positive_integer "$2" || { echo "ERROR: interval-seconds must be a positive integer" >&2; exit 64; }
        INTERVAL_SECONDS=$2; shift 2 ;;
      --max-hours)
        require_value "$#" "$1"
        is_positive_integer "$2" || { echo "ERROR: max-hours must be a positive integer" >&2; exit 64; }
        max_hours=$2
        MAX_SECONDS=$((max_hours * 3600)); shift 2 ;;
      --max-seconds)
        require_value "$#" "$1"
        is_positive_integer "$2" || { echo "ERROR: max-seconds must be a positive integer" >&2; exit 64; }
        MAX_SECONDS=$2; shift 2 ;;
      --probe-timeout-seconds)
        require_value "$#" "$1"
        is_positive_integer "$2" || { echo "ERROR: probe-timeout-seconds must be a positive integer" >&2; exit 64; }
        PROBE_TIMEOUT_SECONDS=$2; shift 2 ;;
      --settings) require_value "$#" "$1"; SETTINGS=$2; shift 2 ;;
      --setting-sources) require_value "$#" "$1"; SETTING_SOURCES=$2; shift 2 ;;
      --state-dir) require_value "$#" "$1"; STATE_DIR=$2; shift 2 ;;
      --wake-text) require_value "$#" "$1"; WAKE_TEXT=$2; shift 2 ;;
      --help|-h) usage; exit 0 ;;
      *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 64 ;;
    esac
  done
fi

[[ "$HANDLE" =~ ^[A-Za-z0-9._:-]+$ ]] || { echo "ERROR: invalid terminal handle" >&2; exit 64; }
[ -n "$MODEL" ] && [[ "$MODEL" != *$'\n'* ]] || { echo "ERROR: --model is required and must be one line" >&2; exit 64; }
[ -n "$STATE_DIR" ] || { echo "ERROR: state directory must not be empty" >&2; exit 64; }
[ ! -L "$STATE_DIR" ] || { echo "ERROR: state directory must not be a symlink" >&2; exit 64; }
[ -n "$SETTINGS" ] && [ -r "$SETTINGS" ] || { echo "ERROR: an explicit readable --settings file is required" >&2; exit 64; }
[ -z "$SETTING_SOURCES" ] || { echo "ERROR: automated wake requires empty --setting-sources; use one explicit settings file" >&2; exit 64; }
[ -r "$PM_QUOTA_STALL" ] || { echo "ERROR: missing helper: $PM_QUOTA_STALL" >&2; exit 64; }

SETTINGS_SHA256=""
if [ -n "$SETTINGS" ]; then
  python_candidate=${PYTHON_CLI_COMMAND:-python3}
  if [[ "$python_candidate" != /* ]]; then
    python_candidate=$(command -v "$python_candidate" 2>/dev/null || true)
  fi
  [ -x "$python_candidate" ] || { echo "ERROR: selected Python runtime is unavailable" >&2; exit 64; }
  SETTINGS_SHA256=$("$python_candidate" - "$SETTINGS" <<'PY'
import hashlib
import sys

digest = hashlib.sha256()
with open(sys.argv[1], "rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
  )
  [[ "$SETTINGS_SHA256" =~ ^[0-9a-f]{64}$ ]] || { echo "ERROR: could not fingerprint settings" >&2; exit 64; }
fi

# Resolve Orca before acquiring the long-lived lock so dependency failures do
# not leave a misleading watcher instance behind.
orca_runtime_init >/dev/null

umask 077
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR" 2>/dev/null || true
[ -d "$STATE_DIR" ] && [ -O "$STATE_DIR" ] || {
  echo "ERROR: state directory must be an owned directory" >&2
  exit 64
}
LOCK_DIR="$STATE_DIR/lock.$HANDLE"
LOG_FILE="$STATE_DIR/night-watch.$HANDLE.log"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  owner="unknown"
  [ -r "$LOCK_DIR/pid" ] && owner=$(sed -n '1p' "$LOCK_DIR/pid")
  if [[ "$owner" =~ ^[1-9][0-9]*$ ]] && ! kill -0 "$owner" 2>/dev/null; then
    stale_lock="$STATE_DIR/stale.$HANDLE.$$"
    if mv "$LOCK_DIR" "$stale_lock" 2>/dev/null; then
      rm -f "$stale_lock/pid"
      rmdir "$stale_lock" 2>/dev/null || {
        echo "ERROR: stale watcher lock contains unexpected files; retained at $stale_lock" >&2
        exit 73
      }
      mkdir "$LOCK_DIR" 2>/dev/null || {
        echo "ERROR: watcher lock was concurrently reacquired for $HANDLE" >&2
        exit 73
      }
    else
      echo "ERROR: watcher lock changed while checking $HANDLE" >&2
      exit 73
    fi
  else
    echo "ERROR: watcher lock already exists for $HANDLE (pid $owner)" >&2
    exit 73
  fi
fi
printf '%s\n' "$$" > "$LOCK_DIR/pid"

cleanup_lock() {
  local owner=""
  [ -r "$LOCK_DIR/pid" ] && owner=$(sed -n '1p' "$LOCK_DIR/pid")
  if [ "$owner" = "$$" ]; then
    rm -f "$LOCK_DIR/pid"
    rmdir "$LOCK_DIR" 2>/dev/null || true
  fi
}
handle_signal() {
  exit 130
}
trap cleanup_lock EXIT
trap handle_signal HUP INT TERM

log_event() {
  printf '%s %s\n' "$(date '+%F %T')" "$1" >> "$LOG_FILE"
}

start_epoch=$(date +%s)
deadline=$((start_epoch + MAX_SECONDS))
armed=0
log_event "watch_started terminal=$HANDLE interval_seconds=$INTERVAL_SECONDS max_seconds=$MAX_SECONDS"

while :; do
  now=$(date +%s)
  if [ "$now" -ge "$deadline" ]; then
    log_event "watch_timeout action=none"
    exit 2
  fi

  remaining=$((deadline - now))
  effective_probe_timeout=$PROBE_TIMEOUT_SECONDS
  [ "$effective_probe_timeout" -le "$remaining" ] || effective_probe_timeout=$remaining
  args=(
    --terminal "$HANDLE"
    --model "$MODEL"
    --probe-timeout-seconds "$effective_probe_timeout"
    --setting-sources "$SETTING_SOURCES"
    --wake-text "$WAKE_TEXT"
    --json
  )
  [ -n "$SETTINGS" ] && args+=(--settings "$SETTINGS")
  [ -n "$SETTINGS_SHA256" ] && args+=(--settings-sha256 "$SETTINGS_SHA256")
  [ "$armed" -eq 1 ] && args+=(--armed)

  set +e
  result=$(bash "$PM_QUOTA_STALL" "${args[@]}" 2>&1)
  status=$?
  set -e

  case "$status" in
    0)
      log_event "quota_available wake_sent"
      exit 0
      ;;
    10)
      armed=1
      log_event "quota_limited armed=1"
      ;;
    11)
      log_event "available_without_quota_evidence fail_closed"
      printf '%s\n' "$result" >&2
      exit 11
      ;;
    *)
      log_event "probe_or_terminal_failure exit=$status"
      printf '%s\n' "$result" >&2
      exit "$status"
      ;;
  esac

  now=$(date +%s)
  remaining=$((deadline - now))
  [ "$remaining" -gt 0 ] || continue
  sleep_for=$INTERVAL_SECONDS
  [ "$sleep_for" -le "$remaining" ] || sleep_for=$remaining
  sleep "$sleep_for"
done
