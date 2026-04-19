#!/usr/bin/env python3
"""审查计划加载与基础校验。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

NEGOTIATION_KEYWORDS = (
    "谈判",
    "协商",
    "待确认",
    "需确认",
    "待补充",
    "可考虑",
    "保留弹性",
    "另行约定",
)

PLACEHOLDER_KEYWORDS = (
    "待填写",
    "待补",
    "待补充",
    "留空",
    "空白",
    "未填写",
    "未补充",
    "负责人",
    "联系方式",
    "邮箱",
    "电子邮箱",
    "附件",
)

DETERMINISTIC_KEYWORDS = (
    "笔误",
    "错别字",
    "术语统一",
    "格式统一",
    "更正",
    "应为",
    "统一为",
    "删除重复",
)

ACTION_ALIAS = {
    "comment": "comment",
    "批注": "comment",
    "注释": "comment",
    "report-only": "report-only",
    "report_only": "report-only",
    "仅报告": "report-only",
    "仅写入意见书": "report-only",
    "意见书": "report-only",
    "replace": "replace",
    "修订": "replace",
    "修改": "replace",
    "insert": "insert",
    "插入": "insert",
    "新增": "insert",
    "delete": "delete",
    "删除": "delete",
    "auto": "auto",
    "自动": "auto",
    "none": "none",
    "skip": "skip",
}

EDIT_POLICIES = {"comment-first", "balanced", "revise-first"}


def load_plan(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("审查计划 JSON 顶层必须是对象")
    return payload


def get_plan_meta(plan: dict[str, Any]) -> dict[str, Any]:
    meta = plan.get("meta")
    return meta if isinstance(meta, dict) else {}


def get_findings(plan: dict[str, Any]) -> list[Any]:
    findings = plan.get("findings") or plan.get("risks") or []
    if not isinstance(findings, list):
        raise ValueError("findings 必须是数组")
    return findings


def _normalize_action(action: Any) -> str:
    raw = str(action or "").strip()
    if not raw:
        return "auto"
    return ACTION_ALIAS.get(raw.lower(), ACTION_ALIAS.get(raw, raw.lower()))


def normalize_edit_policy(policy: Any, default: str = "revise-first") -> str:
    raw = str(policy or "").strip().lower()
    if not raw:
        return default
    if raw not in EDIT_POLICIES:
        raise ValueError(f"不支持的 edit_policy: {policy}")
    return raw


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "是"}
    return False


def _contains_keywords(finding: dict[str, Any], keywords: tuple[str, ...]) -> bool:
    text = " ".join(
        str(finding.get(key) or "")
        for key in ("risk", "title", "description", "suggestion", "comment", "reason")
    )
    return any(keyword in text for keyword in keywords)


def _looks_like_placeholder_finding(finding: dict[str, Any]) -> bool:
    descriptive_fields = [
        str(finding.get(key) or "")
        for key in ("risk", "title", "description", "suggestion", "comment", "reason")
    ]
    target_fields = [str(finding.get(key) or "") for key in ("target_text", "search")]
    descriptive_haystack = " ".join(descriptive_fields)
    full_haystack = " ".join(descriptive_fields + target_fields)
    if "____" in full_haystack or "【" in full_haystack or "】" in full_haystack:
        return True
    return any(keyword in descriptive_haystack for keyword in PLACEHOLDER_KEYWORDS)


def _has_direct_edit_payload(
    finding: dict[str, Any],
    *,
    edit_policy: str,
) -> bool:
    if (
        finding.get("replacement_text") is not None
        or finding.get("insert_text") is not None
        or _is_truthy(finding.get("delete"))
        or _is_truthy(finding.get("remove"))
    ):
        return True

    if edit_policy == "revise-first":
        recommended_text = str(finding.get("recommended_text") or "").strip()
        return bool(recommended_text)

    return False


def infer_strategy_flags(
    finding: dict[str, Any],
    *,
    edit_policy: str = "revise-first",
) -> dict[str, bool]:
    """推断审查项属于谈判建议还是确定性改动。"""
    action = _normalize_action(finding.get("action"))
    policy = normalize_edit_policy(edit_policy)

    explicit_negotiation = any(
        _is_truthy(finding.get(key))
        for key in ("needs_negotiation", "requires_negotiation", "needs_confirmation")
    )
    explicit_deterministic = any(
        _is_truthy(finding.get(key))
        for key in ("deterministic_edit", "is_typo_fix", "term_unification")
    )

    if explicit_negotiation:
        return {"needs_negotiation": True, "deterministic_edit": False}
    if explicit_deterministic:
        return {"needs_negotiation": False, "deterministic_edit": True}
    if _looks_like_placeholder_finding(finding):
        return {"needs_negotiation": True, "deterministic_edit": False}

    has_edit_payload = _has_direct_edit_payload(finding, edit_policy=policy)
    negotiation_hint = _contains_keywords(finding, NEGOTIATION_KEYWORDS)
    deterministic_hint = _contains_keywords(finding, DETERMINISTIC_KEYWORDS)

    if action == "comment":
        return {"needs_negotiation": True, "deterministic_edit": False}
    if action == "report-only":
        return {"needs_negotiation": False, "deterministic_edit": False}
    if action in {"replace", "insert", "delete"}:
        return {"needs_negotiation": False, "deterministic_edit": True}
    if action in {"none", "skip"}:
        return {"needs_negotiation": False, "deterministic_edit": False}
    if negotiation_hint:
        return {"needs_negotiation": True, "deterministic_edit": False}
    if has_edit_payload or deterministic_hint:
        return {"needs_negotiation": False, "deterministic_edit": True}
    return {"needs_negotiation": True, "deterministic_edit": False}


def enrich_findings(
    findings: list[Any],
    *,
    edit_policy: str = "revise-first",
) -> list[Any]:
    """为审查项补全 action 与策略标记，不覆盖已有显式字段。"""
    policy = normalize_edit_policy(edit_policy)
    enriched: list[Any] = []
    for item in findings:
        if not isinstance(item, dict):
            enriched.append(item)
            continue

        finding = dict(item)
        action = _normalize_action(finding.get("action"))
        finding["action"] = action

        inferred = infer_strategy_flags(finding, edit_policy=policy)
        finding.setdefault("needs_negotiation", inferred["needs_negotiation"])
        finding.setdefault("deterministic_edit", inferred["deterministic_edit"])
        enriched.append(finding)
    return enriched


def enrich_plan(
    plan: dict[str, Any],
    *,
    edit_policy: str | None = None,
) -> dict[str, Any]:
    """补全审查计划中的审查项策略字段。"""
    result = deepcopy(plan)
    meta = get_plan_meta(result)
    policy = normalize_edit_policy(edit_policy or meta.get("edit_policy"), default="revise-first")
    if isinstance(meta, dict):
        meta["edit_policy"] = policy
        result["meta"] = meta
    findings = get_findings(result)
    if "findings" in result:
        result["findings"] = enrich_findings(findings, edit_policy=policy)
    elif "risks" in result:
        result["risks"] = enrich_findings(findings, edit_policy=policy)
    else:
        result["findings"] = enrich_findings(findings, edit_policy=policy)
    return result
