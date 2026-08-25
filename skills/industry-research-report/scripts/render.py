#!/usr/bin/env python3
"""行业法律调研报告渲染器:md → A4 HTML

- 模板占位符 + 数据填充（jinja2）
- frontmatter（YAML）→ 封面字段
- markdown body → 按 # / ## 拆 section,每章一个 .section-page
- ```mermaid 块 → mmdc 预渲染 SVG 内联（依赖 mmdc,可降级）
- report-profile.md → 抬头 / 配色 / 主办律师 / 封面变体
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime

import markdown
import yaml
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "references"
COVERS_DIR = TEMPLATE_DIR / "covers"
TEMPLATE_NAME = "report-template.html"

VALID_COVERS = {"C-geo", "D-diagonal", "E-flip", "F-grid"}
VALID_PALETTES = {"bluebook", "service-plan", "burgundy", "forest", "tech"}
VALID_INTENSITY = {"lite", "balanced", "visual"}


# ── report-profile 读取 ────────────────────────────────────────
def load_profile(profile_path: Path) -> dict:
    """读取 report-profile.md 的 YAML frontmatter 与列表字段。"""
    if not profile_path.exists():
        print(f"[warn] {profile_path} 不存在,使用默认配置", file=sys.stderr)
        return default_profile()
    text = profile_path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    profile = {**default_profile(), **(fm or {})}
    # 列表字段(联系方式 / 名单类)从正文中以 `- key: val  # 注释` 形式提取
    # 注意:YAML 行尾 `# 注释` 必须剔除
    for line in body.splitlines():
        stripped = line.strip()
        m = re.match(r"^-\s+([a-zA-Z_]+)\s*:\s*(.+?)(?:\s+#.*)?$", stripped)
        if m:
            profile[m.group(1)] = m.group(2).strip()
    # 字段校验
    if profile["cover_style"] not in VALID_COVERS:
        print(f"[warn] cover_style={profile['cover_style']} 不合法,回退 C-geo", file=sys.stderr)
        profile["cover_style"] = "C-geo"
    if profile["color_palette"] not in VALID_PALETTES:
        profile["color_palette"] = "bluebook"
    if profile["design_intensity"] not in VALID_INTENSITY:
        profile["design_intensity"] = "lite"
    # YAML frontmatter 的布尔字段是 True/False,list 是 [...]
    for bool_key in ("include_toc", "include_methodology"):
        if isinstance(profile.get(bool_key), str):
            profile[bool_key] = profile[bool_key].strip().lower() in ("true", "1", "yes", "on")
    return profile


def default_profile() -> dict:
    return {
        "law_firm": "XX 律所",
        "series_name": "XX 律所实务手册",
        "series_subtitle": "PROFESSIONAL EDITION",
        "report_code": f"YWX-IR-{datetime.now().year}-01",
        "lead_lawyer": "XX 律师",
        "lead_lawyer_title": "律师",
        "lead_lawyer_avatar": "",
        "motto": "",
        "contact_wechat": "{微信号占位}",
        "contact_phone": "{电话占位}",
        "contact_email": "",
        "cover_style": "C-geo",
        "color_palette": "bluebook",
        "accent_color": "#D4AF37",
        "design_intensity": "lite",
        "include_toc": True,
        "include_methodology": True,
        "footer_brand": "行业法律调研报告",
    }


# ── 5 个律师常见调色板（与 references/palette-presets.md 对齐）────
PALETTE_PRESETS = {
    "bluebook": {
        # 法律经典蓝皮书：深蓝主色 + 金色强调
        "primary_deep": "#143049",
        "primary":      "#1B3C59",
        "primary_soft": "#2C5F8A",
        "accent":       "#D4AF37",
        "text":         "#1A1A1A",
        "text_soft":    "#2C3E50",
        "text_muted":   "#666666",
        "bg_page":      "#FFFFFF",
        "bg_card":      "#F4F1EA",
        "bg_soft":      "#FAFAFA",
        "rule":         "#DDDDDD",
    },
    "service-plan": {
        # 传统律所深棕：温暖稳重
        "primary_deep": "#3D342F",
        "primary":      "#5A4E48",
        "primary_soft": "#6E5F56",
        "accent":       "#927F76",
        "text":         "#1A1A1A",
        "text_soft":    "#333333",
        "text_muted":   "#666666",
        "bg_page":      "#FFFFFF",
        "bg_card":      "#F5F0ED",
        "bg_soft":      "#FAFAFA",
        "rule":         "#CCCCCC",
    },
    "burgundy": {
        # 酒红：高端典雅，涉外仲裁
        "primary_deep": "#4F1F25",
        "primary":      "#722F37",
        "primary_soft": "#945661",
        "accent":       "#B08D5C",
        "text":         "#1A1A1A",
        "text_soft":    "#2C3E50",
        "text_muted":   "#666666",
        "bg_page":      "#FFFFFF",
        "bg_card":      "#F8F1ED",
        "bg_soft":      "#FAFAFA",
        "rule":         "#DDDDDD",
    },
    "forest": {
        # 森林绿：环境法 / ESG / 合规
        "primary_deep": "#143024",
        "primary":      "#1F4E3D",
        "primary_soft": "#3D6E5A",
        "accent":       "#A8853A",
        "text":         "#1A1A1A",
        "text_soft":    "#2C3E50",
        "text_muted":   "#666666",
        "bg_page":      "#FFFFFF",
        "bg_card":      "#F2F4ED",
        "bg_soft":      "#FAFAFA",
        "rule":         "#DDDDDD",
    },
    "tech": {
        # 科技蓝：互联网 / 数据合规 / AI
        "primary_deep": "#102449",
        "primary":      "#1A3A6E",
        "primary_soft": "#385E94",
        "accent":       "#00A6B6",
        "text":         "#1A1A1A",
        "text_soft":    "#2C3E50",
        "text_muted":   "#666666",
        "bg_page":      "#FFFFFF",
        "bg_card":      "#F0F4F8",
        "bg_soft":      "#FAFAFA",
        "rule":         "#DDDDDD",
    },
}


def resolve_palette(profile: dict) -> dict:
    """根据 profile.color_palette 解析 5 个预设之一;accent_color 允许覆盖。"""
    key = profile.get("color_palette", "bluebook")
    palette = dict(PALETTE_PRESETS.get(key, PALETTE_PRESETS["bluebook"]))
    # accent_color 覆盖
    accent_override = profile.get("accent_color", "").strip()
    if accent_override and accent_override.startswith("#"):
        palette["accent"] = accent_override
    return palette


def split_frontmatter(text: str):
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            try:
                fm = yaml.safe_load(text[4:end]) or {}
            except yaml.YAMLError:
                fm = {}
            if isinstance(fm, dict):
                return fm, text[end + 5 :]
    return {}, text


# ── mermaid 预渲染（mmdc,可降级）─────────────────────────────
MERMAID_RE = re.compile(r"```mermaid\n(.*?)\n```", re.DOTALL)


def _find_chrome() -> str | None:
    for c in [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
    ]:
        if Path(c).exists():
            return c
    return None


def render_mermaid_blocks(body: str) -> str:
    def repl(m):
        code = m.group(1).strip()
        mmd_path = None
        svg_path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False, encoding="utf-8") as f:
                f.write(code)
                mmd_path = Path(f.name)
            svg_path = mmd_path.with_suffix(".svg")
            env = os.environ.copy()
            chrome = _find_chrome()
            if chrome:
                env["PUPPETEER_EXECUTABLE_PATH"] = chrome
            r = subprocess.run(
                ["mmdc", "-i", str(mmd_path), "-o", str(svg_path), "-b", "transparent"],
                capture_output=True, timeout=60, env=env,
            )
            if r.returncode == 0 and svg_path.exists():
                svg = svg_path.read_text(encoding="utf-8")
                return f'<div class="diagram">\n{svg}\n</div>'
            print(f"[warn] mermaid mmdc 返回 {r.returncode},fallback 代码块", file=sys.stderr)
        except FileNotFoundError:
            print("[warn] mmdc 未安装,fallback 代码块", file=sys.stderr)
        except Exception as e:
            print(f"[warn] mermaid 渲染失败:{e},fallback 代码块", file=sys.stderr)
        finally:
            if mmd_path:
                mmd_path.unlink(missing_ok=True)
            if svg_path:
                svg_path.unlink(missing_ok=True)
        return f"<pre><code>{code}</code></pre>"

    return MERMAID_RE.sub(repl, body)


# ── markdown → html ────────────────────────────────────────────
def md_to_html(body: str) -> str:
    return markdown.markdown(body, extensions=["tables", "fenced_code", "sane_lists", "toc"])


# ── section 拆分（按 # 一级标题）──────────────────────────────
def split_sections(html: str) -> list[dict]:
    """将渲染后的 html 按 # 一级标题拆为 sections 列表,每个 section 含 kicker/title/html。"""
    soup = BeautifulSoup(html, "html.parser")
    sections = []
    current = {"kicker": "", "title": "", "html": ""}
    for el in soup.find_all(["h1", "h2", "h3", "p", "ul", "ol", "blockquote", "table", "div"]):
        if el.name == "h1":
            if current["title"] or current["html"]:
                sections.append(current)
            current = {"kicker": "CHAPTER", "title": el.get_text(strip=True), "html": ""}
        elif el.name == "h2" and not current["title"]:
            # 没有 h1,首个 h2 作为章节标题
            current["kicker"] = "CHAPTER"
            current["title"] = el.get_text(strip=True)
        else:
            current["html"] += str(el)
    if current["title"] or current["html"]:
        sections.append(current)
    # 若无任何 section（罕见,如只有一段免责声明）,包成单 section
    if not sections and html.strip():
        sections = [{"kicker": "CONTENT", "title": "正文", "html": html}]
    return sections


# ── 目录生成 ──────────────────────────────────────────────────
def build_toc(sections: list[dict], start_page: int) -> list[dict]:
    """基于 sections 与起始页码,构造 toc_entries。"""
    entries = []
    page = start_page
    for i, s in enumerate(sections, 1):
        entries.append({"level": 1, "num": f"第 {i} 章", "text": s["title"], "page": page})
        page += 1  # 粗估:每章一页,真实页码由 pdf.py 二次校正（v2）
    return entries


# ── 封面注入 ──────────────────────────────────────────────────
def render_cover(profile: dict, report_meta: dict, jinja_env: Environment) -> str:
    cover_file = COVERS_DIR / f"cover-{profile['cover_style']}.html"
    if not cover_file.exists():
        cover_file = COVERS_DIR / "cover-C-geo.html"
    cover_tpl_text = cover_file.read_text(encoding="utf-8")
    # cover 文件本身是 <style> + <div>...</div> 两段;jinja2 直接渲染 <div> 部分
    # 提取 <div>...</div> 部分（最后一个 div 是根）
    soup = BeautifulSoup(cover_tpl_text, "html.parser")
    div = soup.find("div")
    if not div:
        return cover_tpl_text
    cover_inner_tpl = jinja_env.from_string(str(div))
    return cover_inner_tpl.render(**report_meta)


# ── 主流程 ────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="行业调研报告 md → A4 HTML")
    ap.add_argument("--input", "-i", required=True, help="报告 markdown 路径")
    ap.add_argument("--profile", "-p", default=str(SKILL_DIR / "config" / "report-profile.md"))
    ap.add_argument("--output", "-o", required=True, help="输出 HTML 路径")
    args = ap.parse_args()

    in_path = Path(args.input).resolve()
    out_path = Path(args.output).resolve()
    profile_path = Path(args.profile).resolve()

    profile = load_profile(profile_path)

    md_text = in_path.read_text(encoding="utf-8")
    md_text = render_mermaid_blocks(md_text)
    html_body = md_to_html(md_text)
    sections = split_sections(html_body)

    jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html"]))
    template = jinja_env.get_template(TEMPLATE_NAME)

    now = datetime.now()
    report_meta = {
        **profile,
        "report_title": in_path.stem,
        "report_subtitle": "行业 · 区域 · 法律风险全景",
        "report_lead": "基于企查查企业数据库与公开政策、产业资料自动整理的内部情报底稿,不构成法律意见。",
        "kicker": "INDUSTRY · LEGAL · INTELLIGENCE",
        "industry": extract_industry_from_md(md_text),
        "generated_date": now.strftime("%Y-%m-%d"),
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "skill_version": "0.1.0",
    }

    cover_html = render_cover(profile, report_meta, jinja_env)

    # 目录页（cover 占 1 页,toc 占 1 页;v2 真实页码由 pdf.py 校正）
    start_page = 3 if profile.get("include_toc", True) else 2
    toc_entries = build_toc(sections, start_page) if profile.get("include_toc", True) else []

    rendered = template.render(
        profile=profile,
        palette=resolve_palette(profile),
        sections=sections,
        cover_html=cover_html,
        include_toc=bool(profile.get("include_toc", True)),
        toc_entries=toc_entries,
        **{k: v for k, v in report_meta.items() if k not in ("include_toc", "include_methodology")},
    )

    out_path.write_text(rendered, encoding="utf-8")
    print(f"已生成 HTML:{out_path}")


def extract_industry_from_md(md_text: str) -> str:
    """从报告 md 的 H1 标题中提取行业词（如 '行业调研报告 · XXX · ...'）。"""
    m = re.search(r"^#\s+行业调研报告\s*·\s*([^·\s]+)", md_text, re.M)
    return m.group(1).strip() if m else "—"


if __name__ == "__main__":
    main()
