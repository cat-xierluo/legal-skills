---
name: paddle-ocr
description: 面向法律 PDF 与扫描件的 PaddleOCR 结构化解析技能。默认将本地 PDF 或图片转换为 Markdown，并在技能内部保留可追溯 archive 归档。适用于卷宗、病历、证据材料、发票、财报、复杂扫描件、表格密集文档、公式与多栏版面。触发词包括：法律 PDF OCR、卷宗 OCR、病历 OCR、证据扫描件转 Markdown、PaddleOCR、表格识别、公式识别、版面分析、PDF 转 Markdown、复杂 PDF 解析。
version: "1.1.1"
license: MIT
author: 杨卫薪律师（微信ywxlaw）
---
# PaddleOCR 法律 PDF 转 Markdown

本技能服务于**法律材料 OCR**。默认目标不是返回一段临时文本，而是：

1. 将本地 PDF / 图片转换为可继续编辑和分析的 Markdown。
2. 在 `archive/` 下保留完整归档，便于复核、追溯和二次处理。

## 何时使用

在以下场景使用本技能：

- 需要把卷宗、病历、证据材料、法院通知、财报、票据等扫描 PDF 转成 Markdown。
- 文档包含表格、印章、页眉页脚、多栏排版、公式或复杂版面。
- 希望保留一个技能内的 archive，沉淀原文件、Markdown、结构化 JSON 和批次结果。
- 后续还要继续做法律分析、证据摘录、知识入库或 RAG 切片。

在以下场景不要优先使用本技能：

- 只是快速读取一小段清晰文本，且不需要 Markdown 和归档。
- 只是截图抄字，速度比结构化质量更重要。
- 输入不是 PDF / 常见图片格式。

## 主产出

默认主产出只有两类：

- **Markdown 文件**：保存在源文件同目录，默认与原文件同名、扩展名为 `.md`
- **archive 归档目录**：保存在 `paddle-ocr/archive/时间戳_文件名/`

archive 默认包含：

- 原始输入文件副本
- 最终 `result.md`
- 最终 `result.json`
- 批次级 `batches/*.json`
- 提取出的图片资源
- `metadata.json`

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| `python3` | macOS 通常已内置 |
| `uv` | macOS: `brew install uv` |

### Python 包

脚本使用 `uv run` 执行，依赖写在脚本头部，无需单独维护 `requirements.txt`。

## 首次配置

### 获取 API 信息

1. 打开 [PaddleOCR 官网](https://www.paddleocr.com)
2. 进入对应模型的 API 页面
3. 在示例代码中复制：
   - `API_URL`
   - `Access Token`

### 配置方式

优先编辑 `config/.env`：

```bash
cd paddle-ocr/config
cp .env.example .env
nano .env
```

必填项：

- `PADDLEOCR_DOC_PARSING_API_URL`
- `PADDLEOCR_ACCESS_TOKEN`

## 常用命令

### 主工作流：生成 Markdown + archive

在技能根目录运行：

```bash
uv run scripts/convert.py "/path/to/legal-document.pdf"
```

或继续兼容旧入口：

```bash
/usr/bin/osascript -l JavaScript scripts/convert.js "/path/to/legal-document.pdf"
```

可选参数：

```bash
uv run scripts/convert.py "/path/to/legal-document.pdf" --pages "1-20"
uv run scripts/convert.py "/path/to/legal-document.pdf" --output "/tmp/output.md"
uv run scripts/convert.py "/path/to/legal-document.pdf" --archive-name "某案卷宗-证据一"
```

### 底层调试：只调用解析接口，输出结构化 JSON

```bash
uv run scripts/layout_caller.py --file-path "/path/to/legal-document.pdf" --pretty
uv run scripts/layout_caller.py --file-url "https://example.com/document.pdf" --stdout --pretty
```

当你只想检查原始接口结果，或后续要自己解析表格/坐标信息时，使用这个底层脚本。

### 自检

```bash
uv run scripts/smoke_test.py --skip-api-test
uv run scripts/smoke_test.py
```

### 拆分页码

```bash
uv run scripts/split_pdf.py input.pdf output.pdf --pages "1-5,8,10-12"
```

## 法律 PDF 工作流

按以下顺序工作：

1. 优先使用 `scripts/convert.py`。
2. 如只需部分页码，先传 `--pages`，避免整卷上传。
3. 对大体量卷宗，脚本会按配置自动分批请求，再合并为一个 Markdown。
4. 需要复核时，到 `archive/` 查看：
   - `output/result.md`
   - `output/result.json`
   - `metadata.json`
   - `batches/*.json`

## 大文件策略

本技能为了法律材料的稳定性，默认采用**保守批次策略**：

- PDF 页数超过 `PADDLEOCR_BATCH_PAGES` 时自动分批
- 预估 Base64 大小超过 `PADDLEOCR_MAX_BASE64_MB` 时自动分批

这意味着它可能比官方上限更早拆分，但通常能降低长卷宗、病历合并件和扫描质量不稳定文档的失败率。

## 输出说明

### Markdown

- 默认保存到源文件同目录
- 如果传 `--output` 且是 `.md` 文件路径，则保存到指定路径
- 如果 `--output` 是目录，则在该目录下生成同名 `.md`

### archive

默认归档目录结构：

```text
archive/
└── 20260405_153000_文件名/
    ├── input/
    │   └── 原文件.pdf
    ├── output/
    │   ├── result.md
    │   ├── result.json
    │   └── images/
    ├── batches/
    │   ├── batch_001_1-40.json
    │   └── batch_002_41-67.json
    └── metadata.json
```

## 配置项

编辑 `config/.env`：

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `PADDLEOCR_DOC_PARSING_API_URL` | 空 | 官方要求的完整 `layout-parsing` 端点 |
| `PADDLEOCR_ACCESS_TOKEN` | 空 | 官方 Access Token |
| `PADDLEOCR_DOC_ORIENTATION` | `false` | 是否启用方向分类 |
| `PADDLEOCR_DOC_UNWARP` | `false` | 是否启用去扭曲 |
| `PADDLEOCR_CHART_RECOG` | `false` | 是否启用图表识别 |
| `PADDLEOCR_DOC_PARSING_TIMEOUT` | `600` | 单次请求超时秒数 |
| `PADDLEOCR_BATCH_PAGES` | `40` | PDF 自动分批页数阈值兼批次大小 |
| `PADDLEOCR_MAX_BASE64_MB` | `20` | 触发分批的保守大小阈值 |
| `PADDLEOCR_LOG_LEVEL` | `medium` | `low` / `medium` / `high` |

## 结果结构

如果需要理解底层 JSON 包装格式，读取：

- `references/output_schema.md`

## 故障排除

| 问题 | 解决方式 |
|------|----------|
| 未配置 API | 先补 `config/.env`，再执行 `uv run scripts/smoke_test.py --skip-api-test` |
| 403 / Token 错误 | 更新 `PADDLEOCR_ACCESS_TOKEN` |
| 请求超时 | 调大 `PADDLEOCR_DOC_PARSING_TIMEOUT`，或减少页码范围 |
| 大 PDF 失败 | 使用 `--pages` 缩小范围，或让脚本自动分批 |
| Markdown 为空 | 到 `archive/` 查看 `batches/*.json` 和 `metadata.json`，确认是否原文件质量过差 |
| 需要看原始坐标和表格结构 | 使用 `scripts/layout_caller.py`，并读取 `result.result.layoutParsingResults[*].prunedResult` |

## 维护建议

修改本技能后，同步更新：

- `TASKS.md`
- `DECISIONS.md`
- `CHANGELOG.md`
