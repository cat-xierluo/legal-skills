#!/usr/bin/env python3
"""真实临时 Git 夹具；假 gh/lsof，仅核盘点、未知/错误和原现场不变。"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent
GIT = subprocess.check_output(['which', 'git'], text=True).strip()


class CleanupAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cleanup-audit-test-')
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / 'repo'; self.repo.mkdir()
        self.bin = self.root / 'bin'; self.bin.mkdir()
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                        GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.invalid',
                        GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.invalid',
                        PYTHONDONTWRITEBYTECODE='1')
        for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_NAMESPACE'):
            self.env.pop(key, None)
        self.tool('gh', '''#!/bin/sh
if [ "$1" = repo ]; then echo fixture/repo; exit 0; fi
if [ "${PR_MODE:-}" = failure ]; then exit 7; fi
if [ "${PR_MODE:-}" = truncated ]; then seq 201; exit 0; fi
if [ "${PR_MODE:-}" = open ]; then echo feat/review; fi
exit 0
''')
        self.tool('lsof', '#!/bin/sh\n[ "${CWD_MODE:-}" = failure ] && exit 1\n[ -n "${CWD_PATH:-}" ] && printf "p123\\nn%s\\n" "$CWD_PATH"\nexit 0\n')
        self.git('init', '-b', 'main')
        (self.repo / 'file.txt').write_text('base\n')
        self.git('add', 'file.txt'); self.git('commit', '-m', 'base')
        self.base = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('update-ref', 'refs/remotes/origin/main', self.base)
        self.git('branch', 'feat/review')
        self.wt = self.root / 'worker with spaces'
        self.git('worktree', 'add', str(self.wt), 'feat/review')

    def tearDown(self):
        self.tmp.cleanup()

    def tool(self, name, body):
        p = self.bin / name; p.write_text(body); p.chmod(0o700)

    def git(self, *args, repo=None):
        return subprocess.run([GIT, '-C', str(repo or self.repo), *args], env=self.env,
                              text=True, capture_output=True, check=True)

    def snapshot(self):
        # Capture Git metadata and material, not producer text labels.
        return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*')
                if p.is_file() and self.bin not in p.parents}

    def audit(self, script, **env):
        before = self.snapshot()
        result = subprocess.run(['bash', str(SCRIPTS / script), 'origin/main'], cwd=self.repo,
                                env=dict(self.env, **env), text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, self.snapshot(), 'read-only audit changed metadata/material')
        return result.stdout

    def row(self, out, value):
        return next(line for line in out.splitlines() if value in line)

    def test_normal_candidates_and_no_metadata_mutation(self):
        self.assertTrue(self.row(self.audit('worktree-audit.sh'), str(self.wt)).startswith('REMOVE_ALL'))
        self.git('branch', 'feat/old')
        self.assertTrue(self.row(self.audit('branch-audit.sh'), 'feat/old').startswith('SAFE_DELETE'))

    def test_failed_or_truncated_pr_query_preserves_both(self):
        self.git('branch', 'feat/old')
        for mode in ('failure', 'truncated'):
            self.assertTrue(self.row(self.audit('worktree-audit.sh', PR_MODE=mode), str(self.wt)).startswith('KEEP'))
            self.assertTrue(self.row(self.audit('branch-audit.sh', PR_MODE=mode), 'feat/old').startswith('KEEP'))

    def test_open_pr_is_kept(self):
        self.assertTrue(self.row(self.audit('worktree-audit.sh', PR_MODE='open'), str(self.wt)).startswith('KEEP_OPEN_PR'))
        self.git('update-ref', 'refs/remotes/origin/feat/review', self.base)
        self.assertTrue(self.row(self.audit('branch-audit.sh', PR_MODE='open'), 'feat/review').startswith('KEEP'))

    def test_unknown_cwd_and_real_occupancy_keep(self):
        self.assertTrue(self.row(self.audit('worktree-audit.sh', CWD_MODE='failure'), str(self.wt)).startswith('KEEP_UNKNOWN'))
        self.assertTrue(self.row(self.audit('worktree-audit.sh', CWD_PATH=str(self.wt / 'subdir')), str(self.wt)).startswith('KEEP_ACTIVE'))
        self.assertTrue(self.row(self.audit('worktree-audit.sh', CWD_PATH=str(self.wt)+'-other'), str(self.wt)).startswith('REMOVE_ALL'))

    def test_dirty_and_ignored_material_preserved(self):
        (self.wt / '.gitignore').write_text('private.local\n')
        (self.wt / 'private.local').write_text('synthetic private fixture\n')
        self.assertTrue(self.row(self.audit('worktree-audit.sh'), str(self.wt)).startswith('KEEP_DIRTY'))
        self.git('add', '.gitignore', repo=self.wt); self.git('commit', '-m', 'ignore', repo=self.wt)
        self.git('update-ref', 'refs/remotes/origin/main', self.git('rev-parse','HEAD',repo=self.wt).stdout.strip())
        self.assertTrue(self.row(self.audit('worktree-audit.sh'), str(self.wt)).startswith('KEEP_DIRTY'))

    def test_same_named_historical_pr_not_current_delivery(self):
        (self.wt / 'new.txt').write_text('new content\n')
        self.git('add', 'new.txt', repo=self.wt); self.git('commit', '-m', 'new task', repo=self.wt)
        oid=self.git('rev-parse','HEAD',repo=self.wt).stdout.strip()
        self.git('update-ref','refs/remotes/origin/feat/reused',oid)
        self.tool('gh', '#!/bin/sh\nif [ "$1" = repo ]; then echo fixture/repo; fi\n# No open heads; old MERGED query would report a reused branch.\ncase "$*" in *merged*) echo "feat/reused #1";; esac\nexit 0\n')
        out=self.audit('branch-audit.sh')
        self.assertTrue(self.row(out,'feat/reused').startswith('NEEDS_CONFIRM'))

    def test_fsmonitor_and_filter_helpers_not_run(self):
        marker=self.root/'helper-marker'
        helper=self.bin/'helper'; helper.write_text('#!/bin/sh\ntouch "'+str(marker)+'"\ncat\n'); helper.chmod(0o700)
        self.git('config','core.fsmonitor',str(helper))
        self.audit('worktree-audit.sh'); self.assertFalse(marker.exists())
        self.git('config','filter.fixture.clean',str(helper))
        self.assertTrue(self.row(self.audit('worktree-audit.sh'),str(self.wt)).startswith('KEEP_UNKNOWN'))
        self.assertFalse(marker.exists())

    def test_failed_git_status_is_not_clean(self):
        self.tool('git', '#!/bin/sh\ncase "$*" in *status*) exit 7;; esac\nexec "'+GIT+'" "$@"\n')
        self.assertTrue(self.row(self.audit('worktree-audit.sh'),str(self.wt)).startswith('KEEP_UNKNOWN'))

    def test_replaced_registration_with_independent_clone_is_kept(self):
        original = self.root / 'preserved-worker'
        self.wt.rename(original)
        self.git('clone', '--no-local', str(self.repo), str(self.wt))
        self.git('checkout', 'feat/review', repo=self.wt)
        self.assertEqual(self.base, self.git('rev-parse', 'HEAD', repo=self.wt).stdout.strip())
        self.assertTrue(self.row(self.audit('worktree-audit.sh'), str(self.wt)).startswith('KEEP_UNKNOWN'))

    def test_same_named_local_ref_read_error_keeps_remote(self):
        self.git('branch', 'feat/new')
        self.git('update-ref', 'refs/remotes/origin/feat/new', self.base)
        self.tool('git', '#!/bin/sh\ncase "$*" in *show-ref*) exit 7;; esac\nexec "'+GIT+'" "$@"\n')
        row = self.row(self.audit('branch-audit.sh'), 'feat/new')
        self.assertTrue(row.startswith('KEEP'), row)

    def test_no_fetch_prune_or_permission_bypass(self):
        self.tool('git', '#!/bin/sh\ncase "$*" in *fetch*|*prune*|*remove*|*update-ref*) exit 99;; esac\nexec "'+GIT+'" "$@"\n')
        out=self.audit('branch-audit.sh')+self.audit('worktree-audit.sh')
        self.assertNotIn('分支照删',out); self.assertNotIn('sudo rm',out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
