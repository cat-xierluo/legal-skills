#!/usr/bin/env python3
"""真实隔离 Git 样例：完整登记、材料与身份不变、证据边界。"""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('audit', HERE / 'sparse-worktree-audit.py')
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.lab = tempfile.TemporaryDirectory(prefix='sparse-audit-test-'); self.addCleanup(self.lab.cleanup)
        self.root = Path(self.lab.name).resolve(); self.repo = self.root / 'main repo'; self.repo.mkdir()
        self.git('init', '-b', 'main'); self.git('config', 'user.name', 'Fixture'); self.git('config', 'user.email', 'fixture@example.invalid')
        for directory in ['skills/中文 skill', 'skills/other', '.claude/skills/hidden']:
            p = self.repo / directory; p.mkdir(parents=True); (p / 'SKILL.md').write_text('fixture\n')
        (self.repo / '.gitignore').write_text('*.private\n'); self.git('add', '.'); self.git('commit', '-m', 'fixture')
        self.first = self.root / 'outside' / 'worker'; self.second = self.root / 'another' / 'worker'
        self.git('worktree', 'add', '-b', 'first', str(self.first)); self.git('worktree', 'add', '-b', 'second', str(self.second))
    def git(self, *args, repo=None):
        return subprocess.check_output(['git', '-C', str(repo or self.repo), *args], stderr=subprocess.DEVNULL)
    def command(self, *args, env=None):
        return subprocess.run(['python3', str(HERE / 'sparse-worktree-audit.py'), '--repo', str(self.repo), *args], capture_output=True, text=True, env=env)
    def rows(self): return audit.audit([self.repo])['repositories'][0]['worktrees']
    def test_registration_covers_distinct_external_folders(self):
        rows = self.rows(); self.assertEqual({r['path'] for r in rows}, {str(self.repo), str(self.first), str(self.second)})
        self.assertEqual(sum(r['primary'] for r in rows), 1)
    def test_common_dir_aliases_are_deduplicated(self):
        alias = self.root / 'alias'; alias.symlink_to(self.repo, target_is_directory=True)
        self.assertEqual(len(audit.audit([self.repo, self.first, alias])['repositories']), 1)
    def test_sparse_full_and_hidden_skill_observed(self):
        self.git('sparse-checkout', 'set', '--cone', 'skills/中文 skill', repo=self.first)
        rows = {r['path']:r for r in self.rows()}
        self.assertTrue(rows[str(self.first)]['sparse']); self.assertFalse(rows[str(self.second)]['sparse'])
        self.assertIn('.claude/skills/hidden', rows[str(self.second)]['skill_directories'])
        self.assertEqual(rows[str(self.repo)]['assessment'], 'primary-preserved')
    def test_dirty_staged_local_material_and_refs_unchanged(self):
        p = self.first / 'skills/other/SKILL.md'; p.write_text('staged\n'); self.git('add', str(p), repo=self.first); p.write_text('dirty\n')
        (self.first / 'new-file').write_text('untracked'); private = self.first / 'config.private'; private.write_text('secret-fixture-value')
        before = [self.git(*args, repo=self.first) for args in [('status', '--porcelain', '-z'), ('ls-files', '--stage', '-z'), ('rev-parse', 'HEAD')]]
        report = audit.audit([self.repo]); after = [self.git(*args, repo=self.first) for args in [('status', '--porcelain', '-z'), ('ls-files', '--stage', '-z'), ('rev-parse', 'HEAD')]]
        self.assertEqual(before, after); self.assertEqual(private.read_text(), 'secret-fixture-value')
        row = next(r for r in report['repositories'][0]['worktrees'] if r['path'] == str(self.first))
        self.assertGreater(row['dirty_count'], 0); self.assertEqual(row['untracked_count'], 1); self.assertEqual(row['ignored_count'], 1)
        self.assertNotIn('secret-fixture-value', json.dumps(report)); self.assertIsNone(row['cwd_pids'])
    def test_missing_registration_is_retained_and_reported(self):
        # Move this fixture's checkout only; Git registration remains for inspection.
        self.second.rename(self.root / 'moved-fixture')
        self.assertEqual(next(r for r in self.rows() if r['path'] == str(self.second))['state'], 'missing')
        self.assertIn(str(self.second).encode(), self.git('worktree', 'list', '--porcelain'))
    def test_private_output_outside_all_checkouts_is_0600(self):
        path = self.root / 'private-evidence' / 'audit.json'; p = self.command('--output', str(path))
        self.assertEqual(p.returncode, 0, p.stderr); self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(len(json.loads(path.read_text())['repositories'][0]['worktrees']), 3)
        self.assertNotIn('skill_directories', p.stdout)
    def test_output_inside_worker_or_git_dir_is_refused(self):
        for path in [self.repo / 'audit.json', self.first / 'audit.json', self.repo / '.git/audit.json']:
            p = self.command('--output', str(path)); self.assertEqual(p.returncode, 2, p.stderr); self.assertFalse(path.exists())
    def test_existing_evidence_is_never_overwritten(self):
        path = self.root / 'evidence.json'; path.write_text('original')
        self.assertEqual(self.command('--output', str(path)).returncode, 2); self.assertEqual(path.read_text(), 'original')
    def test_git_environment_override_refused_without_output(self):
        path = self.root / 'evidence.json'; env = {**os.environ, 'GIT_INDEX_FILE': str(self.root / 'foreign-index')}
        self.assertEqual(self.command('--output', str(path), env=env).returncode, 2); self.assertFalse(path.exists())
    def test_rename_status_is_one_change(self):
        self.git('mv', 'skills/other/SKILL.md', 'skills/other/renamed.md', repo=self.first)
        row = next(r for r in self.rows() if r['path'] == str(self.first)); self.assertEqual(row['dirty_count'], 1)
    def test_replaced_registration_symlink_cannot_classify_primary_as_worker(self):
        self.first.rename(self.root / 'original-worker'); self.first.symlink_to(self.repo, target_is_directory=True)
        row = next(r for r in self.rows() if r['path'] == str(self.first))
        self.assertEqual(row['state'], 'unreadable'); self.assertIn('根目录与登记路径', row['error'])
        self.assertNotIn('assessment', row)
    def test_repository_fsmonitor_helper_never_executes(self):
        marker = self.root / 'marker'; helper = self.root / 'fsmonitor.sh'
        helper.write_text('#!/bin/sh\nprintf invoked >> "'+str(marker)+'"\n'); helper.chmod(0o700)
        self.git('config', 'core.fsmonitor', str(helper))
        report = audit.audit([self.repo]); self.assertTrue(all(r['state'] == 'valid' for r in report['repositories'][0]['worktrees']))
        self.assertFalse(marker.exists())
    def test_clean_filter_status_is_not_executed_or_claimed_verified(self):
        marker = self.root / 'clean-marker'; helper = self.root / 'clean.sh'
        helper.write_text('#!/bin/sh\nprintf invoked >> "'+str(marker)+'"\ncat\n'); helper.chmod(0o700)
        self.git('config', 'filter.fixture.clean', str(helper))
        (self.first / '.gitattributes').write_text('data filter=fixture\n'); (self.first / 'data').write_text('before')
        self.git('add', '.gitattributes', 'data', repo=self.first); self.git('commit', '-m', 'filter fixture', repo=self.first)
        marker.unlink(missing_ok=True); (self.first / 'data').write_text('after!')
        report = audit.audit([self.repo]); self.assertFalse(marker.exists())
        row = next(r for r in report['repositories'][0]['worktrees'] if r['path'] == str(self.first))
        self.assertIsNone(row['dirty_count']); self.assertEqual(row['material_scan'], 'NOT_VERIFIED_EXTERNAL_FILTER')
    def test_failed_filter_config_read_never_executes_status(self):
        marker = self.root / 'filter-marker'
        helper = self.root / 'filter-helper.sh'
        helper.write_text('#!/bin/sh\ntouch "'+str(marker)+'"\ncat\n'); helper.chmod(0o700)
        self.git('config', 'filter.fixture.clean', str(helper))
        (self.first / '.gitattributes').write_text('data filter=fixture\n')
        (self.first / 'data').write_text('before')
        self.git('add', '.gitattributes', 'data', repo=self.first)
        self.git('commit', '-m', 'fixture filter', repo=self.first)
        marker.unlink(missing_ok=True); (self.first / 'data').write_text('changed')
        original_run = audit.run
        status_calls = []
        def injected(args, input_bytes=None):
            if '--get-regexp' in args:
                return subprocess.CompletedProcess(args, 7, b'', b'fixture failure')
            if 'status' in args:
                status_calls.append(args)
            return original_run(args, input_bytes)
        with patch.object(audit, 'run', side_effect=injected):
            rows = self.rows()
        self.assertTrue(all(r['state'] == 'unreadable' for r in rows))
        self.assertFalse(status_calls)
        self.assertFalse(marker.exists())

    def test_unused_configured_filter_does_not_block_status(self):
        self.git('config', 'filter.unused.process', 'must-not-run-unused-helper')
        row = next(r for r in self.rows() if r['path'] == str(self.first))
        self.assertEqual(row['dirty_count'], 0); self.assertEqual(row['material_scan'], 'status-observed')


if __name__ == '__main__': unittest.main(verbosity=2)
