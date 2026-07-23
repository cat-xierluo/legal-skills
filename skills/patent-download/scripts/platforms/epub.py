#!/usr/bin/env python3
"""
⚠️ 实验性（PDF 下载未实现）：站点有验证码+强反爬，本模块仅完成搜索+点击流程，未保存文件。
epub 平台的相对完整 Playwright 实现见 scripts/download.py（旧入口，cli.py 统一架构下的占位）。

国家知识产权局专利公布公告系统 专利下载
无需登录，但有反爬机制
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

# 配置
CONFIG = {
    "name": "专利公布公告系统",
    "base_url": "http://epub.cnipa.gov.cn",
    "need_login": False,
}


class EpubAPI:
    """API 方式 - 有强反爬，建议用浏览器"""
    
    def __init__(self, cookies: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": CONFIG["base_url"],
        })
        if cookies:
            self.session.cookies.update(json.loads(cookies))
    
    def search(self, patent_number: str) -> Dict:
        """搜索专利 - 返回混淆的 JS，需要浏览器"""
        url = f"{CONFIG['base_url']}/cnipa-patent-search-searchService/search"
        data = {"keyword": patent_number, "pageNum": 1, "pageSize": 10}
        
        try:
            response = self.session.post(url, json=data)
            return {"status": "blocked", "response": response.text[:500]}
        except Exception as e:
            return {"status": "error", "message": str(e)}


class EpubBrowser:
    """浏览器方式 - 推荐"""
    
    BASE_URL = "http://epub.cnipa.gov.cn"
    
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
    
    def search(self, patent_number: str):
        """搜索专利"""
        self.page.goto(f"{self.BASE_URL}/Index")
        self.page.wait_for_load_state("networkidle")
        
        # 搜索
        self.page.fill('input[placeholder*="申请号"], input[type="text"]', patent_number)
        self.page.click('button:has-text("查询")')
        
        self.page.wait_for_load_state("networkidle")
        print(f"🔍 搜索完成: {patent_number}")
    
    def download_pdf(self, patent_number: str, output_dir: str = ".") -> str:
        """下载 PDF（实验性：当前未实现真正的文件保存）"""
        self.search(patent_number)

        # 点击搜索结果
        try:
            self.page.click('.result-item a, h1 a, a[href*="patent"]')
            self.page.wait_for_load_state("networkidle")
        except:
            pass

        # 点击"专利单行本"
        try:
            self.page.click('text=专利单行本, text=实用新型专利, text=发明专利')
            self.page.wait_for_load_state("networkidle")
        except:
            pass

        # 点击下载按钮
        try:
            # 等待下载按钮出现
            self.page.wait_for_timeout(2000)

            # 尝试点击打包下载或查看PDF
            self.page.click('text=打包下载, text=查看PDF', timeout=5000)
            self.page.wait_for_timeout(2000)
            print("📥 点击了下载按钮")
        except:
            pass

        # 注意：可能需要验证码

        print(f"⚠️ 专利公布公告系统有验证码+反爬，本模块未保存文件。")
        print(f"   epub 平台的相对完整实现见 scripts/download.py；或推荐改用 Google Patents：")
        print(f"   python cli.py google {patent_number}")
        return None


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="专利公布公告系统下载")
    parser.add_argument("patents", nargs="+", help="专利号列表")
    parser.add_argument("--output", "-o", default=".")
    parser.add_argument("--method", "-m", choices=["api", "browser"], default="browser")
    parser.add_argument("--headless", action="store_true")
    
    args = parser.parse_args()
    
    if args.method == "api":
        print("⚠️ API 方式有反爬，建议使用浏览器方式")
        client = EpubAPI()
        for patent in args.patents:
            result = client.search(patent)
            print(f"🔍 {patent}: {result}")
        return
    
    downloader = EpubBrowser(args.headless)
    
    try:
        downloader.start()
        
        for patent in args.patents:
            print(f"\n🔍 处理: {patent}")
            downloader.download_pdf(patent, args.output)
    
    finally:
        downloader.close()


if __name__ == "__main__":
    main()
