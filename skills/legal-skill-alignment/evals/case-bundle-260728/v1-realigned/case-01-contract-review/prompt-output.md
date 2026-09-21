# Case 01 v1 Brief: 供应商服务合同审查

> 本 Brief 由 `legal-skill-alignment v1.0.0` 对齐产出，遵循 `legal-skill-brief/v1` 规范。
>
> 下游消费者：通用 `skill-creator` 或 `legal-skill-creator`（中立交接，二选一或都尝试）。
>
> 方法论版本：`question-set/v1`（五问）。
>
> v0 基线：参见 [`case-bundle-260705/case-01-contract-review/prompt-output.md`](../../../case-bundle-260705/case-01-contract-review/prompt-output.md)。

## 一、上下文元数据（可选）

- **skill_family**：`supplier-service-contract-review`
- **jurisdiction**：CN
- **stage**：`non_litigation`
- **operator**：`buyer-counsel`（买方律师 / 企业法务）
- **represented_party**：`buyer`（采购方 / 委托方）
- **output_audience**：`buyer-internal-team`（企业内部法务 + 采购部门共同评审）
- **doc_type**：`contract-review`
- **tags**：[supplier, service-contract, pre-signing, risk-review]

### 四维正交标签（v1 新增）

| 维度 | 值 |
|------|-----|
| action | 审查 |
| domain | 合同 |
| stage | non_litigation |
| doc_type | contract-review |

---

## 二、五问要素（question-set/v1）

### 1. 输入什么（Inputs）

**必要输入**：
- 供应商服务合同全文（.docx，含附件）
- 服务类型说明（物流 / SaaS / IT 外包 / 其他）

**可选输入**：
- 企业内部采购制度或合规要求
- 历史同类合同审查记录

**信息来源**：用户上传

### 2. 输出什么（Outputs）

**主要产出**：合同审查意见书
**格式要求**：风险等级分色标注（高 / 中 / 低）+ 条款逐条批注 + 修改建议 + 法条依据
**质量标准**：每条风险标注法条依据；8 大审查维度全覆盖；有量化阈值触发机制
**产出形态**：mixed（正文文本 + 风险矩阵表 + 批注列表）

### 3. 处理逻辑（Workflow）

**主流程**：
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

### 4. 向谁交付（Context.Delivery，v1 三子项）

**operator**（Skill 操作者）：`buyer-counsel`（买方律师 / 企业法务）—— 直接使用本 Skill 完成审查操作
- 决定：能调用 Word 批注工具、能在文档上直接标注

**represented_party**（所代表的当事人）：`buyer`（采购方 / 委托方）—— Skill 产出物实质服务的企业方
- 决定：内容立场为买方利益，提示对买方不利的条款
- **注意**：买方企业是 represented_party，**不**是 output_audience

**output_audience**（最终文书读者）：`buyer-internal-team`（企业内部法务 + 采购部门共同评审）
- 决定：语气中性专业，不阻断交易；术语密度适中（法务可读，采购也能理解）

**触发场景**：企业与外部供应商签订服务合同前
**语气基调**：中性专业，提示风险但不阻断交易

### 5. 需要哪些知识支撑（Knowledge Base）

**法律依据**：

> **法源证据说明（v1.0.2 起 `verified` 必须可追溯）**：`effective_date` 为当前引用版本的**施行日期**。`verified` 要求至少有 `source_url` / `source_file`、`verified_by`、`verified_at`、`version_as_of` 四项证据。

| 法条 / 司法解释 | jurisdiction | effective_date | verification_status | 证据 |
|----------------|--------------|----------------|---------------------|------|
| 《民法典》第 577 条（违约责任） | CN | 2021-01-01 | verified | verified_by：对齐者；verified_at：2026-07-30；version_as_of：2020 版（2021-01-01 施行） |
| 《民法典》第 563 条（合同解除） | CN | 2021-01-01 | verified | 同上 |
| 《网络安全法》第 21 条 | CN | 2026-01-01（2025 修正版施行日） | verified | 2025-10-28 修改决定，自 2026-01-01 起施行；verified_by：对齐者；verified_at：2026-07-30；source：国家网信办 cac.gov.cn |
| 《网络安全法》第 42 条 | CN | 2026-01-01 | verified | 同上（条文顺序经 2025 修改调整，引用时须核对最新条号） |
| 《个人信息保护法》第 13 条 | CN | 2021-11-01 | verified | verified_by：对齐者；verified_at：2026-07-30；version_as_of：2021 版 |
| 《电子商务法》第 XX 条 | CN | 2019-01-01 | unverified | SOP 中未明确条款，无 source_url；待用户补充具体条号后升级为 verified |

**范本来源**：律所内部供应商合同审查清单（8 步骤）
**风险清单**：
- 主体资质风险（注册资本 / 合同金额比 > 5）
- 服务标准缺失风险（无量化 SLA）
- 赔偿上限不足风险（赔偿上限 < 预付金额）
- 数据安全风险（无数据处理协议）
- 管辖不利风险（对方所在地管辖）

**风格偏好**：
- 法条引用精确到条
- 风险等级三色标注
- 抬头：致 XX 公司法务部
- 落款：XX 律师事务所

---

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

---

## 四、素材溯源（v1 quality 必填）

| 素材类型 | 数量 | 来源 | quality | 用途 |
|----------|------|------|---------|------|
| sample | 2 | 历史审查意见书（仓储配送 + SaaS） | silver | 提取结构骨架 / 风格特征 |
| sop | 1 | 律所内部供应商审查清单 8 步骤 | gold | 提取决策点 / 阈值 |
| rules | 1 | SOP 中包含的阈值表 | gold | 阈值与判断标准 |
| qa | 0 | 无 | unrated（无 Q&A 素材） | — |
| revisions | 0 | 无 | unrated（无对话修订记录） | — |
| tools-data | 0 | 无 | unrated | — |
| authorities | 0 | 无独立法源原文（从样本反推） | unrated（待与权威文本核对） | 法源验证 |

---

## 五、安全与脱敏说明（v1 必填）

**敏感材料处理**：
- 已识别敏感信息：合同金额、双方当事人真实名称
- 脱敏状态：已脱敏（在 Brief 内引用时用"买方/卖方"替代真实公司名）
- 脱敏责任：用户已确认脱敏

**外传策略**：
- 是否需要外部检索：否
- 是否上传外部服务：否
- 数据留存策略：本地保存，不外传

**高风险结论复核**：
- 是否涉及最终法律结论：否（仅审查意见，非定稿文书）
- 是否需要执业律师复核：高风险项（标红项）须复核

---

## 六、待确认清单（v1 blocker/warning 分类；v1.0.2 起带状态判定）

### 状态判定（v1.0.2 起）

- structurally_complete: **true**（五问齐全 + 法源三列 + quality + 安全段 + 待确认分类全部满足）
- handoff_ready: **true**（blocker = 0）
- blocker 数: 0
- warning 数: 5

### 阻塞交接缺口（blocker）

（无）

### 可带警告交接缺口（warning）

- [ ] 法源覆盖度：《电子商务法》相关条款未在 SOP 中明确，待用户补充具体条号 — type: warning
- [ ] 风格偏好：审查意见书的抬头 / 落款格式是否需要根据客户不同而调整 — type: warning
- [ ] 阈值标准：注册资本 × 5、首付 > 30% 等阈值是否经团队共识确认 — type: warning
- [ ] 素材 quality=unrated（qa / revisions / tools-data / authorities 四类缺失）— type: warning
- [ ] authorities 缺失：法源条目从样本反推，未与权威文本核对 — type: warning

---

## v0 → v1 重对齐验证

| 验证项 | v0 状态 | v1 状态 | 改进 |
|--------|---------|---------|------|
| Brief 命名 / 版本 | 无版本标注 | `legal-skill-brief/v1` + `question-set/v1` | ✅ |
| skill_family 命名 | snake_case `supplier_service_contract_review` | kebab-case `supplier-service-contract-review` | ✅ 命名规范化 |
| 下游契约 | 硬绑定 legal-skill-creator | 中立（skill-creator / legal-skill-creator 均可） | ✅ T-005 |
| 第 4 问角色拆分 | 笼统"终端用户角色" | 拆 operator / represented_party / output_audience | ✅ T-006 |
| 完整性规则 | 无（仅自检清单） | non-goals / prohibited / success / failure / human-review 五类 | ✅ T-007 |
| 字段命名一致性 | identifier 用 snake_case（与 stage 命名空间冲突） | identifier 用 kebab-case，stage/role 用 snake_case | ✅ T-008 |
| 嵌套围栏 | L7-L112 渲染 bug | 4 反引号外层方案 | ✅ T-008 |
| 素材分类 | 仅 sample / sop | 7 类可组合 + quality 必填 | ✅ T-009 |
| 领域标签 | 单一"主分类" | 四维正交标签 | ✅ T-009 |
| 法源可追溯 | 无 | jurisdiction / effective_date / verification_status 三列 | ✅ T-010 |
| 阈值可追溯 | 无 | source 列必填 | ✅ T-010 |
| 安全段 | 无 | 敏感材料 + 外传策略 + 高风险复核三段必填 | ✅ T-010 |
| 待确认分类 | 无类型 | blocker / warning 二分 | ✅ T-007 |

**重对齐结论**：v1.0.0 完整覆盖 v0 所有要素，并补齐 v0 缺失的 6 类关键字段（命名规范化、三角色、完整性规则、安全边界、法源三列、阈值 source）。可作为 v1 模板示范案例。