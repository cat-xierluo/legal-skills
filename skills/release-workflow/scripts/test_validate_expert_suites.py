#!/usr/bin/env python3
"""Unit tests for the manifest-free expert-suite validator."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("validate-expert-suites.py")
SPEC = importlib.util.spec_from_file_location("validate_expert_suites", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ExpertSuiteValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        skill = self.root / "skills" / "alpha-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: alpha-skill\nlicense: MIT\n---\n\n# Alpha\n",
            encoding="utf-8",
        )
        (skill / "CHANGELOG.md").write_text(
            "# 变更日志\n\n## [1.2.3] - 2026-09-13\n",
            encoding="utf-8",
        )
        (skill / "LICENSE.txt").write_text("MIT License\n", encoding="utf-8")

        self.suite = self.root / "expert-suites" / "demo-suite"
        members = self.suite / "skills"
        members.mkdir(parents=True)
        (self.suite / "CHANGELOG.md").write_text(
            "# 变更日志\n\n## [0.1.0] - 2026-09-13\n",
            encoding="utf-8",
        )
        (self.suite / "LICENSE.txt").write_text("MIT License\n", encoding="utf-8")
        (self.suite / "README.md").write_text(
            "# Demo\n\n"
            "> [下载完整专家套件](https://github.com/cat-xierluo/legal-skills/"
            "releases/latest/download/suite-demo-suite-0.1.0.zip)\n\n"
            "## 包含的 Skills\n\n"
            "| Skill | 在本套件中的作用 | 单独下载 |\n"
            "| :--- | :--- | :--- |\n"
            "| [alpha-skill](../../skills/alpha-skill/) | 示例 | "
            "[下载](https://github.com/cat-xierluo/legal-skills/releases/latest/"
            "download/alpha-skill-1.2.3.zip) |\n\n"
            "## 安装方法\n",
            encoding="utf-8",
        )
        (members / "alpha-skill").symlink_to("../../../skills/alpha-skill")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def validate(self) -> list[object]:
        return MODULE.validate_repository(self.root, check_git=False)

    def test_valid_suite(self) -> None:
        summaries = self.validate()
        self.assertEqual(summaries[0].members, ("alpha-skill",))

    def test_rejects_broken_or_wrong_link(self) -> None:
        link = self.suite / "skills" / "alpha-skill"
        link.unlink()
        link.symlink_to("../../../skills/missing-skill")
        with self.assertRaisesRegex(MODULE.ValidationError, "应指向"):
            self.validate()

    def test_rejects_absolute_link(self) -> None:
        link = self.suite / "skills" / "alpha-skill"
        link.unlink()
        link.symlink_to((self.root / "skills" / "alpha-skill").resolve())
        with self.assertRaisesRegex(MODULE.ValidationError, "应指向"):
            self.validate()

    def test_rejects_readme_member_drift(self) -> None:
        readme = self.suite / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8").replace("alpha-skill", "beta-skill"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(MODULE.ValidationError, "README 与符号链接不一致"):
            self.validate()

    def test_rejects_missing_member_license(self) -> None:
        (self.root / "skills" / "alpha-skill" / "LICENSE.txt").unlink()
        with self.assertRaisesRegex(MODULE.ValidationError, "缺少 LICENSE.txt"):
            self.validate()

    def test_rejects_stale_member_download_version(self) -> None:
        readme = self.suite / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8").replace("alpha-skill-1.2.3.zip", "alpha-skill-1.2.2.zip"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(MODULE.ValidationError, "当前版本的单独下载链接"):
            self.validate()

    def test_rejects_asset_name_outside_release_url(self) -> None:
        readme = self.suite / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(
                "releases/latest/download/suite-demo-suite-0.1.0.zip",
                "releases/latest/download/not-the-suite.zip suite-demo-suite-0.1.0.zip",
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(MODULE.ValidationError, "整套下载链接"):
            self.validate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
