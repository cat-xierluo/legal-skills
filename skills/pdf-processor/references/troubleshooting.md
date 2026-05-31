# 故障排除

## PDF 预处理报错

检查可选依赖是否已安装：

```bash
pip install pdf2image opencv-python pillow numpy

# macOS
brew install poppler

# Linux
sudo apt-get install poppler-utils
```

## OCR 识别失败

```bash
# 优先确认是否已配置外部 API；如果没有，可先配置 config/.env
# 若暂时不配 API，则至少确保本地兜底依赖已安装

pip install ocrmypdf

# macOS
brew install tesseract tesseract-lang

# Linux
sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim
```

## 外部 PaddleOCR API 调用失败

1. 先检查接口地址与端口
2. 官方协议请确认请求体包含 `file` + `fileType(0)`
3. 确认响应是 `errorCode=0`，且 `result/data` 中包含 `ocrResults` 或 `layoutParsingResults`
4. 若服务端直接返回成品 PDF，也支持 `output_pdf_base64` / `output_pdf_url` / `output_pdf_path`
5. 协议不一致时可切换：`--paddle-api-protocol official|legacy`
6. 如需临时保障可用性，移除 `--no-paddle-fallback-local`（允许回退本地）

## 双层 PDF 看起来发糊 / 清晰度下降

```bash
# 一键流程默认 medium 合并输出：约 200 DPI + JPEG 质量 72 + 默认不裁剪
python3 scripts/pdf-preprocess-ocr.py -i input.pdf -o output.pdf

# 如需进一步提升清晰度
python3 scripts/pdf-preprocess-ocr.py -i input.pdf -o output.pdf \
  --dpi 300 --pdf-jpeg-quality 95

# 若想控制体积
python3 scripts/pdf-preprocess-ocr.py -i input.pdf -o output.pdf \
  --compress-level high
```

## 中文乱码

确保使用 UTF-8 编码。
