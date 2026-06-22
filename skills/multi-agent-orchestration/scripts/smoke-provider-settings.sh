#!/usr/bin/env bash
# smoke-provider-settings.sh — verify each config/*.settings.json can launch
# Claude Code and get a non-error response.
#
# For every settings file (except the .example template), this script:
#   1. extracts the HAIKU model name from the file
#   2. runs `claude --settings <file> --model <model>` with a deterministic prompt
#   3. checks the response contains the expected token
#
# Why --model: per testing, Claude Code's --model flag is the only thing that
# reliably overrides ANTHROPIC_DEFAULT_*_MODEL in the user's global
# ~/.claude/settings.json. Without --model, the global config wins.
#
# Usage:
#   bash scripts/smoke-provider-settings.sh
#
# Exit codes:
#   0  all settings files passed
#   1  one or more settings files failed
#   2  no settings files found / missing tooling

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CONFIG_DIR="$SCRIPT_DIR/../config"

PROMPT_TEMPLATE='Reply with exactly: %s'

# Build the list of test targets. Skip the example template.
mapfile -t TEST_FILES < <(find "$CONFIG_DIR" -maxdepth 1 -type f -name '*.settings.json' \
  ! -name 'claude-provider-settings.example.json' | sort)

if [ ${#TEST_FILES[@]} -eq 0 ]; then
  echo "ERROR: no *.settings.json found in $CONFIG_DIR" >&2
  exit 2
fi

# Pick a JSON parser. jq is preferred; fall back to python3.
if command -v jq >/dev/null 2>&1; then
  extract_model() {
    jq -r '.env.ANTHROPIC_DEFAULT_HAIKU_MODEL // empty' "$1"
  }
elif command -v python3 >/dev/null 2>&1; then
  extract_model() {
    python3 -c '
import json, sys
with open(sys.argv[1]) as fh:
    d = json.load(fh)
print(d.get("env", {}).get("ANTHROPIC_DEFAULT_HAIKU_MODEL", ""))
' "$1"
  }
else
  echo "ERROR: need either jq or python3 to parse settings files" >&2
  exit 2
fi

PASS=0
FAIL=0
FAILED_FILES=()

printf '%-44s %-30s %s\n' 'Settings' 'Model' 'Result'
printf '%-44s %-30s %s\n' '-------' '-----' '------'

for f in "${TEST_FILES[@]}"; do
  name=$(basename "$f" .settings.json)
  model=$(extract_model "$f")

  if [ -z "$model" ]; then
    printf '%-44s %-30s SKIP (no HAIKU model)\n' "$name" '-'
    continue
  fi

  # Token derived from the file name so a passing response proves the right
  # file is wired up.
  token=$(printf '%s_OK' "$name" | tr '[:lower:]-' '[:upper:]')
  prompt=$(printf "$PROMPT_TEMPLATE" "$token")

  response=$(printf '%s' "$prompt" \
    | claude --settings "$f" --model "$model" \
        -p --output-format text --permission-mode acceptEdits 2>&1 \
    || true)

  if printf '%s' "$response" | grep -qF "$token"; then
    printf '%-44s %-30s PASS\n' "$name" "$model"
    PASS=$((PASS + 1))
  else
    printf '%-44s %-30s FAIL\n' "$name" "$model"
    echo "  --- response (first 5 lines) ---"
    printf '%s\n' "$response" | head -5 | sed 's/^/  /'
    echo "  -------------------------------"
    FAIL=$((FAIL + 1))
    FAILED_FILES+=("$name")
  fi
done

echo ""
echo "=== Summary ==="
echo "Pass: $PASS"
echo "Fail: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo "Failed files: ${FAILED_FILES[*]}"
  exit 1
fi
exit 0
