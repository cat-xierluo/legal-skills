#!/usr/bin/env python3
"""只读检出准入：Skill monorepo 默认 sparse；不创建资源、不启动 Agent。"""
import argparse
import json
import os
import re
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys


def git(repo, *args):
    return subprocess.check_output(['git', '-c', 'core.quotePath=false', '-C', str(repo), *args], stderr=subprocess.PIPE).decode().strip()


def plan(repo, base, scopes, allow_paths, transport, full_reason='', full_source='', budget_mib=512, borrowed=''):
    if (not isinstance(scopes,list) or not isinstance(allow_paths,list)
        or any(not isinstance(x,str) for x in scopes+allow_paths)
        or not isinstance(full_reason,str) or not isinstance(full_source,str)):
        raise ValueError('CHECKOUT_INVALID_CONTRACT_TYPES')
    if any(os.environ.get(k) for k in ('GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_COMMON_DIR','GIT_NAMESPACE')):
        raise ValueError('CHECKOUT_GIT_ENV_OVERRIDE')
    repo = Path(repo).resolve(strict=True)
    oid = git(repo, 'rev-parse', '--verify', base + '^{commit}')
    records = git(repo, 'ls-tree', '-rlz', oid).split('\0')
    files = []
    for item in records:
        if not item: continue
        fields, name = item.split('\t', 1)
        mode, kind, object_id, size = fields.split()
        files.append((name, int(size) if size != '-' else 0, mode))
    skills = sorted({str(PurePosixPath(f).parent) for f,_,_ in files if f.endswith('/SKILL.md')})
    explicit_scopes = bool(scopes)
    scopes = list(scopes)
    full = bool(full_reason or full_source)
    if full and (not full_reason.strip() or not full_source.strip() or scopes):
        raise ValueError('CHECKOUT_FULL_REQUIRES_REASON_SOURCE_WITHOUT_SCOPES')
    if not scopes and not full and skills:
        for path in allow_paths:
            matches = [s for s in skills if path == s or path.startswith(s + '/')]
            if not matches and not path.startswith('.claude/'):
                raise ValueError('CHECKOUT_SCOPE_REQUIRED: write path does not identify a Skill; declare --checkout-scope')
            scopes.extend(matches)
        if not scopes:
            raise ValueError('CHECKOUT_SCOPE_REQUIRED: Skill iteration/reviewer must declare target/read dependencies')
    normalized = []
    for scope in scopes:
        s = scope.rstrip('/'); p = PurePosixPath(s)
        if not s or p.is_absolute() or any(x in s.split('/') for x in ('','.','..')) or any(c in s for c in '\r\n\\\t'):
            raise ValueError('CHECKOUT_INVALID_SCOPE')
        if git(repo, 'cat-file', '-t', oid + ':' + s) != 'tree':
            raise ValueError('CHECKOUT_SCOPE_NOT_TREE: ' + s)
        if s not in normalized: normalized.append(s)
    mode = 'sparse' if normalized else 'full'
    if normalized:
        ancestors = {str(a) for s in normalized for a in PurePosixPath(s).parents}
        for path in allow_paths:
            if path.startswith('.claude/'): continue
            prefix=re.split(r'[*?\[]',path,maxsplit=1)[0].rstrip('/')
            if not prefix or PurePosixPath(prefix).is_absolute() or '..' in PurePosixPath(prefix).parts:
                raise ValueError('CHECKOUT_WRITE_SCOPE_UNPROVED')
            if not (any(prefix==s or prefix.startswith(s+'/') for s in normalized)
                    or (not any(c in path for c in '*?[') and str(PurePosixPath(prefix).parent) in ancestors)):
                raise ValueError('CHECKOUT_WRITE_SCOPE_OUTSIDE: ' + path)
    if mode == 'sparse' and transport == 'orca' and not borrowed:
        raise ValueError('PARKED_FOR_CHECKOUT_CAPABILITY: Orca CLI has no verified first-checkout sparse entry; use supported preset/borrowed contract or explicitly chosen Git transport')
    if normalized:
        ancestors = {str(a) for s in normalized for a in PurePosixPath(s).parents}
        selected = [(f,size,m) for f,size,m in files if any(f.startswith(s+'/') for s in normalized) or str(PurePosixPath(f).parent) in ancestors]
    else: selected = files
    if any(m == '160000' and any(f==s or f.startswith(s+'/') for s in normalized) for f,_,m in selected):
        raise ValueError('CHECKOUT_SUBMODULE_REQUIRES_SEPARATE_CONTRACT')
    if isinstance(budget_mib,bool) or not isinstance(budget_mib,int) or budget_mib <= 0:
        raise ValueError('CHECKOUT_INVALID_DISK_BUDGET')
    # Conservative file-block + complete-index allowance; a plan, not measured usage.
    estimate = sum(max(4096, ((size+4095)//4096)*4096) for _,size,_ in selected) + 32*1024**2
    if estimate > budget_mib*1024**2 or shutil.disk_usage(repo).free < estimate:
        raise ValueError('CHECKOUT_DISK_BUDGET_EXCEEDED')
    if borrowed and mode == 'sparse':
        tree=Path(borrowed).resolve(strict=True)
        common=lambda r:Path(git(r,'rev-parse','--path-format=absolute','--git-common-dir')).resolve()
        if common(tree)!=common(repo) or git(tree,'rev-parse','HEAD')!=oid:
            raise ValueError('CHECKOUT_BORROWED_IDENTITY_MISMATCH')
        actual=git(tree,'sparse-checkout','list').splitlines()
        if any(not any(s==a or s.startswith(a+'/') for a in actual) for s in normalized):
            raise ValueError('CHECKOUT_BORROWED_SCOPE_MISMATCH')
    return {'mode':mode,'base_oid':oid,'scopes':normalized,'estimated_bytes':estimate,
            'budget_mib':budget_mib,'full_reason':full_reason,'full_source':full_source,
            'scope_source':'explicit' if explicit_scopes else 'allowed-Skill-roots' if normalized else 'full-exception' if full else 'ordinary-repository', 'transport':transport}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',default='.')
    p.add_argument('--base',default='HEAD')
    p.add_argument('--scope',action='append',default=[])
    p.add_argument('--allow-path',action='append',default=[])
    p.add_argument('--transport',choices=['git','orca'],default='git')
    p.add_argument('--full-reason',default='')
    p.add_argument('--full-source',default='')
    p.add_argument('--budget-mib',type=int,default=512)
    p.add_argument('--borrowed',default='')
    p.add_argument('--wave-manifest')
    a=p.parse_args()
    if a.wave_manifest:
        d=json.loads(Path(a.wave_manifest).read_text());results=[]
        repo=d.get('project',a.repo)
        if not Path(repo).is_dir(): raise ValueError('CHECKOUT_WAVE_PROJECT_NOT_FOUND')
        probe=subprocess.run(['git','-C',str(repo),'rev-parse','--is-inside-work-tree'],capture_output=True)
        if probe.returncode:
            if 'project' not in d:
                raise ValueError('CHECKOUT_WAVE_PROJECT_REQUIRED: declare project when caller is not a Git worktree')
            print(json.dumps({'mode':'non-Git-context','worktree_creation':False}));return
        for task in d['tasks']:
            c=task.get('checkout',{})
            if not isinstance(c,dict):raise ValueError('CHECKOUT_INVALID_WAVE_CONTRACT')
            results.append(plan(repo,c.get('base_ref','HEAD'),c.get('scopes',[]),[], 'orca',c.get('full_reason',''),c.get('full_source',''),c.get('budget_mib',512),c.get('borrowed_worktree','')))
        if sum(r['estimated_bytes'] for r in results)>shutil.disk_usage(repo).free:
            raise ValueError('CHECKOUT_WAVE_DISK_BUDGET_EXCEEDED')
        print(json.dumps(results,ensure_ascii=False));return
    print(json.dumps(plan(a.repo,a.base,a.scope,a.allow_path,a.transport,a.full_reason,a.full_source,a.budget_mib,a.borrowed),ensure_ascii=False))


if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,OSError,subprocess.CalledProcessError) as e:
        print(str(e),file=sys.stderr);sys.exit(64)
