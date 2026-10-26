# 子 Agent 模型指定（Codex / DSH）

适用参考版本：Magpie 0.1.1307、codex-cli 0.163.0-alpha.10.2、`@deepseek-ai/dsh-subagent` 0.2.0-rc.1。先核安装版再套用。网关只看请求携带的模型名，不区分主/子 Agent 角色（`agents=` 规则按客户端匹配）；持久配置由各客户端管理，按任务意图的自动分流仍走 [smart-split](smart-split.md)。

## Codex

三条优先级，从高到低：

1. 单 agent 持久指定：`~/.codex/agents/<name>.toml` 顶层 `model`、`model_reasoning_effort` 字段。本条不包含 lead 在 spawn 时传入的模型参数；该参数的实测边界见下方修正。
2. 统一默认：`magpie codex subagent_model <模型>` / `magpie codex subagent_effort <档>`，实际写入 `~/.codex/config.toml` 的 `[agents] default_subagent_model` / `default_subagent_reasoning_effort`（Codex 官方 config 键；magpie 的 codex 字段表即含 subagent/subagent_model/subagent_effort）。键名带 default，即兜底语义，会被第 1 条覆盖。
3. 都没设：继承主会话 `model`。

> **运行时核验**：lead 在 spawn 时传入的模型参数不能单独证明实际落点。须在授权日志的有界样本中核对请求指名、统一默认、`subagent.to`、`subagent.kept` 与最终 served；计数和观察窗口仅保存在私有 `state/`。裸 `req == served` 会混入组展开和 provider 前缀差异，诊断口径见 [subagent-override.md](subagent-override.md)。
>
> 另注：**子代理不会因为主会话使用意图入口而自动继承同一规则**。若需要子代理走意图入口，`default_subagent_model` 必须直接指向该入口，并另行验证 spawn 请求是否命中规则。

边界与坑：

- 模型名必须在 `magpie models codex` 可见列表内（Agents 页面 tick 控制，`magpie visible codex …` 调整；具体可用形态以本机实读为准，可能是具体模型 ID 或 `group/<vendor-model>` 组）。
- ChatGPT backend 任务封印：lead 跑在 Codex 自家模型（backend-api/codex 端点）时 spawn 的任务消息会被 backend 封印，只有 ChatGPT 账号的模型能读。subagent 统一切到非 backend 模型是受支持用法，但不要在会话中途于自家/非自家模型间来回切换或嵌套切换；遇封印报错，让一个不在自家模型上的 agent 重新 spawn（`fork_turns="none"` 不解封）。
- effort 同链覆盖；所设档位仍受模型实际支持档位与路由组固定成员 effort 约束。
- magpie 官方语义：统一 subagent model 的用途是把所有子 agent 拉齐到一个（"hold every subagent to one"），单个指名即视为有意偏离。

## DSH

magpie 对 dsh 只有 `model`、`effort` 两个字段（主会话），无 subagent 专用字段。子 Agent 模型三层：

1. 请求级：`request.agentOptions`（provider / model / reasoningEffort / maxTokens），由委托发起方在工具调用时传入，盖一切默认；每项都要求后端具备对应 capability，缺失则启动即失败。
2. 配置级：`~/.dsh/profiles/<web|desktop|next>/` 的 patch 层中 `dsh-tool-subagent` 条目 `config.agentOptions`（同四字段）——该工具行全部子 agent 的固定默认，覆盖 provider 自带路由默认；要求后端支持 agentOptions。
3. 默认：继承父 Agent 的 provider / model / reasoningEffort / 输出上限（in-process spawn/fork 后端）。因此 `magpie dsh <model>` 改主模型即主带子一起变，是 DSH 的"统一配置"路径。

补充：

- 设置页 Plugins → Subagent 分域只管 `maxDepth`（默认 1）与 `maxActiveSubagents`（默认 8），不涉及模型。
- 子 agent 后端可组合 in-process（spawn/fork）、ACP、SDK、Codex、Claude Code；外部后端的模型由该后端自身配置管理，不进上述继承链。
- `modelSelectionSettings` 采样 Host 的 exact-route 授权偏好，属授权观察，不是模型指定。

## 验证

任一入口改动后按 [cli-contract](cli-contract.md) 口径先回读配置；`CONFIG_READBACK_VERIFIED` 只证明落盘，需在授权内发代表性请求核实际 served model，`magpie usage today` 可见落点成员。
