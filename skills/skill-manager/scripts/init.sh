#!/bin/bash

# Skill Manager - Init Script
# 初始化项目的 Agent 配置目录，使不同 Agent（QoderWork/WorkBuddy/Codex/OpenClaw 等）
# 都能发现项目的 Claude Code Skills。
#
# 核心操作：为每个 Agent 创建 skills -> ../.claude/skills 相对符号链接。
# 来源始终是 .claude/skills —— 这是所有 Agent skills 的符号链接根源。

set -e

# 支持的 Agent 配置目录（与 target.sh 保持一致，含 .claude 自身但 init 时跳过）
ALL_AGENTS=(".codex" ".claude" ".openclaw" ".workbuddy" ".qoderworkcn")
# init 默认不处理 .claude（其 skills 是来源，不需要再链接到自己）
DEFAULT_AGENTS=(".codex" ".openclaw" ".workbuddy" ".qoderworkcn")

usage() {
    cat <<'EOF'
用法: init.sh [选项]

初始化项目 Agent 配置目录，为每个 Agent 创建 skills -> ../.claude/skills 符号链接，
使不同 Agent 在项目中工作时都能发现 Claude Code Skills。

选项:
  --all              初始化所有 Agent（含 .codex .openclaw .workbuddy .qoderworkcn .claude）
  --qoderwork        仅初始化 .qoderworkcn
  --workbuddy        仅初始化 .workbuddy
  --codex            仅初始化 .codex
  --openclaw         仅初始化 .openclaw
  --claude           也初始化 .claude（通常不需要，因其 skills 是来源）
  --dry-run          预览模式，仅显示将要执行的操作
  --gitignore        同步更新 .gitignore，追加 .{agent}/ 条目

示例:
  ./init.sh                         # 初始化默认 4 个 Agent
  ./init.sh --qoderwork --workbuddy # 仅初始化 QoderWork 和 WorkBuddy
  ./init.sh --all --gitignore       # 初始化全部 Agent 并更新 .gitignore
  ./init.sh --dry-run               # 预览模式
EOF
    exit 0
}

# 解析参数
SELECTED_AGENTS=()
DRY_RUN=false
UPDATE_GITIGNORE=false
SPECIFIC_SELECTED=false
SKIP_CLAUDE=true

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --gitignore)
            UPDATE_GITIGNORE=true
            shift
            ;;
        --all)
            SELECTED_AGENTS=("${ALL_AGENTS[@]}")
            SKIP_CLAUDE=false
            SPECIFIC_SELECTED=true
            shift
            ;;
        --qoderwork)
            SELECTED_AGENTS+=(".qoderworkcn")
            SPECIFIC_SELECTED=true
            shift
            ;;
        --workbuddy)
            SELECTED_AGENTS+=(".workbuddy")
            SPECIFIC_SELECTED=true
            shift
            ;;
        --codex)
            SELECTED_AGENTS+=(".codex")
            SPECIFIC_SELECTED=true
            shift
            ;;
        --openclaw)
            SELECTED_AGENTS+=(".openclaw")
            SPECIFIC_SELECTED=true
            shift
            ;;
        --claude)
            SELECTED_AGENTS+=(".claude")
            SKIP_CLAUDE=false
            SPECIFIC_SELECTED=true
            shift
            ;;
        *)
            echo "❌ 未知选项: $1"
            echo "   使用 --help 查看可用选项"
            exit 1
            ;;
    esac
done

# 如果没有指定特定 Agent，使用默认列表
if [ "$SPECIFIC_SELECTED" = false ]; then
    SELECTED_AGENTS=("${DEFAULT_AGENTS[@]}")
fi

# 去重
SELECTED_AGENTS=($(printf '%s\n' "${SELECTED_AGENTS[@]}" | sort -u))

# 向上查找项目根目录（优先 git root，其次 .claude/skills 所在目录）
find_project_root() {
    local start_dir="${1:-$PWD}"
    local current
    current="$(cd "$start_dir" 2>/dev/null && pwd)" || current="$start_dir"
    local max_iterations=20
    local iteration=0

    # 优先使用 git root
    local git_root
    git_root="$(cd "$start_dir" && git rev-parse --show-toplevel 2>/dev/null || true)"
    if [ -n "$git_root" ]; then
        printf '%s\n' "$git_root"
        return 0
    fi

    # 向上找 .claude/skills/ 目录
    while [ "$iteration" -lt "$max_iterations" ]; do
        if [ -d "$current/.claude/skills" ]; then
            printf '%s\n' "$current"
            return 0
        fi

        local parent
        parent="$(dirname "$current")"
        if [ "$parent" = "$current" ]; then
            break
        fi
        current="$parent"
        iteration=$((iteration + 1))
    done

    # 未找到，使用当前目录
    printf '%s\n' "$start_dir"
    return 1
}

PROJECT_ROOT="$(find_project_root)"

# 检测项目是否有 .claude/skills/ 源
if [ ! -d "$PROJECT_ROOT/.claude/skills" ]; then
    echo "⚠️  在 $PROJECT_ROOT 未找到 .claude/skills/ 目录"
    echo ""
    echo "   init 需要 .claude/skills/ 作为 skills 符号链接的来源。"
    echo "   如果项目使用 Codex（.codex/skills/）作为主技能目录，"
    echo "   请使用 install 命令安装 skills 后再运行 init。"
    echo ""
    read -p "❓ 是否继续（将创建指向不存在目录的符号链接）？[y/N] " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "已取消"
        exit 0
    fi
fi

# 主逻辑
total_created=0
total_skipped=0
total_failed=0
dry_prefix=""

if [ "$DRY_RUN" = true ]; then
    dry_prefix="[DRY RUN] "
    echo "🔍 预览模式 — 不会实际修改文件"
    echo ""
fi

echo "${dry_prefix}📁 项目根目录: $PROJECT_ROOT"
echo "${dry_prefix}🎯 目标 Agent: ${SELECTED_AGENTS[*]}"
echo "${dry_prefix}📍 技能来源: .claude/skills"
echo ""

for agent in "${SELECTED_AGENTS[@]}"; do
    agent_dir="$PROJECT_ROOT/$agent"
    target_link="$agent_dir/skills"

    echo "───────────────────────────────────"
    echo "${dry_prefix}🔧 初始化 $agent ..."
    echo "───────────────────────────────────"

    # 创建 Agent 配置目录
    if [ ! -d "$agent_dir" ]; then
        echo "  → 创建目录 $agent/"
        if [ "$DRY_RUN" = false ]; then
            mkdir -p "$agent_dir"
        fi
    fi

    # 检查 skills 目标当前状态
    if [ -L "$target_link" ]; then
        existing_target=$(readlink "$target_link")
        if [ "$existing_target" = "../.claude/skills" ]; then
            echo "  ✓ 已正确指向 .claude/skills，跳过"
            ((total_skipped++)) || true
            echo ""
            continue
        else
            echo "  ⚠ skills 指向 $existing_target，需要更新"
            if [ "$DRY_RUN" = false ]; then
                rm "$target_link"
            fi
        fi
    elif [ -d "$target_link" ]; then
        echo "  ⚠ $agent/skills/ 是实体目录（非符号链接），备份后重建"
        backup_path="${target_link}.init-backup-$(date +%Y%m%d%H%M%S)"
        if [ "$DRY_RUN" = false ]; then
            mv "$target_link" "$backup_path"
            echo "  → 备份至 $(basename "$backup_path")"
        else
            echo "  → 将备份至 $(basename "$backup_path")"
        fi
    elif [ -f "$target_link" ]; then
        echo "  ⚠ $agent/skills 是文件（非目录/符号链接），备份后重建"
        backup_path="${target_link}.init-backup-$(date +%Y%m%d%H%M%S)"
        if [ "$DRY_RUN" = false ]; then
            mv "$target_link" "$backup_path"
        fi
    fi

    # 创建符号链接
    if [ "$DRY_RUN" = true ]; then
        echo "  → ln -s ../.claude/skills $agent/skills"
    else
        ln -s "../.claude/skills" "$target_link"
        echo "  ✓ 已创建: $agent/skills -> ../.claude/skills"
    fi
    ((total_created++)) || true
    echo ""
done

# 更新 .gitignore
update_gitignore() {
    local gitignore="$PROJECT_ROOT/.gitignore"

    if [ ! -f "$gitignore" ]; then
        if [ "$DRY_RUN" = false ]; then
            touch "$gitignore"
        fi
    fi

    echo ""
    echo "${dry_prefix}📝 更新 .gitignore ..."

    for agent in "${SELECTED_AGENTS[@]}"; do
        local pattern="${agent}/"
        if grep -q "^${agent}/" "$gitignore" 2>/dev/null; then
            echo "  ✓ ${agent}/ 已存在"
        else
            echo "  → 追加 ${agent}/"
            if [ "$DRY_RUN" = false ]; then
                printf '%s\n' "${agent}/" >> "$gitignore"
            fi
        fi
    done
}

if [ "$UPDATE_GITIGNORE" = true ]; then
    update_gitignore
fi

# 汇总
echo ""
echo "========================================"
echo "${dry_prefix}📊 初始化汇总"
echo "========================================"
echo "  项目: $PROJECT_ROOT"
echo "  新建: $total_created 个符号链接"
echo "  跳过: $total_skipped 个（已正确）"
if [ "$total_failed" -gt 0 ]; then
    echo "  失败: $total_failed"
fi
echo "========================================"
