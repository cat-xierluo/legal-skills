#!/bin/bash

# Skill Manager - List Script
# 列出已安装的 skills

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

echo "📋 已安装的 Skills"
echo ""

if [ ! -d "$TARGET_DIR" ]; then
    echo "❌ 错误: $TARGET_DIR 目录不存在"
    exit 1
fi

count=0
for item in "$TARGET_DIR"/*; do
    if [ -e "$item" ]; then
        name=$(basename "$item")

        if [ -L "$item" ]; then
            # 符号链接
            target=$(readlink "$item")
            echo "🔗 $name"
            echo "   类型: 符号链接"
            echo "   指向: $target"
        elif [ -d "$item" ]; then
            # 目录
            if [ -d "$item/.git" ]; then
                # Git 仓库
                remote=$(cd "$item" && git remote get-url origin 2>/dev/null || echo "未知")
                branch=$(cd "$item" && git branch --show-current 2>/dev/null || echo "未知")
                echo "📦 $name"
                echo "   类型: Git 克隆"
                echo "   仓库: $remote"
                echo "   分支: $branch"
            else
                # 普通目录
                echo "📁 $name"
                echo "   类型: 本地目录"
            fi
        fi
        echo ""
        ((count++))
    fi
done

if [ "$count" -eq 0 ]; then
    echo "暂无已安装的 skills"
else
    echo "总计: $count 个 skills"
fi
