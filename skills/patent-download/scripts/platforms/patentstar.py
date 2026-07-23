#!/usr/bin/env python3
"""
⚠️ 实验性（API 已失效）：搜索接口返回 Ret=206 内部错误，所有查询格式均不可用。
仅作兼容保留。完整可用通道见 references/platform-status.md，推荐改用 Google Patents。

PatentStar (专利之星) 专利下载
支持 API 和浏览器两种方式
"""

import os
import sys
import json
import base64
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
    "name": "专利之星",
    "base_url": "https://cprs.patentstar.com.cn",
}


class PatentStarAPI:
    """API 方式"""
    
    def __init__(self, cookies: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": CONFIG["base_url"],
            "Content-Type": "application/json"
        })
        if cookies:
            self.session.cookies.update(json.loads(cookies))
    
    def login(self, username: str, password: str) -> Dict:
        """登录"""
        url = f"{CONFIG['base_url']}/Account/UserLogin"
        data = {"loginname": username, "password": password}
        response = self.session.post(url, json=data)
        return response.json()
    
    def search(self, patent_number: str, page: int = 1, rows: int = 10) -> Dict:
        """搜索专利"""
        query = f"{patent_number}/YY"
        encoded_query = base64.b64encode(query.encode()).decode()
        
        url = f"{CONFIG['base_url']}/Search/SearchByQuery"
        data = {
            "CurrentQuery": encoded_query,
            "DBType": "CN",
            "PageNum": page,
            "RowCount": rows
        }
        response = self.session.post(url, json=data)
        return response.json()
    
    def export(self, patent_numbers: List[str], output_dir: str = ".") -> str:
        """批量导出"""
        query = ";".join(patent_numbers)
        query_base64 = base64.b64encode(query.encode()).decode()
        
        url = f"{CONFIG['base_url']}/Download/BulkDownloadExcel"
        data = {
            "CurrentQuery": query_base64,
            "From": 1,
            "Size": len(patent_numbers)
        }
        response = self.session.post(url, json=data)
        
        filename = f"patentstar_{len(patent_numbers)}.xlsx"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "wb") as f:
            f.write(response.content)
        
        return filepath
    
    def get_cookies(self) -> str:
        return json.dumps(dict(self.session.cookies))


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="PatentStar 专利下载")
    parser.add_argument("patents", nargs="+", help="专利号列表")
    _creds = load_creds("patentstar")
    parser.add_argument("--username", "-u", default=_creds.get("username"))
    parser.add_argument("--password", "-p", default=_creds.get("password"))
    parser.add_argument("--output", "-o", default=".")
    parser.add_argument("--method", "-m", choices=["api", "browser"], default="api")
    
    args = parser.parse_args()
    
    if args.method == "api":
        client = PatentStarAPI()
        
        # 登录
        print("🔐 登录...")
        result = client.login(args.username, args.password)
        if result.get("Ret") == 200:
            print("✅ 登录成功")
        else:
            print(f"❌ 登录失败: {result}")
            return
        
        # 导出
        print(f"📦 导出 {len(args.patents)} 个专利...")
        filepath = client.export(args.patents, args.output)
        print(f"✅ 已导出: {filepath}")
        
        # 保存 cookies（不再打印到日志，避免 session 泄露）
        _cookies = client.get_cookies()
    
    else:
        print("🔧 浏览器方式需要使用单独的脚本")
        print(f"   python -m platforms.patentstar_browser ...")


if __name__ == "__main__":
    main()
