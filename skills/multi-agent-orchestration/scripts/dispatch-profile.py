#!/usr/bin/env python3
"""Deterministic dispatch intent and receipt-state resolver; never launches workers.

The caller must preserve live harness, native-bridge, budget, scope, authority,
startup and receipt checks in spawn. Supplied observations are explicitly
labelled as supplied, never as runtime reads performed by this module.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

SCHEMA = "multi-agent-orchestration.dispatch-profile.v1"
HERE = Path(__file__).resolve().parent
BACKENDS = ("claude-code", "codex", "codebuddy", "qoder-cn", "zcode", "zcode-cli", "minimax-code", "qwenwork-cn")
ALIASES = {"claude": "claude-code", "claude_code": "claude-code", "mcode": "minimax-code",
           "qoderclicn": "qoder-cn", "workbuddy": "codebuddy"}
STATES = ("draft", "input_accepted", "turn_started", "worker_done", "pm_accepted")
TRANSPORTS = ("auto", "orca-native-supervised", "orca-generic", "direct")
OBS_FIELDS = {"terminal_created", "tui_idle", "composer_text_present", "supervised_spec_injected", "worker_done",
              "delivery_acked", "pm_accepted", "worker_state", "dispatch_status", "terminal_state",
              "permission_mode", "runtime_id", "provider_running_count"}
OBS_ALIASES = {"workerState": "worker_state", "dispatchStatus": "dispatch_status", "terminalState": "terminal_state",
               "runtimeId": "runtime_id", "permissionMode": "permission_mode"}


class Refused(ValueError):
    pass


def need(condition, code):
    if not condition:
        raise Refused(code)


def canonical(value, *, exists=True):
    need(isinstance(value, str) and value.startswith("/") and ".." not in Path(value).parts,
         "absolute_path_required")
    p = Path(value)
    if p.parts[1:2] in (("tmp",), ("var",)):
        p = Path("/private") / p.relative_to("/")
    cursor = Path("/")
    for part in p.parts[1:]:
        cursor /= part
        need(not cursor.is_symlink(), "symlink_path")
    return p.resolve(strict=exists)


def read_json(value):
    path = canonical(str(value))
    s = path.stat()
    need(stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and not s.st_mode & 0o022
         and s.st_size <= 1024 * 1024, "config_untrusted")
    raw = path.read_bytes()
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise Refused("config_json_unknown")
    need(isinstance(result, dict), "config_object_required")
    return result, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


@dataclass(frozen=True)
class ValidatedStartup:
    """Internal API input from the existing command classifier's actual call.

    Construct only in the trusted spawn adapter after resolve_minimax_startup.
    CLI/request JSON has no equivalent verified-startup option.
    """
    mode: str
    source: str


@dataclass(frozen=True)
class ValidatedReceipt:
    next_action: str
    dispatch_status: str
    worker_state: str
    terminal_state: str
    ownership_state: str
    retained_reason: str | None
    durable: bool
    live_status: str
    runtime_id: str
    source_sha256: str


def validate_receipt(raw, expected):
    """Validate a supplied official worker-show receipt against original identity.

    This validates the receipt's structure/bindings, not its live freshness.
    Callers still own reading the exact official runtime and original request.
    No capability, business prompt, screen or nextAction argv is copied out.
    """
    required = {"runtime_id", "dispatch_id", "run_id", "task_id", "worktree_id", "terminal_handle"}
    need(isinstance(expected, dict) and set(expected) == required
         and all(isinstance(x, str) and bool(x) for x in expected.values()), "receipt_expected_identity_incomplete")
    need(isinstance(raw, dict) and raw.get("ok") is True
         and raw.get("_meta", {}).get("runtimeId") == expected["runtime_id"], "receipt_runtime_mismatch")
    result = raw.get("result")
    need(isinstance(result, dict), "receipt_result_unknown")
    dispatch, worker, projection, resource = (result.get(k) for k in ("dispatch", "worker", "projection", "terminalResource"))
    need(all(isinstance(x, dict) for x in (dispatch, worker, projection, resource)), "receipt_sections_unknown")
    def bind(obj, aliases, value):
        present = [obj[k] for k in aliases if k in obj]
        need(bool(present) and all(type(x) is str and x == value for x in present), "receipt_identity_alias_mismatch")
    bind(dispatch, ("id", "dispatchId", "dispatch_id"), expected["dispatch_id"])
    bind(dispatch, ("runId", "run_id"), expected["run_id"])
    bind(dispatch, ("taskId", "task_id"), expected["task_id"])
    bind(worker, ("dispatchId", "dispatch_id"), expected["dispatch_id"])
    bind(worker, ("worktreeId", "worktree_id"), expected["worktree_id"])
    bind(worker, ("agentTerminalHandle", "agent_terminal_handle"), expected["terminal_handle"])
    bind(projection, ("id", "dispatchId", "dispatch_id"), expected["dispatch_id"])
    bind(projection, ("runId", "run_id"), expected["run_id"])
    bind(projection, ("taskId", "task_id"), expected["task_id"])
    bind(resource, ("originDispatchId", "origin_dispatch_id"), expected["dispatch_id"])
    bind(resource, ("ownerDispatchId", "owner_dispatch_id"), expected["dispatch_id"])
    bind(resource, ("worktreeId", "worktree_id"), expected["worktree_id"])
    bind(resource, ("terminalHandle", "terminal_handle"), expected["terminal_handle"])
    evidence = projection.get("evidence")
    action = projection.get("nextAction")
    need(isinstance(evidence, dict) and type(evidence.get("durable")) is bool
         and isinstance(evidence.get("liveStatus"), str)
         and isinstance(action, dict) and isinstance(action.get("kind"), str) and bool(action["kind"]),
         "receipt_projection_unknown")
    for value in (dispatch.get("status"), worker.get("state"), resource.get("releaseState"), resource.get("ownershipState")):
        need(isinstance(value, str) and bool(value), "receipt_state_unknown")
    if dispatch["status"] == "completed" or worker["state"] in {"succeeded", "failed", "cancelled"}:
        need(action["kind"] not in {"send_task", "submit_task", "submit_task_once", "spawn", "spawn_worker", "restart_worker"},
             "receipt_completed_submission_conflict")
    if resource["ownershipState"] == "user_owned" or resource["releaseState"] == "retained":
        need(action["kind"] not in {"close_terminal", "auto_close", "terminal_close", "force_release"},
             "receipt_retained_close_conflict")
    return ValidatedReceipt(action["kind"], dispatch["status"], worker["state"], resource["releaseState"],
                            resource["ownershipState"], resource.get("retainedReason"), evidence["durable"],
                            evidence["liveStatus"], expected["runtime_id"],
                            hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()).hexdigest())


def observations(value):
    need(isinstance(value, dict), "observations_object_required")
    result = {}
    for name, item in value.items():
        key = OBS_ALIASES.get(name, name)
        need(key in OBS_FIELDS, "observation_field_unknown")
        need(key not in result or result[key] == item, "observation_alias_conflict")
        if key in {"terminal_created", "tui_idle", "composer_text_present", "supervised_spec_injected",
                   "worker_done", "delivery_acked", "pm_accepted"}:
            need(isinstance(item, bool), "observation_type_invalid")
        elif key == "provider_running_count":
            need(item is None or type(item) is int and item >= 0, "observation_type_invalid")
        else:
            need(item is None or isinstance(item, str) and bool(item), "observation_type_invalid")
        result[key] = item
    return result


def personal_config(path):
    if path is None:
        return {}, {"path": None, "sha256": None, "status": "absent"}
    resolved = canonical(str(path), exists=False)
    if not resolved.exists():
        return {}, {"path": str(resolved), "sha256": None, "status": "absent"}
    config, source = read_json(str(resolved))
    need(str(config.get("_schema_version")) in {"1.0", "1.1", "1.2", "1.3"}, "personal_version_unknown")
    profiles = config.get("dispatch_profiles", {})
    need(isinstance(profiles, dict) and set(profiles) <= {"zcode-cli"}, "personal_profile_unknown")
    zcode = profiles.get("zcode-cli", {})
    need(isinstance(zcode, dict) and set(zcode) <= {"native_bridge"}, "personal_profile_unknown")
    bridge = zcode.get("native_bridge", {})
    need(isinstance(bridge, dict) and set(bridge) <= {"enabled", "requests_root"}, "native_bridge_config_unknown")
    if bridge:
        need(type(bridge.get("enabled")) is bool, "native_bridge_enabled_unknown")
        if "requests_root" in bridge:
            need(isinstance(bridge["requests_root"], str) and bool(bridge["requests_root"]), "native_bridge_path_invalid")
        need(not bridge["enabled"] or bool(bridge.get("requests_root")), "native_bridge_path_required")
    source["status"] = "read"
    return config, source


def concurrency(config, source, backend):
    value = config.get("concurrency")
    if value is None:
        return {"cap": None, "source": source, "key": None, "slot_lease_required": None,
                "runtime_running_count": None, "meaning": "unknown; provider lease preflight required"}
    need(isinstance(value, dict) and isinstance(value.get("per_backend", {}), dict), "concurrency_config_unknown")
    per = value.get("per_backend", {})
    if backend in per:
        cap, key = per[backend], "concurrency.per_backend." + backend
    else:
        cap, key = value.get("max_per_provider"), "concurrency.max_per_provider"
    need(type(cap) is int and cap >= 0, "concurrency_cap_invalid")
    return {"cap": cap, "source": source, "key": key, "slot_lease_required": cap != 0,
            "runtime_running_count": None, "meaning": "0 skips mechanical slot lease; resource/budget gates still required" if cap == 0
            else "configured slot cap; actual occupancy/budget requires live preflight"}


def next_action(state, obs, supervised, batch):
    # Durable result evidence takes precedence over stale composer/draft labels.
    # This remains a decision over supplied fields, not a runtime observation.
    if state == "pm_accepted" or obs.get("pm_accepted"):
        if obs.get("terminal_state") == "released":
            return "settled" if obs.get("delivery_acked") else "ack_delivery"
        if obs.get("terminal_state") == "retained":
            return "record_retention_then_ack"
        return "release_worker" if supervised else "settle_session"
    if state == "worker_done" or obs.get("worker_done"):
        return "pm_verify_result"
    if obs.get("worker_state") in {"succeeded", "failed", "cancelled"} and obs.get("dispatch_status") == "completed":
        return "inspect_completion_evidence"
    if state == "turn_started":
        return "observe_worker_done" if supervised else "observe_completion"
    if state == "input_accepted":
        return "observe_turn_start"
    if obs.get("supervised_spec_injected"):
        return "inspect_dispatch_submission"
    if obs.get("composer_text_present"):
        return "inspect_existing_input"
    if obs.get("terminal_created"):
        if batch:
            return "inspect_batch_start"
        if supervised:
            return "inspect_dispatch_submission"
        return "submit_task_once" if obs.get("tui_idle") else "wait_input_ready"
    return "spawn_supervised_once" if supervised else "spawn_batch_once" if batch else "spawn_terminal_once"


def resolve(request, *, skill_root=None, policy_path=None, personal_path=None, validated_startup=None, validated_receipt=None):
    need(isinstance(request, dict), "request_object_required")
    allowed = {"backend", "execution_mode", "transport", "explicit_selection", "harness_chain", "supervised",
               "startup_mode", "requested_permission", "input_state", "observations"}
    need(set(request) <= allowed, "request_field_unknown")
    root = canonical(str(skill_root or HERE.parent))
    policy, policy_source = read_json(str(policy_path or root / "config" / "harness-backend-policy.json"))
    need(policy.get("schema") == "multi-agent-orchestration.harness-backend-policy.v1"
         and policy.get("policy") == "deny_by_default", "backend_policy_unknown")
    chain = request.get("harness_chain")
    need(isinstance(chain, list) and len(chain) > 0 and all(isinstance(x, str) for x in chain), "harness_chain_required")
    authorized = None
    for host in chain:
        backends = policy.get("hosts", {}).get(host)
        need(isinstance(backends, list) and bool(backends) and all(isinstance(x, str) for x in backends), "harness_policy_denied")
        authorized = set(backends) if authorized is None else authorized & set(backends)
    selection = policy.get("dispatch_selection", {})
    defaults = selection.get("default_backends")
    optional = selection.get("explicit_only_backends")
    need(isinstance(defaults, list) and defaults and isinstance(optional, list), "selection_policy_unknown")
    raw_backend = request.get("backend")
    need(raw_backend is None or isinstance(raw_backend, str), "backend_type_invalid")
    backend = ALIASES.get(raw_backend, raw_backend) if raw_backend is not None else next((x for x in defaults if x in authorized), None)
    need(backend in BACKENDS and backend in authorized, "backend_not_authorized")
    explicit = request.get("explicit_selection", False)
    need(type(explicit) is bool, "explicit_selection_invalid")
    need(backend not in optional or explicit is True, "optional_backend_requires_explicit_selection")
    mode = request.get("execution_mode", "interactive")
    transport = request.get("transport", "auto")
    need(mode in {"interactive", "batch"} and transport in TRANSPORTS, "mode_or_transport_unknown")
    supervised = request.get("supervised", False)
    need(type(supervised) is bool, "supervised_type_invalid")
    state = request.get("input_state", "draft")
    need(state in STATES, "input_state_unknown")
    obs = observations(request.get("observations", {}))
    personal, personal_source = personal_config(personal_path or root / "config" / "orchestration-personal.json")
    bridge = personal.get("dispatch_profiles", {}).get("zcode-cli", {}).get("native_bridge", {})
    bridge_path = None
    native = backend == "zcode-cli" and transport in {"auto", "orca-native-supervised"}
    if native:
        need(mode == "interactive", "zcode_native_requires_interactive")
        need(bridge.get("enabled") is True and bridge.get("requests_root"), "zcode_native_bridge_config_required")
        bridge_path = canonical(bridge["requests_root"])
        s = bridge_path.stat()
        need(bridge_path.is_dir() and s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == 0o700,
             "native_requests_directory_untrusted")
        supervised = True
        transport = "orca-native-supervised"
    elif transport == "orca-native-supervised":
        raise Refused("native_transport_backend_mismatch")
    elif transport == "auto":
        transport = "orca-generic"
    need(not (transport == "direct" and supervised), "direct_supervised_conflict")
    need(not (backend == "zcode-cli" and mode == "batch"), "zcode_cli_batch_not_supported_by_dispatch_contract")
    startup_requested = request.get("startup_mode", mode)
    need(startup_requested in {"interactive", "batch"} and startup_requested == mode, "startup_mode_contradiction")
    startup = {"requested": startup_requested, "validated_mode": None, "validated_source": None,
               "requires_classifier_validation": backend == "minimax-code"}
    if validated_startup is not None:
        need(backend == "minimax-code" and isinstance(validated_startup, ValidatedStartup)
             and validated_startup.mode == mode and bool(validated_startup.source), "validated_startup_contradiction")
        startup.update(validated_mode=validated_startup.mode, validated_source=validated_startup.source,
                       requires_classifier_validation=False)
    need(not (backend == "minimax-code" and mode == "batch" and supervised), "minimax_batch_supervised_conflict")
    flags = ["--worker-backend", backend]
    if transport == "direct":
        flags += ["--no-orca-mode"]
    if supervised:
        flags += ["--orca-supervised"]
    if native:
        flags += ["--orca-zcode-native-requests", str(bridge_path)]
    requested_permission = request.get("requested_permission")
    need(requested_permission is None or isinstance(requested_permission, str) and bool(requested_permission), "permission_request_invalid")
    permission_source = "request" if requested_permission is not None else "renderer_default"
    if backend == "zcode-cli":
        requested_permission = requested_permission or "yolo"
        need(requested_permission in {"build", "edit", "plan", "yolo"}, "zcode_permission_invalid")
        native_flags = ["--mode", requested_permission]
    elif backend == "minimax-code":
        requested_permission = requested_permission or "full"
        need(requested_permission in {"smart", "full", "off"} if mode == "batch" else requested_permission in {"full", "auto", "default"},
             "minimax_permission_invalid")
        native_flags = ["exec", "--permission", requested_permission] if mode == "batch" else []
        if mode == "interactive":
            permission_source = "worker_scoped_configuration_required"
    else:
        native_flags = []  # Renderer remains argv authority for other supported backends.
    batch = mode == "batch"
    input_source = "command_bootstrap" if batch else "supervised_task_spec" if supervised else "terminal_submit"
    action = next_action(state, obs, supervised, batch)
    if backend == "minimax-code" and startup["requires_classifier_validation"] and state == "draft" and not obs:
        action = "validate_command_startup"
    receipt_projection = None
    if validated_receipt is not None:
        need(isinstance(validated_receipt, ValidatedReceipt), "receipt_adapter_validation_required")
        if "runtime_id" in obs:
            need(obs["runtime_id"] == validated_receipt.runtime_id, "receipt_observation_runtime_conflict")
        if "worker_state" in obs:
            need(obs["worker_state"] == validated_receipt.worker_state, "receipt_observation_state_conflict")
        if "dispatch_status" in obs:
            need(obs["dispatch_status"] == validated_receipt.dispatch_status, "receipt_observation_state_conflict")
        action = validated_receipt.next_action
        receipt_projection = {"dispatch_status": validated_receipt.dispatch_status,
            "worker_state": validated_receipt.worker_state, "terminal_state": validated_receipt.terminal_state,
            "ownership_state": validated_receipt.ownership_state, "retained_reason": validated_receipt.retained_reason,
            "durable": validated_receipt.durable, "live_status": validated_receipt.live_status,
            "fresh_running_activity_verified": False, "source": "supplied_validated_official_receipt",
            "canonical_receipt_sha256": validated_receipt.source_sha256}
    caps = concurrency(personal, personal_source, backend)
    caps["supplied_running_count"] = obs.get("provider_running_count")
    return {"ok": True, "schema": SCHEMA, "profile": backend + ":" + mode + ":" + transport,
            "backend": backend, "execution_mode": mode, "transport": transport,
            "selection": {"explicit": explicit, "source": "request" if raw_backend is not None else "policy_default",
                          "policy": policy_source, "harness_chain": chain, "requires_live_harness_preflight": True},
            "configuration": {"personal": personal_source, "concurrency": caps,
                              "native_requests_directory_verified": native, "orca_launcher_configuration_observed": None},
            "startup": startup, "required_spawn_flags": flags, "required_native_flags": native_flags,
            "permission": {"requested": requested_permission, "requested_source": permission_source,
                           "observed": obs.get("permission_mode"), "observed_source": "supplied_observation" if "permission_mode" in obs else None},
            "task_input": {"source": input_source, "state": state, "requested_state": state, "observation_origin": "supplied_fields",
                           "supervised_spec_injected": obs.get("supervised_spec_injected"),
                           "may_submit_second_input": False},
            "completion_authority": "worker_done_delivery_then_pm_acceptance" if supervised else "session_result_and_verification_then_pm_acceptance",
            "next_action": {"kind": action, "authority": "orca_projection" if receipt_projection else "initial_intent_only",
                            "original_receipt_required": receipt_projection is not None,
                            "requires_live_receipt_validation": True},
            "official_projection": receipt_projection,
            "runtime": {"observed_id": validated_receipt.runtime_id if receipt_projection else obs.get("runtime_id"),
                        "source": "supplied_validated_official_receipt" if receipt_projection else "supplied_observation" if "runtime_id" in obs else None,
                        "live_read_performed": False},
            "preflight_required": ["value", "quota", "memory", "provider_lease", "scope", "authority", "isolation"]
                + (["native_bridge"] if native else []), "dispatch_executed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-file")
    parser.add_argument("--skill-root")
    parser.add_argument("--policy")
    parser.add_argument("--personal-config")
    parser.add_argument("--receipt-file")
    parser.add_argument("--expected-identity-file")
    args = parser.parse_args()
    try:
        request = read_json(args.request_file)[0] if args.request_file else json.load(sys.stdin)
        need(bool(args.receipt_file) == bool(args.expected_identity_file), "receipt_and_expected_identity_required")
        receipt = validate_receipt(read_json(args.receipt_file)[0], read_json(args.expected_identity_file)[0]) if args.receipt_file else None
        result = resolve(request, validated_receipt=receipt, skill_root=args.skill_root, policy_path=args.policy, personal_path=args.personal_config)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Refused, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        error = str(exc) if isinstance(exc, Refused) else "dispatch_profile_input_unknown"
        print(json.dumps({"ok": False, "error": error, "dispatch_executed": False}), file=sys.stderr)
        return 64


if __name__ == "__main__":
    raise SystemExit(main())
