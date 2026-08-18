#!/usr/bin/env python3
"""要素式起诉状 docx 渲染器（v0.2 · OOXML 源码树版）。

把 elements.json 按"特征文本+字段规则"写入 templates/<案由>/ 模板树，
打包输出符合法〔2025〕82 号《要素式起诉状示范文本》格式的官方立案版 docx。

v0.2 架构（相对 v0.1 python-docx 版）：
- 模板源 = **解包 OOXML 目录树**（git 可 diff，见 skill 根级 templates/）
- 替换引擎 = **lxml 直接编辑 <w:t> 节点**（跨 run 精确替换：保留 find 前后字符，
  中间被覆盖 run 清空，不吞字、不破坏字体/段落/表格结构）
- 多 part 覆盖：word/document.xml + header*/footer* 等全部文本 part
- 残留校验 --verify-residual：替换后扫描全文档，报告未清除的旧串
- 渲染流程：复制模板树 → 编辑 XML → pack_docx 打包 → 校验

依赖
----
- lxml（无 python-docx 依赖）
- scripts/pack_docx.py（同目录）

示例
----
python scripts/fill_template.py \\
    --case-type 09-private-lending \\
    --elements elements.json \\
    --output 起诉状.docx \\
    --verify-residual "旧当事人名,旧电话"
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from lxml import etree

from pack_docx import pack_tree

# ---------------------------------------------------------------------------
# OOXML 常量与段落抽象
# ---------------------------------------------------------------------------

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
Wt = "{%s}t" % W_NS       # 文本节点
Wp = "{%s}p" % W_NS       # 段落节点
Wr = "{%s}r" % W_NS       # run 节点


class Para:
    """lxml <w:p> 的轻量包装，对外暴露 .text（聚合全部 <w:t>）。"""

    __slots__ = ("_p",)

    def __init__(self, p_elem):
        self._p = p_elem

    @property
    def text(self) -> str:
        return "".join(t.text or "" for t in self._p.iter(Wt))

    @text.setter
    def text(self, value: str):
        """整段重写（兜底用）：全文写入首个 <w:t>，其余清空。会牺牲段内 run 级字体差异。"""
        ts = list(self._p.iter(Wt))
        if not ts:
            r = etree.SubElement(self._p, Wr)
            t = etree.SubElement(r, Wt)
            t.text = value
            return
        ts[0].text = value
        for t in ts[1:]:
            t.text = ""


class DocParts:
    """一个模板树的全部可编辑文本 part（word/*.xml，不含 .rels）。"""

    def __init__(self, part_trees: dict[str, etree._ElementTree]):
        self.parts = part_trees


def iter_paragraphs(doc: DocParts):
    """遍历所有 part 的所有段落（document + 页眉/页脚等）。"""
    for _name, tree in doc.parts.items():
        for p in tree.iter(Wp):
            yield Para(p)


# ---------------------------------------------------------------------------
# 跨 run 精确替换（不吞字、不破坏结构）
# ---------------------------------------------------------------------------

def _char_positions(p_elem):
    """段落内所有 <w:t> 字符的 [(wt元素, 字符在 wt.text 内索引, 字符), ...]。"""
    pos = []
    for wt in p_elem.iter(Wt):
        s = wt.text or ""
        for i, ch in enumerate(s):
            pos.append((wt, i, ch))
    return pos


def replace_in_paragraph(p: Para, old: str, new: str, replace_count: int = -1) -> bool:
    """在段落内把所有 old 替换为 new。

    跨 run 精确算法：
    - old 完整落在一个 run 内 → 保留 run 内 old 前后的字符
    - old 跨多个 run → 首 run 保留前缀+new，末 run 保留后缀，中间 run 清空
    替换后各 run 的 rPr（字体属性）原样保留。
    """
    if old not in p.text:
        return False
    changed = 0
    pos = 0
    while True:
        positions = _char_positions(p._p)
        text = "".join(c for _, _, c in positions)
        idx = text.find(old, pos)
        if idx < 0:
            break
        end = idx + len(old)
        first_wt = positions[idx][0]
        last_wt = positions[end - 1][0]
        # 各 run 在 positions 中的起始索引（用于算 run 内偏移）
        first_start = next(k for k, (wt, _, _) in enumerate(positions) if wt == first_wt)
        last_start = next(k for k, (wt, _, _) in enumerate(positions) if wt == last_wt)
        first_local = idx - first_start          # old 起点在首 run 内的偏移
        last_local = (end - 1) - last_start      # old 终点在末 run 内的偏移
        ft = first_wt.text or ""
        if first_wt == last_wt:
            first_wt.text = ft[:first_local] + new + ft[last_local + 1:]
        else:
            first_wt.text = ft[:first_local] + new
            lt = last_wt.text or ""
            last_wt.text = lt[last_local + 1:]
            # 中间被覆盖的 run 清空（按元素去重）
            seen = set()
            for k in range(idx, end):
                wt = positions[k][0]
                if wt == first_wt or wt == last_wt:
                    continue
                if wt in seen:
                    continue
                seen.add(wt)
                wt.text = ""
        changed += 1
        if 0 < replace_count <= changed:
            break
        pos = idx + len(new)
    return changed > 0


def check_box(p: Para, target_text: str, checked: bool) -> bool:
    """把 target_text 中的第一个 '□' 替换为 '☑'（checked=True）或留 '□'。"""
    if target_text not in p.text:
        return False
    if checked:
        new = target_text.replace("□", "☑", 1)
    else:
        new = target_text
    return replace_in_paragraph(p, target_text, new)


def replace_option_check(p: Para, option: str) -> bool:
    """勾选段落中独立的 "{option}□"（前一个字符不是"不"），仅第一处。

    解决 "了解□" 是 "不了解□" 子串导致的双勾/误勾问题。
    option: "了解" / "不了解" / "男" / "女" 等互为包含关系的选项。
    """
    old = f"{option}□"
    new = f"{option}☑"
    while True:
        positions = _char_positions(p._p)
        text = "".join(c for _, _, c in positions)
        idx = text.find(old)
        if idx < 0:
            return False
        prev_char = text[idx - 1] if idx > 0 else ""
        if prev_char == "不":
            # 命中的是 "不了解□" 内部子串，跳过该处找下一个
            end_scan = idx + 1
            nxt = text.find(old, end_scan)
            if nxt < 0:
                return False
            idx = nxt
        end = idx + len(old)
        # 以下与 replace_in_paragraph 的跨 run 拼接一致，作用于 [idx, end)
        first_wt = positions[idx][0]
        last_wt = positions[end - 1][0]
        first_start = next(k for k, (wt, _, _) in enumerate(positions) if wt == first_wt)
        last_start = next(k for k, (wt, _, _) in enumerate(positions) if wt == last_wt)
        first_local = idx - first_start
        last_local = (end - 1) - last_start
        ft = first_wt.text or ""
        if first_wt == last_wt:
            first_wt.text = ft[:first_local] + new + ft[last_local + 1:]
        else:
            first_wt.text = ft[:first_local] + new
            lt = last_wt.text or ""
            last_wt.text = lt[last_local + 1:]
            seen = set()
            for k in range(idx, end):
                wt = positions[k][0]
                if wt == first_wt or wt == last_wt:
                    continue
                if wt in seen:
                    continue
                seen.add(wt)
                wt.text = ""
        return True


def fill_blanks(p: Para, prefix: str, suffix: str, value: str) -> bool:
    """在 prefix 和 suffix 之间填入 value（兼容模板里"年/月/日"占位）。

    例：prefix="出生日期："，suffix="日"
        原："出生日期：      年        月         日    民族："
        改："出生日期：1985年3月12日    民族："
    """
    idx_p = p.text.find(prefix)
    if idx_p == -1:
        return False
    idx_s = p.text.find(suffix, idx_p + len(prefix))
    if idx_s == -1:
        return False
    between = p.text[idx_p + len(prefix):idx_s]
    # 允许"空白 + 中文占位字（年/月/日等）"，其他内容视为已填、不动
    if not re.fullmatch(r"[\s一-鿿]*", between):
        return False
    old_segment = p.text[idx_p:idx_s + len(suffix)]
    # 防双 suffix：值本身以 suffix 结尾（如 "…8月17日"）时不再追加
    new_segment = prefix + value + ("" if value.endswith(suffix) else suffix)
    return replace_in_paragraph(p, old_segment, new_segment)


# ---------------------------------------------------------------------------
# 规则构造器（与 v0.1 保持一致）
# ---------------------------------------------------------------------------

RuleFunc = Callable[[DocParts, dict], bool]


def _get_path(d: dict, path: str):
    """按点分路径取值。'诉讼请求.本金.尚欠金额' → 逐层下钻；支持数组下标。"""
    cur = d
    for key in path.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        elif isinstance(cur, list):
            try:
                cur = cur[int(key)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def make_text_replace_rule(path: str, match_text: str, value_key: str | None = None,
                            transform: Callable[[str], str] | None = None,
                            constant: str | None = None,
                            occurrence: int = 0,
                            append: bool = True) -> RuleFunc:
    """text-replace 规则：定位 match_text 所在段（按出现顺序取第 occurrence 个）。

    append=True（默认）：match_text 视为字段标签，替换为 标签+值（如 "姓名："→"姓名：张三"），
    保留模板原有标签文字；append=False：match_text 整体替换为值（用于含空白的复合占位，
    如 "第    条"→"第三条"，此时 transform 需输出完整新文本）。
    """
    def rule(doc: DocParts, elements: dict) -> bool:
        if constant is not None:
            value = constant
        else:
            value = _get_path(elements, path)
            if value_key:
                value = value.get(value_key, "") if isinstance(value, dict) else ""
        if not value and constant is None:
            return False
        if transform:
            value = transform(value)
        new_text = f"{match_text}{value}" if append else str(value)
        matches = [p for p in iter_paragraphs(doc) if match_text in p.text]
        if not matches:
            return False
        if occurrence == -1:
            targets = matches
        elif occurrence < len(matches):
            targets = [matches[occurrence]]
        else:
            targets = []
        if not targets:
            return False
        for p in targets:
            replace_in_paragraph(p, match_text, new_text)
        return True
    rule.__name__ = f"replace[{path}]"
    return rule


def make_text_fill_rule(path: str, prefix: str, suffix: str,
                         transform: Callable[[str], str] | None = None,
                         occurrence: int = 0) -> RuleFunc:
    """text-fill 规则：在 prefix/suffix 之间空白处填入 elements[path]。"""
    def rule(doc: DocParts, elements: dict) -> bool:
        value = _get_path(elements, path)
        if not value:
            return False
        if transform:
            value = transform(value)
        matches = [p for p in iter_paragraphs(doc)
                   if prefix in p.text and suffix in p.text and p.text.find(suffix) > p.text.find(prefix)]
        if not matches:
            return False
        if occurrence == -1:
            targets = matches
        elif occurrence < len(matches):
            targets = [matches[occurrence]]
        else:
            targets = []
        if not targets:
            return False
        for p in targets:
            fill_blanks(p, prefix, suffix, str(value))
        return True
    return rule


def make_gender_rule(path: str, occurrence: int = 0) -> RuleFunc:
    """性别勾选规则：按值勾 男□/女□（避免只勾第一个 □ 导致女性勾到男）。

    匹配条件用稳定的 "性别："+"男"+"女"（不含 □）——若以 未勾选□ 为条件，
    前一个当事人勾完后段落会退出匹配集，导致后续 occurrence 索引漂移。
    """
    def rule(doc: DocParts, elements: dict) -> bool:
        v = _get_path(elements, path)
        if v not in ("男", "女"):
            return False
        matches = [p for p in iter_paragraphs(doc)
                   if "性别：" in p.text and "男" in p.text and "女" in p.text]
        if occurrence >= len(matches):
            return False
        return replace_option_check(matches[occurrence], v)
    rule.__name__ = f"gender[{path}]"
    return rule


def make_pick_option_rule(path: str, context: str, options: tuple[str, ...],
                           occurrence: int = 0) -> RuleFunc:
    """枚举勾选规则：elements[path] 的值即选项名（如 原告/被告/其他），
    在含 context 的第 occurrence 个段落里勾选该独立选项。"""
    def rule(doc: DocParts, elements: dict) -> bool:
        v = _get_path(elements, path)
        if v not in options:
            return False
        matches = [p for p in iter_paragraphs(doc) if context in p.text]
        if occurrence >= len(matches):
            return False
        return replace_option_check(matches[occurrence], str(v))
    rule.__name__ = f"pick[{path}]"
    return rule


def make_fill_after_rule(path: str, title_text: str) -> RuleFunc:
    """在含 title_text 的段落之后，把第一个空段落的文本设为 elements[path]。

    用于"标题 + 空填写区"结构（如 事实与理由 各小节、其他请求、证据清单）。
    若标题后紧跟的是非空段落则放弃（防误写正文）。
    """
    def rule(doc: DocParts, elements: dict) -> bool:
        v = _get_path(elements, path)
        if not v:
            return False
        paras = list(iter_paragraphs(doc))
        for i, p in enumerate(paras):
            if title_text in p.text:
                for q in paras[i + 1: i + 4]:
                    if q.text.strip() == "":
                        q.text = str(v)
                        return True
                    if q.text.strip():
                        break
                return False
        return False
    rule.__name__ = f"fill_after[{path}]"
    return rule


def make_checkbox_rule(path: str, match_text: str,
                        invert: bool = False,
                        occurrence: int = 0) -> RuleFunc:
    """checkbox 规则：truthy 时把 match_text 的第一个 □ 改 ☑。"""
    def rule(doc: DocParts, elements: dict) -> bool:
        value = _get_path(elements, path)
        checked = bool(value)
        if invert:
            checked = not checked
        matches = [p for p in iter_paragraphs(doc) if match_text in p.text]
        if not matches:
            return False
        if occurrence == -1:
            targets = matches
        elif occurrence < len(matches):
            targets = [matches[occurrence]]
        else:
            targets = []
        if not targets:
            return False
        for p in targets:
            check_box(p, match_text, checked)
        return True
    return rule


# ---------------------------------------------------------------------------
# 格式化工具
# ---------------------------------------------------------------------------

def fmt_date(s: str) -> str:
    """2026-08-17 → 2026年8月17日。"""
    if not s:
        return s
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s.strip())
    if m:
        return f"{m.group(1)}年{int(m.group(2))}月{int(m.group(3))}日"
    return s


def fmt_money(s: str) -> str:
    return s.strip()


# ---------------------------------------------------------------------------
# 通用层规则（L1 当事人 + L3 代理人 + L5 调解意愿，跨案由复用；见 references/common-elements.md）
# ---------------------------------------------------------------------------

def build_common_party_rules(occ: dict | None = None) -> list[RuleFunc]:
    """当事人块通用规则（原告+被告+代理人）。

    occ 覆盖各字段的目标 occurrence（因不同模板的当事人块顺序不同）：
    09 布局（代理人表独立在后）：被告 姓名=1，单位/职务/电话=1
    05 布局（代理人插在原被告之间）：被告 姓名=2，单位/职务/电话=2
    其余字段（性别/出生/民族/工作单位/住所/证件）两布局一致（原告=0 被告=1）。
    """
    o = {
        "姓名_被告": 1, "单位_被告": 1, "职务_被告": 1, "电话_被告": 1,
        "代理_单位": 1, "代理_职务": 1, "代理_电话": 1,
    }
    o.update(occ or {})

    rules: list[RuleFunc] = []
    e = "当事人.原告"
    rules += [
        make_text_replace_rule(f"{e}.姓名", "姓名：", occurrence=0),
        make_gender_rule(f"{e}.性别", occurrence=0),
        make_text_fill_rule(f"{e}.出生日期", "出生日期：", "日", transform=fmt_date, occurrence=0),
        make_text_replace_rule(f"{e}.民族", "民族：", occurrence=0),
        make_text_replace_rule(f"{e}.工作单位", "工作单位：", occurrence=0),
        make_text_replace_rule(f"{e}.职务", "职务：", occurrence=0),
        make_text_replace_rule(f"{e}.联系电话", "联系电话：", occurrence=0),
        make_text_replace_rule(f"{e}.住所地", "住所地（户籍所在地）：", occurrence=0),
        make_text_replace_rule(f"{e}.经常居住地", "经常居住地：", occurrence=0),
        make_text_replace_rule(f"{e}.证件类型", "证件类型：", occurrence=0),
        make_text_replace_rule(f"{e}.证件号码", "证件号码：", occurrence=0),
    ]
    d = "当事人.被告"
    rules += [
        make_text_replace_rule(f"{d}.姓名", "姓名：", occurrence=o["姓名_被告"]),
        make_gender_rule(f"{d}.性别", occurrence=1),
        make_text_fill_rule(f"{d}.出生日期", "出生日期：", "日", transform=fmt_date, occurrence=1),
        make_text_replace_rule(f"{d}.民族", "民族：", occurrence=1),
        make_text_replace_rule(f"{d}.工作单位", "工作单位：", occurrence=1),
        make_text_replace_rule(f"{d}.职务", "职务：", occurrence=o["职务_被告"]),
        make_text_replace_rule(f"{d}.联系电话", "联系电话：", occurrence=o["电话_被告"]),
        make_text_replace_rule(f"{d}.住所地", "住所地（户籍所在地）：", occurrence=1),
        make_text_replace_rule(f"{d}.经常居住地", "经常居住地：", occurrence=1),
        make_text_replace_rule(f"{d}.证件类型", "证件类型：", occurrence=1),
        make_text_replace_rule(f"{d}.证件号码", "证件号码：", occurrence=1),
    ]

    # 委托诉讼代理人：姓名定位在"有□"段之后的第一个"姓名："；单位/职务/电话按 occurrence
    def rule_agent_name(doc, elements):
        v = _get_path(elements, "当事人.委托诉讼代理人.0.姓名")
        if not v:
            return False
        paragraphs = list(iter_paragraphs(doc))
        for i, p in enumerate(paragraphs):
            if "有□" in p.text and i + 1 < len(paragraphs) and paragraphs[i + 1].text.strip() == "姓名：":
                replace_in_paragraph(paragraphs[i + 1], "姓名：", f"姓名：{v}")
                return True
        return False
    rule_agent_name.__name__ = "agent[name]"
    rules.append(rule_agent_name)
    a = "当事人.委托诉讼代理人.0"
    rules += [
        make_text_replace_rule(f"{a}.单位", "单位：", occurrence=o["代理_单位"]),
        make_text_replace_rule(f"{a}.职务", "职务：", occurrence=o["代理_职务"]),
        make_text_replace_rule(f"{a}.联系电话", "联系电话：", occurrence=o["代理_电话"]),
    ]
    return rules


def make_signature_date_rule() -> RuleFunc:
    """具状日期规则：在"具状人（签字、盖章）"段（或其后紧邻的 "日期：" 段）内填日期。

    不能全局匹配 "日期："——它是 "出生日期：" 的子串，会污染当事人出生日期段。
    兼容两种布局：同段落（05）/"日期："独立成段（09 完整版树）。
    """
    def rule(doc: DocParts, elements: dict) -> bool:
        v = _get_path(elements, "具状日期")
        if not v:
            return False
        paras = list(iter_paragraphs(doc))
        for i, p in enumerate(paras):
            if "具状人（签字、盖章）" not in p.text:
                continue
            if "日期：" in p.text:
                return replace_in_paragraph(p, "日期：", f"日期：{fmt_date(v)}")
            # 布局二：紧随其后的独立 "日期：" 段
            for q in paras[i + 1: i + 4]:
                if q.text.strip().startswith("日期："):
                    return replace_in_paragraph(q, "日期：", f"日期：{fmt_date(v)}")
                if q.text.strip():
                    break
            return False
        return False
    rule.__name__ = "signature[日期]"
    return rule


def build_common_mediation_rules() -> list[RuleFunc]:
    """调解意愿块通用规则（仅民事起诉状/答辩状模板，L5）。"""

    def rule_tiaojie_zongti(doc, elements):
        v = _get_path(elements, "对纠纷解决方式的意愿.是否了解调解")
        if not v:
            return False
        paragraphs = list(iter_paragraphs(doc))
        for i, p in enumerate(paragraphs):
            if "是否了解调解作为非诉" in p.text:
                for q in paragraphs[i:]:
                    if "了解□" in q.text or "不了解□" in q.text:
                        return replace_option_check(q, v if v in ("了解", "不了解") else "了解")
                break
        return False
    rule_tiaojie_zongti.__name__ = "mediation[总述]"

    def rule_likai_jiechu_benefits(doc, elements):
        v = _get_path(elements, "对纠纷解决方式的意愿.是否了解先行调解好处")
        if not v or not isinstance(v, list) or len(v) != 5:
            return False
        seen_elements: set = set()
        applied = 0
        for p in iter_paragraphs(doc):
            if p._p in seen_elements:
                continue
            text = p.text
            if "☑" in text:
                continue
            if "了解" not in text or "□" not in text:
                continue
            seen_elements.add(p._p)
            target_value = v[applied] if applied < 5 else None
            if target_value in ("了解", "不了解"):
                replace_option_check(p, target_value)
            applied += 1
            if applied >= 5:
                break
        return applied > 0
    rule_likai_jiechu_benefits.__name__ = "mediation[好处×5]"

    def rule_kaolv_tiaojie(doc, elements):
        v = _get_path(elements, "对纠纷解决方式的意愿.是否考虑先行调解")
        if not v:
            return False
        mapping = {"是": "是□ 否□", "否": "是□ 否□", "暂不确定": "暂不确定，想要了解更多内容□"}
        target = mapping.get(v)
        if not target:
            return False
        paragraphs = [p for p in iter_paragraphs(doc) if target in p.text]
        for p in reversed(paragraphs):
            if p.text.count("☑") == 0:
                option = ("是" if v == "是" else "否") if v != "暂不确定" else "暂不确定，想要了解更多内容"
                replace_option_check(p, option)
                return True
        return False
    rule_kaolv_tiaojie.__name__ = "mediation[考虑调解]"

    return [rule_tiaojie_zongti, rule_likai_jiechu_benefits, rule_kaolv_tiaojie]


# ---------------------------------------------------------------------------
# 09-民间借贷 规则集（与 references/case-types/09-private-lending.md §二 对应）
# ---------------------------------------------------------------------------

def build_rules_02_private_lending(tree_dir=None, elements=None) -> list[RuleFunc]:
    rules: list[RuleFunc] = []

    # --- 通用层：当事人块（09 布局：代理人表独立，被告 姓名=1 单位/职务/电话=1）---
    rules += build_common_party_rules()

    # --- 诉讼请求 ---
    def rule_benjin(doc, elements):
        v = _get_path(elements, "诉讼请求.本金")
        if not v or not (v.get("尚欠金额") or v.get("截至日期")):
            return False
        date = fmt_date(v.get("截至日期", ""))
        amount = v.get("尚欠金额", "")
        new_text = f"截至{date}止，尚欠本金{amount}元（人民币，下同；如外"
        for p in iter_paragraphs(doc):
            if "尚欠本金" in p.text and "（人民币" in p.text:
                p.text = re.sub(r"截至.*?（人民币", new_text, p.text, count=1)
                return True
        return False
    rules.append(rule_benjin)

    def rule_lixi(doc, elements):
        v = _get_path(elements, "诉讼请求.利息")
        if not v or not (v.get("尚欠利息") or v.get("截至日期")):
            return False
        date = fmt_date(v.get("截至日期", ""))
        amount = v.get("尚欠利息", "")
        new_text = f"截至{date}止，尚欠利息{amount}元；"
        for p in iter_paragraphs(doc):
            if "尚欠利息" in p.text:
                p.text = re.sub(r"截至.*?；", new_text, p.text, count=1)
                return True
        return False
    rules.append(rule_lixi)

    rules += [
        make_text_replace_rule("诉讼请求.利息.计算方式", "计算方式："),
        # 新版原生 docx 中"是□"与"否□"分属不同段落，只锚定"…：是□"
        make_checkbox_rule("诉讼请求.利息.请求至实际清偿之日", "实际清偿之日止：是□"),
        make_checkbox_rule("诉讼请求.是否要求提前还款或解除合同.勾选", "是□    提前还款（加速到期）□ / 解除合同□"),
        make_checkbox_rule("诉讼请求.是否要求提前还款或解除合同.提前还款_加速到期", "提前还款（加速到期）□"),
        make_checkbox_rule("诉讼请求.是否要求提前还款或解除合同.解除合同", "解除合同□"),
        make_checkbox_rule("诉讼请求.是否主张担保权利.勾选", "是□    内容："),
        make_text_replace_rule("诉讼请求.是否主张担保权利.内容", "内容："),
        make_checkbox_rule("诉讼请求.是否主张实现债权的费用.勾选", "是□    明细："),
        make_text_replace_rule("诉讼请求.是否主张实现债权的费用.明细", "明细："),
        make_checkbox_rule("诉讼请求.是否主张诉讼费用", "是□ 否□"),
    ]

    # --- 约定管辖和诉前保全 ---
    rules += [
        make_checkbox_rule("约定管辖和诉前保全.有无仲裁_法院管辖约定", "有□                合同条款及内容："),
        make_text_replace_rule("约定管辖和诉前保全.合同条款及内容", "合同条款及内容："),
        make_checkbox_rule("约定管辖和诉前保全.是否已经诉前保全", "保全法院：              保全时间："),
        make_text_replace_rule("约定管辖和诉前保全.保全法院", "保全法院："),
        make_text_fill_rule("约定管辖和诉前保全.保全时间", "保全时间：", "日", transform=fmt_date),
        make_text_replace_rule("约定管辖和诉前保全.保全案号", "保全案号："),
    ]

    # --- 事实与理由 ---
    rules += [
        make_text_replace_rule("事实与理由.合同签订情况_名称_编号_签订时间_地点", "1. 合同签订情况（名称、 编号、签订时间、地点   等）"),
        make_text_replace_rule("事实与理由.签订主体.出借人", "出借人："),
        make_text_replace_rule("事实与理由.签订主体.借款人", "借款人："),
        make_text_replace_rule("事实与理由.借款金额.约定", "约定："),
        make_text_replace_rule("事实与理由.借款金额.实际提供", "实际提供："),
        make_checkbox_rule("事实与理由.借款金额.提供方式", "现金□"),
        make_checkbox_rule("事实与理由.借款期限.是否到期", "是否到期：是□    否□"),
    ]

    def rule_qixian(doc, elements):
        v = _get_path(elements, "事实与理由.借款期限")
        if not v:
            return False
        start = fmt_date(v.get("约定期限起", ""))
        end = fmt_date(v.get("约定期限止", ""))
        if not start and not end:
            return False
        new_text = f"约定期限：{start}起至{end}止"
        for p in iter_paragraphs(doc):
            if "约定期限：" in p.text and "起至" in p.text:
                p.text = re.sub(r"约定期限：.*?止", new_text, p.text, count=1)
                return True
        return False
    rules.append(rule_qixian)

    def rule_lilv(doc, elements):
        v = _get_path(elements, "事实与理由.借款利率")
        if not v:
            return False
        rate = v.get("数值", "")
        unit = v.get("单位", "年")
        if not rate:
            return False
        # 模板原句: "利率□    %/ 年（季 / 月）（合同条款：第    条）"
        # 改后:     "利率{rate}% / {unit}（合同条款：第    条）"
        for p in iter_paragraphs(doc):
            if "利率□" in p.text and "%/ 年" in p.text and "季 / 月" in p.text:
                p.text = re.sub(r"利率□\s*%\s*/\s*年\s*（季\s*/\s*月）", f"利率{rate}% / {unit}", p.text, count=1)
                return True
        return False
    rules.append(rule_lilv)

    rules += [
        # "第    条" → "第三条"（复合占位整体替换，保留前缀"合同条款："）
        make_text_replace_rule("事实与理由.借款利率.合同条款", "第    条",
                               transform=lambda v: f"第{v}条", append=False),
    ]

    def rule_jiekuan_time(doc, elements):
        v_time = _get_path(elements, "事实与理由.借款提供时间")
        v_amount = _get_path(elements, "事实与理由.借款提供金额")
        if not v_time and not v_amount:
            return False
        date = fmt_date(v_time) if v_time else "        年        月         日"
        amount = v_amount if v_amount else "          元"
        new_text = f"{date}，{amount}"
        for p in iter_paragraphs(doc):
            if "年        月         日，          元" in p.text:
                replace_in_paragraph(p, "        年        月         日，          元", new_text)
                return True
        return False
    rules.append(rule_jiekuan_time)

    def rule_huankuan_fangshi(doc, elements):
        v = _get_path(elements, "事实与理由.还款方式")
        if not v:
            return False
        options = [
            ("到期一次性还本付息", "到期一次性还本付息□"),
            ("按月计息、到期一次性还本", "按月计息、到期一次性还本□"),
            ("按季计息、到期一次性还本", "按季计息、到期一次性还本□"),
            ("按年计息、到期一次性还本", "按年计息、到期一次性还本□"),
        ]
        applied = False
        for key, match in options:
            if key in str(v):
                for p in iter_paragraphs(doc):
                    if match in p.text:
                        replace_in_paragraph(p, match, match.replace("□", "☑"))
                        applied = True
                        break
        return applied
    rules.append(rule_huankuan_fangshi)

    rules += [
        make_text_replace_rule("事实与理由.还款情况.已还本金", "已还本金：          元",
                               transform=lambda v: f"已还本金：{v} 元", append=False),
        make_text_replace_rule("事实与理由.还款情况.已还利息", "已还利息：          元",
                               transform=lambda v: f"已还利息：{v} 元", append=False),
        make_text_fill_rule("事实与理由.还款情况.还息至", "还息至", "日", transform=fmt_date),
        make_checkbox_rule("事实与理由.是否存在逾期还款.勾选", "是□    逾期时间：              至今已逾期"),
        make_text_replace_rule("事实与理由.是否存在逾期还款.逾期时间", "逾期时间：              至今已逾期",
                               transform=lambda v: f"逾期时间：{v}", append=False),
        make_checkbox_rule("事实与理由.是否签订物的担保_抵押_质押_合同.勾选", "是□    签订时间："),
        make_text_replace_rule("事实与理由.是否签订物的担保_抵押_质押_合同.签订时间", "签订时间："),
        make_text_replace_rule("事实与理由.担保人", "担保人："),
        make_text_replace_rule("事实与理由.担保物", "担保物："),
        make_checkbox_rule("事实与理由.是否最高额担保_抵押_质押", "担保债权的确定时间： 担保额度："),
        make_text_replace_rule("事实与理由.担保债权的确定时间", "担保债权的确定时间："),
        make_text_replace_rule("事实与理由.担保额度", "担保额度："),
        make_checkbox_rule("事实与理由.是否办理抵押_质押_登记.勾选", "是□    正式登记□"),
        make_checkbox_rule("事实与理由.是否办理抵押_质押_登记.正式登记", "正式登记□"),
        make_checkbox_rule("事实与理由.是否办理抵押_质押_登记.预告登记", "预告登记□"),
        make_checkbox_rule("事实与理由.是否签订保证合同.勾选", "是□    签订时间：              保证人："),
        make_text_replace_rule("事实与理由.是否签订保证合同.签订时间", "签订时间：              保证人："),
        make_text_replace_rule("事实与理由.是否签订保证合同.保证人", "保证人："),
        make_text_replace_rule("事实与理由.是否签订保证合同.主要内容", "主要内容："),
        make_checkbox_rule("事实与理由.是否签订保证合同.保证方式", "一般保证□"),
        make_checkbox_rule("事实与理由.其他担保方式.勾选", "是□    形式：    签订时间："),
        make_text_replace_rule("事实与理由.其他担保方式.形式", "形式：    签订时间："),
        make_text_fill_rule("事实与理由.其他担保方式.签订时间", "签订时间：", "日", transform=fmt_date),
        make_text_replace_rule("事实与理由.其他需要说明的内容", "16. 其他需要说明的内容 （可另附页）"),
        make_text_replace_rule("事实与理由.请求依据_合同约定", "合同约定："),
        make_text_replace_rule("事实与理由.请求依据_法律规定", "法律规定："),
        make_text_replace_rule("事实与理由.证据清单", "18. 证据清单（可另附 页）"),
    ]

    # --- 通用层：调解意愿块 ---
    rules += build_common_mediation_rules()

    # --- 具状人/日期 ---
    rules += [
        make_text_replace_rule("具状人_签字_盖章", "具状人（签字、盖章）："),
        make_signature_date_rule(),
    ]

    return rules


# ---------------------------------------------------------------------------
# 05-离婚 规则集（与 references/case-types/05-divorce.md 对应；模板树 occurrence 勘察 2026-08-17）
# ---------------------------------------------------------------------------

def build_rules_05_divorce(tree_dir=None, elements=None) -> list[RuleFunc]:
    rules: list[RuleFunc] = []

    # --- 通用层：当事人块（05 布局：代理人插在原被告之间 → 被告 姓名=2 单位/职务/电话=2）---
    rules += build_common_party_rules({
        "姓名_被告": 2, "单位_被告": 2, "职务_被告": 2, "电话_被告": 2,
    })

    # --- 诉讼请求（05 特定）---
    sq = "诉讼请求"
    rules += [
        # 1. 解除婚姻关系（具体主张占位替换）
        make_text_replace_rule(f"{sq}.解除婚姻关系.具体主张", "（具体主张）", append=False),
        # 2. 夫妻共同财产
        make_pick_option_rule(f"{sq}.夫妻共同财产.勾选", "有财产", ("无财产", "有财产")),
        make_pick_option_rule(f"{sq}.夫妻共同财产.房屋.归属", "房屋明细", ("原告", "被告", "其他")),
        make_text_fill_rule(f"{sq}.夫妻共同财产.房屋.其他说明", "其他□(", ")"),
        make_pick_option_rule(f"{sq}.夫妻共同财产.汽车.归属", "汽车明细", ("原告", "被告", "其他")),
        make_text_fill_rule(f"{sq}.夫妻共同财产.汽车.其他说明", "其他□(", ")", occurrence=1),
        make_pick_option_rule(f"{sq}.夫妻共同财产.存款.归属", "存款明细", ("原告", "被告", "其他")),
        make_text_fill_rule(f"{sq}.夫妻共同财产.存款.其他说明", "其他□(", ")", occurrence=2),
        make_text_replace_rule(f"{sq}.夫妻共同财产.其他", "（4）其他（按照上述样式列明）："),
        # 3. 夫妻共同债务
        make_pick_option_rule(f"{sq}.夫妻共同债务.勾选", "有债务", ("无债务", "有债务")),
        make_text_fill_rule(f"{sq}.夫妻共同债务.债务1.内容", "债务 1：", "承担主体"),
        make_pick_option_rule(f"{sq}.夫妻共同债务.债务1.承担主体", "债务 1：", ("原告", "被告", "其他")),
        make_text_fill_rule(f"{sq}.夫妻共同债务.债务1.其他说明", "其他□(", ")", occurrence=3),
        make_text_fill_rule(f"{sq}.夫妻共同债务.债务2.内容", "债务 2：", "承担主体"),
        make_pick_option_rule(f"{sq}.夫妻共同债务.债务2.承担主体", "债务 2：", ("原告", "被告", "其他")),
        make_text_fill_rule(f"{sq}.夫妻共同债务.债务2.其他说明", "其他□(", ")", occurrence=4),
        # 4. 子女直接抚养
        make_pick_option_rule(f"{sq}.子女直接抚养.勾选", "有此问题", ("无此问题", "有此问题"), occurrence=0),
        make_text_fill_rule(f"{sq}.子女直接抚养.子女1.姓名", "子女 1：", "归属"),
        make_pick_option_rule(f"{sq}.子女直接抚养.子女1.归属", "子女 1：", ("原告", "被告")),
        make_text_fill_rule(f"{sq}.子女直接抚养.子女2.姓名", "子女 2：", "归属"),
        make_pick_option_rule(f"{sq}.子女直接抚养.子女2.归属", "子女 2：", ("原告", "被告")),
        # 5. 子女抚养费
        make_pick_option_rule(f"{sq}.子女抚养费.勾选", "有此问题", ("无此问题", "有此问题"), occurrence=1),
        make_pick_option_rule(f"{sq}.子女抚养费.承担主体", "抚养费承担主体", ("原告", "被告")),
        make_text_replace_rule(f"{sq}.子女抚养费.金额及明细", "金额及明细："),
        make_text_replace_rule(f"{sq}.子女抚养费.支付方式", "支付方式："),
        # 6. 探望权
        make_pick_option_rule(f"{sq}.探望权.勾选", "有此问题", ("无此问题", "有此问题"), occurrence=2),
        make_pick_option_rule(f"{sq}.探望权.行使主体", "探望权行使主体", ("原告", "被告")),
        make_text_replace_rule(f"{sq}.探望权.行使方式", "行使方式："),
        # 7. 离婚损害赔偿／经济补偿／经济帮助
        make_pick_option_rule(f"{sq}.离婚损害赔偿.勾选", "离婚损害赔偿□", ("离婚损害赔偿",)),
        make_text_replace_rule(f"{sq}.离婚损害赔偿.金额", "金额：", occurrence=0),
        make_pick_option_rule(f"{sq}.离婚经济补偿.勾选", "离婚经济补偿□", ("离婚经济补偿",)),
        make_text_replace_rule(f"{sq}.离婚经济补偿.金额", "金额：", occurrence=1),
        make_pick_option_rule(f"{sq}.离婚经济帮助.勾选", "离婚经济帮助□", ("离婚经济帮助",)),
        make_text_replace_rule(f"{sq}.离婚经济帮助.金额", "金额：", occurrence=2),
        # 8. 诉讼费用（第一处"是□ 否□"）
        make_checkbox_rule(f"{sq}.是否主张诉讼费用", "是□ 否□", occurrence=0),
        # 9. 其他请求（标题后空段）
        make_fill_after_rule(f"{sq}.其他请求", "9. 其他请求"),
    ]

    # --- 诉前保全（05 无约定管辖）---
    rules += [
        make_checkbox_rule("诉前保全.是否已经诉前保全", "保全法院：              保全时间："),
        make_text_replace_rule("诉前保全.保全法院", "保全法院："),
        make_text_fill_rule("诉前保全.保全时间", "保全时间：", "日", transform=fmt_date),
        make_text_replace_rule("诉前保全.保全案号", "保全案号："),
    ]

    # --- 事实与理由（05 特定）---
    fr = "事实与理由"
    rules += [
        make_text_replace_rule(f"{fr}.结婚时间", "结婚时间：", transform=fmt_date),
        make_text_replace_rule(f"{fr}.生育子女情况", "生育子女情况："),
        make_text_replace_rule(f"{fr}.双方生活情况", "双方生活情况："),
        make_text_replace_rule(f"{fr}.离婚事由", "离婚事由："),
        make_text_replace_rule(f"{fr}.之前有无提起过离婚诉讼", "之前有无提起过离婚诉讼："),
        make_fill_after_rule(f"{fr}.夫妻共同财产情况", "夫妻共同财产情况"),
        make_fill_after_rule(f"{fr}.夫妻共同债务情况", "夫妻共同债务情况"),
        make_fill_after_rule(f"{fr}.子女直接抚养情况", "子女直接抚养情况"),
        make_fill_after_rule(f"{fr}.子女抚养费情况", "子女抚养费情况"),
        make_fill_after_rule(f"{fr}.子女探望权情况", "子女探望权情况"),
        make_fill_after_rule(f"{fr}.赔偿补偿帮助相关情况", "赔 偿 / 补 偿 / 经 济 帮 助"),
        make_fill_after_rule(f"{fr}.其他", "8. 其他"),
        make_text_replace_rule(f"{fr}.请求依据", "（法律及司法解释的规定，要写明具体条文）", append=False),
        make_fill_after_rule(f"{fr}.证据清单", "10. 证据清单"),
    ]

    # --- 通用层：调解意愿 + 具状人 ---
    rules += build_common_mediation_rules()
    rules += [
        make_text_replace_rule("具状人_签字_盖章", "具状人（签字、盖章）："),
        make_signature_date_rule(),
    ]
    return rules





# ---------------------------------------------------------------------------
# 精调原语（v0.6 提炼，多案由复用）
# ---------------------------------------------------------------------------

def make_amount_sentence(path: str, ctx: str, prefix: str | None = None) -> RuleFunc:
    """金额句（两种形态）：
    A. 纯句段（无□）："营养费    元" → "{prefix或ctx} {值} 元"
    B. 勾选句段："是□ 支付赔偿金    元" → "是☑ 支付赔偿金 {值} 元"（保留勾选态）
    """
    def rule(doc, elements):
        v = _get_path(elements, path)
        if not v:
            return False
        # 形态 A
        for p in iter_paragraphs(doc):
            if ctx in p.text and "□" not in p.text:
                p.text = f"{prefix or ctx} {v} 元"
                return True
        # 形态 B：含□ 的"是/有 + 句子 + 元"段
        for p in iter_paragraphs(doc):
            t = p.text
            if ctx in t and "□" in t and t.strip().endswith("元"):
                lead = "是☑" if t.strip().startswith("是□") else ("有☑" if t.strip().startswith("有□") else None)
                if lead:
                    p.text = f"{lead} {prefix or ctx} {v} 元"
                    return True
        return False
    rule.__name__ = f"amt[{path}]"
    return rule


def make_date_interest_sentence(path: str, ctx: str) -> RuleFunc:
    """日期利息句（09/13 同款）："截至{date}止，{ctx短语}{利息} 元、违约金{违约金} 元"。
    elements[path] = {截至日期, 利息, 违约金}；模板段含 ctx（如"迟延支付工程款的利息"）。"""
    def rule(doc, elements):
        v = _get_path(elements, path)
        if not isinstance(v, dict):
            return False
        d = fmt_date(v.get("截至日期", ""))
        for p in iter_paragraphs(doc):
            if ctx in p.text:
                p.text = f"截至{d}止，{ctx} {v.get('利息','')} 元、违约金 {v.get('违约金','')} 元"
                return True
        return False
    rule.__name__ = f"dint[{path}]"
    return rule


def make_yes_no_pair(path: str, yes_ctx: str, no_ctx: str, detail_label: str | None = None) -> RuleFunc:
    """两段式有/无（或 是/否）：勾选段含 yes_ctx、独立"否□/无□"段含 no_ctx。
    elements[path] = {勾选: bool, 明细|内容: str}；detail_label 为 yes 段内的明细标签。"""
    _yc = re.sub(r"\s+", "", yes_ctx)
    _nc = re.sub(r"\s+", "", no_ctx)
    def rule(doc, elements):
        v = _get_path(elements, path)
        if not isinstance(v, dict):
            return False
        hit = False
        for p in iter_paragraphs(doc):
            if _yc in re.sub(r"\s+", "", p.text) and "□" in p.text:
                if v.get("勾选"):
                    hit = replace_option_check(p, "有") or replace_option_check(p, "是") or hit
                    val = v.get("内容") or v.get("明细") or v.get("费用明细")
                    if val and detail_label and detail_label in p.text:
                        hit = replace_in_paragraph(p, detail_label, f"{detail_label}{val}") or hit
                break
        if not v.get("勾选"):
            for p in iter_paragraphs(doc):
                t = p.text.strip()
                if _nc in re.sub(r"\s+", "", t) and (t.endswith("否□") or t.endswith("无□")):
                    hit = replace_option_check(p, "否") or replace_option_check(p, "无") or hit
                    break
        return hit
    rule.__name__ = f"yn[{path}]"
    return rule


def make_fee_row(path: str, fee_name: str) -> RuleFunc:
    """知产合理费用行：模板段 "{空白}元 {费名}凭证：有□" → 重写为 "{费名} {值} 元 {费名}凭证：有☑/有□"。
    elements[path] = {金额: str, 凭证: bool}。"""
    def rule(doc, elements):
        v = _get_path(elements, path)
        if not isinstance(v, dict):
            return False
        ctx = f"{fee_name}凭证"
        for p in iter_paragraphs(doc):
            if ctx in p.text:
                mark = "有☑" if v.get("凭证", True) else "无☑"
                p.text = f"{fee_name} {v.get('金额','')} 元 {ctx}：{mark}"
                return True
        return False
    rule.__name__ = f"fee[{fee_name}]"
    return rule


# ---------------------------------------------------------------------------
# 06-买卖 / 15-劳动 / 21-交通 规则集（v0.5：通用层叠加 + 案由特定）
# 模式：build_rules_NN = generic_rules.build_generic_rules(tree) + 案由特定规则
# 当事人键沿用通用语义（自然人N/法人N，顺序=模板块顺序）
# ---------------------------------------------------------------------------

def _generic_plus(tree_dir, specifics, elements=None):
    """叠加模式：**案由特定规则在前**，通用层在后。

    顺序原因：特定规则含"找未勾选□整段重写"（如 24 惩罚性赔偿），
    若通用勾选先跑会把 □ 变 ☑ 导致特定规则锚失效（24 实测踩坑）。
    """
    import generic_rules
    return specifics + generic_rules.build_generic_rules(tree_dir, elements)




def _pick_in_window(rules: list, path: str, anchor_ctx: str, options: tuple):
    def rule(doc, elements):
        v = _get_path(elements, path)
        if v not in options:
            return False
        plist = list(iter_paragraphs(doc))
        for i, p in enumerate(plist):
            if anchor_ctx in p.text:
                for q in plist[i: i + 4]:
                    if f"{v}□" in q.text:
                        return replace_option_check(q, v)
                return False
        return False
    rule.__name__ = f"pickwin[{path}]"
    rules.append(rule)


def build_rules_06_sale(tree_dir=None, elements=None) -> list[RuleFunc]:
    sp: list[RuleFunc] = []
    sq = "诉讼请求"
    # 1. 给付价款 / 2. 利息违约金（整段重写式）
    def rule_jiakuan(doc, elements):
        v = _get_path(elements, "诉讼请求.给付价款")
        if not v:
            return False
        for p in iter_paragraphs(doc):
            if "给付价款" in p.text and "元" not in p.text:
                p.text = f"1. 给付价款（元）{v} 元"
                return True
        return False
    sp.append(rule_jiakuan)

    def rule_lixijin(doc, elements):
        v = _get_path(elements, "诉讼请求.迟延利息")
        if not v:
            return False
        d = fmt_date(v.get("截至日期", ""))
        lixi, weiyue = v.get("利息", ""), v.get("违约金", "")
        for p in iter_paragraphs(doc):
            if "迟延给付价款的利息" in p.text:
                p.text = f"截至{d}止，迟延给付价款的利息 {lixi} 元、违约金 {weiyue} 元"
                return True
        return False
    sp.append(rule_lixijin)

    sp += [
        make_text_replace_rule("诉讼请求.计算方式", "计算方式："),
        make_checkbox_rule("诉讼请求.请求至实际清偿之日", "实际清偿之日止：是□"),
        # 3. 违约类型 / 损失
        make_pick_option_rule("诉讼请求.违约类型", "违约类型：", ("迟延履行", "不履行", "其他")),
        make_text_replace_rule("诉讼请求.具体情形", "具体情形："),
        make_text_replace_rule("诉讼请求.损失计算依据", "损失计算依据："),
        # 5. 继续履行 / 解除
        _pick_in_window(sp, "诉讼请求.履行或解除", "继续履行□", ("继续履行", "判令解除合同", "确认买卖合同已于")),
        # 8. 诉讼费用
        make_checkbox_rule("诉讼请求.是否主张诉讼费用", "是□ 否□", occurrence=0),
    ]

    # 4. 瑕疵责任（多选：修理/重作/更换/退货/减少价款或者报酬）
    def rule_xiaci(doc, elements):
        vs = _get_path(elements, "诉讼请求.瑕疵责任方式")
        if not isinstance(vs, list) or not vs:
            return False
        ok = False
        for p in iter_paragraphs(doc):
            if "修理□" in p.text:
                for opt in vs:
                    if f"{opt}□" in p.text:
                        ok = replace_option_check(p, opt) or ok
                return ok
        return ok
    sp.append(rule_xiaci)

    # 6/7. 担保权利 / 实现债权费用（是□ 内容：/否□ 两段式）
    def yes_no_pair(path, yes_ctx, no_ctx):
        def rule(doc, elements):
            v = _get_path(elements, path)
            if not isinstance(v, dict):
                return False
            hit = False
            for p in iter_paragraphs(doc):
                if yes_ctx in p.text and "是□" in p.text:
                    if v.get("勾选"):
                        replace_option_check(p, "是")
                        if v.get("内容") or v.get("明细"):
                            val = v.get("内容") or v.get("明细")
                            lab = "内容：" if "内容：" in yes_ctx else "费用明细："
                            if lab in p.text:
                                replace_in_paragraph(p, lab, f"{lab}{val}")
                        hit = True
                    break
            if not v.get("勾选"):
                for p in iter_paragraphs(doc):
                    if no_ctx in p.text and p.text.strip().endswith("否□"):
                        hit = replace_option_check(p, "否") or hit
                        break
            return hit
        rule.__name__ = f"yesno[{path}]"
        return rule
    sp.append(yes_no_pair("诉讼请求.担保权利", "内容：", "无□"))
    sp.append(yes_no_pair("诉讼请求.实现债权费用", "费用明细：", "无□"))

    sp += [
        # 约定管辖（有/无）
        make_pick_option_rule("约定管辖.有无", "合同条款及内容：", ("有", "无")),
        make_text_replace_rule("约定管辖.合同条款及内容", "合同条款及内容："),
        # 诉前保全
        make_checkbox_rule("诉前保全.是否已经诉前保全", "保全法院："),
        make_text_replace_rule("诉前保全.保全法院", "保全法院："),
        make_text_fill_rule("诉前保全.保全时间", "保全时间：", "日", transform=fmt_date),
        make_text_replace_rule("诉前保全.保全案号", "保全案号："),
        # 事实与理由标签
        make_text_replace_rule("事实与理由.出卖人", "出卖人（卖方）："),
        make_text_replace_rule("事实与理由.买受人", "买受人（买方）："),
        make_text_replace_rule("事实与理由.单价", "单价"),
        make_text_replace_rule("事实与理由.分期方式", "分期方式："),
        make_pick_option_rule("事实与理由.支付方式", "以现金□", ("现金", "转账", "票据", "其他")),
        make_pick_option_rule("事实与理由.支付节奏", "一次性□ 分期□", ("一次性", "分期")),
        make_pick_option_rule("事实与理由.违约金勾选", "违约金□", ("违约金",)),
        make_pick_option_rule("事实与理由.定金勾选", "定金□", ("定金",)),
    ]
    return _generic_plus(tree_dir, sp, elements)


def build_rules_15_labor(tree_dir=None, elements=None) -> list[RuleFunc]:
    """劳动争议：7×「是□ 否□ 明细：」+ 诉讼费（occurrence=7 纯是/否）。"""
    sp: list[RuleFunc] = []
    # item → (标题锚关键词, elements 键)；用标题锚定位对应"是□ 否□ 明细："段，
    # 避免 occurrence 与段落非 1:1 时错位
    labor_items = [
        ("工资支付", "工资支付"), ("双倍工资", "书面 劳动合同双倍工资"),
        ("加班费", "加班费"), ("未休年休假工资", "年休假 工资"),
        ("社保经济损失", "社会保险费"), ("解除经济补偿", "经济补偿"),
        ("违法解除赔偿金", "赔偿金"),
    ]
    for key, title_kw in labor_items:
        def make_labor_item(key=key, title_kw=title_kw):
            def rule(doc, elements):
                v = _get_path(elements, f"诉讼请求.{key}")
                if not isinstance(v, dict):
                    return False
                plist = list(iter_paragraphs(doc))
                for i, p in enumerate(plist):
                    if "是否主张" in p.text and title_kw in p.text.replace(" ", ""):
                        for q in plist[i + 1: i + 3]:
                            if "是□" in q.text and "否□" in q.text and "明细：" in q.text:
                                hit = replace_option_check(q, "是" if v.get("勾选") else "否")
                                if v.get("明细"):
                                    hit = replace_in_paragraph(q, "明细：", f"明细：{v['明细']}") or hit
                                return hit
                        return False
                return False
            rule.__name__ = f"labor[{key}]"
            return rule
        sp.append(make_labor_item())
    # 8 诉讼费用：纯"是□ 否□"（不含明细）第一处
    def rule_feiyong(doc, elements):
        v = _get_path(elements, "诉讼请求.是否主张诉讼费用")
        if not isinstance(v, bool):
            return False
        for p in iter_paragraphs(doc):
            t = p.text.strip()
            if t.startswith("是□ 否□"):
                return replace_option_check(p, "是" if v else "否")
        return False
    sp.append(rule_feiyong)
    return _generic_plus(tree_dir, sp, elements)


def build_rules_21_traffic(tree_dir=None, elements=None) -> list[RuleFunc]:
    """交通事故：金额整段重写 + 证据有无勾选 + 医疗/误工日期段。"""
    sp: list[RuleFunc] = []

    def amount_rewrite(key, ctx):
        def rule(doc, elements):
            v = _get_path(elements, key)
            if not v:
                return False
            for p in iter_paragraphs(doc):
                if ctx in p.text and "□" not in p.text:
                    p.text = f"{ctx} {v} 元"
                    return True
            return False
        rule.__name__ = f"traffic[{key}]"
        return rule

    for key, ctx in [("营养费", "营养费"), ("住院伙食补助费", "住院伙食补助费"),
                     ("交通费", "交通费"), ("残疾赔偿金", "残疾赔偿金"),
                     ("精神损害抚慰金", "精神损害抚慰金")]:
        sp.append(amount_rewrite(f"诉讼请求.{key}", ctx))

    def rule_yiliao(doc, elements):
        v = _get_path(elements, "诉讼请求.医疗费")
        if not isinstance(v, dict):
            return False
        d1, d2 = fmt_date(v.get("起", "")), fmt_date(v.get("止", ""))
        for p in iter_paragraphs(doc):
            if "医院住院" in p.text or ("医疗费" in p.text and "期间" in p.text):
                p.text = f"{d1}至{d2}期间在{v.get('医院','')}医院住院（门诊）治疗，累计发生医疗费 {v.get('金额','')} 元"
                return True
        return False
    sp.append(rule_yiliao)

    def rule_wugong(doc, elements):
        v = _get_path(elements, "诉讼请求.误工费")
        if not isinstance(v, dict):
            return False
        d1, d2 = fmt_date(v.get("起", "")), fmt_date(v.get("止", ""))
        for p in iter_paragraphs(doc):
            if "误工费" in p.text and "□" not in p.text:
                p.text = f"{d1}至{d2}误工费 {v.get('金额','')} 元"
                return True
        return False
    sp.append(rule_wugong)

    # 证据有无（票据类）：bool true→勾"有"
    for key, ctx in [("医疗票据", "医疗费发票"), ("交通凭证", "交通费凭证")]:
        def make_evid(key=key, ctx=ctx):
            def rule(doc, elements):
                v = _get_path(elements, f"诉讼请求.{key}")
                if not isinstance(v, bool):
                    return False
                for p in iter_paragraphs(doc):
                    if ctx in p.text and "有□" in p.text:
                        return replace_option_check(p, "有" if v else "无")
                return False
            rule.__name__ = f"traffic[{key}]"
            return rule
        sp.append(make_evid())

    def rule_feiyong(doc, elements):
        v = _get_path(elements, "诉讼请求.是否主张诉讼费用")
        if not isinstance(v, bool):
            return False
        cnt = 0
        hit = False
        for p in iter_paragraphs(doc):
            t = p.text.strip()
            if t.startswith("是□ 否□"):
                cnt += 1
                if cnt == 2:  # 第 12 项 其他费用（诉讼费鉴定费）后那处
                    hit = replace_option_check(p, "是" if v else "否")
                    break
        return hit
    sp.append(rule_feiyong)
    return _generic_plus(tree_dir, sp, elements)



# ---------------------------------------------------------------------------
# 档1 知产/技术商事六案由（v0.6）：22 著作权 / 23 商标 / 27 商秘 / 24 专利 / 28 技术合同 / 13 建工
# 大勾选群（赔偿计算/权属/侵权方式等）走通用勾选机制 elements["勾选"]；
# 精调补充：金额句、合理费用行、日期利息句、两段式有/无、特征标签。
# ---------------------------------------------------------------------------

def _ip_specifics(economic_ctx: str, fees: tuple = ("律师费", "取证费", "差旅费")) -> list:
    """知产案由共用诉讼请求规则；fees 按模板费用名（27 商秘为公证费）。"""
    sp = [make_amount_sentence("诉讼请求.经济损失", economic_ctx),
          make_text_replace_rule("诉讼请求.计算依据或参考因素", "计算依据或参考因素："),
          make_text_replace_rule("诉讼请求.侵权链接", "侵权链接 / 标题：")]
    for f in fees:
        sp.append(make_fee_row(f"诉讼请求.{f}", f))
    sp.append(make_checkbox_rule("诉讼请求.是否主张诉讼费用", "是□ 否□", occurrence=0))
    return sp


def _pick_in_window_rules(path: str, anchor_ctx: str, options: tuple) -> RuleFunc:
    """锚段后 4 段窗口内勾选项（继续履行/判令解除…选项可能在后续段）。"""
    def rule(doc, elements):
        v = _get_path(elements, path)
        if v not in options:
            return False
        plist = list(iter_paragraphs(doc))
        for i, p in enumerate(plist):
            if anchor_ctx in p.text:
                for q in plist[i: i + 4]:
                    if f"{v}□" in q.text:
                        return replace_option_check(q, v)
                return False
        return False
    rule.__name__ = f"pickw[{path}]"
    return rule


# ---------------------------------------------------------------------------
# v0.8：上册余案由 + 中册补充（12 案由）。策略：复用原语（金额句/两段式/勾选）
# + 通用勾选机制 elements["勾选"] 兜底；复杂定制场景由用户按骨架补 elements。
# ---------------------------------------------------------------------------

def build_rules_07_house_sale(tree_dir=None, elements=None) -> list[RuleFunc]:
    """07 房屋买卖：合同效力/具体主张走通用勾选 + 管辖/保全。"""
    return _generic_plus(tree_dir, [
        make_pick_option_rule("约定管辖.有无", "合同条款及内容：", ("有", "无")),
        make_text_replace_rule("约定管辖.合同条款及内容", "合同条款及内容："),
        make_checkbox_rule("诉前保全.是否已经诉前保全", "保全法院："),
        make_text_replace_rule("诉前保全.保全法院", "保全法院："),
        make_text_fill_rule("诉前保全.保全时间", "保全时间：", "日", transform=fmt_date),
        make_text_replace_rule("诉前保全.保全案号", "保全案号："),
    ], elements)


def build_rules_11_lease(tree_dir=None, elements=None) -> list[RuleFunc]:
    """11 房屋租赁：迟延租金利息句 + 解除合同 + 管辖/保全。"""
    return _generic_plus(tree_dir, [
        make_date_interest_sentence("诉讼请求.迟延租金利息", "迟延支付租金的利息"),
        make_checkbox_rule("诉讼请求.请求至实际清偿之日", "实际清偿之日止：是□"),
        make_yes_no_pair("诉讼请求.解除合同", "是□ 确认合同于", "否□", "确认合同于"),
        make_yes_no_pair("诉讼请求.担保权利", "是□ 内容：", "否□", "内容："),
        make_yes_no_pair("诉讼请求.实现债权费用", "是□ 内容：", "否□", "内容："),
        make_pick_option_rule("约定管辖.有无", "合同条款及内容：", ("有", "无")),
        make_text_replace_rule("约定管辖.合同条款及内容", "合同条款及内容："),
        make_checkbox_rule("诉前保全.是否已经诉前保全", "保全法院："),
        make_text_replace_rule("诉前保全.保全法院", "保全法院："),
        make_text_fill_rule("诉前保全.保全时间", "保全时间：", "日", transform=fmt_date),
        make_text_replace_rule("诉前保全.保全案号", "保全案号："),
    ], elements)


def _date_amount_inplace(path: str, ctx: str) -> RuleFunc:
    """保留模板段前缀的带日期金额句：'截至 年 月 日止，尚欠物业费 元' → 原地填日期+金额。"""
    def rule(doc, elements):
        v = _get_path(elements, path)
        if not isinstance(v, dict):
            return False
        d = fmt_date(v.get("截至日期", ""))
        for p in iter_paragraphs(doc):
            if ctx in p.text and "□" not in p.text and f"{ctx}" in p.text and re.search(rf"{re.escape(ctx)}\s*元", p.text):
                if d:
                    p.text = re.sub(r"截至\s*年\s*月\s*日", f"截至{d}", p.text, count=1)
                p.text = re.sub(rf"{re.escape(ctx)}\s*元", f"{ctx} {v.get('金额','')} 元", p.text, count=1)
                return True
        return False
    rule.__name__ = f"damt[{path}]"
    return rule


def build_rules_14_property(tree_dir=None, elements=None) -> list[RuleFunc]:
    """14 物业：带日期金额句（原地保留"截至…止"前缀）。"""
    return _generic_plus(tree_dir, [
        _date_amount_inplace("诉讼请求.尚欠物业费", "尚欠物业费"),
        _date_amount_inplace("诉讼请求.违约金", "欠逾期物业费的违约金"),
        make_checkbox_rule("诉讼请求.请求至实际清偿之日", "实际清偿之日止：是□"),
        make_pick_option_rule("约定管辖.有无", "合同条款及内容：", ("有", "无")),
        make_text_replace_rule("约定管辖.合同条款及内容", "合同条款及内容："),
        make_checkbox_rule("诉前保全.是否已经诉前保全", "保全法院："),
        make_text_replace_rule("诉前保全.保全法院", "保全法院："),
        make_text_fill_rule("诉前保全.保全时间", "保全时间：", "日", transform=fmt_date),
        make_text_replace_rule("诉前保全.保全案号", "保全案号："),
    ], elements)


def build_rules_12_lease_finance(tree_dir=None, elements=None) -> list[RuleFunc]:
    """12 融资租赁：违约金滞纳金句 + 履行或解除窗口勾选。"""
    return _generic_plus(tree_dir, [
        _date_amount_inplace("诉讼请求.违约金滞纳金.违约金", "违约金"),
        _date_amount_inplace("诉讼请求.违约金滞纳金.滞纳金", "滞纳金"),
        make_checkbox_rule("诉讼请求.请求至实际清偿之日", "实际清偿之日止：是□"),
        _pick_in_window_rules("诉讼请求.履行或解除", "继续履行□",
                              ("继续履行", "判令解除融资租赁合同", "确认融资租赁合同已于")),
        make_yes_no_pair("诉讼请求.担保权利", "是□ 内容：", "否□", "内容："),
        make_yes_no_pair("诉讼请求.实现债权费用", "是□ 费用明细：", "否□", "费用明细："),
        make_pick_option_rule("约定管辖.有无", "合同条款及内容：", ("有", "无")),
        make_text_replace_rule("约定管辖.合同条款及内容", "合同条款及内容："),
        make_checkbox_rule("诉前保全.是否已经诉前保全", "保全法院："),
        make_text_replace_rule("诉前保全.保全法院", "保全法院："),
        make_text_fill_rule("诉前保全.保全时间", "保全时间：", "日", transform=fmt_date),
        make_text_replace_rule("诉前保全.保全案号", "保全案号："),
    ], elements)


def build_rules_16_securities_fraud(tree_dir=None, elements=None) -> list[RuleFunc]:
    """16 证券虚假陈述：投资差额损失 + 责任主体两段式。"""
    return _generic_plus(tree_dir, [
        make_amount_sentence("诉讼请求.投资差额损失", "投资差额损失"),
        make_yes_no_pair("诉讼请求.责任主体", "是□ 责任主体及责任范围：", "否□", "责任主体及责任范围"),
        make_yes_no_pair("诉讼请求.实现债权费用", "是□ 费用明细：", "否□", "费用明细："),
        make_checkbox_rule("诉讼请求.是否主张诉讼费用", "是□ 否□", occurrence=0),
        make_pick_option_rule("约定管辖.有无", "合同条款及内容：", ("有", "无")),
        make_text_replace_rule("约定管辖.合同条款及内容", "合同条款及内容："),
        make_checkbox_rule("诉前保全.是否已经诉前保全", "保全法院："),
        make_text_replace_rule("诉前保全.保全法院", "保全法院："),
        make_text_fill_rule("诉前保全.保全时间", "保全时间：", "日", transform=fmt_date),
        make_text_replace_rule("诉前保全.保全案号", "保全案号："),
    ], elements)


def _insurance_common() -> list[RuleFunc]:
    """保险类案由（17/18/20）共用：保险金句 + 费用两段式 + 管辖/保全。"""
    return [
        make_amount_sentence("诉讼请求.保险金", "保险金"),
        make_checkbox_rule("诉讼请求.请求至实际清偿之日", "实际清偿之日止：是□"),
        make_yes_no_pair("诉讼请求.实现债权费用", "是□ 费用明细：", "否□", "费用明细："),
        make_checkbox_rule("诉讼请求.是否主张诉讼费用", "是□ 否□", occurrence=0),
        make_pick_option_rule("约定管辖.有无", "合同条款及内容：", ("有", "无")),
        make_text_replace_rule("约定管辖.合同条款及内容", "合同条款及内容："),
        make_checkbox_rule("诉前保全.是否已经诉前保全", "保全法院："),
        make_text_replace_rule("诉前保全.保全法院", "保全法院："),
        make_text_fill_rule("诉前保全.保全时间", "保全时间：", "日", transform=fmt_date),
        make_text_replace_rule("诉前保全.保全案号", "保全案号："),
    ]


def build_rules_17_property_loss(tree_dir=None, elements=None) -> list[RuleFunc]:
    """17 财产损失保险。"""
    return _generic_plus(tree_dir, _insurance_common(), elements)


def build_rules_18_liability(tree_dir=None, elements=None) -> list[RuleFunc]:
    """18 责任保险。"""
    return _generic_plus(tree_dir, _insurance_common(), elements)


def build_rules_20_personal(tree_dir=None, elements=None) -> list[RuleFunc]:
    """20 人身保险。"""
    return _generic_plus(tree_dir, _insurance_common(), elements)


def build_rules_19_guarantee(tree_dir=None, elements=None) -> list[RuleFunc]:
    """19 保证保险：保险费违约金句 + 后续起算日 + 履行/解除。"""
    return _generic_plus(tree_dir, [
        make_date_interest_sentence("诉讼请求.保险费违约金", "保险费、违约金等共计"),
        make_text_replace_rule("诉讼请求.后续起算日", "自 年 月 日之后的保险费、违约金等各项费用按照保证保险合同"),
        make_yes_no_pair("诉讼请求.实现债权费用", "是□ 费用明细：", "否□", "费用明细："),
        make_checkbox_rule("诉讼请求.是否主张诉讼费用", "是□ 否□", occurrence=0),
        make_pick_option_rule("约定管辖.有无", "合同条款及内容：", ("有", "无")),
        make_text_replace_rule("约定管辖.合同条款及内容", "合同条款及内容："),
        make_checkbox_rule("诉前保全.是否已经诉前保全", "保全法院："),
        make_text_replace_rule("诉前保全.保全法院", "保全法院："),
        make_text_fill_rule("诉前保全.保全时间", "保全时间：", "日", transform=fmt_date),
        make_text_replace_rule("诉前保全.保全案号", "保全案号："),
    ], elements)


def build_rules_25_design_patent(tree_dir=None, elements=None) -> list[RuleFunc]:
    """25 外观设计专利：停止侵权 + 经济损失 + 合理费用。"""
    return _generic_plus(tree_dir, [
        make_amount_sentence("诉讼请求.经济损失", "经济损失"),
        make_text_replace_rule("诉讼请求.计算依据或参考因素", "计算依据或参考因素："),
        make_fee_row("诉讼请求.律师费", "律师费"),
        make_yes_no_pair("诉讼请求.停止侵权", "有□ 内容：", "无□", "内容："),
        make_checkbox_rule("诉讼请求.是否主张诉讼费用", "是□ 否□", occurrence=0),
    ], elements)


def build_rules_29_unfair_competition(tree_dir=None, elements=None) -> list[RuleFunc]:
    """29 不正当竞争：停止侵权 + 经济损失 + 调查取证费。"""
    return _generic_plus(tree_dir, [
        make_amount_sentence("诉讼请求.经济损失", "经济损失"),
        make_text_replace_rule("诉讼请求.计算依据或参考因素", "计算依据或参考因素："),
        make_fee_row("诉讼请求.律师费", "律师费"),
        make_fee_row("诉讼请求.调查取证费", "调查取证费"),
        make_yes_no_pair("诉讼请求.停止侵权", "有□ 内容：", "无□", "内容："),
        make_checkbox_rule("诉讼请求.是否主张诉讼费用", "是□ 否□", occurrence=0),
    ], elements)


def build_rules_30_civil_monopoly(tree_dir=None, elements=None) -> list[RuleFunc]:
    """30 民事垄断：停止侵权 + 经济损失 + 律师费/调查费。树名"30-垄断纠纷-民事起诉状"。"""
    return _generic_plus(tree_dir, [
        make_amount_sentence("诉讼请求.经济损失", "经济损失"),
        make_text_replace_rule("诉讼请求.计算依据或参考因素", "计算依据或参考因素："),
        make_pick_option_rule("诉讼请求.律师费勾选", "律师费□", ("律师费",)),
        make_pick_option_rule("诉讼请求.调查费勾选", "调查费□", ("调查费",)),
        make_yes_no_pair("诉讼请求.停止侵权", "有□ 内容：", "无□", "内容："),
        make_checkbox_rule("诉讼请求.是否主张诉讼费用", "是□ 否□", occurrence=0),
    ], elements)


# ---------------------------------------------------------------------------
# v0.9：60 强制执行（诉讼案件必备）+ 31-35 知产行政五案由
# ---------------------------------------------------------------------------

def build_rules_60_enforcement(tree_dir=None, elements=None) -> list[RuleFunc]:
    """60 强制执行申请书：执行依据（文书类型勾选+机构/案号/生效日期/判项）+ 申请执行事项。"""
    sp = []
    # 执行依据文书类型勾选（判决书/裁定书/调解书…）
    sp.append(make_pick_option_rule("执行依据.文书类型", "民事类：",
                                    ("判决书", "裁定书", "调解书", "支付令", "裁决书")))
    # 执行依据作出机构 / 案由 / 文书号 / 生效日期 / 判项主文：标题后空段填入
    sp += [
        make_fill_after_rule("执行依据.作出机构", "执行依据作出机构"),
        make_fill_after_rule("执行依据.案由", "案 由"),
        make_fill_after_rule("执行依据.文书号", "文书号"),
        make_fill_after_rule("执行依据.判项主文", "执行依据判项主文"),
    ]
    # 生效日期：标题后紧跟"年 月 日"段
    def rule_60_date(doc, elements_):
        v = _get_path(elements_, "执行依据.生效日期")
        if not v:
            return False
        plist = list(iter_paragraphs(doc))
        for i, p in enumerate(plist):
            if "生效日期" in p.text:
                for q in plist[i + 1: i + 3]:
                    if "年" in q.text and "月" in q.text and "日" in q.text and "□" not in q.text:
                        q.text = fmt_date(v)
                        return True
                break
        return False
    sp.append(rule_60_date)
    # 申请执行事项勾选（金钱给付/本金/利息/行为执行…）
    sp.append(make_pick_option_rule("申请执行事项.类型", "金钱给付□",
                                    ("金钱给付", "本金", "一般债务利息", "迟延履行利息",
                                     "其他费用", "行为执行", "交付特定物", "其他")))
    # 申请执行事项金额
    sp.append(make_text_replace_rule("申请执行事项.金额", "本金□:"))
    # 保全
    sp += [
        make_pick_option_rule("保全.有无", "保全案号：", ("有", "无")),
        make_text_replace_rule("保全.保全案号", "保全案号："),
    ]
    # 银行账户（申请执行人收款信息）
    sp += [
        make_text_replace_rule("当事人.自然人1.银行账号", "银行账号："),
        make_text_replace_rule("当事人.自然人1.开户名", "开户名："),
        make_text_replace_rule("当事人.自然人1.开户行", "开户行："),
    ]
    return _generic_plus(tree_dir, sp, elements)


def _ip_admin_specifics() -> list[RuleFunc]:
    """知产行政五案由（31-35）共用：被告=国家知识产权局/商标局等行政机关，法人块渲染。"""
    return [
        # 诉讼请求通常简单（撤销被诉决定+重新作出），走通用勾选
        make_fill_after_rule("诉讼请求.具体请求", "诉讼请求"),
        # 事实与理由：被诉决定文号 + 裁定理由 标题后空段
        make_fill_after_rule("事实与理由.被诉决定", "被诉决定"),
        make_fill_after_rule("事实与理由.事实理由", "事实与理由"),
    ]


def build_rules_31_tm_rejection(tree_dir=None, elements=None) -> list[RuleFunc]:
    """31 商标申请驳回复审。"""
    return _generic_plus(tree_dir, _ip_admin_specifics(), elements)


def build_rules_32_tm_cancellation(tree_dir=None, elements=None) -> list[RuleFunc]:
    """32 商标撤销复审行政纠纷。"""
    return _generic_plus(tree_dir, _ip_admin_specifics(), elements)


def build_rules_33_tm_invalidity(tree_dir=None, elements=None) -> list[RuleFunc]:
    """33 商标无效行政纠纷。"""
    return _generic_plus(tree_dir, _ip_admin_specifics(), elements)


def build_rules_34_patent_rejection(tree_dir=None, elements=None) -> list[RuleFunc]:
    """34 专利申请驳回复审行政纠纷。"""
    return _generic_plus(tree_dir, _ip_admin_specifics(), elements)


def build_rules_35_patent_invalidity(tree_dir=None, elements=None) -> list[RuleFunc]:
    """35 专利无效行政纠纷。"""
    return _generic_plus(tree_dir, _ip_admin_specifics(), elements)


# ---------------------------------------------------------------------------
# v0.10：执行类 61-68 八案由（共用工厂：身份勾选 + 执行依据 + 异议/复议事项）
# ---------------------------------------------------------------------------

def _enforcement_doc_specifics(role_ctx: str) -> list[RuleFunc]:
    """执行类申请书共用规则。role_ctx = 身份勾选段锚（如"身份：申请执行人□"或"身份：被执行人□"）。"""
    return [
        # 申请人/异议人身份勾选（申请执行人/被执行人/利害关系人/案外人/其他）
        make_pick_option_rule("身份.类型", role_ctx,
                              ("申请执行人", "被执行人", "利害关系人", "案外人", "其他",
                               "单位被执行人的法定代表人", "单位被执行人的负责人",
                               "单位被执行人的影响债务履行的直接责任人", "单位被执行人的实际控制人")),
        # 执行依据（机构/案号/生效日期）
        make_fill_after_rule("执行依据.作出机构", "执行依据作出机构"),
        make_fill_after_rule("执行依据.文书号", "文书号"),
        make_fill_after_rule("执行依据.判项主文", "判项主文"),
        # 银行账户
        make_text_replace_rule("当事人.自然人1.银行账号", "银行账号："),
        make_text_replace_rule("当事人.自然人1.开户名", "开户名："),
        make_text_replace_rule("当事人.自然人1.开户行", "开户行："),
    ]


def build_rules_61_limit_lift(tree_dir=None, elements=None) -> list[RuleFunc]:
    """61 暂时解除乘坐飞机高铁限制措施。"""
    return _generic_plus(tree_dir, _enforcement_doc_specifics("身份：被执行人□"), elements)


def build_rules_62_distribution(tree_dir=None, elements=None) -> list[RuleFunc]:
    """62 参与分配申请书。"""
    return _generic_plus(tree_dir, _enforcement_doc_specifics("身份：申请执行人□"), elements)


def build_rules_63_guarantee(tree_dir=None, elements=None) -> list[RuleFunc]:
    """63 执行担保申请书。"""
    return _generic_plus(tree_dir, _enforcement_doc_specifics("身份：被执行人□"), elements)


def build_rules_64_preemption(tree_dir=None, elements=None) -> list[RuleFunc]:
    """64 确认优先购买权。"""
    return _generic_plus(tree_dir, _enforcement_doc_specifics("身份：申请执行人□"), elements)


def build_rules_65_objection(tree_dir=None, elements=None) -> list[RuleFunc]:
    """65 执行异议申请书。"""
    return _generic_plus(tree_dir, _enforcement_doc_specifics("身份：申请执行人□"), elements)


def build_rules_66_reconsideration(tree_dir=None, elements=None) -> list[RuleFunc]:
    """66 执行复议申请书。"""
    return _generic_plus(tree_dir, _enforcement_doc_specifics("身份：申请执行人□"), elements)


def build_rules_67_supervision(tree_dir=None, elements=None) -> list[RuleFunc]:
    """67 执行监督申请书。"""
    return _generic_plus(tree_dir, _enforcement_doc_specifics("身份：申请执行人□"), elements)


def build_rules_68_non_execution(tree_dir=None, elements=None) -> list[RuleFunc]:
    """68 申请不予执行仲裁裁决、调解书或公证债权文书。"""
    return _generic_plus(tree_dir, _enforcement_doc_specifics("身份：申请执行人□"), elements)


# ---------------------------------------------------------------------------
# v0.11：剩余 34 案由全量精调（68/68 完成线）
# ---------------------------------------------------------------------------

def _civil_generic_specifics() -> list[RuleFunc]:
    """海事/环资类民事起诉状共用：管辖保全 + 标准金额句位（金额字段走通用勾选）。"""
    return [
        make_pick_option_rule("约定管辖.有无", "合同条款及内容：", ("有", "无")),
        make_text_replace_rule("约定管辖.合同条款及内容", "合同条款及内容："),
        make_checkbox_rule("诉前保全.是否已经诉前保全", "保全法院："),
        make_text_replace_rule("诉前保全.保全法院", "保全法院："),
        make_text_fill_rule("诉前保全.保全时间", "保全时间：", "日", transform=fmt_date),
        make_text_replace_rule("诉前保全.保全案号", "保全案号："),
        make_checkbox_rule("诉讼请求.是否主张诉讼费用", "是□ 否□", occurrence=0),
        make_amount_sentence("诉讼请求.经济损失", "经济损失"),
        make_text_replace_rule("诉讼请求.计算依据或参考因素", "计算依据或参考因素："),
    ]


# ── 26 植物新品种（知产）──
def build_rules_26_plant_variety(tree_dir=None, elements=None) -> list[RuleFunc]:
    return _generic_plus(tree_dir, _ip_specifics("经济损失", fees=("律师费", "调查取证费")), elements)


# ── 36 垄断行政（知产行政）──
def build_rules_36_admin_monopoly(tree_dir=None, elements=None) -> list[RuleFunc]:
    return _generic_plus(tree_dir, _ip_admin_specifics(), elements)


# ── 37-40 海事四案由 ──
def build_rules_37_ship_collision(tree_dir=None, elements=None) -> list[RuleFunc]:
    """37 船舶碰撞损害责任纠纷。"""
    sp = _civil_generic_specifics()
    sp.append(make_text_replace_rule("诉讼请求.船舶信息", "船舶名称"))
    return _generic_plus(tree_dir, sp, elements)


def build_rules_38_maritime_injury(tree_dir=None, elements=None) -> list[RuleFunc]:
    """38 海上通海水域人身损害责任纠纷。"""
    sp = _civil_generic_specifics()
    sp.append(make_text_replace_rule("诉讼请求.伤残等级", "伤残等级"))
    return _generic_plus(tree_dir, sp, elements)


def build_rules_39_freight_forward(tree_dir=None, elements=None) -> list[RuleFunc]:
    """39 海上通海水域货运代理合同纠纷。"""
    return _generic_plus(tree_dir, _civil_generic_specifics(), elements)


def build_rules_40_crew_labor(tree_dir=None, elements=None) -> list[RuleFunc]:
    """40 船员劳务合同纠纷。"""
    return _generic_plus(tree_dir, _civil_generic_specifics(), elements)


# ── 41-43 环资三案由 ──
def build_rules_41_env_pollution(tree_dir=None, elements=None) -> list[RuleFunc]:
    """41 环境污染民事公益诉讼（原告=检察院/环保组织）。"""
    return _generic_plus(tree_dir, _civil_generic_specifics(), elements)


def build_rules_42_eco_damage(tree_dir=None, elements=None) -> list[RuleFunc]:
    """42 生态破坏民事公益诉讼。"""
    return _generic_plus(tree_dir, _civil_generic_specifics(), elements)


def build_rules_43_eco_compensation(tree_dir=None, elements=None) -> list[RuleFunc]:
    """43 生态环境损害赔偿诉讼（原告=省级/市级政府）。"""
    return _generic_plus(tree_dir, _civil_generic_specifics(), elements)


# ── 44-54 行政十一案由 ──
def _admin_civil_generic() -> list[RuleFunc]:
    """行政起诉状共用（被告=行政机关，同 31-35 IP admin 模式）。"""
    return _ip_admin_specifics()


def build_rules_44_admin_penalty(tree_dir=None, elements=None) -> list[RuleFunc]:
    """44 行政处罚。"""
    return _generic_plus(tree_dir, _admin_civil_generic(), elements)


def build_rules_45_admin_enforcement(tree_dir=None, elements=None) -> list[RuleFunc]:
    """45 行政强制执行。"""
    return _generic_plus(tree_dir, _admin_civil_generic(), elements)


def build_rules_46_admin_license(tree_dir=None, elements=None) -> list[RuleFunc]:
    """46 行政许可。"""
    return _generic_plus(tree_dir, _admin_civil_generic(), elements)


def build_rules_47_land_expropriation(tree_dir=None, elements=None) -> list[RuleFunc]:
    """47 国有土地上房屋征收决定。"""
    return _generic_plus(tree_dir, _admin_civil_generic(), elements)


def build_rules_48_work_injury(tree_dir=None, elements=None) -> list[RuleFunc]:
    """48 工伤保险资格或者待遇认定。"""
    return _generic_plus(tree_dir, _admin_civil_generic(), elements)


def build_rules_49_info_disclosure(tree_dir=None, elements=None) -> list[RuleFunc]:
    """49 政府信息公开。"""
    return _generic_plus(tree_dir, _admin_civil_generic(), elements)


def build_rules_50_admin_reconsider(tree_dir=None, elements=None) -> list[RuleFunc]:
    """50 行政复议。"""
    return _generic_plus(tree_dir, _admin_civil_generic(), elements)


def build_rules_51_admin_agreement(tree_dir=None, elements=None) -> list[RuleFunc]:
    """51 行政协议。"""
    return _generic_plus(tree_dir, _admin_civil_generic(), elements)


def build_rules_52_admin_compensation(tree_dir=None, elements=None) -> list[RuleFunc]:
    """52 行政补偿。"""
    return _generic_plus(tree_dir, _admin_civil_generic(), elements)


def build_rules_53_admin_damage(tree_dir=None, elements=None) -> list[RuleFunc]:
    """53 行政赔偿。"""
    return _generic_plus(tree_dir, _admin_civil_generic(), elements)


def build_rules_54_non_performance(tree_dir=None, elements=None) -> list[RuleFunc]:
    """54 不履行法定职责。"""
    return _generic_plus(tree_dir, _admin_civil_generic(), elements)


# ── 56-59 国赔四案由 ──
def build_rules_56_illegal_detention(tree_dir=None, elements=None) -> list[RuleFunc]:
    """56 违法刑事拘留赔偿。"""
    return _generic_plus(tree_dir, _enforcement_doc_specifics("身份：赔偿请求人□"), elements)


def build_rules_57_wrongful_conviction(tree_dir=None, elements=None) -> list[RuleFunc]:
    """57 刑事改判无罪赔偿。"""
    return _generic_plus(tree_dir, _enforcement_doc_specifics("身份：赔偿请求人□"), elements)


def build_rules_58_negligence(tree_dir=None, elements=None) -> list[RuleFunc]:
    """58 怠于履行监管职责致伤致死赔偿。"""
    return _generic_plus(tree_dir, _enforcement_doc_specifics("身份：赔偿请求人□"), elements)


def build_rules_59_wrongful_execution(tree_dir=None, elements=None) -> list[RuleFunc]:
    """59 错误执行赔偿。"""
    return _generic_plus(tree_dir, _enforcement_doc_specifics("身份：赔偿请求人□"), elements)


def build_rules_22_copyright(tree_dir=None, elements=None) -> list[RuleFunc]:
    return _generic_plus(tree_dir, _ip_specifics("经济损失"), elements)


def build_rules_23_trademark(tree_dir=None, elements=None) -> list[RuleFunc]:
    return _generic_plus(tree_dir, _ip_specifics("经济损失"), elements)


def build_rules_27_tradesecret(tree_dir=None, elements=None) -> list[RuleFunc]:
    # 商秘模板费用名为 公证费（非取证费），凭证段为"公证费凭证：有□ 无□"两选形态
    return _generic_plus(tree_dir, _ip_specifics("经济损失", fees=("律师费", "公证费", "差旅费")), elements)


def build_rules_24_patent(tree_dir=None, elements=None) -> list[RuleFunc]:
    # 专利模板费用行为"费名独立段 + 凭证：有□"形态，fee_row 不适用，凭证走通用勾选
    sp = _ip_specifics("经济损失", fees=())
    sp.append(make_yes_no_pair("诉讼请求.停止侵权", "有□ 内容：", "无□", "内容："))

    # 惩罚性赔偿整段："包含□ 计算方法：基数 元 ×（1+ 倍数）" → 重写
    def rule_24_punitive(doc, elements):
        v = _get_path(elements, "诉讼请求.惩罚性赔偿")
        if not isinstance(v, dict):
            return False
        for p in iter_paragraphs(doc):
            if "包含□" in p.text and "基数" in p.text:
                p.text = (f"是否包含惩罚性赔偿：{'包含☑' if v.get('勾选') else '不包含☑'} "
                          f"计算方法：基数 {v.get('基数','')} 元 ×（1+ {v.get('倍数','')} 倍数）")
                return True
        return False
    sp.append(rule_24_punitive)
    return _generic_plus(tree_dir, sp, elements)


def build_rules_28_tech(tree_dir=None, elements=None) -> list[RuleFunc]:
    sp = [
        make_pick_option_rule("诉讼请求.履行或解除", "继续履行□", ("继续履行", "判令解除合同")),
        make_text_replace_rule("诉讼请求.计算方式", "计算方式："),
        make_amount_sentence("诉讼请求.赔偿金", "支付赔偿金", prefix="支付赔偿金"),
        make_text_replace_rule("诉讼请求.具体情形", "具体情形："),
        make_text_replace_rule("诉讼请求.损失计算依据", "损失计算依据："),
        make_yes_no_pair("诉讼请求.鉴定申请", "鉴定内容：", "否□", "鉴定内容："),
        make_text_replace_rule("诉讼请求.鉴定机构名称", "鉴定机构名称："),
        make_checkbox_rule("诉前保全.是否已经诉前保全", "保全法院："),
        make_text_replace_rule("诉前保全.保全法院", "保全法院："),
        make_text_fill_rule("诉前保全.保全时间", "保全时间：", "日", transform=fmt_date),
        make_text_replace_rule("诉前保全.保全案号", "保全案号："),
    ]

    def rule_28_jiexuan(doc, elements):
        v = _get_path(elements, "诉讼请求.解除确认日期")
        if not v:
            return False
        for p in iter_paragraphs(doc):
            if "确认合同已于" in p.text:
                p.text = f"确认合同已于 {fmt_date(v)} 解除☑"
                return True
        return False
    sp.append(rule_28_jiexuan)
    return _generic_plus(tree_dir, sp, elements)


def build_rules_13_construction(tree_dir=None, elements=None) -> list[RuleFunc]:
    sp = [
        make_date_interest_sentence("诉讼请求.工程款利息违约金", "迟延支付工程款的利息"),
        make_checkbox_rule("诉讼请求.请求至实际清偿之日", "实际清偿之日止：是□", occurrence=0),
        make_yes_no_pair("诉讼请求.担保权利", "是□ 内容：", "否□", "内容："),
        make_yes_no_pair("诉讼请求.连带责任", "责任主体姓名或者名称：", "否□", "责任主体姓名或者名称："),
        make_amount_sentence("诉讼请求.停工损失", "金额", prefix="停工损失金额"),
        make_amount_sentence("诉讼请求.赔偿金", "支付赔偿金", prefix="支付赔偿金"),
        make_text_replace_rule("诉讼请求.计算方式", "计算方式："),
        make_checkbox_rule("诉讼请求.超付利息至清偿", "实际清偿之日止：是□", occurrence=1),
    ]

    def rule_13_chaofu(doc, elements):
        v = _get_path(elements, "诉讼请求.超付利息")
        if not isinstance(v, dict):
            return False
        d = fmt_date(v.get("截至日期", ""))
        for p in iter_paragraphs(doc):
            if "返还超付工程款的利息" in p.text:
                p.text = f"是☑ 截至{d}止，返还超付工程款的利息 {v.get('利息','')} 元"
                return True
        return False
    sp.append(rule_13_chaofu)
    return _generic_plus(tree_dir, sp, elements)




# ---------------------------------------------------------------------------
# P4 金融机构两案由（v0.7）：08 金融借款 / 10 信用卡
# ---------------------------------------------------------------------------

def build_rules_08_loan(tree_dir=None, elements=None) -> list[RuleFunc]:
    sp = []

    def rule_08_benjin(doc, elements):
        v = _get_path(elements, "诉讼请求.本金")
        if not isinstance(v, dict):
            return False
        d = fmt_date(v.get("截至日期", ""))
        for p in iter_paragraphs(doc):
            if "尚欠本金" in p.text:
                p.text = f"截至{d}止，尚欠本金 {v.get('金额','')} 元（人民币，下同；如外币需特别注明）"
                return True
        return False
    sp.append(rule_08_benjin)

    def rule_08_lixi(doc, elements):
        v = _get_path(elements, "诉讼请求.利息")
        if not isinstance(v, dict):
            return False
        d = fmt_date(v.get("截至日期", ""))
        body = (f"截至{d}止，欠利息 {v.get('利息','')} 元、期内利息 {v.get('期内利息','')} 元、"
                f"复利 {v.get('复利','')} 元、罚息（违约金） {v.get('罚息','')} 元")
        for p in iter_paragraphs(doc):
            if "欠利息" in p.text:
                p.text = body
                return True
            if "利 元、罚息" in re.sub(r"\s+", "", p.text):
                p.text = body
                return True
        return False
    sp.append(rule_08_lixi)

    sp += [
        make_text_replace_rule("诉讼请求.计算方式", "计算方式："),
        make_checkbox_rule("诉讼请求.请求至实际清偿之日", "实际清偿之日止：是□"),
        make_pick_option_rule("诉讼请求.提前还款或解除", "提前还款（加速到期）□",
                              ("提前还款（加速到期）", "解除合同")),
        make_yes_no_pair("诉讼请求.担保权利", "是□ 内容：", "否□", "内容："),
        make_yes_no_pair("诉讼请求.实现债权费用", "是□ 明细：", "否□", "明细："),
        make_checkbox_rule("诉讼请求.是否主张诉讼费用", "是□ 否□", occurrence=0),
        make_pick_option_rule("约定管辖.有无", "合同条款及内容：", ("有", "无")),
        make_text_replace_rule("约定管辖.合同条款及内容", "合同条款及内容："),
        make_checkbox_rule("诉前保全.是否已经诉前保全", "保全法院："),
        make_text_replace_rule("诉前保全.保全法院", "保全法院："),
        make_text_fill_rule("诉前保全.保全时间", "保全时间：", "日", transform=fmt_date),
        make_text_replace_rule("诉前保全.保全案号", "保全案号："),
        # 事实区
        make_text_replace_rule("事实与理由.贷款人", "贷款人："),
        make_text_replace_rule("事实与理由.借款人", "借款人："),
        make_text_replace_rule("事实与理由.约定金额", "约定："),
        make_text_replace_rule("事实与理由.实际发放", "实际发放："),
        make_pick_option_rule("事实与理由.是否到期", "是否到期：", ("是", "否")),
        make_text_replace_rule("事实与理由.已还本金", "已还本金："),
        make_pick_option_rule("事实与理由.还款方式", "等额本息□",
                              ("等额本息", "等额本金", "到期一次性还本付息", "其他")),
    ]
    return _generic_plus(tree_dir, sp, elements)


def build_rules_10_creditcard(tree_dir=None, elements=None) -> list[RuleFunc]:
    sp = []

    def rule_10_benjin(doc, elements):
        v = _get_path(elements, "诉讼请求.本金")
        if not isinstance(v, dict):
            return False
        d = fmt_date(v.get("截至日期", ""))
        for p in iter_paragraphs(doc):
            if "尚欠本金" in p.text:
                p.text = f"截至{d}止，尚欠本金 {v.get('金额','')} 元（人民币，下同；如为外币需特别注明）"
                return True
        return False
    sp.append(rule_10_benjin)

    def rule_10_lixi(doc, elements):
        v = _get_path(elements, "诉讼请求.利息")
        if not isinstance(v, dict):
            return False
        d = fmt_date(v.get("截至日期", ""))
        body = (f"截至{d}止，欠利息、罚息、复利、滞纳金、违约金、手续费等合计 {v.get('合计','')} 元；"
                f"计算方式：{v.get('计算方式','')}")
        for p in iter_paragraphs(doc):
            t = re.sub(r"\s+", "", p.text)
            if "欠利息" in t and ("罚息" in t or "滞纳金" in t):
                p.text = body
                return True
        return False
    sp.append(rule_10_lixi)

    def rule_10_houqi(doc, elements):
        v = _get_path(elements, "诉讼请求.后续利息起算日")
        if not v:
            return False
        for p in iter_paragraphs(doc):
            if "之后的利息" in p.text:
                p.text = (f"自 {fmt_date(v)} 之后的利息、罚息、复利、滞纳金、违约金以及手续费等各项费用"
                          f"按照信用卡领用协议计算至实际清偿之日止")
                return True
        return False
    sp.append(rule_10_houqi)

    sp += [
        make_text_replace_rule("诉讼请求.明细", "明细："),
        make_yes_no_pair("诉讼请求.担保权利", "是□ 内容：", "否□", "内容："),
        make_yes_no_pair("诉讼请求.实现债权费用", "是□ 费用明细：", "否□", "费用明细："),
        make_checkbox_rule("诉讼请求.是否主张诉讼费用", "是□ 否□", occurrence=0),
        make_pick_option_rule("约定管辖.有无", "合同条款及内容：", ("有", "无")),
        make_text_replace_rule("约定管辖.合同条款及内容", "合同条款及内容："),
        make_checkbox_rule("诉前保全.是否已经诉前保全", "保全法院："),
        make_text_replace_rule("诉前保全.保全法院", "保全法院："),
        make_text_fill_rule("诉前保全.保全时间", "保全时间：", "日", transform=fmt_date),
        make_text_replace_rule("诉前保全.保全案号", "保全案号："),
        make_text_replace_rule("事实与理由.透支金额", "透支金额："),
        make_text_replace_rule("事实与理由.计算标准", "计算标准："),
        make_text_replace_rule("事实与理由.违约责任", "违约责任："),
    ]
    return _generic_plus(tree_dir, sp, elements)



# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

CASE_TYPE_TO_TREE = {
    "09-private-lending": "09-民间借贷纠纷-民事起诉状",
    "05-divorce": "05-离婚纠纷-民事起诉状",
}

RULE_BUILDERS = {
    "09-private-lending": build_rules_02_private_lending,
    "05-divorce": build_rules_05_divorce,
    "06-sale": build_rules_06_sale,
    "15-labor": build_rules_15_labor,
    "21-traffic": build_rules_21_traffic,
    "22-copyright": build_rules_22_copyright,
    "23-trademark": build_rules_23_trademark,
    "27-tradesecret": build_rules_27_tradesecret,
    "24-patent": build_rules_24_patent,
    "28-tech": build_rules_28_tech,
    "13-construction": build_rules_13_construction,
    "08-loan": build_rules_08_loan,
    "10-creditcard": build_rules_10_creditcard,
    "07-house-sale": build_rules_07_house_sale,
    "11-lease": build_rules_11_lease,
    "14-property": build_rules_14_property,
    "12-lease-finance": build_rules_12_lease_finance,
    "16-securities-fraud": build_rules_16_securities_fraud,
    "17-property-loss": build_rules_17_property_loss,
    "18-liability": build_rules_18_liability,
    "19-guarantee": build_rules_19_guarantee,
    "20-personal": build_rules_20_personal,
    "25-design-patent": build_rules_25_design_patent,
    "29-unfair-competition": build_rules_29_unfair_competition,
    "30-civil-monopoly": build_rules_30_civil_monopoly,
    "60-enforcement": build_rules_60_enforcement,
    "31-tm-rejection": build_rules_31_tm_rejection,
    "32-tm-cancellation": build_rules_32_tm_cancellation,
    "33-tm-invalidity": build_rules_33_tm_invalidity,
    "34-patent-rejection": build_rules_34_patent_rejection,
    "35-patent-invalidity": build_rules_35_patent_invalidity,
    "61-limit-lift": build_rules_61_limit_lift,
    "62-distribution": build_rules_62_distribution,
    "63-guarantee": build_rules_63_guarantee,
    "64-preemption": build_rules_64_preemption,
    "65-objection": build_rules_65_objection,
    "66-reconsideration": build_rules_66_reconsideration,
    "67-supervision": build_rules_67_supervision,
    "68-non-execution": build_rules_68_non_execution,
    "26-plant-variety": build_rules_26_plant_variety,
    "36-admin-monopoly": build_rules_36_admin_monopoly,
    "37-ship-collision": build_rules_37_ship_collision,
    "38-maritime-injury": build_rules_38_maritime_injury,
    "39-freight-forward": build_rules_39_freight_forward,
    "40-crew-labor": build_rules_40_crew_labor,
    "41-env-pollution": build_rules_41_env_pollution,
    "42-eco-damage": build_rules_42_eco_damage,
    "43-eco-compensation": build_rules_43_eco_compensation,
    "44-admin-penalty": build_rules_44_admin_penalty,
    "45-admin-enforcement": build_rules_45_admin_enforcement,
    "46-admin-license": build_rules_46_admin_license,
    "47-land-expropriation": build_rules_47_land_expropriation,
    "48-work-injury": build_rules_48_work_injury,
    "49-info-disclosure": build_rules_49_info_disclosure,
    "50-admin-reconsider": build_rules_50_admin_reconsider,
    "51-admin-agreement": build_rules_51_admin_agreement,
    "52-admin-compensation": build_rules_52_admin_compensation,
    "53-admin-damage": build_rules_53_admin_damage,
    "54-non-performance": build_rules_54_non_performance,
    "56-illegal-detention": build_rules_56_illegal_detention,
    "57-wrongful-conviction": build_rules_57_wrongful_conviction,
    "58-negligence": build_rules_58_negligence,
    "59-wrongful-execution": build_rules_59_wrongful_execution,
}

# ---------------------------------------------------------------------------
# 通用级接入（v0.4）：精调案由之外的编号（"01"…"68"）自动路由到 generic_rules
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _generic_ns() -> list[str]:
    import generic_rules
    mains = [n for n in generic_rules.generic_case_numbers(_TEMPLATES_DIR)
             if n not in ("05", "09")]
    answers = [f"{n}-answer" for n in generic_rules.generic_case_numbers(_TEMPLATES_DIR)
               if generic_rules.answer_tree_for(n, _TEMPLATES_DIR) is not None
               and f"{n}-answer" not in mains]
    return mains + answers


def _lookup_tree_by_slug(case_type: str) -> str:
    """精调 slug（06-sale 等）→ 编号前缀的首个主文书树。"""
    nn = case_type.split("-")[0]
    cands = sorted(d.name for d in _TEMPLATES_DIR.iterdir() if d.is_dir() and d.name.startswith(nn + "-"))
    for marker in ("民事起诉状", "行政起诉状"):
        for c in cands:
            if c.endswith(marker):
                return c
    return cands[0]


def resolve_case(case_type: str, templates_dir: Path | None = None) -> tuple[Path, "Callable[[], list[RuleFunc]]"]:
    """case-type → (模板树路径, 规则构建器)。精调 key 优先，两位编号走通用级。"""
    base = templates_dir or _TEMPLATES_DIR
    if case_type in RULE_BUILDERS:
        tree = CASE_TYPE_TO_TREE.get(case_type) or _lookup_tree_by_slug(case_type)
        return base / tree, (lambda elements=None: RULE_BUILDERS[case_type](base / tree, elements))
    import generic_rules
    # 答辩状路由：NN-answer → 答辩状树
    if case_type.endswith("-answer"):
        nn = case_type[:-7]
        tree = generic_rules.answer_tree_for(nn, base)
        if tree is None:
            raise SystemExit(f"[fill_template] 错误：编号 {nn} 无答辩状模板树")
        tree_dir = base / tree
        return tree_dir, (lambda elements=None: generic_rules.build_generic_rules(tree_dir, elements))
    tree = generic_rules.primary_tree_for(case_type, base)
    if tree is None:
        raise SystemExit(f"[fill_template] 错误：编号 {case_type} 无主文书模板树")
    tree_dir = base / tree
    return tree_dir, (lambda elements=None: generic_rules.build_generic_rules(tree_dir, elements))


def apply_rules(doc: DocParts, rules: list[RuleFunc], elements: dict) -> dict:
    """应用规则。返回 {'applied': N, 'skipped': M, 'details': [...]}。"""
    details = []
    applied_count = 0
    skipped_count = 0
    for rule in rules:
        name = getattr(rule, "__name__", "rule")
        try:
            if rule(doc, elements):
                applied_count += 1
                details.append(("applied", name))
            else:
                skipped_count += 1
                details.append(("skipped", name))
        except Exception as e:
            skipped_count += 1
            details.append(("error", f"{name}: {e}"))
            print(f"[fill_template] 规则错误: {name}: {e}", file=sys.stderr)
    return {"applied": applied_count, "skipped": skipped_count, "details": details}


def load_text_parts(tree_dir: Path) -> dict[str, etree._ElementTree]:
    """读取模板树中所有 word/*.xml 文本 part（跳过 .rels）。"""
    parts = {}
    for f in sorted(tree_dir.rglob("*.xml")):
        rel = f.relative_to(tree_dir).as_posix()
        if not rel.startswith("word/") or rel.endswith(".rels"):
            continue
        try:
            parts[rel] = etree.parse(str(f))
        except etree.XMLSyntaxError as e:
            print(f"[fill_template] 警告：跳过解析失败的 part {rel}: {e}", file=sys.stderr)
    return parts


def merge_sections_and_normalize(parts: dict) -> int:
    """后处理：合并主体部分（4 个表→1 段），保留调解意愿/证据清单前两个独立节。

    官方模板用 4 个段落级 sectPr 把表单分成 5 节：
        [5]  表 2 前（表 1 末尾双面分页）
        [12] 表 3 前（表 2 末尾双面分页）
        [19] 表 4 前（表 3 末尾双面分页）
        [24] 调解意愿前（保留！）
        [47] 文档末尾（保留！）
    合并策略：删除 [5][12][19] 三个表内分隔，保留 [24] 调解意愿节和 [47] 末尾节。
    页边距：末尾节为标准 1800twips（25mm），其他节保持原版镜像边距。
    """
    W = "{%s}" % W_NS
    removed = 0

    def _paragraph_sect_indices(body):
        """返回 body 下含段落级 sectPr 的段落在 body 内的索引（从 0 开始）。"""
        return [i for i, child in enumerate(body) if child.tag == f"{W}p"
                and child.find(f".//{W}sectPr") is not None]

    for tree in parts.values():
        body = tree.getroot().find(f"{W}body")
        if body is None:
            continue
        # 模板固定是 4 个段落级 sectPr（5 节），保留最后 2 个
        sect_indices = _paragraph_sect_indices(body)
        keep = set(sect_indices[-1:]) if len(sect_indices) >= 1 else set()
        for i in sect_indices:
            if i in keep:
                continue
            p = body[i]
            sect = p.find(f".//{W}sectPr")
            if sect is not None:
                sect.getparent().remove(sect)
                removed += 1
    return removed


def save_text_parts(tree_dir: Path, parts: dict[str, etree._ElementTree]) -> None:
    for rel, tree in parts.items():
        f = tree_dir / rel
        f.write_bytes(etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True))


def all_text_of_parts(parts: dict[str, etree._ElementTree]) -> str:
    out = []
    for tree in parts.values():
        out.append("".join(t.text or "" for t in tree.iter(Wt)))
    return "\n".join(out)


def run_batch(args) -> int:
    """批量模式：目录内每个 *-elements.json → 同名 docx（输出到 --output 目录或同目录）。"""
    files = sorted(args.batch.glob("*-elements.json"))
    if not files:
        print(f"[batch] 错误：{args.batch} 下无 *-elements.json", file=sys.stderr)
        return 2
    out_dir = args.output or args.batch  # 缺省输出回输入目录
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    for f in files:
        try:
            ct = json.loads(f.read_text(encoding="utf-8")).get("case_type", "")
            if not ct:
                print(f"  ✗ {f.name}: 缺 case_type 字段")
                fail += 1
                continue
            out = out_dir / (f.stem.replace("-elements", "") + "-要素式起诉状.docx")
            # 复用单件渲染（子进程避免规则状态串扰）
            import subprocess
            r = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()),
                                "--case-type", ct, "--elements", str(f), "--output", str(out)],
                               capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                ok += 1
                print(f"  ✓ {f.name} → {out.name}")
            else:
                fail += 1
                print(f"  ✗ {f.name}: {r.stderr.strip()[:120]}")
        except Exception as e:
            fail += 1
            print(f"  ✗ {f.name}: {e}")
    print(f"[batch] 完成 {ok}，失败 {fail}")
    return 0 if fail == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case-type", default=None,
                        choices=sorted(set(list(RULE_BUILDERS.keys()) + _generic_ns())),
                        help="精调案由 key（09-private-lending/05-divorce）或两位编号（06/15/21…通用级）；--batch 模式可省略")
    parser.add_argument("--elements", default=None, type=Path, help="elements.json 路径")
    parser.add_argument("--output", default=None, type=Path, help="输出 docx 路径（--batch 模式为输出目录）")
    parser.add_argument(
        "--templates-dir", type=Path,
        default=Path(__file__).resolve().parent.parent / "templates",
        help="OOXML 模板树根目录（默认 skill 根级 templates/）",
    )
    parser.add_argument(
        "--verify-residual", type=str, default="",
        help='替换后扫描残留旧串，逗号分隔。例: "旧姓名,旧电话"',
    )
    parser.add_argument(
        "--batch", type=Path, default=None,
        help="批量模式：目录下每个 *-elements.json 渲染为同名 .docx（按文件内 case_type 字段路由案由）",
    )
    args = parser.parse_args()

    if args.batch:
        return run_batch(args)

    if not args.elements or not args.elements.exists():
        print(f"[fill_template] 错误：elements 文件不存在 {args.elements}", file=sys.stderr)
        return 2
    if not args.case_type or not args.output:
        print("[fill_template] 错误：单件模式需 --case-type 与 --output", file=sys.stderr)
        return 2
    elements_raw = json.loads(args.elements.read_text(encoding="utf-8"))
    # 兼容两种结构：直接要素 dict / {case_type, elements:{...}} 嵌套
    if isinstance(elements_raw, dict) and "elements" in elements_raw and isinstance(elements_raw["elements"], dict):
        elements = elements_raw["elements"]
    else:
        elements = elements_raw

    tree_src, rules_builder = resolve_case(args.case_type, args.templates_dir)
    if not tree_src.is_dir():
        print(f"[fill_template] 错误：模板树不存在 {tree_src}", file=sys.stderr)
        return 2

    # 复制模板树到临时目录（绝不污染源码树）
    tmp_root = Path(tempfile.mkdtemp(prefix="ecg-render-"))
    tree_work = tmp_root / "tree"
    shutil.copytree(tree_src, tree_work)

    # 加载 → 应用规则 → 写回 → 打包
    parts = load_text_parts(tree_work)
    doc = DocParts(parts)
    rules = rules_builder(elements)
    result = apply_rules(doc, rules, elements)
    # 后处理：删段落级 sectPr（合并节，表格连续排版）
    removed = merge_sections_and_normalize(parts)
    if removed:
        print(f"[fill_template] 节合并：删除 {removed} 个段落级 sectPr（表格连续排版）")
    save_text_parts(tree_work, parts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pack_tree(tree_work, args.output)

    print(f"[fill_template] case_type = {args.case_type}")
    print(f"[fill_template] template  = {tree_src}")
    print(f"[fill_template] output    = {args.output}")
    print(f"[fill_template] rules applied={result['applied']}  skipped={result['skipped']}")

    # 残留校验
    if args.verify_residual:
        residual = [s.strip() for s in args.verify_residual.split(",") if s.strip()]
        blob = all_text_of_parts(parts)
        still = [r for r in residual if r in blob]
        if still:
            print(f"[fill_template] ⚠️ 残留校验：以下旧串仍存在，请检查：")
            for s in still:
                print(f"  - {s!r}")
        else:
            print(f"[fill_template] 残留校验：未发现残留旧串 ✓")

    # 完整性校验：输出 docx 可解包、勾选计数正常
    try:
        import zipfile as _zip
        with _zip.ZipFile(args.output) as z:
            square = checked = 0
            for name in z.namelist():
                if name.startswith("word/") and name.endswith(".xml") and not name.endswith(".rels"):
                    xml = etree.fromstring(z.read(name))
                    t = "".join(x.text or "" for x in xml.iter(Wt))
                    square += t.count("□")
                    checked += t.count("☑")
        print(f"[fill_template] 完整性：□={square} ☑={checked}")
    except Exception as e:
        print(f"[fill_template] 警告：输出 docx 二次校验失败：{e}", file=sys.stderr)
        return 3

    # 清理临时目录
    shutil.rmtree(tmp_root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())