#!/usr/bin/env python3
"""审查报告渲染工具。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .report_docx import write_review_report_docx
except ImportError:
    from report_docx import write_review_report_docx

RISK_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def _normalize_risk_level(value: Any) -> str:
    text = str(value or "P2").upper().strip()
    if text in RISK_ORDER:
        return text
    if "高" in text:
        return "P0"
    if "中" in text:
        return "P1"
    return "P2"


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON 顶层必须是对象")
    return payload


def collect_findings(plan: dict[str, Any]) -> list[dict[str, Any]]:
    findings = plan.get("findings") or plan.get("risks") or []
    if not isinstance(findings, list):
        raise ValueError("findings 必须是数组")
    normalized = []
    for idx, item in enumerate(findings, start=1):
        if not isinstance(item, dict):
            continue
        current = dict(item)
        current.setdefault("id", f"R{idx:03d}")
        current["risk_level"] = _normalize_risk_level(current.get("risk_level"))
        normalized.append(current)
    normalized.sort(key=lambda x: (RISK_ORDER.get(x["risk_level"], 99), x["id"]))
    return normalized


def _safe_line(value: Any, fallback: str = "未提及/待补充") -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
            continue
        if isinstance(value, (int, float)):
            return str(value)
    return ""


def _to_text_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _merge_report_meta(
    plan_meta: dict[str, Any],
    execution: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(plan_meta)
    if not isinstance(execution, dict):
        return merged
    review_context = execution.get("review_context")
    if isinstance(review_context, dict):
        for key in ("client_name", "party_role", "review_intensity"):
            if not merged.get(key) and review_context.get(key):
                merged[key] = review_context.get(key)
    reviewer_profile = execution.get("reviewer_profile")
    if not isinstance(reviewer_profile, dict):
        return merged
    if not merged.get("reviewer"):
        merged["reviewer"] = reviewer_profile.get("author")
    if not merged.get("reviewer_organization"):
        merged["reviewer_organization"] = reviewer_profile.get("organization")
    if not merged.get("reviewer_department"):
        merged["reviewer_department"] = reviewer_profile.get("department")
    return merged


def _resolve_meta_text(summary: dict[str, Any], meta: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = _first_text(summary.get(key), meta.get(key))
        if text:
            return text
    return ""


def _resolve_parties(summary: dict[str, Any], meta: dict[str, Any]) -> str:
    for container in (summary, meta):
        parties = container.get("parties")
        if isinstance(parties, dict):
            party_a = _first_text(
                parties.get("party_a"),
                parties.get("party_a_name"),
                parties.get("甲方"),
            )
            party_b = _first_text(
                parties.get("party_b"),
                parties.get("party_b_name"),
                parties.get("乙方"),
            )
            if party_a or party_b:
                parts = []
                if party_a:
                    parts.append(f"甲方：{party_a}")
                if party_b:
                    parts.append(f"乙方：{party_b}")
                return "；".join(parts)

        party_list = _to_text_list(parties)
        if party_list:
            return "；".join(party_list)

        party_a = _first_text(
            container.get("party_a"),
            container.get("party_a_name"),
            container.get("甲方"),
        )
        party_b = _first_text(
            container.get("party_b"),
            container.get("party_b_name"),
            container.get("乙方"),
        )
        if party_a or party_b:
            parts = []
            if party_a:
                parts.append(f"甲方：{party_a}")
            if party_b:
                parts.append(f"乙方：{party_b}")
            return "；".join(parts)

    return "未提及/待补充"


def _resolve_party_entities(summary: dict[str, Any], meta: dict[str, Any]) -> tuple[str, str]:
    for container in (summary, meta):
        parties = container.get("parties")
        if isinstance(parties, dict):
            party_a = _first_text(
                parties.get("party_a"),
                parties.get("party_a_name"),
                parties.get("甲方"),
            )
            party_b = _first_text(
                parties.get("party_b"),
                parties.get("party_b_name"),
                parties.get("乙方"),
            )
            if party_a or party_b:
                return party_a, party_b

        party_a = _first_text(
            container.get("party_a"),
            container.get("party_a_name"),
            container.get("甲方"),
        )
        party_b = _first_text(
            container.get("party_b"),
            container.get("party_b_name"),
            container.get("乙方"),
        )
        if party_a or party_b:
            return party_a, party_b

    return "", ""


def _resolve_my_party(summary: dict[str, Any], meta: dict[str, Any], party_role: str) -> str:
    party_a, party_b = _resolve_party_entities(summary, meta)
    role = str(party_role or "").strip().lower()
    if role in {"party_a", "甲方", "a"} and party_a:
        return party_a
    if role in {"party_b", "乙方", "b"} and party_b:
        return party_b
    return "未提及/待补充"


def _resolve_other_parties(summary: dict[str, Any], meta: dict[str, Any], party_role: str) -> str:
    party_a, party_b = _resolve_party_entities(summary, meta)
    role = str(party_role or "").strip().lower()
    if role in {"party_a", "甲方", "a"} and party_b:
        return party_b
    if role in {"party_b", "乙方", "b"} and party_a:
        return party_a
    parties = _resolve_parties(summary, meta)
    return parties if parties != "未提及/待补充" else "未提及/待补充"


def _resolve_structured_text(summary: dict[str, Any], meta: dict[str, Any], *keys: str) -> str:
    for container in (summary, meta):
        for key in keys:
            value = container.get(key)
            if isinstance(value, dict):
                parts = []
                for part_key, part_value in value.items():
                    text = _first_text(part_value)
                    if text:
                        parts.append(f"{part_key}：{text}")
                if parts:
                    return "；".join(parts)
            items = _to_text_list(value)
            if items:
                return "；".join(items)
            text = _first_text(value)
            if text:
                return text
    return ""


def _resolve_key_milestones(summary: dict[str, Any], meta: dict[str, Any]) -> list[str]:
    for key in ("key_milestones", "milestones", "timeline"):
        items = _to_text_list(summary.get(key))
        if items:
            return items
        items = _to_text_list(meta.get(key))
        if items:
            return items
    return []


def _resolve_business_overview(
    summary: dict[str, Any],
    meta: dict[str, Any],
    contract_name: str,
    contract_type: str,
    party_role: str,
) -> str:
    overview = _resolve_meta_text(
        summary,
        meta,
        "business_overview",
        "contract_summary",
        "overview",
        "business_model",
    )
    if overview:
        return overview

    parts: list[str] = []
    if contract_name != "未提及/待补充":
        parts.append(f"本次审查对象为《{contract_name}》")
    if contract_type != "未提及/待补充":
        parts.append(f"合同类型暂识别为{contract_type}")
    if party_role != "未提及/待补充":
        parts.append(f"当前按{party_role}立场进行审查")
    if not parts:
        return "未提及/待补充"
    return "，".join(parts) + "。"


def _resolve_transaction_content(
    summary: dict[str, Any],
    meta: dict[str, Any],
    contract_name: str,
    contract_type: str,
    party_role: str,
) -> str:
    content = _resolve_structured_text(
        summary,
        meta,
        "transaction_content",
        "deal_overview",
        "business_overview",
        "contract_summary",
        "overview",
        "business_model",
    )
    if content:
        return content
    return _resolve_business_overview(summary, meta, contract_name, contract_type, party_role)


def _resolve_price_overview(summary: dict[str, Any], meta: dict[str, Any]) -> str:
    amount = _resolve_meta_text(summary, meta, "contract_amount", "amount", "total_amount")
    payment = _resolve_structured_text(
        summary,
        meta,
        "payment_terms",
        "payment_arrangement",
        "price_terms",
        "pricing_terms",
    )
    parts = [item for item in (amount, payment) if item]
    if not parts:
        return "未提及/待补充"
    return "；".join(parts)


def _resolve_rights_obligations(summary: dict[str, Any], meta: dict[str, Any]) -> str:
    rights = _resolve_structured_text(
        summary,
        meta,
        "rights_obligations",
        "rights_obligations_summary",
        "core_rights_obligations",
        "rights_and_obligations",
        "obligations_overview",
    )
    return rights or "未提及/待补充"


def _resolve_legal_basis(item: dict[str, Any]) -> str:
    basis = item.get("legal_basis")
    if isinstance(basis, (list, tuple, set)):
        text = "；".join(str(part).strip() for part in basis if str(part).strip())
        return text or "/"
    return _first_text(basis) or "/"


def _resolve_key_recommendations(
    summary: dict[str, Any],
    findings: list[dict[str, Any]],
) -> list[str]:
    recommendations = _to_text_list(summary.get("key_recommendations"))
    if recommendations:
        return recommendations

    derived: list[str] = []
    for item in findings:
        suggestion = _first_text(item.get("suggestion"), item.get("fix"))
        if suggestion and suggestion not in derived:
            derived.append(suggestion)
        if len(derived) >= 5:
            break
    return derived


def _resolve_overall_opinion(
    summary: dict[str, Any],
    findings: list[dict[str, Any]],
    overall: str,
    conclusion: str,
) -> str:
    opinion = _resolve_meta_text(
        summary,
        {},
        "overall_opinion",
        "review_opinion",
        "opinion",
    )
    if opinion:
        return opinion

    focus_titles: list[str] = []
    for item in findings:
        if item.get("risk_level") not in {"P0", "P1"}:
            continue
        title = _safe_line(item.get("title") or item.get("risk"))
        if title not in focus_titles:
            focus_titles.append(title)
        if len(focus_titles) >= 3:
            break

    parts: list[str] = []
    if overall != "未提及/待补充":
        parts.append(f"当前总体风险等级为{overall}")
    if conclusion != "未提及/待补充":
        parts.append(f"审查结论为{conclusion}")

    if not parts and not focus_titles:
        return "未提及/待补充"

    sentence = "，".join(parts)
    if sentence:
        sentence += "。"
    if focus_titles:
        sentence += f" 现阶段建议优先关注{'、'.join(focus_titles)}。"
    return sentence.strip()


def _resolve_recipient(my_party: str, other_parties: str) -> str:
    if my_party != "未提及/待补充":
        return my_party
    if other_parties != "未提及/待补充":
        return other_parties
    return "委托方"


def _resolve_opening_paragraph(
    *,
    contract_name: str,
    recipient: str,
    contract_type: str,
    party_role: str,
) -> str:
    role_text = party_role if party_role != "未提及/待补充" else "委托方"
    contract_text = f"《{contract_name}》" if contract_name != "未提及/待补充" else "相关合同文本"
    type_text = contract_type if contract_type != "未提及/待补充" else "合同"
    return (
        f"致：{recipient}\n\n"
        f"就 {recipient} 拟签署的{contract_text}，本次从 {role_text} 立场对该{type_text}进行合同审查。"
        "以下意见基于当前提供的合同文本及已识别信息形成，供签署、谈判和后续修订时参考。"
    )


def _resolve_high_risk_alerts(findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    for item in findings:
        if item.get("risk_level") not in {"P0", "P1"}:
            continue
        alerts.append(
            {
                "title": _safe_line(item.get("title") or item.get("risk")),
                "clause": _safe_line(item.get("clause") or item.get("clause_position")),
                "risk": _safe_line(item.get("risk") or item.get("description")),
                "suggestion": _safe_line(
                    item.get("suggestion") or item.get("fix") or item.get("comment")
                ),
            }
        )
        if len(alerts) >= 5:
            break
    return alerts


def render_review_report(
    plan: dict[str, Any],
    execution: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> str:
    plan_meta = plan.get("meta") if isinstance(plan.get("meta"), dict) else {}
    meta = _merge_report_meta(plan_meta, execution)
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    findings = collect_findings(plan)

    timestamp = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    contract_name = _safe_line(meta.get("contract_name") or meta.get("title"))
    project_name = _safe_line(meta.get("project_name"))
    reviewer = _safe_line(meta.get("reviewer"))
    reviewer_organization = _safe_line(
        meta.get("reviewer_organization"), fallback="未设置"
    )
    reviewer_department = _safe_line(
        meta.get("reviewer_department"), fallback="未设置"
    )
    client_name = _safe_line(meta.get("client_name"))
    party_role = _safe_line(meta.get("party_role") or meta.get("role"))
    review_intensity = _safe_line(meta.get("review_intensity"))
    contract_type = _safe_line(_resolve_meta_text(summary, meta, "contract_type"))
    contract_term = _safe_line(
        _resolve_meta_text(summary, meta, "contract_term", "term", "duration")
    )
    signing_date = _safe_line(
        _resolve_meta_text(summary, meta, "signing_date", "review_version", "version")
    )
    my_party = _resolve_my_party(summary, meta, party_role)
    other_parties = _resolve_other_parties(summary, meta, party_role)
    transaction_content = _resolve_transaction_content(
        summary=summary,
        meta=meta,
        contract_name=contract_name,
        contract_type=contract_type,
        party_role=party_role,
    )
    price_overview = _resolve_price_overview(summary, meta)
    rights_obligations = _resolve_rights_obligations(summary, meta)
    key_milestones = _resolve_key_milestones(summary, meta)
    overall = _safe_line(summary.get("overall_risk") or summary.get("risk_level"))
    conclusion = _safe_line(summary.get("core_conclusion") or summary.get("conclusion"))
    overall_opinion = _resolve_overall_opinion(
        summary=summary,
        findings=findings,
        overall=overall,
        conclusion=conclusion,
    )
    key_recommendations = _resolve_key_recommendations(summary=summary, findings=findings)
    recipient = _resolve_recipient(my_party=my_party, other_parties=other_parties)
    opening_paragraph = _resolve_opening_paragraph(
        contract_name=contract_name,
        recipient=recipient,
        contract_type=contract_type,
        party_role=party_role,
    )
    high_risk_alerts = _resolve_high_risk_alerts(findings)

    lines: list[str] = [
        f"# 关于《{contract_name}》的审查意见书",
        "",
        opening_paragraph,
        "",
        f"- 合同名称：{contract_name}",
        f"- 项目名称：{project_name}",
        f"- 客户名称：{client_name}",
        f"- 审查日期：{timestamp}",
        f"- 审查立场：{party_role}",
        f"- 审查口径：{review_intensity}",
        f"- 审查人：{reviewer}",
        f"- 所属机构/公司：{reviewer_organization}",
        f"- 所属部门：{reviewer_department}",
        "",
        "## 一、合同概况",
        "",
        "### 1. 合同主体",
        "",
        f"- 我方主体：{my_party}",
        f"- 其他签约方：{other_parties}",
        f"- 合同类型：{contract_type}",
        "",
        "### 2. 交易内容",
        "",
        f"- 交易内容：{transaction_content}",
        f"- 合同期限：{contract_term}",
        f"- 签署时间/版本：{signing_date}",
    ]

    if key_milestones:
        lines.append("- 关键时间节点：")
        for milestone in key_milestones:
            lines.append(f"  - {_safe_line(milestone)}")
    else:
        lines.append("- 关键时间节点：未提及/待补充")

    lines.extend(
        [
            "",
            "### 3. 合同价款",
            "",
            f"- 价款安排：{price_overview}",
            "",
            "### 4. 核心权利义务",
            "",
            f"- 核心权利义务：{rights_obligations}",
            "",
            "## 二、综合审查意见",
            "",
            f"- 总体风险等级：{overall}",
            f"- 核心结论：{conclusion}",
            f"- 审查意见：{overall_opinion}",
        ]
    )

    if key_recommendations:
        lines.append("- 重点处理事项：")
        for recommendation in key_recommendations:
            lines.append(f"  - {_safe_line(recommendation)}")

    lines.extend(["", "## 三、重要风险提示", ""])
    if high_risk_alerts:
        for index, alert in enumerate(high_risk_alerts, start=1):
            lines.append(f"### {index}. {alert['title']}")
            lines.append("")
            lines.append(f"- 条款位置：{alert['clause']}")
            lines.append(f"- 风险说明：{alert['risk']}")
            lines.append(f"- 修改方向：{alert['suggestion']}")
            lines.append("")
    else:
        lines.extend(["- 当前未识别出需单独前置提示的重要风险。", ""])

    lines.extend(["## 四、详细审查意见", ""])

    if not findings:
        lines.extend(["- 未识别到需要提示的具体审查问题。", ""])
    else:
        for index, item in enumerate(findings, start=1):
            title = _safe_line(item.get("title") or item.get("risk"))
            review_comment = _safe_line(
                item.get("suggestion") or item.get("fix") or item.get("comment")
            )
            target_text = _first_text(item.get("target_text"), item.get("search"))
            revision_text = _first_text(
                item.get("replacement_text"),
                item.get("recommended_text"),
                item.get("insert_text"),
            )
            lines.append(f"### {index}. {title}")
            lines.append("")
            lines.append(f"- 风险等级：{item['risk_level']}")
            lines.append(
                f"- 条款位置：{_safe_line(item.get('clause') or item.get('clause_position'))}"
            )
            lines.append(
                f"- 风险概述：{_safe_line(item.get('risk') or item.get('description'))}"
            )
            lines.append(f"- 审查意见：{review_comment}")
            if target_text:
                lines.append(f"- 原条款：{target_text}")
            if revision_text:
                lines.append(f"- 建议修改：{revision_text}")
            lines.append(f"- 法律依据：{_resolve_legal_basis(item)}")
            lines.append("")

    lines.extend(
        [
            "## 五、声明",
            "",
            "- 本意见书基于当前提供的合同文本、已识别事实和现行有效规则形成，仅供本次合同谈判、修订和签署决策时参考。",
            "- 如后续合同文本、项目事实、审批程序、对方主体信息或交易安排发生变化，本意见书内容应相应调整。",
            "- 本意见书不替代项目事实核查、主体资信核查、审批合规核查及专项法律意见。",
            "",
            "## 六、出具信息",
            "",
            f"- 审查人：{reviewer}",
            f"- 所属机构/公司：{reviewer_organization}",
            f"- 所属部门：{reviewer_department}",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="根据结构化审查计划生成 Markdown 审查意见书")
    parser.add_argument("--plan", required=True, help="审查计划 JSON 文件路径")
    parser.add_argument("--output", required=True, help="输出 Markdown 报告路径")
    parser.add_argument("--output-docx", help="可选，输出 Word 报告路径")
    parser.add_argument(
        "--execution",
        help="可选，执行日志 JSON 文件路径（用于补充本地审查人配置）",
    )
    args = parser.parse_args()

    plan = load_json(args.plan)
    execution = load_json(args.execution) if args.execution else None
    report = render_review_report(plan=plan, execution=execution)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    if args.output_docx:
        output_docx_path = Path(args.output_docx)
        output_docx_path.parent.mkdir(parents=True, exist_ok=True)
        meta = plan.get("meta") if isinstance(plan.get("meta"), dict) else {}
        write_review_report_docx(
            markdown_content=report,
            output_path=output_docx_path,
            title=str(meta.get("contract_name") or meta.get("title") or "合同审查报告"),
            author=str(meta.get("reviewer") or "合同审查助手"),
        )
    print(f"审查报告已生成: {output_path}")
    if args.output_docx:
        print(f"审查报告 DOCX 已生成: {output_docx_path}")


if __name__ == "__main__":
    main()
