# 输出结构说明

`legal-ocr` 有三类输出：

1. Markdown 主文件：给用户继续编辑、分析或入库。非法律材料保持通用 OCR 输出；法律材料会按检测结果启用保守增强。
2. 图片资源目录：保存后端返回或 Markdown 引用的图片资源。
3. archive：保存可追溯的完整转换记录。

## 主输出

默认输出位置：

- 本地文件：源文件同目录，文件名与源文件同名，扩展名为 `.md`
- 远程 URL：当前执行目录
- 显式 `--output`：按指定文件或目录输出

如有图片资源，默认保存到：

```text
<markdown_stem>_images/
```

## Archive 结构

```text
archive/
└── 20260520_153000_某案卷宗/
    ├── input/
    │   ├── 原文件.pdf
    │   └── source_url.txt
    ├── output/
    │   ├── result.md
    │   ├── result_raw.md
    │   ├── result.json
    │   └── images/
    ├── batches/
    │   └── batch_001_1-40.json
    ├── backend_result/
    │   ├── result.zip
    │   ├── token_poll.json
    │   └── batch_001_all-pages.json
    ├── postprocess_log.json
    └── metadata.json
```

说明：

- `input/`：本地输入副本；远程 URL 保存为 `source_url.txt`。
- `output/result.md`：最终 Markdown，可能经过基础后处理。
- `output/result_raw.md`：后端原始 Markdown，未经过基础后处理。
- `output/result.json`：统一结构化摘要。
- `batches/`：PaddleOCR 分批结果；仅在适用时存在。
- `backend_result/`：后端原始响应或结果包。
- `metadata.json`：路由、后端、输出路径和处理配置。
- `postprocess_log.json`：基础标题识别和清理记录；仅在命中时存在。

## `output/result.json`

成功时：

```json
{
  "ok": true,
  "source": {
    "raw": "/path/to/file.pdf",
    "type": "local_file",
    "name": "file.pdf",
    "suffix": ".pdf",
    "page_count": 35,
    "sha256": "..."
  },
  "backend": {
    "name": "paddle",
    "mode": "api",
    "provider": "PaddleOCR Document Parsing API"
  },
  "route": {
    "preferred": "paddle",
    "candidates": ["paddle", "mineru"],
    "reason": "已检测到 PaddleOCR 与 MinerU 两套 API，按输入类型选择最优后端，并保留失败回退",
    "attempts": [
      {
        "backend": "paddle",
        "status": "failed",
        "category": "quota_or_rate_limit",
        "fallback": "next_backend"
      },
      {"backend": "mineru", "status": "success"}
    ]
  },
  "processing": {
    "mode": "single",
    "batch_count": 1
  },
  "text": "最终 Markdown",
  "raw_text": "后端原始 Markdown",
  "images": [],
  "batches": [],
  "postprocess": {
    "enabled": true,
    "log_count": 3,
    "legal_context": {
      "mode": "auto",
      "enabled": true,
      "detection": {
        "is_legal": true,
        "score": 12,
        "strong_signal_count": 2,
        "hits": [
          {"label": "人民法院", "count": 1, "weight": 3},
          {"label": "本院认为", "count": 1, "weight": 5}
        ],
        "filename_hits": [],
        "threshold": "score>=6 or strong_signal_count>=2"
      }
    }
  }
}
```

## `postprocess_log.json`

后处理命中时会保存日志。普通材料在 `auto` 模式下通常只会记录法律增强跳过信息和通用换行整理；法律术语优化的日志示例：

```json
[
  {
    "action": "legal_term_replace",
    "category": "spaced_legal_term",
    "pattern": "本(?:[ \\t]+|[ \\t]*\\n[ \\t]*)院...",
    "replacement": "本院认为",
    "count": "1",
    "description": "合并法律术语断字/断行：本院认为"
  },
  {
    "action": "line_merge",
    "category": "hard_wrap",
    "count": "2",
    "description": "合并明显属于同一中文段落的 OCR 硬换行"
  }
]
```

`result_raw.md` 始终保留后端原始文本，便于对照法律术语优化是否合适。

## 法律上下文检测

`LEGAL_OCR_LEGAL_TERMS=auto` 时，脚本会先对 OCR 原始文本和文件名做保守检测：

- 命中法院、检察院、判决书、裁定书、起诉状、案号、当事人标签、本院认为、判决如下等信号时，才启用法律术语优化。
- 非法律材料不会因为包含少量“法律”“权利”“义务”等泛化词而触发法律替换。
- 检测结果写入 `result.json` 的 `postprocess.legal_context`，并复制到 `metadata.json` 的 `legal_context`。
- `mode=always` 表示用户强制启用；`mode=never` 或 `--no-legal-terms` 表示跳过法律术语优化。

## 后端差异

### 路由与回退

- `auto` 先看已配置 API：只配置 PaddleOCR 时优先 PaddleOCR，只配置 MinerU Token 时统一 MinerU，两者都配置时按材料类型选择最优顺序。
- 失败尝试会记录在 `route.attempts` 中；`category` 可能是 `quota_or_rate_limit`、`auth`、`light_limit`、`unsupported`、`timeout`、`network` 或 `error`。
- 当前没有独立额度预检结果字段；额度/频率判断来自后端响应码和错误信息。

### PaddleOCR

- 支持本地 PDF、图片，以及 PDF/图片类远程文档 URL。
- 本地 PDF 支持 `--pages` 与自动分批。
- `backend_result/` 中保存每个批次的原始 JSON envelope。
- 支持两类协议：
  - `sync`：`/layout-parsing` JSON 接口，适合沿用 `paddle-ocr` 的旧配置。
  - `async`：`/api/v2/ocr/jobs` 异步任务接口，适合沿用 `pdf-processor` 的 PaddleOCR API 配置。
- 异步模式支持 `PP-OCRv5` 和 `PaddleOCR-VL-1.5`。Markdown 输出优先使用 `PaddleOCR-VL-1.5`，因为它返回版面块和 Markdown 文本。

### MinerU

- 支持本地 PDF、图片、Office 文档、远程文档 URL。
- 配置 Token 后支持网页 URL。
- 无 Token 时使用轻量接口，受 10 MB、20 页和频率限制影响。
- Token API 的结果包保存为 `backend_result/result.zip`。
