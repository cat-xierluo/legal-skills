# PDF 文本层双路径探测算法

> v1.5.0 引入。对应代码：`scripts/text_layer.py`。本文档解释探测逻辑、字符分类、阈值理由和已知失败模式，便于排查「为什么走了 / 没走文本层」。

## 为什么需要文本层探测

法律场景里很多 PDF 本就带可用的原生文本层：

- 法院电子送达的判决书 / 裁定书 / 调解书（带法院电子签章，但底层是文本而非扫描图像）。
- 政府公文系统导出的 PDF。
- 电子合同平台（如 e签宝、法大大）的签署件。
- Word / WPS 导出的 PDF。

这些 PDF 直读文本层比 OCR 更优：

| 维度 | 文本层直读 | OCR |
|------|------------|-----|
| 准确率 | 100%（就是作者写的字） | 受识别模型限制，常见 95-99% |
| 速度 | <1s（本地解码） | 数秒到数分钟（含网络往返） |
| API 额度 | 0 | PaddleOCR / MinerU 都按页计费 |
| 网络依赖 | 无 | 必须 |

但「带文本层」不等于「文本层可用」。典型坑：

- 扫描件被套了一层「假文本层」（OCR 软件预生成，但识别质量差）。
- 用了 CID / 自定义字体的 PDF，文本层抽出来全是 PUA 私用区字符（看上去有内容，实则乱码）。
- 只有封面页有文本、正文是图片。
- 解码错误导致大量 `U+FFFD` 替换字符。

所以需要一个质量判定，不能「有就信」。

## 探测算法

### 1. 抽取

```python
doc = pypdfium2.PdfDocument(str(pdf_path))
for idx in page_indices:
    page = doc.get_page(idx)
    textpage = page.get_textpage()
    raw_text = textpage.get_text_range() or ""
    # 标准化换行
```

只取纯文本，不做版面分析。后续 post-process 会处理段落 / 标题。

### 2. 字符分类

逐字符统计 5 类：

| 类别 | 字符范围 | 计入 |
|------|----------|------|
| 空白 | `str.isspace() == True` | 跳过 |
| 替换字符 | `U+FFFD` | `replacement++` |
| 私用区（PUA） | `U+E000–U+F8FF` 及补充私用区 | `pua++` |
| CJK | `U+4E00–U+9FFF`（CJK Unified Ideographs） | `cjk++`，`good++` |
| ASCII 字母数字 | `0-9 A-Z a-z` | `good++` |
| 常见标点 | CJK 符号、半全角形式、通用标点、ASCII 标点 | `good++` |
| 其他 | 不在上述类别 | 既不计入 good，也不计入 pua/replacement，归入「不明字符」 |

### 3. 指标计算

```
total_chars        = 非空白字符总数
garbled_ratio      = (total_chars - good_chars) / total_chars
text_coverage      = pages_with_text / pages_probed
avg_cjk_per_text_page = cjk_chars / pages_with_text
```

`garbled_ratio` 把 PUA、替换字符、不明字符一起算坏。这三种字符在正常法律 PDF 里都极少出现，>5% 就足以怀疑字体 / 编码有问题。

### 4. 决策

按顺序检查，第一条命中即拒绝（reason 字段写进 archive 便于复盘）：

1. `pages_with_text == 0` → `no_text_layer`（纯扫描件，最常见）
2. `text_coverage < min_coverage` → `low_coverage`（封面 + 扫描正文混排）
3. `total_chars < min_total_chars` → `too_few_chars`（1 页短文档兜底）
4. `avg_cjk < min_chars_per_text_page AND cjk < total_chars` → `low_cjk_density`（零星标题 / 图注）
5. `garbled_ratio > max_garbled_ratio` → `high_garbled_ratio`（CID 字体陷阱）
6. 否则 → `text_layer_ok`（usable=True，进入文本层分支）

`avg_cjk` 判据加了 `AND cjk < total_chars` 是为了**不误判纯英文 PDF**：英文合同每页可能只有几十个 CJK 字符（甚至 0），但 `good_chars` 包含 ASCII 字母数字，garbled_ratio 仍低，所以走兜底路径通过。

## 阈值默认值与理由

| 阈值 | 默认 | 理由 |
|------|------|------|
| `min_coverage` | 0.8 | 允许 20% 页面是空白 / 封面 / 印章页，剩余 80% 必须有文本。太严会误杀多页判决书（首尾常是空白）；太松会让封面 + 图片混排件蒙混过关。 |
| `min_chars_per_text_page` | 50 | 一份正常 A4 判决书每页约 600-1500 CJK 字符；50 已经是非常宽松的下限，避免短标题 / 图注页面被当成「有文本」。 |
| `max_garbled_ratio` | 0.05 | 正常 PDF 抽出来几乎没有 PUA / 替换字符；超过 5% 就足以怀疑字体映射坏了。这个值是直觉默认，**待真实卷宗校准**。 |
| `min_total_chars` | 100 | 1 页短文档（如单张传票）容易被随机字符误判，加一道绝对下限兜底。 |

**这些默认是保守的、直觉驱动的，没有用真实卷宗校准过。** 理想做法是收集 50-100 份真实法律 PDF，人工标注「该走文本层 / 该走 OCR」，跑探测脚本，看 ROC 曲线找最优阈值。在拿到真实样本前，宁可漏走文本层（fallback 到 OCR 也只是慢一点），也不要错走文本层（输出乱码、用户没察觉）。

## 已知失败模式

### 1. 误判为可用（false positive）

- **CID 字体但 ToUnicode CMap 正确**：抽出来是正常 Unicode，但部分字形 / 标点位置错乱。garbled_ratio 抓不到，需要语义层判定。**目前没解**，依赖人工复核。
- **OCR 预生成的「假文本层」**：扫描件套了一层 OCR 文本，识别质量 80-95%。文本层指标全过，但实际质量不如重新 OCR。**目前没解**；如果你看到结果质量差，用 `--text-layer never` 强制重跑。
- **多栏排版**：文本层抽取按 PDF 内部对象顺序，可能左右栏交错。`linebreaks.py` 后处理部分缓解，但不完美。

### 2. 误判为不可用（false negative）

- **CJK 占比很低但 ASCII 多的纯英文合同**：已通过 `cjk < total_chars` 条件兜底；如果你遇到仍被拒绝，调低 `LEGAL_OCR_TEXT_LAYER_MIN_CHARS_PER_PAGE`。
- **印章 / 水印占字符比例高**：水印字符也算 good，理论上不影响。但极端情况可能 garbled_ratio 升高。
- **少量页是图片**：低于 20% 图片页可以容忍（coverage 阈值 0.8）；超过就回退 OCR。

### 3. 已知不处理

- **远端 URL 的 PDF**：不会下载到本地再探测；直接走 OCR。
- **加密 PDF**：pypdfium2 抽不出文本，自动回退 OCR。
- **`--pages` 截取后的探测**：只看选定页的指标；如果你只选了图片页，会回退 OCR，即使其它页有文本。

## 调试技巧

### 查看 probe 指标

任何 PDF 转换后看 archive 的 `metadata.json`：

```bash
jq '.text_layer' archive/<latest>/metadata.json
jq '.backend_metadata.processing.text_layer.metrics' archive/<latest>/metadata.json
```

### 强制对比文本层 vs OCR

```bash
# 先跑文本层版本
uv run scripts/convert.py input.pdf --output with_tl.md
# 再强制 OCR 版本
uv run scripts/convert.py input.pdf --output with_ocr.md --text-layer never
# diff
diff with_tl.md with_ocr.md
```

如果 OCR 版本明显更好（少错字 / 段落更整齐），说明文本层 false positive，把样本反馈给维护者调阈值。

### 单独跑探测（不进 OCR）

```python
import sys
sys.path.insert(0, "skills/legal-ocr/scripts")
from text_layer import probe_and_extract, load_thresholds, resolve_page_indices
from pathlib import Path

pdf = Path("input.pdf")
indices, total = resolve_page_indices(pdf, None)
probe = probe_and_extract(pdf, page_indices=indices, thresholds=load_thresholds({}))
print(probe.to_payload())
```

## 关联

- 实现：`scripts/text_layer.py`
- 主入口集成：`scripts/convert.py` 的 `maybe_probe_text_layer` 函数
- 决策记录：`DECISIONS.md`「文本层质量阈值（v1.5.0）」段
- 调研缘由：260707 DataInfra-RedactionEverything 调研 Part B §一
