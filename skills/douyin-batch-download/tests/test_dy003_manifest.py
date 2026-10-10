#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DY-003 隔离回归：manifest v1 只读导出、指标缺失语义与历史快照

验证契约(对应 TASKS.md DY-003 验收,全部在 SQLite 副本/fixture 上):
1. 同一作品两时间快照均留存(history_len=2)
2. 同快照重复导入幂等;同键不同值冲突拒绝(退出码 2)
3. 缺失(NULL)与真实 0 可区分
4. 播放分母缺失/未知/为 0 时 derived 比例为 null
5. 非法 ID/时间拒绝;输出目录已存在拒绝
6. 只读导出前后源库字节哈希不变
7. 旧 schema 副本可迁移(unknown_legacy)且可恢复(DROP 新表即回滚)

运行: cd <skill>/tests && python3 test_dy003_manifest.py
"""

import json
import sqlite3
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).parent.resolve()
SCRIPTS_DIR = TESTS_DIR.parent / "scripts"
PY = sys.executable or "python3"

sys.path.insert(0, str(SCRIPTS_DIR))
import manifest as mf  # noqa: E402


def _file_sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _make_db(db_path: Path, with_videos=True):
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE user_info_web (
        uid TEXT, sec_user_id TEXT, nickname TEXT, avatar_url TEXT,
        signature TEXT, follower_count INTEGER, following_count INTEGER, peer_type TEXT)""")
    conn.execute("INSERT INTO user_info_web (uid, sec_user_id, nickname, peer_type) "
                 "VALUES ('U1','SEC1','作者甲','peer')")
    conn.execute("INSERT INTO user_info_web (uid, sec_user_id, nickname, peer_type) "
                 "VALUES ('U2','SEC2','作者乙','followed')")
    conn.execute("""CREATE TABLE video_metadata (
        aweme_id TEXT PRIMARY KEY, uid TEXT NOT NULL, nickname TEXT, desc TEXT,
        create_time INTEGER, duration INTEGER,
        digg_count INTEGER DEFAULT 0, comment_count INTEGER DEFAULT 0,
        collect_count INTEGER DEFAULT 0, share_count INTEGER DEFAULT 0,
        play_count INTEGER DEFAULT 0, local_filename TEXT, file_size INTEGER,
        fetch_time INTEGER)""")
    if with_videos:
        # 旧语义: play_count 全 0(含"真实有互动但播放未知")
        conn.execute("INSERT INTO video_metadata VALUES "
                     "('AW1','U1','作者甲','第一条',1760000000,15000,100,10,5,3,0,NULL,NULL,1760000100)")
        conn.execute("INSERT INTO video_metadata VALUES "
                     "('AW2','U2','作者乙','第二条',0,0,0,0,0,0,0,NULL,NULL,0)")
    conn.commit()
    conn.close()


class TestSnapshots(unittest.TestCase):
    """append_snapshot 幂等/冲突/缺失语义"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dy003_"))
        self.db = self.tmp / "snap.db"
        _make_db(self.db, with_videos=False)
        self.conn = sqlite3.connect(str(self.db))
        mf.ensure_snapshot_table(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_01_two_snapshots_retained(self):
        """同作品两个时间的快照都留存"""
        mf.append_snapshot(self.conn, "AW1", "2026-10-10T10:00:00", "t/source",
                           {"digg_count": 10, "play_count": None})
        mf.append_snapshot(self.conn, "AW1", "2026-10-11T10:00:00", "t/source",
                           {"digg_count": 12, "play_count": 500})
        rows = self.conn.execute(
            "SELECT observed_at, digg_count, play_count FROM metric_snapshots "
            "WHERE aweme_id='AW1' ORDER BY observed_at").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], ("2026-10-10T10:00:00", 10, None))
        self.assertEqual(rows[1], ("2026-10-11T10:00:00", 12, 500))

    def test_02_idempotent_same_values(self):
        """同键同值重复导入幂等(不报错不重复)"""
        stats = {"digg_count": 10, "play_count": 0}
        first = mf.append_snapshot(self.conn, "AW1", "2026-10-10T10:00:00", "t/source", stats)
        second = mf.append_snapshot(self.conn, "AW1", "2026-10-10T10:00:00", "t/source", stats)
        self.assertTrue(first)
        self.assertFalse(second)  # 幂等
        n = self.conn.execute("SELECT count(*) FROM metric_snapshots").fetchone()[0]
        self.assertEqual(n, 1)

    def test_03_conflict_rejected(self):
        """同键不同值拒绝(ConflictError,不覆盖)"""
        mf.append_snapshot(self.conn, "AW1", "2026-10-10T10:00:00", "t/source",
                           {"digg_count": 10})
        with self.assertRaises(mf.ConflictError):
            mf.append_snapshot(self.conn, "AW1", "2026-10-10T10:00:00", "t/source",
                               {"digg_count": 11})
        row = self.conn.execute("SELECT digg_count FROM metric_snapshots").fetchone()
        self.assertEqual(row[0], 10)  # 原值保留

    def test_04_missing_vs_real_zero(self):
        """缺失(NULL)与真实 0 可区分"""
        mf.append_snapshot(self.conn, "AW1", "t1", "t/source", {"play_count": None})
        mf.append_snapshot(self.conn, "AW2", "t1", "t/source", {"play_count": 0})
        vals = dict(self.conn.execute(
            "SELECT aweme_id, play_count FROM metric_snapshots").fetchall())
        self.assertIsNone(vals["AW1"])
        self.assertEqual(vals["AW2"], 0)

    def test_05_invalid_inputs_rejected(self):
        with self.assertRaises(mf.ManifestError):
            mf.append_snapshot(self.conn, "", "t1", "t/source", {})
        with self.assertRaises(mf.ManifestError):
            mf.append_snapshot(self.conn, "AW1", "", "t/source", {})
        with self.assertRaises(mf.ManifestError):
            mf.append_snapshot(self.conn, "AW1", "t1", "t/source", {"digg_count": "很多"})

    def test_23_window_in_idempotency(self):
        """审计 R1-P2:同键同指标不同 window → 冲突拒绝(不再误判幂等)"""
        mf.append_snapshot(self.conn, "AW1", "t1", "s/x",
                           {"digg_count": 10}, window="daily")
        with self.assertRaises(mf.ConflictError):
            mf.append_snapshot(self.conn, "AW1", "t1", "s/x",
                               {"digg_count": 10}, window="weekly")
        # 完全一致(含 window)仍幂等
        self.assertFalse(mf.append_snapshot(self.conn, "AW1", "t1", "s/x",
                                            {"digg_count": 10}, window="daily"))

    def test_24_migrate_refuses_existing_snapshots(self):
        """审计 R1-P2:已有采集快照的库拒绝 migrate(DROP 会误删)"""
        conn = sqlite3.connect(str(self.db))
        mf.ensure_snapshot_table(conn)
        mf.append_snapshot(conn, "AW1", "t1", "download-v2/aweme_list", {"digg_count": 1})
        conn.commit(); conn.close()
        with self.assertRaises(mf.ManifestError) as cm:
            mf.migrate_legacy(self.db)
        self.assertIn("误删", str(cm.exception))


class TestExportCLI(unittest.TestCase):
    """真实 CLI: 只读导出、缺播放比例 null、输出保护、源库不变"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dy003x_"))
        self.db = self.tmp / "users.db"
        _make_db(self.db)

    def _cli(self, *args):
        return subprocess.run([PY, str(SCRIPTS_DIR / "manifest.py"), *args],
                              capture_output=True, text=True, timeout=60)

    def test_10_export_readonly_source_intact(self):
        """只读导出:源库前后字节哈希不变;产物正确"""
        before = _file_sha(self.db)
        out = self.tmp / "manifest_out"
        p = self._cli("export", "--db", str(self.db), "--out", str(out))
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertEqual(_file_sha(self.db), before)  # 源库一字节未动

        data = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["counts"]["videos"], 2)
        items = {i["video"]["aweme_id"]: i for i in data["items"]}

        # AW1: 旧表 play=0 → unknown_legacy(null) + 播放分母比例 null
        aw1 = items["AW1"]
        self.assertIsNone(aw1["metrics_snapshot"]["current"]["values"]["play_count"])
        self.assertIn("play_count:unknown_legacy", aw1["metrics_snapshot"]["missing_fields"])
        self.assertIsNone(aw1["derived"]["digg_per_play"])
        self.assertEqual(aw1["metrics_snapshot"]["history_len"], 0)
        self.assertEqual(aw1["author"]["cohort"], "peer")
        self.assertEqual(aw1["video"]["duration_ms"], 15000)
        self.assertIsNotNone(aw1["video"]["published_at"])
        # AW2: create_time=0 → published_at null;指标全 0 也是未知缺播放
        aw2 = items["AW2"]
        self.assertIsNone(aw2["video"]["published_at"])
        self.assertIsNone(aw2["derived"]["digg_per_play"])
        # 资产 v1 未绑定
        self.assertIsNone(aw1["assets"]["cover"])

    def test_11_export_with_snapshots_ratio(self):
        """有快照时: play>0 算比例; play=0 真实零 → 比例仍 null"""
        conn = sqlite3.connect(str(self.db))
        mf.ensure_snapshot_table(conn)
        mf.append_snapshot(conn, "AW1", "2026-10-10T10:00:00", "download-v2/aweme_list",
                           {"digg_count": 50, "play_count": 1000})
        conn.commit()
        conn.close()
        out = self.tmp / "manifest_out2"
        p = self._cli("export", "--db", str(self.db), "--out", str(out))
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        aw1 = next(i for i in data["items"] if i["video"]["aweme_id"] == "AW1")
        self.assertEqual(aw1["derived"]["digg_per_play"], 0.05)
        self.assertEqual(aw1["metrics_snapshot"]["history_len"], 1)
        self.assertEqual(aw1["metrics_snapshot"]["current"]["values"]["play_count"], 1000)

    def test_12_output_dir_exists_refused(self):
        out = self.tmp / "already"
        out.mkdir()
        p = self._cli("export", "--db", str(self.db), "--out", str(out))
        self.assertEqual(p.returncode, 1)
        self.assertIn("拒绝覆盖", p.stderr)

    def test_13_missing_db_rejected(self):
        p = self._cli("export", "--db", str(self.tmp / "nope.db"),
                      "--out", str(self.tmp / "o"))
        self.assertEqual(p.returncode, 1)

    def test_14_bad_rows_rejected(self):
        """非法 ID/时间拒绝"""
        conn = sqlite3.connect(str(self.db))
        conn.execute("INSERT INTO video_metadata VALUES "
                     "('', 'U1','x','bad',-5,0,0,0,0,0,0,NULL,NULL,0)")
        conn.commit()
        conn.close()
        p = self._cli("export", "--db", str(self.db), "--out", str(self.tmp / "o3"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("非法 aweme_id", p.stderr)


class TestLegacyMigration(unittest.TestCase):
    """旧 schema 副本迁移 + 可恢复"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dy003m_"))
        self.db = self.tmp / "copy.db"
        _make_db(self.db)

    def test_20_migrate_and_rollback(self):
        before_videos = _file_sha(self.db)
        conn = sqlite3.connect(str(self.db))
        old_rows = conn.execute("SELECT * FROM video_metadata").fetchall()
        conn.close()

        result = mf.migrate_legacy(self.db)
        self.assertEqual(result["migrated"], 2)

        # 旧表逐字节不动
        conn = sqlite3.connect(str(self.db))
        self.assertEqual(conn.execute("SELECT * FROM video_metadata").fetchall(), old_rows)
        snaps = dict((r[0], r[1]) for r in conn.execute(
            "SELECT aweme_id, play_count FROM metric_snapshots").fetchall())
        self.assertEqual(snaps, {"AW1": None, "AW2": None})  # 旧 0 → unknown(NULL)
        srcs = {r[0] for r in conn.execute("SELECT DISTINCT source FROM metric_snapshots")}
        self.assertEqual(srcs, {"legacy/video_metadata"})
        conn.close()
        self.assertNotEqual(before_videos, _file_sha(self.db))  # 库文件变化(新增表)

        # 导出: unknown_legacy 标注
        out = self.tmp / "out"
        p = subprocess.run([PY, str(SCRIPTS_DIR / "manifest.py"), "export",
                            "--db", str(self.db), "--out", str(out)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        aw1 = next(i for i in data["items"] if i["video"]["aweme_id"] == "AW1")
        self.assertIsNone(aw1["derived"]["digg_per_play"])
        self.assertEqual(aw1["metrics_snapshot"]["history_len"], 1)

        # 可恢复: DROP 新表回到迁移前逻辑状态
        conn = sqlite3.connect(str(self.db))
        conn.execute("DROP TABLE metric_snapshots")
        conn.commit()
        remaining = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='metric_snapshots'").fetchall()
        self.assertEqual(remaining, [])
        conn.close()

    def test_21_refuses_main_db_name(self):
        main_named = self.tmp / "douyin_users.db"
        _make_db(main_named)
        with self.assertRaises(mf.ManifestError):
            mf.migrate_legacy(main_named)

    def test_22_migrate_idempotent(self):
        mf.migrate_legacy(self.db)
        again = mf.migrate_legacy(self.db)
        self.assertEqual(again["migrated"], 0)
        self.assertEqual(again["skipped_idempotent_or_conflict"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
