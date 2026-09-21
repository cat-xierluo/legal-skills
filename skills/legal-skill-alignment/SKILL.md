---
name: legal-skill-alignment
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.0.7"
license: CC-BY-NC
description: 写法律 Skill 前的前置对齐步骤——通过苏格拉底式提问把零散的法律经验/素材/直觉厘清为结构化 Brief（legal-skill-brief/v1），交给 skill-creator 编译。适用于律师想把文书经验、办案 SOP、咨询记录做成 Skill 的场景。不适用于非法律类 Skill 创建，也不适用于用户已提供完整可执行 Brief 且明确要求直接编译的情况。
---

# 法律 Skill 目标对齐

## 定位

**本 Skill 是写法律 Skill 前的前置步骤**——通过苏格拉底式提问，帮助你把零散的"经验/素材/直觉"转化为一份结构化、可被通用 `skill-creator` 等下游编译器消费的 **Legal Skill Brief v1**（详见 [standard-prompt-output.md](references/standard-prompt-output.md)）。本 Skill **不直接生成 Skill 文件**，只产出喂给下游编译器的 Brief。

**分工**：

- `legal-skill-alignment`（本 Skill）：负责"想清楚要做什么"——把意图结构化。
- 通用 `skill-creator`（或你环境中可用的法律领域 Skill 编排器）：负责"做出来"——把 Brief 编译为 SKILL.md / references / scripts。

---

## 方法论：question-set/v1（当前默认五问）

本 Skill 当前落地采用 **question-set/v1**（五问实例）——从五个关键维度对齐目标：

| # | 要素 | 解决的问题 | 在 Brief v1 中对应的字段 |
|---|------|-----------|--------------------------|
| 1 | **输入什么** | 这个 Skill 吃什么数据 | `## 二、1. 输入什么（Inputs）` |
| 2 | **输出什么** | 产出长什么样 | `## 二、2. 输出什么（Outputs）` |
| 3 | **处理逻辑** | 从输入到输出怎么走 | `## 二、3. 处理逻辑（Workflow）` |
| 4 | **向谁交付**（v1 拆三子项） | 谁用、谁代表、写给谁看 | `## 二、4. 向谁交付（Context.Delivery）` |
| 5 | **需要哪些知识支撑** | 法律依据、范本、风险清单、风格偏好 | `## 二、5. 需要哪些知识支撑（Knowledge Base）` |

第 4、5 问是相对"经典三问"补全的两问——**向谁交付**决定语气与详略，**需要哪些知识支撑**决定这个 Skill 是"空壳模板"还是"有肉的真本事"。

### 为什么叫 question-set/v1 而不是"五问法"

- **不锁数字**：v1 是当前默认实例（5 问），未来 v2 可扩展为 6 问 / 7 问 / 缩减为 4 问，Skill 名不变。
- **版本化约束**：v1 锁定的不是问数，而是**完整性规则**（见下文）和**字段语义**（如下文"第 4 问拆三子项"）。
- **扩展方式**：修改本 SKILL.md 的问数 + 对应 references，发布新版本（如 `question-set/v2`）。

### v1 第 4 问的三子项

第 4 问在 v1 中拆为三类角色，三者**经常被混淆**，必须分别明确：

| 子项 | 含义 | 典型值 | 决定什么 |
|------|------|--------|---------|
| `operator` | 直接使用本 Skill 的角色 | 律师 / 律师助理 / 法务 / 合规专员 / AI 操作员 | 能调用什么工具 / 看到哪些字段 |
| `represented_party` | Skill 产出物实质服务的当事人 | 原告 / 被告 / 雇主 / 收购方 | 内容立场 / 利益偏好 / 保密等级 |
| `output_audience` | 最终文书的读者 | 法官 / 对方律师 / 客户 / 监管机关 | 语气基调 / 详略取舍 / 术语密度 |

**最常见错误**：把 `output_audience` 写成 `represented_party`（如把"法官"误填到 `represented_party`）。法官是读者，不是被代表的当事人。

---

## 完整性规则（question-set/v1 必读）

产出 Brief 前必须满足以下规则。完整性是**对齐内部约束**，不阻塞下游消费者接收（下游不做 schema 校验），但**阻塞 alignment 自身判定为"可交接"**。

### 非目标（Non-goals）

本 Skill **不做**：

- **不替代法律判断**：厘清出的处理逻辑和风险清单需由执业律师最终确认。
- **不产出最终文书**：只产出 Brief，下游编译才是 Skill 文件。
- **不做合规审查**：Brief 的内容不构成法律意见或合规承诺。
- **不验证法源时效**：法源生效日期由用户在 `effective_date` 与 `verification_status` 中标注，未确认的标 `unverified`。

### 禁止事项（Prohibited）

- **禁止编造法条 / 案例**：每条法源引用必须可溯源；无法提供原文 URL 或本地原文路径的，标 `verification_status: unverified`。
- **禁止把个案事实硬编码为通用规则**：单样本反推出的规则必须标"待补"，不直接当通用结论。
- **禁止替用户做价值判断**：当事人立场 / 策略选择 / 风险偏好，由用户确认而非 alignment 推断。
- **禁止默默推断缺口**：每个推断要素必须在"待确认清单"中标注推断依据和确认方式。

### 成功标准与状态判定（Success Criteria，v1.0.2 起拆分两状态）

一份 Brief 的可交接性用**两个独立状态**判定，避免"字段齐全但含 blocker 却标可交接"的歧义：

#### `structurally_complete`（结构完整）

Brief 满足以下全部条件即判定为 `structurally_complete = true`：

- 五问每问都有答案（明确答案 / 推断答案 / 标"待补"，三者之一）
- 法源条目带 `effective_date` 与 `verification_status`（即便值是 `unverified`）
- 素材溯源 quality 字段已填写（`unrated` 也算）
- 安全与脱敏说明段已填（即便无敏感信息也填"无敏感信息识别"）
- 待确认清单已按 `blocker` / `warning` 分类

> `structurally_complete` 只看"字段是否齐全 + 是否标注"，**不看 blocker 是否清零**。含"待补"标记的 Brief 仍可满足此状态。

#### `handoff_ready`（可交接）

在 `structurally_complete = true` 基础上，**且待确认清单中 blocker 项 = 0**，才判定为 `handoff_ready = true`。

存在以下任一情况，`handoff_ready = false`（即使 `structurally_complete = true`）：

- `operator` 未确认（仅 warning 级别标"待补"**不**算未确认；但完全空白或无任何推断依据算 blocker）
- 五问中任何一问完全空白且未标"待补"（同时导致 `structurally_complete = false`）
- Brief 产出涉及具体法律建议，但没有任何可追溯的关键法源原文（`source_url` 或 `source_file`）

**关键法源缺失的唯一判定**：只要 Brief 会产出具体法律建议（包括法律意见、诉讼/应诉策略、起诉状或答辩状、合同定稿或审查结论、需据法源作出的合规整改建议），且相应关键法源没有原文 URL 或本地原文路径，就必须登记一项 `blocker`，并判定 `handoff_ready = false`。是否已知或可推定法域不改变该结论。纯流程整理、素材归档或不包含具体法律建议的工具型 Brief，法源原文缺失可登记为 `warning`。

#### 状态转换规则（v1.0.2 核心修复，解决 T-014 歧义）

| 当前状态 | 待确认清单 blocker 数 | 操作 |
|---------|---------------------|------|
| `structurally_complete = false` | — | 回到对应步骤补全字段，**不**交付 |
| `structurally_complete = true`，`handoff_ready = false` | ≥ 1 | 交付时**必须**在 Brief 顶部与待确认清单显式标注"含 blocker，不建议下游直接编译"；由用户决定是否强行交接 |
| `structurally_complete = true`，`handoff_ready = true` | 0 | 可正常交付；warning 项允许保留 |

**判定唯一性**：任何 Agent 读同一份 Brief，只要按上述规则，对 `structurally_complete` / `handoff_ready` 的判定结果必须一致。如果出现"一个 Agent 判可交接、另一个判不可"的分歧，以 `handoff_ready = (blocker 数 = 0)` 为准。

### 失败条件（Failure Conditions）

出现以下情况，Brief 应**判定为 `structurally_complete = false` 而非交付**：

- 五问中任何一问完全空白且未标"待补"
- 涉及最终法律结论但未声明"需执业律师复核"
- 素材中含明显敏感信息（身份证 / 手机号 / 当事人真实姓名）但未声明脱敏状态

> 关键法源缺失不改变 `structurally_complete` 的字段完整性判断；只要缺口已如实列为 `blocker`，则应判定为 `structurally_complete = true`、`handoff_ready = false`，不得把它同时写成结构不完整和可带 warning 交接。

### 人工复核点（Human Review）

以下产出**必须**由执业律师复核（与 T-010 安全边界联动）：

- 最终法律意见书 / 起诉状 / 答辩状 / 合同定稿
- 起诉应诉策略建议
- 合规整改建议（涉及监管报送的）
- 高额标的（合同金额 / 索赔金额 > 一定阈值，建议用户团队阈值表）的合同审查结论

---

## 工作流程

### 步骤 0：判定路径（最先做）+ 安全预检

读用户第一条消息，判断走哪条路径：

| 用户说话特征 | 路径 |
|------------|------|
| 提到"这是我的样本/SOP/Q&A/历史文书/案例"，或粘贴/上传了素材 | **有素材路径** |
| 说"我想做个 XX skill 但不知道怎么开始""我脑子里有经验但没整理过""教我做" | **无素材路径** |
| 同时满足 | 先走有素材路径，再用访谈补缺口 |

**安全预检**（无论哪条路径都要做）：

1. **敏感材料识别**：检查用户上传或粘贴的内容是否含明显敏感信息（见 [alignment-strategies.md](references/alignment-strategies.md) 顶部的"敏感材料识别清单"）。
2. **脱敏提示**：如有敏感信息，提示用户："检测到 [敏感信息类型]，请确认是否已脱敏 / 是否需要本 Skill 协助脱敏（仅提示，不自动改写原文件）"。
3. **外传确认**：默认**不**上传 / 共享给任何外部服务。如需外部检索或服务，**必须**显式询问用户确认。

不要在没素材的情况下硬走有素材路径——会产出空洞的 Brief。

#### 步骤 0.5：负向触发判定（v1.0.4 起强制）

在判定路径**之后、开始访谈/厘清之前**，必须先用下表排除**不应触发**本 Skill 的场景。命中任一行即**不进入**对齐流程，按"建议去向"收尾（不产出 Brief）。

| 用户输入特征 | 判定 | 建议去向 |
|------------|------|---------|
| 非法律类 Skill 创建（视频下载 / 读书笔记 / 通用工具 / 内容创作） | ❌ 不触发 | 通用 `skill-creator` 或工具类技能 |
| 已提供完整可执行 Brief 且明确要求"直接编译 / 直接生成，别问我" | ❌ 不触发 | 直接交 `skill-creator` 编译 |
| 仅问"skill 是什么 / 怎么装 / 适不适合我"（使用咨询） | ❌ 不触发 | 通用帮助文档 / `skill-manager` |

**灰度场景**（命中下表须**先追问再判定**，不得直接触发或拒绝）：

| 用户输入特征 | 追问话术 | 倾向 |
|------------|---------|------|
| "帮律师做案件管理工具" | "核心是法律业务流程，还是通用排期/项目管理？" | 法律业务流程→触发；通用排期→不触发 |
| "审查合同条款合规性，但走技术合规" | 指出"技术合规 ≠ 法律合规" | 不触发 |
| "把公司审批流程做成 skill" | "流程是否涉及法律判断（合同/合规/劳动关系）？" | 涉及→触发；纯 OA→不触发 |

> 灰度判定唯一原则：**场景是否涉及法律领域**（合同/诉讼/合规/尽调/知产/劳动/公司/家事/税务/刑事）。不确定时问用户"你是想把法律经验做成 Skill 吗？"——答否则不触发。

### 步骤 1A：有素材路径——多分类厘清

#### 1A.1 材料分类（v1 起扩展为可组合类型）

v1 把素材分类从三类扩展为**七类可组合类型**（原 3 类保留并新增 4 类）：

| 分类 | 识别特征 | 厘清重点 |
|------|---------|---------|
| **样本（sample）** | 成品文书：律师函、起诉状、合同、审查意见 | 提炼结构骨架 + 风格特征 + 风险点清单 |
| **流程 SOP（sop）** | 步骤化文档：办案流程、审查清单、出庭准备 | 提炼决策点 + 分支条件 + 质量检查点 |
| **问答 Q&A（qa）** | 一问一答：客户咨询、培训答疑、内部 FAQ | 提炼高频问题 + 标准答法 + 例外情形 |
| **规则包（rules）** | 结构化规则：阈值表、判断标准、合规清单 | 提炼阈值与判断逻辑 + 来源 + 适用范围 |
| **对话修订记录（revisions）** | 历史对话 / 反复修改痕迹：律师-客户沟通、稿件修改批注 | 提炼风格偏好 + 反馈修订倾向 + 常见避坑 |
| **工具与数据源（tools-data）** | 工具输出、API 数据、数据库快照 | 提炼输入/输出格式 + 数据来源 + 联动方式 |
| **法源原文（authorities）** | 法律条文、司法解释、案例原文、监管文件 | 提炼法源时效 + 适用范围 + 引用格式 |

> **迁移提示**：v0.x 仅支持前三类，v1 起后四类也作为正式素材类型。各 references（[alignment-strategies.md](references/alignment-strategies.md)）给出每类的完整厘清策略。

#### 1A.2 领域 / 阶段 / 任务识别（v1 起正交标签）

v0.x 强制单一"法律模板骨架"。v1 起改为**正交标签**——四个维度独立选择：

| 维度 | 说明 | 典型值 |
|------|------|--------|
| **任务动作类型（action）** | Skill 做什么动作 | 起草 / 审查 / 谈判 / 起诉 / 答辩 / 尽调 / 扫描 / 抽取 / 组织 / 监控 |
| **法律领域（domain）** | 涉及的法律分支 | 合同 / 诉讼 / 合规 / 尽调 / 知产 / 劳动 / 公司 / 家事 / 税务 / 刑事 / 其他 |
| **程序阶段（stage）** | 时间或程序位置 | 见 [legal-domain-mapping.md](references/legal-domain-mapping.md) 的 stage 枚举 |
| **文书类型（doc_type）** | 产出形态 | demand-letter / complaint / answer / contract-review / compliance-report / **tool** / **data-pack** |

> v1 起不再强制所有 Skill 选单一法律模板骨架。一个跨领域任务可同时挂多个 `domain` 标签；非文书 / 工具型任务用 `doc_type: tool` 或 `data-pack` 标识。

#### 1A.3 引导补全五问

厘清完，把已从素材中提取的要素列给用户看，**明确指出缺口**（通常是第 4 问"向谁交付"的三子项和第 5 问"知识支撑"的法源时效），引导用户补全。一次只问 1-2 个缺口，不要一次抛出五个空字段吓退用户。

#### 1A.4 素材未覆盖要素的补全策略

当素材未直接体现某要素时，按以下策略处理，**不要默默推断**：

| 要素 | 素材中有线索 | 素材中无线索 |
|------|------------|------------|
| **第 4 问 `operator`** | 从使用场景反推，列出推断依据，**请用户确认** | 切换为访谈模式，用 [interview-guide.md](references/interview-guide.md) 第 4 问引导用户补全 |
| **第 4 问 `represented_party`** | 从文书抬头 / 落款 / 立场反推，**请用户确认** | 访谈模式补全；常见错误是误填为法官（法官是 `output_audience`） |
| **第 4 问 `output_audience`** | 从文书语言风格 / 引用格式反推，**请用户确认** | 访谈模式补全 |
| **第 5 问 法源 `effective_date`** | 从素材中标注的版本号 / 引用日期提取 | 标 `unverified` + 在待确认清单列出 |
| **第 3 问 决策点** | 从 SOP 提取步骤 + 从样本逆推决策点 | 标"决策点基于样本反推，可能遗漏分支" |

**关键原则**：推断不可怕，可怕的是不告知用户"这部分是我推断的"。每个推断要素必须在"待确认清单"中标注推断依据和确认方式。

---

### 步骤 1B：无素材路径——苏格拉底式访谈

不假设用户有任何素材。通过逐题引导，从用户脑中的"经验直觉"挖出五问答案。

访谈遵循三条铁律：

1. **一次一问**：不要一次列五个问题，用户会放弃。
2. **给锚点不给答案**：每个问题配 2-3 个具体例子帮助联想，但不替用户做决定。
3. **追问直到具体**：用户说"帮助客户"→ 追问"哪个阶段、什么角色、什么场景下需要帮助"。

第 4 问在 v1 拆为三个子问题逐次访谈（详见 [interview-guide.md](references/interview-guide.md)）：

- 4a：`operator` —— 谁会直接用这个 Skill？
- 4b：`represented_party` —— Skill 是为谁的立场服务的？
- 4c：`output_audience` —— 产出物最终交给谁看？

第 5 问在 v1 新增**法源时效确认**子问题（详见 [interview-guide.md](references/interview-guide.md)）：法律依据的生效日期 / 法域 / 是否最新有效。

---

### 步骤 2：识别一组正交标签

无论素材路径还是访谈路径，最终都要落到一组**正交标签**上：

- **任务动作类型**：审查 / 起草 / 扫描 / 抽取 / ...（详见 [legal-domain-mapping.md](references/legal-domain-mapping.md)）
- **法律领域**：合同 / 诉讼 / 合规 / ...
- **程序阶段**：见 stage 枚举
- **产出形态**：text-document / table / tool / data-pack

**标签组合示例**：

- 劳动合同审查 = 审查 + 劳动 + non_litigation + text-document
- App 数据合规扫描 = 扫描 + 合规 + post_launch + table
- 证据组织器 = 组织 + 诉讼 + first_instance + data-pack（**非文书型**）
- 知识产权维权策略 = 策略 + 知产 + enforcement + text-document

不再强制"单一法律模板骨架"，让跨领域 / 工具型任务能正确路由。

---

### 步骤 3：产出 legal-skill-brief/v1

把五问的答案组装成一份 **Legal Skill Brief v1**，格式遵循 [standard-prompt-output.md](references/standard-prompt-output.md)。

**Brief v1 关键约束**：

- Brief 顶部必须标注 `legal-skill-brief/v1` 与 `question-set/v1` 版本。
- 上下文元数据（`skill_family` / `jurisdiction` / `stage` / `operator` / `represented_party` / `output_audience` / `doc_type` / `tags`）为**可选 metadata**——下游消费者可不读，但不读不影响 Brief 完整性。
- 五问要素齐全，缺一不可。如果某要素访谈完仍无法确定，标 `[待用户确认]` 并在末尾"待确认清单"中按 `blocker` / `warning` 分类列出，**不要编造**。
- 法源条目**必须**带 `effective_date`（施行日期）/ `jurisdiction` / `verification_status` 三列，`verified` 条目须补 `证据` 列（见上）。
- 阈值与判断标准**必须**带 `source`（来源）。
- 素材溯源 quality **必须**填写（`unrated` 也算）。
- 安全与脱敏说明段**必须**填写（即便无敏感信息也填"无敏感信息识别"）。
- 标识符 `skill_family` 使用 **kebab-case**（如 `labor-contract-review`）；stage / role / doc_type 使用 snake_case。
- **第 4 问三子项防错核对（v1.0.4 起强制，对应 C-06）**：组装 Brief 前，**必须**对 `operator` / `represented_party` / `output_audience` 做一次互斥核对，并在 Brief 二.4 段末尾追加一行"防错核对"：逐一确认 (a) 三者均非空、(b) `represented_party` 不是读者类角色（法官/对方律师/监管机关属 `output_audience`，**绝不**填入 `represented_party`）、(c) `operator` 与 `output_audience` 不混淆。任一项存疑，不得静默放过，须在"待确认清单"标 blocker 或 warning。
- **法源缺失结构化降级（v1.0.6 起强制，对应 C-07/C-08）**：当素材或访谈**未提供任何 authorities 法源原文**（只有法条名称、或无任何法源线索）时，二.5 法律依据表**必须**显式写首行占位："法源原文缺失：以下条目均 `unverified`，待用户补充权威出处后升级"，且每一法源行 `verification_status` 一律 `unverified`、`effective_date` 填 `unverified`（**不得**凭名称编造施行日）。若 Brief 会产出具体法律建议，必须在"待确认清单"登记 `blocker`（"关键法源原文缺失"）并判定 `handoff_ready = false`；否则登记 warning（"法源时效未验证"）。法域已知或可定位不能降低 blocker 等级。
- **不登记空壳法源行（finding#1 回填，v1.0.5 起强制，对应 C-07/C-08 细化）**：二.5 法律依据表的每一行**必须**是「可定位的具体法源」——至少具备 `jurisdiction` + 可识别的法条/文件标识（条号、文件全称、或案例案号）+ `effective_date`/`verification_status` 三列。当素材仅给出**法源主题或法规名称**（如"《个人信息保护法》"）、但无条号、无原文、无适用指向时，**不得**为凑满表格而登记一行「名称 + 三列全空 `unverified`」的空壳条目；正确做法是：仅在降级首行占位中转录该名称作为"待补线索"，并在"待确认清单"明确列出"需补充《XX法》具体条号/适用版本"，由用户补齐后再登记正式法源行。例外：若素材已点名法域且名称足以定位法源范围（如 case-03 明确 CN + 四部法规名称），可转录名称行但 `effective_date`/`verification_status` 仍须 `unverified`，且须注明"仅名称、待补条号与施行日"，**不**得据此编写任何具体法律结论。

---

### 步骤 4：交付与移交

1. 把 Brief 展示给用户确认。
2. 用户确认后，**明确提示**下一步可调用：
   - 通用 `skill-creator`（自然语言意图友好）
   - 或你环境中可用的法律领域 Skill 编排器（路由决策友好）
3. 本 Skill 不直接产出 SKILL.md / references / scripts——那是下游的事。

---

## 五问要素自检清单

产出 Brief 前，**必须**逐条核对：

- [ ] 第 1 问 输入什么：列出了必要输入与可选输入，标注了信息来源
- [ ] 第 2 问 输出什么：明确了产出格式、字数/结构要求、质量标准、产出形态
- [ ] 第 3 问 处理逻辑：写了主要步骤、决策点、可选分支、异常路径
- [ ] 第 4 问 向谁交付（v1 三子项）：
  - [ ] `operator` 明确或标"待补"
  - [ ] `represented_party` 明确或标"待补"（**不与 `output_audience` 混淆**）
  - [ ] `output_audience` 明确或标"待补"
  - [ ] 触发场景 + 语气基调已写
- [ ] 第 5 问 知识支撑：法源带三列（jurisdiction / effective_date / verification_status）；范本来源；风险清单；风格偏好
- [ ] 上下文元数据：identifier 使用 kebab-case；stage / role / doc_type 使用 snake_case
- [ ] 规则引擎（如适用）：阈值与判断标准带 source
- [ ] 素材溯源：quality 字段已填
- [ ] 安全与脱敏：敏感信息状态、外传策略、高风险结论复核已写
- [ ] 待确认清单：按 blocker / warning 分类
- [ ] 状态判定：标注 `structurally_complete` 与 `handoff_ready`（见完整性规则段）

任一项缺失或模糊，回到对应步骤补全，**不放过半成品**。`handoff_ready = false` 时须在 Brief 顶部显式标注 blocker 数量。

---

## 安全与合规边界

本 Skill 在处理用户材料时遵循以下安全约束（与 [standard-prompt-output.md](references/standard-prompt-output.md) 的"五、安全与脱敏说明"段联动）：

### 敏感材料处理

- **默认不假设用户已脱敏**：处理历史文书、咨询记录、内部 SOP 时，主动识别明显敏感信息（见 [alignment-strategies.md](references/alignment-strategies.md) 顶部"敏感材料识别清单"）。
- **提示但不自动改写原文件**：发现敏感信息后，提示用户脱敏并请其确认，不擅自修改用户提供的内容。
- **Brief 中默认使用脱敏表述**：用户提供的真实姓名 / 金额 / 案件名在 Brief 内引用时，建议替换为脱敏形式（如"买方/卖方""XX 公司"）。

### 禁止默认外传

- **任何外部检索 / 上传 / 分享须由用户显式确认**。默认行为是不外传、不上传、不调用外部 API。
- 如需联网检索（如查最新司法解释），**先告知用户再执行**。

### 法源时点与版本

- 每条法源引用**必须**包含 `effective_date`（**施行日期**，不是通过日 / 公布日）与 `jurisdiction`（法域）。
- 用户未确认时效的法源，标 `verification_status: unverified`，**不当作确定性依据**输出。
- 涉及监管规则 / 行业规范的，须额外标注最近一次更新日期。
- **verified 证据门槛**（v1.0.2 起）：标 `verified` 的法源必须满足最小证据要求（`source_url` / `source_file` + `verified_by` + `verified_at` + `version_as_of`）；仅有法条名称或从样本反推时**不得**升级为 `verified`（详见 [standard-prompt-output.md](references/standard-prompt-output.md)）。

### 高风险结论必须执业律师复核

以下产出在 Brief 中必须标注"需执业律师复核"：

- 最终法律意见书 / 起诉状 / 答辩状 / 合同定稿类文书
- 起诉应诉策略建议（涉及程序选择、时效判断）
- 合规整改建议（涉及监管报送或重大经营变更）
- 高额标的（用户团队阈值表定义）的合同审查结论

alignment **不替代**律师复核；下游编译出的 Skill 也不替代。

---

## 输入要求

本 Skill 接受以下输入：

1. **素材路径**：用户提供的文件路径（支持 .md / .txt / .docx）
2. **粘贴内容**：用户直接粘贴的样本 / SOP / Q&A / 规则 / 对话修订 / 工具数据 / 法源原文
3. **场景描述**：用户用自然语言描述"我想做一个 XX skill"
4. **混合**：上述任意组合

---

## 输出要求

- 一份 **Legal Skill Brief v1**（markdown 格式，遵循 [standard-prompt-output.md](references/standard-prompt-output.md)）
- Brief 末尾附"待确认清单"（按 blocker / warning 分类）
- 明确提示调用通用 `skill-creator`（或法律领域 Skill 编排器）完成编译

---

## 适用场景

- 律师把多年积累的某类文书做成可复用 Skill
- 律所把内部 SOP 沉淀为团队级 Skill
- 从客户咨询记录中提炼可复用问答 Skill
- 法律培训师把课程方法论转化为 Skill
- 把规则包 / 阈值表沉淀为可执行 Skill
- 把工具 / 数据源打包成可调用 Skill
- 跨领域任务（同时涉及合同 + 诉讼 + 合规的复合 Skill）
- 任何"我有经验/素材，想做成 Skill 但不知如何下手"的场景

---

## 边界

- **不直接生成 Skill 文件**：只产出 Brief v1，编译交给下游。
- **不替代法律判断**：厘清出的"处理逻辑"和"风险清单"需由执业律师最终确认。
- **不做证据不足的推断**：素材或访谈不足以支撑的结论，标 `[需补充]`，不臆测。
- **不外传用户数据**：默认不调用外部服务；外部操作须用户显式确认。
- **不验证法源时效**：法源是否现行有效由用户在 `effective_date` / `verification_status` 中标注，alignment 不替用户做判断。

### 不应触发的场景（负向边界，T-017）

以下场景**不应**触发本 Skill：

- **非法律类 Skill 创建**：通用工具类、内容创作类、非法律业务流程类 Skill 的前置对齐，不归本 Skill。判断标准：场景是否涉及法律领域（合同 / 诉讼 / 合规 / 尽调 / 知产 / 劳动 / 公司 / 家事 / 税务 / 刑事）。
- **用户已提供完整可执行 Brief 且明确要求直接编译**：当用户已给出结构完整的 Brief 并明确说"直接编译 / 直接生成 SKILL.md"，应直接交给 skill-creator，不走本 Skill 的对齐流程。
- **用户只是问"什么是 Skill / 怎么用 Skill"**：这是使用咨询，不是创建前置对齐，不触发。

如果不确定是否应触发，优先询问用户"你是想把法律经验做成 Skill 吗？"——若回答为否，则不触发。
