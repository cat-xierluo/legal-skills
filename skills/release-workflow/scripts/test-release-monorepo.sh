#!/usr/bin/env bash
# test-release-monorepo.sh — release-monorepo.sh 驱动的回归测试
# 覆盖：变量展开边界、构建失败保留上一批产物、同标识旧版本替换、未知文件保留、
# 输出目录为符号链接时拒绝写入。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER="$SCRIPT_DIR/release-monorepo.sh"
WORK="$(mktemp -d /tmp/release-monorepo-test.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "ok - $*"; }

# ---------- 1. 资产数输出行的变量展开 ----------
# 历史缺陷：`$release_asset_count（含…` 与 `$suite_zip_count）` 在 set -u 下
# 会把紧邻的多字节字符并入变量名，导致未绑定变量退出 127。
line="$(grep -n 'echo "assets: ' "$DRIVER" | head -1 | cut -d: -f2-)"
[ -n "$line" ] || fail "找不到资产数输出行"
out="$(release_asset_count=79 suite_zip_count=8 bash -u -c "set -u; $line" 2>&1)" \
    || fail "资产数输出行在 bash -u 下失败: $out"
[ "$out" = "assets: 79（含专家套件 8）" ] || fail "资产数输出错误: $out"
pass "资产数输出行在 bash -u 下正确展开"

# ---------- 准备一个隔离的仓库骨架 ----------
make_repo() {
    local dir="$1"
    mkdir -p "$dir/skills/release-workflow/scripts"
    cp "$DRIVER" "$dir/skills/release-workflow/scripts/release-monorepo.sh"
    chmod +x "$dir/skills/release-workflow/scripts/release-monorepo.sh"
    cat >"$dir/skills/release-workflow/scripts/build-stub-ok.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$OUTPUT_DIR"
printf 'skill payload\n' >"$OUTPUT_DIR/skill-1.0.0.zip"
printf 'other payload\n' >"$OUTPUT_DIR/other-2.3.4.zip"
STUB
    cat >"$dir/skills/release-workflow/scripts/build-stub-suite.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$OUTPUT_DIR"
printf 'suite payload\n' >"$OUTPUT_DIR/suite-demo-suite-0.1.0.zip"
STUB
    cat >"$dir/skills/release-workflow/scripts/build-stub-fail.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
exit 31
STUB
    chmod +x "$dir"/skills/release-workflow/scripts/build-stub-*.sh
}

# ---------- 2. 构建失败保留上一批产物 ----------
repo="$WORK/fail-repo"
make_repo "$repo"
mkdir -p "$repo/pack-skills"
printf 'old batch\n' >"$repo/pack-skills/skill-0.9.0.zip"
printf 'unknown\n' >"$repo/pack-skills/backup.zip"
set +e
(cd "$repo" && RELEASE_OUTPUT_DIR=pack-skills \
    BUILD_SKILL_ZIPS=skills/release-workflow/scripts/build-stub-fail.sh \
    BUILD_SUITE_ZIPS=skills/release-workflow/scripts/build-stub-suite.sh \
    bash skills/release-workflow/scripts/release-monorepo.sh v2099.01.01 --dry-run) \
    >"$WORK/fail.log" 2>&1
status=$?
set -e
[ "$status" -ne 0 ] || fail "构建失败时驱动应当非零退出"
[ -f "$repo/pack-skills/skill-0.9.0.zip" ] || fail "构建失败后上一批产物被删除"
[ -f "$repo/pack-skills/backup.zip" ] || fail "构建失败后未知文件被删除"
pass "构建失败保留上一批产物与未知文件"

# ---------- 3. 成功时替换同标识旧版本，保留未知文件 ----------
repo="$WORK/ok-repo"
make_repo "$repo"
mkdir -p "$repo/pack-skills"
printf 'old batch\n' >"$repo/pack-skills/skill-0.9.0.zip"
printf 'unknown\n' >"$repo/pack-skills/backup.zip"
printf 'note\n' >"$repo/pack-skills/notes.txt"
(cd "$repo" && RELEASE_OUTPUT_DIR=pack-skills \
    BUILD_SKILL_ZIPS=skills/release-workflow/scripts/build-stub-ok.sh \
    BUILD_SUITE_ZIPS=skills/release-workflow/scripts/build-stub-suite.sh \
    bash skills/release-workflow/scripts/release-monorepo.sh v2099.01.01 --dry-run) \
    >"$WORK/ok.log" 2>&1 || fail "dry-run 失败: $(cat "$WORK/ok.log")"
[ -f "$repo/pack-skills/skill-1.0.0.zip" ] || fail "新资产未写入"
[ -f "$repo/pack-skills/suite-demo-suite-0.1.0.zip" ] || fail "套件资产未写入"
[ ! -f "$repo/pack-skills/skill-0.9.0.zip" ] || fail "同标识旧版本未清理"
[ -f "$repo/pack-skills/backup.zip" ] || fail "未知 ZIP 被误删"
[ -f "$repo/pack-skills/notes.txt" ] || fail "非 ZIP 文件被误删"
[ ! -d "$repo/pack-skills/.staging" ] || fail "临时目录未清理"
pass "成功时替换同标识旧版本并保留未知文件"

# ---------- 4. 输出目录是符号链接时拒绝写入 ----------
repo="$WORK/link-repo"
make_repo "$repo"
mkdir -p "$WORK/link-target"
ln -s "$WORK/link-target" "$repo/pack-skills"
set +e
(cd "$repo" && RELEASE_OUTPUT_DIR=pack-skills \
    BUILD_SKILL_ZIPS=skills/release-workflow/scripts/build-stub-ok.sh \
    BUILD_SUITE_ZIPS=skills/release-workflow/scripts/build-stub-suite.sh \
    bash skills/release-workflow/scripts/release-monorepo.sh v2099.01.01 --dry-run) \
    >"$WORK/link.log" 2>&1
status=$?
set -e
[ "$status" -ne 0 ] || fail "符号链接输出目录应当被拒绝"
grep -q '符号链接' "$WORK/link.log" || fail "缺少符号链接拒绝说明"
[ -z "$(ls -A "$WORK/link-target")" ] || fail "沿符号链接写入了产物"
pass "输出目录为符号链接时拒绝写入"

echo "ALL_RELEASE_MONOREPO_TESTS_PASSED"
