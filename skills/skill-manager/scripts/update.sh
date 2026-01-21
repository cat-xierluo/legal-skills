#!/bin/bash

# Skill Manager - Update Script
# 更新已安装的 skills

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

if [ ! -d "$TARGET_DIR" ]; then
    echo "❌ 错误: $TARGET_DIR 目录不存在"
    exit 1
fi

update_skill() {
    local skill_path="$1"
    local skill_name=$(basename "$skill_path")

    # 只更新 git 克隆的 skills
    if [ -d "$skill_path/.git" ]; then
        echo "▶ 更新: $skill_name"

        cd "$skill_path"
        git fetch -q origin
        local local_rev=$(git rev-parse HEAD)
        local remote_rev=$(git rev-parse @{u})

        if [ "$local_rev" != "$remote_rev" ]; then
            git pull -q
            echo "  ✓ 已更新"
        else
            echo "  ○ 已是最新"
        fi

        cd - > /dev/null
        echo ""
    fi
}

if [ -z "$SKILL_NAME" ]; then
    # 更新所有 git 克隆的 skills
    echo "🔄 更新所有 Git 克隆的 skills..."
    echo ""

    count=0
    for item in "$TARGET_DIR"/*; do
        if [ -d "$item/.git" ]; then
            update_skill "$item"
            ((count++))
        fi
    done

    if [ "$count" -eq 0 ]; then
        echo "没有需要更新的 skills"
    else
        echo "✓ 更新完成，共检查 $count 个 skills"
    fi
else
    # 更新指定 skill
    TARGET_PATH="$TARGET_DIR/$SKILL_NAME"

    if [ ! -e "$TARGET_PATH" ]; then
        echo "❌ 错误: Skill '$SKILL_NAME' 不存在"
        exit 1
    fi

    if [ ! -d "$TARGET_PATH/.git" ]; then
        echo "❌ 错误: '$SKILL_NAME' 不是 Git 克隆的 skill，无法更新"
        exit 1
    fi

    update_skill "$TARGET_PATH"
    echo "✓ 更新完成"
fi
