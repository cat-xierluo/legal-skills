#!/bin/bash

# Skill & Command Manager - Update Script
# 更新已安装的 git 克隆的 skills
# 注意：符号链接的 skills/commands 会自动与源同步，无需更新

ITEM_NAME="$1"
# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGER_DIR="$(dirname "$SCRIPT_DIR")"

# 更新记录函数
record_update() {
    local skill_name="$1"
    local old_version="$2"
    local new_version="$3"
    
    if command -v python3 &> /dev/null; then
        RECORD_SCRIPT="$SCRIPT_DIR/record.py"
        if [ -f "$RECORD_SCRIPT" ]; then
            python3 "$RECORD_SCRIPT" update "$skill_name" --from "$old_version" --to "$new_version" 2>/dev/null || true
        fi
    fi
}

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

if [ ! -d "$SKILLS_DIR" ]; then
    echo "❌ 错误: $SKILLS_DIR 目录不存在"
    exit 1
fi

update_skill() {
    local skill_path="$1"
    local skill_name=$(basename "$skill_path")

    # 只更新 git 克隆的 skills
    if [ -d "$skill_path/.git" ]; then
        echo "▶ 更新: $skill_name"

        cd "$skill_path"
        
        # 记录更新前的版本
        local old_version=$(grep -oP 'version:\s*["\']?\K[\d.]+' SKILL.md 2>/dev/null || echo "")
        
        git fetch -q origin 2>/dev/null || {
            echo "  ❌ 无法获取更新"
            cd - > /dev/null
            echo ""
            return
        }
        local local_rev=$(git rev-parse HEAD)
        local remote_rev=$(git rev-parse @{u} 2>/dev/null)

        if [ "$local_rev" != "$remote_rev" ] && [ -n "$remote_rev" ]; then
            git pull -q
            
            # 获取更新后的版本
            local new_version=$(grep -oP 'version:\s*["\']?\K[\d.]+' SKILL.md 2>/dev/null || echo "")
            
            echo "  ✓ 已更新 ($old_version → $new_version)"
            
            # 记录更新
            record_update "$skill_name" "$old_version" "$new_version"
        else
            echo "  ○ 已是最新"
        fi

        cd - > /dev/null
        echo ""
    fi
}

if [ -z "$ITEM_NAME" ]; then
    # 更新所有 git 克隆的 skills
    echo "🔄 更新所有 Git 克隆的 skills..."
    echo ""
    echo "注意: 符号链接的 skills/commands 会自动与源同步，无需手动更新"
    echo ""

    count=0
    for item in "$SKILLS_DIR"/*; do
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
    TARGET_PATH="$SKILLS_DIR/$ITEM_NAME"

    if [ ! -e "$TARGET_PATH" ]; then
        echo "❌ 错误: Skill '$ITEM_NAME' 不存在"
        exit 1
    fi

    if [ -L "$TARGET_PATH" ]; then
        echo "ℹ '$ITEM_NAME' 是符号链接，会自动与源同步，无需手动更新"
        echo "   指向: $(readlink "$TARGET_PATH")"
        exit 0
    fi

    if [ ! -d "$TARGET_PATH/.git" ]; then
        echo "❌ 错误: '$ITEM_NAME' 不是 Git 克隆的 skill，无法更新"
        exit 1
    fi

    update_skill "$TARGET_PATH"
    echo "✓ 更新完成"
fi
