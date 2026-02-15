#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频元数据提取脚本

从本地视频文件和 F2 数据库提取视频元数据并保存到 SQLite 数据库。

用法：
    python scripts/extract-metadata.py              # 扫描本地视频并提取元数据
    python scripts/extract-metadata.py --stats      # 显示统计摘要

⚠️ DEPRECATED: --fetch 选项已废弃
推荐使用 download-v2.py 重新下载视频，会自动保存统计数据：
    python scripts/download-v2.py <主页URL>

原因：
- --fetch 使用浏览器方式获取数据，可能触发反爬
- download-v2.py 在下载时自动保存统计数据，零额外请求
"""

import argparse
import asyncio
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# 强制使用脚本所在目录作为工作目录
SKILL_DIR = Path(__file__).parent.parent.resolve()
os.chdir(SKILL_DIR)

DB_PATH = SKILL_DIR / "douyin_users.db"
F2_VIDEO_DB_PATH = SKILL_DIR / "douyin_videos.db"
CONFIG_PATH = SKILL_DIR / "config" / "config.yaml"


def create_metadata_table():
    """创建视频元数据表"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_metadata (
            aweme_id TEXT PRIMARY KEY,
            uid TEXT NOT NULL,
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

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_video_digg ON video_metadata(digg_count DESC)
    """)

    conn.commit()
    conn.close()
    print("✅ 元数据表已创建/验证")


def get_video_stats_from_f2_db() -> List[Dict]:
    """从 F2 的视频数据库获取统计数据（如果存在）"""
    if not F2_VIDEO_DB_PATH.exists():
        return []

    conn = sqlite3.connect(str(F2_VIDEO_DB_PATH))
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                aweme_id, uid, desc, create_time, duration,
                digg_count, comment_count, collect_count, share_count
            FROM video_info
        """)
        rows = cursor.fetchall()
        conn.close()

        videos = []
        for row in rows:
            videos.append({
                "aweme_id": row[0],
                "uid": row[1] or "",
                "desc": row[2] or "",
                "create_time": int(row[3]) if row[3] else 0,
                "duration": int(row[4]) if row[4] else 0,
                "digg_count": int(row[5]) if row[5] else 0,
                "comment_count": int(row[6]) if row[6] else 0,
                "collect_count": int(row[7]) if row[7] else 0,
                "share_count": int(row[8]) if row[8] else 0,
            })
        return videos
    except sqlite3.OperationalError:
        conn.close()
        return []


def scan_local_videos() -> Dict[str, Dict]:
    """扫描本地视频文件，返回 aweme_id -> 文件信息的映射"""
    downloads_path = SKILL_DIR / "downloads"
    if not downloads_path.exists():
        return {}

    videos = {}
    for video_file in downloads_path.rglob("*.mp4"):
        # 文件名格式: {时间戳}_{描述}_{aweme_id}_video.mp4
        # 注意：描述中可能包含下划线
        stem = video_file.stem

        # 移除末尾的 _video
        stem = re.sub(r'_video$', '', stem)

        # 找所有纯数字段
        parts = stem.split("_")
        numeric_parts = []
        for part in parts:
            part = part.strip()
            if part.isdigit() and len(part) >= 15:
                numeric_parts.append(part)

        # 如果找到纯数字段，返回最长的那个
        if numeric_parts:
            aweme_id = max(numeric_parts, key=len)
        else:
            # 回退方案：使用正则表达式找最长的数字串
            matches = re.findall(r'\d{15,}', stem)
            if matches:
                aweme_id = max(matches, key=len)
            else:
                continue

        stat = video_file.stat()
        parent_dir = video_file.parent.name  # uid

        videos[aweme_id] = {
            "aweme_id": aweme_id,
            "uid": parent_dir,
            "local_filename": video_file.name,
            "file_size": stat.st_size,
        }

    return videos


def save_metadata(videos: List[Dict]):
    """保存元数据到数据库"""
    if not videos:
        print("⚠️ 没有视频元数据需要保存")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    fetch_time = int(datetime.now().timestamp())

    for video in videos:
        cursor.execute("""
            INSERT OR REPLACE INTO video_metadata
            (aweme_id, uid, desc, create_time, duration,
             digg_count, comment_count, collect_count, share_count, play_count,
             local_filename, file_size, fetch_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            video.get("aweme_id"),
            video.get("uid", ""),
            video.get("desc", ""),
            video.get("create_time", 0),
            video.get("duration", 0),
            video.get("digg_count", 0),
            video.get("comment_count", 0),
            video.get("collect_count", 0),
            video.get("share_count", 0),
            video.get("play_count", 0),
            video.get("local_filename", ""),
            video.get("file_size", 0),
            fetch_time
        ))

    conn.commit()
    conn.close()
    print(f"✅ 已保存 {len(videos)} 条视频元数据")


def get_cookie_from_config() -> str:
    """从配置文件读取 Cookie"""
    import yaml

    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config.get("douyin", {}).get("cookie", "") or config.get("cookie", "")
    return ""


def get_sec_user_id_from_db(uid: str) -> str:
    """从数据库获取 sec_user_id"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT sec_user_id FROM user_info_web WHERE uid = ?", (uid,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else ""
    except Exception:
        return ""


async def fetch_video_stats_from_user_page(sec_user_id: str, delay: float = 2.0) -> Dict[str, Dict]:
    """
    通过访问用户主页获取视频统计数据

    从 API 响应中捕获 aweme_list 数据

    Args:
        sec_user_id: 用户的 sec_user_id
        delay: 请求延迟

    Returns:
        aweme_id -> 统计数据的字典
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ 需要安装 playwright: pip install playwright && playwright install chromium")
        return {}

    stats_data = {}
    all_videos = []

    print("  启动浏览器...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )

        # 加载 Cookie
        cookie_str = get_cookie_from_config()
        if cookie_str:
            cookies = []
            for item in cookie_str.split(';'):
                item = item.strip()
                if '=' in item:
                    name, value = item.split('=', 1)
                    cookies.append({
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": ".douyin.com",
                        "path": "/"
                    })
            if cookies:
                await context.add_cookies(cookies)
                print(f"  已加载 {len(cookies)} 个 Cookie")

        # 监听 API 响应
        async def handle_response(response):
            if 'aweme/post' in response.url:
                try:
                    data = await response.json()
                    aweme_list = data.get('aweme_list', [])
                    for v in aweme_list:
                        aweme_id = v.get('aweme_id', '')
                        stats = v.get('statistics', {})
                        if aweme_id:
                            all_videos.append({
                                "aweme_id": aweme_id,
                                "uid": v.get('author', {}).get('uid', ''),
                                "desc": v.get('desc', ''),
                                "create_time": v.get('create_time', 0),
                                "duration": v.get('duration', 0),
                                "digg_count": stats.get('digg_count', 0),
                                "comment_count": stats.get('comment_count', 0),
                                "collect_count": stats.get('collect_count', 0),
                                "share_count": stats.get('share_count', 0),
                                "play_count": stats.get('play_count', 0),
                            })
                except Exception:
                    pass

        page = await context.new_page()
        page.on('response', handle_response)

        url = f"https://www.douyin.com/user/{sec_user_id}"
        print(f"  访问用户主页...")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            print("  页面加载完成，等待 API 响应...")

            # 滚动页面以加载更多视频
            for i in range(5):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
                print(f"  滚动加载中... ({i+1}/5)")

            # 再等待一下确保所有请求完成
            await page.wait_for_timeout(3000)

        except Exception as e:
            print(f"  访问页面时出错: {e}")

        await browser.close()

    # 整理数据
    for v in all_videos:
        stats_data[v['aweme_id']] = v

    print(f"  ✅ 获取到 {len(stats_data)} 个视频的统计数据")
    return stats_data


def get_stats_summary() -> Dict:
    """获取统计摘要"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # 视频总数
    cursor.execute("SELECT COUNT(*) FROM video_metadata")
    total_videos = cursor.fetchone()[0]

    # 有统计数据的视频数
    cursor.execute("SELECT COUNT(*) FROM video_metadata WHERE digg_count > 0")
    videos_with_stats = cursor.fetchone()[0]

    # 总点赞数
    cursor.execute("SELECT SUM(digg_count) FROM video_metadata")
    total_diggs = cursor.fetchone()[0] or 0

    # 用户统计
    cursor.execute("""
        SELECT uid, COUNT(*) as count, SUM(digg_count) as total_diggs
        FROM video_metadata
        GROUP BY uid
        ORDER BY total_diggs DESC
    """)
    user_stats = cursor.fetchall()

    conn.close()

    return {
        "total_videos": total_videos,
        "videos_with_stats": videos_with_stats,
        "total_diggs": total_diggs,
        "user_stats": user_stats
    }


def main():
    parser = argparse.ArgumentParser(description="视频元数据提取工具")
    parser.add_argument("--fetch", action="store_true", help="从网页获取统计数据（需要 sec_user_id）")
    parser.add_argument("--stats", action="store_true", help="显示统计摘要")
    parser.add_argument("--uid", type=str, help="指定用户 UID")
    args = parser.parse_args()

    print("=" * 50)
    print("视频元数据提取工具")
    print("=" * 50)

    # 创建表
    create_metadata_table()

    if args.stats:
        # 显示统计
        stats = get_stats_summary()
        print(f"\n📊 统计摘要:")
        print(f"   总视频数: {stats['total_videos']}")
        print(f"   有统计数据的视频: {stats['videos_with_stats']}")
        print(f"   总点赞数: {stats['total_diggs']:,}")
        print(f"\n   用户统计:")
        for uid, count, diggs in stats['user_stats'][:10]:
            print(f"     {uid}: {count} 视频, {diggs:,} 点赞")
        return

    # 扫描本地视频
    print("\n📁 扫描本地视频文件...")
    local_videos = scan_local_videos()
    print(f"   找到 {len(local_videos)} 个本地视频")

    if args.fetch:
        # 弃用警告
        print("\n" + "=" * 60)
        print("⚠️  警告: --fetch 选项已废弃")
        print("   推荐使用 download-v2.py 重新下载视频，会自动保存统计数据")
        print("   用法: python scripts/download-v2.py <主页URL>")
        print("=" * 60)

        # 使用 Playwright 从用户主页获取统计数据
        print("\n🌐 从用户主页获取统计数据...")

        # 获取用户的 sec_user_id
        if args.uid:
            uid = args.uid
        else:
            # 从本地视频推断 uid
            uids = set(v['uid'] for v in local_videos.values())
            if len(uids) == 1:
                uid = list(uids)[0]
            else:
                print(f"❌ 发现多个用户: {uids}，请使用 --uid 指定")
                return

        sec_user_id = get_sec_user_id_from_db(uid)
        if not sec_user_id:
            print(f"❌ 未找到用户 {uid} 的 sec_user_id")
            return

        print(f"   用户 UID: {uid}")
        print(f"   sec_user_id: {sec_user_id[:20]}...\n")

        stats_data = asyncio.run(fetch_video_stats_from_user_page(sec_user_id))

        if stats_data:
            # 合并本地信息和 API 数据
            merged = []
            for aweme_id, local_info in local_videos.items():
                video = local_info.copy()
                if aweme_id in stats_data:
                    video.update(stats_data[aweme_id])
                merged.append(video)

            save_metadata(merged)
    else:
        # 检查 F2 数据库
        print("\n📊 检查 F2 视频数据库...")
        f2_videos = get_video_stats_from_f2_db()
        print(f"   找到 {len(f2_videos)} 条 F2 数据库记录")

        # 创建 F2 数据的索引
        f2_index = {v["aweme_id"]: v for v in f2_videos}

        # 合并数据
        merged = []
        for aweme_id, local_info in local_videos.items():
            video = local_info.copy()
            if aweme_id in f2_index:
                f2_data = f2_index[aweme_id]
                video.update({
                    "desc": f2_data.get("desc", ""),
                    "create_time": f2_data.get("create_time", 0),
                    "duration": f2_data.get("duration", 0),
                    "digg_count": f2_data.get("digg_count", 0),
                    "comment_count": f2_data.get("comment_count", 0),
                    "collect_count": f2_data.get("collect_count", 0),
                    "share_count": f2_data.get("share_count", 0),
                })
            merged.append(video)

        save_metadata(merged)

    # 显示结果
    stats = get_stats_summary()
    print(f"\n📊 当前状态:")
    print(f"   总视频数: {stats['total_videos']}")
    print(f"   有统计数据的视频: {stats['videos_with_stats']}")


if __name__ == "__main__":
    main()
