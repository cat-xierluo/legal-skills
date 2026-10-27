from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import teaching_demo as demo


class TeachingDemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.root = self.base / 'state'
        self.root.mkdir()

    def cli(self, *args):
        env = dict(os.environ)
        env['SELF_EVOLVE_DATA_ROOT'] = str(self.root)
        env.pop('CODEX_HOME', None)
        env.pop('ZCODE_DATA_BASE_DIR', None)
        proc = subprocess.run([sys.executable, str(demo.WORKFLOW), *args],
                              capture_output=True, text=True, env=env)
        payload = json.loads(proc.stdout)
        # rc=1 means scan finished with failures (partial), which is a valid
        # teaching scenario; rc=2 means a hard CLI error and fails the test.
        self.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
        return payload

    def test_fixtures_are_synthetic_and_complete(self):
        files = demo.build_fixtures(self.home)
        self.assertEqual(set(files), {'claude', 'codex', 'workbuddy', 'codebuddy',
                                      'gemini', 'zcode', 'unsupported', 'workbuddy-trace'})
        for name in ('claude', 'codex', 'workbuddy', 'codebuddy', 'gemini', 'zcode'):
            self.assertTrue(files[name].exists(), name)
        self.assertTrue((self.home / '.qwen').is_dir())

    def test_broken_and_unknown_payload_failures_visible(self):
        demo.build_fixtures(self.home)
        demo.broken_fixture(self.home)
        demo.unknown_payload_fixture(self.home)
        result = self.cli('scan', '--home', str(self.home), '--max-sessions', '200')
        packet = json.loads(Path(result['packet']).read_text())
        self.assertGreaterEqual(packet['stats']['failed'], 1)
        self.assertTrue(packet['failures'])
        self.assertTrue(all('error' in f and 'session_key' in f for f in packet['failures']))

    def test_two_rounds_incremental_and_isolated_state_root(self):
        demo.build_fixtures(self.home)
        first = self.cli('scan', '--home', str(self.home), '--max-sessions', '200')
        packet = json.loads(Path(first['packet']).read_text())
        self.assertGreaterEqual(packet['stats']['new'], 6)
        second = self.cli('scan', '--home', str(self.home), '--max-sessions', '200')
        packet2 = json.loads(Path(second['packet']).read_text())
        self.assertGreaterEqual(packet2['stats']['unchanged'], 6)
        # All state lives under the isolated root, never under the skill tree.
        self.assertTrue((self.root / 'ledger.sqlite').exists() or
                        any(self.root.rglob('ledger.sqlite')))
        for p in self.root.rglob('*'):
            self.assertNotIn('self-evolve-teaching', str(p.resolve()).split('/scripts/')[0].replace(str(self.root), ''))

    def test_summary_uses_real_packet_fields(self):
        demo.build_fixtures(self.home)
        result = self.cli('scan', '--home', str(self.home), '--max-sessions', '200')
        result['_returncode'] = 0
        summary = demo.summarize(result, result['packet'], 'r1')
        for key in ('stats', 'pending_analysis', 'analysis_status', 'coverage',
                    'failures', 'cumulative', 'runtimes_with_evidence'):
            self.assertIn(key, summary)
        packet = json.loads(Path(result['packet']).read_text())
        self.assertEqual(summary['analysis_status'], packet['analysis_status'])
        self.assertIn(packet['analysis_status'], {'awaiting_agent', 'no_pending_evidence'})
        for c in summary['coverage']:
            self.assertIn('runtime', c)
            self.assertIn('status', c)

    def test_classroom_round_shows_multiple_runtimes_with_evidence(self):
        # The teaching story is "one scan covers many runtimes", so the demo
        # must surface evidence from more than one runtime in the first round.
        demo.build_fixtures(self.home)
        result = self.cli('scan', '--home', str(self.home), '--max-sessions', '50')
        packet = json.loads(Path(result['packet']).read_text())
        runtimes = {e['runtime'] for e in packet['evidence']}
        self.assertGreaterEqual(len(runtimes), 4)
        for name in ('claude', 'codex', 'workbuddy', 'codebuddy', 'gemini', 'zcode'):
            self.assertIn(name, runtimes)

    def test_no_real_home_writes(self):
        # The fixture builder must only write inside the given home; the real
        # user home must stay untouched by import-time side effects.
        demo.build_fixtures(self.home)
        self.assertFalse((Path.home() / '.qwen' / 'sessions' / 'teaching-demo-marker').exists())

    def test_keep_preserves_the_demo_directory_after_main_returns(self):
        keep_root = self.base / 'kept-demo'
        keep_root.mkdir()
        expected = keep_root / 'self-evolve-teaching-demo'
        expected.mkdir()
        argv = [sys.argv[0], '--rounds', '1', '--keep']
        with mock.patch.object(tempfile, 'mkdtemp', return_value=str(expected)), \
             mock.patch.object(sys, 'argv', argv):
            self.assertEqual(demo.main(), 0)
        self.assertTrue(expected.is_dir())
        self.assertTrue(any(expected.glob('state/runtime/public-workflow/runs/*/*.html')))
        shutil.rmtree(expected)

    def test_kept_demo_and_followup_commands_are_isolated_across_processes(self):
        temporary = self.base / 'demo-tmp'
        temporary.mkdir()
        default_root = self.base / 'unrelated-state'
        default_root.mkdir()
        sentinel = default_root / 'sentinel'
        sentinel.write_bytes(b'unrelated ledger stays untouched')
        env = dict(os.environ, HOME=str(self.home), TMPDIR=str(temporary),
                   SELF_EVOLVE_DATA_ROOT=str(default_root),
                   SELF_EVOLVE_REVIEW_ROOT=str(default_root / 'review'),
                   SKILL_EVOLVE_STATE_ROOT=str(default_root / 'runtime'))
        for key in ('CODEX_HOME', 'ZCODE_DATA_BASE_DIR', 'SELF_EVOLVE_SKILL_ROOT',
                    'SELF_EVOLVE_STATE_ROOT', 'SELF_EVOLVE_RUNTIME_ROOT'):
            env.pop(key, None)
        proc = subprocess.run([sys.executable, '-S', str(SCRIPTS / 'teaching_demo.py'),
                               '--keep', '--rounds', '1'], env=env,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        retained = list(temporary.glob('self-evolve-teaching-*'))
        self.assertEqual(len(retained), 1)
        demo_root = retained[0]
        self.assertTrue(list(demo_root.glob('state/runtime/public-workflow/runs/*/analysis-*.html')))
        followup_env = dict(env, SELF_EVOLVE_DATA_ROOT=str(demo_root / 'state'))
        for key in ('SELF_EVOLVE_REVIEW_ROOT', 'SKILL_EVOLVE_STATE_ROOT'):
            followup_env.pop(key, None)
        scan = subprocess.run([sys.executable, '-S', str(demo.WORKFLOW), 'scan',
                               '--home', str(demo_root / 'home'), '--max-sessions', '200'],
                              env=followup_env, capture_output=True, text=True, timeout=60)
        self.assertEqual(scan.returncode, 1, scan.stdout + scan.stderr)  # two intentional failures
        self.assertGreaterEqual(json.loads(scan.stdout)['stats']['unchanged'], 6)
        status = subprocess.run([sys.executable, '-S', str(demo.WORKFLOW), 'status'],
                                env=followup_env, capture_output=True, text=True, timeout=60)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)['analysis_count'], 1)
        self.assertEqual(list(default_root.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b'unrelated ledger stays untouched')

    def test_demo_without_keep_cleans_its_own_directory_after_exit(self):
        temporary = self.base / 'demo-tmp'
        temporary.mkdir()
        env = dict(os.environ, HOME=str(self.home), TMPDIR=str(temporary),
                   SELF_EVOLVE_DATA_ROOT=str(self.root))
        proc = subprocess.run([sys.executable, '-S', str(SCRIPTS / 'teaching_demo.py'),
                               '--rounds', '1'], env=env,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(list(temporary.glob('self-evolve-teaching-*')))


if __name__ == '__main__':
    unittest.main()
