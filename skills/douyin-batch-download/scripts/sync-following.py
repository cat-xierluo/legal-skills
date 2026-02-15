#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步 following.json
从 douyin_users.db (F2 缓存) 读取用户信息，更新 following.json

数据源：
- douyin_users.db: F2 缓存的主数据源（用户信息）
- following.json: 保留 last_fetch_time 等自定义字段

用法：python scripts/sync-following.py
"""

import sqlite3
from pathlib import Path
from datetime import datetime
import os
import sys

# 强制使用脚本所在目录作为工作目录
SKILL_DIR = Path(__file__).parent.parent.resolve()
# 切换到脚本目录（确保相对路径正确）
os.chdir(SKILL_DIR)

from following import (
    load_following,
    save_following,
    add_user,
    list_users,
    get_user,
    FOLLOWING_PATH,
)

DB_PATH = SKILL_DIR / "douyin_users.db"
HTML_PATH = SKILL_DIR / "downloads" / "index.html"
DOWNLOADS_PATH = SKILL_DIR / "downloads"


def get_user_info_from_db(uid):
    """从 F2 数据库获取用户信息"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT uid, sec_user_id, nickname, avatar_url, signature, follower_count, following_count
            FROM user_info_web WHERE uid = ?
        """, (uid,))
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception:
        return None


def get_video_count(user_path):
    """统计用户视频数量"""
    return sum(1 for _ in user_path.glob("*.mp4")) if user_path.exists() else 0


def generate_html(users):
    """生成 index.html"""
    if not HTML_PATH.exists():
        print(f"  [跳过] 未找到 HTML 模板")
        return

    import json

    html = HTML_PATH.read_text(encoding="utf-8")
    downloads_dir = str(DOWNLOADS_PATH.resolve())

    # 转换为 {users: [...]} 格式
    data = {"users": users}
    json_str = json.dumps(data, ensure_ascii=False)

    html = html.replace("FILE_PLACEHOLDER", downloads_dir)
    html = html.replace("PLACEHOLDER_JSON", json_str)

    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"  [更新] index.html")


def main():
    print("同步 following.json")
    print("=" * 50)

    if not DOWNLOADS_PATH.exists():
        print("未找到 downloads 目录")
        return

    # 加载旧数据（保留 last_fetch_time）
    old_data = load_following()
    old_users = {u.get("uid"): u for u in old_data.get("users", [])}

    new_users = []

    # 遍历 downloads 目录找用户
    for folder in DOWNLOADS_PATH.iterdir():
        if not folder.is_dir():
            continue

        uid = folder.name
        if not uid.isdigit():
            continue

        # 从 F2 数据库获取用户信息
        user_data = get_user_info_from_db(uid)
        if not user_data:
            continue

        video_count = get_video_count(folder)

        # 保留旧数据中的 last_fetch_time
        old_user = old_users.get(uid, {})
        last_fetch = old_user.get("last_fetch_time")

        user_info = {
            "uid": uid,
            "sec_user_id": user_data[1],
            "name": user_data[2],
            "nickname": user_data[2],
            "avatar_url": user_data[3] or "",
            "signature": user_data[4] or "",
            "follower_count": user_data[5] or 0,
            "following_count": user_data[6] or 0,
            "video_count": video_count,
            "last_updated": datetime.now().isoformat(),
            "last_fetch_time": last_fetch,  # 保留上次抓取时间
        }
        new_users.append(user_info)
        print(f"  [OK] {user_data[2]} ({video_count} 视频)")

    # 同时保留 downloads 目录中没有但 following.json 中有的用户
    for uid, old_user in old_users.items():
        if not any(u.get("uid") == uid for u in new_users):
            # 检查是否在数据库中
            user_data = get_user_info_from_db(uid)
            if user_data:
                user_info = {
                    "uid": uid,
                    "sec_user_id": user_data[1],
                    "name": user_data[2],
                    "nickname": user_data[2],
                    "avatar_url": user_data[3] or "",
                    "signature": user_data[4] or "",
                    "follower_count": user_data[5] or 0,
                    "following_count": user_data[6] or 0,
                    "video_count": 0,
                    "last_updated": datetime.now().isoformat(),
                    "last_fetch_time": old_user.get("last_fetch_time"),
                }
                new_users.append(user_info)
                print(f"  [保留] {user_data[2]} (无本地视频)")

    if new_users:
        # 生成 HTML
        generate_html(new_users)

        # 保存 following.json
        save_following({"users": new_users})

    print(f"\n保存到: {FOLLOWING_PATH}")
    print(f"共 {len(new_users)} 个博主")


if __name__ == "__main__":
    main()
