#!/usr/bin/env python3
"""Offline tests for root and expert-suite README release-link refresh."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("update-readme.py")
SPEC = importlib.util.spec_from_file_location("update_readme", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class UpdateReadmeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.root_readme = self.root / "README.md"
        self.suite_readme = self.root / "expert-suites" / "demo-suite" / "README.md"
        self.suite_readme.parent.mkdir(parents=True)
        self.root_readme.write_text(
            "[下载](https://github.com/cat-xierluo/legal-skills/releases/"
            "download/v2026.01.01/alpha-skill-1.2.2.zip)\n",
            encoding="utf-8",
        )
        self.suite_readme.write_text(
            "[整套](https://github.com/cat-xierluo/legal-skills/releases/latest/"
            "download/suite-demo-suite-0.1.0.zip)\n"
            "[成员](https://github.com/cat-xierluo/legal-skills/releases/latest/"
            "download/alpha-skill-1.2.2.zip)\n"
            "[外部](https://github.com/example/other/releases/latest/"
            "download/alpha-skill-9.9.9.zip)\n",
            encoding="utf-8",
        )
        self.urls = MODULE.asset_url_map(
            {
                "assets": [
                    {
                        "name": "alpha-skill-1.2.3.zip",
                        "browser_download_url": "https://github.com/cat-xierluo/legal-skills/"
                        "releases/download/v2026.09.13/alpha-skill-1.2.3.zip",
                    },
                    {
                        "name": "suite-demo-suite-0.2.0.zip",
                        "browser_download_url": "https://github.com/cat-xierluo/legal-skills/"
                        "releases/download/v2026.09.13/suite-demo-suite-0.2.0.zip",
                    },
                ]
            }
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_discovers_root_and_suite_readmes(self) -> None:
        self.assertEqual(
            MODULE.discover_readmes(self.root),
            [self.root_readme, self.suite_readme],
        )

    def test_updates_skill_and_suite_links_but_not_other_repositories(self) -> None:
        root_stats = MODULE.rewrite_readme(
            self.root_readme, "cat-xierluo/legal-skills", self.urls
        )
        suite_stats = MODULE.rewrite_readme(
            self.suite_readme, "cat-xierluo/legal-skills", self.urls
        )
        self.assertEqual(root_stats["links"], 1)
        self.assertEqual(suite_stats["links"], 2)
        self.assertIn("alpha-skill-1.2.3.zip", self.root_readme.read_text())
        suite_text = self.suite_readme.read_text()
        self.assertIn("suite-demo-suite-0.2.0.zip", suite_text)
        self.assertIn("https://github.com/example/other/", suite_text)

    def test_is_idempotent(self) -> None:
        MODULE.rewrite_readme(self.root_readme, "cat-xierluo/legal-skills", self.urls)
        stats = MODULE.rewrite_readme(
            self.root_readme, "cat-xierluo/legal-skills", self.urls
        )
        self.assertEqual(stats["links"], 0)
        self.assertEqual(stats["versions"], 0)


class HtmlRowRewriteTest(unittest.TestCase):
    """根 README HTML 表行:按行内技能名重映射 + 版本列对齐。"""

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.readme = Path(self.tempdir.name) / "README.md"
        self.urls = {
            "alpha-skill": "https://github.com/cat-xierluo/legal-skills/"
            "releases/download/v2026.09.13/alpha-skill-1.2.3.zip",
            "renamed-skill": "https://github.com/cat-xierluo/legal-skills/"
            "releases/download/v2026.09.13/renamed-skill-2.0.0.zip",
        }
        self.repo = "cat-xierluo/legal-skills"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write(self, row_html: str) -> None:
        self.readme.write_text(
            "<table>\n<tr>\n" + row_html + "\n</tr>\n</table>\n", encoding="utf-8"
        )

    def test_version_cell_realigned_with_link(self) -> None:
        self._write(
            '<td><a href="skills/alpha-skill/"><strong>alpha-skill</strong></a></td>\n'
            '<td>工具</td>\n'
            '<td style="text-align:center">v1.0.0</td>\n'
            '<td style="text-align:center"><a href="https://github.com/cat-xierluo/'
            'legal-skills/releases/download/v2026.01.01/alpha-skill-1.0.0.zip">下载</a></td>'
        )
        stats = MODULE.rewrite_readme(self.readme, self.repo, self.urls)
        text = self.readme.read_text()
        self.assertEqual(stats["links"], 1)
        self.assertEqual(stats["versions"], 1)
        self.assertIn("alpha-skill-1.2.3.zip", text)
        self.assertIn(">v1.2.3</td>", text)

    def test_version_cell_realigned_even_when_link_already_current(self) -> None:
        """链接已最新但版本列滞后(存量状态)时,重跑仍应只修版本列。"""
        self._write(
            '<td><a href="skills/alpha-skill/"><strong>alpha-skill</strong></a></td>\n'
            '<td>工具</td>\n'
            '<td style="text-align:center">v1.0.0</td>\n'
            '<td style="text-align:center"><a href="https://github.com/cat-xierluo/'
            'legal-skills/releases/download/v2026.09.13/alpha-skill-1.2.3.zip">下载</a></td>'
        )
        stats = MODULE.rewrite_readme(self.readme, self.repo, self.urls)
        text = self.readme.read_text()
        self.assertEqual(stats["links"], 0)
        self.assertEqual(stats["versions"], 1)
        self.assertIn(">v1.2.3</td>", text)

    def test_renamed_dead_link_rewritten_by_row_skill(self) -> None:
        """改名残留死链:链接 slug 是旧名,按行内技能名重映射到正确资产。"""
        self._write(
            '<td><a href="skills/renamed-skill/"><strong>renamed-skill</strong></a></td>\n'
            '<td>工具</td>\n'
            '<td style="text-align:center">v1.4.1</td>\n'
            '<td style="text-align:center"><a href="https://github.com/cat-xierluo/'
            'legal-skills/releases/download/v2026.08.06/old-name-1.6.1.zip">下载</a></td>'
        )
        stats = MODULE.rewrite_readme(self.readme, self.repo, self.urls)
        text = self.readme.read_text()
        self.assertEqual(stats["links"], 1)
        self.assertEqual(stats["versions"], 1)
        self.assertIn("renamed-skill-2.0.0.zip", text)
        self.assertNotIn("old-name-1.6.1.zip", text)
        self.assertIn(">v2.0.0</td>", text)

    def test_independent_repo_row_untouched(self) -> None:
        """独立仓库下载行(链接域名非本仓库)整行不动,版本列也不动。"""
        self._write(
            '<td><a href="skills/alpha-skill/"><strong>alpha-skill</strong></a></td>\n'
            '<td>工具</td>\n'
            '<td style="text-align:center">v9.9.9</td>\n'
            '<td style="text-align:center"><a href="https://github.com/'
            'cat-xierluo/alpha-skill.skill/releases/download/v1.7.0/'
            'alpha-skill-1.7.0.zip">下载</a></td>\n'
            '<td><a href="https://github.com/cat-xierluo/alpha-skill.skill">独立仓库</a></td>'
        )
        stats = MODULE.rewrite_readme(self.readme, self.repo, self.urls)
        text = self.readme.read_text()
        self.assertEqual(stats["links"], 0)
        self.assertEqual(stats["versions"], 0)
        self.assertIn("alpha-skill.skill/releases", text)
        self.assertIn(">v9.9.9</td>", text)

    def test_range_version_cell_replaced_whole(self) -> None:
        """v0.4.4→v0.4.6 区间写法的版本列整体对齐为 zip 版本。"""
        self._write(
            '<td><a href="skills/alpha-skill/"><strong>alpha-skill</strong></a></td>\n'
            '<td>工具</td>\n'
            '<td style="text-align:center">v1.0.0→v1.0.2</td>\n'
            '<td style="text-align:center"><a href="https://github.com/cat-xierluo/'
            'legal-skills/releases/latest/download/alpha-skill-1.0.2.zip">下载</a></td>'
        )
        MODULE.rewrite_readme(self.readme, self.repo, self.urls)
        text = self.readme.read_text()
        self.assertIn(">v1.2.3</td>", text)
        self.assertNotIn("→", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
