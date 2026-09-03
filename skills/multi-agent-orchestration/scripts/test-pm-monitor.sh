#!/usr/bin/env bash
# test-pm-monitor.sh — pm-monitor.sh tmux 判活三态回归门禁（Task-113）
#
# 背景：Badminton Lab 实测 pm-monitor 把可用 `tmux capture-pane`/`tmux has-session`
# 证明仍存活的 bl112/bl113-glm53flash 报为 SESSION_GONE。旧实现把三种失败折叠成
# 同一个 `! tmux has-session` → dead 分支：
#   ① tmux 命令不在 PATH（rc=127，Monitor/受限环境常见）
#   ② tmux 可用但控制面查询失败（socket 不可达 / Permission denied 等）
#   ③ 目标 session 确实不存在（can't find session / no server running）
# 只有 ③ 是可靠的 absent；①② 必须输出可机器识别的 SESSION_UNKNOWN +
# AGENT_NEEDS_INPUT，不能冒充 dead。
#
# 方法：PATH shim fake tmux（模式驱动，POSIX sh）+ 临时 Git 仓库跑 --once/短循环，
# 覆盖：alive 不误报、可靠 absent 才 SESSION_GONE、查询错误/命令不可用报 UNKNOWN、
# 同状态多轮去重、恢复事件。Case 4/5/6 对旧实现（折叠判死）必红。
#
# 用法：bash scripts/test-pm-monitor.sh  # exit 0 全过，1 有失败
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PM="$SCRIPT_DIR/pm-monitor.sh"
[ -f "$PM" ] || { echo "✗ 找不到 $PM" >&2; exit 1; }

# pm-monitor 需要 bash 4+（关联数组）；测试自身选一个可用的 bash4 来拉起被测脚本。
BASH_BIN="$(command -v bash)"
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
  for candidate in /opt/homebrew/bin/bash /usr/local/bin/bash /usr/bin/bash; do
    if [ -x "$candidate" ] && [ "$("$candidate" -c 'echo ${BASH_VERSINFO[0]}')" -ge 4 ]; then
      BASH_BIN="$candidate"
      break
    fi
  done
fi
if [ "$("$BASH_BIN" -c 'echo ${BASH_VERSINFO[0]}')" -lt 4 ]; then
  echo "✗ 需要 bash 4+ 才能测试 pm-monitor.sh（关联数组）" >&2
  exit 1
fi

TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

pass=0
fail=0
ok() { printf '  ✓ %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  ✗ %s\n' "$1" >&2; fail=$((fail + 1)); }

# ===== fake tmux（POSIX sh；FAKE_TMUX_MODE 或 FAKE_TMUX_SEQUENCE 驱动）=====
FAKE_BIN="$TMP_ROOT/bin"
mkdir -p "$FAKE_BIN"
FAKE_TMUX="$FAKE_BIN/tmux"
cat > "$FAKE_TMUX" <<'FAKE'
#!/bin/sh
# fake tmux — 仅 test-pm-monitor.sh 使用；模式：
#   live      has-session 直接成功
#   absent    can't find session（服务器可达，目标不存在 → 可靠 absent）
#   no-server no server running（服务器未运行 → 控制面明确无 session）
#   error     error connecting ... Permission denied（控制面查询失败 → unknown）
mode=""
if [ -n "${FAKE_TMUX_SEQUENCE:-}" ] && [ -f "${FAKE_TMUX_SEQUENCE:-}" ]; then
  count_file="${FAKE_TMUX_SEQUENCE}.count"
  n=0
  [ -f "$count_file" ] && n=$(cat "$count_file")
  n=$((n + 1))
  printf '%s\n' "$n" > "$count_file"
  total=$(wc -l < "$FAKE_TMUX_SEQUENCE" | tr -d ' ')
  if [ "$n" -gt "$total" ]; then n=$total; fi
  mode=$(sed -n "${n}p" "$FAKE_TMUX_SEQUENCE")
else
  mode="${FAKE_TMUX_MODE:-live}"
fi
target=""
prev_arg=""
for a in "$@"; do
  if [ "$prev_arg" = "-t" ]; then target="$a"; fi
  prev_arg="$a"
done
case "$mode" in
  live)      exit 0 ;;
  absent)    echo "can't find session: $target" >&2; exit 1 ;;
  no-server) echo "no server running on /tmp/tmux-501/default" >&2; exit 1 ;;
  error)     echo "error connecting to /tmp/tmux-501/default: Permission denied" >&2; exit 1 ;;
  *)         echo "fake tmux: unknown mode $mode" >&2; exit 2 ;;
esac
FAKE
chmod +x "$FAKE_TMUX"

# 构造“tmux 命令不可用”的 PATH：把当前 PATH 内除 tmux 外的全部可执行文件
# symlink 进独立目录（忠实模拟 Monitor/受限环境缺 tmux 的形态）。
STRIPPED_BIN="$TMP_ROOT/bin-stripped"
build_stripped_path() {
  local dest="$1" dir entry name
  mkdir -p "$dest"
  local oldIFS=$IFS
  IFS=':'
  for dir in $PATH; do
    [ -n "$dir" ] && [ -d "$dir" ] || continue
    for entry in "$dir"/* "$dir"/.*; do
      name="${entry##*/}"
      case "$name" in
        .|..|tmux) continue ;;
      esac
      [ -f "$entry" ] && [ -x "$entry" ] || continue
      [ -e "$dest/$name" ] || ln -s "$entry" "$dest/$name" 2>/dev/null || true
    done
  done
  IFS=$oldIFS
}
build_stripped_path "$STRIPPED_BIN"
if [ -e "$STRIPPED_BIN/tmux" ]; then
  echo "✗ stripped PATH 仍含 tmux，Case 5 无法构造" >&2
  exit 1
fi

# ===== 临时 Git 仓库（本地分支未被任何 worktree 检出）=====
REPO="$TMP_ROOT/repo"
"$BASH_BIN" -c "
  git init -q -b main '$REPO' &&
  git -C '$REPO' config user.email test@example.com &&
  git -C '$REPO' config user.name test &&
  git -C '$REPO' commit -q --allow-empty -m init &&
  git -C '$REPO' checkout -q -b feat/task113 &&
  git -C '$REPO' commit -q --allow-empty -m wip &&
  git -C '$REPO' checkout -q main
" >/dev/null 2>&1
BRANCH="feat/task113"
SESSION="worker-a"

# ===== 运行辅助 =====
run_once() {
  # $1=FAKE_TMUX_MODE $2=输出文件 $3=PATH（可选，默认 fake-bin + 原 PATH）
  local mode="$1" outfile="$2" path="${3:-$FAKE_BIN:$PATH}"
  set +e
  (
    cd "$TMP_ROOT" || exit 99
    export PATH="$path"
    export FAKE_TMUX_MODE="$mode"
    unset FAKE_TMUX_SEQUENCE
    exec "$BASH_BIN" "$PM" \
      --project "$REPO" \
      --branch "$BRANCH:$SESSION" \
      --base-ref main \
      --once
  ) >"$outfile" 2>&1
  set -e
}

run_loop() {
  # $1=FAKE_TMUX_MODE $2=FAKE_TMUX_SEQUENCE(可选) $3=输出文件 $4=PATH
  local mode="$1" seq="$2" outfile="$3" path="$4" pid
  set +e
  (
    cd "$TMP_ROOT" || exit 99
    export PATH="$path"
    export FAKE_TMUX_MODE="$mode"
    if [ -n "$seq" ]; then
      export FAKE_TMUX_SEQUENCE="$seq"
    else
      unset FAKE_TMUX_SEQUENCE
    fi
    exec "$BASH_BIN" "$PM" \
      --project "$REPO" \
      --branch "$BRANCH:$SESSION" \
      --base-ref main \
      --interval 1
  ) >"$outfile" 2>&1 &
  pid=$!
  # 3 个迭代足够（t≈0/1/2s）；判活每迭代消费 2 次 tmux 调用（check_tmux_session + staleness）
  sleep 2.6
  kill "$pid" 2>/dev/null
  wait "$pid" 2>/dev/null
  set -e
}

count_lines() { # $1=needle $2=file → 打印次数（grep -c 无匹配时 exit 1）
  grep -cF "$1" "$2" 2>/dev/null || true
}

assert_count() { # $1=说明 $2=期望次数 $3=needle $4=file
  local label="$1" expected="$2" needle="$3" file="$4" actual
  actual=$(count_lines "$needle" "$file")
  if [ "$actual" = "$expected" ]; then
    ok "$label"
  else
    bad "${label}（期望 ${expected} 次，实际 ${actual} 次）"
    grep -n "SESSION" "$file" 2>/dev/null | head -10 >&2 || true
  fi
}

assert_run_completed() { # $1=file
  if grep -qF "PM_MONITOR_ONCE_COMPLETE" "$1" 2>/dev/null; then
    ok "巡检完整跑完（PM_MONITOR_ONCE_COMPLETE）"
  else
    bad "巡检未完整跑完（缺 PM_MONITOR_ONCE_COMPLETE，控制面故障不得中断监控主循环）"
    head -20 "$1" >&2 || true
  fi
}

echo "Case 1: session 存活（fake tmux exit 0）→ 不得报 SESSION_GONE/UNKNOWN"
OUT1="$TMP_ROOT/case1.out"
run_once "live" "$OUT1"
assert_run_completed "$OUT1"
assert_count "存活 session 零 SESSION_GONE" 0 "SESSION_GONE:" "$OUT1"
assert_count "存活 session 零 SESSION_UNKNOWN" 0 "SESSION_UNKNOWN:" "$OUT1"

echo "Case 2: 目标确实不存在（can't find session）→ 恰好 1 条 SESSION_GONE"
OUT2="$TMP_ROOT/case2.out"
run_once "absent" "$OUT2"
assert_run_completed "$OUT2"
assert_count "可靠 absent 报 SESSION_GONE" 1 "SESSION_GONE:" "$OUT2"
assert_count "可靠 absent 不报 SESSION_UNKNOWN" 0 "SESSION_UNKNOWN:" "$OUT2"

echo "Case 3: no server running（控制面明确无 session）→ 视为可靠 absent"
OUT3="$TMP_ROOT/case3.out"
run_once "no-server" "$OUT3"
assert_run_completed "$OUT3"
assert_count "no-server 报 SESSION_GONE" 1 "SESSION_GONE:" "$OUT3"
assert_count "no-server 不报 SESSION_UNKNOWN" 0 "SESSION_UNKNOWN:" "$OUT3"

echo "Case 4: 控制面查询失败（socket Permission denied）→ SESSION_UNKNOWN + NEEDS_INPUT，禁止 SESSION_GONE"
OUT4="$TMP_ROOT/case4.out"
run_once "error" "$OUT4"
assert_run_completed "$OUT4"
assert_count "查询错误必须报 SESSION_UNKNOWN" 1 "SESSION_UNKNOWN:" "$OUT4"
assert_count "查询错误必须附 AGENT_NEEDS_INPUT" 1 "AGENT_NEEDS_INPUT:" "$OUT4"
assert_count "查询错误禁止冒充 SESSION_GONE" 0 "SESSION_GONE:" "$OUT4"

echo "Case 5: tmux 命令不在 PATH（受限环境）→ SESSION_UNKNOWN + NEEDS_INPUT，禁止 SESSION_GONE"
OUT5="$TMP_ROOT/case5.out"
run_once "live" "$OUT5" "$STRIPPED_BIN"
assert_run_completed "$OUT5"
assert_count "tmux 缺失必须报 SESSION_UNKNOWN" 1 "SESSION_UNKNOWN:" "$OUT5"
assert_count "tmux 缺失必须附 AGENT_NEEDS_INPUT" 1 "AGENT_NEEDS_INPUT:" "$OUT5"
assert_count "tmux 缺失禁止冒充 SESSION_GONE" 0 "SESSION_GONE:" "$OUT5"

echo "Case 6: 状态去重（连续 3 轮查询失败）→ 事件只发 1 次"
OUT6="$TMP_ROOT/case6.out"
run_loop "error" "" "$OUT6" "$FAKE_BIN:$PATH"
assert_count "UNKNOWN 状态 3 轮只发 1 次" 1 "SESSION_UNKNOWN:" "$OUT6"
assert_count "NEEDS_INPUT 3 轮只发 1 次" 1 "AGENT_NEEDS_INPUT:" "$OUT6"
assert_count "查询错误全程禁止 SESSION_GONE" 0 "SESSION_GONE:" "$OUT6"

echo "Case 7: 恢复（absent → live）→ SESSION_GONE 与 SESSION_RECOVERED 各 1 次"
OUT7="$TMP_ROOT/case7.out"
SEQ7="$TMP_ROOT/seq7"
printf '%s\n' absent live live live live live > "$SEQ7"
run_loop "" "$SEQ7" "$OUT7" "$FAKE_BIN:$PATH"
assert_count "absent 只报 1 次 SESSION_GONE" 1 "SESSION_GONE:" "$OUT7"
assert_count "恢复时报 1 次 SESSION_RECOVERED" 1 "SESSION_RECOVERED:" "$OUT7"
assert_count "恢复过程零 SESSION_UNKNOWN" 0 "SESSION_UNKNOWN:" "$OUT7"

echo
echo "结果：$pass 通过，$fail 失败"
if [ "$fail" -gt 0 ]; then
  echo "test-pm-monitor.sh: FAIL" >&2
  exit 1
fi
echo "test-pm-monitor.sh: PASS"
