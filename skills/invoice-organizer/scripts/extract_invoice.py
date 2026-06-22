#!/usr/bin/env python3
"""
发票 PDF 批量文本提取。

用 pdftotext (poppler) 提取文本层，逐文件分隔输出，供 AI 解析字段。
仅负责"提取文本"，字段解析由 AI 完成（发票格式多样，正则易碎）。
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def extract_one(pdf_path: Path) -> str:
    """提取单个 PDF 的文本层，返回纯文本。"""
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        text=True,
    )
    return result.stdout


def collect_pdfs(inputs):
    pdfs = []
    for inp in inputs:
        p = Path(inp).expanduser()
        if p.is_dir():
            pdfs.extend(p.glob("*.pdf"))
        elif p.suffix.lower() == ".pdf" and p.exists():
            pdfs.append(p)
    return sorted(set(pdfs))


def main():
    parser = argparse.ArgumentParser(
        description="批量提取发票 PDF 文本（pdftotext 封装）"
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="PDF 文件路径或目录（可多个）",
    )
    args = parser.parse_args()

    if not shutil.which("pdftotext"):
        print("❌ 缺少依赖: pdftotext (poppler)")
        print("   macOS:   brew install poppler")
        print("   Linux:   sudo apt-get install poppler-utils")
        print("   或改用 legal-ocr / pdf skill 做 OCR")
        raise SystemExit(1)

    pdfs = collect_pdfs(args.inputs)
    if not pdfs:
        print("未找到 PDF 文件。")
        raise SystemExit(1)

    for i, pdf in enumerate(pdfs, 1):
        text = extract_one(pdf)
        print(f"========== [{i}/{len(pdfs)}] {pdf.name} ==========")
        if text.strip():
            print(text)
        else:
            print("[无文本层，疑似扫描件，请改用 legal-ocr / pdf skill 做 OCR]")
        print()


if __name__ == "__main__":
    main()
