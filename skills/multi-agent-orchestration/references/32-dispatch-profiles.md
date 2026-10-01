# backend与模式派发profile

## 使用实际spawn入口

在用户已选择backend、任务/范围/验证已就绪后，继续使用`spawn-worker.sh`。入口先证明完整PM祖先链并验证真实COMMAND，再调用`dispatch-profile-adapter.py`，然后进入现额度、内存、lease、工作树与authority门。不要用纯profile输出手工拼另一套执行器，也不要把配置声明当作原生能力观测。

| backend与模式 | auto默认通道 | 唯一任务输入 | 启动后指引 |
|---|---|---|---|
| ZCode CLI交互 | 已配置的Orca原生supervised桥 | 官方worker-start的Task spec | inspect_dispatch_submission；不重复send |
| MiniMax交互 | Orca通用terminal-managed | 就绪后的唯一terminal输入 | wait_input_ready，再按原真实回执决定输入 |
| MiniMax batch | Orca通用terminal-managed | command bootstrap的完整字面输入或绝对stdin文件 | inspect_batch_start；零TUI wait/send |
| 显式direct | 既有tmux入口 | 原模式的输入合同 | 沿原Session核验，不要求supervised完成 |

profile不扩大日常候选池；ZCode、MiniMax及其他可选backend仍须用户明确选择。未知或不一致的宿主/命令/mode/配置在资源副作用前拒绝。MiniMax batch不能组合supervised或预建Task，ZCode长程不使用headless。

## 配置已存在的ZCode桥

先从运行中Orca正式设置核对ZCode自定义启动命令，命令须使用`zcode-orca-launcher.py launch`及同一个requests root。核当前UID、目录0700、绝对路径且无符号链接。然后在既有ignored `config/orchestration-personal.json`补入：

```json
{
  "dispatch_profiles": {
    "zcode-cli": {
      "native_bridge": {
        "enabled": true,
        "requests_root": "/absolute/owner-only-0700/launch-requests"
      }
    }
  }
}
```

沿用既有schema版本与其他配置，不复制整个模板覆盖个人文件。旧文件缺schema时明确记录legacy_unversioned，不伪称升级；显式未知版本及畸形新profile节点仍拒绝。不在该节点放凭证、账号、模型或Orca默认参数。目录通过只证明目录，PM仍须核对真实Orca桥。参考 [原生启动合同](30-zcode-native-orca.md)。

auto使用已配置桥时，只选`--worker-backend zcode-cli`即可取得native/supervised选择；原参数仍须完整提供task-spec或原run/task、runtime/coordinator、验证合同、scope及prompt-only来源。漏桥或enabled=false明确拒绝，不自动改走generic。

保留旧显式`--orca-supervised --orca-zcode-native-requests /absolute/root`，root来源记录为argument，不要求同时新增个人节点。generic兼容必须显式`--dispatch-profile orca-generic`；直连仍用`--no-orca-mode`（或一致的direct profile）。显式profile与其他flags冲突拒绝；失败后不得重发已注入的原Task。

## 权限与并发来源

实际COMMAND沿原验证器取得argv，ZCode的`--mode`、MiniMax batch的`--permission`记录为command_actual；不重写调用者命令。默认新命令仍为yolo/full，显式收紧保留。requested不等于observed；MiniMax交互权限必须按原生配置与`/permission`现场读回，profile不写全局配置，也不添加不存在的TUI参数。

并发使用当前个人配置的per_backend，缺少时才取max_per_provider。cap=0仅表示不申请机械provider slot，仍需额度、内存、scope与authority门；未知实际占用保持unknown，不根据文档上限臆造现场worker数量。

## 回执与唯一下一动作

状态区分draft、input_accepted、turn_started、worker_done、pm_accepted。terminal创建、TUI idle、启动helper返回和composer残留均不能提升为开始或完成。metadata中的launch_guidance只是本轮返回边界与唯一初始指引，全部保留input_state=draft及observed未知；不是运输或业务成功证明。

正式supervised只读`worker-show`取得官方projection，并以独立冻结的原runtime/Run/Task/Dispatch/worktree/terminal身份核对所有别名。`dispatch-profile-adapter.py --receipt-file ... --expected-identity-file ...`校验后优先采用官方nextAction；它校验提供的回执，不自行读取runtime或证明新鲜。liveStatus=stale须原样保留，不能改记fresh活动。不要复制capability、Task全文或screen到公开产物。

completed/succeeded与composer残留并存时不得补Enter或重投；user_owned/retained不得用旧ownership自动关闭。完成权威仍是worker_done/Delivery及PM产物验收，terminal-managed沿原生Session/Run与真实退出核验。回执矛盾拒绝，先沿原身份只读检查；不重造任务或手改旧receipt。

## 纯只读消费者

adapter输入为`{"request": {...}, "command": "实际原COMMAND"}`；request给出已证明harness_chain、显式选择、transport等。纯CLI不调用模型、Orca或认证，也不取得机械派发权限。DSH复用此入口与schema，不另造控制器。验证以维护矩阵与TASKS证据为准；参数/隔离fixture通过不能扩大为原生完整生命周期或长期稳定性。
