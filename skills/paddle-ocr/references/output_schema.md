# 输出结构说明

本技能有两层输出：

1. **底层接口层**：`scripts/layout_caller.py` 输出稳定 JSON envelope
2. **高层法律工作流**：`scripts/convert.py` 生成 Markdown，并把结构化结果写入 archive

## 一、`layout_caller.py` 输出结构

`layout_caller.py` 用于直接调用 PaddleOCR 接口，返回统一包装：

```json
{
  "ok": true,
  "text": "从所有页面拼接出的 Markdown 文本",
  "result": { "errorCode": 0, "result": { "...": "原始接口结果" } },
  "error": null
}
```

失败时：

```json
{
  "ok": false,
  "text": "",
  "result": null,
  "error": {
    "code": "CONFIG_ERROR | INPUT_ERROR | API_ERROR",
    "message": "可直接展示给用户的错误信息"
  }
}
```

重点字段：

- `text`：由 `result.result.layoutParsingResults[*].markdown.text` 拼接而成
- `result.result.layoutParsingResults[*].markdown.images`：页面内图片资源
- `result.result.layoutParsingResults[*].prunedResult`：坐标、分类、置信度等结构化版面信息

## 二、`convert.py` 的 archive 结构

`convert.py` 是高层入口，默认生成 Markdown 并写入 `archive/`。

归档目录示例：

```text
archive/
└── 20260405_153000_某案卷宗/
    ├── input/
    │   └── 某案卷宗.pdf
    ├── output/
    │   ├── result.md
    │   ├── result.json
    │   └── images/
    ├── batches/
    │   ├── batch_001_1-40.json
    │   └── batch_002_41-67.json
    └── metadata.json
```

### `output/result.json`

这是高层工作流的汇总文件，包含：

- 输入文件基本信息
- 处理模式（单次 / 自动分批）
- 提取出的全文 Markdown
- 输出图片列表
- 各批次摘要

示例：

```json
{
  "ok": true,
  "source": {
    "path": "/path/to/file.pdf",
    "name": "file.pdf",
    "sha256": "..."
  },
  "processing": {
    "mode": "batched",
    "batch_count": 2,
    "total_pages": 67,
    "processed_pages": 67,
    "selected_pages": "1-67"
  },
  "text": "最终合并后的 Markdown",
  "images": [],
  "batches": [
    {
      "index": 1,
      "label": "1-40",
      "text_length": 12345,
      "image_count": 2
    }
  ]
}
```

### `batches/*.json`

每个批次对应一个底层 envelope，便于排查：

- 哪一批 OCR 异常
- 哪一批版面错乱
- 某页的 `prunedResult` 是否需要单独读取

### `metadata.json`

记录：

- 处理时间
- provider 名称
- 关键配置
- Markdown 输出路径
- 图片目录路径

## 三、建议读取顺序

如果只是要最终文本：

1. 读取 `output/result.md`

如果需要排查 OCR 质量：

1. 读取 `output/result.json`
2. 再按需读取 `batches/*.json`

如果需要提取表格、坐标、阅读顺序：

1. 直接运行 `scripts/layout_caller.py`
2. 读取 `result.result.layoutParsingResults[*].prunedResult`
