#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音图文笔记下载器

下载抖音图文笔记中的所有图片。

使用方法:
    python download_douyin_note.py "<url>" [--out-dir <directory>]

示例:
    python download_douyin_note.py "https://v.douyin.com/xxx/"
    python download_douyin_note.py "https://www.douyin.com/note/xxx/" --out-dir ~/Downloads/douyin
"""

import argparse
import os
import re
import json
import requests
from pathlib import Path
from urllib.parse import urlparse, unquote

SCRIPT_DIR = Path(__file__).parent.parent
DEFAULT_OUT_DIR = SCRIPT_DIR / "downloads" / "douyin_notes"

# 请求头
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.38',
    'Referer': 'https://www.douyin.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}


def expand_short_url(url: str) -> str:
    """展开短链接"""
    try:
        resp = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=10)
        return resp.url
    except:
        return url


def extract_note_id(url: str) -> str:
    """从 URL 中提取笔记 ID"""
    # 展开短链接
    full_url = expand_short_url(url)
    
    # 匹配各种格式的笔记 ID
    patterns = [
        r'/note/(\d+)',
        r'/share/note/(\d+)',
        r'modal_id=(\d+)',
        r'/video/(\d+)',  # 有些图文笔记也可能是 video 格式
    ]
    
    for pattern in patterns:
        match = re.search(pattern, full_url)
        if match:
            return match.group(1)
    
    return None


def get_note_data(note_id: str) -> dict:
    """获取笔记数据（通过模拟 API 请求）"""
    # 尝试通过移动端 API 获取数据
    api_url = f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={note_id}"
    
    try:
        resp = requests.get(api_url, headers=HEADERS, timeout=10)
        data = resp.json()
        
        if data.get('status_code') == 0:
            return data.get('item_list', [{}])[0]
    except Exception as e:
        print(f"[warning] API 请求失败: {e}")
    
    return None


def extract_images_from_html(url: str) -> list:
    """从 HTML 页面提取图片 URL"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        html = resp.text
        
        # 尝试从页面中提取图片数据
        # 抖音页面中通常有 <script>__RENDER_DATA__=xxx</script>
        match = re.search(r'__RENDER_DATA__\s*=\s*([^<]+)</script>', html)
        if match:
            try:
                render_data = json.loads(unquote(match.group(1)))
                # 解析 render_data 获取图片列表
                # 这里需要根据实际数据结构调整
                images = []
                
                # 尝试不同的数据路径
                paths = [
                    ('app', 'video', 'images'),
                    ('app', 'aweme', 'detail', 'aweme', 'images'),
                    ('aweme_detail', 'images'),
                ]
                
                for path in paths:
                    data = render_data
                    for key in path:
                        if isinstance(data, dict) and key in data:
                            data = data[key]
                        else:
                            data = None
                            break
                    
                    if data and isinstance(data, list):
                        for img in data:
                            if isinstance(img, dict):
                                url_list = img.get('url_list', [])
                                if url_list:
                                    images.append(url_list[0])
                            elif isinstance(img, str):
                                images.append(img)
                
                if images:
                    return images
            except json.JSONDecodeError:
                pass
        
        # 备用：直接匹配图片 URL
        img_pattern = r'https?://[^"\'>\s]+\.(?:jpg|jpeg|png|webp|heic)'
        images = list(set(re.findall(img_pattern, html)))
        
        # 过滤掉头像等非内容图片
        images = [img for img in images if 'p26-' in img or 'p3-' in img or 'p9-' in img]
        
        return images[:20]  # 最多返回 20 张
        
    except Exception as e:
        print(f"[error] 提取图片失败: {e}")
        return []


def download_images(images: list, out_dir: Path, title: str = "douyin_note") -> list:
    """下载所有图片"""
    downloaded = []
    
    # 清理标题
    safe_title = re.sub(r'[^\w\s-]', '', title)[:50]
    safe_title = re.sub(r'[-\s]+', '_', safe_title)
    
    for i, img_url in enumerate(images, 1):
        try:
            # 确定扩展名
            ext = '.jpg'
            if '.png' in img_url:
                ext = '.png'
            elif '.webp' in img_url:
                ext = '.webp'
            elif '.heic' in img_url:
                ext = '.heic'
            
            # 下载图片
            resp = requests.get(img_url, headers=HEADERS, timeout=30)
            
            if resp.status_code == 200:
                filename = f"{safe_title}_{i:02d}{ext}"
                filepath = out_dir / filename
                
                with open(filepath, 'wb') as f:
                    f.write(resp.content)
                
                downloaded.append(str(filepath))
                print(f"[downloaded] {filename}")
            else:
                print(f"[warning] 图片 {i} 下载失败: HTTP {resp.status_code}")
                
        except Exception as e:
            print(f"[warning] 图片 {i} 下载失败: {e}")
    
    return downloaded


def main():
    parser = argparse.ArgumentParser(description='抖音图文笔记下载器')
    parser.add_argument('url', help='抖音图文笔记链接')
    parser.add_argument('--out-dir', default=str(DEFAULT_OUT_DIR), help='输出目录')
    parser.add_argument('--title', default='', help='自定义标题')
    
    args = parser.parse_args()
    
    # 创建输出目录
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    
    url = args.url
    print(f"[info] 处理链接: {url}")
    
    # 展开短链接
    full_url = expand_short_url(url)
    print(f"[info] 完整链接: {full_url}")
    
    # 检查是否是图文笔记
    if '/note/' not in full_url and '/share/note/' not in full_url:
        print("[warning] 这可能不是图文笔记链接，可能需要使用 universal-media-downloader 处理视频")
    
    # 提取图片
    print("[info] 正在提取图片...")
    images = extract_images_from_html(full_url)
    
    if not images:
        print("[error] 未能提取到任何图片")
        print("[提示] 可以尝试：")
        print("  1. 手动打开链接截图保存")
        print("  2. 使用浏览器开发者工具查看图片 URL")
        return 1
    
    print(f"[info] 找到 {len(images)} 张图片")
    
    # 下载图片
    print("[info] 开始下载...")
    title = args.title or "douyin_note"
    downloaded = download_images(images, out_dir, title)
    
    print(f"\n[完成] 成功下载 {len(downloaded)} 张图片到: {out_dir}")
    
    # 输出文件路径（供 AI 读取）
    for path in downloaded:
        print(f"SAVED_FILEPATH={path}")
    
    return 0


if __name__ == '__main__':
    exit(main())
