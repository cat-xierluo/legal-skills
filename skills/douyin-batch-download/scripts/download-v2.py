#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音视频下载脚本 v2 - 使用 F2 Python API，同时保存视频统计数据

工作流程：
1. 使用 F2 Python API 下载视频（自动跳过已存在文件）
2. 在下载过程中保存视频统计数据（点赞、评论、收藏等）到数据库
3. 自动整理文件到下载目录/{博主昵称}/
4. 同步 following.json

用法：
    python scripts/download-v2.py <主页URL>
    python scripts/download-v2.py <主页URL> --max-counts=10
    python scripts/download-v2.py <主页URL> --root <目录> --db <douyin_users.db>

DY-001（2026-10-10）下载隔离与身份/路径契约：
- 下载 staging 按「每次运行」隔离：<root>/.f2-staging/run-<时间戳>-<pid>/，
  F2 仍写 <staging>/douyin/post/<昵称>/；整理完成后把有效媒体发布到
  <root>/<安全昵称>/，再清理本次 staging。绝不触碰共享 <root>/douyin/
  （旧版启动时 rmtree 该目录会删除并发运行的在途材料）。
- 超过 24h 的历史 staging 视为崩溃残留可清理（下载单博主上限 900s）。
- 作者身份按当前 URL 解析出的 sec_user_id 精确查询，不再取数据库最后一行。
- --root/--db 显式覆盖下载根目录与元数据库；db 覆盖时不写默认 following.json
  （following.json 绑定默认库，跨库重建会污染清单）。
- 退出码：0=成功（含零新增）；1=失败（无法解析用户/下载异常/同步失败），
  失败时不更新 last_fetch_time，已有视频与状态保持原样。
"""

import shutil
import json
import sqlite3
import asyncio
import sys
import os
import time
import uuid
import argparse
from pathlib import Path
from datetime import datetime

# 强制使用脚本所在目录作为工作目录
SKILL_DIR = Path(__file__).parent.parent.resolve()
os.chdir(SKILL_DIR)

# 导入统一配置模块
from utils.config import (
    get_download_path,
    get_db_path,
    get_user_folder_name,
    sanitize_folder_name,
    load_config,
    set_overrides,
    get_active_overrides,
)

# 导入 F2 模块
from f2.apps.douyin.handler import DouyinHandler
from f2.apps.douyin.utils import format_file_name
from f2.apps.douyin.db import AsyncUserDB, AsyncVideoDB
from f2.utils.conf_manager import ConfigManager
import f2

# staging 清理阈值：下载单博主超时 900s，24h 远超任何合法运行
STAGING_MAX_AGE_HOURS = 24


def merge_config(main_conf: dict, custom_conf: dict) -> dict:
    """合并配置"""
    result = (main_conf or {}).copy()
    for key, value in (custom_conf or {}).items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key].update(value)
        else:
            result[key] = value
    return result


def get_f2_kwargs(staging_root: Path) -> dict:
    """获取 F2 所需的配置参数（下载写入本次运行独立的 staging 目录）"""
    # 加载 F2 默认配置
    try:
        main_conf_manager = ConfigManager(f2.F2_CONFIG_FILE_PATH)
        all_conf = main_conf_manager.config  # 获取完整配置
        main_conf = all_conf.get("douyin", {}) if all_conf else {}
    except Exception:
        main_conf = {}

    # 加载自定义配置
    custom_conf = load_config()
    douyin_custom = custom_conf.get("douyin", custom_conf)  # 兼容两种格式

    # 合并配置
    kwargs = merge_config(main_conf, douyin_custom)

    # 添加必要参数
    kwargs["app_name"] = "douyin"
    kwargs["mode"] = "post"

    # 设置路径 - 指向本次运行的独立 staging（F2 落盘 <path>/douyin/post/<昵称>/）
    kwargs["path"] = str(staging_root)

    # 封面下载显式声明(Task-002): 配置未写 cover 时默认开启;
    # F2 落盘 <naming>_cover.webp(动态)/.jpeg(静态),由 reorganize 按 aweme_id 绑定
    kwargs["cover"] = bool(douyin_custom.get("cover", True))

    # 确保 cookie 存在
    if not kwargs.get("cookie"):
        raise ValueError("未配置 cookie，请在 config/config.yaml 中设置")

    # 确保 headers 存在（F2 需要这个）
    if not kwargs.get("headers"):
        kwargs["headers"] = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.douyin.com/",
        }

    return kwargs


def create_video_metadata_table():
    """确保视频元数据表存在"""
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_metadata (
            aweme_id TEXT PRIMARY KEY,
            uid TEXT NOT NULL,
            nickname TEXT,
            desc TEXT,
            create_time INTEGER,
            duration INTEGER,
            digg_count INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            collect_count INTEGER DEFAULT 0,
            share_count INTEGER DEFAULT 0,
            play_count INTEGER DEFAULT 0,
            local_filename TEXT,
            file_size INTEGER,
            fetch_time INTEGER
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_video_uid ON video_metadata(uid)
    """)

    # 添加 nickname 列（如果不存在）
    try:
        cursor.execute("ALTER TABLE video_metadata ADD COLUMN nickname TEXT")
    except sqlite3.OperationalError:
        pass  # 列已存在

    conn.commit()
    conn.close()


def save_video_metadata_from_raw(raw_data: dict, nickname: str = ""):
    """从原始 API 响应中提取并保存视频统计数据。

    DY-003: 除写 video_metadata(现行兼容行为不变)外,逐条追加
    metric_snapshots 历史快照(同键同值幂等/同键不同值拒绝)。
    指标缺失存 NULL,真实 0 存 0——旧表把缺失填 0 的语义自此可区分。
    """
    aweme_list = raw_data.get("aweme_list", [])
    if not aweme_list:
        return 0

    from manifest import ensure_snapshot_table, append_snapshot, ConflictError

    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    fetch_time = int(datetime.now().timestamp())
    observed_at = datetime.now().isoformat(timespec="seconds")
    saved_count = 0
    conflicts = []

    ensure_snapshot_table(conn)

    for video in aweme_list:
        aweme_id = video.get("aweme_id", "")
        if not aweme_id:
            continue

        # 从原始数据中获取统计信息
        stats = video.get("statistics", {}) or {}
        author = video.get("author", {}) or {}
        video_nickname = author.get("nickname", nickname)

        cursor.execute("""
            INSERT OR REPLACE INTO video_metadata
            (aweme_id, uid, nickname, desc, create_time, duration,
             digg_count, comment_count, collect_count, share_count, play_count,
             fetch_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            aweme_id,
            author.get("uid", ""),
            video_nickname,
            video.get("desc", ""),
            video.get("create_time", 0),
            video.get("video", {}).get("duration", 0) if video.get("video") else 0,
            stats.get("digg_count", 0),
            stats.get("comment_count", 0),
            stats.get("collect_count", 0),
            stats.get("share_count", 0),
            stats.get("play_count", 0),
            fetch_time
        ))
        saved_count += 1

        try:
            append_snapshot(conn, aweme_id, observed_at, "download-v2/aweme_list", stats)
        except ConflictError as e:
            conflicts.append(str(e))

    conn.commit()
    conn.close()
    if conflicts:
        for c in conflicts[:5]:
            print(f"[冲突] {c}")
        raise ConflictError(f"{len(conflicts)} 条快照冲突(同键不同值),已拒绝;video_metadata 已按现行语义写入")
    return saved_count


# ============ staging 管理（DY-001：每次运行只操作自己的临时材料） ============

def make_staging_root(downloads_path: Path) -> Path:
    """创建本次运行独立的 staging 目录，并清理超龄崩溃残留"""
    staging_base = downloads_path / ".f2-staging"
    staging_base.mkdir(parents=True, exist_ok=True)
    _sweep_stale_staging(staging_base)
    staging_root = staging_base / f"run-{int(time.time())}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    staging_root.mkdir(parents=True, exist_ok=True)
    return staging_root


def _sweep_stale_staging(staging_base: Path, max_age_hours: int = STAGING_MAX_AGE_HOURS):
    """清理超过阈值的 run-* staging 目录（只匹配本命名约定，绝不碰共享 douyin/）"""
    cutoff = time.time() - max_age_hours * 3600
    if not staging_base.exists():
        return
    for d in staging_base.iterdir():
        if not d.is_dir() or not d.name.startswith("run-"):
            continue
        try:
            if d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                print(f"[清理] 过期 staging 残留: {d.name}")
        except OSError:
            pass  # 正被并发访问等异常时留给下一轮


def cleanup_staging(staging_root: Path):
    """清理本次运行自己的 staging 目录（失败容忍：残留交给超龄清扫）"""
    if staging_root and staging_root.exists():
        shutil.rmtree(staging_root, ignore_errors=True)


# ============ 封面绑定(Task-002) ============

COVER_INDEX = "_covers.json"
COVER_INDEX_SCHEMA = 1

VIDEO_INDEX = "_videos.json"   # DCM-004: 视频文件→aweme_id 稳定映射(消费端 manifest 适配用)
VIDEO_INDEX_SCHEMA = 1


def update_video_index(author_dir: Path, video_map: dict):
    """把 <naming> → aweme_id 映射与实际落盘文件名写入/合并 _videos.json(幂等)。"""
    idx_path = author_dir / VIDEO_INDEX
    index = {"schema_version": VIDEO_INDEX_SCHEMA, "videos": {}}
    if idx_path.exists():
        try:
            data = json.loads(idx_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("videos"), dict):
                index = data
        except Exception:
            pass
    changed = False
    now_iso = datetime.now().isoformat()
    for naming, meta in (video_map or {}).items():
        aid = str(meta.get("aweme_id", ""))
        if not aid:
            continue
        # 实际文件: 优先 exact naming.mp4, 否则任何以 naming 开头的 mp4
        cand = author_dir / f"{naming}.mp4"
        if not cand.exists():
            matches = sorted(author_dir.glob(f"{naming}*.mp4"))
            cand = matches[0] if matches else None
        entry = {
            "aweme_id": aid,
            "file": cand.name if cand else None,
            "file_missing": cand is None,
            "fetched_at": now_iso,
        }
        existing = index["videos"].get(aid)
        if not (existing and existing.get("file") == entry["file"]):
            index["videos"][aid] = entry
            changed = True
    if changed or not idx_path.exists():
        idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2),
                            encoding="utf-8")


def build_video_map(kwargs: dict, video_list: list) -> dict:
    """video_list(model dict) → {naming: {aweme_id}}(与 F2 download_video 同源命名)"""
    naming_tpl = kwargs.get("naming", "{create}_{desc}")
    mapping = {}
    for item in video_list or []:
        try:
            stem = format_file_name(naming_tpl, item)
        except Exception:
            continue
        aid = str(item.get("aweme_id", ""))
        if aid:
            mapping[stem] = {"aweme_id": aid}
    return mapping


def _image_signature_ok(path: Path) -> bool:
    """轻量图片签名校验(不引第三方依赖): JPEG/WEBP/PNG 魔数。"""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
        if len(head) < 12:
            return False
        if head[:3] == b"\xff\xd8\xff":                       # JPEG
            return True
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":       # WEBP
            return True
        if head[:8] == b"\x89PNG\r\n\x1a\n":                 # PNG
            return True
        return False
    except OSError:
        return False


def _load_cover_index(author_dir: Path) -> dict:
    idx_path = author_dir / COVER_INDEX
    if not idx_path.exists():
        return {"schema_version": COVER_INDEX_SCHEMA, "covers": {}}
    try:
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("covers"), dict):
            return data
    except Exception:
        pass
    return {"schema_version": COVER_INDEX_SCHEMA, "covers": {}}


def build_cover_map(kwargs: dict, video_list: list) -> dict:
    """从模型字典列表复算 F2 命名,建立 <stem>_cover → {aweme_id, kind, url} 映射。

    与 F2 download_cover 同源(format_file_name + 同一 video_list item),
    命名模板一致时映射即准确;不含封面的作品不进映射。
    """
    naming_tpl = kwargs.get("naming", "{create}_{desc}")
    mapping = {}
    for item in video_list or []:
        try:
            stem = format_file_name(naming_tpl, item) + "_cover"
        except Exception:
            continue
        animated = item.get("animated_cover")
        url = item.get("cover")
        if not (animated or url):
            continue  # 无封面的作品:缺项保留,不伪造
        mapping[stem] = {
            "aweme_id": str(item.get("aweme_id", "")),
            "kind": "animated" if animated else "cover",
            "url": animated or url,
        }
    return mapping


def reorganize_files(nickname: str, uid: str, staging_root: Path,
                     cover_map: dict = None) -> str:
    """把 staging 内该作者的有效媒体发布到 <root>/<安全昵称>/

    只读自己的 staging，不动共享 <root>/douyin/ 与其他作者的目录。
    """
    downloads_path = get_download_path()
    old_path = staging_root / "douyin" / "post" / nickname

    if not old_path.exists():
        return None

    # 使用博主昵称作为文件夹名（清理非法字符）
    folder_name = get_user_folder_name(nickname, uid)
    new_path = downloads_path / folder_name
    new_path.mkdir(parents=True, exist_ok=True)

    # 移动文件(F2 静态封面为 .jpeg,旧清单漏了该扩展名——Task-002 修正)
    moved_count = 0
    cover_files = []  # (staging内文件, 命名stem)
    for pattern in ["*.mp4", "*.jpg", "*.jpeg", "*.webp"]:
        for f in old_path.glob(pattern):
            if f.stem.endswith("_cover"):
                cover_files.append(f)
                continue
            dest = new_path / f.name
            if not dest.exists():
                shutil.move(str(f), str(dest))
                moved_count += 1

    # 封面按 aweme_id 绑定改名后落作者目录,并维护 _covers.json 索引
    bound = unbound = invalid = 0
    if cover_files:
        cover_map = cover_map or {}
        index = _load_cover_index(new_path)
        now_iso = datetime.now().isoformat()
        for f in cover_files:
            meta = cover_map.get(f.stem)
            if meta and meta.get("aweme_id"):
                dest_name = f"{meta['aweme_id']}_cover{f.suffix}"
                dest = new_path / dest_name
                if not dest.exists():
                    shutil.move(str(f), str(dest))
                ok = _image_signature_ok(dest)
                entry = {
                    "file": dest_name,
                    "kind": meta.get("kind"),
                    "source_url": meta.get("url"),
                    "fetched_at": now_iso,
                    "bytes": dest.stat().st_size,
                    "signature_ok": ok,
                }
                # 幂等: 已有有效产物不重写(重复执行不覆盖)
                existing = index["covers"].get(meta["aweme_id"])
                if not (existing and existing.get("signature_ok") and
                        (new_path / existing["file"]).exists()):
                    index["covers"][meta["aweme_id"]] = entry
                else:
                    # 已有有效条目:保留原条目,清理本次重复文件
                    if dest.exists() and existing["file"] != dest_name:
                        dest.unlink()
                bound += 1 if ok else 0
                invalid += 0 if ok else 1
            else:
                # 无法绑定命名(历史遗留/命名漂移):原样移动并在索引记 unbound,不伪造 aweme_id
                dest = new_path / f.name
                if not dest.exists():
                    shutil.move(str(f), str(dest))
                index.setdefault("_unbound", []).append(
                    {"file": f.name, "fetched_at": now_iso})
                unbound += 1
        idx_path = new_path / COVER_INDEX
        idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"  [封面] {nickname}: 绑定 {bound} 无效 {invalid} 未绑定 {unbound}")

    if moved_count > 0:
        print(f"  [移动] {nickname} -> {folder_name} ({moved_count} 文件)")

    return folder_name


def update_last_fetch_time(uid: str, nickname: str = ""):
    """更新 following.json 中的 last_fetch_time（仅默认库模式）"""
    try:
        from following import update_fetch_time
        update_fetch_time(uid, nickname)
        print(f"  [更新] last_fetch_time for {nickname or uid}")
    except ImportError:
        pass


def run_sync(root: Path) -> bool:
    """运行 sync-following.py（跟随实际 root）；失败返回 False"""
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts" / "sync-following.py"),
         "--root", str(root)],
    )
    return proc.returncode == 0


def get_author_by_sec_uid(sec_user_id: str):
    """按当前 URL 解析出的 sec_user_id 精确查询作者（不再取数据库最后一行）"""
    conn = sqlite3.connect(str(get_db_path()))
    cursor = conn.cursor()
    cursor.execute(
        "SELECT uid, nickname FROM user_info_web WHERE sec_user_id = ? "
        "ORDER BY ROWID DESC LIMIT 1",
        (sec_user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return (row[0], row[1]) if row else (None, None)


async def download_with_stats(url: str, max_counts: int = None,
                              root: str = None, db: str = None) -> bool:
    """
    使用 F2 API 下载视频并保存统计数据

    Args:
        url: 用户主页 URL
        max_counts: 最大下载数量
        root: 显式下载根目录覆盖（None=配置/默认）
        db: 显式元数据库覆盖（None=默认；覆盖时不写默认 following.json）

    Returns:
        bool: True=成功（含零新增）；False=失败（不更新 last_fetch_time）
    """
    # 应用运行时覆盖（影响 get_download_path/get_db_path 及其所有消费者）
    set_overrides(download_root=root, db_path=db)
    using_default_db = not get_active_overrides()["db_path"]

    try:
        kwargs = get_f2_kwargs(Path(get_download_path()))  # cookie 校验提前
    except ValueError as e:
        print(f"[错误] {e}")
        return False

    downloads_path = get_download_path()
    staging_root = make_staging_root(downloads_path)
    kwargs["path"] = str(staging_root)

    if max_counts:
        kwargs["max_counts"] = max_counts
    kwargs["url"] = url

    print(f"[下载] 开始下载...")
    print(f"[路径] {downloads_path} (staging: {staging_root.name})")

    # 创建元数据表
    create_video_metadata_table()

    try:
        # 初始化 Handler
        handler = DouyinHandler(kwargs)

        # 解析 sec_user_id
        from f2.apps.douyin.utils import SecUserIdFetcher
        sec_user_id = await SecUserIdFetcher.get_sec_user_id(url)

        if not sec_user_id:
            print("[错误] 无法解析用户 ID")
            return False

        print(f"[信息] sec_user_id: {sec_user_id[:30]}...")

        # 获取用户信息并保存
        async with AsyncUserDB(str(get_db_path())) as db_conn:
            user_path = await handler.get_or_add_user_data(kwargs, sec_user_id, db_conn)

        # 按当前作者精确取身份（历史 bug：取最后一行会在并发/多作者时串号）
        uid, nickname = get_author_by_sec_uid(sec_user_id)
        if not uid:
            print(f"[错误] 数据库中找不到 sec_user_id={sec_user_id[:20]}... 的作者记录")
            return False

        print(f"[博主] {nickname} (UID: {uid})")

        # 收集所有视频数据
        total_downloaded = 0
        total_stats_saved = 0
        cover_map = {}  # <naming>_cover → {aweme_id, kind, url}
        video_map = {}  # <naming> → {aweme_id}(DCM-004)

        print("[下载] 正在获取视频列表...")

        async for aweme_data_list in handler.fetch_user_post_videos(
            sec_user_id,
            max_counts=max_counts or float("inf")
        ):
            # 获取视频数据列表（用于下载）
            video_list = aweme_data_list._to_list()

            if video_list:
                # 从原始数据中保存统计数据（不增加额外请求）
                raw_data = aweme_data_list._to_raw()
                stats_saved = save_video_metadata_from_raw(raw_data, nickname)
                total_stats_saved += stats_saved

                # 封面命名→aweme_id 映射(Task-002,reorganize 绑定用)
                cover_map.update(build_cover_map(kwargs, video_list))
                # 视频命名→aweme_id 映射(DCM-004,_videos.json 索引用)
                video_map.update(build_video_map(kwargs, video_list))

                # 创建下载任务
                await handler.downloader.create_download_tasks(
                    kwargs, video_list, user_path
                )

                total_downloaded += len(video_list)
                print(f"[下载] 已处理 {total_downloaded} 个视频...")

        # 显示统计结果
        print(f"[统计] 保存了 {total_stats_saved} 条视频元数据（含点赞/评论等数据）")

        # 整理文件（只从本次 staging 发布）
        print("[整理] 重新组织文件...")
        post_path = staging_root / "douyin" / "post"
        folder_name = None
        if post_path.exists():
            for folder in sorted(post_path.iterdir()):
                if folder.is_dir():
                    folder_name = reorganize_files(folder.name, uid, staging_root, cover_map)
                    if folder_name:
                        update_video_index(downloads_path / folder_name, video_map)

        # 同步 following.json：仅默认库模式（跨库重建会污染默认清单）
        sync_ok = True
        if using_default_db:
            print("[同步] 更新 following.json...")
            sync_ok = run_sync(downloads_path)
            if not sync_ok:
                print("[失败] sync-following 返回非零，last_fetch_time 不更新")
        else:
            print("[跳过] 使用自定义 --db，不更新默认 following.json")

        # 更新 last_fetch_time：仅全部成功时
        if sync_ok and using_default_db:
            update_last_fetch_time(uid, nickname or (folder_name or ""))

        print(f"\n[完成] 共下载 {total_downloaded} 个视频")
        if folder_name:
            print(f"[位置] {downloads_path / folder_name}")

        return sync_ok

    except Exception as e:
        print(f"[失败] 下载中断: {e}")
        return False
    finally:
        # 只清理本次运行自己的 staging；已有视频/状态/共享 douyin/ 不受影响
        cleanup_staging(staging_root)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="抖音视频下载 v2（staging 隔离 + 精确作者身份）",
    )
    parser.add_argument("url", nargs="?", help="用户主页 URL")
    parser.add_argument("--max-counts", type=int, default=None, help="最大下载数量")
    parser.add_argument("--daemon", action="store_true", help="后台守护模式（日志落盘）")
    parser.add_argument("--task-id", default=None, help="守护模式任务 ID")
    parser.add_argument("--root", default=None,
                        help="显式下载根目录覆盖（默认: config.yaml download_path 或 ~/Downloads/抖音视频下载）")
    parser.add_argument("--db", default=None,
                        help="显式元数据库覆盖（默认: 技能目录 douyin_users.db；覆盖时不写默认 following.json）")
    return parser.parse_args(argv)


async def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if not args.url:
        print("用法: python scripts/download-v2.py <主页URL>")
        print("  示例: python scripts/download-v2.py https://www.douyin.com/user/xxx")
        print("  限制数量: python scripts/download-v2.py <URL> --max-counts=10")
        print("  自定义目录/库: python scripts/download-v2.py <URL> --root <目录> --db <db>")
        print("  后台运行: python scripts/download-v2.py <URL> --daemon")
        return 0

    url = args.url

    # 守护进程模式：立即输出进度信息后开始下载
    log_handle = None
    if args.daemon and args.task_id:
        downloads_path = get_download_path()
        log_file = downloads_path / "logs" / f"{args.task_id}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # 打开日志文件并保持打开状态
        log_handle = open(log_file, "w", encoding="utf-8")
        log_handle.write(f"[任务启动] {args.task_id}\n")
        log_handle.write(f"[URL] {url}\n")
        log_handle.write(f"[时间] {datetime.now().isoformat()}\n")
        log_handle.write("=" * 60 + "\n")
        log_handle.flush()

        # 重定向 stdout/stderr 到日志文件
        sys.stdout = log_handle
        sys.stderr = log_handle

        print(f"[守护模式] 任务 {args.task_id} 已启动")
        print(f"[日志] {log_file}")

    ok = await download_with_stats(url, args.max_counts, args.root, args.db)

    if log_handle:
        log_handle.close()

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
