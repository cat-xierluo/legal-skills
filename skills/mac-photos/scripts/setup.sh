#!/bin/bash
#
# setup.sh — mac-photos 技能一键环境安装
#
# 做三件事:
#   1. 创建 Python venv 并安装 osxphotos（默认 ~/venvs/osxphotos, 可用 OSXPHOTOS_VENV 覆盖）
#   2. 用 swiftc 编译 Vision OCR 工具到 scripts/bin/（ocr-vision / mktext）
#   3. 运行 doctor 自检, 输出各项状态
#
# 国内网络较慢时可用清华镜像:
#   OSXPHOTOS_PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple bash setup.sh
#
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${OSXPHOTOS_VENV:-$HOME/venvs/osxphotos}"
PIP_INDEX="${OSXPHOTOS_PIP_INDEX:-}"

echo "==> [1/3] 安装 osxphotos 到 venv: $VENV"
if [ -x "$VENV/bin/osxphotos" ]; then
    echo "    已存在, 跳过: $($VENV/bin/osxphotos --version | head -1)"
else
    python3 -m venv "$VENV"
    if [ -n "$PIP_INDEX" ]; then
        "$VENV/bin/pip" install --disable-pip-version-check -i "$PIP_INDEX" osxphotos
    else
        "$VENV/bin/pip" install --disable-pip-version-check osxphotos
    fi
fi

echo "==> [2/3] 编译 Vision OCR 工具"
if ! command -v swiftc >/dev/null 2>&1; then
    echo "❌ 未找到 swiftc, 请先安装 Xcode Command Line Tools: xcode-select --install" >&2
    exit 1
fi
mkdir -p "$SKILL_DIR/scripts/bin"
swiftc -O -o "$SKILL_DIR/scripts/bin/ocr-vision" "$SKILL_DIR/scripts/ocr_vision.swift"
swiftc -O -o "$SKILL_DIR/scripts/bin/mktext" "$SKILL_DIR/scripts/mktext.swift"
echo "    编译完成: scripts/bin/ocr-vision, scripts/bin/mktext"

echo "==> [3/3] 环境自检"
"$VENV/bin/python3" "$SKILL_DIR/scripts/photos_read.py" doctor
