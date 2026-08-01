# OCR 后端配置与对比指南

## 后端选择建议

| 需求 | 推荐方案 | 说明 |
| --- | --- | --- |
| 默认可搜索双层 PDF | `auto` → PaddleOCR `PP-OCRv6` | 已配置 API 时默认首选并直送原 PDF；行级坐标比 VL 块级坐标更适合文字层匹配 |
| 自然段 Markdown + 干净文字层 | `PP-OCRv6` 文字 + `PP-StructureV3` 版面 | 只按几何关系融合，不采用 Structure 块文本；过滤 `seal` 区域 OCR 噪声 |
| 干净扫描件、表格密集页 | PaddleOCR `PP-StructureV3` | 从 `overall_ocr_res` 读取行级坐标；带重复水印的拍照件可能产生较多噪声，不作为默认 |
| 复杂版面结构提取 | PaddleOCR-VL-1.6 / 1.5 | 返回版面块和阅读结构，但块级坐标较粗，不作为双层 PDF 默认模型 |
| 已接入 MinerU 并复用其服务 | `--backend mineru_api` 或 `auto` | 支持双层 PDF + 结构化解析（Markdown/JSON/docx/html/latex），但无图像预处理能力 |
| 敏感材料禁止外传 | `--local-only` | 跳过已配置的 PaddleOCR/MinerU，仅运行本地 `ocrmypdf`；统一入口默认保留原扫描分辨率并使用 OCRmyPDF 内置预处理 |
| 外部 API 故障兜底 | `local_ocrmypdf` | `auto` 在外部服务全部失败后自动进入该路径 |
| 需要归档标准 | `--backend local_ocrmypdf --output-type pdfa` | PDF/A-2b 格式 |

> 历史保留的本地 PaddleOCR 双层 PDF 实现已移至 `scripts/pdf_ocr_paddle_local.py`。该实现不属于公开默认后端，后续如需在高性能本地硬件上恢复实验，可通过内部编排接入。

> `auto` 在 API 已配置时会传输完整 PDF。输入含姓名、案号、医疗、账号等敏感信息时，Agent 必须先取得针对当前文件的明确上传授权；授权不自动覆盖同目录或其他材料。材料不允许外传时必须使用 `--local-only`。旧参数 `--allow-external-upload` 只保留命令兼容，不再充当上传门禁。OCR 可读文本归档仍默认关闭，需显式使用 `--archive-results`。

> 本地 `ocrmypdf` 的文字层是真实 Tesseract 输出，但“文字框对齐、可选择、关键词命中”不代表逐字正确。统一入口不会再默认先重采样、预压缩后交给 Tesseract；需要裁剪时显式使用 `--enable-crop`，需要复现统一栅格预处理时使用 `--force-raster-preprocess`。中文法律扫描件对准确率要求较高且允许外传时，仍优先使用 PaddleOCR `PP-OCRv6`。

> PaddleOCR `PP-OCRv6` 也默认接收原 PDF，不再由统一入口先栅格化和预压缩。真实拍照扫描样本中，v5/v6 原图直送的原始全文 CER 均为 2.98%；以 Structure 版面区域排除两行印章噪声并重建自然段后，v6 输出在 470 字符人工基准上为 0%。该结果只证明本样本，不替代跨文档基准。`--enable-crop` 或 `--force-raster-preprocess` 会显式覆盖原图直送策略。

## 推荐 API 配置方式

```bash
# 使用本地 config/.env 管理 API 配置
cp config/.env.example config/.env

# 在 config/.env 中填写：
# OCR_API_ORDER="paddle,mineru"
# PADDLE_OCR_API_ENDPOINT="https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
# PADDLE_OCR_API_KEY="..."
# MINERU_API_BASE="https://mineru.net/api/v4"
# MINERU_API_TOKEN="..."
```

## 外部 API 协议说明

### PaddleOCR API（异步任务模式）

- **推荐首选后端**：具备方向矫正、去畸变、版面分析等图像预处理能力，尤其适合拍照件
- 模型：
  - `PP-OCRv6`（双层 PDF 默认）：文本行级 OCR，坐标粒度更适合文字层匹配
  - `PP-OCRv5`：兼容旧流程；可显式指定做对照或回退
  - `PP-StructureV3`：复杂版面/表格/图文混排；从 `overall_ocr_res` 读取行级坐标
  - `PaddleOCR-VL-1.6` / `PaddleOCR-VL-1.5`：block 级结构与版面信息，适合结构化输出
- 任务提交：`POST multipart/form-data` 到 `/api/v2/ocr/jobs`
- 结果轮询：`GET /api/v2/ocr/jobs/{jobId}`（状态 pending → running → done/failed）
- 结果下载：JSONL 格式，每行包含一页 OCR 结果（文字 + 坐标 + 矫正图片）
- 鉴权方式：`Authorization: bearer {TOKEN}`
- PP-OCRv5/v6 行级参数：`useTextlineOrientation`（文本行方向矫正）、`textDetLimitSideLen`、`textDetThresh` 等
- VL-1.5 独有参数：`useLayoutDetection`、`useChartRecognition`、`layoutShapeMode` 等；VL-1.6/StructureV3 只发送已验证的通用预处理参数
- 本地叠层：从 JSONL 解析坐标后本地生成双层 PDF
- 坐标约束：关闭服务端方向/去畸变以保持原图坐标；云端结果按行级或块级处理，不推断字符级坐标
- 环境变量别名：`TOKEN` → `PADDLE_OCR_API_KEY`、`API_URL` → `PADDLE_OCR_API_ENDPOINT`
- 详细参数说明：`references/paddleocr-api-guide.md`

### MinerU API（异步任务）

- 文档结构解析后端：擅长版面分析、公式/表格提取、多格式输出（Markdown/JSON/docx/html/latex）
- **不具备图像预处理能力**（无方向矫正、去畸变），适合平扫件或已矫正的文档
- 模型：`pipeline`（默认）/ `vlm`（推荐，精度更高） / `MinerU-HTML`（HTML 文件）
- 提交方式：
  - URL 模式：`POST /api/v4/extract/task`（传入文件 URL）
  - 文件上传：`POST /api/v4/file-urls/batch`（获取上传地址 → PUT 上传，≤50 文件/次）
  - 批量 URL：`POST /api/v4/extract/task/batch`（≤50 URL/次）
- 结果轮询：`GET /api/v4/extract-results/batch/{batch_id}`
- 支持 `page_ranges` 参数分段处理（上限 200 页/文件）
- 支持 `extra_formats` 输出 docx/html/latex
- 支持回调通知（`callback` + `seed` 签名验证）
- Token 时效约 90 天（3 个月），过期提示更新：<https://mineru.net/apiManage/token>
- 每日配额 1000 页高优先级，超出后降为低优先级
- 支持 PDF/图片/Word/PPT/Excel 等多格式输入
- 详细参数说明：`references/mineru-api-guide.md`
