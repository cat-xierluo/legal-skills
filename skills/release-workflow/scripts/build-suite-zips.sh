#!/usr/bin/env bash
set -euo pipefail

# build-suite-zips.sh — 校验 expert-suites/ 并把成员符号链接展开为自包含 ZIP
# 用法: build-suite-zips.sh [REPO_TAG]
# 输入: expert-suites/<suite>/{README.md,CHANGELOG.md,LICENSE.txt,skills/* symlink}
# 输出: pack-skills/suite-<suite>-<semver>.zip

REPO_TAG="${1:-v$(date +%Y.%m.%d)}"
EXPERT_SUITES_ROOT="${EXPERT_SUITES_ROOT:-expert-suites}"
OUTPUT_DIR="${OUTPUT_DIR:-pack-skills}"
SOURCE_REF="${SOURCE_REF:-HEAD}"

if [[ ! "$REPO_TAG" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "ERROR: 非法 release tag: $REPO_TAG" >&2
    exit 1
fi
validate_repo_relative_dir() {
    local label="$1"
    local value="$2"
    if [[ -z "$value" || "$value" = /* ]]; then
        echo "ERROR: $label 必须是仓库内非空相对路径: $value" >&2
        exit 1
    fi
    case "/$value/" in
        *"/../"*|*"/./"*|*"//"*)
            echo "ERROR: $label 不得含路径逃逸或空路径段: $value" >&2
            exit 1
            ;;
    esac
}

validate_repo_relative_dir "EXPERT_SUITES_ROOT" "$EXPERT_SUITES_ROOT"
validate_repo_relative_dir "OUTPUT_DIR" "$OUTPUT_DIR"

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

git rev-parse --verify "${SOURCE_REF}^{tree}" >/dev/null
python3 skills/release-workflow/scripts/validate-expert-suites.py \
    --repo-root "$ROOT" \
    --suite-root "$ROOT/$EXPERT_SUITES_ROOT"

BATCH_DIR="$(mktemp -d /tmp/legal-skills-suite-build.XXXXXX)"
cleanup() {
    case "$BATCH_DIR" in
        /tmp/legal-skills-suite-build.*|/private/tmp/legal-skills-suite-build.*) rm -rf "$BATCH_DIR" ;;
        *) echo "WARN: 拒绝清理非临时路径: $BATCH_DIR" >&2 ;;
    esac
}
trap cleanup EXIT
mkdir -p "$BATCH_DIR/final"

suite_count=0
membership_count=0
for suite_dir in "$EXPERT_SUITES_ROOT"/*; do
    [ -d "$suite_dir" ] || continue
    suite_id="$(basename "$suite_dir")"
    changelog="$suite_dir/CHANGELOG.md"
    version_line="$(grep -m1 -oE '## \[?v?[0-9]+\.[0-9]+\.[0-9]+\]?' "$changelog")"
    version="$(printf '%s' "$version_line" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"
    zip_name="suite-${suite_id}-${version}.zip"

    export_dir="$BATCH_DIR/export-$suite_id"
    stage_parent="$BATCH_DIR/stage-$suite_id"
    stage_suite="$stage_parent/$suite_id"
    mkdir -p "$export_dir" "$stage_suite/skills"

    git archive "$SOURCE_REF" --worktree-attributes -- \
        "$suite_dir/README.md" \
        "$suite_dir/CHANGELOG.md" \
        "$suite_dir/LICENSE.txt" \
        | tar -x -C "$export_dir"
    for outer_file in README.md CHANGELOG.md LICENSE.txt; do
        mv "$export_dir/$suite_dir/$outer_file" "$stage_suite/$outer_file"
    done

    member_count=0
    for member_link in "$suite_dir"/skills/*; do
        [ -L "$member_link" ] || {
            echo "ERROR: 非符号链接成员: $member_link" >&2
            exit 1
        }
        skill_id="$(basename "$member_link")"
        member_export="$BATCH_DIR/member-$suite_id-$skill_id"
        mkdir -p "$member_export"
        git archive "$SOURCE_REF" --worktree-attributes -- "skills/$skill_id" \
            | tar -x -C "$member_export"
        [ -d "$member_export/skills/$skill_id" ] || {
            echo "ERROR: $SOURCE_REF 不含 skills/$skill_id" >&2
            exit 1
        }
        mv "$member_export/skills/$skill_id" "$stage_suite/skills/$skill_id"
        member_count=$((member_count + 1))
    done

    # ZIP 内使用本次 tag 的精确下载链接；仓库源码继续保留 releases/latest 占位。
    python3 - "$stage_suite/README.md" "$REPO_TAG" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
tag = sys.argv[2]
text = path.read_text(encoding="utf-8")
text = text.replace("/releases/latest/download/", f"/releases/download/{tag}/")
path.write_text(text, encoding="utf-8")
PY

    if find "$stage_suite" -type l -print -quit | grep -q .; then
        echo "ERROR: staging 中仍存在符号链接: $suite_id" >&2
        exit 1
    fi
    sensitive="$(find "$stage_suite" -type f \( \
        -name '.env' -o -name '.env.*' -o -name '*.pem' -o -name '*.key' \
        -o -name 'credentials.json' -o -name 'secrets.yaml' -o -name '*.db' \
        -o -name '*.sqlite' -o -name '*.sqlite3' \) -print -quit)"
    if [ -n "$sensitive" ]; then
        echo "ERROR: staging 中发现敏感或运行时文件: $sensitive" >&2
        exit 1
    fi

    tmp_zip="$BATCH_DIR/final/$zip_name"
    (cd "$stage_parent" && zip -rq "$tmp_zip" "$suite_id")
    unzip -tq "$tmp_zip" >/dev/null

    skill_dirs="$(find "$stage_suite/skills" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
    [ "$skill_dirs" -eq "$member_count" ] || {
        echo "ERROR: $suite_id 解包成员数不一致: expected=$member_count actual=$skill_dirs" >&2
        exit 1
    }
    echo "build suite: $suite_id v$version → $zip_name ($member_count members)"
    suite_count=$((suite_count + 1))
    membership_count=$((membership_count + member_count))
done

[ "$suite_count" -gt 0 ] || {
    echo "ERROR: 没有可构建的专家套件" >&2
    exit 1
}

mkdir -p "$OUTPUT_DIR"
# 全部套件成功后再替换旧套件产物，避免半批次覆盖。
find "$OUTPUT_DIR" -mindepth 1 -maxdepth 1 -type f -name 'suite-*.zip' -delete
for built_zip in "$BATCH_DIR"/final/suite-*.zip; do
    mv "$built_zip" "$OUTPUT_DIR/"
done

echo "done: $suite_count suite zips, $membership_count memberships in $OUTPUT_DIR/ (tag: $REPO_TAG, source: $SOURCE_REF)"
