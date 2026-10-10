#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DY-002 隔离回归：压缩失败退出码与源文件替换保护

验证契约(对应 TASKS.md DY-002 验收):
1. 实跑短合成视频(ffmpeg 生成,隔离目录):
   - 成功 --keep 保留原片, *_compressed.mp4 可读; 默认替换后原路径可读、时长一致
   - 模拟 ffmpeg 非零(垃圾输入): 退出码 1, 源 SHA 不变, 无临时残留
   - 跳过小文件是明确成功结果(退出码 0)
2. 临时片命名 `.<stem>.compressing.mp4.tmp`: 不进入 *.mp4 / *_compressed.mp4 扫描集合
3. 故障注入(模块级): 输出无效(ffprobe 不可读)/时长漂移/替换失败 → False、源不变、临时清理
4. 符号链接拒绝替换; 旧命令兼容(--help/--user 不存在目录)

运行: cd <skill>/tests && python3 test_dy002_compress_safety.py
"""

import os
import io
import sys
import subprocess
import tempfile
import unittest
import hashlib
import importlib.util
from pathlib import Path
from unittest import mock
from contextlib import redirect_stdout

TESTS_DIR = Path(__file__).parent.resolve()
SCRIPTS_DIR = TESTS_DIR.parent / "scripts"
PY = sys.executable or "python3"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _make_video(path: Path, duration=3):
    subprocess.run([
        "ffmpeg", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=640x480:rate=15",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ], check=True, timeout=60)


def _probe_duration(path: Path) -> float:
    r = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path),
    ], capture_output=True, text=True, check=True)
    import json
    return float(json.loads(r.stdout)["format"]["duration"])


class CompressCLITest(unittest.TestCase):
    """真实 CLI + 真实 ffmpeg(合成短视频)"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dy002_"))
        _make_video(cls.tmp / "v_keep.mp4")
        _make_video(cls.tmp / "v_replace.mp4")
        _make_video(cls.tmp / "v_small.mp4", duration=1)
        (cls.tmp / "v_bad.mp4").write_bytes(b"THIS-IS-NOT-A-VIDEO-" * 100)

    def _cli(self, *args):
        return subprocess.run(
            [PY, str(SCRIPTS_DIR / "compress.py"), *args],
            capture_output=True, text=True, timeout=180,
        )

    def test_01_keep_preserves_original(self):
        src = self.tmp / "v_keep.mp4"
        before = _sha(src)
        p = self._cli("--file", str(src), "--keep", "--no-skip-small")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(_sha(src), before)  # 原片字节不变
        out = self.tmp / "v_keep_compressed.mp4"
        self.assertTrue(out.exists())
        self.assertAlmostEqual(_probe_duration(out), 3.0, delta=0.5)
        self.assertAlmostEqual(_probe_duration(src), 3.0, delta=0.5)

    def test_02_default_replace_readable(self):
        src = self.tmp / "v_replace.mp4"
        p = self._cli("--file", str(src), "--no-skip-small")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("已替换原文件", p.stdout)
        # 替换后原路径是可读、时长一致的视频
        self.assertAlmostEqual(_probe_duration(src), 3.0, delta=0.5)
        # 无临时残留
        leftovers = [f.name for f in self.tmp.iterdir() if f.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_03_ffmpeg_failure_source_intact(self):
        src = self.tmp / "v_bad.mp4"
        before = _sha(src)
        p = self._cli("--file", str(src), "--no-skip-small")
        self.assertEqual(p.returncode, 1, f"失败必须退出 1:\n{p.stdout}")
        self.assertIn("压缩失败", p.stdout)
        self.assertEqual(_sha(src), before)
        leftovers = [f.name for f in self.tmp.iterdir() if f.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_04_skip_small_is_success(self):
        src = self.tmp / "v_small.mp4"
        before = _sha(src)
        p = self._cli("--file", str(src))  # 默认跳过小文件
        self.assertEqual(p.returncode, 0)
        self.assertIn("跳过", p.stdout)
        self.assertEqual(_sha(src), before)

    def test_05_temp_naming_invisible_to_scanners(self):
        """临时片命名不进入 *.mp4 / *_compressed.mp4 扫描集合(pipeline 有效视频集)"""
        d = self.tmp / "scan_check"
        d.mkdir(exist_ok=True)
        (d / "real.mp4").write_bytes(b"x")
        (d / ".real.compressing.mp4.tmp").write_bytes(b"temp")
        mp4s = {f.name for f in d.glob("*.mp4")}
        self.assertEqual(mp4s, {"real.mp4"})
        comp = {f.name for f in d.glob("*_compressed.mp4")}
        self.assertEqual(comp, set())

    def test_06_symlink_refused(self):
        """符号链接:拒绝替换,退出 1,目标原样"""
        target = self.tmp / "v_keep.mp4"
        link = self.tmp / "link_to_video.mp4"
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(target)
        before = _sha(target)
        p = self._cli("--file", str(link), "--no-skip-small")
        self.assertEqual(p.returncode, 1)
        self.assertIn("符号链接", p.stdout)
        self.assertEqual(_sha(target), before)
        self.assertTrue(link.is_symlink())

    def test_07_old_command_surface(self):
        p = self._cli("--help")
        self.assertEqual(p.returncode, 0)
        for token in ("--user", "--file", "--keep", "--aggressive", "--no-skip-small"):
            self.assertIn(token, p.stdout)
        p2 = self._cli("--user", "不存在的目录xyz")
        self.assertEqual(p2.returncode, 0)
        self.assertIn("目录不存在", p2.stdout)


class CompressFaultInjectionTest(unittest.TestCase):
    """模块级故障注入:输出无效/时长漂移/替换失败"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SCRIPTS_DIR))
        import utils.config as cfg
        cls.cfg = cfg
        # 先设隔离 root 再 import compress(其模块级调用 get_download_path)
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="dy002_mod_"))
        cfg.set_overrides(download_root=str(cls.tmpdir / "root"))
        spec = importlib.util.spec_from_file_location("compress_under_test", SCRIPTS_DIR / "compress.py")
        cls.mod = importlib.util.module_from_spec(spec)
        sys.modules["compress_under_test"] = cls.mod
        spec.loader.exec_module(cls.mod)

    @classmethod
    def tearDownClass(cls):
        cls.cfg.set_overrides(download_root="", db_path="", following_path="")

    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="dy002_case_"))
        _make_video(self.d / "in.mp4", duration=2)
        self.src = self.d / "in.mp4"
        self.tmp_out = self.mod.temp_output_path(self.src)

    def test_10_invalid_output_cleaned(self):
        """ffmpeg 成功但输出 ffprobe 不可读 → False, 源不变, 临时清理"""
        real_info = self.mod.get_video_info(self.src)
        before = _sha(self.src)
        with mock.patch.object(self.mod, "get_video_info",
                               side_effect=[real_info, None]), \
             mock.patch.object(self.mod.subprocess, "run") as mrun:
            mrun.return_value = subprocess.CompletedProcess([], 0)  # 假装 ffmpeg 成功
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = self.mod.compress_video(self.src, self.tmp_out, replace=True, skip_small=False, aggressive=False)
        self.assertIs(rc, False)
        self.assertIn("输出无效", buf.getvalue())
        self.assertEqual(_sha(self.src), before)
        self.assertFalse(self.tmp_out.exists())

    def test_11_duration_drift_rejected(self):
        """输出时长与源漂移超容差 → False, 源不变, 临时清理"""
        src_info = dict(self.mod.get_video_info(self.src))
        bad_out = dict(src_info)
        bad_out["duration"] = src_info["duration"] + 5.0  # 远超 max(1s,2%)
        before = _sha(self.src)
        with mock.patch.object(self.mod, "get_video_info",
                               side_effect=[src_info, bad_out]), \
             mock.patch.object(self.mod.subprocess, "run") as mrun:
            mrun.return_value = subprocess.CompletedProcess([], 0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = self.mod.compress_video(self.src, self.tmp_out, replace=True, skip_small=False, aggressive=False)
        self.assertIs(rc, False)
        self.assertIn("时长异常", buf.getvalue())
        self.assertEqual(_sha(self.src), before)
        self.assertFalse(self.tmp_out.exists())

    def test_12_replace_failure_atomic_guard(self):
        """os.replace 抛错(替换失败) → False, 源不变, 临时清理"""
        real_info = self.mod.get_video_info(self.src)
        before = _sha(self.src)

        real_run = self.mod.subprocess.run

        def fake_run(cmd, **kw):
            # 真跑 ffmpeg 生成有效输出,再让替换失败
            return real_run(cmd, **kw)

        with mock.patch.object(self.mod.subprocess, "run", side_effect=fake_run), \
             mock.patch.object(self.mod.os, "replace", side_effect=OSError("模拟替换失败")):
            # get_video_info 对源/输出都用真实实现
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = self.mod.compress_video(self.src, self.tmp_out, replace=True, skip_small=False, aggressive=False)
        self.assertIs(rc, False)
        self.assertIn("替换失败", buf.getvalue())
        self.assertEqual(_sha(self.src), before)
        self.assertFalse(self.tmp_out.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
