#!/bin/bash
# SVG Article Illustrator - SVG 归档脚本
# 从文章中提取嵌入的 SVG 代码并归档到 archive 目录

set -e

# 获取脚本所在目录的父目录（skill root）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(dirname "$SCRIPT_DIR")"

# 归档根目录
ARCHIVE_ROOT="$SKILL_ROOT/archive"

# 创建归档目录（如果不存在）
mkdir -p "$ARCHIVE_ROOT"

# 从文章中提取并归档 SVG
archive_svgs() {
    local article_path="$1"

    # 检查文件是否存在
    if [ ! -f "$article_path" ]; then
        echo "错误：文件不存在: $article_path"
        return 1
    fi

    # 获取文章绝对路径
    local abs_path="$(cd "$(dirname "$article_path")" && pwd)/$(basename "$article_path")"

    # 提取文章标题（第一个 # 标题）
    local title="$(grep -m1 '^# ' "$abs_path" 2>/dev/null | sed 's/^# //' | tr ' ' '_' | tr -d '[:punct:]' | cut -c1-50)"

    # 如果没有提取到标题，使用文件名
    if [ -z "$title" ]; then
        title="$(basename "$abs_path" .md)"
    fi

    # 生成时间戳
    local date_str="$(date +%Y%m%d)"
    local timestamp="$(date +%H%M%S)"

    # 创建归档目录
    local archive_dir="$ARCHIVE_ROOT/${date_str}_${timestamp}_${title}"
    mkdir -p "$archive_dir"

    # 提取 SVG 代码并保存为独立文件
    local svg_count=0
    local in_svg=false
    local svg_content=""
    local svg_index=1

    while IFS= read -r line; do
        if [[ "$line" =~ ^[[:space:]]*\<svg[[:space:]] ]]; then
            in_svg=true
            svg_content="$line"
        elif [[ "$line" =~ \</svg\>[[:space:]]*$ ]]; then
            svg_content="$svg_content"$'\n'"$line"
            in_svg=false

            # 提取 SVG 中的注释作为文件名（如果有）
            local svg_name=""
            if [[ "$svg_content" =~ \<\!\-\-[[:space:]]*配图[：:][[:space:]]*([^\-]+)\-\-\> ]]; then
                svg_name="${BASH_REMATCH[1]}"
                # 清理文件名：去除空格和特殊字符
                svg_name=$(echo "$svg_name" | tr -d '[:punct:]' | tr ' ' '_' | cut -c1-30)
            fi

            # 如果没有提取到名称，使用序号
            if [ -z "$svg_name" ]; then
                svg_name="illustration_${svg_index}"
            fi

            # 保存 SVG 文件
            local svg_file="$archive_dir/${svg_index}_${svg_name}.svg"
            echo "$svg_content" > "$svg_file"
            svg_count=$((svg_count + 1))
            svg_index=$((svg_index + 1))
            svg_content=""
        elif [ "$in_svg" = true ]; then
            svg_content="$svg_content"$'\n'"$line"
        fi
    done < "$abs_path"

    if [ $svg_count -eq 0 ]; then
        echo "⚠️  未在文章中找到 SVG 代码"
        return 1
    fi

    echo "✅ 已归档 $svg_count 个 SVG 到: $archive_dir"
    echo "📁 归档目录: $archive_dir"

    return 0
}

# 如果直接执行脚本，传递参数
if [ "${BASH_SOURCE[0]}" = "${0}" ] && [ $# -gt 0 ]; then
    archive_svgs "$1"
fi
