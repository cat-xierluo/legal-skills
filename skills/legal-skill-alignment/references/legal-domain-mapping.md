# 法律领域识别与正交标签（question-set/v1）

> 本文档定义如何从素材或场景描述中识别一组**正交标签**，对应 SKILL.md 步骤 1A.2 与步骤 2。
>
> **v1 变更**：从单一"主分类 + 辅分类"改为**四维正交标签**（任务动作 / 法律领域 / 程序阶段 / 文书类型），不再强制单一法律模板骨架；新增"非文书型任务"专章；stage 枚举扩展刑事 / 家事 / 劳动仲裁等之前缺失领域。

---

## 一、正交标签体系（v1 核心）

v1 起每个 Skill 用 **四个独立维度** 的标签来描述：

| 维度 | 含义 | 典型值 |
|------|------|--------|
| **任务动作类型（action）** | Skill 做什么动作 | 起草 / 审查 / 谈判 / 起诉 / 答辩 / 尽调 / 扫描 / 抽取 / 组织 / 监控 / 评估 / 教学 |
| **法律领域（domain）** | 涉及的法律分支 | 合同 / 诉讼 / 合规 / 尽调 / 知产 / 劳动 / 公司 / 家事 / 税务 / 刑事 / 其他 |
| **程序阶段（stage）** | 时间或程序位置 | 见下文 stage 枚举（按领域分组） |
| **文书类型 / 产出形态（doc_type）** | 产出物类别 | `demand-letter` / `complaint` / `answer` / `contract-review` / `compliance-report` / `tool` / `data-pack` / `mixed` |

### 为什么叫"正交"

四个维度**互不依赖**：

- 同一 `action` 可跨多个 `domain`（如"审查"动作可用于合同、劳动、刑事）
- 同一 `domain` 可有多个 `stage`（如"诉讼"领域涵盖 pre_litigation / first_instance / ...）
- 同一 `doc_type` 可用于不同任务场景（如 `tool` 类可承载各种动作）

v0.x 强制"单一法律模板骨架"的做法（每个 Skill 只能选一个主分类）已被废除。

### 标签组合示例

| Skill | action | domain | stage | doc_type |
|-------|--------|--------|-------|----------|
| 供应商服务合同审查 | 审查 | 合同 | non_litigation | contract-review |
| 著作权侵权代理词 | 起草 | 知产 + 诉讼 | first_instance | agent-statement |
| App 数据合规扫描 | 扫描 | 合规 + 知产 | post_launch | compliance-report |
| 证据组织器 | 组织 | 诉讼 | first_instance | data-pack（**非文书型**） |
| 合同审查规则抽取器 | 抽取 | 合同 | non_litigation | tool（**非文书型**） |
| 并购尽调报告 | 尽调 | 公司 + 劳动 + 知产 + 税务 | full_scope | due-diligence-report |
| 庭审应对教学 | 教学 | 诉讼 | first_instance | mixed |

---

## 二、从素材中识别标签

### 2.1 从素材中识别 action + domain + stage + doc_type

| 信号词 | 倾向 | 维度 |
|--------|------|------|
| 起诉状、答辩状、判决书、庭审、立案、上诉 | 诉讼 | domain |
| 合同、协议、条款、审查意见、谈判 | 合同 | domain |
| 合规、内控、风控、整改、监管 | 合规 | domain |
| 尽调、尽职调查、并购、收购、DD | 尽调 | domain |
| 商标、专利、著作权、商业秘密、侵权 | 知产 | domain |
| 解除劳动合同、工伤、仲裁、工资、社保 | 劳动 | domain |
| 股权、股东、章程、决议、增资 | 公司 | domain |
| 遗嘱、继承、离婚、抚养、财产分割 | 家事 | domain |
| 发票、纳税、税务稽查、增值税 | 税务 | domain |
| 刑事、侦查、取保、辩护、罪名 | 刑事 | domain |
| 审查 / 核对 / 找出问题 | 审查 | action |
| 起草 / 撰写 / 代写 | 起草 | action |
| 扫描 / 体检 / 检查 | 扫描 | action |
| 抽取 / 提取 / 提炼 | 抽取 | action |
| 组织 / 整理 / 编排 | 组织 | action |
| 监控 / 跟踪 / 报告 | 监控 | action |

### 2.2 从场景描述中识别

| 用户描述 | 倾向 |
|---------|------|
| "我常给企业做合规体检" | action=扫描，domain=合规 |
| "我做知识产权维权" | action=起诉/起草，domain=知产 |
| "我代理劳动争议原告" | action=起草/答辩，domain=劳动+诉讼，stage=arbitration |
| "我审合同审得多了" | action=审查，domain=合同 |
| "我把历史文书整理成证据目录" | action=组织，domain=诉讼，doc_type=data-pack |

---

## 三、stage 枚举（v1 扩展）

> 选择 stage 时优先匹配最精确的值；无法精确匹配时选最近似的上级分类；如果实在没有匹配，标 `unclassified` 并在 Brief 待确认清单中说明。

### 3.1 合同

| stage | 说明 |
|-------|------|
| `pre_contract` | 签约前审查 |
| `in_contract` | 履约中 |
| `post_contract` | 争议后 |

### 3.2 诉讼

| stage | 说明 |
|-------|------|
| `pre_litigation` | 诉前 |
| `first_instance` | 一审 |
| `second_instance` | 二审 |
| `retrial` | 再审 |
| `enforcement` | 执行 |

### 3.3 合规

| stage | 说明 |
|-------|------|
| `pre_launch` | 上线前 |
| `post_launch` | 运营中 |
| `annual_audit` | 年度审计 |
| `regulatory_inquiry` | 监管问询应对 |
| `incident_response` | 事件响应 |

### 3.4 尽调

| stage | 说明 |
|-------|------|
| `preliminary` | 初步尽调 |
| `full_scope` | 全面尽调 |
| `post_closing` | 交割后 |

### 3.5 知产

| stage | 说明 |
|-------|------|
| `pre_filing` | 申请前 |
| `prosecution` | 审查中 |
| `enforcement` | 维权中 |
| `licensing` | 许可交易 |

### 3.6 刑事（v1 增补）

| stage | 说明 |
|-------|------|
| `investigation` | 侦查阶段 |
| `prosecution` | 审查起诉 |
| `trial` | 审判 |
| `appeal` | 上诉 |
| `execution` | 执行 |
| `parole` | 假释 |

### 3.7 家事（v1 增补）

| stage | 说明 |
|-------|------|
| `pre_divorce` | 离婚前 |
| `divorce` | 离婚 |
| `custody` | 抚养纠纷 |
| `estate` | 继承 |
| `adoption` | 收养 |

### 3.8 劳动仲裁（v1 增补）

| stage | 说明 |
|-------|------|
| `pre_arbitration` | 仲裁前 |
| `arbitration` | 仲裁中 |
| `litigation_after_arbitration` | 仲裁后诉讼 |
| `enforcement` | 执行 |

### 3.9 通用

| stage | 说明 |
|-------|------|
| `non_litigation` | 非诉通用 |
| `advisory` | 咨询 |
| `unclassified` | 无法精确分类（须在 Brief 中说明） |

---

## 四、doc_type 枚举

### 4.1 文书类（text-document / table / mixed）

| doc_type | 说明 |
|----------|------|
| `demand-letter` | 律师函 |
| `complaint` | 起诉状 |
| `answer` | 答辩状 |
| `agent-statement` | 代理词 |
| `contract-review` | 合同审查意见 |
| `contract-draft` | 合同草案 |
| `due-diligence-report` | 尽调报告 |
| `compliance-report` | 合规报告 |
| `legal-opinion` | 法律意见书 |
| `evidence-list` | 证据目录 |
| `memo` | 备忘录 |
| `pleading` | 其他诉讼文书 |

### 4.2 工具与数据包类（tool / data-pack）

| doc_type | 说明 |
|----------|------|
| `tool` | 可调用的工具（如规则抽取器、扫描器） |
| `data-pack` | 数据包（如证据组织结果、风险矩阵） |
| `dashboard` | 看板 / 报表 |
| `checklist` | 检查清单 |

### 4.3 混合格式

| doc_type | 说明 |
|----------|------|
| `mixed` | 同时含文本 / 表格 / 列表 / 工具输出的混合 |

---

## 五、非文书型任务（v1 新增专章）

v0.x 仅支持文书型 Skill。v1 起，工具型 / 数据型 / 扫描型任务也有正式路径。

### 5.1 工具型（`doc_type = tool`）

**典型场景**：

- 合同审查规则抽取器：从历史合同中抽取审查规则
- 合规扫描工具：批量扫描文档是否合规
- 法条检索工具：在本地法源库中检索条款
- 风险评分器：基于规则对输入打分

**Brief 中的差异**：

- `Outputs` 段：`产出形态 = tool-output`，说明输入格式 / 输出格式 / 调用方式（CLI / API / 嵌入式）
- `Workflow` 段：按工具三段式描述（输入 → 处理逻辑 → 输出）
- 不强制 `抬头 / 落款` 等文书专属字段
- `operator` 常为 `ai-operator` 或自动化脚本
- `represented_party` 视工具服务对象而定
- `output_audience` 视工具输出给谁消费而定（机器 / 律师 / 客户）

### 5.2 数据包型（`doc_type = data-pack`）

**典型场景**：

- 证据组织器：把案件材料整理成结构化数据包
- 类案检索结果：以表格 / JSON 输出同类案例
- 风险矩阵：输出风险评分矩阵

**Brief 中的差异**：

- `Outputs` 段：`产出形态 = data-output`（或 table / json）
- `Workflow` 段：以"输入数据 → 整理逻辑 → 输出结构"组织
- 不强调"质量检查点由律师复核"——重点是数据准确性而非法律意见

### 5.3 跨领域任务

**典型场景**：

- 并购尽调 = 尽调 + 公司 + 劳动 + 知产 + 税务 的复合 Skill
- IPO 法律准备 = 合规 + 知产 + 公司 + 证券 的复合 Skill
- 集团内部合规 = 合规 + 劳动 + 数据合规 + 反舞弊 的复合 Skill

**Brief 中的差异**：

- 每个领域在 `Knowledge Base` 中分段落组织
- `Workflow` 按时间顺序串联跨领域动作（而非塞进单一模板）
- `stage` 选主领域 stage，其他领域在描述中补充
- `tags` 字段列出所有相关领域标签

---

## 六、识别不确定时的处理

如果素材或描述模糊，**不要硬猜**：

1. 向用户提供 2-3 个候选标签组合，让用户选。
2. 如果用户自己也不确定，先用"通用"标签起步：
   - `action = advisory`
   - `domain = 其他`
   - `stage = unclassified`
   - `doc_type = mixed`
3. 等五问访谈完再回填具体标签。
4. 在 Brief 待确认清单中按 `warning` 列出"标签待精确化"。

宁可起步用通用标签，也不要错分领域导致模板选错。