#!/usr/bin/env python3
"""Codex App 心跳的有界循环适配器（一次心跳 = 一次有限循环）。

调度器是外部 Codex App heartbeat（automation），本脚本不是守护进程、不是
sleep 循环、不是 TUI 注入器、不是调度器、也不是并行控制器。每次调用只做：

  1. 读取显式常规文件 JSON 请求（钉扎 controller / 状态身份 / 变更适配器 /
     PM owner / 有界超时），校验路径与身份（fail-closed）；
  2. 经现有 autopilot-controller CLI（argv 数组、shell=False）执行一次
     status（只读）→ reconcile（收集事实 + 规划唯一下一动作）；
  3. 仅当 reconcile 给出 ready 的外部变更意图、且动作在受支持 allowlist、
     且配额/验收反压/事实新鲜度/租约身份全部通过时，执行至多一次 tick 变更；
  4. 输出机器 JSON：decision（wait/review/dispatch/park/complete）、精确
     receipts、是否还需要未来心跳、以及 fail-closed 原因。

硬边界（本脚本永远不做）：
  - 不循环、不 sleep、不派生后台进程；
  - 不注入 raw 终端输入；不改 TASKS；不自行挑选价值任务（任务选择权在
    PM 与 controller 的既定事实管线，绝不按 token 丰度排序）；
  - 不重试不确定的变更：tick 至多调用一次，任何非零退出/超时/无法解析
    输出都按"结果不确定"上报，绝不二次执行。

用法：
  codex-heartbeat-cycle.py --request REQUEST.json        # 执行一次有限循环
  codex-heartbeat-cycle.py --check-request REQUEST.json  # 仅结构校验，不执行

退出码：0 = 完整走完一次有限循环（decision 以 JSON 为准）；
64/65 = 请求缺失或非法；78 = 钉扎文件漂移（未调用控制器）；70 = 内部错误。
非零退出时错误 JSON 输出到 stderr（与 autopilot-controller 约定一致）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time
from typing import Any


REQUEST_CONTRACT = "multi-agent-orchestration.codex-heartbeat-cycle-request.v1"
CYCLE_CONTRACT = "multi-agent-orchestration.codex-heartbeat-cycle.v1"
SCHEMA_VERSION = 1

MAX_REQUEST_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
# 控制器对自身子进程使用相同秒数上界；外加固定 slack 覆盖解释器启动与
# 控制器簿记开销。整条链路仍然有界：至多 4 次有界子进程调用。
SLACK_SECONDS = 5

EXIT_USAGE = 64
EXIT_DATA = 65
EXIT_SOFTWARE = 70
EXIT_PINNED = 78

# 允许经本适配器执行的控制器外部变更动作（与 autopilot_runtime 的
# EXTERNAL_ACTIONS 一致）；内部动作（observe/adopt/complete 等）不需要 tick。
ALLOWED_TICK_ACTIONS = frozenset(
    {"spawn", "settle", "verify", "push", "open_pr", "merge", "writeback"}
)
DEFAULT_TIMEOUTS = {"status_seconds": 30, "reconcile_seconds": 60, "tick_seconds": 120}
TIMEOUT_BOUNDS = {
    "status_seconds": (1, 120),
    "reconcile_seconds": (1, 300),
    "tick_seconds": (1, 600),
}
# 与 dispatch-value-gate.v2 的验收反压阈值一致：待验收 PR > 2 时不允许再 spawn。
BACKPRESSURE_THRESHOLD = 2

OID_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
HEX64_RE = re.compile(r"[0-9a-f]{64}")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

REQUIRED_REQUEST_KEYS = {
    "schema_version", "contract", "controller", "mutation_adapter", "repo",
    "project_id", "policy_commit", "owner", "fencing_token",
}
OPTIONAL_REQUEST_KEYS = {"timeouts", "gates"}
ALL_REQUEST_KEYS = REQUIRED_REQUEST_KEYS | OPTIONAL_REQUEST_KEYS
TIMEOUT_KEYS = set(DEFAULT_TIMEOUTS)
GATE_KEYS = {"quota_denied", "acceptance_backpressure"}


class RequestError(Exception):
    def __init__(self, message: str, code: int = EXIT_DATA):
        super().__init__(message)
        self.code = code


class PinnedError(RequestError):
    def __init__(self, message: str):
        super().__init__(message, EXIT_PINNED)


def utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))


def fail(message: str, code: int) -> int:
    print(
        json.dumps({"error": message, "exit_code": code}, ensure_ascii=False),
        file=sys.stderr,
    )
    return code


# ---------------------------------------------------------------------------
# 请求加载与校验（fail-closed；--check-request 不触碰任何钉扎文件）
# ---------------------------------------------------------------------------


def load_request_file(raw_path: str) -> dict[str, Any]:
    path = Path(raw_path)
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise RequestError(f"无法读取请求文件：{exc}") from exc
    if stat.S_ISLNK(mode):
        raise RequestError("请求文件不允许是 symlink")
    if not stat.S_ISREG(mode):
        raise RequestError("请求路径必须是常规文件")
    flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            raw = stream.read(MAX_REQUEST_BYTES + 1)
    except OSError as exc:
        raise RequestError(f"无法读取请求文件：{exc}") from exc
    if len(raw) > MAX_REQUEST_BYTES:
        raise RequestError(f"请求 JSON 超过 {MAX_REQUEST_BYTES} 字节上限")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RequestError(f"请求 JSON 非法：{exc}") from exc
    if not isinstance(payload, dict):
        raise RequestError("请求 JSON 根必须是对象")
    return payload


def _plain_identifier(value: Any, label: str, max_len: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise RequestError(f"{label} 必须是非空且不超过 {max_len} 字符的字符串")
    if value[0] == "-":
        raise RequestError(f"{label} 不允许以 '-' 开头（argv 安全）")
    if CONTROL_RE.search(value):
        raise RequestError(f"{label} 不允许包含控制字符")
    return value


def _pinned_binding(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise RequestError(f"{label} 必须是恰好含 path/sha256 的对象")
    path = value["path"]
    if not isinstance(path, str) or not path.startswith("/"):
        raise RequestError(f"{label}.path 必须是绝对路径字符串")
    if CONTROL_RE.search(path):
        raise RequestError(f"{label}.path 不允许包含控制字符")
    digest = value["sha256"]
    if not isinstance(digest, str) or HEX64_RE.fullmatch(digest) is None:
        raise RequestError(f"{label}.sha256 必须是 64 位小写十六进制摘要")
    return {"path": path, "sha256": digest}


def validate_request(payload: dict[str, Any]) -> dict[str, Any]:
    if (
        type(payload.get("schema_version")) is not int
        or payload["schema_version"] != SCHEMA_VERSION
    ):
        raise RequestError(f"schema_version 必须等于 {SCHEMA_VERSION}")
    if payload.get("contract") != REQUEST_CONTRACT:
        raise RequestError(f"contract 必须等于 {REQUEST_CONTRACT}")
    unsupported = sorted(set(payload) - ALL_REQUEST_KEYS)
    if unsupported:
        raise RequestError(f"请求包含不支持的字段：{unsupported}")
    missing = sorted(REQUIRED_REQUEST_KEYS - set(payload))
    if missing:
        raise RequestError(f"请求缺少必填字段：{missing}")

    repo = payload["repo"]
    if not isinstance(repo, str) or not repo.startswith("/"):
        raise RequestError("repo 必须是绝对路径字符串")
    if CONTROL_RE.search(repo):
        raise RequestError("repo 不允许包含控制字符")
    identity = {
        "repo": repo,
        "project_id": _plain_identifier(payload["project_id"], "project_id", 200),
        "owner": _plain_identifier(payload["owner"], "owner", 200),
        "policy_commit": payload["policy_commit"],
        "fencing_token": payload["fencing_token"],
    }
    if (
        not isinstance(identity["policy_commit"], str)
        or OID_RE.fullmatch(identity["policy_commit"]) is None
    ):
        raise RequestError("policy_commit 必须是完整小写 Git commit OID")
    if type(identity["fencing_token"]) is not int or identity["fencing_token"] < 1:
        raise RequestError("fencing_token 必须是正整数")

    timeouts = dict(DEFAULT_TIMEOUTS)
    if "timeouts" in payload:
        section = payload["timeouts"]
        if not isinstance(section, dict) or not set(section).issubset(TIMEOUT_KEYS):
            raise RequestError(f"timeouts 必须是键不超过 {sorted(TIMEOUT_KEYS)} 的对象")
        for key, value in section.items():
            low, high = TIMEOUT_BOUNDS[key]
            if type(value) is not int or not low <= value <= high:
                raise RequestError(f"timeouts.{key} 必须是 {low}..{high} 的整数")
            timeouts[key] = value

    gates = {"quota_denied": False, "acceptance_backpressure": False}
    if "gates" in payload:
        section = payload["gates"]
        if not isinstance(section, dict) or not set(section).issubset(GATE_KEYS):
            raise RequestError(f"gates 必须是键不超过 {sorted(GATE_KEYS)} 的对象")
        for key, value in section.items():
            if type(value) is not bool:
                raise RequestError(f"gates.{key} 必须是布尔值")
            gates[key] = value

    return {
        "controller": _pinned_binding(payload["controller"], "controller"),
        "mutation_adapter": _pinned_binding(payload["mutation_adapter"], "mutation_adapter"),
        "identity": identity,
        "timeouts": timeouts,
        "gates": gates,
    }


def check_request_file(raw_path: str) -> dict[str, Any]:
    """结构校验入口：只解析与校验请求本身，不读取钉扎文件、不调用控制器。"""
    try:
        payload = load_request_file(raw_path)
    except RequestError as exc:
        return {"valid": False, "errors": [str(exc)]}
    try:
        request = validate_request(payload)
    except RequestError as exc:
        return {"valid": False, "errors": [str(exc)]}
    return {
        "valid": True,
        "errors": [],
        "request": {
            "contract": REQUEST_CONTRACT,
            "controller": request["controller"],
            "mutation_adapter": request["mutation_adapter"],
            "identity": request["identity"],
            "timeouts": request["timeouts"],
            "gates": request["gates"],
        },
    }


def verify_pinned_executable(binding: dict[str, str], label: str) -> None:
    path = Path(binding["path"])
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise PinnedError(f"{label} 不可用：{exc}") from exc
    if stat.S_ISLNK(mode):
        raise PinnedError(f"{label} 不允许是 symlink：{path}")
    if not stat.S_ISREG(mode):
        raise PinnedError(f"{label} 必须是常规文件：{path}")
    if not os.access(path, os.X_OK):
        raise PinnedError(f"{label} 必须可执行：{path}")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PinnedError(f"无法计算钉扎 {label} 摘要：{exc}") from exc
    actual = digest.hexdigest()
    if actual != binding["sha256"]:
        raise PinnedError(
            f"{label} 摘要漂移：钉扎 {binding['sha256']}，实际 {actual}"
        )


# ---------------------------------------------------------------------------
# 控制器子进程（argv 数组、shell=False、有界超时、stdin=/dev/null）
# ---------------------------------------------------------------------------


class StepResult:
    def __init__(
        self, step: str, argv: list[str], duration_ms: int, timed_out: bool,
        returncode: int | None, stdout: str, stderr: str,
    ) -> None:
        self.step = step
        self.argv = argv
        self.duration_ms = duration_ms
        self.timed_out = timed_out
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def summary(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "argv": self.argv,
            "exit_code": self.returncode,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
            "stdout_bytes": len(self.stdout.encode("utf-8")),
            "stdout_sha256": hashlib.sha256(self.stdout.encode("utf-8")).hexdigest(),
            "stderr_sha256": hashlib.sha256(self.stderr.encode("utf-8")).hexdigest(),
        }


def controller_error(step: StepResult) -> str:
    """从控制器 stderr 提取稳定的错误信息（控制器约定 stderr 为错误 JSON）。"""
    try:
        payload = json.loads(step.stderr)
    except (UnicodeDecodeError, json.JSONDecodeError):
        text = step.stderr.strip()
        return text[:300] if text else f"controller {step.step} exited {step.returncode}"
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        return payload["error"]
    return f"controller {step.step} exited {step.returncode}"


def run_controller_step(argv: list[str], step: str, timeout_seconds: int) -> StepResult:
    started = time.monotonic()
    timed_out = False
    returncode: int | None = None
    stdout = ""
    stderr = ""
    try:
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            shell=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        # 只杀死控制器子进程本身；若这是 tick，变更适配器可能在控制器侧已经
        # 启动——调用方必须按"结果不确定"处理，绝不重试。
        timed_out = True
    else:
        returncode = completed.returncode
        stdout = completed.stdout[:MAX_OUTPUT_BYTES]
        stderr = completed.stderr[:MAX_OUTPUT_BYTES]
    duration_ms = int((time.monotonic() - started) * 1000)
    return StepResult(step, argv, duration_ms, timed_out, returncode, stdout, stderr)


def parse_controller_stdout(step: StepResult) -> dict[str, Any] | None:
    if step.timed_out or step.returncode != 0:
        return None
    try:
        payload = json.loads(step.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


class Cycle:
    """单次有限循环：status → reconcile →（可选，至多一次）tick。

    状态推进只发生在 run() 一条直线路径上；tick 之后不再发起任何控制器
    调用（结构上保证"不确定变更后零重试、零追加调用"）。
    """

    def __init__(self, request: dict[str, Any]) -> None:
        self.request = request
        self.identity = request["identity"]
        self.steps: list[dict[str, Any]] = []
        self.started_at = utc_iso()
        self.decision = "wait"
        self.controller_action: str | None = None
        self.reason = ""
        self.future_heartbeat_needed = True
        self.fail_closed: dict[str, Any] = {"refused": False, "reason": None}
        self.tick: dict[str, Any] = {
            "invoked": False, "mutation_count": 0, "receipt_id": None, "uncertain": False,
        }
        self.ticked = False

    # -- 结果装配 -----------------------------------------------------------

    def refuse(self, decision: str, reason: str, *, future: bool | None = None) -> None:
        self.decision = decision
        self.reason = reason
        self.fail_closed = {"refused": True, "reason": reason}
        if future is not None:
            self.future_heartbeat_needed = future

    def observe_wait(self, reason: str) -> None:
        self.decision = "wait"
        self.reason = reason
        self.fail_closed = {"refused": True, "reason": reason}

    def finish(self) -> dict[str, Any]:
        return {
            "contract": CYCLE_CONTRACT,
            "schema_version": SCHEMA_VERSION,
            "cycle_id": "hb_" + secrets.token_hex(8),
            "started_at": self.started_at,
            "finished_at": utc_iso(),
            "identity": self.identity,
            "pinned": {
                "controller": self.request["controller"],
                "mutation_adapter": self.request["mutation_adapter"],
            },
            "decision": self.decision,
            "controller_action": self.controller_action,
            "reason": self.reason,
            "future_heartbeat_needed": self.future_heartbeat_needed,
            "fail_closed": self.fail_closed,
            "tick": self.tick,
            "steps": self.steps,
            "not_verified": [
                "真实 Orca/GitHub 副作用只由钉扎的 controller 及其适配器执行，本循环自身不做任何外部写入",
                "单次循环语义依赖外部 Codex App heartbeat 调度器按需再次唤醒",
            ],
        }

    # -- 控制器 argv 组装 ---------------------------------------------------

    def _base_argv(self) -> list[str]:
        return [sys.executable or "python3", self.request["controller"]["path"]]

    def _identity_flags(self) -> list[str]:
        return [
            "--repo", self.identity["repo"],
            "--project-id", self.identity["project_id"],
            "--policy-commit", self.identity["policy_commit"],
        ]

    def _owner_flags(self) -> list[str]:
        return [
            "--owner", self.identity["owner"],
            "--fencing-token", str(self.identity["fencing_token"]),
        ]

    def _run(self, step: str, argv: list[str], seconds: int) -> StepResult:
        result = run_controller_step(argv, step, seconds + SLACK_SECONDS)
        self.steps.append(result.summary())
        return result

    # -- 只读 status --------------------------------------------------------

    def observe(self, label: str, seconds: int) -> dict[str, Any] | None:
        """只读 status；返回载荷，失败时设置决策并返回 None。"""
        argv = self._base_argv() + ["status"] + self._identity_flags()
        step = self._run(f"status:{label}", argv, seconds)
        if step.timed_out:
            self.observe_wait("status 子进程超时；本循环拒绝推进，等待下次心跳")
            return None
        payload = parse_controller_stdout(step)
        if payload is None:
            if step.returncode != 0:
                if step.returncode == 66:
                    self.refuse(
                        "review",
                        f"Autopilot runtime 未初始化：{controller_error(step)}；"
                        "需要 PM 先 init，心跳可以停止",
                        future=False,
                    )
                else:
                    self.refuse(
                        "review",
                        f"status 失败（exit {step.returncode}）：{controller_error(step)}",
                    )
            else:
                self.refuse("review", "status 输出无法解析为 JSON 对象；fail-closed 拒绝推进")
            return None
        state = payload.get("state")
        if not isinstance(state, dict):
            self.refuse("review", "status 载荷缺少 state 对象；fail-closed 拒绝推进")
            return None
        if (
            state.get("project_id") != self.identity["project_id"]
            or state.get("policy_commit") != self.identity["policy_commit"]
        ):
            self.refuse("review", "status 的 project/policy 身份与请求不一致；拒绝推进")
            return None
        lease = payload.get("lease")
        if (
            not isinstance(lease, dict)
            or lease.get("owner") != self.identity["owner"]
            or lease.get("fencing_token") != self.identity["fencing_token"]
        ):
            self.refuse(
                "review",
                "PM 租约缺失或与请求的 owner/fencing_token 不一致；需要 PM 重新建立租约，心跳可以停止",
                future=False,
            )
            return None
        return payload

    # -- reconcile ----------------------------------------------------------

    def plan(self, seconds: int) -> dict[str, Any] | None:
        argv = (
            self._base_argv()
            + ["reconcile"]
            + self._identity_flags()
            + self._owner_flags()
            + ["--timeout-seconds", str(seconds)]
        )
        step = self._run("reconcile", argv, seconds)
        if step.timed_out:
            self.observe_wait("reconcile 子进程超时（事实收集未完成）；拒绝 tick，等待下次心跳")
            return None
        payload = parse_controller_stdout(step)
        if payload is None:
            if step.returncode != 0:
                self.observe_wait(
                    f"reconcile 失败（exit {step.returncode}）：{controller_error(step)}；"
                    "事实未知或过期，拒绝 tick，等待下次心跳"
                )
            else:
                self.refuse("review", "reconcile 输出无法解析为 JSON 对象；fail-closed 拒绝 tick")
            return None
        return payload

    # -- reconcile 结果分类（内部动作 → wait/park/complete/review） ----------

    def classify_internal(self, action: dict[str, Any]) -> None:
        name = action.get("action")
        self.controller_action = name
        if name == "complete":
            self.decision = "complete"
            self.reason = "全部条目已完成/释放；心跳可以停止"
            self.future_heartbeat_needed = False
        elif name in {"observe", "adopt"}:
            self.decision = "wait"
            self.reason = f"控制器内部动作 {name}；无需变更，等待下次心跳巡检"
        elif name == "retry_later":
            self.decision = "wait"
            self.reason = "provider 等待重置（配额受限）；控制器规划 retry_later，拒绝任何 tick"
        elif name == "hard_park":
            self.decision = "park"
            self.reason = f"控制器硬泊车：{action.get('reason', '')}；需要人工介入，心跳可以停止"
            self.future_heartbeat_needed = False
        elif name == "reject_duplicate":
            self.decision = "review"
            self.reason = f"控制器拒绝重复目标：{action.get('reason', '')}；需要人工复核，心跳可以停止"
            self.future_heartbeat_needed = False
        else:
            self.refuse("review", f"控制器返回未知内部动作 {name!r}；拒绝 tick")

    # -- tick 前闸门（全部通过才允许唯一的 tick） ----------------------------

    def pre_tick_gate(
        self, action_name: str, reconcile_result: dict[str, Any], payload: dict[str, Any],
    ) -> bool:
        state = payload.get("state") or {}
        if (
            state.get("pm_owner") != self.identity["owner"]
            or state.get("fencing_token") != self.identity["fencing_token"]
        ):
            self.refuse("review", "pre-tick status 显示租约身份已变化；拒绝 tick")
            return False
        pending = reconcile_result.get("pending_intent")
        if (
            not isinstance(pending, dict)
            or pending.get("fencing_token") != self.identity["fencing_token"]
        ):
            self.refuse("wait", "reconcile 待定意图的 fencing_token 与请求不一致；拒绝 tick")
            return False
        fresh_pending = state.get("pending_intent")
        if (
            not isinstance(fresh_pending, dict)
            or fresh_pending.get("status") != "planned"
            or fresh_pending.get("ready") is not True
            or fresh_pending.get("fencing_token") != self.identity["fencing_token"]
        ):
            self.refuse(
                "wait",
                "pre-tick status 显示待定意图不是 ready/planned 或已被推进；拒绝 tick",
            )
            return False
        gates = self.request["gates"]
        if gates["quota_denied"]:
            self.refuse(
                "wait", "请求声明配额被拒（gates.quota_denied=true）；fail-closed 拒绝 tick"
            )
            return False
        if action_name == "spawn":
            items = state.get("items") if isinstance(state.get("items"), list) else []
            open_prs = sum(
                1
                for item in items
                if isinstance(item, dict)
                and item.get("pr_state") == "open"
                and item.get("status") != "COMPLETE"
                and item.get("released") is not True
            )
            if open_prs > BACKPRESSURE_THRESHOLD:
                self.refuse(
                    "wait",
                    f"验收反压：待验收 open PR 数 {open_prs} 超过阈值 "
                    f"{BACKPRESSURE_THRESHOLD}；拒绝 spawn tick",
                )
                return False
            if gates["acceptance_backpressure"]:
                self.refuse(
                    "wait",
                    "请求声明验收反压（gates.acceptance_backpressure=true）；拒绝 spawn tick",
                )
                return False
        return True

    # -- 唯一一次 tick -------------------------------------------------------

    def execute_tick(
        self, seconds: int, reconcile_result: dict[str, Any], payload: dict[str, Any],
    ) -> None:
        if self.ticked:  # 结构性保险：单次循环至多一次 tick
            self.refuse("review", "内部错误：tick 已在本次循环执行过")
            return
        self.ticked = True
        if not self.pre_tick_gate(str(self.controller_action), reconcile_result, payload):
            return
        argv = (
            self._base_argv()
            + ["tick"]
            + self._identity_flags()
            + self._owner_flags()
            + [
                "--adapter", self.request["mutation_adapter"]["path"],
                "--timeout-seconds", str(seconds),
            ]
        )
        step = self._run("tick", argv, seconds)
        self.tick["invoked"] = True

        def uncertain(reason: str) -> None:
            self.tick["uncertain"] = True
            self.decision = "review"
            self.reason = reason
            self.fail_closed = {"refused": True, "reason": reason}

        if step.timed_out:
            uncertain(
                "tick 子进程超时：变更适配器可能已在控制器侧启动，结果不确定；"
                "按协议绝不重试，等待下次心跳以 reconcile 收敛"
            )
            return
        result = parse_controller_stdout(step)
        if result is None:
            if step.returncode != 0:
                uncertain(
                    f"tick 非零退出（exit {step.returncode}）：{controller_error(step)}；"
                    "变更结果不确定，绝不重试，等待下次心跳 reconcile"
                )
            else:
                uncertain(
                    "tick 退出码为 0 但输出无法解析；控制器状态是唯一权威，"
                    "本循环按不确定处理且绝不重试"
                )
            return
        disposition = result.get("disposition")
        mutation_count = result.get("mutation_count")
        if mutation_count == 1 and disposition == "receipt_recorded_await_external_fact":
            self.decision = "dispatch"
            self.tick["mutation_count"] = 1
            self.tick["receipt_id"] = result.get("receipt_id")
            self.reason = (
                f"变更已由控制器执行一次并记录 receipt {result.get('receipt_id')}；"
                "等待外部事实收敛"
            )
            return
        if mutation_count == 0 and disposition in {"no_pending_intent", "await_external_fact"}:
            self.decision = "wait"
            self.tick["mutation_count"] = 0
            self.reason = f"tick 无新变更（disposition {disposition!r}）；等待下次心跳"
            return
        uncertain(
            f"tick 返回未知结果（disposition {disposition!r}, "
            f"mutation_count {mutation_count!r}）；fail-closed，绝不重试"
        )

    # -- 主路径 --------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        timeouts = self.request["timeouts"]

        first = self.observe("pre-status", timeouts["status_seconds"])
        if first is None:
            return self.finish()
        if first.get("state", {}).get("state") == "COMPLETE":
            self.decision = "complete"
            self.controller_action = "complete"
            self.reason = "控制器状态已是 COMPLETE；无需 reconcile，心跳可以停止"
            self.future_heartbeat_needed = False
            return self.finish()

        second = self.plan(timeouts["reconcile_seconds"])
        if second is None:
            return self.finish()

        action = second.get("planned_action")
        if not isinstance(action, dict):
            self.refuse("review", "reconcile 载荷缺少 planned_action；fail-closed 拒绝 tick")
            return self.finish()
        disposition = second.get("disposition")
        self.controller_action = action.get("action")

        if disposition == "ready":
            if (
                action.get("external_mutation") is not True
                or self.controller_action not in ALLOWED_TICK_ACTIONS
            ):
                self.refuse(
                    "review",
                    f"控制器计划了 allowlist 之外的动作 {self.controller_action!r}；拒绝 tick",
                )
                return self.finish()
            third = self.observe("pre-tick-status", timeouts["status_seconds"])
            if third is None:
                return self.finish()
            self.execute_tick(timeouts["tick_seconds"], second, third)
            return self.finish()

        if disposition == "internal_only":
            self.classify_internal(action)
            return self.finish()
        if disposition in {"await_external_fact", "await_revalidation"}:
            pending = second.get("pending_intent")
            pending_status = pending.get("status") if isinstance(pending, dict) else None
            self.decision = "wait"
            self.reason = (
                f"待定变更 {self.controller_action!r} 状态 {pending_status!r}："
                "等待外部事实收敛，本循环不执行任何变更"
            )
            return self.finish()

        self.refuse(
            "review", f"reconcile 返回未知 disposition {disposition!r}；拒绝 tick"
        )
        return self.finish()


# ---------------------------------------------------------------------------
# CLI 边界
# ---------------------------------------------------------------------------


def run_cycle(argv: str) -> int:
    try:
        payload = load_request_file(argv)
        request = validate_request(payload)
        verify_pinned_executable(request["controller"], "controller")
        verify_pinned_executable(request["mutation_adapter"], "mutation adapter")
    except RequestError as exc:
        return fail(str(exc), exc.code)
    emit(Cycle(request).run())
    return 0


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"ERROR: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def build_parser() -> Parser:
    parser = Parser(
        description="Codex App 心跳的有界循环适配器（一次调用 = 一次有限循环）",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--request", help="执行一次有限循环的请求 JSON（常规文件）")
    mode.add_argument(
        "--check-request",
        help="仅对请求 JSON 做结构校验，不读取钉扎文件、不调用控制器",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.check_request:
            result = check_request_file(args.check_request)
            emit(result)
            return 0 if result["valid"] else EXIT_DATA
        assert args.request
        return run_cycle(args.request)
    except RequestError as exc:  # 防御：正常路径已在 run_cycle 内转换
        return fail(str(exc), exc.code)
    except KeyboardInterrupt:
        return fail("interrupted", 75)
    except Exception as exc:  # 稳定 CLI 边界：不外泄内部数据
        return fail(f"internal heartbeat cycle error: {type(exc).__name__}", EXIT_SOFTWARE)


if __name__ == "__main__":
    raise SystemExit(main())
