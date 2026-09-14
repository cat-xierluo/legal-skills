#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""涵摄式检索计划与 Agent 精选来源的确定性合同校验。"""

import json
from pathlib import Path


SCHEMA_VERSION = "1.0"
FACT_STATUSES = {"established", "alleged", "disputed", "missing"}
PROOF_STATUSES = {"sufficient", "weak", "none", "unknown"}
SUBSUMPTION_STATUSES = {"satisfied", "not_satisfied", "uncertain"}
RESOLUTION_PATHS = {"legal_research", "fact_supplement", "evidence_review", "none"}
PROPOSITION_DIRECTIONS = {"support", "oppose"}
PROPOSITION_TYPES = {"normative", "fact-structure", "adjudication-rule", "reverse"}
IMPORTANCE_LEVELS = {"decisive", "supportive"}
RELEVANCE_LABELS = {"HIGH", "MEDIUM"}
PRIORITY_LEVELS = {"core", "supplementary"}
SOURCE_TYPES = {
    "constitution",
    "law",
    "judicial_interpretation",
    "administrative_regulation",
    "local_regulation",
    "department_rule",
    "guiding_case",
    "typical_case",
    "case",
    "other",
}
NORMATIVE_SOURCE_TYPES = {
    "constitution",
    "law",
    "judicial_interpretation",
    "administrative_regulation",
    "local_regulation",
    "department_rule",
}
CASE_SOURCE_TYPES = {"guiding_case", "typical_case", "case"}
VALIDITY_STATUSES = {"current", "historical", "not_applicable"}
MAX_SELECTED_SOURCES = 12

SOURCE_TYPE_LABELS = {
    "constitution": "宪法",
    "law": "法律",
    "judicial_interpretation": "司法解释",
    "administrative_regulation": "行政法规",
    "local_regulation": "地方性法规",
    "department_rule": "部门规章",
    "guiding_case": "指导性案例",
    "typical_case": "典型案例",
    "case": "司法案例",
    "other": "其他核实材料",
}
SOURCE_TYPE_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "constitution",
            "law",
            "judicial_interpretation",
            "administrative_regulation",
            "local_regulation",
            "department_rule",
            "guiding_case",
            "typical_case",
            "case",
            "other",
        )
    )
}
PRIORITY_LABELS = {"core": "核心", "supplementary": "补充"}
STANCE_LABELS = {"support": "支持", "oppose": "反向", "mixed": "双向"}
VALIDITY_LABELS = {
    "current": "现行有效",
    "historical": "历史法源（仅背景）",
    "not_applicable": "不适用（案例／其他材料）",
}


class ContractInputError(ValueError):
    """合同文件无法读取或不是 JSON 对象。"""


def load_json_object(path, label="合同"):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ContractInputError(f"无法读取{label}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ContractInputError(f"{label}不是合法 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractInputError(f"{label}顶层必须是 JSON 对象")
    return value


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _string_list(value):
    return isinstance(value, list) and bool(value) and all(_text(item) for item in value)


def _error(path, message):
    return {"path": path, "msg": message}


def _require_text(errors, obj, key, path):
    if not _text(obj.get(key)):
        errors.append(_error(f"{path}.{key}", "必须是非空字符串"))


def _require_enum(errors, obj, key, allowed, path):
    value = obj.get(key)
    if value not in allowed:
        errors.append(_error(f"{path}.{key}", f"必须是 {sorted(allowed)} 之一"))


def validate_research_plan(plan):
    """校验涵摄式 research plan；返回问题列表，空列表表示结构有效。"""
    errors = []
    if not isinstance(plan, dict):
        return [_error("$", "顶层必须是 JSON 对象")]
    if plan.get("schema_version") != SCHEMA_VERSION:
        errors.append(_error("$.schema_version", f"必须为 {SCHEMA_VERSION}"))
    _require_text(errors, plan, "case_id", "$")

    brief = plan.get("research_brief")
    if not isinstance(brief, dict):
        errors.append(_error("$.research_brief", "必须是对象"))
    else:
        for key in ("research_goal", "procedure_stage"):
            _require_text(errors, brief, key, "$.research_brief")
        party_stance = brief.get("party_stance")
        if not isinstance(party_stance, dict):
            errors.append(_error("$.research_brief.party_stance", "必须是对象"))
        else:
            for key in ("role", "claim_or_defense"):
                _require_text(errors, party_stance, key, "$.research_brief.party_stance")
        for key in ("dispute_focus", "decisive_facts", "must_exclude_neighbor_types"):
            if not _string_list(brief.get(key)):
                errors.append(_error(f"$.research_brief.{key}", "必须是非空字符串数组"))

    issues = plan.get("issues")
    if not isinstance(issues, list) or not issues:
        errors.append(_error("$.issues", "必须是非空数组"))
        issues = []

    issue_ids = set()
    element_ids = set()
    gaps = {}
    decisive_issue_ids = set()
    for issue_index, issue in enumerate(issues):
        path = f"$.issues[{issue_index}]"
        if not isinstance(issue, dict):
            errors.append(_error(path, "必须是对象"))
            continue
        for key in ("id", "question", "claim_or_defense_basis", "provisional_conclusion"):
            _require_text(errors, issue, key, path)
        issue_id = issue.get("id")
        if _text(issue_id):
            if issue_id in issue_ids:
                errors.append(_error(f"{path}.id", "issue id 重复"))
            issue_ids.add(issue_id)
        _require_enum(errors, issue, "importance", IMPORTANCE_LEVELS, path)
        if issue.get("importance") == "decisive" and _text(issue_id):
            decisive_issue_ids.add(issue_id)

        premise = issue.get("major_premise")
        if not isinstance(premise, dict):
            errors.append(_error(f"{path}.major_premise", "必须是对象"))
        else:
            for key in ("candidate_rule", "applicability", "legal_consequence"):
                _require_text(errors, premise, key, f"{path}.major_premise")
            if not _string_list(premise.get("elements")):
                errors.append(_error(f"{path}.major_premise.elements", "必须是非空字符串数组"))
            if not isinstance(premise.get("exceptions"), list):
                errors.append(_error(f"{path}.major_premise.exceptions", "必须是数组，可为空"))

        matrix = issue.get("element_matrix")
        if not isinstance(matrix, list) or not matrix:
            errors.append(_error(f"{path}.element_matrix", "必须是非空数组"))
            continue
        for row_index, row in enumerate(matrix):
            row_path = f"{path}.element_matrix[{row_index}]"
            if not isinstance(row, dict):
                errors.append(_error(row_path, "必须是对象"))
                continue
            for key in ("id", "element", "opposing_path"):
                _require_text(errors, row, key, row_path)
            element_id = row.get("id")
            if _text(element_id):
                if element_id in element_ids:
                    errors.append(_error(f"{row_path}.id", "element id 重复"))
                element_ids.add(element_id)
            facts = row.get("facts")
            if not isinstance(facts, list) or not all(_text(item) for item in facts):
                errors.append(_error(f"{row_path}.facts", "必须是字符串数组；事实缺失时可为空数组"))
            _require_enum(errors, row, "fact_status", FACT_STATUSES, row_path)
            _require_enum(errors, row, "proof_status", PROOF_STATUSES, row_path)
            _require_enum(errors, row, "provisional_subsumption", SUBSUMPTION_STATUSES, row_path)
            if isinstance(facts, list):
                if not facts and row.get("fact_status") != "missing":
                    errors.append(_error(row_path, "facts 为空时 fact_status 必须为 missing"))
                if facts and row.get("fact_status") == "missing":
                    errors.append(_error(row_path, "fact_status=missing 时 facts 必须为空"))

            gap = row.get("research_gap")
            if gap is None:
                if row.get("provisional_subsumption") == "uncertain":
                    errors.append(_error(f"{row_path}.research_gap", "暂定涵摄为 uncertain 时必须声明解决路径"))
                continue
            if not isinstance(gap, dict):
                errors.append(_error(f"{row_path}.research_gap", "必须是对象或 null"))
                continue
            for key in ("id", "question"):
                _require_text(errors, gap, key, f"{row_path}.research_gap")
            _require_enum(errors, gap, "resolution_path", RESOLUTION_PATHS, f"{row_path}.research_gap")
            gap_id = gap.get("id")
            if _text(gap_id):
                if gap_id in gaps:
                    errors.append(_error(f"{row_path}.research_gap.id", "research gap id 重复"))
                gaps[gap_id] = {
                    "issue_id": issue_id,
                    "element_id": element_id,
                    "resolution_path": gap.get("resolution_path"),
                }
            source_types = gap.get("required_source_types")
            if gap.get("resolution_path") == "legal_research":
                if not _string_list(source_types):
                    errors.append(
                        _error(
                            f"{row_path}.research_gap.required_source_types",
                            "legal_research 缺口必须声明非空法源类型数组",
                        )
                    )
            elif source_types not in (None, []):
                errors.append(
                    _error(
                        f"{row_path}.research_gap.required_source_types",
                        "非 legal_research 缺口不得生成法源需求",
                    )
                )

    propositions = plan.get("propositions")
    if not isinstance(propositions, list) or not propositions:
        errors.append(_error("$.propositions", "必须是非空数组"))
        propositions = []
    proposition_ids = set()
    proposition_map = {}
    directions_by_issue = {}
    gap_propositions = {}
    for index, proposition in enumerate(propositions):
        path = f"$.propositions[{index}]"
        if not isinstance(proposition, dict):
            errors.append(_error(path, "必须是对象"))
            continue
        for key in ("id", "issue_id", "element_id", "research_gap_id", "statement"):
            _require_text(errors, proposition, key, path)
        prop_id = proposition.get("id")
        if _text(prop_id):
            if prop_id in proposition_ids:
                errors.append(_error(f"{path}.id", "proposition id 重复"))
            proposition_ids.add(prop_id)
            proposition_map[prop_id] = proposition
        issue_id = proposition.get("issue_id")
        element_id = proposition.get("element_id")
        gap_id = proposition.get("research_gap_id")
        if issue_id not in issue_ids:
            errors.append(_error(f"{path}.issue_id", "未指向已声明 issue"))
        if element_id not in element_ids:
            errors.append(_error(f"{path}.element_id", "未指向已声明 element"))
        gap_meta = gaps.get(gap_id)
        if not gap_meta:
            errors.append(_error(f"{path}.research_gap_id", "未指向已声明 research gap"))
        else:
            if gap_meta["resolution_path"] != "legal_research":
                errors.append(_error(f"{path}.research_gap_id", "只有 legal_research 缺口可以派生检索命题"))
            if gap_meta["issue_id"] != issue_id or gap_meta["element_id"] != element_id:
                errors.append(_error(path, "命题与 research gap 的 issue/element 映射不一致"))
            gap_propositions.setdefault(gap_id, set()).add(prop_id)
        _require_enum(errors, proposition, "direction", PROPOSITION_DIRECTIONS, path)
        _require_enum(errors, proposition, "type", PROPOSITION_TYPES, path)
        _require_enum(errors, proposition, "importance", IMPORTANCE_LEVELS, path)
        if issue_id in decisive_issue_ids and proposition.get("direction") in PROPOSITION_DIRECTIONS:
            directions_by_issue.setdefault(issue_id, set()).add(proposition.get("direction"))

    for issue_id in decisive_issue_ids:
        missing = PROPOSITION_DIRECTIONS - directions_by_issue.get(issue_id, set())
        if missing:
            errors.append(_error("$.propositions", f"决定性争点 {issue_id} 缺少正反命题: {sorted(missing)}"))

    queries = plan.get("queries")
    if not isinstance(queries, list) or not queries:
        errors.append(_error("$.queries", "必须是非空数组"))
        queries = []
    query_ids = set()
    query_map = {}
    gap_queries = {}
    proposition_queries = {}
    for index, query in enumerate(queries):
        path = f"$.queries[{index}]"
        if not isinstance(query, dict):
            errors.append(_error(path, "必须是对象"))
            continue
        for key in (
            "id",
            "proposition_id",
            "research_gap_id",
            "interface",
            "routing_rationale",
            "query_field",
            "query_expression",
            "expected_hit",
            "fallback_path",
        ):
            _require_text(errors, query, key, path)
        query_id = query.get("id")
        if _text(query_id):
            if query_id in query_ids:
                errors.append(_error(f"{path}.id", "query id 重复"))
            query_ids.add(query_id)
            query_map[query_id] = query
        prop_id = query.get("proposition_id")
        gap_id = query.get("research_gap_id")
        proposition = proposition_map.get(prop_id)
        if proposition is None:
            errors.append(_error(f"{path}.proposition_id", "未指向已声明 proposition"))
        elif proposition.get("research_gap_id") != gap_id:
            errors.append(_error(path, "query 与 proposition 的 research_gap_id 不一致"))
        else:
            proposition_queries.setdefault(prop_id, set()).add(query_id)
        gap_meta = gaps.get(gap_id)
        if not gap_meta or gap_meta.get("resolution_path") != "legal_research":
            errors.append(_error(f"{path}.research_gap_id", "query 只能指向 legal_research 缺口"))
        else:
            gap_queries.setdefault(gap_id, set()).add(query_id)
        if not isinstance(query.get("filters"), dict):
            errors.append(_error(f"{path}.filters", "必须是对象，可为空"))
        if not isinstance(query.get("allow_rewrite"), bool):
            errors.append(_error(f"{path}.allow_rewrite", "必须是布尔值"))
        if not _string_list(query.get("exclusion_criteria")):
            errors.append(_error(f"{path}.exclusion_criteria", "必须是非空字符串数组"))

    for gap_id, gap_meta in gaps.items():
        if gap_meta["resolution_path"] != "legal_research":
            if gap_id in gap_propositions or gap_id in gap_queries:
                errors.append(_error(f"research_gap:{gap_id}", "非法律检索缺口不得派生命题或查询"))
            continue
        if not gap_propositions.get(gap_id):
            errors.append(_error(f"research_gap:{gap_id}", "legal_research 缺口未派生检索命题"))
        if not gap_queries.get(gap_id):
            errors.append(_error(f"research_gap:{gap_id}", "legal_research 缺口未派生查询"))

    for prop_id in proposition_ids:
        if not proposition_queries.get(prop_id):
            errors.append(_error(f"proposition:{prop_id}", "检索命题未派生任何 query"))

    return errors


def validate_selected_sources(selection, plan):
    """校验 Agent 精选清单及其与 research plan 的映射。"""
    errors = []
    if not isinstance(selection, dict):
        return [_error("$", "顶层必须是 JSON 对象")]
    if selection.get("schema_version") != SCHEMA_VERSION:
        errors.append(_error("$.schema_version", f"必须为 {SCHEMA_VERSION}"))
    if selection.get("case_id") != plan.get("case_id"):
        errors.append(_error("$.case_id", "必须与 research plan 的 case_id 一致"))

    propositions = {
        item.get("id"): item
        for item in plan.get("propositions", [])
        if isinstance(item, dict) and _text(item.get("id"))
    }
    queries = {
        item.get("id"): item
        for item in plan.get("queries", [])
        if isinstance(item, dict) and _text(item.get("id"))
    }
    decisive_ids = {
        prop_id
        for prop_id, item in propositions.items()
        if item.get("importance") == "decisive"
    }

    sources = selection.get("selected_sources")
    if not isinstance(sources, list) or not sources:
        errors.append(_error("$.selected_sources", "正式报告必须包含至少一条 Agent 精选来源"))
        sources = []
    elif len(sources) > MAX_SELECTED_SOURCES:
        errors.append(
            _error(
                "$.selected_sources",
                f"正式报告最多纳入 {MAX_SELECTED_SOURCES} 条精选来源；"
                "请去重、保留最高位阶／最对位依据，或拆分为专题附件",
            )
        )
    source_ids = set()
    normalized_citations = set()
    covered_propositions = set()
    for index, source in enumerate(sources):
        path = f"$.selected_sources[{index}]"
        if not isinstance(source, dict):
            errors.append(_error(path, "必须是对象"))
            continue
        for key in (
            "source_id",
            "title",
            "citation",
            "rule_or_holding",
            "applicability",
            "verification_note",
        ):
            _require_text(errors, source, key, path)
        source_id = source.get("source_id")
        if _text(source_id):
            if source_id in source_ids:
                errors.append(_error(f"{path}.source_id", "source id 重复"))
            source_ids.add(source_id)
        citation = source.get("citation")
        if _text(citation):
            normalized = "".join(citation.split()).lower()
            if normalized in normalized_citations:
                errors.append(_error(f"{path}.citation", "citation 重复；应先去重"))
            normalized_citations.add(normalized)
        _require_enum(errors, source, "source_type", SOURCE_TYPES, path)
        _require_enum(errors, source, "relevance_label", RELEVANCE_LABELS, path)
        _require_enum(errors, source, "priority", PRIORITY_LEVELS, path)
        _require_enum(errors, source, "stance", {"support", "oppose", "mixed"}, path)
        _require_enum(errors, source, "validity_status", VALIDITY_STATUSES, path)
        if source.get("verification_status") != "verified":
            errors.append(_error(f"{path}.verification_status", "正式报告只允许 verified 来源"))
        if source.get("priority") == "core" and source.get("relevance_label") != "HIGH":
            errors.append(_error(path, "core 依据必须为 HIGH；MEDIUM 只能作 supplementary"))
        source_type = source.get("source_type")
        validity = source.get("validity_status")
        if source_type in NORMATIVE_SOURCE_TYPES and validity not in {"current", "historical"}:
            errors.append(_error(f"{path}.validity_status", "规范性法源必须标记 current 或 historical"))
        if source_type in CASE_SOURCE_TYPES and validity != "not_applicable":
            errors.append(_error(f"{path}.validity_status", "案例的 validity_status 必须为 not_applicable"))
        if validity == "historical" and source.get("priority") == "core":
            errors.append(_error(path, "历史法源不得作为 core 依据"))

        prop_ids = source.get("proposition_ids")
        if not _string_list(prop_ids):
            errors.append(_error(f"{path}.proposition_ids", "必须是非空字符串数组"))
            prop_ids = []
        elif len(prop_ids) != len(set(prop_ids)):
            errors.append(_error(f"{path}.proposition_ids", "不得包含重复 proposition id"))
        for prop_id in prop_ids:
            if prop_id not in propositions:
                errors.append(_error(f"{path}.proposition_ids", f"未知 proposition: {prop_id}"))
            else:
                covered_propositions.add(prop_id)

        trace = source.get("trace")
        if not isinstance(trace, dict):
            errors.append(_error(f"{path}.trace", "必须是对象"))
            continue
        query_ids = trace.get("query_ids")
        if not _string_list(query_ids):
            errors.append(_error(f"{path}.trace.query_ids", "必须是非空字符串数组"))
            query_ids = []
        elif len(query_ids) != len(set(query_ids)):
            errors.append(_error(f"{path}.trace.query_ids", "不得包含重复 query id"))
        for query_id in query_ids:
            query = queries.get(query_id)
            if query is None:
                errors.append(_error(f"{path}.trace.query_ids", f"未知 query: {query_id}"))
                continue
            if query.get("proposition_id") not in prop_ids:
                errors.append(_error(path, f"query {query_id} 未映射到本来源的 proposition_ids"))
        if not _text(trace.get("source_url")) and not _text(trace.get("archive_ref")):
            errors.append(_error(f"{path}.trace", "source_url 与 archive_ref 至少提供一项"))

    unresolved = selection.get("unresolved_propositions", [])
    if not isinstance(unresolved, list):
        errors.append(_error("$.unresolved_propositions", "必须是数组，可为空"))
        unresolved = []
    unresolved_ids = set()
    for index, item in enumerate(unresolved):
        path = f"$.unresolved_propositions[{index}]"
        if not isinstance(item, dict):
            errors.append(_error(path, "必须是对象"))
            continue
        for key in ("proposition_id", "reason", "next_action"):
            _require_text(errors, item, key, path)
        prop_id = item.get("proposition_id")
        if prop_id not in propositions:
            errors.append(_error(f"{path}.proposition_id", "未知 proposition"))
        if prop_id in unresolved_ids:
            errors.append(_error(f"{path}.proposition_id", "重复的 unresolved proposition"))
        unresolved_ids.add(prop_id)
        if prop_id in covered_propositions:
            errors.append(_error(path, "同一 proposition 不得同时有精选来源又标记 unresolved"))

    missing_decisive = decisive_ids - covered_propositions - unresolved_ids
    if missing_decisive:
        errors.append(
            _error(
                "$.selected_sources",
                f"决定性命题既无精选来源也未显式标记 unresolved: {sorted(missing_decisive)}",
            )
        )

    excluded = selection.get("excluded_candidates", [])
    if not isinstance(excluded, list):
        errors.append(_error("$.excluded_candidates", "必须是数组，可为空"))
    else:
        excluded_ids = set()
        for index, item in enumerate(excluded):
            path = f"$.excluded_candidates[{index}]"
            if not isinstance(item, dict):
                errors.append(_error(path, "必须是对象"))
                continue
            for key in ("candidate_id", "title", "reason", "query_id"):
                _require_text(errors, item, key, path)
            candidate_id = item.get("candidate_id")
            if candidate_id in excluded_ids:
                errors.append(_error(f"{path}.candidate_id", "candidate id 重复"))
            excluded_ids.add(candidate_id)
            if item.get("relevance_label") not in {"LOW", "MISMATCH"}:
                errors.append(_error(f"{path}.relevance_label", "排除项只能是 LOW 或 MISMATCH"))
            if item.get("query_id") not in queries:
                errors.append(_error(f"{path}.query_id", "未知 query"))

    return errors


def _md_cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


def sorted_sources(selection):
    priority_order = {"core": 0, "supplementary": 1}
    return sorted(
        selection.get("selected_sources", []),
        key=lambda item: (
            priority_order.get(item.get("priority"), 9),
            SOURCE_TYPE_ORDER.get(item.get("source_type"), 99),
            item.get("source_id", ""),
        ),
    )


def render_support_table(selection):
    rows = [
        "| 编号 | 位阶／类型 | 核心引用 | 对应命题 | 作用 | 相关性 |",
        "|---|---|---|---|---|---|",
    ]
    for source in sorted_sources(selection):
        rows.append(
            "| {source_id} | {source_type} | {citation} | {propositions} | {priority}/{stance} | {relevance} |".format(
                source_id=_md_cell(source.get("source_id")),
                source_type=_md_cell(SOURCE_TYPE_LABELS.get(source.get("source_type"), source.get("source_type"))),
                citation=_md_cell(source.get("citation")),
                propositions=_md_cell("、".join(source.get("proposition_ids", []))),
                priority=_md_cell(PRIORITY_LABELS.get(source.get("priority"), source.get("priority"))),
                stance=_md_cell(STANCE_LABELS.get(source.get("stance"), source.get("stance"))),
                relevance=_md_cell(source.get("relevance_label")),
            )
        )
    return "\n".join(rows)


def render_selected_sections(selection):
    groups = [
        ("### 6.1 规范性法律依据", NORMATIVE_SOURCE_TYPES),
        ("### 6.2 精选司法案例", CASE_SOURCE_TYPES),
        ("### 6.3 其他核实材料", {"other"}),
    ]
    sections = []
    ordered = sorted_sources(selection)
    for heading, types in groups:
        matching = [item for item in ordered if item.get("source_type") in types]
        if not matching:
            continue
        blocks = []
        for item in matching:
            trace = item.get("trace", {})
            links = []
            if _text(trace.get("source_url")):
                links.append(f"[来源页面]({trace['source_url']})")
            if _text(trace.get("archive_ref")):
                links.append(f"归档：`{trace['archive_ref']}`")
            blocks.append(
                "\n".join(
                    [
                        f"#### {item.get('source_id')} · {item.get('title')}",
                        "",
                        f"- **引用**：{item.get('citation')}",
                        f"- **对应命题**：{'、'.join(item.get('proposition_ids', []))}",
                        f"- **地位与方向**：{PRIORITY_LABELS.get(item.get('priority'), item.get('priority'))} / "
                        f"{STANCE_LABELS.get(item.get('stance'), item.get('stance'))} / {item.get('relevance_label')}",
                        f"- **效力状态**：{VALIDITY_LABELS.get(item.get('validity_status'), item.get('validity_status'))}",
                        f"- **规则或裁判要旨**：{item.get('rule_or_holding')}",
                        f"- **本案适用理由**：{item.get('applicability')}",
                        f"- **核验说明**：{item.get('verification_note')}",
                        f"- **溯源**：{'；'.join(links)}",
                    ]
                )
            )
        sections.append(f"{heading}\n\n" + "\n\n".join(blocks))
    return "\n\n".join(sections)


def render_subsumption_summary(plan):
    rows = [
        "| 争点／要件 | 法律化事实与证明状态 | 暂定涵摄 | 检索缺口或补充路径 |",
        "|---|---|---|---|",
    ]
    for issue in plan.get("issues", []):
        issue_label = f"{issue.get('id')} {issue.get('question')}"
        for row in issue.get("element_matrix", []):
            facts = "；".join(row.get("facts", [])) or "未提供"
            fact_cell = f"{facts}（{row.get('fact_status')}/{row.get('proof_status')}）"
            gap = row.get("research_gap")
            gap_cell = "无"
            if isinstance(gap, dict):
                gap_cell = f"{gap.get('id')} {gap.get('question')}（{gap.get('resolution_path')}）"
            rows.append(
                f"| {_md_cell(issue_label + ' / ' + str(row.get('element', '')))} | "
                f"{_md_cell(fact_cell)} | {_md_cell(row.get('provisional_subsumption'))} | {_md_cell(gap_cell)} |"
            )
    return "\n".join(rows)


def render_query_trace(plan):
    rows = [
        "| Query | 命题／缺口 | 接口 | 查询表达 | 筛选 |",
        "|---|---|---|---|---|",
    ]
    for query in plan.get("queries", []):
        filters = json.dumps(query.get("filters", {}), ensure_ascii=False, sort_keys=True)
        rows.append(
            f"| {_md_cell(query.get('id'))} | "
            f"{_md_cell(str(query.get('proposition_id')) + ' / ' + str(query.get('research_gap_id')))} | "
            f"{_md_cell(query.get('interface'))} | {_md_cell(query.get('query_expression'))} | `{_md_cell(filters)}` |"
        )
    return "\n".join(rows)


def render_unresolved(selection):
    items = selection.get("unresolved_propositions", [])
    if not items:
        return "_无。_"
    rows = ["| 命题 | 未解决原因 | 后续动作 |", "|---|---|---|"]
    for item in items:
        rows.append(
            f"| {_md_cell(item.get('proposition_id'))} | {_md_cell(item.get('reason'))} | {_md_cell(item.get('next_action'))} |"
        )
    return "\n".join(rows)


def render_excluded(selection):
    items = selection.get("excluded_candidates", [])
    if not items:
        return "_无单独记录；完整候选仍保留在原始归档中。_"
    counts = {"LOW": 0, "MISMATCH": 0}
    for item in items:
        label = item.get("relevance_label")
        if label in counts:
            counts[label] += 1
    return (
        f"已排除 {len(items)} 条候选（LOW {counts['LOW']} 条，MISMATCH {counts['MISMATCH']} 条）。"
        "为避免用无关材料增加正文负担，名称与逐条理由仅保留在归档的 `selected-sources.json`。"
    )
