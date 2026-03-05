#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown 到 HTML 可视化报告转换工具

将 Markdown 文档转换为结构化、可视化的 HTML 报告
支持多种主题、打印样式、目录导航
"""

import os
import sys
import argparse
import re
from pathlib import Path
from datetime import datetime

import markdown
from bs4 import BeautifulSoup

# 获取脚本所在目录
SCRIPT_DIR = Path(__file__).parent.absolute()
ASSETS_DIR = SCRIPT_DIR.parent / "assets"
THEMES_DIR = ASSETS_DIR / "themes"
TEMPLATES_DIR = ASSETS_DIR / "templates"


# ============================================================================
# 核心转换类
# ============================================================================

class MarkdownToHTMLConverter:
    """Markdown 转 HTML 转换器"""
    
    def __init__(self, theme="legal", toc=False, print_style=True, inline=False):
        self.theme = theme
        self.toc = toc
        self.print_style = print_style
        self.inline = inline
        self.md = markdown.Markdown(
            extensions=[
                'tables',
                'fenced_code',
                'toc',
                'nl2br',
                'sane_lists',
                'codehilite',
            ]
        )
    
    def convert(self, md_content: str, title: str = None) -> str:
        """
        转换 Markdown 为 HTML
        
        Args:
            md_content: Markdown 内容
            title: 页面标题（可选，默认从内容提取）
        
        Returns:
            完整的 HTML 字符串
        """
        # 转换 Markdown 为 HTML
        html_body = self.md.convert(md_content)
        
        # 提取标题
        if not title:
            title = self._extract_title(md_content) or "文档"
        
        # 解析 HTML，进行增强处理
        soup = BeautifulSoup(html_body, 'html.parser')
        soup = self._enhance_html(soup)
        
        # 生成目录
        toc_html = ""
        if self.toc:
            toc_html = self._generate_toc(soup)
        
        # 加载主题 CSS
        theme_css = self._load_theme_css()
        
        # 生成完整 HTML
        full_html = self._generate_full_html(
            title=title,
            body=str(soup),
            toc=toc_html,
            theme_css=theme_css
        )
        
        return full_html
    
    def _extract_title(self, md_content: str) -> str:
        """从 Markdown 内容提取标题"""
        # 查找第一个 # 标题
        match = re.search(r'^#\s+(.+)$', md_content, re.MULTILINE)
        if match:
            # 移除可能的链接等
            title = match.group(1)
            title = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', title)
            return title.strip()
        return "文档"
    
    def _enhance_html(self, soup: BeautifulSoup) -> BeautifulSoup:
        """增强 HTML 结构"""
        
        # 1. 表格增强
        for table in soup.find_all('table'):
            table['class'] = table.get('class', []) + ['enhanced-table']
            # 添加斑马纹
            for i, row in enumerate(table.find_all('tr')):
                if i % 2 == 1:
                    row['class'] = row.get('class', []) + ['zebra-row']
        
        # 2. 引用块增强（识别法条引用）
        for blockquote in soup.find_all('blockquote'):
            text = blockquote.get_text()
            if re.search(r'《.+》第.+条', text):
                blockquote['class'] = blockquote.get('class', []) + ['law-quote']
        
        # 3. 代码块增强
        for pre in soup.find_all('pre'):
            pre['class'] = pre.get('class', []) + ['code-block']
        
        # 4. 标题 ID（用于目录跳转）
        for i in range(1, 7):
            for heading in soup.find_all(f'h{i}'):
                if not heading.get('id'):
                    # 生成 ID
                    heading_text = heading.get_text()
                    heading_id = re.sub(r'[^\w\u4e00-\u9fff]+', '-', heading_text)
                    heading_id = heading_id.strip('-').lower()[:50]
                    heading['id'] = heading_id
        
        # 5. 识别案件信息卡片
        soup = self._detect_case_card(soup)
        
        # 6. 识别争议焦点
        soup = self._detect_focus_points(soup)
        
        return soup
    
    def _detect_case_card(self, soup: BeautifulSoup) -> BeautifulSoup:
        """检测并增强案件信息卡片"""
        # 查找包含"案号"的表格
        for table in soup.find_all('table'):
            text = table.get_text()
            if '案号' in text or '案由' in text:
                table['class'] = table.get('class', []) + ['case-info-table']
        return soup
    
    def _detect_focus_points(self, soup: BeautifulSoup) -> BeautifulSoup:
        """检测并增强争议焦点"""
        # 查找包含"争议焦点"的标题
        for heading in soup.find_all(['h2', 'h3', 'h4']):
            if '争议焦点' in heading.get_text():
                heading['class'] = heading.get('class', []) + ['focus-heading']
        return soup
    
    def _generate_toc(self, soup: BeautifulSoup) -> str:
        """生成目录 HTML"""
        toc_items = []
        
        for heading in soup.find_all(['h1', 'h2', 'h3']):
            level = int(heading.name[1])
            title = heading.get_text()
            heading_id = heading.get('id', '')
            
            if heading_id:
                toc_items.append({
                    'level': level,
                    'title': title,
                    'id': heading_id
                })
        
        if not toc_items:
            return ""
        
        toc_html = '<nav class="toc">\n<h3>目录</h3>\n<ul>\n'
        for item in toc_items:
            indent = (item['level'] - 1) * 20
            toc_html += f'<li style="margin-left: {indent}px;"><a href="#{item["id"]}">{item["title"]}</a></li>\n'
        toc_html += '</ul>\n</nav>\n'
        
        return toc_html
    
    def _load_theme_css(self) -> str:
        """加载主题 CSS"""
        theme_file = THEMES_DIR / f"{self.theme}.css"
        
        if not theme_file.exists():
            # 降级到默认主题
            theme_file = THEMES_DIR / "legal.css"
        
        if theme_file.exists():
            with open(theme_file, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            # 返回内置基础样式
            return self._get_default_css()
    
    def _get_default_css(self) -> str:
        """获取默认 CSS 样式"""
        return """
/* 基础样式 */
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height: 1.8;
    color: #333;
    max-width: 900px;
    margin: 0 auto;
    padding: 40px 20px;
}

h1, h2, h3, h4, h5, h6 {
    margin-top: 1.5em;
    margin-bottom: 0.5em;
    font-weight: bold;
}

h1 { font-size: 1.8em; }
h2 { font-size: 1.5em; }
h3 { font-size: 1.2em; }

table {
    width: 100%;
    border-collapse: collapse;
    margin: 1em 0;
}

th, td {
    border: 1px solid #ddd;
    padding: 8px 12px;
    text-align: left;
}

th {
    background-color: #f5f5f5;
    font-weight: bold;
}

.zebra-row {
    background-color: #fafafa;
}

blockquote {
    border-left: 4px solid #007bff;
    padding-left: 1em;
    margin: 1em 0;
    color: #666;
}

.law-quote {
    background-color: #f8f9fa;
    padding: 1em;
    border-radius: 4px;
}

/* 目录样式 */
.toc {
    position: fixed;
    right: 20px;
    top: 20px;
    width: 250px;
    background: #f8f9fa;
    padding: 20px;
    border-radius: 8px;
    font-size: 0.9em;
    max-height: 80vh;
    overflow-y: auto;
}

.toc h3 {
    margin-top: 0;
    font-size: 1.1em;
}

.toc ul {
    list-style: none;
    padding-left: 0;
}

.toc a {
    color: #333;
    text-decoration: none;
}

.toc a:hover {
    color: #007bff;
}

/* 打印样式 */
@media print {
    .toc {
        display: none;
    }
    
    body {
        max-width: 100%;
        padding: 0;
    }
    
    .page-break {
        page-break-before: always;
    }
}
"""
    
    def _generate_full_html(self, title: str, body: str, toc: str, theme_css: str) -> str:
        """生成完整的 HTML 文档"""
        
        print_style_block = ""
        if self.print_style:
            print_style_block = """
<style media="print">
.toc { display: none; }
body { max-width: 100%; padding: 20mm; }
.page-break { page-break-before: always; }
</style>
"""
        
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
{theme_css}
    </style>
{print_style_block}
</head>
<body>
{toc}
<article class="content">
{body}
</article>
<footer class="document-footer">
    <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</footer>
</body>
</html>"""
        
        return html


# ============================================================================
# 文件处理
# ============================================================================

def process_file(input_path: str, output_path: str = None, **kwargs) -> str:
    """
    处理单个文件
    
    Args:
        input_path: 输入 Markdown 文件路径
        output_path: 输出 HTML 文件路径（可选）
        **kwargs: 转换器参数
    
    Returns:
        输出文件路径
    """
    # 读取输入文件
    with open(input_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # 确定输出路径
    if not output_path:
        input_file = Path(input_path)
        output_path = str(input_file.with_suffix('.html'))
    
    # 转换
    converter = MarkdownToHTMLConverter(**kwargs)
    html_content = converter.convert(md_content)
    
    # 写入输出文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ 转换完成: {input_path} → {output_path}")
    return output_path


def process_batch(input_pattern: str, output_dir: str = None, **kwargs):
    """批量处理文件"""
    import glob
    
    files = glob.glob(input_pattern)
    
    if not files:
        print(f"❌ 未找到匹配的文件: {input_pattern}")
        return
    
    print(f"📄 找到 {len(files)} 个文件")
    
    for input_path in files:
        output_path = None
        if output_dir:
            input_file = Path(input_path)
            output_path = str(Path(output_dir) / input_file.with_suffix('.html').name)
        
        try:
            process_file(input_path, output_path, **kwargs)
        except Exception as e:
            print(f"❌ 处理失败 {input_path}: {e}")


# ============================================================================
# 命令行入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Markdown 转 HTML 可视化报告',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本转换
  python md2html.py report.md
  
  # 指定输出路径
  python md2html.py report.md -o output.html
  
  # 使用主题
  python md2html.py report.md --theme=academic
  
  # 启用目录
  python md2html.py report.md --toc
  
  # 批量转换
  python md2html.py *.md --output-dir=./html/
        """
    )
    
    parser.add_argument('input', help='输入 Markdown 文件（支持通配符）')
    parser.add_argument('-o', '--output', help='输出 HTML 文件路径')
    parser.add_argument('--output-dir', help='批量转换时的输出目录')
    parser.add_argument('--theme', default='legal', 
                        choices=['legal', 'academic', 'minimal'],
                        help='主题样式（默认: legal）')
    parser.add_argument('--toc', action='store_true', help='生成目录导航')
    parser.add_argument('--no-print-style', action='store_true', help='禁用打印样式')
    parser.add_argument('--inline', action='store_true', help='内联所有资源')
    
    args = parser.parse_args()
    
    kwargs = {
        'theme': args.theme,
        'toc': args.toc,
        'print_style': not args.no_print_style,
        'inline': args.inline
    }
    
    # 判断是批量还是单文件
    if '*' in args.input or args.output_dir:
        process_batch(args.input, args.output_dir, **kwargs)
    else:
        process_file(args.input, args.output, **kwargs)


if __name__ == '__main__':
    main()
