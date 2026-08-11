"""候选外可复用的审查报告完整性校验。

本模块不负责渲染或写出报告。调用方必须在生成正式交付物前调用它，
避免“渲染未报错”被误判为“报告可以交付”。
"""

from __future__ import annotations

import re
from typing import Any

MISSING_PLACEHOLDER = "待补充"
MAX_MISSING_PLACEHOLDERS = 10
_DETAIL_SECTION = re.compile(r"## 四、详细审查意见\s*(.*?)(?=\n## 五、|\Z)", re.DOTALL)
_FINDING_HEADING = re.compile(r"^### \d+\. ", re.MULTILINE)
_LEGAL_BASIS_LINE = re.compile(r"^- 法律依据：\s*(\S.*?)\s*$", re.MULTILINE)


def _findings(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(plan, dict):
        return []
    raw = plan.get("findings") or plan.get("risks") or []
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _legal_basis_text(finding: dict[str, Any]) -> str:
    basis = finding.get("legal_basis")
    if isinstance(basis, (list, tuple, set)):
        return "；".join(str(item).strip() for item in basis if str(item).strip())
    return str(basis or "").strip()


def _has_meaningful_legal_basis(value: str) -> bool:
    """法律依据必须是可核验内容，不能用缺失占位符伪装为已填写。"""
    normalized = value.strip().replace(" ", "")
    if not normalized:
        return False
    return normalized not in {"/", "待补", "待补充", "未提及", "未提及/待补充", "依据待补"}


def check_plan_integrity(plan: dict[str, Any]) -> dict[str, Any]:
    """检查每一项结构化审查 finding 是否具有可交付的法律依据。"""
    missing_ids: list[str] = []
    for index, finding in enumerate(_findings(plan), start=1):
        if not _has_meaningful_legal_basis(_legal_basis_text(finding)):
            missing_ids.append(str(finding.get("id") or f"R{index:03d}"))
    problems = []
    if missing_ids:
        problems.append("以下审查项缺少法律依据：" + "、".join(missing_ids))
    return {
        "passed": not problems,
        "finding_count": len(_findings(plan)),
        "missing_legal_basis_ids": missing_ids,
        "problems": problems,
    }


def check_report_integrity(report: str) -> dict[str, Any]:
    """检查最终文本的字段塌缩和详细审查项法律依据覆盖。"""
    missing_count = report.count(MISSING_PLACEHOLDER)
    detail_match = _DETAIL_SECTION.search(report)
    detail_section = detail_match.group(1) if detail_match else ""
    finding_count = len(_FINDING_HEADING.findall(detail_section))
    legal_basis_count = sum(
        1 for value in _LEGAL_BASIS_LINE.findall(detail_section) if _has_meaningful_legal_basis(value)
    )
    missing_legal_basis_count = max(finding_count - legal_basis_count, 0)

    problems: list[str] = []
    if missing_count > MAX_MISSING_PLACEHOLDERS:
        problems.append(
            f"报告存在 {missing_count} 处“{MISSING_PLACEHOLDER}”占位，"
            f"超过阈值 {MAX_MISSING_PLACEHOLDERS}，字段未落地"
        )
    if missing_legal_basis_count:
        problems.append(
            f"详细审查意见有 {finding_count} 项，但仅有 {legal_basis_count} 项法律依据"
        )
    return {
        "passed": not problems,
        "missing_placeholder_count": missing_count,
        "finding_count": finding_count,
        "legal_basis_count": legal_basis_count,
        "empty_legal_basis_count": missing_legal_basis_count,
        "problems": problems,
    }


def check_delivery_integrity(plan: dict[str, Any], report: str) -> dict[str, Any]:
    """合并计划与最终报告校验，作为正式交付物的唯一完整性门禁。"""
    plan_result = check_plan_integrity(plan)
    report_result = check_report_integrity(report)
    problems = [*plan_result["problems"], *report_result["problems"]]
    return {
        "passed": not problems,
        "plan": plan_result,
        "report": report_result,
        "problems": problems,
    }


def format_integrity_failure(result: dict[str, Any]) -> str:
    lines = ["报告未通过完整性复核："]
    lines.extend(f"  - {problem}" for problem in result.get("problems", []))
    lines.append("  请补齐审查计划中的对应字段后重新生成正式交付物。")
    return "\n".join(lines)
