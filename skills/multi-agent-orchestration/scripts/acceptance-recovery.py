#!/usr/bin/env python3
"""acceptance-recovery.py — 验收失败的单一机械分类合同（fail-closed）。

编排合同曾把「任何门禁失败」直接映射为泊车：autopilot_runtime 对
`checks == "fail"` 一律 hard_park，codex-heartbeat 对 hard_park 一律
decision=park 且建议停止心跳。内部可恢复的验收失败（本项目资产即可修复）
因此被错误泊车。本模块是修复后的唯一分类权威：autopilot runtime 与
codex-heartbeat-cycle 都从这里导入同一张表，不得各自硬编码
「gate failure => park」。

三类失败（v2.14.0 合同，不得增删语义后仍声称本版本）：

- `internal_recoverable`：可用本项目自有资产修复（PR checks 确定性失败、
  交付 diff 越界、验证证据缺失、review blocking findings、docs-only 验收
  修复）。修复预算未耗尽时动作必须是 `repair`（首次）或 `re_review`
  （已有修复记录后的复核），默认预算 2 次；耗尽才 `park`。
- `external_dependency`：依赖用户资产、环境、授权或外部服务（配额耗尽、
  上游不可用、第三方 API 故障）→ 立即 `park`。
- `safety_unknown`：事实不明或不可证明（身份/head 漂移不可证、歧义事实、
  安全高风险证据、runtime 损坏）→ 立即 `park`（fail-closed）。

表外信号一律归 `safety_unknown` 并立即泊车——未知即不安全，绝不默认可修。

修复预算按「失败 episode」计数：从非 repair_acceptance 状态进入
repair_acceptance 记一次；同一 episode 内的重复 reconcile 不重复计数
（修复在途 ≠ 新失败）。计数语义见 autopilot_runtime 的 reconcile 收尾。

用法：
  acceptance-recovery.py classify INPUT.json   # 分类一条失败记录
  acceptance-recovery.py table                 # 输出机械分类表（机器可读）

退出码：0 = 分类完成（action=park 也是正常分类结果，看 JSON 的 action）；
2 = 输入缺失/非法。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


SCHEMA = "acceptance-recovery.v1"
DEFAULT_MAX_REPAIR_ATTEMPTS = 2

INTERNAL_RECOVERABLE = "internal_recoverable"
EXTERNAL_DEPENDENCY = "external_dependency"
SAFETY_UNKNOWN = "safety_unknown"

ACTION_REPAIR = "repair"
ACTION_RE_REVIEW = "re_review"
ACTION_PARK = "park"

# 单一机械分类表：信号 → 失败类别。autopilot_runtime、codex-heartbeat-cycle
# 与 acceptance-repair-gate 全部从这里取表，禁止在别处再写分类分支。
FAILURE_CLASS_BY_SIGNAL: dict[str, str] = {
    # internal_recoverable：本项目自有资产可修复
    "pr_checks_failed": INTERNAL_RECOVERABLE,
    "verification_evidence_missing": INTERNAL_RECOVERABLE,
    "delivery_out_of_scope": INTERNAL_RECOVERABLE,
    "review_blocking_findings": INTERNAL_RECOVERABLE,
    "docs_acceptance_repair": INTERNAL_RECOVERABLE,
    # external_dependency：立即泊车
    "provider_quota_exhausted": EXTERNAL_DEPENDENCY,
    "upstream_service_unavailable": EXTERNAL_DEPENDENCY,
    "missing_user_asset_or_authorization": EXTERNAL_DEPENDENCY,
    "third_party_api_failure": EXTERNAL_DEPENDENCY,
    # safety_unknown：立即泊车（fail-closed）
    "facts_unknown_or_ambiguous": SAFETY_UNKNOWN,
    "identity_or_head_drift_unprovable": SAFETY_UNKNOWN,
    "security_or_high_risk_evidence": SAFETY_UNKNOWN,
    "runtime_corrupted_or_future_schema": SAFETY_UNKNOWN,
}
UNKNOWN_SIGNAL_CLASS = SAFETY_UNKNOWN


def classify_failure(
    failure_signal: str, repair_attempts_used: int, max_repair_attempts: int = DEFAULT_MAX_REPAIR_ATTEMPTS,
) -> dict[str, Any]:
    """对一条失败记录给出机械决策；纯函数，无 IO。"""
    recognized = failure_signal in FAILURE_CLASS_BY_SIGNAL
    failure_class = FAILURE_CLASS_BY_SIGNAL.get(failure_signal, UNKNOWN_SIGNAL_CLASS)
    result: dict[str, Any] = {
        "failure_signal": failure_signal,
        "recognized_signal": recognized,
        "failure_class": failure_class,
        "repair_attempts_used": repair_attempts_used,
        "max_repair_attempts": max_repair_attempts,
        "repair_attempts_remaining": max(0, max_repair_attempts - repair_attempts_used),
        "action": ACTION_PARK,
        "park_reason": None,
    }
    if failure_class == EXTERNAL_DEPENDENCY:
        result["park_reason"] = f"external_dependency:{failure_signal}"
        return result
    if failure_class == SAFETY_UNKNOWN:
        result["park_reason"] = f"safety_unknown:{failure_signal}"
        return result
    if repair_attempts_used >= max_repair_attempts:
        result["park_reason"] = "repair_budget_exhausted"
        result["repair_attempts_remaining"] = 0
        return result
    # internal_recoverable 且预算未耗尽：首次给 repair，之后必须独立 re_review。
    result["action"] = ACTION_REPAIR if repair_attempts_used == 0 else ACTION_RE_REVIEW
    return result


def _missing(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    stripped = value.strip()
    return not stripped or stripped.casefold() in {"tbd", "todo", "unknown", "n/a", "na", "none"}


def validate_record(record: Any) -> tuple[list[str], dict[str, Any]]:
    """校验 classify 输入；返回 (errors, normalized)。"""
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["failure record must be a JSON object"], {}
    if record.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must equal {SCHEMA}")
    signal = record.get("failure_signal")
    if _missing(signal):
        errors.append("failure_signal is required and cannot be a placeholder")
    attempts = record.get("repair_attempts_used")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        errors.append("repair_attempts_used must be a non-negative integer (caller must track repair episodes)")
    max_attempts = record.get("max_repair_attempts", DEFAULT_MAX_REPAIR_ATTEMPTS)
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        errors.append("max_repair_attempts must be a positive integer when provided")
    detail = record.get("failure_detail")
    if detail is not None and (not isinstance(detail, str) or len(detail) > 2000):
        errors.append("failure_detail must be a string of at most 2000 characters when provided")
    normalized = {
        "failure_signal": signal if isinstance(signal, str) else "",
        "failure_detail": detail if isinstance(detail, str) else "",
        "repair_attempts_used": attempts if isinstance(attempts, int) and not isinstance(attempts, bool) else -1,
        "max_repair_attempts": max_attempts if isinstance(max_attempts, int) and not isinstance(max_attempts, bool) else -1,
    }
    return errors, normalized


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    classify_parser = sub.add_parser("classify", help="分类一条失败记录")
    classify_parser.add_argument("record", type=Path)
    sub.add_parser("table", help="输出机械分类表")

    args = parser.parse_args()
    if args.command == "table":
        print(json.dumps({
            "schema_version": SCHEMA,
            "failure_class_by_signal": FAILURE_CLASS_BY_SIGNAL,
            "unknown_signal_class": UNKNOWN_SIGNAL_CLASS,
            "default_max_repair_attempts": DEFAULT_MAX_REPAIR_ATTEMPTS,
            "actions": {
                INTERNAL_RECOVERABLE: f"{ACTION_REPAIR} (first episode) / {ACTION_RE_REVIEW} (later episodes), {ACTION_PARK} when budget exhausted",
                EXTERNAL_DEPENDENCY: ACTION_PARK,
                SAFETY_UNKNOWN: ACTION_PARK,
            },
        }, ensure_ascii=False, sort_keys=True))
        return 0

    try:
        record = json.loads(args.record.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 2
    errors, normalized = validate_record(record)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False))
        return 2
    outcome = classify_failure(
        normalized["failure_signal"], normalized["repair_attempts_used"], normalized["max_repair_attempts"],
    )
    print(json.dumps({"ok": True, "schema_version": SCHEMA, **outcome}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
