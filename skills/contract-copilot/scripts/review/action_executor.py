#!/usr/bin/env python3
"""审查动作执行器。"""

from __future__ import annotations

from typing import Any

try:
    from ..docx.reviewer import ContractReviewer
except ImportError:
    from scripts.docx.reviewer import ContractReviewer


DEFAULT_TAG_BY_ACTION = {
    "comment": "w:p",
    "delete": "w:r",
    "insert": "w:p",
    "replace": "w:r",
}

ACTION_ALIASES = {
    "comment": "comment",
    "批注": "comment",
    "注释": "comment",
    "report-only": "report-only",
    "report_only": "report-only",
    "仅报告": "report-only",
    "仅写入意见书": "report-only",
    "意见书": "report-only",
    "delete": "delete",
    "删除": "delete",
    "insert": "insert",
    "插入": "insert",
    "新增": "insert",
    "replace": "replace",
    "修订": "replace",
    "修改": "replace",
    "auto": "auto",
    "自动": "auto",
}

COMMENT_HINT_FLAGS = (
    "needs_negotiation",
    "requires_negotiation",
    "needs_confirmation",
    "requires_confirmation",
    "keep_flexible",
)

REVISION_HINT_FLAGS = (
    "deterministic_edit",
    "is_typo_fix",
    "term_unification",
)

REPORT_ONLY_HINT_FLAGS = (
    "report_only",
    "opinion_only",
    "advice_only",
)

COMMENT_HINT_KEYWORDS = (
    "谈判",
    "协商",
    "待确认",
    "需确认",
    "待补充",
    "可考虑",
    "视情况",
    "保留弹性",
)

REVISION_HINT_KEYWORDS = (
    "笔误",
    "错别字",
    "术语统一",
    "表述统一",
    "更正为",
    "应为",
    "删除重复",
    "格式统一",
)

REPORT_ONLY_HINT_KEYWORDS = (
    "仅写入意见书",
    "仅在意见书中提示",
    "仅作报告提示",
    "不直接修改正文",
)

PLACEHOLDER_HINT_KEYWORDS = (
    "待填写",
    "待补",
    "待补充",
    "留空",
    "空白",
    "未填写",
    "负责人",
    "联系方式",
    "邮箱",
    "电子邮箱",
    "附件",
)

CLERICAL_HINT_KEYWORDS = (
    "笔误",
    "错别字",
    "术语统一",
    "表述统一",
    "格式统一",
    "标点",
    "编号",
    "日期表述",
    "天内",
    "日内",
    "权力",
    "权利",
)

SOFT_OPTIMIZATION_HINT_KEYWORDS = (
    "宜调整",
    "需明确",
    "需覆盖",
    "应明确",
    "需写明",
    "交付物需写明",
    "确认机制",
    "挂钩",
    "脱钩",
    "生效标准",
    "管辖",
    "签订地",
    "建议明确",
    "建议补充",
    "需补充",
    "需具体化",
    "明确生效规则",
    "建议调整",
    "建议改为",
    "可考虑",
)

STRUCTURAL_CONFLICT_HINT_KEYWORDS = (
    "冲突",
    "矛盾",
    "逻辑颠倒",
    "前后不一致",
    "不一致",
    "无法执行",
    "不可执行",
    "影响项目实施",
    "妨碍本项目落地",
    "妨碍项目实施",
    "阻碍项目实施",
    "直接妨碍",
    "与委托目的冲突",
    "项目实施需求不匹配",
    "项目使用权",
)

SUPPORTED_ACTIONS = {
    "comment",
    "report-only",
    "delete",
    "insert",
    "replace",
    "none",
    "skip",
    "auto",
}
EDIT_POLICIES = {"comment-first", "balanced", "revise-first"}
DIRECT_EDIT_ACTIONS = {"delete", "insert", "replace"}


def normalize_action(action: Any, default: str = "comment") -> str:
    raw = str(action or "").strip()
    if not raw:
        return default
    normalized = raw.lower()
    return ACTION_ALIASES.get(normalized) or ACTION_ALIASES.get(raw) or normalized


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
    haystack = " ".join(
        str(finding.get(field) or "")
        for field in ("title", "risk", "description", "suggestion", "comment", "reason")
    )
    return any(keyword in haystack for keyword in keywords)


def _risk_level(finding: dict[str, Any]) -> str:
    return str(finding.get("risk_level") or "P2").upper().strip()


def _looks_like_placeholder_finding(finding: dict[str, Any]) -> bool:
    descriptive_haystack = " ".join(
        str(finding.get(field) or "")
        for field in (
            "title",
            "risk",
            "description",
            "suggestion",
            "comment",
            "reason",
        )
    )
    target_haystack = " ".join(
        str(finding.get(field) or "") for field in ("target_text", "search")
    )
    full_haystack = f"{descriptive_haystack} {target_haystack}"
    if "____" in full_haystack or "【" in full_haystack or "】" in full_haystack:
        return True
    return any(keyword in descriptive_haystack for keyword in PLACEHOLDER_HINT_KEYWORDS)


def _is_minor_clerical_finding(finding: dict[str, Any]) -> bool:
    if any(_is_truthy(finding.get(flag)) for flag in ("is_typo_fix", "term_unification")):
        return True
    if not _contains_keywords(finding, CLERICAL_HINT_KEYWORDS):
        return False
    target_text = str(finding.get("target_text") or finding.get("search") or "")
    replacement_text = resolve_replacement_text(finding, edit_policy="revise-first") or ""
    longest = max(len(target_text), len(replacement_text))
    return longest <= 40


def _has_explicit_direct_edit_authorization(finding: dict[str, Any]) -> bool:
    return any(
        _is_truthy(finding.get(flag))
        for flag in ("force_edit", "direct_edit", "allow_substantive_rewrite")
    )


def _looks_like_soft_optimization_finding(finding: dict[str, Any]) -> bool:
    return _contains_keywords(finding, SOFT_OPTIMIZATION_HINT_KEYWORDS)


def _looks_like_structural_conflict_finding(finding: dict[str, Any]) -> bool:
    return _contains_keywords(finding, STRUCTURAL_CONFLICT_HINT_KEYWORDS)


def _is_substantive_direct_rewrite(
    finding: dict[str, Any],
    *,
    edit_policy: str,
) -> bool:
    if _is_minor_clerical_finding(finding):
        return False
    target_text = str(finding.get("target_text") or finding.get("search") or "")
    replacement_text = resolve_replacement_text(finding, edit_policy=edit_policy) or ""
    if not target_text and not replacement_text:
        return False
    longest = max(len(target_text), len(replacement_text))
    length_gap = abs(len(target_text) - len(replacement_text))
    if longest >= 80 or length_gap >= 25:
        return True
    if _contains_keywords(finding, COMMENT_HINT_KEYWORDS):
        return True
    has_substantive_reason = bool(
        str(finding.get("risk") or finding.get("description") or "").strip()
        or str(finding.get("suggestion") or finding.get("fix") or "").strip()
    )
    return has_substantive_reason and longest >= 40


def resolve_replacement_text(
    finding: dict[str, Any],
    *,
    edit_policy: str = "revise-first",
) -> str | None:
    replacement_text = finding.get("replacement_text")
    if replacement_text is not None:
        return str(replacement_text)

    policy = normalize_edit_policy(edit_policy)
    if policy != "revise-first":
        return None

    recommended_text = str(finding.get("recommended_text") or "").strip()
    return recommended_text or None


def infer_revision_action(
    finding: dict[str, Any],
    *,
    strict: bool = False,
    edit_policy: str = "revise-first",
) -> str:
    policy = normalize_edit_policy(edit_policy)
    explicit = normalize_action(
        finding.get("edit_type")
        or finding.get("preferred_action")
        or finding.get("suggested_action"),
        default="",
    )
    if explicit in {"delete", "insert"}:
        return explicit

    replacement_text = resolve_replacement_text(finding, edit_policy=policy)
    insert_text = finding.get("insert_text")

    if _is_truthy(finding.get("delete")) or _is_truthy(finding.get("remove")):
        return "delete"
    if insert_text is not None:
        return "insert"
    if replacement_text is not None:
        if isinstance(replacement_text, str) and replacement_text == "":
            return "delete"
        return "replace"

    if explicit == "replace":
        return "replace" if strict else "comment"

    return "comment"


def infer_auto_action(
    finding: dict[str, Any],
    *,
    edit_policy: str = "revise-first",
) -> str:
    policy = normalize_edit_policy(edit_policy)
    if any(_is_truthy(finding.get(flag)) for flag in REPORT_ONLY_HINT_FLAGS):
        return "report-only"
    if _contains_keywords(finding, REPORT_ONLY_HINT_KEYWORDS):
        return "report-only"
    if _looks_like_placeholder_finding(finding):
        return "comment"
    if any(_is_truthy(finding.get(flag)) for flag in COMMENT_HINT_FLAGS):
        return "comment"
    if _contains_keywords(finding, COMMENT_HINT_KEYWORDS):
        return "comment"

    if any(_is_truthy(finding.get(flag)) for flag in REVISION_HINT_FLAGS):
        return infer_revision_action(finding, strict=False, edit_policy=policy)
    if _contains_keywords(finding, REVISION_HINT_KEYWORDS):
        return infer_revision_action(finding, strict=False, edit_policy=policy)

    if (
        resolve_replacement_text(finding, edit_policy=policy) is not None
        or finding.get("insert_text") is not None
        or _is_truthy(finding.get("delete"))
        or _is_truthy(finding.get("remove"))
    ):
        return infer_revision_action(finding, strict=False, edit_policy=policy)

    return "comment"


def resolve_delivery_action(
    finding: dict[str, Any],
    *,
    requested_action: str,
    action: str,
    edit_policy: str,
) -> str:
    if action in {"none", "skip", "comment", "report-only"}:
        return action
    if any(_is_truthy(finding.get(flag)) for flag in REPORT_ONLY_HINT_FLAGS):
        return "report-only"
    if _contains_keywords(finding, REPORT_ONLY_HINT_KEYWORDS):
        return "report-only"
    if should_downgrade_direct_edit_to_comment(
        finding,
        requested_action=requested_action,
    ):
        return "comment"
    if _has_explicit_direct_edit_authorization(finding):
        return action
    if _is_minor_clerical_finding(finding):
        return action
    if any(_is_truthy(finding.get(flag)) for flag in ("is_typo_fix", "term_unification")):
        return action
    if _is_truthy(finding.get("deterministic_edit")) and requested_action == "auto":
        return action
    if _looks_like_structural_conflict_finding(finding):
        return action
    if any(_is_truthy(finding.get(flag)) for flag in COMMENT_HINT_FLAGS):
        return "comment"
    if _contains_keywords(finding, COMMENT_HINT_KEYWORDS):
        return "comment"

    risk_level = _risk_level(finding)
    if risk_level == "P2" and _is_substantive_direct_rewrite(finding, edit_policy=edit_policy):
        return "report-only"
    if _looks_like_soft_optimization_finding(finding):
        return "comment" if risk_level == "P0" else "report-only"
    if _is_substantive_direct_rewrite(finding, edit_policy=edit_policy):
        return "comment"
    return action


def should_downgrade_direct_edit_to_comment(
    finding: dict[str, Any],
    *,
    requested_action: str,
) -> bool:
    if requested_action not in DIRECT_EDIT_ACTIONS:
        return False
    if _is_truthy(finding.get("force_edit")) or _is_truthy(
        finding.get("allow_placeholder_fill")
    ):
        return False
    return _looks_like_placeholder_finding(finding)


def resolve_action_tag(finding: dict[str, Any], action: str) -> str:
    selector = finding.get("selector")
    if isinstance(selector, dict) and selector.get("tag"):
        return str(selector["tag"])
    return str(finding.get("tag") or DEFAULT_TAG_BY_ACTION.get(action, "w:p"))


def resolve_occurrence(finding: dict[str, Any]) -> int | None:
    selector = finding.get("selector")
    raw = None
    if isinstance(selector, dict) and selector.get("occurrence") is not None:
        raw = selector.get("occurrence")
    elif finding.get("occurrence") is not None:
        raw = finding.get("occurrence")

    if raw is None:
        return None

    value = int(raw)
    if value < 1:
        raise ValueError("occurrence 必须从 1 开始")
    return value


def resolve_node(reviewer: ContractReviewer, finding: dict[str, Any], action: str):
    selector = finding.get("selector")
    occurrence = resolve_occurrence(finding)
    if isinstance(selector, dict):
        tag = resolve_action_tag(finding, action)
        attrs = selector.get("attrs")
        line_number = selector.get("line_number")
        contains = selector.get("contains")
        if line_number is not None and not isinstance(line_number, range):
            if isinstance(line_number, list) and len(line_number) == 2:
                start, end = line_number
                line_number = range(int(start), int(end) + 1)
            elif isinstance(line_number, int):
                line_number = int(line_number)
        return reviewer.find_node(
            tag=tag,
            attrs=attrs if isinstance(attrs, dict) else None,
            line_number=line_number,
            contains=str(contains) if contains is not None else None,
            occurrence=occurrence,
        )

    target_text = finding.get("target_text") or finding.get("search")
    tag = resolve_action_tag(finding, action)
    if not target_text:
        raise ValueError(f"action={action} 缺少 target_text 或 selector")
    return reviewer.find_text(str(target_text), tag=tag, occurrence=occurrence)


def build_comment_text(finding: dict[str, Any]) -> str:
    risk_level = str(finding.get("risk_level") or "P2").upper()
    title = str(finding.get("title") or finding.get("risk") or "风险提示").strip()
    risk = str(finding.get("risk") or finding.get("description") or "未提及/待补充").strip()
    suggestion = str(finding.get("suggestion") or finding.get("fix") or "未提及/待补充").strip()
    recommended_text = str(finding.get("recommended_text") or "").strip()
    clause = str(finding.get("clause") or finding.get("clause_position") or "").strip()

    lines = [
        f"【风险等级】{risk_level}",
        f"【风险点】{title}",
    ]
    if clause:
        lines.append(f"【条款位置】{clause}")
    lines.extend(
        [
            f"【说明】{risk}",
            f"【修改建议】{suggestion}",
        ]
    )
    if recommended_text and recommended_text != suggestion:
        lines.append(f"【建议措辞】{recommended_text}")
    return "\n".join(lines)


def resolve_revision_comment(
    finding: dict[str, Any],
    *,
    action: str,
    requested_action: str,
) -> str | None:
    explicit = str(finding.get("comment") or "").strip()
    if explicit:
        return explicit
    if _is_truthy(finding.get("suppress_comment_on_revision")):
        return None
    if _looks_like_placeholder_finding(finding):
        return build_comment_text(finding)
    if action not in {"delete", "insert", "replace"}:
        return None
    if _is_minor_clerical_finding(finding):
        return None

    risk_level = str(finding.get("risk_level") or "P2").upper().strip()
    has_substantive_reason = bool(
        str(finding.get("risk") or finding.get("description") or "").strip()
        or str(finding.get("suggestion") or finding.get("fix") or "").strip()
    )
    if _is_truthy(finding.get("keep_comment_on_revision")):
        return build_comment_text(finding)
    if requested_action == "auto" and has_substantive_reason:
        return build_comment_text(finding)
    if risk_level in {"P0", "P1"} and has_substantive_reason:
        return build_comment_text(finding)
    return None


def apply_finding(
    reviewer: ContractReviewer,
    finding: dict[str, Any],
    *,
    edit_policy: str = "revise-first",
) -> dict[str, Any]:
    policy = normalize_edit_policy(edit_policy)
    requested_action = normalize_action(finding.get("action"), default="comment")
    action = (
        infer_auto_action(finding, edit_policy=policy)
        if requested_action == "auto"
        else requested_action
    )
    action = resolve_delivery_action(
        finding,
        requested_action=requested_action,
        action=action,
        edit_policy=policy,
    )
    if action not in SUPPORTED_ACTIONS:
        raise ValueError(f"不支持的 action: {requested_action}")

    result: dict[str, Any] = {
        "id": finding.get("id"),
        "action": action,
        "requested_action": requested_action,
        "status": "skipped",
        "message": "",
    }

    if action in {"none", "skip"}:
        result["message"] = "按计划跳过"
        return result
    if action == "report-only":
        result["status"] = "report_only"
        result["message"] = "仅写入审查意见书，不写入 Word 正文"
        return result

    tag = resolve_action_tag(finding, action)

    if action == "comment":
        node = resolve_node(reviewer, finding, action)
        reviewer.add_comment(node, finding.get("comment") or build_comment_text(finding))
        result["status"] = "applied"
        result["message"] = "已添加批注"
        return result

    if action == "delete":
        comment = resolve_revision_comment(
            finding,
            action=action,
            requested_action=requested_action,
        )
        target_text = finding.get("target_text") or finding.get("search")
        if target_text:
            delete_result = reviewer.delete_text(
                target_text=str(target_text),
                tag=tag,
                comment_text=comment,
                occurrence=resolve_occurrence(finding),
            )
            fallback = delete_result.get("fallback")
            if fallback == "paragraph_rewrite":
                result["message"] = "已按段落级重写删除文本"
            elif fallback in {"run_fragment", "paragraph_fragment"}:
                result["message"] = "已完成局部删除"
            else:
                result["message"] = "已标记删除"
        else:
            node = resolve_node(reviewer, finding, action)
            reviewer.suggest_deletion(node)
            if comment:
                reviewer.add_comment(node, comment)
            result["message"] = "已标记删除"
        if comment:
            result["message"] += "并添加批注"
        result["status"] = "applied"
        return result

    if action == "insert":
        node = resolve_node(reviewer, finding, action)
        new_text = finding.get("replacement_text") or finding.get("insert_text")
        if not new_text:
            raise ValueError("insert 缺少 replacement_text/insert_text")
        inserted = reviewer.insert_text_after(node, str(new_text), as_paragraph=(tag == "w:p"))
        comment = resolve_revision_comment(
            finding,
            action=action,
            requested_action=requested_action,
        )
        if comment and inserted:
            reviewer.add_comment(inserted[0], comment)
        result["status"] = "applied"
        result["message"] = "已插入文本"
        if comment:
            result["message"] += "并添加批注"
        return result

    if action == "replace":
        target_text = finding.get("target_text") or finding.get("search")
        replacement_text = resolve_replacement_text(finding, edit_policy=policy)
        if replacement_text is None:
            raise ValueError("replace 缺少 replacement_text")
        occurrence = resolve_occurrence(finding)
        comment = resolve_revision_comment(
            finding,
            action=action,
            requested_action=requested_action,
        )
        if target_text:
            replace_result = reviewer.replace_text(
                old_text=str(target_text),
                new_text=str(replacement_text),
                tag=tag,
                comment_text=comment,
                occurrence=occurrence,
            )
            fallback = replace_result.get("fallback") if isinstance(replace_result, dict) else None
            if fallback == "paragraph_rewrite":
                result["message"] = "已按段落级重写替换文本"
            elif fallback in {"run_fragment", "paragraph_fragment"}:
                result["message"] = "已完成局部替换"
            else:
                result["message"] = "已完成替换"
        else:
            node = resolve_node(reviewer, finding, action)
            reviewer.replace_node(
                node=node,
                new_text=str(replacement_text),
                tag=tag,
                comment_text=comment,
            )
            result["message"] = "已完成节点替换"
        if comment:
            result["message"] += "并添加批注"
        result["status"] = "applied"
        return result

    raise ValueError(f"不支持的 action: {action}")
