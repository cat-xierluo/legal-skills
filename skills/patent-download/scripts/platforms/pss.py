#!/usr/bin/env python3
"""
⚠️ 实验性（PDF 下载未实现）：本模块仅完成搜索+进入详情，未实现真正的 PDF 保存。
完整可用通道见 references/platform-status.md，推荐改用 Google Patents。

PSS 国家知识产权局专利检索系统 专利下载
账号通过环境变量配置（见 config/.env.example），不在脚本里硬编码。
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
    "name": "PSS专利检索系统",
    "base_url": "https://pss-system.cponline.cnipa.gov.cn",
}


class PSSAPI:
    """API 方式 - 待研究"""
    
    def __init__(self, cookies: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": CONFIG["base_url"],
        })
        if cookies:
            self.session.cookies.update(json.loads(cookies))
    
    def search(self, patent_number: str) -> Dict:
        """搜索专利 - 需要研究具体 API"""
        # TODO: 研究具体 API
        return {"status": "not_implemented", "message": "API 待研究"}


class PSSBrowser:
    """浏览器方式"""
    
    BASE_URL = "https://pss-system.cponline.cnipa.gov.cn"
    
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
        
        # 点击登录按钮
        self.page.click('a:has-text("登录"), button:has-text("登录")')
        self.page.wait_for_load_state("networkidle")
        
        # 填写登录表单
        self.page.fill('input[name="username"], input[id="username"]', username)
        self.page.fill('input[name="password"], input[id="password"]', password)
        self.page.click('button:has-text("登录")')
        
        self.page.wait_for_load_state("networkidle")
        print("✅ 登录成功")
    
    def search(self, patent_number: str):
        """搜索专利"""
        self.page.goto(f"{self.BASE_URL}/conventionalSearch")
        self.page.wait_for_load_state("networkidle")
        
        # 选择数据范围（中国）
        try:
            self.page.click('text=数据范围')
            self.page.click('text=中国')
        except:
            pass
        
        # 搜索
        self.page.fill('input[placeholder*="请输入"]', patent_number)
        self.page.click('button:has-text("检索")')
        
        self.page.wait_for_load_state("networkidle")
        print(f"🔍 搜索完成: {patent_number}")
    
    def download_pdf(self, patent_number: str, output_dir: str = ".") -> str:
        """下载 PDF（实验性：当前未实现真正的文件保存）"""
        self.search(patent_number)

        # 尝试点击详情
        try:
            self.page.click('.result-item a, a[href*="detail"], h1 a')
            self.page.wait_for_load_state("networkidle")
        except:
            pass

        print(f"⚠️ PSS 平台 PDF 下载尚未实现，未保存文件。推荐改用 Google Patents：")
        print(f"   python cli.py google {patent_number}")
        return None


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="PSS专利检索系统下载")
    parser.add_argument("patents", nargs="+", help="专利号列表")
    _creds = load_creds("pss")
    parser.add_argument("--username", "-u", default=_creds.get("username"))
    parser.add_argument("--password", "-p", default=_creds.get("password"))
    parser.add_argument("--output", "-o", default=".")
    parser.add_argument("--method", "-m", choices=["api", "browser"], default="browser")
    parser.add_argument("--headless", action="store_true")
    
    args = parser.parse_args()
    
    if args.method == "api":
        print("⚠️ API 方式待研究，请使用浏览器方式")
        return
    
    downloader = PSSBrowser(args.headless)
    
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
