#!/usr/bin/env python3
"""Run one registered Self Evolve task from an external Cron trigger.

The YAML file is a registry and a kill-switch layer, not a system scheduler.
Only command types and arguments declared in ``COMMAND_SPECS`` can execute;
arbitrary shell commands are never accepted from configuration.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from self_evolve_paths import (
    DATA_ROOT,
    REVIEW_ROOT,
    RUNTIME_ROOT,
    SKILL_ROOT,
    assert_runtime_ready,
)


SCHEMA_VERSION = "2.0"
CONFIG_PATH = SKILL_ROOT / "config" / "scheduled_tasks.yaml"
SCHEDULER_ROOT = RUNTIME_ROOT / "scheduler"
RUN_LOG_DIR = SCHEDULER_ROOT / "task-runs"
STATE_FILE = SCHEDULER_ROOT / "task-state.json"
LOCKS_DIR = SCHEDULER_ROOT / "locks"
LOGS_DIR = SCHEDULER_ROOT / "logs"
TRANSACTION_LOCK_FILE = LOCKS_DIR / ".scheduler-transaction.lock"
BACKFILL_STATE_PATH = RUNTIME_ROOT / "dreaming" / "backfill-state.json"
MAX_TASK_LOGS = 40
RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class SchedulerRunLogCorruptionError(RuntimeError):
    """Raised when the current monthly run ledger cannot be trusted for quota."""


@dataclass(frozen=True)
class ArgumentSpec:
    """A safe command-line argument accepted from the task registry."""

    kind: str
    choices: tuple[str, ...] = ()
    minimum: int | float | None = None
    maximum: int | float | None = None
    pattern: str = ""


@dataclass(frozen=True)
class CommandSpec:
    """A fixed script entry point and its complete argument allowlist."""

    script: str
    fixed_args: tuple[str, ...] = ()
    args: dict[str, ArgumentSpec] = field(default_factory=dict)
    missing_is_skip: bool = False


BOOL = ArgumentSpec("bool")

# This is the single executable allowlist. Do not derive commands from any
# other config field, schedule string, task id, or user-provided shell text.
COMMAND_SPECS: dict[str, CommandSpec] = {
    "render_panel": CommandSpec(
        script="render_panel.py",
        fixed_args=("--json",),
        args={"limit": ArgumentSpec("int", minimum=10, maximum=1_000)},
    ),
    "refresh_inventory": CommandSpec(script="refresh_skill_inventory.py", fixed_args=("--quiet",)),
    "maintain_runtime": CommandSpec(script="maintain_runtime.py", fixed_args=("--report", "--json")),
    "dream_sweep": CommandSpec(
        script="dream_sweep.py",
        fixed_args=("--json",),
        args={
            "since": ArgumentSpec("str", pattern=r"^(?:\d{1,4}[dhw]|all)$"),
            "mode": ArgumentSpec("str", choices=("dry-run", "generate")),
            "budget": ArgumentSpec("str", choices=("low", "medium", "high")),
            "sources": ArgumentSpec("str", pattern=r"^(?:claude|codex)(?:,(?:claude|codex))*$"),
            "index_mode": ArgumentSpec("str", choices=("recent", "backfill")),
            "max_sessions": ArgumentSpec("int", minimum=1, maximum=10_000),
            "max_lines_per_session": ArgumentSpec("int", minimum=100, maximum=200_000),
            "min_cluster_size": ArgumentSpec("int", minimum=2, maximum=1_000),
            "max_cluster_size": ArgumentSpec("int", minimum=1, maximum=200),
            "max_reports": ArgumentSpec("int", minimum=0, maximum=1_000),
            "backfill_batch_size": ArgumentSpec("int", minimum=1, maximum=10_000),
            "backfill_order": ArgumentSpec("str", choices=("newest-first", "oldest-first")),
            "include_subagents": BOOL,
            "backfill_refresh_existing": BOOL,
            "reset_backfill": BOOL,
        },
    ),
    "distill_portrait": CommandSpec(
        script="distill_skill_portrait.py",
        fixed_args=("distill",),
        args={
            "no_llm": BOOL,
            "dry_run": BOOL,
            "force": BOOL,
            "force_all": BOOL,
            "enhanced": BOOL,
            "limit": ArgumentSpec("int", minimum=0, maximum=10_000),
            "skill": ArgumentSpec("str_list", pattern=r"^[A-Za-z0-9_.:-]{1,160}$"),
            "fields": ArgumentSpec("str", pattern=r"^[A-Za-z0-9_,-]{1,240}$"),
            "timeout": ArgumentSpec("int", minimum=10, maximum=3_600),
            "timeout_enhanced": ArgumentSpec("int", minimum=10, maximum=3_600),
            "model": ArgumentSpec("str", choices=("haiku", "sonnet", "opus")),
            "max_budget_usd": ArgumentSpec("number", minimum=0.01, maximum=5.0),
            "max_calls": ArgumentSpec("int", minimum=1, maximum=100),
            "max_total_budget_usd": ArgumentSpec("number", minimum=0.01, maximum=100.0),
        },
    ),
    # The optional weekly LLM stage has a separate config kill switch. Its
    # cluster file and executable are intentionally not configurable here.
    "deep_dream": CommandSpec(
        script="deep_dream.py",
        fixed_args=("--json",),
        args={
            "cluster_id": ArgumentSpec("str", pattern=r"^[A-Za-z0-9_-]{1,160}$"),
            "max_clusters": ArgumentSpec("int", minimum=1, maximum=10),
            "execute": BOOL,
            "timeout": ArgumentSpec("int", minimum=10, maximum=3_600),
            "model": ArgumentSpec("str", choices=("haiku", "sonnet", "opus")),
            "budget": ArgumentSpec("str", choices=("low", "medium", "high")),
            "max_budget_usd": ArgumentSpec("number", minimum=0.01, maximum=20.0),
            "per_call_budget_usd": ArgumentSpec("number", minimum=0.01, maximum=5.0),
            "max_calls": ArgumentSpec("int", minimum=1, maximum=10),
        },
        missing_is_skip=True,
    ),
    "iteration_report": CommandSpec(
        script="iteration_report.py",
        fixed_args=("--json",),
        args={
            "output": ArgumentSpec("str", pattern=r"^[\w./~\- 一-鿿]{1,200}$"),
            "since": ArgumentSpec("str", pattern=r"^(?:\d{1,4}[dhw]|all)$"),
            "no_desktop": BOOL,
        },
    ),
    "workmode_analyze": CommandSpec(
        script="workmode_pipeline.py",
        args={
            "since": ArgumentSpec("str", pattern=r"^(?:\d{1,4}[dhw]|all)$"),
            "model": ArgumentSpec("str", pattern=r"^[A-Za-z0-9_./\-]{1,120}$"),
            "force": BOOL,
        },
    ),
}


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"找不到任务配置: {path}；复制 config/scheduled_tasks.example.yaml 到 config/scheduled_tasks.yaml，填写时区并显式启用所需任务")
    try:
        import yaml
    except ImportError:
        print("缺少依赖: pyyaml", file=sys.stderr)
        print("请运行: pip install pyyaml", file=sys.stderr)
        raise SystemExit(1)

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"找不到任务配置: {path}") from None
    except Exception as exc:
        raise ValueError(f"无法读取任务配置: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("任务配置根节点必须是对象")
    return data


def _validate_argument(path: str, value: Any, spec: ArgumentSpec) -> list[str]:
    errors: list[str] = []
    values = value if spec.kind == "str_list" and isinstance(value, list) else [value]
    if spec.kind == "bool":
        if not isinstance(value, bool):
            errors.append(f"{path} 必须是布尔值")
        return errors
    if spec.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return [f"{path} 必须是整数"]
        if spec.minimum is not None and value < spec.minimum:
            errors.append(f"{path} 不能小于 {spec.minimum}")
        if spec.maximum is not None and value > spec.maximum:
            errors.append(f"{path} 不能大于 {spec.maximum}")
        return errors
    if spec.kind == "number":
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            return [f"{path} 必须是有限数字"]
        if spec.minimum is not None and float(value) < float(spec.minimum):
            errors.append(f"{path} 不能小于 {spec.minimum}")
        if spec.maximum is not None and float(value) > float(spec.maximum):
            errors.append(f"{path} 不能大于 {spec.maximum}")
        return errors
    if spec.kind == "str_list" and not isinstance(value, list):
        return [f"{path} 必须是字符串数组"]
    for item in values:
        if not isinstance(item, str):
            errors.append(f"{path} 必须是字符串" if spec.kind == "str" else f"{path} 的元素必须是字符串")
            continue
        if spec.choices and item not in spec.choices:
            errors.append(f"{path} 只能是: {', '.join(spec.choices)}")
        if spec.pattern and not re.fullmatch(spec.pattern, item):
            errors.append(f"{path} 格式不合法")
    return errors


def validate_config(config: dict[str, Any]) -> list[str]:
    """Return all schema and command allowlist violations."""
    errors: list[str] = []
    if str(config.get("schema_version", "")) != SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {SCHEMA_VERSION}")
    tasks = config.get("tasks")
    if not isinstance(tasks, list):
        return [*errors, "tasks 必须是数组"]

    seen: set[str] = set()
    for index, task in enumerate(tasks):
        prefix = f"tasks[{index}]"
        if not isinstance(task, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        for key in set(task) - {
            "id",
            "name",
            "runner",
            "recommended_schedule",
            "command",
            "run_policy",
            "notes",
        }:
            errors.append(f"{prefix}.{key} 不是 schema v2 字段")
        task_id = task.get("id")
        if not isinstance(task_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,79}", task_id):
            errors.append(f"{prefix}.id 格式不合法")
        elif task_id in seen:
            errors.append(f"{prefix}.id 重复: {task_id}")
        else:
            seen.add(task_id)
        if not isinstance(task.get("name"), str) or not task["name"].strip():
            errors.append(f"{prefix}.name 必须是非空字符串")

        runner = task.get("runner")
        if not isinstance(runner, dict):
            errors.append(f"{prefix}.runner 必须是对象")
        else:
            for key in set(runner) - {"enabled", "external_only"}:
                errors.append(f"{prefix}.runner.{key} 不是 schema v2 字段")
            for key in ("enabled", "external_only"):
                if not isinstance(runner.get(key), bool):
                    errors.append(f"{prefix}.runner.{key} 必须是布尔值")

        schedule = task.get("recommended_schedule")
        if not isinstance(schedule, dict):
            errors.append(f"{prefix}.recommended_schedule 必须是对象")
        else:
            for key in set(schedule) - {"cron", "timezone"}:
                errors.append(f"{prefix}.recommended_schedule.{key} 不是 schema v2 字段")
            cron = schedule.get("cron")
            timezone = schedule.get("timezone")
            if not isinstance(cron, str) or not cron.strip():
                errors.append(f"{prefix}.recommended_schedule.cron 必须是非空字符串")
            if not isinstance(timezone, str) or not timezone.strip():
                errors.append(f"{prefix}.recommended_schedule.timezone 必须是非空字符串")

        run_policy = task.get("run_policy")
        if not isinstance(run_policy, dict):
            errors.append(f"{prefix}.run_policy 必须是对象")
        else:
            for key in set(run_policy) - {"overlap", "timeout_minutes", "max_runs_per_day"}:
                errors.append(f"{prefix}.run_policy.{key} 不是 schema v2 字段")
            if run_policy.get("overlap") != "skip":
                errors.append(f"{prefix}.run_policy.overlap 只能是 skip")
            for key in ("timeout_minutes", "max_runs_per_day"):
                value = run_policy.get(key)
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    errors.append(f"{prefix}.run_policy.{key} 必须是正整数")

        command = task.get("command")
        if not isinstance(command, dict):
            errors.append(f"{prefix}.command 必须是对象")
            continue
        for key in set(command) - {"type", "args"}:
            errors.append(f"{prefix}.command.{key} 不是 schema v2 字段")
        command_type = command.get("type")
        spec = COMMAND_SPECS.get(command_type) if isinstance(command_type, str) else None
        if spec is None:
            errors.append(f"{prefix}.command.type 不在白名单")
            continue
        args = command.get("args", {})
        if not isinstance(args, dict):
            errors.append(f"{prefix}.command.args 必须是对象")
            continue
        for key in args:
            if key not in spec.args:
                errors.append(f"{prefix}.command.args.{key} 不在 {command_type} 白名单")
        for key, value in args.items():
            arg_spec = spec.args.get(key)
            if arg_spec:
                errors.extend(_validate_argument(f"{prefix}.command.args.{key}", value, arg_spec))
    return errors


def find_task(config: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for task in config.get("tasks", []):
        if isinstance(task, dict) and task.get("id") == task_id:
            return task
    return None


def safe_task_id(task_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", task_id)[:120] or "task"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return default


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(str(path), flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def write_json(path: Path, data: Any) -> None:
    """Atomically replace JSON after syncing both contents and directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd: int | None = None
    try:
        fd = os.open(str(temp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        _fsync_directory(path.parent)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def current_run_log(now: float | None = None) -> Path:
    stamp = time.localtime(now or time.time())
    return RUN_LOG_DIR / time.strftime("%Y-%m.jsonl", stamp)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Durably append one complete JSONL record.

    Shared scheduler callers also hold ``scheduler_transaction()`` so a
    multi-write fallback cannot interleave with another scheduler process.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("无法追加 scheduler JSONL")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_directory(path.parent)


@contextmanager
def scheduler_transaction() -> Iterator[None]:
    """Serialize every shared scheduler read-modify-write transaction.

    The lock file is deliberately stable and is never unlinked.  Removing a
    flock file creates a second inode and therefore a second lock domain for
    processes that already had the old inode open.
    """
    TRANSACTION_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(TRANSACTION_LOCK_FILE), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _record_quota_date(record: dict[str, Any]) -> str:
    quota_date = record.get("quota_date")
    if isinstance(quota_date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", quota_date):
        return quota_date
    timestamp = record.get("timestamp")
    if isinstance(timestamp, str) and re.match(r"^\d{4}-\d{2}-\d{2}(?: |T)", timestamp):
        return timestamp[:10]
    return ""


def _read_current_run_log_unlocked() -> list[dict[str, Any]]:
    """Read the quota ledger without silently accepting torn or invalid lines."""
    path = current_run_log()
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise SchedulerRunLogCorruptionError("scheduler run log is unreadable") from exc
    if payload and not payload.endswith(b"\n"):
        raise SchedulerRunLogCorruptionError("scheduler run log has a torn final line")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SchedulerRunLogCorruptionError("scheduler run log is not valid UTF-8") from exc

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise SchedulerRunLogCorruptionError(
                f"scheduler run log has a blank line at {line_number}"
            )
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SchedulerRunLogCorruptionError(
                f"scheduler run log has invalid JSON at line {line_number}"
            ) from exc
        if not isinstance(record, dict):
            raise SchedulerRunLogCorruptionError(
                f"scheduler run log line {line_number} is not an object"
            )
        records.append(record)
    return records


def _count_runs_today_unlocked(task_id: str, today: str) -> int:
    run_ids: set[str] = set()
    legacy_count = 0
    for record in _read_current_run_log_unlocked():
        if record.get("task_id") != task_id:
            continue
        quota_date = _record_quota_date(record)
        if not quota_date:
            raise SchedulerRunLogCorruptionError(
                f"scheduler run log has an undated record for task {task_id}"
            )
        if quota_date != today:
            continue

        record_type = record.get("record_type")
        if record_type in {"attempt", "result"}:
            run_id = record.get("run_id")
            if not isinstance(run_id, str) or RUN_ID_PATTERN.fullmatch(run_id) is None:
                raise SchedulerRunLogCorruptionError(
                    f"scheduler run log has an invalid run_id for task {task_id}"
                )
            run_ids.add(run_id)
        elif record_type == "event":
            continue
        elif record_type is None:
            # Compatibility with v2.0 logs written before durable attempts.
            if record.get("status") in {"skipped", "blocked"}:
                continue
            run_id = record.get("run_id")
            if isinstance(run_id, str) and RUN_ID_PATTERN.fullmatch(run_id):
                run_ids.add(run_id)
            else:
                legacy_count += 1
        else:
            raise SchedulerRunLogCorruptionError(
                f"scheduler run log has an unknown record_type for task {task_id}"
            )
    return len(run_ids) + legacy_count


def count_runs_today(task_id: str) -> int:
    with scheduler_transaction():
        return _count_runs_today_unlocked(task_id, time.strftime("%Y-%m-%d"))


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _identity_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def boot_identity() -> str:
    """Return a stable, non-secret identity for the current system boot."""
    linux_boot_id = Path("/proc/sys/kernel/random/boot_id")
    try:
        value = linux_boot_id.read_text(encoding="ascii").strip()
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        value = ""
    if value:
        return _identity_digest(f"linux:{value}")

    sysctl = Path("/usr/sbin/sysctl")
    if sysctl.is_file():
        try:
            completed = subprocess.run(
                [str(sysctl), "-n", "kern.boottime"],
                env={**os.environ, "LC_ALL": "C"},
                text=True,
                capture_output=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            completed = None
        if completed is not None and completed.returncode == 0 and completed.stdout.strip():
            return _identity_digest(f"darwin:{completed.stdout.strip()}")
    return ""


def process_start_token(pid: int) -> str:
    """Identify one PID incarnation so a reused live PID is not trusted."""
    if pid <= 0:
        return ""
    proc_stat = Path(f"/proc/{pid}/stat")
    try:
        stat_text = proc_stat.read_text(encoding="ascii")
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        stat_text = ""
    if stat_text:
        close_paren = stat_text.rfind(")")
        fields = stat_text[close_paren + 2 :].split() if close_paren >= 0 else []
        # /proc/<pid>/stat field 22 is process start time; fields starts at 3.
        if len(fields) > 19:
            return _identity_digest(f"{boot_identity()}|linux-start:{fields[19]}")

    ps = Path("/bin/ps")
    if not ps.is_file():
        ps = Path("/usr/bin/ps")
    if ps.is_file():
        try:
            completed = subprocess.run(
                [str(ps), "-o", "lstart=", "-p", str(pid)],
                env={**os.environ, "LC_ALL": "C"},
                text=True,
                capture_output=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            completed = None
        if completed is not None and completed.returncode == 0 and completed.stdout.strip():
            return _identity_digest(f"{boot_identity()}|ps-start:{completed.stdout.strip()}")
    return ""


def _process_identity_matches(payload: dict[str, Any], pid: int) -> bool:
    if not pid_is_alive(pid):
        return False
    expected_boot = payload.get("boot_id")
    current_boot = boot_identity()
    if isinstance(expected_boot, str) and expected_boot:
        if not current_boot or expected_boot != current_boot:
            return False
    expected_start = payload.get("process_start_token")
    if isinstance(expected_start, str) and expected_start:
        current_start = process_start_token(pid)
        if not current_start or current_start != expected_start:
            return False
    return True


def _finite_timestamp(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _reservation_created_at(active: dict[str, Any]) -> float | None:
    created_at = _finite_timestamp(active.get("reserved_at_epoch"))
    if created_at is not None:
        return created_at
    reserved_at = active.get("reserved_at")
    if not isinstance(reserved_at, str):
        return None
    try:
        return time.mktime(time.strptime(reserved_at, "%Y-%m-%d %H:%M:%S"))
    except (OverflowError, ValueError):
        return None


def _active_run_is_live(active: dict[str, Any], task_lock: "TaskLock", now: float) -> bool:
    created_at = _reservation_created_at(active)
    if created_at is None or created_at > now + 60:
        return False
    hard_deadline = created_at + task_lock.stale_after_seconds
    declared_deadline = _finite_timestamp(active.get("expires_at_epoch"))
    deadline = min(hard_deadline, declared_deadline) if declared_deadline is not None else hard_deadline
    if now >= deadline:
        return False
    pid = active.get("pid")
    return isinstance(pid, int) and _process_identity_matches(active, pid)


class TaskLock:
    """O_EXCL task lock guarded against stale-lock TOCTOU races.

    Creation, stale recovery, and owner release all run under the stable
    scheduler flock.  The ephemeral task lock can therefore keep its useful
    PID/time/token diagnostics without ever unlinking a peer's replacement.
    """

    def __init__(self, task_id: str, stale_after_seconds: int) -> None:
        self.path = LOCKS_DIR / f"{safe_task_id(task_id)}.lock"
        self.stale_after_seconds = max(30, stale_after_seconds)
        self.token = uuid.uuid4().hex
        self.fd: int | None = None
        self.inode: int | None = None
        self.recovered = False

    def _snapshot(self) -> tuple[bytes, os.stat_result] | None:
        try:
            with self.path.open("rb") as handle:
                content = handle.read()
                stat = os.fstat(handle.fileno())
        except (FileNotFoundError, OSError):
            return None
        return content, stat

    def _is_stale(self, snapshot: tuple[bytes, os.stat_result] | None) -> bool:
        if snapshot is None:
            return True
        content, stat = snapshot
        age = max(0.0, time.time() - stat.st_mtime)
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if not isinstance(payload, dict):
            return age > 5
        created_at = payload.get("created_at")
        pid = payload.get("pid")
        token = payload.get("token")
        if not isinstance(token, str) or not token:
            return age > 5
        if not isinstance(created_at, (int, float)) or not isinstance(pid, int):
            return age > 5
        created_at_value = _finite_timestamp(created_at)
        now = time.time()
        if created_at_value is None or created_at_value > now + 60:
            return True
        if now - created_at_value > self.stale_after_seconds:
            return True
        return not _process_identity_matches(payload, pid)

    def _recover_stale(self) -> bool:
        snapshot = self._snapshot()
        if not self._is_stale(snapshot):
            return False
        if snapshot is None:
            return True
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            return False
        self.recovered = True
        return True

    def acquire(self) -> bool:
        with scheduler_transaction():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            for attempt in range(2):
                try:
                    fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                except FileExistsError:
                    if attempt == 0 and self._recover_stale():
                        continue
                    return False

                try:
                    payload = {
                        "pid": os.getpid(),
                        "created_at": time.time(),
                        "token": self.token,
                        "process_start_token": process_start_token(os.getpid()),
                        "boot_id": boot_identity(),
                    }
                    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                    view = memoryview(encoded)
                    while view:
                        written = os.write(fd, view)
                        if written <= 0:
                            raise OSError("无法写入 task lock")
                        view = view[written:]
                    os.fsync(fd)
                    self.fd = fd
                    self.inode = os.fstat(fd).st_ino
                    return True
                except BaseException:
                    os.close(fd)
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    raise
        return False

    def release(self) -> None:
        fd = self.fd
        inode = self.inode
        self.fd = None
        self.inode = None
        if fd is None:
            return
        try:
            with scheduler_transaction():
                snapshot = self._snapshot()
                if snapshot is None:
                    return
                content, stat = snapshot
                try:
                    payload = json.loads(content.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return
                if (
                    stat.st_ino == inode
                    and isinstance(payload, dict)
                    and payload.get("token") == self.token
                ):
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
        finally:
            os.close(fd)


def _cli_name(key: str) -> str:
    return "--" + key.replace("_", "-")


def build_command(command: dict[str, Any]) -> tuple[list[str] | None, str]:
    command_type = str(command.get("type", ""))
    spec = COMMAND_SPECS[command_type]
    script = SKILL_ROOT / "scripts" / spec.script
    if not script.is_file():
        return None, "not_implemented" if spec.missing_is_skip else "script_missing"
    result = [sys.executable, str(script), *spec.fixed_args]
    args = command.get("args", {})
    for key, value in args.items():
        arg_spec = spec.args[key]
        if arg_spec.kind == "bool":
            if value:
                result.append(_cli_name(key))
        elif arg_spec.kind == "str_list":
            for item in value:
                result.extend([_cli_name(key), item])
        else:
            result.extend([_cli_name(key), str(value)])
    return result, ""


def _terminate_process_group(process: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def prune_task_logs(task_id: str) -> None:
    paths = sorted(LOGS_DIR.glob(f"{safe_task_id(task_id)}-*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
    for path in paths[MAX_TASK_LOGS:]:
        try:
            path.unlink()
        except OSError:
            pass


def run_subprocess(
    task_id: str,
    command: list[str],
    timeout_seconds: int,
    reservation: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    log_path = LOGS_DIR / f"{safe_task_id(task_id)}-{timestamp}-{uuid.uuid4().hex[:8]}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["SELF_EVOLVE_SKILL_ROOT"] = str(SKILL_ROOT)
    env["SELF_EVOLVE_DATA_ROOT"] = str(DATA_ROOT)
    env["SELF_EVOLVE_RUNTIME_ROOT"] = str(RUNTIME_ROOT)
    # Old scripts still read STATE_ROOT as the runtime leaf. Keep their output
    # external without changing the v2 data-root interpretation.
    env["SELF_EVOLVE_STATE_ROOT"] = str(RUNTIME_ROOT)
    env["SELF_EVOLVE_REVIEW_ROOT"] = str(REVIEW_ROOT)
    process: subprocess.Popen[Any] | None = None
    with log_path.open("w", encoding="utf-8") as log:
        try:
            process = subprocess.Popen(
                command,
                cwd=str(SKILL_ROOT),
                env=env,
                text=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            if reservation is not None and not bind_active_process(reservation, process.pid):
                _terminate_process_group(process)
                log.write("scheduler active-run binding failed\n")
                prune_task_logs(task_id)
                return "failed", "active_run_binding_failed", str(log_path.relative_to(RUNTIME_ROOT))
            return_code = process.wait(timeout=timeout_seconds)
        except (FileNotFoundError, OSError) as exc:
            if process is not None and process.poll() is None:
                _terminate_process_group(process)
            log.write(f"scheduler start error: {type(exc).__name__}\n")
            prune_task_logs(task_id)
            return "failed", "process_start_failed", str(log_path.relative_to(RUNTIME_ROOT))
        except subprocess.TimeoutExpired:
            assert process is not None
            _terminate_process_group(process)
            log.write(f"\nscheduler timeout after {timeout_seconds}s\n")
            prune_task_logs(task_id)
            return "failed", f"timeout_after={timeout_seconds}s", str(log_path.relative_to(RUNTIME_ROOT))
    prune_task_logs(task_id)
    if return_code == 0:
        return "success", "completed", str(log_path.relative_to(RUNTIME_ROOT))
    return "failed", f"exit_code={return_code}", str(log_path.relative_to(RUNTIME_ROOT))


def build_record(task_id: str, status: str, reason: str, started_at: float, **extra: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "task_id": task_id,
        "status": status,
        "reason": reason,
        "duration_seconds": round(time.time() - started_at, 3),
    }
    record.update(extra)
    return record


def _count_raw_source_files() -> int:
    """Count raw ``.jsonl`` source files (excluding subagents) across known roots.

    Lightweight recheck used by :func:`backfill_is_complete` to detect files that
    appeared after a previously-completed backfill run, without importing
    ``dream_sweep`` (keeps the scheduler↔sweep subprocess boundary intact).
    """
    home = Path.home()
    roots = [
        home / ".claude" / "projects",
        home / ".claude" / "transcripts",
        home / ".codex" / "sessions",
        home / ".codex" / "archived_sessions",
    ]
    total = 0
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            if "subagents" in path.parts:
                continue
            total += 1
    return total


def backfill_is_complete() -> bool:
    payload = load_json(BACKFILL_STATE_PATH, {})
    if not (isinstance(payload, dict) and payload.get("completed") is True):
        return False
    last_run = payload.get("last_run")
    last_total = last_run.get("total_discovered") if isinstance(last_run, dict) else None
    if isinstance(last_total, int) and last_total >= 0:
        # Recheck: if new source files appeared since the completed run, it isn't done.
        # Falls back to the persisted flag when last_run is absent (e.g. legacy state).
        if _count_raw_source_files() > last_total:
            return False
    return True


def _load_scheduler_state_unlocked() -> dict[str, Any]:
    state = load_json(STATE_FILE, {})
    return state if isinstance(state, dict) else {}


def bind_active_process(reservation: dict[str, Any], child_pid: int) -> bool:
    """Move an active reservation from the scheduler PID to its child PID."""
    task_id = reservation.get("task_id")
    if not isinstance(task_id, str) or not task_id or child_pid <= 0:
        return False
    child_identity = {
        "pid": child_pid,
        "process_start_token": process_start_token(child_pid),
        "boot_id": boot_identity(),
    }
    with scheduler_transaction():
        state = _load_scheduler_state_unlocked()
        raw_prior = state.get(task_id)
        prior = dict(raw_prior) if isinstance(raw_prior, dict) else {}
        raw_active = prior.get("active_run")
        if not isinstance(raw_active, dict):
            return False
        active = dict(raw_active)
        if (
            active.get("run_id") != reservation.get("run_id")
            or active.get("owner_token") != reservation.get("owner_token")
        ):
            return False
        active["supervisor_pid"] = active.get("pid")
        active.update(child_identity)
        prior["active_run"] = active
        state[task_id] = prior
        write_json(STATE_FILE, state)
    reservation.update(child_identity)
    reservation["supervisor_pid"] = os.getpid()
    return True


def reserve_daily_run(
    task_id: str,
    max_runs_per_day: int,
    task_lock: TaskLock,
) -> tuple[dict[str, Any] | None, str]:
    """Atomically check daily quota and durably reserve one execution slot."""
    now = time.time()
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    reservation = {
        "task_id": task_id,
        "run_id": uuid.uuid4().hex,
        "quota_date": today,
        "reserved_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
        "reserved_at_epoch": now,
        "expires_at_epoch": now + task_lock.stale_after_seconds,
        "pid": os.getpid(),
        "process_start_token": process_start_token(os.getpid()),
        "boot_id": boot_identity(),
        "owner_token": task_lock.token,
    }
    with scheduler_transaction():
        state = _load_scheduler_state_unlocked()
        raw_prior = state.get(task_id)
        prior = dict(raw_prior) if isinstance(raw_prior, dict) else {}
        active = prior.get("active_run")
        state_changed = False
        if isinstance(active, dict):
            if _active_run_is_live(active, task_lock, now):
                # A live reservation is a second line of defence if a task
                # lock was externally removed or its PID was reused.
                return None, "already_running"
            prior.pop("active_run", None)
            state_changed = True

        try:
            runs_today = _count_runs_today_unlocked(task_id, today)
        except SchedulerRunLogCorruptionError:
            if state_changed:
                state[task_id] = prior
                write_json(STATE_FILE, state)
            return None, "scheduler_run_log_corrupt"
        if runs_today >= max_runs_per_day:
            if state_changed:
                state[task_id] = prior
                write_json(STATE_FILE, state)
            return None, "max_runs_per_day_reached"

        attempt = {
            "record_type": "attempt",
            "timestamp": reservation["reserved_at"],
            "task_id": task_id,
            "status": "reserved",
            "reason": "quota_reserved",
            "duration_seconds": 0,
            **reservation,
        }
        append_jsonl(current_run_log(now), attempt)
        prior["active_run"] = reservation
        state[task_id] = prior
        write_json(STATE_FILE, state)
    return reservation, ""


def persist_record(
    record: dict[str, Any],
    reservation: dict[str, Any] | None = None,
) -> bool:
    """Durably append a result and merge its task state in one transaction."""
    task_id = str(record.get("task_id", ""))
    stored_record = dict(record)
    if reservation is None:
        stored_record["record_type"] = "event"
    else:
        reservation_task_id = reservation.get("task_id")
        run_id = reservation.get("run_id")
        if reservation_task_id != task_id:
            raise ValueError("result task_id does not match reservation")
        if not isinstance(run_id, str) or RUN_ID_PATTERN.fullmatch(run_id) is None:
            raise ValueError("reservation run_id is invalid")
        supplied_run_id = record.get("run_id")
        if supplied_run_id not in {None, run_id}:
            raise ValueError("result run_id does not match reservation")
        stored_record.update(
            {
                "record_type": "result",
                "run_id": run_id,
                "quota_date": reservation.get("quota_date"),
            }
        )
    with scheduler_transaction():
        state = _load_scheduler_state_unlocked()
        raw_prior = state.get(task_id)
        prior = dict(raw_prior) if isinstance(raw_prior, dict) else {}
        terminal_repeat = (
            record.get("terminal") is True
            and prior.get("terminal") is True
            and prior.get("last_reason") == record.get("reason")
        )
        if terminal_repeat:
            return False

        append_jsonl(current_run_log(), stored_record)
        prior.update(
            {
                "last_run_at": record.get("timestamp", ""),
                "last_status": record.get("status", ""),
                "last_reason": record.get("reason", ""),
                "last_duration_seconds": record.get("duration_seconds", 0),
                "terminal": record.get("terminal") is True,
            }
        )
        if reservation is not None:
            prior["last_run_id"] = reservation.get("run_id")
            active = prior.get("active_run")
            if (
                isinstance(active, dict)
                and active.get("run_id") == reservation.get("run_id")
                and active.get("owner_token") == reservation.get("owner_token")
            ):
                prior.pop("active_run", None)
        state[task_id] = prior
        write_json(STATE_FILE, state)
    return True


def persist_result(
    record: dict[str, Any],
    reservation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record["persisted"] = persist_record(record, reservation)
    return record


def run_task(task: dict[str, Any], trigger: str) -> dict[str, Any]:
    task_id = str(task.get("id", ""))
    started_at = time.time()
    runner = task["runner"]
    if runner["enabled"] is not True:
        return persist_result(
            build_record(
                task_id,
                "blocked",
                "runner_disabled",
                started_at,
                next_action="enable runner.enabled or remove/disable the matching external Cron task",
            )
        )
    if runner["external_only"] is True and trigger != "external":
        return persist_result(
            build_record(
                task_id,
                "blocked",
                "external_trigger_required",
                started_at,
                next_action="add --trigger external to the registered external Cron command",
            )
        )
    if task_id == "history-backfill-index" and backfill_is_complete():
        return persist_result(
            build_record(task_id, "skipped", "backfill_already_completed", started_at, terminal=True)
        )

    run_policy = task["run_policy"]
    timeout_seconds = run_policy["timeout_minutes"] * 60
    lock = TaskLock(task_id, stale_after_seconds=timeout_seconds + 300)
    if not lock.acquire():
        return persist_result(build_record(task_id, "skipped", "already_running", started_at))
    try:
        command, build_error = build_command(task["command"])
        if command is None:
            status = "skipped" if build_error == "not_implemented" else "failed"
            return persist_result(
                build_record(
                    task_id,
                    status,
                    build_error,
                    started_at,
                    lock_recovered=lock.recovered,
                )
            )

        reservation, reservation_error = reserve_daily_run(
            task_id,
            run_policy["max_runs_per_day"],
            lock,
        )
        if reservation is None:
            if reservation_error == "scheduler_run_log_corrupt":
                record = build_record(
                    task_id,
                    "blocked",
                    reservation_error,
                    started_at,
                    lock_recovered=lock.recovered,
                    next_action=(
                        "inspect and repair the current scheduler quota ledger at "
                        f"{current_run_log().relative_to(RUNTIME_ROOT)}; preserve all valid "
                        "attempt records before retrying"
                    ),
                )
                record["persisted"] = False
                return record
            quota_blocked = reservation_error == "max_runs_per_day_reached"
            return persist_result(
                build_record(
                    task_id,
                    "blocked" if quota_blocked else "skipped",
                    reservation_error,
                    started_at,
                    lock_recovered=lock.recovered,
                    **(
                        {
                            "next_action": (
                                "wait for the next quota day or explicitly raise "
                                "run_policy.max_runs_per_day in the reviewed registry"
                            )
                        }
                        if quota_blocked
                        else {}
                    ),
                )
            )

        status, reason, log_path = run_subprocess(
            task_id,
            command,
            timeout_seconds,
            reservation,
        )
        return persist_result(
            build_record(
                task_id,
                status,
                reason,
                started_at,
                run_id=reservation["run_id"],
                quota_date=reservation["quota_date"],
                log_path=log_path,
                lock_recovered=lock.recovered,
            ),
            reservation,
        )
    finally:
        lock.release()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a registered Self Evolve Cron task.")
    parser.add_argument("--task", help="Task id from config/scheduled_tasks.yaml")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--run-now", action="store_true", help="Run the selected registered task")
    parser.add_argument("--trigger", choices=("manual", "external"), default="manual")
    parser.add_argument("--validate-config", action="store_true", help="Validate schema v2 and exit")
    parser.add_argument(
        "--allow-disabled",
        action="store_true",
        help="Deprecated and ignored; runner.enabled is an absolute kill switch",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.allow_disabled:
        print(
            "警告: --allow-disabled 已废弃且被忽略；它不会绕过 runner.enabled。",
            file=sys.stderr,
        )

    try:
        config = load_yaml(args.config.expanduser())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    errors = validate_config(config)
    if errors:
        payload = {"valid": False, "schema_version": config.get("schema_version"), "errors": errors}
        print(json.dumps(payload, ensure_ascii=False) if args.json else "\n".join(f"- {item}" for item in errors))
        return 2
    if args.validate_config:
        payload = {"valid": True, "schema_version": SCHEMA_VERSION, "task_count": len(config["tasks"])}
        print(json.dumps(payload, ensure_ascii=False) if args.json else f"配置有效: {payload['task_count']} 个任务")
        return 0
    if not args.run_now or not args.task:
        parser.error("执行任务需要同时提供 --task 和 --run-now")

    try:
        assert_runtime_ready()
    except ValueError as exc:
        detail = str(exc)
        migration_blocked = detail.startswith("migration_required:")
        record = build_record(
            args.task,
            "blocked",
            "migration_required" if migration_blocked else "unsafe_state_layout",
            time.time(),
            detail=detail,
            **(
                {
                    "next_action": (
                        "python3 scripts/migrate_state.py --dry-run; "
                        "确认预览后运行 python3 scripts/migrate_state.py --apply"
                    )
                }
                if migration_blocked
                else {}
            ),
        )
        record["persisted"] = False
        print(json.dumps(record, ensure_ascii=False) if args.json else record["reason"])
        return 1
    task = find_task(config, args.task)
    if task is None:
        record = build_record(args.task, "failed", "task_not_found", time.time())
        persist_result(record)
        print(json.dumps(record, ensure_ascii=False) if args.json else record["reason"])
        return 1

    record = run_task(task, args.trigger)
    if args.json:
        print(json.dumps(record, ensure_ascii=False))
    else:
        print(f"{record['task_id']}: {record['status']} ({record['reason']})")
    return 0 if record["status"] in {"success", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
