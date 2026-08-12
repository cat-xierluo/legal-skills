#!/usr/bin/env bash
# 将“文件写入”“新会话加载”“行为符合”拆成三个可审计状态。
# session evidence 使用 key=value；必须来自新启动的目标 harness 会话，而非当前写入进程自报。

set -u

die() {
    printf 'verify.sh: 错误：%s\n' "$*" >&2
    exit 2
}

json_escape() {
    local s="${1-}"
    s=${s//\\/\\\\}; s=${s//\"/\\\"}; s=${s//$'\n'/\\n}; s=${s//$'\r'/\\r}; s=${s//$'\t'/\\t}
    printf '%s' "$s"
}

sha256_file() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        printf ''
    fi
}

evidence_value() {
    local key="$1" file="$2"
    awk -F= -v wanted="$key" '$1 == wanted { sub(/^[^=]*=/, ""); print; exit }' "$file"
}

TARGET=""
BLOCK_ID=""
EVIDENCE_FILE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --target) [ $# -ge 2 ] || die "--target 需要参数"; TARGET="$2"; shift 2 ;;
        --block-id) [ $# -ge 2 ] || die "--block-id 需要参数"; BLOCK_ID="$2"; shift 2 ;;
        --session-evidence) [ $# -ge 2 ] || die "--session-evidence 需要参数"; EVIDENCE_FILE="$2"; shift 2 ;;
        -h|--help) sed -n '1,25p' "$0"; exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
done

[ -n "$TARGET" ] || die "缺 --target"
[ -n "$BLOCK_ID" ] || die "缺 --block-id"

START_MARKER="<!-- legal-harness-init:${BLOCK_ID}:start -->"
END_MARKER="<!-- legal-harness-init:${BLOCK_ID}:end -->"
config_written=false
target_sha=""
if [ -s "$TARGET" ]; then
    start_count=$(awk -v marker="$START_MARKER" '$0 == marker { count++ } END { print count + 0 }' "$TARGET")
    end_count=$(awk -v marker="$END_MARKER" '$0 == marker { count++ } END { print count + 0 }' "$TARGET")
    markers_valid=false
    if awk '
        /<!--[[:space:]]*legal-harness-init:/ && $0 !~ /^<!--[[:space:]]legal-harness-init:[a-z0-9-]+:(start|end)[[:space:]]-->$/ { bad=1 }
        /^<!--[[:space:]]legal-harness-init:[a-z0-9-]+:(start|end)[[:space:]]-->$/ {
            marker=$0
            id=marker
            sub(/^<!--[[:space:]]legal-harness-init:/, "", id)
            sub(/:(start|end)[[:space:]]-->$/, "", id)
            kind=marker
            sub(/^.*:/, "", kind)
            sub(/[[:space:]]-->$/, "", kind)
            if (kind == "start") {
                if (open != "" || ++starts[id] > 1) bad=1
                open=id
            } else {
                if (open != id || ++ends[id] > 1) bad=1
                open=""
            }
        }
        END {
            if (open != "") bad=1
            for (id in starts) if (starts[id] != ends[id]) bad=1
            exit bad ? 1 : 0
        }
    ' "$TARGET"; then
        markers_valid=true
    fi
    if [ "$start_count" -eq 1 ] && [ "$end_count" -eq 1 ] && [ "$markers_valid" = true ]; then
        target_sha=$(sha256_file "$TARGET")
        [ -n "$target_sha" ] && config_written=true
    fi
fi

instructions_loaded=false
behavior_verified=false
evidence_note="未提供新会话证据"
if [ -n "$EVIDENCE_FILE" ]; then
    [ -f "$EVIDENCE_FILE" ] || die "证据文件不存在：$EVIDENCE_FILE"
    evidence_new_session=$(evidence_value new_session "$EVIDENCE_FILE")
    evidence_loaded=$(evidence_value loaded "$EVIDENCE_FILE")
    evidence_source=$(evidence_value source_path "$EVIDENCE_FILE")
    evidence_sha=$(evidence_value config_sha256 "$EVIDENCE_FILE")
    if [ "$config_written" = true ] \
        && [ "$evidence_new_session" = true ] \
        && [ "$evidence_loaded" = true ] \
        && [ "$evidence_source" = "$TARGET" ] \
        && [ "$evidence_sha" = "$target_sha" ]; then
        instructions_loaded=true
        evidence_note="新会话报告了精确来源路径"
        if [ "$(evidence_value probe_permission "$EVIDENCE_FILE")" = pass ] \
            && [ "$(evidence_value probe_confidentiality "$EVIDENCE_FILE")" = pass ] \
            && [ "$(evidence_value probe_information_gap "$EVIDENCE_FILE")" = pass ] \
            && [ "$(evidence_value probe_traceability "$EVIDENCE_FILE")" = pass ]; then
            behavior_verified=true
            evidence_note="新会话加载成功且四类行为探针全部通过"
        fi
    else
        evidence_note="配置结构或证据未满足 config_written=true、new_session=true、loaded=true、精确 source_path 与当前 config_sha256"
    fi
fi

if [ "$behavior_verified" = true ]; then
    status="BEHAVIOR_VERIFIED"
elif [ "$instructions_loaded" = true ]; then
    status="INSTRUCTIONS_LOADED"
elif [ "$config_written" = true ]; then
    status="CONFIG_WRITTEN"
else
    status="NOT_VERIFIED"
fi

cat <<EOF
{"schema_version":"1","status":"$(json_escape "$status")","config_written":$config_written,"instructions_loaded":$instructions_loaded,"behavior_verified":$behavior_verified,"target":"$(json_escape "$TARGET")","target_sha256":"$(json_escape "$target_sha")","block_id":"$(json_escape "$BLOCK_ID")","note":"$(json_escape "$evidence_note")"}
EOF

[ "$config_written" = true ]
