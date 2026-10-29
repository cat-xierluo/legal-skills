#!/usr/bin/env bash
set -euo pipefail

# release-monorepo.sh — monorepo Skill 与专家套件发布驱动
# 用法: release-monorepo.sh [REPO_TAG] [--dry-run]
# dry-run 只构建本地产物，不创建 tag、不联网、不修改 README。
# 正式发布前必须由使用者完成 Release 五问并设置 RELEASE_CONFIRMED=1。
#
# 产物策略：整批资产先构建到临时目录，全部校验通过后才替换 pack-skills/ 里的
# 上一批。构建失败不会破坏已有产物；替换只清理同技能的过期版本，保留与本次
# 发布无关的未知文件。pack-skills 本身是符号链接时直接拒绝，不沿链接写入。

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

PACK_DIR="${RELEASE_OUTPUT_DIR:-pack-skills}"
STAGE_DIR="$PACK_DIR/.staging"
BUILD_SKILL_ZIPS="${BUILD_SKILL_ZIPS:-skills/release-workflow/scripts/build-zips.sh}"
BUILD_SUITE_ZIPS="${BUILD_SUITE_ZIPS:-skills/release-workflow/scripts/build-suite-zips.sh}"

asset_slug() {
    # 去掉 .zip 与结尾版本号，得到技能/套件标识（如 legal-ocr、suite-demo-suite）
    printf '%s' "$1" | sed -E 's/\.zip$//; s/-[0-9]+(\.[0-9]+)*$//'
}

prepare_stage() {
    if [ -L "$PACK_DIR" ]; then
        echo "ERROR: 输出目录是符号链接，拒绝沿链接写入: $PACK_DIR" >&2
        return 1
    fi
    mkdir -p "$PACK_DIR"
    rm -rf "$STAGE_DIR"
    mkdir -p "$STAGE_DIR"
}

stage_assets() {
    find "$STAGE_DIR" -mindepth 1 -maxdepth 1 -type f -name '*.zip' -print \
        | sed 's#.*/##' | LC_ALL=C sort
}

# check_targets <names-file>
# 移动任何资产前逐个检查目标路径：必须是普通文件或不存在。
# 符号链接、子目录等一律拒绝，避免 mv 沿链接写出仓库外。
check_targets() {
    local names_file="$1"
    local name target
    while IFS= read -r name; do
        [ -n "$name" ] || continue
        target="$PACK_DIR/$name"
        if [ -L "$target" ]; then
            echo "ERROR: 目标路径是符号链接，拒绝写入: $target" >&2
            return 1
        fi
        if [ -e "$target" ] && [ ! -f "$target" ]; then
            echo "ERROR: 目标路径已存在且不是普通文件，拒绝写入: $target" >&2
            return 1
        fi
    done <"$names_file"
}

# promote_assets <names-file>
# 把已校验的整批资产移入目标目录，并只清理同标识的过期版本。
promote_assets() {
    local names_file="$1"
    local name base slug f
    local -a built=()

    while IFS= read -r name; do
        [ -n "$name" ] || continue
        built+=("$name")
    done <"$names_file"

    check_targets "$names_file" || return 1

    for name in "${built[@]}"; do
        mv -f "$STAGE_DIR/$name" "$PACK_DIR/$name"
    done

    while IFS= read -r f; do
        [ -n "$f" ] || continue
        base="$(basename "$f")"
        if printf '%s\n' "${built[@]}" | grep -Fxq "$base"; then
            continue
        fi
        slug="$(asset_slug "$base")"
        if printf '%s\n' "${built[@]}" | sed -E 's/\.zip$//; s/-[0-9]+(\.[0-9]+)*$//' \
            | grep -Fxq "$slug"; then
            rm -f "$f"
            echo "  removed superseded asset: $base"
        fi
    done < <(find "$PACK_DIR" -mindepth 1 -maxdepth 1 -type f -name '*.zip' -print)

    rm -rf "$STAGE_DIR"
}

main() {
    REPO_TAG="${1:-v$(date +%Y.%m.%d)}"
    DRY_RUN=false
    [ "${2:-}" = "--dry-run" ] && DRY_RUN=true
    RELEASE_BRANCH="${RELEASE_BRANCH:-main}"

    if [[ ! "$REPO_TAG" =~ ^v20[0-9]{2}\.[0-9]{2}\.[0-9]{2}([.-][A-Za-z0-9.-]+)?$ ]]; then
        echo "ERROR: tag 必须符合 CalVer（如 v2026.09.13 或带安全后缀）: $REPO_TAG" >&2
        exit 1
    fi

    cd "$ROOT"

    prepare_stage
    trap 'rm -rf "$STAGE_DIR"' EXIT

    echo "[1/6] build skill zips..."
    OUTPUT_DIR="$STAGE_DIR" bash "$BUILD_SKILL_ZIPS" "$REPO_TAG"

    echo "[2/6] build expert-suite zips..."
    OUTPUT_DIR="$STAGE_DIR" bash "$BUILD_SUITE_ZIPS" "$REPO_TAG"

    echo "[3/6] 检查产物..."
    names_file="$(mktemp)"
    trap 'rm -f "$names_file"; rm -rf "$STAGE_DIR"' EXIT
    stage_assets >"$names_file"
    zip_count="$(wc -l <"$names_file" | tr -d ' ')"
    suite_zip_count="$(grep -c '^suite-' "$names_file" || true)"
    echo "  产物: $zip_count 个 zip（其中专家套件 $suite_zip_count 个）"
    [ "$zip_count" -gt 0 ] || { echo "ERROR: 无 zip 产物，终止" >&2; exit 1; }
    [ "$suite_zip_count" -gt 0 ] || { echo "ERROR: 无专家套件 zip 产物，终止" >&2; exit 1; }

    promote_assets "$names_file"

    if $DRY_RUN; then
        echo "OK: dry-run 完成；未创建 tag、未联网、未修改 README"
        echo "产物保留在 $PACK_DIR/，可直接解压复验"
        exit 0
    fi

    [ "${RELEASE_CONFIRMED:-}" = "1" ] || {
        echo "ERROR: 尚未确认 Release 五问；确认后设置 RELEASE_CONFIRMED=1" >&2
        exit 1
    }

    echo "[4/6] 发布前 Git 门禁..."
    if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
        echo "ERROR: 工作树不干净；发布只能从无未提交改动的工作树执行" >&2
        exit 1
    fi

    # 输出当前 git worktree 归属，避免在不明工作树或 detached HEAD 上发布。
    git worktree list --porcelain | sed -n '1,4p'
    current_branch="$(git symbolic-ref --quiet --short HEAD || true)"
    [ "$current_branch" = "$RELEASE_BRANCH" ] || {
        echo "ERROR: 当前分支为 ${current_branch:-detached}，要求 $RELEASE_BRANCH" >&2
        exit 1
    }

    git fetch origin "$RELEASE_BRANCH" --tags
    head_oid="$(git rev-parse HEAD)"
    remote_oid="$(git rev-parse "origin/$RELEASE_BRANCH")"
    [ "$head_oid" = "$remote_oid" ] || {
        echo "ERROR: HEAD 与 origin/$RELEASE_BRANCH 不一致，拒绝发布" >&2
        exit 1
    }

    if git show-ref --verify --quiet "refs/tags/$REPO_TAG"; then
        echo "ERROR: 本地 tag 已存在: $REPO_TAG" >&2
        exit 1
    fi
    remote_tag_status=0
    git ls-remote --exit-code --tags origin "refs/tags/$REPO_TAG" >/dev/null 2>&1 || remote_tag_status=$?
    case "$remote_tag_status" in
        0) echo "ERROR: 远端 tag 已存在: $REPO_TAG" >&2; exit 1 ;;
        2) ;;
        *) echo "ERROR: 无法确认远端 tag 是否存在" >&2; exit 1 ;;
    esac

    release_name="${RELEASE_GIT_NAME:-$(git config user.name || true)}"
    release_email="${RELEASE_GIT_EMAIL:-$(git config user.email || true)}"
    [ -n "$release_name" ] && [ -n "$release_email" ] || {
        echo "ERROR: 请设置 RELEASE_GIT_NAME 与 RELEASE_GIT_EMAIL 绑定 tagger 身份" >&2
        exit 1
    }

    GIT_COMMITTER_NAME="$release_name" \
    GIT_COMMITTER_EMAIL="$release_email" \
        git tag -a "$REPO_TAG" "$head_oid" -m "release $REPO_TAG"
    tag_oid="$(git rev-parse "refs/tags/$REPO_TAG^{tag}")"
    peeled_oid="$(git rev-parse "refs/tags/$REPO_TAG^{commit}")"
    tagger="$(git for-each-ref --format='%(taggername)|%(taggeremail)' "refs/tags/$REPO_TAG")"
    [ "$peeled_oid" = "$head_oid" ] || {
        echo "ERROR: tag 没有指向已核验 HEAD" >&2
        exit 1
    }
    [ "$tagger" = "$release_name|<$release_email>" ] || {
        echo "ERROR: tagger 身份核验失败: $tagger" >&2
        exit 1
    }

    echo "[5/6] push immutable tag object..."
    # 分支 safe-push 不适用于 annotated tag；这里把已核验的不可变 tag OID 精确推到目标 ref。
    git push origin "$tag_oid:refs/tags/$REPO_TAG"

    echo "[6/6] 监控 Actions 并核对资产..."
    run_id=""
    for _ in $(seq 1 20); do
        run_id="$(gh run list --workflow=release.yml --limit 10 --json databaseId,headSha \
            --jq ".[] | select(.headSha==\"$head_oid\") | .databaseId" | head -1)"
        [ -n "$run_id" ] && break
        echo "  等待 CI run 出现..."
        sleep 3
    done
    if [ -z "$run_id" ]; then
        echo "ERROR: 未找到 $head_oid 触发的 release.yml run，请检查 Actions" >&2
        exit 1
    fi
    gh run watch "$run_id" --exit-status || {
        echo "ERROR: Release CI 失败，先查明原因，不要直接重打 tag" >&2
        exit 1
    }

    release_asset_count="$(gh release view "$REPO_TAG" --json assets --jq '.assets | length')"
    [ "$release_asset_count" -eq "$zip_count" ] || {
        echo "ERROR: Release 资产数不一致: expected=$zip_count actual=$release_asset_count" >&2
        exit 1
    }

    repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
    echo "release URL: https://github.com/$repo/releases/tag/$REPO_TAG"
    echo "assets: ${release_asset_count}（含专家套件 ${suite_zip_count}）"
    echo "下载链接继续使用 releases/latest；显式 tag 链接由 update-readme workflow 更新"

    project_key="${PROJECT_KEY:-legal-skills}"
    python3 "$(dirname "${BASH_SOURCE[0]}")/generate-release-notes.py" "$repo" "$REPO_TAG" "$project_key" \
        2>/dev/null || \
    python3 "$(dirname "${BASH_SOURCE[0]}")/generate-release-notes.py" "$repo" "$REPO_TAG"
    echo "Release notes 复验稿: .release-notes.md"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
