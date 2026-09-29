#!/usr/bin/env bash
# test-remote-node-probe.sh — 远程节点探测测试（mock ssh，零真实网络）。
# mock ssh 把远端命令就地执行在本地 fixture 上：git/CHANGELOG 走真实文件系统，
# load/内存/磁盘取本机真值（门限用参数控制，保证确定性）。
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CASE_ROOT=$(mktemp -d)
trap 'rm -rf "$CASE_ROOT"' EXIT

passed=0
failed=0
ok() { printf 'PASS: %s\n' "$1"; passed=$((passed + 1)); }
bad() { printf 'FAIL: %s\n' "$1" >&2; failed=$((failed + 1)); }
run_probe() { # run_probe <expected-rc> <label> <args...>
  local expected="$1" label="$2"; shift 2
  python3 "$SCRIPT_DIR/remote-node-probe.py" "$@" >/dev/null 2>&1 && rc=$? || rc=$?
  if [ "$rc" -eq "$expected" ]; then ok "$label"; else bad "$label (expect rc=$expected got rc=$rc)"; fi
}

# mock ssh：剥掉 -o 选项后，首个非选项当 alias（dead-host 模拟不可达），其余整体交给 bash -c
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
[ "${args[0]}" = "dead-host" ] && { echo "ssh: connect refused" >&2; exit 255; }
exec bash -c "${args[*]:1}"
EOF
chmod +x "$CASE_ROOT/bin/mock-ssh"

# fixture：本地裸 origin + clone + skill 版本文件（版本与 PM 侧同源即相等）
git init -q --bare "$CASE_ROOT/origin.git"
git clone -q "$CASE_ROOT/origin.git" "$CASE_ROOT/node-root"
git -C "$CASE_ROOT/node-root" commit -q --allow-empty -m "base"
git -C "$CASE_ROOT/node-root" branch -M main
git -C "$CASE_ROOT/node-root" push -q origin main
FIXTURE_SKILL="$CASE_ROOT/node-root/skills/multi-agent-orchestration"
mkdir -p "$FIXTURE_SKILL"
printf '## [9.9.9] - 2026-09-29\n' > "$FIXTURE_SKILL/CHANGELOG.md"
PM_VERSION=$(grep -m1 -oE '\[[0-9]+\.[0-9]+\.[0-9]+\]' "$SCRIPT_DIR/../CHANGELOG.md" | tr -d '[]')
NODE_SHA=$(git -C "$CASE_ROOT/node-root" rev-parse origin/main)

cat > "$CASE_ROOT/personal.json" <<EOF
{
  "remote_nodes": {
    "node-a": {
      "enabled": true,
      "ssh_alias": "any-host",
      "remote_root": "$CASE_ROOT/node-root",
      "skill_root": "$FIXTURE_SKILL",
      "load_threshold": 6.0,
      "active_session_cap": 4,
      "min_free_disk_gb": 20,
      "connect_timeout_seconds": 5
    },
    "node-off": { "enabled": false, "ssh_alias": "any-host", "remote_root": "$CASE_ROOT/node-root", "skill_root": "$FIXTURE_SKILL" },
    "node-dead": { "enabled": true, "ssh_alias": "dead-host", "remote_root": "$CASE_ROOT/node-root", "skill_root": "$FIXTURE_SKILL" }
  }
}
EOF
SSH_MOCK="$CASE_ROOT/bin/mock-ssh"

# 1) ok：全字段通过（容量门限放宽保证确定性；基线/版本真实比对）
out=$(python3 "$SCRIPT_DIR/remote-node-probe.py" --node node-a --config "$CASE_ROOT/personal.json" \
  --ssh-command "$SSH_MOCK" --load-threshold 999 --active-session-cap 999 --min-free-disk-gb 0 --min-free-memory-percent 0 \
  --expect-base-sha "$NODE_SHA" --expect-skill-version 9.9.9) && rc=$? || rc=$?
[ "$rc" -eq 0 ] && ok "ok 全门通过" || bad "ok 全门通过 (rc=$rc)"
[ "$(printf '%s' "$out" | jq -r .status)" = "ok" ] && ok "输出 schema status=ok" || bad "输出 schema status=ok"
[ "$(printf '%s' "$out" | jq -r '.git.origin_main_sha')" = "$NODE_SHA" ] && ok "节点 origin/main SHA 采集" || bad "节点 origin/main SHA 采集"
[ -n "$(printf '%s' "$out" | jq -r '.runtime.claude_path // empty')" ] && ok "claude 路径采集（登录 shell）" || bad "claude 路径采集"

# 2) 不可达 → 65
run_probe 65 "不可达 → 65" --node node-dead --config "$CASE_ROOT/personal.json" --ssh-command "$SSH_MOCK"
# 3) 节点未配置 → 64
run_probe 64 "节点未配置 → 64" --node ghost --config "$CASE_ROOT/personal.json" --ssh-command "$SSH_MOCK"
# 4) enabled=false → 3
run_probe 3 "enabled=false → 3" --node node-off --config "$CASE_ROOT/personal.json" --ssh-command "$SSH_MOCK"
# 5) load 门 → 4
run_probe 4 "load15 超限 → 4" --node node-a --config "$CASE_ROOT/personal.json" --ssh-command "$SSH_MOCK" \
  --load-threshold 0.01 --active-session-cap 999 --skip-fetch
# 6) 活跃会话门 → 4
run_probe 4 "活跃会话超限 → 4" --node node-a --config "$CASE_ROOT/personal.json" --ssh-command "$SSH_MOCK" \
  --load-threshold 999 --active-session-cap 0 --skip-fetch
# 7) 基线不匹配 → 3
run_probe 3 "基线不匹配 → 3" --node node-a --config "$CASE_ROOT/personal.json" --ssh-command "$SSH_MOCK" \
  --load-threshold 999 --active-session-cap 999 --min-free-disk-gb 0 --min-free-memory-percent 0 --skip-fetch --expect-base-sha 0000000000000000000000000000000000000000
# 8) 版本不匹配 → 3
run_probe 3 "skill 版本不一致 → 3" --node node-a --config "$CASE_ROOT/personal.json" --ssh-command "$SSH_MOCK" \
  --load-threshold 999 --active-session-cap 999 --min-free-disk-gb 0 --min-free-memory-percent 0 --skip-fetch --expect-skill-version 0.0.1
# 9) remote_root 缺失 → 3
sed "s|\"remote_root\": \"$CASE_ROOT/node-root\"|\"remote_root\": \"$CASE_ROOT/no-such-root\"|" \
  "$CASE_ROOT/personal.json" > "$CASE_ROOT/personal-missing.json"
run_probe 3 "remote_root 缺失 → 3" --node node-a --config "$CASE_ROOT/personal-missing.json" --ssh-command "$SSH_MOCK" \
  --load-threshold 999 --active-session-cap 999 --min-free-disk-gb 0 --min-free-memory-percent 0 --skip-fetch
# 10) 真实 fetch（本地裸仓）+ 全通过
run_probe 0 "真实 fetch 基线一致 → 0" --node node-a --config "$CASE_ROOT/personal.json" --ssh-command "$SSH_MOCK" \
  --load-threshold 999 --active-session-cap 999 --min-free-disk-gb 0 --min-free-memory-percent 0 --expect-base-sha "$NODE_SHA" --expect-skill-version 9.9.9

printf '\n远程节点探测测试：%d passed, %d failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
