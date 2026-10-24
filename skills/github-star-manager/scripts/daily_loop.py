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


def _quarantine(path: Path) -> Dict:
    """把不可解析的文件改名或复制保留（不销毁原内容），返回隔离结果。

    返回 {"preserved": bool, "backup": Optional[str], "method": str, "detail": str}。
    preserved=True 表示原始损坏内容已完整保留在 backup 中；preserved=False 表示
    无法保留——调用方必须拒绝覆盖原文件，不得销毁现场。
    """
    stamp = now_utc().strftime("%Y%m%dT%H%M%S.%fZ")
    backup = path.with_name(f"{path.name}.corrupt-{stamp}")
    try:
        os.replace(path, backup)
        return {"preserved": True, "backup": str(backup), "method": "rename", "detail": ""}
    except OSError as exc:
        detail = f"改名失败（{type(exc).__name__}）"
    try:
        data = path.read_bytes()
    except OSError as exc:
        return {"preserved": False, "backup": None, "method": "failed",
                "detail": f"{detail}；读取原始内容失败（{type(exc).__name__}）"}
    try:
        backup.write_bytes(data)
    except OSError as exc:
        return {"preserved": False, "backup": None, "method": "failed",
                "detail": f"{detail}；写入备份失败（{type(exc).__name__}）"}
    method = "copy"
    try:
        path.unlink()
        method = "copy+remove"
    except OSError:
        # 原件仍在原位，但副本已保存——原始内容不会丢失。
        pass
    return {"preserved": True, "backup": str(backup), "method": method, "detail": detail}


def _quarantine_result(result) -> Dict:
    """把 _quarantine 的返回值规整成隔离结果字典。

    兼容 None（隔离完全失败）和旧版字符串返回值，避免调用方误把失败当成功。
    """
    if isinstance(result, dict):
        return result
    if isinstance(result, str) and result:
        return {"preserved": True, "backup": result, "method": "rename", "detail": ""}
    return {"preserved": False, "backup": None, "method": "failed",
            "detail": "隔离失败"}


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
      隔离失败时拒绝获取租约（LeaseError），损坏原文保留在原位不被覆盖。
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
            quarantine = _quarantine_result(_quarantine(path))
            if not quarantine["preserved"]:
                # 隔离失败意味着原始损坏内容无法安全保留。绝不能继续写入：
                # atomic_json 会直接覆盖原文件，把现场毁掉。
                raise LeaseError(
                    "损坏租约文件隔离失败——原始内容无法保留，拒绝获取租约，"
                    f"原文件保持原样未改动：{path}（{quarantine['detail']}）")
            notes.append(
                f"损坏租约文件已隔离至 {quarantine['backup']}"
                f"（{quarantine['method']}）"
                + (f"；{quarantine['detail']}" if quarantine.get("detail") else "")
                + "——本轮按无可用租约继续，属显式降级")
            current = {}
        expired = bool(current) and lease_expired(current, now)
        if current:
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
        if run_id and current.get("run_id") and current.get("run_id") != run_id:
            notes.append(f"运行 ID 切换：{current.get('run_id')} → {run_id}")
        elif (not run_id and current
              and current.get("owner") == owner and current.get("run_id")):
            # 同 owner 续租且调用方未给新 run_id → 保留原 run_id，
            # 否则原 run_id 将永远无法用于释放租约。
            run_id = current["run_id"]
            notes.append(f"保留原运行 ID：{run_id}（同 owner 续租，未指定新的 --run-id）")
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


def run_age_hours(path: Path, generated_at=None,
                  now: Optional[datetime] = None) -> Optional[float]:
    """\u8fd0\u884c\u5305\u751f\u6210\u65f6\u95f4\u8ddd\u73b0\u5728\u7684\u5c0f\u65f6\u6570\u3002

    \u4f18\u5148\u7528\u8fd0\u884c\u5305\u81ea\u5e26\u7684 generated_at\uff1b\u7f3a\u5931\u6216\u4e0d\u53ef\u89e3\u6790\u65f6\u56de\u9000\u5230\u6587\u4ef6 mtime\u3002
    \u65e0\u6cd5\u5224\u5b9a\u65f6\u8fd4\u56de None\uff08\u4e0d\u505a\u65b0\u9c9c\u5ea6\u5224\u5b9a\uff09\u3002
    """
    now = now or now_utc()
    stamp = parse_dt(generated_at)
    if stamp is None:
        try:
            stamp = datetime.fromtimestamp(Path(path).stat().st_mtime, timezone.utc)
        except (OSError, TypeError, ValueError):
            return None
    return (now - stamp).total_seconds() / 3600


def latest_run_file(data_dir) -> Optional[Path]:
    """最近一次准备阶段的运行包（不含回执文件）。"""
    directory = runs_dir(data_dir)
    if not directory.is_dir():
        return None
    files = [p for p in directory.glob("*.json") if not p.name.endswith(".receipt.json")]
    if not files:
        return None
    return max(files, key=lambda p: (p.stat().st_mtime, p.name))

