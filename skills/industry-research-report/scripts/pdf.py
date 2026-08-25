#!/usr/bin/env python3
"""行业法律调研报告 PDF 渲染:HTML → A4 PDF

封面 / 后部全幅(margin 0)+ 正文带页眉页脚页码,
通过 Playwright 分部分渲染 + pymupdf 合并实现(单 PDF 不能分页不同 margin)。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 正文 margin:仅 bottom 预留 16mm 给页脚(横线距底 ~14mm),其余 0 让 CSS padding 主导
BODY_MARGIN = {"top": "0", "bottom": "16mm", "left": "0", "right": "0"}
ZERO_MARGIN = {"top": "0", "bottom": "0", "left": "0", "right": "0"}
HEADER_TEMPLATE = '<div></div>'  # 蓝皮书体例不使用 Playwright header;页眉由 HTML 内 .section-header 承担

# 页脚:左"律所名 · 系列名" / 右"报告名 · 页码/总页数",金色横线,160mm 内容宽
# 颜色从 profile 注入;默认 bluebook (#1B3C59 / #D4AF37)
FOOTER_TEMPLATE_TPL = (
    '<div style="width:100%;font-family:serif;font-size:9px;color:{primary};padding:0 0 9mm;">'
    '<div style="width:160mm;margin:0 25mm;border-top:1px solid {accent};padding-top:2mm;'
    'display:flex;justify-content:space-between;">'
    '<span>{firm} · {series}</span>'
    '<span>{footer_brand} · <span class="pageNumber"></span> / <span class="totalPages"></span></span>'
    '</div></div>'
)


def _render_part(browser, content: str, style: str, title: str, *, margin, footer: bool = False, profile: dict = None) -> bytes:
    """渲染一部分 HTML 为 PDF 字节。footer=True 时按 profile 注入页脚信息。"""
    html = (
        f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f'<title>{title}</title>{style}</head><body>{content}</body></html>'
    )
    page = browser.new_page()
    page.set_content(html, wait_until="networkidle")
    page.emulate_media(media="screen")
    kwargs = dict(print_background=True, margin=margin)
    if footer and profile:
        # 从 profile 解析 palette,得到主色和强调色;若 profile 含 primary/accent 字段则直接用
        primary = profile.get("primary") or _palette_primary(profile.get("color_palette", "bluebook"))
        accent = profile.get("accent") or _palette_accent(profile.get("color_palette", "bluebook"))
        # accent_color 字段也作为覆盖
        accent_override = profile.get("accent_color", "").strip()
        if accent_override and accent_override.startswith("#"):
            accent = accent_override
        footer_tpl = FOOTER_TEMPLATE_TPL.format(
            firm=profile.get("law_firm", ""),
            series=profile.get("series_name", ""),
            footer_brand=profile.get("footer_brand", "行业法律调研报告"),
            primary=primary,
            accent=accent,
        )
        kwargs.update(
            format="A4", prefer_css_page_size=False,
            display_header_footer=True,
            header_template=HEADER_TEMPLATE,
            footer_template=footer_tpl,
        )
    else:
        kwargs.update(prefer_css_page_size=True)
    pdf_bytes = page.pdf(**kwargs)
    page.close()
    return pdf_bytes


def render_playwright(html_path: Path, pdf_path: Path, profile: dict) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[info] playwright 未安装,无法生成 PDF", file=sys.stderr)
        return False
    try:
        import fitz  # pymupdf
    except ImportError:
        print("[warn] pymupdf 未装,无法分部分合并,回退单 PDF", file=sys.stderr)
        return _render_playwright_single(html_path, pdf_path)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri())
            page.wait_for_load_state("networkidle")

            style = page.evaluate('document.querySelector("style").outerHTML')
            title = page.evaluate('document.title') or ""

            cover = page.evaluate(
                'document.querySelector(".cover-page")?document.querySelector(".cover-page").outerHTML:""'
            )
            # 其他 page（toc + sections + meta）作为整体正文
            body_pages = page.evaluate(
                'Array.from(document.querySelectorAll(".page:not(.cover-page)")).map(e=>e.outerHTML).join("\\n")'
            )
            browser.close()

            browser = p.chromium.launch(channel="chrome")
            pdfs = []
            if cover:
                pdfs.append(_render_part(browser, cover, style, title, margin=ZERO_MARGIN))
            if body_pages:
                pdfs.append(_render_part(browser, body_pages, style, title, margin=BODY_MARGIN, footer=True, profile=profile))
            browser.close()

        out = fitz.open()
        for b in pdfs:
            tmp = fitz.open("pdf", b)
            out.insert_pdf(tmp)
            tmp.close()
        out.save(str(pdf_path))
        out.close()
        print(f"已生成 PDF(playwright 分部分渲染 + 合并):{pdf_path}")
        return True
    except Exception as e:
        print(f"[warn] playwright B 方案失败:{e},回退单 PDF", file=sys.stderr)
        return _render_playwright_single(html_path, pdf_path)


def _render_playwright_single(html_path: Path, pdf_path: Path) -> bool:
    """回退:单次 page.pdf() 渲染全 HTML。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri())
            page.wait_for_load_state("networkidle")
            page.emulate_media(media="screen")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0", "bottom": "16mm", "left": "0", "right": "0"},
            )
            browser.close()
        print(f"已生成 PDF(playwright 单 PDF 回退):{pdf_path}")
        return True
    except Exception as e:
        print(f"[error] 单 PDF 回退也失败:{e}", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser(description="行业调研报告 HTML → A4 PDF")
    ap.add_argument("--input", "-i", required=True, help="HTML 路径")
    ap.add_argument("--output", "-o", required=True, help="输出 PDF 路径")
    ap.add_argument("--profile", "-p", default=None, help="report-profile.md 路径,用于页脚品牌信息")
    args = ap.parse_args()

    in_path = Path(args.input).resolve()
    out_path = Path(args.output).resolve()

    profile = {}
    if args.profile:
        try:
            import yaml
            text = Path(args.profile).read_text(encoding="utf-8")
            if text.startswith("---\n"):
                end = text.find("\n---\n", 4)
                if end != -1:
                    profile = yaml.safe_load(text[4:end]) or {}
        except Exception as e:
            print(f"[warn] 读取 profile 失败:{e},页脚用默认", file=sys.stderr)

    ok = render_playwright(in_path, out_path, profile)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
