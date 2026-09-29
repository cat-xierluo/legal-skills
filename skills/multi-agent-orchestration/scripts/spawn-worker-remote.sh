#!/usr/bin/env bash
# spawn-worker-remote.sh — PM 侧远程节点 Worker 派发入口（M0：SSH 桥）。
#
# 形态（references/25-remote-node-dispatch.md，DEC-2026-09-29-REMOTE-NODE-DISPATCH）：
#   PM 在本机完成 harness 验证与容量/基线预检后，把一次性 receipt 传到远程节点，
#   经 ssh 调用「远程节点本机的」spawn-worker.sh。全套门禁（receipt 校验 → policy
#   交集 → quota preflight → mem budget → provider lease → worktree → isolation）
#   在远程节点本机原样成立；worker 读节点自己的 env/key 配置（unset 继承的
#   ANTHROPIC_*/CLAUDE_CODE_* 后由节点侧 claude-provider-env.sh 注入）。
#
# 子命令：
#   spawn    派发（默认：首个参数为 --flag 时免写）
#   status   巡检：ssh 读远程 STATUS.json + 本机 gh 查 PR
#   cleanup  收口：校验 PR/STATUS 终态后转发节点侧 pm-cleanup-worker.sh，删软账
#
# 退出码契约（与 remote-node-probe.py 对齐）：
#   0 ok；3 precondition_failed（基线/版本/配置，修复后重试）；4 capacity_denied
#   （节点容量，PARKED_FOR_REMOTE_CAPACITY 排队，不回落本机）；65 unreachable
#   （可回落本机：回落=全新本机 spawn，天然重走全套门禁）；75 PM 侧软账自限
#   （等待或改派）；64 usage/fail-closed 拒绝。
#
# M0 边界：单节点串行派发；不自动回落（只打印建议）；不透传未列明的 spawn flag。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
# shellcheck source=harness-backend-policy.sh
source "$SCRIPT_DIR/harness-backend-policy.sh"
# shellcheck source=remote-dispatch-receipt.sh
source "$SCRIPT_DIR/remote-dispatch-receipt.sh"

PERSONAL_CONFIG_FILE="${MULTI_AGENT_ORCHESTRATION_PERSONAL_CONFIG:-$SCRIPT_DIR/../config/orchestration-personal.json}"
LEDGER_SCHEMA="multi-agent-orchestration.remote-dispatch.v1"
# REMOTE_DISPATCH_SSH_COMMAND：仅测试注入用（mock ssh/rsync）；正式链路固定走 ssh/rsync。
REMOTE_DISPATCH_SSH_BIN="${REMOTE_DISPATCH_SSH_COMMAND:-ssh}"

# 远程派发前在节点 shell 里 unset 的 provider 路由变量：与 claude-provider-env.sh
# 的 PROVIDER_ENV_KEYS 保持同一清单（现场提取，防两处漂移；测试覆盖清单非空）。
REMOTE_PROVIDER_ENV_KEYS=()
while IFS= read -r _env_key; do
  [ -n "$_env_key" ] && REMOTE_PROVIDER_ENV_KEYS+=("$_env_key")
done < <(awk '/^PROVIDER_ENV_KEYS=\(/{f=1;next} f&&/^\)/{exit} f{gsub(/[ \t]/,""); if ($0!="") print}' \
  "$SCRIPT_DIR/claude-provider-env.sh")

remote_usage() {
  cat >&2 <<USAGE
Usage:
  spawn-worker-remote.sh spawn --node NAME --branch NAME --session NAME \\
      --worker-backend NAME [--command CMD] [--verify-cmd CMD ...] \\
      [--api-provider NAME] [--model NAME] [--runtime-profile NAME] \\
      [--require-verification] [--local-project PATH] [--receipt-ttl-seconds N] \\
      [--provision]
  spawn-worker-remote.sh provision --node NAME [--local-project PATH] [--skip-clone]
  （spawn 另支持 --remote-env KEY=VALUE 可重复：在节点侧 spawn-worker.sh 之前 export，
    用于按节点调优，如 SPAWN_WORKER_MEM_BUDGET_BYTES=1073741824）
  spawn-worker-remote.sh status --node NAME --session NAME
  spawn-worker-remote.sh cleanup --node NAME --session NAME [--force-with-reason R]

Node inventory lives in the gitignored personal config remote_nodes section
(see config/orchestration-personal.example.json). Exit codes: 0 ok; 3 node
precondition (fix then retry); 4 node capacity (PARKED_FOR_REMOTE_CAPACITY);
65 node unreachable (local fallback allowed); 75 PM-side soft ledger cap; 64 fail-closed.
USAGE
}

# ---- 节点配置与 PM 软账 ------------------------------------------------------

remote_node_config_load() {
  local node="$1"
  [ -f "$PERSONAL_CONFIG_FILE" ] || {
    echo "ERROR: personal config not found: $PERSONAL_CONFIG_FILE" >&2
    return 64
  }
  local cfg
  cfg=$(jq -er --arg node "$node" '.remote_nodes[$node] // empty' "$PERSONAL_CONFIG_FILE") || {
    printf 'ERROR: node %s not found in remote_nodes of %s\n' "$node" "$PERSONAL_CONFIG_FILE" >&2
    return 64
  }
  REMOTE_NODE_NAME="$node"
  REMOTE_NODE_SSH_ALIAS=$(jq -r '.ssh_alias // empty' <<<"$cfg")
  REMOTE_NODE_ROOT=$(jq -r '.remote_root // empty' <<<"$cfg")
  REMOTE_NODE_SKILL_ROOT=$(jq -r '.skill_root // empty' <<<"$cfg")
  REMOTE_NODE_MAX_WORKERS=$(jq -r '.max_workers // 2' <<<"$cfg")
  REMOTE_NODE_ALLOWED_BACKENDS=$(jq -r '(.allowed_backends // []) | join(" ")' <<<"$cfg")
  REMOTE_NODE_ENABLED=$(jq -r '.enabled // false' <<<"$cfg")
  local missing=()
  [ -n "$REMOTE_NODE_SSH_ALIAS" ] || missing+=(ssh_alias)
  [ -n "$REMOTE_NODE_ROOT" ] || missing+=(remote_root)
  [ -n "$REMOTE_NODE_SKILL_ROOT" ] || missing+=(skill_root)
  if [ "${#missing[@]}" -gt 0 ]; then
    printf 'ERROR: remote_nodes.%s missing required fields: %s\n' "$node" "${missing[*]}" >&2
    return 64
  fi
  [ "$REMOTE_NODE_ENABLED" = "true" ] || {
    printf 'ERROR: remote_nodes.%s.enabled is not true (fail-closed)\n' "$node" >&2
    return 3
  }
}

remote_ledger_dir() {
  local local_project="$1" git_common_dir
  git_common_dir=$(git -C "$local_project" rev-parse --git-common-dir 2>/dev/null) || {
    echo "ERROR: --local-project is not a git repository: $local_project" >&2
    return 64
  }
  case "$git_common_dir" in /*) ;; *) git_common_dir="$local_project/$git_common_dir" ;; esac
  git_common_dir=$(cd "$git_common_dir" && pwd -P)
  printf '%s\n' "$git_common_dir/orchestration/remote-dispatches"
}

remote_ledger_active_count() {
  local ledger_dir="$1" node="$2"
  [ -d "$ledger_dir/$node" ] || { echo 0; return; }
  ls "$ledger_dir/$node" 2>/dev/null | grep -c '\.json$' || true
}

# ---- spawn 子命令 ------------------------------------------------------------

cmd_spawn() {
  local node="" branch="" session="" worker_backend="" command="" local_project=""
  local receipt_ttl="" require_verification=0 provision=0
  local api_provider="" model="" runtime_profile=""
  local verify_commands=() remote_envs=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --node) node="$2"; shift 2 ;;
      --branch) branch="$2"; shift 2 ;;
      --session) session="$2"; shift 2 ;;
      --worker-backend) worker_backend="$2"; shift 2 ;;
      --command) command="$2"; shift 2 ;;
      --verify-cmd) verify_commands+=("$2"); shift 2 ;;
      --api-provider) api_provider="$2"; shift 2 ;;
      --model) model="$2"; shift 2 ;;
      --runtime-profile) runtime_profile="$2"; shift 2 ;;
      --require-verification) require_verification=1; shift ;;
      --local-project) local_project="$2"; shift 2 ;;
      --receipt-ttl-seconds) receipt_ttl="$2"; shift 2 ;;
      --provision) provision=1; shift ;;
      --remote-env)
        [[ "$2" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || {
          printf 'ERROR: --remote-env expects KEY=VALUE (got: %s)\n' "$2" >&2; return 64; }
        remote_envs+=("$2"); shift 2 ;;
      *) printf 'ERROR: spawn: unknown argument: %s\n' "$1" >&2; remote_usage; return 64 ;;
    esac
  done
  local missing=()
  [ -n "$node" ] || missing+=(--node)
  [ -n "$branch" ] || missing+=(--branch)
  [ -n "$session" ] || missing+=(--session)
  [ -n "$worker_backend" ] || missing+=(--worker-backend)
  if [ "${#missing[@]}" -gt 0 ]; then
    printf 'ERROR: spawn: missing required arguments: %s\n' "${missing[*]}" >&2
    remote_usage
    return 64
  fi
  [ "${#REMOTE_PROVIDER_ENV_KEYS[@]}" -gt 0 ] || {
    echo "ERROR: PROVIDER_ENV_KEYS extraction failed (claude-provider-env.sh changed?)" >&2
    return 64
  }

  remote_node_config_load "$node" || return $?

  # 1) PM 本机 harness 验证 + 本地策略交集预检（fail fast，权威判定仍在节点侧原样重跑）
  DETECTED_PM_HARNESS=""
  detect_pm_harness "" || return 64
  local pm_harness="$DETECTED_PM_HARNESS" pm_chain="$PM_HARNESS_CHAIN_JSON" pm_source="$PM_HARNESS_SOURCE"
  enforce_harness_backend_policy_chain "$pm_harness" "$pm_chain" "$worker_backend" || return 64
  if [ -n "$REMOTE_NODE_ALLOWED_BACKENDS" ]; then
    local allowed item found=0
    allowed=$(remote_node_allowed_backends "$node")
    for item in $allowed; do
      [ "$item" = "$WORKER_BACKEND_CANONICAL" ] && { found=1; break; }
    done
    [ "$found" -eq 1 ] || {
      printf 'ERROR: remote_nodes.%s.allowed_backends does not include %s (fail-closed)\n' \
        "$node" "$WORKER_BACKEND_CANONICAL" >&2
      return 64
    }
  fi

  # 2) 本地仓库事实（基线 SHA / skill 版本；缺省取 skill 所在仓库）
  if [ -z "$local_project" ]; then
    local_project=$(git -C "$SKILL_DIR" rev-parse --show-toplevel 2>/dev/null) || {
      echo "ERROR: cannot derive local project from $SKILL_DIR; pass --local-project" >&2
      return 64
    }
  fi
  git -C "$local_project" fetch origin >/dev/null 2>&1 || {
    echo "ERROR: git fetch origin failed in $local_project (基线门需要最新 origin/main)" >&2
    return 3
  }
  local pm_origin_main_sha pm_skill_version
  pm_origin_main_sha=$(git -C "$local_project" rev-parse --verify origin/main^{commit}) || return 3
  pm_skill_version=$(grep -m1 -oE '\[[0-9]+\.[0-9]+\.[0-9]+\]' "$SKILL_DIR/CHANGELOG.md" | tr -d '[]')
  [ -n "$pm_skill_version" ] || { echo "ERROR: cannot read PM skill version from CHANGELOG.md" >&2; return 64; }

  # 3) PM 软账自限（硬限制在节点本机 lease；软账只收紧不放宽）
  local ledger_dir
  ledger_dir=$(remote_ledger_dir "$local_project") || return 64
  if [ -f "$ledger_dir/$node/$session.json" ]; then
    printf 'ERROR: session %s already dispatched to node %s (软账存在；先 cleanup 或换名)\n' "$session" "$node" >&2
    return 64
  fi
  local active_count
  active_count=$(remote_ledger_active_count "$ledger_dir" "$node")
  if [ "$active_count" -ge "$REMOTE_NODE_MAX_WORKERS" ]; then
    printf 'PARKED_FOR_REMOTE_CAPACITY: PM 软账在途 %s/%s（remote_nodes.%s.max_workers）；等待结算或改派\n' \
      "$active_count" "$REMOTE_NODE_MAX_WORKERS" "$node" >&2
    return 75
  fi

  # 4) 节点探测：可达性/容量/基线/版本/claude（任何 ssh 派发副作用之前）
  local probe_rc=0 probe_json
  probe_json=$(python3 "$SCRIPT_DIR/remote-node-probe.py" --node "$node" --config "$PERSONAL_CONFIG_FILE" \
    --ssh-command "$REMOTE_DISPATCH_SSH_BIN" \
    --expect-base-sha "$pm_origin_main_sha" --expect-skill-version "$pm_skill_version") || probe_rc=$?
  if [ "$probe_rc" -eq 3 ] && [ "$provision" -eq 1 ] \
     && grep -qE 'REMOTE_NODE_ROOT_MISSING|REMOTE_NODE_ROOT_NOT_GIT' <<<"$probe_json"; then
    # --provision：节点缺项目路径时自动补装（clone + ORCA 注册），随后原样重探一次
    printf 'SPAWN_WORKER_REMOTE_PROVISION: 节点缺项目路径，自动补装后重探\n' >&2
    if [ -n "$local_project" ]; then
      cmd_provision --node "$node" --local-project "$local_project" || return $?
    else
      cmd_provision --node "$node" || return $?
    fi
    probe_rc=0
    probe_json=$(python3 "$SCRIPT_DIR/remote-node-probe.py" --node "$node" --config "$PERSONAL_CONFIG_FILE" \
      --ssh-command "$REMOTE_DISPATCH_SSH_BIN" \
      --expect-base-sha "$pm_origin_main_sha" --expect-skill-version "$pm_skill_version") || probe_rc=$?
  fi
  if [ "$probe_rc" -ne 0 ]; then
    printf '%s\n' "$probe_json" >&2
    case "$probe_rc" in
      4) printf 'PARKED_FOR_REMOTE_CAPACITY: 节点容量门拒绝；排队重试，不自动回落本机\n' >&2 ;;
      65) printf 'REMOTE_NODE_DOWN: 节点不可达；如需继续可回落本机派发（全新本机 spawn，重走全套门禁）\n' >&2 ;;
      3) printf 'REMOTE_NODE_PRECONDITION: 先修复（push/pull/对时/开节点；或 spawn --provision 自动补装），修复前该节点不接新派发\n' >&2 ;;
    esac
    return "$probe_rc"
  fi
  printf 'SPAWN_WORKER_REMOTE_PROBE: node=%s %s\n' "$node" "$(printf '%s' "$probe_json" | jq -c '{status,load,active_sessions:.runtime.active_sessions,origin_main:.git.origin_main_sha}')"
  local remote_bash_bin
  remote_bash_bin=$(printf '%s' "$probe_json" | jq -r '.runtime.bash_path')
  [ -n "$remote_bash_bin" ] && [ -x "$remote_bash_bin" ] || {
    # probe 放行却拿不到 bash>=4 绝对路径 = 状态不一致，fail-closed
    echo "ERROR: probe ok but runtime.bash_path missing (fail-closed)" >&2
    return 64
  }

  # 5) 生成一次性 receipt 并传到节点受限 inbox
  local remote_branch receipt_local receipt_name receipt_remote receipt_sha
  remote_branch="node-${node}/${branch}"
  receipt_local=$(mktemp "${TMPDIR:-/tmp}/remote-receipt.XXXXXX.json")
  receipt_name="receipt-$(date +%Y%m%d%H%M%S)-$$.json"
  receipt_remote="$REMOTE_NODE_SKILL_ROOT/config/remote-dispatch-inbox/$receipt_name"
  local issue_args=(--file "$receipt_local" --node "$node" --pm-harness "$pm_harness"
    --chain-json "$pm_chain" --worker-backend "$WORKER_BACKEND_CANONICAL"
    --branch "$remote_branch" --session "$session")
  [ -n "$receipt_ttl" ] && issue_args+=(--ttl-seconds "$receipt_ttl")
  receipt_sha=$(remote_receipt_issue "${issue_args[@]}" | awk '{print $1}')
  [ -n "$receipt_sha" ] || { echo "ERROR: receipt issue failed" >&2; rm -f "$receipt_local"; return 64; }
  $REMOTE_DISPATCH_SSH_BIN -o BatchMode=yes -o ConnectTimeout=15 "$REMOTE_NODE_SSH_ALIAS" \
    "mkdir -p '$REMOTE_NODE_SKILL_ROOT/config/remote-dispatch-inbox' && chmod 700 '$REMOTE_NODE_SKILL_ROOT/config/remote-dispatch-inbox'" || {
    rm -f "$receipt_local"; return 65; }
  # receipt 传输用 ssh cat 流式写入：远端路径整体单引号包裹不踩 shell 词法；
  # 不用 rsync/scp——macOS 上 rsync 是 Xcode shim，CLT license 未接受时整体不可用
  # （2026-09-29 真机 E2E 实测），ssh cat 只依赖 ssh 通道本身。
  $REMOTE_DISPATCH_SSH_BIN -o BatchMode=yes -o ConnectTimeout=15 "$REMOTE_NODE_SSH_ALIAS" \
    "cat > '$receipt_remote'" < "$receipt_local" || { rm -f "$receipt_local"; return 65; }
  $REMOTE_DISPATCH_SSH_BIN -o BatchMode=yes "$REMOTE_NODE_SSH_ALIAS" "chmod 600 '$receipt_remote'" || true
  rm -f "$receipt_local"

  # 6) ssh 调节点本机 spawn-worker.sh（zsh -lc 拿登录 PATH；前置 unset provider env；
  #    固定 --base-ref origin/main 防基线漂移）
  local remote_args=(
    --project "$REMOTE_NODE_ROOT"
    --branch "$remote_branch"
    --base-ref origin/main
    --session "$session"
    --worker-backend "$WORKER_BACKEND_CANONICAL"
    --remote-dispatch-receipt "$receipt_remote"
  )
  [ -n "$command" ] && remote_args+=(--command "$command")
  [ -n "$api_provider" ] && remote_args+=(--api-provider "$api_provider")
  [ -n "$model" ] && remote_args+=(--model "$model")
  [ -n "$runtime_profile" ] && remote_args+=(--runtime-profile "$runtime_profile")
  [ "$require_verification" -eq 1 ] && remote_args+=(--require-verification)
  local verify_command
  for verify_command in "${verify_commands[@]}"; do
    remote_args+=(--verify-cmd "$verify_command")
  done

  local unset_prefix="" env_key
  for env_key in "${REMOTE_PROVIDER_ENV_KEYS[@]}"; do
    unset_prefix+="unset $env_key; "
  done
  # --remote-env：节点侧调优变量（如 SPAWN_WORKER_MEM_BUDGET_BYTES）在 unset 之后、
  # exec 之前 export；值为原样单引号包裹（含空格安全）。
  local env_prefix="" remote_env
  for remote_env in "${remote_envs[@]}"; do
    env_prefix+="export ${remote_env%%=*}=$(printf '%q' "${remote_env#*=}"); "
  done
  local remote_command="${unset_prefix}${env_prefix}exec '$remote_bash_bin' '$REMOTE_NODE_SKILL_ROOT/scripts/spawn-worker.sh' "
  local arg
  for arg in "${remote_args[@]}"; do
    remote_command+=$(printf '%q ' "$arg")
  done

  local spawn_output spawn_rc=0
  spawn_output=$(mktemp "${TMPDIR:-/tmp}/remote-spawn.XXXXXX.out")
  $REMOTE_DISPATCH_SSH_BIN -o BatchMode=yes -o ConnectTimeout=15 "$REMOTE_NODE_SSH_ALIAS" \
    "zsh -lc $(printf '%q' "$remote_command")" > "$spawn_output" 2>&1 || spawn_rc=$?
  cat "$spawn_output"
  if [ "$spawn_rc" -ne 0 ]; then
    $REMOTE_DISPATCH_SSH_BIN -o BatchMode=yes -o ConnectTimeout=10 "$REMOTE_NODE_SSH_ALIAS" "rm -f '$receipt_remote'" 2>/dev/null || true
    printf 'ERROR: remote spawn failed rc=%s（receipt 已回收；软账未落盘）\n' "$spawn_rc" >&2
    rm -f "$spawn_output"
    return "$spawn_rc"
  fi

  # 7) 从节点输出解析 Session Context 锚点并落 PM 软账
  local remote_metadata_file remote_status_file
  remote_metadata_file=$(grep -m1 'SPAWN_WORKER_METADATA: ' "$spawn_output" | sed 's/^SPAWN_WORKER_METADATA: //')
  rm -f "$spawn_output"
  [ -n "$remote_metadata_file" ] || {
    echo "ERROR: cannot parse SPAWN_WORKER_METADATA from remote output（worker 已起但软账缺锚点；人工核对节点侧）" >&2
    return 64
  }
  remote_status_file=$(dirname "$remote_metadata_file")/STATUS.json
  mkdir -p "$ledger_dir/$node"
  jq -n \
    --arg schema "$LEDGER_SCHEMA" \
    --arg node "$node" --arg session "$session" --arg branch "$branch" --arg remote_branch "$remote_branch" \
    --arg worker_backend "$WORKER_BACKEND_CANONICAL" --arg pm_harness "$pm_harness" --arg pm_harness_source "$pm_source" \
    --arg receipt_file "$receipt_remote" --arg receipt_sha256 "$receipt_sha" \
    --arg remote_root "$REMOTE_NODE_ROOT" --arg remote_skill_root "$REMOTE_NODE_SKILL_ROOT" \
    --arg remote_metadata_file "$remote_metadata_file" --arg remote_status_file "$remote_status_file" \
    --arg pm_origin_main_sha "$pm_origin_main_sha" --arg pm_skill_version "$pm_skill_version" \
    --argjson spawned_at_epoch "$(date +%s)" \
    '{schema: $schema, node: $node, session: $session, branch: $branch, remote_branch: $remote_branch,
      worker_backend: $worker_backend, pm_harness: $pm_harness, pm_harness_source: $pm_harness_source,
      receipt: {inbox_file: $receipt_file, sha256: $receipt_sha256},
      remote: {root: $remote_root, skill_root: $remote_skill_root,
               metadata_file: $remote_metadata_file, status_file: $remote_status_file},
      pm: {origin_main_sha: $pm_origin_main_sha, skill_version: $pm_skill_version},
      spawned_at_epoch: $spawned_at_epoch, last_poll_at_epoch: null, state: "dispatched"}' \
    > "$ledger_dir/$node/$session.json"
  chmod 600 "$ledger_dir/$node/$session.json"
  printf 'SPAWN_WORKER_REMOTE_OK: node=%s session=%s branch=%s\n' "$node" "$session" "$remote_branch"
  printf '后续：status → %s status --node %s --session %s\n' "$0" "$node" "$session"
  printf '      cleanup → %s cleanup --node %s --session %s（PR 合并/关闭后）\n' "$0" "$node" "$session"
  return 0
}

# personal config 里的 allowed_backends 规范化列表（空格分隔）
remote_node_allowed_backends() {
  local node="$1" item normalized
  local result=()
  for item in $REMOTE_NODE_ALLOWED_BACKENDS; do
    normalized=$(canonical_harness_backend "$item" 2>/dev/null) || continue
    result+=("$normalized")
  done
  printf '%s\n' "${result[*]}"
}

remote_ledger_read() {
  local ledger_file="$1"
  [ -f "$ledger_file" ] || {
    echo "ERROR: ledger not found: $ledger_file（该 session 未派发过？）" >&2
    return 64
  }
  jq -er '.' "$ledger_file" >/dev/null
}

# ---- status 子命令 -----------------------------------------------------------

cmd_status() {
  local node="" session="" local_project=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --node) node="$2"; shift 2 ;;
      --session) session="$2"; shift 2 ;;
      --local-project) local_project="$2"; shift 2 ;;
      *) printf 'ERROR: status: unknown argument: %s\n' "$1" >&2; return 64 ;;
    esac
  done
  [ -n "$node" ] && [ -n "$session" ] || { echo "ERROR: status requires --node and --session" >&2; return 64; }
  remote_node_config_load "$node" || return $?
  if [ -z "$local_project" ]; then
    local_project=$(git -C "$SKILL_DIR" rev-parse --show-toplevel 2>/dev/null) || {
      echo "ERROR: cannot derive local project; pass --local-project" >&2
      return 64
    }
  fi
  local ledger_dir ledger_file
  ledger_dir=$(remote_ledger_dir "$local_project") || return 64
  ledger_file="$ledger_dir/$node/$session.json"
  remote_ledger_read "$ledger_file" || return 64

  local remote_status_file remote_branch
  remote_status_file=$(jq -r '.remote.status_file' "$ledger_file")
  remote_branch=$(jq -r '.remote_branch' "$ledger_file")
  printf '== 远程 STATUS.json ==\n'
  $REMOTE_DISPATCH_SSH_BIN -o BatchMode=yes -o ConnectTimeout=15 "$REMOTE_NODE_SSH_ALIAS" \
    "cat '$remote_status_file' 2>/dev/null || echo '(尚无 STATUS.json——worker 刚启动或路径未生成)'" || true
  printf '== PR（GitHub 共享事实） ==\n'
  if command -v gh >/dev/null 2>&1; then
    gh pr list --head "$remote_branch" --json number,title,state,url 2>/dev/null \
      | jq -r '.[] | "#\(.number) [\(.state)] \(.title) \(.url)"' || echo '(gh pr list 失败或无 PR)'
    if [ "$(gh pr list --head "$remote_branch" --json number 2>/dev/null | jq 'length')" = "0" ]; then
      echo '(该分支暂无 PR)'
    fi
  else
    echo '(本机无 gh，跳过 PR 查询)'
  fi
  local status_state=""
  status_state=""
  if ! status_state=$($REMOTE_DISPATCH_SSH_BIN -o BatchMode=yes -o ConnectTimeout=15 "$REMOTE_NODE_SSH_ALIAS" \
      "jq -r '.status // empty' '$remote_status_file' 2>/dev/null"); then
    printf 'WARN: 远程 STATUS 读取失败（节点不可达？），按非终态处理（fail-closed）\n' >&2
    status_state=""
  fi
  case "$status_state" in
    done|failed|blocked|stopped) jq --argjson now "$(date +%s)" --arg s "$status_state" \
        '.last_poll_at_epoch=$now | .state=$s' \
        "$ledger_file" > "$ledger_file.tmp" && mv "$ledger_file.tmp" "$ledger_file" ;;
    *) jq --argjson now "$(date +%s)" '.last_poll_at_epoch=$now' \
        "$ledger_file" > "$ledger_file.tmp" && mv "$ledger_file.tmp" "$ledger_file" ;;
  esac
  printf '软账: %s state=%s\n' "$ledger_file" "$(jq -r '.state' "$ledger_file")"
  return 0
}

# ---- cleanup 子命令 ----------------------------------------------------------

cmd_cleanup() {
  local node="" session="" local_project="" force_reason=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --node) node="$2"; shift 2 ;;
      --session) session="$2"; shift 2 ;;
      --local-project) local_project="$2"; shift 2 ;;
      --force-with-reason) force_reason="$2"; shift 2 ;;
      *) printf 'ERROR: cleanup: unknown argument: %s\n' "$1" >&2; return 64 ;;
    esac
  done
  [ -n "$node" ] && [ -n "$session" ] || { echo "ERROR: cleanup requires --node and --session" >&2; return 64; }
  remote_node_config_load "$node" || return $?
  if [ -z "$local_project" ]; then
    local_project=$(git -C "$SKILL_DIR" rev-parse --show-toplevel 2>/dev/null) || {
      echo "ERROR: cannot derive local project; pass --local-project" >&2
      return 64
    }
  fi
  local ledger_dir ledger_file remote_branch
  ledger_dir=$(remote_ledger_dir "$local_project") || return 64
  ledger_file="$ledger_dir/$node/$session.json"
  remote_ledger_read "$ledger_file" || return 64
  remote_branch=$(jq -r '.remote_branch' "$ledger_file")

  # 前置：PR 终态（MERGED/CLOSED）或 STATUS 终态；都没有则要求显式 --force-with-reason
  local pr_state="" terminal=0
  if command -v gh >/dev/null 2>&1; then
    pr_state=$(gh pr list --head "$remote_branch" --json state --limit 1 2>/dev/null | jq -r '.[0].state // empty')
  fi
  case "$pr_state" in MERGED|CLOSED) terminal=1 ;; esac
  if [ "$terminal" -eq 0 ]; then
    local status_state
    status_state=""
    if ! status_state=$($REMOTE_DISPATCH_SSH_BIN -o BatchMode=yes -o ConnectTimeout=15 "$REMOTE_NODE_SSH_ALIAS" \
        "jq -r '.status // empty' '$(jq -r '.remote.status_file' "$ledger_file")' 2>/dev/null"); then
      printf 'WARN: 远程 STATUS 读取失败（节点不可达？），cleanup 前置按非终态处理（fail-closed）\n' >&2
      status_state=""
    fi
    case "$status_state" in done|failed|stopped) terminal=1 ;; esac
  fi
  if [ "$terminal" -eq 0 ] && [ -z "$force_reason" ]; then
    printf 'ERROR: cleanup 前置未满足：PR state=%s 非终态且 STATUS 非终态；确认后用 --force-with-reason "<原因>" 强制\n' \
      "${pr_state:-unknown}" >&2
    return 64
  fi

  # 节点侧 dry-run → execute（幂等；转发 pm-cleanup-worker.sh 的判定与输出）
  local remote_root cleanup_command extra arg
  remote_root=$(jq -r '.remote.root' "$ledger_file")
  for extra in "" "--execute"; do
    cleanup_command="exec '$REMOTE_NODE_SKILL_ROOT/scripts/pm-cleanup-worker.sh' --project "
    for arg in "$remote_root" "$session"; do
      cleanup_command+=$(printf '%q ' "$arg")
    done
    cleanup_command+="$extra"
    if ! $REMOTE_DISPATCH_SSH_BIN -o BatchMode=yes -o ConnectTimeout=15 "$REMOTE_NODE_SSH_ALIAS" \
        "zsh -lc $(printf '%q' "$cleanup_command")"; then
      if [ -z "$extra" ]; then
        echo "ERROR: 节点侧 cleanup dry-run 失败（不落 --execute）" >&2
      else
        echo "ERROR: 节点侧 cleanup --execute 失败；软账保留以便重试" >&2
      fi
      return 64
    fi
  done
  rm -f "$ledger_file"
  printf 'SPAWN_WORKER_REMOTE_CLEANED: node=%s session=%s（节点资源已收口，软账已删）\n' "$node" "$session"
  return 0
}

# ---- provision 子命令（节点路径检查 + 首次部署 + ORCA 项目注册） ----------------
# 与本机派发同款前置：本机 spawn 依赖项目路径存在且（Orca 模式下）repo 已注册；
# 远程节点首次派发前可能两者皆无。本子命令幂等：
#   A. remote_root 不存在 → 从 PM 的 origin URL clone（节点需有对应凭证）
#   B. skill CHANGELOG 校验（本 skill 应随同一仓库分发；否则要求手动部署）
#   C. 节点侧 orca-register-project.py 注册（互斥锁内 selector 查找 + repo add）
#   D. 复跑 probe 汇报就绪度

cmd_provision() {
  local node="" local_project="" skip_clone=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --node) node="$2"; shift 2 ;;
      --local-project) local_project="$2"; shift 2 ;;
      --skip-clone) skip_clone=1; shift ;;
      *) printf 'ERROR: provision: unknown argument: %s\n' "$1" >&2; return 64 ;;
    esac
  done
  [ -n "$node" ] || { echo "ERROR: provision requires --node" >&2; return 64; }
  remote_node_config_load "$node" || return $?
  if [ -z "$local_project" ]; then
    local_project=$(git -C "$SKILL_DIR" rev-parse --show-toplevel 2>/dev/null) || {
      echo "ERROR: cannot derive local project; pass --local-project" >&2
      return 64
    }
  fi
  [ -n "$local_project" ] || { echo "ERROR: cannot derive local project; pass --local-project" >&2; return 64; }
  local origin_url
  origin_url=$(git -C "$local_project" remote get-url origin) || {
    echo "ERROR: local project has no origin remote: $local_project" >&2
    return 64
  }

  # A. 路径检查 + clone（幂等：已存在则跳过）
  local root_exists
  root_exists=$($REMOTE_DISPATCH_SSH_BIN -o BatchMode=yes -o ConnectTimeout=15 \
    "$REMOTE_NODE_SSH_ALIAS" "test -d '$REMOTE_NODE_ROOT' && echo 1 || echo 0") || return 65
  if [ "$root_exists" = "1" ]; then
    printf 'PROVISION: remote_root 已存在：%s\n' "$REMOTE_NODE_ROOT"
  elif [ "$skip_clone" -eq 1 ]; then
    printf 'PROVISION: remote_root 缺失且 --skip-clone：%s\n' "$REMOTE_NODE_ROOT" >&2
    return 3
  else
    printf 'PROVISION: clone %s → %s\n' "$origin_url" "$REMOTE_NODE_ROOT"
    $REMOTE_DISPATCH_SSH_BIN -o BatchMode=yes -o ConnectTimeout=15 "$REMOTE_NODE_SSH_ALIAS" \
      "zsh -lc $(printf '%q' "git clone --origin origin $(printf '%q ' "$origin_url" "$REMOTE_NODE_ROOT")")" || {
        printf 'ERROR: 节点 clone 失败（检查节点凭证是否能读 %s）\n' "$origin_url" >&2
        return 3
      }
  fi

  # B. skill 随仓库分发校验
  local skill_changelog
  skill_changelog=$($REMOTE_DISPATCH_SSH_BIN -o BatchMode=yes -o ConnectTimeout=15 \
    "$REMOTE_NODE_SSH_ALIAS" "test -f '$REMOTE_NODE_SKILL_ROOT/CHANGELOG.md' && echo 1 || echo 0") || return 65
  if [ "$skill_changelog" != "1" ]; then
    printf 'ERROR: 节点缺本 skill（%s/CHANGELOG.md 不存在）：本机制假设 skill 随项目仓库分发；独立部署请手动同步后重试\n' \
      "$REMOTE_NODE_SKILL_ROOT" >&2
    return 3
  fi

  # C. 节点侧 ORCA 项目注册（与本机 spawn 前置同款；互斥锁内注册 + 注册后身份复核）
  local register_command
  register_command="ci=\$(command -v orca); [ -n \"\$ci\" ] || { echo 'ERROR: node has no orca in login PATH' >&2; exit 3; }; "
  register_command+="exec python3 '$REMOTE_NODE_SKILL_ROOT/scripts/orca-register-project.py' --project $(printf '%q' "$REMOTE_NODE_ROOT") --orca-cli \"\$ci\""
  printf 'PROVISION: 节点侧 ORCA 项目注册（orca-register-project.py）\n'
  $REMOTE_DISPATCH_SSH_BIN -o BatchMode=yes -o ConnectTimeout=30 "$REMOTE_NODE_SSH_ALIAS" \
    "zsh -lc $(printf '%q' "$register_command")" || {
      echo "ERROR: 节点侧 ORCA 注册失败（看上方脚本输出；已注册/并发注册会由其互斥逻辑判定）" >&2
      return 3
    }

  # D. 复跑 probe 汇报就绪度（不比对基线/版本——provision 后基线即 origin/main）
  printf 'PROVISION: 复跑 probe 确认就绪\n'
  local probe_rc=0
  python3 "$SCRIPT_DIR/remote-node-probe.py" --node "$node" --config "$PERSONAL_CONFIG_FILE" \
    --ssh-command "$REMOTE_DISPATCH_SSH_BIN" --skip-fetch || probe_rc=$?
  printf 'PROVISION: probe rc=%s（0=就绪；3=先 push/pull 对齐基线）\n' "$probe_rc"
  return "$probe_rc"
}


if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  [ "$#" -ge 1 ] || { remote_usage; exit 64; }
  subcommand="spawn"
  case "$1" in
    spawn|provision|status|cleanup) subcommand="$1"; shift ;;
    --*) ;;
    *) printf 'ERROR: unknown subcommand: %s\n' "$1" >&2; remote_usage; exit 64 ;;
  esac
  case "$subcommand" in
    spawn) cmd_spawn "$@" ;;
    provision) cmd_provision "$@" ;;
    status) cmd_status "$@" ;;
    cleanup) cmd_cleanup "$@" ;;
  esac
fi
