---
name: pdf-processor
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "2.10.2"
description: PDF 处理工具，支持扫描件预处理、OCR 双层 PDF、页码添加、PDF 合并、解密、水印去除和压缩。本技能应在用户需要一键处理、优化或整理 PDF 文档时使用。不要用于：纯文本 PDF 内容编辑、PDF 阅读与批注、电子签名、非压缩目的的格式转换。
license: MIT
---

# pdf-processor

## 定位

本技能是 PDF 处理的统一入口，覆盖扫描件预处理、OCR 双层 PDF 生成、页码添加、PDF 合并、解密、水印去除和压缩。优先保护原始文件，按用户意图选择最短可用流程。

核心职责：

1. 扫描件一键处理：解密 → 页面预处理 → 合并输出 → OCR 双层 PDF。
2. 单项处理：只预处理、只 OCR、只压缩、只解密、只去水印、只合并、只加页码。
3. 用户没有特别说明时，扫描件走默认统一入口；明确提出单项需求时只执行对应工具。

本技能不做纯文本 PDF 内容编辑、PDF 阅读批注、电子签名、非压缩目的的格式转换。

## 默认策略

- 不修改原始文件；输出到新文件，重名时加 `_1`、`_2` 等序号。
- 扫描件、拍照件、证据材料默认继续生成可搜索双层 PDF；PaddleOCR 与本地 `ocrmypdf` 默认直接保留原 PDF，只有 MinerU 或显式图像处理请求才走统一栅格预处理。
- `auto` 在已配置时默认优先 PaddleOCR API，再尝试 MinerU，最后回退本地 `ocrmypdf`；明确禁止外传的材料必须使用 `--local-only`。
- 输入含姓名、案号、医疗、账号等敏感信息且用户尚未明确授权该文件外传时，先说明将上传完整 PDF 并取得一次确认；已授权当前文件后不重复询问，授权不扩展到同目录或其他材料。
- 电子 PDF 或混合 PDF 默认保留文字、矢量、图片和批注层，跳过栅格化预处理与重压缩；只有用户明确接受层丢失风险时才使用 `--force-raster-preprocess`。
- “只预处理”“不要 OCR”“只矫正压缩”才使用 `--preprocess-only`。
- “合并”“加页码”“解密”“去水印”“压缩”只执行对应工具，不自动进入预处理/OCR。
- 压缩只有用户明确提出时才单独执行；统一入口中的默认压缩是预处理输出策略的一部分。
- 水印去除只在用户明确要求时执行，不作为默认自动步骤。

## 常用流程

### 1. 一键处理扫描 PDF

```bash
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf
```

`auto` 选中已配置的 PaddleOCR 时，默认把原 PDF 直接送给 `PP-OCRv6`，跳过统一栅格化和 OCR 前压缩，以保留扫描分辨率、图像层和 API 坐标空间；实际后端确定为本地 `ocrmypdf` 时同样保留原扫描页，并使用 OCRmyPDF 自带的方向检测、纠偏和清理。MinerU 或显式预处理路径仍以 `medium` 的 200 DPI、JPEG 质量 72、色度子采样 1 为目标，并以 25MP 保护异常大画布。确需裁剪或统一重栅格化时使用 `--enable-crop` 或 `--force-raster-preprocess`。电子/混合 PDF 自动保留原有层。文件大小限制很严时使用：

```bash
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf --compress-level high
```

确需保留超大栅格时可显式调高上限；`--max-preprocess-megapixels 0` 会关闭保护，但可能显著增加内存占用和 OCR 跳页风险。

敏感材料用统一入口但禁止外传：

```bash
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf --local-only
```

页面方向已正确的大批量扫描件可提速：

```bash
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf \
  --skip-coarse-rotation --preprocess-jobs 6 --preprocess-chunk-pages 80
```

### 2. 只预处理，不做 OCR

```bash
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf --preprocess-only
```

只做页面矫正、不压缩、不 OCR：

```bash
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf \
  --preprocess-only --no-compress
```

### 3. 只做 OCR 文字层

```bash
python3 scripts/pdf-ocr.py --input input.pdf --output output.pdf
```

默认后端为 `auto`：已配置 PaddleOCR 时先用 `PP-OCRv6` 的行级坐标生成文字层，再按 `OCR_API_ORDER` 尝试 MinerU；外部服务失败或未配置时回退本地 `ocrmypdf`。该默认路径会上传完整 PDF，不允许外传时使用：

```bash
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --local-only
```

`--allow-external-upload` 仅为旧命令兼容参数，不再控制后端选择。Paddle 的服务端方向矫正和去畸变默认关闭，避免 OCR 坐标与原图空间不一致。

```bash
# 强制本地兜底
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --backend local_ocrmypdf

# 强制 PaddleOCR API；PP-OCRv6 是双层 PDF 默认模型
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf \
  --backend paddle_api --paddle-model PP-OCRv6

# 干净扫描件/表格可试 PP-StructureV3 的 overall_ocr_res 行级坐标
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf \
  --backend paddle_api --paddle-model PP-StructureV3

# 强制 MinerU API
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --backend mineru_api

# 显式保存 OCR 可读文本和运行元数据；默认不归档案件材料
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --archive-results
```

后端选择、API 配置和协议细节见 `references/ocr-backend-guide.md`、`references/paddleocr-api-guide.md`、`references/mineru-api-guide.md`。

PaddleOCR-VL-1.5/1.6 也可解析，但只提供块级坐标，文字层定位粒度低于 `PP-OCRv5/v6` / `PP-StructureV3`。本技能不接入 Qwen/GLM 等视觉识别链路，也不宣称云端结果含字符级坐标。

PP-OCRv6 文字模型默认开启 `--actualtext`：文字层生成后再调一次 PP-StructureV3 拿版面，融合出自然段并以 `/ActualText` marked-content 写入 PDF，让从 PDF 复制的文字按段落连续而非按物理行断行。`--no-actualtext` 可关闭；`--layout-dump FILE` 复用已有版面 dump 避免二次 API 调用。阅读器兼容性见下文第 4 节。

### 4. 自然段文本与 PDF 复制换行

双层 PDF 的文字层按行叠层（保护选区坐标精度），直接从 PDF 复制会按物理行断行。解决方式有两条：

**默认：`/ActualText` + 独立 Markdown。** `--actualtext`（默认开启）把自然段写入 PDF 的 `/ActualText` marked-content，同时保留行级字形坐标。实测各阅读器支持：

| 提取方式 | 从 PDF 复制的段落连续性 |
|---|---|
| Poppler（`pdftotext -raw`、`pdftotext` 默认） | ✅ 整段连续，无换行 |
| PyMuPDF、pypdf、macOS 预览（PDFKit） | ❌ 仍按物理行断行 |

因此 Poppler 用户能直接从 PDF 拿到段落级文本；macOS 预览用户复制仍会断行，需用独立 Markdown（`pdf_ocr_paragraphs.py` 输出的 `clean.md`）作为段落文本交付。个别自然段若跳过被排除的行（如印章碎片），因物理行不连续无法包裹，会降级为行级（文字不丢失，仅该段复制按行断行）。

需要解决复制文本中的段内回车、多余空行和印章文字时，采用两模型分工：`PP-OCRv6` 提供主要行级文字及坐标，`PP-StructureV3` 提供阅读顺序、区域类型和 `seal` 区域。只有 v6 行置信度低于 0.80、Structure 对应行置信度不低于 0.90、双方坐标高度重合且后者至少高 0.10 时，才采用 Structure 的行级文字兜底；始终不读取版面块文字，也不调用大语言模型。

Structure 的块边界只作为候选而非强制段界：融合器先合并同一视觉行的碎片，在 `text` 区域内按行距、缩进和右边界恢复物理换行，再依据句末标点和条款编号跨相邻文本块连接正文；`table` 区域按视觉行保留单元格次序并用 ` | ` 分隔。这样可处理 Structure 高覆盖但正文块过度切碎的页面。

需要独立 Markdown、自定义 dump 审查或复用已有版面 dump 时，用以下四步法（主流程已默认自动完成等价工作）：

```bash
# 1. 获取文字真值（--dump-and-pdf 同时出 dump 和双层 PDF）
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf \
  --backend paddle_api --paddle-model PP-OCRv6 \
  --ocr-dump /tmp/text.json --dump-and-pdf

# 2. 获取版面结构
python3 scripts/pdf-ocr.py -i input.pdf -o unused.pdf \
  --backend paddle_api --paddle-model PP-StructureV3 --ocr-dump /tmp/layout.json

# 3. 生成自然段文本，同时输出不含正文的诊断和已过滤文字层 dump
python3 scripts/pdf_ocr_paragraphs.py \
  --text-dump /tmp/text.json --layout-dump /tmp/layout.json \
  --output /tmp/clean.md --diagnostics /tmp/paragraphs.json \
  --filtered-dump /tmp/text-filtered.json

# 4. 用过滤后的行级坐标生成双层 PDF
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf \
  --backend paddle_api --ocr-resume /tmp/text-filtered.json
```

诊断中的 `layout_coverage` 低于 `0.75` 时自动退回纯几何规则；同时查看 `structure_text_fallbacks` 和 `layout_boundary_merges`，确认低置信替换与跨块合并均可审计。只有 Structure 明显漏块、区域类型错误或阅读顺序错误，且纯几何回退仍不能恢复时，才另测 `PaddleOCR-VL-1.5` 作为 `--layout-dump`；VL-1.6 不作为默认兜底。全文、dump 与账号等敏感信息继续只放临时目录，除非用户明确要求归档。

## 单项工具

```bash
# 手动旋转
python3 scripts/pdf-rotate.py --input input.pdf --output output.pdf --angle 90

# 解密
python3 scripts/pdf-decrypt.py --input input.pdf --output output.pdf
python3 scripts/pdf-decrypt.py --input input.pdf --output output.pdf --password 123456

# 去水印
python3 scripts/pdf-remove-watermark.py --input input.pdf --output output.pdf

# 压缩
python3 scripts/pdf-compress.py -i input.pdf -o output.pdf --level medium

# 加页码
python3 scripts/pdf-add-page-numbers.py -i input.pdf -o output.pdf

# 合并
python3 scripts/pdf-merge.py -i file1.pdf file2.pdf file3.pdf -o merged.pdf
python3 scripts/pdf-merge.py -i file1.pdf file2.pdf -o merged.pdf --add-numbers --continuous
```

页码、合并、压缩等详细参数见 `references/pdf-workflows.md`。

## 依赖

### 基础依赖

```bash
pip install pymupdf pypdf pillow numpy opencv-python pdf2image
```

macOS:

```bash
brew install poppler
```

Linux:

```bash
sudo apt-get install poppler-utils
```

### OCR 兜底依赖

```bash
pip install ocrmypdf
```

macOS:

```bash
brew install tesseract tesseract-lang
```

Linux:

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim
```

完整可选依赖清单见 `references/optional-dependencies.txt`。历史保留的本地 Paddle 双层实现已拆到 `scripts/pdf_ocr_paddle_local.py`，不属于默认生产链路；需要实验时再安装 `paddleocr paddlepaddle` 并单独接入。

## 质量检查

```bash
python3 scripts/pdf-ocr-quality-check.py \
  -i input.pdf -o output.pdf --keywords 合同,法院

python3 scripts/pdf-ocr-benchmark.py \
  -i input.pdf \
  --backend local_ocrmypdf \
  --sample-pages 5 \
  --skip-coarse-rotation \
  --preprocess-jobs 6 \
  --preprocess-chunk-pages 80
```

关键词门禁会先做 NFKC、大小写和空白归一化，避免中文 OCR 在汉字间插入空格后被误判为未命中；CER 仍按独立参考文本计算。

常见问题见 `references/troubleshooting.md`。

## 交付前检查

1. 确认输出页数与原始文件一致。
2. 抽查页面方向、清晰度、裁剪边界和文件体积。
3. 对双层 PDF 测试文字搜索、复制和关键词命中。
4. 向用户说明实际使用的后端、输出文件路径和任何回退情况。
