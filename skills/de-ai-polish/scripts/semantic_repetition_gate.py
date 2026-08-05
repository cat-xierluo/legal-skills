#!/usr/bin/env python3
"""召回反复出现的“工具能力—限制—人的判断/责任”语义骨架。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CONSTRAINT_ID = "NO-REPEATED-CAPABILITY-BOUNDARY-SKELETON"
SUBJECT = re.compile(r"(?:AI|人工智能|大模型|模型|工具|系统|框架)", re.IGNORECASE)
CAPABILITY = re.compile(
    r"(?:能(?:够)?|可以|会|擅长|善于|生成|起草|整理|复述|检索|模仿|提供|"
    r"识别|归纳|完成|调用|协助|参与|使用|用对|降低|压低|形成|写出)"
)
LIMITATION = re.compile(
    r"(?:但(?:是)?|不过|却|仍(?:然)?|只是|并不|不能|无法|不等于|离不开|"
    r"取决于|还需要|还要|仍需|需要|未必|没有|缺少|只能|只完成|不会|"
    r"尚待|不具备|无对应关系|不意味着|并未|必须|难点在于|另一项工作|欠缺|尚有距离|"
    r"只(?:能|对应|覆盖|提供|停留于)|两件不同的事|两回事)"
)
JUDGMENT = re.compile(
    r"(?:人|律师|法务|使用者|专业人士|审查|复核|判断|经验|责任|承担|取舍|"
    r"决策|材料|事实|交易|语境|条件|实践|后果|风险|位阶|例外|关系|程序|"
    r"地区|谈判|训练|反馈|体系|核验|检验|适用|名称|匹配|价值|专业|依据|"
    r"输入|形成过程|权利义务|答案|规则|影响)"
)
IMPLICIT_SURFACE = re.compile(
    r"(?:生成|复述|匹配|模仿|初稿|文本|词面|形式|外观|名称|规则|模式相似|"
    r"起草门槛|起草成本|完整合同|完整协议|条款写得完整|措辞|填入|填满|排列|"
    r"自洽|成文依据|专业外观|格式规范|写完|直接得到(?:一份)?(?:协议|文本))"
)
IMAGE_LINE = re.compile(r"^\s*!\[[^\]]*\]\(.+\)\s*$")
FUNCTIONAL_NAVIGATION_LABEL = re.compile(
    r"^(?:>\s*)?(?:\*\*)?(?:第[一二三四五六七八九十百]+(?:层|种|类|步|项)|"
    r"[一二三四五六七八九十]+[、.])"
)


def markdown_paragraphs(text: str) -> list[tuple[int, str, str]]:
    paragraphs: list[tuple[int, str, str]] = []
    buffer: list[str] = []
    start_line = 0
    heading = "<document>"
    in_fence = False
    in_frontmatter = text.startswith("---\n")

    def flush() -> None:
        nonlocal buffer, start_line
        if buffer:
            paragraph = " ".join(item.strip() for item in buffer).strip()
            if paragraph:
                paragraphs.append((start_line, heading, paragraph))
        buffer = []
        start_line = 0

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if line_number == 1 and stripped == "---":
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith("#"):
            flush()
            heading = stripped
            continue
        if not stripped or IMAGE_LINE.match(line):
            flush()
            continue
        if not buffer:
            start_line = line_number
        buffer.append(line)
    flush()
    return paragraphs


def is_capability_boundary(paragraph: str) -> bool:
    for subject in SUBJECT.finditer(paragraph):
        window = paragraph[subject.start() : subject.start() + 320]
        capability = CAPABILITY.search(window)
        if capability is None:
            continue
        limitation = LIMITATION.search(window, capability.end())
        if limitation is None:
            continue
        if JUDGMENT.search(window, limitation.end()) is not None:
            return True
    surface = IMPLICIT_SURFACE.search(paragraph)
    if surface is not None:
        window = paragraph[surface.start() : surface.start() + 320]
        limitation = LIMITATION.search(window, surface.end() - surface.start())
        if limitation is not None:
            before = window[: limitation.start()]
            after = window[limitation.end() :]
            if JUDGMENT.search(before) is not None or JUDGMENT.search(after) is not None:
                return True
    if re.search(r"(?:AI|模型).{0,100}没有.{0,80}(?:训练|反馈|经验).{0,160}(?:生成|文本|判断)", paragraph):
        return True
    if re.search(
        r"(?:初稿|文本|外观|生成速度).{0,120}(?:不能据此|不能|不等于|没有|尚待|无对应关系)"
        r".{0,100}(?:判断|核对|责任|事实|规则|答案)",
        paragraph,
    ):
        return True
    if re.search(
        r"(?:入口|门槛|工具).{0,120}(?:判断|责任|专业训练).{0,80}"
        r"(?:没有|不会|并未|不等于|消失|转移|仍)",
        paragraph,
    ):
        return True
    return False


def check(
    path: Path,
    max_count: int,
    max_per_section: int,
    max_final_section: int,
    max_adjacent: int,
) -> tuple[bool, dict[str, object]]:
    paragraphs = markdown_paragraphs(path.read_text(encoding="utf-8"))
    findings = []
    counted_findings = []
    functional_navigation_findings = []
    section_counts: dict[str, int] = {}
    raw_section_counts: dict[str, int] = {}
    counted_indices: list[tuple[int, str]] = []
    for index, (line_number, heading, paragraph) in enumerate(paragraphs):
        if is_capability_boundary(paragraph):
            raw_section_counts[heading] = raw_section_counts.get(heading, 0) + 1
            follows_navigation = (
                index > 0
                and paragraphs[index - 1][1] == heading
                and FUNCTIONAL_NAVIGATION_LABEL.match(paragraphs[index - 1][2]) is not None
            )
            finding = {
                "line": line_number,
                "section": heading,
                "preview": paragraph[:72],
                "hard_counted": not follows_navigation,
                "context": (
                    "functional_navigation_item" if follows_navigation else "ordinary_body"
                ),
            }
            findings.append(finding)
            if follows_navigation:
                functional_navigation_findings.append(finding)
            else:
                counted_findings.append(finding)
                counted_indices.append((index, heading))
                section_counts[heading] = section_counts.get(heading, 0) + 1

    adjacent_runs: list[dict[str, object]] = []
    run: list[tuple[int, str]] = []
    for item in counted_indices:
        if run and item[1] == run[-1][1] and item[0] == run[-1][0] + 1:
            run.append(item)
        else:
            if len(run) > max_adjacent:
                adjacent_runs.append(
                    {
                        "section": run[0][1],
                        "count": len(run),
                        "paragraph_indices": [entry[0] for entry in run],
                    }
                )
            run = [item]
    if len(run) > max_adjacent:
        adjacent_runs.append(
            {
                "section": run[0][1],
                "count": len(run),
                "paragraph_indices": [entry[0] for entry in run],
            }
        )

    headings = list(dict.fromkeys(heading for _, heading, _ in paragraphs))
    final_heading = headings[-1] if len(headings) >= 2 else None
    final_section_count = section_counts.get(final_heading, 0) if final_heading else 0

    failure_reasons = []
    if len(counted_findings) > max_count:
        failure_reasons.append("total_count")
    if any(count > max_per_section for count in section_counts.values()):
        failure_reasons.append("section_concentration")
    if final_heading and final_section_count > max_final_section:
        failure_reasons.append("final_section_repetition")
    if adjacent_runs:
        failure_reasons.append("adjacent_repetition")

    common = {
        "constraint_id": CONSTRAINT_ID,
        "candidate_count": len(findings),
        "counted_candidate_count": len(counted_findings),
        "functional_navigation_candidate_count": len(functional_navigation_findings),
        "max_count": max_count,
        "max_per_section": max_per_section,
        "max_final_section": max_final_section,
        "max_adjacent": max_adjacent,
        "section_counts": section_counts,
        "raw_section_counts": raw_section_counts,
        "final_section": final_heading,
        "final_section_count": final_section_count,
        "adjacent_runs": adjacent_runs,
        "failure_reasons": failure_reasons,
        "findings": findings,
        "boundary": (
            "原始候选全部保留用于人工复扫；紧跟‘第 N 层／种／步’导航标签的说明项"
            "作为功能性分类单独报告，不进入硬删除配额。硬门禁检查普通正文总量、"
            "单节集中、相邻复唱和末节重复；未命中不证明不存在语义重复"
        ),
    }
    if failure_reasons:
        return False, {"failed_constraint_ids": [CONSTRAINT_ID], **common}
    return True, {"passed_constraint_ids": [CONSTRAINT_ID], **common}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--max-count", type=int, required=True)
    parser.add_argument("--max-per-section", type=int, required=True)
    parser.add_argument("--max-final-section", type=int, default=1)
    parser.add_argument("--max-adjacent", type=int, default=1)
    args = parser.parse_args()
    if not args.file.is_file():
        parser.error(f"文件不存在: {args.file}")
    if args.max_count < 0:
        parser.error("--max-count 不能小于 0")
    if args.max_per_section < 0:
        parser.error("--max-per-section 不能小于 0")
    if args.max_final_section < 0:
        parser.error("--max-final-section 不能小于 0")
    if args.max_adjacent < 0:
        parser.error("--max-adjacent 不能小于 0")
    passed, result = check(
        args.file,
        args.max_count,
        args.max_per_section,
        args.max_final_section,
        args.max_adjacent,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
