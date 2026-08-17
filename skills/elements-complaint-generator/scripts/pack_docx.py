#!/usr/bin/env python3
"""OOXML 源码目录树 → docx（打包输出用）。

把解包形态的模板树（或渲染后已编辑的树副本）打包回 Word 可打开的 docx。
文件按排序遍历写入 zip，Word/WPS/LibreOffice 均可正常打开。

用法
----
python scripts/pack_docx.py --tree assets/templates-ooxml/02-民间借贷 --output out.docx
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


def pack_tree(tree_dir: Path, out_docx: Path) -> int:
    """打包目录树为 docx。返回写入的文件数。"""
    files = sorted(f for f in tree_dir.rglob("*") if f.is_file())
    if not files:
        raise FileNotFoundError(f"目录树为空：{tree_dir}")
    if not (tree_dir / "[Content_Types].xml").exists():
        raise FileNotFoundError(f"缺少 [Content_Types].xml，不是有效的 OOXML 树：{tree_dir}")
    out_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_docx, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            arcname = f.relative_to(tree_dir).as_posix()
            z.writestr(arcname, f.read_bytes())
    return len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tree", required=True, type=Path, help="OOXML 目录树")
    parser.add_argument("--output", required=True, type=Path, help="输出 docx 路径")
    args = parser.parse_args()

    if not args.tree.is_dir():
        print(f"[pack_docx] 错误：目录不存在 {args.tree}", file=sys.stderr)
        return 2
    try:
        n = pack_tree(args.tree, args.output)
    except Exception as e:
        print(f"[pack_docx] 错误：{e}", file=sys.stderr)
        return 2
    print(f"[pack_docx] {args.tree} → {args.output}（{n} 个文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())