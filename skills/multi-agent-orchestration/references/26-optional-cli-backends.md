# 按需 CLI backend

## 选择合同

重点支持独立 ZCode CLI 和独立 MiniMax Code CLI。保留 CodeBuddy，新增独立 Qoder CN CLI 与千问办公入口。所有这些 backend 只在用户明确指定时选用，不进入日常 Claude Code/Codex worker 池，也不因余额/额度不足自动回退。支持集合以 `config/harness-backend-policy.json` 的 hosts 为机械权限权威，dispatch_selection 说明选择规则。

| 产品 | backend | CLI | 配置与权限 | 验证状态 |
|---|---|---|---|---|
| 独立 ZCode CLI | `zcode-cli` | `zcode` TUI / `--prompt` | 原生会话配置；默认 `build`，`edit/yolo` 须显式选择 | help/argv、原生模型切换/短请求与个人 Coding Plan 的 tmux 文件任务已核对（独立验收 `ACCEPT`）；1.4.218 起显式 native supervised 增量见 [原生 Orca 合同](30-zcode-native-orca.md)，验收以当前 TASKS 为准 |
| 独立 MiniMax Code | `minimax-code`（`mcode` 别名） | `mcode` TUI / `mcode exec` | 原生 Session/Run 模型；exec 默认 `smart` | help/argv 与真实 Orca terminal-managed 文件任务已独立验收；实际 minimax / MiniMax-M3.1-Flash-Preview；supervised/settlement `NOT_VERIFIED` |
| CodeBuddy | `codebuddy` | `codebuddy` | 沿用既有 settings/hook 集成 | 本次保留；未重测 live 生命周期 |
| 独立 Qoder CN | `qoder-cn`（`qoderclicn` 别名） | 独立安装的 `qoderclicn` | 原生 auto；不继承旧 QoderWork 模型表或 hook 保证 | 官方参数/隔离 argv 已核对；本机独立入口未安装、live `NOT_VERIFIED` |
| 千问办公 | `qwenwork-cn` | 指定 bundle 的 `qoderclicn`；原生工具是 `qwenwork` | 需显式独立 config-dir；见 ref 27 | help 已核对；账号/provider `NOT_VERIFIED` |
| 旧 ZCode driver | `zcode` | Skill app-server driver | 仍要求私有 `--settings`，且目标 runtime 必须接受隔离参数 | 沿用 ref 24，不作为独立 CLI 默认入口 |

## 启动配方

先检查本地已安装 CLI，不自动安装、登录、复制凭证或改全局默认模型：

```bash
bash scripts/check-dependencies.sh --backend zcode-cli --backend minimax-code
zcode --help
mcode --help
mcode exec --help
```

渲染交互式命令（便于持续巡检和纠偏）：

```bash
bash scripts/render-runtime-profile.sh --backend zcode-cli --output shell
bash scripts/render-runtime-profile.sh --backend minimax-code --output shell
bash scripts/render-runtime-profile.sh --backend qoder-cn --bin /absolute/path/qoderclicn --output shell
```

自包含短任务可渲染 batch（原任务仍须通过完整价值/验证合同）：

```bash
bash scripts/render-runtime-profile.sh --backend zcode-cli --mode batch \
  --permission-mode edit --prompt-file /absolute/path/task.md --output shell
bash scripts/render-runtime-profile.sh --backend minimax-code --mode batch \
  --model '<provider/model>' --prompt-file /absolute/path/task.md --output shell
```

显式选择 `minimax-code`（含 `mcode` 别名）后，`spawn-worker.sh` 默认要求匹配当前项目的 Orca 通道。Orca 缺失、不可达、注册失败、错仓或 lightweight 模式在工作树、provider lease、Session Context、终端与任务创建前失败；不要因失败另起直连。用户明确选择直连时传 `--no-orca-mode`，无需工作树时再加 `--no-worktree`。此默认只决定已选 MiniMax 的管理通道，不改变可选 backend 池。Orca terminal-managed 可见终端、工作树和分支，但没有 supervised Task/Dispatch，也不要求 `worker_done`。

MiniMax batch 使用 `exec --permission smart --output-format stream-json --input -`；stdin 原样读取 prompt。交互模式仅 `-m` 覆盖当前 Session，不能传 headless 的 `--permission`。ZCode 启动帮助未提供 `--model`，renderer 在传模型时拒绝，不能静默忽略或改共享配置；按原生 `/model list` 与 `/model <provider/model>` 明确选择；BigModel 套餐认证、reasoning 必填与静默回落风险读取 [独立 CLI 的 BigModel 实测](28-zcode-cli-bigmodel-coding-plan.md)。ZCode renderer 显式默认 `--mode build`，避免 CLI `--prompt` 的原生 yolo 默认隐式扩大权限。

用渲染后的 WORKER_COMMAND 交给 `spawn-worker.sh --worker-backend ... --command ...`；ZCode CLI、MiniMax Code、Qoder CN 尚无本 Skill 已配置的 PreToolUse 集成，必须显式传 `--allow-prompt-only-install-guard '<授权来源>'`。本次增加支持不授权实际派发、安装、push/PR 或 bypass 模式；按真实任务授权运行。不要自动应答未验证 CLI 的 trust/permission dialog。

## 身份与失败边界

- 移除 QoderWork：旧 backend/别名拒绝；命令实路径含 QoderWork 的软链也拒绝。只改 backend 标签不能把旧产品伪装成新产品。
- 同名 qoderclicn：千问 bundle 只认 `qwenwork-cn`；独立 Qoder CN 只认 `qoder-cn`。千问 bundle 的配置目录必须显式提供且存在，不能从产品同源推断账号/额度共享。
- 默认路由：route_suggest 自动 provider 补选仍只处理 Claude Code，新可选 backend 不加入 tier_policy。
- ZCode CLI 的显式 native Orca 路径读取 [原生启动合同](30-zcode-native-orca.md)；MiniMax 默认 Orca terminal-managed，显式直连用 `--no-orca-mode`；其余新 backend 优先 terminal-managed/tmux。仅帮助和隔离 stub argv 通过不证明真实模型写文件、持续交互、hook 或 supervised 成功；真实 `worker_done → Delivery → settlement → ack` 缺失则 `NOT_VERIFIED`。

## 2026-10-01 有界文件任务验收

MiniMax Code 的实际 Orca terminal-managed 任务已独立 `ACCEPT`：产物提交 `5461cc089956c078dccb53f79f69de471f07aa68`，PM 执行3项测试通过，STATUS 为 done，postflight 通过，工作树干净、终端关闭。同一原生会话的15条 assistant 响应元数据与15条 `llm_response_identifiers`（HTTP200）都精确绑定本次任务，provider/model 为 `minimax / MiniMax-M3.1-Flash-Preview`；这是实际响应记录，不只依赖启动 `-m` 或模型自述。

ZCode 的 tmux fallback 文件任务产物提交 `08230b664fcaee9e6a2ee5f3257ec977073ffc9d`：3项测试通过，仅修改 probe 任务文件；SQLite 记录13条 completed `model_usage`，全部为个人 Coding Plan provider / `GLM-5.3-Flash`，retry 为0。临时研究认证/配置副本已精确删除，tmux 已关闭；独立验收为 `ACCEPT`（限tmux实际任务）。Orca 1.4.217 的两次尝试均遇到 `terminal_handle_stale`，业务 prompt 的 send 次数为0，不能把 tmux 成功写成 Orca 成功。

这两项任务均采用显式 prompt-only 降级；ZCode bootstrap 曾执行超出精确 shell allowlist 的 `ls`，不证明机械 scope/hook。terminal-managed 没有 supervised Task/Dispatch，tmux 也不能替代 `worker_done → Delivery → settlement → ack`。本轮无真实账号切换、耗卡或默认自动身份绑定；共享配置/凭证一致性仅有准备进程内断言，未持久化该次共享 before baseline，独立 before/after 重放仍 `NOT_VERIFIED`。精确服务端扣费归属同样 `NOT_VERIFIED`。证据状态与独立验收以 TASKS 的 LIVE-WORKER-ACCEPTANCE 卡为准。

## 默认Orca渠道的增量验收

2.33.0默认入口另以新的MiniMax交互会话完成文件任务：产物`1f0c1513b09351542e5ce51411922c27b7079d63`仅probe.py，PM3/3与postflight通过；实际16条assistant响应、16条HTTP200事件均为`minimax / MiniMax-M3.1-Flash-Preview`。原生历史与usage按精确session/turn/timestamp/rawusage唯一消费，日志按同session/turn/provider/model核数量组；逐responseId的HTTP直接join与精确计费仍NOT_VERIFIED。测试CLI/launcher及已记录后代退出，默认空shell核后正式close-all，最终终端库存0；long-lived树/分支保留证据。

启动bootstrap可能已消费完整本轮授权合同并开始或完成工作。PM先读精确终端与产物再决定后续输入，已有业务不能再次派发；本次只发送一次现有结果的验收指导。MiniMax的Orca receipt可能仅报告input_accepted且provider unsupported：不重发，不把运输成功当作业务已启动，通过该原生会话及实际结果核消费。terminal-managed仍没有supervised Task/Dispatch/worker_done闭环。

## 依赖与来源

现有依赖之外，只需用户自行安装对应 CLI；Qoder CN 独立安装文档为 [官方安装与升级](https://docs.qoder.cn/cli/installation)，常规 npm 入口是 `@qodercn-ai/qoderclicn`，安装先遵循本机依赖纪律。本 Skill 不执行安装。MiniMax Code 的运行时依赖和安装方式以 [官方仓库](https://github.com/MiniMax-AI/minimax-code) 为准。Qoder 参数以 [官方 CLI 参考](https://docs.qoder.cn/cli/cli-reference) 与运行中 help 为准。

2026-09-30 本机观测：独立 ZCode help 显示 TUI、prompt、mode；MiniMax Code help 与 exec help 显示 Session 模型、stdin 与 permission；旧 QoderWork 的 PATH 软链目标不存在。只记录入口行为，不打印用户配置、凭证或 session 数据。
