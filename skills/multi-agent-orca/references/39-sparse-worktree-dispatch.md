# Worker 稀疏检出与磁盘预算

Git 创建方法、根规则保留、ignore/配置/历史边界统一读取 [git-workflow 稀疏工作树合同](../../git-workflow/references/sparse-worktree.md)。本页只维护 PM 的派发职责，不复制 Git 命令实现。同仓链接用于阅读跳转；独立安装时通过宿主 Skill 发现机制解析 `git-workflow` 的实际安装路径，读取其 references/sparse-worktree.md。该 Git 入口是可选开发依赖；缺失时不能假称已采用其脚本或自动改用全仓。

## 1. 资源创建前完成范围选择

- Monorepo 单 Skill/单套件默认要求稀疏；跨 Skill 列出每个实际依赖，不能因“可能用到”选整个 `skills/`。先读取任务输入、验证命令和相对引用，核对共享脚本、manifest/锁文件、fixture 与验证器所在目录；套件含符号链接时列出实际成员目录，不能只检出链接外壳或复制其他树补材料。仓库外依赖沿既有安装/共享配置合同处理，不自动跟随链接读取私有内容。
- 在既有完整任务卡/PM 派发计划记录下表；脚本只机械检查下文列出的字段，其余仍是 PM 准入证据。不得向外部 CLI/Task spec 塞入未支持字段。
- 对 read-only 依赖明确只读；checkout 范围不替代 allowed/forbidden files、scope hook 或任务写入授权。共享 README/版本/锁文件继续由指定集成者串行维护。
- 先盘点可复用的适用树及已核准可清理的旧树；在完整任务源记录结果，复用仍须满足原 owner 与借用合同。估算本波新增检出文件、独立 index、依赖/缓存/验证产物和必要备份，核创建路径所在卷的当前剩余空间与项目余量。预算缺失、探测失败或空间不足时停在资源创建前；额度/CPU/内存 slots 不证明硬盘够用，不能为腾空间自行删别人的资源。

| 准入事实 | 要求 |
|---|---|
| 任务与归属 | 原任务 ID/任务卡、PM、资源 owner、预计生命周期 |
| 创建/复用路径 | 受监管模式、实际入口与当前版本/help/schema、目标仓库与路径 |
| 检出模式 | 新建 sparse、具名例外 full，或复用树及其实际 sparse/full 状态 |
| 范围与权限 | 目标目录、各依赖目录及用途/读写授权、验证命令需要的材料 |
| 基准 | 明确 base ref 与完整冻结 OID；分支/HEAD 的启动验收预期 |
| 规则与配置 | 根规则来源、未跟踪规则的合法交接、ignored 配置/共享目录物化方式 |
| 磁盘 | 估算依据、本波新增占用、当前可用空间、项目余量与检查时间 |
| 例外及结论 | 全量原因/选择依据（若适用）；准入或停止的理由与下一动作 |

### 全量例外不能由通道缺口自动生成

以下两类全量选择可以成立，但必须在资源创建前具名记录，并符合用户/项目当前授权：

1. 任务本身需要全仓集成或跨模块迁移，写清哪些输入/验证使窄范围不足。
2. 当前要求的受监管通道不能稀疏创建，核过可用入口后，用户/项目已有规则或本任务的明确选择允许全量代价；记录该选择来源、能力证据、替代路径不适用原因与预算。仅“CLI 没参数”“先跑起来”“任务已授权”均不足。

用户禁止全量时任何例外都不适用。没有合法例外且不能证明该入口在首次检出时限定范围，就在 Wave/Run/Task、lease、worktree、terminal 和 Agent 副作用前停止，原卡记 `PARKED_FOR_CHECKOUT_CAPABILITY` 并给出所缺能力、具名 owner 和下一动作；本机检出计划入口以该诊断退出 64，不写入 Orca 状态枚举。单卡停止不阻塞其他已准入的独立卡，不重造任务或改通道绕过原合同。

full 只决定文件检出，不自动批准全量 test/build。实施 worker 沿 scoped 自验；具名全仓集成验收任务可以使用专门验证 worker，仍按主入口 §3.1.6 / §5 核独占、预算与有界输出。

## 2. 保持运行通道与启动顺序

- 先读取当前 `orca-cli` 指南与 `worktree create --help`。2026-10-04 核对版本有 GUI 稀疏预设，CLI 创建没有目录参数；后续版本以实际帮助为准。
- 无论使用何种已支持的创建入口，Agent 开始处理业务前先核真实目录/HEAD、所需规则与依赖，再设置 Session Context、安装/scope 门禁和监督身份。继续遵守既有 `--setup skip` 与禁止提前 `--agent` 启动的顺序。
- 原生 Git 稀疏创建入口可用于普通隔离开发；不能自动变成 Orca supervised worker。要复用已创建树，必须先满足 [既有树借用合同](31-borrowed-existing-worktree.md) 和当前通道的身份、门禁、收尾条件；借用入口的 backend/模式限制继续生效，不向不支持的 Claude/Codex 路径套借用参数。不能裸启 Agent、伪造 Run/Task/Dispatch 或双投。稀疏树借用到正式监督链的端到端接线仍 NOT_VERIFIED。
- `spawn-worker.sh` 在 Orca 自动注册、额度/lease及资源创建前调用 `checkout-plan.py`；原生 Git sparse 路径调用 `git-workflow` 创建器，首次使用 no-checkout。Orca CLI 尚无已验首次 sparse 入口，计划要求 sparse 时前置拒绝，不静默切换通道或全量。GUI 有预设不证明 CLI 自动继承，Codex 工具仍不能接受未声明 scope。
- 创建后、Session/依赖物化/terminal 前机械核冻结 HEAD，sparse 另核列表；现有 isolation pregate 继续核 branch/path。目标文件、根规则、符号链接真实依赖与宿主实际落盘卷仍由 PM 检查。完整原生监督或 GUI 稀疏启动尚未实测，不以隔离 Git/helper 通过签其端到端完成。

### 已支持的本机参数

- `--checkout-scope DIR`：重复声明仓库相对目标和只读依赖，中文/空格作为一个参数。未声明时只从明确的 allow-paths 识别业务 Skill 根；没有可证明范围时拒绝，reviewer 的 Session 写范围不能用来推断被审 Skill。
- `--checkout-budget-mib N`：默认 512 MiB；按所选 blob 的文件块估算并加 32 MiB 完整 index/元数据余量，检查源仓卷余量。它是检出计划，不包括安装、缓存、产物、备份，也不能证明跨卷宿主真实路径够用；PM 仍核真实创建卷及本波余量。
- `--full-checkout-reason TEXT` 与 `--full-checkout-source TEXT`：两项同时填写，不能与 checkout-scope 混用；必须符合上文具名全量例外，不能用含糊来源追认全量。
- `--no-orca-mode` 是明确选择原生 Git/tmux 通道，不能为了绕过用户要求的监督而偷偷追加。Git 创建器缺失时停止，不复制其实现或退回全量。
- `METADATA.json.checkout` 记录模式、范围、冻结 OID、估算、预算和 full 来源；它不扩张写权限。借用树继续执行原 owner、无 writer、新 Session 和保护账本合同，计划只能核其实际 sparse 范围与仓库/HEAD。

Wave manifest 在 `project` 声明项目路径；每个 task 的 `checkout` 可提供 `base_ref`、`scopes`、`budget_mib`，合法 full 时提供 `full_reason/full_source`，合法借用时提供 `borrowed_worktree`。Skill 项目缺范围或首次能力时，在 Run/Task 创建前拒绝整次 prepare；移出不准入卡后只准备其余独立卡。旧 manifest 未声明项目时仅沿调用者的实际 Git 仓库检查；非 Git 调用目录无法证明目标，前置拒绝 `CHECKOUT_WAVE_PROJECT_REQUIRED`。显式非 Git 项目只表明没有 Git worktree 检出，不替代监督或轻量模式准入。隐藏目录下的 Skill 同样适用默认规则。

## 3. 验证与收尾

创建后、Agent 启动前按 Git 合同核实际仓库/路径/分支、冻结 HEAD、sparse 配置与 `sparse-checkout list`、目标/依赖/根规则实际存在、代表性范围外目录未落盘；full 则核准入中的例外和预算。新树在写 Session Context 前核 status 干净；之后核新增只来自已声明的脚手架/配置，不将正常 checkpoint 当作检出失败，也不忽略非预期改动。借用树按原合同保留允许的现场基线，不用“为通过验收”覆盖或 stash 成果。把事实写入原任务证据；任一不符即停止 Agent 启动，保留精确创建账目，按原恢复合同处理，不取消 sparse 补救。

Worker 启动时只复核 PM 已批准的模式、路径与所需材料；不自行修改检出定义。缺依赖时回报所缺目录、被阻断命令与用途，由 PM 核职责/权限后最小追加，并复查 HEAD、范围、规则与异常改动；沿同任务继续，不另投新 Worker。若实际必须全量，重新走例外选择，不能让 Worker disable sparse、全量 restore/reset 或复制其他树。安装、缓存、ignored 私有配置的物化另核，不能用“本来 ignore 了”推断没有落盘。

PM 将启动后所需只读核验命令纳入该 backend 的合法 Shell 合同；无读取/执行权限时 Worker 报告 PM，不用包装命令绕过 hook 或把缺权限误判为缺目录。这些复核仍不能替代资源创建前的准入与启动前检查。

启动新 worker 不顺手改造其他旧树。旧树收缩的 owner、dirty/在途保护和 ignored/untracked 备份统一依 Git 合同；仅 `git status` 干净或宿主 inactive 不证明可改造。监督身份未知时保持原现场，不以空间收益取消生命周期保护。

结束时按原资源退出/精确 Git 清理合同处理；sparse 不放宽 dirty、ignored 材料备份、长期线保留或精确 tip 条件。不得把“少占空间”写成“可以直接删”。
