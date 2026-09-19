#!/usr/bin/env python3
"""Regression tests for evaluation_package_gate.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "evaluation_package_gate.py"
ASSETS = ROOT / "assets"


class GateFixtureTests(unittest.TestCase):
    def run_gate(self, fixture: str) -> tuple[int, dict]:
        result = subprocess.run(
            [
                sys.executable,
                str(GATE),
                "check",
                "--input",
                str(ASSETS / fixture),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertTrue(result.stdout.strip(), result.stderr)
        return result.returncode, json.loads(result.stdout)

    def run_stability_gate(self, fixture: str) -> tuple[int, dict]:
        result = subprocess.run(
            [
                sys.executable,
                str(GATE),
                "check",
                "--input",
                str(ASSETS / fixture),
                "--stability-protocol",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertTrue(result.stdout.strip(), result.stderr)
        return result.returncode, json.loads(result.stdout)

    def test_valid_package_passes(self) -> None:
        code, payload = self.run_gate("evaluation-package-valid.json")
        self.assertEqual(0, code)
        self.assertEqual("pass", payload["status"])
        self.assertEqual(
            {
                "EVAL-REPORT-COVERAGE",
                "EVAL-EVIDENCE-BINDING",
                "EVAL-CLOSURE",
            },
            set(payload["passed_constraint_ids"]),
        )

    def test_legal_near_miss_with_na_reason_passes(self) -> None:
        code, payload = self.run_gate("evaluation-package-legal-near-miss.json")
        self.assertEqual(0, code)
        self.assertEqual("pass", payload["status"])

    def test_missing_dimension_fails_coverage(self) -> None:
        code, payload = self.run_gate("evaluation-package-missing-dimension.json")
        self.assertEqual(3, code)
        self.assertIn("EVAL-REPORT-COVERAGE", payload["failed_constraint_ids"])

    def test_stale_candidate_hash_fails_binding(self) -> None:
        code, payload = self.run_gate("evaluation-package-stale-candidate.json")
        self.assertEqual(3, code)
        self.assertIn("EVAL-EVIDENCE-BINDING", payload["failed_constraint_ids"])

    def test_candidate_hash_scope_mismatch_fails_binding(self) -> None:
        code, payload = self.run_gate("evaluation-package-scope-mismatch.json")
        self.assertEqual(3, code)
        self.assertIn("EVAL-EVIDENCE-BINDING", payload["failed_constraint_ids"])

    def test_false_pass_fails_closure(self) -> None:
        code, payload = self.run_gate("evaluation-package-false-pass.json")
        self.assertEqual(3, code)
        self.assertIn("EVAL-CLOSURE", payload["failed_constraint_ids"])

    def test_historical_template_omission_is_caught(self) -> None:
        code, payload = self.run_gate("evaluation-package-historical-omission.json")
        self.assertEqual(3, code)
        self.assertIn("EVAL-REPORT-COVERAGE", payload["failed_constraint_ids"])

    def test_historical_unbound_output_cannot_support_false_pass(self) -> None:
        code, payload = self.run_gate("evaluation-package-unbound-false-pass.json")
        self.assertEqual(3, code)
        self.assertIn("EVAL-CLOSURE", payload["failed_constraint_ids"])

    def test_out_of_scope_finding_cannot_support_false_pass(self) -> None:
        code, payload = self.run_gate("evaluation-package-out-of-scope-false-pass.json")
        self.assertEqual(3, code)
        self.assertIn("EVAL-CLOSURE", payload["failed_constraint_ids"])

    def test_stability_protocol_positive_shape(self) -> None:
        code, payload = self.run_stability_gate("evaluation-package-valid.json")
        self.assertEqual(0, code)
        self.assertEqual(
            {
                "passed_constraint_ids",
                "artifact_sha256",
                "measurements",
                "observables",
            },
            set(payload),
        )
        self.assertEqual(
            {
                "EVAL-REPORT-COVERAGE",
                "EVAL-EVIDENCE-BINDING",
                "EVAL-CLOSURE",
            },
            set(payload["measurements"]),
        )

    def test_stability_protocol_negative_shape(self) -> None:
        code, payload = self.run_stability_gate(
            "evaluation-package-stale-candidate.json"
        )
        self.assertEqual(3, code)
        self.assertEqual(
            {"failed_constraint_ids", "artifact_sha256", "measurements"},
            set(payload),
        )
        self.assertEqual(
            ["EVAL-EVIDENCE-BINDING"],
            payload["failed_constraint_ids"],
        )

    def test_candidate_hash_changes_with_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SKILL.md").write_text("version one\n", encoding="utf-8")
            first = subprocess.run(
                [
                    sys.executable,
                    str(GATE),
                    "hash",
                    "--candidate-root",
                    str(root),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            (root / "SKILL.md").write_text("version two\n", encoding="utf-8")
            second = subprocess.run(
                [
                    sys.executable,
                    str(GATE),
                    "hash",
                    "--candidate-root",
                    str(root),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, first.returncode)
            self.assertEqual(0, second.returncode)
            self.assertNotEqual(
                json.loads(first.stdout)["candidate_sha256"],
                json.loads(second.stdout)["candidate_sha256"],
            )

    def test_git_tracked_scope_ignores_untracked_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            root = repository / "skill"
            root.mkdir()
            (root / "SKILL.md").write_text("tracked candidate\n", encoding="utf-8")
            (root / "reference.md").write_text("tracked reference\n", encoding="utf-8")
            init = subprocess.run(
                ["git", "init", str(repository)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, init.returncode, init.stderr)
            add = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "add",
                    "skill/SKILL.md",
                    "skill/reference.md",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, add.returncode, add.stderr)

            def hash_candidate(scope: str) -> str:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(GATE),
                        "hash",
                        "--candidate-root",
                        str(root),
                        "--scope",
                        scope,
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                return json.loads(result.stdout)["candidate_sha256"]

            tracked_before = hash_candidate("git-tracked")
            full_before = hash_candidate("full-directory")
            archive = root / "archive"
            archive.mkdir()
            (archive / "runtime-output.txt").write_text(
                "untracked private output\n",
                encoding="utf-8",
            )
            tracked_after = hash_candidate("git-tracked")
            full_after = hash_candidate("full-directory")
            self.assertEqual(tracked_before, tracked_after)
            self.assertNotEqual(full_before, full_after)

            (root / "reference.md").unlink()
            tracked_after_deletion = hash_candidate("git-tracked")
            self.assertNotEqual(tracked_after, tracked_after_deletion)


if __name__ == "__main__":
    unittest.main()
