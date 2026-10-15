#!/usr/bin/env python3
"""Actual adapter CLI consumers using product classifier bytes in an isolated skill."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mao-profile-adapter-")
        self.root = Path(self.temp.name).resolve()
        self.skill = self.root / "skill"
        self.scripts = self.skill / "scripts";self.scripts.mkdir(parents=True)
        self.config_dir = self.skill / "config";self.config_dir.mkdir()
        classifier = Path(os.environ.get("MAO_TEST_MINIMAX_CLASSIFIER", str(HERE / "validate-worker-command.py")))
        for name in ("dispatch-profile.py", "dispatch-profile-adapter.py"):
            shutil.copyfile(HERE / name, self.scripts / name)
        shutil.copyfile(classifier, self.scripts / "validate-worker-command.py")
        shutil.copyfile(HERE.parent / "config" / "harness-backend-policy.json", self.config_dir / "harness-backend-policy.json")
        self.classifier_available = "def resolve_minimax_startup" in classifier.read_text()
        self.classifier_sha = hashlib.sha256(classifier.read_bytes()).hexdigest()
        self.requests = self.root / "requests";self.requests.mkdir(mode=0o700)
        self.personal = self.config_dir / "orchestration-personal.json"
        self.config = {"_schema_version": "1.3", "concurrency": {"max_per_provider": 3, "per_backend": {"zcode-cli": 0}},
            "dispatch_profiles": {"zcode-cli": {"native_bridge": {"enabled": True, "requests_root": str(self.requests)}}}}
        self.save()
        self.prompt = self.root / "prompt.txt";self.prompt.write_text("isolated classifier bootstrap\n")
        self.mcode = shutil.which("mcode") or "mcode"
        self.zcode = shutil.which("zcode") or "zcode"

    def tearDown(self):self.temp.cleanup()

    def save(self):
        self.personal.write_text(json.dumps(self.config));self.personal.chmod(0o600)

    def invoke(self, backend, command, **request_fields):
        request = {"backend": backend, "explicit_selection": True, "harness_chain": ["codex"], **request_fields}
        return subprocess.run([sys.executable, "-B", str(self.scripts / "dispatch-profile-adapter.py")],
            input=json.dumps({"request": request, "command": command}), capture_output=True, text=True,
            env={**os.environ, "MULTI_AGENT_ORCHESTRATION_PERSONAL_CONFIG": str(self.personal)})

    def batch(self, permission="full", equals=False):
        flags = ["--permission=" + permission] if equals else ["--permission", permission]
        return shlex.join([self.mcode, "exec", *flags, "--input", "-"]) + " < " + shlex.quote(str(self.prompt))

    def require_classifier(self):
        if not self.classifier_available:self.skipTest("new product classifier has not entered this base")

    def success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertFalse(value["dispatch_executed"])
        self.assertFalse(value["adapter"]["model_executed"])
        self.assertEqual(value["adapter"]["command_validator"]["sha256"], self.classifier_sha)
        return value

    def denied(self, result, error):
        self.assertEqual(result.returncode, 64, result.stdout + result.stderr)
        self.assertIn(error, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(list(self.requests.iterdir()), [])

    def test_real_command_batch_classification_not_request_mode(self):
        self.require_classifier()
        value = self.success(self.invoke("minimax-code", self.batch()))
        self.assertEqual(value["execution_mode"], "batch")
        self.assertEqual(value["startup"]["validated_mode"], "batch")
        self.assertEqual(value["task_input"]["source"], "command_bootstrap")
        self.assertEqual(value["next_action"]["kind"], "spawn_batch_once")
        self.assertEqual(value["permission"]["command_actual"], "full")
        self.denied(self.invoke("minimax-code", self.batch(), execution_mode="interactive"), "requested_mode_command_conflict")

    def test_batch_explicit_smart_off_and_equals_preserved(self):
        self.require_classifier()
        for mode in ("smart", "off"):
            for equals in (False, True):
                command = self.batch(mode, equals)
                value = self.success(self.invoke("minimax-code", command))
                self.assertEqual(value["permission"]["requested"], mode)
                self.assertEqual(value["permission"]["command_actual"], mode)
                self.assertEqual(value["permission"]["requested_source"], "actual_command_argv")
                self.assertEqual(value["required_native_flags"], ["exec", "--permission", mode])
                self.assertIsNone(value["permission"]["observed"])
                self.assertEqual(value["adapter"]["command_sha256"], hashlib.sha256(command.encode()).hexdigest())

    def test_tui_permission_native_observation_unknown(self):
        self.require_classifier()
        value = self.success(self.invoke("minimax-code", shlex.join([self.mcode]), transport="direct"))
        self.assertEqual(value["execution_mode"], "interactive")
        self.assertEqual(value["permission"]["requested_source"], "native_configuration_observation_required")
        self.assertIsNone(value["permission"]["command_actual"])
        self.assertIsNone(value["permission"]["observed"])
        self.assertEqual(value["required_native_flags"], [])
        self.assertIn("--no-orca-mode", value["required_spawn_flags"])

    def test_zcode_explicit_build_edit_plan_and_equals(self):
        for mode in ("build", "edit", "plan", "yolo"):
            for option in (["--mode", mode], ["--mode=" + mode]):
                value = self.success(self.invoke("zcode-cli", shlex.join([self.zcode, *option])))
                self.assertEqual(value["permission"]["requested"], mode)
                self.assertEqual(value["permission"]["command_actual"], mode)
                self.assertEqual(value["required_native_flags"], ["--mode", mode])
                self.assertIsNone(value["permission"]["observed"])

    def test_no_permission_argv_does_not_claim_actual_defaults(self):
        value = self.success(self.invoke("zcode-cli", shlex.join([self.zcode])))
        self.assertEqual(value["permission"]["requested"], "yolo")
        self.assertEqual(value["permission"]["requested_source"], "dispatch_intent_default")
        self.assertIsNone(value["permission"]["command_actual"])
        self.assertIsNone(value["permission"]["observed"])

    def test_requested_permission_contradiction_refuses(self):
        self.denied(self.invoke("zcode-cli", shlex.join([self.zcode, "--mode", "build"]), requested_permission="yolo"),
            "requested_permission_command_conflict")

    def test_permission_option_value_is_not_scanned_as_flag(self):
        self.require_classifier()
        command = shlex.join([self.mcode, "exec", "--model", "--permission=off", "--input", "-"]) + " < " + shlex.quote(str(self.prompt))
        value = self.success(self.invoke("minimax-code", command))
        self.assertIsNone(value["permission"]["command_actual"])
        self.assertEqual(value["permission"]["requested"], "full")

    def test_backend_command_conflict_no_model_execution(self):
        self.denied(self.invoke("zcode-cli", shlex.join([self.mcode])), "adapter_backend_command_conflict")

    def test_actual_classifier_rejects_empty_bootstrap(self):
        self.require_classifier()
        self.prompt.write_text("")
        self.denied(self.invoke("minimax-code", self.batch()), "existing_command_validator_refused")

    def test_supervised_batch_and_resend_are_forbidden(self):
        self.require_classifier()
        self.denied(self.invoke("minimax-code", self.batch(), supervised=True), "minimax_batch_supervised_conflict")
        value = self.success(self.invoke("minimax-code", self.batch(), observations={"terminal_created": True, "tui_idle": True}))
        self.assertEqual(value["next_action"]["kind"], "inspect_batch_start")
        self.assertFalse(value["task_input"]["may_submit_second_input"])

    def test_old_explicit_native_arguments_no_new_config_required(self):
        self.config.pop("dispatch_profiles");self.save()
        value = self.success(self.invoke("zcode-cli", shlex.join([self.zcode, "--mode", "build"]),
            supervised=True, native_requests_root=str(self.requests)))
        self.assertEqual(value["configuration"]["native_requests_source"], "argument")
        self.assertIn("--orca-supervised", value["required_spawn_flags"])

    def test_missing_or_disabled_bridge_zero_effects(self):
        command = shlex.join([self.zcode, "--mode", "yolo"])
        self.config["dispatch_profiles"]["zcode-cli"]["native_bridge"]["enabled"] = False;self.save()
        before = self.personal.read_bytes()
        self.denied(self.invoke("zcode-cli", command), "zcode_native_bridge_config_required")
        self.assertEqual(self.personal.read_bytes(), before)
        self.config.pop("dispatch_profiles");self.save()
        self.denied(self.invoke("zcode-cli", command), "zcode_native_bridge_config_required")
        self.success(self.invoke("zcode-cli", command, transport="orca-generic"))
        self.success(self.invoke("zcode-cli", command, transport="direct"))

    def test_zcode_headless_command_never_native_dispatches(self):
        self.denied(self.invoke("zcode-cli", shlex.join([self.zcode, "--mode", "yolo", "--prompt", "fixture"])),
            "zcode_headless_dispatch_forbidden")

    def test_command_redirection_and_unknown_assignment_guard_preserved(self):
        self.require_classifier()
        self.denied(self.invoke("minimax-code", "mcode exec > /not-written"), "existing_command_validator_refused")
        # The adapter relies on the exact existing command validator. It does
        # not claim to fix the validator's historical quoted-assignment debt.
        result = self.invoke("zcode-cli", "unknown_binary --mode yolo")
        self.denied(result, "existing_command_validator_refused")

    def guidance(self, profile, outcome):
        result = subprocess.run([sys.executable, "-B", str(self.scripts / "dispatch-profile-adapter.py"), "--launch-outcome", outcome],
            input=json.dumps(profile),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout)
        self.assertEqual(value["input_state"],"draft")
        for key in ("input_accepted_verified","turn_started_verified","completion_verified"): self.assertFalse(value[key])
        return value

    def test_unique_initial_guidance_supervised_no_second_send(self):
        profile=self.success(self.invoke("zcode-cli",self.zcode+" --mode build"))
        guide=self.guidance(profile,"supervised_registration_returned")
        self.assertEqual(guide["next_action"]["kind"],"inspect_dispatch_submission")
        self.assertEqual(self.guidance(profile,"planned")["next_action"]["kind"],"spawn_supervised_once")

    def test_batch_and_terminal_created_do_not_claim_accepted(self):
        self.require_classifier()
        profile=self.success(self.invoke("minimax-code",self.batch()))
        self.assertEqual(self.guidance(profile,"batch_launch_returned")["next_action"]["kind"],"inspect_batch_start")
        generic=self.success(self.invoke("zcode-cli",self.zcode,transport="orca-generic"))
        self.assertEqual(self.guidance(generic,"terminal_created")["next_action"]["kind"],"wait_input_ready")

    def test_official_projection_keeps_none_after_local_launch_observation(self):
        profile=self.success(self.invoke("zcode-cli",self.zcode))
        # The original receipt validation is covered by profile tests. Guidance
        # preserves its already validated action rather than manufacturing send.
        profile["official_projection"]={"source":"supplied_validated_official_receipt"}
        profile["next_action"]={"kind":"none","authority":"orca_projection"}
        self.assertEqual(self.guidance(profile,"terminal_created")["next_action"]["kind"],"none")

    def test_worker_done_or_existing_composer_cannot_become_submit_again(self):
        for fields, action in (({"input_state":"worker_done"},"pm_verify_result"),
                               ({"observations":{"composer_text_present":True}},"inspect_existing_input")):
            profile=self.success(self.invoke("zcode-cli",self.zcode,transport="orca-generic",**fields))
            result=subprocess.run([sys.executable,"-B",str(self.scripts/"dispatch-profile-adapter.py"),"--launch-outcome","terminal_created"],
                input=json.dumps(profile),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            guide=json.loads(result.stdout)
            self.assertEqual(guide["next_action"]["kind"],action)
            self.assertFalse(guide["completion_verified"])

    def test_actual_adapter_completed_retained_receipt_refuses_spawn_actions(self):
        expected={"runtime_id":"runtime-fixture","dispatch_id":"ctx-fixture","run_id":"run-fixture","task_id":"task-fixture",
                  "worktree_id":"repo::/isolated/fixture","terminal_handle":"term-fixture"}
        raw={"ok":True,"_meta":{"runtimeId":"runtime-fixture"},"result":{
            "dispatch":{"id":"ctx-fixture","runId":"run-fixture","taskId":"task-fixture","status":"completed"},
            "worker":{"dispatchId":"ctx-fixture","state":"succeeded","worktreeId":"repo::/isolated/fixture","agentTerminalHandle":"term-fixture"},
            "projection":{"id":"ctx-fixture","runId":"run-fixture","taskId":"task-fixture",
                          "evidence":{"durable":True,"liveStatus":"stale"},"nextAction":{"kind":"none"}},
            "terminalResource":{"originDispatchId":"ctx-fixture","ownerDispatchId":"ctx-fixture","worktreeId":"repo::/isolated/fixture",
                                "terminalHandle":"term-fixture","ownershipState":"user_owned","releaseState":"retained","retainedReason":"user_takeover"}}}
        receipt=self.root/"official-receipt.json";identity=self.root/"expected-identity.json"
        identity.write_text(json.dumps(expected));identity.chmod(0o600)
        request={"request":{"backend":"zcode-cli","explicit_selection":True,"harness_chain":["codex"]},"command":self.zcode+" --mode yolo"}
        for kind in ("spawn_supervised_once","spawn_batch_once","spawn_terminal_once","submit_task_once","none"):
            raw["result"]["projection"]["nextAction"]["kind"]=kind
            receipt.write_text(json.dumps(raw));receipt.chmod(0o600)
            result=subprocess.run([sys.executable,"-B",str(self.scripts/"dispatch-profile-adapter.py"),
                    "--receipt-file",str(receipt),"--expected-identity-file",str(identity)],
                input=json.dumps(request),capture_output=True,text=True,
                env={**os.environ,"MULTI_AGENT_ORCHESTRATION_PERSONAL_CONFIG":str(self.personal)})
            if kind=="none":
                value=self.success(result)
                self.assertEqual(value["next_action"]["kind"],"none")
                self.assertEqual(self.guidance(value,"terminal_created")["next_action"]["kind"],"none")
                self.assertFalse(value["official_projection"]["fresh_running_activity_verified"])
            else:self.denied(result,"receipt_completed_submission_conflict")

    def test_actual_adapter_legacy_personal_accepts_and_unknown_version_refuses(self):
        self.config={"quota_aware_routing":{"enabled":False}};self.save()
        value=self.success(self.invoke("codebuddy","codebuddy --permission-mode acceptEdits",transport="direct"))
        self.assertEqual(value["configuration"]["personal"]["format"],"legacy_unversioned")
        self.config["_schema_version"]="unknown";self.save()
        self.denied(self.invoke("codebuddy","codebuddy --permission-mode acceptEdits",transport="direct"),"personal_version_unknown")
        self.config={"dispatch_profiles":{"zcode-cli":{"native_bridge":{"enabled":"true"}}}};self.save()
        self.denied(self.invoke("codebuddy","codebuddy --permission-mode acceptEdits",transport="direct"),"native_bridge_enabled_unknown")

    def test_unknown_launch_outcome_and_malformed_profile_refuse(self):
        profile=self.success(self.invoke("zcode-cli",self.zcode))
        for data,outcome in ((profile,"worker_done"),({"ok":True,"task_input":{},"next_action":{}},"terminal_created")):
            result=subprocess.run([sys.executable,"-B",str(self.scripts/"dispatch-profile-adapter.py"),"--launch-outcome",outcome],
                input=json.dumps(data),capture_output=True,text=True)
            self.assertEqual(result.returncode,64)
            self.assertEqual(result.stdout,"")


if __name__ == "__main__":
    unittest.main()
