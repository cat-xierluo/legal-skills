#!/usr/bin/env python3
"""Actual CLI/API consumers of dispatch profiles, without live dispatch/model calls."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shlex
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("profiles", HERE / "dispatch-profile.py")
p = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = p
spec.loader.exec_module(p)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mao-dispatch-profile-")
        self.root = Path(self.temp.name).resolve()
        self.requests = self.root / "native-requests"
        self.requests.mkdir(mode=0o700)
        self.personal = self.root / "orchestration-personal.json"
        self.config = {"_schema_version": "1.3", "concurrency": {"max_per_provider": 3,
            "per_backend": {"claude-code": 10, "zcode-cli": 0}},
            "dispatch_profiles": {"zcode-cli": {"native_bridge": {"enabled": True, "requests_root": str(self.requests)}}}}
        self.save()
        self.request = {"backend": "zcode-cli", "explicit_selection": True, "harness_chain": ["codex"],
                        "execution_mode": "interactive"}
        self.expected = {"runtime_id": "runtime-fixture", "dispatch_id": "ctx-fixture", "run_id": "run-fixture",
            "task_id": "task-fixture", "worktree_id": "repo::/isolated/fixture", "terminal_handle": "term-fixture"}
        # Exact normalized field combination of the real retained/stale receipt.
        # Identities below are invented fixture identities. No screen, business
        # text, capability, actual task ID or private original argv is copied.
        self.receipt = {"ok": True, "_meta": {"runtimeId": "runtime-fixture"}, "result": {
            "dispatch": {"id": "ctx-fixture", "runId": "run-fixture", "taskId": "task-fixture",
                         "task_id": "task-fixture", "status": "completed"},
            "worker": {"dispatchId": "ctx-fixture", "state": "succeeded", "stage": "settled",
                       "worktreeId": "repo::/isolated/fixture", "agentTerminalHandle": "term-fixture"},
            "projection": {"id": "ctx-fixture", "dispatchId": "ctx-fixture", "runId": "run-fixture",
                "taskId": "task-fixture", "outcome": "succeeded", "evidence": {"durable": True, "liveStatus": "stale"},
                "nextAction": {"kind": "none", "argv": []}},
            "terminalResource": {"originDispatchId": "ctx-fixture", "ownerDispatchId": "ctx-fixture",
                "worktreeId": "repo::/isolated/fixture", "terminalHandle": "term-fixture", "ownershipState": "user_owned",
                "releaseState": "retained", "retainedReason": "user_takeover"}}}

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        self.personal.write_text(json.dumps(self.config))
        self.personal.chmod(0o600)

    def resolve(self, request=None, **kwargs):
        return p.resolve(request or self.request, personal_path=str(self.personal), **kwargs)

    def cli(self, request=None, receipt=None):
        argv = [sys.executable, "-B", str(HERE / "dispatch-profile.py"), "--personal-config", str(self.personal)]
        if receipt is not None:
            for name, data in (("receipt", receipt), ("expected", self.expected)):
                file = self.root / (name + ".json")
                file.write_text(json.dumps(data));file.chmod(0o600)
                argv += ["--receipt-file" if name == "receipt" else "--expected-identity-file", str(file)]
        return subprocess.run(argv, input=json.dumps(request or self.request), capture_output=True, text=True)

    def refused(self, action, error):
        with self.assertRaisesRegex(p.Refused, error):
            action()

    def minimax(self, mode, **overrides):
        return dict(backend="minimax-code", explicit_selection=True, harness_chain=["codex"], execution_mode=mode, **overrides)

    def test_deterministic_same_inputs_and_unchanged_configuration(self):
        before = self.personal.read_bytes()
        first, second = self.resolve(), self.resolve()
        self.assertEqual(first, second)
        self.assertEqual(self.personal.read_bytes(), before)
        self.assertEqual(first["configuration"]["personal"]["path"], str(self.personal))
        self.assertEqual(first["configuration"]["personal"]["sha256"], hashlib.sha256(before).hexdigest())

    def test_actual_cli_restores_missing_native_flags(self):
        before = hashlib.sha256(self.personal.read_bytes()).hexdigest()
        result = self.cli()  # Old caller intentionally omits --orca-supervised/native requests.
        self.assertEqual(result.returncode, 0, result.stderr)
        profile = json.loads(result.stdout)
        self.assertEqual(profile["transport"], "orca-native-supervised")
        flags = profile["required_spawn_flags"]
        self.assertIn("--orca-supervised", flags)
        self.assertEqual(flags[flags.index("--orca-zcode-native-requests") + 1], str(self.requests))
        self.assertEqual(profile["required_native_flags"], ["--mode", "yolo"])
        self.assertEqual(profile["next_action"]["kind"], "spawn_supervised_once")
        self.assertIsNone(profile["configuration"]["orca_launcher_configuration_observed"])
        self.assertIsNone(profile["runtime"]["observed_id"])
        self.assertEqual(hashlib.sha256(self.personal.read_bytes()).hexdigest(), before)
        self.assertEqual(list(self.requests.iterdir()), [])

    def test_zcode_unconfigured_default_refuses_explicit_compatibility_survives(self):
        self.config.pop("dispatch_profiles");self.save()
        self.refused(self.resolve, "zcode_native_bridge_config_required")
        for transport in ("orca-generic", "direct"):
            request = dict(self.request, transport=transport)
            profile = self.resolve(request)
            self.assertEqual(profile["transport"], transport)
            self.assertNotIn("--orca-supervised", profile["required_spawn_flags"])
            if transport == "direct":self.assertIn("--no-orca-mode", profile["required_spawn_flags"])

    def test_legacy_personal_and_zero_cap_semantics(self):
        self.config["_schema_version"] = "1.1";self.save()
        caps = self.resolve()["configuration"]["concurrency"]
        self.assertEqual(caps["cap"], 0)
        self.assertFalse(caps["slot_lease_required"])
        self.assertIn("resource/budget", caps["meaning"])
        self.assertIsNone(caps["runtime_running_count"])
        request = {"backend": "claude-code", "harness_chain": ["codex"]}
        self.assertEqual(self.resolve(request)["configuration"]["concurrency"]["cap"], 10)
        self.assertEqual(self.resolve(self.minimax("interactive"))["configuration"]["concurrency"]["cap"], 3)

    def test_native_directory_mode_and_symlink_refused(self):
        self.requests.chmod(0o755)
        self.refused(self.resolve, "native_requests_directory_untrusted")
        self.requests.chmod(0o700)
        link = self.root / "requests-link";link.symlink_to(self.requests)
        self.config["dispatch_profiles"]["zcode-cli"]["native_bridge"]["requests_root"] = str(link);self.save()
        self.refused(self.resolve, "symlink_path")

    def test_unknown_config_enabled_and_cap_refused(self):
        self.config["dispatch_profiles"]["zcode-cli"]["native_bridge"]["enabled"] = "yes";self.save()
        self.refused(self.resolve, "native_bridge_enabled_unknown")
        self.config["dispatch_profiles"]["zcode-cli"]["native_bridge"]["enabled"] = True
        self.config["dispatch_profiles"]["zcode-cli"]["native_bridge"]["other"] = True;self.save()
        self.refused(self.resolve, "native_bridge_config_unknown")
        self.config.pop("dispatch_profiles");self.config["concurrency"]["max_per_provider"] = True;self.save()
        self.refused(lambda: self.resolve(self.minimax("interactive")), "concurrency_cap_invalid")

    def test_missing_personal_has_no_fabricated_concurrency(self):
        self.personal.unlink()
        request = self.minimax("interactive", transport="direct")
        caps = self.resolve(request)["configuration"]["concurrency"]
        self.assertIsNone(caps["cap"])
        self.assertIsNone(caps["slot_lease_required"])

    def test_optional_and_host_intersection_preserved(self):
        self.refused(lambda: self.resolve(dict(self.request, explicit_selection=False)), "optional_backend_requires_explicit_selection")
        self.refused(lambda: self.resolve(dict(self.request, harness_chain=["codex", "codebuddy"])), "backend_not_authorized")
        self.refused(lambda: self.resolve(dict(self.request, harness_chain=["unknown"])), "harness_policy_denied")
        default = self.resolve({"harness_chain": ["codex"]})
        self.assertEqual(default["backend"], "claude-code")
        self.assertEqual(default["selection"]["source"], "policy_default")

    def test_minimax_actual_api_validated_mode_is_separate_from_requested(self):
        request = self.minimax("batch")
        unverified = self.resolve(request)
        self.assertIsNone(unverified["startup"]["validated_mode"])
        self.assertEqual(unverified["next_action"]["kind"], "validate_command_startup")
        verified = self.resolve(request, validated_startup=p.ValidatedStartup("batch", "actual resolve_minimax_startup consumer"))
        self.assertEqual(verified["startup"]["validated_mode"], "batch")
        self.assertEqual(verified["next_action"]["kind"], "spawn_batch_once")
        self.assertEqual(verified["task_input"]["source"], "command_bootstrap")
        self.assertEqual(verified["required_native_flags"], ["exec", "--permission", "full"])
        self.assertNotIn("--orca-supervised", verified["required_spawn_flags"])
        self.refused(lambda: self.resolve(request, validated_startup={"mode": "batch"}), "validated_startup_contradiction")
        self.refused(lambda: self.resolve(request, validated_startup=p.ValidatedStartup("interactive", "actual")), "validated_startup_contradiction")

    def test_actual_existing_minimax_classifier_consumer(self):
        classifier = Path(os.environ.get("MAO_TEST_MINIMAX_STARTUP_CLI", str(HERE / "minimax-cli-startup.py")))
        if not classifier.is_file():
            self.skipTest("existing MiniMax classifier has not entered this integration base")
        mcode = shutil.which("mcode")
        if not mcode:
            self.skipTest("native mcode path unavailable; no model is executed by this test")
        prompt = self.root / "classifier-input.txt"
        prompt.write_text("isolated profile classification fixture\n")
        batch = shlex.join([mcode, "exec", "--permission", "full", "--input", "-"]) + " < " + shlex.quote(str(prompt))
        for command, mode in ((batch, "batch"), (shlex.join([mcode]), "interactive")):
            result = subprocess.run([sys.executable, "-B", str(classifier), "--require-input", "--command", command],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), mode)
            source = "existing_classifier_cli:" + hashlib.sha256(classifier.read_bytes()).hexdigest()
            profile = self.resolve(self.minimax(mode), validated_startup=p.ValidatedStartup(result.stdout.strip(), source))
            self.assertEqual(profile["startup"]["validated_mode"], mode)
        denied = subprocess.run([sys.executable, "-B", str(classifier), "--require-input", "--supervised", "1", "--command", batch],
                                capture_output=True, text=True)
        self.assertEqual(denied.returncode, 64)
        self.assertIn("MINIMAX_BATCH_REQUIRES_TERMINAL_MANAGED", denied.stderr)

    def test_official_completed_submission_or_user_owned_close_conflict(self):
        for action, error in (("submit_task_once", "receipt_completed_submission_conflict"),
                              ("close_terminal", "receipt_retained_close_conflict")):
            raw = copy.deepcopy(self.receipt)
            raw["result"]["projection"]["nextAction"]["kind"] = action
            self.refused(lambda: p.validate_receipt(raw, self.expected), error)

    def test_minimax_batch_created_never_sends_second_input(self):
        request = self.minimax("batch", observations={"terminal_created": True, "tui_idle": True})
        result = self.resolve(request)
        self.assertEqual(result["task_input"]["source"], "command_bootstrap")
        self.assertEqual(result["next_action"]["kind"], "inspect_batch_start")
        self.assertFalse(result["task_input"]["may_submit_second_input"])
        self.refused(lambda: self.resolve(self.minimax("batch", supervised=True)), "minimax_batch_supervised_conflict")

    def test_minimax_interactive_direct_and_requested_observed_permission(self):
        result = self.resolve(self.minimax("interactive", transport="direct", observations={"permissionMode": "auto"}))
        self.assertEqual(result["permission"]["requested"], "full")
        self.assertEqual(result["permission"]["observed"], "auto")
        self.assertEqual(result["permission"]["observed_source"], "supplied_observation")
        self.assertEqual(result["required_native_flags"], [])
        self.assertIn("--no-orca-mode", result["required_spawn_flags"])

    def test_transport_mode_and_startup_conflicts(self):
        self.refused(lambda: self.resolve(self.minimax("interactive", transport="orca-native-supervised")), "native_transport_backend_mismatch")
        self.refused(lambda: self.resolve(dict(self.request, transport="direct", supervised=True)), "direct_supervised_conflict")
        self.refused(lambda: self.resolve(dict(self.request, execution_mode="batch")), "zcode_native_requires_interactive")
        self.refused(lambda: self.resolve(self.minimax("interactive", startup_mode="batch")), "startup_mode_contradiction")

    def test_submission_states_never_upgrade_tui_to_completion(self):
        request = dict(self.request, observations={"terminal_created": True, "tui_idle": True})
        self.assertEqual(self.resolve(request)["next_action"]["kind"], "inspect_dispatch_submission")
        for state, expected in [("input_accepted", "observe_turn_start"), ("turn_started", "observe_worker_done"),
                                ("worker_done", "pm_verify_result"), ("pm_accepted", "release_worker")]:
            self.assertEqual(self.resolve(dict(request, input_state=state))["next_action"]["kind"], expected)
        self.assertEqual(self.resolve(request)["task_input"]["state"], "draft")

    def test_supervised_injected_and_composer_residue_never_duplicate(self):
        for observation, kind in [({"supervised_spec_injected": True}, "inspect_dispatch_submission"),
                                 ({"composer_text_present": True}, "inspect_existing_input"),
                                 ({"worker_done": True, "composer_text_present": True}, "pm_verify_result"),
                                 ({"workerState": "succeeded", "dispatchStatus": "completed", "composer_text_present": True}, "inspect_completion_evidence")]:
            self.assertEqual(self.resolve(dict(self.request, observations=observation))["next_action"]["kind"], kind)

    def test_actual_cli_official_completed_retained_stale_projection_wins(self):
        request = dict(self.request, observations={"composer_text_present": True, "worker_done": True})
        result = self.cli(request, self.receipt)
        self.assertEqual(result.returncode, 0, result.stderr)
        profile = json.loads(result.stdout)
        self.assertEqual(profile["next_action"]["kind"], "none")
        self.assertEqual(profile["next_action"]["authority"], "orca_projection")
        projection = profile["official_projection"]
        self.assertEqual(projection["ownership_state"], "user_owned")
        self.assertEqual(projection["terminal_state"], "retained")
        self.assertEqual(projection["live_status"], "stale")
        self.assertFalse(projection["fresh_running_activity_verified"])
        self.assertNotIn("argv", profile["next_action"])
        self.assertFalse(profile["dispatch_executed"])

    def test_official_identity_alias_conflict_null_and_runtime_drift_refuse(self):
        for location, key, value in [("dispatch", "task_id", "other"), ("projection", "id", None),
                                     ("worker", "dispatch_id", "other"), ("terminalResource", "ownerDispatchId", "other")]:
            raw = copy.deepcopy(self.receipt);raw["result"][location][key] = value
            self.refused(lambda: p.validate_receipt(raw, self.expected), "receipt_identity_alias_mismatch")
        raw = copy.deepcopy(self.receipt);raw["_meta"]["runtimeId"] = "other"
        self.refused(lambda: p.validate_receipt(raw, self.expected), "receipt_runtime_mismatch")
        self.refused(lambda: p.validate_receipt(self.receipt, {"dispatch_id": "ctx-fixture"}), "receipt_expected_identity_incomplete")

    def test_official_projection_missing_cannot_fallback_to_send(self):
        raw = copy.deepcopy(self.receipt);raw["result"]["projection"].pop("nextAction")
        result = self.cli(self.request, raw)
        self.assertEqual(result.returncode, 64)
        self.assertIn("receipt_projection_unknown", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_observation_alias_conflicts_and_unsupported_screen_refused(self):
        self.refused(lambda: self.resolve(dict(self.request, observations={"workerState": "succeeded", "worker_state": "running"})), "observation_alias_conflict")
        self.refused(lambda: self.resolve(dict(self.request, observations={"screen": "do not copy business screen"})), "observation_field_unknown")
        self.refused(lambda: self.resolve(dict(self.request, observations={"tui_idle": "yes"})), "observation_type_invalid")

    def test_actual_cli_negative_no_configuration_mutation(self):
        before = self.personal.read_bytes()
        result = self.cli(dict(self.request, transport="unknown"))
        self.assertEqual(result.returncode, 64)
        self.assertIn("mode_or_transport_unknown", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.personal.read_bytes(), before)
        self.assertEqual(list(self.requests.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
