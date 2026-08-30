#!/usr/bin/env python3
"""Collect bounded, read-only external facts for the L2 Autopilot controller.

The controller pins this file and the bindings manifest by canonical path and
SHA-256.  This process accepts one versioned request on stdin and emits one
versioned, evidence-only response on stdout.  It never prints child stdout,
stderr, environment variables, credentials, or transcripts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import sys
import tempfile
from typing import Any


SCHEMA_VERSION = 1
REQUEST_CONTRACT = "multi-agent-orchestration.autopilot-facts-request.v1"
MANIFEST_CONTRACT = "multi-agent-orchestration.autopilot-facts-bindings.v1"
RESPONSE_CONTRACT = "multi-agent-orchestration.autopilot-facts.v1"
PROJECT_PROBE_CONTRACT = "multi-agent-orchestration.autopilot-project-probe.v1"
PROVIDER_PROBE_CONTRACT = "multi-agent-orchestration.autopilot-provider-probe.v1"

EXIT_USAGE = 64
EXIT_DATA = 65
EXIT_IDENTITY = 66
EXIT_UNAVAILABLE = 69
EXIT_SOFTWARE = 70
EXIT_IO = 74

MAX_INPUT_BYTES = 1024 * 1024
DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024
MAX_ALLOWED_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_REQUEST_WINDOW_SECONDS = 300

OID_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
SAFE_REMOTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SAFE_BRANCH_RE = re.compile(r"^(?!-)(?!.*(?:\.\.|@\{|\\|[\x00-\x20\x7f]))[A-Za-z0-9._/-]+$")
FORBIDDEN_ARG_TOKENS = {
    "add", "ack", "checkout", "clean", "commit", "create", "delete", "destroy",
    "merge", "mutate", "push", "release", "remove", "reset", "send", "settle",
    "stop", "update", "write",
}
COMMON_ENV = ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "XDG_CONFIG_HOME", "SSH_AUTH_SOCK")
SOURCE_ENV = {
    "github": ("GH_HOST", "GH_TOKEN", "GITHUB_TOKEN"),
    "orca": ("ORCA_ENDPOINT", "ORCA_RUNTIME_ID"),
}


class FactsError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        raise FactsError(EXIT_USAGE, message)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or len(value) != 20:
        raise FactsError(EXIT_DATA, f"{label} must be YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise FactsError(EXIT_DATA, f"{label} must be valid RFC3339 UTC") from exc
    return parsed.replace(tzinfo=dt.timezone.utc)


def _oid(value: Any, label: str) -> str:
    if not isinstance(value, str) or OID_RE.fullmatch(value) is None:
        raise FactsError(EXIT_DATA, f"{label} must be a full lowercase Git OID")
    return value


def _digest_literal(value: Any, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise FactsError(EXIT_DATA, f"{label} must be a lowercase SHA-256")
    return value


def _sha256(path: Path) -> str:
    try:
        before = path.lstat()
    except OSError as exc:
        raise FactsError(EXIT_IO, "cannot inspect file for hashing") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise FactsError(EXIT_DATA, "only a regular non-symlink file may be hashed")
    digest = hashlib.sha256()
    flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            after = os.fstat(stream.fileno())
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise FactsError(EXIT_DATA, "file changed while hashing")
            for block in iter(lambda: stream.read(128 * 1024), b""):
                digest.update(block)
    except FactsError:
        raise
    except OSError as exc:
        raise FactsError(EXIT_IO, "cannot hash regular file") from exc
    return digest.hexdigest()


def _read_regular(path: Path, label: str, limit: int = MAX_INPUT_BYTES) -> bytes:
    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise FactsError(EXIT_DATA, f"{label} is missing") from exc
    except OSError as exc:
        raise FactsError(EXIT_IO, f"cannot inspect {label}") from exc
    if stat.S_ISLNK(before.st_mode):
        raise FactsError(EXIT_DATA, f"{label} may not be a symlink")
    if not stat.S_ISREG(before.st_mode):
        raise FactsError(EXIT_DATA, f"{label} must be a regular file")
    flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            after = os.fstat(stream.fileno())
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise FactsError(EXIT_DATA, f"{label} changed while opening")
            raw = stream.read(limit + 1)
    except FactsError:
        raise
    except OSError as exc:
        raise FactsError(EXIT_IO, f"cannot read {label}") from exc
    if len(raw) > limit:
        raise FactsError(EXIT_DATA, f"{label} exceeds {limit} bytes")
    return raw


def _parse_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FactsError(EXIT_DATA, f"invalid {label} JSON") from exc
    if not isinstance(value, dict):
        raise FactsError(EXIT_DATA, f"{label} JSON root must be an object")
    return value


def _read_stdin() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise FactsError(EXIT_DATA, "request exceeds 1 MiB")
    return _parse_object(raw, "request")


def _require_contract(value: dict[str, Any], contract: str, label: str) -> None:
    if value.get("schema_version") != SCHEMA_VERSION or value.get("contract") != contract:
        raise FactsError(EXIT_DATA, f"unsupported {label} contract")


def _string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise FactsError(EXIT_DATA, f"{label} must be a non-empty string")
    if "\x00" in value:
        raise FactsError(EXIT_DATA, f"{label} contains NUL")
    return value


def _absolute_path(value: Any, label: str, *, kind: str) -> Path:
    raw = _string(value, label)
    path = Path(raw)
    if not path.is_absolute():
        raise FactsError(EXIT_DATA, f"{label} must be absolute")
    try:
        entry = path.lstat()
    except FileNotFoundError as exc:
        raise FactsError(EXIT_DATA, f"{label} is missing") from exc
    except OSError as exc:
        raise FactsError(EXIT_IO, f"cannot inspect {label}") from exc
    if stat.S_ISLNK(entry.st_mode):
        raise FactsError(EXIT_DATA, f"{label} may not be a symlink")
    if kind == "directory" and not stat.S_ISDIR(entry.st_mode):
        raise FactsError(EXIT_DATA, f"{label} must be a directory")
    if kind == "file" and not stat.S_ISREG(entry.st_mode):
        raise FactsError(EXIT_DATA, f"{label} must be a regular file")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise FactsError(EXIT_IO, f"cannot resolve {label}") from exc
    if resolved != path:
        raise FactsError(EXIT_DATA, f"{label} must be a canonical path without symlink components")
    return resolved


def _expected_directory(value: Any, label: str) -> tuple[Path, bool]:
    raw = _string(value, label)
    path = Path(raw)
    if not path.is_absolute():
        raise FactsError(EXIT_DATA, f"{label} must be absolute")
    try:
        exists = path.exists()
        if path.is_symlink():
            raise FactsError(EXIT_DATA, f"{label} may not be a symlink")
        resolved = path.resolve(strict=exists)
    except FactsError:
        raise
    except OSError as exc:
        raise FactsError(EXIT_IO, f"cannot resolve {label}") from exc
    if resolved != path:
        raise FactsError(EXIT_DATA, f"{label} must be canonical without symlink components")
    if exists and not path.is_dir():
        raise FactsError(EXIT_DATA, f"{label} must be a directory when present")
    return path, exists


def _safe_branch(value: Any, label: str) -> str:
    branch = _string(value, label)
    if SAFE_BRANCH_RE.fullmatch(branch) is None or branch.endswith(("/", ".")) or branch.startswith("refs/"):
        raise FactsError(EXIT_DATA, f"{label} is not a safe branch name")
    return branch


def _safe_remote(value: Any, label: str) -> str:
    remote = _string(value, label)
    if SAFE_REMOTE_RE.fullmatch(remote) is None or "::" in remote:
        raise FactsError(EXIT_DATA, f"{label} is not a safe Git remote name")
    return remote


def _command_spec(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("argv"), list):
        raise FactsError(EXIT_DATA, f"{label}.argv must be an array")
    if value.get("read_only") is not True:
        raise FactsError(EXIT_DATA, f"{label} must declare read_only=true")
    argv = value["argv"]
    if not argv or len(argv) > 32:
        raise FactsError(EXIT_DATA, f"{label}.argv must contain 1..32 elements")
    clean = [_string(part, f"{label}.argv[]", allow_empty=True) for part in argv]
    executable = Path(clean[0])
    if not executable.is_absolute():
        raise FactsError(EXIT_DATA, f"{label} executable must be absolute")
    try:
        entry = executable.lstat()
    except FileNotFoundError as exc:
        raise FactsError(EXIT_UNAVAILABLE, f"{label} executable is unavailable") from exc
    except OSError as exc:
        raise FactsError(EXIT_IO, f"cannot inspect {label} executable") from exc
    if stat.S_ISLNK(entry.st_mode):
        raise FactsError(EXIT_DATA, f"{label} executable may not be a symlink")
    if not stat.S_ISREG(entry.st_mode) or not os.access(executable, os.X_OK):
        raise FactsError(EXIT_UNAVAILABLE, f"{label} executable is not a regular executable")
    try:
        if executable.resolve(strict=True) != executable:
            raise FactsError(EXIT_DATA, f"{label} executable path must be canonical")
    except FactsError:
        raise
    except OSError as exc:
        raise FactsError(EXIT_IO, f"cannot resolve {label} executable") from exc
    expected = _digest_literal(value.get("sha256"), f"{label}.sha256")
    if _sha256(executable) != expected:
        raise FactsError(EXIT_IDENTITY, f"{label} executable digest mismatch")
    pinned_raw = value.get("pinned_files", [])
    if not isinstance(pinned_raw, list):
        raise FactsError(EXIT_DATA, f"{label}.pinned_files must be an array")
    pinned: dict[str, str] = {}
    for index, binding in enumerate(pinned_raw):
        if not isinstance(binding, dict):
            raise FactsError(EXIT_DATA, f"{label}.pinned_files[{index}] must be an object")
        bound_path = _absolute_path(binding.get("path"), f"{label}.pinned_files[{index}].path", kind="file")
        bound_digest = _digest_literal(binding.get("sha256"), f"{label}.pinned_files[{index}].sha256")
        if str(bound_path) in pinned or _sha256(bound_path) != bound_digest:
            raise FactsError(EXIT_IDENTITY, f"{label} pinned file is duplicate or changed")
        pinned[str(bound_path)] = bound_digest
    for token in clean[1:]:
        lowered = token.lower().lstrip("-").split("=", 1)[0]
        if lowered in FORBIDDEN_ARG_TOKENS or any(
            lowered.startswith(f"{word}-") or lowered.startswith(f"{word}_")
            for word in FORBIDDEN_ARG_TOKENS
        ):
            raise FactsError(EXIT_DATA, f"{label} contains a forbidden mutation argument")
        if token.startswith("/"):
            token_path = _absolute_path(token, f"{label} argv file", kind="file")
            if str(token_path) not in pinned:
                raise FactsError(EXIT_DATA, f"{label} argv file is not digest-pinned")
    return {"argv": clean, "executable": str(executable), "sha256": expected, "pinned_files": pinned}


def _run(
    spec: dict[str, Any], suffix: list[str], *, stdin_value: dict[str, Any] | None,
    cwd: Path, timeout: float, max_output: int, source: str, evidence: list[dict[str, Any]],
) -> tuple[int, bytes, str]:
    argv = list(spec["argv"]) + suffix
    encoded = None
    if stdin_value is not None:
        encoded = (json.dumps(stdin_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        if len(encoded) > MAX_INPUT_BYTES:
            raise FactsError(EXIT_DATA, f"{source} probe input exceeds 1 MiB")
    started = dt.datetime.now(dt.timezone.utc)
    status = "ok"
    returncode = 0
    stdout = b""
    source_class = source.split(":", 1)[0]
    env: dict[str, str] = {}
    for name in COMMON_ENV + SOURCE_ENV.get(source_class, ()):
        value = os.environ.get(name)
        if value is not None:
            env[name] = value
    env.update({
        "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0",
        "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1",
        "PAGER": "cat", "NO_COLOR": "1", "LC_ALL": "C",
    })

    def limit_child() -> None:
        resource.setrlimit(resource.RLIMIT_FSIZE, (max_output, max_output))

    try:
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            process = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=stdout_file, stderr=stderr_file,
                cwd=str(cwd), env=env, start_new_session=True, preexec_fn=limit_child,
            )
            try:
                process.communicate(input=encoded, timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                status = "timeout"
                returncode = 124
            else:
                returncode = int(process.returncode)
            stdout_size = os.fstat(stdout_file.fileno()).st_size
            stderr_size = os.fstat(stderr_file.fileno()).st_size
            if stdout_size >= max_output or stderr_size >= max_output:
                status = "output_limit"
                returncode = EXIT_DATA
            elif status != "timeout":
                stdout_file.seek(0)
                stdout = stdout_file.read(max_output)
                if returncode != 0:
                    status = "nonzero"
        if status == "output_limit":
            status = "output_limit"
            returncode = EXIT_DATA
    except (FileNotFoundError, PermissionError):
        status = "unavailable"
        returncode = EXIT_UNAVAILABLE
    except OSError:
        status = "io_error"
        returncode = EXIT_IO
    finished = dt.datetime.now(dt.timezone.utc)
    elapsed = int((finished - started).total_seconds() * 1000)
    evidence.append({
        "source": source,
        "tool_sha256": spec["sha256"],
        "operation": suffix[:4],
        "status": status,
        "exit_code": returncode,
        "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished_at": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "elapsed_ms": elapsed,
    })
    return returncode, stdout, status


def _json_output(raw: bytes) -> Any | None:
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _resolve_git_common(raw: str, cwd: Path) -> Path:
    candidate = Path(raw.strip())
    if not candidate.is_absolute():
        candidate = cwd / candidate
    return candidate.resolve(strict=True)


def _git_text(
    git_spec: dict[str, Any], repo: Path, args: list[str], *, timeout: float,
    max_output: int, evidence: list[dict[str, Any]], source: str = "git",
) -> tuple[int, str]:
    rc, raw, _ = _run(git_spec, ["-C", str(repo)] + args, stdin_value=None, cwd=repo,
                      timeout=timeout, max_output=max_output, source=source, evidence=evidence)
    if rc != 0:
        return rc, ""
    try:
        return 0, raw.decode("utf-8")
    except UnicodeDecodeError:
        return EXIT_DATA, ""


def _parse_worktrees(raw: str) -> list[dict[str, str]] | None:
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for token in raw.split("\0"):
        if not token:
            if current:
                entries.append(current)
                current = {}
            continue
        if " " in token:
            key, value = token.split(" ", 1)
        else:
            key, value = token, "true"
        if key in current:
            return None
        current[key] = value
    if current:
        entries.append(current)
    return entries


def _unknown_dispatch(dispatch_id: str | None) -> dict[str, Any]:
    return {"id": dispatch_id, "status": "unknown", "liveness": "unknown"}


def _collect_dispatch(
    item: dict[str, Any], orca: dict[str, Any], repo: Path, timeout: float,
    max_output: int, evidence: list[dict[str, Any]], ambiguity: list[str],
) -> dict[str, Any]:
    expected = item.get("dispatch_id")
    if expected is None:
        rc, raw, _ = _run(
            orca, ["orchestration", "dispatch-show", "--task", item["orca_task_id"], "--json"],
            stdin_value=None, cwd=repo, timeout=timeout, max_output=max_output,
            source=f"orca:{item['task_id']}", evidence=evidence,
        )
        if rc != 0:
            return _unknown_dispatch(None)
        payload = _json_output(raw)
        result = payload.get("result") if isinstance(payload, dict) and payload.get("ok") is True else None
        if not isinstance(result, dict):
            ambiguity.append(f"{item['task_id']}:dispatch_discovery_shape")
            return _unknown_dispatch(None)
        candidates: list[dict[str, Any]] = []
        discovered = result.get("dispatch")
        if isinstance(discovered, dict):
            candidates.append(discovered)
        elif discovered is not None:
            ambiguity.append(f"{item['task_id']}:dispatch_discovery_shape")
            return _unknown_dispatch(None)
        dispatches = result.get("dispatches")
        if isinstance(dispatches, list):
            if any(not isinstance(candidate, dict) for candidate in dispatches):
                ambiguity.append(f"{item['task_id']}:dispatch_discovery_shape")
                return _unknown_dispatch(None)
            candidates.extend(dispatches)
        elif dispatches is not None:
            ambiguity.append(f"{item['task_id']}:dispatch_discovery_shape")
            return _unknown_dispatch(None)
        if len(candidates) > 1:
            ambiguity.append(f"{item['task_id']}:dispatch_discovery_ambiguous")
            return _unknown_dispatch(None)
        for candidate in candidates:
            candidate_id = candidate.get("id") or candidate.get("dispatchId")
            if not isinstance(candidate_id, str) or not candidate_id:
                ambiguity.append(f"{item['task_id']}:dispatch_discovery_identity")
                return _unknown_dispatch(None)
            if (
                candidate.get("task_id", candidate.get("taskId")) != item["orca_task_id"]
                or candidate.get("run_id", candidate.get("runId")) != item["run_id"]
            ):
                ambiguity.append(f"{item['task_id']}:dispatch_discovery_identity")
                return _unknown_dispatch(None)
        if not candidates:
            return {"id": None, "status": "missing", "liveness": "unknown"}
        expected = candidates[0].get("id") or candidates[0].get("dispatchId")
    rc, raw, _ = _run(
        orca, ["orchestration", "worker-show", "--dispatch", expected, "--json"],
        stdin_value=None, cwd=repo, timeout=timeout, max_output=max_output,
        source=f"orca:{item['task_id']}", evidence=evidence,
    )
    if rc != 0:
        return _unknown_dispatch(expected)
    payload = _json_output(raw)
    if not isinstance(payload, dict):
        ambiguity.append(f"{item['task_id']}:orca_json")
        return _unknown_dispatch(expected)
    if payload.get("ok") is False:
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        code = error.get("code")
        if code in {"not_found", "dispatch_not_found"}:
            return {"id": expected, "status": "missing", "liveness": "unknown"}
        return _unknown_dispatch(expected)
    result = payload.get("result")
    if not isinstance(result, dict) or isinstance(result.get("workers"), list):
        ambiguity.append(f"{item['task_id']}:orca_shape")
        return _unknown_dispatch(expected)
    worker = result.get("worker")
    dispatch = result.get("dispatch")
    observation = result.get("observation")
    if not isinstance(worker, dict) or not isinstance(dispatch, dict) or not isinstance(observation, dict):
        ambiguity.append(f"{item['task_id']}:orca_echo_missing")
        return _unknown_dispatch(expected)
    worker_id = worker.get("dispatch_id") or worker.get("dispatchId")
    if (
        worker_id != expected or dispatch.get("id") != expected
        or dispatch.get("task_id") != item["orca_task_id"]
        or dispatch.get("run_id") != item["run_id"]
    ):
        ambiguity.append(f"{item['task_id']}:dispatch_identity")
        return _unknown_dispatch(expected)
    worker_state = str(worker.get("state", "")).lower()
    dispatch_state = str(dispatch.get("status", "")).lower()
    observation_state = str(observation.get("status", "")).lower()
    completed_dispatch = {"completed", "succeeded", "settled"}
    completed_worker = {"succeeded", "completed"}
    completed_observation = {"exited", "missing", "stopped", "settled"}
    failed_dispatch = {"failed", "abandoned", "cancelled", "canceled", "error"}
    failed_worker = {"failed", "stopped", "abandoned", "cancelled", "canceled", "error"}
    dead_observation = {"exited", "missing", "stopped"}
    active_dispatch = {"active", "dispatched", "pending", "running", "starting"}
    active_worker = {"active", "working", "running", "ready", "starting"}
    if dispatch_state in completed_dispatch and worker_state in completed_worker and observation_state in completed_observation:
        status_value, liveness = "completed", "settled"
    elif dispatch_state in failed_dispatch and worker_state in failed_worker and observation_state in dead_observation:
        status_value, liveness = "failed", "dead"
    elif dispatch_state in active_dispatch and worker_state in active_worker and observation_state == "active":
        status_value, liveness = "active", "active"
    else:
        ambiguity.append(f"{item['task_id']}:dispatch_state_contradiction")
        status_value, liveness = "unknown", "unknown"
    return {"id": expected, "status": status_value, "liveness": liveness}


def _unknown_git(worktree: str) -> dict[str, Any]:
    return {
        "worktree": worktree, "worktree_count": "unknown", "branch": "unknown",
        "branch_matches": "unknown", "dirty": "unknown", "local_oid": None,
        "remote_oid": None, "published": "unknown",
    }


def _collect_git(
    item: dict[str, Any], git_spec: dict[str, Any], repo: Path, common_dir: Path,
    timeout: float, max_output: int, evidence: list[dict[str, Any]], ambiguity: list[str],
) -> dict[str, Any]:
    expected_path = item["worktree"]
    expected_branch = item["branch"]
    result = _unknown_git(expected_path)
    result["remote"] = item["git_remote"]
    rc, raw = _git_text(git_spec, repo, ["worktree", "list", "--porcelain", "-z"],
                        timeout=timeout, max_output=max_output, evidence=evidence)
    if rc != 0:
        return result
    worktrees = _parse_worktrees(raw)
    if worktrees is None:
        ambiguity.append(f"{item['task_id']}:worktree_list")
        return result
    branch_ref = f"refs/heads/{expected_branch}"
    matching = [entry for entry in worktrees if entry.get("branch") == branch_ref]
    result["worktree_count"] = len(matching)
    exact_entries = []
    for entry in worktrees:
        try:
            if Path(entry.get("worktree", "")).resolve(strict=True) == Path(expected_path):
                exact_entries.append(entry)
        except OSError:
            continue
    if len(exact_entries) != 1:
        if len(exact_entries) > 1:
            ambiguity.append(f"{item['task_id']}:worktree_duplicate")
        elif not Path(expected_path).exists() and not matching:
            result.update({
                "worktree_count": 0, "branch": expected_branch, "branch_matches": True,
                "dirty": False, "local_oid": None, "remote_oid": None, "published": False,
            })
        elif matching:
            ambiguity.append(f"{item['task_id']}:worktree_binding")
        return result
    worktree = Path(expected_path)
    try:
        entry = worktree.lstat()
    except OSError:
        return result
    if stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode):
        ambiguity.append(f"{item['task_id']}:worktree_type")
        return result
    rc, top = _git_text(git_spec, worktree, ["rev-parse", "--show-toplevel"], timeout=timeout,
                        max_output=max_output, evidence=evidence, source=f"git:{item['task_id']}")
    rc2, common_raw = _git_text(git_spec, worktree, ["rev-parse", "--git-common-dir"], timeout=timeout,
                                max_output=max_output, evidence=evidence, source=f"git:{item['task_id']}")
    if rc != 0 or rc2 != 0:
        return result
    try:
        if Path(top.strip()).resolve(strict=True) != worktree or _resolve_git_common(common_raw, worktree) != common_dir:
            ambiguity.append(f"{item['task_id']}:worktree_identity")
            return result
    except OSError:
        return result
    rc, branch = _git_text(git_spec, worktree, ["symbolic-ref", "--quiet", "--short", "HEAD"],
                           timeout=timeout, max_output=max_output, evidence=evidence,
                           source=f"git:{item['task_id']}")
    if rc != 0:
        return result
    branch = branch.strip()
    result["branch"] = branch
    result["branch_matches"] = branch == expected_branch
    if branch != expected_branch:
        ambiguity.append(f"{item['task_id']}:branch_identity")
        return result
    rc, local_oid = _git_text(git_spec, worktree, ["rev-parse", "HEAD"], timeout=timeout,
                              max_output=max_output, evidence=evidence, source=f"git:{item['task_id']}")
    rc2, dirty = _git_text(git_spec, worktree, ["status", "--porcelain=v1", "-z"], timeout=timeout,
                           max_output=max_output, evidence=evidence, source=f"git:{item['task_id']}")
    if rc != 0 or rc2 != 0 or OID_RE.fullmatch(local_oid.strip()) is None:
        return result
    result["local_oid"] = local_oid.strip()
    result["dirty"] = bool(dirty)
    remote = item["git_remote"]
    rc, remote_urls = _git_text(
        git_spec, worktree, ["remote", "get-url", "--all", remote], timeout=timeout,
        max_output=max_output, evidence=evidence, source=f"git-remote:{item['task_id']}",
    )
    if rc != 0:
        return result
    urls = [line.strip() for line in remote_urls.splitlines() if line.strip()]
    safe_url = re.compile(r"^(?:https://|ssh://|git://|file://|git@[^:]+:|/)[^\x00-\x20]*$")
    if not urls or any("::" in url or safe_url.fullmatch(url) is None for url in urls):
        ambiguity.append(f"{item['task_id']}:unsafe_remote_url")
        return result
    rc, remote_text = _git_text(
        git_spec, worktree,
        ["ls-remote", "--exit-code", "--heads", "--upload-pack=git-upload-pack", remote,
         f"refs/heads/{expected_branch}"],
        timeout=timeout, max_output=max_output, evidence=evidence, source=f"git-remote:{item['task_id']}",
    )
    if rc == 2 and not remote_text:
        result["published"] = False
        return result
    if rc != 0:
        return result
    rows = [line.split() for line in remote_text.splitlines() if line.strip()]
    if len(rows) != 1 or len(rows[0]) != 2 or rows[0][1] != f"refs/heads/{expected_branch}" or OID_RE.fullmatch(rows[0][0]) is None:
        ambiguity.append(f"{item['task_id']}:remote_branch")
        return result
    result["remote_oid"] = rows[0][0]
    result["published"] = rows[0][0] == result["local_oid"]
    return result


def _unknown_pr(
    number: int | None, required_checks: list[str] | None = None, required_approvals: int = 0,
) -> dict[str, Any]:
    return {
        "number": number, "state": "unknown", "checks": "unknown", "mergeable": "unknown",
        "approvals": 0, "approvals_known": False,
        "head_oid": None, "head_branch": None, "base_branch": None,
        "merge_commit": None, "adopted": False,
        "required_checks": sorted(required_checks or []), "required_approvals": required_approvals,
    }


def _checks(entries: Any, required_contexts: list[str]) -> tuple[str, str | None]:
    if not isinstance(entries, list):
        return "unknown", "checks_shape"
    success = {"SUCCESS", "SKIPPED", "NEUTRAL"}
    failure = {"FAILURE", "ERROR", "CANCELLED", "CANCELED", "TIMED_OUT", "ACTION_REQUIRED"}
    pending = {"PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED", "WAITING", "REQUESTED"}
    by_context: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            return "unknown", "checks_shape"
        context = entry.get("name") or entry.get("context")
        raw = entry.get("conclusion") or entry.get("state") or entry.get("status")
        if not isinstance(context, str) or not context or not isinstance(raw, str):
            return "unknown", "checks_shape"
        if context in by_context:
            return "unknown", "checks_duplicate_context"
        by_context[context] = raw.upper()
    if any(context not in by_context for context in required_contexts):
        return "unknown", "required_check_missing"
    values = [by_context[context] for context in required_contexts]
    if not values:
        return "pass", None
    if any(value in failure for value in values):
        return "fail", None
    if any(value in pending for value in values):
        return "pending", None
    if all(value in success for value in values):
        return "pass", None
    return "unknown", "required_check_unknown"


def _approvals(reviews: Any, head_oid: str) -> tuple[int | str, str | None]:
    if not isinstance(reviews, list):
        return "unknown", "reviews_shape"
    latest: dict[str, tuple[dt.datetime, str]] = {}
    for review in reviews:
        if not isinstance(review, dict) or not isinstance(review.get("author"), dict):
            return "unknown", "reviews_shape"
        login = review["author"].get("login")
        state_value = review.get("state")
        submitted = review.get("submittedAt")
        commit_value = review.get("commit")
        commit_oid = review.get("commitOid")
        if commit_oid is None and isinstance(commit_value, dict):
            commit_oid = commit_value.get("oid")
        if not isinstance(login, str) or not login or not isinstance(state_value, str):
            return "unknown", "reviews_shape"
        if not isinstance(commit_oid, str) or OID_RE.fullmatch(commit_oid) is None or commit_oid != head_oid:
            return "unknown", "review_head_mismatch"
        try:
            submitted_at = _parse_time(submitted, "review.submittedAt")
        except FactsError:
            return "unknown", "reviews_timestamp"
        previous = latest.get(login)
        if previous is None or submitted_at > previous[0]:
            latest[login] = (submitted_at, state_value.upper())
        elif submitted_at == previous[0] and state_value.upper() != previous[1]:
            return "unknown", "reviews_ambiguous_latest"
    return sum(1 for _, state_value in latest.values() if state_value == "APPROVED"), None


def _collect_pr(
    item: dict[str, Any], gh: dict[str, Any], repo: Path, github_repo: str,
    expected_head_oid: str | None, timeout: float, max_output: int,
    evidence: list[dict[str, Any]], ambiguity: list[str],
) -> dict[str, Any]:
    number = item["pr_number"]
    unknown = lambda: _unknown_pr(number, item["required_checks"], item["required_approvals"])
    fields = "number,state,statusCheckRollup,mergeable,reviews,headRefOid,headRefName,baseRefName,mergeCommit"
    rc, raw, _ = _run(
        gh, ["pr", "list", "--repo", github_repo, "--head", item["branch"], "--state", "all",
             "--limit", "100", "--json", fields],
        stdin_value=None, cwd=repo, timeout=timeout, max_output=max_output,
        source=f"github:{item['task_id']}", evidence=evidence,
    )
    if rc != 0:
        return unknown()
    payload = _json_output(raw)
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        ambiguity.append(f"{item['task_id']}:github_json")
        return unknown()
    if len(payload) > 1:
        ambiguity.append(f"{item['task_id']}:pr_duplicate")
        return unknown()
    if not payload:
        if number is None:
            return {
                "number": None, "state": "none", "checks": "not_applicable", "mergeable": "not_applicable",
                "approvals": 0, "approvals_known": True,
                "head_oid": None, "head_branch": None, "base_branch": item["base_branch"],
                "merge_commit": None, "adopted": False,
                "required_checks": sorted(item["required_checks"]),
                "required_approvals": item["required_approvals"],
            }
        ambiguity.append(f"{item['task_id']}:pr_missing")
        return unknown()
    row = payload[0]
    observed_number = row.get("number")
    head = row.get("headRefName")
    base = row.get("baseRefName")
    head_oid = row.get("headRefOid")
    if (
        type(observed_number) is not int or observed_number < 1
        or (number is not None and observed_number != number)
        or head != item["branch"] or base != item["base_branch"]
        or not isinstance(head_oid, str) or OID_RE.fullmatch(head_oid) is None
        or expected_head_oid is None or head_oid != expected_head_oid
    ):
        ambiguity.append(f"{item['task_id']}:pr_identity")
        return unknown()
    state_raw = str(row.get("state", "")).upper()
    state_value = {"OPEN": "open", "MERGED": "merged"}.get(state_raw, "unknown")
    mergeable_raw = str(row.get("mergeable", "")).upper()
    mergeable: bool | str = {"MERGEABLE": True, "CONFLICTING": False, "UNKNOWN": "unknown"}.get(mergeable_raw, "unknown")
    approvals, review_error = _approvals(row.get("reviews"), head_oid)
    checks, checks_error = _checks(row.get("statusCheckRollup"), item["required_checks"])
    if checks_error:
        ambiguity.append(f"{item['task_id']}:{checks_error}")
    if review_error:
        ambiguity.append(f"{item['task_id']}:{review_error}")
    approvals_known = approvals != "unknown"
    if approvals == "unknown":
        checks = "unknown"
        approvals = 0
    elif approvals < item["required_approvals"] and checks == "pass":
        checks = "pending"
    merge_commit_value = row.get("mergeCommit")
    merge_commit = merge_commit_value.get("oid") if isinstance(merge_commit_value, dict) else None
    if merge_commit is not None and (not isinstance(merge_commit, str) or OID_RE.fullmatch(merge_commit) is None):
        merge_commit = None
    if state_value == "merged" and merge_commit is None:
        ambiguity.append(f"{item['task_id']}:merge_commit_missing")
        return unknown()
    return {
        "number": observed_number, "state": state_value,
        "checks": checks,
        "mergeable": mergeable, "approvals": approvals, "approvals_known": approvals_known,
        "head_oid": head_oid,
        "head_branch": head, "base_branch": base, "merge_commit": merge_commit,
        "adopted": number is None,
        "required_checks": sorted(item["required_checks"]),
        "required_approvals": item["required_approvals"],
    }


def _probe(
    spec: dict[str, Any], request: dict[str, Any], repo: Path, timeout: float,
    max_output: int, source: str, evidence: list[dict[str, Any]], contract: str,
) -> dict[str, Any] | None:
    rc, raw, _ = _run(spec, [], stdin_value=request, cwd=repo, timeout=timeout,
                      max_output=max_output, source=source, evidence=evidence)
    if rc != 0:
        return None
    payload = _json_output(raw)
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or payload.get("contract") != contract:
        return None
    return payload


def _collect_project(
    item: dict[str, Any], repo: Path, timeout: float, max_output: int,
    evidence: list[dict[str, Any]], ambiguity: list[str], request_id: str,
    local_oid: str | None, merge_commit: str | None, policy_commit: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    unknown_project = {
        "status": "unknown", "writeback_applied": "unknown",
        "writeback_target": None, "evidence_sha256": None,
    }
    unknown_verification = {
        "passed": "unknown", "evidence_sha256": None,
        "local_oid": None, "gate_contract_sha256": None,
    }
    evidence_path = Path(item["evidence_path"])
    raw = _read_regular(evidence_path, f"{item['task_id']} project evidence")
    evidence_digest = hashlib.sha256(raw).hexdigest()
    if evidence_digest != item["evidence_sha256"]:
        raise FactsError(EXIT_IDENTITY, f"{item['task_id']} project evidence digest mismatch")
    probe_request = {
        "schema_version": 1, "contract": PROJECT_PROBE_CONTRACT,
        "mode": "read_only", "request_id": request_id, "task_id": item["task_id"],
        "evidence_path": str(evidence_path), "evidence_sha256": evidence_digest,
        "local_oid": local_oid, "gate_contract_path": item["gate_contract_path"],
        "gate_contract_sha256": item["gate_contract_sha256"],
        "merge_commit": merge_commit, "policy_commit": policy_commit,
    }
    payload = _probe(item["project_probe"], probe_request, repo, timeout, max_output,
                     f"project:{item['task_id']}", evidence, PROJECT_PROBE_CONTRACT)
    if payload is None:
        return unknown_project, unknown_verification
    if payload.get("request_id") != request_id or payload.get("task_id") != item["task_id"] or payload.get("evidence_sha256") != evidence_digest:
        ambiguity.append(f"{item['task_id']}:project_identity")
        return unknown_project, unknown_verification
    status_value = payload.get("status")
    writeback = payload.get("writeback_applied")
    verification = payload.get("verification")
    passed = verification.get("passed") if isinstance(verification, dict) else None
    if status_value not in {"ready", "in_progress", "complete"} or type(writeback) is not bool or (type(passed) is not bool and passed != "unknown"):
        ambiguity.append(f"{item['task_id']}:project_shape")
        return unknown_project, unknown_verification
    verification_binding_valid = not (
        not isinstance(verification, dict) or local_oid is None
        or verification.get("local_oid") != local_oid
        or verification.get("gate_contract_sha256") != item["gate_contract_sha256"]
    )
    if not verification_binding_valid:
        ambiguity.append(f"{item['task_id']}:verification_stale")
        passed = "unknown"
    writeback_record = payload.get("writeback")
    writeback_target: dict[str, Any] | None = None
    if writeback is True:
        if (
            not isinstance(writeback_record, dict)
            or writeback_record.get("task_id") != item["task_id"]
            or writeback_record.get("merge_commit") != merge_commit
            or writeback_record.get("policy_commit") != policy_commit
            or merge_commit is None
        ):
            ambiguity.append(f"{item['task_id']}:writeback_stale")
            writeback = "unknown"
        else:
            writeback_target = {
                "task_id": item["task_id"], "merge_commit": merge_commit,
                "policy_commit": policy_commit, "evidence_sha256": evidence_digest,
            }
    return (
        {"status": status_value, "writeback_applied": writeback,
         "writeback_target": writeback_target, "evidence_sha256": evidence_digest},
        {
            "passed": passed, "evidence_sha256": evidence_digest,
            "local_oid": local_oid if verification_binding_valid else None,
            "gate_contract_sha256": (
                item["gate_contract_sha256"] if verification_binding_valid else None
            ),
        },
    )


def _collect_provider(
    item: dict[str, Any], repo: Path, timeout: float, max_output: int,
    evidence: list[dict[str, Any]], ambiguity: list[str], request_id: str,
) -> dict[str, Any]:
    spec = item.get("provider_probe")
    if spec is None:
        if item["provider"] == "not_applicable":
            return {"identity": "not_applicable", "status": "not_applicable", "retry_at": None}
        return {"identity": item["provider"], "status": "unknown", "retry_at": None}
    probe_request = {
        "schema_version": 1, "contract": PROVIDER_PROBE_CONTRACT,
        "mode": "read_only", "request_id": request_id, "task_id": item["task_id"],
        "provider": item["provider"],
    }
    payload = _probe(spec, probe_request, repo, timeout, max_output,
                     f"provider:{item['task_id']}", evidence, PROVIDER_PROBE_CONTRACT)
    if payload is None:
        return {"identity": item["provider"], "status": "unknown", "retry_at": None}
    if payload.get("request_id") != request_id or payload.get("task_id") != item["task_id"] or payload.get("provider") != item["provider"]:
        ambiguity.append(f"{item['task_id']}:provider_identity")
        return {"identity": item["provider"], "status": "unknown", "retry_at": None}
    status_value = payload.get("status")
    if status_value not in {"available", "waiting_reset", "not_applicable"}:
        ambiguity.append(f"{item['task_id']}:provider_shape")
        status_value = "unknown"
    retry_at = payload.get("retry_at")
    if status_value == "waiting_reset":
        try:
            _parse_time(retry_at, f"{item['task_id']} provider.retry_at")
        except FactsError:
            ambiguity.append(f"{item['task_id']}:provider_retry_at")
            return {"identity": item["provider"], "status": "unknown", "retry_at": None}
    elif retry_at is not None:
        ambiguity.append(f"{item['task_id']}:provider_retry_at_unexpected")
        return {"identity": item["provider"], "status": "unknown", "retry_at": None}
    return {"identity": item["provider"], "status": status_value, "retry_at": retry_at}


def _normalize_manifest(manifest: dict[str, Any], request: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _require_contract(manifest, MANIFEST_CONTRACT, "manifest")
    repo_request = request.get("repo")
    project_request = request.get("project")
    if not isinstance(repo_request, dict) or not isinstance(project_request, dict):
        raise FactsError(EXIT_DATA, "request repo/project identities are required")
    identity = {
        "repo_identity": _digest_literal(repo_request.get("identity"), "request.repo.identity"),
        "project_id": _string(project_request.get("project_id"), "request.project.project_id"),
        "policy_commit": _oid(project_request.get("policy_commit"), "request.project.policy_commit"),
        "run_id": _string(request.get("run_id"), "request.run_id"),
    }
    for key, expected in identity.items():
        if manifest.get(key) != expected:
            raise FactsError(EXIT_IDENTITY, f"manifest/request {key} mismatch")
    repo_block = manifest.get("repo")
    tools = manifest.get("tools")
    if not isinstance(repo_block, dict) or not isinstance(tools, dict):
        raise FactsError(EXIT_DATA, "manifest repo/tools blocks are required")
    repo = _absolute_path(repo_block.get("root"), "manifest.repo.root", kind="directory")
    common = _absolute_path(repo_block.get("common_dir"), "manifest.repo.common_dir", kind="directory")
    if str(repo) != repo_request.get("root") or str(common) != repo_request.get("common_dir"):
        raise FactsError(EXIT_IDENTITY, "manifest/request repository paths mismatch")
    github_repo = _string(repo_block.get("github_repo"), "manifest.repo.github_repo")
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", github_repo) is None:
        raise FactsError(EXIT_DATA, "manifest.repo.github_repo must be owner/name")
    git_remote = _safe_remote(repo_block.get("git_remote", "origin"), "manifest.repo.git_remote")
    normalized_tools = {
        name: _command_spec(tools.get(name), f"manifest.tools.{name}")
        for name in ("git", "orca", "gh")
    }
    raw_items = manifest.get("items")
    request_items = request.get("items")
    if not isinstance(raw_items, list) or not isinstance(request_items, list):
        raise FactsError(EXIT_DATA, "manifest/request items must be arrays")
    request_by_task: dict[str, dict[str, Any]] = {}
    for raw in request_items:
        if not isinstance(raw, dict):
            raise FactsError(EXIT_DATA, "request item must be an object")
        task_id = _string(raw.get("task_id"), "request.items[].task_id")
        if task_id in request_by_task:
            raise FactsError(EXIT_DATA, f"duplicate request task {task_id}")
        request_by_task[task_id] = raw
    normalized: list[dict[str, Any]] = []
    seen_dispatch: set[str] = set()
    seen_worktree: set[str] = set()
    seen_branch: set[str] = set()
    seen_pr: set[int] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise FactsError(EXIT_DATA, "manifest item must be an object")
        forbidden_dynamic = {"attempt", "dispatch_id", "pr_number", "pr_head_oid"}.intersection(raw)
        if forbidden_dynamic:
            raise FactsError(EXIT_DATA, "manifest item contains runtime-ledger dynamic fields")
        task_id = _string(raw.get("task_id"), "manifest.items[].task_id")
        request_item = request_by_task.pop(task_id, None)
        attempt = request_item.get("attempt") if request_item is not None else None
        if request_item is not None and (type(attempt) is not int or attempt < 1):
            raise FactsError(EXIT_DATA, f"task {task_id} request attempt must be positive")
        dispatch_id = request_item.get("dispatch_id") if request_item is not None else None
        orca_task_id = _string(raw.get("orca_task_id"), f"{task_id}.orca_task_id")
        if dispatch_id is not None:
            dispatch_id = _string(dispatch_id, f"{task_id}.dispatch_id")
            if dispatch_id in seen_dispatch:
                raise FactsError(EXIT_DATA, f"duplicate dispatch binding {dispatch_id}")
            seen_dispatch.add(dispatch_id)
        branch = _safe_branch(raw.get("branch"), f"{task_id}.branch")
        worktree, _ = _expected_directory(raw.get("worktree"), f"{task_id}.worktree")
        provider = _string(raw.get("provider"), f"{task_id}.provider")
        if branch in seen_branch or str(worktree) in seen_worktree:
            raise FactsError(EXIT_DATA, f"duplicate branch/worktree binding for {task_id}")
        seen_branch.add(branch)
        seen_worktree.add(str(worktree))
        pr_block = raw.get("pr")
        project_probe = raw.get("project_probe")
        if not isinstance(pr_block, dict) or not isinstance(project_probe, dict):
            raise FactsError(EXIT_DATA, f"task {task_id} pr/project_probe blocks are required")
        if any(key in pr_block for key in ("number", "head_oid", "pr_number", "pr_head_oid")):
            raise FactsError(EXIT_DATA, f"task {task_id} manifest PR block contains dynamic fields")
        pr_number = request_item.get("pr_number") if request_item is not None else None
        if pr_number is not None:
            if type(pr_number) is not int or pr_number < 1 or pr_number in seen_pr:
                raise FactsError(EXIT_DATA, f"invalid or duplicate PR binding for {task_id}")
            seen_pr.add(pr_number)
        bound_head_raw = request_item.get("pr_head_oid") if request_item is not None else None
        if bound_head_raw is None:
            bound_head_oid = None
        else:
            bound_head_oid = _oid(bound_head_raw, f"{task_id} request.pr_head_oid")
        if request_item is not None and pr_number is not None and bound_head_oid is None:
            raise FactsError(EXIT_DATA, f"{task_id} request pr_head_oid is required for a bound PR")
        required_checks = pr_block.get("required_checks")
        required_approvals = pr_block.get("required_approvals")
        if (
            not isinstance(required_checks, list) or len(required_checks) > 64
            or any(not isinstance(context, str) or not context or len(context) > 128 for context in required_checks)
            or len(set(required_checks)) != len(required_checks)
        ):
            raise FactsError(EXIT_DATA, f"{task_id}.pr.required_checks must be a unique bounded string array")
        if type(required_approvals) is not int or required_approvals < 0 or required_approvals > 20:
            raise FactsError(EXIT_DATA, f"{task_id}.pr.required_approvals must be 0..20")
        evidence_path = _absolute_path(project_probe.get("evidence_path"), f"{task_id}.evidence_path", kind="file")
        evidence_sha256 = _digest_literal(project_probe.get("evidence_sha256"), f"{task_id}.evidence_sha256")
        gate_contract_path = _absolute_path(
            project_probe.get("gate_contract_path"), f"{task_id}.gate_contract_path", kind="file",
        )
        gate_contract_sha256 = _digest_literal(project_probe.get("gate_contract_sha256"), f"{task_id}.gate_contract_sha256")
        if _sha256(evidence_path) != evidence_sha256:
            raise FactsError(EXIT_IDENTITY, f"{task_id} evidence digest mismatch")
        if _sha256(gate_contract_path) != gate_contract_sha256:
            raise FactsError(EXIT_IDENTITY, f"{task_id} gate contract digest mismatch")
        try:
            evidence_path.relative_to(repo)
            gate_contract_path.relative_to(repo)
        except ValueError as exc:
            raise FactsError(EXIT_IDENTITY, f"{task_id} project evidence escaped repository root") from exc
        normalized_item = {
            "task_id": task_id, "attempt": attempt, "dispatch_id": dispatch_id,
            "orca_task_id": orca_task_id, "run_id": identity["run_id"],
            "branch": branch, "worktree": str(worktree), "provider": provider,
            "pr_number": pr_number,
            "bound_head_oid": bound_head_oid,
            "base_branch": _safe_branch(pr_block.get("base_branch"), f"{task_id}.pr.base_branch"),
            "required_checks": required_checks, "required_approvals": required_approvals,
            "project_probe": _command_spec(project_probe, f"{task_id}.project_probe"),
            "evidence_path": str(evidence_path), "evidence_sha256": evidence_sha256,
            "gate_contract_path": str(gate_contract_path),
            "gate_contract_sha256": gate_contract_sha256, "git_remote": git_remote,
        }
        if raw.get("provider_probe") is not None:
            normalized_item["provider_probe"] = _command_spec(
                raw["provider_probe"], f"{task_id}.provider_probe",
            )
        if request_item is not None:
            for field, expected in {
                "branch": branch, "worktree": str(worktree),
                "orca_task_id": orca_task_id, "provider": provider,
            }.items():
                if request_item.get(field) != expected:
                    raise FactsError(EXIT_IDENTITY, f"task {task_id} {field} immutable binding mismatch")
            normalized.append(normalized_item)
    if request_by_task:
        raise FactsError(EXIT_IDENTITY, "request contains tasks absent from manifest")
    return {
        **identity, "repo": repo, "common_dir": common, "github_repo": github_repo,
        "tools": normalized_tools,
    }, normalized


def collect(
    request: dict[str, Any], manifest: dict[str, Any], manifest_digest: str,
    *, timeout: float, max_output: int,
) -> dict[str, Any]:
    started_at = dt.datetime.now(dt.timezone.utc)
    _require_contract(request, REQUEST_CONTRACT, "request")
    request_id = _string(request.get("request_id"), "request.request_id")
    expected_adapter_digest = _digest_literal(request.get("adapter_sha256"), "request.adapter_sha256")
    expected_manifest_digest = _digest_literal(request.get("manifest_sha256"), "request.manifest_sha256")
    if expected_manifest_digest != manifest_digest:
        raise FactsError(EXIT_IDENTITY, "facts bindings manifest digest mismatch")
    issued_at = _parse_time(request.get("issued_at"), "request.issued_at")
    deadline = _parse_time(request.get("deadline"), "request.deadline")
    if deadline <= issued_at or (deadline - issued_at).total_seconds() > MAX_REQUEST_WINDOW_SECONDS:
        raise FactsError(EXIT_DATA, "request freshness window is invalid or exceeds 300 seconds")
    if issued_at > started_at + dt.timedelta(seconds=5) or deadline < started_at:
        raise FactsError(EXIT_IDENTITY, "request is future-dated or expired")
    adapter_path = Path(__file__).resolve(strict=True)
    actual_adapter_digest = _sha256(adapter_path)
    if expected_adapter_digest != actual_adapter_digest:
        raise FactsError(EXIT_IDENTITY, "facts adapter digest mismatch")
    identity, items = _normalize_manifest(manifest, request)
    evidence: list[dict[str, Any]] = []
    ambiguity: list[str] = []
    git_spec = identity["tools"]["git"]
    repo = identity["repo"]
    common = identity["common_dir"]
    rc, top = _git_text(git_spec, repo, ["rev-parse", "--show-toplevel"], timeout=timeout,
                        max_output=max_output, evidence=evidence, source="git:repo")
    rc2, common_raw = _git_text(git_spec, repo, ["rev-parse", "--git-common-dir"], timeout=timeout,
                                max_output=max_output, evidence=evidence, source="git:repo")
    rc3, _ = _git_text(git_spec, repo, ["cat-file", "-e", f"{identity['policy_commit']}^{{commit}}"],
                       timeout=timeout, max_output=max_output, evidence=evidence, source="git:policy")
    try:
        actual_common = _resolve_git_common(common_raw, repo) if rc2 == 0 else None
        actual_top = Path(top.strip()).resolve(strict=True) if rc == 0 else None
    except OSError:
        actual_common = actual_top = None
    calculated_identity = hashlib.sha256(str(common).encode("utf-8")).hexdigest()
    if rc != 0 or rc2 != 0 or rc3 != 0 or actual_top != repo or actual_common != common or calculated_identity != identity["repo_identity"]:
        raise FactsError(EXIT_IDENTITY, "repository or policy identity drift")
    observed_items: list[dict[str, Any]] = []
    for item in items:
        rc_branch, _ = _git_text(
            git_spec, repo, ["check-ref-format", "--branch", item["branch"]], timeout=timeout,
            max_output=max_output, evidence=evidence, source=f"git-branch:{item['task_id']}",
        )
        rc_base, _ = _git_text(
            git_spec, repo, ["check-ref-format", "--branch", item["base_branch"]], timeout=timeout,
            max_output=max_output, evidence=evidence, source=f"git-branch:{item['task_id']}",
        )
        if rc_branch != 0 or rc_base != 0:
            raise FactsError(EXIT_DATA, f"{item['task_id']} branch binding is invalid")
        dispatch = _collect_dispatch(item, identity["tools"]["orca"], repo, timeout, max_output, evidence, ambiguity)
        git_facts = _collect_git(item, git_spec, repo, common, timeout, max_output, evidence, ambiguity)
        observed_head = git_facts.get("remote_oid") if git_facts.get("published") is True else git_facts.get("local_oid")
        if item["bound_head_oid"] is not None and observed_head is not None and observed_head != item["bound_head_oid"]:
            ambiguity.append(f"{item['task_id']}:bound_head_oid_mismatch")
            comparable = None
        else:
            comparable = observed_head or item["bound_head_oid"]
        pr = _collect_pr(
            item, identity["tools"]["gh"], repo, identity["github_repo"], comparable,
            timeout, max_output, evidence, ambiguity,
        )
        if pr.get("state") == "merged" and isinstance(pr.get("merge_commit"), str):
            merge_commit = pr["merge_commit"]
            base_ref = f"refs/remotes/{item['git_remote']}/{item['base_branch']}"
            rc_object, _ = _git_text(
                git_spec, repo, ["cat-file", "-e", f"{merge_commit}^{{commit}}"], timeout=timeout,
                max_output=max_output, evidence=evidence, source=f"git-merge:{item['task_id']}",
            )
            rc_base, base_oid = _git_text(
                git_spec, repo, ["rev-parse", "--verify", base_ref], timeout=timeout,
                max_output=max_output, evidence=evidence, source=f"git-merge:{item['task_id']}",
            )
            rc_ancestor, _ = _git_text(
                git_spec, repo, ["merge-base", "--is-ancestor", merge_commit, base_ref], timeout=timeout,
                max_output=max_output, evidence=evidence, source=f"git-merge:{item['task_id']}",
            )
            if rc_object != 0 or rc_base != 0 or OID_RE.fullmatch(base_oid.strip()) is None or rc_ancestor != 0:
                ambiguity.append(f"{item['task_id']}:merge_commit_git_mismatch")
                pr = _unknown_pr(item["pr_number"], item["required_checks"], item["required_approvals"])
        project, verification = _collect_project(
            item, repo, timeout, max_output, evidence, ambiguity, request_id,
            git_facts.get("local_oid"), pr.get("merge_commit"), identity["policy_commit"],
        )
        provider = _collect_provider(item, repo, timeout, max_output, evidence, ambiguity, request_id)
        observed_items.append({
            "task_id": item["task_id"], "attempt": item["attempt"],
            "dispatch": dispatch, "git": git_facts, "pr": pr,
            "project": project, "provider": provider, "verification": verification,
        })
    finished_at = dt.datetime.now(dt.timezone.utc)
    if finished_at > deadline:
        raise FactsError(EXIT_IDENTITY, "facts collection exceeded request deadline")
    return {
        "schema_version": SCHEMA_VERSION,
        "contract": RESPONSE_CONTRACT,
        "request_id": request_id,
        "adapter_sha256": actual_adapter_digest,
        "manifest_sha256": manifest_digest,
        "repo_identity": identity["repo_identity"],
        "project_id": identity["project_id"],
        "policy_commit": identity["policy_commit"],
        "run_id": identity["run_id"],
        "issued_at": issued_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "deadline": deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "started_at": started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished_at": finished_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "observed_at": finished_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ambiguous": bool(ambiguity),
        "ambiguity_codes": sorted(set(ambiguity)),
        "sources": evidence,
        "items": observed_items,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(description="Read-only facts collector for the L2 Autopilot controller")
    parser.add_argument("--manifest", required=True, help="pinned regular-file bindings manifest")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--max-output-bytes", type=int, default=DEFAULT_MAX_OUTPUT_BYTES)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        if args.timeout_seconds <= 0 or args.timeout_seconds > 60:
            raise FactsError(EXIT_USAGE, "timeout must be >0 and <=60 seconds")
        if args.max_output_bytes < 1024 or args.max_output_bytes > MAX_ALLOWED_OUTPUT_BYTES:
            raise FactsError(EXIT_USAGE, "max output must be between 1024 and 4 MiB")
        manifest_path = Path(args.manifest)
        if not manifest_path.is_absolute():
            raise FactsError(EXIT_DATA, "manifest path must be absolute")
        try:
            if manifest_path.resolve(strict=True) != manifest_path:
                raise FactsError(EXIT_DATA, "manifest path must be canonical without symlink components")
        except FactsError:
            raise
        except OSError as exc:
            raise FactsError(EXIT_DATA, "manifest path is unavailable") from exc
        manifest_raw = _read_regular(manifest_path, "bindings manifest")
        manifest_digest = hashlib.sha256(manifest_raw).hexdigest()
        manifest = _parse_object(manifest_raw, "bindings manifest")
        request = _read_stdin()
        response = collect(
            request, manifest, manifest_digest,
            timeout=args.timeout_seconds, max_output=args.max_output_bytes,
        )
        encoded = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > args.max_output_bytes:
            raise FactsError(EXIT_DATA, "facts response exceeds configured output limit")
        print(encoded)
        return 0
    except FactsError as exc:
        print(json.dumps({"error": exc.message, "exit_code": exc.code}, ensure_ascii=False), file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        print(json.dumps({"error": "interrupted", "exit_code": 75}), file=sys.stderr)
        return 75
    except Exception as exc:
        print(json.dumps({"error": f"internal facts collector error: {type(exc).__name__}", "exit_code": EXIT_SOFTWARE}), file=sys.stderr)
        return EXIT_SOFTWARE


if __name__ == "__main__":
    raise SystemExit(main())
