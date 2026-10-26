#!/usr/bin/env python3
"""Offline example/schema validator for the magpie-optimizer Skill.

Scope: this is a deliberately small *subset* validator, not a general
JSON Schema engine. It implements exactly the keyword subset used by this
Skill's own `config/*.schema.json` files and refuses everything else, so a
schema can never look "validated" when it was only partially understood.

Supported validation keywords
    type              (single name or union list)
    required, properties, additionalProperties, items
    enum, const
    minimum, maximum
    minItems, maxItems
    pattern
    $ref              (local JSON pointer only, e.g. "#/$defs/role")

Accepted annotations (never turned into a validation condition)
    $schema, $id, title, description, default, $comment, examples

Structural keywords (walked for schema checking, never applied to data)
    $defs

Every other keyword is rejected, including legal-but-unsupported ones such
as oneOf, allOf, not, format, uniqueItems, minLength, maxLength,
patternProperties, if/then/else, prefixItems, multipleOf,
exclusiveMinimum/exclusiveMaximum, propertyNames, dependentSchemas,
contains and unevaluatedProperties.

Deliberate differences from a full JSON Schema implementation
    * `pattern` runs on Python's `re`, not ECMA-262. Only start-anchored
      patterns are accepted, and a trailing `$` is read as an absolute end
      of string, so a value ending in a newline does NOT match.
    * `type: "integer"` also accepts a float with a zero fractional part.
    * Circular local references are rejected outright.
    * Boolean schemas (`true` / `false`) are not supported as schemas.

Safety properties
    * Offline and standard library only: no network, no third-party
      package, no Magpie CLI, no model request, no quota use.
    * Diagnostics never echo instance values. Only JSON paths, keyword
      names and JSON type names appear in messages.
    * Input budgets: 1 MiB per file, bounded nesting depth and node count.
    * Exit codes: 0 = pass, 1 = instance does not conform,
      2 = usage / file / JSON / schema error.

Public API (stable for `scripts/public_release_check.py` to import)
    check_schema(schema)           -> list[str]  schema problems
    validate_instance(inst, sch)   -> list[str]  instance problems
    validate_pair(example, schema) -> dict       single pair result
    validate_skill(root)           -> dict       whole-skill report
    discover_pairs(root)           -> list[(Path, Path)]
"""

import sys

sys.dont_write_bytecode = True

import argparse
import json
import math
import re
from pathlib import Path

SCHEMA_ID = "magpie-example-validator.v1"

EXIT_OK = 0
EXIT_INSTANCE_ERROR = 1
EXIT_INPUT_ERROR = 2

# Input budgets: a malicious or accidentally huge file must fail loudly
# instead of consuming the machine.
MAX_FILE_BYTES = 1024 * 1024
MAX_DEPTH = 64
MAX_NODES = 100000
MAX_REF_CHAIN = 32
MAX_VALIDATION_DEPTH = 256
MAX_ERRORS = 100

JSON_TYPES = frozenset(
    ("object", "array", "string", "integer", "number", "boolean", "null")
)

VALIDATION_KEYWORDS = frozenset(
    (
        "$ref",
        "type",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "pattern",
    )
)

ANNOTATION_KEYWORDS = frozenset(
    ("$schema", "$id", "title", "description", "default", "$comment", "examples")
)

STRUCTURAL_KEYWORDS = frozenset(("$defs",))


class InputError(Exception):
    """File, JSON or budget problem. Maps to exit code 2."""


class SchemaError(Exception):
    """Schema is invalid or outside the declared subset. Maps to exit code 2."""


class DuplicateKeyError(ValueError):
    pass


class NonFiniteNumberError(ValueError):
    pass


def _drop_cached_bytecode():
    """Remove this module's own cached bytecode.

    Importing the module writes the cache file before this body runs; the
    published tree must stay free of stray artefacts.
    """
    try:
        source = Path(__file__).resolve()
        cached = source.parent / "__pycache__"
        if not cached.is_dir():
            return
        for item in cached.glob(source.stem + ".*.pyc"):
            item.unlink()
        if not any(cached.iterdir()):
            cached.rmdir()
    except OSError:
        pass


# ---------------------------------------------------------------- JSON input


def _pairs_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            # The key name itself comes from the data, so it is not echoed.
            raise DuplicateKeyError()
        result[key] = value
    return result


def _reject_constant(_name):
    raise NonFiniteNumberError()


def _parse_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise NonFiniteNumberError()
    return value


def _measure(value):
    """Count nodes and nesting depth of a parsed document."""
    stack = [(value, 1)]
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > MAX_NODES:
            raise InputError("document exceeds the node budget")
        if depth > MAX_DEPTH:
            raise InputError("document exceeds the nesting depth budget")
        if isinstance(node, dict):
            for item in node.values():
                stack.append((item, depth + 1))
        elif isinstance(node, list):
            for item in node:
                stack.append((item, depth + 1))


def parse_json_text(text):
    """Parse JSON strictly: no duplicate keys, no NaN/Infinity."""
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_without_duplicates,
            parse_constant=_reject_constant,
            parse_float=_parse_float,
        )
    except DuplicateKeyError:
        raise InputError("duplicate object key in JSON input")
    except NonFiniteNumberError:
        raise InputError("non-finite number in JSON input")
    except RecursionError:
        raise InputError("JSON input nests too deeply")
    except ValueError:
        raise InputError("invalid JSON input")
    _measure(value)
    return value


def load_json_file(path):
    """Read and parse one JSON file under the input budgets."""
    target = Path(path)
    if not target.exists():
        raise InputError("file not found")
    if not target.is_file():
        raise InputError("path is not a regular file")
    try:
        size = target.stat().st_size
    except OSError:
        raise InputError("file cannot be inspected")
    if size > MAX_FILE_BYTES:
        raise InputError("file exceeds the 1 MiB size budget")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise InputError("file is not valid UTF-8")
    except OSError:
        raise InputError("file cannot be read")
    return parse_json_text(text)


# ------------------------------------------------------------- JSON helpers


def json_type_name(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def json_equal(left, right):
    """JSON equality where booleans never equal numbers."""
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if isinstance(left, bool):
        return left is right
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, str) and isinstance(right, str):
        return left == right
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            json_equal(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left.keys()) != set(right.keys()):
            return False
        return all(json_equal(left[key], right[key]) for key in left)
    return False


def value_matches_type(value, name):
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    if name == "integer":
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        return isinstance(value, float) and value.is_integer()
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ------------------------------------------------------------------ patterns

_PATTERN_CACHE = {}


def _uses_unsupported_regex(pattern):
    """Reject regex constructs outside the declared shared subset."""
    for match in re.finditer(r"\(\?", pattern):
        tail = pattern[match.start() + 2:match.start() + 3]
        if tail != ":":
            # Look-around, named group, inline flags, atomic group.
            return True
    if re.search(r"\\[1-9]", pattern):
        # Back references are not part of the shared subset.
        return True
    if re.search(r"[*+?}]\+", pattern):
        # Possessive quantifiers are Python-only.
        return True
    return False


def compile_pattern(pattern):
    """Compile one pattern of the declared subset, or raise SchemaError."""
    if not isinstance(pattern, str):
        raise SchemaError("pattern must be a string")
    if not pattern.startswith("^"):
        raise SchemaError("only start-anchored patterns are supported")
    if _uses_unsupported_regex(pattern):
        raise SchemaError("pattern uses constructs outside the supported subset")
    translated = pattern
    if translated.endswith("$") and not translated.endswith("\\$"):
        # Python's `$` also matches before a trailing newline; JSON Schema
        # expects an absolute end of string, so translate the final anchor.
        translated = translated[:-1] + r"\Z"
    try:
        return re.compile(translated)
    except re.error:
        raise SchemaError("invalid regular expression")


def get_pattern(pattern):
    compiled = _PATTERN_CACHE.get(pattern)
    if compiled is None:
        compiled = compile_pattern(pattern)
        _PATTERN_CACHE[pattern] = compiled
    return compiled


# ------------------------------------------------------------- schema checks


def resolve_ref(root, ref):
    """Resolve a local JSON pointer such as "#/$defs/role"."""
    if not isinstance(ref, str) or not ref.startswith("#"):
        raise SchemaError("only local references are supported")
    pointer = ref[1:]
    if pointer == "":
        return root
    if not pointer.startswith("/"):
        raise SchemaError("unsupported reference pointer")
    node = root
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            if token not in node:
                raise SchemaError("unresolved local reference")
            node = node[token]
        elif isinstance(node, list):
            if not token.isdigit() or int(token) >= len(node):
                raise SchemaError("unresolved local reference")
            node = node[int(token)]
        else:
            raise SchemaError("unresolved local reference")
    return node


def _check_type_keyword(value, path, errors):
    if isinstance(value, list):
        if not value:
            errors.append("path %s: type union must not be empty" % path)
            return
        names = value
    else:
        names = [value]
    seen = set()
    for name in names:
        if not isinstance(name, str):
            errors.append("path %s: type names must be strings" % path)
            return
        if name not in JSON_TYPES:
            errors.append("path %s: unsupported type '%s'" % (path, name))
        if name in seen:
            errors.append("path %s: duplicate type '%s'" % (path, name))
        seen.add(name)


def _check_required_keyword(value, path, errors):
    if not isinstance(value, list):
        errors.append("path %s: required must be an array" % path)
        return
    seen = set()
    for name in value:
        if not isinstance(name, str):
            errors.append("path %s: required entries must be strings" % path)
            return
        if name in seen:
            errors.append("path %s: duplicate required property" % path)
        seen.add(name)


def _check_numeric_keyword(keyword, value, path, errors):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append("path %s: %s must be a number" % (path, keyword))


def _check_count_keyword(keyword, value, path, errors):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append("path %s: %s must be a non-negative integer" % (path, keyword))


def _walk_schema(node, path, errors, registry, edges):
    """Recursively check one schema node and record its reference edges."""
    if not isinstance(node, dict):
        errors.append("path %s: schema must be a JSON object" % path)
        return
    registry[id(node)] = (node, path)
    for key, value in node.items():
        if key in ANNOTATION_KEYWORDS:
            continue
        if key in STRUCTURAL_KEYWORDS:
            if not isinstance(value, dict):
                errors.append("path %s: $defs must be a JSON object" % path)
                continue
            for name, sub in value.items():
                _walk_schema(
                    sub, "%s/$defs/%s" % (path, name), errors, registry, edges
                )
            continue
        if key not in VALIDATION_KEYWORDS:
            errors.append("path %s: unsupported keyword '%s'" % (path, key))
            continue
        if key == "type":
            _check_type_keyword(value, path, errors)
        elif key == "required":
            _check_required_keyword(value, path, errors)
        elif key == "properties":
            if not isinstance(value, dict):
                errors.append("path %s: properties must be a JSON object" % path)
            else:
                for name, sub in value.items():
                    _walk_schema(
                        sub, "%s/properties/%s" % (path, name), errors, registry, edges
                    )
        elif key == "additionalProperties":
            if isinstance(value, dict):
                _walk_schema(
                    value, "%s/additionalProperties" % path, errors, registry, edges
                )
            elif not isinstance(value, bool):
                errors.append(
                    "path %s: additionalProperties must be a boolean or a schema" % path
                )
        elif key == "items":
            if isinstance(value, list):
                errors.append("path %s: tuple-form items is not supported" % path)
            elif isinstance(value, dict):
                _walk_schema(value, "%s/items" % path, errors, registry, edges)
            else:
                errors.append("path %s: items must be a schema" % path)
        elif key == "enum":
            if not isinstance(value, list) or not value:
                errors.append("path %s: enum must be a non-empty array" % path)
        elif key == "const":
            pass
        elif key in ("minimum", "maximum"):
            _check_numeric_keyword(key, value, path, errors)
        elif key in ("minItems", "maxItems"):
            _check_count_keyword(key, value, path, errors)
        elif key == "pattern":
            try:
                compile_pattern(value)
            except SchemaError as exc:
                errors.append("path %s: %s" % (path, exc))

    if "minimum" in node and "maximum" in node:
        low = node.get("minimum")
        high = node.get("maximum")
        if is_number(low) and is_number(high) and low > high:
            errors.append("path %s: minimum is greater than maximum" % path)
    if "minItems" in node and "maxItems" in node:
        low = node.get("minItems")
        high = node.get("maxItems")
        if (
            isinstance(low, int)
            and not isinstance(low, bool)
            and isinstance(high, int)
            and not isinstance(high, bool)
            and low > high
        ):
            errors.append("path %s: minItems is greater than maxItems" % path)


def _detect_cycles(edges, errors):
    """Reject circular local references, including in unused branches."""
    state = {}
    reported = [False]

    def visit(node_id, depth):
        if depth > MAX_REF_CHAIN:
            if not reported[0]:
                reported[0] = True
                errors.append("schema: reference chain is too deep")
            return
        mark = state.get(node_id)
        if mark == 2:
            return
        if mark == 1:
            if not reported[0]:
                reported[0] = True
                errors.append("schema: circular local reference detected")
            return
        state[node_id] = 1
        for target, _path in edges.get(node_id, ()):
            visit(id(target), depth + 1)
        state[node_id] = 2

    for node_id in list(edges):
        visit(node_id, 1)


def check_schema(schema):
    """Return the list of schema problems.

    An empty list means the schema is inside the declared subset and
    internally consistent. Every schema node is checked, including nodes
    that the data never reaches.
    """
    if not isinstance(schema, dict):
        return ["schema root must be a JSON object"]
    errors = []
    registry = {}
    edges = {}
    _walk_schema(schema, "$", errors, registry, edges)

    for node_id, (node, path) in registry.items():
        ref = node.get("$ref")
        if ref is None:
            continue
        try:
            target = resolve_ref(schema, ref)
        except SchemaError as exc:
            errors.append("path %s: %s" % (path, exc))
            continue
        if not isinstance(target, dict):
            errors.append("path %s: reference target is not a schema object" % path)
            continue
        edges.setdefault(node_id, []).append((target, path))

    _detect_cycles(edges, errors)
    return errors


# -------------------------------------------------------- instance validation


def _validate(instance, node, root, path, errors, depth):
    if depth > MAX_VALIDATION_DEPTH:
        errors.append("path %s: validation depth budget exceeded" % path)
        return
    if not isinstance(node, dict):
        return

    if "$ref" in node:
        try:
            target = resolve_ref(root, node["$ref"])
        except SchemaError as exc:
            errors.append("path %s: %s" % (path, exc))
            return
        # The referenced schema and the sibling keywords both apply; the
        # sibling constraints must not be dropped.
        _validate(instance, target, root, path, errors, depth + 1)
        siblings = {
            key: value
            for key, value in node.items()
            if key != "$ref"
            and key not in ANNOTATION_KEYWORDS
            and key not in STRUCTURAL_KEYWORDS
        }
        if siblings:
            _validate(instance, siblings, root, path, errors, depth + 1)
        return

    if "type" in node:
        expected = node["type"]
        names = expected if isinstance(expected, list) else [expected]
        if not any(value_matches_type(instance, name) for name in names):
            errors.append(
                "path %s: expected type %s, got %s"
                % (path, " or ".join(names), json_type_name(instance))
            )
            return

    if "const" in node and not json_equal(instance, node["const"]):
        errors.append("path %s: value does not equal the required const" % path)

    if "enum" in node:
        allowed = node["enum"]
        if not any(json_equal(instance, candidate) for candidate in allowed):
            errors.append("path %s: value is not one of the allowed enum values" % path)

    if isinstance(instance, str) and "pattern" in node:
        if not get_pattern(node["pattern"]).search(instance):
            errors.append("path %s: string does not match the pattern" % path)

    if is_number(instance):
        if "minimum" in node and instance < node["minimum"]:
            errors.append("path %s: number is below the minimum" % path)
        if "maximum" in node and instance > node["maximum"]:
            errors.append("path %s: number is above the maximum" % path)

    if isinstance(instance, list):
        if "minItems" in node and len(instance) < node["minItems"]:
            errors.append("path %s: array has fewer items than minItems" % path)
        if "maxItems" in node and len(instance) > node["maxItems"]:
            errors.append("path %s: array has more items than maxItems" % path)
        item_schema = node.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(instance):
                _validate(
                    item,
                    item_schema,
                    root,
                    "%s[%d]" % (path, index),
                    errors,
                    depth + 1,
                )

    if isinstance(instance, dict):
        for name in node.get("required", ()):
            if name not in instance:
                errors.append("path %s: missing required property '%s'" % (path, name))
        properties = node.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        for name, sub in properties.items():
            if name in instance:
                _validate(
                    instance[name],
                    sub,
                    root,
                    "%s/%s" % (path, name),
                    errors,
                    depth + 1,
                )
        additional = node.get("additionalProperties")
        if additional is not None:
            for name in instance:
                if name in properties:
                    continue
                # The offending key comes from the data, so it is withheld.
                extra_path = "%s/<additional-property>" % path
                if additional is False:
                    errors.append(
                        "path %s: additional property is not allowed" % extra_path
                    )
                elif isinstance(additional, dict):
                    _validate(
                        instance[name],
                        additional,
                        root,
                        extra_path,
                        errors,
                        depth + 1,
                    )


def validate_instance(instance, schema):
    """Return the list of instance problems.

    An empty list means the instance conforms to the (already checked)
    schema.
    """
    errors = []
    _validate(instance, schema, schema, "$", errors, 0)
    if len(errors) > MAX_ERRORS:
        errors = errors[:MAX_ERRORS] + ["path $: additional errors omitted"]
    return errors


# ------------------------------------------------------------------- drivers


def discover_pairs(root):
    """Return the (example, schema) pairs of one Skill root."""
    base = Path(root).expanduser().resolve()
    config = base / "config"
    if not config.is_dir():
        raise InputError("config directory not found under the given root")
    examples = sorted(config.glob("*.example.json"))
    if not examples:
        raise InputError("no example files found in the config directory")
    pairs = []
    for example in examples:
        stem = example.name[: -len(".example.json")]
        schema = config / (stem + ".schema.json")
        if not schema.is_file():
            raise InputError("no schema file for the example '%s'" % stem)
        pairs.append((example, schema))
    return pairs


def validate_pair(example_path, schema_path):
    """Validate one example/schema pair and return a result dict."""
    result = {
        "example": str(example_path),
        "schema": str(schema_path),
        "status": "pass",
        "errors": [],
    }
    try:
        schema = load_json_file(schema_path)
    except InputError as exc:
        result["status"] = "schema_error"
        result["errors"] = [str(exc)]
        return result
    schema_errors = check_schema(schema)
    if schema_errors:
        result["status"] = "schema_error"
        result["errors"] = schema_errors[:MAX_ERRORS]
        return result
    try:
        instance = load_json_file(example_path)
    except InputError as exc:
        result["status"] = "input_error"
        result["errors"] = [str(exc)]
        return result
    errors = validate_instance(instance, schema)
    if errors:
        result["status"] = "instance_error"
        result["errors"] = errors
    return result


def _relative(path, root):
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(path)


def _empty_summary():
    return {
        "pass": 0,
        "instance_error": 0,
        "schema_error": 0,
        "input_error": 0,
        "fail": 0,
    }


def validate_skill(root):
    """Validate every example/schema pair of one Skill root."""
    base = Path(root).expanduser().resolve()
    report = {
        "schema": SCHEMA_ID,
        "root": str(base),
        "pairs": [],
        "summary": _empty_summary(),
    }
    try:
        pairs = discover_pairs(base)
    except InputError as exc:
        report["pairs"].append(
            {
                "example": "",
                "schema": "",
                "status": "input_error",
                "errors": [str(exc)],
            }
        )
        report["summary"]["input_error"] += 1
        report["summary"]["fail"] += 1
        return report
    for example, schema in pairs:
        result = validate_pair(example, schema)
        result["example"] = _relative(example, base)
        result["schema"] = _relative(schema, base)
        report["pairs"].append(result)
        status = result["status"]
        report["summary"][status] += 1
        if status != "pass":
            report["summary"]["fail"] += 1
    return report


# ----------------------------------------------------------------------- CLI


EPILOG = """\
示例:
  python3 scripts/validate_examples.py
  python3 scripts/validate_examples.py --root magpie-optimizer
  python3 scripts/validate_examples.py --example config/policy.example.json \\
      --schema config/policy.schema.json

退出码: 0 = 全部通过；1 = 实例不符合 schema；2 = 用法、文件、JSON 或 schema 错误。
诊断只给 JSON 路径与关键字，不回显实例字段原值。
"""


def build_parser():
    parser = argparse.ArgumentParser(
        prog="validate_examples.py",
        description="离线校验 magpie-optimizer 的示例与 schema（标准库实现）。",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        help="Skill 根目录；默认是本脚本所在 Skill 目录。校验其 config/ 下的全部示例对。",
    )
    parser.add_argument("--example", help="只校验一个示例文件，需要同时给出 --schema。")
    parser.add_argument("--schema", help="只校验一个 schema 文件，需要同时给出 --example。")
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="输出机器可读 JSON 报告。",
    )
    return parser


def default_root():
    return Path(__file__).resolve().parents[1]


def _print_pair(result):
    if result["status"] == "pass":
        print("PASS %s" % (result["example"] or "-"))
        return
    print("FAIL [%s] %s" % (result["status"], result["example"] or "-"))
    for message in result["errors"]:
        print("  - %s" % message)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if bool(args.example) != bool(args.schema):
        print(
            "用法错误：--example 与 --schema 必须同时给出。",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR

    if args.example:
        result = validate_pair(args.example, args.schema)
        report = {
            "schema": SCHEMA_ID,
            "root": "",
            "pairs": [result],
            "summary": _empty_summary(),
        }
        report["summary"][result["status"]] += 1
        if result["status"] != "pass":
            report["summary"]["fail"] += 1
    else:
        root = Path(args.root).expanduser() if args.root else default_root()
        report = validate_skill(root)

    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        for result in report["pairs"]:
            _print_pair(result)
        summary = report["summary"]
        print(
            "共 %d 对：通过 %d，实例不符 %d，schema 错误 %d，输入错误 %d"
            % (
                len(report["pairs"]),
                summary["pass"],
                summary["instance_error"],
                summary["schema_error"],
                summary["input_error"],
            )
        )

    if report["summary"]["schema_error"] or report["summary"]["input_error"]:
        return EXIT_INPUT_ERROR
    if report["summary"]["instance_error"]:
        return EXIT_INSTANCE_ERROR
    return EXIT_OK


if __name__ == "__main__":
    _drop_cached_bytecode()
    try:
        sys.exit(main())
    except InputError as error:
        print("输入错误：%s" % error, file=sys.stderr)
        sys.exit(EXIT_INPUT_ERROR)
    except SchemaError as error:
        print("schema 错误：%s" % error, file=sys.stderr)
        sys.exit(EXIT_INPUT_ERROR)
    except OSError as error:
        print("输入错误：%s" % type(error).__name__, file=sys.stderr)
        sys.exit(EXIT_INPUT_ERROR)
