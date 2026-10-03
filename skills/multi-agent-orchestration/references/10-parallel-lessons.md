# 并发任务排障索引

遇到具体异常时读取本页。日常流程以 [SKILL.md](../SKILL.md) 为准；下列入口复用当前合同，历史项目事故、旧版本参数和性能记录留在维护任务/本地归档。

## 1. 先确定卡在哪一层

| 现象 | 先读事实 | 操作权威 |
|---|---|---|
| backend/宿主被拒 | 实际PM祖先链、policy与本轮选择 | [06 CLI路由](06-agent-cli-reference.md)、[26按需backend](26-optional-cli-backends.md) |
| consumer_fenced / 协调身份拒绝 | 原run-use/create回执、coordinator handle及本轮consumer | [14 PM控制](14-pm-orchestrate.md)，保留原Run/Task，不重建Run逃避fencing |
| spawn失败但已有工作树/终端 | 正式回执、精确资源归属、输入是否已消费 | [13 Orca worker](13-orca-cli-worker.md)、[31借用边界](31-borrowed-existing-worktree.md) |
| 原生CLI就绪未知 | 实际进程、composer及匹配入口的就绪证据 | [32 profile](32-dispatch-profiles.md)；ZCode原生另读[30](30-zcode-native-orca.md) |
| 命令accepted但未工作 | 原输入/原生会话是否消费、实际活动与产物 | [14 PM控制](14-pm-orchestrate.md)、[33接续](33-pm-continuation-readiness.md) |
| 权限/登录/信任等待 | 精确请求、命令、身份与新鲜screen | [02授权边界](02-runtime-dependencies.md)、对应backend操作页 |
| 模型或provider不符 | 实际请求证据与选定配置 | [06](06-agent-cli-reference.md)、ZCode的[28](28-zcode-cli-bigmodel-coding-plan.md) |
| 429、空闲或预算拒绝 | 新鲜额度/压力、原native活动及pending输入 | [20限流](20-orca-rate-limit-recovery.md)、[22内存](22-mem-budget-lane.md) |
| worker完成后PM不接续 | 原PM、正式监测配置/触发、是否人工唤醒 | [33](33-pm-continuation-readiness.md)、[15波次](15-wave-autopilot.md) |
| STATUS done但不能结算 | 真实产物、Task/Dispatch、Delivery、lease/资源 | [18验收](18-dispatch-acceptance-contracts.md)、[23结算](23-runtime-settlement.md) |
| 主CLI退出仍有负载 | 本轮归属清单、后代/额外shell/端口与保留理由 | [37资源收尾](37-worker-resource-closeout.md) |

失败与未知都保留原件。先确认发生了什么，再消费原合同允许的恢复动作；不因一条失败退出码重新派发已经工作的任务。

## 2. Agent Teams与消息

官方Teams配置/inbox与本Skill的Session Context不是同一状态源。成员创建、收件、上下文不足等问题读取 [11 Teams排障](11-agent-teams-troubleshooting.md)；不要以项目内自建同名目录冒充官方团队状态。

### T1. tmux输入未提交

在已经选定tmux回退的原会话核当前输入状态，区分文本输入与提交键，观察实际消费。按键不能保证原生业务开始；不固定重复Enter、attach占住PM或把文本发送给退回的shell。

### T2. 输入法或终端键处理

确认目标窗口/终端、输入法和CLI当前状态后再处理原输入。优先正式CLI控制接口；不要把本机一次键盘修复写成其他backend通用配方。

### T6. spawn worker撞项目MCP选择dialog

先核任务是否需要MCP。Claude路线的`--no-mcp`是显式选择；CodeBuddy默认strict空MCP、需工具时`--with-mcp`。通过现有renderer生成，见 [06](06-agent-cli-reference.md) / [08](08-codebuddy-cli-worker.md)。不以`--bare`、盲Escape或删全局hooks规避正式门。

本小节继续承接`claude-provider-env.sh`和spawn注释中的T6旧指路；当前行为以这两份backend指南及实际代码为准。

## 3. 工作树、依赖与基线

### G28. verify用主仓node_modules

先核项目允许的依赖复用方式、实际工作树路径与验证命令。主仓存在依赖不证明任意Orca工作树可以解析到它；也不意味着worker可自动安装。使用 [02依赖合同](02-runtime-dependencies.md) 的实际入口，保留复用/缺失证据。

### G31. Orca工作树脱离主仓父链

工作树位于另一根目录时，Node向父目录解析依赖的结果可能不同。核真实cwd与解析路径，按项目合同选择依赖复用或获授权安装；不要为解决验证失败把任务移回主仓或扩大写范围。G28/G31保留供`spawn-worker-deps.sh`旧注释定位。

### 分支、HEAD与重复创建

比较任务变更时先核冻结起点/实际基线，再检查与最新主干的关系；按项目Git规则集成，不照搬历史直接merge处方。occupied分支/工作树按正式借用或恢复合同处理，不加后缀重建来解除拒绝。

工作树实际目录/分支/HEAD应在任务注入前通过正式隔离门。已有partial-create残留先核所有权及原输入消费，再按原任务恢复；仅创建资源成功不等于worker-start成功。

## 4. 纠偏、权限与验收

- worker偏题时先把具名问题、证据与范围交回原任务，在允许预算内纠偏；PM接管需符合现有例外，不因难审直接代写业务。
- 多维任务逐项定义验收，独立审查覆盖实际约束；按文件域/依赖拆解，参考 [12任务分组](12-issue-grouping.md) 与 [18验收](18-dispatch-acceptance-contracts.md)。不靠增加worker数量代替任务定义。
- provider并发按当前配额、lease和内存合同，不将历史“三四个”的经验变成所有backend的上限或豁免。
- 授权回执、launch和能力身份由正式入口绑定；修改旁路配置不能追认原worker权限。恢复读取 [14](14-pm-orchestrate.md)，不能手改receipt或重置Task身份。
- STATUS/检查点帮助巡检，完成与释放按实际模式的权威来源验收；读取 [03 checkpoint](03-checkpoint-files.md) 与 [23](23-runtime-settlement.md)。

### G41. Reviewer证据预算

先看固定产物/head、diff与受影响合同；同一证据不反复全文重读。验证失败按事实分类，有理由才复跑，保留首次失败。预算耗尽写明确剩余和下一动作，不变成放宽验收，也不自动重派同题；具体规则以 [18](18-dispatch-acceptance-contracts.md) 和原任务预算为准。

## 5. 历史记录与维护

旧G编号中的项目复盘、未支持CLI、价格/速度比较、通用Git/测试教材不再作为运行正文。维护任务保存原文归档与章节去向；当前规则已在权威指南存在时只保留路由，不复制第二套。

新增排障项至少包含可观察症状、最小事实、合法下一步和权威入口。一次事故的时间、提交、测试计数、失败过程与待实现修复写回原TASK；真实取舍写DECISIONS。只把经过核实且可重复使用的操作知识放入本页。
