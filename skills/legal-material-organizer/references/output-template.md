# 标准输出模板

## 存储边界

将三类产物分开：

1. **源材料目录**：只保存律师阅读的 Markdown 和用户确认后的整理结果。
2. **运行时元数据归档**：只保存 JSON、清单副本和运行参数，不复制真实材料或 OCR/ASR 全文。
3. **真实材料工作目录**：只保存压缩包解压结果等可重建工作副本，不进入 Skill 包。

Skill 包内 `archive/` 只保留 `.gitignore` 与 `.gitkeep`。

```text
<源材料父目录>/
├── <源材料>/
│   ├── 材料清单.md
│   ├── <源目录名称> - 材料说明.md
│   ├── <源目录名称> - 材料综合分析.md
│   └── <分类目录>/
│       ├── <分类目录名称> - 材料说明.md
│       └── A001 <描述>.<扩展名>
└── .legal-material-organizer/<源材料名称>/
    ├── archive/<运行目录>/
    │   ├── materials_manifest.json
    │   ├── filing_plan.json
    │   ├── renaming_map.json
    │   ├── run_meta.json
    │   └── 材料清单.md
    └── work/extracted_containers/
```

运行时 archive 中的文件名、路径、指纹和摘要仍属于敏感元数据，不要公开发布。

## `材料清单.md`

```markdown
# 材料清单

## 基本信息

- 扫描时间：<YYYY-MM-DD HH:MM>
- 输入来源：`<源路径>`
- 元数据归档：`<本次运行目录>`
- 真实材料工作目录：`<工作目录>`
- 材料总数：<N>
- 缺失材料：<N>
- 是否自动拆包：是/否

## 类型统计

- PDF：<N>
- 图片/截图：<N>
- 其他：<N>

## 清单

| 展示编号 | 所属材料组 | 原始名称 | 展示路径 | 整理前路径 | 父级材料 | 类型 | 可读性 | 待处理动作 | 备注 |
|----------|------------|----------|----------|------------|----------|------|--------|------------|------|
| A001 | 文档材料组 | <原始文件名> | <当前路径> | <首次路径> | - | PDF | unknown | need_ocr_or_visual | 待处理 |
```

Markdown 只展示 `display_code`，不展示后台 `material_id`。

## `{文件夹名称} - 材料说明.md`

```markdown
# <文件夹名称>

> 本文件由 AI 自动生成（legal-material-organizer Skill v0.16.1）。内容用于快速了解和整理材料，请以原始文件为准；AI 归纳不构成法律意见。

## A001 <原始文件名>

### 可见内容或提取结果

<客观记录；无法确认时写“待识别/待人工确认”>

### 注解

<仅说明材料类型、整理用途和可能关联；不要写法律结论>

### 待确认

- <主体/日期/金额/来源等缺口；没有则写“无”>
```

不要把 OCR 结果和 AI 归纳混在同一段；视觉识别内容注明“视觉识别”。

## `{源目录名称} - 材料综合分析.md`

使用 [comprehensive-analysis-template.md](comprehensive-analysis-template.md)。文件名为兼容既有项目保留“综合分析”，正文只做材料结构、关联线索和完整性整理，不形成案件结论或证明目的。

## 元数据文件

### `materials_manifest.json`

至少包含：

```json
{
  "generated_at": "<ISO-8601>",
  "skill": "legal-material-organizer",
  "skill_version": "0.16.1",
  "source": "<源路径>",
  "markdown_output_dir": "<Markdown 输出目录>",
  "archive_dir": "<元数据归档目录>",
  "work_dir": "<真实材料工作目录>",
  "material_count": 1,
  "materials": [
    {
      "material_id": "M-000001",
      "display_code": "A001",
      "original_name": "<示例文件>.pdf",
      "original_display_path": "<首次相对路径>",
      "display_path": "<当前相对路径>",
      "organized_path": null,
      "source_chain": [],
      "readability_status": "unknown",
      "processing_need": "need_ocr_or_visual",
      "needs_human_review": false,
      "review_reasons": []
    }
  ],
  "material_sets": [],
  "variants": [],
  "processing_runs": [],
  "follow_up_candidates": []
}
```

完整字段与受控值见 [field-dictionary.md](field-dictionary.md)。

### `filing_plan.json`

记录拟整理路径、展示编号、参照度和命名依据。它是计划，不代表已执行。

### `renaming_map.json`

记录 `material_id → display_code → source_path/current_path`。只有核对真实文件系统后才能把 `applied` 视为已执行。

### `run_meta.json`

记录版本、输入、元数据归档、真实材料工作目录和命令参数；不要写入凭证、Token 或材料正文。

## 完成检查

- 文件总数、活动记录数和缺失记录能够解释。
- 压缩包内部文件有父子来源链。
- 元数据归档中没有图片、音频、视频、PDF、办公文档或解压目录。
- 工作目录与元数据归档不重叠。
- 移动/重命名后，真实路径与三份元数据文件一致。
- 原文、OCR/ASR、视觉识别、AI 注解和人工确认状态分层清楚。
