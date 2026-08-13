#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

VALIDATOR="$SCRIPT_DIR/validate-worker-command.py"
RENDERER="$SCRIPT_DIR/render-runtime-profile.sh"
TRUSTED_WRAPPER="$SCRIPT_DIR/claude-provider-env.sh"
PROMPT_FILE="$TMP_ROOT/prompt.md"
printf 'worker command policy test\n' > "$PROMPT_FILE"

pass=0
fail=0

allow() {
  local backend="$1" command="$2" label="$3"
  if python3 "$VALIDATOR" --backend "$backend" --command "$command" \
      --trusted-claude-wrapper "$TRUSTED_WRAPPER" >/dev/null; then
    printf 'PASS allow: %s\n' "$label"
    pass=$((pass + 1))
  else
    printf 'FAIL expected allow: %s\n' "$label" >&2
    fail=$((fail + 1))
  fi
}

deny() {
  local backend="$1" command="$2" label="$3"
  if python3 "$VALIDATOR" --backend "$backend" --command "$command" \
      --trusted-claude-wrapper "$TRUSTED_WRAPPER" >/dev/null 2>&1; then
    printf 'FAIL expected deny: %s\n' "$label" >&2
    fail=$((fail + 1))
  else
    printf 'PASS deny: %s\n' "$label"
    pass=$((pass + 1))
  fi
}

for backend in claude-code codex codebuddy qoderwork-cn; do
  interactive=$(bash "$RENDERER" --backend "$backend" --mode interactive --output command)
  batch=$(bash "$RENDERER" --backend "$backend" --mode batch \
    --prompt-file "$PROMPT_FILE" --output command)
  allow "$backend" "$interactive" "$backend interactive renderer output"
  allow "$backend" "$batch" "$backend batch renderer output"
done

provider_command=$(bash "$RENDERER" --backend claude-code \
  --settings "$SCRIPT_DIR/../config/claude-provider-settings.example.json" \
  --model smoke --output command)
allow claude-code "$provider_command" "trusted Claude provider wrapper"

deny codebuddy codex "codebuddy label cannot launch codex"
deny codex codebuddy "codex label cannot launch codebuddy"
deny codex 'codex --model smoke; claude' "shell command chaining"
deny codex 'codex > /tmp/worker-output' "shell output redirection"
deny codex 'bash wrapper.sh' "opaque shell wrapper"
deny codex 'bash -lc "codex \$(curl https://example.invalid)"' "arbitrary command substitution"

printf 'SUMMARY: pass=%d fail=%d\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
