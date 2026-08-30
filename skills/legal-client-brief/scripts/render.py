#!/usr/bin/env python3
"""行业报告 / 客户简报渲染器：Markdown → A4 HTML。

- 模板占位符 + 数据填充(jinja2)
- frontmatter(YAML)→ 封面字段
- markdown body → 按 ## 二级标题拆 section,每章一个 .section-page
- ```mermaid 块 → mmdc 预渲染 SVG 内联(依赖 mmdc,可降级)
- report-profile.md → 抬头 / 配色 / 主办律师 / 封面变体 / report_kind
- 封面 CSS 内容注入(去 <style> 包装后)到主模板 style 末尾
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

try:
    import markdown
    import yaml
    from bs4 import BeautifulSoup
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError as exc:
    package = getattr(exc, "name", "未知包")
    print(f"[error] 缺少 Python 依赖: {package}", file=sys.stderr)
    print("请运行: python3 -m pip install -r scripts/requirements.txt", file=sys.stderr)
    raise SystemExit(1) from exc

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "references"
COVERS_DIR = TEMPLATE_DIR / "covers"
TEMPLATE_NAME = "report-template.html"

# report 使用机构出版物封面，brief 使用轻量信息简报封面。
REPORT_COVERS = {"C-geo", "D-diagonal", "E-flip", "F-grid"}
BRIEF_COVERS = {"W1-minimal", "W2-tag-bar"}
VALID_COVERS = REPORT_COVERS | BRIEF_COVERS
VALID_PALETTES = {"bluebook", "service-plan", "burgundy", "forest", "tech"}
VALID_INTENSITY = {"lite", "balanced", "visual"}
VALID_REPORT_KIND = {"report", "brief"}
DEFAULT_COVER_BY_KIND = {"report": "C-geo", "brief": "W1-minimal"}


# ── report-profile 读取 ────────────────────────────────────────
def load_profile(profile_path: Path) -> dict:
    if not profile_path.exists():
        print(f"[warn] {profile_path} 不存在,使用默认配置", file=sys.stderr)
        return default_profile()
    text = profile_path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    profile = {**default_profile(), **(fm or {})}
    for line in body.splitlines():
        stripped = line.strip()
        m = re.match(r"^-\s+([a-zA-Z_]+)\s*:\s*(.+?)(?:\s+#.*)?$", stripped)
        if m:
            raw_value = m.group(2).strip()
            try:
                value = yaml.safe_load(raw_value)
            except yaml.YAMLError:
                value = raw_value
            profile[m.group(1)] = "" if value is None else value
    return normalize_profile(profile)


def normalize_profile(profile: dict) -> dict:
    """在配置与 CLI 覆盖合并后统一校验，避免 kind 改了但封面仍沿用旧类型。"""
    report_kind = str(profile.get("report_kind", "report")).lower()
    if report_kind not in VALID_REPORT_KIND:
        report_kind = "report"
    profile["report_kind"] = report_kind
    # cover_style 按 kind 校验
    allowed = REPORT_COVERS if report_kind == "report" else BRIEF_COVERS
    if profile["cover_style"] not in allowed:
        fallback = DEFAULT_COVER_BY_KIND[report_kind]
        print(f"[warn] cover_style={profile['cover_style']} 不适用于 report_kind={report_kind},回退 {fallback}", file=sys.stderr)
        profile["cover_style"] = fallback
    if profile["color_palette"] not in VALID_PALETTES:
        profile["color_palette"] = "bluebook"
    if profile["design_intensity"] not in VALID_INTENSITY:
        profile["design_intensity"] = "lite"
    for bool_key in ("include_toc", "include_methodology"):
        if isinstance(profile.get(bool_key), str):
            profile[bool_key] = profile[bool_key].strip().lower() in ("true", "1", "yes", "on")
    return profile


def default_profile() -> dict:
    return {
        "report_kind": "report",
        "law_firm": "XX 律所",
        "series_name": "XX 律所实务手册",
        "series_subtitle": "PROFESSIONAL EDITION",
        "report_code": f"YWX-REPORT-{datetime.now().year}-01",
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
        "footer_brand": "行业报告",
        "audience_label": "科技型制造企业",
        "period_start": "",
        "period_end": datetime.now().strftime("%Y-%m-%d"),
        "cadence": "weekly",
    }


# ── 5 个律师常见调色板 ──
PALETTE_PRESETS = {
    "bluebook": {
        "primary_deep": "#143049", "primary": "#1B3C59", "primary_soft": "#2C5F8A",
        "accent": "#D4AF37", "text": "#1A1A1A", "text_soft": "#2C3E50",
        "text_muted": "#666666", "bg_page": "#FFFFFF", "bg_card": "#F4F1EA",
        "bg_soft": "#FAFAFA", "rule": "#DDDDDD",
    },
    "service-plan": {
        "primary_deep": "#3D342F", "primary": "#5A4E48", "primary_soft": "#6E5F56",
        "accent": "#927F76", "text": "#1A1A1A", "text_soft": "#333333",
        "text_muted": "#666666", "bg_page": "#FFFFFF", "bg_card": "#F5F0ED",
        "bg_soft": "#FAFAFA", "rule": "#CCCCCC",
    },
    "burgundy": {
        "primary_deep": "#4F1F25", "primary": "#722F37", "primary_soft": "#945661",
        "accent": "#B08D5C", "text": "#1A1A1A", "text_soft": "#2C3E50",
        "text_muted": "#666666", "bg_page": "#FFFFFF", "bg_card": "#F8F1ED",
        "bg_soft": "#FAFAFA", "rule": "#DDDDDD",
    },
    "forest": {
        "primary_deep": "#143024", "primary": "#1F4E3D", "primary_soft": "#3D6E5A",
        "accent": "#A8853A", "text": "#1A1A1A", "text_soft": "#2C3E50",
        "text_muted": "#666666", "bg_page": "#FFFFFF", "bg_card": "#F2F4ED",
        "bg_soft": "#FAFAFA", "rule": "#DDDDDD",
    },
    "tech": {
        "primary_deep": "#102449", "primary": "#1A3A6E", "primary_soft": "#385E94",
        "accent": "#00A6B6", "text": "#1A1A1A", "text_soft": "#2C3E50",
        "text_muted": "#666666", "bg_page": "#FFFFFF", "bg_card": "#F0F4F8",
        "bg_soft": "#FAFAFA", "rule": "#DDDDDD",
    },
}


def resolve_palette(profile: dict) -> dict:
    key = profile.get("color_palette", "bluebook")
    palette = dict(PALETTE_PRESETS.get(key, PALETTE_PRESETS["bluebook"]))
    accent_override = str(profile.get("accent_color") or "").strip()
    if accent_override and accent_override.startswith("#"):
        palette["accent"] = accent_override
    return palette


# ── 正式报告 / 高频简报使用不同的阅读节奏 ──
DESIGN_REPORT = {
    "body_size": "11pt", "body_leading": "1.95",
    "h1_size": "21pt", "h2_size": "16pt", "h3_size": "12.5pt",
    "toc_columns": "2",
    "rule_color": "{{ palette.accent }}",
    "rule_width": "2px",
    "header_rule_color": "{{ palette.accent }}",
    "header_rule_width": "1.5px",
    "table_header_bg": "{{ palette.primary }}",
}
DESIGN_BRIEF = {
    "body_size": "10.5pt", "body_leading": "1.72",
    "h1_size": "16pt", "h2_size": "13.5pt", "h3_size": "11.5pt",
    "toc_columns": "1",
    "rule_color": "{{ palette.primary_soft }}",
    "rule_width": "0.8px",
    "header_rule_color": "{{ palette.primary_soft }}",
    "header_rule_width": "0.5px",
    "table_header_bg": "{{ palette.bg_card }}",
}


def resolve_design(report_kind: str, palette: dict) -> dict:
    base = DESIGN_REPORT if report_kind == "report" else DESIGN_BRIEF
    env = Environment()
    return {k: env.from_string(v).render(palette=palette) for k, v in base.items()}


def split_frontmatter(text: str):
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            try:
                fm = yaml.safe_load(text[4:end]) or {}
            except yaml.YAMLError:
                fm = {}
            if isinstance(fm, dict):
                return fm, text[end + 5:]
    return {}, text


MERMA_RE = re.compile(r"```mermaid\n(.*?)\n```", re.DOTALL)


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
        except FileNotFoundError:
            print("[warn] mmdc 未安装,fallback 代码块", file=sys.stderr)
        except Exception as e:
            print(f"[warn] mermaid 渲染失败:{e}", file=sys.stderr)
        finally:
            if mmd_path:
                mmd_path.unlink(missing_ok=True)
            if svg_path:
                svg_path.unlink(missing_ok=True)
        return f"<pre><code>{code}</code></pre>"

    return MERMA_RE.sub(repl, body)


def md_to_html(body: str) -> str:
    return markdown.markdown(body, extensions=["tables", "fenced_code", "sane_lists", "toc"])


def split_sections(html: str) -> list[dict]:
    """按 H2 二级标题拆章。H1 报告名跳过;H1 之后到第一个 H2 之前的前言块并入首个 section。"""
    soup = BeautifulSoup(html, "html.parser")
    sections = []
    current = {"kicker": "CHAPTER", "title": "", "html": ""}
    preamble_parts = []
    h1_seen = False
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "ul", "ol", "blockquote", "table", "div"]):
        if el.name == "h1":
            h1_seen = True
            continue
        if el.name == "h2":
            if current["title"] or current["html"]:
                sections.append(current)
            current = {"kicker": "CHAPTER", "title": el.get_text(strip=True), "html": "".join(preamble_parts)}
            preamble_parts = []
            continue
        if el.name == "h3" and not current["title"]:
            current = {"kicker": "CHAPTER", "title": el.get_text(strip=True), "html": "".join(preamble_parts)}
            preamble_parts = []
            continue
        if not h1_seen:
            current["html"] += str(el)
        elif not current["title"]:
            preamble_parts.append(str(el))
        else:
            current["html"] += str(el)
    if current["title"] or current["html"]:
        sections.append(current)
    if not sections and preamble_parts:
        sections = [{"kicker": "PREAMBLE", "title": "前言", "html": "".join(preamble_parts)}]
    if not sections and html.strip():
        sections = [{"kicker": "CONTENT", "title": "正文", "html": html}]
    for index, section in enumerate(sections, 1):
        section["number"] = f"{index:02d}"
    return sections


def build_toc(sections: list[dict]) -> list[dict]:
    """生成可靠的章节索引；HTML 阶段无法得知浏览器最终分页，不伪造页码。"""
    entries = []
    for i, s in enumerate(sections, 1):
        entries.append({"level": 1, "num": f"第 {i} 章", "text": s["title"]})
    return entries


def render_cover(profile: dict, report_meta: dict, jinja_env: Environment):
    """返回 (css_body, div_str)。css_body 是 <style> 去掉包装的纯 CSS 内容(并入主模板 style 末尾)。
    Playwright 打印时 querySelector("style") 只取第一个元素,故必须合并到主模板的 style 内。"""
    cover_file = COVERS_DIR / f"cover-{profile['cover_style']}.html"
    if not cover_file.exists():
        cover_file = COVERS_DIR / "cover-C-geo.html"
    cover_tpl_text = cover_file.read_text(encoding="utf-8")
    soup = BeautifulSoup(cover_tpl_text, "html.parser")
    style_tag = soup.find("style")
    div = soup.find("div")
    css_body = (style_tag.string or "") if style_tag else ""
    if not div:
        return css_body, cover_tpl_text
    cover_inner_tpl = jinja_env.from_string(str(div))
    div_str = cover_inner_tpl.render(**report_meta)
    return css_body, div_str


def main():
    ap = argparse.ArgumentParser(description="行业报告 / 客户简报 Markdown → A4 HTML")
    ap.add_argument("--input", "-i", required=True, help="报告 markdown 路径")
    ap.add_argument("--profile", "-p", default=str(SKILL_DIR / "config" / "report-profile.md"))
    ap.add_argument("--output", "-o", required=True, help="输出 HTML 路径")
    ap.add_argument("--report-kind", choices=["report", "brief"], default=None, help="覆盖 profile 字段")
    ap.add_argument("--cover-style", default=None, help="封面变体")
    ap.add_argument("--period-start", default=None, help="简报窗口起始日")
    ap.add_argument("--period-end", default=None, help="简报窗口结束日")
    ap.add_argument("--cadence", choices=["daily", "weekly", "event"], default=None)
    args = ap.parse_args()

    in_path = Path(args.input).resolve()
    out_path = Path(args.output).resolve()
    profile_path = Path(args.profile).resolve()

    profile = load_profile(profile_path)

    if args.report_kind:
        profile["report_kind"] = args.report_kind
    if args.cover_style:
        if args.cover_style not in VALID_COVERS:
            print(f"[warn] --cover-style={args.cover_style} 不合法,忽略", file=sys.stderr)
        else:
            profile["cover_style"] = args.cover_style
    if args.period_start:
        profile["period_start"] = args.period_start
    if args.period_end:
        profile["period_end"] = args.period_end
    if args.cadence:
        profile["cadence"] = args.cadence
    profile = normalize_profile(profile)

    report_kind = profile["report_kind"]
    is_brief = report_kind == "brief"
    if is_brief:
        period_end = str(profile.get("period_end") or now_date())
        cadence = str(profile.get("cadence") or "weekly")
        report_code = str(profile.get("report_code", "YWX-BRIEF"))
        report_code = re.sub(r"-(?:DAILY|WEEKLY|EVENT)-\d{8}$", "", report_code)
        profile["report_code"] = f"{report_code}-{cadence.upper()}-{period_end.replace('-', '')}"
        profile["cadence_label"] = {"daily": "每日", "weekly": "每周", "event": "事件"}[cadence]

    if not in_path.is_file():
        print(f"[error] 输入 Markdown 不存在: {in_path}", file=sys.stderr)
        raise SystemExit(2)
    if not profile_path.is_file():
        print(f"[warn] 未找到 profile，已使用去具体化默认值: {profile_path}", file=sys.stderr)

    md_text = in_path.read_text(encoding="utf-8")
    md_text = render_mermaid_blocks(md_text)
    html_body = md_to_html(md_text)
    sections = split_sections(html_body)

    jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html"]))
    template = jinja_env.get_template(TEMPLATE_NAME)

    now = datetime.now()
    if is_brief:
        default_subtitle = "客户相关 · 增量变化 · 可执行提示"
        default_lead = "只保留本窗口内与既有客户相关的变化；三渠道草稿均须经律师复核后人工发布。"
        default_kicker = "CLIENT · SIGNAL · BRIEF"
        default_footer = f"客户简报 · {profile.get('cadence_label', '每周')}"
    else:
        default_subtitle = "产业结构 · 监管趋势 · 法律机会"
        default_lead = "面向公开展示与长期留存的行业研究作品；所有事实、判断和表达均需在发布前完成专业复核。"
        default_kicker = "INDUSTRY · LEGAL · REPORT"
        default_footer = "行业报告"

    skill_name, skill_version = read_skill_identity(is_brief)
    configured_footer = str(profile.get("footer_brand") or default_footer)
    document_title = extract_report_title(md_text) or in_path.stem
    cover_title = document_title.split("·", 1)[0].strip() if is_brief else document_title

    report_meta = {
        **profile,
        "report_title": cover_title,
        "document_title": document_title,
        "report_subtitle": default_subtitle,
        "report_lead": default_lead,
        "kicker": default_kicker,
        "footer_brand": configured_footer,
        "industry": extract_industry_from_md(md_text),
        "generated_date": now.strftime("%Y-%m-%d"),
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "skill_version": skill_version,
    }

    cover_style, cover_html = render_cover(profile, report_meta, jinja_env)

    toc_entries = build_toc(sections) if profile.get("include_toc", True) else []

    palette = resolve_palette(profile)
    design = resolve_design(report_kind, palette)

    rendered = template.render(
        profile=profile,
        palette=palette,
        design=design,
        sections=sections,
        cover_style=cover_style,
        cover_html=cover_html,
        include_toc=bool(profile.get("include_toc", True)),
        toc_entries=toc_entries,
        toc_page_label="第 2 页" if profile.get("include_toc", True) else "第 1 页",
        skill_name=skill_name,
        **{k: v for k, v in report_meta.items() if k not in ("include_toc", "include_methodology", "cover_style", "cover_html")},
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"已生成 HTML:{out_path}")


def extract_industry_from_md(md_text: str) -> str:
    m = re.search(r"^#\s+行业(?:法律)?(?:研究|调研)?报告\s*·\s*([^·\s]+)", md_text, re.M)
    return m.group(1).strip() if m else "—"


def extract_report_title(md_text: str) -> str:
    m = re.search(r"^#\s+(.+?)\s*$", md_text, re.M)
    return m.group(1).strip() if m else ""


def now_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def read_skill_identity(is_brief: bool) -> tuple[str, str]:
    skill_dir = SKILL_DIR
    if is_brief:
        sibling = SKILL_DIR.parent / "legal-client-brief"
        if (sibling / "SKILL.md").is_file():
            skill_dir = sibling
    skill_file = skill_dir / "SKILL.md"
    try:
        fm, _ = split_frontmatter(skill_file.read_text(encoding="utf-8"))
    except OSError:
        fm = {}
    fallback_name = "legal-client-brief" if is_brief else "legal-industry-report"
    return str(fm.get("name", fallback_name)), str(fm.get("version", "unknown"))


if __name__ == "__main__":
    main()
