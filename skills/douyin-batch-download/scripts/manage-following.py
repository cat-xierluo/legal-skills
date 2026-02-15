#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关注列表管理脚本

用法：
    # 列出所有关注用户
    python scripts/manage-following.py --list

    # 通过主页链接添加用户（仅基础信息）
    python scripts/manage-following.py --add "https://www.douyin.com/user/MS4wLjABAAAA..."

    # 批量导入（粘贴多个 URL，自动获取用户信息）
    python scripts/manage-following.py --batch

    # 更新所有用户信息（不下载视频）
    python scripts/manage-following.py --update

    # 通过UID删除用户（保留已下载的视频文件）
    python scripts/manage-following.py --remove 2722012335188296

    # 通过昵称搜索用户
    python scripts/manage-following.py --search "张总"
"""

import sys
import re
import asyncio
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime
import os

# 强制使用脚本所在目录作为工作目录
SKILL_DIR = Path(__file__).parent.parent.resolve()
# 切换到脚本目录（确保相对路径正确）
os.chdir(SKILL_DIR)

from following import (
    load_following,
    save_following,
    add_user,
    get_user,
    list_users,
    remove_user,
    create_empty_user,
    FOLLOWING_PATH,
)

DOWNLOADS_PATH = SKILL_DIR / "downloads"
DB_PATH = SKILL_DIR / "douyin_users.db"


def clean_nickname(name: str) -> str:
    """清理昵称，去掉抖音后缀"""
    if not name:
        return ""
    # 去掉各种抖音后缀
    suffixes = ["的抖音", "的Douyin", " - 抖音", " - Douyin", " | 抖音", " | Douyin"]
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name.strip()


def fetch_user_info_via_f2(url: str) -> dict:
    """
    通过 F2 下载1个视频来获取用户信息（不弹窗）

    流程：URL -> F2 下载1个视频 -> 归档视频到 downloads/{uid}/ -> 从数据库读取用户信息 -> 返回用户信息
    """
    print(f"  📥 通过 F2 获取用户信息...")

    CONFIG_PATH = SKILL_DIR / "config" / "config.yaml"

    # 先解析 URL 获取 sec_user_id 或 uid
    uid_from_url, sec_id_from_url = extract_uid_from_url(url)

    # 1. 清理旧的 F2 临时目录
    f2_temp_path = DOWNLOADS_PATH / "douyin"
    if f2_temp_path.exists():
        import shutil
        shutil.rmtree(f2_temp_path)

    # 2. 运行 F2 下载（只下载1个视频）
    f2_env = os.environ.copy()
    f2_env["PWD"] = str(SKILL_DIR)

    result = subprocess.run([
        "f2", "dy",
        "-c", str(CONFIG_PATH),
        "-u", url,
        "-M", "post",
        "--max-counts", "1"
    ], env=f2_env, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"     ❌ F2 下载失败: {result.stderr[:100]}")
        return None

    # 3. 从数据库读取用户信息（根据 sec_user_id 或 uid 查询）
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # 优先用 sec_user_id 查询，因为 URL 中通常只有这个
        if sec_id_from_url:
            cursor.execute("""
                SELECT uid, sec_user_id, nickname, avatar_url, signature,
                       follower_count, following_count, aweme_count
                FROM user_info_web WHERE sec_user_id = ?
            """, (sec_id_from_url,))
        elif uid_from_url:
            cursor.execute("""
                SELECT uid, sec_user_id, nickname, avatar_url, signature,
                       follower_count, following_count, aweme_count
                FROM user_info_web WHERE uid = ?
            """, (uid_from_url,))
        else:
            # 兜底：取最新的记录
            cursor.execute("""
                SELECT uid, sec_user_id, nickname, avatar_url, signature,
                       follower_count, following_count, aweme_count
                FROM user_info_web ORDER BY ROWID DESC LIMIT 1
            """)

        row = cursor.fetchone()
        conn.close()

        if not row:
            print(f"     ❌ 数据库中未找到用户信息")
            return None

        # 使用数据库中的数字 UID
        numeric_uid = str(row[0])

        # 4. 归档视频文件到 downloads/{uid}/
        import shutil as sh
        post_path = DOWNLOADS_PATH / "douyin" / "post"
        if post_path.exists():
            for folder in post_path.iterdir():
                if folder.is_dir():
                    target_dir = DOWNLOADS_PATH / numeric_uid
                    target_dir.mkdir(parents=True, exist_ok=True)
                    for f in folder.glob("*.mp4"):
                        dest = target_dir / f.name
                        if not dest.exists():
                            sh.move(str(f), str(dest))
                    for f in folder.glob("*.jpg"):
                        dest = target_dir / f.name
                        if not dest.exists():
                            sh.move(str(f), str(dest))
                    # 删除空文件夹
                    try:
                        sh.rmtree(folder)
                    except:
                        pass

        user_info = {
            "uid": numeric_uid,
            "sec_user_id": row[1] or "",
            "name": clean_nickname(row[2] or ""),
            "nickname": clean_nickname(row[2] or ""),
            "avatar_url": row[3] or "",
            "signature": row[4] or "",
            "follower_count": row[5] or 0,
            "following_count": row[6] or 0,
            "video_count": row[7] or 0,
            "last_updated": datetime.now().isoformat(),
            "last_fetch_time": None,
        }
        print(f"     ✅ 获取成功: {user_info['nickname']}")
        return user_info

    except Exception as e:
        print(f"     ❌ 数据库读取失败: {e}")
        return None


def extract_uid_from_url(url: str) -> tuple:
    """从抖音URL中提取 UID 和 sec_user_id

    Returns:
        (uid, sec_user_id) 元组
        uid: 纯数字 UID（如果没有则返回 None，等 F2 返回后从数据库获取）
        sec_user_id: sec_user_id
    """
    # 匹配数字 UID
    uid_match = re.search(r'/user/(\d+)', url)
    if uid_match:
        return (uid_match.group(1), "")

    # 匹配 sec_user_id (MS4wLjABAAAA...)
    sec_match = re.search(r'/user/(MS4wLjABAAAA[^/"\s]+)', url)
    if sec_match:
        sec_id = sec_match.group(1)
        # 返回 (None, sec_id)，等 F2 下载后从数据库获取真正的数字 UID
        return (None, sec_id)

    return (None, None)


def list_users_cmd():
    """列出所有关注用户"""
    users = list_users()

    if not users:
        print("📋 关注列表为空")
        return

    print(f"\n📋 关注列表 (共 {len(users)} 位博主):")
    print("=" * 60)

    for info in users:
        uid = info.get("uid", "未知")
        name = info.get("nickname", info.get("name", "未知"))
        videos = info.get("video_count", 0)
        followers = info.get("follower_count", 0)
        last_fetch = info.get("last_fetch_time", "未获取")

        # 检查本地视频目录
        user_dir = DOWNLOADS_PATH / str(uid)
        has_videos = user_dir.exists() if user_dir else False
        local_video_count = len(list(user_dir.glob("*.mp4"))) if has_videos else 0

        print(f"\n👤 {name}")
        print(f"   UID: {uid}")
        print(f"   粉丝: {followers:,}  |  视频: {videos}  |  本地: {local_video_count} 个")
        print(f"   最后获取: {last_fetch or '未获取'}")

    print("\n" + "=" * 60)


def remove_user_cmd(uid: str):
    """删除关注用户（保留视频文件，清理数据库记录）"""
    user = get_user(uid)

    if not user:
        print(f"❌ 用户 {uid} 不在关注列表中")
        return

    name = user.get("nickname", user.get("name", "未知"))
    sec_user_id = user.get("sec_user_id", "")

    # 1. 从 following.json 删除
    remove_user(uid)
    print(f"✅ 已从关注列表移除: {name} (UID: {uid})")

    # 2. 清理数据库记录
    db_cleaned = False
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            # 删除 user_info_web 中的记录
            cursor.execute("DELETE FROM user_info_web WHERE uid = ?", (uid,))
            user_deleted = cursor.rowcount

            # 也尝试用 sec_user_id 删除
            if sec_user_id:
                cursor.execute("DELETE FROM user_info_web WHERE sec_user_id = ?", (sec_user_id,))
                user_deleted += cursor.rowcount

            # 删除 video_metadata 中的记录
            cursor.execute("DELETE FROM video_metadata WHERE uid = ?", (uid,))
            video_deleted = cursor.rowcount

            conn.commit()
            conn.close()

            if user_deleted > 0 or video_deleted > 0:
                print(f"🗑️ 已清理数据库: 用户记录 {user_deleted} 条, 视频记录 {video_deleted} 条")
                db_cleaned = True
        except Exception as e:
            print(f"⚠️ 清理数据库时出错: {e}")

    if not db_cleaned and DB_PATH.exists():
        print(f"📋 数据库中无该用户记录")

    # 3. 检查视频目录（保留）
    user_dir = DOWNLOADS_PATH / uid
    if user_dir.exists():
        video_count = len(list(user_dir.glob("*.mp4")))
        print(f"📁 视频文件保留在: {user_dir}")
        print(f"   共 {video_count} 个视频文件未被删除")
    else:
        print(f"📁 本地无该用户视频目录")


def add_user_cmd(url: str):
    """通过主页链接添加用户（仅添加到 following.json）"""
    uid, sec_user_id = extract_uid_from_url(url)

    if not uid:
        print(f"❌ 无法从 URL 提取 UID: {url}")
        print("   请使用抖音主页链接，格式如:")
        print("   https://www.douyin.com/user/MS4wLjABAAAA...")
        return

    # 检查是否已存在
    existing = get_user(uid)
    if existing:
        name = existing.get("nickname", existing.get("name", "未知"))
        print(f"⚠️ 用户已在关注列表: {name} (UID: {uid})")
        return

    # 创建基础用户信息（详细信息需后续下载时更新）
    user_info = create_empty_user(uid, sec_user_id)

    # 添加到关注列表
    add_user(uid, user_info)

    print(f"✅ 已添加用户 (UID: {uid})")
    print(f"   提示: 运行下载脚本可获取完整用户信息和视频")


async def fetch_user_info_from_web(uid: str, sec_user_id: str = None) -> dict:
    """从抖音网页获取用户详细信息"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("   ⚠️ Playwright 未安装，无法获取详细信息")
        return None

    user_info = {
        "uid": uid,
        "sec_user_id": sec_user_id or "",
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

    # 优先使用 sec_user_id 访问
    access_id = sec_user_id if sec_user_id and sec_user_id.startswith("MS4w") else uid

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(SKILL_DIR / ".playwright-data"),
                headless=False,  # 有头模式，避免抖音反爬虫
                viewport={"width": 1280, "height": 800},
                args=["--no-sandbox", "--disable-web-security", "--disable-blink-features=AutomationControlled"],
            )

            page = context.pages[0] if context.pages else await context.new_page()

            try:
                url = f"https://www.douyin.com/user/{access_id}"
                await page.goto(url, wait_until="networkidle", timeout=20000)
                await page.wait_for_timeout(1500)

                # 获取 sec_user_id
                sec_user_id = await page.evaluate("""() => {
                    const url = window.location.href;
                    const match = url.match(/\\/user\\/([^?]+)/);
                    return match ? match[1] : '';
                }""")
                if sec_user_id and not sec_user_id.isdigit():
                    user_info["sec_user_id"] = sec_user_id

                # 从 JSON-LD 获取
                json_ld = await page.evaluate("""() => {
                    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                    for (const s of scripts) {
                        try {
                            const data = JSON.parse(s.textContent);
                            if (data['@type'] === 'Person' || data.author) return data;
                        } catch {}
                    }
                    return null;
                }""")

                if json_ld and isinstance(json_ld, dict):
                    user_info["nickname"] = clean_nickname(json_ld.get("name", ""))
                    if isinstance(json_ld.get("image"), dict):
                        user_info["avatar_url"] = json_ld["image"].get("url", "")
                    else:
                        user_info["avatar_url"] = json_ld.get("image", "")

                # 从 meta 获取昵称
                if not user_info["nickname"]:
                    nickname = await page.evaluate("""() => {
                        const ogTitle = document.querySelector('meta[property="og:title"]');
                        return ogTitle ? ogTitle.getAttribute('content') : document.title;
                    }""")
                    user_info["nickname"] = clean_nickname(nickname)

                # 获取头像 - 优先从页面元素获取
                if not user_info["avatar_url"]:
                    avatar_result = await page.evaluate("""() => {
                        // 1. 尝试 og:image
                        const ogImage = document.querySelector('meta[property="og:image"]');
                        if (ogImage) return ogImage.getAttribute('content');

                        // 2. 尝试页面上的头像图片
                        const avatarImg = document.querySelector('img[class*="avatar"], img[src*="avatar"], img[alt*="头像"]');
                        if (avatarImg && avatarImg.src) return avatarImg.src;

                        // 3. 尝试 background-image
                        const avatarDiv = document.querySelector('[class*="avatar"]');
                        if (avatarDiv) {
                            const bg = window.getComputedStyle(avatarDiv).backgroundImage;
                            const match = bg.match(/url\\(['"]?(.+?)['"]?\\)/);
                            if (match) return match[1];
                        }
                        return '';
                    }""")
                    user_info["avatar_url"] = avatar_result or ""

                # 获取签名
                signature = await page.evaluate("""() => {
                    const desc = document.querySelector('meta[property="og:description"]');
                    return desc ? desc.getAttribute('content') : '';
                }""")
                user_info["signature"] = signature

            except Exception as e:
                print(f"   ⚠️ 获取信息出错: {e}")

            await context.close()

    except Exception as e:
        print(f"   ⚠️ Playwright 错误: {e}")
        return None

    return user_info


def batch_add_cmd(auto_confirm: bool = False):
    """批量导入用户（粘贴多个 URL，自动获取用户信息）"""
    print("\n📋 批量导入用户")
    print("=" * 60)
    print("请粘贴多个抖音主页 URL（支持逗号、空格、换行分隔）")
    print("输入空行或 'done' 结束输入")
    print("-" * 60)

    lines = []
    while True:
        try:
            line = input()
            if line.strip().lower() in ("", "done", "q", "quit"):
                break
            lines.append(line)
        except EOFError:
            break

    # 合并所有行
    all_text = " ".join(lines)

    # 分割 URL（支持逗号、空格、换行）
    urls = re.split(r'[,\s]+', all_text)
    urls = [u.strip() for u in urls if u.strip()]

    if not urls:
        print("❌ 未检测到有效的 URL")
        return

    # 提取所有 UID（包括只有 sec_user_id 的情况）
    user_requests = []
    for url in urls:
        uid, sec_user_id = extract_uid_from_url(url)
        user_requests.append({
            "url": url,
            "initial_uid": uid,  # URL 中解析出的初始 UID（可能为 None）
            "sec_user_id": sec_user_id,
        })

    if not user_requests:
        print("❌ 无法从输入中提取有效的用户 ID")
        return

    # 去重（基于 URL）
    seen_urls = set()
    unique_requests = []
    for req in user_requests:
        if req["url"] not in seen_urls:
            seen_urls.add(req["url"])
            unique_requests.append(req)

    # 显示待添加列表
    print(f"\n📝 检测到 {len(unique_requests)} 个用户:")
    print("-" * 60)
    for i, req in enumerate(unique_requests, 1):
        # 检查是否已存在（按 sec_user_id 检查）
        existing = None
        if req["sec_user_id"]:
            # 通过 sec_user_id 查找已存在的用户
            for u in list_users():
                if u.get("sec_user_id") == req["sec_user_id"]:
                    existing = u
                    break
        status = "已存在" if existing else "新增"
        display_id = req["sec_user_id"][:20] if req["sec_user_id"] else (req["initial_uid"][:20] if req["initial_uid"] else "未知")
        print(f"  {i}. {display_id}... [{status}]")

    # 确认添加
    print("-" * 60)
    if not auto_confirm:
        confirm = input("\n确认添加并获取用户信息？(y/N): ").strip().lower()
        if confirm != "y":
            print("❌ 已取消")
            return

    # 添加用户并获取信息
    added = 0
    updated = 0
    failed = 0

    print("\n📱 正在通过 F2 获取用户信息...")

    for i, req in enumerate(unique_requests, 1):
        url = req["url"]
        print(f"  [{i}/{len(unique_requests)}] {url[:50]}...")

        # 检查是否已存在（通过 sec_user_id）
        existing = None
        if req["sec_user_id"]:
            for u in list_users():
                if u.get("sec_user_id") == req["sec_user_id"]:
                    existing = u
                    break

        # 通过 F2 下载获取用户信息（不弹窗）
        info = fetch_user_info_via_f2(url)

        if info and info.get("nickname"):
            # 使用获取到的真正数字 UID
            actual_uid = info.get("uid")
            # 再次检查是否已存在（通过数字 UID）
            if not existing:
                existing = get_user(actual_uid)
            # 保留已有的 last_fetch_time
            if existing:
                info["last_fetch_time"] = existing.get("last_fetch_time")
                add_user(actual_uid, info, merge=False)
                updated += 1
            else:
                add_user(actual_uid, info, merge=False)
                added += 1
        else:
            if existing:
                failed += 1
                print(f"     ⚠️ 获取失败，保留原有数据")
            else:
                user_info = create_empty_user(req["initial_uid"] or "", req["sec_user_id"])
                add_user(req["initial_uid"] or "", user_info)
                added += 1
                failed += 1
                print(f"     ⚠️ 获取失败，仅保存基础信息")

    print(f"\n✅ 完成! 新增 {added} 个，更新 {updated} 个，失败 {failed} 个")
    print(f"   配置文件: {FOLLOWING_PATH}")


def update_all_users_cmd(auto_confirm: bool = False):
    """更新所有用户信息（从 F2 数据库同步，不触发下载）"""
    users = list_users()

    if not users:
        print("📋 关注列表为空")
        return

    print(f"\n📋 更新用户信息（从 F2 数据库同步）")
    print("=" * 60)
    print(f"共 {len(users)} 个用户")
    print("-" * 60)

    from following import update_user_info_from_db

    synced = 0
    no_data = 0

    for i, user in enumerate(users, 1):
        uid = user.get("uid")
        name = user.get("nickname", user.get("name", ""))

        # 从数据库更新用户信息（保留 last_fetch_time）
        if update_user_info_from_db(uid, user.get("last_fetch_time")):
            synced += 1
            # 读取更新后的昵称
            updated = get_user(uid)
            new_name = updated.get("nickname", uid[:20]) if updated else uid[:20]
            print(f"  [{i}/{len(users)}] ✅ {new_name}")
        else:
            no_data += 1
            display = name if name else f"{uid[:30]}..."
            print(f"  [{i}/{len(users)}] ⚠️ {display} (数据库无记录)")

    print("\n" + "=" * 60)
    print(f"📊 结果: 同步 {synced} 个，无数据 {no_data} 个")
    if no_data > 0:
        print("\n💡 提示: 无数据的用户需要先运行下载脚本获取完整信息")
        print("   例如: python scripts/batch-download.py --all")


def search_users(keyword: str):
    """搜索用户"""
    users = list_users()
    keyword_lower = keyword.lower()

    print(f"\n🔍 搜索: {keyword}")
    print("=" * 60)

    found = False
    for info in users:
        uid = info.get("uid", "")
        name = info.get("nickname", info.get("name", "")).lower()
        sig = info.get("signature", "").lower()

        if keyword_lower in name or keyword_lower in sig or keyword_lower in uid:
            found = True
            display_name = info.get("nickname", info.get("name", "未知"))
            print(f"\n👤 {display_name}")
            print(f"   UID: {uid}")
            if info.get("signature"):
                sig_text = info.get("signature", "")[:50]
                if len(info.get("signature", "")) > 50:
                    sig_text += "..."
                print(f"   简介: {sig_text}")

    if not found:
        print("未找到匹配用户")

    print("\n" + "=" * 60)


def status_tasks_cmd():
    """查看后台任务状态"""
    log_dir = DOWNLOADS_PATH / "logs"

    if not log_dir.exists():
        print("📋 暂无后台任务")
        return

    log_files = sorted(log_dir.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)

    if not log_files:
        print("📋 暂无后台任务")
        return

    print(f"\n📋 后台任务列表 (共 {len(log_files)} 个)")
    print("=" * 60)

    for log_file in log_files:
        task_id = log_file.stem

        # 读取日志文件获取任务信息
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                first_lines = lines[:5] if lines else []
                last_lines = lines[-3:] if lines else []
                log_content = ''.join(lines)
        except Exception:
            log_content = ""

        # 判断状态
        if "[完成]" in log_content or "共下载" in log_content:
            status = "✅ 已完成"
        elif "[下载]" in log_content:
            status = "🟢 运行中"
        else:
            status = "⚪ 已启动"

        # 从文件名提取 UID
        parts = task_id.split("-")
        uid = parts[1] if len(parts) > 1 else "未知"

        # 查找对应用户
        user = get_user(uid)
        name = user.get("nickname", user.get("name", "未知")) if user else "未知"

        print(f"\n{status} {name}")
        print(f"   任务ID: {task_id}")
        print(f"   UID: {uid}")

        # 显示最后一条进度信息
        for line in reversed(last_lines):
            line = line.strip()
            if line and not line.startswith("="):
                print(f"   📊 {line}")
                break

    print("\n" + "=" * 60)
    print("💡 命令提示:")
    print("   查看实时日志: tail -f downloads/logs/<任务ID>.log")
    print("   查看所有日志: ls -lt downloads/logs/")
    print("=" * 60)


def main():
    # 检查是否有 --yes 参数（跳过确认）
    auto_confirm = "--yes" in sys.argv
    if auto_confirm:
        sys.argv.remove("--yes")

    if len(sys.argv) < 2:
        print("用法:")
        print("  python scripts/manage-following.py --list")
        print("  python scripts/manage-following.py --add <抖音主页链接>")
        print("  python scripts/manage-following.py --batch")
        print("  python scripts/manage-following.py --update")
        print("  python scripts/manage-following.py --remove <UID>")
        print("  python scripts/manage-following.py --search <关键词>")
        print("  python scripts/manage-following.py --status          # 查看后台任务状态")
        print("  --yes                                    # 跳过确认直接执行")
        return

    action = sys.argv[1]

    if action == "--list":
        list_users_cmd()
    elif action == "--remove":
        if len(sys.argv) < 3:
            print("用法: python scripts/manage-following.py --remove <UID>")
            return
        remove_user_cmd(sys.argv[2])
    elif action == "--add":
        if len(sys.argv) < 3:
            print("用法: python scripts/manage-following.py --add <抖音主页链接>")
            return
        add_user_cmd(sys.argv[2])
    elif action == "--batch":
        batch_add_cmd(auto_confirm=auto_confirm)
    elif action == "--update":
        update_all_users_cmd(auto_confirm=auto_confirm)
    elif action == "--search":
        if len(sys.argv) < 3:
            print("用法: python scripts/manage-following.py --search <关键词>")
            return
        search_users(sys.argv[2])
    elif action == "--status":
        status_tasks_cmd()
    else:
        print(f"❌ 未知操作: {action}")
        print("可用操作: --list, --add, --batch, --update, --remove, --search, --status")


if __name__ == "__main__":
    main()
