#!/bin/bash

# Skill Manager - Install Script
# 安装或同步外部 skills 到本地 .claude/skills

set -e

SOURCE="$1"
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
if [ -z "$SOURCE" ]; then
    echo "❌ 错误: 请提供源路径或 URL"
    echo ""
    echo "使用方法:"
    echo "  $0 <本地路径 | github-url | owner/repo>"
    echo ""
    echo "示例:"
    echo "  本地单个 skill:     $0 ~/skills/pdf-tool"
    echo "  本地 skills 集合:   $0 ~/skills/"
    echo "  GitHub 仓库:        $0 owner/repo"
    echo "  GitHub 子目录:      $0 owner/repo/branch/path/to/skills"
    exit 1
fi

# 检查是否为包含多个 skills 的目录
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
elif [[ "$SOURCE" =~ ^https?://github\.com/([^/]+)/([^/]+?)(\.git)?/?$ ]]; then
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
                    echo "▶ 安装: $skill_name"

                    target_path="$TARGET_DIR/$skill_name"

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

    # 单个本地 skill - 使用符号链接
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

    echo "🔗 正在创建到本地路径的符号链接..."
    ln -s "$SOURCE" "$TARGET_PATH"
    echo "✓ 已链接: $TARGET_PATH -> $SOURCE"
    ls -l "$TARGET_PATH"
    exit 0
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
