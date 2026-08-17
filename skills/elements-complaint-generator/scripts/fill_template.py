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

def build_rules_02_private_lending(tree_dir=None) -> list[RuleFunc]:
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

def build_rules_05_divorce(tree_dir=None) -> list[RuleFunc]:
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
# 06-买卖 / 15-劳动 / 21-交通 规则集（v0.5：通用层叠加 + 案由特定）
# 模式：build_rules_NN = generic_rules.build_generic_rules(tree) + 案由特定规则
# 当事人键沿用通用语义（自然人N/法人N，顺序=模板块顺序）
# ---------------------------------------------------------------------------

def _generic_plus(tree_dir, specifics):
    import generic_rules
    return generic_rules.build_generic_rules(tree_dir) + specifics




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


def build_rules_06_sale(tree_dir=None) -> list[RuleFunc]:
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
    return _generic_plus(tree_dir, sp)


def build_rules_15_labor(tree_dir=None) -> list[RuleFunc]:
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
    return _generic_plus(tree_dir, sp)


def build_rules_21_traffic(tree_dir=None) -> list[RuleFunc]:
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
    return _generic_plus(tree_dir, sp)


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
}

# ---------------------------------------------------------------------------
# 通用级接入（v0.4）：精调案由之外的编号（"01"…"68"）自动路由到 generic_rules
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _generic_ns() -> list[str]:
    import generic_rules
    return [n for n in generic_rules.generic_case_numbers(_TEMPLATES_DIR)
            if n not in ("05", "09")]


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
        return base / tree, (lambda: RULE_BUILDERS[case_type](base / tree))
    import generic_rules
    tree = generic_rules.primary_tree_for(case_type, base)
    if tree is None:
        raise SystemExit(f"[fill_template] 错误：编号 {case_type} 无主文书模板树")
    tree_dir = base / tree
    return tree_dir, (lambda: generic_rules.build_generic_rules(tree_dir))


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


def save_text_parts(tree_dir: Path, parts: dict[str, etree._ElementTree]) -> None:
    for rel, tree in parts.items():
        f = tree_dir / rel
        f.write_bytes(etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True))


def all_text_of_parts(parts: dict[str, etree._ElementTree]) -> str:
    out = []
    for tree in parts.values():
        out.append("".join(t.text or "" for t in tree.iter(Wt)))
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case-type", required=True,
                        choices=sorted(set(list(RULE_BUILDERS.keys()) + _generic_ns())),
                        help="精调案由 key（09-private-lending/05-divorce）或两位编号（06/15/21…通用级）")
    parser.add_argument("--elements", required=True, type=Path, help="elements.json 路径")
    parser.add_argument("--output", required=True, type=Path, help="输出 docx 路径")
    parser.add_argument(
        "--templates-dir", type=Path,
        default=Path(__file__).resolve().parent.parent / "templates",
        help="OOXML 模板树根目录（默认 skill 根级 templates/）",
    )
    parser.add_argument(
        "--verify-residual", type=str, default="",
        help='替换后扫描残留旧串，逗号分隔。例: "旧姓名,旧电话"',
    )
    args = parser.parse_args()

    if not args.elements.exists():
        print(f"[fill_template] 错误：elements 文件不存在 {args.elements}", file=sys.stderr)
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
    rules = rules_builder()
    result = apply_rules(doc, rules, elements)
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