# 变更日志

本文档记录 new-case skill 的重要变更。

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
