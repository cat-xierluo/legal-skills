#!/usr/bin/env python3
"""
PDF 水印去除工具

检测并移除 PDF 中的水印元素
支持文字水印、图像水印等常见类型
"""

import sys
import argparse
from pathlib import Path
import re

try:
    import fitz  # PyMuPDF
except ImportError as e:
    print(f"错误: 缺少必需的依赖 - {e}")
    print("\n请运行以下命令安装:")
    print("  pip install pymupdf")
    sys.exit(1)


def detect_watermarks(page):
    """
    检测页面中的水印元素

    Args:
        page: PyMuPDF 页面对象

    Returns:
        list: 水印元素列表，每个元素包含 (xref, 类型, 描述)
    """
    watermarks = []

    # 检查页面中的所有元素
    blocks = page.get_text("dict")

    # 1. 检测透明度较低的元素（可能是水印）
    for block in blocks.get("blocks", []):
        if block.get("type") == 0:  # 文本
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    # 检查字体颜色和透明度
                    color = span.get("color", (0, 0, 0))
                    flags = span.get("flags", 0)

                    # 浅灰色文字通常是水印
                    if isinstance(color, (list, tuple)) and len(color) >= 3:
                        gray_value = sum(color[:3]) / 3
                        if gray_value > 0.8:  # 浅色
                            watermarks.append({
                                'type': 'text',
                                'bbox': span.get("bbox"),
                                'text': span.get("text"),
                                'color': color
                            })

        elif block.get("type") == 1:  # 图像
            for img in block.get("image", []):
                # 检查图像透明度
                if img.get("colorspace") == "DeviceGray":
                    # 灰度图像，检查是否是水印
                    watermarks.append({
                        'type': 'image',
                        'bbox': block.get("bbox"),
                        'xref': img.get("xref")
                    })

    # 2. 检查特定水印模式
    text = page.get_text()

    # 常见水印关键词
    watermark_keywords = [
        r'机密',
        r'保密',
        r'内部.*资料',
        r'仅供参考',
        r'草稿',
        r'样本',
        r'样稿',
        r'评估',
        r'非正式',
        r'未.*正式.*生效',
        r'未经许可.*转载',
        r'版权所有',
        r'Copyright',
        r'Confidential',
        r'Draft',
        r'Sample',
        r'Evaluation',
        r'Not.*Official',
    ]

    for pattern in watermark_keywords:
        if re.search(pattern, text, re.IGNORECASE):
            # 尝试定位这些文本
            instances = page.search_for(pattern)
            for inst in instances:
                watermarks.append({
                    'type': 'keyword',
                    'text': pattern,
                    'bbox': inst
                })

    return watermarks


def remove_watermark_page(page, watermarks):
    """
    从页面中移除水印元素

    Args:
        page: PyMuPDF 页面对象
        watermarks: 水印元素列表

    Returns:
        int: 移除的水印数量
    """
    if not watermarks:
        return 0

    # 创建新页面，不包含水印
    # 注意：这是一个简化版本，复杂的水印可能需要更复杂的处理

    # 获取所有非水印内容
    # 使用 pymupdf 的页面清洗功能
    cleaned_page = page

    # 对于文字水印，尝试删除包含水印文本的文本块
    removed_count = 0
    for wm in watermarks:
        if wm['type'] == 'keyword':
            try:
                # 尝试删除包含水印关键词的文本
                text_instances = cleaned_page.search_for(wm['text'])
                for inst in text_instances:
                    # redact（涂黑）然后删除
                    cleaned_page.add_redact_annot(inst)
                    cleaned_page.apply_redactions()
                    removed_count += 1
            except:
                pass

    return removed_count


def remove_watermarks(input_pdf, output_pdf):
    """
    移除 PDF 中的水印

    Args:
        input_pdf: 输入 PDF 文件
        output_pdf: 输出 PDF 文件

    Returns:
        dict: 处理结果统计
    """
    print(f"正在处理 PDF: {input_pdf}")

    try:
        pdf_document = fitz.open(input_pdf)
        total_pages = len(pdf_document)
        print(f"共 {total_pages} 页")

        stats = {
            'total_pages': total_pages,
            'pages_with_watermarks': 0,
            'total_watermarks_removed': 0
        }

        # 创建新 PDF
        output_pdf_document = fitz.open()

        for page_num, page in enumerate(pdf_document, 1):
            print(f"处理第 {page_num}/{total_pages} 页...", end=' ')

            # 检测水印
            watermarks = detect_watermarks(page)

            if watermarks:
                print(f"发现 {len(watermarks)} 个水印", end=' ')
                stats['pages_with_watermarks'] += 1

                # 尝试移除水印
                removed = remove_watermark_page(page, watermarks)
                stats['total_watermarks_removed'] += removed

                if removed > 0:
                    print(f"已移除 {removed} 个", end=' ')
                else:
                    print("无法自动移除", end=' ')

                # 复制页面到新文档（即使无法完全移除）
                output_pdf_document.new_page(pdfpage=page)

            else:
                print("未发现水印")
                # 直接复制页面
                output_pdf_document.new_page(pdfpage=page)

            print()

        # 保存结果
        print(f"\n正在保存到: {output_pdf}")
        Path(output_pdf).parent.mkdir(parents=True, exist_ok=True)
        output_pdf_document.save(output_pdf)
        output_pdf_document.close()
        pdf_document.close()

        return stats

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'message': str(e)
        }


def main():
    parser = argparse.ArgumentParser(
        description='PDF 水印去除工具 - 移除 PDF 中的水印',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本使用
  python pdf-remove-watermark.py -i input.pdf -o output.pdf
        """
    )

    parser.add_argument('--input', '-i', required=True, help='输入 PDF 文件')
    parser.add_argument('--output', '-o', required=True, help='输出 PDF 文件')

    args = parser.parse_args()

    # 验证输入文件
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误: 输入文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    # 执行水印去除
    result = remove_watermarks(args.input, args.output)

    # 显示结果
    if 'status' in result and result['status'] == 'error':
        print(f"\n错误: {result['message']}", file=sys.stderr)
        sys.exit(1)
    else:
        print("\n" + "=" * 50)
        print("处理完成！")
        print(f"总页数: {result['total_pages']}")
        print(f"包含水印的页数: {result['pages_with_watermarks']}")
        print(f"移除的水印数: {result['total_watermarks_removed']}")
        print(f"输出文件: {args.output}")
        print("=" * 50)


if __name__ == '__main__':
    main()
