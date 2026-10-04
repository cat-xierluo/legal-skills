#!/usr/bin/env python3
"""Inject alternate exit codes while preserving real history findings."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class ExitSignalTests(unittest.TestCase):
    def run_fixture(self, injected):
        with tempfile.TemporaryDirectory(prefix='identity-exit-') as name:
            root = Path(name)
            suite = root / 'test-identity-audit.sh'
            suite.write_bytes((HERE / suite.name).read_bytes())
            counter = root / 'counter'
            real = shlex.quote(str(HERE / 'identity-audit.sh'))
            wrapper = root / 'identity-audit.sh'
            wrapper.write_text(f"""#!/bin/bash
{real} "$@"
rc=$?
if [ "$#" -eq 3 ] && [ "$1" = history ] && [ "$2" = --repo ]; then
  count=0
  [ ! -f {shlex.quote(str(counter))} ] || read -r count < {shlex.quote(str(counter))}
  count=$((count + 1))
  printf '%s\\n' "$count" > {shlex.quote(str(counter))}
  if [ "$count" -eq 2 ]; then exit {injected}; fi
fi
exit "$rc"
""")
            wrapper.chmod(0o700)
            env = dict(os.environ)
            for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_NAMESPACE',
                        'GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL', 'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL'):
                env.pop(key, None)
            return subprocess.run(['bash', str(suite)], capture_output=True, text=True, env=env)

    def test_actual_findings_exit_one_passes(self):
        result = self.run_fixture(1)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_identical_findings_with_success_or_error_exit_are_rejected(self):
        for code in (0, 2, 99):
            with self.subTest(code=code):
                result = self.run_fixture(code)
                self.assertNotEqual(0, result.returncode)
                self.assertIn('FAIL: history: 尾注与作者均被标注', result.stderr)
                self.assertIn('expected exit 1, got '+str(code), result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
