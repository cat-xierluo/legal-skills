#!/usr/bin/env python3
"""Isolated integration regressions. Every identifier is generated synthetic data."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import hashlib
import shutil

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from privacy_check import Checker, PrivacyError, digest
BATCH = SCRIPTS.parents[1] / 'git-batch-commit/scripts/interactive_commit.py'
CASE = '(' + '2099' + ')' + '示例法院' + '民初' + '7654321' + '号'
PHONE = '1' + '38' + '0000' + '0000'
ENV = dict(os.environ, GIT_AUTHOR_NAME='Privacy Test', GIT_AUTHOR_EMAIL='privacy@example.invalid',
           GIT_COMMITTER_NAME='Privacy Test', GIT_COMMITTER_EMAIL='privacy@example.invalid',
           GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')


class PrivacyIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='privacy-tests-')
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.remote = self.root / 'remote.git'
        self.cmd('git', 'init', '--bare', str(self.remote), cwd=self.root)
        self.cmd('git', 'init', '-b', 'main', str(self.repo), cwd=self.root)
        self.git('remote', 'add', 'origin', str(self.remote))
        self.write('base.txt', 'base\n')
        self.commit('base')
        self.git('push', '-u', 'origin', 'main')
        self.base = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('switch', '-c', 'feat/privacy')

    def tearDown(self):
        self.tmp.cleanup()

    def cmd(self, *args, cwd=None, check=True, env=None):
        return subprocess.run(args, cwd=cwd or self.repo, env=env or ENV,
                              capture_output=True, text=True, check=check)

    def git(self, *args, **kwargs):
        return self.cmd('git', *args, **kwargs)

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, message):
        self.git('add', '-A')
        self.git('commit', '-m', message)
        return self.git('rev-parse', 'HEAD').stdout.strip()

    def outgoing(self):
        checker = Checker(self.repo)
        checker.scan_range(self.base, self.git('rev-parse', 'HEAD').stdout.strip())
        checker.finish()

    def batch(self, *args):
        return self.cmd(sys.executable, str(BATCH), *args, check=False)

    def assert_private_failure(self, result, marker=CASE):
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn(marker, result.stdout + result.stderr)

    def test_message_only_leak_is_blocked(self):
        self.git('commit', '--allow-empty', '-m', 'docs: normal\n\n' + CASE)
        with self.assertRaisesRegex(PrivacyError, 'case-number') as error:
            self.outgoing()
        self.assertNotIn(CASE, str(error.exception))

    def test_intermediate_content_deleted_later_still_blocks(self):
        self.write('note.txt', CASE)
        self.commit('add sample')
        (self.repo / 'note.txt').unlink()
        self.commit('remove sample')
        self.assertEqual('', self.git('diff', self.base, 'HEAD').stdout)
        with self.assertRaisesRegex(PrivacyError, 'case-number'):
            self.outgoing()

    def test_mobile_and_local_denylist_diagnostics_are_redacted(self):
        (self.repo / '.git/privacy-denylist').write_text('private synthetic client\n')
        checker = Checker(self.repo)
        checker.scan_text(PHONE + ' private synthetic client', 'message')
        with self.assertRaises(PrivacyError) as error:
            checker.finish()
        self.assertNotIn(PHONE, str(error.exception))
        self.assertNotIn('private synthetic client', str(error.exception))

    def test_known_pr_and_issue_numbers_pass(self):
        self.write('note.md', '# ordinary PR #227\nRefs #13\n(2026)苏XXXX民初XXXX号\n')
        self.commit('fix(git-workflow): normal (#227)\n\nRefs #13')
        self.outgoing()

    def test_all_groups_preflight_before_first_commit_with_yes(self):
        self.write('a.json', '{"ordinary": true}')
        self.write('z.md', '# ' + CASE)
        self.git('add', '-A')
        snapshot = self.git('write-tree').stdout
        result = self.batch('--yes')
        self.assert_private_failure(result)
        self.assertEqual(self.base, self.git('rev-parse', 'HEAD').stdout.strip())
        self.assertEqual(snapshot, self.git('write-tree').stdout)

    def test_local_ref_in_final_message_is_blocked_with_yes(self):
        self.write('normal.txt', 'normal')
        self.git('add', '-A')
        result = self.batch('--yes', '--local-ref', CASE)
        self.assert_private_failure(result)
        self.assertEqual(self.base, self.git('rev-parse', 'HEAD').stdout.strip())

    def test_dry_run_does_not_echo_generated_sensitive_message(self):
        self.write('note.md', '# ' + CASE)
        self.git('add', '-A')
        self.assert_private_failure(self.batch('--dry-run'))

    def test_partially_staged_snapshot_and_index_are_preserved(self):
        self.write('normal.txt', 'approved staged bytes\n')
        self.git('add', 'normal.txt')
        snapshot = self.git('write-tree').stdout
        self.write('normal.txt', 'unstaged ' + CASE)
        result = self.batch('--yes', '--issue', '227')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('approved staged bytes\n', self.git('show', 'HEAD:normal.txt').stdout)
        self.assertEqual(snapshot, self.git('write-tree').stdout)
        self.assertEqual('unstaged ' + CASE, (self.repo / 'normal.txt').read_text())
        self.assertIn('(#227)', self.git('show', '-s', '--format=%B').stdout)

    def test_multiple_groups_and_deletion_keep_exact_tree(self):
        self.write('a.json', '{"ok": true}\n')
        self.write('b.md', '# Clean\n')
        (self.repo / 'base.txt').unlink()
        self.git('add', '-A')
        snapshot = self.git('write-tree').stdout.strip()
        result = self.batch('--yes')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(snapshot, self.git('rev-parse', 'HEAD^{tree}').stdout.strip())
        self.assertEqual('', self.git('diff', '--cached').stdout)
        self.assertGreater(int(self.git('rev-list', '--count', self.base + '..HEAD').stdout), 1)

    def test_shallow_missing_empty_and_nonancestor_ranges_fail(self):
        checker = Checker(self.repo)
        with self.assertRaises(PrivacyError):
            checker.scan_range(self.base, '0' * 40)
        with self.assertRaisesRegex(PrivacyError, 'EMPTY_RANGE'):
            checker.scan_range(self.base, self.base)
        self.write('clean.txt', 'clean')
        head = self.commit('clean')
        with self.assertRaises(PrivacyError):
            checker.scan_range(head, self.base)
        (self.repo / '.git/shallow').write_text(head + '\n')
        with self.assertRaisesRegex(PrivacyError, 'HISTORY_INCOMPLETE'):
            checker.scan_range(self.base, head)

    def test_missing_blob_fails_closed(self):
        self.write('clean.txt', 'unique clean body')
        self.commit('clean')
        oid = self.git('rev-parse', 'HEAD:clean.txt').stdout.strip()
        (self.repo / '.git/objects' / oid[:2] / oid[2:]).unlink()
        with self.assertRaisesRegex(PrivacyError, 'GIT_READ_FAILED'):
            self.outgoing()

    def test_binary_staged_content_fails_closed(self):
        (self.repo / 'data.bin').write_bytes(b'\0' + CASE.encode())
        self.git('add', '-A')
        checker = Checker(self.repo)
        checker.scan_staged()
        with self.assertRaisesRegex(PrivacyError, 'binary-content'):
            checker.finish()

    def test_printable_pdf_still_requires_format_review(self):
        checker = Checker(self.repo)
        checker.scan_bytes(b'%PDF-1.4\nprintable container', 'blob:sample.pdf')
        with self.assertRaisesRegex(PrivacyError, 'binary-content'):
            checker.finish()

    def test_versioned_commit_msg_hook_blocks_final_text(self):
        target = self.repo / 'skills/git-workflow/scripts'
        target.mkdir(parents=True)
        shutil.copyfile(SCRIPTS / 'privacy_check.py', target / 'privacy_check.py')
        message = self.root / 'COMMIT_EDITMSG'
        message.write_text('docs: clean\n\n' + CASE)
        hook = SCRIPTS.parents[2] / '.githooks/commit-msg'
        result = self.cmd('bash', str(hook), str(message), check=False)
        self.assert_private_failure(result)
        self.assertIn('case-number', result.stderr)

    def approve(self, kind='synthetic', source='sample', text=CASE, rule='case-number'):
        entry = dict(rule=rule, source_sha256=digest(source), content_sha256=digest(text),
                     kind=kind, reason='Reviewed artificial test fixture', reviewed_by='test reviewer',
                     evidence='https://example.invalid/synthetic-public-judgment-fixture' if kind == 'public-judgment' else 'generated test fixture')
        (self.repo / '.git/privacy-reviewed.json').write_text(json.dumps([entry]))

    def test_synthetic_exact_review_and_changed_text_block(self):
        self.approve()
        checker = Checker(self.repo)
        checker.scan_text(CASE, 'sample')
        checker.finish()
        checker.scan_text(CASE + ' changed', 'sample')
        with self.assertRaisesRegex(PrivacyError, 'REVIEW_REQUIRED'):
            checker.finish()

    def test_public_judgment_exact_review_no_directory_or_other_rule_bypass(self):
        self.approve('public-judgment')
        checker = Checker(self.repo)
        checker.scan_text(CASE, 'sample')
        checker.finish()
        checker.scan_text(CASE, 'another-file')
        checker.scan_text(PHONE, 'sample')
        with self.assertRaisesRegex(PrivacyError, 'mobile'):
            checker.finish()

    def test_invalid_public_waiver_and_unreadable_policy_fail(self):
        self.approve('public-judgment', rule='mobile')
        with self.assertRaisesRegex(PrivacyError, 'POLICY_INVALID'):
            Checker(self.repo)
        (self.repo / '.git/privacy-reviewed.json').write_text('{bad json')
        with self.assertRaisesRegex(PrivacyError, 'POLICY_INVALID'):
            Checker(self.repo)

    def test_safe_push_blocks_early_leak_without_remote_write(self):
        self.write('note.txt', CASE)
        self.commit('sample')
        self.write('note.txt', 'clean')
        self.commit('clean')
        result = self.cmd('bash', str(SCRIPTS / 'safe-push.sh'), '--base', 'main',
                          '--expected-name', 'Privacy Test', '--expected-email', 'privacy@example.invalid', check=False)
        self.assert_private_failure(result)
        self.assertEqual('', self.git('ls-remote', 'origin', 'refs/heads/feat/privacy').stdout)

    def test_binary_review_is_exact_and_requires_review_artifact(self):
        content = b'\0' + b'synthetic-image-fixture'
        entry = dict(rule='binary-content', source_sha256=digest('blob:sample.bin'),
                     content_sha256=hashlib.sha256(content).hexdigest(), kind='reviewed-binary',
                     reason='Rendered and reviewed synthetic fixture', reviewed_by='test reviewer',
                     evidence='sha256:' + digest('independent rendered inspection artifact'))
        (self.repo / '.git/privacy-reviewed.json').write_text(json.dumps([entry]))
        checker = Checker(self.repo)
        checker.scan_bytes(content, 'blob:sample.bin')
        checker.finish()
        checker.scan_bytes(content + b'changed', 'blob:sample.bin')
        with self.assertRaisesRegex(PrivacyError, 'binary-content'):
            checker.finish()
        entry['evidence'] = 'did not inspect'
        (self.repo / '.git/privacy-reviewed.json').write_text(json.dumps([entry]))
        with self.assertRaisesRegex(PrivacyError, 'POLICY_INVALID'):
            Checker(self.repo)

    def test_later_generated_message_failure_creates_no_earlier_commit(self):
        self.write('a.json', '{"clean": true}')
        self.write('z.md', '# Clean')
        self.git('add', '-A')
        runner = self.root / 'runner.py'
        runner.write_text('import sys\nfrom unittest.mock import patch\n'
                          + f'sys.path.insert(0, {str(BATCH.parent)!r})\n'
                          + 'import interactive_commit as batch\n'
                          + 'def messages(groups):\n'
                          + f' return {{key: "docs: clean\\n\\n" + ({CASE!r} if index else "clean") for index,key in enumerate(sorted(groups))}}\n'
                          + 'with patch.object(batch, "generate_commit_messages", messages):\n'
                          + ' sys.exit(batch.batch_commit(skip_confirm=True))\n')
        result = self.cmd(sys.executable, str(runner), check=False)
        self.assert_private_failure(result)
        self.assertIn('case-number', result.stderr)
        self.assertEqual(self.base, self.git('rev-parse', 'HEAD').stdout.strip())

    def test_hook_message_mutation_stops_batch_without_publishing(self):
        self.write('a.json', '{"clean": true}')
        self.write('z.md', '# Clean')
        self.git('add', '-A')
        snapshot = self.git('write-tree').stdout
        hook = self.repo / '.git/hooks/commit-msg'
        hook.write_text('#!/bin/sh\nprintf "\\nchanged by fixture hook\\n" >> "$1"\n')
        hook.chmod(0o755)
        result = self.batch('--yes')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('PRIVACY_COMMIT_CHANGED', result.stderr)
        self.assertEqual('1', self.git('rev-list', '--count', self.base + '..HEAD').stdout.strip())
        self.assertEqual(snapshot, self.git('write-tree').stdout)
        self.assertEqual('', self.git('ls-remote', 'origin', 'refs/heads/feat/privacy').stdout)

    def test_head_race_during_privacy_check_never_pushes(self):
        self.write('one.txt', 'clean one')
        first = self.commit('first')
        self.write('two.txt', 'clean two')
        second = self.commit('second')
        self.git('update-ref', 'refs/heads/feat/privacy', first)
        binary = self.root / 'bin'
        binary.mkdir()
        real_git = shutil.which('git')
        fake = binary / 'git'
        fake.write_text('#!' + sys.executable + '\nimport subprocess,sys\n'
                        + f'real={real_git!r}\n'
                        + 'if "--format=%B" in sys.argv:\n'
                        + f' subprocess.run([real,"-C",{str(self.repo)!r},"update-ref","refs/heads/feat/privacy",{second!r}], check=True)\n'
                        + 'sys.exit(subprocess.run([real,*sys.argv[1:]]).returncode)\n')
        fake.chmod(0o755)
        env = dict(ENV, PATH=str(binary) + os.pathsep + ENV['PATH'])
        result = self.cmd('bash', str(SCRIPTS / 'safe-push.sh'), '--base', 'main',
                          '--expected-name', 'Privacy Test', '--expected-email', 'privacy@example.invalid',
                          env=env, check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn('SAFE_PUSH_HEAD_CHANGED', result.stderr)
        self.assertEqual('', self.git('ls-remote', 'origin', 'refs/heads/feat/privacy').stdout)

    def fake_gh(self, metadata):
        binary = self.root / 'bin'
        binary.mkdir()
        data = self.root / 'metadata.json'
        data.write_text(json.dumps(metadata))
        log = self.root / 'gh-log.jsonl'
        fake = binary / 'gh'
        fake.write_text('#!' + sys.executable + '\nimport json,sys\nfrom pathlib import Path\n'
                        + f'log=Path({str(log)!r})\n'
                        + 'with log.open("a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
                        + 'if sys.argv[1:3] == ["pr", "view"]:\n'
                        + f' print(Path({str(data)!r}).read_text())\n'
                        + 'elif sys.argv[1:3] == ["pr", "create"]: print("https://github.com/example/example/pull/1")\n')
        fake.chmod(0o755)
        # Local transport stays isolated; advertise a GitHub URL to the target parser.
        git_stub = binary / 'git'
        git_stub.write_text('#!' + sys.executable + '\nimport subprocess,sys\n'
                            + 'if sys.argv[-3:] == ["remote","get-url","origin"]:\n'
                            + ' print("git@github.com:example/example.git")\n'
                            + 'else:\n'
                            + f' sys.exit(subprocess.run([{shutil.which("git")!r},*sys.argv[1:]]).returncode)\n')
        git_stub.chmod(0o755)
        return dict(ENV, PATH=str(binary) + os.pathsep + ENV['PATH']), log

    def safe_pr(self, mode, title='fix(git-workflow): clean (#227)', body='Clean summary\n', pr_body='Clean PR'):
        self.write('clean.txt', 'clean')
        head = self.commit('clean')
        self.git('push', 'origin', 'HEAD:refs/heads/feat/privacy', 'HEAD:refs/pull/227/head')
        title_file, body_file = self.root / 'title', self.root / 'body'
        title_file.write_text(title)
        body_file.write_text(body)
        env, log = self.fake_gh(dict(headRefOid=head, baseRefName='main', title=title, body=body if mode == 'create' else pr_body, state='OPEN', isDraft=False))
        extra = ['--base', 'main', '--head', 'feat/privacy'] if mode == 'create' else ['--number', '227']
        result = self.cmd(sys.executable, str(SCRIPTS / 'safe-pr.py'), mode, '--expected-head', head,
                          '--title-file', str(title_file), '--body-file', str(body_file), *extra, env=env, check=False)
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, calls, head

    def test_github_target_normalizes_https_and_ssh_without_credentials(self):
        spec = importlib.util.spec_from_file_location('safe_pr_fixture', SCRIPTS / 'safe-pr.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for remote in ('https://github.com/example/example.git',
                       'https://fixture-user:fixture-password@github.com/example/example.git',
                       'git@github.com:example/example.git',
                       'ssh://git@github.com/example/example.git'):
            with self.subTest(remote=remote):
                self.assertEqual('github.com/example/example', module.github_target(remote))
        with self.assertRaises(PrivacyError):
            module.github_target('/local/path')

    def test_pr_body_blocks_creation(self):
        result, calls, _ = self.safe_pr('create', body='Summary ' + CASE)
        self.assert_private_failure(result)
        self.assertFalse(any(call[:2] == ['pr', 'create'] for call in calls))

    def test_pr_title_blocks_creation(self):
        result, calls, _ = self.safe_pr('create', title=CASE)
        self.assert_private_failure(result)
        self.assertFalse(any(call[:2] == ['pr', 'create'] for call in calls))

    def test_squash_final_body_blocks_merge(self):
        result, calls, _ = self.safe_pr('squash', body=CASE)
        self.assert_private_failure(result)
        self.assertFalse(any(call[:2] == ['pr', 'merge'] for call in calls))

    def test_existing_pr_body_blocks_squash(self):
        result, calls, _ = self.safe_pr('squash', pr_body=CASE)
        self.assert_private_failure(result)
        self.assertFalse(any(call[:2] == ['pr', 'merge'] for call in calls))

    def test_clean_creation_sends_exact_text_and_draft(self):
        result, calls, _ = self.safe_pr('create')
        self.assertEqual(0, result.returncode, result.stderr)
        create = next(call for call in calls if call[:2] == ['pr', 'create'])
        self.assertIn('--draft', create)
        self.assertEqual('github.com/example/example', create[create.index('--repo') + 1])
        self.assertEqual('Clean summary\n', create[create.index('--body') + 1])

    def test_clean_squash_binds_head_and_exact_body(self):
        result, calls, head = self.safe_pr('squash')
        self.assertEqual(0, result.returncode, result.stderr)
        merge = next(call for call in calls if call[:2] == ['pr', 'merge'])
        self.assertEqual(head, merge[merge.index('--match-head-commit') + 1])
        self.assertEqual('Clean summary\n', merge[merge.index('--body') + 1])


if __name__ == '__main__':
    unittest.main()
