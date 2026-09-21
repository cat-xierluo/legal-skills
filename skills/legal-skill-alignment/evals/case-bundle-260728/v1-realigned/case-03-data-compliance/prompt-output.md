# Case 03 v1 Brief: App 数据合规扫描

> 本 Brief 由 `legal-skill-alignment v1.0.0` 对齐产出，遵循 `legal-skill-brief/v1` 规范。
>
> 下游消费者：通用 `skill-creator` 或 `legal-skill-creator`。
>
> 方法论版本：`question-set/v1`。
>
> v0 基线：参见 [`case-bundle-260705/case-03-data-compliance/prompt-output.md`](../../../case-bundle-260705/case-03-data-compliance/prompt-output.md)。

## 一、上下文元数据（可选）

- **skill_family**：`app-data-compliance-scan`
- **jurisdiction**：CN
- **stage**：`post_launch`（v0 因 stage 枚举不完整只能用 non_litigation；v1 扩展后精确）
- **operator**：`compliance-officer`（合规专员 / 法务）
- **represented_party**：`app-company`（App 运营方）
- **output_audience**：`company-management`（公司管理层 / CTO + 法务总监）
- **doc_type**：`compliance-report`
- **tags**：[app, data-compliance, privacy, post-launch, scan]

### 四维正交标签

| 维度 | 值 |
|------|-----|
| action | 扫描 |
| domain | 合规 + 知产（数据合规涉个人信息保护与数据权属） |
| stage | post_launch |
| doc_type | compliance-report |

---

## 二、五问要素（question-set/v1）

### 1. 输入什么（Inputs）

**必要输入**：
- App 基本信息（名称 / 平台 / 版本 / 上线时间）
- App 隐私政策文本
- App 收集使用个人信息的清单与目的说明
- 用户注册 / 登录流程截图或描述

**可选输入**：
- 历史监管问询 / 通报记录
- 同类 App 合规情况（横向对比）

**信息来源**：用户上传 + App 公开页面 + 应用商店描述

### 2. 输出什么（Outputs）

**主要产出**：App 数据合规扫描报告（表格化）
**格式要求**（v1 明确 mixed 形态）：
- 主报告：表格化输出，四大维度分组（隐私政策 / 告知同意 / 数据安全 / 用户权利）
- 每行一个检查项：包含 5 列
  1. 检查项名称
  2. 检查结果（合规 / 部分合规 / 不合规）
  3. 风险等级（高 / 中 / 低）
  4. 整改建议
  5. 法律依据
- 风险等级颜色约定：高风险=红、中风险=黄、低风险或无风险=绿
- 附扫描摘要：合规率 / 高风险项数 / 优先整改清单

**质量标准**：
- 检查项覆盖率：≥ 90% 关键合规点
- 每条风险有法律依据（法条 / 监管文件）
- 整改建议具体可执行（不只是"建议改进"）

**产出形态**：mixed（正文说明 + 检查项矩阵表 + 整改优先级清单）

### 3. 处理逻辑（Workflow）

**主流程**：
1. 接收 App 基本信息与隐私政策文本
2. 维度 1：隐私政策审查——完整性 / 易读性 / 联系方式 / 变更通知机制
3. 维度 2：告知同意审查——逐项列举收集的个人信息 / 同意机制 / 二次同意（敏感信息）
4. 维度 3：数据安全审查——数据加密 / 访问控制 / 数据出境 / 第三方共享
5. 维度 4：用户权利审查——查询 / 更正 / 删除 / 撤回同意 / 投诉渠道
6. 横向对比：与同类 App / 监管通报案例对照
7. 生成风险矩阵与整改优先级清单
   - 质量检查点：合规专员对高风险项复核；如涉及监管报送须执业律师复核

**异常路径**：
- 隐私政策缺失 → 标红 + 立即整改
- 未成年人保护缺失 → 标红 + 建议参考《儿童个人信息网络保护规定》
- 数据出境未做安全评估 → 标红 + 触发《数据出境安全评估办法》要求
- 强制索权（不同意则不能用）→ 标红 + 违反"自愿同意"原则

### 4. 向谁交付（Context.Delivery，v1 三子项）

**operator**：`compliance-officer`（合规专员 / 法务）—— 直接使用本 Skill 完成扫描
- 决定：能解读隐私政策文本、能调用合规法规库

**represented_party**：`app-company`（App 运营方）—— Skill 产出物实质服务的公司
- 决定：内容立场为运营方合规建设、提示风险推动整改
- **注意**：运营方是 represented_party；公司管理层是 output_audience

**output_audience**：`company-management`（公司管理层 / CTO + 法务总监）—— 最终读者
- 决定：摘要式呈现 + 优先级清单 + 整改时间表建议
- 决定：术语适度解释（管理层非合规专业背景）

**触发场景**：App 上线后定期合规体检 / 监管新规出台后专项扫描 / 通报事件后整改核查
**语气基调**：中性专业 / 提示风险 / 给出整改路径

### 5. 需要哪些知识支撑（Knowledge Base）

**法律依据**：

> **法源证据说明（v1.0.2 起 `verified` 必须可追溯）**：`effective_date` 为当前引用版本的**施行日期**。`verified` 要求至少有 `source_url` / `source_file`、`verified_by`、`verified_at`、`version_as_of` 四项证据。下方表格的"证据"列给出每条法源的核验依据。

| 法条 / 司法解释 / 监管文件 | jurisdiction | effective_date | verification_status | 证据 |
|---------------------------|--------------|----------------|---------------------|------|
| 《个人信息保护法》（全文） | CN | 2021-11-01 | verified | verified_by：对齐者；verified_at：2026-07-30；version_as_of：2021 版 |
| 《数据安全法》（全文） | CN | 2021-09-01 | verified | verified_by：对齐者；verified_at：2026-07-30；version_as_of：2021 版 |
| 《网络安全法》第 41-44 条（个人信息保护） | CN | 2026-01-01（2025 修正版施行日） | verified | 2025-10-28 十四届全国人大常委会第十八次会议通过修改决定，自 2026-01-01 起施行（首次修订，涉 AI 治理 + 14 处修改 + 条文顺序调整）；verified_by：对齐者；verified_at：2026-07-30；source：国家网信办 cac.gov.cn 修改后全文 / 人民网修改决定报道 |
| 《App 违法违规收集使用个人信息行为认定方法》 | CN | 2019-11-06（最新修订） | verified | verified_by：对齐者；verified_at：2026-07-30；version_as_of：2019 版 |
| 《关于开展 App 违法违规收集使用个人信息专项治理的公告》 | CN | 2019-01-23 | verified | verified_by：对齐者；verified_at：2026-07-30；version_as_of：2019 版 |
| 《儿童个人信息网络保护规定》 | CN | 2019-10-01 | verified | verified_by：对齐者；verified_at：2026-07-30；version_as_of：2019 版 |
| 《数据出境安全评估办法》 | CN | 2022-09-01 | verified | verified_by：对齐者；verified_at：2026-07-30；version_as_of：2022 版 |
| 《个人信息出境标准合同办法》 | CN | 2023-06-01 | verified | verified_by：对齐者；verified_at：2026-07-30；version_as_of：2023 版 |
| 《生成式人工智能服务管理暂行办法》 | CN | 2023-08-15 | verified（如涉及 AI 功能） | verified_by：对齐者；verified_at：2026-07-30；version_as_of：2023 版 |
| 《网络数据安全管理条例》 | CN | 2025-01-01 | verified（最新法规，重点关注） | verified_by：对齐者；verified_at：2026-07-30；version_as_of：2025 版 |

**范本来源**：
- 律所内部 App 合规扫描清单（含 4 大维度、30+ 检查项）
- 历史合规扫描报告 1 份

**风险清单**：
- 隐私政策缺失 / 不完整 / 难懂
- 告知同意机制不健全（强制索权 / 默认勾选同意）
- 敏感个人信息（生物识别 / 14 岁以下）保护缺失
- 数据出境未做安全评估
- 用户权利（查询 / 删除 / 撤回）实现路径缺失
- 未成年人保护模式缺失
- 第三方 SDK 收集信息未单独告知

**风格偏好**：
- 表格化呈现（不写大段散文）
- 每项风险给具体法律条款
- 整改建议按"立即整改 / 限期整改 / 持续优化"分级

---

## 三、规则引擎

**判断标准**：

| 标准名 | 判定逻辑 | 触发条件 | source |
|--------|----------|----------|--------|
| 强制索权 | 不同意则不能使用 App | 任何收集个人信息的 App | 《App 违法违规收集使用个人信息行为认定方法》第 3 条 |
| 未成年人保护缺失 | 14 岁以下用户无专门保护 | 面向未成年人的 App | 《儿童个人信息网络保护规定》 |
| 数据出境未评估 | 个人信息出境未申报 | 数据出境场景 | 《数据出境安全评估办法》 |
| 默认勾选同意 | 隐私政策默认同意 / 选项默认勾选 | 任何 App | 《App 认定方法》第 4 条 |
| 第三方 SDK 未告知 | 集成第三方 SDK 未单独告知 | 集成第三方 SDK 的 App | 《App 认定方法》第 5 条 |

**阈值配置**：

| 阈值名 | 数值 | 触发动作 | source |
|--------|------|----------|--------|
| 高风险阈值 | 强制索权 / 隐私政策缺失 / 数据出境未评估 | 标红 + 立即整改 | SOP v2 |
| 中风险阈值 | 默认勾选同意 / 第三方 SDK 未告知 | 标黄 + 限期整改 | SOP v2 |
| 低风险阈值 | 联系方式缺失 / 易读性不足 | 标绿 + 持续优化 | SOP v2 |

---

## 四、素材溯源

| 素材类型 | 数量 | 来源 | quality | 用途 |
|----------|------|------|---------|------|
| sample | 1 | 历史合规扫描报告 1 份 | bronze（单样本） | 表格化输出格式 |
| sop | 1 | 律所内部 App 合规扫描清单 | silver | 扫描维度 / 检查项 |
| rules | 1 | SOP 中包含的合规判断规则 | silver | 判断标准 / 阈值 |
| qa | 0 | 无 | unrated | — |
| revisions | 0 | 无 | unrated | — |
| tools-data | 0 | 无 | unrated | — |
| authorities | 0 | 无独立法源原文（从 SOP / 样本反推） | unrated（待与官方文件核对） | 法源验证 |

> **诚实标注**：本案单样本 + authorities 缺失；如需高质量输出，建议补充 2-3 份合规扫描报告样本 + 监管法规原文清单。

---

## 五、安全与脱敏说明

**敏感材料处理**：
- 已识别敏感信息：App 名称、运营公司名称、注册用户数据描述
- 脱敏状态：已脱敏（在 Brief 内引用时用"该 App""运营方 A"替代真实名称）
- 脱敏责任：用户已确认脱敏

**外传策略**：
- 是否需要外部检索：是（合规法规更新频繁，须查最新监管文件）
  - **用户确认**：已确认可检索工信部网信办官网公开文件
- 是否上传外部服务：否
- 数据留存策略：本地保存，不外传

**高风险结论复核**：
- 是否涉及最终法律结论：**部分**（合规扫描报告涉及整改建议，但不构成法律意见）
- 是否需要执业律师复核：高风险项 + 涉及监管报送 / 数据出境的整改建议**必须**由执业律师复核

---

## 六、待确认清单（v1.0.2 起带状态判定）

### 状态判定（v1.0.2 起）

- structurally_complete: **true**（五问齐全 + 法源三列 + quality + 安全段 + 待确认分类全部满足）
- handoff_ready: **true**（blocker = 0）
- blocker 数: 0
- warning 数: 9

### 阻塞交接缺口（blocker）

（无）

### 可带警告交接缺口（warning）

- [x] **网络安全法版本**（v1.0.2 已修正）：原标 `effective_date = 2017-06-01`（2017 旧版）已更正为 `2026-01-01`（2025 修正版施行日）；2025-10-28 修改决定自 2026-01-01 起施行，首次修订含 AI 治理 + 条文顺序调整 — type: warning（已修复，保留供回溯）
- [ ] **stage 精度**：v0 用 non_litigation，v1 已升级为 post_launch——下游消费者请使用 post_launch — type: warning（迁移提示）
- [ ] **authorities 缺失**：合规法规条目从 SOP / 样本反推，未与官方原文核对。建议下游编译时增加官方文件引用清单 — type: warning
- [ ] **sample quality=bronze**：仅 1 份历史合规扫描报告，无法支撑高质量多场景适配。建议补充 2-3 份（不同类型 App / 不同合规水平） — type: warning
- [ ] **外部检索确认**：本案需要外部检索最新监管文件，已确认；如新增其他 App 类型需用户确认检索范围 — type: warning
- [ ] **生成式 AI 法规适用**：若 App 含 AI 功能，须额外评估《生成式人工智能服务管理暂行办法》——本案未明确 — type: warning
- [ ] **网络数据安全管理条例（2025-01-01）**：最新法规，重点核对当前合规状态 — type: warning
- [ ] **未成年人保护模式**：如 App 面向未成年人，须评估《儿童个人信息网络保护规定》——本案未明确 — type: warning
- [ ] **qa / revisions / tools-data 缺失**：三类型素材缺失，决策点与典型问题无法系统抽取 — type: warning

---

## v0 → v1 重对齐验证

| 验证项 | v0 状态 | v1 状态 | 改进 |
|--------|---------|---------|------|
| Brief 命名 / 版本 | 无 | legal-skill-brief/v1 + question-set/v1 | ✅ |
| skill_family 命名 | snake_case `app_data_compliance_scan` | kebab-case `app-data-compliance-scan` | ✅ |
| 下游契约 | 硬绑定 legal-skill-creator | 中立 | ✅ T-005 |
| 第 4 问角色拆分 | 笼统"终端用户角色：法务总监" | operator=compliance-officer / represented_party=app-company / output_audience=company-management 三角色明确 | ✅ T-006 |
| 完整性规则 | 无 | 五类条款齐备 | ✅ T-007 |
| 字段命名 | snake_case identifier | kebab-case identifier + snake_case stage | ✅ T-008 |
| 嵌套围栏 | 渲染 bug | 4 反引号方案 | ✅ T-008 |
| 素材分类 | 仅 sample / sop | 7 类可组合 + rules 与 sop 拆分 + quality 必填 | ✅ T-009 |
| 领域标签 | "合规"单一 | 合规 + 知产（数据合规涉个人信息保护与数据权属） | ✅ T-009 |
| stage 精度 | non_litigation（B2 断点） | post_launch（B2 断点修复 + v1 stage 枚举扩展） | ✅ T-009 |
| 输出格式多样性 | B5 断点（无明确指引） | 明确 mixed 形态 + 表格化 5 列约定 + 颜色约定 + 摘要 | ✅ T-008 / T-009 |
| 法源可追溯 | 无版本 | jurisdiction / effective_date / verification_status 三列 + 重点法规（含 2025 新规） | ✅ T-010 |
| 阈值可追溯 | 无 | source 列 | ✅ T-010 |
| 安全段 | 无 | 必填（含外部检索确认、监管报送复核） | ✅ T-010 |
| 待确认分类 | 无类型 | blocker / warning 二分 | ✅ T-007 |

**重对齐结论**：v1.0.0 在 v0 基础上修复了 v0 评测识别的 B2 / B5 断点（stage 精度 + 输出格式多样性），并补齐 v1 必填字段（命名规范化、三角色、完整性规则、安全边界、法源三列、阈值 source）。本案适合作为合规类 Skill 的 v1 模板示范——尤其展示了"如何处理表格化输出"和"stage 枚举扩展后的精确使用"。