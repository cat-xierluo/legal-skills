#!/usr/bin/env bash
# One-shot quota classifier and guarded PM-terminal wake-up.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=orca-runtime.sh
source "$SCRIPT_DIR/orca-runtime.sh"

EXIT_QUOTA=10
EXIT_AVAILABLE_UNARMED=11
EXIT_CONFIG=12
EXIT_AUTH=13
EXIT_NETWORK=14
EXIT_TIMEOUT=15
EXIT_UNKNOWN=16
EXIT_TERMINAL_SHOW=17
EXIT_TERMINAL_SEND=18

usage() {
  cat <<'USAGE'
Usage: pm-quota-stall.sh --terminal HANDLE --model MODEL [options]

Options:
  --armed                    Confirm this watcher previously observed quota
  --probe-timeout-seconds N  Probe timeout in seconds (default: 120)
  --settings PATH            Exact Claude settings file for the probed provider
  --settings-sha256 HEX      Require settings contents to keep this SHA-256
  --setting-sources SOURCES  Claude setting sources (default: empty)
  --wake-text TEXT           Text injected only for armed quota -> available
  --json                     Emit stable JSON state
  --help                     Show this help

Exit codes:
  0 wake sent; 10 quota; 11 available but unarmed; 12 config; 13 auth;
  14 network; 15 timeout; 16 unknown; 17 terminal show failed;
  18 terminal send failed; 64 invalid usage/dependency.
USAGE
}

is_positive_integer() {
  [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

require_value() {
  local argc=$1 flag=$2
  [ "$argc" -ge 2 ] || { echo "ERROR: $flag requires a value" >&2; exit 64; }
}

emit_result() {
  local classification=$1 action=$2
  if [ "$JSON" -eq 1 ]; then
    jq -cn --arg classification "$classification" --arg action "$action" \
      '{classification:$classification,action:$action}'
  else
    printf 'classification=%s action=%s\n' "$classification" "$action"
  fi
}

HANDLE=""
MODEL=""
ARMED=0
PROBE_TIMEOUT_SECONDS=120
SETTINGS=""
SETTINGS_SHA256=""
SETTING_SOURCES=""
WAKE_TEXT="【守夜脚本】已确认额度从受限恢复。请按看门狗清单继续 Autopilot。"
JSON=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --terminal) require_value "$#" "$1"; HANDLE=$2; shift 2 ;;
    --model) require_value "$#" "$1"; MODEL=$2; shift 2 ;;
    --armed) ARMED=1; shift ;;
    --probe-timeout-seconds)
      require_value "$#" "$1"
      is_positive_integer "$2" || { echo "ERROR: probe timeout must be a positive integer" >&2; exit 64; }
      PROBE_TIMEOUT_SECONDS=$2; shift 2 ;;
    --settings) require_value "$#" "$1"; SETTINGS=$2; shift 2 ;;
    --settings-sha256) require_value "$#" "$1"; SETTINGS_SHA256=$2; shift 2 ;;
    --setting-sources) require_value "$#" "$1"; SETTING_SOURCES=$2; shift 2 ;;
    --wake-text) require_value "$#" "$1"; WAKE_TEXT=$2; shift 2 ;;
    --json) JSON=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 64 ;;
  esac
done

[[ "$HANDLE" =~ ^[A-Za-z0-9._:-]+$ ]] || { echo "ERROR: invalid terminal handle" >&2; exit 64; }
[ -n "$MODEL" ] && [[ "$MODEL" != *$'\n'* ]] || { echo "ERROR: --model is required and must be one line" >&2; exit 64; }
[ -n "$WAKE_TEXT" ] || { echo "ERROR: wake text must not be empty" >&2; exit 64; }
[ -z "$SETTINGS" ] || [ -r "$SETTINGS" ] || { echo "ERROR: settings file is not readable" >&2; exit 64; }
[ "$ARMED" -ne 1 ] || [ -n "$SETTINGS" ] || { echo "ERROR: --armed requires an explicit provider settings file" >&2; exit 64; }
[ "$ARMED" -ne 1 ] || [ -z "$SETTING_SOURCES" ] || { echo "ERROR: --armed requires empty --setting-sources; use one explicit settings file" >&2; exit 64; }
[ -z "$SETTINGS_SHA256" ] || [[ "$SETTINGS_SHA256" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "ERROR: settings SHA-256 must be 64 hexadecimal characters" >&2; exit 64; }
[ -z "$SETTINGS_SHA256" ] || [ -n "$SETTINGS" ] || { echo "ERROR: --settings-sha256 requires --settings" >&2; exit 64; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }

CLAUDE_CLI_BIN=""
PYTHON_CLI_BIN=""
resolve_claude_cli() {
  local candidate=${CLAUDE_CLI_COMMAND:-claude}
  if [[ "$candidate" = /* ]]; then
    [ -x "$candidate" ] || { echo "ERROR: selected Claude CLI is not executable" >&2; return 64; }
    CLAUDE_CLI_BIN=$candidate
  else
    command -v "$candidate" >/dev/null 2>&1 || { echo "ERROR: selected Claude CLI is unavailable" >&2; return 64; }
    CLAUDE_CLI_BIN=$(command -v "$candidate")
  fi
}

resolve_python_cli() {
  local candidate=${PYTHON_CLI_COMMAND:-python3}
  if [[ "$candidate" = /* ]]; then
    [ -x "$candidate" ] || { echo "ERROR: selected Python runtime is not executable" >&2; return 64; }
    PYTHON_CLI_BIN=$candidate
  else
    command -v "$candidate" >/dev/null 2>&1 || { echo "ERROR: selected Python runtime is unavailable" >&2; return 64; }
    PYTHON_CLI_BIN=$(command -v "$candidate")
  fi
}

orca_runtime_init >/dev/null
resolve_claude_cli
resolve_python_cli

settings_digest() {
  "$PYTHON_CLI_BIN" - "$SETTINGS" <<'PY'
import hashlib
import sys

digest = hashlib.sha256()
with open(sys.argv[1], "rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
}

if [ -n "$SETTINGS_SHA256" ]; then
  current_settings_sha256=$(settings_digest 2>/dev/null || true)
  if [ "${current_settings_sha256,,}" != "${SETTINGS_SHA256,,}" ]; then
    emit_result config settings_identity_changed
    exit "$EXIT_CONFIG"
  fi
fi

set +e
terminal_json=$(orca_cli terminal show --terminal "$HANDLE" --json 2>&1)
terminal_status=$?
set -e
if [ "$terminal_status" -ne 0 ] \
   || ! printf '%s' "$terminal_json" | jq -e --arg handle "$HANDLE" \
      '.ok == true
       and .result.terminal.handle == $handle
       and .result.terminal.connected == true
       and .result.terminal.writable == true' >/dev/null 2>&1; then
  emit_result unknown terminal_show_failed
  exit "$EXIT_TERMINAL_SHOW"
fi

TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/pm-quota-stall.XXXXXX")
PROBE_STDOUT="$TMP_ROOT/stdout"
PROBE_STDERR="$TMP_ROOT/stderr"
PROBE_RESULT="$TMP_ROOT/result"

# shellcheck disable=SC2329  # Invoked through EXIT trap.
cleanup_probe() {
  rm -rf "$TMP_ROOT"
}
# shellcheck disable=SC2329  # Invoked through signal traps.
handle_signal() {
  exit 130
}
trap cleanup_probe EXIT
trap handle_signal HUP INT TERM

probe_args=(
  -p ok
  --model "$MODEL"
  --tools ""
  --disable-slash-commands
  --strict-mcp-config
  --mcp-config '{"mcpServers":{}}'
  --no-session-persistence
  --no-chrome
  --setting-sources "$SETTING_SOURCES"
)
[ -n "$SETTINGS" ] && probe_args+=(--settings "$SETTINGS")

set +e
"$PYTHON_CLI_BIN" - "$PROBE_TIMEOUT_SECONDS" "$PROBE_STDOUT" "$PROBE_STDERR" "$PROBE_RESULT" \
  "$CLAUDE_CLI_BIN" "${probe_args[@]}" <<'PY'
import os
import signal
import subprocess
import sys

timeout = int(sys.argv[1])
stdout_path, stderr_path, result_path = sys.argv[2:5]
command = sys.argv[5:]

with open(stdout_path, "wb") as stdout_file, open(stderr_path, "wb") as stderr_file:
    try:
        process = subprocess.Popen(
            command,
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=True,
        )
        try:
            return_code = process.wait(timeout=timeout)
            result = f"exit:{return_code}"
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            result = "timeout"
    except Exception:
        result = "wrapper_error"

with open(result_path, "w", encoding="utf-8") as result_file:
    result_file.write(result + "\n")
PY
wrapper_status=$?
set -e

if [ "$wrapper_status" -ne 0 ] || [ ! -r "$PROBE_RESULT" ]; then
  emit_result unknown fail_closed
  exit "$EXIT_UNKNOWN"
fi
probe_result=$(sed -n '1p' "$PROBE_RESULT")

if [ "$probe_result" = timeout ]; then
  emit_result timeout none
  exit "$EXIT_TIMEOUT"
fi

if [[ "$probe_result" == exit:* ]]; then
  probe_status=${probe_result#exit:}
else
  emit_result unknown fail_closed
  exit "$EXIT_UNKNOWN"
fi

if [ "$probe_status" -eq 0 ]; then
  if [ "$ARMED" -ne 1 ]; then
    emit_result available fail_closed_unarmed
    exit "$EXIT_AVAILABLE_UNARMED"
  fi

  if [ -n "$SETTINGS_SHA256" ]; then
    current_settings_sha256=$(settings_digest 2>/dev/null || true)
    if [ "${current_settings_sha256,,}" != "${SETTINGS_SHA256,,}" ]; then
      emit_result config settings_identity_changed
      exit "$EXIT_CONFIG"
    fi
  fi

  set +e
  send_json=$(orca_cli terminal send --terminal "$HANDLE" --text "$WAKE_TEXT" --enter --json 2>&1)
  send_status=$?
  set -e
  if [ "$send_status" -ne 0 ] \
     || ! printf '%s' "$send_json" | jq -e '.ok == true' >/dev/null 2>&1; then
    emit_result available terminal_send_failed
    exit "$EXIT_TERMINAL_SEND"
  fi
  emit_result available wake_sent
  exit 0
fi

combined_error=$(LC_ALL=C tr '[:upper:]' '[:lower:]' < "$PROBE_STDERR"; LC_ALL=C tr '[:upper:]' '[:lower:]' < "$PROBE_STDOUT")

if printf '%s' "$combined_error" | grep -Eiq '(^|[^0-9])(401|403)([^0-9]|$)|unauthori[sz]ed|forbidden|authentication|invalid[[:space:]_-]*(api[[:space:]_-]*)?key|login[[:space:]]+required|not[[:space:]]+logged[[:space:]]+in'; then
  emit_result auth fail_closed
  exit "$EXIT_AUTH"
fi
if printf '%s' "$combined_error" | grep -Eiq '(^|[^0-9])400([^0-9]|$)|bad[[:space:]]+request|invalid.*model|model.*(not[[:space:]_-]*found|does[[:space:]]+not[[:space:]]+exist|unsupported|unknown)|modelcode|config(uration)?[[:space:]_-]*error|unknown[[:space:]]+option|usage:[[:space:]]*claude'; then
  emit_result config fail_closed
  exit "$EXIT_CONFIG"
fi
if printf '%s' "$combined_error" | grep -Eiq 'network|connection|connect[[:space:]_-]*(failed|refused|reset)|dns|econn|enotfound|socket|tls|certificate|request[[:space:]]+timed[[:space:]]+out|temporary[[:space:]]+failure'; then
  emit_result network retry_manually
  exit "$EXIT_NETWORK"
fi
if printf '%s' "$combined_error" | grep -Eiq '(^|[^0-9])429([^0-9]|$)|rate[ _-]?limit|usage[ _-]?limit|quota[[:space:]_-]*(exceed|exhaust|deplet|limit|reset)|credits?[[:space:]].*(exhaust|deplet)|hit[[:space:]]+(your[[:space:]]+)?limit|limit[[:space:]]+resets?'; then
  emit_result quota wait
  exit "$EXIT_QUOTA"
fi

emit_result unknown fail_closed
exit "$EXIT_UNKNOWN"
