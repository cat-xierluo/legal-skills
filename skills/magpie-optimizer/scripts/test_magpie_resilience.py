import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

SCRIPT = Path(__file__).with_name('magpie_resilience.py')
spec = importlib.util.spec_from_file_location('resilience', SCRIPT)
resilience = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resilience)


class ResilienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'config'
        self.config.mkdir(mode=0o700)
        self.bindir = self.root / 'bin'
        self.bindir.mkdir()
        self.ps = self.bindir / 'ps'
        self.env = dict(os.environ, PATH=str(self.bindir), PYTHONDONTWRITEBYTECODE='1')
        self.output = self.root / 'out' / 'report.json'

    def fake_ps(self, body):
        self.ps.write_text('#!/bin/sh\n' + body + '\n')
        self.ps.chmod(0o700)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), 'collect', '--samples', '2',
                               '--interval', '0.1', '--config-dir', str(self.config),
                               '--output', str(self.output), *args], env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_segments_privacy_and_permissions(self):
        marker = self.root / 'called'
        self.fake_ps(f'''if [ -e "{marker}" ]; then
  printf '12 1 200 1.0 Sun Nov  1 10:00:00 2026 /private/magpie-bun\\n'
else
  : > "{marker}"
  printf '11 1 100 2.0 Sun Nov  1 09:00:00 2026 /private/magpie-bun\\n'
fi''')
        auth = self.config / 'plugin-auth.json'
        auth.write_text('SECRET_ACCOUNT_SECRET_TOKEN')
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        raw = self.output.read_text()
        report = json.loads(raw)
        self.assertNotIn('SECRET', raw)
        self.assertNotIn('/private', raw)
        self.assertNotIn(str(self.root), raw)
        self.assertEqual([s['pid'] for s in report['host_segments']], [11, 12])
        self.assertEqual([s['rss_change_kib'] for s in report['host_segments']], [0, 0])
        self.assertEqual(report['auth_change_count'], 0)
        self.assertGreaterEqual(report['coverage_seconds'], 0.09)
        self.assertEqual(report['requested_interval_seconds'], 0.1)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.output.parent.stat().st_mode), 0o700)
        original = self.output.read_bytes()
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.assertEqual(self.output.read_bytes(), original)

    def test_default_xdg_config_and_ps_locale(self):
        xdg = self.root / 'xdg'
        config = xdg / 'magpie'
        config.mkdir(parents=True, mode=0o700)
        (config / 'plugin-auth.json').write_text('SECRET_XDG_CONTENT')
        self.fake_ps("""[ "$LC_ALL" = C ] || exit 1
printf '11 1 100 2.0 Sun Nov  1 09:00:00 2026 /private/magpie-bun\\n'""")
        env = dict(self.env, XDG_CONFIG_HOME=str(xdg), LC_ALL='not_a_locale')
        result = subprocess.run([sys.executable, str(SCRIPT), 'collect', '--samples', '2',
                                 '--interval', '0.1', '--output', str(self.output)],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        raw = self.output.read_text()
        self.assertNotIn('SECRET_XDG_CONTENT', raw)
        self.assertEqual([s['auth']['status'] for s in json.loads(raw)['samples']],
                         ['present', 'present'])

    def test_process_failure_and_absent_auth_are_distinct(self):
        self.fake_ps('exit 1')
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(self.output.read_text())
        self.assertIsNone(report['samples'][0]['hosts'])
        self.assertEqual(report['samples'][0]['auth']['status'], 'absent')
        self.assertIsNone(report['auth_change_count'])
        self.assertEqual(report['status'], 'incomplete')

    def test_stat_permission_failure_is_unknown(self):
        with mock.patch.object(Path, 'stat', side_effect=PermissionError):
            self.assertEqual(resilience.auth_stat(self.config), {'status': 'unknown'})
        with mock.patch.object(resilience, 'hosts', return_value=[]), \
             mock.patch.object(resilience, 'auth_stat', return_value={'status': 'unknown'}):
            result = io.StringIO()
            args = type('Args', (), {'samples': 2, 'interval': 0.1, 'config_dir': self.config})()
            self.assertEqual(resilience.collect(args, result), 1)
            self.assertIsNone(json.loads(result.getvalue())['auth_change_count'])

    def test_same_pid_new_start_and_rss_growth(self):
        def host(start, rss):
            return [{'pid': 1, 'ppid': 2, 'rss_kib': rss, 'cpu_percent': 0.0, 'started': start}]
        with mock.patch.object(resilience, 'hosts', side_effect=[host('old', 100), host('old', 130), host('new', 500)]):
            result = io.StringIO()
            args = type('Args', (), {'samples': 3, 'interval': 0.1, 'config_dir': self.config})()
            self.assertEqual(resilience.collect(args, result), 0)
        segments = json.loads(result.getvalue())['host_segments']
        self.assertEqual([s['rss_change_kib'] for s in segments], [30, 0])

    def test_utc_timestamps_and_wall_clock_rollback(self):
        args = type('Args', (), {'samples': 2, 'interval': 10, 'config_dir': self.config})()
        instants = ['2026-11-01T12:00:00Z', '2026-11-01T12:00:02Z',
                    '2026-11-01T11:00:14Z', '2026-11-01T11:00:15Z']
        clock = [100.0]
        timeouts = []

        def sample(timeout):
            timeouts.append(timeout)
            clock[0] += 2
            return []

        def sleep(seconds):
            clock[0] += seconds

        with mock.patch.object(resilience.time, 'monotonic', side_effect=lambda: clock[0]), \
             mock.patch.object(resilience.time, 'sleep', side_effect=sleep), \
             mock.patch.object(resilience, 'utc_now', side_effect=instants), \
             mock.patch.object(resilience, 'hosts', side_effect=sample):
            output = io.StringIO()
            self.assertEqual(resilience.collect(args, output), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report['requested_interval_seconds'], 10)
        self.assertEqual(report['coverage_seconds'], 12)
        self.assertEqual(report['observation_elapsed_seconds'], 14)
        self.assertEqual([s['elapsed_seconds'] for s in report['samples']], [2, 14])
        self.assertEqual(timeouts, [300, 288])
        values = [report['started_at'], *(s['at'] for s in report['samples']), report['finished_at']]
        self.assertEqual(values, instants)
        for value in values:
            self.assertEqual(datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo, timezone.utc)
        self.assertLess(values[2], values[1])  # The wall clock actually moved backward.

    def test_utc_timestamps_are_ordered_with_normal_clock(self):
        with mock.patch.object(resilience, 'hosts', return_value=[]):
            output = io.StringIO()
            args = type('Args', (), {'samples': 2, 'interval': 0.1, 'config_dir': self.config})()
            self.assertEqual(resilience.collect(args, output), 0)
        report = json.loads(output.getvalue())
        values = [report['started_at'], *(s['at'] for s in report['samples']), report['finished_at']]
        parsed = [datetime.fromisoformat(value.replace('Z', '+00:00')) for value in values]
        self.assertTrue(all(value.endswith('Z') for value in values))
        self.assertTrue(all(value.tzinfo == timezone.utc for value in parsed))
        self.assertEqual(parsed, sorted(parsed))

    def test_auth_changes_and_no_content_open(self):
        auth = self.config / 'plugin-auth.json'
        auth.write_text('private')
        os.utime(auth, ns=(1_000_000_000, 1_000_000_000))
        first = resilience.auth_stat(self.config)
        os.utime(auth, ns=(2_000_000_000, 2_000_000_000))
        with mock.patch('builtins.open', side_effect=AssertionError('content read')):
            second = resilience.auth_stat(self.config)
        with mock.patch.object(resilience, 'hosts', return_value=[]), \
             mock.patch.object(resilience, 'auth_stat', side_effect=[first, second]):
            output = io.StringIO()
            args = type('Args', (), {'samples': 2, 'interval': 0.1, 'config_dir': self.config})()
            self.assertEqual(resilience.collect(args, output), 0)
        self.assertEqual(json.loads(output.getvalue())['auth_change_count'], 1)

    def test_invalid_parameters_do_not_create_output(self):
        for arguments in [('--interval', 'nan'), ('--interval', 'inf'), ('--interval', '0'),
                          ('--interval', '61'), ('--samples', '1'), ('--samples', '61'),
                          ('--samples', '60', '--interval', '6')]:
            with self.subTest(arguments=arguments):
                self.assertNotEqual(self.run_cli(*arguments).returncode, 0)
                self.assertFalse(self.output.exists())

    def test_interrupt_preserves_partial(self):
        with mock.patch.object(resilience, 'hosts', side_effect=[[], KeyboardInterrupt]):
            output = io.StringIO()
            args = type('Args', (), {'samples': 2, 'interval': 0.1, 'config_dir': self.config})()
            self.assertEqual(resilience.collect(args, output), 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report['status'], 'interrupted')
        self.assertEqual(report['collected_samples'], 1)

    def test_insecure_parent_rejected(self):
        self.output.parent.mkdir(mode=0o755)
        self.output.parent.chmod(0o755)
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
