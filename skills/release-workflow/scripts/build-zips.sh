#!/usr/bin/env bash
set -euo pipefail

# build-zips.sh — 遍历 skills/ 给每个 skill 打 zip
# 用法: build-zips.sh [REPO_TAG]
# 输入: skills/<name>/(每个含 SKILL.md + CHANGELOG.md)
# 输出: pack-skills/<skill>-<semver>.zip

REPO_TAG="${1:-v$(date +%Y.%m.%d)}"
SKILLS_ROOT="${SKILLS_ROOT:-skills}"
OUTPUT_DIR="${OUTPUT_DIR:-pack-skills}"

mkdir -p "$OUTPUT_DIR"

# 跳过 symlink 与已归档 skill
SKIP_SYMLINK="${SKIP_SYMLINK:-1}"
# 归档/废弃 skill 列表:通过环境变量 SKIP_ARCHIVED 注入(空格分隔),
# 例: SKIP_ARCHIVED="skill-architect repo-research" bash build-zips.sh
# 默认空(不自动跳过任何 skill,完全由调用方决定)。
IFS=' ' read -ra SKIP_ARCHIVED <<< "${SKIP_ARCHIVED:-}"

count=0
for skill_dir in "$SKILLS_ROOT"/*/; do
    [ -d "$skill_dir" ] || continue

    skill_name=$(basename "$skill_dir")

    # 注意: -L 对带尾斜杠的路径返回 false,要去掉斜杠再测
    if [ "$SKIP_SYMLINK" = 1 ] && [ -L "${skill_dir%/}" ]; then
        echo "skip symlink: $skill_name"
        continue
    fi

    skip_archived=false
    for archived in "${SKIP_ARCHIVED[@]}"; do
        # 支持精确匹配 + 通配符(如 archived/* 匹配 archived/foo)
        # 空字符串(未设置 SKIP_ARCHIVED)直接跳过
        [ -z "$archived" ] && continue
        if [ "$skill_name" = "$archived" ] || [[ "$skill_name" == $archived ]]; then
            echo "skip archived: $skill_name"
            skip_archived=true
            break
        fi
    done
    if $skip_archived; then
        continue
    fi

    # 从 CHANGELOG.md 头部读 semver,支持 4 种格式:
    #   ## [X.Y.Z] - YYYY-MM-DD       (主流,带方括号)
    #   ## [vX.Y.Z] - YYYY-MM-DD      (方括号 + v 前缀,如 svg-book-illustrator)
    #   ## vX.Y.Z (YYYY-MM-DD)        (无方括号 + v,如 img2pdf)
    #   ## X.Y.Z - YYYY-MM-DD         (无 v 无方括号)
    changelog="$skill_dir/CHANGELOG.md"
    if [ ! -f "$changelog" ]; then
        echo "skip no-changelog: $skill_name"
        continue
    fi
    # 第一步:匹配形如 "## [vX.Y.Z]" 或 "## vX.Y.Z" 或 "## [X.Y.Z]" 或 "## X.Y.Z"
    version_line=$(grep -m1 -oE '## \[?v?[0-9]+\.[0-9]+\.[0-9]+\]?' "$changelog" || true)
    # 第二步:从匹配行里提取纯 X.Y.Z
    semver=$(echo "$version_line" | grep -oE 'v?[0-9]+\.[0-9]+\.[0-9]+' | head -1 | sed 's/^v//')
    if [ -z "$semver" ]; then
        echo "skip no-version: $skill_name"
        continue
    fi

    zip_name="${skill_name}-${semver}.zip"
    echo "build: $skill_name → $zip_name"

    # 三步打包法:
    #   1. git archive 输出 tar 流(paths 是 skills/<name>/...)
    #   2. tar -x --strip-components=1 抽出,去掉 skills/ 前缀
    #   3. 在 staging 目录 zip 打包
    # 效果:zip 内路径是 <name>/<files>,用户解压后直接得到 <name>/ 文件夹,
    # 复制到目标 skills/ 目录即可,不需要再剥一层。
    STAGING=$(mktemp -d)
    git archive HEAD --worktree-attributes -- "$skill_dir" \
        | tar -x -C "$STAGING" --strip-components=1
    (cd "$STAGING" && zip -rq "$OLDPWD/$OUTPUT_DIR/$zip_name" "$skill_name")
    rm -rf "$STAGING"
    count=$((count + 1))
done

echo "done: $count zips in $OUTPUT_DIR/ (tag: $REPO_TAG)"