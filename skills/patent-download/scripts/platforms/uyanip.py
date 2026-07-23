#!/usr/bin/env python3
"""
度衍专利 (uyanip) 专利下载
账号通过环境变量配置（见 config/.env.example），不在脚本里硬编码。

特点：
- 搜索后可以直接看到专利详情
- 有"PDF下载"按钮，可以直接下载
- 无需验证码
"""

import os
import sys
import json
from typing import Optional, Dict, List

try:
    import requests
except ImportError:
    print("❌ 缺少依赖: requests")
    print("   请运行: pip install -r scripts/requirements.txt")
    raise SystemExit(1)

try:
    from platforms._creds import load_creds
except Exception:
    def load_creds(_platform):
        return {}

# 配置
CONFIG = {
    "name": "度衍专利",
    "base_url": "https://www.uyanip.com",
}


class UyanipAPI:
    """API 方式 - 待研究（实验性桩，未实现）"""

    def __init__(self, cookies: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": CONFIG["base_url"],
        })
        if cookies:
            self.session.cookies.update(json.loads(cookies))

    def search(self, patent_number: str) -> Dict:
        """搜索专利 - 需要研究具体 API（未实现桩）"""
        # TODO: 研究具体 API
        print("⚠️ 度衍 API 方式尚未实现，请使用浏览器方式（-m browser）。")
        return {"status": "not_implemented", "message": "API 待研究"}


class UyanipBrowser:
    """浏览器方式 - 推荐"""
    
    BASE_URL = "https://www.uyanip.com"
    
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.browser = None
        self.page = None
    
    def start(self):
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context(viewport={"width": 1920, "height": 1080})
        self.page = self.context.new_page()
    
    def close(self):
        if self.browser:
            self.browser.close()
        if hasattr(self, 'playwright'):
            self.playwright.stop()
    
    def login(self, username: str, password: str):
        """登录"""
        self.page.goto(f"{self.BASE_URL}/")
        self.page.wait_for_load_state("networkidle")
        
        # 点击登录按钮 - 使用更精确的选择器
        try:
            # 尝试点击顶部的登录按钮
            login_btn = self.page.locator('a:has-text("登录"), button:has-text("登录")').first
            if login_btn.is_visible():
                login_btn.click()
                self.page.wait_for_load_state("networkidle")
        except:
            pass
        
        # 如果页面没有自动跳转，刷新后重试
        if "login" not in self.page.url:
            self.page.goto(f"{self.BASE_URL}/user/login")
            self.page.wait_for_load_state("networkidle")
        
        # 填写登录表单
        self.page.fill('input[placeholder*="手机号"], input[type="text"]', username)
        self.page.fill('input[type="password"]', password)
        self.page.click('button:has-text("登录")')
        
        self.page.wait_for_load_state("networkidle")
        print("✅ 登录成功")
    
    def search(self, patent_number: str):
        """搜索专利"""
        self.page.goto(f"{self.BASE_URL}/")
        self.page.wait_for_load_state("networkidle")
        
        # 搜索
        self.page.fill('input[placeholder*="搜索"]', patent_number)
        self.page.click('button:has-text("检索")')
        
        self.page.wait_for_load_state("networkidle")
        print(f"🔍 搜索完成: {patent_number}")
    
    def download_pdf(self, patent_number: str, output_dir: str = ".") -> str:
        """下载 PDF"""
        self.search(patent_number)
        
        # 等待搜索结果
        self.page.wait_for_timeout(2000)
        
        # 点击第一个搜索结果进入详情页
        try:
            # 点击专利标题
            self.page.click('a[href*="/detail?aid="]')
            self.page.wait_for_load_state("networkidle")
        except Exception as e:
            print(f"⚠️ 点击专利标题失败: {e}")
        
        # 点击 PDF 下载按钮
        try:
            self.page.wait_for_timeout(1000)
            # 尝试点击 PDF 下载按钮
            pdf_btn = self.page.locator('text=PDF下载, text=pdf下载').first
            if pdf_btn.is_visible():
                pdf_btn.click()
                print("📥 点击了 PDF 下载按钮")
                self.page.wait_for_timeout(2000)
        except Exception as e:
            print(f"⚠️ 点击 PDF 下载失败: {e}")

        print(f"ℹ️ 度衍浏览器流程已走完（登录→搜索→点PDF），但本模块未监听 download 事件保存文件。")
        print(f"   如需确定可用的 PDF 下载，推荐改用 Google Patents：python cli.py google {patent_number}")
        return None
    
    def get_cookies(self) -> str:
        """获取 cookies"""
        cookies = self.context.cookies()
        return json.dumps(cookies)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="度衍专利 (uyanip) 专利下载")
    parser.add_argument("patents", nargs="+", help="专利号列表")
    _creds = load_creds("uyanip")
    parser.add_argument("--username", "-u", default=_creds.get("username"))
    parser.add_argument("--password", "-p", default=_creds.get("password"))
    parser.add_argument("--output", "-o", default=".")
    parser.add_argument("--method", "-m", choices=["api", "browser"], default="browser")
    parser.add_argument("--headless", action="store_true")
    
    args = parser.parse_args()
    
    if args.method == "api":
        print("⚠️ API 方式待研究，请使用浏览器方式")
        return
    
    downloader = UyanipBrowser(args.headless)
    
    try:
        downloader.start()
        downloader.login(args.username, args.password)
        
        for patent in args.patents:
            print(f"\n🔍 处理: {patent}")
            downloader.download_pdf(patent, args.output)
    
    finally:
        downloader.close()


if __name__ == "__main__":
    main()
