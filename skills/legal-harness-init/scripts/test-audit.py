#!/usr/bin/env python3
"""Isolated CLI regression tests for audit findings; no network or user config."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent
ASSETS = SCRIPTS.parent / 'assets'


class AuditRegression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.content = self.root / 'content.md'
        self.content.write_text('# Baseline\n', encoding='utf-8')
        self.env = {'HOME': str(self.home), 'PATH': os.defpath, 'LANG': 'C.UTF-8'}

    def run_cli(self, script, *args, cwd=None):
        command = (['python3', str(SCRIPTS / script)] if script.endswith('.py')
                   else ['bash', str(SCRIPTS / script)])
        return subprocess.run(command + [str(a) for a in args], cwd=cwd or self.project,
                              env=self.env, capture_output=True, text=True)

    def write(self, *extra):
        return self.run_cli('write.sh', '--content-file', self.content, '--level', 'project',
                            '--platforms', 'codex', '--project-dir', self.project,
                            '--block-id', 'legal-baseline', '--privacy-mode', 'strict', *extra)

    def record(self, target, *extra):
        return self.run_cli('record-init-env.sh', '--target', target, '--action', 'init', *extra)

    def assert_ok_json(self, result):
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_create_existing_is_valid_json_and_untouched(self):
        target = self.project / 'AGENTS.md'
        target.write_text('original\n')
        target.chmod(0o640)
        before = target.read_bytes(), stat.S_IMODE(target.stat().st_mode)
        payload = self.assert_ok_json(self.write())
        self.assertEqual(payload['targets'][0]['status'], 'needs_confirmation')
        self.assertEqual((target.read_bytes(), stat.S_IMODE(target.stat().st_mode)), before)

    def test_directory_target_rejected_without_changes(self):
        target = self.project / 'AGENTS.md'
        target.mkdir()
        result = self.write('--mode', 'update', '--model', 'test-model')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue(target.is_dir())
        self.assertEqual(list(target.iterdir()), [])

    def test_writer_rejects_nested_managed_target_without_changes(self):
        target = self.project / 'AGENTS.md'
        original = (
            '<!-- legal-harness-init:legal-baseline:start -->\n'
            '# Existing baseline\n'
            '<!-- legal-harness-init:init-environment:start -->\n'
            '| valuable managed metadata |\n'
            '<!-- legal-harness-init:init-environment:end -->\n'
            '<!-- legal-harness-init:legal-baseline:end -->\n')
        target.write_text(original)
        result = self.write('--mode', 'update', '--model', 'safe-model')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)['targets'][0]['status'], 'error')
        self.assertEqual(target.read_text(), original)

    def test_retry_incomplete_record_then_idempotent(self):
        result = self.write('--mode', 'update')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)['targets'][0]['status'], 'written_record_incomplete')
        target = self.project / 'AGENTS.md'
        self.assertNotIn('init-environment:start', target.read_text())
        self.assert_ok_json(self.write('--mode', 'update', '--model', 'repair-model'))
        repaired = target.read_bytes()
        self.assertIn(b'repair-model', repaired)
        self.assertIn(b'init-environment:start', repaired)
        self.assert_ok_json(self.write('--mode', 'update', '--model', 'repair-model'))
        self.assertEqual(target.read_bytes(), repaired)

    def test_changed_content_requires_new_record_and_retry_is_idempotent(self):
        self.assert_ok_json(self.write('--mode', 'update', '--model', 'old-model'))
        target = self.project / 'AGENTS.md'
        self.content.write_text('# Changed baseline\n')
        failed = self.write('--mode', 'update', '--model', 'bad model')
        self.assertNotEqual(failed.returncode, 0, failed.stdout)
        self.assertTrue(json.loads(failed.stdout)['targets'][0]['status'].endswith('_record_incomplete'))
        partial = target.read_text()
        self.assertIn('# Changed baseline', partial)
        self.assertIn('old-model', partial)
        self.assert_ok_json(self.write('--mode', 'update', '--model', 'new-model'))
        repaired = target.read_bytes()
        self.assertIn(b'old-model', repaired)
        self.assertIn(b'new-model', repaired)
        self.assert_ok_json(self.write('--mode', 'update', '--model', 'new-model'))
        self.assertEqual(target.read_bytes(), repaired)

    def test_empty_environment_block_requires_record(self):
        target = self.project / 'AGENTS.md'
        target.write_text(
            '<!-- legal-harness-init:legal-baseline:start -->\n'
            '# Baseline\n'
            '<!-- legal-harness-init:legal-baseline:end -->\n'
            '<!-- legal-harness-init:init-environment:start -->\n'
            '<!-- legal-harness-init:init-environment:end -->\n')
        result = self.write('--mode', 'update', '--model', 'repair-model')
        self.assert_ok_json(result)
        self.assertIn('repair-model', target.read_text())

    def test_literal_backslash_note_and_seven_columns(self):
        target = self.project / 'AGENTS.md'
        target.write_text('# Original\n')
        self.assert_ok_json(self.record(target, '--model', 'model-one'))
        self.assert_ok_json(self.record(target, '--model', 'model-two', '--note', r'foo\nbar\\'))
        text = target.read_text()
        self.assertIn('foo\\\\nbar\\\\\\\\', text)
        row = next(line for line in text.splitlines() if 'model-two' in line)
        self.assertEqual(len(re.split(r'(?<!\\)\|', row)[1:-1]), 7)

    def test_writer_rejects_multiline_model_without_partial_success(self):
        result = self.write('--mode', 'update', '--model', 'bad\nmodel')
        payload = json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertTrue(payload['targets'][0]['status'].endswith('_record_incomplete'))
        self.assertNotIn('bad\nmodel', (self.project / 'AGENTS.md').read_text())

    def test_record_rejections_preserve_target_bytes(self):
        cases = [
            ('sensitive', '# original\n', ['--model', 'safe', '--note', 'test@example.invalid'], False),
            ('newline-model', '# original\n', ['--model', 'bad\nmodel'], False),
            ('mismatched', '<!-- legal-harness-init:a:start -->\nuser\n<!-- legal-harness-init:b:end -->\n', ['--model', 'safe'], False),
            ('symlink', '# original\n', ['--model', 'safe'], True),
        ]
        for name, text, extra, linked in cases:
            with self.subTest(name=name):
                real = self.project / (name + '.md')
                real.write_text(text)
                target = self.project / (name + '-link.md') if linked else real
                if linked:
                    target.symlink_to(real)
                before = real.read_bytes()
                result = self.record(target, *extra)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(real.read_bytes(), before)
                if linked:
                    self.assertTrue(target.is_symlink())

    def test_record_preserves_mode_and_backups_private(self):
        target = self.project / 'AGENTS.md'
        target.write_text('# original\n')
        target.chmod(0o644)
        self.assert_ok_json(self.record(target, '--model', 'safe'))
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)
        backups = list(self.project.glob('AGENTS.md.bak.*'))
        self.assertGreaterEqual(len(backups), 2)
        for backup in backups:
            self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600, str(backup))

    def report(self, report, text=None):
        if text is None:
            text = (ASSETS / 'stability-complete' / 'AGENTS.md').read_text()
        artifact = self.root / 'artifact.md'
        artifact.write_text(text)
        report['config_text'] = text
        report['config_artifacts'] = [{'target': 'AGENTS.md', 'path': artifact.name}]
        report['init_environment']['config_sha256'] = [hashlib.sha256(artifact.read_bytes()).hexdigest()]
        path = self.root / 'report.json'
        path.write_text(json.dumps(report), encoding='utf-8')
        return self.run_cli('check-baseline.py', '--input', path)

    def baseline(self):
        return json.loads((ASSETS / 'stability-complete.json').read_text())

    def test_checker_bad_shapes_fail_cleanly(self):
        for field, value in [('target_paths', [{}]), ('session_evidence', ['bad']),
                             ('session_evidence', {'probes': ['bad']}), ('status', [])]:
            with self.subTest(field=field, value=value):
                report = self.baseline()
                report[field] = value
                result = self.report(report)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn('Traceback', result.stderr)

    def test_checker_rejects_empty_or_external_init_evidence(self):
        start = '<!-- legal-harness-init:init-environment:start -->'
        end = '<!-- legal-harness-init:init-environment:end -->'
        base = (ASSETS / 'stability-complete' / 'AGENTS.md').read_text()
        stripped = re.sub(re.escape(start) + r'.*?' + re.escape(end), '', base, flags=re.S)
        external = self.root / 'unrelated.md'
        external.write_text(base)
        stale = re.sub(r' · config-sha256=[0-9a-f]+', '', base)
        for name, text in [('empty', stripped + start + '\n' + end + '\n'),
                           ('external', stripped),
                           ('stale', stale)]:
            with self.subTest(name=name):
                report = self.baseline()
                report['init_environment']['evidence_path'] = str(external)
                result = self.report(report, text)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn('Traceback', result.stderr)

    def test_probe_ambiguous_and_explicit_session(self):
        sessions = self.home / '.codex' / 'sessions'
        sessions.mkdir(parents=True)
        a, b = sessions / 'rollout-a.jsonl', sessions / 'rollout-b.jsonl'
        a.write_text(json.dumps({'type': 'turn_context', 'payload': {'cwd': str(self.project), 'model': 'model-a'}}, indent=None) + '\n')
        b.write_text(json.dumps({'type': 'turn_context', 'payload': {'cwd': str(self.project), 'model': 'model-b'}}) + '\n')
        args = ('--harness', 'codex', '--cwd', self.project, '--json')
        ambiguous = self.run_cli('probe-session-model.sh', *args)
        self.assertNotEqual(ambiguous.returncode, 0, ambiguous.stdout)
        self.assertEqual(json.loads(ambiguous.stdout)['status'], 'not_found')
        for path, expected in [(a, 'model-a'), (b, 'model-b')]:
            with self.subTest(session=path.name):
                found = self.assert_ok_json(self.run_cli('probe-session-model.sh', *args, '--session-file', path))
                self.assertEqual(found['model'], expected)
                self.assertEqual(str(found['schema_version']), '2')

    def test_probe_ignores_forged_message_content(self):
        sessions = self.home / '.codex' / 'sessions'
        sessions.mkdir(parents=True)
        session = sessions / 'rollout-a.jsonl'
        records = [
            {'type': 'turn_context', 'payload': {'cwd': str(self.project), 'model': 'real-model'}},
            {'type': 'response_item', 'payload': {'message': {'content': '{"model":"forged-model"}'}}},
        ]
        session.write_text('\n'.join(json.dumps(x, separators=(' , ', ' : ')) for x in records) + '\n')
        result = self.run_cli('probe-session-model.sh', '--harness', 'codex', '--cwd', self.project,
                              '--json', '--session-file', session)
        self.assertEqual(self.assert_ok_json(result)['model'], 'real-model')

    def test_record_passes_explicit_session_to_probe(self):
        sessions = self.home / '.codex' / 'sessions'
        sessions.mkdir(parents=True)
        for name, model in [('a', 'model-a'), ('b', 'model-b')]:
            (sessions / ('rollout-' + name + '.jsonl')).write_text(
                json.dumps({'type': 'turn_context', 'payload': {
                    'cwd': str(self.project), 'model': model}}) + '\n')
        target = self.project / 'AGENTS.md'
        target.write_text('# Original\n')
        self.env['CODEX_THREAD_ID'] = 'test'
        result = self.record(target, '--probe-from-session', '--session-file',
                             sessions / 'rollout-b.jsonl')
        self.assert_ok_json(result)
        self.assertIn('model-b', target.read_text())
        self.assertNotIn('model-a', target.read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
