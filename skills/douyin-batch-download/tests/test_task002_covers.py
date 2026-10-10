#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task-002 隔离回归: F2 封面能力复用与封面证据

验证契约(对应 TASKS.md Task-002 验收,合成媒体样例):
1. 封面按 aweme_id 绑定改名(<aweme_id>_cover.jpeg/.webp) + _covers.json 索引
2. 同描述不同作品(命名含 create_time)不串片
3. 损坏图片(签名不符)标记 signature_ok=false,缺项保留不伪造
4. 无法绑定命名的封面原样保留并记 _unbound
5. 重复执行不重写有效产物(fetched_at 不变)
6. build_cover_map 与 F2 同源命名(format_file_name)
7. manifest export 封面字段: 绑定→assets.cover;缺失→null+缺项说明
8. .jpeg 静态封面进入搬运清单(旧 *.jpg 漏 .jpeg 的缺口)

运行(需主目录 venv 的 f2): cd <skill>/tests && <主目录>/.venv/bin/python test_task002_covers.py
真实登录态/真实封面下载 NOT_VERIFIED。
"""

import json
import os
import sys
import hashlib
import tempfile
import unittest
import importlib.util
import subprocess
import sqlite3
from pathlib import Path

TESTS_DIR = Path(__file__).parent.resolve()
SCRIPTS_DIR = TESTS_DIR.parent / "scripts"
MAIN_SKILL = Path(os.environ.get("DY_TEST_SKILL_DIR") or
                  str(Path.home() / "Library/Application Support/maoscripts/skills/legal-skills/skills/douyin-batch-download"))
VENV_PY = MAIN_SKILL / ".venv" / "bin" / "python"

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100            # 合法 JPEG 魔数
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 40  # 合法 WEBP 魔数
GARBAGE = b"THIS-IS-NOT-AN-IMAGE" * 8


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class Task002Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SCRIPTS_DIR))
        # 先以标准名加载 utils.config,保证 download-v2 内部 import 绑定同一实例
        cls.dl = _load_module("download_v2_t2", SCRIPTS_DIR / "download-v2.py")
        cls.cfg = sys.modules["utils.config"]

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t002_"))
        self.root = self.tmp / "root"
        self.root.mkdir()
        self.cfg.set_overrides(download_root=str(self.root))
        self.staging = self.tmp / "staging"
        self.nick_dir = self.staging / "douyin" / "post" / "作者甲"
        self.nick_dir.mkdir(parents=True)

    def tearDown(self):
        self.cfg.set_overrides(download_root="", db_path="", following_path="")

    def _reorg(self, cover_map=None):
        return self.dl.reorganize_files("作者甲", "UID1", self.staging, cover_map or {})

    def _index(self):
        p = self.root / "作者甲" / "_covers.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def test_01_bind_jpeg_cover(self):
        (self.nick_dir / "20260101_标题A_cover.jpeg").write_bytes(JPEG)
        cmap = {"20260101_标题A_cover": {"aweme_id": "AW1", "kind": "cover",
                                          "url": "https://img/x.jpeg"}}
        folder = self._reorg(cmap)
        self.assertEqual(folder, "作者甲")
        f = self.root / "作者甲" / "AW1_cover.jpeg"
        self.assertTrue(f.exists())
        idx = self._index()
        self.assertEqual(idx["covers"]["AW1"]["file"], "AW1_cover.jpeg")
        self.assertEqual(idx["covers"]["AW1"]["kind"], "cover")
        self.assertTrue(idx["covers"]["AW1"]["signature_ok"])
        self.assertEqual(idx["covers"]["AW1"]["source_url"], "https://img/x.jpeg")

    def test_02_animated_webp(self):
        (self.nick_dir / "20260102_标题B_cover.webp").write_bytes(WEBP)
        cmap = {"20260102_标题B_cover": {"aweme_id": "AW2", "kind": "animated",
                                          "url": "https://img/anim.webp"}}
        self._reorg(cmap)
        self.assertTrue((self.root / "作者甲" / "AW2_cover.webp").exists())
        self.assertEqual(self._index()["covers"]["AW2"]["kind"], "animated")

    def test_03_same_desc_no_cross_binding(self):
        """同描述不同 create_time(命名不同)→ 各自绑定正确 aweme_id"""
        (self.nick_dir / "20260101_同题_cover.jpeg").write_bytes(JPEG)
        (self.nick_dir / "20260102_同题_cover.jpeg").write_bytes(JPEG)
        cmap = {
            "20260101_同题_cover": {"aweme_id": "AW_A", "kind": "cover", "url": "u1"},
            "20260102_同题_cover": {"aweme_id": "AW_B", "kind": "cover", "url": "u2"},
        }
        self._reorg(cmap)
        self.assertTrue((self.root / "作者甲" / "AW_A_cover.jpeg").exists())
        self.assertTrue((self.root / "作者甲" / "AW_B_cover.jpeg").exists())
        idx = self._index()["covers"]
        self.assertEqual(idx["AW_A"]["source_url"], "u1")
        self.assertEqual(idx["AW_B"]["source_url"], "u2")

    def test_04_invalid_signature_marked(self):
        """损坏图片: 绑定改名但 signature_ok=false(缺项保留不伪造)"""
        (self.nick_dir / "20260103_坏图_cover.jpeg").write_bytes(GARBAGE)
        cmap = {"20260103_坏图_cover": {"aweme_id": "AW3", "kind": "cover", "url": "u3"}}
        self._reorg(cmap)
        idx = self._index()["covers"]["AW3"]
        self.assertFalse(idx["signature_ok"])

    def test_05_unbound_cover_kept(self):
        """无法绑定命名的封面: 原样移动 + _unbound 记录(不伪造 aweme_id)"""
        (self.nick_dir / "神秘历史封面_cover.jpeg").write_bytes(JPEG)
        self._reorg({})
        kept = self.root / "作者甲" / "神秘历史封面_cover.jpeg"
        self.assertTrue(kept.exists())
        idx = self._index()
        self.assertEqual(len(idx["_unbound"]), 1)
        self.assertNotIn("神秘历史封面", json.dumps(idx.get("covers", {})))

    def test_06_idempotent_no_rewrite(self):
        """重复执行不重写有效产物: fetched_at 不变、文件不重复"""
        src = self.nick_dir / "20260104_幂等_cover.jpeg"
        src.write_bytes(JPEG)
        cmap = {"20260104_幂等_cover": {"aweme_id": "AW4", "kind": "cover", "url": "u4"}}
        self._reorg(cmap)
        idx1 = self._index()["covers"]["AW4"]
        # 二次执行(模拟重复运行,封面文件再次出现在 staging)
        self.nick_dir.mkdir(parents=True, exist_ok=True)
        (self.nick_dir / "20260104_幂等_cover.jpeg").write_bytes(JPEG)
        self._reorg(cmap)
        idx2 = self._index()["covers"]["AW4"]
        self.assertEqual(idx1["fetched_at"], idx2["fetched_at"])  # 原条目未重写
        files = list((self.root / "作者甲").glob("AW4_cover*"))
        self.assertEqual(len(files), 1)

    def test_07_build_cover_map_naming(self):
        """build_cover_map 与 F2 format_file_name 同源命名"""
        from f2.apps.douyin.utils import format_file_name
        item = {"create": "20260105", "desc": "标题C", "aweme_id": "AW5",
                "cover": "https://img/c.jpeg", "animated_cover": None}
        kwargs = {"naming": "{create}_{desc}"}
        cmap = self.dl.build_cover_map(kwargs, [item])
        expected_stem = format_file_name("{create}_{desc}", item) + "_cover"
        self.assertIn(expected_stem, cmap)
        self.assertEqual(cmap[expected_stem]["aweme_id"], "AW5")
        # 无封面作品不进映射
        no_cover = {"create": "20260106", "desc": "无图", "aweme_id": "AW6",
                    "cover": None, "animated_cover": None}
        cmap2 = self.dl.build_cover_map(kwargs, [no_cover])
        self.assertEqual(cmap2, {})

    def test_08_legacy_jpeg_moved(self):
        """非 _cover 命名的 .jpeg 图片按普通文件搬运(旧 *.jpg 漏 .jpeg 缺口)"""
        (self.nick_dir / "普通图.jpeg").write_bytes(JPEG)
        self._reorg({})
        self.assertTrue((self.root / "作者甲" / "普通图.jpeg").exists())

    def test_09_manifest_cover_field(self):
        """manifest export: 绑定封面→assets.cover;缺失→null+说明"""
        db = self.tmp / "users.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE user_info_web (uid TEXT, sec_user_id TEXT, nickname TEXT, peer_type TEXT)")
        conn.execute("INSERT INTO user_info_web VALUES ('UID1','SEC1','作者甲','peer')")
        conn.execute("""CREATE TABLE video_metadata (
            aweme_id TEXT PRIMARY KEY, uid TEXT, nickname TEXT, desc TEXT,
            create_time INTEGER, duration INTEGER, digg_count INTEGER, comment_count INTEGER,
            collect_count INTEGER, share_count INTEGER, play_count INTEGER,
            local_filename TEXT, file_size INTEGER, fetch_time INTEGER)""")
        conn.execute("INSERT INTO video_metadata VALUES "
                     "('AW1','UID1','作者甲','x',1760000000,1000,1,1,1,1,0,NULL,NULL,1760000100)")
        conn.execute("INSERT INTO video_metadata VALUES "
                     "('AW9','UID1','作者甲','y',1760000001,1000,1,1,1,1,0,NULL,NULL,1760000100)")
        conn.commit(); conn.close()

        # 作者目录: AW1 有绑定封面,AW9 无
        adir = self.root / "作者甲"
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "AW1_cover.jpeg").write_bytes(JPEG)
        (adir / "_covers.json").write_text(json.dumps({
            "schema_version": 1,
            "covers": {"AW1": {"file": "AW1_cover.jpeg", "kind": "cover",
                               "source_url": "u1", "fetched_at": "t",
                               "bytes": 104, "signature_ok": True}},
        }, ensure_ascii=False), encoding="utf-8")

        out = self.tmp / "manifest_out"
        p = subprocess.run([str(VENV_PY), str(SCRIPTS_DIR / "manifest.py"),
                            "export", "--db", str(db), "--out", str(out),
                            "--root", str(self.root)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        data = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        items = {i["video"]["aweme_id"]: i for i in data["items"]}
        self.assertEqual(items["AW1"]["assets"]["cover"]["path"], "作者甲/AW1_cover.jpeg")
        self.assertTrue(items["AW1"]["assets"]["cover"]["signature_ok"])
        self.assertIsNone(items["AW9"]["assets"]["cover"])
        self.assertIn("封面缺项保留", items["AW9"]["assets"]["note"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
