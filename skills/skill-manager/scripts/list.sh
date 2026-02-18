#!/bin/bash

# Skill & Command Manager - List Script
# 列出已安装的 skills 和 commands

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

# 列出 skills
list_skills() {
    local dir="$1"
    if [ ! -d "$dir" ]; then
        return
    fi

    echo "📋 已安装的 Skills"
    echo ""

    count=0
    for item in "$dir"/*; do
        if [ -e "$item" ] && [ "$(basename "$item")" != "skill-manager" ]; then
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
}

# 列出 commands
list_commands() {
    local dir="$1"
    if [ ! -d "$dir" ]; then
        return
    fi

    echo ""
    echo "📋 已安装的 Commands"
    echo ""

    count=0
    for item in "$dir"/*.md; do
        if [ -e "$item" ]; then
            name=$(basename "$item" .md)

            if [ -L "$item" ]; then
                # 符号链接
                target=$(readlink "$item")
                echo "🔗 $name"
                echo "   类型: 符号链接"
                echo "   指向: $target"
            elif [ -f "$item" ]; then
                # 普通文件
                echo "📄 $name"
                echo "   类型: 本地文件"
            fi
            echo ""
            ((count++))
        fi
    done

    if [ "$count" -eq 0 ]; then
        echo "暂无已安装的 commands"
    else
        echo "总计: $count 个 commands"
    fi
}

# 执行列表
list_skills "$SKILLS_DIR"
list_commands "$COMMANDS_DIR"
