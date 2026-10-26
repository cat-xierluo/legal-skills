# 路由模板

本文解决什么问题 / 何时读：当使用者手里已经有若干 provider、account 和 model，却不知道该把它们组织成什么形状的路由时，先读本文选定结构，再用[盘点结果解读](inventory.md)补真实成员、用[操作入口](operations.md)生成计划。本文只给结构与判据，不给模型选择建议；全文示例使用占位 ID。

本文中的脚本与路径以 Skill 安装目录 `<skill-dir>/` 为基准：命令在该目录下执行，本机私有层位于同一目录内的 `config/*.local.json` 与 `state/`，不入库。

私有层的排除口径以 Skill 内两个 ignore 文件为准：`config/.gitignore` 用 `*.local.*` 通配排除全部本地配置（早期逐个列出的 `profile.local.json`、`inventory.local.json`、`route-policy.local.json`、`integration.local.json` 已被通配取代，新私有文件名不必逐名补规则）；`state/.gitignore` 排除该目录下全部运行证据，只保留 `.gitignore` 自身。

## 两条通用结论

选任何模板之前先接受这两条，否则模板里的"兜底"会被理解成"不会发生"。

### 结论 A：顺序只是降低概率，不是硬闸门

组内排在后面的成员，仍然会在前面的成员失败（HTTP 错误、限流、额度耗尽）时被穿透命中。

| 机制 | 实际效果 | 不能用来做什么 |
|---|---|---|
| 组内顺序 | 降低落到该成员的概率 | 不能保证"绝不消耗末尾成员" |
| `use` 规则 | 只把目标提到前面，其它成员仍可回退 | 不能当作"只在命中时使用"的硬闸门 |
| `pause` | 硬排除目标成员 | 条件不含 intent，不能按意图精确暂停；排除面覆盖嵌套组里的同名模型，暂停外层一个成员不等于所有嵌套路径都被禁止 |
| 移出自动路由链 | 唯一可靠的硬性不消耗 | 需另立显式调用入口，并承担它失败即失败的代价 |

想要"绝不消耗某入口"，只能把它移出自动路由链、改为显式调用；顺序本身做不到。`pause` 还可能打断会话粘性，代价是替代来源全不可用时直接失败。落点检查的步骤、断言口径与实测差异见[路由治理](routing-governance.md)的落点检查小节，本文不复述细节。

### 结论 B：每层准备多个来源

单来源层在额度打满或限流后整层失效，请求穿透到下一层或直接失败，事后从 usage 上看不出这一层曾经存在。

| 层 | 来源数 | 失效时表现 | 建议 |
|---|---|---|---|
| 单来源 | 1 | 该层在最前无可用候选，请求直接落到下一层 | 不作为独立能力层：要么补第二个来源，要么并入相邻层 |
| 双来源 | 2 | 前一个不可用时同层第二个承接，能力层不塌陷 | 每个能力层的最低线 |
| 多来源 | 3 及以上 | 覆盖更广，但需逐个确认能力等价 | 只在成员都经过验收时才加 |

补充两条判据：

- 层内来源数只表示**配置候选数**：不等于独立账号容量，也不等于实时健康。同一 provider 的多个 account 可能共享同一套餐池，一处打满会同时影响被当成"多个来源"的成员；成员当前是否可服务要另按盘点与实际回读核
- 成员"进入额度休息""供应商关闭""被移出组"是三种不同状态，数量要在变更前后分别回读，不能只看 `magpie groups` 里还存在几个名字

## 模板选择表

| 模板名 | 适用场景 | 需要几组 | 是否需要意图规则 | 改造成本 |
|---|---|---|---|---|
| `one-group` | 单一客户端入口，账号少，先跑通 | 1 | 否 | 低 |
| `tiered` | 规划、实现、轻任务需要不同能力层 | 3–4 | 建议 | 中 |
| `subagent-exec` | 主 Agent 与子 Agent 要走不同模型 | 2–3 | 否 | 中 |
| `budget-first` | 当次目标明确低价或免费优先 | 1–2 | 否 | 低 |
| `personal-first-team-fallback` | 个人账号与团队账号并存 | 1–2 | 否 | 中 |
| `explicit-strong` | 强模型必须由人显式指定 | 2 | 否 | 中 |
| `compact-cheap` | 辅助调用要单独走低线路径 | 1–2 | 否 | 低 |

"改造成本"指从现有配置迁到该模板的改动量：低＝只调成员顺序与字段；中＝需新增组、调整客户端绑定或规则顺序。

## 模板

### one-group —— 一组走天下
**适用场景**
- 只有一个客户端入口，不想维护嵌套组
- 账号与模型数量还不多，先要一条能读懂、能验收的链
- 后续可再按 `tiered` 拆层，不必一次到位
**结构**

| 角色 | 占位 | 说明 |
|---|---|---|
| 入口 | `group/main` | 客户端唯一绑定对象，只绑组 ID，不绑具体模型 |
| 兜底 | `group/main` 内的第 2、3 成员 | 与入口同组，靠组内顺序承接 |
| 只显式调用 | 无 | 若强模型不能被兜底消耗，移出去改用 `explicit-strong` |
**组内顺序**

| 顺序 | 成员（占位） | 角色 | 说明 |
|---|---|---|---|
| 1 | `example/model-strong` | 主能力 | 默认落点，承接需要判断力的请求 |
| 2 | `example/model-fast` | 次能力 | 第 1 个不可用时承接，能力档位低一档 |
| 3 | `example/model-free` | 末位兜底 | 只在前两个都不可用时被命中；命中即成本边界事件，须单独统计 |
**routing 与 stays 的选择理由**
- `routing=order`：需要可预测的尝试顺序来核对回退链。`smart` 指向额度续期、不表达能力分层；`manual` 无自动失败回退，作为唯一入口时失败即整链失败；`weight` 在 `order` 下的作用未验证
- `stays=auto`：保留缓存。`off` 每请求重选会损失缓存；`session` 与 `strict` 更粘滞，起步阶段用不上
**失效模式**
- 第 1 个成员失效：请求落到第 2 个，能力降一档。先查额度与并发，不要先调顺序
- 第 2 个成员失效：请求落到末位，成本结构改变，观察点同上
- 第 3 个成员失效：全链失败并如实返回错误。保留失败证据与时间窗，不靠重试放大消耗
**适配时必须改的字段**

| 字段 | 该模板给的默认值 | 必须换成什么 |
|---|---|---|
| 组 ID | `group/main` | 使用者自己的入口组 ID；新建组用 `mpr-` 前缀 |
| 成员 | `example/model-strong` / `example/model-fast` / `example/model-free` | 盘点结果中经对应档位验收的真实模型 ID |
| `routing` | `order` | 一般不改；需要按请求配比时另选并单独验证 |
| `stays` | `auto` | 要每轮重选改 `turn`；接受缓存下降才改 `off` |
| 规则与客户端绑定 | 无规则；绑定该组 | 保留用户已确认的既有规则；目录是静态快照，改完要重建并回读可见性 |

### tiered —— 规划、实现、轻任务分层
**适用场景**
- 三类任务的验收标准明显不同，允许用不同能力层承接
- 需要在最终验收上保留强模型，不希望它被轻任务消耗
- 客户端仍只绑定一个入口组
**结构**

| 角色 | 占位 | 说明 |
|---|---|---|
| 入口 | `group/main` | 客户端唯一绑定对象，成员是三个嵌套组 |
| 兜底 | `group/exec`、`group/aux` | 作为成员槽位参与外层回退，内层各自再按自己的顺序选来源 |
| 只显式调用 | `example/model-strong` | 位于 `group/plan` 内；需要硬性验收时由人显式指定该模型 |
**组内顺序**

| 分组 | 顺序 | 成员（占位） | 说明 |
|---|---|---|---|
| `group/main` | 1 | `group/plan` | 规划与关键判断层 |
| `group/main` | 2 | `group/exec` | 边界明确的实现层 |
| `group/main` | 3 | `group/aux` | 轻任务与整理层 |
| `group/plan` | 1 | `example/model-strong` | 规划层主来源 |
| `group/plan` | 2 | `example/model-strong-alt` | 同档第二来源，避免单点塌陷 |
| `group/exec` | 1 | `example/model-fast` | 执行层主来源 |
| `group/exec` | 2 | `example/model-fast-alt` | 同档第二来源 |
| `group/aux` | 1 | `example/model-free` | 轻任务层主来源 |
| `group/aux` | 2 | `example/model-fast` | 轻任务层第二来源 |
**routing 与 stays 的选择理由**
- 外层与内层都显式设 `routing=order`：外层写 `order` 不会把内层也变成固定顺序，内层仍按自己的 routing 与 rules 选来源，所以两层都要设、都要分别回读
- `stays=auto` 只设在外层：经外层入口的请求按外层 affinity 保持会话，内层 `stays` 只在直接请求内层组时生效
- 不用 `routing=smart`：智能选路不表达"规划/实现/轻任务"这种能力分层，也不等于免费优先
**失效模式**
- `group/plan` 整层不可用：请求落到 `group/exec`，强模型层实际没被用上。分层分别发直接请求与经外层请求，看 `tries` 与 `served`
- `group/plan` 内只剩单来源：同档塌陷，需补来源并回读当前可用数
- 内层为空、全休息或被关闭：外层不会因为"引用存在"就获得该能力，先恢复内层可用来源
**适配时必须改的字段**

| 字段 | 该模板给的默认值 | 必须换成什么 |
|---|---|---|
| 组 ID | `group/main`、`group/plan`、`group/exec`、`group/aux` | 使用者自己的组 ID，保持中性名称，不沿用示例名 |
| 成员与嵌套深度 | `example/...` 占位；3 层 | 各层经该档验收的真实模型 ID，每层至少两个来源；嵌套不超过 8 层，不得自引用或同链重复 |
| `routing` | 内外层均 `order` | 按各层真实需要分别设定并分别回读 |
| `stays` | 外层 `auto` | 内层默认不设；需要单独行为时再显式设置 |
| 意图规则 | 无 | 若要按意图分流，规则按顺序维护，追加后核是否被既有规则先命中 |

### subagent-exec —— 主 Agent 与子 Agent 分离
**适用场景**
- 主 Agent 承担判断与验收，子 Agent 承担边界明确的执行
- 希望子 Agent 的重试与长输出不消耗主路径的额度
- 接受"子 Agent 绑定哪个组"由客户端侧决定，而不是由网关自动判断角色
**结构**

| 角色 | 占位 | 说明 |
|---|---|---|
| 入口 | `group/main` | 主 Agent 绑定，偏向判断与验收能力 |
| 兜底 | `group/exec` | 子 Agent 绑为独立入口；或子 Agent 继承 `group/main` 由内层分流 |
| 只显式调用 | `example/model-strong` | 关键验收、终审由人显式指定 |
**组内顺序**

| 分组 | 顺序 | 成员（占位） | 说明 |
|---|---|---|---|
| `group/main` | 1 | `example/model-strong` | 主路径默认落点 |
| `group/main` | 2 | `example/model-fast` | 主路径降档 |
| `group/exec` | 1 | `example/model-fast` | 子 Agent 主来源 |
| `group/exec` | 2 | `example/model-free` | 子 Agent 降档，命中需单独统计 |
| `group/exec` | 3 | `example/model-strong-alt` | 末位，仅在前面都不可用时命中 |
**routing 与 stays 的选择理由**
- 网关只看请求携带的模型名，不区分主 Agent 与子 Agent 角色；本模板是"两个组加两处客户端绑定"，不是网关层的角色开关。客户端侧的持久指定与优先级见[子 Agent 模型指定](subagent-models.md)
- 两个组都用 `routing=order`：两条路径要分别核对落点，自动选路会让"哪条路径承接了失败"难以归因
- `group/main` 用 `stays=auto` 保缓存；`group/exec` 用 `stays=turn`，子 Agent 会话短、上下文增量小，每轮重选更容易落到当前可用的执行来源
**失效模式**
- 子 Agent 未按预期绑定组：落点仍是主路径模型。修客户端侧绑定，不改网关
- `group/exec` 整层不可用：子 Agent 报错或被回退到主路径，核该组成员可用性
- 末位强模型被命中：额度消耗超出预期，把它移出自动链改显式调用
**适配时必须改的字段**

| 字段 | 该模板给的默认值 | 必须换成什么 |
|---|---|---|
| 组 ID | `group/main`、`group/exec` | 使用者自己的组 ID |
| 成员 | `example/...` 占位 | 各自经验收的真实模型 ID |
| `stays` | 主 `auto`、子 `turn` | 按实际会话形态调整 |
| 客户端绑定 | 两侧各绑一个组 | 核对客户端各自暴露的绑定项；不支持则记录 `NOT_VERIFIED` |
| 子 Agent 模型指定 | 由客户端配置 | 按各客户端实际优先级链设置，见[子 Agent 模型指定](subagent-models.md) |

### budget-first —— 低价或免费优先
**适用场景**
- 当次目标已明确"优先用低价或免费资源"，且这一边界由用户重新确认过
- 任务以提取、格式化、整理、明确规则的轻任务为主
- 用户已有的混合资源池是有意设计，本模板不替代它、也不清空它
**结构**

| 角色 | 占位 | 说明 |
|---|---|---|
| 入口 | `group/main` | 客户端唯一绑定对象 |
| 兜底 | `group/main` 内的第 2、3 成员 | 低价层在前，主力层只在低价层不可用时承接 |
| 只显式调用 | `example/model-strong` | 需要高能力时由人显式指定，不靠自动回退触发 |
**组内顺序**

| 顺序 | 成员（占位） | 角色 | 说明 |
|---|---|---|---|
| 1 | `example/model-free` | 首选层 | 命中即成本最优，但不代表能力足够 |
| 2 | `example/model-fast` | 次选层 | 首选层不可用时承接 |
| 3 | `example/model-strong` | 末位 | 只在前面都不可用时被命中；命中即成本边界被突破，须统计 |
**routing 与 stays 的选择理由**
- `routing=order`：`smart` 指向额度续期，不表达"免费优先"，用它得不到本模板想要的顺序
- `stays=auto`：首选层被反复命中时缓存收益最大；`off` 每请求重选会让低成本也变成高重复成本
- 时段策略用 `time` 加 `use` 调优先级，不动成员顺序：`use` 只把目标提到前面，仍会回退；只有当次明确要求绝不消耗某入口时才用 `pause`，并接受替代全不可用时直接失败
**失效模式**
- 首选层额度耗尽：落到第 2 层，成本小幅上升。核额度分类，确认是否与其它入口共享同一池
- 首选层限流：排队或重试增多。调账号级并发或有界队列，不靠多建组
- 第 2 层也不可用：落到末位主力层，核是否违反当次成本边界
- 末位也被命中：请求失败，保留证据，不把失败转成无限重试
**适配时必须改的字段**

| 字段 | 该模板给的默认值 | 必须换成什么 |
|---|---|---|
| 成员 | `example/model-free` → `example/model-fast` → `example/model-strong` | 用户已有的低价层成员；首层必须是已核实为零或极低成本的来源 |
| `routing` | `order` | 不改 |
| `stays` | `auto` | 一般不改 |
| 规则 | 无 | 需要时段偏好时用 `time` 加 `use`，不要用无条件 `use` 规则 |
| 成本边界 | 低价优先 | 必须由用户当次确认；已确认的混合资源池按原样保留 |

### personal-first-team-fallback —— 个人账号优先、团队账号兜底
**适用场景**
- 个人账号与团队账号同时存在，希望默认走个人额度
- 团队账号额度更大但归属方不同，需要可归因的消耗
- 个人账号额度耗尽时希望有明确下一落点，而不是直接失败
**结构**

| 角色 | 占位 | 说明 |
|---|---|---|
| 入口 | `group/main` | 客户端唯一绑定对象 |
| 兜底 | `group/team` | 团队账号来源，作为成员槽位参与回退 |
| 只显式调用 | 无 | 需要指定归属方时用独立组显式调用 |
**组内顺序**

| 分组 | 顺序 | 成员（占位） | 说明 |
|---|---|---|---|
| `group/main` | 1 | `example/provider-a/model-strong` | 个人账号的主来源 |
| `group/main` | 2 | `example/provider-a/model-fast` | 个人账号的第二来源 |
| `group/main` | 3 | `group/team` | 团队账号层 |
| `group/team` | 1 | `example/provider-b/model-strong` | 团队侧主来源 |
| `group/team` | 2 | `example/provider-b/model-fast` | 团队侧第二来源 |
**routing 与 stays 的选择理由**
- 两层都用 `routing=order`：需要能回答"这次消耗记在谁头上"，自动选路会让归属方归因依赖事后推断
- `stays=auto`：个人账号掉线或休息时仍要能迁到团队侧；`strict` 连账号失效都不迁移、错误直接返回 Agent，不适合作为兜底链的粘滞档
- 不用 `routing=usage` 或 `pace` 作为默认：这两者依赖可靠的额度读数，读不到时不能假设可精算
**失效模式**
- 个人账号额度耗尽：落到团队层，归属方变化，核 usage 的 provider、model、账号维度与时间窗
- 个人账号限流：排队增多、延迟上升，调账号级并发或有界队列
- 个人与团队共享同一套餐池：两层同时打满。认定为单来源层，按结论 B 补来源
**适配时必须改的字段**

| 字段 | 该模板给的默认值 | 必须换成什么 |
|---|---|---|
| 组 ID | `group/main`、`group/team` | 使用者自己的组 ID |
| 成员 | `example/provider-a/...`、`example/provider-b/...` | 用户实际持有的 account 下、已启用的显式模型 ID |
| `routing` | 内外层均 `order` | 不改；若要按配比分流需另行验证 |
| `stays` | `auto` | 一般不改 |
| 账号级限制与归属 | 未设定 | 按 provider 账号级并发与有界队列维护，组内 routing 不替代账号限制；记录消耗归属口径便于事后核账 |

### explicit-strong —— 强模型仅显式调用，不参与自动兜底
**适用场景**
- 强模型额度稀缺或成本高，不希望被轻任务和失败回退消耗
- 最终验收、关键判断由人显式指定强模型，其余请求走中低档
- 需要把"能力升级"从自动回退改成人的决定
**结构**

| 角色 | 占位 | 说明 |
|---|---|---|
| 入口 | `group/main` | 客户端唯一绑定对象，成员中不含强模型 |
| 兜底 | `group/main` 内的第 2 成员 | 入口组自身的多来源回退 |
| 只显式调用 | `group/strong` | 独立组，只在显式指定时被使用 |
**组内顺序**

| 分组 | 顺序 | 成员（占位） | 说明 |
|---|---|---|---|
| `group/main` | 1 | `example/model-fast` | 入口组主来源 |
| `group/main` | 2 | `example/model-free` | 入口组第二来源 |
| `group/strong` | 1 | `example/model-strong` | 唯一成员，不配自动回退 |
**routing 与 stays 的选择理由**
- `group/strong` 用 `routing=manual`：只走指定成员、无自动失败回退，失败就如实报错，不会静默降级或改投别的模型
- `group/main` 用 `routing=order` 并排除强模型：主路径需要能回退，但回退链里不存在强模型
- **不能用 `use` 规则实现本模板**：`use` 只把目标提到前面，其它成员仍可回退，规则命中的是"优先"不是"唯一"，与本模板意图相反
- `stays=auto`：单成员组的粘滞没有实际效果，保持与其它组一致的回读口径即可
**失效模式**
- 强模型组不可用：显式调用直接失败，由人决定换模型还是等待，不用网关代选
- 入口组两个来源都不可用：入口请求失败，保留证据，核额度与并发
- 强模型被误留在其它组：轻任务出现高成本落点，清理该成员并跨嵌套组一并核同名模型
**适配时必须改的字段**

| 字段 | 该模板给的默认值 | 必须换成什么 |
|---|---|---|
| 组 ID | `group/main`、`group/strong` | 使用者自己的组 ID |
| 入口组成员 | `example/model-fast`、`example/model-free` | 经验收的中低档模型 ID；确认其中不含强模型 |
| 强模型组成员 | `example/model-strong` | 用户实际的强模型 ID，且必须由人显式指定才进入请求 |
| `routing` 与 `stays` | 主 `order`、强 `manual`；`stays=auto` | 不改；单成员组的粘滞无实际效果 |
| 规则 | 无 | 核对其它组里没有指向强模型的 `use` 规则 |

### compact-cheap —— 压缩/摘要/标题等辅助任务走低价模型
**适用场景**
- 客户端允许为辅助调用单独指定模型
- 辅助调用量较大且单次输出短，值得单独压低成本
- 辅助调用影响后续上下文，需要能力与失败方式都已核实
**结构**

| 角色 | 占位 | 说明 |
|---|---|---|
| 入口 | `group/main` | 主会话入口，与辅助路径分开 |
| 兜底 | `group/aux` | 辅助调用组，组内多来源回退 |
| 只显式调用 | `example/model-free` | 客户端直接指定的辅助模型 |
**组内顺序**

| 分组 | 顺序 | 成员（占位） | 说明 |
|---|---|---|---|
| `group/aux` | 1 | `example/model-free` | 首选，能力已核实可承接该类调用 |
| `group/aux` | 2 | `example/model-fast` | 第二来源，首选不可用时承接 |
| `group/main` | 1 | `example/model-strong` | 主会话路径，与辅助路径分离 |
**routing 与 stays 的选择理由**
- `group/aux` 用 `routing=order`：辅助调用需要可控、可回读，落点必须能回答"这次摘要由谁生成"
- `stays=auto`：辅助调用往往连续多轮命中同一来源，保留缓存更省
- 不假定辅助调用受主组控制：绑定主组并不自动接管会话标题、描述与摘要、输入预测、自动审批、记忆提取、压缩等调用；有些客户端单独指定模型，有些继承主会话，有些用固定内置模型，版本之间也会变
**失效模式**
- 客户端不支持独立指定：辅助调用仍走主会话模型。从客户端帮助、配置 schema 与实际回读核，记 `NOT_VERIFIED`，不伪造绑定
- 辅助请求无法与主请求区分：usage 里看不出对应记录，触发一次代表性辅助行为后再按时间窗、请求类型、provider 定位
- 低价模型压缩质量不足：后续上下文丢失关键信息，按任务产物与验收判定，先核能力与失败方式，不能只按价格降级
**适配时必须改的字段**

| 字段 | 该模板给的默认值 | 必须换成什么 |
|---|---|---|
| 组 ID | `group/aux` | 使用者自己的辅助组 ID |
| 成员与能力判定 | `example/model-free`、`example/model-fast` | 已核实能承接该类辅助调用的模型 ID；逐类辅助调用记录核验范围与失败方式 |
| `routing` | `order` | 不改 |
| `stays` | `auto` | 一般不改 |
| 客户端绑定 | 辅助项指向该组 | 该客户端实际暴露的独立模型字段；未暴露则保持现状并标 `NOT_VERIFIED` |

## 占位示例约定

全文示例只使用下列占位，不含任何真实 provider、model、account、额度、代理地址或本机路径。

| 占位 | 含义 | 替换成什么 |
|---|---|---|
| `example/provider-a`、`example/provider-b` | 两个已启用的 provider | 用户实际在用的 provider 名称 |
| `example/model-strong` | 能力最强的一档模型 | 用户目录中经任务验收的强模型 ID |
| `example/model-strong-alt` | 同档第二来源 | 同档另一来源，能力等价且已验收 |
| `example/model-fast` | 中档执行模型 | 用户目录中经任务验收的执行模型 ID |
| `example/model-free` | 低价或免费模型 | 用户目录中已核实成本的模型 ID |
| `group/main` | 入口组 | 用户自己的入口组 ID |
| `group/plan`、`group/exec`、`group/aux` | 内层或专用组 | 用户自己的中性组名 |
| `group/team`、`group/strong` | 团队侧组、强模型专用组 | 用户自己的组 ID |
| `group/<group-id>` | 泛指某个组 | 实际组 ID |
| `<port>`、`config/*.local.json`、`state/...` | 网关本机端口、本机私有层文件 | 从实际界面或配置核实的端口、使用者自己的私有层文件 |

## 从模板到落地

1. 先按模板搭骨架：确定组数量、每组成员角色、routing 与 stays 的选择；骨架阶段不填真实模型
2. 用[盘点结果解读](inventory.md)补真实成员：按能力档位、额度类型、账号归属把用户已有的 provider、account、model 填进各层，并按结论 B 核对每层来源数
3. 用[操作入口](operations.md)生成计划：新组建组用 `scripts/magpie_route.py plan/apply`，已有组建组用 `scripts/magpie_change.py plan/apply`；成员、routing、stays 与规则都写进计划，绑定内容哈希与有效期
4. 落地前用 `scripts/magpie_preflight.py` 与 `scripts/magpie_inventory.py` 做只读核对
5. 改完按[路由治理](routing-governance.md)的落点检查发代表性请求，核对 routing log 的 `tries` 与 usage 的 `served model`；`CONFIG_READBACK_VERIFIED` 只证明落盘
6. 发布前用 `scripts/public_release_check.py` 检查文档不含真实 provider、model、账号、额度、代理地址与本机绝对路径

提醒：模板给的是结构与判据，不是模型选择建议。模型必须来自用户已有资源，并经过任务验收与实际落点复核后才能进入生产路由。

## 模板与 plan 的边界

模板是**结构判据**，不是 plan 输入格式。`scripts/magpie_route.py plan` 只接受 `magpie-route-policy.v1`，只新建 `mpr-` 前缀的组，字段封闭：`id`、`members`、`routing`、`stays`、`rules`；`routing` 只接受 `order`、`smart`、`usage`、`pace`，`stays` 只接受 `auto`、`session`、`turn`。

因此以下模板要素**不在** plan 支持范围内，需按已核的原生 CLI 或 GUI 单独实施并回读，不能为了套进 plan 而删改设计：

| 模板要素 | 出现在 | 另行实施入口 |
|---|---|---|
| 嵌套组（`group/plan` 作成员槽位） | `tiered`、`personal-first-team-fallback` | [路由治理](routing-governance.md)的嵌套组一节 |
| `routing=manual`、`rotate`、`weight` | `explicit-strong` 等 | [路由治理](routing-governance.md)的单组可配置项一节 |
| `stays=off`、`strict` | 部分模板的备选 | 同上 |
| 意图规则、分类器、`effort=auto`、权重配比 | `tiered` 等 | [路由治理](routing-governance.md)的规则变更与落点检查 |
| 账号顺序、账号级并发与队列 | `personal-first-team-fallback` | [供应商与账号接入](provider-integration.md) |

可执行 policy 的本地副本由 `config/policy.example.json` 复制而来（`cp config/policy.example.json config/policy.local.json`）；`config/route-policy.example.json`（`magpie-route-design.v1`）是设计层示例，只用于规划讨论，不能直接喂给 `plan`。本 Skill 不提供把设计层文件转成可执行 policy 的转换器。
