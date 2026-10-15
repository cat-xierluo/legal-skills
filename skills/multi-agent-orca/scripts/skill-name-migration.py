#!/usr/bin/env python3
"""Plan, install, verify or roll back new-name links; preserve old runtime links."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import uuid

OLD = 'multi-agent-orchestration'
NEW = 'multi-agent-orca'
SCHEMA = 'multi-agent-orca.name-migration.v1'


def snapshot(path):
    try:
        s = path.lstat()
    except FileNotFoundError:
        return None
    result = {'device': s.st_dev, 'inode': s.st_ino, 'mode': s.st_mode}
    if stat.S_ISLNK(s.st_mode):
        result['target'] = os.readlink(path)
    return result


def parent_state(path):
    parent = path.parent.resolve(strict=True)
    s = parent.stat()
    return {'resolved': str(parent), 'device': s.st_dev, 'inode': s.st_ino}


def source_state(path):
    path = path.resolve(strict=True)
    data = (path / 'SKILL.md').read_bytes()
    if b'name: multi-agent-orca\n' not in data:
        raise ValueError('source is not the new-name Skill')
    digest = hashlib.sha256(data)
    public = []
    for directory in ['scripts', 'references', 'templates']:
        public.extend(p for p in (path / directory).rglob('*')
                      if '__pycache__' not in p.parts and p.suffix != '.pyc'
                      and (p.is_file() or p.is_symlink()))
    public.extend((path / 'config').glob('*.example.*'))
    policy = path / 'config/harness-backend-policy.json'
    if policy.exists():
        public.append(policy)
    for item in sorted(public):
        digest.update(str(item.relative_to(path)).encode() + b'\0')
        digest.update(os.readlink(item).encode() if item.is_symlink() else item.read_bytes())
    return {'path': str(path), 'skill_sha256': hashlib.sha256(data).hexdigest(),
            'public_runtime_sha256': digest.hexdigest()}


def save(path, data):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def plan(args):
    manifest = Path(args.manifest).absolute()
    if os.path.lexists(manifest):
        raise ValueError('manifest already exists; continue the original operation')
    source = source_state(Path(args.source))
    entries, seen = [], {}
    for value in args.old_link:
        original = Path(value).absolute()
        if original.name != OLD or not original.is_symlink():
            raise ValueError('old installation must be an exact old-name symlink')
        old = original.parent.resolve(strict=True) / original.name
        if str(old) in seen:
            seen[str(old)]['aliases'].append(str(original))
            continue  # Parent aliases reference a single real link object.
        old.resolve(strict=True)
        new = old.with_name(NEW)
        if os.path.lexists(new):
            raise ValueError('new-name path already exists; no overwrite permitted')
        entry = {'old': str(old), 'old_before': snapshot(old),
                 'new': str(new), 'parent': parent_state(old),
                 'aliases': [str(original)], 'status': 'planned'}
        entries.append(entry)
        seen[str(old)] = entry
    if not entries:
        raise ValueError('no installation links selected')
    data = {'schema': SCHEMA, 'owner': args.owner, 'operation': uuid.uuid4().hex,
            'source': source, 'entries': entries, 'state': 'planned'}
    manifest.parent.mkdir(parents=True, exist_ok=True)
    # Initial publication must not replace a concurrent manifest.
    fd = os.open(manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return data


def validate(data):
    if data.get('schema') != SCHEMA or not data.get('owner'):
        raise ValueError('invalid manifest schema/owner')
    if source_state(Path(data['source']['path'])) != data['source']:
        raise ValueError('source changed since planning')
    seen = set()
    for e in data['entries']:
        old, new = Path(e['old']), Path(e['new'])
        if (old.name != OLD or new != old.with_name(NEW) or not old.is_absolute()
                or str(old) in seen):
            raise ValueError('invalid or repeated installation path')
        seen.add(str(old))
        if (any(parent_state(Path(alias)) != e['parent'] for alias in e['aliases'])
                or parent_state(old) != e['parent'] or snapshot(old) != e['old_before']):
            raise ValueError('old link or parent drift; original links preserved')
        if (old.resolve(strict=True) / 'SKILL.md').exists():
            raise ValueError('old runtime still exposes SKILL.md; refuse duplicate discovery')
        current = snapshot(new)
        owned = e.get('installed') or e.get('staged')
        if current is not None and current != owned:
            raise ValueError('new path conflict/drift; refuse overwrite')
        if current and current.get('target') != data['source']['path']:
            raise ValueError('new target mismatch')
        if e.get('stage_path'):
            expected = new.parent / ('.' + NEW + '.' + data['operation'])
            if Path(e['stage_path']) != expected:
                raise ValueError('invalid staging path')
            stage = snapshot(expected)
            if stage is not None:
                if e.get('staged') is not None and stage != e['staged']:
                    raise ValueError('staging object drift')
                if (not stat.S_ISLNK(stage['mode'])
                        or stage.get('target') != data['source']['path']):
                    raise ValueError('unexpected staging object')


def retire_owned(target, expected, data, manifest):
    """Capture atomically before deletion; never unlink an unverified path winner."""
    private = Path(tempfile.mkdtemp(prefix='.' + NEW + '.retire-', dir=target.parent))
    captured = private / 'object'
    entry = {'original': str(target), 'quarantine': str(captured),
             'expected': expected, 'state': 'intent'}
    data.setdefault('retirements', []).append(entry)
    try:
        save(manifest, data)
    except OSError:
        private.rmdir()  # Only our still-empty private directory; no captured object exists.
        raise
    os.rename(target, captured)
    if snapshot(captured) != expected:
        entry['state'] = 'foreign_preserved'
        try:
            os.link(captured, target, follow_symlinks=False)
            entry['restored_without_overwrite'] = True
        except FileExistsError:
            entry['restored_without_overwrite'] = False
        save(manifest, data)
        raise ValueError('concurrent foreign object preserved at ' + str(captured))
    entry['state'] = 'captured'
    save(manifest, data)
    captured.unlink()  # Inside our private quarantine, after inode/target validation.
    private.rmdir()
    entry['state'] = 'removed'
    save(manifest, data)


def finish_retirements(data, manifest):
    for entry in data.get('retirements', []):
        if entry['state'] == 'foreign_preserved':
            raise ValueError('foreign object requires reconciliation: ' + entry['quarantine'])
        if entry['state'] in ['intent', 'captured']:
            captured = Path(entry['quarantine'])
            current = snapshot(captured)
            if current is not None:
                if current != entry['expected']:
                    raise ValueError('quarantined object drift; preserve for reconciliation')
                captured.unlink()
            # An intent saved before rename may still have an original object: leave it for normal rollback.
            if captured.parent.is_dir():
                captured.parent.rmdir()
            entry['state'] = 'removed'
            save(manifest, data)


@contextlib.contextmanager
def locked(path):
    lock = path.with_name(path.name + '.lock')
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        lock.unlink()


def operate(args):
    path = Path(args.manifest).absolute()
    if path.is_symlink():
        raise ValueError('manifest must be a private regular file')
    with locked(path):
        data = json.loads(path.read_text())
        validate(data)  # Validate the entire batch before the first installation write.
        if args.action != 'verify':
            finish_retirements(data, path)
        if args.action == 'verify':
            if data['state'] != 'applied' or any(snapshot(Path(e['new'])) != e.get('installed')
                                                  for e in data['entries']):
                raise ValueError('installation incomplete')
            return data
        if args.action == 'apply':
            if data['state'] == 'rolled_back':
                raise ValueError('rolled-back operation requires a new plan')
            for e in data['entries']:
                validate(data)
                new = Path(e['new'])
                if snapshot(new) is None:
                    if 'stage_path' not in e:
                        stage = new.parent / ('.' + NEW + '.' + data['operation'])
                        e.update(stage_path=str(stage), status='staging_intent')
                        save(path, data)
                    stage = Path(e['stage_path'])
                    if e.get('staged') is None:
                        if snapshot(stage) is None:
                            os.symlink(data['source']['path'], stage)
                        validate(data)
                        e.update(staged=snapshot(stage), status='staged')
                        save(path, data)
                    stage = Path(e['stage_path'])
                    if snapshot(stage) != e['staged']:
                        raise ValueError('staging object missing/drift')
                    # An exclusive hard link to our recorded symlink inode: never replaces a race winner.
                    os.link(stage, new, follow_symlinks=False)
                e.update(installed=snapshot(new), status='installed')
                if e['installed'] != e['staged']:
                    raise ValueError('installed link is not the owned staging object')
                save(path, data)
                stage = Path(e['stage_path'])
                if snapshot(stage) == e['staged']:
                    retire_owned(stage, e['staged'], data, path)
            data['state'] = 'applied'
        else:
            for e in reversed(data['entries']):
                validate(data)
                new = Path(e['new'])
                if snapshot(new) is not None:
                    retire_owned(new, e.get('installed') or e['staged'], data, path)
                stage = Path(e['stage_path']) if e.get('stage_path') else None
                if stage and snapshot(stage) is not None:
                    # A durable operation-specific intent plus exact target binds a pre-journal crash.
                    e.setdefault('staged', snapshot(stage))
                    save(path, data)
                    if snapshot(stage) != e['staged']:
                        raise ValueError('staging object drift during rollback')
                    retire_owned(stage, e['staged'], data, path)
                e['status'] = 'rolled_back'
                save(path, data)
            data['state'] = 'rolled_back'
        save(path, data)
        return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'apply', 'verify', 'rollback'])
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--source')
    parser.add_argument('--old-link', action='append')
    parser.add_argument('--owner')
    args = parser.parse_args()
    if args.action == 'plan' and not (args.source and args.old_link and args.owner):
        parser.error('plan requires --source, --old-link and --owner')
    try:
        data = plan(args) if args.action == 'plan' else operate(args)
        print(json.dumps({'state': data['state'], 'entries': len(data['entries']),
                          'owner': data['owner']}, ensure_ascii=False))
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print('MIGRATION_REFUSED: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
