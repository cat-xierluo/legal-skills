#!/usr/bin/env python3
"""
Dashboard 生成器 - 将 GitHub Star 数据导出为 HTML Dashboard

负责：
1. 保存项目数据为 JSON 文件
2. 复制模板到输出目录（纯前端加载 JSON，不内嵌数据）
3. 创建简版 HTML（当模板不存在时）
"""

import json
from pathlib import Path


def generate_dashboard(projects: list, output_dir: str = "output") -> dict:
    """
    生成 Dashboard HTML 和数据文件

    Args:
        projects: 项目数据列表
        output_dir: 输出目录（相对于项目根目录）

    Returns:
        dict: 包含生成的文件的路径信息
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 生成 data.js 文件（HTML 直接引用，无需 HTTP 服务器）
    data_js_path = output_path / "data.js"
    json_str = json.dumps(projects, ensure_ascii=False)
    # 修复 JavaScript 不兼容的字符：U+2028 (Line Separator) 和 U+2029 (Paragraph Separator)
    json_str = json_str.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    with open(data_js_path, "w", encoding="utf-8") as f:
        f.write(f"const PROJECTS_DATA = {json_str};\n")

    # 查找模板文件
    example_path = Path("assets/dashboard.example.html")

    if example_path.exists():
        dashboard_path = _generate_from_template(projects, example_path, output_path)
    else:
        dashboard_path = _generate_simple_html(projects, output_path)

    return {
        "data_js_path": str(data_js_path),
        "dashboard_path": str(dashboard_path),
        "project_count": len(projects)
    }


def _generate_from_template(projects: list, template_path: Path, output_dir: Path) -> Path:
    """从模板生成 HTML（纯前端加载 JSON，不内嵌数据）"""
    # 直接复制模板，保持原有的 fetch 机制
    html_content = template_path.read_text(encoding='utf-8')

    dashboard_path = output_dir / "dashboard.html"
    dashboard_path.write_text(html_content, encoding='utf-8')

    return dashboard_path


def _generate_simple_html(projects: list, output_dir: Path) -> Path:
    """创建简版 HTML（当模板不存在时，使用 fetch 加载 JSON）"""
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub Star Tracker</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0d1117; color: #c9d1d9; padding: 40px; }}
        h1 {{ color: #58a6ff; }}
        .project {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 12px; }}
        a {{ color: #58a6ff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <h1>⭐ GitHub Star Tracker</h1>
    <p>加载中...</p>
    <div id="app"></div>

    <script>
        async function loadProjects() {{
            try {{
                const response = await fetch('projects.json');
                const projects = await response.json();
                renderProjects(projects);
            }} catch (error) {{
                document.getElementById('app').innerHTML =
                    '<p style="color: #f85149;">加载失败: 请确保 projects.json 存在</p>';
            }}
        }}

        function renderProjects(projects) {{
            document.getElementById('app').innerHTML = projects.map(p => `
                <div class="project">
                    <a href="${{p.html_url}}" target="_blank"><strong>${{p.full_name}}</strong></a><br>
                    <span style="color: #8b949e;">${{p.description || '暂无描述'}}</span><br>
                    <small>⭐ ${{p.stargazers_count}} | ⑂ ${{p.forks_count}} | ${{p.language || '-'}}</small>
                </div>
            `).join('');
        }}

        loadProjects();
    </script>
</body>
</html>'''

    dashboard_path = output_dir / "dashboard.html"
    dashboard_path.write_text(html, encoding='utf-8')

    return dashboard_path


def generate_simple_html(projects: list, output_path: str) -> Path:
    """
    创建简版 HTML

    Args:
        projects: 项目数据列表
        output_path: 输出文件路径

    Returns:
        Path: 输出文件的 Path 对象
    """
    return _generate_simple_html(projects, Path(output_path).parent)


def embed_data_in_template(template_path: str, projects: list) -> str:
    """
    返回 HTML 模板内容（纯前端加载 JSON，不内嵌数据）

    注意：此函数已废弃，现在使用纯前端 fetch 方式加载 JSON 文件
    保留此函数是为了向后兼容，直接返回原始模板内容

    Args:
        template_path: 模板文件路径
        projects: 项目数据列表（不再使用，保留参数以兼容旧调用）

    Returns:
        str: 原始模板内容
    """
    template_file = Path(template_path)
    if not template_file.exists():
        raise FileNotFoundError(f"模板文件不存在: {template_path}")

    # 直接返回原始模板内容，不进行任何修改
    return template_file.read_text(encoding='utf-8')
