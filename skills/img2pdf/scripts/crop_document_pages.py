#!/usr/bin/env python3
"""Execute visually reviewed page rectangles; this is not a page detector."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path


def load_image_module():
    try:
        from PIL import Image
    except ImportError as exc:
        print("缺少依赖 Pillow。请运行：python3 -m pip install 'Pillow>=10.0.0'", file=sys.stderr)
        raise SystemExit(1) from exc
    return Image


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def integers(value, length: int) -> bool:
    return isinstance(value, list) and len(value) == length and all(type(v) is int for v in value)


def validate_manifest(manifest: Path, Image, manifest_bytes: bytes) -> list[dict]:
    data = json.loads(manifest_bytes.decode("utf-8"))
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("需要 schema_version: 1 的 JSON 对象")
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("pages 应为非空数组")
    result = []
    identities = set()
    for index, item in enumerate(pages, 1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 项不是对象")
        for key in ("source", "document", "page"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"第 {index} 项缺少非空字符串 {key}")
        identity = (item["document"], item["page"])
        if identity in identities:
            raise ValueError(f"第 {index} 项重复文书页身份；先核是否重复截图")
        identities.add(identity)
        source = Path(item["source"]).expanduser()
        if not source.is_absolute():
            source = manifest.parent / source
        source = source.resolve(strict=True)
        if source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError(f"第 {index} 项不是支持的图片格式")
        expected_hash = item.get("source_sha256")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise ValueError(f"第 {index} 项缺少有效 source_sha256")
        raw = source.read_bytes()
        if digest(raw) != expected_hash:
            raise ValueError(f"第 {index} 项来源哈希变化；重新查看图片并确认坐标")
        with Image.open(io.BytesIO(raw)) as image:
            size = image.size
            image.load()
        if not integers(item.get("source_size"), 2) or tuple(item["source_size"]) != size:
            raise ValueError(f"第 {index} 项来源尺寸不匹配；坐标应对应原图")
        box = item.get("crop")
        if not integers(box, 4):
            raise ValueError(f"第 {index} 项 crop 应为四个整数 [left, top, right, bottom]")
        left, top, right, bottom = box
        if not (0 <= left < right <= size[0] and 0 <= top < bottom <= size[1]):
            raise ValueError(f"第 {index} 项裁切矩形为空或越界")
        result.append({**item, "source": str(source), "output": f"{index:04d}.png"})
    return result


def execute(manifest: Path, output_dir: Path, dry_run: bool) -> dict:
    Image = load_image_module()
    manifest_bytes = manifest.read_bytes()
    pages = validate_manifest(manifest, Image, manifest_bytes)
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("输出目录已存在；请指定新的目录，避免混入旧页或覆盖文件")
    if dry_run:
        return {"schema_version": 1, "dry_run": True, "pages": pages}
    # All manifest/schema/bounds checks finish before any output is created.
    output_dir.mkdir(parents=True, exist_ok=False)
    completed = []
    for item in pages:
        raw = Path(item["source"]).read_bytes()
        if digest(raw) != item["source_sha256"]:
            raise ValueError("裁切前来源发生变化；停止，已写部分页不可作为完整交付")
        with Image.open(io.BytesIO(raw)) as image:
            cropped = image.crop(item["crop"])
            target = output_dir / item["output"]
            with target.open("xb") as stream:
                cropped.save(stream, format="PNG")
            completed.append({**item, "output_sha256": digest(target.read_bytes()),
                              "output_size": list(cropped.size)})
    receipt = {"schema_version": 1, "manifest_sha256": digest(manifest_bytes),
               "pages": completed}
    with (output_dir / "crop_receipt.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return {"schema_version": 1, "output_dir": str(output_dir), "page_count": len(completed)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args.manifest.expanduser().resolve(), args.output_dir.expanduser().absolute(), args.dry_run)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"裁切失败：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
