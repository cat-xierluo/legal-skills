#!/usr/bin/env bash
set -euo pipefail

# release-monorepo.sh — legal-skills 等 monorepo-many-skills 主发布驱动
# 用法: release-monorepo.sh [REPO_TAG] [--dry-run]
# 流程: 打 zip → 检查产物 → 打 tag →(dry-run 跳过 push)→ push → 监控 Actions → 验证 assets

REPO_TAG="${1:-v$(date +%Y.%m.%d)}"
DRY_RUN=false
[ "${2:-}" = "--dry-run" ] && DRY_RUN=true

# 跳到仓库根
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

echo "[1/5] build zips..."
bash skills/release-workflow/scripts/build-zips.sh "$REPO_TAG"

echo "[2/5] 检查产物..."
zip_count=$(ls -1 pack-skills/*.zip 2>/dev/null | wc -l | tr -d ' ')
echo "  产物:$zip_count 个 zip"
[ "$zip_count" -gt 0 ] || { echo "ERROR: 无 zip 产物,终止"; exit 1; }

echo "[3/5] 打 tag: $REPO_TAG"
git tag "$REPO_TAG" -m "release $REPO_TAG"
git show "$REPO_TAG" --no-patch --format="%H %s%n%n%b" | head -5

if $DRY_RUN; then
    echo "[dry-run] 跳过 push,清理本地"
    git tag -d "$REPO_TAG" >/dev/null
    rm -rf pack-skills/
    echo "OK (dry-run 完成,tag 已删除,zip 已清理)"
    exit 0
fi

echo "[4/5] push tag..."
git push origin "$REPO_TAG"

echo "[5/5] 监控 Actions..."
gh run watch --exit-status || { echo "CI 失败,排查后重试"; exit 1; }

echo
echo "release info:"
gh release view "$REPO_TAG" --json tagName,assets --jq '"tag: \(.tagName)\nassets: \(.assets | length)"'
echo "release URL: https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/releases/tag/$REPO_TAG"

echo
echo "[6/6] 自动回写 README 下载链接(release-monorepo 内嵌,不依赖外部 workflow)..."
# 调 update-readme.py 替换 README 占位为真实 browser_download_url
if python3 "$(dirname "$0")/update-readme.py"; then
    # 如果 README 有变更,提交并推送
    if ! git diff --quiet README.md; then
        git add README.md
        git commit -m "docs: 同步 README 下载链接到 ${REPO_TAG} release

内嵌 update-readme.py 自动执行(不依赖 .github/workflows/update-readme.yml 跨 workflow 事件)。"
        git push origin HEAD
        echo "✅ README 已自动同步"
    else
        echo "README 无需变更"
    fi
else
    echo "⚠️  update-readme.py 失败,需手动处理"
    exit 1
fi