#!/bin/bash
# prepare-publish.sh - 准备技能发布目录
# 用法: prepare-publish.sh <skill-path>
#
# 此脚本创建一个临时目录，只包含符合 .gitignore 规则的文件，
# 用于 ClawHub CLI 发布。
#
# 过滤规则（双重过滤）：
# 1. 项目根目录的 .gitignore（如果存在）
# 2. 技能内部的 .gitignore（如果存在）
#
# 参数:
#   skill-path - 技能目录路径（相对或绝对路径）
#
# 输出:
#   临时目录路径

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 帮助信息
usage() {
    echo "用法: prepare-publish.sh <skill-path>"
    echo ""
    echo "参数:"
    echo "  skill-path - 技能目录路径（相对或绝对路径）"
    echo ""
    echo "功能:"
    echo "  创建临时目录用于 ClawHub 发布，自动应用 .gitignore 过滤规则。"
    echo ""
    echo "过滤规则（双重过滤）:"
    echo "  1. 项目根目录的 .gitignore（自动检测）"
    echo "  2. 技能内部的 .gitignore（如果存在）"
    echo ""
    echo "示例:"
    echo "  prepare-publish.sh skills/trademark-assistant"
    echo "  prepare-publish.sh /path/to/skills/trademark-assistant"
    exit 1
}

# 检查参数
if [ -z "$1" ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    usage
fi

SKILL_PATH="$1"

# 转换为绝对路径
if [ "${SKILL_PATH:0:1}" != "/" ]; then
    SKILL_PATH="$(cd "$(dirname "$SKILL_PATH")" 2>/dev/null && pwd)/$(basename "$SKILL_PATH")"
fi

# 检查技能目录是否存在
if [ ! -d "$SKILL_PATH" ]; then
    echo -e "${RED}错误: 技能目录不存在: $SKILL_PATH${NC}"
    exit 1
fi

# 检查 SKILL.md 是否存在
if [ ! -f "$SKILL_PATH/SKILL.md" ] && [ ! -f "$SKILL_PATH/skill.md" ]; then
    echo -e "${RED}错误: 技能目录中未找到 SKILL.md: $SKILL_PATH${NC}"
    exit 1
fi

# 获取技能名称
SKILL_NAME=$(basename "$SKILL_PATH")

# 确定项目根目录（从技能路径向上查找包含 .git 的目录）
PROJECT_ROOT=""
CURRENT_DIR="$SKILL_PATH"
while [ "$CURRENT_DIR" != "/" ]; do
    if [ -d "$CURRENT_DIR/.git" ]; then
        PROJECT_ROOT="$CURRENT_DIR"
        break
    fi
    CURRENT_DIR=$(dirname "$CURRENT_DIR")
done

if [ -z "$PROJECT_ROOT" ]; then
    echo -e "${YELLOW}警告: 未找到 Git 仓库根目录，将只使用技能内部的 .gitignore${NC}"
fi

# 创建临时目录
TEMP_DIR="/tmp/clawhub-publish-$SKILL_NAME"
echo -e "${GREEN}准备发布目录: $TEMP_DIR${NC}"

# 清理旧的临时目录
rm -rf "$TEMP_DIR"

# 构建 rsync 参数
RSYNC_ARGS=(
    -av                    # 归档模式，显示详细信息
    --delete               # 删除目标目录中多余的文件
    --exclude='.git/'      # 排除 Git 目录
    --exclude='node_modules/'  # 排除 node_modules
    --exclude='__pycache__/'   # 排除 Python 缓存
    --exclude='.DS_Store'      # 排除 macOS 系统文件
)

# 检查项目根目录的 .gitignore
PROJECT_GITIGNORE=""
if [ -n "$PROJECT_ROOT" ] && [ -f "$PROJECT_ROOT/.gitignore" ]; then
    PROJECT_GITIGNORE="$PROJECT_ROOT/.gitignore"
    echo -e "${BLUE}[1] 使用项目根目录 .gitignore: $PROJECT_GITIGNORE${NC}"
fi

# 检查技能内部的 .gitignore
SKILL_GITIGNORE=""
if [ -f "$SKILL_PATH/.gitignore" ]; then
    SKILL_GITIGNORE="$SKILL_PATH/.gitignore"
    echo -e "${BLUE}[2] 使用技能内部 .gitignore: $SKILL_GITIGNORE${NC}"
fi

# 应用过滤规则
# 注意：rsync 的 --filter 顺序很重要，先应用的规则优先级更高
# 我们希望技能内部的 .gitignore 优先级更高，所以后应用

if [ -n "$PROJECT_GITIGNORE" ]; then
    RSYNC_ARGS+=(--filter=":- $PROJECT_GITIGNORE")
fi

if [ -n "$SKILL_GITIGNORE" ]; then
    RSYNC_ARGS+=(--filter=":- $SKILL_GITIGNORE")
fi

# 如果没有任何 .gitignore，给出提示
if [ -z "$PROJECT_GITIGNORE" ] && [ -z "$SKILL_GITIGNORE" ]; then
    echo -e "${YELLOW}警告: 未找到任何 .gitignore 文件，将只排除默认目录${NC}"
fi

# 执行 rsync
echo -e "${GREEN}复制文件到临时目录...${NC}"
rsync "${RSYNC_ARGS[@]}" "$SKILL_PATH/" "$TEMP_DIR/"

# 统计文件数量
FILE_COUNT=$(find "$TEMP_DIR" -type f | wc -l | tr -d ' ')
echo -e "${GREEN}已复制 $FILE_COUNT 个文件到临时目录${NC}"

# 列出被排除的重要文件类型（用于验证）
echo ""
echo -e "${BLUE}=== 临时目录内容预览 ===${NC}"
ls -la "$TEMP_DIR" | head -20

# 输出临时目录路径（最后一行）
echo ""
echo "$TEMP_DIR"
