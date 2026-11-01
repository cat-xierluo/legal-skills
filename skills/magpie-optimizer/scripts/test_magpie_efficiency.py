import datetime as dt
import gzip
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).with_name('magpie_efficiency.py')
spec = importlib.util.spec_from_file_location('efficiency', SCRIPT)
eff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eff)
SINCE = '2026-11-01T00:00:00Z'
UNTIL = '2026-11-02T00:00:00Z'


def row(**kw):
    return {'time': '2026-11-01T08:00:00Z', 'done': True, 'status': 200, **kw}


class EfficiencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = self.root / 'secret-input.jsonl'
        self.out = self.root / 'reports' / 'result.json'

    def write(self, *records):
        self.log.write_text(''.join(json.dumps(r) + '\n' for r in records))

    def collect(self, *paths, limit=1024 * 1024):
        return eff.collect(paths or [self.log], eff.timestamp(SINCE), eff.timestamp(UNTIL), limit)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.log), '--since', SINCE,
                               '--until', UNTIL, '--output', str(self.out), *args],
                              capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})

    def test_cli_smoke_privacy_and_permissions(self):
        self.write(row(provider='SECRET_PROVIDER', model='SECRET_MODEL', served='SECRET_SERVED',
                       folder='SECRET_FOLDER', session='SECRET_SESSION', agent='SECRET_AGENT',
                       error=None, ms=300, ttft=70, tries=[{'status': 200, 'net': {'send': 50, 'secret': 42}}],
                       prompt={'parts': [{'kind': 'skills', 'tokens': 30, 'text': 'SECRET_PROMPT'}], 'counted': True}))
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        raw = self.out.read_text()
        for secret in ('SECRET_', str(self.root), 'secret-input', 'secret'):
            self.assertNotIn(secret, raw)
        data = json.loads(raw)
        self.assertEqual(data['parts']['tokens']['skills'], 30)
        self.assertEqual(data['success_latency_ms']['p50'], 300)
        self.assertEqual(data['success_ttft_ms']['p50'], 70)
        self.assertEqual(data['net']['all_tries']['send']['sum'], 50)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.out.parent.stat().st_mode), 0o700)
        original = self.out.read_bytes()
        self.assertNotEqual(self.cli().returncode, 0)
        self.assertEqual(original, self.out.read_bytes())

    def test_time_window_and_inflight(self):
        self.write(row(time=SINCE), row(time=UNTIL), row(time='2026-11-01T09:00:00+02:00', done=False),
                   row(time='2026-11-01T08:00:00Z', done=None))
        c = self.collect()['coverage']
        self.assertEqual((c['finished_in_window'], c['outside_window'], c['in_flight'], c['completion_unknown']), (1, 1, 1, 1))

    def test_final_status_and_tries_recovery(self):
        self.write(row(tries=[{'status': 503, 'error': 'SECRET_ERROR'}, {'status': 200}]),
                   row(status=500, tries=[{'status': 503}]), row(status=200, tries=[{'status': 500}, {}]),
                   row(status=None, tries='SECRET_ERROR'))
        report = self.collect()
        self.assertEqual(report['final_status'], {'success': 2, 'failure': 1, 'unknown': 1})
        self.assertEqual(report['tries']['failure'], 3)
        self.assertEqual(report['tries']['success'], 1)
        self.assertEqual(report['tries']['unknown'], 1)
        self.assertEqual(report['tries']['recovered_after_failure'], 1)
        self.assertEqual(report['tries']['recovery_unknown_records'], 1)
        self.assertEqual(report['tries']['missing_or_invalid_records'], 1)
        self.assertNotIn('SECRET_ERROR', json.dumps(report))

    def test_http200_error_is_not_success_and_auxiliary_is_separate(self):
        self.write(row(kind='composer_predictions', error='SECRET_EMPTY_PREDICTION'),
                   row(tries=[{'status': 200}]),
                   row(kind='SECRET_KIND', error='SECRET_ERROR'))
        report = self.collect()
        self.assertEqual(report['final_http_status']['codes']['200'], 3)
        self.assertEqual(report['final_status'], {'success': 1, 'failure': 2, 'unknown': 0})
        self.assertEqual(report['by_kind']['composer_predictions']['http_200_with_error'], 1)
        self.assertEqual(report['by_kind']['main_or_unspecified']['success'], 1)
        self.assertEqual(report['by_kind']['other']['failure'], 1)
        self.assertNotIn('SECRET', json.dumps(report))

    def test_redirect_is_unknown_and_not_success_latency(self):
        self.write(row(status=302, ms=99, ttft=10, tries=[{'status': 302}]),
                   row(ms=300, ttft=20, tries=[{'status': 200}]))
        report = self.collect()
        self.assertEqual(report['final_status'], {'success': 1, 'failure': 0, 'unknown': 1})
        self.assertEqual(report['tries']['unknown'], 1)
        self.assertEqual(report['success_latency_ms']['count'], 1)
        self.assertEqual(report['success_latency_ms']['p50'], 300)
        self.assertEqual(report['final_http_status']['codes']['302'], 1)

    def test_input_output_same_path_refused_before_creation(self):
        command = [sys.executable, str(SCRIPT), str(self.log), '--since', SINCE,
                   '--until', UNTIL, '--output', str(self.log)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())
        self.write(row())
        original = self.log.read_bytes()
        alias = self.root / 'alias.jsonl'
        alias.symlink_to(self.log)
        command[-1] = str(alias)
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.log.read_bytes(), original)

    def test_parts_skills_unknown_and_missing(self):
        self.write(row(prompt={'counted': False, 'parts': [{'kind': 'system', 'tokens': 10},
                            {'kind': 'skills', 'tokens': 30}, {'kind': 'UNRECOGNIZED_SECRET', 'tokens': 60},
                            {'kind': 'chat'}, None]}), row(prompt={}))
        p = self.collect()['parts']
        self.assertEqual(p['numeric_token_total'], 100)
        self.assertEqual(p['shares']['skills'], 0.3)
        self.assertEqual(p['shares']['unknown'], 0.6)
        self.assertIsNone(p['tokens']['tools'])
        self.assertEqual((p['unknown_kind_entries'], p['invalid_entries'], p['missing_or_invalid_parts']), (1, 2, 1))
        self.assertEqual(p['estimated_records'], 1)
        self.assertEqual(p['tokens_by_counted'], {'counted': None, 'estimated': 100, 'unknown': None})
        self.assertNotIn('UNRECOGNIZED_SECRET', json.dumps(p))

    def test_missing_values_are_not_zero(self):
        self.write(row(prompt={'parts': []}), row(status=500, ms=10))
        report = self.collect()
        self.assertIsNone(report['parts']['numeric_token_total'])
        self.assertIsNone(report['parts']['shares'])
        self.assertIsNone(report['parts']['tokens']['skills'])
        self.assertIsNone(report['success_latency_ms']['p50'])
        self.assertIsNone(report['success_ttft_ms']['p50'])
        self.assertIsNone(report['net']['all_tries']['send']['sum'])
        self.assertIsNone(report['usage']['raw_fields']['cache_read']['sum'])

    def test_quantiles_and_cache_separate(self):
        self.write(row(ms=10, ttft=1, usage=[{'cache_read': 100}], prompt={'parts': [{'kind': 'chat', 'tokens': 200}]}),
                   row(ms=30, ttft=3, usage=[{'cache_read': 50}]), row(ms=20), row(status=500, ms=1000))
        report = self.collect()
        self.assertEqual(report['success_latency_ms']['p50'], 20)
        self.assertEqual(report['success_latency_ms']['p90'], 30)
        self.assertEqual(report['success_ttft_ms']['count'], 2)
        self.assertEqual(report['usage']['raw_fields']['cache_read']['sum'], 150)
        self.assertEqual(report['parts']['tokens']['chat'], 200)

    def test_usage_raw_list_coverage_and_legacy_dict(self):
        self.write(row(usage=[{'model': 'SECRET_MODEL', 'in': 26037, 'out': 995,
                               'cache_read': 6656, 'reasoning': 32}]),
                   row(usage=[{'in': 10203, 'cache_read': 32512}, {'in': 10}, []]),
                   row(usage={'in': 999999, 'cache_read': 999999}),
                   row(usage=[]), row())
        usage = self.collect()['usage']
        self.assertEqual(usage['list_records'], 3)
        self.assertEqual(usage['multi_entry_records'], 1)
        self.assertEqual(usage['empty_list_records'], 1)
        self.assertEqual(usage['legacy_dict_records'], 1)
        self.assertEqual(usage['unsupported_records'], 0)
        self.assertEqual(usage['legacy_dict_raw_fields']['in']['sum'], 999999)
        self.assertEqual(usage['missing_records'], 1)
        self.assertEqual(usage['invalid_entries'], 1)
        self.assertEqual(usage['dict_entries'], 3)
        fields = usage['raw_fields']
        self.assertEqual(fields['in']['sum'], 26037 + 10203 + 10)
        self.assertEqual(fields['cache_read']['sum'], 6656 + 32512)
        self.assertEqual(fields['out']['sum'], 995)
        self.assertEqual(fields['out']['missing_or_invalid_entries'], 2)
        self.assertEqual(fields['reasoning']['sum'], 32)
        self.assertNotIn('SECRET_MODEL', json.dumps(usage))
        self.assertNotIn('input_total', usage)

    def test_malformed_invalid_structure_and_nan(self):
        self.log.write_text('not-json\n[]\n{"time":"bad"}\n{"time":"2026-11-01T08:00:00Z","ms":NaN}\n')
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(self.out.read_text())
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['coverage']['malformed_lines'], 2)
        self.assertEqual(report['coverage']['invalid_records_or_time'], 2)
        self.assertIsNone(report['success_latency_ms']['p50'])

    def test_try_net_and_http_status_codes(self):
        self.write(row(status=200, net={'send': 9999}, tries=[
            {'status': 429, 'net': {'send': 20, 'wait': 5}},
            {'status': 200, 'net': {'send': 30, 'own': 2}},
            {'status': 'SECRET_STATUS', 'net': {'send': 40}}, []]),
            row(status=499, tries=[{'status': 502}]), row(status=502, tries=[{'status': 499}]),
            row(status=999, tries='bad'))
        report = self.collect()
        self.assertEqual(report['final_http_status'], {'codes': {'200': 1, '499': 1, '502': 1}, 'unknown': 1})
        self.assertEqual(report['try_http_status'], {'codes': {'429': 1, '200': 1, '502': 1, '499': 1}, 'unknown': 2})
        self.assertEqual(report['net']['all_tries']['send'], {'observed_tries': 3, 'sum': 90})
        self.assertEqual(report['net']['successful_tries']['send'], {'observed_tries': 1, 'sum': 30})
        self.assertIsNone(report['net']['successful_tries']['wait']['sum'])
        self.assertNotIn('SECRET_STATUS', json.dumps(report))
        self.assertIn('WS handshake', json.dumps(report['notes']))

    def test_prompt_total_difference_and_incomplete_parts(self):
        self.write(row(prompt={'tokens': 100, 'parts': [{'kind': 'skills', 'tokens': 20},
                                                        {'kind': 'unknown-secret', 'tokens': 30}]}),
                   row(prompt={'tokens': 60, 'parts': [{'kind': 'chat', 'tokens': 60}]}),
                   row(prompt={'tokens': 200, 'parts': [{'kind': 'chat', 'tokens': 10}, {'kind': 'files'}]}),
                   row(prompt={'parts': [{'kind': 'chat', 'tokens': 10}]}))
        report = self.collect()
        totals = report['prompt_total']
        self.assertEqual((totals['observed_records'], totals['sum']), (3, 360))
        self.assertEqual((totals['comparable_records'], totals['uncomparable_records']), (2, 2))
        self.assertEqual((totals['comparable_prompt_sum'], totals['comparable_parts_sum']), (160, 110))
        self.assertEqual((totals['difference_prompt_minus_parts'], totals['mismatched_records']), (50, 1))
        self.assertEqual(report['parts']['tokens']['unknown'], 30)

    def test_fifo_and_duplicate_inode_are_partial_without_hanging_or_double_count(self):
        self.write(row(ms=42))
        alias = self.root / 'hardlink.jsonl'
        os.link(self.log, alias)
        fifo = self.root / 'fifo.jsonl'
        os.mkfifo(fifo)
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.log), str(alias), str(fifo),
                                 '--since', SINCE, '--until', UNTIL, '--output', str(self.out)],
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(self.out.read_text())
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['coverage']['duplicate_inputs'], 1)
        self.assertEqual(report['coverage']['non_regular_inputs'], 1)
        self.assertEqual(report['coverage']['finished_in_window'], 1)
        self.assertEqual(report['success_latency_ms']['count'], 1)

    def test_non_dict_json_then_valid_record_cli(self):
        self.write(['not', 'a', 'record'], row(ms=42))
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(self.out.read_text())
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['coverage']['invalid_records_or_time'], 1)
        self.assertEqual(report['coverage']['finished_in_window'], 1)
        self.assertEqual(report['success_latency_ms']['p50'], 42)

    def test_budget_truncates_without_partial_line(self):
        self.write(row(ms=10), row(ms=20))
        first_len = len((json.dumps(row(ms=10)) + '\n').encode())
        report = self.collect(limit=first_len + 5)
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['coverage']['finished_in_window'], 1)
        self.assertTrue(report['coverage']['truncated_by_byte_limit'])
        self.assertEqual(report['success_latency_ms']['count'], 1)

    def test_gzip_and_budget_applies_across_files(self):
        self.write(row(ms=10))
        compressed = self.root / 'second.jsonl.gz'
        with gzip.open(compressed, 'wt') as f:
            f.write(json.dumps(row(ms=20)) + '\n')
        report = self.collect(self.log, compressed)
        self.assertEqual(report['success_latency_ms']['count'], 2)
        limited = self.collect(self.log, compressed, limit=self.log.stat().st_size + 3)
        self.assertEqual(limited['status'], 'partial')
        self.assertEqual(limited['coverage']['finished_in_window'], 1)

    def test_bad_input_limits_and_read_errors(self):
        self.write(row())
        for arguments in [('--since', '2026-11-01'), ('--max-bytes', '0'), ('--max-bytes', '1073741825'),
                          ('--until', SINCE)]:
            with self.subTest(arguments=arguments):
                self.assertNotEqual(self.cli(*arguments).returncode, 0)
                self.assertFalse(self.out.exists())
        report = self.collect(self.root / 'missing')
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['coverage']['read_errors'], 1)

    def test_row_cap_counts_malformed_and_excluded_rows(self):
        self.log.write_text('invalid\ninvalid\n' + json.dumps(row()) + '\n')
        with mock.patch.object(eff, 'MAX_ROWS', 2):
            report = self.collect()
        self.assertEqual(report['coverage']['lines_read'], 2)
        self.assertTrue(report['coverage']['truncated_by_row_limit'])
        self.assertEqual(report['coverage']['finished_in_window'], 0)

    def test_invalid_numeric_values_are_unknown(self):
        self.write(row(ms=-1, ttft=True, net={'send': 1e300}, prompt={'parts': [{'kind': 'skills', 'tokens': -1}]}))
        report = self.collect()
        self.assertIsNone(report['success_latency_ms']['p50'])
        self.assertIsNone(report['success_ttft_ms']['p50'])
        self.assertIsNone(report['net']['all_tries']['send']['sum'])
        self.assertEqual(report['parts']['invalid_entries'], 1)
        self.assertIsNone(report['parts']['tokens']['skills'])


if __name__ == '__main__':
    unittest.main()
