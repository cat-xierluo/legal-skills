#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""book-gate markdown 阶段验证器。

检查 manuscript markdown 源：mermaid 残留 / 非 SVG 图表 DSL / 中文撇号笔误。
每个检查函数签名 (scope_path, req_id) -> List[Finding]（空 = PASS）。
book-gate.py 按 requirements.yaml 的 verifier 字段调度。
"""
import re
import os
import glob

# ```mermaid 围栏块
_MERMAID_RE = re.compile(r'^```mermaid\b', re.MULTILINE)
# 其它图表 DSL（与 writing-reviewer 22-non-svg-diagram-gate 对齐）
_OTHER_DSL_RE = re.compile(
    r'^```(?:plantuml|dot|graphviz|flowchart|sequenceDiagram|classDiagram|erDiagram|stateDiagram|gantt|pie|gitGraph|journey)\b',
    re.MULTILINE,
)
# 中文-ASCII撇号-中文（源稿笔误，应用中文单引号 ‘’）
_CN_APOS_CN_RE = re.compile(r'([一-鿿])\'([一-鿿])')


class Finding:
    def __init__(self, req_id, file, line, severity, message, suggestion=''):
        self.req_id = req_id
        self.file = file
        self.line = line
        self.severity = severity  # 'hard' / 'soft'
        self.message = message
        self.suggestion = suggestion

    def to_dict(self):
        return {'req_id': self.req_id, 'file': self.file, 'line': self.line,
                'severity': self.severity, 'message': self.message,
                'suggestion': self.suggestion}

    def __repr__(self):
        return f"[{self.severity}] {self.req_id} {self.file}:{self.line} {self.message}"


def _iter_manuscript(scope_path):
    """scope_path 是 manuscript 根；递归 glob ch*.md（兼容 chNN-篇/ch*.md 与 ch*.md）。"""
    patterns = [
        os.path.join(scope_path, 'ch*.md'),
        os.path.join(scope_path, '*', 'ch*.md'),
        os.path.join(scope_path, '**', 'ch*.md'),
    ]
    seen = set()
    for pat in patterns:
        for f in glob.glob(pat, recursive=True):
            if f not in seen:
                seen.add(f)
                yield f


def no_mermaid(scope_path, req_id='MD-001'):
    """MD-001：禁 mermaid 代码块（转 Word 降级文本）。hard。"""
    findings = []
    for f in _iter_manuscript(scope_path):
        with open(f, encoding='utf-8') as fh:
            for i, line in enumerate(fh, 1):
                if _MERMAID_RE.match(line):
                    findings.append(Finding(
                        req_id, f, i, 'hard',
                        '含 ```mermaid 代码块（转 Word 降级为文本，丢失视觉）',
                        '用 svg-book-illustrator 重画为 SVG（方案 A 灰阶+蓝色焦点）替换'))
    return findings


def no_other_diagram_dsl(scope_path, req_id='MD-002'):
    """MD-002：禁 plantuml/dot/graphviz 等非 SVG 图表 DSL。hard。"""
    findings = []
    for f in _iter_manuscript(scope_path):
        with open(f, encoding='utf-8') as fh:
            for i, line in enumerate(fh, 1):
                if _OTHER_DSL_RE.match(line):
                    findings.append(Finding(
                        req_id, f, i, 'hard',
                        f'含非 SVG 图表 DSL: {line.strip()[:50]}',
                        '转 SVG（本书结构图/流程图一律 SVG）'))
    return findings


def chinese_quote_correct(scope_path, req_id='MD-004'):
    """MD-004：中文夹 ASCII 撇号应改中文单引号（md2word isalpha 回归·源稿笔误）。soft。

    注：md2word v1.1.5+ 的 convert_quotes_to_chinese 已能正确把 ASCII 撇号按
    ASCII 边界转中文单引号（isascii 限定）；本规则查**源稿**是否有「中文'中文」
    笔误（源稿应直接用中文单引号 ‘’，不依赖 md2word 转换）。
    """
    findings = []
    for f in _iter_manuscript(scope_path):
        with open(f, encoding='utf-8') as fh:
            for i, line in enumerate(fh, 1):
                for m in _CN_APOS_CN_RE.finditer(line):
                    findings.append(Finding(
                        req_id, f, i, 'soft',
                        f"中文夹 ASCII 撇号「{m.group(1)}'{m.group(2)}」（源稿建议直接用中文单引号 ‘’）",
                        '改用中文单引号 ‘’（或确认该撇号属英文所有格上下文）'))
    return findings
