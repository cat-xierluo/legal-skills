#!/bin/bash
# pm-closeout.sh — PR-first PM closeout with exact PR adoption and explicit results.
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SP="${PM_CLOSEOUT_SAFE_PUSH:-}"
GIT_NAME="${EXPECTED_GIT_NAME:-}"; GIT_EMAIL="${EXPECTED_GIT_EMAIL:-}"
WT=""; MAIN_WT=""; TITLE=""; BODY_FILE=""; VERIFY_BIN=""; KEEP_BRANCH=0; TMP_BODY=""
WORKER_BASE=""; WORKER_TIP=""; START_MAIN=""; STABLE_MAIN=""
MODE="${PM_CLOSEOUT_MODE:-local-after-pr}"; MAIN_PROTECTION="${PM_CLOSEOUT_MAIN_PROTECTION:-auto}"
TASK_ID="${PM_CLOSEOUT_TASK_ID:-}"; AGENT_ID="${PM_CLOSEOUT_AGENT_ID:-}"
AUTH_BRANCH_PUSH=""; AUTH_PR_CREATE=""; AUTH_MAIN_PUSH=""; AUTH_REMOTE_MERGE=""; AUTH_PR_CLOSE=""
AUTH_MAIN_CANDIDATE=""; AUTH_REMOTE_CANDIDATE=""
CANDIDATE_WT=""; CANDIDATE_PARENT=""; CANDIDATE_PATCH=""
VERIFY_ARGS=(); INTEGRATION_PATHS=()

redact_stream() {
  python3 -c '
import re,sys
value=sys.stdin.read()
value=re.sub(r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s]+@", r"\1***@", value)
value=re.sub(r"(?i)([?&](?:access_token|token|password|secret)=)[^&\s]+", r"\1***", value)
value=re.sub(r"(?i)\b[^\s/@:]+:[^\s@]+@([^\s/:]+)", r"***@\1", value)
sys.stdout.write(value.strip())'
}

run_redacted() {
  local operation=$1 err rc detail
  shift
  err=$(mktemp "${TMPDIR:-/tmp}/pm-closeout-error.XXXXXX")
  if "$@" 2>"$err"; then rc=0; else rc=$?; fi
  if [ "$rc" -ne 0 ]; then
    detail=$(redact_stream < "$err")
    echo "PM_CLOSEOUT_COMMAND_FAILED: operation=$operation exit=$rc detail=${detail:-none}" >&2
  fi
  rm -f -- "$err"
  return "$rc"
}

cleanup_temp() {
  if [ -n "$CANDIDATE_PARENT" ] && [ -d "$CANDIDATE_PARENT" ]; then
    rm -rf -- "$CANDIDATE_PARENT"
  fi
  if [ -n "$TMP_BODY" ] && [ -f "$TMP_BODY" ]; then
    rm -f -- "$TMP_BODY"
  fi
}
trap cleanup_temp EXIT

while [ $# -gt 0 ]; do case $1 in
  --worktree) WT="$2"; shift 2 ;;
  --main-worktree) MAIN_WT="$2"; shift 2 ;;
  --title) TITLE="$2"; shift 2 ;;
  --body-file) BODY_FILE="$2"; shift 2 ;;
  --safe-push-script) SP="$2"; shift 2 ;;
  --verify-cmd) VERIFY_BIN="$2"; shift 2 ;;
  --verify-arg) VERIFY_ARGS+=("$2"); shift 2 ;;
  --verify) echo "PM_CLOSEOUT_USAGE: --verify 字符串已停用；改用 --verify-cmd + --verify-arg，禁止 shell 字符串执行" >&2; exit 64 ;;
  --keep-branch) KEEP_BRANCH=1; shift ;;
  --mode) MODE="$2"; shift 2 ;;
  --main-protection) MAIN_PROTECTION="$2"; shift 2 ;;
  --task-id) TASK_ID="$2"; shift 2 ;;
  --agent-id) AGENT_ID="$2"; shift 2 ;;
  --integration-path) INTEGRATION_PATHS+=("$2"); shift 2 ;;
  --authorize-branch-push) AUTH_BRANCH_PUSH="$2"; shift 2 ;;
  --authorize-pr-create) AUTH_PR_CREATE="$2"; shift 2 ;;
  --authorize-main-push) AUTH_MAIN_PUSH="$2"; shift 2 ;;
  --authorize-remote-merge) AUTH_REMOTE_MERGE="$2"; shift 2 ;;
  --authorize-main-candidate) AUTH_MAIN_CANDIDATE="$2"; shift 2 ;;
  --authorize-remote-candidate) AUTH_REMOTE_CANDIDATE="$2"; shift 2 ;;
  --authorize-pr-close) AUTH_PR_CLOSE="$2"; shift 2 ;;
  *) echo "PM_CLOSEOUT_USAGE: 未知参数 $1" >&2; exit 64 ;;
esac; done
[ -n "$WT" ] && [ -n "$TITLE" ] || { echo "PM_CLOSEOUT_USAGE: 需要 --worktree 与 --title" >&2; exit 64; }
[ -n "$TASK_ID" ] && [ -n "$AGENT_ID" ] || { echo "PM_CLOSEOUT_USAGE: 需要 --task-id 与 --agent-id 绑定 PR 归属" >&2; exit 64; }
case "$MODE" in local-after-pr|remote-pr|validate-only) ;; *) echo "PM_CLOSEOUT_USAGE: 非法 --mode $MODE" >&2; exit 64 ;; esac
case "$MAIN_PROTECTION" in auto|protected) ;; *) echo "PM_CLOSEOUT_USAGE: --main-protection 仅接受 auto|protected；unprotected 必须由 GitHub branch metadata 正向证明" >&2; exit 64 ;; esac
[ "$MODE" = "validate-only" ] || [ "${#INTEGRATION_PATHS[@]}" -gt 0 ] || {
  echo "PM_CLOSEOUT_USAGE: local-after-pr/remote-pr 至少需要一个 --integration-path" >&2; exit 64
}
if [ "$MODE" != "validate-only" ]; then
  [ -n "$SP" ] && [ -f "$SP" ] && [ ! -L "$SP" ] || {
    echo "PM_CLOSEOUT_NO_SAFE_PUSH: 需要 --safe-push-script 指向已审查的 git-workflow safe-push.sh（或设置 PM_CLOSEOUT_SAFE_PUSH）" >&2
    exit 7
  }
  SP="$(cd "$(dirname "$SP")" && pwd -P)/$(basename "$SP")"
fi
[ -n "$VERIFY_BIN" ] || {
  echo "PM_CLOSEOUT_VERIFY_REQUIRED: 需要 --verify-cmd；多步门禁请封装为仓库内可执行脚本" >&2
  exit 64
}
for dependency in git jq gh python3; do
  command -v "$dependency" >/dev/null 2>&1 || {
    echo "PM_CLOSEOUT_DEPENDENCY_MISSING: $dependency" >&2
    exit 64
  }
done
cd "$WT"
BR=$(git branch --show-current)
[ -n "$BR" ] || { echo "PM_CLOSEOUT_DETACHED_HEAD: 必须在具名分支收口" >&2; exit 2; }
if [ "$MODE" != "validate-only" ]; then
  [ -n "$GIT_NAME" ] || GIT_NAME=$(git config user.name || true)
  [ -n "$GIT_EMAIL" ] || GIT_EMAIL=$(git config user.email || true)
  [ -n "$GIT_NAME" ] && [ -n "$GIT_EMAIL" ] || {
    echo "PM_CLOSEOUT_GIT_IDENTITY_REQUIRED: 设置仓库 git user.name/user.email 或 EXPECTED_GIT_NAME/EXPECTED_GIT_EMAIL" >&2
    exit 7
  }
fi
echo "PM_CLOSEOUT_BRANCH: $BR"

# 1) 未提交改动检查(fail-closed)
if [ -n "$(git status --porcelain)" ]; then echo "PM_CLOSEOUT_DIRTY: 工作树有未提交改动,先处理" >&2; exit 2; fi

# 2) 冻结 worker 贡献范围。PR 先行，禁止在 worker 分支 merge main。
run_redacted git-fetch-worker git fetch origin --quiet || exit $?
WORKER_TIP=$(git rev-parse --verify 'HEAD^{commit}')
START_MAIN=$(git rev-parse --verify 'origin/main^{commit}')
WORKER_BASE=$(git merge-base "$WORKER_TIP" "$START_MAIN")
if [ -z "$WORKER_BASE" ] || ! git merge-base --is-ancestor "$WORKER_BASE" "$WORKER_TIP"; then
  echo "PM_CLOSEOUT_WORKER_RANGE_INVALID: base=$WORKER_BASE tip=$WORKER_TIP main=$START_MAIN" >&2
  exit 3
fi
echo "PM_CLOSEOUT_WORKER_RANGE: base=$WORKER_BASE tip=$WORKER_TIP start_main=$START_MAIN"

# 路径声明使用仓库相对路径，拒绝 absolute/../ 和现有 symlink 组件逃逸。
validate_integration_path() {
  python3 - "$1" "$2" <<'PY'
import os, pathlib, sys
root=os.path.realpath(sys.argv[1]); value=sys.argv[2]
parts=pathlib.PurePosixPath(value).parts
if not value or value.startswith(':') or os.path.isabs(value) or any(p in ('', '.', '..') for p in parts): raise SystemExit(2)
candidate=os.path.abspath(os.path.join(root, *parts))
if os.path.commonpath([root, candidate]) != root: raise SystemExit(2)
probe=root
for part in parts:
    probe=os.path.join(probe, part)
    if os.path.lexists(probe) and os.path.islink(probe): raise SystemExit(3)
print('/'.join(parts))
PY
}
for i in "${!INTEGRATION_PATHS[@]}"; do
  normalized=$(validate_integration_path "$WT" "${INTEGRATION_PATHS[$i]}") || {
    echo "PM_CLOSEOUT_INTEGRATION_PATH_INVALID: ${INTEGRATION_PATHS[$i]}" >&2; exit 2
  }
  INTEGRATION_PATHS[i]="$normalized"
done
if [ "${#INTEGRATION_PATHS[@]}" -gt 0 ]; then
  while IFS= read -r -d '' changed; do
    in_scope=0
    for scope in "${INTEGRATION_PATHS[@]}"; do
      case "$changed" in "$scope"|"$scope"/*) in_scope=1; break ;; esac
    done
    [ "$in_scope" -eq 1 ] || { echo "PM_CLOSEOUT_SCOPE_VIOLATION: $changed" >&2; exit 3; }
  done < <(git diff --name-only --no-renames -z "$WORKER_BASE" "$WORKER_TIP")
fi

# 3) worker 门禁：数组执行，且不得改变工作树、HEAD 或分支。
verify_head=$WORKER_TIP; verify_branch=$BR
echo "PM_CLOSEOUT_VERIFY: worker $VERIFY_BIN (${#VERIFY_ARGS[@]} args)"
if ! "$VERIFY_BIN" "${VERIFY_ARGS[@]}"; then echo "PM_CLOSEOUT_VERIFY_FAILED" >&2; exit 4; fi
[ -z "$(git status --porcelain)" ] || { echo "PM_CLOSEOUT_VERIFY_DIRTY" >&2; exit 4; }
after_verify_head=$(git rev-parse --verify 'HEAD^{commit}')
after_verify_branch=$(git branch --show-current)
if [ "$after_verify_head" != "$verify_head" ] || [ "$after_verify_branch" != "$verify_branch" ]; then
  echo "PM_CLOSEOUT_VERIFY_GIT_STATE_CHANGED: before=$verify_head/$verify_branch after=$after_verify_head/$after_verify_branch" >&2; exit 4
fi

# 4) mutation 前只读预审：唯一 exact 接管，歧义拒绝，zero 才允许进入 push/create。
audit_prs() {
  python3 "$SKILL_DIR/scripts/pr-audit.py" --repo "$WT" --base-ref main \
    --head-ref "$BR" --head-sha "$WORKER_TIP" --task-id "$TASK_ID" --agent-id "$AGENT_ID"
}
AUDIT_JSON=$(audit_prs) || exit $?
AUDIT_DECISION=$(printf '%s' "$AUDIT_JSON" | jq -er '.decision') || { echo "PM_CLOSEOUT_PR_AUDIT_INVALID" >&2; exit 5; }
REMOTE=$(printf '%s' "$AUDIT_JSON" | jq -er '.repository.remote') || { echo "PM_CLOSEOUT_REMOTE_IDENTITY_INVALID" >&2; exit 5; }
echo "PM_CLOSEOUT_PR_AUDIT: decision=$AUDIT_DECISION exact=$(printf '%s' "$AUDIT_JSON" | jq -r '.counts.exact') suspected=$(printf '%s' "$AUDIT_JSON" | jq -r '.counts.suspected') unrelated=$(printf '%s' "$AUDIT_JSON" | jq -r '.counts.unrelated')"
PR_N=""; PR_URL=""

expected_authority() {
  local operation=$1 pr_number=${2:-none}
  printf 'operation=%s;repo=%s;pr=%s;head=%s;sha=%s' "$operation" "$REMOTE" "$pr_number" "$BR" "$WORKER_TIP"
}
require_authority() {
  local actual=$1 operation=$2 pr_number=${3:-none} expected
  expected=$(expected_authority "$operation" "$pr_number")
  [ "$actual" = "$expected" ] || {
    echo "PM_CLOSEOUT_AUTHORIZATION_REQUIRED: operation=$operation expected=$expected" >&2
    return 1
  }
}
require_candidate_authority() {
  local actual=$1 operation=$2 expected
  expected=$(printf 'operation=%s;repo=%s;pr=%s;head=%s;sha=%s;base=%s;candidate=%s;tree=%s' \
    "$operation" "$REMOTE" "$PR_N" "$BR" "$WORKER_TIP" "$STABLE_MAIN" "$CANDIDATE_SHA" "$CANDIDATE_TREE")
  [ "$actual" = "$expected" ] || {
    echo "PM_CLOSEOUT_CANDIDATE_AUTHORIZATION_REQUIRED: operation=$operation expected=$expected" >&2
    return 1
  }
}
finish_validate_only() {
  local reason=$1 pr_number=${2:-${PR_N:-none}}
  echo "PM_CLOSEOUT_RESULT: VALIDATE_ONLY pr=$pr_number head=$WORKER_TIP reason=$reason"
  [ "$MODE" = "validate-only" ] && exit 0
  exit 8
}

if [ "$AUDIT_DECISION" = "adopt" ]; then
  PR_N=$(printf '%s' "$AUDIT_JSON" | jq -er '.exact[0].number | tostring')
  PR_URL=$(printf '%s' "$AUDIT_JSON" | jq -er '.exact[0].url')
  echo "PM_CLOSEOUT_PR_ADOPTED: #$PR_N ($PR_URL)"
elif [ "$AUDIT_DECISION" = "ambiguous" ]; then
  echo "PM_CLOSEOUT_PR_AMBIGUOUS: exact/suspected candidates require PM review; no PR created" >&2
  exit 5
else
  if [ "$MODE" = "validate-only" ]; then
    echo "PM_CLOSEOUT_MODE: requested=validate-only effective=validate-only protection=not-queried reason=no-existing-pr"
    echo "PM_CLOSEOUT_RESULT: VALIDATE_ONLY pr=none head=$WORKER_TIP reason=no-existing-pr"
    exit 0
  fi
  require_authority "$AUTH_BRANCH_PUSH" branch-push || exit 8
  require_authority "$AUTH_PR_CREATE" pr-create || exit 8

  if [ -n "$BODY_FILE" ]; then
    [ -f "$BODY_FILE" ] && [ ! -L "$BODY_FILE" ] || {
      echo "PM_CLOSEOUT_BODY_FILE_INVALID: $BODY_FILE" >&2; exit 64
    }
    if LC_ALL=C grep -Eqi '^(Task|Agent):[[:space:]]*' "$BODY_FILE"; then
      echo "PM_CLOSEOUT_BODY_TRAILER_RESERVED: body-file 不得自带 Task:/Agent:，由收口脚本唯一追加" >&2
      exit 64
    fi
  fi

  run_redacted safe-push-branch "$SP" --repo . --base origin/main --branch "$BR" \
    --expected-name "$GIT_NAME" --expected-email "$GIT_EMAIL" >/dev/null || exit $?
  if [ "$(git rev-parse 'HEAD^{commit}')" != "$WORKER_TIP" ] || \
     [ "$(git branch --show-current)" != "$BR" ] || [ -n "$(git status --porcelain)" ]; then
    echo "PM_CLOSEOUT_SAFE_PUSH_GIT_STATE_CHANGED: expected=$WORKER_TIP/$BR" >&2; exit 4
  fi
  echo "PM_CLOSEOUT_PUSHED: $BR"

  # Push 与 create 之间也可能有 worker/其他 PM 自建 PR；再次审计后才决定 create。
  POST_PUSH_AUDIT=$(audit_prs) || exit $?
  POST_PUSH_DECISION=$(printf '%s' "$POST_PUSH_AUDIT" | jq -er '.decision') || { echo "PM_CLOSEOUT_PR_AUDIT_INVALID" >&2; exit 5; }
  if [ "$POST_PUSH_DECISION" = "adopt" ]; then
    PR_N=$(printf '%s' "$POST_PUSH_AUDIT" | jq -er '.exact[0].number | tostring')
    PR_URL=$(printf '%s' "$POST_PUSH_AUDIT" | jq -er '.exact[0].url')
    echo "PM_CLOSEOUT_PR_ADOPTED_AFTER_PUSH_RACE: #$PR_N ($PR_URL)"
  elif [ "$POST_PUSH_DECISION" = "ambiguous" ]; then
    echo "PM_CLOSEOUT_PR_AMBIGUOUS_AFTER_PUSH: no PR created" >&2
    exit 5
  fi

  if [ -z "$PR_N" ]; then
    TMP_BODY=$(mktemp "${TMPDIR:-/tmp}/pm-closeout-body.XXXXXX")
    if [ -n "$BODY_FILE" ]; then
      command cat -- "$BODY_FILE" > "$TMP_BODY"
      printf '\n\nTask: %s\nAgent: %s\n' "$TASK_ID" "$AGENT_ID" >> "$TMP_BODY"
    else
      printf '%s\n\nTask: %s\nAgent: %s\n\n%s\n' "$TITLE" "$TASK_ID" "$AGENT_ID" \
        '- 管道自动收口（未提供 body-file）：验证证据见分支提交与门禁日志。' > "$TMP_BODY"
    fi
    BODY_FILE="$TMP_BODY"
  CREATE_ARGS=(--repo "$REMOTE" --base main --head "$BR" --title "$TITLE" --body-file "$BODY_FILE")
  set +e
  CREATE_OUT=$(gh pr create "${CREATE_ARGS[@]}" 2>&1)
  create_rc=$?
  set -e
  receipt_pr=""
  if [ "$create_rc" -eq 0 ]; then
    PR_URL=$(printf '%s\n' "$CREATE_OUT" | tail -1)
    PR_N=$(printf '%s\n' "$PR_URL" | sed -nE 's#^.*/pull/([0-9]+).*$#\1#p')
    receipt_pr=$PR_N
  fi
  # create 成败都只重审一次。失败可能是并发创建；只有唯一 exact 才接管。
  set +e
  POST_CREATE_AUDIT=$(audit_prs)
  post_create_audit_rc=$?
  set -e
  if [ "$post_create_audit_rc" -ne 0 ]; then
    echo "PM_CLOSEOUT_RESULT: PR_CREATE_OUTCOME_UNKNOWN head=$WORKER_TIP reason=post-create-audit-failed" >&2
    exit 9
  fi
  POST_CREATE_DECISION=$(printf '%s' "$POST_CREATE_AUDIT" | jq -er '.decision') || {
    echo "PM_CLOSEOUT_RESULT: PR_CREATE_OUTCOME_UNKNOWN head=$WORKER_TIP reason=post-create-audit-invalid" >&2
    exit 9
  }
  if [ "$POST_CREATE_DECISION" != "adopt" ]; then
    if [ "$create_rc" -ne 0 ]; then
      create_detail=$(printf '%s' "$CREATE_OUT" | redact_stream)
      echo "PM_CLOSEOUT_RESULT: PR_CREATE_OUTCOME_UNKNOWN head=$WORKER_TIP audit=$POST_CREATE_DECISION detail=${create_detail:-none}" >&2
    else
      echo "PM_CLOSEOUT_RESULT: PR_CREATED_REVIEW_REQUIRED pr=$PR_N head=$WORKER_TIP audit=$POST_CREATE_DECISION" >&2
    fi
    exit 9
  fi
  adopted_n=$(printf '%s' "$POST_CREATE_AUDIT" | jq -er '.exact[0].number | tostring')
  adopted_url=$(printf '%s' "$POST_CREATE_AUDIT" | jq -er '.exact[0].url')
  if [ "$create_rc" -eq 0 ] && [ -n "$receipt_pr" ] && [ "$adopted_n" != "$receipt_pr" ]; then
    echo "PM_CLOSEOUT_RESULT: PR_CREATED_REVIEW_REQUIRED pr=$receipt_pr head=$WORKER_TIP audit_pr=$adopted_n reason=receipt-audit-mismatch" >&2
    exit 9
  fi
  PR_N=$adopted_n; PR_URL=$adopted_url
  if [ "$create_rc" -eq 0 ]; then echo "PM_CLOSEOUT_PR_CREATED: #$PR_N ($PR_URL)"
  else echo "PM_CLOSEOUT_PR_ADOPTED_AFTER_CREATE_RACE: #$PR_N ($PR_URL)"; fi
  fi
fi
echo "PM_CLOSEOUT_PR: #$PR_N ($PR_URL)"

# 6) 冻结 PR base/head OID、真实 diff、checks/review canonical digest。
pr_snapshot() {
  gh pr view "$PR_N" --repo "$REMOTE" \
    --json number,url,state,baseRefName,baseRefOid,headRefName,headRefOid,statusCheckRollup,reviewDecision,mergeable,mergedAt,mergeCommit
}
pr_diff_digest() {
  local diff_file rc=0
  diff_file=$(mktemp "${TMPDIR:-/tmp}/pm-closeout-pr-diff.XXXXXX")
  run_redacted pr-diff gh pr diff "$PR_N" --repo "$REMOTE" > "$diff_file" || rc=$?
  if [ "$rc" -ne 0 ]; then
    rm -f -- "$diff_file"
    return "$rc"
  fi
  python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())' < "$diff_file" || rc=$?
  rm -f -- "$diff_file"
  return "$rc"
}
canonical_gate_digest() {
  python3 -c '
import hashlib,json,sys
d=json.load(sys.stdin); checks=d.get("statusCheckRollup")
if not isinstance(checks,list): raise SystemExit(2)
checks=sorted(checks,key=lambda x:json.dumps(x,sort_keys=True,separators=(",",":")))
raw=json.dumps({"checks":checks,"reviewDecision":d.get("reviewDecision")},sort_keys=True,separators=(",",":")).encode()
print(hashlib.sha256(raw).hexdigest())'
}
snapshot_ready() {
  local s=$1
  printf '%s' "$s" | python3 -c '
import json,sys
expected=sys.argv[1]; expected_branch=sys.argv[2]
try: d=json.load(sys.stdin)
except Exception: raise SystemExit(2)
required=("state","baseRefName","baseRefOid","headRefName","headRefOid","statusCheckRollup")
if any(k not in d for k in required): raise SystemExit(2)
if d["state"]!="OPEN" or d["baseRefName"]!="main" or d["headRefName"]!=expected_branch or d["headRefOid"]!=expected: raise SystemExit(3)
if not isinstance(d["baseRefOid"],str) or len(d["baseRefOid"])!=40: raise SystemExit(2)
if not isinstance(d["statusCheckRollup"],list): raise SystemExit(2)
good={"SUCCESS","NEUTRAL","SKIPPED"}
for row in d["statusCheckRollup"]:
    if not isinstance(row,dict): raise SystemExit(2)
    status=str(row.get("status") or "").upper()
    conclusion=str(row.get("conclusion") or row.get("state") or "").upper()
    if status and status!="COMPLETED": raise SystemExit(1)
    if conclusion not in good: raise SystemExit(1)
if str(d.get("reviewDecision") or "") in {"CHANGES_REQUESTED","REVIEW_REQUIRED"}: raise SystemExit(1)
' "$WORKER_TIP" "$BR"
}

SNAPSHOT=$(pr_snapshot 2>/dev/null || true)
if [ -z "$SNAPSHOT" ] || ! snapshot_ready "$SNAPSHOT"; then
  finish_validate_only pr-snapshot-or-checks-not-ready
fi
FROZEN_BASE_OID=$(printf '%s' "$SNAPSHOT" | jq -er '.baseRefOid')
FROZEN_HEAD_OID=$(printf '%s' "$SNAPSHOT" | jq -er '.headRefOid')
[ "$FROZEN_BASE_OID" = "$(git rev-parse 'origin/main^{commit}')" ] || {
  finish_validate_only pr-base-not-fresh
}
FROZEN_DIFF=$(pr_diff_digest) || finish_validate_only pr-diff-unavailable
FROZEN_GATE=$(printf '%s' "$SNAPSHOT" | canonical_gate_digest) || finish_validate_only checks-review-unknown
echo "PM_CLOSEOUT_REVIEW_FROZEN: pr=$PR_N base=$FROZEN_BASE_OID head=$FROZEN_HEAD_OID diff=$FROZEN_DIFF checks_review=$FROZEN_GATE"

snapshot_still_frozen() {
  local current diff gate
  current=$(pr_snapshot 2>/dev/null) || return 1
  snapshot_ready "$current" || return 1
  [ "$(printf '%s' "$current" | jq -r '.baseRefOid')" = "$FROZEN_BASE_OID" ] || return 1
  [ "$(printf '%s' "$current" | jq -r '.headRefOid')" = "$FROZEN_HEAD_OID" ] || return 1
  diff=$(pr_diff_digest) || return 1
  gate=$(printf '%s' "$current" | canonical_gate_digest) || return 1
  [ "$diff" = "$FROZEN_DIFF" ] && [ "$gate" = "$FROZEN_GATE" ]
}
audit_still_unique() {
  local current decision number
  current=$(audit_prs) || return 1
  decision=$(printf '%s' "$current" | jq -er '.decision') || return 1
  [ "$decision" = "adopt" ] || return 1
  number=$(printf '%s' "$current" | jq -er '.exact[0].number | tostring') || return 1
  [ "$number" = "$PR_N" ]
}

# 7) 保护规则与操作授权分流。branch metadata 的 protected 布尔值同时
# 覆盖 classic branch protection 与 rulesets；未知或畸形结果失败关闭。
read_protection_state() {
  local out rc
  set +e
  out=$(gh api --hostname "$REMOTE_HOST" "repos/$REMOTE_REPO/branches/main" 2>/dev/null)
  rc=$?
  set -e
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | jq -e '.protected | type == "boolean"' >/dev/null 2>&1; then
    if [ "$(printf '%s' "$out" | jq -r '.protected')" = "true" ]; then printf 'protected\n'
    else printf 'unprotected\n'; fi
  else
    printf 'unknown\n'
  fi
}
read_merge_queue_state() {
  local out rc
  set +e
  out=$(gh api --hostname "$REMOTE_HOST" "repos/$REMOTE_REPO/rules/branches/main" 2>/dev/null)
  rc=$?
  set -e
  if [ "$rc" -ne 0 ] || ! printf '%s' "$out" | jq -e 'type == "array"' >/dev/null 2>&1; then
    printf 'unknown\n'
  elif printf '%s' "$out" | jq -e 'any(.[]; .type == "merge_queue")' >/dev/null 2>&1; then
    printf 'present\n'
  else
    printf 'absent\n'
  fi
}

PROTECTION_STATE="$MAIN_PROTECTION"
REMOTE_HOST=${REMOTE%%/*}
REMOTE_REPO=${REMOTE#*/}
if [ "$MAIN_PROTECTION" = "auto" ]; then
  PROTECTION_STATE=$(read_protection_state)
fi
REQUESTED_MODE="$MODE"; EFFECTIVE_MODE="$MODE"; MODE_REASON="requested"
if [ "$MODE" = "local-after-pr" ] && [ "$PROTECTION_STATE" = "protected" ]; then
  EFFECTIVE_MODE="remote-pr"; MODE_REASON="protected-main"
elif [ "$MODE" = "local-after-pr" ] && [ "$PROTECTION_STATE" = "unknown" ]; then
  EFFECTIVE_MODE="validate-only"; MODE_REASON="main-protection-unknown"
fi
if [ "$EFFECTIVE_MODE" = "local-after-pr" ] && ! require_authority "$AUTH_MAIN_PUSH" main-push "$PR_N"; then
  EFFECTIVE_MODE="validate-only"; MODE_REASON="main-push-authorization-missing-or-mismatched"
elif [ "$EFFECTIVE_MODE" = "remote-pr" ] && ! require_authority "$AUTH_REMOTE_MERGE" remote-merge "$PR_N"; then
  EFFECTIVE_MODE="validate-only"; MODE_REASON="remote-merge-authorization-missing-or-mismatched"
fi
echo "PM_CLOSEOUT_MODE: requested=$REQUESTED_MODE effective=$EFFECTIVE_MODE protection=$PROTECTION_STATE reason=$MODE_REASON"
if [ "$EFFECTIVE_MODE" = "validate-only" ]; then
  echo "PM_CLOSEOUT_RESULT: VALIDATE_ONLY pr=$PR_N head=$WORKER_TIP reason=$MODE_REASON"
  [ "$REQUESTED_MODE" = "validate-only" ] && exit 0
  exit 8
fi

canonical_common_dir() {
  local repo=$1 raw top
  raw=$(git -C "$repo" rev-parse --git-common-dir 2>/dev/null) || return 1
  top=$(git -C "$repo" rev-parse --show-toplevel 2>/dev/null) || return 1
  case "$raw" in /*) ;; *) raw="$top/$raw" ;; esac
  (cd "$raw" && pwd -P)
}
NEED_MAIN_WT=0
[ "$EFFECTIVE_MODE" = "local-after-pr" ] && NEED_MAIN_WT=1
if [ "$NEED_MAIN_WT" -eq 1 ] && [ -z "$MAIN_WT" ]; then
  main_worktree_count=0
  while IFS= read -r line; do
    case "$line" in
      "worktree "*) candidate_path=${line#worktree } ;;
      "branch refs/heads/main") MAIN_WT=${candidate_path:-}; main_worktree_count=$((main_worktree_count + 1)) ;;
    esac
  done < <(git worktree list --porcelain)
  if [ "$main_worktree_count" -ne 1 ]; then
    echo "PM_CLOSEOUT_RESULT: VALIDATE_ONLY pr=$PR_N reason=main-worktree-not-unique"; exit 8
  fi
fi
if [ "$NEED_MAIN_WT" -eq 1 ]; then
  MAIN_WT=$(cd "$MAIN_WT" 2>/dev/null && pwd -P || true)
  WORKER_COMMON=$(canonical_common_dir "$WT" || true)
  MAIN_COMMON=$(canonical_common_dir "$MAIN_WT" || true)
  WORKER_REMOTE_URL=$(git -C "$WT" remote get-url origin 2>/dev/null || true)
  MAIN_REMOTE_URL=$(git -C "$MAIN_WT" remote get-url origin 2>/dev/null || true)
  if [ -z "$MAIN_WT" ] || [ -z "$WORKER_COMMON" ] || [ "$WORKER_COMMON" != "$MAIN_COMMON" ] || [ "$WORKER_REMOTE_URL" != "$MAIN_REMOTE_URL" ]; then
    echo "PM_CLOSEOUT_RESULT: VALIDATE_ONLY pr=$PR_N reason=main-worktree-wrong-repository"; exit 8
  fi
  if [ "$(git -C "$MAIN_WT" branch --show-current 2>/dev/null || true)" != "main" ]; then
    echo "PM_CLOSEOUT_RESULT: VALIDATE_ONLY pr=$PR_N reason=main-worktree-wrong-branch"; exit 8
  fi
  if [ -n "$(git -C "$MAIN_WT" status --porcelain)" ]; then
    echo "PM_CLOSEOUT_RESULT: VALIDATE_ONLY pr=$PR_N reason=main-worktree-dirty"; exit 8
  fi
  main_git_dir=$(git -C "$MAIN_WT" rev-parse --absolute-git-dir 2>/dev/null || true)
  # REBASE_HEAD may persist after a completed/conflicted rebase; active rebases
  # are identified by rebase-merge/rebase-apply below.
  for operation_marker in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD BISECT_START; do
    if [ -n "$main_git_dir" ] && [ -e "$main_git_dir/$operation_marker" ]; then
      echo "PM_CLOSEOUT_RESULT: VALIDATE_ONLY pr=$PR_N reason=main-worktree-operation-in-progress-$operation_marker"; exit 8
    fi
  done
  for operation_dir in rebase-merge rebase-apply sequencer; do
    if [ -n "$main_git_dir" ] && [ -e "$main_git_dir/$operation_dir" ]; then
      echo "PM_CLOSEOUT_RESULT: VALIDATE_ONLY pr=$PR_N reason=main-worktree-operation-in-progress-$operation_dir"; exit 8
    fi
  done
  for scope in "${INTEGRATION_PATHS[@]}"; do
    validate_integration_path "$MAIN_WT" "$scope" >/dev/null || {
      echo "PM_CLOSEOUT_RESULT: VALIDATE_ONLY pr=$PR_N reason=integration-path-main-symlink"; exit 8
    }
  done
fi

reset_candidate() {
  if [ -n "$CANDIDATE_PARENT" ] && [ -d "$CANDIDATE_PARENT" ]; then
    rm -rf -- "$CANDIDATE_PARENT"
  fi
  CANDIDATE_WT=""; CANDIDATE_PARENT=""; CANDIDATE_PATCH=""
}

# 8) 从 fresh origin/main 建隔离 main clone；三方应用冻结 patch，冲突即失败关闭。
WORKER_REMOTE_URL=$(git remote get-url origin)
CANDIDATE_STABLE=0
for candidate_round in 1 2 3; do
  run_redacted git-fetch-candidate-base git fetch origin --quiet || exit $?
  candidate_main=$(git rev-parse --verify 'origin/main^{commit}')
  CANDIDATE_PARENT=$(mktemp -d "${TMPDIR:-/tmp}/pm-closeout-candidate.XXXXXX")
  CANDIDATE_WT="$CANDIDATE_PARENT/repository"
  CANDIDATE_PATCH="$CANDIDATE_PARENT/worker.patch"
  run_redacted git-clone-candidate git clone --quiet --no-checkout "$WT" "$CANDIDATE_WT" || exit $?
  git -C "$CANDIDATE_WT" remote set-url origin "$WORKER_REMOTE_URL"
  run_redacted git-fetch-candidate git -C "$CANDIDATE_WT" fetch --quiet origin \
    'main:refs/remotes/origin/main' || exit $?
  git -C "$CANDIDATE_WT" checkout -q -B main "$candidate_main"
  git --literal-pathspecs diff --binary --full-index --no-renames \
    --output="$CANDIDATE_PATCH" "$WORKER_BASE" "$WORKER_TIP" -- "${INTEGRATION_PATHS[@]}"
  if ! git -C "$CANDIDATE_WT" apply --3way --index "$CANDIDATE_PATCH"; then
    finish_validate_only integration-conflict
  fi
  if git -C "$CANDIDATE_WT" diff --cached --quiet; then
    finish_validate_only empty-integration-candidate
  fi
  CANDIDATE_DATE=$(git show -s --format=%aI "$WORKER_TIP")
  GIT_AUTHOR_DATE="$CANDIDATE_DATE" GIT_COMMITTER_DATE="$CANDIDATE_DATE" \
    git -C "$CANDIDATE_WT" -c user.name="$GIT_NAME" -c user.email="$GIT_EMAIL" \
      -c user.useConfigOnly=true -c commit.gpgSign=false -c commit.cleanup=verbatim \
      -c core.hooksPath=/dev/null \
      commit -q -m "$TITLE (#$PR_N)"
  CANDIDATE_SHA=$(git -C "$CANDIDATE_WT" rev-parse 'HEAD^{commit}')
  CANDIDATE_TREE=$(git -C "$CANDIDATE_WT" rev-parse 'HEAD^{tree}')
  [ "$(git -C "$CANDIDATE_WT" rev-parse 'HEAD^1')" = "$candidate_main" ] || {
    echo "PM_CLOSEOUT_CANDIDATE_PARENT_MISMATCH" >&2; exit 4
  }
  echo "PM_CLOSEOUT_VERIFY: candidate round=$candidate_round $VERIFY_BIN (${#VERIFY_ARGS[@]} args)"
  if ! (cd "$CANDIDATE_WT" && "$VERIFY_BIN" "${VERIFY_ARGS[@]}"); then echo "PM_CLOSEOUT_VERIFY_FAILED: candidate" >&2; exit 4; fi
  [ -z "$(git -C "$CANDIDATE_WT" status --porcelain)" ] && [ "$(git -C "$CANDIDATE_WT" rev-parse HEAD)" = "$CANDIDATE_SHA" ] || {
    echo "PM_CLOSEOUT_VERIFY_GIT_STATE_CHANGED: candidate" >&2; exit 4
  }
  run_redacted git-fetch-after-candidate git fetch origin --quiet || exit $?
  observed_main=$(git rev-parse --verify 'origin/main^{commit}')
  if [ "$observed_main" != "$candidate_main" ]; then
    echo "PM_CLOSEOUT_MAIN_ADVANCED: round=$candidate_round before=$candidate_main after=$observed_main"
    reset_candidate
    # main movement changes the PR base and often its diff.  Re-read all review
    # facts before rebuilding; unknown/pending facts stop rather than inherit.
    REFRESHED=$(pr_snapshot 2>/dev/null || true)
    if [ -z "$REFRESHED" ] || ! snapshot_ready "$REFRESHED"; then
      finish_validate_only main-moved-pr-revalidation-not-ready
    fi
    FROZEN_BASE_OID=$(printf '%s' "$REFRESHED" | jq -er '.baseRefOid')
    FROZEN_HEAD_OID=$(printf '%s' "$REFRESHED" | jq -er '.headRefOid')
    [ "$FROZEN_BASE_OID" = "$observed_main" ] || {
      finish_validate_only main-moved-pr-base-not-fresh
    }
    FROZEN_DIFF=$(pr_diff_digest) || finish_validate_only main-moved-pr-diff-unavailable
    FROZEN_GATE=$(printf '%s' "$REFRESHED" | canonical_gate_digest) || {
      finish_validate_only main-moved-checks-review-unknown
    }
    echo "PM_CLOSEOUT_REVIEW_REFROZEN: pr=$PR_N base=$FROZEN_BASE_OID head=$FROZEN_HEAD_OID diff=$FROZEN_DIFF checks_review=$FROZEN_GATE"
    continue
  fi
  if ! snapshot_still_frozen; then echo "PM_CLOSEOUT_REVIEW_DRIFT: head/base/diff/checks changed" >&2; exit 5; fi
  STABLE_MAIN=$candidate_main; CANDIDATE_STABLE=1; break
done
[ "$CANDIDATE_STABLE" -eq 1 ] || { echo "PM_CLOSEOUT_MAIN_MOVED_TOO_MANY_TIMES: max_rounds=3" >&2; exit 3; }
echo "PM_CLOSEOUT_CANDIDATE_VERIFIED: pr=$PR_N base=$STABLE_MAIN commit=$CANDIDATE_SHA"

# 外部 mutation 使用第二阶段授权，绑定最终验证过的 base、candidate commit 与 tree。
# main 前移后旧回执必然失效，调用方必须基于新 challenge 明确重授权。
if [ "$EFFECTIVE_MODE" = "remote-pr" ]; then
  require_candidate_authority "$AUTH_REMOTE_CANDIDATE" remote-merge-candidate || \
    finish_validate_only remote-candidate-authorization-missing-or-mismatched
else
  require_candidate_authority "$AUTH_MAIN_CANDIDATE" main-push-candidate || \
    finish_validate_only main-candidate-authorization-missing-or-mismatched
fi

# 9a) protected/remote authority: final unique+snapshot gate, head-locked GitHub merge, three-field confirmation.
if [ "$EFFECTIVE_MODE" = "remote-pr" ]; then
  run_redacted git-fetch-before-remote-merge git fetch origin --quiet || exit $?
  [ "$(git rev-parse 'origin/main^{commit}')" = "$STABLE_MAIN" ] || finish_validate_only origin-main-drift-before-remote-merge
  audit_still_unique || { echo "PM_CLOSEOUT_PR_SET_DRIFT: before remote merge" >&2; exit 5; }
  snapshot_still_frozen || { echo "PM_CLOSEOUT_REVIEW_DRIFT: before remote merge" >&2; exit 5; }
  MERGE_QUEUE_STATE=$(read_merge_queue_state)
  [ "$MERGE_QUEUE_STATE" = "absent" ] || {
    finish_validate_only "merge-queue-$MERGE_QUEUE_STATE-task-070-required"
  }
  set +e
  MERGE_OUT=$(gh pr merge "$PR_N" --repo "$REMOTE" --squash \
    --match-head-commit "$FROZEN_HEAD_OID" --subject "$TITLE (#$PR_N)" 2>&1)
  merge_rc=$?
  STATE_OUT=$(gh pr view "$PR_N" --repo "$REMOTE" --json state,mergedAt,mergeCommit 2>&1)
  state_rc=$?
  set -e
  if [ "$state_rc" -ne 0 ] || ! printf '%s' "$STATE_OUT" | jq -e \
    '.state=="MERGED" and (.mergedAt|type=="string" and length>0) and (.mergeCommit.oid|type=="string" and test("^[0-9a-fA-F]{40}$"))' \
    >/dev/null 2>&1; then
    # merge 是远端 commit point；命令/回执失败后不能声称 main 未变。
    echo "PM_CLOSEOUT_RESULT: REMOTE_MERGE_OUTCOME_UNKNOWN pr=$PR_N head=$WORKER_TIP merge_exit=$merge_rc state_exit=$state_rc" >&2
    exit 9
  fi
  MERGE_SHA=$(printf '%s' "$STATE_OUT" | jq -r '.mergeCommit.oid')
  run_redacted git-fetch-after-remote-merge git fetch origin --quiet || {
    echo "PM_CLOSEOUT_RESULT: REMOTE_MERGE_OUTCOME_UNKNOWN pr=$PR_N merge_commit=$MERGE_SHA reason=fetch-failed" >&2
    exit 9
  }
  git merge-base --is-ancestor "$MERGE_SHA" 'origin/main^{commit}' || {
    echo "PM_CLOSEOUT_RESULT: REMOTE_MERGED_REVIEW_REQUIRED pr=$PR_N merge_commit=$MERGE_SHA reason=commit-not-on-main" >&2
    exit 9
  }
  MERGE_PARENT=$(git rev-parse "$MERGE_SHA^1" 2>/dev/null || true)
  MERGE_TREE=$(git rev-parse "$MERGE_SHA^{tree}" 2>/dev/null || true)
  if [ "$MERGE_PARENT" != "$STABLE_MAIN" ] || [ "$MERGE_TREE" != "$CANDIDATE_TREE" ]; then
    echo "PM_CLOSEOUT_RESULT: REMOTE_MERGED_REVIEW_REQUIRED pr=$PR_N merge_commit=$MERGE_SHA expected_base=$STABLE_MAIN actual_base=${MERGE_PARENT:-unknown} expected_tree=$CANDIDATE_TREE actual_tree=${MERGE_TREE:-unknown}" >&2
    exit 9
  fi
  echo "PM_CLOSEOUT_MERGED: #$PR_N commit=$MERGE_SHA"
  [ "$KEEP_BRANCH" -eq 1 ] || echo "PM_CLOSEOUT_BRANCH_RETAINED: automatic cleanup belongs to Task-103; no raw delete push"
  echo "PM_CLOSEOUT_RESULT: REMOTE_PR pr=$PR_N head=$WORKER_TIP merge_commit=$MERGE_SHA"; exit 0
fi

# 9b) unprotected local authority: push the verified isolated main candidate first;
# only after remote confirmation fast-forward the user's clean main worktree.
[ -z "$(git -C "$MAIN_WT" status --porcelain)" ] || finish_validate_only main-worktree-became-dirty
[ "$(git -C "$MAIN_WT" branch --show-current)" = "main" ] || finish_validate_only main-worktree-branch-drift
[ "$(git -C "$MAIN_WT" rev-parse HEAD)" = "$STABLE_MAIN" ] || finish_validate_only main-worktree-head-drift
run_redacted git-fetch-before-local-push git fetch origin --quiet || exit $?
[ "$(git rev-parse 'origin/main^{commit}')" = "$STABLE_MAIN" ] || finish_validate_only origin-main-drift-before-local-push
audit_still_unique || { echo "PM_CLOSEOUT_PR_SET_DRIFT: before local main push" >&2; exit 5; }
snapshot_still_frozen || { echo "PM_CLOSEOUT_REVIEW_DRIFT: before local main push" >&2; exit 5; }
FINAL_PROTECTION_STATE=$(read_protection_state)
[ "$FINAL_PROTECTION_STATE" = "unprotected" ] || {
  finish_validate_only "main-protection-drift-$FINAL_PROTECTION_STATE"
}
if [ -n "$AUTH_PR_CLOSE" ]; then require_authority "$AUTH_PR_CLOSE" pr-close "$PR_N" || exit 64; fi
set +e
run_redacted safe-push-main "$SP" --repo "$CANDIDATE_WT" --base origin/main --branch main \
  --expected-name "$GIT_NAME" --expected-email "$GIT_EMAIL" >/dev/null
safe_push_rc=$?
set -e
LOCAL_SHA=$CANDIDATE_SHA
run_redacted git-fetch-after-local-push git fetch origin --quiet || {
  echo "PM_CLOSEOUT_RESULT: MAIN_PUSH_OUTCOME_UNKNOWN candidate=$LOCAL_SHA reason=fetch-failed" >&2
  exit 9
}
REMOTE_MAIN=$(git rev-parse 'origin/main^{commit}')
if [ "$safe_push_rc" -ne 0 ] && [ "$REMOTE_MAIN" != "$LOCAL_SHA" ]; then
  if [ "$REMOTE_MAIN" = "$STABLE_MAIN" ]; then exit "$safe_push_rc"; fi
  echo "PM_CLOSEOUT_RESULT: MAIN_PUSH_OUTCOME_UNKNOWN candidate=$LOCAL_SHA remote=$REMOTE_MAIN" >&2
  exit 9
fi
[ "$REMOTE_MAIN" = "$LOCAL_SHA" ] || {
  echo "PM_CLOSEOUT_RESULT: MAIN_PUSH_OUTCOME_UNKNOWN candidate=$LOCAL_SHA remote=$REMOTE_MAIN" >&2; exit 9
}
[ "$(git -C "$CANDIDATE_WT" rev-parse 'HEAD^{tree}')" = "$CANDIDATE_TREE" ] || {
  echo "PM_CLOSEOUT_RESULT: REMOTE_MAIN_APPLIED_REVIEW_REQUIRED main_commit=$LOCAL_SHA reason=candidate-tree-drift" >&2
  exit 9
}

# Remote delivery is complete. Synchronize local main only if its exact preconditions still hold.
if [ -n "$(git -C "$MAIN_WT" status --porcelain)" ] || \
   [ "$(git -C "$MAIN_WT" branch --show-current)" != "main" ] || \
   [ "$(git -C "$MAIN_WT" rev-parse HEAD)" != "$STABLE_MAIN" ]; then
  echo "PM_CLOSEOUT_RESULT: REMOTE_MAIN_APPLIED_LOCAL_PENDING remote_main=$LOCAL_SHA reason=main-worktree-drift-after-push" >&2
  exit 9
fi
run_redacted git-fetch-main-worktree git -C "$MAIN_WT" fetch origin main --quiet || {
  echo "PM_CLOSEOUT_RESULT: REMOTE_MAIN_APPLIED_LOCAL_PENDING remote_main=$LOCAL_SHA reason=local-fetch-failed" >&2
  exit 9
}
git -C "$MAIN_WT" merge --ff-only "$LOCAL_SHA" >/dev/null || {
  echo "PM_CLOSEOUT_RESULT: REMOTE_MAIN_APPLIED_LOCAL_PENDING remote_main=$LOCAL_SHA reason=fast-forward-failed" >&2; exit 9
}
[ "$(git -C "$MAIN_WT" rev-parse HEAD)" = "$LOCAL_SHA" ] && \
[ "$(git -C "$MAIN_WT" rev-parse 'HEAD^{tree}')" = "$CANDIDATE_TREE" ] && \
[ -z "$(git -C "$MAIN_WT" status --porcelain)" ] || {
  echo "PM_CLOSEOUT_RESULT: REMOTE_MAIN_APPLIED_LOCAL_PENDING remote_main=$LOCAL_SHA reason=tree-or-status-mismatch" >&2; exit 9
}
echo "PM_CLOSEOUT_LOCAL_INTEGRATED: pr=$PR_N commit=$LOCAL_SHA"
if [ -n "$AUTH_PR_CLOSE" ]; then
  CLOSE_READY=$(gh pr view "$PR_N" --repo "$REMOTE" --json state,headRefOid 2>/dev/null || true)
  if [ "$(printf '%s' "$CLOSE_READY" | jq -r '.state // empty' 2>/dev/null)" != "OPEN" ] || \
     [ "$(printf '%s' "$CLOSE_READY" | jq -r '.headRefOid // empty' 2>/dev/null)" != "$FROZEN_HEAD_OID" ]; then
    echo "PM_CLOSEOUT_PR_LEFT_OPEN: #$PR_N reason=head-or-state-drift-after-main-push"
    echo "PM_CLOSEOUT_RESULT: LOCAL_AFTER_PR pr=$PR_N head=$WORKER_TIP main_commit=$LOCAL_SHA"
    exit 0
  fi
  set +e
  gh pr close "$PR_N" --repo "$REMOTE" --comment "Integrated locally as $LOCAL_SHA" >/dev/null 2>&1
  close_rc=$?
  CLOSED=$(gh pr view "$PR_N" --repo "$REMOTE" --json state 2>&1)
  close_state_rc=$?
  set -e
  if [ "$close_state_rc" -ne 0 ] || [ "$(printf '%s' "$CLOSED" | jq -r '.state // empty' 2>/dev/null)" != "CLOSED" ]; then
    echo "PM_CLOSEOUT_RESULT: LOCAL_AFTER_PR_CLOSE_OUTCOME_UNKNOWN pr=$PR_N main_commit=$LOCAL_SHA close_exit=$close_rc state_exit=$close_state_rc" >&2
    exit 9
  fi
  echo "PM_CLOSEOUT_PR_CLOSED: #$PR_N integrated_commit=$LOCAL_SHA"
else
  echo "PM_CLOSEOUT_PR_LEFT_OPEN: #$PR_N reason=close-authorization-missing"
fi
echo "PM_CLOSEOUT_RESULT: LOCAL_AFTER_PR pr=$PR_N head=$WORKER_TIP main_commit=$LOCAL_SHA"
