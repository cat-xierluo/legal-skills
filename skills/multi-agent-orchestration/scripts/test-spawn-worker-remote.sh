#!/usr/bin/env bash
# test-spawn-worker-remote.sh — PM 侧远程派发入口测试（mock ssh/rsync/gh，零真实网络）。
# 覆盖：spawn 参数/节点配置校验；PM 软账自限(75)/重复 session(64)；receipt 传输与
# 远端命令构造（--remote-dispatch-receipt / --base-ref origin/main / node- 前缀分支 /
# unset 前缀）；status 软账状态回写；cleanup 前置与软账删除；provision 缺路径补装路径。
# 说明：spawn 链在本测试进程内做 detect_pm_harness（ps 祖先链），需在 Claude 等
# harness 内运行（与 test-harness-backend-policy.sh 同一前提）。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CASE_ROOT=$(mktemp -d)
trap 'rm -rf "$CASE_ROOT"' EXIT

passed=0
failed=0
ok() { printf 'PASS: %s\n' "$1"; passed=$((passed + 1)); }
bad() { printf 'FAIL: %s\n' "$1" >&2; failed=$((failed + 1)); }
expect_rc() { local expected="$1" label="$2" actual="$3"
  if [ "$actual" -eq "$expected" ]; then ok "$label"; else bad "$label (expect rc=$expected got rc=$actual)"; fi }

MOCK_LOG="$CASE_ROOT/mock.log"
: > "$MOCK_LOG"
STATUS_FILE=""  # spawn 成功后由测试写入 fixture 路径

# ---- fixture：本地裸 origin + PM 项目 clone + 节点 root clone（同一 bare，基线一致）----
git init -q --bare "$CASE_ROOT/origin.git"
git clone -q "$CASE_ROOT/origin.git" "$CASE_ROOT/pm-project" 2>/dev/null
git -C "$CASE_ROOT/pm-project" commit -q --allow-empty -m "base"
git -C "$CASE_ROOT/pm-project" branch -M main
git -C "$CASE_ROOT/pm-project" push -q origin main
git clone -q "$CASE_ROOT/origin.git" "$CASE_ROOT/node-root" 2>/dev/null
# 节点 skill 版本与 PM 同源（指向真实 worktree skill），probe 版本门才放行
NODE_SKILL_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

cat > "$CASE_ROOT/personal.json" <<EOF
{
  "remote_nodes": {
    "alpha": {
      "enabled": true,
      "ssh_alias": "mock-host",
      "remote_root": "$CASE_ROOT/node-root",
      "skill_root": "$NODE_SKILL_ROOT",
      "max_workers": 1,
      "load_threshold": 999,
      "active_session_cap": 999,
      "min_free_disk_gb": 0,
      "min_free_memory_percent": 0,
      "connect_timeout_seconds": 5
    }
  }
}
EOF

# ---- mock ssh / rsync / gh（引号 heredoc 零转义；CASE_ROOT/MOCK_LOG 经 env 传入）----
export CASE_ROOT MOCK_LOG
mkdir -p "$CASE_ROOT/bin"
cat > "$CASE_ROOT/bin/mock-ssh" <<'EOF'
#!/usr/bin/env bash
args=()
while [ $# -gt 0 ]; do
  case "$1" in
    -o) shift 2 ;;
    -*) shift ;;
    *) args+=("$1"); shift ;;
  esac
done
cmd="${args[*]:1}"
printf 'SSH: %s\n' "$cmd" >> "$MOCK_LOG"
case "$cmd" in
  "test -d "*|test\ -f*) echo 1 ;;
  "mkdir -p "*) exit 0 ;;
  "chmod 600 "*) exit 0 ;;
  "rm -f "*) exit 0 ;;
  "bash -s -- "*)
    exec bash -c "$cmd" ;;
  "cat "*)
    target=$(printf '%s' "$cmd" | sed -E "s/^cat '([^']*)'.*/\1/")
    [ -f "$target" ] && cat "$target" || echo '(尚无 STATUS.json——worker 刚启动或路径未生成)' ;;
  "jq -r '.status // empty' "*)
    target=$(printf '%s' "$cmd" | sed -E "s/.*'([^']*)' 2>.*$/\1/")
    if [ -f "$target" ]; then jq -r '.status // empty' "$target"; else echo ""; fi ;;
  "zsh -lc "*)
    inner=${cmd#zsh -lc }
    case "$inner" in
      *spawn-worker.sh*)
        sess=$(printf '%s' "$inner" | sed -E 's/.*--session[\\ ]+([A-Za-z0-9_-]+).*/\1/')
        echo "SPAWN_WORKER_METADATA: $CASE_ROOT/node-root/.claude/worktrees/w1/.claude/agent-sessions/${sess}/METADATA.json" ;;
      *pm-cleanup-worker.sh*) echo 'CLEANUP_OK' ;;
      *orca-register-project.py*) echo 'REGISTER_OK' ;;
      *"git clone "*) echo 'CLONE_OK' ;;
      *) echo 'ZSH_OK' ;;
    esac ;;
  *) echo 0 ;;
esac
EOF
chmod +x "$CASE_ROOT/bin/mock-ssh"

cat > "$CASE_ROOT/bin/rsync" <<EOF
#!/usr/bin/env bash
printf 'RSYNC: %s\n' "\$*" >> "$MOCK_LOG"
exit 0
EOF
chmod +x "$CASE_ROOT/bin/rsync"

cat > "$CASE_ROOT/bin/gh" <<EOF
#!/usr/bin/env bash
case "\$1" in
  pr) echo '[]' ;;
  *) echo '[]' ;;
esac
EOF
chmod +x "$CASE_ROOT/bin/gh"

export MULTI_AGENT_ORCHESTRATION_PERSONAL_CONFIG="$CASE_ROOT/personal.json"
export REMOTE_DISPATCH_SSH_COMMAND="$CASE_ROOT/bin/mock-ssh"
export PATH="$CASE_ROOT/bin:$PATH"
REMOTE="$SCRIPT_DIR/spawn-worker-remote.sh"
LEDGER_DIR="$CASE_ROOT/pm-project/.git/orchestration/remote-dispatches"

# ---- 1) 参数与节点配置 ----
bash "$REMOTE" spawn --node alpha --branch b1 2>/dev/null && rc=$? || rc=$?
expect_rc 64 "spawn 缺参 → 64" "$rc"
bash "$REMOTE" spawn --node ghost --branch b1 --session s --worker-backend claude-code 2>/dev/null && rc=$? || rc=$?
expect_rc 64 "节点未配置 → 64" "$rc"

# ---- 2) spawn 成功：receipt/远端命令构造断言 + 软账落盘 ----
bash "$REMOTE" spawn --node alpha --branch fix/demo --session rs1 --worker-backend claude-code \
  --verify-cmd 'python3 -m pytest -q' --local-project "$CASE_ROOT/pm-project" \
  > "$CASE_ROOT/spawn.out" 2>&1 && rc=$? || rc=$?
expect_rc 0 "spawn 成功（mock 全链）" "$rc"
grep -q 'SPAWN_WORKER_REMOTE_OK: node=alpha session=rs1 branch=node-alpha/fix/demo' "$CASE_ROOT/spawn.out" \
  && ok "输出 SPAWN_WORKER_REMOTE_OK" || bad "输出 SPAWN_WORKER_REMOTE_OK"
[ -f "$LEDGER_DIR/alpha/rs1.json" ] && ok "PM 软账落盘" || bad "PM 软账落盘"
jq -e '.remote_branch=="node-alpha/fix/demo" and (.remote.status_file|length>0)' "$LEDGER_DIR/alpha/rs1.json" >/dev/null \
  && ok "软账 remote_branch/status_file 字段" || bad "软账 remote_branch/status_file 字段"
# 远端命令经 printf %q 转义：空格显示为 '\ '，断言按转义后形态匹配
spawn_cmd=$(grep 'SSH: zsh -lc' "$MOCK_LOG" | tail -1)
[[ "$spawn_cmd" == *"--remote-dispatch-receipt"* ]] && ok "远端命令带 --remote-dispatch-receipt" || bad "远端命令带 --remote-dispatch-receipt"
[[ "$spawn_cmd" == *"--base-ref\\ origin/main"* ]] && ok "强制 --base-ref origin/main" || bad "强制 --base-ref origin/main"
[[ "$spawn_cmd" == *"--branch\\ node-alpha/fix/demo"* ]] && ok "分支加 node- 前缀" || bad "分支加 node- 前缀"
[[ "$spawn_cmd" == *"unset\\ ANTHROPIC_AUTH_TOKEN"* ]] && ok "unset 继承 provider env" || bad "unset 继承 provider env"
grep -qF -- '--verify-cmd\ python3\\\ -m\\\ pytest\\\ -q' "$MOCK_LOG" && ok "verify-cmd 透传" || bad "verify-cmd 透传"
rsync_line=$(grep 'RSYNC:' "$MOCK_LOG" | tail -1)
[[ "$rsync_line" == *"remote-dispatch-inbox/receipt-"* ]] && ok "receipt 传到受限 inbox" || bad "receipt 传到受限 inbox"

# ---- 3) 软账自限 ----
bash "$REMOTE" spawn --node alpha --branch fix/demo --session rs1 --worker-backend claude-code \
  --local-project "$CASE_ROOT/pm-project" 2>/dev/null && rc=$? || rc=$?
expect_rc 64 "重复 session → 64" "$rc"
bash "$REMOTE" spawn --node alpha --branch fix/other --session rs2 --worker-backend claude-code \
  --local-project "$CASE_ROOT/pm-project" 2>/dev/null && rc=$? || rc=$?
expect_rc 75 "max_workers=1 软账自限 → 75" "$rc"

# ---- 4) status：STATUS 演进回写软账 ----
mkdir -p "$CASE_ROOT/node-root/.claude/worktrees/w1/.claude/agent-sessions/rs1"
printf '{"status":"done","progress":"全部完成"}' > "$CASE_ROOT/node-root/.claude/worktrees/w1/.claude/agent-sessions/rs1/STATUS.json"
bash "$REMOTE" status --node alpha --session rs1 --local-project "$CASE_ROOT/pm-project" \
  > "$CASE_ROOT/status.out" 2>&1 && rc=$? || rc=$?
expect_rc 0 "status 成功" "$rc"
grep -q '"status":"done"' "$CASE_ROOT/status.out" && ok "status 展示远程 STATUS" || bad "status 展示远程 STATUS"
[ "$(jq -r .state "$LEDGER_DIR/alpha/rs1.json")" = "done" ] && ok "软账 state=done 回写" || bad "软账 state=done 回写"

# ---- 5) cleanup：STATUS 终态放行 + 软账删除 ----
bash "$REMOTE" cleanup --node alpha --session rs1 --local-project "$CASE_ROOT/pm-project" \
  > "$CASE_ROOT/cleanup.out" 2>&1 && rc=$? || rc=$?
expect_rc 0 "cleanup 成功（STATUS done 放行）" "$rc"
grep -q 'CLEANUP_OK' "$CASE_ROOT/cleanup.out" && ok "转发节点侧 pm-cleanup-worker" || bad "转发节点侧 pm-cleanup-worker"
[ ! -f "$LEDGER_DIR/alpha/rs1.json" ] && ok "cleanup 后软账删除" || bad "cleanup 后软账删除"

# ---- 6) cleanup 前置：非终态且无 PR → 64 ----
bash "$REMOTE" spawn --node alpha --branch fix/two --session rs3 --worker-backend claude-code \
  --local-project "$CASE_ROOT/pm-project" >/dev/null 2>&1
mkdir -p "$CASE_ROOT/node-root/.claude/worktrees/w1/.claude/agent-sessions/rs3"
printf '{"status":"running"}' > "$CASE_ROOT/node-root/.claude/worktrees/w1/.claude/agent-sessions/rs3/STATUS.json"
bash "$REMOTE" cleanup --node alpha --session rs3 --local-project "$CASE_ROOT/pm-project" \
  >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 64 "cleanup 非终态无强制 → 64" "$rc"
bash "$REMOTE" cleanup --node alpha --session rs3 --local-project "$CASE_ROOT/pm-project" \
  --force-with-reason "test" >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 0 "cleanup --force-with-reason 放行" "$rc"
rm -f "$LEDGER_DIR/alpha/rs3.json"

# ---- 7) provision：缺 remote_root → 3；--provision 自动补装 → 走通 ----
sed "s|\"remote_root\": \"$CASE_ROOT/node-root\"|\"remote_root\": \"$CASE_ROOT/fresh-root\"|" \
  "$CASE_ROOT/personal.json" > "$CASE_ROOT/personal-fresh.json"
sed "s|\"skill_root\": \"$NODE_SKILL_ROOT\"|\"skill_root\": \"$CASE_ROOT/fresh-root/skills/multi-agent-orchestration\"|" \
  "$CASE_ROOT/personal-fresh.json" > "$CASE_ROOT/personal-fresh2.json"
export MULTI_AGENT_ORCHESTRATION_PERSONAL_CONFIG="$CASE_ROOT/personal-fresh2.json"
bash "$REMOTE" spawn --node alpha --branch fix/new --session rp1 --worker-backend claude-code \
  --local-project "$CASE_ROOT/pm-project" >/dev/null 2>&1 && rc=$? || rc=$?
expect_rc 3 "缺 remote_root 无 --provision → 3" "$rc"

# provision 子命令：clone 走 mock（模拟建目录+skill CHANGELOG），注册走 mock
mkdir -p "$CASE_ROOT/fresh-root/skills/multi-agent-orchestration"
printf '## [%s] - 2026-09-29\n' "$(grep -m1 -oE '\[[0-9]+\.[0-9]+\.[0-9]+\]' "$SCRIPT_DIR/../CHANGELOG.md" | tr -d '[]')" \
  > "$CASE_ROOT/fresh-root/skills/multi-agent-orchestration/CHANGELOG.md"
git init -q "$CASE_ROOT/fresh-root"
git -C "$CASE_ROOT/fresh-root" remote add origin "$CASE_ROOT/origin.git"
git -C "$CASE_ROOT/fresh-root" fetch -q origin
git -C "$CASE_ROOT/fresh-root" branch -M main 2>/dev/null || true
git -C "$CASE_ROOT/fresh-root" reset -q --soft origin/main 2>/dev/null || true
bash "$REMOTE" provision --node alpha --local-project "$CASE_ROOT/pm-project" --skip-clone \
  > "$CASE_ROOT/provision.out" 2>&1 && rc=$? || rc=$?
grep -q 'REGISTER_OK' "$CASE_ROOT/provision.out" && ok "provision 转发 ORCA 注册" || bad "provision 转发 ORCA 注册"
grep -q 'orca-register-project.py' "$MOCK_LOG" && ok "provision 调节点注册脚本" || bad "provision 调节点注册脚本"

printf '\n远程派发入口测试：%d passed, %d failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
