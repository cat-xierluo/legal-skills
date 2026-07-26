#!/usr/bin/env python3
"""instantiate_template.py 的模板锁定回归。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("instantiate_template.py")
SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = SKILL_ROOT / "templates" / "litigation" / "complex-case-split.drawio"
VALUES = SKILL_ROOT / "assets" / "stability" / "complex-case-values.json"


class InstantiateTemplateTest(unittest.TestCase):
    def test_known_values_render_without_changing_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.drawio"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(TEMPLATE), str(VALUES), str(output), "--json"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            report = json.loads(result.stdout)
            self.assertTrue(report["validation"]["passed"])
            rendered = output.read_text(encoding="utf-8")
            self.assertNotIn("{{", rendered)
            self.assertIn("证券虚假陈述案件核心事实总览", rendered)
            self.assertIn('x="60" y="120" width="280" height="260"', rendered)

    def test_missing_value_fails_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = Path(directory) / "values.json"
            output = Path(directory) / "result.drawio"
            values.write_text('{"title": "缺字段"}\n', encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(TEMPLATE), str(values), str(output), "--json"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
            self.assertIn("缺少占位符值", result.stdout)


if __name__ == "__main__":
    unittest.main()
