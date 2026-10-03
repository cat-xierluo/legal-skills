#!/usr/bin/env python3
"""Synthetic regressions for fail-closed evaluation input contracts."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

import evaluation_package_gate as package_gate
import semantic_micro_case_gate as semantic_gate


ROOT = Path(__file__).resolve().parents[1]


class RawFindingTests(unittest.TestCase):
    def package(self):
        payload = package_gate.load_package(ROOT / "assets/evaluation-package-valid.json")
        payload["verdict"] = {
            "recommendation": "enter-workflow", "formal_markers": ["DOMAIN_VERIFIED"]
        }
        payload["generic_gate"]["domain_status"] = "DOMAIN_VERIFIED"
        return payload

    def test_rejects_malformed_raw_findings_before_workflow_approval(self):
        for finding in ({"message": "synthetic finding"}, None, "", " ", 7, [], {"id": " "}):
            with self.subTest(finding=finding):
                payload = self.package()
                payload["generic_gate"]["raw_hard_findings"] = [finding]
                result = package_gate.validate(payload, None)
                self.assertIn("BIND-034", {error["code"] for error in result["errors"]})

    def test_valid_string_and_object_findings_still_require_disposition(self):
        for finding in ("SYNTHETIC-001", {"id": "SYNTHETIC-001", "severity": "hard"}):
            payload = self.package()
            payload["generic_gate"]["raw_hard_findings"] = [finding]
            result = package_gate.validate(payload, None)
            self.assertIn("BIND-030", {error["code"] for error in result["errors"]})
            payload["generic_gate"]["finding_adjudications"] = [{
                "finding_id": "SYNTHETIC-001", "disposition": "false-positive",
                "reason": "Synthetic fixture", "evidence": "Synthetic review"
            }]
            self.assertEqual([], package_gate.validate(payload, None)["errors"])

    def test_legacy_schema_and_empty_raw_list_remain_valid(self):
        payload = self.package()
        self.assertEqual([], package_gate.validate(payload, None)["errors"])
        payload["schema_version"] = "1.0"
        del payload["generic_gate"]["raw_hard_findings"]
        del payload["generic_gate"]["finding_adjudications"]
        self.assertEqual([], package_gate.validate(payload, None)["errors"])


class GenericSemanticContractTests(unittest.TestCase):
    def check(self, assertions, output="confirmation", case_id="CASE-SYNTHETIC"):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, target = root / "input.json", root / "output.md"
            source.write_text(json.dumps({"case_id": case_id, "assertions": assertions}))
            target.write_text(output)
            return semantic_gate.validate(source, target)

    def test_rejects_missing_blank_and_non_string_assertion_ids(self):
        for aid in (None, "", " ", [], 7):
            with self.subTest(aid=aid):
                code, result = self.check([{"id": aid, "judge_hint": {"contains_any": ["confirmation"]}}])
                self.assertEqual(2, code)
                self.assertEqual("error", result["status"])

    def test_rejects_duplicate_ids_and_non_object_assertions(self):
        assertion = {"id": "A", "judge_hint": {"contains_any": ["confirmation"]}}
        for assertions in ([assertion, copy.deepcopy(assertion)], [None], ["A"]):
            with self.subTest(assertions=assertions):
                self.assertEqual(2, self.check(assertions)[0])

    def test_rejects_scalar_empty_and_malformed_phrase_lists(self):
        for operator in ("contains_any", "not_contains"):
            for value in ("confirmation", [], [""], [" "], [None], 7, {}):
                with self.subTest(operator=operator, value=value):
                    code, result = self.check([{"id": "A", "judge_hint": {operator: value}}], "c")
                    self.assertEqual(2, code)
                    self.assertEqual("error", result["status"])

    def test_rejects_invalid_regex_and_case_id_without_traceback(self):
        for value in ("[", "", None, []):
            with self.subTest(value=value):
                self.assertEqual(2, self.check([{"id": "A", "judge_hint": {"regex": value}}])[0])
        self.assertEqual(2, self.check([], case_id=[])[0])

    def test_all_declared_operators_must_pass(self):
        hint = {"contains_any": ["confirmation"], "not_contains": ["forbidden"], "regex": "^confirmation"}
        assertion = {"id": "A", "judge_hint": hint}
        self.assertEqual(0, self.check([assertion])[0])
        self.assertEqual(3, self.check([assertion], "confirmation forbidden")[0])
        self.assertEqual(3, self.check([assertion], "prefix confirmation")[0])

    def test_valid_operators_and_optional_metadata_remain_supported(self):
        for hint in ({"contains_any": ["confirmation"]}, {"not_contains": ["forbidden"]}, {"regex": "^confirmation$"}):
            hint["description"] = "Optional descriptor"
            code, result = self.check([{"id": "A", "judge_hint": hint}])
            self.assertEqual(0, code)
            self.assertEqual(["A"], result["passed_constraint_ids"])
        self.assertEqual(3, self.check([{"id": "A", "judge_hint": {"contains_any": ["confirmation"]}}], "c")[0])


if __name__ == "__main__":
    unittest.main()
