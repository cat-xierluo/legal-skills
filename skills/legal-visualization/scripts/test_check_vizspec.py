#!/usr/bin/env python3
"""check_vizspec.py 的声明校验回归。"""

from __future__ import annotations

import sys
import unittest

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from check_vizspec import validate  # noqa: E402

try:
    import yaml  # type: ignore  # noqa: F401

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@unittest.skipUnless(HAS_YAML, "PyYAML 未安装，跳过 VizSpec 校验回归")
class CheckVizspecTest(unittest.TestCase):
    def test_valid_spec_has_no_errors(self) -> None:
        data = yaml.safe_load(
            """
visual:
  theme: client_report
  icons: false
entities:
  - id: a
    visual_role: plaintiff
  - id: b
    visual_role: company
"""
        )
        findings = validate(data)
        self.assertFalse([f for f in findings if f["severity"] == "error"], findings)

    def test_illegal_role_is_error(self) -> None:
        data = yaml.safe_load("entities:\n  - id: a\n    visual_role: superhero\n")
        findings = validate(data)
        self.assertTrue(
            any(f["severity"] == "error" and "superhero" in f["message"] for f in findings),
            findings,
        )

    def test_reserved_theme_warns_without_error(self) -> None:
        data = yaml.safe_load(
            "visual:\n  theme: court_submit\nentities:\n  - id: a\n    visual_role: court\n"
        )
        findings = validate(data)
        self.assertFalse([f for f in findings if f["severity"] == "error"], findings)
        self.assertTrue(
            any(f["severity"] == "warning" and "court_submit" in f["message"] for f in findings),
            findings,
        )


if __name__ == "__main__":
    unittest.main()
