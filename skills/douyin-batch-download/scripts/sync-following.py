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
# 视频实际位置(douyin-batch-download 官方目录约定:博主子目录用昵称,平铺 mp4)
VIDEO_ROOT = Path.home() / "Downloads" / "抖音视频下载"


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
    downloads_dir = str(VIDEO_ROOT.resolve())

    # 转换为 {users: [...]} 格式
    data = {"users": users}
    json_str = json.dumps(data, ensure_ascii=False)

    html = html.replace("FILE_PLACEHOLDER", downloads_dir)
    html = html.replace("PLACEHOLDER_JSON", json_str)

    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"  [更新] index.html")


def main():
    print("同步 following.json (从 db 全量重建,db 为真值)")
    print("=" * 50)

    if not DB_PATH.exists():
        print(f"未找到 db: {DB_PATH}")
        return

    # 加载旧数据(按 sec_user_id 保留 last_fetch_time 等扩展字段)
    old_data = load_following()
    old_users = {u.get("sec_user_id"): u for u in old_data.get("users", [])}

    # 从 db 全量读博主(db 是真值,含 peer_type)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT uid, sec_user_id, nickname, avatar_url, signature,
               follower_count, following_count, peer_type
        FROM user_info_web
    """).fetchall()
    conn.close()

    new_users = []
    for r in rows:
        sec = r["sec_user_id"]
        old_user = old_users.get(sec, {})
        # video_count 从视频实际位置统计(~/Downloads/抖音视频下载/<昵称>/)
        video_count = 0
        user_dir = VIDEO_ROOT / r["nickname"]
        if user_dir.exists():
            try:
                video_count = sum(1 for _ in user_dir.glob("*.mp4"))
            except Exception:
                video_count = 0
        new_users.append({
            "uid": r["uid"],
            "sec_user_id": sec,
            "name": r["nickname"],
            "nickname": r["nickname"],
            "avatar_url": r["avatar_url"] or "",
            "signature": r["signature"] or "",
            "follower_count": r["follower_count"] or 0,
            "following_count": r["following_count"] or 0,
            "video_count": video_count,
            "last_updated": datetime.now().isoformat(),
            "last_fetch_time": old_user.get("last_fetch_time"),
            "peer_type": r["peer_type"] or "followed",
        })
        print(f"  [OK] {r['nickname']} ({video_count} 视频, {r['peer_type']})")

    if new_users:
        # 生成 HTML
        generate_html(new_users)
        # 保存 following.json
        save_following({"users": new_users})

    print(f"\n保存到: {FOLLOWING_PATH}")
    print(f"共 {len(new_users)} 个博主")


if __name__ == "__main__":
    main()
