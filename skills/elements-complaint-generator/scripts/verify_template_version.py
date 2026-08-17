#!/usr/bin/env python3
"""模板版本核查（半年复查配套）：对比源目录 docx 的 SHA-256 与 manifest 记录。

用途
----
官方发布新版模板后（或到复查日 2026-11-17），把新完整版目录传入本脚本，
与 `templates/templates-manifest.json` 中记录的原件 SHA-256 比对，
输出：未变更 / 内容变更 / 新增 / 缺失 四类报告，辅助决定是否需要重跑入库。

用法
----
python scripts/verify_template_version.py \\
    --source "~/Desktop/要素式起诉状模板/67类完整版(起诉状+答辩状+第三人意见陈述书)" \\
    [--manifest templates/templates-manifest.json]

退出码：0=无变更；1=有变更（需人工审阅）；2=输入错误
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, type=Path, help="新版完整版根目录（含 上/中/下册）")
    parser.add_argument("--manifest", type=Path,
                        default=Path(__file__).resolve().parent.parent / "templates" / "templates-manifest.json")
    args = parser.parse_args()

    src = Path(args.source).expanduser()
    if not src.is_dir():
        print(f"[verify] 错误：源目录不存在 {src}", file=sys.stderr)
        return 2
    data = json.loads(args.manifest.read_text(encoding="utf-8"))

    # manifest: tree → {source_path(~/…), source_sha256}
    recorded = {e["tree"]: e for e in data.get("trees", [])}
    # 重建树名（与 ingest_full_templates 相同规则）太复杂——直接按 source_file + volume 定位
    # 简化匹配：新版文件按 (volume, source_file) 对齐
    by_key = {}
    for e in data.get("trees", []):
        by_key[(e["volume"], e["source_file"])] = e

    new_files: list[tuple[str, str, Path]] = []   # (volume, filename, path)
    for volume in ("上册", "中册", "下册"):
        vol = src / volume
        if not vol.is_dir():
            continue
        for folder in sorted(vol.iterdir()):
            if not folder.is_dir():
                continue
            for f in sorted(folder.glob("*.docx")):
                new_files.append((volume, f.name, f))

    unchanged, changed, added = [], [], []
    seen = set()
    for vol, fname, f in new_files:
        e = by_key.get((vol, fname))
        if e is None:
            # 尝试宽松匹配：同名文件不管卷
            e = next((x for (v2, n2), x in by_key.items() if n2 == fname), None)
        if e is None:
            added.append(f"{vol}/{fname}")
            continue
        seen.add(e["tree"])
        new_sha = sha256_of(f)
        if new_sha == e["source_sha256"]:
            unchanged.append(e["tree"])
        else:
            changed.append((e["tree"], f"{vol}/{fname}"))

    missing = [t for t in recorded if t not in seen]

    print(f"[verify] 源目录：{src}")
    print(f"[verify] 未变更 {len(unchanged)} / 内容变更 {len(changed)} / 新增 {len(added)} / 疑缺失 {len(missing)}")
    if changed:
        print("\n⚠️ 内容变更（官方改版，需重跑入库 + git diff 审查 + 规则回归）：")
        for tree, loc in changed[:20]:
            print(f"  - {tree} ← {loc}")
    if added:
        print("\n🆕 新增文件（原 manifest 无对应条目）：")
        for a in added[:20]:
            print(f"  + {a}")
    if missing:
        print(f"\n❓ 疑缺失（{len(missing)} 棵树在新版源中未找到对应文件）：")
        for t in missing[:10]:
            print(f"  ? {t}")
    if not changed and not added and not missing:
        print("[verify] ✅ 与当前 manifest 完全一致，无需更新")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())