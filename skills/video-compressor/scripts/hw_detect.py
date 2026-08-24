#!/usr/bin/env python3
"""硬件检测与自适应编码配置模块。

检测系统硬件能力（Apple Silicon VideoToolbox 等），
自动选择最优 FFmpeg 编码参数。"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_hw_cache: dict | None = None


def ffmpeg_smoke_test(ffmpeg_path: str) -> None:
    """ffmpeg 二进制健全性测试。

    检测 ffmpeg 能否正常启动（处理 dyld 库缺失、版本不匹配等环境问题）。
    若失败，立即输出诊断信息和 brew 修复命令并退出脚本，
    而不是让后续编码器探测静默失败、误导用户。

    触发此函数的典型场景:
    - brew upgrade x265 后 ffmpeg 仍链接旧 libx265.215.dylib
    - brew reinstall ffmpeg 后未完成链接
    - 系统 Python/库路径冲突
    """
    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True, text=True, timeout=5,
        )
    except FileNotFoundError:
        print("错误：未找到 ffmpeg，请先安装: brew install ffmpeg")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("错误：ffmpeg -version 调用超时（5 秒）")
        sys.exit(1)
    except Exception as e:
        print(f"错误：ffmpeg 调用失败: {e}")
        sys.exit(1)

    # ffmpeg 启动崩溃通常非 0 返回码 + stderr 含 dyld / Library not loaded
    if result.returncode == 0 and "ffmpeg version" in result.stdout:
        return  # 通过

    # 保存完整诊断到临时文件，便于用户上报
    log_path = Path(tempfile.gettempdir()) / f"ffmpeg_smoke_test_{datetime.now():%Y%m%d_%H%M%S}.log"
    log_path.write_text(
        f"=== stdout ===\n{result.stdout}\n\n=== stderr ===\n{result.stderr}\n"
    )

    stderr = result.stderr
    symbol_match = re.search(r"_x265_api_get_\d+|_x264_api_get_\d+|Symbol not found: (\S+)", stderr)
    library_match = re.search(r"Library not loaded: (\S+)", stderr)
    version_match = re.search(r"tried: '([^']+)' \(no such file\)", stderr)

    print("错误：ffmpeg 二进制无法正常运行")
    print(f"返回码: {result.returncode}")
    if library_match:
        print(f"诊断: 缺失动态库 {library_match.group(1)}")
    if version_match:
        print(f"原因: 路径 {version_match.group(1)} 不存在")
    if symbol_match:
        print(f"符号: {symbol_match.group(0)}")
    if "dyld" in stderr or "Library not loaded" in stderr:
        print()
        print("常见原因: brew upgrade 升级某个依赖库后，ffmpeg 未重新链接。")
        print("修复命令:")
        print("  brew upgrade ffmpeg")
        print("  或: brew reinstall ffmpeg")
    print()
    print(f"完整诊断日志: {log_path}")
    sys.exit(1)


def detect_hardware() -> dict:
    """检测硬件能力，结果缓存在模块级别避免重复调用。"""
    global _hw_cache
    if _hw_cache is not None:
        return _hw_cache

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        print("错误：未找到 ffmpeg，请先安装: brew install ffmpeg")
        sys.exit(1)
    ffmpeg_smoke_test(ffmpeg_path)

    hw = {
        "platform": "unknown",
        "cpu_cores": os.cpu_count() or 4,
        "memory_gb": 0.0,
        "has_h264_vt": False,
        "has_hevc_vt": False,
        "ffmpeg_version": "",
    }

    # macOS Apple Silicon 检测
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.optional.arm64"],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip() == "1":
                hw["platform"] = "apple_silicon"
            else:
                hw["platform"] = "generic_mac"
        except Exception:
            hw["platform"] = "generic_mac"

        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.ncpu"],
                capture_output=True, text=True, timeout=5,
            )
            hw["cpu_cores"] = int(result.stdout.strip())
        except Exception:
            pass

        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
            )
            hw["memory_gb"] = round(int(result.stdout.strip()) / (1024 ** 3), 1)
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        hw["platform"] = "linux"

    # FFmpeg 编码器检测（smoke test 已确保 ffmpeg 能跑）
    try:
        result = subprocess.run(
            [ffmpeg_path, "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        encoders = result.stdout
        hw["has_h264_vt"] = "h264_videotoolbox" in encoders
        hw["has_hevc_vt"] = "hevc_videotoolbox" in encoders
    except Exception:
        pass

    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True, text=True, timeout=5,
        )
        m = re.search(r"ffmpeg version (\d+\.\d+)", result.stdout)
        if m:
            hw["ffmpeg_version"] = m.group(1)
    except Exception:
        pass

    _hw_cache = hw
    return hw


def select_profile(hw: dict, user_codec: str | None = None) -> dict:
    """根据硬件信息和用户偏好选择编码配置。"""
    # 用户手动指定
    codec_map = {
        "hevc_vt": _profile_hevc_vt,
        "h264_vt": _profile_h264_vt,
        "x264": _profile_x264,
        "x265": _profile_x265,
        "x264_fast": _profile_x264_fast,
    }
    if user_codec and user_codec in codec_map:
        return codec_map[user_codec]()

    # 自动选择
    if hw["platform"] == "apple_silicon" and hw["has_hevc_vt"]:
        return _profile_hevc_vt()
    if hw["platform"] == "apple_silicon" and hw["has_h264_vt"]:
        return _profile_h264_vt()
    return _profile_x264()


def _profile_hevc_vt() -> dict:
    # Apple Silicon VideoToolbox 是共享硬件编码器，多 ffmpeg 进程并行争抢
    # 会让单任务速度从 2-3x 降到 1-1.5x，串行处理多个文件效率更高。
    return {
        "name": "hevc_videotoolbox",
        "display_name": "HEVC VideoToolbox (硬件加速)",
        "tier": 1,
        "video_codec": "hevc_videotoolbox",
        "is_hardware": True,
        "optimal_workers": 1,
    }


def _profile_h264_vt() -> dict:
    # 同 _profile_hevc_vt 注释：VideoToolbox 共享硬件编码器，最佳并发为 1
    return {
        "name": "h264_videotoolbox",
        "display_name": "H.264 VideoToolbox (硬件加速)",
        "tier": 1,
        "video_codec": "h264_videotoolbox",
        "is_hardware": True,
        "optimal_workers": 1,
    }


def _profile_x264() -> dict:
    cores = os.cpu_count() or 4
    return {
        "name": "libx264",
        "display_name": "x264 (软件编码)",
        "tier": 3,
        "video_codec": "libx264",
        "is_hardware": False,
        "optimal_workers": min(cores, 8),
    }


def _profile_x265() -> dict:
    cores = os.cpu_count() or 4
    return {
        "name": "libx265",
        "display_name": "x265 (软件HEVC编码)",
        "tier": 3,
        "video_codec": "libx265",
        "is_hardware": False,
        "optimal_workers": min(cores, 8),
    }


def _profile_x264_fast() -> dict:
    cores = os.cpu_count() or 4
    return {
        "name": "libx264_ultrafast",
        "display_name": "x264 ultrafast (快速软件编码)",
        "tier": 2,
        "video_codec": "libx264",
        "is_hardware": False,
        "optimal_workers": min(cores, 8),
    }


def build_encode_args(
    profile: dict,
    crf: int | None = None,
    maxrate: str | None = None,
    bufsize: str | None = None,
    audio_bitrate: str | None = None,
    preset: str | None = None,
) -> list[str]:
    """根据编码配置构建完整的 FFmpeg 编码参数列表。"""
    audio_bitrate = audio_bitrate or "96k"

    name = profile["name"]

    if name == "hevc_videotooloolbox":
        # 不应到达这里，但作为安全网
        name = "hevc_videotoolbox"

    if name == "hevc_videotoolbox":
        args = [
            "-c:v", "hevc_videotoolbox",
            "-q:v", "65",
            "-b:v", maxrate or "2000k",
            "-maxrate", maxrate or "3000k",
            "-bufsize", bufsize or "3000k",
            "-tag:v", "hvc1",
            "-allow_sw", "1",
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", audio_bitrate,
        ]
        if crf is not None:
            print("  注意: VideoToolbox 编码器不支持 CRF 参数，已忽略")
        if preset is not None:
            print("  注意: VideoToolbox 编码器不支持 preset 参数，已忽略")
        return args

    if name == "h264_videotoolbox":
        args = [
            "-c:v", "h264_videotoolbox",
            "-q:v", "65",
            "-b:v", maxrate or "2000k",
            "-maxrate", maxrate or "3000k",
            "-bufsize", bufsize or "3000k",
            "-allow_sw", "1",
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", audio_bitrate,
        ]
        if crf is not None:
            print("  注意: VideoToolbox 编码器不支持 CRF 参数，已忽略")
        if preset is not None:
            print("  注意: VideoToolbox 编码器不支持 preset 参数，已忽略")
        return args

    if name == "libx265":
        return [
            "-c:v", "libx265",
            "-crf", str(crf or 28),
            "-maxrate", maxrate or "2500k",
            "-bufsize", bufsize or "2500k",
            "-preset", preset or "veryfast",
            "-pix_fmt", "yuv420p",
            "-tag:v", "hvc1",
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", audio_bitrate,
        ]

    if name == "libx264_ultrafast":
        return [
            "-c:v", "libx264",
            "-profile:v", "high",
            "-crf", str(crf or 23),
            "-maxrate", maxrate or "2500k",
            "-bufsize", bufsize or "2500k",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", audio_bitrate,
        ]

    # 默认 libx264（当前行为）
    return [
        "-c:v", "libx264",
        "-profile:v", "high",
        "-crf", str(crf or 23),
        "-maxrate", maxrate or "2500k",
        "-bufsize", bufsize or "2500k",
        "-preset", preset or "veryfast",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", audio_bitrate,
    ]


def print_hardware_info(hw: dict, profile: dict) -> None:
    """打印硬件检测和编码配置信息。"""
    if hw["platform"] == "apple_silicon":
        platform_str = f"Apple Silicon ({hw['cpu_cores']} 核 / {hw['memory_gb']:.0f} GB)"
    elif hw["platform"] == "generic_mac":
        platform_str = f"macOS ({hw['cpu_cores']} 核 / {hw['memory_gb']:.0f} GB)"
    else:
        platform_str = f"{hw['platform']} ({hw['cpu_cores']} 核)"

    print(f"硬件检测: {platform_str}")

    speed_hint = ""
    if profile["tier"] == 1:
        speed_hint = " — 预计速度提升 5-15x"
    elif profile["tier"] == 2:
        speed_hint = " — 速度优先模式"
    print(f"编码器: {profile['display_name']}{speed_hint}")

    if hw["ffmpeg_version"]:
        vt_support = []
        if hw["has_h264_vt"]:
            vt_support.append("H.264")
        if hw["has_hevc_vt"]:
            vt_support.append("HEVC")
        vt_str = f" (VideoToolbox: {' + '.join(vt_support)})" if vt_support else ""
        print(f"FFmpeg: {hw['ffmpeg_version']}{vt_str}")
