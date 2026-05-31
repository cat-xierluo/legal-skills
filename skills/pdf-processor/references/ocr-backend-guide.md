# OCR 后端配置与对比指南

## 后端选择建议

| 需求 | 推荐方案 | 说明 |
| --- | --- | --- |
| 可搜索双层 PDF + 拍照件矫正（推荐） | PaddleOCR VL-1.5 API（`auto` 默认优先） | 支持方向矫正、去畸变、版面分析、图表识别、印章识别；返回矫正后图片可替换 PDF 原始页面 |
| 可搜索双层 PDF（PP-OCRv5 高速） | PaddleOCR PP-OCRv5 API | 纯 OCR，速度更快，支持手写体/竖排文本，适合平扫件 |
| 已接入 MinerU 并复用其服务 | `--backend mineru_api` 或 `auto` | 支持双层 PDF + 结构化解析（Markdown/JSON/docx/html/latex），但无图像预处理能力 |
| 尚未配置 API | `pdf-preprocess-ocr.py` 默认 `auto` | 提示先配 API，然后回退 `ocrmypdf` |
| 追求极致稳健兜底 | `--backend local_ocrmypdf` | 标准实现，成熟稳定 |
| 需要归档标准 | `--backend local_ocrmypdf --output-type pdfa` | PDF/A-2b 格式 |

> 历史保留的本地 PaddleOCR 双层 PDF 实现已移至 `scripts/pdf_ocr_paddle_local.py`。该实现不属于公开默认后端，后续如需在高性能本地硬件上恢复实验，可通过内部编排接入。

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
  - `PaddleOCR-VL-1.5`（默认推荐）：block 级结构，版面分析 + 方向/去畸变矫正 + 图表识别 + 印章识别 + 异形框定位
  - `PP-OCRv5`：文本行级 OCR，速度更快，支持手写体/竖排文本
  - `PP-StructureV3`：复杂版面/表格/图文混排
- 任务提交：`POST multipart/form-data` 到 `/api/v2/ocr/jobs`
- 结果轮询：`GET /api/v2/ocr/jobs/{jobId}`（状态 pending → running → done/failed）
- 结果下载：JSONL 格式，每行包含一页 OCR 结果（文字 + 坐标 + 矫正图片）
- 鉴权方式：`Authorization: token {TOKEN}`
- PP-OCRv5 独有参数：`useTextlineOrientation`（文本行方向矫正）、`textDetLimitSideLen`、`textDetThresh` 等
- VL-1.5 独有参数：`useLayoutDetection`、`useChartRecognition`、`layoutShapeMode`、`promptLabel`、`restructurePages` 等
- 本地叠层：从 JSONL 解析坐标后本地生成双层 PDF
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
