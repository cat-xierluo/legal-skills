#!/usr/bin/env python3
"""语义骨架与 VoiceAnchor 复刻门禁回归。"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "stability"
SEMANTIC_GATE = ROOT / "scripts" / "semantic_repetition_gate.py"
VOICE_GATE = ROOT / "scripts" / "voice_anchor_copy_gate.py"


class SemanticRepetitionTests(unittest.TestCase):
    def run_case(
        self,
        fixture: str,
        maximum: int,
        expected: int,
        *,
        max_per_section: int = 2,
        max_final_section: int = 1,
        max_adjacent: int = 1,
    ) -> dict[str, object]:
        result = subprocess.run(
            [
                "python3",
                str(SEMANTIC_GATE),
                "--file",
                str(ASSETS / fixture),
                "--max-count",
                str(maximum),
                "--max-per-section",
                str(max_per_section),
                "--max-final-section",
                str(max_final_section),
                "--max-adjacent",
                str(max_adjacent),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, msg=result.stderr or result.stdout)
        return json.loads(result.stdout)

    def test_lexically_varied_skeleton_is_blocked(self) -> None:
        output = self.run_case("semantic-capability-repeated.md", 2, 3)
        self.assertEqual(
            output["failed_constraint_ids"],
            ["NO-REPEATED-CAPABILITY-BOUNDARY-SKELETON"],
        )
        self.assertEqual(output["candidate_count"], 3)

    def test_single_functional_boundary_passes(self) -> None:
        output = self.run_case("semantic-capability-functional.md", 2, 0)
        self.assertEqual(
            output["passed_constraint_ids"],
            ["NO-REPEATED-CAPABILITY-BOUNDARY-SKELETON"],
        )

    def test_implicit_surface_task_skeleton_is_blocked(self) -> None:
        output = self.run_case("semantic-capability-implicit.md", 12, 3)
        self.assertEqual(output["candidate_count"], 3)

    def test_distributed_implicit_skeletons_are_blocked(self) -> None:
        output = self.run_case("semantic-capability-distributed.md", 5, 3)
        self.assertEqual(output["candidate_count"], 6)

    def test_evasive_boundary_phrasing_is_blocked(self) -> None:
        output = self.run_case("semantic-capability-evasion.md", 3, 3)
        self.assertEqual(output["candidate_count"], 10)

    def test_functional_navigation_candidates_are_reported_but_not_hard_counted(self) -> None:
        output = self.run_case(
            "semantic-capability-functional-navigation.md",
            1,
            0,
            max_per_section=1,
        )
        self.assertEqual(output["candidate_count"], 5)
        self.assertEqual(output["counted_candidate_count"], 0)
        self.assertEqual(output["functional_navigation_candidate_count"], 5)


class VoiceAnchorCopyTests(unittest.TestCase):
    def run_case(self, source: str, final: str, expected: int) -> dict[str, object]:
        result = subprocess.run(
            [
                "python3",
                str(VOICE_GATE),
                "--source",
                str(ASSETS / source),
                "--final",
                str(ASSETS / final),
                "--sample",
                str(ASSETS / "voice-copy-sample.md"),
                "--min-chars",
                "14",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, msg=result.stderr or result.stdout)
        return json.loads(result.stdout)

    def test_new_long_overlap_is_blocked_without_echoing_phrase(self) -> None:
        output = self.run_case("voice-copy-source.md", "voice-copy-final-copied.md", 3)
        self.assertEqual(output["failed_constraint_ids"], ["NO-NEW-VOICE-ANCHOR-COPY"])
        serialized = json.dumps(output, ensure_ascii=False)
        self.assertNotIn("反复回看", serialized)

    def test_paraphrase_passes(self) -> None:
        output = self.run_case("voice-copy-source.md", "voice-copy-final-safe.md", 0)
        self.assertEqual(output["passed_constraint_ids"], ["NO-NEW-VOICE-ANCHOR-COPY"])

    def test_overlap_already_present_in_source_passes(self) -> None:
        output = self.run_case("voice-copy-source-existing.md", "voice-copy-final-existing.md", 0)
        self.assertEqual(output["passed_constraint_ids"], ["NO-NEW-VOICE-ANCHOR-COPY"])


if __name__ == "__main__":
    unittest.main()
