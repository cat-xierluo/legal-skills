#!/usr/bin/env python3
"""
PDF 预处理核心模块
实现统一的倾斜矫正与页面旋转流水线

参考: PDF倾斜矫正与页面旋转：算法综述与工程实践指南
"""

import os
import platform
import subprocess
import sys
import time
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Tuple
from dataclasses import dataclass
from enum import Enum

from pdf_runtime import exit_for_missing_dependencies
from pdf_preprocess_skew import SkewDetector

# 核心依赖
try:
    import cv2
    import numpy as np
    from PIL import Image
    from pdf2image import convert_from_path
except ImportError as e:
    exit_for_missing_dependencies(
        "PDF 预处理核心",
        missing_python=["opencv-python", "pillow", "numpy", "pdf2image"],
        missing_system=["poppler"],
        install_commands=[
            "pip install opencv-python pillow numpy pdf2image",
            "macOS: brew install poppler",
            "Linux: sudo apt-get install poppler-utils",
        ],
        extra_notes=[f"原始错误: {e}"],
    )

# 可选依赖
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("警告: 未安装 PyMuPDF，将跳过矢量文本分析")

try:
    import pytesseract
    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False
    print("警告: 未安装 pytesseract，将跳过 OSD 旋转检测")


class PDFType(Enum):
    """PDF 类型枚举"""
    SCANNED = "scanned"      # 扫描件（纯图片）
    DIGITAL = "digital"      # 电子原生（含矢量文本）
    HYBRID = "hybrid"        # 混合型


@dataclass
class ProcessingResult:
    """处理结果"""
    pdf_type: PDFType
    rotation_angle: float    # 90° 倍数旋转
    skew_angle: float        # 细微倾斜角度
    confidence: float        # 置信度
    method_used: str         # 使用的方法
    processing_time: float   # 处理耗时（秒）


@dataclass
class PageAnalysis:
    """页面分析结果"""
    has_text: bool
    text_amount: int
    aspect_ratio: float
    brightness: float
    contrast: float


class PDFPreprocessor:
    """
    PDF 预处理流水线

    实现级联式处理：
    1. PDF 类型检测 (PyMuPDF)
    2. 粗矫正 - 90° 倍数旋转检测 (Tesseract OSD)
    3. 精细矫正 - 微小倾斜检测 (< 15°)
    4. 边界情况处理
    """

    def __init__(
        self,
        dpi=300,
        skew_threshold=0.3,
        rotation_confidence=0.5,
        enable_coarse_rotation=True,
    ):
        self.dpi = dpi
        self.skew_threshold = skew_threshold
        self.rotation_confidence = rotation_confidence
        self.enable_coarse_rotation = enable_coarse_rotation
        # 经验上，文档微倾斜通常不应超过 15°；超过多为检测噪声
        self.max_reasonable_skew = 15.0
        self.skew_detector = SkewDetector(
            skew_threshold=skew_threshold,
            max_reasonable_skew=self.max_reasonable_skew,
        )
        self.cached_pdf_type = None

    # ==================== PDF 类型检测 ====================

    def detect_pdf_type(self, doc_path: str) -> PDFType:
        """
        检测 PDF 类型

        策略：
        - 尝试提取矢量文本，> 50 chars = digital
        - 部分页面有文本 = hybrid
        - 无文本 = scanned
        """
        if not HAS_PYMUPDF:
            return PDFType.SCANNED

        doc = fitz.open(doc_path)
        total_text = 0
        pages_with_text = 0
        total_pages = len(doc)

        for page in doc:
            text = page.get_text()
            if text.strip():
                pages_with_text += 1
                total_text += len(text)

        doc.close()

        # 阈值：50 个字符
        if total_text > 50:
            return PDFType.DIGITAL
        elif pages_with_text > 0:
            return PDFType.HYBRID
        else:
            return PDFType.SCANNED

    def analyze_page(self, image: Image.Image) -> PageAnalysis:
        """分析页面特征"""
        img_array = np.array(image)

        # 基本尺寸
        width, height = image.size
        aspect_ratio = width / height if height > 0 else 1.0

        # 亮度和对比度
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array

        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))

        # 文本量估算（通过边缘检测）
        edges = cv2.Canny(gray, 50, 150)
        text_pixels = np.sum(edges > 0)
        total_pixels = edges.shape[0] * edges.shape[1]
        has_text = text_pixels / total_pixels > 0.01
        text_amount = int(text_pixels)

        return PageAnalysis(
            has_text=has_text,
            text_amount=text_amount,
            aspect_ratio=aspect_ratio,
            brightness=brightness,
            contrast=contrast
        )

    # ==================== 粗矫正：90° 倍数旋转检测 ====================

    def coarse_rotation_detect(self, image: Image.Image) -> Tuple[float, float]:
        """
        粗矫正：检测 90° 倍数的页面旋转

        返回: (rotation_angle, confidence)
        rotation_angle: 0, 90, 180, 270
        confidence: 0-1
        """
        # 方法 1: Tesseract OSD (优先，最准确)
        if HAS_PYTESSERACT:
            try:
                angle, conf = self._tesseract_osd(image)
                if conf >= self.rotation_confidence:
                    return angle, conf
            except Exception as e:
                pass

        # 方法 2: 文本行方向分析 (霍夫变换)
        angle, conf = self._hough_rotation_detect(image)
        if conf >= self.rotation_confidence:
            return angle, conf

        # 方法 3: 宽高比启发式 (最后手段)
        angle, conf = self._aspect_ratio_rotation_detect(image)

        return angle, conf

    def _tesseract_osd(self, image: Image.Image) -> Tuple[float, float]:
        """使用 Tesseract OSD 检测旋转"""
        # 缩小图像以加速 OSD
        img_small = image.copy()
        if max(img_small.size) > 1000:
            scale = 1000 / max(img_small.size)
            new_size = tuple(int(dim * scale) for dim in img_small.size)
            img_small = img_small.resize(new_size, Image.LANCZOS)

        try:
            osd = pytesseract.image_to_osd(
                img_small,
                config='--psm 0 --oem 1',
                output_type=pytesseract.Output.DICT
            )

            # OSD 返回格式：
            # Page number: 0
            # Orientation in degrees: 0
            # Rotate: 0
            # Orientation confidence: 2.53
            # Script: Latin
            # Script confidence: 15.32

            orientation = osd.get('Orientation', 0)
            rotate = osd.get('Rotate', 0)
            confidence = osd.get('Orientation confidence', 0)

            # Tesseract 的 confidence 值通常较小，需要转换
            # 经验值：confidence > 3 时较为可靠
            normalized_conf = min(confidence / 5.0, 1.0)

            # 计算实际旋转角度
            # Orientation 是当前方向，Rotate 是需要的旋转
            angle = (orientation + rotate) % 360
            if angle == 360:
                angle = 0

            return float(angle), normalized_conf

        except Exception as e:
            return 0.0, 0.0

    def _hough_rotation_detect(self, image: Image.Image) -> Tuple[float, float]:
        """使用霍夫变换检测主要文本行方向"""
        img_array = np.array(image)

        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array

        # 二值化
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # 霍夫直线检测
        lines = cv2.HoughLinesP(
            binary,
            rho=1,
            theta=np.pi / 180,
            threshold=100,
            minLineLength=100,
            maxLineGap=10
        )

        if lines is None or len(lines) < 5:
            return 0.0, 0.0

        # 统计直线角度
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
            # 标准化到 0-180
            if angle < 0:
                angle += 180
            angles.append(angle)

        # 找到最接近 0° 或 90° 的角度分布
        hist, bins = np.histogram(angles, bins=36, range=(0, 180))

        # 找峰值
        peak_idx = np.argmax(hist)
        peak_angle = bins[peak_idx]

        # 判断是水平还是垂直
        if 45 <= peak_angle <= 135:
            # 垂直文本，可能需要旋转 90° 或 270°
            # 进一步判断需要看旋转后的效果
            return 90.0, 0.3  # 低置信度
        else:
            # 水平文本
            return 0.0, 0.3

    def _aspect_ratio_rotation_detect(self, image: Image.Image) -> Tuple[float, float]:
        """基于宽高比的简单旋转检测（最后手段）"""
        width, height = image.size

        # 如果明显横向，可能是需要旋转
        if width > height * 1.5:
            return 90.0, 0.2

        return 0.0, 0.1

    # ==================== 精细矫正：微小倾斜检测 ====================

    def fine_skew_detect(self, image: Image.Image) -> float:
        """精细矫正：检测细微倾斜角度 (< +/-15deg)。"""
        return self.skew_detector.detect(image).angle

    def _min_area_rect_angle(self, image: Image.Image) -> float:
        """使用最小外接矩形检测角度。"""
        return self.skew_detector.min_area_rect_angle(image)

    def _projection_profile_angle(self, image: Image.Image) -> float:
        """投影剖面法检测倾斜角度。"""
        return self.skew_detector.projection_profile_angle(image)

    def _hough_skew_angle(self, image: Image.Image) -> Tuple[float, float]:
        """使用霍夫变换检测倾斜角度（带置信度）。"""
        return self.skew_detector.hough_skew_angle(image)

    # ==================== 图像旋转 ====================

    def rotate_image(self, image: Image.Image, angle: float,
                     expand: bool = True) -> Image.Image:
        """
        旋转图像

        Args:
            image: PIL Image
            angle: 旋转角度（度）
            expand: 是否扩展图像以包含完整旋转后的内容
        """
        return image.rotate(
            angle,
            resample=Image.BICUBIC,
            expand=expand,
            fillcolor='white'
        )

    # ==================== 边缘裁剪 ====================

    def crop_blank_edges(self, image: Image.Image,
                         threshold: int = 254,
                         margin: int = 10,
                         aggressive: bool = False) -> Image.Image:
        """
        裁剪空白边缘

        Args:
            image: PIL Image
            threshold: 二值化阈值（接近白色的像素被视为空白）
            margin: 保留的边距
            aggressive: 激进模式（用于旋转后裁剪，降低保护阈值）
        """
        img_array = np.array(image)

        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array

        # 检测接近白色的区域
        _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
        coords = cv2.findNonZero(255 - binary)

        if coords is None:
            return image

        x, y, w, h = cv2.boundingRect(coords)

        # 添加边距保护
        width, height = image.size
        x = max(0, x - margin)
        y = max(0, y - margin)
        w = min(width - x, w + 2 * margin)
        h = min(height - y, h + 2 * margin)

        # 激进模式：降低保护阈值到 50%（用于旋转后的裁剪）
        # 正常模式：保持 90% 的保护阈值
        crop_threshold = 0.5 if aggressive else 0.9

        # 如果裁剪区域过小，不裁剪
        if w < width * crop_threshold or h < height * crop_threshold:
            return image

        return image.crop((x, y, x + w, y + h))

    def resize_to_original(self, image: Image.Image,
                          target_size: tuple) -> Image.Image:
        """
        将图像调整到目标尺寸（保持宽高比，居中填充）

        Args:
            image: PIL Image
            target_size: (width, height) 目标尺寸

        Returns:
            调整后的图像
        """
        target_w, target_h = target_size
        current_w, current_h = image.size

        # 如果已经是目标尺寸，直接返回
        if (current_w, current_h) == (target_w, target_h):
            return image

        # 创建白色背景
        background = Image.new('RGB', target_size, 'white')

        # 计算缩放比例（保持宽高比）
        scale_w = target_w / current_w
        scale_h = target_h / current_h
        scale = min(scale_w, scale_h)

        new_w = int(current_w * scale)
        new_h = int(current_h * scale)

        # 缩放图像
        resized = image.resize((new_w, new_h), Image.LANCZOS)

        # 居中放置
        paste_x = (target_w - new_w) // 2
        paste_y = (target_h - new_h) // 2

        background.paste(resized, (paste_x, paste_y))

        return background

    # ==================== 完整处理流程 ====================

    def process_page(self, image: Image.Image, page_num: int = 0,
                    enable_crop: bool = True,
                    restore_original_size: bool = True) -> Tuple[Image.Image, ProcessingResult]:
        """
        处理单个页面

        流水线：
        1. 记录原始尺寸
        2. 页面分析
        3. 粗矫正 (90° 倍数旋转)
        4. 精细矫正 (< 15° 倾斜)
        5. 边界情况处理
        6. 可选裁剪
        7. 恢复原始尺寸

        Args:
            restore_original_size: 是否在处理完成后恢复到原始尺寸
        """
        start_time = time.time()

        # 记录原始尺寸
        original_size = image.size

        # 粗矫正：检测 90° 倍数旋转。Tesseract OSD 成本较高，批量 OCR 场景可显式跳过。
        if self.enable_coarse_rotation:
            rotation_angle, rot_confidence = self.coarse_rotation_detect(image)
        else:
            rotation_angle, rot_confidence = 0.0, 0.0

        # 应用粗矫正
        if abs(rotation_angle) >= 90 and rot_confidence > self.rotation_confidence:
            image = self.rotate_image(image, rotation_angle)

        # 精细矫正：检测微小倾斜
        skew_angle = self.fine_skew_detect(image)

        # 死区过滤：小于阈值的角度视为噪声
        if abs(skew_angle) < self.skew_threshold:
            skew_angle = 0.0

        # 上限过滤：超过 5° 大概率是表格线等误检测，跳过
        MAX_SKEW = 5.0
        if abs(skew_angle) > MAX_SKEW:
            skew_angle = 0.0

        # 应用精细矫正
        rotated = False
        if abs(skew_angle) >= self.skew_threshold:
            image = self.rotate_image(image, skew_angle)
            rotated = True

        # 裁剪空白边缘
        crop_applied = False
        if enable_crop:
            # 如果进行了旋转，使用激进模式裁剪（因为旋转会产生新的空白边缘）
            crop_source_size = image.size
            image = self.crop_blank_edges(image, aggressive=rotated)
            crop_applied = image.size != crop_source_size

        # 恢复原始尺寸（确保所有页面尺寸一致）
        if restore_original_size and image.size != original_size:
            image = self.resize_to_original(image, original_size)

        processing_time = time.time() - start_time

        # 确定方法
        methods = []
        if abs(rotation_angle) >= 90:
            methods.append("rotation_90")
        if abs(skew_angle) >= self.skew_threshold:
            methods.append("deskew")
        if crop_applied:
            methods.append("crop")

        method_used = "+".join(methods) if methods else "none"

        result = ProcessingResult(
            pdf_type=self.cached_pdf_type or PDFType.SCANNED,
            rotation_angle=rotation_angle,
            skew_angle=skew_angle,
            confidence=rot_confidence,
            method_used=method_used,
            processing_time=processing_time
        )

        return image, result


# ==================== 工具函数 ====================

def _copy_file_times(src: str | Path, dst: str | Path) -> None:
    """复制源文件的创建时间和修改时间到目标文件（macOS 含 birthtime）。"""
    src, dst = Path(src), Path(dst)
    stat = src.stat()
    mtime = stat.st_mtime
    birthtime = getattr(stat, "st_birthtime", mtime)
    os.utime(dst, (mtime, mtime))
    if platform.system() == "Darwin":
        try:
            dt = datetime.fromtimestamp(birthtime)
            date_str = dt.strftime("%m/%d/%Y %H:%M:%S")
            subprocess.run(
                ["SetFile", "-d", date_str, str(dst)],
                check=True, capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass


def get_pdf_page_sizes(input_path: str | Path) -> list[tuple[float, float]] | None:
    """读取 PDF 原始页面尺寸（point），不可用时返回 None。"""
    if not HAS_PYMUPDF:
        return None
    try:
        with fitz.open(str(input_path)) as doc:
            return [(float(page.rect.width), float(page.rect.height)) for page in doc]
    except Exception:
        return None


def get_pdf_page_count(input_path: str | Path) -> int | None:
    """读取 PDF 页数，不可用时返回 None。"""
    if not HAS_PYMUPDF:
        return None
    try:
        with fitz.open(str(input_path)) as doc:
            return len(doc)
    except Exception:
        return None


def _resolve_worker_count(worker_count: int | None, total_items: int) -> int:
    if total_items <= 1:
        return 1
    if worker_count is None:
        return 1
    if worker_count <= 0:
        return max(1, min(total_items, os.cpu_count() or 1))
    return max(1, min(worker_count, total_items))


def _encode_image_as_jpeg_bytes(
    image: Image.Image,
    jpeg_quality: int,
    jpeg_subsampling: int,
    jpeg_optimize: bool,
) -> bytes:
    rgb_image = image.convert("RGB")
    buffer = io.BytesIO()
    rgb_image.save(
        buffer,
        format="JPEG",
        quality=jpeg_quality,
        subsampling=jpeg_subsampling,
        optimize=jpeg_optimize,
    )
    return buffer.getvalue()


def _encode_image_as_jpeg_bytes_from_args(args) -> bytes:
    return _encode_image_as_jpeg_bytes(*args)


def append_images_to_pdf_document(
    doc,
    images: list[Image.Image],
    dpi: int,
    jpeg_quality: int = 90,
    jpeg_subsampling: int = 0,
    jpeg_optimize: bool = False,
    page_sizes: list[tuple[float, float]] | None = None,
    page_offset: int = 0,
    image_encode_jobs: int | None = 1,
) -> None:
    """按顺序把图像追加到 PyMuPDF 文档。"""
    if not images:
        return

    encode_jobs = _resolve_worker_count(image_encode_jobs, len(images))
    encode_args = [
        (image, jpeg_quality, jpeg_subsampling, jpeg_optimize)
        for image in images
    ]
    if encode_jobs <= 1:
        encoded_images = [
            _encode_image_as_jpeg_bytes(*args)
            for args in encode_args
        ]
    else:
        with ThreadPoolExecutor(max_workers=encode_jobs) as executor:
            encoded_images = list(
                executor.map(_encode_image_as_jpeg_bytes_from_args, encode_args)
            )

    for idx, image_bytes in enumerate(encoded_images):
        page_idx = page_offset + idx
        if page_sizes and page_idx < len(page_sizes):
            page_w, page_h = page_sizes[page_idx]
        else:
            image = images[idx]
            page_w = image.width / dpi * 72.0
            page_h = image.height / dpi * 72.0

        page = doc.new_page(width=page_w, height=page_h)
        page.insert_image(
            fitz.Rect(0, 0, page_w, page_h),
            stream=image_bytes,
        )


def save_fitz_document(doc, output_path: str | Path) -> None:
    """使用统一压缩参数保存 PyMuPDF 文档。"""
    doc.save(
        str(output_path),
        garbage=4,
        deflate=True,
        deflate_images=True,
        deflate_fonts=True,
        use_objstms=1,
    )


def save_images_as_pdf(
    images: list[Image.Image],
    output_path: str | Path,
    dpi: int,
    jpeg_quality: int = 90,
    jpeg_subsampling: int = 0,
    jpeg_optimize: bool = False,
    page_sizes: list[tuple[float, float]] | None = None,
    image_encode_jobs: int | None = 1,
) -> None:
    """保存图像序列为 PDF，优先保留显式页面尺寸。"""
    if not images:
        return

    if HAS_PYMUPDF:
        doc = fitz.open()
        try:
            append_images_to_pdf_document(
                doc,
                images,
                dpi=dpi,
                jpeg_quality=jpeg_quality,
                jpeg_subsampling=jpeg_subsampling,
                jpeg_optimize=jpeg_optimize,
                page_sizes=page_sizes,
                image_encode_jobs=image_encode_jobs,
            )
            save_fitz_document(doc, output_path)
        finally:
            doc.close()
        return

    if images:
        images[0].save(
            output_path,
            save_all=True,
            append_images=images[1:],
            resolution=dpi,
            quality=jpeg_quality,
            subsampling=jpeg_subsampling,
            optimize=jpeg_optimize,
        )


def resolve_preprocess_jobs(preprocess_jobs: int | None, total_pages: int) -> int:
    """解析预处理页面并行数；1 为串行，0 为自动。"""
    return _resolve_worker_count(preprocess_jobs, total_pages)


def resolve_preprocess_chunk_pages(
    preprocess_chunk_pages: int | None,
    total_pages: int,
) -> int:
    """解析预处理分块页数；0/None 表示不分块。"""
    if not preprocess_chunk_pages or preprocess_chunk_pages <= 0 or total_pages <= 1:
        return 0
    return max(1, min(preprocess_chunk_pages, total_pages))


# ==================== 便捷函数 ====================

def process_pdf(input_path: str, output_path: str,
                dpi: int = 300,
                skew_threshold: float = 0.3,
                rotation_confidence: float = 0.5,
                enable_coarse_rotation: bool = True,
                enable_crop: bool = True,
                skip_pages: set = None,
                restore_original_size: bool = True,
                pdf_jpeg_quality: int = 90,
                pdf_jpeg_subsampling: int = 0,
                pdf_jpeg_optimize: bool = False,
                preprocess_jobs: int | None = 1,
                preprocess_chunk_pages: int | None = 0,
                verbose: bool = True) -> dict:
    """
    处理整个 PDF 文件

    Args:
        input_path: 输入 PDF 路径
        output_path: 输出 PDF 路径
        dpi: DPI 设置（默认 300，保真优先）
        skew_threshold: 倾斜阈值（默认 0.3 度，兼顾轻微歪斜页）
        rotation_confidence: 旋转置信度阈值
        enable_crop: 是否裁剪空白边缘
        skip_pages: 要跳过的页面集合（1-based）
        restore_original_size: 是否恢复到原始页面尺寸（确保所有页面尺寸一致）
        pdf_jpeg_quality: PDF 内嵌 JPEG 质量（1-100），默认 90
        preprocess_jobs: 预处理页面并行数；1 为串行，0 为自动
        preprocess_chunk_pages: 预处理分块页数；0 为旧的全量渲染模式
        verbose: 是否显示详细输出

    Returns:
        dict: 处理统计信息
    """
    if skip_pages is None:
        skip_pages = set()
    preprocessor = PDFPreprocessor(
        dpi=dpi,
        skew_threshold=skew_threshold,
        rotation_confidence=rotation_confidence,
        enable_coarse_rotation=enable_coarse_rotation,
    )

    # 检测 PDF 类型
    pdf_type = preprocessor.detect_pdf_type(input_path)
    preprocessor.cached_pdf_type = pdf_type

    if verbose:
        print(f"PDF 类型: {pdf_type.value}")

    if verbose:
        print(f"正在读取 PDF: {input_path}")

    page_sizes = get_pdf_page_sizes(input_path) if restore_original_size else None
    page_count = len(page_sizes) if page_sizes else get_pdf_page_count(input_path)

    # 分块模式需要提前知道页数，并依赖 PyMuPDF 顺序追加页面。
    # 单页 PDF 不启用分块，否则后续分块解析会退回 0，但旧判断已跳过全量渲染。
    use_chunked = bool(
        preprocess_chunk_pages
        and preprocess_chunk_pages > 0
        and page_count
        and page_count > 1
    )
    if use_chunked and (not HAS_PYMUPDF or not page_count):
        raise ValueError("分块预处理需要安装 PyMuPDF 并能读取 PDF 页数")

    # 旧模式：一次性渲染完整 PDF，保持兼容。
    images: list[Image.Image] = []
    if not use_chunked:
        render_start = time.time()
        images = convert_from_path(input_path, dpi=dpi)
        render_time = time.time() - render_start
        total_pages = len(images)
    else:
        render_time = 0.0
        total_pages = int(page_count)

    if verbose:
        print(f"共 {total_pages} 页")

    preprocess_jobs_resolved = resolve_preprocess_jobs(preprocess_jobs, total_pages)
    preprocess_chunk_pages_resolved = resolve_preprocess_chunk_pages(
        preprocess_chunk_pages,
        total_pages,
    )
    stats = {
        'total_pages': total_pages,
        'rotated_pages': 0,
        'deskewed_pages': 0,
        'cropped_pages': 0,
        'total_time': 0.0,
        'page_wall_time': 0.0,
        'render_time': render_time,
        'save_time': 0.0,
        'preprocess_jobs': preprocess_jobs_resolved,
        'preprocess_chunk_pages': preprocess_chunk_pages_resolved,
    }

    def process_one_page(page_item):
        i, img = page_item
        if i in skip_pages:
            return i, img, None, True

        processed_img, result = preprocessor.process_page(
            img,
            page_num=i - 1,
            enable_crop=enable_crop,
            restore_original_size=restore_original_size
        )
        return i, processed_img, result, False

    def record_page_result(i, processed_img, result, skipped, output_images):
        output_images.append(processed_img)
        if skipped:
            if verbose:
                print(f"处理第 {i}/{total_pages} 页... 跳过", flush=True)
            return

        assert result is not None
        # 更新统计
        if abs(result.rotation_angle) >= 90:
            stats['rotated_pages'] += 1
        if abs(result.skew_angle) >= skew_threshold:
            stats['deskewed_pages'] += 1
        if 'crop' in result.method_used:
            stats['cropped_pages'] += 1

        stats['total_time'] += result.processing_time

        if verbose:
            print(f"处理第 {i}/{total_pages} 页...", end=' ', flush=True)
            rot_msg = f"旋转{result.rotation_angle:.0f}°" if abs(result.rotation_angle) >= 90 else ""
            skew_msg = f"倾斜{result.skew_angle:.2f}°" if abs(result.skew_angle) >= skew_threshold else ""
            crop_msg = "已裁剪" if 'crop' in result.method_used else ""

            parts = [p for p in [rot_msg, skew_msg, crop_msg] if p]
            if parts:
                print(" ".join(parts), end=' ', flush=True)
            print(f"({result.processing_time:.2f}s)", flush=True)

    def process_page_items(page_items, output_images):
        processing_start = time.time()
        if preprocess_jobs_resolved <= 1:
            for page_item in page_items:
                record_page_result(*process_one_page(page_item), output_images)
        else:
            with ThreadPoolExecutor(max_workers=preprocess_jobs_resolved) as executor:
                for page_result in executor.map(process_one_page, page_items):
                    record_page_result(*page_result, output_images)
        stats['page_wall_time'] += time.time() - processing_start

    def render_chunk(first_page: int, last_page: int):
        chunk_render_start = time.time()
        chunk_images = convert_from_path(
            input_path,
            dpi=dpi,
            first_page=first_page,
            last_page=last_page,
        )
        return first_page, last_page, chunk_images, time.time() - chunk_render_start

    if verbose and preprocess_jobs_resolved > 1:
        print(f"预处理并行数: {preprocess_jobs_resolved}")
    if verbose and preprocess_chunk_pages_resolved:
        print(f"预处理分块页数: {preprocess_chunk_pages_resolved}")

    if not preprocess_chunk_pages_resolved:
        processed_images = []
        page_items = list(enumerate(images, start=1))
        process_page_items(page_items, processed_images)

        # 保存结果
        if verbose:
            print(f"\n正在保存到: {output_path}")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        save_start = time.time()
        save_images_as_pdf(
            processed_images,
            output_path,
            dpi=dpi,
            jpeg_quality=pdf_jpeg_quality,
            jpeg_subsampling=pdf_jpeg_subsampling,
            jpeg_optimize=pdf_jpeg_optimize,
            page_sizes=page_sizes,
            image_encode_jobs=preprocess_jobs_resolved,
        )
        stats['save_time'] += time.time() - save_start
    else:
        if verbose:
            print(f"\n正在分块保存到: {output_path}")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        chunks = [
            (first, min(first + preprocess_chunk_pages_resolved - 1, total_pages))
            for first in range(1, total_pages + 1, preprocess_chunk_pages_resolved)
        ]
        doc = fitz.open()
        render_pool = ThreadPoolExecutor(max_workers=1)
        try:
            render_future = render_pool.submit(render_chunk, *chunks[0])
            for chunk_idx, (first_page, last_page) in enumerate(chunks):
                first_page, last_page, chunk_images, chunk_render_time = render_future.result()
                stats['render_time'] += chunk_render_time

                next_idx = chunk_idx + 1
                if next_idx < len(chunks):
                    render_future = render_pool.submit(render_chunk, *chunks[next_idx])

                page_items = [
                    (first_page + offset, image)
                    for offset, image in enumerate(chunk_images)
                ]
                processed_chunk = []
                process_page_items(page_items, processed_chunk)

                save_start = time.time()
                append_images_to_pdf_document(
                    doc,
                    processed_chunk,
                    dpi=dpi,
                    jpeg_quality=pdf_jpeg_quality,
                    jpeg_subsampling=pdf_jpeg_subsampling,
                    jpeg_optimize=pdf_jpeg_optimize,
                    page_sizes=page_sizes,
                    page_offset=first_page - 1,
                    image_encode_jobs=preprocess_jobs_resolved,
                )
                stats['save_time'] += time.time() - save_start

                del chunk_images
                del processed_chunk

            save_start = time.time()
            save_fitz_document(doc, output_path)
            stats['save_time'] += time.time() - save_start
        finally:
            render_pool.shutdown(wait=True)
            doc.close()

    # 保留原文件时间戳（创建时间 + 修改时间）
    _copy_file_times(input_path, output_path)

    return stats


if __name__ == '__main__':
    # 测试代码
    import argparse

    parser = argparse.ArgumentParser(description='PDF 预处理核心模块测试')
    parser.add_argument('--input', '-i', required=True, help='输入 PDF 文件')
    parser.add_argument('--output', '-o', required=True, help='输出 PDF 文件')
    parser.add_argument('--dpi', type=int, default=300, help='DPI（默认 300，保真优先）')
    parser.add_argument('--skew-threshold', type=float, default=0.3, help='倾斜阈值（默认 0.3 度）')
    parser.add_argument(
        '--skip-coarse-rotation',
        action='store_true',
        help='跳过 90° 粗方向检测（提速；适用于页面方向已正确的扫描件）',
    )
    parser.add_argument('--no-crop', action='store_true', help='不裁剪空白边缘')
    parser.add_argument(
        '--pdf-jpeg-quality',
        type=int,
        default=90,
        help='输出 PDF 内嵌 JPEG 质量（1-100，默认 90）',
    )
    parser.add_argument(
        '--pdf-jpeg-subsampling',
        type=int,
        default=0,
        choices=[0, 1, 2],
        help='输出 PDF 内嵌 JPEG 色度子采样（0/1/2，默认 0）',
    )
    parser.add_argument(
        '--pdf-jpeg-optimize',
        action='store_true',
        help='启用 JPEG optimize 编码（更小但略慢）',
    )
    parser.add_argument(
        '--preprocess-jobs',
        type=int,
        default=1,
        help='预处理页面并行数（默认 1；0 表示自动）',
    )
    parser.add_argument(
        '--preprocess-chunk-pages',
        type=int,
        default=0,
        help='预处理分块页数（默认 0，不分块；如 40）',
    )

    args = parser.parse_args()

    result = process_pdf(
        args.input,
        args.output,
        dpi=args.dpi,
        skew_threshold=args.skew_threshold,
        enable_coarse_rotation=not args.skip_coarse_rotation,
        enable_crop=not args.no_crop,
        pdf_jpeg_quality=args.pdf_jpeg_quality,
        pdf_jpeg_subsampling=args.pdf_jpeg_subsampling,
        pdf_jpeg_optimize=args.pdf_jpeg_optimize,
        preprocess_jobs=args.preprocess_jobs,
        preprocess_chunk_pages=args.preprocess_chunk_pages,
    )

    print("\n" + "=" * 50)
    print("处理完成！")
    print(f"总页数: {result['total_pages']}")
    print(f"旋转页数: {result['rotated_pages']}")
    print(f"倾斜矫正: {result['deskewed_pages']}")
    print(f"裁剪页数: {result['cropped_pages']}")
    print(f"页面累计耗时: {result['total_time']:.2f}s")
    print(f"墙钟耗时: {result['page_wall_time']:.2f}s")
    print(f"渲染耗时: {result['render_time']:.2f}s")
    print(f"保存耗时: {result['save_time']:.2f}s")
    print(f"并行数: {result['preprocess_jobs']}")
    print(f"分块页数: {result['preprocess_chunk_pages']}")
    print(f"平均每页: {result['total_time']/result['total_pages']:.2f}s")
    print("=" * 50)
