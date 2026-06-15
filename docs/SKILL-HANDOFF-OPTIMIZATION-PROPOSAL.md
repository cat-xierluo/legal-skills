# Skill Handoff 优化设计稿 (Optimization Proposal)

> 本文档是 [SKILL-HANDOFF-GUIDE.md](SKILL-HANDOFF-GUIDE.md) v1.0.0 的**优化设计稿**,不是正式指南。
> 设计依据:MyAgents 任务中心(MyAgents,hAcKlyc)跑通的契约实践,对照本项目现状,补齐缺失的三块。
> **本稿不替换原指南,由维护者评审后自行决定是否合并进 v1.1。**

---

## 0. 这份稿子解决什么

读完原指南(v1.0.0)和项目实际在用的 handoff 产出(`pdf-organizer/handoff.json`),有两个发现:

**发现一:原指南已经覆盖了契约思想的大部分地基。**
- Markdown 外壳 + YAML 头 ✅
- 强/弱交接分级 ✅
- 原始材料随包走 ✅
- 版本化 ✅
- 上下游职责分工 ✅

**发现二:实操中已经偏离了指南推荐的形态。**
`pdf-organizer/handoff.json` 是**纯 JSON**,不是指南推荐的「Markdown 外壳 + YAML 头」。这透露一个信号:**实操中机器友好性正在压倒人类可读性**。这是合理的偏移——MyAgents 的实践也印证了这一点(它的 task.md / verify.md 是给人/Agent 读的 markdown,但任务状态、trace 是结构化的 JSON/jsonl)。

**发现三:原指南缺 MyAgents 跑通后才沉淀出来的三块关键能力。**

| 缺失 | MyAgents 对应 | 原指南里的状态 |
|------|--------------|---------------|
| **执行回执 / 状态闭环** | task 有 status(进行中/完成/失败),任务面板可视 | 第 9.2 节标注为「后续建议」,未落地 |
| **验收契约(verify 思想)** | verify.md:自动化检查 + Agent 自检 + 端到端场景 | 只有「强交接判定标准」,没有「下游怎么算成功」 |
| **任务级 trace(全局可追溯)** | 任务实体有 id / 状态 / 历史 | 第 8.2 节写「后续考虑加 trace 字段」——没内置 |

**结论:优化方向不是重写,是补这三块,把 v1.0 升到 v1.1。** 同时把指南推荐形态和实操形态的分歧显式处理掉。

---

## 1. 设计原则(三要三不要)

这三条原则贯穿全文,任何字段设计都必须服从:

### 要:服从「AI 是编排引擎」

本项目的编排理念是「AI 自主理解决策」,不是预定义节点连接(见 [SKILL-ORCHESTRATION-GUIDE.md](SKILL-ORCHESTRATION-GUIDE.md) §1.2)。因此 handoff 契约:

- **是 AI 可读的契约,不是僵化的 RPC schema**。字段是给 AI 的判断依据,不是给代码做硬解析的协议。
- **允许 AI 按需降级/补全**。弱交接可以执行,但要显式标记。
- **不追求字段穷举**。先把高频字段稳定下来,边界场景用自由文本兜底。

### 要:闭环优先于单向传递

v1.0 的 handoff 是**单向**的:上游 → 下游,推完就结束。MyAgents 证明 handoff 必须是**闭环**:下游执行完要有**回执**回流到上游(或 trace 层),否则无法追溯、无法做面板、无法判断链路在哪一环出了问题。

> 经验法则:**一个 handoff 没有回执,等于这个交接没发生过**(对系统而言)。

### 要:trace 从第一个 handoff 就内置

不要把 trace 当「后续扩展」。每个 handoff package 从诞生起就带 `task_id` 和 `trace_id`,这样:
- 全局任务流天然可聚合(未来做面板时数据是现成的)
- 跨 skill 的链路可追溯(哪个匹配触发了哪个执行)
- 不用回头改 70+ skill 去补字段

### 不要:强行统一所有 skill 的 package_type

不同 skill 的 handoff 语义天然不同(writer_brief / doc_split / stt_result / ... )。统一的是**外壳字段和回执/验收结构**,不是业务 payload。

### 不要:为了「规范」牺牲 AI 的自主判断空间

字段是约束,不是枷锁。强交接要求字段齐全;但 AI 在缺字段时有权自主决定是否降级执行——只要它**显式声明**这是弱交接。

### 不要:一次性把所有字段铺满

先稳定核心字段(本稿 §3),扩展字段(评分、优先级、回执详情)分批落。指南第 8.2 节「先稳定再扩展」原则不变。

---

## 2. 三块新增设计总览

```
                       v1.0 已有                  v1.1 新增
                  ┌─────────────────┐      ┌──────────────────────┐
  上游 Skill ───► │  Handoff Package │ ───► │  下游 Skill           │
                  │  (单向, v1.0)    │      │                      │
                  └─────────────────┘      └──────────┬───────────┘
                       │                               │
                       │                          【新增①回执】
                       │                          Execution Receipt
                       │                          (下游→上游/trace)
                       │                               │
                       │                          【新增②验收】
                       │                          Acceptance Contract
                       │                          (handoff 内置 verify)
                       │
                  【新增③trace】
                  task_id + trace_id
                  贯穿全链路
```

---

## 3. v1.1 Handoff Package 标准结构

### 3.1 推荐形态的修订(v1.0 → v1.1)

v1.0 推荐「Markdown 外壳 + YAML 头 + 分层正文」。v1.1 修订为**双轨制**,显式承认实操中的两种合法形态:

| 形态 | 适用场景 | 示例 |
|------|---------|------|
| **A. Markdown Package**(v1.0 推荐,保留) | 内容生成类 handoff,正文承载长文章/热点原文/聊天记录 | `lawyer-ip-os → legal-video-creator` |
| **B. JSON Package**(实操中已广泛使用,显式合法化) | 数据处理类 handoff,payload 是结构化文档清单/STT 结果/检索结果 | `pdf-organizer/handoff.json` |

**判定规则**:
- payload 主体是**长文本** → 用 A(Markdown)
- payload 主体是**结构化条目列表** → 用 B(JSON)
- 混合时,A 优先,B 的结构化数据塞进 A 的 YAML 块

两种形态**共用同一套外壳字段**(§3.2),只是 payload 编码方式不同。这统一了字段语义,又尊重了实操。

### 3.2 外壳字段(v1.0 基础 + v1.1 新增)

**v1.0 基础字段(保留,语义不变)**:

| 字段 | 必填 | 说明 |
|------|------|------|
| `handoff_version` | 是 | 交接协议版本号,本稿定 v1.1 |
| `source_skill` | 是 | 上游 Skill 名称 |
| `target_skill` | 是 | 下游 Skill 名称 |
| `package_type` | 是 | 包类型(writer_brief / doc_split / stt_result / ...) |
| `content_format` | 是 | markdown / json |
| `contains_original_materials` | 是 | 是否包含原始输入材料 |
| `material_count` | 是 | 原始材料数量 |

**v1.1 新增字段**:

| 字段 | 必填 | 说明 | 新增理由 |
|------|------|------|---------|
| `task_id` | 是 | 本次任务的稳定唯一 ID(如 `pdf-organizer-20260601-123007`) | 【新增③trace】全局追溯的锚点 |
| `trace_id` | 否 | 跨 skill 链路的贯穿 ID(同一条信息从 RSS→router→writer 共用一个 trace_id) | 【新增③trace】链路追溯 |
| `created_at` | 是 | ISO8601 时间戳 | 排序、超时判断、面板展示 |
| `acceptance` | 是 | 验收契约对象(见 §4) | 【新增②验收】下游怎么算成功 |
| `handoff_strength` | 是 | `strong` / `weak`,显式标记(替代 v1.0 隐式判定) | 让 AI 主动声明,而非靠下游推断 |
| `expires_at` | 否 | 失效时间(热点类 handoff 有时效) | 老的 handoff 不应被无限期消费 |

### 3.3 Markdown Package 模板(v1.1)

````markdown
## Handoff Package

```yaml
# v1.0 基础字段
handoff_version: "1.1"
source_skill: lawyer-ip-os
target_skill: legal-video-creator
package_type: writer_brief
content_format: markdown
contains_original_materials: true
material_count: 1

# v1.1 新增字段
task_id: lawyer-ip-os-20260614-ip-shortvideo-001
trace_id: rss-hot-20260614-ip-infringement
created_at: 2026-06-14T15:30:00+08:00
handoff_strength: strong
expires_at: 2026-06-21T00:00:00+08:00   # 热点类,7 天后失效

# v1.1 验收契约(详见 §4)
acceptance:
  automated_checks: []
  agent_self_review:
    - 脚本覆盖 brief 中所有必须强调的点
    - 未触碰任何「必须避免」边界
    - CTA 轻重与 brief 一致
  integration_scenario: 产出的短视频脚本能被 video-creator 直接消费,无需二次确认 brief
```

### 1. 上游判断摘要
(同 v1.0)

### 2. 原始输入材料
(同 v1.0)

### 3. 交接备注
(同 v1.0)
````

### 3.4 JSON Package 模板(v1.1,以 pdf-organizer 为例)

这是把你现有 `pdf-organizer/handoff.json` 升级到 v1.1 的样子(只展示外壳变化,documents 数组语义不变):

```json
{
  "handoff_version": "1.1",
  "source_skill": "pdf-organizer",
  "target_skill": "contract-review | litigation-analysis",
  "package_type": "doc_split",
  "content_format": "json",

  "task_id": "pdf-organizer-20260601-123007",
  "trace_id": "desktop-inbox-20260601-batch01",
  "created_at": "2026-06-01T12:30:08+08:00",
  "handoff_strength": "strong",
  "expires_at": null,

  "contains_original_materials": true,
  "material_count": 6,

  "acceptance": {
    "automated_checks": [
      "document_count 与 documents 数组长度一致",
      "每个 document 有非空 file_path 且文件存在"
    ],
    "agent_self_review": [
      "每份文档的 suggested_downstream 合理(合同→合同审查,诉状→诉讼分析)",
      "needs_review=true 的文档已标注原因(见 evidence)"
    ],
    "integration_scenario": "下游合同审查 skill 能直接读取 documents 中 document_type=合同 的条目,无需重新 OCR"
  },

  "documents": [ /* ...你现有的 D001~D006 结构不变... */ ],
  "recommended_next_steps": [ /* ...同现有... */ ]
}
```

> 注意:你现有的 `schema: "pdf-organizer-handoff/v1"` 字段,在 v1.1 下被 `handoff_version` + `package_type` 取代——统一协议版本,不再每个 skill 自定义 schema 名。

---

## 4. 【新增②】验收契约 (Acceptance Contract)

这是 v1.1 最重要的新增,直接借鉴 MyAgents 的 verify.md。

### 4.1 为什么要有验收契约

v1.0 只有「强交接判定标准」(回答:这个 handoff 合不合格)。但它不回答**下游执行完,怎么算成功**。没有验收契约:

- 下游执行完,没有客观标准判断合格与否
- 同一个 handoff 给不同下游,验收口径不一致
- 无法自动化判断「这条链路是不是真的跑通了」

MyAgents 的解法是 verify.md 三层结构,迁移到 handoff 里就是 `acceptance` 对象的三个字段。

### 4.2 acceptance 三层结构

| 层 | 字段 | 是什么 | 例子 |
|----|------|--------|------|
| **自动化检查** | `automated_checks` | 返回 pass/fail 的命令或断言,不需要判断 | `"document_count 与数组长度一致"`、`"npm run typecheck"` |
| **Agent 自检** | `agent_self_review` | 需要判断力的检查项,描述 + 通过标准 | `"脚本覆盖 brief 所有必须强调的点"` |
| **端到端场景** | `integration_scenario` | 整条链路的验收场景 | `"产出的脚本能被 video-creator 直接消费"` |

### 4.3 谁来写 acceptance

**上游写,不是下游写。** 理由:上游知道自己交付了什么、期望下游产出什么。下游只是验收方,不是出题方。

这跟 MyAgents 一致:对齐阶段(上游,人+AI)产出 verify.md,执行阶段(下游,AI)照着验。

### 4.4 验收契约的可复用性

借鉴 MyAgents 的设计——同一类 package_type 的验收契约应当**可复用**。

建议在项目里维护一份 `references/acceptance-templates/<package_type>.yaml`,handoff 里只引用模板名 + 本次特化项:

```yaml
acceptance:
  template: writer_brief        # 引用通用模板
  overrides:                    # 本次特化
    integration_scenario: 本条须特别强调「合理使用」抗辩边界
```

用得越多,验收越快——这是个会自我加速的设计。

---

## 5. 【新增①】执行回执 (Execution Receipt)

### 5.1 为什么需要回执

v1.0 的 handoff 推完就结束,下游执行成功/失败/进行中,上游和全局都不知道。这是「状态散在几十个 JSON 里、看不见全局」的根本原因之一。

MyAgents 证明:**handoff 必须有回声**。下游执行完(或失败、或需返修),要回传一份**回执**。

### 5.2 回执结构

回执是**独立的 package**,方向相反(下游 → 上游或 trace 层):

```json
{
  "handoff_version": "1.1",
  "package_type": "execution_receipt",
  "content_format": "json",

  "task_id": "pdf-organizer-20260601-123007",     // 与原 handoff 的 task_id 对应
  "trace_id": "desktop-inbox-20260601-batch01",   // 贯穿
  "source_skill": "contract-review",              // 下游(回执的发出方)
  "target_skill": "pdf-organizer",                // 上游(回执的接收方)
  "created_at": "2026-06-01T13:15:00+08:00",

  "status": "completed",                          // completed | failed | needs_rework | skipped
  "accepted": true,                               // 是否通过验收契约

  "verification_result": {
    "automated_checks": { "passed": 2, "failed": 0 },
    "agent_self_review_passed": true,
    "integration_scenario_met": true
  },

  "outputs": [                                    // 产出物定位
    { "type": "file", "path": "/path/to/review-report.md" }
  ],
  "errors": [],                                   // 失败时填
  "rework_hints": []                              // needs_rework 时填,告诉上游缺什么
}
```

### 5.3 四种 status 的语义

| status | 含义 | 上游/编排层该怎么处理 |
|--------|------|---------------------|
| `completed` | 下游正常完成且通过验收 | 链路闭合,可标记任务完成 |
| `failed` | 下游执行出错(异常,非质量问题) | 记录,决定重试或上报 |
| `needs_rework` | 执行了但验收没过(质量不达标) | 读 `rework_hints`,补全后重新 handoff |
| `skipped` | 下游判断不该执行(如时效已过、重复) | 正常,非错误 |

### 5.4 回执往哪写

短期(不做面板时):回执写到**与原 handoff 同目录**,文件名 `{task_id}.receipt.json`。这样原 handoff 和它的回执天然配对,排查时一目了然。

中期(做状态层时):所有回执追加到一个全局 `task-events.jsonl`,一行一条。这就是未来面板的数据源。

> 关键:**回执格式现在就定下来,哪怕短期只写本地文件**。等做面板时数据是现成的,不用回头补。这就是 §1 「trace 从第一个 handoff 就内置」的具体落地。

---

## 6. 【新增③】任务级 Trace

### 6.1 task_id vs trace_id 的区别

这两个容易混,必须讲清:

| ID | 粒度 | 生命周期 | 例子 |
|----|------|---------|------|
| `task_id` | 单次 handoff 任务 | 一次交接 | `pdf-organizer-20260601-123007`(一次 PDF 拆分) |
| `trace_id` | 跨 skill 的整条链路 | 从信息进入到最终产出 | `rss-hot-20260614-ip-infringement`(一条 IP 热点从 RSS 到视频的全流程) |

一条 trace 包含多个 task。例:`RSS 命中 → router handoff(task_id=A)→ writer 产出(task_id=B)→ video 生成(task_id=C)`,三者共用一个 `trace_id`,各有自己的 `task_id`。

### 6.2 命名规范建议

- `task_id`: `{skill}-{date}-{HHMMSS}-{short-slug}`,保证全局唯一且可读
- `trace_id`: `{source}-{date}-{topic-slug}`,topic 维度聚合

不强制,但统一命名能让 grep 和面板排序都更顺。

### 6.3 trace 现在怎么用(不做面板时)

短期价值:**排查**。当一条链路结果有问题,用 `trace_id` 一 grep,全链路的 handoff 和回执都出来,能定位是哪一环出的:

```bash
grep -r "trace_id: rss-hot-20260614-ip-infringement" ./private-skills/
```

这就比现在「翻遍几十个 JSON 找问题出在哪」强一个量级。面板是锦上添花,trace 本身现在就有独立价值。

---

## 7. 强弱交接标准的升级(v1.0 → v1.1)

v1.0 的强/弱交接是**隐式判定**(靠下游根据字段齐全度推断)。v1.1 改为**上游显式声明** + **客观标准**。

### 7.1 v1.1 强交接判定(全部满足)

- [ ] v1.0 的四项(完整头信息 / 上游判断摘要 / ≥1 份原始材料 / 下游能直接执行)
- [ ] **新增**:`task_id` + `created_at` 存在
- [ ] **新增**:`acceptance` 对象三层齐全(至少 automated_checks 或 agent_self_review 非空)
- [ ] **新增**:`handoff_strength: strong` 由上游显式声明

### 7.2 v1.1 弱交接的处理

弱交接不再只是「精度受影响」的提示,而是**触发回执的 `needs_rework` 机制**:

- 上游声明 `handoff_strength: weak`,在交接备注写明缺什么
- 下游可选择降级执行,但回执里 `status` 应为 `needs_rework` 而非 `completed`
- 上游收到 `needs_rework` 回执,读 `rework_hints` 补全,重新 handoff(共用同一 `trace_id`,新 `task_id`)

这让弱交接**可恢复**,而不是一锤子买卖。

---

## 8. 端到端示例:pdf-organizer → 合同审查(完整闭环)

用你真实在用的场景,演示 v1.1 一个完整闭环长什么样样。

### 8.1 上游 handoff(pdf-organizer 发出,JSON 形态)

外壳见 §3.4,documents 数组沿用你现有结构。关键:它带了 `task_id`、`trace_id`、`acceptance`,且显式声明 `handoff_strength: strong`。

### 8.2 下游执行 + 回执(contract-review 发出)

```json
{
  "handoff_version": "1.1",
  "package_type": "execution_receipt",
  "content_format": "json",
  "task_id": "pdf-organizer-20260601-123007",
  "trace_id": "desktop-inbox-20260601-batch01",
  "source_skill": "contract-review",
  "target_skill": "pdf-organizer",
  "created_at": "2026-06-01T13:15:00+08:00",
  "status": "completed",
  "accepted": true,
  "verification_result": {
    "automated_checks": { "passed": 2, "failed": 0 },
    "agent_self_review_passed": true,
    "integration_scenario_met": true
  },
  "outputs": [
    { "type": "file", "path": ".../review-D001-青柏教育.md" },
    { "type": "file", "path": ".../review-D002-张家宁叠影.md" }
  ],
  "errors": [],
  "rework_hints": []
}
```

### 8.3 这个闭环相比现状多了什么

| | v1.0 现状 | v1.1 闭环 |
|---|---|---|
| handoff 方向 | 单向 | 双向(含回执) |
| 状态可见性 | 只有 `status: ok`(在 handoff 自身) | 有独立的回执 status + accepted |
| 验收 | 无客观标准 | acceptance 三层 + verification_result |
| 追溯 | 靠文件路径推断 | task_id / trace_id 显式 |
| 失败恢复 | 无 | needs_rework + rework_hints |

---

## 9. 落地路线(给维护者的建议)

不要一次改 70+ skill。分三批,每批独立可验证:

### 批次 1(最小可用,1-2 个 skill)
- 选 1 条已跑通的链路(建议 `pdf-organizer → 合同审查/诉讼分析`)
- 给上游 handoff 补 v1.1 外壳字段(task_id / created_at / acceptance / handoff_strength)
- 给下游加回执产出(同目录写 `{task_id}.receipt.json`)
- **验证**:跑一次,确认回执能生成、trace_id 能 grep 到全链路

### 批次 2(模板化,2-3 条链路)
- 把 acceptance 抽成 `references/acceptance-templates/<package_type>.yaml`
- 接入第 2、3 条链路,复用模板
- **验证**:不同链路复用同一验收模板,特化项只在 overrides

### 批次 3(全局状态层,为面板铺路)
- 所有 skill 的回执追加到全局 `task-events.jsonl`
- 写一个最小的只读脚本,按 trace_id 聚合展示链路状态
- **验证**:`task-events.jsonl` 能回答「我所有 skill 今天跑了哪些任务、各自什么状态」

> 批次 3 完成时,「做前端 UI」就只是给这个 jsonl 套个皮——这正是你说的「等节点成熟了让 AI 直接根据现有 skill 做前端 UI」的成熟时机判断依据。

---

## 10. 与 v1.0 的兼容性

| 场景 | 处理 |
|------|------|
| 老 handoff(无 v1.1 新字段)被下游消费 | 下游视为弱交接,按 §7.2 处理(可执行,但回执标 needs_rework 提示补全) |
| `schema: "xxx/v1"` 这种 skill 自定义版本号 | 逐步迁移到统一的 `handoff_version` + `package_type`,过渡期两者并存 |
| 同时存在 Markdown Package 和 JSON Package | 合法,§3.1 双轨制已承认 |

v1.1 是**向后兼容的增量升级**,不是破坏性变更。

---

## 11. 字段速查表(v1.1 完整)

### Handoff Package 外壳

| 字段 | 必填 | 版本 | 说明 |
|------|------|------|------|
| `handoff_version` | 是 | v1.0 | "1.1" |
| `source_skill` | 是 | v1.0 | 上游 |
| `target_skill` | 是 | v1.0 | 下游 |
| `package_type` | 是 | v1.0 | 业务类型 |
| `content_format` | 是 | v1.0 | markdown / json |
| `contains_original_materials` | 是 | v1.0 | 是否含原始材料 |
| `material_count` | 是 | v1.0 | 材料数 |
| `task_id` | 是 | **v1.1** | 任务唯一 ID |
| `trace_id` | 否 | **v1.1** | 链路贯穿 ID |
| `created_at` | 是 | **v1.1** | ISO8601 时间 |
| `handoff_strength` | 是 | **v1.1** | strong / weak |
| `expires_at` | 否 | **v1.1** | 失效时间 |
| `acceptance` | 是 | **v1.1** | 验收契约对象 |

### Execution Receipt 外壳

| 字段 | 必填 | 说明 |
|------|------|------|
| `package_type` | 是 | 固定 `execution_receipt` |
| `task_id` | 是 | 对应原 handoff |
| `trace_id` | 否 | 贯穿 |
| `source_skill` | 是 | 回执发出方(原下游) |
| `target_skill` | 是 | 回执接收方(原上游) |
| `status` | 是 | completed / failed / needs_rework / skipped |
| `accepted` | 是 | 是否通过验收 |
| `verification_result` | 是 | 验收结果明细 |
| `outputs` | 否 | 产出物定位 |
| `errors` | 否 | 失败明细 |
| `rework_hints` | 否 | needs_rework 时的补全指引 |

---

## 变更历史

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| proposal-0.1 | 2026-06-14 | 初稿。基于 SKILL-HANDOFF-GUIDE.md v1.0.0 + MyAgents 任务中心实践,提出 v1.1 优化设计,新增验收契约 / 执行回执 / 任务级 trace 三块。待维护者评审。 |

---

> 本文档性质:**设计稿(Proposal)**,非正式指南。
> 维护者评审通过后,可将 §3-§7 合并进 SKILL-HANDOFF-GUIDE.md 升为 v1.1.0,本稿归档或删除。
