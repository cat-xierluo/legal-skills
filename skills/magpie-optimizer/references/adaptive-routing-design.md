# 智能路由设计

本文解决什么问题 / 何时读：使用者已经配置了多个 provider、account、model，需要把这些资源组织成适合自己任务形态的路由，而不是照抄某个固定组名或模型名。目标是把「资源盘点 → 用户意图 → 能力层 → 规则 → 验证」变成可复用的设计流程。

本文只写通用方法与判据，不包含真实 provider、模型 ID、账号、额度、代理地址或本机路径。真实选择只能来自当前用户的已授权资源，并写入 `config/*.local.*` 私有层。

## 0. 输入与产出

| 输入 | 来源 | 用于 |
|---|---|---|
| provider / account / group 摘要 | `scripts/magpie_inventory.py scan` | 识别现有资源与待核项；该输出只有计数，不能据它补模型 ID 或断言独立容量 |
| 具体成员、能力与可见性 | 当前用户的 `magpie models <agent>`、`magpie group <id>` 与私有配置投影 | 由 Agent 核对可用模型与嵌套边界，结果留在私有层 |
| 用户偏好与硬边界 | `config/profile.local.json` | 判断能力角色、成本边界、账号顺序、辅助调用 |
| 实际任务样本 | usage / routing log / 交付验收 | 校准意图规则与能力档位 |

产出是一份**设计草案**，不是直接可执行计划：

1. 角色层定义：每层的能力、典型任务、验收标准。
2. 成员映射：用户现有模型到各层的占位映射。
3. 组结构与顺序：入口组、嵌套组、成员槽位。
4. 规则草案：意图规则、压缩规则、账号顺序、硬排除项。
5. 验证矩阵：每层至少一个代表性请求与 expected served model。

后续按[路由模板](routing-templates.md)选形状，按[操作入口](operations.md)生成可执行 plan；嵌套组、分类器、账号顺序等超出 plan 字段的部分用原生 CLI/GUI 单独实施并回读。

设计草案可先复制 `config/route-policy.example.json` 为 `config/route-policy.local.json`，再用只读检查器核结构：

```sh
python3 scripts/magpie_route_design.py validate --design config/route-policy.local.json --strict
```

检查器不读取本机 Magpie 配置、不发起模型请求，也不输出真实成员 ID；它只核 schema、组引用、循环/深度、规则目标、分类器前置条件、compact 顺序和 provider 前缀多样性。provider 前缀多样性只是容量线索，不能替代账号池与真实可用性核对。

## 1. 先抽角色，不先选模型

把用户的工作拆成能力层，而不是先列模型。常见起点：

| 角色 | 典型任务 | 验收重点 |
|---|---|---|
| planning / final-acceptance | 方向重置、项目级启动、多交付物终审 | 决策质量、风险覆盖、验收证据 |
| implementation | 跨文件实现、复杂排障、明确边界的技术执行 | 测试/构建通过、行为正确 |
| execution | 边界清晰、已指定验收的常规执行 | 完成度、成本、返工率 |
| light / aux | 字段提取、格式化、简单查询、压缩、标题/摘要 | 信息保真、失败可见 |
| free / low-cost | 可容错、成本优先的任务 | 成本边界与能力足够性 |

分层判据：

- **能力可互换**：同一层成员必须能承接同类任务并使用相同验收标准。
- **成本可接受**：同层失败后的兜底不违反用户当次成本边界。
- **容量可区分**：同层成员如果共享同一账号/套餐池，不能因数量多而被视为多来源。
- **角色可验证**：每层至少有一个代表性请求能从 routing log 与 usage 归因。

## 2. 从盘点映射资源

对每个已启用 model 只标记抽象属性，不在公开层写真实 ID：

| 属性 | 判读 |
|---|---|
| capability | 是否支持所需上下文、视觉、工具调用、推理档位 |
| cost class | free / subscription / metered / expensive，按用户画像确认 |
| capacity pool | provider + account + 套餐池；多账号共享额度时合并判断 |
| reliability | 近期 429、排队、登录失效、超时；仅作为当次线索，不是永久标签 |
| role fit | 能承担哪些能力层；一个模型可进入多个层，但共享折叠需单独核对 |

映射规则：

1. 多来源是可用性建议，最低数量以用户画像为准。只有一个合格来源时可以保留单来源层并标记单点风险；不得为凑数量合并能力不等价的层或追加未授权资源。
2. 同 provider 下多个账号若共享同一额度池，视为一个容量来源。
3. 个人账号与团队账号的归属边界优先于模型能力相似性。
4. 高成本模型默认不进自动回退链；确需进入时放末位并设置窄规则，接受“顺序不是硬闸门”的事实。
5. 免费层必须证明能力足够；价格优势不能替代任务验收。

## 3. 组结构与规则生成

`config/route-policy.example.json` 采用同一结构：一个 `role=entry` 的外层入口按角色顺序引用多个 `group/<role>` 内层组；外层 `routing=order + stays=turn`，内层各组再按自己的成员顺序和规则承接失败回退。此形状来自可复用的 smart-split 实践，但示例 ID 全部为占位，不代表任何用户的真实资源。

### 3.1 外层入口

外层只做角色层排序，默认：

```text
main group:
  1. role: planning / default analysis
  2. role: implementation / same-tier fallback
  3. role: execution
  4. role: light / free
  5. optional: expensive explicit tier (only if user accepts fallback cost)
```

默认 `routing=order`：链路可预测、失败路径可归因。`smart` 不表达能力分层；`usage`/`pace` 只有在额度读数可靠时才可评估。

`stays=turn` 适合外层规则较多的主入口：新回合可重新按当前规则与资源状态选择，同时本回合内保持稳定。若用户更重视缓存连续性，可用 `auto`，但需验证旧成员休息时是否拖长迁移。

### 3.2 内层能力组

每个内层组是一组可互换来源：

```text
role group:
  1. primary source
  2. same-tier alternate
  3. optional low-cost alternate
```

- 内外层均显式 `routing=order`，并分别回读。
- 内层 `stays=turn` 常用于短生命周期子任务；直接请求内层与经外层请求的保持语义不同，需分别验证。
- 同一 provider/model 与固定 effort 在兄弟嵌套组中可能折叠到首次出现位置；这是可接受的共享，不是组循环，但会改变默认首次落点。

### 3.3 意图规则

规则是“把某层提到前面”，不是硬隔离。生成顺序建议：

1. `compact` → 低成本执行层。
2. 明确轻任务 → free/light 层。
3. 普通分析/实现 → 主力层。
4. 明确困难升级 → 强模型层，`useEffort` 只在模型支持档位时设置。
5. 项目级启动/终审 → 最高能力层，规则描述必须排除普通规划和常规 review。

每条规则的 intent 必须互斥、可由分类器区分，并写“不是什么”：

```text
use: role:final-acceptance
intent: project-wide kickoff, major direction reset, or final acceptance across completed deliverables; not routine planning or ordinary review
```

分类器选低成本且稳定的成员；无 intent 规则时不要单独设置 classifier。

### 3.4 子 Agent 与辅助调用

子 Agent、压缩、标题/摘要、网页搜索不一定继承主入口。按[子 Agent 模型指定](subagent-models.md)核对客户端配置链，再分别验证：

- 主会话请求：规则命中与 served model。
- 子 Agent 请求：客户端默认/持久指定是否生效。
- 辅助请求：独立字段是否存在、落点是否可观测。

不能验证的路径标 `NOT_VERIFIED`，不假定绑定主组即接管全部调用。

## 4. 用户画像字段使用

`config/profile.local.json` 是由 Agent 读取的私有设计输入。`roles`、`constraints`、`account_priority` 由 Agent 在设计时解释，盘点脚本不会自动推荐模型或实施这些偏好；`plan/apply` 也不读取它们。检查器只校验设计结构。关键字段：

| 字段 | 用法 |
|---|---|
| `roles.*.capability` | 写清任务定义与验收标准 |
| `roles.*.models` | 留空表示待 Agent 根据当前模型目录和任务验收补全；显式值表示用户确认选择 |
| `roles.*.sources_per_tier` | 用户期望的每层来源数，实际独立容量另核 |
| `constraints.expensive_models_explicit_only` | 是否允许高成本模型进入自动链 |
| `constraints.expensive_models` | 用户确认的高成本模型清单；为空时只输出未评估，不推断模型等级 |
| `constraints.personal_account_before_team` | 账号归属优先级 |
| `auxiliary_routes.*` | 辅助调用的独立目标 |

画像中的显式值是用户意图；盘点结果是本机事实。二者冲突时先向用户确认，不自动改边界。

## 5. 设计检查矩阵

| 检查 | 通过标准 |
|---|---|
| 角色完整性 | 每层有任务定义、成员、验收标准 |
| 来源容量 | 区分候选数与独立账号池；单来源风险已说明，满足用户确认的可用性要求 |
| 成本边界 | 高成本成员的位置与规则符合画像约束 |
| 账号归属 | 个人/团队/共享池边界清晰 |
| 规则互斥 | intent 描述不含重叠大类；分类器可区分 |
| 客户端边界 | 主、子 Agent、辅助调用各自可见并已验证或标 NOT_VERIFIED |
| 失效路径 | 每层失效后的下一落点可预测 |
| 回读验证 | 配置成员、routing、stays、rules、off 状态全部回读 |
| 行为验证 | 每层代表性请求核对 rule/tries/served |

## 6. 禁止事项

- 不从模型名推断能力；以目录能力、任务验收与实际请求为准。
- 不把 provider 数量当容量；共享账号池会同时失效。
- 不把 `use` 当硬隔离；硬性不消耗必须移出自动链或 `pause`。
- 不为“智能”引入模糊规则；规则越多，分类器漂移和误命中越难归因。
- 不把个人组名、模型名、额度数值写入公开文档或 example。
- 不把设计层 `magpie-route-design.v1` 直接喂给 plan；先转成可执行 policy 并校验。

## 7. 最小工作流

1. 运行 inventory，得到脱敏 provider/model/account/group 快照。
2. 复制 `config/profile.example.json` 为 `config/profile.local.json`，补角色、约束与辅助调用。
3. 生成角色层草案：每层能力、成员占位、来源数、验证请求。
4. 选模板：一组、分层、主/子 Agent、低价优先、个人/团队、显式强模型、辅助低价。
5. 生成规则草案：压缩、轻任务、普通、困难升级、终审，逐条互斥并加“不是什么”。
6. 生成计划前核对：成员可见、provider 启用、账号池不重复、模型档位支持。
7. 执行后回读配置；每层发代表性请求并核对 rule/tries/served。
8. 把实际偏差写回 `profile.local.json` 或重新调整层，不在通用层硬编码个人结论。
