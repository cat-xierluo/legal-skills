#!/usr/bin/env python3
"""Offline tests for check-readme-coverage link matching and rename fallback."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("check-readme-coverage.py")
SPEC = importlib.util.spec_from_file_location("check_readme_coverage", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def run_main(readme_text: str, assets: list[str]) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text(readme_text, encoding="utf-8")
        assets_json = root / "assets.json"
        assets_json.write_text(json.dumps({"assets": [
            {"name": name, "browser_download_url": f"url/{name}"} for name in assets
        ]}), encoding="utf-8")
        argv = ["check-readme-coverage.py",
                "--assets-json", str(assets_json),
                "cat-xierluo/legal-skills", str(root / "README.md")]
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err), \
                unittest.mock.patch.object(sys, "argv", argv):
            code = MODULE.main()
        return code


class CheckReadmeCoverageTest(unittest.TestCase):
    ROW = (
        '<tr><td><a href="skills/{skill}/"><strong>{skill}</strong></a></td>'
        "<td>工具</td><td>说明</td><td>MIT</td>"
        '<td>v1.0.0</td>'
        '<td><a href="https://github.com/cat-xierluo/legal-skills/releases/{link}">下载</a></td>'
        "<td></td></tr>"
    )

    def test_latest_download_form_matches(self) -> None:
        """latest/download 形态的下载链必须被识别（回归：alternation 缺尾斜杠）。"""
        readme = "<table>\n" + self.ROW.format(
            skill="demo-skill", link="latest/download/demo-skill-1.0.0.zip") + "\n</table>\n"
        self.assertEqual(run_main(readme, ["demo-skill-1.0.0.zip"]), 0)

    def test_pinned_tag_form_matches(self) -> None:
        readme = "<table>\n" + self.ROW.format(
            skill="demo-skill", link="download/v2026.01.01/demo-skill-1.0.0.zip") + "\n</table>\n"
        self.assertEqual(run_main(readme, ["demo-skill-1.0.0.zip"]), 0)

    def test_missing_row_fails(self) -> None:
        readme = "<table>\n</table>\n"
        self.assertEqual(run_main(readme, ["demo-skill-1.0.0.zip"]), 1)

    def test_renamed_asset_fallback_on_successor_row(self) -> None:
        """旧名资产包挂在更名后承接技能的表行下时，全文降级检索应豁免。"""
        readme = "<table>\n" + self.ROW.format(
            skill="local-asr", link="download/v2026.01.01/funasr-transcribe-1.9.4.zip") + "\n</table>\n"
        self.assertEqual(run_main(readme, ["funasr-transcribe-1.9.4.zip"]), 0)

    def test_renamed_asset_without_any_link_fails(self) -> None:
        readme = "<table>\n</table>\n"
        self.assertEqual(run_main(readme, ["funasr-transcribe-1.9.4.zip"]), 1)


if __name__ == "__main__":
    unittest.main()
