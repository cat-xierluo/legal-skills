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
    --case-type 02-private-lending \\
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
    new_segment = prefix + value + suffix
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
                            occurrence: int = 0) -> RuleFunc:
    """text-replace 规则：定位 match_text 所在段（按出现顺序取第 occurrence 个），替换。"""
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
            replace_in_paragraph(p, match_text, str(value))
        return True
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
# 02-民间借贷 规则集（与 references/case-types/02-private-lending.md §二 对应）
# ---------------------------------------------------------------------------

def build_rules_02_private_lending() -> list[RuleFunc]:
    rules: list[RuleFunc] = []

    # --- 原告（自然人，第一个）---
    # occurrence 0=原告 1=被告 2=第三人自然人 3=第三人法人（按段落出现顺序）
    e = "当事人.原告"
    rules += [
        make_text_replace_rule(f"{e}.姓名", "姓名：", occurrence=0),
        make_checkbox_rule(f"{e}.性别", "性别：男□    女□", occurrence=0),
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

    # --- 被告（自然人，第一个）---
    e = "当事人.被告"
    rules += [
        make_text_replace_rule(f"{e}.姓名", "姓名：", occurrence=1),
        make_checkbox_rule(f"{e}.性别", "性别：男□    女□", occurrence=1),
        make_text_fill_rule(f"{e}.出生日期", "出生日期：", "日", transform=fmt_date, occurrence=1),
        make_text_replace_rule(f"{e}.民族", "民族：", occurrence=1),
        make_text_replace_rule(f"{e}.工作单位", "工作单位：", occurrence=1),
        make_text_replace_rule(f"{e}.职务", "职务：", occurrence=1),
        make_text_replace_rule(f"{e}.联系电话", "联系电话：", occurrence=1),
        make_text_replace_rule(f"{e}.住所地", "住所地（户籍所在地）：", occurrence=1),
        make_text_replace_rule(f"{e}.经常居住地", "经常居住地：", occurrence=1),
        make_text_replace_rule(f"{e}.证件类型", "证件类型：", occurrence=1),
        make_text_replace_rule(f"{e}.证件号码", "证件号码：", occurrence=1),
    ]

    # --- 委托诉讼代理人 ---
    # 「姓名：」occurrence=0/1/2/3 已被 原告/被告/第三人占用；代理人姓名走专用规则
    e = "当事人.委托诉讼代理人.0"

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

    rules.append(rule_agent_name)
    rules += [
        make_text_replace_rule(f"{e}.单位", "单位：", occurrence=1),
        make_text_replace_rule(f"{e}.职务", "职务：", occurrence=1),
        make_text_replace_rule(f"{e}.联系电话", "联系电话：", occurrence=1),
    ]

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
        make_checkbox_rule("诉讼请求.利息.请求至实际清偿之日", "是否请求支付至实际清偿之日止：是□    否□"),
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
        make_text_replace_rule("事实与理由.借款利率.合同条款", "合同条款：第    条"),
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
        make_text_replace_rule("事实与理由.还款情况.已还本金", "已还本金：          元"),
        make_text_replace_rule("事实与理由.还款情况.已还利息", "已还利息：          元，还息至        年        月         日"),
        make_checkbox_rule("事实与理由.是否存在逾期还款.勾选", "是□    逾期时间：              至今已逾期"),
        make_text_replace_rule("事实与理由.是否存在逾期还款.逾期时间", "逾期时间：              至今已逾期"),
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

    # --- 对纠纷解决方式的意愿 ---
    def rule_tiaojie_zongti(doc, elements):
        v = _get_path(elements, "对纠纷解决方式的意愿.是否了解调解")
        if not v:
            return False
        # 第一处「了解□    不了解□」紧跟"是否了解调解…"标题段
        paragraphs = list(iter_paragraphs(doc))
        for i, p in enumerate(paragraphs):
            if "是否了解调解作为非诉" in p.text:
                # 向后找最近的勾选段
                for q in paragraphs[i:]:
                    if "了解□    不了解□" in q.text:
                        target = "了解□" if v == "了解" else "不了解□"
                        replace_in_paragraph(q, target, target.replace("□", "☑"))
                        return True
                break
        return False
    rules.append(rule_tiaojie_zongti)

    def rule_likai_jiechu_benefits(doc, elements):
        v = _get_path(elements, "对纠纷解决方式的意愿.是否了解先行调解好处")
        if not v or not isinstance(v, list) or len(v) != 5:
            return False
        # 5 处「了解□ 不了解□」按文档顺序去重后逐个填
        seen_elements: set = set()
        applied = 0
        for p in iter_paragraphs(doc):
            if p._p in seen_elements:
                continue
            if "了解□" in p.text and "不了解□" in p.text:
                seen_elements.add(p._p)
                target_value = v[applied] if applied < 5 else None
                if target_value == "了解":
                    replace_in_paragraph(p, "了解□", "了解☑")
                elif target_value == "不了解":
                    replace_in_paragraph(p, "不了解□", "不了解☑")
                applied += 1
                if applied >= 5:
                    break
        return applied > 0
    rules.append(rule_likai_jiechu_benefits)

    def rule_kaolv_tiaojie(doc, elements):
        v = _get_path(elements, "对纠纷解决方式的意愿.是否考虑先行调解")
        if not v:
            return False
        mapping = {"是": "是□ 否□", "否": "是□ 否□", "暂不确定": "暂不确定，想要了解更多内容□"}
        target = mapping.get(v)
        if not target:
            return False
        # 最后一处「是□ 否□」（前面已被诉讼费用等规则勾过的跳过）
        paragraphs = [p for p in iter_paragraphs(doc) if target in p.text]
        for p in reversed(paragraphs):
            if "☑" not in p.text or p.text.count("☑") == 0:
                replace_in_paragraph(p, ("是□" if v == "是" else "否□") if v != "暂不确定" else target,
                                     (("是☑" if v == "是" else "否☑") if v != "暂不确定" else target.replace("□", "☑")))
                return True
        return False
    rules.append(rule_kaolv_tiaojie)

    # --- 具状人/日期 ---
    rules += [
        make_text_replace_rule("具状人_签字_盖章", "具状人（签字、盖章）："),
        make_text_fill_rule("具状日期", "日期：", "日", transform=fmt_date),
    ]

    return rules


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

CASE_TYPE_TO_TREE = {
    "02-private-lending": "02-民间借贷纠纷民事起诉状",
}


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
    parser.add_argument("--case-type", required=True, choices=list(CASE_TYPE_TO_TREE.keys()))
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

    tree_src = args.templates_dir / CASE_TYPE_TO_TREE[args.case_type]
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
    rules = build_rules_02_private_lending()
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