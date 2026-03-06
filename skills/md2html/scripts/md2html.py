#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown 到 HTML 法律文书可视化报告转换工具 v2.0

核心特性：
- 智能文档类型识别
- 基于内容的结构化渲染
- 专业法律文书视觉风格
"""

import os
import sys
import argparse
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

import markdown
from bs4 import BeautifulSoup, Tag

# 获取脚本所在目录
SCRIPT_DIR = Path(__file__).parent.absolute()
ASSETS_DIR = SCRIPT_DIR.parent / "assets"
THEMES_DIR = ASSETS_DIR / "themes"


# ============================================================================
# 文档类型识别
# ============================================================================

class DocumentTypeDetector:
    """文档类型识别器"""
    
    # 类型定义：模式 -> 类型
    TYPE_PATTERNS = {
        'judgment_internal': {
            'keywords': ['争议焦点', '法院认定', '证据认定', '判决主文', '上诉可行性'],
            'required': 2,
            'weight': {'争议焦点': 3, '法院认定': 3, '证据认定': 2}
        },
        'judgment_client': {
            'keywords': ['案件核心问题', '行动建议', '立即行动', '案件进展', '费用预估'],
            'required': 2,
            'weight': {'案件核心问题': 3, '行动建议': 3, '立即行动': 2}
        },
        'judgment_research': {
            'keywords': ['法律问题', '研究课题', '类似案例', '裁判要点', '实务启示'],
            'required': 2,
            'weight': {'法律问题': 3, '研究课题': 3, '类似案例': 2}
        },
        'legal_opinion': {
            'keywords': ['法律分析', '风险评估', '法律依据', '建议', '结论'],
            'required': 2,
            'weight': {'法律分析': 3, '风险评估': 3, '法律依据': 2}
        }
    }
    
    @classmethod
    def detect(cls, md_content: str) -> str:
        """
        自动检测文档类型
        
        Args:
            md_content: Markdown 内容
        
        Returns:
            文档类型字符串
        """
        # 统计关键词出现次数
        scores = {}
        
        for doc_type, config in cls.TYPE_PATTERNS.items():
            score = 0
            for keyword in config['keywords']:
                count = md_content.count(keyword)
                weight = config['weight'].get(keyword, 1)
                score += count * weight
            
            # 检查必需关键词
            required_found = sum(1 for k in config['keywords'][:config['required']] 
                              if k in md_content)
            if required_found < config['required']:
                continue
                
            scores[doc_type] = score
        
        # 返回最高分的类型
        if scores:
            return max(scores, key=scores.get)
        
        return 'general'
    
    @classmethod
    def get_type_display_name(cls, doc_type: str) -> str:
        """获取类型的显示名称"""
        names = {
            'judgment_internal': '判决书分析（内部版）',
            'judgment_client': '案件简报（客户版）',
            'judgment_research': '判决研究（研究版）',
            'legal_opinion': '法律意见书',
            'general': '文档'
        }
        return names.get(doc_type, '文档')


# ============================================================================
# 内容结构解析
# ============================================================================

class ContentStructureParser:
    """内容结构解析器"""
    
    def __init__(self, soup: BeautifulSoup, md_content: str):
        self.soup = soup
        self.md_content = md_content
        self.structure = {}
    
    def parse(self) -> Dict:
        """解析内容结构"""
        self.structure = {
            'title': self._extract_title(),
            'case_info': self._extract_case_info(),
            'key_points': self._extract_key_points(),
            'dispute_focus': self._extract_dispute_focus(),
            'evidence': self._extract_evidence(),
            'timeline': self._extract_timeline(),
            'action_items': self._extract_action_items(),
            'conclusions': self._extract_conclusions()
        }
        return self.structure
    
    def _extract_title(self) -> Optional[str]:
        """提取文档标题"""
        h1 = self.soup.find('h1')
        return h1.get_text(strip=True) if h1 else None
    
    def _extract_case_info(self) -> List[Dict]:
        """提取案件信息表格"""
        case_info = []
        for table in self.soup.find_all('table'):
            text = table.get_text()
            if '案号' in text or '案由' in text or '法院' in text:
                rows = []
                for tr in table.find_all('tr'):
                    cells = [c.get_text(strip=True) for c in tr.find_all(['th', 'td'])]
                    if len(cells) >= 2:
                        rows.append({'key': cells[0], 'value': cells[1]})
                case_info.append(rows)
        return case_info
    
    def _extract_key_points(self) -> List[Dict]:
        """提取核心要点"""
        points = []
        
        # 查找包含"核心要点"、"关键"等的表格
        for h2 in self.soup.find_all('h2'):
            if any(k in h2.get_text() for k in ['要点', '概览', '速览']):
                # 找下一个表格
                next_sibling = h2.find_next_sibling()
                if next_sibling and next_sibling.name == 'table':
                    for tr in next_sibling.find_all('tr')[1:]:  # 跳过表头
                        cells = [c.get_text(strip=True) for c in tr.find_all('td')]
                        if len(cells) >= 2:
                            points.append({'label': cells[0], 'value': cells[1]})
        
        return points
    
    def _extract_dispute_focus(self) -> List[Dict]:
        """提取争议焦点"""
        focus_list = []
        
        for h2 in self.soup.find_all('h2'):
            if '争议焦点' in h2.get_text() or '焦点' in h2.get_text():
                # 查找后续内容
                for sibling in h2.find_next_siblings():
                    if sibling.name == 'h2':
                        break
                    if sibling.name in ['h3', 'h4']:
                        focus_item = {'title': sibling.get_text(strip=True)}
                        # 查找法院认定
                        court_text = sibling.get_text()
                        if '法院认定' in court_text or '⭐' in str(sibling):
                            focus_item['has_court_ruling'] = True
                        focus_list.append(focus_item)
        
        return focus_list
    
    def _extract_evidence(self) -> List[Dict]:
        """提取证据表格"""
        evidence_list = []
        
        for table in self.soup.find_all('table'):
            text = table.get_text()
            if '证据' in text and ('法院认定' in text or '证明目的' in text):
                headers = [th.get_text(strip=True) for th in table.find_all('th')]
                for tr in table.find_all('tr')[1:]:
                    cells = [c.get_text(strip=True) for c in tr.find_all('td')]
                    if len(cells) >= len(headers):
                        evidence_list.append(dict(zip(headers, cells)))
        
        return evidence_list
    
    def _extract_timeline(self) -> List[Dict]:
        """提取时间轴"""
        timeline = []
        
        for table in self.soup.find_all('table'):
            text = table.get_text()
            if '时间' in text and ('事件' in text or '日期' in text):
                for tr in table.find_all('tr')[1:]:
                    cells = [c.get_text(strip=True) for c in tr.find_all('td')]
                    if len(cells) >= 2:
                        timeline.append({'date': cells[0], 'event': cells[1]})
        
        return timeline
    
    def _extract_action_items(self) -> List[Dict]:
        """提取行动项"""
        actions = []
        
        # 查找包含"行动"、"建议"的列表
        for h2 in self.soup.find_all('h2'):
            if '行动' in h2.get_text() or '建议' in h2.get_text():
                # 查找后续的 ul/ol
                for sibling in h2.find_next_siblings():
                    if sibling.name in ['h2', 'h3']:
                        break
                    if sibling.name in ['ul', 'ol']:
                        for li in sibling.find_all('li'):
                            text = li.get_text(strip=True)
                            if text:
                                checked = 'x' in text.lower() or '✓' in text or '☑' in text
                                actions.append({'text': text, 'checked': checked})
        
        return actions
    
    def _extract_conclusions(self) -> List[str]:
        """提取结论"""
        conclusions = []
        
        for h2 in self.soup.find_all('h2'):
            if '结论' in h2.get_text():
                # 查找后续段落
                for sibling in h2.find_next_siblings():
                    if sibling.name == 'h2':
                        break
                    if sibling.name == 'p':
                        text = sibling.get_text(strip=True)
                        if text:
                            conclusions.append(text)
        
        return conclusions


# ============================================================================
# HTML 生成器
# ============================================================================

class LegalHTMLGenerator:
    """法律文书 HTML 生成器"""
    
    def __init__(self, doc_type: str = 'general'):
        self.doc_type = doc_type
    
    def generate(self, soup: BeautifulSoup, structure: Dict, title: str) -> str:
        """生成完整 HTML"""
        
        # 根据类型选择渲染方法
        if self.doc_type.startswith('judgment'):
            return self._generate_judgment(soup, structure, title)
        elif self.doc_type == 'legal_opinion':
            return self._generate_legal_opinion(soup, structure, title)
        else:
            return self._generate_general(soup, structure, title)
    
    def _generate_judgment(self, soup: BeautifulSoup, structure: Dict, title: str) -> str:
        """生成判决书分析 HTML"""
        
        # 获取案件信息
        case_info = structure.get('case_info', [])
        case_meta = {}
        if case_info and case_info[0]:
            for item in case_info[0]:
                case_meta[item['key']] = item['value']
        
        # 生成核心要点卡片 HTML
        key_points_html = ""
        if structure.get('key_points'):
            key_points_html = self._render_key_points(structure['key_points'])
        
        # 生成时间轴 HTML
        timeline_html = ""
        if structure.get('timeline'):
            timeline_html = self._render_timeline(structure['timeline'])
        
        # 获取原始 HTML 内容
        body_content = str(soup)
        
        # 使用专业法律文书样式
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
{self._get_legal_styles()}
    </style>
</head>
<body>
{self._get_pdf_button()}
{self._get_header(case_meta, title)}
{key_points_html}
{body_content}
{timeline_html}
{self._get_footer()}
</body>
</html>"""
        
        return html
    
    def _generate_general(self, soup: BeautifulSoup, structure: Dict, title: str) -> str:
        """生成通用文档 HTML"""
        body_content = str(soup)
        
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
{self._get_general_styles()}
    </style>
</head>
<body>
{self._get_pdf_button()}
{body_content}
{self._get_footer()}
</body>
</html>"""
        
        return html
    
    def _generate_legal_opinion(self, soup: BeautifulSoup, structure: Dict, title: str) -> str:
        """生成法律意见书 HTML"""
        return self._generate_general(soup, structure, title)
    
    def _render_key_points(self, points: List[Dict]) -> str:
        """渲染核心要点卡片"""
        if not points:
            return ""
        
        html = '<section class="key-points">\n'
        
        # 第一行：判决结果（最重要）
        result_point = None
        other_points = []
        for p in points:
            if '判决' in p.get('label', '') or '结果' in p.get('label', ''):
                result_point = p
            else:
                other_points.append(p)
        
        if result_point:
            html += f'''  <div class="key-point result">
    <div class="point-label">{result_point['label']}</div>
    <div class="point-value">{result_point['value']}</div>
  </div>\n'''
        
        # 其他要点
        if other_points:
            html += '  <div class="points-row">\n'
            for p in other_points:
                html += f'''  <div class="key-point">
    <div class="point-label">{p['label']}</div>
    <div class="point-value">{p['value']}</div>
  </div>\n'''
            html += '  </div>\n'
        
        html += '</section>\n'
        return html
    
    def _render_timeline(self, timeline: List[Dict]) -> str:
        """渲染时间轴"""
        if not timeline:
            return ""
        
        html = '<section class="timeline-section">\n  <h2>📅 案件时间轴</h2>\n  <div class="timeline">\n'
        
        for i, item in enumerate(timeline):
            html += f'''    <div class="timeline-item">
      <div class="timeline-dot"></div>
      <div class="timeline-date">{item['date']}</div>
      <div class="timeline-content">{item['event']}</div>
    </div>\n'''
        
        html += '  </div>\n</section>\n'
        return html
    
    def _get_header(self, case_meta: Dict, title: str) -> str:
        """生成头部"""
        case_type = DocumentTypeDetector.get_type_display_name(self.doc_type)
        
        html = f'''<header class="doc-header">
  <div class="doc-badge">{case_type}</div>
  <h1>{title}</h1>
  <div class="case-meta">'''
        
        if case_meta.get('案号'):
            html += f'<span class="meta-item"><span class="meta-label">案号</span>{case_meta["案号"]}</span>'
        if case_meta.get('法院'):
            html += f'<span class="meta-item"><span class="meta-label">法院</span>{case_meta["法院"]}</span>'
        if case_meta.get('裁判日期'):
            html += f'<span class="meta-item"><span class="meta-label">裁判日期</span>{case_meta["裁判日期"]}</span>'
        
        html += '''</div>
</header>
'''
        return html
    
    def _get_pdf_button(self) -> str:
        """获取 PDF 按钮"""
        return '''
<div class="pdf-action-btn" id="pdfBtn">
    <button onclick="saveAsPDF()" title="保存为 PDF">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="12" y1="18" x2="12" y2="12"></line>
            <line x1="9" y1="15" x2="15" y2="15"></line>
        </svg>
    </button>
</div>

<script>
function saveAsPDF() { window.print(); }
</script>

<style>
.pdf-action-btn {
    position: fixed;
    bottom: 30px;
    right: 30px;
    z-index: 1000;
}
.pdf-action-btn button {
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
    color: white;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 15px rgba(30, 58, 95, 0.4);
    transition: all 0.3s ease;
}
.pdf-action-btn button:hover {
    transform: translateY(-3px);
    box-shadow: 0 6px 20px rgba(30, 58, 95, 0.6);
}
@media print {
    .pdf-action-btn { display: none !important; }
}
@media (max-width: 768px) {
    .pdf-action-btn { bottom: 20px; right: 20px; }
}
</style>'''
    
    def _get_footer(self) -> str:
        """获取页脚"""
        return f'''<footer class="doc-footer">
    <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · 法律文书可视化</p>
</footer>'''
    
    def _get_legal_styles(self) -> str:
        """获取法律文书专业样式"""
        return '''
/* ===== 法律文书专业样式 ===== */
:root {
    --primary: #1e3a5f;
    --primary-light: #2d5a87;
    --accent: #e67e22;
    --text: #2c3e50;
    --text-light: #7f8c8d;
    --bg: #f8f9fa;
    --bg-white: #ffffff;
    --success: #27ae60;
    --warning: #f39c12;
    --danger: #e74c3c;
    --border: #e0e6ed;
}

* { box-sizing: border-box; }

body {
    font-family: "Source Han Sans CN", "Noto Sans SC", -apple-system, BlinkMacSystemFont, sans-serif;
    line-height: 1.8;
    color: var(--text);
    background: var(--bg);
    margin: 0;
    padding: 0;
}

/* 头部 */
.doc-header {
    background: var(--primary);
    color: white;
    padding: 40px;
    text-align: center;
}

.doc-badge {
    display: inline-block;
    background: rgba(255,255,255,0.15);
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 13px;
    margin-bottom: 16px;
    letter-spacing: 1px;
}

.doc-header h1 {
    font-size: 1.8em;
    margin: 0 0 20px 0;
    font-weight: 600;
}

.case-meta {
    display: flex;
    justify-content: center;
    gap: 24px;
    flex-wrap: wrap;
}

.meta-item {
    font-size: 14px;
    opacity: 0.9;
}

.meta-label {
    opacity: 0.7;
    margin-right: 6px;
}

/* 内容区域 */
.content {
    max-width: 900px;
    margin: 0 auto;
    padding: 40px 20px;
    background: var(--bg-white);
}

/* 核心要点 */
.key-points {
    max-width: 900px;
    margin: -30px auto 30px;
    padding: 0 20px;
}

.key-point {
    background: white;
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    border-left: 4px solid var(--primary);
}

.key-point.result {
    border-left-color: var(--accent);
    background: linear-gradient(135deg, #fff 0%, #fff9f0 100%);
}

.point-label {
    font-size: 12px;
    color: var(--text-light);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
}

.point-value {
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
}

.points-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
    margin-top: 12px;
}

/* 表格样式 */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 1.5em 0;
    font-size: 0.95em;
}

th, td {
    padding: 12px 16px;
    text-align: left;
    border-bottom: 1px solid var(--border);
}

th {
    background: var(--primary);
    color: white;
    font-weight: 500;
}

tr:nth-child(even) { background: #f8f9fa; }

tr:hover { background: #f0f4f8; }

/* 引用块 */
blockquote {
    border-left: 4px solid var(--accent);
    background: #fffbf5;
    padding: 16px 20px;
    margin: 1.5em 0;
    border-radius: 0 8px 8px 0;
}

/* 标题 */
h2 {
    color: var(--primary);
    border-bottom: 2px solid var(--border);
    padding-bottom: 8px;
    margin-top: 2em;
}

h3 {
    color: var(--primary-light);
    margin-top: 1.5em;
}

/* 时间轴 */
.timeline-section {
    max-width: 900px;
    margin: 40px auto;
    padding: 0 20px;
}

.timeline {
    position: relative;
    padding-left: 30px;
    border-left: 2px solid var(--border);
}

.timeline-item {
    position: relative;
    padding-bottom: 24px;
}

.timeline-dot {
    position: absolute;
    left: -36px;
    top: 4px;
    width: 10px;
    height: 10px;
    background: var(--primary);
    border-radius: 50%;
    border: 2px solid white;
    box-shadow: 0 0 0 2px var(--primary);
}

.timeline-date {
    font-size: 13px;
    color: var(--text-light);
    font-family: "SF Mono", Consolas, monospace;
}

.timeline-content {
    font-size: 15px;
    margin-top: 4px;
}

/* 页脚 */
.doc-footer {
    text-align: center;
    padding: 30px;
    color: var(--text-light);
    font-size: 13px;
    border-top: 1px solid var(--border);
    margin-top: 60px;
}

/* 打印样式 */
@media print {
    .doc-header { padding: 20px; }
    .key-points { margin: 20px 0; }
    body { background: white; }
    table { page-break-inside: avoid; }
}
'''
    
    def _get_general_styles(self) -> str:
        """获取通用样式"""
        return '''
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    line-height: 1.8;
    max-width: 900px;
    margin: 0 auto;
    padding: 40px 20px;
    color: #333;
}
h1, h2, h3 { color: #1e3a5f; }
table { width: 100%; border-collapse: collapse; margin: 1em 0; }
th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
th { background: #1e3a5f; color: white; }
blockquote { border-left: 4px solid #e67e22; padding-left: 1em; margin: 1em 0; }
@media print {
    .pdf-action-btn { display: none !important; }
}
'''


# ============================================================================
# 主转换器
# ============================================================================

class MarkdownToHTMLConverter:
    """Markdown 转 HTML 转换器 v2.0"""
    
    def __init__(self, theme="legal", toc=False, print_style=True, 
                 auto_detect=True, doc_type=None):
        self.theme = theme
        self.toc = toc
        self.print_style = print_style
        self.auto_detect = auto_detect
        self.doc_type = doc_type
        self.md = markdown.Markdown(
            extensions=['tables', 'fenced_code', 'toc', 'nl2br', 'sane_lists']
        )
    
    def convert(self, md_content: str, title: str = None) -> str:
        """转换 Markdown 为 HTML"""
        
        # 1. 检测文档类型
        if self.auto_detect and not self.doc_type:
            self.doc_type = DocumentTypeDetector.detect(md_content)
        
        # 2. 转换 Markdown
        html_body = self.md.convert(md_content)
        
        # 3. 提取标题
        if not title:
            title = self._extract_title(md_content) or "文档"
        
        # 4. 解析内容结构
        soup = BeautifulSoup(html_body, 'html.parser')
        parser = ContentStructureParser(soup, md_content)
        structure = parser.parse()
        
        # 5. 生成专业 HTML
        generator = LegalHTMLGenerator(self.doc_type)
        html = generator.generate(soup, structure, title)
        
        return html
    
    def _extract_title(self, md_content: str) -> str:
        """提取标题"""
        match = re.search(r'^#\s+(.+)$', md_content, re.MULTILINE)
        if match:
            title = match.group(1)
            title = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', title)
            return title.strip()
        return "文档"


# ============================================================================
# 文件处理
# ============================================================================

def process_file(input_path: str, output_path: str = None, **kwargs) -> str:
    """处理单个文件"""
    with open(input_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    if not output_path:
        input_file = Path(input_path)
        output_path = str(input_file.with_suffix('.html'))
    
    converter = MarkdownToHTMLConverter(**kwargs)
    html_content = converter.convert(md_content)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    # 显示检测到的类型
    doc_type = converter.doc_type
    type_name = DocumentTypeDetector.get_type_display_name(doc_type)
    print(f"✅ 转换完成: {input_path} → {output_path}")
    print(f"   📋 检测类型: {type_name}")
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description='法律文书 Markdown 转 HTML 可视化报告 v2.0')
    parser.add_argument('input', help='输入 Markdown 文件')
    parser.add_argument('-o', '--output', help='输出 HTML 文件')
    parser.add_argument('--type', '--doc-type', dest='doc_type', 
                       help='指定文档类型 (judgment_internal, judgment_client, judgment_research, legal_opinion)')
    parser.add_argument('--no-auto-detect', dest='auto_detect', action='store_false',
                       help='禁用自动类型检测')
    parser.add_argument('--theme', default='legal', choices=['legal', 'academic', 'minimal'])
    parser.add_argument('--toc', action='store_true', help='生成目录导航')
    
    args = parser.parse_args()
    
    kwargs = {
        'theme': args.theme,
        'toc': args.toc,
        'print_style': True,
        'auto_detect': args.auto_detect,
        'doc_type': args.doc_type
    }
    
    process_file(args.input, args.output, **kwargs)


if __name__ == '__main__':
    main()
