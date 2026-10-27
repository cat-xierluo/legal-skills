from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("builder", SKILL_ROOT / "scripts/build_release.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class BuildReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE).decode().strip()

    def fixture(self, layout="self-evolve"):
        skill = self.repo / layout
        (skill / "config").mkdir(parents=True)
        (skill / "scripts").mkdir()
        files = [".gitignore", "SKILL.md", "scripts/main.py", "config/release-files.json"]
        (skill / ".gitignore").write_text("state/\n")
        (skill / "SKILL.md").write_text("---\nname: self-evolve\n---\nbody\n")
        (skill / "scripts/main.py").write_text("print('hello')\n")
        (skill / "config/release-files.json").write_text(json.dumps({"files": files}))
        for name in builder.EXCLUDED:
            target = skill / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("private\n")
        return skill

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture", "--allow-empty")
        return self.git("rev-parse", "HEAD")

    def test_layout_exclusions_reproducibility_and_homepage(self):
        for layout in ("self-evolve", "skills/self-evolve"):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as td:
                nested = BuildReleaseTests(methodName="runTest")
                nested.setUp()
                try:
                    nested.fixture(layout)
                    oid = nested.commit()
                    a = builder.build(nested.repo, oid, Path(td) / "one", homepage="https://example.org")
                    b = builder.build(nested.repo, oid, Path(td) / "two", homepage="https://example.org")
                    pa, pb = Path(a["bundle"]), Path(b["bundle"])
                    manifest = json.loads((pa / "release-manifest.json").read_text())
                    self.assertEqual((pa / "release-manifest.json").read_bytes(), (pb / "release-manifest.json").read_bytes())
                    self.assertEqual(manifest["source_oid"], oid)
                    self.assertEqual(manifest["source_skill_path"], layout)
                    for name in builder.EXCLUDED:
                        self.assertIn(name, manifest["excluded"])
                        self.assertFalse((pa / name).exists())
                        self.assertNotIn(name, [row["path"] for row in manifest["files"]])
                    self.assertIn('homepage: "https://example.org"\n---\nbody', (pa / "SKILL.md").read_text())
                    with self.assertRaises(FileExistsError):
                        builder.build(nested.repo, oid, Path(td) / "one")
                finally:
                    nested.doCleanups()

    def test_unknown_symlink_escape_missing_and_homepage_injection(self):
        skill = self.fixture()
        (skill / "unknown.py").write_text("unknown")
        oid = self.commit()
        with self.assertRaisesRegex(ValueError, "unreviewed"):
            builder.build(self.repo, oid, self.root / "out")
        (skill / "unknown.py").unlink()
        (skill / "link").symlink_to("SKILL.md")
        oid = self.commit()
        with self.assertRaisesRegex(ValueError, "symlink"):
            builder.build(self.repo, oid, self.root / "out")
        (skill / "link").unlink()
        allow = skill / "config/release-files.json"
        for value in ("../escape", "missing.py", "config/scheduled_tasks.yaml"):
            original = json.loads(allow.read_text())
            original["files"].append(value)
            allow.write_text(json.dumps(original))
            oid = self.commit()
            with self.assertRaises(ValueError):
                builder.build(self.repo, oid, self.root / "out")
            original["files"].pop()
            allow.write_text(json.dumps(original))
        for value in ("config/workmode.local.json",):
            original = json.loads(allow.read_text())
            original["files"].append(value)
            allow.write_text(json.dumps(original))
            oid = self.commit()
            with self.assertRaises(ValueError):
                builder.build(self.repo, oid, self.root / "out")
            original["files"].pop()
            allow.write_text(json.dumps(original))
        oid = self.commit()
        with self.assertRaisesRegex(ValueError, "homepage"):
            builder.build(self.repo, oid, self.root / "out", homepage="x\ninjected: true")

    def test_homepage_replaces_frontmatter_only(self):
        original = b"---\nname: example\nhomepage: old\n---\nhomepage: body\n"
        updated = builder._homepage(original, "https://example.org")
        self.assertEqual(updated, b'---\nname: example\nhomepage: "https://example.org"\n---\nhomepage: body\n')
        with self.assertRaisesRegex(ValueError, "frontmatter"):
            builder._homepage(b"body\n", "https://example.org")

    def test_invalid_source_path_and_complete_distribution(self):
        skill = self.fixture()
        allow = skill / "config/release-files.json"
        extra = skill / "scripts/compatibility.py"
        extra.write_text("print('compatibility remains available')\n")
        with self.assertRaisesRegex(ValueError, "unreviewed"):
            builder.build(self.repo, self.commit(), self.root / "unknown")
        payload = json.loads(allow.read_text())
        payload["files"].append("scripts/compatibility.py")
        allow.write_text(json.dumps(payload))
        built = builder.build(self.repo, self.commit(), self.root / "complete")
        self.assertEqual((Path(built["bundle"]) / "scripts/compatibility.py").read_bytes(),
                         extra.read_bytes())
        (skill / "bad\\name").write_text("invalid")
        with self.assertRaisesRegex(ValueError, "invalid_source_path"):
            builder.build(self.repo, self.commit(), self.root / "invalid")

    def test_missing_allowlist_and_ambiguous_layout(self):
        a = self.fixture()
        self.fixture("skills/self-evolve")
        oid = self.commit()
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            builder.build(self.repo, oid, self.root / "out")
        builder.build(self.repo, oid, self.root / "out", skill_path="self-evolve")
        (a / "config/release-files.json").unlink()
        oid = self.commit()
        with self.assertRaisesRegex(ValueError, "allowlist_missing"):
            builder.build(self.repo, oid, self.root / "other", skill_path="self-evolve")


if __name__ == "__main__":
    unittest.main()
