#!/usr/bin/env python3
"""Standard-library contract and real-consumer tests for staged receipts."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT = Path(__file__).with_name("build_staged_receipt.py")
SPEC = importlib.util.spec_from_file_location("build_staged_receipt", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import machinery failure
    raise RuntimeError("cannot load staged receipt adapter")
ADAPTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTER)
PEA_ROOT: Path | None = None


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run(*command: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command), cwd=cwd, check=False, capture_output=True, text=True
    )


def git(repo: Path, *args: str) -> str:
    completed = run("git", "-C", str(repo), *args)
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return completed.stdout.strip()


def stage(
    *,
    stage_id: str = "e2e",
    kind: str = "e2e",
    status: str = "passed",
    required: bool = True,
    command: str = "python3 tests/e2e.py",
    exit_code: int = 0,
    failure_count: int = 0,
    evidence: str = "artifacts/stages/e2e.log",
) -> dict[str, Any]:
    return {
        "id": stage_id,
        "kind": kind,
        "status": status,
        "required": required,
        "command": command,
        "exit_code": exit_code,
        "failure_count": failure_count,
        "evidence": evidence,
    }


class StagedReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.assertEqual(run("git", "init", "-q", str(self.repo)).returncode, 0)
        write(self.repo / "seed.txt", "seed\n")
        write(self.repo / "artifacts/stages/e2e.log", "e2e evidence\n")
        write(self.repo / "artifacts/stages/unit.log", "unit evidence\n")
        write(self.repo / "artifacts/consumer.log", "consumer evidence\n")
        write(self.repo / "artifacts/original-symptom.log", "symptom evidence\n")
        write(self.repo / "artifacts/negative-control.log", "control evidence\n")
        self.assertEqual(git(self.repo, "add", "."), "")
        completed = run(
            "git",
            "-C",
            str(self.repo),
            "-c",
            "user.name=Receipt Test",
            "-c",
            "user.email=receipt@example.invalid",
            "commit",
            "-qm",
            "seed",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.head = git(self.repo, "rev-parse", "HEAD")

    def report(self) -> dict[str, Any]:
        return {
            "contract": "verification-gate-stage-report/v1",
            "claim": {
                "id": "FEATURE-001",
                "type": "feature",
                "statement": "代表性入口由真实 consumer 观察到终态",
                "claimed_level": "e2e_verified",
                "observed_at": datetime.now(timezone.utc).isoformat(),
            },
            "candidate": {"git_commit": self.head},
            "target": {"type": "service", "name": "representative-service"},
            "stages": [stage()],
            "consumer": {
                "name": "downstream-consumer",
                "observed": True,
                "evidence": "artifacts/consumer.log",
            },
            "unsupported_claims": ["真实 provider 与长时容量未验证"],
        }

    def build(self, report: dict[str, Any] | None = None) -> dict[str, Any]:
        return ADAPTER.build_receipt(self.repo, report or self.report())

    def assert_rejected(self, report: dict[str, Any]) -> None:
        with self.assertRaises(ADAPTER.ReceiptError):
            self.build(report)

    def test_valid_input_is_deterministic_and_schema_valid(self) -> None:
        report = self.report()
        first = self.build(report)
        second = self.build(copy.deepcopy(report))
        self.assertEqual(first, second)
        self.assertEqual(
            first["contract"], "production-engineering-completion-evidence/v1"
        )
        self.assertEqual(first["verification"]["kind"], "staged")
        self.assertEqual(first["candidate"]["git_commit"], self.head)

    def test_failed_required_stage_is_preserved(self) -> None:
        report = self.report()
        report["stages"] = [stage(status="failed", exit_code=1, failure_count=1)]
        receipt = self.build(report)
        self.assertEqual(receipt["verification"]["stages"][0]["status"], "failed")
        self.assertEqual(receipt["verification"]["stages"][0]["exit_code"], 1)

    def test_missing_absolute_traversal_and_symlink_escape_are_rejected(self) -> None:
        outside = self.base / "outside.log"
        write(outside, "outside\n")
        link = self.repo / "artifacts/stages/escape.log"
        link.symlink_to(outside)
        for evidence in (
            "artifacts/stages/missing.log",
            str(outside),
            "../outside.log",
            "artifacts/stages/escape.log",
        ):
            with self.subTest(evidence=evidence):
                report = self.report()
                report["stages"][0]["evidence"] = evidence
                self.assert_rejected(report)

    def test_candidate_must_match_head(self) -> None:
        report = self.report()
        report["candidate"]["git_commit"] = "0" * 40
        self.assert_rejected(report)

    def test_duplicate_and_invalid_stage_kinds_are_rejected(self) -> None:
        duplicate = self.report()
        duplicate["stages"].append(
            stage(stage_id="e2e", kind="unit", evidence="artifacts/stages/unit.log")
        )
        self.assert_rejected(duplicate)
        invalid = self.report()
        invalid["stages"][0]["kind"] = "browser-ish"
        self.assert_rejected(invalid)

    def test_bool_as_integer_is_rejected(self) -> None:
        for field in ("exit_code", "failure_count"):
            with self.subTest(field=field):
                report = self.report()
                report["stages"][0][field] = False
                self.assert_rejected(report)

    def test_executed_status_contradictions_are_rejected(self) -> None:
        passed_nonzero = self.report()
        passed_nonzero["stages"][0]["exit_code"] = 1
        self.assert_rejected(passed_nonzero)
        failed_zero = self.report()
        failed_zero["stages"][0]["status"] = "failed"
        self.assert_rejected(failed_zero)
        skipped_with_execution = self.report()
        skipped_with_execution["stages"][0].update(
            {"status": "skipped", "required": False, "skip_reason": "not needed"}
        )
        self.assert_rejected(skipped_with_execution)
        non_runtime_fresh = self.report()
        non_runtime_fresh["stages"][0]["fresh_context"] = True
        self.assert_rejected(non_runtime_fresh)

    def test_required_and_optional_skip_rules_are_rejected(self) -> None:
        required_skip = self.report()
        required_skip["stages"] = [
            {
                "id": "unit",
                "kind": "unit",
                "status": "skipped",
                "required": True,
                "skip_reason": "cannot skip required work",
            }
        ]
        self.assert_rejected(required_skip)
        optional_without_reason = self.report()
        optional_without_reason["stages"] = [
            {"id": "unit", "kind": "unit", "status": "not_run", "required": False}
        ]
        self.assert_rejected(optional_without_reason)

    def test_valid_optional_skip_is_preserved_but_not_promoted(self) -> None:
        report = self.report()
        report["stages"].append(
            {
                "id": "integration",
                "kind": "integration",
                "status": "not_run",
                "required": False,
                "skip_reason": "当前声明不依赖外部 provider",
            }
        )
        receipt = self.build(report)
        skipped = receipt["verification"]["stages"][1]
        self.assertEqual(skipped["status"], "not_run")
        self.assertNotIn("command", skipped)

    def test_bugfix_evidence_is_structural_not_adjudicated(self) -> None:
        report = self.report()
        report["claim"].update(
            {"id": "BUG-001", "type": "bugfix", "claimed_level": "reproduced"}
        )
        report["original_symptom"] = {
            "status": "not_verified",
            "evidence": "artifacts/original-symptom.log",
        }
        report["negative_control"] = {
            "status": "not_proved",
            "evidence": "artifacts/negative-control.log",
        }
        receipt = self.build(report)
        self.assertEqual(receipt["original_symptom"]["status"], "not_verified")
        self.assertEqual(receipt["negative_control"]["status"], "not_proved")

    def test_receipt_has_no_absolute_path_secret_or_independent_verdict(self) -> None:
        receipt = self.build()
        payload = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(str(self.repo), payload)
        forbidden_keys = {"ready", "overall", "verdict", "released"}

        def keys(value: Any) -> set[str]:
            if isinstance(value, dict):
                return set(value) | set().union(*(keys(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(item) for item in value)) if value else set()
            return set()

        self.assertTrue(forbidden_keys.isdisjoint(keys(receipt)))
        report = self.report()
        report["stages"][0]["command"] = "tool --token=super-secret-value"
        self.assert_rejected(report)
        report = self.report()
        report["stages"][0]["command"] = "python3 /srv/tests/e2e.py"
        self.assert_rejected(report)

    def test_punctuated_paths_and_secret_forms_are_rejected(self) -> None:
        mac_path = "/" + "Users/alice/customer.txt"
        dangerous_values = (
            "日志：" + mac_path,
            "log:" + mac_path,
            "file://" + mac_path,
            "日志：/" + mac_path,
            r"output=C:\\Users\\alice\\customer.txt",
            "artifact=~/customer.txt",
            "-----BEGIN PRIVATE KEY-----",
            "-----BEGIN ENCRYPTED PRIVATE KEY-----",
            "Authorization: Basic dXNlcjpwYXNz",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlMTIz",
            "凭证：https://user:pass@example.com/api",
        )
        for value in dangerous_values:
            with self.subTest(value=value):
                report = self.report()
                report["claim"]["statement"] = value
                self.assert_rejected(report)

    def test_ordinary_https_url_is_not_misclassified_as_a_path(self) -> None:
        report = self.report()
        report["claim"]["statement"] = (
            "公开接口说明：https://example.com/api/v1?mode=representative"
        )
        report["stages"][0]["command"] = (
            "curl https://example.com/api/v1?mode=representative"
        )
        receipt = self.build(report)
        self.assertIn("https://example.com/api/v1", receipt["claim"])

    def test_long_non_uri_ascii_input_completes_within_wide_timeout(self) -> None:
        output_relative = "artifacts/long-input-completion-evidence.json"
        report_path = self.base / "long-stage-report.json"
        for shape in ("A", "a."):
            for length in (32 * 1024, 64 * 1024):
                with self.subTest(shape=shape, length=length):
                    value = (shape * (length // len(shape) + 1))[:length]
                    report = self.report()
                    report["claim"]["statement"] = value
                    write(report_path, json.dumps(report, ensure_ascii=False))
                    completed = subprocess.run(
                        [
                            sys.executable,
                            str(SCRIPT),
                            "--repo",
                            str(self.repo),
                            "--input",
                            str(report_path),
                            "--output",
                            output_relative,
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=4,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    emitted = json.loads(
                        (self.repo / output_relative).read_text(encoding="utf-8")
                    )
                    self.assertEqual(len(emitted["claim"]), length)

    def test_cli_blocks_sensitive_input_and_pea_sees_no_receipt(self) -> None:
        self.assertIsNotNone(PEA_ROOT)
        assert PEA_ROOT is not None
        report_path = self.base / "sensitive-stage-report.json"
        output_relative = "artifacts/blocked-completion-evidence.json"
        mac_path = "/" + "Users/alice/customer.txt"
        dangerous_values = (
            "日志：" + mac_path,
            "log:" + mac_path,
            "file://" + mac_path,
            "-----BEGIN PRIVATE KEY-----",
            "Authorization: Basic dXNlcjpwYXNz",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlMTIz",
            "凭证：https://user:pass@example.com/api",
        )
        for value in dangerous_values:
            with self.subTest(value=value):
                report = self.report()
                report["claim"]["statement"] = value
                write(report_path, json.dumps(report, ensure_ascii=False))
                completed = run(
                    sys.executable,
                    str(SCRIPT),
                    "--repo",
                    str(self.repo),
                    "--input",
                    str(report_path),
                    "--output",
                    output_relative,
                )
                self.assertEqual(completed.returncode, 65, completed.stderr)
                self.assertFalse((self.repo / output_relative).exists())

        write(
            self.repo / ".production-engineering-audit.toml",
            """\
schema_version = 1
contract = "production-engineering-audit/v1"
profile = "test"

[ci]
required = false
audit_required = false
install_mode = "local-only"

[scale]
required = false
sizes = []

[completion]
required = true
evidence_file = "artifacts/blocked-completion-evidence.json"
target_type = "service"
minimum_level = "e2e_verified"
max_age_hours = 24
bind_git_head = true
require_clean_worktree = false
""",
        )
        write(
            self.repo / ".github/workflows/placeholder.yml",
            "name: existing-ci\non: [push]\njobs:\n  noop:\n    steps:\n      - run: true\n",
        )
        pea = run(
            sys.executable,
            str(PEA_ROOT / "scripts/audit_project.py"),
            "--repo",
            str(self.repo),
        )
        rows = [json.loads(line) for line in pea.stdout.splitlines() if line.strip()]
        self.assertEqual(pea.returncode, 1, rows)
        hard_rules = {row["rule_id"] for row in rows if row.get("severity") == "hard"}
        self.assertIn("completion-evidence-missing", hard_rules)

    def test_real_pea_consumer_accepts_valid_and_blocks_failed_stage(self) -> None:
        self.assertIsNotNone(PEA_ROOT)
        assert PEA_ROOT is not None
        pea_script = PEA_ROOT / "scripts/audit_project.py"
        self.assertTrue(pea_script.is_file(), pea_script)
        config = """\
schema_version = 1
contract = "production-engineering-audit/v1"
profile = "test"

[ci]
required = false
audit_required = false
install_mode = "local-only"

[scale]
required = false
sizes = []

[completion]
required = true
evidence_file = "artifacts/completion-evidence.json"
target_type = "service"
minimum_level = "e2e_verified"
max_age_hours = 24
bind_git_head = true
require_clean_worktree = false
"""
        write(self.repo / ".production-engineering-audit.toml", config)
        write(
            self.repo / ".github/workflows/placeholder.yml",
            "name: existing-ci\non: [push]\njobs:\n  noop:\n    steps:\n      - run: true\n",
        )
        report_path = self.base / "stage-report.json"
        output_relative = "artifacts/completion-evidence.json"

        def generate(report: dict[str, Any]) -> subprocess.CompletedProcess[str]:
            write(report_path, json.dumps(report, ensure_ascii=False))
            return run(
                sys.executable,
                str(SCRIPT),
                "--repo",
                str(self.repo),
                "--input",
                str(report_path),
                "--output",
                output_relative,
            )

        valid = generate(self.report())
        self.assertEqual(valid.returncode, 0, valid.stderr)
        pea_valid = run(sys.executable, str(pea_script), "--repo", str(self.repo))
        valid_rows = [
            json.loads(line) for line in pea_valid.stdout.splitlines() if line.strip()
        ]
        self.assertEqual(pea_valid.returncode, 0, valid_rows)
        self.assertIn("completion-evidence-valid", {row["rule_id"] for row in valid_rows})

        failed_report = self.report()
        failed_report["stages"] = [
            stage(status="failed", exit_code=1, failure_count=1)
        ]
        failed = generate(failed_report)
        self.assertEqual(failed.returncode, 0, failed.stderr)
        emitted = json.loads((self.repo / output_relative).read_text(encoding="utf-8"))
        self.assertEqual(emitted["verification"]["stages"][0]["status"], "failed")
        pea_failed = run(sys.executable, str(pea_script), "--repo", str(self.repo))
        failed_rows = [
            json.loads(line) for line in pea_failed.stdout.splitlines() if line.strip()
        ]
        self.assertEqual(pea_failed.returncode, 1, failed_rows)
        hard_rules = {
            row["rule_id"] for row in failed_rows if row.get("severity") == "hard"
        }
        self.assertIn("completion-verification-stage-failed", hard_rules)


def main() -> None:
    global PEA_ROOT
    argument_parser = argparse.ArgumentParser(add_help=False)
    argument_parser.add_argument("--pea-root", required=True)
    args, unittest_args = argument_parser.parse_known_args()
    PEA_ROOT = Path(args.pea_root).resolve()
    unittest.main(argv=[sys.argv[0], *unittest_args], verbosity=2)


if __name__ == "__main__":
    main()
