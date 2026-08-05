#!/bin/bash
# prepare-publish.sh - 准备技能发布目录
# 用法: prepare-publish.sh [--platform <clawhub|skillhub>] <skill-path>
#
# 此脚本创建一个临时目录，只包含符合 .gitignore 规则的文件，
# 用于 ClawHub / 腾讯 SkillHub CLI 发布。
#
# 过滤规则（双重过滤）：
# 1. 项目根目录的 .gitignore（如果存在）
# 2. 技能内部的 .gitignore（如果存在）
#
# 参数:
#   --platform <name> - 目标平台，决定临时目录前缀（默认 clawhub）
#                       clawhub  → /tmp/clawhub-publish-<skill>
#                       skillhub → /tmp/skillhub-publish-<skill>
#   skill-path        - 技能目录路径（相对或绝对路径）
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
    echo "用法: prepare-publish.sh [--platform <clawhub|skillhub>] <skill-path>"
    echo ""
    echo "参数:"
    echo "  --platform <name> - 目标平台（默认 clawhub），决定临时目录前缀"
    echo "                      clawhub  → /tmp/clawhub-publish-<skill>"
    echo "                      skillhub → /tmp/skillhub-publish-<skill>"
    echo "  skill-path        - 技能目录路径（相对或绝对路径）"
    echo ""
    echo "功能:"
    echo "  创建临时目录用于发布（ClawHub / 腾讯 SkillHub），自动应用 .gitignore 过滤规则。"
    echo ""
    echo "过滤规则（双重过滤）:"
    echo "  1. 项目根目录的 .gitignore（自动检测）"
    echo "  2. 技能内部的 .gitignore（如果存在）"
    echo ""
    echo "示例:"
    echo "  prepare-publish.sh skills/trademark-assistant"
    echo "  prepare-publish.sh --platform skillhub skills/trademark-assistant"
    echo "  prepare-publish.sh /path/to/skills/trademark-assistant"
    exit 1
}

# 解析参数（支持 --platform 可选参数，向后兼容旧式位置参数）
PLATFORM="clawhub"
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            ;;
        --platform)
            if [ -z "$2" ]; then
                echo -e "${RED}错误: --platform 需要一个参数${NC}" >&2
                exit 1
            fi
            PLATFORM="$2"
            shift 2
            ;;
        --platform=*)
            PLATFORM="${1#--platform=}"
            shift
            ;;
        *)
            SKILL_PATH="$1"
            shift
            ;;
    esac
done

# 校验平台参数
case "$PLATFORM" in
    clawhub|skillhub)
        ;;
    *)
        echo -e "${RED}错误: 不支持的平台 '$PLATFORM'，可选值: clawhub | skillhub${NC}" >&2
        exit 1
        ;;
esac

# 检查参数
if [ -z "$SKILL_PATH" ]; then
    usage
fi

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

# 创建临时目录（前缀随目标平台变化）
TEMP_DIR="/tmp/${PLATFORM}-publish-$SKILL_NAME"
echo -e "${GREEN}准备发布目录（平台: $PLATFORM）: $TEMP_DIR${NC}"

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
    --exclude='**/.env'        # 排除环境变量文件（防止凭证泄露）
    --exclude='**/*.db'        # 排除数据库文件
    --exclude='**/*.sqlite'    # 排除 SQLite 文件
    --exclude='**/logs/'       # 排除日志目录
    --exclude='**/output/'     # 排除输出目录
    --exclude='**/downloads/'  # 排除下载目录
    --exclude='**/archive/'    # 排除运行时缓存目录
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
# 优先使用 git ls-files（100% 精确匹配 Git 追踪状态，避免 rsync 解析 gitignore 不完整导致敏感文件泄露）
# 仅在非 Git 环境下回退到 rsync + 硬编码排除规则

if [ -n "$PROJECT_ROOT" ]; then
    RELATIVE_PATH="${SKILL_PATH#$PROJECT_ROOT/}"
    RELATIVE_PATH="${RELATIVE_PATH%/}"

    echo -e "${GREEN}复制文件到临时目录（git ls-files 模式）...${NC}"

    COPIED=0
    while IFS= read -r -d '' FILE; do
        DEST="${FILE#$RELATIVE_PATH/}"
        DEST_DIR="$TEMP_DIR/$(dirname "$DEST")"
        mkdir -p "$DEST_DIR"
        cp "$PROJECT_ROOT/$FILE" "$TEMP_DIR/$DEST"
        COPIED=$((COPIED + 1))
    done < <(cd "$PROJECT_ROOT" && git ls-files -z -- "$RELATIVE_PATH")

    if [ "$COPIED" -eq 0 ]; then
        echo -e "${RED}错误: git ls-files 未返回任何文件，确认技能已提交${NC}"
        exit 1
    fi
    echo -e "${GREEN}已复制 $COPIED 个文件到临时目录${NC}"
else
    if [ -n "$PROJECT_GITIGNORE" ] || [ -n "$SKILL_GITIGNORE" ]; then
        [ -n "$PROJECT_GITIGNORE" ] && RSYNC_ARGS+=(--filter=":- $PROJECT_GITIGNORE")
        [ -n "$SKILL_GITIGNORE" ] && RSYNC_ARGS+=(--filter=":- $SKILL_GITIGNORE")
    else
        echo -e "${YELLOW}警告: 未找到任何 .gitignore 文件，将只排除默认目录${NC}"
    fi

    echo -e "${GREEN}复制文件到临时目录（rsync 模式）...${NC}"
    rsync "${RSYNC_ARGS[@]}" "$SKILL_PATH/" "$TEMP_DIR/"
fi

# 强制清理 rsync 可能遗漏的运行时目录（.gitignore 路径相对于项目根时 rsync 无法匹配）
for _DIR in archive output downloads logs; do
    [ -d "$TEMP_DIR/$_DIR" ] && rm -rf "$TEMP_DIR/$_DIR" && echo -e "${YELLOW}强制移除: $_DIR/${NC}"
done

# 清理 .gitkeep 占位文件（git 用来追踪空目录，非 skill 内容；部分平台如 SkillHub 拒收该文件类型）
find "$TEMP_DIR" -name '.gitkeep' -delete 2>/dev/null

# ── SkillHub 专用:从本地配置注入 slug/displayName 到临时副本 frontmatter ──
# 设计:源 SKILL.md 不含 slug/displayName(平台元数据与 skill 本体解耦),
#       发布前从此脚本同目录的 ../config/sync-allowlist.yaml 读取并注入临时副本。
#       slug 默认 = skill 目录名;重名/被占用时在配置里用 slug 字段覆盖。
#       displayName 必填(中文展示名),缺失则 fail-closed 退出。
# ClawHub 不触发本段(它用 --slug/--name 命令行参数,不依赖 frontmatter)。
if [ "$PLATFORM" = "skillhub" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    CONFIG_PATH="$SCRIPT_DIR/../config/sync-allowlist.yaml"
    SKILL_MD="$TEMP_DIR/SKILL.md"
    [ -f "$SKILL_MD" ] || SKILL_MD="$TEMP_DIR/skill.md"

    if [ ! -f "$CONFIG_PATH" ]; then
        echo -e "${RED}错误: 未找到白名单配置 $CONFIG_PATH,无法注入 SkillHub frontmatter${NC}" >&2
        exit 1
    fi
    if [ ! -f "$SKILL_MD" ]; then
        echo -e "${RED}错误: 临时目录未找到 SKILL.md: $SKILL_MD${NC}" >&2
        exit 1
    fi

    echo -e "${BLUE}注入 SkillHub frontmatter(slug/displayName)...${NC}"
    INJECT_SKILL="$SKILL_NAME" \
    INJECT_CONFIG="$CONFIG_PATH" \
    INJECT_SKILL_MD="$SKILL_MD" \
    python3 - <<'PYEOF'
import os, re, sys

skill = os.environ['INJECT_SKILL']
config = os.environ['INJECT_CONFIG']
skill_md = os.environ['INJECT_SKILL_MD']

# 1) 从 sync-allowlist.yaml 解析目标 skill 的 display_name / slug
meta = {}
in_block = False
top_re = re.compile(r'^([A-Za-z0-9_.\-]+):\s*(?:#.*)?$')
field_re = re.compile(r'^\s+(display_name|slug)\s*:\s*["\']?(.*?)["\']?\s*(?:#.*)?$')
with open(config, encoding='utf-8') as f:
    for line in f:
        if not in_block:
            m = top_re.match(line)
            if m and m.group(1) == skill:
                in_block = True
            continue
        if line.strip() == '' or line.lstrip().startswith('#'):
            continue
        if not (line.startswith(' ') or line.startswith('\t')):
            break  # 离开当前 skill 块
        fm = field_re.match(line)
        if fm:
            meta[fm.group(1)] = fm.group(2).strip()

if 'display_name' not in meta:
    print(f'错误: sync-allowlist.yaml 中 {skill} 缺少 display_name(SkillHub 发布必填,中文名)', file=sys.stderr)
    sys.exit(1)

slug = meta.get('slug', skill)
display_name = meta['display_name'].replace('"', '\\"')

# 2) 幂等注入到 SKILL.md frontmatter(先删已有 slug/displayName,再在闭合 --- 前插入)
with open(skill_md, encoding='utf-8') as f:
    lines = f.read().split('\n')

out = []
fm_count = 0
injected = False
for line in lines:
    if line.strip() == '---':
        fm_count += 1
        if fm_count == 2 and not injected:
            out.append(f'slug: {slug}')
            out.append(f'displayName: "{display_name}"')
            injected = True
        out.append(line)
        continue
    # frontmatter 内删除已有 slug/displayName(保证幂等)
    if fm_count == 1 and re.match(r'^(slug|displayName)\s*:', line):
        continue
    out.append(line)

if not injected:
    print(f'错误: {skill_md} 未找到 frontmatter 闭合 ---,无法注入', file=sys.stderr)
    sys.exit(1)

with open(skill_md, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))

print(f'  slug={slug}')
print(f'  displayName={display_name}')
PYEOF
    echo -e "${GREEN}已注入 SkillHub frontmatter${NC}"
fi

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
