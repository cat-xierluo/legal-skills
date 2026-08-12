#!/usr/bin/env bash
#
# scripts/detect.sh - 一次性环境检测
#
# 检测：
#   - 8 个 harness 平台（Claude Code / Codex / OpenClaw / MyAgents / QoderWork / QwenWork / WorkBuddy / Orca）
#   - 各平台用户级配置文件是否存在、行数、config_kind
#   - 当前 runtime（通过 env 标志变量，只看存在性不读值）
#   - 当前 cwd 项目级 AGENTS.md/CLAUDE.md
#   - project-init 痕迹（.claude/skills/、docs/）
#
# 平台权威表在 scripts/lib_platforms.sh（detect/write 共享单一真值源）。
#
# 输出：JSON（schema_version 2）到 stdout
# 退出码：检测到至少一个 harness → 0；否则 1

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

file_lines() {
    local f="${1-}"
    if [ -f "$f" ]; then
        wc -l < "$f" | tr -d ' '
    else
        echo "0"
    fi
}

dir_exists() {
    [ -d "$1" ]
}

# 动态 env 变量存在性检查（bash 3.2 兼容；只看是否 set，不读值，避免泄露 token）
env_var_is_set() {
    local varname="$1"
    [ -n "${varname}" ] && [ -n "${!varname+x}" ]
}

# ========== detect: 用户级平台 ==========

HARNESSES=()
USER_LEVEL_ENTRIES=()  # 每条: key|exists|path|lines|config_kind

for key in "${PLATFORM_KEYS[@]}"; do
    home_dir=$(platform_home_dir "$key")
    [ -z "$home_dir" ] && continue
    if ! dir_exists "$home_dir"; then
        continue
    fi
    # 额外文件痕迹（若有定义则必须命中，否则视为未真正安装）
    extra=$(platform_extra_probe "$key")
    if [ -n "$extra" ] && [ ! -e "${home_dir}/${extra}" ]; then
        continue
    fi
    HARNESSES+=("$key")

    cfg_path=$(platform_user_config_path "$key")
    cfg_kind=$(platform_config_kind "$key")
    if [ -n "$cfg_path" ] && [ -f "$cfg_path" ]; then
        lines=$(file_lines "$cfg_path")
        exists=true
    else
        lines=0
        exists=false
    fi
    USER_LEVEL_ENTRIES+=("${key}|${exists}|${cfg_path}|${lines}|${cfg_kind}")
done

# ========== detect: 当前 runtime（env 标志）==========

CURRENT_RUNTIME="null"
CURRENT_RUNTIME_WRITEABLE=false
# 优先级：支持写入的平台（claude_md/agents_md）> non-agents-md 容器层
runtime_hits_writable=()
runtime_hits_other=()
for key in "${PLATFORM_KEYS[@]}"; do
    envname=$(platform_runtime_env "$key")
    [ -z "$envname" ] && continue
    if env_var_is_set "$envname"; then
        if platform_supports_write "$key"; then
            runtime_hits_writable+=("$key")
        else
            runtime_hits_other+=("$key")
        fi
    fi
done
if [ ${#runtime_hits_writable[@]} -gt 0 ]; then
    CURRENT_RUNTIME="\"$(json_escape "${runtime_hits_writable[0]}")\""
    CURRENT_RUNTIME_WRITEABLE=true
elif [ ${#runtime_hits_other[@]} -gt 0 ]; then
    CURRENT_RUNTIME="\"$(json_escape "${runtime_hits_other[0]}")\""
    CURRENT_RUNTIME_WRITEABLE=false
fi

# ========== detect: 项目级 ==========

CWD_PATH="$(pwd)"
AGENTS_MD_EXISTS=false
AGENTS_MD_LINES=0
CLAUDE_MD_EXISTS=false
CLAUDE_MD_LINES=0
PROJECT_INIT_RAN=false
PROJECT_INIT_EVIDENCE=()

if [ -f "AGENTS.md" ]; then
    AGENTS_MD_EXISTS=true
    AGENTS_MD_LINES=$(file_lines "AGENTS.md")
fi
if [ -f "CLAUDE.md" ]; then
    CLAUDE_MD_EXISTS=true
    CLAUDE_MD_LINES=$(file_lines "CLAUDE.md")
fi

if dir_exists ".claude/skills"; then
    PROJECT_INIT_EVIDENCE+=(".claude/skills/")
fi
if dir_exists "docs"; then
    PROJECT_INIT_EVIDENCE+=("docs/")
fi
if [ ${#PROJECT_INIT_EVIDENCE[@]} -gt 0 ]; then
    PROJECT_INIT_RAN=true
fi

# ========== output ==========

# harness list（空数组守卫：bash 3.2 + set -u）
harness_list="["
if [ ${#HARNESSES[@]} -gt 0 ]; then
    first=true
    for h in "${HARNESSES[@]}"; do
        if [ "$first" = true ]; then first=false; else harness_list+=","; fi
        harness_list+="\"$(json_escape "$h")\""
    done
fi
harness_list+="]"

# user_level object（空对象守卫）
user_level_obj="{"
if [ ${#USER_LEVEL_ENTRIES[@]} -gt 0 ]; then
    first=true
    for ul in "${USER_LEVEL_ENTRIES[@]}"; do
        if [ "$first" = true ]; then first=false; else user_level_obj+=","; fi
        IFS='|' read -r ul_name ul_exists ul_path ul_lines ul_kind <<EOF
$ul
EOF
        user_level_obj+="\"$(json_escape "$ul_name")\":{\"exists\":$ul_exists,\"path\":\"$(json_escape "$ul_path")\",\"lines\":$ul_lines,\"config_kind\":\"$(json_escape "$ul_kind")\"}"
    done
fi
user_level_obj+="}"

# project_init evidence list（空数组守卫）
evidence_list="["
if [ ${#PROJECT_INIT_EVIDENCE[@]} -gt 0 ]; then
    first=true
    for ev in "${PROJECT_INIT_EVIDENCE[@]}"; do
        if [ "$first" = true ]; then first=false; else evidence_list+=","; fi
        evidence_list+="\"$(json_escape "$ev")\""
    done
fi
evidence_list+="]"

cat <<EOF
{
  "schema_version": "2",
  "current_runtime": $CURRENT_RUNTIME,
  "current_runtime_writeable": $CURRENT_RUNTIME_WRITEABLE,
  "harnesses_detected": $harness_list,
  "user_level_files": $user_level_obj,
  "project_level": {
    "cwd": "$(json_escape "$CWD_PATH")",
    "agents_md_exists": $AGENTS_MD_EXISTS,
    "agents_md_lines": $AGENTS_MD_LINES,
    "claude_md_exists": $CLAUDE_MD_EXISTS,
    "claude_md_lines": $CLAUDE_MD_LINES,
    "project_init_ran": $PROJECT_INIT_RAN,
    "evidence": $evidence_list
  }
}
EOF

if [ ${#HARNESSES[@]} -gt 0 ]; then
    exit 0
else
    exit 1
fi
