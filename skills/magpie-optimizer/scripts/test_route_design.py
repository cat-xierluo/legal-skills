#!/usr/bin/env python3
"""Offline checks for the nested smart-split route-design contract."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

SCRIPTS = Path(__file__).resolve().parent
SKILL = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import magpie_route_design as d


def shipped():
    return json.loads((SKILL / "config" / "route-policy.example.json").read_text())


class RouteDesignTests(unittest.TestCase):
    def test_shipped_nested_design_passes_strict(self):
        errors, warnings = d.validate_design(shipped())
        self.assertEqual((errors, warnings), ([], []))

    def test_entry_references_nested_role_groups(self):
        design = shipped()
        entry = next(g for g in design["groups"] if g["role"] == "entry")
        self.assertEqual(entry["routing"], "order")
        self.assertEqual(entry["stays"], "turn")
        nested = [m for m in entry["members"] if m.startswith("group/")]
        self.assertGreaterEqual(len(nested), 4)
        self.assertIn("group/example-free", nested)

    def test_rule_targets_must_be_members(self):
        design = shipped()
        design["groups"][0]["selection_rules"][1]["use"] = "group/example-absent"
        self.assertIn("selection_rule_target_missing", d.validate_design(design)[0])

    def test_nested_group_cycles_and_unknown_refs_are_rejected(self):
        design = shipped()
        planning = next(g for g in design["groups"] if g["role"] == "planning")
        planning["members"].append("group/example-main")
        self.assertIn("nested_group_cycle", d.validate_design(design)[0])
        planning["members"][-1] = "group/example-absent"
        self.assertIn("nested_group_unknown", d.validate_design(design)[0])

    def test_intent_requires_classifier_and_negation_is_warned(self):
        design = shipped()
        entry = next(g for g in design["groups"] if g["role"] == "entry")
        without_negation = copy.deepcopy(entry["selection_rules"][1])
        without_negation["intent"] = "a lightweight task"
        entry["selection_rules"].append(without_negation)
        errors, warnings = d.validate_design(design)
        self.assertIn("intent_rule_negation_missing", warnings)
        entry["classifier"] = None
        errors, _ = d.validate_design(design)
        self.assertIn("intent_rule_requires_classifier", errors)

    def test_compact_should_be_first_and_conditions_required(self):
        design = shipped()
        entry = next(g for g in design["groups"] if g["role"] == "entry")
        compact = entry["selection_rules"].pop(0)
        entry["selection_rules"].append(compact)
        self.assertIn("compact_rule_not_first", d.validate_design(design)[1])
        compact.pop("compact")
        self.assertIn("selection_rule_condition_missing", d.validate_design(design)[0])

    def test_role_capacity_uses_distinct_provider_prefixes(self):
        design = shipped()
        free = next(g for g in design["groups"] if g["role"] == "free")
        free["members"] = ["example/a", "example/b"]
        self.assertIn("role_provider_diversity_insufficient", d.validate_design(design)[1])

    def test_duplicate_json_keys_are_refused_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "design.local.json"
            target.write_text('{"schema": "x", "schema": "y"}', encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "magpie_route_design.py"), "validate",
                 "--design", str(target), "--strict"],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stderr.strip(), '{"status": "REFUSED", "reason": "InputError"}')

    def test_eight_nested_group_levels_are_allowed(self):
        design = shipped()
        entry = next(g for g in design["groups"] if g["role"] == "entry")
        entry["members"] = ["group/example-level-1"]
        entry["selection_rules"] = []
        entry["pause_rules"] = []
        design["groups"] = [entry]
        parent = "group/example-main"
        for level in range(1, 9):
            gid = "group/example-level-%d" % level
            design["groups"].append({
                "id": gid, "role": "nested", "members": [], "routing": "order",
                "stays": "turn", "effort": "agent", "classifier": None,
                "selection_rules": [], "pause_rules": [],
            })
            if level == 1:
                entry["members"] = [gid]
            else:
                previous = "group/example-level-%d" % (level - 1)
                parent_group = next(g for g in design["groups"] if g["id"] == previous)
                parent_group["members"] = [gid]
        leaf = "group/example-level-8"
        leaf_group = next(g for g in design["groups"] if g["id"] == leaf)
        leaf_group["members"] = ["example/model", "other-example/model"]
        errors, warnings = d.validate_design(design)
        self.assertEqual((errors, warnings), ([], []))
        leaf_group["members"] = ["group/example-level-1"]
        self.assertIn("nested_group_depth", d.validate_design(design)[0])

    def test_cli_reports_without_local_identifiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "design.local.json"
            target.write_text(json.dumps(shipped()), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "magpie_route_design.py"), "validate",
                 "--design", str(target), "--strict"],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "PASSED")
            self.assertEqual(report["errors"], [])
            self.assertEqual(report["warnings"], [])


if __name__ == "__main__":
    unittest.main()
