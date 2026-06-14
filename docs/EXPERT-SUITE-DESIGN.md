# Legal Skills 专家套件设计思路

本文档用于说明 Legal Skills 如何从单个 Skill 与松散 pack，升级为面向真实法律工作场景的专家套件。

参考对象包括 LobsterAI 的 Kit / 专家套件实现及其 Legal Kit 中的 Skill 写法。结论是：Legal Skills 可以借鉴 LobsterAI 的 YAML 元数据、套件选择、Skill 触发描述和输出模板写法，但不应把套件仅理解为一个文件夹或一个可安装包。Legal Skills 的核心价值应放在场景流程、上下游交接、质量门槛和人工复核边界上。

## 1. 核心判断

### 1.1 Kit 与 Expert Suite 不是同一层

LobsterAI 的 Kit 更接近分发和选择层：

- Kit 记录名称、描述、图标、版本、示例问题。
- Kit 引用若干 Skills、MCP Servers、Connectors。
- 用户选择 Kit 后，系统把 Kit 展开成一组 Skill，并把所选 Kit / Skill 写入上下文。
- Kit 本身不提供独立 Agent 身份，也不直接主导 Skill 之间的工作流。

因此，LobsterAI 的 Kit 可以解决“如何安装、展示、选择一组 Skill”，但不能单独解决“这些 Skill 如何协作完成一个法律任务”。

Legal Skills 更适合采用以下分层：

| 层级 | 作用 | 是否主导流程 |
| :--- | :--- | :--- |
| Skill | 一个可复用能力单元 | 否，只负责自己边界内的任务 |
| Pack | 松散归类，用于浏览、分发和理解 | 否 |
| Expert Suite | 面向场景的流程组织、阶段、交接、质量门槛 | 是 |
| Kit | 面向平台的安装 / 导出包 | 否，是分发形态 |
| Agent | 运行时角色、上下文和执行策略 | 是，但属于更重的运行层 |

建议对外中文仍使用“专家套件”，对内结构使用 `expert-suite`。未来如果需要兼容某个平台的分发机制，再把 Expert Suite 导出为 Kit。

### 1.2 不要把专家套件做成“文件夹命名”

如果只是把几个 Skill 放进一个目录，然后称为“诉讼套件”或“合同套件”，问题仍然存在：

- Skill 之间不知道谁在前、谁在后。
- 上游输出没有稳定格式，下游只能重新理解。
- 缺少阶段目标，用户不知道当前处于哪一步。
- 缺少升级条件，AI 容易在应当人工复核的地方继续生成。
- 难以评估一个套件到底是否完成了法律工作。

专家套件应至少回答五个问题：

1. 这个套件解决什么场景。
2. 这个场景分为哪些阶段。
3. 每个阶段由哪些 Skill 负责。
4. Skill 之间交接什么输入和输出。
5. 哪些节点必须提示人工复核或升级处理。

## 2. 从 LobsterAI Legal Kit 学到什么

LobsterAI Legal Kit 包含 `brief`、`compliance-check`、`legal-response`、`legal-risk-assessment`、`meeting-briefing`、`review-contract`、`signature-request`、`triage-nda`、`vendor-check` 等 Skill。

这些 Skill 对 Legal Skills 最有启发的不是美国法务内容本身，而是它们的写法。

### 2.1 强触发描述

LobsterAI 的 `description` 通常不是一句功能描述，而是包含：

- 这个 Skill 做什么。
- 用户在什么场景下需要它。
- 典型任务是什么。
- 触发边界在哪里。

例如 `triage-nda` 会直接说明用于 NDA 初筛、GREEN / YELLOW / RED 分类、发现竞业限制或缺少 carveout 时触发。

Legal Skills 可借鉴这种写法。每个法律专业 Skill 的 `description` 不应只写“用于法律分析”，而应写清：

- 任务对象：判决书、起诉状、证据材料、法院短信、合同、专利交底书等。
- 使用场景：立案准备、证据整理、诉讼研判、客户沟通、检索支撑、交付成文等。
- 不适用场景：例如普通文本润色、非法律 OCR、无事实材料的泛泛咨询。

### 2.2 Skill 内部有可执行流程

LobsterAI 的法律 Skill 通常包含明确步骤：

- 接收材料。
- 补充上下文。
- 加载 playbook 或模板。
- 逐项检查。
- 分类 / 路由。
- 输出结构化结果。

这比“请分析合同风险”稳定得多。Legal Skills 也应要求专业 Skill 至少包含：

```markdown
## 工作流程

### Step 1: 接收材料
说明接受哪些输入、缺少输入时如何追问。

### Step 2: 识别任务类型
说明如何判断当前属于哪类法律任务。

### Step 3: 执行分析或处理
说明分析维度、检查清单或脚本调用方式。

### Step 4: 生成输出
给出固定输出格式。

### Step 5: 交接或升级
说明下游 Skill、handoff package 或人工复核条件。
```

### 2.3 Playbook 优先，默认规则兜底

`triage-nda`、`review-contract` 等 Skill 会先尝试加载组织自己的 playbook；如果没有，再使用市场通用默认规则，并明确提示当前是默认规则。

这对 Legal Skills 很重要。法律工作不能长期只靠 Skill 内置经验，应支持：

- 用户自己的办案模板。
- 律师团队的审查清单。
- 特定法院 / 地区 / 案由的经验规则。
- 客户偏好的文风和交付格式。

建议写法：

```markdown
## Playbook

优先读取用户提供的 playbook、模板、既有案例或项目规则。
如果没有可用 playbook，可以使用本 Skill 的默认规则，但必须在输出中标注“使用默认规则，未读取团队 playbook”。
```

### 2.4 风险分级与路由

LobsterAI Legal Kit 很常用 GREEN / YELLOW / RED 或 severity x likelihood 这类分类方法。它的价值不是颜色本身，而是把下一步动作绑定到风险等级：

- GREEN：可按标准流程继续。
- YELLOW：需要律师复核或补充材料。
- RED：停止自动处理，进入完整法律审查或人工决策。

Legal Skills 可以按中国律师工作语境调整为：

| 等级 | 含义 | 推荐动作 |
| :--- | :--- | :--- |
| 可继续 | 信息充分、风险较低、适合自动进入下游 | 生成 handoff package 或进入交付 Skill |
| 需补充 | 事实、证据、主体、期限或依据不足 | 先列补充清单，不直接下结论 |
| 需复核 | 涉及重大法律判断、诉讼策略、客户承诺、期限风险 | 提醒律师复核后再输出 |
| 停止自动化 | 可能误导客户、涉及保全 / 上诉 / 再审期限、重大合规或伦理风险 | 不继续生成实质建议 |

### 2.5 输出模板很稳定

LobsterAI 的 Skill 往往直接给出 Markdown 输出结构，包括表格、风险列表、下一步行动。这一点值得强借鉴。

法律专业 Skill 的输出不宜每次漂移。建议每个核心 Skill 至少固定：

- 摘要。
- 材料依据。
- 分析过程。
- 风险或问题清单。
- 建议动作。
- 缺失信息。
- 下游交接。

### 2.6 明确升级条件

`legal-response` 这类 Skill 会先检查是否存在不得使用模板回复的情形，例如监管机关、潜在诉讼、重大承诺、多法域冲突等。

Legal Skills 也需要类似机制，尤其是在：

- 客户可直接依赖的法律结论。
- 诉讼期限、上诉期限、再审期限。
- 证据保全、财产保全、行为保全。
- 可能构成虚假陈述或误导客户的表达。
- 未脱敏材料、敏感个人信息、商业秘密。
- AI 无法核验的事实来源。

## 3. 不宜直接照搬的部分

### 3.1 不把长篇实体法知识全部塞进 SKILL.md

LobsterAI 的某些 Skill 把大量美国法务清单直接写在 `SKILL.md` 中。它适合演示，也能开箱即用，但会带来两个问题：

- `SKILL.md` 过长，影响渐进式加载。
- 法域、团队、客户差异很大，内置知识容易变成过期规则。

Legal Skills 应遵守本仓库的 Progressive Disclosure 原则：

- `SKILL.md` 放任务流程、触发条件、输出格式、关键判断框架。
- `references/` 放详细 playbook、法律规则、示例和检查清单。
- `scripts/` 放可执行处理逻辑。
- `assets/` 放模板、示例配置和输出资源。

### 3.2 不把企业法务连接器假设当成默认前提

LobsterAI Legal Kit 经常假设 CLM、CRM、Email、Calendar、Cloud Storage、E-signature 等连接器。

Legal Skills 当前更贴近律师个人与律所工作流，应优先支持：

- 本地案件目录。
- 扫描件、PDF、图片、音视频、Word。
- 法律检索平台。
- Obsidian / Markdown 知识库。
- 客户沟通材料和法院短信。

连接器可以作为增强能力，不应成为套件成立的前提。

### 3.3 不把 Kit 当 Agent

Kit 不等于 Agent。Kit 只是能力包；Expert Suite 是场景组织；Agent 才是运行时角色。

Legal Skills 早期不必急着做 Suite Agent。先把 suite.yaml、README、handoff 和 Skill 写法稳定下来，就足以解决“不是一堆 Skill 放文件夹”的问题。

## 4. 推荐目录结构

现有 `pack-skills/` 可以继续作为松散归类目录。新增专家套件时，建议使用独立目录：

```text
expert-suites/
├── litigation-assessment/
│   ├── README.md
│   ├── suite.yaml
│   └── references/
│       └── playbook.md
├── material-digitization/
│   ├── README.md
│   └── suite.yaml
└── document-delivery/
    ├── README.md
    └── suite.yaml
```

关系建议：

- `skills/` 是 Skill 源码的唯一真实位置。
- `pack-skills/` 用于展示和松散归类。
- `expert-suites/` 用于场景编排和专家套件。
- `expert-suites/*/suite.yaml` 只引用 Skill，不复制 Skill。
- 若未来需要平台分发，再从 `expert-suites/*/suite.yaml` 导出 Kit 元数据。

## 5. suite.yaml 设计

### 5.1 最小可用结构

```yaml
id: litigation-assessment
type: expert-suite
name: 诉讼研判套件
version: 0.1.0
status: draft
summary: 从案件材料进入、事实证据整理、法律检索、诉讼研判到客户交付的场景套件。

domain:
  primary: litigation
  jurisdiction: CN
  language: zh-CN

audience:
  - litigation-lawyer
  - legal-assistant

skills:
  - id: legal-ocr
    role: material_ingestion
    required: true
  - id: pdf-organizer
    role: material_organization
    required: false
  - id: legal-case-analysis
    role: general_legal_analysis
    required: true
  - id: yuandian-law-search
    role: legal_research
    required: false
  - id: litigation-analysis
    role: litigation_strategy
    required: true
  - id: legal-proposal-generator
    role: client_delivery
    required: false
  - id: md2word
    role: document_export
    required: false

stages:
  - id: intake
    name: 材料进入
    objective: 将扫描件、PDF、图片、音视频或法院短信转为可分析材料。
    skills:
      - legal-ocr
      - funasr-transcribe
      - court-sms
    outputs:
      - markdown_materials
      - source_file_index
    exit_criteria:
      - 主要材料已转为 Markdown 或可引用文本。
      - 原始文件路径可追溯。

  - id: facts
    name: 事实与证据整理
    objective: 形成案件事实、时间线、证据目录和证明目的。
    skills:
      - legal-case-analysis
    outputs:
      - fact_summary
      - evidence_catalog
      - missing_evidence
    exit_criteria:
      - 关键事实、证据缺口和争议点已列明。

  - id: research
    name: 法律检索与依据补强
    objective: 检索法条、案例和裁判观点，为诉讼研判提供依据。
    skills:
      - yuandian-law-search
      - zhihe-legal-research
    outputs:
      - law_and_case_research_notes
    exit_criteria:
      - 关键法律依据有来源说明。

  - id: analysis
    name: 诉讼研判
    objective: 形成胜败风险、诉讼路径、举证策略和沟通建议。
    skills:
      - litigation-analysis
    outputs:
      - litigation_assessment
      - strategy_options
      - review_flags
    exit_criteria:
      - 明确哪些结论可交付，哪些需要律师复核。

  - id: delivery
    name: 客户交付
    objective: 将研判结果转化为客户可读的方案、备忘录或 Word 文档。
    skills:
      - legal-proposal-generator
      - de-ai-polish
      - md2word
    outputs:
      - client_memo
      - word_document
    exit_criteria:
      - 输出结构完整，风险提示和依据保留。

handoff:
  - from: intake
    to: facts
    package_type: material_package
    required_fields:
      - source_file_index
      - markdown_materials
      - missing_or_unreadable_files

  - from: facts
    to: analysis
    package_type: case_brief
    required_fields:
      - fact_summary
      - evidence_catalog
      - disputed_issues
      - missing_evidence

  - from: analysis
    to: delivery
    package_type: client_delivery_brief
    required_fields:
      - litigation_assessment
      - strategy_options
      - review_flags
      - client_communication_points

quality_gates:
  - id: source_traceability
    name: 来源可追溯
    rule: 关键事实和引用材料必须能回到原始文件或检索来源。
  - id: missing_information
    name: 缺失信息显式列明
    rule: 缺材料、缺事实、缺检索依据时，不得假装完整。
  - id: lawyer_review
    name: 律师复核
    rule: 涉及诉讼策略、期限、重大风险和客户承诺时，必须标注需律师复核。

routing:
  default_entry_stage: intake
  allow_skip_stages:
    - research
    - delivery
  escalation:
    - condition: 涉及上诉、再审、保全、时效或重大期限。
      action: stop_and_request_lawyer_review
    - condition: 关键材料不可读或来源不可追溯。
      action: request_missing_materials

distribution:
  exportable_as_kit: true
  kit_id: litigation-assessment
  display_category: 诉讼案件
```

### 5.2 字段说明

| 字段 | 作用 |
| :--- | :--- |
| `id` | 套件稳定标识，建议英文短横线命名 |
| `type` | 固定为 `expert-suite`，避免和普通 pack 混淆 |
| `status` | `draft`、`usable`、`stable`、`deprecated` |
| `skills` | 套件引用的 Skill 清单，不复制 Skill 内容 |
| `stages` | 场景流程阶段，是 Expert Suite 区别于 Kit 的关键 |
| `handoff` | 阶段或 Skill 之间的交接契约 |
| `quality_gates` | 套件级质量门槛 |
| `routing` | 默认入口、可跳过阶段、升级条件 |
| `distribution` | 未来导出为 Kit 或市场包时使用 |

## 6. README.md 应该写什么

每个专家套件目录下的 `README.md` 应面向使用者，而不是面向系统。

建议结构：

```markdown
# 诉讼研判套件

## 适用场景

## 不适用场景

## 你需要准备什么材料

## 套件工作流

## 包含的 Skill

## 输出物

## 人工复核边界

## 常见用法
```

其中“人工复核边界”必须保留。法律套件不能给用户一种“自动法律意见已经完成”的错觉。

## 7. 单个 Skill 的改写建议

为了让 Expert Suite 真正可编排，核心 Skill 应增加以下章节。不是每个 Skill 都必须很长，但关键法律专业 Skill 应具备这些接口。

### 7.1 推荐章节

```markdown
## 在套件中的角色

说明本 Skill 在哪些 Expert Suite 中通常承担什么职责。

## 输入

列明可接受输入、必须输入、可选输入、缺失时如何追问。

## 输出

列明稳定输出结构，以及能交给哪些下游 Skill。

## 工作流程

按步骤说明如何处理任务。

## 质量门槛

列明不能省略的检查项。

## 与其他 Skill 配合

说明上游来源和下游去向。

## 升级 / 人工复核条件

说明哪些情形必须停止自动化或提示律师复核。
```

### 7.2 推荐 Frontmatter 写法

```yaml
---
name: litigation-analysis
description: |
  本技能应在用户需要对中国诉讼案件进行胜败风险、争议焦点、举证责任、诉讼路径和客户沟通策略分析时使用，适用于已有起诉状、判决书、证据材料、庭审笔录或案件事实摘要的场景。
  不要用于：无事实材料的泛泛法律咨询、单纯 OCR/格式转换、非诉合同审查、未经过律师复核即可直接发送客户的最终法律意见。
version: 1.x.x
license: CC-BY-NC
---
```

### 7.3 推荐输出结构

```markdown
## 诉讼研判结果

### 1. 材料基础
- 已读取材料：
- 未读取 / 不可读材料：
- 关键事实来源：

### 2. 案件摘要

### 3. 争议焦点

### 4. 证据与证明责任

### 5. 法律依据与案例参考

### 6. 风险分级

### 7. 策略选项

### 8. 需律师复核的问题

### 9. 下游交接
```

## 8. 首批专家套件建议

### 8.1 文档入库与材料数字化套件

目的：把 PDF、扫描件、图片、音视频、法院短信等材料转成可分析的 Markdown / Word / 案件目录。

候选 Skill：

- `legal-ocr`
- `pdf-organizer`
- `funasr-transcribe`
- `tingwu-asr`
- `court-sms`
- `md2word`

### 8.2 诉讼案件研判套件

目的：从案件材料进入，到事实证据整理、法律检索、诉讼策略和客户交付。

候选 Skill：

- `legal-case-analysis`
- `litigation-analysis`
- `yuandian-law-search`
- `zhihe-legal-research`
- `legal-proposal-generator`
- `de-ai-polish`
- `md2word`

### 8.3 法律研究与知识库套件

目的：围绕法律问题做检索、归纳、知识库沉淀和后续复用。

候选 Skill：

- `multi-search`
- `yuandian-law-search`
- `zhihe-legal-research`
- `wechat-article-fetch`
- `legal-qa-extractor`
- `article2book`

### 8.4 知识产权专利商标套件

目的：支持专利交底、专利分析、商标申请 / 异议 / 无效等 IP 工作。

候选 Skill：

- `code2patent`
- `patent-analysis`
- `trademark-assistant`
- `legal-case-analysis`
- `legal-proposal-generator`

### 8.5 交付成文套件

目的：把分析结果转成客户可读、可交付、可归档的正式文档。

候选 Skill：

- `legal-proposal-generator`
- `legal-text-format`
- `de-ai-polish`
- `md2word`
- `legal-qa-extractor`

## 9. 轻量落地路线

### v0：命名与说明

- 保留 `pack-skills/` 作为松散归类。
- 新增 `expert-suites/` 作为场景套件目录。
- 每个套件先写 `README.md` 和 `suite.yaml`。

### v1：阶段与交接

- 为 3 个核心套件补齐 `stages` 和 `handoff`。
- 给相关核心 Skill 增加“输入 / 输出 / 下游 / 复核条件”章节。
- 与 `SKILL-HANDOFF-GUIDE.md` 的 Markdown Package 结构保持一致。

### v2：质量门槛

- 增加套件级 `quality_gates`。
- 为诉讼、知识产权、交付成文等套件定义人工复核边界。
- 增加简单校验脚本：检查 `suite.yaml` 引用的 Skill 是否存在。

### v3：导出为 Kit

- 在 `distribution` 字段中增加平台导出信息。
- 根据目标平台生成 Kit 元数据。
- Kit 仍然是分发产物，不反过来定义 Expert Suite。

### v4：Suite Agent

- 当套件流程稳定后，再考虑为特定套件配置 Agent 上下文。
- Suite Agent 可以读取 `suite.yaml`，负责阶段推进、Skill 选择和复核提醒。
- 不建议在 v0 就引入 Agent，否则会把结构问题隐藏到提示词里。

## 10. 设计原则

1. Expert Suite 是流程，不是文件夹。
2. Skill 是能力单元，不直接依赖其他 Skill 的内部实现。
3. Handoff 是接口，不能只靠自然语言含糊接力。
4. Playbook 优先于通用经验。
5. 法律判断必须保留人工复核边界。
6. 先轻量可用，再考虑自动化导出和 Suite Agent。
7. Kit 是分发形态，不是 Legal Skills 的核心抽象。

## 11. 与现有文档的关系

- `SKILL-DEV-GUIDE.md`：约束单个 Skill 如何写。
- `SKILL-ORCHESTRATION-GUIDE.md`：说明多个 Skill 为什么需要编排。
- `SKILL-HANDOFF-GUIDE.md`：定义 Skill 之间如何交接。
- 本文档：定义 Expert Suite 如何组织场景、阶段、Skill 引用和质量门槛。

