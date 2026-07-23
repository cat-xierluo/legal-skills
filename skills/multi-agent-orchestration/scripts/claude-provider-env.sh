#!/usr/bin/env bash
# claude-provider-env.sh - launch Claude Code with a settings-derived provider env.
#
# This wrapper is intentionally small and shell-native. It does not own provider
# storage; it only turns one Claude Code settings JSON into the effective
# subprocess env for a single worker. The goal is to keep user/global Claude
# settings from silently overriding a task-selected provider/model.

set -euo pipefail

# v2.0：PATH 注入 helper（spawn-worker.sh 同源 helper），确保 claude CLI 可解析。
SCRIPT_DIR_CPE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=ensure-claude-path.sh
source "$SCRIPT_DIR_CPE/ensure-claude-path.sh"
ensure_claude_in_path

SETTINGS=""
PROVIDER_REGISTRY=""
API_PROVIDER=""
MODEL=""
SETTING_SOURCES="project,local"
PRINT_ENV_SUMMARY=0
# v2.0：--no-mcp 显式禁用 MCP server 加载，规避项目 .mcp.json 触发的
# "N new MCP servers found" 选择 dialog（references/09 T6 实战坑）。
# wrapper 把 --strict-mcp-config --mcp-config '{"mcpServers":{}}' 注入给 claude。
NO_MCP=0

usage() {
  cat >&2 <<'USAGE'
Usage:
  claude-provider-env.sh --settings PATH --model MODEL [options] -- claude [args...]
  claude-provider-env.sh --provider-registry PATH --api-provider ID --model MODEL_ALIAS [options] -- claude [args...]

Options:
  --setting-sources LIST   Sources passed to claude when it does not already
                           provide --setting-sources. Default: project,local
  --print-env-summary      Print a sanitized env summary to stderr before exec
  --no-mcp                 (v2.0) Disable MCP server loading by injecting
                           --strict-mcp-config --mcp-config '{"mcpServers":{}}'
                           into the wrapped claude command. Use when project
                           has .mcp.json that triggers "N new MCP servers found"
                           selection dialog (references/09 T6). Skipped silently
                           if claude already passes --strict-mcp-config.

The wrapper:
  - clears inherited Anthropic/Claude provider-routing env vars;
  - exports env entries from the given settings JSON, or resolves provider/model
    from a registry JSON;
  - sets ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN together when one is absent;
  - pins ANTHROPIC_MODEL to --model;
  - sets CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=1; and
  - injects --setting-sources project,local for claude commands by default.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --settings)
      SETTINGS="$2"
      shift 2
      ;;
    --provider-registry)
      PROVIDER_REGISTRY="$2"
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
    --setting-sources)
      SETTING_SOURCES="$2"
      shift 2
      ;;
    --print-env-summary)
      PRINT_ENV_SUMMARY=1
      shift
      ;;
    --no-mcp)  # v2.0：禁用 MCP server 加载（references/09 T6 坑）
      NO_MCP=1
      shift
      ;;
    --)
      shift
      break
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

[ -n "$MODEL" ] || { echo "ERROR: --model is required" >&2; exit 64; }
[ -n "$SETTING_SOURCES" ] || { echo "ERROR: --setting-sources cannot be empty" >&2; exit 64; }
[ "$#" -gt 0 ] || { echo "ERROR: command after -- is required" >&2; exit 64; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 64; }

if [ -n "$SETTINGS" ] && [ -n "$PROVIDER_REGISTRY" ]; then
  echo "ERROR: use either --settings or --provider-registry, not both" >&2
  exit 64
fi
if [ -z "$SETTINGS" ] && [ -z "$PROVIDER_REGISTRY" ]; then
  usage
  exit 64
fi
if [ -n "$SETTINGS" ]; then
  [ -f "$SETTINGS" ] || { echo "ERROR: settings file not found: $SETTINGS" >&2; exit 64; }
  jq -e '.env and (.env | type == "object")' "$SETTINGS" >/dev/null
fi
if [ -n "$PROVIDER_REGISTRY" ]; then
  [ -f "$PROVIDER_REGISTRY" ] || { echo "ERROR: provider registry not found: $PROVIDER_REGISTRY" >&2; exit 64; }
  [ -n "$API_PROVIDER" ] || { echo "ERROR: --api-provider is required with --provider-registry" >&2; exit 64; }
  jq -e --arg provider "$API_PROVIDER" '.providers[$provider] and (.providers[$provider] | type == "object")' "$PROVIDER_REGISTRY" >/dev/null
fi

# Remove provider-routing values inherited from the parent shell before applying
# the selected profile. This is narrower than env -i: PATH, HOME, TERM, locale,
# SSH agent, proxy, and tool-specific env remain available to the worker.
PROVIDER_ENV_KEYS=(
  ANTHROPIC_API_KEY
  ANTHROPIC_AUTH_TOKEN
  ANTHROPIC_BASE_URL
  ANTHROPIC_MODEL
  ANTHROPIC_MODEL_NAME
  ANTHROPIC_REASONING_MODEL
  ANTHROPIC_SMALL_FAST_MODEL
  ANTHROPIC_SMALL_FAST_MODEL_NAME
  ANTHROPIC_DEFAULT_FABLE_MODEL
  ANTHROPIC_DEFAULT_FABLE_MODEL_NAME
  ANTHROPIC_DEFAULT_HAIKU_MODEL
  ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME
  ANTHROPIC_DEFAULT_OPUS_MODEL
  ANTHROPIC_DEFAULT_OPUS_MODEL_NAME
  ANTHROPIC_DEFAULT_SONNET_MODEL
  ANTHROPIC_DEFAULT_SONNET_MODEL_NAME
  CLAUDE_CODE_OAUTH_TOKEN
  CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR
  CLAUDE_CODE_USE_BEDROCK
  CLAUDE_CODE_USE_VERTEX
  CLAUDE_CODE_USE_FOUNDRY
)

for key in "${PROVIDER_ENV_KEYS[@]}"; do
  unset "$key"
done

AUTH_TYPE="both"
MODEL_ALIAS="$MODEL"
RESOLVED_MODEL="$MODEL"

if [ -n "$SETTINGS" ]; then
  while IFS='=' read -r key value; do
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    export "$key=$value"
  done < <(jq -r '.env | to_entries[] | "\(.key)=\(.value)"' "$SETTINGS")
fi

if [ -n "$PROVIDER_REGISTRY" ]; then
  provider_jq='.providers[$provider]'
  ANTHROPIC_BASE_URL=$(jq -er --arg provider "$API_PROVIDER" "$provider_jq.base_url // $provider_jq.baseUrl // empty" "$PROVIDER_REGISTRY")
  AUTH_TYPE=$(jq -r --arg provider "$API_PROVIDER" "$provider_jq.auth_type // $provider_jq.authType // \"both\"" "$PROVIDER_REGISTRY")

  token_literal=$(jq -r --arg provider "$API_PROVIDER" "$provider_jq.auth_token // $provider_jq.api_key // $provider_jq.apiKey // empty" "$PROVIDER_REGISTRY")
  token_env=$(jq -r --arg provider "$API_PROVIDER" "$provider_jq.auth_token_env // $provider_jq.api_key_env // $provider_jq.authTokenEnv // $provider_jq.apiKeyEnv // empty" "$PROVIDER_REGISTRY")
  token="$token_literal"
  if [ -z "$token" ] && [ -n "$token_env" ]; then
    token="${!token_env:-}"
  fi
  if [ -z "$token" ]; then
    echo "ERROR: provider registry entry '$API_PROVIDER' must provide auth_token/api_key or auth_token_env/api_key_env with a non-empty value" >&2
    exit 64
  fi

  has_models=$(jq -r --arg provider "$API_PROVIDER" 'if (.providers[$provider].models | type) == "object" then "yes" else "no" end' "$PROVIDER_REGISTRY")
  if [ "$has_models" = "yes" ]; then
    if ! jq -e --arg provider "$API_PROVIDER" --arg model "$MODEL_ALIAS" '.providers[$provider].models[$model] != null' "$PROVIDER_REGISTRY" >/dev/null; then
      echo "ERROR: model alias not found in provider registry: provider=$API_PROVIDER model=$MODEL_ALIAS" >&2
      exit 64
    fi
    RESOLVED_MODEL=$(jq -er --arg provider "$API_PROVIDER" --arg model "$MODEL_ALIAS" '
      .providers[$provider].models[$model] as $entry
      | if ($entry | type) == "object" then ($entry.model // $entry.id // empty) else $entry end
    ' "$PROVIDER_REGISTRY")
    ANTHROPIC_MODEL_NAME=$(jq -r --arg provider "$API_PROVIDER" --arg model "$MODEL_ALIAS" --arg resolved "$RESOLVED_MODEL" '
      .providers[$provider].models[$model] as $entry
      | if ($entry | type) == "object" then ($entry.model_name // $entry.modelName // $entry.display_name // $entry.displayName // $resolved) else $resolved end
    ' "$PROVIDER_REGISTRY")
    ANTHROPIC_REASONING_MODEL=$(jq -r --arg provider "$API_PROVIDER" --arg model "$MODEL_ALIAS" --arg resolved "$RESOLVED_MODEL" '
      .providers[$provider].models[$model] as $entry
      | if ($entry | type) == "object" then ($entry.reasoning_model // $entry.reasoningModel // $resolved) else $resolved end
    ' "$PROVIDER_REGISTRY")
  fi

  ANTHROPIC_DEFAULT_FABLE_MODEL=$(jq -r --arg provider "$API_PROVIDER" --arg model "$MODEL_ALIAS" --arg resolved "$RESOLVED_MODEL" '
    .providers[$provider] as $p
    | ($p.models[$model] // {}) as $entry
    | if ($entry | type) == "object" then ($entry.aliases.fable // $p.model_aliases.fable // $p.modelAliases.fable // $resolved) else ($p.model_aliases.fable // $p.modelAliases.fable // $resolved) end
  ' "$PROVIDER_REGISTRY")
  ANTHROPIC_DEFAULT_SONNET_MODEL=$(jq -r --arg provider "$API_PROVIDER" --arg model "$MODEL_ALIAS" --arg resolved "$RESOLVED_MODEL" '
    .providers[$provider] as $p
    | ($p.models[$model] // {}) as $entry
    | if ($entry | type) == "object" then ($entry.aliases.sonnet // $p.model_aliases.sonnet // $p.modelAliases.sonnet // $resolved) else ($p.model_aliases.sonnet // $p.modelAliases.sonnet // $resolved) end
  ' "$PROVIDER_REGISTRY")
  ANTHROPIC_DEFAULT_OPUS_MODEL=$(jq -r --arg provider "$API_PROVIDER" --arg model "$MODEL_ALIAS" --arg resolved "$RESOLVED_MODEL" '
    .providers[$provider] as $p
    | ($p.models[$model] // {}) as $entry
    | if ($entry | type) == "object" then ($entry.aliases.opus // $p.model_aliases.opus // $p.modelAliases.opus // $resolved) else ($p.model_aliases.opus // $p.modelAliases.opus // $resolved) end
  ' "$PROVIDER_REGISTRY")
  ANTHROPIC_DEFAULT_HAIKU_MODEL=$(jq -r --arg provider "$API_PROVIDER" --arg model "$MODEL_ALIAS" --arg resolved "$RESOLVED_MODEL" '
    .providers[$provider] as $p
    | ($p.models[$model] // {}) as $entry
    | if ($entry | type) == "object" then ($entry.aliases.haiku // $p.model_aliases.haiku // $p.modelAliases.haiku // $resolved) else ($p.model_aliases.haiku // $p.modelAliases.haiku // $resolved) end
  ' "$PROVIDER_REGISTRY")

  export ANTHROPIC_BASE_URL
  case "$AUTH_TYPE" in
    both|auth_token)
      export ANTHROPIC_AUTH_TOKEN="$token"
      export ANTHROPIC_API_KEY="$token"
      ;;
    api_key)
      export ANTHROPIC_API_KEY="$token"
      export ANTHROPIC_AUTH_TOKEN=""
      ;;
    auth_token_clear_api_key)
      export ANTHROPIC_AUTH_TOKEN="$token"
      export ANTHROPIC_API_KEY=""
      ;;
    *)
      echo "ERROR: unsupported auth_type for provider '$API_PROVIDER': $AUTH_TYPE" >&2
      exit 64
      ;;
  esac
fi

if [ -z "${ANTHROPIC_BASE_URL:-}" ]; then
  echo "ERROR: provider env must include ANTHROPIC_BASE_URL for a provider worker" >&2
  exit 64
fi

if [ -z "${ANTHROPIC_AUTH_TOKEN:-}" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ERROR: settings env must include ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY" >&2
  exit 64
fi

if [ "$AUTH_TYPE" = "both" ] || [ "$AUTH_TYPE" = "auth_token" ]; then
  if [ -z "${ANTHROPIC_AUTH_TOKEN:-}" ]; then
    export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_API_KEY}"
  fi
  if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    export ANTHROPIC_API_KEY="${ANTHROPIC_AUTH_TOKEN}"
  fi
fi

export ANTHROPIC_MODEL="$RESOLVED_MODEL"
: "${ANTHROPIC_MODEL_NAME:=$RESOLVED_MODEL}"
: "${ANTHROPIC_REASONING_MODEL:=$RESOLVED_MODEL}"
: "${ANTHROPIC_DEFAULT_FABLE_MODEL:=$RESOLVED_MODEL}"
: "${ANTHROPIC_DEFAULT_FABLE_MODEL_NAME:=$ANTHROPIC_DEFAULT_FABLE_MODEL}"
: "${ANTHROPIC_DEFAULT_SONNET_MODEL:=$RESOLVED_MODEL}"
: "${ANTHROPIC_DEFAULT_SONNET_MODEL_NAME:=$ANTHROPIC_DEFAULT_SONNET_MODEL}"
: "${ANTHROPIC_DEFAULT_OPUS_MODEL:=$RESOLVED_MODEL}"
: "${ANTHROPIC_DEFAULT_OPUS_MODEL_NAME:=$ANTHROPIC_DEFAULT_OPUS_MODEL}"
: "${ANTHROPIC_DEFAULT_HAIKU_MODEL:=$RESOLVED_MODEL}"
: "${ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME:=$ANTHROPIC_DEFAULT_HAIKU_MODEL}"
export ANTHROPIC_MODEL_NAME
export ANTHROPIC_REASONING_MODEL
export ANTHROPIC_DEFAULT_FABLE_MODEL
export ANTHROPIC_DEFAULT_FABLE_MODEL_NAME
export ANTHROPIC_DEFAULT_SONNET_MODEL
export ANTHROPIC_DEFAULT_SONNET_MODEL_NAME
export ANTHROPIC_DEFAULT_OPUS_MODEL
export ANTHROPIC_DEFAULT_OPUS_MODEL_NAME
export ANTHROPIC_DEFAULT_HAIKU_MODEL
export ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME

export CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=1
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="${CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC:-1}"
export CLAUDE_CODE_OAUTH_TOKEN=""
export CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR=""

cmd=("$@")
cmd0=$(basename "${cmd[0]}")
if [ "$cmd0" = "claude" ]; then
  has_setting_sources=0
  has_strict_mcp=0
  for arg in "${cmd[@]}"; do
    if [ "$arg" = "--setting-sources" ]; then
      has_setting_sources=1
    fi
    if [ "$arg" = "--strict-mcp-config" ]; then
      has_strict_mcp=1
    fi
  done
  if [ "$has_setting_sources" -eq 0 ]; then
    cmd=("${cmd[0]}" --setting-sources "$SETTING_SOURCES" "${cmd[@]:1}")
  fi
  # v2.0：--no-mcp 注入空 MCP 配置，规避项目 .mcp.json 触发的 dialog
  # （references/09-parallel-lessons.md T6）。用户已显式传 --strict-mcp-config
  # 时不再叠加，尊重用户选择。
  if [ "$NO_MCP" -eq 1 ] && [ "$has_strict_mcp" -eq 0 ]; then
    cmd=("${cmd[0]}" --strict-mcp-config --mcp-config '{"mcpServers":{}}' "${cmd[@]:1}")
    echo "CLAUDE_PROVIDER_ENV_NO_MCP: injected --strict-mcp-config --mcp-config empty" >&2
  fi
fi

if [ "$PRINT_ENV_SUMMARY" -eq 1 ]; then
  base_label=$(printf '%s' "$ANTHROPIC_BASE_URL" | sed -E 's#^(https?://[^/]+).*#\1#')
  auth_label="present"
  api_key_label="present"
  if [ -n "$PROVIDER_REGISTRY" ]; then
    printf 'CLAUDE_PROVIDER_ENV_SUMMARY: registry=%s provider=%s model_alias=%s resolved_model=%s base=%s auth_token=%s api_key=%s setting_sources=%s host_managed=1\n' \
      "$PROVIDER_REGISTRY" "$API_PROVIDER" "$MODEL_ALIAS" "$RESOLVED_MODEL" "$base_label" "$auth_label" "$api_key_label" "$SETTING_SOURCES" >&2
  else
    printf 'CLAUDE_PROVIDER_ENV_SUMMARY: settings=%s model=%s base=%s auth_token=%s api_key=%s setting_sources=%s host_managed=1\n' \
      "$SETTINGS" "$RESOLVED_MODEL" "$base_label" "$auth_label" "$api_key_label" "$SETTING_SOURCES" >&2
  fi
fi

exec "${cmd[@]}"
