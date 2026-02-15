#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音视频下载脚本（已废弃）

⚠️ DEPRECATED: 此脚本已被 download-v2.py 取代
推荐使用: python scripts/download-v2.py <主页URL>

download-v2.py 优势：
- 使用 F2 Python API，更稳定
- 自动保存视频统计数据（点赞、评论、收藏、分享）
- 零额外 API 请求

---

工作流程：
1. 使用 F2 CLI 下载视频（自动跳过已存在文件）
2. 自动整理文件到 downloads/{uid}/
3. 运行 sync-following.py 更新 following.json（含 last_fetch_time）

用法：
    python scripts/download.py <主页URL>           # 首次下载（全量）
    python scripts/download.py <主页URL> --incr    # 增量下载（只下新视频）

增量抓取说明：
- following.json 记录每个用户的 last_fetch_time
- 下载时通过文件存在性检测自动跳过已有视频
- 下载完成后更新 last_fetch_time
"""

import subprocess
import shutil
import sqlite3
import asyncio
import sys
from pathlib import Path
import os

# 强制使用脚本所在目录作为工作目录
SKILL_DIR = Path(__file__).parent.parent.resolve()
# 切换到脚本目录（确保相对路径正确）
os.chdir(SKILL_DIR)

CONFIG_PATH = SKILL_DIR / "config" / "config.yaml"
DB_PATH = SKILL_DIR / "douyin_users.db"
DOWNLOADS_PATH = SKILL_DIR / "downloads"


def get_uid_from_db():
    """从 F2 数据库获取最新的 uid"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT uid, nickname FROM user_info_web ORDER BY ROWID DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception:
        return None


def reorganize_files(nickname):
    """整理文件到 downloads/{uid}/"""
    old_path = DOWNLOADS_PATH / "douyin" / "post" / nickname

    if not old_path.exists():
        return None

    # 获取 uid
    uid_info = get_uid_from_db()
    if not uid_info:
        return None

    uid, _ = uid_info
    new_path = DOWNLOADS_PATH / str(uid)

    # 确保目标文件夹存在
    new_path.mkdir(parents=True, exist_ok=True)

    # 移动所有 mp4 文件（即使已存在也检查是否需要补充）
    moved_count = 0
    for f in old_path.glob("*.mp4"):
        dest = new_path / f.name
        if not dest.exists():
            shutil.move(str(f), str(dest))
            moved_count += 1

    # 如果旧文件夹还有图片也一起移动
    for f in old_path.glob("*.jpg"):
        dest = new_path / f.name
        if not dest.exists():
            shutil.move(str(f), str(dest))
            moved_count += 1

    # 删除旧文件夹（如果为空或不再需要）
    if old_path.exists():
        try:
            shutil.rmtree(old_path)
            print(f"  [清理] {nickname} -> 已删除旧文件夹")
        except:
            pass

    if moved_count > 0:
        print(f"  [移动] {nickname} -> {uid} ({moved_count} 文件)")

    return uid


def run_sync():
    """运行 sync-following.py"""
    subprocess.run([sys.executable, str(SKILL_DIR / "scripts" / "sync-following.py")])


def update_last_fetch_time(uid):
    """更新 following.json 中的 last_fetch_time"""
    from following import update_fetch_time
    update_fetch_time(uid)
    print(f"  [更新] last_fetch_time for {uid}")



async def main():
    # 弃用警告
    print("=" * 60)
    print("⚠️  警告: 此脚本已被废弃，推荐使用 download-v2.py")
    print("   新版优势: 自动保存视频统计数据（点赞、评论等）")
    print("   用法: python scripts/download-v2.py <主页URL>")
    print("=" * 60)
    print()

    if len(sys.argv) < 2:
        print("用法: python scripts/download.py <主页URL>")
        print("  示例: python scripts/download.py https://www.douyin.com/user/xxx")
        return

    url = sys.argv[1]

    # 解析可选参数
    max_counts = None
    extra_args = []
    for arg in sys.argv[2:]:
        if arg.startswith("--max-counts="):
            max_counts = int(arg.split("=")[1])
        else:
            extra_args.append(arg)

    print("开始下载...")

    # 0. 清理 F2 临时结构
    f2_temp_path = DOWNLOADS_PATH / "douyin"
    if f2_temp_path.exists():
        shutil.rmtree(f2_temp_path)
        print("\n0. 清理 F2 临时目录...")

    # 1. 运行 F2 CLI（设置工作目录环境变量，确保日志路径正确）
    print("\n1. 下载中...")

    # 设置 F2 工作目录为技能目录
    f2_env = os.environ.copy()
    f2_env["PWD"] = str(SKILL_DIR)

    # 构建 F2 命令
    f2_cmd = [
        "f2", "dy",
        "-c", str(CONFIG_PATH),
        "-u", url,
        "-M", "post"
    ]
    if max_counts is not None:
        f2_cmd.extend(["--max-counts", str(max_counts)])

    result = subprocess.run(f2_cmd, env=f2_env, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"F2 下载失败: {result.stderr}")
        return

    # 2. 整理文件
    print("\n2. 整理文件...")

    # 查找刚下载的昵称文件夹
    post_path = DOWNLOADS_PATH / "douyin" / "post"
    uid = None
    if post_path.exists():
        for folder in post_path.iterdir():
            if folder.is_dir():
                uid = reorganize_files(folder.name)

    # 3. 更新 last_fetch_time
    if uid:
        update_last_fetch_time(uid)

    # 4. 同步 following.json
    print("\n3. 同步 following.json...")
    run_sync()

    # 5. 提取视频元数据（点赞、评论、收藏等统计信息）
    print("\n4. 提取视频元数据...")
    subprocess.run([sys.executable, str(SKILL_DIR / "scripts" / "extract-metadata.py")])

    # 6. 生成 Web 数据文件
    print("\n5. 生成数据文件...")
    subprocess.run([sys.executable, str(SKILL_DIR / "scripts" / "generate-data.py")])

    print("\n完成！")


if __name__ == "__main__":
    asyncio.run(main())
