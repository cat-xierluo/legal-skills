#!/usr/bin/env python3
"""校验行业报告或客户简报 Markdown 的客观交付门禁。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


REPORT_SECTIONS = (
    "执行摘要",
    "研究边界与方法",
    "行业结构与市场",
    "竞争格局与代表企业",
    "政策监管与区域",
    "法律风险与争议",
    "服务机会与行动建议",
    "附录与信源",
)
BRIEF_SECTIONS = (
    "编辑说明与适用范围",
    "本期一句话",
    "重点变化",
    "客户相关性",
    "行动建议",
    "案例观察",
    "信源与核验",
)
URL_RE = re.compile(r"https?://[^\s<>\])}，。；、]+", re.I)
PLACEHOLDER_RE = re.compile(r"\{[^{}\n]+\}|\[P\?\]|^\s*\.\.\.\s*$", re.MULTILINE)
CASE_NO_RE = re.compile(r"[（(]\d{4}[）)].{0,80}?号")
DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-/.年](1[0-2]|0?[1-9])[-/.月]([12]\d|3[01]|0?[1-9])日?(?!\d)")


def _headings(text: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"(?m)^##\s+(.+?)\s*$", text)]


def _urls(text: str) -> list[str]:
    return list(dict.fromkeys(URL_RE.findall(text)))


def _domains(urls: list[str]) -> set[str]:
    return {host for url in urls if (host := urlparse(url).hostname)}


def load_whitelist(path: Path | None) -> set[str]:
    if path is None or not path.is_file():
        raise ValueError(f"信源白名单不存在: {path}")
    values = {
        raw.split("#", 1)[0].strip().lower().rstrip(".")
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.split("#", 1)[0].strip()
    }
    if not values:
        raise ValueError("信源白名单为空")
    return values


def allowed_domain(domain: str, whitelist: set[str]) -> bool:
    value = domain.lower().rstrip(".")
    return any(value == item or value.endswith(f".{item}") for item in whitelist)


def _section(text: str, keyword: str) -> str:
    match = re.search(rf"(?ms)^##\s+[^\n]*{re.escape(keyword)}[^\n]*\n(.*?)(?=^##\s+|\Z)", text)
    return match.group(1) if match else ""


def _dates(text: str) -> list[date]:
    result = []
    for year, month, day in DATE_RE.findall(text):
        try:
            result.append(date(int(year), int(month), int(day)))
        except ValueError:
            continue
    return result


def validate(
    path: Path,
    kind: str,
    whitelist_path: Path | None = None,
    period_start: str | None = None,
    period_end: str | None = None,
) -> dict:
    findings: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {"status": "FAIL", "findings": [{"id": "DOCUMENT-READ", "message": str(exc)}]}

    headings = _headings(text)
    urls = _urls(text)
    domains = _domains(urls)
    unresolved = sorted(set(PLACEHOLDER_RE.findall(text)))
    prefix = "REPORT" if kind == "report" else "BRIEF"

    if unresolved:
        findings.append({"id": f"{prefix}-PLACEHOLDERS", "message": f"仍有 {len(unresolved)} 类未替换占位符"})

    required = REPORT_SECTIONS if kind == "report" else BRIEF_SECTIONS
    missing = [item for item in required if not any(item in heading for heading in headings)]
    if missing:
        findings.append({"id": f"{prefix}-SECTIONS", "message": f"缺少必需章节: {', '.join(missing)}"})
    if not urls:
        findings.append({"id": f"{prefix}-SOURCES", "message": "未发现可点击的 http(s) 信源 URL"})

    if kind == "report":
        disclaimer_pos = text.find("不构成针对具体事项的法律意见")
        summary_pos = text.find("执行摘要")
        if disclaimer_pos < 0 or summary_pos < 0 or disclaimer_pos > summary_pos:
            findings.append({"id": "REPORT-DISCLAIMER", "message": "免责声明缺失，或未置于执行摘要之前"})
        if urls and len(domains) < 2 and "[单一信源]" not in text:
            findings.append({"id": "REPORT-CROSS-SOURCE", "message": "仅有一个独立域名，且未标注 [单一信源]"})
        if not re.search(r"\[P[1-5]\]", text):
            findings.append({"id": "REPORT-SOURCE-TIER", "message": "未发现 [P1]-[P5] 信源层级标记"})
    else:
        if "_DRAFT" not in path.stem or "DRAFT" not in text:
            findings.append({"id": "BRIEF-DRAFT", "message": "客户简报文件名与正文都必须保留 DRAFT 标识"})
        if "不构成针对具体事项的法律意见" not in text:
            findings.append({"id": "BRIEF-DISCLAIMER", "message": "缺少法律意见免责声明"})
        if "相对上期的新变化" not in text:
            findings.append({"id": "BRIEF-DELTA", "message": "未说明相对上期的新变化"})
        try:
            whitelist = load_whitelist(whitelist_path)
        except ValueError as exc:
            findings.append({"id": "BRIEF-WHITELIST", "message": str(exc)})
            whitelist = set()
        if whitelist:
            rejected = sorted(domain for domain in domains if not allowed_domain(domain, whitelist))
            if rejected:
                findings.append({"id": "BRIEF-WHITELIST", "message": f"发现白名单外域名: {', '.join(rejected)}"})
        if period_start and period_end:
            try:
                start = date.fromisoformat(period_start)
                end = date.fromisoformat(period_end)
            except ValueError:
                findings.append({"id": "BRIEF-WINDOW", "message": "日期窗口必须使用 YYYY-MM-DD"})
            else:
                if start > end:
                    findings.append({"id": "BRIEF-WINDOW", "message": "起始日不能晚于结束日"})
                change_dates = _dates(_section(text, "重点变化"))
                outside = sorted({item.isoformat() for item in change_dates if not start <= item <= end})
                if outside:
                    findings.append({"id": "BRIEF-WINDOW", "message": f"重点变化出现窗口外日期: {', '.join(outside)}"})
        case_text = _section(text, "案例观察")
        if case_text and "本期未收录可核验案例" not in case_text:
            blocks = re.split(r"(?m)^###\s+", case_text)[1:]
            if not blocks:
                findings.append({"id": "BRIEF-CASE", "message": "案例观察未分条，且未声明本期无可核验案例"})
            for index, block in enumerate(blocks, 1):
                missing_case = []
                if not CASE_NO_RE.search(block):
                    missing_case.append("案号")
                if "审理法院" not in block:
                    missing_case.append("审理法院")
                if "裁判日期" not in block:
                    missing_case.append("裁判日期")
                if "核验日期" not in block:
                    missing_case.append("核验日期")
                if not _urls(block):
                    missing_case.append("核验链接")
                if missing_case:
                    findings.append({"id": "BRIEF-CASE", "message": f"第 {index} 个案例缺少: {', '.join(missing_case)}"})

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "schema_version": 1,
        "status": "PASS" if not findings else "FAIL",
        "kind": kind,
        "artifact": str(path),
        "artifact_sha256": digest,
        "measurements": {
            "section_count": len(headings),
            "url_count": len(urls),
            "independent_domain_count": len(domains),
            "finding_count": len(findings),
        },
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="校验行业报告或客户简报的结构、信源与客观门禁")
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--kind", choices=("report", "brief"), required=True)
    parser.add_argument("--whitelist", help="客户简报信源白名单")
    parser.add_argument("--period-start")
    parser.add_argument("--period-end")
    args = parser.parse_args()
    result = validate(
        Path(args.input).resolve(),
        args.kind,
        Path(args.whitelist).resolve() if args.whitelist else None,
        args.period_start,
        args.period_end,
    )
    for finding in result.get("findings", []):
        print(f"[FAIL] {finding['id']}: {finding['message']}", file=sys.stderr)
    if result.get("status") == "PASS":
        print("Markdown 客观门禁通过")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
