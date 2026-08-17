#!/usr/bin/env python3
"""模板字段反推（T2）：从模板树生成字段骨架 Markdown，作为 case-types/NN-*.md 的底稿。

原理
----
解析模板树 word/document.xml，按文档序遍历段落：
- 识别**节标题**（当事人信息 / 诉讼请求 / 答辩事项 / 事实与理由 / 调解意愿 / 证据清单…）分组
- 每段分类：
  - `勾选`：含 □ → 提取全部 "X□" 选项
  - `标签填空`：含 "标签：" 形态 → 提取标签列表
  - `日期占位`：含 "年/月/日" 空白复合占位
  - `文本`：其他（标题/说明/整段填写区）
- 输出 Markdown 表：序号 | 类型 | 段落原文（空白归一）| 选项/标签 | 建议要素路径（留空待补）

人/Agent 拿到骨架后只需：补"建议要素路径"、写 occurrence 映射、补抽取提示。

用法
----
python scripts/dump_template_fields.py --tree templates/05-离婚纠纷-民事起诉状 \
    [--output references/case-types/05-divorce-skeleton.md]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
Wt = "{%s}t" % W_NS
Wp = "{%s}p" % W_NS

SECTION_TITLES = [
    "当事人信息", "诉讼请求", "答辩事项", "事实与理由", "答辩理由",
    "对纠纷解决方式的意愿", "证据清单", "关联案件信息",
    "约定管辖和诉前保全", "诉前保全", "诉前保全及鉴定申请",
    "其他", "附件",
]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def paras_of(tree_dir: Path) -> list[str]:
    doc = tree_dir / "word" / "document.xml"
    if not doc.exists():
        raise FileNotFoundError(f"缺 word/document.xml：{tree_dir}")
    xml = etree.parse(str(doc))
    return [norm("".join(t.text or "" for t in p.iter(Wt))) for p in xml.iter(Wp)]


def extract_options(text: str) -> list[str]:
    """提取 'X□' 选项（X 为 1-8 个非空白/非分隔符字符）。"""
    return re.findall(r"([^\s□：:，,、/（）()]{1,8})□", text)


def extract_labels(text: str) -> list[str]:
    """提取 '标签：' 形态的标签。"""
    return [m for m in re.findall(r"([^：:\s]{1,15})[：:]", text)]


def classify(text: str) -> tuple[str, str]:
    """返回 (类型, 选项或标签描述)。"""
    if "□" in text:
        opts = extract_options(text)
        return "勾选", "、".join(opts) if opts else "（含 □）"
    labels = extract_labels(text)
    if re.search(r"年\s*月\s*日", text):
        return "日期占位", "、".join(labels) if labels else ""
    if labels:
        return "标签填空", "、".join(labels)
    return "文本", ""


def is_section_title(text: str) -> str | None:
    t = text.strip()
    if not t or len(t) > 16:
        return None
    for st in SECTION_TITLES:
        if st in t and re.fullmatch(r"[\d\.\s、（）()一-鿿]*" + re.escape(st) + r"[\d\.\s、（）()一-鿿]*", t):
            return st
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tree", required=True, type=Path, help="模板树目录")
    parser.add_argument("--output", type=Path, default=None, help="输出 .md（缺省打印 stdout）")
    args = parser.parse_args()

    paras = [p for p in paras_of(args.tree) if p]
    lines: list[str] = []
    lines.append(f"# {args.tree.name} — 字段骨架（脚本反推，待补全）")
    lines.append("")
    lines.append(f"> 由 `scripts/dump_template_fields.py --tree {args.tree.name}` 生成于模板树；")
    lines.append("> 「建议要素路径」列请人工/Agent 补齐，并补 occurrence 映射与抽取提示后升级为正式 case-types 文档。")
    lines.append("")

    section = "（开头）"
    idx = 0
    lines.append(f"## {section}")
    lines.append("")
    lines.append("| # | 类型 | 段落原文 | 选项 / 标签 | 建议要素路径 |")
    lines.append("|---|---|---|---|---|")
    for p in paras:
        st = is_section_title(p)
        if st and st != section:
            section = st
            lines.append("")
            lines.append(f"## {section}")
            lines.append("")
            lines.append("| # | 类型 | 段落原文 | 选项 / 标签 | 建议要素路径 |")
            lines.append("|---|---|---|---|---|")
            continue
        idx += 1
        typ, meta = classify(p)
        display = p if len(p) <= 60 else p[:57] + "…"
        lines.append(f"| {idx} | {typ} | {display} | {meta} | | ")

    out = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out, encoding="utf-8")
        print(f"[dump] {args.tree.name} → {args.output}（{idx} 段）")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())