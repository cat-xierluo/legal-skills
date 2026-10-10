#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步 following.json
从 douyin_users.db (F2 缓存) 读取用户信息，更新 following.json

数据源：
- douyin_users.db: F2 缓存的主数据源（用户信息）
- following.json: 保留 last_fetch_time 等自定义字段

用法：
    python scripts/sync-following.py
    python scripts/sync-following.py --root <视频根目录> --db <db> --following <out.json> --no-html

DY-001（2026-10-10）：
- --root/--db/--following 显式覆盖（供 download-v2 与测试隔离使用，默认行为不变）。
- 视频计数使用与下载器同一配置源（utils.config），不再硬编码 ~/Downloads/抖音视频下载。
- 退出码：0=成功；1=db 缺失或写入失败。
- --following 显式覆盖时默认不生成 index.html（防止测试/自定义清单覆写技能页），
  需要时显式 --html。
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from datetime import datetime
import os

# 强制使用脚本所在目录作为工作目录
SKILL_DIR = Path(__file__).parent.parent.resolve()
# 切换到脚本目录（确保相对路径正确）
os.chdir(SKILL_DIR)

from utils.config import (
    set_overrides,
    get_db_path,
    get_download_path,
    get_following_path,
)

from following import (
    load_following,
    save_following,
    add_user,
    list_users,
    get_user,
)

HTML_PATH = SKILL_DIR / "downloads" / "index.html"


def get_user_info_from_db(db_path, uid):
    """从 F2 数据库获取用户信息"""
    try:
        conn = sqlite3.connect(str(db_path))
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


def get_video_count(video_root: Path, nickname: str):
    """统计用户视频数量（按下载器同一配置源解析的视频根目录）"""
    user_path = video_root / nickname
    return sum(1 for _ in user_path.glob("*.mp4")) if user_path.exists() else 0


def generate_html(users):
    """生成 index.html"""
    if not HTML_PATH.exists():
        print(f"  [跳过] 未找到 HTML 模板")
        return

    import json

    html = HTML_PATH.read_text(encoding="utf-8")
    downloads_dir = str(Path.home() / "Downloads" / "抖音视频下载")

    # 转换为 {users: [...]} 格式
    data = {"users": users}
    json_str = json.dumps(data, ensure_ascii=False)

    html = html.replace("FILE_PLACEHOLDER", downloads_dir)
    html = html.replace("PLACEHOLDER_JSON", json_str)

    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"  [更新] index.html")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="同步 following.json（db 为真值全量重建）")
    parser.add_argument("--root", default=None,
                        help="视频根目录覆盖（默认: 下载器同一配置源）")
    parser.add_argument("--db", default=None,
                        help="douyin_users.db 路径覆盖（默认: 技能目录）")
    parser.add_argument("--following", default=None,
                        help="following.json 输出路径覆盖（默认: 技能 config/following.json）")
    parser.add_argument("--no-html", dest="html", action="store_false", default=None,
                        help="不生成 index.html")
    parser.add_argument("--html", dest="html", action="store_true", default=None,
                        help="强制生成 index.html（--following 覆盖时默认关闭）")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    set_overrides(download_root=args.root, db_path=args.db, following_path=args.following)
    db_path = Path(get_db_path())
    video_root = Path(get_download_path())
    following_path = Path(get_following_path())

    # --following 显式覆盖时默认不写技能页，防误覆写
    want_html = args.html
    if want_html is None:
        want_html = args.following is None

    print("同步 following.json (从 db 全量重建,db 为真值)")
    print("=" * 50)
    print(f"  db: {db_path}")
    print(f"  视频根目录: {video_root}")
    print(f"  following: {following_path}")

    if not db_path.exists():
        print(f"未找到 db: {db_path}")
        return 1

    # 加载旧数据(按 sec_user_id 保留 last_fetch_time 等扩展字段)
    old_data = load_following()
    old_users = {u.get("sec_user_id"): u for u in old_data.get("users", [])}

    # 从 db 全量读博主(db 是真值,含 peer_type)
    conn = sqlite3.connect(str(db_path))
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
        # video_count 从视频实际位置统计(<root>/<昵称>/)
        video_count = get_video_count(video_root, r["nickname"])
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
        if want_html:
            generate_html(new_users)
        # 保存 following.json
        try:
            save_following({"users": new_users})
        except OSError as e:
            print(f"写入 following.json 失败: {e}")
            return 1

    print(f"\n保存到: {following_path}")
    print(f"共 {len(new_users)} 个博主")
    return 0


if __name__ == "__main__":
    sys.exit(main())
