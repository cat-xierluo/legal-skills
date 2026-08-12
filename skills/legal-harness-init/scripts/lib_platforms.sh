#!/usr/bin/env bash
#
# scripts/lib_platforms.sh - harness 平台权威表
#
# 被 detect.sh / write.sh 共同 source，作为"哪个平台 → 配置文件路径"的单一真值源，
# 避免两个脚本路径漂移。本文件不直接执行（被 source 时只定义函数与数据）。
#
# 兼容 macOS 默认 bash 3.2（不使用关联数组，用 `|` 分隔的元数据行 + IFS 解析）。
#
# 字段说明（每平台一行，`|` 分隔）：
#   key | home_subdir | user_config_file | config_kind | runtime_env | extra_probe
#
#   - key              平台标识（snake 写法，用于 JSON 字段名）
#   - home_subdir      用户级配置目录（相对于 $HOME，如 .claude）
#   - user_config_file 用户级配置文件名（相对 home_subdir；non-agents-md 平台留空）
#   - config_kind      claude_md / agents_md / non-agents-md
#                       claude_md/agents_md → write.sh 自动写入
#                       non-agents-md       → 仅检测，write.sh 跳过并提示手动
#   - runtime_env      判断"当前 runtime"的 env 变量名（留空 = 无 env 信号，靠目录）
#                       只读"变量是否存在"，绝不读其值（值可能含 token）
#   - extra_probe      目录存在外的额外文件痕迹（相对 home_subdir；留空 = 只看目录）

PLATFORM_KEYS=(
    claude-code
    codex
    openclaw
    myagents
    qoderwork
    qwenwork
    workbuddy
    orca
)

# shellcheck disable=SC2016
_PLATFORM_META=(
    'claude-code|.claude|CLAUDE.md|claude_md|CLAUDECODE|'
    'codex|.codex|AGENTS.md|agents_md|CODEX_HOME|'
    'openclaw|.openclaw|AGENTS.md|agents_md||cron/jobs.json'
    'myagents|.myagents|CLAUDE.md|claude_md||'
    'qoderwork|.qoderworkcn||non-agents-md||'
    'qwenwork|.qwenworkcn||non-agents-md||.status.json'
    'workbuddy|.workbuddy||non-agents-md||workbuddy.db'
    'orca|.orca||non-agents-md|ORCA_AGENT_HOOK_TOKEN|'
)

# 按平台 key 取一行元数据（找不到返回空）。内部用。
_platform_meta_line() {
    local want="$1"
    local line
    for line in "${_PLATFORM_META[@]}"; do
        local key="${line%%|*}"
        if [ "$key" = "$want" ]; then
            printf '%s' "$line"
            return 0
        fi
    done
    return 1
}

# 解析某平台的指定字段。用法：_platform_field <key> <field-index 1..6>
_platform_field() {
    local key="$1" idx="$2"
    local line
    line=$(_platform_meta_line "$key") || return 1
    # IFS='|' read 6 字段
    local f1 f2 f3 f4 f5 f6
    IFS='|' read -r f1 f2 f3 f4 f5 f6 <<EOF
$line
EOF
    case "$idx" in
        1) printf '%s' "$f1" ;;
        2) printf '%s' "$f2" ;;
        3) printf '%s' "$f3" ;;
        4) printf '%s' "$f4" ;;
        5) printf '%s' "$f5" ;;
        6) printf '%s' "$f6" ;;
    esac
}

# 公开函数：平台用户级配置目录绝对路径（~/.<subdir>）。不存在该平台返回空。
platform_home_dir() {
    local sub
    sub=$(_platform_field "$1" 2) || return 1
    [ -n "$sub" ] && printf '%s/%s' "${HOME}" "$sub"
}

# 公开函数：平台用户级配置文件绝对路径（~/.<subdir>/<file>）。non-agents-md 返回空。
platform_user_config_path() {
    local sub file
    sub=$(_platform_field "$1" 2) || return 1
    file=$(_platform_field "$1" 3) || return 1
    if [ -n "$sub" ] && [ -n "$file" ]; then
        printf '%s/%s/%s' "${HOME}" "$sub" "$file"
    fi
}

# 公开函数：config_kind（claude_md / agents_md / non-agents-md）
platform_config_kind() {
    _platform_field "$1" 4
}

# 公开函数：runtime env 变量名（可能为空）
platform_runtime_env() {
    _platform_field "$1" 5
}

# 公开函数：额外文件痕迹（相对 home_subdir，可能为空）
platform_extra_probe() {
    _platform_field "$1" 6
}

# 公开函数：判断平台是否支持自动写入（claude_md / agents_md → 0；否则 1）
platform_supports_write() {
    local kind
    kind=$(platform_config_kind "$1")
    [ "$kind" = "claude_md" ] || [ "$kind" = "agents_md" ]
}
