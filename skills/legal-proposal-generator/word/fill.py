#!/usr/bin/env python3
"""fill.py — legal-proposal-word OOXML 模板填充工具（python-docx）

把 legal-proposal-OOXML-template.docx 中的 {{TOKEN}} 占位符替换为实际内容，
照片位（*_IMG / *_PHOTO）用 --photo 嵌入真实图片。

用法：
  python3 fill.py 模板.docx -o 输出.docx --set LAW_FIRM=XX律师事务所 CLIENT=某公司 ...
  python3 fill.py 模板.docx -o 输出.docx --json tokens.json --photo TEAM1_PHOTO=a.jpg
  python3 fill.py 模板.docx --list          # 仅列出模板中的占位符

说明：
  - 文本替换在段落级完成；若占位符被 Word 拆成多个 run，会先合并该段 run
    （仅影响占位符所在段落的 run 级格式，模板中占位符均独占段落/run，无实际影响）。
  - 照片宽度按占位符前缀自动设定：TEAM→3.0cm，CASE→5.0cm，FIRM→8.0cm。
  - {{PROPOSAL_TITLE}} 同时出现在封面与正文题名块及页眉，替换一次全局生效。
"""
import argparse
import json
import re
import sys

try:
    from docx import Document
    from docx.shared import Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
except ImportError:
    print("缺少依赖 python-docx。请运行：python3 -m pip install python-docx", file=sys.stderr)
    raise SystemExit(2)

TOKEN_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
PHOTO_WIDTH_CM = {"TEAM": 3.0, "CASE": 5.0, "FIRM": 8.0}


def iter_paragraphs(parent):
    """递归产出 parent（Document/Header/Footer/_Cell）下的全部段落，含嵌套表格内段落。"""
    for p in parent.paragraphs:
        yield p
    for t in parent.tables:
        for row in t.rows:
            for cell in row.cells:
                yield from iter_paragraphs(cell)


def replace_in_paragraph(p, token, value):
    if token not in p.text:
        return False
    new_text = p.text.replace(token, value)
    runs = list(p.runs)
    if not runs:
        p.add_run(new_text)
        return True
    for r in runs[1:]:
        r._element.getparent().remove(r._element)
    runs[0].text = new_text
    return True


def fill_photo(p, img_path, width_cm):
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(img_path, width=Cm(width_cm))


def photo_width_cm(token):
    prefix = token.split("_")[0]  # TEAM1_PHOTO → TEAM
    return PHOTO_WIDTH_CM.get(prefix, 4.0)


def collect_documents(doc):
    """返回需扫描的容器列表：正文 + 各节「已存在」的页眉页脚。

    ⚠️ 必须先用 is_linked_to_previous 过滤：python-docx 对不存在页眉/页脚的
    paragraphs/tables 访问会凭空创建空部件并写入 sectPr，空页眉会占据页眉距离
    空间，导致零边距封面（全出血设计）正文区被压矮、固定高度表格溢出分页。
    """
    containers = [doc]
    for sec in doc.sections:
        for hf in (sec.header, sec.footer, sec.first_page_header, sec.first_page_footer,
                   sec.even_page_header, sec.even_page_footer):
            try:
                if not hf.is_linked_to_previous:
                    containers.append(hf)
            except Exception:
                pass
    return containers


def list_tokens(doc):
    found = set()
    for container in collect_documents(doc):
        for p in iter_paragraphs(container):
            found.update(TOKEN_RE.findall(p.text))
    return sorted(found)


def fill_text(doc, tokens):
    replaced = 0
    for container in collect_documents(doc):
        for p in iter_paragraphs(container):
            for key, value in tokens.items():
                token = "{{%s}}" % key.strip("{}")  # 裸键名 → {{KEY}}；容忍调用方已带花括号
                if replace_in_paragraph(p, token, str(value)):
                    replaced += 1
    return replaced


def fill_photos(doc, photos):
    done = []
    for container in collect_documents(doc):
        for p in iter_paragraphs(container):
            m = TOKEN_RE.search(p.text or "")
            if not m:
                continue
            token = m.group(0)[2:-2]  # 去掉 {{ }}
            if token in photos:
                fill_photo(p, photos[token], photo_width_cm(token))
                done.append(token)
    return done


def main():
    ap = argparse.ArgumentParser(description="legal-proposal-word 模板填充工具")
    ap.add_argument("template", help="模板 docx 路径")
    ap.add_argument("-o", "--output", help="输出 docx 路径（缺省为 <模板名>_filled.docx）")
    ap.add_argument("--set", dest="pairs", nargs="*", default=[], help="文本占位符赋值，形如 KEY=值")
    ap.add_argument("--json", dest="jsonfile", help="从 JSON 文件读取文本占位符")
    ap.add_argument("--photo", dest="photos", nargs="*", default=[], help="照片占位符，形如 KEY=图片路径")
    ap.add_argument("--list", action="store_true", help="仅列出模板中的占位符后退出")
    args = ap.parse_args()

    doc = Document(args.template)

    if args.list:
        for t in list_tokens(doc):
            print(t)
        return 0

    tokens = {}
    if args.jsonfile:
        with open(args.jsonfile, encoding="utf-8") as f:
            tokens.update(json.load(f))
    for pair in args.pairs:
        k, _, v = pair.partition("=")
        if not k or not _:
            sys.exit(f"无效的 --set 参数（应为 KEY=值）：{pair}")
        tokens[k.strip()] = v

    photos = {}
    for pair in args.photos:
        k, _, v = pair.partition("=")
        if not k or not _:
            sys.exit(f"无效的 --photo 参数（应为 KEY=图片路径）：{pair}")
        photos[k.strip()] = v

    n_text = fill_text(doc, tokens)
    done_photos = fill_photos(doc, photos)

    out = args.output or args.template.rsplit(".", 1)[0] + "_filled.docx"
    doc.save(out)

    missing = [t for t in list_tokens(doc)]
    print(f"文本替换 {n_text} 处；照片填充 {len(done_photos)} 个：{', '.join(done_photos) or '无'}")
    print(f"输出 -> {out}")
    if missing:
        print(f"⚠️ 仍有未填充占位符 {len(missing)} 个：{', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
