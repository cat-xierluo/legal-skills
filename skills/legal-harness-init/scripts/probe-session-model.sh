#!/usr/bin/env bash
#
# scripts/probe-session-model.sh - 从当前 harness session jsonl 反查 model
#
# 用途：
#   legal-harness-init 在 init 那一刻拿不到 model（多数 harness 不 export env）。
#   init 后几秒到几分钟内,harness 会把 session 写入 jsonl/trace,可从最近的
#   record 反查 model 字段，覆盖之前 init-environment 表里的 unknown。
#
# 用法：
#   bash scripts/probe-session-model.sh
#   bash scripts/probe-session-model.sh --harness <key> [--cwd <path>] [--within <seconds>]
#   bash scripts/probe-session-model.sh --json
#
# 输出（stdout）：
#   探测成功：仅打印 model 名
#   探测失败：空（退出码非 0）
#   --json: 始终输出 JSON { status, model, evidence, reason, harness, cwd }
#
# 当前支持（v0.5.2）：
#   claude-code: ~/.claude/projects/<encoded-cwd>/*.jsonl → role=assistant.message.model
#   qwenwork:    ~/.qwenworkcn/projects/<encoded-cwd>/*.jsonl → 同(CC 克隆,model 是平台别名)
#   qoderwork:   ~/.qoderworkcn/projects/<encoded-cwd>/*.jsonl → 同(CC 克隆,model 是别名)
#   myagents:    ~/.myagents/sessions/*.jsonl → 同(CC 克隆,flat 不分 cwd,model 较真实)
#   codex:       ~/.codex/sessions/**/rollout-*.jsonl → turn_context.payload.model
#   workbuddy:   ~/.workbuddy/traces/<pid>/trace_*.json → spans[].toolOutput chat.completion.model
#   openclaw:    本机未发现统一会话 jsonl(logs/ 仅补全/审计);按 CC 克隆路径试,失败 not_found
#   orca:        worktree 编排型,session 在各 worktree 的 .claude/projects,~/.orca 无统一 session → not_found
#
# 隐私边界：只读 jsonl/trace 元数据(mtime + model 字段)，不读 message.content /
#           thinking / tool_use 正文;解析只匹配 "model":"<name>" 模式。
#
# 退出码：0 = 找到；1 = 找不到；2 = 参数错误。

set -u

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
WITHIN=600   # 10 分钟内 mtime 的 jsonl/trace 算"当前 session"
JSON_OUTPUT=false

while [ $# -gt 0 ]; do
    case "$1" in
        --harness) [ $# -ge 2 ] || die "--harness 需要参数"; HARNESS_OVERRIDE="$2"; shift 2 ;;
        --cwd)     [ $# -ge 2 ] || die "--cwd 需要参数"; CWD_OVERRIDE="$2"; shift 2 ;;
        --within)  [ $# -ge 2 ] || die "--within 需要参数"; WITHIN="$2"; shift 2 ;;
        --json)    JSON_OUTPUT=true; shift ;;
        -h|--help) sed -n '3,40p' "$0"; exit 0 ;;
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

# ========== 共享 helpers ==========

# CC 克隆 jsonl 提取 model:tail 后找最后一条 role=assistant 的 message.model
# 用于 claude-code / qwenwork / qoderwork / myagents(格式同 CC)
probe_cc_clone_model() {
    local f="$1"
    tail -2000 "$f" 2>/dev/null | awk '
        /"role":"assistant"/ {
            if (match($0, /"model":"[^"]+"/)) {
                current = substr($0, RSTART+9, RLENGTH-10)
                found = 1
            }
        }
        END { if (found) print current; else print "" }
    '
}

# 在 CC 克隆 projects 根下,按 encoded-cwd 找最近 mtime 的 jsonl
# $1=root $2=encoded-cwd;输出 jsonl 绝对路径(找不到为空)
find_cc_clone_jsonl() {
    local root="$1" encoded="$2"
    [ -d "$root" ] || return 1
    local found=""
    while IFS= read -r f; do
        [ -n "$f" ] && found="$f"
    done < <(find "$root" -maxdepth 2 -name "*.jsonl" -type f \
        -path "*${encoded}*" -mmin "-$((WITHIN / 60 + 1))" 2>/dev/null \
        | xargs -I{} stat -f "%m %N" "{}" 2>/dev/null \
        | sort -rn | head -1 | awk '{$1=""; sub(/^ /, ""); print}')
    printf '%s' "$found"
}

# 编码 cwd 为 CC projects 子目录名(每个非字母数字字符变 -)
encode_cwd() {
    printf '%s' "$1" | sed -E 's/[^a-zA-Z0-9]/-/g'
}

# CC 克隆探测通用流程:$1=root。用全局 CWD 编码。
run_cc_clone_probe() {
    local root="$1" encoded jsonl model
    encoded=$(encode_cwd "$CWD")
    jsonl=$(find_cc_clone_jsonl "$root" "$encoded")
    if [ -z "$jsonl" ] || [ ! -f "$jsonl" ]; then
        emit_json "not_found" "" "" "no jsonl mtime in last ${WITHIN}s under $root (encoded=$encoded)"
        return 1
    fi
    model=$(probe_cc_clone_model "$jsonl")
    if [ -n "$model" ]; then
        emit_json "found" "$model" "$jsonl" "CC 克隆 role=assistant 提取 message.model"
        [ "$JSON_OUTPUT" != true ] && printf '%s\n' "$model"
        return 0
    fi
    emit_json "not_found" "" "$jsonl" "jsonl 存在但无 role=assistant 记录或 message.model"
    return 1
}

# ========== 平台分支 ==========

case "$HARNESS" in
    claude-code)
        run_cc_clone_probe "$HOME/.claude/projects" || exit 1
        ;;
    qwenwork)
        run_cc_clone_probe "$HOME/.qwenworkcn/projects" || exit 1
        ;;
    qoderwork)
        run_cc_clone_probe "$HOME/.qoderworkcn/projects" || exit 1
        ;;
    myagents)
        # myagents sessions flat 不分 cwd,取最近 mtime 最大者
        root="$HOME/.myagents/sessions"
        if [ ! -d "$root" ]; then
            emit_json "not_found" "" "" "sessions_root 不存在: $root"
            exit 1
        fi
        jsonl=""
        while IFS= read -r f; do
            [ -n "$f" ] && jsonl="$f"
        done < <(find "$root" -maxdepth 1 -name "*.jsonl" -type f \
            -mmin "-$((WITHIN / 60 + 1))" 2>/dev/null \
            | xargs -I{} stat -f "%m %N" "{}" 2>/dev/null \
            | sort -rn | head -1 | awk '{$1=""; sub(/^ /, ""); print}')
        if [ -z "$jsonl" ] || [ ! -f "$jsonl" ]; then
            emit_json "not_found" "" "" "no session jsonl mtime in last ${WITHIN}s under $root"
            exit 1
        fi
        model=$(probe_cc_clone_model "$jsonl")
        if [ -n "$model" ]; then
            emit_json "found" "$model" "$jsonl" "myagents session role=assistant message.model"
            [ "$JSON_OUTPUT" != true ] && printf '%s\n' "$model"
            exit 0
        fi
        emit_json "not_found" "" "$jsonl" "session jsonl 存在但无 role=assistant 或 message.model"
        exit 1
        ;;
    codex)
        sessions_root="$HOME/.codex/sessions"
        if [ ! -d "$sessions_root" ]; then
            emit_json "not_found" "" "" "sessions_root 不存在: $sessions_root"
            exit 1
        fi
        jsonl_file=""
        while IFS= read -r f; do
            [ -n "$f" ] && jsonl_file="$f"
        done < <(find "$sessions_root" -name "rollout-*.jsonl" -type f \
            -mmin "-$((WITHIN / 60 + 1))" 2>/dev/null \
            | xargs -I{} stat -f "%m %N" "{}" 2>/dev/null \
            | sort -rn | head -1 | awk '{$1=""; sub(/^ /, ""); print}')
        if [ -z "$jsonl_file" ] || [ ! -f "$jsonl_file" ]; then
            emit_json "not_found" "" "" "no rollout jsonl mtime in last ${WITHIN}s under $sessions_root"
            exit 1
        fi
        # 最后一条 turn_context 的 payload.model
        model=$(grep '"type":"turn_context"' "$jsonl_file" 2>/dev/null | awk '
            { if (match($0, /"model":"[^"]+"/)) { current = substr($0, RSTART+9, RLENGTH-10); found = 1 } }
            END { if (found) print current; else print "" }
        ')
        if [ -n "$model" ]; then
            emit_json "found" "$model" "$jsonl_file" "最后一条 turn_context 提取 payload.model"
            [ "$JSON_OUTPUT" != true ] && printf '%s\n' "$model"
            exit 0
        fi
        emit_json "not_found" "" "$jsonl_file" "rollout 存在但无 turn_context 记录或 payload.model"
        exit 1
        ;;
    workbuddy)
        traces_root="$HOME/.workbuddy/traces"
        if [ ! -d "$traces_root" ]; then
            emit_json "not_found" "" "" "traces_root 不存在: $traces_root"
            exit 1
        fi
        # traces/<pid>/trace_*.json;每个操作一个 trace,只有 generation 类含 model。
        # 按 mtime 降序遍历,第一个含 "model":"..." 的就用(最新一次 generation)。
        trace_file=""
        model=""
        while IFS= read -r f; do
            [ -z "$f" ] && continue
            # toolOutput 是 JSON 字符串,model 字段的引号被转义为 \",先去反斜杠再 grep
            m=$(sed 's/\\//g' "$f" 2>/dev/null | grep -oE '"model":"[^"]+"' | tail -1 \
                | sed -E 's/^"model":"([^"]+)"$/\1/')
            if [ -n "$m" ]; then
                trace_file="$f"
                model="$m"
                break
            fi
        done < <(find "$traces_root" -name "trace_*.json" -type f \
            -mmin "-$((WITHIN / 60 + 1))" 2>/dev/null \
            | xargs -I{} stat -f "%m %N" "{}" 2>/dev/null \
            | sort -rn | awk '{$1=""; sub(/^ /, ""); print}')
        if [ -n "$model" ]; then
            emit_json "found" "$model" "$trace_file" "trace(mtime 最新含 model)spans toolOutput chat.completion.model"
            [ "$JSON_OUTPUT" != true ] && printf '%s\n' "$model"
            exit 0
        fi
        emit_json "not_found" "" "" "最近 ${WITHIN}s 内无含 chat.completion.model 的 trace(可能都是工具调用类)"
        exit 1
        ;;
    openclaw)
        # OpenClaw 是 CC fork;本机 logs/ 仅补全/审计无会话 jsonl。
        # 先按 CC 克隆常见路径试(~/.openclaw/sessions 或 projects),失败标 not_found。
        run_cc_clone_probe "$HOME/.openclaw/sessions" && exit 0
        run_cc_clone_probe "$HOME/.openclaw/projects" && exit 0
        emit_json "not_found" "" "" "openclaw 本机无统一会话 jsonl(logs/ 仅补全/审计);CC fork 会话路径待研究"
        exit 1
        ;;
    orca)
        # worktree 编排型:session 在各 worktree 的 .claude/projects,~/.orca 无统一 session
        emit_json "not_found" "" "" "orca 是 worktree 编排型,~/.orca 无统一 session(在各 worktree 内);不可自动反查"
        exit 1
        ;;
    *)
        emit_json "not_found" "" "" "未知 harness: $HARNESS"
        exit 1
        ;;
esac
