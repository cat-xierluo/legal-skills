# 安装与依赖

## 系统依赖

### ffmpeg（必需）

视频帧提取的核心工具，必须安装。

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# 验证安装
ffmpeg -version
ffprobe -version
```

要求版本 ≥ 5.0，推荐 ≥ 7.0。本 Skill 使用 ffmpeg 的 `-progress pipe:1`、`select` 场景检测滤镜和 `mpdecimate` 去重滤镜。

### Python（必需）

要求 Python ≥ 3.10。macOS 系统自带或通过 brew 安装：

```bash
brew install python
```

### uv（必需）

用于运行 PEP 723 内联依赖的 Python 脚本。

```bash
brew install uv
```

## Python 依赖

### Pillow（自动安装）

图像处理核心库（dHash 计算、缩略图生成、OCR 预处理和联系表渲染）。相关脚本使用 PEP 723 内联依赖声明，`uv run` 时自动安装，无需手动操作。

### rapidocr-onnxruntime（可选，OCR 内容增量和证据线索多锚点需要）

本地离线 OCR 引擎，用于内容增量判断和文本相似度去重。它只在时间簇择优后的少量候选上运行，不把 OCR 原文写入报告。

```bash
# 推荐：不修改全局环境，按次注入可选依赖
uv run --with rapidocr-onnxruntime scripts/extract.py \
  -i <视频文件路径> --ocr-dedup

# 如果直接用 python3 运行，也可先安装
python3 -m pip install rapidocr-onnxruntime
python3 scripts/extract.py -i <视频文件路径> --ocr-dedup

# 对基础帧生成不保存 OCR 原文的证据线索索引
uv run --with rapidocr-onnxruntime scripts/prepare_evidence_leads.py \
  -i <基础输出目录>
```

如果未安装，`--ocr-dedup` 会跳过 OCR 内容增量与文本去重；`prepare_evidence_leads.py` 会降级为视觉主体和时序排序，不影响基础抽帧。

基础时间簇择优、加载浮层/未完成页时序覆盖识别、自适应滚动密度和视觉审计联系表只依赖 Pillow，不需要安装 RapidOCR。启用 OCR 后仍保留 SSIM 图像去重，并关闭未完成页的纯视觉自动删除，让 OCR 内容增量先完整运行；OCR 发现高可信新增金额、长编号或足量正文时可以保护相似帧，因此输出可能略多于纯视觉模式。

## 输入目录边界

后续 `prepare_evidence_leads.py`、`prepare_vision_audit.py` 和两个应用器的 `-i` 必须指向 `extract.py` 的实际基础输出目录：其中应同时存在 `_report.json` 及报告列出的 `frame_*.jpg`。Skill `archive/` 从 v0.8.1 起只保存 `_report.json` 和 `extraction_meta.json`，不含图片，不能作为后续复核输入。

## 输出目录边界

`extract.py` 会先验证参数和视频，再在目标目录同级 staging 中生成完整结果；成功前不会清理旧输出。若目标目录含未知文件、符号链接、证据线索包、视觉审计或精选结果，脚本会失败关闭。此时不要把这些文件临时删除后强行重跑，直接使用新的 `-o <新目录>`，保留原目录用于复核。

新版基础输出包含 `_video_screenshot_output.json`，它只绑定报告哈希、目录内容哈希和根目录清单，不含源视频路径。旧版没有该标记时，脚本仅在 `_report.json` 的逐帧 SHA256 与实际基础帧完全一致的情况下兼容替换。

## 首次使用检查清单

```bash
# 1. 检查 ffmpeg
ffmpeg -version

# 2. 检查 Python 版本
python3 --version

# 3. 检查 uv
uv --version

# 4. 运行（Pillow 自动安装）
uv run scripts/extract.py -i <视频文件路径>

# 5. 如需 OCR 内容增量，按次注入 RapidOCR
uv run --with rapidocr-onnxruntime scripts/extract.py \
  -i <视频文件路径> --ocr-dedup

# 6. 基础帧确认完整后，生成证据线索包（推荐 OCR；也可改用 --no-ocr）
uv run --with rapidocr-onnxruntime scripts/prepare_evidence_leads.py \
  -i <实际基础输出目录>

# 7. 只有需要进一步去重且当前模型能读图时，才准备减法审计包
uv run scripts/prepare_vision_audit.py \
  -i <实际基础输出目录> --profile weak
```
