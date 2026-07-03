#!/usr/bin/env python3
"""一次性补齐 archive 目录中缺失的 slides 子目录。

背景：save_archive() 历史上只保存 MD + meta，没有复制 slides 目录，
导致 archive/.../file.md 中的图片引用全部失效。本脚本：
  1. 扫描 archive/ 下所有归档目录
  2. 若目录中已有 slides 子目录，跳过
  3. 否则根据 transcription_meta.json 中的 source_file 找到原文件，
     把同级 {stem}_slides/ 复制到归档目录

幂等：可重复运行；已修复的归档会立即跳过。
"""
import json
import shutil
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_ROOT = SKILL_ROOT / "archive"


def fix_one(archive_dir: Path) -> str:
    meta_path = archive_dir / "transcription_meta.json"
    md_path = next(archive_dir.glob("*.md"), None)
    if not md_path:
        return "skip (no md)"

    # 已存在 slides 目录 → 视为已修复
    existing = [d for d in archive_dir.iterdir()
                if d.is_dir() and d.name.endswith("_slides")]
    if existing:
        return f"skip (already has {existing[0].name})"

    # 优先从 meta 里拿 source_file；否则按 MD 同名推断源文件
    src_file = None
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            src_file = meta.get("source_file")
        except Exception:
            pass

    stem = md_path.stem
    candidates = []
    if src_file:
        src = Path(src_file)
        candidates.append(src.parent / f"{stem}_slides")
        candidates.append(src.parent / "slides")
    # 最后兜底：扫描常见下载目录
    for guess in [Path.home() / "Downloads" / f"{stem}_slides",
                  Path.home() / "Downloads" / "slides"]:
        if guess not in candidates:
            candidates.append(guess)

    for slides_src in candidates:
        if slides_src.is_dir():
            slides_dst = archive_dir / slides_src.name
            shutil.copytree(slides_src, slides_dst)
            # 回写 meta
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["slides_copied_from"] = str(slides_src)
                meta["slides_backfilled_at"] = str(slides_dst)
                meta_path.write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            return f"fixed → {slides_dst.name} ({sum(1 for _ in slides_dst.glob('*'))} files)"

    return f"WARN: no slides source found for {stem}"


def main():
    if not ARCHIVE_ROOT.exists():
        print(f"archive 目录不存在: {ARCHIVE_ROOT}")
        sys.exit(1)

    fixed, skipped, warned = 0, 0, 0
    for archive_dir in sorted(ARCHIVE_ROOT.iterdir()):
        if not archive_dir.is_dir():
            continue
        result = fix_one(archive_dir)
        marker = "✓" if result.startswith("fixed") else \
                 "⚠" if result.startswith("WARN") else "·"
        print(f"{marker} {archive_dir.name}: {result}")
        if result.startswith("fixed"):
            fixed += 1
        elif result.startswith("WARN"):
            warned += 1
        else:
            skipped += 1

    print(f"\n汇总: {fixed} 已补齐 · {skipped} 已存在跳过 · {warned} 找不到源 slides")
    sys.exit(0 if warned == 0 else 2)


if __name__ == "__main__":
    main()
