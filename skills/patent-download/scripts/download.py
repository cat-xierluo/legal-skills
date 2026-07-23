#!/usr/bin/env python3
"""
中国专利 PDF 下载工具 v2
使用 Playwright 从国家知识产权局下载专利 PDF

这是 epub（专利公布公告系统）平台的相对完整实现，由 patent-download.sh
在非 google 参数时作为旧入口调用。统一架构下对应的占位模块是
platforms/epub.py（仅流程演示，未保存文件），本文件才是可用实现。

使用方法:
    python download.py 2024214535561
    python download.py 2024214535561 2024222490312 -o ~/patents
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ 缺少依赖: playwright")
    print("   请运行: pip install -r scripts/requirements.txt")
    print("   并安装浏览器: playwright install chromium")
    raise SystemExit(1)


def download_patent(patent_number: str, output_dir: str = None) -> str:
    """
    下载专利 PDF
    
    Args:
        patent_number: 专利号（申请号/公告号）
        output_dir: 输出目录
    
    Returns:
        下载的文件路径，失败返回 None
    """
    if output_dir is None:
        output_dir = os.path.expanduser("~/Downloads/patent")
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    with sync_playwright() as p:
        # 启动无头浏览器
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        # 创建带有下载功能的 context
        context = browser.new_context()
        
        # 创建页面
        page = context.new_page()
        
        # 用于存储下载路径
        download_path = None
        
        # 监听下载事件
        def on_download(download):
            nonlocal download_path
            print(f"📥 检测到下载: {download.url}")
            download_path = download.path
        
        page.on("download", on_download)
        
        try:
            # ========== 步骤1: 搜索专利 ==========
            print(f"🔍 搜索专利: {patent_number}")
            page.goto("http://epub.cnipa.gov.cn/Index", timeout=30000)
            
            # 等待搜索框出现 - 使用更通用的选择器
            page.wait_for_selector('input[placeholder*="申请号" i], input[placeholder*="专利" i], input[type="text"]', timeout=10000)
            
            # 输入专利号并搜索
            page.fill('input[placeholder*="申请号" i]', patent_number)
            page.click('button:has-text("查询")')
            
            # 等待搜索结果
            page.wait_for_load_state("networkidle", timeout=15000)
            
            # 检查是否有搜索结果
            content = page.content()
            if "没有找到" in content or "无结果" in content:
                print(f"❌ 未找到专利: {patent_number}")
                return None
            
            # ========== 步骤2: 点击进入详情页 ==========
            # 尝试点击搜索结果中的专利标题或链接
            # 先尝试点击包含专利信息的区域
            try:
                # 点击第一个搜索结果的标题
                heading = page.locator("h1, h2").first
                if heading.is_visible():
                    heading.click()
                    print("✅ 进入专利详情页")
            except Exception as e:
                print(f"⚠️ 点击标题失败: {e}")
            
            page.wait_for_load_state("networkidle", timeout=15000)
            
            # 如果 URL 没变，尝试其他方式
            if "Index" in page.url and "patent" not in page.url:
                # 尝试直接通过申请号获取公告号
                # 从搜索结果中提取公告号
                try:
                    # 查找包含 CN 开头的链接
                    patent_link = page.locator('a[href*="patent/CN"]').first
                    if patent_link.is_visible():
                        patent_link.click()
                        print("✅ 点击专利链接进入详情")
                except:
                    pass
            
            page.wait_for_load_state("networkidle", timeout=15000)
            
            # ========== 步骤3: 获取专利信息 ==========
            title = "patent"
            try:
                # 尝试获取专利标题
                title_elem = page.locator("h2").first
                if title_elem.is_visible():
                    title = title_elem.text_content()
                    title = title.strip()[:50]
            except:
                pass
            
            # 清理文件名非法字符
            title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
            if not title:
                title = "patent"
            
            # ========== 步骤4: 点击"专利单行本"进入下载页 ==========
            # 尝试点击"专利单行本"链接
            dxb_clicked = False
            for link_text in ["专利单行本", "实用新型专利", "发明专利", "外观设计"]:
                try:
                    link = page.locator(f"text={link_text}").first
                    if link.is_visible():
                        link.click()
                        dxb_clicked = True
                        print(f"✅ 进入下载页: {link_text}")
                        break
                except:
                    continue
            
            if not dxb_clicked:
                # 尝试直接从当前 URL 构造下载页 URL
                if "patent" in page.url:
                    # 从 URL 提取公告号，如 CN222853348U
                    patent_code = page.url.split("CN")[-1].split("/")[-1].split("?")[0]
                    if patent_code:
                        page.goto(f"http://epub.cnipa.gov.cn/Dxb/IndexQuery?patentCode=CN{patent_code}")
                        print("✅ 直接访问下载页")
            
            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(2000)  # 等待 JS 渲染
            
            # ========== 步骤5: 点击下载按钮 ==========
            # 尝试点击"打包下载"或"查看PDF"按钮
            download_clicked = False
            
            # 方法1: 尝试点击打包下载
            try:
                # 查找包含"打包下载"的元素
                download_btn = page.locator('button:has-text("打包下载"), a:has-text("打包下载")').first
                if download_btn.is_visible():
                    # 开始下载监听
                    with page.expect_download(timeout=30000) as download_info:
                        download_btn.click()
                    download = download_info.value
                    
                    # 保存文件
                    filename = f"{patent_number}_{title}.pdf"
                    filepath = os.path.join(output_dir, filename)
                    download.save_as(filepath)
                    print(f"✅ 下载成功: {filepath}")
                    browser.close()
                    return filepath
            except Exception as e:
                print(f"⚠️ 打包下载失败: {e}")
            
            # 方法2: 尝试点击查看PDF
            try:
                pdf_btn = page.locator('button:has-text("查看PDF"), a:has-text("查看PDF")').first
                if pdf_btn.is_visible():
                    with page.expect_download(timeout=30000) as download_info:
                        pdf_btn.click()
                    download = download_info.value
                    
                    filename = f"{patent_number}_{title}.pdf"
                    filepath = os.path.join(output_dir, filename)
                    download.save_as(filepath)
                    print(f"✅ 下载成功: {filepath}")
                    browser.close()
                    return filepath
            except Exception as e:
                print(f"⚠️ 查看PDF失败: {e}")
            
            # 方法3: 尝试查找 PDF 下载链接
            try:
                pdf_links = page.locator('a[href*=".pdf"]')
                if pdf_links.count() > 0:
                    pdf_url = pdf_links.first.get_attribute("href")
                    if pdf_url:
                        if not pdf_url.startswith("http"):
                            pdf_url = "http://epub.cnipa.gov.cn" + pdf_url
                        
                        # 使用 requests 下载
                        import requests
                        response = requests.get(pdf_url, timeout=30)
                        if response.status_code == 200:
                            filename = f"{patent_number}_{title}.pdf"
                            filepath = os.path.join(output_dir, filename)
                            with open(filepath, "wb") as f:
                                f.write(response.content)
                            print(f"✅ 下载成功: {filepath}")
                            browser.close()
                            return filepath
            except Exception as e:
                print(f"⚠️ PDF链接下载失败: {e}")
            
            print(f"❌ 未能找到下载按钮，请手动操作")
            # 保存页面用于调试
            debug_file = os.path.join(output_dir, f"{patent_number}_debug.html")
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(page.content())
            print(f"📝 已保存调试页面: {debug_file}")
            
            browser.close()
            return None
            
        except Exception as e:
            print(f"❌ 下载失败: {e}")
            import traceback
            traceback.print_exc()
            browser.close()
            return None


def main():
    parser = argparse.ArgumentParser(description="中国专利 PDF 下载工具 v2")
    parser.add_argument("patent_numbers", nargs="+", help="专利号列表")
    parser.add_argument("-o", "--output", default=None, help="输出目录")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    print("📥 专利下载工具 v2")
    print("=" * 50)
    
    for patent_num in args.patent_numbers:
        print(f"\n处理: {patent_num}")
        result = download_patent(patent_num, args.output)
        if result:
            print(f"✅ 已保存: {result}")
        else:
            print(f"❌ 失败: {patent_num}")
    
    print("\n" + "=" * 50)
    print("完成!")


if __name__ == "__main__":
    main()
