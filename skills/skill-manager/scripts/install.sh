#!/bin/bash

# Skill & Command Manager - Install Script
# 安装或同步外部 skills/commands 到本地 Agent 配置目录
# 自动检测所有 Agent 目录 (.codex/.claude/.openclaw) 并批量安装

set -e

# Parse arguments: support --target flag for explicit target directory
SOURCE=""
TARGET_OVERRIDE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --target|-t)
            if [ -z "${2:-}" ]; then
                echo "❌ 错误: --target 需要指定目录路径"
                exit 1
            fi
            TARGET_OVERRIDE="$2"
            shift 2
            ;;
        -h|--help)
            echo "用法: $0 [选项] <source>"
            echo ""
            echo "选项:"
            echo "  --target, -t <dir>  指定目标 Agent 配置目录"
            echo ""
            echo "示例:"
            echo "  $0 ~/skills/pdf-tool"
            echo "  $0 --target /path/to/project/.claude ~/skills/pdf-tool"
            exit 0
            ;;
        *)
            SOURCE="$1"
            shift
            ;;
    esac
done

# 保存调用者的原始工作目录（关键：用于定位项目 Agent 配置目录）
ORIGINAL_PWD="$PWD"

# Apply --target override
if [ -n "$TARGET_OVERRIDE" ]; then
    export SKILL_MANAGER_TARGET_DIR="$TARGET_OVERRIDE"
fi
# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGER_DIR="$(dirname "$SCRIPT_DIR")"
TARGET_HELPER="$SCRIPT_DIR/target.sh"

if [ -f "$TARGET_HELPER" ]; then
    # shellcheck source=target.sh
    source "$TARGET_HELPER"
else
    echo "❌ 错误: 找不到目标目录识别模块: $TARGET_HELPER"
    exit 1
fi

# 安装记录函数 - 记录 Skill 安装到注册表
record_install() {
    local skill_name="$1"
    local source_url="$2"
    local target_path="$3"

    # 调用 Python 记录模块
    if command -v python3 &> /dev/null; then
        RECORD_SCRIPT="$SCRIPT_DIR/record.py"
        if [ -f "$RECORD_SCRIPT" ]; then
            python3 "$RECORD_SCRIPT" install "$skill_name" "$source_url" --path "$target_path" --install-type local 2>/dev/null || true
        fi
    fi
}

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
        # 优先检查是否为 skill（包含 SKILL.md 或 Agent 配置目录等）
        if [ -f "$src/SKILL.md" ] || [ -f "$src/skill.md" ] || [ -d "$src/.codex" ] || [ -d "$src/.claude" ] || [ -d "$src/.openclaw" ] || [ -d "$src/.agents" ] || [ -d "$src/.agent" ]; then
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

# 检查是否为 skills 集合目录
is_skills_collection() {
    local dir="$1"
    local found_skills=0

    for item in "$dir"/*; do
        if [ -d "$item" ]; then
            if [ -f "$item/SKILL.md" ] || [ -f "$item/skill.md" ] || [ -d "$item/.codex" ] || [ -d "$item/.claude" ] || [ -d "$item/.openclaw" ]; then
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
    if [ -f "$dir/SKILL.md" ] || [ -f "$dir/skill.md" ] || [ -d "$dir/.codex" ] || [ -d "$dir/.claude" ] || [ -d "$dir/.openclaw" ]; then
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

# ---- 检测来源类型 ----

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

# ---- 检测所有 Agent 配置目录 ----

FALLBACK_AGENT_DIR="$(find_agent_config_dir "$ORIGINAL_PWD" "$(find_agent_config_dir "$MANAGER_DIR" "$PWD/.claude")")"

ALL_AGENT_DIRS=()
while IFS= read -r dir; do
    ALL_AGENT_DIRS+=("$dir")
done < <(find_all_agent_config_dirs "$ORIGINAL_PWD" "$FALLBACK_AGENT_DIR")

if [ ${#ALL_AGENT_DIRS[@]} -eq 0 ]; then
    echo "❌ 错误: 未找到任何 Agent 配置目录 (.codex/.claude/.openclaw)"
    exit 1
fi

# Safety: if target would be a global config root, try git-based project rescue
_is_global_config_root() {
    local dir="$1"
    local _home="${HOME:-/Users/${USER}}"
    case "$dir" in
        "$_home/.codex"| "$_home/.claude"| "$_home/.openclaw"| "$_home/.agents"| "$_home/.agent") return 0 ;;
    esac
    return 1
}

if [ -z "${SKILL_MANAGER_TARGET_DIR:-}" ] && [ ${#ALL_AGENT_DIRS[@]} -gt 0 ]; then
    _only_global=true
    for _dir in "${ALL_AGENT_DIRS[@]}"; do
        if ! _is_global_config_root "$_dir"; then
            _only_global=false
            break
        fi
    done

    if [ "$_only_global" = true ]; then
        # Try git-based project rescue
        _git_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
        _rescued=false
        if [ -n "$_git_root" ] && ! _is_global_config_root "$_git_root" && [ "$_git_root" != "$HOME" ]; then
            for _cfg in .codex .claude .openclaw .agents .agent; do
                if [ -d "$_git_root/$_cfg" ]; then
                    echo "🔄 检测到从全局配置目录调用，已通过 git 发现项目: $_git_root"
                    echo ""
                    ALL_AGENT_DIRS=("$_git_root/$_cfg")
                    _rescued=true
                    break
                fi
            done
        fi

        if [ "$_rescued" = false ]; then
            echo "⚠️  目标为全局配置目录 (${ALL_AGENT_DIRS[*]})"
            echo "   如需安装到项目目录，请使用: $0 --target <project/.claude> <source>"
            echo ""
        fi
    fi
fi

# 显示检测到的目录
AGENT_NAMES=()
for dir in "${ALL_AGENT_DIRS[@]}"; do
    AGENT_NAMES+=($(basename "$dir"))
done
echo "🔍 检测到 ${#ALL_AGENT_DIRS[@]} 个 Agent 配置目录: ${AGENT_NAMES[*]}"
echo ""

# ---- GitHub 预处理：克隆到临时目录（只克隆一次）----

TEMP_CLONE_DIR=""
INSTALL_COMMIT=""
INSTALL_BRANCH=""
GH_SKILL_NAME=""

if [ "$SOURCE_TYPE" = "github-subdir" ] || [ "$SOURCE_TYPE" = "github" ]; then
    if [ "$SOURCE_TYPE" = "github-subdir" ]; then
        GH_SKILL_NAME=$(basename "$SUBPATH")
    else
        GH_SKILL_NAME="$REPO"
    fi

    TEMP_CLONE_DIR=$(mktemp -d)

    if [ "$SOURCE_TYPE" = "github-subdir" ]; then
        echo "📦 正在从 GitHub 获取子目录..."
        echo "  仓库: $CLONE_URL"
        echo "  路径: $SUBPATH"

        cd "$TEMP_CLONE_DIR"
        git init -q
        git remote add origin "$CLONE_URL"
        git config core.sparseCheckout true
        echo "$SUBPATH" > .git/info/sparse-checkout
        git fetch --depth 1 origin "${BRANCH:-main}" -q 2>/dev/null || {
            echo "❌ 错误: 无法从 GitHub 获取"
            cd - > /dev/null
            rm -rf "$TEMP_CLONE_DIR"
            exit 1
        }
        git checkout "${BRANCH:-main}" -q

        INSTALL_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "")
        INSTALL_BRANCH="${BRANCH:-main}"

        cd - > /dev/null

        # 移动到临时目录内的固定位置
        mv "$TEMP_CLONE_DIR/$SUBPATH" "$TEMP_CLONE_DIR/$GH_SKILL_NAME"
    else
        echo "📦 正在从 GitHub 克隆..."
        echo "  仓库: $CLONE_URL"

        git clone --depth 1 -q "$CLONE_URL" "$TEMP_CLONE_DIR/$GH_SKILL_NAME" 2>/dev/null || {
            echo "❌ 错误: 无法从 GitHub 克隆"
            rm -rf "$TEMP_CLONE_DIR"
            exit 1
        }

        INSTALL_COMMIT=$(cd "$TEMP_CLONE_DIR/$GH_SKILL_NAME" && git rev-parse --short HEAD 2>/dev/null || echo "")
        INSTALL_BRANCH=$(cd "$TEMP_CLONE_DIR/$GH_SKILL_NAME" && git branch --show-current 2>/dev/null || echo "main")

        # 删除 .git 目录
        rm -rf "$TEMP_CLONE_DIR/$GH_SKILL_NAME/.git"
    fi

    echo "✓ GitHub 源准备完成"
    echo ""
fi

# ---- 安装到每个 Agent 目录 ----

install_count=0
success_dirs=()
fail_count=0

for AGENT_DIR in "${ALL_AGENT_DIRS[@]}"; do
    agent_name=$(basename "$AGENT_DIR")
    SKILLS_DIR="$AGENT_DIR/skills"
    COMMANDS_DIR="$AGENT_DIR/commands"

    echo "───────────────────────────────────"
    echo "📦 安装到 $agent_name"
    echo "───────────────────────────────────"

    # ---- 本地来源 ----
    if [ "$SOURCE_TYPE" = "local" ]; then
        DETECTED_TYPE=$(detect_source_type "$SOURCE")

        if [ "$DETECTED_TYPE" = "unknown" ]; then
            if [ ! -e "$SOURCE" ]; then
                echo "❌ 错误: 找不到源: $SOURCE"
            else
                echo "❌ 错误: 无法识别源类型，请确保是 skill 目录或 command .md 文件"
            fi
            ((fail_count++)) || true
            echo ""
            continue
        fi

        # 处理单个 command 文件
        if [ "$DETECTED_TYPE" = "command" ]; then
            COMMAND_NAME=$(basename "$SOURCE" .md)
            TARGET_PATH="$COMMANDS_DIR/$COMMAND_NAME.md"

            mkdir -p "$COMMANDS_DIR"

            if [ -L "$TARGET_PATH" ]; then
                echo "⚠ 发现现有符号链接，正在移除..."
                rm "$TARGET_PATH"
            elif [ -f "$TARGET_PATH" ]; then
                if [ "$TARGET_PATH" -ef "$SOURCE" ]; then
                    echo "✓ 已指向相同文件"
                    ((install_count++)) || true
                    success_dirs+=("$agent_name")
                    echo ""
                    continue
                fi
                echo "⚠ 目标已存在，正在备份到 ${TARGET_PATH}.backup..."
                mv "$TARGET_PATH" "${TARGET_PATH}.backup"
            fi

            echo "🔗 正在创建 command 符号链接..."
            ln -s "$SOURCE" "$TARGET_PATH"
            echo "✓ 已链接 command: $TARGET_PATH -> $SOURCE"
            ((install_count++)) || true
            success_dirs+=("$agent_name")
            echo ""
            continue
        fi

        # 处理目录
        if [ ! -d "$SOURCE" ]; then
            echo "❌ 错误: 找不到源目录: $SOURCE"
            ((fail_count++)) || true
            echo ""
            continue
        fi

        # 检查是否为 skills 集合目录
        if is_skills_collection "$SOURCE"; then
            local_count=0
            for skill_dir in "$SOURCE"/*; do
                if [ -d "$skill_dir" ]; then
                    skill_name=$(basename "$skill_dir")

                    if [ -f "$skill_dir/SKILL.md" ] || [ -f "$skill_dir/skill.md" ] || [ -d "$skill_dir/.codex" ] || [ -d "$skill_dir/.claude" ] || [ -d "$skill_dir/.openclaw" ]; then
                        target_path="$SKILLS_DIR/$skill_name"
                        mkdir -p "$SKILLS_DIR"

                        if [ -L "$target_path" ]; then
                            rm "$target_path"
                        elif [ -d "$target_path" ]; then
                            if [ "$target_path" -ef "$skill_dir" ]; then
                                continue
                            fi
                            rm -rf "${target_path}.backup"
                            mv "$target_path" "${target_path}.backup"
                        fi

                        ln -s "$skill_dir" "$target_path"
                        echo "  ✓ 已链接: $skill_name"
                        ((local_count++)) || true
                    fi
                fi
            done

            echo "✓ 已安装 $local_count 个 skills"
            ((install_count++)) || true
            success_dirs+=("$agent_name")
            echo ""
            continue
        fi

        # 检查是否为 commands 集合目录
        if is_commands_collection "$SOURCE"; then
            local_count=0
            for cmd_file in "$SOURCE"/*.md; do
                if [ -f "$cmd_file" ]; then
                    cmd_name=$(basename "$cmd_file" .md)
                    target_path="$COMMANDS_DIR/$cmd_name.md"
                    mkdir -p "$COMMANDS_DIR"

                    if [ -L "$target_path" ]; then
                        rm "$target_path"
                    elif [ -f "$target_path" ]; then
                        if [ "$target_path" -ef "$cmd_file" ]; then
                            continue
                        fi
                        mv "$target_path" "${target_path}.backup"
                    fi

                    ln -s "$cmd_file" "$target_path"
                    echo "  ✓ 已链接: $cmd_name"
                    ((local_count++)) || true
                fi
            done

            echo "✓ 已安装 $local_count 个 commands"
            ((install_count++)) || true
            success_dirs+=("$agent_name")
            echo ""
            continue
        fi

        # 单个本地 skill - 使用符号链接
        if [ "$DETECTED_TYPE" = "skill" ]; then
            SKILL_NAME=$(basename "$SOURCE")
            TARGET_PATH="$SKILLS_DIR/$SKILL_NAME"

            mkdir -p "$SKILLS_DIR"

            if [ -L "$TARGET_PATH" ]; then
                echo "⚠ 发现现有符号链接，正在移除..."
                rm "$TARGET_PATH"
            elif [ -d "$TARGET_PATH" ]; then
                if [ "$TARGET_PATH" -ef "$SOURCE" ]; then
                    echo "✓ 已指向相同目录"
                    ((install_count++)) || true
                    success_dirs+=("$agent_name")
                    echo ""
                    continue
                fi
                echo "⚠ 目标已存在，正在备份到 ${TARGET_PATH}.backup..."
                rm -rf "${TARGET_PATH}.backup"
                mv "$TARGET_PATH" "${TARGET_PATH}.backup"
            fi

            echo "🔗 正在创建 skill 符号链接..."
            ln -s "$SOURCE" "$TARGET_PATH"
            echo "✓ 已链接 skill: $TARGET_PATH -> $SOURCE"

            # 记录安装
            record_install "$SKILL_NAME" "$SOURCE" "$TARGET_PATH"
            ((install_count++)) || true
            success_dirs+=("$agent_name")
            echo ""
            continue
        fi
    fi

    # ---- GitHub 来源 ----
    if [ "$SOURCE_TYPE" = "github-subdir" ] || [ "$SOURCE_TYPE" = "github" ]; then
        TARGET_PATH="$SKILLS_DIR/$GH_SKILL_NAME"
        mkdir -p "$SKILLS_DIR"

        if [ -e "$TARGET_PATH" ]; then
            echo "⚠ 目标已存在，正在备份到 ${TARGET_PATH}.backup..."
            rm -rf "${TARGET_PATH}.backup"
            mv "$TARGET_PATH" "${TARGET_PATH}.backup"
        fi

        cp -R "$TEMP_CLONE_DIR/$GH_SKILL_NAME" "$TARGET_PATH"
        echo "✓ 已安装: $TARGET_PATH"

        # 记录安装
        if command -v python3 &> /dev/null; then
            RECORD_SCRIPT="$SCRIPT_DIR/record.py"
            if [ -f "$RECORD_SCRIPT" ]; then
                local_args=()
                if [ "$SOURCE_TYPE" = "github-subdir" ]; then
                    local_args=(--remote-url "$CLONE_URL/tree/${INSTALL_BRANCH}/$SUBPATH" --remote-subpath "$SUBPATH")
                else
                    local_args=(--remote-url "$CLONE_URL")
                fi
                python3 "$RECORD_SCRIPT" install "$GH_SKILL_NAME" "$CLONE_URL" \
                    --path "$TARGET_PATH" \
                    --install-type remote \
                    --install-commit "$INSTALL_COMMIT" \
                    --install-branch "$INSTALL_BRANCH" \
                    "${local_args[@]}" 2>/dev/null || true
            fi
        fi

        ((install_count++)) || true
        success_dirs+=("$agent_name")
        echo ""
    fi

done

# ---- 清理临时目录 ----
if [ -n "$TEMP_CLONE_DIR" ] && [ -d "$TEMP_CLONE_DIR" ]; then
    rm -rf "$TEMP_CLONE_DIR"
fi

# ---- 安全检查（GitHub 来源，只检查一次）----
if [ "$SOURCE_TYPE" = "github" ] || [ "$SOURCE_TYPE" = "github-subdir" ]; then
    if [ ${#success_dirs[@]} -gt 0 ]; then
        FIRST_AGENT_DIR="${ALL_AGENT_DIRS[0]}"
        CHECK_PATH="$FIRST_AGENT_DIR/skills/$GH_SKILL_NAME"

        if command -v python3 &> /dev/null && [ -d "$CHECK_PATH" ]; then
            SECURITY_SCRIPT="$SCRIPT_DIR/security.py"
            if [ -f "$SECURITY_SCRIPT" ]; then
                echo "🔍 正在进行安全检查..."
                python3 "$SECURITY_SCRIPT" "$CHECK_PATH" 2>/dev/null || {
                    echo ""
                    echo "⚠️  安全检查发现问题，请查看上方报告"
                    echo "   如需继续使用，请自行评估风险"
                }
            fi
        else
            echo "💡 提示: 未检测到 Python，跳过安全检查"
        fi
    fi
fi

# ---- 汇总 ----
echo ""
echo "========================================"
echo "📊 安装汇总"
echo "========================================"
if [ "$install_count" -gt 0 ]; then
    echo "  成功: $install_count 个 Agent 目录"
    for d in "${success_dirs[@]}"; do
        echo "    ✅ $d"
    done
fi
if [ "$fail_count" -gt 0 ]; then
    echo "  失败: $fail_count"
fi
echo "========================================"
