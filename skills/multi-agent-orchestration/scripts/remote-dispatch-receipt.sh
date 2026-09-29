#!/usr/bin/env bash
# remote-dispatch-receipt.sh — 远程节点派发的一次性授权回执（remote dispatch receipt）。
#
# 背景（references/25-remote-node-dispatch.md）：PM 在本机用 detect_pm_harness 完成
# ps 祖先链验证后，经 ssh 把 Worker 派到远程节点执行。远程节点上的 spawn-worker.sh
# 无法复现这条祖先链（ssh 会话的祖先是 sshd，无 claude 帧，按 fail-closed 拒绝——
# 这是正确行为，不得削弱）。本模块把「PM 本机已验证的 harness 事实」以一次性回执
# 的形式传输到远程节点，替代进程链证据：
#
#   remote_receipt_issue  （PM 本机）生成回执：nonce 一次性 + TTL 短窗 + 绑定
#                         node/pm_harness/chain/worker_backend/branch/session。
#   remote_receipt_consume（远程节点）校验并原子消费：schema/TTL/未消费/字段全匹配，
#                         通过即写入 consumed_at_epoch 并 chmod 400（不可逆）。
#
# 安全论证：回执不创造新 authority，只传输 PM 本机已成立的检测结果；后续
# enforce_harness_backend_policy_chain 仍用原版交集函数（authority 不放大）；
# nonce 一次性消费 + 300s 默认 TTL + 受限 inbox 目录 600 权限 + consumed 不可逆，
# 把重放/伪造面收敛到 inbox 目录的写权限本身。harness-backend-policy.json 的
# remote_dispatch.enabled=false 可在远程侧全局禁用本通道。
#
# 命令身份（command_sha256）不在回执绑定范围内：spawn-worker.sh 自带的
# validate_worker_command_backend 门禁对远程派发同样生效，无需重复绑定。
set -euo pipefail

REMOTE_RECEIPT_SCHEMA="multi-agent-orchestration.remote-dispatch-receipt.v1"
REMOTE_RECEIPT_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REMOTE_RECEIPT_DEFAULT_TTL_SECONDS=300

# policy 路径每次调用时解析（REMOTE_DISPATCH_POLICY_FILE 仅测试注入用），
# 不在 source 时固化——否则运行中切换 fixture 不生效。
remote_receipt_policy_path() {
  printf '%s\n' "${REMOTE_DISPATCH_POLICY_FILE:-$REMOTE_RECEIPT_SCRIPT_DIR/../config/harness-backend-policy.json}"
}

# 惰性复用 harness-backend-policy.sh 的 canonical_harness_backend（spawn-worker.sh
# 场景下已被 source，独立测试场景下现场补载）。只做规范化，不做任何 policy 判定。
_remote_receipt_ensure_canonical_helper() {
  if ! declare -F canonical_harness_backend >/dev/null 2>&1; then
    # shellcheck source=harness-backend-policy.sh
    source "$REMOTE_RECEIPT_SCRIPT_DIR/harness-backend-policy.sh" >/dev/null 2>&1
  fi
  declare -F canonical_harness_backend >/dev/null 2>&1 || {
    echo "ERROR: remote receipt: canonical_harness_backend unavailable (harness-backend-policy.sh missing?)" >&2
    return 64
  }
}

# 远程侧全局开关：harness-backend-policy.json .remote_dispatch.enabled 必须 === true；
# 段缺失 / 文件缺失 / 值非 true 一律视为禁用（fail-closed）。
remote_dispatch_policy_enabled() {
  local policy_file
  policy_file=$(remote_receipt_policy_path)
  [ -f "$policy_file" ] || {
    echo "ERROR: REMOTE_RECEIPT_POLICY_DISABLED: policy file missing: $policy_file" >&2
    return 64
  }
  jq -er 'select(.remote_dispatch.enabled == true) | .remote_dispatch.max_ttl_seconds // 300' \
    "$policy_file" >/dev/null 2>&1 || {
    printf 'ERROR: REMOTE_RECEIPT_POLICY_DISABLED: remote_dispatch.enabled is not true in %s (fail-closed)\n' \
      "$policy_file" >&2
    return 64
  }
}

# remote_receipt_issue --file F --node N --pm-harness H --chain-json JSON
#                       --worker-backend B --branch BR --session S [--ttl-seconds T]
# 成功：把回执原子写入 F（chmod 600），stdout 打印回执 sha256（消费侧审计锚点）。
remote_receipt_issue() {
  _remote_receipt_ensure_canonical_helper || return $?
  remote_dispatch_policy_enabled || return $?

  local out_file="" node="" pm_harness="" chain_json="" worker_backend="" branch="" session=""
  local ttl_seconds="$REMOTE_RECEIPT_DEFAULT_TTL_SECONDS"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --file) out_file="$2"; shift 2 ;;
      --node) node="$2"; shift 2 ;;
      --pm-harness) pm_harness="$2"; shift 2 ;;
      --chain-json) chain_json="$2"; shift 2 ;;
      --worker-backend) worker_backend="$2"; shift 2 ;;
      --branch) branch="$2"; shift 2 ;;
      --session) session="$2"; shift 2 ;;
      --ttl-seconds) ttl_seconds="$2"; shift 2 ;;
      *) echo "ERROR: remote_receipt_issue: unknown argument: $1" >&2; return 64 ;;
    esac
  done
  local missing=()
  [ -n "$out_file" ] || missing+=(--file)
  [ -n "$node" ] || missing+=(--node)
  [ -n "$pm_harness" ] || missing+=(--pm-harness)
  [ -n "$chain_json" ] || missing+=(--chain-json)
  [ -n "$worker_backend" ] || missing+=(--worker-backend)
  [ -n "$branch" ] || missing+=(--branch)
  [ -n "$session" ] || missing+=(--session)
  if [ "${#missing[@]}" -gt 0 ]; then
    printf 'ERROR: remote_receipt_issue: missing required arguments: %s\n' "${missing[*]}" >&2
    return 64
  fi
  case "$ttl_seconds" in ''|*[!0-9]*) echo "ERROR: remote_receipt_issue: --ttl-seconds must be a positive integer: $ttl_seconds" >&2; return 64 ;; esac

  # TTL 不得超过 policy 上限（issue 侧同样受远程侧策略约束，防 PM 私自发长窗回执）。
  local max_ttl
  max_ttl=$(jq -r '.remote_dispatch.max_ttl_seconds // 300' "$(remote_receipt_policy_path)")
  if [ "$ttl_seconds" -gt "$max_ttl" ]; then
    printf 'ERROR: REMOTE_RECEIPT_TTL_EXCEEDS_POLICY: %s > max_ttl_seconds=%s (fail-closed)\n' \
      "$ttl_seconds" "$max_ttl" >&2
    return 64
  fi

  pm_harness=$(canonical_harness_backend "$pm_harness") || {
    echo "ERROR: remote_receipt_issue: unsupported --pm-harness (fail-closed)" >&2
    return 64
  }
  worker_backend=$(canonical_harness_backend "$worker_backend") || {
    echo "ERROR: remote_receipt_issue: unsupported --worker-backend (fail-closed)" >&2
    return 64
  }
  # chain 必须是合法 JSON 数组且逐项可规范化（后续交集检查仍会二次校验）。
  chain_json=$(printf '%s' "$chain_json" | jq -c '. as $c | select(($c|type)=="array" and ($c|length)>0) | $c' 2>/dev/null) || {
    echo "ERROR: remote_receipt_issue: --chain-json must be a non-empty JSON array" >&2
    return 64
  }
  [ -n "$chain_json" ] || {
    echo "ERROR: remote_receipt_issue: --chain-json must be a non-empty JSON array" >&2
    return 64
  }
  local chain_item
  for chain_item in $(printf '%s' "$chain_json" | jq -r '.[]'); do
    canonical_harness_backend "$chain_item" >/dev/null || {
      printf 'ERROR: remote_receipt_issue: chain item cannot canonicalize: %s (fail-closed)\n' "$chain_item" >&2
      return 64
    }
  done

  local nonce issued_at expires_at receipt_json out_dir
  nonce=$(head -c 32 /dev/urandom 2>/dev/null | shasum -a 256 | cut -d' ' -f1)
  [ -n "$nonce" ] || { echo "ERROR: remote_receipt_issue: nonce generation failed" >&2; return 64; }
  issued_at=$(date +%s)
  expires_at=$((issued_at + ttl_seconds))
  receipt_json=$(jq -cn \
    --arg schema "$REMOTE_RECEIPT_SCHEMA" \
    --arg node "$node" \
    --arg pm_harness "$pm_harness" \
    --argjson pm_harness_chain "$chain_json" \
    --arg worker_backend "$worker_backend" \
    --arg branch "$branch" \
    --arg session "$session" \
    --argjson issued_at_epoch "$issued_at" \
    --argjson expires_at_epoch "$expires_at" \
    --arg nonce "$nonce" \
    '{schema: $schema, node: $node, pm_harness: $pm_harness, pm_harness_chain: $pm_harness_chain,
      worker_backend: $worker_backend, branch: $branch, session: $session,
      issued_at_epoch: $issued_at_epoch, expires_at_epoch: $expires_at_epoch, nonce: $nonce,
      consumed_at_epoch: null}')

  out_dir=$(dirname "$out_file")
  mkdir -p "$out_dir"
  chmod 700 "$out_dir" 2>/dev/null || true
  local tmp_file
  tmp_file=$(mktemp "$out_dir/.receipt.XXXXXX")
  printf '%s\n' "$receipt_json" > "$tmp_file"
  chmod 600 "$tmp_file"
  mv -f "$tmp_file" "$out_file"
  printf '%s  %s\n' "$(shasum -a 256 "$out_file" | cut -d' ' -f1)" "$out_file"
}

# remote_receipt_consume --file F [--expect-node N] [--expect-worker-backend B]
#                         [--expect-branch BR] [--expect-session S] [--now-epoch E]
# 校验 + 原子消费。任一不符 exit 64（REMOTE_RECEIPT_* 错误码）；通过则设置：
#   REMOTE_DISPATCH_RECEIPT_PM_HARNESS / _PM_HARNESS_CHAIN_JSON / _NONCE / _SHA256
# （spawn-worker.sh 以 _PM_HARNESS 进入原版 enforce_harness_backend_policy_chain。）
remote_receipt_consume() {
  _remote_receipt_ensure_canonical_helper || return $?
  remote_dispatch_policy_enabled || return $?

  local file="" expect_node="" expect_worker_backend="" expect_branch="" expect_session="" now_epoch=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --file) file="$2"; shift 2 ;;
      --expect-node) expect_node="$2"; shift 2 ;;
      --expect-worker-backend) expect_worker_backend="$2"; shift 2 ;;
      --expect-branch) expect_branch="$2"; shift 2 ;;
      --expect-session) expect_session="$2"; shift 2 ;;
      --now-epoch) now_epoch="$2"; shift 2 ;;
      *) echo "ERROR: remote_receipt_consume: unknown argument: $1" >&2; return 64 ;;
    esac
  done
  [ -n "$file" ] || { echo "ERROR: remote_receipt_consume: --file is required" >&2; return 64; }
  [ -f "$file" ] || { echo "ERROR: REMOTE_RECEIPT_FILE_MISSING: $file (fail-closed)" >&2; return 64; }
  [ -n "$now_epoch" ] || now_epoch=$(date +%s)
  [ -n "$expect_worker_backend" ] && expect_worker_backend=$(canonical_harness_backend "$expect_worker_backend") || true

  # 消费动作（读-验-写回 consumed）在 python 内单文件 flock 下原子完成；
  # 任何一项不匹配即拒绝且不改文件（未消费的回执在 TTL 内可重试一次完整校验，
  # 但 consumed 标记一旦写入即不可逆）。
  local consume_output consume_rc=0
  consume_output=""
  consume_output=$(python3 - "$file" "$now_epoch" "$expect_node" "$expect_worker_backend" "$expect_branch" "$expect_session" <<'PY'
import fcntl, hashlib, json, os, stat, sys, tempfile

file_path, now_epoch, expect_node, expect_backend, expect_branch, expect_session = sys.argv[1:7]
now_epoch = int(now_epoch)
expectations = {
    "node": expect_node or None,
    "worker_backend": expect_backend or None,
    "branch": expect_branch or None,
    "session": expect_session or None,
}

def reject(reason, detail=""):
    print(f"ERROR: {reason}{(': ' + detail) if detail else ''} (fail-closed)", file=sys.stderr)
    sys.exit(64)

with open(file_path, "r", encoding="utf-8") as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    raw = f.read()
    try:
        receipt = json.loads(raw)
    except ValueError:
        reject("REMOTE_RECEIPT_MALFORMED_JSON", file_path)
    if receipt.get("schema") != "multi-agent-orchestration.remote-dispatch-receipt.v1":
        reject("REMOTE_RECEIPT_SCHEMA_MISMATCH", str(receipt.get("schema")))
    if receipt.get("consumed_at_epoch") is not None:
        reject("REMOTE_RECEIPT_ALREADY_CONSUMED", str(receipt.get("consumed_at_epoch")))
    expires = receipt.get("expires_at_epoch")
    if not isinstance(expires, int) or now_epoch > expires:
        reject("REMOTE_RECEIPT_EXPIRED", f"now={now_epoch} expires={expires}")
    issued = receipt.get("issued_at_epoch")
    if not isinstance(issued, int) or issued > expires:
        reject("REMOTE_RECEIPT_INVALID_WINDOW", f"issued={issued} expires={expires}")
    for field, expected in expectations.items():
        if expected is not None and receipt.get(field) != expected:
            reject(f"REMOTE_RECEIPT_{field.upper()}_MISMATCH",
                   f"expected={expected} actual={receipt.get(field)}")
    chain = receipt.get("pm_harness_chain")
    if not isinstance(chain, list) or not chain:
        reject("REMOTE_RECEIPT_CHAIN_INVALID", str(chain))
    pm_harness = receipt.get("pm_harness")
    if not isinstance(pm_harness, str) or not pm_harness:
        reject("REMOTE_RECEIPT_PM_HARNESS_INVALID", str(pm_harness))
    nonce = receipt.get("nonce")
    if not isinstance(nonce, str) or len(nonce) < 16:
        reject("REMOTE_RECEIPT_NONCE_INVALID", str(nonce))
    sha256_before = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    receipt["consumed_at_epoch"] = now_epoch
    payload = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    directory = os.path.dirname(os.path.abspath(file_path))
    fd, tmp_path = tempfile.mkstemp(prefix=".consumed.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.chmod(tmp_path, 0o400)
        os.replace(tmp_path, file_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    result = {
        "node": receipt.get("node"),
        "pm_harness": pm_harness,
        "pm_harness_chain": chain,
        "nonce": nonce,
        "sha256": sha256_before,
    }
    print(json.dumps(result, ensure_ascii=False))
PY
  ) || consume_rc=$?
  [ "$consume_rc" -eq 0 ] || return "$consume_rc"

  REMOTE_DISPATCH_RECEIPT_NODE=$(printf '%s' "$consume_output" | jq -r '.node // empty')
  REMOTE_DISPATCH_RECEIPT_PM_HARNESS=$(printf '%s' "$consume_output" | jq -r '.pm_harness')
  REMOTE_DISPATCH_RECEIPT_PM_HARNESS_CHAIN_JSON=$(printf '%s' "$consume_output" | jq -c '.pm_harness_chain')
  REMOTE_DISPATCH_RECEIPT_NONCE=$(printf '%s' "$consume_output" | jq -r '.nonce')
  REMOTE_DISPATCH_RECEIPT_SHA256=$(printf '%s' "$consume_output" | jq -r '.sha256')
  printf 'SPAWN_WORKER_REMOTE_RECEIPT_CONSUMED: node=%s pm=%s backend=%s branch=%s nonce=%s sha256=%s\n' \
    "$expect_node" "$REMOTE_DISPATCH_RECEIPT_PM_HARNESS" "$expect_worker_backend" \
    "$expect_branch" "$REMOTE_DISPATCH_RECEIPT_NONCE" "${REMOTE_DISPATCH_RECEIPT_SHA256:0:12}"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  # CLI 直跑：issue/consume 两个子命令（测试与人工诊断用；正式链路由
  # spawn-worker-remote.sh / spawn-worker.sh 调函数）。
  usage() {
    cat >&2 <<USAGE
Usage:
  remote-dispatch-receipt.sh issue --file F --node N --pm-harness H --chain-json JSON \\
      --worker-backend B --branch BR --session S [--ttl-seconds T]
  remote-dispatch-receipt.sh consume --file F [--expect-node N] \\
      [--expect-worker-backend B] [--expect-branch BR] [--expect-session S] [--now-epoch E]
USAGE
  }
  [ "$#" -ge 1 ] || { usage; exit 64; }
  cmd="$1"; shift
  case "$cmd" in
    issue) remote_receipt_issue "$@" ;;
    consume) remote_receipt_consume "$@" ;;
    *) usage; exit 64 ;;
  esac
fi
