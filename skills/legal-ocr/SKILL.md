---
name: legal-ocr
description: 本技能应在用户需要 OCR、扫描识别、图片文字识别、文档识别，或将 PDF、图片、Office 文档、URL 转换为 Markdown 时使用。检测到法律材料时可进行保守的法律术语与文书结构优化。不要用于法律事实判断、补写缺失内容、语义改写、印章深度识别或图表实体分析。
version: "1.3.1"
license: MIT
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
---
# Legal OCR

本技能用于 OCR、扫描识别、图片文字识别、文档识别，以及把 PDF、图片、Office 文档和 URL 转换为可继续编辑、分析和归档的 Markdown。它首先是通用 OCR 入口；当结果被识别为法律材料时，再自动启用保守型法律后处理。默认使用配置优先的自动路由：

- 只配置 PaddleOCR：PaddleOCR 支持的 PDF / 图片优先走 PaddleOCR；超出能力边界时再提示或改走 MinerU 支持链路。
- 只配置 MinerU Token：所有 MinerU 支持的输入统一走 MinerU，包含 PDF、图片、Office、远程文档 URL 和网页 URL。
- 同时配置两套 API：本地 PDF / 图片优先 PaddleOCR，Office / 网页 URL 优先 MinerU；首选后端出现额度、频率、鉴权、网络或服务失败时自动尝试候选后端。
- 两套 API 都未配置：使用 MinerU 轻量接口处理小文件，并在超限时提示补充 Token。

旧的 `paddle-ocr` 和 `mineru-ocr` 保持可用；本技能是新的统一入口，目标是覆盖两者的常用 OCR/转换场景。

## 何时使用

在以下场景使用本技能：

- 用户明确需要 OCR、扫描识别、图片文字识别或文档识别。
- 输入可能是 PDF、图片、Office 文档、远程文档 URL 或网页 URL，并希望转成 Markdown。
- 希望保留 archive，便于复核原文件、后端结果、Markdown 和图片资源。
- 需要自动选择 OCR 后端，而不是手动判断该用 PaddleOCR 还是 MinerU。
- 希望非法律材料保持通用 OCR 输出，法律材料再做术语和文书结构优化。

不优先使用本技能的场景：

- 只需要快速读取一小段清晰文本，且不需要 Markdown 文件和归档。
- 需要基于上下文改写事实、补充缺失信息、印章深度标注或图表语义分析；这些能力仍在后续计划中。

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| `python3` | macOS 通常已内置 |
| `uv` | macOS: `brew install uv` |

### Python 包

脚本使用 `uv run` 执行，依赖写在脚本头部；推荐直接使用 `uv run scripts/convert.py`，无需单独维护 `requirements.txt`。

| 包名 | 用途 | 安装命令 |
|------|------|----------|
| `httpx` | 调用 PaddleOCR 与 MinerU API | `pip install httpx` |
| `pypdfium2` | 读取 PDF 页数与拆分页码范围 | `pip install pypdfium2` |

如直接用 `python scripts/convert.py` 运行且缺少依赖，脚本会给出安装提示。

## 首次配置

复制配置模板：

```bash
cd legal-ocr/config
cp .env.example .env
nano .env
```

可选配置：

- PaddleOCR：填写 `PADDLEOCR_DOC_PARSING_API_URL` 和 `PADDLEOCR_ACCESS_TOKEN`。
- MinerU Token：填写 `MINERU_API_TOKEN`；不填时小文件默认走 MinerU 轻量接口。
- 自动路由：保持 `LEGAL_OCR_BACKEND=auto`。
- 法律术语优化：保持 `LEGAL_OCR_LEGAL_TERMS=auto`，只在检测到法律材料时启用；如需强制启用可设为 `true`，如需关闭可设为 `false`。
- 通用硬换行优化：保持 `LEGAL_OCR_LINE_MERGE=true`；如需加载自定义法律术语，设置 `LEGAL_OCR_CUSTOM_TERMS_PATH`。

本技能也会尝试读取环境变量和 `~/.mineru/config.yaml` 中的 MinerU Token。
PaddleOCR 也兼容 `pdf-processor` 使用的 `PADDLE_OCR_API_ENDPOINT` / `PADDLE_OCR_API_KEY`，并支持 `/api/v2/ocr/jobs` 异步任务接口。

## 常用命令

在技能根目录运行：

```bash
uv run scripts/convert.py "/path/to/file.pdf"
uv run scripts/convert.py "/path/to/file.pdf" --pages "1-20"
uv run scripts/convert.py "/path/to/file.pdf" --backend paddle
uv run scripts/convert.py "/path/to/file.pdf" --backend paddle --paddle-model PaddleOCR-VL-1.5
uv run scripts/convert.py "https://example.com/document.pdf" --backend auto
uv run scripts/convert.py "https://example.com/article" --backend mineru
uv run scripts/convert.py "/path/to/judgment.pdf" --legal-terms always
uv run scripts/convert.py checktoken
```

兼容 JXA 入口：

```bash
/usr/bin/osascript -l JavaScript scripts/convert.js "/path/to/file.pdf"
```

可选参数：

| 参数 | 说明 |
|------|------|
| `--backend auto|paddle|mineru` | 指定后端；默认读取 `LEGAL_OCR_BACKEND`，未配置时为 `auto` |
| `--output <path>` | 输出 Markdown 路径或目录 |
| `--pages <spec>` | 页码范围，如 `1-20`、`1-5,8,10-12` |
| `--archive-name <name>` | 自定义 archive 目录名 |
| `--no-archive` | 不写入 archive |
| `--no-post-process` | 跳过全部后处理 |
| `--no-legal-terms` | 跳过法律术语优化 |
| `--legal-terms auto|always|never` | 法律术语优化模式；默认 `auto` |
| `--no-line-merge` | 跳过 OCR 硬换行整理 |
| `--model pipeline|vlm` | MinerU Token API 模型 |
| `--paddle-model PP-OCRv5|PaddleOCR-VL-1.5` | PaddleOCR 异步任务模型 |
| `--paddle-api-protocol auto|sync|async` | PaddleOCR API 协议 |
| `--paddle-api-extra-json <path>` | 合并额外 PaddleOCR optionalPayload |

## 自动分流

- `auto` 会先看用户实际配置了哪些 API；只配置一套时尽量统一走这一套，减少用户判断成本。
- 两套 API 都配置时，按材料类型选择首选后端，并把另一个可用后端作为候选。
- 如果后端返回 429、额度不足、余额不足、频率限制、鉴权失败、网络超时或服务失败，会在 `result.json` 和 `metadata.json` 的 `route.attempts` 中记录失败类别；存在候选后端时自动继续转换。
- 当前没有接入独立额度预检接口；额度判断来自 API 响应码和错误信息。若服务商提供稳定 quota endpoint，再加入转换前检查。

## OCR 与法律增强

- 非法律材料默认只做通用 Markdown 清理、空行整理和硬换行整理。
- 法律增强默认处于 `auto` 模式：先扫描 OCR 原始文本和文件名，只有命中法院、案号、当事人标签、判决/裁定结构等足够信号时，才运行法律术语优化。
- 检测结果会写入 `result.json` 和 `metadata.json` 的 `postprocess.legal_context` / `legal_context` 字段。
- 如用户确认输入一定是法律材料，可使用 `--legal-terms always` 或 `LEGAL_OCR_LEGAL_TERMS=true` 强制启用。
- 如处理非法律材料且希望完全关闭法律替换，可使用 `--legal-terms never`、`--no-legal-terms` 或 `LEGAL_OCR_LEGAL_TERMS=false`。

## 法律术语优化

- 默认仅在检测到法律材料时启用保守型法律术语后处理，只处理高置信 OCR 断字和常见误识别，不做事实补全或语义改写。
- 默认覆盖文书名称、主体标签、诉讼程序、证据材料、法院文书结构词等常见词。
- 默认整理明显的 OCR 硬换行，只合并同一中文段落内的物理换行；标题、当事人标签、编号、表格、引用和 Markdown 结构会保留。
- 每次替换会写入 `postprocess_log.json`，并保留 `result_raw.md` 供复核。
- 自定义术语格式见 `references/legal_terms.md`。

## 输出

- Markdown 默认保存在源文件同目录；远程 URL 默认保存在当前目录。
- 图片资源默认保存在 Markdown 同目录的 `<文件名>_images/`。
- archive 默认保存在 `legal-ocr/archive/时间戳_文件名/`。

## 输入/输出

### 输入

- 必需：本地文件路径、远程 URL，或 `checktoken`。
- 可选：`--backend`、`--output`、`--pages`、`--archive-name`、`--model` 和 PaddleOCR 相关参数。

### 输出

- Markdown 主文件：转换后的可编辑文本。
- 图片目录：后端返回或 Markdown 引用的图片资源。
- Archive：默认保存输入副本、原始结果、最终结果、后端响应、路由记录和后处理日志。

archive 内包含：

- 输入文件或 URL 记录
- `output/result.md`
- `output/result_raw.md`
- `output/result.json`
- `backend_result/`
- `metadata.json`
- 必要时包含图片资源和 `postprocess_log.json`

详细结构见 `references/output_schema.md`。

## 故障排除

| 问题 | 解决方式 |
|------|----------|
| PaddleOCR 未配置 | 补充 `PADDLEOCR_DOC_PARSING_API_URL` 与 `PADDLEOCR_ACCESS_TOKEN`，或显式使用 `--backend mineru` |
| MinerU 轻量接口超限 | 配置 `MINERU_API_TOKEN` 后重试 |
| 一个 API 额度用尽 | 同时配置另一套 API，并保持 `--backend auto`；转换时会自动尝试候选后端 |
| 网页 URL 失败 | 网页 URL 需要 MinerU Token，不支持轻量模式 |
| DOCX/PPTX 走 PaddleOCR 失败 | Office 文档只能走 MinerU，使用 `--backend auto` 或 `--backend mineru` |
| 转换质量需复核 | 查看 archive 中的 `result_raw.md`、`result.json` 和 `backend_result/` |

## 维护

修改本技能后，同步更新本目录下的 `TASKS.md`、`DECISIONS.md` 和 `CHANGELOG.md`。
