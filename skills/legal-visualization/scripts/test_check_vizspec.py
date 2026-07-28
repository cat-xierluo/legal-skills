#!/usr/bin/env python3
"""check_vizspec.py 的 VizSpec 2.1 声明校验回归。"""

from __future__ import annotations

import builtins
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from check_vizspec import (  # noqa: E402
    MissingDependencyError,
    VizSpecError,
    load_registry,
    load_yaml,
    validate,
)


def valid_spec() -> dict:
    return {
        "vizspec_version": "2.1",
        "routing": {
            "primary_scene": "multi-party-relation",
            "selection_reason": "需要表达多主体及资金关系",
        },
        "visual": {"theme": "client_report", "density": "normal", "icons": False},
        "entities": [
            {
                "id": "a",
                "visual_role": "plaintiff",
                "epistemic_status": "confirmed",
                "emphasis": "normal",
            },
            {
                "id": "b",
                "visual_role": "decision",
                "epistemic_status": "disputed",
                "emphasis": "high",
            },
        ],
        "relations": [
            {"id": "e1", "source": "a", "target": "b", "status": "confirmed"}
        ],
    }


class CheckVizspecTest(unittest.TestCase):
    def test_valid_complete_spec_has_no_errors(self) -> None:
        findings = validate(valid_spec())
        self.assertFalse([item for item in findings if item["severity"] == "error"], findings)

    def test_every_registered_role_is_accepted(self) -> None:
        registry = load_registry()
        data = valid_spec()
        data["entities"] = [
            {"id": f"node-{index}", "visual_role": role}
            for index, role in enumerate(registry["roles"])
        ]
        data["relations"] = []
        findings = validate(data, registry)
        self.assertFalse([item for item in findings if item["severity"] == "error"], findings)
        self.assertIn("decision", registry["roles"])
        self.assertIn("section", registry["roles"])
        self.assertIn("lane", registry["roles"])

    def test_illegal_role_is_error(self) -> None:
        data = valid_spec()
        data["entities"][0]["visual_role"] = "superhero"
        findings = validate(data)
        self.assertIn("visual_role", {item["code"] for item in findings if item["severity"] == "error"})

    def test_invalid_visual_fields_are_not_silently_accepted(self) -> None:
        data = valid_spec()
        data["visual"] = {"theme": "neon", "density": "huge", "icons": True}
        data["entities"][0].update(
            {
                "shape_token": "decision_diamond",
                "emphasis": "extreme",
                "epistemic_status": "rumour",
                "icon": "⚖️",
            }
        )
        findings = validate(data)
        codes = {item["code"] for item in findings if item["severity"] == "error"}
        self.assertTrue(
            {
                "theme",
                "density",
                "icons_disabled",
                "shape_role_mismatch",
                "emphasis",
                "epistemic_status",
                "icon_disabled",
            }.issubset(codes),
            findings,
        )

    def test_routing_and_relation_endpoints_are_required(self) -> None:
        data = valid_spec()
        data.pop("routing")
        data["relations"][0]["target"] = "missing"
        findings = validate(data)
        codes = [item["code"] for item in findings if item["severity"] == "error"]
        self.assertGreaterEqual(codes.count("routing_required"), 2)
        self.assertIn("relation_endpoint", codes)

    def test_missing_pyyaml_is_explicit_dependency_failure(self) -> None:
        real_import = builtins.__import__

        def fake_import(name: str, *args, **kwargs):
            if name == "yaml":
                raise ImportError("simulated missing PyYAML")
            return real_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "spec.yaml"
            path.write_text("vizspec_version: '2.1'\n", encoding="utf-8")
            with mock.patch("builtins.__import__", side_effect=fake_import):
                with self.assertRaisesRegex(MissingDependencyError, "pip install pyyaml"):
                    load_yaml(path)

    def test_registry_drift_is_blocking_error(self) -> None:
        registry = load_registry()
        registry["roles"]["decision"]["shape_token"] = "nonexistent"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "registry.json"
            path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(VizSpecError, "未声明形状 token"):
                load_registry(path)


if __name__ == "__main__":
    unittest.main()
