# 变更日志

本文档记录 new-case skill 的重要变更。

## [1.3.5] - 2026-06-10

### 变更

- **商标预设拆 2 模板**（与专利 v1.3.4 思路一致）：
  - **注册模板**（注册/变更/转让，6 目录）：1 委托 → 2 图样 → 3 申请书 → 4 律师工作 → 5 官方文书 → 6 发票财务
  - **异议/复审/无效模板**（对抗性，7 目录）：1 委托 → 2 图样 → 3 申请书 → 4 律师工作 → 5 证据材料 → 6 官方文书 → 7 发票财务
  - 商标"沟通/工作记录"并入 1 委托材料（DEC-009，与专利一致）
- `assets/trademark.yaml` v1.3.5：2 个子模板，5 个业务子类型自动映射
- `references/classification-guide.md` 商标项目分类小节重写
- `SKILL.md`：frontmatter description + 商标案件描述 + 现有预设列表 + 商标目录示例同步更新
- 实际验证：260203 雅艺轩 商标异议（异议模板 7 目录）、251119 方帅体育 商标注册（注册模板 6 目录）干跑+应用

### 设计演进

- v1.3.0 7 目录超集 → v1.3.5 注册 6 + 异议/复审/无效 7（按业务子类型精确选模板）
- 商标 vs 专利的多模板对比：
  - 商标：2 模板（注册 vs 对抗性），业务子类型差异在**是否需要证据材料**
  - 专利：3 模板（申请 vs 复审/无效 vs 检索），业务子类型差异在**目录数量级**

## [1.3.4] - 2026-06-09

### 变更

- **专利预设：合并 2 工作记录 → 1 委托材料**（用户反馈 2026-06-09）
  - 用户原话："可能不需要有工作记录这个东西啊，那个可能可以放到委托材料或者是客户提供里面"
  - 沟通录音/邮件/会议纪要本质是律师-客户工作过程记录，与委托/合同同属"项目交互"层
  - 选择并入 1 委托材料（而非 3 客户提供），因为 1 已是"项目交互"广义目录，加入沟通记录语义最自然
  - 申请模板 8 → **7 目录**；复审/无效 9 → **8 目录**；检索 5 → **4 目录**

### 设计原则

- 沟通/工作记录**不是独立分类**——是律师-客户工作过程中的副产品
- 与委托/合同同属"项目启动"阶段，并入 1 委托材料
- 保留律师工作目录（含文件进程跟踪），合并范围限于沟通类文件
- 未来商标如需类似调整也可应用本原则

## [1.3.3] - 2026-06-09

### 变更

- **专利预设目录顺序按"项目进展"重排**（用户反馈 2026-06-09）
  - 旧（v1.3.2）：1 委托 → 2 沟通 → 3 清单 → 4 文件进程 → 5 客户提供 → 6 申请书 → 7 国知局 → 8 律师工作 → 9 发票
  - 新：1 委托 → 2 工作记录 → 3 清单 → 4 客户提供 → 5 律师工作 → 6 申请书 → 7 国知局 → 8 发票
  - **律师工作与文件进程合并**（用户原话："这个东西和文件进程感觉是一个意思吧，都是我们律师产出的工作文件"）
  - **2 沟通记录 → 2 工作记录**（更通用，包含沟通/进程跟踪等）
  - 申请模板 9 → **8 目录**；复审/无效 10 → **9 目录**；检索 5 目录（不变）

### 设计原则

- 目录编号 1-N 按"项目进展"自然顺序：启动（委托/工作）→ 准备（清单/客户）→ 律师产出（律师工作/申请书）→ 官方（国知局）→ 收尾（发票）
- 律师工作与文件进程是同一个概念（都是律师产出），合并为 1 个目录
- 复审/无效的 证据材料 + 对方提交 保持独立（复审/无效特有，律师/对方的对抗性文件分开追踪）
- 检索/其他 模板 5 目录（去掉了"申请书/官方文书"等不适用的目录）

## [1.3.2] - 2026-06-09

### 变更

- **专利预设重构：1 套 11 目录超集 → 3 个业务子模板**（用户反馈 2026-06-09）
  - 申请模板（application）：9 目录，适用于发明/实用新型/外观/PCT，无证据/对方提交
  - 复审/无效模板（invalidation）：10 目录，含证据/对方提交，无申请清单
  - 检索/其他模板（search）：5 目录，适用于检索/布局/变更/年费
  - 业务子类型自动选模板（`business_type_templates` 字段）
  - **不创建空目录**（早期设计 11 目录超集导致申请类项目出现空 8 证据/9 对方提交，现按模板创建）

- `assets/patent.yaml` 重构：保留 `meta`/`detection`/`management_files`/`business_types`/`timeline_event_types` 公共字段；新增 `business_type_templates` 映射表 + `templates` 分组（每个模板含 `directories` + `classification`）

- SKILL.md：第二步加 3 模板结构示例 + 模板选择逻辑说明；frontmatter description 更新为"按业务子类型选 3 个模板"；自定配置章节加"多模板分组模式"作为第二种结构选项

- `references/classification-guide.md`："专利项目分类"小节重写为 3 模板说明（vs 11 目录超集）

### 设计原则演进

- 旧（v1.3.1）：1 套 11 目录超集 → 申请类有空 8 证据/9 对方提交
- 新（v1.3.2）：按业务子类型自动选 3 模板之一 → 目录按需创建，无空目录
- 商标保持单模板 7 目录（业务子类型都是同质化的申请/异议/复审等，目录差异小）
- 未来如需更细的子模板（如商标的"国际申请"），同样可改多模板

## [1.3.1] - 2026-06-09

### 新增

- **专利案件预设 (patent)**：覆盖发明 / 实用新型 / 外观设计 / 无效 / 复审 / 检索 / PCT / 变更 / 年费 9 种子业务
  - `assets/patent.yaml` — 11 个平铺分类目录配置（1-11 连续编号）、分类规则、9 个业务子类型枚举、22 个时间线事件类型
  - `templates/patent-info.md` — 专利项目信息卡（含年费提醒表、引证对比文件、对方当事人）
  - `templates/patent-task-list.md` — 含年费提醒表 + 多业务法定期限追踪

### 变更

- SKILL.md：新增专利预设到触发方式和适用场景；`--case-type` 扩展支持 `专利`/`发明`/`实用新型`/`外观`/`检索`/`PCT`/`年费`；workflow 第二步加专利 11 目录结构示例；管理文件表扩展为 4 列
- `references/naming-conventions.md`：新增"专利项目"小节（业务子类型枚举 9 个、示例、注意）；管理文件表加专利列
- `references/classification-guide.md`：新增"专利项目分类"小节（11 平铺分类 + 9 业务子类型目录映射 + 模糊场景处理）；对比表扩展为 4 列
- frontmatter description 更新为"诉讼/咨询/商标/专利四种预设"

### 设计原则

- **11 编号是超集**：所有 9 个业务子类型共享 11 目录，按业务类型填充相关目录，空目录正常
- **vs 商标 7 目录的关键差异**：
  - 新增 2 沟通记录、3 专利清单、4 文件进程（专利特有）
  - 5 客户提供（从商标 01 委托材料拆出）
  - 7 国知局文件（商标叫 04 官方文书）
  - 8 证据材料 + 9 对方提交（专利无效/复审特有，商标场景弱）
  - 11 发票/财务（含年费追踪）
- **统一编号**：区别于 260316 历史的 1/2/3/4/5/9/10/11 跳跃编号，**新项目统一用 1-11 连续编号**。详见 DEC-006。

## [1.3.0] - 2026-06-08

### 新增

- **商标案件预设 (trademark)**：覆盖商标注册 / 异议 / 驳回复审 / 无效宣告 / 变更转让 5 种子业务
  - `assets/trademark.yaml` — 7 个平铺分类目录配置、分类规则、detection、业务子类型枚举
  - `templates/trademark-info.md` — 商标项目信息卡（含关联申请号表、续展提醒、引证商标）
  - `templates/trademark-task-list.md` — 含续展提醒表 + 法定期限追踪表

### 变更

- SKILL.md：新增商标预设到触发方式和适用场景；`--case-type` 扩展支持 `商标`/`注册`/`异议`/`复审`/`无效`/`变更`；多步骤加入商标条目；**新增操作铁律**：保留文件时间戳、保留用户自建子目录
- `references/naming-conventions.md`：新增"商标项目"小节；管理文件表加商标列
- `references/classification-guide.md`：新增"商标项目分类"小节（7 平铺分类 + 多申请号文件归位原则）；对比表扩展为三列；**新增分类原则**4 和 5（保留时间戳、保留自建子目录）

### 设计演进

- **2026-06-08 晚**（基于伊甸文化项目干跑验证）：早期设计曾尝试"项目共享 + 申请号子目录"两层结构（每个申请号一个子目录，目录内 7 分类），实测对 2-3 个申请号的常见场景属过度设计。改为 **7 个平铺分类目录**，多申请号同类文件归位到一起，申请号信息以"关联申请号"表形式记录在项目信息卡中。详见 DEC-003。
- **2026-06-09**（基于伊甸文化 v2 验证）：发现两类实现 bug：(1) `cp` 未带 `-p` 导致文件 mtime 全部丢失；(2) 把用户自建的 `NOVA ARTS/` 子目录内容拉平到 `02 商标图样/` 根目录，破坏用户原有组织。已写为 SKILL.md 第三步"操作铁律"和 classification-guide.md 分类原则 4、5。
- **2026-06-09**（基于伊甸文化项目 04 官方文书 PDF 优化）：发现 2 个官方文书 PDF（驳回通知书、驳回复审决定书）文件名无发文日期，导致按文件名排序时乱序。**新增"第三步半：官方文书 PDF 自动加发文日期前缀"**：扫描 `04/03/05` 中无 `YYMMDD` 前缀的 PDF，用 `pdftotext` 或 OCR 提取发文日期，匹配"发文日期/决定日期"等关键字附近的日期，`mv` 改名（保留 mtime）。伊甸文化项目实战：`84549280_NOVA ARTS_驳回通知书.pdf` → `250710 84549280_NOVA ARTS_驳回通知书.pdf`；`商标驳回复审决定书_84549280_第28类NOVAARTS_176717.pdf` → `251229 商标驳回复审决定书_84549280_第28类NOVAARTS_176717.pdf`。详见 DEC-005。

## [1.2.2] - 2026-04-23

### 改进

- **咨询预设分类规则扩充**：基于 4 个实际咨询项目的文件分析，优化 `consultation.yaml` 的分类规则
  - 01-咨询记录：新增视频录像(.mp4)、微信语音转写、转写文稿关键词匹配
  - 02-证据材料：补充声明、鉴定报告、权属证明、起诉状等分类
  - 03-工作文件：新增法律问答提取、内部沟通记录关键词匹配
  - detection 新增法律问答、内部沟通、应对说明关键词
- **consultation-info.md 模板扩充**：新增关联案件段落，记录咨询转化为诉讼后的关联信息
- **classification-guide.md 扩充**：新增视频文件、法律问答提取、内部沟通记录、转化后子案件文件夹的分类指南

## [1.2.1] - 2026-04-23

### 修复

- 删除已废弃的 `references/case-config.yaml`（内容已迁移到 `assets/litigation.yaml`）
- 更新 `templates/case-directory.md`、`templates/case-info.md`、`references/material-classification.md` 中的过时引用
- 更新 SKILL.md 向后兼容说明

### 变更

- `assets/presets/` 扁平化为 `assets/`（`litigation.yaml`、`consultation.yaml` 直接放在 assets/ 下）
- 更新所有文件中的 `assets/presets/` 引用

### 改进

- **咨询预设分类规则扩充**：基于 4 个实际咨询项目的文件分析，优化 `consultation.yaml` 的分类规则
  - 01-咨询记录：明确覆盖录音(.mp3/.aac)、转写、微信记录、通话记录
  - 02-证据材料：补充声明、鉴定报告、权属证明、起诉状等分类
  - 03-工作文件：从"沟通记录"重命名，明确存放内部沟通、案件分析、策略草稿
  - 根目录保留：新增法律意见书、咨询报告作为 root_files
- **consultation-info.md 模板扩充**：新增相关当事人、材料清单、已交付文件、转化评估等字段
- **references/ 目录充实**：新增 3 个参考文档，承载从 SKILL.md 解耦的领域知识
  - `references/naming-conventions.md` — 案件编号、案件名称、文件命名详细规则
  - `references/classification-guide.md` — 材料分类决策逻辑、模糊场景处理
  - `references/extraction-rules.md` — 从不同材料类型提取案件信息的规则

### 删除

- 删除 `references/material-classification.md`（YAML→Word 映射属于 md2word 职责）
- 删除 `templates/case-directory.md`（冗余，信息已在 assets/*.yaml 中）

### 重构

- SKILL.md 从 212 行精简到 176 行，详细规则下沉到 references/，改为引用方式

## [1.2.0] - 2026-04-23

### 新增

- **多预设配置系统**：引入 `assets/` 目录，支持不同案件类型的独立配置
  - `assets/litigation.yaml` — 诉讼案件（12目录），从 `references/case-config.yaml` 迁移
  - `assets/consultation.yaml` — 潜在项目/咨询（3目录），新增
- **类型自动检测**：SKILL.md 新增第零步，根据路径关键词和文件内容自动识别案件类型
- **咨询项目模板**：新增 `templates/consultation-info.md`（简化项目信息卡片）
- **`--case-type` 参数扩展**：支持 `诉讼`/`咨询`/`民事`/`刑事`/`行政`

### 变更

- SKILL.md 工作流增加第零步（类型检测），步骤2-5改为读取预设配置
- 管理文件生成改为条件式，根据预设的 `management_files` 配置决定生成哪些文件
- `references/case-config.yaml` 标记废弃，指向 `assets/litigation.yaml`

## [1.1.0] - 2026-04-22

### 重构

- **templates/ + references/ 分层**：对齐 monorepo 约定（templates 管输出、references 管规则）
  - 合并 `case-structure.md` + `directory-guide.md` → `templates/case-directory.md`
  - 迁移 `case-info-template.md` → `templates/case-info.md`
  - 迁移 `timesheet-template.md` → `templates/timesheet.md`
  - 拆分 `yaml-schema.md` → `templates/deadline-yaml.md`（模板）+ `references/material-classification.md`（映射规则）
- **目录与分类配置化**：新增 `references/case-config.yaml`，目录定义和材料分类规则改为 YAML 配置，用户可自定义
  - `material-classification.md` 精简为仅保留 YAML→Word 字段映射
  - `case-directory.md` 改为引用 YAML 的速览表
  - SKILL.md 第二步、第三步改为读取 YAML 配置
- **case-info.md 精简为案件卡片**：移除动态内容，仅保留稳定信息
  - 法定期限管理 → 引用 YAML 文件（YAML 为唯一数据源）
  - 风险提示与策略 → 引用 `02 - 📄 案件分析/`
  - 更新历史 → 移除（YAML 中已包含）
- **待办事项独立模板**：从 case-info.md 提取到 `templates/task-list.md`

### 删除

- 删除所有 Agent 责任分配内容（SuitAgent 遗留配置）
- YAML 模板保留 🔧/⏳ 标记，删除 Agent 名称
- 删除 `references/` 下 5 个旧文件

### 改进

- service-proposal 改为调用 `legal-proposal-generator` skill，消除悬空引用
- SKILL.md 引用路径更新，step 4 描述对齐精简后的 case-info 结构

## [1.0.0] - 2026-04-22

### 迁移

- 从 SuitAgent 项目迁移到 legal-skills 独立 skill 仓库

## [0.3.0] - 2026-04-03

### 重构

- 从 `/new-case` command（`.claude/commands/new-case.md`）转为 skill 格式（SKILL.md + references/）
- 内置模板拆分为独立参考文件：
  - `references/case-info-template.md` — 案件信息看板模板（10个段落结构）
  - `references/case-structure.md` — 12层目录结构规范与材料分类映射
  - `references/directory-guide.md` — 各目录的子目录结构、关联 Agent、输出文件示例
  - `references/timesheet-template.md` — 工时记录模板
  - `references/yaml-schema.md` — 期限管理 YAML 结构（含初始化/后续段落标注）

### 新增

- 可选第六步：基于客户沟通记录生成法律服务方案（引用 `references/service-proposal-template.md`）
- SKILL.md frontmatter 添加 license 字段

## [0.2.0] - 2026-01-01

### 改进

- 适配 SuitAgent 配置文件解耦与单一真实源设计
- 更新案件信息模板字段与格式

## [0.1.0] - 2025-11-17

### 新增

- 作为 SuitAgent `/new-case` 命令首次创建
- 定义标准12层目录诉讼架构（替代原6目录结构）
- 案件材料自动分类整理（身份证/合同/证据/法律文书等映射到对应目录）
- 生成案件信息看板（案件信息.md）：当事人信息、争议焦点、时间线、任务清单、法定期限管理
- 生成工时记录（工时记录.md）和期限管理文件（.yaml）
- 支持自然语言和参数化触发（`--case-id`、`--client-name`、`--case-type` 等）
