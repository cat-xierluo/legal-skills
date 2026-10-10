#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
manifest v1：只读导出与历史快照迁移（DY-003）

子命令:
  export        只读源库 → 写新目标目录的 manifest JSON（绝不覆盖已有输出、绝不写源库）
  migrate-legacy 在库副本上把旧 video_metadata 播放量(全 0,无法区分缺失/真实零)
                迁为 unknown_legacy 快照；只增不改旧表,删掉 metric_snapshots 即可恢复

数据契约见 references/manifest-contract.md（schema_version=1）。

用法:
  python scripts/manifest.py export --db douyin_users.db --out <新目录>
  python scripts/manifest.py export --db douyin_users.db --out <新目录> --root <视频根目录>
  python scripts/manifest.py migrate-legacy --db <副本.db>

退出码: 0=成功; 1=输入/校验失败; 2=冲突拒绝
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timezone

SCHEMA_VERSION = 1
SNAPSHOT_TABLE = "metric_snapshots"

SNAPSHOT_DDL = f"""
CREATE TABLE IF NOT EXISTS {SNAPSHOT_TABLE} (
    aweme_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    source TEXT NOT NULL,
    window TEXT,
    digg_count INTEGER,
    comment_count INTEGER,
    collect_count INTEGER,
    share_count INTEGER,
    play_count INTEGER,
    PRIMARY KEY (aweme_id, observed_at, source)
)
"""

METRIC_KEYS = ("digg_count", "comment_count", "collect_count", "share_count", "play_count")


class ManifestError(Exception):
    """输入/校验失败(退出码 1)"""


class ConflictError(Exception):
    """同键不同值的快照冲突(退出码 2)"""


# ============ 快照写入(采集端,download-v2 也复用) ============

def ensure_snapshot_table(conn: sqlite3.Connection):
    conn.execute(SNAPSHOT_DDL)


def append_snapshot(conn: sqlite3.Connection, aweme_id: str, observed_at: str,
                    source: str, stats: dict, window: str = None,
                    missing_as_null: bool = True):
    """追加一条指标快照。

    幂等/冲突契约: 同 (aweme_id, observed_at, source) 已存在且各指标值
    完全一致 → 忽略(幂等); 任一不一致 → ConflictError(拒绝,绝不覆盖)。
    指标缺失写 NULL(未知),真实 0 写 0——两者由此可区分。
    """
    if not aweme_id or not isinstance(aweme_id, str):
        raise ManifestError(f"aweme_id 非法: {aweme_id!r}")
    if not observed_at or not isinstance(observed_at, str):
        raise ManifestError(f"observed_at 非法: {observed_at!r}")
    if not source:
        raise ManifestError("source 不能为空")

    values = {k: stats.get(k) for k in METRIC_KEYS}  # 缺失 → None → NULL
    for k, v in values.items():
        if v is not None and not isinstance(v, int):
            raise ManifestError(f"指标 {k} 非整数: {v!r}")

    row = conn.execute(
        f"SELECT {', '.join(METRIC_KEYS)}, window FROM {SNAPSHOT_TABLE} "
        "WHERE aweme_id=? AND observed_at=? AND source=?",
        (aweme_id, observed_at, source),
    ).fetchone()
    if row is not None:
        existing = {k: row[i] for i, k in enumerate(METRIC_KEYS)}
        existing_window = row[len(METRIC_KEYS)]
        if existing == values and existing_window == window:
            return False  # 幂等: 指标与窗口完全一致的重复快照
        if existing == values:
            raise ConflictError(
                f"快照冲突: aweme_id={aweme_id} observed_at={observed_at} "
                f"source={source} 指标一致但 window 不同"
                f"(存量={existing_window!r} vs 本次={window!r});拒绝覆盖")
        raise ConflictError(
            f"快照冲突: aweme_id={aweme_id} observed_at={observed_at} "
            f"source={source} 已存在且值不同(拒绝覆盖)")

    conn.execute(
        f"INSERT INTO {SNAPSHOT_TABLE} (aweme_id, observed_at, source, window, "
        f"{', '.join(METRIC_KEYS)}) VALUES (?,?,?,?,?,?,?,?,?)",
        (aweme_id, observed_at, source, window,
         *[values[k] for k in METRIC_KEYS]),
    )
    return True


# ============ 只读连接 ============

def ro_connect(db_path: Path) -> sqlite3.Connection:
    """只读打开源库(mode=ro);文件不存在/不可读立即报错,绝不创建"""
    if not db_path.exists():
        raise ManifestError(f"源库不存在: {db_path}")
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError as e:
        raise ManifestError(f"只读打开失败: {e}") from None


def _check_columns(conn: sqlite3.Connection, table: str, required: set):
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if not cols:
        raise ManifestError(f"源库缺少表 {table}")
    missing = required - cols
    if missing:
        raise ManifestError(f"表 {table} 缺列: {sorted(missing)}")


# ============ 导出 ============

def _iso_from_epoch(ts) -> str:
    if not ts or ts <= 0:
        return None  # 未知/未提供
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()


def export_manifest(db_path: Path, out_dir: Path, root: Path = None,
                    digg_floor: int = 0) -> Path:
    """只读导出 manifest v1 到新目录。返回 manifest 文件路径。"""
    conn = ro_connect(db_path)
    try:
        _check_columns(conn, "user_info_web",
                       {"uid", "sec_user_id", "nickname", "peer_type"})
        _check_columns(conn, "video_metadata",
                       {"aweme_id", "uid", "nickname", "desc", "create_time",
                        "duration", "digg_count", "comment_count",
                        "collect_count", "share_count", "play_count", "fetch_time"})

        authors = {}
        for r in conn.execute(
                "SELECT uid, sec_user_id, nickname, peer_type FROM user_info_web"):
            authors[r["uid"]] = {
                "uid": r["uid"],
                "sec_user_id": r["sec_user_id"],
                "nickname": r["nickname"],
                "cohort": r["peer_type"] or "followed",
            }

        videos = {}
        for r in conn.execute("SELECT * FROM video_metadata"):
            aweme_id = r["aweme_id"]
            if not aweme_id or not str(aweme_id).strip():
                raise ManifestError(f"video_metadata 存在非法 aweme_id: {aweme_id!r}")
            if r["create_time"] is not None and r["create_time"] < 0:
                raise ManifestError(f"aweme_id={aweme_id} create_time 为负: {r['create_time']}")
            videos[aweme_id] = {
                "aweme_id": aweme_id,
                "author_uid": r["uid"],
                "desc": r["desc"],
                "published_at": _iso_from_epoch(r["create_time"]),
                "duration_ms": r["duration"] if (r["duration"] or 0) > 0 else None,
                "local_filename": None,  # v1 未绑定本地资产(见契约文档 assets 节)
            }

        # 快照(若有): 每作品取每 source 最新一条作为 current;全部快照都进入 history
        snapshots = {}
        has_snap = bool(conn.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{SNAPSHOT_TABLE}'"
        ).fetchone())
        if has_snap:
            for r in conn.execute(
                    f"SELECT * FROM {SNAPSHOT_TABLE} ORDER BY aweme_id, observed_at, source"):
                snap = {
                    "observed_at": r["observed_at"],
                    "source": r["source"],
                    "window": r["window"],
                    "values": {k: r[k] for k in METRIC_KEYS},
                }
                snapshots.setdefault(r["aweme_id"], []).append(snap)

        # 封面索引(Task-002): <root>/<作者目录>/_covers.json → assets.cover
        cover_index = {}
        if root and Path(root).exists():
            import re as _re
            for author_dir in Path(root).iterdir():
                idx = author_dir / "_covers.json"
                if not (author_dir.is_dir() and idx.exists()):
                    continue
                try:
                    data = json.loads(idx.read_text(encoding="utf-8"))
                except Exception:
                    continue
                for aid, entry in (data.get("covers") or {}).items():
                    f = author_dir / entry.get("file", "")
                    cover_index[aid] = {
                        "path": str(f.relative_to(root)),
                        "kind": entry.get("kind"),
                        "signature_ok": entry.get("signature_ok"),
                        "exists": f.exists(),
                        "note": None if (f.exists() and entry.get("signature_ok"))
                                else ("file_missing" if not f.exists() else "signature_invalid"),
                    }

        items = []
        for aweme_id, v in sorted(videos.items()):
            author = authors.get(v["author_uid"])
            snaps = snapshots.get(aweme_id)

            metrics = None
            missing_fields = []
            if snaps:
                latest = snaps[-1]
                metrics = dict(latest)
                missing_fields = [k for k in METRIC_KEYS if metrics["values"].get(k) is None]
                if metrics["source"].startswith("legacy"):
                    # 旧表全 0 无法区分缺失/真实零 → 未知
                    if metrics["values"].get("play_count") is None:
                        missing_fields.append("play_count:unknown_legacy")
            else:
                # 无快照表: 退化用 video_metadata 旧行,play_count=0 语义未知
                row = conn.execute(
                    "SELECT digg_count, comment_count, collect_count, share_count, "
                    "play_count, fetch_time FROM video_metadata WHERE aweme_id=?",
                    (aweme_id,),
                ).fetchone()
                metrics = {
                    "observed_at": _iso_from_epoch(row["fetch_time"]),
                    "source": "legacy/video_metadata",
                    "window": None,
                    "values": {k: row[k] for k in METRIC_KEYS},
                }
                if (row["play_count"] or 0) == 0:
                    metrics["values"]["play_count"] = None
                    missing_fields.append("play_count:unknown_legacy")
                missing_fields += [k for k in METRIC_KEYS
                                   if k != "play_count" and metrics["values"].get(k) is None]

            # 播放分母比例: 分母缺失/未知/为 0 时一律 null(不以点赞反推播放)
            play = metrics["values"].get("play_count")
            engagement = None
            if play is not None and play > 0:
                digg = metrics["values"].get("digg_count") or 0
                engagement = round(digg / play, 6)

            item = {
                "schema_version": SCHEMA_VERSION,
                "author": author or {"uid": v["author_uid"], "sec_user_id": None,
                                     "nickname": None, "cohort": None},
                "video": {k: v[k] for k in
                          ("aweme_id", "desc", "published_at", "duration_ms", "local_filename")},
                "assets": {
                    "source_video": None,
                    "cover": cover_index.get(aweme_id),
                    "raw_transcript": None,
                    "corrected_transcript": None,
                    "frames": None,
                    "note": ("cover 已按 aweme_id 绑定(见 _covers.json);其余资产 v1 未绑定"
                             if aweme_id in cover_index else
                             "v1 未绑定本地资产路径(封面缺项保留,不伪造)"),
                },
                "metrics_snapshot": {
                    "current": metrics,
                    "history_len": len(snaps) if snaps else 0,
                    "missing_fields": missing_fields,
                },
                "derived": {
                    "digg_per_play": engagement,
                    "note": "play 缺失/未知/为 0 时为 null;不以其他指标反推播放量",
                },
            }
            items.append(item)

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_db": str(db_path),
            "video_root": str(root) if root else None,
            "counts": {"authors": len(authors), "videos": len(items)},
            "items": items,
        }

        # 输出校验: 新目录、不覆盖已有产物
        if out_dir.exists():
            raise ManifestError(f"输出目录已存在,拒绝覆盖: {out_dir}")
        out_dir.mkdir(parents=True)
        out_path = out_dir / "manifest.json"
        out_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return out_path
    finally:
        conn.close()


# ============ 旧库迁移(只在副本上跑) ============

def migrate_legacy(db_path: Path, in_place_confirm: str = None) -> dict:
    """把旧 video_metadata 迁为 unknown_legacy 快照。

    只在库副本上执行: 默认拒绝主位库名含 douyin_users.db 的路径,除非
    显式传入 in_place_confirm='migrate-in-place'(生产采用另走验收)。
    迁移只新增 metric_snapshots 表与行,旧表逐字节不动;
    回滚 = DROP TABLE metric_snapshots(可恢复)。
    """
    if in_place_confirm != "migrate-in-place" and db_path.name == "douyin_users.db":
        raise ManifestError(
            "拒绝在疑似主位库上迁移: 请在副本上执行,或显式确认生产采用流程")
    if not db_path.exists():
        raise ManifestError(f"库不存在: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # 守卫(审计 R1-P2):已有采集快照时 DROP 会误删——生产库必须先备份并
        # 由明确采用方案处理,本工具只在"迁移前无快照表/空表"的副本上执行
        pre = conn.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{SNAPSHOT_TABLE}'"
        ).fetchone()
        if pre is not None:
            n_real = conn.execute(
                f"SELECT count(*) FROM {SNAPSHOT_TABLE} WHERE source != 'legacy/video_metadata'"
            ).fetchone()[0]
            if n_real > 0:
                raise ManifestError(
                    f"{SNAPSHOT_TABLE} 已含 {n_real} 条非 legacy 采集快照——回滚(DROP)会误删;"
                    f"生产采用须先备份并单独立案,不在本工具范围"
                    f"(纯 legacy 快照的幂等重跑不受此限)")
        ensure_snapshot_table(conn)
        rows = conn.execute(
            "SELECT aweme_id, digg_count, comment_count, collect_count, share_count, "
            "play_count, fetch_time FROM video_metadata").fetchall()
        migrated = skipped = 0
        for r in rows:
            observed = _iso_from_epoch(r["fetch_time"]) or "1970-01-01T00:00:00+00:00"
            # 旧行 play_count 全 0 且无法区分缺失 → 一律 NULL(unknown_legacy)
            stats = {
                "digg_count": r["digg_count"],
                "comment_count": r["comment_count"],
                "collect_count": r["collect_count"],
                "share_count": r["share_count"],
                "play_count": None,
            }
            try:
                if append_snapshot(conn, r["aweme_id"], observed,
                                   "legacy/video_metadata", stats):
                    migrated += 1
                else:
                    skipped += 1
            except ConflictError:
                skipped += 1  # 已有同键不同值快照: 保留现值,不覆盖
        conn.commit()
        return {"migrated": migrated, "skipped_idempotent_or_conflict": skipped,
                "rollback": f"DROP TABLE {SNAPSHOT_TABLE};"}
    finally:
        conn.close()


# ============ CLI ============

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="manifest v1 导出与历史迁移(DY-003)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pExport = sub.add_parser("export", help="只读源库导出 manifest(不写源库/不覆盖输出)")
    pExport.add_argument("--db", required=True, help="源 douyin_users.db(只读)")
    pExport.add_argument("--out", required=True, help="输出目录(必须不存在)")
    pExport.add_argument("--root", default=None, help="视频根目录(仅记录到 manifest,不扫描)")

    pMig = sub.add_parser("migrate-legacy", help="旧 video_metadata → unknown_legacy 快照(在副本上)")
    pMig.add_argument("--db", required=True, help="库副本路径")
    pMig.add_argument("--in-place-confirm", default=None,
                      help="生产库显式确认标记(默认拒绝主位库名)")

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    try:
        if args.cmd == "export":
            out = export_manifest(Path(args.db).expanduser(),
                                  Path(args.out).expanduser(),
                                  Path(args.root).expanduser() if args.root else None)
            print(f"[完成] manifest: {out}")
            return 0
        if args.cmd == "migrate-legacy":
            result = migrate_legacy(Path(args.db).expanduser(), args.in_place_confirm)
            print(f"[完成] 迁移: {result}")
            return 0
    except ConflictError as e:
        print(f"[冲突拒绝] {e}", file=sys.stderr)
        return 2
    except ManifestError as e:
        print(f"[错误] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
