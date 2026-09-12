#!/usr/bin/env python3
"""Exercise real Task-spec routes and launch bindings, without live Orca/providers."""

import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parent
COMPLETION = "SUPERVISED COMPLETION PROTOCOL (MANDATORY):"
DELIVERY = "WORKER DELIVERY PROTOCOL (MANDATORY):"
FAKE_ORCA = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
log = Path(os.environ["DELIVERY_ORCA_LOG"])
with log.open("a") as stream:
    stream.write(json.dumps(args) + "\n")

def refuse(message):
    print("FAKE_ORCA_REFUSED: " + message + " " + repr(args), file=sys.stderr)
    sys.exit(97)

def flags(valued=(), switches=("--json",), required=()):
    parsed = {}
    tail = args[2:]
    while tail:
        key, *tail = tail
        if key in parsed:
            refuse("duplicate flag")
        if key in switches:
            parsed[key] = True
        elif key in valued and tail:
            parsed[key], *tail = tail
        else:
            refuse("unknown flag or missing value")
    if any(key not in parsed for key in required):
        refuse("missing required flag")
    return parsed

runtime = os.environ.get("DELIVERY_RUNTIME_ID", "runtime-delivery")
meta_runtime = runtime
if args == ["status", "--json"]:
    result = {"runtime": {"reachable": True, "runtimeId": runtime}}
elif args[:2] == ["terminal", "show"]:
    parsed = flags(("--terminal",), required=("--terminal", "--json"))
    if parsed["--terminal"] != "term-pm":
        print(json.dumps({"ok": False, "error": {"code": "selector_not_found"}}))
        sys.exit(1)
    meta_runtime = os.environ.get("DELIVERY_TERMINAL_RUNTIME_ID", runtime)
    result = {"terminal": {"handle": "term-pm", "connected": True, "writable": True,
                           "orphaned": False, "exitCause": None}}
elif args[:2] in (["orchestration", "run-create"], ["orchestration", "run-use"],
                  ["orchestration", "run-current"]):
    action_flag = {"run-create": "--objective", "run-use": "--id"}.get(args[1])
    required = ("--from", "--json") + ((action_flag,) if action_flag else ())
    parsed = flags(("--from",) + ((action_flag,) if action_flag else ()), required=required)
    if parsed["--from"] != "term-pm" or (args[1] == "run-use" and parsed["--id"] != "run-delivery"):
        refuse("wrong Run/sender")
    meta_runtime = os.environ.get("DELIVERY_RUN_RUNTIME_ID", runtime)
    result = {"run": {"id": "run-delivery", "coordinator_handle": "term-pm"}}
elif args[:2] == ["orchestration", "task-create"]:
    required = ("--spec", "--task-title", "--run", "--from", "--json")
    parsed = flags(required[:-1], required=required)
    if parsed["--from"] != "term-pm" or parsed["--run"] != "run-delivery":
        refuse("wrong task Run/sender")
    count = sum(json.loads(line)[:2] == ["orchestration", "task-create"]
                for line in log.read_text().splitlines())
    result = {"task": {"id": "task-" + str(count)}}
elif args[:2] == ["orchestration", "worker-start"]:
    required = ("--task", "--terminal", "--worktree", "--run", "--from", "--timeout-ms", "--json")
    parsed = flags(required[:-1], required=required)
    if (parsed["--from"] != "term-pm" or parsed["--run"] != "run-delivery"
            or parsed["--terminal"] != "term-worker"
            or parsed["--worktree"] != "id:repo-fixture::worker"):
        refuse("wrong worker identity")
    task = parsed["--task"]
    result = {"dispatch": {"id": "ctx-" + task}}
elif args[:2] == ["orchestration", "dispatch-show"]:
    parsed = flags(("--task",), required=("--task", "--json"))
    result = {"dispatch": {"id": "ctx-" + parsed["--task"]}}
elif args[:2] in (["worktree", "current"], ["worktree", "show"]):
    if args[1] == "current":
        flags(required=("--json",))
    else:
        parsed = flags(("--worktree",), required=("--worktree", "--json"))
        if parsed["--worktree"] != "id:repo-fixture::worker":
            refuse("wrong worktree selector")
    print(json.dumps({"ok": False, "error": {"code": "selector_not_found"}}))
    sys.exit(1)
else:
    refuse("unsupported command")
print(json.dumps({"ok": True, "result": result, "_meta": {"runtimeId": meta_runtime}}))
'''


class WorkerDeliveryPromptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mao-delivery-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "orca.jsonl"
        self.fake_orca = self.bin / "orca"
        self.fake_orca.write_text(FAKE_ORCA)
        self.fake_orca.chmod(0o755)
        for name in ("orca-dev", "orca-ide"):
            (self.bin / name).symlink_to("orca")
        self.env = os.environ.copy()
        for name in ("SCOPE_GUARD_SESSION_ROOT", "WORKER_INSTALL_AUTH_FILE",
                     "WORKER_INSTALL_AUTH_B64", "WORKER_GUARD_ATTESTATION_FILE",
                     "WORKER_GUARD_SETTINGS_FILE", "WORKER_AUTHORITY_RECEIPT_FILE",
                     "ORCA_TERMINAL_HANDLE", "DELIVERY_RUNTIME_ID",
                     "DELIVERY_TERMINAL_RUNTIME_ID", "DELIVERY_RUN_RUNTIME_ID"):
            self.env.pop(name, None)
        self.env.update(
            ORCA_CLI_COMMAND=str(self.fake_orca), ORCA_CLI_BIN=str(self.fake_orca),
            DELIVERY_ORCA_LOG=str(self.log), PATH=f"{self.bin}:{self.env['PATH']}",
            MULTI_AGENT_ORCHESTRATION_PERSONAL_CONFIG=str(self.root / "absent-personal.json"),
            GIT_AUTHOR_NAME="Delivery Test", GIT_COMMITTER_NAME="Delivery Test",
            GIT_AUTHOR_EMAIL="delivery@example.invalid",
            GIT_COMMITTER_EMAIL="delivery@example.invalid",
        )

    def run_command(self, args, *, env=None, expected=0, cwd=None, input_text=None):
        completed = subprocess.run(
            args, cwd=cwd or self.root, env=env or self.env,
            text=True, capture_output=True, timeout=45, input=input_text,
        )
        diagnostic = f"{args!r}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        if expected == "nonzero":
            self.assertNotEqual(completed.returncode, 0, diagnostic)
        else:
            self.assertEqual(completed.returncode, expected, diagnostic)
        return completed

    def calls(self, command=None):
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return [call for call in calls if command is None or call[:len(command)] == command]

    def assert_no_second_injector(self):
        self.assertEqual(self.calls(["terminal", "send"]), [])
        self.assertEqual(self.calls(["orchestration", "dispatch"]), [])

    def assert_delivery_spec(self, spec, body):
        self.assertTrue(spec.startswith(COMPLETION))
        self.assertEqual(spec.count(COMPLETION), 1)
        self.assertEqual(spec.count(DELIVERY), 1)
        self.assertTrue(spec.endswith("\n\n" + body))
        for rule in ("smallest in-scope implementation", "scoped verification commands",
                     "git add only the task-authorized files", "commit the verified deliverable",
                     "Review-only or genuinely no-change", "not manufacture an empty commit",
                     "real 40-character git rev-parse HEAD", "never repository-root RESULT.md",
                     "Push, PR and history changes follow the PM task contract"):
            self.assertIn(rule, spec)

    def wave(self, bodies, *, sender="term-pm", expected=0):
        manifest = self.root / "wave.json"
        manifest.write_text(json.dumps({"objective": "delivery fixture", "tasks": [
            {"key": str(index), "title": "Worker " + str(index), "spec": body}
            for index, body in enumerate(bodies)
        ]}))
        output = self.run_command(["bash", str(SCRIPTS / "orca-wave-prepare.sh"),
                                   "--from", sender, "--manifest", str(manifest)], expected=expected)
        return json.loads(output.stdout) if expected == 0 else output

    def register(self, *extra):
        return self.run_command([
            "bash", str(SCRIPTS / "orca-supervised-register.sh"),
            "--worktree-id", "repo-fixture::worker", "--terminal-handle", "term-worker",
            "--run-id", "run-delivery", "--coordinator-handle", "term-pm",
            "--runtime-id", "runtime-delivery", *extra,
        ])

    def test_wave_precreation_preserves_body_without_expanding_pm_environment(self):
        self.env["SCOPE_GUARD_SESSION_ROOT"] = "/pm-context-must-not-leak"
        self.env["WORKER_INSTALL_AUTH_FILE"] = "/pm-auth-must-not-leak/auth.json"
        bodies = ["Implement owned.py only.\nVerify: python3 owned_test.py",
                  "Review-only: report findings; no branch changes. Literal $HOME stays literal."]
        receipt = self.wave(bodies)
        self.assertEqual(receipt["run_id"], "run-delivery")
        self.assertEqual(receipt["coordinator_handle"], "term-pm")
        self.assertEqual(receipt["_meta"]["runtimeId"], "runtime-delivery")
        self.assertEqual(self.calls(["orchestration", "run-create"]), [
            ["orchestration", "run-create", "--objective", "delivery fixture", "--from", "term-pm", "--json"]])
        self.assertTrue(self.calls(["orchestration", "run-current"]))
        for call in self.calls(["orchestration", "run-current"]):
            self.assertEqual(call, ["orchestration", "run-current", "--from", "term-pm", "--json"])
        self.assertEqual(len(receipt["tasks"]), 2)
        self.assertFalse((self.root / "worktree").exists())
        calls = self.calls(["orchestration", "task-create"])
        self.assertEqual(len(calls), 2)
        for call, body in zip(calls, bodies):
            spec = call[call.index("--spec") + 1]
            self.assert_delivery_spec(spec, body)
            self.assertNotIn("/pm-context-must-not-leak", spec)
            self.assertNotIn("/pm-auth-must-not-leak", spec)
        self.assertEqual(self.calls(["orchestration", "worker-start"]), [])
        self.assert_no_second_injector()

    def test_direct_register_creates_one_spec_and_one_worker_start(self):
        body = "Implement only src/owned.py, verify its single test; PM owns PR."
        result = self.register("--task-spec", body)
        calls = self.calls(["orchestration", "task-create"])
        self.assertEqual(len(calls), 1)
        self.assert_delivery_spec(calls[0][calls[0].index("--spec") + 1], body)
        self.assertEqual(len(self.calls(["orchestration", "worker-start"])), 1)
        self.assertIn("ORCAREG_DISPATCH_ID=ctx-task-1", result.stdout)
        self.assert_no_second_injector()

    def test_register_reuses_wave_task_without_recreating_or_reinjecting(self):
        body = "Implement only owned.py; stop at verified commit."
        receipt = self.wave([body])
        before = self.calls(["orchestration", "task-create"])
        bindings_before = self.calls(["orchestration", "run-create"]) + self.calls(["orchestration", "run-use"])
        self.register("--task-id", receipt["tasks"][0]["task_id"], "--task-spec", body)
        self.assertEqual(self.calls(["orchestration", "task-create"]), before)
        self.assertEqual(self.calls(["orchestration", "run-create"]) + self.calls(["orchestration", "run-use"]),
                         bindings_before)
        starts = self.calls(["orchestration", "worker-start"])
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0][starts[0].index("--task") + 1], "task-1")
        self.assert_no_second_injector()

    def test_wave_rejects_wrong_sender_or_runtime_before_task_injection(self):
        cases = [
            ("term-unrelated", {}, "terminal show failed", False),
            ("term-pm", {"DELIVERY_TERMINAL_RUNTIME_ID": "runtime-other"},
             "sender handle/runtime must match", False),
            ("term-pm", {"DELIVERY_RUN_RUNTIME_ID": "runtime-other"},
             "ORCA_COORDINATOR_RUN_MISMATCH", True),
        ]
        for sender, overrides, diagnostic, run_created in cases:
            with self.subTest(sender=sender, overrides=overrides):
                self.log.write_text("")
                self.env.pop("DELIVERY_TERMINAL_RUNTIME_ID", None)
                self.env.pop("DELIVERY_RUN_RUNTIME_ID", None)
                self.env.update(overrides)
                result = self.wave(["Must never be injected."], sender=sender, expected=3)
                self.assertIn(diagnostic, result.stderr)
                self.assertEqual(bool(self.calls(["orchestration", "run-create"])), run_created)
                self.assertEqual(self.calls(["orchestration", "task-create"]), [])
                self.assertEqual(self.calls(["orchestration", "worker-start"]), [])
                self.assert_no_second_injector()

    def test_fake_refuses_unknown_or_unofficial_sender_arguments(self):
        for args in (["terminal", "show", "--from", "term-pm", "--json"],
                     ["orchestration", "run-current", "--from", "term-pm", "--unknown", "--json"]):
            with self.subTest(args=args):
                result = self.run_command([str(self.fake_orca), *args], expected=97)
                self.assertIn("FAKE_ORCA_REFUSED:", result.stderr)
        self.assertEqual(self.calls(["orchestration", "task-create"]), [])
        self.assertEqual(self.calls(["orchestration", "worker-start"]), [])

    def test_exact_prefix_is_idempotent_when_reused_as_direct_spec(self):
        body = "Business text with quotes ' and \" and a second line.\nNo changes means no empty commit."
        self.wave([body])
        call = self.calls(["orchestration", "task-create"])[0]
        prepared = call[call.index("--spec") + 1]
        self.register("--task-spec", prepared)
        call = self.calls(["orchestration", "task-create"])[1]
        self.assertEqual(call[call.index("--spec") + 1], prepared)
        self.assert_delivery_spec(prepared, body)
        self.assert_no_second_injector()

    def binding_snippet(self):
        self.wave(["Implement owned.py and report verification."])
        call = self.calls(["orchestration", "task-create"])[0]
        spec = call[call.index("--spec") + 1]
        matches = re.findall(r"```bash\n(.*?)\n```", spec, re.S)
        self.assertEqual(len(matches), 1)
        return matches[0]

    def assert_hook_allows(self, snippet):
        loader = importlib.util.spec_from_file_location(
            "delivery_guard", SCRIPTS / "dependency-install-guard.py")
        guard = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(guard)
        self.assertTrue(guard.is_safe_lifecycle_command(snippet))
        # Invoke the actual wrapper with a representative PreToolUse event and a
        # deny-default process snapshot with NO exact-command widening. This is
        # fixture authority only; no real runtime receipt/attestation is touched.
        snapshot = base64.b64encode(json.dumps({
            "policy": "deny_by_default", "authorized_commands": [],
            "allowed_shell_commands": [], "authorization_source": "",
        }).encode()).decode()
        env = {**self.env, "WORKER_INSTALL_AUTH_B64": snapshot, "WORKER_GUARD_BACKEND": "claude-code"}
        for tool in ("Bash", "Shell"):
            event = json.dumps({"tool_name": tool, "tool_input": {"command": snippet}})
            result = self.run_command(["bash", str(SCRIPTS / "dependency-install-guard-hook.sh")],
                                      env=env, input_text=event)
            self.assertEqual(result.stdout, "", "hook denied the generated binding command")
        # A denied arbitrary Python resolver proves that empty output above is
        # genuine admission, not a dead/no-op hook that accepts every event.
        denied = self.run_command(["bash", str(SCRIPTS / "dependency-install-guard-hook.sh")],
                                  env=env, input_text=json.dumps({
                                      "tool_name": "Bash", "tool_input": {"command": "python3 -c 'print(1)'"}}))
        self.assertEqual(json.loads(denied.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_delivered_binding_command_fails_closed_without_guessing_or_writing(self):
        snippet = self.binding_snippet()
        self.assert_hook_allows(snippet)
        context = self.root / "worktree" / ".claude" / "agent-sessions" / "bound session"
        context.mkdir(parents=True)
        auth = context / "INSTALL_AUTHORIZATION.json"
        auth.write_text("{}")
        alias = self.root / "context-alias"
        alias.symlink_to(context, target_is_directory=True)
        cases = [
            ({}, "nonzero"),
            ({"SCOPE_GUARD_SESSION_ROOT": ".claude/agent-sessions/guessed"}, "nonzero"),
            ({"WORKER_INSTALL_AUTH_FILE": "relative/auth.json"}, "nonzero"),
            ({"SCOPE_GUARD_SESSION_ROOT": str(self.root / "missing")}, "nonzero"),
            ({"SCOPE_GUARD_SESSION_ROOT": str(context),
              "WORKER_INSTALL_AUTH_FILE": str(self.root / "other" / "auth.json")}, "nonzero"),
            ({"SCOPE_GUARD_SESSION_ROOT": str(context)}, 0),
            ({"WORKER_INSTALL_AUTH_FILE": str(auth)}, 0),
            ({"SCOPE_GUARD_SESSION_ROOT": str(context), "WORKER_INSTALL_AUTH_FILE": str(auth)}, 0),
            ({"SCOPE_GUARD_SESSION_ROOT": str(alias), "WORKER_INSTALL_AUTH_FILE": str(auth)}, "nonzero"),
        ]
        before = sorted(str(path) for path in self.root.rglob("*"))
        for bindings, expected in cases:
            with self.subTest(bindings=bindings):
                result = self.run_command(["bash", "-c", snippet],
                                          env={**self.env, **bindings}, expected=expected)
                if expected == 0:
                    self.assertEqual(result.stdout.splitlines(), [str(context), str(context) + "/."])
                else:
                    self.assertTrue(result.stderr)
                    # An unavailable directory may print its candidate before ls
                    # fails; the nonzero exit, never empty output, is authoritative.
                    if "missing" not in str(bindings):
                        self.assertIn("BLOCKED:", result.stderr)
                        self.assertEqual(result.stdout, "")
                self.assertEqual(sorted(str(path) for path in self.root.rglob("*")), before)

    def test_real_spawn_commands_bind_scope_and_install_paths_for_delivery(self):
        snippet = self.binding_snippet()
        # Explicit, hermetic process-identity fixture; the actual detector/policy
        # still execute. No real agent/provider or tmux process is started here.
        ps = self.bin / "ps"
        ps.write_text("#!/usr/bin/env bash\ncase \"$*\" in\n"
                      "*ppid=*) echo 1 ;;\n*comm=*|*args=*) echo /fixture/codex ;;\n"
                      "*) exit 97 ;;\nesac\n")
        ps.chmod(0o755)
        fake_claude = self.bin / "claude"
        fake_claude.write_text("#!/usr/bin/env bash\nexit 97 # dry-run must never start provider\n")
        fake_claude.chmod(0o755)
        repo = self.root / "fixture repo"
        repo.mkdir()
        self.run_command(["git", "init", "-q", str(repo)])
        (repo / "owned.txt").write_text("base\n")
        self.run_command(["git", "-C", str(repo), "add", "owned.txt"])
        self.run_command(["git", "-C", str(repo), "commit", "-qm", "fixture base"])
        self.run_command(["git", "-C", str(repo), "branch", "-M", "main"])
        for role, scoped in (("implementer", True), ("implementer", False), ("reviewer", False)):
            with self.subTest(role=role, scoped=scoped):
                session = f"delivery-{role}-{int(scoped)}"
                worktree = self.root / f"worker {session}"
                args = ["bash", str(SCRIPTS / "spawn-worker.sh"), "--dry-run", "--no-orca-mode",
                        "--project", str(repo), "--worktree", str(worktree), "--session", session,
                        "--branch", "codex/" + session, "--base-ref", "main", "--role", role,
                        "--worker-backend", "claude-code", "--command", str(fake_claude),
                        "--no-trust-auto", "--no-permission-auto", "--no-external-imports-auto",
                        "--verify-cmd", "git diff --check"]
                if scoped:
                    args += ["--allow-paths", "owned.txt"]
                result = self.run_command(args)
                lines = [line for line in result.stdout.splitlines()
                         if line.startswith("SPAWN_WORKER_DRY_RUN_LAUNCH_SH:")]
                self.assertEqual(len(lines), 1, result.stdout)
                fields = dict(item.split("=", 1) for item in shlex.split(lines[0])[1:])
                command = shlex.split(fields["command"])
                bindings = dict(item.split("=", 1) for item in command if item.startswith((
                    "SCOPE_GUARD_SESSION_ROOT=", "WORKER_INSTALL_AUTH_FILE=")))
                context = worktree / ".claude" / "agent-sessions" / session
                self.assertFalse(worktree.exists(), "dry-run must not create the future worktree")
                self.assertEqual(bindings["WORKER_INSTALL_AUTH_FILE"],
                                 str(context / "INSTALL_AUTHORIZATION.json"))
                if scoped or role == "reviewer":
                    self.assertEqual(bindings["SCOPE_GUARD_SESSION_ROOT"], str(context))
                else:
                    self.assertNotIn("SCOPE_GUARD_SESSION_ROOT", bindings)
                # Emulate only the already-created Session Context at worker time,
                # then execute the actual snippet captured from the real Task call.
                context.mkdir(parents=True)
                (context / "INSTALL_AUTHORIZATION.json").write_text("{}")
                resolved = self.run_command(["bash", "-c", snippet], env={**self.env, **bindings})
                self.assertEqual(resolved.stdout.splitlines(), [str(context), str(context) + "/."])
        self.assert_no_second_injector()


if __name__ == "__main__":
    missing = [name for name in ("bash", "git", "jq", "python3") if not shutil.which(name)]
    if missing:
        raise SystemExit("Missing test dependencies (no install attempted): " + ", ".join(missing))
    unittest.main(verbosity=2)
