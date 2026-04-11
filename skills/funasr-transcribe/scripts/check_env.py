#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
FunASR Skill 环境检测脚本

检测当前环境是否满足 funasr-transcribe skill 的运行要求。
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
from pathlib import Path

# 检测结果
issues = []
warnings = []


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
        print("  💡 建议: 使用 homebrew 安装 python@3.14")
        print("     brew install python@3.14")
        issues.append("python3 命令不可用")

    # 2. 检查 Python 版本
    try:
        result = subprocess.run(
            ["python3", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        version_output = result.stdout.strip() or result.stderr.strip()
        print(f"  ℹ️  {version_output}")

        # 解析版本号
        version_str = version_output.replace("Python ", "")
        major, minor, _ = version_str.split(".")[:3]
        if int(major) >= 3 and int(minor) >= 8:
            print("  ✅ Python 版本满足要求 (>= 3.8)")
        else:
            issues.append(f"Python 版本过低: {version_str} (需要 >= 3.8)")
            print(f"  ❌ Python 版本过低 (需要 >= 3.8)")
    except FileNotFoundError:
        print("  ❌ 无法执行 python3 命令")
    except subprocess.TimeoutExpired:
        print("  ❌ python3 命令执行超时")
    except Exception as e:
        print(f"  ❌ 检查 Python 版本时出错: {e}")

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
        "scripts/transcribe.py",
        "scripts/auto_transcribe.py",
        "scripts/setup.py",
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
    print("  FunASR Skill - 环境检测")
    print("=" * 60)
    print()
    print("首次使用 funasr-transcribe skill 前，请先检测环境是否满足要求。")
    print()

    check_python()
    check_curl()
    check_basic_commands()
    skill_ok = check_skill_dirs()

    # 汇总结果
    print("=" * 60)
    print("  检测结果汇总")
    print("=" * 60)

    if not issues:
        print()
        print("  ✅ 所有检测通过！环境满足要求。")
        print()
        print("  下一步：")
        print("    1. 运行安装脚本: python3 scripts/setup.py")
        print("    2. 启动服务: python3 scripts/server.py")
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
