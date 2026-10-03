# 原 PM 持续接续：准备检查与人工介入归因

适用：真人要求持续派发、返回后review并继续、不要每轮催促，或任务会超出当前PM活跃回合。一次派发授权不自行扩成长期调度授权；已有真人授权包含持续监测时直接沿用，不为同一范围重复询问。

## 1. 派发前确定执行策略

- `one_wave`：完成本波及其独立验收。PM在当前回合持续读真实进展、消费返回；缺少监测不免除本波责任，也不宣称无人值守。
- `continuous`：在原任务源固定原PM、合法队列、返回后的独审/写回/修复或下一项、暂停条件及监测周期。派发前检查唯一现有正式唤醒；若缺失，在已有授权范围内用宿主正式工具补配置并回读，不能只承诺“稍后设置”。工具确实拒绝时记录原原因，不改用shell定时绕过。
- 原PM目标与宏观总控分开。总控只读汇总且不唤醒原PM时，不能把总控心跳当项目接续；复用已存在监测，不创建第二controller/任务源。
- 新建持续Wave准备不足时保留 `CONTINUATION_NOT_READY`，不得静默改成单波后声称持续运行。已有在途工作继续由原PM观察和验收，不为补监测重发任务、停止writer或重建分支。

## 2. 显式continuous的机械准备门

先填 [持续合同模板](../templates/continuation-contract.example.json)，保存于项目已有控制目录；它是原任务的派发合同，不能成为第二任务队列。所有路径使用canonical绝对路径，授权指针指回原任务源。

Codex heartbeat当前可使用只读入口（Python3.11+标准库，无安装/联网）：

```bash
python3 -B scripts/continuation-readiness.py --contract "$CONTRACT"
```

检查实际已安装 `$CODEX_HOME/automations/<id>/automation.toml`（未设CODEX_HOME则为 `~/.codex`）：精确id、heartbeat、ACTIVE、target_thread_id等于原PM、prompt以空白或引号/Markdown边界引用精确原任务源绝对路径、周期不超过合同上限。后缀备份名、子路径和URL前缀不算原卡绑定。当前周期只支持无额外过滤的MINUTELY/HOURLY；不认识的宿主、规则或缺文件均拒绝，不猜测。

`--automation-root`允许读取明确指定的已安装宿主或隔离fixture；不创建配置，不因此产生调度/业务授权。检查依赖受信宿主配置原件；不是防伪签名，也不验证自然语言prompt的实际执行。

在正式heartbeat prompt中建议写“读取原任务源 `/absolute/path/to/project/TASKS.md` 并沿原卡接续”，将路径置于反引号、引号、括号或空白边界；直接拼成“原任务源：/path”不满足当前保守的绑定语法。

准备supervised Wave时，在原manifest中加入：

```json
{
  "execution_policy": "continuous",
  "continuation_contract": "/absolute/path/to/project-continuation.json"
}
```

`orca-wave-prepare.sh`在任何Orca调用前消费该检查。明确one_wave或旧manifest无字段保持单波兼容；没有机械手段从任意自然语言或绕过此入口的调用推断持续意图。terminal-managed/tmux/subagent由PM在派发前显式运行同一准备门；不能声称这些入口已强制接入。其他宿主正式调度适配继续归Task-067，不用Codex文件fixture冒充真机集成。

退出0只允许报告 `CONFIGURED_NOT_PROVEN_AUTONOMOUS`；暂停、错PM、缺原卡绑定、未知周期/格式等退出64。输出仅包含身份、配置digest、周期及未验边界，不输出完整prompt、凭证或全局设置。

## 3. 监测每次触发后的业务责任

1. 读取原完整卡和精确worker身份。派发回执只证明提交/接受；实际模型/工具、授权工程变化或任务产物才证明已开始。输出时间、spinner、Queue、TUI idle不替代业务进展。
2. 定向读真实状态/Delivery与当前head；没有消息也检查结算。完成后固定真实提交和停止写入状态，由不同执行上下文独审，不能仅核作者自报PASS。
3. 原PM同次写回原Task。通过则冻结该范围并继续具名合法READY；不通过先分类，预算内沿原问题修复。原Session/成果/累计失败保留，runtime必要的新执行attempt不重置业务预算。
4. 单卡额度、身份依赖或预算耗尽只暂停其依赖链，继续其他独立READY；预算耗尽先做一次具名定因和有限重估，不能盲修第三轮，也不能把它当成整个目标完成。无READY时保持低成本等待；全目标完成、真人暂停或明确停止合同成立时才关闭对应监测。

## 4. 证据等级和人工介入

| 事实 | 可声明 | 不能据此声明 |
|---|---|---|
| 真人手动发“继续”、催设置或修复后恢复 | `HUMAN_RESUMED`，记录原真人消息与恢复步骤 | 自动自愈、零人工介入 |
| 正式job ACTIVE且绑定正确 | `CONFIGURED_NOT_PROVEN_AUTONOMOUS` | 已自动触发、业务继续 |
| 正式宿主的一次实际定时触发 | 自动触发事实 | 返回已review、已续派、L3 |
| 无新真人催促的“worker返回→独审→原Task写回→下一合法动作”证据链 | 该次 `AUTOMATIC_CYCLE_OBSERVED` | 长期稳定、退出/重启仍有效 |

在原Task记录 trigger_origin、原PM、job id、原worker/native Session/Dispatch、return→review→writeback→next-action证据及manual_interventions。配置或自然语言自填“自动”不是宿主事件证明；宿主没有来源元数据时写UNKNOWN。历史人工恢复不能被后一次自动触发抹掉。nextRun未由正式工具提供时写NOT_CAPTURED，不由周期算一个时间冒充回执。

会话外持续调度、断线/丢推送恢复和重启仍按 [持久控制面](16-autopilot-durability.md) 的Task-067验收；一次配置准备通过、一次tick均不完成该任务。
