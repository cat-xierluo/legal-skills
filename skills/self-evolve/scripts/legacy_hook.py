#!/usr/bin/env python3
"""Inspect or remove obsolete Self Evolve SessionEnd hooks.

This migration helper deliberately has no install operation. ``remove`` is a
dry-run unless ``--apply`` is supplied, and it preserves every unrelated hook
and setting.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def default_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def load_settings_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    """Parse settings and derive the CAS digest from the exact same bytes."""
    if not path.exists():
        return {}, "missing"
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"settings.json 不是有效 JSON: {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"settings.json 不是有效 UTF-8: {path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"无法读取 settings.json: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"settings.json 根节点必须是对象: {path}")
    return payload, hashlib.sha256(raw).hexdigest()


def load_settings(path: Path) -> dict[str, Any]:
    return load_settings_snapshot(path)[0]


def settings_digest(path: Path) -> str:
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        return "missing"
    except OSError as exc:
        raise ValueError(f"无法读取 settings.json: {path}: {exc}") from exc
    return hashlib.sha256(payload).hexdigest()


def is_legacy_self_evolve_hook(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    command = value.get("command")
    if not isinstance(command, str):
        return False
    normalized = command.replace("\\", "/").casefold()
    return "sediment_guard.py" in normalized and (
        "/self-evolve/" in normalized
        or "/skill-evolve/" in normalized
        or "self-evolve/scripts/" in normalized
        or "skill-evolve/scripts/" in normalized
    )


def command_fingerprint(hook: dict[str, Any]) -> str:
    command = str(hook.get("command", ""))
    return hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]


def inspect_session_end(settings: dict[str, Any]) -> list[dict[str, Any]]:
    hooks_root = settings.get("hooks")
    if not isinstance(hooks_root, dict):
        return []
    session_end = hooks_root.get("SessionEnd")
    if not isinstance(session_end, list):
        return []
    matches: list[dict[str, Any]] = []
    for group_index, group in enumerate(session_end):
        if is_legacy_self_evolve_hook(group):
            matches.append(
                {
                    "group_index": group_index,
                    "hook_index": None,
                    "command_sha256": command_fingerprint(group),
                }
            )
            continue
        if not isinstance(group, dict):
            continue
        nested = group.get("hooks")
        if not isinstance(nested, list):
            continue
        for hook_index, hook in enumerate(nested):
            if is_legacy_self_evolve_hook(hook):
                matches.append(
                    {
                        "group_index": group_index,
                        "hook_index": hook_index,
                        "command_sha256": command_fingerprint(hook),
                    }
                )
    return matches


def remove_session_end_hooks(settings: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return a copied settings tree with only matching legacy hooks removed."""
    copied = json.loads(json.dumps(settings, ensure_ascii=False))
    hooks_root = copied.get("hooks")
    if not isinstance(hooks_root, dict):
        return copied, 0
    session_end = hooks_root.get("SessionEnd")
    if not isinstance(session_end, list):
        return copied, 0

    removed = 0
    retained_groups: list[Any] = []
    for group in session_end:
        if is_legacy_self_evolve_hook(group):
            removed += 1
            continue
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            retained_groups.append(group)
            continue
        nested = group["hooks"]
        retained_hooks = [hook for hook in nested if not is_legacy_self_evolve_hook(hook)]
        removed += len(nested) - len(retained_hooks)
        if retained_hooks:
            group["hooks"] = retained_hooks
            retained_groups.append(group)

    if retained_groups:
        hooks_root["SessionEnd"] = retained_groups
    else:
        hooks_root.pop("SessionEnd", None)
    if not hooks_root:
        copied.pop("hooks", None)
    return copied, removed


def atomic_write_with_backup(
    path: Path,
    settings: dict[str, Any],
    *,
    expected_sha256: str,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.self-evolve.lock")
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            current_bytes = path.read_bytes()
            current_sha256 = hashlib.sha256(current_bytes).hexdigest()
        except FileNotFoundError:
            current_bytes = b"{}\n"
            current_sha256 = "missing"
        except OSError as exc:
            raise ValueError(f"无法读取 settings.json: {path}: {exc}") from exc
        if current_sha256 != expected_sha256:
            raise ValueError(
                "settings.json 在读取后已被其他进程修改；未创建备份，也未覆盖文件"
            )

        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.name}.bak-self-evolve-{stamp}")
        suffix = 1
        while backup.exists():
            backup = path.with_name(f"{path.name}.bak-self-evolve-{stamp}-{suffix}")
            suffix += 1
        if path.exists():
            mode = path.stat().st_mode & 0o777
        else:
            mode = 0o600
        backup_fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
        try:
            with os.fdopen(backup_fd, "wb") as backup_handle:
                backup_handle.write(current_bytes)
                backup_handle.flush()
                os.fsync(backup_handle.fileno())
        except BaseException:
            backup.unlink(missing_ok=True)
            raise
        os.chmod(backup, mode)

        rendered = json.dumps(settings, ensure_ascii=False, indent=2) + "\n"
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_path, mode)
            # Detect an uncooperative writer that ignored the advisory lock.
            if settings_digest(path) != expected_sha256:
                backup.unlink(missing_ok=True)
                raise ValueError(
                    "settings.json 在写入前已被其他进程修改；未保留备份，也未覆盖文件"
                )
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)
        return backup
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect/remove obsolete Self Evolve SessionEnd hooks.")
    parser.add_argument("action", nargs="?", choices=("status", "remove"), default="status")
    parser.add_argument("--settings", type=Path, default=default_settings_path())
    parser.add_argument("--apply", action="store_true", help="Apply removal; remove is otherwise a dry-run")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.action == "status" and args.apply:
        parser.error("status 不接受 --apply")
    settings_path = args.settings.expanduser()
    try:
        settings, initial_sha256 = load_settings_snapshot(settings_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    matches = inspect_session_end(settings)
    result: dict[str, Any] = {
        "action": args.action,
        "settings_exists": settings_path.exists(),
        "legacy_hook_count": len(matches),
        "matches": matches,
        "applied": False,
    }
    if args.action == "remove":
        updated, removed = remove_session_end_hooks(settings)
        result["would_remove"] = removed
        if args.apply and removed:
            try:
                backup = atomic_write_with_backup(
                    settings_path,
                    updated,
                    expected_sha256=initial_sha256,
                )
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 3
            result["applied"] = True
            result["removed"] = removed
            result["backup"] = str(backup)
        elif args.apply:
            result["removed"] = 0

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "status":
        print(f"遗留 Self Evolve SessionEnd hook: {len(matches)}")
    elif result["applied"]:
        print(f"已移除 {result['removed']} 个遗留 hook；备份: {result['backup']}")
    else:
        print(f"dry-run: 将移除 {result['would_remove']} 个遗留 hook；使用 --apply 才会写入")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
