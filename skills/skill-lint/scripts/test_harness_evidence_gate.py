#!/usr/bin/env python3
"""harness_evidence_gate.py 的故障注入回归测试。"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("harness_evidence_gate.py")
POLICY_FILES = (
    "SKILL.md",
    "references/harness-reliability-standards.md",
    "references/workflow-output-standards.md",
    "references/business-flow-rubric.md",
    "references/reporting-standards.md",
)
class HarnessEvidenceGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.candidate = self.root / "candidate"
        self.policy = self.root / "policy"
        self.review = self.root / "review"
        self.candidate.mkdir()
        self.review.mkdir()
        (self.candidate / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
        (self.candidate / "script.py").write_text(
            "import os\n"
            "import sys\n"
            "if 'HARNESS_TEST_SECRET' in os.environ:\n"
            "    print('secret leaked')\n"
            "    raise SystemExit(9)\n"
            "if '--bad' in sys.argv:\n"
            "    print('blocked invalid input')\n"
            "    raise SystemExit(3)\n"
            "print('ok')\n",
            encoding="utf-8",
        )
        (self.candidate / "mutate.py").write_text(
            "from pathlib import Path\n"
            "Path('generated.txt').write_text('mutation')\n"
            "print('mutated')\n",
            encoding="utf-8",
        )
        for relative in POLICY_FILES:
            path = self.policy / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            content = (
                "---\nname: skill-lint\nversion: \"2.3.0\"\n---\n"
                if relative == "SKILL.md"
                else f"policy: {relative}\n"
            )
            path.write_text(content, encoding="utf-8")
        self.evidence = self.review / "harness-review.json"
        result = self.run_gate(
            "snapshot",
            "--candidate-root",
            str(self.candidate),
            "--policy-root",
            str(self.policy),
            "--output",
            str(self.evidence),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.make_valid_evidence()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_gate(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "HARNESS_TEST_SECRET": "must-not-reach-checker"},
        )

    def load(self) -> dict:
        return json.loads(self.evidence.read_text(encoding="utf-8"))

    def save(self, data: dict) -> None:
        self.evidence.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def make_valid_evidence(self) -> None:
        data = self.load()
        for name in data["review"]["layers"]:
            data["review"]["layers"][name] = {
                "status": "pass",
                "rationale": f"{name} 已有可复查证据",
            }
        data["review"]["hard_findings"] = []
        data["review"]["checks"] = [
            {
                "id": "smoke",
                "runtime": "python3",
                "checker": "script.py",
                "args": [],
                "timeout_seconds": 10,
            }
        ]
        data["review"]["fault_cases"] = [
            {
                "id": "bad-input",
                "target": "错误输入必须被门禁阻断",
                "runtime": "python3",
                "checker": "script.py",
                "args": ["--bad"],
                "timeout_seconds": 10,
                "expected_exit_code": 3,
            }
        ]
        data["review"]["overall"] = "pass"
        self.save(data)

    def verify(self) -> subprocess.CompletedProcess[str]:
        return self.run_gate(
            "verify",
            "--candidate-root",
            str(self.candidate),
            "--policy-root",
            str(self.policy),
            "--evidence",
            str(self.evidence),
            "--confirm-trusted-candidate",
        )

    def test_valid_candidate_is_verified(self) -> None:
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HARNESS_REVIEW_VERIFIED", result.stdout)

    def test_dynamic_verify_requires_trust_confirmation(self) -> None:
        result = self.run_gate(
            "verify",
            "--candidate-root",
            str(self.candidate),
            "--policy-root",
            str(self.policy),
            "--evidence",
            str(self.evidence),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("自有/可信候选", result.stderr)

    def test_candidate_mutation_invalidates_evidence(self) -> None:
        (self.candidate / "script.py").write_text("print('changed')\n", encoding="utf-8")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("证据已陈旧", result.stderr)

    def test_new_candidate_file_invalidates_scope(self) -> None:
        (self.candidate / "new.md").write_text("new\n", encoding="utf-8")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("范围不完整", result.stderr)

    def test_empty_manifest_is_blocked(self) -> None:
        data = self.load()
        data["candidate"]["files"] = []
        self.save(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("为空", result.stderr)

    def test_policy_mutation_invalidates_evidence(self) -> None:
        (self.policy / "SKILL.md").write_text(
            "---\nname: skill-lint\nversion: \"2.3.0\"\n---\nchanged policy\n",
            encoding="utf-8",
        )
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("策略文件清单", result.stderr)

    def test_self_reported_result_fields_are_blocked(self) -> None:
        data = self.load()
        data["review"]["checks"][0]["exit_code"] = 0
        data["review"]["checks"][0]["result"] = "pass"
        self.save(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("自报结果", result.stderr)

    def test_fault_case_must_really_be_blocked(self) -> None:
        data = self.load()
        data["review"]["fault_cases"][0]["args"] = []
        self.save(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("预期 3", result.stderr)

    def test_unknown_checker_is_blocked(self) -> None:
        data = self.load()
        data["review"]["checks"][0]["checker"] = "missing.py"
        self.save(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("不在候选清单", result.stderr)

    def test_unknown_runtime_is_blocked(self) -> None:
        data = self.load()
        data["review"]["checks"][0]["runtime"] = "magic"
        self.save(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("未知 runtime", result.stderr)

    def test_checker_mutation_invalidates_result(self) -> None:
        data = self.load()
        data["review"]["checks"][0]["checker"] = "mutate.py"
        self.save(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checker 修改了候选文件", result.stderr)

    def test_snapshot_does_not_overwrite_existing_evidence(self) -> None:
        result = self.run_gate(
            "snapshot",
            "--candidate-root",
            str(self.candidate),
            "--policy-root",
            str(self.policy),
            "--output",
            str(self.evidence),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("避免覆盖", result.stderr)

    def test_unknown_layer_is_blocked(self) -> None:
        data = self.load()
        data["review"]["layers"]["unknown"] = {
            "status": "pass",
            "rationale": "不应接受未知层",
        }
        self.save(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("未知层", result.stderr)

    def test_not_applicable_requires_rationale(self) -> None:
        data = self.load()
        data["review"]["layers"]["composition"] = {
            "status": "not_applicable",
            "rationale": "无",
        }
        self.save(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("说明边界", result.stderr)


if __name__ == "__main__":
    unittest.main()
