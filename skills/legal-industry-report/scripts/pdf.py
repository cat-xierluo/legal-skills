#!/usr/bin/env python3
"""行业报告 / 客户简报 PDF 渲染器：HTML → A4 PDF。"""

from __future__ import annotations

import argparse
import sys
from html import escape
from pathlib import Path

# 页边距、页眉与页脚均由模板内 @page 规则控制，避免两套设置互相叠加。
ZERO_MARGIN = {"top": "0", "bottom": "0", "left": "0", "right": "0"}


def _launch_browser(playwright):
    """优先使用本机 Chrome；不存在时回退 Playwright 自带 Chromium。"""
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return playwright.chromium.launch(executable_path=candidate)
    try:
        return playwright.chromium.launch()
    except Exception as exc:
        print("[error] 未找到可用浏览器。请运行: python3 -m playwright install chromium", file=sys.stderr)
        raise RuntimeError("browser unavailable") from exc


def _render_part(browser, content: str, style: str, title: str, *, margin, body_class: str = "") -> bytes:
    """渲染一部分 HTML；页眉、页脚和边距以模板内 @page 为单一权威。"""
    html = (
        f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f'<title>{escape(title)}</title>{style}</head>'
        f'<body class="{escape(body_class, quote=True)}">{content}</body></html>'
    )
    page = browser.new_page()
    page.set_content(html, wait_until="networkidle")
    page.emulate_media(media="screen")
    pdf_bytes = page.pdf(print_background=True, margin=margin, prefer_css_page_size=True)
    page.close()
    return pdf_bytes


def render_playwright(html_path: Path, pdf_path: Path) -> bool:
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
            browser = _launch_browser(p)
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri())
            page.wait_for_load_state("networkidle")

            style = page.evaluate('document.querySelector("style").outerHTML')
            title = page.evaluate('document.title') or ""
            body_class = page.evaluate('document.body.className') or ""

            cover = page.evaluate(
                'document.querySelector(".cover-page")?document.querySelector(".cover-page").outerHTML:""'
            )
            # 其他 page（toc + sections + meta）作为整体正文
            body_pages = page.evaluate(
                'Array.from(document.querySelectorAll(".page:not(.cover-page)")).map(e=>e.outerHTML).join("\\n")'
            )
            browser.close()

            browser = _launch_browser(p)
            pdfs = []
            if cover:
                pdfs.append(_render_part(browser, cover, style, title, margin=ZERO_MARGIN, body_class=body_class))
            if body_pages:
                pdfs.append(_render_part(browser, body_pages, style, title, margin=ZERO_MARGIN, body_class=body_class))
            browser.close()

        out = fitz.open()
        for b in pdfs:
            tmp = fitz.open("pdf", b)
            out.insert_pdf(tmp)
            tmp.close()
        out.save(str(pdf_path))
        out.close()
        if not validate_pdf_geometry(pdf_path):
            return False
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
            browser = _launch_browser(p)
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri())
            page.wait_for_load_state("networkidle")
            page.emulate_media(media="screen")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin=ZERO_MARGIN,
            )
            browser.close()
        if not validate_pdf_geometry(pdf_path):
            return False
        print(f"已生成 PDF(playwright 单 PDF 回退):{pdf_path}")
        return True
    except Exception as e:
        print(f"[error] 单 PDF 回退也失败:{e}", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser(description="行业法律报告 HTML → A4 PDF")
    ap.add_argument("--input", "-i", required=True, help="HTML 路径")
    ap.add_argument("--output", "-o", required=True, help="输出 PDF 路径")
    ap.add_argument("--profile", "-p", default=None, help="保留兼容；品牌信息已经写入 HTML")
    args = ap.parse_args()

    in_path = Path(args.input).resolve()
    out_path = Path(args.output).resolve()

    if not in_path.is_file():
        print(f"[error] 输入 HTML 不存在: {in_path}", file=sys.stderr)
        raise SystemExit(2)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ok = render_playwright(in_path, out_path)
    if not ok:
        sys.exit(1)


def validate_pdf_geometry(pdf_path: Path) -> bool:
    """检查最终件存在、非空且每页为 A4；缺 PyMuPDF 时给出可理解的降级提示。"""
    try:
        import fitz
    except ImportError:
        print("[warn] 未安装 PyMuPDF，已跳过最终 PDF 页尺寸复核", file=sys.stderr)
        return pdf_path.is_file() and pdf_path.stat().st_size > 0
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            print("[error] 生成的 PDF 没有页面", file=sys.stderr)
            return False
        expected = (595.28, 841.89)
        for index, page in enumerate(doc, 1):
            rect = page.rect
            if abs(rect.width - expected[0]) > 1.0 or abs(rect.height - expected[1]) > 1.0:
                print(
                    f"[error] 第 {index} 页不是 A4: {rect.width:.2f} x {rect.height:.2f} pt",
                    file=sys.stderr,
                )
                return False
        return True
    except Exception as exc:
        print(f"[error] 无法复核最终 PDF: {exc}", file=sys.stderr)
        return False


if __name__ == "__main__":
    main()
