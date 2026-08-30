#!/usr/bin/env python3
"""校验朋友圈与公众号 DRAFT 的长度、结构与白名单。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from validate_report import PLACEHOLDER_RE, URL_RE, allowed_domain, load_whitelist


WECHAT_SECTIONS = ("导语", "发生了什么", "为什么值得关注", "给企业的提示", "信源", "免责声明")


def _urls(text: str) -> list[str]:
    return list(dict.fromkeys(URL_RE.findall(text)))


def _content_length(text: str) -> int:
    stripped = re.sub(r"(?m)^\s*(?:#|>|-|\d+\.)+\s*", "", text)
    return len(re.sub(r"\s+", "", stripped))


def _read(path: Path, label: str, findings: list[dict]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        findings.append({"id": "CHANNEL-READ", "artifact": label, "message": str(exc)})
        return ""


def validate_channels(moments: Path, wechat: Path, whitelist_path: Path, brief: Path | None = None) -> dict:
    findings: list[dict] = []
    moments_text = _read(moments, "moments", findings)
    wechat_text = _read(wechat, "wechat", findings)
    brief_text = _read(brief, "brief", findings) if brief else ""
    brief_urls = set(_urls(brief_text))
    try:
        whitelist = load_whitelist(whitelist_path)
    except ValueError as exc:
        findings.append({"id": "CHANNEL-WHITELIST", "artifact": "all", "message": str(exc)})
        whitelist = set()

    for label, path, text in (("moments", moments, moments_text), ("wechat", wechat, wechat_text)):
        if text and ("_DRAFT" not in path.stem or "DRAFT" not in text):
            findings.append({"id": "CHANNEL-DRAFT", "artifact": label, "message": "文件名与正文都必须保留 DRAFT 标识"})
        if text and PLACEHOLDER_RE.search(text):
            findings.append({"id": "CHANNEL-PLACEHOLDER", "artifact": label, "message": "仍有未替换占位符"})
        urls = _urls(text)
        if not urls:
            findings.append({"id": "CHANNEL-SOURCE", "artifact": label, "message": "至少保留一个可点击信源 URL"})
        if whitelist:
            rejected = sorted({urlparse(url).hostname for url in urls if urlparse(url).hostname and not allowed_domain(urlparse(url).hostname or "", whitelist)})
            if rejected:
                findings.append({"id": "CHANNEL-WHITELIST", "artifact": label, "message": f"发现白名单外域名: {', '.join(rejected)}"})
        if brief_urls:
            drifted = sorted(set(urls) - brief_urls)
            if drifted:
                findings.append({"id": "CHANNEL-SOURCE-DRIFT", "artifact": label, "message": f"渠道稿出现完整简报未使用的信源: {', '.join(drifted)}"})
        if "不构成针对具体事项的法律意见" not in text:
            findings.append({"id": "CHANNEL-DISCLAIMER", "artifact": label, "message": "缺少法律意见免责声明"})

    moments_length = _content_length(moments_text)
    if moments_text and not 80 <= moments_length <= 900:
        findings.append({"id": "MOMENTS-LENGTH", "artifact": "moments", "message": f"朋友圈正文应为 80—900 个非空白字符，当前 {moments_length}"})
    if moments_text and len(re.findall(r"(?m)^\s*(?:[-*]|\d+\.)\s+", moments_text)) > 3:
        findings.append({"id": "MOMENTS-DENSITY", "artifact": "moments", "message": "朋友圈稿要点超过 3 条"})

    headings = [item.strip() for item in re.findall(r"(?m)^##\s+(.+?)\s*$", wechat_text)]
    missing = [required for required in WECHAT_SECTIONS if not any(required in heading for heading in headings)]
    if missing:
        findings.append({"id": "WECHAT-SECTIONS", "artifact": "wechat", "message": f"缺少必需章节: {', '.join(missing)}"})

    return {
        "schema_version": 1,
        "status": "PASS" if not findings else "FAIL",
        "artifacts": {
            "moments": {"path": str(moments), "sha256": hashlib.sha256(moments_text.encode()).hexdigest(), "content_length": moments_length},
            "wechat": {"path": str(wechat), "sha256": hashlib.sha256(wechat_text.encode()).hexdigest(), "section_count": len(headings)},
        },
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="校验客户简报的朋友圈与公众号草稿")
    parser.add_argument("--moments", required=True)
    parser.add_argument("--wechat", required=True)
    parser.add_argument("--whitelist", required=True)
    parser.add_argument("--brief", help="可选：完整简报，用于阻断渠道稿新增事实来源")
    args = parser.parse_args()
    result = validate_channels(
        Path(args.moments).resolve(),
        Path(args.wechat).resolve(),
        Path(args.whitelist).resolve(),
        Path(args.brief).resolve() if args.brief else None,
    )
    for finding in result["findings"]:
        print(f"[FAIL] {finding['id']} {finding['artifact']}: {finding['message']}", file=sys.stderr)
    if result["status"] == "PASS":
        print("渠道草稿客观门禁通过")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
