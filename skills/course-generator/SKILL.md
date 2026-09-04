---
name: course-generator
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "2.9.15"
license: MIT
description: 从转录稿或文献生成可独立阅读、可溯源验收的结构化课程，也可在用户明确要求时归档既有课程或从已验证素材提取培训方案。本技能应在用户要“把长转录稿整理成课程”“生成总览和章节”“归档课程”“按受众定制课程方案”时使用。不要用于：仅做 ASR 纠错（用 transcription-corrector）、复盘讲课表现（用 lecture-review）、把多篇文章扩写成书（用 article2book）。
---

# Course Generator v2.9.15

## 选择模式

生成模式是主入口；归档和提取是显式后续动作，不因生成完成自动触发。

| 模式 | 何时进入 | 必需输入 | 主输出 |
|---|---|---|---|
| 生成 | 将转录稿、逐字稿或文献整理成课程 | 输入文件/目录、期望输出位置 | `00 + 章节 + course-manifest.json` |
| 归档 | 用户明确要求复制/移动到知识库 | 已生成课程、归档根目录、日期/课名 | 已验证的归档副本 |
| 提取 | 根据受众、时长和主题组合培训方案 | 需求描述、课程索引、既有课程素材 | 定制课程方案 |

若意图仍不明确，先根据输入判断；会改变文件位置、覆盖策略或课程边界时再追问。原始材料默认只读，生成模式不修改源文件。

## 共用边界

- **忠实可溯源**：数字、动作、后果、建议和专有名称可回到 `SRC-xxx` 定位；无法定位的内容不写成事实。
- **显式权威声明优先**：来源写明“不作为现行规范”“以某文档为准”“统一见勘误/修订口径”时，先解析控制文档，再做课程结构。控制章节中的“原口径 → 修订口径”表会被编译为 `COR-xxx`；每条修正必须路由到一个计划 H2，并把工具给出的每个候选旧口径块逐项判定为 `superseded` 或 `retained_current`。被替代块只能进入 `authority_superseded` 跳过项，不能再充当正文证据；修订句由脚手架原样注入并作为该问题的唯一当前结论，纯旧别名不得重新进入任何读者文件。控制文档只纠正或约束历史素材，不自动扩成新的课程主题；只有用户明确要求保留历史版本时才使用 historical 模式，并在总览向读者披露非现行边界。
- **封闭来源展开**：只把原文已经提供的事实、案例要素、步骤和判断写厚；不借常识补全缩写、参数、产品能力、标准流程、行业案例、商业模式或未来路线。来源只给出设想、举例或保留意见时，正文保留同等语气，不升级为确定方案。
- **高价值素材不得净丢失**：每个确定性 `content block` 都必须进入素材或使用受控理由跳过；但来源块只是盘点单位，不是写作颗粒度。案例、操作、踩坑、取舍和判断技巧应按读者可复用的信息单元拆分并充分展开，再从真实正文取证。“去来源痕迹”只改叙述框架，不连带删素材。
- **读者成品与审计分离**：章节不显示原文区间、素材编号或生成来源；这些信息写入 `course-manifest.json` 和可选审计文件。
- **专名与图片保真**：英文产品名、Skill、命令、文件名保留原写法；正文图片使用 manifest 中的原始 Markdown。
- **客观项脚本验收，语义项人工复核**：验证器检查真实产物，不采信大纲或执行者自报；素材展开质量、跨章逻辑和事实忠实度仍由人工判断。
- **章节也是证据边界**：最终正文的每个二级标题必须在冻结的章节计划中声明，并至少绑定一个 include 素材；素材证据只能从它的目标二级标题内抽取。不得用“自然延伸”“知识管理”等无来源小节补齐结构。
- **来源密度约束扩写**：章节可见正文不得超过 `max(1400 字, 本章纳入来源字符数 × 2.5)`。这不是写作目标，而是识别稀薄来源被常识、套话或重复段落注水的异常上限；素材不足时合并到来源更充分的章节，不能凭空补厚。
- **转录噪声不得事实化**：明显断裂、疑似同音误识别或上下文无法解释的 ASR 片段，不得照抄成课程事实。来源带有“我记得”“好像”“可能”“比如”“畅想”等不确定、举例或设想标记时，正文必须保留同等语气；当身份、数量、平台名与断裂片段混在一起且无法由邻近上下文唯一确认时，整项舍弃，不得挑出醒目的数字或专名写成确定事实。
- **中文书面成品约束**：中文正文使用全角逗号、分号、冒号、问号和感叹号，引号必须成对；不得用高度近重复的长段补足篇幅。读者正文不得出现真实或占位形式的 `SRC/BLK/MAT/IMG` 标识，也不得讨论门禁、审计或生成过程。

冲突时依次以忠实/可溯源、读者正文的素材守恒与展开、章节边界、书稿化表达、审计便利为准。不得为了更快填完 manifest 而压缩正文；篇幅下限用于发现异常缩水，来源密度上限用于发现无依据扩写，两者都不是独立完成证据。

## 配置

- **生成模式**不要求 `config/paths.yaml`。优先使用用户指定输出目录；未指定时，在输入目录旁创建新课程目录，并在写入前说明位置。
- **用户词典**可选：复制 [user_dictionary.example.yaml](config/user_dictionary.example.yaml) 为本地 `config/user_dictionary.yaml`。只校正上下文明确的近似误转写，低置信内容保留原文。
- **归档/提取模式**需要路径时，复制 [paths.example.yaml](config/paths.example.yaml) 为本地 `config/paths.yaml`。本地配置由 `.gitignore` 排除。
- 目标目录已存在且含文件时，不静默覆盖；使用用户指定的新目录/版本目录，或先取得覆盖授权。

## 生成模式

流程：`确定性来源与权威索引 → 官方工具初始化账本 → 确认权威处理并冻结章/节计划 → 分批合并素材 → 带原文重建的账本预检 → 短清单选图 → 确定性章节脚手架 → 单章生成/门禁 → 正文证据自动收口 → 确定性验收 → 人工复核 → 可选归档`

### 1. 建立确定性来源索引

先运行索引器，不让模型自行决定“哪些段落存在”：

```bash
python3 scripts/index_sources.py \
  --input <单个来源文件或来源目录> \
  --output <课程目录>/source-index.json \
  --authority-mode current

python3 scripts/ledger_tool.py init \
  --source-index <课程目录>/source-index.json \
  --source-root <同一个来源文件或来源目录> \
  --manifest <课程目录>/course-manifest.json \
  --title "<真实课程名称>" \
  --overview-file "00 <真实课程名称> - 总览.md"
```

索引器按稳定顺序分配 `SRC-xxx` / `BLK-xxxxx`，记录相对路径、来源 SHA-256、行号、块类型和预览。`content block` 是覆盖基线；标题、图片、说话人标签与独立时间戳保留为索引上下文，但不要求建立素材。转录平台附带的“关键词/议程摘要/重点内容/Q&A/PPT 章节标题”在同时存在原始“转录内容”时标为 `derived`：只用于定位，不得作为独立事实或新章节来源。

默认 `--authority-mode current`。索引器在材料开头识别明确编校/修订声明，并从同目录精确解析《控制文档》：声明块标为 `authority`，控制文档块标为 `control`，两者都不进入普通素材覆盖基线；指定章节存在“原课堂口径 / 修订后的课程口径”等两列表格时，确定性生成 `authority.corrections`，并为每条修正给出最多 8 个 `superseded_candidate_block_ids` 作为高召回检索入口。候选只帮助定位，不等于自动删除；必须结合块预览和原文逐项判断，不能只提交自己注意到的子集。控制文档缺失或同名不唯一时直接失败，不得因赶进度忽略声明。只有用户明确要求整理“当时课堂原貌/历史版本”时才改用 `--authority-mode historical`；不得由 Agent 自行把 current 降级为 historical。

- 材料能够在保留生成空间的前提下完整进入上下文时，可以直接整体分析。
- 多文件、超长转录或完整读取会挤压生成/复核空间时，使用索引化两遍流程：先按 `BLK-xxxxx` 分批读取并提取素材账本，再基于账本合并全局结构；不要强行一次性塞入全部原文。
- 分块边界不得切断一个连续问答、案例或三步以上操作链；确需切分时保留重叠上下文，并让相邻块引用同一稳定 source ref。

### 2. 冻结章/节计划并分批建立素材账本

先查看 `ledger_tool.py init/status` 返回的 `authority_notices`、`authority_corrections` 与已经带短预览的 `authority_candidate_review_queue`。current 模式下，读取每条声明指定的 `controlling_source_ids`、`section_hint` 和修正候选块；对每个 `COR-xxx` 选择一个能自然承载修订口径的计划 H2。按 review queue 的原顺序逐块读取预览和必要原文：直接陈述或支持旧口径的判为 `superseded`，不承载旧结论的判为 `retained_current`；每项摘录至少 6 字、能逐字回到该候选预览的 `evidence_quote`，再写至少 12 字的专属理由。不得为多个候选复制同一理由，不得把整张高召回矩阵一律删除，也不得漏掉看似相近但用词不同的候选。候选之外仍要检索同义旧结论。找到被替代块时使用 `blocks_identified` 并列出全部确认块；确实没有时使用 `no_matching_source_block` 并写明检索依据。模型不摘抄、概括或重写修订句。控制来源只用于消解冲突，不建立 `MAT-xxx`。然后基于其余普通 `content block`、完整素材盘点和必要原文片段确定章/节边界，把权威确认、逐条修正路由、候选逐项判定、被替代来源块、章节文件名、标题和最终二级标题顺序写成计划 JSON，再运行：

```bash
python3 scripts/ledger_tool.py plan \
  <课程目录>/course-manifest.json \
  <临时目录>/chapter-plan.json
```

默认路径最多 8 章，`plan` 会在正文生成前失败关闭；不得因来源标题多、单章门禁难通过或工具提示而自行提高上限。只有用户明确要求超过 8 章时才读取 [advanced-overrides.md](references/advanced-overrides.md)。

随后按有界批次读取尚未处理的 `BLK-xxxxx`，输出批次 JSON，并用官方工具合并。批次中只写素材语义、原始块、`coverage_terms`、目标章节和目标二级标题；不要手工分配 `MAT-xxx`、复制 `source_refs` 或修改 manifest。每批宜覆盖 20—40 个 content block，完成后用 `status` 决定下一批，避免弱模型在一次超长回复中同时维护全局编号、哈希和大段正文。完全相同的批次因超时被重试时会幂等跳过，不重复生成素材。

```bash
python3 scripts/ledger_tool.py merge \
  <课程目录>/course-manifest.json \
  <临时目录>/batch-001.json \
  --source-root <同一个来源文件或来源目录>

python3 scripts/ledger_tool.py status \
  <课程目录>/course-manifest.json \
  --next-batch-size 30
```

`status` 的 `next_batch_content_block_ids` 是下一批唯一输入，不重新计算、截取或猜测剩余 ID；最后不足 30 个时原样处理实际返回值。`maximum_material_count` 是整份账本的硬上限 `max(60, ceil(content block 数 × 0.5))`。正常长课通常整理为约 40—80 项素材；若预计超过预算，先合并同一观点、连续操作阶段或同一 skip 理由，再提交批次。`merge` 会一次返回该批全部可独立识别的字段错误，并在覆盖词无效时给出可直接复制的原文候选；一次修完该批错误再重试。

计划必须逐项提交 `authority_acknowledgements`：current 模式使用 `action=apply_control` 并精确回填工具给出的控制来源 ID；historical 模式使用 `action=historical_disclaimer` 并提供将原样进入总览的 `reader_notice`。current 模式还必须按 `COR-xxx` 顺序提交 `authority_correction_routes`；每项同时给出目标章/H2、`supersession_status`、`superseded_source_block_ids`、至少 12 字的 `supersession_note`，以及与候选 ID 原顺序完全一致的 `candidate_block_reviews`。每条 review 都要有逐字来自对应预览的 `evidence_quote` 和不与其他候选重复的理由，只允许 `superseded` / `retained_current`，其结论必须与隔离列表一致。工具从索引复制真正的修订句，模型不得自己改写。缺项、错序、批量同理由、整表全删、漏审候选、状态与块列表冲突或目标 H2 不存在时 `plan` 失败关闭。格式见 [course-manifest.md](references/course-manifest.md)。临时 JSON/YAML 写在课程目录之外；最终课程目录不得遗留批次、计划、图片选择等临时 `.json` / `.yaml` / `.yml`，也不得遗留 `.py`、`.sh`、`.js`、`.ts`、`.command` 或 `.course-work` 等辅助执行文件。

逐块扫描全部 `content block`。每个 `BLK-xxxxx` 必须被一个或多个 `MAT-xxx` 覆盖；`authority` / `control` / `derived` 不建立普通素材。plan 已确认被修订替代的块必须单独或按同一修正合并为 skip 素材，并使用 `skip_code=authority_superseded`；这类块不得进入 include，也不得在正文中作为例子、历史说明或引文变相恢复旧结论。每个 include 素材记录类型、摘要、`source_block_ids`、目标章节和目标二级标题，其他 skip 素材使用受控 `skip_code` 且目标章/节均为 `null`。include/skip 共用一个从 `MAT-001` 连续分配的 ID 命名空间；编号、`source_refs`、图片登记和冲突检测交给 `ledger_tool.py`。`MAT-xxx` 的单位是一项可以单独讲清的观点、案例、操作阶段、踩坑、取舍或疑问，不是一个发言片段，也不是标题下的整节摘要。通常把 2—5 个相邻、同一教学点或同一连续操作阶段的块合并为一项；只有新内容本身能被独立讲清时才拆分，不因每个微步骤、插话或块边界新建素材。一个 include 素材最多合并 6 个相邻来源块；来源已把多个独立教学点塞在同一长块时才允许一个块拆成多项。整份账本不得超过 `max(60, ceil(content block 数 × 0.5))`，超过时在写正文前重建或合并账本。include 素材在写正文前预先填写 1—3 个 `coverage_terms`，数量至少为 `ceil(source_block_ids 数量 / 3)`（最低 1、最高 3）。每个词必须原样存在于该素材绑定的原始来源块，优先选择步骤、结果、数字、限制或专名；不要求为了审计把词硬塞进素材摘要。`merge` 报错时从候选中重选完整、有辨识度的来源短语，不盲抄“我觉得”“比如说”“你像”“做一个新”等口语指代、语气词或截断片段，不发明“范式阶梯”等抽象词，也不得全用 `AI` / `Agent` / `Skill` 类通用词。

`pure_repeat` 与 `no_course_value` 只用于真正重复或没有课程信息的片段，不得用来整体跳过案例、现场操作、Agent 反馈、错误修正、版本比较或产品效果。两种泛化跳过码合计最多覆盖 `max(1200 字, 全部 content block 字符数的 5%)`；超出时在正文生成前失败。`meeting`、`device`、`chatter`、`derived_duplicate` 仍按各自语义使用，不占该预算；`authority_superseded` 只能绑定 plan 已确认的被替代块，不能作为扩充跳过预算的通用理由。

素材分类、词典校正、图片价值判断和章节边界细则见 [outline_prompt.md](references/outline_prompt.md)。机器字段必须同步进入 [course-manifest.md](references/course-manifest.md) 定义的 manifest；`98 图片资产表.md`、`99 课程大纲.md` 只作为可选的人类审计视图，不是验证器的数据源。

素材和图片账本初步完成后，先把进行中的 `course-manifest.json` 落盘。让脚本从来源索引同步每个素材的 `source_refs` 和索引哈希，再运行低成本预检：

```bash
python3 scripts/finalize_manifest.py \
  <课程目录>/course-manifest.json --phase ledger --write

python3 scripts/preflight_ledger.py \
  <课程目录>/course-manifest.json \
  --source-root <同一个来源文件或来源目录>
```

两条命令都以退出码 `0` 为通过。退出码 `1` 时只修复报告的素材划分、去向，或把报告的弱 `coverage_terms` 替换为绑定原文中完整、有辨识度的短语；不重新抽取原文，也不把弱词硬塞进正文。退出码 `2` 表示文件或 JSON 无法读取。不要手工复制大量 source refs。配额、网络或平台异常时保留当前目录并报告失败，不从头重跑整门课程。

预检通过后，从来源图片及相邻内容中选择方法框架、关键界面、转折或结果代表图，只提交短选择清单，不翻改整份 manifest。`status` 会给出 `minimum_reader_image_count`；图片密集来源必须在写正文前达到该最低数。选择 JSON 格式见 [course-manifest.md](references/course-manifest.md)：

```bash
python3 scripts/ledger_tool.py select-images \
  <课程目录>/course-manifest.json \
  <临时目录>/image-selection.json

python3 scripts/ledger_tool.py scaffold \
  <课程目录>/course-manifest.json
```

`select-images` 按来源顺序确定性同步 `body_action`、目标文档和各文档 `image_ids`；未选择图片自动保留为 `asset_only`。`scaffold` 创建缺失章节的精确 H1/H2，并把每条 `COR-xxx.revised_text` 原样放入其目标 H2 的“关键规则”引用块；这些句子是来源事实，不是审计标记，写作时保留原文并围绕它自然展开。已有章节标题不一致或缺少应有修订句时直接失败，不静默覆盖。总览结构仍由 [overview_prompt.md](references/overview_prompt.md) 生成。

### 3. 生成全局大纲

使用已经冻结的章/节计划生成全局大纲；此时只补充章际关系和读者路径，不再增加没有素材绑定的二级标题。按主题组织，不机械按文件切章；分流到其他章节的素材仍保留原 source ref、目标章节和目标二级标题。

默认组织为 3—8 章，8 章是验收上限而非建议值；未收到用户明确的超限要求时，不加载或使用高级上限参数。不按原稿标题逐节切章：开班/签到、领导致辞、设备与安装准备、讲者履历默认不得单独成章；其中可复用判断并入总览或核心章，纯会务/设备信息使用受控理由跳过。只有来源本身就是安装或环境配置教程时，准备工作才可成为主题章。结构性薄章优先合并，不从其他章节复制内容凑篇幅。

### 4. 生成总览

读取 [overview_prompt.md](references/overview_prompt.md)，生成带真实名称的总览文件，例如 `00 法律人 Agent 与 Skill 办案实务 - 总览.md`。方括号示例仅用于说明字段，实际文件名禁止保留 `[课程名称]`、`[主题名称]`、`TBD`、`TODO` 等占位符。结构导览仅在材料确有流程、框架、能力模型或系统关系时加入。总览只插入 manifest 目标为 `OVERVIEW` 的图片。

### 5. 逐章生成

读取 [chapter_prompt.md](references/chapter_prompt.md)。在 `scaffold` 已生成的标题之间填写正文，不重写标题行，也不删除、改写或重复工具注入的修订句。每章只加载该章的 `section_headings`、`material_ids`、`image_ids`、相关 `COR-xxx`、source refs 和必要邻接上下文；长材料模式下不要再次读入全部原文。最终 H2 必须与 `section_headings` 顺序、文字完全一致，每个 H2 至少展开一个绑定素材，素材只写入自己的 `target_section_heading`；计划冻结并合并素材后不得边写边改结构。若结构错误足以影响成品，保留当前候选为失败，在新版本目录重新 `init → plan → merge`，不得手改 manifest 迁移素材。

先把章节写成读者可独立使用的完整正文，再处理审计字段。每章完成后立即运行单章门禁；只有当前章 `PASS` 才写下一章：

```bash
python3 scripts/ledger_tool.py check-chapter \
  <课程目录>/course-manifest.json \
  --document CH-01
```

单章门禁返回精确的标题差异、缺失 coverage terms、图片序列、书面化命中行和深度下限，避免九篇写完后集中返工。它不证明事实忠实度；通过后仍回扫对应 source refs：案例/操作/踩坑类不应只剩一句概述；正文中的数字、动作、结论和专名能定位；问答自然融入；不把讲者现场行为推广成材料没有的通用建议。不要把 `reader_evidence` 的最低长度当作正文目标，也不要围绕 coverage terms 拼一段“过门禁文字”后收笔。

完成全部总览与章节后，不逐项手工复制大量证据，运行：

```bash
python3 scripts/finalize_manifest.py \
  <课程目录>/course-manifest.json --phase final --write
```

脚本只在每个素材声明的目标二级标题范围内，从最终 Markdown 确定性回填可满足条件的 `reader_evidence.quotes`，并按正文实际图片同步 `image_ids`、`body_action` 和目标文档；它不写正文、不发明缺失事实。退出码 `1` 时查看 `unresolved`：若报告某个素材缺 coverage term 或展开长度，只补写该素材对应的真实过程、结果、限制或修正后重跑；不得删词、换泛词、把证据移到别节，或添加“正文证据补丁”“原文痕迹”“覆盖足够长度以满足证据”等面向门禁的段落。读者正文不得出现来源没有讨论的 `source-index.json`、`course-manifest.json`、`coverage_terms` 或 `SRC/BLK/MAT/IMG` 审计 ID；这些生成过程信息只留在 JSON。脚本会保留无法确定的字段并失败关闭，退出码 `2` 表示输入或运行异常。

### 6. 保存规范产物

读者成品：

- `00 法律人 Agent 与 Skill 办案实务 - 总览.md`（示例；使用本课程真实名称）
- `01 从聊天到可执行任务.md`、`02 Skill 的复用边界.md`……（示例；使用真实主题）

实际文件名不得包含说明模板用的方括号，也不得包含 Windows 非法字符 `: * ? " < > |`。

审计产物：

- `source-index.json`：强制，由索引器生成，不手写。
- `course-manifest.json`：强制，按 [course-manifest.md](references/course-manifest.md) 保存，并绑定 `source-index.json` SHA-256。
- `98 图片资产表.md`、`99 课程大纲.md`：可选；生成时在 manifest 的 `audit_files` 声明。

最终课程目录只保留读者成品、两份强制 JSON、manifest 声明的可选审计文件和必要图片资产；生成辅助脚本、批次 JSON、临时目录和缓存不得混入候选交付物。

课程名称优先取自该项目的对外大纲或报价方案；没有正式课名时再基于素材拟名。生成目录日期不用冒充培训实际举办日期。

### 7. 运行确定性验收

保存全部产物后运行：

```bash
bash scripts/verify.sh <课程目录> --source-root <单个来源文件或来源根目录>
```

退出码 `0` 才表示客观门禁通过；`1` 表示产物不符合契约，按失败项修改后重跑；`2` 表示目录、运行环境或验证器异常，同样不得交付。脚本最后一行输出机器可读 JSON，并绑定 manifest 与读者文件 SHA-256。

验证器检查：manifest 与来源索引哈希、原始来源 SHA-256、显式权威声明、逐条修正路由、候选旧口径块的逐字证据与逐项审查、批量同理由/整表全删、被替代块专用隔离、目标 H2 中原样修订句、纯旧别名全局禁用、historical 读者警示、每个 `content block` 的 include/skip 去向、素材总数预算、泛化跳过预算、覆盖词逐字存在且不是低信号口语片段、来源外缩写释义、单样本范围外推、冻结 H2 顺序、每节素材绑定、仅在目标小节内成立的 1—3 段正文证据、include 素材颗粒度、单章文字相对纳入来源的最低深度与来源密度上限、默认八章上限、占位符、总览/章节完整性、素材双向映射、源图片全登记、图片精确集合/目标/顺序、图片密集来源的最低代表图与正文图片上限、候选目录临时 JSON/YAML、辅助脚本/缓存、模糊讲者指代、课程/演示框架、逐字稿口语赘词、中文半角标点、引号闭合、高度近重复长段、面向门禁的证据补丁、可见审计元数据和来源外生成器内部术语。v2.9.15 使用 manifest schema `1.8` 与 source-index schema `1.4`；生成验收必须提供与索引时相同的 `--source-root`，旧课程需要重建索引并升级 manifest 后再验收。

### 8. 完成人工语义复核

脚本通过后仍检查：

- **素材守恒**：抽查各章 `material_ids`、`source_block_ids`、预承诺 `coverage_terms`、正文证据和跳过项；高价值素材未发生无理由净丢失，也没有用一段泛化文字假覆盖多个具体素材。
- **忠实溯源**：抽查数字、动作链、建议、结果和专名；事实可回原文定位，推断有明显推论语气。
- **权威口径**：逐项核查 `source_authority.corrections`、路由 H2 与所有读者文件；机器已保证修订句存在并阻断纯旧别名，但仍要检查其他段落没有用同义改写制造内部冲突，也没有把适用于特定团队的选择写成通用规律。
- **封闭来源高风险扫描**：逐项回查缩写释义、技术参数、命令/路径/字段、产品能力、流程承诺、行业案例、商业模式和时间预测；原文未明确给出的删除，不以“行业常识”补齐。
- **跨章一致性**：主题边界清楚、无大段重复、交叉引用章号正确。
- **图片语义价值**：图片位置确实支撑相邻论述，而非只满足数量。

向用户交付时分别报告“脚本验收结果”和“人工复核范围”，不得把客观 PASS 扩大为全量语义正确。

## 归档模式

仅在用户明确要求归档时执行：

1. 读取课程 manifest；旧课程无 manifest 时按旧命名盘点，并标注为 legacy/未通过 v2.9.15 细粒度验证。
2. 从用户材料确认培训实际日期、正式课名、归档根目录和主办方写法；不要用生成日期替代培训日期。
3. 默认复制，不默认移动；只有用户明确说“移动”时才移走源文件。
4. 目标已存在时不覆盖，先使用新版本目录或请求用户决定。
5. 复制后对目标目录重跑验证；源/目标文件集合或哈希不一致时归档失败。
6. 知识库已有索引且本次归档范围包含索引维护时，再更新索引。

## 提取模式

读取 [extract_prompt.md](references/extract_prompt.md)，按 `解析需求 → 匹配课程 → 定位已验证素材 → 提取重组 → 输出方案` 推进。

需求至少包含受众、基础水平、培训时长和重点方向。优先使用带 manifest 的课程，从 source refs 追踪素材；只有 raw 转录稿时先走生成模式。既有材料覆盖不了的主题必须标注“需补充素材”，不凭空补课。

## 权限与隐私

- 只读取用户指定的材料范围，只向用户指定或已说明的本地输出目录写文件。
- 来源盘点会执行 `index_sources.py` 读取用户指定的 `.md` / `.txt` 并写入课程目录下的 `source-index.json`；`ledger_tool.py` 的 `init/plan/merge/select-images` 只原子更新课程目录内的来源索引或 manifest，`scaffold` 只创建缺失章节的标题脚手架，`status/check-chapter` 只读；`finalize_manifest.py` 默认只预览，只有带 `--write` 时才原子更新 manifest，从不修改读者正文；验收会执行 `verify.sh` / `verify_course.py` 读取课程、来源索引和用户指定的原始来源根目录。脚本不联网、不安装依赖、不修改原始材料。自测脚本仅写入并自动清理系统临时目录。
- 本技能不需要网络、凭证或外部服务。
- 未脱敏转录稿、客户信息和课程材料按最小必要原则处理；公开示例、manifest 模板和变更记录不得写入真实客户信息或本机私有路径。

## 依赖

### 系统依赖

| 依赖 | 用途 | 安装方式 |
|---|---|---|
| `python3 >= 3.10` | 运行 manifest 领域验证器 | macOS: `brew install python`<br>Linux: `sudo apt-get install python3` |

### Python 包

无需第三方 Python 包，验证器仅使用标准库。

## 参考与脚本

- [outline_prompt.md](references/outline_prompt.md)：素材/图片账本与全局大纲。
- [overview_prompt.md](references/overview_prompt.md)：总览生成。
- [chapter_prompt.md](references/chapter_prompt.md)：章节书稿化生成与人工自检。
- [extract_prompt.md](references/extract_prompt.md)：提取模式。
- [course-manifest.md](references/course-manifest.md)：产物契约和最小示例。
- [course-manifest.schema.json](config/course-manifest.schema.json)：JSON Schema。
- [source-index.schema.json](config/source-index.schema.json)：来源索引 Schema。
- [index_sources.py](scripts/index_sources.py)：确定性来源分块与哈希索引器。
- [index_sources_selftest.py](scripts/index_sources_selftest.py)：索引器回归套件。
- [ledger_tool.py](scripts/ledger_tool.py)：弱模型友好的账本初始化、章/节计划、批次聚合校验、精确下一批、代表图同步、章节脚手架与单章门禁工具。
- [ledger_tool_selftest.py](scripts/ledger_tool_selftest.py)：账本工具正常/冲突/越界故障注入回归套件。
- [preflight_ledger.py](scripts/preflight_ledger.py)：长篇生成前的素材账本 fail-fast 预检。
- [preflight_ledger_selftest.py](scripts/preflight_ledger_selftest.py)：素材账本预检回归套件。
- [finalize_manifest.py](scripts/finalize_manifest.py)：从索引与最终 Markdown 确定性同步 source refs、正文证据和图片映射。
- [finalize_manifest_selftest.py](scripts/finalize_manifest_selftest.py)：manifest 自动收口回归套件。
- [verify.sh](scripts/verify.sh)：验收入口。
- [verify_course.py](scripts/verify_course.py)：标准库领域验证器。
- [verify_selftest.py](scripts/verify_selftest.py)：故障注入回归套件。
