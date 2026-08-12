#!/usr/bin/env bash
#
# scripts/write.sh - 把生成好的 AGENTS.md/CLAUDE.md 内容写入对应 harness 位置
#
# 平台权威表在 scripts/lib_platforms.sh（与 detect.sh 共享）。
# 只对 config_kind = claude_md / agents_md 的平台写入；其余平台记 unsupported。
#
# 用法：
#   bash scripts/write.sh \
#     --content-file <生成好的内容文件> \
#     --level <user|project> \
#     [--platforms <key1,key2>]   # 默认 = detect 的 current_runtime + 所有可写平台
#     [--mode <create|update|append>]  # 默认 create
#     [--project-dir <path>]      # level=project 时目标目录，默认当前 cwd
#     [--dry-run]                 # 只展示 diff，不落盘
#     [--force]                   # 已存在时不等确认，直接备份+覆盖
#
# 退出码：0 = 全部成功或 needs_confirmation；1 = 参数错或有 error
#
# 安全：只用 shell 文件操作（cp -p / diff / cat）。不调 subprocess、不联网、不安装。

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib_platforms.sh
. "${SCRIPT_DIR}/lib_platforms.sh"

# ========== helpers ==========

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

# ========== 参数解析 ==========

CONTENT_FILE=""
LEVEL=""
PLATFORMS_ARG=""
MODE="create"
PROJECT_DIR=""
DRY_RUN=false
FORCE=false

while [ $# -gt 0 ]; do
    case "$1" in
        --content-file)
            [ $# -ge 2 ] || die "--content-file 需要参数"
            CONTENT_FILE="$2"; shift 2 ;;
        --level)
            [ $# -ge 2 ] || die "--level 需要参数"
            LEVEL="$2"; shift 2 ;;
        --platforms)
            [ $# -ge 2 ] || die "--platforms 需要参数"
            PLATFORMS_ARG="$2"; shift 2 ;;
        --mode)
            [ $# -ge 2 ] || die "--mode 需要参数"
            MODE="$2"; shift 2 ;;
        --project-dir)
            [ $# -ge 2 ] || die "--project-dir 需要参数"
            PROJECT_DIR="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --force)   FORCE=true; shift ;;
        -h|--help)
            sed -n '3,25p' "$0"
            exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
done

[ -n "$CONTENT_FILE" ] || die "缺 --content-file"
[ -n "$LEVEL" ] || die "缺 --level（user 或 project）"
case "$LEVEL" in
    user|project) ;;
    *) die "--level 必须是 user 或 project" ;;
esac
case "$MODE" in
    create|update|append) ;;
    *) die "--mode 必须是 create / update / append" ;;
esac
[ -f "$CONTENT_FILE" ] || die "内容文件不存在：$CONTENT_FILE"
[ -s "$CONTENT_FILE" ] || die "内容文件为空：$CONTENT_FILE"

CONTENT="$(cat "$CONTENT_FILE")"

# ========== 确定目标平台 ==========

target_keys=()
if [ -n "$PLATFORMS_ARG" ]; then
    IFS=',' read -r -a _pa <<< "$PLATFORMS_ARG"
    for k in "${_pa[@]}"; do
        target_keys+=("$k")
    done
else
    # 默认：detect.sh 的 current_runtime（若可写）+ 所有可写已装平台
    detect_json=$("${SCRIPT_DIR}/detect.sh" 2>/dev/null || true)
    if [ -n "$detect_json" ]; then
        # 抽 current_runtime（简单文本解析；不依赖 jq）
        cr=$(printf '%s' "$detect_json" | sed -n 's/.*"current_runtime":[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
        if [ -n "$cr" ]; then
            target_keys+=("$cr")
        fi
        # 抽 harnesses_detected 数组
        hd=$(printf '%s' "$detect_json" | sed -n 's/.*"harnesses_detected":[[:space:]]*\[\([^]]*\)\].*/\1/p' | head -1)
        if [ -n "$hd" ]; then
            # 拆 "key", "key2" → key key2
            for k in $(printf '%s' "$hd" | tr -d '"' | tr ',' ' '); do
                target_keys+=("$k")
            done
        fi
    fi
    # 去重 + 只保留可写
    _seen=""
    _unique=()
    for k in "${target_keys[@]}"; do
        case " $_seen " in
            *" $k "*) continue ;;
        esac
        _seen="$_seen $k"
        if platform_supports_write "$k" 2>/dev/null; then
            _unique+=("$k")
        fi
    done
    target_keys=("${_unique[@]}")
fi

if [ ${#target_keys[@]} -eq 0 ]; then
    die "没有可写入的目标平台（检测到 0 个可写 harness）。用 --platforms 显式指定。"
fi

# ========== 项目级目标目录 ==========

if [ "$LEVEL" = "project" ]; then
    if [ -z "$PROJECT_DIR" ]; then
        PROJECT_DIR="$(pwd)"
    fi
    [ -d "$PROJECT_DIR" ] || die "项目目录不存在：$PROJECT_DIR"
fi

# ========== 解析每个平台的目标路径 ==========

target_path_for() {
    local key="$1"
    if [ "$LEVEL" = "user" ]; then
        platform_user_config_path "$key"
    else
        # project 级：agents_md → <dir>/AGENTS.md；claude_md → <dir>/CLAUDE.md
        local kind
        kind=$(platform_config_kind "$key")
        case "$kind" in
            agents_md) printf '%s/%s' "$PROJECT_DIR" "AGENTS.md" ;;
            claude_md) printf '%s/%s' "$PROJECT_DIR" "CLAUDE.md" ;;
            *) printf '' ;;
        esac
    fi
}

# ========== 写入循环 ==========

umask_val="077"   # 用户级默认保护隐私
[ "$LEVEL" = "project" ] && umask_val="022"

TS=$(date +%Y%m%d-%H%M%S 2>/dev/null || echo "manual")
results_json=""

emit_result() {
    # $1=platform $2=path $3=status $4=backup(可空) $5=note(可空)
    local p="$1" path="$2" status="$3" backup="${4:-}" note="${5:-}"
    local frag
    frag="\"platform\":\"$(json_escape "$p")\",\"path\":\"$(json_escape "$path")\",\"status\":\"$(json_escape "$status")\""
    [ -n "$backup" ] && frag="$frag,\"backup\":\"$(json_escape "$backup")\""
    [ -n "$note" ] && frag="$frag,\"note\":\"$(json_escape "$note")\""
    if [ -z "$results_json" ]; then
        results_json="{$frag}"
    else
        results_json="${results_json},{${frag}}"
    fi
}

had_error=false

for key in "${target_keys[@]}"; do
    # 校验是已知平台
    if ! platform_config_kind "$key" >/dev/null 2>&1; then
        # 未知 key（不在权威表）
        if _platform_meta_line "$key" >/dev/null 2>&1; then
            : # 已知但 non-agents-md
        else
            emit_result "$key" "" "unsupported" "" "未知平台 key（不在权威表）"
            continue
        fi
    fi

    if ! platform_supports_write "$key"; then
        emit_result "$key" "" "unsupported" "" "该平台 config_kind=non-agents-md，不自动写入，请手动配置"
        continue
    fi

    target=$(target_path_for "$key")
    if [ -z "$target" ]; then
        emit_result "$key" "" "error" "" "无法解析目标路径"
        had_error=true
        continue
    fi

    # 确保父目录存在
    parent=$(dirname "$target")
    if [ ! -d "$parent" ]; then
        emit_result "$key" "$target" "error" "" "父目录不存在：$parent"
        had_error=true
        continue
    fi

    if [ "$DRY_RUN" = true ]; then
        if [ -f "$target" ]; then
            printf '=== [dry-run] %s 已存在，diff（旧 → 新）===\n' "$target" >&2
            diff -u "$target" "$CONTENT_FILE" >&2 || true
            emit_result "$key" "$target" "dry_run_diff" "" "已存在，未落盘"
        else
            printf '=== [dry-run] %s 将新建（%d 字节）===\n' "$target" "$(wc -c < "$CONTENT_FILE" | tr -d ' ')" >&2
            emit_result "$key" "$target" "dry_run_create" "" "将新建，未落盘"
        fi
        continue
    fi

    # 实写入
    if [ -f "$target" ]; then
        # 已存在 → 备份
        backup="${target}.bak.${TS}"
        if ! cp -p "$target" "$backup" 2>/dev/null; then
            emit_result "$key" "$target" "error" "" "备份失败：$backup"
            had_error=true
            continue
        fi

        if [ "$FORCE" = true ] || [ "$MODE" = "update" ]; then
            # 覆盖（update 模式或 force）
            printf '=== %s 覆盖（备份在 %s）===\n' "$target" "$backup" >&2
            diff -u "$backup" "$CONTENT_FILE" >&2 || true
            (
                umask "$umask_val"
                cat "$CONTENT_FILE" > "$target"
            ) || { emit_result "$key" "$target" "error" "$backup" "覆盖写入失败"; had_error=true; continue; }
            emit_result "$key" "$target" "backed_up" "$backup" "已备份并覆盖"
        elif [ "$MODE" = "append" ]; then
            printf '=== %s 追加（备份在 %s）===\n' "$target" "$backup" >&2
            (
                umask "$umask_val"
                { cat "$target"; printf '\n\n---\n\n'; cat "$CONTENT_FILE"; } > "${target}.tmp.$$" \
                    && mv "${target}.tmp.$$" "$target"
            ) || { emit_result "$key" "$target" "error" "$backup" "追加写入失败"; had_error=true; continue; }
            emit_result "$key" "$target" "backed_up" "$backup" "已备份并追加"
        else
            # create 模式 + 已存在 + 非 force → 生成 diff，等确认
            printf '=== %s 已存在（备份 %s）。加 --force 覆盖，或 --mode append 追加 ===\n' "$target" "$backup" >&2
            diff -u "$target" "$CONTENT_FILE" >&2 || true
            emit_result "$key" "$target" "needs_confirmation" "$backup" "已生成 diff；--force 覆盖 / --mode append 追加 / 保持现状"
        fi
    else
        # 不存在 → 直接写
        (
            umask "$umask_val"
            cat "$CONTENT_FILE" > "$target"
        ) || { emit_result "$key" "$target" "error" "" "新建写入失败"; had_error=true; continue; }
        printf '=== %s 新建 ===\n' "$target" >&2
        emit_result "$key" "$target" "written" "" "新建成功"
    fi
done

# ========== 输出 JSON 报告 ==========

cat <<EOF
{
  "schema_version": "1",
  "level": "$(json_escape "$LEVEL")",
  "mode": "$(json_escape "$MODE")",
  "dry_run": $DRY_RUN,
  "force": $FORCE,
  "content_file": "$(json_escape "$CONTENT_FILE")",
  "targets": [$results_json]
}
EOF

if [ "$had_error" = true ]; then
    exit 1
fi
exit 0
