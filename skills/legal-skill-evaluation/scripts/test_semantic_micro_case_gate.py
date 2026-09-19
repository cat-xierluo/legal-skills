#!/usr/bin/env python3
"""Regression tests for semantic_micro_case_gate.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "semantic_micro_case_gate.py"
MICRO = ROOT / "evals" / "contract-calibration-260730" / "micro-runs"


class SemanticMicroCaseGateTests(unittest.TestCase):
    def run_gate(self, input_name: str, output_name: str) -> tuple[int, dict]:
        completed = subprocess.run(
            [
                sys.executable,
                str(GATE),
                "--input",
                str(MICRO / input_name),
                "--output",
                str(MICRO / output_name),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertTrue(completed.stdout.strip(), completed.stderr)
        return completed.returncode, json.loads(completed.stdout)

    def run_mutated(self, input_name: str, output_text: str) -> tuple[int, dict]:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "output.md"
            output_path.write_text(output_text, encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(GATE),
                    "--input",
                    str(MICRO / input_name),
                    "--output",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        return completed.returncode, json.loads(completed.stdout)

    def test_objective_missing_fixture_passes(self) -> None:
        code, payload = self.run_gate(
            "objective-missing-input.json", "objective-missing-output.md"
        )
        self.assertEqual(0, code)
        self.assertEqual("pass", payload["status"])

    def test_attachment_missing_fixture_passes(self) -> None:
        code, payload = self.run_gate(
            "attachment-missing-input.json", "attachment-missing-output.md"
        )
        self.assertEqual(0, code)
        self.assertEqual("pass", payload["status"])

    def test_objective_missing_without_stop_fails(self) -> None:
        code, payload = self.run_mutated(
            "objective-missing-input.json",
            "请确认目标：签约前把关、谈判修订或仅识别文本问题。我不自行选择。",
        )
        self.assertEqual(3, code)
        self.assertEqual(
            ["CAP-MICRO-OBJECTIVE-MISSING-STOP"], payload["failed_constraint_ids"]
        )

    def test_objective_missing_with_formal_verdict_fails(self) -> None:
        code, payload = self.run_mutated(
            "objective-missing-input.json",
            "请确认目标：签约前把关或谈判修订。在目标确认前暂停实质审查，不自行选择。\n结论：可签。",
        )
        self.assertEqual(3, code)
        self.assertEqual("fail", payload["status"])

    def test_attachment_missing_without_all_limitations_fails(self) -> None:
        code, payload = self.run_mutated(
            "attachment-missing-input.json",
            "附件未提供，无法核对服务范围。请在签署前必须补齐附件。",
        )
        self.assertEqual(3, code)
        self.assertEqual(
            ["CAP-MICRO-ATTACHMENT-MISSING-LIMIT"],
            payload["failed_constraint_ids"],
        )

    def test_attachment_missing_with_signing_recommendation_fails(self) -> None:
        code, payload = self.run_mutated(
            "attachment-missing-input.json",
            "附件未提供，影响服务范围、验收和费用判断；签署前必须补齐，但建议直接签署。",
        )
        self.assertEqual(3, code)
        self.assertEqual("fail", payload["status"])

    def test_clause_boundary_fixtures_pass(self) -> None:
        fixtures = [
            ("service-scope-input.json", "service-scope-output.md", "CAP-MICRO-SERVICE-SCOPE-BOUNDARY"),
            ("acceptance-payment-input.json", "acceptance-payment-output.md", "CAP-MICRO-ACCEPTANCE-PAYMENT-LINK"),
            ("change-fee-input.json", "change-fee-output.md", "CAP-MICRO-CHANGE-FEE-AUTHORIZATION"),
            ("penalty-stacking-input.json", "penalty-stacking-output.md", "CAP-MICRO-PENALTY-STACKING-BOUNDARY"),
            ("design-ip-use-input.json", "design-ip-use-output.md", "CAP-MICRO-DESIGN-IP-PROJECT-USE"),
            ("notice-input.json", "notice-output.md", "CAP-MICRO-NOTICE-DELIVERY"),
            ("jurisdiction-input.json", "jurisdiction-output.md", "CAP-MICRO-JURISDICTION-CONNECTION"),
            ("patent-subject-input.json", "patent-subject-output.md", "CAP-MICRO-PATENT-SUBJECT-BLOCK"),
            ("patent-scope-input.json", "patent-scope-output.md", "CAP-MICRO-PATENT-SCOPE-SUBLICENSE"),
            ("patent-fee-input.json", "patent-fee-output.md", "CAP-MICRO-PATENT-FEE-AUDIT"),
            ("patent-invalidity-input.json", "patent-invalidity-output.md", "CAP-MICRO-PATENT-INVALIDITY-ALLOCATION"),
        ]
        for input_name, output_name, assertion_id in fixtures:
            code, payload = self.run_gate(input_name, output_name)
            self.assertEqual(0, code, input_name)
            self.assertEqual("pass", payload["status"], input_name)
            self.assertEqual([assertion_id], payload["passed_constraint_ids"], input_name)

    def test_clause_boundary_with_formal_verdict_fails(self) -> None:
        code, payload = self.run_mutated(
            "service-scope-input.json",
            "服务范围过粗，在以下信息补齐前我将暂停实质审查：服务事项清单、频次、扩项机制。\n结论：可签。",
        )
        self.assertEqual(3, code)
        self.assertEqual("fail", payload["status"])
        self.assertEqual(
            ["CAP-MICRO-SERVICE-SCOPE-BOUNDARY"], payload["failed_constraint_ids"]
        )

    def test_clause_boundary_without_stop_fails(self) -> None:
        code, payload = self.run_mutated(
            "service-scope-input.json",
            "服务范围过粗，建议直接签署并补充服务事项清单。",
        )
        self.assertEqual(3, code)
        self.assertEqual("fail", payload["status"])
        self.assertEqual(
            ["CAP-MICRO-SERVICE-SCOPE-BOUNDARY"], payload["failed_constraint_ids"]
        )

    def test_unknown_case_is_scope_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            output_path = root / "output.md"
            input_path.write_text('{"case_id":"UNKNOWN"}\n', encoding="utf-8")
            output_path.write_text("output\n", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(GATE),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(2, completed.returncode)
        self.assertEqual("error", json.loads(completed.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
