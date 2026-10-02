#!/usr/bin/env python3
"""Opt-in, single-use PM launch bridge for Orca's native interactive ZCode agent.

The same OS user controls these receipts: this is an identity/TOCTOU boundary,
not a sandbox against that user. No credential files or account settings are read.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import time
import uuid
from completion_authority import load_authority

SCHEMA = "multi-agent-orchestration.zcode-launch-request.v1"
LIMIT = 1024 * 1024

class Rejected(ValueError):
    pass

def require(condition, reason):
    if not condition:
        raise Rejected(reason)

def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result

def decode(raw):
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(Rejected("nonfinite_json")))

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def trusted_path(text):
    p = Path(text)
    require(p.is_absolute() and ".." not in p.parts, "absolute_path_required")
    # /tmp and /var are macOS system aliases; no user-controlled ancestor alias.
    if p.parts[1:2] in (("tmp",), ("var",)):
        p = Path("/private") / p.relative_to("/")
    current = Path("/")
    for part in p.parts[1:]:
        current = current / part
        require(not current.is_symlink(), "symlink_path")
    return p

def read_file(text, private=False):
    p = trusted_path(text)
    fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        s = os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid()
                and not s.st_mode & 0o022 and s.st_size <= LIMIT, "untrusted_file")
        if private:
            require(stat.S_IMODE(s.st_mode) == 0o600, "manifest_mode")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(LIMIT + 1)
        require(len(raw) <= LIMIT, "oversize_file")
        return raw
    finally:
        os.close(fd)

def request_root(text):
    p = trusted_path(text)
    require(p.is_dir(), "requests_root_missing")
    s = p.stat()
    require(s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == 0o700, "requests_root_permissions")
    return p

def version_ok(value):
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[-+][A-Za-z0-9.-]+)?", value or "")
    require(m is not None and tuple(map(int, m.groups())) >= (1, 4, 218), "native_version_unsupported")

def cli(binary, *args):
    require(os.path.isabs(binary) and os.access(binary, os.X_OK), "orca_binary_invalid")
    try:
        out = subprocess.run([binary, *args, "--json"], capture_output=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        raise Rejected("orca_read_failed")
    require(out.returncode == 0, "orca_read_failed")
    value = decode(out.stdout)
    require(isinstance(value, dict) and value.get("ok") is True, "orca_response_invalid")
    return value

def live(req, terminal=""):
    binary = req["orca_bin"]
    status = cli(binary, "status")
    runtime = status.get("result", {}).get("runtime", {})
    version_ok(runtime.get("appVersion"))
    require(runtime.get("reachable") is True and runtime.get("runtimeId") == req["runtime_id"], "runtime_drift")
    wt = cli(binary, "worktree", "show", "--worktree", "id:" + req["worktree_id"]).get("result", {}).get("worktree", {})
    require(wt.get("id") == req["worktree_id"] and Path(wt.get("path", "")).resolve() == Path(req["worktree"]), "worktree_drift")
    if terminal:
        # A native PTY may exec before its preallocated handle is registered.
        for attempt in range(4):
            try:
                t = cli(binary, "terminal", "show", "--terminal", terminal).get("result", {}).get("terminal", {})
                require(t.get("handle") == terminal and t.get("worktreeId") == req["worktree_id"], "terminal_identity_mismatch")
                return
            except Rejected:
                if attempt == 3:
                    raise
                time.sleep(0.1)

def git(worktree, *args):
    p = subprocess.run(["git", "-C", worktree, *args], capture_output=True, timeout=8)
    require(p.returncode == 0, "git_identity_unavailable")
    return p.stdout.decode().strip()

def interactive_command(command, depth=0):
    require(depth <= 4 and "`" not in command and "$(" not in command, "command_unproven")
    try:
        words = shlex.split(command)
    except ValueError:
        raise Rejected("command_unproven")
    # Only inspect actual argv, never an environment value containing --prompt.
    while words and (words[0] == "env" or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=",words[0])):
        if words[0] == "env":
            words.pop(0)
        while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=",words[0]):
            words.pop(0)
    require(bool(words), "command_unproven")
    name=Path(words[0]).name
    if name in ("bash","sh","zsh"):
        require(len(words)==3 and words[1] in ("-c","-lc","-cl"), "command_unproven")
        return interactive_command(words[2],depth+1)
    require(name == "zcode", "command_unproven")
    require(not any(x in ("--prompt","-p","--headless","--print","--output-format","app-server","agent-server")
                    or x.startswith(("--prompt=","--headless=","--print=","--output-format=")) for x in words[1:]), "headless_not_allowed")

def validate(req, check_borrowed=True):
    require(req.get("schema") == SCHEMA and isinstance(req.get("nonce"),str)
            and str(uuid.UUID(req["nonce"])) == req["nonce"], "request_schema")
    require(isinstance(req.get("expires_at"), (int, float)) and time.time() <= req["expires_at"]
            and 0 < req["expires_at"] - req["created_at"] <= 120, "request_expired")
    raw = read_file(req["metadata"])
    require(sha(raw) == req["metadata_sha256"], "metadata_changed")
    m = decode(raw)
    require(m.get("schema") == "multi-agent-orchestration.worktree-metadata.v1", "metadata_schema")
    s, runtime, authority = m["session"], m["runtime"], m["execution_authority"]
    wt = Path(m["worktree"]).resolve(strict=True)
    require(str(wt) == req["worktree"] and s["id"] == req["session"], "session_identity_mismatch")
    context = wt / ".claude" / "agent-sessions" / s["id"]
    require(Path(s["context"]) == context and Path(req["metadata"]) == context / "METADATA.json"
            and Path(req["launch"]) == context / "launch.sh", "context_identity_mismatch")
    current = wt
    for part in (".claude", "agent-sessions", s["id"]):
        current = current / part
        require(not current.is_symlink(), "context_symlink")
    require(s["orca"]["worktree_id"] == req["worktree_id"] and s["orca"]["runtime_id"] == req["runtime_id"]
            and not s["orca"].get("terminal_handle"), "pending_metadata_identity")
    require(runtime.get("worker_backend") == "zcode-cli"
            and runtime.get("harness_authority", {}).get("worker_backend") == "zcode-cli", "backend_mismatch")
    command = runtime["command"]
    require(isinstance(command, str) and sha(command.encode()) == req["command_sha256"], "command_changed")
    interactive_command(command)
    require(authority["authority_receipt_file"] == req["authority"], "authority_mismatch")
    a, digest = load_authority(req["authority"], req["authority_sha256"])
    require(authority["authority_receipt_sha256"] == digest and a.get("session") == req["session"]
            and Path(a.get("worktree", "")).resolve() == wt and a.get("branch") == m["branch"], "authority_identity_mismatch")
    # Native Task injection may complete an authorized commit before bind returns.
    # Keep branch/authority/receipt identity; never replay the borrowed prelaunch
    # HEAD or dirty snapshot after the worker has begun executing the Task.
    require(git(str(wt), "branch", "--show-current") == req["branch"]
            and (not check_borrowed and req.get("worktree_ownership") == "borrowed"
                 or git(str(wt), "rev-parse", "HEAD") == req["head"]), "git_identity_changed")
    launch = read_file(req["launch"])
    require(sha(launch) == req["launch_sha256"] and launch.startswith(b"#!/bin/bash\n")
            and stat.S_IMODE(Path(req["launch"]).stat().st_mode) == 0o700, "launch_changed")
    quoted=subprocess.run(["/bin/bash","--noprofile","--norc","-c",'printf %q "$1"',"_",command],capture_output=True,check=True).stdout
    # PM generated wrapper must execute precisely the frozen full command.
    require(launch.splitlines()[-1] == b"exec bash -c " + quoted, "launch_command_mismatch")
    if m.get("worktree_ownership") == "borrowed" and check_borrowed:
        binding=m["borrowed_worktree"]
        approved=json.loads(read_file(binding["contract_file"]))
        require(approved["approved_by"] == a.get("degradation_source"), "borrowed_authority_source_mismatch")
        require(sha(read_file(binding["contract_file"])) == binding["contract_sha256"], "borrowed_contract_changed")
        # The digest is inside authority-bound frozen launch bytes. Never import
        # mutable helper code first, or verify one read then execute a second.
        expected=re.findall(rb"^# borrowed-helper-sha256: ([0-9a-f]{64})$",launch,re.MULTILINE)
        require(len(expected)==1,"borrowed_helper_binding_missing")
        helper_path=Path(__file__).with_name("borrowed-worktree.py")
        helper_buffer=read_file(str(helper_path))
        require(sha(helper_buffer)==expected[0].decode(),"borrowed_helper_changed")
        import types
        module=types.ModuleType("mao_borrowed_worktree");module.__file__=str(helper_path)
        exec(compile(helper_buffer,str(helper_path),"exec"),module.__dict__)
        try:
            module.validate(binding["contract_file"],m["project"],str(wt),m["branch"],req["orca_bin"],
                            req["session"],binding["lock_owner_pid"],os.environ.get("ORCA_TERMINAL_HANDLE", ""),
                            launcher_parent_pid=os.getppid() if req.get("state") in ("pending","claimed") and os.environ.get("ORCA_WORKTREE_ID")==req["worktree_id"] else 0)
        except (module.Refused,OSError,ValueError,KeyError,TypeError,AttributeError):
            raise Rejected("borrowed_late_gate_refused")
    return launch

def manifests(root):
    files = sorted(root.glob("*.json"))
    # Bound tombstones retain replay fencing without exhausting the active limit.
    require(sum(not p.name.endswith(".bound.json") for p in files) <= 128, "request_inventory_limit")
    result = []
    for p in files:
        require(re.fullmatch(r"[0-9a-f-]{36}\.(?:request|claimed|bound)\.json", p.name) is not None, "unexpected_manifest")
        r = decode(read_file(str(p), private=True))
        require(isinstance(r, dict) and r.get("schema") == SCHEMA
                and p.name.split(".")[0] == r.get("nonce")
                and str(uuid.UUID(r["nonce"])) == r["nonce"], "request_schema")
        expected_state={"request":"pending","claimed":"claimed","bound":"bound"}[p.name.split(".")[1]]
        require(r.get("state") == expected_state, "request_state_mismatch")
        result.append((p, r))
    return result

def lock(root):
    p = root / ".claim.lock"
    fd = os.open(p, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    s = os.fstat(fd)
    require(stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == 0o600, "lock_untrusted")
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd

def write(p, value, exclusive=False):
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(p, flags, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())

def prepare(a):
    root = request_root(a.requests_root)
    raw = read_file(a.metadata)
    m = decode(raw)
    wt = str(Path(m["worktree"]).resolve(strict=True))
    authority, digest = load_authority(a.authority)
    context = Path(m["session"]["context"])
    created = time.time()
    r = dict(schema=SCHEMA, nonce=str(uuid.uuid4()), state="pending", created_at=created,
             expires_at=created+a.ttl_seconds, metadata=str(trusted_path(a.metadata)), metadata_sha256=sha(raw),
             launch=str(context/"launch.sh"), launch_sha256=sha(read_file(str(context/"launch.sh"))),
             command_sha256=sha(m["runtime"]["command"].encode()), authority=str(trusted_path(a.authority)),
             authority_sha256=digest, worktree=wt, worktree_id=a.worktree_id, runtime_id=a.runtime_id,
             session=m["session"]["id"], branch=m["branch"], head=git(wt,"rev-parse","HEAD"),
             orca_bin=str(Path(a.orca_bin).resolve(strict=True)), run_id=a.run_id, task_id=a.task_id,
             coordinator_handle=a.coordinator_handle, worktree_ownership=m.get("worktree_ownership","created"))
    require(1 <= a.ttl_seconds <= 120 and all((a.runtime_id,a.worktree_id,a.run_id,a.task_id,a.coordinator_handle)), "request_parameters")
    validate(r)
    live(r)
    fd = lock(root)
    try:
        existing=[old for _,old in manifests(root) if old["worktree"] == wt]
        require(not any(old["state"] != "bound" for old in existing), "pending_request_exists")
        require(not any(old["session"] == r["session"] for old in existing), "session_already_consumed")
        path = root / (r["nonce"]+".request.json")
        write(path,r,exclusive=True)
    finally:
        os.close(fd)
    return {"ok":True,"request_file":str(path)}

def launch(a):
    root = request_root(a.requests_root)
    native_args = a.native_args[1:] if a.native_args[:1] == ["--"] else a.native_args
    fd = lock(root)
    try:
        cwd = str(Path.cwd().resolve())
        matching = [(p,r) for p,r in manifests(root) if r.get("worktree") == cwd]
        candidates = [(p,r) for p,r in matching if r["state"] != "bound"]
        if not candidates:
            require(not matching, "request_already_consumed")
            require(os.path.isabs(a.default_zcode) and os.access(a.default_zcode,os.X_OK), "default_zcode_invalid")
            os.close(fd)
            fd = -1
            os.execv(a.default_zcode,[a.default_zcode,*native_args])
        require(len(candidates) == 1, "ambiguous_request")
        p,r = candidates[0]
        require(r.get("state") == "pending" and p.name.endswith(".request.json"), "request_already_claimed")
        require(not any(x == "--prompt" or x.startswith("--prompt=") or x == "--headless" or x.startswith("--headless=") for x in native_args), "headless_not_allowed")
        terminal = os.environ.get("ORCA_TERMINAL_HANDLE", "")
        require(terminal and os.environ.get("ORCA_WORKTREE_ID") == r["worktree_id"], "orca_environment_missing")
        launch_bytes = validate(r)
        live(r,terminal)
        claimed = root / (r["nonce"]+".claimed.json")
        require(not claimed.exists(), "request_already_claimed")
        os.rename(p,claimed)
        r.update(state="claimed", terminal_handle=terminal, claimed_at=time.time(), launcher_pid=os.getpid())
        write(claimed,r)
        # Freeze verified bytes rather than reopening a worktree-controlled script.
        validate(r)
    finally:
        if fd >= 0:
            os.close(fd)
    os.execve("/bin/bash",["/bin/bash","-c",launch_bytes.decode()],dict(os.environ))

def bind(a):
    root=request_root(a.requests_root)
    original=trusted_path(a.request_file) if Path(a.request_file).exists() else Path(a.request_file)
    require(original.parent.resolve() == root and re.fullmatch(r"[0-9a-f-]{36}\.request\.json",original.name),"request_path_invalid")
    claimed=root/(original.name.replace(".request.json",".claimed.json"))
    fd=lock(root)
    try:
        r=decode(read_file(str(claimed),private=True))
        require(r.get("state")=="claimed","request_not_claimed")
        validate(r,check_borrowed=False)
        receipt=decode(read_file(a.receipt))
        result=receipt.get("result",{})
        require(result.get("state") == "ready", "native_receipt_not_ready")
        require(receipt.get("ok") is True and receipt.get("_meta",{}).get("runtimeId")==r["runtime_id"]
                and result.get("runId")==r["run_id"] and result.get("taskId")==r["task_id"]
                and isinstance(result.get("dispatchId"),str) and result["dispatchId"],"native_receipt_identity")
        effects=result.get("effects",[])
        require(isinstance(effects,list) and all(isinstance(e,dict) for e in effects),"native_effects_unknown")
        if r.get("worktree_ownership") == "borrowed":
            worktrees=[e for e in effects if e.get("kind")=="worktree"]
            require(len(worktrees)==1 and worktrees[0].get("id")==r["worktree_id"]
                    and worktrees[0].get("action")=="reused","borrowed_native_worktree_ownership_unknown")
        terminals=[e for e in effects if e.get("kind")=="terminal" and e.get("role")=="agent" and e.get("action")=="created"]
        require(len(terminals)==1 and terminals[0].get("id")==r["terminal_handle"],"native_receipt_terminal_mismatch")
        require(any(e.get("kind")=="worktree" and e.get("id")==r["worktree_id"] and e.get("action")=="reused" for e in effects),"native_receipt_worktree_mismatch")
        live(r,r["terminal_handle"])
        r.update(state="bound",dispatch_id=result["dispatchId"],bound_at=time.time())
        dest=root/(r["nonce"]+".bound.json")
        write(dest,r,exclusive=True)
        claimed.unlink()
        return {"ok":True,"terminal_handle":r["terminal_handle"],"terminal_ownership":"created"}
    finally:
        os.close(fd)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    subs=p.add_subparsers(dest="action",required=True)
    pre=subs.add_parser("preflight"); pre.add_argument("--requests-root",required=True); pre.add_argument("--app-version",required=True)
    prep=subs.add_parser("prepare")
    for key in ("requests-root","metadata","authority","orca-bin","runtime-id","worktree-id","run-id","task-id","coordinator-handle"):
        prep.add_argument("--"+key,required=True)
    prep.add_argument("--ttl-seconds",type=int,default=120)
    la=subs.add_parser("launch"); la.add_argument("--requests-root",required=True); la.add_argument("--default-zcode",required=True); la.add_argument("native_args",nargs=argparse.REMAINDER)
    bi=subs.add_parser("bind-receipt")
    for key in ("requests-root","request-file","receipt"): bi.add_argument("--"+key,required=True)
    resume=subs.add_parser("resume-exec", help="Explicit closed recovery runner; first-start request path is unchanged")
    resume.add_argument("--intent",required=True)
    a=p.parse_args()
    try:
        if a.action=="resume-exec":
            from zcode_closed_recovery import resume_exec
            resume_exec(a.intent)
            return
        if a.action=="preflight": request_root(a.requests_root); version_ok(a.app_version); out={"ok":True}
        elif a.action=="prepare": out=prepare(a)
        elif a.action=="launch": launch(a); return
        else: out=bind(a)
        print(json.dumps(out,sort_keys=True))
    except Rejected as error:
        print(json.dumps({"ok":False,"error":str(error)}),file=sys.stderr)
        raise SystemExit(64)
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError):
        # Never print raw command/env, credential-like fields or external stderr.
        print(json.dumps({"ok":False,"error":"launch_contract_rejected"}),file=sys.stderr)
        raise SystemExit(64)

if __name__=="__main__": main()
