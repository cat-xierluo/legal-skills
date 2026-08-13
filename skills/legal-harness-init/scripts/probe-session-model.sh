#!/usr/bin/env bash
#
# scripts/probe-session-model.sh - 从当前 harness session jsonl 反查 model
#
# 用途：
#   legal-harness-init 在 init 那一刻拿不到 model（多数 harness 不 export env）。
#   init 后几秒到几分钟内,harness 会把 session 写入 jsonl,可从最近的 jsonl
#   record 反查 message.model 字段，覆盖之前 init-environment 表里的 unknown。
#
# 用法：
#   bash scripts/probe-session-model.sh
#   bash scripts/probe-session-model.sh --harness <key> [--cwd <path>] [--within <seconds>]
#   bash scripts/probe-session-model.sh --json    # 输出 JSON 含 evidence 路径
#
# 输出（stdout）：
#   探测成功：仅打印 model 名（如 `claude-fable-5`）
#   探测失败：空（退出码非 0）
#   --json: 始终输出 JSON { "status": "found"|"not_found", "model": "...", "evidence": "..." }
#
# 当前支持：
#   claude-code: ~/.claude/projects/<encoded-cwd>/*.jsonl，最近 <within> 秒内 mtime；
#                读最新一条 type=assistant 记录的 message.model 字段
#
#   暂不支持（v0.5.1+ 再扩）：codex / openclaw / myagents / qoderwork /
#                qwenwork / workbuddy / orca
#   失败原因在 --json 的 reason 字段标注
#
# 隐私边界：只读 jsonl 元数据（mtime / 顶层 record 字段），不读 message.content；
#           解析只匹配 "model":"<name>" 模式，不回显 thinking / tool_use 正文。
#
# 退出码：0 = 找到；1 = 找不到；2 = 参数错误。

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

die() {
    printf 'probe-session-model.sh: 错误：%s\n' "$*" >&2
    exit 2
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

HARNESS_OVERRIDE=""
CWD_OVERRIDE=""
WITHIN=600   # 10 分钟内 mtime 的 jsonl 算"当前 session"
JSON_OUTPUT=false

while [ $# -gt 0 ]; do
    case "$1" in
        --harness) [ $# -ge 2 ] || die "--harness 需要参数"; HARNESS_OVERRIDE="$2"; shift 2 ;;
        --cwd)     [ $# -ge 2 ] || die "--cwd 需要参数"; CWD_OVERRIDE="$2"; shift 2 ;;
        --within)  [ $# -ge 2 ] || die "--within 需要参数"; WITHIN="$2"; shift 2 ;;
        --json)    JSON_OUTPUT=true; shift ;;
        -h|--help) sed -n '3,30p' "$0"; exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
done

CWD="${CWD_OVERRIDE:-$PWD}"
HARNESS="${HARNESS_OVERRIDE:-claude-code}"
# 宽容兜底:harness=unknown(agent 没识别出来)时按 CC 试
[ "$HARNESS" = "unknown" ] && HARNESS="claude-code"

emit_json() {
    local status="$1" model="$2" evidence="$3" reason="$4"
    if [ "$JSON_OUTPUT" = true ]; then
        cat <<EOF
{"schema_version":"1","status":"$(json_escape "$status")","model":"$(json_escape "$model")","evidence":"$(json_escape "$evidence")","reason":"$(json_escape "$reason")","harness":"$(json_escape "$HARNESS")","cwd":"$(json_escape "$CWD")"}
EOF
    fi
}

# === CC: ~/.claude/projects/<encoded-cwd>/*.jsonl ===
if [ "$HARNESS" = "claude-code" ]; then
    # CC 编码规则：每个非字母数字字符（/, 空格, . 等）变 -,不去重
    encoded=$(printf '%s' "$CWD" | sed -E 's/[^a-zA-Z0-9]/-/g')
    projects_dir="$HOME/.claude/projects/${encoded}"
    if [ ! -d "$projects_dir" ]; then
        emit_json "not_found" "" "" "projects_dir 不存在: $projects_dir"
        exit 1
    fi

    # 找 mtime 在 WITHIN 秒内最大的 jsonl
    jsonl_file=""
    while IFS= read -r f; do
        jsonl_file="$f"
    done < <(find "$projects_dir" -maxdepth 1 -name "*.jsonl" -type f -mmin "-$((WITHIN / 60 + 1))" 2>/dev/null | xargs -I{} stat -f "%m %N" "{}" 2>/dev/null | sort -rn | head -1 | awk '{$1=""; sub(/^ /, ""); print}')

    if [ -z "$jsonl_file" ] || [ ! -f "$jsonl_file" ]; then
        emit_json "not_found" "" "" "no jsonl mtime in last ${WITHIN}s under $projects_dir"
        exit 1
    fi

    # 找最后一条 role=assistant 的 record 提取 message.model
    # jsonl 每条 record 一行，message 嵌套对象内含 role + model。
    # awk 逐行处理：保留最后一条 role=assistant 的 model 字段。
    model=$(tail -2000 "$jsonl_file" 2>/dev/null | awk '
        /"role":"assistant"/ {
            # 在本行内匹配 "model":"..."
            if (match($0, /"model":"[^"]+"/)) {
                current = substr($0, RSTART+9, RLENGTH-10)
                found = 1
            }
        }
        END { if (found) print current; else print "" }
    ')
    if [ -n "$model" ]; then
        emit_json "found" "$model" "$jsonl_file" "tail role=assistant 提取 message.model"
        if [ "$JSON_OUTPUT" != true ]; then
            printf '%s\n' "$model"
        fi
        exit 0
    fi

    emit_json "not_found" "" "$jsonl_file" "jsonl 存在但无 role=assistant 记录或 message.model 字段"
    exit 1
fi

# === Codex / OpenClaw / MyAgents / QoderWork / QwenWork / WorkBuddy / Orca ===
# v0.5.0 暂不支持；Codex jsonl 嵌套 payload.turn_context.model 需要更复杂解析
# 留 v0.5.1+ 实现
emit_json "not_found" "" "" "harness=$HARNESS 在 v0.5.0 暂未实现（codex 留 v0.5.1）"
exit 1
