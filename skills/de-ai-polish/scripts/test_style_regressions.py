#!/usr/bin/env python3
"""de-ai-polish 修复伪影回归。"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "style_regression_gate.py"
ASSETS = ROOT / "assets" / "stability"
class StyleRegressionTests(unittest.TestCase):
    def run_case(self, fixture: str, expected: int) -> dict[str, object]:
        result = subprocess.run(
            ["python3", str(GATE), str(ASSETS / fixture)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, msg=result.stderr or result.stdout)
        return json.loads(result.stdout)

    def test_disguised_enumeration_is_blocked(self) -> None:
        output = self.run_case("style-hidden-enumeration.md", 3)
        self.assertIn("NO-DISGUISED-ENUMERATION", output["failed_constraint_ids"])

    def test_functional_enumeration_is_preserved(self) -> None:
        output = self.run_case("style-functional-enumeration.md", 0)
        self.assertIn("NO-DISGUISED-ENUMERATION", output["passed_constraint_ids"])

    def test_editorial_process_leakage_is_blocked(self) -> None:
        output = self.run_case("style-editorial-process-leakage.md", 3)
        self.assertIn("NO-EDITORIAL-PROCESS-LEAKAGE", output["failed_constraint_ids"])

    def test_framework_starter_is_blocked(self) -> None:
        output = self.run_case("style-framework-starter.md", 3)
        self.assertIn("NO-FRAMEWORK-STARTER", output["failed_constraint_ids"])

    def test_compressed_aphorism_evasion_is_blocked(self) -> None:
        output = self.run_case("style-compressed-aphorism-evasion.md", 3)
        self.assertIn("NO-COMPRESSED-APHORISM-EVASION", output["failed_constraint_ids"])

    def test_abstract_entry_metaphor_is_blocked(self) -> None:
        output = self.run_case("style-abstract-entry-metaphor.md", 3)
        self.assertIn("NO-ABSTRACT-ENTRY-METAPHOR", output["failed_constraint_ids"])

    def test_repeated_spatial_access_metaphor_is_blocked(self) -> None:
        output = self.run_case("style-spatial-access-repeated.md", 3)
        self.assertIn("NO-REPEATED-SPATIAL-ACCESS-METAPHOR", output["failed_constraint_ids"])

if __name__ == "__main__":
    unittest.main()
