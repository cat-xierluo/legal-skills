#!/usr/bin/env python3
"""每日闭环的并发租约与运行回执（离线原语）。

本模块只做两件事：
1. 并发租约（lease.json）：同一状态目录只允许一个 writer 跑每日闭环。
   - acquire：现有租约未过期且 owner 不同 → 明确拒绝（LeaseConflict）。
   - 过期租约可被接管；损坏租约不阻塞流程，改为显式降级（隔离备份 + 告警）。
   - release：只删除自己持有的租约，别人的租约不动。
2. 运行回执（runs/<ts>.receipt.json）：区分 judged / silent / failed 三种结局。
   - silent 必须带正向证据（候选数=0 且队列无新增待研判，或调用方显式给出的证据）。
   - Agent 崩溃 / 缺证据 → failed，不得记成 silent。

约束：全程离线——不调用 gh、不读取网络、不执行上游代码。
原子性依赖既有 lockutil.write_lock（fcntl.flock 排他），写文件用临时文件 + os.replace。
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from lockutil import write_lock

LEASE_FILE = "auto-opportunities/lease.json"
RUNS_DIR = "auto-opportunities/runs"
RECEIPT_SCHEMA = "daily-receipt/1.0"
LEASE_SCHEMA = "daily-lease/1.0"
DEFAULT_TTL_SECONDS = 1800


class LeaseConflict(RuntimeError):
    """现有租约仍有效且属于其他 owner——调用方必须拒绝写入。"""


class LeaseError(RuntimeError):
    """租约本身不可用（owner 为空等无法继续的输入）。"""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def atomic_json(path: Path, value) -> None:
    """原子写 JSON（临时文件 + os.replace）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def lease_path(data_dir) -> Path:
    return Path(data_dir) / LEASE_FILE


def runs_dir(data_dir) -> Path:
    return Path(data_dir) / RUNS_DIR


def lease_dir(data_dir) -> Path:
    return Path(data_dir) / "auto-opportunities"


def _quarantine(path: Path) -> Optional[str]:
    """把不可解析的文件改名保留（不删除），返回备份路径。"""
    stamp = now_utc().strftime("%Y%m%dT%H%M%S.%fZ")
    backup = path.with_name(f"{path.name}.corrupt-{stamp}")
    try:
        os.replace(path, backup)
    except OSError:
        try:
            backup.write_bytes(path.read_bytes())
            path.unlink(missing_ok=True)
        except OSError:
            return None
    return str(backup)


def read_lease(data_dir) -> Dict:
    """读取当前租约。

    返回 {} 表示没有租约；{"corrupt": True, ...} 表示文件存在但无法解析——
    调用方必须显式降级，不得当作"没有租约"静默通过。
    """
    path = lease_path(data_dir)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"corrupt": True, "path": str(path)}
    if not isinstance(value, dict) or not value.get("owner"):
        return {"corrupt": True, "path": str(path)}
    if parse_dt(value.get("expires_at")) is None:
        return {**value, "corrupt": True, "path": str(path),
                "note": "lease expires_at missing or unparsable"}
    return value


def lease_expired(lease: Dict, now: Optional[datetime] = None) -> bool:
    now = now or now_utc()
    expires = parse_dt(lease.get("expires_at"))
    if expires is None:
        return True
    return expires <= now


def acquire_lease(data_dir, owner: str, run_id: Optional[str] = None,
                   ttl_seconds: int = DEFAULT_TTL_SECONDS,
                   now: Optional[datetime] = None) -> Tuple[Dict, List[str]]:
    """获取租约。返回 (lease, notes)；冲突时抛 LeaseConflict。

    规则：
    - 没有租约 → 直接持有。
    - 现有租约未过期且 owner 不同 → LeaseConflict（明确报错，不覆盖）。
    - 现有租约未过期且 owner 相同 → 续租（同一 owner 可重入）。
    - 现有租约已过期 → 接管，并记录被接管的旧 owner。
    - 现有租约文件损坏 → 隔离备份后接管，并在 notes 中显式降级告警。
    """
    if not owner:
        raise LeaseError("owner 不能为空")
    now = now or now_utc()
    directory = lease_dir(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    notes: List[str] = []
    with write_lock(directory):
        path = lease_path(data_dir)
        current = read_lease(data_dir)
        if current.get("corrupt"):
            backup = _quarantine(path)
            notes.append(
                "损坏租约文件已隔离" + (f"至 {backup}" if backup else "（备份失败，文件保持原样）")
                + "——本轮按无可用租约继续，属显式降级")
            current = {}
        if current:
            expired = lease_expired(current, now)
            if not expired and current.get("owner") != owner:
                raise LeaseConflict(
                    f"租约被占用：owner={current.get('owner')} "
                    f"run_id={current.get('run_id')} "
                    f"expires_at={current.get('expires_at')}——拒绝并发写入")
            if expired:
                notes.append(f"接管过期租约：owner={current.get('owner')} "
                             f"expires_at={current.get('expires_at')}")
            else:
                notes.append(f"同一 owner 续租：owner={owner}")
        lease = {
            "schema_version": LEASE_SCHEMA,
            "owner": owner,
            "run_id": run_id or now.strftime("%Y%m%dT%H%M%S.%fZ"),
            "acquired_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=max(1, int(ttl_seconds)))).isoformat(),
        }
        atomic_json(path, lease)
    return lease, notes


def release_lease(data_dir, owner: str, run_id: Optional[str] = None,
                  now: Optional[datetime] = None) -> Dict:
    """释放租约——只删自己持有的那一份。

    返回 {"released": bool, ...}；他人持有时 released=False 且不删除文件。
    """
    if not owner:
        raise LeaseError("owner 不能为空")
    directory = lease_dir(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    with write_lock(directory):
        path = lease_path(data_dir)
        current = read_lease(data_dir)
        if current.get("corrupt"):
            return {"released": False, "degraded": True,
                    "reason": "租约文件损坏，无法确认归属——未删除任何文件",
                    "path": str(path)}
        if not current:
            return {"released": False, "reason": "没有持有中的租约",
                    "path": str(path)}
        if current.get("owner") != owner:
            return {"released": False, "conflict": True,
                    "reason": f"租约属于其他 owner={current.get('owner')}——未删除",
                    "path": str(path)}
        if run_id and current.get("run_id") and current.get("run_id") != run_id:
            return {"released": False, "conflict": True,
                    "reason": f"租约 run_id={current.get('run_id')} 与请求不一致——未删除",
                    "path": str(path)}
        path.unlink(missing_ok=True)
        return {"released": True, "path": str(path),
                "run_id": current.get("run_id"), "owner": owner}


def lease_status(data_dir, now: Optional[datetime] = None) -> Dict:
    now = now or now_utc()
    current = read_lease(data_dir)
    if not current:
        return {"held": False, "path": str(lease_path(data_dir))}
    if current.get("corrupt"):
        return {"held": False, "degraded": True, "corrupt": True,
                "path": str(lease_path(data_dir)),
                "note": "租约文件损坏，未能判定归属"}
    expires = parse_dt(current.get("expires_at"))
    return {"held": not lease_expired(current, now),
            "expired": lease_expired(current, now),
            "owner": current.get("owner"),
            "run_id": current.get("run_id"),
            "acquired_at": current.get("acquired_at"),
            "expires_at": current.get("expires_at"),
            "seconds_remaining": round((expires - now).total_seconds()) if expires else None,
            "path": str(lease_path(data_dir))}


def write_receipt(data_dir, receipt: Dict,
                  timestamp: Optional[str] = None) -> Path:
    """写运行回执到 auto-opportunities/runs/<ts>.receipt.json。"""
    directory = runs_dir(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or now_utc().strftime("%Y%m%dT%H%M%S.%fZ")
    path = directory / f"{stamp}.receipt.json"
    with write_lock(directory):
        atomic_json(path, receipt)
    return path


def latest_run_file(data_dir) -> Optional[Path]:
    """最近一次准备阶段的运行包（不含回执文件）。"""
    directory = runs_dir(data_dir)
    if not directory.is_dir():
        return None
    files = [p for p in directory.glob("*.json") if not p.name.endswith(".receipt.json")]
    if not files:
        return None
    return max(files, key=lambda p: (p.stat().st_mtime, p.name))

