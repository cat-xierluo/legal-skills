#!/usr/bin/env python3
"""Validate a private Magpie route-design document without model requests."""

import argparse
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import validate_examples


SCHEMA = "magpie-route-design.v1"
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d$")


class DesignError(Exception):
    """Input cannot be interpreted as a route design."""


def load_json(path):
    target = Path(path)
    try:
        return validate_examples.load_json_file(target)
    except Exception as error:
        # The shared loader maps I/O, JSON and budget failures to InputError.
        raise DesignError("InputError") from error


def _is_group_ref(value):
    return isinstance(value, str) and value.startswith("group/")


def _provider_key(value):
    if not isinstance(value, str) or "/" not in value or _is_group_ref(value):
        return None
    return value.split("/", 1)[0]


def _leaf_providers(member, groups_by_id, seen=None):
    seen = seen or frozenset()
    if member in seen:
        return set()
    if not _is_group_ref(member):
        key = _provider_key(member)
        return {key} if key else set()
    group = groups_by_id.get(member)
    if group is None:
        return set()
    next_seen = seen | {member}
    result = set()
    for child in group.get("members", []):
        result.update(_leaf_providers(child, groups_by_id, next_seen))
    return result


def validate_design(design):
    """Return (errors, warnings); messages are stable codes, never local IDs."""
    errors = []
    warnings = []
    if not isinstance(design, dict) or design.get("schema") != SCHEMA:
        return ["design_schema"], warnings
    groups = design.get("groups")
    if not isinstance(groups, list) or not groups:
        return ["design_groups_required"], warnings

    groups_by_id = {}
    for group in groups:
        if not isinstance(group, dict):
            errors.append("group_shape")
            continue
        gid = group.get("id")
        if not isinstance(gid, str) or not gid:
            errors.append("group_id_invalid")
            continue
        if gid in groups_by_id:
            errors.append("group_id_duplicate")
            continue
        groups_by_id[gid] = group

    entries = [g for g in groups_by_id.values() if g.get("role") == "entry"]
    if len(entries) > 1:
        errors.append("entry_group_duplicate")
    referenced = {m for g in groups_by_id.values()
                  for m in g.get("members", []) if _is_group_ref(m)}
    if referenced and len(entries) != 1:
        errors.append("entry_group_required_for_nested_design")

    referenced_targets = set()
    for group in groups_by_id.values():
        gid = group.get("id")
        members = group.get("members")
        if not isinstance(members, list) or not members:
            errors.append("group_members_required")
            continue
        string_members = [member for member in members if isinstance(member, str)]
        if len(string_members) != len(members):
            errors.append("group_member_invalid")
        if len(string_members) != len(set(string_members)):
            errors.append("group_members_duplicate")
        for member in members:
            if not isinstance(member, str) or not member:
                errors.append("group_member_invalid")
                continue
            if not _is_group_ref(member):
                continue
            if member == gid:
                errors.append("nested_group_self_reference")
            target = groups_by_id.get(member)
            if target is None:
                errors.append("nested_group_unknown")
            else:
                referenced_targets.add(member)

    # A nested path must terminate and stay within eight group references.
    def visit(member, chain, depth):
        if not _is_group_ref(member):
            return
        if member in chain:
            errors.append("nested_group_cycle")
            return
        group = groups_by_id.get(member)
        if group is None:
            return
        for child in group.get("members", []):
            if isinstance(child, str):
                if _is_group_ref(child) and depth >= 8:
                    errors.append("nested_group_depth")
                    continue
                visit(child, chain | {member}, depth + (1 if _is_group_ref(child) else 0))

    for gid in groups_by_id:
        visit(gid, frozenset(), 0)

    for group in groups_by_id.values():
        gid = group.get("id")
        raw_members = group.get("members", [])
        members = {member for member in raw_members if isinstance(member, str)}
        if group.get("routing") != "order" and gid in referenced_targets:
            warnings.append("nested_role_routing_not_order")
        if group.get("effort") == "auto" and not group.get("classifier"):
            errors.append("auto_effort_requires_classifier")

        selections = group.get("selection_rules", [])
        pauses = group.get("pause_rules", [])
        if not isinstance(selections, list) or not isinstance(pauses, list):
            errors.append("design_rule_shape")
            continue
        for index, rule in enumerate(selections):
            if not isinstance(rule, dict):
                errors.append("selection_rule_shape")
                continue
            if rule.get("use") not in members:
                errors.append("selection_rule_target_missing")
            has_condition = bool(rule.get("intent") or rule.get("compact"))
            if not has_condition:
                errors.append("selection_rule_condition_missing")
            if rule.get("compact") and index != 0:
                warnings.append("compact_rule_not_first")
            if rule.get("intent") and not group.get("classifier"):
                errors.append("intent_rule_requires_classifier")
            if "intent" in rule and "not " not in str(rule.get("intent", "")).lower():
                warnings.append("intent_rule_negation_missing")
        for rule in pauses:
            if not isinstance(rule, dict) or not isinstance(rule.get("pause"), str) or rule.get("pause") not in members:
                errors.append("pause_rule_target_missing")
                continue
            if not isinstance(rule.get("time"), str) or not TIME_RE.fullmatch(rule["time"]):
                errors.append("pause_rule_time_invalid")

        # Provider diversity is a capacity warning, not a hard error: accounts
        # and quota pools, not provider names alone, determine real capacity.
        if gid in referenced_targets:
            providers = _leaf_providers(gid, groups_by_id)
            if len(providers) < 2:
                warnings.append("role_provider_diversity_insufficient")

    accounts = design.get("accounts", [])
    if not isinstance(accounts, list):
        errors.append("accounts_shape")
    else:
        seen_providers = set()
        for account in accounts:
            if not isinstance(account, dict):
                errors.append("account_shape")
                continue
            provider = account.get("provider")
            if not isinstance(provider, str) or not provider:
                errors.append("account_provider_invalid")
            elif provider in seen_providers:
                errors.append("account_provider_duplicate")
            else:
                seen_providers.add(provider)

    return sorted(set(errors)), sorted(set(warnings))


def save_private(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
    os.chmod(str(target), 0o600)


def validate_file(design_path, schema_path):
    design = load_json(design_path)
    schema = load_json(schema_path)
    schema_errors = validate_examples.check_schema(schema)
    instance_errors = []
    if not schema_errors:
        instance_errors = validate_examples.validate_instance(design, schema)
    semantic_errors, warnings = validate_design(design)
    errors = sorted(set(schema_errors + instance_errors + semantic_errors))
    return design, errors, warnings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate"])
    parser.add_argument("--design", required=True)
    parser.add_argument("--schema", default=str(SCRIPT_DIR.parent / "config" / "route-policy.schema.json"))
    parser.add_argument("--output")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        _, errors, warnings = validate_file(args.design, args.schema)
    except DesignError as error:
        print(json.dumps({"status": "REFUSED", "reason": str(error)}), file=sys.stderr)
        return 2
    failed = bool(errors) or (args.strict and warnings)
    result = {
        "schema": "magpie-route-design-validation.v1",
        "status": "FAILED" if failed else "PASSED",
        "errors": errors,
        "warnings": warnings,
    }
    if args.output:
        save_private(args.output, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
