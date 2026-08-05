#!/usr/bin/env python3
"""拦截 de-ai-polish 已知的假排名、编辑过程泄漏与框架启动语。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ENUMERATION_CONSTRAINT_ID = "NO-DISGUISED-ENUMERATION"
PROCESS_LEAKAGE_CONSTRAINT_ID = "NO-EDITORIAL-PROCESS-LEAKAGE"
FRAMEWORK_STARTER_CONSTRAINT_ID = "NO-FRAMEWORK-STARTER"
APHORISM_EVASION_CONSTRAINT_ID = "NO-COMPRESSED-APHORISM-EVASION"
ENTRY_METAPHOR_CONSTRAINT_ID = "NO-ABSTRACT-ENTRY-METAPHOR"
SPATIAL_METAPHOR_CONSTRAINT_ID = "NO-REPEATED-SPATIAL-ACCESS-METAPHOR"
STARTER_PATTERNS = (
    re.compile(r"^.{0,20}最典型(?:。|，|是)"),
    re.compile(r"^.{0,20}最容易.{0,18}(?:一条|一项|一种|一处|地方|问题)"),
    re.compile(r"^.{0,20}也容易(?:出事|出问题|忽略|略过|漏掉)"),
    re.compile(r"^类似的还有"),
)
IMAGE_LINE = re.compile(r"^\s*!\[[^\]]*\]\(.+\)\s*$")
PROCESS_LEAKAGE_PATTERNS = (
    re.compile(r"(?:按(?:照)?源稿|源稿(?:中|里|的)?.{0,18}(?:导航|标题|结构|顺序|分类|材料|相连|保留))"),
    re.compile(r"(?:导航|标题|结构|顺序|分类).{0,12}(?:仍|继续)(?:予以|得到)?保留"),
    re.compile(r"没有足够材料.{0,16}(?:相连|建立关系|支持)"),
    re.compile(r"不是.{0,24}(?:照单执行|逐项执行).{0,12}(?:检查任务|清单)"),
    re.compile(r"(?:关系证据卡|AUTHOR_MATERIAL_NEEDED|STRUCTURE_REVIEW|NOT_VERIFIED|候选外|交付正文)"),
    re.compile(r"(?:换词重复|同功能段落|连续同构|能力边界候选|门禁阈值)"),
)
FRAMEWORK_STARTER_PATTERNS = (
    re.compile(r"^先承认(?:一个)?前提[：:，,]?"),
)
APHORISM_EVASION_PATTERNS = (
    re.compile(r"(?:工具|模型).{0,18}(?:走到边界|退场).{0,18}(?:留下|剩下).{0,18}(?:判断|责任)"),
    re.compile(r"(?:AI|工具).{0,30}的是.{0,30}不是.{0,30}。.{0,24}(?:判断|责任).{0,12}。$"),
    re.compile(r"AI最(?:危险|可怕|重要|有用).{0,16}时候"),
)
ENTRY_METAPHOR_PATTERNS = (
    re.compile(r"(?:入口顺滑|低摩擦入口|更低的入口|较低的入口|入口变得更低)"),
)
SPATIAL_METAPHOR_PATTERN = re.compile(
    r"(?:入口|门槛|进入(?:专业|领域|任务|法律|内部)|回到(?:法律)?内部|内部判断|送进|穿透|穿过去|工具退场)"
)


def markdown_sections(text: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    heading = "<document>"
    paragraphs: list[str] = []
    buffer: list[str] = []

    def flush_paragraph() -> None:
        if buffer:
            paragraph = " ".join(item.strip() for item in buffer).strip()
            if paragraph:
                paragraphs.append(paragraph)
            buffer.clear()

    def flush_section() -> None:
        flush_paragraph()
        if paragraphs:
            sections.append((heading, list(paragraphs)))
            paragraphs.clear()

    for line in text.splitlines():
        if line.startswith("## "):
            flush_section()
            heading = line[3:].strip()
        elif not line.strip():
            flush_paragraph()
        elif IMAGE_LINE.match(line):
            flush_paragraph()
        else:
            buffer.append(line)
    flush_section()
    return sections


def first_sentence(paragraph: str) -> str:
    return re.split(r"(?<=[。！？])", paragraph, maxsplit=1)[0].strip()


def check(path: Path) -> tuple[bool, dict[str, object]]:
    enumeration_findings: list[dict[str, object]] = []
    process_findings: list[dict[str, object]] = []
    framework_findings: list[dict[str, object]] = []
    aphorism_findings: list[dict[str, object]] = []
    entry_metaphor_findings: list[dict[str, object]] = []
    spatial_metaphor_findings: list[dict[str, object]] = []
    for heading, paragraphs in markdown_sections(path.read_text(encoding="utf-8")):
        matches: list[dict[str, object]] = []
        for index, paragraph in enumerate(paragraphs, start=1):
            sentence = first_sentence(paragraph)
            if any(pattern.search(sentence) for pattern in STARTER_PATTERNS):
                matches.append({"paragraph": index, "starter": sentence})
            if any(pattern.search(paragraph) for pattern in PROCESS_LEAKAGE_PATTERNS):
                process_findings.append(
                    {
                        "section": heading,
                        "paragraph": index,
                        "preview": paragraph[:96],
                        "reason": "面向编辑或评测者的过程说明泄漏进了读者正文",
                    }
                )
            if any(pattern.search(sentence) for pattern in FRAMEWORK_STARTER_PATTERNS):
                framework_findings.append(
                    {
                        "section": heading,
                        "paragraph": index,
                        "preview": sentence[:96],
                        "reason": "用通用框架提示启动段落，没有直接进入内容",
                    }
                )
            if any(pattern.search(paragraph) for pattern in APHORISM_EVASION_PATTERNS):
                aphorism_findings.append(
                    {
                        "section": heading,
                        "paragraph": index,
                        "preview": paragraph[:96],
                        "reason": "把已反复出现的能力边界压成短金句或口号，未解决语义重复",
                    }
                )
            if any(pattern.search(paragraph) for pattern in ENTRY_METAPHOR_PATTERNS):
                entry_metaphor_findings.append(
                    {
                        "section": heading,
                        "paragraph": index,
                        "preview": paragraph[:96],
                        "reason": "把具体的启动成本或操作变化改写成抽象入口隐喻",
                    }
                )
            if SPATIAL_METAPHOR_PATTERN.search(paragraph):
                spatial_metaphor_findings.append(
                    {
                        "section": heading,
                        "paragraph": index,
                        "preview": paragraph[:96],
                        "reason": "入口／门槛／内部空间隐喻跨段重复，开始替代具体动作和条件",
                    }
                )
        if len(matches) >= 3:
            enumeration_findings.append(
                {
                    "section": heading,
                    "matched_paragraphs": matches,
                    "reason": "三个以上同功能段首用假排名或口语标签伪装列举",
                }
            )
    failed_constraint_ids: list[str] = []
    findings: list[dict[str, object]] = []
    if enumeration_findings:
        failed_constraint_ids.append(ENUMERATION_CONSTRAINT_ID)
        findings.extend(enumeration_findings)
    if process_findings:
        failed_constraint_ids.append(PROCESS_LEAKAGE_CONSTRAINT_ID)
        findings.extend(process_findings)
    if framework_findings:
        failed_constraint_ids.append(FRAMEWORK_STARTER_CONSTRAINT_ID)
        findings.extend(framework_findings)
    if aphorism_findings:
        failed_constraint_ids.append(APHORISM_EVASION_CONSTRAINT_ID)
        findings.extend(aphorism_findings)
    if entry_metaphor_findings:
        failed_constraint_ids.append(ENTRY_METAPHOR_CONSTRAINT_ID)
        findings.extend(entry_metaphor_findings)
    if len(spatial_metaphor_findings) >= 3:
        failed_constraint_ids.append(SPATIAL_METAPHOR_CONSTRAINT_ID)
        findings.extend(spatial_metaphor_findings)
    if failed_constraint_ids:
        return False, {
            "failed_constraint_ids": failed_constraint_ids,
            "finding_count": len(findings),
            "findings": findings,
            "boundary": "已知回归启发式，不替代 Agent 通读",
        }
    return True, {
        "passed_constraint_ids": [
            ENUMERATION_CONSTRAINT_ID,
            PROCESS_LEAKAGE_CONSTRAINT_ID,
            FRAMEWORK_STARTER_CONSTRAINT_ID,
            APHORISM_EVASION_CONSTRAINT_ID,
            ENTRY_METAPHOR_CONSTRAINT_ID,
            SPATIAL_METAPHOR_CONSTRAINT_ID,
        ],
        "finding_count": 0,
        "boundary": "只证明未命中已知假排名、过程泄漏、框架启动语、压缩金句逃逸和重复空间隐喻，不证明全文无 AI 腔",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    if not args.file.is_file():
        parser.error(f"文件不存在: {args.file}")
    passed, result = check(args.file)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
