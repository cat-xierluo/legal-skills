#!/usr/bin/env bash
#
# scripts/record-init-env.sh - 在被初始化的项目里 append 一条 init 环境元数据
#
# 用途：
#   legal-harness-init 每完成一次 init / update / append，
#   都应在被初始化的项目里 append 一行"用了哪个 harness + 哪个 model"的元数据，
#   供将来追溯"问题出在 harness 层面还是 model 层面"。
#
# 用法：
#   bash scripts/record-init-env.sh \
#     --target <AGENTS.md|CLAUDE.md> \
#     [--model <model-name>] \
#     [--action <init|update|append>] \
#     [--harness <key>] \
#     [--harness-version <v>] \
#     [--skill-version <v>] \
#     [--note <extra>] \
#     [--dry-run]
#
# 行为：
#   - 自动采集 harness(name)：优先 --harness，否则 source detect.sh 取 current_runtime。
#   - 自动采集 harness version：探测 harness 自带 --version 命令，超时 2s 失败兜底 unknown。
#   - 自动采集 model：env 白名单 (ANTHROPIC_MODEL/OPENAI_MODEL/CLAUDE_MODEL/GLM_MODEL/MY_MODEL)；
#     命中即填，都未命中 → 强制 --model 必填（不臆造）。
#   - 自动采集 init skill version：从本 skill 根的 SKILL.md frontmatter 读 version。
#   - 写：在 --target 的 init-environment 受管区块 append 一行表格行；
#     受管区块不存在则创建（带表头）。
#   - 失败关闭：参数非法、target 不存在、candidate marker 不完整或整体结构异常均拒绝。
#
# 退出码：0 = 成功 / unchanged / dry_run；1 = 写入失败；2 = 参数错误。
#
# 隐私边界：harness / model / version 是协作元数据，**不是**案件事实；
#           不进 .legal-context.local.md，也不被 strict / local / team 模式差异化拒绝。

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib_platforms.sh
. "${SCRIPT_DIR}/lib_platforms.sh"

BLOCK_ID="init-environment"
START_MARKER="<!-- legal-harness-init:${BLOCK_ID}:start -->"
END_MARKER="<!-- legal-harness-init:${BLOCK_ID}:end -->"

die() {
    printf 'record-init-env.sh: 错误：%s\n' "$*" >&2
    exit 1
}

json_escape() {
    local s="${1-}"
    s=${s//\\/\\\\}
    s=${s//\"/\\\"}
    s=${s//$'\n'/\\n}
    s=${s//$'\r'/\\r}
    s=${s//$'\t'/\\t}
    printf '%s' "$s"
}

# 探测一个命令，2s 超时，失败返回空（绝不读凭证，绝不循环）
probe_with_timeout() {
    local cmd="$1"
    if command -v timeout >/dev/null 2>&1; then
        timeout 2s sh -c "$cmd" 2>/dev/null | head -1 || true
    elif command -v gtimeout >/dev/null 2>&1; then
        gtimeout 2s sh -c "$cmd" 2>/dev/null | head -1 || true
    else
        sh -c "$cmd" 2>/dev/null | head -1 || true
    fi
}

# === 解析参数 ===
TARGET=""
MODEL=""
ACTION="init"
HARNESS_OVERRIDE=""
HARNESS_VERSION_OVERRIDE=""
SKILL_VERSION_OVERRIDE=""
NOTE=""
DRY_RUN=false

while [ $# -gt 0 ]; do
    case "$1" in
        --target) [ $# -ge 2 ] || { die "--target 需要参数"; }; TARGET="$2"; shift 2 ;;
        --model) [ $# -ge 2 ] || { die "--model 需要参数"; }; MODEL="$2"; shift 2 ;;
        --action) [ $# -ge 2 ] || { die "--action 需要参数"; }; ACTION="$2"; shift 2 ;;
        --harness) [ $# -ge 2 ] || { die "--harness 需要参数"; }; HARNESS_OVERRIDE="$2"; shift 2 ;;
        --harness-version) [ $# -ge 2 ] || { die "--harness-version 需要参数"; }; HARNESS_VERSION_OVERRIDE="$2"; shift 2 ;;
        --skill-version) [ $# -ge 2 ] || { die "--skill-version 需要参数"; }; SKILL_VERSION_OVERRIDE="$2"; shift 2 ;;
        --note) [ $# -ge 2 ] || { die "--note 需要参数"; }; NOTE="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help) sed -n '3,30p' "$0"; exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
done

[ -n "$TARGET" ] || die "缺 --target"
[ -f "$TARGET" ] || die "目标文件不存在：$TARGET"
case "$ACTION" in init|update|append) ;; *) die "--action 必须是 init / update / append" ;; esac

# === 采集 harness name ===
HARNESS_NAME=""
if [ -n "$HARNESS_OVERRIDE" ]; then
    if ! _platform_meta_line "$HARNESS_OVERRIDE" >/dev/null 2>&1; then
        die "未知平台 key：${HARNESS_OVERRIDE}（不在 lib_platforms.sh 权威表）"
    fi
    HARNESS_NAME="$HARNESS_OVERRIDE"
else
    detect_json=$(bash "${SCRIPT_DIR}/detect.sh" 2>/dev/null || true)
    HARNESS_NAME=$(printf '%s' "$detect_json" | sed -n 's/.*"current_runtime":[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi
[ -n "$HARNESS_NAME" ] || HARNESS_NAME="unknown"

# === 采集 harness version（探测自带 --version；非 claude/codex 标 n/a）===
HARNESS_VERSION=""
if [ -n "$HARNESS_VERSION_OVERRIDE" ]; then
    HARNESS_VERSION="$HARNESS_VERSION_OVERRIDE"
else
    case "$HARNESS_NAME" in
        claude-code) HARNESS_VERSION=$(probe_with_timeout "claude --version") ;;
        codex)       HARNESS_VERSION=$(probe_with_timeout "codex --version") ;;
        openclaw|myagents|qoderwork|qwenwork|workbuddy|orca) HARNESS_VERSION="n/a" ;;
        *)           HARNESS_VERSION="unknown" ;;
    esac
    # 标准化：剥前缀和空行
    HARNESS_VERSION=$(printf '%s' "$HARNESS_VERSION" | sed -E 's/^(claude-code|codex)[[:space:]]+//;s/^$//')
    [ -n "$HARNESS_VERSION" ] || HARNESS_VERSION="unknown"
fi

# === 采集 model（env 白名单 + 兜底）===
# 预设白名单：harness 直接 export 的标准 model env（按经验+用户可 export 顺序）
# - ANTHROPIC_MODEL: Claude 系直接 export
# - OPENAI_MODEL: OpenAI 系直接 export
# - CLAUDE_MODEL: 部分 Claude fork (Claude-in-Slack 等)
# - GLM_MODEL: 智谱系（GLM-4 / GLM-5.2 / GLM-MiniMax-M3）
# - CODEX_MODEL / OPENAI_MODEL_GLM: 部分 Codex 包装层 export
# - MYAGENTS_MODEL / QWEN_MODEL: MyAgents / QwenWork 等"用户友好"名
# - MY_MODEL: 用户兜底 export（agent 在 self-aware 后自行 export 自己的 model）
if [ -z "$MODEL" ]; then
    for envname in ANTHROPIC_MODEL OPENAI_MODEL CLAUDE_MODEL GLM_MODEL CODEX_MODEL OPENAI_MODEL_GLM MYAGENTS_MODEL QWEN_MODEL MY_MODEL; do
        if [ -n "${!envname+x}" ] && [ -n "${!envname}" ]; then
            MODEL=$(printf '%s' "${!envname}" | head -1)
            break
        fi
    done
fi
if [ -z "$MODEL" ]; then
    cat >&2 <<EOF
record-init-env.sh: 错误：model 探测失败。

env 白名单 (ANTHROPIC_MODEL / OPENAI_MODEL / CLAUDE_MODEL / GLM_MODEL /
CODEX_MODEL / OPENAI_MODEL_GLM / MYAGENTS_MODEL / QWEN_MODEL / MY_MODEL)
均未命中。

自助补 model 的两条简单路径：

  1. export 后重跑（推荐，让 agent 自检自填）：
       export MY_MODEL="<你的 model 名>"
       bash scripts/record-init-env.sh --target <AGENTS.md> --action <init|update|append>

  2. --model 兜底（一次性）：
       bash scripts/record-init-env.sh --target <AGENTS.md> --action <init|update|append> \\
         --model "<你的 model 名>"

为什么不臆造：harness 实际 model 名称在 init 时不可见；env 白名单 + --model
兜底是当前最稳的"模型自检自填"路径。详见 references/22-initialization-environment.md §自助补 model。
EOF
    die "model 未提供"
fi

# === 采集 init skill version（SKILL.md frontmatter）===
SKILL_VERSION=""
if [ -n "$SKILL_VERSION_OVERRIDE" ]; then
    SKILL_VERSION="$SKILL_VERSION_OVERRIDE"
else
    skill_root=$(cd "${SCRIPT_DIR}/.." && pwd)
    skill_md="${skill_root}/SKILL.md"
    if [ -f "$skill_md" ]; then
        SKILL_VERSION=$(awk '/^version:[[:space:]]*"/ { gsub(/^version:[[:space:]]*"|"[[:space:]]*$/, ""); print; exit }' "$skill_md")
    fi
fi
[ -n "$SKILL_VERSION" ] || SKILL_VERSION="unknown"

# === 采集时间 ===
TIMESTAMP=$(date '+%Y-%m-%d %H:%M' 2>/dev/null || printf 'unknown-time')

# === 构造新行（markdown 表格行；字段含 | 时由 --note 自行转义为 \\|）===
NOTE_CELL=""
[ -n "$NOTE" ] && NOTE_CELL=" · ${NOTE}"
NEW_ROW="| ${TIMESTAMP} | ${HARNESS_NAME} | ${HARNESS_VERSION} | ${MODEL} | legal-harness-init | ${SKILL_VERSION} | ${ACTION}${NOTE_CELL} |"

# === 判断 init-environment 区块状态 ===
#   - start/end 都成对存在 → append
#   - 都不存在 → create
#   - 只存在一个（残缺）→ die（避免破坏不完整区块）
start_count=$(grep -Fxc -- "$START_MARKER" "$TARGET" 2>/dev/null || true)
end_count=$(grep -Fxc -- "$END_MARKER" "$TARGET" 2>/dev/null || true)
if [ "$start_count" -eq 1 ] && [ "$end_count" -eq 1 ]; then
    MODE="append"
elif [ "$start_count" -eq 0 ] && [ "$end_count" -eq 0 ]; then
    MODE="create"
else
    die "目标文件 ${TARGET} 的 init-environment 区块残缺（start=${start_count} end=${end_count}）；请先人工修复再 append"
fi

# === 构造 candidate ===
target_dir=$(dirname -- "$TARGET")
[ "$target_dir" = "/" ] && target_dir=""
candidate=$(mktemp "${target_dir}/.record-init-env.XXXXXX") || die "无法创建候选文件"
if [ "$MODE" = "create" ]; then
    {
        cat "$TARGET"
        # 若 target 不以换行结尾,补一个,避免与新追加区块粘连
        if [ -s "$TARGET" ] && [ "$(tail -c 1 "$TARGET")" != "" ] && [ "$(tail -c 1 "$TARGET" | wc -l)" -eq 0 ]; then
            printf '\n'
        fi
        printf '\n%s\n' "$START_MARKER"
        printf '| 时间 | Harness | Harness Version | Model | Init Skill | Init Skill Version | 操作 |\n'
        printf '|---|---|---|---|---|---|---|\n'
        printf '%s\n' "$NEW_ROW"
        printf '\n%s\n' "$END_MARKER"
    } > "$candidate"
else
    # 在 END_MARKER 之前插入新行
    awk -v row="$NEW_ROW" -v end="$END_MARKER" '
        $0 == end {
            print row
            print ""
        }
        { print }
    ' "$TARGET" > "$candidate"
fi

# === 校验 candidate marker 单点出现 + 整体结构 ===
start_count=$(grep -Fxc -- "$START_MARKER" "$candidate" || true)
end_count=$(grep -Fxc -- "$END_MARKER" "$candidate" || true)
if [ "$start_count" -ne 1 ] || [ "$end_count" -ne 1 ]; then
    rm -f "$candidate"
    die "candidate 受管 marker 校验失败（start=${start_count} end=${end_count}）"
fi

if ! awk '
    /<!--[[:space:]]*legal-harness-init:/ && !/^<!--[[:space:]]legal-harness-init:[a-z0-9-]+:(start|end)[[:space:]]-->$/ { bad=1 }
    /^<!--[[:space:]]legal-harness-init:[a-z0-9-]+:start[[:space:]]-->$/ {
        if (open != "" || ++starts[$0] > 1) bad=1
        open=$0
    }
    /^<!--[[:space:]]legal-harness-init:[a-z0-9-]+:end[[:space:]]-->$/ {
        if (open == "" || ++ends[$0] > 1) bad=1
        open=""
    }
    END { exit (bad || open != "") ? 1 : 0 }
' "$candidate"; then
    rm -f "$candidate"
    die "candidate 全部受管 marker 结构校验失败"
fi

# === unchanged 检查 ===
if cmp -s "$TARGET" "$candidate"; then
    rm -f "$candidate"
    cat <<EOF
{"schema_version":"1","status":"unchanged","target":"$(json_escape "$TARGET")","row":"$(json_escape "$NEW_ROW")","mode":"$MODE"}
EOF
    exit 0
fi

# === dry-run ===
if [ "$DRY_RUN" = true ]; then
    printf '=== [dry-run] %s init-environment 区块将 %s ===\n' "$TARGET" "$MODE" >&2
    diff -u "$TARGET" "$candidate" >&2 || true
    rm -f "$candidate"
    cat <<EOF
{"schema_version":"1","status":"dry_run","target":"$(json_escape "$TARGET")","row":"$(json_escape "$NEW_ROW")","mode":"$MODE"}
EOF
    exit 0
fi

# === 写回（原子 mv）===
if ! mv "$candidate" "$TARGET"; then
    rm -f "$candidate"
    die "原子替换失败"
fi

# === 行数软上限提示（>50 行建议归档；不阻断）===
rows=0
soft_note=""
if [ "$MODE" = "append" ]; then
    rows=$(awk -v start="$START_MARKER" -v end="$END_MARKER" '
        $0 == start { in_block = 1; next }
        $0 == end   { in_block = 0 }
        in_block && /^\|/ { count++ }
        END { print count + 0 }
    ' "$TARGET")
    if [ "$rows" -gt 50 ]; then
        soft_note="表格行数 ${rows} 超过 50 行软上限；建议手动归档到 docs/init-environment-history.md 并清空本表"
        printf '⚠️  %s\n' "$soft_note" >&2
    fi
fi

cat <<EOF
{"schema_version":"1","status":"recorded","target":"$(json_escape "$TARGET")","row":"$(json_escape "$NEW_ROW")","mode":"$MODE","rows":$rows}
EOF
