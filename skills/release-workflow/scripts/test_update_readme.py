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
        root_count, _ = MODULE.rewrite_readme(
            self.root_readme, "cat-xierluo/legal-skills", self.urls
        )
        suite_count, _ = MODULE.rewrite_readme(
            self.suite_readme, "cat-xierluo/legal-skills", self.urls
        )
        self.assertEqual(root_count, 1)
        self.assertEqual(suite_count, 2)
        self.assertIn("alpha-skill-1.2.3.zip", self.root_readme.read_text())
        suite_text = self.suite_readme.read_text()
        self.assertIn("suite-demo-suite-0.2.0.zip", suite_text)
        self.assertIn("https://github.com/example/other/", suite_text)

    def test_is_idempotent(self) -> None:
        MODULE.rewrite_readme(self.root_readme, "cat-xierluo/legal-skills", self.urls)
        count, _ = MODULE.rewrite_readme(
            self.root_readme, "cat-xierluo/legal-skills", self.urls
        )
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
