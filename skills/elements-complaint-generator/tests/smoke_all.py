#!/usr/bin/env python3
"""全案由冒烟测试：68 个编号逐个用通用样本渲染，验证当事人/调解/落款块可用。

对每个编号（01-68）：
- 解析主文书树（起诉状/自诉状/申请书优先；纯答辩编号自动跳过定位）
- 用 tests/fixtures/generic-smoke.json（当事人+调解+具状）渲染
- 断言：姓名：王五 + 性别勾选；含调解块时 了解☑ 单勾且无双勾；
  含具状块时 日期落位；全文无双"日"；产物 zip 可解析
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from lxml import etree

from fill_template import (Wt, Wp, resolve_case, apply_rules,
                           load_text_parts, save_text_parts, DocParts)
from pack_docx import pack_tree
from generic_rules import generic_case_numbers

SKILL_DIR = Path(__file__).resolve().parent.parent


def tree_full_text(parts) -> str:
    chunks = []
    for tree in parts.values():
        for p in tree.iter(Wp):
            chunks.append("".join(t.text or "" for t in p.iter(Wt)))
    return "\n".join(chunks)


def render_case(nn: str, elements: dict, out: Path) -> list[str]:
    """渲染一个编号，返回失败断言列表（空=通过）。"""
    tree_src, builder = resolve_case(nn, SKILL_DIR / "templates")
    probe_text = tree_full_text(load_text_parts(tree_src))
    has_mediation = "是否了解调解作为非诉" in probe_text
    has_signature = "具状人（签字、盖章）" in probe_text
    has_sex_row = "性别：男" in probe_text
    has_legal_row = "统一社会信用代码：" in probe_text
    has_ltd_option = "有限责任公司□" in probe_text
    # 是否存在自然人当事人块（法人-only 文书如 55 行政答辩状无）
    from generic_rules import _find_party_anchor, _paras
    probe_paras = _paras(DocParts(load_text_parts(tree_src)))
    has_natural_party = len(_find_party_anchor(probe_paras)) >= 1

    tmp = Path(tempfile.mkdtemp(prefix="smoke-"))
    tw = tmp / "tree"
    shutil.copytree(tree_src, tw)
    parts = load_text_parts(tw)
    apply_rules(DocParts(parts), builder(), elements)
    save_text_parts(tw, parts)
    out.parent.mkdir(parents=True, exist_ok=True)
    pack_tree(tw, out)
    shutil.rmtree(tmp, ignore_errors=True)

    with zipfile.ZipFile(out) as z:
        xml = etree.fromstring(z.read("word/document.xml"))
    full = "\n".join("".join(t.text or "" for t in p.iter(Wt)).strip()
                     for p in xml.iter(Wp))

    fails = []
    if has_natural_party and "姓名：王五" not in full:
        fails.append("姓名：王五缺失")
    if has_sex_row and "性别：男☑" not in full:
        fails.append("性别勾选缺失")
    if has_legal_row and "名称：某科技有限公司" not in full:
        fails.append("法人名称缺失")
    if has_ltd_option and "有限责任公司☑" not in full:
        fails.append("法人类型勾选缺失")
    if has_mediation:
        if "了解☑    不了解□" not in full:
            fails.append("调解勾选缺失")
        if "了解☑    不了解☑" in full:
            fails.append("调解双勾")
    if has_signature and "日期：2026年8月17日" not in full:
        fails.append("具状日期缺失")
    if "日日" in full:
        fails.append("双日哨兵")
    return fails


def main() -> int:
    elements = json.loads((SKILL_DIR / "tests/fixtures/generic-smoke.json")
                          .read_text(encoding="utf-8"))["elements"]
    out_dir = SKILL_DIR / "tests/output/smoke"
    nns = generic_case_numbers(SKILL_DIR / "templates")
    ok, failures = 0, []
    for nn in nns:
        try:
            fails = render_case(nn, elements, out_dir / f"gen-{nn}.docx")
        except Exception as e:
            fails = [f"异常: {type(e).__name__}: {e}"]
        if fails:
            failures.append((nn, fails))
            print(f"  ✗ {nn}: {fails}")
        else:
            ok += 1
    print(f"\n[smoke] 通过 {ok}/{len(nns)}，失败 {len(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())