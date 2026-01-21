#!/bin/bash

# Skill Manager - Remove Script
# 卸载指定的 skill

SKILL_NAME="$1"
# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_MANAGER_DIR="$(dirname "$SCRIPT_DIR")"

# 检查 skill-manager 是否在 .claude/skills/ 目录下
PARENT_DIR="$(dirname "$SKILL_MANAGER_DIR")"
PARENT_DIR_NAME="$(basename "$PARENT_DIR")"
if [ "$PARENT_DIR_NAME" = "skills" ]; then
    # skill-manager 在 .claude/skills/ 下，使用该目录
    TARGET_DIR="$PARENT_DIR"
else
    # 否则，假设 skill-manager/.claude/skills/skill-manager 的结构
    PROJECT_ROOT="$(dirname "$SKILL_MANAGER_DIR")"
    TARGET_DIR="$PROJECT_ROOT/.claude/skills"
fi

# 检查参数
if [ -z "$SKILL_NAME" ]; then
    echo "❌ 错误: 请提供要卸载的 skill 名称"
    echo ""
    echo "使用方法: $0 <skill-name>"
    echo ""
    echo "示例: $0 pdf-tool"
    exit 1
fi

TARGET_PATH="$TARGET_DIR/$SKILL_NAME"

# 检查是否存在
if [ ! -e "$TARGET_PATH" ]; then
    echo "❌ 错误: Skill '$SKILL_NAME' 不存在"
    exit 1
fi

# 确认删除
echo "⚠ 即将卸载: $SKILL_NAME"
if [ -L "$TARGET_PATH" ]; then
    echo "   类型: 符号链接"
elif [ -d "$TARGET_PATH/.git" ]; then
    echo "   类型: Git 克隆"
else
    echo "   类型: 本地目录"
fi

echo ""
read -p "确认删除? (y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 0
fi

# 执行删除
if [ -L "$TARGET_PATH" ]; then
    rm "$TARGET_PATH"
    echo "✓ 已删除符号链接"
elif [ -d "$TARGET_PATH" ]; then
    rm -rf "$TARGET_PATH"
    echo "✓ 已删除目录"
fi

echo "✓ Skill '$SKILL_NAME' 已卸载"
