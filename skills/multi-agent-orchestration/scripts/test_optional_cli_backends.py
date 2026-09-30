#!/usr/bin/env python3
"""Run rendered commands against isolated argv consumers; never call a model."""
from pathlib import Path
import importlib.util
import json
import os
import shlex
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('worker_command_validator', SCRIPTS / 'validate-worker-command.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class OptionalBackends(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mao-cli-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'private config'
        self.config.mkdir()
        self.prompt = self.root / 'task prompt.md'
        self.prompt.write_text('任务正文 "quote" ; $(touch should-not-exist)\n第二行\n')
        self.bins = {}
        for backend, relative in {
            'minimax-code': 'MiniMax Code bin/mcode',
            'zcode-cli': 'ZCode bin/zcode',
            'qoder-cn': 'Standalone CN bin/qoderclicn',
            'qwenwork-cn': 'QwenWorkCN.app/Contents/Resources/bin/qoderclicn',
            'retired': 'QoderWork CN.app/Contents/Resources/bin/qoderclicn',
        }.items():
            p = self.root / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps({"argv":sys.argv[1:],"stdin":sys.stdin.read() if "--input" in sys.argv else ""}))\n')
            p.chmod(0o755)
            self.bins[backend] = p

    def render(self, backend, *args):
        extra = ['--config-dir', str(self.config)] if backend == 'qwenwork-cn' else []
        return subprocess.run(['bash', str(SCRIPTS / 'render-runtime-profile.sh'), '--backend', backend,
            '--bin', str(self.bins.get(backend, self.bins['qoder-cn'])), *extra, *args,
            '--output', 'command'], text=True, capture_output=True)

    def validate(self, backend, command):
        return subprocess.run(['python3', str(SCRIPTS / 'validate-worker-command.py'), '--backend', backend,
            '--command', command, '--trusted-claude-wrapper', str(SCRIPTS / 'claude-provider-env.sh')],
            text=True, capture_output=True)

    def execute(self, backend, mode='batch', *args):
        rendered = self.render(backend, '--mode', mode, '--prompt-file', str(self.prompt), *args)
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        command = rendered.stdout.strip()
        checked = self.validate(backend, command)
        self.assertEqual(checked.returncode, 0, checked.stdout)
        result = subprocess.run(['bash', '-c', command], text=True, capture_output=True, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / 'should-not-exist').exists())
        return json.loads(result.stdout)

    def test_minimax_batch_stdin_and_model(self):
        result = self.execute('minimax-code', 'batch', '--model', 'custom_provider:work/model-id')
        self.assertEqual(result['stdin'], self.prompt.read_text())
        self.assertEqual(result['argv'], ['exec','--permission','smart','--output-format','stream-json',
            '--model','custom_provider:work/model-id','--input','-'])

    def test_minimax_tui_model_only(self):
        self.assertEqual(self.execute('minimax-code', 'interactive', '--model', 'provider/model')['argv'],
            ['-m','provider/model'])
        self.assertEqual(self.render('minimax-code', '--permission-mode', 'full').returncode, 64)

    def test_zcode_safe_default_and_prompt(self):
        self.assertEqual(self.execute('zcode-cli')['argv'], ['--mode','build','--prompt',self.prompt.read_text().rstrip('\n')])
        self.assertEqual(self.execute('zcode-cli','interactive')['argv'], ['--mode','build'])
        self.assertEqual(self.render('zcode-cli','--model','guessed-model').returncode, 64)

    def test_qoder_batch_and_permission(self):
        result = self.execute('qoder-cn','batch','--model','test-model')['argv']
        self.assertIn('auto', result)
        self.assertIn('stream-json', result)
        self.assertNotIn('--dangerously-skip-permissions', result)
        self.assertEqual(result[-1],self.prompt.read_text().rstrip('\n'))
        self.assertEqual(self.render('qoder-cn','--permission-mode','acceptEdits').returncode,64)

    def test_qwen_config_bound_in_real_argv(self):
        result = self.execute('qwenwork-cn')['argv']
        self.assertEqual(result[result.index('--config-dir')+1], str(self.config.resolve()))
        self.assertEqual(result[-1], self.prompt.read_text().rstrip('\n'))

    def test_qwen_config_cannot_bypass_renderer(self):
        command = shlex.quote(str(self.bins['qwenwork-cn']))
        for suffix in ('', ' --config-dir relative', ' --config-dir /missing/config',
                ' --config-dir ' + shlex.quote(str(self.config)) + ' --config-dir /tmp'):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.validate('qwenwork-cn', command+suffix).returncode,64)
        r = subprocess.run(['bash',str(SCRIPTS/'render-runtime-profile.sh'),'--backend','qwenwork-cn',
            '--output','command'],capture_output=True,text=True)
        self.assertEqual(r.returncode,64)

    def test_same_name_product_identity(self):
        qwen=shlex.quote(str(self.bins['qwenwork-cn']))+' --config-dir '+shlex.quote(str(self.config.resolve()))
        self.assertEqual(self.validate('qoder-cn',qwen).returncode,64)
        self.assertEqual(self.validate('qwenwork-cn',shlex.quote(str(self.bins['qoder-cn']))).returncode,64)
        self.assertEqual(self.validate('minimax-code',shlex.quote(str(self.bins['qoder-cn']))).returncode,64)

    def test_retired_alias_and_symlink_rejected(self):
        symlink=self.root/'qoderclicn'
        symlink.symlink_to(self.bins['retired'])
        self.assertEqual(self.validate('qoder-cn',shlex.quote(str(symlink))).returncode,64)
        for backend in ('qoderwork-cn','qoderwork','qoder'):
            self.assertEqual(self.render(backend).returncode,64)
        r=subprocess.run(['bash',str(SCRIPTS/'qoderclicn-interactive-spawn.sh')],capture_output=True,text=True)
        self.assertEqual(r.returncode,64)
        self.assertIn('retired',r.stderr)

    def test_policy_support_is_not_default_selection(self):
        policy=json.loads((SCRIPTS.parent/'config/harness-backend-policy.json').read_text())
        selection=policy['dispatch_selection']
        self.assertEqual(selection['default_backends'],['claude-code','codex'])
        self.assertEqual(selection['priority_optional_backends'],['zcode-cli','minimax-code'])
        for optional in selection['explicit_only_backends']:
            self.assertNotIn(optional,selection['default_backends'])
            for host in ('claude-code','codex','hermes'):
                self.assertIn(optional,policy['hosts'][host])
        for host in ('minimax-code','zcode-cli','qoder-cn','qwenwork-cn','qoderwork-cn'):
            self.assertNotIn(host,policy['hosts'])
        self.assertEqual(policy['hosts']['codebuddy'],['codebuddy'])
        example=json.loads((SCRIPTS.parent/'config/orchestration-personal.example.json').read_text())
        self.assertEqual(example['dispatch_selection'],selection)
        for chain in example['quota_aware_routing']['tier_policy'].values():
            for optional in selection['explicit_only_backends']:
                self.assertNotIn(optional,chain)

    def test_new_worker_ancestry_never_gains_pm_authority(self):
        for frame, expected in (
            ('/usr/local/bin/mcode','minimax-code'),
            ('/opt/tools/mcode','minimax-code'),
            ('/applications/minimax code.app/contents/macos/mcode','minimax-code'),
            ('/users/demo/.minimax-code/releases/1/lib/node_modules/@minimax-ai/code/cli.js','minimax-code'),
            ('/usr/local/bin/zcode','zcode-cli'),
            ('/opt/tools/zcode','zcode-cli'),
            ('/applications/qoder cn.app/contents/macos/qoder','qoder-cn'),
            ('/repos/zcode-cli/bin/zcode.mjs','zcode-cli'),
            ('/repos/zcode-cli/dist/cli.js','zcode-cli'),
            ('/repos/zcode-cli/bin/zcode.js','zcode-cli'),
            ('/users/demo/.zcode/runtime/current/bin/zcode.mjs','zcode-cli'),
        ):
            with self.subTest(frame=frame):
                r=subprocess.run(['bash','-c','source "$1"; pm_harness_candidate_for_frame "$2"',
                    'check',str(SCRIPTS/'harness-backend-policy.sh'),frame],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertEqual(r.stdout.strip(),expected)
                r=subprocess.run(['bash','-c','source "$1"; allowed_worker_backends_for_chain_json "$2"',
                    'check',str(SCRIPTS/'harness-backend-policy.sh'),json.dumps(['codex',expected])],capture_output=True,text=True)
                self.assertEqual(r.returncode,64,r.stdout+r.stderr)
                self.assertIn('least-privilege intersection',r.stderr)

    def test_retired_ancestry_is_not_skipped(self):
        cmd='source "$1"; retired=$(pm_harness_candidate_for_frame "/applications/qoderwork cn.app/contents/bin/qoderclicn"); [ "$retired" = qoderwork-cn ]; allowed_worker_backends_for_chain_json "[\\\"codex\\\",\\\"$retired\\\"]"'
        r=subprocess.run(['bash','-c',cmd,'check',str(SCRIPTS/'harness-backend-policy.sh')],capture_output=True,text=True)
        self.assertEqual(r.returncode,64,r.stdout + r.stderr)
        self.assertIn("least-privilege intersection", r.stderr)
        # Independently prove that recognition succeeded, not just that the script errored.
        r=subprocess.run(['bash','-c','source "$1"; pm_harness_candidate_for_frame "/applications/qoderwork cn.app/bin/qoderclicn"','check',str(SCRIPTS/'harness-backend-policy.sh')],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.strip(),'qoderwork-cn')


if __name__=='__main__':
    unittest.main()
