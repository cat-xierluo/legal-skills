#!/usr/bin/env bash
# subtree-push.sh — 将 monorepo 中的子目录推送到独立 GitHub 仓库
#
# 用法:
#   bash scripts/subtree-push.sh --auto                # 自动检测最近 commit 涉及的子项目并推送
#   bash scripts/subtree-push.sh <name>                # 推送指定子项目
#   bash scripts/subtree-push.sh <name> --setup        # 首次设置：创建仓库 + 添加 remote + 推送
#   bash scripts/subtree-push.sh <name> --dry-run      # 只显示将要执行的操作

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config/subtree-skills.json"

# 从 JSON 配置读取 org 和 prefix
GITHUB_ORG=$(jq -r '.org // "cat-xierluo"' "$CONFIG_FILE")
PREFIX=$(jq -r '.prefix // "skills"' "$CONFIG_FILE")

# 检查是否在 monorepo 根目录
if [ ! -f "${PREFIX}/subtree-publish/SKILL.md" ]; then
  echo "错误: 请在 monorepo 根目录执行此脚本"
  exit 1
fi

# --- 自动检测模式 ---
if [ "${1:-}" = "--auto" ]; then
  if [ ! -f "$CONFIG_FILE" ]; then
    echo "配置文件不存在: ${CONFIG_FILE}"
    exit 1
  fi

  CHANGED_FILES=$(git diff --name-only HEAD~1 HEAD 2>/dev/null || echo "")
  if [ -z "$CHANGED_FILES" ]; then
    echo "没有检测到最近的 commit 变更"
    exit 0
  fi

  PUSHED=0
  SKILL_COUNT=$(jq '.skills | length' "$CONFIG_FILE")
  for i in $(seq 0 $((SKILL_COUNT - 1))); do
    skill_name=$(jq -r ".skills[$i].name" "$CONFIG_FILE")
    repo_name=$(jq -r ".skills[$i].repo // .skills[$i].name" "$CONFIG_FILE")
    REMOTE_NAME=$(jq -r ".skills[$i].remote // \"${skill_name}-standalone\"" "$CONFIG_FILE")
    SKILL_DIR="${PREFIX}/${skill_name}"

    if echo "$CHANGED_FILES" | grep -q "^${SKILL_DIR}/"; then
      echo "检测到 ${skill_name} 有变更，推送到独立仓库..."

      if ! git remote get-url "$REMOTE_NAME" &>/dev/null; then
        echo "  跳过: remote '${REMOTE_NAME}' 未配置"
        continue
      fi

      echo "  git subtree push --prefix=${SKILL_DIR} ${REMOTE_NAME} main"
      git subtree push --prefix="$SKILL_DIR" "$REMOTE_NAME" main
      echo "  完成: https://github.com/${GITHUB_ORG}/${repo_name}"
      PUSHED=$((PUSHED + 1))
    fi
  done

  if [ "$PUSHED" -eq 0 ]; then
    echo "本次 commit 未涉及任何已注册的 subtree 子项目"
  fi
  exit 0
fi

# --- 单个子项目模式 ---
SKILL_NAME="${1:?用法: subtree-push.sh [--auto|<name>] [--setup|--dry-run]}"
FLAG="${2:-}"

REMOTE_NAME="${SKILL_NAME}-standalone"
SKILL_DIR="${PREFIX}/${SKILL_NAME}"

# 从 config 读取仓库名和 remote 映射
REPO_NAME="$SKILL_NAME"
REMOTE_NAME="${SKILL_NAME}-standalone"
if [ -f "$CONFIG_FILE" ]; then
  MAPPED_REPO=$(jq -r --arg name "$SKILL_NAME" '.skills[] | select(.name == $name) | .repo // .name' "$CONFIG_FILE")
  if [ -n "$MAPPED_REPO" ] && [ "$MAPPED_REPO" != "null" ]; then
    REPO_NAME="$MAPPED_REPO"
  fi
  MAPPED_REMOTE=$(jq -r --arg name "$SKILL_NAME" '.skills[] | select(.name == $name) | .remote // ""' "$CONFIG_FILE")
  if [ -n "$MAPPED_REMOTE" ] && [ "$MAPPED_REMOTE" != "null" ]; then
    REMOTE_NAME="$MAPPED_REMOTE"
  fi
fi

REPO_URL="https://github.com/${GITHUB_ORG}/${REPO_NAME}.git"

if [ ! -d "$SKILL_DIR" ]; then
  echo "错误: 子目录不存在: ${SKILL_DIR}"
  exit 1
fi

if [ ! -f "${SKILL_DIR}/SKILL.md" ]; then
  echo "错误: 未找到 ${SKILL_DIR}/SKILL.md"
  exit 1
fi

echo "=== Subtree Publish: ${SKILL_NAME} ==="
echo ""

DESCRIPTION=$(grep -m1 '^description:' "${SKILL_DIR}/SKILL.md" | sed 's/^description: *//' || echo "")

if [ "$FLAG" = "--dry-run" ]; then
  echo "[dry-run] 将要执行的操作:"
  echo "  1. 检查 remote '${REMOTE_NAME}' 是否存在"
  echo "  2. 如不存在，创建 GitHub 仓库 ${GITHUB_ORG}/${REPO_NAME}"
  echo "  3. 添加 remote: git remote add ${REMOTE_NAME} ${REPO_URL}"
  echo "  4. 推送: git subtree push --prefix=${SKILL_DIR} ${REMOTE_NAME} main"
  echo ""
  echo "描述: ${DESCRIPTION}"
  exit 0
fi

if git remote get-url "$REMOTE_NAME" &>/dev/null; then
  echo "remote '${REMOTE_NAME}' 已存在: $(git remote get-url "$REMOTE_NAME")"
else
  if [ "$FLAG" = "--setup" ]; then
    echo "创建 GitHub 仓库: ${GITHUB_ORG}/${REPO_NAME}"
    gh repo create "${GITHUB_ORG}/${REPO_NAME}" --public ${DESCRIPTION:+--description "$DESCRIPTION"}
  else
    echo "remote '${REMOTE_NAME}' 不存在。使用 --setup 首次设置，或手动添加:"
    echo "  git remote add ${REMOTE_NAME} ${REPO_URL}"
    exit 1
  fi

  echo "添加 remote: ${REMOTE_NAME}"
  git remote add "$REMOTE_NAME" "$REPO_URL"
fi

echo ""
echo "推送 subtree: ${SKILL_DIR} -> ${REMOTE_NAME}/main"
git subtree push --prefix="$SKILL_DIR" "$REMOTE_NAME" main

echo ""
echo "=== 完成 ==="
echo "独立仓库: https://github.com/${GITHUB_ORG}/${REPO_NAME}"

# 提醒注册到清单
if [ -f "$CONFIG_FILE" ]; then
  REGISTERED=$(jq --arg name "$SKILL_NAME" '.skills[] | select(.name == $name) | .name' "$CONFIG_FILE")
  if [ -z "$REGISTERED" ]; then
    echo ""
    echo "提醒: ${SKILL_NAME} 尚未注册到 config/subtree-skills.json"
  fi
fi
