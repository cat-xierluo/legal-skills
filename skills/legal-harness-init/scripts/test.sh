#!/usr/bin/env bash
# legal-harness-init 的无网络回归测试。

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEST_ROOT=$(mktemp -d "/tmp/legal-harness-init-test.XXXXXX") || exit 1
case "$TEST_ROOT" in /tmp/legal-harness-init-test.*) ;; *) printf '不安全的测试目录：%s\n' "$TEST_ROOT" >&2; exit 1 ;; esac
trap 'rm -rf -- "$TEST_ROOT"' EXIT INT TERM

passed=0
failed=0
pass() { passed=$((passed + 1)); printf 'PASS %s\n' "$1"; }
fail() { failed=$((failed + 1)); printf 'FAIL %s\n' "$1" >&2; }
assert_contains() {
    local text="$1" pattern="$2" name="$3"
    if printf '%s' "$text" | grep -Fq "$pattern"; then pass "$name"; else fail "$name"; fi
}

mkdir -p "$TEST_ROOT/home" "$TEST_ROOT/only-docs/docs"
detect_only_docs=$(cd "$TEST_ROOT/only-docs" && HOME="$TEST_ROOT/home" bash "$SCRIPT_DIR/detect.sh" 2>/dev/null || true)
assert_contains "$detect_only_docs" '"project_init_ran": false' "仅有 docs 不误判 project-init"

detect_explicit=$(cd "$TEST_ROOT/only-docs" && HOME="$TEST_ROOT/home" bash "$SCRIPT_DIR/detect.sh" --runtime codex 2>/dev/null || true)
assert_contains "$detect_explicit" '"current_runtime": "codex"' "显式 runtime 优先"
assert_contains "$detect_explicit" '"current_runtime_source": "explicit"' "显式 runtime 保留证据"

detect_env=$(cd "$TEST_ROOT/only-docs" && HOME="$TEST_ROOT/home" CODEX_THREAD_ID=test bash "$SCRIPT_DIR/detect.sh" 2>/dev/null || true)
assert_contains "$detect_env" '"current_runtime": "codex"' "CODEX_THREAD_ID 可识别 Codex"
assert_contains "$detect_env" 'env:CODEX_THREAD_ID' "runtime 输出证据信号"

mkdir -p "$TEST_ROOT/project"
printf '# 用户区块\n' > "$TEST_ROOT/project/AGENTS.md"
printf '# 法律协作基线\n\n- 项目代号：LIT-001\n- 真实事实：见 .legal-context.local.md\n' > "$TEST_ROOT/content.md"
mkdir -p "$TEST_ROOT/clean-project"
clean_write=$(HOME="$TEST_ROOT/home" bash "$SCRIPT_DIR/write.sh" --content-file "$TEST_ROOT/content.md" --level project --platforms codex --project-dir "$TEST_ROOT/clean-project" --mode update --block-id legal-baseline --privacy-mode strict 2>/dev/null)
assert_contains "$clean_write" '"status":"written"' "干净项目创建 AGENTS.md"
if [ -s "$TEST_ROOT/clean-project/AGENTS.md" ]; then pass "干净创建产物非空"; else fail "干净创建产物非空"; fi
write_one=$(HOME="$TEST_ROOT/home" bash "$SCRIPT_DIR/write.sh" --content-file "$TEST_ROOT/content.md" --level project --platforms codex,openclaw --project-dir "$TEST_ROOT/project" --mode update --block-id legal-baseline --privacy-mode strict 2>/dev/null)
assert_contains "$write_one" '"platform":"codex,openclaw"' "同路径平台合并为单一目标"
schema_count=$(printf '%s' "$write_one" | grep -c '"schema_version"')
if [ "$schema_count" -eq 1 ]; then pass "write.sh stdout 仅含一个 JSON 文档"; else fail "write.sh stdout 仅含一个 JSON 文档"; fi
marker_count=$(grep -c '^<!-- legal-harness-init:legal-baseline:start -->$' "$TEST_ROOT/project/AGENTS.md")
if [ "$marker_count" -eq 1 ]; then pass "同路径只写一次"; else fail "同路径只写一次"; fi
if grep -Fq '# 用户区块' "$TEST_ROOT/project/AGENTS.md"; then pass "保留受管区块外用户内容"; else fail "保留受管区块外用户内容"; fi
sha_before=$(shasum -a 256 "$TEST_ROOT/project/AGENTS.md" | awk '{print $1}')
write_two=$(HOME="$TEST_ROOT/home" bash "$SCRIPT_DIR/write.sh" --content-file "$TEST_ROOT/content.md" --level project --platforms codex,openclaw --project-dir "$TEST_ROOT/project" --mode update --block-id legal-baseline --privacy-mode strict 2>/dev/null)
sha_after=$(shasum -a 256 "$TEST_ROOT/project/AGENTS.md" | awk '{print $1}')
assert_contains "$write_two" '"status":"unchanged"' "重复写入报告 unchanged"
if [ "$sha_before" = "$sha_after" ]; then pass "重复写入零 diff"; else fail "重复写入零 diff"; fi

mkdir -p "$TEST_ROOT/home/.codex"
printf 'ORIGINAL\n' > "$TEST_ROOT/home/.codex/AGENTS.md"
chmod 644 "$TEST_ROOT/home/.codex/AGENTS.md"
HOME="$TEST_ROOT/home" bash "$SCRIPT_DIR/write.sh" --content-file "$TEST_ROOT/content.md" --level user --platforms codex --mode update --block-id legal-baseline --privacy-mode strict >/dev/null 2>&1
target_mode=$(stat -f '%Lp' "$TEST_ROOT/home/.codex/AGENTS.md" 2>/dev/null || stat -c '%a' "$TEST_ROOT/home/.codex/AGENTS.md")
backup_mode=$(stat -f '%Lp' "$TEST_ROOT/home/.codex/AGENTS.md.bak.legal-harness-init" 2>/dev/null || stat -c '%a' "$TEST_ROOT/home/.codex/AGENTS.md.bak.legal-harness-init")
if [ "$target_mode" = 600 ] && [ "$backup_mode" = 600 ]; then pass "用户配置与备份权限 0600"; else fail "用户配置与备份权限 0600"; fi
HOME="$TEST_ROOT/home" bash "$SCRIPT_DIR/restore.sh" --target "$TEST_ROOT/home/.codex/AGENTS.md" >/dev/null
restored_mode=$(stat -f '%Lp' "$TEST_ROOT/home/.codex/AGENTS.md" 2>/dev/null || stat -c '%a' "$TEST_ROOT/home/.codex/AGENTS.md")
if [ "$(sed -n '1p' "$TEST_ROOT/home/.codex/AGENTS.md")" = ORIGINAL ] && [ "$restored_mode" = 644 ]; then pass "恢复首次原文与权限"; else fail "恢复首次原文与权限"; fi

printf 'CORRUPTED\n' >> "$TEST_ROOT/home/.codex/AGENTS.md.bak.legal-harness-init"
if HOME="$TEST_ROOT/home" bash "$SCRIPT_DIR/write.sh" --content-file "$TEST_ROOT/content.md" --level user --platforms codex --mode update --block-id legal-baseline --privacy-mode strict >/dev/null 2>&1; then fail "原始备份损坏时拒绝继续更新"; else pass "原始备份损坏时拒绝继续更新"; fi

mkdir -p "$TEST_ROOT/home/.claude"
printf 'ORIGINAL\n' > "$TEST_ROOT/home/.claude/CLAUDE.md"
HOME="$TEST_ROOT/home" bash "$SCRIPT_DIR/write.sh" --content-file "$TEST_ROOT/content.md" --level user --platforms claude-code --mode update --block-id legal-baseline --privacy-mode strict >/dev/null 2>&1
unlink "$TEST_ROOT/home/.claude/CLAUDE.md.bak.legal-harness-init"
ln -s "$TEST_ROOT/home/.claude/missing-original" "$TEST_ROOT/home/.claude/CLAUDE.md.bak.legal-harness-init"
printf '\n- 变更：用于触发真实更新路径\n' >> "$TEST_ROOT/content.md"
if HOME="$TEST_ROOT/home" bash "$SCRIPT_DIR/write.sh" --content-file "$TEST_ROOT/content.md" --level user --platforms claude-code --mode update --block-id legal-baseline --privacy-mode strict >/dev/null 2>&1; then fail "原始备份为损坏符号链接时拒绝更新"; else pass "原始备份为损坏符号链接时拒绝更新"; fi

printf '%s\n' '- 案号：(2026)沪0101民初123号' > "$TEST_ROOT/sensitive.md"
if bash "$SCRIPT_DIR/validate-content.sh" --file "$TEST_ROOT/sensitive.md" --privacy-mode strict >/dev/null 2>&1; then fail "strict 拒绝真实案号"; else pass "strict 拒绝真实案号"; fi
if bash "$SCRIPT_DIR/validate-content.sh" --file "$TEST_ROOT/sensitive.md" --privacy-mode team >/dev/null 2>&1; then fail "team 配置仍拒绝直接写真实案号"; else pass "team 配置仍拒绝直接写真实案号"; fi

mkdir -p "$TEST_ROOT/broken"
printf '%s\n' '<!-- legal-harness-init:legal-baseline:start -->' '残缺区块' > "$TEST_ROOT/broken/AGENTS.md"
if HOME="$TEST_ROOT/home" bash "$SCRIPT_DIR/write.sh" --content-file "$TEST_ROOT/content.md" --level project --platforms codex --project-dir "$TEST_ROOT/broken" --mode update --block-id legal-baseline --privacy-mode strict >/dev/null 2>&1; then fail "残缺 marker 拒绝写入"; else pass "残缺 marker 拒绝写入"; fi

mkdir -p "$TEST_ROOT/crossed"
printf '%s\n' \
  '<!-- legal-harness-init:m1-role:start -->' \
  '<!-- legal-harness-init:m2-workflow:start -->' \
  '<!-- legal-harness-init:m1-role:end -->' \
  '<!-- legal-harness-init:m2-workflow:end -->' > "$TEST_ROOT/crossed/AGENTS.md"
if HOME="$TEST_ROOT/home" bash "$SCRIPT_DIR/write.sh" --content-file "$TEST_ROOT/content.md" --level project --platforms codex --project-dir "$TEST_ROOT/crossed" --mode update --block-id legal-baseline --privacy-mode strict >/dev/null 2>&1; then fail "交叉 marker 拒绝写入"; else pass "交叉 marker 拒绝写入"; fi

mkdir -p "$TEST_ROOT/malformed"
printf '%s\n' '<!-- legal-harness-init:m1-role:start -- >' '畸形区块' > "$TEST_ROOT/malformed/AGENTS.md"
if HOME="$TEST_ROOT/home" bash "$SCRIPT_DIR/write.sh" --content-file "$TEST_ROOT/content.md" --level project --platforms codex --project-dir "$TEST_ROOT/malformed" --mode update --block-id legal-baseline --privacy-mode strict >/dev/null 2>&1; then fail "畸形 marker 前缀拒绝写入"; else pass "畸形 marker 前缀拒绝写入"; fi

verify_output=$(bash "$SCRIPT_DIR/verify.sh" --target "$TEST_ROOT/project/AGENTS.md" --block-id legal-baseline)
assert_contains "$verify_output" '"status":"CONFIG_WRITTEN"' "无新会话证据只报告 CONFIG_WRITTEN"

cat > "$TEST_ROOT/session-evidence.txt" <<EOF
new_session=true
loaded=true
source_path=$TEST_ROOT/missing/AGENTS.md
config_sha256=not-a-current-hash
probe_permission=pass
probe_confidentiality=pass
probe_information_gap=pass
probe_traceability=pass
EOF
fake_verify_file="$TEST_ROOT/fake-verify.json"
bash "$SCRIPT_DIR/verify.sh" --target "$TEST_ROOT/missing/AGENTS.md" --block-id legal-baseline --session-evidence "$TEST_ROOT/session-evidence.txt" >"$fake_verify_file" 2>/dev/null
fake_verify_rc=$?
fake_verify=$(cat "$fake_verify_file")
if [ "$fake_verify_rc" -eq 1 ] && printf '%s' "$fake_verify" | grep -Fq '"status":"NOT_VERIFIED"'; then pass "配置不存在时伪 evidence 不得升级状态"; else fail "配置不存在时伪 evidence 不得升级状态"; fi

cat > "$TEST_ROOT/session-evidence.txt" <<EOF
new_session=true
loaded=true
source_path=$TEST_ROOT/project/AGENTS.md
config_sha256=stale-hash
probe_permission=pass
probe_confidentiality=pass
probe_information_gap=pass
probe_traceability=pass
EOF
stale_output=$(bash "$SCRIPT_DIR/verify.sh" --target "$TEST_ROOT/project/AGENTS.md" --block-id legal-baseline --session-evidence "$TEST_ROOT/session-evidence.txt")
assert_contains "$stale_output" '"status":"CONFIG_WRITTEN"' "旧配置哈希证据不得升级状态"

project_sha=$(shasum -a 256 "$TEST_ROOT/project/AGENTS.md" | awk '{print $1}')
cat > "$TEST_ROOT/session-evidence.txt" <<EOF
new_session=true
loaded=true
source_path=$TEST_ROOT/project/AGENTS.md
config_sha256=$project_sha
probe_permission=pass
probe_confidentiality=pass
probe_information_gap=pass
probe_traceability=pass
EOF
verified_output=$(bash "$SCRIPT_DIR/verify.sh" --target "$TEST_ROOT/project/AGENTS.md" --block-id legal-baseline --session-evidence "$TEST_ROOT/session-evidence.txt")
assert_contains "$verified_output" '"status":"BEHAVIOR_VERIFIED"' "配置与四类证据齐备时升级 BEHAVIOR_VERIFIED"

printf '结果：%s 通过，%s 失败\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
