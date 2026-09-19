# Legal Skill Brief v1 规范

> 本规范定义 **Legal Skill Brief v1**（简称 `legal-skill-brief/v1`）——legal-skill-alignment 的最终产出格式。
>
> **中立交接**：Brief v1 设计为可被通用 `skill-creator`（上游公开版）与 `legal-skill-creator`（法律领域编排器）**共同消费**。下游对字段无强制 schema 校验，少给字段不失败，多给字段不报错。

## 版本与作用域

- **schema 版本**：`legal-skill-brief/v1`
- **配套方法论**：`question-set/v1`（当前默认五问；预留扩展为六问/七问的能力）
- **本文件替代**：v0.x 时代的"标准 Prompt 输出模板"+ 五标识符必填协议

---

## 目录

- [字段命名约定](#字段命名约定)
- [一、上下文元数据](#一上下文元数据可选-metadata)
- [二、五问要素](#二五问要素question-setv1-主结构)
- [三、规则引擎](#三规则引擎可选)
- [四、素材溯源](#四素材溯源v1-起必填-quality-字段)
- [五、安全与脱敏说明](#五安全与脱敏说明v1-起必填)
- [六、待确认清单](#六待确认清单v1-起带缺口类型v102-起带状态判定)
- [完整模板](#完整模板一页复制版)
- [模板填充示例](#模板填充示例合同审查)
- [下游消费者兼容性](#下游消费者兼容性)
- [输出格式多样化指引](#输出格式多样化指引)
- [v0 → v1 迁移指南](#v0--v1-迁移指南)

---

## 字段命名约定

| 规则 | 说明 | 示例 |
|------|------|------|
| 标识符（identifier）使用 **kebab-case** | 唯一标识符层级 | `ip-copyright-demand-letter`、`labor-contract-review` |
| 阶段 / 角色使用 **snake_case** | 语义复合词 | `non_litigation`、`first_instance`、`buyer_counsel` |
| **禁止** 在 identifier 中使用下划线 | 避免与阶段/角色字段混淆 | ❌ `labor_contract_review`（应改为 `labor-contract-review`） |
| **允许** 在 stage / role 等枚举值中下划线 | snake_case 是其命名空间 | ✅ `pre_litigation` ✅ `rights_holder_counsel` |
| 文书类型使用 snake_case | 与 stage 同命名空间 | ✅ `demand_letter`、`agent_statement` |
| 元数据键使用 snake_case | 与下游消费者约定一致 | ✅ `skill_family`、`represented_party` |

> **迁移提示**：v0.x 历史上使用 `labor_contract_review` 等 snake_case 标识符，v1 起重命名为 `labor-contract-review`。既有评测案例保留原值作 v0 快照，重对齐案例全部使用 kebab-case。

---

## 一、上下文元数据（可选 metadata）

**说明**：本节为**可选**元数据，下游消费者可读可不读；alignment 自检**不强制**本节字段齐全。如果用户对某个字段不确定，可填 `unverified` 或留空。

````markdown
## 一、上下文元数据（可选）

- **skill_family**：{kebab-case 英文标识，如 `ip-copyright-demand-letter`}
- **jurisdiction**：{`CN` / `HK` / `US` / `EU` / 其他法域}
- **stage**：{见 legal-domain-mapping.md 的 stage 枚举}
- **operator**：{谁直接使用本 Skill，如 `lawyer`、`paralegal`、`compliance-officer`、`ai-operator`}
- **represented_party**：{所代表的当事人，如 `plaintiff`、`defendant`、`employer`、`target-company`}
- **output_audience**：{最终文书读者，如 `judge`、`opposing-counsel`、`client`、`internal-team`}
- **doc_type**：{文书/产物类型，如 `demand-letter`、`complaint`、`compliance-report`；非文书型可填 `tool` / `data-pack`}
- **tags**：{自由标签列表，便于下游检索}
````

---

## 二、五问要素（question-set/v1 主结构）

本段是 Brief 的**主体**，承载从素材或访谈对齐出的全部意图。下游消费者从这里提取"输入/输出/逻辑/交付/知识"五大维度。

> **字段类型**：每个五问子段独立成节，按下表编号；不可省略、不可换序。
>
> **完整性约束**：见 SKILL.md 的「完整性规则」段——五问每问都必须有答案或被明确标记为"待补"，缺一不可。

### 1. 输入什么（Inputs）

````markdown
**必要输入**：
- {输入项 1，含格式要求与来源}
- {输入项 2}

**可选输入**：
- {可选项 1}

**信息来源**：{用户上传 / 公开检索 / 律所内部库 / 工具导出}
````

### 2. 输出什么（Outputs）

````markdown
**主要产出**：{产出名}
**格式要求**：{章节结构 / 字数 / 抬头落款 / 表格化 / 多级编号 等；见下文"输出格式多样化指引"}
**质量标准**：{什么算"做得好"，可量化的标准}
**产出形态**：{text-document / table / mixed / tool-output}
````

### 3. 处理逻辑（Workflow）

````markdown
**主流程**：
1. {步骤 1}
2. {步骤 2}
   - 决策点：{条件} → {分支 A / 分支 B}
3. {步骤 3}
   - 质量检查点：{谁 review 什么}

**异常路径**：
- {异常 1} → {应对}
````

### 4. 向谁交付（Context.Delivery，v1 拆三子项）

> **v1 变更**：第 4 问在 question-set/v1 中拆为 `operator` / `represented_party` / `output_audience` 三子项，对应"使用 Skill 的角色" / "所代表的当事人" / "最终文书读者"——三者常被混淆，必须分别明确。

````markdown
**operator**（Skill 操作者）：{直接使用本 Skill 的角色}
  - 典型：执业律师 / 律师助理 / 合规专员 / 法务总监 / AI 操作员
  - 决定：能调用什么工具、看到哪些字段、能跳过哪些步骤

**represented_party**（所代表的当事人）：{Skill 产出物实质服务的对象}
  - 典型：原告 / 被告 / 雇主 / 雇员 / 收购方 / 目标公司 / 第三方中立
  - 决定：内容立场、利益偏好、保密等级
  - **禁止误写**：法官是 `output_audience`，不是 `represented_party`

**output_audience**（最终文书读者）：{产出物最终交付给谁看}
  - 典型：法官 / 对方律师 / 客户本人 / 客户内部决策层 / 监管机关
  - 决定：语气基调、详略取舍、术语密度、引用格式

**触发场景**：{什么情况下使用本 Skill，如"签约前法务审查"/"纠纷发生后起诉准备"}
**语气基调**：{正式威慑 / 平和可读 / 中性专业 / 教育科普}
````

### 5. 需要哪些知识支撑（Knowledge Base）

> **v1 变更**：法源条目**强制**带 `effective_date` / `jurisdiction` / `verification_status` 三列；阈值规则**强制**带 `source`（来源）列。
>
> **v1.0.2 起 verified 证据门槛**（T-013）：`verification_status = verified` 必须满足最小证据要求，否则只能标 `unverified`。`effective_date` 指当前引用版本的**施行日期**，不得与通过日 / 公布日 / 修订通过日混用。

#### verified 最小证据要求（T-013）

`verified` 条目必须同时满足：

| 字段 | 要求 | 示例 |
|------|------|------|
| `source_url` 或 `source_file` | 至少一项，指向可访问的法源原文或权威转录；不得只写网站名称或“同上” | 完整 URL 或本 Skill 内可访问的相对路径 |
| `verified_by` | 可追溯的核验责任人或内部核验记录 ID；不得只写泛称角色 | `张某律师` / `legal-team-review-001` |
| `verified_at` | 核验日期（ISO 8601） | `2026-07-30` |
| `version_as_of` | 引用的法源版本标识 | `2020 修正版` / `2025 修改决定版` |

**禁止**：仅有法条名称、网站名称、“同上”或从样本反推时，**不得**升级为 `verified`——必须标 `unverified` 并在“待确认清单”列出缺口。若 Brief 会产出具体法律建议，关键法源原文缺失为 `blocker`；否则为 `warning`。

````markdown
**法律依据**：

| 法条 / 司法解释 | jurisdiction | effective_date | verification_status | source_url / source_file | verified_by | verified_at | version_as_of | 说明 |
|----------------|--------------|----------------|---------------------|--------------------------|-------------|-------------|---------------|------|
| 《民法典》第 577 条 | CN | unverified | unverified | unverified | unverified | unverified | unverified | 仅展示字段形态；未附原文，不得作为确定性依据 |
| 《XYZ 法》第 N 条 | CN | unverified | unverified | unverified | unverified | unverified | unverified | 仅有法条名称；待补原文、条号与施行日 |

**范本来源**：{内部范本 / 公开模板，路径或描述}
**风险清单**：{风险点 1 / 风险点 2}
**风格偏好**：{用词 / 句式 / 语气特征}
````

---

## 三、规则引擎（可选）

当对齐产出包含量化阈值、评分规则或判断标准时，在此段列出。**v1 起**：阈值与判断标准必须带 `source`（来源），未确认的标 `unverified`。

````markdown
**阈值配置**：

| 阈值名 | 数值 | 触发动作 | source |
|--------|------|----------|--------|
| 注册资本风险阈值 | 合同年金额 > 注册资本 × 5 | 标红 | SOP（律所内部审查清单 v3） |
| 首付比例阈值 | 首付 > 30% | 标黄 | SOP（律所内部审查清单 v3） |
| SLA 缺失 | 无量化 KPI | 标黄 | sample-001 反推 |

**判断标准**：

| 标准名 | 判定逻辑 | 触发条件 | source |
|--------|----------|----------|--------|
| 管辖不利 | 约定对方所在地管辖 | 任何管辖条款 | SOP v3 |
| 数据安全缺失 | 涉及用户数据但无数据处理协议 | 涉及用户数据的合同 | sample-002 反推 |
````

> **重要**：阈值和判断标准来自素材（SOP / 样本）或用户确认，**不要凭空编造**。如果素材未提供阈值但 workflow 需要，标 `source: unverified` 并在待确认清单中说明"阈值待团队确认"。

---

## 四、素材溯源（v1 起必填 quality 字段）

> **v1 变更**：质量等级从"可选"改为**必填**——`gold` / `silver` / `bronze` / `unrated`（无法判断时必须填 unrated 并注明原因）。

````markdown
| 素材类型 | 数量 | 来源 | quality | 用途 |
|----------|------|------|---------|------|
| sample（成品文书） | N | {路径或描述} | gold / silver / bronze / unrated（原因） | {用于提取结构骨架/风格特征/...} |
| sop（流程规则） | N | {路径或描述} | quality | {用于决策点/质量检查点} |
| qa（问答） | N | {路径或描述} | quality | {用于高频问题/标准答法} |
| rules（规则包） | N | {路径或描述} | quality | {用于阈值/判断标准} |
| revisions（对话修订记录） | N | {路径或描述} | quality | {用于风格偏好/反馈修订} |
| tools-data（工具/数据源） | N | {路径或描述} | quality | {用于输入/输出/联动} |
| authorities（法源原文） | N | {路径或描述} | quality | {用于法源验证} |

**quality 定义**：
- **gold**：经执业律师审核的标杆样本或现行有效法条原文
- **silver**：来源可靠但未经审核，或时间略旧但核心内容仍有效
- **bronze**：参考性素材，结论需进一步验证
- **unrated**：无法判定质量等级（须注明原因，如"素材过少无法交叉验证"）
````

---

## 五、安全与脱敏说明（v1 起必填）

> **v1 变更**：本段为新增必填段。Brief 涉及真实材料时，必须声明敏感信息已脱敏状态与外传策略。

````markdown
**敏感材料处理**：
- 已识别敏感信息：{身份证号 / 手机号 / 客户名 / 案件名 / 当事人自然人信息 / 合同金额 / 地址 / 其他}
- 脱敏状态：{已脱敏 / 未脱敏 / 部分脱敏（说明）}
- 脱敏责任：{用户已确认脱敏 / AI 提示用户须自行脱敏 / 仅使用脱敏样本}

**外传策略**：
- 是否需要外部检索：{是 / 否}
- 是否上传外部服务：{否 / 仅经用户确认的具体服务（说明）}
- 数据留存策略：{一次性使用 / 本地保存 / 共享给团队（说明）}

**高风险结论复核**：
- 是否涉及最终法律结论：{是 / 否}
- 是否需要执业律师复核：{是 / 否 / 由用户自行决定}
````

---

## 六、待确认清单（v1 起带缺口类型；v1.0.2 起带状态判定）

> **v1 变更**：每个待确认项必须标注 `缺口类型`：`blocker`（阻塞交接） / `warning`（带警告交接）。
>
> **v1.0.6 起状态判定**：Brief 顶部须标注 `structurally_complete` 与 `handoff_ready` 两个状态。`handoff_ready = true` 当且仅当 `structurally_complete = true` **且 blocker 项 = 0**。

````markdown
### 状态判定（v1.0.6 起必填）

- structurally_complete: true / false
- handoff_ready: true / false（= structurally_complete && blocker数=0）
- blocker 数: N
- warning 数: M

### 阻塞交接缺口（blocker，必须补全才能 handoff_ready）

- [ ] {要素}：{为什么待确认 + 建议补充方式} — type: blocker

### 可带警告交接缺口（warning，允许交付但必须列出）

- [ ] {要素}：{为什么待确认 + 建议补充方式} — type: warning
````

> **判定规则**（详见 SKILL.md 完整性规则段）：
> - **blocker**：五问任何一问答案为空 / `operator` 完全空白（仅标“待补”不算 blocker，但完全无推断依据算）/ Brief 会产出具体法律建议但关键法源没有 `source_url` 或 `source_file`
> - **warning**：`output_audience` 仅模糊推断 / 阈值未共识 / 风格偏好仅口头 / quality=unrated / `operator` 标"待补"

---

## 完整模板（一页复制版）

````markdown
# Skill 编译请求：{skill 中文名}

> 由 legal-skill-alignment v1.0.0 对齐产出，遵循 legal-skill-brief/v1 规范。
> 下游消费者：通用 `skill-creator` 或 `legal-skill-creator`。

## 一、上下文元数据（可选）

- skill_family：{kebab-case}
- jurisdiction：{CN / HK / US / ...}
- stage：{枚举值}
- operator：{角色}
- represented_party：{当事人}
- output_audience：{读者}
- doc_type：{文书类型}
- tags：{[tag1, tag2]}

## 二、五问要素（question-set/v1）

### 1. 输入什么（Inputs）
**必要输入**：...
**可选输入**：...
**信息来源**：...

### 2. 输出什么（Outputs）
**主要产出**：...
**格式要求**：...
**质量标准**：...
**产出形态**：{text-document / table / mixed / tool-output}

### 3. 处理逻辑（Workflow）
**主流程**：1. ... 2. ... 3. ...
**异常路径**：...

### 4. 向谁交付（Context.Delivery）
**operator**：...
**represented_party**：...
**output_audience**：...
**触发场景**：...
**语气基调**：...

### 5. 需要哪些知识支撑（Knowledge Base）
**法律依据**：

| 法条 / 司法解释 | jurisdiction | effective_date | verification_status | source_url / source_file | verified_by | verified_at | version_as_of | 说明 |
|----------------|--------------|----------------|---------------------|--------------------------|-------------|-------------|---------------|------|
| ... | ... | ... | ... | verified 必填；unverified 填 `unverified` | verified 必填 | verified 必填 | verified 必填 | unverified 注明原因 |

**范本来源**：...
**风险清单**：...
**风格偏好**：...

## 三、规则引擎（可选）
**阈值配置**：

| 阈值名 | 数值 | 触发动作 | source |
|--------|------|----------|--------|

**判断标准**：

| 标准名 | 判定逻辑 | 触发条件 | source |
|--------|----------|----------|--------|

## 四、素材溯源（必填 quality）

| 素材类型 | 数量 | 来源 | quality | 用途 |
|----------|------|------|---------|------|

## 五、安全与脱敏说明（必填）
**敏感材料处理**：...
**外传策略**：...
**高风险结论复核**：...

## 六、待确认清单
### 状态判定（v1.0.2 起必填）
- structurally_complete: true / false
- handoff_ready: true / false
- blocker 数: N
- warning 数: M

### 阻塞交接缺口（blocker）
- [ ] ...

### 可带警告交接缺口（warning）
- [ ] ...
````

---

## 模板填充示例（合同审查）

````markdown
# Skill 编译请求：供应商服务合同审查

> 由 legal-skill-alignment v1.0.0 对齐产出，遵循 legal-skill-brief/v1 规范。
> 下游消费者：通用 `skill-creator` 或 `legal-skill-creator`。

## 一、上下文元数据（可选）

- skill_family：supplier-service-contract-review
- jurisdiction：CN
- stage：non_litigation
- operator：buyer-counsel（买方律师 / 企业法务）
- represented_party：buyer（采购方/委托方）
- output_audience：buyer-internal-team（企业内部法务+采购）
- doc_type：contract-review
- tags：[supplier, service-contract, pre-signing]

## 二、五问要素（question-set/v1）

### 1. 输入什么
**必要输入**：供应商服务合同全文（.docx，含附件）；服务类型说明（物流 / SaaS / IT 外包 / 其他）
**可选输入**：企业内部采购制度或合规要求；历史同类合同审查记录
**信息来源**：用户上传

### 2. 输出什么
**主要产出**：合同审查意见书
**格式要求**：风险等级分色标注（高 / 中 / 低）+ 条款逐条批注 + 修改建议 + 法条依据
**质量标准**：每条风险标注法条依据；8 大审查维度全覆盖；有量化阈值触发机制
**产出形态**：mixed（正文文本 + 风险矩阵表 + 批注列表）

### 3. 处理逻辑
1. 解析合同结构，识别服务类型
2. 主体核查：核实服务商注册资本 vs 合同金额
3. 标的条款审查：检查 SLA 指标是否量化
4. 价款与支付：检查首付比例
5. 知识产权审查：技术类服务合同必须约定 IP 归属
6. 违约责任审查：赔偿上限是否覆盖预付金额
7. 保密与数据安全：涉及用户数据的合同必须有数据处理协议附件
8. 管辖与争议解决：对方所在地管辖 → 建议改
9. 退出机制：是否有单方解除权
10. 生成风险清单与修改建议
    - 质量检查点：执业律师对高风险项复核

**异常路径**：
- 无 SLA 条款 → 标黄 + 建议增加 SLA 附录
- 无数据安全条款 → 标红 + 建议增加数据处理协议附件

### 4. 向谁交付
**operator**：买方律师 / 企业法务（直接使用本 Skill）
**represented_party**：买方企业（采购方/委托方）
**output_audience**：企业内部法务 + 采购部门（共同评审）
**触发场景**：企业与外部供应商签订服务合同前
**语气基调**：中性专业，提示风险但不阻断交易

### 5. 需要哪些知识支撑
**法律依据**：

| 法条 / 司法解释 | jurisdiction | effective_date | verification_status | source_url / source_file | verified_by | verified_at | version_as_of | 说明 |
|----------------|--------------|----------------|---------------------|--------------------------|-------------|-------------|---------------|------|
| 《民法典》第 577 条（违约责任） | CN | unverified | unverified | unverified | unverified | unverified | unverified | 示例未附原文；待补充后方可用于具体审查结论 |
| 《民法典》第 563 条（合同解除） | CN | unverified | unverified | unverified | unverified | unverified | unverified | 示例未附原文；待补充后方可用于具体审查结论 |
| 《网络安全法》第 21 / 42 条 | CN | unverified | unverified | unverified | unverified | unverified | unverified | 示例未附原文；不得凭名称填施行日 |
| 《个人信息保护法》第 13 条 | CN | unverified | unverified | unverified | unverified | unverified | unverified | 示例未附原文；待补具体条文与版本 |

**范本来源**：律所内部供应商合同审查清单（8 步骤）
**风险清单**：主体资质风险 / 服务标准缺失风险 / 赔偿上限不足风险 / 数据安全风险 / 管辖不利风险
**风格偏好**：法条引用精确到条；风险等级三色标注；抬头"致 XX 公司法务部"；落款"XX 律师事务所"

## 三、规则引擎

**阈值配置**：

| 阈值名 | 数值 | 触发动作 | source |
|--------|------|----------|--------|
| 注册资本风险阈值 | 合同年金额 > 注册资本 × 5 | 标红 | SOP（律所内部审查清单 v3） |
| 首付比例阈值 | 首付 > 30% | 标黄 | SOP（律所内部审查清单 v3） |
| SLA 缺失 | 无量化 KPI | 标黄 | SOP（律所内部审查清单 v3） |

**判断标准**：

| 标准名 | 判定逻辑 | 触发条件 | source |
|--------|----------|----------|--------|
| 管辖不利 | 约定对方所在地管辖 | 任何管辖条款 | SOP v3 |
| 数据安全缺失 | 涉及用户数据但无数据处理协议 | 涉及用户数据的合同 | sample-002 反推 |

## 四、素材溯源

| 素材类型 | 数量 | 来源 | quality | 用途 |
|----------|------|------|---------|------|
| sample | 2 | 历史审查意见书（仓储配送 + SaaS） | silver | 提取结构骨架 / 风格特征 |
| sop | 1 | 律所内部供应商审查清单 8 步骤 | gold | 提取决策点 / 阈值 |
| qa | 0 | 无 | unrated（无 Q&A 素材） | — |

## 五、安全与脱敏说明

**敏感材料处理**：
- 已识别敏感信息：合同金额 / 双方当事人名称（已脱敏处理为"买方/卖方"）
- 脱敏状态：已脱敏
- 脱敏责任：用户已确认脱敏

**外传策略**：
- 是否需要外部检索：否
- 是否上传外部服务：否
- 数据留存策略：本地保存，不外传

**高风险结论复核**：
- 是否涉及最终法律结论：否（仅审查意见，非定稿文书）
- 是否需要执业律师复核：高风险项须复核

## 六、待确认清单

### 状态判定
- structurally_complete: true（字段已如实标注）
- handoff_ready: false（具体合同审查结论所需的关键法源原文未提供）
- blocker 数: 1
- warning 数: 4

### 阻塞交接缺口（blocker）
- [ ] 关键法源原文：合同审查结论涉及具体法律建议，但示例未附任何可追溯的法源原文 URL 或本地路径；补齐后逐条核验 — type: blocker

### 可带警告交接缺口（warning）
- [ ] 法源覆盖度：SOP 中未体现《电子商务法》相关条款 — type: warning
- [ ] 风格偏好：抬头/落款格式是否需根据客户不同调整 — type: warning
- [ ] 阈值标准：注册资本 × 5、首付 > 30% 是否经团队共识 — type: warning
- [ ] 样本 quality=unrated（Q&A 素材缺失）— type: warning
````

---

## 下游消费者兼容性

| 下游 | 期望输入 | Brief v1 兼容性 | 说明 |
|------|---------|----------------|------|
| 通用 `skill-creator` | 自然语言意图 + 用户已知道要做什么 | ✅ 友好 | `五问要素` 即对应其 Capture Intent + Interview 输出；`素材溯源` 可作为 references 来源；`元数据` 可作为额外结构提示 |
| `legal-skill-creator` | 自然语言意图 + 上游材料 + 路由决策 | ✅ 友好 | `五问要素` 描述了"输入状态"（杂乱/已筛选/单份/对话/现有 skill），正好支撑其路由决策表；不强制要求任何 schema |
| `legal-skill-alignment` 本体（递归） | 上游已对齐的 Brief | ✅ 友好 | 可基于上一份 Brief 再做一轮对齐（适用于对齐已有 skill 的重构场景） |

> **重要**：下游消费者**不会**因为 Brief 中某字段缺失而拒绝接收。"五问齐全"是 alignment 内部的完整性约束，不是下游的硬性 schema。

---

## 输出格式多样化指引

Brief v1 主结构是 markdown 纯文本，但不同法律场景的输出格式差异大。当产出格式不是纯文本时，按以下原则处理：

| 格式类型 | 适用场景 | Brief 中如何描述 |
|---------|---------|------------------|
| 纯文本段落 | 法律意见书、代理词、律师函 | 按章节结构描述，标注字数 / 段落要求 |
| 表格化 | 合规扫描报告、尽调清单、风险矩阵 | 在"格式要求"中注明"表格化输出"，列出列名和行逻辑 |
| 多级编号 | 合同条款逐条审查、证据目录 | 注明编号层级和格式约定 |
| 混合格式 | 审查意见书（文本 + 表格 + 列表） | 分别描述各部分的格式要求 |
| 工具/数据型 | 规则抽取器、证据组织器、合规扫描工具 | `doc_type: tool` / `data-pack`；在"产出形态"标注 `tool-output` |

**格式描述要点**：
- 不要假设下游消费者能自动理解"表格化"——明确说明列名、排序规则、填充逻辑
- 如果输出含风险等级标注（高 / 中 / 低），说明颜色 / 符号约定
- 如果输出含法律条文引用，说明引用格式（如《XX 法》第 X 条）
- 工具型产出须说明输入格式、输出格式、调用方式（CLI / API / 嵌入式）

---

## v0 → v1 迁移指南

| v0.x（deprecated） | v1.0.0（current） | 迁移要点 |
|--------------------|-------------------|----------|
| `skill_family = labor_contract_review` | `skill_family = labor-contract-review` | 标识符改 kebab-case |
| 标识符必填（五标识符） | 元数据可选 | 不强制下游 schema；alignment 内部仍建议填 |
| 五问法 | `question-set/v1` | 命名版本化，预留扩展 |
| 第 4 问"向谁交付"（笼统） | 拆为 operator / represented_party / output_audience | 角色语义明确化 |
| 素材溯源质量过滤可选 | quality 必填（unrated 也行） | 强制标注 |
| 法源条目无版本信息 | 法源三列：jurisdiction / effective_date / verification_status | 法源可追溯 |
| 阈值无来源标注 | 阈值带 source | 决策可追溯 |
| 待确认清单无类型 | 待确认清单带 type: blocker / warning | 完整性可判定 |
| 无安全段 | 安全与脱敏说明段必填 | 安全边界明确 |

> 历史评测 `evals/case-bundle-260705/` 与 `evals/case-bundle-260728/v1-realigned/` 均保留为版本快照；后者早于 v1.0.6 的逐字段法源证据与交接状态规则，不能作为当前版本的验证证据。
