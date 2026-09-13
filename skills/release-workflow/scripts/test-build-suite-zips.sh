#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

python3 skills/release-workflow/scripts/test_validate_expert_suites.py
python3 skills/release-workflow/scripts/test_update_readme.py

FIXTURE="$(mktemp -d /tmp/legal-skills-suite-test.XXXXXX)"
cleanup() {
    case "$FIXTURE" in
        /tmp/legal-skills-suite-test.*|/private/tmp/legal-skills-suite-test.*) rm -rf "$FIXTURE" ;;
        *) echo "WARN: 拒绝清理非临时路径: $FIXTURE" >&2 ;;
    esac
}
trap cleanup EXIT

mkdir -p \
    "$FIXTURE/skills/release-workflow/scripts" \
    "$FIXTURE/skills/alpha-skill" \
    "$FIXTURE/expert-suites/demo-suite/skills"
cp skills/release-workflow/scripts/validate-expert-suites.py \
    skills/release-workflow/scripts/build-suite-zips.sh \
    "$FIXTURE/skills/release-workflow/scripts/"

cat >"$FIXTURE/skills/alpha-skill/SKILL.md" <<'EOF'
---
name: alpha-skill
license: MIT
---

# Alpha
EOF
cat >"$FIXTURE/skills/alpha-skill/CHANGELOG.md" <<'EOF'
# 变更日志

## [1.2.3] - 2026-09-13
EOF
cat >"$FIXTURE/skills/alpha-skill/LICENSE.txt" <<'EOF'
MIT License
EOF
cat >"$FIXTURE/expert-suites/demo-suite/README.md" <<'EOF'
# Demo Suite

> [下载完整专家套件](https://github.com/cat-xierluo/legal-skills/releases/latest/download/suite-demo-suite-0.1.0.zip)

## 包含的 Skills

| Skill | 在本套件中的作用 | 单独下载 |
| :--- | :--- | :--- |
| [alpha-skill](../../skills/alpha-skill/) | 示例成员 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/alpha-skill-1.2.3.zip) |
EOF
cat >"$FIXTURE/expert-suites/demo-suite/CHANGELOG.md" <<'EOF'
# 变更日志

## [0.1.0] - 2026-09-13
EOF
cat >"$FIXTURE/expert-suites/demo-suite/LICENSE.txt" <<'EOF'
MIT License
EOF
ln -s ../../../skills/alpha-skill \
    "$FIXTURE/expert-suites/demo-suite/skills/alpha-skill"

git -C "$FIXTURE" init -q
git -C "$FIXTURE" add \
    expert-suites \
    skills/alpha-skill \
    skills/release-workflow/scripts
git -C "$FIXTURE" \
    -c user.name='Expert Suite Test' \
    -c user.email='expert-suite-test@example.invalid' \
    commit -qm 'test: fixture'

OUTPUT_DIR=pack-skills \
    bash "$FIXTURE/skills/release-workflow/scripts/build-suite-zips.sh" v2099.01.02
ZIP="$FIXTURE/pack-skills/suite-demo-suite-0.1.0.zip"
[ -f "$ZIP" ]
unzip -tq "$ZIP" >/dev/null

EXTRACT="$FIXTURE/extracted"
mkdir -p "$EXTRACT"
unzip -q "$ZIP" -d "$EXTRACT"
[ -f "$EXTRACT/demo-suite/README.md" ]
[ -f "$EXTRACT/demo-suite/CHANGELOG.md" ]
[ -f "$EXTRACT/demo-suite/LICENSE.txt" ]
[ -f "$EXTRACT/demo-suite/skills/alpha-skill/SKILL.md" ]
[ -f "$EXTRACT/demo-suite/skills/alpha-skill/LICENSE.txt" ]
[ -z "$(find "$EXTRACT/demo-suite" -type l -print -quit)" ]
grep -q '/releases/download/v2099.01.02/' "$EXTRACT/demo-suite/README.md"
if OUTPUT_DIR=../escaped-output \
    bash "$FIXTURE/skills/release-workflow/scripts/build-suite-zips.sh" v2099.01.02 \
    >"$FIXTURE/path-escape.log" 2>&1; then
    echo "ERROR: OUTPUT_DIR 路径逃逸未被拒绝" >&2
    exit 1
fi
test ! -e "$FIXTURE/escaped-output"
if find "$EXTRACT/demo-suite" -name 'suite.yaml' -o -name 'suite.yml' | grep -q .; then
    echo "ERROR: ZIP 不应包含 suite YAML" >&2
    exit 1
fi

BEFORE_HASH="$(shasum -a 256 "$ZIP" | awk '{print $1}')"
rm "$FIXTURE/expert-suites/demo-suite/skills/alpha-skill"
ln -s ../../../skills/missing-skill \
    "$FIXTURE/expert-suites/demo-suite/skills/alpha-skill"
if OUTPUT_DIR=pack-skills \
    bash "$FIXTURE/skills/release-workflow/scripts/build-suite-zips.sh" v2099.01.02 \
    >"$FIXTURE/expected-failure.log" 2>&1; then
    echo "ERROR: 损坏链接应阻断构建" >&2
    exit 1
fi
AFTER_HASH="$(shasum -a 256 "$ZIP" | awk '{print $1}')"
[ "$BEFORE_HASH" = "$AFTER_HASH" ] || {
    echo "ERROR: 失败构建覆盖了上一份完整产物" >&2
    exit 1
}

echo "PASS: expert-suite build, expansion, exact-tag README, path safety and rollback safety"
