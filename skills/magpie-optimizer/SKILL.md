---
name: magpie-optimizer
description: 用 Magpie 配置并优化 AI 工作效能：接入供应商、订阅与插件，配置模型路由组与意图规则，管理网关、可见性、共享 MCP 与搜索；盘点额度与套餐，诊断 Token 消耗与限流，把每次调整关联真实任务验收效果。
license: MIT
metadata:
  version: "1.7.0"
  author: 杨卫薪律师（微信ywxlaw）
  homepage: https://github.com/cat-xierluo/legal-skills
---

# AI 工作效能优化

用 Magpie 观察 AI 工作，关联真实任务与产物，再决定怎样调整模型、上下文、工具使用和工作时间。以质量达标后的交付成本、耗时和返工衡量效果。统一使用 `magpie-optimizer` 名称。

## 选择工作方式

| 用户需要 | 执行路径 |
|---|---|
| 第一次配置 Magpie，不知道从哪下手 | 读[入门主路径](references/onboarding.md) |
| 扫描本机 Agent 与供应商、账号和额度现状 | 读[环境体检](references/preflight.md)与[脱敏盘点](references/inventory.md) |
| 接入新账号、导入供应商或安装插件 | 读[供应商与账号接入](references/provider-integration.md)与[插件与客户端接入](references/plugin-guide.md) |
| 为什么消耗快，哪里值得优化 | 先采集、核覆盖，再诊断；必要时按会话深入 |
| 怎样利用套餐和临期积分 | 诊断结合现有任务，读取[资源策略](references/token-strategy.md)，输出当前/稍后/待输入建议 |
| 新建路由或改已有组 | 先按[智能路由设计](references/adaptive-routing-design.md)生成草案；再读[配置合同](references/cli-contract.md)和[操作入口](references/operations.md)，展示计划，按已有授权执行 |
| 查某个 magpie 子命令的写法，或接入供应商、订阅、插件 | 读[CLI 命令参考](references/cli-command-reference.md)；涉及写入时按[CLI 与变更边界](references/cli-contract.md)先只读回读并展示计划 |
| 已有多个 provider，不知道怎么分层、哪些模型放同一层 | 读[智能路由设计](references/adaptive-routing-design.md)，先抽角色与硬边界，再映射到现有资源 |
| 单一入口里嵌套多个能力组并配意图规则 | 读[智能路由设计](references/adaptive-routing-design.md)，用 `magpie_route_design.py validate` 先核结构，再按[操作入口](references/operations.md)生成/执行变更 |
| 跨 harness 共用难易任务自动分流 | 读取[通用 smart-split](references/smart-split.md)，复用稳定组ID，核规则和有意回退 |
| 查额度还剩多少、窗口何时重置、等额度恢复 | 读[额度读数合同](references/cli-command-reference.md#额度读数合同magpie-quota---json)，按窗口口径回答；[额度、任务与成果](references/token-strategy.md)承接成本与资源安排 |
| 只用一个组当统一入口、建组/拆组、组内分层与回退治理 | 读取[路由治理](references/routing-governance.md)，按坑位排障、成员分层、计点溢出、规则顺序、出口代理分层与可配置项落地 |
| 给某 harness 的子 Agent 单独配模型、核优先级与坑 | 读取[子Agent模型指定](references/subagent-models.md)，先核安装版与该客户端可见模型列表 |
| 派发时指定了子 Agent 模型却没按它跑 | 读取[指名覆盖观测](references/subagent-override.md)，核请求名、统一默认与实际 served 是否一致 |
| 改完是否有效，是否留下成果 | 关联任务、实际产物与验收；运行效果复核，保留混杂因素和样本边界 |

先运行 `magpie --version`，以安装版 CLI 帮助及实际接口为准。Magpie 可有耗时的会话索引；超时是读取尚未完成，先保留部分状态，不判断能力不存在。使用本机已有网关，端口从实际界面/配置核实；不为诊断启动公开服务或升级软件。

## 从零开始配置

面向第一次配置 Magpie 的场景。前三步全程只读，任何一步失败先解决该步再往下走；第四步之后每一步的写入都要有对应的回读。完整路径见[入门主路径](references/onboarding.md)。

| 步 | 目的 | 入口 |
|---|---|---|
| 1 | 确认已安装并登录、网关在跑 | `magpie --version`、`magpie ls` |
| 2 | 跑体检，确认环境可读可用 | `python3 <skill-dir>/scripts/magpie_preflight.py check --output <skill-dir>/state/preflight.json` |
| 3 | 盘点本机已有的 Agent、供应商、账号与组 | `python3 <skill-dir>/scripts/magpie_inventory.py scan --output <skill-dir>/state/inventory.json` |
| 4 | 接入供应商与账号 | [供应商与账号接入](references/provider-integration.md) |
| 5 | 决定一套走天下还是分层 | 复杂配置读[智能路由设计](references/adaptive-routing-design.md)，常规形状选[路由模板](references/routing-templates.md) |
| 6 | 生成本机画像 | 复制 `config/profile.example.json` 为 `config/profile.local.json`，按[智能路由设计](references/adaptive-routing-design.md)标注角色、意图与硬边界 |
| 7 | 生成变更计划并执行 | [操作入口](references/operations.md)与[CLI 与变更边界](references/cli-contract.md) |
| 8 | 用真实请求验证落点 | 发一个代表性请求，读 usage 与路由日志 |

配置语义由八个心智对象构成：provider、account、model、routing group、agent、可见性、routing 模式、served model。体检结果按 ok / warn / fail 判定，check code 与处置见[环境体检](references/preflight.md)；盘点输出是只读快照而非事实源，字段读不到不等于 0，结构与风险段见[脱敏盘点](references/inventory.md)。接入方式、可见性、多账号行为、额度窗口与并发见[供应商与账号接入](references/provider-integration.md)；插件形态、安装前须确认项与回读验证见[插件与客户端接入](references/plugin-guide.md)。

### 私有层与自包含

私有层放在 Skill 目录内，与公开层同一棵树，靠 ignore 分离：

- `config/*.local.*` 是本机私有层，由 `config/.gitignore` 的 `*.local.*` 通配排除，不进版本库。
- `state/` 放运行产物：观察、盘点、计划、回执与快照，同样不进版本库。
- 公开层只有 `config/*.example.*` 与 schema 定义。
- 原始 `TASKS.md` 与 `DECISIONS.md` 放在同一 Skill 目录，由 Skill 内 `.gitignore` 排除；公开树不复制这两份维护记录。

新增私有配置名无需逐名补 ignore 规则，通配已覆盖；新增公开配置仍必须是 `*.example.*` 或 schema。复制清单和最小路径见[配置样例](references/configuration.md)，完整隐私口径见[隐私与公开边界](references/privacy.md)。

Skill 自包含：单独安装到任意路径即可用，配置、状态与脚本的相对关系不变，命令里的相对路径仍然成立，不需要另外维护仓库外的目录约定。

## 1. 观察与覆盖

```sh
python3 scripts/magpie_observe.py collect --period week --day 2026-10-15 --gateway http://127.0.0.1:<port> --output /private/path/observation.json
python3 scripts/magpie_observe.py diagnose --observation /private/path/observation.json --output /private/path/diagnosis.json
```

日期、网关和输出位置换为当前请求的实际值。优先已结束的一天，减少分页时新增记录的影响。`--day` 限定请求账日期；不指定时使用 period。读取单次默认可等 180 秒，总预算 600 秒；进程运行时每约一分钟向用户更新进度，避免启动多个同类全量扫描。最大分页可调；未覆盖时保留 PARTIAL/PENDING，不以空列表冒充成功。续读与来源合同见[观测说明](references/observation.md)。

<!-- skill-lint:constraint MO-COVERAGE -->
`COMPLETE_PAGINATION` 只表示本次分页读到 API 声明的全部请求并完成首尾检查；不保证平台账单完整，也不是跨页事务快照。原生调用、网关调用和客户端上报分别保留，遵循 Magpie 返回的关联/去重结果。上下文是保留路由样本；工具是本地缓存文件计数，均不与账单相加。

默认只输出字段白名单、聚合与会话/项目摘要标识。脚本会只读本机 HTTP、配置、路由历史和会话缓存；不导出密钥、账号、路径、标题、提示词或工具参数。进一步读取具体会话内容时按任务最小必要处理，保存在私有目录。`source`、价格缺失、未知缓存版本、未记录的 Skill 调用保留未知。

## 2. 诊断与行动

诊断输出区分观察事实、解释假设、建议动作、验证指标与证据范围。默认阈值只用于选取检查对象。根据用户目标排序少量重要发现，再阅读相关会话与任务；不要把自动检测结果当最终裁决。

- 上下文增长或历史占比高：结合缓存命中、任务进展及压缩检查，比较有界读取、阶段交接或新会话的总成本。
- 工具定义或结果较重：核任务需要的工具，减少明确无关的定义或重复/过长输出，保留能力和证据。
- 重试/排队较多：核共享账号总并发、队列、冷却与回退，不以多建组扩大容量。
- 复杂度与模型可能不匹配：必须结合任务验收与返工，不能凭短回复、低 Token 或工具次数决定降级。
- 协作往返多：先核输入、任务边界和交接，不凭消息工具占比否定协作。

网关可控制对应路由的请求；原生直连调用另列，不能声称改组就覆盖所有 Agent。已有 Magpie 调优或历史回放只作候选输入；其成本假设不能替代实际任务质量验证。

## 3. 资源安排与配置执行

先读 `config/profile.local.json` 与实际组配置：沿用户在私有画像或当次授权中确认的边界，不据组名或架构偏好判断配置错误，也不强制迁移。维护通用 `smart-split` 时按任务意图分流，角色专用模型仅作可选增强。

从已有任务中匹配必要能力、期限、保密要求、套餐多窗口、临期积分与并发；保留缓存及返工机会成本。输出“现在适合做／建议稍后／等待输入”，附原因。按真实库存规划重置卡，不预支固定发卡数量。账号切换、用卡、业务派发和持续监控由各自专用工具处理，沿当前授权执行；诊断不隐含这些动作。

新建组继续用 `magpie_route.py plan/apply`；已有组使用 `magpie_change.py plan/apply`，支持成员、路由、会话保持和追加有限条件规则。恢复使用已保存前态生成恢复计划。具体命令和 schema 见[操作入口](references/operations.md)。

<!-- skill-lint:constraint MO-CHANGE -->
先固定具名对象、允许字段和可读计划，绑定内容哈希、配置哈希、CLI版本及15分钟有效期。逐条通过原生CLI写入并回读目标与无关配置。发现漂移或部分失败即停，保留状态，不自动重放或整文件恢复。自有锁不能阻止GUI或其他writer，因此保持单一配置操作者；不宣称跨进程原子性。

已有明确实施授权则直接推进；仅请求诊断/规划时交付方案。新组同名替换必须拒绝。恢复前核该组仍与本次后态一致，保留他人修改。`CONFIG_READBACK_VERIFIED` 只证明配置落盘，另在授权内用代表性请求核实际 served model、工具回合与客户端生效。

## 4. 效果与资产

使用用户现有任务源作为权威记录，将一个或多个会话显式关联到任务，指向产物与验收，不按标题猜测任务完成。不新造竞争性任务库。模板和复核方法见[效果比较](references/outcomes.md)。

<!-- skill-lint:constraint MO-OUTCOME -->
效果复核必须检查实际产物文件、验收绑定的哈希、完整观测及会话归属；禁止重复分摊同一请求。只有同类任务 before/after 都具备质量通过证据时，才给出每份验收成果的描述性消耗比较。缺样本、未验收、产物变化或价格未知均保留缺口，不自动写“节省”或因果收益。

工具仅核验收文件与实际产物的一致性，任务可比性和语义质量仍由具名评审负责。没有 before/after 时，可先建立基线。把有效结论写入现有个人经验/任务记录，附适用任务、模型版本、观察窗口和重新评估条件，避免把一次结果固定为全局偏好。

## 交付与验证

交付当前事实、主要发现、具名建议、已执行变化、验证结果和待观测效果。私人读数、配置和案例落在 Skill 目录内的 `config/*.local.json` 与 `state/` 私有层，不进版本库；输出文件0600。按[验证说明](references/verification.md)运行真实CLI隔离测试、分页/隐私/漂移/产物变更反例。多轮Agent稳定性与实际优化收益单独说明，不以测试通过替代。

### 发布前门禁

```sh
python3 <skill-dir>/scripts/public_release_check.py check --root <skill-dir>/..
```

只读扫描待发布目录树，核对私密数据、示例与 schema、Markdown 链接、私有层覆盖与版本漂移；发现任一问题即非零退出，发布以退出码为准。逐项清单见[隐私与公开边界](references/privacy.md)。

## 依赖

### 系统依赖

| 依赖 | 用途与安装 |
|---|---|
| Python 3.10+ | 全部脚本只用标准库，无需 pip；使用本机已有Python，缺失时提示安装 |
| 已安装 Magpie CLI 与本机网关 | 采集/配置；沿用官方应用已有安装和登录，不自动下载或升级 |

采集只请求本机只读接口；CLI可能初始化已安装插件运行时。配置apply会写网关设置并可能同步客户端模型目录；效果复核只读用户具名产物和验收文件。运行时不自动执行模型任务、付费请求、账号切换、耗卡或后台任务。
