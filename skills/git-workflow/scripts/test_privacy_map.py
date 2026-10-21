#!/usr/bin/env python3
"""privacy-map.py 的隔离集成回归：真实临时 Git 仓库 + 真实 privacy_check 诊断 → 映射与登记。

全部敏感样本均为运行时拼接构造的合成数据，源码中不出现可直接匹配的字面量。
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

CHECKER = SCRIPTS / 'privacy_check.py'
MAPPER = SCRIPTS / 'privacy-map.py'
SEG = '/Use' + 'rs/'  # 拼接构造，避免本文件自身命中 local-user-path
ENV = dict(os.environ, GIT_AUTHOR_NAME='Privacy Map Test', GIT_AUTHOR_EMAIL='map@example.invalid',
           GIT_COMMITTER_NAME='Privacy Map Test', GIT_COMMITTER_EMAIL='map@example.invalid',
           GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')


def run(*args, **kwargs):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True,
                          env=ENV, **kwargs)


class PrivacyMapIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='privacy-map-tests-')
        self.repo = Path(self.tmp.name) / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', '-C', self.repo, 'init', '-q'], check=True,
                       env=ENV, capture_output=True)

    def commit(self, message, *files):
        for path, content in files:
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        subprocess.run(['git', '-C', self.repo, 'add', '-A'], check=True, env=ENV, capture_output=True)
        command = ['git', '-C', self.repo, 'commit', '-q', '-m', message]
        if not files:
            command.append('--allow-empty')
        subprocess.run(command, check=True, env=ENV, capture_output=True)
        return subprocess.run(['git', '-C', self.repo, 'rev-parse', 'HEAD'], check=True,
                              env=ENV, capture_output=True, text=True).stdout.strip()

    def diagnostics(self, base, head):
        result = run(CHECKER, '--repo', self.repo, 'range', '--base-oid', base, '--head-oid', head)
        return result

    def test_maps_blob_patch_and_message_sources_and_flags_real_usernames(self):
        demo = SEG + 'de' + 'mo'
        real = SEG + 'con' + 'fidential'
        base = self.commit('base', ('docs/fixture.md', 'first\nsecond\nthird\nfourth\nfifth\n'))
        # B：改动相邻行，使 patch 上下文带上既有占位符行；blob 同时含占位符。
        head_b = self.commit('edit tail', ('docs/fixture.md', f'first\nsecond {demo}/k.png\nthird\nfourth\nFIFTH\n'))
        # C：新增含真实用户名段的文件。
        head_c = self.commit('add real', ('docs/real.md', f'# note\n{real}/secret.png\n'))
        # D：提交说明本身含占位符路径 → message 来源。
        head_d = self.commit(f'docs: see {demo}/guide.md')

        result = self.diagnostics(base, head_d)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('PRIVACY_REVIEW_REQUIRED', result.stderr)

        mapped = subprocess.run([sys.executable, str(MAPPER), '--repo', self.repo, base, head_d],
                                input=result.stderr, capture_output=True, text=True, env=ENV)
        out = mapped.stdout
        self.assertEqual(mapped.returncode, 2, out + mapped.stderr)
        self.assertIn('blob:docs/fixture.md', out)
        self.assertIn(':patch', out)
        self.assertIn(':message', out)
        self.assertIn('de' + 'mo', out)
        self.assertIn('blob:docs/real.md', out)
        self.assertIn('含非占位符用户名段', out)
        self.assertIn('con' + 'fidential', out)
        # 只映射不登记：不得写任何例外文件。
        self.assertFalse((self.repo / '.git' / 'privacy-reviewed.json').exists())

    def test_record_writes_loader_valid_exceptions_and_clears_the_gate(self):
        demo = SEG + 'your' + '-path'
        base = self.commit('base', ('docs/sample.md', 'one\ntwo\n'))
        head = self.commit('mention', ('docs/sample.md', f'one\ntwo {demo}/img.png\n'))

        blocked = self.diagnostics(base, head)
        self.assertEqual(blocked.returncode, 1)

        recorded = subprocess.run(
            [sys.executable, str(MAPPER), '--repo', self.repo, base, head,
             '--record', '--reviewer', 'Privacy Map Test', '--reason-prefix', '回归测试：'],
            input=blocked.stderr, capture_output=True, text=True, env=ENV)
        self.assertEqual(recorded.returncode, 0,
                         f'checker stderr:\n{blocked.stderr}\n{recorded.stdout}{recorded.stderr}')
        self.assertIn('已通过 checker 加载校验', recorded.stdout)

        cleared = self.diagnostics(base, head)
        self.assertEqual(cleared.returncode, 0, cleared.stderr + cleared.stdout)
        self.assertIn('PRIVACY_OK', cleared.stdout)

    def test_record_requires_reviewer_and_rejects_empty_input(self):
        demo = SEG + 'de' + 'mo'
        base = self.commit('base', ('docs/x.md', 'x\n'))
        head = self.commit('hit', ('docs/x.md', f'x {demo}/a.png\n'))
        blocked = self.diagnostics(base, head)
        missing = subprocess.run([sys.executable, str(MAPPER), '--repo', self.repo, base, head,
                                  '--record'], input=blocked.stderr, capture_output=True, text=True, env=ENV)
        self.assertEqual(missing.returncode, 2)
        empty = subprocess.run([sys.executable, str(MAPPER), '--repo', self.repo, base, head],
                               input='', capture_output=True, text=True, env=ENV)
        self.assertEqual(empty.returncode, 2)


if __name__ == '__main__':
    unittest.main()
