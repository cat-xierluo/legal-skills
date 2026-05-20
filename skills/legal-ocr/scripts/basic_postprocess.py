from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class PostprocessResult:
    text: str
    log: list[dict[str, str]] = field(default_factory=list)


CHAPTER_RE = re.compile(r"^(第[一二三四五六七八九十百千万\d]+章\s*.+)$")
SECTION_RE = re.compile(r"^(第[一二三四五六七八九十百千万\d]+节\s*.+)$")
ARTICLE_RE = re.compile(r"^(第[一二三四五六七八九十百千万\d]+条\s*.+)$")
COURT_HEADING_RE = re.compile(
    r"^(原告诉称|被告辩称|第三人述称|上诉人上诉称|被上诉人辩称|申请人称|被申请人辩称|"
    r"诉讼请求|事实和理由|审理经过|本院查明|经审理查明|本院认为|裁判结果|判决如下|"
    r"裁定如下|审理查明|法院认为)[:：]?$"
)


def _normalize_heading(line: str) -> tuple[str, str | None]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return stripped, None
    if CHAPTER_RE.match(stripped):
        return f"## {stripped}", "chapter"
    if SECTION_RE.match(stripped):
        return f"### {stripped}", "section"
    if COURT_HEADING_RE.match(stripped):
        return f"## {stripped}", "court_heading"
    if ARTICLE_RE.match(stripped) and not stripped.startswith("**"):
        return f"**{stripped}**", "article"
    return stripped, None


def run_basic_postprocess(markdown: str) -> PostprocessResult:
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")
    log: list[dict[str, str]] = []
    normalized_lines: list[str] = []

    for line_no, raw_line in enumerate(text.split("\n"), start=1):
        line = raw_line.rstrip()
        normalized, action = _normalize_heading(line)
        if action:
            log.append({"line": str(line_no), "action": action, "text": normalized})
        normalized_lines.append(normalized)

    text = "\n".join(normalized_lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return PostprocessResult(text=text, log=log)
