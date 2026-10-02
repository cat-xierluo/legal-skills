#!/usr/bin/env python3
"""Explicit closed-provider recovery; never creates Tasks or sends business text.

Native SQLite is persisted selection, not Orca provider provenance or billing.
The same OS user's explicit provider-session target is a PM recovery decision.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from completion_authority import load_authority, load_completion, completion_path, dispatch_identity

SCHEMA = 'multi-agent-orchestration.zcode-closed-recovery.v1'
LIMIT = 1024 * 1024

def require(ok, why):
    if not ok: raise ValueError(why)

def digest(raw): return hashlib.sha256(raw).hexdigest()

def read(path):
    p=Path(path)
    require(p.is_absolute() and '..' not in p.parts, 'absolute path required')
    # Resolve only the benign system prefix, then reject user symlink components.
    if sys.platform=='darwin' and p.parts[1:2] in (('tmp',),('var',)):
        p=Path('/private')/p.relative_to('/')
    require(not p.is_symlink() and p.parent.resolve(strict=True)==p.parent, 'symlink or aliased parent refused')
    fd=os.open(p,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        st=os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and not st.st_mode&0o022 and st.st_size<=LIMIT,'untrusted or oversized file')
        raw=os.read(fd,LIMIT+1);require(len(raw)<=LIMIT,'oversized file');return raw
    finally:os.close(fd)

def atomic(path,raw):
    p=Path(path);fd,tmp=tempfile.mkstemp(prefix=p.name+'.tmp.',dir=p.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def save(path,obj): atomic(path,(json.dumps(obj,sort_keys=True)+'\n').encode())

def lock(path):
    p=Path(path);require(not p.is_symlink(),'symlink lock')
    fd=os.open(p,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
    st=os.fstat(fd);require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==0o600,'untrusted lock')
    fcntl.flock(fd,fcntl.LOCK_EX);return fd

def call(binary,*args):
    require(os.path.isabs(binary),'absolute Orca required')
    p=subprocess.run([binary,*args,'--json'],capture_output=True,timeout=12)
    require(p.returncode==0,'Orca call failed; inspect exact operation, never replay blind')
    out=json.loads(p.stdout);require(out.get('ok') is True,'Orca response refused');return out

def alias(d,*names):
    values=[d[n] for n in names if n in d]
    require(values and all(isinstance(v,str) and v for v in values) and len(set(values))==1,'missing or conflicting identity aliases')
    return values[0]

def value_alias(d,*names):
    values=[d[n] for n in names if n in d]
    require(values and all(type(v) is type(values[0]) and v==values[0] for v in values),'missing or conflicting explicit aliases')
    return values[0]

def historical(payload):
    require(payload.get('ok') is True,'invalid worker read')
    d=payload['result']['dispatch']
    return dict(dispatch_id=alias(d,'id'),task_id=alias(d,'taskId','task_id'),run_id=alias(d,'runId','run_id'),terminal_handle=alias(d,'assigneeHandle','assignee_handle'),process_incarnation=alias(d,'processIncarnation','process_incarnation'),runtime_id=payload['_meta']['runtimeId'])

def closed_chain(initial,failed,old,worktree_id):
    first,last=historical(initial),historical(failed)
    require(all(first[k]==old[k] for k in first),'initial receipt/authority mismatch')
    require(first['dispatch_id']!=last['dispatch_id'],'later failure required')
    for key in ('runtime_id','run_id','terminal_handle','process_incarnation'):
        require(first[key]==last[key],'initial to failed process chain mismatch')
    r=failed['result'];d=r['dispatch'];obs=r.get('observation',{});live=r.get('projection',{}).get('liveness',{});t=r.get('terminal',{})
    require(d.get('status') in ('failed','stopped') and r.get('worker',{}).get('stage')=='process_exited','failed exited worker required')
    revoked=value_alias(d,'capabilityRevokedAt','capability_revoked_at')
    require(isinstance(revoked,str) and re.fullmatch(r'\d{4}-\d\d-\d\d[T ][0-9:.]+(?:Z|[+-][0-9:]+)?',revoked),'old capability revocation must be positively recorded')
    require(live.get('verdict')=='exited' and live.get('source')=='execution_host' and obs.get('exactWorker') is True and obs.get('status')=='exited','positive exact exit required')
    require(t.get('handle')==last['terminal_handle'] and t.get('worktreeId')==worktree_id and t.get('connected') is False and t.get('writable') is False,'exact closed terminal required')
    return last

def native_selection(db,sid,worktree,expected):
    original=Path(db).expanduser();require(not original.is_symlink(),'symlink native database');p=original.resolve(strict=True);st=p.stat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and not st.st_mode&0o022,'untrusted native database')
    con=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=2)
    try:
        con.execute('PRAGMA query_only=ON');con.execute('BEGIN')
        rows=con.execute('SELECT id,directory,path,parent_id,substr(permission,1,65537),version FROM session WHERE directory=? AND parent_id IS NULL LIMIT 3',(worktree,)).fetchall()
        require(len(rows)==1 and rows[0][0]==sid and rows[0][1]==worktree and rows[0][2]==worktree,'unique native primary Session/path required')
        require(len(rows[0][4] or '')<=65536,'native permission oversized')
        if expected is not None:require(json.loads(rows[0][4]).get('mode')=='yolo','native yolo required')
        entries=con.execute("SELECT substr(data,1,65537),time_updated FROM session_entry WHERE session_id=? AND type='runtime/model_selection' LIMIT 3",(sid,)).fetchall()
        require(len(entries)==1 and isinstance(entries[0][0],str) and len(entries[0][0])<=65536,'unique bounded native model entry required')
        selection=json.loads(entries[0][0])['modelSelection']
        observed={'provider':selection['providerId'],'model':selection['modelId'],'effort':selection['options']['reasoningLevel']}
        if expected is not None:require(observed==expected,'native model/effort mismatch; no business input permitted')
        return {'session_id':sid,'selection':observed,'version':rows[0][5],'model_updated':entries[0][1],'source':'native_sqlite_readonly','provider_provenance':'NOT_ORCA_PROVIDER_PROVENANCE'}
    finally:
        con.close()
        after=p.stat();require((after.st_dev,after.st_ino)==(st.st_dev,st.st_ino),'native database replaced during observation')

def snapshot(metadata,authority):
    raw=read(metadata);m=json.loads(raw);a,ah=load_authority(authority)
    wt=str(Path(m['worktree']).resolve(strict=True));session=m['session'];s=session['orca'];ea=m['execution_authority']
    require(m['runtime']['worker_backend']=='zcode-cli' and ea['authority_receipt_file']==authority and ea['authority_receipt_sha256']==ah,'launch authority/backend mismatch')
    require(a.get('session')==session['id'] and a.get('worktree')==wt and a.get('branch')==m['branch'],'authority Session/worktree mismatch')
    require(Path(metadata).resolve()==Path(wt)/'.claude/agent-sessions'/session['id']/'METADATA.json','exact Session Context required')
    old=load_completion(completion_path(authority),authority,ah)
    require(all(old[k]==s['supervised'][{'task_id':'task_id','dispatch_id':'dispatch_id','run_id':'run_id'}[k]] for k in ('task_id','dispatch_id','run_id')) and old['terminal_handle']==s['terminal_handle'] and old['runtime_id']==s['runtime_id'],'metadata initial completion mismatch')
    return m,raw,old,ah

def native_binary(path):
    p=Path(path);require(p.is_absolute() and not p.is_symlink(),'canonical native Node required')
    fd=os.open(p,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        st=os.fstat(fd);require(stat.S_ISREG(st.st_mode) and not st.st_mode&0o022 and st.st_size<=256*1024**2,'native Node unsafe')
        h=hashlib.sha256()
        with os.fdopen(fd,'rb',closefd=False) as f:
            magic=f.read(4);require(magic in (b'\x7fELF',b'\xcf\xfa\xed\xfe',b'\xca\xfe\xba\xbe'),'native Node executable required');h.update(magic)
            for block in iter(lambda:f.read(1024**2),b''):h.update(block)
        return {'path':str(p),'sha256':h.hexdigest(),'device':st.st_dev,'inode':st.st_ino,'size':st.st_size}
    finally:os.close(fd)

def run_owner(binary,run,runtime):
    out=call(binary,'orchestration','run-show','--id',run)
    row=out['result']['run']
    require(out['_meta']['runtimeId']==runtime and row.get('id')==run,'run owner scope drift')
    handle=alias(row,'coordinator_handle','coordinatorHandle')
    generation=value_alias(row,'consumer_generation','consumerGeneration')
    require(type(generation) is int and generation>=0,'unknown coordinator generation')
    return {'handle':handle,'generation':generation}

def recheck(r,post_start=False):
    m,raw,old,ah=snapshot(r['metadata'],r['authority'])
    status=call(r['orca_bin'],'status')['result']['runtime']
    require(status.get('reachable') is True and status.get('runtimeId')==r['runtime_id'],'runtime unavailable or replaced')
    require(run_owner(r['orca_bin'],r['failed']['run_id'],r['runtime_id'])==r['owner'],'current run owner drift')
    require(digest(raw)==r['metadata_sha256'] and digest(read(completion_path(r['authority'])))==r['completion_sha256'] and ah==r['authority_sha256'],'original routing/authority drift')
    for label,args in [('branch',('branch','--show-current')),('head',('rev-parse','HEAD'))]:
        p=subprocess.run(['git','-C',r['worktree'],*args],capture_output=True,text=True,timeout=8)
        require(p.returncode==0 and (post_start and label=='head' or p.stdout.strip()==r[label]),'Git identity drift')
    initial=call(r['orca_bin'],'orchestration','worker-show','--dispatch',old['dispatch_id'])
    failed=call(r['orca_bin'],'orchestration','worker-show','--dispatch',r['failed']['dispatch_id'])
    require(closed_chain(initial,failed,old,r['worktree_id'])==r['failed'],'failed chain drift')
    native_selection(r['native_db'],r['provider_session'],r['worktree'],None if post_start else r['expected_model'])
    require(digest(read(r['launch']))==r['launch_sha256'],'original launch drift')
    require(digest(read(r['zcode_bin']))==r['zcode_bin_sha256'] and digest(read(r['zcode_entry']))==r['zcode_entry_sha256'],'native executable drift')
    require(native_binary(r['native_node']['path'])==r['native_node'],'native Node drift')
    if r['state'] in ('prepared','opening'):
        require(0<=time.time()-r['created_at']<=120,'unopened recovery intent expired')
    return m

def prepare(a):
    m,raw,old,ah=snapshot(a.metadata,a.authority);s=m['session']['orca']
    failed=closed_chain(call(a.orca_bin,'orchestration','worker-show','--dispatch',old['dispatch_id']),call(a.orca_bin,'orchestration','worker-show','--dispatch',a.failed_dispatch),old,s['worktree_id'])
    expected={'provider':a.provider,'model':a.model,'effort':a.effort}
    native_selection(a.native_db,a.provider_session,m['worktree'],expected)
    words=shlex.split(m['runtime']['command'])
    require(not any(x in m['runtime']['command'] for x in ('\n',';','|','&','`','$(','<','>')),'opaque command refused')
    require('--resume' not in words and not any(x.startswith('--resume=') for x in words),'original command already resumes')
    require(a.zcode_bin in words and words.count(a.zcode_bin)==1 and words[-2:]==['--mode','yolo'],'explicit flat original yolo command required')
    require(words.index(a.zcode_bin)==len(words)-3,'original CLI argv not narrowly supported')
    require(words[0]=='env' and all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=[^\n]*',x) or x=='env' for x in words[:words.index(a.zcode_bin)]),'original env prefix unsupported')
    launch=Path(a.metadata).parent/'launch.sh';launchraw=read(str(launch))
    quoted=subprocess.run(['/bin/bash','--noprofile','--norc','-c','printf %q "$1"','_',m['runtime']['command']],capture_output=True,check=True).stdout
    require(launchraw.startswith(b'#!/bin/bash\n') and launchraw.splitlines()[-1]==b'exec bash -c '+quoted,'frozen original launch mismatch')
    r={'schema':SCHEMA,'nonce':str(uuid.uuid4()),'state':'prepared','created_at':time.time(),'metadata':a.metadata,'metadata_sha256':digest(raw),'authority':a.authority,'authority_sha256':ah,'completion_sha256':digest(read(completion_path(a.authority))),'initial':old,'failed':failed,'worktree':m['worktree'],'worktree_id':s['worktree_id'],'runtime_id':s['runtime_id'],'session':m['session']['id'],'branch':m['branch'],'head':subprocess.check_output(['git','-C',m['worktree'],'rev-parse','HEAD'],text=True).strip(),'orca_bin':a.orca_bin,'native_db':str(Path(a.native_db).expanduser().resolve()),'provider_session':a.provider_session,'expected_model':expected,'zcode_bin':a.zcode_bin,'zcode_bin_sha256':digest(read(a.zcode_bin)),'zcode_entry':a.zcode_entry,'zcode_entry_sha256':digest(read(a.zcode_entry)),'launch':str(launch),'launch_sha256':digest(launchraw),'launch_prefix':launchraw.rsplit(b'\n',2)[0].decode()+'\n','resume_argv':words+['--resume',a.provider_session],'provider_provenance':'NOT_ORCA_PROVIDER_PROVENANCE','helper_sha256':digest(read(str(Path(__file__).resolve()))),'native_node':native_binary(a.zcode_node),'owner':run_owner(a.orca_bin,failed['run_id'],s['runtime_id'])}
    directory=Path(a.authority).parent;fd=lock(directory/(r['session']+'.recovery.lock'))
    try:
        for p in directory.glob(r['session']+'.recovery-*.json'):
            previous=json.loads(read(str(p)))
            require(previous['failed']['dispatch_id']!=a.failed_dispatch,'recovery source already reserved; inspect prior intent')
        path=directory/(r['session']+'.recovery-'+r['nonce']+'.json');save(path,r)
    finally:os.close(fd)
    return {'ok':True,'intent':str(path),'business_input':False,'next_action':'open'}

def load_intent(path):
    r=json.loads(read(path));require(r.get('schema')==SCHEMA and Path(path).parent==Path(r['authority']).parent and Path(path).name==r['session']+'.recovery-'+r['nonce']+'.json','recovery intent identity')
    return r

def open_terminal(path):
    r=load_intent(path);fd=lock(Path(r['authority']).parent/(r['session']+'.recovery.lock'))
    try:
        require(r['state']=='prepared','intent already opened; never replay terminal creation')
        recheck(r)
        require(not os.environ.get('MEM_BUDGET_FIXTURE_DIR'),'fixture cannot authorize live restoration')
        budget=os.environ.get('SPAWN_WORKER_MEM_BUDGET_BYTES',str(3*1024**3))
        require(budget.isdecimal() and int(budget)>=3*1024**3,'recovery budget cannot disable or discount')
        probe=subprocess.run([sys.executable,str(Path(__file__).with_name('mem_budget_probe.py')),'--json','--budget',budget],capture_output=True,timeout=15)
        result=json.loads(probe.stdout);require(probe.returncode==0 and result.get('status')=='ok' and result.get('slots',0)>=1,'fresh memory admission refused')
        recheck(r);r['state']='opening';save(path,r)
        os.close(fd);fd=-1
        command=shlex.join([sys.executable,str(Path(__file__).with_name('zcode-orca-launcher.py')),'resume-exec','--intent',path])
        out=call(r['orca_bin'],'terminal','create','--worktree','id:'+r['worktree_id'],'--title',r['session']+' recovery','--command',command)
        fd=lock(Path(r['authority']).parent/(r['session']+'.recovery.lock'))
        latest=load_intent(path);terminal=out['result']['terminal']['handle']
        require(terminal!=r['initial']['terminal_handle'],'new exact terminal required')
        require(latest.get('terminal_handle',terminal)==terminal,'runner/create receipt handle mismatch')
        latest['terminal_handle']=terminal
        if latest['state']=='opening':latest['state']='opened'
        save(path,latest);return {'ok':True,'intent':path,'terminal_handle':terminal,'business_input':False,'next_action':'verify'}
    finally:
        if fd>=0:os.close(fd)

def _resume_exec_locked(path):
    r=load_intent(path)
    claim=Path(path+'.runner-claim')
    claimfd=os.open(claim,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
    os.close(claimfd)
    require(r['state'] in ('opening','opened') and not r.get('runner_pid'),'runner replay')
    recheck(r);require(digest(read(str(Path(__file__).resolve())))==r['helper_sha256'],'helper changed')
    handle=os.environ.get('ORCA_TERMINAL_HANDLE');require(handle and handle!=r['initial']['terminal_handle'] and os.environ.get('ORCA_WORKTREE_ID')==r['worktree_id'],'Orca runner environment mismatch')
    require(str(Path.cwd().resolve())==r['worktree'],'runner cwd mismatch')
    r.update(state='launched',terminal_handle=handle,runner_pid=os.getpid(),runner_start=subprocess.check_output(['/bin/ps','-p',str(os.getpid()),'-o','lstart='],text=True).strip());save(path,r)
    code=r['launch_prefix']+'exec '+shlex.join(r['resume_argv'])+'\n'
    return code

def resume_exec(path):
    r=load_intent(path);fd=lock(Path(r['authority']).parent/(r['session']+'.recovery.lock'))
    try:code=_resume_exec_locked(path)
    finally:os.close(fd)
    os.execve('/bin/bash',['/bin/bash','-c',code],dict(os.environ))

def _verify(path,post_start=False):
    r=load_intent(path);require(r['state']=='launched' or post_start and r['state']=='adoption_failed_rolled_back' and r.get('new_dispatch') and r.get('retry_reserved') is True,'runner not proven')
    recheck(r,post_start=post_start)
    t=call(r['orca_bin'],'terminal','show','--terminal',r['terminal_handle'])['result']['terminal']
    require(t.get('handle')==r['terminal_handle'] and t.get('worktreeId')==r['worktree_id'] and t.get('connected') is True and t.get('writable') is True and t.get('agentIdentity')=='zcode' and isinstance(t.get('incarnationId'),str) and t['incarnationId'],'fresh native terminal identity required')
    start=subprocess.check_output(['/bin/ps','-p',str(r['runner_pid']),'-o','lstart='],text=True).strip()
    command=subprocess.check_output(['/bin/ps','-ww','-p',str(r['runner_pid']),'-o','command='],text=True).strip()
    argv=shlex.split(command)
    require(start==r['runner_start'] and str(Path(argv[0]).resolve(strict=True))==r['native_node']['path'] and len(argv)==6 and str(Path(argv[1]).resolve(strict=True))==r['zcode_entry'] and argv[-4:]==['--mode','yolo','--resume',r['provider_session']],'exact resumed native process not proven')
    native_selection(r['native_db'],r['provider_session'],r['worktree'],None if post_start else r['expected_model'])
    r.update(verified_at=time.time(),terminal_incarnation=t['incarnationId'],terminal_pty=t.get('ptyId'));save(path,r)
    return {'ok':True,'intent':path,'terminal_handle':r['terminal_handle'],'task_id':r['failed']['task_id'],'retry_of':r['failed']['dispatch_id'],'run_id':r['failed']['run_id'],'business_input':False,'provider_provenance':'NOT_ORCA_PROVIDER_PROVENANCE'}

def _admit_retry(path,task,dispatch,terminal,run):
    _verify(path);r=load_intent(path)
    require(r['failed']['task_id']==task and r['failed']['dispatch_id']==dispatch and r['terminal_handle']==terminal and r['failed']['run_id']==run,'retry target mismatch')
    require(not r.get('retry_reserved'),'retry intent already consumed')
    r['retry_reserved']=True;r['retry_request']=str(uuid.uuid4());save(path,r)
    return r

def _adopt(path,new_dispatch):
    r=load_intent(path);require(r.get('retry_reserved') is True and (r['state']=='launched' or r['state']=='adoption_failed_rolled_back' and r.get('new_dispatch',{}).get('dispatch_id')==new_dispatch),'retry reservation or exact recorded adoption retry required')
    _verify(path,post_start=True);recheck(r,post_start=True);payload=call(r['orca_bin'],'orchestration','dispatch-show','--task',r['failed']['task_id']);d=payload['result']['dispatch'];new=dispatch_identity(d)
    require(payload['_meta']['runtimeId']==r['runtime_id'] and new['dispatch_id']==new_dispatch and new['task_id']==r['failed']['task_id'] and new['run_id']==r['failed']['run_id'] and new['terminal_handle']==r['terminal_handle'],'new dispatch identity mismatch')
    require(alias(d,'retryOfDispatchId','retry_of_dispatch_id')==r['failed']['dispatch_id'] and new['dispatch_id'] not in (r['initial']['dispatch_id'],r['failed']['dispatch_id']) and new['process_incarnation']!=r['initial']['process_incarnation'] and re.fullmatch('[0-9a-f]{64}',new['capability_hash']) and value_alias(d,'capabilityRevokedAt','capability_revoked_at') is None and d.get('status') in ('active','dispatched'),'new live retry authority required')
    live=call(r['orca_bin'],'orchestration','worker-show','--dispatch',new_dispatch)
    shown=historical(live)
    require(all(shown[k]==new[k] for k in shown if k!='runtime_id') and shown['runtime_id']==r['runtime_id'],'new worker-show identity mismatch')
    require(live['result'].get('projection',{}).get('liveness',{}).get('verdict')=='live' and live['result'].get('projection',{}).get('liveness',{}).get('source')=='execution_host' and live['result'].get('observation',{}).get('exactWorker') is True and live['result'].get('observation',{}).get('status')=='live','new exact execution-host live proof required')
    require(live['result'].get('terminal',{}).get('incarnationId')==r['terminal_incarnation'] and live['result'].get('terminalResource',{}).get('endpointIncarnation')==new['process_incarnation'] and live['result'].get('terminalResource',{}).get('terminalHandle')==new['terminal_handle'],'new terminal/process incarnation drift')
    m=json.loads(read(r['metadata']));oldmeta=read(r['metadata']);cp=completion_path(r['authority']);oldcompletion=read(cp)
    receipt={'schema':'multi-agent-orchestration.completion-authority.v1','state':'active',**new,'runtime_id':r['runtime_id'],'authority_receipt_file':r['authority'],'authority_receipt_sha256':r['authority_sha256'],'recovery_intent':path}
    public_ownership=live['result']['terminalResource'].get('ownershipState')
    require(public_ownership=='external','exact reused terminal external ownership required')
    supervised=m['session']['orca']['supervised'];previous_ownership=supervised.get('terminal_ownership');supervised['terminal_ownership']=public_ownership;supervised.update(task_id=new['task_id'],dispatch_id=new['dispatch_id'],coordinator_handle=r['owner']['handle']);m['session']['orca']['terminal_handle']=new['terminal_handle']
    m.setdefault('recovery',{})['closed_session']={'intent':path,'initial_task_id':r['initial']['task_id'],'initial_dispatch_id':r['initial']['dispatch_id'],'failed_task_id':r['failed']['task_id'],'failed_dispatch_id':r['failed']['dispatch_id'],'new_dispatch_id':new['dispatch_id'],'previous_terminal_ownership':previous_ownership,'terminal_ownership':public_ownership}
    receiptbytes=(json.dumps(receipt,sort_keys=True)+'\n').encode();m['execution_authority'].update(completion_authority_file=cp,completion_authority_sha256=digest(receiptbytes))
    r['post_start_observation']={'head':subprocess.check_output(['git','-C',r['worktree'],'rev-parse','HEAD'],text=True).strip(),'native_selection':native_selection(r['native_db'],r['provider_session'],r['worktree'],None)}
    r.update(state='adopting',old_metadata=oldmeta.decode(),old_completion=oldcompletion.decode(),new_dispatch=new,new_metadata_sha256=digest((json.dumps(m,sort_keys=True)+'\n').encode()),new_completion_sha256=digest(receiptbytes));save(path,r)
    try:
        atomic(cp,receiptbytes);save(r['metadata'],m);r.update(state='adopted',adopted_at=time.time());save(path,r)
    except BaseException:
        atomic(cp,oldcompletion);atomic(r['metadata'],oldmeta);r['state']='adoption_failed_rolled_back';save(path,r);raise
    return {'ok':True,'new_dispatch_id':new_dispatch,'completion_authority':cp,'recovery_intent':path}

def _rollback(path):
    r=load_intent(path)
    require(r['state']=='adopting','only interrupted adoption may roll back')
    oldmeta=r['old_metadata'].encode();oldcompletion=r['old_completion'].encode()
    require(digest(read(r['metadata'])) in (digest(oldmeta),r['new_metadata_sha256']) and digest(read(completion_path(r['authority']))) in (digest(oldcompletion),r['new_completion_sha256']),'unknown route/completion state; do not overwrite')
    load_authority(r['authority'],r['authority_sha256'])
    atomic(completion_path(r['authority']),oldcompletion);atomic(r['metadata'],oldmeta)
    r['state']='adoption_failed_rolled_back';save(path,r)
    return {'ok':True,'state':r['state'],'new_dispatch_id':r['new_dispatch']['dispatch_id'],'business_retry_allowed':False}

def locked_operation(path,function,*args):
    r=load_intent(path);fd=lock(Path(r['authority']).parent/(r['session']+'.recovery.lock'))
    try:return function(path,*args)
    finally:os.close(fd)

def verify(path):return locked_operation(path,_verify)
def admit_retry(path,*args):return locked_operation(path,_admit_retry,*args)
def adopt(path,*args):return locked_operation(path,_adopt,*args)

def main():
    p=argparse.ArgumentParser(description=__doc__);sp=p.add_subparsers(dest='action',required=True)
    prep=sp.add_parser('prepare')
    for key in ('metadata','authority','failed-dispatch','provider-session','provider','model','effort','orca-bin','zcode-bin','zcode-entry','zcode-node'):prep.add_argument('--'+key,required=True)
    prep.add_argument('--native-db',default=str(Path.home()/'.zcode/cli/db/db.sqlite'))
    for name in ('open','verify','resume-exec','rollback'):
        q=sp.add_parser(name);q.add_argument('--intent',required=True)
    q=sp.add_parser('admit-retry');q.add_argument('--intent',required=True)
    for key in ('task','dispatch','terminal','run'):q.add_argument('--'+key,required=True)
    q=sp.add_parser('adopt');q.add_argument('--intent',required=True);q.add_argument('--new-dispatch',required=True)
    a=p.parse_args()
    try:
        if a.action=='prepare':out=prepare(a)
        elif a.action=='open':out=open_terminal(a.intent)
        elif a.action=='verify':out=verify(a.intent)
        elif a.action=='resume-exec':resume_exec(a.intent);return
        elif a.action=='rollback':out=locked_operation(a.intent,_rollback)
        elif a.action=='admit-retry':out=admit_retry(a.intent,a.task,a.dispatch,a.terminal,a.run);out={'ok':True,'retry_request':out['retry_request']}
        else:out=adopt(a.intent,a.new_dispatch)
        print(json.dumps(out,sort_keys=True))
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,subprocess.SubprocessError):
        print('ZCODE_CLOSED_RECOVERY_REFUSED: closed/identity/model/process/admission proof missing; no blind replay',file=sys.stderr);raise SystemExit(64)

if __name__=='__main__':main()
