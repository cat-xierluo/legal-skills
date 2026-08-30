#!/usr/bin/env python3
"""候选件验证失败时，不得覆盖用户已有目标文件。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent


class FailClosedPublishTests(unittest.TestCase):
    def test_residual_failure_preserves_existing_output(self):
        sentinel = b"existing-user-output\n"
        with tempfile.TemporaryDirectory(prefix="ecg-fail-closed-") as directory:
            output = Path(directory) / "existing.docx"
            output.write_bytes(sentinel)
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SKILL_DIR / "scripts/fill_template.py"),
                    "--case-type",
                    "09-private-lending",
                    "--elements",
                    str(SKILL_DIR / "tests/fixtures/09-private-lending-sample.json"),
                    "--output",
                    str(output),
                    "--verify-residual",
                    "民事起诉状",
                    "--layout-check",
                    "docx",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(output.read_bytes(), sentinel)
            self.assertIn("旧串仍存在", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
