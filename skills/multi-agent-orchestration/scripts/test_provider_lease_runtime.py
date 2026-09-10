#!/usr/bin/env python3
"""Real provider-lease CLI against one isolated synthetic Orca executable."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import runtime_settlement as rs
from test_runtime_settlement import Fixture, LEASE_CLI


class BoundLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='provider-runtime-')
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def prepare_lease(self, resource_released=True):
        fixture = Fixture(self.root, succeeded=True, required_lease=True)
        fake = self.root / 'fake-orca'
        fixture.binding['cli_argv0'] = str(fake)
        fixture.save()
        raw_response = {'ok': True, '_meta': {'runtimeId': 'runtime-now'}, 'result': fixture.results['worker']}
        if not resource_released:
            raw_response['result']['terminalResource']['releaseState'] = 'pending'
        fixture.put('fake-worker.json', raw_response)
        fake.write_text('#!' + sys.executable + '\nimport pathlib,sys\nassert sys.argv[1:] == ["orchestration","worker-show","--dispatch","dispatch-one","--json"]\nprint(pathlib.Path(__file__).with_name("fake-worker.json").read_text())\n')
        fake.chmod(0o700)
        lease_path = Path(fixture.binding['lease']['path'])
        lease_path.parent.mkdir(parents=True)
        lease = {'schema': 'multi-agent-orchestration.provider-lease.v1', 'state': 'active', 'created_at': '2020-01-01T00:00:00Z',
                 'updated_at': '2020-01-01T00:00:00Z', 'provider': 'synthetic', 'backend': 'fixture', 'session': 'session-one',
                 'project': str(self.root), 'owner_pid': os.getpid(), 'max_concurrency': 1, 'transport': 'orca_terminal', 'resource_handle': 'terminal:one'}
        lease_path.write_bytes(rs.canonical(lease))
        common = ['--root', str(lease_path.parent.parent), '--lease-file', str(lease_path), '--session', 'session-one']
        bind = subprocess.run([sys.executable, str(LEASE_CLI), 'bind-runtime', *common, '--runtime-binding', str(self.root / 'binding.json')], capture_output=True, text=True)
        self.assertEqual(0, bind.returncode, bind.stdout + bind.stderr)
        fixture.request['lease_record'] = fixture.put('lease-before.json', lease_path.read_bytes())
        release_path = lease_path.parent.parent / '.runtime-release-receipts' / (rs.digest(fixture.binding) + '.json')
        self.assertEqual(str(release_path), json.loads(bind.stdout)['release_receipt_path'])
        release_argv = [sys.executable, str(LEASE_CLI), 'release', *common, '--resource-settled', '--orca-cli', str(fake),
                        '--runtime-binding', str(self.root / 'binding.json'), '--release-receipt', str(release_path)]
        return fixture, lease_path, release_path, release_argv

    def test_required_lease_real_producer_release_and_idempotent_receipt(self):
        fixture, path, receipt_path, argv = self.prepare_lease()
        first = subprocess.run(argv, capture_output=True)
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertTrue(json.loads(first.stdout)['released'])
        self.assertFalse(path.exists())
        original = receipt_path.read_bytes()
        second = subprocess.run(argv, capture_output=True)
        self.assertEqual(0, second.returncode)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(original, receipt_path.read_bytes())
        fixture.request['lease_release'] = fixture.capture('lease_release', first.stdout, argv)
        result = fixture.settle()
        self.assertTrue(result['complete'])
        self.assertTrue(result['observed']['lease']['release_verified'])

    def test_bound_lease_pending_resource_retains_quota(self):
        fixture, path, receipt, argv = self.prepare_lease(resource_released=False)
        result = subprocess.run(argv, capture_output=True)
        self.assertEqual(75, result.returncode, result.stdout)
        self.assertTrue(path.exists())
        self.assertFalse(receipt.exists())

    def test_missing_lease_without_receipt_never_promoted(self):
        fixture, path, receipt, argv = self.prepare_lease()
        path.unlink()
        result = subprocess.run(argv, capture_output=True)
        self.assertEqual(0, result.returncode)
        self.assertFalse(json.loads(result.stdout)['released'])
        self.assertFalse(receipt.exists())

    def test_bound_lease_old_release_and_sweeper_cannot_reclaim(self):
        fixture, path, receipt, argv = self.prepare_lease()
        old_argv = argv[:argv.index('--runtime-binding')]
        result = subprocess.run(old_argv, capture_output=True)
        self.assertEqual(75, result.returncode)
        self.assertTrue(path.exists())
        spec = importlib.util.spec_from_file_location('provider_lease_test', LEASE_CLI)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(module.lease_alive(json.loads(path.read_text()), '/missing/orca'))

    def test_release_refuses_wrong_dispatch_resource(self):
        fixture, path, receipt, argv = self.prepare_lease()
        response = json.loads((self.root / 'fake-worker.json').read_text())
        response['result']['terminalResource']['ownerDispatchId'] = 'other'
        fixture.put('fake-worker.json', response)
        result = subprocess.run(argv, capture_output=True)
        self.assertEqual(64, result.returncode)
        self.assertTrue(path.exists())
        self.assertFalse(receipt.exists())

    def test_nested_release_raw_and_normalized_proof_rederived(self):
        fixture, path, receipt, argv = self.prepare_lease()
        result = subprocess.run(argv, capture_output=True)
        self.assertEqual(0, result.returncode)
        original = json.loads(result.stdout)
        for variant in ('stdout_hash', 'stderr_hash', 'worker_summary', 'raw_identity'):
            with self.subTest(variant=variant):
                response = json.loads(json.dumps(original))
                release = response['runtime_release']
                proof = release['payload']['resource_observation']
                if variant == 'stdout_hash':
                    proof['stdout_sha256'] = '0' * 64
                elif variant == 'stderr_hash':
                    proof['stderr_sha256'] = '0' * 64
                elif variant == 'worker_summary':
                    proof['worker']['worker_state'] = 'failed'
                else:
                    raw = json.loads(proof['stdout'])
                    raw['result']['worker']['runtime_epoch'] = 'other-epoch'
                    proof['stdout'] = json.dumps(raw)
                    proof['stdout_sha256'] = rs.raw_sha(proof['stdout'].encode())
                release['sha256'] = rs.digest(release['payload'])
                fixture.request['lease_release'] = fixture.capture('lease_release', response, argv)
                with self.assertRaises(rs.SettlementError):
                    rs.observe(fixture.save(), self.root / 'snapshot.json')
                self.assertFalse((self.root / 'snapshot.json').exists())

    def test_persisted_receipt_replay_rechecks_original_raw(self):
        fixture, path, receipt, argv = self.prepare_lease()
        result = subprocess.run(argv, capture_output=True)
        self.assertEqual(0, result.returncode)
        envelope = json.loads(receipt.read_text())
        envelope['payload']['resource_observation']['stdout_sha256'] = '0' * 64
        envelope['sha256'] = rs.digest(envelope['payload'])
        receipt.write_bytes(rs.canonical(envelope))
        replay = subprocess.run(argv, capture_output=True)
        self.assertEqual(64, replay.returncode)
        self.assertFalse(json.loads(replay.stdout)['released'])


if __name__ == '__main__':
    unittest.main()
