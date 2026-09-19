#!/usr/bin/env python3
"""渲染器选址与 fail-closed 回归。

覆盖四个验收点：
1. PATH 里是开发构建、正式版在 Cask 时，_find_soffice 必须选正式版；
2. 显式 --soffice 始终优先；
3. development/unknown 渲染器在 rendered 门禁中硬失败（不渲染、不误判通过）；
4. render_docx 每次渲染携带唯一 -env:UserInstallation（避免单实例锁）。
"""
from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import layout_gate  # noqa: E402
from layout_gate import (  # noqa: E402
    _find_soffice,
    _renderer_kind,
    _soffice_version,
    audit_docx,
    check,
    render_docx,
    W,
)
from test_layout_gate import POLICY, make_document, write_opc_docx  # noqa: E402


def make_fake_soffice(root: Path, name: str, version_line: str) -> Path:
    """造一个可执行的假 soffice，--version 输出指定版本行。"""
    path = root / name
    path.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"--version\" ]; then\n"
        f"  echo '{version_line}'\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


class RendererSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ecg-renderer-sel-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_official_preferred_over_dev(self):
        """回归：PATH 命中的是开发构建（LibreOfficeDev alpha）、Cask 里有
        正式版时，必须选正式版——headless 开发构建不暴露系统中文字体，
        不能作为中文视觉 oracle。"""
        dev = make_fake_soffice(
            self.root, "dev-soffice", "LibreOfficeDev 26.8.0.0.alpha0 abc123"
        )
        official = make_fake_soffice(
            self.root, "official-soffice", "LibreOffice 25.8.4.2 def456"
        )
        with mock.patch.object(
            layout_gate, "_candidate_soffice_paths", return_value=[str(dev), str(official)]
        ):
            self.assertEqual(_find_soffice(), str(official))

    def test_explicit_path_always_wins(self):
        """显式 --soffice 优先于自动选址（即使它是开发构建——由门禁 fail-closed）。"""
        explicit = make_fake_soffice(
            self.root, "explicit-soffice", "LibreOfficeDev 26.8.0.0.alpha0 abc123"
        )
        official = make_fake_soffice(
            self.root, "official-soffice", "LibreOffice 25.8.4.2 def456"
        )
        with mock.patch.object(
            layout_gate, "_candidate_soffice_paths", return_value=[str(official)]
        ):
            self.assertEqual(_find_soffice(explicit), str(explicit))

    def test_rendered_gate_fails_closed_on_development_renderer(self):
        """回归：development/unknown 渲染器在 rendered 门禁中必须硬失败，
        不渲染、不给任何“通过”结论（简单文档在 alpha 下缺字不明显会被误判）。"""
        docx = write_opc_docx(self.root, grid=(3504, 3504), margins=(2449, 2449))
        static = audit_docx(docx, dict(POLICY))
        self.assertTrue(static["ok"], static["issues"])
        dev = make_fake_soffice(
            self.root, "dev-only-soffice", "LibreOfficeDev 26.8.0.0.alpha0 abc123"
        )
        with mock.patch.object(layout_gate, "_find_soffice", return_value=str(dev)):
            report = check(docx, dict(POLICY), rendered=True)
        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "FAIL")
        messages = " ".join(item["message"] for item in report["issues"])
        self.assertIn("开发构建", messages)

    def test_rendered_gate_fails_closed_on_unknown_renderer(self):
        """回归：--version 输出为空（unknown）的渲染器同样必须硬失败，
        不得让无法判定资格的渲染器参与中文视觉验收。"""
        docx = write_opc_docx(self.root, grid=(3504, 3504), margins=(2449, 2449))
        unknown = make_fake_soffice(self.root, "unknown-soffice", "")
        self.assertEqual(_renderer_kind(_soffice_version(str(unknown))), "unknown")
        with mock.patch.object(layout_gate, "_find_soffice", return_value=str(unknown)):
            report = check(docx, dict(POLICY), rendered=True)
        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "FAIL")
        messages = " ".join(item["message"] for item in report["issues"])
        self.assertIn("未知", messages)

    def test_render_docx_uses_unique_user_installation(self):
        """每次渲染必须携带唯一 -env:UserInstallation（LibreOffice 单实例锁
        会让并发渲染互相踢掉，表现为 exit=0 的假失败）。"""
        captured: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))
            return mock.Mock(returncode=1, stdout="", stderr="")

        with mock.patch.object(layout_gate.shutil, "which", return_value=None), \
                mock.patch.object(layout_gate.subprocess, "run", side_effect=fake_run):
            for _ in range(2):
                with self.assertRaises(RuntimeError):
                    render_docx(
                        write_opc_docx(self.root, grid=(3504, 3504), margins=(2449, 2449)),
                        soffice=make_fake_soffice(
                            self.root, f"noop-{len(captured)}", "LibreOffice 25.8.4.2"
                        ),
                    )
        self.assertEqual(len(captured), 2)
        profiles = []
        for cmd in captured:
            env_args = [arg for arg in cmd if arg.startswith("-env:UserInstallation=")]
            self.assertEqual(len(env_args), 1, f"缺少唯一 UserInstallation: {cmd}")
            profiles.append(env_args[0])
        self.assertNotEqual(profiles[0], profiles[1], "两次渲染的 profile 不应相同")
        self.assertTrue(all(p.startswith("-env:UserInstallation=file://") for p in profiles))

    def test_renderer_kind_classification(self):
        self.assertEqual(_renderer_kind("LibreOffice 25.8.4.2 abc"), "official")
        self.assertEqual(_renderer_kind("LibreOfficeDev 26.8.0.0.alpha0 abc"), "development")
        self.assertEqual(_renderer_kind(""), "unknown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
