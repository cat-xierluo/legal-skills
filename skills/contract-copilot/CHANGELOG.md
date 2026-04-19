# 变更日志

本文档记录 Contract Copilot 的重要变更。

## [1.4.50] - 2026-04-09

### 改进

- 解除“审查口径”和“正文落痕策略”的强绑定：`克制 / 常规 / 强势` 现在只影响风险识别与结论表达强弱，不再直接映射为 `comment-first / balanced / revise-first`。
- 未显式指定 `edit_policy` 时，自动分流默认仍保持 `revise-first`，因此即便本轮口径偏克制，对高确定性问题也仍可直接修订。

### 修复

- 修复低口径场景被机械收敛成“只批注、不改文”的行为偏差，避免审查尺度被错误等同于正文是否可修改。
- 修复历史 `review_memory.json` 中旧版 `edit_policy` 记忆会继续影响当前默认落痕策略的问题。

### 技术优化

- `review_runtime.py` 现将 `review_intensity` 与 `edit_policy` 独立解析，只接受显式 `--edit-policy` 或 `meta.edit_policy` 覆盖。
- 补充回归测试，覆盖“低口径仍可保持默认直接修订策略”和“历史记忆不再偷偷带回旧动作策略”两条路径。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`ARCHITECTURE.md`、`ROADMAP.md`、`TASKS.md` 与 `DECISIONS.md`，统一“口径独立、落痕独立”的运行语义。

## [1.4.49] - 2026-04-09

### 改进

- 收紧审查人身份确认规则：首次使用时，如果 `reviewer_profile.json` 缺少姓名或机构，仍然必须先询问并写入后再继续运行。
- 新增当前环境确认门槛：即使本地已经存在姓名 / 机构，只要该配置尚未在当前环境完成确认，交互模式下也会先要求确认一次，再继续执行。
- 明确不应根据 skill 作者、仓库 owner、历史样例或其他上下文静默推断审查人姓名和单位。

### 修复

- 修复“配置文件里已有值就直接继续”带来的静默代填风险，避免新环境或遗留本地配置在未经确认时直接进入法律文书输出。

### 技术优化

- `review_runtime.py` 现为审查人配置新增 `confirmed` 状态，并补充交互式确认逻辑。
- 新增回归测试，覆盖“空配置时交互补录”和“已有但未确认配置时交互确认”两条路径。

### 文档完善

- 更新 `config/reviewer_profile.example.json`、`SKILL.md`、`README.md`、`scripts/README.md`、`TASKS.md` 与 `DECISIONS.md`，统一新的首次确认口径。

## [1.4.48] - 2026-04-09

### 改进

- 明确 IM 渠道语义：当合同任务由飞书或其他 IM 对话发起，且合同文件由该对话直接传入时，默认把原对话视为任务布置与成果交付的同一渠道。
- 明确最终回传口径：审核修订版 DOCX 与审查报告 DOCX 默认都应回传到原 IM 对话，不再只默认本地落盘或仅回复文件路径。
- 增加保底规则：若当前运行时没有附件发送能力，需要显式说明“文件已生成但尚未完成会话回传”，避免把未发送状态误表述为已交付。

### 文档完善

- 更新 `SKILL.md`、`README.md`、`ARCHITECTURE.md`、`TASKS.md` 与 `DECISIONS.md`，同步本次 IM 渠道交付规则。

## [1.4.47] - 2026-04-09

### 新增

- 新增 `references/setup-dependencies.md`，集中说明 `contract-copilot` 的目录依赖、Python 包依赖、可选系统依赖、推荐安装顺序与常见报错排查。
- 新增 `scripts/requirements.txt`，固化当前 Python 运行依赖 `defusedxml` 与 `lxml`，便于外部使用者直接执行 `pip install -r`。

### 改进

- `README.md`、`SKILL.md` 与 `scripts/README.md` 现在统一指向同一份依赖入口，不再把运行前提分散在脚本注释和零散说明中。
- 明确 `docx/` 为同级必需 skill，`ooxml` 能力随 `docx` 一起提供，不需要额外单独准备第二个目录。

### 文档完善

- 更新 `TASKS.md` 与 `DECISIONS.md`，记录本次“依赖显式化 + reference 化”的背景、取舍与结果。

### 待办事项

- 后续如新增或删除 Python 包、系统命令或同级 skill 目录依赖，同步更新 `references/setup-dependencies.md` 与 `scripts/requirements.txt`。

## [1.4.46] - 2026-04-07

### 新增

- 新增 `scripts/run_apply_review_plan.ps1`，作为面向 Windows / 中文路径场景的薄包装器入口。
- 包装器现在会将 `input / plan / output / report / report-docx / log` staging 到 ASCII 临时目录后再调用 `apply_review_plan.py`，并在执行结束后把用户可见产物拷回原始目录。
- 新增 PowerShell 入口集成测试：在存在 `pwsh / powershell` 时，校验“中文路径输入 + PowerShell 包装器 + Python 主流程”的端到端链路；未安装 PowerShell 时自动跳过。

### 改进

- 将 Windows 兼容策略明确收敛到“包装器处理路径与运行时差异，Python 继续作为唯一审查执行链路”，避免再维护第二套文档操作逻辑。
- 默认 Word 审查意见书输出现在也经过包装器显式 staging，避免 `output_审查报告.docx` 这类默认衍生文件名在中文路径下直接暴露给 Python 主入口。
- 调整打包过滤规则：`dist/contract-copilot.zip` 现在会跳过 `.DS_Store`、`__pycache__`、`.pyc`、运行时 `archive/` 内容、`internal-notes/` 内部台账以及 gitignore 命中的本地配置，避免把缓存、归档、来源材料和本地记忆误打进发布包。

### 技术优化

- 为共享打包脚本补充回归测试，覆盖“跳过 transient 文件”“跳过 `internal-notes/`”“跳过 gitignore 本地配置”三类场景；重新打包后，当前 `contract-copilot.zip` 已收敛为仅包含技能本体和必要示例文件。

### 文档完善

- 更新 `README.md` 与 `scripts/README.md`，补充 PowerShell 包装器调用示例、适用场景和 WPS 人工验证建议。
- 更新 `TASKS.md` 与 `DECISIONS.md`，记录本次“兼容层增强而不改方法层”以及“打包发布面清理”的取舍。

### 待办事项

- 在真实 Windows + WPS Office 环境完成一次人工冒烟验证，确认中文路径下的修订痕迹、批注和接受/拒绝修订功能显示正常。

## [1.4.45] - 2026-03-31

### 改进

- 将 `README.md` 从内部说明风格重写为面向外部使用者的项目型首页，收敛首页信息密度，重点保留“是什么、怎么装、怎么跑、会产出什么”。
- 新增面向 Claude Code 的两种安装口径：通过 `legal-skills` 技能集安装，以及手动复制 `contract-copilot/` 目录安装。
- 新增面向 OpenClaw 与其他本地运行时的通用导入说明，不再把 README 写成仅供当前仓库内部使用的文档。
- README 中补充首次配置、审查人配置、审查上下文记忆、快速开始、默认输出物和常见说明，降低外部使用门槛。

### 文档完善

- 修正 `README.md` 中 `config/` 树状结构的 ASCII 漂移，确保 `example` 文件与运行时文件的展示层级正确。
- 清理 `TASKS.md` 中与当前目录结构冲突的旧描述，不再保留“删除 config 目录”这类过时表述。
- 更新 `DECISIONS.md` 与 `TASKS.md`，同步记录本次“README 项目化改写 + 配置文档治理”的背景和结果。

## [1.4.44] - 2026-03-31

### 新增

- 新增 `config/review_memory.example.json`，作为“客户名称 / 审查立场 / 审查口径”本地记忆模板。
- `apply_review_plan.py` 新增 `--client-name`、`--party-role`、`--review-intensity` 参数，支持显式覆盖本次审查上下文。
- 新增运行时“审查上下文记忆”能力：按合同名记录客户名称、立场与口径，后续命中同名合同可自动回填。

### 改进

- 将“审查口径”正式接入动作分流：`克制 -> comment-first`、`常规 -> balanced`、`强势 -> revise-first`，不再只是文档层概念。
- `apply_review_plan.py` 现在会在执行前统一解析客户名称、立场与口径，并将其写入执行日志和审查意见书。
- 审查意见书首页新增“客户名称”和“审查口径”字段，方便后续留痕和复核。
- 交互模式下，若用户未说明客户名称、立场或口径，会先询问；非交互脚本场景则优先复用历史记录并保持既有默认执行口径兼容。

### 技术优化

- `review_runtime.py` 扩展为“审查人配置 + 审查上下文记忆 + 时间线”统一运行时模块。
- 新增回归测试，覆盖审查上下文记忆落盘、历史命中回填，以及执行入口写入 `review_context` 的场景。

### 文档完善

- 更新 `SKILL.md`、`README.md`、`scripts/README.md`、`ARCHITECTURE.md`、`templates/审查报告模板.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步新的审查上下文确认与本地记忆机制。

## [1.4.43] - 2026-03-26

### 改进

- 在 `action_executor.py` 中新增“仅写入意见书（report-only）”第三通道，不再把所有识别出的风险都直接落到 Word 修订或批注里。
- 收紧默认执行口径：`revise-first` 仍保留“确定性问题优先直接改”的总体方向，但会先过滤掉程序优化型、说明型、低必要性条款；这类问题默认改为“仅写入意见书”或“保留批注”，不再直接改正文。
- 修正显式 `replace` 与 `deterministic_edit` 的耦合误伤：不再因为上游计划把某条风险写成 `replace`，就自动视为必须正文直改。
- 收紧“轻微文字修订”识别条件：只有目标文本本身足够短时，才把“5日/5天、编号、标点”类问题视为轻微 clerical 修订，避免长条款因包含此类字样被误判为应直接修订。
- 扩展占位识别边界：`邮箱`、`待补` 等待填信息现在会稳定回退为就地批注，而不是误沉到“仅意见书”。
- 基于同一份设计委托合同样张多轮重跑收束：当前 `v16` 样张相较 `v11`，已从 `53` 处插入 / `51` 处删除 / `19` 条批注，收敛到 `9` 处插入 / `7` 处删除 / `14` 条批注，并将 `11` 项优化型问题退出 Word 页面，仅保留在意见书。

### 新增

- 新增回归测试，覆盖 `report-only` 动作、长条款不再误判为轻微 clerical、邮箱占位项回退批注、P1 优化型条款退出 Word 正文等场景。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`references/revision-strategy.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步“修订 / 批注 / 仅意见书”三段分流的新口径与版本号。

## [1.4.42] - 2026-03-26

### 新增

- 新增 `ARCHITECTURE.md`，将 `contract-copilot` 正式固定为“立场与授权 / 方法论 / 知识清单 / 动作收束 / 文档执行 / 交付呈现 / 治理与验证”七层总纲。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，将七层模型接入现有入口文档，避免继续只散落在对话和局部说明中。

## [1.4.41] - 2026-03-26

### 改进

- 新增“审查密度收敛”规则：复杂条款的多段最小差异修订现在会优先合并过碎的微小修改岛，避免同一条款炸出十几个单字级 `w:del / w:ins`，审阅视图更接近律师人工修订。
- 保留局部修订能力的同时，新增可读性上限：若同一条替换会拆成过多可见修订块，执行器会自动收敛成更少、更成组的修改痕迹，而不是继续展示低价值的标点/单字级碎改。
- 新增显式占位兜底：即使 `review-plan.json` 错把留空项写成 `replace`，运行时也会自动降为 `comment`，避免把负责人、联系方式、附件等待填信息直接代填进合同。
- 修正占位识别误判边界：现在只有描述字段明确指向“留空/待填”，或目标文本本身真的包含占位符时，才会降为批注；不会再因为正常条款里出现“负责人”等普通词语就误把实质修订打回批注。

### 新增

- 新增回归测试，覆盖“显式 `replace` 的留空项自动降为批注”“含 `负责人` 普通表述的非留空条款仍保持直接修订”“复杂长条款自动收敛为更少修订块”等场景。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`references/revision-strategy.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步新的审查密度收敛规则与版本号。

## [1.4.40] - 2026-03-26

### 改进

- 调整 Word 审查时间线为两层错峰：同一条审查意见内部，每个实际落到 Word 的修订/批注批次默认相隔 `1-2` 分钟；不同审查意见之间继续保持 `5-10` 分钟的大间隔。
- 修正批注写入链的时间消费方式：同一条批注在 `comments.xml`、`commentsExtended.xml`、`commentsExtensible.xml` 等内部文件写入时，统一共用同一个逻辑时间，不再因为底层 OOXML 多次落盘而被意外拉长。

### 新增

- 新增时间线单测，覆盖“同一 finding 内 1-2 分钟步进 + finding 之间 5 分钟以上间隔”。
- 新增真实 DOCX 集成测试，直接校验“同一条 replace 后附带 comment”时，批注时间会晚于修订时间 `1-2` 分钟。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步新的两层错峰时间线规则与版本号。

## [1.4.39] - 2026-03-26

### 改进

- 收紧 Word 审查意见书版式密度：左右页边距由 `1800` 收窄到 `1440`，正文与元信息段落行距、段前段后距同步压缩，整体页感更接近 Alpha 样张的正式意见书。
- 调整“详细审查意见”表格布局：标签列收窄、内容列加宽，表格行距压到 `260`，单元格上下内边距归零、左右内边距收窄，减少不必要换行与空白。
- 每条详细意见后的空段改为更紧的表格间距，不再额外拉长全文页数。

### 新增

- 新增 Word 报告回归断言，校验紧凑版式下的页边距、表格行距与单元格内边距参数。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步“紧凑型审查意见书版式”能力与版本号。

## [1.4.38] - 2026-03-26

### 改进

- 将最小差异修订从“单个中段替换”升级为“多段差异修订”：同一条款中存在多处改动时，会尽量拆成多组局部 `w:del / w:ins`，而不是继续生成一个很长的中段重写块。
- `reviewer.py` 现在基于多段 diff 生成段内修订片段；复杂长条款在存在多个稳定相同片段时，会优先保留这些不变片段，只对变化点逐处落痕。
- 真实样张验证显示，设计委托合同 `v7` 的平均删除块长度已从 `53.3` 字降到 `6.0` 字，平均插入块长度已从 `68.9` 字降到 `9.3` 字，审阅视图显著更接近人工逐句修订。

### 新增

- 新增真实 DOCX 集成测试，覆盖“同一条款内多处差异拆成多个小修订块”的场景，确保复杂句子不会再默认收敛成单个大替换块。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步“多段最小差异修订”能力与版本号。

### 待办事项

- 继续优化复杂长条款的样式碎片保留与超长替换块收敛，进一步缩小与 Alpha 样张在极复杂条款上的观感差距。

## [1.4.37] - 2026-03-26

### 改进

- 审查修订链路新增“首轮最小差异修订”能力：同一 `w:r` 内的短语替换/删除会优先拆成局部 `w:del` / `w:ins`，不再默认整条 run 删除后重写。
- 当目标文本跨多个 `w:r` 时，执行器会优先退到“段落内局部片段修订”，只对命中的短语片段生成修订痕迹，而不是整段删掉重写。
- `apply_review_plan.py` 的执行日志文案同步区分“已完成局部替换 / 已完成局部删除”与“已按段落级重写”，便于判断本次落地颗粒度。

### 新增

- 新增真实 DOCX 集成测试，覆盖同一 run 内短语替换、跨 run 片段替换和局部短语删除三类最小差异修订场景。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`references/revision-strategy.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步“首轮最小差异修订”能力与版本号。

### 待办事项

- 继续优化复杂长条款的局部拼接与样式保留，减少大段替换在审阅视图中的存在感。

## [1.4.36] - 2026-03-25

### 改进

- 默认对外交付的审核版 DOCX 收敛为“修订批注一体版”：确定性问题继续直接修订，留空项/事实待补项保持批注，重大直接修订默认附带解释性批注。
- 自动批注模板参考 Alpha / 智合 样式调整为 `风险等级 / 风险点 / 条款位置 / 说明 / 修改建议 / 可选建议措辞`，降低“技术提示味”，更接近律师审阅表达。
- 审查意见书结构参考 Alpha 的正式出件方式升级为“致函开篇 + 合同概况 + 综合审查意见 + 重要风险提示 + 详细审查意见 + 声明 + 出具信息”，更贴近对客法律意见书。

### 新增

- 新增回归测试，覆盖“留空项保持 comment-only”“重大直接修订同时保留批注说明”“正式意见书结构包含重要风险提示与声明”等场景。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`references/revision-strategy.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步新的修订批注一体版口径与意见书结构。

### 待办事项

- 继续细化最小差异修订能力，减少整条 `replace` 与段落级 fallback 带来的大块修订痕迹。

## [1.4.35] - 2026-03-25

### 新增

- 新增 `references/revision-strategy.md`，将“直接修订 / 局部删减 / 局部补入 / 整条重写 / 仅作批注”的展现策略单独沉淀为方法层文件。

### 改进

- 明确留空项、事实待补项、授权不明的商务取舍项默认只批注，不直接代填。
- 明确准确的法条引用默认不因篇幅较长而删减，只有错误、过时、冲突或误导时才修改。
- 明确修订动作内部遵循“局部删减 / 局部补入优先于整段重写”的默认口径。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`references/review-framework.md`、`references/priority-clauses.md`、`scripts/README.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步新的方法层文件与版本号。

## [1.4.34] - 2026-03-25

### 改进

- Word 审查意见书中的无序列表与编号列表改为 OOXML 原生列表，不再只是“圆点字符 + 普通段落”的模拟样式，层级显示更稳定。
- “具体审查意见”段落改为表格化展示：每条意见以独立表格呈现标题、风险等级、条款位置、风险概述、审查意见、原条款、建议修改和法律依据，更接近正式律师出件样式。

### 新增

- 新增 Word 报告回归断言，校验 `numbering.xml`、原生列表关系和具体审查意见表格块均已写入 DOCX。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步新的报告渲染样式与版本号。

## [1.4.33] - 2026-03-25

### 修复

- 修正 Word 批注/修订时间戳的时区策略：现在会先读取本机当前时区与本地时间，再向后错峰写入，`w:date` 使用本地时区偏移格式，避免显示出 UTC 时间或错误时区时间。
- 保留 `w16du:dateUtc` 等 UTC 扩展字段，兼顾 Word 显示效果与底层 OOXML 兼容性。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步“本机时区优先”的时间线说明与版本号。

## [1.4.32] - 2026-03-25

### 改进

- 升级 Word 版审查意见书的默认版式，吸收“法律服务方案”预设中的深蓝标题、仿宋正文、浅底元信息卡和棕色标签高亮，输出更接近正式律师交付件。
- 为 Word 意见书补入页脚页码、统一的 1.5 倍行距和更清晰的章节层级，保持 OOXML 直出路径不变。

### 新增

- 新增版式回归测试，校验 Word 报告中的分区底色、字体配置和页脚页码部件。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步新的 Word 意见书版式说明与版本号。

## [1.4.31] - 2026-03-25

### 改进

- 对外报告从“风险清单式审查报告”进一步收敛为更接近律师交付件的“审查意见书”体例：前部先写合同概况与综合审查意见，后部再按正式意见逐项展开。
- 具体审查意见现在按单项问题逐条展开，并补入“原条款 / 建议修改 / 法律依据”等字段，便于客户和律师直接对照使用。
- Word 报告元数据标题同步调整为“审查意见书”口径。

### 新增

- 新增回归测试，覆盖新的意见书结构、Word 正文标题和端到端报告内容断言。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`templates/审查报告模板.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步新的意见书体例说明。

## [1.4.30] - 2026-03-24

### 修复

- 修正审查时间线生成逻辑：批注与修订的时间戳不再向前倒推，而是以本次命令执行时点为起点，仅向后顺延。
- 补充回归校验，确保写入到 Word 的批注和修订时间不会早于命令实际启动时间。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步新的时间线语义。

## [1.4.29] - 2026-03-24

### 改进

- 默认自动分流策略调整为 `revise-first`：能形成明确改文的审查项，优先直接修订，而不是仅留批注。
- 在 `revise-first` 下，若审查项已提供可直接落文的 `recommended_text`，即使未显式给出 `replacement_text`，也会优先提升为直接替换文本。
- 保留 `balanced` 与 `comment-first` 两种回退策略，便于在不同审查风格之间切换。

### 新增

- 新增 `--edit-policy` 参数，并支持在计划的 `meta.edit_policy` 中显式声明自动分流策略。
- 新增回归测试，覆盖 `recommended_text` 直转修订、`comment-first` 保守回退，以及 CLI 默认采用 `revise-first` 的执行链路。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md` 与根目录 `README.md`，同步新的“改文优先”执行口径。

## [1.4.28] - 2026-03-24

### 改进

- 审查报告调整为“合同概要速览 + 综合审查意见 + 风险清单”的阅读顺序，方便客户和审查人先快速理解合同基本面与总体结论。
- 执行命中率、失败项和其他内部质量统计默认不再写入对外报告，仅保留在 `*_执行日志.json`。
- 自动生成的批注格式升级为多行结构化模板：`风险等级 / 问题类型 / 风险说明 / 处理建议 / 可选建议措辞`。

### 新增

- 扩展审查计划 `summary` 字段示例，支持 `contract_type`、`parties`、`contract_amount`、`contract_term`、`business_overview`、`key_milestones` 等报告速览字段。
- 新增回归测试，覆盖新的报告前置结构与自动批注模板。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`templates/审查报告模板.md`、`TASKS.md`、`DECISIONS.md` 与根目录 `README.md`，同步新的报告结构和批注格式说明。

## [1.4.27] - 2026-03-24

### 改进

- 调整 `apply_review_plan.py` 的默认交付边界：用户目录现在只保留审核修订版 DOCX 与 Word 审查报告。
- Markdown 审查报告、执行日志和审查计划副本默认不再外露到用户目录，而是直接沉淀到 `archive/<时间戳_合同名>/`。
- 保留 `--no-archive` 作为调试模式：关闭归档时，Markdown 报告和执行日志仍会直接输出到当前目录。

### 新增

- 新增归档模式集成测试，覆盖“默认只对外交付两个 DOCX，其余过程文件进入 archive/”场景。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`TASKS.md`、`DECISIONS.md` 与根目录 `README.md`，同步新的交付边界与归档说明。

## [1.4.26] - 2026-03-24

### 新增

- 新增 `scripts/review_runtime.py`，统一管理审查人本地配置与审查时间线。
- 新增 `config/reviewer_profile.example.json`，作为审查人本地配置模板。
- 首次执行 `apply_review_plan.py` 时，支持交互录入审查人姓名、律所/公司名称和可选部门，或在首次显式传入 `--author` / `--organization` 时自动写入 `config/reviewer_profile.json`。
- 新增真实 DOCX 集成测试，覆盖“审查人配置落盘 + 批注/修订时间戳错峰写入”场景。

### 改进

- 写入 Word 的批注与修订默认按 5 到 10 分钟区间错开时间戳，降低整批审查意见在同一分钟内落地的机械痕迹。
- `docx/scripts/document.py` 与 `scripts/reviewer.py` 新增可注入时间戳能力，使批注、修订、回复批注共用同一条审查时间线。
- Markdown / Word 审查报告现在会复用同一份审查人配置，统一展示审查人、所属机构/公司和所属部门。
- 若本地配置缺少姓名或机构信息，脚本不再静默回退默认值，而是要求先补全配置。
- 取消 initials 自动生成；若本地配置未填写 initials，则不会再自动推导，也不会把 `w:initials` 写入 Word 批注。
- Word 批注作者显示调整为 `姓名｜机构`，例如 `杨卫薪律师｜剑桥颐华律师事务所`。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md`，同步审查人配置、报告署名和时间戳行为说明。

### 待办事项

- 继续把 `references/priority-clauses.md` 扩充为按 12 类细化的速查页。
- 继续按目录补充房地产、建设工程、公司投资的细分起草条款模块。
- 继续推进 marketplace 版本同步。

## [1.4.21] - 2026-03-24

### 改进

- 调整 `scripts/apply_review_plan.py` 的执行语义：若存在未成功落地到 Word 的审查项，脚本仍保留输出文件，但会以非零退出码结束，避免上层流程误判为“全部成功”。
- 强化文本定位稳健性：支持 `occurrence` 指定重复文本的命中位置，并在 `replace/delete` 遇到跨 `w:r` 拆分文本时回退到段落级重写。
- 审查报告现在逐项回写执行状态与执行说明，区分“识别出的风险”和“实际落地的文档修改”。

### 新增

- 新增 `scripts/report_docx.py`，使用 OOXML 直接生成 Word 版审查报告。
- `apply_review_plan.py` 默认新增输出 `*_审查报告.docx`。
- 新增真实 DOCX 集成测试，覆盖歧义定位失败、跨 `w:r` 替换成功和 Word 报告产出。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`scripts/README.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md`，同步新的执行语义、定位说明和报告产物。

### 待办事项

- 继续把 `references/priority-clauses.md` 扩充为按 12 类细化的速查页。
- 继续按目录补充房地产、建设工程、公司投资的细分起草条款模块。
- 继续推进 marketplace 版本同步。

## [1.4.20] - 2026-03-24

### 改进

- 将 `references/` 重组为“入口文件 + contract-types”结构：根层保留 `review-framework.md`、`contract-routing.md`、`priority-clauses.md`，12 类合同主文件统一收进 `references/contract-types/`。
- 将原 `references/12类合同全量映射清单.md` 重命名为 `references/contract-routing.md`，降低顶层结构的目录同构感，同时保留审查分流与起草路由能力。
- 新增 `references/priority-clauses.md` 作为审查入口层的总控速查页。

### 文档完善

- 更新 `SKILL.md`、`README.md`、`ROADMAP.md`、`TASKS.md`、`DECISIONS.md`，同步新的目录结构与调用顺序。

### 待办事项

- 继续把 `references/priority-clauses.md` 扩充为按 12 类细化的速查页。
- 继续按目录补充房地产、建设工程、公司投资的细分起草条款模块。
- 继续推进 marketplace 版本同步。

## [1.4.19] - 2026-03-22

### 改进

- 扩充 `references/12类合同全量映射清单.md` 的起草能力，新增“推荐交付包型”“起草分流问题与必带文件”“起草骨架优先顺序”等内容，让映射清单可直接产出起草路由卡。
- 将 `templates/合同起草信息清单.md` 从简单事实清单升级为“起草工作台”，承接主文件、文件包、待补事实、程序性前提和待确认问题。
- 更新 `SKILL.md` 与 `README.md` 的起草流程说明，明确起草交付至少包含“起草路由卡 + 条款骨架 + 待确认问题表”。

### 待办事项

- 建立 12 类合同“优先审查条款”速查页。
- 继续按目录补充房地产、建设工程、公司投资的细分起草条款模块。
- 继续推进 marketplace 版本同步。

## [1.4.18] - 2026-03-22

### 改进

- 从 12 类合同主文件中抽取首批高频共性起草条款，补强 `templates/条款库.md`，新增文件优先级、交付与验收、配合义务、条件成就与长停、通知送达、责任限制及例外等通用结构模块。
- 重写 `templates/条款库.md` 中的知识产权条款，区分背景知识产权、定制成果、第三方素材与侵权责任，减少“一刀切归属”带来的起草偏差。
- 新增里程碑与阶段验收、交割条件与交割清单两组专项条款，补足技术开发、建设工程、投资和资产交易场景的起草支撑。

### 文档完善

- 更新 `SKILL.md`、`README.md`、`TASKS.md`、`DECISIONS.md`，同步条款库的当前定位和任务进度。

### 待办事项

- 建立 12 类合同“优先审查条款”速查页。
- 继续按目录补充房地产、建设工程、公司投资的细分起草条款模块。
- 继续推进 marketplace 版本同步。

## [1.4.17] - 2026-03-22

### 新增

- 新增 `templates/合同起草信息清单.md`，用于在起草前固定主合同类型、配套协议类型、待补事实和程序性前提。

### 改进

- 将 `references/12类合同全量映射清单.md` 从“审查分流索引”扩展为“审查 / 起草双用途入口”，补入 12 类合同的起草调用速查信息。
- 更新 `SKILL.md` 与 `README.md` 的起草流程说明，明确起草链路为“通用框架 -> 映射清单 -> 起草信息清单 -> 合同主文件 -> 条款库”。
- 更新 `templates/条款库.md` 的定位说明，明确其只负责提供通用候选措辞，不替代映射清单和主文件确定合同骨架。

### 待办事项

- 建立 12 类合同“优先审查条款”速查页。
- 从 12 类合同主文件中抽取高频共性条款，持续迭代 `templates/条款库.md`。
- 继续推进 marketplace 版本同步。

## [1.4.16] - 2026-03-22

### 文档完善

- 删除重复的根层文档 `审查原则.md` 与 `优化说明.md`。
- 明确将审查方法统一收口到 `SKILL.md`，将优化过程与结果统一收口到 `CHANGELOG.md`、`ROADMAP.md`、`TASKS.md` 与 `DECISIONS.md`。

### 待办事项

- 建立 12 类合同“优先审查条款”速查页。
- 从 12 类合同主文件中抽取高频共性条款，持续迭代 `templates/条款库.md`。
- 继续推进 marketplace 版本同步。

## [1.4.15] - 2026-03-22

### 改进

- 将 `references/00-通用框架.md` 重命名为 `references/review-framework.md`。
- 将 `references/01-12类合同全量映射清单.md` 重命名为 `references/12类合同全量映射清单.md`。
- 保留 12 类合同目录编号，但去掉根层两个总控文件的序号前缀，降低命名冲突。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`TASKS.md`、`DECISIONS.md`、`templates/条款库.md` 及相关路径引用，统一新的文件名。

### 待办事项

- 建立 12 类合同“优先审查条款”速查页。
- 从 12 类合同主文件中抽取高频共性条款，持续迭代 `templates/条款库.md`。
- 继续推进 marketplace 版本同步。

## [1.4.14] - 2026-03-22

### 改进

- 将 12 类合同主文件目录从技能根目录移回 `references/` 根层，统一为同一套参考资料体系。
- 明确合同起草与合同审查共用 `references/review-framework.md`、`references/12类合同全量映射清单.md` 和 12 类合同主文件，不再额外平行维护另一套起草 reference。
- 重新定义 `templates/条款库.md` 的定位：作为从各类合同主文件中抽取的通用候选条款库，用于辅助起草，不替代对应类型主文件。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md`、`CLAUDE.md`、`优化说明.md` 与 `references/12类合同全量映射清单.md`，同步新的目录结构和起草调用顺序。

### 待办事项

- 建立 12 类合同“优先审查条款”速查页。
- 从 12 类合同主文件中抽取高频共性条款，持续迭代 `templates/条款库.md`。
- 继续推进 marketplace 版本同步。

## [1.4.13] - 2026-03-22

### 改进

- 将 `合同类型/` 目录从 `references/` 中移出，直接放到技能根目录，`references/` 只保留通用框架与映射清单。
- 同步更新 `README.md`、`SKILL.md`、`references/12类合同全量映射清单.md` 及协作文档中的当前路径说明，明确“通用参考资料”和“合同主文件”分层。

### 待办事项

- 建立 12 类合同“优先审查条款”速查页。
- 评估是否为映射清单补充机器可读格式（如 CSV/JSON）。
- 继续推进 marketplace 版本同步。

## [1.4.12] - 2026-03-22

### 改进

- 将 `references/01-引用导航.md` 与 `references/03-审查流程指引.md` 的核心内容并入 `SKILL.md`，不再单独保留短小说明文件。
- `references/` 根层现收敛为 `review-framework.md`、`12类合同全量映射清单.md`、`02-合同类型/`，只保留高复用硬资料。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`TASKS.md`、`DECISIONS.md`、`ROADMAP.md`、`CLAUDE.md`、`优化说明.md`，同步新的入口分工与目录结构。

### 待办事项

- 建立 12 类合同“优先审查条款”速查页。
- 评估是否为映射清单补充机器可读格式（如 CSV/JSON）。
- 继续推进 marketplace 版本同步。

## [1.4.11] - 2026-03-22

### 改进

- 为 `references/` 根层入口统一增加顺序编号，强化目录可扫性与调用顺序表达。
- 同步更新 `README.md`、`SKILL.md`、`引用导航.md`、`12类合同全量映射清单.md` 及协作文档中的路径引用，确保目录排序与调用顺序一致。

### 待办事项

- 建立 12 类合同“优先审查条款”速查页。
- 评估是否为映射清单补充机器可读格式（如 CSV/JSON）。
- 继续推进 marketplace 版本同步。

## [1.4.10] - 2026-03-22

### 改进

- 将 12 类合同目录整体下沉到 `合同类型/`，使 `references/` 根层更聚焦于审查框架、映射清单、引用导航和审查流程。
- 更新 `references/01-引用导航.md`、`references/12类合同全量映射清单.md`、`README.md`、`SKILL.md` 中的目录路径说明，统一新的主文件位置。
- 删除 `references/03-审查流程指引.md` 各阶段的分钟估计，避免使用人工审查时长去限定 AI 审查流程。

### 文档完善

- 更新 `TASKS.md`、`DECISIONS.md`、`ROADMAP.md`，记录目录层级调整与流程文档去时间化的当前口径。

### 待办事项

- 建立 12 类合同“优先审查条款”速查页。
- 评估是否为映射清单补充机器可读格式（如 CSV/JSON）。
- 继续推进 marketplace 版本同步。

## [1.4.9] - 2026-03-22

### 改进

- 删除 `references/专项议题适用索引.md` 与 4 份 `专项议题-*.md`，取消横向专题体系，`references/` 回归“引用导航 + 通用框架 + 映射清单 + 12 类主目录 + 流程指引”的主线结构。
- 重写 `references/01-引用导航.md` 与 `references/12类合同全量映射清单.md` 的调用说明，统一为“通用框架 -> 映射清单 -> 合同主文件 -> 流程指引”。

### 文档完善

- 更新 `README.md`、`SKILL.md`、`TASKS.md`、`DECISIONS.md`，同步去专题化后的当前结构与版本号。

### 待办事项

- 建立 12 类合同“优先审查条款”速查页。
- 评估是否为映射清单补充机器可读格式（如 CSV/JSON）。
- 继续推进 marketplace 版本同步。

## [1.4.8] - 2026-03-22

### 新增

- 新增 `references/01-引用导航.md`，将 `references/` 明确拆分为“基础规则层 / 类型路由层 / 合同主文件层 / 专题叠加层”四层入口。
- 新增 `references/专项议题适用索引.md`，统一记录专项议题的触发条件、优先叠加目录与常见组合。

### 改进

- 为 `references/review-framework.md`、`03-审查流程指引.md`、`12类合同全量映射清单.md` 以及 4 份专项议题文件补充结构化角色说明，明确各自的定位、输入输出与适用场景。
- 更新 `README.md` 与 `SKILL.md` 的调用顺序说明，改为“先看引用导航，再走映射与专题路由”的统一入口。

### 待办事项

- 建立 12 类合同“优先审查条款”速查页。
- 评估是否为映射清单补充机器可读格式（如 CSV/JSON）。
- 继续推进 marketplace 版本同步。

## [1.4.7] - 2026-03-22

### 改进

- 将 `合同类型/01-sale/`、`02-lease/`、`04-ip/`、`05-guarantee/`、`06-lending-gift/`、`07-internet/`、`08-marriage-family/`、`09-employment/`、`10-real-estate/`、`11-construction/`、`12-corporate-investment/` 下剩余 45 份旧模板重写为统一的“宏观/中观/微观 + 9 列字段表”结构。
- `references/` 下 64 份合同参考文件现已全部使用同一风险字段标准，并同步补齐推荐措辞、风险示例、整改建议等核心字段。

### 文档完善

- 更新 `TASKS.md`、`DECISIONS.md`、`README.md`、`SKILL.md`，记录本次全量标准化完成状态并同步版本号。

### 待办事项

- 建立 12 类合同“优先审查条款”速查页。
- 建立合同文件年度复核机制（条款有效性与实务可执行性）。
- 继续推进 marketplace 版本同步。

## [1.4.6] - 2026-03-22

### 改进

- 将 `合同类型/03-service/` 下 7 份旧模板重写为统一的“宏观/中观/微观 + 9 列字段表”结构：
  - `一般服务合同.md`
  - `中介合同.md`
  - `广告服务合同.md`
  - `承揽合同.md`
  - `物业服务合同.md`
  - `行纪合同.md`
  - `运输合同.md`
- 统一服务类合同的风险字段表达口径，补齐服务边界、验收流程、费用结算、知识产权、数据合规、退出交接等高频审查点。

### 文档完善

- 更新 `TASKS.md`、`DECISIONS.md`、`README.md`、`SKILL.md`，记录本次批次化内容标准化进展并同步版本号。

### 待办事项

- 继续按目录推进 `04-ip/`、`09-employment/`、`12-corporate-investment/` 等旧模板标准化。
- 继续推进 marketplace 版本同步。

## [1.4.5] - 2026-02-09

### 新增

- 新增 `scripts/enrich_review_plan.py`：在生成阶段自动补全审查项的 `needs_negotiation` / `deterministic_edit` 字段。
- 新增 `plan_loader.enrich_plan()` 与 `enrich_findings()`，统一计划字段补全入口。

### 改进

- `scripts/apply_review_plan.py` 默认在执行前自动补全计划策略字段，减少因标记遗漏导致的批注/修订分流偏差。
- 新增参数 `--no-enrich-plan`，可在需要严格复现原计划时关闭自动补全。

### 技术优化

- 扩展 `scripts/tests/test_plan_loader.py`，覆盖显式动作推断、显式字段保留、`auto` 关键词推断等路径。

### 文档完善

- 更新 `SKILL.md`、`README.md`、`scripts/README.md`，补充“生成阶段自动补字段”流程与命令示例。
- 更新 `TASKS.md`、`DECISIONS.md`，记录本次计划补全能力落地。

### 待办事项

- 继续推进 marketplace 版本同步。

## [1.4.4] - 2026-02-09

### 新增

- 新增 `action=auto` 动作分流能力：可根据审查项特征自动选择 `comment` 或修订动作（`replace/insert/delete`）。
- 新增动作别名兼容：支持中文动作标识（如 `批注`、`修订`、`删除`、`插入`、`自动`）。

### 改进

- 优化 `scripts/action_executor.py` 的动作归一化与判定逻辑，统一输出 `requested_action` 与实际执行 `action`，便于执行日志复盘。
- 在不影响既有显式动作（`comment/delete/insert/replace`）的前提下，为自动化计划提供“谈判项优先批注、确定性改动优先修订”的默认落地策略。

### 技术优化

- 扩展 `scripts/tests/test_action_executor.py` 回归用例，覆盖：
  - 中文动作别名归一化；
  - `auto + needs_negotiation` 场景自动走批注；
  - `auto + deterministic_edit` 场景自动走修订。

### 文档完善

- 更新 `SKILL.md`、`README.md`、`scripts/README.md`：补充“批注/修订判定口径”与 `action=auto` 用法说明。
- 更新 `TASKS.md`、`DECISIONS.md`：记录本次规则落地的任务状态与设计决策。

### 待办事项

- 继续推进 marketplace 版本同步。

## [1.4.3] - 2026-02-09

### 修复

- 修复 `scripts/action_executor.py` 在 `replace + selector` 场景下的标签不一致问题：统一采用 `selector.tag > finding.tag > action 默认值`。
- 修复 `replace` 在未提供 `target_text` 时依赖二次文本检索的问题，改为直接按 selector 定位节点执行替换。

### 技术优化

- 新增 `ContractReviewer.replace_node()`，支持节点级替换（删除目标节点 + 插入新文本）。
- 新增回归测试：
  - `scripts/tests/test_action_executor.py`
  - `scripts/tests/test_plan_loader.py`
- 重新打包并校验 `dist/contract-copilot.zip`，确保与当前源码同步。

### 文档完善

- 更新 `TASKS.md`、`DECISIONS.md`、`SKILL.md`、`README.md`、`scripts/README.md`，同步本次修复与测试策略。

### 待办事项

- 继续推进 marketplace 版本同步。

## [1.4.2] - 2026-02-09

### 改进

- 对 `scripts/apply_review_plan.py` 做最小解耦重构，入口仅保留流程编排。
- 新增 `scripts/plan_loader.py`，统一审查计划加载与结构校验。
- 新增 `scripts/action_executor.py`，统一动作分发与节点定位逻辑。
- 新增 `scripts/archive_service.py`，统一归档命名与 `manifest.json` 生成逻辑。
- 更新 `scripts/README.md`，补充分层脚本结构说明。

### 技术优化

- 降低单文件复杂度，减少计划解析/动作执行/归档逻辑互相耦合，便于后续动作扩展与单元测试。

### 待办事项

- 为 `plan_loader` 与 `action_executor` 增加独立回归用例，覆盖更多异常输入场景。

## [1.4.1] - 2026-02-09

### 改进

- 删除未使用且为空的目录：`contract-copilot/assets/`、`contract-copilot/config/`。
- 保留实际在流程中使用的目录：`references/`、`scripts/`、`templates/`、`archive/`。

### 技术优化

- 精简技能目录结构，减少无效目录对维护和分发的干扰。

### 待办事项

- 同步 marketplace 版本信息。

## [1.4.0] - 2026-02-09

### 新增

- 新增 `references/12类合同全量映射清单.md`，将现有合同类型内容完整归入固定 12 类体系。
- 新增劳动用工缺口文件：
  - `合同类型/09-employment/培训服务期协议.md`
  - `合同类型/09-employment/竞业限制协议.md`
  - `合同类型/09-employment/保密协议.md`
- 新增房地产缺口文件：
  - `合同类型/10-real-estate/勾地协议.md`
  - `合同类型/10-real-estate/土地置换协议.md`
  - `合同类型/10-real-estate/拆迁安置补偿协议.md`
- 新增建设工程缺口文件：
  - `合同类型/11-construction/内部承包合同.md`
- 新增公司投资缺口文件：
  - `合同类型/12-corporate-investment/资产收购合同.md`
  - `合同类型/12-corporate-investment/名股实债投资安排.md`

### 改进

- 更新 `SKILL.md`：明确“全量覆盖但不扩类”策略，增加未单列类型归类规则和映射清单入口。
- 更新 `README.md`：补充映射清单调用顺序，统一审查入口。
- 更新 `TASKS.md` 与 `DECISIONS.md`：记录“全量映射 + 高风险单列”的执行策略与结果。
- 完成 `dist/contract-copilot.zip` 打包与目录结构校验。

### 技术优化

- 将“合同类型识别”与“条款审查”解耦，形成“映射定位 -> 同类主文件 -> 专项议题”的标准路径。

### 待办事项

- 继续补齐剩余低深度文件，拉齐字段完整性与示例质量。
- 同步 marketplace 版本信息。

## [1.3.1] - 2026-02-09

### 新增

- 新增 `archive/` 目录及自动归档能力：每次执行后按 `archive/<时间戳_合同名>/` 存档。
- 新增归档清单 `manifest.json`，记录归档时间、关键文件和执行统计。
- 新增归档参数：`--archive-dir`、`--no-archive`、`--archive-no-input`。

### 改进

- 更新 `scripts/README.md`、`README.md`、`SKILL.md`，补充归档能力和回溯使用说明。
- 更新 `TASKS.md`、`ROADMAP.md`、`DECISIONS.md`，同步归档能力的任务状态和设计理由。

### 技术优化

- 归档流程统一沉淀审查计划、执行日志、审查报告与输出 DOCX，减少交付文件被覆盖导致的追溯缺口。

### 待办事项

- 评估是否增加归档清理策略（按天数或数量保留），控制长期存储占用。

## [1.3.0] - 2026-02-09

### 新增

- 新增 `scripts/apply_review_plan.py`，支持基于 `review-plan.json` 批量执行 DOCX 批注/修订（`comment/delete/insert/replace`）。
- 新增 `scripts/reporting.py`，支持根据审查计划与执行日志自动生成 Markdown 审查报告。
- 新增 `ContractReviewer.add_comment_by_text()`、`insert_text_after()`、`replace_text()` 便捷接口。
- 新增 `selector` 精准定位能力（`tag/attrs/line_number/contains` 组合）用于多处同文案场景。

### 改进

- 更新 `scripts/README.md`：补充一体化执行命令、输入 JSON 结构和输出文件说明。
- 更新 `README.md` 与 `SKILL.md`：将 DOCX 处理流程升级为“计划执行 + 报告生成”的推荐路径。
- 更新 `ROADMAP.md` 与 `TASKS.md`：新增脚本自动化交付阶段并记录完成状态。

### 修复

- 修复 `scripts/reviewer.py` 对 `docx` 脚本加载的兼容性，避免模块路径冲突导致导入失败。

### 技术优化

- 统一“AI 生成结构化结论 + 脚本执行文档操作 + 模板化报告输出”的交付链路，提升可重复执行性。

### 待办事项

- 用真实合同样本补充 `apply_review_plan.py` 的回归用例（含多处同文案匹配与表格场景）。
- 在发布阶段完成 `dist/contract-copilot.zip` 打包与 marketplace 版本同步。

## [1.2.0] - 2026-02-09

### 新增

- 新增 `references/03-审查流程指引.md`，提供标准化审查执行流程。
- 新增 4 个专项议题文件（不新增合同类型）：
  - `references/专项议题-交易结构与担保.md`
  - `references/专项议题-公司投资并购程序.md`
  - `references/专项议题-房地产与建设工程程序.md`
  - `references/专项议题-劳动用工关键条款.md`

### 改进

- 重写 `SKILL.md`：
  - 增加 frontmatter
  - 统一为“分层四步审查框架”表达
  - 修正合同类型覆盖说明与路径引用
- 重写 `README.md`，与当前目录结构保持一致。
- 重写 `references/review-framework.md`，统一字段化风险输出。
- 深化高频薄弱合同文件：
  - `合同类型/03-service/保管仓储合同.md`
  - `合同类型/12-corporate-investment/投资协议.md`
  - `合同类型/10-real-estate/土地出让合同.md`

### 修复

- 修复 `scripts/reviewer.py` 导入冲突：避免本地 `scripts` 包与依赖模块同名导致 `ModuleNotFoundError`。
- 修复 `scripts/README.md` 的依赖路径与示例代码。

### 技术优化

- 清理技能文档中不必要的背景说明性表述，降低分发与版权风险。
- 更新 `TASKS.md` 与 `DECISIONS.md`，使任务与决策记录与现状一致。

### 待办事项

- 继续提升剩余合同文件深度，拉齐字段完整性。
- 进行打包验证并同步发布版本。

## [1.1.0] - 2026-01-20

### 新增

- 增强知识产权类合同文件的审查细度。

### 改进

- 增加更多可复用的推荐措辞与审查提示。

### 待办事项

- 推进其他合同类别的深度补齐。

## [1.0.0] - 2026-01-19

### 新增

- 建立 `contract-copilot` 基础目录结构与核心文档。
- 提供基础合同审查参考内容、模板和脚本入口。
