#!/usr/bin/env python3
"""Synthetic captured RPCs; no real Orca/provider lifecycle operations."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import runtime_settlement as rs

SCRIPTS = Path(__file__).resolve().parent
CLI = SCRIPTS / 'runtime-reconcile.py'
LEASE_CLI = SCRIPTS / 'provider-lease.py'
TIME = '2030-01-01T00:00:00Z'


class Fixture:
    def __init__(self, root, *, succeeded=False, required_lease=False):
        self.root = root
        self.binding = {
            'schema_version': rs.BINDING, 'binding_id': 'binding-synthetic', 'cli_argv0': '/synthetic/orca',
            'runtime': {'observer_runtime_id': 'runtime-now', 'worker_runtime_epoch': 'worker-epoch', 'process_incarnation': 'process-one'},
            'run': {'run_id': 'run-one', 'consumer_generation': 1}, 'task_id': 'task-one', 'dispatch_id': 'dispatch-one',
            'worktree_id': 'worktree-one', 'terminal_handle': 'terminal:one', 'session_id': 'session-one',
            'lease': {'requirement': 'NONE_REQUIRED', 'allocation_id': None, 'provider': None,
                      'reason': 'UNCONFIGURED_PROVIDER_LIMIT', 'path': None},
            'delivery': {'requirement': 'REQUIRED' if succeeded else 'NONE_REQUIRED',
                         'reason': 'WORKER_DONE' if succeeded else 'TERMINAL_LOSS_RECOVERY', 'delivery_id': None, 'message_ids': []},
            'correlation': None,
        }
        if required_lease:
            self.binding['lease'] = {'requirement': 'REQUIRED', 'allocation_id': 'allocation-one', 'provider': 'synthetic',
                                     'reason': 'DECLARED_ALLOCATION', 'path': str(root / 'leases' / 'provider' / 'session.json')}
        self.results = {
            'run': {'run': {'id': 'run-one', 'consumer_generation': 1}},
            'tasks': {'runId': 'run-one', 'count': 1, 'tasks': [{'id': 'task-one', 'run_id': 'run-one', 'status': 'completed' if succeeded else 'failed'}]},
            'worker': {
                'dispatch': {'id': 'dispatch-one', 'run_id': 'run-one', 'task_id': 'task-one', 'assignee_handle': 'terminal:one',
                             'process_incarnation': 'process-one', 'status': 'completed' if succeeded else 'failed'},
                'worker': {'dispatch_id': 'dispatch-one', 'runtime_epoch': 'worker-epoch', 'worktree_id': 'worktree-one',
                           'agent_terminal_handle': 'terminal:one', 'state': 'succeeded' if succeeded else 'abandoned',
                           'stage': 'finished' if succeeded else 'terminal_missing', 'residualResources': []},
                'observation': {'status': 'missing', 'exactWorker': False},
                'terminalResource': {'id': 'resource-one', 'terminalHandle': 'terminal:one', 'worktreeId': 'worktree-one',
                                     'originDispatchId': 'dispatch-one', 'ownerDispatchId': 'dispatch-one', 'ownershipState': 'released',
                                     'releaseState': 'released', 'releaseCompletedAt': '2020-01-01T00:00:00Z', 'releaseError': None, 'retainedReason': None},
            },
        }
        self.request = {'schema_version': rs.REQUEST, 'observer_runtime_id': 'runtime-now', 'binding': None,
                        'commands': {}, 'lease_record': None, 'lease_release': None}
        self.stdout_overrides = {}
        self.argv_overrides = {}
        self.exit_overrides = {}
        if succeeded:
            self.results['delivery'] = {'runId': 'run-one', 'deliveryId': 'delivery-original', 'count': 1, 'messages': [self.message('message-one')]}
            # check --ack may return a NEXT delivery ID. Only acknowledged proves the old batch.
            self.results['ack'] = {'runId': 'run-one', 'deliveryId': 'delivery-next', 'acknowledged': 'delivery-original', 'count': 0, 'messages': []}

    @staticmethod
    def message(ident):
        return {'id': ident, 'run_id': 'run-one', 'to_handle': 'run:run-one', 'type': 'worker_done',
                'delivery_contract': 'current_delivery', 'payload': json.dumps({'taskId': 'task-one', 'dispatchId': 'dispatch-one', 'outcome': 'succeeded'})}

    def put(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = value if isinstance(value, bytes) else rs.canonical(value) + b'\n'
        path.write_bytes(raw)
        return {'path': name, 'sha256': hashlib.sha256(raw).hexdigest()}

    def argv(self, role):
        base = [self.binding['cli_argv0'], 'orchestration']
        return base + {
            'run': ['run-show', '--id', 'run-one', '--json'],
            'tasks': ['task-list', '--run', 'run-one', '--json'],
            'worker': ['worker-show', '--dispatch', 'dispatch-one', '--json'],
            'authority': ['run-use', '--id', 'run-one', '--json'],
            'release': ['worker-release', '--dispatch', 'dispatch-one', '--json'],
            'delivery': ['check', '--run', 'run-one', '--json'],
            'ack': ['check', '--run', 'run-one', '--ack', 'delivery-original', '--json'],
        }[role]

    def capture(self, role, stdout, argv=None, exit_code=0):
        return self.put(role + '.command.json', {'schema_version': rs.COMMAND, 'argv': argv or self.argv(role), 'exit_code': exit_code,
                                               'observed_at': TIME, 'stdout': self.put(role + '.stdout', stdout),
                                               'stderr': self.put(role + '.stderr', b'')})

    def save(self):
        self.request['binding'] = self.put('binding.json', self.binding)
        for role, result in self.results.items():
            response = self.stdout_overrides.get(role, {'ok': True, '_meta': {'runtimeId': self.request['observer_runtime_id']}, 'result': result})
            self.request['commands'][role] = self.capture(role, response, self.argv_overrides.get(role), self.exit_overrides.get(role, 0))
        self.put('request.json', self.request)
        return self.root / 'request.json'

    def settle(self):
        rs.observe(self.save(), self.root / 'snapshot.json')
        rs.reconcile(self.root / 'snapshot.json', self.root / 'receipt.json')
        return rs.verify(self.root / 'receipt.json')


class RuntimeSettlementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='runtime-settlement-')
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def expect_error(self, fixture, code):
        with self.assertRaises(rs.SettlementError) as caught:
            rs.observe(fixture.save(), self.root / 'snapshot.json')
        self.assertEqual(code, caught.exception.code)
        self.assertFalse((self.root / 'snapshot.json').exists())

    def test_required_delivery_success_and_next_batch_ack(self):
        result = Fixture(self.root, succeeded=True).settle()
        self.assertTrue(result['complete'])
        self.assertEqual('SUCCEEDED', result['effective_outcome'])
        self.assertEqual('delivery-original', result['observed']['acknowledged_delivery_id'])
        self.assertFalse(result['lifecycle_mutations'])

    def test_terminal_loss_recovery_complete(self):
        result = Fixture(self.root).settle()
        self.assertTrue(result['complete'])
        self.assertEqual('INVALID_RUNTIME', result['effective_outcome'])

    def test_ready_failed_retains_unsettled_even_released(self):
        fixture = Fixture(self.root)
        fixture.results['tasks']['tasks'][0]['status'] = 'ready'
        fixture.results['authority'] = {}
        fixture.stdout_overrides['authority'] = {'ok': False, '_meta': {'runtimeId': 'runtime-now'}, 'error': {'code': 'permission_denied'}}
        fixture.exit_overrides['authority'] = 1
        result = fixture.settle()
        self.assertFalse(result['complete'])
        self.assertFalse(result['logical_settled'])
        self.assertTrue(result['resources_settled'])
        self.assertIn('TASK_DISPATCH_UNSETTLED', [v['code'] for v in result['missing_evidence']])
        self.assertTrue(any(a['action'] == 'RESTORE_EXACT_OWNER_AUTHORITY' for a in result['next_actions']))

    def test_current_runtime_can_change_without_relabeling_epoch(self):
        fixture = Fixture(self.root)
        fixture.request['observer_runtime_id'] = 'runtime-new'
        result = fixture.settle()
        self.assertTrue(result['complete'])
        self.assertTrue(result['observed']['runtime_changed'])
        self.assertEqual('worker-epoch', result['expected_binding']['runtime']['worker_runtime_epoch'])

    def test_mixed_runtime_rejected(self):
        fixture = Fixture(self.root)
        fixture.stdout_overrides['tasks'] = {'ok': True, '_meta': {'runtimeId': 'other'}, 'result': fixture.results['tasks']}
        self.expect_error(fixture, 'MIXED_RUNTIME')

    def test_epoch_process_and_resource_owner_rejected(self):
        for section, key in [('worker', 'runtime_epoch'), ('dispatch', 'process_incarnation'), ('terminalResource', 'ownerDispatchId')]:
            with self.subTest(field=key):
                fixture = Fixture(self.root)
                fixture.results['worker'][section][key] = 'other'
                self.expect_error(fixture, 'IDENTITY_MISMATCH')

    def test_filtered_peek_and_all_views_rejected(self):
        for extra in [['--types', 'worker_done'], ['--peek'], ['--all']]:
            with self.subTest(extra=extra):
                fixture = Fixture(self.root, succeeded=True)
                fixture.argv_overrides['delivery'] = fixture.argv('delivery') + extra
                self.expect_error(fixture, 'ARGV_MISMATCH')

    def test_other_task_batch_message_remains_unhandled(self):
        fixture = Fixture(self.root, succeeded=True)
        message = fixture.message('message-other')
        message['payload'] = json.dumps({'taskId': 'task-other', 'dispatchId': 'dispatch-other', 'outcome': 'succeeded'})
        fixture.results['delivery']['messages'].append(message)
        fixture.results['delivery']['count'] = 2
        result = fixture.settle()
        self.assertFalse(result['complete'])
        self.assertFalse(result['delivery_settled'])
        self.assertIn('UNHANDLED_BATCH_MESSAGE', [v['code'] for v in result['missing_evidence']])

    def test_batch_count_duplicate_id_and_binding_set_rejected(self):
        for variant in ('count', 'duplicate', 'binding'):
            with self.subTest(variant=variant):
                fixture = Fixture(self.root, succeeded=True)
                if variant == 'count':
                    fixture.results['delivery']['count'] = 2
                elif variant == 'duplicate':
                    fixture.results['delivery']['messages'] *= 2
                    fixture.results['delivery']['count'] = 2
                else:
                    fixture.binding['delivery']['message_ids'] = ['other']
                self.expect_error(fixture, 'IDENTITY_MISMATCH' if variant == 'binding' else 'INVALID_SCHEMA')

    def test_wrong_ack_target_rejected(self):
        fixture = Fixture(self.root, succeeded=True)
        fixture.results['ack']['acknowledged'] = 'delivery-next'
        self.expect_error(fixture, 'IDENTITY_MISMATCH')

    def test_ack_alone_does_not_prove_batch(self):
        fixture = Fixture(self.root, succeeded=True)
        del fixture.results['delivery']
        result = fixture.settle()
        self.assertFalse(result['complete'])
        self.assertFalse(result['delivery_settled'])

    def test_terminal_disappearance_abandon_or_pending_is_not_release(self):
        for variant in ('missing', 'pending', 'active'):
            with self.subTest(variant=variant):
                fixture = Fixture(self.root / variant)
                fixture.root.mkdir()
                if variant == 'missing':
                    fixture.results['worker']['terminalResource'] = None
                elif variant == 'pending':
                    fixture.results['worker']['terminalResource']['releaseState'] = 'pending'
                else:
                    fixture.results['worker']['observation']['status'] = 'active'
                result = fixture.settle()
                self.assertFalse(result['complete'])
                self.assertFalse(result['resources_settled'])

    def test_required_lease_missing_and_legacy_unbound_stay_unknown(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                folder = self.root / str(legacy)
                folder.mkdir()
                fixture = Fixture(folder, required_lease=True)
                if legacy:
                    fixture.request['lease_record'] = fixture.put('lease.json', {'schema': 'multi-agent-orchestration.provider-lease.v1', 'state': 'active'})
                result = fixture.settle()
                self.assertFalse(result['complete'])
                self.assertFalse(result['resources_settled'])

    def test_non_json_permission_output_stays_unknown(self):
        fixture = Fixture(self.root)
        fixture.stdout_overrides['worker'] = b'permission denied\n'
        fixture.exit_overrides['worker'] = 1
        result = fixture.settle()
        self.assertFalse(result['complete'])
        self.assertEqual('NON_JSON_COMMAND_OUTPUT', result['observed']['commands']['worker']['error_code'])

    def test_failed_rpc_null_runtime_is_recorded_unsettled(self):
        fixture = Fixture(self.root)
        fixture.stdout_overrides['worker'] = {'ok': False, '_meta': {'runtimeId': None}, 'error': {'code': 'runtime_unavailable'}}
        fixture.exit_overrides['worker'] = 1
        result = fixture.settle()
        self.assertFalse(result['complete'])
        self.assertEqual('runtime_unavailable', result['observed']['commands']['worker']['error_code'])

    def test_duplicate_keys_nonfinite_and_wrong_types_rejected(self):
        for raw in [b'{"ok":true,"ok":false}', b'{"ok":true,"x":NaN}', b'{"ok":true,"x":1e999}', b'[]']:
            with self.subTest(raw=raw):
                fixture = Fixture(self.root)
                fixture.stdout_overrides['worker'] = raw
                self.expect_error(fixture, 'INVALID_SCHEMA')

    def test_recursive_dependency_drift_and_receipt_forgery(self):
        fixture = Fixture(self.root)
        result = fixture.settle()
        dependencies = [Path(ref['path']) for ref in result['dependencies']]
        self.assertIn(self.root / 'worker.stdout', dependencies)
        self.assertIn(self.root / 'worker.stderr', dependencies)
        for path in dependencies:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original + (b'broken' if path.name == 'receipt.json' else b' '))
                with self.assertRaises(rs.SettlementError):
                    rs.verify(self.root / 'receipt.json')
                path.write_bytes(original)
        value = rs.parse((self.root / 'receipt.json').read_bytes())
        value['payload']['effective_outcome'] = 'SUCCEEDED'
        value['sha256'] = rs.digest(value['payload'])
        (self.root / 'receipt.json').write_bytes(rs.canonical(value))
        with self.assertRaises(rs.SettlementError) as caught:
            rs.verify(self.root / 'receipt.json')
        self.assertEqual('RECEIPT_DRIFT', caught.exception.code)

    def test_path_symlink_and_traversal_rejected(self):
        fixture = Fixture(self.root)
        fixture.save()
        (self.root / 'worker.stdout').unlink()
        (self.root / 'worker.stdout').symlink_to(self.root / 'run.stdout')
        with self.assertRaises(rs.SettlementError) as caught:
            rs.observe(self.root / 'request.json', self.root / 'snapshot.json')
        self.assertEqual('UNSAFE_PATH', caught.exception.code)
        fixture.request['binding']['path'] = '../binding.json'
        fixture.put('request.json', fixture.request)
        with self.assertRaises(rs.SettlementError):
            rs.observe(self.root / 'request.json', self.root / 'snapshot.json')

    def test_future_release_time_rejected(self):
        fixture = Fixture(self.root)
        fixture.results['worker']['terminalResource']['releaseCompletedAt'] = '2031-01-01T00:00:00Z'
        self.expect_error(fixture, 'INVALID_ORDER')

    def test_cli_idempotent_immutable_and_nonzero_error(self):
        fixture = Fixture(self.root, succeeded=True)
        fixture.save()
        calls = [('observe', '--request', 'request.json', '--output', 'snapshot.json'),
                 ('reconcile', '--snapshot', 'snapshot.json', '--output', 'receipt.json'),
                 ('verify', '--receipt', 'receipt.json')]
        for args in calls * 2:
            result = subprocess.run([sys.executable, str(CLI), *args], cwd=self.root, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertTrue(json.loads(result.stdout)['ok'])
        (self.root / 'worker.stdout').write_text('{}')
        failed = subprocess.run([sys.executable, str(CLI), 'verify', '--receipt', 'receipt.json'], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(2, failed.returncode)
        self.assertFalse(json.loads(failed.stdout)['complete'])
        self.assertNotIn('Traceback', failed.stderr)


if __name__ == '__main__':
    unittest.main()
