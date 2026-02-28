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

优势：
- 不增加额外 API 请求（数据在下载时已获取）
- 自动保存视频统计数据到数据库
- 使用博主昵称作为文件夹名（更易识别）
"""

import shutil
import sqlite3
import asyncio
import sys
import yaml
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List

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
)

# 导入 F2 模块
from f2.apps.douyin.handler import DouyinHandler
from f2.apps.douyin.db import AsyncUserDB, AsyncVideoDB
from f2.utils.conf_manager import ConfigManager
import f2


def merge_config(main_conf: dict, custom_conf: dict) -> dict:
    """合并配置"""
    result = (main_conf or {}).copy()
    for key, value in (custom_conf or {}).items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key].update(value)
        else:
            result[key] = value
    return result


def get_f2_kwargs() -> dict:
    """获取 F2 所需的配置参数"""
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

    # 设置路径 - 使用统一配置模块
    kwargs["path"] = str(get_download_path())

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
    """从原始 API 响应中提取并保存视频统计数据"""
    aweme_list = raw_data.get("aweme_list", [])
    if not aweme_list:
        return 0

    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    fetch_time = int(datetime.now().timestamp())
    saved_count = 0

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

    conn.commit()
    conn.close()
    return saved_count


def reorganize_files(nickname: str, uid: str) -> str:
    """整理文件到下载目录/{博主昵称}/"""
    downloads_path = get_download_path()
    old_path = downloads_path / "douyin" / "post" / nickname

    if not old_path.exists():
        return None

    # 使用博主昵称作为文件夹名
    folder_name = get_user_folder_name(nickname, uid)
    new_path = downloads_path / folder_name
    new_path.mkdir(parents=True, exist_ok=True)

    # 移动文件
    moved_count = 0
    for pattern in ["*.mp4", "*.jpg", "*.webp"]:
        for f in old_path.glob(pattern):
            dest = new_path / f.name
            if not dest.exists():
                shutil.move(str(f), str(dest))
                moved_count += 1

    # 清理旧文件夹
    if old_path.exists():
        try:
            shutil.rmtree(old_path)
        except:
            pass

    if moved_count > 0:
        print(f"  [移动] {nickname} -> {folder_name} ({moved_count} 文件)")

    return folder_name


def update_last_fetch_time(uid: str, nickname: str = ""):
    """更新 following.json 中的 last_fetch_time"""
    try:
        from following import update_fetch_time
        update_fetch_time(uid, nickname)
        print(f"  [更新] last_fetch_time for {nickname or uid}")
    except ImportError:
        pass


def run_sync():
    """运行 sync-following.py"""
    import subprocess
    subprocess.run([sys.executable, str(SKILL_DIR / "scripts" / "sync-following.py")])


async def download_with_stats(url: str, max_counts: int = None):
    """
    使用 F2 API 下载视频并保存统计数据

    Args:
        url: 用户主页 URL
        max_counts: 最大下载数量
    """
    # 获取配置
    kwargs = get_f2_kwargs()
    kwargs["url"] = url

    if max_counts:
        kwargs["max_counts"] = max_counts

    downloads_path = get_download_path()

    # 清理临时目录
    f2_temp_path = downloads_path / "douyin"
    if f2_temp_path.exists():
        shutil.rmtree(f2_temp_path)
        print("[清理] F2 临时目录")

    print(f"[下载] 开始下载...")
    print(f"[路径] {downloads_path}")

    # 创建元数据表
    create_video_metadata_table()

    # 初始化 Handler
    handler = DouyinHandler(kwargs)

    # 解析 sec_user_id
    from f2.apps.douyin.utils import SecUserIdFetcher
    sec_user_id = await SecUserIdFetcher.get_sec_user_id(url)

    if not sec_user_id:
        print("[错误] 无法解析用户 ID")
        return

    print(f"[信息] sec_user_id: {sec_user_id[:30]}...")

    # 获取用户信息并保存
    async with AsyncUserDB(str(get_db_path())) as db:
        user_path = await handler.get_or_add_user_data(kwargs, sec_user_id, db)

    # 从数据库获取用户信息（昵称）
    conn = sqlite3.connect(str(get_db_path()))
    cursor = conn.cursor()
    cursor.execute("SELECT uid, nickname FROM user_info_web ORDER BY ROWID DESC LIMIT 1")
    user_info = cursor.fetchone()
    conn.close()

    uid = user_info[0] if user_info else ""
    nickname = user_info[1] if user_info else ""

    if nickname:
        print(f"[博主] {nickname} (UID: {uid})")

    # 收集所有视频数据
    all_videos = []
    total_downloaded = 0
    total_stats_saved = 0

    print("[下载] 正在获取视频列表...")

    async for aweme_data_list in handler.fetch_user_post_videos(
        sec_user_id,
        max_counts=max_counts or float("inf")
    ):
        # 获取视频数据列表（用于下载）
        video_list = aweme_data_list._to_list()

        if video_list:
            all_videos.extend(video_list)

            # 从原始数据中保存统计数据（不增加额外请求）
            raw_data = aweme_data_list._to_raw()
            stats_saved = save_video_metadata_from_raw(raw_data, nickname)
            total_stats_saved += stats_saved

            # 创建下载任务
            await handler.downloader.create_download_tasks(
                kwargs, video_list, user_path
            )

            total_downloaded += len(video_list)
            print(f"[下载] 已处理 {total_downloaded} 个视频...")

    # 显示统计结果
    print(f"[统计] 保存了 {total_stats_saved} 条视频元数据（含点赞/评论等数据）")

    # 整理文件
    print("[整理] 重新组织文件...")
    post_path = downloads_path / "douyin" / "post"
    folder_name = None
    if post_path.exists():
        for folder in post_path.iterdir():
            if folder.is_dir():
                folder_name = reorganize_files(folder.name, uid)

    # 更新 last_fetch_time
    if folder_name:
        update_last_fetch_time(uid, nickname or folder_name)

    # 同步 following.json
    print("[同步] 更新 following.json...")
    run_sync()

    print(f"\n[完成] 共下载 {total_downloaded} 个视频")
    if folder_name:
        print(f"[位置] {downloads_path / folder_name}")


async def main():
    # 检查是否需要作为守护进程运行（由 batch-download.py 调用）
    daemon_mode = "--daemon" in sys.argv
    if daemon_mode:
        sys.argv.remove("--daemon")

    if len(sys.argv) < 2:
        print("用法: python scripts/download-v2.py <主页URL>")
        print("  示例: python scripts/download-v2.py https://www.douyin.com/user/xxx")
        print("  限制数量: python scripts/download-v2.py <URL> --max-counts=10")
        print("  后台运行: python scripts/download-v2.py <URL> --daemon")
        return

    url = sys.argv[1]

    # 解析参数
    max_counts = None
    task_id = None  # 任务 ID（守护模式使用）

    for arg in sys.argv[2:]:
        if arg.startswith("--max-counts="):
            max_counts = int(arg.split("=")[1])
        elif arg.startswith("--task-id="):
            task_id = arg.split("=")[1]

    # 守护进程模式：立即输出进度信息后开始下载
    if daemon_mode and task_id:
        downloads_path = get_download_path()
        log_file = downloads_path / "logs" / f"{task_id}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # 打开日志文件并保持打开状态
        log_handle = open(log_file, "w", encoding="utf-8")
        log_handle.write(f"[任务启动] {task_id}\n")
        log_handle.write(f"[URL] {url}\n")
        log_handle.write(f"[时间] {datetime.now().isoformat()}\n")
        log_handle.write("=" * 60 + "\n")
        log_handle.flush()

        # 重定向 stdout/stderr 到日志文件
        sys.stdout = log_handle
        sys.stderr = log_handle

        print(f"[守护模式] 任务 {task_id} 已启动")
        print(f"[日志] {log_file}")

    await download_with_stats(url, max_counts)

    # 守护进程模式：关闭日志文件
    if daemon_mode and task_id:
        log_handle.close()


if __name__ == "__main__":
    asyncio.run(main())
