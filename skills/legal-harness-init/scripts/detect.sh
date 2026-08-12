#!/usr/bin/env bash
#
# scripts/detect.sh - 一次性环境检测
#
# 检测：
#   - 4 个 harness 平台（Claude Code / Codex / OpenClaw / QoderWork）
#   - 用户级文件存在性
#   - 当前 cwd 项目级 AGENTS.md/CLAUDE.md
#   - project-init 痕迹（.claude/skills/、docs/）
#
# 输出：JSON 到 stdout

set -u

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

# ========== detect ==========

HARNESSES=()
USER_LEVEL=()
PROJECT_DETECTED=false
AGENTS_MD_EXISTS=false
AGENTS_MD_LINES=0
CLAUDE_MD_EXISTS=false
CLAUDE_MD_LINES=0
PROJECT_INIT_RAN=false
PROJECT_INIT_EVIDENCE=()

# Claude Code
if dir_exists "$HOME/.claude"; then
    HARNESSES+=("claude-code")
    claude_user="$HOME/.claude/CLAUDE.md"
    if [ -f "$claude_user" ]; then
        lines=$(file_lines "$claude_user")
    else
        lines=0
    fi
    USER_LEVEL+=("claude-code|$( [ -f "$claude_user" ] && echo true || echo false )|$claude_user|$lines")
fi

# Codex
if dir_exists "$HOME/.codex"; then
    HARNESSES+=("codex")
    codex_user="$HOME/.codex/AGENTS.md"
    if [ -f "$codex_user" ]; then
        lines=$(file_lines "$codex_user")
    else
        lines=0
    fi
    USER_LEVEL+=("codex|$( [ -f "$codex_user" ] && echo true || echo false )|$codex_user|$lines")
fi

# OpenClaw
if dir_exists "$HOME/.openclaw"; then
    HARNESSES+=("openclaw")
    oc_user="$HOME/.openclaw/AGENTS.md"
    if [ -f "$oc_user" ]; then
        lines=$(file_lines "$oc_user")
    else
        lines=0
    fi
    USER_LEVEL+=("openclaw|$( [ -f "$oc_user" ] && echo true || echo false )|$oc_user|$lines")
fi

# QoderWork
if dir_exists "$HOME/.qoderworkcn"; then
    HARNESSES+=("qoderwork")
    qw_user="$HOME/.qoderworkcn/AGENTS.md"
    if [ -f "$qw_user" ]; then
        lines=$(file_lines "$qw_user")
    else
        lines=0
    fi
    USER_LEVEL+=("qoderwork|$( [ -f "$qw_user" ] && echo true || echo false )|$qw_user|$lines")
fi

# Project level
CWD_PATH="$(pwd)"
if [ -f "AGENTS.md" ]; then
    AGENTS_MD_EXISTS=true
    AGENTS_MD_LINES=$(file_lines "AGENTS.md")
fi
if [ -f "CLAUDE.md" ]; then
    CLAUDE_MD_EXISTS=true
    CLAUDE_MD_LINES=$(file_lines "CLAUDE.md")
fi

# project-init 痕迹
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

# harness list（空数组守卫：bash 3.2 + set -u 下 "${arr[@]}" 对空数组会 unbound）
harness_list="["
if [ ${#HARNESSES[@]} -gt 0 ]; then
    first=true
    for h in "${HARNESSES[@]}"; do
        if [ "$first" = true ]; then
            first=false
        else
            harness_list+=","
        fi
        harness_list+="\"$h\""
    done
fi
harness_list+="]"

# user_level object（空数组守卫）
user_level_obj="{"
if [ ${#USER_LEVEL[@]} -gt 0 ]; then
    first=true
    for ul in "${USER_LEVEL[@]}"; do
        if [ "$first" = true ]; then
            first=false
        else
            user_level_obj+=","
        fi
        # ul 格式: name|exists|path|lines
        IFS='|' read -r ul_name ul_exists ul_path ul_lines <<EOF
$ul
EOF
        user_level_obj+="\"$ul_name\":{\"exists\":$ul_exists,\"path\":\"$(json_escape "$ul_path")\",\"lines\":$ul_lines}"
    done
fi
user_level_obj+="}"

# project_init evidence list（空数组守卫）
evidence_list="["
if [ ${#PROJECT_INIT_EVIDENCE[@]} -gt 0 ]; then
    first=true
    for ev in "${PROJECT_INIT_EVIDENCE[@]}"; do
        if [ "$first" = true ]; then
            first=false
        else
            evidence_list+=","
        fi
        evidence_list+="\"$ev\""
    done
fi
evidence_list+="]"

cat <<EOF
{
  "schema_version": "1",
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

# 退出码：检测到至少一个 harness → 0；否则 1
if [ ${#HARNESSES[@]} -gt 0 ]; then
    exit 0
else
    exit 1
fi