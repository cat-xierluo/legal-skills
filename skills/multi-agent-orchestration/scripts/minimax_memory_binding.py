"""官方 MiniMax 有界安装闭包与原生 argv 绑定；不启动模型。"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess

WRAPPER = '''#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
release=$(tr -d '\\r\\n' < "$root/current")
case "$release" in ""|*[!0-9A-Za-z._-]*) echo "Invalid MCode current release pointer." >&2; exit 1;; esac
exec "$root/releases/$release/.mcode-launcher" "$@"
'''
LAUNCHER = '''#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec {node} "$root/lib/node_modules/@minimax-ai/code/cli.js" "$@"
'''
MAX_FILES=10000
MAX_BYTES=256*1024**2

def identity(path, directory=False, link=False, max_bytes=MAX_BYTES, capture=False):
    if capture and (directory or link or max_bytes>16384):raise ValueError('buffer capture limited to small grammar files')
    p=Path(path);s=p.lstat()
    if s.st_uid != os.getuid() or (not link and s.st_mode & 0o022):
        raise ValueError('MiniMax runtime must be current-user owned and nonwritable by others')
    if link:
        if not stat.S_ISLNK(s.st_mode):raise ValueError('expected internal link')
    elif (not stat.S_ISDIR(s.st_mode) if directory else not stat.S_ISREG(s.st_mode)):
        raise ValueError('runtime path type mismatch or symlink')
    result={'device':s.st_dev,'inode':s.st_ino,'uid':s.st_uid,'mode':stat.S_IMODE(s.st_mode)}
    if not directory and not link:
        if s.st_size > max_bytes:raise ValueError('file exceeds pre-read byte bound')
        digest=hashlib.sha256();chunks=[]
        with p.open('rb') as stream:
            before=os.fstat(stream.fileno())
            if (before.st_dev,before.st_ino,before.st_size)!=(s.st_dev,s.st_ino,s.st_size):raise ValueError('file changed before bounded read')
            count=0
            while True:
                block=stream.read(min(65536,max_bytes-count+1))
                if not block:break
                count+=len(block)
                if count>max_bytes:raise ValueError('file grew past read bound')
                digest.update(block)
                if capture:chunks.append(block)
            after=os.fstat(stream.fileno())
            if count!=s.st_size or (after.st_size,after.st_mtime_ns,after.st_ctime_ns)!=(before.st_size,before.st_mtime_ns,before.st_ctime_ns):raise ValueError('file mutated during bounded hash')
        result.update(size=s.st_size,sha256=digest.hexdigest())
    return (result,b''.join(chunks)) if capture else result

def read_verified(path,max_bytes):
    return identity(path,max_bytes=max_bytes,capture=True)

def cwd_identity(path,expected_branch,expected_head,expected_common):
    p=Path(path)
    if not p.is_absolute() or str(p.resolve()) != str(p):raise ValueError('execution cwd must be canonical')
    result={'path':str(p),**identity(p,directory=True)}
    if not expected_branch or not re.fullmatch(r'[0-9a-f]{40,64}',expected_head or '') or not expected_common:raise ValueError('isolation pregate branch/HEAD/common-dir required')
    if any(os.environ.get(k) for k in ('GIT_DIR','GIT_WORK_TREE','GIT_COMMON_DIR','GIT_INDEX_FILE','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES')):raise ValueError('Git identity environment override refused')
    def git(*args):
        r=subprocess.run(['/usr/bin/git','-C',str(p),*args],capture_output=True,text=True,timeout=5)
        if r.returncode:raise ValueError('actual Git worktree identity unavailable')
        return r.stdout.strip()
    branch=git('branch','--show-current');head=git('rev-parse','HEAD');common=git('rev-parse','--path-format=absolute','--git-common-dir')
    if branch!=expected_branch or head!=expected_head or common!=expected_common or str(Path(common).resolve())!=common:raise ValueError('Git branch/HEAD/common-dir drift from isolation pregate')
    result.update(branch=branch,head=head,common_dir={'path':common,**identity(common,directory=True)})
    return result

def reject_environment(env):
    if any(env.get(k) for k in env if k in {'NODE_OPTIONS','NODE_PATH'} or k.startswith(('LD_','DYLD_'))):
        raise ValueError('MiniMax caller runtime environment override refused')
    if env.get('SPAWN_WORKER_NODE_MAX_OLD_SPACE_MB','2048') != '2048':raise ValueError('MiniMax old-space override refused')

def installation(executable,env):
    reject_environment(env)
    p=Path(executable)
    if not p.is_absolute() or str(p.resolve()) != str(p) or p.name != 'mcode' or p.parent.name != 'bin':raise ValueError('official canonical bin/mcode required')
    root=p.parent.parent
    identity(root,directory=True);identity(p.parent,directory=True)
    wrapper,wrapper_bytes=read_verified(p,16384)
    if wrapper_bytes.decode('utf-8')!=WRAPPER:raise ValueError('unrecognized official mcode wrapper grammar')
    pointer=root/'current';pointer_id,pointer_bytes=read_verified(pointer,128);release_name=pointer_bytes.decode('utf-8').strip('\r\n')
    if release_name in {'.','..'} or not re.fullmatch(r'[0-9A-Za-z._-]+',release_name):raise ValueError('invalid release pointer')
    releases=root/'releases';identity(releases,directory=True)
    release=releases/release_name
    if str(releases.resolve())!=str(releases) or str(release.resolve())!=str(release) or release.resolve().parent!=releases:raise ValueError('release must be canonical direct child')
    identity(release,directory=True)
    launcher=release/'.mcode-launcher';launcher_id,launcher_bytes=read_verified(launcher,16384)
    content=launcher_bytes.decode('utf-8')
    match=re.fullmatch(re.escape(LAUNCHER).replace(re.escape('{node}'),r"'([^'\n]+)'"),content)
    if not match:raise ValueError('unrecognized official launcher grammar')
    node=Path(match[1])
    if not node.is_absolute() or str(node.resolve()) != str(node):raise ValueError('native Node path not canonical')
    node_id=identity(node,max_bytes=256*1024**2)
    with node.open('rb') as source:magic=source.read(4)
    if magic not in (b'\x7fELF',b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca',b'\xca\xfe\xba\xbf'):raise ValueError('interpreter is not native binary')
    grammar_bindings=((p,16384,wrapper,wrapper_bytes),(pointer,128,pointer_id,pointer_bytes),(launcher,16384,launcher_id,launcher_bytes))
    def recheck_grammar():
        for path,limit,expected,expected_bytes in grammar_bindings:
            observed,buffer=read_verified(path,limit)
            if observed!=expected or buffer!=expected_bytes:raise ValueError('verified grammar fingerprint/bytes drift')
    recheck_grammar()
    rows=[];total=0
    for base,dirs,files in os.walk(release,followlinks=False):
        dirs.sort();files.sort()
        for name in sorted(set(dirs+files)):
            if len(rows)>=MAX_FILES:raise ValueError('release closure exceeds file bound')
            item=Path(base)/name;relative=str(item.relative_to(release))
            if item.is_symlink():
                meta=identity(item,link=True);target=item.resolve(strict=True)
                if not target.is_relative_to(release):raise ValueError('release symlink escapes closure')
                meta.update(type='link',target=os.readlink(item))
            elif item.is_dir():meta={**identity(item,directory=True),'type':'directory'}
            else:
                meta={**identity(item,max_bytes=MAX_BYTES-total),'type':'file'};total+=meta['size']
            rows.append({'path':relative,**meta})
            if len(rows)>MAX_FILES or total>MAX_BYTES:raise ValueError('release closure exceeds bound')
    recheck_grammar()
    entry=release/'lib/node_modules/@minimax-ai/code/cli.js';identity(entry)
    observation=subprocess.run([str(node),'--max-old-space-size=2048','--max-semi-space-size=1','-e','process.stdout.write(JSON.stringify({execPath:process.execPath,version:process.versions.node,heap:require("v8").getHeapStatistics().heap_size_limit}))'],env=dict(env),capture_output=True,text=True,timeout=5)
    fact=json.loads(observation.stdout)
    if observation.returncode or fact.get('execPath')!=str(node) or not re.fullmatch(r'\d+\.\d+\.\d+',fact.get('version','')) or type(fact.get('heap')) is not int or not 2048*1024**2 <= fact['heap'] <= 2056*1024**2 or identity(node,max_bytes=256*1024**2)!=node_id:raise ValueError('actual native Node heap/identity observation refused')
    recheck_grammar()
    return {'root':str(root),'wrapper':wrapper,'current':pointer_id,'release':str(release),'release_identity':identity(release,directory=True),'closure_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'closure_count':len(rows),'closure_bytes':total,'node':{'path':str(node),**node_id,**fact},'entry':{'path':str(entry),**identity(entry)}}

def command_plan(command,backend,script_dir,env):
    if backend!='minimax-code':raise ValueError('bounded MiniMax backend identity required')
    reject_environment(env)
    words=shlex.split(command)
    body=command
    if words and Path(words[0]).name in {'bash','sh'}:
        if len(words)!=3 or words[1] not in {'-c','-lc'}:raise ValueError('only one literal shell body supported')
        body=words[2]
    if any(c in body for c in ('$', '`', '\n',';','|','&','>','\\')):raise ValueError('opaque shell expansion/chaining refused')
    if not re.match(r'^(?:mcode|/[A-Za-z0-9_./-]+/mcode)(?:\s|$)',body):raise ValueError('environment/quoted launcher refused')
    spec=importlib.util.spec_from_file_location('minimax_command_validator',Path(script_dir)/'validate-worker-command.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    v.validate_safe_command_substitutions(command)
    argv=[];redirects=[]
    actual=v.command_backend(v.split_words(command,shell_body=True),expected=backend,trusted_claude_wrapper='',shell_body=True,resolved_argv=argv,stdin_redirect=redirects)
    if actual!=backend:raise ValueError('actual backend mismatch')
    mode=v.resolve_minimax_startup(command,require_input=False)
    if any(re.search(r'NODE_OPTIONS|max[-_]old[-_]space[-_]size|max[-_]semi[-_]space[-_]size|max[-_]heap[-_]size',x,re.I) for x in argv):raise ValueError('native argv heap override refused')
    if any(x == '--cwd' or x.startswith('--cwd=') or x in {'--directory','--working-directory','--config-dir'} or x.startswith(('--directory=','--working-directory=','--config-dir=')) for x in argv):raise ValueError('native execution cwd override refused')
    stdin=None
    if mode=='batch':
        if len(redirects)!=1:raise ValueError('bounded batch requires exactly one owned stdin redirect')
        stdin={'path':redirects[0],**identity(redirects[0],max_bytes=1024**2)}
        if str(Path(redirects[0]).resolve())!=redirects[0] or stdin['size']<1:raise ValueError('stdin must be nonempty canonical regular nonlink')
        v.resolve_minimax_startup(command,require_input=True)
        for key,expected in (('--timeout','20m'),('--max-steps','60')):
            values=[argv[i+1] for i,x in enumerate(argv[:-1]) if x==key]+[x.split('=',1)[1] for x in argv if x.startswith(key+'=')]
            if values!=[expected]:raise ValueError('bounded batch requires exact 20m/60 native limits')
    elif redirects:raise ValueError('interactive stdin redirect refused')
    executable=shutil.which(argv[0]) or argv[0]
    chain=installation(str(Path(executable)),env)
    return {'mode':mode,'native_argv':argv[1:],'stdin':stdin,'installation':chain,'actual_argv':[chain['node']['path'],'--max-old-space-size=2048','--max-semi-space-size=1',chain['entry']['path'],*argv[1:]],'limits':{'node_old_space_mb':2048,'semi_space_mb':1,'whole_worker_rss_cap':None,'timeout_steps':'native_exec_20m_60' if mode=='batch' else 'original_PM_monitoring_not_mechanically_enforced','pty':'inherited_native_interactive' if mode=='interactive' else 'not_required'}}

def execute(plan,env,cwd):
    reject_environment(env)
    if os.environ.get('MEM_BUDGET_FIXTURE_DIR'):raise ValueError('fixture diagnostic cannot execute MiniMax')
    if cwd_identity(os.getcwd(),cwd['branch'],cwd['head'],cwd['common_dir']['path']) != cwd:raise ValueError('actual cwd identity drift')
    if installation(str(Path(plan['installation']['root'])/'bin/mcode'),env)!=plan['installation']:raise ValueError('runtime closure drift at exec')
    fd=None
    try:
        if plan['stdin']:
            p=plan['stdin'];fd=os.open(p['path'],os.O_RDONLY|os.O_NOFOLLOW);s=os.fstat(fd)
            meta={'device':s.st_dev,'inode':s.st_ino,'uid':s.st_uid,'mode':stat.S_IMODE(s.st_mode),'size':s.st_size}
            if any(meta[k]!=p[k] for k in meta) or not stat.S_ISREG(s.st_mode):raise ValueError('stdin fstat drift')
            digest=hashlib.sha256()
            while True:
                block=os.read(fd,65536)
                if not block:break
                digest.update(block)
            if digest.hexdigest()!=p['sha256']:raise ValueError('stdin bytes drift')
            os.lseek(fd,0,os.SEEK_SET);os.dup2(fd,0)
        if cwd_identity(os.getcwd(),cwd['branch'],cwd['head'],cwd['common_dir']['path']) != cwd:raise ValueError('Git cwd identity changed at exec boundary')
        os.execve(plan['actual_argv'][0],plan['actual_argv'],env)
    finally:
        if fd is not None:os.close(fd)
