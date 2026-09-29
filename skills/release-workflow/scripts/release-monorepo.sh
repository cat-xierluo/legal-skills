#!/usr/bin/env bash
set -euo pipefail

# release-monorepo.sh — monorepo Skill 与专家套件发布驱动
# 用法: release-monorepo.sh [REPO_TAG] [--dry-run]
# dry-run 只构建本地产物，不创建 tag、不联网、不修改 README。
# 正式发布前必须由使用者完成 Release 五问并设置 RELEASE_CONFIRMED=1。

REPO_TAG="${1:-v$(date +%Y.%m.%d)}"
DRY_RUN=false
[ "${2:-}" = "--dry-run" ] && DRY_RUN=true
RELEASE_BRANCH="${RELEASE_BRANCH:-main}"

if [[ ! "$REPO_TAG" =~ ^v20[0-9]{2}\.[0-9]{2}\.[0-9]{2}([.-][A-Za-z0-9.-]+)?$ ]]; then
    echo "ERROR: tag 必须符合 CalVer（如 v2026.09.13 或带安全后缀）: $REPO_TAG" >&2
    exit 1
fi

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

echo "[1/6] build skill zips..."
bash skills/release-workflow/scripts/build-zips.sh "$REPO_TAG"

echo "[2/6] build expert-suite zips..."
bash skills/release-workflow/scripts/build-suite-zips.sh "$REPO_TAG"

echo "[3/6] 检查产物..."
zip_count="$(find pack-skills -mindepth 1 -maxdepth 1 -type f -name '*.zip' | wc -l | tr -d ' ')"
suite_zip_count="$(find pack-skills -mindepth 1 -maxdepth 1 -type f -name 'suite-*.zip' | wc -l | tr -d ' ')"
echo "  产物: $zip_count 个 zip（其中专家套件 $suite_zip_count 个）"
[ "$zip_count" -gt 0 ] || { echo "ERROR: 无 zip 产物，终止" >&2; exit 1; }
[ "$suite_zip_count" -gt 0 ] || { echo "ERROR: 无专家套件 zip 产物，终止" >&2; exit 1; }

if $DRY_RUN; then
    echo "OK: dry-run 完成；未创建 tag、未联网、未修改 README"
    echo "产物保留在 pack-skills/，可直接解压复验"
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
echo "assets: $release_asset_count（含专家套件 $suite_zip_count）"
echo "下载链接继续使用 releases/latest；显式 tag 链接由 update-readme workflow 更新"

project_key="${PROJECT_KEY:-legal-skills}"
python3 "$(dirname "$0")/generate-release-notes.py" "$repo" "$REPO_TAG" "$project_key" \
    2>/dev/null || \
python3 "$(dirname "$0")/generate-release-notes.py" "$repo" "$REPO_TAG"
echo "Release notes 复验稿: .release-notes.md"
