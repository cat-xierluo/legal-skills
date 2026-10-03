import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
import test_validate_expert_suites as fixtures
MODULE = fixtures.MODULE

spec = importlib.util.spec_from_file_location("stager", Path(__file__).with_name("stage-suite-readme.py"))
stager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stager)


class SourceStageTests(unittest.TestCase):
    setUp = fixtures.ExpertSuiteValidatorTest.setUp
    tearDown = fixtures.ExpertSuiteValidatorTest.tearDown
    validate = fixtures.ExpertSuiteValidatorTest.validate

    def source(self):
        return MODULE.validate_repository(self.root, check_git=False, mode="source")

    def old_link(self, marker="源码 v1.2.3 待发布"):
        path = self.suite / "README.md"
        text = path.read_text().replace("示例 |", f"示例；{marker} |")
        text = text.replace("alpha-skill-1.2.3.zip", "alpha-skill-1.2.2.zip")
        path.write_text(text)

    def test_old_link_requires_exact_pending_marker(self):
        original = (self.suite / "README.md").read_text()
        for marker in ("", "源码 v1.2.2 待发布", "非源码 v1.2.3 待发布", "源码 v1.2.3 待发布；源码 v1.2.4 待发布"):
            (self.suite / "README.md").write_text(original)
            self.old_link(marker)
            with self.assertRaises(MODULE.ValidationError):
                self.source()
        (self.suite / "README.md").write_text(original)
        self.old_link()
        self.source()
        with self.assertRaises(MODULE.ValidationError):
            self.validate()  # Strict default unchanged.

    def test_source_rejects_wrong_asset_and_malformed_suffix(self):
        self.old_link()
        path = self.suite / "README.md"
        original = path.read_text()
        for replacement in ("wrong-skill-1.2.2.zip", "alpha-skill-1.2.2.zip.bak", "alpha-skill-9.0.0.zip"):
            path.write_text(original.replace("alpha-skill-1.2.2.zip", replacement))
            with self.assertRaises(MODULE.ValidationError):
                self.source()

    def test_prose_asset_url_cannot_hide_wrong_download_href(self):
        path = self.suite / "README.md"
        original = path.read_text()
        for version in ("1.2.3", "1.2.2"):
            text = original.replace("示例 |", f"示例 https://github.com/cat-xierluo/legal-skills/releases/latest/download/alpha-skill-{version}.zip；源码 v1.2.3 待发布 |")
            path.write_text(text.replace("download/alpha-skill-1.2.3.zip)", "download/wrong-skill-1.2.3.zip)"))
            with self.assertRaises(MODULE.ValidationError):
                self.source()
        path.write_text(original.replace("suite-demo-suite-0.1.0.zip)", "wrong-suite-0.1.0.zip)") + "\nhttps://github.com/cat-xierluo/legal-skills/releases/latest/download/suite-demo-suite-0.1.0.zip\n")
        with self.assertRaises(MODULE.ValidationError):
            self.source()

    def test_duplicate_suite_download_and_contradictory_pending_fail(self):
        path = self.suite / "README.md"
        original = path.read_text()
        download = next(line for line in original.splitlines() if line.startswith("> "))
        for extra in (download, "> 整套源码 v0.1.0 待首次发布（尚无公开下载）"):
            path.write_text(original.replace("## 包含的 Skills", extra + "\n\n## 包含的 Skills"))
            with self.assertRaises(MODULE.ValidationError):
                self.source()

    def test_source_binds_only_to_validated_member_section(self):
        path = self.suite / "README.md"
        original = path.read_text()
        row = next(line for line in original.splitlines() if "[alpha-skill]" in line)
        text = original.replace("## 包含的 Skills", row + "\n\n## 包含的 Skills")
        start = text.index("## 包含的 Skills")
        path.write_text(text[:start] + text[start:].replace("download/alpha-skill-1.2.3.zip)", "download/wrong-skill-1.2.3.zip)"))
        with self.assertRaises(MODULE.ValidationError):
            self.source()
        path.write_text(text)
        self.source()  # Valid references outside the section are ignored.

    def test_source_does_not_waive_symlink_boundary(self):
        self.old_link()
        link = self.suite / "skills/alpha-skill"
        link.unlink()
        link.symlink_to("../../../../outside")
        with self.assertRaises(MODULE.ValidationError):
            self.source()

    def test_unpublished_suite_and_older_suite_are_explicit_source_only(self):
        path = self.suite / "README.md"
        original = path.read_text()
        published = "https://github.com/cat-xierluo/legal-skills/releases/latest/download/suite-demo-suite-0.1.0.zip"
        path.write_text(original.replace(f"> [下载完整专家套件]({published})", "> 整套源码 v0.1.0 待首次发布（尚无公开下载）"))
        self.source()
        with self.assertRaises(MODULE.ValidationError):
            self.validate()
        path.write_text(original.replace("suite-demo-suite-0.1.0.zip", "suite-demo-suite-0.0.9.zip") + "\n> 整套源码 v0.1.0 待发布\n")
        with self.assertRaises(MODULE.ValidationError):
            self.source()  # A declaration outside the suite header is not accepted.
        path.write_text(original.replace("suite-demo-suite-0.1.0.zip", "suite-demo-suite-0.0.9.zip").replace("## 包含的 Skills", "> 整套源码 v0.1.0 待发布\n\n## 包含的 Skills"))
        self.source()

    def test_stager_rejects_source_worktree_without_writing(self):
        before = (self.suite / "README.md").read_bytes()
        with self.assertRaisesRegex(ValueError, "Staging"):
            stager.render(self.suite, "v2099.01.02", self.root)
        self.assertEqual(before, (self.suite / "README.md").read_bytes())

    def test_release_staging_rewrites_fixed_tag_and_requires_matching_zip(self):
        self.old_link()
        source = self.suite / "README.md"
        source.write_text(source.read_text().replace("latest/download", "download/v2000.01.01"))
        outside = "| [alpha-skill](../../skills/alpha-skill/) | Other reference | [download](https://github.com/cat-xierluo/legal-skills/releases/download/v2000.01.01/alpha-skill-1.2.2.zip) |"
        source.write_text(source.read_text() + "\n## Other references\n" + outside + "\n")
        before = source.read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            import shutil
            stage = Path(temp) / "demo-suite"
            shutil.copytree(self.suite, stage, symlinks=False)
            assets = Path(temp) / "assets"
            assets.mkdir()
            with self.assertRaisesRegex(ValueError, "Missing current release asset"):
                stager.render(stage, "v2099.01.02", assets)
            member = stage / "skills/alpha-skill"
            with zipfile.ZipFile(assets / "alpha-skill-1.2.3.zip", "w") as archive:
                for name in ("SKILL.md", "CHANGELOG.md", "LICENSE.txt"):
                    archive.write(member / name, f"alpha-skill/{name}")
            stager.render(stage, "v2099.01.02", assets)
            text = (stage / "README.md").read_text()
            self.assertIn("download/v2099.01.02/alpha-skill-1.2.3.zip", text)
            self.assertIn("download/v2099.01.02/suite-demo-suite-0.1.0.zip", text)
            self.assertEqual(outside, text.split("## Other references\n", 1)[1].strip())
            self.assertNotIn("v2000", text.split("## Other references", 1)[0])
            self.assertNotIn("待发布", text)
            self.assertEqual(before, source.read_bytes())
            with zipfile.ZipFile(assets / "alpha-skill-1.2.3.zip", "w") as archive:
                archive.writestr("alpha-skill/CHANGELOG.md", "wrong candidate")
            with self.assertRaisesRegex(ValueError, "does not match"):
                stager.render(stage, "v2099.01.02", assets)


if __name__ == "__main__":
    unittest.main()
