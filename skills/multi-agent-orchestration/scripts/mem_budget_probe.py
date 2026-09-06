#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""物理内存预算探测（memory budget probe，fail-closed）。

spawn 前的物理内存维度预检：读 hw.memsize 与 vm_stat / memory_pressure /
vm.swapusage 的现场快照，折算「当前还能安全承诺几个 worker」，输出
memory-budget.summary.v1 JSON。quota preflight 管 API 配额维度，本 probe 管
物理内存维度；两者都在任何 provider lease / worktree create / terminal /
dispatch 副作用之前运行（spawn-worker.sh mem_budget_gate_run）。

预算模型（references/22-mem-budget-lane.md 为权威推导）：

  available_bytes   ≈ (Pages free + speculative + inactive) × page size
                      （可回收而无须新换出的近似；memory_pressure 百分比兜底）
  reserve_bytes     = max(2 GiB, 10% × hw.memsize)（系统/内核余量，不派给 worker）
  safe_available    = max(0, available - reserve)
  pressure level    = worst(memory_pressure 关键词, vm.swapusage used/total)
                      normal=1.0 / warn=0.5（折半收紧）/ critical=0（slots=0）
  slots             = floor(safe_available × tighten / budget_bytes)

fail-closed 语义：
  - hw.memsize 缺失，或 vm_stat 与 memory_pressure 均不可用（无法确立可用性
    基准）→ exit 1，输出不含任何额度字段（绝不编造）。
  - SPAWN_WORKER_MEM_BUDGET_BYTES 非法（非十进制非负整数）→ exit 1。
  - 额度不足（slots == 0）→ exit 3，status=denied，reason 含可用/预算/缺口。
  - =0 显式关闭整道门 → status=disabled，exit 0（与 NODE_OPTIONS 堆顶的
    opt-out 风格一致）。

数据源读取默认走绝对路径（macOS）；任一读取失败只降级该源信号，可用性基准
仍按上述 fail-closed 规则判定。测试/离线诊断用 --fixture-dir（或
MEM_BUDGET_FIXTURE_DIR）注入快照文件，文件缺席 = 该源读取失败。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any, Callable

EXIT_OK = 0
EXIT_FAIL_CLOSED = 1
EXIT_DENIED = 3

SCHEMA = "memory-budget.summary.v1"

# per-worker 默认预算 3 GiB：agent 本体（约 1.2 GiB）+ 测试/构建余量（约 2 GiB），
# 与 v2.20.0 NODE_OPTIONS=--max-old-space-size=2048 堆顶量级对齐。
DEFAULT_BUDGET_BYTES = 3 * 1024 ** 3
# 系统保留：不派给 worker 的底仓，防 spawn 后内核/缓存无路可走。
RESERVE_FLOOR_BYTES = 2 * 1024 ** 3
RESERVE_RATIO = 0.10

GIB = float(1024 ** 3)

SYSCTL = "/usr/sbin/sysctl"
VM_STAT = "/usr/bin/vm_stat"
MEMORY_PRESSURE = "/usr/bin/memory_pressure"
SOURCE_TIMEOUT_SECONDS = 10

FIXTURE_FILES = {
    "hw_memsize": "hw_memsize.txt",
    "vm_swapusage": "vm_swapusage.txt",
    "vm_stat": "vm_stat.txt",
    "memory_pressure": "memory_pressure.txt",
}

BUDGET_ENV = "SPAWN_WORKER_MEM_BUDGET_BYTES"
FIXTURE_ENV = "MEM_BUDGET_FIXTURE_DIR"

SWAP_WARN_RATIO = 0.75
SWAP_CRITICAL_RATIO = 0.95
PRESSURE_WARN_AVAILABLE_PERCENT = 15.0
PRESSURE_CRITICAL_AVAILABLE_PERCENT = 5.0


def _gib(value: int) -> str:
    return f"{value / GIB:.2f}GiB"


def parse_hw_memsize(text: str) -> int | None:
    """`sysctl -n hw.memsize` → 物理内存字节数。"""
    if not text:
        return None
    match = re.search(r"(\d+)", text)
    if not match:
        return None
    total = int(match.group(1))
    return total if total > 0 else None


_SIZE_SUFFIXES = {
    "": 1, "B": 1,
    "K": 1024, "KB": 1024, "KIB": 1024,
    "M": 1024 ** 2, "MB": 1024 ** 2, "MIB": 1024 ** 2,
    "G": 1024 ** 3, "GB": 1024 ** 3, "GIB": 1024 ** 3,
    "T": 1024 ** 4, "TB": 1024 ** 4, "TIB": 1024 ** 4,
}


def _parse_size(token: str) -> int | None:
    match = re.fullmatch(r"([\d.]+)\s*([A-Za-z]*)", token.strip())
    if not match:
        return None
    multiplier = _SIZE_SUFFIXES.get(match.group(2).upper())
    if multiplier is None:
        return None
    try:
        value = int(float(match.group(1)) * multiplier)
    except (ValueError, OverflowError):
        return None
    return value if value >= 0 else None


def parse_swap_usage(text: str) -> dict[str, Any] | None:
    """`sysctl -n vm.swapusage` → {"total_bytes","used_bytes","free_bytes","used_ratio"}。

    形态：`total = 2048.00M  used = 512.00M  free = 1536.00M`。
    """

    def grab(name: str) -> int | None:
        match = re.search(rf"\b{name}\s*=\s*([\d.]+\s*[A-Za-z]*)", text)
        return _parse_size(match.group(1)) if match else None

    if not text:
        return None
    total = grab("total")
    used = grab("used")
    free = grab("free")
    if total is None or used is None:
        return None
    if total == 0:
        # 未配置 swap：无换出空间，也无换出压力信号。
        return {"total_bytes": 0, "used_bytes": 0, "free_bytes": 0, "used_ratio": 0.0,
                "no_swap": True}
    if free is None:
        free = max(0, total - used)
    used = min(used, total)
    return {"total_bytes": total, "used_bytes": used, "free_bytes": free,
            "used_ratio": used / total, "no_swap": False}


def parse_vm_stat(text: str) -> dict[str, Any] | None:
    """`vm_stat` → {"page_size","available_bytes","pages"}。

    需要表头 page size 与 Pages free（speculative / inactive 缺席按 0 容忍，
    兼容不同 macOS 版本的行集差异）。解析不出可用性基准 → None。
    """
    if not text:
        return None
    header = re.search(r"page size of (\d+) bytes", text)
    if not header:
        return None
    page_size = int(header.group(1))
    if page_size <= 0:
        return None
    pages: dict[str, int] = {}
    for line in text.splitlines():
        match = re.match(r"^Pages?\s+([^:]+?)\s*:\s*([\d,]+)\s*\.?\s*$", line)
        if match:
            pages[match.group(1).strip().lower()] = int(match.group(2).replace(",", ""))
    free = pages.get("free")
    if free is None:
        return None
    available_pages = free + pages.get("speculative", 0) + pages.get("inactive", 0)
    return {
        "page_size": page_size,
        "available_bytes": available_pages * page_size,
        "pages": pages,
    }


def parse_memory_pressure(text: str) -> dict[str, Any] | None:
    """`memory_pressure`（无参数只读形态）→ level 与百分比。

    兼容两类输出形态：关键词句式（"The system has sufficient space." /
    "is under increasing pressure" / "critical memory situation"）与
    百分比句式（"X% of memory in use by apps, Y% available"）。
    关键词是操作系统自己的分级，优先于百分比推导；两者都没有 → None。
    """
    if not text:
        return None
    lowered = text.lower()
    level: str | None = None
    if "critical" in lowered:
        level = "critical"
    elif "increasing pressure" in lowered or re.search(r"\bwarn(ing)?\b", lowered):
        level = "warn"
    elif "sufficient space" in lowered or re.search(r"pressure[^:\n]{0,24}:\s*normal", lowered):
        level = "normal"
    used_percent: float | None = None
    available_percent: float | None = None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*of memory\s+(?:in use|used)", lowered)
    if match:
        used_percent = float(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*available", lowered)
    if match:
        available_percent = float(match.group(1))
    if level is None and available_percent is not None:
        # 无关键词但有官方可用百分比：按阈值推导分级。
        if available_percent <= PRESSURE_CRITICAL_AVAILABLE_PERCENT:
            level = "critical"
        elif available_percent <= PRESSURE_WARN_AVAILABLE_PERCENT:
            level = "warn"
        else:
            level = "normal"
    if level is None:
        return None
    return {"level": level, "used_percent": used_percent,
            "available_percent": available_percent}


_LEVEL_ORDER = {"normal": 0, "warn": 1, "critical": 2}
_TIGHTEN_FACTOR = {"normal": 1.0, "warn": 0.5, "critical": 0.0}


def aggregate_pressure(memory_pressure: dict[str, Any] | None,
                       swap: dict[str, Any] | None) -> dict[str, Any]:
    """汇成单一 level + 收紧因子 + 命中信号列表；无任何信号时按 normal 不收紧。"""
    signals: list[str] = []
    level = "normal"
    if memory_pressure is not None:
        mp_level = memory_pressure["level"]
        if _LEVEL_ORDER[mp_level] > _LEVEL_ORDER[level]:
            level = mp_level
        if mp_level != "normal":
            signals.append(f"memory_pressure:{mp_level}")
    if swap is not None and not swap.get("no_swap"):
        ratio = float(swap["used_ratio"])
        if ratio >= SWAP_CRITICAL_RATIO:
            if _LEVEL_ORDER["critical"] > _LEVEL_ORDER[level]:
                level = "critical"
            signals.append(f"swap_used_ratio={ratio:.2f}>={SWAP_CRITICAL_RATIO}")
        elif ratio >= SWAP_WARN_RATIO:
            if _LEVEL_ORDER["warn"] > _LEVEL_ORDER[level]:
                level = "warn"
            signals.append(f"swap_used_ratio={ratio:.2f}>={SWAP_WARN_RATIO}")
    return {"level": level, "tighten_factor": _TIGHTEN_FACTOR[level], "signals": signals}


def resolve_budget(flag_value: str | None, env: dict[str, str]) -> tuple[int | None, str | None]:
    """--budget > SPAWN_WORKER_MEM_BUDGET_BYTES > 默认 3 GiB；非法值 fail-closed。"""
    raw: str | None = None
    source = "default"
    if flag_value is not None:
        raw, source = flag_value, "flag"
    elif env.get(BUDGET_ENV, "").strip() != "":
        raw, source = env.get(BUDGET_ENV), "env"
    if raw is None:
        return DEFAULT_BUDGET_BYTES, source
    token = raw.strip()
    if not re.fullmatch(r"\d+", token):
        return None, source
    return int(token), source


def collect_real() -> dict[str, str | None]:
    def run(argv: list[str]) -> str | None:
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=SOURCE_TIMEOUT_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout or None

    return {
        "hw_memsize": run([SYSCTL, "-n", "hw.memsize"]),
        "vm_swapusage": run([SYSCTL, "-n", "vm.swapusage"]),
        "vm_stat": run([VM_STAT]),
        "memory_pressure": run([MEMORY_PRESSURE]),
    }


def collect_fixture(fixture_dir: str) -> dict[str, str | None]:
    """快照文件缺席 = 该源读取失败（与真实读取失败同语义）。"""
    snapshots: dict[str, str | None] = {}
    for name, filename in FIXTURE_FILES.items():
        path = os.path.join(fixture_dir, filename)
        try:
            with open(path, encoding="utf-8") as stream:
                snapshots[name] = stream.read()
        except OSError:
            snapshots[name] = None
    return snapshots


def evaluate(snapshots: dict[str, str | None], budget_bytes: int,
             budget_source: str) -> dict[str, Any]:
    """纯决策核心：快照 + 预算 → memory-budget.summary.v1 payload。"""
    sources: dict[str, str] = {}
    for name in ("hw_memsize", "vm_stat", "memory_pressure", "vm_swapusage"):
        sources[name] = "ok" if snapshots.get(name) else "failed"

    total_bytes = parse_hw_memsize(snapshots.get("hw_memsize") or "")
    vm_stat = parse_vm_stat(snapshots.get("vm_stat") or "")
    memory_pressure = parse_memory_pressure(snapshots.get("memory_pressure") or "")
    swap = parse_swap_usage(snapshots.get("vm_swapusage") or "")

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "budget_bytes": budget_bytes,
        "budget_source": budget_source,
        "sources": sources,
    }

    if total_bytes is None:
        payload["status"] = "unprobeable"
        payload["reason"] = "hw.memsize 不可读：无法确立物理内存总量（fail-closed，不输出额度）"
        return payload

    # 可用性基准：vm_stat 页账本优先，memory_pressure 官方百分比兜底；两者皆失 → fail-closed。
    if vm_stat is not None:
        available_bytes = min(vm_stat["available_bytes"], total_bytes)
        availability_basis = "vm_stat"
        page_size: int | None = vm_stat["page_size"]
    elif memory_pressure is not None and memory_pressure["available_percent"] is not None:
        # 百分比兜底同样钳位到 [0, total]：病态快照（>100%）不得虚增可用内存。
        available_bytes = min(int(total_bytes * memory_pressure["available_percent"] / 100.0),
                              total_bytes)
        availability_basis = "memory_pressure_percent"
        page_size = None
    else:
        payload["status"] = "unprobeable"
        payload["total_bytes"] = total_bytes
        payload["reason"] = ("vm_stat 与 memory_pressure 均不可用：无法确立可用内存基准"
                            "（fail-closed，不输出额度）")
        return payload

    reserve_bytes = max(RESERVE_FLOOR_BYTES, int(total_bytes * RESERVE_RATIO))
    safe_available = max(0, available_bytes - reserve_bytes)
    pressure = aggregate_pressure(memory_pressure, swap)

    payload.update({
        "total_bytes": total_bytes,
        "page_size": page_size,
        "availability_basis": availability_basis,
        "available_bytes": available_bytes,
        "reserve_bytes": reserve_bytes,
        "safe_available_bytes": safe_available,
        "pressure": pressure,
    })
    if swap is not None:
        payload["swap"] = {key: swap[key] for key in
                           ("total_bytes", "used_bytes", "free_bytes", "used_ratio")}

    if budget_bytes == 0:
        payload["status"] = "disabled"
        payload["slots"] = None
        payload["reason"] = f"{BUDGET_ENV}=0 显式关闭内存预算门（opt-out，探测数据照常输出）"
        return payload

    effective = int(safe_available * pressure["tighten_factor"])
    slots = effective // budget_bytes
    payload["slots"] = slots
    payload["effective_available_bytes"] = effective
    if pressure["level"] == "critical":
        payload["status"] = "denied"
        payload["reason"] = (f"内存压力 critical（{', '.join(pressure['signals']) or 'level=critical'}）"
                            f"→ slots=0；safe_available={_gib(safe_available)} "
                            f"budget={_gib(budget_bytes)}")
    elif slots < 1:
        deficit = budget_bytes - effective
        payload["status"] = "denied"
        payload["reason"] = (f"safe_available={_gib(safe_available)}"
                            f"×tighten({pressure['tighten_factor']})={_gib(effective)} "
                            f"< budget={_gib(budget_bytes)}（缺口 {_gib(deficit)}，"
                            f"pressure={pressure['level']}）")
    else:
        payload["status"] = "ok"
        payload["reason"] = (f"safe_available={_gib(safe_available)} "
                            f"budget={_gib(budget_bytes)} → slots={slots}"
                            f"（pressure={pressure['level']}）")
    return payload


def human_summary(payload: dict[str, Any]) -> str:
    if payload.get("status") == "unprobeable":
        return f"MEM_BUDGET_PROBE: status=unprobeable reason={payload.get('reason', '')}"
    pressure = payload.get("pressure", {})
    return (f"MEM_BUDGET_PROBE: status={payload.get('status')} "
            f"total={_gib(payload['total_bytes'])} "
            f"available={_gib(payload['available_bytes'])} "
            f"reserve={_gib(payload['reserve_bytes'])} "
            f"safe={_gib(payload['safe_available_bytes'])} "
            f"budget={_gib(payload['budget_bytes'])} "
            f"slots={payload.get('slots')} pressure={pressure.get('level')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="物理内存预算探测：输出 memory-budget.summary.v1（fail-closed）")
    parser.add_argument("--json", action="store_true", help="输出单行 JSON（机器合同）")
    parser.add_argument("--budget", default=None,
                        help="per-worker 预算字节数（覆盖 %s；0=关闭）" % BUDGET_ENV)
    parser.add_argument("--fixture-dir", default=None,
                        help=("测试/离线诊断快照目录（%s 同名）；文件缺席=该源读取失败"
                              % FIXTURE_ENV))
    args = parser.parse_args(argv)

    budget_bytes, budget_source = resolve_budget(args.budget, dict(os.environ))
    if budget_bytes is None:
        payload = {
            "schema": SCHEMA,
            "status": "config_invalid",
            "budget_source": budget_source,
            "reason": (f"{BUDGET_ENV}/{args.budget!r} 不是合法的非负整数字节数"
                       "（fail-closed，不输出额度）"),
        }
        json.dump(payload, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return EXIT_FAIL_CLOSED

    fixture_dir = args.fixture_dir or os.environ.get(FIXTURE_ENV, "").strip() or None
    if fixture_dir is not None:
        snapshots = collect_fixture(fixture_dir)
    else:
        snapshots = collect_real()

    payload = evaluate(snapshots, budget_bytes, budget_source)
    if args.json:
        json.dump(payload, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(human_summary(payload))
        if payload.get("status") == "denied":
            print(f"MEM_BUDGET_PROBE_REASON: {payload['reason']}")
    status = payload.get("status")
    if status == "denied":
        return EXIT_DENIED
    if status in {"unprobeable", "config_invalid"}:
        return EXIT_FAIL_CLOSED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
