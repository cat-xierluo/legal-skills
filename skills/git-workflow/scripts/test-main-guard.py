#!/usr/bin/env python3
"""隔离 Git 仓库验证分支保护；不访问用户仓库，不下载依赖。"""
import importlib.util
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('guard', Path(__file__).with_name('main-guard.py'))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


@unittest.skipUnless(platform.system() == 'Darwin', 'macOS 真实 uchg 测试，其他平台未验')
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='main-guard-test-')
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init', '-b', 'main')
        # 身份只设置在隔离夹具，绝不写真实仓库或 global。
        self.git('config', 'user.name', 'Guard Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.repo / 'skill').mkdir()
        (self.repo / 'skill/TASKS.md').write_text('original\n')
        (self.repo / '.gitignore').write_text('ignored-data\n')
        self.git('add', '.')
        self.git('commit', '-m', 'fixture')
        self.head = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('update-ref', 'refs/remotes/origin/main', self.head)
        self.git('branch', 'other')
        self.receipt = self.root / 'handoff.json'
        self.handoff = dict(state='SAFE_STOPPED', head=self.head, owner='fixture-owner',
                            unknown_git_writers=False, owners=[dict(name='fixture-owner', state='SAFE_STOPPED')])
        self.receipt.write_text(json.dumps(self.handoff))
        self.state = self.root / 'state.json'
        self.args = SimpleNamespace(repo=str(self.repo), expected_head=self.head, base=self.head,
                                    handoff=str(self.receipt), state=str(self.state), allow_index_blocking=True)

    def git(self, *args, cwd=None, check=True):
        return subprocess.run(['git', '-C', str(cwd or self.repo), *args], capture_output=True,
                              text=True, check=check)

    def tearDown(self):
        # 只解除测试 TemporaryDirectory 中的 flags，允许失败现场安全回收。
        for root, ds, fs in os.walk(self.root, followlinks=False):
            for p in [Path(root)] + [Path(root) / n for n in ds + fs]:
                if p.exists() or p.is_symlink():
                    os.chflags(p, 0, follow_symlinks=False)
        self.tmp.cleanup()

    def install(self):
        return guard.install(self.args)

    def test_default_install_does_not_block_add_commit(self):
        self.args.allow_index_blocking = False
        with self.assertRaises(guard.GuardError):
            self.install()
        self.assertFalse((self.repo / '.git/index.lock').exists())
        self.assertFalse(self.state.exists())
        (self.repo / 'skill/TASKS.md').write_text('ordinary main edit\n')
        self.assertEqual(self.git('add', 'skill/TASKS.md').returncode, 0)
        self.assertEqual(self.git('commit', '-m', 'ordinary').returncode, 0)

    def test_edit_allowed_switch_blocked_before_any_file_change(self):
        self.git('switch', 'other')
        (self.repo / 'skill/TASKS.md').write_text('different branch content\n')
        self.git('commit', '-am', 'other-content')
        self.git('switch', 'main')
        self.install()
        p = self.repo / 'skill/TASKS.md'
        p.write_text('user edit\n')
        (self.repo / 'ignored-data').write_text('local data\n')
        for args in [('switch', 'other'), ('checkout', 'other'), ('switch', '--detach', self.head),
                     ('add', '.'), ('reset', '--hard', 'other')]:
            r = self.git(*args, check=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('index.lock', r.stderr)
            self.assertEqual(p.read_text(), 'user edit\n')
        p.unlink()
        p.write_text('restored edit\n')
        self.assertEqual(guard.verify(SimpleNamespace(state=str(self.state), probe=True))['state'], 'VERIFIED')

    def test_raw_head_and_ref_moves_blocked(self):
        self.install()
        for a in [('symbolic-ref', 'HEAD', 'refs/heads/other'), ('update-ref', '-d', 'refs/heads/main')]:
            self.assertNotEqual(self.git(*a, check=False).returncode, 0)
        self.assertEqual(self.git('symbolic-ref', 'HEAD').stdout.strip(), 'refs/heads/main')

    def test_creation_time_sparse_worktree_commit(self):
        self.install()
        w = self.root / 'worker'
        self.git('worktree', 'add', '--no-checkout', '-b', 'worker', str(w), self.head)
        self.git('sparse-checkout', 'set', '--cone', '--no-sparse-index', 'skill', cwd=w)
        self.git('read-tree', '-mu', self.head, cwd=w)
        (w / 'skill/TASKS.md').write_text('worker changed\n')
        self.git('add', '--', 'skill/TASKS.md', cwd=w)
        self.git('commit', '-m', 'worker-only', cwd=w)
        self.assertNotEqual(self.git('rev-parse', 'HEAD', cwd=w).stdout.strip(), self.head)
        self.assertEqual((self.repo / 'skill/TASKS.md').read_text(), 'original\n')
        guard.verify(SimpleNamespace(state=str(self.state), probe=True))

    def test_release_and_reinstall_new_state(self):
        self.install()
        guard.release(SimpleNamespace(state=str(self.state), owner='fixture-owner', reason='scoped maintenance'))
        self.assertFalse((self.repo / '.git/index.lock').exists())
        self.git('switch', 'other')
        self.git('switch', 'main')
        self.args.state = str(self.root / 'state-2.json')
        self.install()

    def test_release_retries_after_partial_unlock_failure(self):
        self.install()
        args = SimpleNamespace(state=str(self.state), owner='fixture-owner', reason='retry')
        real = os.chflags
        calls = 0
        def fail_once(*a, **kw):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('injected release failure')
            return real(*a, **kw)
        with patch.object(guard.os, 'chflags', side_effect=fail_once):
            with self.assertRaises(OSError): guard.release(args)
        self.assertEqual(json.loads(self.state.read_text())['state'], 'RELEASING')
        with self.assertRaises(guard.GuardError):
            guard.release(SimpleNamespace(state=str(self.state), owner='wrong', reason='retry'))
        self.assertTrue((self.repo / '.git/index.lock').exists())
        self.assertEqual(guard.release(args)['state'], 'RELEASED')
        self.assertFalse((self.repo / '.git/index.lock').exists())
        self.git('add', 'skill/TASKS.md')

    def test_release_retries_after_final_state_write_failure(self):
        self.install()
        args = SimpleNamespace(state=str(self.state), owner='fixture-owner', reason='retry')
        real = guard.save
        def fail_final(p, doc, **kwargs):
            if doc.get('state') == 'RELEASED':
                raise OSError('injected state write failure')
            return real(p, doc, **kwargs)
        with patch.object(guard, 'save', side_effect=fail_final):
            with self.assertRaises(OSError): guard.release(args)
        self.assertFalse((self.repo / '.git/index.lock').exists())
        self.assertEqual(json.loads(self.state.read_text())['state'], 'RELEASING')
        self.assertEqual(guard.release(args)['state'], 'RELEASED')

    def test_release_retry_refuses_replaced_lock(self):
        self.install()
        args = SimpleNamespace(state=str(self.state), owner='fixture-owner', reason='retry')
        with patch.object(guard.os, 'chflags', side_effect=OSError('injected')):
            with self.assertRaises(OSError): guard.release(args)
        lock = self.repo / '.git/index.lock'
        os.chflags(lock, 0)
        lock.write_text('different owner lock\n')
        with self.assertRaises(guard.GuardError): guard.release(args)
        self.assertEqual(lock.read_text(), 'different owner lock\n')

    def test_state_write_failure_keeps_previous_json(self):
        guard.save(self.state, {'state': 'RELEASING'}, new=True)
        before = self.state.read_bytes()
        with patch.object(guard.os, 'replace', side_effect=OSError('injected')):
            with self.assertRaises(OSError): guard.save(self.state, {'state': 'RELEASED'})
        self.assertEqual(self.state.read_bytes(), before)

    def test_existing_flags_preserved_and_external_symlink_untouched(self):
        target = self.root / 'external'
        target.write_text('outside\n')
        (self.repo / 'link').symlink_to(target)
        head = self.repo / '.git/HEAD'
        os.chflags(head, stat.UF_IMMUTABLE)
        self.install()
        target.write_text('still writable\n')
        guard.release(SimpleNamespace(state=str(self.state), owner='fixture-owner', reason='test'))
        self.assertTrue(head.stat().st_flags & stat.UF_IMMUTABLE)
        self.assertEqual(target.stat().st_flags, 0)

    def test_wrong_head(self):
        self.args.expected_head = '0' * 40
        with self.assertRaises(guard.GuardError): self.install()

    def test_wrong_branch(self):
        self.git('switch', 'other')
        with self.assertRaises(guard.GuardError): self.install()

    def test_remote_base_ahead_not_in_main(self):
        self.git('switch', 'other')
        (self.repo / 'remote-only').write_text('remote delivery\n')
        self.git('add', '.')
        self.git('commit', '-m', 'remote')
        remote = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('switch', 'main')
        self.git('update-ref', 'refs/remotes/origin/main', remote)
        self.args.base = remote
        with self.assertRaises(guard.GuardError): self.install()

    def test_owner_receipts_incomplete(self):
        self.handoff['owners'][0]['state'] = 'NOTIFIED'
        self.receipt.write_text(json.dumps(self.handoff))
        with self.assertRaises(guard.GuardError): self.install()

    def test_unknown_writer(self):
        self.handoff['unknown_git_writers'] = True
        self.receipt.write_text(json.dumps(self.handoff))
        with self.assertRaises(guard.GuardError): self.install()

    def test_existing_lock_not_deleted(self):
        lock = self.repo / '.git/index.lock'
        lock.write_text('other writer\n')
        with self.assertRaises(guard.GuardError): self.install()
        self.assertEqual(lock.read_text(), 'other writer\n')

    def test_state_in_repo_and_repeat_refused(self):
        self.args.state = str(self.repo / 'state.json')
        with self.assertRaises(guard.GuardError): self.install()
        self.args.state = str(self.state)
        self.install()
        with self.assertRaises(guard.GuardError): self.install()

    def test_linked_worktree_not_primary(self):
        w = self.root / 'linked'
        self.git('worktree', 'add', str(w), 'other')
        self.args.repo = str(w)
        with self.assertRaises(guard.GuardError): self.install()

    def test_install_final_state_failure_rolls_back(self):
        head = self.repo / '.git/HEAD'
        os.chflags(head, stat.UF_IMMUTABLE)
        real = guard.save
        def fail_final(p, doc, **kwargs):
            if doc.get('state') == 'INSTALLED':
                raise OSError('injected install state write failure')
            return real(p, doc, **kwargs)
        with patch.object(guard, 'save', side_effect=fail_final):
            with self.assertRaises(OSError): self.install()
        self.assertEqual(json.loads(self.state.read_text())['state'], 'INSTALL_FAILED')
        self.assertFalse((self.repo / '.git/index.lock').exists())
        self.assertTrue(head.stat().st_flags & stat.UF_IMMUTABLE)
        for name in ('index', 'refs/heads/main'):
            self.assertFalse((self.repo / '.git' / name).stat().st_flags & stat.UF_IMMUTABLE)

    def test_partial_install_rolls_back_only_own_flags(self):
        real = os.chflags
        calls = 0
        def fail_once(*a, **kw):
            nonlocal calls
            calls += 1
            if calls == 3: raise OSError('injected install failure')
            return real(*a, **kw)
        with patch.object(guard.os, 'chflags', side_effect=fail_once):
            with self.assertRaises(OSError): self.install()
        self.assertEqual(json.loads(self.state.read_text())['state'], 'INSTALL_FAILED')
        self.assertFalse((self.repo / '.git/index.lock').exists())
        self.assertFalse((self.repo / '.git/HEAD').stat().st_flags & stat.UF_IMMUTABLE)

    def test_wrong_release_owner_does_not_unlock(self):
        self.install()
        with self.assertRaises(guard.GuardError):
            guard.release(SimpleNamespace(state=str(self.state), owner='other-owner', reason='test'))
        guard.verify(SimpleNamespace(state=str(self.state), probe=True))

    def test_other_platform_does_not_mutate(self):
        with patch.object(guard.platform, 'system', return_value='Linux'):
            with self.assertRaises(guard.GuardError): self.install()
        self.assertFalse(self.state.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
