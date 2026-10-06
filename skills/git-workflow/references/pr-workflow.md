# PR 创建、审查与合并

创建、审查、合并或更新 PR 时读取本页。先满足[共同约束](../SKILL.md#共同约束)；完整历史、精确文本与例外格式只在[隐私预检](privacy-preflight.md)维护；标题和 Issue 语义见[命名格式](issue-pr-format.md)。

## 0. 按分支角色确定 PR 路径

先读 [分支命名](issue-pr-format.md#分支名称先看角色再看-skill-和目标)，再核任务合同中的实际角色与完整目标；名称和目标冲突时先对账，不能只靠前缀选 base。

| 分支角色 | 创建与更新 | Ready / 合并门槛 | 交付后的去向 |
|---|---|---|---|
| 独立短任务 | 同一任务、同一目标复用一个有效 PR，base 为声明主干；默认 Draft，已验且授权满足再转 Ready | 本项范围、实际验证及本页通用门禁满足；短不等于免验 | 证明交付后按清理合同处理短分支/树 |
| 里程碑短子任务 | base 为完整父里程碑分支；正文关联父任务/已有父 PR，不能默认 main | 本子项独立验收；进入父线不代表整体可发布 | 子任务可独立收尾，父线及其树继续保留 |
| 里程碑整体 | 首个可审阅提交出现且已有发表授权时，建议开唯一 Draft 主干 PR；返修持续更新同一 PR | 里程碑范围、观察证据、最终候选及通用门禁全部满足，才转 Ready/合并 | 核主干交付及本机稳定入口，再判结案或具名下一里程碑；删除另核 |

不提交空 PR 来占位，不因换会话或每轮返修重复建 PR；第一次网络返回不明先查同一 head/base/任务的已有 PR。父 PR 尚未创建时，子 PR 关联真实父任务与完整父分支即可，不伪造 PR 编号。同一短任务直接交付两种目标确有 backport 等需求时，分别记录目标和采用关系，不能把重复 PR 当作默认迭代手段。

### 正文应让接手者能直接判断

沿用下一节的摘要、验证、归属与来源要求，再按角色补足：

- 所有 PR：分支角色（独立任务/里程碑子任务/里程碑整体）、实际目标、允许范围与不包含的内容。结论对应当前 head，不把旧版本通过沿用成新 head 通过。
- 子 PR：父任务/父分支/已有父 PR，自己交付什么、还有哪些依赖，子项完成是否影响父线观察候选。
- 里程碑整体：纳入与排除子项、固定观察候选与最终 head 的关系、实际运行/失败/返修证据、尚未验证的范围、下一复核节点，以及本轮完成后结案还是继续下一目标。无证据时保持 Draft；约定一周到期不等于自动 Ready。

任务源维护当前阶段与 owner，PR 描述保留本次交付说明和对应证据链接，不复制全量内部任务流水。字段要求是协作合同，不表示 safe-pr.py 已能机械校验这些语义。

### 合并、关闭、删除分别判断

- **合并**表示已通过审查并交付到实际 base。子 PR 合入父线只结算该子项；父里程碑未整体达标时继续保留，不能报已进入 main。
- **关闭但不合并**适用于取消、被取代或决定不采用；需已获关闭授权，说明原因、替代 PR（如有）及未采用成果去向。因等待观察、暂时冲突或超过计划日期，不自动关闭。取消的观察记录和失败证据保留。
- **删除分支/工作树**是另一次资源处置，沿 [生命周期合同](branch-lifecycle-and-cleanup.md)核当前 tip、交付、dirty/ignored/占用与授权。合并默认不带 delete-branch；关闭 PR 不等于允许删未交付成果。删除失败记 CLEANUP_PENDING，不重放已完成合并。
- **里程碑结案**先核实际主干结果、交付范围内共享加载入口的采用（如适用）和剩余工作，再选择结束或具名续线。没有下一目标不无限维持“活跃”状态，但结案标记也不能跳过删除门禁。远端交付、本机采用和资源清理分别记录。

## 1. 创建与后验

确认授权、目标仓库、真实 PR base 和独占 head 分支；先按[身份与推送](identity-and-push.md)使用 safe-push 推送已核不可变 OID。Python 3.10+、Git 和已认证 gh 必须可用，缺失时停止，不绕过 helper。

将最终单行标题与完整正文写入仓外或 Git 管理目录的文件，再运行：

```bash
python3 "$git_workflow_dir/scripts/safe-pr.py" create \
  --base '<已核真实目标分支>' --head '<branch-name>' --expected-head '<完整已核 head OID>' \
  --title-file '<最终标题文件>' --body-file '<最终正文文件>'
```

默认 draft，不用 `--fill` 或自动拼接未经核验的历史说明。创建后立即检查返回 URL、head/base、完整标题正文及状态；宿主要求附加 PR 到任务时使用其原入口。API 创建没有原子 head 条件，后验失败或网络结果不明时先只读确认，不能盲目再建。

PR 正文最低要求：摘要、实际测试及未验原因、Agent 归属（如适用：ID/作者/触发来源）、关联 Issue 或项目任务。迁移、删除、权限、安全、跨模块变更补风险与回退方式；缺摘要或测试计划不 approve，Agent 归属缺失先补齐。

提 PR 前可在独占候选运行 `bash "$git_workflow_dir/scripts/pre-worktree-check.sh" --pre-pr <branch>`，以 Git 2.38+ 的 `merge-tree --write-tree` 预演 base/head 冲突；该 helper 会 fetch，merge-tree 可写对象但不改检出或 index。本地预演干净不代替创建后的真实 mergeable 和最终 CI 后验。

## 2. 审查与隔离验证

外部贡献先核需求来源和项目契合度（Issue、任务源、路线图或核心用途），再投入代码深审。需求证据缺失时保留待讨论，不自动关闭或发送评论；用户已授权处置时才执行。项目答案不能从“代码看起来正确”推断。

读取完整 diff 和文件清单，核与声明范围一致；Monorepo 不带入无关目录、未解释的大量删除、敏感配置或无法关联的 lock/schema/迁移/生成物，版本与索引须一致。

本地测试优先复用适合的隔离树，不能在共享主源 `gh pr checkout`。新树先核真实 PR head 与所需范围；Skill/套件按[稀疏合同](sparse-worktree.md)从创建时控制检出，不先全量落盘。原主树有 merge/rebase/dirty 时保留原归属，不为审查他人 PR 自行 abort/reset。

验证错误与 PR diff 对不上时，核实际 root、HEAD、环境和残留状态，在独立候选复跑再归因。不默认链接共享 node_modules 或重新安装依赖；存在项目明确复用方案时核可写性和测试副作用。本人创建的试验按其归属完成或安全中止，记录真实结果。

## 3. 合并前门禁

以下查询用于只读核对，不能替代独立 review 和实际测试：

```bash
gh pr view '<N>' --json title,state,isDraft,mergeable,reviewDecision,headRefOid,headRefName,baseRefName
gh pr diff '<N>' --name-only
gh pr diff '<N>'
gh pr checks '<N>'
```

任一条件不满足则停止：

- PR 是 OPEN 且非 draft；在授权和验收满足后转 ready。
- mergeable 明确可合并，完整 diff 可读，范围与删除解释已核。
- 独立 review 有明确 verdict，分支保护和 required checks 满足；CHANGES_REQUESTED、结论矛盾或只有摘要均未通过。
- 最终 head 的 checks 明确通过。失败、等待、未知或读取失败不合；仓库明确无需某项检查时核实际保护与项目合同，不能把缺失自行判 PASS。
- 当前 head/base、实际验证、最终完整文本与受审候选相同；候选变化后复验。

GitHub 不允许作者自 approve。仓库无需 GitHub approval 时可使用真实不同角色、绑定当前候选的独立审查；保护要求他人 approval 时按规则满足，不使用 admin override。

## 4. 精确合并与收口

授权、review、CI 和范围门均满足后使用：

```bash
python3 "$git_workflow_dir/scripts/safe-pr.py" squash --number '<N>' \
  --expected-head '<完整已审核 head OID>' \
  --title-file '<最终 squash 标题文件>' --body-file '<最终 squash 正文文件>'
```

最终标题包含 `(#N)`（已有不重复），API 自定义标题不会自动加编号；当前 PR 标题/正文、每笔历史与最终 squash 说明都须精确检查。helper 的 head 绑定不代替 review/CI/授权。其他合并方法/API 也检查相同范围及最终文本，不能依赖自动生成说明。

用户明确要保留多个原子 commit 时按原意选择合并方法，仍满足所有门禁，不强制 squash。所谓“把 PR 拉进 main”默认核正式服务端交付；不得用 fast-forward pull 代替 PR 来源记录和验收，也不能把 CLOSED 称为 MERGED。本地采用遵循[改动集成](change-integration.md)。

完成后读取真实 `MERGED`、`mergedAt`、`mergeCommit` 和目标侧内容。main 被另一树占用或 cleanup 报错时先对账，区分云端合并、本机待同步与清理失败；不切换/删除别人的树，不重放已完成合并。[生命周期合同](branch-lifecycle-and-cleanup.md)维护清理、批量验收与取代旧 PR 的授权和覆盖关系，合并默认不附删除参数。

## 5. base 落后、冲突与未知状态

创建后立即读取 `mergeable/mergeStateStatus/baseRefName/headRefName`，不要等待下一轮才发现过期基准。MERGEABLE/CLEAN 仅表示无合并冲突，仍须 review/CI；UNKNOWN 不等于只是 CI 慢，先查服务端计算、权限与检查状态。

| 场景 | 处理 |
|---|---|
| BEHIND、无内容冲突 | 核原 head owner、项目同步策略及授权，再更新 base；不能盲目 update-branch |
| 共享文档冲突 | 保留双方有效记录，串行分配版本/编号，按文件解决；未发表短分支可按项目策略 rebase，已发表历史须另核授权 |
| 代码冲突或旧候选带入无关差异 | 按授权在最新目标开隔离窄采用候选，保留原 PR/分支及来源映射；覆盖和未采用处置完成后按取代合同关闭 |
| 少量集中冲突 | 按文件解决，核最终 message/patch/blob；网页处理同样核发布文本、实际服务端结果和候选 |

长期功能线只在波次边界 merge 主干，不 rebase/reset/force。冲突不自动授权关 PR、删分支、重建同名 head 或裸 force push；safe-push 当前不支持 force，拒绝时保留成果按已授权路径处理。

## 6. 项目扩展

文档体检等扩展仅沿项目已有接口及授权衔接。其阈值、状态、可改目录、维护 PR 与调用时机归项目维护；不因 PR 创建/合并自动授权新任务、消息或外部写入，不能替代本页门禁。
