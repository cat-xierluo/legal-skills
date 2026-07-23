#!/usr/bin/env python3
"""instruction_stability_gate.py 的历史失效与漂移回归测试。"""

from __future__ import annotations

import base64
import json
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("instruction_stability_gate.py")
HARNESS_SCRIPT = Path(__file__).with_name("harness_evidence_gate.py")
POLICY_ROOT = Path(__file__).resolve().parents[1]


class InstructionStabilityGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.key_temp = tempfile.TemporaryDirectory()
        key_root = Path(cls.key_temp.name)
        cls.private_key = key_root / "evaluator-private.pem"
        cls.public_key = key_root / "evaluator-public.pem"
        generated = subprocess.run(
            [
                "openssl",
                "genpkey",
                "-algorithm",
                "Ed25519",
                "-out",
                str(cls.private_key),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if generated.returncode != 0:
            raise RuntimeError(generated.stderr)
        exported = subprocess.run(
            [
                "openssl",
                "pkey",
                "-in",
                str(cls.private_key),
                "-pubout",
                "-out",
                str(cls.public_key),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if exported.returncode != 0:
            raise RuntimeError(exported.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.key_temp.cleanup()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.candidate = self.root / "candidate"
        self.runs = self.root / "runs"
        self.review = self.root / "review"
        (self.candidate / "config").mkdir(parents=True)
        (self.candidate / "scripts").mkdir()
        (self.candidate / "assets").mkdir()
        self.runs.mkdir()
        self.review.mkdir()
        self.held_out = self.review / "held-out"
        self.held_out.mkdir()
        (self.candidate / "SKILL.md").write_text(
            "---\nname: demo-reviewer\nversion: \"1.0.0\"\n---\n"
            "# Demo\n\n## 完成标准\n\n"
            "<!-- skill-lint:constraint WR-COVERAGE -->\n"
            "必须逐项检查 required-a 和 required-b。\n",
            encoding="utf-8",
        )
        (self.candidate / "scripts" / "check_report.py").write_text(
            "import argparse\n"
            "import hashlib\n"
            "import json\n"
            "import os\n"
            "from pathlib import Path\n"
            "if 'INSTRUCTION_STABILITY_SECRET' in os.environ:\n"
            "    print('secret leaked')\n"
            "    raise SystemExit(9)\n"
            "p = argparse.ArgumentParser()\n"
            "p.add_argument('--input', required=True)\n"
            "a = p.parse_args()\n"
            "path = Path(a.input)\n"
            "data = json.loads(path.read_text())\n"
            "artifact_sha256 = {'review': hashlib.sha256(path.read_bytes()).hexdigest()}\n"
            "required = {'required-a', 'required-b'}\n"
            "if not required.issubset(set(data['dimensions'])):\n"
            "    failed = ['WR-OTHER'] if data.get('wrong_failed_constraint') else ['WR-COVERAGE']\n"
            "    print(json.dumps({'failed_constraint_ids': failed,\n"
            "      'artifact_sha256': artifact_sha256,\n"
            "      'measurements': {failed[0]: {'covered-count': len(data['dimensions'])}}\n"
            "    }, sort_keys=True))\n"
            "    raise SystemExit(3)\n"
            "if data.get('mutate'):\n"
            "    path.write_text(path.read_text() + ' ')\n"
            "constraint_ids = [] if data.get('omit_constraint') else ['WR-COVERAGE']\n"
            "print(json.dumps({'passed_constraint_ids': constraint_ids,\n"
            " 'artifact_sha256': artifact_sha256,\n"
            " 'measurements': {'WR-COVERAGE': {'covered-count': len(data['dimensions'])}},\n"
            " 'observables': {\n"
            "  'covered-dimensions': data['dimensions'],\n"
            "  'finding-count': data['finding_count']\n"
            "}}, sort_keys=True))\n",
            encoding="utf-8",
        )
        (self.candidate / "scripts" / "produce_report.py").write_text(
            "# demo producer implementation\n",
            encoding="utf-8",
        )
        fixture_payloads = {
            "complete.json": {
                "dimensions": ["required-a", "required-b"],
                "finding_count": 2,
            },
            "missing-section.json": {
                "dimensions": ["required-a"],
                "finding_count": 1,
            },
            "historical-omission.json": {
                "dimensions": ["required-b"],
                "finding_count": 1,
            },
        }
        for name, payload in fixture_payloads.items():
            (self.candidate / "assets" / name).write_text(
                json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        self.contract_path = (
            self.candidate / "config" / "instruction-stability-contract.json"
        )
        self.contract_path.write_text(
            json.dumps(self.valid_contract(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.evidence_path = self.review / "runs.json"
        self.write_runs(
            [
                {"dimensions": ["required-a", "required-b"], "finding_count": 2},
                {"dimensions": ["required-b", "required-a"], "finding_count": 2},
                {"dimensions": ["required-a", "required-b"], "finding_count": 2},
            ]
        )
        self.receipt = self.review / "receipt.json"
        self.baseline = self.review / "requirements-baseline.json"
        self.harness_evidence = self.review / "harness-evidence.json"
        self.held_out_manifest = self.review / "held-out-cases.json"
        (self.held_out / "hidden-complete.json").write_text(
            json.dumps(
                {
                    "dimensions": ["required-b", "required-a"],
                    "finding_count": 7,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (self.held_out / "hidden-missing.json").write_text(
            json.dumps({"dimensions": [], "finding_count": 0}) + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def valid_contract(self) -> dict:
        return {
            "schema_version": 1,
            "skill": {"name": "demo-reviewer", "version": "1.0.0"},
            "producer": {
                "id": "demo-review-producer",
                "implementation_paths": ["scripts/produce_report.py"],
            },
            "artifacts": [{"id": "review", "stage": "final", "required": True}],
            "checkers": [
                {
                    "id": "review-coverage",
                    "kind": "active",
                    "modality": "schema",
                    "artifact_stages": ["final"],
                    "independent_from_producer": True,
                    "runtime": "python3",
                    "implementation": "scripts/check_report.py",
                    "args": ["--input", "{artifact:review}"],
                    "timeout_seconds": 10,
                }
            ],
            "constraints": [
                {
                    "id": "WR-COVERAGE",
                    "severity": "hard",
                    "requirement_type": "coverage",
                    "stage": "final",
                    "source_refs": ["SKILL.md#WR-COVERAGE"],
                    "checker_ids": ["review-coverage"],
                    "case_ids": ["complete", "missing-section", "historical-omission"],
                    "historical_failure_known": True,
                }
            ],
            "cases": [
                {
                    "id": "complete",
                    "kind": "positive",
                    "constraint_ids": ["WR-COVERAGE"],
                    "checker_ids": ["review-coverage"],
                    "artifacts": [
                        {
                            "artifact_id": "review",
                            "path": "assets/complete.json",
                        }
                    ],
                    "expected": "pass",
                    "expected_exit_code": 0,
                },
                {
                    "id": "missing-section",
                    "kind": "mutation",
                    "constraint_ids": ["WR-COVERAGE"],
                    "checker_ids": ["review-coverage"],
                    "artifacts": [
                        {
                            "artifact_id": "review",
                            "path": "assets/missing-section.json",
                        }
                    ],
                    "expected": "blocked",
                    "expected_exit_code": 3,
                },
                {
                    "id": "historical-omission",
                    "kind": "historical",
                    "constraint_ids": ["WR-COVERAGE"],
                    "checker_ids": ["review-coverage"],
                    "artifacts": [
                        {
                            "artifact_id": "review",
                            "path": "assets/historical-omission.json",
                        }
                    ],
                    "expected": "blocked",
                    "expected_exit_code": 3,
                },
            ],
            "stability": {
                "minimum_runs": 3,
                "measurements": [
                    {
                        "id": "covered-count",
                        "checker_id": "review-coverage",
                        "constraint_id": "WR-COVERAGE",
                        "value_type": "integer",
                        "condition": "gte",
                        "expected": 2,
                    }
                ],
                "observables": [
                    {
                        "id": "covered-dimensions",
                        "checker_id": "review-coverage",
                        "constraint_ids": ["WR-COVERAGE"],
                        "comparison": "set_equal",
                        "required": True,
                        "tolerance": None,
                    },
                    {
                        "id": "finding-count",
                        "checker_id": "review-coverage",
                        "constraint_ids": ["WR-COVERAGE"],
                        "comparison": "numeric_tolerance",
                        "required": True,
                        "tolerance": 0,
                    },
                ],
            },
        }

    def load_contract(self) -> dict:
        return json.loads(self.contract_path.read_text(encoding="utf-8"))

    def save_contract(self, data: dict) -> None:
        self.contract_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def sign_payload(self, payload: dict) -> dict:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "payload.json"
            signature = Path(temp_dir) / "signature.bin"
            source.write_bytes(canonical)
            completed = subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-sign",
                    "-rawin",
                    "-inkey",
                    str(self.private_key),
                    "-in",
                    str(source),
                    "-out",
                    str(signature),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            signature_value = base64.b64encode(signature.read_bytes()).decode()
        key_id = hashlib.sha256(self.public_key.read_bytes()).hexdigest()[:16]
        return {
            **payload,
            "signature": {
                "algorithm": "ed25519",
                "key_id": key_id,
                "value": signature_value,
            },
        }

    def producer_digest(self) -> str:
        contract = self.load_contract()
        records = []
        for relative in sorted(contract["producer"]["implementation_paths"]):
            path = self.candidate / relative
            records.append(
                {
                    "path": relative,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
        manifest = "".join(
            f"{item['path']}\0{item['sha256']}\n" for item in records
        )
        return hashlib.sha256(manifest.encode()).hexdigest()

    def write_runs(self, payloads: list[dict]) -> None:
        records = []
        evaluation_id = "evaluation-demo-001"
        input_sha256 = hashlib.sha256(b"same-input").hexdigest()
        config_sha256 = hashlib.sha256(b"same-config").hexdigest()
        for index, payload in enumerate(payloads, 1):
            run_dir = self.runs / f"r{index}"
            run_dir.mkdir(exist_ok=True)
            artifact = run_dir / "review.json"
            artifact.write_text(
                json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            artifact_record = {
                "artifact_id": "review",
                "path": f"r{index}/review.json",
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            }
            nonce = f"execution-{index}"
            producer_log = run_dir / "producer-log.json"
            log_payload = self.sign_payload(
                {
                    "schema_version": 1,
                    "run_id": f"r{index}",
                    "execution_nonce": nonce,
                    "input_sha256": input_sha256,
                    "config_sha256": config_sha256,
                    "candidate_sha256": self.candidate_digest(),
                    "producer_id": "demo-review-producer",
                    "producer_sha256": self.producer_digest(),
                    "evaluation_id": evaluation_id,
                    "artifacts": [artifact_record],
                }
            )
            producer_log.write_text(
                json.dumps(log_payload, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            records.append(
                {
                    "id": f"r{index}",
                    "execution_nonce": nonce,
                    "input_sha256": input_sha256,
                    "config_sha256": config_sha256,
                    "producer_log": f"r{index}/producer-log.json",
                    "artifacts": [
                        {"artifact_id": "review", "path": f"r{index}/review.json"}
                    ],
                }
            )
        self.evidence_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "evaluation_id": evaluation_id,
                    "runs": records,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def refresh_producer_logs(self) -> None:
        evidence = json.loads(self.evidence_path.read_text(encoding="utf-8"))
        for run in evidence["runs"]:
            records = []
            unsafe = False
            for artifact in run["artifacts"]:
                relative = Path(artifact["path"])
                if relative.is_absolute() or ".." in relative.parts:
                    unsafe = True
                    break
                path = self.runs / relative
                if not path.is_file():
                    unsafe = True
                    break
                records.append(
                    {
                        "artifact_id": artifact["artifact_id"],
                        "path": artifact["path"],
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
            if unsafe:
                continue
            log_path = self.runs / run["producer_log"]
            log_path.write_text(
                json.dumps(
                    self.sign_payload(
                        {
                            "schema_version": 1,
                            "run_id": run["id"],
                            "execution_nonce": run["execution_nonce"],
                            "input_sha256": run["input_sha256"],
                            "config_sha256": run["config_sha256"],
                            "candidate_sha256": self.candidate_digest(),
                            "producer_id": self.load_contract()["producer"]["id"],
                            "producer_sha256": self.producer_digest(),
                            "evaluation_id": evidence["evaluation_id"],
                            "artifacts": sorted(
                                records, key=lambda item: item["artifact_id"]
                            ),
                        }
                    ),
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

    def candidate_digest(self) -> str:
        records = []
        for path in sorted(self.candidate.rglob("*")):
            relative = path.relative_to(self.candidate)
            if any(
                part in {".git", "archive", "__pycache__", ".pytest_cache"}
                for part in relative.parts
            ):
                continue
            if (
                path.is_file()
                and path.suffix != ".pyc"
                and ".local." not in path.name
            ):
                records.append(
                    {
                        "path": relative.as_posix(),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
        payload = "".join(
            f"{item['path']}\0{item['sha256']}\n" for item in records
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def write_requirements_baseline(self) -> None:
        contract = self.load_contract()
        hard_constraints = [
            {
                "id": item["id"],
                "source_refs": item["source_refs"],
            }
            for item in contract.get("constraints", [])
            if item.get("severity") == "hard"
        ]
        payload = self.sign_payload(
            {
                "schema_version": 1,
                "candidate_sha256": self.candidate_digest(),
                "requirement_sources": ["SKILL.md"],
                "requirement_exclusions": [],
                "hard_constraints": hard_constraints,
            }
        )
        self.baseline.write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def write_held_out_manifest(self) -> None:
        cases = []
        for case_id, kind, name, expected_exit in (
            ("hidden-complete", "positive", "hidden-complete.json", 0),
            ("hidden-missing", "mutation", "hidden-missing.json", 3),
        ):
            path = self.held_out / name
            cases.append(
                {
                    "id": case_id,
                    "kind": kind,
                    "constraint_id": "WR-COVERAGE",
                    "checker_id": "review-coverage",
                    "artifacts": [
                        {
                            "artifact_id": "review",
                            "path": name,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        }
                    ],
                    "expected_exit_code": expected_exit,
                }
            )
        payload = self.sign_payload(
            {
                "schema_version": 1,
                "candidate_sha256": self.candidate_digest(),
                "cases": cases,
            }
        )
        self.held_out_manifest.write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def write_harness_evidence(self) -> None:
        if self.harness_evidence.exists():
            self.harness_evidence.unlink()
        snapshot = subprocess.run(
            [
                "python3",
                str(HARNESS_SCRIPT),
                "snapshot",
                "--candidate-root",
                str(self.candidate),
                "--policy-root",
                str(POLICY_ROOT),
                "--output",
                str(self.harness_evidence),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(snapshot.returncode, 0, snapshot.stderr)
        data = json.loads(self.harness_evidence.read_text(encoding="utf-8"))
        data["review"] = {
            "layers": {
                name: {
                    "status": "pass",
                    "rationale": "独立审查已确认本层满足当前候选的最低证据要求。",
                }
                for name in (
                    "contract",
                    "producer",
                    "verifier",
                    "evidence_binding",
                    "fault_injection",
                    "closure",
                    "composition",
                )
            },
            "hard_findings": [],
            "checks": [
                {
                    "id": "checker-positive",
                    "runtime": "python3",
                    "checker": "scripts/check_report.py",
                    "args": ["--input", "assets/complete.json"],
                    "timeout_seconds": 10,
                }
            ],
            "fault_cases": [
                {
                    "id": "checker-negative",
                    "runtime": "python3",
                    "checker": "scripts/check_report.py",
                    "args": ["--input", "assets/missing-section.json"],
                    "timeout_seconds": 10,
                    "target": "缺少必审维度时必须阻断",
                    "expected_exit_code": 3,
                }
            ],
            "overall": "pass",
        }
        self.harness_evidence.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def prepare_external_evidence(self) -> None:
        self.write_requirements_baseline()
        self.write_harness_evidence()
        self.write_held_out_manifest()

    def run_gate(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "INSTRUCTION_STABILITY_SECRET": "must-not-leak",
            },
        )

    def verify(
        self,
        *extra: str,
        refresh: bool = True,
        refresh_logs: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if refresh:
            self.prepare_external_evidence()
        if refresh_logs:
            self.refresh_producer_logs()
        return self.run_gate(
            "verify",
            "--candidate-root",
            str(self.candidate),
            "--evaluator-public-key",
            str(self.public_key),
            "--requirements-baseline",
            str(self.baseline),
            "--harness-evidence",
            str(self.harness_evidence),
            "--held-out-cases",
            str(self.held_out_manifest),
            "--held-out-root",
            str(self.held_out),
            "--run-evidence",
            str(self.evidence_path),
            "--runs-root",
            str(self.runs),
            "--receipt",
            str(self.receipt),
            "--confirm-trusted-candidate",
            *extra,
        )

    def sign_file(self, source: Path, output: Path) -> subprocess.CompletedProcess[str]:
        return self.run_gate(
            "sign-evidence",
            "--input",
            str(source),
            "--output",
            str(output),
            "--private-key",
            str(self.private_key),
        )

    def verify_signed_receipt(
        self, signed_receipt: Path
    ) -> subprocess.CompletedProcess[str]:
        return self.run_gate(
            "verify-receipt",
            "--receipt",
            str(signed_receipt),
            "--candidate-root",
            str(self.candidate),
            "--evaluator-public-key",
            str(self.public_key),
            "--requirements-baseline",
            str(self.baseline),
            "--harness-evidence",
            str(self.harness_evidence),
            "--held-out-cases",
            str(self.held_out_manifest),
            "--held-out-root",
            str(self.held_out),
            "--run-evidence",
            str(self.evidence_path),
            "--runs-root",
            str(self.runs),
        )

    def test_valid_three_run_candidate_writes_bound_receipt(self) -> None:
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("INSTRUCTION_STABILITY_EVIDENCE_READY", result.stdout)
        receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(receipt["run_count"], 3)
        self.assertEqual(receipt["hard_constraint_ids"], ["WR-COVERAGE"])
        self.assertEqual(len(receipt["runs"]), 3)
        signed = self.review / "signed-receipt.json"
        signed_result = self.sign_file(self.receipt, signed)
        self.assertEqual(signed_result.returncode, 0, signed_result.stderr)
        verified = self.verify_signed_receipt(signed)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertIn("INSTRUCTION_STABILITY_VERIFIED", verified.stdout)

    def test_dynamic_verify_requires_trust_confirmation(self) -> None:
        self.prepare_external_evidence()
        result = self.run_gate(
            "verify",
            "--candidate-root",
            str(self.candidate),
            "--evaluator-public-key",
            str(self.public_key),
            "--requirements-baseline",
            str(self.baseline),
            "--harness-evidence",
            str(self.harness_evidence),
            "--held-out-cases",
            str(self.held_out_manifest),
            "--held-out-root",
            str(self.held_out),
            "--run-evidence",
            str(self.evidence_path),
            "--runs-root",
            str(self.runs),
            "--receipt",
            str(self.receipt),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("自有/可信", result.stderr)

    def test_evaluator_can_sign_new_evidence_without_overwrite(self) -> None:
        unsigned = self.review / "unsigned.json"
        signed = self.review / "signed.json"
        unsigned.write_text('{"schema_version": 1}\n', encoding="utf-8")
        first = self.run_gate(
            "sign-evidence",
            "--input",
            str(unsigned),
            "--output",
            str(signed),
            "--private-key",
            str(self.private_key),
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        payload = json.loads(signed.read_text(encoding="utf-8"))
        self.assertEqual(payload["signature"]["algorithm"], "ed25519")
        self.assertEqual(payload["signature"]["key_id"], hashlib.sha256(
            self.public_key.read_bytes()
        ).hexdigest()[:16])
        self.assertTrue(payload["signature"]["value"])
        second = self.run_gate(
            "sign-evidence",
            "--input",
            str(unsigned),
            "--output",
            str(signed),
            "--private-key",
            str(self.private_key),
        )
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("不允许覆盖", second.stderr)

    def test_policy_root_override_is_not_exposed(self) -> None:
        result = self.verify("--policy-root", str(self.candidate))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments: --policy-root", result.stderr)

    def test_legacy_writing_reviewer_is_not_verified(self) -> None:
        legacy = self.root / "legacy-writing-reviewer"
        legacy.mkdir()
        (legacy / "SKILL.md").write_text(
            "---\nname: writing-reviewer\n---\n"
            "必须逐项审阅内容、论证、术语、口吻和配图，最后给出通过结论。\n",
            encoding="utf-8",
        )
        result = self.run_gate("assess", "--candidate-root", str(legacy))
        self.assertEqual(result.returncode, 2)
        self.assertIn("ISG-003", result.stdout)
        self.assertIn("NOT_VERIFIED", result.stdout)

    def test_legacy_svg_skill_requires_visual_modality(self) -> None:
        legacy = self.root / "legacy-svg"
        legacy.mkdir()
        (legacy / "SKILL.md").write_text(
            "---\nname: svg-book-illustrator\n---\n"
            "必须检查 SVG 颜色、定位、位置和重叠，渲染后即可声明完成。\n",
            encoding="utf-8",
        )
        result = self.run_gate("assess", "--candidate-root", str(legacy))
        self.assertEqual(result.returncode, 2)
        self.assertIn("ISG-002", result.stdout)
        self.assertIn("ISG-004", result.stdout)

    def test_geometry_constraint_rejects_text_checker(self) -> None:
        data = self.load_contract()
        data["constraints"][0]["requirement_type"] = "geometry"
        data["checkers"][0]["modality"] = "text"
        self.save_contract(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("不能由 text 模态验证", result.stderr)

    def test_final_constraint_rejects_source_stage_checker(self) -> None:
        data = self.load_contract()
        data["checkers"][0]["artifact_stages"] = ["source"]
        self.save_contract(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("参数与声明产物阶段不一致", result.stderr)

    def test_checker_must_read_declared_stage_via_artifact_argument(self) -> None:
        data = self.load_contract()
        data["checkers"][0]["args"] = [
            "--input",
            "assets/complete.json",
        ]
        self.save_contract(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("未通过 artifact 参数读取", result.stderr)

    def test_contract_identity_must_match_skill_frontmatter(self) -> None:
        data = self.load_contract()
        data["skill"]["version"] = "9.9.9"
        self.save_contract(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("与 SKILL.md frontmatter 不一致", result.stderr)

    def test_contract_cannot_omit_an_explicit_hard_constraint(self) -> None:
        skill = self.candidate / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8")
            + "\n<!-- skill-lint:constraint WR-SECOND -->\n"
            + "必须同时检查第二个硬约束。\n",
            encoding="utf-8",
        )
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("合同漏项=['WR-SECOND']", result.stderr)

    def test_unmarked_second_hard_requirement_is_blocked(self) -> None:
        skill = self.candidate / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8")
            + "\n必须另外检查一条没有锚点的硬要求。\n",
            encoding="utf-8",
        )
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("未加唯一 constraint marker", result.stderr)

    def test_baseline_cannot_silently_omit_a_requirements_file(self) -> None:
        references = self.candidate / "references"
        references.mkdir()
        (references / "extra-rules.md").write_text(
            "# Extra rules\n\n必须检查一项额外规则。\n",
            encoding="utf-8",
        )
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("未完整枚举候选中含硬要求信号", result.stderr)

    def test_contract_without_external_baseline_remains_not_verified(self) -> None:
        result = self.run_gate(
            "assess",
            "--candidate-root",
            str(self.candidate),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("ISG-006", result.stdout)
        self.assertIn("NOT_VERIFIED", result.stdout)

    def test_existing_but_bypassable_contract_is_reported_not_verified(self) -> None:
        skill = self.candidate / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8").replace(
                "<!-- skill-lint:constraint WR-COVERAGE -->\n", ""
            ),
            encoding="utf-8",
        )
        result = self.run_gate(
            "assess",
            "--candidate-root",
            str(self.candidate),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("ISG-007", result.stdout)
        self.assertIn("NOT_VERIFIED", result.stdout)

    def test_external_baseline_must_match_all_hard_constraints(self) -> None:
        self.prepare_external_evidence()
        baseline = json.loads(self.baseline.read_text(encoding="utf-8"))
        baseline["hard_constraints"] = []
        self.baseline.write_text(json.dumps(baseline), encoding="utf-8")
        result = self.verify(refresh=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("evaluator Ed25519 signature 无效", result.stderr)

    def test_each_hard_constraint_requires_an_observable(self) -> None:
        skill = self.candidate / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8")
            + "\n<!-- skill-lint:constraint WR-SECOND -->\n"
            + "必须同时检查第二个硬约束。\n",
            encoding="utf-8",
        )
        data = self.load_contract()
        data["constraints"].append(
            {
                "id": "WR-SECOND",
                "severity": "hard",
                "requirement_type": "coverage",
                "stage": "final",
                "source_refs": ["SKILL.md#WR-SECOND"],
                "checker_ids": ["review-coverage"],
                "case_ids": ["complete-second", "missing-second"],
                "historical_failure_known": False,
            }
        )
        data["cases"].extend(
            [
                {
                    "id": "complete-second",
                    "kind": "positive",
                    "constraint_ids": ["WR-SECOND"],
                    "checker_ids": ["review-coverage"],
                    "artifacts": [
                        {
                            "artifact_id": "review",
                            "path": "assets/complete.json",
                        }
                    ],
                    "expected": "pass",
                    "expected_exit_code": 0,
                },
                {
                    "id": "missing-second",
                    "kind": "mutation",
                    "constraint_ids": ["WR-SECOND"],
                    "checker_ids": ["review-coverage"],
                    "artifacts": [
                        {
                            "artifact_id": "review",
                            "path": "assets/missing-section.json",
                        }
                    ],
                    "expected": "blocked",
                    "expected_exit_code": 3,
                },
            ]
        )
        self.save_contract(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("至少需要一个 artifact-derived observable", result.stderr)

    def test_measurement_threshold_is_machine_enforced(self) -> None:
        data = self.load_contract()
        data["stability"]["measurements"][0]["expected"] = 3
        self.save_contract(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("measurement covered-count 未满足 gte 3", result.stderr)

    def test_hard_constraint_requires_positive_and_negative_cases(self) -> None:
        data = self.load_contract()
        data["constraints"][0]["case_ids"] = ["complete", "historical-omission"]
        data["cases"] = [
            case for case in data["cases"] if case["id"] != "missing-section"
        ]
        self.save_contract(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("缺少正例或故障/变异反例", result.stderr)

    def test_known_failure_requires_historical_case(self) -> None:
        data = self.load_contract()
        data["constraints"][0]["case_ids"] = ["complete", "missing-section"]
        data["cases"] = [
            case for case in data["cases"] if case["id"] != "historical-omission"
        ]
        self.save_contract(data)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("未固化历史回归", result.stderr)

    def test_fewer_than_three_runs_is_blocked(self) -> None:
        self.write_runs(
            [
                {"dimensions": ["required-a", "required-b"], "finding_count": 2},
                {"dimensions": ["required-a", "required-b"], "finding_count": 2},
            ]
        )
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("有效运行轮次不足", result.stderr)

    def test_three_run_records_cannot_reuse_another_run_artifact(self) -> None:
        evidence = json.loads(self.evidence_path.read_text(encoding="utf-8"))
        evidence["runs"][1]["artifacts"][0]["path"] = "r1/review.json"
        self.evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("独立 run 目录", result.stderr)

    def test_three_runs_must_bind_same_input_and_config(self) -> None:
        evidence = json.loads(self.evidence_path.read_text(encoding="utf-8"))
        evidence["runs"][1]["input_sha256"] = hashlib.sha256(
            b"different-input"
        ).hexdigest()
        self.evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("相同 input_sha256 和 config_sha256", result.stderr)

    def test_producer_log_must_match_real_artifact(self) -> None:
        producer_log = self.runs / "r2" / "producer-log.json"
        data = json.loads(producer_log.read_text(encoding="utf-8"))
        data.pop("signature")
        data["execution_nonce"] = "fabricated-nonce"
        producer_log.write_text(
            json.dumps(self.sign_payload(data)), encoding="utf-8"
        )
        result = self.verify(refresh_logs=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("producer_log 与本轮输入、配置或真实产物不一致", result.stderr)

    def test_old_producer_log_cannot_be_replayed_for_changed_candidate(self) -> None:
        self.prepare_external_evidence()
        self.refresh_producer_logs()
        skill = self.candidate / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8") + "\n补充非约束说明。\n",
            encoding="utf-8",
        )
        self.prepare_external_evidence()
        result = self.verify(refresh=False, refresh_logs=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("producer_log 与本轮输入、配置或真实产物不一致", result.stderr)

    def test_checker_must_report_every_mapped_constraint(self) -> None:
        self.write_runs(
            [
                {
                    "dimensions": ["required-a", "required-b"],
                    "finding_count": 2,
                    "omit_constraint": True,
                },
                {"dimensions": ["required-a", "required-b"], "finding_count": 2},
                {"dimensions": ["required-a", "required-b"], "finding_count": 2},
            ]
        )
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("未逐项报告全部映射约束", result.stderr)

    def test_coverage_set_drift_is_blocked(self) -> None:
        self.write_runs(
            [
                {"dimensions": ["required-a", "required-b"], "finding_count": 2},
                {
                    "dimensions": ["required-a", "required-b", "optional-c"],
                    "finding_count": 2,
                },
                {"dimensions": ["required-a", "required-b"], "finding_count": 2},
            ]
        )
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("覆盖集合在多轮执行中漂移", result.stderr)

    def test_numeric_drift_beyond_tolerance_is_blocked(self) -> None:
        self.write_runs(
            [
                {"dimensions": ["required-a", "required-b"], "finding_count": 2},
                {"dimensions": ["required-a", "required-b"], "finding_count": 3},
                {"dimensions": ["required-a", "required-b"], "finding_count": 2},
            ]
        )
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("波动超过 tolerance", result.stderr)

    def test_checker_mutating_artifact_is_blocked(self) -> None:
        self.write_runs(
            [
                {
                    "dimensions": ["required-a", "required-b"],
                    "finding_count": 2,
                    "mutate": True,
                },
                {"dimensions": ["required-a", "required-b"], "finding_count": 2},
                {"dimensions": ["required-a", "required-b"], "finding_count": 2},
            ]
        )
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("修改了输入 artifact", result.stderr)

    def test_negative_fixtures_detect_a_weakened_checker(self) -> None:
        (self.candidate / "scripts" / "check_report.py").write_text(
            "import argparse\n"
            "import json\n"
            "p = argparse.ArgumentParser()\n"
            "p.add_argument('--input', required=True)\n"
            "p.parse_args()\n"
            "print(json.dumps({'constraint_ids': ['WR-COVERAGE'], 'observables': {\n"
            "  'covered-dimensions': ['required-a', 'required-b'],\n"
            "  'finding-count': 2\n"
            "}}, sort_keys=True))\n",
            encoding="utf-8",
        )
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("退出码为 0，预期 3", result.stderr)

    def test_checker_cannot_distinguish_run_public_and_hidden_by_stage_path(self) -> None:
        checker = self.candidate / "scripts" / "check_report.py"
        checker.write_text(
            checker.read_text(encoding="utf-8").replace(
                "data = json.loads(path.read_text())\n",
                "if any(token in str(path) for token in "
                "('run-artifacts', 'held-case', 'hidden-case')):\n"
                "    print('stage category leaked through path')\n"
                "    raise SystemExit(12)\n"
                "data = json.loads(path.read_text())\n",
            ),
            encoding="utf-8",
        )
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("INSTRUCTION_STABILITY_EVIDENCE_READY", result.stdout)

    def test_negative_case_must_fail_for_the_target_constraint(self) -> None:
        fixture = self.candidate / "assets" / "missing-section.json"
        data = json.loads(fixture.read_text(encoding="utf-8"))
        data["wrong_failed_constraint"] = True
        fixture.write_text(json.dumps(data), encoding="utf-8")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("未精确命中目标 constraint", result.stderr)

    def test_stale_harness_review_cannot_authorize_changed_candidate(self) -> None:
        self.prepare_external_evidence()
        skill = self.candidate / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8") + "\n补充非约束说明。\n",
            encoding="utf-8",
        )
        self.write_requirements_baseline()
        result = self.verify(refresh=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HARNESS_REVIEW_VERIFIED", result.stderr)

    def test_tampered_evaluator_held_out_case_is_blocked(self) -> None:
        self.prepare_external_evidence()
        hidden = self.held_out / "hidden-missing.json"
        hidden.write_text('{"dimensions": []}\n', encoding="utf-8")
        result = self.verify(refresh=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("artifact 不存在或哈希不匹配", result.stderr)

    def test_run_artifact_path_cannot_escape_root(self) -> None:
        evidence = json.loads(self.evidence_path.read_text(encoding="utf-8"))
        evidence["runs"][0]["artifacts"][0]["path"] = "../outside.json"
        self.evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("独立 run 目录", result.stderr)

    def test_receipt_is_immutable(self) -> None:
        first = self.verify()
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.verify()
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("不允许覆盖", second.stderr)

    def test_tampered_signed_receipt_is_not_verified(self) -> None:
        draft = self.verify()
        self.assertEqual(draft.returncode, 0, draft.stderr)
        signed = self.review / "signed-receipt.json"
        signed_result = self.sign_file(self.receipt, signed)
        self.assertEqual(signed_result.returncode, 0, signed_result.stderr)
        payload = json.loads(signed.read_text(encoding="utf-8"))
        payload["run_count"] = 99
        signed.write_text(json.dumps(payload), encoding="utf-8")
        verified = self.verify_signed_receipt(signed)
        self.assertNotEqual(verified.returncode, 0)
        self.assertIn("evaluator Ed25519 signature 无效", verified.stderr)

    def test_dangling_symlink_cannot_be_used_as_receipt(self) -> None:
        self.receipt.symlink_to(self.review / "does-not-exist.json")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("不允许覆盖", result.stderr)


if __name__ == "__main__":
    unittest.main()
