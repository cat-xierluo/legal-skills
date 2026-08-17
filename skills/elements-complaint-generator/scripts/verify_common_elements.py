#!/usr/bin/env python3
"""通用要素同构性验证（T1）：扫描 templates/ 全部树，对通用标记做存在性 + 形态聚类。

目的
----
为 references/common-elements.md 的"通用层范围"提供证据：
- 哪些标记在哪些树群中存在（聚类 → 通用层的分层定义）
- 同一标记在不同树中的文本形态是否一致（渲染规则的跨案由复用可行性）

用法
----
python scripts/verify_common_elements.py [--templates templates] [--sample 5]
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
Wt = "{%s}t" % W_NS
Wp = "{%s}p" % W_NS

# 通用标记：key = 标记名，needle = 段落包含即算存在
MARKERS = {
    # 当事人-自然人
    "姓名：": "姓名：",
    "性别：男□": "性别：男□",
    "出生日期：": "出生日期：",
    "民族：": "民族：",
    "工作单位：": "工作单位：",
    "住所地（户籍所在地）：": "住所地（户籍所在地）：",
    "证件类型：": "证件类型：",
    "证件号码：": "证件号码：",
    # 当事人-法人
    "名称：": "名称：",
    "法定代表人 / 负责人：": "法定代表人 / 负责人：",
    "统一社会信用代码：": "统一社会信用代码：",
    # 代理人
    "委托诉讼代理人": "委托诉讼代理人",
    "代理权限：": "代理权限：",
    # 保全 / 管辖
    "诉前保全（词）": "诉前保全",
    "保全法院：": "保全法院：",
    "保全案号：": "保全案号：",
    "约定管辖（词）": "约定管辖",
    # 调解意愿
    "调解标题（是否了解调解作为非诉）": "是否了解调解作为非诉",
    "了解□": "了解□",
    "是否考虑先行调解": "是否考虑先行调解",
    "暂不确定，想要了解更多内容□": "暂不确定，想要了解更多内容□",
    # 尾部
    "具状人（签字、盖章）：": "具状人（签字、盖章）：",
    "证据清单": "证据清单",
}

# 形态聚类用标记（对包含该标记的整段做空白归一后聚类）
SHAPE_KEYS = ["姓名：", "性别：男□", "出生日期：", "性别行的女□", "民族：", "证件类型："]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def tree_paragraphs(tree_dir: Path) -> list[str]:
    doc = tree_dir / "word" / "document.xml"
    if not doc.exists():
        return []
    xml = etree.parse(str(doc))
    return ["".join(t.text or "" for t in p.iter(Wt)) for p in xml.iter(Wp)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--templates", type=Path, default=Path(__file__).resolve().parent.parent / "templates")
    parser.add_argument("--sample", type=int, default=5, help="每组抽样展示树名数")
    args = parser.parse_args()

    trees = sorted(d for d in args.templates.iterdir() if d.is_dir())
    print(f"[verify] 扫描 {len(trees)} 棵树")

    presence: dict[str, dict[str, bool]] = {}     # tree -> marker -> present
    shapes: dict[str, dict[str, set[str]]] = {}   # tree -> shape_key -> {normalized para}
    for td in trees:
        paras = tree_paragraphs(td)
        presence[td.name] = {k: any(n in p for p in paras) for k, n in MARKERS.items()}
        sh: dict[str, set[str]] = {}
        for sk in SHAPE_KEYS:
            needle = "女□" if sk == "性别行的女□" else sk
            hits = {norm(p) for p in paras if needle in p}
            sh[sk] = hits
        shapes[td.name] = sh

    # ① 聚类：按存在性签名分组
    groups: dict[tuple, list[str]] = defaultdict(list)
    for name, sig in presence.items():
        groups[tuple(sig.items())].append(name)

    def sig_label(sig: tuple) -> str:
        d = dict(sig)
        present = [k for k, v in d.items() if v]
        absent = [k for k, v in d.items() if not v]
        return present, absent

    print(f"\n[verify] === 存在性签名聚类：{len(groups)} 组 ===")
    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    for sig, members in ordered:
        present, absent = sig_label(sig)
        print(f"\n组大小 {len(members)}：")
        print(f"  有：{'、'.join(present)}")
        if absent:
            print(f"  无：{'、'.join(absent)}")
        print(f"  成员（前 {args.sample}）：{'、'.join(members[:args.sample])}")

    # ② 形态一致性：对"最大组"内每个形态键统计 variant
    biggest_members = ordered[0][1]
    print(f"\n[verify] === 最大组（{len(biggest_members)} 棵）形态一致性 ===")
    for sk in SHAPE_KEYS:
        all_variants: dict[str, list[str]] = defaultdict(list)
        for m in biggest_members:
            for v in shapes[m].get(sk, set()):
                all_variants[v].append(m)
        print(f"\n[{sk}] {len(all_variants)} 种形态：")
        for v, owners in sorted(all_variants.items(), key=lambda kv: -len(kv[1]))[:6]:
            print(f"  ×{len(owners):3d}  {v[:70]!r}  例：{owners[0]}")

    # ③ 标记覆盖率总表（跨全部树）
    print(f"\n[verify] === 标记覆盖率（全部 {len(trees)} 棵）===")
    for k in MARKERS:
        n = sum(1 for name in trees if presence[name.name][k])
        print(f"  {n:3d}/{len(trees)}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())