# MinerU API 接入指引（法律文档场景）

本文档用于指导 `pdf-processor` 接入 MinerU API。

## 1. API 模式对比

MinerU 提供两种 API：

| 维度 | Precision Extract API | Agent Lightweight API |
| --- | --- | --- |
| Token | 需要 | 不需要（IP 限流） |
| 接口 | `/api/v4/extract/task` 或 `/api/v4/file-urls/batch` | `/api/v1/agent/parse/url` 或 `/api/v1/agent/parse/file` |
| 模型 | `pipeline`（默认）/ `vlm`（推荐）/ `MinerU-HTML` | 固定 pipeline 轻量模型 |
| 文件大小 | ≤ 200MB | ≤ 10MB |
| 页数限制 | ≤ 200 页 | ≤ 20 页 |
| 批量 | 支持（≤ 200 文件） | 不支持（单文件） |
| 输出 | ZIP（Markdown + JSON + 可选 docx/html/latex） | 仅 Markdown（CDN 链接） |
| 调用方式 | 异步（提交 → 轮询） | 异步（提交 → 轮询） |

本 Skill 使用 **Precision Extract API**（支持更复杂的文档处理和坐标提取）。

## 2. 适用说明

- 输入：本地 PDF / 图片 / Word / PPT / Excel 文件
- 输出：MinerU 任务结果 ZIP（含 `*_middle.json` / `*_model.json` / `full.md`，可选 `docx`/`html`/`latex`）
- 本 Skill 行为：自动解析结果中的文本与坐标，并本地叠层生成双层 PDF
- **不具备图像预处理能力**（无方向矫正、去畸变），适合平扫件或已矫正的文档

## 3. API 基础配置

在 `config/.env` 中配置：

```bash
MINERU_API_BASE="https://mineru.net/api/v4"
MINERU_API_TOKEN="your_mineru_token_here"
MINERU_USER_TOKEN=""
```

可选别名（脚本会自动映射）：

```bash
MINERU_API_BASE_URL="https://mineru.net"
MINERU_BASE_URL="https://mineru.net"
MINERU_TOKEN="your_mineru_token_here"
```

说明：
- `MINERU_API_BASE` 可配置为 `https://mineru.net/api/v4` 或 `https://mineru.net`，脚本会自动兼容
- `MINERU_USER_TOKEN` 为可选项，用于部分网关需要的 `token` 请求头
- 每账号每日 1000 页高优先级配额，超出后降为低优先级

### 3.1 Token 过期提醒（90 天）

- MinerU API Token 约 90 天（3 个月）有效
- 当接口返回 `401/403`（错误码 A0202/A0211）时，脚本会自动提示"Token 可能过期"
- 更新地址：<https://mineru.net/apiManage/token>
- 更新后请同步修改 `config/.env` 中的 `MINERU_API_TOKEN`

## 4. Precision Extract API 接口详情

### 4.1 提交方式

MinerU 支持三种提交方式：

| 方式 | 接口 | 说明 |
| --- | --- | --- |
| URL 提交 | `POST /api/v4/extract/task` | 传入文件 URL，无需上传 |
| 文件上传 | `POST /api/v4/file-urls/batch` | 先获取上传地址，再 PUT 上传文件（≤50 文件/次） |
| 批量 URL | `POST /api/v4/extract/task/batch` | 批量传入文件 URL（≤50 URL/次） |

本 Skill 当前使用**文件上传**模式（`/api/v4/file-urls/batch`）。

### 4.2 文件上传流程（本 Skill 使用）

```
1. POST /api/v4/file-urls/batch  → 获取 batch_id + 上传 URL
2. PUT 上传 URL                   → 上传 PDF 文件
3. GET /api/v4/extract-results/batch/{batch_id}  → 轮询任务状态
4. 下载 full_zip_url 对应的结果 ZIP
5. 解析 middle/model JSON，提取文本与坐标，生成双层 PDF
```

### 4.3 请求参数

#### 提交任务通用参数

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `model_version` | string | 否 | `pipeline`（默认）/ `vlm`（推荐，精度更高）/ `MinerU-HTML`（HTML 文件） |
| `is_ocr` | bool | 否 | 是否启用 OCR，默认 false。仅 pipeline/vlm 生效 |
| `enable_formula` | bool | 否 | 是否启用公式识别，默认 true。仅 pipeline/vlm 生效 |
| `enable_table` | bool | 否 | 是否启用表格识别，默认 true。仅 pipeline/vlm 生效 |
| `language` | string | 否 | 文档语言，默认 `ch`。仅 pipeline/vlm 生效 |
| `extra_formats` | [string] | 否 | 额外输出格式：`docx`/`html`/`latex`（Markdown+JSON 为默认，无需设置） |
| `page_ranges` | string | 否 | 页面范围，如 `"2,4-6"` 或 `"2--2"`（倒数第二页） |
| `callback` | string | 否 | 回调通知 URL（HTTP/HTTPS），完成后 POST 推送结果 |
| `seed` | string | 否 | 回调签名随机字符串（使用 callback 时必填） |
| `no_cache` | bool | 否 | 是否忽略缓存，默认 false |
| `cache_tolerance` | int | 否 | 缓存容忍时间（秒），默认 900（15 分钟） |

#### 文件上传模式特有参数

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `files[].name` | string | 是 | 文件名（含扩展名） |
| `files[].data_id` | string | 否 | 业务数据 ID（≤128 字符） |
| `files[].is_ocr` | bool | 否 | 单文件 OCR 开关 |
| `files[].page_ranges` | string | 否 | 单文件页面范围 |

### 4.4 任务状态

| 状态 | 说明 |
| --- | --- |
| `waiting-file` | 等待文件上传 |
| `pending` | 排队中 |
| `running` | 解析中 |
| `converting` | 格式转换中 |
| `done` | 完成 |
| `failed` | 失败 |

### 4.5 响应结构

成功响应：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "batch_id": "...",
    "extract_result": [{
      "file_name": "example.pdf",
      "state": "done",
      "full_zip_url": "https://cdn-mineru.openxlab.org.cn/pdf/xxx.zip",
      "err_msg": "",
      "extract_progress": {
        "extracted_pages": 10,
        "total_pages": 20,
        "start_time": "2025-01-20 11:43:20"
      }
    }]
  }
}
```

### 4.6 支持的文件格式

- PDF、图片（png/jpg/jpeg/jp2/webp/gif/bmp）
- Word（doc/docx）、PPT（ppt/pptx）、Excel（xls/xlsx）
- HTML（需 `model_version: "MinerU-HTML"`）

### 4.7 常见错误码

| 错误码 | 说明 | 解决方案 |
| --- | --- | --- |
| A0202 | Token 无效 | 检查 Token 或 Bearer 前缀 |
| A0211 | Token 过期 | 更新 Token |
| -500 | 参数错误 | 检查参数类型和 Content-Type |
| -60002 | 文件格式匹配失败 | 确保文件名含正确扩展名 |
| -60005 | 文件超过 200MB | 压缩或拆分文件 |
| -60006 | 页数超过 200 页 | 拆分文件或使用 page_ranges |
| -60018 | 每日提取任务达到上限 | 次日再试 |

## 5. 顺序控制（与 Paddle 共存）

当同时配置 MinerU 与 Paddle API 时，可通过以下变量控制 `auto` 模式优先级：

```bash
OCR_API_ORDER="paddle,mineru"
```

支持值：`mineru`、`paddle`（逗号分隔）。

## 6. 参考文档

- MinerU 官方 API 文档：<https://mineru.net/apiManage/docs>
- MinerU 产品文档：<https://mineru.net/doc/docs/>
- 输出文件结构说明：<https://opendatalab.github.io/MinerU/reference/output_files/>
