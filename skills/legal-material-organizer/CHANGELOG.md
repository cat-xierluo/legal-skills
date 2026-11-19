# 变更日志

## [0.16.0] - 2026-11-19

### 新增

- 从私有候选清洁导出为公仓正式源码，并加入「法律材料与证据处理」专家套件。
- 新增匿名混合材料示例，演示目录扫描、manifest 生成和处理任务导出。

### 改进

- 将公开维护文档压缩为任务状态、长期方向和核心设计决策，不再分发内部执行流水。
- 明确公仓源码为权威实现；真实材料、运行归档、候选外评测和个人配置保留在私有层或仓外证据目录。
- 根 README 与套件索引同步标注源码版本和尚无公开 ZIP 的发布状态。

### 技术优化

- 发布校验不再要求本地维护文档，并增加邮箱、电话、证件号、案号、聊天账号、机构名和内部编号的确定性隐私锚点检查；文本扫描范围覆盖 `.url` 等常见配置与网页文件。

### 验证边界

- 0.16.0 仍为 `0.x` 公开候选，不声明 1.0 稳定版。
- 候选外独立 requirements baseline、held-out cases、producer logs 和签名回执继续标记 `NOT_VERIFIED`。

## [0.15.0] - 2026-08-01

### 新增

- 新增 `scripts/material_processing_handoff.py`，以工具中立方式导出待处理任务，并统一回写成功、失败和部分可读结果。
- 新增 `PROCESSING-CLOSURE` 硬约束，检查材料、预处理候选、处理运行、输出变体和主可读变体是否闭合。
- 新增成功闭环与“候选已完成但缺少结果”的匿名稳定性夹具。

### 修复

- 修复外部处理完成后只能手工修改 manifest、容易漏写 `variants`、`processing_runs` 或 `primary_readable_variant_id` 的稳定性缺口。
- 修复失败处理可能没有错误原因或人工复核入口、却被误标为完成的问题。
- 移除处理清单中对具体 OCR 工具的优先绑定，改为由运行环境选择合适的可用能力。

### 技术优化

- 结果回写改为先完整校验、再同目录原子替换；拒绝不存在、越出 `work_dir` 或使用符号链接的输出文件。
- 结果合同改为字段白名单，限制 `extra_json` 大小并拒绝正文类字段，防止提取全文或转写稿回流到元数据 archive。
- 使用结果字段和输出指纹生成稳定运行 ID 与变体 ID；重复回写同一结果不新增重复记录。
- 增加工具中立任务导出、成功回写、部分可读、失败转人工复核、越界阻断、缺失输出、错误关联和幂等回写测试。

### 文档完善

- 在 `SKILL.md`、字段字典和处理清单中明确：PDF 文字层判断及各种内容识别由外部可用能力负责，本 Skill 只处理路由、交接和结果登记。
- 将 Skill、脚本、机器合同和参考模板版本同步至 v0.15.0。

## [0.14.0] - 2026-07-30

### 新增

- 新增 `config/instruction-stability-contract.json`，把存储分离、引用完整性和不确定性路由三项硬约束映射到最终 manifest、active checker、正反例、measurement 和 observable。
- 新增 `scripts/check_material_manifest.py`，独立检查真实材料是否误入 archive、材料/变体/材料组引用是否闭合，以及不可读材料是否进入后续处理或人工复核。
- 新增 1 个匿名合法正例、3 个最小变异反例和 1 个历史 archive 膨胀回归；夹具只含合成 JSON，不含真实案件材料。

### 改进

- 为三项硬约束增加稳定锚点，降低自然语言规则与验证器之间的映射漂移。
- 把零散规范性措辞收口到权威锚点，references 保留操作说明而不重复声明同一硬约束。
- 将脚本、模板、字段字典和 Skill 元数据版本同步至 v0.14.0。

### 技术优化

- 新增 checker 正向、最小违规、历史回归及真实 scanner 输出测试；失败时精确返回目标 constraint ID、artifact SHA-256 和逐约束 measurement。
- 明确候选内 checker 只能形成领域不变量证据；没有候选外 evaluator 签名和三轮回执时继续标记 `NOT_VERIFIED`。

## [0.13.0] - 2026-07-30

### 改进

- 将运行时元数据 archive 与真实材料 work 目录分离；默认写入源材料旁的 `.legal-material-organizer/<名称>/`，不再向 Skill 包写入运行记录或解压材料。
- 每次扫描前重建受控 `work/extracted_containers/`，避免解压副本跨运行累计膨胀。
- 重写 `SKILL.md` 和输出模板，收口为材料清点、理解、整理与交接，不把材料关联说明扩张为法律结论。
- chat-html 下载器改用解析后的主机名匹配，拒绝伪造白名单域名、`file://`、localhost、私网字面地址和危险重定向；增加 100MB 单文件上限与同名避让。

### 修复

- 同步 frontmatter、脚本和模板版本，修复 `SKILL.md` 仍停留在 v0.11.0 的版本漂移。
- 将许可证从 CC BY-NC-SA 调整为项目规定的 CC BY-NC，并同步完整许可证文本。
- 修正文档中把 chat-html 资源候选误写成独立 `materials` 记录的问题，使说明与当前实现一致。

### 技术优化

- 新增 `scripts/validate_release.py` 和对应单测，阻止真实 archive、开发目录、缓存、私有绝对路径、断链引用、版本或许可证漂移进入发布候选。
- 增加默认运行目录、元数据 archive 纯净性、URL 欺骗、私网 URL、禁止覆盖等回归用例。
- 将版本、作者和主页收进标准 `metadata` 字段，兼容严格的 Codex Skill frontmatter 校验器。
- 发布检查区分工作区噪声与实际发布物：Git 已忽略的 `.DS_Store` 不阻断仓库候选，非 Git 打包目录仍会拒绝该文件。

### 文档完善

- 删除已完成的 `docs/plans/`、具名 benchmark 占位、重复设计稿和缓存目录。
- 清空 Skill 内运行材料 archive，只保留 `.gitignore` 与 `.gitkeep`；目录层级与存储边界改由 `SKILL.md` 和 `references/output-template.md` 维护。
- 对 `SKILL.md`、references、TASKS、DECISIONS、CHANGELOG 和测试样例执行去具体化处理。

## [0.12.0] - 2026-07-12 - chat-html 抽取子路径

### 新增

- `scripts/chat_html_extract.py`：识别 chat-html（Cubox/微信/企微导出件）+ 抽取外链下载/图片/视频三类资源 + 下载器（白名单 + 重试 + 失败不阻断）。
- `scripts/scan_materials.py` 接入 chat-html 子路径：识别 → 抽取 → dry-run → 可选真下载。
- `references/chat-html-extract.md`：抽取规则与白名单。
- `references/field-dictionary.md`：新增 `extra_json.chat_html` 段。
- 增加匿名化合成用例，覆盖三类资源抽取、上下文识别和下载失败路径。

### 行为

- 默认不下载；使用 `--chat-html-dry-run` 生成独立核对清单，使用 `--chat-html-download` 才会真下载。
- 单条下载失败/拒绝记录到 manifest（`download_status` 在 `extra_json.chat_html.downloads`）。
- chat-html 识别成功但未抽取到资源时标记 `needs_human_review`，除非显式使用 `--chat-html-no-fail`。
- 材料清单末尾自动追加「外部资源抽取对账」小节。
- `SKILL_VERSION` 同步从 0.11.0 → 0.12.0。

## [0.11.0] - 2026-05-20

### 新增

- **局部 registry 数据层**：`materials_manifest.json` 新增 `material_sets`、`variants`、`processing_runs`、`follow_up_candidates`，形成案件材料包内的局部事实源。
- **材料组模型**：初次扫描按通用材料类型初始化材料组，支持后续综合分析按组理解，而不是只按物理文件夹汇总。
- **变体与处理过程记录**：为原始文件自动生成 `original` variant；解压等处理写入 `processing_runs`，后续 OCR/ASR/视觉理解可追加对应变体和运行记录。
- **后续候选动作**：对需要 OCR、ASR、文本提取、网页留痕或人工复核的材料生成 `follow_up_candidates`。
- **字段字典**：新增 `references/field-dictionary.md`，固定核心字段和受控值，避免字段语义漂移。

### 改进

- `材料清单.md` 新增“所属材料组 / 可读性 / 待处理动作”列，仍只展示 `display_code`，不展示后台 `material_id`。
- `filing_plan.json` 和 `renaming_map.json` 增加材料组字段，统一记录展示编号、参照度和整理路径。
- 旧 manifest 缺失新结构时自动补齐默认数组，继续兼容既有增量扫描。

### 修复

- 修复旧 manifest 缺少可读性字段时，文本材料无法自动恢复 `primary_readable_variant_id` 的问题。
- 修复二次扫描会重置 `follow_up_candidates.status` 和 `extra_json` 的问题。
- 修复源文件缺失后旧 variant 仍显示为 `asset_status: available` 的问题。
- 对齐字段字典与实际 `processing_runs` 输出字段，统一使用 `input_path`、`output_path`、`error_message`。

### 文档完善

- 更新 `SKILL.md`、输出模板、综合分析模板、处理清单和命名规则，统一“archive JSON 是事实源，源目录 Markdown 是阅读投影”的描述。
- 记录本次不整合 `content-registry`、不引入 SQLite 的局部 registry 决策。

## [0.10.0] - 2026-05-20

### 新增

- **入库身份与展示编号分离**：`material_id` 改为后台稳定主键（`M-000001`），律师可见交付物统一展示 `display_code`（如 `A001`、`B003`、`D005`）。
- **参照度排序模型**：新增 `reference_level`、`reference_score`、`reference_basis`，展示编号按 A→B→C→D、评分降序、扫描顺序生成，全局递增不按等级重置。
- **整理计划记录**：archive 新增 `filing_plan.json` 与 `renaming_map.json`，记录 `material_id -> display_code -> current_path` 的映射。
- **content-registry 投影字段**：manifest 增加 `material_key`、`variant_kind`、`readability_status`、`processing_need`，用于表达轻量入库、变体和预处理状态。

### 改进

- 源目录 `材料清单.md` 不再暴露后台 `material_id`，只展示前台 `display_code`。
- 兼容旧 manifest 中的 `M-XXX`、`D-XXX`、`A-XXX` 编号，迁移为稳定 `material_id` 并写入 `legacy_ids`。
- 更新 `scan_materials.py` 测试，覆盖展示编号重排、后台 ID 稳定、旧编号迁移和 Markdown 隐藏后台 ID。

### 文档完善

- 更新 `SKILL.md`、输出模板、综合分析模板、处理清单和命名规则，统一“后台入库身份 + 前台展示编号”的表述。
- 记录本次后台身份与展示编号分离的架构决策。

## [0.9.0] - 2026-05-18

### 新增

- **统一整理流程**：删除"副本模式"和"原地模式"的二分法，Step 6 统一为"理解 → 规划 → 执行 → 回更新引用"单一流程
- **原件快照策略**：Step 1 新增原件保留策略——压缩包来源保留原包不动、文件夹来源先压缩一份快照，压缩包作为不可变溯源锚点
- **整理后路径回更新**：Step 6 新增整理后必须回更新所有材料说明、材料清单和 manifest 的路径引用
- **manifest 双路径记录**：`original_display_path` 保留整理前路径，`display_path` / `organized_path` 记录整理后路径
- **数据架构明确**：manifest 为真相源（M-XXX 主键，与路径解耦），材料说明为当前状态的视图，材料清单是索引
- **清单表格新增整理前路径列**：同时展示原始路径和整理后路径，通过编号桥接

### 改进

- **文件命名规则**：从 `{编号}_{类型}_{关键词}_{日期}` 改为 `M-XXX {描述} - {补充}.{扩展名}`
- **文件夹命名规则**：新增 `NN - {描述性名称}` 格式（NN 为两位序号）
- **删除 `organized/` 副本目录**：不再创建整理副本，直接在源材料目录上执行整理
- **输出质量要求**：更新"不破坏原件"条款，改为通过原件快照策略保障
- **版本号**：统一更新为 v0.9.0

### 文档完善

- 重写 `SKILL.md` Step 1（原件快照策略）、Step 6（统一整理流程）
- 重写 `references/organization-and-naming-rules.md`：新增文件夹命名规则，删除 organized/ 相关内容
- 更新 `references/output-template.md`：整理后目录结构、清单模板（含整理前/后路径）、manifest 新增 `original_display_path`
- 更新 `references/material-processing-checklist.md`：新增整理回更新、原件快照、编号前缀检查项

## [0.8.1] - 2026-05-18

### 实践发现

在一批匿名化后的程序性材料样例上完整执行 v0.8.0 后发现以下改进点：

- **材料编号前缀应写入文件名**：`M-011 商品发货地 - 城市名.png` 而非仅在清单中编号，让文件脱离清单也能识别
- **文件夹应加序号前缀**：`01 - 聊天记录/`、`02 - 支付记录/` 等，让目录浏览时有序
- **根目录散落材料应归入分类子文件夹**：理解完成后，根目录只保留分析性文档（材料清单、材料说明、综合分析），原始材料按类型/主题归入子文件夹
- **整理后必须回更新引用**：文件移动/重命名后，材料说明和清单中的路径引用必须同步更新
- **综合分析可转为 Word 交付**：律师交付时 Word 格式更实用

### 文档更新

- 记录 v0.9.0 整理流程设计决策
- 更新工作日志

## [0.8.0] - 2026-05-18

### 新增

- **材料综合分析**：新增 Step 5.5，在所有文件夹材料说明完成后，自动生成 `{源目录名称} - 材料综合分析.md`，包含材料概况、案件上下文关联、证据链分析、材料完整性评估和补充建议
- **材料完整性评估**：支持比对需求方材料清单与实际收到材料，评估材料质量，输出完整性结论（完整 / 部分缺失 / 需要客户补充）
- **案件上下文分析段落**：当用户提供了案件上下文时，每个文件夹的 `材料说明` 末尾追加 `## 案件上下文` 段落，解释材料在案件中的整体角色和获取目的
- **需求方材料清单作为上下文来源**：上下文读取策略新增第5优先级——用户提供的需求方材料清单，用于完整性比对
- **综合分析模板**：新建 `references/comprehensive-analysis-template.md`

### 改进

- **材料说明文件命名**：从 `材料说明.md` 改为 `{文件夹名称} - 材料说明.md`，确保文件被复制到其他位置后仍可识别来源
- **标准输出表格**：新增 `{源目录名称} - 材料综合分析.md` 作为标准输出之一
- **步骤控制表格**：更新为包含 Step 5.5 的步骤范围
- **交付前检查**：新增文件命名前缀检查、综合分析完整性检查、案件上下文检查项
- **版本号**：统一更新为 v0.8.0

### 文档完善

- 更新 `SKILL.md`：新增 Step 5.5、案件上下文分析段落、文件命名规则、上下文读取策略第5优先级
- 更新 `references/output-template.md`：新命名规则、综合分析文件、更新版本号
- 更新 `references/material-processing-checklist.md`：新增综合分析和完整性评估检查项
- 新建 `references/comprehensive-analysis-template.md`

## [0.7.0] - 2026-05-18

### 改进

- 明确 `legal-material-organizer` 是内容理解和材料治理层，不承担长期任务事实源。
- 新增与 `content-registry` 的交接说明：原始材料、OCR/转写/清洗变体、材料说明、标签和任务候选分别写入对应表。
- 明确从材料中发现的后续动作只生成 `TaskCandidate`，后续交给 `task-policy` 决定是否进入 Discord 或 Git。

## [0.6.0] - 2026-05-17

### 新增

- 新增“双层输出”机制：源材料目录保留 `材料清单.md` 和按需 `材料说明.md`，机器记录和过程文件统一进入 Skill `archive/`。
- `scan_materials.py` 新增 `--archive-dir`、`--no-write-md`、`--fresh` 参数。
- `materials_manifest.json` 扩展为核心机器记录，新增文件指纹、生命周期状态、通用分类、处理字段、整理字段和复核字段。
- 新增增量扫描能力：二次扫描同一源目录时复用未变化文件编号，新增文件顺延编号，缺失文件标记为 `missing`。
- 新增 `run_meta.json` 保存运行参数、Skill 版本、源路径和 archive 路径。
- 新增 `scripts/test_scan_materials.py` 覆盖双层输出、增量编号、压缩包解压位置和恶意 tar 路径拒绝。

### 改进

- 压缩包解压结果改为写入本次 archive 的 `processed/extracted_containers/`，不再写入源材料目录。
- `archive/` 增加本地忽略规则，只保留 `.gitkeep` 和 `.gitignore`，避免运行记录进入 Git。
- 加固 zip/tar 解压安全，拒绝绝对路径、`..` 路径、符号链接、硬链接和设备文件。
- 文档中的 OCR/视觉理解调用改为松耦合能力描述，不再直接绑定其他 Skill 的内部脚本路径或特定 MCP 工具名。
- 将 `材料说明.md` 的“案件价值”表述调整为“可能关联（待人工确认）”，避免越界输出法律结论。

### 文档完善

- 更新 `SKILL.md`、`references/output-template.md`、`references/material-processing-checklist.md`、`references/organization-and-naming-rules.md`。
- 记录双层输出与 archive 主记录决策。

## [0.5.0] - 2026-05-15

### 新增

- **"理解驱动"核心理念**：整理的前提是理解，先 OCR + 注解，再归类命名
- **7 步工作流**：扫描 → 编号 → 内容提取 → 材料说明 → 文件夹摘要 → 归类整理 → 输出交付
- **OCR + 视觉理解双通道**：图片/截图/扫描件同时走环境可用 OCR 能力和视觉理解，合并结果生成更完整的注解
- **每个文件夹一个 `材料说明.md`**：一个文件覆盖该文件夹所有材料，包含 AI 生成声明
- **按需注解机制**：自解释文件（证书、合同、判决书）只 OCR，需上下文文件（投诉截图、聊天记录）追加解释性注解
- **上下文读取策略**：处理文件夹前读取父级和关联兄弟文件夹的 `材料说明.md`，提升注解质量
- **并行处理策略**：按文件夹分组启动多个 agent 并行处理，加速批量材料处理
- **步骤控制**：用户可通过自然语言控制执行哪些步骤（"不用整理"、"只要 OCR"等）
- **案件上下文注入**：可选的案件类型、当事人、核心争议、材料角色输入
- **`scan_materials.py` 新增字段**：`MaterialRecord` 增加 `ocr_output_path`、`ocr_status`、`annotation_summary`、`annotation_keywords`、`annotation_case_relevance`

### 改进

- **输出自包含**：所有输出文件直接放在源材料目录内部，不再创建 `整理输出/` 子目录
- **文件名中文化**：`00-材料清单.md` → `材料清单.md`，`_文件夹注解.md` → `材料说明.md`
- **OCR 路由统一**：所有图片/PDF/Word/PPT 统一交给环境可用 OCR 能力，视频使用 ASR 能力
- **可用能力表更新**：视觉理解从"OCR 失败时回退"升级为与 OCR 并行的正式通道

### 文档更新

- 重写 `SKILL.md`，从 5 步扩展到 7 步工作流
- 重写 `references/output-template.md`，新增 `材料说明.md` 模板和 v0.5.0 manifest 结构
- 重写 `references/material-processing-checklist.md`，新增双通道路由表、注解判断表、上下文读取检查项
- 记录 v0.5.0 升级决策

## [0.4.1] - 2026-04-23

### 改进

- 将“重命名计划”从标准留存输出调整为 AI 执行整理时的内部命名工作表。
- 标准整理包不再默认保留 `01-重命名计划.md`，改为通过 `materials_manifest.json` 和 `01-整理目录结构.md` 记录实际整理结果。
- 明确不得用 Agent 的 Plan 模式替代材料整理交付物，Plan 模式仅用于代理自身执行管理。

### 文档完善

- 更新 `SKILL.md`、`references/output-template.md`、`references/organization-and-naming-rules.md`、`references/material-processing-checklist.md` 和 `references/material-source-matrix.md`。

### 待办事项

- 为 `scan_materials.py` 增加基于内部命名工作表创建 `organized/` 整理副本的能力。
- 在 manifest 中补充整理后路径、最终文件名、命名依据、识别方式和确认状态字段。

## [0.4.0] - 2026-04-22

### 新增

- 新增 `references/organization-and-naming-rules.md`，定义材料识别、命名、重命名计划和整理目录规则
- 标准输出新增 `01-重命名计划.md`、`02-整理目录结构.md`、`03-预处理记录.md`

### 改进

- 收口 `SKILL.md` 职责边界：本技能聚焦材料清洗、识别、命名和归类，不承担案件事实分析
- 将图片、截图、扫描件、PDF 的处理目标调整为“识别内容并用于命名 / 归类”
- 将工具调用写成抽象能力选择，不绑定具体视觉识别、OCR 或转写工具

### 技术优化

- 默认采用先生成重命名计划、再确认执行的安全流程
- 默认创建 `organized/` 整理副本目录，不覆盖原始文件

### 待办事项

- 为 `scan_materials.py` 增加 `01-重命名计划.md` 初始生成能力
- 支持按重命名计划创建 `organized/` 副本目录

## [0.3.0] - 2026-04-10

### 新增

- 新增 `scripts/scan_materials.py`，支持目录扫描、初始编目和双格式输出
- 新增 `materials_manifest.json` 作为机器可读的材料清单

### 改进

- 自动记录压缩包拆包后的父子来源关系
- 支持对目录、单文件、常见压缩包进行统一扫描入口
- 为 `rar` / `7z` 增加可选系统解压支持说明

### 技术优化

- 首版脚本仅依赖 Python 标准库，降低环境门槛
- 增强输出模板，使 Markdown 清单与 JSON manifest 保持一致

### 待办事项

- 增加内容级摘要而不只是文件级编目
- 将 OCR / 转录 / 网页正文读取接入下一层自动编排

## [0.2.0] - 2026-04-09

### 新增

- 新增 `references/material-source-matrix.md`，系统梳理容器类与文件类材料来源
- 在 `references/output-template.md` 中新增“父级材料 / 容器来源关系”模板

### 改进

- 扩展 `SKILL.md`，显式纳入案件目录、压缩包、导出包、视频、邮件、表格、演示文稿、结构化导出等材料来源
- 将材料输入模型升级为“容器 + 文件”双层结构
- 扩展 `references/material-processing-checklist.md`，新增容器类材料处理表与更多文件类型

### 技术优化

- 强化“解压 / 拆包后保留父子来源关系”的要求
- 将录屏、邮件附件、Excel 多工作表、JSON / XML 导出纳入整理边界

### 待办事项

- 增加自动拆包与来源关系建档脚本
- 用脱敏混合材料包验证新增输入类型的整理效果

## [0.1.0] - 2026-03-26

### 新增

- 建立技能级 `CHANGELOG.md`、`DECISIONS.md`、`TASKS.md`、`LICENSE.txt`
- 新增 `references/output-template.md`，定义标准整理包输出结构
- 新增 `references/material-processing-checklist.md`，统一多类型材料处理清单
- 新增 `archive/.gitkeep`，预留集中归档目录

### 改进

- 重写 `SKILL.md`，明确技能定位、适用边界、标准输出和质量要求
- 将固定桌面路径改为“源目录优先、`archive/` 回退”的输出策略
- 将硬编码的外部脚本调用改为“按环境调用现有 skill / 工具”的协作说明

### 技术优化

- 标准化输出为 `00-材料清单` 到 `04-案件材料梳理报告` 的整理包
- 统一缺失信息标记规则：`未提及`、`待补充`、`需人工核验`
- 强化来源追溯要求，要求关键事实尽量附材料编号

### 待办事项

- 增加自动生成材料清单的脚本
- 增加匿名混合材料样例整理包
- 在复杂混合材料上做回归验证
