#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
CHECKER = SKILL_ROOT / "scripts" / "check_material_manifest.py"
SCANNER = SKILL_ROOT / "scripts" / "scan_materials.py"
ASSETS = SKILL_ROOT / "assets"


class MaterialManifestCheckerTest(unittest.TestCase):
    def run_checker(self, fixture: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        result = subprocess.run(
            ["python3", str(CHECKER), "--input", str(ASSETS / fixture)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        return result, payload

    def test_valid_fixture_passes_all_constraints(self) -> None:
        result, payload = self.run_checker("stability-manifest-valid.json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            payload["passed_constraint_ids"],
            [
                "STORAGE-SEPARATION",
                "TRACEABILITY-INTEGRITY",
                "UNCERTAINTY-ROUTING",
                "PROCESSING-CLOSURE",
            ],
        )

    def test_completed_processing_fixture_passes(self) -> None:
        result, payload = self.run_checker("stability-manifest-processing-complete.json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PROCESSING-CLOSURE", payload["passed_constraint_ids"])

    def test_completed_candidate_without_writeback_isolated(self) -> None:
        result, payload = self.run_checker("stability-manifest-processing-without-writeback.json")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(payload["failed_constraint_ids"], ["PROCESSING-CLOSURE"])

    def test_processing_payload_in_metadata_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            data = json.loads((ASSETS / "stability-manifest-processing-complete.json").read_text(encoding="utf-8"))
            data["processing_runs"][0]["extra_json"]["result_extra"] = {"raw_text": "合成材料正文"}
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                ["python3", str(CHECKER), "--input", str(path)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            payload = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(result.returncode, 3)
            self.assertEqual(payload["failed_constraint_ids"], ["PROCESSING-CLOSURE"])

    def test_storage_mutation_isolated(self) -> None:
        result, payload = self.run_checker("stability-manifest-storage-under-archive.json")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(payload["failed_constraint_ids"], ["STORAGE-SEPARATION"])

    def test_historical_archive_payload_isolated(self) -> None:
        result, payload = self.run_checker("stability-manifest-historical-archive-payload.json")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(payload["failed_constraint_ids"], ["STORAGE-SEPARATION"])

    def test_broken_reference_mutation_isolated(self) -> None:
        result, payload = self.run_checker("stability-manifest-broken-reference.json")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(payload["failed_constraint_ids"], ["TRACEABILITY-INTEGRITY"])

    def test_unrouted_uncertainty_mutation_isolated(self) -> None:
        result, payload = self.run_checker("stability-manifest-unrouted-uncertainty.json")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(payload["failed_constraint_ids"], ["UNCERTAINTY-ROUTING"])

    def test_real_scanner_manifest_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input"
            source.mkdir()
            (source / "sample.pdf").write_bytes(b"%PDF-1.4 synthetic")
            scan = subprocess.run(
                ["python3", str(SCANNER), str(source), "--no-write-md"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(scan.returncode, 0, scan.stdout + scan.stderr)
            manifests = list((root / ".legal-material-organizer").rglob("materials_manifest.json"))
            self.assertEqual(len(manifests), 1)
            result = subprocess.run(
                ["python3", str(CHECKER), "--input", str(manifests[0])],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_three_runs_preserve_contract_observables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input"
            source.mkdir()
            (source / "sample.pdf").write_bytes(b"%PDF-1.4 synthetic")
            observed: list[dict] = []
            seen_manifests: set[Path] = set()
            for _ in range(3):
                scan = subprocess.run(
                    ["python3", str(SCANNER), str(source), "--no-write-md", "--fresh"],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self.assertEqual(scan.returncode, 0, scan.stdout + scan.stderr)
                manifests = set((root / ".legal-material-organizer").rglob("materials_manifest.json"))
                current = manifests - seen_manifests
                self.assertEqual(len(current), 1)
                seen_manifests = manifests
                result = subprocess.run(
                    ["python3", str(CHECKER), "--input", str(current.pop())],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                observed.append(json.loads(result.stdout.strip().splitlines()[-1])["observables"])
            self.assertEqual(observed, [observed[0], observed[0], observed[0]])


if __name__ == "__main__":
    unittest.main()
