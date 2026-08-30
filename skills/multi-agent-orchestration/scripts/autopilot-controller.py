#!/usr/bin/env python3
"""CLI for the L2 cross-session-recoverable Autopilot runtime."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

from autopilot_runtime import (
    ControllerError,
    EXIT_DATA,
    EXIT_SOFTWARE,
    EXIT_USAGE,
    RuntimeContext,
    acquire_lease,
    collect_and_reconcile,
    execute_tick,
    init_runtime,
    renew_lease,
    status,
)


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"ERROR: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))


def load_json_input(value: str, label: str) -> dict[str, Any]:
    try:
        if value == "-":
            raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        else:
            path = Path(value)
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ControllerError(EXIT_DATA, f"{label} file may not be a symlink")
            if not stat.S_ISREG(mode):
                raise ControllerError(EXIT_DATA, f"{label} path must be a regular file")
            flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
            fd = os.open(path, flags)
            with os.fdopen(fd, "rb") as stream:
                raw = stream.read(1024 * 1024 + 1)
    except ControllerError:
        raise
    except OSError as exc:
        raise ControllerError(EXIT_DATA, f"cannot read {label} JSON: {exc}") from exc
    if len(raw) > 1024 * 1024:
        raise ControllerError(EXIT_DATA, f"{label} JSON exceeds 1 MiB")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ControllerError(EXIT_DATA, f"invalid {label} JSON") from exc
    if not isinstance(payload, dict):
        raise ControllerError(EXIT_DATA, f"{label} JSON root must be an object")
    return payload


def command_context(args: argparse.Namespace, *, create: bool = False) -> RuntimeContext:
    return RuntimeContext(Path(args.repo), create=create)


def cmd_init(args: argparse.Namespace) -> int:
    items: list[dict[str, Any]] = []
    if args.items_file:
        payload = load_json_input(args.items_file, "items")
        candidate = payload.get("items")
        if not isinstance(candidate, list):
            raise ControllerError(EXIT_DATA, "items JSON must contain an items list")
        items = candidate
    state = init_runtime(
        command_context(args, create=True), args.project_id, args.policy_commit,
        args.wave_id, args.run_id, items, Path(args.facts_adapter), Path(args.facts_manifest),
    )
    emit({"initialized": True, "state": state})
    return 0


def cmd_acquire(args: argparse.Namespace) -> int:
    lease = acquire_lease(
        command_context(args), args.project_id, args.policy_commit, args.owner,
        args.ttl_seconds, takeover=args.takeover, reason=args.reason,
    )
    emit({"acquired": True, "lease": lease})
    return 0


def cmd_renew(args: argparse.Namespace) -> int:
    lease = renew_lease(
        command_context(args), args.project_id, args.policy_commit, args.owner,
        args.fencing_token, args.ttl_seconds,
    )
    emit({"renewed": True, "lease": lease})
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    emit(status(command_context(args), args.project_id, args.policy_commit))
    return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    result = collect_and_reconcile(
        command_context(args), args.project_id, args.policy_commit, args.owner,
        args.fencing_token, timeout_seconds=args.timeout_seconds,
    )
    emit(result)
    return 0


def cmd_tick(args: argparse.Namespace) -> int:
    result = execute_tick(
        command_context(args), args.project_id, args.policy_commit, args.owner,
        args.fencing_token, Path(args.adapter), timeout_seconds=args.timeout_seconds,
    )
    emit(result)
    return 0


def add_identity(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", required=True, help="path inside the target Git repository")
    parser.add_argument("--project-id", required=True, help="stable project policy identity")
    parser.add_argument("--policy-commit", required=True, help="exact policy commit identity")


def add_owner(parser: argparse.ArgumentParser) -> None:
    add_identity(parser)
    parser.add_argument("--owner", required=True, help="stable PM owner identity")
    parser.add_argument("--fencing-token", required=True, type=int)


def build_parser() -> argparse.ArgumentParser:
    root = Parser(description="Durable L2 Autopilot controller (no scheduler)")
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="initialize a new runtime without overwriting evidence")
    add_identity(init)
    init.add_argument("--wave-id", required=True)
    init.add_argument("--run-id", required=True)
    init.add_argument("--items-file", help="version-independent {items:[...]} initializer; '-' reads stdin")
    init.add_argument("--facts-adapter", required=True, help="canonical read-only facts collector executable")
    init.add_argument("--facts-manifest", required=True, help="canonical pinned facts bindings manifest")
    init.set_defaults(func=cmd_init)

    acquire = commands.add_parser("acquire", help="acquire or explicitly take over the PM lease")
    add_identity(acquire)
    acquire.add_argument("--owner", required=True)
    acquire.add_argument("--ttl-seconds", type=int, default=900)
    acquire.add_argument("--takeover", action="store_true")
    acquire.add_argument("--reason")
    acquire.set_defaults(func=cmd_acquire)

    renew = commands.add_parser("renew", help="renew the exact current owner/token")
    add_owner(renew)
    renew.add_argument("--ttl-seconds", type=int, default=900)
    renew.set_defaults(func=cmd_renew)

    show = commands.add_parser("status", help="read validated runtime state without mutation")
    add_identity(show)
    show.set_defaults(func=cmd_status)

    reconcile_cmd = commands.add_parser("reconcile", help="collect pinned external facts and plan one unique next action")
    add_owner(reconcile_cmd)
    reconcile_cmd.add_argument("--timeout-seconds", type=int, default=30, help="pinned facts collector timeout (1..300)")
    reconcile_cmd.set_defaults(func=cmd_reconcile)

    tick = commands.add_parser("tick", help="execute at most one pending adapter mutation")
    add_owner(tick)
    tick.add_argument("--adapter", required=True, help="one executable; request is fixed JSON on stdin")
    tick.add_argument("--timeout-seconds", type=int, default=60)
    tick.set_defaults(func=cmd_tick)
    return root


def main() -> int:
    try:
        args = build_parser().parse_args()
        return int(args.func(args))
    except ControllerError as exc:
        print(json.dumps({"error": exc.message, "exit_code": exc.code}, ensure_ascii=False), file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        print(json.dumps({"error": "interrupted", "exit_code": 75}), file=sys.stderr)
        return 75
    except Exception as exc:  # Last-resort stable CLI boundary; no traceback/data spill.
        print(json.dumps({"error": f"internal controller error: {type(exc).__name__}", "exit_code": EXIT_SOFTWARE}), file=sys.stderr)
        return EXIT_SOFTWARE


if __name__ == "__main__":
    raise SystemExit(main())
