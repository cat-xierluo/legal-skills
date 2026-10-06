# Skill 里程碑迭代、观察验证与长期功能线

## 1. 选择分支结构

默认主干保存已交付基线。按本轮交付目标和持续协作需求选择分支，不能用存在几天、Skill 是否还会继续开发、PR 数量来单独判断长短。长期表示跨开发/验证轮次保留，不表示永久存在。

| 情形 | 选择 | 默认退出 |
|---|---|---|
| 一个独立修复/文档任务，做完只等测试或合并 | 短任务分支，`ephemeral-worker`；等待一周仍可保持这一类型 | 交付、现场和授权满足后按清理合同收尾 |
| 一个具名版本或能力要连续开发、试用、返修后整体交付 | 里程碑迭代线，`long-lived`；可只有一个 Agent、一个 PR | 里程碑交付后默认进入结案评估；是否删除另核 |
| 同一里程碑有多个独立 Worker 同时写不同范围 | 迭代线 `long-lived` + 必要的短 Worker 分支 | 子 PR 合入迭代线，整体达标后进主干 |
| Skill 未来可能迭代，但本轮没有明确目标 | 不预建常驻开发线 | 新需求就绪后再选择 |

同一个 Skill 持续维护，并不要求一直保留一条永远未交付的 dev 分支。跨多个里程碑确需固定集成基线时，仍用 `long-lived`，但必须有下一里程碑、owner 和复核节点；不能只填“持续优化”。单项任务变成跨轮迭代时，在原任务源显式调整生命周期和退出条件，保留原成果，不默默新开替代线。

同一 Skill、同一交付目标默认只有一条权威迭代线，固定一个集成 worktree 和一个集成 writer。单 Agent 串行开发直接在该树继续提交；换聊天、换 Agent 或做一次 review 不自动产生新分支。交接时核 owner、未提交材料和原会话；多个 writer 确需同时修改时才按互不重叠的范围开短子分支。不能把多人并行变成共用一个 worktree。

不同 Skill 默认各自按需立线；同 Skill 的并行实验线须说明不同假设、写域、owner、最终采用去向与复核时间，不能把临时对照实验自动升级成第二条权威版本线。

Monorepo 按功能边界判断：同一模块的相关 PR 可共用功能线；彼此独立的 Skill 不因同仓就共用一条线。先建当前需要的最少功能线，新增时明确不同 owner、写域与退出条件。PR 数量多或希望暂存 WIP 本身不足以建线；短分支继续用于单项交付。

```text
默认主干
  ├─ 通用修复短分支 ── PR ──► 默认主干
  │                              └─ 波次边界 merge ──► 功能线
  └─ 长期功能线
       ├─ 单 Agent：在固定隔离树连续提交、验证和返修
       ├─ 多 writer 时：worker 短分支 A ── 子 PR ──► 功能线
       ├─ worker 短分支 B ── 子 PR ──► 功能线
       └─ 具名里程碑达到 ── 里程碑 PR ──► 默认主干
```

新分支命名统一见 [命名合同](issue-pr-format.md#分支名称先看角色再看-skill-和目标)，使用 `milestone/<skill>/<goal>` 显示里程碑身份；父子 PR 的创建、目标与关闭统一见 [PR 路径](pr-workflow.md#0-按分支角色确定-pr-路径)。已有不符合新名称的活跃线按原任务继续，不为了外观再开一条替代线。

## 2. 固定建线与波次合同

在项目既有任务源固定这些字段；项目专属名、路径、SHA与审计流水不复制进通用 Skill：

| 字段 | 约束 |
|---|---|
| integration_branch / integration_target | 功能线完整名称及子 PR 的显式 base |
| default_branch | 里程碑 PR 的最终目标 |
| integration_owner / integration_worktree | 唯一集成者、固定干净 Worktree；不重复检出 |
| branch_lifecycle | 里程碑/跨里程碑线 long-lived；单任务/子 worker ephemeral-worker；不由名字或天数猜测 |
| allowed_paths | 功能写域及共享文档/CI例外；共享入口由集成者串行处理 |
| milestone / validation_requirements | 具名结果、退出条件、真实消费者、匹配CI与独立review |
| sync_policy | 无未决子PR的同步边界、观察候选漂移处置与清理授权 |
| phase / next_review_at | 开发、观察验证、待交付、暂停或已交付；具名下一次复核时间，不自动创建定时任务 |
| candidate_oid / validation_scope | 观察时固定的完整 OID、依赖/运行配置、验证范围与证据位置 |
| delivery_pr / continuation | 已获发表授权时的唯一主干 PR；本轮结束或具名下一里程碑 |
| default_base_sha / integration_head_sha | 本波真实远端完整OID；子任务不得混用旧快照 |

复用项目既有 TASKS/任务卡作为权威来源；项目级总览只链接对应任务，不复制维护另一套状态。至少能回答“当前在哪条线、谁在写、什么要交付、测的是哪个候选、何时再看、如何退出”。已有一次性任务不为填表强行立长期线；长期线缺 owner、目标或里程碑时保持草案，先补边界。功能线遵守默认主干同等级门禁。

`phase` 是验证/交付状态，独立于 `branch_lifecycle`：短分支和长期线都能处于观察验证。沿用 `ephemeral-worker` / `long-lived` 两个现有枚举，不发明清理工具尚不认识的第三种生命周期；本页新增字段是任务记录要求，不表示现有脚本已能自动读取和强制执行。

## 3. 审计已有 PR 池与窄采用

1. 冻结每个PR的编号、head/base完整OID、范围、状态、依赖、review及实际checks；区分通用修复、同功能子项、未发布依赖与活跃owner候选。
2. 先处理已验通用修复，再让功能线吸收当前主干。旧PR改base后重读实际diff/checks/mergeability，旧验收不自动适用于新base。
3. 同族共享文档PR串行采用，每次合并后刷新下一候选。UNKNOWN触发有界等待重查；CI green、可合并或PR数量减少不代替验收。
4. 旧分支过大或含未验提交时，从当前目标基线新建窄采用候选。逐文件记录来源PR/head、采用文件、原受审SHA与当前字节关系；共享SKILL/version/TASKS/CHANGELOG/README/CI按当前基线增量拼接，保留其他模块与双方有效记录。
5. 工程字节相同可沿用其限定独审结论；新增组合依赖、共享文档、最终候选与CI仍须核验。摘要或patch-id不能证明整工程等价，也不能将历史失败改判成功。
6. 新候选已合入实际声明的目标、且旧PR当前head的采用/未采用范围处置完整后，才按[取代关闭合同](branch-lifecycle-and-cleanup.md)关闭旧PR。只进入功能线时如实写功能线，不能写成已进默认主干；关闭与删除分支分开核授权。

部分采用、依赖未发布或原owner仍返修时，保留候选及后续条件，不凭冲突或旧日期判过时。最终交付树的版本、入口与必要依赖必须可达，不能只存在于ignored本地任务源。

## 4. 子 worker 与子 PR

只有确需并行写入或独立子项交付时才开子 Worker 分支；单 Agent 不强制套两层 PR。刷新远端，从本波 origin/<integration_branch> 建短分支与隔离Worktree，核起点等于冻结integration_head_sha。通过multi-agent-orchestration派发时，从其真实安装路径定位scripts/spawn-worker.sh，显式传 --base-ref origin/<integration_branch> 与 --branch-lifecycle ephemeral-worker；launcher不属于git-workflow的scripts。承载功能线的受控会话声明long-lived。

完整子PR range的身份/隐私base是真实功能线，PR base也须相同：

```bash
# 在worker Worktree中；变量来自本波合同，helper指向git-workflow安装目录
bash "$git_workflow_dir/scripts/safe-push.sh" \
  --base "origin/$integration_branch" --remote origin --branch "$worker_branch" \
  --expected-name "$expected_name" --expected-email "$expected_email"
verified_head=$(git rev-parse HEAD)
python3 "$git_workflow_dir/scripts/safe-pr.py" create \
  --base "$integration_branch" --head "$worker_branch" --expected-head "$verified_head" \
  --title-file "$title_file" --body-file "$body_file"
```

独立审查、真实产物/行为验证、最终head的CI和主Skill门禁满足后才转ready，用safe-pr.py squash合入功能线；事后读MERGED/mergedAt/mergeCommit，不凭退出码或作者自报收口。

### squash 重做与冲突

squash后相同树可能有不同提交身份与祖先，使再次集成冲突；先看共同基线、双方diff与最终采用范围。保留双方当前有效内容，按文件解决并复验；禁止默认 checkout <旧树> -- .、git add -A，或忽略merge失败后继续发布。完整树等价只在合同明确要求等价时作为验收条件，不能借此丢掉目标侧已前进成果。

## 5. 变更流向

| 变更 | 路径 |
|---|---|
| 单项通用修复/基础能力 | 短分支 → 默认主干 → 波次边界同步功能线 |
| 功能线专属子项 | worker短分支 → 功能线 |
| 已满足里程碑的集合 | 功能线 → 默认主干 |

通用修复优先拆独立PR；不能安全拆分时固定在功能线里程碑范围内，不能分别实现相同patch到两侧。Monorepo禁止本地feature→main直接merge；默认主干merge到功能线是本节同步方向。实际采用仍核范围、全仓其他模块、敏感文件与版本索引，不整目录覆盖旧基线。

## 6. 波次同步与冻结

1. 刷新两端远端tip，核固定Worktree干净、唯一writer与open子PR名单。未决子PR先处理或明确重新安排，不在其base下移动功能线。
2. 冻结两tip、共同基线、同步范围与预期结果。将最新默认主干普通merge到功能线，保留双方历史；不rebase/force/reset或重建同名功能线。
3. 每项核真实exit；冲突或断言失败后停止后续add/commit/push。按具名文件解冲突，保留双边有效内容及其他模块；结果变化后复验受影响消费者。
4. 本机新增提交仍走完整身份/隐私门，绑定真实目标、完整范围、最终message和待发表OID；不得用较近任意commit隐藏早期污染。
5. 核远端新head、固定Worktree及最终树；冻结下一波default_base_sha/integration_head_sha再派发。任一端、owner或未决PR漂移使旧快照失效，重新核验。

### 观察验证：固定“正在测的版本”

可用于短分支，也可用于里程碑迭代线。观察窗口由任务的真实使用频率和风险决定；一周、两周只是计划，不是自动达标时间。进入观察前，必须先把应验证的改动提交，并完成相应基础检查。

1. **固定候选和证据范围**：记录完整 candidate OID、Skill/脚本/引用与必要依赖、模型/runtime/关键配置、输入类型、成功标准及原始证据位置。只写分支名或版本字符串不足以绑定被测内容。
2. **隔离试用入口**：在专门测试工作区或任务级安装目录使用固定候选；由宿主明确选中该入口，并核实际加载路径、内容指纹和必要的重载/新会话。共享全局入口继续使用已采用主干/稳定快照，不为了试用把所有 Agent 的链接指向开发树。多端部署行为继续沿各自安装 Skill；Git 规则不虚构统一开关。
3. **覆盖真实使用**：预先列代表性正常输入、材料不足/异常输入、历史失败回归，以及依赖 Agent 理解时的无旧上下文执行；保存实际输出、失败与返修记录。样本数量和时间须匹配任务目标，不把少量例子或自然经过七天叫作“稳定”。期间没发生真实运行，结论就是未验证。
4. **返修与并行开发**：修复后产生新 OID，旧证据仍归原候选。评估变动涉及的脚本、指令、依赖、运行配置和验证范围，重跑受影响检查；未受影响证据沿用须说明字节/依赖关系。影响观察目标的变更重新开始对应观察范围；纯说明修订也须有影响判断，不能一律重算全部天数或自动豁免。主开发线要继续下轮时，用固定只读快照或专用验证 worktree 保留被测版本，按原稀疏与预算合同核必要依赖，不能持续跟随移动的 HEAD。
5. **到期判定**：满足退出标准且无阻塞问题才进入待交付；暴露缺陷回开发；样本不足则延长并写原因/下次复核；暂不推进标暂停并保存成果。到期不自动合并，也不自动删除。暂停不等于无人负责。

主干必要修复在波次边界同步；最终交付前若同步改变被测范围，重新核最终候选。不能为保留“测试了一周”的说法而忽略最新基准冲突，也不能让日常同步不断悄悄替换观察版本。

例如：一次 FAQ 修订只有一个交付项，即使排期一周后试讲，也仍可用短分支；一个课程生成流程重构需多轮真实输入与返修，可用一条里程碑线保留两周，期间多次 commit，无需每次反馈新建分支。是否达标由该任务记录的证据决定，示例时长不是门槛。

### 已发布 GitHub squash 与本机身份不同

里程碑squash后，旧功能线提交仍可能在origin/main..HEAD中；GitHub author/committer与本机期望不同会使当前严格身份门拒绝。这不自动证明陌生作者污染，也不授权放宽门禁。保留拒绝、实际两端身份与合并回执，不改旧署名、不伪装GitHub committer、不任意扩大白名单。

对两个已发表且分别已验的tip，项目明确授权波次同步且保护允许时，可以由GitHub正式执行默认主干→功能线合并：

1. 核两tip的真实远端ref、merge回执或独立发布记录、可读历史、共同基线及零未决子PR；核原工程接受范围，不仅看GitHub用户名。
2. 对共同基线→每个tip的全部message/patch/blob及精确最终合并message做身份归属与隐私复核，不仅看净diff。两侧非祖先不能硬塞给safe-pr.py，后者会拒绝；分别复核两条真实可枚举范围并保存读集/结果。
3. 在隔离候选用 git merge-tree --write-tree 预演预期树（可写对象但不改检出或 index）；冲突、缺历史或身份不能绑定时保留SYNC_PENDING。[GitHub merge API](https://docs.github.com/en/rest/branches/branches#merge-a-branch)的base为目标分支、head为已验完整主干OID、message为已检字符串；没有expected-base原子条件，依靠独占writer、发送前重核及后验，不能声称消除竞态。保护要求PR、禁止该路径或工具拒绝时，不解除保护或admin绕过。
4. 成功后核真实ref/OID、parents、message与预期树。204表示已合并，仍核真实祖先/树；异常或回执不符先只读对账，不盲目重试。一轮真实merge只证明本次同步，不签所有场景或长期稳定。
5. 固定Worktree普通merge或ff接收真实结果，保留先前未发表尝试；仍有本机新增提交时，以已核且已发表的真实目标tip检查完整本机增量后safe-push，不能用自建ref、同名feature upstream或未验提交缩窄范围。最后重新冻结波次。

此路径只同步已发表历史，新功能仍经子PR进入功能线。服务端合并提交可按[身份与推送](identity-and-push.md#已合并历史的服务端回执)运行 identity-audit.sh receipt 精确核本仓回执；不替代整波同步、保护与等价门禁。[git-merge-tree官方说明](https://git-scm.com/docs/git-merge-tree)支持合并预演（可写对象但不改检出或 index），不替代行为验收。

## 7. 里程碑 PR 与证据

同一里程碑向默认主干只保留一个有效交付 PR。已获发表授权且需要提前审阅时可开 Draft，持续更新同一 PR；也可到里程碑达标再创建，不因每次返修重复开 PR。Draft 只表示待交付，不授权合并；所有已发表增量仍走完整身份/隐私门。并行子项的 PR 以功能线为 base。

进入 Ready/合并前，核唯一 base=默认主干、head=功能线的里程碑 PR：

- 纳入/排除子项、真实采用关系、已满足退出条件与剩余任务；纳入子PR全部处理，范围外WIP未混入。
- 最新默认主干已在功能线历史中，最终候选可复算；绑定原独审head/文件与最终工程关系。仅证明工程等价时，另核新文档、组合行为、最终CI及发布身份，不能改旧ACCEPT为新整包ACCEPT。
- 真实代表性消费者/错误路径、匹配CI实际执行。核心缺依赖全SKIP不算验收；可选样例、历史负控与不适用SKIP分计。
- 全部路径与其他模块保留、版本索引一致；review/CI/身份/隐私门满足，base/head与预期一致。

用safe-pr.py创建与squash，最终标题/正文明确、服务端绑定精确head；事后核MERGED/mergedAt/mergeCommit及实际交付树。单样例、已发布文档或CI green不扩大为业务正确、计费、持续监测或自治能力。

里程碑合并后先判断是否续线。默认本轮完成就进入结案评估，不因 Skill 未来还会开发而无限保留活跃线；下一次独立目标可从当时最新主干立新线。确需跨里程碑继续时，必须写明下一里程碑、owner、写域、未决工作与复核时间；无未决子 PR 时再把包含里程碑的最新默认主干 merge 回原功能线并冻结下一波。此处结束/续线判断不授权删除，资源处置继续沿清理合同。如果项目授权force-reset head且意外使旧PR自动CLOSED，先核远端状态与唯一性，再决定重开/新建并更新任务指路；不自行用重置消除历史。

## 8. 收口、安装与清理

- 回写既有任务源的合并/关闭/保留清单、原失败、剩余条件及实际OID；分支策略写已有决策。实录/大原件归任务或ignored archive，reference保留通用合同。
- 本机源dirty或并发更新时，逐文件compare-and-swap接回已验文件与必要文档，保留index、既有成果和别名；云端/本机版本与调用路径分别记录，不把同源别名说成所有活跃聊天已重新加载。
- 授权交接按回执报告投递；没有消费者证据不称已采用。备份SKILL.md用.snapshot等非入口文件名，避免重复发现Skill。
- 合并/关闭与清理分开。[清理合同](branch-lifecycle-and-cleanup.md)绑定任务归属、head、真实tip、dirty/占用、settlement与精确删除授权；有交付证据也不能擅自-D或删除材料。
- 观察中、有未决子 PR 或具名下一里程碑的长期线及固定 Worktree 保留；本轮完成且无续线条件时进入结案评估，未决工作处置且取得精确删除授权后才清理。结束开发、移除 worktree、删除本地/远端 ref 分别核定；短 worker 清理不触碰 integration target。
- 清理失败或有意保留输出CLEANUP_PENDING / RETAINED_WITH_REASON，记录恢复动作；已交付的push/merge不重放。
