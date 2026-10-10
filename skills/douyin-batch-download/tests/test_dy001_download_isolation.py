#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DY-001 隔离回归：下载 staging 隔离、作者身份精确化、路径参数统一与退出码

验证契约(对应 TASKS.md DY-001 验收):
1. staging 按运行隔离:并发两实例不互删;共享 <root>/douyin/ 旧临时目录不被触碰
2. 作者身份:已有作者不是最后一行时不串号;特殊字符昵称正确清洗落盘
3. 自定义 --root/--db:下载落到指定 root,元数据写指定 db;db 覆盖时不写默认 following.json
4. 失败语义:下载中断/同步失败 → 返回 False(退出码 1),旧视频与旧 last_fetch_time 保留,
   staging 只清理自己的
5. 真 CLI:sync-following --db/--following/--no-html 退出码与产物正确;download-v2 参数面可用

运行(需要主目录 .venv 的 f2 依赖):
    cd <skill>/tests && <主目录>/.venv/bin/python test_dy001_download_isolation.py
网络下载不在本回归范围(NOT_VERIFIED),F2 网络面全部替身。
"""

import os
import io
import sys
import json
import asyncio
import sqlite3
import hashlib
import tempfile
import unittest
import importlib.util
import subprocess
from pathlib import Path
from contextlib import redirect_stdout
from unittest import mock

TESTS_DIR = Path(__file__).parent.resolve()
SCRIPTS_DIR = TESTS_DIR.parent / "scripts"
SKILL_DIR = TESTS_DIR.parent

# 主目录 .venv(含 f2);worktree 无 .venv(gitignored)
MAIN_SKILL = Path(os.environ.get("DY_TEST_SKILL_DIR") or
                  str(Path.home() / "Library/Application Support/maoscripts/skills/legal-skills/skills/douyin-batch-download"))
VENV_PY = MAIN_SKILL / ".venv" / "bin" / "python"

SEC_TARGET = "MS4wTargetSecUid000001"
SEC_OTHER = "MS4wOtherSecUid000002"
SEC_SPECIAL = "MS4wSpecialSecUid00003"
SEC_CONCURRENT = "MS4wConcurrentSecUid004"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _make_db(db_path: Path, rows):
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE user_info_web (
        uid TEXT, sec_user_id TEXT, nickname TEXT, avatar_url TEXT,
        signature TEXT, follower_count INTEGER, following_count INTEGER, peer_type TEXT)""")
    for uid, sec, nick, ptype in rows:
        conn.execute("INSERT INTO user_info_web (uid, sec_user_id, nickname, peer_type) VALUES (?,?,?,?)",
                     (uid, sec, nick, ptype))
    conn.commit()
    conn.close()


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeAwemeList:
    """替身 F2 aweme 数据对象:含 _to_list/_to_raw"""

    def __init__(self, aweme_id, uid, nickname):
        self.aweme_id = aweme_id
        self.uid = uid
        self.nickname = nickname

    def _to_list(self):
        return [{"aweme_id": self.aweme_id}]

    def _to_raw(self):
        return {"aweme_list": [{
            "aweme_id": self.aweme_id,
            "author": {"uid": self.uid, "nickname": self.nickname},
            "desc": f"desc-{self.aweme_id}",
            "statistics": {"digg_count": 11, "comment_count": 2, "collect_count": 3, "share_count": 4},
        }]}


class FakeDownloader:
    def __init__(self, handler):
        self.handler = handler

    async def create_download_tasks(self, kwargs, video_list, user_path):
        # 把假视频写进本次 staging(F2 真实路径约定:path/douyin/post/<昵称>/)
        for v in video_list:
            nick_dir = Path(kwargs["path"]) / "douyin" / "post" / self.handler.nickname
            nick_dir.mkdir(parents=True, exist_ok=True)
            (nick_dir / f"{v['aweme_id']}.mp4").write_bytes(b"FAKEVIDEO-" + v["aweme_id"].encode())
        if self.handler.fail_with:
            raise self.handler.fail_with


class FakeHandler:
    """替身 DouyinHandler:按 sec_user_id 提供作者与一页视频;可注入失败"""
    fail_with = None

    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.nickname = "未设置"
        self.downloader = FakeDownloader(self)

    async def get_or_add_user_data(self, kwargs, sec_user_id, db):
        self.nickname = SEC_TO_NICK.get(sec_user_id, "未知作者")
        p = Path(kwargs["path"]) / "douyin" / "post" / self.nickname
        p.mkdir(parents=True, exist_ok=True)
        return p

    async def fetch_user_post_videos(self, sec_user_id, max_counts=float("inf")):
        self.nickname = SEC_TO_NICK.get(sec_user_id, "未知作者")
        yield FakeAwemeList(f"aweme-{sec_user_id[-4:]}", SEC_TO_UID[sec_user_id], self.nickname)


SEC_TO_NICK = {}
SEC_TO_UID = {}


class _FakeAsyncUserDB:
    def __init__(self, path):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


async def _fake_get_sec_user_id(url):
    # 按 URL 尾段映射回 sec_user_id
    for sec in SEC_TO_NICK:
        if sec in url:
            return sec
    return SEC_TARGET


class DY001TestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global SEC_TO_NICK, SEC_TO_UID
        sys.path.insert(0, str(SCRIPTS_DIR))
        cls._orig_cwd = os.getcwd()

        SEC_TO_NICK = {
            SEC_TARGET: "目标作者",
            SEC_OTHER: "最后插入的别人",
            SEC_SPECIAL: "特*殊?字:符 作 者",
            SEC_CONCURRENT: "并发作者",
        }
        SEC_TO_UID = {
            SEC_TARGET: "UID-TARGET",
            SEC_OTHER: "UID-OTHER",
            SEC_SPECIAL: "UID-SPECIAL",
            SEC_CONCURRENT: "UID-CONC",
        }

        cls.dl = _load_module("download_v2_under_test", SCRIPTS_DIR / "download-v2.py")
        cls.cfg = sys.modules.get("utils.config") or _load_module("utils_config_under_test", SCRIPTS_DIR / "utils" / "config.py")

        # F2 网络面全替身
        cls._patchers = [
            mock.patch.object(cls.dl, "DouyinHandler", FakeHandler),
            mock.patch.object(cls.dl, "AsyncUserDB", _FakeAsyncUserDB),
            mock.patch.object(cls.dl, "load_config", lambda: {"douyin": {"cookie": "fake-cookie-for-test"}}),
        ]
        import f2.apps.douyin.utils as f2utils
        cls._patchers.append(
            mock.patch.object(f2utils.SecUserIdFetcher, "get_sec_user_id",
                              classmethod(lambda cls, url: _fake_get_sec_user_id(url)))
        )
        for p in cls._patchers:
            p.start()

    @classmethod
    def tearDownClass(cls):
        for p in cls._patchers:
            p.stop()
        os.chdir(cls._orig_cwd)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dy001_"))
        self.root = self.tmp / "root"
        self.root.mkdir()
        self.db = self.tmp / "users.db"
        _make_db(self.db, [
            ("UID-TARGET", SEC_TARGET, "目标作者", "followed"),
            ("UID-SPECIAL", SEC_SPECIAL, "特*殊?字:符 作 者", "peer"),
            ("UID-OTHER", SEC_OTHER, "最后插入的别人", "followed"),  # 刻意最后插入
        ])
        self.fetch_calls = []
        self._patch_update = mock.patch.object(
            self.dl, "update_last_fetch_time",
            lambda uid, nick="": self.fetch_calls.append((uid, nick)))
        self._patch_update.start()
        self.addCleanup(self._patch_update.stop)
        self._patch_sync = mock.patch.object(self.dl, "run_sync", lambda root: True)
        self._patch_sync.start()
        self.addCleanup(self._patch_sync.stop)
        self.addCleanup(lambda: self.cfg.set_overrides(download_root="", db_path="", following_path=""))
        os.chdir(self._orig_cwd)

    def _run(self, sec=SEC_TARGET, **kw):
        url = f"https://www.douyin.com/user/{sec}"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = asyncio.run(self.dl.download_with_stats(url, **kw))
        return rc, buf.getvalue()


class TestDownloadIsolation(DY001TestBase):

    def test_01_author_precise_not_last_row(self):
        """目标作者是首行、他人是末行:身份按 sec_user_id 精确取,不串号"""
        rc, out = self._run(root=str(self.root), db=str(self.db))
        self.assertTrue(rc, out)
        self.assertIn("目标作者", out)
        self.assertNotIn("最后插入的别人", out)
        # 文件落到 <root>/<目标作者>/,而不是末行作者的目录
        self.assertTrue((self.root / "目标作者" / "aweme-0001.mp4").exists())
        self.assertFalse((self.root / "最后插入的别人").exists())
        # 元数据写指定 db,昵称是目标作者
        conn = sqlite3.connect(str(self.db))
        rows = conn.execute("SELECT nickname FROM video_metadata").fetchall()
        conn.close()
        self.assertEqual(rows, [("目标作者",)])

    def test_02_shared_douyin_untouched(self):
        """旧共享 <root>/douyin/ 在途材料不被删除(旧版启动即 rmtree)"""
        canary = self.root / "douyin" / "post" / "别的运行" / "inflight.mp4"
        canary.parent.mkdir(parents=True, exist_ok=True)
        canary.write_bytes(b"OTHER-RUN-IN-FLIGHT")
        before = _sha(canary)

        rc, out = self._run(root=str(self.root), db=str(self.db))
        self.assertTrue(rc, out)
        self.assertTrue(canary.exists())
        self.assertEqual(_sha(canary), before)

    def test_03_concurrent_runs_no_cross_delete(self):
        """同 root 两实例并发:各自 staging,互不删除,双双落盘成功"""
        conn = sqlite3.connect(str(self.db))
        conn.execute("INSERT INTO user_info_web (uid, sec_user_id, nickname, peer_type) "
                     "VALUES ('UID-CONC',?,?,'peer')", (SEC_CONCURRENT, "并发作者"))
        conn.commit(); conn.close()

        async def two():
            t1 = self.dl.download_with_stats(
                f"https://www.douyin.com/user/{SEC_TARGET}",
                root=str(self.root), db=str(self.db))
            t2 = self.dl.download_with_stats(
                f"https://www.douyin.com/user/{SEC_CONCURRENT}",
                root=str(self.root), db=str(self.db))
            return await asyncio.gather(t1, t2)

        buf = io.StringIO()
        with redirect_stdout(buf):
            r1, r2 = asyncio.run(two())
        self.assertTrue(r1); self.assertTrue(r2)
        self.assertTrue((self.root / "目标作者" / "aweme-0001.mp4").exists())
        self.assertTrue((self.root / "并发作者" / f"aweme-{SEC_CONCURRENT[-4:]}.mp4").exists())
        # staging 全部清理
        staging_base = self.root / ".f2-staging"
        leftovers = list(staging_base.iterdir()) if staging_base.exists() else []
        self.assertEqual(leftovers, [])

    def test_04_special_chars_folder(self):
        """非法字符昵称清洗后落盘(与 get_user_folder_name 同一规则)"""
        rc, out = self._run(sec=SEC_SPECIAL, root=str(self.root), db=str(self.db))
        self.assertTrue(rc, out)
        expected = self.cfg.sanitize_folder_name("特*殊?字:符 作 者")
        self.assertTrue((self.root / expected).exists(), f"应有目录 {expected}")
        mp4s = list((self.root / expected).glob("*.mp4"))
        self.assertEqual(len(mp4s), 1)

    def test_05_db_override_skips_default_following(self):
        """自定义 --db:不更新默认 following.json(fetch time 不写)"""
        rc, out = self._run(root=str(self.root), db=str(self.db))
        self.assertTrue(rc, out)
        self.assertIn("不更新默认 following.json", out)
        self.assertEqual(self.fetch_calls, [])

    def test_06_download_failure_preserves_everything(self):
        """下载中断:返回 False,旧视频原样,staging 清理,fetch time 不更新"""
        old_video = self.root / "目标作者" / "old.mp4"
        old_video.parent.mkdir(parents=True, exist_ok=True)
        old_video.write_bytes(b"OLD-VIDEO")
        before = _sha(old_video)

        orig = FakeDownloader.create_download_tasks
        async def boom(self, kwargs, video_list, user_path):
            raise RuntimeError("模拟下载中断")
        FakeDownloader.create_download_tasks = boom
        try:
            rc, out = self._run(root=str(self.root), db=str(self.db))
        finally:
            FakeDownloader.create_download_tasks = orig

        self.assertFalse(rc)
        self.assertIn("下载中断", out)
        self.assertTrue(old_video.exists())
        self.assertEqual(_sha(old_video), before)
        self.assertEqual(self.fetch_calls, [])
        staging_base = self.root / ".f2-staging"
        self.assertEqual(list(staging_base.iterdir()) if staging_base.exists() else [], [])

    def test_07_sync_failure_no_fetch_time(self):
        """同步失败:返回 False 且不更新 last_fetch_time(默认库模式)"""
        with mock.patch.object(self.dl, "run_sync", lambda root: False), \
             mock.patch.object(self.dl, "get_db_path", lambda: self.db):
            rc, out = self._run(root=str(self.root))  # 默认 db 模式(db 指向 fixture)
        self.assertFalse(rc)
        self.assertIn("sync-following 返回非零", out)
        self.assertEqual(self.fetch_calls, [])

    def test_08_exit_code_mapping(self):
        """main() 退出码:成功 0 / 失败 1(真实 argv 解析含 --root/--db)"""
        async def call(argv, retval):
            with mock.patch.object(self.dl, "download_with_stats", mock.AsyncMock(return_value=retval)):
                return await self.dl.main(argv)
        self.assertEqual(asyncio.run(call(["https://x/user/a", "--root", str(self.root),
                                           "--db", str(self.db)], True)), 0)
        self.assertEqual(asyncio.run(call(["https://x/user/a"], False)), 1)
        self.assertEqual(asyncio.run(call([], True)), 0)  # 无 URL 打印用法


class TestSyncFollowingCLI(DY001TestBase):
    """真实 CLI 子进程:sync-following --db/--root/--following/--no-html"""

    def _run_cli(self, *extra):
        return subprocess.run(
            [str(VENV_PY), str(SCRIPTS_DIR / "sync-following.py"), *extra],
            capture_output=True, text=True, timeout=60,
        )

    def test_10_sync_ok_and_counts_from_root(self):
        (self.root / "目标作者").mkdir(parents=True, exist_ok=True)
        (self.root / "目标作者" / "v1.mp4").write_bytes(b"x")
        (self.root / "目标作者" / "v2.mp4").write_bytes(b"x")
        out_json = self.tmp / "following_out.json"
        out_json.write_text(json.dumps({"users": [{
            "uid": "UID-TARGET", "sec_user_id": SEC_TARGET,
            "last_fetch_time": "2026-01-01T00:00:00",
            "custom_field": "保留扩展字段",
        }]}, ensure_ascii=False), encoding="utf-8")

        p = self._run_cli("--db", str(self.db), "--root", str(self.root),
                          "--following", str(out_json), "--no-html")
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(out_json.read_text(encoding="utf-8"))
        users = {u["sec_user_id"]: u for u in data["users"]}
        self.assertEqual(users[SEC_TARGET]["video_count"], 2)  # 计数跟随 --root
        self.assertEqual(users[SEC_TARGET]["last_fetch_time"], "2026-01-01T00:00:00")  # 扩展字段保留
        self.assertEqual(users[SEC_TARGET]["peer_type"], "followed")
        # 重建契约为保留 last_fetch_time 等既有白名单字段,未知扩展字段不迁移

    def test_11_sync_missing_db_nonzero(self):
        p = self._run_cli("--db", str(self.tmp / "nope.db"),
                          "--following", str(self.tmp / "o.json"), "--no-html")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("未找到 db", p.stdout)

    def test_12_following_override_skips_html(self):
        """--following 覆盖时默认不生成 index.html(防覆写技能页)"""
        p = self._run_cli("--db", str(self.db), "--root", str(self.root),
                          "--following", str(self.tmp / "o2.json"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("[更新] index.html", p.stdout)


class TestCLISurface(DY001TestBase):
    """参数面/既有入口兼容(不触网络)"""

    def test_20_download_v2_help_and_usage(self):
        p = subprocess.run([str(VENV_PY), str(SCRIPTS_DIR / "download-v2.py"), "--help"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0)
        for flag in ("--root", "--db", "--max-counts", "--daemon"):
            self.assertIn(flag, p.stdout)
        p2 = subprocess.run([str(VENV_PY), str(SCRIPTS_DIR / "download-v2.py")],
                            capture_output=True, text=True, timeout=60)
        self.assertEqual(p2.returncode, 0)
        self.assertIn("用法", p2.stdout)

    def test_21_batch_download_usage_surface(self):
        """batch-download 旧入口:未知参数打印用法,--all/--uid/--sample/--yes 分支保留"""
        src = (SCRIPTS_DIR / "batch-download.py").read_text(encoding="utf-8")
        for token in ("--all", "--uid", "--sample", "--yes", "--daemon"):
            self.assertIn(token, src)
        p = subprocess.run([str(VENV_PY), str(SCRIPTS_DIR / "batch-download.py"), "badarg"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0)
        self.assertIn("未知参数", p.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
