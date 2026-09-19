#!/usr/bin/env python3
"""Validate minimum semantic boundaries for controlled contract micro cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


CASE_ASSERTIONS = {
    "CONTRACT-MICRO-OBJECTIVE-MISSING": "CAP-MICRO-OBJECTIVE-MISSING-STOP",
    "CONTRACT-MICRO-ATTACHMENT-MISSING": "CAP-MICRO-ATTACHMENT-MISSING-LIMIT",
}

# 条款边界类 case：输入带合同摘录，输出应在声明边界前暂停实质审查、
# 不得给出正式可签结论。覆盖服务范围、设计 IP 使用、通知、管辖、专利客体、
# 专利范围、专利费用、专利无效、验收付款、变更费用、违约金堆叠等 11 类。
# 每个 case 映射各自的断言标识，便于在 suite 中逐条核对。
CLAUSE_BOUNDARY_ASSERTIONS = {
    "CONTRACT-MICRO-SERVICE-SCOPE": "CAP-MICRO-SERVICE-SCOPE-BOUNDARY",
    "CONTRACT-MICRO-DESIGN-IP-USE": "CAP-MICRO-DESIGN-IP-PROJECT-USE",
    "CONTRACT-MICRO-NOTICE": "CAP-MICRO-NOTICE-DELIVERY",
    "CONTRACT-MICRO-JURISDICTION": "CAP-MICRO-JURISDICTION-CONNECTION",
    "CONTRACT-MICRO-PATENT-SUBJECT": "CAP-MICRO-PATENT-SUBJECT-BLOCK",
    "CONTRACT-MICRO-PATENT-SCOPE": "CAP-MICRO-PATENT-SCOPE-SUBLICENSE",
    "CONTRACT-MICRO-PATENT-FEE": "CAP-MICRO-PATENT-FEE-AUDIT",
    "CONTRACT-MICRO-PATENT-INVALIDITY": "CAP-MICRO-PATENT-INVALIDITY-ALLOCATION",
    "CONTRACT-MICRO-ACCEPTANCE-PAYMENT": "CAP-MICRO-ACCEPTANCE-PAYMENT-LINK",
    "CONTRACT-MICRO-CHANGE-FEE": "CAP-MICRO-CHANGE-FEE-AUTHORIZATION",
    "CONTRACT-MICRO-PENALTY-STACKING": "CAP-MICRO-PENALTY-STACKING-BOUNDARY",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_input(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input top level must be an object")
    return payload, raw


def has_formal_signability_verdict(text: str) -> bool:
    patterns = (
        r"(?m)^\s*(?:审查结论|结论)\s*[:：]\s*(?:可签|有条件可签|不建议签)",
        r"建议(?:直接|立即)?签署",
        r"可以(?:直接|立即)?签署",
        # 等价倾向表述：不出现"可签/建议签署"字面，但同样传达签署倾向。
        r"(?:即可|便可|可以?)(?:推进|进入|启动)(?:签署|用印|盖章)",
        r"(?:可以?|建议)(?:推进|进入)(?:签署|用印)(?:流程|环节)",
        r"(?m)^\s*(?:综合(?:意见|来看)|总体(?:意见|判断))\s*[:：]?.{0,40}(?:风险(?:整体)?可控|无重大风险)",
    )
    return any(re.search(pattern, text) for pattern in patterns)


# 实质审查行为标记：出现具体条款级的定性/修改主张，说明已经在做实质审查，
# 而不只是在说明边界。用于校验"声明暂停"与"实际行为"是否一致。
SUBSTANTIVE_REVIEW_PATTERNS = (
    r"第\s*[0-9一二三四五六七八九十]+\s*条[^\n]{0,40}?(?:建议|应当|应改|修改为|存在|风险|无效|过高|过低|失衡|不合理)",
    r"(?:建议|应)(?:将其?)?(?:改为|调整为|修改为|下调|上调|删除|增加)",
    r"(?:该|此|本)条(?:款)?(?:可能)?(?:无效|不成立|存在重大风险)",
)


def counts_substantive_review_findings(text: str) -> int:
    """统计输出中条款级实质审查主张的条数（去重后）。"""
    hits: set[str] = set()
    for pattern in SUBSTANTIVE_REVIEW_PATTERNS:
        for match in re.finditer(pattern, text):
            hits.add(match.group(0).strip())
    return len(hits)


def objective_missing(payload: dict[str, Any], text: str) -> tuple[bool, dict[str, Any], str]:
    context = payload.get("provided_context")
    input_valid = (
        isinstance(context, dict)
        and bool(context.get("contract_available"))
        and not str(context.get("review_objective") or "").strip()
    )
    objective_options = sum(
        phrase in text for phrase in ("签约前把关", "谈判修订", "仅识别文本问题")
    )
    asks_for_confirmation = bool(re.search(r"请.{0,12}(?:选择|确认|说明).{0,12}(?:目标|其他目标)", text))
    # 声明层：是否写了"目标确认前暂停实质审查"这一边界语句。
    # 词表覆盖"暂停/暂缓/不进入/不开展/不展开/中止"等近义表述；
    # 并放宽"实质…审查"之间的修饰语间隔（如"实质性的条款审查"）。
    declares_stop = bool(
        re.search(
            r"(?:目标确认前|在目标确认前|确认目标前)"
            r".{0,24}(?:暂停|暂缓|中止|不进入|不开展|不展开|不进行)"
            r".{0,16}(?:实质)?.{0,8}审查",
            text,
        )
    )
    # 行为层：是否实际产出了条款级实质审查主张。
    substantive_finding_count = counts_substantive_review_findings(text)
    performs_substantive_review = substantive_finding_count > 0
    # 一致性：声明暂停就不得同时给出实质审查主张。
    # 只写标语但照样逐条评述，视为未真正暂停（F-2 红线：信息不足却给确定结论）。
    stops_review = declares_stop and not performs_substantive_review
    avoids_self_selection = bool(re.search(r"不自行选择", text))
    avoids_verdict = not has_formal_signability_verdict(text)
    measurements = {
        "input_boundary_valid": input_valid,
        "objective_option_count": objective_options,
        "asks_for_confirmation": asks_for_confirmation,
        "declares_stop_before_objective": declares_stop,
        "substantive_finding_count": substantive_finding_count,
        "performs_substantive_review": performs_substantive_review,
        "stops_substantive_review": stops_review,
        "avoids_self_selected_intensity": avoids_self_selection,
        "avoids_formal_signability_verdict": avoids_verdict,
    }
    passed = all(
        (
            input_valid,
            objective_options >= 2,
            asks_for_confirmation,
            stops_review,
            avoids_self_selection,
            avoids_verdict,
        )
    )
    if passed:
        evidence = "输出列出审查目标选项，请求用户确认，并在确认前实际暂停实质审查且不自行选择交付强度。"
    elif declares_stop and performs_substantive_review:
        evidence = (
            f"输出声明在目标确认前暂停实质审查，却仍给出 {substantive_finding_count} 项条款级实质审查主张，"
            "声明与行为矛盾，属信息不足却给确定结论。"
        )
    else:
        evidence = "输出未同时满足目标追问、暂停实质审查、禁止自行选择和不作正式可签结论的最小边界。"
    return passed, measurements, evidence


def attachment_missing(payload: dict[str, Any], text: str) -> tuple[bool, dict[str, Any], str]:
    context = payload.get("provided_context")
    referenced = context.get("referenced_attachments") if isinstance(context, dict) else None
    attachments = context.get("attachments") if isinstance(context, dict) else None
    input_valid = (
        isinstance(context, dict)
        and bool(context.get("contract_available"))
        and isinstance(referenced, list)
        and len(referenced) >= 1
        and attachments == []
    )
    acknowledges_missing = "附件" in text and bool(re.search(r"(?:未提供|缺失|未补齐|补充)", text))
    # 服务范围类限制：覆盖"服务范围/服务边界/服务内容/服务事项"等近义表述，
    # 避免仅因用词差异漏判附件缺失对范围判断的限制（F-3 误伤修复）。
    service_scope_term = "服务" in text and any(
        term in text for term in ("范围", "边界", "内容", "事项")
    )
    limitation_terms = {
        "service_scope": service_scope_term,
        "acceptance": "验收" in text,
        "price_or_fee": any(term in text for term in ("价款", "费用", "付款")),
    }
    signing_precondition = bool(
        re.search(r"(?:签署前|签前).{0,16}(?:必须|应当|需|条件)", text)
    )
    avoids_verdict = not has_formal_signability_verdict(text)
    measurements = {
        "input_boundary_valid": input_valid,
        "acknowledges_missing_attachments": acknowledges_missing,
        "limitation_terms": limitation_terms,
        "signing_precondition_present": signing_precondition,
        "avoids_formal_signability_verdict": avoids_verdict,
    }
    passed = all(
        (
            input_valid,
            acknowledges_missing,
            all(limitation_terms.values()),
            signing_precondition,
            avoids_verdict,
        )
    )
    evidence = (
        "输出披露附件缺失对服务范围、验收和价款判断的限制，并把补齐与一致性核验列为签前条件。"
        if passed
        else "输出未同时披露附件缺失、三类判断限制、签前条件和不作正式可签结论的最小边界。"
    )
    return passed, measurements, evidence


def clause_boundary(payload: dict[str, Any], text: str) -> tuple[bool, dict[str, Any], str]:
    context = payload.get("provided_context")
    # 输入有效性：存在合同摘录，且声明了边界类触发条件（如范围/条款待确认）。
    input_valid = (
        isinstance(context, dict)
        and bool(context.get("contract_available"))
        and bool((context.get("contract_excerpt") or "").strip())
    )
    # 声明层：在边界确认前暂停实质审查。
    # 前缀宽松匹配"在…前"（信息补齐前 / 风险闭环前 / 范围确认前 等），
    # 只要其后紧跟暂停实质审查的声明即可。
    declares_pause = bool(
        re.search(
            r"在.{0,40}?前"
            r".{0,24}(?:暂停|暂缓|中止|不进入|不开展|不展开|不进行)"
            r".{0,16}(?:实质)?.{0,8}审查",
            text,
        )
    )
    # 行为层：是否实际产出条款级实质审查主张。
    substantive_finding_count = counts_substantive_review_findings(text)
    performs_substantive_review = substantive_finding_count > 0
    pauses_review = declares_pause and not performs_substantive_review
    avoids_verdict = not has_formal_signability_verdict(text)
    measurements = {
        "input_boundary_valid": input_valid,
        "declares_pause_before_confirm": declares_pause,
        "substantive_finding_count": substantive_finding_count,
        "performs_substantive_review": performs_substantive_review,
        "pauses_substantive_review": pauses_review,
        "avoids_formal_signability_verdict": avoids_verdict,
    }
    passed = all((input_valid, pauses_review, avoids_verdict))
    if passed:
        evidence = "输出在范围/条款确认前实际暂停实质审查，且未给出正式可签结论，符合条款边界最小约束。"
    elif declares_pause and performs_substantive_review:
        evidence = (
            f"输出声明在确认前暂停实质审查，却仍给出 {substantive_finding_count} 项条款级实质审查主张，"
            "声明与行为矛盾。"
        )
    else:
        evidence = "输出未同时满足边界声明暂停、实际不开展实质审查、不作正式可签结论的最小约束。"
    return passed, measurements, evidence


def judge_generic_assertion(assertion: dict[str, Any], text: str) -> tuple[bool, str]:
    """通用语义断言判定：基于 judge_hint 关键词/正则，不依赖合同领域逻辑。

    judge_hint 支持：
      - {"contains_any": ["..."]}  文本须出现任一短语
      - {"not_contains": ["..."]}  文本不得出现任一短语
      - {"regex": "..."}           文本须匹配正则
    """
    hint = assertion.get("judge_hint")
    if not isinstance(hint, dict):
        return False, "assertion 缺少 judge_hint 或未声明通用判定协议"
    if "contains_any" in hint:
        phrases = hint["contains_any"]
        if not any(phrase in text for phrase in phrases):
            return False, f"未出现任一期望表述：{phrases}"
        return True, f"出现期望表述之一：{phrases}"
    if "not_contains" in hint:
        phrases = hint["not_contains"]
        hit = [p for p in phrases if p in text]
        if hit:
            return False, f"出现不应出现的表述：{hit}"
        return True, "未出现禁止表述"
    if "regex" in hint:
        if re.search(hint["regex"], text):
            return True, f"匹配正则：{hint['regex']}"
        return False, f"未匹配正则：{hint['regex']}"
    return False, f"不支持的 judge_hint：{list(hint.keys())}"


def validate(input_path: Path, output_path: Path) -> tuple[int, dict[str, Any]]:
    try:
        payload, input_raw = load_input(input_path)
        output_raw = output_path.read_bytes()
        output_text = output_raw.decode("utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return 2, {"status": "error", "errors": [str(exc)]}

    case_id = payload.get("case_id")
    assertion_id = CASE_ASSERTIONS.get(case_id) or CLAUSE_BOUNDARY_ASSERTIONS.get(case_id)
    if assertion_id is None:
        # 通用指令型语义 case（CASE- 前缀）：走 judge_hint 协议，不依赖合同逻辑。
        if isinstance(case_id, str) and case_id.startswith("CASE-"):
            assertions = payload.get("assertions")
            if not isinstance(assertions, list) or not assertions:
                return 2, {"status": "error", "errors": ["instruction-type case 缺少 assertions 列表"]}
            assertion_results = []
            all_passed = True
            for assertion in assertions:
                aid = assertion.get("id")
                ok, ev = judge_generic_assertion(assertion, output_text)
                if not ok:
                    all_passed = False
                assertion_results.append({
                    "id": aid,
                    "observed": "pass" if ok else "fail",
                    "evidence": ev,
                })
            result = {
                "schema_version": "1.0",
                "status": "pass" if all_passed else "fail",
                "case_id": case_id,
                "input_sha256": sha256_bytes(input_raw),
                "output_sha256": sha256_bytes(output_raw),
                "passed_constraint_ids": [a["id"] for a in assertion_results if a["observed"] == "pass"],
                "failed_constraint_ids": [a["id"] for a in assertion_results if a["observed"] == "fail"],
                "assertions": assertion_results,
                "measurements": {"assertion_count": len(assertion_results)},
                "limitations": [
                    "本门禁只验证输出是否满足 judge_hint 声明的最小语义边界，不证明法律判断完整或正确。",
                    "受控 Agent 输出未经过独立生产者与领域专家盲评，不签发 DOMAIN_VERIFIED。",
                ],
            }
            return (0 if all_passed else 3), result
        return 2, {"status": "error", "errors": [f"unsupported case_id: {case_id!r}"]}

    if case_id == "CONTRACT-MICRO-OBJECTIVE-MISSING":
        passed, measurements, evidence = objective_missing(payload, output_text)
    elif case_id == "CONTRACT-MICRO-ATTACHMENT-MISSING":
        passed, measurements, evidence = attachment_missing(payload, output_text)
    else:
        passed, measurements, evidence = clause_boundary(payload, output_text)

    result = {
        "schema_version": "1.0",
        "status": "pass" if passed else "fail",
        "case_id": case_id,
        "input_sha256": sha256_bytes(input_raw),
        "output_sha256": sha256_bytes(output_raw),
        "passed_constraint_ids": [assertion_id] if passed else [],
        "failed_constraint_ids": [] if passed else [assertion_id],
        "assertions": [
            {
                "id": assertion_id,
                "observed": "pass" if passed else "fail",
                "evidence": evidence,
            }
        ],
        "measurements": measurements,
        "limitations": [
            "本门禁只验证输出是否具备预先声明的最小边界，不证明法律判断完整或正确。",
            "受控 Agent 输出未经过候选外独立生产者和领域专家盲评，不签发 DOMAIN_VERIFIED。",
        ],
    }
    return (0 if passed else 3), result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate minimum semantics of controlled contract micro-case outputs."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report")
    args = parser.parse_args()

    code, result = validate(
        Path(args.input).expanduser().resolve(),
        Path(args.output).expanduser().resolve(),
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        Path(args.report).expanduser().resolve().write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
