#!/usr/bin/env python3
"""
OCR 双层 PDF 质量验收脚本。

指标：
1) 可检索页占比
2) 关键词命中率
3) CER（可选，需提供参考文本）
4) 输出体积比
5) 处理耗时（可选，手动传入或从日志提取）
"""

import argparse
import json
import re
from pathlib import Path

try:
    import pypdf
except Exception as e:
    raise SystemExit(f"缺少依赖 pypdf，请先安装：pip install pypdf\n{e}")


def normalize_text_for_cer(text: str) -> str:
    """用于 CER 的标准化：移除所有空白。"""
    return re.sub(r"\s+", "", text or "")


def levenshtein_distance(a: str, b: str) -> int:
    """计算编辑距离（空间优化版）。"""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            ins = curr[j - 1] + 1
            delete = prev[j] + 1
            repl = prev[j - 1] + (0 if ca == cb else 1)
            curr.append(min(ins, delete, repl))
        prev = curr
    return prev[-1]


def extract_pdf_text(pdf_path: Path) -> tuple[list[str], str]:
    """提取每页文本和全文。"""
    reader = pypdf.PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    return pages, "\n".join(pages)


def load_keywords(args) -> list[str]:
    items = []
    if args.keywords:
        items.extend([x.strip() for x in args.keywords.split(",") if x.strip()])
    if args.keywords_file:
        raw = Path(args.keywords_file).read_text(encoding="utf-8")
        items.extend([x.strip() for x in raw.splitlines() if x.strip()])
    # 去重且保序
    seen = set()
    result = []
    for k in items:
        if k not in seen:
            seen.add(k)
            result.append(k)
    return result


def parse_runtime_from_log(log_path: Path) -> float | None:
    """从日志中提取耗时（秒）。"""
    if not log_path.exists():
        return None
    text = log_path.read_text(encoding="utf-8", errors="ignore")

    patterns = [
        r"总耗时:\s*([0-9]+(?:\.[0-9]+)?)s",
        r"耗时[:：]\s*([0-9]+(?:\.[0-9]+)?)s",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                return None
    return None


def main():
    parser = argparse.ArgumentParser(description="OCR 双层 PDF 质量验收脚本")
    parser.add_argument("--input-pdf", required=True, help="输入 PDF（OCR 前）")
    parser.add_argument("--output-pdf", required=True, help="输出 PDF（OCR 后）")
    parser.add_argument(
        "--searchable-min-chars",
        type=int,
        default=10,
        help="判定页面可检索的最小字符数，默认 10",
    )
    parser.add_argument("--keywords", help="关键词列表，逗号分隔")
    parser.add_argument("--keywords-file", help="关键词文件（每行一个）")
    parser.add_argument("--reference-text", help="参考文本文件（用于 CER）")
    parser.add_argument("--runtime-sec", type=float, help="本次处理总耗时（秒）")
    parser.add_argument("--runtime-log", help="包含耗时信息的日志文件路径（可选）")

    # 阈值（可选）
    parser.add_argument("--min-searchable-ratio", type=float, help="最小可检索页占比（0-1）")
    parser.add_argument("--min-keyword-hit-rate", type=float, help="最小关键词命中率（0-1）")
    parser.add_argument("--max-cer", type=float, help="最大 CER（0-1）")
    parser.add_argument("--max-size-ratio", type=float, help="最大体积比（output/input）")
    parser.add_argument("--max-runtime-sec", type=float, help="最大耗时（秒）")

    parser.add_argument("--json-output", help="将结果写入 JSON 文件")
    args = parser.parse_args()

    input_pdf = Path(args.input_pdf)
    output_pdf = Path(args.output_pdf)
    if not input_pdf.exists():
        raise SystemExit(f"输入文件不存在: {input_pdf}")
    if not output_pdf.exists():
        raise SystemExit(f"输出文件不存在: {output_pdf}")

    output_pages, output_full_text = extract_pdf_text(output_pdf)
    total_pages = len(output_pages)
    searchable_pages = sum(1 for t in output_pages if len((t or "").strip()) >= args.searchable_min_chars)
    searchable_ratio = (searchable_pages / total_pages) if total_pages else 0.0

    keywords = load_keywords(args)
    keyword_hits = []
    for kw in keywords:
        hit = kw in output_full_text
        keyword_hits.append({"keyword": kw, "hit": hit})
    keyword_hit_rate = (sum(1 for x in keyword_hits if x["hit"]) / len(keyword_hits)) if keyword_hits else None

    cer = None
    if args.reference_text:
        ref_text = Path(args.reference_text).read_text(encoding="utf-8", errors="ignore")
        ref_norm = normalize_text_for_cer(ref_text)
        out_norm = normalize_text_for_cer(output_full_text)
        if ref_norm:
            dist = levenshtein_distance(out_norm, ref_norm)
            cer = dist / len(ref_norm)

    runtime_sec = args.runtime_sec
    if runtime_sec is None and args.runtime_log:
        runtime_sec = parse_runtime_from_log(Path(args.runtime_log))

    input_size = input_pdf.stat().st_size
    output_size = output_pdf.stat().st_size
    size_ratio = (output_size / input_size) if input_size else None

    checks = []
    def add_check(name: str, value, threshold, op: str):
        if threshold is None or value is None:
            return
        if op == ">=":
            passed = value >= threshold
        else:
            passed = value <= threshold
        checks.append(
            {
                "name": name,
                "value": value,
                "threshold": threshold,
                "operator": op,
                "passed": passed,
            }
        )

    add_check("searchable_ratio", searchable_ratio, args.min_searchable_ratio, ">=")
    add_check("keyword_hit_rate", keyword_hit_rate, args.min_keyword_hit_rate, ">=")
    add_check("cer", cer, args.max_cer, "<=")
    add_check("size_ratio", size_ratio, args.max_size_ratio, "<=")
    add_check("runtime_sec", runtime_sec, args.max_runtime_sec, "<=")

    all_passed = all(x["passed"] for x in checks) if checks else True

    report = {
        "input_pdf": str(input_pdf),
        "output_pdf": str(output_pdf),
        "total_pages": total_pages,
        "searchable_pages": searchable_pages,
        "searchable_ratio": searchable_ratio,
        "keyword_total": len(keywords),
        "keyword_hit_rate": keyword_hit_rate,
        "keyword_hits": keyword_hits,
        "cer": cer,
        "input_size_bytes": input_size,
        "output_size_bytes": output_size,
        "size_ratio": size_ratio,
        "runtime_sec": runtime_sec,
        "checks": checks,
        "all_passed": all_passed,
    }

    print("=" * 60)
    print("OCR 质量验收报告")
    print("=" * 60)
    print(f"页数: {total_pages}")
    print(f"可检索页: {searchable_pages}/{total_pages} ({searchable_ratio:.2%})")
    if keyword_hit_rate is not None:
        print(f"关键词命中率: {keyword_hit_rate:.2%} ({sum(1 for x in keyword_hits if x['hit'])}/{len(keyword_hits)})")
    if cer is not None:
        print(f"CER: {cer:.4f}")
    print(f"体积比(output/input): {size_ratio:.3f}" if size_ratio is not None else "体积比: N/A")
    if runtime_sec is not None:
        print(f"耗时: {runtime_sec:.2f}s")

    if checks:
        print("-" * 60)
        print("阈值校验:")
        for c in checks:
            state = "PASS" if c["passed"] else "FAIL"
            print(
                f"[{state}] {c['name']}: {c['value']:.6f} {c['operator']} {c['threshold']}"
            )
        print("-" * 60)
        print(f"总体结论: {'PASS' if all_passed else 'FAIL'}")

    if args.json_output:
        out_path = Path(args.json_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON 报告: {out_path}")

    print("=" * 60)

    # 若设置了阈值，则返回状态码体现是否通过
    raise SystemExit(0 if all_passed else 2)


if __name__ == "__main__":
    main()
