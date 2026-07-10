"""PDF 原生文本层探测与抽取。

legal-ocr 进入 OCR 后端（PaddleOCR / MinerU）之前，先用本模块判断 PDF 是否已带
可用的原生文本层。文本层质量达标时直接抽取文字、复用既有 post-process 转 Markdown，
跳过 OCR；质量差或无文本层才走 OCR。

设计动机见 `references/text-layer-detection.md` 与 DECISIONS.md「文本层质量阈值」段。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import pypdfium2 as pdfium
except ImportError as error:  # pragma: no cover - pypdfium2 is required by pdf_tools
    print("缺少依赖: pypdfium2", flush=True)
    print("请使用: uv run scripts/convert.py <input>", flush=True)
    raise SystemExit(1) from error

from common import (  # noqa: E402
    first_non_empty,
    parse_positive_float,
    parse_positive_int,
)
from pdf_tools import parse_pages_spec  # noqa: E402


# ---------------------------------------------------------------------------
# 字符分类
# ---------------------------------------------------------------------------

CJK_RE = re.compile(r"[一-鿿]")  # CJK Unified Ideographs（中文主体）
PUA_RE = re.compile(
    # 私用区字符：自定义字体（CID 字体）常把字形映射到 PUA，
    # 抽出来的文本对人类不可读，是「文本层看似有实则烂」的典型信号。
    r"[-"
    r"\U000f0000-\U000ffffd"
    r"\U00100000-\U0010fffd]"
)
# 常见合法标点 / 空白（中英文）。注意 PUA 不在内。
COMMON_PUNCT_RE = re.compile(
    r"["
    r"　-〿"  # CJK Symbols and Punctuation（。、「」、【】…）
    r"＀-￯"  # Halfwidth and Fullwidth Forms（！，：；？）
    r" -⁯"  # General Punctuation（—…""）
    r"!-/:-@\[-`{-~"  # ASCII 标点
    r"\s]"
)
REPLACEMENT_CHAR = "�"  # Unicode 替换字符，解码失败时出现


@dataclass(frozen=True)
class CharStats:
    total_non_space: int
    cjk: int
    good: int  # CJK + ASCII 字母数字 + 常见标点
    pua: int
    replacement: int


@dataclass(frozen=True)
class TextLayerMetrics:
    page_count: int  # PDF 总页数
    pages_probed: int  # 实际探测页数（按 --pages 截取后）
    pages_with_text: int  # 抽出非空文本的页数
    total_chars: int  # 非空白字符总数（text_layer 视角）
    total_cjk: int  # CJK 字符总数
    good_chars: int
    pua_chars: int
    replacement_chars: int
    avg_cjk_per_text_page: float  # 文本页的平均 CJK 字符数
    text_coverage: float  # pages_with_text / pages_probed
    garbled_ratio: float  # (total - good) / total，越高越脏


@dataclass
class TextLayerThresholds:
    min_coverage: float
    min_chars_per_text_page: float  # 文本页 CJK 平均下限
    max_garbled_ratio: float
    min_total_chars: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "min_coverage": self.min_coverage,
            "min_chars_per_text_page": self.min_chars_per_text_page,
            "max_garbled_ratio": self.max_garbled_ratio,
            "min_total_chars": self.min_total_chars,
        }


@dataclass
class TextLayerProbe:
    usable: bool
    reason: str  # 机器可读的简短结果标签（text_layer_ok / no_text / low_coverage / ...）
    page_indices: list[int] = field(default_factory=list)
    metrics: TextLayerMetrics | None = None
    thresholds: TextLayerThresholds | None = None
    text: str = ""  # 抽取并按页拼接的全文（仅 usable=True 时填）

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "usable": self.usable,
            "reason": self.reason,
            "page_indices": self.page_indices,
        }
        if self.metrics is not None:
            payload["metrics"] = {
                "page_count": self.metrics.page_count,
                "pages_probed": self.metrics.pages_probed,
                "pages_with_text": self.metrics.pages_with_text,
                "total_chars": self.metrics.total_chars,
                "total_cjk": self.metrics.total_cjk,
                "good_chars": self.metrics.good_chars,
                "pua_chars": self.metrics.pua_chars,
                "replacement_chars": self.metrics.replacement_chars,
                "avg_cjk_per_text_page": round(self.metrics.avg_cjk_per_text_page, 3),
                "text_coverage": round(self.metrics.text_coverage, 3),
                "garbled_ratio": round(self.metrics.garbled_ratio, 4),
            }
        if self.thresholds is not None:
            payload["thresholds"] = self.thresholds.as_dict()
        return payload


# ---------------------------------------------------------------------------
# 阈值加载（env / CLI 共享）
# ---------------------------------------------------------------------------


def load_thresholds(env: dict[str, str]) -> TextLayerThresholds:
    """从 env 读阈值；缺失走保守默认。

    默认值依据见 DECISIONS.md「文本层质量阈值（v1.5.0）」。简要：
    - 覆盖率 0.8：允许 20% 页面是封面 / 空白页 / 印章页，剩余 80% 必须有文本。
    - 每文本页平均 CJK ≥ 50：低于此多为零星标题或图注，不算可用的正文文本层。
    - 乱码比例 ≤ 0.05：CID/PUA 字体抽出来字符超过 5% 就不可信。
    - 总字符 ≥ 100：1 页以下短文档容易误判，加一道兜底。
    """
    return TextLayerThresholds(
        min_coverage=_parse_ratio(
            env, "LEGAL_OCR_TEXT_LAYER_MIN_COVERAGE", default=0.8
        ),
        min_chars_per_text_page=_parse_ratio(
            env, "LEGAL_OCR_TEXT_LAYER_MIN_CHARS_PER_PAGE", default=50.0
        ),
        max_garbled_ratio=_parse_ratio(
            env, "LEGAL_OCR_TEXT_LAYER_MAX_GARBLE_RATIO", default=0.05
        ),
        min_total_chars=parse_positive_int(
            env.get("LEGAL_OCR_TEXT_LAYER_MIN_TOTAL_CHARS"), default=100
        ),
    )


def _parse_ratio(env: dict[str, str], key: str, default: float) -> float:
    raw = first_non_empty(env, key)
    if not raw:
        return default
    try:
        value = float(raw.strip())
    except ValueError as error:
        raise ValueError(f"{key} 必须是数字：{raw!r}") from error
    if value < 0:
        raise ValueError(f"{key} 不能为负：{value}")
    return value


# ---------------------------------------------------------------------------
# 字符分类实现
# ---------------------------------------------------------------------------


def classify_chars(text: str) -> CharStats:
    """逐字符统计合法 / CJK / PUA / 替换字符 / 其他。

    PUA 与替换字符在「合法字符」之外单独计数，便于诊断 CID 字体问题。
    其他（既非 CJK、ASCII 字母数字、也非常见标点）算「不明」，归入 garbled。
    """
    total = 0
    cjk = 0
    good = 0
    pua = 0
    replacement = 0
    for ch in text:
        if ch.isspace():
            continue
        total += 1
        if ch == REPLACEMENT_CHAR:
            replacement += 1
            continue
        if PUA_RE.match(ch):
            pua += 1
            continue
        if CJK_RE.match(ch):
            cjk += 1
            good += 1
            continue
        code = ord(ch)
        if (48 <= code <= 57) or (65 <= code <= 90) or (97 <= code <= 122):
            # ASCII 数字 / 大小写字母
            good += 1
            continue
        if COMMON_PUNCT_RE.match(ch):
            good += 1
            continue
        # 既非 CJK / ASCII / 常见标点，也不在 PUA / 替换字符——算 garbled
    return CharStats(
        total_non_space=total,
        cjk=cjk,
        good=good,
        pua=pua,
        replacement=replacement,
    )


# ---------------------------------------------------------------------------
# 页码解析
# ---------------------------------------------------------------------------


def resolve_page_indices(
    pdf_path: Path, pages_spec: str | None
) -> tuple[list[int], int]:
    """返回 (要探测的 0-based 页索引, PDF 总页数)。

    pages_spec 为空时返回所有页。pages_spec 非法时抛 ValueError（由调用方处理）。
    """
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        total_pages = len(doc)
    finally:
        doc.close()
    if not pages_spec:
        return list(range(total_pages)), total_pages
    indices = parse_pages_spec(pages_spec, total_pages)
    return indices, total_pages


# ---------------------------------------------------------------------------
# 探测 + 抽取
# ---------------------------------------------------------------------------


def probe_and_extract(
    pdf_path: Path,
    *,
    page_indices: list[int] | None,
    thresholds: TextLayerThresholds,
) -> TextLayerProbe:
    """探测 PDF 文本层质量并抽取文本。

    - 先按 page_indices 逐页 `page.get_textpage().get_text_range()` 取文本；
    - 计算 coverage / garbled_ratio / avg_cjk_per_text_page；
    - 达标时把按页拼接的全文填入 `probe.text`，`usable=True`；
    - 不达标时 `usable=False`，`reason` 解释卡在哪条阈值，便于 archive 与日志诊断。
    """
    if not page_indices:
        return TextLayerProbe(
            usable=False,
            reason="no_pages_to_probe",
            thresholds=thresholds,
        )

    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        total_pages = len(doc)
        valid_indices = [i for i in page_indices if 0 <= i < total_pages]
        if not valid_indices:
            return TextLayerProbe(
                usable=False,
                reason="no_valid_pages",
                thresholds=thresholds,
            )
        text_parts: list[str] = []
        pages_with_text = 0
        for idx in valid_indices:
            page = doc.get_page(idx)
            try:
                textpage = page.get_textpage()
                try:
                    raw_text = textpage.get_text_range() or ""
                finally:
                    textpage.close()
            finally:
                page.close()
            normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
            if normalized:
                pages_with_text += 1
                text_parts.append(normalized)
    finally:
        doc.close()

    joined = "\n\n".join(text_parts)
    stats = classify_chars(joined)
    pages_probed = len(valid_indices)
    avg_cjk = (stats.cjk / pages_with_text) if pages_with_text else 0.0
    coverage = pages_with_text / pages_probed if pages_probed else 0.0
    garbled = (
        1.0 - (stats.good / stats.total_non_space)
        if stats.total_non_space
        else 1.0
    )
    metrics = TextLayerMetrics(
        page_count=total_pages,
        pages_probed=pages_probed,
        pages_with_text=pages_with_text,
        total_chars=stats.total_non_space,
        total_cjk=stats.cjk,
        good_chars=stats.good,
        pua_chars=stats.pua,
        replacement_chars=stats.replacement,
        avg_cjk_per_text_page=avg_cjk,
        text_coverage=coverage,
        garbled_ratio=garbled,
    )

    if pages_with_text == 0:
        reason = "no_text_layer"
    elif coverage < thresholds.min_coverage:
        reason = "low_coverage"
    elif stats.total_non_space < thresholds.min_total_chars:
        reason = "too_few_chars"
    elif avg_cjk < thresholds.min_chars_per_text_page and stats.cjk < stats.total_non_space:
        # 当 CJK 占比本身就低（纯英文 PDF），用 avg_cjk 卡会误判；
        # 加 `and stats.cjk < stats.total_non_space` 让纯 ASCII 文档走 good_chars 路径
        reason = "low_cjk_density"
    elif garbled > thresholds.max_garbled_ratio:
        reason = "high_garbled_ratio"
    else:
        reason = "text_layer_ok"

    usable = reason == "text_layer_ok"
    return TextLayerProbe(
        usable=usable,
        reason=reason,
        page_indices=valid_indices,
        metrics=metrics,
        thresholds=thresholds,
        text=joined if usable else "",
    )


# ---------------------------------------------------------------------------
# 决策（CLI + env 合并）
# ---------------------------------------------------------------------------


TEXT_LAYER_MODES = ("auto", "never", "always")


def resolve_text_layer_mode(
    env: dict[str, str],
    cli_value: str | None,
) -> str:
    """合并 CLI / env 决定文本层分支模式。

    - 优先级：CLI `--text-layer` > env `LEGAL_OCR_TEXT_LAYER` > 默认 `auto`。
    - 接受 auto / never / always 以及 0/1/true/false 等布尔别名（兼容老配置）。
    """
    raw = (cli_value or first_non_empty(env, "LEGAL_OCR_TEXT_LAYER") or "auto").strip().lower()
    aliases = {
        "auto": "auto",
        "always": "always",
        "force": "always",
        "1": "always",
        "true": "always",
        "yes": "always",
        "on": "always",
        "never": "never",
        "off": "never",
        "0": "never",
        "false": "never",
        "no": "never",
    }
    if raw not in aliases:
        raise ValueError(
            "LEGAL_OCR_TEXT_LAYER 仅支持 auto / never / always，"
            f"或命令行 --text-layer auto|never|always；收到：{raw!r}"
        )
    return aliases[raw]
