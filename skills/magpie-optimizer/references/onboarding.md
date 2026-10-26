# 入门主路径

本文解决什么问题 / 何时读：本文给出一条 6–8 步、可直接执行的新手入门路径，适用于第一次使用 Magpie、但已经持有若干供应商账号的开发者、律师与知识工作者；读完之后应当能装好入口、接入已有账号、生成一份可审阅的变更计划，并用一次真实请求证明路由确实生效。已经在用 Magpie、只想调某一个具体坑位的使用者，直接读[路由治理](routing-governance.md)与[CLI 与变更边界](cli-contract.md)，不必从本文第 1 步重来。

本文只写通用做法与占位示例。真实供应商名、模型 ID、账号、额度、代理地址与本机绝对路径一律不出现在本文，按 `<...>` 占位标注。

**以下命令在 Skill 目录内执行，`scripts/`、`config/`、`state/` 均相对该目录。**

## 心智模型

先把这八个对象对齐，后面八步的每一步都在动其中之一。

| 对象 | 定义 | 本文在哪一步会碰到 |
|---|---|---|
| provider（供应商） | 一个上游模型服务来源，成员写作 `example/provider-a`。它是额度与限流问题的第一归因位置 | 第 3 步盘点、第 4 步接入、第 7 步变更 |
| account（账号） | 某供应商下的一个登录或密钥身份。额度、并发与队列挂在账号层，且跨模型、跨分组共享 | 第 3 步盘点（以脱敏标签出现）、第 4 步接入 |
| model（模型） | 上游的具体模型，写作 `example/model-strong`。某模型是否可用，由供应商与账号共同决定，不由模型名本身决定 | 第 3 步盘点、第 5 步选层、第 6 步画像 |
| routing group（路由组） | 把若干成员组织成一条候选链的容器，是客户端真正绑定的对象。组的职责是组织成员与失败路径，不替代账号级限流 | 第 5 步定结构、第 7 步变更、第 8 步验证 |
| agent（客户端接入方） | 把请求送进网关的客户端，例如某个 CLI 或 IDE 插件。绑定写法为 `magpie <agent> group/<group-id>` | 第 1 步确认客户端、第 4 步接入、第 8 步核对落点 |
| 可见性 | 决定成员或组对客户端是否可见、以及客户端模型目录里显示什么。目录可能是静态快照，改配置不等于目录刷新 | 第 4 步接入、第 8 步验证 |
| routing 模式 | 组内挑选成员的方式，如 `order`、`smart`、`rotate`、`usage`、`pace`、`weight`、`manual`。不同模式下的「排在末位」含义不同（其中只有 `order`、`smart`、`usage`、`pace` 在第 7 步新建组的 plan 输入内，其余走原生命令，见[操作入口](operations.md)） | 第 5 步定结构、第 7 步写入 |
| served model（实际服务模型） | 一次请求最终由哪个成员应答。从 usage 读出，是「配置真的生效」的唯一运行时证据 | 第 8 步验证 |

术语约定：下文「组」一律指 routing group；「成员」指组内的 provider/model 条目；「落点」指某次请求实际由谁应答。

## 步骤总览

| 步 | 目的 | 主要命令 | 产出物 | 是否写配置 |
|---|---|---|---|---|
| 1 | 确认已安装并登录、网关在跑 | `magpie --version`、`magpie ls` | 版本号与客户端清单 | 否 |
| 2 | 跑体检，确认环境可读可用 | `python3 scripts/magpie_preflight.py check` | 体检状态行 | 否 |
| 3 | 盘点已有资源 | `python3 scripts/magpie_inventory.py scan` | 脱敏盘点 JSON 摘要 | 否 |
| 4 | 接入供应商与账号 | 见[供应商与账号接入](provider-integration.md) | 可用供应商、账号与模型目录 | 是（新增接入） |
| 5 | 决定「一套走天下」还是分层 | 见[路由模板](routing-templates.md) | 入口结构草案 | 否（只出草案） |
| 6 | 生成本机画像 | 复制 `config/profile.example.json` 为 `config/profile.local.json` | 本机画像文件 | 是（本地副本） |
| 7 | 生成变更计划并执行 | 见[操作入口](operations.md)与[CLI 与变更边界](cli-contract.md) | 计划、计划哈希与回执 | plan 否／apply 是 |
| 8 | 用真实请求验证落点 | 发一个代表性请求并读 usage 与路由日志 | 落点证据 | 否 |

纪律：第 1–3 步全程只读，任何一步失败都先解决该步再往下走；第 4 步之后每一步的写入都要有对应的回读。

## 1. 确认已安装并登录、网关在跑

**目的**：确认 Magpie CLI 在本机可用、账号已登录、本机网关正在运行，且客户端侧能被识别。这一步不通，后面所有命令的输出都不可信。

**命令**

```sh
magpie --version
magpie ls
```

**期望输出**

- `magpie --version` 返回一行版本号，例如 `magpie <version>`。
- `magpie ls` 列出已检测到的客户端（agent），以及它们当前可见的组或模型。

**常见偏差**

- CLI 未在 PATH：提示找不到命令。改用安装版完整路径，或先修正 PATH；不要为了跑通而重装覆盖已有安装。
- `magpie ls` 为空：通常是没有客户端安装或未被识别。先确认客户端已装且能正常发起请求，再谈绑定；此时网关本身可能是好的。
- 子命令名随版本变化：`ls` 之外，`magpie groups`、`magpie models`、`magpie group <group-id>` 是稳定的只读盘点入口。用 `magpie --help` 核对当前安装版支持哪些子命令。
- 版本与本 Skill 记录的不一致：以本机为准。Skill 里的版本号是写作时的快照，升级后先重读 CLI 帮助再套用本文命令。

## 2. 跑体检

**目的**：在改任何配置之前，确认脚本能运行、依赖满足、本机网关可连、配置目录可读。体检只读，不写配置。

**命令**

```sh
python3 scripts/magpie_preflight.py check
```

**期望输出**

一行状态汇总，形如 `ok=<n> warn=<n> fail=<n>`，随后是逐项 check 明细。`fail` 必须清零后才进入下一步；`warn` 可以带着走，但要记下它影响哪一步。

check 覆盖的类别与处置（一句话概览，权威表在[环境体检详解](preflight.md)）。另有一个包级自检入口 `scripts/public_release_check.py`，用于本 Skill 自身的发布前核对，不在使用者的入门路径上。

| check 类别 | 含义 | 处置 |
|---|---|---|
| Python 版本 | 脚本只用标准库，不需 pip，但仍要求最低版本 | 不满足时 `fail`，改用本机已有合规 Python，不改环境 |
| CLI 可达 | PATH 中能否找到 Magpie CLI | 找不到时先修 PATH 或改用完整路径 |
| 网关可达 | 本机网关是否在跑、地址是否可连 | 不通时在应用界面确认网关状态；不自行启动公开服务或升级软件 |
| 配置目录可读 | 能否读取本机 Magpie 配置（尊重 `XDG_CONFIG_HOME`） | 读不到时核环境变量与文件权限，不要复制真实认证到别处排查 |

**常见偏差**

- Python 版本偏低：先确认本机是否已有合规版本，再决定是否安装。
- 脚本路径相对当前目录：脚本路径相对本 Skill 目录解析。在别处执行会报找不到脚本，此时回到 Skill 目录或改用相对本 Skill 的路径。
- 网关端口不是默认端口：体检按实际界面或配置核实端口，不要假定固定端口；不要为了通过体检去改网关配置。

## 3. 盘点已有资源

**目的**：设计之前先知道本机已有什么：哪些客户端已接入、哪些供应商已启用、有哪些账号与组、已知风险在哪。

**命令**

```sh
python3 scripts/magpie_inventory.py scan
```

**期望输出**

一份 JSON 摘要，含四段：

| 段 | 读什么 | 用来决定 |
|---|---|---|
| `agents` | 已检测到的客户端及其可见的组与模型 | 第 4 步接哪个客户端、第 5 步绑哪个入口 |
| `providers` | 已启用供应商、暴露的模型、账号数量（脱敏标签） | 第 4 步补什么账号、第 6 步画像填什么 |
| `groups` | 已有组的成员、routing 模式、是否停用 | 第 5 步沿用还是新建、第 7 步改哪个对象 |
| `risks` | 盘点期可判定的线索，如组停用、成员当前不可服务、目录与组不一致 | 第 5、7 步需要先处理的前置问题 |

账号以脱敏标签出现，不出现真实账号名、邮箱或密钥。

**常见偏差**

- 把盘点快照当事实源：快照是读取当时的状态。后续每改一次配置就重新 scan 一次，不要用旧快照判断当前可用性。
- 读不到某些额度字段：保留「未知」，不要写成 0，也不要据此断言「免费」或「无限」。
- 供应商已启用但模型列不出来：这是「未暴露」，不是额度耗尽，两者的处置位置不同（见[路由治理](routing-governance.md)的失败定位表）。

## 4. 接入供应商与账号

**目的**：把已有的供应商账号接进 Magpie，核到模型可选，并确认账号级限制读得到。

完整步骤、支持的 provider 字段与账号级参数见[供应商与账号接入](provider-integration.md)；此处只给最小核对命令。

**命令**

```sh
magpie models
magpie quota --json
magpie provider test example/provider-a
magpie provider account-concurrency example/provider-a
```

**期望输出**

- `magpie models` 中出现目标模型（如 `example/model-strong`）。
- `magpie quota --json` 给出额度读数；读不到的部分保留未知。
- `magpie provider test` 报告该供应商当前是否可服务。
- 省略修改值的 provider 查询命令返回限制值而不是改写配置。

**常见偏差**

- 启用供应商 ≠ 有额度 ≠ 模型可调用：三件事分别核，不要用其一推断其二。
- 账号级并发与队列是跨模型、跨分组共享的总上限。不能用「多建一个组」来扩容。
- 可见性没跟上：新增的组可能不出现在客户端模型目录里。目录快照与刷新机制属于坑位，细节见[路由治理](routing-governance.md)的客户端侧一节，本文不重复。
- 命令返回 0 不代表能力存在：部分版本的 provider 子命令只回总帮助。必要时按[CLI 与变更边界](cli-contract.md)的环境隔离办法验证参数。

## 5. 决定「一套走天下」还是分层

**目的**：定下入口结构：客户端只绑一个组（一套走天下），还是保留多个组按任务选择。这是一次设计决定，不是配置写入。

具体模板与成员组织方式见[路由模板](routing-templates.md)；入口语义见[通用 smart-split](smart-split.md)；建组与拆组判据、能力层治理见[路由治理](routing-governance.md)。

**命令**

本步不执行 CLI 写入命令。产出是一份结构草案：

```
入口组：<group-id>
客户端绑定：magpie <agent> group/<group-id>
成员顺序：example/model-strong → example/model-fast → example/model-free
routing：order
stays：auto
嵌套组：<group-id>/<nested-group-id>（若需要分层）
```

**期望输出**

一份可被第 7 步转成计划的草案：入口组 ID、成员顺序、routing 模式、stays、是否需要嵌套组、每个能力层准备几个来源。

**与 plan 的衔接**：草案里的字段要落到第 7 步的 plan 输入，先对照[操作入口](operations.md)的执行边界核对：`plan` 只新建 `mpr-` 前缀的组，字段封闭，routing 只接受 `order`、`smart`、`usage`、`pace`，stays 只接受 `auto`、`session`、`turn`，成员必须是已启用 provider 下已暴露的具体模型 ID。草案里的嵌套组、意图分流、分类器与账号顺序**不在** plan 支持范围内，也不是 plan 缺少能力——它们按已核的原生 CLI 或 GUI 单独实施，见[操作入口](operations.md)与[路由治理](routing-governance.md)。

**常见偏差**

- 客户端绑了具体模型而不是组：这样会绕过组内分流，整套设计的价值消失。
- 组存在 ≠ 外层入口会选到它：能力层必须被外层显式引用，判据见[路由治理](routing-governance.md)的能力层治理一节。
- 一个能力层只放一个来源：该来源一旦进入额度休息或限流，该层就没有承接。
- 改了外层 routing 就以为内层也变了：内外层的 routing 与 rules 相互独立，判据同样见[路由治理](routing-governance.md)。
- 想推倒既有组重来：既有设计里可能有已确认的成本边界，处置顺序见[通用 smart-split](smart-split.md)与[额度、任务与成果](token-strategy.md)。

## 6. 生成本机画像

**目的**：把本机事实与已确认的意图固化成一份可复用的记录，让第 3 步盘点按同一份依据判风险，而不是每次重新口头描述。

**命令**

```sh
# 按 references/configuration.md 创建拒绝覆盖、权限 0600 的 profile.local.json
```

**期望输出**

`config/profile.local.json` 存在、可解析。读它的入口是第 3 步的盘点脚本（`scripts/magpie_inventory.py`）：盘点用它判定昂贵模型兜底与辅助路由落点，并把结果写进 `risks` 与 `notes`。**plan 与 apply 不读取画像**——画像是意图与事实的记录，不是策略输入文件。

**填充口径**

| 字段类型 | 填法 |
|---|---|
| 本机画像填法 | 填本机实际持有并授权使用的模型 ID，例如 `example/model-strong` |
| 留空由扫描推荐 | 空数组表示待 Agent 结合第 3 步摘要、真实模型目录及验收补全；扫描脚本不推荐模型 |
| provider 与 account | 填稳定的供应商标识与账号脱敏标签，不写账号名或邮箱 |
| 成本边界 | 填本次已确认的边界，例如「某类资源可作兜底」；边界一旦确认不要中途改写 |
| 网关地址与端口 | 填实际值，文档里以 `<gateway-url>`、`<port>` 形态出现 |
| 任务与验收口径 | 填该画像适用的任务类别与验收标准，便于后续效果比较 |

**常见偏差**

- 把真实账号、密钥、代理地址写进画像：画像是本机私有文件，保留在 `config/*.local.json`（由 `config/.gitignore` 的 `*.local.*` 通配排除）或 `state/`（由 `state/.gitignore` 排除全部运行证据），不进版本库。
- 把扫描结果当事实硬编码进画像：画像里的显式值是「用户确认的选择」，与「扫描读数」是两回事。
- 一次填满所有字段：先填第 4 步与第 5 步已经确定的部分，其余留空。

## 7. 生成变更计划

**目的**：把草案转成可审阅、可回滚的变更，先看计划、人工确认，再执行，执行后逐项回读。

入口命令与 schema 见[操作入口](operations.md)；字段语义、写入语法与边界见[CLI 与变更边界](cli-contract.md)。

**命令**

新建组：

```sh
python3 scripts/magpie_route.py inspect --live --output state/inventory.json
python3 scripts/magpie_route.py plan --policy config/policy.local.json --output state/plan.json
python3 scripts/magpie_route.py apply --plan state/plan.json --plan-sha256 <sha256> --execute --receipt state/receipt.json
```

改已有组：

```sh
python3 scripts/magpie_change.py plan --spec state/change.json --output state/change-plan.json
python3 scripts/magpie_change.py apply --plan state/change-plan.json --plan-sha256 <sha256> --execute --receipt state/change-receipt.json
```

新建组的 plan 输入来自 `config/policy.example.json` 的本地副本（`cp config/policy.example.json config/policy.local.json`）；`config/route-policy.example.json` 是设计层示例（`magpie-route-design.v1`），只用于规划，不能直接喂给 `plan`。plan 的可执行边界（新建限定、字段封闭、routing 与 stays 取值、成员与规则限制）见[操作入口](operations.md)。

**期望输出**

- `plan` 产出一份可读的计划文件与一个计划哈希（`--plan-sha256` 的取值来源）。
- `apply` 产出回执文件。
- apply 后回读目标对象，并确认无关配置未变；只有配置落盘这一层结论。

**常见偏差**

- 直接改 `providers.json`：绕过计划、哈希、漂移检查与回读，且该文件有密钥、有并发写入者。
- 跳过人工确认直接 apply：计划是给人审阅的，确认环节不是形式。
- 沿用旧哈希：计划有有效期，配置漂移后旧计划不再适用，重新生成。
- 一次顺带做多件事：接入账号、改组、动客户端默认值要分开授权、分开验证。
- 组被停用却找不到开关：停用状态没有 CLI 开关，处理路径见[路由治理](routing-governance.md)的坑位一节。

## 8. 用真实请求验证

**目的**：用一次真实请求证明落点符合预期。配置回读只证明落盘，不证明生效。

**命令**

```sh
curl -s http://127.0.0.1:<port>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <local-key>" \
  -d '{"model":"group/<group-id>","messages":[{"role":"user","content":"<该难度的一句话>"}],"max_tokens":25}'

magpie usage today
```

**期望输出**

- 请求返回成功。
- `magpie usage today` 中该请求的 `served_model` 落在预期的能力层。
- 路由日志中能读到该请求的逐次尝试序列。

**落点检查清单**

- 响应体里的 `model` 可能是组名，不等于最终成员；served model 以 usage 为准。
- 「规则命中」与「实际落点」要分开断言，两者不一致有多种互不相同的成因。判据与排查顺序见[路由治理](routing-governance.md)的落点检查一节。
- 每个能力层至少各发一次代表性请求；用了嵌套组时，内层组与外层入口分别核，避免只看到最终 served model 而不知道哪一层完成了回退。
- 记录 `CONFIG_READBACK_VERIFIED` 只代表配置落盘；运行时结论要另取真实请求证据。证据边界见[验证与证据边界](verification.md)。
- 客户端侧要另行核对：目录是否已刷新、客户端重启后是否真的看到新组。判据见[路由治理](routing-governance.md)的客户端侧一节。

**常见偏差**

- 只做配置回读就宣布配置生效。
- 拿响应体的 `model` 字段当 served model。
- 只测一条请求就下「路由正确」的结论。
- 把一次观测直接当成因果证明；对比时保留时间窗、改动项与混杂因素。

## 第一次不要做什么

- **不要一上来就建很多组。** 先把一个入口组跑通，再用真实请求验证；分层是第二步的事。
- **不要直接改 `providers.json`。** 该文件含密钥且有并发写入者，改动走 plan、人工确认、apply、回读。
- **不要先动额度、并发与队列相关设置。** 先用默认行为跑通，观察到真实排队或限流再调；这些是账号级共享上限。
- **不要把「组名」当作配置正确性证据。** 组存在、组被引用、客户端可见，都不等于落点正确。
- **不要在没跑真实请求前宣布配置生效。** 配置回读只证明落盘。
- **不要把个人账号、额度、代理地址、模型 ID 写进通用文档或版本库。** 这些留在 `config/*.local.json` 与 `state/` 私有层，不进版本库。
- **不要在一次变更里顺带改客户端默认模型、启用所有使用者或开启停用供应商。** 维护一个组与激活它，是两次独立授权。

## 下一步

- 需要更细的坑位与排障顺序：[路由治理](routing-governance.md)。
- 需要动配置的操作细节：[操作入口](operations.md)、[CLI 与变更边界](cli-contract.md)。
- 需要比较改造前后的消耗与质量：[任务、成果与效果复核](outcomes.md)、[额度、任务与成果](token-strategy.md)。
- 需要接更多供应商账号：[供应商与账号接入](provider-integration.md)；需要挑路由结构：[路由模板](routing-templates.md)。
