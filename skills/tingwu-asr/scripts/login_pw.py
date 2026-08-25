#!/usr/bin/env python3
"""通义听悟登录(SKILL 内置 Playwright 通道,替代 MCP Playwright 手工流程)

用途:一条命令完成"打开浏览器 → 自动填凭证 → 等待登录 → cookie 落盘"。
为什么不用 document.cookie:拿不到 HttpOnly 的 login_aliyunid_ticket,
必须用 context.cookies() 从浏览器上下文取,本脚本即走该通道,
且 cookie 值全程不经过 stdout。

用法:
  python3 scripts/login_pw.py            # 从 config/.env 读凭证自动填充
  python3 scripts/login_pw.py --headless # 无头模式(不推荐,滑块验证需人工)

流程:
1. headed Chromium 打开 tingwu.aliyun.com/home
2. 点"立即登录" → 切"账号密码登录" tab → 自动填充账号密码 → 提交
3. 若出现滑块/验证码,在可见窗口手动完成即可,脚本轮询等待
4. 登录成功后 context.cookies() 直接写 config/cookies.json
"""
import argparse
import json
import sys
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
COOKIE_PATH = SKILL_ROOT / "config" / "cookies.json"
ENV_PATH = SKILL_ROOT / "config" / ".env"

LOGIN_MARKER = "login_aliyunid_ticket"  # HttpOnly,登录态判定的锚点


def load_env():
    user, pwd = "", ""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TINGWU_USERNAME="):
                user = line.split("=", 1)[1]
            elif line.startswith("TINGWU_PASSWORD="):
                pwd = line.split("=", 1)[1]
    return user, pwd


def has_login_cookie(cookies):
    return any(c["name"] == LOGIN_MARKER for c in cookies)


def find_login_frame(page):
    for fr in page.frames:
        if "account.aliyun.com" in (fr.url or ""):
            return fr
    return None


def main():
    parser = argparse.ArgumentParser(description="通义听悟 Playwright 登录")
    parser.add_argument("--headless", action="store_true", help="无头模式(滑块验证时不可用)")
    parser.add_argument("--timeout", type=int, default=300, help="等待人工完成登录的最长秒数")
    args = parser.parse_args()

    username, password = load_env()
    if not username or not password:
        print("!! config/.env 凭证缺失(TINGWU_USERNAME / TINGWU_PASSWORD)")
        sys.exit(1)
    print(f"[1] 凭证已加载 (用户名 {len(username)} 字符)")

    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/145.0.0.0 Safari/537.36"),
        )
        page = ctx.new_page()
        page.goto("https://tingwu.aliyun.com/home", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)

        if has_login_cookie(ctx.cookies()):
            print("[2] 已处于登录态,跳过登录")
        else:
            print("[2] 打开登录弹窗...")
            try:
                page.get_by_role("button", name="立即登录").click(timeout=8000)
            except PWTimeout:
                try:
                    page.get_by_text("立即登录", exact=True).click(timeout=5000)
                except Exception:
                    print("   (未找到'立即登录'按钮,尝试直接定位登录 iframe)")
            page.wait_for_timeout(3000)

            print("[3] 切换到账号密码登录...")
            target_frame = None
            for _ in range(6):
                target_frame = find_login_frame(page)
                if target_frame:
                    break
                page.wait_for_timeout(2000)
            if not target_frame:
                print("!! 未找到阿里云登录 frame")
                browser.close()
                sys.exit(2)

            tab_clicked = False
            for fr in page.frames:
                if "account.aliyun.com" not in (fr.url or ""):
                    continue
                for name in ["账号密码登录", "密码登录"]:
                    try:
                        fr.get_by_text(name, exact=False).first.click(timeout=3000)
                        tab_clicked = True
                        print(f"   已点击 tab: {name}")
                        break
                    except Exception:
                        continue
                if tab_clicked:
                    break
            if not tab_clicked:
                print("   (未找到'账号密码登录'tab,可能默认已是密码页)")
            page.wait_for_timeout(2000)

            print("[4] 填充账号密码...")
            filled_user = filled_pwd = False
            for fr in page.frames:
                if "account.aliyun.com" not in (fr.url or ""):
                    continue
                for sel in ['input#account', 'input[name="account"]',
                            'input[placeholder*="邮箱"]', 'input[placeholder*="账号"]',
                            'input[placeholder*="手机"]']:
                    try:
                        el = fr.locator(sel).first
                        if el.is_visible(timeout=1500):
                            el.fill(username)
                            filled_user = True
                            break
                    except Exception:
                        continue
                for sel in ['input#password', 'input[name="password"]',
                            'input[type="password"]']:
                    try:
                        el = fr.locator(sel).first
                        if el.is_visible(timeout=1500):
                            el.fill(password)
                            filled_pwd = True
                            break
                    except Exception:
                        continue
                if filled_user and filled_pwd:
                    break
            print(f"   账号填充={filled_user} 密码填充={filled_pwd}")
            if not (filled_user and filled_pwd):
                print("!! 自动填充失败,请在弹出的浏览器窗口手动输入并登录")
            else:
                page.wait_for_timeout(8000)  # 等 JS 校验/可能的滑块出现
                for fr in page.frames:
                    if "account.aliyun.com" not in (fr.url or ""):
                        continue
                    try:
                        btn = fr.get_by_role("button", name="登 录")
                        if not btn.count():
                            btn = fr.get_by_role("button", name="登录")
                        if btn.count():
                            btn.first.click(timeout=3000)
                            print("   已点击登录按钮")
                            break
                    except Exception:
                        continue

            print(f"[5] 等待登录完成(最长 {args.timeout}s;如浏览器有滑块/验证码请手动完成)...")
            ok = False
            rounds = args.timeout // 5
            for i in range(rounds):
                try:
                    if has_login_cookie(ctx.cookies()):
                        ok = True
                        break
                except Exception:
                    pass
                if i and i % 6 == 0:
                    print(f"   ...已等待 {i*5}s")
                page.wait_for_timeout(5000)
            if not ok:
                print(f"!! 等待登录超时({args.timeout}s),未检测到登录 cookie")
                browser.close()
                sys.exit(3)
            print("[5] 登录成功 ✓")

        print("[6] 保存 cookie...")
        page.goto("https://tingwu.aliyun.com/home", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        raw = ctx.cookies()
        cookie_map = {}
        for c in raw:
            d = c.get("domain", "")
            if "aliyun.com" in d or "taobao.com" in d or "alicdn.com" in d:
                cookie_map[c["name"]] = c["value"]
        data = {
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cookies": cookie_map,
        }
        COOKIE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[6] 已保存 {len(cookie_map)} 个 cookie → {COOKIE_PATH}")
        browser.close()

    print("DONE")


if __name__ == "__main__":
    main()
