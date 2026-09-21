"""Validate a PM-bound completion receipt; Orca remains the mutation authority.

The caller must supply the authority path/hash from the worker launch snapshot,
never from Session Context. This is a hook boundary, not an OS-user sandbox.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess


def receipt_bytes(path_text: str) -> bytes:
    path = Path(path_text)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("receipt path must be absolute without traversal")
    # Canonicalize only the system prefix; all authority-directory components
    # below it must be real directories/files. /tmp -> /private/tmp is benign.
    if path.parent.name != "agent-authority":
        raise ValueError("receipt must live in the PM agent-authority directory")
    anchor = path.parent.parent.resolve(strict=True)
    checked = anchor
    for part in path.parts[-2:]:
        checked = checked / part
        mode = checked.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError("symlinked receipt path")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(checked, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise ValueError("receipt must be an owner-controlled regular file")
        if info.st_size > 1024 * 1024:
            raise ValueError("receipt is unexpectedly large")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            return stream.read(1024 * 1024 + 1)
    finally:
        os.close(fd)


def completion_path(authority_path: str) -> str:
    path = Path(authority_path)
    return str(path.with_suffix(".completion.json")) if path.suffix == ".json" else str(path) + ".completion.json"


def load_authority(authority_path: str, expected_sha: str = "") -> tuple[dict, str]:
    raw = receipt_bytes(authority_path)
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha and digest != expected_sha:
        raise ValueError("PM authority receipt changed after worker launch")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("schema") != "multi-agent-orchestration.authority-receipt.v1":
        raise ValueError("invalid PM authority receipt")
    return value, digest


def load_completion(path_text: str, authority_path: str, authority_sha: str) -> dict:
    if not authority_path or not authority_sha or path_text != completion_path(authority_path):
        raise ValueError("completion receipt is not bound to the launch snapshot")
    load_authority(authority_path, authority_sha)
    value = json.loads(receipt_bytes(path_text))
    if not isinstance(value, dict) or value.get("schema") != "multi-agent-orchestration.completion-authority.v1":
        raise ValueError("invalid completion receipt")
    if value.get("authority_receipt_file") != authority_path or value.get("authority_receipt_sha256") != authority_sha:
        raise ValueError("completion receipt has a different PM authority")
    return value


def live_dispatch_matches(receipt: dict, cli_path: str) -> bool:
    if not cli_path or not os.path.isabs(cli_path):
        return False
    try:
        result = subprocess.run(
            [cli_path, "orchestration", "dispatch-show", "--task", receipt["task_id"], "--json"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        payload = json.loads(result.stdout)
        if result.returncode or not isinstance(payload, dict) or payload.get("ok") is not True:
            return False
        if payload.get("_meta", {}).get("runtimeId") != receipt.get("runtime_id"):
            return False
        dispatch = payload["result"]["dispatch"]
        mapping = {"id": "dispatch_id", "task_id": "task_id", "assignee_handle": "terminal_handle",
                   "run_id": "run_id", "process_incarnation": "process_incarnation", "capability_hash": "capability_hash"}
        return isinstance(dispatch, dict) and all(dispatch.get(key) == receipt.get(field) for key, field in mapping.items())
    except (AttributeError, KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError):
        return False
