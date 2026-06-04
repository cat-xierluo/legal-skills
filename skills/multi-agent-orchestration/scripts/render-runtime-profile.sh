#!/usr/bin/env bash
# render-runtime-profile.sh — render worker command and prompt context for one runtime profile.

set -euo pipefail

BACKEND=""
MODE="interactive"
RUNTIME_PROFILE=""
API_PROVIDER=""
MODEL=""
PROVIDER_SLOT=""
SETTINGS=""
CODEX_PROFILE=""
PROMPT_FILE=""
PERMISSION_MODE=""
SANDBOX="danger-full-access"
APPROVAL="never"
CUSTOM_COMMAND=""
OUTPUT="shell"

usage() {
  cat >&2 <<'USAGE'
Usage:
  render-runtime-profile.sh --backend BACKEND [options]

Backends:
  claude-code     Claude Code with provider/settings profile
  claude-oauth    Claude Code subscription/OAuth; clears Anthropic provider env
  codex           Codex CLI
  opencode        OpenCode CLI
  custom          Use --command as-is

Options:
  --mode MODE              interactive | batch. Default: interactive
  --runtime-profile NAME   Runtime/settings/profile label for prompt metadata
  --api-provider NAME      API/provider label for prompt metadata
  --model NAME             Model name
  --provider-slot SLOT     Provider concurrency slot label
  --settings PATH          Claude Code settings path
  --codex-profile NAME     Codex profile name
  --prompt-file PATH       Prompt file for batch mode
  --permission-mode MODE   Claude permission mode. Defaults: auto interactive, acceptEdits batch
  --sandbox MODE           Codex sandbox. Default: danger-full-access
  --approval POLICY        Codex approval policy. Default: never
  --command CMD            Custom backend command
  --output FORMAT          shell | command | prompt-context. Default: shell

The script only renders metadata and command strings. It does not create
worktrees, start tmux, send prompts, or run the worker.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend)
      BACKEND="$2"
      shift 2
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --runtime-profile)
      RUNTIME_PROFILE="$2"
      shift 2
      ;;
    --api-provider)
      API_PROVIDER="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    --provider-slot)
      PROVIDER_SLOT="$2"
      shift 2
      ;;
    --settings)
      SETTINGS="$2"
      shift 2
      ;;
    --codex-profile)
      CODEX_PROFILE="$2"
      shift 2
      ;;
    --prompt-file)
      PROMPT_FILE="$2"
      shift 2
      ;;
    --permission-mode)
      PERMISSION_MODE="$2"
      shift 2
      ;;
    --sandbox)
      SANDBOX="$2"
      shift 2
      ;;
    --approval)
      APPROVAL="$2"
      shift 2
      ;;
    --command)
      CUSTOM_COMMAND="$2"
      shift 2
      ;;
    --output)
      OUTPUT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 64
      ;;
  esac
done

[ -n "$BACKEND" ] || { usage; exit 64; }

case "$MODE" in
  interactive|batch) ;;
  *) echo "ERROR: --mode must be interactive or batch" >&2; exit 64 ;;
esac

case "$OUTPUT" in
  shell|command|prompt-context) ;;
  *) echo "ERROR: --output must be shell, command, or prompt-context" >&2; exit 64 ;;
esac

if [ "$MODE" = "batch" ] && [ -z "$PROMPT_FILE" ] && [ "$BACKEND" != "custom" ]; then
  echo "ERROR: --prompt-file is required for batch mode" >&2
  exit 64
fi

quote_words() {
  local out=""
  local word
  for word in "$@"; do
    printf -v quoted '%q' "$word"
    if [ -z "$out" ]; then
      out="$quoted"
    else
      out="$out $quoted"
    fi
  done
  printf '%s' "$out"
}

append_redirection() {
  local base="$1"
  local file="$2"
  printf '%s < %q' "$base" "$file"
}

COMMAND=""

case "$BACKEND" in
  claude-code|claude-oauth)
    if [ -z "$PERMISSION_MODE" ]; then
      [ "$MODE" = "batch" ] && PERMISSION_MODE="acceptEdits" || PERMISSION_MODE="auto"
    fi
    parts=(claude)
    [ -n "$SETTINGS" ] && parts+=(--settings "$SETTINGS")
    [ -n "$MODEL" ] && parts+=(--model "$MODEL")
    if [ "$MODE" = "batch" ]; then
      parts+=(-p --output-format stream-json --permission-mode "$PERMISSION_MODE")
    else
      parts+=(--permission-mode "$PERMISSION_MODE")
    fi
    COMMAND=$(quote_words "${parts[@]}")
    [ "$MODE" = "batch" ] && COMMAND=$(append_redirection "$COMMAND" "$PROMPT_FILE")
    if [ "$BACKEND" = "claude-oauth" ]; then
      COMMAND="env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL $COMMAND"
    fi
    ;;
  codex)
    if [ "$MODE" = "batch" ]; then
      parts=(codex exec -a "$APPROVAL" -s "$SANDBOX")
    else
      parts=(codex -a "$APPROVAL" -s "$SANDBOX")
    fi
    [ -n "$CODEX_PROFILE" ] && parts+=(-p "$CODEX_PROFILE")
    [ -n "$MODEL" ] && parts+=(-m "$MODEL")
    if [ "$MODE" = "batch" ]; then
      parts+=(-)
      COMMAND=$(quote_words "${parts[@]}")
      COMMAND=$(append_redirection "$COMMAND" "$PROMPT_FILE")
    else
      COMMAND=$(quote_words "${parts[@]}")
    fi
    ;;
  opencode)
    if [ "$MODE" = "batch" ]; then
      parts=(opencode run --format json)
      [ -n "$MODEL" ] && parts+=(--model "$MODEL")
      COMMAND="$(quote_words "${parts[@]}") \"\$(cat $(printf '%q' "$PROMPT_FILE"))\""
    else
      parts=(opencode)
      [ -n "$MODEL" ] && parts+=(--model "$MODEL")
      COMMAND=$(quote_words "${parts[@]}")
    fi
    ;;
  custom)
    [ -n "$CUSTOM_COMMAND" ] || { echo "ERROR: --command is required for custom backend" >&2; exit 64; }
    COMMAND="$CUSTOM_COMMAND"
    ;;
  *)
    echo "ERROR: unsupported backend: $BACKEND" >&2
    exit 64
    ;;
esac

if [ "$OUTPUT" = "command" ]; then
  printf '%s\n' "$COMMAND"
  exit 0
fi

if [ "$OUTPUT" = "prompt-context" ]; then
  cat <<EOF
- Worker Backend: $BACKEND
- Runtime Profile: $RUNTIME_PROFILE
- API Provider: $API_PROVIDER
- Model: $MODEL
- Provider Slot: $PROVIDER_SLOT
- Mode: $MODE
- Command: $COMMAND
EOF
  exit 0
fi

printf 'WORKER_BACKEND=%q\n' "$BACKEND"
printf 'RUNTIME_PROFILE=%q\n' "$RUNTIME_PROFILE"
printf 'API_PROVIDER=%q\n' "$API_PROVIDER"
printf 'MODEL=%q\n' "$MODEL"
printf 'PROVIDER_SLOT=%q\n' "$PROVIDER_SLOT"
printf 'WORKER_MODE=%q\n' "$MODE"
printf 'WORKER_COMMAND=%q\n' "$COMMAND"
