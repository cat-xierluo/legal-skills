#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
本地 ASR Skill 环境检测脚本

检测当前环境是否满足 local-asr skill 的运行要求。
首次使用前必须运行此脚本进行环境检测。

用法:
    python3 scripts/check_env.py

退出码:
    0 - 所有检测通过
    1 - 检测失败（环境不满足要求）
"""

import sys
import shutil
import subprocess
import os
import platform
import importlib.util
from pathlib import Path

# 检测结果
issues = []
warnings = []
DEFAULT_BACKEND = os.environ.get("FUNASR_SERVER_DEFAULT_MODEL", "moss-mlx")


def check_python():
    """检测 Python 环境"""
    print("=" * 60)
    print("检测 Python3 环境...")
    print("-" * 60)

    # 1. 检查 python3 命令是否可用
    python3_path = shutil.which("python3")
    if python3_path:
        print(f"  ✅ python3 命令可用: {python3_path}")
    else:
        print("  ❌ python3 命令不可用")
        print("  💡 建议: 使用 Homebrew 安装 Apple Silicon 原生 Python 3.11")
        print("     brew install python@3.11")
        issues.append("python3 命令不可用")

    # 按执行当前检查脚本的解释器判断，避免虚拟环境与 PATH 中的 python3 不一致。
    print(f"  ℹ️  当前解释器: {sys.executable} (Python {sys.version.split()[0]})")
    if (3, 10) <= sys.version_info < (3, 13):
        print("  ✅ Python 版本满足完整安装要求 (3.10–3.12)")
    else:
        issues.append(f"Python 版本不受当前完整安装支持: {sys.version.split()[0]} (需要 3.10–3.12)")
        print("  ❌ 当前完整安装需要 Python 3.10–3.12")

    print()


def check_curl():
    """检测 curl"""
    print("=" * 60)
    print("检测 curl...")
    print("-" * 60)

    curl_path = shutil.which("curl")
    if curl_path:
        print(f"  ✅ curl 命令可用: {curl_path}")
        try:
            result = subprocess.run(
                ["curl", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            version_line = result.stdout.split("\n")[0]
            print(f"  ℹ️  {version_line}")
        except:
            pass
    else:
        print("  ❌ curl 命令不可用")
        print("  💡 建议: macOS 通常自带 curl，如果不可用请检查 PATH")
        issues.append("curl 命令不可用")

    print()


def check_basic_commands():
    """检测基本命令"""
    print("=" * 60)
    print("检测基本命令 (ls, ps, grep)...")
    print("-" * 60)

    basic_commands = ["ls", "ps", "grep"]
    all_ok = True

    for cmd in basic_commands:
        path = shutil.which(cmd)
        if path:
            print(f"  ✅ {cmd}: {path}")
        else:
            print(f"  ❌ {cmd}: 不可用")
            all_ok = False

    if not all_ok:
        issues.append("部分基本命令不可用")

    print()


def check_default_backend():
    """检查默认 MOSS 运行条件；旧管线可用环境变量显式选回。"""
    if DEFAULT_BACKEND != "moss-mlx":
        return
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        issues.append("MOSS 默认后端需要 Apple Silicon macOS；旧管线请设置 FUNASR_SERVER_DEFAULT_MODEL=paraformer")
    if shutil.which("ffmpeg") is None:
        issues.append("MOSS 需要 ffmpeg（macOS: brew install ffmpeg）")
    if importlib.util.find_spec("mlx_audio") is None:
        issues.append("尚未安装 mlx-audio[stt]；运行 python3 scripts/setup.py 安装默认后端")


def check_skill_dirs():
    """检测 skill 目录结构"""
    print("=" * 60)
    print("检测 Skill 目录结构...")
    print("-" * 60)

    script_dir = Path(__file__).parent.absolute()
    skill_dir = script_dir.parent

    required_files = [
        "SKILL.md",
        "scripts/server.py",
        "scripts/server-onnx.py",
        "scripts/transcribe.py",
        "scripts/auto_transcribe.py",
        "scripts/setup.py",
        "scripts/moss_mlx.py",
        "assets/requirements-moss-mlx.txt",
    ]

    all_ok = True
    for file_path in required_files:
        full_path = skill_dir / file_path
        if full_path.exists():
            print(f"  ✅ {file_path}")
        else:
            print(f"  ❌ {file_path} (缺失)")
            all_ok = False

    if not all_ok:
        issues.append("Skill 文件缺失")

    print()

    return all_ok


def main():
    print()
    print("=" * 60)
    print("  本地 ASR Skill - 环境检测")
    print("=" * 60)
    print()
    print("首次使用 local-asr skill 前，请先检测环境是否满足要求。")
    print()

    check_python()
    check_curl()
    check_basic_commands()
    check_default_backend()
    skill_ok = check_skill_dirs()

    # 汇总结果
    print("=" * 60)
    print("  检测结果汇总")
    print("=" * 60)

    for warning in warnings:
        print(f"  ⚠️  {warning}")

    if not issues:
        print()
        print("  ✅ 所有检测通过！环境满足要求。")
        print()
        print("  下一步：")
        if DEFAULT_BACKEND == "moss-mlx":
            print("    1. 安装两套后端: python3 scripts/setup.py")
            print("    2. 启动默认 MOSS 服务: python3 scripts/server.py")
        else:
            print("    1. 安装旧 FunASR 后端: python3 scripts/setup.py --legacy")
            print("    2. 使用 FUNASR_SERVER_DEFAULT_MODEL=paraformer 启动 scripts/server.py")
            print("       或运行 scripts/server-onnx.py --preload")
        print("    3. 开始转录！")
        print()
        return 0
    else:
        print()
        print(f"  ❌ 检测到 {len(issues)} 个问题，环境不满足要求：")
        print()
        for i, issue in enumerate(issues, 1):
            print(f"    {i}. {issue}")
        print()
        print("  请修复上述问题后重新运行检测：")
        print("    python3 scripts/check_env.py")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
