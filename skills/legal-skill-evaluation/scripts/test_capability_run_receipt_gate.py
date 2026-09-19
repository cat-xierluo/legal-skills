#!/usr/bin/env python3
"""Regression tests for capability_run_receipt_gate.py."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evaluation_package_gate import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "capability_run_receipt_gate.py"
SUITE = ROOT / "evals" / "contract-calibration-260730" / "capability-suite.json"
RECEIPTS = (
    ROOT / "evals" / "contract-calibration-260730" / "current-run-receipts.json"
)


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


class CapabilityRunReceiptGateTests(unittest.TestCase):
    def payloads(self) -> tuple[dict, dict]:
        suite = json.loads(SUITE.read_text(encoding="utf-8"))
        receipts = json.loads(RECEIPTS.read_text(encoding="utf-8"))
        return suite, receipts

    def run_gate(self, suite: dict, receipts: dict) -> tuple[int, dict]:
        with tempfile.TemporaryDirectory(prefix="capability-receipt-test-") as temp_dir:
            temp_root = Path(temp_dir)
            suite_path = temp_root / "suite.json"
            receipts_path = temp_root / "receipts.json"
            for run in receipts.get("runs", []):
                artifacts = run.get("artifacts", [])
                if not isinstance(artifacts, list):
                    continue
                for artifact in artifacts:
                    raw_path = artifact.get("path")
                    if not isinstance(raw_path, str) or raw_path.startswith("../"):
                        continue
                    source = (ROOT / raw_path).resolve()
                    destination = temp_root / raw_path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
            suite_path.write_text(
                json.dumps(suite, ensure_ascii=False), encoding="utf-8"
            )
            receipts_path.write_text(
                json.dumps(receipts, ensure_ascii=False), encoding="utf-8"
            )
            for case in suite.get("cases", []):
                for ref in case.get("run_receipts", []):
                    if isinstance(ref, dict):
                        ref["manifest"] = "receipts.json"
            suite_path.write_text(
                json.dumps(suite, ensure_ascii=False), encoding="utf-8"
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(GATE),
                    "--suite",
                    str(suite_path),
                    "--receipts",
                    str(receipts_path),
                    "--candidate-root",
                    str(CANDIDATE),
                    "--evidence-root",
                    str(temp_root),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            return completed.returncode, json.loads(completed.stdout)

    @staticmethod
    def case(suite: dict, case_id: str) -> dict:
        return next(case for case in suite["cases"] if case["id"] == case_id)

    @staticmethod
    def receipt_run(receipts: dict, run_id: str) -> dict:
        return next(run for run in receipts["runs"] if run["id"] == run_id)

    def rebind(self, suite: dict, receipts: dict, case_id: str, run_id: str) -> None:
        case = self.case(suite, case_id)
        run = self.receipt_run(receipts, run_id)
        case["run_receipts"][0]["record_sha256"] = canonical_hash(run)

    def error_codes(self, payload: dict) -> set[str]:
        return {item["code"] for item in payload["errors"]}

    def test_current_receipts_pass(self) -> None:
        suite, receipts = self.payloads()
        code, result = self.run_gate(suite, receipts)
        self.assertEqual(0, code)
        self.assertEqual("pass", result["status"])
        self.assertEqual(20, result["measurements"]["receipt_record_count"])
        self.assertEqual(18, result["measurements"]["artifact_backed_count"])

    def test_unstructured_self_report_is_rejected(self) -> None:
        suite, receipts = self.payloads()
        self.case(suite, "CONTRACT-E2E-DESIGN-CURRENT")["run_receipts"] = [
            "self-reported-pass"
        ]
        code, result = self.run_gate(suite, receipts)
        self.assertEqual(3, code)
        self.assertIn("RECEIPT-012", self.error_codes(result))

    def test_stale_record_hash_is_rejected(self) -> None:
        suite, receipts = self.payloads()
        self.receipt_run(receipts, "design-current")["runner"]["command"] += " --changed"
        code, result = self.run_gate(suite, receipts)
        self.assertEqual(3, code)
        self.assertIn("RECEIPT-016", self.error_codes(result))

    def test_candidate_mismatch_is_rejected(self) -> None:
        suite, receipts = self.payloads()
        run = self.receipt_run(receipts, "design-current")
        run["candidate_sha256"] = "0" * 64
        self.rebind(suite, receipts, "CONTRACT-E2E-DESIGN-CURRENT", "design-current")
        code, result = self.run_gate(suite, receipts)
        self.assertEqual(3, code)
        self.assertIn("RECEIPT-018", self.error_codes(result))

    def test_case_mismatch_is_rejected(self) -> None:
        suite, receipts = self.payloads()
        run = self.receipt_run(receipts, "design-current")
        run["case_id"] = "CONTRACT-E2E-PATENT-CURRENT"
        self.rebind(suite, receipts, "CONTRACT-E2E-DESIGN-CURRENT", "design-current")
        code, result = self.run_gate(suite, receipts)
        self.assertEqual(3, code)
        self.assertIn("RECEIPT-017", self.error_codes(result))

    def test_input_mismatch_is_rejected(self) -> None:
        suite, receipts = self.payloads()
        run = self.receipt_run(receipts, "role-missing-synthetic")
        run["input_sha256"] = "0" * 64
        self.rebind(
            suite,
            receipts,
            "CONTRACT-MICRO-ROLE-MISSING",
            "role-missing-synthetic",
        )
        code, result = self.run_gate(suite, receipts)
        self.assertEqual(3, code)
        self.assertIn("RECEIPT-019", self.error_codes(result))

    def test_assertion_omission_is_rejected(self) -> None:
        suite, receipts = self.payloads()
        run = self.receipt_run(receipts, "design-current")
        run["assertions"] = run["assertions"][:-1]
        self.rebind(suite, receipts, "CONTRACT-E2E-DESIGN-CURRENT", "design-current")
        code, result = self.run_gate(suite, receipts)
        self.assertEqual(3, code)
        self.assertIn("RECEIPT-028", self.error_codes(result))

    def test_artifact_hash_mismatch_is_rejected(self) -> None:
        suite, receipts = self.payloads()
        run = self.receipt_run(receipts, "missing-context-controlled")
        run["artifacts"][1]["sha256"] = "0" * 64
        self.rebind(
            suite,
            receipts,
            "CONTRACT-DYNAMIC-MISSING-CONTEXT",
            "missing-context-controlled",
        )
        code, result = self.run_gate(suite, receipts)
        self.assertEqual(3, code)
        self.assertIn("RECEIPT-036", self.error_codes(result))

    def test_evidence_path_escape_is_rejected(self) -> None:
        suite, receipts = self.payloads()
        run = self.receipt_run(receipts, "missing-context-controlled")
        run["artifacts"][1]["path"] = "../outside.md"
        self.rebind(
            suite,
            receipts,
            "CONTRACT-DYNAMIC-MISSING-CONTEXT",
            "missing-context-controlled",
        )
        code, result = self.run_gate(suite, receipts)
        self.assertEqual(3, code)
        self.assertIn("RECEIPT-035", self.error_codes(result))

    def test_orphan_run_is_rejected(self) -> None:
        suite, receipts = self.payloads()
        orphan = copy.deepcopy(receipts["runs"][0])
        orphan["id"] = "orphan-run"
        orphan["case_id"] = "ORPHAN-CASE"
        receipts["runs"].append(orphan)
        code, result = self.run_gate(suite, receipts)
        self.assertEqual(3, code)
        self.assertIn("RECEIPT-041", self.error_codes(result))

    def test_verified_claim_rejects_digest_only_runs(self) -> None:
        suite, receipts = self.payloads()
        suite["status"] = "verified"
        suite["formal_markers"] = ["DOMAIN_VERIFIED"]
        suite["domain_receipts"] = [
            {
                "path": "evals/contract-calibration-260730/missing-context-output.md",
                "sha256": "809d7fa6f2105b43c0924309f8f0163ac3933fc78ff19baf072b015fb9ae020f",
                "candidate_sha256": suite["candidate"]["sha256"],
                "suite_id": suite["suite_id"],
            }
        ]
        code, result = self.run_gate(suite, receipts)
        self.assertEqual(3, code)
        self.assertIn("RECEIPT-043", self.error_codes(result))


if __name__ == "__main__":
    unittest.main()
