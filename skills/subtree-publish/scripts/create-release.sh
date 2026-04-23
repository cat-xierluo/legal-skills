#!/usr/bin/env bash
# create-release.sh - 为 subtree 发布的 skill 创建 GitHub Release
# 用法: bash scripts/create-release.sh <name> [--dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 从 config 或默认值读取配置
CONFIG_FILE=""
PREFIX="skills"
ORG=""

# 尝试定位配置文件
for candidate in "$SKILL_ROOT/config/subtree-skills.json" "$SKILL_ROOT/../../../config/subtree-skills.json"; do
  if [ -f "$candidate" ]; then
    CONFIG_FILE="$candidate"
    break
  fi
done

if [ -n "$CONFIG_FILE" ] && command -v jq &>/dev/null; then
  PREFIX=$(jq -r '.prefix // "skills"' "$CONFIG_FILE")
  ORG=$(jq -r '.org // ""' "$CONFIG_FILE")
fi

# 参数解析
NAME=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    -*)
      echo "未知选项: $1" >&2
      exit 1
      ;;
    *)
      if [ -z "$NAME" ]; then
        NAME="$1"
      else
        echo "用法: $0 <name> [--dry-run]" >&2
        exit 1
      fi
      shift
      ;;
  esac
done

if [ -z "$NAME" ]; then
  echo "用法: $0 <name> [--dry-run]" >&2
  exit 1
fi

# 查找仓库名
REPO="${NAME}.skill"
if [ -n "$CONFIG_FILE" ] && command -v jq &>/dev/null; then
  CUSTOM_REPO=$(jq -r --arg n "$NAME" '.skills[] | select(.name == $n) | .repo // empty' "$CONFIG_FILE" 2>/dev/null || true)
  if [ -n "$CUSTOM_REPO" ]; then
    REPO="$CUSTOM_REPO"
  fi
fi

SKILL_DIR="${PREFIX}/${NAME}"
SKILL_MD="${SKILL_DIR}/SKILL.md"

# 校验
if [ ! -f "$SKILL_MD" ]; then
  echo "错误: 找不到 $SKILL_MD" >&2
  exit 1
fi

if [ -z "$ORG" ]; then
  echo "错误: 无法确定 GitHub org，请检查 config/subtree-skills.json" >&2
  exit 1
fi

if ! command -v gh &>/dev/null; then
  echo "错误: 需要安装 gh (GitHub CLI)" >&2
  exit 1
fi

# 读取版本号
VERSION=$(grep '^version:' "$SKILL_MD" | head -1 | sed 's/version: *//' | tr -d '"' | tr -d "'")
if [ -z "$VERSION" ]; then
  echo "错误: 无法从 $SKILL_MD 读取 version" >&2
  exit 1
fi

TAG="v${VERSION}"
FULL_REPO="${ORG}/${REPO}"

echo "=== Release 创建 ==="
echo "  Skill:    $NAME"
echo "  版本:     $VERSION"
echo "  仓库:     $FULL_REPO"
echo ""

# 检查是否已有该版本的 Release
EXISTING=$(gh release list --repo "$FULL_REPO" --limit 100 2>/dev/null | grep -E "^${TAG}\t" || true)
if [ -n "$EXISTING" ]; then
  echo "跳过: ${TAG} 已存在 (${FULL_REPO})"
  exit 0
fi

# 准备 Release Notes
NOTES="发布 v${VERSION}"
CHANGELOG_FILE="${SKILL_DIR}/CHANGELOG.md"
if [ -f "$CHANGELOG_FILE" ]; then
  # 提取对应版本的变更记录（匹配 ## [vX.Y.Z] 或 ## vX.Y.Z 格式）
  CHANGELOG_CONTENT=$(awk "/^## .*\[?v?${VERSION}\]?/{found=1; next} /^## /{if(found) exit} found{print}" "$CHANGELOG_FILE" 2>/dev/null || true)
  if [ -n "$CHANGELOG_CONTENT" ]; then
    NOTES="$CHANGELOG_CONTENT"
  fi
fi

# 打包
ZIP_FILE="/tmp/${NAME}-${VERSION}.zip"
if [ "$DRY_RUN" = true ]; then
  echo "[dry-run] 将执行以下操作:"
  echo "  1. 打包: cd ${PREFIX} && zip -r ${ZIP_FILE} ${NAME}/ -x '${NAME}/*.DS_Store' '${NAME}/README.md' '${NAME}/config/*.json'"
  echo "     然后补回: ${NAME}/config/*.example.json"
  echo "  2. 创建 Release:"
  echo "     gh release create ${TAG} --repo ${FULL_REPO} --title '${TAG}' --notes '...'"
  echo "     附件: ${ZIP_FILE}"
  exit 0
fi

echo "打包 ${NAME}/ ..."
cd "$PREFIX"
zip -r "$ZIP_FILE" "${NAME}/" -x "${NAME}/*.DS_Store" "${NAME}/README.md" "${NAME}/config/*.json"
if [ -d "${NAME}/config" ]; then
  while IFS= read -r example_config; do
    zip -r "$ZIP_FILE" "$example_config" >/dev/null
  done < <(find "${NAME}/config" -maxdepth 1 -type f -name "*.example.json" | sort)
fi
cd - > /dev/null

echo "创建 Release ${TAG}..."
gh release create "$TAG" --repo "$FULL_REPO" \
  --title "$TAG" \
  --notes "$NOTES" \
  "$ZIP_FILE"

echo "完成: ${TAG} 已发布到 ${FULL_REPO}"
