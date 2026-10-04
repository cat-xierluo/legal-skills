# 提交身份与完整范围推送

仅在提交、推送或身份排查时读取。隐私内容与精确例外由[隐私预检](privacy-preflight.md)维护，PR 发表/合并由[PR 流程](pr-workflow.md)维护。本页不授权修改共享身份配置、历史或远端。

## 提交前：核分支和身份来源

共享检出可能被其他会话切换分支。每次提交前核实际根目录、当前分支、HEAD 和 dirty/index；status 干净不能证明在预期分支。出现近期 checkout 或身份变化时先确认归属，不强移正在被其他树检出的 ref。

```bash
git branch --show-current
git reflog -3
bash "$git_workflow_dir/scripts/identity-audit.sh" whoami
```

## Worktree 身份隔离

worktree 隔离文件和 HEAD，但同一仓库的 worktree 默认共享仓库级 `.git/config`。因此 worker **禁止**运行 `git config user.name ...`、`git config user.email ...` 或带 `--local` 的同类命令；这些写入会污染其他并发 worktree。只有项目已明确启用 `extensions.worktreeConfig` 且用户授权时，才可讨论 `git config --worktree`。默认用单次环境变量绑定本次提交身份：

```bash
GIT_AUTHOR_NAME="<name>" GIT_AUTHOR_EMAIL="<email>" \
GIT_COMMITTER_NAME="<name>" GIT_COMMITTER_EMAIL="<email>" \
  git commit -m "<title>" -m "<body>"
```

普通提交发表必须走身份与隐私绑定的 `safe-push.sh`，核验**完整 PR range**后只 push 已核验的 immutable OID；不得直接 `git push`，也不得只看 `git log -1` 或 HEAD：

```bash
# integration base 必须显式是远端跟踪 ref；不要用 HEAD~1 缩窄范围
bash "$git_workflow_dir/scripts/safe-push.sh" \
  --base origin/main \
  --remote origin \
  --branch feat/example \
  --expected-name "<name>" \
  --expected-email "<email>"

# 只读诊断可单独运行门禁；不替代 safe-push
bash "$git_workflow_dir/scripts/check-outgoing-identities.sh" \
  --base origin/main \
  --expected-name "<name>" \
  --expected-email "<email>"
```

门禁逐 commit 比较 author name/email 与 committer name/email，只接受当前 worktree HEAD 与远端跟踪 base。当前 feature branch 若已跟踪同名 `origin/feat/...`，自动 upstream 会隐藏已 push 的早期 commit，因此判为 ambiguous，必须显式传 PR base。以下任一情况均 fail-closed：base 不明或不是远端跟踪 ref、用 `HEAD~1`/本地 ref 任意缩窄范围、bad revision、base 不是 HEAD 祖先、range 为空、Git 命令出错、身份字段为空或任一 commit 身份不一致。`safe-push.sh` 刷新明确的 integration base ref，固定 base/head OID；身份门禁与共享隐私 checker 核验相同范围。隐私 checker 逐笔读取 message、patch、变更 blob，覆盖中间提交泄露后删除；浅克隆、缺对象、不可读历史或内容均停止。核验期间 HEAD/base 改变即拒绝，再把该 OID 精确推到目标分支。

## 身份自检与污染排查

期望身份须来自用户或已确认项目配置，不能直接信任可能被并行会话污染的 repo-local config。Co-authored-by 尾注独立于 author/committer 字段，另核完整说明；GitHub 自动 squash 汇总也可能带入分支作者。

每次 commit 前（至少 push 前）跑一次只读自检：

```bash
bash "$git_workflow_dir/scripts/identity-audit.sh" whoami
# 可选硬门禁：与期望身份不符即非 0 退出
bash "$git_workflow_dir/scripts/identity-audit.sh" whoami \
  --expected-name "<name>" --expected-email "<email>"
```

覆盖四类风险，任一命中即非 0 退出（先排查再提交）：

1. 仓库级（`--local`）或工作树级（`--worktree`）`user.*` 覆盖——本技能规范 worker 本就禁止写入；
2. `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env 覆盖——只影响单次提交但会静默压过 config；
3. 可疑身份模式——邮箱 `*.local`/`*.invalid`/`*.test`/`@example.*`/`noreply@`（`users.noreply.github.com` 的 noreply 不贴着 @，不误伤），姓名 hermes/openclaw/codex/claude/checkpointer/minimax/glm/bot/agent/worker/dashboard/assistant（大小写不敏感；模式据 260930 全仓实测归纳）；
4. `--expected-name/--expected-email` 不符。

发现属本人身份（自定义域邮箱、本人设置的仓库级覆盖等）时用 `--allow-email`/`--allow-name`/`--allow-local-override` 精确放行，不要放宽模式。

身份问题排查入口：

| 症状 | 动作 |
|:-----|:-----|
| PR/合并提交多出陌生 Co-authored-by 尾注 | `bash "$git_workflow_dir/scripts/identity-audit.sh" history --all` 看尾注分布；根源=分支提交作者，清洗须改写分支作者（`git rebase -r --exec 'git commit --amend --reset-author --no-edit'`）后重推，且必须用户授权 |
| 提交作者不是我 | `whoami` 来源链定位写入层（env → worktree → repo-local → global，`--show-origin` 给出具体文件）；核用户确认的具体覆盖键，分别 unset 后回落全局，确认后再提交 |
| 全仓身份体检（交接/发版/公开化前） | `history --all` 输出 author/committer/尾注三张分布表，可疑项自动标注；大仓用 `--max-commits` 控制上限 |

发现身份污染时**先报告用户**，不得擅自改写历史或 force push（[共同约束](../SKILL.md#共同约束)）。与 `check-outgoing-identities.sh` 的分工：`whoami` 管"提交前我是谁、身份哪来的"，push 门禁管"push 前 range 内每一笔是谁"——两者互补，不可互替。


## 已合并历史的服务端回执

已合历史对账中遇到 GitHub 服务端合成签名时，使用现有只读入口核本仓 MERGED 回执：

```bash
bash "$git_workflow_dir/scripts/identity-audit.sh" receipt \
  --repo '<目标仓库>' --range '<base>..<head>' --merged-limit 500
# 单个提交也可传完整 <oid>
```

完整 mergeCommit OID 精确绑定才 ACCEPT；普通提交 SKIP；完整查询无绑定为 DENY_FORGED。网络/格式失败、查询截断且未命中为 UNKNOWN，非零退出，不放行也不称伪造。保留原始列表数量，不能因过滤空回执而误判完整；需要时显式扩大查询窗口。此能力仅核已发表历史，不改变普通 safe-push 的用户身份要求，不授权改写历史。
