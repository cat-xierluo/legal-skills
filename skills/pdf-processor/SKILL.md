---
name: pdf-processor
description: PDF 处理工具，支持扫描件预处理、OCR 双层 PDF、页码添加、PDF 合并、解密、水印去除和压缩。本技能应在用户需要一键处理、优化或整理 PDF 文档时使用。不要用于：纯文本 PDF 内容编辑、PDF 阅读与批注、电子签名、非压缩目的的格式转换。
license: MIT
---
# PDF Processor - PDF 处理器

你是一个专业的 PDF 处理助手。优先保护原始文件，按用户意图选择最短可用流程；用户没有特别说明时，扫描件处理走“解密 -> 页面预处理 -> 默认 medium 合并输出 -> OCR 双层 PDF”的统一入口。

## 默认策略

- 不修改原始文件；输出到新文件，重名时加 `_1`、`_2` 等序号。
- 扫描件、拍照件、证据材料默认执行预处理后继续生成可搜索双层 PDF。
- “只预处理”“不要 OCR”“只矫正压缩”才使用 `--preprocess-only`。
- “合并”“加页码”“解密”“去水印”“压缩”只执行对应工具，不自动进入预处理/OCR。
- 压缩只有用户明确提出时才单独执行；统一入口中的默认压缩是预处理输出策略的一部分。
- 水印去除只在用户明确要求时执行，不作为默认自动步骤。

## 常用流程

### 1. 一键处理扫描 PDF

```bash
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf
```

默认 `medium` 合并输出为约 200 DPI、JPEG 质量 72、色度子采样 1，优先兼顾法院上传体积和放大阅读清晰度。文件大小限制很严时使用：

```bash
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf --compress-level high
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

默认后端为 `auto`：优先按 `--api-order`、`OCR_API_ORDER` 或 `config/.env` 顺序调用 PaddleOCR / MinerU API；外部 API 不可用时回退本地 `ocrmypdf`。

```bash
# 强制本地兜底
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --backend local_ocrmypdf

# 强制 PaddleOCR API
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --backend paddle_api

# 强制 MinerU API
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --backend mineru_api
```

后端选择、API 配置和协议细节见 `references/ocr-backend-guide.md`、`references/paddleocr-api-guide.md`、`references/mineru-api-guide.md`。

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
python3 scripts/pdf-ocr-quality-check.py -i output.pdf --keyword 合同,法院

python3 scripts/pdf-ocr-benchmark.py \
  -i input.pdf \
  --backend local_ocrmypdf \
  --sample-pages 5 \
  --skip-coarse-rotation \
  --preprocess-jobs 6 \
  --preprocess-chunk-pages 80
```

常见问题见 `references/troubleshooting.md`。

## 交付前检查

1. 确认输出页数与原始文件一致。
2. 抽查页面方向、清晰度、裁剪边界和文件体积。
3. 对双层 PDF 测试文字搜索、复制和关键词命中。
4. 向用户说明实际使用的后端、输出文件路径和任何回退情况。
