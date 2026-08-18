#!/usr/bin/env python3
"""通用级规则生成器：从任意模板树自动推导渲染规则（v0.4 全案由接入）。

定位
----
精调级（09 民间借贷 / 05 离婚）手写案由特定规则；其余 65 个案由先用本模块
自动接入"通用级"：当事人块（行块窗口定位）+ 编号标题填空 + 唯一标签追加 +
调解意愿 + 具状落款。案由特定勾选/金额字段后续按 case-routing 优先级精调升级。

通用级 elements Schema（Agent 抽取按对应骨架 references/skeletons/NN-*.md）：

    当事人: {自然人1:{...}, 自然人2:{...}, 委托诉讼代理人:[{姓名,单位,职务,联系电话}]}
    # 自然人N=模板中第 N 个自然人块（顺序语义；法人原告案由中自然人1可能是被告方）
    # 兼容键：原告→自然人1、被告→自然人2（仅双方均自然人时语义等价）
    填空: {"<编号标题前缀>": str}          # 如 "1. 医疗费"、"9. 请求依据"
    标签: {"<全文唯一标签>": str}          # 如 "计算方式"（仅全文出现一次的标签）
    对纠纷解决方式的意愿: {...}            # 模板含调解块时
    具状人_签字_盖章 / 具状日期

行块窗口定位（核心防错位机制）
----
以"姓名："独立段为锚，向后在 5 段窗口内定位该当事人的 性别/出生日期/民族/
工作单位/职务/联系电话/住所地/证件 标签段，直接对段内标签做定向替换——
不依赖全局 occurrence，天然兼容各模板当事人块顺序差异（05 代理人插中间、
09 代理人独立表、第三人块有无等）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fill_template import (
    DocParts, RuleFunc, Para, iter_paragraphs, load_text_parts,
    replace_in_paragraph, replace_option_check, fill_blanks,
    make_text_replace_rule, make_fill_after_rule, make_signature_date_rule,
    fmt_date, _get_path,
)

PERSON_LABELS = [
    "民族：", "工作单位：", "职务：", "联系电话：",
    "住所地（户籍所在地）：", "经常居住地：", "证件类型：", "证件号码：",
]

# 法人块标签（窗口内定向追加）
LEGAL_LABELS = [
    ("名称", "名称："),
    ("住所地", "住所地（主要办事机构所在地）："),
    ("注册地", "注册地 / 登记地："),
    ("统一社会信用代码", "统一社会信用代码："),
]


def _paras(doc: DocParts) -> list[Para]:
    return list(iter_paragraphs(doc))


def _find_party_anchor(paras: list[Para]) -> list[int]:
    """自然人当事人锚点：以 "姓名：" 结尾的段落（裸形态或"其他□ 姓名："前缀形态），
    且其后 1-3 段内存在 "性别：男" 行（排除法人/代理人块中无性别行的姓名段）。"""
    out = []
    for i, p in enumerate(paras):
        t = p.text.strip()
        if not t.endswith("姓名："):
            continue
        if any(paras[j].text.strip().startswith("性别：男") for j in range(i + 1, min(i + 4, len(paras)))):
            out.append(i)
    return out


def _party_window(paras: list[Para], anchor: int) -> list[Para]:
    return paras[anchor: anchor + 7]


def _clone_party_block(parts, paras, anchor_idx: int) -> int:
    """复制自然人锚所在块（<w:tr> 表格行优先，否则锚起 5 个 <w:p>），返回新增段落数。

    直接修改 parts 内的 XML 树；调用方随后重新枚举段落。
    """
    import copy as _copy
    target_p = paras[anchor_idx]._p
    # 向上找 <w:tr>（表格行）
    node = target_p
    tr = None
    while node is not None:
        if node.tag.endswith("}tr"):
            tr = node
            break
        node = node.getparent()
    if tr is not None:
        new_tr = _copy.deepcopy(tr)
        tr.addnext(new_tr)
        # 新行段落数 ≈ 原行（估算 +6 已含原块窗口 5+1 头）
        return 6
    # 非表格：复制锚起 5 个连续 <w:p>
    cur = target_p
    group = []
    for _ in range(5):
        group.append(cur)
        nxt = cur.getnext()
        while nxt is not None and not nxt.tag.endswith("}p"):
            nxt = nxt.getnext()
        if nxt is None:
            break
        cur = nxt
    prev_tail = group[-1]
    for g in group:
        new_p = _copy.deepcopy(g)
        prev_tail.addnext(new_p)
        prev_tail = new_p
    return len(group)


def build_generic_rules(tree_dir: Path, elements: dict | None = None) -> list[RuleFunc]:
    """对指定模板树生成通用级规则集。elements 用于多当事人侦测（自然人N/法人N N≥3 时复制块）。"""
    # 先加载一次做布局侦测
    probe_parts = load_text_parts(tree_dir)
    probe = DocParts(probe_parts)
    paras = _paras(probe)
    texts = [p.text for p in paras]

    anchors = _find_party_anchor(paras)   # 已过滤为自然人行

    # ---- 多自然人扩容：elements 声明 自然人3/4 而块不足时，复制末块（模板"可复制粘贴"条款）----
    if elements:
        want = 0
        for n in (3, 4):
            if _get_path(elements, f"当事人.自然人{n}.姓名"):
                want = n
        for _ in range(want - min(want, len(anchors))):
            if not anchors:
                break
            added = _clone_party_block(probe_parts, paras, anchors[-1])
            paras = _paras(probe)
            anchors = _find_party_anchor(paras)
            if added == 0:
                break
    has_mediation = any("是否了解调解作为非诉" in t for t in texts)
    has_signature = any("具状人" in t for t in texts)

    rules: list[RuleFunc] = []

    # ---------------- 当事人（窗口定位；自然人1/2 = 模板中第一/第二个自然人块）----------------
    # 角色语义：部分案由第一当事人为法人（物业/公益诉讼/执行类），
    # 其自然人块可能是被告/被申请人——通用级按"自然人N"顺序填，避免角色错位。
    party_anchors = anchors[:4]

    def party_lookup(elements: dict, n: int, field: str):
        v = _get_path(elements, f"当事人.自然人{n}.{field}")
        if v:
            return v
        alias = "原告" if n == 1 else "被告"
        return _get_path(elements, f"当事人.{alias}.{field}")

    for n, anchor in enumerate(party_anchors, start=1):
        role = f"自然人{n}"

        def make_name(idx=anchor, n=n):
            def rule(doc, elements):
                v = party_lookup(elements, n, "姓名")
                if not v:
                    return False
                plist = _paras(doc)
                if idx >= len(plist):
                    return False
                return replace_in_paragraph(plist[idx], "姓名：", f"姓名：{v}")
            rule.__name__ = f"gen[自然人{n}.姓名]"
            return rule
        rules.append(make_name())

        def make_gender(anchor=anchor, n=n):
            def rule(doc, elements):
                v = party_lookup(elements, n, "性别")
                if v not in ("男", "女"):
                    return False
                plist = _paras(doc)
                for q in plist[anchor: anchor + 7]:
                    if q.text.strip().startswith("性别：男"):
                        return replace_option_check(q, v)
                return False
            rule.__name__ = f"gen[自然人{n}.性别]"
            return rule
        rules.append(make_gender())

        def make_birth(anchor=anchor, n=n):
            def rule(doc, elements):
                v = party_lookup(elements, n, "出生日期")
                if not v:
                    return False
                plist = _paras(doc)
                for q in plist[anchor: anchor + 7]:
                    if "出生日期：" in q.text:
                        return fill_blanks(q, "出生日期：", "日", fmt_date(v))
                return False
            rule.__name__ = f"gen[自然人{n}.出生日期]"
            return rule
        rules.append(make_birth())

        for label in PERSON_LABELS:
            def make_label(label=label, anchor=anchor, n=n):
                short = label.rstrip("：")
                def rule(doc, elements):
                    v = party_lookup(elements, n, short)
                    if not v:
                        return False
                    plist = _paras(doc)
                    for q in plist[anchor: anchor + 7]:
                        if label in q.text:
                            return replace_in_paragraph(q, label, f"{label}{v}")
                    return False
                rule.__name__ = f"gen[自然人{n}.{short}]"
                return rule
            rules.append(make_label())

    # ---------------- 法人当事人块（锚=裸"名称："，窗口含统一社会信用代码验证）----------------
    legal_anchors = []
    for i, p in enumerate(paras):
        t = p.text.strip()
        if not t.endswith("名称："):
            continue
        window_texts = [paras[j].text for j in range(i + 1, min(i + 12, len(paras)))]
        has_code = any("统一社会信用代码：" in t for t in window_texts)
        has_repr = any("法定代表人" in t for t in window_texts)
        if has_code or has_repr:
            legal_anchors.append(i)
    for n_legal, anchor in enumerate(legal_anchors[:4], start=1):
        n = n_legal
        for field, label in LEGAL_LABELS:
            def make_legal(label=label, field=field, anchor=anchor, n=n_legal):
                def rule(doc, elements):
                    v = _get_path(elements, f"当事人.法人{n}.{field}")
                    if not v:
                        return False
                    plist = _paras(doc)
                    for q in plist[anchor: anchor + 12]:
                        if label in q.text:
                            return replace_in_paragraph(q, label, f"{label}{v}")
                    return False
                rule.__name__ = f"gen[法人{n}.{field}]"
                return rule
            rules.append(make_legal())

        # 法定代表人（含同段 职务/联系电话）
        for field, label in (("法定代表人", "法定代表人 / 负责人："), ("职务", "职务："), ("联系电话", "联系电话：")):
            def make_repr(field=field, label=label, anchor=anchor, n=n_legal):
                def rule(doc, elements):
                    v = _get_path(elements, f"当事人.法人{n}.{field}")
                    if not v:
                        return False
                    plist = _paras(doc)
                    for q in plist[anchor: anchor + 12]:
                        if label in q.text:
                            return replace_in_paragraph(q, label, f"{label}{v}")
                    return False
                rule.__name__ = f"gen[法人{n}.{field}]"
                return rule
            rules.append(make_repr())

        # 类型勾选（选项可能跨多段，窗口内扫描）
        def make_type_check(anchor=anchor, n=n_legal):
            def rule(doc, elements):
                v = _get_path(elements, f"当事人.法人{n}.类型")
                if not v:
                    return False
                plist = _paras(doc)
                for q in plist[anchor: anchor + 16]:
                    if f"{v}□" in q.text:
                        return replace_option_check(q, v)
                return False
            rule.__name__ = f"gen[法人{n}.类型]"
            return rule
        rules.append(make_type_check())

        # 所有制性质勾选（国有[控股/参股]/民营/其他）
        for field in ("所有制性质", "所有制_控股", "所有制_参股"):
            def make_ownership(field=field, anchor=anchor, n=n_legal):
                option_map = {"所有制_控股": "控股", "所有制_参股": "参股"}
                def rule(doc, elements):
                    v = _get_path(elements, f"当事人.法人{n}.{field}")
                    if not v:
                        return False
                    option = option_map.get(field, str(v))
                    plist = _paras(doc)
                    for q in plist[anchor: anchor + 16]:
                        if "所有制" in q.text and f"{option}□" in q.text:
                            return replace_option_check(q, option)
                    return False
                rule.__name__ = f"gen[法人{n}.{field}]"
                return rule
            rules.append(make_ownership())

    # ---------------- 委托诉讼代理人（"有□"段后姓名 + 独立"单位："行）----------------
    def rule_agent(doc, elements):
        v = _get_path(elements, "当事人.委托诉讼代理人.0.姓名")
        if not v:
            return False
        plist = _paras(doc)
        for i, p in enumerate(plist):
            if "有□" in p.text and i + 1 < len(plist) and plist[i + 1].text.strip() == "姓名：":
                return replace_in_paragraph(plist[i + 1], "姓名：", f"姓名：{v}")
        return False
    rule_agent.__name__ = "gen[代理人.姓名]"
    rules.append(rule_agent)

    for field, label in (("单位", "单位："), ("职务", "职务："), ("联系电话", "联系电话：")):
        def make_agent(field=field, label=label):
            def rule(doc, elements):
                v = _get_path(elements, f"当事人.委托诉讼代理人.0.{field}")
                if not v:
                    return False
                plist = _paras(doc)
                for q in plist:
                    if q.text.strip().startswith("单位：") and label in q.text:
                        return replace_in_paragraph(q, label, f"{label}{v}")
                return False
            rule.__name__ = f"gen[代理人.{field}]"
            return rule
        rules.append(make_agent())

    # ---------------- 编号标题填空（"N. xxx" 标题后紧跟空段）----------------
    title_pat = re.compile(r"^\d{1,2}[\.、]")
    seen_titles: set[str] = set()
    for i, p in enumerate(paras):
        t = p.text.strip()
        if not title_pat.match(t) or len(t) > 30:
            continue
        if i + 1 >= len(paras) or paras[i + 1].text.strip() != "":
            continue  # 仅"标题后紧跟空段"结构；指引段/正文段交给精调
        key = t[:14]
        if key in seen_titles:
            continue
        seen_titles.add(key)
        rules.append(make_fill_after_rule(f"填空.{key}", key))

    # ---------------- 全文唯一标签追加（非当事人窗口、跳过开头说明区）----------------
    label_counts: dict[str, int] = {}
    for i, p in enumerate(paras):
        if i < 12:
            continue
        if any(a <= i < a + 7 for a in party_anchors):
            continue
        for lab in re.findall(r"([^：:\s]{1,12})[：:]", p.text):
            if lab and not re.match(r"^\d", lab):
                label_counts[lab] = label_counts.get(lab, 0) + 1
    for lab, cnt in label_counts.items():
        if cnt == 1 and len(lab) >= 2:
            rules.append(make_text_replace_rule(f"标签.{lab}", f"{lab}："))

    # ---------------- 通用勾选（elements["勾选"] = {锚文本: 选项 | [选项...]}）----------------
    # 锚文本 = 含该勾选行的段落中任一稳定子串（骨架"段落原文"列取短语）；
    # 选项 = 模板选项原文（骨架"选项/标签"列）。单选用字符串，多选用列表。
    def rule_generic_checks(doc, elements):
        checks = _get_path(elements, "勾选")
        if not isinstance(checks, dict) or not checks:
            return False
        plist = _paras(doc)
        hit_any = False
        for anchor, option in checks.items():
            opts = option if isinstance(option, list) else [option]
            for q in plist:
                if anchor in q.text:
                    for opt in opts:
                        if f"{opt}□" in q.text:
                            hit_any = replace_option_check(q, opt) or hit_any
                    break  # 每个锚只作用于首个命中段
        return hit_any
    rule_generic_checks.__name__ = "gen[勾选*]"
    rules.append(rule_generic_checks)

    # ---------------- 调解意愿 / 具状 ----------------
    if has_mediation:
        from fill_template import build_common_mediation_rules
        rules += build_common_mediation_rules()
    if has_signature:
        rules.append(make_text_replace_rule("具状人_签字_盖章", "具状人（签字、盖章）："))
        rules.append(make_signature_date_rule())

    return rules


# ---------------------------------------------------------------------------
# 案由编号注册：NN → 该编号的主文书树（起诉状/自诉状/申请书优先，答辩状靠后）
# ---------------------------------------------------------------------------

PRIMARY_ORDER = ["民事起诉状", "行政起诉状", "刑事附带民事自诉状", "国家赔偿申请书", "申请书"]
ANSWER_MARKERS = ("答辩", "第三人意见陈述")


def primary_tree_for(nn: str, templates_dir: Path) -> str | None:
    """给定两位编号，返回主文书树名；纯答辩编号（如 55）返回 None。"""
    cands = [d.name for d in templates_dir.iterdir() if d.is_dir() and d.name.startswith(nn + "-")]
    if not cands:
        return None
    for marker in PRIMARY_ORDER:
        for c in cands:
            if c.endswith(marker):
                return c
    non_answer = [c for c in cands if not any(m in c for m in ANSWER_MARKERS)]
    return (non_answer or cands)[0]




def answer_tree_for(nn: str, templates_dir: Path) -> str | None:
    """给定编号，返回答辩状/第三人意见陈述书树名（非主文书）。"""
    cands = sorted(d.name for d in templates_dir.iterdir()
                   if d.is_dir() and d.name.startswith(nn + "-") and "答辩" in d.name)
    return cands[0] if cands else None


def all_secondary_trees(templates_dir: Path) -> list[str]:
    """全部非主文书树（答辩状 + 第三人意见陈述书）。"""
    from generic_rules import generic_case_numbers, primary_tree_for
    primaries = {primary_tree_for(n, templates_dir) for n in generic_case_numbers(templates_dir)}
    primaries.discard(None)
    return sorted(d.name for d in templates_dir.iterdir()
                  if d.is_dir() and d.name not in primaries)


def generic_case_numbers(templates_dir: Path) -> list[str]:
    """全部可通用接入的编号（01-68 中有主文书的）。"""
    out = []
    for d in sorted(templates_dir.iterdir()):
        if d.is_dir() and re.match(r"^\d{2}-", d.name):
            nn = d.name[:2]
            if nn not in out:
                out.append(nn)
    return out
