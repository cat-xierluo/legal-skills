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

## 文字框对齐，但复制出的文字不正确

先区分“文字层损坏”和“OCR 本身误识别”：至少用 PyMuPDF、pypdf、`pdftotext` 交叉抽取，并把结果与 OCR sidecar 对比。三种抽取结果一致且与 sidecar 一致时，说明 PDF Unicode 映射正常，错误来自识别引擎；不要再用关键词命中或词框越界率证明逐字准确。

敏感材料使用统一入口的本地路径：

```bash
python3 scripts/pdf-preprocess-ocr.py -i input.pdf -o output.pdf --local-only
```

该路径默认保留原扫描分辨率并使用 OCRmyPDF 内置方向检测、纠偏和清理，避免统一重采样及预压缩降低 Tesseract 识别率。若仍有明显中文错字，本地 Tesseract 已达到能力边界；允许外传时改用默认 PaddleOCR `PP-OCRv6`，不允许外传时必须把结果标为需要人工复核，不能把可搜索性等同于文本正确性。

PaddleOCR 路径同样默认直送原 PDF。若文字选区位置正确但复制内容仍有少量错误，先区分正文误识与印章/水印噪声；不要为单份材料写死自动删除规则。需要零差异交付时，保留 Paddle 原始版，并另生成明确标注的人工复核版。

## 外部 PaddleOCR API 调用失败

1. 先检查接口地址与端口
2. 官方协议请确认请求体包含 `file` + `fileType(0)`
3. 确认响应是 `errorCode=0`，且 `result/data` 中包含 `ocrResults` 或 `layoutParsingResults`
4. 若服务端直接返回成品 PDF，也支持 `output_pdf_base64` / `output_pdf_url` / `output_pdf_path`
5. 协议不一致时可切换：`--paddle-api-protocol official|legacy`
6. 如需临时保障可用性，移除 `--no-paddle-fallback-local`（允许回退本地）

## 双层 PDF 看起来发糊 / 清晰度下降

```bash
# 纯扫描 PDF 一键流程默认 medium 合并输出：约 200 DPI + JPEG 质量 72 + 默认不裁剪
python3 scripts/pdf-preprocess-ocr.py -i input.pdf -o output.pdf

# 电子/混合 PDF 会自动保留原有文字、矢量、图片和批注层，不做上述栅格化

# 如需进一步提升清晰度
python3 scripts/pdf-preprocess-ocr.py -i input.pdf -o output.pdf \
  --dpi 300 --pdf-jpeg-quality 95

# 若想控制体积
python3 scripts/pdf-preprocess-ocr.py -i input.pdf -o output.pdf \
  --compress-level high
```

## 预处理后提示页面过大并跳过 OCR

手机图片转换的 PDF 可能把像素尺寸直接当作 PDF point，导致 200 DPI 预处理被放大到 50MP 以上。统一入口默认以 25MP 单页上限自动降低实际 DPI；看到 `[像素保护]` 提示属于正常保护行为。确实需要更大位图时可显式提高：

```bash
python3 scripts/pdf-preprocess-ocr.py -i input.pdf -o output.pdf \
  --max-preprocess-megapixels 40
```

不要只把 `--skip-big` 调大：那会让 OCR 接收已经异常放大的页面，可能造成内存峰值和超时。`--max-preprocess-megapixels 0` 仅用于明确接受该风险的场景。

## 中文乱码

确保使用 UTF-8 编码。
