#!/usr/bin/env python3
"""Serialize this helper's Orca registration attempts for one Git common-dir.

Only an explicit selector_not_found permits registration. The lock covers the
second lookup, repo add and exact post-add identity check. No stale-lock removal,
other-client coordination or duplicate-repository cleanup is attempted.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from typing import Any


LOCK_NAME = "mao-orca-register.lock"
REPO_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
PENDING_SCHEMA = "multi-agent-orchestration.orca-registration-pending.v1"


class RegistrationError(Exception):
    def __init__(self, reason: str, code: int = 1):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def text_identity(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and not any(c in value for c in "\x00\r\n")


def invoke(argv: list[str], cwd: Path, timeout: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RegistrationError("cli_timeout", 75) from exc
    except (OSError, UnicodeError) as exc:
        raise RegistrationError("cli_unavailable") from exc


def project_identity(project: str, timeout: float) -> tuple[Path, Path]:
    try:
        directory = Path(project).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise RegistrationError("invalid_project") from exc
    result = invoke(["git", "rev-parse", "--show-toplevel"], directory, timeout)
    if result.returncode != 0 or not text_identity(result.stdout.rstrip("\n")):
        raise RegistrationError("not_git_project")
    try:
        top = Path(result.stdout.rstrip("\n")).resolve(strict=True)
        result = invoke(["git", "rev-parse", "--git-common-dir"], top, timeout)
        if result.returncode != 0 or not text_identity(result.stdout.rstrip("\n")):
            raise RegistrationError("git_common_dir_unknown")
        common = (top / result.stdout.rstrip("\n")).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise RegistrationError("git_common_dir_unknown") from exc
    if not top.is_dir() or not common.is_dir():
        raise RegistrationError("git_common_dir_unknown")
    return top, common


def cli_json(cli: str, top: Path, timeout: float, *args: str) -> tuple[int, dict[str, Any]]:
    result = invoke([cli, *args, "--json"], top, timeout)
    try:
        payload = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise RegistrationError("cli_invalid_json") from exc
    if not isinstance(payload, dict):
        raise RegistrationError("cli_invalid_contract")
    return result.returncode, payload


def current_project(cli: str, top: Path, timeout: float) -> dict[str, Any] | None:
    code, payload = cli_json(cli, top, timeout, "worktree", "current")
    error = payload.get("error")
    if payload.get("ok") is False and isinstance(error, dict) and error.get("code") == "selector_not_found":
        if payload.get("result"):
            raise RegistrationError("current_contract_conflict")
        return None
    if code != 0 or payload.get("ok") is not True or error:
        raise RegistrationError("current_query_failed")
    result = payload.get("result")
    worktree = result.get("worktree") if isinstance(result, dict) else None
    if not isinstance(worktree, dict):
        raise RegistrationError("current_identity_unknown")
    path, identity = worktree.get("path"), worktree.get("id")
    if path != str(top) or not text_identity(identity):
        raise RegistrationError("path_mismatch")
    repo_id, delimiter, id_path = identity.partition("::")
    if not delimiter or not REPO_ID.fullmatch(repo_id) or id_path != str(top):
        raise RegistrationError("current_identity_mismatch")
    if "repoId" in worktree and worktree["repoId"] != repo_id:
        raise RegistrationError("current_identity_mismatch")
    return {"ok": True, "result": {"worktree": {"id": identity, "path": path}}}


def verify_lock(fd: int, path: Path) -> None:
    try:
        opened, named = os.fstat(fd), path.lstat()
    except OSError as exc:
        raise RegistrationError("registration_lock_unknown", 74) from exc
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_uid != os.getuid()
        or stat.S_IMODE(opened.st_mode) & 0o077
        or opened.st_nlink != 1
        or not stat.S_ISREG(named.st_mode)
        or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
    ):
        raise RegistrationError("registration_lock_unsafe", 74)


def acquire_lock(common: Path, wait_seconds: float, *, existing_only: bool = False) -> int | None:
    path = common / LOCK_NAME
    if not hasattr(os, "O_NOFOLLOW"):
        raise RegistrationError("registration_lock_platform_unsupported", 74)
    try:
        access = os.O_RDONLY if existing_only else os.O_RDWR | os.O_CREAT
        fd = os.open(path, access | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except FileNotFoundError as exc:
        if existing_only:
            return None
        raise RegistrationError("registration_lock_unsafe", 74) from exc
    except OSError as exc:
        raise RegistrationError("registration_lock_unsafe", 74) from exc
    try:
        verify_lock(fd, path)
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RegistrationError("registration_lock_busy", 75)
                time.sleep(min(0.05, remaining))
            except OSError as exc:
                raise RegistrationError("registration_lock_unavailable", 74) from exc
        verify_lock(fd, path)
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_pending(fd: int) -> dict[str, Any] | None:
    try:
        raw = os.pread(fd, 16385, 0)
        if not raw:
            return None
        if len(raw) > 16384:
            raise ValueError("oversized marker")
        pending = json.loads(raw)
        if (
            not isinstance(pending, dict)
            or set(pending) != {"schema", "state", "project", "repo_id"}
            or pending["schema"] != PENDING_SCHEMA
            or pending["state"] != "pending"
            or not text_identity(pending["project"])
            or not Path(pending["project"]).is_absolute()
            or (pending["repo_id"] is not None and (not text_identity(pending["repo_id"]) or not REPO_ID.fullmatch(pending["repo_id"])))
        ):
            raise ValueError("unknown marker")
        return pending
    except (OSError, ValueError, TypeError) as exc:
        # Foreign/truncated state is never erased or interpreted as no attempt.
        raise RegistrationError("registration_marker_unknown", 74) from exc


def write_pending(fd: int, top: Path, repo_id: str | None = None) -> None:
    pending = {"schema": PENDING_SCHEMA, "state": "pending", "project": str(top), "repo_id": repo_id}
    raw = json.dumps(pending, separators=(",", ":")).encode()
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        remaining = memoryview(raw)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("marker write made no progress")
            remaining = remaining[written:]
        os.ftruncate(fd, len(raw))
        os.fsync(fd)
    except OSError as exc:
        raise RegistrationError("registration_marker_write_failed", 74) from exc


def clear_verified_pending(fd: int) -> None:
    try:
        os.ftruncate(fd, 0)
        os.fsync(fd)
    except OSError as exc:
        raise RegistrationError("registration_marker_clear_failed", 74) from exc


def require_pending_identity(pending: dict[str, Any], top: Path, current: dict[str, Any]) -> None:
    if pending["project"] != str(top) or (pending["repo_id"] is not None and pending["repo_id"] != current["result"]["worktree"]["id"].partition("::")[0]):
        raise RegistrationError("registration_pending_identity_mismatch", 75)


def check_existing_pending(common: Path, top: Path, current: dict[str, Any], wait_seconds: float) -> None:
    # Initial probes remain read-only. They must not bypass an acknowledged
    # repo identity left by a failed earlier registration, nor create a lock.
    fd = acquire_lock(common, wait_seconds, existing_only=True)
    if fd is None:
        return
    try:
        pending = read_pending(fd)
        if pending is not None:
            require_pending_identity(pending, top, current)
            current["registration"] = {"status": "observed", "pending_marker_preserved": True}
    finally:
        os.close(fd)


def register(cli: str, top: Path, common: Path, timeout: float, wait_seconds: float) -> dict[str, Any]:
    fd = acquire_lock(common, wait_seconds)
    assert fd is not None
    try:
        pending = read_pending(fd)
        # A competing helper may have completed registration after the caller's
        # first selector_not_found. Never mutate on that stale observation.
        current = current_project(cli, top, timeout)
        if current is not None:
            if pending is not None:
                require_pending_identity(pending, top, current)
                clear_verified_pending(fd)
            current["registration"] = {"status": "already_registered"}
            return current
        if pending is not None:
            # A timed-out CLI may have submitted a server-side mutation that is
            # still in flight. Lock release/process death is NOT proof of no-op.
            raise RegistrationError("registration_prior_outcome_unknown", 75)
        try:
            code, status_payload = cli_json(cli, top, timeout, "status")
            result = status_payload.get("result")
            runtime = result.get("runtime") if isinstance(result, dict) else None
            # Older CLI status envelopes omit ok. This is only a liveness
            # precheck; registration still requires TWO explicit ok contracts.
            if code != 0 or status_payload.get("ok") is False or not isinstance(runtime, dict) or runtime.get("reachable") is False:
                raise RegistrationError("runtime_unavailable")
        except RegistrationError:
            print("SPAWN_WORKER_ORCA_AUTO_REGISTER_SKIPPED: orca status 不可达或合同无效，跳过自动注册（回退 tmux）", file=sys.stderr)
            raise

        # Durable intent MUST precede the first potentially mutating RPC.
        # Any interruption/uncertain response leaves it for read-only recovery.
        write_pending(fd, top)
        print(f"SPAWN_WORKER_ORCA_AUTO_REGISTER: 仓库未注册 Orca，注册当前 Git toplevel: {top}", file=sys.stderr)
        try:
            code, added = cli_json(cli, top, timeout, "repo", "add", "--path", str(top))
            result = added.get("result")
            repo = result.get("repo") if isinstance(result, dict) else None
            if code != 0 or added.get("ok") is not True or added.get("error") or not isinstance(repo, dict) or not text_identity(repo.get("id")) or not REPO_ID.fullmatch(repo["id"]):
                raise RegistrationError("repo_add_unconfirmed")
            # Preserve the acknowledged ID even if the optional path is wrong.
            # Later current queries must not reconcile pending to another repo.
            write_pending(fd, top, repo["id"])
            if "path" in repo and repo["path"] != str(top):
                raise RegistrationError("repo_add_identity_mismatch")
        except RegistrationError:
            print("ERROR: orca repo add 失败或未返回明确成功身份，不进入 Orca 模式（回退 tmux；不得盲目重试）", file=sys.stderr)
            raise
        try:
            current = current_project(cli, top, timeout)
            if current is None or current["result"]["worktree"]["id"].partition("::")[0] != repo["id"]:
                raise RegistrationError("post_add_identity_mismatch")
        except RegistrationError:
            print("ERROR: repo add 后 worktree current 复验失败，不进入 Orca 模式（回退 tmux；保留注册状态供人工核对）", file=sys.stderr)
            raise
        clear_verified_pending(fd)
        current["registration"] = {"status": "registered", "repo_id": repo["id"]}
        return current
    finally:
        # Persistent sentinel; unlinking could split waiters onto different
        # inodes. Kernel close releases the lock even after process failure.
        os.close(fd)


def bounded_seconds(value: str) -> float:
    result = float(value)
    if not math.isfinite(result) or not 0.05 <= result <= 30:
        raise argparse.ArgumentTypeError("seconds must be between 0.05 and 30")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--orca-cli", required=True, help="one resolved executable path, never a shell command")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--probe-only", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--lock-timeout", type=bounded_seconds, default=5.0)
    parser.add_argument("--cli-timeout", type=bounded_seconds, default=10.0)
    args = parser.parse_args()
    try:
        if not Path(args.orca_cli).is_absolute() or not os.access(args.orca_cli, os.X_OK):
            raise RegistrationError("invalid_cli_path", 64)
        top, common = project_identity(args.project, args.cli_timeout)
        if args.dry_run:
            # No lock, current lookup, status or mutation is needed to report
            # this plan. Dry-run cannot establish a registered project.
            payload = {"ok": False, "error": {"code": "registration_dry_run"}, "project": str(top)}
            code = 1
        elif args.probe_only:
            payload = current_project(args.orca_cli, top, args.cli_timeout)
            if payload is None:
                payload = {"ok": False, "error": {"code": "selector_not_found"}}
                code = 1
            else:
                check_existing_pending(common, top, payload, args.lock_timeout)
                code = 0
        else:
            payload = register(args.orca_cli, top, common, args.cli_timeout, args.lock_timeout)
            code = 0
    except RegistrationError as exc:
        payload = {"ok": False, "error": {"code": exc.reason}}
        code = exc.code
        print(f"SPAWN_WORKER_ORCA_AUTO_REGISTER_FAILED: reason={exc.reason}", file=sys.stderr)
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
