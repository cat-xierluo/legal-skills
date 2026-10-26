#!/usr/bin/env python3
"""Offline fault checks for scripts/validate_examples.py.

Covers the real five example/schema pairs of this Skill plus negative
cases: wrong type, missing required property, extra property, boolean vs
number, $ref siblings, unused/invalid/circular/external references,
unknown keywords, broken regular expressions, trailing newlines against an
anchored pattern, duplicate JSON keys, non-finite numbers, input budgets
and the CLI exit codes.

The suite is standard library only and fully offline. It never reads the
real Magpie configuration, never calls the Magpie CLI and never issues a
model request.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SCRIPT = SCRIPT_DIR / "validate_examples.py"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import validate_examples as v


def run_cli(*args, cwd=None):
    """Run the CLI in a subprocess and return (exit_code, stdout, stderr)."""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class RealPairTests(unittest.TestCase):
    """The five shipped example/schema pairs must pass unchanged."""

    def test_discover_finds_five_pairs(self):
        pairs = v.discover_pairs(SKILL_DIR)
        self.assertEqual(len(pairs), 5)
        names = sorted(p.name for p, _ in pairs)
        self.assertEqual(
            names,
            [
                "integration.example.json",
                "inventory.example.json",
                "policy.example.json",
                "profile.example.json",
                "route-policy.example.json",
            ],
        )

    def test_all_real_pairs_pass(self):
        report = v.validate_skill(SKILL_DIR)
        self.assertEqual(report["summary"]["fail"], 0, report["pairs"])
        self.assertEqual(report["summary"]["pass"], 5, report["pairs"])
        for pair in report["pairs"]:
            self.assertEqual(pair["status"], "pass", pair)
            self.assertEqual(pair["errors"], [])

    def test_shipped_schemas_are_inside_the_declared_subset(self):
        for _, schema_path in v.discover_pairs(SKILL_DIR):
            schema = v.load_json_file(schema_path)
            self.assertEqual(v.check_schema(schema), [], schema_path.name)


class TypeAndShapeTests(unittest.TestCase):
    def test_wrong_type_is_rejected(self):
        errors = v.validate_instance("not-an-int", {"type": "integer"})
        self.assertTrue(errors)
        self.assertIn("type", errors[0])

    def test_missing_required_property_is_rejected(self):
        errors = v.validate_instance({}, {"type": "object", "required": ["alpha"]})
        self.assertTrue(errors)
        self.assertIn("required", errors[0])

    def test_additional_property_is_rejected(self):
        schema = {
            "type": "object",
            "properties": {"alpha": {"type": "string"}},
            "additionalProperties": False,
        }
        errors = v.validate_instance({"alpha": "ok", "beta": "x"}, schema)
        self.assertTrue(errors)
        self.assertIn("additional property", errors[0])

    def test_additional_properties_schema_form_is_applied(self):
        schema = {
            "type": "object",
            "properties": {"alpha": {"type": "string"}},
            "additionalProperties": {"type": "integer"},
        }
        self.assertEqual(v.validate_instance({"alpha": "ok", "beta": 3}, schema), [])
        self.assertTrue(v.validate_instance({"alpha": "ok", "beta": "x"}, schema))

    def test_type_union_accepts_either_member(self):
        schema = {"type": ["string", "null"]}
        self.assertEqual(v.validate_instance("x", schema), [])
        self.assertEqual(v.validate_instance(None, schema), [])
        self.assertTrue(v.validate_instance(1, schema))

    def test_integer_rejects_fraction_and_accepts_zero_fraction(self):
        schema = {"type": "integer"}
        self.assertEqual(v.validate_instance(2, schema), [])
        self.assertEqual(v.validate_instance(2.0, schema), [])
        self.assertTrue(v.validate_instance(2.5, schema))

    def test_array_bounds_and_items(self):
        schema = {"type": "array", "minItems": 1, "maxItems": 2, "items": {"type": "string"}}
        self.assertEqual(v.validate_instance(["a"], schema), [])
        self.assertTrue(v.validate_instance([], schema))
        self.assertTrue(v.validate_instance(["a", "b", "c"], schema))
        self.assertTrue(v.validate_instance(["a", 1], schema))

    def test_numeric_bounds(self):
        schema = {"type": "number", "minimum": 0, "maximum": 100}
        self.assertEqual(v.validate_instance(50, schema), [])
        self.assertTrue(v.validate_instance(-1, schema))
        self.assertTrue(v.validate_instance(101, schema))


class BooleanVersusNumberTests(unittest.TestCase):
    def test_boolean_is_not_a_number(self):
        self.assertTrue(v.validate_instance(True, {"type": "number"}))
        self.assertTrue(v.validate_instance(True, {"type": "integer"}))
        self.assertTrue(v.validate_instance(1, {"type": "boolean"}))

    def test_const_true_is_not_equal_to_one(self):
        errors = v.validate_instance(1, {"const": True})
        self.assertTrue(errors)
        self.assertEqual(v.validate_instance(True, {"const": True}), [])

    def test_const_one_is_not_equal_to_true(self):
        self.assertTrue(v.validate_instance(True, {"const": 1}))

    def test_enum_uses_strict_json_equality(self):
        schema = {"enum": [True, "x"]}
        self.assertEqual(v.validate_instance(True, schema), [])
        self.assertTrue(v.validate_instance(1, schema))
        self.assertEqual(v.validate_instance("x", schema), [])

    def test_minimum_ignores_booleans(self):
        schema = {"type": "number", "minimum": 5}
        self.assertTrue(v.validate_instance(True, schema))


class ReferenceTests(unittest.TestCase):
    def test_ref_siblings_are_not_dropped(self):
        schema = {
            "$defs": {"small": {"type": "integer"}},
            "$ref": "#/$defs/small",
            "maximum": 5,
        }
        self.assertEqual(v.check_schema(schema), [])
        self.assertEqual(v.validate_instance(3, schema), [])
        self.assertTrue(v.validate_instance(7, schema))
        self.assertTrue(v.validate_instance("x", schema))

    def test_ref_resolves_into_defs(self):
        schema = {
            "$defs": {"role": {"type": "object", "required": ["id"]}},
            "type": "object",
            "properties": {"role": {"$ref": "#/$defs/role"}},
        }
        self.assertEqual(v.validate_instance({"role": {"id": "a"}}, schema), [])
        self.assertTrue(v.validate_instance({"role": {}}, schema))

    def test_unused_branch_with_missing_ref_is_rejected(self):
        schema = {
            "type": "object",
            "properties": {"alpha": {"type": "string"}},
            "$defs": {"orphan": {"$ref": "#/$defs/missing"}},
        }
        errors = v.check_schema(schema)
        self.assertTrue(errors)
        self.assertIn("unresolved local reference", errors[0])

    def test_unused_branch_with_unknown_keyword_is_rejected(self):
        schema = {
            "type": "object",
            "$defs": {"orphan": {"type": "string", "minLength": 2}},
        }
        errors = v.check_schema(schema)
        self.assertTrue(errors)
        self.assertIn("unsupported keyword", errors[0])

    def test_unused_branch_with_unknown_type_is_rejected(self):
        schema = {
            "type": "object",
            "$defs": {"orphan": {"type": "date"}},
        }
        errors = v.check_schema(schema)
        self.assertTrue(errors)
        self.assertIn("unsupported type", errors[0])

    def test_external_ref_is_rejected(self):
        schema = {"type": "object", "properties": {"a": {"$ref": "https://x.invalid/s.json"}}}
        errors = v.check_schema(schema)
        self.assertTrue(errors)
        self.assertIn("local reference", errors[0])

    def test_circular_ref_is_rejected(self):
        schema = {
            "$defs": {
                "a": {"$ref": "#/$defs/b"},
                "b": {"$ref": "#/$defs/a"},
            },
            "$ref": "#/$defs/a",
        }
        errors = v.check_schema(schema)
        self.assertTrue(errors)
        self.assertTrue(any("circular" in e for e in errors), errors)

    def test_self_circular_ref_is_rejected(self):
        schema = {"$defs": {"a": {"$ref": "#/$defs/a"}}, "$ref": "#/$defs/a"}
        errors = v.check_schema(schema)
        self.assertTrue(errors)
        self.assertTrue(any("circular" in e for e in errors), errors)

    def test_unknown_keyword_is_rejected(self):
        schema = {"type": "object", "oneOf": [{"type": "object"}]}
        errors = v.check_schema(schema)
        self.assertTrue(errors)
        self.assertIn("unsupported keyword", errors[0])

    def test_annotations_are_accepted_but_not_enforced(self):
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://example.invalid/x.v1",
            "title": "x.v1",
            "description": "annotation only",
            "type": "string",
            "default": "anything",
        }
        self.assertEqual(v.check_schema(schema), [])
        self.assertEqual(v.validate_instance("value", schema), [])

    def test_tuple_form_items_is_rejected(self):
        schema = {"type": "array", "items": [{"type": "string"}]}
        errors = v.check_schema(schema)
        self.assertTrue(errors)


class PatternTests(unittest.TestCase):
    def test_anchored_pattern_rejects_trailing_newline(self):
        schema = {"type": "string", "pattern": "^abc$"}
        self.assertEqual(v.validate_instance("abc", schema), [])
        self.assertTrue(v.validate_instance("abc\n", schema))

    def test_shipped_time_window_pattern_rejects_trailing_newline(self):
        schema = {"type": "string", "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]-([01][0-9]|2[0-3]):[0-5][0-9]$"}
        self.assertEqual(v.validate_instance("14:00-18:00", schema), [])
        self.assertTrue(v.validate_instance("14:00-18:00\n", schema))

    def test_non_anchored_pattern_is_rejected(self):
        schema = {"type": "string", "pattern": "abc"}
        errors = v.check_schema(schema)
        self.assertTrue(errors)
        self.assertIn("start-anchored", errors[0])

    def test_invalid_regular_expression_is_rejected(self):
        schema = {"type": "string", "pattern": "^(unclosed"}
        errors = v.check_schema(schema)
        self.assertTrue(errors)
        self.assertIn("invalid regular expression", errors[0])

    def test_lookaround_is_rejected(self):
        schema = {"type": "string", "pattern": "^(?=abc)abc$"}
        errors = v.check_schema(schema)
        self.assertTrue(errors)

    def test_pattern_only_applies_to_strings(self):
        schema = {"type": ["number", "string"], "pattern": "^abc$"}
        self.assertEqual(v.validate_instance(5, schema), [])


class InputBudgetTests(unittest.TestCase):
    def test_duplicate_keys_are_rejected(self):
        with self.assertRaises(v.InputError):
            v.parse_json_text('{"alpha": 1, "alpha": 2}')

    def test_nan_and_infinity_are_rejected(self):
        for text in ("NaN", "Infinity", "-Infinity", '{"alpha": NaN}'):
            with self.subTest(text=text):
                with self.assertRaises(v.InputError):
                    v.parse_json_text(text)

    def test_invalid_json_is_rejected(self):
        with self.assertRaises(v.InputError):
            v.parse_json_text("{not json}")

    def test_oversized_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.json"
            path.write_text("[" + "1," * 525000 + "1]", encoding="utf-8")
            self.assertGreater(path.stat().st_size, v.MAX_FILE_BYTES)
            with self.assertRaises(v.InputError):
                v.load_json_file(path)

    def test_deep_nesting_is_rejected(self):
        payload = "[" * (v.MAX_DEPTH + 5) + "]" * (v.MAX_DEPTH + 5)
        with self.assertRaises(v.InputError):
            v.parse_json_text(payload)

    def test_missing_file_is_an_input_error(self):
        with self.assertRaises(v.InputError):
            v.load_json_file("/nonexistent/path/does-not-exist.json")

    def test_missing_config_dir_is_an_input_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(v.InputError):
                v.discover_pairs(tmp)

    def test_example_without_schema_is_an_input_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_json(Path(tmp) / "config" / "demo.example.json", {"a": 1})
            with self.assertRaises(v.InputError):
                v.discover_pairs(tmp)


class DiagnosticSafetyTests(unittest.TestCase):
    def test_diagnostics_do_not_echo_instance_values(self):
        secret = "REDACTED-INSTANCE-VALUE"
        cases = [
            ({"type": "integer"}, secret),
            ({"const": "other-const"}, secret),
            ({"enum": ["a", "b"]}, secret),
            ({"type": "string", "pattern": "^zzz$"}, secret),
            (
                {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                secret,
            ),
        ]
        for schema, value in cases:
            with self.subTest(schema=schema):
                errors = v.validate_instance(value, schema)
                self.assertTrue(errors)
                joined = " ".join(errors)
                self.assertNotIn(secret, joined)
                self.assertNotIn("SECRET-VALUE", joined)

    def test_extra_property_name_is_withheld(self):
        secret_key = "SECRET-KEY-9f2a"
        schema = {"type": "object", "properties": {}, "additionalProperties": False}
        errors = v.validate_instance({secret_key: 1}, schema)
        self.assertTrue(errors)
        self.assertNotIn(secret_key, " ".join(errors))


class CliTests(unittest.TestCase):
    def test_default_run_passes_with_exit_zero(self):
        code, out, _err = run_cli()
        self.assertEqual(code, 0, out)
        self.assertIn("通过 5", out)

    def test_root_option_passes(self):
        code, out, _err = run_cli("--root", str(SKILL_DIR))
        self.assertEqual(code, 0, out)

    def test_single_pair_options_pass(self):
        code, out, _err = run_cli(
            "--example", str(SKILL_DIR / "config" / "policy.example.json"),
            "--schema", str(SKILL_DIR / "config" / "policy.schema.json"),
        )
        self.assertEqual(code, 0, out)

    def test_instance_mismatch_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            example = write_json(
                Path(tmp) / "demo.example.json",
                {"schema": "demo.v1", "count": "not-a-number"},
            )
            schema = write_json(
                Path(tmp) / "demo.schema.json",
                {
                    "$id": "https://example.invalid/demo.v1",
                    "type": "object",
                    "required": ["schema", "count"],
                    "properties": {
                        "schema": {"const": "demo.v1"},
                        "count": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
            )
            code, out, _err = run_cli("--example", str(example), "--schema", str(schema))
            self.assertEqual(code, 1, out)

    def test_schema_error_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            example = write_json(Path(tmp) / "demo.example.json", {"a": 1})
            schema = write_json(
                Path(tmp) / "demo.schema.json",
                {"type": "object", "oneOf": [{"type": "object"}]},
            )
            code, out, _err = run_cli("--example", str(example), "--schema", str(schema))
            self.assertEqual(code, 2, out)

    def test_broken_example_json_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            example = write_text(Path(tmp) / "demo.example.json", "{oops")
            schema = write_json(Path(tmp) / "demo.schema.json", {"type": "object"})
            code, _out, _err = run_cli("--example", str(example), "--schema", str(schema))
            self.assertEqual(code, 2)

    def test_duplicate_key_example_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            example = write_text(
                Path(tmp) / "demo.example.json", '{"alpha": 1, "alpha": 2}'
            )
            schema = write_json(Path(tmp) / "demo.schema.json", {"type": "object"})
            code, _out, _err = run_cli("--example", str(example), "--schema", str(schema))
            self.assertEqual(code, 2)

    def test_missing_file_exits_two(self):
        code, _out, _err = run_cli(
            "--example", "/nonexistent/a.json", "--schema", "/nonexistent/b.json"
        )
        self.assertEqual(code, 2)

    def test_usage_error_exits_two(self):
        code, _out, _err = run_cli("--example", "/nonexistent/a.json")
        self.assertEqual(code, 2)

    def test_json_output_is_machine_readable(self):
        code, out, _err = run_cli("--json")
        self.assertEqual(code, 0, out)
        report = json.loads(out)
        self.assertEqual(report["summary"]["pass"], 5)
        self.assertEqual(report["summary"]["fail"], 0)


class IsolatedCopyTests(unittest.TestCase):
    """An isolated copy of the tree must keep working without this checkout."""

    def test_copied_tree_validates_and_still_detects_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy_root = Path(tmp) / "skill"
            shutil.copytree(
                SKILL_DIR / "config", copy_root / "config", ignore=shutil.ignore_patterns("*.local.*")
            )
            (copy_root / "scripts").mkdir(parents=True)
            shutil.copy2(SCRIPT, copy_root / "scripts" / "validate_examples.py")

            code, out, _err = run_cli("--root", str(copy_root))
            self.assertEqual(code, 0, out)
            self.assertIn("通过 5", out)

            broken = copy_root / "config" / "policy.example.json"
            broken.write_text(
                json.dumps({"schema": "magpie-route-policy.v1", "groups": []}),
                encoding="utf-8",
            )
            code, out, _err = run_cli("--root", str(copy_root))
            self.assertEqual(code, 1, out)

    def test_copied_single_pair_runs_from_its_own_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy_root = Path(tmp) / "skill"
            shutil.copytree(
                SKILL_DIR / "config", copy_root / "config", ignore=shutil.ignore_patterns("*.local.*")
            )
            (copy_root / "scripts").mkdir(parents=True)
            shutil.copy2(SCRIPT, copy_root / "scripts" / "validate_examples.py")
            code, out, _err = run_cli(
                "--example", str(copy_root / "config" / "profile.example.json"),
                "--schema", str(copy_root / "config" / "profile.schema.json"),
            )
            self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
