# 长期功能线与两层 PR 迭代

## 1. 选择分支结构

默认主干保存已交付基线，短 fix/feat/test/docs 分支交付可独立验收的单项任务。具名功能跨多个子 PR 或开发波次，各子项可验收、整体尚未达到主干里程碑时，为它建立长期功能线；子 PR 先进入功能线，达到具名里程碑后再向默认主干提 PR。

Monorepo 按功能边界判断：同一模块的相关 PR 可共用功能线；彼此独立的 Skill 不因同仓就共用一条线。先建当前需要的最少功能线，新增时明确不同 owner、写域与退出条件。PR 数量多或希望暂存 WIP 本身不足以建线；短分支继续用于单项交付。

```text
默认主干
  ├─ 通用修复短分支 ── PR ──► 默认主干
  │                              └─ 波次边界 merge ──► 功能线
  └─ 长期功能线
       ├─ worker 短分支 A ── 子 PR ──► 功能线
       ├─ worker 短分支 B ── 子 PR ──► 功能线
       └─ 具名里程碑达到 ── 里程碑 PR ──► 默认主干
```

## 2. 固定建线与波次合同

在项目既有任务源固定这些字段；项目专属名、路径、SHA与审计流水不复制进通用 Skill：

| 字段 | 约束 |
|---|---|
| integration_branch / integration_target | 功能线完整名称及子 PR 的显式 base |
| default_branch | 里程碑 PR 的最终目标 |
| integration_owner / integration_worktree | 唯一集成者、固定干净 Worktree；不重复检出 |
| branch_lifecycle | 功能线 long-lived；子 worker ephemeral-worker；不由名字猜测 |
| allowed_paths | 功能写域及共享文档/CI例外；共享入口由集成者串行处理 |
| milestone / validation_requirements | 具名结果、退出条件、真实消费者、匹配CI与独立review |
| sync_policy | 无未决子PR的同步边界、漂移处置与清理授权 |
| default_base_sha / integration_head_sha | 本波真实远端完整OID；子任务不得混用旧快照 |

缺 owner、目标或里程碑时沿用普通短分支。功能线遵守默认主干同等级门禁。

## 3. 审计已有 PR 池与窄采用

1. 冻结每个PR的编号、head/base完整OID、范围、状态、依赖、review及实际checks；区分通用修复、同功能子项、未发布依赖与活跃owner候选。
2. 先处理已验通用修复，再让功能线吸收当前主干。旧PR改base后重读实际diff/checks/mergeability，旧验收不自动适用于新base。
3. 同族共享文档PR串行采用，每次合并后刷新下一候选。UNKNOWN触发有界等待重查；CI green、可合并或PR数量减少不代替验收。
4. 旧分支过大或含未验提交时，从当前目标基线新建窄采用候选。逐文件记录来源PR/head、采用文件、原受审SHA与当前字节关系；共享SKILL/version/TASKS/CHANGELOG/README/CI按当前基线增量拼接，保留其他模块与双方有效记录。
5. 工程字节相同可沿用其限定独审结论；新增组合依赖、共享文档、最终候选与CI仍须核验。摘要或patch-id不能证明整工程等价，也不能将历史失败改判成功。
6. 新候选已合入实际声明的目标、且旧PR当前head的采用/未采用范围处置完整后，才按[取代关闭合同](branch-lifecycle-and-cleanup.md)关闭旧PR。只进入功能线时如实写功能线，不能写成已进默认主干；关闭与删除分支分开核授权。

部分采用、依赖未发布或原owner仍返修时，保留候选及后续条件，不凭冲突或旧日期判过时。最终交付树的版本、入口与必要依赖必须可达，不能只存在于ignored本地任务源。

## 4. 子 worker 与子 PR

刷新远端，从本波 origin/<integration_branch> 建短分支与隔离Worktree，核起点等于冻结integration_head_sha。通过multi-agent-orchestration派发时，从其真实安装路径定位scripts/spawn-worker.sh，显式传 --base-ref origin/<integration_branch> 与 --branch-lifecycle ephemeral-worker；launcher不属于git-workflow的scripts。承载功能线的受控会话声明long-lived。

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

功能线推进期只开子PR；里程碑达到后提唯一base=默认主干、head=功能线的里程碑PR，核：

- 纳入/排除子项、真实采用关系、已满足退出条件与剩余任务；纳入子PR全部处理，范围外WIP未混入。
- 最新默认主干已在功能线历史中，最终候选可复算；绑定原独审head/文件与最终工程关系。仅证明工程等价时，另核新文档、组合行为、最终CI及发布身份，不能改旧ACCEPT为新整包ACCEPT。
- 真实代表性消费者/错误路径、匹配CI实际执行。核心缺依赖全SKIP不算验收；可选样例、历史负控与不适用SKIP分计。
- 全部路径与其他模块保留、版本索引一致；review/CI/身份/隐私门满足，base/head与预期一致。

用safe-pr.py创建与squash，最终标题/正文明确、服务端绑定精确head；事后核MERGED/mergedAt/mergeCommit及实际交付树。单样例、已发布文档或CI green不扩大为业务正确、计费、持续监测或自治能力。

里程碑合并后保留功能线，无未决子PR时把包含里程碑的最新默认主干merge回功能线再冻结下一波。如果项目授权force-reset head且意外使旧PR自动CLOSED，先核远端状态与唯一性，再决定重开/新建并更新任务指路；不自行用重置消除历史。

## 8. 收口、安装与清理

- 回写既有任务源的合并/关闭/保留清单、原失败、剩余条件及实际OID；分支策略写已有决策。实录/大原件归任务或ignored archive，reference保留通用合同。
- 本机源dirty或并发更新时，逐文件compare-and-swap接回已验文件与必要文档，保留index、既有成果和别名；云端/本机版本与调用路径分别记录，不把同源别名说成所有活跃聊天已重新加载。
- 授权交接按回执报告投递；没有消费者证据不称已采用。备份SKILL.md用.snapshot等非入口文件名，避免重复发现Skill。
- 合并/关闭与清理分开。[清理合同](branch-lifecycle-and-cleanup.md)绑定任务归属、head、真实tip、dirty/占用、settlement与精确删除授权；有交付证据也不能擅自-D或删除材料。
- 长期线及固定Worktree作为活跃基线保留；明确完成/取消、未决工作处置且取得精确删除授权后才关闭。短worker清理不触碰integration target。
- 清理失败或有意保留输出CLEANUP_PENDING / RETAINED_WITH_REASON，记录恢复动作；已交付的push/merge不重放。
