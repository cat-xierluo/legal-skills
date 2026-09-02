#!/usr/bin/env python3
"""Durable, fail-closed runtime primitives for the L2 Autopilot controller."""

from __future__ import annotations

import contextlib
import copy
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import secrets
import signal
import stat
import subprocess
import tempfile
from typing import Any, Callable, Iterator


SCHEMA_VERSION = 1
STATE_CONTRACT = "multi-agent-orchestration.autopilot-state.v1"
LEASE_CONTRACT = "multi-agent-orchestration.autopilot-lease.v1"
EVENT_CONTRACT = "multi-agent-orchestration.autopilot-event.v1"
FACTS_REQUEST_CONTRACT = "multi-agent-orchestration.autopilot-facts-request.v1"
FACTS_CONTRACT = "multi-agent-orchestration.autopilot-facts.v1"
ADAPTER_REQUEST_CONTRACT = "multi-agent-orchestration.autopilot-adapter-request.v1"
ADAPTER_RECEIPT_CONTRACT = "multi-agent-orchestration.autopilot-adapter-receipt.v1"

EXIT_USAGE = 64
EXIT_DATA = 65
EXIT_NOT_FOUND = 66
EXIT_SOFTWARE = 70
EXIT_IO = 74
EXIT_CONFLICT = 75
EXIT_CONFIG = 78
MUTATION_SAFETY_SECONDS = 5
MAX_JSON_BYTES = 1024 * 1024

STATES = {
    "IDLE", "PLANNING", "DISPATCHING", "RUNNING", "VERIFYING",
    "MERGING", "WRITEBACK", "COMPLETE", "WAITING_PROVIDER_RESET",
    "PARKED_SOFT", "PARKED_HARD", "ERROR_RECONCILE_REQUIRED",
}
EXTERNAL_ACTIONS = {"spawn", "settle", "verify", "push", "open_pr", "merge", "writeback"}
# repair_acceptance（v2.14.0）：验收失败的内部可恢复修复动作。checks=="fail"
# 不再无条件 hard_park——先经 acceptance-recovery.py 分类，预算未耗尽时规划
# repair_acceptance（不泊车），耗尽/外部依赖/安全不明才按类泊车。
INTERNAL_ACTIONS = {"adopt", "observe", "retry_later", "reject_duplicate", "hard_park", "complete", "repair_acceptance"}
ALLOWED_ACTIONS = EXTERNAL_ACTIONS | INTERNAL_ACTIONS
DANGEROUS_DIRTY_ACTIONS = {"spawn", "verify", "push", "open_pr", "merge", "writeback", "adopt"}
STATE_KEYS = {
    "schema_version", "contract", "repo_identity", "project_id", "policy_commit",
    "wave_id", "run_id", "state", "pm_owner", "fencing_token", "lease_expires_at",
    "last_tick_at", "last_event_id", "items", "parking_code", "parking_detail",
    "pending_intent", "facts_adapter", "facts_manifest", "mutation_adapter",
}
INITIAL_ITEM_KEYS = {
    "task_id", "attempt", "orca_task_id", "dispatch_id", "branch", "worktree",
    "provider", "pr_number", "pr_head_oid", "status", "next_action", "retry_at",
    "last_heartbeat_at", "released",
}
RUNTIME_ITEM_KEYS = INITIAL_ITEM_KEYS | {
    "dispatch_status", "local_oid", "remote_oid", "pr_state", "merge_commit",
    "observed_at", "adopted_target_digest", "dirty", "worktree_count", "published",
    "checks", "mergeable", "approvals", "approvals_known", "required_approvals",
    "provider_status", "verification_passed", "evidence_sha256", "gate_contract_sha256",
    # v2.14.0：已消耗的验收修复 episode 数（edge-triggered，见 reconcile 收尾）。
    "repair_attempts",
}


class ControllerError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_time(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value: Any) -> dt.datetime:
    if not isinstance(value, str):
        raise ControllerError(EXIT_DATA, "timestamp must be an RFC3339 string")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ControllerError(EXIT_DATA, f"invalid RFC3339 timestamp: {value}") from exc
    return parsed.replace(tzinfo=dt.timezone.utc)


def canonical_json(value: Any) -> bytes:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ControllerError(EXIT_DATA, f"value is not strict JSON: {exc}") from exc
    return (encoded + "\n").encode("utf-8")


def object_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ControllerError(EXIT_IO, f"cannot hash pinned file {path}: {exc}") from exc
    return digest.hexdigest()


def _run_git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise ControllerError(EXIT_CONFIG, f"git unavailable: {exc}") from exc
    if result.returncode != 0:
        raise ControllerError(EXIT_CONFIG, f"Git repository query failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def _reject_symlink(path: Path, *, allow_missing: bool = False) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        if allow_missing:
            return
        raise ControllerError(EXIT_NOT_FOUND, f"required path is missing: {path}")
    except OSError as exc:
        raise ControllerError(EXIT_IO, f"cannot inspect path {path}: {exc}") from exc
    if stat.S_ISLNK(mode):
        raise ControllerError(EXIT_CONFIG, f"symlink is forbidden: {path}")


def _mkdir_trusted(path: Path, common_dir: Path) -> None:
    try:
        relative = path.relative_to(common_dir)
    except ValueError as exc:
        raise ControllerError(EXIT_CONFIG, "runtime root escaped Git common dir") from exc
    cursor = common_dir
    _reject_symlink(cursor)
    for part in relative.parts:
        cursor = cursor / part
        _reject_symlink(cursor, allow_missing=True)
        try:
            cursor.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as exc:
            raise ControllerError(EXIT_IO, f"cannot create runtime directory {cursor}: {exc}") from exc
        _reject_symlink(cursor)
        if not cursor.is_dir():
            raise ControllerError(EXIT_CONFIG, f"runtime component is not a directory: {cursor}")


def resolve_pinned_file(path: Path, *, executable: bool) -> dict[str, str]:
    _reject_symlink(path)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ControllerError(EXIT_CONFIG, f"pinned file is unavailable: {path}: {exc}") from exc
    if not resolved.is_file() or executable and not os.access(resolved, os.X_OK):
        raise ControllerError(EXIT_CONFIG, f"pinned file has invalid type or mode: {resolved}")
    return {"path": str(resolved), "sha256": file_sha256(resolved)}


def verify_pinned_file(binding: dict[str, Any], label: str, *, executable: bool) -> Path:
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ControllerError(EXIT_DATA, f"{label} binding is malformed")
    current = resolve_pinned_file(Path(binding["path"]), executable=executable)
    if current != binding:
        raise ControllerError(EXIT_CONFIG, f"{label} path/digest changed after init")
    return Path(binding["path"])


class RuntimeContext:
    def __init__(self, repo: Path, *, create: bool):
        try:
            requested = repo.resolve(strict=True)
            self.repo = Path(_run_git(requested, "rev-parse", "--show-toplevel")).resolve(strict=True)
            common_raw = Path(_run_git(requested, "rev-parse", "--git-common-dir"))
            self.common_dir = (common_raw if common_raw.is_absolute() else requested / common_raw).resolve(strict=True)
        except OSError as exc:
            raise ControllerError(EXIT_CONFIG, f"repository identity path is unavailable: {exc}") from exc
        self.repo_identity = hashlib.sha256(str(self.common_dir).encode("utf-8")).hexdigest()
        self.root = self.common_dir / "orchestration" / "autopilot"
        if create:
            _mkdir_trusted(self.root, self.common_dir)
        else:
            _reject_symlink(self.common_dir / "orchestration")
            _reject_symlink(self.root)
            if not self.root.is_dir():
                raise ControllerError(EXIT_NOT_FOUND, f"Autopilot runtime is not initialized: {self.root}")
            try:
                self.root.resolve(strict=True).relative_to(self.common_dir)
            except (OSError, ValueError) as exc:
                raise ControllerError(EXIT_CONFIG, "runtime root escaped Git common dir") from exc
        self.state_path = self.root / "state.json"
        self.events_path = self.root / "events.jsonl"
        self.lease_path = self.root / "lease.json"
        self.lock_path = self.root / "lock"
        for candidate in (self.state_path, self.events_path, self.lease_path, self.lock_path):
            _reject_symlink(candidate, allow_missing=True)

    def validate_policy_commit(self, policy_commit: str) -> None:
        if not isinstance(policy_commit, str) or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", policy_commit) is None:
            raise ControllerError(EXIT_CONFIG, "policy_commit must be a lowercase full Git commit OID")
        if _run_git(self.repo, "rev-parse", "--verify", f"{policy_commit}^{{commit}}") != policy_commit:
            raise ControllerError(EXIT_CONFIG, "policy_commit does not resolve to the exact full commit OID")

    def registered_worktrees(self) -> set[Path]:
        roots: set[Path] = set()
        for line in _run_git(self.repo, "worktree", "list", "--porcelain").splitlines():
            if line.startswith("worktree "):
                with contextlib.suppress(OSError):
                    roots.add(Path(line[9:]).resolve(strict=True))
        return roots


@contextlib.contextmanager
def runtime_lock(ctx: RuntimeContext) -> Iterator[None]:
    _reject_symlink(ctx.lock_path, allow_missing=True)
    flags = os.O_RDWR | os.O_CREAT | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
    try:
        fd = os.open(ctx.lock_path, flags, 0o600)
    except OSError as exc:
        raise ControllerError(EXIT_IO, f"cannot open runtime lock: {exc}") from exc
    with os.fdopen(fd, "a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


@contextlib.contextmanager
def runtime_read_lock(ctx: RuntimeContext) -> Iterator[None]:
    _reject_symlink(ctx.lock_path)
    flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
    try:
        fd = os.open(ctx.lock_path, flags)
    except OSError as exc:
        raise ControllerError(EXIT_IO, f"cannot open runtime lock read-only: {exc}") from exc
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_SH)
        yield


def _read_bytes(path: Path, *, required: bool = True, max_bytes: int | None = None) -> bytes | None:
    _reject_symlink(path, allow_missing=not required)
    flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        if required:
            raise ControllerError(EXIT_NOT_FOUND, f"runtime file is missing: {path}")
        return None
    except OSError as exc:
        raise ControllerError(EXIT_IO, f"cannot read {path}: {exc}") from exc
    with os.fdopen(fd, "rb") as stream:
        raw = stream.read(None if max_bytes is None else max_bytes + 1)
    if max_bytes is not None and len(raw) > max_bytes:
        raise ControllerError(EXIT_DATA, f"file exceeds {max_bytes} bytes: {path}")
    return raw


def strict_json_loads(raw: bytes, label: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(value)
    try:
        return json.loads(raw, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ControllerError(EXIT_DATA, f"corrupt strict JSON: {label}") from exc


def read_json(path: Path, *, required: bool = True) -> dict[str, Any] | None:
    raw = _read_bytes(path, required=required, max_bytes=MAX_JSON_BYTES)
    if raw is None:
        return None
    payload = strict_json_loads(raw, str(path))
    if not isinstance(payload, dict):
        raise ControllerError(EXIT_DATA, f"JSON root must be an object: {path}")
    return payload


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise ControllerError(EXIT_IO, f"directory fsync failed for {path}: {exc}") from exc


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _reject_symlink(path, allow_missing=True)
    try:
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical_json(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        _reject_symlink(path, allow_missing=True)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError as exc:
        raise ControllerError(EXIT_IO, f"atomic write failed for {path}: {exc}") from exc
    finally:
        if "temporary" in locals():
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)


def _append_event_bytes(ctx: RuntimeContext, payload: bytes) -> None:
    _reject_symlink(ctx.events_path, allow_missing=True)
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
    try:
        fd = os.open(ctx.events_path, flags, 0o600)
        with os.fdopen(fd, "ab") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(ctx.events_path.parent)
    except OSError as exc:
        raise ControllerError(EXIT_IO, f"write-ahead event append failed: {exc}") from exc


def _validate_schema(payload: dict[str, Any], contract: str, label: str) -> None:
    version = payload.get("schema_version")
    if type(version) is not int or version != SCHEMA_VERSION:
        qualifier = "future " if type(version) is int and version > SCHEMA_VERSION else "unsupported "
        raise ControllerError(EXIT_DATA, f"{qualifier}{label} schema_version: {version!r}")
    if payload.get("contract") != contract:
        raise ControllerError(EXIT_DATA, f"{label} contract mismatch")


def _validate_identity(payload: dict[str, Any], ctx: RuntimeContext, project_id: str, policy_commit: str, label: str) -> None:
    if payload.get("repo_identity") != ctx.repo_identity:
        raise ControllerError(EXIT_CONFIG, f"{label} repository identity mismatch")
    if payload.get("project_id") != project_id:
        raise ControllerError(EXIT_CONFIG, f"{label} project identity mismatch")
    if payload.get("policy_commit") != policy_commit:
        raise ControllerError(EXIT_CONFIG, f"{label} policy identity mismatch")


def validate_state(state: dict[str, Any], ctx: RuntimeContext, project_id: str, policy_commit: str) -> dict[str, Any]:
    ctx.validate_policy_commit(policy_commit)
    _validate_schema(state, STATE_CONTRACT, "state")
    _validate_identity(state, ctx, project_id, policy_commit, "state")
    if set(state) != STATE_KEYS:
        raise ControllerError(EXIT_DATA, "state fields are unsupported or missing")
    if state.get("state") not in STATES or not isinstance(state.get("items"), list):
        raise ControllerError(EXIT_DATA, "state enum/items are invalid")
    if type(state.get("fencing_token")) is not int or state["fencing_token"] < 0:
        raise ControllerError(EXIT_DATA, "fencing_token must be non-negative integer")
    if type(state.get("last_event_id")) is not int or state["last_event_id"] < 0:
        raise ControllerError(EXIT_DATA, "last_event_id must be non-negative integer")
    for key in ("facts_adapter", "facts_manifest"):
        if not isinstance(state.get(key), dict) or set(state[key]) != {"path", "sha256"}:
            raise ControllerError(EXIT_DATA, f"state {key} binding is malformed")
    mutation_binding = state.get("mutation_adapter")
    if mutation_binding is not None and (
        not isinstance(mutation_binding, dict) or set(mutation_binding) != {"path", "sha256"}
    ):
        raise ControllerError(EXIT_DATA, "state mutation_adapter binding is malformed")
    roots = ctx.registered_worktrees()
    seen: set[str] = set()
    for item in state["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("task_id"), str) or item["task_id"] in seen:
            raise ControllerError(EXIT_DATA, "state item is malformed or duplicated")
        if not set(item).issubset(RUNTIME_ITEM_KEYS):
            raise ControllerError(EXIT_DATA, f"state item contains unsupported fields: {item['task_id']}")
        seen.add(item["task_id"])
        if type(item.get("attempt", 1)) is not int or item.get("attempt", 1) < 1:
            raise ControllerError(EXIT_DATA, f"invalid attempt for {item['task_id']}")
        worktree = item.get("worktree")
        if not worktree:
            continue
        try:
            resolved = Path(worktree).resolve(strict=True)
        except OSError as exc:
            if item.get("status") == "COMPLETE" or item.get("released") is True or not item.get("dispatch_id"):
                continue
            raise ControllerError(EXIT_CONFIG, f"active item worktree unavailable: {worktree}") from exc
        if resolved not in roots and item.get("status") != "COMPLETE" and item.get("released") is not True:
            raise ControllerError(EXIT_CONFIG, f"active item worktree not registered: {resolved}")
    return state


def read_event_log(ctx: RuntimeContext, project_id: str) -> list[dict[str, Any]]:
    raw = _read_bytes(ctx.events_path, required=False)
    if not raw:
        return []
    events: list[dict[str, Any]] = []
    previous_after: str | None = None
    for line_number, line in enumerate(raw.splitlines(), start=1):
        event = strict_json_loads(line, f"event line {line_number}")
        if not isinstance(event, dict):
            raise ControllerError(EXIT_DATA, f"event line {line_number} is not an object")
        _validate_schema(event, EVENT_CONTRACT, f"event line {line_number}")
        if event.get("event_id") != line_number or event.get("project_id") != project_id:
            raise ControllerError(EXIT_DATA, f"event identity/order mismatch at line {line_number}")
        after = event.get("state_after")
        if not isinstance(after, dict) or after.get("last_event_id") != line_number or event.get("after_hash") != object_hash(after):
            raise ControllerError(EXIT_DATA, f"event state/hash mismatch at line {line_number}")
        if line_number == 1 and event.get("before_hash") is not None:
            raise ControllerError(EXIT_DATA, "initial event before_hash must be null")
        if line_number > 1 and event.get("before_hash") != previous_after:
            raise ControllerError(EXIT_DATA, f"event hash chain mismatch at line {line_number}")
        previous_after = event["after_hash"]
        events.append(event)
    return events


def load_state_snapshot(
    ctx: RuntimeContext, project_id: str, policy_commit: str, *, recover: bool,
) -> tuple[dict[str, Any], bool]:
    persisted = read_json(ctx.state_path, required=False)
    events = read_event_log(ctx, project_id)
    if persisted is None:
        if len(events) != 1 or events[0].get("before_hash") is not None:
            raise ControllerError(EXIT_NOT_FOUND, "state missing without one recoverable init event")
        effective = validate_state(copy.deepcopy(events[0]["state_after"]), ctx, project_id, policy_commit)
        if recover:
            atomic_write_json(ctx.state_path, effective)
        return effective, True
    persisted = validate_state(persisted, ctx, project_id, policy_commit)
    if not events:
        raise ControllerError(EXIT_DATA, "state exists without write-ahead history")
    tail = events[-1]
    if tail["event_id"] == persisted["last_event_id"]:
        if tail["after_hash"] != object_hash(persisted):
            raise ControllerError(EXIT_DATA, "persisted state hash differs from event tail")
        return persisted, False
    if tail["event_id"] == persisted["last_event_id"] + 1 and tail["before_hash"] == object_hash(persisted):
        effective = validate_state(copy.deepcopy(tail["state_after"]), ctx, project_id, policy_commit)
        if recover:
            atomic_write_json(ctx.state_path, effective)
        return effective, True
    raise ControllerError(EXIT_DATA, f"unrecoverable event/state gap: event={tail['event_id']} state={persisted['last_event_id']}")


def write_ahead_transition(
    ctx: RuntimeContext, before: dict[str, Any] | None, after: dict[str, Any],
    kind: str, detail: dict[str, Any], *, after_event_hook: Callable[[], None] | None = None,
) -> dict[str, Any]:
    next_id = 1 if before is None else before["last_event_id"] + 1
    committed = copy.deepcopy(after)
    committed["last_event_id"] = next_id
    validate_state(committed, ctx, committed["project_id"], committed["policy_commit"])
    event = {
        "schema_version": 1, "contract": EVENT_CONTRACT, "event_id": next_id,
        "at": iso_time(utc_now()), "kind": kind, "project_id": committed["project_id"],
        "fencing_token": committed["fencing_token"],
        "before_hash": None if before is None else object_hash(before),
        "after_hash": object_hash(committed), "state_after": committed, "detail": detail,
    }
    _append_event_bytes(ctx, canonical_json(event))
    if after_event_hook:
        after_event_hook()
    atomic_write_json(ctx.state_path, committed)
    return committed


def load_lease(ctx: RuntimeContext, project_id: str, policy_commit: str, *, required: bool = True) -> dict[str, Any] | None:
    lease = read_json(ctx.lease_path, required=required)
    if lease is None:
        return None
    _validate_schema(lease, LEASE_CONTRACT, "lease")
    _validate_identity(lease, ctx, project_id, policy_commit, "lease")
    if type(lease.get("fencing_token")) is not int or not isinstance(lease.get("owner"), str):
        raise ControllerError(EXIT_DATA, "lease owner/token are invalid")
    parse_time(lease.get("expires_at"))
    return lease


def assert_lease_state_consistency(state: dict[str, Any], lease: dict[str, Any] | None) -> None:
    if lease is None:
        if state.get("fencing_token") != 0 or state.get("pm_owner") is not None or state.get("lease_expires_at") is not None:
            raise ControllerError(EXIT_DATA, "state has fencing data but lease.json is missing")
        return
    if any((
        state.get("pm_owner") != lease.get("owner"),
        state.get("fencing_token") != lease.get("fencing_token"),
        state.get("lease_expires_at") != lease.get("expires_at"),
    )):
        raise ControllerError(EXIT_DATA, "lease/state fencing records are inconsistent")


def recover_lease_state_gap(
    ctx: RuntimeContext, state: dict[str, Any], lease: dict[str, Any] | None, *, recover: bool,
) -> tuple[dict[str, Any], bool]:
    """Roll forward the two bounded gaps created by lease-first persistence.

    A new lease is durable before the matching state/event transition.  A crash
    in that interval can only produce either token+1 (acquire/takeover) or the
    same token with a later expiry (renew).  Every other mismatch is corruption
    and remains fail-closed.
    """
    try:
        assert_lease_state_consistency(state, lease)
        return state, False
    except ControllerError:
        if lease is None:
            raise
    assert lease is not None
    after = copy.deepcopy(state)
    if (
        lease.get("fencing_token") == state.get("fencing_token", -1) + 1
        and isinstance(lease.get("owner"), str)
    ):
        kind = "lease_acquire_gap_recovered"
        after.update(
            pm_owner=lease["owner"], fencing_token=lease["fencing_token"],
            lease_expires_at=lease["expires_at"],
        )
    elif (
        lease.get("fencing_token") == state.get("fencing_token")
        and lease.get("owner") == state.get("pm_owner")
        and lease.get("expires_at") != state.get("lease_expires_at")
        and parse_time(lease["expires_at"]) > parse_time(state["lease_expires_at"])
    ):
        kind = "lease_renew_gap_recovered"
        after["lease_expires_at"] = lease["expires_at"]
    else:
        raise ControllerError(EXIT_DATA, "unrecoverable lease/state fencing mismatch")
    if recover:
        after = write_ahead_transition(ctx, state, after, kind, {
            "owner": lease["owner"], "fencing_token": lease["fencing_token"],
            "expires_at": lease["expires_at"],
        })
    return after, True


def initial_state(
    ctx: RuntimeContext, project_id: str, policy_commit: str, wave_id: str, run_id: str,
    items: list[dict[str, Any]], facts_adapter: Path, facts_manifest: Path,
) -> dict[str, Any]:
    return validate_state({
        "schema_version": 1, "contract": STATE_CONTRACT, "repo_identity": ctx.repo_identity,
        "project_id": project_id, "policy_commit": policy_commit, "wave_id": wave_id,
        "run_id": run_id, "state": "IDLE", "pm_owner": None, "fencing_token": 0,
        "lease_expires_at": None, "last_tick_at": None, "last_event_id": 0,
        "items": items, "parking_code": None, "parking_detail": None, "pending_intent": None,
        "facts_adapter": resolve_pinned_file(facts_adapter, executable=True),
        "facts_manifest": resolve_pinned_file(facts_manifest, executable=False),
        "mutation_adapter": None,
    }, ctx, project_id, policy_commit)


def sanitize_initial_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(items, list) or len(items) > 256:
        raise ControllerError(EXIT_DATA, "initial items must be a bounded list")
    clean: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or not set(item).issubset(INITIAL_ITEM_KEYS):
            raise ControllerError(EXIT_DATA, "initial item contains unsupported/sensitive fields")
        try:
            copied = strict_json_loads(canonical_json(item), "initial item")
        except ControllerError:
            raise
        for key, value in copied.items():
            if isinstance(value, str) and len(value) > (4096 if key == "worktree" else 1000):
                raise ControllerError(EXIT_DATA, f"initial item field is too long: {key}")
        clean.append(copied)
    return clean


def init_runtime(
    ctx: RuntimeContext, project_id: str, policy_commit: str, wave_id: str, run_id: str,
    items: list[dict[str, Any]], facts_adapter: Path, facts_manifest: Path,
) -> dict[str, Any]:
    ctx.validate_policy_commit(policy_commit)
    with runtime_lock(ctx):
        if ctx.state_path.exists() or ctx.lease_path.exists() or ctx.events_path.exists():
            raise ControllerError(EXIT_CONFLICT, "Autopilot runtime already exists")
        state = initial_state(
            ctx, project_id, policy_commit, wave_id, run_id,
            sanitize_initial_items(items), facts_adapter, facts_manifest,
        )
        return write_ahead_transition(ctx, None, state, "runtime_initialized", {"wave_id": wave_id, "run_id": run_id})


def acquire_lease(
    ctx: RuntimeContext, project_id: str, policy_commit: str, owner: str, ttl_seconds: int,
    *, takeover: bool, reason: str | None, now: dt.datetime | None = None,
    after_lease_hook: Callable[[], None] | None = None,
) -> dict[str, Any]:
    ctx.validate_policy_commit(policy_commit)
    if not 10 <= ttl_seconds <= 86400 or not owner.strip() or len(owner) > 200:
        raise ControllerError(EXIT_USAGE, "invalid lease TTL or owner")
    current = now or utc_now()
    with runtime_lock(ctx):
        state, _ = load_state_snapshot(ctx, project_id, policy_commit, recover=True)
        lease = load_lease(ctx, project_id, policy_commit, required=False)
        state, _ = recover_lease_state_gap(ctx, state, lease, recover=True)
        if lease and parse_time(lease["expires_at"]) > current:
            if lease["owner"] != owner:
                raise ControllerError(EXIT_CONFLICT, f"PM lease held by {lease['owner']}")
            return lease
        if lease and (not takeover or not reason or not reason.strip()):
            raise ControllerError(EXIT_CONFLICT, "expired lease requires explicit takeover reason")
        token = state["fencing_token"] + 1
        expires = iso_time(current + dt.timedelta(seconds=ttl_seconds))
        new_lease = {
            "schema_version": 1, "contract": LEASE_CONTRACT, "repo_identity": ctx.repo_identity,
            "project_id": project_id, "policy_commit": policy_commit, "owner": owner,
            "fencing_token": token, "acquired_at": iso_time(current), "expires_at": expires,
        }
        atomic_write_json(ctx.lease_path, new_lease)
        if after_lease_hook:
            after_lease_hook()
        after = copy.deepcopy(state)
        after.update(pm_owner=owner, fencing_token=token, lease_expires_at=expires)
        write_ahead_transition(ctx, state, after, "lease_acquired" if lease is None else "lease_taken_over", {
            "owner": owner, "expires_at": expires, "reason": reason if lease else None,
        })
        return new_lease


def require_lease(
    state: dict[str, Any], lease: dict[str, Any] | None, owner: str, token: int,
    *, current: dt.datetime | None = None, min_remaining_seconds: int = 0,
) -> dict[str, Any]:
    if type(token) is not int or token < 1:
        raise ControllerError(EXIT_USAGE, "fencing token must be positive integer")
    assert_lease_state_consistency(state, lease)
    if lease is None or lease["owner"] != owner or lease["fencing_token"] != token:
        raise ControllerError(EXIT_CONFLICT, "stale PM owner or fencing token")
    remaining = (parse_time(lease["expires_at"]) - (current or utc_now())).total_seconds()
    if remaining <= min_remaining_seconds:
        raise ControllerError(EXIT_CONFLICT, f"lease remaining {remaining:.3f}s <= required {min_remaining_seconds}s")
    return lease


def renew_lease(
    ctx: RuntimeContext, project_id: str, policy_commit: str, owner: str, token: int,
    ttl_seconds: int, *, now: dt.datetime | None = None,
    after_lease_hook: Callable[[], None] | None = None,
) -> dict[str, Any]:
    ctx.validate_policy_commit(policy_commit)
    if not 10 <= ttl_seconds <= 86400:
        raise ControllerError(EXIT_USAGE, "invalid lease TTL")
    current = now or utc_now()
    with runtime_lock(ctx):
        state, _ = load_state_snapshot(ctx, project_id, policy_commit, recover=True)
        lease = load_lease(ctx, project_id, policy_commit)
        state, _ = recover_lease_state_gap(ctx, state, lease, recover=True)
        require_lease(state, lease, owner, token, current=current)
        assert lease is not None
        updated = copy.deepcopy(lease)
        new_expiry = current + dt.timedelta(seconds=ttl_seconds)
        if new_expiry <= parse_time(lease["expires_at"]):
            raise ControllerError(EXIT_USAGE, "lease renewal must monotonically extend expiry")
        updated["expires_at"] = iso_time(new_expiry)
        atomic_write_json(ctx.lease_path, updated)
        if after_lease_hook:
            after_lease_hook()
        after = copy.deepcopy(state)
        after["lease_expires_at"] = updated["expires_at"]
        write_ahead_transition(ctx, state, after, "lease_renewed", {"owner": owner, "expires_at": updated["expires_at"]})
        return updated


def build_facts_request(
    ctx: RuntimeContext, state: dict[str, Any], *, timeout_seconds: int,
) -> dict[str, Any]:
    issued = utc_now()
    deadline = issued + dt.timedelta(seconds=timeout_seconds)
    return {
        "schema_version": 1, "contract": FACTS_REQUEST_CONTRACT,
        "request_id": "facts_" + secrets.token_hex(16),
        "adapter_sha256": state["facts_adapter"]["sha256"],
        "manifest_sha256": state["facts_manifest"]["sha256"],
        "issued_at": iso_time(issued), "deadline": iso_time(deadline),
        "repo": {"root": str(ctx.repo), "common_dir": str(ctx.common_dir), "identity": ctx.repo_identity},
        "project": {"project_id": state["project_id"], "policy_commit": state["policy_commit"]},
        "run_id": state["run_id"],
        "items": [{key: item.get(key) for key in (
            "task_id", "attempt", "dispatch_id", "orca_task_id", "branch", "worktree", "provider", "pr_number",
            "pr_head_oid",
        )} for item in state["items"] if item.get("status") != "COMPLETE"],
    }


def run_facts_adapter(ctx: RuntimeContext, state: dict[str, Any], *, timeout_seconds: int) -> tuple[dict[str, Any], dict[str, Any]]:
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
        raise ControllerError(EXIT_USAGE, "facts timeout must be 1..300")
    adapter = verify_pinned_file(state["facts_adapter"], "facts adapter", executable=True)
    manifest = verify_pinned_file(state["facts_manifest"], "facts manifest", executable=False)
    request = build_facts_request(ctx, state, timeout_seconds=timeout_seconds)
    try:
        result = subprocess.run(
            [str(adapter), "--manifest", str(manifest)], input=canonical_json(request),
            capture_output=True, timeout=timeout_seconds, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ControllerError(EXIT_CONFLICT, "facts adapter timed out") from exc
    except OSError as exc:
        raise ControllerError(EXIT_IO, f"facts adapter failed: {exc}") from exc
    if result.returncode != 0:
        raise ControllerError(EXIT_CONFLICT, f"facts adapter returned {result.returncode}")
    if len(result.stdout) > MAX_JSON_BYTES:
        raise ControllerError(EXIT_DATA, "facts response too large")
    facts = strict_json_loads(result.stdout, "facts response")
    if not isinstance(facts, dict):
        raise ControllerError(EXIT_DATA, "facts response must be object")
    return facts, request


def validate_facts(
    facts: dict[str, Any], ctx: RuntimeContext, project_id: str, policy_commit: str,
    state: dict[str, Any], *, request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_schema(facts, FACTS_CONTRACT, "facts")
    _validate_identity(facts, ctx, project_id, policy_commit, "facts")
    if any((
        facts.get("run_id") != state["run_id"],
        facts.get("adapter_sha256") != state["facts_adapter"]["sha256"],
        facts.get("manifest_sha256") != state["facts_manifest"]["sha256"],
    )):
        raise ControllerError(EXIT_CONFIG, "facts run/adapter/manifest identity mismatch")
    if request is None:
        raise ControllerError(EXIT_CONFIG, "trusted facts request binding is required")
    if any((
        facts.get("request_id") != request["request_id"],
        facts.get("issued_at") != request["issued_at"],
        facts.get("deadline") != request["deadline"],
    )):
        raise ControllerError(EXIT_CONFIG, "facts request/freshness identity mismatch")
    if not isinstance(facts.get("request_id"), str) or not facts["request_id"]:
        raise ControllerError(EXIT_DATA, "facts request_id missing")
    issued = parse_time(facts.get("issued_at"))
    deadline = parse_time(facts.get("deadline"))
    started = parse_time(facts.get("started_at"))
    finished = parse_time(facts.get("finished_at"))
    observed = parse_time(facts.get("observed_at"))
    if not (issued <= started <= finished == observed <= deadline):
        raise ControllerError(EXIT_DATA, "facts freshness interval is inconsistent")
    if utc_now() > deadline + dt.timedelta(seconds=5):
        raise ControllerError(EXIT_CONFLICT, "facts snapshot expired before reconcile")
    if not isinstance(facts.get("items"), list):
        raise ControllerError(EXIT_DATA, "facts.items must be list")
    seen: set[str] = set()
    roots = ctx.registered_worktrees()
    for item in facts["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("task_id"), str) or item["task_id"] in seen:
            raise ControllerError(EXIT_DATA, "facts item malformed or duplicated")
        seen.add(item["task_id"])
        git_facts = item.get("git", {}) if isinstance(item.get("git"), dict) else {}
        if git_facts.get("worktree_count") == 1:
            try:
                resolved = Path(git_facts["worktree"]).resolve(strict=True)
            except (KeyError, OSError) as exc:
                raise ControllerError(EXIT_CONFIG, f"facts worktree unavailable for {item['task_id']}") from exc
            if resolved not in roots:
                raise ControllerError(EXIT_CONFIG, f"facts worktree not registered for {item['task_id']}")
            git_facts["worktree"] = str(resolved)
    return facts


def _fact_value(item: dict[str, Any], section: str, key: str, allowed: set[Any]) -> Any:
    value = item.get(section, {}).get(key) if isinstance(item.get(section), dict) else None
    if allowed == {True, False, "unknown"} and value != "unknown" and type(value) is not bool:
        raise ControllerError(EXIT_DATA, f"facts {item.get('task_id')} {section}.{key} must be bool/unknown")
    if value not in allowed:
        raise ControllerError(EXIT_DATA, f"facts {item.get('task_id')} {section}.{key} invalid")
    return value


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 1000


def _full_oid(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value) is not None


def _sha256_digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _load_acceptance_recovery():
    """加载 acceptance-recovery.py——验收失败的单一机械分类合同。"""
    module_path = Path(__file__).resolve().parent / "acceptance-recovery.py"
    spec_loader = importlib.util.spec_from_file_location("acceptance_recovery_runtime", module_path)
    module = importlib.util.module_from_spec(spec_loader)
    spec_loader.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _fail_action(
    task_id: str, reason: str, action: str = "hard_park", failure_class: str = "safety_unknown",
) -> dict[str, Any]:
    return {
        "task_id": task_id, "action": action, "reason": reason,
        "external_mutation": False, "target": {}, "failure_class": failure_class,
    }


def _plan_repair_action(task_id: str, runtime_item: dict[str, Any]) -> dict[str, Any]:
    """验收失败（checks==fail）按机械分类合同规划动作。

    internal_recoverable 且修复预算未耗尽 → 内部动作 repair_acceptance
    （不泊车，PM 按 15-wave-autopilot §6 派发修复/独立 re-review）；预算
    耗尽 → hard_park（internal_recoverable 类，原因注明预算耗尽）。
    """
    recovery = _load_acceptance_recovery()
    used = runtime_item.get("repair_attempts", 0)
    if type(used) is not int or used < 0:
        used = 0
    outcome = recovery.classify_failure("pr_checks_failed", used)
    if outcome["action"] == recovery.ACTION_PARK:
        return _fail_action(
            task_id, f"acceptance checks failed: {outcome['park_reason']}",
            failure_class=outcome["failure_class"],
        )
    return _action(
        task_id, "repair_acceptance",
        "acceptance checks failed: internal_recoverable "
        f"({outcome['action']}, repair episode {used + 1}/{outcome['max_repair_attempts']})",
        {
            "task_id": task_id, "repair_step": outcome["action"],
            "repair_attempts_used": used,
            "max_repair_attempts": outcome["max_repair_attempts"],
        },
        False,
    )


def _action(task_id: str, action: str, reason: str, target: dict[str, Any], external: bool) -> dict[str, Any]:
    return {"task_id": task_id, "action": action, "reason": reason, "external_mutation": external, "target": target}


def _exact_target(action: str, state: dict[str, Any], runtime_item: dict[str, Any], fact: dict[str, Any]) -> dict[str, Any]:
    dispatch, git_facts, pr = fact.get("dispatch", {}), fact.get("git", {}), fact.get("pr", {})
    project = fact.get("project", {}) if isinstance(fact.get("project"), dict) else {}
    verification = fact.get("verification", {}) if isinstance(fact.get("verification"), dict) else {}
    common = {
        "task_id": runtime_item["task_id"], "attempt": runtime_item.get("attempt", 1),
        "run_id": state["run_id"],
    }
    if action == "spawn":
        target = {
            **common, "orca_task_id": runtime_item.get("orca_task_id"),
            "branch": runtime_item.get("branch"), "worktree": runtime_item.get("worktree"),
            "provider": runtime_item.get("provider"),
        }
        if not all(_nonempty(target.get(key)) for key in ("orca_task_id", "branch", "worktree", "provider")):
            raise ControllerError(EXIT_DATA, "spawn target lacks Orca task/branch/worktree/provider")
        return target
    if action == "settle":
        if not _nonempty(dispatch.get("id")) or dispatch.get("liveness") != "dead":
            raise ControllerError(EXIT_DATA, "settle requires exact dispatch and liveness=dead")
        if not _nonempty(runtime_item.get("provider")):
            raise ControllerError(EXIT_DATA, "settle requires exact provider identity")
        return {**common, "dispatch_id": dispatch["id"], "provider": runtime_item["provider"]}
    if action == "verify":
        if not _nonempty(dispatch.get("id")) or not _nonempty(git_facts.get("worktree")) or not _full_oid(git_facts.get("local_oid")):
            raise ControllerError(EXIT_DATA, "verify lacks exact dispatch/worktree/OID")
        if not _sha256_digest(verification.get("evidence_sha256")) or not _sha256_digest(verification.get("gate_contract_sha256")):
            raise ControllerError(EXIT_DATA, "verify lacks exact evidence/gate contract digest")
        return {
            **common, "dispatch_id": dispatch["id"], "worktree": git_facts["worktree"],
            "local_oid": git_facts["local_oid"],
            "evidence_sha256": verification["evidence_sha256"],
            "gate_contract_sha256": verification["gate_contract_sha256"],
        }
    if action == "push":
        if (
            not _nonempty(git_facts.get("worktree")) or not _nonempty(git_facts.get("branch"))
            or not _nonempty(git_facts.get("remote")) or not _full_oid(git_facts.get("local_oid"))
        ):
            raise ControllerError(EXIT_DATA, "push lacks exact worktree/branch/remote/OID")
        return {
            **common, "worktree": git_facts["worktree"], "branch": git_facts["branch"],
            "remote": git_facts["remote"], "local_oid": git_facts["local_oid"],
        }
    if action == "open_pr":
        if not _nonempty(git_facts.get("branch")) or not _nonempty(pr.get("base_branch")) or not _full_oid(git_facts.get("local_oid")):
            raise ControllerError(EXIT_DATA, "open_pr lacks exact head/base/OID")
        return {**common, "head_branch": git_facts["branch"], "base_branch": pr["base_branch"], "head_oid": git_facts["local_oid"]}
    if action == "merge":
        required_checks = pr.get("required_checks")
        approvals = pr.get("approvals")
        required_approvals = pr.get("required_approvals")
        evidence_sha256 = verification.get("evidence_sha256")
        gate_contract_sha256 = verification.get("gate_contract_sha256")
        valid = (
            type(pr.get("number")) is int and pr["number"] > 0 and pr.get("checks") == "pass"
            and pr.get("mergeable") is True and pr.get("approvals_known") is True
            and type(approvals) is int and type(required_approvals) is int
            and approvals >= required_approvals >= 0
            and isinstance(required_checks, list)
            and all(isinstance(context, str) and context for context in required_checks)
            and _full_oid(pr.get("head_oid")) and _nonempty(pr.get("head_branch")) and _nonempty(pr.get("base_branch"))
            and pr.get("head_branch") == git_facts.get("branch")
            and pr.get("head_oid") in {git_facts.get("local_oid"), git_facts.get("remote_oid")}
            and verification.get("passed") is True
            and verification.get("local_oid") == pr.get("head_oid")
            and _sha256_digest(evidence_sha256) and _sha256_digest(gate_contract_sha256)
            and project.get("evidence_sha256") == evidence_sha256
        )
        if not valid:
            raise ControllerError(EXIT_DATA, "merge requires exact checks/approvals/head verification and evidence/gate binding")
        return {
            **common, "pr_number": pr["number"], "head_oid": pr["head_oid"],
            "head_branch": pr["head_branch"], "base_branch": pr["base_branch"],
            "required_checks": sorted(required_checks),
            "required_approvals": required_approvals,
            "evidence_sha256": evidence_sha256,
            "gate_contract_sha256": gate_contract_sha256,
        }
    if action == "writeback":
        if not _full_oid(pr.get("merge_commit")) or not _sha256_digest(project.get("evidence_sha256")):
            raise ControllerError(EXIT_DATA, "writeback requires exact merge commit/evidence")
        return {
            **common, "merge_commit": pr["merge_commit"], "policy_commit": state["policy_commit"],
            "evidence_sha256": project["evidence_sha256"],
        }
    raise ControllerError(EXIT_SOFTWARE, f"no target contract for {action}")


def plan_action(state: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    if facts.get("ambiguous") is True:
        return _fail_action("*", "external facts ambiguous")
    by_task = {item["task_id"]: item for item in facts["items"]}
    for runtime_item in state["items"]:
        if runtime_item.get("status") == "COMPLETE" or runtime_item.get("released") is True:
            continue
        task_id = runtime_item["task_id"]
        item = by_task.get(task_id)
        if item is None:
            return _fail_action(task_id, "external facts missing")
        dispatch = _fact_value(item, "dispatch", "status", {"missing", "active", "completed", "failed", "unknown"})
        dispatch_id = item.get("dispatch", {}).get("id")
        if dispatch == "unknown" or dispatch in {"active", "completed", "failed"} and not _nonempty(dispatch_id):
            return _fail_action(task_id, "Dispatch status/id unknown")
        if dispatch == "active":
            return _action(task_id, "observe", "active exact Dispatch is authoritative", {"dispatch_id": dispatch_id}, False)
        git_facts = item.get("git", {}) if isinstance(item.get("git"), dict) else {}
        count = git_facts.get("worktree_count")
        if count != "unknown" and (type(count) is not int or count < 0):
            raise ControllerError(EXIT_DATA, "worktree_count invalid")
        if count == "unknown":
            return _fail_action(task_id, "worktree identity unknown")
        if count > 1:
            return _fail_action(task_id, "duplicate worktrees", "reject_duplicate")
        dirty = _fact_value(item, "git", "dirty", {True, False, "unknown"})
        branch_matches = _fact_value(item, "git", "branch_matches", {True, False, "unknown"})
        pr_state = _fact_value(item, "pr", "state", {"none", "open", "merged", "unknown"})
        checks = _fact_value(item, "pr", "checks", {"not_applicable", "pass", "fail", "pending", "unknown"})
        project_status = _fact_value(item, "project", "status", {"ready", "in_progress", "complete", "unknown"})
        writeback = _fact_value(item, "project", "writeback_applied", {True, False, "unknown"})
        if branch_matches == "unknown" or pr_state == "unknown" or project_status == "unknown" or writeback == "unknown":
            return _fail_action(task_id, "Git/PR/project facts unknown")
        if pr_state in {"open", "merged"} and checks == "unknown":
            return _fail_action(task_id, "checks unknown: facts ambiguous (safety_unknown)")
        if checks == "fail":
            # v2.14.0：验收失败不再硬编码泊车——先按 acceptance-recovery 分类，
            # internal_recoverable 预算未耗尽时规划 repair_acceptance。
            return _plan_repair_action(task_id, runtime_item)
        if project_status == "complete" and pr_state != "merged":
            return _fail_action(task_id, "project completion conflicts with PR")
        provider_status = item.get("provider", {}).get("status", "unknown") if isinstance(item.get("provider"), dict) else "unknown"
        if state["state"] == "WAITING_PROVIDER_RESET" or provider_status == "waiting_reset":
            return _action(task_id, "retry_later", "provider reset needs explicit resume", {}, False)
        if provider_status not in {"available", "not_applicable"}:
            return _fail_action(task_id, "provider unknown")
        if pr_state == "merged":
            if writeback is True:
                return _action(task_id, "complete", "merge/writeback confirmed", {"merge_commit": item.get("pr", {}).get("merge_commit")}, False)
            action = "writeback"
        elif pr_state == "open":
            if checks == "pending":
                return _action(task_id, "observe", "checks pending", {"pr_number": item.get("pr", {}).get("number")}, False)
            action = "merge"
        elif dispatch == "completed":
            published = _fact_value(item, "git", "published", {True, False, "unknown"})
            verified = _fact_value(item, "verification", "passed", {True, False, "unknown"})
            if published == "unknown" or verified == "unknown":
                return _fail_action(task_id, "publish/verification unknown")
            action = "verify" if not verified else "push" if not published else "open_pr"
        elif dispatch == "failed":
            action = "settle"
        elif count == 1:
            if branch_matches is not True:
                return _fail_action(task_id, "worktree branch mismatch")
            target = {"worktree": git_facts.get("worktree"), "branch": git_facts.get("branch")}
            if runtime_item.get("adopted_target_digest") == object_hash(target):
                return _action(task_id, "observe", "worktree already adopted", target, False)
            if dirty is not False:
                return _fail_action(task_id, "dirty/unknown worktree cannot be adopted")
            return _action(task_id, "adopt", "one exact worktree adopted", target, False)
        else:
            action = "spawn"
        if action in DANGEROUS_DIRTY_ACTIONS and dirty is not False:
            return _fail_action(task_id, f"dirty/unknown blocks {action}")
        try:
            target = _exact_target(action, state, runtime_item, item)
        except ControllerError as exc:
            if exc.code == EXIT_DATA:
                return _fail_action(task_id, exc.message)
            raise
        return _action(task_id, action, "exact next action", target, True)
    return _action("*", "complete", "all items complete/released", {}, False)


def _absorb_facts(state: dict[str, Any], facts: dict[str, Any], action: dict[str, Any]) -> None:
    by_task = {item["task_id"]: item for item in facts["items"]}
    for runtime_item in state["items"]:
        fact = by_task.get(runtime_item["task_id"])
        if not fact:
            continue
        dispatch, git_facts, pr = fact.get("dispatch", {}), fact.get("git", {}), fact.get("pr", {})
        provider = fact.get("provider", {}) if isinstance(fact.get("provider"), dict) else {}
        verification = fact.get("verification", {}) if isinstance(fact.get("verification"), dict) else {}
        runtime_item.update({
            "dispatch_id": dispatch.get("id"), "dispatch_status": dispatch.get("status"),
            "worktree": git_facts.get("worktree") or runtime_item.get("worktree"),
            "branch": git_facts.get("branch") or runtime_item.get("branch"),
            "local_oid": git_facts.get("local_oid"), "remote_oid": git_facts.get("remote_oid"),
            "pr_number": pr.get("number"), "pr_state": pr.get("state"),
            "pr_head_oid": pr.get("head_oid"),
            "merge_commit": pr.get("merge_commit"), "observed_at": facts["observed_at"],
            "dirty": git_facts.get("dirty"), "worktree_count": git_facts.get("worktree_count"),
            "published": git_facts.get("published"), "checks": pr.get("checks"),
            "mergeable": pr.get("mergeable"), "approvals": pr.get("approvals"),
            "approvals_known": pr.get("approvals_known"),
            "required_approvals": pr.get("required_approvals"),
            "provider_status": provider.get("status"),
            "verification_passed": verification.get("passed"),
            "evidence_sha256": verification.get("evidence_sha256"),
            "gate_contract_sha256": verification.get("gate_contract_sha256"),
        })
        if runtime_item["task_id"] == action["task_id"]:
            runtime_item["next_action"] = action["action"]
            if action["action"] == "adopt":
                runtime_item["adopted_target_digest"] = object_hash(action["target"])


def idempotency_key(state: dict[str, Any], action: dict[str, Any]) -> tuple[str, str]:
    digest = object_hash(action["target"])
    return object_hash({
        "project_id": state["project_id"], "wave_id": state["wave_id"],
        "run_id": state["run_id"],
        "task_id": action["task_id"], "action": action["action"],
        "policy_commit": state["policy_commit"], "target_digest": digest,
    }), digest


def _pending_fact(pending: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any] | None:
    task_id = pending.get("task_id")
    target = pending.get("target")
    if not isinstance(target, dict) or not isinstance(task_id, str):
        raise ControllerError(EXIT_DATA, "pending intent target/task is malformed")
    matches = [item for item in facts["items"] if item.get("task_id") == task_id]
    if len(matches) != 1 or matches[0].get("attempt", 1) != target.get("attempt", 1):
        return None
    return matches[0]


def _decision_evidence(facts: dict[str, Any], task_id: str) -> dict[str, Any]:
    item = next((candidate for candidate in facts["items"] if candidate.get("task_id") == task_id), None)
    sections = {}
    if isinstance(item, dict):
        for key in ("attempt", "dispatch", "git", "pr", "project", "provider", "verification"):
            if key in item:
                sections[key] = copy.deepcopy(item[key])
    return {
        "request_id": facts.get("request_id"), "observed_at": facts.get("observed_at"),
        "task_id": task_id, "facts": sections,
    }


def _facts_after_pending(pending: dict[str, Any], facts: dict[str, Any]) -> bool:
    anchor = pending.get("receipt_recorded_at") or pending.get("started_at") or pending.get("planned_at")
    original_request = pending.get("facts_request_id")
    return (
        isinstance(original_request, str) and facts.get("request_id") != original_request
        and parse_time(facts.get("observed_at")) >= parse_time(anchor)
    )


def pending_intent_converged(pending: dict[str, Any], facts: dict[str, Any]) -> bool:
    """Accept only mutation-specific, independently observed after-facts.

    A receipt records adapter acceptance, not external convergence.  The
    pending intent remains authoritative across transient/ambiguous snapshots
    until the exact target is visible in a snapshot at or after the intent.
    """
    if facts.get("ambiguous") is True or not _facts_after_pending(pending, facts):
        return False
    item = _pending_fact(pending, facts)
    if item is None:
        return False
    target = pending["target"]
    action = pending.get("action")
    dispatch = item.get("dispatch", {}) if isinstance(item.get("dispatch"), dict) else {}
    git_facts = item.get("git", {}) if isinstance(item.get("git"), dict) else {}
    pr = item.get("pr", {}) if isinstance(item.get("pr"), dict) else {}
    project = item.get("project", {}) if isinstance(item.get("project"), dict) else {}
    provider = item.get("provider", {}) if isinstance(item.get("provider"), dict) else {}
    verification = item.get("verification", {}) if isinstance(item.get("verification"), dict) else {}
    if action == "spawn":
        return (
            _nonempty(target.get("orca_task_id")) and _nonempty(dispatch.get("id"))
            and dispatch.get("status") in {"active", "completed", "failed"}
        )
    if action == "settle":
        return (
            dispatch.get("id") == target.get("dispatch_id")
            and (
                dispatch.get("status") == "missing"
                or dispatch.get("status") == "completed" and dispatch.get("liveness") == "settled"
            )
            and provider.get("identity") == target.get("provider")
            and provider.get("status") in {"available", "not_applicable"}
        )
    if action == "verify":
        return (
            git_facts.get("local_oid") == target.get("local_oid")
            and verification.get("passed") is True
            and verification.get("local_oid") == target.get("local_oid")
            and verification.get("evidence_sha256") == target.get("evidence_sha256")
            and verification.get("gate_contract_sha256") == target.get("gate_contract_sha256")
        )
    if action == "push":
        return (
            git_facts.get("published") is True
            and git_facts.get("remote_oid") == target.get("local_oid")
            and git_facts.get("branch") == target.get("branch")
            and git_facts.get("remote") == target.get("remote")
        )
    if action == "open_pr":
        return (
            type(pr.get("number")) is int and pr["number"] > 0
            and pr.get("state") in {"open", "merged"}
            and pr.get("head_oid") == target.get("head_oid")
            and pr.get("head_branch") == target.get("head_branch")
            and pr.get("base_branch") == target.get("base_branch")
        )
    if action == "merge":
        return (
            pr.get("state") == "merged" and pr.get("number") == target.get("pr_number")
            and pr.get("head_oid") == target.get("head_oid")
            and pr.get("head_branch") == target.get("head_branch")
            and pr.get("base_branch") == target.get("base_branch")
            and _full_oid(pr.get("merge_commit"))
            and verification.get("passed") is True
            and verification.get("local_oid") == target.get("head_oid")
            and verification.get("evidence_sha256") == target.get("evidence_sha256")
            and verification.get("gate_contract_sha256") == target.get("gate_contract_sha256")
        )
    if action == "writeback":
        expected = {
            "task_id": target.get("task_id"), "merge_commit": target.get("merge_commit"),
            "policy_commit": target.get("policy_commit"),
            "evidence_sha256": target.get("evidence_sha256"),
        }
        return project.get("writeback_applied") is True and project.get("writeback_target") == expected
    raise ControllerError(EXIT_DATA, f"pending intent action is unsupported: {action!r}")


def _pending_wait_result(
    ctx: RuntimeContext, state: dict[str, Any], after: dict[str, Any], action: dict[str, Any],
    old: dict[str, Any], token: int, facts: dict[str, Any], recovered: bool,
) -> dict[str, Any]:
    after["pending_intent"] = copy.deepcopy(old)
    status_value = old.get("status")
    if status_value == "planned":
        after["pending_intent"]["ready"] = False
        if old.get("fencing_token") != token:
            after["pending_intent"].update(fencing_token=token, refenced_at=iso_time(utc_now()))
    for item in after["items"]:
        if item.get("task_id") == old.get("task_id"):
            item["next_action"] = "await_external_fact" if status_value != "planned" else "await_revalidation"
    observed_evidence = _decision_evidence(facts, str(old.get("task_id")))
    committed = write_ahead_transition(ctx, state, after, "pending_intent_preserved", {
        "task_id": old.get("task_id"), "action": old.get("action"),
        "idempotency_key": old.get("idempotency_key"), "status": status_value,
        "transient_plan": action.get("action"),
        "observed_evidence": observed_evidence,
        "observed_evidence_sha256": object_hash(observed_evidence),
    })
    disposition = "await_revalidation" if status_value == "planned" else "await_external_fact"
    wait_action = _action(
        str(old.get("task_id")), "observe", "pending mutation awaits exact after-fact convergence",
        {"idempotency_key": old.get("idempotency_key"), "target_digest": old.get("target_digest")}, False,
    )
    return {
        "planned_action": wait_action, "pending_intent": committed["pending_intent"],
        "disposition": disposition, "recovered": recovered,
    }


def _reconcile_locked(ctx: RuntimeContext, state: dict[str, Any], token: int, facts: dict[str, Any], recovered: bool) -> dict[str, Any]:
    action = plan_action(state, facts)
    if action["action"] not in ALLOWED_ACTIONS:
        raise ControllerError(EXIT_SOFTWARE, "planner emitted unsupported action")
    after = copy.deepcopy(state)
    _absorb_facts(after, facts, action)
    old = state.get("pending_intent")
    if isinstance(old, dict):
        if old.get("status") not in {"planned", "started", "uncertain", "receipt_recorded"}:
            raise ControllerError(EXIT_DATA, "pending intent status is unsupported")
        if pending_intent_converged(old, facts):
            after["pending_intent"] = None
            if old.get("action") == "settle":
                for item in after["items"]:
                    if item.get("task_id") == old.get("task_id"):
                        item["released"] = True
                        item["next_action"] = None
            after_evidence = _decision_evidence(facts, str(old.get("task_id")))
            converged = write_ahead_transition(ctx, state, after, "pending_intent_converged", {
                "task_id": old.get("task_id"), "action": old.get("action"),
                "idempotency_key": old.get("idempotency_key"),
                "target_digest": old.get("target_digest"),
                "before_evidence_sha256": old.get("before_evidence_sha256"),
                "after_evidence": after_evidence,
                "after_evidence_sha256": object_hash(after_evidence),
            })
            result = _reconcile_locked(ctx, converged, token, facts, recovered)
            result["converged_intent"] = {
                "task_id": old.get("task_id"), "action": old.get("action"),
                "idempotency_key": old.get("idempotency_key"),
            }
            return result
        if action["external_mutation"]:
            key, _ = idempotency_key(state, action)
            if old.get("status") == "planned" and old.get("idempotency_key") == key:
                changed = (
                    old.get("fencing_token") != token or old.get("ready") is not True
                    or old.get("facts_request_id") != facts.get("request_id")
                    or old.get("facts_deadline") != facts.get("deadline")
                )
                if changed:
                    before_evidence = _decision_evidence(facts, action["task_id"])
                    after["pending_intent"] = copy.deepcopy(old)
                    after["pending_intent"].update(
                        fencing_token=token, ready=True, refenced_at=iso_time(utc_now()),
                        facts_request_id=facts["request_id"], facts_issued_at=facts["issued_at"],
                        facts_deadline=facts["deadline"], facts_observed_at=facts["observed_at"],
                        before_evidence=before_evidence,
                        before_evidence_sha256=object_hash(before_evidence),
                    )
                    committed = write_ahead_transition(ctx, state, after, "planned_intent_refenced", {
                        "task_id": action["task_id"], "idempotency_key": key,
                        "old_fencing_token": old.get("fencing_token"), "new_fencing_token": token,
                    })
                    return {
                        "planned_action": action, "pending_intent": committed["pending_intent"],
                        "disposition": "ready", "recovered": recovered,
                    }
                return {"planned_action": action, "pending_intent": old, "disposition": "ready", "recovered": recovered}
        return _pending_wait_result(ctx, state, after, action, old, token, facts, recovered)
    if action["external_mutation"]:
        key, target_digest = idempotency_key(state, action)
        before_evidence = _decision_evidence(facts, action["task_id"])
        after["pending_intent"] = {
            "schema_version": 1, "idempotency_key": key, "target_digest": target_digest,
            "target": action["target"], "task_id": action["task_id"], "action": action["action"],
            "status": "planned", "ready": True, "fencing_token": token, "planned_at": iso_time(utc_now()),
            "facts_request_id": facts["request_id"], "facts_issued_at": facts["issued_at"],
            "facts_deadline": facts["deadline"], "facts_observed_at": facts["observed_at"],
            "before_evidence": before_evidence,
            "before_evidence_sha256": object_hash(before_evidence),
        }
        after["state"] = {"spawn": "DISPATCHING", "settle": "RUNNING", "verify": "VERIFYING", "push": "VERIFYING", "open_pr": "MERGING", "merge": "MERGING", "writeback": "WRITEBACK"}[action["action"]]
        committed = write_ahead_transition(ctx, state, after, "intent_planned", {"task_id": action["task_id"], "action": action["action"], "idempotency_key": key, "target_digest": target_digest})
        return {"planned_action": action, "pending_intent": committed["pending_intent"], "disposition": "ready", "recovered": recovered}
    after["pending_intent"] = None
    if action["action"] in {"hard_park", "reject_duplicate"}:
        after.update(state="ERROR_RECONCILE_REQUIRED", parking_code="FACTS_FAIL_CLOSED", parking_detail=action["reason"])
    elif action["action"] == "retry_later":
        after.update(state="WAITING_PROVIDER_RESET", parking_code="WAITING_PROVIDER_RESET", parking_detail=action["reason"])
    elif action["action"] == "repair_acceptance":
        # 内部可恢复：不泊车，保持 RUNNING 等待修复收敛。修复预算按「失败
        # episode」计数——以 absorb 前的 state（非 after）判断是否为一次新的
        # 进入：同一 episode 内的重复 reconcile 不重复计数（修复在途 ≠ 新失败）。
        after["state"] = "RUNNING"
        previous = next((item for item in state["items"] if item.get("task_id") == action["task_id"]), {})
        for item in after["items"]:
            if item.get("task_id") == action["task_id"]:
                if previous.get("next_action") != "repair_acceptance":
                    item["repair_attempts"] = item.get("repair_attempts", 0) + 1
                item["next_action"] = "repair_acceptance"
    elif action["action"] in {"adopt", "observe"}:
        after["state"] = "RUNNING"
    elif action["action"] == "complete":
        for item in after["items"]:
            if action["task_id"] == "*" or item["task_id"] == action["task_id"]:
                item.update(status="COMPLETE", next_action=None)
        after["state"] = "COMPLETE" if all(item.get("status") == "COMPLETE" or item.get("released") is True for item in after["items"]) else "RUNNING"
    committed = write_ahead_transition(ctx, state, after, "reconciled", {"task_id": action["task_id"], "action": action["action"], "reason": action["reason"]})
    return {"planned_action": action, "pending_intent": committed.get("pending_intent"), "disposition": "internal_only", "recovered": recovered}


def reconcile(
    ctx: RuntimeContext, project_id: str, policy_commit: str, owner: str, token: int,
    facts: dict[str, Any], *, request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ctx.validate_policy_commit(policy_commit)
    with runtime_lock(ctx):
        state, recovered = load_state_snapshot(ctx, project_id, policy_commit, recover=True)
        lease = load_lease(ctx, project_id, policy_commit)
        state, lease_recovered = recover_lease_state_gap(ctx, state, lease, recover=True)
        recovered = recovered or lease_recovered
        require_lease(state, lease, owner, token)
        validate_facts(facts, ctx, project_id, policy_commit, state, request=request)
        return _reconcile_locked(ctx, state, token, facts, recovered)


def collect_and_reconcile(
    ctx: RuntimeContext, project_id: str, policy_commit: str, owner: str, token: int,
    *, timeout_seconds: int = 30,
) -> dict[str, Any]:
    ctx.validate_policy_commit(policy_commit)
    with runtime_lock(ctx):
        state, recovered = load_state_snapshot(ctx, project_id, policy_commit, recover=True)
        lease = load_lease(ctx, project_id, policy_commit)
        state, lease_recovered = recover_lease_state_gap(ctx, state, lease, recover=True)
        recovered = recovered or lease_recovered
        require_lease(state, lease, owner, token, min_remaining_seconds=timeout_seconds + MUTATION_SAFETY_SECONDS)
        facts, request = run_facts_adapter(ctx, state, timeout_seconds=timeout_seconds)
        validate_facts(facts, ctx, project_id, policy_commit, state, request=request)
        return _reconcile_locked(ctx, state, token, facts, recovered)


def execute_tick(
    ctx: RuntimeContext, project_id: str, policy_commit: str, owner: str, token: int,
    adapter: Path, *, timeout_seconds: int = 60, after_adapter_hook: Callable[[], None] | None = None,
) -> dict[str, Any]:
    ctx.validate_policy_commit(policy_commit)
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600:
        raise ControllerError(EXIT_USAGE, "tick timeout must be 1..3600 seconds")
    requested_adapter = resolve_pinned_file(adapter, executable=True)
    with runtime_lock(ctx):
        state, recovered = load_state_snapshot(ctx, project_id, policy_commit, recover=True)
        lease = load_lease(ctx, project_id, policy_commit)
        state, lease_recovered = recover_lease_state_gap(ctx, state, lease, recover=True)
        recovered = recovered or lease_recovered
        require_lease(state, lease, owner, token, min_remaining_seconds=timeout_seconds + MUTATION_SAFETY_SECONDS)
        pending = state.get("pending_intent")
        sealed_adapter = state.get("mutation_adapter")
        if sealed_adapter is not None and sealed_adapter != requested_adapter:
            raise ControllerError(EXIT_CONFIG, "mutation adapter differs from sealed path/digest")
        if not isinstance(pending, dict):
            return {"disposition": "no_pending_intent", "mutation_count": 0, "recovered": recovered}
        if pending.get("fencing_token") != token:
            raise ControllerError(EXIT_CONFLICT, "pending intent has stale token")
        if pending.get("status") == "receipt_recorded":
            return {"disposition": "await_external_fact", "mutation_count": 0, "pending_intent": pending, "recovered": recovered}
        if pending.get("status") != "planned":
            raise ControllerError(EXIT_CONFLICT, "pending mutation outcome uncertain")
        if pending.get("ready", True) is not True:
            raise ControllerError(EXIT_CONFLICT, "pending mutation requires fresh exact revalidation")
        deadline_value = pending.get("facts_deadline")
        if utc_now() > parse_time(deadline_value):
            after_expiry = copy.deepcopy(state)
            after_expiry["pending_intent"].update(
                ready=False, expired_at=iso_time(utc_now()),
            )
            write_ahead_transition(ctx, state, after_expiry, "planned_intent_facts_expired", {
                "task_id": pending.get("task_id"), "action": pending.get("action"),
                "idempotency_key": pending.get("idempotency_key"),
                "facts_request_id": pending.get("facts_request_id"), "facts_deadline": deadline_value,
            })
            raise ControllerError(EXIT_CONFLICT, "planned mutation facts deadline expired; fresh reconcile required")
        if state.get("mutation_adapter") is None:
            after_binding = copy.deepcopy(state)
            after_binding["mutation_adapter"] = requested_adapter
            state = write_ahead_transition(ctx, state, after_binding, "mutation_adapter_sealed", {
                "path": requested_adapter["path"], "sha256": requested_adapter["sha256"],
            })
            pending = state["pending_intent"]
        adapter = verify_pinned_file(state["mutation_adapter"], "mutation adapter", executable=True)
        after_started = copy.deepcopy(state)
        after_started["pending_intent"].update(status="started", started_at=iso_time(utc_now()))
        state = write_ahead_transition(ctx, state, after_started, "mutation_started", {
            "task_id": pending["task_id"], "action": pending["action"],
            "idempotency_key": pending["idempotency_key"], "target_digest": pending["target_digest"],
        })
        current = state["pending_intent"]
        request = {
            "schema_version": 1, "contract": ADAPTER_REQUEST_CONTRACT,
            "request_id": "mutation_" + secrets.token_hex(16), "repo_identity": ctx.repo_identity,
            "project_id": project_id, "policy_commit": policy_commit, "wave_id": state["wave_id"],
            "fencing_token": token,
            "intent": {key: current[key] for key in ("idempotency_key", "target_digest", "target", "task_id", "action")},
        }
        encoded_request = canonical_json(request)

        def limit_adapter_output() -> None:
            resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_JSON_BYTES, MAX_JSON_BYTES))

        try:
            with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
                process = subprocess.Popen(
                    [str(adapter)], stdin=subprocess.PIPE, stdout=stdout_file, stderr=stderr_file,
                    start_new_session=True, preexec_fn=limit_adapter_output,
                )
                try:
                    process.communicate(input=encoded_request, timeout=timeout_seconds)
                except subprocess.TimeoutExpired as exc:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    raise ControllerError(EXIT_CONFLICT, "mutation adapter timed out; outcome unknown") from exc
                finally:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
                stdout_size = os.fstat(stdout_file.fileno()).st_size
                stderr_size = os.fstat(stderr_file.fileno()).st_size
                if stdout_size >= MAX_JSON_BYTES or stderr_size >= MAX_JSON_BYTES:
                    raise ControllerError(EXIT_DATA, "mutation adapter output exceeded 1 MiB")
                stdout_file.seek(0)
                adapter_stdout = stdout_file.read(MAX_JSON_BYTES)
                adapter_returncode = int(process.returncode)
        except ControllerError:
            raise
        except OSError as exc:
            raise ControllerError(EXIT_IO, f"mutation adapter failed: {exc}") from exc
        if after_adapter_hook:
            after_adapter_hook()
        if adapter_returncode != 0:
            raise ControllerError(EXIT_CONFLICT, f"mutation adapter returned {adapter_returncode}; outcome unknown")
        receipt = strict_json_loads(adapter_stdout, "mutation receipt")
        if not isinstance(receipt, dict):
            raise ControllerError(EXIT_DATA, "mutation receipt must be object")
        _validate_schema(receipt, ADAPTER_RECEIPT_CONTRACT, "mutation receipt")
        if any((
            receipt.get("request_id") != request["request_id"],
            receipt.get("idempotency_key") != current["idempotency_key"],
            receipt.get("target_digest") != current["target_digest"],
            receipt.get("fencing_token") != token,
        )):
            raise ControllerError(EXIT_DATA, "mutation receipt request/target/token mismatch")
        if receipt.get("accepted") is not True or not _nonempty(receipt.get("receipt_id")):
            raise ControllerError(EXIT_DATA, "mutation receipt lacks accepted/receipt_id")
        latest, _ = load_state_snapshot(ctx, project_id, policy_commit, recover=True)
        require_lease(latest, load_lease(ctx, project_id, policy_commit), owner, token)
        latest_pending = latest.get("pending_intent")
        if not isinstance(latest_pending, dict) or latest_pending.get("status") != "started" or latest_pending.get("target_digest") != receipt["target_digest"]:
            raise ControllerError(EXIT_CONFLICT, "pending exact target changed during adapter")
        after = copy.deepcopy(latest)
        after["pending_intent"].update(status="receipt_recorded", receipt_id=receipt["receipt_id"], receipt_recorded_at=iso_time(utc_now()))
        after["last_tick_at"] = iso_time(utc_now())
        write_ahead_transition(ctx, latest, after, "adapter_receipt_recorded", {
            "task_id": latest_pending["task_id"], "action": latest_pending["action"],
            "idempotency_key": latest_pending["idempotency_key"], "target_digest": latest_pending["target_digest"],
            "receipt_id": receipt["receipt_id"], "external_fact_converged": False,
        })
        return {"disposition": "receipt_recorded_await_external_fact", "mutation_count": 1, "receipt_id": receipt["receipt_id"], "recovered": recovered}


def status(ctx: RuntimeContext, project_id: str, policy_commit: str) -> dict[str, Any]:
    ctx.validate_policy_commit(policy_commit)
    with runtime_read_lock(ctx):
        state, recovery_needed = load_state_snapshot(ctx, project_id, policy_commit, recover=False)
        lease = load_lease(ctx, project_id, policy_commit, required=False)
        state, lease_recovery_needed = recover_lease_state_gap(ctx, state, lease, recover=False)
        recovery_needed = recovery_needed or lease_recovery_needed
        return {
            "state": state, "lease": lease, "runtime_root": str(ctx.root),
            "read_only": True, "recovery_needed": recovery_needed,
        }
