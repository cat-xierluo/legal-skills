#!/usr/bin/env python3
"""
PDF 页码添加工具

为 PDF 添加页码，支持精确的边距控制（毫米单位）
"""

import sys
import argparse
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError as e:
    print(f"错误: 缺少必需的依赖 - {e}")
    print("\n请运行以下命令安装:")
    print("  pip install pymupdf")
    sys.exit(1)


def mm_to_points(mm):
    """将毫米转换为点（PDF 单位）"""
    return mm * 2.83465


def add_page_numbers(
    input_pdf,
    output_pdf,
    position='bottom-right',
    font_name='helv',
    font_size=15,
    start_num=1,
    margin_top=10.0,
    margin_bottom=5.0,
    margin_left=15.0,
    margin_right=15.0
):
    """
    为 PDF 添加页码

    Args:
        input_pdf: 输入 PDF 文件路径
        output_pdf: 输出 PDF 文件路径
        position: 页码位置 ('bottom-right', 'bottom-center', 'bottom-left', 'top-right', 'top-center', 'top-left')
        font_name: 字体名称 ('helv'=Helvetica, 'times'=Times, 'cour'=Courier)
        font_size: 字体大小（点）
        start_num: 起始页码
        margin_top: 顶部边距（毫米）
        margin_bottom: 底部边距（毫米）
        margin_left: 左侧边距（毫米）
        margin_right: 右侧边距（毫米）
    """
    print("=" * 60)
    print("PDF 页码添加工具")
    print("=" * 60)

    # 打开 PDF
    doc = fitz.open(input_pdf)
    total_pages = len(doc)

    print(f"\n输入文件: {input_pdf}")
    print(f"总页数: {total_pages}")
    print(f"\n页码设置:")
    print(f"  位置: {position}")
    print(f"  字体: {font_name.upper()} {font_size}pt")
    print(f"  起始页码: {start_num}")
    print(f"  边距: 上={margin_top}mm, 下={margin_bottom}mm, 左={margin_left}mm, 右={margin_right}mm")

    # 转换边距为点
    top_pt = mm_to_points(margin_top)
    bottom_pt = mm_to_points(margin_bottom)
    left_pt = mm_to_points(margin_left)
    right_pt = mm_to_points(margin_right)

    # 处理每一页
    for page_num in range(total_pages):
        page = doc[page_num]
        page_rect = page.rect

        # 计算页码文本
        page_number = start_num + page_num
        text = str(page_number)

        # 估算文本宽度（简化计算）
        text_width = len(text) * font_size * 0.6

        # 根据位置计算坐标
        if position == 'bottom-right':
            x = page_rect.width - right_pt - text_width
            y = page_rect.height - bottom_pt
        elif position == 'bottom-center':
            x = (page_rect.width - text_width) / 2
            y = page_rect.height - bottom_pt
        elif position == 'bottom-left':
            x = left_pt
            y = page_rect.height - bottom_pt
        elif position == 'top-right':
            x = page_rect.width - right_pt - text_width
            y = top_pt + font_size
        elif position == 'top-center':
            x = (page_rect.width - text_width) / 2
            y = top_pt + font_size
        elif position == 'top-left':
            x = left_pt
            y = top_pt + font_size
        else:
            # 默认右下角
            x = page_rect.width - right_pt - text_width
            y = page_rect.height - bottom_pt

        # 添加页码文本
        page.insert_text(
            fitz.Point(x, y),
            text,
            fontsize=font_size,
            color=(0, 0, 0),  # 黑色
            fontname=font_name
        )

        if (page_num + 1) % 10 == 0:
            print(f"处理进度: {page_num + 1}/{total_pages} 页")

    # 保存
    Path(output_pdf).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_pdf)
    doc.close()

    print(f"\n{'=' * 60}")
    print("完成!")
    print(f"{'=' * 60}")
    print(f"输出文件: {output_pdf}")
    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(
        description='PDF 页码添加工具 - 支持精确边距控制（毫米单位）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认设置（底端右边，15pt Helvetica，边距：上10mm/下5mm/左右15mm）
  python pdf-add-page-numbers.py -i input.pdf -o output.pdf

  # 自定义位置和字体大小
  python pdf-add-page-numbers.py -i input.pdf -o output.pdf --position bottom-center --font-size 12

  # 自定义边距
  python pdf-add-page-numbers.py -i input.pdf -o output.pdf --margin-top 15 --margin-bottom 10

  # 从第5页开始编号
  python pdf-add-page-numbers.py -i input.pdf -o output.pdf --start 5

  # 使用 Times 字体
  python pdf-add-page-numbers.py -i input.pdf -o output.pdf --font times

页码位置选项:
  - bottom-right   (底端右边，默认)
  - bottom-center  (底端居中)
  - bottom-left    (底端左边)
  - top-right      (顶端右边)
  - top-center     (顶端居中)
  - top-left       (顶端左边)

字体选项:
  - helv    (Helvetica，默认)
  - times   (Times Roman)
  - cour    (Courier)
        """
    )

    parser.add_argument('--input', '-i', required=True,
                        help='输入 PDF 文件')
    parser.add_argument('--output', '-o', required=True,
                        help='输出 PDF 文件')
    parser.add_argument('--position', default='bottom-right',
                        choices=['bottom-right', 'bottom-center', 'bottom-left',
                                'top-right', 'top-center', 'top-left'],
                        help='页码位置（默认: bottom-right）')
    parser.add_argument('--font', default='helv',
                        choices=['helv', 'times', 'cour'],
                        help='字体名称（默认: helv=Helvetica）')
    parser.add_argument('--font-size', type=float, default=15,
                        help='字体大小（点，默认: 15）')
    parser.add_argument('--start', type=int, default=1,
                        help='起始页码（默认: 1）')
    parser.add_argument('--margin-top', type=float, default=10.0,
                        help='顶部边距（毫米，默认: 10.0）')
    parser.add_argument('--margin-bottom', type=float, default=5.0,
                        help='底部边距（毫米，默认: 5.0）')
    parser.add_argument('--margin-left', type=float, default=15.0,
                        help='左侧边距（毫米，默认: 15.0）')
    parser.add_argument('--margin-right', type=float, default=15.0,
                        help='右侧边距（毫米，默认: 15.0）')

    args = parser.parse_args()

    # 验证输入文件
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误: 输入文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        add_page_numbers(
            args.input,
            args.output,
            position=args.position,
            font_name=args.font,
            font_size=args.font_size,
            start_num=args.start,
            margin_top=args.margin_top,
            margin_bottom=args.margin_bottom,
            margin_left=args.margin_left,
            margin_right=args.margin_right
        )
    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
