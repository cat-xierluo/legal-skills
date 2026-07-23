#!/usr/bin/env python3
"""
⚠️ 实验性（PDF 下载未实现）：仅完成登录+搜索流程，详情页有验证码未处理，未保存任何文件。
完整可用通道见 references/platform-status.md，推荐改用 Google Patents。

PatentStar (专利之星) 浏览器自动化版本
"""

import os
from playwright.sync_api import sync_playwright

try:
    from platforms._creds import load_creds
except Exception:
    def load_creds(_platform):
        return {}


class PatentStarBrowser:
    """浏览器方式"""
    
    BASE_URL = "https://cprs.patentstar.com.cn"
    
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.browser = None
        self.page = None
    
    def start(self):
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
        self.page.goto(f"{self.BASE_URL}/Account/Login")
        self.page.wait_for_load_state("networkidle")
        
        # 填写登录表单
        self.page.fill('input[name="loginname"], input[id="username"]', username)
        self.page.fill('input[name="password"], input[id="password"]', password)
        self.page.click('button:has-text("登录")')
        
        self.page.wait_for_load_state("networkidle")
        print("✅ 登录成功")
    
    def search(self, patent_number: str):
        """搜索专利"""
        self.page.goto(f"{self.BASE_URL}/Search/Index")
        self.page.wait_for_load_state("networkidle")
        
        # 搜索
        self.page.fill('input[placeholder*="请输入"], input[type="text"]', patent_number)
        self.page.click('button:has-text("检索")')
        
        self.page.wait_for_load_state("networkidle")
        print(f"🔍 搜索完成: {patent_number}")
    
    def download_pdf(self, patent_number: str, output_dir: str = ".") -> str:
        """下载 PDF（实验性：当前未实现真正的文件保存）"""
        self.search(patent_number)

        # 尝试点击详情页
        try:
            self.page.click('.result-item a, h1 a, a[href*="Detail"]')
            self.page.wait_for_load_state("networkidle")
        except:
            pass

        # 注意：详情页可能需要验证码
        # 这里只是演示流程，实际需要处理验证码

        print(f"⚠️ PatentStar 浏览器下载尚未实现（详情页有验证码），未保存文件。推荐改用 Google Patents：")
        print(f"   python cli.py google {patent_number}")
        return None


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="PatentStar 浏览器下载")
    parser.add_argument("patents", nargs="+", help="专利号列表")
    _creds = load_creds("patentstar")
    parser.add_argument("--username", "-u", default=_creds.get("username"))
    parser.add_argument("--password", "-p", default=_creds.get("password"))
    parser.add_argument("--output", "-o", default=".")
    parser.add_argument("--headless", action="store_true")
    
    args = parser.parse_args()
    
    downloader = PatentStarBrowser(args.headless)
    
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
