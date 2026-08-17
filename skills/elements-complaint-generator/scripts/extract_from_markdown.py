#!/usr/bin/env python3
"""常规起诉状（Markdown）→ 要素 elements.json 抽取器（C 入口）。

读取律师已写好的"散文版"起诉状（Markdown 格式），按当前案由的 Schema 抽出
结构化要素，写到 elements.json，供 fill_template.py 后续渲染。

设计原则
--------
- **正则优先**：常见当事人字段（姓名、性别、电话、证件号）有强模板特征，用 regex 抽取
- **段落分类**：用小标题（## 一、二、三、）把 md 内容切成"诉讼请求 / 事实与理由 / 调解意愿"等段
- **人机协作**：抽取结果写到 elements.json 后，必须人工复核（CLI 提示）→ 再渲染
- **不臆造**：抽取不到字段保留空值，由人补齐；不强行编造

适用场景
--------
- v0.1 MVP：02 民间借贷 + 01 离婚
- 输入：起诉状.md（律师手写或 AI 生成的常规版）
- 输出：elements.json（按 case-types/{案由}.md §一的 Schema）

依赖
----
- Python 3.11+
- 无第三方依赖（纯 stdlib）

示例
----
python scripts/extract_from_markdown.py \\
    --case-type 02-private-lending \\
    --input tests/fixtures/02-private-lending-complaint.md \\
    --output tests/output/02-private-lending-elements.json

然后人工编辑 elements.json 复核后：
python scripts/fill_template.py \\
    --case-type 02-private-lending \\
    --elements tests/output/02-private-lending-elements.json \\
    --output tests/output/02-private-lending-filled.docx
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# 通用 Markdown 段落切分
# ---------------------------------------------------------------------------

def split_into_sections(md_text: str) -> dict[str, str]:
    """把 md 切成 {"title": ..., "原告": ..., "被告": ..., "诉讼请求": ..., "事实与理由": ..., "调解意愿": ..., "other": ...}

    策略：先用 "## " 二级标题切大段（"## 诉讼请求" / "## 事实与理由" 等），
    再在每段内按当事人特征归类。
    """
    md_text = md_text.strip()
    # 按 "## " 二级标题切
    # 找到所有二级标题位置
    h2_pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    parts: list[tuple[str, str]] = []  # [(title, body), ...]
    last_end = 0
    last_title = ""
    for m in h2_pattern.finditer(md_text):
        if last_end > 0:
            body = md_text[last_end: m.start()].strip()
            parts.append((last_title, body))
        last_title = m.group(1).strip()
        last_end = m.end()
    if last_end > 0:
        body = md_text[last_end:].strip()
        parts.append((last_title, body))
    # 标题前部分作 header（包含 "原告/被告/委托诉讼代理人" 等当事人段）
    first_h2_pos = h2_pattern.search(md_text)
    header = md_text[: first_h2_pos.start()].strip() if first_h2_pos else md_text

    sections: dict[str, list[str]] = {
        "title": [], "原告": [], "被告": [], "第三人": [],
        "委托诉讼代理人": [], "诉讼请求": [], "事实与理由": [],
        "调解意愿": [], "具状": [], "other": [],
    }
    if header:
        # 头部分可能含 # 标题 + 原告/被告/委托代理人
        for line in header.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("# "):
                if not sections["title"]:
                    sections["title"].append(line)
            elif "委托诉讼代理人" in line:
                sections["委托诉讼代理人"].append(line)
            elif re.search(r"^\s*原告[：:]", line):
                sections["原告"].append(line)
            elif re.search(r"^\s*被告[：:]", line):
                sections["被告"].append(line)
            elif "第三人" in line and "被告" not in line:
                sections["第三人"].append(line)

    # 每个 ## 段按标题分类
    for title, body in parts:
        if not body:
            continue
        body = body.strip()
        if "诉讼请求" in title or "诉请" in title or "请求事项" in title:
            sections["诉讼请求"].append(body)
        elif "事实" in title or "理由" in title or "经审理" in title:
            sections["事实与理由"].append(body)
        elif "调解" in title or "纠纷解决" in title:
            sections["调解意愿"].append(body)
        elif "具状" in title or "此致" in title or "落款" in title:
            sections["具状"].append(body)
        else:
            sections["other"].append(f"## {title}\n{body}")
    # 具状/日期通常在最后一段
    if not sections["具状"] and parts:
        last_body = parts[-1][1]
        if "具状人" in last_body or "此致" in last_body:
            sections["具状"].append(last_body)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


# ---------------------------------------------------------------------------
# 当事人字段抽取（自然人）—— 面向"原告：张三，男，1985年3月12日出生，汉族，..."
# 这种连贯描述式，每个字段用严格锚定 + 短截取
# ---------------------------------------------------------------------------

# 顺序敏感：先抽短字段（姓名/性别/民族），再抽含"出生"长字段，避免 pattern 互相吞噬
PARTY_FIELD_PATTERNS = [
    # 姓名（开头总是"原告/被告：张三，"或"姓名：张三"）
    ("姓名", r"(?:姓名|原告|被告|第三人)[：:]\s*([^\s，,。；;、]{2,4})"),
    # 性别（必须紧跟逗号短字段）
    ("性别", r"，([男女])[，,]"),
    # 出生日期（含"出生"字样，避免吞其他字段）
    ("出生日期", r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)\s*出生"),
    ("出生日期", r"出生(?:日期)?[：:]?\s*(\d{4}[\-\.年]\d{1,2}[\-\.月]\d{1,2}日?)"),
    # 民族（紧跟"，X族，"或"民族：族"）
    ("民族", r"，(\S{1,3}族)[，,]"),
    ("民族", r"民族[：:]\s*(\S{1,3}族)"),
    # 工作单位 / 职务 / 电话（电话后可能有冒号也可能没）
    ("工作单位", r"(?:工作单位|单位)[：:\s]+([^，,。]+?)(?=[，,。；;]|住所|经常居住地|身份证|电话|职务)"),
    ("职务", r"职务[：:\s]+([^，,。]+?)(?=[，,。；;]|住所|经常居住地|身份证|电话)"),
    ("联系电话", r"(?:联系电话|手机|电话)\s*[：:]?\s*([\d\-]{11,})"),
    # 住所
    ("住所地", r"(?:住所地|住址|户籍地|户籍所在地)\s*[：:]?\s*([^，,。]+?)(?=[，,。；;]|经常居住地|身份证)"),
    ("经常居住地", r"经常居住地\s*[：:]?\s*([^，,。]+?)(?=[，,。；;]|身份证|电话)"),
    # 证件
    ("证件类型", r"证件类型\s*[：:]?\s*(身份证|护照|港澳通行证|台胞证|军官证)"),
    ("证件号码", r"(?:身份证|证件)号码\s*[：:]?\s*([\dxX]+)"),
    ("证件号码", r"身份证\s*号?\s*[：:]?\s*([\dXx]{15,18})"),
    ("统一社会信用代码", r"统一社会信用代码\s*[：:]?\s*([\dA-Z]{18})"),
    ("法定代表人", r"法定代表人\s*[：:\/]?\s*([^\s，,。]+)"),
]


def extract_party(text: str, party_type: str) -> dict:
    """从当事人段落里抽要素。party_type: 原告/被告/第三人/委托诉讼代理人"""
    elements: dict = {"主体类型": "自然人"}
    for field, pattern in PARTY_FIELD_PATTERNS:
        if field in elements and elements[field]:
            continue
        m = re.search(pattern, text)
        if m:
            value = m.group(1).strip().rstrip("，,。；;")
            if field == "姓名" and value in ("原告", "被告", "第三人", "姓名"):
                continue
            if field == "民族" and "出生" in value:
                continue
            # 出生日期归一化为 ISO（YYYY-MM-DD），便于 fill_template.py 的 fmt_date 再格式化
            if field == "出生日期":
                value = _normalize_date(value)
            elements[field] = value
    if elements.get("统一社会信用代码") or elements.get("法定代表人"):
        elements["主体类型"] = "法人或非法人组织"
    return elements


def _normalize_date(s: str) -> str:
    """把 '1985年3月12日' / '1985-3-12' / '1985.3.12' 归一为 '1985-03-12'。失败返回原串。"""
    if not s:
        return s
    # 1985年3月12日
    m = re.match(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 1985-3-12 / 1985.3.12 / 1985/3/12
    m = re.match(r"(\d{4})[\-\.\/](\d{1,2})[\-\.\/](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return s


# ---------------------------------------------------------------------------
# 02 民间借贷专属抽取
# ---------------------------------------------------------------------------

def extract_02_private_lending(sections: dict[str, str]) -> dict:
    elements: dict = {"当事人": {}, "诉讼请求": {}, "约定管辖和诉前保全": {}, "事实与理由": {}, "对纠纷解决方式的意愿": {}}

    # 原告
    if sections.get("原告"):
        elements["当事人"]["原告"] = extract_party(sections["原告"], "原告")
    else:
        elements["当事人"]["原告"] = {}

    # 被告
    if sections.get("被告"):
        elements["当事人"]["被告"] = extract_party(sections["被告"], "被告")
    else:
        elements["当事人"]["被告"] = {}

    # 委托诉讼代理人（可选）
    if sections.get("委托诉讼代理人"):
        agent_text = sections["委托诉讼代理人"]
        agent = extract_party(agent_text, "委托诉讼代理人")
        # 委托代理人姓名：用"姓名/王律师，"模式；或单独"代理人：王律师"
        m = re.search(r"(?:委托诉讼代理人|代理人)[：:]?\s*([^\s，,。；;、]+?)(?:[，,]|某|的|，)", agent_text)
        if m:
            agent["姓名"] = m.group(1).strip()
        # 委托单位
        m = re.search(r"(?:某)?([^，,。]+?律师事务所|律师事务所)", agent_text)
        if m:
            agent.setdefault("单位", m.group(1).strip())
        elements["当事人"]["委托诉讼代理人"] = [agent]
    else:
        elements["当事人"]["委托诉讼代理人"] = []

    # 诉讼请求
    sr_text = sections.get("诉讼请求", "")
    elements["诉讼请求"] = extract_02_litigation_request(sr_text)

    # 事实与理由
    fr_text = sections.get("事实与理由", "")
    elements["事实与理由"] = extract_02_facts_reasons(fr_text)

    # 调解意愿（默认填"了解"+全部了解）
    if sections.get("调解意愿"):
        elements["对纠纷解决方式的意愿"] = extract_02_mediation(sections["调解意愿"])
    else:
        elements["对纠纷解决方式的意愿"] = {
            "是否了解调解": "了解",
            "是否了解先行调解好处": ["了解"] * 5,
            "是否考虑先行调解": "是",
        }

    # 具状人/日期
    ji_text = sections.get("具状", "")
    if ji_text:
        m = re.search(r"具状人[：:]?\s*([^\n]+)", ji_text)
        if m:
            elements["具状人_签字_盖章"] = m.group(1).strip()
        m = re.search(r"(\d{4}[\-\.年]\d{1,2}[\-\.月]\d{1,2}日?)", ji_text)
        if m:
            elements["具状日期"] = m.group(1).replace(".", "-").replace("年", "-").replace("月", "-").replace("日", "")

    return elements


def extract_02_litigation_request(text: str) -> dict:
    """从诉讼请求段抽要素。"""
    res: dict = {}
    # 本金（"借款本金 500000.00 元"）
    m = re.search(r"(?:借款)?本金[^\d]*?([\d,\.]+)\s*元", text)
    if m:
        res["本金"] = {"尚欠金额": m.group(1).replace(",", "")}
    # 利息（"借款利息 180000.00 元"）
    m = re.search(r"(?:借款)?利息[^\d]*?([\d,\.]+)\s*元", text)
    if m:
        res["利息"] = {"尚欠利息": m.group(1).replace(",", "")}
    # 利率
    m = re.search(r"(?:年利率|月利率|利率)\s*[：:]?\s*(\d+(?:\.\d+)?)\s*[%％]", text)
    if m:
        rate = m.group(1)
        unit = "年" if "年" in m.group(0) else ("月" if "月" in m.group(0) else "年")
        res.setdefault("利息", {})["计算方式"] = f"按{rate}%/{unit}计算"
    # 律师费
    m = re.search(r"律师费\s*[：:]?\s*([\d,\.]+)\s*元", text)
    if m:
        res["是否主张实现债权的费用"] = {"勾选": True, "明细": f"律师费 {m.group(1).replace(',', '')} 元"}
    # 诉讼费用
    if "诉讼费" in text or "诉讼费用" in text:
        res["是否主张诉讼费用"] = True
    return res


def extract_02_facts_reasons(text: str) -> dict:
    """从事实与理由段抽要素。"""
    res: dict = {}
    # 签订主体
    m = re.search(r"出借人[：:]?\s*([^\n，,。]+)", text)
    if m:
        res.setdefault("签订主体", {})["出借人"] = m.group(1).strip()
    m = re.search(r"借款人[：:]?\s*([^\n，,。]+?)(?:[，,。]|借款金额|约定)", text)
    if m:
        res.setdefault("签订主体", {})["借款人"] = m.group(1).strip()
    # 借款金额
    m = re.search(r"借款(?:金额)?[：:]?\s*人民币?\s*([\d,\.]+)\s*元", text)
    if m:
        res.setdefault("借款金额", {})["约定"] = m.group(1).replace(",", "")
    # 借款期限
    m = re.search(r"借款期限[：:]?\s*(\d{4}[\-\.年]\d{1,2}[\-\.月]\d{1,2}日?)\s*起?(?:至|到)\s*(\d{4}[\-\.年]\d{1,2}[\-\.月]\d{1,2}日?)\s*止?", text)
    if m:
        res.setdefault("借款期限", {})["约定期限起"] = _normalize_date(m.group(1))
        res.setdefault("借款期限", {})["约定期限止"] = _normalize_date(m.group(2))
        res["借款期限"]["是否到期"] = True
    # 借款利率
    m = re.search(r"(?:约定)?(?:年利率|月利率|利率)[：:]?\s*(\d+(?:\.\d+)?)\s*[%％]", text)
    if m:
        res.setdefault("借款利率", {})["数值"] = m.group(1)
        res["借款利率"]["单位"] = "年"
    # 还款情况
    m = re.search(r"(?:已还本金|已归还本金)[：:]?\s*([\d,\.]*)\s*元", text)
    if m:
        res.setdefault("还款情况", {})["已还本金"] = (m.group(1) or "0").replace(",", "")
    # 是否逾期
    if "逾期" in text:
        res.setdefault("是否存在逾期还款", {})["勾选"] = True
    return res


def extract_02_mediation(text: str) -> dict:
    res = {"是否了解调解": "了解", "是否了解先行调解好处": ["了解"] * 5, "是否考虑先行调解": "是"}
    if "不同意调解" in text or "不愿调解" in text:
        res["是否考虑先行调解"] = "否"
    elif "暂不确定" in text or "暂不考虑" in text:
        res["是否考虑先行调解"] = "暂不确定"
    if "不了解" in text:
        res["是否了解调解"] = "不了解"
    return res


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

CASE_TYPE_TO_EXTRACTOR = {
    "02-private-lending": extract_02_private_lending,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case-type", required=True, choices=list(CASE_TYPE_TO_EXTRACTOR.keys()))
    parser.add_argument("--input", required=True, type=Path, help="起诉状 .md 路径")
    parser.add_argument("--output", required=True, type=Path, help="elements.json 输出路径")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"[extract_from_markdown] 错误：输入不存在 {args.input}", file=sys.stderr)
        return 2

    md_text = args.input.read_text(encoding="utf-8")
    sections = split_into_sections(md_text)
    extractor = CASE_TYPE_TO_EXTRACTOR[args.case_type]
    elements = extractor(sections)

    # 包装成 sample fixture 同样的格式（带 case_type / case_name / elements）
    output_doc = {
        "case_type": args.case_type,
        "case_name": args.input.stem,
        "extracted_at": datetime.now().isoformat(),
        "source_md": str(args.input),
        "elements": elements,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_doc, ensure_ascii=False, indent=2), encoding="utf-8")

    # 打印人工复核提示
    print(f"[extract_from_markdown] case_type = {args.case_type}")
    print(f"[extract_from_markdown] input     = {args.input}")
    print(f"[extract_from_markdown] output    = {args.output}")
    print()
    print("⚠️  请人工复核 elements.json 的要素（特别是未抽到的字段）：")
    print(f"  - 打开 {args.output}")
    print(f"  - 检查 '诉讼请求.本金.尚欠金额'、'事实与理由.借款利率.数值' 等关键字段是否已抽取")
    print(f"  - 补齐缺失字段（特别是勾选类字段：是否要求提前还款、是否主张担保权利 等）")
    print(f"  - 复核 '对纠纷解决方式的意愿'（默认全勾'了解'/'是'，按案件调整）")
    print()
    print("复核完成后跑：")
    print(f"  python scripts/fill_template.py --case-type {args.case_type} \\")
    print(f"      --elements {args.output} \\")
    print(f"      --output <目标>.docx")

    return 0


if __name__ == "__main__":
    sys.exit(main())