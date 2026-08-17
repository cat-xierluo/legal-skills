#!/usr/bin/env python3
"""67 类完整版（上/中/下册）全量模板入库 → templates/ OOXML 源码树。

数据源
------
~/Desktop/要素式起诉状模板/67类完整版(起诉状+答辩状+第三人意见陈述书)/
  上册/1-21（刑事自诉4 + 民事9 + 商事8）
  中册/22-36（知产民事9 + 知产行政6 + 垄断行政1）
  下册/37-68（海事4 + 环资3 + 行政11 + 行政答辩状1 + 国赔4 + 执行9）
完整版文件为原生 OOXML docx（无需 soffice），直接解包为源码树。

树命名
------
<NN>-<案由>[-<文书类型>]/
- NN = 完整版官方编号（01-68，两位补零，上中下顺序即编号顺序）
- 案由 = 目录名去掉 "N." 前缀，去全角括号
- 文书类型 = 文件名去 .docx、去尾段（…），规范化缺"状"笔误；
  若与案由同名则省略（如 55-行政答辩状、60-强制执行申请书）

已知源文件命名笔误（入库时规范化，manifest 记录原名）
- "民事起诉（垄断纠纷）" 等缺"状" → 民事起诉状/民事答辩状/行政起诉状
- 42 号目录内文件名误标"环境污染…" → 树名按目录编号取 42-生态破坏…
- 38 号目录名"人参" → 规范为"人身"

用法
----
python scripts/ingest_full_templates.py --source <完整版目录> --templates templates [--overwrite]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

VOLUMES = ["上册", "中册", "下册"]

# 文书类型规范化：源文件名常见笔误 → 规范名
DOC_TYPE_NORMALIZE = {
    "民事起诉": "民事起诉状",
    "民事答辩": "民事答辩状",
    "行政起诉": "行政起诉状",
    "行政答辩": "行政答辩状",
    "刑事（附带民事）自诉状": "刑事附带民事自诉状",
    "刑事（附带民事）自诉答辩状": "刑事附带民事自诉答辩状",
}

# 案由规范化（打包方笔误）
CAUSE_NORMALIZE = {
    "海上、通海水域人参损害责任纠纷": "海上、通海水域人身损害责任纠纷",
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def strip_trailing_paren(s: str) -> str:
    """去掉尾段（…）：'民事起诉状（离婚纠纷）' → '民事起诉状'。"""
    return re.sub(r"（[^）]*）\s*$", "", s.strip()).strip()


def normalize_cause(folder_name: str) -> tuple[str, str]:
    """'5.离婚纠纷' → ('05', '离婚纠纷')；应用案由笔误修正。"""
    m = re.match(r"^(\d+)\.(.+)$", folder_name)
    if not m:
        raise ValueError(f"目录名不符合 'N.案由' 模式：{folder_name}")
    nn = f"{int(m.group(1)):02d}"
    cause = m.group(2).replace("（", "").replace("）", "")
    cause = CAUSE_NORMALIZE.get(cause, cause)
    return nn, cause


def derive_tree_name(folder_name: str, filename: str) -> tuple[str, str, list[str]]:
    """返回 (tree_name, doc_type, notes)。notes 记录规范化处理。"""
    notes: list[str] = []
    nn, cause = normalize_cause(folder_name)
    base = strip_trailing_paren(filename.removesuffix(".docx"))
    doc_type = base.replace("（", "").replace("）", "")
    if doc_type in DOC_TYPE_NORMALIZE:
        notes.append(f"文书名规范化：{base} → {DOC_TYPE_NORMALIZE[doc_type]}")
        doc_type = DOC_TYPE_NORMALIZE[doc_type]
    if doc_type == cause or doc_type == "":
        tree = f"{nn}-{cause}"
    else:
        tree = f"{nn}-{cause}-{doc_type}"
    # 42 号目录内文件误标环境污染 → 树名按目录编号，记录原文件名即可
    return tree, doc_type, notes


def unpack_docx_to_tree(docx: Path, tree_dir: Path, overwrite: bool) -> int:
    """docx 解包到 tree_dir；返回文件数。"""
    if tree_dir.exists():
        if not overwrite:
            raise FileExistsError(f"目标树已存在（--overwrite 覆盖）：{tree_dir}")
        shutil.rmtree(tree_dir)
    tree_dir.mkdir(parents=True)
    with zipfile.ZipFile(docx) as z:
        z.extractall(tree_dir)
    return sum(1 for f in tree_dir.rglob("*") if f.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, type=Path, help="完整版根目录（含 上/中/下册）")
    parser.add_argument("--templates", required=True, type=Path, help="templates/ 输出目录")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的树")
    args = parser.parse_args()

    if not args.source.is_dir():
        print(f"[ingest] 错误：源目录不存在 {args.source}", file=sys.stderr)
        return 2
    args.templates.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    anomalies: list[dict] = []
    failed: list[str] = []
    seen_trees: dict[str, str] = {}

    for volume in VOLUMES:
        vol_dir = args.source / volume
        if not vol_dir.is_dir():
            print(f"[ingest] 警告：缺少 {volume}", file=sys.stderr)
            continue
        folders = sorted(
            (d for d in vol_dir.iterdir() if d.is_dir() and not d.name.startswith(".")),
            key=lambda d: int(re.match(r"^(\d+)\.", d.name).group(1)) if re.match(r"^(\d+)\.", d.name) else 999,
        )
        for folder in folders:
            for f in sorted(folder.glob("*.docx")):
                try:
                    tree, doc_type, notes = derive_tree_name(folder.name, f.name)
                    if tree in seen_trees:
                        raise ValueError(f"树名冲突：{tree}（已来自 {seen_trees[tree]}）")
                    seen_trees[tree] = f"{folder.name}/{f.name}"
                    tree_dir = args.templates / tree
                    n_files = unpack_docx_to_tree(f, tree_dir, overwrite=args.overwrite)
                    entries.append({
                        "tree": tree,
                        "volume": volume,
                        "doc_type": doc_type,
                        "cause_dir": folder.name,
                        "source_file": f.name,
                        "source_path": f"~/Desktop/要素式起诉状模板/67类完整版(起诉状+答辩状+第三人意见陈述书)/{volume}/{folder.name}/{f.name}",
                        "source_sha256": sha256_of(f),
                        "source_size": f.stat().st_size,
                        "tree_files": n_files,
                    })
                    if notes:
                        anomalies.append({"tree": tree, "source_file": f.name, "notes": notes})
                    print(f"  ✓ {volume} {folder.name}/{f.name} → {tree}/（{n_files} 文件）")
                except Exception as e:
                    failed.append(f"{folder.name}/{f.name}: {e}")
                    print(f"  ✗ {folder.name}/{f.name}: {e}", file=sys.stderr)

    manifest = {
        "schema_version": "2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_edition": "法〔2025〕82 号 67 类完整版（起诉状+答辩状+第三人意见陈述书），上中下三册，2025-07-23 官方打包",
        "ingest_script": "scripts/ingest_full_templates.py",
        "count": len(entries),
        "volumes": {v: sum(1 for e in entries if e["volume"] == v) for v in VOLUMES},
        "anomalies": anomalies,
        "trees": sorted(entries, key=lambda e: e["tree"]),
        "failed": failed,
    }
    out = args.templates / "templates-manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"[ingest] 完成：{len(entries)} 棵树 / 失败 {len(failed)}")
    print(f"[ingest] 分册：{manifest['volumes']}")
    print(f"[ingest] 规范化处理 {len(anomalies)} 处（详见 manifest anomalies）")
    print(f"[ingest] manifest → {out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())