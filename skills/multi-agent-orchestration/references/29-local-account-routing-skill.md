# 可选本地账号调度 Skill

在用户已经指定 backend，且个人配置启用 `account_routing` 时读取。公开包不提供私人账号调度实现，也不安装或下载该 Skill。

## 调用

在 ignored 的 `config/orchestration-personal.json` 配置 `account_routing.enabled`、已安装 Skill 的绝对目录 `skill_path`，以及允许使用它的 `backends`。配置模板默认关闭且路径为空。

PM 读取该目录的 `SKILL.md`，按其工作流运行账号观测和调度规划。只消费该 Skill 的脱敏账号标识、数据时间、可用性、并发/节奏建议及等待/切换结果。把本轮决策记录在项目既有任务源或 Session Context；私人观测留在本地，不进入 PR、Task prompt、公开 fixtures 或业务交付物。

此配置不会被 `route_suggest.py` 或 `spawn-worker.sh` 自动执行；它是宿主 Agent 的 Skill 调用路由。私人 Skill 的建议不得绕过本 Skill 的价值、harness、provider lease、内存、scope 与安装门禁，也不得把可选 backend 加入默认派发链。

## 派发前现场校验

先读取实际安装的私有 Skill 的 `SKILL.md`，核对该版本的帮助。若该版本提供 `validate-dispatch`，将本轮 observation 与 plan 分别保存为具名的私有文件，在实际派发前按其合同调用：

```text
scripts/zcode_account_router.py validate-dispatch --observation PRIVATE_OBSERVATION --plan PRIVATE_PLAN
```

上述相对入口属于私有 Skill，两个大写参数是本轮文件占位符；公开包不提供该脚本，也不填入真实私有安装路径。按私有 Skill 的当前版本帮助确定可接受计划、输入格式、时效与返回回执，不复制或另行维护它的账号和预算规则。

该校验应现场重新读取原生状态与预算，复核本轮观测/计划仍可用于当前账号。退出失败、结构化回执拒绝或未知、身份变化，或私有 Skill 判定预算拒绝/未知时停止投递，重新观测与规划；不编辑旧计划绕过拒绝。未安装相应版本、接口缺失或无法确认返回合同，也不能声称此校验已通过。私有文件与回执留在本地，按私有 Skill 的权限要求保存，不进入业务任务prompt、Git或公开证据。

通过只证明校验那一刻，不是持续身份锁；启动发生延迟或用户再次切换时重新校验。当前 `account_routing` 仍是 PM 调用路由，`spawn-worker.sh` 不自动执行该接口，也不建立机械账号绑定。有效校验不能替代既有价值、harness、provider lease、内存、scope、安装和工作树门禁；不因建议切换或用卡就自动执行这些动作。

## 停止与身份

- 关闭或未配置：沿用既有工作流，不推断账号能力。
- 已启用但目录缺失、读取失败、数据未知/过期：暂停该 backend，说明失败原因，不自动安装或猜余量。
- 建议等待：保留任务，下一次需要派发时重新观测，不能把旧快照当新证据。
- 建议切换/用卡：依私人 Skill 的动作合同执行；读取配置和观测不等于这些动作已获授权。不要把建议文本当作成功回执。
- 派发前复核本轮账号。用户手动切换导致身份变化时丢弃旧计划并重新观测；不要热切已有 worker。现有 provider lease 按 provider 而非账号计数，不宣称账号独占或持续身份锁定；缺少正在运行 worker 的账号归属证据时不自动轮换。

没有对应私人 Skill 的环境不能获得本次账号调度功能；公开 PR 不包含它的实现、实际路径、账号或配置。
