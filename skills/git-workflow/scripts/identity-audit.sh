#!/usr/bin/env bash
# 只读审计：提交身份自检（whoami）、历史身份/尾注审计（history）与服务端合并回执核验（receipt）。
#
# 2026-09-30 实录背景：private-skills 仓库级 .git/config 被写入
# Hermes(info-assistant) 身份——190 个提交作者被污染，且每次 PR squash 合并
# GitHub 自动把分支提交作者转成 Co-authored-by 尾注。既有门禁
# check-outgoing-identities.sh 在 push 时核验"传入的期望身份"，但期望值取自
# 被污染 config 时形同虚设，尾注也不在其检查范围。本脚本补齐三件事：
#   whoami  — commit 前自检：当前生效 user.name/email、来源链
#             （env → worktree → repo-local → global）、可疑身份模式、
#             仓库级/工作树级覆盖与 env 覆盖告警
#   history — 历史审计：全部分支（或指定 range）内 author/committer/
#             Co-authored-by 尾注身份分布，可疑项自动标注
#   receipt — 服务端合并回执核验（2026-10-03，Task-012）：对 committer 为
#             GitHub 服务端合成签名（GitHub <noreply@github.com>）的提交，
#             用 gh 认证通道查询本仓 MERGED PR 回执绑定 mergeCommit.oid，
#             机械区分「合法服务端 squash 产物」与「本地伪造」。回执必须
#             脚本自查，不接受任何传参回执；gh 不可用/查询失败一律
#             fail-closed（UNKNOWN）。只影响已合并历史的核对/本地同步对账
#             场景，不改变 push 门禁（safe-push/check-outgoing-identities）。
# 只读：不修改任何 Git 配置、refs、工作树或提交。非 0 退出 = 有发现。

set -euo pipefail

REPO="."
MODE="whoami"
EXPECTED_NAME=""
EXPECTED_EMAIL=""
ALLOW_LOCAL_OVERRIDE=0
RANGE_ARGS=(--all)
RECEIPT_GAVE_RANGE=0
RECEIPT_OIDS=()
MERGED_LIMIT=500
MAX_COMMITS=50000
ALLOW_EMAILS=()
ALLOW_NAMES=()

usage() {
  cat >&2 <<'USAGE'
用法：
  identity-audit.sh [whoami] [--repo PATH] [--expected-name NAME]
    [--expected-email EMAIL] [--allow-local-override]
  identity-audit.sh history [--repo PATH] [--range A..B | --all]
    [--max-commits N] [--allow-email EMAIL]... [--allow-name NAME]...
  identity-audit.sh receipt [--repo PATH] <oid>... [--merged-limit N]
  identity-audit.sh receipt [--repo PATH] --range A..B [--merged-limit N]

子命令：
  whoami   提交前自检（默认）：当前生效身份 + 来源链 + 可疑模式 + 覆盖告警
  history  历史审计：author/committer/Co-authored-by 尾注身份分布，可疑项标注
  receipt  服务端合并回执核验：committer=GitHub<noreply> 的提交按 gh 查询的
           MERGED PR 回执（mergeCommit.oid 绑定）判 ACCEPT / DENY_FORGED /
           UNKNOWN；非服务端提交 SKIP 不计。--range 适合本地同步对账前
           核 range 内服务端提交。

退出码：0 = 无发现；1 = 有发现（WARN/FAIL/DENY/UNKNOWN）；2 = 用法或环境错误。
门禁只读，不修改 Git 配置、refs、工作树或提交。
USAGE
}

die() {
  local code="$1"
  shift
  printf '%s: %s\n' "$code" "$*" >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    whoami|history|receipt)
      MODE="$1"
      shift
      ;;
    --repo)
      [ "$#" -ge 2 ] || die "IDENTITY_AUDIT_USAGE" "--repo 缺少参数"
      REPO="$2"
      shift 2
      ;;
    --merged-limit)
      [ "$#" -ge 2 ] || die "IDENTITY_AUDIT_USAGE" "--merged-limit 缺少参数"
      case "$2" in
        ''|*[!0-9]*) die "IDENTITY_AUDIT_USAGE" "--merged-limit 必须是正整数" ;;
      esac
      [ "$2" -gt 0 ] 2>/dev/null || die "IDENTITY_AUDIT_USAGE" "--merged-limit 必须是正整数"
      MERGED_LIMIT="$2"
      shift 2
      ;;
    --expected-name)
      [ "$#" -ge 2 ] || die "IDENTITY_AUDIT_USAGE" "--expected-name 缺少参数"
      EXPECTED_NAME="$2"
      shift 2
      ;;
    --expected-email)
      [ "$#" -ge 2 ] || die "IDENTITY_AUDIT_USAGE" "--expected-email 缺少参数"
      EXPECTED_EMAIL="$2"
      shift 2
      ;;
    --allow-local-override)
      ALLOW_LOCAL_OVERRIDE=1
      shift
      ;;
    --range)
      [ "$#" -ge 2 ] || die "IDENTITY_AUDIT_USAGE" "--range 缺少参数"
      RANGE_ARGS=("$2")
      RECEIPT_GAVE_RANGE=1
      shift 2
      ;;
    --all)
      RANGE_ARGS=(--all)
      shift
      ;;
    --max-commits)
      [ "$#" -ge 2 ] || die "IDENTITY_AUDIT_USAGE" "--max-commits 缺少参数"
      case "$2" in
        ''|*[!0-9]*) die "IDENTITY_AUDIT_USAGE" "--max-commits 必须是非负整数" ;;
      esac
      MAX_COMMITS="$2"
      shift 2
      ;;
    --allow-email)
      [ "$#" -ge 2 ] || die "IDENTITY_AUDIT_USAGE" "--allow-email 缺少参数"
      ALLOW_EMAILS+=("$2")
      shift 2
      ;;
    --allow-name)
      [ "$#" -ge 2 ] || die "IDENTITY_AUDIT_USAGE" "--allow-name 缺少参数"
      ALLOW_NAMES+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      usage
      die "IDENTITY_AUDIT_USAGE" "未知参数：$1"
      ;;
    *)
      # 位置参数：仅 receipt 子命令接受提交 OID
      if [ "$MODE" = "receipt" ]; then
        RECEIPT_OIDS+=("$1")
        shift
      else
        usage
        die "IDENTITY_AUDIT_USAGE" "未知参数：$1"
      fi
      ;;
  esac
done

[ -d "$REPO" ] || die "IDENTITY_AUDIT_NOT_REPOSITORY" "目录不存在：$REPO"
git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1 || \
  die "IDENTITY_AUDIT_NOT_REPOSITORY" "不是 Git worktree：$REPO"

# 判断 "Name <email>" 是否命中可疑模式：命中时输出原因并返回 1，否则返回 0。
# 模式依据 260930 全仓实测归纳：
#   邮箱：@localhost / *.local / *.invalid / *.test / @example.* / noreply@
#         （users.noreply.github.com 的 noreply 不贴着 @，不会误伤）
#   姓名：常见 agent 命名片段（hermes/openclaw/codex/claude/checkpointer/
#         minimax/glm/bot/agent/worker/dashboard/assistant，大小写不敏感）
# --allow-name/--allow-email 精确命中的身份放行（本人自定义身份、已确认的
# 协作者等）。
suspicious_reason() {
  local who="$1"
  local name="${who%% <*}"
  local email="${who##*<}"
  email="${email%>}"
  local allow
  for allow in "${ALLOW_NAMES[@]:-}"; do
    [ -n "$allow" ] && [ "$name" = "$allow" ] && return 0
  done
  for allow in "${ALLOW_EMAILS[@]:-}"; do
    [ -n "$allow" ] && [ "$email" = "$allow" ] && return 0
  done
  case "$email" in
    *@localhost|*.local|*.invalid|*.test|*@example.*|*noreply@*)
      printf '邮箱命中占位/agent 域模式'
      return 1
      ;;
  esac
  case "$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')" in
    *hermes*|*openclaw*|*codex*|*claude*|*checkpointer*|*minimax*|*glm-*|\
*agent*|*bot*|*worker*|*dashboard*|*assistant*)
      printf '姓名命中 agent 命名模式'
      return 1
      ;;
  esac
  return 0
}

# 从 stdin 读 "N<TAB>identity" 行打印分布表；发现可疑项时函数返回可疑计数。
print_identity_table() {
  local title="$1"
  local flagged=0 total=0 line count who reason
  printf '== %s ==\n' "$title"
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    count=${line%%$'\t'*}
    who=${line#*$'\t'}
    total=$((total + 1))
    if reason=$(suspicious_reason "$who"); then
      printf '%8s  %s\n' "$count" "$who"
    else
      flagged=$((flagged + 1))
      printf '%8s  %s   [可疑: %s]\n' "$count" "$who" "$reason"
    fi
  done
  [ "$total" -gt 0 ] || printf '（无记录）\n'
  return "$flagged"
}

# uniq -c 输出（"  N identity"）转成 "N<TAB>identity"，供分布表解析。
count_table() {
  awk '{c=$1; $1=""; sub(/^ /, ""); print c "\t" $0}'
}

cmd_whoami() {
  local eff_name eff_email warn=0 fail=0 reason origin
  eff_name=$(git -C "$REPO" config user.name 2>/dev/null) || eff_name=""
  eff_email=$(git -C "$REPO" config user.email 2>/dev/null) || eff_email=""
  [ -n "$eff_name" ] || { printf 'IDENTITY_AUDIT_FAIL: user.name 未设置\n'; exit 1; }
  [ -n "$eff_email" ] || { printf 'IDENTITY_AUDIT_FAIL: user.email 未设置\n'; exit 1; }

  printf '== Git 提交身份自检（whoami）==\n'
  printf '生效身份: %s <%s>\n' "$eff_name" "$eff_email"
  for key in user.name user.email; do
    origin=$(git -C "$REPO" config --show-origin --get "$key" 2>/dev/null | head -1 || true)
    printf '来源 %s: %s\n' "$key" "${origin:-（未设置）}"
  done

  # worktree/local 层覆盖是身份污染高发层（技能规范 worker 禁止写入）
  local scope key value
  for scope in local worktree; do
    for key in user.name user.email; do
      value=$(git -C "$REPO" config --"$scope" --get "$key" 2>/dev/null || true)
      [ -n "$value" ] || continue
      if [ "$ALLOW_LOCAL_OVERRIDE" = "1" ]; then
        printf 'IDENTITY_AUDIT_INFO: %s 级覆盖 %s=%s（--allow-local-override 已抑制告警）\n' \
          "$scope" "$key" "$value"
      else
        warn=$((warn + 1))
        printf 'IDENTITY_AUDIT_WARN: %s 级覆盖 %s=%s——规范禁止 worker 写仓库级 user.*；确认是否你本人设置（是则加 --allow-local-override）\n' \
          "$scope" "$key" "$value"
      fi
    done
  done
  [ "$warn" -gt 0 ] || printf '覆盖检查: 无仓库级/工作树级 user.* 覆盖\n'

  # env 覆盖只影响单次提交，但会静默压过 config，必须显式可见
  local env_var
  for env_var in GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL; do
    if [ -n "${!env_var:-}" ]; then
      warn=$((warn + 1))
      printf 'IDENTITY_AUDIT_WARN: %s=%s（env 覆盖，仅本次提交生效）\n' "$env_var" "${!env_var}"
    fi
  done

  if reason=$(suspicious_reason "$eff_name <$eff_email>"); then
    printf '可疑模式: 未命中\n'
  else
    warn=$((warn + 1))
    printf 'IDENTITY_AUDIT_WARN: 生效身份命中可疑模式（%s）——若是本人身份用 --allow-email/--allow-name 抑制\n' "$reason"
  fi

  if [ -n "$EXPECTED_NAME" ] && [ "$eff_name" != "$EXPECTED_NAME" ]; then
    fail=$((fail + 1))
    printf 'IDENTITY_AUDIT_FAIL: user.name=%s 与期望 %s 不符\n' "$eff_name" "$EXPECTED_NAME"
  fi
  if [ -n "$EXPECTED_EMAIL" ] && [ "$eff_email" != "$EXPECTED_EMAIL" ]; then
    fail=$((fail + 1))
    printf 'IDENTITY_AUDIT_FAIL: user.email=%s 与期望 %s 不符\n' "$eff_email" "$EXPECTED_EMAIL"
  fi

  if [ "$fail" -gt 0 ]; then
    printf 'IDENTITY_AUDIT_FAIL: 身份自检未通过，先排查再提交\n'
    exit 1
  fi
  if [ "$warn" -gt 0 ]; then
    printf 'IDENTITY_AUDIT_WARN: 共 %s 项发现，确认后再提交\n' "$warn"
    exit 1
  fi
  printf 'IDENTITY_AUDIT_OK\n'
  exit 0
}

cmd_history() {
  local total
  total=$(git -C "$REPO" log "${RANGE_ARGS[@]}" --format='%H' | wc -l | tr -d ' ') || \
    die "IDENTITY_AUDIT_GIT_ERROR" "无法枚举提交：${RANGE_ARGS[*]}"

  local limit_args=() shown="$total"
  if [ "$total" -gt "$MAX_COMMITS" ]; then
    limit_args=(-n "$MAX_COMMITS")
    shown="$MAX_COMMITS"
    printf 'IDENTITY_AUDIT_INFO: 提交数 %s 超过 --max-commits %s，仅审计每个列表前 %s 个\n' \
      "$total" "$MAX_COMMITS" "$MAX_COMMITS"
  fi
  printf '== Git 历史身份审计（range: %s，commits: %s/%s）==\n' \
    "${RANGE_ARGS[*]}" "$shown" "$total"

  local author_flagged=0 committer_flagged=0 trailer_flagged=0
  local block

  block=$(git -C "$REPO" log "${RANGE_ARGS[@]}" "${limit_args[@]}" --format='%an <%ae>' \
    | sort | uniq -c | sort -rn | count_table) || \
    die "IDENTITY_AUDIT_GIT_ERROR" "无法统计作者身份"
  print_identity_table "作者身份分布" <<<"$block" || author_flagged=$?

  printf '\n'
  block=$(git -C "$REPO" log "${RANGE_ARGS[@]}" "${limit_args[@]}" --format='%cn <%ce>' \
    | sort | uniq -c | sort -rn | count_table) || \
    die "IDENTITY_AUDIT_GIT_ERROR" "无法统计 committer 身份"
  print_identity_table "committer 身份分布" <<<"$block" || committer_flagged=$?

  printf '\n'
  # grep 无命中（全仓没有尾注）时退出码 1，属正常路径
  block=$(git -C "$REPO" log "${RANGE_ARGS[@]}" "${limit_args[@]}" --format='%b' \
    | grep -E '^Co-authored-by:' \
    | sed -E 's/^Co-authored-by:[[:space:]]*//' \
    | sort | uniq -c | sort -rn | count_table) || block=""
  print_identity_table "Co-authored-by 尾注分布" <<<"$block" || trailer_flagged=$?

  if [ $((author_flagged + committer_flagged + trailer_flagged)) -gt 0 ]; then
    printf '\nIDENTITY_AUDIT_FINDINGS: 可疑 author=%s committer=%s trailer=%s——下一步：whoami 看来源链定位写入层；改写历史作者须用户授权\n' \
      "$author_flagged" "$committer_flagged" "$trailer_flagged"
    exit 1
  fi
  printf '\nIDENTITY_AUDIT_OK: 未命中可疑模式\n'
  exit 0
}

# 服务端合并回执核验（2026-10-03，Task-012）：
#   committer = GitHub <noreply@github.com> 的提交 → gh 查本仓 MERGED PR 回执，
#   mergeCommit.oid 精确绑定判 ACCEPT / DENY_FORGED；gh 不可查一律 UNKNOWN
#   （fail-closed）。普通提交 SKIP。回执只能由本函数经 gh 认证通道自查，
#   不接受任何外部传入的回执数据（防伪造）。
cmd_receipt() {
  local oids=() oid full finds=0
  if [ "$RECEIPT_GAVE_RANGE" = "1" ]; then
    local range_oids
    range_oids=$(git -C "$REPO" rev-list "${RANGE_ARGS[0]}" 2>/dev/null) || \
      die "IDENTITY_AUDIT_USAGE" "无效提交范围：${RANGE_ARGS[0]}"
    while IFS= read -r oid; do
      [ -n "$oid" ] && oids+=("$oid")
    done <<<"$range_oids"
  else
    oids=("${RECEIPT_OIDS[@]}")
  fi
  [ "${#oids[@]}" -gt 0 ] || die "IDENTITY_AUDIT_USAGE" \
    "receipt 需要至少一个 <oid> 或 --range A..B"

  printf '== 服务端合并回执核验（receipt）==\n'
  printf 'repo=%s 模式=%s\n' "$REPO" "$([ "$RECEIPT_GAVE_RANGE" = "1" ] && printf 'range=%s' "${RANGE_ARGS[0]}" || printf '显式 OID ×%s' "${#oids[@]}")"

  # 解析为完整 40 位 hex（rev-parse 保证输出形态，杜绝 jq 内插注入面）
  local full_oids=()
  for oid in "${oids[@]}"; do
    full=$(git -C "$REPO" rev-parse --verify --quiet "$oid^{commit}") || \
      die "IDENTITY_AUDIT_USAGE" "无效提交引用：$oid"
    full_oids+=("$full")
  done

  # 先扫 committer：普通提交直接 SKIP 打印，只收集服务端提交（后者才触发 gh）
  local server_oids=() info ce cn
  for full in "${full_oids[@]}"; do
    info=$(git -C "$REPO" show -s --format='%cn|%ce' "$full")
    cn="${info%%|*}"; ce="${info##*|}"
    if [ "$cn" = "GitHub" ] && [ "$ce" = "noreply@github.com" ]; then
      server_oids+=("$full")
    else
      printf 'SKIP          %s  非服务端提交（committer=%s <%s>）；正常提交走 whoami/history\n' \
        "${full:0:12}" "$cn" "$ce"
    fi
  done

  if [ "${#server_oids[@]}" -eq 0 ]; then
    printf '\nIDENTITY_AUDIT_OK: 无服务端合成提交需要核验（%s 个全 SKIP）\n' "${#full_oids[@]}"
    exit 0
  fi

  # gh 定位本仓（无 gh/无 remote/未认证 → UNKNOWN fail-closed，绝不猜）
  local slug="" receipts="" reason=""
  if ! command -v gh >/dev/null 2>&1; then
    reason="gh 未安装"
  else
    slug=$(cd "$REPO" && gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null) || {
      slug=""; reason="gh 无法定位仓库（无 origin remote 或未认证）"
    }
  fi
  if [ -z "$slug" ]; then
    for full in "${server_oids[@]}"; do
      printf 'UNKNOWN       %s  回执不可查（%s）——fail-closed 不放行\n' "${full:0:12}" "$reason"
      finds=$((finds + 1))
    done
    printf '\nIDENTITY_AUDIT_FINDINGS: %s 个服务端提交无法核验回执；安装/认证 gh 后重跑，勿手工放行\n' "$finds"
    exit 1
  fi

  # 同时保留原始 PR 数量；先过滤 null mergeCommit 会丢失查询截断信息。
  # 数量达到上限时未命中只能 UNKNOWN；只有未达到上限才可判断无绑定。
  local raw_receipts="" header="" receipt_count="" query_ok=1
  raw_receipts=$(gh pr list -R "$slug" --state merged --limit "$MERGED_LIMIT" \
    --json number,mergeCommit,mergedAt,headRefOid \
    --jq '(["COUNT", length] | @tsv), (.[] | select(.mergeCommit != null) | "\(.mergeCommit.oid)\t#\(.number)\t\(.mergedAt)\t\(.headRefOid)")' \
    2>/dev/null) || query_ok=0
  header="${raw_receipts%%$'\n'*}"
  case "$header" in
    COUNT$'\t'*) receipt_count="${header#*$'\t'}" ;;
    *) query_ok=0 ;;
  esac
  case "$receipt_count" in ''|*[!0-9]*) query_ok=0 ;; esac
  if [ "$query_ok" = 1 ]; then
    if ! { [ "$receipt_count" -ge 0 ] 2>/dev/null && [ "$receipt_count" -le "$MERGED_LIMIT" ]; }; then
      query_ok=0
    fi
  fi
  receipts=$(printf '%s\n' "$raw_receipts" | sed '1d')
  if [ "$query_ok" = 0 ]; then
    for full in "${server_oids[@]}"; do
      printf 'UNKNOWN       %s  回执查询失败/格式异常（%s merged ≤%s）——fail-closed\n' \
        "${full:0:12}" "$slug" "$MERGED_LIMIT"
      finds=$((finds + 1))
    done
    printf '\nIDENTITY_AUDIT_FINDINGS: %s 个服务端提交回执不可核；检查网络/权限后重跑\n' "$finds"
    exit 1
  fi

  local accept=0 line mo pr merged_at head rest
  for full in "${server_oids[@]}"; do
    line=$(printf '%s\n' "$receipts" | awk -F'\t' -v oid="$full" '$1==oid' | head -1)
    if [ -n "$line" ]; then
      mo="${line%%$'\t'*}"; rest="${line#*$'\t'}"
      pr="${rest%%$'\t'*}"; rest="${rest#*$'\t'}"
      merged_at="${rest%%$'\t'*}"; head="${rest##*$'\t'}"
      printf 'ACCEPT        %s  %s mergedAt=%s head=%s\n' "${full:0:12}" "$pr" "$merged_at" "$head"
      accept=$((accept + 1))
    elif [ "$receipt_count" -ge "$MERGED_LIMIT" ]; then
      printf 'UNKNOWN       %s  未命中且查询达到上限（%s merged ≥%s）；证据不足，增大 --merged-limit 后重跑——fail-closed\n' \
        "${full:0:12}" "$slug" "$MERGED_LIMIT"
      finds=$((finds + 1))
    else
      printf 'DENY_FORGED  %s  服务端合成签名但无 %s 的 MERGED 回执绑定（伪造或外部仓库提交）\n' \
        "${full:0:12}" "$slug"
      finds=$((finds + 1))
    fi
  done

  if [ "$finds" -gt 0 ]; then
    printf '\nIDENTITY_AUDIT_FINDINGS: accept=%s deny/unknown=%s——未核验项不进入对账基线；UNKNOWN 是证据不足，不能判为伪造\n' \
      "$accept" "$finds"
    exit 1
  fi
  printf '\nIDENTITY_AUDIT_OK: %s 个服务端提交全部有 MERGED 回执绑定\n' "$accept"
  exit 0
}

case "$MODE" in
  whoami) cmd_whoami ;;
  history) cmd_history ;;
  receipt) cmd_receipt ;;
esac
