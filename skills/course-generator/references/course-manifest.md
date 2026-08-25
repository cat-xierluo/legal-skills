# `course-manifest.json` 产物契约

生成模式使用 `course-manifest.json` 作为课程事实的机器可读单点真相。读者成品与审计材料分离：

- 读者成品：`00 [课程名称] - 总览.md` 与 manifest 声明的章节文件。
- 强制审计文件：`course-manifest.json`。
- 可选人工审计文件：`98 图片资产表.md`、`99 课程大纲.md` 或其他在 `audit_files` 中声明的文件。

JSON Schema 见 [course-manifest.schema.json](../config/course-manifest.schema.json)。生成后运行 `bash scripts/verify.sh <课程目录>`，验证器直接读取 manifest 和真实 Markdown，不采信大纲中的“已完成”文字。

## 最小示例

```json
{
  "schema_version": "1.0",
  "generator_version": "2.8.0",
  "course": {"title": "示例课程"},
  "sources": [
    {"id": "SRC-001", "path": "转录稿-01.md"}
  ],
  "overview": {
    "file": "00 示例课程 - 总览.md",
    "image_ids": ["IMG-001"]
  },
  "chapters": [
    {
      "id": "CH-01",
      "file": "01 第一章.md",
      "title": "第一章",
      "source_refs": ["SRC-001#00:00-10:00"],
      "material_ids": ["MAT-001"],
      "image_ids": ["IMG-002"]
    }
  ],
  "materials": [
    {
      "id": "MAT-001",
      "type": "操作",
      "summary": "完成一次可复用的操作链",
      "source_refs": ["SRC-001#03:20-06:10"],
      "disposition": "include",
      "target_chapter_id": "CH-01"
    }
  ],
  "images": [
    {
      "id": "IMG-001",
      "source_ref": "SRC-001#01:20",
      "original_markdown": "![方法框架](https://example.com/framework.png)",
      "body_action": "insert",
      "target_document_id": "OVERVIEW"
    },
    {
      "id": "IMG-002",
      "source_ref": "SRC-001#04:30",
      "original_markdown": "![操作界面](https://example.com/step.png)",
      "body_action": "insert",
      "target_document_id": "CH-01"
    }
  ],
  "audit_files": {
    "outline": "99 课程大纲.md",
    "image_assets": "98 图片资产表.md"
  }
}
```

## 字段规则

### 来源与定位

- `course.title` 必填；已确认培训实际日期或主办方时，可填写 `training_date`（`YYYY-MM-DD`）与 `organizer`，不要用生成日期冒充培训日期。
- `sources[].id` 使用跨文件连续编号 `SRC-001`、`SRC-002`……。
- `sources[].path` 使用相对输入根目录的路径或稳定文件名，不写仅在某台机器成立的绝对路径。
- `source_refs` / `source_ref` 以来源 ID 开头；`#` 后可写时间区间、段落号或标题锚点，如 `SRC-002#P0042-P0058`。
- 长材料先建立稳定段落/时间索引，再生成材料项；不要用模型临时记忆代替 source ref。

### 素材

- 每个实质素材建立 `MAT-xxx`；类型使用【案例】【操作】【观点】【金句】【踩坑】【取舍】【疑问】【其他】之一。
- `include` 素材必须指定 `target_chapter_id`，并出现在对应章节的 `material_ids` 中。
- `skip` 素材的 `target_chapter_id` 为 `null`，并填写 `skip_reason`。跳过只用于会务、设备调试、寒暄、纯重复或无课程价值的确认性插话。
- manifest 证明“素材已被分配并可回查”，不自动证明正文已经语义充分展开；后者保留人工复核。

### 图片

- 每张原始 Markdown 图片按所有来源的读取顺序连续编号 `IMG-xxx`。
- `original_markdown` 原样保存单行图片引用，不改 alt、URL、路径或括号。
- `body_action=insert` 时，`target_document_id` 只能是 `OVERVIEW` 或某个 `CH-xx`，并且同一 ID 必须出现在目标文档的 `image_ids` 中。
- `body_action=asset_only` 或 `skip` 时，`target_document_id` 为 `null`，填写 `reason`，读者成品中不得出现该图片。
- `overview.image_ids` 和 `chapters[].image_ids` 按目标文件中的实际出现顺序填写。主题重组允许跨小节改变全局 IMG 数字顺序，但 manifest 声明顺序必须与最终正文完全一致；不再同时要求“全章严格递增”。

### 文件与失败语义

- manifest 内文件路径使用课程目录下的相对路径，不允许绝对路径、反斜杠或 `..` 路径穿越。
- manifest 声明的总览、章节和可选审计文件必须存在且非空。
- `00` 与章节编号 Markdown 中出现的图片必须全部由 manifest 声明；多图、少图、重复、错位或顺序不符均验收失败。
- 目录中存在未由 manifest 声明的编号章节时验收失败，避免生成了文件却漏进交付契约。

## 验收边界

验证器客观检查：manifest 结构、文件完整性、图片精确集合/目标/顺序、素材双向映射、明显来源框架与转录口吻、读者成品和审计元数据分离。

人工检查：素材是否充分展开、数字/动作/建议是否忠实、跨章重复与引用是否合理、图片是否真的有助于理解。人工检查未完成时，不得把脚本 PASS 扩大表述为课程语义质量已通过。
