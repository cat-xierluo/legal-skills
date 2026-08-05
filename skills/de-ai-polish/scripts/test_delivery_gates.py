#!/usr/bin/env python3
"""de-ai-polish 两层交付门禁回归。"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
IMAGE_GATE = ROOT / "scripts" / "protected_markdown_gate.py"
HEADING_GATE = ROOT / "scripts" / "heading_preservation_gate.py"
DELIVERY_GATE = ROOT / "scripts" / "delivery_gate.py"
RUBRIC = ROOT / "config" / "quality-score-rubric.json"
ASSETS = ROOT / "assets" / "stability"


class DeliveryGateTests(unittest.TestCase):
    maxDiff = None

    def run_gate(
        self, script: Path, *args: str, expected: int
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["python3", str(script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            expected,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def last_json(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
        self.assertTrue(lines, msg=result.stdout)
        return json.loads(lines[-1])

    def test_image_line_gate_positive_and_faults(self) -> None:
        source = ASSETS / "image-lines-source.md"
        positive = self.run_gate(
            IMAGE_GATE,
            "check",
            "--source",
            str(source),
            "--final",
            str(ASSETS / "image-lines-final-ok.md"),
            expected=0,
        )
        self.assertIn("passed_constraint_ids", self.last_json(positive))
        for fixture in (
            "image-lines-final-missing.md",
            "image-lines-final-mutated.md",
            "image-lines-final-reordered.md",
        ):
            with self.subTest(fixture=fixture):
                negative = self.run_gate(
                    IMAGE_GATE,
                    "check",
                    "--source",
                    str(source),
                    "--final",
                    str(ASSETS / fixture),
                    expected=3,
                )
                self.assertEqual(
                    self.last_json(negative)["failed_constraint_ids"],
                    ["PRESERVE-MARKDOWN-IMAGE-LINES"],
                )

    def test_heading_line_gate_preserves_existing_structure(self) -> None:
        source = ASSETS / "heading-lines-source.md"
        positive = self.run_gate(
            HEADING_GATE,
            "check",
            "--source",
            str(source),
            "--final",
            str(ASSETS / "heading-lines-final-ok.md"),
            expected=0,
        )
        self.assertEqual(
            self.last_json(positive)["passed_constraint_ids"],
            ["PRESERVE-MARKDOWN-HEADING-LINES"],
        )
        for fixture in (
            "heading-lines-final-added.md",
            "heading-lines-final-releveled.md",
            "heading-lines-final-renamed.md",
        ):
            with self.subTest(fixture=fixture):
                negative = self.run_gate(
                    HEADING_GATE,
                    "check",
                    "--source",
                    str(source),
                    "--final",
                    str(ASSETS / fixture),
                    expected=3,
                )
                self.assertEqual(
                    self.last_json(negative)["failed_constraint_ids"],
                    ["PRESERVE-MARKDOWN-HEADING-LINES"],
                )

    def test_delivery_gate_positive_and_precise_faults(self) -> None:
        source = ASSETS / "delivery-source.md"
        positive = self.run_gate(
            DELIVERY_GATE,
            "check",
            "--source",
            str(source),
            "--final",
            str(ASSETS / "delivery-final-ok.md"),
            "--run-plan",
            str(ASSETS / "delivery-run-plan.json"),
            "--score-receipt",
            str(ASSETS / "delivery-score-good.json"),
            expected=0,
        )
        self.assertEqual(
            self.last_json(positive)["passed_constraint_ids"],
            [
                "SCENE-DECLARED-BEFORE-REWRITE",
                "VOICE-MODE-DECLARED-BEFORE-REWRITE",
                "PROTECTED-SPANS-PRESERVED",
                "QUALITY-SCORE-GATE-PASSED",
            ],
        )

        local_anchor = self.run_gate(
            DELIVERY_GATE,
            "check",
            "--source",
            str(source),
            "--final",
            str(ASSETS / "delivery-final-ok.md"),
            "--run-plan",
            str(ASSETS / "delivery-run-plan-local-anchor.json"),
            "--score-receipt",
            str(ASSETS / "delivery-score-local-anchor-good.json"),
            expected=0,
        )
        self.assertEqual(
            self.last_json(local_anchor)["observables"]["voice-anchor-id"],
            ["sample-anchor-v1"],
        )

        faults = (
            (
                "delivery-final-ok.md",
                "delivery-run-plan-invalid-scene.json",
                "delivery-score-good.json",
                "SCENE-DECLARED-BEFORE-REWRITE",
            ),
            (
                "delivery-final-ok.md",
                "delivery-run-plan-invalid-voice.json",
                "delivery-score-good.json",
                "VOICE-MODE-DECLARED-BEFORE-REWRITE",
            ),
            (
                "delivery-final-span-mutated.md",
                "delivery-run-plan.json",
                "delivery-score-span-mutated.json",
                "PROTECTED-SPANS-PRESERVED",
            ),
            (
                "delivery-final-ok.md",
                "delivery-run-plan.json",
                "delivery-score-bad.json",
                "QUALITY-SCORE-GATE-PASSED",
            ),
        )
        for final, plan, score, constraint_id in faults:
            with self.subTest(constraint_id=constraint_id):
                negative = self.run_gate(
                    DELIVERY_GATE,
                    "check",
                    "--source",
                    str(source),
                    "--final",
                    str(ASSETS / final),
                    "--run-plan",
                    str(ASSETS / plan),
                    "--score-receipt",
                    str(ASSETS / score),
                    expected=3,
                )
                self.assertEqual(
                    self.last_json(negative)["failed_constraint_ids"],
                    [constraint_id],
                )

    def test_delivery_snapshot_binds_source_and_run_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            copied_source = temp_dir / "source.md"
            copied_plan = temp_dir / "run-plan.json"
            copied_rubric = temp_dir / "quality-score-rubric.json"
            shutil.copy2(ASSETS / "delivery-source.md", copied_source)
            shutil.copy2(ASSETS / "delivery-run-plan.json", copied_plan)
            shutil.copy2(RUBRIC, copied_rubric)
            manifest = temp_dir / "manifest.json"
            self.run_gate(
                DELIVERY_GATE,
                "snapshot",
                "--input",
                str(copied_source),
                "--run-plan",
                str(copied_plan),
                "--rubric",
                str(copied_rubric),
                "--output",
                str(manifest),
                expected=0,
            )
            self.run_gate(
                DELIVERY_GATE,
                "verify",
                "--manifest",
                str(manifest),
                "--final",
                str(ASSETS / "delivery-final-ok.md"),
                "--score-receipt",
                str(ASSETS / "delivery-score-good.json"),
                expected=0,
            )

            rubric = json.loads(copied_rubric.read_text(encoding="utf-8"))
            rubric["thresholds"]["total_minimum"] = 8
            copied_rubric.write_text(
                json.dumps(rubric, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self.run_gate(
                DELIVERY_GATE,
                "verify",
                "--manifest",
                str(manifest),
                "--final",
                str(ASSETS / "delivery-final-ok.md"),
                "--score-receipt",
                str(ASSETS / "delivery-score-good.json"),
                expected=2,
            )
            shutil.copy2(RUBRIC, copied_rubric)

            plan = json.loads(copied_plan.read_text(encoding="utf-8"))
            plan["scene"] = "general"
            copied_plan.write_text(
                json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self.run_gate(
                DELIVERY_GATE,
                "verify",
                "--manifest",
                str(manifest),
                "--final",
                str(ASSETS / "delivery-final-ok.md"),
                "--score-receipt",
                str(ASSETS / "delivery-score-good.json"),
                expected=2,
            )


if __name__ == "__main__":
    unittest.main()
