#!/usr/bin/env python3
"""Exercise filesystem outcomes and failure boundaries of the rename installer."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('skill-name-migration.py')


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='orca name ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / 'source' / 'multi-agent-orca'
        self.source.mkdir(parents=True)
        (self.source / 'SKILL.md').write_text('---\nname: multi-agent-orca\n---\n')
        self.legacy = self.root / 'legacy'
        self.legacy.mkdir()
        (self.legacy / 'script.py').write_text('print("frozen")\n')
        self.install = self.root / 'skills'
        self.install.mkdir()
        self.old = self.install / 'multi-agent-orchestration'
        self.old.symlink_to(self.legacy)
        self.manifest = self.root / 'private.json'
        self.old_stat = self.old.lstat()

    def cli(self, action, ok=True, extra=()):
        args = [sys.executable, str(SCRIPT), action, '--manifest', str(self.manifest)]
        if action == 'plan':
            args += ['--source', str(self.source), '--old-link', str(self.old), '--owner', 'test']
        r = subprocess.run(args + list(extra), capture_output=True, text=True)
        self.assertEqual(r.returncode == 0, ok, r.stdout + r.stderr)
        return r

    @property
    def new(self):
        return self.install / 'multi-agent-orca'

    def test_apply_verify_idempotent_rollback_preserves_old_runtime(self):
        self.cli('plan'); self.assertFalse(self.new.exists())
        self.cli('apply'); self.cli('verify')
        self.assertEqual(self.new.resolve(), self.source)
        inode = self.new.lstat().st_ino
        self.cli('apply'); self.assertEqual(self.new.lstat().st_ino, inode)
        self.cli('rollback'); self.assertFalse(os.path.lexists(self.new))
        self.cli('rollback'); self.assertEqual(self.old.lstat(), self.old_stat)
        self.assertEqual((self.legacy / 'script.py').read_text(), 'print("frozen")\n')
        self.cli('verify', False)

    def test_relative_old_target_and_spaces(self):
        self.old.unlink(); self.old.symlink_to('../legacy')
        self.cli('plan'); self.cli('apply'); self.cli('verify')
        self.assertEqual(os.readlink(self.old), '../legacy')

    def test_parent_alias_deduplicated(self):
        alias = self.root / 'alias'; alias.symlink_to(self.install, target_is_directory=True)
        self.cli('plan', extra=['--old-link', str(alias / self.old.name)])
        self.assertEqual(len(json.loads(self.manifest.read_text())['entries']), 1)
        self.cli('apply'); self.assertEqual((alias / self.new.name).resolve(), self.source)

    def test_existing_entity_is_not_overwritten(self):
        self.new.mkdir(); (self.new / 'keep').write_text('user')
        self.cli('plan', False); self.assertEqual((self.new / 'keep').read_text(), 'user')

    def test_dangling_new_link_is_conflict(self):
        self.new.symlink_to(self.root / 'missing'); self.cli('plan', False)
        self.assertEqual(os.readlink(self.new), str(self.root / 'missing'))

    def test_dangling_old_refused(self):
        self.old.unlink(); self.old.symlink_to(self.root / 'missing'); self.cli('plan', False)

    def test_loop_refused(self):
        self.old.unlink(); self.old.symlink_to(self.old.name); self.cli('plan', False)

    def test_static_old_copy_not_modified(self):
        self.old.unlink(); self.old.mkdir(); (self.old / 'local').write_text('private')
        self.cli('plan', False); self.assertEqual((self.old / 'local').read_text(), 'private')

    def test_source_drift_blocks_apply(self):
        self.cli('plan'); (self.source / 'SKILL.md').write_text('name: multi-agent-orca\nchanged')
        self.cli('apply', False); self.assertFalse(self.new.exists())

    def test_old_target_drift_blocks_apply(self):
        self.cli('plan'); self.old.unlink(); self.old.symlink_to(self.root)
        self.cli('apply', False); self.assertFalse(self.new.exists())

    def test_existing_new_name_race_winner_preserved(self):
        self.cli('plan'); self.new.write_text('concurrent user')
        self.cli('apply', False); self.assertEqual(self.new.read_text(), 'concurrent user')

    def test_rollback_never_removes_replaced_new_link(self):
        self.cli('plan'); self.cli('apply'); self.new.unlink(); self.new.symlink_to(self.root)
        self.cli('rollback', False); self.assertEqual(self.new.resolve(), self.root)

    def test_no_two_discoverable_skills(self):
        (self.legacy / 'SKILL.md').write_text('name: multi-agent-orchestration\n')
        self.cli('plan'); self.cli('apply', False); self.assertFalse(self.new.exists())
        (self.legacy / 'SKILL.md').unlink(); self.cli('apply')
        discovered = [p.name for p in self.install.iterdir() if (p / 'SKILL.md').is_file()]
        self.assertEqual(discovered, ['multi-agent-orca'])

    def test_exclusive_manifest_and_permission(self):
        self.cli('plan'); original = self.manifest.read_bytes(); self.cli('plan', False)
        self.assertEqual(self.manifest.read_bytes(), original)
        self.assertEqual(self.manifest.stat().st_mode & 0o777, 0o600)

    def test_foreign_operation_lock_preserved(self):
        self.cli('plan'); lock = Path(str(self.manifest) + '.lock'); lock.write_text('foreign')
        self.cli('apply', False); self.assertEqual(lock.read_text(), 'foreign')

    def test_batch_validates_all_before_write(self):
        parent = self.root / 'other'; parent.mkdir(); other = parent / self.old.name
        other.symlink_to(self.legacy)
        self.cli('plan', extra=['--old-link', str(other)])
        other.unlink(); other.symlink_to(self.root)
        self.cli('apply', False); self.assertFalse(self.new.exists())

    def test_rollback_race_preserves_foreign_file(self):
        self.cli('plan'); self.cli('apply')
        spec = importlib.util.spec_from_file_location('migration_race', SCRIPT)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        original = module.os.rename
        def replace_before_capture(src, dst):
            if Path(src) == self.new:
                self.new.unlink(); self.new.write_text('foreign concurrent file')
            return original(src, dst)
        module.os.rename = replace_before_capture
        try:
            args = type('Args', (), {'manifest': str(self.manifest), 'action': 'rollback'})()
            with self.assertRaises(ValueError): module.operate(args)
        finally:
            module.os.rename = original
        self.assertEqual(self.new.read_text(), 'foreign concurrent file')
        data = json.loads(self.manifest.read_text())
        retained = [r for r in data['retirements'] if r['state'] == 'foreign_preserved']
        self.assertEqual(len(retained), 1)
        self.assertEqual(Path(retained[0]['quarantine']).read_text(), 'foreign concurrent file')
        self.cli('rollback', False)
        self.assertEqual(self.new.read_text(), 'foreign concurrent file')

    def test_runtime_source_drift_blocks_apply(self):
        scripts = self.source / 'scripts'; scripts.mkdir(); helper = scripts / 'helper.py'
        helper.write_text('original')
        self.cli('plan'); helper.write_text('changed')
        self.cli('apply', False); self.assertFalse(self.new.exists())

    def test_parent_alias_drift_is_refused(self):
        alias = self.root / 'alias'; alias.symlink_to(self.install, target_is_directory=True)
        self.cli('plan', extra=['--old-link', str(alias / self.old.name)])
        other = self.root / 'other'; other.mkdir(); (other / self.old.name).symlink_to(self.legacy)
        alias.unlink(); alias.symlink_to(other, target_is_directory=True)
        self.cli('apply', False); self.assertFalse(self.new.exists())

    def test_crash_after_stage_creation_recovers_or_rolls_back(self):
        for recovery in ['apply', 'rollback']:
            with self.subTest(recovery=recovery):
                self.manifest.unlink(missing_ok=True)
                self.cli('plan')
                spec = importlib.util.spec_from_file_location('migration_crash', SCRIPT)
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                original = module.save
                calls = 0
                def interrupt_stage_journal(*a, **kw):
                    nonlocal calls
                    calls += 1
                    if calls == 2: raise OSError('crash after stage creation')
                    return original(*a, **kw)
                module.save = interrupt_stage_journal
                args = type('Args', (), {'manifest': str(self.manifest), 'action': 'apply'})()
                with self.assertRaises(OSError): module.operate(args)
                self.cli(recovery)
                if recovery == 'apply': self.cli('verify'); self.cli('rollback')
                self.assertFalse(self.new.exists())
                self.assertFalse(list(self.install.glob('.multi-agent-orca.*')))

    def test_partial_failure_resumes_recorded_installation(self):
        spec = importlib.util.spec_from_file_location('migration', SCRIPT)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.cli('plan')
        original = module.os.link
        def install_then_interrupt(*a, **kw):
            original(*a, **kw)
            raise OSError('simulated interruption after exclusive installation')
        module.os.link = install_then_interrupt
        try:
            args = type('Args', (), {'manifest': str(self.manifest), 'action': 'apply'})()
            with self.assertRaises(OSError): module.operate(args)
        finally:
            module.os.link = original
        inode = self.new.lstat().st_ino
        self.cli('apply'); self.cli('verify'); self.assertEqual(self.new.lstat().st_ino, inode)
        self.cli('rollback'); self.assertFalse(self.new.exists())


if __name__ == '__main__':
    unittest.main()
