#!/usr/bin/env python3
"""
PDF 合并工具 - 支持添加页码序号

功能:
1. 合并多个 PDF 文件
2. 可选添加页码序号（每个文件编号 1、2、3...）
3. 支持自定义页码位置和样式

页码添加逻辑复用 pdf-add-page-numbers.py
"""

import sys
import argparse
from pathlib import Path
import importlib.util

try:
    import fitz  # PyMuPDF
    from pypdf import PdfMerger
except ImportError as e:
    print(f"错误: 缺少必需的依赖 - {e}")
    print("\n请运行以下命令安装:")
    print("  pip install pymupdf pypdf")
    sys.exit(1)

# 导入页码添加模块
script_dir = Path(__file__).parent
spec = importlib.util.spec_from_file_location("pdf_add_page_numbers",
                                              script_dir / "pdf-add-page-numbers.py")
pdf_add_page_numbers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pdf_add_page_numbers)

add_page_numbers_external = pdf_add_page_numbers.add_page_numbers


def merge_pdfs_with_numbering(input_files, output_file, add_numbers=True, position='bottom-right',
                               font_size=10, per_file_numbering=True):
    """
    合并多个 PDF 文件，并可选添加页码

    Args:
        input_files: 输入 PDF 文件列表
        output_file: 输出 PDF 文件路径
        add_numbers: 是否添加页码
        position: 页码位置
        font_size: 字体大小
        per_file_numbering: True=每个文件独立编号(1,2,3...); False=全局连续编号
    """
    print("=" * 60)
    print("PDF 合并工具")
    print("=" * 60)

    # 验证输入文件
    valid_files = []
    for file_path in input_files:
        path = Path(file_path)
        if not path.exists():
            print(f"⚠️  跳过不存在的文件: {file_path}")
            continue
        if not path.suffix.lower() == '.pdf':
            print(f"⚠️  跳过非 PDF 文件: {file_path}")
            continue
        valid_files.append(str(path))

    if len(valid_files) == 0:
        print("\n✗ 没有有效的 PDF 文件可合并")
        sys.exit(1)

    print(f"\n准备合并 {len(valid_files)} 个文件:")
    for i, file_path in enumerate(valid_files, 1):
        print(f"  {i}. {Path(file_path).name}")

    # 如果需要添加页码，先处理每个文件
    if add_numbers:
        print(f"\n{'=' * 60}")
        print(f"步骤 1/2: 为每个文件添加页码序号")
        print(f"{'=' * 60}")

        import tempfile
        import shutil
        temp_dir = Path(tempfile.mkdtemp())
        temp_files = []

        for i, file_path in enumerate(valid_files, 1):
            doc = fitz.open(file_path)
            page_count = len(doc)
            doc.close()

            temp_file = temp_dir / f"numbered_{i}.pdf"

            if per_file_numbering:
                print(f"文件 {i}/{len(valid_files)}: {Path(file_path).name} ({page_count} 页) - 编号 1~{page_count}")
                add_page_numbers_external(file_path, str(temp_file), position=position,
                                         font_size=font_size, start_num=1)
            else:
                # 全局连续编号
                start_num = sum(len(fitz.open(f)) for f in valid_files[:i-1]) + 1
                end_num = start_num + page_count - 1
                print(f"文件 {i}/{len(valid_files)}: {Path(file_path).name} ({page_count} 页) - 编号 {start_num}~{end_num}")
                add_page_numbers_external(file_path, str(temp_file), position=position,
                                         font_size=font_size, start_num=start_num)

            temp_files.append(str(temp_file))

        # 使用添加了页码的临时文件进行合并
        files_to_merge = temp_files
    else:
        files_to_merge = valid_files

    # 合并 PDF
    print(f"\n{'=' * 60}")
    print(f"步骤 {'2/2' if add_numbers else '1/1'}: 合并 PDF 文件")
    print(f"{'=' * 60}")

    merger = PdfMerger()

    for i, file_path in enumerate(files_to_merge, 1):
        print(f"添加文件 {i}/{len(files_to_merge)}: {Path(valid_files[i-1]).name}")
        merger.append(file_path)

    # 保存合并后的文件
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    merger.write(output_file)
    merger.close()

    # 清理临时文件
    if add_numbers:
        import shutil
        shutil.rmtree(temp_dir)

    # 统计信息
    final_doc = fitz.open(output_file)
    total_pages = len(final_doc)
    final_doc.close()

    print(f"\n{'=' * 60}")
    print("合并完成!")
    print(f"{'=' * 60}")
    print(f"文件数量: {len(valid_files)}")
    print(f"总页数: {total_pages}")
    if add_numbers:
        numbering_mode = "每个文件独立编号 (1, 2, 3...)" if per_file_numbering else "全局连续编号"
        print(f"页码模式: {numbering_mode}")
        print(f"页码位置: {position}")
    print(f"输出文件: {output_file}")
    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(
        description='PDF 合并工具 - 支持添加页码序号',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本合并（不添加页码）
  python pdf-merge.py -i file1.pdf file2.pdf file3.pdf -o merged.pdf

  # 合并并添加页码（每个文件独立编号：1,2,3...）
  python pdf-merge.py -i file1.pdf file2.pdf file3.pdf -o merged.pdf --add-numbers

  # 合并并添加页码（全局连续编号）
  python pdf-merge.py -i file1.pdf file2.pdf -o merged.pdf --add-numbers --continuous

  # 自定义页码位置
  python pdf-merge.py -i file1.pdf file2.pdf -o merged.pdf --add-numbers --position bottom-center

  # 自定义字体大小
  python pdf-merge.py -i file1.pdf file2.pdf -o merged.pdf --add-numbers --font-size 12

页码位置选项:
  - bottom-right   (右下角，默认)
  - bottom-center  (底部居中)
  - bottom-left    (左下角)
  - top-right      (右上角)
  - top-center     (顶部居中)
  - top-left       (左上角)
        """
    )

    parser.add_argument('--input', '-i', nargs='+', required=True,
                        help='输入 PDF 文件列表（用空格分隔）')
    parser.add_argument('--output', '-o', required=True,
                        help='输出 PDF 文件')
    parser.add_argument('--add-numbers', action='store_true',
                        help='添加页码序号')
    parser.add_argument('--continuous', action='store_true',
                        help='使用全局连续编号（默认每个文件独立编号）')
    parser.add_argument('--position', default='bottom-right',
                        choices=['bottom-right', 'bottom-center', 'bottom-left',
                                'top-right', 'top-center', 'top-left'],
                        help='页码位置（默认: bottom-right）')
    parser.add_argument('--font-size', type=int, default=10,
                        help='页码字体大小（默认: 10）')

    args = parser.parse_args()

    try:
        merge_pdfs_with_numbering(
            args.input,
            args.output,
            add_numbers=args.add_numbers,
            position=args.position,
            font_size=args.font_size,
            per_file_numbering=not args.continuous
        )
    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
