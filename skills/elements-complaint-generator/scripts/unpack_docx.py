#!/usr/bin/env python3
"""docx → OOXML 源码目录树（模板入库用）。

把 docx（zip 容器）解包为纯文本 XML 目录树，作为 git 可 diff 的模板源码。
官方 OLE2 .doc 先经 ole2_to_docx.py（soffice）转 docx，再用本脚本入库。

用法
----
python scripts/unpack_docx.py --input assets/tmp-docx/ --output assets/templates-ooxml/
python scripts/unpack_docx.py --input 某模板.docx --output assets/templates-ooxml/
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


def unpack_one(docx_path: Path, out_root: Path, overwrite: bool = False) -> Path:
    """单文件解包。输出目录名 = docx 文件名去扩展名。返回输出目录路径。"""
    out_dir = out_root / docx_path.stem
    if out_dir.exists() and not overwrite:
        raise FileExistsError(f"目标已存在（--overwrite 覆盖）：{out_dir}")
    if out_dir.exists():
        for f in sorted(out_dir.rglob("*"), reverse=True):
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                f.rmdir()
        out_dir.rmdir()
    out_dir.mkdir(parents=True)
    with zipfile.ZipFile(docx_path) as z:
        z.extractall(out_dir)
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path, help="docx 文件或目录（目录则批量）")
    parser.add_argument("--output", required=True, type=Path, help="OOXML 树输出根目录")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的模板目录")
    args = parser.parse_args()

    if args.input.is_dir():
        targets = sorted(args.input.glob("*.docx"))
    elif args.input.is_file():
        targets = [args.input]
    else:
        print(f"[unpack_docx] 错误：输入不存在 {args.input}", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    ok, fail = 0, 0
    for t in targets:
        try:
            out = unpack_one(t, args.output, overwrite=args.overwrite)
            n_files = sum(1 for f in out.rglob("*") if f.is_file())
            print(f"  ✓ {t.name} → {out.name}/（{n_files} 个文件）")
            ok += 1
        except Exception as e:
            print(f"  ✗ {t.name}: {e}", file=sys.stderr)
            fail += 1
    print(f"[unpack_docx] 完成 {ok}，失败 {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())