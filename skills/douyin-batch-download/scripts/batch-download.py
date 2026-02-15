#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量下载脚本 - 使用 F2 Python API 下载视频并自动保存统计数据

用法：
    # 交互式选择博主下载
    python scripts/batch-download.py

    # 一键全量下载
    python scripts/batch-download.py --all

    # 下载指定博主
    python scripts/batch-download.py --uid 7483912725043774523

    # 采样下载（每个博主1个视频，用于快速更新统计数据）
    python scripts/batch-download.py --sample

特性：
    - 自动保存视频统计数据（点赞、评论、收藏、分享）
    - 零额外 API 请求（数据在下载时获取）
"""

import subprocess
import sys
import uuid
import time
from pathlib import Path
import os

# 强制使用脚本所在目录作为工作目录
SKILL_DIR = Path(__file__).parent.parent.resolve()
# 切换到脚本目录（确保相对路径正确）
os.chdir(SKILL_DIR)

from following import (
    list_users,
    get_user,
    update_fetch_time,
)

DOWNLOAD_SCRIPT = SKILL_DIR / "scripts" / "download-v2.py"
DOWNLOADS_PATH = SKILL_DIR / "downloads"


def get_local_video_count(uid: str) -> int:
    """获取本地视频数量"""
    user_dir = DOWNLOADS_PATH / str(uid)
    if user_dir.exists():
        return len(list(user_dir.glob("*.mp4")))
    return 0


def download_user(uid: str, sec_user_id: str = None, max_counts: int = None, daemon: bool = False):
    """下载单个用户的视频

    Args:
        uid: 用户 ID
        sec_user_id: 用户 sec_user_id
        max_counts: 最大下载数量，None 表示不限制
        daemon: 是否后台运行
    """
    # 构建用户主页 URL
    if sec_user_id and sec_user_id.startswith("MS4w"):
        url = f"https://www.douyin.com/user/{sec_user_id}"
    else:
        url = f"https://www.douyin.com/user/{uid}"

    # 生成任务 ID
    task_id = f"douyin-{uid}-{int(time.time())}"

    if daemon:
        # 后台运行模式
        log_dir = DOWNLOADS_PATH / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{task_id}.log"

        cmd = [sys.executable, str(DOWNLOAD_SCRIPT), url, "--daemon", f"--task-id={task_id}"]
        if max_counts is not None:
            cmd.append(f"--max-counts={max_counts}")

        # 使用 nohup 后台运行
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"[任务创建] {task_id}\n")
            f.write(f"[UID] {uid}\n")
            f.write(f"[URL] {url}\n")
            f.write(f"[时间] {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n")

        # 后台启动进程
        subprocess.Popen(
            cmd,
            cwd=str(SKILL_DIR),
            stdout=open(log_file, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            start_new_session=True,  # 脱离父进程
        )

        print(f"✅ 已启动后台任务: {task_id}")
        print(f"   📋 任务ID: {task_id}")
        print(f"   📁 日志: {log_file}")
        print(f"   🔍 查看进度: tail -f {log_file}")
        return task_id
    else:
        # 同步运行模式
        print(f"\n{'='*60}")
        print(f"📥 开始下载: {uid}" + (f" (最多 {max_counts} 个)" if max_counts else ""))
        print(f"{'='*60}")

        cmd = [sys.executable, str(DOWNLOAD_SCRIPT), url]
        if max_counts is not None:
            cmd.append(f"--max-counts={max_counts}")

        result = subprocess.run(cmd, cwd=str(SKILL_DIR))

        if result.returncode == 0:
            # 更新 last_fetch_time
            update_fetch_time(uid)
            print(f"✅ 下载完成: {uid}")
            return True
        else:
            print(f"❌ 下载失败: {uid}")
            return False


def interactive_select():
    """交互式选择博主下载"""
    users = list_users()

    if not users:
        print("📋 关注列表为空，请先添加用户")
        print("   用法: python scripts/manage-following.py --batch")
        return

    print("\n📋 选择要下载的博主")
    print("=" * 60)

    for i, user in enumerate(users, 1):
        uid = user.get("uid", "未知")
        name = user.get("nickname", user.get("name", "未知"))
        local_count = get_local_video_count(uid)
        last_fetch = user.get("last_fetch_time", "未获取")

        # 显示状态标记
        if local_count > 0:
            status = f"📦 已下载 {local_count} 个"
        else:
            status = "🆕 未下载"

        print(f"  {i:2}. {name}")
        print(f"      UID: {uid}")
        print(f"      状态: {status} | 最后获取: {last_fetch or '未获取'}")
        print()

    print("=" * 60)
    print("输入数字选择博主（支持多选，用逗号分隔）")
    print("输入 'all' 下载全部，'q' 退出")
    print("-" * 60)

    choice = input("请选择: ").strip().lower()

    if choice == "q" or choice == "":
        print("❌ 已取消")
        return

    if choice == "all":
        download_all_users(users)
        return

    # 解析选择的数字
    try:
        indices = [int(x.strip()) for x in choice.split(",")]
        selected = []
        for idx in indices:
            if 1 <= idx <= len(users):
                selected.append(users[idx - 1])
            else:
                print(f"⚠️ 无效的序号: {idx}")

        if not selected:
            print("❌ 没有有效的选择")
            return

        print(f"\n📝 已选择 {len(selected)} 个博主")
        download_selected_users(selected)

    except ValueError:
        print("❌ 无效的输入，请输入数字")


def download_selected_users(users: list):
    """下载选定的用户"""
    total = len(users)
    success = 0
    failed = 0

    for i, user in enumerate(users, 1):
        uid = user.get("uid")
        sec_user_id = user.get("sec_user_id", "")
        name = user.get("nickname", user.get("name", "未知"))

        print(f"\n[{i}/{total}] 处理: {name}")

        if download_user(uid, sec_user_id):
            success += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    print(f"✨ 批量下载完成: 成功 {success}，失败 {failed}")
    print("=" * 60)


def download_all_users(users: list = None, auto_confirm: bool = False, daemon: bool = False):
    """下载全部用户

    Args:
        users: 用户列表，None 表示从 following.json 加载
        auto_confirm: 是否跳过确认
        daemon: 是否后台运行
    """
    if users is None:
        users = list_users()

    if not users:
        print("📋 关注列表为空，请先添加用户")
        return

    total = len(users)

    if daemon:
        # 后台模式：直接启动所有任务
        print(f"\n🚀 后台模式：准备启动全部 {total} 个下载任务")
        print("-" * 60)

        task_ids = []
        for user in users:
            uid = user.get("uid")
            sec_user_id = user.get("sec_user_id", "")
            name = user.get("nickname", user.get("name", "未知"))
            task_id = download_user(uid, sec_user_id, daemon=True)
            if task_id:
                task_ids.append((name, task_id))

        print("\n" + "=" * 60)
        print(f"✅ 已启动 {len(task_ids)} 个后台任务")
        print("-" * 60)
        for name, task_id in task_ids:
            print(f"   📺 {name}: {task_id}")
        print("-" * 60)
        print("🔍 查看所有日志: ls downloads/logs/")
        print("=" * 60)
    else:
        # 同步模式
        print(f"\n📥 准备下载全部 {total} 个博主")
        print("-" * 60)

        if not auto_confirm:
            confirm = input("确认开始？(y/N): ").strip().lower()
            if confirm != "y":
                print("❌ 已取消")
                return

        download_selected_users(users)


def download_by_uid(uid: str, max_counts: int = None, daemon: bool = False):
    """下载指定 UID 的用户

    Args:
        uid: 用户 ID
        max_counts: 最大下载数量
        daemon: 是否后台运行
    """
    user = get_user(uid)

    if not user:
        print(f"❌ 用户 {uid} 不在关注列表中")
        print("   请先添加: python scripts/manage-following.py --add <URL>")
        return

    name = user.get("nickname", user.get("name", "未知"))
    sec_user_id = user.get("sec_user_id", "")

    if daemon:
        print(f"\n🚀 后台模式：准备启动下载任务")
        print(f"   📺 博主: {name} (UID: {uid})")
        print("-" * 60)
        task_id = download_user(uid, sec_user_id, max_counts, daemon=True)
        print("\n" + "=" * 60)
        if task_id:
            print(f"✅ 后台任务已启动")
            print(f"   📋 任务ID: {task_id}")
        print("=" * 60)
    else:
        print(f"\n📥 下载博主: {name} (UID: {uid})")
        download_user(uid, sec_user_id, max_counts)


def download_sample(auto_confirm: bool = False, daemon: bool = False):
    """每个用户只下载1个视频，用于快速更新数据

    Args:
        auto_confirm: 是否跳过确认
        daemon: 是否后台运行
    """
    users = list_users()

    if not users:
        print("📋 关注列表为空，请先添加用户")
        return

    total = len(users)

    if daemon:
        # 后台模式：直接启动所有任务
        print(f"\n🚀 后台模式：准备启动 {total} 个采样下载任务")
        print("-" * 60)

        task_ids = []
        for user in users:
            uid = user.get("uid")
            sec_user_id = user.get("sec_user_id", "")
            name = user.get("nickname", user.get("name", "未知"))
            task_id = download_user(uid, sec_user_id, max_counts=1, daemon=True)
            if task_id:
                task_ids.append((name, task_id))

        print("\n" + "=" * 60)
        print(f"✅ 已启动 {len(task_ids)} 个后台任务")
        print("-" * 60)
        for name, task_id in task_ids:
            print(f"   📺 {name}: {task_id}")
        print("-" * 60)
        print("🔍 查看所有日志: ls downloads/logs/")
        print("=" * 60)
    else:
        # 同步模式
        print(f"\n📥 采样下载：每个博主只下载 1 个视频")
        print(f"   共 {total} 个博主")
        print("-" * 60)

        if not auto_confirm:
            confirm = input("确认开始？(y/N): ").strip().lower()
            if confirm != "y":
                print("❌ 已取消")
                return

        success = 0
        failed = 0

        for i, user in enumerate(users, 1):
            uid = user.get("uid")
            sec_user_id = user.get("sec_user_id", "")
            name = user.get("nickname", user.get("name", "未知"))

            print(f"\n[{i}/{total}] 采样下载: {name}")

            if download_user(uid, sec_user_id, max_counts=1):
                success += 1
            else:
                failed += 1

        print("\n" + "=" * 60)
    print(f"✨ 采样下载完成: 成功 {success}，失败 {failed}")
    print("=" * 60)


def main():
    # 检查是否有 --yes 参数（跳过确认）
    auto_confirm = "--yes" in sys.argv
    if auto_confirm:
        sys.argv.remove("--yes")

    # 检查是否有 --daemon 参数（后台运行）
    daemon_mode = "--daemon" in sys.argv
    if daemon_mode:
        sys.argv.remove("--daemon")

    if len(sys.argv) < 2:
        interactive_select()
        return

    action = sys.argv[1]

    if action == "--all":
        download_all_users(auto_confirm=auto_confirm, daemon=daemon_mode)
    elif action == "--sample":
        # 每个用户只下载1个视频，用于更新数据
        download_sample(auto_confirm=auto_confirm, daemon=daemon_mode)
    elif action == "--uid":
        if len(sys.argv) < 3:
            print("用法: python scripts/batch-download.py --uid <UID>")
            return
        download_by_uid(sys.argv[2], daemon=daemon_mode)
    else:
        print(f"❌ 未知参数: {action}")
        print("用法:")
        print("  python scripts/batch-download.py           # 交互选择")
        print("  python scripts/batch-download.py --all      # 全量下载")
        print("  python scripts/batch-download.py --sample   # 采样下载（每个1个视频）")
        print("  python scripts/batch-download.py --uid <UID> # 指定博主")
        print("  --daemon                                # 后台运行模式")
        print("  --yes                                   # 跳过确认直接执行")
        print("  --yes                                    # 跳过确认直接执行")


if __name__ == "__main__":
    main()
