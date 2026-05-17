#!/usr/bin/env python3
"""从 Markdown 文件中提取内联 SVG 并保存为独立文件。

用法：
    python extract_svgs.py <markdown_file> [--output <output_dir>]

示例：
    python extract_svgs.py manuscript/方法篇/ch06.md --output manuscript/方法篇/figures/
"""
import argparse
import os
import re
import sys
from pathlib import Path


SVG_OPEN = re.compile(r'<svg\b[^>]*>')
SVG_CLOSE = re.compile(r'</svg>')
FIG_CAPTION = re.compile(r'^\*\*图\s+(\d+)-(\d+)[:：]\s*(.+?)\*\*')
PLACEHOLDER = re.compile(r'\[\[FIG:(\d+):([^\]]+)\]\]')


def find_svgs(content):
    """找到所有 <svg>...</svg> 块及其起止位置。"""
    blocks = []
    pos = 0
    while True:
        m_open = SVG_OPEN.search(content, pos)
        if not m_open:
            break
        m_close = SVG_CLOSE.search(content, m_open.end())
        if not m_close:
            break
        end = m_close.end()
        blocks.append((m_open.start(), end, content[m_open.start():end]))
        pos = end
    return blocks


def find_caption(content, svg_end):
    """找到 SVG 块紧随的图注行，返回 (章节号, 序号, 标题) 或 None。"""
    after = content[svg_end:].lstrip('\n')
    first_line = after.split('\n', 1)[0].strip()
    m = FIG_CAPTION.match(first_line)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return None


def slugify(text, max_len=40):
    text = re.sub(r'[\\/:*?"<>|#\s]+', '-', text.strip())
    text = re.sub(r'-{2,}', '-', text)
    text = text.strip('-')
    return text[:max_len]


def extract(source_path, output_dir, dry_run=False):
    content = Path(source_path).read_text(encoding='utf-8')
    blocks = find_svgs(content)

    if not blocks:
        print('未找到 SVG 块。')
        return []

    os.makedirs(output_dir, exist_ok=True)
    results = []

    for idx, (start, end, svg_code) in enumerate(blocks, 1):
        cap = find_caption(content, end)
        if cap:
            ch, num, title = cap
            filename = f'ch{ch}-fig{num}-{slugify(title)}.svg'
        else:
            stem = Path(source_path).stem
            filename = f'{stem}-fig{idx:02d}.svg'

        out_path = os.path.join(output_dir, filename)

        if dry_run:
            print(f'  [{idx}] → {out_path} ({len(svg_code)} chars)')
        else:
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(svg_code)
                f.write('\n')
            print(f'  ✓ {out_path}')

        results.append(out_path)

    return results


def main():
    parser = argparse.ArgumentParser(description='从 Markdown 提取 SVG 到独立文件')
    parser.add_argument('source', help='Markdown 文件路径')
    parser.add_argument('--output', '-o', default='.', help='输出目录（默认当前目录）')
    parser.add_argument('--dry-run', action='store_true', help='只显示将提取的文件，不实际写入')
    args = parser.parse_args()

    if not os.path.isfile(args.source):
        print(f'文件不存在: {args.source}', file=sys.stderr)
        sys.exit(1)

    results = extract(args.source, args.output, args.dry_run)
    print(f'\n共提取 {len(results)} 个 SVG 文件到 {args.output}/')


if __name__ == '__main__':
    main()
