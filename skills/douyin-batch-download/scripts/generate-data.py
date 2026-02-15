#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据生成脚本 - 扫描 downloads 目录和 following.json，生成前端可用数据
包含视频元数据（点赞、评论、收藏、分享数）
"""
import json
import re
import sqlite3
import sys
import os
from pathlib import Path
from datetime import datetime

# 强制使用脚本所在目录作为工作目录
SKILL_DIR = Path(__file__).parent.parent.resolve()
os.chdir(SKILL_DIR)

DOWNLOADS_PATH = SKILL_DIR / "downloads"
FOLLOWING_PATH = SKILL_DIR / "config" / "following.json"
DB_PATH = SKILL_DIR / "douyin_users.db"
OUTPUT_PATH = SKILL_DIR / "downloads" / "data.js"


def extract_aweme_id(filename: str) -> str:
    """从文件名提取 aweme_id

    文件名格式: {时间戳}_{描述}_{aweme_id}_video.mp4
    例如: 2023-09-11 20-55-58_描述_7277551294787620150_video.mp4

    注意：描述中可能包含下划线，所以需要找所有纯数字段，然后选择合适的
    aweme_id 通常是 18-19 位数字，以 7 开头
    """
    stem = Path(filename).stem

    # 移除末尾的 _video
    stem = re.sub(r'_video$', '', stem)

    # 找所有纯数字段
    parts = stem.split("_")
    numeric_parts = []

    for part in parts:
        part = part.strip()
        # 检查是否是纯数字且长度 >= 15 (aweme_id 通常是 18-19 位)
        if part.isdigit() and len(part) >= 15:
            numeric_parts.append(part)

    # 如果找到纯数字段，返回最长的那个（应该是 aweme_id）
    if numeric_parts:
        return max(numeric_parts, key=len)

    # 回退方案：使用正则表达式找最长的数字串（15位以上）
    matches = re.findall(r'\d{15,}', stem)
    if matches:
        return max(matches, key=len)

    return stem  # 最后返回文件名


def format_size(bytes_size):
    """格式化文件大小"""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    if bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    if bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / 1024 / 1024:.1f} MB"
    return f"{bytes_size / 1024 / 1024 / 1024:.2f} GB"


def format_number(num):
    """格式化数字（大数用万/亿表示）"""
    if num >= 100000000:  # 1亿
        return f"{num / 100000000:.1f}亿"
    if num >= 10000:  # 1万
        return f"{num / 10000:.1f}万"
    return str(num)


def get_video_metadata():
    """从数据库获取视频元数据"""
    if not DB_PATH.exists():
        return {}

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        # 检查 video_metadata 表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='video_metadata'
        """)
        if not cursor.fetchone():
            conn.close()
            return {}

        cursor.execute("""
            SELECT
                aweme_id, uid, desc, create_time, duration,
                digg_count, comment_count, collect_count, share_count, play_count,
                local_filename, file_size, fetch_time
            FROM video_metadata
        """)
        rows = cursor.fetchall()
        conn.close()

        # 以 aweme_id 为键建立索引
        metadata = {}
        for row in rows:
            aweme_id = row[0]
            metadata[aweme_id] = {
                "uid": row[1] or "",
                "desc": row[2] or "",
                "create_time": row[3] or 0,
                "duration": row[4] or 0,
                "digg_count": row[5] or 0,
                "comment_count": row[6] or 0,
                "collect_count": row[7] or 0,
                "share_count": row[8] or 0,
                "play_count": row[9] or 0,
                "local_filename": row[10] or "",
                "file_size": row[11] or 0,
                "fetch_time": row[12] or 0,
            }
        return metadata
    except sqlite3.OperationalError:
        conn.close()
        return {}


def scan_videos_from_root(metadata: dict):
    """扫描 downloads 目录下所有子目录中的视频文件"""
    videos = []
    # 扫描所有子目录中的 mp4 文件
    for video_file in sorted(DOWNLOADS_PATH.rglob("*.mp4")):
        stat = video_file.stat()
        # 获取视频文件的直接父目录名作为 folder (即 uid)
        parent_dir = video_file.parent.name

        # 提取 aweme_id
        aweme_id = extract_aweme_id(video_file.name)

        video_data = {
            "name": video_file.stem,
            "aweme_id": aweme_id,
            "size": stat.st_size,
            "folder": parent_dir,
        }

        # 合并元数据
        if aweme_id in metadata:
            meta = metadata[aweme_id]
            video_data["stats"] = {
                "digg_count": meta["digg_count"],
                "comment_count": meta["comment_count"],
                "collect_count": meta["collect_count"],
                "share_count": meta["share_count"],
                "play_count": meta["play_count"],
            }
            video_data["desc"] = meta["desc"]
            video_data["create_time"] = meta["create_time"]
            video_data["duration"] = meta["duration"]

        videos.append(video_data)
    return videos


def scan_user_videos(user_uid, metadata: dict):
    """扫描指定用户目录的视频文件（子目录）"""
    user_dir = DOWNLOADS_PATH / user_uid

    if not user_dir.exists():
        return []

    videos = []
    for video_file in sorted(user_dir.glob("*.mp4")):
        stat = video_file.stat()
        aweme_id = video_file.stem.split("_")[0]

        video_data = {
            "name": video_file.stem,
            "aweme_id": aweme_id,
            "size": stat.st_size,
            "folder": user_uid,
        }

        if aweme_id in metadata:
            meta = metadata[aweme_id]
            video_data["stats"] = {
                "digg_count": meta["digg_count"],
                "comment_count": meta["comment_count"],
                "collect_count": meta["collect_count"],
                "share_count": meta["share_count"],
                "play_count": meta["play_count"],
            }
            video_data["desc"] = meta["desc"]
            video_data["create_time"] = meta["create_time"]
            video_data["duration"] = meta["duration"]

        videos.append(video_data)
    return videos


def calculate_user_stats(videos: list) -> dict:
    """计算用户统计信息"""
    total_diggs = sum(v.get("stats", {}).get("digg_count", 0) for v in videos)
    total_comments = sum(v.get("stats", {}).get("comment_count", 0) for v in videos)
    total_collects = sum(v.get("stats", {}).get("collect_count", 0) for v in videos)
    total_shares = sum(v.get("stats", {}).get("share_count", 0) for v in videos)

    # 找出热门视频（点赞最多的前3个）
    sorted_videos = sorted(
        videos,
        key=lambda x: x.get("stats", {}).get("digg_count", 0),
        reverse=True
    )
    top_videos = sorted_videos[:3]

    return {
        "total_diggs": total_diggs,
        "total_comments": total_comments,
        "total_collects": total_collects,
        "total_shares": total_shares,
        "top_videos": [
            {
                "name": v["name"],
                "digg_count": v.get("stats", {}).get("digg_count", 0)
            } for v in top_videos
        ]
    }


def main():
    print("开始生成数据文件...")

    # 1. 读取 following.json
    if not FOLLOWING_PATH.exists():
        print("错误: following.json 不存在")
        return

    with open(FOLLOWING_PATH, "r", encoding="utf-8") as f:
        following = json.load(f)

    # 2. 获取视频元数据
    metadata = get_video_metadata()
    print(f"从数据库读取 {len(metadata)} 条视频元数据")

    # 3. 初始化数据结构
    data = {
        "generated_at": datetime.now().isoformat(),
        "users": [],
        "videos": []
    }

    # 4. 先扫描根目录下的所有视频
    all_videos = scan_videos_from_root(metadata)

    # 5. 构建用户数据
    # 支持两种 following.json 格式：
    #   - 旧格式：单个用户对象，uid 作为键
    #   - 新格式：users 数组

    if following.get("users") and isinstance(following["users"], list):
        # 新格式：users 是数组
        for user in following["users"]:
            uid = user.get("uid")
            if not uid:
                continue

            # 从根目录扫描结果中筛选该用户的视频
            user_videos = [v for v in all_videos if v["folder"] == uid]
            user_stats = calculate_user_stats(user_videos)

            data["users"].append({
                "uid": uid,
                "name": user.get("name", ""),
                "avatar_url": user.get("avatar_url", ""),
                "video_count": len(user_videos),
                "stats": user_stats
            })
    else:
        # 旧格式：单个用户对象，uid 作为键
        for uid, user_info in following.items():
            # 跳过非用户字段（如"说明"）
            if isinstance(user_info, dict) and user_info.get("uid"):
                # 从根目录扫描结果中筛选该用户的视频
                user_videos = [v for v in all_videos if v["folder"] == uid]

                # 同时从用户目录扫描（如果存在）
                subdir_videos = scan_user_videos(uid, metadata)
                user_videos.extend(subdir_videos)

                user_stats = calculate_user_stats(user_videos)

                data["users"].append({
                    "uid": uid,
                    "name": user_info.get("name", ""),
                    "avatar_url": user_info.get("avatar_url", ""),
                    "video_count": len(user_videos),
                    "stats": user_stats
                })

    data["videos"] = all_videos

    # 6. 计算总大小和总统计
    total_size = sum(v["size"] for v in data["videos"])
    videos_with_stats = sum(1 for v in data["videos"] if "stats" in v)
    total_diggs = sum(v.get("stats", {}).get("digg_count", 0) for v in data["videos"])

    # 7. 写入 data.js
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("// 自动生成 - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
        f.write(f"// 视频总数: {len(data['videos'])}, 有统计: {videos_with_stats}, 总点赞: {format_number(total_diggs)}\n")
        f.write("window.APP_DATA = ")
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write(";\n")

    print(f"✅ 数据已生成: {OUTPUT_PATH}")
    print(f"   博主: {len(data['users'])}")
    print(f"   视频: {len(data['videos'])}")
    print(f"   有统计数据的视频: {videos_with_stats}")
    print(f"   总大小: {format_size(total_size)}")
    print(f"   总点赞: {format_number(total_diggs)}")
    print("\n提示: 直接用浏览器打开 index.html 即可")
    print("  或双击 index.html 文件")


if __name__ == "__main__":
    main()
