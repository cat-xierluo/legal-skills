#!/usr/bin/env python3
"""Explicit first-entry gate for an externally owned long-lived Git worktree.

Locks serialize MAO entries only; they cannot restrain an independent same-user
writer. Fresh process/runtime and dirty checks are repeated before launch.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

SCHEMA="multi-agent-orchestration.borrowed-worktree.v1"
SESSION_FILES=("METADATA.json","INSTALL_AUTHORIZATION.json","launch.sh")
class Refused(ValueError): pass

def need(condition,code):
    if not condition: raise Refused(code)
def run(argv):
    try: p=subprocess.run(argv,capture_output=True,timeout=10)
    except (OSError,subprocess.TimeoutExpired): raise Refused("dependency_or_read_unavailable")
    need(p.returncode==0,"dependency_or_read_failed")
    return p.stdout

def canonical(text):
    p=Path(text)
    need(p.is_absolute() and ".." not in p.parts,"absolute_path_required")
    if p.parts[1:2] in (("tmp",),("var",)): p=Path("/private")/p.relative_to("/")
    q=Path("/")
    for part in p.parts[1:]:
        q=q/part;need(not q.is_symlink(),"symlink_path")
    return str(p.resolve(strict=True))
def git(wt,*args): return run(["git","-C",wt,*args])
def common(wt): return canonical(git(wt,"rev-parse","--path-format=absolute","--git-common-dir").decode().strip())
def digest(data): return hashlib.sha256(data).hexdigest()
def read(path):
    path=canonical(path);s=os.stat(path)
    need(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and not s.st_mode & 0o022 and s.st_size<=1024*1024,"contract_untrusted")
    return Path(path).read_bytes()
def write(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    with os.fdopen(fd,"w") as f:
        json.dump(value,f,sort_keys=True);f.write("\n");f.flush();os.fsync(f.fileno())
def directory(path):
    if not path.exists():path.mkdir(mode=0o700)
    need(not path.is_symlink() and path.stat().st_uid==os.getuid() and stat.S_IMODE(path.stat().st_mode)==0o700,"private_directory_untrusted")
def paths(wt):
    c=Path(common(wt));key=digest(wt.encode())
    return c/"agent-borrowed-worktrees"/(key+".json"),c/"agent-borrowed-locks"/(key+".lock")
def protected(project,wt,branch):
    wt=canonical(wt);need(common(project)==common(wt),"repository_mismatch")
    marker,_=paths(wt)
    if marker.parent.exists() or marker.parent.is_symlink():
        need(not marker.parent.is_symlink() and marker.parent.stat().st_uid==os.getuid() and stat.S_IMODE(marker.parent.stat().st_mode)==0o700,"ownership_unknown_retain")
    if not marker.exists() and not marker.is_symlink():
        need(not marker.with_suffix(".reserved").exists() and not marker.with_suffix(".reserved").is_symlink(),"ownership_ledger_missing_retain")
        return False
    m=json.loads(read(str(marker)))
    need(m.get("schema")==SCHEMA and m.get("worktree")==wt and m.get("common_dir")==common(wt)
         and m.get("branch")==branch and m.get("ownership")=="borrowed","ownership_unknown_retain")
    return True

def dirty(wt,session=""):
    specs=["--","."]
    if session:
        context=Path(wt)/".claude"/"agent-sessions"/session
        if context.exists():
            need(not context.is_symlink(),"session_directory_untrusted")
            need(all(p.name in SESSION_FILES and not p.is_symlink() and p.is_file() for p in context.iterdir()),"session_assets_uncovered")
        specs.extend(":(exclude).claude/agent-sessions/"+session+"/"+name for name in SESSION_FILES)
    h=hashlib.sha256()
    for args in (("status","--porcelain=v1","-z"),("diff","--binary"),("diff","--cached","--binary","HEAD")):
        raw=git(wt,*args,*specs);h.update(len(raw).to_bytes(8,"big"));h.update(raw)
    ignored=git(wt,"ls-files","--others","--ignored","--exclude-standard","-z",*specs)
    need(not ignored,"ignored_assets_uncovered")
    tracked=git(wt,"ls-files","-z",*specs).split(b"\0")
    untracked=git(wt,"ls-files","--others","--exclude-standard","-z",*specs).split(b"\0")
    names=set(tracked+untracked)
    need(len(names)<=20000,"asset_inventory_limit")
    total=0
    for name in sorted(n for n in names if n):
        p=Path(wt)/os.fsdecode(name)
        if not p.exists() and not p.is_symlink():
            h.update(name);h.update(b"deleted");continue
        s=p.lstat()
        total+=s.st_size
        need(s.st_size<=32*1024*1024 and total<=256*1024*1024,"asset_size_limit")
        need(stat.S_ISREG(s.st_mode) or stat.S_ISLNK(s.st_mode),"dirty_file_unreadable")
        raw=os.fsencode(os.readlink(p)) if p.is_symlink() else p.read_bytes()
        h.update(name);h.update(str(stat.S_IMODE(s.st_mode)).encode());h.update(digest(raw).encode())
    return h.hexdigest()

def no_writer(wt,controller_pid=0,baseline_pids=None,launcher_parent_pid=0):
    # Query the entire owner UID inventory. Do not classify writers by argv:
    # a custom Python/node/shell process at the target cwd is equally unsafe.
    try:
        observer=subprocess.Popen(["ps","-u",str(os.getuid()),"-o","pid=,ppid="],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:raw,_=observer.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            observer.kill();observer.communicate();raise Refused("dependency_or_read_unavailable")
    except OSError:raise Refused("dependency_or_read_unavailable")
    need(observer.returncode==0,"dependency_or_read_failed")
    rows={}
    for row in raw.decode().splitlines():
        fields=row.strip().split(None,2)
        need(len(fields)>=2 and fields[0].isdigit() and fields[1].isdigit(),"process_schema_unknown")
        pid=int(fields[0]);need(pid>0 and pid not in rows,"process_inventory_incomplete")
        rows[pid]=int(fields[1])
    need(os.getpid() in rows,"process_inventory_incomplete")
    own={os.getpid(),observer.pid}
    if controller_pid:
        # On first entry the controller must be an actual caller ancestor.
        # Subsequent calls have already proved its private lock/start binding.
        if baseline_pids is None:
            current=os.getppid();seen=set()
            while current and current not in seen and current!=controller_pid:
                seen.add(current);current=rows.get(current,0)
            need(current==controller_pid,"borrow_controller_lineage_unknown")
        own.add(controller_pid)
    if launcher_parent_pid:
        need(launcher_parent_pid==os.getppid() and isinstance(baseline_pids,list),"launcher_lineage_unknown")
        current=launcher_parent_pid;seen=set()
        # Exact live native launcher ancestry, newly created after acquisition.
        # A baseline process can never become exempt merely by its program name.
        while current and current not in seen and current not in baseline_pids:
            own.add(current);seen.add(current);current=rows.get(current,0)
    for pid in sorted(set(rows)-own):
        raw=run(["lsof","-a","-p",str(pid),"-d","cwd","-Fpn"]).decode().splitlines()
        returned=[x[1:] for x in raw if x.startswith("p")]
        cwd=[x[1:] for x in raw if x.startswith("n")]
        need(returned==[str(pid)] and len(cwd)==1,"process_cwd_unknown")
        current=canonical(cwd[0]);need(Path(current).is_dir(),"process_cwd_unknown")
        need(current!=wt and not current.startswith(wt+os.sep),"active_native_writer")
    return sorted(set(rows)|own)

def rpc(binary,*args):
    need(os.path.isabs(binary) and os.access(binary,os.X_OK),"orca_binary_unavailable")
    value=json.loads(run([binary,*args,"--json"]))
    need(value.get("ok") is True,"orca_response_unknown")
    return value

def runtime(c,binary,terminal=""):
    status=rpc(binary,"status").get("result",{}).get("runtime",{})
    need(status.get("runtimeId")==c["runtime_id"] and status.get("reachable") is True,"runtime_drift")
    w=rpc(binary,"worktree","show","--worktree","id:"+c["orca_worktree_id"]).get("result",{}).get("worktree",{})
    need(w.get("id")==c["orca_worktree_id"] and canonical(w.get("path",""))==c["worktree"]
         and w.get("branch")==c["branch"],"orca_worktree_mismatch")
    inventory=rpc(binary,"terminal","list","--worktree","id:"+c["orca_worktree_id"])
    result=inventory.get("result",{})
    need(not result.get("truncated") and not result.get("hasMore") and not result.get("nextCursor")
         and not result.get("pagination",{}).get("nextCursor"),"terminal_inventory_incomplete")
    rows=result.get("terminals")
    need(isinstance(rows,list),"terminal_inventory_unknown")
    for row in rows:
        need(isinstance(row,dict) and row.get("worktreeId")==c["orca_worktree_id"]
             and isinstance(row.get("connected"),bool),"terminal_inventory_unknown")
        need(not row["connected"] or terminal and row.get("handle")==terminal,"active_orca_terminal")

def validate(path,project,wt,branch,binary,session="",owner_pid=0,terminal="",initial=False,initial_controller_pid=0,launcher_parent_pid=0,process_observation=None):
    raw=read(path);c=json.loads(raw)
    need(c.get("schema")==SCHEMA and c.get("approved_by") and isinstance(c.get("created_at"),(int,float))
         and 0<=time.time()-c["created_at"]<=120,"contract_schema_or_stale")
    project=canonical(project);wt=canonical(wt)
    need(c["project"]==project and c["worktree"]==wt and c["common_dir"]==common(wt)==common(project)
         and wt!=project,"repository_or_path_mismatch")
    listed=git(project,"worktree","list","--porcelain").decode().split("\n\n")
    need(any("worktree "+wt in block.splitlines() and "branch refs/heads/"+branch in block.splitlines() for block in listed),"worktree_registration_mismatch")
    need(c["branch"]==branch==git(wt,"branch","--show-current").decode().strip()
         and re.fullmatch(r"[0-9a-f]{40}",c["head"] or "")
         and c["head"]==git(wt,"rev-parse","HEAD").decode().strip(),"branch_or_head_drift")
    if session:
        current=Path(wt)
        for part in (".claude","agent-sessions",session):
            current=current/part;need(not current.is_symlink(),"session_directory_untrusted")
        need(re.fullmatch(r"[A-Za-z0-9_.-]+",session) is not None,"session_name_invalid")
        need(not git(wt,"ls-files","--", ".claude/agent-sessions/"+session),"session_path_already_tracked")
    excluded=session if owner_pid and not initial else ""
    need(c["dirty_sha256"]==dirty(wt,excluded),"dirty_snapshot_drift")
    sessions=Path(wt)/".claude"/"agent-sessions"
    if sessions.exists():
        need(not sessions.is_symlink(),"session_directory_untrusted")
        need(not any(p.name!=session or initial or not owner_pid for p in sessions.iterdir()),"existing_mao_session_requires_recovery")
    record=None
    if owner_pid:
        _,lock=paths(wt);record=json.loads(read(str(lock/"owner.json")))
        need(record.get("owner_pid")==owner_pid and record.get("session")==session and record.get("contract_sha256")==digest(raw) and record.get("initial_session_absent") is True,"borrow_lock_mismatch")
        need(record.get("owner_started")==run(["ps","-p",str(owner_pid),"-o","lstart="]).decode().strip(),"borrow_lock_owner_gone")
        need(isinstance(record.get("initial_pids"),list) and all(isinstance(pid,int) and pid>0 for pid in record["initial_pids"]),"borrow_lock_inventory_unknown")
    runtime(c,binary,terminal)
    launcher_parent_pid=launcher_parent_pid or globals().get("_VERIFIED_FROZEN_LAUNCH_PARENT_PID",0)
    if launcher_parent_pid:
        need(bool(record) and terminal and os.environ.get("ORCA_TERMINAL_HANDLE")==terminal
             and os.environ.get("ORCA_WORKTREE_ID")==c["orca_worktree_id"],"launcher_identity_unknown")
        live_terminal=rpc(binary,"terminal","show","--terminal",terminal).get("result",{}).get("terminal",{})
        need(live_terminal.get("handle")==terminal and live_terminal.get("worktreeId")==c["orca_worktree_id"]
             and live_terminal.get("connected") is True,"launcher_identity_unknown")
    observed=no_writer(wt,owner_pid or initial_controller_pid,record["initial_pids"] if record else None,launcher_parent_pid)
    if process_observation is not None:process_observation["pids"]=observed
    return c

def acquire(a):
    need(a.owner_pid>0 and bool(a.session),"borrow_owner_required")
    observation={}
    c=validate(a.contract,a.project,a.worktree,a.branch,a.orca_bin,a.session,initial=True,initial_controller_pid=a.owner_pid,process_observation=observation)
    marker,lock=paths(c["worktree"]);directory(lock.parent);directory(marker.parent)
    try:lock.mkdir(mode=0o700)
    except FileExistsError:raise Refused("borrow_lock_contended")
    try:
        record={"owner_pid":a.owner_pid,"owner_started":run(["ps","-p",str(a.owner_pid),"-o","lstart="]).decode().strip(),"session":a.session,"contract_sha256":digest(read(a.contract)),"initial_session_absent":True,"initial_pids":observation["pids"]}
        need(record["owner_started"],"borrow_lock_owner_unknown");write(lock/"owner.json",record)
        validate(a.contract,a.project,a.worktree,a.branch,a.orca_bin,a.session,a.owner_pid,initial=True)
        if marker.exists():need(protected(a.project,a.worktree,a.branch),"ownership_unknown_retain")
        else:
            reserve=marker.with_suffix(".reserved")
            need(not reserve.exists(),"ownership_ledger_missing_retain")
            write(reserve,{"schema":SCHEMA,"worktree":c["worktree"],"ownership":"borrowed"})
            write(marker,dict(c,ownership="borrowed"))
    except Exception:
        (lock/"owner.json").unlink(missing_ok=True);lock.rmdir();raise
    return dict(c,ok=True,contract_sha256=record["contract_sha256"],ownership="borrowed")

def release(a):
    _,lock=paths(canonical(a.worktree))
    record=json.loads(read(str(lock/"owner.json")))
    need(record.get("owner_pid")==a.owner_pid and record.get("session")==a.session,"borrow_lock_mismatch")
    (lock/"owner.json").unlink();lock.rmdir()
    return {"ok":True,"ownership_retained":True}

def main():
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest="action",required=True)
    for action in ("snapshot","validate","acquire"):
        q=subs.add_parser(action)
        for key in ("project","worktree","branch","orca-bin"):q.add_argument("--"+key,required=True)
        q.add_argument("--session",default="");q.add_argument("--owner-pid",type=int,default=0);q.add_argument("--terminal",default="")
        if action=="snapshot":
            for key in ("orca-worktree-id","runtime-id","approved-by"):q.add_argument("--"+key,required=True)
        else:q.add_argument("--contract",required=True)
    q=subs.add_parser("release")
    for key in ("worktree","session"):q.add_argument("--"+key,required=True)
    q.add_argument("--owner-pid",type=int,required=True)
    q=subs.add_parser("protect")
    for key in ("project","worktree","branch"):q.add_argument("--"+key,required=True)
    a=p.parse_args()
    try:
        if a.action=="snapshot":
            wt=canonical(a.worktree);out=dict(schema=SCHEMA,project=canonical(a.project),common_dir=common(wt),worktree=wt,branch=a.branch,head=git(wt,"rev-parse","HEAD").decode().strip(),dirty_sha256=dirty(wt),orca_worktree_id=a.orca_worktree_id,runtime_id=a.runtime_id,approved_by=a.approved_by,created_at=time.time())
            no_writer(wt);runtime(out,a.orca_bin)
        elif a.action=="acquire":out=acquire(a)
        elif a.action=="release":out=release(a)
        elif a.action=="protect":out={"ok":True,"protected":protected(a.project,a.worktree,a.branch)}
        else:out=dict(validate(a.contract,a.project,a.worktree,a.branch,a.orca_bin,a.session,a.owner_pid,a.terminal),ok=True)
        print(json.dumps(out,sort_keys=True))
    except Refused as e:print(json.dumps({"ok":False,"error":str(e),"resources_retained":True}),file=sys.stderr);raise SystemExit(64)
    except (OSError,ValueError,KeyError,TypeError,AttributeError):print(json.dumps({"ok":False,"error":"borrow_contract_unknown","resources_retained":True}),file=sys.stderr);raise SystemExit(64)
if __name__=="__main__":main()
