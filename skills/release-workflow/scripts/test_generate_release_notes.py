#!/usr/bin/env python3
"""Regression tests for monorepo release-note generation."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("generate-release-notes.py")
REPO_ROOT = Path(__file__).resolve().parents[3]


class GenerateReleaseNotesTest(unittest.TestCase):
    def test_status_goes_to_stderr_and_body_file_starts_cleanly(self) -> None:
        """stdout must stay empty; Actions redirects it to the body file."""
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "release-notes.md"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "cat-xierluo/legal-skills",
                    "v2099.01.02",
                    "legal-skills",
                    "5",
                    str(REPO_ROOT / "README.md"),
                    str(output),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("release notes 已生成", result.stderr)
            body = output.read_text(encoding="utf-8")
            self.assertTrue(body.startswith("## Legal Skills 本次发布"), body[:120])


if __name__ == "__main__":
    unittest.main()
