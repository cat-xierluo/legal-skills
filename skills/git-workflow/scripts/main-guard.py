#!/usr/bin/env python3
"""macOS 主目录分支保护：文件可编辑，主目录 Git 写操作转 worktree。"""
import argparse
import datetime
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import uuid


class GuardError(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise GuardError(message)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(repo, *args, check=True):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', LC_ALL='C')
    p = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', str(repo), *args],
                       env=env, capture_output=True, text=True)
    if check:
        require(p.returncode == 0, 'Git 查询失败：' + p.stderr.strip())
    return p


def external(p, repo):
    p = Path(p).expanduser().absolute()
    require(not p.is_symlink(), '证据不能为符号链接')
    p = p.resolve()
    require(not p.is_relative_to(repo) and '.git' not in p.parts,
            '清单必须放在仓库及 Git 元数据外')
    require(p.parent.is_dir(), '先建立外部证据目录')
    return p


def save(p, data, new=False):
    with p.open('x' if new else 'w', encoding='utf-8') as f:
        os.chmod(p, 0o600)
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def layout(repo):
    require(platform.system() == 'Darwin' and hasattr(os, 'chflags'),
            '仅支持 macOS uchg；其他平台 NOT_VERIFIED，未修改权限')
    require(not any(os.environ.get(k) for k in ('GIT_DIR', 'GIT_COMMON_DIR', 'GIT_WORK_TREE',
                    'GIT_INDEX_FILE', 'GIT_NAMESPACE', 'GIT_CONFIG_COUNT', 'GIT_CONFIG_PARAMETERS')),
            '拒绝 Git 环境覆盖')
    repo = Path(repo).expanduser().resolve(strict=True)
    gd = repo / '.git'
    require(gd.is_dir() and not gd.is_symlink(), '只接受主工作树的真实 .git 目录')
    require(Path(git(repo, 'rev-parse', '--show-toplevel').stdout.strip()).resolve() == repo,
            '仓库根身份不符')
    common = Path(git(repo, 'rev-parse', '--git-common-dir').stdout.strip())
    require((common if common.is_absolute() else repo / common).resolve() == gd, 'common-dir 不符')
    require(git(repo, 'symbolic-ref', 'HEAD').stdout.strip() == 'refs/heads/main',
            '主目录不在 main；本工具不会切分支')
    for n in ('HEAD', 'index', 'refs/heads/main'):
        require((gd / n).is_file() and not (gd / n).is_symlink(), '需真实 loose 文件：.git/' + n)
    return repo


def identity(repo, head):
    require(len(head) == 40 and all(c in '0123456789abcdef' for c in head), '必须提供完整 HEAD SHA')
    require(git(repo, 'rev-parse', 'HEAD').stdout.strip() == head, 'HEAD 已漂移')
    require(git(repo, 'symbolic-ref', 'HEAD').stdout.strip() == 'refs/heads/main', 'main 身份已漂移')


def row(repo, name):
    p = repo / '.git' / name
    s = p.lstat()
    require(stat.S_ISREG(s.st_mode), '元数据不是普通文件：' + name)
    return dict(name=name, flags=s.st_flags, inode=s.st_ino, device=s.st_dev, sha256=digest(p))


def unchanged(repo, rows, locked=False):
    for a in rows:
        b = row(repo, a['name'])
        require(all(a[k] == b[k] for k in ('inode', 'device', 'sha256')), '元数据已漂移：' + a['name'])
        if locked:
            require(b['flags'] & stat.UF_IMMUTABLE, '缺少 uchg：' + a['name'])


def install(a):
    require(getattr(a, 'allow_index_blocking', False),
            '四元数据锁会阻断主目录 add/commit；当前默认不安装。仅明确接受此限制时使用 --allow-index-blocking')
    repo = layout(a.repo)
    state = external(a.state, repo)
    require(not state.exists(), '旧清单不能覆盖；使用新维护窗口清单')
    identity(repo, a.expected_head)
    require(len(a.base) == 40, 'base 必须为固定 SHA')
    require(git(repo, 'rev-parse', 'refs/remotes/origin/main').stdout.strip() == a.base,
            'base 与已核 origin/main 不符；本工具不 fetch')
    require(git(repo, 'merge-base', '--is-ancestor', a.base, a.expected_head, check=False).returncode == 0,
            'main 漏掉固定远端基线；先对账')
    h = json.loads(external(a.handoff, repo).read_text())
    require(h.get('state') == 'SAFE_STOPPED' and h.get('head') == a.expected_head and h.get('owner'),
            '缺少绑定 HEAD 的具名 Git 停写回执')
    require(h.get('unknown_git_writers') is False and h.get('owners') and
            all(x.get('name') and x.get('state') == 'SAFE_STOPPED' for x in h['owners']),
            'Git/index owner 回执未齐')
    gd = repo / '.git'
    require(not any((gd / n).exists() for n in ('index.lock', 'HEAD.lock', 'refs/heads/main.lock')),
            '存在主目录 Git 锁，先核 owner，不能删除')
    rows = [row(repo, n) for n in ('HEAD', 'index', 'refs/heads/main')]
    lock = gd / 'index.lock'
    doc = dict(version=1, mode='BRANCH_ONLY', state='INSTALLING', repo=str(repo),
               head=a.expected_head, base=a.base, owner=h['owner'], paths=rows, created_at=now())
    save(state, doc, new=True)
    added = []
    created = False
    try:
        # O_EXCL 与真实 Git index writer 竞争；先占锁，确保 switch 在改动文件前拒绝。
        save(lock, dict(purpose='main-branch-guard', owner=h['owner'], head=a.expected_head,
                        state_file=str(state), instruction='Intentional guard; not a stale lock.'), new=True)
        created = True
        unchanged(repo, rows)
        identity(repo, a.expected_head)
        rows.append(row(repo, 'index.lock'))
        doc['paths'] = rows
        save(state, doc)
        for r in reversed(rows):
            if not r['flags'] & stat.UF_IMMUTABLE:
                p = gd / r['name']
                unchanged(repo, [r])
                os.chflags(p, p.lstat().st_flags | stat.UF_IMMUTABLE, follow_symlinks=False)
                added.append(r)
        unchanged(repo, rows, locked=True)
        identity(repo, a.expected_head)
        doc.update(state='INSTALLED', installed_at=now())
    except BaseException:
        errors = []
        for r in reversed(added):
            try:
                unchanged(repo, [r])
                p = gd / r['name']
                os.chflags(p, p.lstat().st_flags & ~stat.UF_IMMUTABLE, follow_symlinks=False)
            except Exception as e:
                errors.append(str(e))
        if created and not errors:
            lock.unlink()
        doc.update(state='INSTALL_FAILED', rollback_errors=errors)
        save(state, doc)
        raise
    save(state, doc)
    return dict(state='INSTALLED', mode='BRANCH_ONLY', head=doc['head'], protected_metadata=4,
                primary_files='可正常编辑', primary_git_writes='转独立 worktree')


def load(a):
    state = Path(a.state).expanduser().resolve(strict=True)
    doc = json.loads(state.read_text())
    repo = layout(doc['repo'])
    external(state, repo)
    require(doc['version'] == 1 and doc['mode'] == 'BRANCH_ONLY' and doc['state'] == 'INSTALLED',
            '非已安装分支保护清单')
    require([x['name'] for x in doc['paths']] == ['HEAD', 'index', 'refs/heads/main', 'index.lock'],
            '保护清单范围不符')
    identity(repo, doc['head'])
    unchanged(repo, doc['paths'], locked=True)
    return state, doc, repo


def verify(a):
    _, doc, repo = load(a)
    probes = []
    if a.probe:
        for name in ('HEAD', 'index', 'refs/heads/main', 'index.lock'):
            try:
                with (repo / '.git' / name).open('r+b'):
                    pass
            except OSError as e:
                require(e.errno in (errno.EPERM, errno.EACCES), '非权限拒绝')
                probes.append('write-open:' + name)
            else:
                raise GuardError('元数据写打开未被拒绝：' + name)
        p = git(repo, 'switch', '--detach', doc['head'], check=False)
        require(p.returncode != 0 and 'index.lock' in p.stderr and 'File exists' in p.stderr,
                '同内容切换未在 index lock 准入阶段拒绝')
        probes.append('same-content-switch-before-checkout')
        unchanged(repo, doc['paths'], locked=True)
        identity(repo, doc['head'])
    require(not (repo / '.git/objects').lstat().st_flags & stat.UF_IMMUTABLE, '共享 objects 被锁')
    return dict(state='VERIFIED', mode='BRANCH_ONLY', head=doc['head'], probes=probes,
                file_edit_and_worktree_commit='另用隔离行为验证；不从 flags 推断')


def release(a):
    state, doc, repo = load(a)
    require(a.owner == doc['owner'] and a.reason.strip(), '维护 owner/原因不符')
    doc.update(state='RELEASING', reason=a.reason, maintenance_at=now())
    save(state, doc)
    # 保留既有 flags；最后解除并移除本工具的 index.lock，避免提前让 Git 进入。
    for r in doc['paths']:
        if not r['flags'] & stat.UF_IMMUTABLE:
            p = repo / '.git' / r['name']
            unchanged(repo, [r])
            os.chflags(p, p.lstat().st_flags & ~stat.UF_IMMUTABLE, follow_symlinks=False)
    unchanged(repo, doc['paths'])
    (repo / '.git/index.lock').unlink()
    doc.update(state='RELEASED', released_at=now())
    save(state, doc)
    return dict(state='RELEASED', note='维护完毕须用新回执/新清单重装并核验')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    i = sub.add_parser('install')
    i.add_argument('--allow-index-blocking', action='store_true',
                   help='显式接受主目录 add/commit 被阻断；不适用需要正常提交的主目录')
    for key in ('repo', 'expected-head', 'base', 'handoff', 'state'):
        i.add_argument('--' + key, required=True)
    v = sub.add_parser('verify')
    v.add_argument('--state', required=True)
    v.add_argument('--probe', action='store_true')
    r = sub.add_parser('release')
    for key in ('state', 'owner', 'reason'):
        r.add_argument('--' + key, required=True)
    a = p.parse_args()
    try:
        print(json.dumps(globals()[a.command](a), ensure_ascii=False))
    except (GuardError, OSError, KeyError, ValueError) as e:
        print('main-guard 拒绝：' + str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
