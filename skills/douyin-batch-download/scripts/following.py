#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
following.json 统一读写模块

数据格式: {users: [{uid, nickname, ...}, ...]}
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

# 获取 skill 根目录（scripts/ 的上一级）
SKILL_DIR = Path(__file__).parent.parent.resolve()
FOLLOWING_PATH = SKILL_DIR / "config" / "following.json"
DB_PATH = SKILL_DIR / "douyin_users.db"


def load_following() -> dict:
    """加载 following.json，返回 {users: [...]} 格式"""
    if FOLLOWING_PATH.exists():
        try:
            with open(FOLLOWING_PATH, encoding="utf-8") as f:
                data = json.load(f)
                # 确保格式正确
                if "users" not in data:
                    data = {"users": []}
                return data
        except Exception:
            return {"users": []}
    return {"users": []}


def save_following(data: dict):
    """保存 following.json"""
    FOLLOWING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FOLLOWING_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _find_user_index(data: dict, uid: str) -> int:
    """查找用户在列表中的索引，找不到返回 -1"""
    for i, user in enumerate(data.get("users", [])):
        if user.get("uid") == uid:
            return i
    return -1


def get_user(uid: str) -> Optional[dict]:
    """获取单个用户信息，不存在返回 None"""
    data = load_following()
    for user in data.get("users", []):
        if user.get("uid") == uid:
            return user
    return None


def list_users() -> list:
    """获取用户列表"""
    data = load_following()
    return data.get("users", [])


def add_user(uid: str, info: dict, merge: bool = True) -> bool:
    """
    添加或更新用户

    Args:
        uid: 用户 ID
        info: 用户信息字典
        merge: 是否合并已有信息（True=保留未提供的字段）

    Returns:
        True=新增, False=更新已有用户
    """
    data = load_following()
    index = _find_user_index(data, uid)

    # 确保 info 包含 uid
    info["uid"] = uid

    if index >= 0:
        # 更新已有用户
        if merge:
            # 合并：保留已有值，更新新提供的值
            existing = data["users"][index]
            for key, value in info.items():
                if value is not None and value != "":
                    existing[key] = value
            info = existing
        data["users"][index] = info
        save_following(data)
        return False
    else:
        # 新增用户
        if "last_updated" not in info:
            info["last_updated"] = datetime.now().isoformat()
        if "last_fetch_time" not in info:
            info["last_fetch_time"] = None
        data["users"].append(info)
        save_following(data)
        return True


def remove_user(uid: str) -> bool:
    """删除用户，返回是否成功"""
    data = load_following()
    index = _find_user_index(data, uid)

    if index >= 0:
        del data["users"][index]
        save_following(data)
        return True
    return False


def update_fetch_time(uid: str):
    """更新用户的 last_fetch_time"""
    data = load_following()
    index = _find_user_index(data, uid)

    if index >= 0:
        data["users"][index]["last_fetch_time"] = datetime.now().isoformat()
        save_following(data)


def create_empty_user(uid: str, sec_user_id: str = "") -> dict:
    """创建空用户模板"""
    return {
        "uid": uid,
        "sec_user_id": sec_user_id,
        "name": "",
        "nickname": "",
        "avatar_url": "",
        "signature": "",
        "follower_count": 0,
        "following_count": 0,
        "video_count": 0,
        "last_updated": datetime.now().isoformat(),
        "last_fetch_time": None,
    }


def update_user_info_from_db(uid: str, last_fetch_time: str = None) -> bool:
    """
    从 F2 数据库读取用户信息并更新到 following.json

    Args:
        uid: 用户 ID（可以是数字 UID 或 sec_user_id）
        last_fetch_time: 保留的 last_fetch_time

    Returns:
        是否成功更新
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # 先尝试用 uid 查找
        cursor.execute("""
            SELECT uid, sec_user_id, nickname, avatar_url, signature,
                   follower_count, following_count, aweme_count
            FROM user_info_web WHERE uid = ?
        """, (uid,))
        result = cursor.fetchone()

        # 如果没找到，尝试用 sec_user_id 查找
        if not result:
            cursor.execute("""
                SELECT uid, sec_user_id, nickname, avatar_url, signature,
                       follower_count, following_count, aweme_count
                FROM user_info_web WHERE sec_user_id = ?
            """, (uid,))
            result = cursor.fetchone()

        conn.close()

        if not result:
            return False

        user_info = {
            "uid": result[0],
            "sec_user_id": result[1] or "",
            "name": result[2] or "",
            "nickname": result[2] or "",
            "avatar_url": result[3] or "",
            "signature": result[4] or "",
            "follower_count": result[5] or 0,
            "following_count": result[6] or 0,
            "video_count": result[7] or 0,
            "last_updated": datetime.now().isoformat(),
            "last_fetch_time": last_fetch_time,
        }

        # 更新到 following.json
        add_user(result[0], user_info, merge=False)
        return True

    except Exception:
        return False
