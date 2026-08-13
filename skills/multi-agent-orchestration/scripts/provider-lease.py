#!/usr/bin/env python3
"""Atomic provider concurrency leases shared by all worktrees of a repo."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


SCHEMA = "multi-agent-orchestration.provider-lease.v1"
PROVISIONAL_TTL_SECONDS = 600


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_now() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def safe_key(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]
    label = "".join(char if char.isalnum() or char in "._-" else "-" for char in value)[:40]
    return f"{label or 'provider'}-{digest}"


def process_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # EPERM still proves that the process exists; reclaiming here would
        # exceed the configured provider limit.
        return True


def tmux_alive(session: str) -> bool | None:
    if not session:
        return False
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.returncode == 0


def orca_terminal_alive(handle: str, orca_cli: str) -> bool | None:
    if not handle:
        return False
    if not orca_cli:
        return None
    try:
        result = subprocess.run(
            [orca_cli, "terminal", "show", "--terminal", handle, "--json"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    try:
        payload = json.loads(result.stdout or result.stderr)
    except json.JSONDecodeError:
        return None
    if result.returncode != 0:
        error_code = str(payload.get("error", {}).get("code", ""))
        if error_code in {
            "terminal_handle_stale",
            "terminal_not_found",
            "tab_not_found",
            "worktree_not_found",
        }:
            return False
        # Runtime / transport failures are not proof that the resource died.
        return None
    try:
        terminal = payload.get("result", {}).get("terminal", {})
    except AttributeError:
        return None
    return bool(terminal.get("connected", False) or terminal.get("writable", False))


def lease_alive(lease: dict, orca_cli: str) -> bool:
    if lease.get("schema") != SCHEMA:
        return True
    state = lease.get("state")
    if state == "provisional":
        created = parse_time(lease.get("created_at", ""))
        fresh = created is not None and (utc_now() - created).total_seconds() <= PROVISIONAL_TTL_SECONDS
        return fresh and process_alive(int(lease.get("owner_pid", 0) or 0))
    if state == "active":
        transport = lease.get("transport")
        if transport == "tmux":
            alive = tmux_alive(str(lease.get("resource_handle", "")))
        elif transport == "orca_terminal":
            alive = orca_terminal_alive(str(lease.get("resource_handle", "")), orca_cli)
        else:
            alive = None
        # Unknown liveness is fail-closed: never reclaim a possibly active quota.
        return True if alive is None else alive
    # Malformed/unknown states are not stale evidence. Keep their quota until
    # an operator can inspect the registry.
    return True


def read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


@contextlib.contextmanager
def provider_lock(provider_dir: Path):
    provider_dir.mkdir(parents=True, exist_ok=True)
    lock_path = provider_dir / ".lock"
    with lock_path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


def cmd_acquire(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    provider_dir = root / safe_key(args.provider)
    session_path = provider_dir / f"{safe_key(args.session)}.json"
    with provider_lock(root):
        for existing_path in root.glob("*/*.json"):
            existing = read_json(existing_path)
            if existing is not None and existing.get("schema") == SCHEMA and existing.get("session") == args.session:
                if lease_alive(existing, args.orca_cli):
                    print(f"ERROR: provider lease session is already registered: {args.session}", file=sys.stderr)
                    return 75
                existing_path.unlink(missing_ok=True)
        active: list[Path] = []
        for path in provider_dir.glob("*.json"):
            lease = read_json(path)
            if lease is None or lease_alive(lease, args.orca_cli):
                active.append(path)
            else:
                path.unlink(missing_ok=True)
        if session_path in active:
            print(f"ERROR: provider lease already exists for session={args.session}", file=sys.stderr)
            return 75
        if len(active) >= args.max:
            print(
                f"ERROR: provider concurrency exhausted provider={args.provider} "
                f"active={len(active)} max={args.max}",
                file=sys.stderr,
            )
            return 75
        payload = {
            "schema": SCHEMA,
            "state": "provisional",
            "created_at": iso_now(),
            "updated_at": iso_now(),
            "provider": args.provider,
            "backend": args.backend,
            "session": args.session,
            "project": args.project,
            "owner_pid": args.owner_pid,
            "max_concurrency": args.max,
            "transport": "",
            "resource_handle": "",
        }
        atomic_write(session_path, payload)
    print(json.dumps({"lease_file": str(session_path), "active": len(active) + 1, "max": args.max}))
    return 0


def load_exact_lease(path: Path, session: str) -> dict:
    lease = read_json(path)
    if lease is None or lease.get("schema") != SCHEMA or lease.get("session") != session:
        raise ValueError("lease file does not match the expected schema/session")
    return lease


def resolve_exact_lease_path(root_value: str, path_value: str) -> Path:
    root = Path(root_value).resolve()
    path = Path(path_value).resolve()
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ValueError("lease file is outside the trusted provider lease root") from exc
    if len(relative.parts) != 2 or path.suffix != ".json":
        raise ValueError("lease file does not have the expected provider/session path shape")
    return path


def cmd_finalize(args: argparse.Namespace) -> int:
    try:
        path = resolve_exact_lease_path(args.root, args.lease_file)
    except ValueError as exc:
        print(f"ERROR: {exc}: {args.lease_file}", file=sys.stderr)
        return 64
    with provider_lock(Path(args.root).resolve()):
        try:
            lease = load_exact_lease(path, args.session)
        except ValueError as exc:
            print(f"ERROR: {exc}: {path}", file=sys.stderr)
            return 64
        lease["state"] = "active"
        lease["updated_at"] = iso_now()
        lease["transport"] = args.transport
        lease["resource_handle"] = args.resource_handle
        atomic_write(path, lease)
    print(json.dumps({"lease_file": str(path), "state": "active"}))
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    try:
        path = resolve_exact_lease_path(args.root, args.lease_file)
    except ValueError as exc:
        print(f"ERROR: {exc}: {args.lease_file}", file=sys.stderr)
        return 64
    if not args.resource_settled:
        print("ERROR: release requires --resource-settled after caller-side lifecycle proof", file=sys.stderr)
        return 64
    with provider_lock(Path(args.root).resolve()):
        if not path.exists():
            print(json.dumps({"lease_file": str(path), "released": False, "reason": "already_missing"}))
            return 0
        try:
            lease = load_exact_lease(path, args.session)
        except ValueError as exc:
            print(f"ERROR: {exc}: {path}", file=sys.stderr)
            return 64
        if lease.get("state") == "provisional":
            if args.owner_pid <= 1 or args.owner_pid != int(lease.get("owner_pid", 0) or 0):
                print("ERROR: only the exact acquiring process may release a provisional lease", file=sys.stderr)
                return 75
        elif lease.get("state") == "active":
            if lease_alive(lease, args.orca_cli):
                print("ERROR: provider lease resource is still active or its liveness is unknown", file=sys.stderr)
                return 75
        else:
            print("ERROR: provider lease has an unsupported state; retaining quota fail-closed", file=sys.stderr)
            return 75
        path.unlink()
    print(json.dumps({"lease_file": str(path), "released": True}))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    subcommands = root.add_subparsers(dest="command", required=True)

    acquire = subcommands.add_parser("acquire")
    acquire.add_argument("--root", required=True)
    acquire.add_argument("--provider", required=True)
    acquire.add_argument("--backend", required=True)
    acquire.add_argument("--session", required=True)
    acquire.add_argument("--project", required=True)
    acquire.add_argument("--max", type=int, required=True)
    acquire.add_argument("--owner-pid", type=int, required=True)
    acquire.add_argument("--orca-cli", default="")
    acquire.set_defaults(func=cmd_acquire)

    finalize = subcommands.add_parser("finalize")
    finalize.add_argument("--root", required=True)
    finalize.add_argument("--lease-file", required=True)
    finalize.add_argument("--session", required=True)
    finalize.add_argument("--transport", choices=("tmux", "orca_terminal"), required=True)
    finalize.add_argument("--resource-handle", required=True)
    finalize.set_defaults(func=cmd_finalize)

    release = subcommands.add_parser("release")
    release.add_argument("--root", required=True)
    release.add_argument("--lease-file", required=True)
    release.add_argument("--session", required=True)
    release.add_argument("--resource-settled", action="store_true")
    release.add_argument("--orca-cli", default="")
    release.add_argument("--owner-pid", type=int, default=0)
    release.set_defaults(func=cmd_release)
    return root


def main() -> int:
    args = parser().parse_args()
    if getattr(args, "max", 1) < 1:
        print("ERROR: --max must be a positive integer", file=sys.stderr)
        return 64
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
