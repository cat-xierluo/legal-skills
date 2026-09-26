#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""声纹库共用存储层：HTTP 服务与本地 CLI 共用同一套读写契约。

职责（Task-017/018 整改）：
- 按 CAM++ 声纹模型显式校验向量：维度、数值有限性、有效范数；返回归一化单位向量。
- 读取时逐条校验历史条目，坏条目隔离并给出原因，不影响其余有效记录。
- 区分"库不存在"（空库）与"库损坏"：读路径可降级告警；写路径必须拒绝，保留原件。
- 原子保存：同目录临时文件写入、flush、fsync 后 os.replace；失败时旧库字节不变。
- 进程间锁覆盖整个读-改-写事务（仅锁最终 write 无法防止丢更新）。
- 新建的库/锁/临时文件仅当前用户可读写。

声纹库文件 assets/speaker-profiles.json 属本地个人数据，被 .gitignore 排除。
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import json
import math
import os
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np

# 当前声纹模型为 CAM++，输出 192 维向量；注册与读取均按此契约校验。
# 若更换模型维度，须同步更新此处并核对既有库的兼容说明（Task-017 基线）。
EXPECTED_EMBEDDING_DIM = 192
EMBEDDING_MODEL = "cam++"

# 归一化前的最小范数；低于该值视为无信息向量，拒绝入库。
MIN_VALID_NORM = 1e-8


class RegistryCorruptError(RuntimeError):
    """库文件存在但无法安全解析；写操作必须拒绝，保留原件。"""


def validate_embedding(raw, expected_dim: int = EXPECTED_EMBEDDING_DIM) -> np.ndarray:
    """校验一条声纹向量并返回 float32 单位向量；非法输入抛 ValueError（原因可直接展示）。"""
    if isinstance(raw, (str, bytes)) or raw is None:
        raise ValueError("embedding 必须是数值数组")
    try:
        with np.errstate(over="ignore"):
            # 1e40 这类 float64 有限值转 float32 后溢出为 inf，由随后的 isfinite 拦截。
            vector = np.asarray(raw, dtype=np.float32).reshape(-1)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"embedding 无法解析为数值数组: {exc}") from exc
    if vector.size != expected_dim:
        raise ValueError(
            f"embedding 维度必须为 {expected_dim}（当前模型 {EMBEDDING_MODEL} 输出），实际为 {vector.size}"
        )
    if not np.all(np.isfinite(vector)):
        # 1e40 这类 float64 有限值转 float32 后溢出为 inf，同样在此拦截。
        raise ValueError("embedding 含非有限数值（NaN/Inf，含 float32 溢出），无法注册")
    norm = float(np.linalg.norm(vector.astype(np.float64)))
    if not math.isfinite(norm) or norm <= MIN_VALID_NORM:
        raise ValueError("embedding 为零向量或范数无效，无法注册")
    unit = (vector.astype(np.float64) / norm).astype(np.float32)
    if not np.all(np.isfinite(unit)):
        raise ValueError("embedding 归一化后出现非有限数值，无法注册")
    return unit


def _entry_issue(item, expected_dim: int) -> str | None:
    """返回单条库记录无效的原因；有效时返回 None。原因不包含向量原文。"""
    if not isinstance(item, dict):
        return "条目不是对象"
    name = str(item.get("name", "")).strip()
    if not name:
        return "条目缺少有效 name"
    try:
        validate_embedding(item.get("embedding"), expected_dim)
    except ValueError as exc:
        return f"条目「{name}」向量无效: {exc}"
    return None


def _load_payload(path: Path) -> tuple[list | None, str | None]:
    """读取库文件的原始 profiles 列表；返回 (profiles, 损坏原因)。

    文件不存在 → ([], None)；JSON/顶层结构损坏 → (None, 原因)。
    """
    try:
        with open(path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
    except FileNotFoundError:
        return [], None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, f"库文件损坏，无法解析: {exc}"
    profiles = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(profiles, list):
        return None, "库文件顶层结构无效（缺少 profiles 列表）"
    return profiles, None


def load_profiles(path: Path | str, expected_dim: int = EXPECTED_EMBEDDING_DIM,
                  keep_invalid: bool = False) -> tuple[list[dict], list[str], bool]:
    """读取声纹库。

    Returns:
        (profiles, issues, corrupt)
        - profiles: 有效条目；keep_invalid=True 时返回全部原始条目（写事务须保留坏条目原样，
          不自动改写或清理真实库，坏条目的处置交给用户）
        - issues: 隔离坏条目的具体原因；corrupt 时含整体损坏原因
        - corrupt: True 表示库整体不可解析（读路径应降级为空库并告警，写路径必须拒绝）
    """
    path = Path(path)
    profiles, corrupt_reason = _load_payload(path)
    if corrupt_reason is not None:
        return [], [corrupt_reason], True
    valid: list[dict] = []
    issues: list[str] = []
    for index, item in enumerate(profiles):
        reason = _entry_issue(item, expected_dim)
        if reason is None:
            valid.append(item)
        else:
            issues.append(f"第 {index + 1} 条记录已隔离：{reason}")
    return (profiles if keep_invalid else valid), issues, False


def _locked(path: Path):
    """进程间排它锁；锁文件与库同目录、仅当前用户可读写。"""
    lock_path = path.parent / f".{path.name}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_stream = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    os.fchmod(lock_stream, 0o600)

    @contextlib.contextmanager
    def _guard():
        try:
            fcntl.flock(lock_stream, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(lock_stream, fcntl.LOCK_UN)
            finally:
                os.close(lock_stream)

    return _guard()


def _write_atomic(path: Path, profiles: list) -> None:
    """原子写库：同目录临时文件 → 写入/flush/fsync → os.replace。

    任何一步失败都会清理临时文件并抛出异常，旧库字节保持不变。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EXPECTED_EMBEDDING_DIM,
        "profiles": profiles,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    temporary = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.tmp-", dir=str(path.parent)
        )
        temporary = Path(temp_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)
    finally:
        if temporary is not None:
            with contextlib.suppress(OSError):
                temporary.unlink()


def save_profiles(path: Path | str, profiles: list) -> None:
    """原子保存整个声纹库（调用方保证 profiles 已校验）。"""
    with _locked(Path(path)):
        _write_atomic(Path(path), profiles)


def mutate_profiles(path: Path | str, mutate, expected_dim: int = EXPECTED_EMBEDDING_DIM):
    """在进程间排它锁内完成 读→校验→修改→原子保存 的完整事务。

    库损坏时抛 RegistryCorruptError（保留原件，不做任何修改）。
    mutate 接收 (原始全部条目, 隔离原因列表)，返回 (新条目列表, 任意结果值)；
    写回使用 mutate 返回的完整列表，历史坏条目是否保留由 mutate 决定（默认应原样保留）。
    """
    path = Path(path)
    with _locked(path):
        profiles, issues, corrupt = load_profiles(path, expected_dim, keep_invalid=True)
        if corrupt:
            raise RegistryCorruptError(issues[0] if issues else "库文件损坏")
        new_profiles, result = mutate(profiles, issues)
        _write_atomic(path, new_profiles)
        return new_profiles, result, issues


def build_entry(name: str, unit_vector: np.ndarray, source_file: str | None = None,
                source_label: str | None = None) -> dict:
    """构造一条规范化库记录（unit_vector 须经 validate_embedding）。"""
    return {
        "name": name,
        "embedding": [round(float(x), 6) for x in unit_vector],
        "dim": int(unit_vector.size),
        "model": EMBEDDING_MODEL,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": source_file,
        "source_label": source_label,
    }
