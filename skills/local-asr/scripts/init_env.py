#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
Local ASR 环境检测与配置生成脚本

检测当前环境的工具路径和依赖，生成 skill-env.json 供执行器读取。
适用于 Claude Code CLI（诊断用）和 Raycast agent-executor（环境注入用）。

用法:
    python3 scripts/init_env.py          # 检测环境并生成 skill-env.json
    python3 scripts/init_env.py --check  # 只检测，不写文件
    python3 scripts/init_env.py --force  # 强制重新检测（覆盖已有文件）

退出码:
    0 - 检测通过，skill-env.json 已生成
    1 - 检测失败（缺少必要工具）
"""

import os
import sys
import json
import shutil
import platform
import subprocess
import argparse
import importlib.util
import importlib.metadata
from pathlib import Path
from datetime import datetime

# skill 根目录
SKILL_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = SKILL_DIR / "assets" / "skill-env.json"

# 必需工具
REQUIRED_TOOLS = ["python3", "curl"]
# 可选但建议的工具
OPTIONAL_TOOLS = ["ffmpeg", "ffprobe"]
# Python 依赖（检测是否已安装）
PYTHON_DEPS = ["mlx_audio", "funasr", "funasr_onnx", "torch", "fastapi", "uvicorn"]


def get_login_shell_path():
    """通过 login shell 获取完整的 PATH 环境变量"""
    system = platform.system()

    if system == "Darwin" or system == "Linux":
        # 尝试通过 login shell 获取 PATH
        shell = os.environ.get("SHELL", "/bin/zsh")
        try:
            result = subprocess.run(
                [shell, "-l", "-c", "echo $PATH"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # 备选：尝试 path_helper（macOS）
        if system == "Darwin":
            try:
                result = subprocess.run(
                    ["/usr/libexec/path_helper", "-s"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    # path_helper 输出格式: PATH="..."; export PATH;
                    path_line = result.stdout.strip()
                    if 'PATH="' in path_line:
                        path_val = path_line.split('PATH="')[1].split('"')[0]
                        return path_val
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

    # 最终回退：使用当前 PATH
    return os.environ.get("PATH", "")


def detect_tool(name, search_path=None):
    """检测工具的实际路径"""
    return shutil.which(name, path=search_path)


def detect_python_version(python_path):
    """检测 Python 版本"""
    if not python_path:
        return None
    try:
        result = subprocess.run(
            [python_path, "--version"],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout.strip() or result.stderr.strip()
        return output.replace("Python ", "")
    except Exception:
        return None


def check_python_deps():
    """检查 Python 依赖是否已安装"""
    installed = {}
    for dep in PYTHON_DEPS:
        try:
            if importlib.util.find_spec(dep) is None:
                installed[dep] = None
                continue
            try:
                installed[dep] = importlib.metadata.version(dep.replace("_", "-"))
            except importlib.metadata.PackageNotFoundError:
                installed[dep] = "已安装"
        except Exception:
            installed[dep] = None
    return installed


def run_detection():
    """执行完整的环境检测"""
    issues = []
    warnings = []
    default_backend = os.environ.get("FUNASR_SERVER_DEFAULT_MODEL", "moss-mlx")

    # 1. 获取完整 PATH
    # 登录 shell 可能丢掉当前虚拟环境；执行器必须继续使用检测过依赖的 Python。
    full_path = os.pathsep.join((str(Path(sys.executable).parent), get_login_shell_path()))
    if not full_path:
        issues.append("无法获取 PATH 环境变量")

    # 2. 检测必需工具
    detected_tools = {}
    for tool in REQUIRED_TOOLS:
        path = detect_tool(tool, full_path)
        if path:
            detected_tools[tool] = path
        else:
            # 也尝试在默认 PATH 中查找
            path = detect_tool(tool)
            if path:
                detected_tools[tool] = path
            else:
                issues.append(f"必需工具 {tool} 未找到")

    # 3. 检测可选工具
    for tool in OPTIONAL_TOOLS:
        path = detect_tool(tool, full_path) or detect_tool(tool)
        if path:
            detected_tools[tool] = path
        else:
            if tool == "ffmpeg":
                message = "ffmpeg 未安装（MOSS 音频归一化必需；macOS: brew install ffmpeg）"
                (issues if default_backend == "moss-mlx" else warnings).append(message)

    # 4. Python 版本
    python_version = None
    if "python3" in detected_tools:
        python_version = detect_python_version(detected_tools["python3"])
        if python_version:
            parts = python_version.split(".")
            if len(parts) >= 2 and (int(parts[0]) < 3 or int(parts[1]) < 8):
                issues.append(f"Python 版本过低: {python_version}（需要 >= 3.8）")

    # 5. Python 依赖
    python_deps = check_python_deps()
    if default_backend == "moss-mlx":
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            issues.append("MOSS 默认后端需要 Apple Silicon macOS；旧管线可设置 FUNASR_SERVER_DEFAULT_MODEL=paraformer")
        if sys.version_info < (3, 10):
            issues.append("MOSS 默认后端需要 Python 3.10+")
        if not python_deps.get("mlx_audio"):
            issues.append("缺少 mlx-audio[stt]；运行 python3 -m pip install -r assets/requirements-moss-mlx.txt")

    return {
        "full_path": full_path,
        "tools": detected_tools,
        "python_version": python_version,
        "python_deps": python_deps,
        "default_backend": default_backend,
        "issues": issues,
        "warnings": warnings,
    }


def generate_env_json(detection):
    """生成 skill-env.json 内容"""
    # 只保留实际需要的命令目录，避免把登录 shell 的临时/个人 PATH 写入配置。
    path_dirs = [str(Path(sys.executable).parent)]
    path_dirs.extend(str(Path(path).parent) for path in detection["tools"].values() if path)
    path_dirs.extend(("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"))
    runtime_path = os.pathsep.join(dict.fromkeys(path_dirs))
    env_data = {
        "env": {
            "PATH": runtime_path,
            "FUNASR_SERVER_DEFAULT_MODEL": detection["default_backend"],
        },
        "detected": {
            **detection["tools"],
            "python_version": detection["python_version"],
            "python_deps": detection["python_deps"],
            "platform": platform.system(),
            "machine": platform.machine(),
            "detected_at": datetime.now().isoformat(),
            "default_backend": detection["default_backend"],
        },
    }

    # 添加自定义环境变量
    if "python3" in detection["tools"]:
        env_data["env"]["FUNASR_PYTHON"] = sys.executable

    return env_data


def print_results(detection):
    """打印检测结果"""
    print()
    print("=" * 60)
    print("  Local ASR - 环境检测")
    print("=" * 60)
    print()

    # PATH
    print(f"  PATH: {detection['full_path'][:80]}...")
    print()

    # 工具
    print("  工具检测:")
    for tool in REQUIRED_TOOLS:
        path = detection["tools"].get(tool)
        status = f"✅ {path}" if path else "❌ 未找到"
        print(f"    {tool}: {status}")
    for tool in OPTIONAL_TOOLS:
        path = detection["tools"].get(tool)
        status = f"✅ {path}" if path else "⚠️  未安装（可选）"
        print(f"    {tool}: {status}")
    print()

    # Python
    if detection["python_version"]:
        print(f"  Python 版本: {detection['python_version']}")
    print()

    # 依赖
    print("  Python 依赖:")
    for dep, ver in detection["python_deps"].items():
        status = f"✅ {ver}" if ver else "❌ 未安装"
        print(f"    {dep}: {status}")
    print()

    # 问题
    if detection["issues"]:
        print(f"  ❌ 发现 {len(detection['issues'])} 个问题:")
        for issue in detection["issues"]:
            print(f"    - {issue}")
        print()

    if detection["warnings"]:
        for w in detection["warnings"]:
            print(f"  ⚠️  {w}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Local ASR 环境检测与配置生成")
    parser.add_argument("--check", action="store_true", help="只检测，不写文件")
    parser.add_argument("--force", action="store_true", help="强制重新检测")
    args = parser.parse_args()

    # 如果已有 skill-env.json 且不是强制模式，跳过
    if ENV_FILE.exists() and not args.force and not args.check:
        print(f"✅ skill-env.json 已存在: {ENV_FILE}")
        print("   使用 --force 强制重新检测")
        return 0

    # 执行检测
    detection = run_detection()
    print_results(detection)

    # 如果有严重问题，报错退出
    if detection["issues"]:
        print("=" * 60)
        print("  ❌ 环境检测未通过，请修复上述问题后重试")
        print("  运行 python3 scripts/setup.py 安装依赖")
        print("=" * 60)
        return 1

    # 生成 skill-env.json
    if not args.check:
        env_data = generate_env_json(detection)
        ENV_FILE.write_text(
            json.dumps(env_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"  ✅ 已生成: {ENV_FILE}")
        print()

    print("=" * 60)
    print("  ✅ 环境检测通过")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
