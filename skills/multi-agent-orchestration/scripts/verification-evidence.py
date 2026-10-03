#!/usr/bin/env python3
"""Collect/check scoped engineering verification; never attest role or completion.

Run exact simple argv commands from a valid dispatch spec in a clean pinned Git
checkout. Keep logs in a new private directory outside that checkout. All dirty,
untracked and ignored content is refused: ignoring files is not source proof.
This is a same-user integrity receipt, not a signature against its OS owner.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import shutil
import signal
import stat
import subprocess
import time

SCHEMA = "multi-agent-orchestration.verification-evidence.v1"
MAX_JSON = 2 * 1024 * 1024
MAX_FILES = 20000
SHA = re.compile(r"[0-9a-f]{40}")

class Refused(ValueError):
    pass

def require(ok, reason):
    if not ok: raise Refused(reason)

def sha(data): return hashlib.sha256(data).hexdigest()

def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()

def file_identity(path):
    p = Path(path); st = p.stat()
    return {"path": str(p), "sha256": file_sha(p), "device": st.st_dev,
            "inode": st.st_ino, "mtime_ns": st.st_mtime_ns, "ctime_ns": st.st_ctime_ns,
            "size": st.st_size, "mode": st.st_mode}

def resolved_binary(argv):
    binary = shutil.which(argv[0]) if not Path(argv[0]).is_absolute() else argv[0]
    require(binary is not None, "verification_executable_missing")
    return Path(binary).resolve(strict=True)

def command_inputs(command, repo):
    argv = command_argv(command); inputs = []
    require(not any(os.environ.get(k) for k in ("PYTHONPATH", "PYTHONHOME", "BASH_ENV", "ENV", "NODE_OPTIONS", "RUBYOPT", "PERL5OPT", "LD_PRELOAD", "DYLD_INSERT_LIBRARIES")), "injected_runtime_environment_refused")
    for arg in argv[1:]:
        candidate = Path(arg) if Path(arg).is_absolute() else repo / arg
        if candidate.is_file():
            require(not candidate.is_symlink(), "input_alias_refused")
            inputs.append(file_identity(candidate.resolve(strict=True)))
    return inputs

def read_json(path):
    p = Path(path)
    require(not p.is_symlink() and p.is_file() and p.stat().st_size <= MAX_JSON, "json_path_refused")
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, "duplicate_json_key")
            out[key] = value
        return out
    raw = p.read_bytes()
    value = json.loads(raw, object_pairs_hook=pairs)
    require(isinstance(value, dict), "json_object_required")
    return value, sha(raw)

def write_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, sort_keys=True, ensure_ascii=False)
        f.write("\n"); f.flush(); os.fsync(f.fileno())

def git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=15)
    require(p.returncode == 0 and len(p.stdout) <= MAX_JSON, "git_observation_failed")
    return p.stdout

def source_binding(repo, head):
    require(SHA.fullmatch(head) is not None, "immutable_head_required")
    require(repo.is_dir() and git(repo, "rev-parse", "--show-toplevel").decode().strip() == str(repo), "canonical_git_root_required")
    require(git(repo, "rev-parse", "HEAD").decode().strip() == head, "head_changed")
    require(not git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored=matching"), "dirty_untracked_or_ignored_content")
    entries = git(repo, "ls-files", "--stage", "-z").split(b"\0")
    require(1 < len(entries) <= MAX_FILES + 1, "source_inventory_limit")
    digest = hashlib.sha256()
    for row in entries[:-1]:
        header, rawpath = row.split(b"\t", 1)
        mode, blob, stage = header.split()
        require(stage == b"0" and mode in (b"100644", b"100755"), "unsupported_source_entry")
        relative = os.fsdecode(rawpath); p = repo / relative
        require(not Path(relative).is_absolute() and ".." not in Path(relative).parts and p.resolve(strict=True) == p and p.is_file(), "source_alias_refused")
        require(bool(p.stat().st_mode & 0o111) == (mode == b"100755"), "source_mode_differ_from_index")
        # Do not trust Git's assume-unchanged/skip-worktree status shortcuts.
        actual_blob = git(repo, "hash-object", "--no-filters", "--", relative).strip()
        require(actual_blob == blob, "source_bytes_differ_from_index")
        digest.update(row + b"\0")
        digest.update(json.dumps(file_identity(p), sort_keys=True).encode() + b"\0")
        with p.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""): digest.update(block)
        digest.update(b"\0")
    return {"sha256": digest.hexdigest(), "tracked_files": len(entries) - 1}

def command_argv(command):
    require(isinstance(command, str) and command.strip() and len(command) <= 4096, "command_required")
    require(not any(c in command for c in "\r\n;$`|&<>"), "complex_shell_refused")
    argv = shlex.split(command)
    require(argv and not any(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", v) for v in argv), "environment_assignment_refused")
    name = resolved_binary(argv).name
    is_python = re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", name) is not None
    require(name not in ("env", "eval", "exec", "source", ".", "sudo"), "command_wrapper_refused")
    if is_python or name in ("sh", "bash", "zsh", "dash", "fish", "node", "perl", "ruby"):
        require(not any(v in ("-c", "-e", "--eval", "--command") or v.startswith(("--eval=", "--command=", "-c", "-e")) for v in argv[1:]), "inline_interpreter_refused")
    if name in ("sh", "bash", "zsh", "dash", "fish"):
        require(not any(v.startswith("-") and not v.startswith("--") and "c" in v[1:] for v in argv[1:]), "inline_shell_refused")
    return argv

def binding(spec, task_id, repo, head):
    data, spec_sha = read_json(spec)
    loader = importlib.util.spec_from_file_location("evidence_value_gate", Path(__file__).with_name("dispatch-value-gate.py"))
    gate = importlib.util.module_from_spec(loader); loader.loader.exec_module(gate)
    require(not gate.validate(data, datetime.now(timezone.utc)), "dispatch_spec_refused")
    tasks = [t for t in data["tasks"] if t.get("task_id") == task_id]
    require(len(tasks) == 1 and tasks[0].get("value_kind") in ("implementation", "reusable_verification"), "engineering_task_required")
    task = tasks[0]
    require(task.get("starts_external_resources") is False, "external_resources_not_supported")
    commands = task.get("verification_commands")
    require(isinstance(commands, list) and 0 < len(commands) <= 16 and len(set(commands)) == len(commands), "scoped_commands_required")
    inputs = {command: command_inputs(command, repo) for command in commands}
    return {"spec_path": str(spec), "spec_sha256": spec_sha, "task_id": task_id,
            "value_kind": task["value_kind"], "repo": str(repo), "verified_head": head,
            "source": source_binding(repo, head), "command_inputs": inputs}, commands

def group_members(pgid):
    p = subprocess.run(['/bin/ps', '-axo', 'pid=,pgid=,stat='], capture_output=True, text=True, timeout=5)
    require(p.returncode == 0 and len(p.stdout) <= MAX_JSON, 'group_observation_failed')
    return [int(fields[0]) for line in p.stdout.splitlines() if len(fields := line.split()) == 3 and fields[1] == str(pgid) and not fields[2].startswith('Z')]

def private_root(root, repo, create=False):
    require(root.is_absolute() and root.parent.resolve(strict=True) == root.parent and not root.is_symlink(), "output_alias_refused")
    require(root != repo and repo not in root.parents, "output_must_be_outside_checkout")
    if create: root.mkdir(mode=0o700)
    st = root.stat()
    require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid() and stat.S_IMODE(st.st_mode) == 0o700, "private_output_directory_required")

def run_command(command, repo, root, index, timeout, limit):
    paths = [root / f"{index:02d}.stdout.log", root / f"{index:02d}.stderr.log"]
    streams = [os.fdopen(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") for p in paths]
    started = datetime.now(timezone.utc).isoformat(); start = time.monotonic()
    proc = None; selector = selectors.DefaultSelector(); total = 0; incomplete = None
    executable = None
    try:
        # No shell, injected argv, caller exit codes, or result self-report.
        argv = command_argv(command)
        binary_path = resolved_binary(argv)
        executable = {"path": str(binary_path), "sha256": file_sha(binary_path)}
        proc = subprocess.Popen(argv, executable=str(binary_path), cwd=repo, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        for i, pipe in enumerate((proc.stdout, proc.stderr)):
            os.set_blocking(pipe.fileno(), False); selector.register(pipe, selectors.EVENT_READ, i)
        while selector.get_map():
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0: incomplete = "timeout"; break
            for key, _ in selector.select(min(remaining, .1)):
                block = os.read(key.fileobj.fileno(), 65536)
                if not block: selector.unregister(key.fileobj); continue
                available = limit - total
                streams[key.data].write(block[:available]); total += min(len(block), available)
                if len(block) > available: incomplete = "log_limit"; break
            if incomplete: break
        if incomplete:
            os.killpg(proc.pid, signal.SIGKILL)
        try: code = proc.wait(timeout=max(.1, timeout - (time.monotonic() - start)))
        except subprocess.TimeoutExpired:
            incomplete = "timeout"; os.killpg(proc.pid, signal.SIGKILL); code = proc.wait(timeout=5)
    except (OSError, ValueError):
        incomplete = "execution_error"; code = None
    finally:
        if proc is not None:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait(timeout=5)
            try:
                if group_members(proc.pid):
                    incomplete = incomplete or "background_processes"
                    os.killpg(proc.pid, signal.SIGKILL)
                    for _ in range(10):
                        if not group_members(proc.pid): break
                        time.sleep(.05)
                    else: incomplete = "cleanup_unknown"
            except (ValueError, OSError, subprocess.SubprocessError):
                incomplete = "cleanup_unknown"
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            for pipe in (proc.stdout, proc.stderr): pipe.close()
        selector.close()
        for f in streams: f.flush(); os.fsync(f.fileno()); f.close()
    return {"command": command, "exit_code": code, "started_at": started,
            "elapsed_seconds": round(time.monotonic() - start, 6), "complete": incomplete is None,
            "failure": incomplete, "executable": executable, "logs": [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha(p.read_bytes())} for p in paths]}

def collect(args):
    bound, commands = binding(args.spec, args.task_id, args.repo, args.head)
    private_root(args.output_dir, args.repo, create=True)
    results = []; failure = None
    for index, command in enumerate(commands):
        result = run_command(command, args.repo, args.output_dir, index, args.timeout_seconds, args.max_log_bytes)
        results.append(result)
        if result["exit_code"] != 0 or not result["complete"]:
            failure = result["failure"] or "nonzero_exit"; break
        try:
            current, _ = binding(args.spec, args.task_id, args.repo, args.head)
            require(current == bound, "binding_changed")
        except (ValueError, OSError, subprocess.SubprocessError): failure = "binding_changed"; break
    evidence = {"schema": SCHEMA, **bound, "executed": results,
                "timeout_seconds": args.timeout_seconds, "max_log_bytes": args.max_log_bytes,
                "collector_sha256": sha(Path(__file__).read_bytes()), "usable_for_postflight": failure is None,
                "task_complete": False, "reviewer_attestation": False, "failure": failure}
    write_json(args.output_dir / "attempt.json", evidence)
    if failure is None: write_json(args.output_dir / "postflight-evidence.json", evidence)
    return {"ok": failure is None, "usable_for_postflight": failure is None, "task_complete": False,
            "attempt": str(args.output_dir / "attempt.json"), "evidence": str(args.output_dir / "postflight-evidence.json") if failure is None else None,
            "failure": failure}

def check(args):
    evidence, _ = read_json(args.evidence)
    private_root(args.evidence.parent, args.repo)
    bound, commands = binding(args.spec, args.task_id, args.repo, args.head)
    require(evidence.get("schema") == SCHEMA and evidence.get("usable_for_postflight") is True and evidence.get("failure") is None, "unusable_evidence")
    require(all(evidence.get(k) == v for k, v in bound.items()), "evidence_binding_changed")
    require(evidence.get("collector_sha256") == sha(Path(__file__).read_bytes()), "collector_changed")
    rows = evidence.get("executed")
    require(isinstance(rows, list) and len(rows) == len(commands), "command_receipts_missing")
    for index, (row, command) in enumerate(zip(rows, commands)):
        require(row.get("command") == command and type(row.get("exit_code")) is int and row["exit_code"] == 0 and row.get("complete") is True and row.get("failure") is None, "command_receipt_refused")
        executable = row.get("executable")
        argv = command_argv(command)
        resolved = shutil.which(argv[0]) if not Path(argv[0]).is_absolute() else argv[0]
        require(isinstance(executable, dict) and resolved is not None and str(Path(resolved).resolve(strict=True)) == executable.get("path") and file_sha(executable["path"]) == executable.get("sha256"), "executable_changed")
        logs = row.get("logs")
        require(isinstance(logs, list) and len(logs) == 2, "incomplete_logs")
        for stream, receipt in zip(("stdout", "stderr"), logs):
            name = f"{index:02d}.{stream}.log"; p = args.evidence.parent / name
            require(receipt.get("name") == name and not p.is_symlink(), "log_alias_refused")
            st = p.stat(); require(stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and stat.S_IMODE(st.st_mode) == 0o600 and st.st_size <= args.max_log_bytes, "log_permissions_or_size")
            require(st.st_size == receipt.get("bytes") and sha(p.read_bytes()) == receipt.get("sha256"), "log_changed")
    return {"ok": True, "usable_for_postflight": True, "task_complete": False, "reviewer_attestation": False, "evidence": str(args.evidence)}

def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="action", required=True)
    for action in ("collect", "check"):
        p = sub.add_parser(action)
        p.add_argument("--spec", type=Path, required=True); p.add_argument("--task-id", required=True)
        p.add_argument("--repo", type=Path, required=True); p.add_argument("--head", required=True)
        p.add_argument("--max-log-bytes", type=int, default=128 * 1024)
        if action == "collect":
            p.add_argument("--output-dir", type=Path, required=True); p.add_argument("--timeout-seconds", type=float, default=300)
        else: p.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    try:
        args.repo = args.repo.resolve(strict=True); args.spec = args.spec.resolve(strict=True)
        require(1024 <= args.max_log_bytes <= 1024 * 1024, "log_limit_refused")
        if args.action == "collect":
            require(0 < args.timeout_seconds <= 1800, "timeout_limit_refused")
            args.output_dir = args.output_dir.absolute()
            out = collect(args)
        else:
            require(not args.evidence.is_symlink(), "evidence_alias_refused"); args.evidence = args.evidence.resolve(strict=True)
            out = check(args)
        print(json.dumps(out, sort_keys=True)); return 0 if out["ok"] else 2
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError):
        # Never echo a command, raw log, exception payload or credential value.
        print(json.dumps({"ok": False, "usable_for_postflight": False, "task_complete": False, "error": "verification_evidence_refused"})); return 2

if __name__ == "__main__": raise SystemExit(main())
