#!/usr/bin/env python3
"""Offline real-script smoke identity and readonly-boundary consumers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SMOKE = HERE / "smoke-orca-worker.sh"
SPAWN = HERE / "spawn-worker.sh"


def executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o700)


class SmokeIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="smoke-identity-selftest-")
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "current-repo"
        self.repo.mkdir()
        for argv in (["git", "init", "-q"], ["git", "config", "user.name", "Smoke Test"],
                     ["git", "config", "user.email", "smoke@example.invalid"],
                     ["git", "commit", "-q", "--allow-empty", "-m", "fixture"]):
            subprocess.run(argv, cwd=self.repo, check=True, capture_output=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "orca.jsonl"
        self.spawn_log = self.root / "spawn.jsonl"
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        SMOKE_FIXTURE_REPO=str(self.repo), SMOKE_FIXTURE_LOG=str(self.log),
                        SMOKE_FIXTURE_SPAWN_LOG=str(self.spawn_log))
        # The real smoke's readonly proxy calls only this isolated fixture CLI.
        executable(self.bin / "orca", "#!" + sys.executable + "\n" + r'''
import json, os, pathlib, sys
args=sys.argv[1:]
with pathlib.Path(os.environ['SMOKE_FIXTURE_LOG']).open('a') as f:
    f.write(json.dumps(args)+'\n')
if args == ['status', '--json']:
    payload={'ok':True,'result':{'runtime':{'reachable':True,'runtimeId':'fixture-runtime','appVersion':'1.4.218',
        'capabilities':['terminal.multiplex.v1','orchestration.contract.v1']}}}
elif args == ['worktree', 'current', '--json']:
    payload={'ok':True,'result':{'worktree':{'id':'fixture::'+os.environ['SMOKE_FIXTURE_REPO'],
        'repoId':'fixture','path':os.environ['SMOKE_FIXTURE_REPO']}}}
elif args == ['worktree', 'ps', '--limit', '100', '--json']:
    payload={'ok':True,'result':{'worktrees':[{'id':'fixture::'+os.environ['SMOKE_FIXTURE_REPO'],
        'repoId':'fixture','path':os.environ['SMOKE_FIXTURE_REPO']}]}}
elif len(args)==5 and args[:3]==['terminal','show','--terminal'] and args[4]=='--json':
    raise SystemExit(1)
else:
    raise SystemExit(95)
print(json.dumps(payload))
''')
        self.scripts = self.root / "scripts"
        self.scripts.mkdir()
        shutil.copyfile(SMOKE, self.scripts / SMOKE.name)
        # Capture actual smoke argv, then execute the unchanged production spawn
        # entry. No substituted spawn response or occupied-worktree gate.
        executable(self.scripts / "spawn-worker.sh", "#!" + sys.executable + "\n" +
                   "import json, os, pathlib, re, sys\n"
                   "args=sys.argv[1:]\n"
                   "with pathlib.Path(os.environ['SMOKE_FIXTURE_SPAWN_LOG']).open('a') as f: f.write(json.dumps(args)+'\\n')\n"
                   "if os.environ.get('SMOKE_FIXTURE_COLLISION') and not pathlib.Path(os.environ['SMOKE_FIXTURE_SPAWN_LOG']).read_text().count('\\n') > 1:\n"
                   "  branch=args[args.index('--branch')+1]\n"
                   "  safe=re.sub(r'[^A-Za-z0-9._-]', '', re.sub(r'[/\\s]', '-', branch))\n"
                   "  path=pathlib.Path(os.environ['SMOKE_FIXTURE_REPO'])/'.claude/worktrees'/('tmux-'+safe)\n"
                   "  path.mkdir(parents=True); (path/'keep-marker').write_text('preserve')\n"
                   f"os.execv({shutil.which('bash')!r}, [{shutil.which('bash')!r}, {str(SPAWN)!r}, *args])\n")
        # smoke invokes its sibling through bash, so use a shell exec bridge.
        launcher = self.scripts / "spawn-worker.sh"
        launcher.rename(self.scripts / "capture-spawn.py")
        executable(launcher, f"#!/usr/bin/env bash\nexec '{sys.executable}' '{self.scripts / 'capture-spawn.py'}' \"$@\"\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def invoke(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(self.scripts / SMOKE.name)], cwd=self.repo,
                              env=self.env, capture_output=True, text=True, timeout=60)

    def assert_readonly(self) -> None:
        for args in map(json.loads, self.log.read_text().splitlines()):
            self.assertTrue(args in (["status", "--json"], ["worktree", "current", "--json"],
                                    ["worktree", "ps", "--limit", "100", "--json"])
                            or (len(args) == 5 and args[:3] == ["terminal", "show", "--terminal"]
                                and args[4] == "--json"), args)

    def test_repeated_real_smoke_uses_private_round_identity(self) -> None:
        rounds = []
        for _ in range(2):
            self.spawn_log.unlink(missing_ok=True)
            result = self.invoke()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SMOKE_SENDER_REFUSAL: missing_exit=3 invalid_exit=3", result.stdout)
            calls = list(map(json.loads, self.spawn_log.read_text().splitlines()))
            self.assertEqual(len(calls), 5)
            branches = [args[args.index("--branch") + 1] for args in calls]
            sessions = [args[args.index("--session") + 1] for args in calls]
            self.assertEqual(branches[:3], [branches[0]] * 3)
            self.assertEqual(branches[3:], [branches[0] + "-supervised", branches[0] + "-wave"])
            self.assertEqual(sessions[3:], [sessions[0] + "-supervised", sessions[0] + "-wave"])
            self.assertNotEqual(branches[0], "feat/smoke-orca")
            self.assertFalse((self.repo / ".claude/agent-sessions").exists())
            rounds.append((branches[0], sessions[0]))
        self.assertNotEqual(rounds[0], rounds[1])
        self.assert_readonly()

    def test_collision_still_rejected_without_retry_or_removal(self) -> None:
        self.env["SMOKE_FIXTURE_COLLISION"] = "1"
        result = self.invoke()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("EXISTING_WORKTREE_REQUIRES_RECOVERY", result.stdout)
        calls = list(map(json.loads, self.spawn_log.read_text().splitlines()))
        self.assertEqual(len(calls), 1)
        markers = list(self.repo.glob(".claude/worktrees/*/keep-marker"))
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0].read_text(), "preserve")
        self.assert_readonly()

    def test_worktree_path_matches_production_branch_mapping(self) -> None:
        # Execute the real initialization block, before dependencies or RPC.
        header = SMOKE.read_text().split("assert_contains()", 1)[0]
        command = header + '\nprintf "%s\\n" "$TMP_ROOT" "$BRANCH" "$WT" "$SESSION" "$CTX"\n'
        header_path = self.root / "namespace.sh"
        header_path.write_text(command)
        result = subprocess.run(["bash", str(header_path)], capture_output=True, text=True, check=True)
        temp, branch, worktree, session, context = result.stdout.splitlines()
        try:
            safe = re.sub(r"[^A-Za-z0-9._-]", "", re.sub(r"[/\s]", "-", branch))
            self.assertEqual(worktree, temp + "/repo/.claude/worktrees/tmux-" + safe)
            self.assertEqual(context, worktree + "/.claude/agent-sessions/" + session)
        finally:
            shutil.rmtree(temp)

    def test_real_readonly_proxy_blocks_mutation(self) -> None:
        proxy = SMOKE.read_text().split("<<'READONLY'\n", 1)[1].split("\nREADONLY", 1)[0]
        path = self.root / "readonly-proxy"
        executable(path, proxy + "\n")
        env = dict(self.env, SMOKE_REAL_ORCA_BIN=str(self.bin / "orca"),
                   SMOKE_ORCA_LOG=str(self.root / "proxy.log"))
        result = subprocess.run([str(path), "terminal", "create", "--json"],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 95)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
