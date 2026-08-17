#!/usr/bin/env python3
"""OLE2 老版 .doc 模板 → OOXML .docx 批量转换（一次性预处理脚本）。

读取 67 类官方要素式起诉状/答辩状模板（OLE2 二进制格式），用 LibreOffice headless
批量转换为真 OOXML docx，输出 SHA-256 manifest 用于后续渲染校验。

适用场景
--------
仅供 v0.1 MVP 一次性预处理使用；后续每半年提醒用户核查官方版本更新并重跑。

依赖
----
- LibreOffice 25.x（macOS: `brew install --cask libreoffice`）
- Python 3.11+

输出
----
- 指定 --output 目录：N 份真 docx
- 指定 --manifest 路径：templates-manifest.json（数组，每份模板含
  original_name / original_sha256 / original_size / converted_name /
  converted_sha256 / converted_size / converted_at / case_type_hint）

示例
----
python scripts/ole2_to_docx.py \\
    --input "~/Desktop/要素式起诉状模板/67类" \\
    --output assets/templates-docx \\
    --manifest assets/templates-manifest.json \\
    --limit 2   # v0.1 MVP 只跑 2 份（民间借贷、离婚）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

DEFAULT_SOFFICE_PATHS = [
    "/opt/homebrew/Caskroom/libreoffice/25.8.4.upgrading/LibreOffice.app/Contents/MacOS/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
]


@dataclass(frozen=True)
class TemplateEntry:
    """单份模板的转换元数据。"""

    original_name: str
    original_path: str
    original_sha256: str
    original_size: int
    converted_name: str
    converted_path: str
    converted_sha256: str
    converted_size: int
    converted_at: str  # ISO 8601 with timezone


def detect_soffice() -> str:
    """在 macOS/Linux 常见位置查找 soffice，找不到则抛错。"""
    for path in DEFAULT_SOFFICE_PATHS:
        if Path(path).exists():
            return path
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    raise RuntimeError(
        "找不到 LibreOffice soffice；请先 `brew install --cask libreoffice`，"
        "或把 soffice 路径加进 DEFAULT_SOFFICE_PATHS。"
    )


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_one(soffice: str, src: Path, dst_dir: Path, timeout: int = 120) -> Path:
    """单文件转换；返回输出 docx 路径。失败抛 RuntimeError。"""
    dst_dir.mkdir(parents=True, exist_ok=True)
    # LibreOffice headless 要求 -env:UserInstallation 指向独立目录，避免多进程冲突
    with tempfile.TemporaryDirectory() as user_profile:
        cmd = [
            soffice,
            f"-env:UserInstallation=file://{user_profile}",
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(dst_dir),
            str(src),
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"soffice 转换失败: {src}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
            )
    out = dst_dir / (src.stem + ".docx")
    if not out.exists():
        raise RuntimeError(f"soffice 未产出 {out}")
    return out


def case_type_hint(filename: str) -> str:
    """从文件名粗略推断案由分类，仅作 manifest 元数据，便于人工检索。

    形如 `01-离婚纠纷民事起诉状.docx`、`03-金融借款合同纠纷民事起诉状.docx`、
    `46-侵害著作权及邻接权纠纷民事起诉状.docx`。
    """
    name = filename
    for prefix in ("01-", "02-", "03-", "04-", "05-", "06-", "07-", "08-", "09-",
                   "10-", "11-", "12-", "13-", "14-", "15-", "16-", "17-",
                   "18-", "19-", "20-", "21-", "22-", "23-", "24-", "25-",
                   "26-", "27-", "28-", "29-", "30-", "31-", "32-", "33-",
                   "34-", "35-", "36-", "37-", "38-", "39-", "40-", "41-",
                   "42-", "43-", "44-", "45-", "46-", "47-", "48-", "49-",
                   "50-", "51-", "52-", "53-", "54-", "55-", "56-", "57-",
                   "58-", "59-", "60-", "61-", "62-", "63-", "64-", "65-",
                   "66-", "67-"):
        if name.startswith(prefix):
            rest = name[len(prefix):]
            # 取中段案由名（去掉"民事起诉状"等后缀）
            for suffix in (
                "民事起诉状.docx",
                "行政起诉状.docx",
                "国家赔偿申请书.docx",
                "申请书.docx",
            ):
                if rest.endswith(suffix):
                    return rest[: -len(suffix)]
            return rest.replace(".docx", "")
    return ""


def iter_ole2(src_dir: Path) -> Iterable[Path]:
    """遍历 src_dir 下扩展名为 .docx 的文件（OLE2 文件的扩展名虽然是 .docx）。"""
    yield from sorted(p for p in src_dir.iterdir() if p.is_file() and p.suffix.lower() == ".docx")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path, help="OLE2 模板目录（67类/）")
    parser.add_argument("--output", required=True, type=Path, help="docx 输出目录")
    parser.add_argument("--manifest", required=True, type=Path, help="manifest.json 输出路径")
    parser.add_argument(
        "--limit", type=int, default=0, help="只转前 N 份（0=全部）"
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="GLOB",
        help="只转文件名匹配 glob 的文件；可重复多次。例如 --include '01-*' --include '02-*'",
    )
    parser.add_argument("--soffice", type=str, default="", help="显式指定 soffice 路径")
    parser.add_argument("--timeout", type=int, default=120, help="单文件转换超时（秒）")
    args = parser.parse_args()

    soffice = args.soffice or detect_soffice()
    print(f"[ole2_to_docx] soffice = {soffice}")
    print(f"[ole2_to_docx] input   = {args.input}")
    print(f"[ole2_to_docx] output  = {args.output}")

    if not args.input.exists():
        print(f"[ole2_to_docx] 错误：输入目录不存在 {args.input}", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    sources = list(iter_ole2(args.input))
    if args.include:
        import fnmatch
        sources = [s for s in sources if any(fnmatch.fnmatch(s.name, g) for g in args.include)]
    if args.limit > 0:
        sources = sources[: args.limit]

    print(f"[ole2_to_docx] 待转换 {len(sources)} 份")
    started = time.monotonic()
    entries: list[TemplateEntry] = []
    failed: list[tuple[Path, str]] = []

    for i, src in enumerate(sources, 1):
        t0 = time.monotonic()
        try:
            dst = convert_one(soffice, src, args.output, timeout=args.timeout)
        except Exception as e:
            failed.append((src, str(e)))
            print(f"  [{i}/{len(sources)}] ✗ {src.name}  ({e})")
            continue
        entry = TemplateEntry(
            original_name=src.name,
            original_path=str(src),
            original_sha256=sha256_of(src),
            original_size=src.stat().st_size,
            converted_name=dst.name,
            converted_path=str(dst),
            converted_sha256=sha256_of(dst),
            converted_size=dst.stat().st_size,
            converted_at=datetime.now(timezone.utc).isoformat(),
        )
        entries.append(entry)
        dt = time.monotonic() - t0
        print(f"  [{i}/{len(sources)}] ✓ {src.name}  →  {dst.name}  ({dt:.1f}s)")

    elapsed = time.monotonic() - started
    print(f"[ole2_to_docx] 完成 {len(entries)} 份，失败 {len(failed)} 份，耗时 {elapsed:.1f}s")

    manifest = {
        "schema_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "soffice_path": soffice,
        "source_dir": str(args.input),
        "output_dir": str(args.output),
        "case_type_hints": {e.converted_name: case_type_hint(e.original_name) for e in entries},
        "templates": [asdict(e) for e in entries],
        "failed": [{"name": p.name, "error": err} for p, err in failed],
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ole2_to_docx] manifest 写入 {args.manifest}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())