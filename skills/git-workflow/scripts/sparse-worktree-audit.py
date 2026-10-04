#!/usr/bin/env python3
"""只读盘点指定仓库的全部注册工作树；不收缩、不清理、不调用宿主。"""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys

OVERRIDES = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_NAMESPACE')


def run(args, input_bytes=None):
    return subprocess.run(args, input=input_bytes, capture_output=True, timeout=120,
                          env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})


def git(repo, *args, optional=False, input_bytes=None):
    p = run(['git', '--no-pager', '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false',
             '-c', 'core.quotePath=false', '-C', str(repo), *args], input_bytes)
    if p.returncode and not (optional and p.returncode == 1):
        raise ValueError('Git 读取失败：' + ' '.join(args))
    return p.stdout.decode('utf-8', errors='surrogateescape') if not p.returncode else ''


def registrations(repo):
    rows = []
    for block in git(repo, 'worktree', 'list', '--porcelain', '-z').split('\0\0'):
        fields = dict(s.split(' ', 1) for s in block.split('\0') if ' ' in s)
        if 'worktree' in fields:
            rows.append(fields)
    if not rows:
        raise ValueError('没有可读取的工作树登记')
    return rows


def status_count(raw):
    entries = [e for e in raw.split('\0') if e]
    i = count = 0
    while i < len(entries):
        rename = 'R' in entries[i][:2] or 'C' in entries[i][:2]
        i += 2 if rename else 1
        count += 1
    return count


def usage(path):
    if not shutil.which('du'):
        return None
    p = run(['du', '-sk', str(path)])
    if p.returncode:
        return None
    return int(p.stdout.split()[0])


def cwd_snapshot(enabled):
    if not enabled or not shutil.which('lsof'):
        return None
    p = run(['lsof', '-w', '-d', 'cwd', '-F', 'pn'])
    if p.returncode not in (0, 1) or not p.stdout:
        return None
    result = []; pid = None
    for line in p.stdout.decode(errors='replace').splitlines():
        if line.startswith('p'):
            pid = line[1:]
        elif line.startswith('n') and pid:
            result.append((pid, line[1:]))
    return result


def audit(repos, with_cwd=False):
    if any(os.environ.get(key) for key in OVERRIDES):
        raise ValueError('拒绝 Git 仓库/索引环境覆盖')
    common_seen = set(); reports = []; cwd = cwd_snapshot(with_cwd)
    for supplied in repos:
        repo = Path(supplied).expanduser().resolve(strict=True)
        common = Path(git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir').strip()).resolve()
        if common in common_seen:
            continue
        common_seen.add(common)
        rows = []
        for index, entry in enumerate(registrations(repo)):
            path = Path(entry['worktree'])
            row = {'path': str(path), 'primary': index == 0,
                   'registered_head': entry.get('HEAD'),
                   'registered_branch': entry.get('branch', 'DETACHED'), 'state': 'missing'}
            if path.exists():
                try:
                    actual_common = Path(git(path, 'rev-parse', '--path-format=absolute', '--git-common-dir').strip()).resolve()
                    if actual_common != common:
                        raise ValueError('工作树仓库身份与登记不一致')
                    actual_root = Path(git(path, 'rev-parse', '--show-toplevel').strip()).resolve()
                    if actual_root != path.absolute():
                        raise ValueError('实际工作树根目录与登记路径不一致；保留坏登记，不沿链接治理主源')
                    actual_branch = git(path, 'symbolic-ref', '-q', 'HEAD', optional=True).strip() or 'DETACHED'
                    if actual_branch != row['registered_branch']:
                        raise ValueError('实际分支/detached 身份与登记不一致')
                    row['git_dir'] = git(path, 'rev-parse', '--absolute-git-dir').strip()
                    row.update(state='valid', head=git(path, 'rev-parse', 'HEAD').strip(),
                               sparse=git(path, 'config', '--bool', 'core.sparseCheckout', optional=True).strip() == 'true')
                    row['head_matches_registration'] = row['head'] == row['registered_head']
                    row['physical_kib'] = usage(path)
                    row['scopes'] = git(path, 'sparse-checkout', 'list').splitlines() if row['sparse'] else []
                    # status may execute clean/process filters while comparing bytes.
                    # Detect keys only; do not print commands or alter filter semantics.
                    tracked_raw = git(path, 'ls-files', '-z')
                    tracked = [f for f in tracked_raw.split('\0') if f]
                    filter_keys = git(path, 'config', '--name-only', '--get-regexp', r'^filter\..*\.(clean|process)$', optional=True)
                    drivers = {key[len('filter.'):].rsplit('.', 1)[0] for key in filter_keys.splitlines()}
                    active_filter = False
                    if drivers and tracked:
                        attrs = git(path, 'check-attr', '-z', '--stdin', 'filter', input_bytes=tracked_raw.encode('utf-8', errors='surrogateescape')).split('\0')
                        active_filter = any(attrs[i] in drivers for i in range(2, len(attrs), 3))
                    row['material_scan'] = 'NOT_VERIFIED_EXTERNAL_FILTER' if active_filter else 'status-observed'
                    row['dirty_count'] = None if active_filter else status_count(git(path, 'status', '--porcelain=v1', '-z', '--untracked-files=all'))
                    for name, flags in [('untracked', ['--others', '--exclude-standard']),
                                        ('ignored', ['--others', '--ignored', '--exclude-standard'])]:
                        row[name + '_count'] = len([f for f in git(path, 'ls-files', *flags, '-z').split('\0') if f])
                    # Names and counts only; never read ignored/configuration contents.
                    row['skill_directories'] = sorted({str(PurePosixPath(f).parent) for f in tracked
                                                       if f == 'SKILL.md' or f.endswith('/SKILL.md')})
                    row['cwd_pids'] = None if cwd is None else sorted({pid for pid, directory in cwd
                                          if directory == str(path) or directory.startswith(str(path) + '/')})
                    row['assessment'] = ('primary-preserved' if row['primary'] else 'already-sparse' if row['sparse']
                                         else 'full-needs-task-dependencies-and-material-preflight')
                except (ValueError, OSError, subprocess.TimeoutExpired) as e:
                    row.update(state='unreadable', error=str(e))
            rows.append(row)
        reports.append({'repo': str(repo), 'common_dir': str(common), 'worktrees': rows})
    return {'schema_version': 1, 'mode': 'read-only', 'repositories': reports,
            'limitations': ['注册清单快照不覆盖未登记目录或其他机器',
                            'cwd 无命中不证明无写入者；宿主 owner/Session/终端须另核',
                            'du 为目录占用，不是可回收量；缓存与任务材料须单独分类',
                            '本入口不推断目标、不授权收缩、不执行修改或清理']}


def save_private(report, filename):
    requested = Path(filename).expanduser()
    if requested.exists() or requested.is_symlink():
        raise ValueError('证据目标已存在，拒绝覆盖')
    target = requested.resolve()
    protected = [Path(r['common_dir']).resolve() for r in report['repositories']]
    protected += [Path(w['path']).resolve() for r in report['repositories'] for w in r['worktrees']]
    if any(target == root or root in target.parents for root in protected):
        raise ValueError('私有证据必须写在所有登记工作树与 Git 管理目录之外')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps(report, ensure_ascii=True, indent=2) + '\n'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', action='append', required=True, help='仓库或其已有工作树，可重复；按 common-dir 去重')
    parser.add_argument('--output', help='仓库外的新私有 JSON 证据文件；拒绝覆盖')
    parser.add_argument('--with-cwd', action='store_true', help='若有 lsof，另做本机 cwd 观察；不能据此断言无 writer')
    args = parser.parse_args()
    report = audit(args.repo, args.with_cwd)
    if args.output:
        save_private(report, args.output)
    summary = []
    for repo in report['repositories']:
        valid = [w for w in repo['worktrees'] if not w['primary'] and w['state'] == 'valid']
        full = [w for w in valid if not w['sparse']]
        summary.append({'repo': repo['repo'], 'registered': len(repo['worktrees']),
                        'valid_secondary': len(valid), 'full_secondary': len(full),
                        'full_physical_kib': sum(w['physical_kib'] or 0 for w in full),
                        'size_not_verified': sum(w['physical_kib'] is None for w in full),
                        'dirty_not_verified': sum(w['dirty_count'] is None for w in valid),
                        'unreadable_or_missing': sum(w['state'] != 'valid' for w in repo['worktrees'])})
    print(json.dumps({'mode': 'read-only', 'summary': summary, 'detailed_evidence_written': bool(args.output)}, ensure_ascii=True))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
