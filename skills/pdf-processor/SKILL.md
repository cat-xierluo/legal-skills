---
name: pdf-processor
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "2.18.1"
description: PDF 处理工具，支持扫描件预处理、拍照件单张或批量规整合并、OCR 双层 PDF、页码添加、PDF 合并、解密、水印去除和压缩。本技能应在用户需要一键处理、优化或整理 PDF 文档时使用。不要用于：纯文本 PDF 内容编辑、PDF 阅读与批注、电子签名、非压缩目的的格式转换。
license: MIT
---

# pdf-processor

## 定位

本技能是 PDF 处理的统一入口，覆盖扫描件预处理、拍照件转规整 PDF、OCR 双层 PDF 生成、页码添加、PDF 合并、解密、水印去除和压缩。优先保护原始文件，按用户意图选择最短可用流程。

核心职责：

1. 扫描件一键处理：解密 → 页面预处理 → 合并输出 → OCR 双层 PDF。
2. 拍照件规整：EXIF 转正 → 纸面透视校正；无完整纸边时识别可见文字主体和空白表格线网 → 可靠表框/横线簇/正文投影精校 → 去阴影和增强对比度 → A4 PDF；多张照片可逐页规整后合并。
3. 单项处理：只预处理、只 OCR、只压缩、只解密、只去水印、只合并、只加页码。
4. 用户没有特别说明时，扫描 PDF 走默认统一入口；手机拍摄的 JPG/PNG/TIFF/BMP/WebP 先走拍照件规整入口；明确提出单项需求时只执行对应工具。

本技能不做纯文本 PDF 内容编辑、PDF 阅读批注、电子签名、非压缩目的的格式转换。

## 默认策略

- 不修改原始文件；输出到新文件，重名时加 `_1`、`_2` 等序号。
- 扫描件、拍照件、证据材料默认继续生成可搜索双层 PDF；统一入口的本地 RapidOCR 与显式 PaddleOCR 原图直送路径会在 OCR 前做内容流无损倾斜检测与旋正；本地 `ocrmypdf` 使用其原生方向检测、纠偏和清理。
- `auto` 默认全程本地：优先 RapidOCR，未安装或失败时回退 `ocrmypdf`；PaddleOCR/MinerU 仅在显式选择对应 backend 时使用。
- 显式选择外部 API 且输入含姓名、案号、医疗、账号等敏感信息时，先说明将上传完整 PDF 并取得一次当前文件授权；授权不扩展到同目录或其他材料。
- 电子 PDF 或混合 PDF 默认保留文字、矢量、图片和批注层，跳过栅格化预处理与重压缩；只有用户明确接受层丢失风险时才使用 `--force-raster-preprocess`。
- “只预处理”“不要 OCR”“只矫正压缩”才使用 `--preprocess-only`。
- 拍照件纸边通过检测时，将完整校正纸面铺满 A4 页框；无完整纸边但可见文字主体可靠时，按主体、空白表格线网及更可靠的邻近彩色印章估计比例裁切并等比排版，排除靠近重叠页或地面边缘的痕迹，不虚构缺失的完整纸面。表框轮廓不完整时，用至少三条可靠长横线簇恢复上下边界，并要求左右竖线同时支持该边界后做空间校正；超过 5° 或投影越界时保守放弃。两类证据都不足或候选框过宽时等比保留整幅图像，并在报告中说明。需要保留检测比例时使用 `--page-size original`。
- 可靠表框不可用时，按字符级墨迹估计正文倾角。检测到两侧均有多段正文的栏间空隙时，两栏分别测角并检查一致性。其余页面沿用上中下分段投影。可靠角度超过 0.3° 且不超过 5° 时旋正并扩展画布。证据冲突、支持不足或超过安全角时保留原方向。连贯表框优先，线簇校正后正文残余倾角超过 0.3° 时回到正文投影。决策记录在 `text_deskew`。
- 多张拍照件默认先按自然文件名顺序逐页规整并合并为一个 PDF，再交给本地 OCR；任一页面失败时停止输出，避免材料缺页。
- “合并”“加页码”“解密”“去水印”“压缩”只执行对应工具，不自动进入预处理/OCR。
- 压缩只有用户明确提出时才单独执行；统一入口中的默认压缩是预处理输出策略的一部分。
- 水印去除只在用户明确要求时执行，不作为默认自动步骤。

## 常用流程

### 1. 一键处理扫描 PDF

```bash
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf
```

`auto` 默认使用本地 RapidOCR 原图直送：先逐页检测页内倾角，超过 0.3° 且不超过 5° 时在 PDF 内容流上无损旋正，不重栅格化、不重压缩扫描图像；OCR 再基于旋正后的页面生成透明文字层。无可靠正文墨迹、页面盒异常或角度超出安全阈值的页面保持原状并记录原因。RapidOCR 不可用或失败时回退 `ocrmypdf` 原生方向检测、纠偏和清理。显式预处理路径仍以 `medium` 的 200 DPI、JPEG 质量 72、色度子采样 1 为目标，并以 25MP 保护异常大画布；确需裁剪或统一重栅格化时使用 `--enable-crop` 或 `--force-raster-preprocess`。电子/混合 PDF 自动保留原有层。文件大小限制很严时使用：

```bash
python3 scripts/pdf-preprocess-ocr.py --input input.pdf --output output.pdf --compress-level high
```

确需保留超大栅格时可显式调高上限；`--max-preprocess-megapixels 0` 会关闭保护，但可能显著增加内存占用和 OCR 跳页风险。

`--local-only` 保留为兼容参数；`auto` 默认已不上传。

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

### 3. 拍照件转规整 PDF

```bash
python3 scripts/pdf-photo-normalize.py \
  --input summons.jpg \
  --output summons-regular.pdf \
  --report /tmp/summons-report.json
```

先按纸边纠正透视；纸边缺失时按文本行簇识别可见主体、主文书和空白表格线网。再用可靠表框、长横线簇或正文投影校正残余的横竖偏斜，合成映射后从原图取样。完整纸边选用 A4 时铺满标准页框；内容主体按可见比例等比排版。适度增强文字和纸底的对比度。多页 TIFF 等多帧输入须先拆成单页图像。需要可搜索文本时，用既有本地 OCR 处理规整件。 [拍照件参数和回退规则](references/pdf-workflows.md#拍照件规整参数)

```bash
python3 scripts/pdf-ocr.py \
  --input summons-regular.pdf \
  --output summons-searchable.pdf \
  --backend rapidocr_local --preprocessed
```

多张照片按自然文件名顺序合成一个 PDF：

```bash
python3 scripts/pdf-photo-batch.py \
  --input /path/to/photo-dir \
  --output merged-regular.pdf \
  --report /tmp/photo-batch-report.json
```

目录内 JPG/PNG/TIFF/BMP/WebP 逐张进入单页规整流程后合并；也可显式传入多个文件或目录，顺序为参数顺序加目录内自然文件名排序。任一张失败即停止，不输出缺页 PDF。

纸面四边检测不可靠时（纸边贴画面、深色桌面上有黑色物件、缺角），用 `--quad` 直接指定四角，坐标为 0–1 归一化值、相对 EXIF 转正后的画面，顺序任意。批量入口用 `--quad-file` 传 JSON，键为照片文件名，值为 4 个 `[x, y]` 点；未列出的照片继续走自动检测。指定四角后仍会执行表框与正文投影纠斜，选用 A4 时与完整纸边一样铺满页框。照片大致正拍（相对正放约 45° 以内）时左上角取最靠近画面左上方的角；接近 45° 时按竖版比例选定。侧拍超过约 45° 时上方向有几何歧义，成品可能横竖颠倒，用 `--rotate 90/270` 纠正。

```bash
python3 scripts/pdf-photo-normalize.py \
  --input page.jpg --output page.pdf \
  --quad "0.100,0.094,0.897,0.105,0.940,0.976,0.086,0.966"

python3 scripts/pdf-photo-batch.py \
  --input /path/to/photo-dir --output merged.pdf \
  --quad-file /tmp/quads.json --bw
```

`--bw` 把输出转为黑白：先用形态学闭运算估计纸面背景并做除法归一，再按 `--bw-high`（默认 235，高于该值视为纸面）与 `--bw-low`（默认 195，低于该值视为墨迹）做柔和二值化，笔画边缘保留灰阶过渡，签名与印章不丢失。黑白页面直接跳过阴影归一与对比度曲线。

### 4. 只做 OCR 文字层

```bash
python3 scripts/pdf-ocr.py --input input.pdf --output output.pdf
```

默认后端为 `auto`：全程本地优先 RapidOCR（中文行级识别质量好、不出本机），未安装或失败时回退 `ocrmypdf`。敏感材料的本地中文 OCR 推荐先安装 RapidOCR：

```bash
pip install rapidocr
```

`--allow-external-upload` 仅为旧命令兼容参数，不再控制后端选择。Paddle 的服务端方向矫正和去畸变默认关闭，避免 OCR 坐标与原图空间不一致。

```bash
# 强制本地兜底
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --backend local_ocrmypdf

# 强制本地 RapidOCR（onnx 本地推理，中文质量好且不出本机）
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf --backend rapidocr_local

# 显式使用 PaddleOCR API；需确认当前文件允许上传
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

PP-OCRv6 文字模型默认开启 `--actualtext`：文字层生成后再调一次 PP-StructureV3 拿版面，融合出自然段并以 `/ActualText` marked-content 写入 PDF。Paddle 文字层还会用本地几何规则识别正文多行段落，把段内字号向下统一到现有最小安全值，同时保留原行坐标和横向框宽，用于改善 PDF Expert 的段落推断。`--no-actualtext` 可关闭；`--layout-dump FILE` 复用已有版面 dump 避免二次 API 调用。阅读器兼容性见下文第 5 节。

### 5. 自然段文本与 PDF 复制换行

双层 PDF 的文字层按行叠层（保护选区坐标精度），直接从 PDF 复制会按物理行断行。解决方式有两条：

**默认：`/ActualText` + 独立 Markdown。** `--actualtext`（默认开启）把自然段写入 PDF 的 `/ActualText` marked-content，同时保留行级字形坐标。实测各阅读器支持：

| 提取方式 | 从 PDF 复制的段落连续性 |
|---|---|
| Poppler（`pdftotext -raw`、`pdftotext` 默认） | ✅ 整段连续，无换行 |
| PDF Expert | ⚠️ 忽略 `/ActualText`，但会按字号和几何自行推断段落；Paddle 正文段落样式归一可减少换行，不保证完全消除 |
| PyMuPDF、pypdf、macOS 预览（PDFKit） | ❌ 仍按物理行断行 |

因此 Poppler 用户能直接从 PDF 拿到段落级文本；PDF Expert 只能做阅读器启发式改善；macOS 预览用户复制仍会断行。跨阅读器需要稳定段落文本时，显式输出独立 Markdown；默认不在案件材料旁生成正文副本：

```bash
python3 scripts/pdf-ocr.py -i input.pdf -o output.pdf \
  --backend paddle_api --clean-text-output output-clean.md
```

独立 Markdown 也可由 `pdf_ocr_paragraphs.py` 生成。个别自然段若跳过被排除的行（如印章碎片），因物理行不连续无法包裹，会降级为行级（文字不丢失，仅该段复制按行断行）。

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

### 本地 RapidOCR（推荐，本地优先引擎）

```bash
pip install rapidocr
```

安装后 `auto` 会优先使用 RapidOCR（onnx 本地推理，中文行级识别质量明显高于 tesseract，且全程不出本机）；首次运行自动下载检测/识别模型（各约 5-16MB，仅一次）。也可显式指定 `--backend rapidocr_local`。

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
2. 逐页实测并记录页内倾角、方向、清晰度、裁剪边界和文件体积。正文页残余倾角超过 0.3° 时需要矫正或说明原因。拍照件另检查表格横竖线、细字与印章在导出页面上的可读性。
3. 对双层 PDF 测试文字搜索、复制和关键词命中。
4. 向用户说明实际使用的后端、输出文件路径和任何回退情况。

## PaddleOCR 坐标与旋转页（v2.11.1+）

PaddleOCR API 的行级 poly 使用正向渲染图的左上原点像素坐标；PyMuPDF 页面坐标同样使用左上原点。不要按文字分布猜测 y 原点，也不要执行 `page_height - y` 翻转。

输入 PDF 若依赖 rotation 元数据装正，Paddle 路径会先用 PyMuPDF 无损移除 rotation，把原页面内容变换为 `rotation=0` 的正存页面，再按原有缩放和文字排版逻辑叠层。该过程不重采样扫描图，不改变可见页面像素。MinerU 等尚未验证坐标契约的后端继续保持原行为，不复用 Paddle 的坐标假设。
