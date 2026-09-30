# Multi-Agent Orchestration Tasks

本文件是本 Skill 的当前维护队列。历史实现细节以 Git、PR 和 `CHANGELOG.md` 为准；不要把已失效的本机绝对路径、terminal、Run、Task、Dispatch 或临时 capability 当作可恢复上下文。

## 状态与领取规则

| 状态 | 含义 | Agent 动作 |
|---|---|---|
| `READY` | 依赖与范围齐全，可领取 | 从最新 `origin/main` 新建短分支和独立 Worktree |
| `IN_PROGRESS` | 已有唯一 owner、候选分支和冻结起点 | 只由当前 owner 推进；其他 Agent 只读观察或独立 review |
| `RESTART_REQUIRED` | 目标仍有效，但旧候选/Worktree/证据已失效 | 先重建合同与基线，不复用旧运行身份 |
| `BLOCKED` | 前置任务未完成 | 不实施，只维护依赖事实 |
| `PARKED` | 等用户授权、外部 owner 或设计决定 | 不自动恢复 |
| `OBSERVE` | 只收集证据，尚未达到立项阈值 | 不修改生产规则 |
| `COMPLETE` | 已由合并提交或其他不可变证据关闭 | 不重复实现 |

领取 `READY` 任务前必须：`git fetch origin`；确认任务未被其他 PR/会话占用；记录 owner、分支、Worktree、base ref 与 immutable start SHA；只修改卡片允许范围；完成后写回 PR、测试和剩余 `NOT_VERIFIED`。任务未明确允许时，不编辑其他 Skill、个人配置或其他会话 Worktree。

## 当前执行顺序与波次

1. 通信能力波次：`ORCA-CROSS-PM-HANDOFF` 从最新 `origin/main` 重建合同并交付。
2. `ORCA-PEER-COMMS` → `ORCA-COMMS-E2E`；两项保持依赖阻塞，不提前实现。

Hermes 专项和 ZCode 专项不插入上述顺序；只有卡片状态转为 `READY` 且 owner 明确后才进入执行队列。

## TASK-2026-10-01-LIVE-WORKER-ACCEPTANCE — 两个 Skill 的实际任务验收

- 状态：`IN_PROGRESS`；Owner：Codex `/root`；来源：用户要求自主推进测试，直至 MAO 与私有账号 Skill 可完成实际任务，并向已授权会话交接。候选文档 owner 为 `/root/optional_cli_review`，不改共享 source。
- 范围：MiniMax Code 与 ZCode CLI 串行执行有界隔离文件任务，PM 实际回读产物、测试、运行时模型与资源收口；私有 Skill 仅重新观测/规划与启动前身份复核。无真实账号切换、耗卡或产品化自动身份绑定；不影响已有 GUI/会话。
- 候选：`fix/mao-orca-terminal-ready`，代码冻结 `0ed048bfb80373a267c62dca38a48d880abde15e`；基线 `41268aaa91e71158cb4551dce8d757038869af0f`。readiness 源码已独立 `ACCEPT`，本卡的后续提交仅追加文档。
- MiniMax：真实 Orca terminal-managed 任务产物 HEAD `5461cc089956c078dccb53f79f69de471f07aa68`；PM 测试3/3，STATUS done、postflight通过、工作树干净、终端关闭；已独立 `ACCEPT`。数据库唯一工作区会话与原生 manifest/catalog/history路径精确一致，两轮任务共15条 assistant 元数据及15条 HTTP200 响应事件全部为 minimax / MiniMax-M3.1-Flash-Preview；15个响应ID，不以argv或自述代替实际模型证据。
- ZCode：tmux fallback 产物 HEAD `08230b664fcaee9e6a2ee5f3257ec977073ffc9d`，PM 测试3/3、仅probe任务文件改变；SQLite 13条 completed model_usage均为 account:bigmodel-individual-coding-plan / GLM-5.3-Flash，retry0。临时研究认证/配置副本已精确删除，tmux关闭；独立产物验收 `PENDING`，待 PM 回报更新，不能预签完成。
- Orca边界：当前1.4.217具备所需能力；两次 ZCode 尝试均 terminal_handle_stale，0业务send。MiniMax terminal-managed 没有 supervised Task/Dispatch；tmux不替代Orca，完整supervised/settlement、持续纠偏仍 `NOT_VERIFIED`。
- 权限/身份边界：均为prompt-only降级；ZCode bootstrap的ls超出精确shell allowlist，机械scope/hook未证明。私有路由和研究副本仅本轮使用；共享原件哈希一致性仅准备进程内断言，该次before baseline未持久化，独立before/after重放 `NOT_VERIFIED`；副本哈希不作替代。逐请求精确服务端计费仍 `NOT_VERIFIED`。
- 脱敏证据：本机 `/tmp/mao-live-acceptance-261001/minimax/tui-model-review/summary.sanitized.json`（SHA256 `87b957aa64cbab0b4272b613c00512141dc7460b7593b60467015617dd116580`）与本轮私有路由的 `prepare-baseline-audit.sanitized.json`；后者由私有Skill任务源管理。原始账号、日志、认证路径和内容不进公开包。
- 剩余：ZCode独立验收与最终文档head复验、safe-push/对应Skill PR、已授权会话交接由PM收口；未经完成证据不关闭本卡。

## TASK-2026-10-01-ORCA-TERMINAL-READY — 投递前严格核对就绪回执

- 状态：`IN_PROGRESS`；Owner：Codex `/root/optional_cli_review`（implementer）；来源：本轮真实 CLI 验收发现 terminal wait 的 rc0 超时会继续投递。
- 冻结基线：`origin/main` / immutable start `41268aaa91e71158cb4551dce8d757038869af0f`；已 fetch；分支 `fix/mao-orca-terminal-ready`，隔离 managed worktree `mao-live-cli-acceptance`。
- 范围：`scripts/spawn-worker-orca.sh`、定向 Orca 测试、mem-budget 测试的一行 wait fixture，以及本卡、CHANGELOG、DECISIONS、ref 13 和版本字段/README MAO索引；不改权限、宿主、provider、metadata 模块或 batch 启动机制。
- 清单：①核对当前 `orca skills get orca-cli` 与 wait help；②严格回执门禁、同 handle 有界重等；③确定性消费者回归；④独立 review 后由 PM 继续真实 CLI 验收。
- 验收：rc0 但 satisfied=false、畸形/错绑回执、命令失败均零 send；明确 ready 仅一次 send；supervised 不发送普通 prompt。两轮等待分别30s/60s，仍不满足则非0退出并输出精确 terminal/worktree，保留资源供先只读核查后恢复。
- 交付版本：v2.31.2；新增 patch 记录，不改已交付 v2.31.1 的历史正文。
- 验证：`bash scripts/test-spawn-worker-orca.sh` 184/184、`bash scripts/test-spawn-worker-launch.sh` 42/42、`python3 scripts/test-mem-budget-probe.py` 58/58；Bash/Python语法与 `git diff --check` 通过。Orca helper 原件 `/tmp/mao-terminal-ready-261001/orca.log`，summary记录定向命令与结果；源码 `0ed048bfb80373a267c62dca38a48d880abde15e` 已独立 `ACCEPT`。真实任务结果与剩余范围见 LIVE-WORKER-ACCEPTANCE 卡，不把定向测试扩大为完整 supervised/settlement证明。

## TASK-2026-10-01-LOCAL-ACCOUNT-SKILL — 私人账号调度调用合同

- 状态：`COMPLETE`（本地调用合同已提交 PR，尚未合并）；Owner：Codex `/root`；用户最新决定：账号额度/刷新卡规则抽为独立私有 Skill；本 Skill 仅调用，不影响日常使用，不公开私人实现。
- 冻结基线：`origin/main` = `6d85291eb3a59d72cf95f9fb0542bd906eb49fbd`；分支 `feat/mao-optional-cli-support`，独立 app-managed worktree。
- 范围：个人配置模板默认关闭的 `account_routing` 与 ref 29、主入口和版本文档；具体实现与实测在私有 Skill 的 TASKS 维护，不复制账号/卡数据到此处。
- 验收：无配置不调用；启用且 backend 用户指定时读取本地 Skill；缺失/失败/未知暂停；不绕过任何现有派发门，不宣称 PM 调用是 spawn 机械账号绑定。
- 清单：调用合同已落地，独立 review 无有证据 P1/P2；私有 Skill 独立实现/安装验证由其任务源闭环；本卡已提交 PR #230（https://github.com/cat-xierluo/legal-skills/pull/230），状态 OPEN/MERGEABLE/CLEAN；未合并。
- 验证：公开包没有账号 adapter/卡实现或真实账号字段；调用配置 JSON、主入口和 ref 29 可达，默认关闭。实际私有 Skill 缺失时只按合同暂停，不能据此宣称 spawn 机械绑定。

## TASK-2026-09-30-ZCODE-BIGMODEL-LIVE — 独立 CLI 模型选择与 Coding Plan 实测

- 状态：`COMPLETE`（本地研究与有界实测交付；不等于完整 worker 验收）；Owner：Codex `/root`；来源：用户要求继续研究与尝试，重点确认默认 MiniMax 的原因及怎样消费 BigModel Coding Plan。
- 范围：读取已安装开源 ZCode runtime 的真实配置/模型/认证契约；只用隔离测试工作区和 Session 选择模型；允许有界短模型探针，禁止把真实凭证写入 Git/公开日志，禁止更改共享默认模型或现有会话。必要适配只在本 Skill 内维护，沿用现有改动。
- 清单：①确认 CLI/v2/provider_config/工作区最近模型的优先级；②定位 BigModel 账号套餐与 API Key 通道及精确 providerId；③回读隔离会话模型后做有界短请求；④检查请求通道/用量与共享配置未变化，补相应回归和文档。
- 验收：使用实际 provider/model 回读与成功请求证明模型切换，不采信模型自述；区分账户个人Coding Plan、体验/闲时与通用余额，不用模拟测试替代套餐消费证据。未拿到服务端扣费来源证据时明确 `NOT_VERIFIED`。
- 清单结果：①新版默认实际是 minimax/MiniMax-M3；已有新版配置时旧 CLI 默认不覆盖，新默认缺 reasoning 会回落 registry 首个模型；②个人套餐 provider 精确为 account:bigmodel-individual-coding-plan，原生独立 CLI 与 app-server 的 account source 不同；③原生 TUI /model list 与 GLM-5.3/Flash 切换通过，GLM-5.3 与 Flash 各一次真实请求 completed；④实际请求接口与同一凭证的有效 Pro 套餐/积分限额已核对，共享 config/credentials 哈希不变，临时认证副本已删除。
- 对照：未修复的原始凭证副本下 TUI 当前为 MiniMax，个人 BigModel 模型不在列表、两次切换未接受，0 推理；隔离副本只补齐既存套餐 secret 对应的缺失 identity 后，可选套餐。app-server 无宿主 accountConfig 时 setModel 被拒绝，无推理。没有改变原件或伪造 entitlement。
- 模型证据：省略 reasoning 的默认 Flash 请求实际为 GLM-5.3（31,263 total tokens）；增加 max 后请求实际为 GLM-5.3-Flash（31,194 total tokens）。SQLite model_usage 的 provider 都是个人 Coding Plan、status completed、retry 0、tool_call_count 0；原生输出为固定探针文本，0 网页/搜索请求。TUI 两次切换有原生精确反馈，0 model_usage，显式 Ctrl-C 退出130；不把退出130算异常完成或推理成功。
- 服务端只读：subscription/list 返回 GLM Coding Pro、VALID；quota 返回 pro 和 CREDIT_LIMIT。模型用量返回 hourly 汇总；credit detail HTTP200 但非可解析 JSON，没有逐请求扣分原件或独占前后差，不声称精确积分归因通过。
- 交付：ref 28 记录原生 /model/provider/认证与 reasoning 合同，ref 26、SKILL 索引、DECISIONS、CHANGELOG、README 已同步。仍拒绝 zcode-cli 的不存在 --model flag，没有新增自动模型注入包装。
- 私有证据：/tmp/zcode-bigmodel-live-260930/summary.sanitized.json、hashes.json、两份 native 输出/SQLite、TUI 记录；原始认证对照 /tmp/zcode-bigmodel-live-original-260930/；原始请求/账户响应不进仓库。脱敏 summary 可复查模型、用量、退出与配置一致性；临时凭证与含密钥的 personal clone 完成后按精确文件删除。
- 收口复验：CLI 隔离 argv 回归 11/11，新增文档本地链接、配置 JSON 与 git diff --check 通过；独立 reviewer 直接复核两份 SQLite、TUI反馈、请求日志和四份配置哈希，最终无剩余有证据P1/P2。ref26曾误把ZCode证据赋给MiniMax行，已纠正并复验；MiniMax真实provider仍未测。脱敏实测summary SHA-256：d30afcb8e2f405dbed976eff283e04b19d727699ecfa9588b5d905bc64bfa21e。
- NOT_VERIFIED：逐请求精确积分扣分；官方 login 的交互登录/原件迁移；worker 自动模型注入、业务文件修改与 scope hook、持续纠偏、完整 Orca supervised/settlement。此次仅关闭用户要求的研究与短实测，不扩大 OPTIONAL-CLI-BACKENDS 的完成线。


## TASK-2026-09-30-OPTIONAL-CLI-BACKENDS — 按需支持 CLI 并保留 CodeBuddy

- 状态：`COMPLETE`（本地支持适配交付；PR #230 已提交、未合并/发布）；优先级：`P1`；Owner：Codex `/root`；来源：用户当前明确指令，优先于旧删除卡。
- 冻结基线：当前共享检出 `main`，起点 `02012092b7d91b2c616c48c6ae028f3a6f4b9022`；仅修改本 Skill 与根 README 的对应索引，不纳入其他既有改动。
- 目标：重点支持独立 ZCode CLI、MiniMax Code CLI；保留 CodeBuddy；删除 QoderWork backend，新增 Qoder CN CLI 与千问办公入口。新增及保留的可选 backend 不进入日常自动派发池。
- 清单：①真实入口与授权边界已核对；②renderer/身份/依赖/启动门禁已接入，旧删除目标已替代；③正反例与维护回归已执行；④版本/README/证据已同步。
- 验收：真实 CLI help 与渲染 argv 一致；QoderWork 明确拒绝；不同产品的同名 qoderclicn 不串绑；无 hook 新 backend 只能显式降级；默认路由不加入可选 backend。新 backend 的真实 provider 与 Orca supervised 生命周期未测时标记 `NOT_VERIFIED`。
- 设计边界：七层合同沿用既有派发/交付/验收门禁；新增薄 CLI 适配层与独立命令/策略验证，不改结算协议。逃逸反例：旧 QoderWork 软链冒充 Qoder CN、千问 bundled CLI 冒充 Qoder CN、模型选项静默忽略，均须拒绝。


- 交付：v2.31.0；新入口说明在 references/26、27。保留 CodeBuddy，移除 QoderWork 的可派 backend/旧别名与 ungated helper 启动能力；保留旧链接迁移说明及历史记录。
- 本地验证（2026-09-30）：新增实际 argv consumer 11/11；worker command policy 23/23；harness policy 36/36；frame/production policy 23通过、1环境探针跳过；reviewer scope 44/44。完整 references/19 矩阵60条：57条验证通过，smoke-sentinel/smoke-tmux 因 sandbox 不允许隔离socket跳过，smoke-orca-worker 因缺 terminal.multiplex.v1 capability 返回77跳过。最后策略/scope改动另复跑上述受影响套件，Python/Bash语法、JSON、引用与 git diff --check 通过。
- PR 工作树复验（2026-10-01）：references/19 全部60条已运行，初轮58条退出0、2项失败；定位为环境探针误判及重复 fixture 截空，同轮修复后这两项与新增11项 argv consumer 复跑均通过。隔离 tmux worker 真实 socket smoke 通过，Hermes 专项在完整 Codex 宿主下环境跳过，确定性签名/策略用例通过；保留初轮失败与复跑原件于 /tmp/mao-pr-261001/matrix/ 与 final-targeted-summary.json。并非新 backend 的模型/Orca 全生命周期证明。
- 独立审查：code-reviewer 发现并复验关闭未授权PM迁移、退休祖先被跳过、QwenWork配置绕过与新CLI祖先漏识别；最终无剩余有证据P1/P2。新增CLI只作worker sentinel，不能嵌套强宿主提权；默认池与可选集合分离。
- Skill Lint：安全扫描0 critical/0 high，其余能力/fixture命中需按上下文看待。Harness Failure Audit有1项既有HFA-009（pm-cleanup-worker.sh:305），该行在冻结HEAD同样存在：扫描把观测旁路 RESULT.md 文本摘要的 jq -R -s 失败兜底当作配置解析失败；原件在 /tmp/mao-harness-audit.json。未通过变形规避扫描，未改无关清理模块；此项不是本次CLI支持的新权限依据，不宣称全Skill审计零finding。
- 证据：本次运行日志与summary在 /tmp/mao-maintainer-260930/，最后定向复跑日志在 /tmp/mao-final-*.log，安全扫描在 /tmp/mao-final-security.json；这些为本机会话证据，不打包公开。候选文件SHA-256清单生成于该目录，文档闭环后重新冻结。
- `NOT_VERIFIED`：除上述 ZCODE-BIGMODEL-LIVE 原生短请求外，其他新backend真实模型执行，以及新backend文件修改/持续纠偏/hook与Orca supervised完整生命周期；独立Qoder CN尚未安装（旧PATH软链指向已消失QoderWork），不自动安装；千问办公原生tools discovery未认证、bundled coding的账号/模型/积分归属未测。支持适配完成不扩大上述证据。

## TASK-2026-09-28-ORCA-SETTLEMENT-READBACK — 对齐真实 Orca 回读与外部终端结算

- 状态：`READY`；优先级：`P1`；类型：`runtime-compatibility`；Owner：未领取。来源：Eval Harness 的 P014 主线接入检查；这是该任务短生命周期验证的直接前置，不变更通信波次排序。
- 已复现事实：现行 `scripts/runtime_settlement.py` SHA-256 `6ca9c93e3394f0013a6bae627eba3d5573de19a8e4299d6daf39dae8d7fab08d` 对已保全真实 `worker-show` 回执报 `IDENTITY_MISMATCH: dispatch.run_id`；原始响应为 `runId` / `processIncarnation` / `runtimeEpoch` 等 camelCase。另一个独立资源谓词检查中，真实 `exited + exactWorker`、无 residual 的 `external/not_requested` 终端仍不能结算，因为当前规则只接受 Orca-owned `released`。
- 私有证据入口：由 P014 PM 保管的 `eval-harness/evals/ehcg-p014-integration-260928/`。原始退出响应完整哈希 `f79199c81126509135a22cf556086ad72589be3f3d384d857ee210c4aa06ffe6`；不向公开仓复制真实工作树、任务身份、capability 或课程数据。当前复现是历史原件只读重放，不是新 runtime 观察，不补签旧 attempt。
- 目标：让真实新旧 Orca 响应形状被严格消费，并按实际 owner 证明外部终端已关闭且完成结算；保留 `released` 与 `external closed/accounted` 的区别，不改写上游原始状态、不按 missing/失联推断退出。
- 允许范围：本 Skill 的 `scripts/runtime_settlement.py`、必要的 `scripts/provider-lease.py` 结算消费者、对应 runtime/provider 测试和短脱敏 fixtures、`references/23-runtime-settlement.md` 及随行版本文档；实现前现查基线并冻结确切文件。禁止改历史证据、私有 provider 配置、通用权限策略、用户全局 settings 或其他 Skill。
- 可观察验收：真实结构最小脱敏回放可被读取；snake_case/camelCase 双字段出现时必须同值，矛盾、缺项或错绑 Run/Task/Dispatch/runtime/incarnation/terminal 均拒绝。外部终端的正向退出必须与精确 owner、关闭后态、无残留、lease 与 Delivery 证据组合；仅 retained、terminal missing、退出自报或重复旧回执不得完成结算。旧 owned-release、terminal-loss、lease/ack 顺序及递归哈希回归保持。
- 执行与停止：先用私有原件只读复现，再在隔离短分支实现和独立复验；代码通过后才允许一次新鲜 MiniMax 短 live，经 MAO/Orca 且在首个业务文件前冻结 prepare。首个确定性阻塞即保全，不自动追加长课或重复 claim。P014 本地代码接入不等于本卡完成，本卡也不等于课程质量通过。
## TASK-2026-09-29-REMOTE-NODE-M0-E2E — 远程节点派发真机端到端验收

- 状态：`READY`；优先级：`P1`；类型：`verification`；Owner：待领取；来源：DEC-2026-09-29-REMOTE-NODE-DISPATCH（v2.30.0 代码已合，mock 全绿，真机链路未测）。
- 前置：v2.30.0 已进 origin/main；节点侧 `git pull origin main` 使副本版本门放行；节点 ssh 免密 + rsync + gh 可用。
- 目标：在真实节点跑通 checklist：probe ok 全字段 → 容量拒绝真机复现（临时调低 load_threshold → rc=4）→ 不可达 rc=65 → 基线门 rc=3（PM 未 push 时）→ receipt 生成/consume/重放拒/过期拒 → ssh 直调节点 spawn-worker.sh 无 receipt 仍 fail-closed → 完整 E2E（spawn-worker-remote spawn → 节点起真实 claude-code worker 读节点自己的 key、METADATA remote_dispatch.key_source_node 留痕、node- 前缀分支 push + PR、PM gh 可见、PR-fingerprint 验收合并、status 拿到 STATUS 演进、cleanup 后节点 lease/worktree/terminal 清干净）→ 降级演练（节点断开 → 65 → 回落本机路径人工走通）。
- 允许范围：本 Skill references/25 的验收记录、personal config（gitignored）节点参数微调、临时 receipt/probe 参数。禁止：为过门禁改弱 policy。
- 完成标准：checklist 逐项记录证据（命令 + 输出摘要）；不通过项登记为独立卡。
- 结案证据（2026-09-29 深夜，v2.30.4）：**派发管道全链真机验证通过**——probe 全门（ok/容量4/不可达65/基线3/版本门）；receipt 签发→Air 消费→重放拒绝；fail-closed 不变量；两次完整 spawn（Air 本机 lease acquire/finalize + ORCA worktree `~/orca/workspaces/legal-skills/` + `--trust-worktree` 预置生效 + worker 以借用 key 真实运行并修改 README）；PM 监督面（status 软账回写 + `orca terminal read --environment Air` 实读 + 双机 ORCA 终端列表同步）；失败恢复两轮全净（terminal close → lease release `--orca-cli` 显式 → worktree/branch/软账清零）。
- **未完成腿：worker 端到端交付 PR**。两次失败根因：①untrusted worktree（已由 v2.30.4 `--trust-worktree` 解决）；②worker 任务设计与 provider 稳定性——shell 白名单不含 `echo >>` 追加导致 worker 用多步 Edit 绕行，且 GLM（借用 key）当晚限流窗口直接终止会话（无 result 记录）。跟进要求：worker prompt 改用 Edit 工具而非 shell 追加；provider 稳定窗口重试。本腿转记到下方 AUTODISCOVER/调度 epic 前置，不单独阻塞 M0 结案。

## TASK-2026-09-29-REMOTE-NODE-PROMPT-DELIVERY — 远程 worker 任务投递与终端可见性

- 状态：`COMPLETE`（v2.30.5 交付）；优先级：`P1`；类型：`fix`；来源：用户 2026-09-29 观察"派发远程 worker 后对应终端没有真实推进"。
- 根因：v2.30.0-2.30.4 E2E 用 `claude -p` 内嵌任务——`-p` 模式缓冲全部输出到进程结束，终端只见 preamble；worker 实际在干活（transcript 有完整操作）但双机 Orca UI 均不可见；同时绕开 terminal-managed 的 checkpoint 契约（STATUS.json 无人写）。
- 交付：`spawn --prompt-file`（节点 METADATA 取 terminal_handle + `orca terminal send --environment` 跨机投递 + 失败重试 + 软账 prompt 段）；节点段新增可选 `orca_environment`；任务书规范（Edit 工具 + STATUS 契约）入 references/25。
- 真机验证：`NOT_VERIFIED`（等 provider 稳定窗口按新流程重跑完整 E2E 交付腿，与 SMART-SCHEDULING 开局一并做）。

## TASK-2026-09-29-REMOTE-NODE-AUTODISCOVER — ORCA 配对设备自动发现并登记 remote_nodes

- 状态：`READY`；优先级：`P2`；类型：`feature`；来源：用户 2026-09-29——用户说"派发远程 worker"时，检测本机 ORCA 是否配置了远程设备/服务器（`orca environment list` / `orca host list` 即现成清单），有则登记进 personal config `remote_nodes` 供后续直接复用。
- 目标：`spawn-worker-remote.sh discover [--write]`——列出 ORCA 已配对 environment（区分 local/ssh/environment 三类 host），对每个候选探测 ssh 可达性 + bash/git/python3 三道门 + 猜测 remote_root（该设备上本仓库 clone 的常见位置），打印登记建议；`--write` 时把确认项写入 gitignored personal config（占位字段留待用户补阈值），绝不覆盖已有条目。
- 允许范围：spawn-worker-remote.sh 新子命令、remote-node-probe.py 复用、example 文档；不自动 clone、不自动装依赖（那是 provision 的职责且需显式触发）。
- 验收：mock environment list 单测 + 真机对 Air 跑一次 discover 输出正确建议；已存在条目时幂等跳过。

## TASK-2026-09-29-SMART-SCHEDULING — 双账号×双机智能调度层

- 状态：`BLOCKED`（前置：REMOTE-NODE-M0-E2E）；优先级：`P1`；类型：`feature`；来源：用户 2026-09-29 定稿——两 GLM 账号（数据源=用户 fork 的 cat-xierluo/zcode-cli 项目，可读双账号额度 + 5h/周刷新卡；~/bin/zcode-quota 旧脚本已弃用）× 两机器（probe 容量）→ 动态分流：避开账号并发限制、避开单机终端过载、刷新卡临期优先消耗（token 效率最优）。用户已授权该 epic 开发期额度放心派发，且要求本 epic 本身用 worker 并发推进（M0 远程派发的首战）。
- 目标：在 spawn 决策前增加调度层——输入任务流，状态=账号侧（以 cat-xierluo/zcode-cli fork 的账号/额度/刷新卡读取为准，评估替换或扩展 quota_summary_zcode 生产方/references/21）× 机器侧（remote-node-probe + 本机 mem budget）× 在途（lease + remote-dispatches 软账），输出=backend×provider×机器 的派发建议；刷新卡临期（5h 窗口）优先吃、账号并发各自限流、机器终端数各自限流。
- 允许范围：route_suggest.py/quota_preflight.py 扩展、新调度脚本、personal config schema 演进、references 新页；不得绕过现有门禁。
- 验收：设计卡先行（数据源矩阵 + 调度判据 + 降级矩阵）；实现后 mock 调度单测 + 真机双账号双机实测各一轮。

## TASK-2026-09-29-DROP-CODEBUDDY-QODERWORK — 旧删除目标已被新指令替代

- 状态：`COMPLETE`（范围被用户 2026-09-30 新指令替代）；原类型：`removal`；旧来源：用户 2026-09-29 要求删除两者。
- 最新决定：只移除 QoderWork，CodeBuddy 保留；独立 Qoder CN 与千问办公是单独按需入口，不继承旧 QoderWork backend。实现及验收统一在 TASK-2026-09-30-OPTIONAL-CLI-BACKENDS。
- 禁止继续按旧目标删除 CodeBuddy。历史来源保留以供追溯，不作为执行授权。

## TASK-2026-09-24-CLAUDE-AUTO-SHELL — 恢复 Claude Code 原生 auto 的普通命令权限

- 状态：`COMPLETE`；优先级：`P1`；类型：`security-policy/usability`；Owner：Codex `/root`；来源：用户反馈 Claude Code auto Worker 的定向 unittest 被编排层 `SHELL_COMMAND_NOT_ALLOWLISTED` 拦截。
- 候选合同：分支 `fix/claude-auto-worker-shell`；Worktree `mao-claude-auto-shell/legal-skills`；integration base `origin/main`；immutable start `f36f7c0cc28e0bbafac08e90f995b6391390d85d`。
- 目标：仅对显式 auto 且 hook 生效的 Claude Code Worker，让普通 Bash 由原生 auto/settings 决定；保留安装、Orca 协议、tracked 删除和受保护 Git 操作的编排边界。其他 backend 与非 auto 模式保持精确白名单。
- 允许范围：本 Skill 的 `dependency-install-guard.py`、spawn/metadata/provider 包装、定向测试、`SKILL.md`、worker prompt、运行时参考、`DECISIONS.md`、`CHANGELOG.md`、`TASKS.md`，以及根 README 对本 Skill 的版本索引。
- 验收：原报错命令在 Claude auto 策略下不再由 hook 拒绝；安装、强推、主干 push、`gh pr merge`、tracked 删除与其他 backend 拒绝仍有效；spawn snapshot/METADATA/receipt 策略一致；运行定向门禁与 Skill 审查。真实 Claude auto 分类器是否最终批准该命令须在线实测，未测标 `NOT_VERIFIED`。
- 交付记录：PR #192；review 发现并修复无关文案与受保护命令解析缺口；GitHub `harness-regression` 和 `runtime-settlement` 检查均通过。
- 本地证据（2026-09-24）：`test-dependency-install-guard.sh` 190/190；`test-spawn-worker-metadata.sh` 31/31；`test_worker_delivery_prompt.py` 9/9；provider 路由回归 29/29；Python 编译与 Bash 语法通过；`git diff --check` 通过；skill-lint Harness Failure Audit 0 finding，Security Scan 0 critical / 0 high（其他命中主要为既有测试 fixture 与受控脚本能力）。真实 Claude Code auto 分类器对该命令的最终决策、真实 Orca/provider 生命周期为 `NOT_VERIFIED`。审查时移除无关的 subagent 通道选择文案，并修复 auto 门禁对重定向、赋值前缀和复合语法的误放行。候选分支独立于原工作树；原工作树其他 Skill 的既存修改未纳入本候选。

独立维护池另有 `HERMES-BASH-VERSION-GATE` 可领取；它只增加入口版本诊断，不得顺带处理首次 trust/MCP 交互或 GitHub merge 恢复。

## TASK-2026-09-14-GIT-RM-AUTHORITY — 明确 tracked 文件删除权限

- 状态：`COMPLETE`；优先级：`P1`；类型：`security-policy`；Owner：Codex `/root`。
- 候选合同：分支 `codex/mao-git-rm-authority`；Worktree `/private/tmp/legal-skills-mao-git-rm-authority`；integration base `origin/main`；immutable start `67a5b6c35d76f2002806af781f876e1730599877`。
- 交付证据：PR #180；实现 commit `957d545700c4c23499b946bdf1f60155a4e95198`；独立 adversarial review `APPROVE`。依赖门禁在 Homebrew Bash 与 macOS Bash 3.2 各 170/170，metadata 各 31/31，worker prompt 9/9；完整维护矩阵主体通过，`smoke-orca-worker.sh` 因本机 Orca 缺少 `terminal.multiplex.v1` 按设计 SKIP(77)，fake control-plane smoke 通过；Skill quick validate 与 harness audit 通过，security audit 为 0 critical / 0 high。真实 Orca/provider supervised 全生命周期仍为 `NOT_VERIFIED`。
- 来源修正：原卡名为 `MINIMAX-LANE-ALLOWLIST`，但复核证明 provider 并非根因。合同中的 `node <script>` 和 `gh pr create` 已可执行；失败来自 Worker 改写精确命令，以及 `git rm <tracked>` 尚无授权分类。
- 目标：为 tracked 文件删除建立窄且可审计的合同；同时让 Worker prompt 明确验证命令必须与 authority receipt 完全一致，不得自行加 `export`、`cd`、命令替换或多行 body。
- 已冻结设计：内置分类器只允许单段命令 `git rm -- <一个 repo-relative tracked file>`；必须命中启动时冻结并进入 authority snapshot 的 `allowed_write_paths`。高风险分类先于精确 `allowed_shell_commands`，因此 `--allow-cmd` 不能覆盖 `-r`、`-f`、`--cached`、多路径、目录/submodule、pathspec、Shell 展开或范围外拒绝。
- 允许范围：`scripts/dependency-install-guard.py`、冻结 `allowed_write_paths` 所需的 spawn/authority 生产链及其测试、`templates/worker-prompt.md`、`scripts/orca-supervised-protocol.sh`、`scripts/test_worker_delivery_prompt.py`、`references/02-runtime-dependencies.md`、`references/14-pm-orchestrate.md`、必要的版本与任务同步。
- 验收：最小 tracked fixture 正例；untracked、范围外、`..`、glob、`-r`、`-f`、远端删除混淆和复合命令反例；拒绝时索引与工作树不变。
- 定向验证：`bash scripts/test-dependency-install-guard.sh`、`bash scripts/test-spawn-worker-metadata.sh`、`python3 scripts/test_worker_delivery_prompt.py`，随后执行完整维护矩阵。
- 非目标：不开放任意 Shell，不把 verification contract 变成通用命令授权。

## TASK-2026-09-13-ORCA-CROSS-PM-HANDOFF — 跨 PM 基线通知与任务交接

- 状态：`RESTART_REQUIRED`；优先级：`P1`；类型：`implementation`；Owner：未领取。
- 前置：`ORCA-COMMS-CONTRACT`（PR #153）与 `ORCA-WORKER-ASK-REPLY`（PR #154）已完成。
- 状态修正：旧卡记录的本地分支/Worktree 已不可用，冻结基线停留在 `9fec934c`；不得继续标记 `IN_PROGRESS`，也不得复用旧 Run/Task/Dispatch 或临时回执冒充当前候选证据。
- 下一动作：从最新 `origin/main` 重建一页 Harness/消息合同，重新核对当前 Orca CLI/runtime，再新建短分支和独立 Worktree。旧双 Run shell 试验只能作为设计输入。
- 目标：在两个独立 PM session 之间完成 `offer → accept/reject → immutable handoff receipt`，绑定 source/target task、repo、base ref、immutable head、影响范围、已验门禁、未验证项、唯一下一动作和失效条件。
- 必须覆盖：错误/关闭 sender、recipient 不存在、runtime/repo/main/head 漂移、重复交接、接收方沉默、幂等恢复，以及 Codex App task 与 Orca Run 的边界。
- 权限边界：交接消息不转移文件、Shell、安装、Git/merge 或 lifecycle 权限；接收方必须显式接受，过期后重新交接。
- 非目标：不建立跨平台全局总线，不自动合并 PR，不用广播代替 ownership ledger。

## TASK-2026-09-13-ORCA-PEER-COMMS — 受限同 Run Worker/Reviewer 协作

- 状态：`BLOCKED`；阻塞于：`ORCA-CROSS-PM-HANDOFF`；优先级：`P1`（作为 P1 通信 E2E 的必要前置）；Owner：未领取。
- 目标：允许同 Run 内的只读事实请求、blocker、具名依赖就绪通知和 review 证据引用；默认由 PM 中转，只有身份和审计归属可证明时才评估 direct-peer。
- 禁止：通过 peer 消息修改任务范围、owner、allowed paths、安装/Git 权限、完成 verdict 或资源清理决策；禁止自由群聊和无业务价值广播。
- 解锁条件：Cross-PM Handoff 合并后，先复用其身份、correlation、幂等和失效合同，再冻结本任务 allowed paths 与验证矩阵。

## TASK-2026-09-13-ORCA-COMMS-E2E — 跨 Session 通信真实验收矩阵

- 状态：`BLOCKED`；阻塞于：`ORCA-CROSS-PM-HANDOFF`、`ORCA-PEER-COMMS`；优先级：`P1`；类型：`reusable_verification`。
- 目标：分别证明 `durably_enqueued → delivered_visible → consumed → replied → action_started → business_completed`，并覆盖重启、timeout、Delivery 重放、consumer fencing、handle/runtime 替换和资源结算。
- 验收：离线 fake CLI 故障注入与至少一个真实 Orca 多 session 场景；只有真实启动受支持 Agent 并观察 `worker_done → Delivery → PM 验收 → settlement → ack`，才能标记对应 backend E2E 已验证。
- 非目标：不把 shell session 消息测试扩大为 provider 全生命周期结论。

## TASK-2026-09-20-HERMES-BASH-VERSION-GATE — 入口 Bash 版本诊断

- 状态：`READY`；优先级：`P2`；类型：`diagnostics`；Owner：未领取。
- 已关闭前因：v2.27.4 已修复中文全角括号邻接变量导致的 `set -u` 崩溃；该问题在 Bash 5.3.3 同样复现，不能归因于 macOS Bash 3.2。
- 目标：对确实使用 Bash 4+ 语法/能力的生产入口增加统一、早期、可操作的版本诊断，明确 macOS 默认 Bash 3.2 的升级路径；不把普通语法错误、环境缺失或 runtime 失败误报成版本问题。
- 允许范围：先盘点实际入口与最低版本；保留 `pm-monitor.sh`、`check-dependencies.sh` 和 `references/02-runtime-dependencies.md` 已有诊断，只给遗漏的真实 Bash 4+ 生产入口补统一机器码与安装提示；不得批量改写全部脚本 shebang。
- 验收：Bash 3.2 fixture/替身得到稳定机器码与安装提示；受支持版本继续原行为；诊断发生在 worktree/provider/terminal/Orca mutation 前；完整维护矩阵通过。
- 非目标：不处理 Claude 首次 trust/MCP/import 交互，不改变 permission mode，不处理 GitHub merge 失败恢复。

## TASK-2026-09-20-HERMES-FIRST-RUN-AUTH-DESIGN — 首次交互的安全接管合同

- 状态：`PARKED`；原因码：`NEEDS_SAFE_DESIGN`；优先级：`P2`；Owner：未领取。
- 问题：Claude CLI 首次 trust、MCP/import 或相似交互可能阻塞无人值守 Worker；现有证据不足以安全自动回答。
- 解锁条件：先提交设计候选，列出每类真实交互的可识别证据、显式用户授权、隔离配置目录、超时/人工接管和清理合同，并给出零真实凭证的 fixture。
- 禁止方案：默认 `--dangerously-skip-permissions`、预写用户全局 trust、修改真实凭证、按模糊 pane 文本自动按键，或把首次交互成功扩大为 provider 生命周期已验证。

## TASK-2026-09-20-HERMES-GITHUB-MERGE-RECOVERY — GitHub 失败恢复合同

- 状态：`PARKED`；原因码：`NEEDS_SAFE_DESIGN`；优先级：`P2`；Owner：未领取。
- 问题：merge API 的 403/404/TLS/回执丢失可能分别代表权限、路径、网络或结果不确定；当前不能用同一 fallback 处理。
- 解锁条件：基于 `git-workflow` 冻结错误分类、PR diff/checks/review 证据、远端状态复验、幂等恢复和结果不确定状态；每类必须有零 mutation 反例与已发生 mutation 的 reconciliation 用例。
- 禁止方案：把 raw push main 设为静默默认 fallback、在 merge 结果未知时重复 mutation，或绕过分支保护和用户既定的 PR-first 顺序。

## TASK-2026-09-16-HERMES-PM-REVIEW-BATCH2 — 第二批纪律观察

- 状态：`OBSERVE`；优先级：`P2`；可计数证据：`0/10`。
- 规则：累计至少 10 条带 PR、提交或事件记录指针且按共同根因去重的证据后，再决定是否进入正文或脚本；在此之前不逐点 patch。
- 既有五个主题（stale base、派发后监测、宿主 subagent 边界、PM 收口例外、GitHub 通道降级）因任务源中没有可复查指针，仅作为线索保留，不计入阈值。任何新增观察必须附不可变证据和它与现有任务不重复的理由。

## TASK-2026-09-13-ZCODE-RUNTIME-ADAPTER — ZCode 真实宿主接入

- 状态：`PARKED`；原因：独立 ZCode owner/会话；优先级：`P1`。
- 已完成基础：PR #147 已合并，driver safety 的 27 个 Shell 断言和 59 个 Python 断言构成安全底座。
- 剩余：真实 CLI 配置入口、RuntimeAdapter、模型/套餐读回、双实例隔离和真实 provider 生命周期。旧卡中“PR #147 仍为 draft/未合并”的状态已作废。
- 恢复条件：用户或既有 ZCode owner 明确恢复；从最新 `origin/main` 新建候选，不读取或改写其他会话 Worktree，不把 stub 测试冒充真实 provider 验证。

## TASK-2026-09-05-ZCODE-QUOTA-PHASE2 — ZCode 额度消费链第二期

- 状态：`PARKED`；恢复要求：`REBASE_REQUIRED`；优先级：`P2`；原因：旧候选基于 v2.24.0，且曾发生未授权 Orca Setup 安装。
- 已解除前置：PR #151 已把 Orca Setup 固定为 `--setup skip`，但不使旧候选自动有效。
- 恢复条件：独立 ZCode owner 基于最新 `origin/main` 重建合同，重新确认个人 Coding Plan 5h 观测的身份边界、离线 fixture 与允许文件；真实请求、套餐切换、安装、远控和自动用卡仍需单独授权。

## TASK-2026-09-19-INSTRUCTION-STABILITY-CONTRACT — 建立机器可读约束追踪

- 状态：`PARKED`；优先级：`P2`；类型：`quality-infrastructure`。
- 问题：当前 `skill-lint instruction_stability_gate.py assess` 因缺少 `config/instruction-stability-contract.json` 只能给出 `INSTRUCTION_STABILITY_NOT_VERIFIED`；这不等于已发现具体业务错误。
- 恢复条件：先选择少量真正 hard 的跨会话/权限/完成约束，为每条建立稳定 ID、active checker、正确 artifact stage、最小违规反例和合法近似正例；正式稳定性声明还需要候选外 evaluator-signed baseline/held-out 与至少三轮真实产物。
- 非目标：不为消除扫描告警而给全部自然语言机械加锚点，不用静态 grep 冒充 runtime/state 验证。

## 已完成

| 任务 | 状态 | 不可变证据 |
|---|---|---|
| tracked 文件删除权限 | `COMPLETE` | PR #180；实现 commit `957d545700c4c23499b946bdf1f60155a4e95198`；独立 adversarial review `APPROVE`；两套 Bash 门禁各 170/170，security audit 0 critical / 0 high；真实 online lifecycle 仍为 `NOT_VERIFIED` |
| WorkerList 精确分页清理 | `COMPLETE` | PR #178；实现 commit `83488cdddc6606e9b772007452420cc1dd81734e`；独立 review `APPROVE`；维护矩阵 143 命令通过，Bash 5.3 / 3.2 专项各 211/211；真实 online lifecycle 仍为 `NOT_VERIFIED` |
| Completion Authority 收口 | `COMPLETE` | PR #145，merge `c7501e99` |
| ZCode driver safety 基础 | `COMPLETE` | PR #147，merge `f763d3dc`；RuntimeAdapter 另卡保留 |
| Orca Setup 安装策略 | `COMPLETE` | PR #151，merge `b368d62d` |
| Orca 通信合同 | `COMPLETE` | PR #153，merge `49f55385` |
| Worker ask/reply | `COMPLETE` | PR #154，merge `9fec934c` |
| Hermes PM 宿主识别 | `COMPLETE` | PR #155，merge `ffb47a8a` |
| Hermes 全 backend 授权 | `COMPLETE` | PR #156，merge `6645c0e8` |
| base-ref 引用合同 | `COMPLETE` | PR #165 / #173，merge `a2df4a5f` / `41072b9e` |
| `NON-ZCODE-CLOSEOUT` | `COMPLETE` | 其中曾停放的 PR #145 已于后续修复后合并 |
| `EXISTING-BRANCH-RECONCILE` | `COMPLETE` | PR #145/#147 均已合并；旧本地候选不得继续作为活动分支 |

## Agent 接手模板

领取任务时在 PR 正文或任务卡更新中填写：

```text
task_id:
owner/session:
status: READY -> IN_PROGRESS
branch_lifecycle: ephemeral-worker
branch/worktree:
integration_base_ref: origin/main
immutable_start_sha:
allowed_paths:
forbidden_paths:
verification_commands:
external_side_effects_authorized:
evidence_boundary:
blocker_and_recovery:
```

交付时补充 immutable head、PR URL、review verdict、真实测试结果、仍为 `NOT_VERIFIED` 的层、资源终态，并把任务改为 `COMPLETE`、`PARKED` 或 `RESTART_REQUIRED`。不要仅写“已完成”或保留失效 Worktree 路径。
