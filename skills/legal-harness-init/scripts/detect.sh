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
# 用法：detect.sh [--runtime <platform-key>]
#   --runtime 由当前 harness 显式声明运行平台，优先级高于 env 推断。
# 输出：JSON（schema_version 3）到 stdout
# 退出码：检测到至少一个 harness → 0；否则 1

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib_platforms.sh
. "${SCRIPT_DIR}/lib_platforms.sh"

EXPLICIT_RUNTIME=""
while [ $# -gt 0 ]; do
    case "$1" in
        --runtime)
            [ $# -ge 2 ] || { printf 'detect.sh: 错误：--runtime 需要平台 key\n' >&2; exit 2; }
            EXPLICIT_RUNTIME="$2"
            shift 2
            ;;
        -h|--help)
            sed -n '3,20p' "$0"
            exit 0
            ;;
        *)
            printf 'detect.sh: 错误：未知参数 %s\n' "$1" >&2
            exit 2
            ;;
    esac
done

if [ -n "$EXPLICIT_RUNTIME" ] && ! _platform_meta_line "$EXPLICIT_RUNTIME" >/dev/null 2>&1; then
    printf 'detect.sh: 错误：未知平台 key %s\n' "$EXPLICIT_RUNTIME" >&2
    exit 2
fi

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
        awk 'END { print NR + 0 }' "$f"
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

# ========== detect: 当前 runtime（显式声明 + env 证据）==========

CURRENT_RUNTIME="null"
CURRENT_RUNTIME_WRITEABLE=false
CURRENT_RUNTIME_CONFIDENCE="null"
CURRENT_RUNTIME_SOURCE="null"
RUNTIME_CANDIDATES=() # key|confidence|source|writeable

if [ -n "$EXPLICIT_RUNTIME" ]; then
    explicit_writeable=false
    platform_supports_write "$EXPLICIT_RUNTIME" && explicit_writeable=true
    RUNTIME_CANDIDATES+=("${EXPLICIT_RUNTIME}|high|explicit|${explicit_writeable}")
    CURRENT_RUNTIME="\"$(json_escape "$EXPLICIT_RUNTIME")\""
    CURRENT_RUNTIME_CONFIDENCE='"high"'
    CURRENT_RUNTIME_SOURCE='"explicit"'
    CURRENT_RUNTIME_WRITEABLE=$explicit_writeable
else
    for key in "${PLATFORM_KEYS[@]}"; do
        signals=$(platform_runtime_signals "$key")
        [ -z "$signals" ] && continue
        old_ifs="$IFS"
        IFS=','
        for signal in $signals; do
            envname="${signal%%:*}"
            confidence="${signal#*:}"
            if env_var_is_set "$envname"; then
                candidate_writeable=false
                platform_supports_write "$key" && candidate_writeable=true
                RUNTIME_CANDIDATES+=("${key}|${confidence}|env:${envname}|${candidate_writeable}")
            fi
        done
        IFS="$old_ifs"
    done

    # 只在最高置信度下唯一命中平台时才给出 current_runtime。
    for wanted_confidence in high medium low; do
        matched_keys=""
        matched_count=0
        matched_source=""
        if [ ${#RUNTIME_CANDIDATES[@]} -gt 0 ]; then
            for candidate in "${RUNTIME_CANDIDATES[@]}"; do
                IFS='|' read -r candidate_key candidate_confidence candidate_source candidate_writeable <<EOF
$candidate
EOF
                [ "$candidate_confidence" = "$wanted_confidence" ] || continue
                case " $matched_keys " in
                    *" $candidate_key "*) ;;
                    *)
                        matched_keys="$matched_keys $candidate_key"
                        matched_count=$((matched_count + 1))
                        matched_source="$candidate_source"
                        ;;
                esac
            done
        fi
        if [ "$matched_count" -eq 1 ]; then
            selected_key=$(printf '%s' "$matched_keys" | sed 's/^ *//;s/ *$//')
            CURRENT_RUNTIME="\"$(json_escape "$selected_key")\""
            CURRENT_RUNTIME_CONFIDENCE="\"$wanted_confidence\""
            CURRENT_RUNTIME_SOURCE="\"$(json_escape "$matched_source")\""
            platform_supports_write "$selected_key" && CURRENT_RUNTIME_WRITEABLE=true
            break
        elif [ "$matched_count" -gt 1 ]; then
            break
        fi
    done
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
if [ -f ".claude/settings.json" ]; then
    PROJECT_INIT_EVIDENCE+=(".claude/settings.json")
fi
if [ -e ".codex/skills" ]; then
    PROJECT_INIT_EVIDENCE+=(".codex/skills")
fi

# docs/ 是通用目录，不能单独证明 project-init 已运行。
# 要求核心痕迹 .claude/skills + 项目指令文件 + 至少一个脚手架证据。
project_instruction_exists=false
if [ "$AGENTS_MD_EXISTS" = true ] || [ "$CLAUDE_MD_EXISTS" = true ]; then
    project_instruction_exists=true
fi
project_scaffold_exists=false
if [ -f ".claude/settings.json" ] || [ -e ".codex/skills" ] || [ -d "docs" ]; then
    project_scaffold_exists=true
fi
if [ -d ".claude/skills" ] && [ "$project_instruction_exists" = true ] && [ "$project_scaffold_exists" = true ]; then
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

# runtime candidate list（保留证据，不读 env 值）
runtime_candidate_list="["
if [ ${#RUNTIME_CANDIDATES[@]} -gt 0 ]; then
    first=true
    for candidate in "${RUNTIME_CANDIDATES[@]}"; do
        if [ "$first" = true ]; then first=false; else runtime_candidate_list+=","; fi
        IFS='|' read -r candidate_key candidate_confidence candidate_source candidate_writeable <<EOF
$candidate
EOF
        runtime_candidate_list+="{\"platform\":\"$(json_escape "$candidate_key")\",\"confidence\":\"$(json_escape "$candidate_confidence")\",\"source\":\"$(json_escape "$candidate_source")\",\"writeable\":${candidate_writeable}}"
    done
fi
runtime_candidate_list+="]"

cat <<EOF
{
  "schema_version": "3",
  "current_runtime": $CURRENT_RUNTIME,
  "current_runtime_confidence": $CURRENT_RUNTIME_CONFIDENCE,
  "current_runtime_source": $CURRENT_RUNTIME_SOURCE,
  "current_runtime_writeable": $CURRENT_RUNTIME_WRITEABLE,
  "runtime_candidates": $runtime_candidate_list,
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
