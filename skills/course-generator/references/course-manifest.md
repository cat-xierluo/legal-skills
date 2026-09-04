# `source-index.json` 与 `course-manifest.json` 产物契约

生成模式使用两份机器文件把“原文存在什么”和“课程如何处理”分开：

- `source-index.json`：由 `scripts/index_sources.py` 确定性生成，记录来源文件哈希、段落级 `BLK-xxxxx`、来源权威声明和结构化修正规则；不要手写。
- `course-manifest.json`：记录课程、权威处理确认、逐条修正路由、章节、素材、图片和正文证据，并绑定来源索引 SHA-256。
- 读者成品：使用真实课名的总览文件（如 `00 法律人 Agent 与 Skill 办案实务 - 总览.md`）与 manifest 声明的章节文件。
- 可选人工审计文件：`98 图片资产表.md`、`99 课程大纲.md` 或其他在 `audit_files` 中声明的文件。

JSON Schema 见 [source-index.schema.json](../config/source-index.schema.json) 和 [course-manifest.schema.json](../config/course-manifest.schema.json)。生成后运行：

```bash
bash scripts/verify.sh <课程目录> --source-root <单个来源文件或来源根目录>
```

验证器读取真实来源、来源索引、manifest 和最终 Markdown，不采信大纲中的“已完成”文字。

## 生成顺序

1. 用 `index_sources.py --authority-mode current` 生成来源索引，再用 `ledger_tool.py init` 绑定真实 `--source-root` 并建立 schema 1.8 的 manifest 脚手架；来源、权威声明、结构化修正、候选旧口径块、图片、编号和哈希不由模型手写。只有用户明确要求历史口径时才使用 `historical`。
2. 先读取 `source-index.authority`；`ledger_tool.py init/status` 会把候选 ID、source ref 和短预览汇总为 `authority_candidate_review_queue`。current 模式按 `corrections` 逐条选择目标章与目标 H2，并按 queue 原顺序把每个候选判为 `superseded` 或 `retained_current`；每项同时提交逐字来自该候选预览、至少 6 字的 `evidence_quote` 与专属理由。不得复制同一理由批量判断，也不得把 12 项以上的整张高召回矩阵一律删除。historical 模式准备读者可见的非现行声明。短预览不足以判断时回读原文，候选逐项判断不能替代候选外的同义旧结论检索。把逐项确认、逐条修正路由、候选审查矩阵、被替代来源块与最终章节、二级标题顺序写成 `chapter-plan.json`，用 `ledger_tool.py plan` 一次冻结。模型不复制或改写 `revised_text`；工具负责把它写入 manifest。每个二级标题都是证据边界，不得先生成空模板再期待正文自然补齐。
3. 每次读取 20—40 个尚未处理的 `kind=content` 块，输出一个批次 JSON；用 `ledger_tool.py merge ... --source-root ...` 校验 coverage term、目标章/节、修订替代块、include/skip 冲突及素材总数预算并自动连续编号。`authority`、`control`、`derived` 都不建立普通素材；plan 确认的旧口径块只使用 `authority_superseded` 跳过，控制来源只修订历史表述，不自动扩成新课程主题。
4. 用 `ledger_tool.py status --next-batch-size 30` 获取下一批精确 ID；只处理 `next_batch_content_block_ids`，不自行重算剩余块。全部覆盖后运行 ledger finalizer，再运行带 `--source-root` 的 `preflight_ledger.py`。include 素材的每个 coverage term 必须逐字存在于绑定原文、不能全是通用词，也不能是口语指代、语气词或截断片段；不要求为了审计把词硬塞进摘要。每个计划二级标题至少有一项 include 素材。
5. 从图片相邻内容中确定代表图，提交短 `image-selection.json`，由 `ledger_tool.py select-images` 同步 manifest；再用 `scaffold` 创建精确 H1/H2 并原样注入路由到各节的修订句。不要让模型翻改整份图片数组、自行重写标题或改写修订句。
6. 按冻结的二级标题顺序逐章填写正文；每项素材只写入自己的 `target_section_heading`。每完成一章立即运行 `check-chapter`，修到单章 PASS 后才进入下一章。中文正文统一使用全角标点并保持引号闭合；明显 ASR 异常不照抄为事实。单章超过 `max(1400 字, 本章纳入来源字符数 × 2.5)` 时，应删除来源外扩写、去除重复或合并结构性薄章，不能靠近义重复补字数。
7. 完成后运行 final 阶段收口，只从该目标小节内回填 `reader_evidence.quotes`（1—3 段）并按最终 Markdown 复核图片映射。自动收口报告 `unresolved` 时在对应小节补真实正文，不写“正文证据补丁”“原文痕迹”或覆盖词清单，不跨节借证据；再次运行自动收口与验证器。修改正文、manifest 或来源索引后重新验收。批次/计划/图片选择 JSON 或 YAML、辅助脚本和缓存全部放在课程目录之外。

对应命令顺序：

```bash
python3 scripts/ledger_tool.py init \
  --source-index <课程目录>/source-index.json \
  --source-root <来源文件或目录> \
  --manifest <课程目录>/course-manifest.json \
  --title "<真实课名>" \
  --overview-file "00 <真实课名> - 总览.md"
python3 scripts/ledger_tool.py plan \
  <课程目录>/course-manifest.json <临时目录>/chapter-plan.json
python3 scripts/ledger_tool.py merge \
  <课程目录>/course-manifest.json <临时目录>/batch-001.json \
  --source-root <来源文件或目录>
python3 scripts/ledger_tool.py status \
  <课程目录>/course-manifest.json --next-batch-size 30
python3 scripts/finalize_manifest.py \
  <课程目录>/course-manifest.json --phase ledger --write
python3 scripts/preflight_ledger.py \
  <课程目录>/course-manifest.json --source-root <来源文件或目录>
python3 scripts/ledger_tool.py select-images \
  <课程目录>/course-manifest.json <临时目录>/image-selection.json
python3 scripts/ledger_tool.py scaffold \
  <课程目录>/course-manifest.json
python3 scripts/ledger_tool.py check-chapter \
  <课程目录>/course-manifest.json --document CH-01
```

`plan` 默认最多 8 章；不得为了通过门禁或照搬来源结构自行放宽。只有用户明确要求超过 8 章时才读取 [advanced-overrides.md](advanced-overrides.md)。完全相同的素材批次被重试时，`merge` 幂等跳过已有记录，不重复分配 MAT ID。

## 弱模型输入格式

章节计划包含权威确认、逐条修正路由和全局结构，不包含素材编号。current 模式必须精确回填工具提供的控制来源，并把每个 `COR-xxx` 路由到一个已经声明的 H2；没有权威声明或结构化修正时对应字段填空数组：

```json
{
  "course_title": "示例课程",
  "overview_file": "00 示例课程 - 总览.md",
  "authority_acknowledgements": [
    {
      "id": "AUTH-001",
      "action": "apply_control",
      "controlling_source_ids": ["SRC-002"]
    }
  ],
  "authority_correction_routes": [
    {
      "id": "COR-001",
      "target_chapter_id": "CH-01",
      "target_section_heading": "从入口到结果写回",
      "supersession_status": "blocks_identified",
      "superseded_source_block_ids": ["BLK-00023", "BLK-00041"],
      "supersession_note": "两个来源块都把旧称当成当前方法名称，应由 COR-001 修订句替代。",
      "candidate_block_reviews": [
        {
          "source_block_id": "BLK-00023",
          "decision": "superseded",
          "evidence_quote": "旧称直接写成当前采用的方法名称",
          "reason": "该候选块把旧称直接写成当前采用的方法名称。"
        },
        {
          "source_block_id": "BLK-00041",
          "decision": "superseded",
          "evidence_quote": "再次用同义句支持已经被修订的旧口径",
          "reason": "该候选块再次用同义句支持已经被修订的旧口径。"
        }
      ]
    }
  ],
  "chapters": [
    {
      "file": "01 可复现的操作链.md",
      "title": "可复现的操作链",
      "section_headings": ["从入口到结果写回", "失败后的修正"]
    }
  ]
}
```

若普通来源没有陈述或支持某条旧口径，该路由使用 `supersession_status: "no_matching_source_block"`、空 `superseded_source_block_ids`，并在 `supersession_note` 写明检查结果；但每个候选仍要在 `candidate_block_reviews` 中逐项标为 `retained_current`，摘录对应预览证据，并说明其为何不承载旧结论。候选列表为空时 review 数组才为空，且不等于可以跳过候选外的语义检索。`candidate_block_reviews` 的 ID、数量与顺序必须和索引候选完全相同；`evidence_quote` 必须逐字来自对应候选预览且至少 6 字；多个候选不得复制同一理由；判为 `superseded` 的候选必须进入隔离列表，判为 `retained_current` 的候选不得进入。historical 模式把对应项改为 `action: "historical_disclaimer"`，并提供至少 12 字的 `reader_notice`；该句必须原样出现在总览，`authority_correction_routes` 必须为空数组。Agent 不得自行把 current 改为 historical。

每个批次只提交素材判断。include 必须指定计划中存在的章和节；skip 不得带目标章/节：

```json
{
  "materials": [
    {
      "type": "操作",
      "summary": "从界面入口完成连续步骤，并把结果写回文件。",
      "source_block_ids": ["BLK-00008", "BLK-00010"],
      "coverage_terms": ["界面入口"],
      "disposition": "include",
      "target_chapter_id": "CH-01",
      "target_section_heading": "从入口到结果写回"
    },
    {
      "type": "其他",
      "summary": "设备调试与投影切换。",
      "source_block_ids": ["BLK-00012"],
      "disposition": "skip",
      "skip_code": "device",
      "skip_reason": "只包含设备调试，不构成课程知识。"
    }
  ]
}
```

图片选择只提交图片 ID、目标文档和选择理由；未列出的图片由工具保留为 `asset_only`。数组顺序不承担正文顺序，工具按来源顺序确定性同步：

```json
{
  "selections": [
    {
      "id": "IMG-008",
      "target_document_id": "CH-01",
      "reason": "展示本章方法框架的代表页。"
    },
    {
      "id": "IMG-021",
      "target_document_id": "CH-02",
      "reason": "展示关键操作结果界面。"
    }
  ]
}
```

## 最小示例

```json
{
  "schema_version": "1.8",
  "generator_version": "2.9.15",
  "course": {"title": "示例课程"},
  "sources": [
    {"id": "SRC-001", "path": "转录稿-01.md"},
    {"id": "SRC-002", "path": "示例课程勘误.md"}
  ],
  "source_index": {
    "file": "source-index.json",
    "sha256": "<source-index.json 的 64 位小写 SHA-256>"
  },
  "source_authority": {
    "mode": "current",
    "notices": [
      {
        "id": "AUTH-001",
        "source_block_id": "BLK-00001",
        "source_ref": "SRC-001#L0001-L0004",
        "controlling_titles": ["示例课程勘误"],
        "controlling_source_ids": ["SRC-002"],
        "section_hint": "第 1 节勘误与收束"
      }
    ],
    "corrections": [
      {
        "id": "COR-001",
        "authority_id": "AUTH-001",
        "source_id": "SRC-002",
        "source_ref": "SRC-002#L0097-L0097",
        "original_text": "`spec coding`",
        "revised_text": "使用更清楚的轻量 Spec-Driven Development。",
        "deprecated_terms": ["spec coding"],
        "superseded_candidate_block_ids": ["BLK-00023", "BLK-00041"]
      }
    ],
    "acknowledgements": [
      {
        "id": "AUTH-001",
        "action": "apply_control",
        "controlling_source_ids": ["SRC-002"],
        "reader_notice": null
      }
    ],
    "correction_routes": [
      {
        "id": "COR-001",
        "target_chapter_id": "CH-01",
        "target_section_heading": "从入口到结果写回",
        "supersession_status": "blocks_identified",
        "superseded_source_block_ids": ["BLK-00023", "BLK-00041"],
        "supersession_note": "两个来源块都把旧称当成当前方法名称，应由 COR-001 修订句替代。",
        "candidate_block_reviews": [
          {"source_block_id": "BLK-00023", "decision": "superseded", "evidence_quote": "旧称直接写成当前采用的方法名称", "reason": "该候选块把旧称直接写成当前采用的方法名称。"},
          {"source_block_id": "BLK-00041", "decision": "superseded", "evidence_quote": "再次用同义句支持已经被修订的旧口径", "reason": "该候选块再次用同义句支持已经被修订的旧口径。"}
        ]
      }
    ]
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
      "section_headings": ["从入口到结果写回"],
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
      "coverage_terms": ["界面入口"],
      "disposition": "include",
      "target_chapter_id": "CH-01",
      "target_section_heading": "从入口到结果写回",
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
      "target_section_heading": null,
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
      "target_document_id": "OVERVIEW",
      "reason": "展示课程整体方法框架。"
    },
    {
      "id": "IMG-002",
      "source_ref": "SRC-001#L0030-L0030",
      "original_markdown": "![操作界面](https://example.com/step.png)",
      "body_action": "insert",
      "target_document_id": "CH-01",
      "reason": "展示关键操作界面。"
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
- `content` 是模型必须逐项处理的覆盖基线；`authority` 是来源中的编校/修订声明，`control` 是被声明指定的控制文档，二者决定现行口径但不建立普通素材。`derived` 表示转录平台附带的关键词、议程摘要、重点内容、Q&A 或 PPT 章节标题，只能帮助定位原始 content block，不得独立建立素材或事实；`heading`、`image`、`speaker`、`timestamp` 与 `separator` 保留结构信息，不要求建立素材。
- current 模式会精确解析声明中《文档标题》对应的同目录文件；缺失或重名时索引失败。声明指定章节内存在“原口径 / 修订口径”两列表格时，每行生成一个连续 `COR-xxx`，保留精确来源行、旧口径、修订口径和可确定的纯旧别名。historical 模式不加载 current 修正规则，只由 manifest 的 `reader_notice` 向读者披露非现行边界。
- 索引器记录来源文件 SHA-256、块行号、字符数、块哈希和短预览，不复制整份原文。
- manifest 的 `sources` 必须与来源索引的 ID 和相对路径完全一致；`source_index.sha256` 必须绑定真实索引文件。
- 生成验收优先提供 `--source-root`：索引输入是单个文件时传同一文件，索引输入是目录时传同一目录。验证器会重新枚举完整输入范围并计算原始来源文件 SHA-256；未提供时只能证明索引内部契约，不能证明当前索引仍对应原始输入。

## 素材覆盖规则

- 每个 `kind=content` 的 `BLK-xxxxx` 至少出现在一个素材的 `source_block_ids` 中；未知块、非 content 块、完全未覆盖的块都验收失败。
- `MAT-xxx` 表示一个读者可复用的信息单元，而不是一个发言片段、标题或整节汇总。通常把 2—5 个相邻、同一教学点或同一连续操作阶段的块合并为一项；只有新内容本身能独立讲清时才拆分，不因微步骤、插话或块边界逐项建素材。include 素材最多绑定 6 个来源块；来源已把多个独立教学点塞在同一长块时才允许一块拆成多项。同一块不得同时 include 与 skip。
- 整份账本的素材总数不得超过 `max(60, ceil(content block 数 × 0.5))`。`status.maximum_material_count` 给出当前上限；超过时合并同一观点、连续操作阶段或同一 skip 理由，再进入正文阶段。
- 全部素材共用 `MAT-xxx` 命名空间并从 `MAT-001` 连续分配，skip 项也不例外。禁止 `SKIP-001`、`OMIT-001` 等平行编号；去向只由 `disposition` 表达。
- `include` 素材必须指定目标章节，并出现在该章 `material_ids` 中。
- 每章必须声明非空且不重复的 `section_headings`；最终章节的 H2 必须与该数组文字和顺序完全一致。每个 H2 至少绑定一个 include 素材，禁止没有素材的“自然延伸”、总结性空节或模板节。
- 每个 include 素材必须指定 `target_section_heading`，且该标题存在于目标章节的 `section_headings`；skip 素材的目标章节和目标小节都必须为 `null`。
- `skip` 素材使用受控 `skip_code`：`derived_duplicate`、`meeting`、`device`、`chatter`、`pure_repeat`、`no_course_value`、`authority_superseded`，同时写具体 `skip_reason`。`authority_superseded` 只能覆盖 route 已确认的 `superseded_source_block_ids`，反过来这些块也必须全部使用该 code，不能进入 include；候选块还必须先在 review 矩阵中逐项作出与隔离列表一致的判断。`pure_repeat` 与 `no_course_value` 合计最多覆盖 `max(1200 字, 全部 content block 字符数的 5%)`；高价值演示或迭代过程不能借泛化理由整段跳过。其他 skip code 不占该预算，但仍须语义匹配并接受人工抽查。

## 正文证据规则

- include 素材在正文生成前，必须预先选定 1—3 个 `coverage_terms`；数量至少为 `ceil(source_block_ids 数量 / 3)`（最低 1、最高 3）。每个词必须逐字存在于该素材绑定的原始来源块，优先选择步骤、结果、数字、限制或专名；不要求逐字出现在摘要中。`merge` 报错时从候选中选择完整、有辨识度的来源短语，不盲抄口语指代、语气词或截断片段，不得发明抽象概念，也不得全用 `AI` / `Agent` / `Skill` 类通用词。skip 素材填空数组。
- 每个 include 素材必须提供 `reader_evidence.quotes`，包含 1—3 段真实存在于其 `target_section_heading` 范围内的连续摘录。优先由 `finalize_manifest.py --phase final --write` 从成稿确定性生成，避免弱模型手工维护大量重复审计字段；同章其他小节出现同样词语也不能替代本节证据。
- 1—3 段摘录合并后的长度随来源块数量增加：案例、操作、踩坑、取舍、疑问类至少 `max(80, min(240, 35 × 来源块数))` 字；观点、金句和其他类至少 `max(30, min(180, 25 × 来源块数))` 字。长度只是防止一句带过的最低门槛，不是充分语义证明。
- 预承诺的所有 `coverage_terms` 都必须出现在 1—3 段证据的合并文本内，不要求挤进同一段。正文完成后不得因为某个事实没写进去，而删掉、改成更泛的覆盖词，或专门拼一段审计文字。
- 不同素材不得复用完全相同的一组证据摘录。一个段落确实承载多个相关素材时，为每项选取不同片段组合。
- 证据只写在 manifest，读者正文不显示真实编号或占位形式的 `MAT/BLK/SRC/IMG` 审计标识。除非来源本身讨论这些文件或编号，正文也不得出现 `source-index.json`、`course-manifest.json`、门禁、审计或生成过程名称。

## 图片与文件规则

- `source-index.json` 中每个 `kind=image` 块都必须在 manifest 中逐项登记；按来源索引顺序跨全部来源连续编号 `IMG-xxx`，`source_ref` 精确对应，`original_markdown` 原样保留。不能只登记正文选中的图片。
- `select-images` 校验最低代表图数量、图片 ID、目标文档和具体理由，再按来源顺序同步字段；不要手工编辑完整 `images` 数组。
- `body_action=insert` 时，ID 必须在目标文档 `image_ids` 中精确出现一次；`asset_only` 或 `skip` 时目标为 `null` 并填写理由。
- 目标文档 `image_ids` 按最终正文实际顺序填写；验证器比较图片精确集合、目标和顺序。
- 每份读者文档的正文图数不得超过 `max(3, ceil(可见文字数 / 500))`，整套课程也按相同密度计算总上限。连续截图优先保留起点、关键转折和结果代表图，其余转为 `asset_only`。
- 来源图片少于 12 张时不设正文图片下限，允许全部为低价值图片的合法近似情形。来源图片达到 12 张时，整套课程至少插入 `min(读者文档数, ceil(源图片数 / 20))` 张代表图，防止弱模型把整套 PPT 全部降级为附件；最低数量不证明图片语义选择正确，仍需人工复核。
- manifest 内路径使用课程目录下的可移植相对路径，不允许绝对路径、反斜杠或 `..`。
- manifest 声明的总览、章节和审计文件必须存在且非空；存在未声明的编号章节时验收失败。读者文件名使用真实课名/主题，禁止模板方括号、`TBD`、`TODO` 和 `: * ? " < > |`。
- 候选课程目录不得包含批次、计划、图片选择等临时 `.json` / `.yaml` / `.yml`，也不得包含 `.py`、`.sh`、`.js`、`.ts`、`.command` 辅助脚本或 `.course-work`、`__pycache__` 等生成缓存；允许的机器 JSON 仅为 `source-index.json` 与 `course-manifest.json`。
- 默认最多 8 个章节。只有用户明确要求更多章节时才读取 [advanced-overrides.md](advanced-overrides.md)；不得为了照搬原稿 H2、会务、安装准备或讲者介绍而提高上限。

## 验收边界

验证器客观检查：来源/索引哈希、权威声明与逐项确认、每个 `COR-xxx` 的唯一 H2 路由、目标节中原样修订句、纯旧别名未进入任何读者文件、historical 总览声明、content block 去向、素材总数预算、泛化跳过预算、coverage term 是否真实存在于绑定来源块、来源外缩写释义、冻结 H2 顺序、每节素材绑定、目标小节内 1—3 段正文证据、include 素材颗粒度、章节可见文字相对纳入来源的最低深度（仅单章 40%）与来源密度上限（单章 `max(1400 字, 来源字符数 × 2.5)`）、默认八章上限、占位符、manifest 结构、文件完整性、候选目录辅助脚本/缓存、源图片全登记、图片契约/最低筛选数量/密度、素材双向映射、中文半角标点、引号闭合、高度近重复长段、明显来源框架和审计分离。不存在全局字数下限；不得计算还差多少字再追加通用段落。

人工检查：除工具注入句以外的段落是否仍用同义改写传播旧口径，适用范围是否被绝对化，证据摘录是否真的承载素材语义，跳过理由是否合理，数字/动作/建议是否忠实，跨章重复与引用是否自然，图片是否帮助理解。脚本 PASS 证明逐条修正契约已兑现，不证明整套课程没有更隐蔽的语义矛盾。
