#!/bin/bash
# 专利下载工具 Wrapper
#
# 分流逻辑：
#   - 第一个参数是 google → 走 cli.py 统一入口（推荐，免费免登录）
#   - 其他参数（含空）   → 走 download.py 旧入口（epub 专利公布公告系统专用）
#
# 说明：cli.py 已是多平台统一入口，本 wrapper 主要为保留"非 google 默认走 epub
# 老脚本"的历史行为。新用法建议直接 python cli.py <平台> <专利号>。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 检查参数：如果第一个参数是 google，走 cli.py
if [ "$1" = "google" ]; then
    # 检查 patent-downloader
    if ! python3 -c "from patent_downloader import PatentDownloader" 2>/dev/null; then
        echo "📦 安装 Google Patents 依赖..."
        pip install patent-downloader
    fi
    # 运行新入口
    python3 cli.py "$@"
    exit $?
fi

# 老版路径：检查 playwright
if ! python3 -c "import playwright" 2>/dev/null; then
    echo "📦 安装浏览器自动化依赖..."
    pip install -r requirements.txt
    playwright install chromium
fi

# 运行下载脚本（老版，专利公布公告系统专用）
python3 download.py "$@"
