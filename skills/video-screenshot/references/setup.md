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

图像处理核心库（dHash 计算、缩略图生成、OCR 预处理）。通过 `extract.py` 的 PEP 723 内联依赖声明，`uv run` 时自动安装，无需手动操作。

### rapidocr-onnxruntime（可选，OCR 内容增量需要）

本地离线 OCR 引擎，用于内容增量判断和文本相似度去重。它只在时间簇择优后的少量候选上运行，不把 OCR 原文写入报告。

```bash
# 推荐：不修改全局环境，按次注入可选依赖
uv run --with rapidocr-onnxruntime scripts/extract.py \
  -i <视频文件路径> --ocr-dedup

# 如果直接用 python3 运行，也可先安装
python3 -m pip install rapidocr-onnxruntime
python3 scripts/extract.py -i <视频文件路径> --ocr-dedup
```

如果未安装，`--ocr-dedup` 参数会自动降级为跳过 OCR 内容增量与文本去重，不影响其他功能。

基础时间簇择优、加载浮层/未完成页时序覆盖识别、自适应滚动密度和视觉审计联系表只依赖 Pillow，不需要安装 RapidOCR。启用 OCR 后仍保留 SSIM 图像去重，并关闭未完成页的纯视觉自动删除，让 OCR 内容增量先完整运行；OCR 发现高可信新增金额、长编号或足量正文时可以保护相似帧，因此输出可能略多于纯视觉模式。

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
```
