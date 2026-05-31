#!/usr/bin/env python3
"""
PDF 页面旋转工具 (v2.1)

支持：
- 手动指定角度旋转 (90/180/270/-90/-180/-270)
- 自动检测并矫正 90° 倍数的页面旋转 (使用 Tesseract OSD)

图像处理逻辑复用 pdf-preprocess-core.py 的 PDFPreprocessor
"""

import sys
import argparse
from pathlib import Path

# 导入核心处理模块
import importlib.util
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

spec = importlib.util.spec_from_file_location("pdf_preprocess_core",
                                              script_dir / "pdf-preprocess-core.py")
pdf_preprocess_core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pdf_preprocess_core)

PDFPreprocessor = pdf_preprocess_core.PDFPreprocessor
convert_from_path = pdf_preprocess_core.convert_from_path
HAS_PYTESSERACT = pdf_preprocess_core.HAS_PYTESSERACT


def rotate_pdf(input_path: str, output_path: str,
               angle: int | None = None,
               auto_rotate: bool = False,
               confidence_threshold: float = 0.5,
               crop: bool = True,
               dpi: int = 300,
               verbose: bool = True) -> dict:
    """旋转 PDF 文件"""
    preprocessor = PDFPreprocessor(dpi=dpi)

    if verbose:
        print(f"正在读取 PDF: {input_path}")

    images = convert_from_path(input_path, dpi=dpi)
    total_pages = len(images)

    if verbose:
        print(f"共 {total_pages} 页")

    rotated_images = []
    stats = {
        'total_pages': total_pages,
        'rotated_pages': 0,
        'cropped_pages': 0,
        'total_rotation': 0
    }

    for i, img in enumerate(images, start=1):
        if verbose:
            print(f"处理第 {i}/{total_pages} 页...", end=' ', flush=True)

        rotate_angle = angle

        # 自动检测旋转
        if auto_rotate and angle is None:
            detected_angle, confidence = preprocessor.coarse_rotation_detect(img)

            if confidence >= confidence_threshold and abs(detected_angle) >= 90:
                rotate_angle = int(detected_angle)
                if verbose:
                    print(f"检测到旋转 {rotate_angle}° (置信度: {confidence:.2f})", end=' ')
            else:
                if verbose:
                    print("方向正确", end=' ')
                rotate_angle = None

        elif angle is not None:
            if verbose:
                print(f"旋转 {angle}°", end=' ')

        else:
            if verbose:
                print("无需旋转", end=' ')

        # 应用旋转
        if rotate_angle is not None and rotate_angle != 0:
            img = preprocessor.rotate_image(img, rotate_angle)
            stats['rotated_pages'] += 1
            stats['total_rotation'] += abs(rotate_angle)

        # 裁剪空白边缘
        if crop:
            original_size = img.size
            img = preprocessor.crop_blank_edges(img)
            if img.size != original_size:
                if verbose:
                    print("已裁剪", end=' ')
                stats['cropped_pages'] += 1

        rotated_images.append(img)

        if verbose:
            print()

    # 保存结果
    if verbose:
        print(f"\n正在保存到: {output_path}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if rotated_images:
        rotated_images[0].save(
            output_path,
            save_all=True,
            append_images=rotated_images[1:],
            resolution=dpi
        )

    return stats


def main():
    parser = argparse.ArgumentParser(
        description='PDF 页面旋转工具 (v2.1)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 自动检测并矫正旋转
  %(prog)s -i input.pdf -o output.pdf --auto-rotate

  # 手动旋转 90 度
  %(prog)s -i input.pdf -o output.pdf --angle 90

  # 旋转 180 度
  %(prog)s -i input.pdf -o output.pdf --angle 180

  # 设置更高的置信度阈值
  %(prog)s -i input.pdf -o output.pdf --auto-rotate --confidence 0.8

注意:
  - --angle 和 --auto-rotate 是互斥的
  - 自动检测需要安装 Tesseract
  - 安装: pip install pytesseract
        """
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--angle', type=int,
                           choices=[90, 180, 270, -90, -180, -270],
                           help='手动指定旋转角度')
    mode_group.add_argument('--auto-rotate', action='store_true',
                           help='自动检测并矫正旋转')

    parser.add_argument('--input', '-i', required=True, help='输入 PDF 文件')
    parser.add_argument('--output', '-o', required=True, help='输出 PDF 文件')
    parser.add_argument('--confidence', type=float, default=0.5,
                       help='自动检测的置信度阈值 (默认: 0.5)')
    parser.add_argument('--no-crop', action='store_true',
                       help='不裁剪空白边缘')
    parser.add_argument('--dpi', type=int, default=300,
                       help='PDF 转 DPI (默认: 300)')
    parser.add_argument('--quiet', '-q', action='store_true',
                       help='安静模式')

    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"错误: 输入文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    if args.auto_rotate and not HAS_PYTESSERACT:
        print("错误: --auto-rotate 需要安装 pytesseract", file=sys.stderr)
        print("       安装: pip install pytesseract", file=sys.stderr)
        sys.exit(1)

    try:
        result = rotate_pdf(
            args.input,
            args.output,
            angle=args.angle,
            auto_rotate=args.auto_rotate,
            confidence_threshold=args.confidence,
            crop=not args.no_crop,
            dpi=args.dpi,
            verbose=not args.quiet
        )

        if not args.quiet:
            print("\n" + "=" * 50)
            print("处理完成！")
            print(f"总页数: {result['total_pages']}")
            print(f"旋转页数: {result['rotated_pages']}")
            print(f"总旋转角度: {result['total_rotation']}°")
            print(f"裁剪页数: {result['cropped_pages']}")
            print("=" * 50)

    except Exception as e:
        print(f"\n错误: 处理失败 - {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
