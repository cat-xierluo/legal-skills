#!/usr/bin/env python3
"""codex-heartbeat-cycle 的离线自测：假控制器 + 确定性 fixtures。

全部用例通过一个可执行的假 controller（argv 记录 + 按调用序号回放脚本化
输出）驱动真实的 codex-heartbeat-cycle.py CLI，证明：

  - argv 安全：身份字段（含 shell 元字符的敌意字符串）作为单个 argv 元素
    传递，绝不经过 shell 解释；
  - 每次调用至多一次 tick；每个拒绝场景（配额拒绝 / 验收反压 / 未知或
    过期事实 / 缺租约或身份 / allowlist 之外动作 / 待定意图不 ready）
    tick 次数为 0；有效动作恰好一次 tick；
  - 超时与畸形输出 fail-closed；
  - 不确定的 tick 绝不重试（tick 调用后不再有任何控制器调用）；
  - example 模板通过结构校验并能驱动一次真实形状的完整循环。

不做任何真实 Orca / GitHub 变更：控制器与变更适配器都是临时目录里的假
可执行文件，repo 路径不需要存在。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any


REQUEST_CONTRACT = "multi-agent-orchestration.codex-heartbeat-cycle-request.v1"
CYCLE_CONTRACT = "multi-agent-orchestration.codex-heartbeat-cycle.v1"
SELFTEST_CONTRACT = "multi-agent-orchestration.codex-heartbeat-cycle-selftest.v1"

SCRIPTS_DIR = Path(__file__).resolve().parent
CYCLE_CLI = SCRIPTS_DIR / "codex-heartbeat-cycle.py"
EXAMPLE_TEMPLATE = SCRIPTS_DIR.parent / "templates" / "codex-heartbeat-cycle.example.json"

PROJECT = "project-selftest"
POLICY = "a" * 40
OWNER = "pm-codex-hb"
TOKEN = 7

FAKE_CONTROLLER = """#!/usr/bin/env python3
import json, os, sys, time
log_path = os.environ["HB_CONTROLLER_LOG"]
calls = []
if os.path.exists(log_path):
    with open(log_path, encoding="utf-8") as fh:
        calls = json.load(fh)
calls.append(sys.argv[1:])
with open(log_path, "w", encoding="utf-8") as fh:
    json.dump(calls, fh)
with open(os.environ["HB_CONTROLLER_CONFIG"], encoding="utf-8") as fh:
    script = json.load(fh)
index = len(calls) - 1
responses = script.get("responses", [])
plan = responses[index] if index < len(responses) else script.get("default")
if plan is None:
    plan = {"exit": 70, "stdout": "",
            "stderr": json.dumps({"error": "unexpected controller call", "exit_code": 70})}
time.sleep(plan.get("delay", 0))
sys.stdout.write(plan.get("stdout", ""))
sys.stderr.write(plan.get("stderr", ""))
sys.exit(plan.get("exit", 0))
"""

FAKE_MUTATION_ADAPTER = """#!/usr/bin/env python3
# 假变更适配器：心跳循环只钉扎它，从不直接执行它；真正的执行者是控制器。
import json, sys
request = json.load(sys.stdin)
print(json.dumps({
    "schema_version": 1,
    "contract": "multi-agent-orchestration.autopilot-adapter-receipt.v1",
    "request_id": request["request_id"],
    "idempotency_key": request["intent"]["idempotency_key"],
    "target_digest": request["intent"]["target_digest"],
    "fencing_token": request["fencing_token"],
    "accepted": True,
    "receipt_id": "receipt-fixture",
}))
"""


def digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def controller_stdout(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def controller_error_payload(message: str, code: int) -> str:
    return json.dumps({"error": message, "exit_code": code}, ensure_ascii=False)


class Fixture:
    """一次自测场景：假控制器 + 假适配器 + 请求构造 + CLI 执行。"""

    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="codex-heartbeat-cycle-selftest-")
        self.root = Path(self.temp.name)
        self.controller = self.root / "fake-controller.py"
        self.controller.write_text(FAKE_CONTROLLER, encoding="utf-8")
        self.controller.chmod(0o755)
        self.adapter = self.root / "fake-mutation-adapter.py"
        self.adapter.write_text(FAKE_MUTATION_ADAPTER, encoding="utf-8")
        self.adapter.chmod(0o755)
        self.config_path = self.root / "controller-script.json"
        self.log_path = self.root / "controller-calls.json"
        self.request_path = self.root / "request.json"
        self.repo = self.root / "repo"

    def close(self) -> None:
        self.temp.cleanup()

    # -- 脚本与请求 ---------------------------------------------------------

    def script(self, responses: list[dict[str, Any]], default: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"responses": responses}
        if default is not None:
            payload["default"] = default
        self.config_path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def base_request(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "contract": REQUEST_CONTRACT,
            "controller": {"path": str(self.controller), "sha256": digest(self.controller)},
            "mutation_adapter": {"path": str(self.adapter), "sha256": digest(self.adapter)},
            "repo": str(self.repo),
            "project_id": PROJECT,
            "policy_commit": POLICY,
            "owner": OWNER,
            "fencing_token": TOKEN,
            "timeouts": {"status_seconds": 10, "reconcile_seconds": 10, "tick_seconds": 10},
        }

    def write_request(self, request: dict[str, Any]) -> Path:
        self.request_path.write_text(
            json.dumps(request, ensure_ascii=False), encoding="utf-8"
        )
        return self.request_path

    def run(self, request: dict[str, Any]) -> subprocess.CompletedProcess[str]:
        self.script_config_not_needed_guard()
        os.environ["HB_CONTROLLER_LOG"] = str(self.log_path)
        os.environ["HB_CONTROLLER_CONFIG"] = str(self.config_path)
        path = self.write_request(request)
        return subprocess.run(
            [sys.executable, str(CYCLE_CLI), "--request", str(path)],
            capture_output=True, text=True, timeout=180, check=False,
        )

    def script_config_not_needed_guard(self) -> None:
        if not self.config_path.exists():
            self.script([])

    # -- 观测 ---------------------------------------------------------------

    @property
    def calls(self) -> list[list[str]]:
        if not self.log_path.exists():
            return []
        return json.loads(self.log_path.read_text(encoding="utf-8"))

    def tick_calls(self) -> list[list[str]]:
        return [call for call in self.calls if call and call[0] == "tick"]

    def result(self, proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"cycle stdout 不是 JSON：{exc}; stdout={proc.stdout!r} stderr={proc.stderr!r}"
            )
        assert isinstance(payload, dict), f"cycle stdout 根不是对象：{payload!r}"
        return payload

    # -- 控制器输出 fixtures ------------------------------------------------

    def status_ok(
        self, *, complete: bool = False, items: list[dict[str, Any]] | None = None,
        owner: str = OWNER, token: int = TOKEN, project: str = PROJECT,
        policy: str = POLICY, pending: Any = "auto",
    ) -> str:
        if pending == "auto":
            pending = None if complete else {
                "status": "planned", "ready": True, "fencing_token": token,
            }
        return controller_stdout({
            "state": {
                "state": "COMPLETE" if complete else "RUNNING",
                "project_id": project,
                "policy_commit": policy,
                "pm_owner": owner,
                "fencing_token": token,
                "pending_intent": pending,
                "items": items if items is not None else [
                    {"task_id": "T1", "status": "RUNNING", "pr_state": None, "released": None},
                ],
            },
            "lease": {"owner": owner, "fencing_token": token},
            "runtime_root": str(self.root / "runtime"),
            "read_only": True,
            "recovery_needed": False,
        })

    def reconcile_ready(
        self, action: str = "spawn", *, external: bool = True, token: int = TOKEN,
    ) -> str:
        return controller_stdout({
            "planned_action": {
                "task_id": "T1", "action": action, "reason": "exact next action",
                "external_mutation": external,
                "target": {"task_id": "T1", "attempt": 1},
            },
            "pending_intent": {
                "status": "planned", "ready": True, "fencing_token": token,
                "action": action,
            },
            "disposition": "ready",
            "recovered": False,
        })

    def reconcile_internal(self, action: str, reason: str = "fixture", target: Any = None, failure_class: Any = None) -> str:
        planned: dict[str, Any] = {
            "task_id": "T1", "action": action, "reason": reason,
            "external_mutation": False, "target": {} if target is None else target,
        }
        if failure_class is not None:
            planned["failure_class"] = failure_class
        return controller_stdout({
            "planned_action": planned,
            "pending_intent": None,
            "disposition": "internal_only",
            "recovered": False,
        })

    def reconcile_repair(self, *, step: str = "repair", used: int = 0, total: int = 2) -> str:
        return self.reconcile_internal(
            "repair_acceptance",
            f"acceptance checks failed: internal_recoverable ({step}, repair episode {used + 1}/{total})",
            target={"task_id": "T1", "repair_step": step, "repair_attempts_used": used, "max_repair_attempts": total},
        )

    def reconcile_await(self, disposition: str = "await_external_fact") -> str:
        return controller_stdout({
            "planned_action": {
                "task_id": "T1", "action": "observe",
                "reason": "pending mutation awaits exact after-fact convergence",
                "external_mutation": False, "target": {},
            },
            "pending_intent": {
                "status": "receipt_recorded", "ready": False, "fencing_token": TOKEN,
                "action": "spawn",
            },
            "disposition": disposition,
            "recovered": False,
        })

    def tick_receipt(self, *, mutation_count: int = 1) -> str:
        return controller_stdout({
            "disposition": (
                "receipt_recorded_await_external_fact"
                if mutation_count == 1 else "no_pending_intent"
            ),
            "mutation_count": mutation_count,
            "receipt_id": "receipt-fixture-1" if mutation_count == 1 else None,
            "recovered": False,
        })


def green_script(
    fixture: Fixture, *, project: str = PROJECT, owner: str = OWNER,
    token: int = TOKEN, policy: str = POLICY,
) -> list[dict[str, Any]]:
    """status → reconcile(ready spawn) → pre-tick status → tick(receipt)。"""
    return [
        {
            "exit": 0,
            "stdout": fixture.status_ok(project=project, owner=owner, token=token, policy=policy),
        },
        {"exit": 0, "stdout": fixture.reconcile_ready("spawn", token=token)},
        {
            "exit": 0,
            "stdout": fixture.status_ok(project=project, owner=owner, token=token, policy=policy),
        },
        {"exit": 0, "stdout": fixture.tick_receipt()},
    ]


def open_pr_items(count: int) -> list[dict[str, Any]]:
    return [
        {"task_id": f"T{index}", "status": "RUNNING", "pr_state": "open", "released": None}
        for index in range(1, count + 1)
    ]


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------


def case_valid_spawn_executes_exactly_one_tick_with_pinned_argv() -> dict[str, Any]:
    f = Fixture()
    try:
        f.script(green_script(f))
        request = f.base_request()
        proc = f.run(request)
        assert proc.returncode == 0, f"exit={proc.returncode} stderr={proc.stderr}"
        result = f.result(proc)
        assert result["contract"] == CYCLE_CONTRACT
        assert result["decision"] == "dispatch", result["reason"]
        assert result["controller_action"] == "spawn"
        assert result["tick"]["invoked"] is True
        assert result["tick"]["mutation_count"] == 1
        assert result["tick"]["receipt_id"] == "receipt-fixture-1"
        assert result["tick"]["uncertain"] is False
        assert result["future_heartbeat_needed"] is True
        assert result["fail_closed"]["refused"] is False
        assert len(result["steps"]) == 4
        assert len(f.tick_calls()) == 1

        identity_flags = [
            "--repo", str(f.repo),
            "--project-id", PROJECT,
            "--policy-commit", POLICY,
        ]
        owner_flags = ["--owner", OWNER, "--fencing-token", str(TOKEN)]
        assert f.calls[0] == ["status"] + identity_flags
        assert f.calls[1] == (
            ["reconcile"] + identity_flags + owner_flags + ["--timeout-seconds", "10"]
        )
        assert f.calls[2] == ["status"] + identity_flags
        assert f.calls[3] == (
            ["tick"] + identity_flags + owner_flags
            + ["--adapter", str(f.adapter), "--timeout-seconds", "10"]
        )
        # steps 里的 argv 也必须记录完整调用（含解释器与控制器路径）
        assert result["steps"][3]["argv"][2] == "tick"
        assert result["steps"][3]["argv"][0] == sys.executable
        assert result["steps"][3]["timed_out"] is False
        return {"tick_calls": len(f.tick_calls()), "decision": result["decision"]}
    finally:
        f.close()


def case_hostile_identity_travels_as_single_argv_element() -> dict[str, Any]:
    f = Fixture()
    try:
        hostile_project = 'p"; touch hb-pwned-marker; rm -rf #'
        hostile_owner = "pm$(reboot)`echo hi`|nc evil"
        f.script([
            {"exit": 0, "stdout": f.status_ok(project=hostile_project, owner=hostile_owner)},
            {"exit": 0, "stdout": f.reconcile_ready("spawn")},
            {"exit": 0, "stdout": f.status_ok(project=hostile_project, owner=hostile_owner)},
            {"exit": 0, "stdout": f.tick_receipt()},
        ])
        request = f.base_request()
        request["project_id"] = hostile_project
        request["owner"] = hostile_owner
        proc = f.run(request)
        assert proc.returncode == 0, proc.stderr
        result = f.result(proc)
        assert result["decision"] == "dispatch", result["reason"]
        assert len(f.calls) == 4
        for call in f.calls:
            assert "--project-id" in call
            project_value = call[call.index("--project-id") + 1]
            assert project_value == hostile_project, f"project 被拆分或改写：{project_value!r}"
            if call[0] in {"reconcile", "tick"}:  # status 不携带 owner 旗标
                owner_value = call[call.index("--owner") + 1]
                assert owner_value == hostile_owner, f"owner 被拆分或改写：{owner_value!r}"
        assert not (f.root / "hb-pwned-marker").exists(), "敌意字符串被 shell 解释执行了"
        return {"argv_elements": len(f.calls[0]), "shell_interpreted": False}
    finally:
        f.close()


def case_second_heartbeat_after_receipt_ticks_nothing() -> dict[str, Any]:
    f = Fixture()
    try:
        f.script([
            {"exit": 0, "stdout": f.status_ok(pending={
                "status": "receipt_recorded", "ready": False, "fencing_token": TOKEN,
            })},
            {"exit": 0, "stdout": f.reconcile_await("await_external_fact")},
        ])
        proc = f.run(f.base_request())
        assert proc.returncode == 0, proc.stderr
        result = f.result(proc)
        assert result["decision"] == "wait", result["reason"]
        assert len(f.tick_calls()) == 0
        assert len(f.calls) == 2
        return {"calls": len(f.calls), "ticks": 0}
    finally:
        f.close()


def case_mechanical_backpressure_blocks_spawn() -> dict[str, Any]:
    f = Fixture()
    try:
        items = open_pr_items(3)
        f.script([
            {"exit": 0, "stdout": f.status_ok(items=items)},
            {"exit": 0, "stdout": f.reconcile_ready("spawn")},
            {"exit": 0, "stdout": f.status_ok(items=items)},
        ])
        proc = f.run(f.base_request())
        assert proc.returncode == 0, proc.stderr
        result = f.result(proc)
        assert result["decision"] == "wait", result["reason"]
        assert "反压" in result["reason"], result["reason"]
        assert len(f.tick_calls()) == 0
        assert len(f.calls) == 3
        return {"open_prs": 3, "ticks": 0}
    finally:
        f.close()


def case_two_open_prs_allow_spawn() -> dict[str, Any]:
    f = Fixture()
    try:
        items = open_pr_items(2)
        f.script([
            {"exit": 0, "stdout": f.status_ok(items=items)},
            {"exit": 0, "stdout": f.reconcile_ready("spawn")},
            {"exit": 0, "stdout": f.status_ok(items=items)},
            {"exit": 0, "stdout": f.tick_receipt()},
        ])
        proc = f.run(f.base_request())
        assert proc.returncode == 0, proc.stderr
        result = f.result(proc)
        assert result["decision"] == "dispatch", result["reason"]
        assert len(f.tick_calls()) == 1
        return {"open_prs": 2, "ticks": 1}
    finally:
        f.close()


def case_pre_tick_pending_not_ready_refuses() -> dict[str, Any]:
    f = Fixture()
    try:
        f.script([
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_ready("spawn")},
            {"exit": 0, "stdout": f.status_ok(pending={
                "status": "started", "ready": False, "fencing_token": TOKEN,
            })},
        ])
        proc = f.run(f.base_request())
        assert proc.returncode == 0, proc.stderr
        result = f.result(proc)
        assert result["decision"] == "wait", result["reason"]
        assert "待定意图" in result["reason"], result["reason"]
        assert len(f.tick_calls()) == 0
        assert len(f.calls) == 3
        return {"ticks": 0}
    finally:
        f.close()


def case_status_timeout_is_bounded_and_ticks_nothing() -> dict[str, Any]:
    f = Fixture()
    try:
        f.script([{"exit": 0, "stdout": f.status_ok(), "delay": 60}])
        request = f.base_request()
        request["timeouts"] = {"status_seconds": 1, "reconcile_seconds": 10, "tick_seconds": 10}
        started = time.monotonic()
        proc = f.run(request)
        elapsed = time.monotonic() - started
        assert proc.returncode == 0, proc.stderr
        result = f.result(proc)
        assert result["decision"] == "wait", result["reason"]
        assert "超时" in result["reason"]
        assert result["steps"][0]["timed_out"] is True
        assert elapsed < 30, f"status 超时未及时中断：{elapsed:.1f}s"
        assert len(f.calls) == 1
        assert len(f.tick_calls()) == 0
        return {"elapsed_seconds": round(elapsed, 1), "ticks": 0}
    finally:
        f.close()


def case_tick_timeout_marks_uncertain_without_retry() -> dict[str, Any]:
    f = Fixture()
    try:
        f.script([
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_ready("spawn")},
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.tick_receipt(), "delay": 60},
        ])
        request = f.base_request()
        request["timeouts"] = {"status_seconds": 10, "reconcile_seconds": 10, "tick_seconds": 1}
        started = time.monotonic()
        proc = f.run(request)
        elapsed = time.monotonic() - started
        assert proc.returncode == 0, proc.stderr
        result = f.result(proc)
        assert result["decision"] == "review", result["reason"]
        assert result["tick"]["uncertain"] is True
        assert "不确定" in result["reason"]
        assert elapsed < 30, f"tick 超时未及时中断：{elapsed:.1f}s"
        # tick 之后不得有任何追加控制器调用（无重试）
        assert len(f.calls) == 4
        assert len(f.tick_calls()) == 1
        assert f.calls[-1][0] == "tick"
        return {"ticks": 1, "calls_after_tick": 0}
    finally:
        f.close()


def case_tick_nonzero_exit_is_uncertain_and_never_retried() -> dict[str, Any]:
    f = Fixture()
    try:
        f.script([
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_ready("spawn")},
            {"exit": 0, "stdout": f.status_ok()},
            {
                "exit": 75,
                "stdout": "",
                "stderr": controller_error_payload(
                    "mutation adapter returned 3; outcome unknown", 75
                ),
            },
        ])
        proc = f.run(f.base_request())
        assert proc.returncode == 0, proc.stderr
        result = f.result(proc)
        assert result["decision"] == "review", result["reason"]
        assert result["tick"]["uncertain"] is True
        assert "outcome unknown" in result["reason"]
        assert len(f.calls) == 4, "不确定 tick 后不得再有控制器调用"
        assert len(f.tick_calls()) == 1
        return {"ticks": 1, "calls_after_tick": 0}
    finally:
        f.close()


def case_tick_malformed_zero_exit_output_is_uncertain() -> dict[str, Any]:
    f = Fixture()
    try:
        f.script([
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_ready("spawn")},
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": "not-json{{{"},
        ])
        proc = f.run(f.base_request())
        assert proc.returncode == 0, proc.stderr
        result = f.result(proc)
        assert result["decision"] == "review", result["reason"]
        assert result["tick"]["uncertain"] is True
        assert len(f.calls) == 4
        return {"ticks": 1, "calls_after_tick": 0}
    finally:
        f.close()


def case_status_malformed_output_is_fail_closed() -> dict[str, Any]:
    f = Fixture()
    try:
        f.script([{"exit": 0, "stdout": "garbage-not-json"}])
        proc = f.run(f.base_request())
        assert proc.returncode == 0, proc.stderr
        result = f.result(proc)
        assert result["decision"] == "review", result["reason"]
        assert "无法解析" in result["reason"]
        assert len(f.calls) == 1, "status 畸形输出后不得继续 reconcile/tick"
        return {"calls": 1, "ticks": 0}
    finally:
        f.close()


def case_complete_state_stops_without_reconcile() -> dict[str, Any]:
    f = Fixture()
    try:
        f.script([{"exit": 0, "stdout": f.status_ok(complete=True)}])
        proc = f.run(f.base_request())
        assert proc.returncode == 0, proc.stderr
        result = f.result(proc)
        assert result["decision"] == "complete"
        assert result["future_heartbeat_needed"] is False
        assert len(f.calls) == 1, "COMPLETE 时不得再 reconcile"
        assert len(f.tick_calls()) == 0
        return {"calls": 1, "decision": "complete"}
    finally:
        f.close()


def case_reconcile_missing_planned_action_refuses() -> dict[str, Any]:
    f = Fixture()
    try:
        f.script([
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": controller_stdout({"disposition": "ready"})},
        ])
        proc = f.run(f.base_request())
        assert proc.returncode == 0, proc.stderr
        result = f.result(proc)
        assert result["decision"] == "review"
        assert len(f.tick_calls()) == 0
        return {"ticks": 0}
    finally:
        f.close()


# ---------------------------------------------------------------------------
# 请求硬校验 / check-request 模式 / example 模板
# ---------------------------------------------------------------------------


def run_cli_raw(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CYCLE_CLI), *args],
        capture_output=True, text=True, timeout=60, check=False,
    )


def case_request_validation_fail_closed() -> dict[str, Any]:
    f = Fixture()
    try:
        good = f.base_request()
        os.environ["HB_CONTROLLER_LOG"] = str(f.log_path)
        os.environ["HB_CONTROLLER_CONFIG"] = str(f.config_path)
        f.script([])

        def expect_exit(request: dict[str, Any] | None, code: int) -> None:
            if request is not None:
                f.write_request(request)
            proc = run_cli_raw(["--request", str(f.request_path)])
            assert proc.returncode == code, (
                f"期望 exit {code}，得到 {proc.returncode}: stdout={proc.stdout!r}"
            )
            assert proc.stderr.strip(), "非零退出必须有 stderr 错误 JSON"

        # 请求文件缺失
        proc = run_cli_raw(["--request", str(f.root / "absent-request.json")])
        assert proc.returncode == 65, proc.returncode

        bad_cases: list[tuple[str, dict[str, Any], int]] = []
        for field in ("contract", "controller", "mutation_adapter", "repo", "project_id", "policy_commit", "owner", "fencing_token"):
            broken = dict(good)
            broken.pop(field)
            bad_cases.append((f"missing {field}", broken, 65))
        unknown = dict(good)
        unknown["surprise"] = True
        bad_cases.append(("unknown field", unknown, 65))
        bool_token = dict(good)
        bool_token["fencing_token"] = True
        bad_cases.append(("bool fencing_token", bool_token, 65))
        zero_token = dict(good)
        zero_token["fencing_token"] = 0
        bad_cases.append(("zero fencing_token", zero_token, 65))
        dash_project = dict(good)
        dash_project["project_id"] = "-p; rm -rf x"
        bad_cases.append(("project_id leading dash", dash_project, 65))
        newline_owner = dict(good)
        newline_owner["owner"] = "pm\ninjected"
        bad_cases.append(("owner control char", newline_owner, 65))
        short_policy = dict(good)
        short_policy["policy_commit"] = "abc123"
        bad_cases.append(("short policy_commit", short_policy, 65))
        relative_repo = dict(good)
        relative_repo["repo"] = "relative/path"
        bad_cases.append(("relative repo", relative_repo, 65))
        bad_timeouts = dict(good)
        bad_timeouts["timeouts"] = {"status_seconds": 0}
        bad_cases.append(("timeout below bounds", bad_timeouts, 65))
        bad_timeouts2 = dict(good)
        bad_timeouts2["timeouts"] = {"tick_seconds": 601}
        bad_cases.append(("timeout above bounds", bad_timeouts2, 65))
        bad_gates = dict(good)
        bad_gates["gates"] = {"quota_denied": "yes"}
        bad_cases.append(("non-bool gate", bad_gates, 65))
        unknown_gate = dict(good)
        unknown_gate["gates"] = {"mystery": True}
        bad_cases.append(("unknown gate", unknown_gate, 65))
        drift_controller = dict(good)
        drift_controller["controller"] = {
            "path": str(f.controller), "sha256": "0" * 64,
        }
        bad_cases.append(("controller digest drift", drift_controller, 78))
        drift_adapter = dict(good)
        drift_adapter["mutation_adapter"] = {
            "path": str(f.adapter), "sha256": "0" * 64,
        }
        bad_cases.append(("adapter digest drift", drift_adapter, 78))
        absent_controller = dict(good)
        absent_controller["controller"] = {
            "path": str(f.root / "nope.py"), "sha256": "0" * 64,
        }
        bad_cases.append(("controller file absent", absent_controller, 78))

        noexec = f.root / "noexec-controller.py"
        noexec.write_text(FAKE_CONTROLLER, encoding="utf-8")
        noexec_controller = dict(good)
        noexec_controller["controller"] = {"path": str(noexec), "sha256": digest(noexec)}
        bad_cases.append(("controller not executable", noexec_controller, 78))

        for label, request, expected_code in bad_cases:
            before = len(f.calls)
            expect_exit(request, expected_code)
            assert len(f.calls) == before, f"{label}：非法请求不得调用控制器"

        # symlink / 非常规文件
        f.write_request(good)
        link = f.root / "link-request.json"
        os.symlink(f.request_path, link)
        proc = run_cli_raw(["--request", str(link)])
        assert proc.returncode == 65, proc.returncode
        proc = run_cli_raw(["--request", str(f.root)])
        assert proc.returncode == 65, proc.returncode

        # 用法错误：缺少模式 / 双模式
        parser_proc = run_cli_raw([])
        assert parser_proc.returncode == 64
        both = f.write_request(good)
        parser_proc = run_cli_raw([
            "--request", str(both), "--check-request", str(both),
        ])
        assert parser_proc.returncode == 64
        return {"bad_requests_rejected": len(bad_cases) + 3}
    finally:
        f.close()


def case_check_request_mode() -> dict[str, Any]:
    f = Fixture()
    try:
        os.environ["HB_CONTROLLER_LOG"] = str(f.log_path)
        os.environ["HB_CONTROLLER_CONFIG"] = str(f.config_path)
        valid = f.base_request()
        path = f.write_request(valid)
        proc = run_cli_raw(["--check-request", str(path)])
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["valid"] is True and payload["errors"] == []
        assert payload["request"]["identity"]["project_id"] == PROJECT
        assert payload["request"]["timeouts"]["tick_seconds"] == 10
        assert payload["request"]["gates"] == {
            "quota_denied": False, "acceptance_backpressure": False,
        }
        assert f.calls == [], "check-request 模式不得调用控制器"

        (f.root / "broken.json").write_text("{not json", encoding="utf-8")
        proc = run_cli_raw(["--check-request", str(f.root / "broken.json")])
        assert proc.returncode == 65
        payload = json.loads(proc.stdout)
        assert payload["valid"] is False and payload["errors"]

        bad = f.base_request()
        bad["project_id"] = "-leading-dash"
        bad_path = f.root / "bad.json"
        bad_path.write_text(json.dumps(bad), encoding="utf-8")
        proc = run_cli_raw(["--check-request", str(bad_path)])
        assert proc.returncode == 65
        payload = json.loads(proc.stdout)
        assert payload["valid"] is False
        return {"check_request_valid": True}
    finally:
        f.close()


def case_example_template_validates() -> dict[str, Any]:
    assert EXAMPLE_TEMPLATE.exists(), f"缺少模板：{EXAMPLE_TEMPLATE}"
    proc = run_cli_raw(["--check-request", str(EXAMPLE_TEMPLATE)])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["valid"] is True, payload["errors"]
    request = payload["request"]
    assert request["contract"] == REQUEST_CONTRACT
    assert request["identity"]["fencing_token"] >= 1
    assert request["controller"]["path"].startswith("/")
    return {"example": str(EXAMPLE_TEMPLATE.name), "valid": True}


def case_example_shape_drives_real_cycle() -> dict[str, Any]:
    f = Fixture()
    try:
        example = json.loads(EXAMPLE_TEMPLATE.read_text(encoding="utf-8"))
        example["controller"] = {
            "path": str(f.controller), "sha256": digest(f.controller),
        }
        example["mutation_adapter"] = {
            "path": str(f.adapter), "sha256": digest(f.adapter),
        }
        example["repo"] = str(f.repo)
        f.script(green_script(
            f,
            project=str(example["project_id"]),
            owner=str(example["owner"]),
            token=int(example["fencing_token"]),
            policy=str(example["policy_commit"]),
        ))
        proc = f.run(example)
        assert proc.returncode == 0, proc.stderr
        result = f.result(proc)
        assert result["decision"] == "dispatch", result["reason"]
        assert len(f.tick_calls()) == 1
        return {"decision": result["decision"], "ticks": 1}
    finally:
        f.close()


# ---------------------------------------------------------------------------
# 具名脚本化拒绝场景（供上方 wrapper 复用的数据）
# ---------------------------------------------------------------------------


def scripted_refusal(
    responses_builder, *, expect_decision: str, expect_calls: int,
    reason_contains: str, future: bool | None = None,
    request_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    f = Fixture()
    try:
        f.script(responses_builder(f))
        request = f.base_request()
        request.update(request_overrides or {})
        proc = f.run(request)
        assert proc.returncode == 0, proc.stderr
        result = f.result(proc)
        assert result["decision"] == expect_decision, result["reason"]
        assert reason_contains in result["reason"], result["reason"]
        assert len(f.tick_calls()) == 0, f"拒绝场景出现 tick：{f.tick_calls()}"
        assert len(f.calls) == expect_calls, f.calls
        if future is not None:
            assert result["future_heartbeat_needed"] is future
        return {"calls": expect_calls, "ticks": 0, "decision": expect_decision}
    finally:
        f.close()


def case_quota_denied_gate_blocks_tick() -> dict[str, Any]:
    def build(f: Fixture) -> list[dict[str, Any]]:
        return [
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_ready("spawn")},
            {"exit": 0, "stdout": f.status_ok()},
        ]
    return scripted_refusal(
        build, expect_decision="wait", expect_calls=3, reason_contains="配额",
        request_overrides={"gates": {"quota_denied": True}},
    )


def case_declared_backpressure_blocks_spawn() -> dict[str, Any]:
    def build(f: Fixture) -> list[dict[str, Any]]:
        return [
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_ready("spawn")},
            {"exit": 0, "stdout": f.status_ok()},
        ]
    return scripted_refusal(
        build, expect_decision="wait", expect_calls=3, reason_contains="反压",
        request_overrides={"gates": {"acceptance_backpressure": True}},
    )


def case_provider_reset_ticks_nothing() -> dict[str, Any]:
    def build(f: Fixture) -> list[dict[str, Any]]:
        return [
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_internal(
                "retry_later", "provider reset needs explicit resume"
            )},
        ]
    return scripted_refusal(
        build, expect_decision="wait", expect_calls=2, reason_contains="retry_later",
    )


def case_stale_facts_ticks_nothing() -> dict[str, Any]:
    def build(f: Fixture) -> list[dict[str, Any]]:
        return [
            {"exit": 0, "stdout": f.status_ok()},
            {
                "exit": 75, "stdout": "",
                "stderr": controller_error_payload(
                    "facts snapshot expired before reconcile", 75
                ),
            },
        ]
    return scripted_refusal(
        build, expect_decision="wait", expect_calls=2, reason_contains="reconcile 失败",
    )


def case_runtime_missing_stops() -> dict[str, Any]:
    def build(f: Fixture) -> list[dict[str, Any]]:
        return [{
            "exit": 66, "stdout": "",
            "stderr": controller_error_payload("Autopilot runtime is not initialized", 66),
        }]
    return scripted_refusal(
        build, expect_decision="review", expect_calls=1,
        reason_contains="未初始化", future=False,
    )


def case_lease_missing_refuses() -> dict[str, Any]:
    def build(f: Fixture) -> list[dict[str, Any]]:
        return [{
            "exit": 0,
            "stdout": f.status_ok(owner="pm-someone-else", pending=None),
        }]
    return scripted_refusal(
        build, expect_decision="review", expect_calls=1, reason_contains="租约", future=False,
    )


def case_project_identity_mismatch_refuses() -> dict[str, Any]:
    def build(f: Fixture) -> list[dict[str, Any]]:
        return [{"exit": 0, "stdout": f.status_ok(project="project-other")}]
    return scripted_refusal(
        build, expect_decision="review", expect_calls=1, reason_contains="身份",
    )


def case_unknown_action_outside_allowlist_refuses() -> dict[str, Any]:
    def build(f: Fixture) -> list[dict[str, Any]]:
        return [
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_ready("rm_rf_hostile")},
        ]
    return scripted_refusal(
        build, expect_decision="review", expect_calls=2, reason_contains="allowlist",
    )


def case_internal_action_marked_external_refuses() -> dict[str, Any]:
    def build(f: Fixture) -> list[dict[str, Any]]:
        return [
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_ready("adopt", external=False)},
        ]
    return scripted_refusal(
        build, expect_decision="review", expect_calls=2, reason_contains="allowlist",
    )


def case_await_revalidation_ticks_nothing_v2() -> dict[str, Any]:
    def build(f: Fixture) -> list[dict[str, Any]]:
        return [
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_await("await_revalidation")},
        ]
    return scripted_refusal(
        build, expect_decision="wait", expect_calls=2, reason_contains="收敛",
    )


def case_internal_observe_ticks_nothing_v2() -> dict[str, Any]:
    def build(f: Fixture) -> list[dict[str, Any]]:
        return [
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_internal("observe", "active Dispatch authoritative")},
        ]
    return scripted_refusal(
        build, expect_decision="wait", expect_calls=2, reason_contains="observe",
    )


def case_acceptance_repair_keeps_heartbeat_alive_v2() -> dict[str, Any]:
    """回归（v2.14.0）：内部可恢复验收失败不得映射为 park/停心跳。

    控制器规划 repair_acceptance（acceptance-recovery 分类为
    internal_recoverable 且预算未耗尽）时，适配器必须输出 decision=review
    且 future_heartbeat_needed=true、零 tick——不得硬编码
    "any gate failure => park"。
    """
    f = Fixture()
    try:
        f.script([
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_repair(step="repair", used=0, total=2)},
        ])
        proc = f.run(f.base_request())
        assert proc.returncode == 0, f"exit={proc.returncode} stderr={proc.stderr}"
        result = f.result(proc)
        assert result["controller_action"] == "repair_acceptance", result
        assert result["decision"] == "review", result["reason"]
        assert result["future_heartbeat_needed"] is True, result
        assert result["tick"]["invoked"] is False, result["tick"]
        assert result["fail_closed"]["refused"] is False, result["fail_closed"]
        assert "internal_recoverable" in result["reason"], result["reason"]
        assert len(f.tick_calls()) == 0

        # 第二个修复 episode（re_review 步骤）同样不得泊车。
        f.script([
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_repair(step="re_review", used=1, total=2)},
        ])
        f.log_path.unlink()
        proc = f.run(f.base_request())
        assert proc.returncode == 0, f"exit={proc.returncode} stderr={proc.stderr}"
        result = f.result(proc)
        assert result["decision"] == "review", result["reason"]
        assert result["future_heartbeat_needed"] is True, result
        assert "re_review" in result["reason"], result["reason"]
        return {"ticks": 0, "decisions": ["review", "review"], "park": False}
    finally:
        f.close()


def case_exhausted_repair_budget_parks_v2() -> dict[str, Any]:
    """回归（v2.14.0）：修复预算耗尽（控制器 hard_park + internal_recoverable
    failure_class）仍然必须 park 并停止心跳——预算耗尽不是继续心跳的理由。"""
    f = Fixture()
    try:
        f.script([
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_internal(
                "hard_park",
                "acceptance checks failed: repair_budget_exhausted",
                failure_class="internal_recoverable",
            )},
        ])
        proc = f.run(f.base_request())
        assert proc.returncode == 0, f"exit={proc.returncode} stderr={proc.stderr}"
        result = f.result(proc)
        assert result["decision"] == "park", result["reason"]
        assert result["future_heartbeat_needed"] is False, result
        assert result["tick"]["invoked"] is False
        assert len(f.tick_calls()) == 0
        return {"ticks": 0, "decision": "park"}
    finally:
        f.close()


def case_hard_park_stops_heartbeat_v2() -> dict[str, Any]:
    def build(f: Fixture) -> list[dict[str, Any]]:
        return [
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_internal("hard_park", "external facts ambiguous")},
        ]
    return scripted_refusal(
        build, expect_decision="park", expect_calls=2, reason_contains="硬泊车", future=False,
    )


def case_reject_duplicate_stops_heartbeat_v2() -> dict[str, Any]:
    def build(f: Fixture) -> list[dict[str, Any]]:
        return [
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_internal("reject_duplicate", "duplicate worktrees")},
        ]
    return scripted_refusal(
        build, expect_decision="review", expect_calls=2, reason_contains="重复", future=False,
    )


def case_internal_complete_stops_heartbeat_v2() -> dict[str, Any]:
    def build(f: Fixture) -> list[dict[str, Any]]:
        return [
            {"exit": 0, "stdout": f.status_ok()},
            {"exit": 0, "stdout": f.reconcile_internal("complete", "all items complete")},
        ]
    return scripted_refusal(
        build, expect_decision="complete", expect_calls=2,
        reason_contains="心跳可以停止", future=False,
    )


CASES: list[tuple[str, Any]] = [
    ("有效 spawn 循环恰好一次 tick 且 argv 精确钉扎", case_valid_spawn_executes_exactly_one_tick_with_pinned_argv),
    ("敌意身份字段按单个 argv 元素传递不被 shell 解释", case_hostile_identity_travels_as_single_argv_element),
    ("receipt 之后的下一次心跳不再 tick", case_second_heartbeat_after_receipt_ticks_nothing),
    ("声明配额拒绝时拒绝 tick", case_quota_denied_gate_blocks_tick),
    ("声明验收反压时拒绝 spawn tick", case_declared_backpressure_blocks_spawn),
    ("机械验收反压（3 个 open PR）拒绝 spawn tick", case_mechanical_backpressure_blocks_spawn),
    ("2 个 open PR 允许 spawn tick", case_two_open_prs_allow_spawn),
    ("provider 重置（retry_later）不 tick", case_provider_reset_ticks_nothing),
    ("reconcile 失败（事实过期）不 tick", case_stale_facts_ticks_nothing),
    ("runtime 未初始化时停止心跳", case_runtime_missing_stops),
    ("租约缺失/不匹配时拒绝并停止", case_lease_missing_refuses),
    ("project 身份不一致时拒绝", case_project_identity_mismatch_refuses),
    ("allowlist 之外的动作拒绝 tick", case_unknown_action_outside_allowlist_refuses),
    ("内部动作被标记 external 时防御性拒绝", case_internal_action_marked_external_refuses),
    ("await_revalidation 不 tick", case_await_revalidation_ticks_nothing_v2),
    ("内部 observe 不 tick", case_internal_observe_ticks_nothing_v2),
    ("内部可恢复验收失败（repair_acceptance）不泊车且心跳继续", case_acceptance_repair_keeps_heartbeat_alive_v2),
    ("修复预算耗尽的 hard_park 仍泊车并停止心跳", case_exhausted_repair_budget_parks_v2),
    ("hard_park 停止心跳", case_hard_park_stops_heartbeat_v2),
    ("reject_duplicate 停止心跳", case_reject_duplicate_stops_heartbeat_v2),
    ("内部 complete 停止心跳", case_internal_complete_stops_heartbeat_v2),
    ("pre-tick status 显示待定意图不 ready 时拒绝 tick", case_pre_tick_pending_not_ready_refuses),
    ("status 超时有界且不 tick", case_status_timeout_is_bounded_and_ticks_nothing),
    ("tick 超时标记不确定且绝不重试", case_tick_timeout_marks_uncertain_without_retry),
    ("tick 非零退出按不确定处理且绝不重试", case_tick_nonzero_exit_is_uncertain_and_never_retried),
    ("tick 零退出但输出畸形按不确定处理", case_tick_malformed_zero_exit_output_is_uncertain),
    ("status 畸形输出 fail-closed 且不继续", case_status_malformed_output_is_fail_closed),
    ("COMPLETE 状态直接停止且不再 reconcile", case_complete_state_stops_without_reconcile),
    ("reconcile 缺少 planned_action 时防御性拒绝", case_reconcile_missing_planned_action_refuses),
    ("请求硬校验 fail-closed（非法/漂移/symlink/用法）", case_request_validation_fail_closed),
    ("check-request 模式只做结构校验", case_check_request_mode),
    ("example 模板通过结构校验", case_example_template_validates),
    ("example 形状可驱动一次真实形状的完整循环", case_example_shape_drives_real_cycle),
]


def main() -> int:
    evidence: list[dict[str, Any]] = []
    failures = 0
    for index, (name, operation) in enumerate(CASES, start=1):
        try:
            detail = operation()
        except Exception as exc:
            failures += 1
            print(f"not ok {index} - {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok {index} - {name}")
            evidence.append({"case": name, "evidence": detail})
    print(json.dumps({
        "contract": SELFTEST_CONTRACT,
        "passed": len(CASES) - failures, "failed": failures,
        "network_calls": 0, "real_orca_github_calls": 0,
        "evidence": evidence,
        "not_verified": [
            "真实 autopilot-controller 集成（本套件按任务约束只使用假控制器）",
            "真实 Orca/GitHub 变更适配器（任务禁止真实变更）",
            "外部 Codex App automation 调度行为",
        ],
    }, ensure_ascii=False, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
