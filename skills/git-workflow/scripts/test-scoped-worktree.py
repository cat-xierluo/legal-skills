#!/usr/bin/env python3
"""隔离 Git 行为回归，不访问真实项目、联网或启动 Agent。"""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name('scoped-worktree.py')


class SparseWorktreeTests(unittest.TestCase):
    def setUp(self):
        self.lab = pathlib.Path(tempfile.mkdtemp(prefix='scoped-worktree-test-'))
        self.repo = self.lab / 'repo'
        self.repo.mkdir()
        self.env = os.environ.copy()
        for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_NAMESPACE'):
            self.env.pop(key, None)
        self.git('init', '-q')
        for name, text in {'AGENTS.md': '测试规则\n', 'CLAUDE.md': '测试规则\n',
                           '.gitignore': 'ignored.bin\n', '套件 A/NOTICE.md': '祖先规则\n',
                           '套件 A/skill one/SKILL.md': '测试\n', '套件 A/other/SKILL.md': '范围外\n',
                           'shared/lib/source.py': 'pass\n', 'unrelated/data.bin': '全仓跟踪材料\n'}.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.git('add', '.')
        self.git('-c', 'user.name=Verification', '-c', 'user.email=verification@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '-qm', 'isolated test')
        (self.repo / 'ignored.bin').write_bytes(b'not copied')
        self.oid = self.git('rev-parse', 'HEAD').strip()
        self.index_before = (self.repo / '.git/index').read_bytes()

    def tearDown(self):
        # 只回收 setUp 的私有实验目录，包含本用例创建的全部 Git 元数据。
        shutil.rmtree(self.lab)

    def git(self, *args, cwd=None):
        return subprocess.check_output(['git', '-C', str(cwd or self.repo), *args], env=self.env, text=True)

    def create(self, scopes=None, target=None, branch='verify/scoped', env=None):
        target = target or self.lab / 'new'
        cmd = ['python3', str(SCRIPT), '--repo', str(self.repo), '--path', str(target),
               '--base', 'HEAD', '--branch', branch]
        for scope in scopes or ['套件 A/skill one']:
            cmd += ['--scope', scope]
        return subprocess.run(cmd, env=env or self.env, capture_output=True, text=True)

    def test_selected_scope_root_rules_and_clean_index(self):
        result = self.create()
        self.assertEqual(result.returncode, 0, result.stderr)
        target = pathlib.Path(json.loads(result.stdout)['path'])
        for name in ['套件 A/skill one/SKILL.md', '套件 A/NOTICE.md', 'AGENTS.md', 'CLAUDE.md', '.gitignore']:
            self.assertTrue((target / name).is_file(), name)
        for name in ['套件 A/other', 'shared', 'unrelated', 'ignored.bin']:
            self.assertFalse((target / name).exists(), name)
        self.assertEqual(self.git('status', '--porcelain', cwd=target).strip(), '')
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=target).strip(), self.oid)
        self.assertEqual(self.git('rev-parse', 'HEAD').strip(), self.oid)
        self.assertEqual((self.repo / '.git/index').read_bytes(), self.index_before)
        self.assertEqual(self.git('config', '--bool', '--get', 'index.sparse', cwd=target).strip(), 'false')
        self.assertTrue((self.repo / 'unrelated/data.bin').is_file())

    def test_multiple_scopes_and_append_dependency(self):
        result = self.create(['套件 A/skill one', 'shared/lib'])
        self.assertEqual(result.returncode, 0, result.stderr)
        target = pathlib.Path(json.loads(result.stdout)['path'])
        self.assertTrue((target / 'shared/lib/source.py').exists())
        self.git('sparse-checkout', 'add', '--', '套件 A/other', cwd=target)
        self.assertTrue((target / '套件 A/other/SKILL.md').exists())
        self.assertEqual(self.git('status', '--porcelain', cwd=target).strip(), '')

    def test_add_skips_initial_full_checkout(self):
        trace = self.lab / 'git-trace.log'
        env = dict(self.env, GIT_TRACE=str(trace))
        result = self.create(env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = trace.read_text()
        self.assertIn('worktree add --no-checkout', text)
        self.assertIn('sparse-checkout set --cone --no-sparse-index', text)
        self.assertIn('read-tree -mu', text)

    def test_invalid_scopes_have_no_resource_side_effects(self):
        for scope in ['../outside', '/absolute', './shared', 'shared//lib', 'missing', 'AGENTS.md', 'shared\nlib']:
            with self.subTest(scope=scope):
                result = self.create([scope])
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.lab / 'new').exists())
                self.assertEqual(len(self.git('worktree', 'list', '--porcelain').split('worktree ')) - 1, 1)

    def test_existing_target_and_dangling_symlink_retained(self):
        target = self.lab / 'existing'
        target.mkdir(); (target / 'sentinel').write_text('preserve')
        self.assertNotEqual(self.create(target=target).returncode, 0)
        self.assertEqual((target / 'sentinel').read_text(), 'preserve')
        link = self.lab / 'dangling'
        link.symlink_to(self.lab / 'missing-target')
        self.assertNotEqual(self.create(target=link).returncode, 0)
        self.assertTrue(link.is_symlink())
        self.assertFalse((self.lab / 'missing-target').exists())

    def test_existing_branch_is_not_reset(self):
        self.git('branch', 'verify/scoped')
        result = self.create()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git('rev-parse', 'verify/scoped').strip(), self.oid)
        self.assertFalse((self.lab / 'new').exists())

    def test_git_index_environment_override_refused(self):
        outside = self.lab / 'outside-index'
        outside.write_bytes(b'preserve')
        result = self.create(env=dict(self.env, GIT_INDEX_FILE=str(outside)))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(outside.read_bytes(), b'preserve')
        self.assertFalse((self.lab / 'new').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
