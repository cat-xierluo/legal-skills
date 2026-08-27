# `source-index.json` 与 `course-manifest.json` 产物契约

生成模式使用两份机器文件把“原文存在什么”和“课程如何处理”分开：

- `source-index.json`：由 `scripts/index_sources.py` 确定性生成，记录来源文件哈希和段落级 `BLK-xxxxx`；不要手写。
- `course-manifest.json`：记录课程、章节、素材、图片和正文证据，并绑定来源索引 SHA-256。
- 读者成品：使用真实课名的总览文件（如 `00 法律人 Agent 与 Skill 办案实务 - 总览.md`）与 manifest 声明的章节文件。
- 可选人工审计文件：`98 图片资产表.md`、`99 课程大纲.md` 或其他在 `audit_files` 中声明的文件。

JSON Schema 见 [source-index.schema.json](../config/source-index.schema.json) 和 [course-manifest.schema.json](../config/course-manifest.schema.json)。生成后运行：

```bash
bash scripts/verify.sh <课程目录> --source-root <单个来源文件或来源根目录>
```

验证器读取真实来源、来源索引、manifest 和最终 Markdown，不采信大纲中的“已完成”文字。

## 生成顺序

1. 用 `index_sources.py` 生成来源索引。
2. 逐个读取 `kind=content` 的块并建立素材；每个 content block 必须 include 或使用受控理由 skip。`kind=derived` 的平台附录只作定位线索，不建立素材。include 素材同时从摘要中预承诺 2—5 个 `coverage_terms`，每个词必须逐字存在于绑定的原始来源块。
3. include 与 skip 条目统一从 `MAT-001` 连续编号；`skip` 是 `disposition`，不是 `SKIP-*` 命名空间。账本落盘后先运行 `python3 scripts/preflight_ledger.py <课程目录>/course-manifest.json`。
4. 生成章节后，从真实正文回填每个 include 素材的 `reader_evidence.quotes`（1—3 段）；不回头改弱预承诺词。
5. 计算 `source-index.json` SHA-256，写入 manifest 的 `source_index.sha256`。
6. 运行验证器；修改正文、manifest 或来源索引后重新验收。

## 最小示例

```json
{
  "schema_version": "1.2",
  "generator_version": "2.9.4",
  "course": {"title": "示例课程"},
  "sources": [
    {"id": "SRC-001", "path": "转录稿-01.md"}
  ],
  "source_index": {
    "file": "source-index.json",
    "sha256": "<source-index.json 的 64 位小写 SHA-256>"
  },
  "overview": {
    "file": "00 示例课程 - 总览.md",
    "image_ids": ["IMG-001"]
  },
  "chapters": [
    {
      "id": "CH-01",
      "file": "01 第一章.md",
      "title": "第一章",
      "source_refs": ["SRC-001#L0020-L0058"],
      "material_ids": ["MAT-001"],
      "image_ids": ["IMG-002"]
    }
  ],
  "materials": [
    {
      "id": "MAT-001",
      "type": "操作",
      "summary": "从界面入口开始完成连续操作链，将结果写回文件，并保留错误的修正过程以供复现。",
      "source_refs": ["SRC-001#L0026-L0044"],
      "source_block_ids": ["BLK-00008", "BLK-00010"],
      "coverage_terms": ["界面入口", "结果写回", "修正过程"],
      "disposition": "include",
      "target_chapter_id": "CH-01",
      "reader_evidence": {
        "quotes": [
          "从界面入口开始，任务依次完成文件选择、规则确认、执行和结果写回。",
          "中途出现的错误保留修正过程，使读者可以按相同步骤复现。"
        ]
      }
    },
    {
      "id": "MAT-002",
      "type": "其他",
      "summary": "设备调试与投影切换",
      "source_refs": ["SRC-001#L0045-L0049"],
      "source_block_ids": ["BLK-00012"],
      "coverage_terms": [],
      "disposition": "skip",
      "target_chapter_id": null,
      "skip_code": "device",
      "skip_reason": "只包含设备调试，不构成课程知识。",
      "reader_evidence": null
    }
  ],
  "images": [
    {
      "id": "IMG-001",
      "source_ref": "SRC-001#L0012-L0012",
      "original_markdown": "![方法框架](https://example.com/framework.png)",
      "body_action": "insert",
      "target_document_id": "OVERVIEW"
    },
    {
      "id": "IMG-002",
      "source_ref": "SRC-001#L0030-L0030",
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

## 来源索引规则

- `index_sources.py` 只读取用户指定范围内的 `.md` / `.txt`，按路径稳定排序分配 `SRC-xxx`，跨来源连续分配 `BLK-xxxxx`。
- `content` 是模型必须逐项处理的覆盖基线；`derived` 表示转录平台附带的关键词、议程摘要、重点内容、Q&A 或 PPT 章节标题，只能帮助定位原始 content block，不得独立建立素材或事实；`heading`、`image`、`speaker`、`timestamp` 与 `separator` 保留结构信息，不要求建立素材。
- 索引器记录来源文件 SHA-256、块行号、字符数、块哈希和短预览，不复制整份原文。
- manifest 的 `sources` 必须与来源索引的 ID 和相对路径完全一致；`source_index.sha256` 必须绑定真实索引文件。
- 生成验收优先提供 `--source-root`：索引输入是单个文件时传同一文件，索引输入是目录时传同一目录。验证器会重新枚举完整输入范围并计算原始来源文件 SHA-256；未提供时只能证明索引内部契约，不能证明当前索引仍对应原始输入。

## 素材覆盖规则

- 每个 `kind=content` 的 `BLK-xxxxx` 至少出现在一个素材的 `source_block_ids` 中；未知块、非 content 块、完全未覆盖的块都验收失败。
- `MAT-xxx` 表示一个读者可复用的信息单元，而不是一个标题或整节的汇总。一个长块可以拆成多个素材；相邻同义块可以合并，但 include 素材最多绑定 6 个来源块，出现新的步骤、结果、数字、限制、工具、修正或问答转折时应拆分。同一块不得同时 include 与 skip。
- 全部素材共用 `MAT-xxx` 命名空间并从 `MAT-001` 连续分配，skip 项也不例外。禁止 `SKIP-001`、`OMIT-001` 等平行编号；去向只由 `disposition` 表达。
- `include` 素材必须指定目标章节，并出现在该章 `material_ids` 中。
- `skip` 素材使用受控 `skip_code`：`derived_duplicate`、`meeting`、`device`、`chatter`、`pure_repeat`、`no_course_value`，同时写具体 `skip_reason`。受控编码便于人工抽查跳过是否被滥用，它不自动证明理由正确。

## 正文证据规则

- include 素材在正文生成前，必须从素材摘要中预先选定 2—5 个 `coverage_terms`；数量至少为 `ceil(source_block_ids 数量 / 2)`（最低 2、最高 5）。每个词必须逐字存在于该素材绑定的原始来源块，至少一项是步骤、结果、数字、限制或专名，不得发明抽象概念，也不得全用 `AI` / `Agent` / `Skill` 类通用词。skip 素材填空数组。
- 每个 include 素材必须提供 `reader_evidence.quotes`，包含 1—3 段真实存在于目标章节的连续摘录。
- 1—3 段摘录合并后的长度随来源块数量增加：案例、操作、踩坑、取舍、疑问类至少 `max(80, min(240, 35 × 来源块数))` 字；观点、金句和其他类至少 `max(30, min(180, 25 × 来源块数))` 字。长度只是防止一句带过的最低门槛，不是充分语义证明。
- 预承诺的所有 `coverage_terms` 都必须出现在 1—3 段证据的合并文本内，不要求挤进同一段。正文完成后不得因为某个事实没写进去，而删掉、改成更泛的覆盖词，或专门拼一段审计文字。
- 不同素材不得复用完全相同的一组证据摘录。一个段落确实承载多个相关素材时，为每项选取不同片段组合。
- 证据只写在 manifest，读者正文不显示 `MAT/BLK/SRC` 审计编号。

## 图片与文件规则

- `source-index.json` 中每个 `kind=image` 块都必须在 manifest 中逐项登记；按来源索引顺序跨全部来源连续编号 `IMG-xxx`，`source_ref` 精确对应，`original_markdown` 原样保留。不能只登记正文选中的图片。
- `body_action=insert` 时，ID 必须在目标文档 `image_ids` 中精确出现一次；`asset_only` 或 `skip` 时目标为 `null` 并填写理由。
- 目标文档 `image_ids` 按最终正文实际顺序填写；验证器比较图片精确集合、目标和顺序。
- 每份读者文档的正文图数不得超过 `max(3, ceil(可见文字数 / 500))`，整套课程也按相同密度计算总上限。连续截图优先保留起点、关键转折和结果代表图，其余转为 `asset_only`。
- 来源图片少于 12 张时不设正文图片下限，允许全部为低价值图片的合法近似情形。来源图片达到 12 张时，整套课程至少插入 `min(读者文档数, ceil(源图片数 / 20))` 张代表图，防止弱模型把整套 PPT 全部降级为附件；最低数量不证明图片语义选择正确，仍需人工复核。
- manifest 内路径使用课程目录下的可移植相对路径，不允许绝对路径、反斜杠或 `..`。
- manifest 声明的总览、章节和审计文件必须存在且非空；存在未声明的编号章节时验收失败。读者文件名使用真实课名/主题，禁止模板方括号、`TBD`、`TODO` 和 `: * ? " < > |`。
- 默认最多 8 个章节。只有用户明确要求更多章节时才运行 `verify.sh ... --max-chapters <明确上限>`；不得为了照搬原稿 H2、会务、安装准备或讲者介绍而提高上限。

## 验收边界

验证器客观检查：来源/索引哈希、content block 去向、coverage term 是否真实存在于绑定来源块、来源外缩写释义、include 素材颗粒度、1—3 段正文证据、章节可见文字相对纳入来源的最低深度（单章 40%、全局 55%）、默认八章上限、占位符、manifest 结构、文件完整性、源图片全登记、图片契约/最低筛选数量/密度、素材双向映射、明显来源框架和审计分离。

人工检查：证据摘录是否真的承载素材语义，跳过理由是否合理，数字/动作/建议是否忠实，跨章重复与引用是否自然，图片是否帮助理解。脚本 PASS 不能替代这些语义判断。
