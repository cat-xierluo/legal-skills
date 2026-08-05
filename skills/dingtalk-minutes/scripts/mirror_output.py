#!/usr/bin/env python3
"""
钉钉 AI 听记 —— 镜像到外部指定文件夹

把 archive/ 中选定的听记成品（transcript.md / summary.md / todos.md，
默认不含 meta.json 等结构化内部数据）单向复制到外部固定输出目录，
便于在 Obsidian / Clawd 等外部知识库中查阅。

archive 是权威源（增量同步产生），本脚本只做"方便找"的副本：
单向 copy，不回写 archive。镜像失败不影响 archive，仅报告。

用法:
    python mirror_output.py                     # 按 config/mirror-target.local.json 的 dest 镜像全部听记
    python mirror_output.py --since 260801      # 只镜像 26年8月1日 之后开始的听记（YYMMDD）
    python mirror_output.py --archive-dir /path/to/archive   # 指定 archive 根
    python mirror_output.py --archive <听记目录>            # 只镜像单条听记
    python mirror_output.py --dest /path/to/output          # 覆盖 config 的 dest
    python mirror_output.py --items transcript,summary      # 白名单（可选: transcript/summary/todos/keywords）

镜像目标结构:
    <dest>/<YYMMDD>_<标题>/
        ├── transcript.md
        ├── summary.md
        └── todos.md

每个听记子目录下写 .mirror-manifest.json（源 archive 路径、镜像时间、
文件列表 + sha256），便于事后核对。已有目标文件且哈希一致时跳过（增量）。

依赖: Python 标准库。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "mirror-target.local.json"
MIRROR_SIDECAR = ".mirror-manifest.json"

# 对外成品白名单：transcript/summary/todos 为默认；keywords/meta 可选
ITEM_TO_FILE = {
    "transcript": "transcript.md",
    "summary": "summary.md",
    "todos": "todos.md",
    "keywords": "keywords.md",
    "meta": "meta.json",
}
DEFAULT_ITEMS: tuple[str, ...] = ("transcript", "summary", "todos")
VALID_ITEM_KEYS = frozenset(ITEM_TO_FILE.keys())


class MirrorError(RuntimeError):
    pass


@dataclass
class MirrorRecord:
    rel_path: str
    sha256: str
    size: int


@dataclass
class MirrorReport:
    source_archive: str
    destination: str
    items: list[str]
    started_at: str
    finished_at: str = ""
    records: list[MirrorRecord] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    mirror_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_archive": self.source_archive,
            "destination": self.destination,
            "items": self.items,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "mirror_count": self.mirror_count,
            "records": [
                {"path": r.rel_path, "sha256": r.sha256, "size": r.size}
                for r in self.records
            ],
            "skipped": self.skipped,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise MirrorError(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise MirrorError(f"JSON 无效：{path}:{exc.lineno}:{exc.colno} {exc.msg}") from exc
    except UnicodeDecodeError as exc:
        raise MirrorError(f"JSON 不是有效 UTF-8：{path}:{exc.start}") from exc
    except OSError as exc:
        raise MirrorError(f"读取失败：{path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def atomic_write_text(path: Path, value: str) -> None:
    if not value.endswith("\n"):
        value += "\n"
    atomic_write_bytes(path, value.encode("utf-8"))


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_bytes(path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


def _atomic_copy_file(src: Path, dst: Path) -> None:
    """以原子写方式复制文件（先写临时文件再替换），避免半写残留。"""
    if src.resolve() == dst.resolve():
        return
    tmp = dst.with_name(f".{dst.name}.tmp")
    data = src.read_bytes()
    tmp.write_bytes(data)
    tmp.replace(dst)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mirror_output.py",
        description="把 archive 中的听记成品单向镜像到外部指定文件夹",
    )
    parser.add_argument(
        "--archive-dir", type=Path, default=None,
        help="archive 根目录（默认 <skill根>/archive）",
    )
    parser.add_argument(
        "--archive", type=Path, default=None,
        help="单条听记目录；指定后只镜像这一条",
    )
    parser.add_argument(
        "--dest", type=Path, default=None,
        help="外部输出根目录；省略时读 config/mirror-target.local.json",
    )
    parser.add_argument(
        "--items", default=",".join(DEFAULT_ITEMS),
        help=f"白名单，逗号分隔；默认 {','.join(DEFAULT_ITEMS)}（可选：{','.join(sorted(VALID_ITEM_KEYS))}）",
    )
    parser.add_argument(
        "--since", default=None,
        help="只镜像 YYMMDD（如 260801）之后开始的听记；按听记目录名前缀判断",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="预览将复制哪些文件，不写文件",
    )
    return parser.parse_args(argv)


def _resolve_dest(args_dest: Path | None) -> Path:
    if args_dest is not None:
        return args_dest.expanduser().resolve()
    if CONFIG_PATH.exists():
        data = load_json(CONFIG_PATH)
        dest_raw = data.get("dest") if isinstance(data, dict) else None
        if isinstance(dest_raw, str) and dest_raw.strip():
            return Path(dest_raw).expanduser().resolve()
    print(
        "ERROR 未提供 --dest 且 config/mirror-target.local.json 不存在；\n"
        "      请复制 config/mirror-target.example.json 为\n"
        "      config/mirror-target.local.json 并填入 'dest' 字段。",
        file=sys.stderr,
    )
    raise SystemExit(2)


def _resolve_items(items_csv: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in items_csv.split(","):
        key = raw.strip()
        if not key or key in seen:
            continue
        if key not in VALID_ITEM_KEYS:
            raise MirrorError(f"未知白名单项：{key}（可选：{sorted(VALID_ITEM_KEYS)}）")
        seen.add(key)
        result.append(key)
    if not result:
        raise MirrorError("--items 不能全为空")
    return result


def _since_matches(dir_name: str, since: str | None) -> bool:
    """目录名 YYMMDD_标题，判断日期前缀是否 >= since（YYMMDD）。"""
    if not since:
        return True
    prefix = dir_name.split("_", 1)[0] if "_" in dir_name else dir_name
    # 只比较前 6 位数字（YYMMDD）
    return prefix >= since


def _mirror_one(rec_dir: Path, batch_dest: Path, items: list[str],
                report: MirrorReport, dry_run: bool) -> None:
    """镜像单条听记目录。返回 (本次实际复制数, 已存在未变更数, 缺失跳过列表)。"""
    copied = 0
    up_to_date = 0
    skipped: list[str] = []
    for item in items:
        fname = ITEM_TO_FILE[item]
        src = rec_dir / fname
        if not src.exists():
            skipped.append(f"{rec_dir.name}/{fname}")
            continue
        dst = batch_dest / fname
        if dry_run:
            print(f"  [dry-run] 复制 {rec_dir.name}/{fname} → {batch_dest.name}/{fname}")
            copied += 1
            continue
        # 增量：目标已存在且哈希一致 → 已是最新，无需复制
        if dst.exists() and sha256_file(dst) == sha256_file(src):
            up_to_date += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        _atomic_copy_file(src, dst)
        report.records.append(
            MirrorRecord(
                rel_path=f"{batch_dest.name}/{fname}",
                sha256=sha256_file(src),
                size=src.stat().st_size,
            )
        )
        copied += 1
    report.mirror_count += copied
    report.skipped.extend(skipped)
    return copied, up_to_date, skipped


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))

    if args.archive is not None:
        archives: list[Path] = [args.archive.expanduser().resolve()]
    else:
        archive_root = args.archive_dir.expanduser().resolve() if args.archive_dir else (ROOT / "archive")
        if not archive_root.is_dir():
            print(f"ERROR archive 目录不存在：{archive_root}", file=sys.stderr)
            return 2
        archives = sorted(
            [d for d in archive_root.iterdir() if d.is_dir() and d.name != "index.json"]
        )

    dest_root = _resolve_dest(args.dest)
    dest_root.mkdir(parents=True, exist_ok=True)
    items = _resolve_items(args.items)

    report = MirrorReport(
        source_archive=str(archives[0].parent if archives else ""),
        destination=str(dest_root),
        items=items,
        started_at=utc_now(),
    )

    total = 0
    total_up_to_date = 0
    for rec_dir in archives:
        if not rec_dir.is_dir():
            print(f"  [skip] 不是目录：{rec_dir}", file=sys.stderr)
            continue
        # 单条模式传的是听记目录本身；批量模式 rec_dir 是 archive/<听记>
        dir_name = rec_dir.name
        batch_dest = dest_root / dir_name
        if not _since_matches(dir_name, args.since):
            continue
        copied, up_to_date, skipped = _mirror_one(rec_dir, batch_dest, items, report, args.dry_run)
        total_up_to_date += up_to_date
        # 每个听记子目录写一份 .mirror-manifest.json（含本目录复制记录）
        if not args.dry_run and copied:
            per_record = [
                r for r in report.records
                if r.rel_path.startswith(f"{batch_dest.name}/")
            ]
            atomic_write_json(
                batch_dest / MIRROR_SIDECAR,
                {
                    "source": str(rec_dir),
                    "destination": str(batch_dest),
                    "items": items,
                    "mirrored_at": utc_now(),
                    "files": [
                        {"path": Path(r.rel_path).name, "sha256": r.sha256, "size": r.size}
                        for r in per_record
                    ],
                    "skipped": [s.split("/", 1)[1] for s in skipped if s.startswith(f"{rec_dir.name}/")],
                },
            )
        total += 1

    print(
        f"镜像完成：{report.source_archive} → {dest_root}"
        f"（本次复制 {report.mirror_count} 个，已存在未变更 {total_up_to_date} 个，"
        f"缺失跳过 {len(report.skipped)} 个）"
    )
    if report.skipped:
        print(f"  跳过：{', '.join(report.skipped[:10])}")
        if len(report.skipped) > 10:
            print(f"  ... 其余 {len(report.skipped) - 10} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
