# 长期集成分支模式

## 1. 适用条件

同时满足以下条件时，才使用长期集成分支（long-lived integration branch）：

- 一个具名大型功能需要跨多个短分支、子 PR 或开发波次；
- 各子任务可以独立验收，但整体尚未满足进入默认主干的里程碑门禁；
- 项目已明确指定集成分支、集成者、固定 Worktree、退出条件和最终 PR 目标。

单个 PR 可以完成的功能、没有独立验收边界的探索，或只是希望暂存未完成代码时，不建立长期集成分支。

## 2. 分支角色与拓扑

```text
默认主干（main/master）
  ├─ 通用修复短分支 ── PR ──► 默认主干
  │                              │
  │                              └─ 波次边界 merge ──► 长期集成分支
  │
  └─ 长期集成分支（某一功能线的 mini-main）
       ├─ worker 短分支 A ── squash PR ──► 长期集成分支
       ├─ worker 短分支 B ── squash PR ──► 长期集成分支
       └─ 具名里程碑满足 ── integration PR ──► 默认主干
```

长期集成分支不是第二个全局主干，也不是共享 WIP 分支。它只承载一个功能线，并保持可运行、可审查、可回退。

## 3. 建线合同

项目规则或任务合同至少固定以下信息：

| 字段 | 要求 |
|------|------|
| `integration_branch` | 长期分支的完整名称 |
| `integration_target` | worker PR 的显式 base，通常等于 `integration_branch` |
| `default_branch` | 最终里程碑 PR 的 base |
| `integration_owner` | 唯一集成者或 PM；负责长期分支同步与合并 |
| `integration_worktree` | 固定 Worktree；不得与其他 Worktree 重复检出同一长期分支 |
| `milestone` | 具名结果、退出条件和复验门禁 |
| `sync_policy` | 默认主干同步时机、未决子 PR 的处理和冻结字段 |

缺少集成目标、所有者或里程碑门禁时，保持普通短分支工作流，不自行推断建线。

## 4. Worker 分支与子 PR

每个 worker 在创建 Worktree 前刷新远端，并从长期集成分支的远端跟踪 ref 创建短分支：

```bash
git fetch origin
git worktree add -b <worker-branch> <worker-worktree> origin/<integration-branch>
```

提交和 push 仍遵守主 Skill 的身份门禁。完整 PR range 的 base 必须显式指向长期集成分支：

```bash
bash scripts/safe-push.sh \
  --base origin/<integration-branch> \
  --remote origin \
  --branch <worker-branch> \
  --expected-name "<name>" \
  --expected-email "<email>"

gh pr create \
  --head <worker-branch> \
  --base <integration-branch> \
  --title "feat(<module>): <description>" \
  --body-file <pr-body-file>
```

创建后核验 `baseRefName`、`headRefName`、diff、checks 和 mergeable 状态。子 PR 只有在独立 review 与匹配门禁通过后才能 squash merge；不得把 worker 自报当作集成验收。

## 5. 变更流向

| 变更类型 | 合并路径 | 理由 |
|----------|----------|------|
| 仅属于该大型功能 | worker 短分支 → 长期集成分支 | 在功能线内部逐步集成 |
| 全项目都需要的修复/基础能力 | 独立短分支 → 默认主干 → 长期集成分支 | 默认主干保持权威，避免同一通用修改双重实现 |
| 已满足具名里程碑的功能集合 | 长期集成分支 → 默认主干 | 用一次集成 PR 审查整体行为与风险 |

若在功能 worker 中发现通用修复，优先拆成独立的默认主干 PR。无法安全拆分时，将它留在功能线，直到里程碑 PR 一并进入默认主干；不要把相同 patch 分别提交到两个主干后再制造冲突。

## 6. 波次同步与冻结

只在没有待合并子 PR 时，同步最新默认主干；如仍有 open 子 PR，先完成、关闭或重新安排这些 PR，不在它们的 base 下方移动长期分支：

1. 刷新远端并核验长期分支 Worktree 干净。
2. 确认默认主干、长期分支与 open 子 PR 的准确状态。
3. 将 `origin/<default-branch>` merge 到长期分支；不 rebase 长期分支。
4. 解决冲突后复跑长期分支匹配门禁。
5. 记录并冻结本波 `default_base_sha` 与 `integration_head_sha`；本波 worker 均从该远端集成 head 起步。

同步期间若长期分支、默认主干、任务合同或待合并 PR 发生漂移，旧验收失效，重新核验后再派发或合并。

## 7. 里程碑集成 PR

长期分支向默认主干提 PR 前，必须满足：

- 里程碑名称、范围和退出条件已在项目任务源中固定；
- 所有纳入范围的子 PR 已合并，范围外 WIP 未混入；
- 已吸收最新默认主干，并在最终树上完成对应验证；
- PR diff、提交身份、敏感信息、大文件、迁移与回退风险均已复核；
- PR base 显式为默认主干，head 显式为长期集成分支。

里程碑合并不等于功能线结束。除非项目明确宣布关闭，不使用 `--delete-branch` 删除长期集成分支。

里程碑 PR 合入后，如果功能线仍继续，在无待合并子 PR 的边界把最新默认主干（包含该里程碑的合并结果）merge 回长期集成分支，再冻结下一波 base；不要用 reset、rebase 或重建同名分支来“对齐”历史。

## 8. 生命周期与清理

- worker PR 合并并确认无未推送工作后，删除其短分支和临时 Worktree。
- 长期集成分支及固定 Worktree 持续保留，按普通活跃主干审计，不进入常规 stale branch 批量清理候选。
- 只有功能线完成或取消、未决工作已处置、最终状态已写回项目任务源，并取得明确删除授权后，才清理长期分支与固定 Worktree。
- 删除前仍执行主 Skill 的 PR 状态、最后提交时间、Worktree 未提交改动三查；不得 `git worktree remove --force` 或 `git branch -D` 绕过证据。
