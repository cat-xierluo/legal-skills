#!/usr/bin/env bash
#
# scripts/write.sh - 将 legal-harness-init 受管区块安全写入 harness 配置
#
# 用法：
#   bash scripts/write.sh \
#     --content-file <file> \
#     --level <user|project> \
#     [--platforms <key1,key2>] \
#     [--mode <create|update|append>] \
#     [--block-id <kebab-id>] \
#     [--privacy-mode <strict|local|team>] \
#     [--project-dir <path>] [--dry-run] [--force]
#
# 安全契约：
#   - 实际目标路径去重，多平台共用 AGENTS.md 时只写一次。
#   - 只 upsert legal-harness-init 受管区块，不覆盖区块外的用户内容。
#   - 首次更新保留 .bak.legal-harness-init 原始备份及权限/哈希元数据；每次变更再保留唯一快照。
#   - 候选文件在目标同目录生成并原子 mv；用户级文件与备份强制 0600。
#   - create + 已存在默认只报 needs_confirmation；--force 或 update/append 才落盘。
#
# 退出码：0 = 成功 / 无变更 / needs_confirmation；1 = 参数、校验或写入失败。

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib_platforms.sh
. "${SCRIPT_DIR}/lib_platforms.sh"

json_escape() {
    local s="${1-}"
    s=${s//\\/\\\\}
    s=${s//\"/\\\"}
    s=${s//$'\n'/\\n}
    s=${s//$'\r'/\\r}
    s=${s//$'\t'/\\t}
    printf '%s' "$s"
}

die() {
    printf 'write.sh: 错误：%s\n' "$*" >&2
    exit 1
}

sha256_file() {
    local file="$1"
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$file" | awk '{print $1}'
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$file" | awk '{print $1}'
    else
        printf ''
    fi
}

file_mode() {
    local file="$1"
    stat -f '%Lp' "$file" 2>/dev/null || stat -c '%a' "$file" 2>/dev/null || printf '644'
}

CONTENT_FILE=""
LEVEL=""
PLATFORMS_ARG=""
MODE="create"
PROJECT_DIR=""
DRY_RUN=false
FORCE=false
BLOCK_ID=""
PRIVACY_MODE="strict"
RECORD_INIT_ENV="true"
INIT_ACTION="init"
MODEL=""

while [ $# -gt 0 ]; do
    case "$1" in
        --content-file) [ $# -ge 2 ] || die "--content-file 需要参数"; CONTENT_FILE="$2"; shift 2 ;;
        --level) [ $# -ge 2 ] || die "--level 需要参数"; LEVEL="$2"; shift 2 ;;
        --platforms) [ $# -ge 2 ] || die "--platforms 需要参数"; PLATFORMS_ARG="$2"; shift 2 ;;
        --mode) [ $# -ge 2 ] || die "--mode 需要参数"; MODE="$2"; shift 2 ;;
        --project-dir) [ $# -ge 2 ] || die "--project-dir 需要参数"; PROJECT_DIR="$2"; shift 2 ;;
        --block-id) [ $# -ge 2 ] || die "--block-id 需要参数"; BLOCK_ID="$2"; shift 2 ;;
        --privacy-mode) [ $# -ge 2 ] || die "--privacy-mode 需要参数"; PRIVACY_MODE="$2"; shift 2 ;;
        --record-init-env) [ $# -ge 2 ] || die "--record-init-env 需要参数"; RECORD_INIT_ENV="$2"; shift 2 ;;
        --init-action) [ $# -ge 2 ] || die "--init-action 需要参数"; INIT_ACTION="$2"; shift 2 ;;
        --model) [ $# -ge 2 ] || die "--model 需要参数"; MODEL="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --force) FORCE=true; shift ;;
        -h|--help) sed -n '3,30p' "$0"; exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
done

[ -n "$CONTENT_FILE" ] || die "缺 --content-file"
[ -f "$CONTENT_FILE" ] || die "内容文件不存在：$CONTENT_FILE"
[ -s "$CONTENT_FILE" ] || die "内容文件为空：$CONTENT_FILE"
case "$LEVEL" in user|project) ;; *) die "--level 必须是 user 或 project" ;; esac
case "$MODE" in create|update|append) ;; *) die "--mode 必须是 create / update / append" ;; esac
case "$PRIVACY_MODE" in strict|local|team) ;; *) die "--privacy-mode 必须是 strict / local / team" ;; esac
case "$RECORD_INIT_ENV" in true|false) ;; *) die "--record-init-env 必须是 true 或 false" ;; esac
case "$INIT_ACTION" in init|update|append) ;; *) die "--init-action 必须是 init / update / append" ;; esac

[ -n "$BLOCK_ID" ] || BLOCK_ID="legal-baseline-${LEVEL}"
case "$BLOCK_ID" in
    *[!a-z0-9-]*|''|-*|*-) die "--block-id 必须是非空 kebab-case，且不能以连字符开头或结尾" ;;
esac

START_MARKER="<!-- legal-harness-init:${BLOCK_ID}:start -->"
END_MARKER="<!-- legal-harness-init:${BLOCK_ID}:end -->"
if grep -Fqx "$START_MARKER" "$CONTENT_FILE" || grep -Fqx "$END_MARKER" "$CONTENT_FILE"; then
    die "内容文件不应自带外层受管 marker；write.sh 会自动包裹"
fi

if [ -x "${SCRIPT_DIR}/validate-content.sh" ]; then
    validation_output=$(bash "${SCRIPT_DIR}/validate-content.sh" --file "$CONTENT_FILE" --privacy-mode "$PRIVACY_MODE") || die "内容校验未通过"
fi

if [ "$LEVEL" = "project" ]; then
    [ -n "$PROJECT_DIR" ] || PROJECT_DIR="$(pwd)"
    [ -d "$PROJECT_DIR" ] || die "项目目录不存在：$PROJECT_DIR"
    PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
fi

target_path_for() {
    local key="$1" kind
    if [ "$LEVEL" = "user" ]; then
        platform_user_config_path "$key"
        return
    fi
    kind=$(platform_config_kind "$key") || return 1
    case "$kind" in
        agents_md) printf '%s/AGENTS.md' "$PROJECT_DIR" ;;
        claude_md) printf '%s/CLAUDE.md' "$PROJECT_DIR" ;;
        *) printf '' ;;
    esac
}

results_json=""
emit_result() {
    # platform path status backup original_backup note before_sha after_sha
    local platform="$1" path="$2" status="$3" backup="${4:-}" original_backup="${5:-}"
    local note="${6:-}" before_sha="${7:-}" after_sha="${8:-}" fragment
    fragment="\"platform\":\"$(json_escape "$platform")\",\"path\":\"$(json_escape "$path")\",\"status\":\"$(json_escape "$status")\""
    [ -n "$backup" ] && fragment="$fragment,\"backup\":\"$(json_escape "$backup")\""
    [ -n "$original_backup" ] && fragment="$fragment,\"original_backup\":\"$(json_escape "$original_backup")\""
    [ -n "$note" ] && fragment="$fragment,\"note\":\"$(json_escape "$note")\""
    [ -n "$before_sha" ] && fragment="$fragment,\"before_sha256\":\"$(json_escape "$before_sha")\""
    [ -n "$after_sha" ] && fragment="$fragment,\"after_sha256\":\"$(json_escape "$after_sha")\""
    if [ -z "$results_json" ]; then results_json="{$fragment}"; else results_json="$results_json,{$fragment}"; fi
}

target_keys=()
if [ -n "$PLATFORMS_ARG" ]; then
    IFS=',' read -r -a parsed_platforms <<< "$PLATFORMS_ARG"
    for key in "${parsed_platforms[@]}"; do [ -n "$key" ] && target_keys+=("$key"); done
else
    detect_json=$(bash "${SCRIPT_DIR}/detect.sh" 2>/dev/null || true)
    current=$(printf '%s' "$detect_json" | sed -n 's/.*"current_runtime":[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    [ -n "$current" ] && target_keys+=("$current")
    detected=$(printf '%s' "$detect_json" | sed -n 's/.*"harnesses_detected":[[:space:]]*\[\([^]]*\)\].*/\1/p' | head -1)
    if [ -n "$detected" ]; then
        for key in $(printf '%s' "$detected" | tr -d '"' | tr ',' ' '); do target_keys+=("$key"); done
    fi
fi
[ ${#target_keys[@]} -gt 0 ] || die "没有可写入的目标平台；可用 --platforms 显式指定"

# 先按平台 key 去重，再按实际文件路径去重。
unique_keys=()
seen_keys=""
for key in "${target_keys[@]}"; do
    case " $seen_keys " in *" $key "*) continue ;; esac
    seen_keys="$seen_keys $key"
    unique_keys+=("$key")
done

target_paths=()
target_labels=()
for key in "${unique_keys[@]}"; do
    if ! _platform_meta_line "$key" >/dev/null 2>&1; then
        emit_result "$key" "" "unsupported" "" "" "未知平台 key（不在权威表）"
        continue
    fi
    if ! platform_supports_write "$key"; then
        emit_result "$key" "" "unsupported" "" "" "该平台不是 AGENTS.md/CLAUDE.md 配置模式"
        continue
    fi
    path=$(target_path_for "$key")
    [ -n "$path" ] || { emit_result "$key" "" "error" "" "" "无法解析目标路径"; continue; }
    found_index=-1
    if [ ${#target_paths[@]} -gt 0 ]; then
        index=0
        for existing_path in "${target_paths[@]}"; do
            if [ "$existing_path" = "$path" ]; then found_index=$index; break; fi
            index=$((index + 1))
        done
    fi
    if [ "$found_index" -ge 0 ]; then
        target_labels[$found_index]="${target_labels[$found_index]},${key}"
    else
        target_paths+=("$path")
        target_labels+=("$key")
    fi
done
if [ ${#target_paths[@]} -eq 0 ]; then
    cat <<EOF
{"schema_version":"2","targets":[$results_json]}
EOF
    exit 1
fi

marker_count() {
    local file="$1" marker="$2"
    awk -v marker="$marker" '$0 == marker { count++ } END { print count + 0 }' "$file"
}

validate_managed_markers() {
    # 所有 legal-harness-init 区块必须顺序成对、同 id 闭合且每个 id 唯一；不允许交叉或嵌套。
    awk '
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
    ' "$1"
}

build_candidate() {
    local target="$1" output="$2" start_count=0 end_count=0
    if [ ! -f "$target" ]; then
        {
            printf '%s\n' "$START_MARKER"
            cat "$CONTENT_FILE"
            printf '\n%s\n' "$END_MARKER"
        } > "$output"
        return 0
    fi

    start_count=$(marker_count "$target" "$START_MARKER")
    end_count=$(marker_count "$target" "$END_MARKER")
    if [ "$start_count" -ne "$end_count" ] || [ "$start_count" -gt 1 ]; then
        printf 'write.sh: %s 的受管 marker 不完整或重复（start=%s end=%s）\n' "$target" "$start_count" "$end_count" >&2
        return 1
    fi

    if [ "$start_count" -eq 1 ]; then
        {
            awk -v marker="$START_MARKER" '$0 == marker { exit } { print }' "$target"
            printf '%s\n' "$START_MARKER"
            cat "$CONTENT_FILE"
            printf '\n%s\n' "$END_MARKER"
            awk -v marker="$END_MARKER" 'found { print } $0 == marker { found=1 }' "$target"
        } > "$output"
    else
        {
            cat "$target"
            printf '\n\n%s\n' "$START_MARKER"
            cat "$CONTENT_FILE"
            printf '\n%s\n' "$END_MARKER"
        } > "$output"
    fi
}

TS=$(date +%Y%m%d-%H%M%S 2>/dev/null || printf 'manual')
had_error=false

index=0
for target in "${target_paths[@]}"; do
    labels="${target_labels[$index]}"
    index=$((index + 1))
    parent=$(dirname "$target")
    if [ ! -d "$parent" ]; then
        emit_result "$labels" "$target" "error" "" "" "父目录不存在：$parent"
        had_error=true
        continue
    fi
    if [ -L "$target" ]; then
        emit_result "$labels" "$target" "error" "" "" "目标是符号链接；为避免替换链接本身，需用户明确改用真实文件路径"
        had_error=true
        continue
    fi

    candidate=$(mktemp "${parent}/.legal-harness-init.XXXXXX") || { emit_result "$labels" "$target" "error" "" "" "无法创建同目录候选文件"; had_error=true; continue; }
    if ! build_candidate "$target" "$candidate"; then
        rm -f "$candidate"
        emit_result "$labels" "$target" "error" "" "" "受管 marker 校验失败，未写入"
        had_error=true
        continue
    fi
    if ! validate_managed_markers "$candidate"; then
        rm -f "$candidate"
        emit_result "$labels" "$target" "error" "" "" "全部受管 marker 结构校验失败，未写入"
        had_error=true
        continue
    fi

    before_sha=""
    [ -f "$target" ] && before_sha=$(sha256_file "$target")
    after_sha=$(sha256_file "$candidate")

    if [ -f "$target" ] && cmp -s "$target" "$candidate"; then
        rm -f "$candidate"
        if [ "$LEVEL" = "user" ]; then chmod 600 "$target" 2>/dev/null || true; fi
        emit_result "$labels" "$target" "unchanged" "" "" "受管区块已是目标内容，零 diff" "$before_sha" "$after_sha"
        continue
    fi

    if [ "$DRY_RUN" = true ]; then
        if [ -f "$target" ]; then
            printf '=== [dry-run] %s 受管区块 diff（旧 → 候选）===\n' "$target" >&2
            diff -u "$target" "$candidate" >&2 || true
            status="dry_run_diff"
        else
            printf '=== [dry-run] %s 将新建 ===\n' "$target" >&2
            status="dry_run_create"
        fi
        rm -f "$candidate"
        emit_result "$labels" "$target" "$status" "" "" "未落盘" "$before_sha" "$after_sha"
        continue
    fi

    if [ -f "$target" ] && [ "$MODE" = "create" ] && [ "$FORCE" = false ]; then
        printf '=== %s 已存在，需确认后再 upsert 受管区块 ===\n' "$target" >&2
        diff -u "$target" "$candidate" >&2 || true
        rm -f "$candidate"
        emit_result "$labels" "$target" "needs_confirmation" "" "" "使用 --mode update/append 或 --force 确认落盘" "$before_sha" "$after_sha"
        continue
    fi

    if [ -f "$target" ]; then
        printf '=== %s 受管区块 diff（旧 → 候选）===\n' "$target" >&2
        diff -u "$target" "$candidate" >&2 || true
    else
        printf '=== %s 将新建并写入受管区块 %s ===\n' "$target" "$BLOCK_ID" >&2
    fi

    original_backup=""
    original_backup_meta=""
    snapshot_backup=""
    if [ -f "$target" ]; then
        original_backup="${target}.bak.legal-harness-init"
        original_backup_meta="${original_backup}.meta"
        if [ -e "$original_backup" ] || [ -L "$original_backup" ] \
            || [ -e "$original_backup_meta" ] || [ -L "$original_backup_meta" ]; then
            if [ -L "$original_backup" ] || [ -L "$original_backup_meta" ] \
                || [ ! -f "$original_backup" ] || [ ! -f "$original_backup_meta" ]; then
                rm -f "$candidate"
                emit_result "$labels" "$target" "error" "" "$original_backup" "原始备份或元数据缺失、类型异常或为符号链接；请人工核对后处理"
                had_error=true
                continue
            fi
            saved_original_mode=$(sed -n 's/.*"mode":"\([0-9][0-9]*\)".*/\1/p' "$original_backup_meta" | head -1)
            saved_original_sha=$(sed -n 's/.*"sha256":"\([0-9a-fA-F][0-9a-fA-F]*\)".*/\1/p' "$original_backup_meta" | head -1)
            actual_original_sha=$(sha256_file "$original_backup")
            if [ -z "$saved_original_mode" ] || [ -z "$saved_original_sha" ] \
                || [ "$actual_original_sha" != "$saved_original_sha" ]; then
                rm -f "$candidate"
                emit_result "$labels" "$target" "error" "" "$original_backup" "原始备份完整性校验失败；拒绝继续更新"
                had_error=true
                continue
            fi
        fi
        if [ ! -e "$original_backup" ]; then
            original_mode=$(file_mode "$target")
            original_sha=$(sha256_file "$target")
            [ -n "$original_sha" ] || { rm -f "$candidate"; emit_result "$labels" "$target" "error" "" "" "本机缺少可用的 SHA-256 工具，无法建立可验证原始备份"; had_error=true; continue; }
            cp -p "$target" "$original_backup" || { rm -f "$candidate"; emit_result "$labels" "$target" "error" "" "" "原始备份创建失败"; had_error=true; continue; }
            if ! json_target=$(json_escape "$target") \
                || ! json_mode=$(json_escape "$original_mode") \
                || ! json_sha=$(json_escape "$original_sha"); then
                rm -f "$candidate" "$original_backup" "$original_backup_meta"
                emit_result "$labels" "$target" "error" "" "" "原始备份元数据转义失败"
                had_error=true
                continue
            fi
            if ! { cat <<EOF
{"schema_version":"1","target":"$json_target","mode":"$json_mode","sha256":"$json_sha"}
EOF
            } > "$original_backup_meta"; then
                rm -f "$candidate" "$original_backup" "$original_backup_meta"
                emit_result "$labels" "$target" "error" "" "" "原始备份元数据创建失败"
                had_error=true
                continue
            fi
            chmod 600 "$original_backup_meta" 2>/dev/null || true
        fi
        snapshot_backup="${target}.bak.${TS}.$$"
        cp -p "$target" "$snapshot_backup" || { rm -f "$candidate"; emit_result "$labels" "$target" "error" "" "$original_backup" "时间戳备份创建失败"; had_error=true; continue; }
    fi

    if [ "$LEVEL" = "user" ]; then
        chmod 600 "$candidate" 2>/dev/null || true
        [ -n "$original_backup" ] && chmod 600 "$original_backup" 2>/dev/null || true
        [ -n "$original_backup_meta" ] && [ -f "$original_backup_meta" ] && chmod 600 "$original_backup_meta" 2>/dev/null || true
        [ -n "$snapshot_backup" ] && chmod 600 "$snapshot_backup" 2>/dev/null || true
    elif [ -f "$target" ]; then
        chmod "$(file_mode "$target")" "$candidate" 2>/dev/null || true
    else
        chmod 644 "$candidate" 2>/dev/null || true
    fi

    if ! mv "$candidate" "$target"; then
        rm -f "$candidate"
        emit_result "$labels" "$target" "error" "$snapshot_backup" "$original_backup" "原子替换失败" "$before_sha" "$after_sha"
        had_error=true
        continue
    fi
    [ "$LEVEL" = "user" ] && chmod 600 "$target" 2>/dev/null || true
    printf '=== %s 已 upsert 受管区块 %s ===\n' "$target" "$BLOCK_ID" >&2
    if [ -n "$snapshot_backup" ]; then status="updated"; else status="written"; fi
    emit_result "$labels" "$target" "$status" "$snapshot_backup" "$original_backup" "已按实际路径去重并原子写入" "$before_sha" "$after_sha"

    # === 真实落盘后自动调 record-init-env.sh 记录 init-environment ===
    # 默认 RECORD_INIT_ENV=true；--record-init-env=false 显式关闭（如批量脚本场景）。
    # 失败不阻断：AGENTS.md 已落盘,init-environment 是 metadata;模型探测失败时
    # record-init-env.sh 会输出 hint 让 agent 后续手动补,不静默用 unknown。
    if [ "${RECORD_INIT_ENV:-true}" = "true" ]; then
        init_args=(--target "$target" --action "${INIT_ACTION:-init}")
        [ -n "${MODEL:-}" ] && init_args+=(--model "$MODEL")
        init_output=$(bash "${SCRIPT_DIR}/record-init-env.sh" "${init_args[@]}" 2>&1) && init_rc=0 || init_rc=$?
        if [ "$init_rc" -eq 0 ]; then
            printf '=== init-environment 已记录到 %s ===\n' "$target" >&2
        else
            printf '⚠️  init-environment 记录失败（exit %s）；AGENTS.md 已落盘,后续可手动补\n' "$init_rc" >&2
            printf '%s\n' "$init_output" >&2
            printf '   手动命令：bash scripts/record-init-env.sh --target %s --action %s [--model <name>]\n' "$target" "${INIT_ACTION:-init}" >&2
        fi
    fi
done

cat <<EOF
{
  "schema_version": "2",
  "level": "$(json_escape "$LEVEL")",
  "mode": "$(json_escape "$MODE")",
  "privacy_mode": "$(json_escape "$PRIVACY_MODE")",
  "block_id": "$(json_escape "$BLOCK_ID")",
  "dry_run": $DRY_RUN,
  "force": $FORCE,
  "content_file": "$(json_escape "$CONTENT_FILE")",
  "targets": [$results_json]
}
EOF

[ "$had_error" = false ]
