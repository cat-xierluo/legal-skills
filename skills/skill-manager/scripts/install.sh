#!/bin/bash

# Skill & Command Manager - Install Script
# 安装或同步外部 skills/commands 到本地 .claude/

set -e

SOURCE="$1"
# 保存调用者的原始工作目录（关键：用于定位项目 .claude 目录）
ORIGINAL_PWD="$PWD"
# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGER_DIR="$(dirname "$SCRIPT_DIR")"

# 检测源类型（skill 或 command）
detect_source_type() {
    local src="$1"

    # 如果是文件
    if [ -f "$src" ]; then
        if [[ "$src" =~ \.md$ ]]; then
            echo "command"
        else
            echo "unknown"
        fi
    # 如果是目录
    elif [ -d "$src" ]; then
        # 优先检查是否为 skill（包含 SKILL.md 等）
        if [ -f "$src/SKILL.md" ] || [ -f "$src/skill.md" ] || [ -d "$src/.claude" ]; then
            echo "skill"
        # 检查是否为 command 集合目录（包含多个 .md 文件，但不包含 SKILL.md）
        else
            local md_count=$(find "$src" -maxdepth 1 -name "*.md" -type f 2>/dev/null | wc -l | tr -d ' ')
            if [ "$md_count" -gt 0 ]; then
                echo "command-collection"
            else
                echo "unknown"
            fi
        fi
    else
        echo "unknown"
    fi
}

# 检测目标目录（支持 skills 和 commands）
# 优先从当前工作目录查找 .claude，适用于在项目内调用
# 特殊规则：当在 ~/.openclaw/ 目录下时，使用 ~/.openclaw/skills/ 作为目标
find_claude_dir() {
    # 首先尝试从调用者的原始工作目录查找（项目本地）
    local current="$ORIGINAL_PWD"
    local current_name="$(basename "$current")"
    local max_iterations=10
    local iteration=0

    # 获取用户主目录
    local home_dir="${HOME:-/Users/${USER}}"

    # 特殊规则：检测是否在 ~/.openclaw/ 目录下
    # 如果是，使用 ~/.openclaw/skills/ 作为目标目录
    # 注意：返回 ~/.openclaw/ 而不是 ~/.openclaw/skills/，因为后续会自动拼接 /skills
    if [[ "$current" == "$home_dir/.openclaw"* ]]; then
        # 在 openclaw 目录下，直接使用 openclaw 目录本身
        echo "$home_dir/.openclaw"
        return 0
    fi

    # 如果当前目录本身就是 .claude，直接使用
    if [ "$current_name" = ".claude" ]; then
        echo "$current"
        return 0
    fi

    # 如果当前目录包含 skills 子目录，说明当前目录就是 .claude 目录
    if [ -d "$current/skills" ]; then
        echo "$current"
        return 0
    fi

    while [ $iteration -lt $max_iterations ]; do
        # 检查当前目录是否包含 .claude 子目录
        if [ -d "$current/.claude" ]; then
            echo "$current/.claude"
            return 0
        fi

        # 检查当前目录的父目录是否是 .claude
        local parent="$(dirname "$current")"
        local parent_name="$(basename "$parent")"

        if [ "$parent_name" = ".claude" ]; then
            echo "$parent"
            return 0
        fi

        # 检查父目录是否是 skills 或 commands
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

    # 如果没找到，返回默认值（使用当前工作目录）
    echo "$PWD/.claude"
}

CLAUDE_DIR="$(find_claude_dir)"
SKILLS_DIR="$CLAUDE_DIR/skills"
COMMANDS_DIR="$CLAUDE_DIR/commands"

# 根据 source 类型确定目标目录
if [ -f "$SOURCE" ] && [[ "$SOURCE" =~ \.md$ ]]; then
    TARGET_DIR="$COMMANDS_DIR"
    TARGET_TYPE="command"
else
    TARGET_DIR="$SKILLS_DIR"
    TARGET_TYPE="skill"
fi

# 检查参数
if [ -z "$SOURCE" ]; then
    echo "❌ 错误: 请提供源路径或 URL"
    echo ""
    echo "使用方法:"
    echo "  $0 <本地路径 | github-url | owner/repo>"
    echo ""
    echo "示例:"
    echo "  本地单个 skill/command:  $0 ~/my-skills/pdf-tool"
    echo "  本地 skills 集合:        $0 ~/skills/"
    echo "  本地 commands 集合:      $0 ~/commands/"
    echo "  GitHub 仓库:             $0 owner/repo"
    echo "  GitHub 子目录:           $0 owner/repo/branch/path/to/skills"
    exit 1
fi

# 检查是否为 skills 集合目录
is_skills_collection() {
    local dir="$1"
    local found_skills=0

    for item in "$dir"/*; do
        if [ -d "$item" ]; then
            if [ -f "$item/SKILL.md" ] || [ -f "$item/skill.md" ] || [ -d "$item/.claude" ]; then
                ((found_skills++))
            fi
        fi
    done

    [ "$found_skills" -gt 1 ]
}

# 检查是否为 commands 集合目录
# 注意：必须排除包含 SKILL.md 的 skill 目录
is_commands_collection() {
    local dir="$1"
    local found_commands=0

    # 如果目录包含 SKILL.md，则不是 commands 集合
    if [ -f "$dir/SKILL.md" ] || [ -f "$dir/skill.md" ] || [ -d "$dir/.claude" ]; then
        return 1
    fi

    for item in "$dir"/*; do
        if [ -f "$item" ] && [[ "$item" =~ \.md$ ]]; then
            # 排除 SKILL.md/skill.md 文件
            local basename=$(basename "$item")
            if [ "$basename" != "SKILL.md" ] && [ "$basename" != "skill.md" ]; then
                ((found_commands++))
            fi
        fi
    done

    [ "$found_commands" -gt 1 ]
}

# 检测来源类型
if [[ "$SOURCE" =~ ^https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$ ]]; then
    # GitHub URL 到子目录 (blob 格式)
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
    BRANCH="${BASH_REMATCH[3]}"
    SUBPATH="${BASH_REMATCH[4]}"
    SOURCE_TYPE="github-subdir"
    CLONE_URL="https://github.com/$OWNER/$REPO"
elif [[ "$SOURCE" =~ ^https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.+)$ ]]; then
    # GitHub URL 到子目录 (tree 格式)
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
    BRANCH="${BASH_REMATCH[3]}"
    SUBPATH="${BASH_REMATCH[4]}"
    SOURCE_TYPE="github-subdir"
    CLONE_URL="https://github.com/$OWNER/$REPO"
elif [[ "$SOURCE" =~ ^https?://github\.com/([^/]+)/([^/]+)(\.git)?/?$ ]]; then
    # GitHub 仓库根目录
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
    SOURCE_TYPE="github"
    CLONE_URL="https://github.com/$OWNER/$REPO"
elif [[ "$SOURCE" =~ ^([^/]+)/([^/]+)(/(.+))?$ ]]; then
    # 可能是 GitHub 简写格式，需要进一步检查
    # 如果路径不存在，则认为是 GitHub 格式
    if [ ! -e "$SOURCE" ]; then
        OWNER="${BASH_REMATCH[1]}"
        REPO="${BASH_REMATCH[2]}"
        if [ -n "${BASH_REMATCH[4]}" ]; then
            SUBPATH="${BASH_REMATCH[4]}"
            SOURCE_TYPE="github-subdir"
            CLONE_URL="https://github.com/$OWNER/$REPO"
        else
            SOURCE_TYPE="github"
            CLONE_URL="https://github.com/$OWNER/$REPO"
        fi
    else
        SOURCE_TYPE="local"
    fi
else
    # 本地路径
    SOURCE_TYPE="local"
fi

# 本地路径处理
if [ "$SOURCE_TYPE" = "local" ]; then
    # 检测源类型
    DETECTED_TYPE=$(detect_source_type "$SOURCE")

    if [ "$DETECTED_TYPE" = "unknown" ]; then
        if [ ! -e "$SOURCE" ]; then
            echo "❌ 错误: 找不到源: $SOURCE"
        else
            echo "❌ 错误: 无法识别源类型，请确保是 skill 目录或 command .md 文件"
        fi
        exit 1
    fi

    # 处理单个 command 文件
    if [ "$DETECTED_TYPE" = "command" ]; then
        COMMAND_NAME=$(basename "$SOURCE" .md)
        TARGET_PATH="$TARGET_DIR/$COMMAND_NAME.md"

        mkdir -p "$TARGET_DIR"

        if [ -L "$TARGET_PATH" ]; then
            echo "⚠ 发现现有符号链接，正在移除..."
            rm "$TARGET_PATH"
        elif [ -f "$TARGET_PATH" ]; then
            if [ "$TARGET_PATH" -ef "$SOURCE" ]; then
                echo "✓ 已指向相同文件"
                exit 0
            fi
            echo "⚠ 目标已存在，正在备份到 ${TARGET_PATH}.backup..."
            mv "$TARGET_PATH" "${TARGET_PATH}.backup"
        fi

        echo "🔗 正在创建 command 符号链接..."
        ln -s "$SOURCE" "$TARGET_PATH"
        echo "✓ 已链接 command: $TARGET_PATH -> $SOURCE"
        ls -l "$TARGET_PATH"
        exit 0
    fi

    # 处理目录
    if [ ! -d "$SOURCE" ]; then
        echo "❌ 错误: 找不到源目录: $SOURCE"
        exit 1
    fi

    # 检查是否为 skills 集合目录
    if is_skills_collection "$SOURCE"; then
        echo "📦 检测到 skills 集合目录，开始批量安装..."
        echo ""

        count=0
        for skill_dir in "$SOURCE"/*; do
            if [ -d "$skill_dir" ]; then
                skill_name=$(basename "$skill_dir")

                if [ -f "$skill_dir/SKILL.md" ] || [ -f "$skill_dir/skill.md" ] || [ -d "$skill_dir/.claude" ]; then
                    echo "▶ 安装 skill: $skill_name"

                    target_path="$TARGET_DIR/../skills/$skill_name"

                    if [ -L "$target_path" ]; then
                        rm "$target_path"
                    elif [ -d "$target_path" ]; then
                        if [ "$target_path" -ef "$skill_dir" ]; then
                            echo "  ✓ 已存在相同链接"
                            echo ""
                            continue
                        fi
                        rm -rf "${target_path}.backup"
                        mv "$target_path" "${target_path}.backup"
                    fi

                    # 本地路径使用符号链接
                    ln -s "$skill_dir" "$target_path"
                    echo "  ✓ 已链接: $target_path -> $skill_dir"
                    echo ""
                    ((count++))
                fi
            fi
        done

        echo "✓ 批量安装完成，共安装 $count 个 skills"
        exit 0
    fi

    # 检查是否为 commands 集合目录
    if is_commands_collection "$SOURCE"; then
        echo "📦 检测到 commands 集合目录，开始批量安装..."
        echo ""

        count=0
        for cmd_file in "$SOURCE"/*.md; do
            if [ -f "$cmd_file" ]; then
                cmd_name=$(basename "$cmd_file" .md)
                echo "▶ 安装 command: $cmd_name"

                target_path="$TARGET_DIR/../commands/$cmd_name.md"

                if [ -L "$target_path" ]; then
                    rm "$target_path"
                elif [ -f "$target_path" ]; then
                    if [ "$target_path" -ef "$cmd_file" ]; then
                        echo "  ✓ 已存在相同链接"
                        echo ""
                        continue
                    fi
                    mv "$target_path" "${target_path}.backup"
                fi

                # 本地路径使用符号链接
                ln -s "$cmd_file" "$target_path"
                echo "  ✓ 已链接: $target_path -> $cmd_file"
                echo ""
                ((count++))
            fi
        done

        echo "✓ 批量安装完成，共安装 $count 个 commands"
        exit 0
    fi

    # 单个本地 skill - 使用符号链接
    if [ "$DETECTED_TYPE" = "skill" ]; then
        SKILL_NAME=$(basename "$SOURCE")
        TARGET_PATH="$TARGET_DIR/$SKILL_NAME"

        mkdir -p "$TARGET_DIR"

        if [ -L "$TARGET_PATH" ]; then
            echo "⚠ 发现现有符号链接，正在移除..."
            rm "$TARGET_PATH"
        elif [ -d "$TARGET_PATH" ]; then
            if [ "$TARGET_PATH" -ef "$SOURCE" ]; then
                echo "✓ 已指向相同目录"
                exit 0
            fi
            echo "⚠ 目标已存在，正在备份到 ${TARGET_PATH}.backup..."
            rm -rf "${TARGET_PATH}.backup"
            mv "$TARGET_PATH" "${TARGET_PATH}.backup"
        fi

        echo "🔗 正在创建 skill 符号链接..."
        ln -s "$SOURCE" "$TARGET_PATH"
        echo "✓ 已链接 skill: $TARGET_PATH -> $SOURCE"
        ls -l "$TARGET_PATH"
        exit 0
    fi
fi

# GitHub 处理（复制而非克隆）
if [ "$SOURCE_TYPE" = "github-subdir" ]; then
    SKILL_NAME=$(basename "$SUBPATH")
elif [ "$SOURCE_TYPE" = "github" ]; then
    SKILL_NAME="$REPO"
fi

TARGET_PATH="$TARGET_DIR/$SKILL_NAME"

mkdir -p "$TARGET_DIR"

# 处理已存在的目标
if [ -e "$TARGET_PATH" ]; then
    echo "⚠ 目标已存在，正在备份到 ${TARGET_PATH}.backup..."
    rm -rf "${TARGET_PATH}.backup"
    mv "$TARGET_PATH" "${TARGET_PATH}.backup"
fi

if [ "$SOURCE_TYPE" = "github-subdir" ]; then
    # GitHub 子目录 - 使用稀疏克隆
    echo "📦 正在从 GitHub 获取子目录..."
    echo "  仓库: $CLONE_URL"
    echo "  路径: $SUBPATH"

    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"

    git init -q
    git remote add origin "$CLONE_URL"
    git config core.sparseCheckout true
    echo "$SUBPATH" > .git/info/sparse-checkout
    git fetch --depth 1 origin "${BRANCH:-main}" -q 2>/dev/null || {
        echo "❌ 错误: 无法从 GitHub 获取"
        cd - > /dev/null
        rm -rf "$TEMP_DIR"
        exit 1
    }
    git checkout "${BRANCH:-main}" -q

    cd - > /dev/null

    # 移动到目标位置
    mv "$TEMP_DIR/$SUBPATH" "$TARGET_PATH"
    rm -rf "$TEMP_DIR"

    echo "✓ 已安装: $TARGET_PATH"

elif [ "$SOURCE_TYPE" = "github" ]; then
    # GitHub 仓库 - 直接克隆
    echo "📦 正在从 GitHub 克隆..."
    echo "  仓库: $CLONE_URL"

    git clone --depth 1 -q "$CLONE_URL" "$TARGET_PATH" 2>/dev/null || {
        echo "❌ 错误: 无法从 GitHub 克隆"
        rm -rf "$TARGET_PATH"
        exit 1
    }

    # 删除 .git 目录
    rm -rf "$TARGET_PATH/.git"

    echo "✓ 已安装: $TARGET_PATH"
fi

ls -l "$TARGET_PATH"
