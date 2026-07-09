#!/usr/bin/env bash
# render-runtime-profile.sh — render worker command and prompt context for one runtime profile.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

BACKEND=""
MODE="interactive"
RUNTIME_PROFILE=""
API_PROVIDER=""
MODEL=""
PROVIDER_SLOT=""
SETTINGS=""
PROVIDER_REGISTRY=""
CODEX_PROFILE=""
PROMPT_FILE=""
PERMISSION_MODE=""
SANDBOX="danger-full-access"
APPROVAL="never"
CUSTOM_COMMAND=""
OUTPUT="shell"
SETTING_SOURCES="project,local"
NO_PROVIDER_ENV_ISOLATION=0
NO_MCP=0
BIN=""
SKIP_PERMISSIONS=0
NO_SKIP_PERMISSIONS=0
ADD_DIRS=()

usage() {
  cat >&2 <<'USAGE'
Usage:
  render-runtime-profile.sh --backend BACKEND [options]

Backends:
  claude-code     Claude Code with provider/settings profile
  claude-oauth    Claude Code subscription/OAuth; clears Anthropic provider env
  codex           Codex CLI
  opencode        OpenCode CLI
  codebuddy       WorkBuddy / CodeBuddy CLI (platform额度, 继承桌面端登录态)
  qoderwork-cn    QoderWork CN CLI (qoderclicn; 自动清除 SDK env 变量)
  custom          Use --command as-is

Options:
  --mode MODE              interactive | batch. Default: interactive
  --runtime-profile NAME   Runtime/settings/profile label for prompt metadata
  --api-provider NAME      API/provider label for prompt metadata
  --model NAME             Model name
  --provider-slot SLOT     Provider concurrency slot label
  --settings PATH          Claude Code settings path
  --provider-registry PATH Claude Code provider/model registry path
  --setting-sources LIST   Claude Code setting sources for provider workers.
                           Default: project,local (excludes user settings)
  --no-provider-env-isolation
                           Do not wrap Claude Code provider workers with the
                           settings-derived env isolation launcher
  --no-mcp                 Disable all MCP servers for the worker (Claude Code):
                           injects --strict-mcp-config --mcp-config '{"mcpServers":{}}'.
                           Skips the "new MCP servers found" approval prompt. Use for
                           workers that don't need MCP (e.g. pure text revision).
                           Note: codebuddy/qoderwork-cn backends default to --no-mcp already
                           (avoid ERR_FR_TOO_MANY_REDIRECTS from connector-proxy MCP under
                           concurrency; DEC-106).
  --with-mcp               Opt INTO MCP for codebuddy/qoderwork-cn (which default to --no-mcp).
                           Use only when the worker genuinely needs MCP tools.
  --codex-profile NAME     Codex profile name
  --prompt-file PATH       Prompt file for batch mode
  --permission-mode MODE   Claude permission mode. Defaults: auto interactive, acceptEdits batch
  --sandbox MODE           Codex sandbox. Default: danger-full-access
  --approval POLICY        Codex approval policy. Default: never
  --command CMD            Custom backend command
  --bin PATH               Executable path for codebuddy / qoderwork-cn backends.
                           Defaults to the standard app-bundle binary location.
  --dangerously-skip-permissions
                           Add the skip-permissions flag for the worker.
                           codebuddy: -y. qoderwork-cn: --dangerously-skip-permissions.
                           警告: 已改为默认行为（交互式也加）。该 flag 仅保留兼容。用 --no-skip-permissions 关闭。
  --no-skip-permissions    Explicitly turn OFF the skip-permissions flag for the worker.
                           罕见场景:人要坐终端跟 codebuddy/qoder 交互调试。
                           codebuddy: remove -y; qoderwork-cn: remove --dangerously-skip-permissions.
                           Defaults: ON (skip permissions).
  --add-dir DIR            Add extra directories for codebuddy to access (repeatable).
                           Maps to codebuddy's --add-dir flag. Only used for codebuddy backend.
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
    --provider-registry)
      PROVIDER_REGISTRY="$2"
      shift 2
      ;;
    --setting-sources)
      SETTING_SOURCES="$2"
      shift 2
      ;;
    --no-provider-env-isolation)
      NO_PROVIDER_ENV_ISOLATION=1
      shift
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
    --no-mcp)
      NO_MCP=1
      shift
      ;;
    --with-mcp)
      # codebuddy/qoderwork-cn 默认关 MCP（避 ERR_FR_TOO_MANY_REDIRECTS 启动重定向循环）；
      # 需要 MCP 的 worker 显式 opt-in。
      WITH_MCP=1
      shift
      ;;
    --bin)
      BIN="$2"
      shift 2
      ;;
    --dangerously-skip-permissions)
      SKIP_PERMISSIONS=1
      shift
      ;;
    --no-skip-permissions)
      NO_SKIP_PERMISSIONS=1
      shift
      ;;
    --add-dir)
      ADD_DIRS+=("$2")
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

if [ "$BACKEND" = "claude-code" ] && [ -n "$SETTINGS" ] && [ -n "$PROVIDER_REGISTRY" ]; then
  echo "ERROR: use either --settings or --provider-registry for Claude Code provider workers, not both" >&2
  exit 64
fi

if [ "$BACKEND" = "claude-code" ] && { [ -n "$SETTINGS" ] || [ -n "$PROVIDER_REGISTRY" ]; } && [ -z "$MODEL" ]; then
  echo "ERROR: Claude Code provider settings/registry require --model. Without it, user/global ANTHROPIC_MODEL can override the provider profile." >&2
  exit 64
fi

if [ "$BACKEND" = "claude-code" ] && { [ -n "$SETTINGS" ] || [ -n "$PROVIDER_REGISTRY" ]; } && [ -z "$SETTING_SOURCES" ]; then
  echo "ERROR: --setting-sources cannot be empty for Claude Code provider settings" >&2
  exit 64
fi

if [ "$BACKEND" = "claude-code" ] && [ -n "$PROVIDER_REGISTRY" ]; then
  [ -n "$API_PROVIDER" ] || { echo "ERROR: --api-provider is required with --provider-registry" >&2; exit 64; }
  [ "$NO_PROVIDER_ENV_ISOLATION" -eq 0 ] || { echo "ERROR: --provider-registry requires provider env isolation; do not combine with --no-provider-env-isolation" >&2; exit 64; }
  command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required for --provider-registry" >&2; exit 64; }
  [ -f "$PROVIDER_REGISTRY" ] || { echo "ERROR: provider registry not found: $PROVIDER_REGISTRY" >&2; exit 64; }
  jq -e --arg provider "$API_PROVIDER" '.providers[$provider] and (.providers[$provider] | type == "object")' "$PROVIDER_REGISTRY" >/dev/null
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

shell_wrap() {
  local command="$1"
  quote_words bash -lc "$command"
}

COMMAND=""
PROVIDER_ENV_ISOLATION="inherited-env"
COMMAND_MODEL="$MODEL"
MODEL_DISPLAY="$MODEL"
PROFILE_LABEL=""

if [ "$BACKEND" = "claude-code" ] && [ -n "$PROVIDER_REGISTRY" ]; then
  has_models=$(jq -r --arg provider "$API_PROVIDER" 'if (.providers[$provider].models | type) == "object" then "yes" else "no" end' "$PROVIDER_REGISTRY")
  if [ "$has_models" = "yes" ]; then
    if ! jq -e --arg provider "$API_PROVIDER" --arg model "$MODEL" '.providers[$provider].models[$model] != null' "$PROVIDER_REGISTRY" >/dev/null; then
      echo "ERROR: model alias not found in provider registry: provider=$API_PROVIDER model=$MODEL" >&2
      exit 64
    fi
    COMMAND_MODEL=$(jq -er --arg provider "$API_PROVIDER" --arg model "$MODEL" '
      .providers[$provider].models[$model] as $entry
      | if ($entry | type) == "object" then ($entry.model // $entry.id // empty) else $entry end
    ' "$PROVIDER_REGISTRY")
    MODEL_DISPLAY="$COMMAND_MODEL (alias: $MODEL)"
  fi
fi

if [ -n "$SETTINGS" ]; then
  PROFILE_LABEL="$SETTINGS"
elif [ -n "$PROVIDER_REGISTRY" ]; then
  PROFILE_LABEL="registry:$PROVIDER_REGISTRY"
elif [ -n "$CODEX_PROFILE" ]; then
  PROFILE_LABEL="codex:$CODEX_PROFILE"
fi

case "$BACKEND" in
  claude-code|claude-oauth)
    if [ -z "$PERMISSION_MODE" ]; then
      [ "$MODE" = "batch" ] && PERMISSION_MODE="acceptEdits" || PERMISSION_MODE="auto"
    fi
    claude_parts=(claude)
    [ -n "$SETTINGS" ] && claude_parts+=(--settings "$SETTINGS")
    [ -n "$COMMAND_MODEL" ] && claude_parts+=(--model "$COMMAND_MODEL")
    if [ "$MODE" = "batch" ]; then
      claude_parts+=(-p --verbose --output-format stream-json --permission-mode "$PERMISSION_MODE")
    else
      claude_parts+=(--permission-mode "$PERMISSION_MODE")
    fi

    if [ "$NO_MCP" -eq 1 ]; then
      claude_parts+=(--strict-mcp-config --mcp-config '{"mcpServers":{}}')
    fi

    if [ "$BACKEND" = "claude-code" ] && { [ -n "$SETTINGS" ] || [ -n "$PROVIDER_REGISTRY" ]; }; then
      if [ "$NO_PROVIDER_ENV_ISOLATION" -eq 0 ]; then
        # --bare: minimal mode — skip keychain reads / OAuth / plugin sync / CLAUDE.md auto-discovery.
        # Makes Anthropic auth strictly ANTHROPIC_API_KEY (set by wrapper from provider registry/settings),
        # fixing the bug where claude read a stale keychain sk-ant + misrouted to Fable 5 / OAuth
        # instead of the selected 3P provider (deepseek/glm). Also suppresses the MCP trust dialog
        # (plugin sync skipped). Task#188 worker-spawn env-routing bug, 2026-07-06.
        claude_parts+=(--bare)
        wrapper="$SCRIPT_DIR/claude-provider-env.sh"
        [ -f "$wrapper" ] || { echo "ERROR: missing Claude provider env wrapper: $wrapper" >&2; exit 64; }
        if [ -n "$PROVIDER_REGISTRY" ]; then
          parts=(bash "$wrapper" --provider-registry "$PROVIDER_REGISTRY" --api-provider "$API_PROVIDER" --model "$MODEL" --setting-sources "$SETTING_SOURCES" -- "${claude_parts[@]}")
          PROVIDER_ENV_ISOLATION="registry-env-wrapper(provider=$API_PROVIDER setting-sources=$SETTING_SOURCES)"
        else
          parts=(bash "$wrapper" --settings "$SETTINGS" --model "$MODEL" --setting-sources "$SETTING_SOURCES" -- "${claude_parts[@]}")
          PROVIDER_ENV_ISOLATION="settings-env-wrapper(setting-sources=$SETTING_SOURCES)"
        fi
      else
        parts=("${claude_parts[@]}")
        PROVIDER_ENV_ISOLATION="disabled(inherited-env)"
      fi
    else
      parts=("${claude_parts[@]}")
      [ "$BACKEND" = "claude-oauth" ] && PROVIDER_ENV_ISOLATION="oauth-clear-anthropic-env"
    fi

    COMMAND=$(quote_words "${parts[@]}")
    [ "$MODE" = "batch" ] && COMMAND=$(append_redirection "$COMMAND" "$PROMPT_FILE")
    [ "$MODE" = "batch" ] && COMMAND=$(shell_wrap "$COMMAND")
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
      COMMAND=$(shell_wrap "$COMMAND")
    else
      COMMAND=$(quote_words "${parts[@]}")
    fi
    ;;
  opencode)
    if [ "$MODE" = "batch" ]; then
      parts=(opencode run --format json)
      [ -n "$MODEL" ] && parts+=(--model "$MODEL")
      COMMAND="$(quote_words "${parts[@]}") \"\$(cat $(printf '%q' "$PROMPT_FILE"))\""
      COMMAND=$(shell_wrap "$COMMAND")
    else
      parts=(opencode)
      [ -n "$MODEL" ] && parts+=(--model "$MODEL")
      COMMAND=$(quote_words "${parts[@]}")
    fi
    ;;
  codebuddy)
    # WorkBuddy / CodeBuddy CLI。参数体系与 Claude Code 高度兼容(ref 08)。
    # MCP off 用 inline 空 config(避免 /tmp 依赖)。
    # -y 默认加：spawn-worker 派 tmux session 本质 headless（无人在终端应答 prompt）。
    # 仅 --no-skip-permissions opt-out（罕见场景：人坐终端跟 codebuddy 交互调试）。
    if [ -z "$PERMISSION_MODE" ]; then
      # F1 (DEC-040): batch 默认 bypassPermissions 替代 acceptEdits。CLI 文档与实测都显示
      # batch + acceptEdits 与 -y 冲突，headless 下每个 tool 调用都被 deny。
      # 实测命令 `codebuddy -p -y "<prompt>"` 或 `--permission-mode bypassPermissions` 工作。
      [ "$MODE" = "batch" ] && PERMISSION_MODE="bypassPermissions" || PERMISSION_MODE="acceptEdits"
    fi
    [ -n "$BIN" ] || BIN="/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy"
    cb_parts=("$BIN")
    [ -n "$COMMAND_MODEL" ] && cb_parts+=(--model "$COMMAND_MODEL")
    cb_parts+=(--permission-mode "$PERMISSION_MODE")
    # codebuddy 默认关 MCP（避 ERR_FR_TOO_MANY_REDIRECTS 启动重定向循环）：
    # WorkBuddy 桌面端的 connector-proxy MCP 在多 worker 并发时触发重定向，导致 worker
    # 启动即报 ERR_FR_TOO_MANY_REDIRECTS 停 input。绝大多数 worker 任务（纯脚本/文件）不需要 MCP，
    # 默认关；需要 MCP 的 worker 显式 --with-mcp opt-in。
    if [ "$WITH_MCP" != "1" ]; then
      cb_parts+=(--strict-mcp-config --mcp-config '{"mcpServers":{}}')
    fi
    for add_dir in "${ADD_DIRS[@]}"; do
      cb_parts+=(--add-dir "$add_dir")
    done
    # 默认加 -y：交互式和 batch 均默认加；仅 --no-skip-permissions opt-out。
    if [ "$NO_SKIP_PERMISSIONS" -ne 1 ]; then
      cb_parts+=(-y)
    fi
    if [ "$MODE" = "batch" ]; then
      cb_parts+=(--output-format stream-json -p)
      COMMAND="$(quote_words "${cb_parts[@]}") \"\$(cat $(printf '%q' "$PROMPT_FILE"))\""
      COMMAND=$(shell_wrap "$COMMAND")
    else
      COMMAND=$(quote_words "${cb_parts[@]}")
    fi
    PROVIDER_ENV_ISOLATION="codebuddy-inherited-env"
    [ -z "$PROFILE_LABEL" ] && PROFILE_LABEL="${RUNTIME_PROFILE:-codebuddy}"
    ;;
  qoderwork-cn)
    # QoderWork CN CLI(qoderclicn)。必须先清 SDK env 变量,否则走 SDK 模式报错(ref 07 §5.1)。
    # 二进制路径含空格,靠 quote_words 的 %q 保护。
    if [ -z "$PERMISSION_MODE" ]; then
      PERMISSION_MODE="auto"
    fi
    [ -n "$BIN" ] || BIN="/Applications/QoderWork CN.app/Contents/Resources/bin/qoderclicn"
    qr_parts=(env -u QODER_AGENT_SDK_ENTRYPOINT -u QODER_AGENT_SDK_VERSION -u QODER_WORK_INTEGRATION_MODE -u QODERWORK_SOURCE_CHAT_ID -u QODERWORK_AWARENESS_SINK -u QODERWORK_AWARENESS_SINK_MEMORY "$BIN")
    [ -n "$COMMAND_MODEL" ] && qr_parts+=(-m "$COMMAND_MODEL")
    qr_parts+=(--permission-mode "$PERMISSION_MODE")
    [ "$NO_MCP" -eq 1 ] && qr_parts+=(--strict-mcp-config --mcp-config '{"mcpServers":{}}')
    # 默认加 --dangerously-skip-permissions（spawn-worker tmux worker 本质 headless）。
    # 仅 --no-skip-permissions opt-out。
    if [ "$NO_SKIP_PERMISSIONS" -ne 1 ]; then
      qr_parts+=(--dangerously-skip-permissions)
    fi
    if [ "$MODE" = "batch" ]; then
      qr_parts+=(-p)
      COMMAND="$(quote_words "${qr_parts[@]}") \"\$(cat $(printf '%q' "$PROMPT_FILE"))\""
      COMMAND=$(shell_wrap "$COMMAND")
    else
      # 交互模式(detached tmux)需初始 prompt,否则 qoder 纯 detached REPL 检测
      # "无初始输入"立即 exit 42(2026-07-05 实测根因)。-i(prompt-interactive)给
      # 占位 prompt 让 qoder 启动 REPL,PM 后续 tmux send-keys 投递真任务。
      qr_parts+=(-i "ready")
      COMMAND=$(quote_words "${qr_parts[@]}")
    fi
    PROVIDER_ENV_ISOLATION="qoder-sdk-env-cleared"
    [ -z "$PROFILE_LABEL" ] && PROFILE_LABEL="${RUNTIME_PROFILE:-qoderwork-cn}"
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
- Settings/Profile Path: $PROFILE_LABEL
- API Provider: $API_PROVIDER
- Model: $MODEL_DISPLAY
- Provider Slot: $PROVIDER_SLOT
- Env Isolation: $PROVIDER_ENV_ISOLATION
- Mode: $MODE
- Command: $COMMAND
EOF
  exit 0
fi

printf 'WORKER_BACKEND=%q\n' "$BACKEND"
printf 'RUNTIME_PROFILE=%q\n' "$RUNTIME_PROFILE"
printf 'SETTINGS_PROFILE_PATH=%q\n' "$PROFILE_LABEL"
printf 'API_PROVIDER=%q\n' "$API_PROVIDER"
printf 'MODEL=%q\n' "$COMMAND_MODEL"
printf 'PROVIDER_SLOT=%q\n' "$PROVIDER_SLOT"
printf 'PROVIDER_ENV_ISOLATION=%q\n' "$PROVIDER_ENV_ISOLATION"
printf 'WORKER_MODE=%q\n' "$MODE"
printf 'WORKER_COMMAND=%q\n' "$COMMAND"
