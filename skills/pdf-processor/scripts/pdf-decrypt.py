#!/usr/bin/env python3
"""
PDF 解密工具

移除 PDF 密码保护，使其可以正常编辑和处理
"""

import sys
import argparse
from pathlib import Path

try:
    import pypdf
except ImportError as e:
    print(f"错误: 缺少必需的依赖 - {e}")
    print("\n请运行以下命令安装:")
    print("  pip install pypdf")
    sys.exit(1)


def is_encrypted(pdf_path):
    """检查 PDF 是否加密"""
    try:
        with open(pdf_path, 'rb') as f:
            reader = pypdf.PdfReader(f)
            return reader.is_encrypted
    except Exception as e:
        print(f"检查文件时出错: {e}")
        return False


def decrypt_pdf(input_pdf, output_pdf, password=''):
    """
    移除 PDF 密码保护

    Args:
        input_pdf: 输入 PDF 文件
        output_pdf: 输出 PDF 文件
        password: PDF 密码（如果有）

    Returns:
        dict: 处理结果
    """
    print(f"正在处理 PDF: {input_pdf}")

    try:
        with open(input_pdf, 'rb') as f:
            reader = pypdf.PdfReader(f)

            if not reader.is_encrypted:
                print("PDF 未加密，无需解密")
                # 直接复制文件
                import shutil
                shutil.copy2(input_pdf, output_pdf)
                return {
                    'status': 'not_encrypted',
                    'message': 'PDF 未加密'
                }

            print(f"PDF 已加密，尝试解密...")

            # 尝试解密
            if reader.decrypt(password):
                print("解密成功！")

                # 写入解密后的 PDF
                writer = pypdf.PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)

                with open(output_pdf, 'wb') as f:
                    writer.write(f)

                return {
                    'status': 'success',
                    'message': '解密成功'
                }
            else:
                return {
                    'status': 'failed',
                    'message': '解密失败，密码可能不正确'
                }

    except Exception as e:
        return {
            'status': 'error',
            'message': f'处理失败: {e}'
        }


def main():
    parser = argparse.ArgumentParser(
        description='PDF 解密工具 - 移除 PDF 密码保护',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本使用（尝试空密码）
  python pdf-decrypt.py -i input.pdf -o output.pdf

  # 使用指定密码
  python pdf-decrypt.py -i input.pdf -o output.pdf --password 123456
        """
    )

    parser.add_argument('--input', '-i', required=True, help='输入 PDF 文件')
    parser.add_argument('--output', '-o', required=True, help='输出 PDF 文件')
    parser.add_argument('--password', '-p', default='',
                        help='PDF 密码（默认尝试空密码）')

    args = parser.parse_args()

    # 验证输入文件
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误: 输入文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    # 创建输出目录
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 执行解密
    result = decrypt_pdf(args.input, args.output, args.password)

    # 显示结果
    print("\n" + "=" * 50)
    if result['status'] == 'success':
        print("✓ 处理完成！")
        print(f"输出文件: {args.output}")
    elif result['status'] == 'not_encrypted':
        print("✓ 无需处理（未加密）")
        print(f"输出文件: {args.output}")
    elif result['status'] == 'failed':
        print("✗ 处理失败")
        print(f"原因: {result['message']}")
        sys.exit(1)
    else:
        print("✗ 处理失败")
        print(f"原因: {result['message']}")
        sys.exit(1)
    print("=" * 50)


if __name__ == '__main__':
    main()
