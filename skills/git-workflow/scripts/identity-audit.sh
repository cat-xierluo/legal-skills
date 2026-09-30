#!/usr/bin/env bash
# 只读审计：提交身份自检（whoami）与历史身份/Co-authored-by 尾注审计（history）。
#
# 2026-09-30 实录背景：private-skills 仓库级 .git/config 被写入
# Hermes(info-assistant) 身份——190 个提交作者被污染，且每次 PR squash 合并
# GitHub 自动把分支提交作者转成 Co-authored-by 尾注。既有门禁
# check-outgoing-identities.sh 在 push 时核验"传入的期望身份"，但期望值取自
# 被污染 config 时形同虚设，尾注也不在其检查范围。本脚本补齐两件事：
#   whoami  — commit 前自检：当前生效 user.name/email、来源链
#             （env → worktree → repo-local → global）、可疑身份模式、
#             仓库级/工作树级覆盖与 env 覆盖告警
#   history — 历史审计：全部分支（或指定 range）内 author/committer/
#             Co-authored-by 尾注身份分布，可疑项自动标注
# 只读：不修改任何 Git 配置、refs、工作树或提交。非 0 退出 = 有发现。

set -euo pipefail

REPO="."
MODE="whoami"
EXPECTED_NAME=""
EXPECTED_EMAIL=""
ALLOW_LOCAL_OVERRIDE=0
RANGE_ARGS=(--all)
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

子命令：
  whoami   提交前自检（默认）：当前生效身份 + 来源链 + 可疑模式 + 覆盖告警
  history  历史审计：author/committer/Co-authored-by 尾注身份分布，可疑项标注

退出码：0 = 无发现；1 = 有发现（WARN/FAIL）；2 = 用法或环境错误。
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
    whoami|history)
      MODE="$1"
      shift
      ;;
    --repo)
      [ "$#" -ge 2 ] || die "IDENTITY_AUDIT_USAGE" "--repo 缺少参数"
      REPO="$2"
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
    *)
      usage
      die "IDENTITY_AUDIT_USAGE" "未知参数：$1"
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

case "$MODE" in
  whoami) cmd_whoami ;;
  history) cmd_history ;;
esac
