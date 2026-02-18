#!/bin/bash

# Skill & Command Manager - Remove Script
# 卸载指定的 skill 或 command

ITEM_NAME="$1"
# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGER_DIR="$(dirname "$SCRIPT_DIR")"

# 查找 .claude 目录
# 特殊规则：当在 ~/.openclaw/ 目录下时，使用 ~/.openclaw/ 作为目标
find_claude_dir() {
    local current="$MANAGER_DIR"
    local max_iterations=10
    local iteration=0

    # 获取用户主目录
    local home_dir="${HOME:-/Users/${USER}}"

    # 特殊规则：检测是否在 ~/.openclaw/ 目录下
    # 如果是，使用 ~/.openclaw/ 作为目标目录
    if [[ "$current" == "$home_dir/.openclaw"* ]]; then
        echo "$home_dir/.openclaw"
        return 0
    fi

    while [ $iteration -lt $max_iterations ]; do
        local parent="$(dirname "$current")"
        local parent_name="$(basename "$parent")"

        if [ "$parent_name" = ".claude" ]; then
            echo "$parent"
            return 0
        fi

        if [ "$parent_name" = "skills" ] || [ "$parent_name" = "commands" ]; then
            local grandparent="$(dirname "$parent")"
            local grandparent_name="$(basename "$grandparent")"
            if [ "$grandparent_name" = ".claude" ]; then
                echo "$grandparent"
                return 0
            fi
        fi

        current="$parent"
        ((iteration++))
    done

    echo "$(dirname "$MANAGER_DIR")/../.claude"
}

CLAUDE_DIR="$(find_claude_dir)"
SKILLS_DIR="$CLAUDE_DIR/skills"
COMMANDS_DIR="$CLAUDE_DIR/commands"

# 检查参数
if [ -z "$ITEM_NAME" ]; then
    echo "❌ 错误: 请提供要卸载的 skill 或 command 名称"
    echo ""
    echo "使用方法: $0 <name>"
    echo ""
    echo "示例:"
    echo "  卸载 skill:    $0 pdf-tool"
    echo "  卸载 command:  $0 deepresearch"
    exit 1
fi

# 查找目标（先找 skill，再找 command）
SKILL_PATH="$SKILLS_DIR/$ITEM_NAME"
COMMAND_PATH="$COMMANDS_DIR/$ITEM_NAME.md"

TARGET_PATH=""
TARGET_TYPE=""

if [ -e "$SKILL_PATH" ]; then
    TARGET_PATH="$SKILL_PATH"
    TARGET_TYPE="skill"
elif [ -e "$COMMAND_PATH" ]; then
    TARGET_PATH="$COMMAND_PATH"
    TARGET_TYPE="command"
else
    echo "❌ 错误: 未找到 '$ITEM_NAME'"
    echo "   请确认名称是否正确"
    exit 1
fi

# 检查是否是 skill-manager 自身
if [ "$ITEM_NAME" = "skill-manager" ]; then
    echo "❌ 错误: 不能卸载 skill-manager 自身"
    exit 1
fi

# 确认删除
echo "⚠ 即将卸载: $ITEM_NAME"
if [ "$TARGET_TYPE" = "skill" ]; then
    if [ -L "$TARGET_PATH" ]; then
        echo "   类型: 符号链接 (skill)"
    elif [ -d "$TARGET_PATH/.git" ]; then
        echo "   类型: Git 克隆 (skill)"
    else
        echo "   类型: 本地目录 (skill)"
    fi
else
    if [ -L "$TARGET_PATH" ]; then
        echo "   类型: 符号链接 (command)"
    else
        echo "   类型: 本地文件 (command)"
    fi
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
elif [ -f "$TARGET_PATH" ]; then
    rm "$TARGET_PATH"
    echo "✓ 已删除文件"
fi

echo "✓ $TARGET_TYPE '$ITEM_NAME' 已卸载"
