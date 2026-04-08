#!/bin/bash

# Skill Manager - Check Updates Script
# 检查所有已安装 Skills 的更新状态

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGER_DIR="$(dirname "$SCRIPT_DIR")"

# 检查 Python 是否可用
if ! command -v python3 &> /dev/null; then
    echo "❌ 需要 Python 3 来运行更新检查"
    exit 1
fi

RECORD_SCRIPT="$SCRIPT_DIR/record.py"
if [ ! -f "$RECORD_SCRIPT" ]; then
    echo "❌ 找不到记录模块: $RECORD_SCRIPT"
    exit 1
fi

# 执行检查
echo "🔍 正在检查 Skill 更新..."
echo ""

python3 "$RECORD_SCRIPT" check-all
