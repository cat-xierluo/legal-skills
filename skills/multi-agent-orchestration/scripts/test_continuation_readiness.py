#!/usr/bin/env python3
"""Fault injection and real Wave-entry consumers, without real Orca mutations."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
CHECK = HERE / 'continuation-readiness.py'
WAVE = HERE / 'orca-wave-prepare.sh'


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.task = self.project / 'TASKS.md'
        self.task.write_text('# CONT-TEST\n持续推进原卡，返回后独审。\n')
        self.config = self.root / 'codex' / 'automations'
        self.job = self.config / 'project-pm' / 'automation.toml'
        self.job.parent.mkdir(parents=True)
        self.contract = self.project / 'continuation.json'
        self.data = {
            'schema': 'multi-agent-orchestration.continuation.v1',
            'project_root': str(self.project), 'task_source': str(self.task),
            'pm_thread_id': 'original-pm', 'automation_id': 'project-pm',
            'authorization_ref': 'task:CONT-TEST', 'max_interval_seconds': 1200,
            'on_worker_return': ['independent_review', 'task_writeback', 'repair_or_next_ready'],
        }
        self.write_contract()
        self.write_job()
        self.manifest = self.root / 'wave.json'
        self.manifest.write_text(json.dumps({'objective': 'original task',
            'execution_policy': 'continuous', 'continuation_contract': str(self.contract),
            'tasks': [{'key': 'engineering', 'spec': 'Change owned code; scoped test.'}]}))
        self.log = self.root / 'orca.log'
        self.fake = self.root / 'orca-fixture'
        self.fake.write_text('#!' + sys.executable + '\n' + '''
import json, os, sys
with open(os.environ['FIXTURE_LOG'], 'a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\\n')
args=sys.argv[1:]; key=tuple(args[:2]); meta={'runtimeId':'fixture-runtime'}
if key==('status','--json'):
    result={'runtime':{'reachable':True,'runtimeId':'fixture-runtime'}}
elif key==('terminal','show'):
    result={'terminal':{'handle':'term-pm','connected':True,'writable':True,'orphaned':False,'exitCause':None}}
elif key[0]=='orchestration' and key[1] in ('run-create','run-use','run-current'):
    result={'run':{'id':'run-fixture','coordinator_handle':'term-pm'}}
elif key==('orchestration','task-create'):
    result={'task':{'id':'task-fixture'}}
else:
    raise SystemExit(97)
print(json.dumps({'ok':True,'result':result,'_meta':meta}))
''')
        self.fake.chmod(0o700)
        self.env = dict(os.environ, CODEX_HOME=str(self.config.parent),
                        ORCA_CLI_COMMAND=str(self.fake), FIXTURE_LOG=str(self.log))

    def write_contract(self):
        self.contract.write_text(json.dumps(self.data))

    def write_job(self, **changes):
        values = {'id': 'project-pm', 'kind': 'heartbeat', 'status': 'ACTIVE',
                  'target_thread_id': 'original-pm', 'rrule': 'FREQ=MINUTELY;INTERVAL=20',
                  'prompt': '读取原任务 ' + str(self.task) + '，独审、写回并继续合法队列。'}
        values.update(changes)
        self.job.write_text('\n'.join(k + ' = ' + json.dumps(v, ensure_ascii=False) for k, v in values.items()) + '\n')

    def check(self, *args):
        return subprocess.run([sys.executable, '-B', str(CHECK), *args],
                              capture_output=True, text=True, env=self.env, timeout=10)

    def wave(self):
        return subprocess.run(['bash', str(WAVE), '--manifest', str(self.manifest), '--from', 'term-pm'],
                              capture_output=True, text=True, env=self.env, timeout=15)

    def assert_before_orca(self, code):
        result = self.wave()
        self.assertEqual(result.returncode, 64, result.stderr)
        self.assertIn(code, result.stderr)
        self.assertFalse(self.log.exists(), 'Rejected preflight contacted Orca')

    def test_real_config_read_is_read_only_and_never_claims_autonomy(self):
        before = self.job.read_bytes()
        self.data['autonomous_verified'] = True  # Producer cannot certify itself.
        self.data['resumed_by'] = 'human'
        self.write_contract()
        result = self.check('--contract', str(self.contract))
        self.assertEqual(result.returncode, 0, result.stdout)
        observed = json.loads(result.stdout)
        self.assertEqual(observed['readiness'], 'CONFIGURED_NOT_PROVEN_AUTONOMOUS')
        self.assertFalse(observed['autonomous_verified'])
        self.assertEqual(observed['automatic_review_and_continuation'], 'NOT_VERIFIED')
        self.assertEqual(observed['automation_config_sha256'], hashlib.sha256(before).hexdigest())
        self.assertEqual(before, self.job.read_bytes())

    def test_continuous_positive_executes_real_wave_entry(self):
        result = self.wave()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['tasks'][0]['task_id'], 'task-fixture')
        calls = [json.loads(x) for x in self.log.read_text().splitlines()]
        self.assertEqual(sum(x[:2] == ['orchestration', 'run-create'] for x in calls), 1)
        self.assertEqual(sum(x[:2] == ['orchestration', 'task-create'] for x in calls), 1)
        self.assertIn('CONFIGURED_NOT_PROVEN_AUTONOMOUS', result.stderr)

    def test_legacy_one_wave_does_not_need_a_heartbeat(self):
        value = json.loads(self.manifest.read_text())
        value.pop('execution_policy'); value.pop('continuation_contract')
        self.manifest.write_text(json.dumps(value))
        self.job.unlink()
        self.assertEqual(self.wave().returncode, 0)

    def test_host_configuration_faults_reject_before_any_orca_call(self):
        cases = [({'status': 'PAUSED'}, 'AUTOMATION_NOT_ACTIVE'),
                 ({'target_thread_id': 'macro-pm'}, 'PM_TARGET_MISMATCH'),
                 ({'id': 'other-job'}, 'AUTOMATION_IDENTITY_MISMATCH'),
                 ({'kind': 'cron'}, 'AUTOMATION_IDENTITY_MISMATCH'),
                 ({'prompt': '仅宏观汇总，不指向原任务'}, 'TASK_BINDING_MISSING'),
                 ({'prompt': str(self.task) + '.backup'}, 'TASK_BINDING_MISSING'),
                 ({'prompt': str(self.task) + '备份'}, 'TASK_BINDING_MISSING'),
                 ({'prompt': str(self.task) + '📁'}, 'TASK_BINDING_MISSING'),
                 ({'prompt': str(self.task) + '/another-card'}, 'TASK_BINDING_MISSING'),
                 ({'rrule': 'FREQ=HOURLY'}, 'INTERVAL_TOO_LONG'),
                 ({'rrule': 'FREQ=MINUTELY;INTERVAL=5;COUNT=1'}, 'SCHEDULE_UNVERIFIABLE'),
                 ({'rrule': 'FREQ=MINUTELY;INTERVAL=0'}, 'SCHEDULE_UNVERIFIABLE'),
                 ({'rrule': 'FREQ=MINUTELY;INTERVAL=5;INTERVAL=20'}, 'SCHEDULE_UNVERIFIABLE')]
        for changes, expected in cases:
            with self.subTest(changes=changes):
                self.write_job(**changes)
                self.assert_before_orca(expected)

    def test_contract_faults_reject_before_any_orca_call(self):
        baseline = dict(self.data)
        cases = [('schema', 'future.v99', 'SCHEMA_UNSUPPORTED'),
                 ('pm_thread_id', '', 'PM_OWNER_REQUIRED'),
                 ('authorization_ref', '', 'AUTHORIZATION_REF_REQUIRED'),
                 ('on_worker_return', ['send_next'], 'RETURN_FLOW_REQUIRED'),
                 ('max_interval_seconds', True, 'INTERVAL_BUDGET_REQUIRED'),
                 ('automation_id', '../project-pm', 'AUTOMATION_ID_INVALID'),
                 ('task_source', 'TASKS.md', 'ABSOLUTE_PATH_REQUIRED')]
        for key, value, expected in cases:
            with self.subTest(key=key):
                self.data = dict(baseline); self.data[key] = value; self.write_contract()
                self.assert_before_orca(expected)

    def test_missing_job_rejects_without_fabricating_readiness(self):
        self.job.unlink()
        self.assert_before_orca('CONTINUATION_INPUT_UNREADABLE')

    def test_duplicate_policy_does_not_silently_become_one_wave(self):
        self.manifest.write_text('{"objective":"x","tasks":[{"key":"x","spec":"x"}],'
                                 '"execution_policy":"continuous","execution_policy":"one_wave"}')
        self.assert_before_orca('DUPLICATE_FIELD')

    def test_malformed_toml_does_not_echo_private_text(self):
        self.job.write_text('id = "PRIVATE_FIXTURE_SECRET"\nthis is broken')
        result = self.check('--contract', str(self.contract))
        self.assertEqual(result.returncode, 64)
        self.assertNotIn('PRIVATE_FIXTURE_SECRET', result.stdout + result.stderr)

    def test_config_symlink_escape_rejected(self):
        elsewhere = self.root / 'outside.toml'
        self.job.rename(elsewhere); self.job.symlink_to(elsewhere)
        self.assert_before_orca('AUTOMATION_PATH_ESCAPE')

    def test_explicit_one_wave_has_no_toml_dependency(self):
        manifest = json.loads(self.manifest.read_text())
        manifest['execution_policy'] = 'one_wave'; manifest.pop('continuation_contract')
        self.manifest.write_text(json.dumps(manifest))
        self.job.unlink()
        self.assertEqual(self.wave().returncode, 0)
        # Simulate an interpreter without tomllib at the exact production entry.
        code = """import builtins, runpy, sys
original = builtins.__import__
def importer(name, *args, **kwargs):
    if name == 'tomllib': raise ImportError('fixture: unavailable')
    return original(name, *args, **kwargs)
builtins.__import__ = importer
sys.argv = [sys.argv[1], '--wave-manifest', sys.argv[2]]
runpy.run_path(sys.argv[0], run_name='__main__')
"""
        result = subprocess.run([sys.executable, '-B', '-c', code, str(CHECK), str(self.manifest)],
                                capture_output=True, text=True, env=self.env, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['readiness'], 'ONE_WAVE_ONLY')


if __name__ == '__main__':
    unittest.main()
