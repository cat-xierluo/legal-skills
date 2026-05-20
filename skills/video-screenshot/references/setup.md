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

### rapidocr-onnxruntime（可选，OCR 去重需要）

本地离线 OCR 引擎，用于基于文本相似度的帧去重。

```bash
# pip 安装
pip install rapidocr-onnxruntime

# 或 uv 安装
uv pip install rapidocr-onnxruntime
```

如果未安装，`--ocr-dedup` 参数会自动降级为跳过 OCR 去重，不影响其他功能。

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

# 5. 如需 OCR 去重，安装 RapidOCR
pip install rapidocr-onnxruntime
uv run scripts/extract.py -i <视频文件路径> --ocr-dedup
```
