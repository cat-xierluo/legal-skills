# Legal Skills 项目总上下文与 Specs 升级建议

本文档记录 Legal Skills 后续升级 `AGENTS.md`、项目总上下文和 `specs/` 设计文档体系的建议。

背景判断：当前 `AGENTS.md` 更偏仓库协作规范，已经能约束 Skill 目录、许可证、依赖、发布和安全边界。但随着 Legal Skills 从单个 Skill 清单走向场景专家套件、Web Coding 工作流和跨 Skill 编排，仅靠仓库规则不足以让 Agent 快速理解项目愿景、核心抽象、当前版图和设计取舍。

建议方向不是推倒重写，而是把现有 `AGENTS.md` 升级成入口上下文，并把更长的背景材料拆到独立文档和 `specs/` 中。

## 1. 总体目标

升级后的项目文档体系应回答三类问题：

| 文档 | 主要问题 | 读者 |
| :--- | :--- | :--- |
| `AGENTS.md` | Agent 进入项目后应如何工作 | AI 代理、协作者 |
| `docs/PROJECT-CONTEXT.md` | Legal Skills 是什么，为什么这样组织 | AI 代理、维护者、深度协作者 |
| `specs/` | 某个跨模块功能、重构或修复为什么这样设计 | 维护者、未来接手者 |
| `docs/WEB-CODING-GUIDE.md` | Web Coding 任务如何设计、实现和验证 | 写网页、小工具、可视化页面的 Agent |

核心目标：

- 让 Agent 先理解项目定位，再执行具体文件修改。
- 让跨 Skill / 跨目录改造有设计记录，而不是只留下结果。
- 让 Web Coding 任务形成稳定闭环：需求、设计、实现、浏览器验证、截图证据。
- 保留当前 Skill 级文档规则，不引入不必要的重型流程。

## 2. AGENTS.md 升级建议

### 2.1 定位

`AGENTS.md` 应继续作为项目入口规则，但不宜承载所有背景材料。它应该变成“项目操作导航”：

- 告诉 Agent 项目是什么。
- 告诉 Agent 先读哪些文档。
- 告诉 Agent 哪些事情需要写 spec。
- 告诉 Agent 修改 Skill、Suite、README、Web 页面时分别遵循什么流程。

### 2.2 建议新增章节

可以在现有 `AGENTS.md` 的“核心原则”后，新增较短的“项目总上下文”章节：

```markdown
## 项目总上下文

Legal Skills 是面向中国律师和法律从业者的 AI Agent Skills 仓库。项目目标不是收集零散提示词，而是把法律工作中的材料处理、收案建档、法律检索、诉讼研判、文书交付、知识生产等场景沉淀为可复用、可编排、可分发的 Skill 能力系统。

涉及跨 Skill、专家套件、README 主叙事、仓库结构、Web Coding 工作流或发布机制时，先阅读：

- `docs/PROJECT-CONTEXT.md`
- `docs/EXPERT-SUITE-DESIGN.md`
- `docs/SKILL-ORCHESTRATION-GUIDE.md`
- `docs/SKILL-HANDOFF-GUIDE.md`
```

### 2.3 建议新增核心抽象

```markdown
## 核心抽象

- Skill：最小可复用能力单元，位于 `skills/`。
- Pack：松散归类，用于浏览和理解，位于 `pack-skills/`。
- Expert Suite：面向法律场景的流程编排，未来位于 `expert-suites/`。
- Kit：平台分发形态，不等同于 Expert Suite。
- Agent：运行时角色和方法论，不直接替代 Skill 或 Suite。
- Handoff：Skill 或 Suite 阶段之间的交接契约。
```

### 2.4 建议新增决策原则

```markdown
## 决策原则

- 对外先讲场景，再讲 Skill 清单。
- 跨 Skill 的能力优先沉淀为 Expert Suite，而不是复制 Skill。
- 新 Skill 必须回答：归属哪个场景套件、补哪个能力缺口、让哪条工作流更闭合。
- 法律专业 Skill 必须保留人工复核边界。
- Kit 是分发形态，不反过来定义 Expert Suite。
```

### 2.5 建议新增“何时写 spec”

```markdown
## 何时写 spec

必须先写或补写 spec：

- 新增或重构 `expert-suites/`。
- 改 README 的主叙事。
- 改 Skill 元数据标准。
- 改发布、安装、同步或 marketplace 机制。
- 改多个 Skill 的协作方式。
- 新增 Web Coding 工作流。
- 涉及目录结构迁移。
- 涉及法律专业输出边界。

无需写 spec：

- 单个 Skill 的小修。
- 文案微调。
- 修一个脚本 bug。
- 单个 CHANGELOG / TASKS 更新。
- 不影响结构的小版本更新。
```

### 2.6 注意事项

当前 `AGENTS.md` 已明确“每次修改 AGENTS.md 必须同步更新变更历史”。因此真正落地时，应同时：

- 递增版本号。
- 在底部变更历史表格新增记录。
- 避免一次性塞入过长背景，长内容放到 `docs/PROJECT-CONTEXT.md`。

## 3. PROJECT-CONTEXT.md 建议

建议新增：

```text
docs/PROJECT-CONTEXT.md
```

它是项目总背景，不是具体实现方案。建议结构：

```markdown
# Legal Skills 项目总上下文

## 1. 项目定位

## 2. 用户画像

## 3. 核心抽象

## 4. 当前能力版图

## 5. 八大技能域

## 6. 场景专家套件方向

## 7. 当前成熟套件

## 8. 当前缺口

## 9. 与 WorkBuddy / LobsterAI 的参考关系

## 10. 不做什么

## 11. 后续演进路线
```

### 3.1 PROJECT-CONTEXT 的作用

它应回答：

- Legal Skills 为什么不是普通提示词集合。
- 为什么要从 Skill 清单转向场景专家套件。
- 八大技能域和专家套件是什么关系。
- 哪些套件成熟，哪些只是规划中。
- Pack、Kit、Expert Suite、Agent 的边界是什么。
- 后续研发如何判断优先级。

### 3.2 AGENTS.md 与 PROJECT-CONTEXT 的分工

`AGENTS.md` 写规则：

- 做事前读什么。
- 怎么改文件。
- 怎么更新文档。
- 什么禁止做。

`PROJECT-CONTEXT.md` 写理解：

- 项目为什么这样设计。
- 当前能力地图是什么。
- 长期路线是什么。
- 哪些外部项目只作为启发，不应照搬。

## 4. Specs 体系升级建议

建议新增：

```text
specs/
├── README.md
├── features/
├── bugfixes/
├── refactors/
└── decisions/
```

### 4.1 分类规则

| 类型 | 目录 | 适用场景 |
| :--- | :--- | :--- |
| 功能 | `specs/features/` | 新增用户可感知能力，如 Expert Suite、Web Coding 工作流、校验脚本 |
| 修复 | `specs/bugfixes/` | 修复已有 Skill、脚本、发布流程或文档结构的问题 |
| 重构 | `specs/refactors/` | 不改变对外能力，但调整目录、元数据、命名、结构 |
| 决策 | `specs/decisions/` | 记录重大方向判断，如 Pack / Kit / Expert Suite 的边界 |

### 4.2 文件命名

```text
YYYY-MM-DD-topic-design.md
```

示例：

```text
specs/features/expert-suites/2026-06-13-expert-suite-structure-design.md
specs/features/web-coding-workflow/2026-06-13-web-coding-workflow-design.md
specs/refactors/pack-skills/2026-06-13-pack-to-suite-boundary-design.md
specs/decisions/core-abstractions/2026-06-13-kit-suite-agent-boundary.md
```

建议每个主题建立一个目录，同一主题的迭代用新日期文件保留历史。

### 4.3 specs/README.md 建议内容

```markdown
# Specs 文档规范

## 目录结构

## 文件命名

## 分类规则

## 什么时候必须写 spec

## spec 模板

## 验收标准
```

### 4.4 Spec 模板

```markdown
# 标题

## 1. 背景

为什么要做。

## 2. 目标

做完以后应该解决什么问题。

## 3. 非目标

明确不做什么，避免范围膨胀。

## 4. 用户场景

- 场景 1：
- 场景 2：

## 5. 方案

目录、文件、数据结构、流程。

## 6. 涉及文件

- `path/to/file`

## 7. 边界情况

| 情况 | 处理方式 |
| :--- | :--- |

## 8. 验收标准

- [ ] 标准 1
- [ ] 标准 2
```

### 4.5 第一批建议新增的 spec

1. `specs/features/expert-suites/2026-06-13-expert-suite-structure-design.md`

说明 `expert-suites/` 目录、`suite.yaml` 字段、README 结构、handoff、quality gates、未来导出 Kit 的边界。

2. `specs/features/web-coding-workflow/2026-06-13-web-coding-workflow-design.md`

说明 Legal Skills 内 Web Coding 任务如何从需求、设计、实现、启动预览、Playwright 检查、截图证据到交付。

3. `specs/refactors/pack-skills/2026-06-13-pack-to-suite-boundary-design.md`

说明 `pack-skills/` 与 `expert-suites/` 的关系，避免把松散归类误当流程套件。

4. `specs/decisions/core-abstractions/2026-06-13-kit-suite-agent-boundary.md`

记录 Skill、Pack、Expert Suite、Kit、Agent、Handoff 的边界。

## 5. Web Coding 上下文升级建议

LobsterAI 对 Web Coding 的启发不在于具体 UI 技术栈，而在于它把 Web 功能开发拆成了可验证链路：

- 有 spec。
- 有涉及文件。
- 有边界情况。
- 有验收标准。
- 有前端组件、服务层、状态层、类型定义的分工。
- 有实际浏览器验证和截图检查。

建议新增：

```text
docs/WEB-CODING-GUIDE.md
```

### 5.1 WEB-CODING-GUIDE 建议结构

```markdown
# Web Coding 工作指南

## 1. 适用范围

## 2. 工作流

## 3. 文件组织

## 4. UI 设计原则

## 5. 状态与数据边界

## 6. 验证要求

## 7. 截图与证据

## 8. 不推荐做法
```

### 5.2 推荐工作流

```text
需求理解
→ 写或读取 spec
→ 明确页面 / 组件边界
→ 实现最小可运行版本
→ 启动本地预览
→ 用 Playwright 或浏览器实际检查
→ 截图 / DOM / console 证据
→ 修正问题
→ 总结变更和残余风险
```

### 5.3 Web Coding 验收标准

涉及页面、小工具、可视化、前端组件时，建议要求：

- 页面可实际打开。
- 关键交互能走通。
- 控制台无新增错误。
- 移动端和桌面端不出现明显遮挡或溢出。
- 关键 UI 有截图证据。
- 若有输入输出逻辑，至少验证一个真实样例。

### 5.4 对 Legal Skills 的特殊要求

Legal Skills 的 Web Coding 不应只追求“好看”，还要服务法律工作：

- 页面应优先承载材料、结构、证据、风险、结论。
- 法律业务工具应偏清晰、可扫描、可复核，不要做成营销页。
- 涉及客户、案件、证据、法律结论时，应保留隐私和复核提示。
- 输出物应尽量可导出、可复制、可归档。

## 6. 推荐落地顺序

### 第一阶段：不动现有结构，只补上下文

1. 新增 `docs/PROJECT-CONTEXT.md`。
2. 新增 `specs/README.md`。
3. 新增 `docs/WEB-CODING-GUIDE.md`。
4. 在 `AGENTS.md` 中增加短入口说明，并更新变更历史。

### 第二阶段：建立第一批 specs

1. 新增 Expert Suite 结构设计 spec。
2. 新增 Web Coding 工作流设计 spec。
3. 新增 Pack / Suite 边界重构 spec。
4. 新增核心抽象决策 spec。

### 第三阶段：用 specs 驱动实际改造

1. 创建 `expert-suites/`。
2. 为 3 个核心套件写 `README.md` 和 `suite.yaml`。
3. 补一个轻量校验脚本，检查 suite 引用的 Skill 是否存在。
4. 挑选核心法律 Skill 补输入、输出、handoff、人工复核条件。

### 第四阶段：把规范变成可执行检查

1. 给 `suite.yaml` 增加 schema 或脚本校验。
2. 给 Skill frontmatter 和 README 表格增加一致性检查。
3. 给 Web Coding 任务增加标准验证清单。

## 7. 不建议做的事

- 不要把现有 `AGENTS.md` 一次性改成超长背景文档。
- 不要要求每个小改动都写 spec。
- 不要把 `specs/` 当成替代 `TASKS.md`、`DECISIONS.md`、`CHANGELOG.md` 的地方。
- 不要让 Kit 概念反过来定义 Expert Suite。
- 不要把 Web Coding 规范写成纯审美规则，必须包含可运行和可验证要求。

## 8. 最小可用版本

如果只做最小改造，建议先完成以下 4 个文件：

```text
docs/PROJECT-CONTEXT.md
docs/WEB-CODING-GUIDE.md
specs/README.md
specs/features/expert-suites/2026-06-13-expert-suite-structure-design.md
```

然后再回头更新 `AGENTS.md`，让它引用这些文件。

## 9. 最终判断

Legal Skills 可以借鉴 LobsterAI 的规范化方式，但应保持轻量。

最适合迁移的是：

- `specs/` 的分类和模板。
- `AGENTS.md` 作为项目入口上下文的写法。
- 功能设计中的“背景、目标、用户场景、实现、边界、验收”结构。
- Web Coding 的实际浏览器验证和截图证据要求。

不适合迁移的是：

- 每个小变更都写长设计文档。
- Electron / IPC / Redux 这类与 Legal Skills 当前形态无关的重型结构。
- 把专家套件简化成平台 Kit 或文件夹集合。

推荐的长期形态是：

```text
AGENTS.md                 # 入口规则
docs/PROJECT-CONTEXT.md   # 项目总上下文
docs/EXPERT-SUITE-DESIGN.md
docs/WEB-CODING-GUIDE.md
specs/                    # 跨模块设计记录
skills/                   # 原子能力
pack-skills/              # 松散归类
expert-suites/            # 场景专家套件
```

