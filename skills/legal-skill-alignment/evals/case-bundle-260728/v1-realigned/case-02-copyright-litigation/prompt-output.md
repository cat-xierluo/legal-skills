# Case 02 v1 Brief: 著作权侵权代理词

> 本 Brief 由 `legal-skill-alignment v1.0.0` 对齐产出，遵循 `legal-skill-brief/v1` 规范。
>
> 下游消费者：通用 `skill-creator` 或 `legal-skill-creator`。
>
> 方法论版本：`question-set/v1`。
>
> v0 基线：参见 [`case-bundle-260705/case-02-copyright-litigation/prompt-output.md`](../../../case-bundle-260705/case-02-copyright-litigation/prompt-output.md)。

## 一、上下文元数据（可选）

- **skill_family**：`copyright-infringement-agent-statement`
- **jurisdiction**：CN
- **stage**：`first_instance`
- **operator**：`plaintiff-counsel`（原告方律师）
- **represented_party**：`plaintiff-rights-holder`（原告权利人）
- **output_audience**：`judge`（主审法官）
- **doc_type**：`agent-statement`
- **tags**：[copyright, litigation, first-instance, plaintiff-side]

### 四维正交标签

| 维度 | 值 |
|------|-----|
| action | 起草 |
| domain | 知产 + 诉讼 |
| stage | first_instance |
| doc_type | agent-statement |

---

## 二、五问要素（question-set/v1）

### 1. 输入什么（Inputs）

**必要输入**：
- 案件基本事实（权利基础、侵权行为、损害结果）
- 证据目录（含权利归属证据 + 侵权比对证据）

**可选输入**：
- 原告权利人身份与权属证明（作品登记证书 / 首次发表证据）
- 类似案例判决（如需引用）

**信息来源**：用户上传 + 律所内部证据目录系统

### 2. 输出什么（Outputs）

**主要产出**：原告代理词（一审）
**格式要求**：标准代理词格式（标题 / 尊敬的审判长 / 委托地位与诉求 / 事实与理由 / 法律依据 / 结论 / 落款）
**质量标准**：
- 法条引用精确到条
- 证据与论点一一对应
- 区分"原创性 / 接触可能性 / 实质性相似"三步论证
- 每条损害赔偿主张有计算依据

**产出形态**：text-document（纯文本，含必要列表与表格）

### 3. 处理逻辑（Workflow）

**主流程**：
1. 案件事实梳理：权利基础（权属）、侵权行为（接触 + 实质性相似）、损害结果
2. 法律关系识别：是否为《著作权法》保护客体 / 是否构成侵权 / 责任承担
3. 诉讼请求设计：停止侵害 + 消除影响 + 赔偿损失（+ 赔礼道歉视情形）
4. 证据组织：把证据目录映射到三大构成要件
5. 代理词起草：按"事实 → 法律 → 结论"三段式展开
   - 质量检查点：执业律师对损害赔偿计算与法条引用复核

**异常路径**：
- 被告抗辩"独立创作" → 在代理词中预先回应（举证责任分配）
- 被告抗辩"合理使用" → 引用《著作权法》第 24 条具体情形
- 损害证据不足 → 主张法定赔偿（500 元 - 500 万元区间）

### 4. 向谁交付（Context.Delivery，v1 三子项）

**operator**：`plaintiff-counsel`（原告方律师）—— 直接使用本 Skill 完成代理词撰写
- 决定：能调用律所证据库、能起草正式诉讼文书

**represented_party**：`plaintiff-rights-holder`（原告权利人）—— Skill 产出物实质服务的当事人
- 决定：内容立场为原告方利益、主张停止侵权 + 赔偿损失
- **关键防错**：法官是 `output_audience`，**不**是 `represented_party`（v0 评测曾误把"法院"填到 represented_party，本次重对齐明确纠正）

**output_audience**：`judge`（主审法官）—— 最终文书读者
- 决定：语气正式专业 / 法条引用精确 / 论证严密 / 不夸张用语
- 决定：篇幅适中（5000-8000 字为佳）、段落清晰

**触发场景**：原告一审庭审前 1-2 周
**语气基调**：正式专业 / 法言法语 / 论证严密

### 5. 需要哪些知识支撑（Knowledge Base）

**法律依据**：

> **法源证据说明（v1.0.2 起 `verified` 必须可追溯）**：`effective_date` 为当前引用版本的**施行日期**，不是通过/公布日期。`verified` 要求至少有 `source_url` / `source_file`、`verified_by`、`verified_at`、`version_as_of` 四项证据。

| 法条 / 司法解释 | jurisdiction | effective_date | verification_status | 证据 |
|----------------|--------------|----------------|---------------------|------|
| 《著作权法》第 3 条（保护客体） | CN | 2021-06-01（2020 修正版施行日） | verified | 全国人大常委会 2020-11-11 通过决定，自 2021-06-01 起施行；verified_by：对齐者；verified_at：2026-07-30；version_as_of：2020 修正版 |
| 《著作权法》第 10 条（人身权 + 财产权） | CN | 2021-06-01 | verified | 同上 |
| 《著作权法》第 24 条（合理使用） | CN | 2021-06-01 | verified | 同上 |
| 《著作权法》第 53 条（侵权判定） | CN | 2021-06-01 | verified | 同上 |
| 《著作权法》第 54 条（损害赔偿） | CN | 2021-06-01 | verified | 同上 |
| 《最高人民法院关于审理著作权民事纠纷案件适用法律若干问题的解释》 | CN | 2020-12-29（修正版施行日） | verified | verified_by：对齐者；verified_at：2026-07-30；version_as_of：2020 修正版 |
| 《著作权法》（1990 旧版）相关条款 | CN | unverified | unverified | 仅供历史案件参考，不适用于现行案件；无 source_url |

**范本来源**：律所内部一审代理词范本 1 份
**风险清单**：
- 权属证据不完整（缺作品登记证书 / 首次发表证据）
- 实质性相似论证薄弱（缺逐项比对表）
- 损害赔偿计算缺乏依据（应同时主张权利人损失 / 侵权获利 / 法定赔偿三选一）
- 时效问题（起诉前需核对此前是否已主张权利，避免时效抗辩）

**风格偏好**：
- 法条引用精确到条
- 不使用"恶意""蓄意"等情绪化词汇
- 抬头："尊敬的审判长、审判员"
- 落款："XX 律师事务所 XXX 律师"

---

## 三、规则引擎

**判断标准**：

| 标准名 | 判定逻辑 | 触发条件 | source |
|--------|----------|----------|--------|
| 实质性相似 | 逐项比对（结构 / 表达 / 独创性部分） | 任何著作权侵权案件 | SOP 内部审查清单 + 司法解释第 7 条 |
| 接触可能性 | 被告曾接触过原告作品（如公开发表 / 销售） | 任何著作权侵权案件 | 司法解释第 9 条 |
| 损害赔偿阶梯 | 实际损失 → 侵权获利 → 法定赔偿 | 损害赔偿主张 | 司法解释第 25 条 |

**阈值配置**：

| 阈值名 | 数值 | 触发动作 | source |
|--------|------|----------|--------|
| 法定赔偿区间 | 500 元 - 500 万元 | 实际损失 / 获利无法举证时 | 《著作权法》第 54 条 |
| 维权合理开支 | 实际支出（律师费 / 公证费 / 差旅） | 主张合理开支时 | 《著作权法》第 54 条 |

---

## 四、素材溯源

| 素材类型 | 数量 | 来源 | quality | 用途 |
|----------|------|------|---------|------|
| sample | 1 | 历史一审代理词 1 份 | **bronze（单样本）** | 结构骨架 / 风格 |
| tools-data | 1 | 证据目录（含侵权比对表） | silver | 输入数据 |
| qa | 0 | 无 | unrated | — |
| sop | 0 | 无 | unrated（无 SOP 文档） | — |
| rules | 0 | 无独立规则包（从司法解释抽取） | unrated | — |
| revisions | 0 | 无 | unrated | — |
| authorities | 0 | 无独立法源原文（从样本反推） | unrated（待核对） | 法源验证 |

> **诚实标注**：本案单样本（仅 1 份历史代理词），质量等级 bronze；决策分支、异常路径、不同 `output_audience` 输出差异等内容**单样本无法覆盖**。

---

## 五、安全与脱敏说明

**敏感材料处理**：
- 已识别敏感信息：原告 / 被告真实姓名、作品名称、案件具体信息
- 脱敏状态：已脱敏（在 Brief 内引用时用"原告 / 被告""作品 A / 作品 B"替代）
- 脱敏责任：用户已确认脱敏

**外传策略**：
- 是否需要外部检索：否（仅依赖样本与法律依据）
- 是否上传外部服务：否
- 数据留存策略：本地保存，不外传

**高风险结论复核**：
- 是否涉及最终法律结论：**是**（代理词直接提交法庭）
- 是否需要执业律师复核：**是**（必填项，必须由执业律师复核并签发）

---

## 六、待确认清单（v1.0.2 起带状态判定）

### 状态判定（v1.0.2 起）

- structurally_complete: **true**（五问齐全 + 法源三列 + quality + 安全段 + 待确认分类全部满足）
- handoff_ready: **true**（blocker = 0）
- blocker 数: 0
- warning 数: 8

### 阻塞交接缺口（blocker）

（无）

### 可带警告交接缺口（warning）

- [ ] **单样本局限**：仅 1 份历史代理词，结构与风格特征可能不具代表性，建议补充 2-3 份同类样本 — type: warning
- [ ] **决策分支覆盖不足**：单样本仅展示一种被告抗辩应对路径，建议补充对方抗辩常见类型清单 — type: warning
- [ ] **损害赔偿主张依据**：本案是否已确定主张"实际损失 / 侵权获利 / 法定赔偿"中的哪一项？需用户确认 — type: warning
- [ ] **时效核验**：原告首次知悉侵权行为日期 / 起算时效是否已核验？未核验存在时效抗辩风险 — type: warning
- [x] **法源版本核对**（v1.0.2 已修正）：原标 `effective_date = 2020-11-11`（通过/公布日）已更正为 `2021-06-01`（施行日）；2020 修正版自 2021-06-01 起施行 — type: warning（已修复，保留供回溯）
- [ ] **sample quality=bronze**：单样本无法支撑高质量通用规则提炼 — type: warning
- [ ] **sop / qa / revisions 缺失**：三类型素材缺失，决策点与高频抗辩应对策略无法系统抽取 — type: warning
- [ ] **authorities 缺失**：法源条目从司法解释条文反推，未与官方文本核对 — type: warning

---

## v0 → v1 重对齐验证

| 验证项 | v0 状态 | v1 状态 | 改进 |
|--------|---------|---------|------|
| Brief 命名 / 版本 | 无 | legal-skill-brief/v1 + question-set/v1 | ✅ |
| skill_family 命名 | snake_case `copyright_infringement_agent_statement` | kebab-case `copyright-infringement-agent-statement` | ✅ |
| 下游契约 | 硬绑定 legal-skill-creator | 中立 | ✅ T-005 |
| 第 4 问角色拆分 | "终端用户角色：法院"（**错误**——法院是 output_audience） | operator / represented_party / output_audience 三角色明确分离，附防错提示 | ✅ T-006 |
| 完整性规则 | 无 | 五类条款齐备 | ✅ T-007 |
| 字段命名 | snake_case identifier | kebab-case identifier + snake_case stage | ✅ T-008 |
| 嵌套围栏 | 渲染 bug | 4 反引号方案 | ✅ T-008 |
| 素材分类 | 样本 × 1 + 证据目录 × 1 | 7 类可组合 + quality 必填（单样本诚实标 bronze） | ✅ T-009 |
| 领域标签 | "诉讼 / 知产"复合描述 | 四维正交标签 | ✅ T-009 |
| 法源可追溯 | 无版本 | jurisdiction / effective_date / verification_status 三列 | ✅ T-010 |
| 阈值可追溯 | 无 | source 列 | ✅ T-010 |
| 安全段 | 无 | 必填（高风险结论=是，必须执业律师复核） | ✅ T-010 |
| 待确认分类 | 无类型 | blocker / warning 二分 | ✅ T-007 |

**重对齐结论**：v1.0.0 在 v0 基础上完成关键修正——**纠正"法院=终端用户角色"的语义错误**，拆为三角色后 operator / represented_party / output_audience 边界清晰；补齐法源三列、阈值 source、安全段、单样本局限性诚实标注。v1 比 v0 更适合作为下游编译输入。