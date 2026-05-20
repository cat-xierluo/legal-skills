from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from basic_postprocess import PostprocessResult


@dataclass(frozen=True)
class LegalTermRule:
    pattern: str
    replacement: str
    category: str
    description: str
    flags: int = re.MULTILINE


@dataclass(frozen=True)
class LegalContextSignal:
    pattern: str
    label: str
    weight: int
    flags: int = re.MULTILINE


def _spaced_term_rule(term: str, category: str = "spaced_legal_term") -> LegalTermRule:
    chars = [re.escape(char) for char in term]
    optional_gap = r"(?:[ \t]*\n[ \t]*|[ \t]*)"
    required_gap = r"(?:[ \t]+|[ \t]*\n[ \t]*)"
    variants: list[str] = []
    for required_index in range(len(chars) - 1):
        parts: list[str] = []
        for index, char in enumerate(chars):
            parts.append(char)
            if index < len(chars) - 1:
                parts.append(required_gap if index == required_index else optional_gap)
        variants.append("".join(parts))
    pattern = "(?:" + "|".join(variants) + ")"
    return LegalTermRule(
        pattern=pattern,
        replacement=term,
        category=category,
        description=f"合并法律术语断字/断行：{term}",
    )


def _loose_term_pattern(term: str) -> str:
    chars = [re.escape(char) for char in term]
    return r"[ \t\n]*".join(chars)


LITERAL_CONFUSIONS = [
    ("亊", "事", "ocr_variant", "将 OCR 识别出的异体字“亊”规范为“事”"),
    ("入民法院", "人民法院", "ocr_confusion", "修正常见 OCR 误识别：入民法院"),
    ("入民检察院", "人民检察院", "ocr_confusion", "修正常见 OCR 误识别：入民检察院"),
    ("入民陪审员", "人民陪审员", "ocr_confusion", "修正常见 OCR 误识别：入民陪审员"),
    ("民亊", "民事", "ocr_variant", "修正常见 OCR 误识别：民亊"),
    ("刑亊", "刑事", "ocr_variant", "修正常见 OCR 误识别：刑亊"),
]


SPACED_TERMS = [
    "人民法院",
    "人民检察院",
    "人民陪审员",
    "民事判决书",
    "民事裁定书",
    "民事调解书",
    "刑事判决书",
    "行政判决书",
    "执行裁定书",
    "民事起诉状",
    "民事上诉状",
    "答辩状",
    "代理意见",
    "质证意见",
    "法定代表人",
    "委托诉讼代理人",
    "委托代理人",
    "诉讼请求",
    "事实和理由",
    "审理经过",
    "审理查明",
    "经审理查明",
    "基本事实",
    "争议焦点",
    "本院查明",
    "本院认为",
    "裁判结果",
    "判决如下",
    "裁定如下",
    "审判长",
    "审判员",
    "书记员",
    "原告",
    "被告",
    "第三人",
    "上诉人",
    "被上诉人",
    "申请人",
    "被申请人",
    "再审申请人",
    "申请执行人",
    "被执行人",
    "执行依据",
    "执行标的",
    "管辖权异议",
    "举证期限",
    "证据目录",
    "庭审笔录",
    "开庭传票",
    "送达地址确认书",
    "营业执照",
    "统一社会信用代码",
    "身份证号码",
    "案件受理费",
    "保全费",
    "公告费",
    "鉴定费",
    "律师费",
    "违约金",
    "滞纳金",
    "迟延履行期间",
    "加倍支付迟延履行期间的债务利息",
]


LABEL_RULES = [
    LegalTermRule(
        pattern=r"^(\s*)(原告|被告|第三人|上诉人|被上诉人|申请人|被申请人|再审申请人|申请执行人|被执行人|法定代表人|委托诉讼代理人|委托代理人)\s*[;；:：]\s*",
        replacement=r"\1\2：",
        category="legal_label",
        description="统一常见法律主体标签冒号",
    ),
    LegalTermRule(
        pattern=r"^(\s*)(案号|审理法院|裁判日期|书记员|审判长|审判员|人民陪审员)\s*[;；:：]\s*",
        replacement=r"\1\2：",
        category="legal_label",
        description="统一常见文书信息标签冒号",
    ),
]


DEFAULT_RULES = [
    *[
        LegalTermRule(
            pattern=re.escape(source),
            replacement=target,
            category=category,
            description=description,
        )
        for source, target, category, description in LITERAL_CONFUSIONS
    ],
    *[_spaced_term_rule(term) for term in SPACED_TERMS],
    *LABEL_RULES,
]


LEGAL_CONTEXT_SIGNALS = [
    *[
        LegalContextSignal(
            pattern=_loose_term_pattern(term),
            label=term,
            weight=weight,
        )
        for term, weight in [
            ("人民法院", 3),
            ("人民检察院", 3),
            ("民事判决书", 5),
            ("刑事判决书", 5),
            ("行政判决书", 5),
            ("民事裁定书", 5),
            ("执行裁定书", 5),
            ("民事起诉状", 4),
            ("民事上诉状", 4),
            ("委托诉讼代理人", 3),
            ("法定代表人", 2),
            ("诉讼请求", 3),
            ("事实和理由", 2),
            ("本院查明", 4),
            ("本院认为", 5),
            ("判决如下", 5),
            ("裁定如下", 5),
            ("审判长", 3),
            ("书记员", 3),
            ("证据目录", 3),
        ]
    ],
    LegalContextSignal(
        pattern=r"^\s*(原告|被告|第三人|上诉人|被上诉人|申请人|被申请人|申请执行人|被执行人)\s*[;；:：]",
        label="法律主体标签",
        weight=4,
    ),
    LegalContextSignal(pattern=r"^\s*(案号|审理法院|裁判日期)\s*[;；:：]", label="文书信息标签", weight=3),
    LegalContextSignal(pattern=r"[（(]\d{4}[）)][\u4e00-\u9fffA-Za-z0-9（）()第\-]+号", label="裁判文书案号", weight=4),
]


LEGAL_FILENAME_TERMS = [
    "判决书",
    "裁定书",
    "调解书",
    "起诉状",
    "上诉状",
    "答辩状",
    "证据目录",
    "庭审笔录",
    "法院",
    "卷宗",
    "案卷",
]


def detect_legal_context(markdown: str, *, source_name: str | None = None) -> dict[str, Any]:
    """Conservatively detect whether OCR text looks like a legal document."""

    sample = markdown[:50000]
    hits: list[dict[str, Any]] = []
    score = 0
    strong_signal_count = 0

    for signal in LEGAL_CONTEXT_SIGNALS:
        matches = re.findall(signal.pattern, sample, flags=signal.flags)
        if not matches:
            continue
        count = len(matches)
        capped_count = min(count, 3)
        score += signal.weight * capped_count
        if signal.weight >= 4:
            strong_signal_count += 1
        hits.append(
            {
                "label": signal.label,
                "count": count,
                "weight": signal.weight,
            }
        )

    filename_hits: list[str] = []
    if source_name:
        filename_hits = [term for term in LEGAL_FILENAME_TERMS if term in source_name]
        if filename_hits:
            score += min(len(filename_hits), 2) * 4

    is_legal = score >= 6 or strong_signal_count >= 2
    if filename_hits and score >= 4:
        is_legal = True

    return {
        "is_legal": is_legal,
        "score": score,
        "strong_signal_count": strong_signal_count,
        "hits": hits[:20],
        "filename_hits": filename_hits,
        "threshold": "score>=6 or strong_signal_count>=2",
    }


def _load_custom_rules(path_value: str | None) -> list[LegalTermRule]:
    if not path_value or not str(path_value).strip():
        return []
    path = Path(str(path_value).strip()).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"LEGAL_OCR_CUSTOM_TERMS_PATH 不存在：{path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ValueError(f"LEGAL_OCR_CUSTOM_TERMS_PATH 不是合法 JSON：{path}") from error

    raw_rules: Any
    if isinstance(payload, dict) and isinstance(payload.get("replacements"), list):
        raw_rules = payload["replacements"]
    elif isinstance(payload, dict):
        raw_rules = [{"source": key, "replacement": value} for key, value in payload.items()]
    elif isinstance(payload, list):
        raw_rules = payload
    else:
        raise ValueError("LEGAL_OCR_CUSTOM_TERMS_PATH 顶层必须是对象、数组或包含 replacements 的对象")

    rules: list[LegalTermRule] = []
    for index, item in enumerate(raw_rules, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"自定义术语第 {index} 项必须是对象")
        replacement = str(item.get("replacement") or item.get("target") or "").strip()
        if not replacement:
            raise ValueError(f"自定义术语第 {index} 项缺少 replacement")

        if item.get("pattern"):
            pattern = str(item["pattern"])
        else:
            source = str(item.get("source") or item.get("text") or "").strip()
            if not source:
                raise ValueError(f"自定义术语第 {index} 项缺少 source 或 pattern")
            pattern = re.escape(source)

        rules.append(
            LegalTermRule(
                pattern=pattern,
                replacement=replacement,
                category=str(item.get("category") or "custom_legal_term"),
                description=str(item.get("description") or "自定义法律术语替换"),
            )
        )
    return rules


def run_legal_terms_postprocess(
    markdown: str,
    *,
    custom_terms_path: str | None = None,
) -> PostprocessResult:
    text = markdown
    log: list[dict[str, str]] = []
    rules = [*DEFAULT_RULES, *_load_custom_rules(custom_terms_path)]

    for rule in rules:
        text, count = re.subn(rule.pattern, rule.replacement, text, flags=rule.flags)
        if count:
            log.append(
                {
                    "action": "legal_term_replace",
                    "category": rule.category,
                    "pattern": rule.pattern,
                    "replacement": rule.replacement,
                    "count": str(count),
                    "description": rule.description,
                }
            )
    return PostprocessResult(text=text, log=log)
