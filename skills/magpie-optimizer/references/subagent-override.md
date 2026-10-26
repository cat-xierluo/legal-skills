# 子 Agent 指名覆盖与统一默认

## 结论

`spawn_agent(model=...)` 的模型参数不能单独证明实际服务模型。诊断普通 spawn 请求时，
核对 `subagent.to` 是否指向统一默认组；遇 ChatGPT backend 封印路径时，另核
`subagent.kept` 与实际出口。行为取决于宿主、安装版和配置，需逐项验证。

`~/.codex/agents/<name>.toml` 仍是值得优先尝试的持久指定入口，但本页没有对它做运行时
复测；不要把「agent TOML 可指定」和「spawn 参数可靠」混为同一层结论。

## 统计口径

不能用裸的 `req == served` 证明「指名被改写」。它至少混合三类请求：

1. `req` 是 `group/*`：这是组展开，服务成员与组名不同是正常结果，不是 override。
2. `req` 是具体模型且服务模型不同：才是本页关注的指名不一致。
3. `req` 与 `served` 的字符串形态不同但最后一段模型名相同：只是 provider 前缀/别名差异，
   不能计为失败。

因此，本页只统计「具体模型指名」中「归一化后模型名仍不一致」的行：
`req.split('/')[-1].lower() != str(served).lower()`。`usage.jsonl` 是追加中的活文件，
计数必须绑定读取截止时间。`served=None` 的错误响应也按「未按指名获得服务」计入；如需服务成功率，应另行剔除并按状态码分层。

## 观测方法与证据边界

既有排障样本曾出现普通 spawn 请求被统一默认组接管，以及带 `subagent.kept` 的
backend 封印例外。这是特定宿主与安装版的观察线索；公开参考不保留维护者的调用量、
比例、个人组名或读取时刻，也不能据此预测其他使用者的落点。

在当前用户已授权的日志范围内，分别核对请求指名、客户端默认、`subagent.to`、
`subagent.kept` 和最终 served，保留版本及读取截止时间到私有 `state/`。没有原始日志
时不重建历史比例；缺失字段记未知。升级宿主后重新验证，不将旧样本视为永久合同。

## 配置与落点核对

Codex 的实际请求侧配置在 `~/.codex/config.toml` 的
`[agents] default_subagent_model`；Magpie 的 `settings.codexSubagentModel` 与
`applied.json` 是应用侧保存/应用记录。三处值需要在同一配置窗口核对；
一致仅证明当前配置读数一致，实际落点仍须请求证据。无原始快照的历史差异标记
`NOT_VERIFIED`。

诊断时同时核对：

1. Codex 配置的统一默认与 effort。
2. Magpie settings/applied 的保存值。
3. 当日 routing log 的 `subagent.asked`、`subagent.to`、`subagent.kept`。
4. usage 的 `req`、`provider`、`served` 与状态。

不以 UI 显示值、任务卡里的「模型 = X」或 worker 自报代替上述回执。

## 意图分流

子代理不会因为主会话使用某个意图入口而自动获得同一规则。若统一默认指向普通顺序组，
spawn 请求就按该组的成员与回退执行；若要子代理走意图入口，必须把
`default_subagent_model` 直接指向该入口，并验证 `collab_spawn` 请求是否携带可分类文本、
是否命中 `rule`，不能用「主入口是 smart-split」推断子代理也会分层。

## 归因与限流边界

- 429/503 首先按 provider 与错误体聚类；`providerAccount`/`host` 为空时，只能归因到
  provider 出口，不能归因到具体账号。
- 成员可用性必须当日复核；不要沿用前一天的额度、并发或账号状态。
- 对具体模型敏感的任务，派发卡不得只写「模型 = X」。应要求 agent TOML/全局默认与
  实际 served 回执同时可核对；若无法核对，明确标 `NOT_VERIFIED`。
- 遇 429/503 不要无限重试：停止继续派发、保留错误窗口并回报，由配置 owner 决定降级、
  错峰或修复。
