#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚注/尾注处理模块（md2word）

支持两种模式（CLI --notes=footnote|endnote，默认 footnote）：
- footnote：Word 原生页面脚注（正文 footnoteReference + 注入 word/footnotes.xml）
- endnote：文档末“注释”小节 + 正文上标编号（伪 endnote）
  （Word 原生 endnote 只能放文档末、不能“每章末”，故每章尾注用上标编号 + 末尾列表实现）

markdown 语法：
- 引用：[^id]（行内，可多次引用同一 id）
- 定义：[^id]: 脚注文本（单独行，预处理时提取并从正文移除）
"""

import re
import shutil
import zipfile

from docx.oxml.ns import qn
from docx.oxml.shared import OxmlElement
from docx.shared import Pt

FOOTNOTES_CT = 'application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml'
FOOTNOTES_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes'

NOTE_DEF_RE = re.compile(r'^\[\^([^\]]+)\]:\s*(.*)$')   # [^id]: text
NOTE_REF_RE = re.compile(r'\[\^([^\]]+)\]')              # [^id] 引用


def extract_footnote_defs(lines):
    """从 md 行列表提取脚注定义。返回 (defs_dict, cleaned_lines)。

    defs_dict: {id: text}；cleaned_lines: 移除定义行后的行列表（其他行原样保留）。
    """
    defs = {}
    cleaned = []
    for line in lines:
        m = NOTE_DEF_RE.match(line.strip())
        if m:
            defs[m.group(1)] = m.group(2).strip()
        else:
            cleaned.append(line)
    return defs, cleaned


class FootnoteManager:
    """管理一次转换的脚注/尾注状态。"""

    def __init__(self, mode='footnote'):
        assert mode in ('footnote', 'endnote')
        self.mode = mode
        self.defs = {}        # {id: text}
        self.refs = []        # [(seq, text), ...] 按出现顺序
        self._seq = 0         # 编号 / footnote w:id 计数（从 1 起）

    def set_defs(self, defs):
        self.defs = defs

    def add_reference(self, paragraph, note_id):
        """在段落插入脚注引用。footnote→footnoteReference；endnote→上标编号。"""
        text = self.defs.get(note_id, '')
        if not text:
            return  # 无定义的悬空引用跳过
        self._seq += 1
        seq = self._seq
        self.refs.append((seq, text))
        if self.mode == 'footnote':
            # 正文 run：footnoteReference（w:id 与 footnotes.xml 中 w:footnote 对应）
            run = OxmlElement('w:r')
            rPr = OxmlElement('w:rPr')
            vert = OxmlElement('w:vertAlign')
            vert.set(qn('w:val'), 'superscript')
            rPr.append(vert)
            sz = OxmlElement('w:sz')
            sz.set(qn('w:val'), '18')
            rPr.append(sz)
            run.append(rPr)
            fn_ref = OxmlElement('w:footnoteReference')
            fn_ref.set(qn('w:id'), str(seq))
            run.append(fn_ref)
            paragraph._p.append(run)
        else:  # endnote：上标编号
            r = paragraph.add_run(str(seq))
            r.font.superscript = True
            r.font.size = Pt(9)

    def append_endnotes_section(self, doc):
        """endnote 模式：文档末追加“注释”小节 + 编号列表。footnote 模式无操作。"""
        if self.mode != 'endnote' or not self.refs:
            return
        doc.add_paragraph()  # 空行分隔
        title = doc.add_paragraph()
        tr = title.add_run('注释')
        tr.bold = True
        tr.font.size = Pt(12)
        for seq, text in self.refs:
            p = doc.add_paragraph()
            idx = p.add_run('[%d] ' % seq)
            idx.font.size = Pt(9)
            idx.bold = True
            body = p.add_run(text)
            body.font.size = Pt(9)

    def finalize_footnotes_part(self, output_path):
        """footnote 模式：doc.save 后 post-process，注入 footnotes.xml + rels + Content_Types。"""
        if self.mode != 'footnote' or not self.refs:
            return
        _inject_footnotes_into_docx(output_path, self.refs)


def _xml_escape(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _inject_footnotes_into_docx(docx_path, refs):
    """post-process：把脚注 part 注入已保存的 docx（纯 zip 操作，不依赖 python-docx part API）。

    refs: [(seq, text), ...]，seq 即 footnote w:id。
    footnotes.xml 采用自包含内联格式（vertAlign/sz 内联），不依赖 styles.xml 的
    FootnoteText / FootnoteReference 样式定义，Word 可直接正确渲染。
    """
    tmp_path = docx_path + '.fn_tmp'
    with zipfile.ZipFile(docx_path, 'r') as zin:
        names = zin.namelist()
        data = {n: zin.read(n) for n in names}

    ct = data.get('[Content_Types].xml', b'').decode('utf-8')
    rels_name = 'word/_rels/document.xml.rels'
    rels = data.get(rels_name, b'').decode('utf-8') if rels_name in data else None

    # 1) 构建 footnotes.xml
    fn_items = [
        '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>',
        '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>',
    ]
    for seq, text in refs:
        fn_items.append(
            '<w:footnote w:id="%d"><w:p>'
            '<w:r><w:rPr><w:vertAlign w:val="superscript"/><w:sz w:val="18"/></w:rPr><w:footnoteRef/></w:r>'
            '<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:t xml:space="preserve"> %s</w:t></w:r>'
            '</w:p></w:footnote>' % (seq, _xml_escape(text))
        )
    footnotes_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        + ''.join(fn_items) + '</w:footnotes>'
    )

    # 2) [Content_Types].xml 加 override（若缺）
    if 'footnotes' not in ct:
        override = '<Override PartName="/word/footnotes.xml" ContentType="%s"/>' % FOOTNOTES_CT
        ct = ct.replace('</Types>', override + '</Types>')

    # 3) document.xml.rels 加关系（若缺）
    max_id = 0
    if rels:
        for m in re.finditer(r'Id="rId(\d+)"', rels):
            max_id = max(max_id, int(m.group(1)))
    if rels is None:
        rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId%d" Type="%s" Target="footnotes.xml"/></Relationships>'
                % (max_id + 1, FOOTNOTES_REL))
    elif FOOTNOTES_REL not in rels:
        rel_entry = '<Relationship Id="rId%d" Type="%s" Target="footnotes.xml"/>' % (max_id + 1, FOOTNOTES_REL)
        rels = rels.replace('</Relationships>', rel_entry + '</Relationships>')

    data['[Content_Types].xml'] = ct.encode('utf-8')
    data[rels_name] = rels.encode('utf-8')
    data['word/footnotes.xml'] = footnotes_xml.encode('utf-8')

    # 4) 重写 docx（保持原条目顺序，追加 footnotes.xml）
    with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for n in data:
            zout.writestr(n, data[n])
    shutil.move(tmp_path, docx_path)
    print('✅ 已注入 %d 个页面脚注（footnotes.xml）' % len(refs))
