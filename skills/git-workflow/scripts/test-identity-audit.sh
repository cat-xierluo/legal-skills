#!/usr/bin/env bash
# identity-audit.sh 故障注入测试：临时仓夹具 + 隔离全局配置，只读断言。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
AUDIT="$SCRIPT_DIR/identity-audit.sh"

pass=0
fail=0

ok() {
  printf 'PASS: %s\n' "$1"
  pass=$((pass + 1))
}

not_ok() {
  printf 'FAIL: %s\n' "$1" >&2
  fail=$((fail + 1))
}

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# 隔离全局/系统配置：全局身份=用户标准样（GitHub noreply），排除本机真实配置干扰
GLOBAL_CFG="$WORK/global-gitconfig"
cat > "$GLOBAL_CFG" <<'EOF'
[user]
	name = cat-xierluo
	email = 66555304+cat-xierluo@users.noreply.github.com
EOF
export GIT_CONFIG_GLOBAL="$GLOBAL_CFG"
export GIT_CONFIG_SYSTEM=/dev/null

OUT="$WORK/out.txt"
ERR="$WORK/err.txt"

run_audit() {
  "$AUDIT" "$@" >"$OUT" 2>"$ERR"
}

expect_ok() {
  local name="$1"
  shift
  if run_audit "$@"; then
    ok "$name"
  else
    cat "$OUT" "$ERR" >&2 || true
    not_ok "$name (unexpected exit $?)"
  fi
}

expect_exit_1_contains() {
  local name="$1"
  local expected="$2"
  shift 2
  local rc=0
  run_audit "$@" || rc=$?
  if [ "$rc" -ne 1 ]; then
    cat "$OUT" "$ERR" >&2 || true
    not_ok "$name (expected exit 1, got $rc)"
    return
  fi
  if grep -qF "$expected" "$OUT" "$ERR"; then
    ok "$name"
  else
    cat "$OUT" "$ERR" >&2 || true
    not_ok "$name (missing: $expected)"
  fi
}

expect_exit_2_contains() {
  local name="$1"
  local expected="$2"
  shift 2
  local rc=0
  run_audit "$@" || rc=$?
  if [ "$rc" -ne 2 ]; then
    cat "$OUT" "$ERR" >&2 || true
    not_ok "$name (expected exit 2, got $rc)"
    return
  fi
  if grep -qF "$expected" "$OUT" "$ERR"; then
    ok "$name"
  else
    cat "$OUT" "$ERR" >&2 || true
    not_ok "$name (missing: $expected)"
  fi
}

expect_ok_contains() {
  local name="$1"
  local expected="$2"
  shift 2
  if run_audit "$@"; then
    if grep -qF "$expected" "$OUT" "$ERR"; then
      ok "$name"
    else
      cat "$OUT" "$ERR" >&2 || true
      not_ok "$name (missing: $expected)"
    fi
  else
    cat "$OUT" "$ERR" >&2 || true
    not_ok "$name (unexpected exit $?)"
  fi
}

commit_as() {
  # commit_as <repo> <name> <email> <message>（夹具无工作区内容，必须 --allow-empty）
  git -C "$1" -c "user.name=$2" -c "user.email=$3" commit -q --allow-empty -m "$4"
}

# ---- 夹具仓 1：干净仓（全局身份，无覆盖，无尾注）----
CLEAN="$WORK/clean"
git init -q "$CLEAN"
git -C "$CLEAN" commit -q --allow-empty -m "init"

# ---- 夹具仓 2：污染仓（hermes 仓库级覆盖 + 占位邮箱提交 + agent 尾注）----
DIRTY="$WORK/dirty"
git init -q "$DIRTY"
git -C "$DIRTY" -c user.name=cat-xierluo \
  -c user.email=66555304+cat-xierluo@users.noreply.github.com \
  commit -q --allow-empty -m "clean baseline"
git -C "$DIRTY" config user.name "Hermes(info-assistant)"
git -C "$DIRTY" config user.email "info-assistant@hermes.local"
commit_as "$DIRTY" "Hermes(info-assistant)" "info-assistant@hermes.local" \
  "junk author commit"
git -C "$DIRTY" -c user.name=cat-xierluo \
  -c user.email=66555304+cat-xierluo@users.noreply.github.com \
  commit -q --allow-empty -m "with trailer" -m "Co-authored-by: Hermes(info-assistant) <info-assistant@hermes.local>"

# ---- whoami ----

expect_ok "whoami: 干净仓全局身份通过" whoami --repo "$CLEAN"

expect_exit_1_contains "whoami: 仓库级 hermes 覆盖告警" \
  "IDENTITY_AUDIT_WARN: local 级覆盖" whoami --repo "$DIRTY"

expect_exit_1_contains "whoami: hermes 身份命中可疑模式" \
  "邮箱命中占位/agent 域模式" whoami --repo "$DIRTY"

expect_exit_1_contains "whoami: --expected-name 不符即 FAIL" \
  "IDENTITY_AUDIT_FAIL: user.name" whoami --repo "$CLEAN" \
  --expected-name "someone-else"

expect_ok "whoami: --allow-local-override 抑制覆盖告警" whoami --repo "$DIRTY" \
  --allow-local-override --allow-name "Hermes(info-assistant)" \
  --allow-email "info-assistant@hermes.local"

# env 覆盖检测：只改 env 不动 config
if GIT_AUTHOR_NAME="checkpointer" GIT_AUTHOR_EMAIL="checkpointer@noreply" \
    run_audit whoami --repo "$CLEAN"; then
  not_ok "whoami: env 覆盖应告警（unexpected success）"
else
  if grep -qF "IDENTITY_AUDIT_WARN: GIT_AUTHOR_NAME=checkpointer" "$OUT"; then
    ok "whoami: env 覆盖告警"
  else
    cat "$OUT" "$ERR" >&2 || true
    not_ok "whoami: env 覆盖告警（缺告警行）"
  fi
fi

# worktree 级覆盖检测
WT="$WORK/dirty-wt"
git -C "$DIRTY" worktree add -q --detach "$WT" >/dev/null 2>&1
git -C "$WT" config extensions.worktreeConfig true
git -C "$WT" config --worktree user.email "bot@openclaw.local"
expect_exit_1_contains "whoami: worktree 级覆盖告警" \
  "IDENTITY_AUDIT_WARN: worktree 级覆盖 user.email" whoami --repo "$WT"

# ---- history ----

expect_exit_1_contains "history: 污染仓发现可疑作者/尾注" \
  "IDENTITY_AUDIT_FINDINGS" history --repo "$DIRTY"

HIST_OUT="$WORK/hist.txt"
hist_rc=0
"$AUDIT" history --repo "$DIRTY" >"$HIST_OUT" 2>&1 || hist_rc=$?
# 脚本会剥掉 "Co-authored-by:" 前缀，故按分布表标题断言
[ "$hist_rc" -eq 1 ] && \
  grep -qF "info-assistant@hermes.local" "$HIST_OUT" && \
  grep -qF "Co-authored-by 尾注分布" "$HIST_OUT" && \
  grep -qF "[可疑" "$HIST_OUT" \
  && ok "history: 尾注与作者均被标注" \
  || { cat "$HIST_OUT" >&2; not_ok "history: 尾注与作者均被标注（expected exit 1, got ${hist_rc}）"; }

expect_exit_1_contains "history: --range 只审指定范围" \
  "IDENTITY_AUDIT_FINDINGS" history --repo "$DIRTY" \
  --range "$(git -C "$DIRTY" rev-parse HEAD~2)..HEAD"

# --allow-email 放行后污染仓仍剩仓库级 author=hermes? 放行 hermes 后应全绿
if run_audit history --repo "$DIRTY" \
    --allow-name "Hermes(info-assistant)" --allow-email "info-assistant@hermes.local"; then
  ok "history: --allow 精确放行后转绿"
else
  cat "$OUT" "$ERR" >&2 || true
  not_ok "history: --allow 精确放行后转绿"
fi

# 干净仓 history 通过
expect_ok "history: 干净仓通过" history --repo "$CLEAN"

# ---- 用法与环境错误 ----

expect_exit_2_contains "非仓库目录报错" "IDENTITY_AUDIT_NOT_REPOSITORY" \
  whoami --repo "$WORK"
expect_exit_2_contains "未知参数报错" "IDENTITY_AUDIT_USAGE" \
  whoami --frobnicate
expect_exit_2_contains "非法 --max-commits 报错" "IDENTITY_AUDIT_USAGE" \
  history --repo "$CLEAN" --max-commits abc

# ---- noreply@ 误伤回归：GitHub noreply 邮箱不得命中 ----
GH_NOREPLY="$WORK/gh-noreply"
git init -q "$GH_NOREPLY"
commit_as "$GH_NOREPLY" "杨卫薪律师" "66555304+cat-xierluo@users.noreply.github.com" \
  "github noreply must pass"
expect_ok "history: users.noreply.github.com 不误伤" history --repo "$GH_NOREPLY"

# ---- receipt：服务端合并回执核验（Task-012）----
# 夹具：普通提交 + 伪造服务端合成签名提交（GitHub<noreply>）
FORGE="$WORK/forge"
git init -q "$FORGE"
commit_as "$FORGE" "cat-xierluo" "66555304+cat-xierluo@users.noreply.github.com" "normal commit"
commit_as "$FORGE" "GitHub" "noreply@github.com" "forged server-style commit"

# 伪造服务端提交：夹具仓无 origin remote → gh 无法定位 → UNKNOWN fail-closed
expect_exit_1_contains "receipt: 伪造服务端提交无回执 UNKNOWN（fail-closed）" \
  "UNKNOWN" receipt --repo "$FORGE" HEAD
if grep -qF "fail-closed" "$OUT" "$ERR"; then
  ok "receipt: UNKNOWN 输出含 fail-closed 提示"
else
  not_ok "receipt: UNKNOWN 输出含 fail-closed 提示"
fi

# 普通提交：SKIP 不计发现、exit 0（不触发任何 gh 调用）
expect_ok_contains "receipt: 普通提交 SKIP 不计" "SKIP" \
  receipt --repo "$FORGE" HEAD~1

# 无效提交引用 / 缺参数 → 用法错误 exit 2
expect_exit_2_contains "receipt: 无效提交引用 exit 2" "无效提交引用" \
  receipt --repo "$FORGE" deadbeefdeadbeef
expect_exit_2_contains "receipt: 缺 OID 与 range exit 2" "IDENTITY_AUDIT_USAGE" \
  receipt --repo "$FORGE"

# --range 模式：范围全为普通提交 → 全 SKIP、exit 0（本地同步对账路径）
commit_as "$CLEAN" "cat-xierluo" "66555304+cat-xierluo@users.noreply.github.com" \
  "second normal commit on clean"
expect_ok_contains "receipt: --range 全普通提交全 SKIP" "IDENTITY_AUDIT_OK" \
  receipt --repo "$CLEAN" --range HEAD~1..HEAD

# 离线 gh 夹具：仅这组测试替换 PATH，不访问真实账号或网络。
BIN="$WORK/bin"
mkdir "$BIN"
cat > "$BIN/gh" <<'GH'
#!/usr/bin/env bash
set -euo pipefail
case "$1 $2" in
  'repo view') printf 'fixture-owner/fixture-repo\n' ;;
  'pr list')
    [ "$RECEIPT_TEST_MODE" != failed ] || exit 1
    if [ "$RECEIPT_TEST_MODE" = malformed ]; then printf 'bad response\n'; exit 0; fi
    # 从脚本真正传给gh的jq表达式判断格式，确保旧候选反例也可运行。
    count_format=0
    for arg in "$@"; do case "$arg" in *COUNT*) count_format=1 ;; esac; done
    if [ "$count_format" = 1 ]; then printf 'COUNT\t%s\n' "$RECEIPT_TEST_COUNT"; fi
    [ "$RECEIPT_TEST_MODE" != empty ] || exit 0
    printf '%s\t#1\t2026-10-03T00:00:00Z\t%s\n' "$RECEIPT_TEST_OID" "$RECEIPT_TEST_OID"
    ;;
  *) exit 2 ;;
esac
GH
chmod +x "$BIN/gh"
export PATH="$BIN:$PATH"
server_oid=$(git -C "$FORGE" rev-parse HEAD)
normal_oid=$(git -C "$FORGE" rev-parse HEAD~1)
export RECEIPT_TEST_MODE=rows RECEIPT_TEST_COUNT=1 RECEIPT_TEST_OID="$server_oid"
expect_ok_contains "receipt: 精确绑定MERGED回执ACCEPT" "ACCEPT" receipt --repo "$FORGE" HEAD --merged-limit 2
expect_ok_contains "receipt: 达到上限但已精确匹配仍ACCEPT" "ACCEPT" receipt --repo "$FORGE" HEAD --merged-limit 1
export RECEIPT_TEST_OID="$normal_oid"
expect_exit_1_contains "receipt: 完整查询无绑定DENY_FORGED" "DENY_FORGED" receipt --repo "$FORGE" HEAD --merged-limit 2
expect_exit_1_contains "receipt: 截断查询未命中UNKNOWN" "UNKNOWN" receipt --repo "$FORGE" HEAD --merged-limit 1
if grep -qF DENY_FORGED "$OUT"; then not_ok "receipt: 截断不贴伪造标签"; else ok "receipt: 截断不贴伪造标签"; fi
export RECEIPT_TEST_MODE=empty RECEIPT_TEST_COUNT=1
expect_exit_1_contains "receipt: 过滤null回执后仍保留截断证据" "UNKNOWN" receipt --repo "$FORGE" HEAD --merged-limit 1
export RECEIPT_TEST_COUNT=0
expect_exit_1_contains "receipt: 完整空列表无绑定DENY_FORGED" "DENY_FORGED" receipt --repo "$FORGE" HEAD --merged-limit 2
export RECEIPT_TEST_MODE=failed
expect_exit_1_contains "receipt: 网络查询失败UNKNOWN" "UNKNOWN" receipt --repo "$FORGE" HEAD
export RECEIPT_TEST_MODE=malformed
expect_exit_1_contains "receipt: 查询格式异常UNKNOWN" "UNKNOWN" receipt --repo "$FORGE" HEAD
expect_exit_2_contains "receipt: limit零值拒绝" "IDENTITY_AUDIT_USAGE" receipt --repo "$FORGE" HEAD --merged-limit 0
expect_exit_2_contains "receipt: 无效范围明确拒绝" "无效提交范围" receipt --repo "$FORGE" --range invalid..HEAD

printf '\n== 身份审计测试：%s passed, %s failed ==\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
