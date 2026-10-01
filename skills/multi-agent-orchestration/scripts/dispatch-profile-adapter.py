#!/usr/bin/env python3
"""Resolve real validated COMMAND into the shared dispatch-profile intent.

No model, runtime, authentication or worker launch occurs. Existing spawn
harness, scope, budget and receipt fencing remain mandatory consumers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types

HERE = Path(__file__).resolve().parent


class Refused(ValueError):
    pass


def need(condition, error):
    if not condition:
        raise Refused(error)


def module_from_source(path, name):
    # Fixed product filenames only, executed from the checked byte buffer.
    path = Path(path)
    need(not path.is_symlink(), "adapter_source_symlink")
    s = path.stat()
    need(stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and not s.st_mode & 0o022
         and s.st_size <= 1024 * 1024, "adapter_source_untrusted")
    raw = path.read_bytes()
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def argument_permission(argv, flag, allowed, start=1, value_options=()):
    """Read already-resolved native argv, never parse Shell or bootstrap text."""
    values = []
    index = start
    while index < len(argv):
        item = argv[index]
        if item == "--":
            break
        if item == flag:
            need(index + 1 < len(argv), "native_permission_value_missing")
            values.append(argv[index + 1])
            index += 2
            continue
        if item.startswith(flag + "="):
            values.append(item.split("=", 1)[1])
        elif item in value_options:
            need(index + 1 < len(argv), "native_option_value_missing")
            index += 2
            continue
        elif item.startswith("-") and "=" not in item:
            # Unknown option arity prevents proving subsequent tokens are flags.
            return None
        index += 1
    need(not values or all(value in allowed for value in values), "native_permission_value_unknown")
    need(not values or len(set(values)) == 1, "native_permission_argv_conflict")
    return values[0] if values else None


def adapt(request, command, *, skill_root=None, policy_path=None, personal_path=None,
          official_receipt=None, expected_identity=None):
    need(isinstance(request, dict) and isinstance(command, str) and bool(command.strip()), "adapter_request_or_command_invalid")
    profile, profile_source = module_from_source(HERE / "dispatch-profile.py", "mao_dispatch_profile")
    classifier, classifier_source = module_from_source(HERE / "validate-worker-command.py", "mao_worker_command")
    raw_backend = request.get("backend")
    need(isinstance(raw_backend, str), "adapter_effective_backend_required")
    backend = profile.ALIASES.get(raw_backend, raw_backend)
    planned = dict(request, backend=backend)
    actual_permission = None
    startup = None
    argv = []
    try:
        if backend == "minimax-code":
            need(callable(getattr(classifier, "resolve_minimax_startup", None)), "minimax_classifier_unavailable")
            mode = classifier.resolve_minimax_startup(command, require_input=True)
            need(mode in {"interactive", "batch"}, "classifier_mode_unknown")
            if "execution_mode" in request:
                need(request["execution_mode"] == mode, "requested_mode_command_conflict")
            planned["execution_mode"] = mode
            planned["startup_mode"] = mode
            startup = profile.ValidatedStartup(mode, "resolve_minimax_startup:" + classifier_source["sha256"])
        classifier.validate_safe_command_substitutions(command)
        actual = classifier.command_backend(classifier.split_words(command, shell_body=True), expected=backend,
            trusted_claude_wrapper=str(HERE / "claude-provider-env.sh"),
            trusted_zcode_driver=str(HERE / "zcode-worker-driver.py"), shell_body=True, resolved_argv=argv)
        need(actual == backend, "adapter_backend_command_conflict")
        if backend == "zcode-cli":
            need(not any(x == "--prompt" or x.startswith("--prompt=") or x == "--headless" or x.startswith("--headless=") for x in argv[1:]),
                 "zcode_headless_dispatch_forbidden")
            actual_permission = argument_permission(argv, "--mode", {"build", "edit", "plan", "yolo"})
        elif backend == "minimax-code" and planned["execution_mode"] == "batch":
            positions = []
            need(classifier.minimax_startup_mode(argv, positions) == "batch" and len(positions) == 1,
                 "resolved_argv_startup_conflict")
            actual_permission = argument_permission(argv, "--permission", {"smart", "full", "off"}, positions[0] + 1,
                # These are the currently validated exec value options, not a
                # second Shell parser/startup classifier. Unknown arity stays unknown.
                {"--input", "--input-format", "--cwd", "--file", "--model", "--effort", "--prompt-mode", "--session",
                 "--config", "--timeout", "--max-steps", "--output-format", "--diagnostics-dir", "--output-schema", "-o", "--output-last-message"})
    except classifier.ValidationError:
        # Never echo COMMAND/bootstrap/prompt in error diagnostics.
        raise Refused("existing_command_validator_refused")
    if actual_permission is not None:
        if request.get("requested_permission") is not None:
            need(request["requested_permission"] == actual_permission, "requested_permission_command_conflict")
        planned["requested_permission"] = actual_permission
    need((official_receipt is None) == (expected_identity is None), "adapter_receipt_identity_pair_required")
    receipt = profile.validate_receipt(official_receipt, expected_identity) if official_receipt is not None else None
    result = profile.resolve(planned, skill_root=skill_root, policy_path=policy_path, personal_path=personal_path,
                             validated_startup=startup, validated_receipt=receipt)
    result["permission"]["command_actual"] = actual_permission
    result["permission"]["command_actual_source"] = "validated_resolved_argv" if actual_permission is not None else None
    if actual_permission is not None:
        result["permission"]["requested_source"] = "actual_command_argv"
    elif request.get("requested_permission") is None and backend != "minimax-code":
        result["permission"]["requested_source"] = "dispatch_intent_default"
    result["adapter"] = {"command_sha256": hashlib.sha256(command.encode()).hexdigest(),
                         "command_validator": classifier_source, "profile_source": profile_source,
                         "resolved_backend": backend, "model_executed": False,
                         "command_execution_verified": False}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file")
    parser.add_argument("--skill-root")
    parser.add_argument("--policy")
    parser.add_argument("--personal-config")
    parser.add_argument("--receipt-file")
    parser.add_argument("--expected-identity-file")
    args = parser.parse_args()
    try:
        profile, _ = module_from_source(HERE / "dispatch-profile.py", "mao_adapter_input")
        value = profile.read_json(args.input_file)[0] if args.input_file else json.load(sys.stdin)
        need(isinstance(value, dict) and set(value) == {"request", "command"}, "adapter_input_unknown")
        need(bool(args.receipt_file) == bool(args.expected_identity_file), "adapter_receipt_identity_pair_required")
        raw = profile.read_json(args.receipt_file)[0] if args.receipt_file else None
        expected = profile.read_json(args.expected_identity_file)[0] if args.expected_identity_file else None
        result = adapt(value["request"], value["command"], skill_root=args.skill_root, policy_path=args.policy,
                       personal_path=args.personal_config, official_receipt=raw, expected_identity=expected)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Refused, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        code = str(exc) if isinstance(exc, Refused) or type(exc).__name__ == "Refused" else "adapter_input_unavailable"
        print(json.dumps({"ok": False, "error": code, "dispatch_executed": False}), file=sys.stderr)
        return 64


if __name__ == "__main__":
    raise SystemExit(main())
