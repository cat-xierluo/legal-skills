#!/usr/bin/env python3
"""Regression tests for capability_suite_gate.py."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "capability_suite_gate.py"
SUITE = ROOT / "evals" / "contract-calibration-260730" / "capability-suite.json"
FALSE_VERIFIED = ROOT / "assets" / "capability-suite-false-verified.json"


def _discover_candidate_root() -> Path:
    """定位被测候选 skill（contract-copilot），支持两种解析：
    1. 环境变量 LSE_CANDIDATE_ROOT 显式指定（隔离工作树/CI 用）；
    2. 否则从本 skill 根向上查找包含 legal-skills/skills/contract-copilot 的集合根。
    解耦「candidate 必须与被测 skill 同处于某个固定 monorepo 布局」的测试耦合（F-4 修复）。"""
    import os

    env = os.environ.get("LSE_CANDIDATE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    here = ROOT
    for parent in [here, *here.parents]:
        candidate = parent / "legal-skills" / "skills" / "contract-copilot"
        if candidate.is_dir():
            return candidate
    return ROOT.parents[1] / "legal-skills" / "skills" / "contract-copilot"


CANDIDATE = _discover_candidate_root()


class CapabilitySuiteGateTests(unittest.TestCase):
    def run_gate(
        self, payload: dict | None = None, *, candidate_root: Path | None = None
    ) -> tuple[int, dict]:
        if payload is None:
            input_path = SUITE
            temporary = None
        else:
            temporary = tempfile.TemporaryDirectory()
            input_path = Path(temporary.name) / "suite.json"
            input_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        command = [sys.executable, str(GATE), "--input", str(input_path)]
        if candidate_root is not None:
            command.extend(["--candidate-root", str(candidate_root)])
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if temporary is not None:
            temporary.cleanup()
        self.assertTrue(result.stdout.strip(), result.stderr)
        return result.returncode, json.loads(result.stdout)

    @staticmethod
    def suite() -> dict:
        return json.loads(SUITE.read_text(encoding="utf-8"))

    def test_current_suite_is_internally_consistent(self) -> None:
        code, result = self.run_gate()
        self.assertEqual(0, code)
        self.assertEqual("pass", result["status"])
        self.assertEqual(20, result["measurements"]["case_count"])
        self.assertEqual("regression-detected", result["observables"]["suite_status"])

    def test_current_suite_matches_candidate_snapshot(self) -> None:
        code, result = self.run_gate(candidate_root=CANDIDATE)
        self.assertEqual(0, code)
        self.assertEqual(
            result["observables"]["candidate_sha256"],
            result["observables"]["recomputed_candidate_sha256"],
        )

    def test_suite_below_minimum_case_count_fails(self) -> None:
        payload = self.suite()
        payload["cases"] = payload["cases"][:19]
        code, result = self.run_gate(payload)
        self.assertEqual(3, code)
        self.assertIn("SUITE-008", {item["code"] for item in result["errors"]})

    def test_missing_required_capability_fails(self) -> None:
        payload = self.suite()
        for case in payload["cases"]:
            case["capabilities"] = [
                item for item in case["capabilities"] if item != "human-review"
            ]
        code, result = self.run_gate(payload)
        self.assertEqual(3, code)
        self.assertIn("SUITE-039", {item["code"] for item in result["errors"]})

    def test_current_case_with_stale_candidate_hash_fails(self) -> None:
        payload = self.suite()
        payload["cases"][0]["candidate_sha256"] = "0" * 64
        code, result = self.run_gate(payload)
        self.assertEqual(3, code)
        self.assertIn("SUITE-019", {item["code"] for item in result["errors"]})

    def test_executed_case_without_output_hash_fails(self) -> None:
        payload = self.suite()
        payload["cases"][0].pop("output_sha256")
        code, result = self.run_gate(payload)
        self.assertEqual(3, code)
        self.assertIn("SUITE-033", {item["code"] for item in result["errors"]})

    def test_not_run_case_cannot_claim_pass(self) -> None:
        payload = self.suite()
        # T-401 现已全 executed，需注入一个 not-run case 来验证 SUITE-029 逻辑。
        prepared = {
            "id": "CONTRACT-MICRO-NOT-RUN-INJECTED",
            "title": "注入的未执行案例",
            "case_type": "micro",
            "tier": "dynamic-micro",
            "source_kind": "reference-derived",
            "capabilities": ["intake"],
            "candidate_binding": "current-candidate",
            "execution_status": "not-run",
            "assertions": [
                {"id": "INJECTED-ASSERT", "expected": "占位", "observed": "pass", "evidence": "unsupported"}
            ],
            "gate_verdict": "pass",
        }
        payload["cases"].append(prepared)
        code, result = self.run_gate(payload)
        self.assertEqual(3, code)
        self.assertIn("SUITE-029", {item["code"] for item in result["errors"]})

    def test_false_verified_status_fails_closed(self) -> None:
        payload = copy.deepcopy(self.suite())
        payload["status"] = "verified"
        payload["formal_markers"] = ["DOMAIN_VERIFIED"]
        payload["domain_receipts"] = ["self-asserted"]
        code, result = self.run_gate(payload)
        self.assertEqual(3, code)
        self.assertIn("SUITE-046", {item["code"] for item in result["errors"]})

    def test_false_verified_fixture_fails_closed(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GATE), "--input", str(FALSE_VERIFIED)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(3, result.returncode)
        payload = json.loads(result.stdout)
        self.assertIn("SUITE-046", {item["code"] for item in payload["errors"]})

    def test_executed_fail_requires_failed_assertion(self) -> None:
        payload = self.suite()
        failing = next(
            case for case in payload["cases"] if case["execution_status"] == "executed-fail"
        )
        for assertion in failing["assertions"]:
            assertion["observed"] = "pass"
        code, result = self.run_gate(payload)
        self.assertEqual(3, code)
        self.assertIn("SUITE-036", {item["code"] for item in result["errors"]})

    def test_malformed_formal_markers_fail_without_crashing(self) -> None:
        payload = self.suite()
        payload["formal_markers"] = [{"unsupported": True}]
        code, result = self.run_gate(payload)
        self.assertEqual(3, code)
        self.assertIn("SUITE-041", {item["code"] for item in result["errors"]})


if __name__ == "__main__":
    unittest.main()
