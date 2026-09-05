#!/usr/bin/env python3
"""Audit Orca-managed worker terminals and safely resume quota-stalled TUI turns."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any

from provider_error_classifier import classify_provider_error


CONTRACT = "multi-agent-orchestration.orca-rate-limit-recovery.v1"
MANIFEST_CONTRACT = "multi-agent-orchestration.orca-rate-limit-workers.v1"
STATE_CONTRACT = "multi-agent-orchestration.orca-rate-limit-state.v1"
EXIT_USAGE = 64
EXIT_DATA = 65
EXIT_RUNTIME = 70
EXIT_IO = 74
EXIT_CONFLICT = 75
MAX_JSON_BYTES = 4 * 1024 * 1024
HANDLE_RE = re.compile(r"[A-Za-z0-9._:-]+")
IDENTITY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}")
PROVIDER_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,31}")
ACTIONABLE_QUOTA_RE = re.compile(
    r"^(?:[^\w]{0,8})?(?:(?:api|provider|request|response)\s+)?"
    r"(?:error|failed|failure)\s*[:=#-]?\s*(?:http\s*)?429\b|"
    r"^\s*http\s+429\b|^\s*(?:status|code)\s*[:=]\s*429\b|"
    r"^\s*429\s*[:=-]?\s*(?:too many requests|rate[ _-]?limit|usage[ _-]?limit|quota|error)|"
    r"^\s*\{.*\"(?:code|status)\"\s*:\s*429\b|"
    r"\b(?:you(?:'ve| have)?\s+)?hit\s+(?:your\s+)?limit\b|"
    r"\b(?:rate[ _-]?limit|usage[ _-]?limit)\s+(?:reached|exceeded|exhausted|depleted)\b|"
    r"\bquota[\s_-]*(?:exceeded|exhausted|depleted)\b|\blimit\s+resets?\b",
    re.IGNORECASE,
)
DISCUSSION_RE = re.compile(
    r"\b(?:test|tests|testing|fixture|source|code|docs?|example|assert|grep|regex|mock)\b|"
    r"测试|夹具|源码|文档|示例|正则|断言",
    re.IGNORECASE,
)
NON_PROGRESS_AFTER_QUOTA_RE = re.compile(
    r"^(?:[\s>#$%❯›⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏.·…_-]*|"
    r"(?:retry|retrying|waiting|backing off)(?:\s|:|-|\d).*)$",
    re.IGNORECASE,
)


class RecoveryError(Exception):
    def __init__(self, code: int, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.receipt: dict[str, Any] | None = None


class RecoveryArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"error: {message}\n")


def strict_json(data: bytes, reason: str) -> Any:
    if len(data) > MAX_JSON_BYTES:
        raise RecoveryError(EXIT_DATA, f"{reason}_too_large")
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecoveryError(EXIT_DATA, f"{reason}_malformed") from exc
    return value


def read_json_file(path: Path, reason: str) -> Any:
    try:
        with path.open("rb") as stream:
            return strict_json(stream.read(MAX_JSON_BYTES + 1), reason)
    except OSError as exc:
        raise RecoveryError(EXIT_IO, f"{reason}_unreadable") from exc


def fingerprint(*parts: str, length: int = 16) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
    return digest[:length]


def require_string(value: Any, reason: str, pattern: re.Pattern[str] = IDENTITY_RE) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise RecoveryError(EXIT_DATA, reason)
    return value


def load_manifest(path: Path) -> list[dict[str, str]]:
    value = read_json_file(path, "manifest")
    if not isinstance(value, dict) or set(value) != {"contract", "workers"}:
        raise RecoveryError(EXIT_DATA, "manifest_contract_invalid")
    if value.get("contract") != MANIFEST_CONTRACT or not isinstance(value.get("workers"), list):
        raise RecoveryError(EXIT_DATA, "manifest_contract_invalid")
    workers: list[dict[str, str]] = []
    seen: set[str] = set()
    if not value["workers"] or len(value["workers"]) > 500:
        raise RecoveryError(EXIT_DATA, "manifest_worker_count_invalid")
    required = {"source", "terminal_handle", "incarnation_id", "provider", "account_group"}
    for item in value["workers"]:
        if not isinstance(item, dict) or set(item) != required:
            raise RecoveryError(EXIT_DATA, "manifest_worker_invalid")
        if item.get("source") != "orca":
            raise RecoveryError(EXIT_DATA, "non_orca_source_rejected")
        handle = require_string(item.get("terminal_handle"), "terminal_handle_invalid", HANDLE_RE)
        if handle in seen:
            raise RecoveryError(EXIT_DATA, "duplicate_terminal_handle")
        seen.add(handle)
        workers.append(
            {
                "terminal_handle": handle,
                "incarnation_id": require_string(item.get("incarnation_id"), "incarnation_id_invalid"),
                "provider": require_string(item.get("provider"), "provider_invalid", PROVIDER_RE),
                "account_group": require_string(item.get("account_group"), "account_group_invalid"),
            }
        )
    return workers


def resolve_orca() -> str:
    candidate = os.environ.get("ORCA_CLI_COMMAND", "orca")
    if os.path.isabs(candidate):
        if not os.path.isfile(candidate) or not os.access(candidate, os.X_OK):
            raise RecoveryError(EXIT_USAGE, "orca_cli_unavailable")
        return candidate
    if "/" in candidate:
        raise RecoveryError(EXIT_USAGE, "orca_cli_invalid")
    from shutil import which

    resolved = which(candidate)
    if resolved is None:
        raise RecoveryError(EXIT_USAGE, "orca_cli_unavailable")
    return resolved


def run_orca(orca: str, args: list[str], reason: str, *, allow_timeout: bool = False) -> tuple[str, dict[str, Any]]:
    try:
        result = subprocess.run(
            [orca, *args, "--json"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=15,
            check=False,
            env={"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecoveryError(EXIT_RUNTIME, f"{reason}_failed") from exc
    try:
        payload = strict_json(result.stdout, reason)
    except RecoveryError:
        raise RecoveryError(EXIT_RUNTIME, f"{reason}_malformed") from None
    if not isinstance(payload, dict):
        raise RecoveryError(EXIT_RUNTIME, f"{reason}_malformed")
    if allow_timeout and result.returncode != 0 and payload.get("ok") is False:
        error = payload.get("error")
        if isinstance(error, dict) and error.get("code") == "timeout":
            return "timeout", payload
    if result.returncode != 0 or payload.get("ok") is not True:
        raise RecoveryError(EXIT_RUNTIME, f"{reason}_failed")
    return "ok", payload


def parse_terminal_list(payload: dict[str, Any], expected: dict[str, dict[str, str]]) -> dict[str, dict[str, Any]]:
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("truncated") is not False:
        raise RecoveryError(EXIT_RUNTIME, "terminal_list_truncated_or_invalid")
    terminals = result.get("terminals")
    if not isinstance(terminals, list):
        raise RecoveryError(EXIT_RUNTIME, "terminal_list_malformed")
    found: dict[str, dict[str, Any]] = {}
    for item in terminals:
        if not isinstance(item, dict):
            raise RecoveryError(EXIT_RUNTIME, "terminal_list_malformed")
        handle = item.get("handle")
        if handle in expected:
            if handle in found:
                raise RecoveryError(EXIT_RUNTIME, "terminal_list_duplicate")
            found[handle] = item
    return found


def parse_show(payload: dict[str, Any], handle: str, incarnation: str) -> dict[str, Any]:
    result = payload.get("result")
    terminal = result.get("terminal") if isinstance(result, dict) else None
    if not isinstance(terminal, dict):
        raise RecoveryError(EXIT_RUNTIME, "terminal_show_malformed")
    if terminal.get("handle") != handle or terminal.get("incarnationId") != incarnation:
        raise RecoveryError(EXIT_CONFLICT, "terminal_identity_drift")
    if not isinstance(terminal.get("connected"), bool) or not isinstance(terminal.get("writable"), bool):
        raise RecoveryError(EXIT_RUNTIME, "terminal_show_malformed")
    timestamp = terminal.get("lastOutputAt")
    if timestamp is not None and (not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp < 0):
        raise RecoveryError(EXIT_RUNTIME, "terminal_show_malformed")
    return terminal


def parse_read(payload: dict[str, Any], handle: str) -> dict[str, Any]:
    result = payload.get("result")
    terminal = result.get("terminal") if isinstance(result, dict) else None
    if not isinstance(terminal, dict) or terminal.get("handle") != handle:
        raise RecoveryError(EXIT_RUNTIME, "terminal_read_malformed")
    tail = terminal.get("tail")
    latest = terminal.get("latestCursor")
    source = terminal.get("source")
    if not isinstance(tail, list) or any(not isinstance(line, str) for line in tail):
        raise RecoveryError(EXIT_RUNTIME, "terminal_read_malformed")
    if not isinstance(latest, (str, int)) or isinstance(latest, bool):
        raise RecoveryError(EXIT_RUNTIME, "terminal_read_malformed")
    if source not in (None, "stream"):
        raise RecoveryError(EXIT_RUNTIME, "terminal_read_source_invalid")
    return {"tail": tail, "latest_cursor": str(latest)}


def parse_idle_wait(status: str, payload: dict[str, Any], handle: str) -> bool:
    if status == "timeout":
        return False
    result = payload.get("result")
    wait = result.get("wait") if isinstance(result, dict) else None
    if not isinstance(wait, dict):
        raise RecoveryError(EXIT_RUNTIME, "terminal_wait_malformed")
    if (
        wait.get("handle") != handle
        or wait.get("condition") != "tui-idle"
        or wait.get("satisfied") is not True
        or "status" not in wait
        or wait.get("status") != "running"
        or "exitCode" not in wait
        or wait.get("exitCode") is not None
    ):
        raise RecoveryError(EXIT_RUNTIME, "terminal_wait_malformed")
    return True


def quota_tail(tail: list[str]) -> str:
    meaningful = [line for line in tail if line.strip()]
    return "\n".join(meaningful[-20:])


def actionable_quota_evidence(tail: list[str]) -> str:
    """Return a tail-anchored provider-error line, never a discussion of 429."""

    lines = [value.strip() for value in tail if value.strip()][-20:]
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index]
        if DISCUSSION_RE.search(line):
            continue
        if ACTIONABLE_QUOTA_RE.search(line) and classify_provider_error(line) == "quota":
            trailing = lines[index + 1 :]
            if all(
                (ACTIONABLE_QUOTA_RE.search(value) and classify_provider_error(value) == "quota")
                or NON_PROGRESS_AFTER_QUOTA_RE.fullmatch(value)
                for value in trailing
            ):
                return line
            return ""
    return ""


def audit_worker(
    orca: str,
    worker: dict[str, str],
    listed: dict[str, Any] | None,
    *,
    now_ms: int,
    idle_ms: int,
    max_age_ms: int,
    tail_lines: int,
) -> dict[str, Any]:
    handle = worker["terminal_handle"]
    provider = worker["provider"]
    group = worker["account_group"]
    base = {
        "terminal_handle": handle,
        "terminal_fingerprint": fingerprint(handle, worker["incarnation_id"]),
        "provider": provider,
        "group_fingerprint": fingerprint(provider, group),
        "state": "UNKNOWN",
        "reason": "terminal_not_listed",
        "action": "none",
        "evidence_fingerprint": None,
        "latest_cursor": None,
        "last_output_at": None,
        "eligible": False,
    }
    if listed is None:
        return base
    if listed.get("incarnationId") != worker["incarnation_id"]:
        base["reason"] = "manifest_identity_mismatch"
        return base

    _, show_payload = run_orca(orca, ["terminal", "show", "--terminal", handle], "terminal_show")
    terminal = parse_show(show_payload, handle, worker["incarnation_id"])
    if terminal["connected"] is not True or terminal["writable"] is not True:
        base["reason"] = "terminal_not_writable"
        return base
    timestamp = terminal.get("lastOutputAt")
    if timestamp is None:
        base["reason"] = "activity_timestamp_missing"
        return base

    _, read_payload = run_orca(
        orca, ["terminal", "read", "--terminal", handle, "--limit", str(tail_lines)], "terminal_read"
    )
    read = parse_read(read_payload, handle)
    wait_status, wait_payload = run_orca(
        orca,
        ["terminal", "wait", "--terminal", handle, "--for", "tui-idle", "--timeout-ms", "1"],
        "terminal_wait",
        allow_timeout=True,
    )
    idle = parse_idle_wait(wait_status, wait_payload, handle)
    age = now_ms - timestamp
    base["latest_cursor"] = read["latest_cursor"]
    base["last_output_at"] = timestamp
    if age < 0:
        base["reason"] = "activity_timestamp_in_future"
        return base

    tail_text = quota_tail(read["tail"])
    classification = classify_provider_error(tail_text)
    if classification in {"auth", "config", "network"}:
        base["reason"] = f"provider_{classification}_not_quota"
        return base
    evidence_line = actionable_quota_evidence(read["tail"])
    if classification != "quota" or not evidence_line:
        if not idle and age <= idle_ms:
            base.update(state="RUNNING", reason="recent_non_quota_activity")
        else:
            base["reason"] = "no_actionable_quota_evidence"
        return base
    if age > max_age_ms:
        base["reason"] = "quota_evidence_stale"
        return base

    evidence = fingerprint(handle, worker["incarnation_id"], read["latest_cursor"], str(timestamp), evidence_line, length=32)
    base["evidence_fingerprint"] = evidence
    if not idle or age < idle_ms:
        base.update(state="RATE_LIMIT_RETRYING", reason="quota_with_live_retry")
        return base
    base.update(
        state="RATE_LIMIT_IDLE",
        reason="quota_idle_high_confidence",
        action="resume_candidate",
        eligible=True,
    )
    return base


def inspect_path(path: Path, *, allow_missing: bool) -> os.stat_result | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if allow_missing:
            return None
        raise RecoveryError(EXIT_IO, "state_path_missing") from None
    except OSError as exc:
        raise RecoveryError(EXIT_IO, "state_path_uninspectable") from exc
    if stat.S_ISLNK(info.st_mode):
        raise RecoveryError(EXIT_IO, "state_symlink_rejected")
    return info


def ensure_private_state_dir(path: Path, *, create: bool) -> bool:
    path = Path(os.path.abspath(os.path.expanduser(str(path))))
    if inspect_path(path, allow_missing=True) is None and not create:
        return False
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor = cursor / part
        info = inspect_path(cursor, allow_missing=True)
        if info is None:
            if not create:
                return False
            try:
                cursor.mkdir(mode=0o700)
            except OSError as exc:
                raise RecoveryError(EXIT_IO, "state_directory_create_failed") from exc
            info = inspect_path(cursor, allow_missing=False)
        if info is None or not stat.S_ISDIR(info.st_mode):
            raise RecoveryError(EXIT_IO, "state_component_invalid")
    info = inspect_path(path, allow_missing=False)
    assert info is not None
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise RecoveryError(EXIT_IO, "state_directory_not_private")
    return True


def secure_open(path: Path, flags: int, mode: int) -> int:
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, mode)
    except OSError as exc:
        raise RecoveryError(EXIT_IO, "state_file_open_failed") from exc
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        os.close(fd)
        raise RecoveryError(EXIT_IO, "state_file_not_private")
    return fd


def load_state(path: Path) -> dict[str, Any]:
    if inspect_path(path, allow_missing=True) is None:
        return {"contract": STATE_CONTRACT, "actions": {}}
    fd = secure_open(path, os.O_RDONLY, 0o600)
    try:
        data = os.read(fd, MAX_JSON_BYTES + 1)
    finally:
        os.close(fd)
    value = strict_json(data, "state")
    if not isinstance(value, dict) or set(value) != {"contract", "actions"}:
        raise RecoveryError(EXIT_IO, "state_contract_invalid")
    if value["contract"] != STATE_CONTRACT or not isinstance(value["actions"], dict):
        raise RecoveryError(EXIT_IO, "state_contract_invalid")
    for key, action in value["actions"].items():
        if not isinstance(key, str) or not isinstance(action, dict) or action.get("status") not in {"intent", "sent"}:
            raise RecoveryError(EXIT_IO, "state_contract_invalid")
    return value


def write_state(path: Path, state: dict[str, Any]) -> None:
    encoded = (json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    fd = -1
    temp_path: Path | None = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=".state.", dir=path.parent)
        temp_path = Path(temp_name)
        os.fchmod(fd, 0o600)
        os.write(fd, encoded)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temp_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise RecoveryError(EXIT_IO, "state_write_failed") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def recheck_before_send(orca: str, item: dict[str, Any], worker: dict[str, str]) -> None:
    handle = worker["terminal_handle"]
    _, show_payload = run_orca(orca, ["terminal", "show", "--terminal", handle], "pre_send_show")
    terminal = parse_show(show_payload, handle, worker["incarnation_id"])
    if terminal.get("connected") is not True or terminal.get("writable") is not True:
        raise RecoveryError(EXIT_CONFLICT, "pre_send_terminal_not_writable")
    if terminal.get("lastOutputAt") != item["last_output_at"]:
        raise RecoveryError(EXIT_CONFLICT, "pre_send_activity_changed")
    _, read_payload = run_orca(
        orca,
        ["terminal", "read", "--terminal", handle, "--cursor", str(item["latest_cursor"]), "--limit", "20"],
        "pre_send_read",
    )
    read = parse_read(read_payload, handle)
    if read["latest_cursor"] != item["latest_cursor"] or any(line.strip() for line in read["tail"]):
        raise RecoveryError(EXIT_CONFLICT, "pre_send_cursor_advanced")
    wait_status, wait_payload = run_orca(
        orca,
        ["terminal", "wait", "--terminal", handle, "--for", "tui-idle", "--timeout-ms", "1"],
        "pre_send_wait",
        allow_timeout=True,
    )
    if not parse_idle_wait(wait_status, wait_payload, handle):
        raise RecoveryError(EXIT_CONFLICT, "pre_send_not_idle")


def send_resume(orca: str, handle: str) -> None:
    run_orca(orca, ["terminal", "send", "--terminal", handle, "--text", "继续", "--enter"], "terminal_send")


def recheck_after_send(orca: str, worker: dict[str, str]) -> None:
    handle = worker["terminal_handle"]
    _, show_payload = run_orca(orca, ["terminal", "show", "--terminal", handle], "post_send_show")
    terminal = parse_show(show_payload, handle, worker["incarnation_id"])
    if terminal.get("connected") is not True or terminal.get("writable") is not True:
        raise RecoveryError(EXIT_CONFLICT, "post_send_terminal_not_writable")


def default_state_dir() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "multi-agent-orchestration" / "orca-rate-limit-recovery"
    return Path.home() / ".local" / "state" / "multi-agent-orchestration" / "orca-rate-limit-recovery"


def render_human(receipt: dict[str, Any]) -> str:
    lines = [
        f"ORCA_RATE_LIMIT_RECOVERY mode={receipt['mode']} status={receipt['status']} "
        f"workers={len(receipt['workers'])} wake_accepted={receipt['summary']['wake_accepted']}"
    ]
    for item in receipt["workers"]:
        lines.append(
            f"{item['state']} terminal={item['terminal_handle']} group={item['group_fingerprint']} "
            f"action={item['action']} reason={item['reason']}"
        )
    return "\n".join(lines)


def execute(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    workers = load_manifest(Path(args.manifest))
    worker_by_handle = {item["terminal_handle"]: item for item in workers}
    orca = resolve_orca()
    _, list_payload = run_orca(
        orca, ["terminal", "list", "--limit", str(args.list_limit)], "terminal_list"
    )
    listed = parse_terminal_list(list_payload, worker_by_handle)
    now_ms = int(time.time() * 1000)
    audited: list[dict[str, Any]] = []
    for worker in workers:
        audited.append(
            audit_worker(
                orca,
                worker,
                listed.get(worker["terminal_handle"]),
                now_ms=now_ms,
                idle_ms=args.idle_seconds * 1000,
                max_age_ms=args.evidence_max_age_seconds * 1000,
                tail_lines=args.tail_lines,
            )
        )

    state_dir = Path(os.path.abspath(os.path.expanduser(args.state_dir)))
    state_path = state_dir / "state.json"
    state: dict[str, Any] = {"contract": STATE_CONTRACT, "actions": {}}
    state_available = ensure_private_state_dir(state_dir, create=False)
    if state_available:
        state = load_state(state_path)
    for item in audited:
        evidence = item.get("evidence_fingerprint")
        if evidence and evidence in state["actions"]:
            item.update(action="already_handled", eligible=False, reason="evidence_already_handled")

    receipt = {
        "contract": CONTRACT,
        "mode": "execute" if args.execute else "audit",
        "status": "AUDIT_COMPLETE",
        "summary": {
            "running": sum(item["state"] == "RUNNING" for item in audited),
            "rate_limit_retrying": sum(item["state"] == "RATE_LIMIT_RETRYING" for item in audited),
            "rate_limit_idle": sum(item["state"] == "RATE_LIMIT_IDLE" for item in audited),
            "unknown": sum(item["state"] == "UNKNOWN" for item in audited),
            "wake_accepted": 0,
        },
        "workers": audited,
    }
    if not args.execute:
        return 0, receipt

    ensure_private_state_dir(state_dir, create=True)
    lock_path = state_dir / "lock"
    lock_fd = secure_open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RecoveryError(EXIT_CONFLICT, "state_lock_busy") from exc
        state = load_state(state_path)
        candidates = [item for item in audited if item["eligible"]]
        candidates.sort(key=lambda item: (item["group_fingerprint"], item["terminal_handle"]))
        previous_group: str | None = None
        for item in candidates:
            evidence = item["evidence_fingerprint"]
            assert isinstance(evidence, str)
            if evidence in state["actions"]:
                item.update(action="already_handled", eligible=False, reason="evidence_already_handled")
                continue
            if previous_group is not None:
                delay_ms = (
                    args.terminal_delay_ms
                    if previous_group == item["group_fingerprint"]
                    else args.group_delay_ms
                )
                time.sleep(delay_ms / 1000)
            worker = worker_by_handle[item["terminal_handle"]]
            recheck_before_send(orca, item, worker)
            state["actions"][evidence] = {
                "status": "intent",
                "terminal_fingerprint": item["terminal_fingerprint"],
                "group_fingerprint": item["group_fingerprint"],
                "observed_at": item["last_output_at"],
            }
            write_state(state_path, state)
            try:
                send_resume(orca, item["terminal_handle"])
                recheck_after_send(orca, worker)
            except RecoveryError:
                item.update(action="outcome_unknown", eligible=False, reason="send_outcome_unknown")
                receipt["status"] = "SEND_OUTCOME_UNKNOWN"
                raise
            state["actions"][evidence]["status"] = "sent"
            state["actions"][evidence]["sent_at"] = int(time.time() * 1000)
            item.update(action="wake_accepted", eligible=False, reason="wake_accepted_not_recovery_proof")
            receipt["summary"]["wake_accepted"] += 1
            try:
                write_state(state_path, state)
            except RecoveryError:
                item.update(
                    action="wake_accepted_state_commit_failed",
                    reason="wake_accepted_but_state_commit_failed",
                )
                receipt["status"] = "WAKE_ACCEPTED_STATE_COMMIT_FAILED"
                raise
            previous_group = item["group_fingerprint"]
        receipt["status"] = "EXECUTION_COMPLETE"
        return 0, receipt
    except RecoveryError as exc:
        if receipt["status"] not in {"SEND_OUTCOME_UNKNOWN", "WAKE_ACCEPTED_STATE_COMMIT_FAILED"}:
            receipt["status"] = "FAILED_CLOSED"
        receipt["reason"] = exc.reason
        exc.receipt = receipt
        raise
    finally:
        os.close(lock_fd)


def build_parser() -> argparse.ArgumentParser:
    parser = RecoveryArgumentParser(
        description="Audit Orca worker terminals for quota stalls; --execute sends one guarded '继续'"
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--state-dir", default=str(default_state_dir()))
    parser.add_argument("--idle-seconds", type=int, default=300)
    parser.add_argument("--evidence-max-age-seconds", type=int, default=21600)
    parser.add_argument("--tail-lines", type=int, default=200)
    parser.add_argument("--terminal-delay-ms", type=int, default=8000)
    parser.add_argument("--group-delay-ms", type=int, default=15000)
    parser.add_argument("--list-limit", type=int, default=500)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 1 <= args.idle_seconds <= 86400:
        parser.error("--idle-seconds must be between 1 and 86400")
    if not args.idle_seconds <= args.evidence_max_age_seconds <= 604800:
        parser.error("--evidence-max-age-seconds must be >= idle-seconds and <= 604800")
    if not 20 <= args.tail_lines <= 5000:
        parser.error("--tail-lines must be between 20 and 5000")
    if not 100 <= args.terminal_delay_ms <= 300000:
        parser.error("--terminal-delay-ms must be between 100 and 300000")
    if not 100 <= args.group_delay_ms <= 300000:
        parser.error("--group-delay-ms must be between 100 and 300000")
    if not 1 <= args.list_limit <= 5000:
        parser.error("--list-limit must be between 1 and 5000")
    try:
        code, receipt = execute(args)
    except RecoveryError as exc:
        receipt = exc.receipt or {
            "contract": CONTRACT,
            "mode": "execute" if args.execute else "audit",
            "status": "FAILED_CLOSED",
            "reason": exc.reason,
        }
        if args.json:
            print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        else:
            print(f"ORCA_RATE_LIMIT_RECOVERY FAILED_CLOSED reason={exc.reason}")
        return exc.code
    if args.json:
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    else:
        print(render_human(receipt))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
