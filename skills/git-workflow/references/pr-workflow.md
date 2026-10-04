# PR 创建、审查与合并

创建、审查、合并或更新 PR 时读取本页。先满足[共同约束](../SKILL.md#共同约束)；完整历史、精确文本与例外格式只在[隐私预检](privacy-preflight.md)维护；标题和 Issue 语义见[命名格式](issue-pr-format.md)。

## 1. 创建与后验

确认授权、目标仓库、真实 PR base 和独占 head 分支；先按[身份与推送](identity-and-push.md)使用 safe-push 推送已核不可变 OID。Python 3.10+、Git 和已认证 gh 必须可用，缺失时停止，不绕过 helper。

将最终单行标题与完整正文写入仓外或 Git 管理目录的文件，再运行：

```bash
python3 "$git_workflow_dir/scripts/safe-pr.py" create \
  --base main --head '<branch-name>' --expected-head '<完整已核 head OID>' \
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
