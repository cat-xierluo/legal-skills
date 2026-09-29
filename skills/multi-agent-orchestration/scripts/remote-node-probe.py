#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""远程节点容量与前置条件探测（remote node probe，fail-closed）。

spawn-worker-remote.sh 在任何 ssh 派发副作用（receipt 传输 / 远程 spawn）之前
调用本 probe，采集远程节点的负载/内存/磁盘/git 基线/claude CLI/活跃会话数/
skill 副本版本/时钟偏差，按 personal config remote_nodes 段的门限判定，输出
multi-agent-orchestration.remote-node-probe.v1 单行 JSON。

退出码契约（references/25-remote-node-dispatch.md）：
  0   status=ok            全部门通过
  4   capacity_denied      load15 / 活跃会话数 / 内存 / 磁盘 超门限
                           （PM 侧记 PARKED_FOR_REMOTE_CAPACITY，排队重试不回落本机）
  3   precondition_failed  git 基线冲突 / skill 副本版本不一致 / claude 不可用 /
                           时钟偏差过大（PM 侧修复后重试：push / pull / 对时）
  65  unreachable          ssh 不可达 / 远程采集脚本整体失败（可回落本机派发）
  64  usage                参数错误 / 配置缺节点

fail-closed 语义：远程采集脚本崩了或输出不可解析 → 65（环境级不可用，宁拒勿猜）；
单个字段采集失败只降级该字段并在 gaps 里留痕（不编造数值）。

测试注入：--ssh-command 换掉 ssh 二进制（mock）；--skip-fetch 跳过 git fetch
（只读诊断用，正式派发链路必须 fetch 后比对基线）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time

SCHEMA = "multi-agent-orchestration.remote-node-probe.v1"
EXIT_OK, EXIT_CAPACITY, EXIT_PRECONDITION, EXIT_UNREACHABLE, EXIT_USAGE = 0, 4, 3, 65, 64
CLOCK_SKEW_MAX_SECONDS = 120

# 远程侧采集脚本：POSIX sh 可执行（不依赖远端 python3），每行 KEY<TAB>VALUE。
# REMOTE_ROOT/SKILL_ROOT/SKIP_FETCH 以 bash 位置参数传入（ssh 不转发本地 env）。
# claude 检测显式走 zsh -lc（非交互 ssh 无登录 PATH，见 references/25 §PATH）。
REMOTE_COLLECT_SCRIPT = r"""
REMOTE_ROOT="$1"; SKILL_ROOT="$2"; SKIP_FETCH="$3"
field() { printf '%s\t%s\n' "$1" "$2"; }
field NCPU "$(sysctl -n hw.ncpu 2>/dev/null || echo '?')"
field LOADAVG "$(sysctl -n vm.loadavg 2>/dev/null || echo '?')"
field MEMSIZE "$(sysctl -n hw.memsize 2>/dev/null || echo '?')"
field FREE_PAGES "$(vm_stat 2>/dev/null | awk '/Pages free/{gsub(/[.]/,""); print $NF; exit}')"
field INACTIVE_PAGES "$(vm_stat 2>/dev/null | awk '/Pages inactive/{gsub(/[.]/,""); print $NF; exit}')"
field SPECULATIVE_PAGES "$(vm_stat 2>/dev/null | awk '/Pages speculative/{gsub(/[.]/,""); print $NF; exit}')"
field PAGESIZE "$(pagesize 2>/dev/null || echo '?')"
field EPOCH "$(date +%s)"
if [ -d "$REMOTE_ROOT" ]; then
  field REMOTE_ROOT_EXISTS 1
  field DISK_KB "$(df -k "$REMOTE_ROOT" 2>/dev/null | awk 'NR==2{print $2"\t"$4}')"
  if git -C "$REMOTE_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    field GIT_REPO 1
    if [ "$SKIP_FETCH" = "1" ]; then
      field GIT_FETCH skipped
    elif git -C "$REMOTE_ROOT" fetch origin >/dev/null 2>&1; then
      field GIT_FETCH ok
    else
      field GIT_FETCH failed
    fi
    field GIT_ORIGIN_MAIN "$(git -C "$REMOTE_ROOT" rev-parse --verify --quiet origin/main^{commit} 2>/dev/null || echo '?')"
    field GIT_BRANCH "$(git -C "$REMOTE_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
    field GIT_DIRTY "$(git -C "$REMOTE_ROOT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  else
    field GIT_REPO 0
  fi
else
  field REMOTE_ROOT_EXISTS 0
fi
CLAUDE_PATH=$(zsh -lc 'command -v claude' 2>/dev/null || true)
if [ -n "$CLAUDE_PATH" ]; then
  field CLAUDE_PATH "$CLAUDE_PATH"
  field CLAUDE_VERSION "$(zsh -lc 'claude --version' 2>/dev/null | head -1)"
else
  field CLAUDE_PATH "?"
  field CLAUDE_VERSION "?"
fi
field ACTIVE_SESSIONS "$(pgrep -c -f '[c]laude' 2>/dev/null || echo 0)"
if [ -f "$SKILL_ROOT/CHANGELOG.md" ]; then
  field SKILL_VERSION "$(grep -m1 -oE '\[[0-9]+\.[0-9]+\.[0-9]+\]' "$SKILL_ROOT/CHANGELOG.md" | tr -d '[]')"
else
  field SKILL_VERSION missing
fi
"""

USAGE = ("usage: remote-node-probe.py --node NAME [--config FILE] "
         "[--ssh-command CMD] [--skip-fetch] [--expect-base-sha SHA] "
         "[--expect-skill-version V] [--load-threshold F] [--active-session-cap N] "
         "[--min-free-disk-gb N] [--min-free-memory-percent N] [--connect-timeout N] "
         "[--json-pretty]")


def fail(status: str, reason: str, payload: dict, code: int) -> int:
    payload["status"] = status
    payload["reason"] = reason
    print(json.dumps(payload, ensure_ascii=False))
    return code


def load_node_config(config_path: str, node: str, overrides: dict) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    nodes = config.get("remote_nodes") or {}
    if node not in nodes:
        raise SystemExit(
            f"ERROR: node '{node}' not found in remote_nodes of {config_path} (exit {EXIT_USAGE})")
    node_cfg = dict(nodes[node])
    for key, value in overrides.items():
        if value is not None:
            node_cfg[key] = value
    node_cfg.setdefault("enabled", False)
    node_cfg.setdefault("load_threshold", 6.0)
    node_cfg.setdefault("active_session_cap", 4)
    node_cfg.setdefault("min_free_disk_gb", 20)
    node_cfg.setdefault("min_free_memory_percent", 15)
    node_cfg.setdefault("connect_timeout_seconds", 10)
    for required in ("ssh_alias", "remote_root", "skill_root"):
        if not node_cfg.get(required):
            raise SystemExit(
                f"ERROR: remote_nodes.{node}.{required} is required (exit {EXIT_USAGE})")
    return node_cfg


def run_remote_collect(ssh_command: str, alias: str, timeout: int, remote_root: str,
                       skill_root: str, skip_fetch: bool) -> tuple[dict, float]:
    # 路径与开关以位置参数传给远端 bash（ssh 不转发本地 env）。
    remote_command = "bash -s -- " + " ".join(
        shlex.quote(part) for part in
        (remote_root, skill_root, "1" if skip_fetch else "0"))
    started = time.monotonic()
    proc = subprocess.run(
        [ssh_command, "-o", "BatchMode=yes", "-o", f"ConnectTimeout={timeout}",
         alias, remote_command],
        input=REMOTE_COLLECT_SCRIPT, capture_output=True, text=True,
        timeout=timeout + 60,
    )
    elapsed = time.monotonic() - started
    if proc.returncode != 0:
        raise RuntimeError(
            f"ssh exit {proc.returncode}: {(proc.stderr or '').strip()[:200]}")
    fields: dict = {}
    for line in proc.stdout.splitlines():
        if "\t" not in line:
            continue
        key, _, value = line.partition("\t")
        if key and key not in fields:
            fields[key] = value.strip()
    return fields, elapsed


def to_int(value, default=None):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def to_float(value, default=None):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def parse_loadavg(raw: str):
    # macOS sysctl -n vm.loadavg → "{ 1.23, 2.34, 3.45 }"
    numbers = re.findall(r"[\d.]+", raw or "")
    if len(numbers) >= 3:
        return to_float(numbers[0]), to_float(numbers[1]), to_float(numbers[2])
    return None, None, None


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--node", required=True)
    parser.add_argument("--config", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "config",
        "orchestration-personal.json"))
    parser.add_argument("--ssh-command", default="ssh")
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--expect-base-sha")
    parser.add_argument("--expect-skill-version")
    parser.add_argument("--load-threshold", type=float)
    parser.add_argument("--active-session-cap", type=int)
    parser.add_argument("--min-free-disk-gb", type=float)
    parser.add_argument("--min-free-memory-percent", type=float)
    parser.add_argument("--connect-timeout", type=int)
    parser.add_argument("--json-pretty", action="store_true")
    args = parser.parse_args(sys.argv[1:] or ["--help"])

    if not os.path.isfile(args.config):
        print(f"ERROR: personal config not found: {args.config}", file=sys.stderr)
        return EXIT_USAGE

    try:
        node_cfg = load_node_config(args.config, args.node, {
            "load_threshold": args.load_threshold,
            "active_session_cap": args.active_session_cap,
            "min_free_disk_gb": args.min_free_disk_gb,
            "min_free_memory_percent": args.min_free_memory_percent,
            "connect_timeout_seconds": args.connect_timeout,
        })
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE

    payload = {
        "schema": SCHEMA,
        "node": args.node,
        "ssh_alias": node_cfg["ssh_alias"],
        "gaps": [],
    }
    if not node_cfg.get("enabled"):
        return fail("precondition_failed",
                    f"remote_nodes.{args.node}.enabled is not true",
                    payload, EXIT_PRECONDITION)

    # 1) 可达性 + 采集（整体失败 = 环境级不可用，exit 65）
    try:
        fields, connect_seconds = run_remote_collect(
            args.ssh_command, node_cfg["ssh_alias"],
            int(node_cfg["connect_timeout_seconds"]), node_cfg["remote_root"],
            node_cfg["skill_root"], args.skip_fetch)
    except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
        return fail("unreachable", f"REMOTE_NODE_UNREACHABLE: {exc}", payload,
                    EXIT_UNREACHABLE)
    payload["ssh"] = {"connect_seconds": round(connect_seconds, 2)}

    # 2) 时钟偏差（TTL 300s 的回执判定依赖双端时钟大体一致）
    remote_epoch = to_int(fields.get("EPOCH"))
    if remote_epoch is not None:
        offset = remote_epoch - int(time.time())
        payload["clock"] = {"offset_seconds": offset}
        if abs(offset) > CLOCK_SKEW_MAX_SECONDS:
            return fail("precondition_failed",
                        f"REMOTE_NODE_CLOCK_SKEW: |{offset}s| > {CLOCK_SKEW_MAX_SECONDS}s",
                        payload, EXIT_PRECONDITION)
    else:
        payload["gaps"].append("clock")

    # 3) 负载与容量门（exit 4 族）
    ncpu = to_int(fields.get("NCPU"))
    load1, load5, load15 = parse_loadavg(fields.get("LOADAVG", "?"))
    payload["load"] = {"l1": load1, "l5": load5, "l15": load15, "cores": ncpu,
                       "threshold": node_cfg["load_threshold"]}
    if load15 is None or ncpu is None:
        payload["gaps"].append("load")
    elif load15 > float(node_cfg["load_threshold"]):
        return fail("capacity_denied",
                    f"REMOTE_NODE_CAPACITY_DENIED: load15={load15} > "
                    f"threshold={node_cfg['load_threshold']} (cores={ncpu})",
                    payload, EXIT_CAPACITY)

    memsize = to_int(fields.get("MEMSIZE"))
    page_size = to_int(fields.get("PAGESIZE"))
    free_pages = to_int(fields.get("FREE_PAGES"))
    inactive_pages = to_int(fields.get("INACTIVE_PAGES"))
    speculative_pages = to_int(fields.get("SPECULATIVE_PAGES"))
    memory_block = {
        "total_bytes": memsize,
        "page_size": page_size,
        "free_estimate_bytes": None,
        "free_percent": None,
        "min_free_percent": node_cfg["min_free_memory_percent"],
    }
    if memsize and page_size and free_pages is not None:
        reclaimable = (free_pages + (inactive_pages or 0)
                       + (speculative_pages or 0)) * page_size
        free_percent = round(reclaimable * 100.0 / memsize, 1)
        memory_block["free_estimate_bytes"] = reclaimable
        memory_block["free_percent"] = free_percent
        payload["memory"] = memory_block
        if free_percent < float(node_cfg["min_free_memory_percent"]):
            return fail("capacity_denied",
                        f"REMOTE_NODE_CAPACITY_DENIED: memory free≈{free_percent}% < "
                        f"{node_cfg['min_free_memory_percent']}%",
                        payload, EXIT_CAPACITY)
    else:
        payload["gaps"].append("memory")

    disk_block = {"total_gb": None, "free_gb": None,
                  "min_free_gb": node_cfg["min_free_disk_gb"]}
    disk_raw = fields.get("DISK_KB", "?")
    disk_parts = disk_raw.split("\t") if disk_raw != "?" else []
    if len(disk_parts) == 2:
        total_gb = round(to_int(disk_parts[0], 0) / 1024 / 1024, 1)
        free_gb = round(to_int(disk_parts[1], 0) / 1024 / 1024, 1)
        disk_block["total_gb"], disk_block["free_gb"] = total_gb, free_gb
        payload["disk"] = disk_block
        if free_gb < float(node_cfg["min_free_disk_gb"]):
            return fail("capacity_denied",
                        f"REMOTE_NODE_CAPACITY_DENIED: disk free {free_gb}GB < "
                        f"{node_cfg['min_free_disk_gb']}GB",
                        payload, EXIT_CAPACITY)
    else:
        payload["gaps"].append("disk")

    active_sessions = to_int(fields.get("ACTIVE_SESSIONS"), 0)
    payload["runtime"] = {
        "claude_path": None if fields.get("CLAUDE_PATH") == "?" else fields.get("CLAUDE_PATH"),
        "claude_version": None if fields.get("CLAUDE_VERSION") in ("?", None) else fields.get("CLAUDE_VERSION"),
        "active_sessions": active_sessions,
        "session_cap": node_cfg["active_session_cap"],
    }

    # 4) 前置条件门（exit 3 族）
    if fields.get("REMOTE_ROOT_EXISTS") != "1":
        return fail("precondition_failed",
                    f"REMOTE_NODE_ROOT_MISSING: {node_cfg['remote_root']}",
                    payload, EXIT_PRECONDITION)
    if fields.get("GIT_REPO") != "1":
        return fail("precondition_failed",
                    f"REMOTE_NODE_ROOT_NOT_GIT: {node_cfg['remote_root']}",
                    payload, EXIT_PRECONDITION)
    git_block = {
        "remote_root": node_cfg["remote_root"],
        "current_branch": None if fields.get("GIT_BRANCH") == "?" else fields.get("GIT_BRANCH"),
        "dirty_files": to_int(fields.get("GIT_DIRTY")),
        "fetch": fields.get("GIT_FETCH"),
        "origin_main_sha": None if fields.get("GIT_ORIGIN_MAIN") == "?" else fields.get("GIT_ORIGIN_MAIN"),
        "expect_base_sha": args.expect_base_sha,
        "base_match": None,
    }
    payload["git"] = git_block
    if not args.skip_fetch and fields.get("GIT_FETCH") != "ok":
        return fail("precondition_failed",
                    f"REMOTE_NODE_GIT_FETCH_FAILED: {node_cfg['remote_root']}",
                    payload, EXIT_PRECONDITION)
    if args.expect_base_sha and git_block["origin_main_sha"]:
        if git_block["origin_main_sha"] == args.expect_base_sha:
            git_block["base_match"] = True
        else:
            git_block["base_match"] = False
            return fail("precondition_failed",
                        f"REMOTE_NODE_BASE_MISMATCH: node origin/main="
                        f"{git_block['origin_main_sha'][:12]} expect="
                        f"{args.expect_base_sha[:12]} — 先对齐基线（PM push 或节点 pull）",
                        payload, EXIT_PRECONDITION)
    skill_version = fields.get("SKILL_VERSION")
    payload["skill"] = {"version": None if skill_version in ("?", "missing", None) else skill_version,
                        "expect_version": args.expect_skill_version,
                        "path": node_cfg["skill_root"]}
    if skill_version == "missing":
        return fail("precondition_failed",
                    f"REMOTE_NODE_SKILL_MISSING: {node_cfg['skill_root']}/CHANGELOG.md",
                    payload, EXIT_PRECONDITION)
    if args.expect_skill_version and skill_version not in ("?", None) \
            and skill_version != args.expect_skill_version:
        return fail("precondition_failed",
                    f"REMOTE_NODE_SKILL_VERSION_MISMATCH: node={skill_version} "
                    f"expect={args.expect_skill_version} — 节点侧 git pull origin main",
                    payload, EXIT_PRECONDITION)
    if payload["runtime"]["claude_path"] is None:
        return fail("precondition_failed",
                    "REMOTE_NODE_CLAUDE_MISSING: zsh -lc 'command -v claude' 为空",
                    payload, EXIT_PRECONDITION)

    # 5) 容量门：活跃会话（含用户手开会话，最后判避免被 load 门掩盖根因）
    if active_sessions > int(node_cfg["active_session_cap"]):
        return fail("capacity_denied",
                    f"REMOTE_NODE_CAPACITY_DENIED: active claude sessions "
                    f"{active_sessions} > cap {node_cfg['active_session_cap']}",
                    payload, EXIT_CAPACITY)

    payload["status"] = "ok"
    payload["reason"] = ""
    print(json.dumps(payload, ensure_ascii=False,
                     indent=2 if args.json_pretty else None))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
