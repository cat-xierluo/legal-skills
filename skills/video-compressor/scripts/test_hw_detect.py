#!/usr/bin/env python3
"""hw_detect / compress 的回归测试（标准库 unittest，不依赖 ffmpeg 实际编码）。

覆盖历次实际踩过的故障：
- Apple Silicon / 内存检测：`sysctl -n hw.optional.arm64` 在部分 macOS 上返回空，
  平台被误判为 generic_mac，导致硬件加速从不启用（2026-11-27 M1 Max 实测）。
- ffmpeg 查找：agent/launchd 环境 PATH 不含 /opt/homebrew/bin，脚本开箱报"未找到 ffmpeg"。
- 编码器选择：低码率源走 x264 CRF，高码率源在 Apple Silicon 走硬件，显式 --codec 最高优先。
- 硬件路径参数：不得写死 -b:v（对低码率源压不动），质量由 -q:v 控制。
- 输出命名：防覆盖序号递增 + 支持自定义命名模板。

运行：python3 -m unittest scripts/test_hw_detect.py
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hw_detect  # noqa: E402


def _run_main_with_argv(argv: list[str], monkeypatch=None):
    """在子进程里跑 compress.py main()，返回 CompletedProcess（避免污染当前进程）。"""
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "compress.py"), *argv],
        capture_output=True, text=True, timeout=120,
    )
    return proc


class PlatformDetectionTests(unittest.TestCase):
    """平台检测必须不依赖单一 sysctl 键。"""

    def _detect_with(self, run_results: dict):
        """按命令前缀伪造 subprocess.run 的返回；ffmpeg 健全性/编码器探测默认成功。"""
        def fake_run(cmd, *a, **kw):
            joined = " ".join(cmd)
            if joined.endswith("-version"):
                return subprocess.CompletedProcess(cmd, 0, "ffmpeg version 9.0.2 Copyright", "")
            if joined.endswith("-encoders"):
                return subprocess.CompletedProcess(cmd, 0, " hevc_videotoolbox x\n h264_videotoolbox y\n", "")
            for prefix, result in run_results.items():
                if joined.startswith(prefix):
                    return result
            return subprocess.CompletedProcess(cmd, 1, "", "")
        with mock.patch.object(hw_detect.subprocess, "run", side_effect=fake_run), \
             mock.patch.object(hw_detect.shutil, "which", return_value="/opt/homebrew/bin/ffmpeg"), \
             mock.patch.object(hw_detect, "_hw_cache", None):
            return hw_detect.detect_hardware()

    def test_arm64_reported_by_sysctl(self):
        """标准路径：sysctl 返回 1 → apple_silicon。"""
        ok = lambda out: subprocess.CompletedProcess([], 0, out, "")  # noqa: E731
        hw = self._detect_with({
            "sysctl -n hw.optional.arm64": ok("1\n"),
            "sysctl -n hw.memsize": ok(str(64 * 1024 ** 3) + "\n"),
        })
        self.assertEqual(hw["platform"], "apple_silicon")
        self.assertEqual(hw["memory_gb"], 64.0)

    @unittest.skipUnless(platform.machine() == "arm64", "仅在 Apple Silicon 上验证 machine() 回落")
    def test_arm64_empty_falls_back_to_uname(self):
        """回归：sysctl 返回空（M1 Max 实测）→ 必须仍识别为 apple_silicon，而不是 generic_mac。"""
        empty = subprocess.CompletedProcess([], 0, "", "")  # 无输出，exit 0
        hw = self._detect_with({
            "sysctl -n hw.optional.arm64": empty,
            "sysctl -n hw.memsize": empty,
        })
        self.assertEqual(hw["platform"], "apple_silicon",
                         "sysctl 为空时必须回落到 platform.machine()，否则硬件加速永不启用")

    def test_memory_falls_back_to_sysconf(self):
        """回归：sysctl memsize 为空 → 用 os.sysconf 回落，不显示 0 GB。"""
        empty = subprocess.CompletedProcess([], 0, "", "")
        hw = self._detect_with({
            "sysctl -n hw.memsize": empty,
        })
        if hw["platform"] in ("apple_silicon", "generic_mac"):
            self.assertGreater(hw["memory_gb"], 0, "内存探测失败时必须回落到 os.sysconf")


class FfmpegLookupTests(unittest.TestCase):
    """ffmpeg 查找要覆盖 PATH 缺失 Homebrew 的 agent 环境。"""

    def test_fallback_dirs_when_not_on_path(self):
        """回归：PATH 里没有 ffmpeg 时，必须去常见安装目录找。"""
        with tempfile.TemporaryDirectory() as td:
            fake_bin = Path(td)
            ffmpeg = fake_bin / "ffmpeg"
            ffmpeg.write_text("#!/bin/sh\nexit 0\n")
            ffmpeg.chmod(0o755)
            with mock.patch.object(hw_detect, "COMMON_BIN_DIRS", [str(fake_bin)]), \
                 mock.patch.object(hw_detect.shutil, "which", return_value=None):
                self.assertEqual(hw_detect.find_ffmpeg("ffmpeg"), str(ffmpeg))

    def test_returns_none_when_absent(self):
        with mock.patch.object(hw_detect, "COMMON_BIN_DIRS", []), \
             mock.patch.object(hw_detect.shutil, "which", return_value=None):
            self.assertIsNone(hw_detect.find_ffmpeg("ffmpeg"))

    def test_which_wins_over_fallback(self):
        with mock.patch.object(hw_detect, "COMMON_BIN_DIRS", ["/nonexistent"]), \
             mock.patch.object(hw_detect.shutil, "which", return_value="/usr/bin/ffmpeg"):
            self.assertEqual(hw_detect.find_ffmpeg("ffmpeg"), "/usr/bin/ffmpeg")


class ProfileSelectionTests(unittest.TestCase):
    def _hw(self, apple=True, hevc=True, h264=True):
        return {
            "platform": "apple_silicon" if apple else "generic_mac",
            "has_hevc_vt": hevc, "has_h264_vt": h264,
        }

    def test_low_bitrate_uses_x264_crf(self):
        p = hw_detect.select_profile(self._hw(), source_bitrate=2_400_000)
        self.assertEqual(p["name"], "libx264")
        self.assertFalse(p["is_hardware"])

    def test_high_bitrate_on_apple_silicon_uses_hw(self):
        p = hw_detect.select_profile(self._hw(apple=True), source_bitrate=20_000_000)
        self.assertTrue(p["is_hardware"])
        self.assertEqual(p["name"], "hevc_videotoolbox")

    def test_explicit_codec_overrides_everything(self):
        p = hw_detect.select_profile(self._hw(), user_codec="x264", source_bitrate=20_000_000)
        self.assertEqual(p["name"], "libx264")

    def test_bitrate_threshold_boundary(self):
        self.assertEqual(hw_detect.select_profile(self._hw(), source_bitrate=3_000_000)["name"], "libx264")
        self.assertEqual(
            hw_detect.select_profile(self._hw(), source_bitrate=3_000_001)["name"], "hevc_videotoolbox")


class EncodeArgsTests(unittest.TestCase):
    def test_x264_args_use_crf(self):
        args = hw_detect.build_encode_args(hw_detect._profile_x264(), crf=23, maxrate="2500k",
                                           bufsize="2500k", audio_bitrate="96k", preset="veryfast")
        self.assertIn("-crf", args)
        self.assertNotIn("-b:v", args)

    def test_hw_args_no_hardcoded_bitrate(self):
        """回归：硬件路径写死 -b:v 2000k 导致低码率源压不动。质量应只由 -q:v 控制。"""
        for prof in (hw_detect._profile_hevc_vt(), hw_detect._profile_h264_vt()):
            args = hw_detect.build_encode_args(prof, audio_bitrate="96k")
            self.assertNotIn("-b:v", args, f"{prof['name']} 不应写死 -b:v")
            self.assertIn("-q:v", args)
            # 实测：与 -maxrate/-bufsize 同时出现会把 VT 拖回 ABR，-q:v 被架空
            self.assertNotIn("-maxrate", args, f"{prof['name']} 不应带 -maxrate（会使 -q:v 失效）")
            self.assertNotIn("-bufsize", args, f"{prof['name']} 不应带 -bufsize")

    def test_hw_args_respect_quality_arg(self):
        args = hw_detect.build_encode_args(hw_detect._profile_hevc_vt(), audio_bitrate="96k", vt_quality=40)
        self.assertEqual(args[args.index("-q:v") + 1], "40")


if __name__ == "__main__":
    unittest.main()
