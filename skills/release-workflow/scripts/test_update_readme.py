#!/usr/bin/env python3
"""Offline tests for root and expert-suite README release-link refresh."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import subprocess
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


class SourceAwareRefreshTest(unittest.TestCase):
    """Exercise source-ahead, first release and partial-release consumers."""

    repo = "cat-xierluo/legal-skills"
    base = f"https://github.com/{repo}/releases/download/v2026.10.27/"

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.readme = self.root / "README.md"
        self.skill = self.root / "skills/alpha-skill"
        self.skill.mkdir(parents=True)
        (self.skill / "CHANGELOG.md").write_text("## [1.4.0] - 2026-10-27\n")
        self.old_url = self.base + "alpha-skill-1.2.2.zip"
        self.new_url = self.base + "alpha-skill-1.4.0.zip"
        self.suite = self.root / "expert-suites/demo-suite"
        (self.suite / "skills").mkdir(parents=True)
        (self.suite / "skills/alpha-skill").symlink_to("../../../skills/alpha-skill")
        (self.suite / "CHANGELOG.md").write_text("## [0.2.0] - 2026-10-27\n")
        self.suite_readme = self.suite / "README.md"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def root_row(self, download: str | None = None) -> str:
        if download is None:
            download = f'<a href="{self.old_url}">下载 v1.0.0</a>'
        return (
            '<tr><td><a href="skills/alpha-skill/">alpha-skill</a></td>'
            '<td>工具</td><td>说明</td><td>MIT</td><td>v1.0.0</td>'
            f'<td>{download}</td><td>源码 v1.0.0 待发布；下载为已发布 v1.0.0；配置说明</td></tr>'
        )

    def test_old_zip_never_downgrades_source_version(self) -> None:
        self.readme.write_text(self.root_row())
        MODULE.rewrite_readme(self.readme, self.repo, {"alpha-skill": self.old_url})
        text = self.readme.read_text()
        self.assertIn("<td>v1.4.0</td>", text)
        self.assertIn("已发布 v1.2.2", text)
        self.assertIn("源码 v1.4.0 待发布", text)
        self.assertNotIn("v1.0.0", text)
        self.assertIn("配置说明", text)

    def test_first_release_adds_link_and_clears_pending(self) -> None:
        self.readme.write_text(self.root_row("源码待发布"))
        MODULE.rewrite_readme(self.readme, self.repo, {"alpha-skill": self.new_url})
        text = self.readme.read_text()
        self.assertIn(self.new_url, text)
        self.assertIn("已发布 v1.4.0", text)
        self.assertNotIn("待发布", text)
        self.assertIn("配置说明", text)

    def test_unpublished_skill_never_gets_a_future_zip(self) -> None:
        self.readme.write_text(self.root_row("源码待发布"))
        MODULE.rewrite_readme(self.readme, self.repo, {})
        text = self.readme.read_text()
        self.assertIn("尚无公开 ZIP", text)
        self.assertIn("<td>v1.4.0</td>", text)
        self.assertNotIn(".zip", text)

    def test_partial_release_preserves_other_published_links(self) -> None:
        self.readme.write_text(self.root_row())
        MODULE.rewrite_readme(self.readme, self.repo, {"other": self.base + "other-1.0.0.zip"})
        self.assertIn(self.old_url, self.readme.read_text())
        self.assertIn("<td>v1.4.0</td>", self.readme.read_text())

    def test_older_hotfix_does_not_replace_a_newer_published_download(self) -> None:
        self.readme.write_text(self.root_row())
        MODULE.rewrite_readme(self.readme, self.repo, {
            "alpha-skill": self.base + "alpha-skill-1.2.1.zip"
        })
        self.assertIn(self.old_url, self.readme.read_text())

    def test_unobserved_latest_placeholder_is_not_claimed_as_published(self) -> None:
        future = self.new_url.replace("download/v2026.10.27", "latest/download")
        self.readme.write_text(self.root_row(f'<a href="{future}">待发布</a>'))
        MODULE.rewrite_readme(self.readme, self.repo, {})
        text = self.readme.read_text()
        self.assertIn("尚无公开 ZIP", text)
        self.assertNotIn(future, text)
        self.assertNotIn("已发布 v", text)

    def test_unverified_content_warning_survives_label_refresh(self) -> None:
        self.readme.write_text(self.root_row(f'<a href="{self.old_url}">旧版ZIP（内容版本待核）</a>'))
        MODULE.rewrite_readme(self.readme, self.repo, {})
        self.assertIn("内容版本待核", self.readme.read_text())

    def test_repeated_refresh_is_byte_idempotent(self) -> None:
        self.readme.write_text(self.root_row())
        urls = {"alpha-skill": self.old_url}
        MODULE.rewrite_readme(self.readme, self.repo, urls)
        before = self.readme.read_bytes()
        stats = MODULE.rewrite_readme(self.readme, self.repo, urls)
        self.assertEqual(before, self.readme.read_bytes())
        self.assertEqual(stats["versions"], 0)
        self.assertEqual(stats["links"], 0)

    def test_suite_root_table_preserves_curated_order_and_source_version(self) -> None:
        old = self.base + "suite-demo-suite-0.1.0.zip"
        before = f"| [法律](expert-suites/demo-suite/) | 作用 | 9 | v0.1.0 | [下载]({old}) |\n"
        tail = "| [工具](expert-suites/tools/) | 作用 | 1 | v0.1.0 | 尚无公开 ZIP |\n"
        self.readme.write_text(before + tail)
        MODULE.rewrite_readme(self.readme, self.repo, {})
        text = self.readme.read_text()
        self.assertIn("| 1 | v0.2.0 |", text)
        self.assertLess(text.index("法律"), text.index("工具"))
        self.assertIn(old, text)

    def suite_document(self, header: str) -> str:
        return (
            f"# Demo\n\n{header}\n\n套件用途。\n\n## 包含的 Skills\n\n"
            "| Skill | 作用 | 单独下载 |\n| :--- | :--- | :--- |\n"
            "| [alpha-skill](../../skills/alpha-skill/) | 示例；源码 v1.4.0 待发布 | 尚无公开下载 |\n"
        )

    def test_suite_first_release_fills_header_and_member_download(self) -> None:
        self.suite_readme.write_text(
            self.suite_document("> 整套源码 v0.2.0 待首次发布（尚无公开下载）")
        )
        own_url = self.base + "suite-demo-suite-0.2.0.zip"
        urls = {"suite-demo-suite": own_url, "alpha-skill": self.new_url}
        MODULE.rewrite_readme(self.suite_readme, self.repo, urls)
        text = self.suite_readme.read_text()
        self.assertIn(f"> [已发布 v0.2.0]({own_url})", text)
        self.assertIn(f"[已发布 v1.4.0]({self.new_url})", text)
        self.assertNotIn("待发布", text)
        self.assertNotIn("待首次发布", text)
        before = self.suite_readme.read_bytes()
        MODULE.rewrite_readme(self.suite_readme, self.repo, urls)
        self.assertEqual(before, self.suite_readme.read_bytes())

    def test_suite_partial_hotfix_keeps_older_bundle_pending(self) -> None:
        old = self.base + "suite-demo-suite-0.1.0.zip"
        self.suite_readme.write_text(self.suite_document(f"> [下载]({old})"))
        MODULE.rewrite_readme(self.suite_readme, self.repo, {"alpha-skill": self.new_url})
        text = self.suite_readme.read_text()
        self.assertIn("整套源码 v0.2.0 待发布", text)
        self.assertIn(old, text)
        self.assertNotIn("示例；源码", text)

    def test_suite_header_does_not_rewrite_other_component_links(self) -> None:
        old = self.base + "suite-demo-suite-0.1.0.zip"
        extra = f"> [单独成员]({self.old_url})"
        self.suite_readme.write_text(self.suite_document(f"> [下载]({old})\n{extra}"))
        MODULE.rewrite_readme(self.suite_readme, self.repo, {})
        self.assertIn(extra, self.suite_readme.read_text())

    def test_asset_choice_is_semver_ordered_not_api_ordered(self) -> None:
        assets = [
            {"name": f"alpha-skill-{v}.zip", "browser_download_url": self.base + f"alpha-skill-{v}.zip"}
            for v in ("1.10.0", "1.2.0")
        ]
        a = MODULE.asset_url_map({"assets": assets})
        b = MODULE.asset_url_map({"assets": list(reversed(assets))})
        self.assertEqual(a, b)
        self.assertTrue(a["alpha-skill"].endswith("-1.10.0.zip"))

    def test_real_cli_refreshes_root_and_suite_without_network(self) -> None:
        import json
        self.readme.write_text(self.root_row("源码待发布"))
        self.suite_readme.write_text(
            self.suite_document("> 整套源码 v0.2.0 待首次发布（尚无公开下载）")
        )
        fixture = self.root / "release.json"
        fixture.write_text(json.dumps({"assets": [
            {"name": "alpha-skill-1.4.0.zip", "browser_download_url": self.new_url},
            {"name": "suite-demo-suite-0.2.0.zip",
             "browser_download_url": self.base + "suite-demo-suite-0.2.0.zip"},
        ]}))
        command = [sys.executable, str(MODULE_PATH), "--assets-json", str(fixture), self.repo]
        first = subprocess.run(command, cwd=self.root, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        before = (self.readme.read_bytes(), self.suite_readme.read_bytes())
        second = subprocess.run(command, cwd=self.root, capture_output=True, text=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(before, (self.readme.read_bytes(), self.suite_readme.read_bytes()))
        self.assertIn(self.new_url, self.readme.read_text())
        self.assertNotIn("待发布", self.suite_readme.read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
