"""RapidOCR 本地后端：onnx 本地推理识别文字，几何规则重建段落，输出 Markdown。

定位：本地中文兜底与敏感材料不出本机的 OCR 路径。auto 路由在本机已安装
RapidOCR 时将其作为候选（无 API 配置时优先），也可 `--backend rapid` 显式指定。

能力边界（与云端版面解析后端的差异，选择前须知）：
- 只有文字检测+识别，没有版面分析：段落用几何规则（行距/缩进）重建，
  单栏文书（判决书、合同扫描件等）可靠；多栏版面可能左右错序。
- 不提取图片资源：印章、签名、图表不会出现在 Markdown 里。
- Office 文档与 URL 不支持（仍走 MinerU）。

依赖（可选，未安装时本后端不可用并给出提示）：
    uv run --with rapidocr scripts/convert.py ... --backend rapid
    # 或直接系统 python：
    pip install rapidocr && python3 scripts/convert.py ... --backend rapid
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from base import BackendResult, ConvertOptions
from common import SUPPORTED_IMAGE_SUFFIXES, SourceInfo
from pdf_tools import parse_pages_spec

RAPID_LOCAL_SUFFIXES = (".pdf",) + SUPPORTED_IMAGE_SUFFIXES

_RapidOCR = None
_RAPID_FLAVOR: str | None = None
_RAPID_TRIED = False


def is_rapid_available() -> bool:
    """探测 RapidOCR 是否可导入（供路由判断；不触发模型加载）。"""
    return _load_rapid_class() is not None


def _load_rapid_class():
    global _RapidOCR, _RAPID_FLAVOR, _RAPID_TRIED
    if _RAPID_TRIED:
        return _RapidOCR
    _RAPID_TRIED = True
    try:
        from rapidocr import RapidOCR  # 新统一包

        _RapidOCR, _RAPID_FLAVOR = RapidOCR, "rapidocr"
    except Exception:
        try:
            from rapidocr_onnxruntime import RapidOCR  # 经典包

            _RapidOCR, _RAPID_FLAVOR = RapidOCR, "rapidocr_onnxruntime"
        except Exception:
            _RapidOCR = None
    return _RapidOCR


def rapid_supports(source: SourceInfo) -> bool:
    """RapidOCR 后端支持的输入类型：本地 PDF 与常见图片。"""
    if source.is_url:
        return False
    return source.suffix in RAPID_LOCAL_SUFFIXES


class RapidOCRBackend:
    name = "rapid"

    def __init__(self, env: dict[str, str]) -> None:
        self.env = env
        self.dpi = self._env_int("LEGAL_OCR_RAPID_DPI", 220)
        self.min_score = self._env_float("LEGAL_OCR_RAPID_MIN_SCORE", 0.5)

    def _env_int(self, key: str, default: int) -> int:
        try:
            return int(self.env.get(key, "").strip() or default)
        except ValueError:
            return default

    def _env_float(self, key: str, default: float) -> float:
        try:
            return float(self.env.get(key, "").strip() or default)
        except ValueError:
            return default

    def convert(
        self,
        source: SourceInfo,
        options: ConvertOptions,
        work_dir: Path,
        assets_dir: Path,
    ) -> BackendResult:
        rapid_cls = _load_rapid_class()
        if rapid_cls is None:
            raise RuntimeError(
                "本地 RapidOCR 未安装。可用任一方式启用：\n"
                "  uv run --with rapidocr scripts/convert.py <输入> --backend rapid\n"
                "  pip install rapidocr && python3 scripts/convert.py <输入> --backend rapid"
            )
        if not rapid_supports(source):
            raise ValueError(f"rapid 后端不支持该输入类型：{source.suffix or source.raw}（Office/URL 请使用 MinerU）")

        try:
            import numpy as np
            import pypdfium2 as pdfium
            from PIL import Image
        except ImportError as error:  # pragma: no cover
            raise RuntimeError(f"rapid 后端缺少基础依赖（{error}）；请用 uv run 或安装 pypdfium2/pillow/numpy") from error

        engine = rapid_cls()
        page_images: list[tuple[int, Any]] = []  # [(page_no, PIL.Image)]

        if source.suffix == ".pdf":
            document = pdfium.PdfDocument(source.path)
            total_pages = len(document)
            page_numbers = (
                parse_pages_spec(options.pages, total_pages) if options.pages else list(range(1, total_pages + 1))
            )
            scale = self.dpi / 72.0
            for page_no in page_numbers:
                page = document[page_no - 1]
                bitmap = page.render(scale=scale)
                page_images.append((page_no, bitmap.to_pil().convert("RGB")))
            document.close()
        else:
            page_images.append((1, Image.open(source.path).convert("RGB")))

        markdown_blocks: list[str] = []
        page_stats: list[dict[str, Any]] = []

        for page_no, image in page_images:
            arr = np.asarray(image)[:, :, ::-1]  # RGB → BGR（OpenCV 约定）
            result = engine(arr)
            rows = _parse_result(result)
            rows = [row for row in rows if row[1] >= self.min_score and row[0].strip()]
            lines = _rows_to_sorted_lines(rows)
            for line in lines:
                markdown_blocks.append(normalize_cjk_spacing(line["text"]))
            markdown_blocks.append("")  # 页边界空行：阻断后处理把跨页内容串成一段
            page_stats.append(
                {
                    "page": page_no,
                    "rows": len(rows),
                    "lines": len(lines),
                    "size": f"{image.width}x{image.height}",
                }
            )

        # 行级保守输出（每视觉行一行）：段落合并交给统一后处理链的
        # 硬换行整理（与 PDF 文本层直读分支行为对称），其编号/标签/标题
        # 保留规则比纯几何段落判定可靠。
        markdown = "\n".join(block for block in markdown_blocks if block)
        markdown += "\n" if markdown else ""
        metadata = {
            "engine": _RAPID_FLAVOR,
            "dpi": self.dpi,
            "min_score": self.min_score,
            "reading_order": "single-column-geometric",
            "pages": page_stats,
            "limitations": [
                "无版面分析：按几何行排序（单栏可靠，多栏可能错序），段落由后处理链重建",
                "不提取图片资源（印章/签名/图表不出现在 Markdown）",
            ],
        }
        return BackendResult(
            backend=self.name,
            mode="local",
            provider=f"RapidOCR ({_RAPID_FLAVOR}, onnx 本地推理)",
            markdown=markdown,
            images=[],
            batches=[],
            metadata=metadata,
            backend_result_dir=None,
        )


# ---------- RapidOCR 结果解析（兼容各版本输出形态） ----------

def _parse_result(result) -> list[tuple[str, float, list[list[float]]]]:
    """统一为 [(text, score, poly4)]，poly4 为四角点像素坐标。"""
    import numpy as np

    if result is None:
        return []
    if isinstance(result, tuple):  # 经典包 (result, elapse)
        return _parse_result(result[0] if result else None)

    boxes = getattr(result, "boxes", None)
    txts = getattr(result, "txts", None)
    if txts is None:
        txts = getattr(result, "texts", None)
    if boxes is not None and txts is not None:
        scores = getattr(result, "scores", None)
        rows: list[tuple[str, float, list[list[float]]]] = []
        for i in range(len(txts)):
            text = str(txts[i]).strip()
            if not text:
                continue
            score = 1.0
            if scores is not None and i < len(scores):
                try:
                    score = float(scores[i])
                except (TypeError, ValueError):
                    score = 1.0
            poly = _to_poly(np.asarray(boxes[i], dtype=float))
            if poly:
                rows.append((text, score, poly))
        return rows

    if isinstance(result, list):
        rows = []
        for block in result:
            if not isinstance(block, (list, tuple)) or len(block) < 2:
                continue
            poly_raw, rec = block[0], block[1]
            if isinstance(rec, (list, tuple)) and len(rec) >= 2:
                text, score = str(rec[0]).strip(), _as_float(rec[1])
            elif len(block) >= 3:
                text, score = str(rec).strip(), _as_float(block[2])
            else:
                continue
            if not text:
                continue
            poly = _to_poly(np.asarray(poly_raw, dtype=float))
            if poly:
                rows.append((text, score, poly))
        return rows

    return []


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0


def _to_poly(arr) -> list[list[float]]:
    try:
        points = arr.reshape(-1, 2)
    except Exception:
        return []
    if len(points) < 4:
        return []
    return [[float(x), float(y)] for x, y in points[:4]]


# ---------- 几何阅读顺序与段落重建 ----------

def _row_geometry(poly: list[list[float]]) -> tuple[float, float, float, float]:
    """(y_top, x_left, height, y_center)。"""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x_left, x_right = min(xs), max(xs)
    y_top, y_bottom = min(ys), max(ys)
    height = max(y_bottom - y_top, 1.0)
    return y_top, x_left, height, y_top + height / 2.0


def _rows_to_sorted_lines(rows: list[tuple[str, float, list[list[float]]]]) -> list[dict[str, Any]]:
    """按视觉行排序：先按 y 分行（同一行按 x 拼接），行间按 y 升序。"""
    geoms = [(text, score) + _row_geometry(poly) for text, score, poly in rows]
    geoms.sort(key=lambda g: (g[2], g[3]))  # y_top, x_left

    lines: list[dict[str, Any]] = []
    for text, score, y_top, x_left, height, y_center in geoms:
        if lines:
            last = lines[-1]
            # 与上一行 y 中心接近 → 同一视觉行，按 x 追加
            if abs(y_center - last["y_center"]) < max(last["height"], height) * 0.6:
                if x_left >= last["x_right"] - max(last["height"], height) * 0.3:
                    last["text"] += text
                    last["x_right"] = max(last["x_right"], x_left + _width_hint(text, height))
                    continue
                # 交叠或逆序时保守新起一行
        lines.append(
            {
                "text": text,
                "score": score,
                "y_top": y_top,
                "x_left": x_left,
                "x_right": x_left + _width_hint(text, height),
                "height": height,
                "y_center": y_center,
            }
        )
    return lines


def _width_hint(text: str, height: float) -> float:
    """按 CJK 为主的文本估算行宽（仅用于同行拼接的右边界更新）。"""
    cjk = sum(1 for ch in text if ord(ch) > 0x2E80)
    units = cjk + (len(text) - cjk) * 0.5
    return units * height


# ---------- CJK 空格归一化（去除 OCR 在 CJK/数字字符间误插的空格，保留英文词间距） ----------

_CJK_CLASS = r"㐀-䶿一-鿿豈-﫿　-〿＀-￯"
_CJK_SPACE_RE = re.compile(rf"(?<=[{_CJK_CLASS}])\s+(?=[{_CJK_CLASS}])")
# OCR 常在中文语境的数字前后/内部误插空格（如“1 975年”“202 5”），全部归一；
# 仅保留两个 ASCII 字母之间的空格（英文单词间距）。
_DIGIT_CJK_SPACE_RE = re.compile(
    rf"(?<=[0-9{_CJK_CLASS}])\s+(?=[0-9{_CJK_CLASS}])"
)
_CJK_BEFORE_PUNC_SPACE_RE = re.compile(r"\s+([，。！？；：、）》】」』）])")
_CJK_AFTER_OPEN_PUNC_SPACE_RE = re.compile(r"([（《【「『])\s+")


def normalize_cjk_spacing(text: str) -> str:
    if not text:
        return text
    # 全角数字统一为半角（OCR 常混用，影响日期/金额检索一致性）
    text = text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    text = _CJK_SPACE_RE.sub("", text)
    text = _DIGIT_CJK_SPACE_RE.sub("", text)
    text = _CJK_BEFORE_PUNC_SPACE_RE.sub(r"\1", text)
    text = _CJK_AFTER_OPEN_PUNC_SPACE_RE.sub(r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()
