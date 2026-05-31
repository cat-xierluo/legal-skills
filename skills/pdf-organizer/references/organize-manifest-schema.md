# organize_manifest.json 说明

`organize_manifest.json` 是本技能的执行清单。AI 负责根据 OCR 内容填写清单，脚本只按清单执行拆分、合并、复制、旋转、倾斜校正和安全命名。

可先用 `--inspect` 生成页面检查索引，再用 `--suggest-manifest` 生成草稿。草稿中的 `suggested_filename`、`parties`、`confidence` 和 `needs_review` 必须由 AI/人工结合页面证据复核后再执行。

## 顶层字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `source_pdf` | 否 | 整份 OCR 后 PDF。segment 使用 `pages` 时必填，可被命令行 `--source` 覆盖 |
| `output_dir` | 否 | 输出目录。缺省为 manifest 同级的 `output/`，可被命令行 `--output-dir` 覆盖 |
| `archive_root` | 否 | 归档根目录。缺省为本 Skill 的 `archive/`，可被命令行 `--archive-root` 覆盖 |
| `text_check` | 否 | 文字层检测模式：`strict`、`warn`、`off`。缺省为 `strict`，检测不到文字层时停止执行 |
| `require_text_layer` | 否 | 兼容字段。设为 `false` 等同于 `text_check: "off"` |
| `rotate` | 否 | 顶层旋转角度，作用于所有 segment。可选 `90`、`180`、`270` |
| `deskew` | 否 | 顶层倾斜校正开关，作用于所有 segment。需要系统安装 `ocrmypdf` |
| `segments` | 是 | 待输出的文书数组，按自然顺序排列 |
| `notes` | 否 | 本次整理的整体说明 |

输出目录只保存最终 PDF。`organize_manifest.input.json`、`organize_manifest.resolved.json`、`organize_report.md`、`handoff.json` 和 `run_meta.json` 统一写入 archive 运行目录。

按内容拆分、合并和命名依赖 PDF 已有可检索文字层。默认 `text_check: "strict"` 会抽样检测来源 PDF；如果检测不到文字层，应先用 PDF Processor 生成双层 PDF。只有纯旋转、复制等不依赖内容判断的任务，才建议关闭文字层检测。

## segment 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 建议 | 稳定编号，如 `D001` |
| `pages` | 条件必填 | 页码范围，如 `1-2`、`5`、`7-8,10`。从 `source_pdf` 拆分时使用 |
| `input_file` | 条件必填 | 单个 PDF 路径。对现成 PDF 复制、重命名或旋转时使用 |
| `source_items` | 条件必填 | 多个来源 PDF 或页码片段。用于把碎片合并成一个输出 PDF |
| `input_files` | 否 | `source_items` 的简写，仅支持文件路径数组 |
| `suggested_filename` | 建议 | 目标文件名。也可用 `filename` |
| `rotate` | 否 | 当前 segment 的旋转角度，覆盖顶层 `rotate` |
| `deskew` | 否 | 当前 segment 是否做倾斜校正，覆盖顶层 `deskew` |
| `title` | 建议 | 文书标题或材料名称 |
| `document_type` | 建议 | 合同、授权委托书、函、起诉状、表单、票据等 |
| `date` | 否 | 明确识别到的日期；无法确认写 `未提及` |
| `parties` | 否 | 与命名有关的主体简称数组 |
| `document_no` | 否 | 案号、函号、合同编号等 |
| `confidence` | 建议 | `high`、`medium`、`low` |
| `needs_review` | 建议 | 是否需要人工复核 |
| `evidence` | 建议 | 支持拆分、合并或命名判断的短证据 |
| `notes` | 否 | 当前 segment 的补充说明 |

`pages`、`input_file`、`source_items` / `input_files` 至少填写一个。优先级为：`source_items` / `input_files` → `input_file` → `pages`。

## source_items

`source_items` 可混合整份 PDF 和指定页码：

```json
[
  {"file": "/path/to/起诉状 第1-2页.pdf"},
  {"file": "/path/to/起诉状 第3-4页.pdf", "pages": "1-2"}
]
```

## 完整示例

```json
{
  "source_pdf": "/Users/example/Desktop/scan_ocr.pdf",
  "output_dir": "/Users/example/Desktop/organized",
  "notes": "OCR 后按文书内容整理",
  "segments": [
    {
      "id": "D001",
      "pages": "1-2",
      "suggested_filename": "专项法律服务合同 委托方简称.pdf",
      "title": "专项法律服务合同",
      "document_type": "合同",
      "parties": ["委托方简称"],
      "confidence": "high",
      "needs_review": false,
      "evidence": "第 1 页顶部标题显示为专项法律服务合同"
    },
    {
      "id": "D002",
      "source_items": [
        {"file": "/Users/example/Desktop/起诉状 第1-2页.pdf"},
        {"file": "/Users/example/Desktop/起诉状 第3-4页.pdf"}
      ],
      "suggested_filename": "民事起诉状 张三诉某公司 普通版.pdf",
      "title": "民事起诉状",
      "document_type": "民事起诉状",
      "confidence": "high",
      "needs_review": false,
      "evidence": "两份 PDF 标题一致且页码连续，应合并为同一份起诉状。"
    }
  ]
}
```

## 重命名示例

不需要拆分或合并，只对独立 PDF 做内容识别后规范命名：

```json
{
  "output_dir": "/Users/example/Desktop/organized",
  "notes": "独立 PDF 重命名",
  "segments": [
    {
      "id": "D001",
      "input_file": "/Users/example/Desktop/scan_20260531_001.pdf",
      "suggested_filename": "民事起诉状 张三诉某公司 普通版.pdf",
      "title": "民事起诉状",
      "document_type": "民事起诉状",
      "confidence": "high",
      "needs_review": false,
      "evidence": "首页标题为民事起诉状，正文提及张三与某公司纠纷。"
    },
    {
      "id": "D002",
      "input_file": "/Users/example/Desktop/scan_20260531_002.pdf",
      "suggested_filename": "授权委托书 张三.pdf",
      "title": "授权委托书",
      "document_type": "授权委托书",
      "confidence": "high",
      "needs_review": false,
      "evidence": "首页标题为授权委托书，委托人张三。"
    }
  ]
}
```

每条 segment 只需要 `input_file` + `suggested_filename`，脚本会把文件复制到输出目录并使用新文件名。如需同时旋转或倾斜校正，在同一条 segment 中加上 `rotate` 或 `deskew` 即可。

## 复核规则

- `confidence: low` 或 `needs_review: true` 的 segment 不应被描述为已最终确认。
- `--suggest-manifest` 自动生成的 segment 默认需要复核；不要把 `待确认` 文件名直接作为最终交付名。
- 如果日期、主体、案号来自 OCR 模糊文本，优先省略，不要把不确定信息写进文件名。
- `evidence` 只保留短句，不保存完整客户材料全文。

## handoff.json

`handoff.json` 面向下游 Skill，不替代 resolved manifest。它保留下游最常用字段：

| 字段 | 说明 |
|------|------|
| `schema` | 固定为 `pdf-organizer-handoff/v1` |
| `source_pdf` | 原始来源 PDF |
| `output_dir` | 最终 PDF 输出目录 |
| `review_required` | 是否存在低置信度或需复核文档 |
| `documents` | 下游可消费的文档数组 |

`documents[]` 主要字段：

| 字段 | 说明 |
|------|------|
| `file` / `filename` | 最终 PDF 路径和文件名 |
| `document_type` / `title` | 文书类型和标题 |
| `source_pages` | 来源页码或来源片段 |
| `parties` / `date` / `document_no` | 主体、日期、案号/函号等命名要素 |
| `confidence` / `needs_review` | 置信度和复核状态 |
| `suggested_downstream` | 按文书类别的路由标签，如 `合同审查`、`诉讼分析`、`材料整理`、`复核`；不绑定具体 Skill 名称 |
