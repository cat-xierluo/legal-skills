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

## TASK-2026-10-01-INTERACTIVE-DISPATCH-CONTRACT — 交互CLI与派发前校验说明

- 状态：`COMPLETE`（限定说明文档与两阶段同session实际任务；最终文档review及PR合并由root执行）；Owner：Codex `/root/optional_cli_review`；来源：用户明确要求交互CLI长程，禁止新增headless/--prompt方案；root要求同步私有派发前校验调用合同。
- 冻结起点：`60e58b29ad2304bf0bd97bde91c7a8ebca3c25b9`（已独立ACCEPT并push至PR #233）；候选分支 `fix/mao-orca-terminal-ready`、隔离worktree `mao-live-cli-acceptance`；本卡仅文档，不改变已接受产品代码。
- 范围：ref28、ref29、本卡及CHANGELOG v2.31.3。保留已验tmux交互CLI正式工作路径，记录Orca TUI前提示就绪边界；私有校验仅版本感知调用，不复制私人规则、账号或路径。无新增batch配方、runner、spawn模式、默认池变化或权限扩张。
- 验收：按私有Skill当前版本说明/help调用其提供的 `validate-dispatch --observation PRIVATE_OBSERVATION --plan PRIVATE_PLAN`；具名两文件、现场重读，失败不投递；瞬时通过不当持续身份锁。须按实际安装版本核对是否提供该接口，缺少接口时不能宣称校验通过。
- 清单：①私有接口小节已只读核对；②交互CLI/校验合同已同步；③文档候选 `d902387bce5693e4ded1db7eeb5962fccaafd753` 已固定，保留版本2.31.3；④两阶段实际证据已由root回读，最终文档固定HEAD另交独立review，PR #233尚未合并。
- 证据职责：公开文档仅维护版本感知调用合同，真实私有运行与安装证据由私有Skill维护，不在公开任务卡承载。接口说明与私有规则实现分开，业务脚本保持冻结源码哈希。
- 同session实际任务：通过原生交互CLI、显式 `--no-orca-mode` tmux路径，第一阶段代码审查及256/256回归、第二阶段refs合同审查均收口；最终RESULT v1.2为 `ACCEPT`（审查候选 `d902387bce5693e4ded1db7eeb5962fccaafd753`），STATUS done、tracked diff为0、value postflight PASS。独立reviewer已核业务证据，stop/cleanup最后复核仍由root跟进，不将本卡范围扩大为Orca兼容。
- 实际模型：同一原生交互会话实际验证 `GLM-5.3-Flash`，并经原生 `/model` 切换后验证 `GLM-5.3 / max`；原生记录确认请求完成，重试无异常，不以argv或模型自述替代，也不代表逐请求精确计费证明。
- 范围与资源：PM补落盘具名初始worker提示；过程存在只读目录枚举超出精确scope，仍为prompt-only降级，不能宣称机械scope/hook通过。本轮tmux会话与执行资源由PM精确收口；公开记录只承载任务验收，不包含私人运行环境、账户用量、私有路径或原始日志。
- `NOT_VERIFIED`：通用调用合同不等于持续身份锁、自动机械绑定或已有worker账号归属证明；Orca ZCode TUI/长程监督/settlement、机械scope与逐请求精确计费仍未验。保留既有研究记录但不推荐无头替代，私人证据由私有Skill单独维护。

## TASK-2026-10-01-ORCA-WAIT-EXIT-CONTRACT — 消费原生未满足退出码

- 状态：`COMPLETE`（代码及定向回归已独立ACCEPT，PR #233尚未合并）；Owner：Codex `/root/optional_cli_review`（implementer）；来源：用户要求继续验证，原生 Orca 1.4.217 对合法 `satisfied=false` 回执退出1，修复前 helper 提前拒绝，未执行同句柄重等。
- 冻结起点：`a2dc75ef612731e23dec1678dc36fcbbf000a402`；base `origin/main` = `41268aaa91e71158cb4551dce8d757038869af0f`；复用本轮已授权隔离 worktree `mao-live-cli-acceptance`、分支 `fix/mao-orca-terminal-ready`；PR #233 OPEN，由root发布。
- 范围：仅 Orca spawn helper、定向 Orca 测试及必要 launch/mem fixture、SKILL版本、TASKS、DECISIONS、CHANGELOG、ref13、README MAO索引；交付 v2.31.3。不改Orca源码、focus、权限、宿主、provider、身份/资源合同或共享source。
- 验收：捕获真实退出码后严格解析单个回执；仅rc0布尔回执、rc1且false有效。rc1+true、rc>1、okfalse、畸形、错绑、多JSON均零send；false同一handle仅30s/60s两轮，supervised不双投。运行原生CLI handler的隔离消费者契约回放及真实shell退出码回归，无真实终端或模型请求。
- 清单：①登记任务已完成；②窄修复与定向测试已完成；③原生源码消费者回放与文档同步已完成；④源码 `60e58b29ad2304bf0bd97bde91c7a8ebca3c25b9` 已独立ACCEPT并push至PR #233。该代码任务已闭合，发布/合并由root执行，ZCode实际交互验收独立记录。
- 验证：`bash scripts/test-spawn-worker-orca.sh` 256/256（包含已安装原生handler输出false退出1/true退出0的无RPC消费者回放，以及其回执经真实shell退出码供helper消费）、launch42/42、mem58/58；本轮未修改launch/mem模块或fixture。日志为本机 `/tmp/mao-orca-wait-{exit,launch,mem}-test.log`。独立review已接受上述源码与定向回归；真实ZCode Orca兼容仍未验，PR #233尚未合并。
- `NOT_VERIFIED`：ZCode Orca ready合成及该路径的真实模型请求、supervised/settlement不以本轮隔离测试补证；错误/timeout/stale不作pending成功。

## TASK-2026-10-01-LIVE-WORKER-ACCEPTANCE — 两个 Skill 的实际任务验收

- 状态：`COMPLETE`（限定两项真实任务、私有fresh gate与已授权交接）；Owner：Codex `/root`；来源：用户要求自主推进测试，直至 MAO 与私有账号 Skill 可完成实际任务，并向已授权会话交接。候选文档 owner 为 `/root/optional_cli_review`，不改共享 source。
- 范围：MiniMax Code 与 ZCode CLI 串行执行有界隔离文件任务，PM 实际回读产物、测试、运行时模型与资源收口；私有 Skill 仅重新观测/规划与启动前身份复核。无真实账号切换、耗卡或产品化自动身份绑定；不影响已有 GUI/会话。
- 候选：`fix/mao-orca-terminal-ready`，代码冻结 `0ed048bfb80373a267c62dca38a48d880abde15e`；基线 `41268aaa91e71158cb4551dce8d757038869af0f`。readiness 源码已独立 `ACCEPT`，本卡的后续提交仅追加文档。
- MiniMax：真实 Orca terminal-managed 任务产物 HEAD `5461cc089956c078dccb53f79f69de471f07aa68`；PM 测试3/3，STATUS done、postflight通过、工作树干净、终端关闭；已独立 `ACCEPT`。数据库唯一工作区会话与原生 manifest/catalog/history路径精确一致，两轮 ingress（READY bootstrap + 具名业务任务）共15条 assistant 元数据及15条 HTTP200 响应事件全部为 minimax / MiniMax-M3.1-Flash-Preview；15个响应ID，不以argv或自述代替实际模型证据。
- ZCode：tmux fallback 产物 HEAD `08230b664fcaee9e6a2ee5f3257ec977073ffc9d`，PM 测试3/3、仅probe任务文件改变；SQLite 13条 completed model_usage均为 account:bigmodel-individual-coding-plan / GLM-5.3-Flash，retry0。临时研究认证/配置副本已精确删除，tmux关闭；独立产物验收 `ACCEPT`（限tmux实际任务），独立复跑3项测试及检查产物、原生模型记录、关闭/清理证据。
- Orca边界：当前1.4.217具备所需能力；两次 ZCode 尝试均 terminal_handle_stale，0业务send。MiniMax terminal-managed 没有 supervised Task/Dispatch；tmux不替代Orca，完整supervised/settlement、持续纠偏仍 `NOT_VERIFIED`。
- 权限/身份边界：均为prompt-only降级；ZCode bootstrap的ls超出精确shell allowlist，机械scope/hook未证明。私有路由和研究副本仅本轮使用；共享原件哈希一致性仅准备进程内断言，该次before baseline未持久化，独立before/after重放 `NOT_VERIFIED`；副本哈希不作替代。逐请求精确服务端计费仍 `NOT_VERIFIED`。
- 脱敏证据：本机 `/tmp/mao-live-acceptance-261001/minimax/tui-model-review/summary.sanitized.json`（SHA256 `87b957aa64cbab0b4272b613c00512141dc7460b7593b60467015617dd116580`）与本轮私有路由的 `prepare-baseline-audit.sanitized.json`；后者由私有Skill任务源管理。原始账号、日志、认证路径和内容不进公开包。
- 私有fresh gate：独立复核本轮observe/plan均ok，keep计划与观测active身份一致，观测至METADATA创建约2.496秒，小于120秒门限；仅本次研究副本绑定验证，不扩大为产品默认账号绑定。
- 交接：研究成果已通过工具实际发送至“Legal Skills｜总控入口”和“DSH 总控入口 插件”，包括两项真实任务及未验证边界，不含账号身份或凭证。
- 独立证据：本机 `independent-review/zcode-delivery-review.md` 对ZCode tmux交付为ACCEPT；`zcode/task-proof.sanitized.json` SHA256 `334d8f98a50895adf1d2a4aadb120e64d9b1f59d64d0b10c9313c39defc25926` 已核对原文件。本卡只关闭两项实际任务、fresh gate与交接；最终文档head复验及本修复PR的safe-push/发布由root负责，PR尚未合并。

## TASK-2026-10-01-ORCA-TERMINAL-READY — 投递前严格核对就绪回执

- 状态：`COMPLETE`（代码与定向回归已独立ACCEPT；本修复PR尚未合并，由root发布）；Owner：Codex `/root/optional_cli_review`（implementer）；来源：本轮真实 CLI 验收发现 terminal wait 的 rc0 超时会继续投递。
- 冻结基线：`origin/main` / immutable start `41268aaa91e71158cb4551dce8d757038869af0f`；已 fetch；分支 `fix/mao-orca-terminal-ready`，隔离 managed worktree `mao-live-cli-acceptance`。
- 范围：`scripts/spawn-worker-orca.sh`、定向 Orca 测试、mem-budget 测试的一行 wait fixture，以及本卡、CHANGELOG、DECISIONS、ref 13 和版本字段/README MAO索引；不改权限、宿主、provider、metadata 模块或 batch 启动机制。
- 清单：①核对当前 `orca skills get orca-cli` 与 wait help；②严格回执门禁、同 handle 有界重等；③确定性消费者回归；④独立 review 后由 PM 继续真实 CLI 验收。
- 验收：rc0 但 satisfied=false、畸形回执、命令失败均零 send；回执出现的handle/condition与本轮终端/tui-idle不匹配时也拒绝；明确 ready 仅一次 send；supervised 不发送普通 prompt。两轮等待分别30s/60s，仍不满足则非0退出并输出精确 terminal/worktree，保留资源供先只读核查后恢复。
- 交付版本：v2.31.2；新增 patch 记录，不改已交付 v2.31.1 的历史正文。
- 验证：`bash scripts/test-spawn-worker-orca.sh` 184/184、`bash scripts/test-spawn-worker-launch.sh` 42/42、`python3 scripts/test-mem-budget-probe.py` 58/58；Bash/Python语法与 `git diff --check` 通过。Orca helper 原件 `/tmp/mao-terminal-ready-261001/orca.log`，summary记录定向命令与结果；源码 `0ed048bfb80373a267c62dca38a48d880abde15e` 已独立 `ACCEPT`。真实任务结果与剩余范围见 LIVE-WORKER-ACCEPTANCE 卡，不把定向测试扩大为完整 supervised/settlement证明。

## TASK-2026-10-01-POSTMERGE-BACKEND-VERIFY — 合并与真实后端验证

- 状态：`COMPLETE`（合并、定向回归及有界真机验证）；Owner：Codex `/root`；来源：用户明确授权合并 PR #230/#320，验证功能并确认独立 MiniMax Code 后端。
- 范围：合并已独立接受的精确 HEAD，干净合并版本上的定向回归、私有只读账号观测、实际本地调用及 MiniMax 原生短请求；验证工作区/诊断均在候选外临时目录。不修改认证、共享默认模型或用户会话，不消费真实卡，不合并其他 PR。
- 验收：两个 PR 状态 MERGED 与 merge commit 可回读；合并版本定向测试通过、账号数据不扩散；MiniMax 完成模型请求才可声明后端接通，失败保留真实退出码和原因，CLI参数通过不可代替provider证据。
- 合并：公开 PR #230 与私有 PR #320 均为 MERGED；分别锁定独立 ACCEPT 的 HEAD `850b1d99b1bb18a7248d9a1a6a214d17151591ab`、`25c69fef1f01773c178782c60a9973af2e661d2f` 后 squash 合并。merge commit 分别为 `41268aaa91e71158cb4551dce8d757038869af0f`、`649fc0574daf402a72d303bf6c26b0a5d1b4fd6b`。公侧两项线上 CI 成功；私有仓库无在线 checks，已有25/25本地与独立 ACCEPT，用户本轮明确授权合并。
- 合并版本验证：干净工作树检出上述 merge commit，optional CLI 11/11、harness policy 36/36、worker command policy 23/23、私有 router 25/25 全部通过。已安装 router 与合并版本脚本哈希相同。
- 私有实际调用：按真实 ignored 个人配置找到已安装 Skill，原生 observe/plan 均退出0，账号映射与卡读取正常，未知额度保持拒绝。无 `--execute` 的切换预检退出64、`switch_target_quota_unknown_or_reserved`，拒绝额度信息不完整的候选账号；未切换账号或消费卡。额度建议仍受现有 worker 派发/并发门禁限制。
- MiniMax 真机：本机独立 `mcode` 0.5.10，经本 Skill renderer 的真实 batch 命令完成短请求；权威 `exec.completed` 状态 succeeded、退出0，模型回读 `minimax/MiniMax-M3.1-Flash-Preview`，providerKind 为 minimax-managed，用量回读完整。再显式传同一模型，在唯一临时文件中将减法改为加法，原生工具修改成功，文件字节与 `add(2,3)==5` 均符合预期，返回预期标记；未修改共享默认模型或认证。
- 证据：`/tmp/mao-postmerge-261001/` 下四套测试日志、私有只读 summary、切换预检 summary、`minimax/backend-proof.sanitized.json` 与 `minimax/edit-summary.sanitized.json`。短请求原始 stdout SHA256 `6d4d2bb061459ca9a057bcd1a5f7f80859c3155d5312afe1f024281f28ce3f5d`；编辑后 probe.py SHA256 `ba1a531f581d2e6094e978ed6f7aca7a8d92eeb62c6e7ad73ee692f7f18bc772`。原始输出和账号观测限本机私有临时目录，不进入仓库。
- `NOT_VERIFIED`：真实账号切换/耗卡、逐请求精确套餐扣分，以及新增 CLI 的完整 Orca 派发/交付/settlement 生命周期、持续纠偏与 scope hook；不把上述短请求/单文件修改扩大为这些层的证明。

## TASK-2026-10-01-LOCAL-ACCOUNT-SKILL — 私人账号调度调用合同

- 状态：`COMPLETE`（PR #230 已合并，实际本地调用通过）；Owner：Codex `/root`；用户最新决定：账号额度/刷新卡规则抽为独立私有 Skill；本 Skill 仅调用，不影响日常使用，不公开私人实现。
- 冻结基线：`origin/main` = `6d85291eb3a59d72cf95f9fb0542bd906eb49fbd`；分支 `feat/mao-optional-cli-support`，独立 app-managed worktree。
- 范围：个人配置模板默认关闭的 `account_routing` 与 ref 29、主入口和版本文档；具体实现与实测在私有 Skill 的 TASKS 维护，不复制账号/卡数据到此处。
- 验收：无配置不调用；启用且 backend 用户指定时读取本地 Skill；缺失/失败/未知暂停；不绕过任何现有派发门，不宣称 PM 调用是 spawn 机械账号绑定。
- 清单：调用合同已落地，独立 review 无有证据 P1/P2；私有 Skill 独立实现/安装验证由其任务源闭环；PR #230（https://github.com/cat-xierluo/legal-skills/pull/230）已合并，合并版本验证见 POSTMERGE-BACKEND-VERIFY。
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

- 状态：`COMPLETE`（支持适配交付；PR #230 已合并，未执行平台发布）；优先级：`P1`；Owner：Codex `/root`；来源：用户当前明确指令，优先于旧删除卡。
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
- 后续真机验证：MiniMax 原生短请求、显式模型与临时文件修改已通过，见 POSTMERGE-BACKEND-VERIFY；上述初次验收时间点的未测状态不代表当前仍未接通。
- `NOT_VERIFIED`：新backend持续纠偏/hook与Orca supervised完整生命周期；独立Qoder CN尚未安装（旧PATH软链指向已消失QoderWork），不自动安装；千问办公原生tools discovery未认证、bundled coding的账号/模型/积分归属未测。支持适配完成不扩大上述证据。

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

## TASK-2026-10-01-ZCODE-ORCA-NATIVE-INTEGRATION

- 状态：`COMPLETE`（实现、真实任务与精确资源清理验收；PR合并和本机安装由PM完成交付门）。
- 范围：用户指定的 ZCode 原生交互 CLI、同一会话接续、显式 native supervised 启动、可信单次启动环境桥；保留既有门禁、默认 worker 池与私人账号调用边界。
- 实现责任：独立 implementer 修改脚本；PM 维护文档、真机与收口；不同会话 reviewer 验收冻结 head。
- 交付：PR [#239](https://github.com/cat-xierluo/legal-skills/pull/239)；代码 head `e1fad17d1757aaec68e868a40d112914c452f522`。原始独立审查拒绝的重放和 nonready 回执问题已修复；独立增量审查 ACCEPT，无 P1/P2。
- 回归：本版完整维护矩阵 61/61 命令退出0；bridge 35项、launch 46项、completion 8项通过；安全扫描0 critical/high，quick validate通过。
- 真机：Orca 1.4.218 / ZCode CLI 0.16.9 / runtime 3.14.3，真实 fresh composer、唯一 Task 投递和 native authority 绑定通过。固定代码 head 的只读评审：阶段1实际35项测试通过；同一原生 session / terminal / Dispatch 经 `/model` 从 Flash 切至 GLM-5.3 后，消费/ack 正式 guidance，完成3个定向反例与最终证据，tracked diff为空；PM value postflight通过。
- 模型：SQLite 与请求日志确认同一个 interactive session 的个人 Coding Plan / GLM-5.3-Flash、GLM-5.3 成功请求，实际 Anthropic endpoint，无 MiniMax/体验套餐回落；不以模型自报或配置值替代此证据。
- 完成权威：唯一真实 `worker_done succeeded → Delivery`，Orca Task/Dispatch 自动成功结算；PM验收后 `worker-release` 返回 `retained / user_takeover / processAction=none`，随后 ack 完整 Delivery、收件箱为空。启动回执 created 不覆盖当前 user_owned；不得声称自动关闭已验。
- 失败记录：较早尝试在 provider 额度拒绝后未发 worker_done，按失败尝试保留日志并单独结算，不转记成功。上述成功来自修复版的新尝试，不复用旧认证或旧句柄。
- 资源：正式release的历史终态保持 `retained/user_takeover`。用户随后分别授权两条精确测试终端关闭，实际close与exit均确认；认证/配置研究副本在进程退出后按哈希核对删除，日志、SQLite、Task产物和启动绑定私有归档。两条测试工作树无tracked/untracked变更、终端为空后非强制移除；本轮备用shell与PM shell关闭，两个nonce及receipt精确归档删除，共享请求目录和锁保留。不得把人工关闭改写为coordinator-owned自动release。
- 权限接续：只读源码及纯renderer消费确认单worker `--permission-mode yolo` 输出原生 `zcode --mode yolo`，由spawn的 `--command` 冻结消费；spawn不接受renderer的permission参数。默认build的逐项审批可用正式CLI单键Allow once接续，不重发Task、不重拉worker；yolo仍有必须交互/alwaysAsk/plan例外，未新增yolo业务真机测试。具体见[原生合同](references/30-zcode-native-orca.md)。
- 审计：Harness Failure Audit原始两hard（HFA009旁路RESULT归档、HRA001测试grep计数）保留；独立定向消费者确认误报，不声称全Skill零finding。冻结e1独立ACCEPT，ee06文档/真实链及误报复核ACCEPT；最终交付head另经独立审查。证据根为本机 `/tmp/mao-zcode-orca-native-261001/`，包含terminal-close/exit、profile/request-cleanup与retained-evidence；无原始账号凭证入库。
- `NOT_VERIFIED`：新yolo任务的完整真机行为；coordinator-owned 原生终端的自动关闭；本轮 user_takeover 的实际触发来源；机械 scope/install hook；长期账号身份锁、自动切号/耗卡/持续预算控制；逐请求精确服务端扣分。MiniMax等其他backend的supervised不类推通过。

## TASK-2026-10-01-ZCODE-EXISTING-WORKTREE-ENTRY — 预建工作树首次原生接入合同

- 状态：`PARKED_SAFETY_UNKNOWN`；Owner：Codex `/root`；来源：授权总控将既有工作树首次接入收窄为独立实现/审查任务；当前只在隔离fixture实施，不代派原消费卡领域任务。
- 当前事实：已安装2.32.0的Orca spawn明确拒绝已占用branch/path，exit3 `EXISTING_WORKTREE_REQUIRES_RECOVERY`发生在provider lease/Context/terminal/Task副作用前；`--worktree`与`--branch-lifecycle long-lived`均不是reuse开关。当前Orca1.4.218 `worktree create --help`没有import/path/reuse参数，明确创建新checkout。repo注册不等价于允许复用worker工作树。
- 恢复边界：`pm-orchestrate reauthorize/quota-park`及recover-unconfigured依赖原始Session/METADATA/authority和Dispatch身份；不能为首次接入伪造这些文件、借恢复入口绕过门，不能用raw terminal create代替MAO门禁。Codex PM在backend policy中可选zcode-cli，但仍须真实harness链与当前Orca项目证据。
- 只读证据：`/tmp/mao-zcode-orca-native-261001/existing-worktree-consumer-contract.sanitized.json`，实际安装helper对本源已占用分支返回exit3；未调用Orca/provider/terminal/Task，未读客户材料。官方help与安装源码已核。准确request root及限制已发送至授权总控转交原PM，前一泛化模板已明确更正。
- 后续合同：若立项，在原唯一owner授权下设计显式借用已有树的新Session入口，证明canonical repo/path/branch/head、无active writer、范围/预算/authority门及borrowed long-lived保留策略；不能默认复用、另造同卡第二树或自动关闭用户资源。该行记录2.32诊断时尚未实现的边界；本轮代码/fixture实现见下，真实借用native仍未验，不影响已完成的新建原生路径。

- 执行合同：独立候选 `feat/mao-borrowed-minimax-orca-261001`，base `1002283663cd676ec17ada52da480ed4cb1af30b`；实现 `/root/zswitch_adapter`、独审 `/root/private_skill_forward`、PM `/root`。先隔离入口/失败保留/并发漂移验证，再独审、维护矩阵、真实受控接口验收；两失败episode上限，不因改名/runtime重置。
- 当前消费者：原消费卡已由原PM启动唯一MiniMax writer，进程身份已在2026-10-01精确只读核为minimax-code。既有工作树/卡/材料保持只读，必须待原owner重新明确无writer才允许将新入口用于该树；当前授权不允许另起第二writer/tree。
- 验收：缺显式合同仍维持exit3；合法借用形成真实新Session并保留原tree/branch/资产；active writer、身份/HEAD/快照漂移、冲突及未知生命周期全部失败关闭；失败与release不清理借用的long-lived资源。证据 `/tmp/mao-borrowed-minimax-orca-261001/`，未验范围明确NOT_VERIFIED。

- 恢复记录：首轮26个隔离fixture同一setUp因fake ps空库存被process_schema_unknown拒绝，资源副作用0；计episode1，正式acceptance-recovery分类internal_recoverable/repair，保留日志与ledger，不放宽生产未知拒绝。上限2，不重置；该episode修复已完成，原失败仍保留。

- 实现冻结：`cec2578be04c2b95985503359bc9f744ae85b9d6`仅14个scripts/tests；借用48个消费者分段PASS、8个受影响套件PASS，日志和14个SHA见implementation/fixed-scoped-evidence.json。首episode保留，scoped修复通过；独审/完整矩阵/有界真机待验，原消费卡/private未触及。

- 独审episode2：完整候选 `0101a044dd9c9f9dd97ea7a4ad01546fd4713ace`被REJECT（P1=0/P2=2）：可替换helper绕过旧bridge晚期门、可观测自定义Python writer被名单漏检。实际heldout已保全，live零启动。统一classification内部可恢复/re_review，连续episodes_used2，最后允许修复，下一新失败预算耗尽；产品源码与矩阵分别保持已拒head和原失败日志。

- 第2episode修复冻结：`ed53a4ffbcfe98ad6eb4b81c71fd6672a29a1c40`仅4个scripts/tests，产品clean；53个借用用例、原4个heldout消费者通过；旧2.32真实bridge合法请求exit0、晚期dirty/helper替换均exit64且backend零调用，未知Python writer拒绝且零账本。完整0f82候选独立功能复验关闭两P2，P1/P2=0；62项维护命令全部退出0，不继承实现者自报。
- 真实依赖边界：本机当前UID完整PID/cwd只读探测未完成（sandbox内read_unavailable、归因到sandbox外仍read_failed），0acquire/Task/terminal；不放宽未知拒绝、不补名单。本轮borrowed-native真机入口及结算 `NOT_VERIFIED`，原消费卡不得接入。MiniMax新建树默认Orca真机另行验收。

- 当前门禁：0f82独立普通功能ACCEPT；scanner原始SEC-DYNAMIC_IMPORT high保留，PM按明确例外只复核受信SHA绑定同buffer模块能力（ordinary_delivery=false），Harness snapshot/verify实际通过；原HFA/HRA两hard消费者归因保留。完整cwd不可证按acceptance-recovery facts_unknown_or_ambiguous→park，预算仍2/2，借用真机及原消费卡业务不派发。

## TASK-2026-10-01-MINIMAX-ORCA-DEFAULT-CHANNEL — MiniMax Code 默认 Orca 派发

- 状态：`VERIFIED / GIT_DELIVERY_PENDING`；Owner：Codex `/root`；来源：本聊天真人明确要求MiniMax通过ORCA派发以查看分支并统一管理，同时保留直连。
- 范围：显式选minimax-code后默认Orca terminal-managed；Orca不可达时失败关闭，不静默直连；保留显式直连入口。与借用入口共享产品脚本串行实现，独立审查和有界真机验收。
- 非目标：不将MiniMax加入日常自动backend池、不迁移/重启在途writer、不假称supervised Task/Dispatch已支持、不改认证/付费模型/全局配置。
- 验收：普通MiniMax派发在Orca具有可核对terminal/worktree/branch；显式直连可达；runtime失败不创建tmux/模型副作用；实际文件任务由PM回读产物验收并精确收口。原消费卡仍由原PM管理，不能作为本轮测试对象。
- 清单：价值合同、独立功能复验、完整62项维护命令、正式Harness门与本轮MiniMax真实文件/模型/资源验收均已过；PR/安装/交接由PM继续收口。证据共用 `/tmp/mao-borrowed-minimax-orca-261001/`。

- 真机：默认auto Orca1.4.218 / Mcode0.5.10，显式模型M3.1-Flash-Preview；产物`1f0c1513b09351542e5ce51411922c27b7079d63`仅probe.py，PM测试3/3、身份正确、工作树clean、postflight通过。新树/分支/终端由正式Orca inventory核对。
- 唯一接续：bootstrap已从本轮授权合同读取任务并完成业务；PM未重发业务，只发送一次已有成果验收指导。正式receipt accepted=true但provider unsupported仅证明运输，实际RESULT/STATUS及第二native ingress完成另行证明消费。原生16assistant/16HTTP200同minimax/MiniMax-M3.1-Flash-Preview、2completed ingress；按官方canonical catalog和session/turn/timestamp/rawusage复核，取证consumer两次假设错误及原生schema归因保留，不改产品取绿。
- 资源终态：`RETAINED_WITH_REASON`（long-lived测试树/分支保留）；Mcode/launcher/已记录后代全部退出，活动登记消失；精确测试CLI关闭、未用默认shell核后官方close-all(1stopped/retiredSurfaces)，最终终端库存0。没有其他业务worker被触及。
- `NOT_VERIFIED`：MiniMaxsupervised Task/Dispatch/worker_done/Delivery；逐responseId→HTTP事件直接join与精确计费；机械scope/install hook、长期连续性/身份锁。借用native限制不转记为MiniMax默认新建树失败或通过。

## TASK-2026-10-01-WORKER-PERMISSION-DEFAULTS — 隔离worker默认原生全权限

- 状态：`COMPLETE`；Owner：Codex `/root`；来源：本聊天真人要求默认权限开大，避免Orca worker阻塞审批，可用YOLO。
- 范围：ZCode CLI renderer默认yolo，显式build/edit/plan保留；MiniMax batch原生full，交互模式遵循实际支持接口，不伪造permission flag或改用headless。仅后续新worker，保持原工作范围/安装/Orca准入/验收，不影响在途会话。
- 非目标：不通过Skill修改Codex宿主审批机制，不将CLI YOLO等同跨聊天发送授权，不自动批准真实交互问题/账号登录。
- 清单：核本地安装；官方权限模式消费者；隔离实现与独立审查；定向argv/默认覆盖与显式收紧验证；PR/本地同步。证据 /tmp/mao-permission-defaults-261001/。

- 本轮实际验证：ZCode renderer默认命令启动无任务交互CLI，/mode回报Current mode: yolo；MiniMax原生TUI的/permission显示Current · Full access，配置字节未变，无模型请求，两probe精确退出。参数/默认spawn消费者与独立库存回归通过，PR、本地同步与最终独审继续收口。首轮采集器字节偏移/EIO及缺prompt-only合同的dry-run失败原件保留，未改产品取绿。


- 发布/安装收口：PR #243已合并（https://github.com/cat-xierluo/legal-skills/pull/243），审查head7b9a199a922ff5eba663146383e1adb93b13efdb，merge4fb2d3c77dfad95356c46f7eebeed2e199b9ad96，两CI SUCCESS。13文件CAS安装2.33.1，Git HEAD/branch/index/staged未变，5脚本SHA等候选；安装后默认yolo/显式build、batchfull/TUI无exec和真实两row只读消费者均通过。
- 验证边界：完整矩阵61项首0；58首次20/21 JSONDecodeError未知，候选/基线同case均0，一次带子进程记录的完整21/21复验0，原失败保留。最终独审ACCEPT，postflight/role/Harness门通过；PEA对定向证据裁定tested，不冒签全Skill新业务E2E。首probe/配置门/安装消费者setup故障原件均保留。

## TASK-2026-10-01-ORCA-RELEASE-PAGE-COMPAT — 原生已结算worker库存分页兼容

- 状态：`COMPLETE`；Owner：Codex `/root`；来源：现有Orca消费者报告真实release后MAO重复收口拒绝合法worker-list页。
- 范围：只读核官方当前页schema；窄修adapter和回归，保留分页/身份冲突/未知拒绝。不重开业务卡、不手改lease、不重做认证、不直接操作原业务资源。
- 原件：CS006修复波run_78c2835a1f6b，两Context ctx_32ebcdb1ca3b/ctx_1faef4251e36；原生已release并归档，MAO exit2 malformed worker-list page0，剩lease保留。
- 清单：真实只读schema消费、合法页与冲突反例、独立复验、PR与本地同步。证据 `/tmp/mao-permission-defaults-261001/release-compat/`。

- 窄修验证：269个cleanup消费者与15个sender用例通过；真实两具名row均精确匹配并为released/archive captured，旧4df2de30 helper对同库存均exit2，候选均exit0。仅只读，不操作原provider lease；实际业务结算仍由原PM使用正式入口完成。

- 发布/安装收口：PR #243已合并（https://github.com/cat-xierluo/legal-skills/pull/243），审查head7b9a199a922ff5eba663146383e1adb93b13efdb，merge4fb2d3c77dfad95356c46f7eebeed2e199b9ad96，两CI SUCCESS。13文件CAS安装2.33.1，Git HEAD/branch/index/staged未变，5脚本SHA等候选；安装后默认yolo/显式build、batchfull/TUI无exec和真实两row只读消费者均通过。
- 验证边界：完整矩阵61项首0；58首次20/21 JSONDecodeError未知，候选/基线同case均0，一次带子进程记录的完整21/21复验0，原失败保留。最终独审ACCEPT，postflight/role/Harness门通过；PEA对定向证据裁定tested，不冒签全Skill新业务E2E。首probe/配置门/安装消费者setup故障原件均保留。
- 原业务PM已用正式release执行两原Session，原件read_thread独立抽查：各already_released、processAction none、archive captured，且各PROVIDER_LEASE_RELEASED；命令exit0。此为原PM业务结算，不是root直接操作。

## TASK-2026-10-02-MINIMAX-ORCA-BATCH-STARTUP — 批处理启动与TUI就绪分开

- 状态：`IN_PROGRESS`；Owner：Codex `/root`；来源：真实消费者选择MiniMax exec/full，经Orca terminal-managed已启动原生Run，却被spawn的TUI wait误拒。
- 范围：仅MiniMax非交互启动合同，语义解析真实command而非字符串猜测；command本身已bootstrap输入时不等待TUI、不再次投递任务。交互CLI/其他backend/supervised路径保持原合同，记录准确启动模式与terminal身份。
- 非目标：不碰原CS006业务树/进程/认证/lease、不重发prompt、不另造该业务Task、不代替原PM收口。原scope2.33.1权限/库存发布已完成，不重开借用2/2预算。
- 原件：原nativeRun/SID及启动exit64 SPAWN_WORKER_ORCA_TUI_WAIT_INVALID，完整argv/diagnostics位于原PM cs006-mixed-orca-wave-20261002控制目录。业务由原PM继续，原生产模型已开始工具工作不等于本卡修复已验。
- 清单：具名新卡/价值合同；隔离最小实现；负例及无二次投递回归；独审；有界无客户材料原生exec启动/精确回收；PR与本地同步。证据 `/tmp/mao-minimax-batch-startup-261002/`。
- 实施边界：早期spawn入口preflight在route/lease/worktree之前拒绝batch与supervised/预建Task冲突；validator语义解析非空输入；实现者/root/permission_impl拥有spawn入口及启动/metadata/classifier/test最小文件，root负责随行文档。
- 实现冻结：eca7aad32e8909468c577f03f6b8552ebee5d32f，仅9个owned脚本/测试；startup8、Orca281、metadata33实际通过。原4fb2d3c7负对照同一bootstrap执行一次后wait64并漏句柄，候选0且仅terminalcreate/0wait/0send/准确句柄。首轮Orca267/276（fixture回执缺ok与递归env解析）失败原件保留，修复后281/281；不将fake消费者当真实模型成功。

- 有界原生验收：首轮候选e90经完整spawn启动exit0，仅一次bootstrap；原生Run exec_turn_mupsp045_s4ynyh succeeded/exit0/shutdownComplete，MiniMax-M3.1-Flash-Preview、2次assistant/1次工具，probe.py真实返回指定marker，PM1/1通过、artifact0fb66abb2a2054180d1793c0084c288500e153d1仅probe.py。原生配置SHA前后一致。两精确测试tab正式close，后续官方库存0，long-lived树/分支保留；两次collector断言失败原件保留，没有bulk-close实际发生。runtime_id空为既有metadata边界，不追填历史。
- 独审首轮e90 REJECT两P2（单引号$(cat)误展开、env exec误builtin），episode1已使用、最多2修复episode；实现者同原会话窄修真实Shell反例，canonicalstdin保留，不重发模型或原业务。最终复审、63项完整矩阵、PR与安装待PM核定。

## TASK-2026-10-02-ORCA-PARTIAL-WORKTREE-CREATE-RECOVERY — 首次创建回执断线残留续建

- 状态：`PARKED_DEPENDENCY / IMPLEMENTATION_PARTIAL`；Owner：Codex `/root`；来源：原IP PM与Slides核查，MiniMax前置门通过后worktree create runtime_unavailable，实际原分支/树落盘但无Session/authority/terminal。该问题与batch误等TUI分开。
- 原事实待独核：原分支feat-ip-timeline-map-261002、HEAD147cc3d476532b57615d0000efcde897446af02c、planned session ip-timeline-map-261002；同runtime恢复、Git clean由原PM报告。不是完整无writer证明，不能据此执行启动。
- 输入：原PM orca-consumers-20261002中的minimax-spawn-argv.json、minimax-spawn.log、minimax-partial-worktree.json、dispatch-spec.json、map-prompt.md、runtime-summary.json；仅本机读取，身份/原准入事实均须独核，不进入公开Git。
- 范围：受审显式partial-create恢复合同，仅原失败attempt精确资源；复核Git common-dir/path/branch/head、无writer、Orca repo/worktree/runtime、原scope/verification/value及预算门后首次创建标准Session/authority。已有Context/未知或活跃writer/dirty/漂移全部拒绝。不借recover-unconfigured/borrowed参数伪装完成，不改名重造原卡。
- 非目标：不直接操作原业务工作树/lease/terminal、不代派业务、不伪metadata、不复用陈旧准入、不重建认证；原PM保留writer与验收责任。
- 验收：隔离fake/真实Git证明原身份一次续建、并发/漂移/未知/重复拒绝、零重复worktree create/任务投递；独审及原PM按新入口接续才可声明原消费者恢复。当前入口和原消费者恢复`NOT_VERIFIED`。
- 当前依赖：danger-full-access不等于完整全UID cwd可证；实现者只读库存732条，至少一条cwd读取失败，whole_uid_cwd_provable=false。新helper仅隔离受审实现/intake方案，不是标准spawn续建入口；原消费者无writer及真实恢复仍NOT_VERIFIED。旧borrowed2/2泊车保持，原任务/资源保留，不重启。

## TASK-2026-10-02-DISPATCH-PROFILES-AND-RECEIPTS — backend×mode统一决策与唯一下一动作

- 状态：`SCOPED_ACCEPTED / LOCAL_SYNCED / ORIGINAL_BUSINESS_NOT_VERIFIED`；Owner：Codex `/root`，共享核心由MAO维护，DSH原owner消费，不开第二业务控制器。
- 来源：真人在「诊断多Agent调度瓶颈」2026-10-02明确授权既有MAO/DSH会话接手；root read_thread独核原人消息。报告SHA7e40f27adaf1470666c29e5f1095d60eda62c02677188e25befa5a82a59dab59，第9节为范围输入，方案尚非已实现命令。
- 原卡连续性：MiniMax batch由当前卡返修/复审，partial-create原消费者PARKED_DEPENDENCY，不重复立同题卡、不重启业务writer、不将intake候选当完整续建入口。
- 主范围：确定性backend×execution_mode/profile选择；已配置桥的ZCode默认原生Orca、generic仅显式兼容；MiniMaxbatch/interactive分路；结构化真实task_input/完成权威/唯一next_action，杜绝统一send提示；从实际配置和门回执显示并发/权限来源，收拢旧配方。共享schema/启动运行接口与DSH一份权威，保留MAO项目PM核心，先逻辑分层，暂不增加大模型传话层或物理拆Skill。
- 额外明确需求：审计现value门对合法研究/设计/文档业务任务的误拒，给匹配实质产物与验证模态的合同；维护docs/纯调查独立worker仍不得无价值扩波，不以放开字符串绕门替代证据。
- 非目标：不让每层自建运行JSON、不与DSH已管理项目争owner、不重做认证/账号或耗卡，不通过文案伪解除宿主拒绝。优先复用L2 state/events/lease/lock/pending_intent及现消息/authority接口。
- 验收：真实旧失败argv漏native flags、合法兼容、无重复投递、按模式唯一next_action；无旧上下文前向消费及一条有界真实链；身份/权限/config/未知残留错误先副作用前拒绝。完整完成→独审→原session返修→TASKS回写→下一项及长期稳定性须真实证据，未做则NOT_VERIFIED，不用参数测试冒签。
- 证据：原诊断报告及原件索引保留在原会话控制目录；本卡候选/价值合同/独审由root继续创建。此状态只为具名接手，不宣称profile/共同入口已可用。

- 本轮执行：dispatch-value-gate对 `/tmp/mao-dispatch-profiles-261002/dispatch-spec.json` exit0；release_compat仅拥有独立profile解析器及测试，原partial08候选保留、不继续原业务；batch实现者修两项独审P2，冻结新head后复审与完整63回归，入口文件串行集成。
- 新状态反例：Legal Skills总控报告ZCode任务completed/succeeded与worker_done已存在，composer却保留原任务文字；另有鼠标转义残留。仅screen草稿不推断未投递，原任务不补Enter、不重发、不重启。源码launch桥只exec冻结交互命令，Task注入由官方worker-start负责，PTY渲染根因尚NOT_VERIFIED；统一回执合同需区分draft/input_accepted/turn_started/worker_done/PM验收与retained终端。
- 涌现既有技术债：独审真实Shell消费者证明quoted assignment token（例如单引号包住NAME=value后再启动CLI）在通用validator中仍可误判身份，固定base已有同样行为；新batch修复已拒绝相关exec变体，不因此抹除既有盲区或扩大解析正确性声明。保留原反例，后续共享command语义入口单独根因治理，当前profile模块不再自造Shell解析器。
- batch验收继续：最终候选0b4e8576独审ACCEPT、postflight/角色/Harness门0，PEA scoped tested；完整矩阵前57项0，第58控制器25case中24通过、timeout/lost-receipt计数文件缺失失败。原件保留，formal第二episode限额内做candidate/base失败case及一次带子进程记录完整复验，root继续59—63，不提前合并或称首次全绿。

- 接入进度：batch2.33.2已合并安装，依赖解除；profiles pure4files已rebase到cd29976f，23profile/14adapter消费者0，真实Shell模式/权限由共享validator取得，旧显式native参数兼容；入口/metadata/唯一动作由同worker继续，尚未发布或执行新live任务。

- profile首轮df6154bd独审REJECT保留两P2：无schema旧个人配置误拒、completed回执漏拒本模块spawn_*_once。修复提交db45f0ad8db5110467a83ac6423b8bfbbb7e736f沿同一impl/session，缺schema明确legacy_unversioned、未知显式version仍拒，新节点仍严校；三个spawn动作纳入完成状态冲突拒绝。首65矩阵前11命令0、第12内存消费者49pass8fail均同根因，原件保留，修后矩阵与独审继续。
- 首候选新隔离真实链：故意遗漏native/supervised参数，spawn0自动取得已配置原生桥；仅probe.py产物7b5143721566e2a4c2a2b381b216a68b31e2c485，PM2/2。实际SQLite同nativeSID为个人CodingPlan/GLM-5.3/max completed retry0，唯一worker_done/Delivery核验，正式release返回released/closed_agent_terminal/archivecaptured，随后ack0、postshowcompleted/succeeded/released/none。本轮测试root/worker精确终端库存各0；long-lived分支/树保留。该canary绑定df6154bd，不改记修后head新模型执行。新树.video_agent/plugin_root来源NOT_CONFIRMED且早于模型请求，保留不删；tracked diff精确。
- 修后工程f71fd034独立限定ACCEPT，两P2 actual heldout关闭；65维护命令64首次exit0，第17夜巡28pass3fail原15探测超时保留。五调用源与base逐字节相同，唯一未改31/31复验exit0，首调度根因NOT_CONFIRMED；独审接受限定归因，不改产品期限、不称首次全绿。其余18—65续跑全0，无第三次盲试。当前Harness实际profile/adapter检查0与畸形输入64已核；直连CLI文案机械修正仅--no-orca-mode，最终文档head门与PR/安装待PM执行。证据本机/tmp/mao-dispatch-profiles-261002/，父业务模态合同仍待。
- 此profile发布子项不关闭父卡：研究/设计/文档实质业务的value门模态审计仍待；完整Skill指令稳定性、全backend、原partial/borrowed业务恢复以及账户持续控制未验证。

- 2026-10-03 顺序推进：用户确认先修合法业务产物准入，再统一并发口径，最后验 MiniMax 完整 spawn。沿原卡和 PR #248 的隔离树推进；本平台实现/独审串行，原业务 owner 不变。业务合同采用 `business_artifact`、真实文件指纹、来源与逐项独审；工程原 head/diff/commands 合同保留。证据目录 `/tmp/mao-sequential-gates-261003/`；当前工程候选尚待独审、完整矩阵与安装，不先记完成。
- 业务模态首候选 `2648f988`：作者五套件共117项通过，但独审真实反例发现 UTF-8 final flush 被短路，截断末尾可误过观察/postflight/review 三门，判定 REJECT；原失败保留于 `/tmp/mao-sequential-gates-261003/business-review/`，同作者窄修后重新独审，不能以首轮自测覆盖独审失败。
- 业务窄修 `08c1af90`：作者business14一次exit0；独审原坏字节重绑真实清单后观察/postflight/review均2，合法中文近似样例均0，限定ACCEPT、无blocker。原15个消费者与未变SHA复用，旧REJECT完整保留；尚未安装、完整矩阵和真实Orca/model不在该结论内。
- 并发基线事实：历史提交 `c8a77da677b71091056d3c9d9058e1d089d90c86` 已将 converge/explore/待验收 PR 上限发布为 8/10/4；SKILL 的 3/2 是残留。下一单元保留既有数字，区分本波候选数、PM 跨项目活跃库存与机器内存 slots，项目已声明的较小 cap 优先。当前门仅数 `spec.tasks`，不能声称实现全局原子并发预留。

- 2026-10-03 本轮限定交付：业务产物修后08c1af90独审ACCEPT，截断UTF-8反例三门拒绝，合法中文近似正例通过；并发0abbe330独审17项ACCEPT，沿已发布8/10/4默认值读取当前政策，capacity计已有库存+新候选并优先较小项目上限。库存为PM声明，无全局原子预留。原失败保留，原更广父卡及长期指令稳定性不冒签完成。
- 共用完整矩阵、首次超时、有限复验与安装记录见本文件 `TASK-2026-10-02-MINIMAX-ORCA-MEMORY-CONSUMER`，不重复维护证据。

## TASK-2026-10-02-MEMORY-TELEMETRY-NARROW-REPAIR — 原内存准入的解析与证据来源窄修

- 状态：`IN_PROGRESS / VERIFIED_PR_CLOSEOUT_PENDING`；Owner：原PM Codex `/root`。原实现ID由test-mem-budget-probe.py钉扎为TASK-2026-09-06-MEM-BUDGET；上一诊断卡不再猜该ID，沿相同TASKS/ref22维护源接续。
- 输入：冻结诊断3份真实快照及原Fathom第三轮；来源经原总控交接，消费者是Fathom/DSH原memory拒绝证据，不解除各自泊车或重复业务。
- 通道/资源：同宿主subagent为SKILL§1/2独立合法通道，无独立worker进程/CLIterminal/provider/worktree派发。现liveprobe仍exit3；不能换独立CLI绕门。复用已附着干净managed WT，新分支fix/mao-memory-telemetry-261002，base77b82251b36b270e88253ec2b40f9a43dae9b8a3；原profile分支/evidence保留。
- 实现写域：scripts/mem_budget_probe.py、scripts/test-mem-budget-probe.py、新scripts/test_memory_telemetry.py及scripts/fixtures/memory-admission-261002/**；根PM只写本卡、SKILL版本、CHANGELOG、DECISIONS、ref22/ref19与README索引。无其他代码/global/账号写域。
- 实现责任：/root/release_compat；独审/root/permission_review不同原session，不给产品repair grant。单波只一个实现者和一个reviewer，root统一收口；不重做已验诊断/profile/batch、不建第二controller。
- 行为合同：识别实际System-wide memory free percentage为“报告百分比”与parse-valid，不把84%当available_bytes或安全级别；保留旧关键词/旧available百分比合同。read-success与parse-valid独立结构记录（含缺失/空/未知/畸形）；legacy sources兼容。OS sysctl dispatch通知位1/2/4映射normal/warn/critical，unknown保持unknown；新原生观测只记录来源/值/level，明确used_for_admission=false。算法现level/slots/status/exit/0.95/0.75/default3GiB/reserve/formula不改变，不隐入任何native压力例外策略。
- 预算：实现<=25分钟，scoped新测试一次及原内存套件一次；原始失败保留，同任务最多2失败episode，未改代码重复验证不充稳定。reviewer只读diff/必要文件、正反例及三frozenraw，环境归因至多一次，不复跑整包。root受影响消费者/发布检查串行；不无限模型/步骤。
- 验收：三冻结真实快照parse有效、来源准确且原swap拒绝均exit3/slots0；读取成功但parse无效、缺失/空/非法/多行nativeflag、合法1/2/4、native与composite不混淆、无vm_stat时新84%不能成为物理可用兜底、原schema/正常与低内存/E2E副作用边界回归。独审绑定immutablehead、postflight/role/Harness/PEA scoped、PR exactmerge后CAS同步保主sourceindex与并发改动。
- 非目标：不改0.95、预算、global或例外放行；不purge/reboot/kill其他owner；动态swap/磁盘底仓、新压力准入策略及任何例外仅留单独受审设计。独审与发布仍待完成，NOT_VERIFIED。
- 证据：/tmp/mao-memory-telemetry-261002/，完整派发价值JSON同处；source内存门前后可比，Fathom/DSH业务结果非本卡交付。

- 工程首轮：新遥测13/13、原内存58/58实际exit0，无失败episode或重跑；三frozen CLI保留exit3/slots0/swap critical与原available_bytes。报告84%解析有效但level/available_percent null；无vm_stat+新百分比仍exit1。冻结工程交独立审查，完整矩阵/发布尚待完成。

- 独立验收：a7a6a81d实现绑定ACCEPT，新13/原58独验0、39 heldout/78次base-candidate CLI原payload去telemetry与退出精确一致；三frozen15raw byte/SHA相同，旧parse84 None→新reported84、无physical fallback。首外置consumer错flag/尾marker解析及唯一纠正复验保留，不归产品failure。
- PM完整维护矩阵：66/66 exit0，直接复用两个工程字节相同首套件，其他64项各运行一次；无需失败episode。raw diffcheck2仅15原样快照trailing spaces，非fixture0；静态SEC1/HFA1/ISG2原告警保留，非本修范围不签全Skill安全或多轮稳定。最终文档仅修composite使用条件并记录证据，PR exact交付、本地CAS仍待完成。

## TASK-2026-10-02-HOST-AUTOMATION-APPROVAL — 真人授权后正式宿主接续工具仍被拒

- 状态：IN_PROGRESS；Owner：本MAO支持PM，业务worker/原任务写回仍归Fathom原PM。来源：总控增量通知，已回读原聊天真人“授权周期接续”及原工具失败日志。
- 已确认：原automation_update create失败，原始输出isError=true/MCP tool call requires approval, but approval policy is never；同回合turn_context记录on-request，两层事实不一致，具体宿主工具策略传播根因未确认。已有旧job PAUSED且绑定旧聊天，不是当前原PM接续；当前MiniMax在途，不因此重派或阻塞。
- 范围：核正式宿主入口及已授权原PM目标；不更改全局审批/allowlist，不改旧暂停job，不造第二PM或shell定时，不将worker原生full权限扩大解释成PM工具审批已开放。实际支持入口成功时核job唯一身份/原PM/原卡并只记配置就绪；失败保留原拒绝，不能说缺真人授权。
- 验收：准确拒绝原件和两层策略事实可回查，原业务会话与成果保全；合法解锁路径不绕过审批，不自签自动闭环。宿主根因及首次真实tick/返回独审续派不具备时NOT_VERIFIED。
- 本轮可执行处置已完成：回读原真人周期授权后核当前原PM没有job；本支持上下文正式automation_update create成功，新job fathom-pm-worker ACTIVE/20分钟，target精确原PM。真实配置经新准备门exit0且autonomous=false；原旧PAUSED job未改、原worker未重发、无第二PM。这只解除本案例“没有job”的缺口，不证明原聊天MCP审批传播已修、首次自动tick或业务闭环；原拒绝/本成功及on-request对never差异保留在私有证据。
- 收口增量实证：官方原线程回读到fathom-pm-worker的heartbeat消息（2026-10-02T05:02:59.871Z），原PM自动消费ZCode固定head独审与角色门，真实GUI验收失败后写回ISS-141/累计3/3，并正式暂停同job。root独立只读核原role receipt、GUI FAIL、原Task写回与实际PAUSED/精确目标一致；这是一次自动返回验收→写回→预算泊车周期，不是长期稳定/成功交付/新的下一卡派发。此前人工恢复归因保留，原MCP create审批传播根因仍未确认。

## TASK-2026-10-02-CONTINUATION-READINESS — 持续推进入口与人工介入归因修复

- 状态：IMPLEMENTED_SCOPED_ACCEPTED / PR_PENDING；Owner：本MAO Codex PM。来源：真人指出先前恢复心跳是其手动催促，要求从Skill不明确/脚本/其他原因定因、登记并推进。
- 同源边界：派发阶段事实继续归DISPATCH-PROFILES-AND-RECEIPTS，真实收件/独审证据适配继续归EVIDENCE-AND-PR-CLOSEOUT；L3仍归reference16的Task-067，不另造controller/业务队列。
- 已确认：主文派发前合同没有持续模式的监测准备检查，ref15的强制cron只靠PM遵循；orca-wave-prepare不检查PM持续唤醒。ref15把泊车写成整波停止/删除cron，容易把单卡失败扩成整个目标停止。Fathom旧副本2.28.0是部署漂移，Orca orphaned/readiness失败是运行时问题；后两者不能只改提示词追认解决。
- 本次范围：补主文强制分辨one_wave/continuous；显式continuous Wave资源创建前以只读门检查原PM、原任务源及真实Codex heartbeat ACTIVE/目标/周期/原卡绑定；配置通过只称CONFIGURED_NOT_PROVEN_AUTONOMOUS。补人工恢复归因、返回→独审→原Task写回→修复/合法下一项以及单依赖链泊车纪律。旧无持续字段调用保持兼容，不冒称所有自然语言调用被机械拦住。
- 验收：暂停/缺job/错PM/只宏观心跳/缺原卡/错误周期/未来schema在任何Orca调用前拒绝；合法配置实际读取且仍不签自动闭环；无新全局配置/账号/自动化写入；原wave生命周期回归与独立审查。至少一次无旧上下文前向消费核one_wave/continuous和人工唤醒差别；跨会话持续调度另保NOT_VERIFIED。
- 后续原卡依赖：Task-067补正式宿主job管理及丢推送/退出/到期恢复演练；Task-068补部署版本/读取来源一致性。本轮不替其他项目切版本、不重派在途worker、不绕过宿主审批。
- 涌现验证缺陷：完整矩阵原test-pm-monitor第7例25PASS/1FAIL，固定2.6秒结束循环前未观测到RECOVERED；测试与生产monitor均与已发布版逐字节相同。改测试私有sleep shim在真实循环末记录完成轮次，最多60秒等待三轮后断言；不改生产周期。原失败保留，独审修后26/26通过，窄故障拒绝与发布候选字节一致性均已核；新准备门/Wave/监测测试同时接入既有CI。

- 限定验收：新准备门10项与独立3组反例通过，真实既有job只读消费与错PM拒绝通过；无旧上下文两情景能区分宏观心跳和真人恢复。核心8文件及监测/CI/ref16四对象独审摘要绑定一致。CI定义增加准备门、Wave与监测fixture；尚未以CI结果签通过。
- 完整矩阵首轮67项：61 exit0，6项非零/超时/跳过；两个exit0的tmux smoke也实际为sandbox环境SKIP。原件全部保留。只做有限第二次：借用树53/53、closeout、controller在生产及测试字节不变下exit0（仅外层上限180→600秒）；monitor修后独审26/26；facts仍20/21，剩余超时/身份诊断归新验证欠账卡。此证据不代表首次全绿、全Skill稳定或真实自动独审续派。
- 发布隔离：主source有其他会话GUI文档2.35.1未提交改动，保持其成果；隔离候选本修2.34.2基于远端MAO2.34.1，不回滚共享源码、Git index或个人配置。候选与源码新脚本/参考同字节，版本部署总验收仍归Task-068。
- 单次真实业务接续补证：Fathom原正式job一次HOST_HEARTBEAT已触发，原PM消费独审/真实验收并写回预算泊车，job已正式PAUSED；详见HOST-AUTOMATION-APPROVAL卡。此实证不追认先前人工恢复，也不关闭长期/丢推送/重启及下一合法卡续派的Task-067。

## TASK-2026-10-02-ACTIVE-CONVERSATION-USAGE-AUDIT — 活跃对话派发与持续监测现场审计

- 状态：COMPLETE（只读审计，不代表消费者修复/持久调度完成）；Owner：Codex当前MAO会话。来源：真人要求核查各活跃对话是否真实派发/交接、worker开始工作、PM持续核实和定时监测，不能以声称派发或一次交互代表闭环。
- 范围：只读最近活跃项目及相关worker对话、原Task/Session与成果、Orca当前官方状态和既有自动化；区分当前事实、历史成功、未验证和合理泊车。现MAO2.34.1/账号routing已交付不等于每个消费者已接入。
- 非目标：不向未获授权业务聊天发送指令，不重派业务，不建立或修改自动化，不停止/释放他人资源，不改运行策略、权限或任务身份；必要修复按原同源任务另行推进。
- 真人归因纠正：Video/LivePhoto恢复监测由真人在各原聊天手动催促触发，不属于既有闭环自动修复；ACTIVE配置、一次自动触发与自动review/接续分别记证据。旧审计的状态截面保留，但不能作为无人工介入的闭环验收。
- 验收：给出逐对话阶段表与可回查证据；核实宣称派发后的实际开始/进展/完成和监测owner、触发方式、last/next事实，说明现在是否能正常派发及哪些链路仍未闭环。结论不能只采信PM或worker自报；现场读取不足明确NOT_VERIFIED。
- 证据：本聊天既有私有工作目录 active-conversation-usage-audit-20261002，保留读取索引、原状态摘要和官方快照；不复制第二控制器或业务任务源。
- 研究交接：沿真人此前授权，审计报告与最新监测变化已通过send_message_to_thread发给「Legal Skills｜总控入口」和「DSH 总控入口 插件 PM」，两次工具成功；仅记入队，不宣称对方已消费/已修复，其他项目聊天未发送指令。回执见同目录handoff-receipts.json。
- 验收（2026-10-02，主要现场11:35—11:49，收口增量至11:55 Asia/Shanghai）：读取14个相关近期聊天并新鲜更新10个；受审只读读取Orca1.4.218 runtime/worker/terminal/run/automation、独立核5个原树head/clean、读取初始11个及收口12个Codex定时配置、实际总控与LivePhoto heartbeat。ZCode/MiniMax均有真实本轮工程提交，派发可用；DSH022 stale、Fathom恢复就绪失败后terminal-managed且旧内嵌MAO2.28.0、moot-court DSH ZCode coordinator orphaned、Code Video初读没有专属后台循环、多个项目心跳PAUSED，不能宣称全项目持续闭环；收口时真人在原Video聊天明确授权，原PM实际创建20分钟heartbeat，首次触发待验；LivePhoto恢复5分钟持续派发独审并11:53:20真实触发。收口共3ACTIVE/9PAUSED，总控5分钟心跳真实触发且scope6项目；next实际时间NOT_CAPTURED。明确区分Slides/LivePhoto预算泊车和IP MAP技术依赖，不把合理暂停误判漏监测。详见私有REPORT.md与evidence-manifest.json；版本安装/旧lease/partial-create等剩余仍归原同源卡，审计未替其他PM改业务或建立第二controller。

## TASK-2026-10-02-CONTROL-SOURCE-LIFECYCLE-AUDIT — 持续监测绑定的原控制树消失

- 状态：OPEN；Owner：本MAO支持PM核生命周期证据，原任务源恢复与Folia业务仍归Code Video原PM。来源：原PM报告13:00实际heartbeat首次读原卡成功，随后控制树消失；root稍后复读时目录与原任务源已存在，不能把报告期间的消失当作root亲见的当前状态。
- 当前复核：旧合法合同再次消费实际exit0/CONFIGURED_NOT_PROVEN_AUTONOMOUS，原job配置digest不变、autonomous=false；删除/恢复actor与调用尚NOT_CONFIRMED。初补记在读取结果前写了缺失/exit64，已按实际原件纠正，不把预期当事实。本支持本轮没有直接调用真实worktree/terminal删除或archive API，完整回归使用隔离fixtures；此事实不替代删除根因审计。
- 范围与验收：保留原注册/生命周期/事件证据，核精确资源owner和删除调用，区分控制树保留约束与临时workspace规则；不替原PM重造任务源、停在途worker、重派或另建controller。原owner恢复后重核同一job/原卡及真实接续，恢复来源如实记账。不能按树不存在猜测责任人。
- 原owner增量报告：精确原branch/原path已用受审git worktree add恢复，heartbeat合同重核通过；未提交字节未恢复已披露，Folia原业务继续，未新建scheduler。root当前存在/exit0与该报告一致，删除责任仍NOT_VERIFIED；恢复属于原PM行为，不能记成本支持自动修复或长期稳定。

## TASK-2026-10-02-FACTS-VALIDATION-TIMEOUT — 事实采集器超时测试的身份失败诊断

- 状态：IMPLEMENTED_SCOPED_TESTED / PR_PENDING；Owner：MAO维护PM。来源：本轮完整矩阵首轮facts受180秒外层上限中断，未改字节有限第二次在600秒内退出1，20/21通过，probe timeout is bounded返回repository or policy identity drift/66。
- 已核边界：生产autopilot-facts.py及测试与已发布基线逐字节相同；case_timeout把项目probe sleep3秒与全collector timeout1秒组合，身份Git探测也使用同timeout。实际哪个子命令导致66尚NOT_CONFIRMED，不能用高主机负载或同字节单独归因；不把失败改成预期通过。
- 范围：沿原collector/测试精确记录各子进程退出/耗时，核身份真实漂移与身份探测超时分类；保留所有失败原件。若改产品或测试，先补明确合同、对应正反例和独立审查，不扩大productiondeadline以取绿，不第三次盲跑整包。
- 验收：实际失败具名根因及可复查最小反例，正确身份漂移继续拒绝，项目probe timeout在身份已证明的条件下有准确unknown/timeout事实；新修后运行同一相关消费者并独审。完整回归与跨会话闭环目前NOT_VERIFIED。
- 证据：本机/private/tmp/mao-continuation-matrix/63.log、facts-bounded-second.log、bounded-second-journal.json及remaining-failures-byte-comparison.json；首失败及有限复验均保留在本聊天私有证据包，不进入公共fixture。

- 2026-10-02限定修复与证据：身份探测现在逐项保留状态：timeout/unavailable/非零观测69、IO74、坏数据或超量65，成功观测到真实不符仍66；所有失败立即停止下游probe，不扩大生产deadline。修后23/23 exit0，真实caller对子进程69/74/65/66均拒绝，即使stdout伪装facts也不返回。受控真实Git超时反例已复现分类缺陷，原现场具体失败子命令仍未确认；不以新反例追认负载根因。 本轮证据冻结于维护者archive/20261002_gate_stabilization/，包括实际命令、退出码、候选SHA与所有失败原件；独立审查按本PR最终不可变head绑定，长期稳定性另验。

## TASK-2026-10-02-READONLY-SMOKE-BRANCH-COLLISION — 只读原生smoke固定分支与已有树冲突

- 状态：IMPLEMENTED_OFFLINE_SCOPED_TESTED / LIVE_NOT_VERIFIED；Owner：MAO维护PM。来源：本轮sandbox首smoke exit77，受审只读代理复核真实Orca1.4.218后到达auto检测，但dry-run exit1，固定feat/smoke-orca映射到已有同repo工作树（dirty86）。
- 已核：runtime实际有terminal.multiplex.v1，不能将首次sandbox的capability缺证当作产品缺能力。原smoke固定BRANCH，当前真实环境已有对应树；这是现场冲突，非新准备门验证失败。
- 范围与验收：治理测试私有身份的唯一性及冲突诊断，保留生产occupied-worktree拒绝。先核既有树owner；不删除/强制复用原树，不以重跑或换身份解锁业务。新只读smoke须仍经严格Orca读代理，不启动真实Agent/Run；原失败留存。
- 证据：本机/private/tmp/mao-continuation-real-orca-status.json与mao-continuation-real-orca-readonly-smoke.log；当前原生smoke非通过，完整生命周期NOT_VERIFIED。

- 2026-10-02限定修复与证据：只读smoke用每轮私有nonce及生产safe_branch规则派生branch/session/WT/CTX；不改生产occupied保护。隔离原smoke+真实spawn dry-run最终4/4 exit0：连续两轮不冲突、占用拒绝且marker保留、readonly mutation95、路径映射一致。先前三次fixture失败（Bash3.2、非canonical worktree ID、缺runtimeId）原件保留；最后只补真实runtimeId协议字段，不弱化断言。没有真实Orca mutation/模型调用，完整生命周期仍NOT_VERIFIED。 本轮证据冻结于维护者archive/20261002_gate_stabilization/，包括实际命令、退出码、候选SHA与所有失败原件；独立审查按本PR最终不可变head绑定，长期稳定性另验。

- 独审补充：作者4/4之后，不同session首跑2/4，真实祖先身份前门早于smoke目标断言拒绝；该测试仍依赖宿主环境，返修仅补私有ps完整合成祖先链，不改生产门；定向suite一次4/4 exit0（18.508秒），其余三源码SHA不变，Facts不重复执行。原失败报告按6058e6d固定并保留，合成输入仅用于隔离测试，不是实机宿主身份的证明。

## TASK-2026-10-02-MINIMAX-ORCA-MEMORY-CONSUMER — 完整派发入口资源合同验收

- 状态：`WHOLE_SPAWN_SCOPED_ACCEPTED / LOCAL_SYNCED / LIVE_MODEL_NOT_VERIFIED`；沿原 MiniMax 资源候选与原平台 PM，业务任务仍由原业务 PM 管理。本轮不新派原业务，也不改变模型账户、默认 lane 或权限范围。
- 来源与依赖：用户确认业务产物准入→并发口径→MiniMax 完整 spawn 的顺序；前两项固定 head `08c1af90`、`0abbe330` 已分别限定独审 ACCEPT。资源核心与宿主适配沿原 `RESOURCE-GATE-CALIBRATION`、`CODEX-HOST-MEMORY-PROFILE`，此前候选冻结 `b3e9e849…6160382` 限定独审通过但未安装，旧失败与维护矩阵超时不被抹除。
- 唯一实现者 `/root/release_compat`，之后 `/root/permission_review` 独审。限定移植八个资源生产/测试文件并新增完整入口消费者，禁止复制旧候选整树覆盖新业务门/facts/smoke；其他文档与CI由PM持有。
- 验收：从真实 `spawn-worker.sh` 贯穿早期命令/安装绑定、同一内存探测、late Git/cwd/HEAD/stdin绑定与最终启动；前置拒绝零资源副作用，晚期拒绝零Agent注入并记录已有owned资源。保留旧默认策略；新profile明确≥3GiB、单writer、20秒稳定窗、未测整worker RSS及非全局原子预留。隔离假Orca/采集器成功不能代替真实模型业务。
- 涌现接线缺口：`node_mem_cap_setup` 将 MiniMax COMMAND 包装为固定 `exec-bound` 后，`spawn-worker-launch.sh` 仍按裸CLI重新分类，可能把合法guard误拒为exit64。已授权同作者扩展这一个模块，先用完整入口复现再窄修；必须验证最终COMMAND确为本次可信render产物并重验原命令/binding，不能泛放Python wrapper或只凭profile存在跳过检查。
- 预算：本单元2026-10-02 17:11 UTC开始，截止17:35 UTC，最多2失败episode。新完整入口与原MiniMax定向套件各一轮；必要的launch邻接回归另一次，PM最后串行完整矩阵。证据 `/tmp/mao-sequential-gates-261003/minimax/`，目前未安装、未签原业务恢复。
- 完整入口首轮fixture导入失真首红保留；第二轮10项中9通过、正例1失败，定位到更早的 `spawn-worker-metadata.sh` 也把可信guard当裸CLI误拒，尚未抵达已窄修launch。不是资源不足或授权拒绝。PM据具体第二消费点授权同作者在原17:35截止内最后一次有界纠错，追加metadata唯一写域，与launch共用已核guard/native argv的验证逻辑，禁止只取缓存mode；原两失败原件保留，不重置成首绿。

- 2026-10-03 完整spawn缺口已窄修：metadata/launch共同验证本次fresh render的精确guard后才分类原native命令。作者11/23/33/49项各一次通过；不同会话独审7495e1b4、8个实际消费者ACCEPT，早拒零资源、晚拒保留owned工作树/Context/authority且零终端注入。最初两红和最终有限纠错保留。真实模型/业务、wholeworker RSS/长程峰值、跨PM全局原子资源预留仍NOT_VERIFIED，不替律师IP原PM重派或解除业务泊车。
- 本轮共用验证与安装证据：archive/20261003_sequential_gates/ 保存作者失败、修复、独审、矩阵和CAS记录。维护矩阵72条：71条首次0；第59消息套件一次20s超时，原代码单例及9项整套有限复验0，不同会话核30次调用无改参数，首因NOT_CONFIRMED。其余只续跑，不称首次全绿或长期稳定。安装后由原业务PM重读当前Skill并重新消费当前任务，不能把安装等同业务解除。
- 现场只读证据：真实已安装MiniMax/原生Node/原命令bind-spawn exit0；具名资源profile真实3样本约31秒采集exit3/slots0，reason=swapouts/pageouts growth or counter rollback。kernel normal与约14.34GiB safe_available不能覆盖该稳定窗口拒绝；没有模型、终端、worktree或账号副作用。此观察不是首测试超时因果证明，也不据此改默认政策。

- 安装收口：本地既有更新上增量同步为2.36.8，20个脚本/模板与工程7495e1b4逐字节一致，保留另一原PM远端GUI三卡的并发记录和既有文档整理。Codex/Claude/.agents入口均解析同一源。公共PR仍只含本支2.34.3范围，未将本地其它版本混入。

- CI涌现项：公开head aadf04c8 的 Linux runtime-settlement 在新资源测试 step 失败，26项4fail/2error，实际理由是解释器非安全常规文件校验拒绝；本地矩阵不能替代Linux结果。沿原MiniMax卡由原作者只修CI私有Node输入，保留生产0o022拒绝，禁止chmod共享toolcache/skip测试。实际cache权限尚待现场证据，不把推断写成事实；修后独审与远端CI待。原失败run37047228045保留。

- 同一CI窄修另核现机smoke依赖：test_installed_readonly_chain_heap_no_model原来无条件读取mcode，公共runner未安装。明确仅此现场只读项在CLI缺失时报告LIVE_INSTALLED_MINIMAX_NOT_VERIFIED/skip，存在时仍严格验完整安装，畸形安装不得skip；其余22资源fixture及11完整入口照常执行。本机该项及实际绑定已通过，不自动安装CLI或登录账号。

- CI与交付闭环：工程39b1603c6420a94a09f43b474bb31e02ac3a65cf不同会话限定独审ACCEPT，runtime-settlement（37049375384）及harness-regression（37049375401）均SUCCESS。实际Linux后续运行记录Node源mode0777、私有副本0700、SHA一致，Python去父LD启动成功；26资源全执行，MiniMax23仅现场缺安装skip1，其余22及完整spawn11通过。本机26/23/11均实际执行通过。原CI失败37047228045及矩阵59首红保留。该CI补项已完成，当前状态LOCAL_SYNCED/SCOPED_ACCEPTED，原业务模型、整workerRSS和全局原子预留未验边界不变；最终文档头的自动检查以PR248当前head checks为权威，不重复维护运行状态。

## TASK-2026-10-03-ZCODE-CLOSED-SESSION-RECOVERY — 原失败Task的关闭Session恢复与回执采用

- 状态：IN_PROGRESS；唯一技术owner为本原MAO PM；实现与独审分离，沿隔离候选`fix/mao-continuation-readiness-261002`，冻结起点`fa442feea3ce0df831a1513c732111f754509ebd`。
- 来源与去重：DSH原022的`022-closed-resume-dependency-20261003.json`已由原插件PM登记；MAO现有卡未发现同一关闭Session入口合同。本卡只补公共生命周期依赖，DSH原022预算1/2、原失败Task/Session/工程成果及独立032D不变；不另建聊天或第二配置writer。
- 目标：增加原生`--retry-of`透传；关闭原Session的精确恢复入口与真实后继回执采用；收紧reauthorize只允许可证明live的目标。先证退出及旧cap撤销，再以原provider Session的`--resume`和yolo启动空业务输入会话，核具名目标模型/effort后才由原业务PM单次同failed Task retry。
- 不变量：首次启动anti-replay保持；不reset-ready、不新Task、不修改global/provider账号、不手工造capability；原始authority与初始/后继attempt历史保留，采用新回执需真实runtime/run/task/terminal/process/cap摘要核对与防重放、原子路由/完成替换及失败回滚；未知/live/身份漂移零副作用拒绝。
- 实现范围：register/protocol/completion、zcode launcher、pm-orchestrate的live预门及必要新恢复helper和定向测试。文档只更新既有ref13/14/30、TASKS/CHANGELOG/SKILL，不新增reference。
- 有界合同：技术修复最多2个失败episode、作者单窗口30分钟、独审10分钟；只跑定向套件，保留首次失败。先实现和模拟公共CLI入口正反例；真实DSH恢复/业务输入仅由其原PM执行，不由MAO抢业务。不可证明公开primitive时记录缺口而非制造能力。
- 验收：同failed Task/原Session/真实后继attempt；模型门前零业务输入；完成新绑定只认新live receipt；live/unknown、错run/task/session/model/process、旧回执重放、写入中断均拒绝；原首次启动与reauthorize相关回归通过、独立审查接受。实际DSH整链保持NOT_VERIFIED直至原PM验收。
- 首轮实施与审查（2026-10-03）：作者原30分钟窗口内冻结`cd9a6d5c33f5c2718f9cc1170b6e2dd0e7c79c5e`，新恢复15项、旧bridge35/completion19+8/reauthorize200通过；首11项中process incarnation误接纳及一次错误unittest入口ImportError完整保留。PM最终reader实际读取原022公开退出链/current owner及native SQLite模型PASS，零intent/terminal/业务mutation；不签真实恢复。
- 第二failure episode限定返修：独立12个heldout消费者确认原生retry_request空串、revoked双别名及owner generation双别名冲突3处合同不符，冻结REJECT后由原作者5分钟只修这些绑定与旧归属声明、原reviewer5分钟增量复核；保原30分钟结束事实，不另开实现队列、不重置2-episode预算。旧metadata.created归属叶目前未被cleanup直接消费，不宣称发生误删；仍需投影真实新resource来源。当前候选未安装，真实原022恢复/业务链NOT_VERIFIED。

- 增量复审收尾（2026-10-03）：最终工程`908393338da5da8f7d90dcbbeda8135e3002363f`获不同上下文限定ACCEPT；12个原heldout消费者合同不符0、4个journal消费者通过，9 owned+4 readset前后SHA一致。严格UUID透传、双别名冲突拒绝、新external归属及旧history、同新Dispatch rollback/readopt、全ORCAREG KV已独验。宿主中断前复审未落盘，接续窗口仍限5分钟；复审首KV正则漏SHA256数字的失败原件保留，仅审查正则修复后同工程复跑。
- 当前交付边界：工程与入口合同已实现、原首次bridge35/completion19+8/reauthorize200及作者修复16项通过；原022公开退出链、current owner与native BigModel/GLM-5.3/max在最终工程reader只读实测通过，零intent/terminal/业务mutation。真实原022恢复、请求计费与业务完成仍`NOT_VERIFIED`，由原DSH PM接续同Task/Session及既有预算；本卡保留IN_PROGRESS待消费者验收。证据归`archive/20261003_zcode_closed_recovery`，首失败/REJECT不覆盖。
- 静态范围：15个本地链接可达、Shell入口语法及diff格式通过；security仍基线high2/critical0，harness仍基线hard2，本次无新增该等级，不能签全Skill静态通过。

## TASK-2026-10-03-ZCODE-LINUX-SYSTEM-ALIAS — 首次启动桥的跨平台路径兼容

- 状态：DONE（跨平台入口与权限断言修复，真实Linux CI通过）。来源：PR248提交d92c241f的Linux CI 37095578596；新关闭恢复16项通过，旧首次bridge35项中28项报requests_root_missing，后续验证未运行。旧trusted_path无平台判断将/tmp和/var转换为/private，对Linux错误。
- 范围：仅zcode-orca-launcher.py的macOS系统别名判断与test-zcode-orca-launcher.py定向平台反例；不放宽符号链接/owner/mode/anti-replay检查，不重置关闭恢复原2-episode或DSH业务预算。
- 预算与验收：作者5分钟、不同上下文增量独审5分钟；只跑路径定向与既有bridge35，Linux公开CI原失败必须保留，最终工程语义独审及新提交CI证明。真实DSH业务仍由原PM。

- 实施冻结`bd642c8bfa3ee60c612dcd6946cac6db8a46b36d`，只改2文件：1个平台条件及3个新进程平台反例；原bridge35+新增3共38项通过，新增3项首红保留。不同上下文独审ACCEPT：18个路径消费者（16个明确模拟拓扑+2个真实macOS私有文件/symlink）与4个定向anti-replay通过，两文件首末SHA一致，关闭恢复其他12工程/依赖不变。实际Linux CI待本提交执行，未签DSH真实业务。

- 第二轮Linux CI 37096070166：恢复16、bridge38、completion Python19均通过；Shell completion的mode断言因BSD/GNU stat混合输出误报，实际生产权限实现未变。范围追加仅test-completion-authority.sh该权限读数的跨平台消费者；原作者/独审各3分钟限定返修，保600断言，不改生产权限、不skip，第二次Actions失败保留。

- 权限读数返修冻结`fd1edcd4f0d56297aedf83ce4ac09ed9ae4482c7`，仅测试mode读取一行。作者Shell8项通过；不同上下文限定ACCEPT，实际含空格路径的600退出0、644/640退出1，原严格断言保持。生产launcher与其余12工程/依赖SHA不变。首轮、第二轮CI失败日志完整保留，最终Linux Actions待本提交验证；本机尚未安装此候选。

- Linux实施验收（2026-10-03）：同工程提交`185f2efe9c0f20d7e77ff826e6e7087571d7a475`的[Runtime CI](https://github.com/cat-xierluo/legal-skills/actions/runs/37096479917)与[Harness CI](https://github.com/cat-xierluo/legal-skills/actions/runs/37096479903)均SUCCESS，闭合本跨平台卡；恢复16/bridge38/completion19+8/reauthorize及业务/资源入口均执行通过。保留前两轮失败，不skip失败用例。真实原DSH恢复、请求计费与长期运行继续依原卡NOT_VERIFIED，不扩大本卡验收。
