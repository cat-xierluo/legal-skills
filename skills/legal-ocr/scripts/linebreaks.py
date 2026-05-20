from __future__ import annotations

import re

from basic_postprocess import PostprocessResult


STRUCTURAL_RE = re.compile(
    r"^\s*("
    r"#{1,6}\s+|"
    r"[-*+]\s+|"
    r"\d+[.)、．]\s*|"
    r"[一二三四五六七八九十]+[、.．]\s*|"
    r"[（(][一二三四五六七八九十\d]+[）)]\s*|"
    r"第[一二三四五六七八九十百千万\d]+[章节条]\s*"
    r")"
)

LEGAL_LABEL_RE = re.compile(
    r"^\s*("
    r"原告|被告|第三人|上诉人|被上诉人|申请人|被申请人|"
    r"再审申请人|申请执行人|被执行人|法定代表人|"
    r"委托诉讼代理人|委托代理人|案号|审理法院|裁判日期|"
    r"审判长|审判员|人民陪审员|书记员"
    r")\s*[;；:：]"
)

COURT_HEADING_RE = re.compile(
    r"^(原告诉称|被告辩称|第三人述称|上诉人上诉称|被上诉人辩称|"
    r"申请人称|被申请人辩称|诉讼请求|事实和理由|审理经过|"
    r"本院查明|经审理查明|本院认为|裁判结果|判决如下|裁定如下|"
    r"审理查明|法院认为)[:：]?$"
)

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
CONTINUATION_START_RE = re.compile(r"^[，。；：、,.!?！？）】》”’]")
STRONG_END_RE = re.compile(r"[。！？!?）】》”’]$")
WEAK_END_RE = re.compile(r"[，、；;：:]$")


def _cjk_count(text: str) -> int:
    return len(CJK_RE.findall(text))


def _is_table_line(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _is_markdown_boundary(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.startswith(("```", "~~~", ">", "![", "<")):
        return True
    if stripped in {"---", "***", "___"}:
        return True
    if _is_table_line(stripped):
        return True
    return False


def _is_structural_line(text: str) -> bool:
    stripped = text.strip()
    if _is_markdown_boundary(stripped):
        return True
    if COURT_HEADING_RE.match(stripped):
        return True
    if LEGAL_LABEL_RE.match(stripped):
        return True
    if STRUCTURAL_RE.match(stripped):
        return True
    if re.match(r"^\d{4}年\d{1,2}月\d{1,2}日$", stripped):
        return True
    return False


def _join_text(left: str, right: str) -> str:
    right = right.strip()
    if CONTINUATION_START_RE.match(right):
        return left.rstrip() + right
    if re.search(r"[A-Za-z0-9]$", left) and re.match(r"^[A-Za-z0-9]", right):
        return left.rstrip() + " " + right
    return left.rstrip() + right


def _should_merge(left: str, right: str) -> bool:
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return False
    if _is_structural_line(left) or _is_structural_line(right):
        return False
    if _cjk_count(left) < 6 or _cjk_count(right) < 2:
        return False
    if CONTINUATION_START_RE.match(right):
        return True
    if WEAK_END_RE.search(left):
        return True
    if not STRONG_END_RE.search(left):
        return True
    return False


def run_linebreak_postprocess(markdown: str) -> PostprocessResult:
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    output: list[str] = []
    current: str | None = None
    merge_count = 0
    in_fence = False

    def flush_current() -> None:
        nonlocal current
        if current is not None:
            output.append(current)
            current = None

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith(("```", "~~~")):
            flush_current()
            output.append(line)
            in_fence = not in_fence
            continue

        if in_fence or _is_markdown_boundary(line) or _is_structural_line(line):
            flush_current()
            output.append(line)
            continue

        if current is None:
            current = stripped
            continue

        if _should_merge(current, stripped):
            current = _join_text(current, stripped)
            merge_count += 1
        else:
            flush_current()
            current = stripped

    flush_current()
    result = "\n".join(output).strip()
    log = []
    if merge_count:
        log.append(
            {
                "action": "line_merge",
                "category": "hard_wrap",
                "count": str(merge_count),
                "description": "合并明显属于同一中文段落的 OCR 硬换行",
            }
        )
    return PostprocessResult(text=result, log=log)
