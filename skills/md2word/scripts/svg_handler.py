#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SVG 处理模块
将 Markdown 中的内联 <svg>...</svg> 块渲染为 PNG 并插入 Word。

渲染策略（按优先级自动选择可用者）：
1. rsvg-convert（librsvg，轻快，svg-book-illustrator 门禁同款）
2. cairosvg（pip install cairosvg）
3. svg2png.js + puppeteer（scripts/svg2png.js，Node，复用 svg-book-illustrator 实现）
4. 失败时由调用方降级为代码框（显示 SVG 源码）
"""

import os
import shutil
import subprocess

from PIL import Image


def render_svg_to_png(svg_path, png_path, zoom=6):
    """把 SVG 文件渲染为 PNG。成功返回 png_path，失败返回 None。

    Args:
        svg_path: 输入 .svg 文件路径
        png_path: 输出 .png 文件路径
        zoom: 像素缩放倍数（3≈印刷级清晰度，按 viewBox 原尺寸放大）
    """
    # 策略1: rsvg-convert（轻快，已验证可渲染书稿含中文标签的 SVG）
    rsvg = shutil.which('rsvg-convert')
    if rsvg:
        try:
            cmd = [rsvg, '-z', str(zoom), '-o', png_path, svg_path]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and os.path.exists(png_path):
                return png_path
            print(f"⚠️  rsvg-convert 渲染失败: {(r.stderr or '').strip()}")
        except Exception as e:
            print(f"⚠️  rsvg-convert 异常: {e}")

    # 策略2: cairosvg（纯 Python，pip install cairosvg）
    try:
        import cairosvg
        cairosvg.svg2png(url=svg_path, write_to=png_path, scale=zoom)
        if os.path.exists(png_path):
            return png_path
    except ImportError:
        pass
    except Exception as e:
        print(f"⚠️  cairosvg 渲染失败: {e}")

    # 策略3: svg2png.js + puppeteer（复用 svg-book-illustrator 实现，透明背景 600DPI）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    svg2png_js = os.path.join(script_dir, 'svg2png.js')
    if shutil.which('node') and os.path.exists(svg2png_js):
        try:
            dpi = int(96 * zoom)
            r = subprocess.run(['node', svg2png_js, svg_path, png_path, str(dpi)],
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 0 and os.path.exists(png_path):
                return png_path
            print(f"⚠️  svg2png.js 渲染失败: {(r.stderr or '').strip()[:120]}")
        except Exception as e:
            print(f"⚠️  svg2png.js 异常: {e}")

    return None


def render_inline_svg(insert_image_func, svg_code, md_file_path, idx):
    """渲染内联 SVG 代码并插入 Word 文档。

    Args:
        insert_image_func: 插入 PIL Image 到 Word 的函数（md2word.insert_image_to_word）
        svg_code: 内联 SVG 源码（<svg>...</svg>）
        md_file_path: Markdown 文件路径（用于派生图片输出目录，与 mermaid 一致）
        idx: 该文件内第几个 SVG（用于命名，从 0 起）
    Returns:
        True 插入成功；False 失败（调用方应降级为代码框）
    """
    md_base = os.path.splitext(os.path.basename(md_file_path))[0]
    out_dir = os.path.join(os.path.dirname(os.path.abspath(md_file_path)), f"{md_base}_images")
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        print(f"⚠️  创建 SVG 输出目录失败: {e}")
        return False

    svg_path = os.path.join(out_dir, f"{md_base}-svg-{idx}.svg")
    png_path = os.path.join(out_dir, f"{md_base}-svg-{idx}.png")

    try:
        with open(svg_path, 'w', encoding='utf-8') as f:
            f.write(svg_code)
    except Exception as e:
        print(f"⚠️  写入 SVG 文件失败: {e}")
        return False

    png = render_svg_to_png(svg_path, png_path, zoom=6)
    if not png:
        print(f"⚠️  内联SVG {idx} 渲染失败（无可用渲染器：rsvg-convert / cairosvg / svg2png.js）")
        return False

    try:
        image = Image.open(png)
        image.load()
        insert_image_func(image)
        print(f"✅ 内联SVG {idx} 渲染插入: {os.path.basename(png)}")
        return True
    except Exception as e:
        print(f"⚠️  内联SVG {idx} 插入失败: {e}")
        return False
