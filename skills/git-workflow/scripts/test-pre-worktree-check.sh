#!/usr/bin/env bash
# pre-worktree-check.sh 故障注入测试：bare 仓 + 双 clone 夹具覆盖四态判定与
# --pre-pr 合并模拟，只读断言（脚本本身绝不改动夹具分支状态）。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CHECK="$SCRIPT_DIR/pre-worktree-check.sh"

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

# 隔离全局/系统配置，排除本机真实配置干扰
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

run_check() {
  (cd "$C1" && "$CHECK" "$@") >"$OUT" 2>"$ERR"
}

expect_ok_contains() {
  local name="$1"
  local expected="$2"
  shift 2
  if run_check "$@"; then
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

expect_exit_1_contains() {
  local name="$1"
  local expected="$2"
  shift 2
  local rc=0
  run_check "$@" || rc=$?
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
  run_check "$@" || rc=$?
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

commit_in() { # commit_in <repo> <file> <content> <msg>（在指定 clone 内提交）
  echo "$3" > "$1/$2"
  git -C "$1" add "$2"
  git -C "$1" commit -q -m "$4"
}

# ---- 夹具：bare origin + C1（主测）/C2（推远端推进） ----
BARE="$WORK/origin.git"
C1="$WORK/c1"
C2="$WORK/c2"
git init -q --bare -b main "$BARE"
git clone -q "$BARE" "$C1"
git clone -q "$BARE" "$C2"

# 共同基线：file1 入库并 push，C1/C2 与 origin 同步
commit_in "$C1" file1 "line1" "baseline: file1"
git -C "$C1" push -q origin main

# ---- 1. IN_SYNC + 现场简报 ----
echo "untracked-local" > "$C1/scratch.txt"
expect_ok_contains "IN_SYNC: 同步态 GO" "IN_SYNC" main
if grep -qF "1 项" "$OUT"; then
  ok "IN_SYNC: untracked 现场简报计数"
else
  not_ok "IN_SYNC: untracked 现场简报计数"
fi
rm "$C1/scratch.txt"

# ---- 2. base ref 不存在 ----
expect_exit_2_contains "用法: 远端 base 不存在报 exit 2" "远端 base ref 不存在" nosuchbase

# 独立 ahead base：不改变后续 main 的 BEHIND/DIVERGED 夹具。
git -C "$C1" switch -q -c ahead-base origin/main
git -C "$C1" push -q origin ahead-base
commit_in "$C1" ahead.txt "ahead-only" "local: ahead base"
ahead_before=$(git -C "$C1" rev-parse ahead-base)
expect_ok_contains "AHEAD: 本地领先 GO_WITH_NOTE" "GO_WITH_NOTE" ahead-base
[ "$(git -C "$C1" rev-parse ahead-base)" = "$ahead_before" ] && \
  ok "AHEAD: 保留本地独有提交" || not_ok "AHEAD: 保留本地独有提交"
git -C "$C1" switch -q main

# ---- 3. --pre-pr 干净合并 ----
git -C "$C1" switch -q -c feat/clean origin/main
commit_in "$C1" newfile.txt "new" "feat: new file"
expect_ok_contains "pre-pr: 模拟合并干净 GO" "GO" --pre-pr feat/clean main

# ---- 4. --pre-pr 冲突：feat/conf 与远端推进改同一文件同一行 ----
git -C "$C1" switch -q -c feat/conf origin/main
commit_in "$C1" file1 "local-change" "feat: local edit file1"
git -C "$C2" fetch -q origin && git -C "$C2" checkout -q -b main origin/main
commit_in "$C2" file1 "remote-change" "remote: edit file1"
git -C "$C2" push -q origin main
expect_exit_1_contains "pre-pr: 模拟合并冲突 NO_GO" "NO_GO" --pre-pr feat/conf main
if grep -qF "file1" "$OUT"; then
  ok "pre-pr: 冲突文件清单含 file1"
else
  not_ok "pre-pr: 冲突文件清单含 file1"
fi

# ---- 5. BEHIND：远端已推进（C2 刚 push），C1 main 未跟 ----
git -C "$C1" switch -q main
expect_exit_1_contains "BEHIND: 本地落后 FIX_FIRST" "BEHIND" main

# ---- 6. DIVERGED：C1 main 再加本地独有提交 → 双向分叉 ----
commit_in "$C1" local_only.txt "only-local" "local: ahead commit"
expect_exit_1_contains "DIVERGED: 双向分叉 FIX_FIRST" "DIVERGED" main

# ---- 7. --pre-pr 分支不存在 ----
expect_exit_2_contains "pre-pr: 分支不存在 exit 2" "待检分支不存在" --pre-pr nosuchbranch main

# ---- 8. 本地 base 分支不存在（未建/已删） ----
git -C "$C1" switch -q -c tmp-detached
git -C "$C1" branch -q -D main
expect_ok_contains "本地 base 缺失: 以远端 ref 起点提示" "本地分支 main 不存在" main

echo
echo "== 结果: $pass passed, $fail failed =="
[ "$fail" -eq 0 ] || exit 1
