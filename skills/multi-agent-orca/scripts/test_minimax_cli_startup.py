#!/usr/bin/env python3
"""Exercise native-command parsing and the real Orca launch controller, without models."""
from pathlib import Path
import json
import os
import shlex
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent

class MiniMaxStartup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mao-mm-startup-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prompt = self.root / "task input.md"
        self.prompt.write_text("Write only the fixture nonce.\n")
        self.bin = self.root / "bin space" / "mcode"
        self.bin.parent.mkdir()
        self.bin.write_text("#!/usr/bin/env python3\nimport json,os,sys\nfrom pathlib import Path\nroot=Path(os.environ['FIXTURE_ROOT'])\nwith (root/'bootstrap.jsonl').open('a') as f:f.write(json.dumps({'argv':sys.argv[1:],'stdin':sys.stdin.read() if '--input' in sys.argv else ''})+'\\n')\n(root/'nonce.txt').write_text('fixture-only')\nraise SystemExit(int(os.environ.get('FIXTURE_EXIT','0')))\n")
        self.bin.chmod(0o755)

    def classify(self, command, *extra):
        return subprocess.run(["python3",str(SCRIPTS / "minimax-cli-startup.py"),"--command", command,"--require-input",*extra],text=True,capture_output=True)

    def test_semantic_entrypoint(self):
        for command,mode in [
            ("mcode", "interactive"), ("env NODE_OPTIONS=fixture env WORKER_SESSION_CONTEXT=/fixture mcode", "interactive"), ("mcode --model exec", "interactive"), ("mcode -mexec", "interactive"),
            ("mcode 'echo exec'", "interactive"), ("mcode -- exec", "interactive"),
            ("mcode --session exec", "interactive"), ("mcode 'exec' 'fixture'", "batch"),
            ("mcode --model exec exec 'fixture'", "batch"),
            ("env -u EXAMPLE A=value bash -lc \"exec mcode exec 'fixture'\"", "batch"),
            ("bash -lc \"mcode -m exec\"", "interactive"),
        ]:
            with self.subTest(command=command):
                p=self.classify(command);self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout.strip(),mode)

    def test_invalid_bootstrap_and_opaque_shell(self):
        empty=self.root/'empty';empty.touch()
        for command in ["echo mcode exec", "mcode exec", "mcode exec --model x",
            "mcode exec --input -", "mcode exec --unknown foo", "mcode exec review",
            "mcode exec --input-format unknown 'fixture'", "mcode exec ''", "mcode exec '$UNPROVEN_PROMPT'",
            "mcode exec --input - < " + shlex.quote(str(empty)),
            "mcode exec --input - < /missing/fixture", "mcode exec x && echo duplicate"]:
            with self.subTest(command=command):self.assertEqual(self.classify(command).returncode,64)
        for extra in [("--supervised","1"),("--task-id","task-fixture")]:
            self.assertEqual(self.classify("mcode exec 'fixture'",*extra).returncode,64)

    def test_native_json_input_shape_and_whitespace(self):
        for value in ('fixture JSON task', {'prompt':'fixture JSON task'}):
            self.prompt.write_text(json.dumps(value))
            command='mcode exec --input-format json --input - < '+shlex.quote(str(self.prompt))
            p=self.classify(command);self.assertEqual(p.returncode,0,p.stderr)
        for value in ({'prompt':''}, [], {'wrong':'fixture'}):
            self.prompt.write_text(json.dumps(value))
            self.assertEqual(self.classify(command).returncode,64)
        self.prompt.write_text('  \n')
        self.assertEqual(self.classify('mcode exec --input - < '+shlex.quote(str(self.prompt))).returncode,64)

    def test_positional_substitution_quote_semantics_use_actual_argv(self):
        self.prompt.write_text(json.dumps({'prompt':'fixture JSON task'}))
        self.bin.write_text("#!/usr/bin/env python3\nimport json,sys\nargs=sys.argv[1:]\nraw=sys.stdin.read() if '--input' in args else args[-1]\nprint(json.dumps({'argv':args,'raw_input':raw}))\ntry:\n value=json.loads(raw)\n prompt=value if isinstance(value,str) else value.get('prompt') if isinstance(value,dict) else None\nexcept ValueError:prompt=None\nraise SystemExit(0 if isinstance(prompt,str) and prompt.strip() else 64)\n")
        prefix=shlex.quote(str(self.bin))+' exec --input-format json '
        substitution='$(cat '+shlex.quote(str(self.prompt))+')'
        single_quoted=prefix+shlex.quote(substitution)
        double_quoted=prefix+'"'+substitution+'"'
        stdin=prefix+'--input - < '+shlex.quote(str(self.prompt))
        for command, classifier_rc, consumer_rc in (
            (single_quoted,64,64), (double_quoted,64,0),
            ('bash -lc '+shlex.quote(single_quoted),64,64),
            ('bash -lc '+shlex.quote(double_quoted),64,0),
            (stdin,0,0), ('bash -lc '+shlex.quote(stdin),0,0),
        ):
            with self.subTest(command=command):
                self.assertEqual(self.classify(command).returncode,classifier_rc)
                actual=subprocess.run(['bash','-c',command],text=True,capture_output=True)
                self.assertEqual(actual.returncode,consumer_rc,actual.stderr)
                result=json.loads(actual.stdout)
                if consumer_rc:
                    self.assertEqual(result['argv'][-1],substitution)
                    self.assertEqual(result['raw_input'],substitution)
                else:
                    self.assertEqual(json.loads(result['raw_input']),{'prompt':'fixture JSON task'})

    def test_env_exec_target_is_not_a_shell_builtin(self):
        backend=shlex.quote(str(self.bin))
        for command in ('env exec '+backend+" exec 'fixture'",
            'env FIXTURE=1 env exec '+backend+" exec 'fixture'",
            "'FIXTURE=1' exec env "+backend+" exec 'fixture'",
            'bash -lc '+shlex.quote('env exec '+backend+" exec 'fixture'")):
            with self.subTest(command=command):
                self.assertEqual(self.classify(command).returncode,64)
                actual=subprocess.run(['bash','-c',command],env=dict(os.environ,FIXTURE_ROOT=str(self.root)),text=True,capture_output=True)
                self.assertEqual(actual.returncode,127,actual.stderr)
                self.assertFalse((self.root/'bootstrap.jsonl').exists())
        for command in ('exec env '+backend+" exec 'fixture'",
            'exec env FIXTURE=1 env '+backend+" exec 'fixture'",
            'env FIXTURE=1 bash -lc '+shlex.quote('exec env '+backend+" exec 'fixture'")):
            with self.subTest(command=command):
                self.assertEqual(self.classify(command).returncode,0)
                actual=subprocess.run(['bash','-c',command],env=dict(os.environ,FIXTURE_ROOT=str(self.root)),text=True,capture_output=True)
                self.assertEqual(actual.returncode,0,actual.stderr)
        entries=[json.loads(x) for x in (self.root/'bootstrap.jsonl').read_text().splitlines()]
        self.assertEqual(len(entries),3)
        self.assertTrue(all(entry['argv']==['exec','fixture'] for entry in entries))

    def controller(self, command, wait_valid=True, create_valid=True, child_exit=0, orca_helper=None):
        metadata=self.root/'metadata.json'
        metadata.write_text(json.dumps({'session':{'orca':{'terminal_handle':''}},'runtime':{'worker_backend':'minimax-code','startup':{'observation':'not_observed'}}}))
        script = r"""
set -euo pipefail
SCRIPT_DIR="$1"
WORKTREE="$2"
SESSION=fixture
COMMAND="$3"
METADATA_FILE="$2/metadata.json"
ORCA_MODE=auto
ORCA_WORKTREE_ID=repo-fixture::worker
ORCA_TERMINAL_HANDLE=""
ORCA_SUPERVISED=0
ORCA_TASK_ID=""
ORCA_RUN_ID=""
ORCA_ZCODE_NATIVE_REQUESTS=""
WORKER_BACKEND_CANONICAL=minimax-code
DRY_RUN=0
source "${4:-$SCRIPT_DIR/spawn-worker-orca.sh}"
source "$SCRIPT_DIR/spawn-worker-launch.sh"
orca_cli() {
  printf '%s\n' "$1 $2" >> "$WORKTREE/calls.log"
  case "$1 $2" in
    "terminal create")
      shift 2
      local command=""
      while [ "$#" -gt 0 ]; do
        if [ "$1" = --command ]; then command="$2"; shift 2; else shift; fi
      done
      bash -c "$command" > "$WORKTREE/child.log" 2>&1 || printf '%s\n' "$?" > "$WORKTREE/child-exit"
      if [ "$CREATE_VALID" = 1 ]; then
        printf '%s\n' '{"ok":true,"result":{"terminal":{"handle":"term-fixture"}}}'
      else printf '%s\n' '{"ok":false,"result":{"terminal":{"handle":"term-unproven"}}}'; fi
      ;;
    "terminal wait")
      if [ "$WAIT_VALID" = 1 ]; then printf '%s\n' '{"ok":true,"result":{"wait":{"handle":"term-fixture","condition":"tui-idle","satisfied":true}}}'
      else printf '%s\n' '{"ok":true,"result":{"wait":{"satisfied":null}}}'; fi
      ;;
    "terminal send") printf '%s\n' '{"ok":true}' ;;
    *) return 1 ;;
  esac
}
launch_worker_session
"""
        env=dict(os.environ,FIXTURE_ROOT=str(self.root),WAIT_VALID=str(int(wait_valid)),CREATE_VALID=str(int(create_valid)),FIXTURE_EXIT=str(child_exit))
        p=subprocess.run(['bash','-c',script,'fixture',str(SCRIPTS),str(self.root),command,str(orca_helper or SCRIPTS/"spawn-worker-orca.sh")],env=env,text=True,capture_output=True)
        calls=(self.root/'calls.log').read_text().splitlines() if (self.root/'calls.log').exists() else []
        boots=[json.loads(x) for x in (self.root/'bootstrap.jsonl').read_text().splitlines()] if (self.root/'bootstrap.jsonl').exists() else []
        return p,calls,boots,json.loads(metadata.read_text())

    def test_batch_real_controller_zero_duplicate_send(self):
        command='env FIXTURE_MARKER=exec bash -lc ' + shlex.quote(shlex.quote(str(self.bin))+' exec --permission full --input - < '+shlex.quote(str(self.prompt)))
        p,calls,boots,meta=self.controller(command,wait_valid=False)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(calls,['terminal create'])
        self.assertEqual(len(boots),1)
        self.assertEqual(boots[0]['stdin'],self.prompt.read_text())
        self.assertEqual((self.root/'nonce.txt').read_text(),'fixture-only')
        self.assertEqual(meta['session']['orca']['terminal_handle'],'term-fixture')
        self.assertEqual(meta['session']['orca']['tui_ready_method'],'command_bootstrap_no_tui_wait')
        self.assertEqual(meta['runtime']['startup']['observation'],'terminal_created_execution_unverified')

    def test_interactive_preserves_wait_and_send(self):
        p,calls,boots,meta=self.controller(shlex.quote(str(self.bin))+' --model exec')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(calls,['terminal create','terminal wait','terminal send'])
        self.assertEqual(boots[0]['argv'],['--model','exec'])

    def test_late_wait_failure_preserves_identity(self):
        p,calls,boots,meta=self.controller(shlex.quote(str(self.bin)),wait_valid=False)
        self.assertEqual(p.returncode,64)
        self.assertEqual(calls,['terminal create','terminal wait'])
        self.assertEqual(meta['session']['orca']['terminal_handle'],'term-fixture')

    def test_child_failure_is_not_reported_as_execution_success(self):
        p,calls,boots,meta=self.controller(shlex.quote(str(self.bin))+" exec 'fixture'",child_exit=7)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(calls,['terminal create'])
        self.assertEqual((self.root/'child-exit').read_text().strip(),'7')
        self.assertEqual(meta['runtime']['startup']['observation'],'terminal_created_execution_unverified')

    def test_invalid_create_receipt_does_not_bind_or_send(self):
        p,calls,boots,meta=self.controller(shlex.quote(str(self.bin))+" exec 'fixture'",create_valid=False)
        self.assertEqual(p.returncode,64)
        self.assertEqual(calls,['terminal create'])
        self.assertEqual(meta['session']['orca']['terminal_handle'],'')

if __name__ == '__main__':unittest.main()
