# 范围采用、回补与冲突处理

本页管理 Monorepo 窄采用、cherry-pick、误删与锁文件冲突；PR 发表和合并门禁由[PR 流程](pr-workflow.md)维护，长期线同步由[功能线合同](long-lived-integration-branch.md)维护。

## 1. 目标与分支

普通短分支以最新远端默认目标为基准；已声明功能线的 worker 从最新远端功能线创建，显式使用该 PR base。先复用适合的隔离现场，刷新所选 ref，保留原源 dirty/本地独有提交；[本地 SOP](local-worktree-sop.md)维护基准检查。

分支按任务语义使用 `feat/`、`fix/`、`docs/`、`research/`、`refactor/` 或 `chore/` 加简短描述，不使用 tmux/subagent/team 等本地执行来源前缀。Session 与 worktree 名由宿主/编排层管理，不代替分支或基准身份。

## 2. Monorepo 窄采用

禁止在本地直接 feature→main merge；旧基线和整目录替换可能带入其他模块变化。先核用户授权、隔离目标现场、真实文件清单与当前目标差异。目录整树只有在全部内容已验且目标侧差异已对账时可采用；旧目录含过时或未验内容时只采用精确文件/增量 patch。

在已准备好的干净隔离短分支内，按核定清单采用：

```bash
# 文件清单经过与当前目标逐项对账；不在共享 dirty 主源执行
git restore --source='<候选 OID>' -- '<已核文件>'
git diff -- '<已核文件>'
git add -- '<已核文件>'
git diff --cached --stat
git diff --cached
# 核身份与最终说明后按命名合同提交，走 safe-push / safe-pr
```

共享文档保留双方有效内容，不用旧目录覆盖新记录。独立 Skill/模块按目的拆提交；采用后核最终 tree/diff、其他模块及根规则/本地配置仍保留，运行受影响消费者。干净 diff 不能替代语义验收。

正式 PR 同样核最终允许范围。未发表短分支可按项目策略 rebase；已发表分支须核 owner 和重写授权。长期集成分支不 rebase/force，主干→长期线是另一个同步方向。修改 base/head 后重新验收；不能以 safe-push 拒绝为理由退回裸 push。

## 3. Cherry-pick / backport

先核隔离工作区及 index 干净、源 commit 的完整 patch/范围和目标需要。完整 commit 均属本次范围时，跨分支回补使用 `git cherry-pick -x <OID>` 保留来源；只需要其中部分内容时按上节窄采用，不 cherry-pick 整个 commit。

不直接 cherry-pick merge commit；确需处理时先明确父提交及语义，使用 `-m <parent-number> -x`。多个无关提交逐笔对账和验证，不作为批量同步工具。冲突后意图不明或范围扩大时，仅对本次本人发起的操作安全 abort，保留源成果；解决后核实际 diff、提交来源与验证。已有中间态属于其他会话时不得自行中止。

## 4. 冲突与误删恢复

读取双方意图及真实允许范围，只改冲突区域，保留双方有效成果。删除/修改冲突须确认删除意图和目标侧现状，不能仅凭“本地还存在”判远端误删，也不能盲目接受删除。

确证误删时先保留现场与恢复点；仅对本人发起的 rebase 安全中止，通过 reflog 核原提交，在最新目标的干净隔离候选恢复已核文件：

```bash
git reflog -10
git restore --source='<已核原提交>' -- '<已核误删文件>'
```

不以旧整目录覆盖目标新成果、不移动其他会话检出的 ref。误提交到别人的分支时保留原提交，在正确基准的隔离候选窄采用；原分支后续如何整理由 owner 和重写授权决定，不能替其删重复提交。

精确暂存解决内容后，运行匹配的构建/测试和消费者，核最终说明与完整范围，再继续提交/发表。不要为了探测冲突在共享主源发起试验 merge；使用项目已有隔离验证方式。

## 5. Lock 文件

package-lock / pnpm-lock 等冲突先理解双方依赖变化，优先使用包管理器支持的锁文件合并/重算方式。不要默认删除锁文件并重装依赖。确需 npm install / pnpm install 时核用户或项目对精确命令的既有授权，编排层保留来源；无授权或缺工具时保留失败和剩余验证边界，不自行安装。
