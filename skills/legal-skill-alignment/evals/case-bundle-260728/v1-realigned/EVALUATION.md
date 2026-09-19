# Case Bundle 260728 v1-realigned: 评估汇总

> 本文件记录 `legal-skill-alignment v1.0.0` 在 3 个历史法律场景上的**重对齐**评估结果。
>
> 评估目的：验证 v1.0.0 协议层重构（T-005~T-010）是否解决了 v0 评测识别的全部断点（B1-B6），并展示 v1 规范的完整样貌。
>
> **历史快照说明（v1.0.6）**：本 bundle 的法源证据字段早于 v1.0.6 的逐字段可追溯规则，不能证明当前 `verified` 门槛或 `handoff_ready` 判定；仅用于回溯 v1.0.0 的设计演变，不得作为当前发布或稳定性证据。
>
> **v0 基线**：[`case-bundle-260705/EVALUATION.md`](../../case-bundle-260705/EVALUATION.md)

---

## 一、场景覆盖（与 v0 一致，便于对照）

| Case | 领域 | v0 素材 | v1 素材分类（v1 七类） | 对齐路径 |
|------|------|--------|-----------------------|----------|
| case-01 | 合同 | 样本×2 + SOP×1 | sample × 2 + sop × 1 + rules × 1 + authorities × 0 | 有素材 |
| case-02 | 诉讼 / 知产 | 样本×1 + 证据目录×1 | sample × 1 + tools-data × 1 | 有素材（单样本） |
| case-03 | 合规 | 样本×1 + SOP×1 | sample × 1 + sop × 1 + rules × 1 | 有素材（混合） |

---

## 二、v1 重对齐验证矩阵

每行一项 v1 必填字段 / 协议改进；每列一个 case；值 = 是否满足。

| 验证项 | case-01 | case-02 | case-03 |
|--------|---------|---------|---------|
| **T-005 交接契约** | | | |
| Brief 顶部标注 `legal-skill-brief/v1` | ✅ | ✅ | ✅ |
| 标注 `question-set/v1` | ✅ | ✅ | ✅ |
| 移除"对齐 legal-skill-creator 第二章"引用 | ✅ | ✅ | ✅ |
| 下游消费者中立（skill-creator / legal-skill-creator） | ✅ | ✅ | ✅ |
| 下游兼容性双列表（明确告知下游） | ✅ | ✅ | ✅ |
| **T-006 三角色拆分** | | | |
| `operator` 明确 | ✅ buyer-counsel | ✅ plaintiff-counsel | ✅ compliance-officer |
| `represented_party` 明确 | ✅ buyer | ✅ plaintiff-rights-holder | ✅ app-company |
| `output_audience` 明确 | ✅ buyer-internal-team | ✅ judge（**v0 误填纠正**） | ✅ company-management |
| 法官/法院 vs represented_party 防错提示 | ✅ | ✅ | n/a |
| 五问总数仍为 5（仅第 4 问拆三子项） | ✅ | ✅ | ✅ |
| **T-007 完整性规则** | | | |
| SKILL.md 完整性规则段（non-goals / prohibited / success / failure / human-review） | ✅ | ✅ | ✅ |
| 待确认清单按 `blocker` / `warning` 分类 | ✅ | ✅ | ✅ |
| **T-008 字段修复** | | | |
| skill_family kebab-case | ✅ `supplier-service-contract-review` | ✅ `copyright-infringement-agent-statement` | ✅ `app-data-compliance-scan` |
| stage / role / doc_type snake_case | ✅ | ✅ | ✅ |
| 字段命名约定段（在 standard-prompt-output.md） | ✅ | ✅ | ✅ |
| 嵌套围栏 4 反引号方案 | ✅ | ✅ | ✅ |
| 法源三列 jurisdiction / effective_date / verification_status | ✅ | ✅ | ✅ |
| 规则引擎 source 列 | ✅ | ✅ | ✅ |
| 素材 quality 列必填 | ✅ | ✅ | ✅ |
| **T-009 素材 / 分类重构** | | | |
| 七类素材分类全部显式标注 | ✅ | ✅ | ✅ |
| 四维正交标签（action / domain / stage / doc_type） | ✅ | ✅ | ✅ |
| 跨领域任务（case-03 涉合规+知产） | n/a | n/a | ✅ |
| 非文书型任务（如需） | n/a（本案为文书型） | n/a | n/a |
| stage 枚举扩展（case-03 改用 post_launch 精确） | n/a | n/a | ✅ B2 修复 |
| 输出格式多样化指引（mixed 形态） | n/a | n/a | ✅ B5 修复 |
| **T-010 安全边界** | | | |
| 敏感材料识别清单（在 alignment-strategies.md 顶部） | ✅ | ✅ | ✅ |
| 安全段必填（敏感材料 + 外传策略 + 高风险复核） | ✅ | ✅ | ✅ |
| 法源三列已含（与 T-008 联动） | ✅ | ✅ | ✅ |
| 高风险结论必须执业律师复核（case-02 明确） | n/a（审查意见） | ✅（代理词=是） | 部分（高风险项+监管报送=是） |

---

## 三、v0 断点修复情况

| v0 断点 | 严重度 | v1 修复情况 | 验证 case |
|---------|--------|-------------|-----------|
| **B1** 第 4 问"向谁交付"推断依赖 | 中 | ✅ T-006 三角色拆分 + 防错提示；alignment-strategies.md 加三角色交叉验证 | case-01 / case-02 / case-03 全部明确三角色 |
| **B2** stage 枚举不完整 | 中 | ✅ T-009 legal-domain-mapping.md 扩展刑事 / 家事 / 劳动仲裁；case-03 重对齐后用 post_launch | case-03 已精确化 |
| **B3** 单样本对齐通用性 | 低 | ✅ alignment-strategies.md 单样本策略保留并诚实标注 quality=bronze | case-02 标 bronze + warning 7 条 |
| **B4** 阈值和判断标准无处安放 | 中 | ✅ standard-prompt-output.md 规则引擎段保留 + source 列 | case-01 / case-03 规则引擎完整 |
| **B5** 输出格式多样性 | 低 | ✅ standard-prompt-output.md 输出格式多样化指引 + 表格化明确约定 | case-03 mixed 形态完整描述 |
| **B6** skill-creator 可编译性 | 待测 | ⚠️ **本次重对齐未实测**（v1 协议已与下游解耦，需另起任务 T-001） | 待 T-001 跑通 |

---

## 四、v1 新增改进（v0 没有的项）

- **第七类素材 authorities 单独管理**：v0 法源混杂在 sample / sop 中；v1 起 authorities 作为独立类型管理，便于回溯。
- **quality 必填（含 unrated）**：v0 quality 完全缺失；v1 必须标注，unrated 也要注明原因。
- **法源 verification_status**：v0 法源无可信度判断；v1 起 unverified 法源**不**当作确定性依据。
- **敏感材料识别清单**：v0 无；v1 alignment-strategies.md 顶部 10 类典型敏感信息清单。
- **外部检索用户确认**：v0 无；v1 case-03 明确"已确认可检索公开监管文件"作为安全段必填。
- **高风险结论复核**：v0 无；v1 case-02（代理词）+ case-03（监管报送）明确标注"是 / 必须复核"。
- **四维正交标签**：v0 单一"主分类 + 辅分类"；v1 四维正交支持跨领域任务。
- **v0 → v1 迁移指南**：在 standard-prompt-output.md 末尾，每个 v0 老用法都有对应 v1 新用法对照表。

---

## 五、与 v0 EVALUATION 字段映射表对照

v0 的"字段映射检查"表（alignment 输出 → legal-skill-creator 字段）已不再适用——v1 起 alignment 与下游解耦，无硬绑定映射。

下表改为 **v1 内部自检**：

| v1 内部检查项 | case-01 | case-02 | case-03 |
|---------------|---------|---------|---------|
| legal-skill-brief/v1 顶部标注 | ✅ | ✅ | ✅ |
| question-set/v1 顶部标注 | ✅ | ✅ | ✅ |
| 元数据（可选）齐全 | ✅ | ✅ | ✅ |
| skill_family kebab-case | ✅ | ✅ | ✅ |
| 五问每问有答案或"待补" | ✅ | ✅ | ✅ |
| 第 4 问三子项齐全 | ✅ | ✅ | ✅ |
| 法源三列齐 | ✅ | ✅ | ✅ |
| 规则引擎 source 列齐 | ✅ | ✅ | ✅ |
| 素材溯源 quality 列齐 | ✅ | ✅ | ✅ |
| 安全段三部分齐 | ✅ | ✅ | ✅ |
| 待确认按 blocker / warning 分类 | ✅ | ✅ | ✅ |
| 阻塞交接缺口（blocker）= 0 | ✅ | ✅ | ✅ |
| warning 项有明确建议补充方式 | ✅ | ✅ | ✅ |
| **v1.0.2 状态判定** | | | |
| `structurally_complete` 标注 | ✅ true | ✅ true | ✅ true |
| `handoff_ready` 标注 | ✅ true | ✅ true | ✅ true |
| blocker 数 / warning 数明确 | ✅ 0/5 | ✅ 0/8 | ✅ 0/9 |
| **v1.0.2 法源证据门槛（T-013）** | | | |
| `verified` 条目带证据列 | ✅（含网络安全法 2026 修正版） | ✅（著作权法 effective_date 已从 2020-11-11 更正为 2021-06-01） | ✅（网络安全法 effective_date 已从 2017-06-01 更正为 2026-01-01） |
| `effective_date` = 施行日期（非通过/公布日） | ✅ | ✅ | ✅ |

**结论**：3 个案例全部通过 v1 内部自检。

---

## 六、与 v0 重对齐的诚实说明

| 项 | v0 状态 | v1 处理 | 说明 |
|----|---------|----------|------|
| case-01 阈值共识待确认 | warning | warning（保留）| v1 也未确认团队阈值共识；这是用户决策而非 alignment 能解决的 |
| case-02 单样本局限 | 未标注 | warning 7 条 | v1 诚实标注单样本风险 |
| case-03 阶段从 non_litigation → post_launch | n/a | 已修正 | v0 B2 断点的修复体现 |
| case-03 输出格式未明确 | warning | 已明确 mixed + 表格 5 列约定 | v0 B5 断点的修复体现 |
| 素材 quality | 未填 | 全部填写（含 unrated）| v1 必填项 |
| 敏感信息脱敏 | 未声明 | 必填项已声明 | v1 安全段必填 |
| 下游契约 | 硬绑定 legal-skill-creator | 中立 | v1 T-005 核心变更 |

---

## 七、TASKS 关联

- 本次 v1 重对齐对应 TASKS T-005~T-010 全部完成。
- B6（下游编译实测）作为 T-001 待完成项，仍需后续真实下游验证。
- 历史评测 case-bundle-260705/ 完整保留为 v0 快照。
- 本次评测 case-bundle-260728/v1-realigned/ 作为 v1 模板示范。

---

## 八、后续评测任务（不属于本次范围）

- **T-011**：增加 1-2 个零起点访谈案例（无素材路径）
- **T-011**：增加不应触发 alignment 的负向案例
- **T-011**：将 v1 Brief 交给下游（通用 skill-creator / legal-skill-creator）实测编译，保留失败日志和人工确认记录
- **T-002 / T-004**：苏格拉底式访谈路径无素材验证
- **T-003**：法律分类识别自动化可信度评估（v1 起改为四维正交标签，需重新评估）
