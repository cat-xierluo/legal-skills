#!/usr/bin/env python3
"""acceptance-recovery.py 的离线契约自测：单一机械分类合同。

全部用例通过真实 CLI（classify/table 子命令）与直接导入模块 API 两条路径
驱动，零网络、零外部副作用。覆盖：

  - 三类失败的最小机械分类表（internal_recoverable / external_dependency /
    safety_unknown）与表外信号 fail-closed 归 safety_unknown；
  - internal_recoverable 预算语义：首次 repair、后续 re_review、耗尽 park，
    默认预算 2 且可显式覆盖；
  - 输入校验 fail-closed（缺 attempts、占位信号、坏 schema、布尔伪装整数）；
  - module API 与 CLI 输出一致（autopilot_runtime 与 codex-heartbeat-cycle
    复用同一张表，不允许两套语义）。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


SCRIPT = Path(__file__).resolve().parent / "acceptance-recovery.py"
SCHEMA = "acceptance-recovery.v1"

passed = 0
failed = 0


def check(label: str, condition: bool, detail: Any = "") -> None:
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"FAIL {label}: {detail}")


def run_cli(payload: dict[str, Any] | None, mode: str = "classify") -> tuple[int, dict[str, Any]]:
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
        if payload is not None:
            json.dump(payload, handle)
            handle.flush()
            argv = [sys.executable, str(SCRIPT), mode, handle.name]
        else:
            argv = [sys.executable, str(SCRIPT), mode]
        result = subprocess.run(argv, capture_output=True, text=True, check=False)
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        parsed = {"_stdout": result.stdout, "_stderr": result.stderr}
    return result.returncode, parsed


def record(signal: str, used: int = 0, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA,
        "failure_signal": signal,
        "repair_attempts_used": used,
    }
    payload.update(overrides)
    return payload


# -- internal_recoverable：预算内 repair / re_review，耗尽 park ------------------

code, out = run_cli(record("pr_checks_failed", 0))
check("first failure is repair", (code, out.get("ok"), out.get("failure_class"), out.get("action"))
      == (0, True, "internal_recoverable", "repair"), out)
check("budget remaining reported", out.get("repair_attempts_remaining") == 2, out)
check("park_reason empty when repairing", out.get("park_reason") is None, out)

code, out = run_cli(record("review_blocking_findings", 1))
check("second episode is re_review", out.get("action") == "re_review", out)
check("re_review keeps one attempt left", out.get("repair_attempts_remaining") == 1, out)

code, out = run_cli(record("delivery_out_of_scope", 2))
check("exhausted budget parks", out.get("action") == "park", out)
check("exhausted park reason", out.get("park_reason") == "repair_budget_exhausted", out)
check("exhausted keeps internal class", out.get("failure_class") == "internal_recoverable", out)

code, out = run_cli(record("verification_evidence_missing", 3, max_repair_attempts=5))
check("custom budget re_review within window", out.get("action") == "re_review", out)
check("custom budget remaining reported", out.get("repair_attempts_remaining") == 2, out)

code, out = run_cli(record("verification_evidence_missing", 5, max_repair_attempts=5))
check("custom budget exhausted at limit", out.get("action") == "park", out)

code, out = run_cli(record("docs_acceptance_repair", 1, max_repair_attempts=3))
check("custom budget re_review within window", out.get("action") == "re_review", out)

# -- external_dependency / safety_unknown：立即 park -----------------------------

for signal, expected_class in (
    ("provider_quota_exhausted", "external_dependency"),
    ("upstream_service_unavailable", "external_dependency"),
    ("missing_user_asset_or_authorization", "external_dependency"),
    ("third_party_api_failure", "external_dependency"),
    ("facts_unknown_or_ambiguous", "safety_unknown"),
    ("identity_or_head_drift_unprovable", "safety_unknown"),
    ("security_or_high_risk_evidence", "safety_unknown"),
    ("runtime_corrupted_or_future_schema", "safety_unknown"),
):
    code, out = run_cli(record(signal, 0))
    check(f"{signal} parks immediately",
          (out.get("failure_class"), out.get("action")) == (expected_class, "park"), out)
    check(f"{signal} park reason names class",
          str(out.get("park_reason", "")).startswith(expected_class), out)
    check(f"{signal} parks even at zero budget", out.get("repair_attempts_remaining") == 2, out)

# -- 表外信号 fail-closed 归 safety_unknown --------------------------------------

code, out = run_cli(record("some_future_unknown_signal", 0))
check("unknown signal is not recognized", out.get("recognized_signal") is False, out)
check("unknown signal parks fail-closed",
      (out.get("failure_class"), out.get("action")) == ("safety_unknown", "park"), out)

# -- 输入校验 fail-closed ---------------------------------------------------------

code, out = run_cli({"schema_version": "acceptance-recovery.v0", "failure_signal": "pr_checks_failed", "repair_attempts_used": 0})
check("wrong schema rejected", (code, out.get("ok")) == (2, False), out)

code, out = run_cli({"schema_version": SCHEMA, "failure_signal": "pr_checks_failed"})
check("missing attempts rejected", (code, out.get("ok")) == (2, False), out)

code, out = run_cli({"schema_version": SCHEMA, "failure_signal": "tbd", "repair_attempts_used": 0})
check("placeholder signal rejected", (code, out.get("ok")) == (2, False), out)

code, out = run_cli({"schema_version": SCHEMA, "failure_signal": "pr_checks_failed", "repair_attempts_used": True})
check("boolean attempts rejected", (code, out.get("ok")) == (2, False), out)

code, out = run_cli({"schema_version": SCHEMA, "failure_signal": "pr_checks_failed", "repair_attempts_used": -1})
check("negative attempts rejected", (code, out.get("ok")) == (2, False), out)

code, out = run_cli({"schema_version": SCHEMA, "failure_signal": "pr_checks_failed", "repair_attempts_used": 0, "max_repair_attempts": 0})
check("non-positive max budget rejected", (code, out.get("ok")) == (2, False), out)

code, out = run_cli(None, mode="table")
check("table subcommand dumps the mechanical table",
      code == 0 and out.get("default_max_repair_attempts") == 2
      and out.get("failure_class_by_signal", {}).get("pr_checks_failed") == "internal_recoverable", out)

# -- module API 与 CLI 同表（runtime/heartbeat 复用路径） -------------------------

spec_loader = importlib.util.spec_from_file_location("acceptance_recovery_selftest", SCRIPT)
module = importlib.util.module_from_spec(spec_loader)
spec_loader.loader.exec_module(module)  # type: ignore[union-attr]

check("module default budget is 2", module.DEFAULT_MAX_REPAIR_ATTEMPTS == 2)
for signal, expected in (
    ("pr_checks_failed", "internal_recoverable"),
    ("provider_quota_exhausted", "external_dependency"),
    ("identity_or_head_drift_unprovable", "safety_unknown"),
):
    api = module.classify_failure(signal, 0)
    _code, cli = run_cli(record(signal, 0))
    check(f"module and CLI agree on {signal}",
          (api["failure_class"], api["action"]) == (cli["failure_class"], cli["action"]),
          {"api": api, "cli": cli})
check("module unknown signal is fail-closed",
      module.classify_failure("never-heard-of-it", 0)["failure_class"] == "safety_unknown")
check("module repair/re-review actions exposed",
      (module.ACTION_REPAIR, module.ACTION_RE_REVIEW, module.ACTION_PARK) == ("repair", "re_review", "park"))

print(f"acceptance recovery tests: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
