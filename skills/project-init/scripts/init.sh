#!/bin/bash
# project-init - 目录脚手架与项目检测
# 子命令：scaffold, detect
# Skill 安装委托 skill-manager/scripts/install.sh 处理

set -e

# --- scaffold: 创建 Skill 目录骨架 ---
# 用法: init.sh scaffold <project_dir> [skill_name]
handle_scaffold() {
    local project_dir="$1"
    local skill_name="${2:-$(basename "$project_dir")}"

    # 创建标准目录
    for dir in references scripts assets; do
        if [ ! -d "$project_dir/$dir" ]; then
            mkdir -p "$project_dir/$dir"
            echo "OK: 创建目录: $dir/"
        else
            echo "OK: 目录已存在: $dir/"
        fi
    done

    # 创建 SKILL.md（仅在不存在时）
    if [ ! -f "$project_dir/SKILL.md" ]; then
        cat > "$project_dir/SKILL.md" << SKILLEOF
---
name: ${skill_name}
description: |
  描述。本技能应在...时使用。不要用于：...
license: MIT License - 详见 LICENSE.txt
---

# ${skill_name}

## 概述

[描述技能的功能]

## 工作流程

[定义工作流步骤]
SKILLEOF
        echo "OK: 创建 SKILL.md"
    else
        echo "OK: SKILL.md 已存在，跳过"
    fi

    # 创建 LICENSE.txt（仅在不存在时）
    if [ ! -f "$project_dir/LICENSE.txt" ]; then
        cat > "$project_dir/LICENSE.txt" << 'LICENSEOF'
MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
LICENSEOF
        echo "OK: 创建 LICENSE.txt"
    else
        echo "OK: LICENSE.txt 已存在，跳过"
    fi
}

# --- codex: 创建 .codex/ 目录结构 ---
# 用法: init.sh codex <project_dir>
handle_codex() {
    local project_dir="$1"
    local script_dir="$(cd "$(dirname "$0")/.." && pwd)"

    # 创建 .codex 目录
    mkdir -p "$project_dir/.codex/rules"

    # 复制 config.toml
    if [ ! -f "$project_dir/.codex/config.toml" ]; then
        cp "$script_dir/references/codex-config.toml" "$project_dir/.codex/config.toml"
        echo "OK: 创建 .codex/config.toml"
    else
        echo "OK: .codex/config.toml 已存在，跳过"
    fi

    # 复制 rules/default.rules
    if [ ! -f "$project_dir/.codex/rules/default.rules" ]; then
        cp "$script_dir/references/codex-default.rules" "$project_dir/.codex/rules/default.rules"
        echo "OK: 创建 .codex/rules/default.rules"
    else
        echo "OK: .codex/rules/default.rules 已存在，跳过"
    fi

    # 创建 skills 软链 → ../.claude/skills
    if [ ! -e "$project_dir/.codex/skills" ]; then
        ln -s ../.claude/skills "$project_dir/.codex/skills"
        echo "OK: 创建 .codex/skills → ../.claude/skills"
    else
        echo "OK: .codex/skills 已存在，跳过"
    fi
}

# --- detect: 输出当前目录的指示文件列表 ---
# 用法: init.sh detect <project_dir>
handle_detect() {
    local project_dir="$1"

    echo "=== 文件指示器 ==="

    # 包管理文件
    for f in package.json pyproject.toml Cargo.toml go.mod requirements.txt Gemfile pom.xml build.gradle composer.json Makefile; do
        if [ -f "$project_dir/$f" ]; then
            echo "FOUND: $f"
        fi
    done

    # 前端配置
    for f in tailwind.config.js tailwind.config.ts next.config.js next.config.ts vite.config.ts nuxt.config.ts; do
        if [ -f "$project_dir/$f" ]; then
            echo "FOUND: $f"
        fi
    done

    # SKILL.md
    if [ -f "$project_dir/SKILL.md" ]; then
        echo "FOUND: SKILL.md (根目录)"
    fi

    # 检查 skills/ 目录下是否有 SKILL.md
    if [ -d "$project_dir/skills" ]; then
        for d in "$project_dir/skills"/*/; do
            if [ -f "$d/SKILL.md" ]; then
                echo "FOUND: skills/$(basename "$d")/SKILL.md"
            fi
        done
    fi

    # 目录指示器
    for d in src/components components pages app blog posts articles content drafts notebooks data analysis; do
        if [ -d "$project_dir/$d" ]; then
            echo "FOUND_DIR: $d/"
        fi
    done

    # Jupyter notebook
    local ipynb_count
    ipynb_count=$(find "$project_dir" -maxdepth 2 -name "*.ipynb" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$ipynb_count" -gt 0 ]; then
        echo "FOUND: *.ipynb (${ipynb_count} files)"
    fi

    # 文档文件统计
    local docx_count pdf_count
    docx_count=$(find "$project_dir" -maxdepth 2 -name "*.docx" 2>/dev/null | wc -l | tr -d ' ')
    pdf_count=$(find "$project_dir" -maxdepth 2 -name "*.pdf" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$docx_count" -gt 0 ] || [ "$pdf_count" -gt 0 ]; then
        echo "FOUND: .docx(${docx_count}) .pdf(${pdf_count})"
    fi
}

# --- 主入口 ---
ACTION="${1:-}"

case "$ACTION" in
    scaffold)
        if [ -z "$2" ]; then
            echo "用法: $0 scaffold <project_dir> [skill_name]"
            exit 1
        fi
        handle_scaffold "$2" "${3:-}"
        ;;
    detect)
        if [ -z "$2" ]; then
            echo "用法: $0 detect <project_dir>"
            exit 1
        fi
        handle_detect "$2"
        ;;
    codex)
        if [ -z "$2" ]; then
            echo "用法: $0 codex <project_dir>"
            exit 1
        fi
        handle_codex "$2"
        ;;
    *)
        echo "project-init 脚本"
        echo ""
        echo "用法:"
        echo "  $0 scaffold <project_dir> [skill_name]   创建 Skill 目录骨架"
        echo "  $0 detect <project_dir>                  检测项目指示文件"
        echo "  $0 codex <project_dir>                   创建 .codex/ 目录结构"
        echo ""
        echo "注意: Skill 安装请使用 skill-manager/scripts/install.sh"
        ;;
esac
