#!/usr/bin/env python3
"""答辩状全量冒烟：45 棵非主文书树逐个用通用样本渲染，验证当事人块可用。"""
import json, shutil, sys, tempfile, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from lxml import etree

from fill_template import (Wt, Wp, resolve_case, apply_rules,
                           load_text_parts, save_text_parts, DocParts)
from generic_rules import all_secondary_trees, _find_party_anchor, _paras
from pack_docx import pack_tree

SKILL_DIR = Path(__file__).resolve().parent.parent
W = Wt; P = Wp


def render_tree(tree_name: str, elements: dict, out: Path) -> list[str]:
    tree_src = SKILL_DIR / "templates" / tree_name
    probe_text_parts = load_text_parts(tree_src)
    probe = " ".join("".join(t.text or "" for t in p.iter(Wt))
                     for tree in probe_text_parts.values() for p in tree.iter(Wp))
    probe_paras = _paras(DocParts(load_text_parts(tree_src)))
    has_natural = len(_find_party_anchor(probe_paras)) >= 1
    has_sex = "性别：男" in probe

    tmp = Path(tempfile.mkdtemp(prefix="ans-smoke-"))
    tw = tmp / "tree"
    shutil.copytree(tree_src, tw)
    parts = load_text_parts(tw)
    from generic_rules import build_generic_rules
    rules = build_generic_rules(tree_src, elements)
    apply_rules(DocParts(parts), rules, elements)
    save_text_parts(tw, parts)
    out.parent.mkdir(parents=True, exist_ok=True)
    pack_tree(tw, out)
    shutil.rmtree(tmp, ignore_errors=True)

    with zipfile.ZipFile(out) as z:
        xml = etree.fromstring(z.read("word/document.xml"))
    full = " ".join("".join(t.text or "" for t in p.iter(Wt)).strip() for p in xml.iter(Wp))

    fails = []
    if has_natural and "姓名：王五" not in full:
        fails.append("姓名缺失")
    if has_sex and "性别：男☑" not in full:
        fails.append("性别勾选缺失")
    if "日日" in full:
        fails.append("双日哨兵")
    return fails


def main() -> int:
    elements = json.loads((SKILL_DIR / "tests/fixtures/generic-smoke.json").read_text(encoding="utf-8"))["elements"]
    trees = all_secondary_trees(SKILL_DIR / "templates")
    out_dir = SKILL_DIR / "tests/output/smoke-answer"
    ok, failures = 0, []
    for tree in trees:
        try:
            fails = render_tree(tree, elements, out_dir / f"{tree}.docx")
        except Exception as e:
            fails = [f"异常: {type(e).__name__}: {e}"]
        if fails:
            failures.append((tree, fails))
            print(f"  ✗ {tree[:30]}: {fails}")
        else:
            ok += 1
    print(f"\n[answer-smoke] 通过 {ok}/{len(trees)}，失败 {len(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())