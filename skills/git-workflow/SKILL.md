---
name: git-workflow
description: Git 工作流安全助手。用于分支与 worktree 管理、Skill 稀疏检出、PR 创建/审查/合并，以及提交身份和隐私检查；也支持 CI 额度治理、敏感文件历史撤回与仓库瘦身。不要用于批量生成提交信息、项目任务分配或本地 Agent 会话编排。
license: MIT
metadata:
  version: "1.17.1"
  homepage: https://github.com/cat-xierluo/legal-skills
  author: 杨卫薪律师（微信ywxlaw）
---

# Git 工作流

维护 Git 的范围、身份、候选和交付规则。先读取用户授权、项目规则与完整任务卡，确定仓库、允许路径、目标分支、预期身份和验收；只加载当前场景需要的参考文档。

## 场景路由

在相应操作前读取该行的合同；跨场景任务按执行顺序读取，不一次性加载全部 references。

| 当前需求 | 读取与执行入口 |
|---|---|
| 本地隔离开发到交付、基准落后或共享主树被占用 | [本地 Worktree SOP](references/local-worktree-sop.md) |
| 新建或限缩 Skill/套件工作树、跨目录占用审计 | [稀疏工作树](references/sparse-worktree.md)；创建用 `scoped-worktree.py`，完整登记只读审计用 `sparse-worktree-audit.py` |
| 提交身份、Co-authored-by 污染、已合历史回执、完整 PR 范围推送 | [身份与推送](references/identity-and-push.md)，再按内容读取[隐私预检](references/privacy-preflight.md) |
| PR 创建/审查/合并、CI 未知、冲突或更新 base | [PR 流程](references/pr-workflow.md)；文本与完整历史核验读取[隐私预检](references/privacy-preflight.md) |
| Monorepo 窄采用、cherry-pick 与冲突 | [改动集成](references/change-integration.md) |
| 误 amend / stash / 删分支 / reset 的事故恢复 | [事故恢复](references/accident-recovery.md)；先定位证据，再按授权恢复 |
| 长期功能线、子 PR、波次同步或里程碑 | [长期集成分支](references/long-lived-integration-branch.md) |
| 分支/工作树清理、批量验收或取代关闭旧 PR | [生命周期与清理](references/branch-lifecycle-and-cleanup.md)；只读盘点用 `branch-audit.sh` / `worktree-audit.sh` |
| Commit / Issue / PR 标题、编号与关闭语义 | [命名与提交格式](references/issue-pr-format.md) |
| GitHub Actions 分钟耗尽、停挂或恢复 | [CI 额度治理](references/github-actions-quota-guard.md) |
| 敏感/私有材料已经发表，需从历史撤回 | [历史撤回](references/history-rewrite-and-removal.md) |
| 仓库或对象库膨胀、配置同步仓瘦身 | [膨胀审计](references/repo-bloat-audit-and-slim.md)；先区分历史、检出、缓存和任务材料 |
| 查 gh 参数 | [gh 速查](references/gh-cli-quickref.md)，命令示例仍受对应合同约束 |

本 Skill 内脚本名均相对技能目录。执行时将 `git_workflow_dir` 设置为本技能安装目录的绝对路径，在目标仓库运行；不要为了调用脚本切换到技能源码仓库。本文及参考文档提供方法，不能代替用户对外部写入或破坏性操作的授权。

## 共同约束

- 保留现有改动、暂存状态、任务材料及其他会话归属。优先复用适合的隔离检出；不通过 stash/reset/切换共享主树清掉别人的现场。提交前核实际分支和身份，worktree 默认共享 repo-local Git 配置，worker 不写 `user.name/email`。
- 单 Skill/具名套件默认**创建时稀疏检出**。副作用前固定目标、真实依赖、基准与磁盘预算，入口不支持目录范围时停在创建前，不把缺少参数当作全量许可。已有树限缩先保护 dirty/index、ignored/untracked 和 Session；详细方法只在稀疏合同维护。
- `force push`、`reset --hard`、丢弃修改、`clean -f`、强删分支、跳过 hooks/签名及改写历史须有具体明确授权。锁先查持有者，不直接删；hook 失败修复后新建提交，不绕过。默认新建 commit，amend 须用户要求；精确暂存文件。
- 普通提交发表走 `safe-push.sh`，身份和隐私核验**完整 PR range**并绑定不可变 OID；不得只查 HEAD、用 `HEAD~1` 缩窄范围或裸 push 绕门。创建/合并 PR 用 `safe-pr.py` 核最终完整文本与精确 head，不使用未经检查的自动说明。已明确授权的历史重写与精确 ref 删除按对应专页执行，不能借该例外绕过普通发表门禁。
- 合并须绑定授权、可读 diff、允许范围、独立 review 和最终 checks。未知、失败、缺失或候选漂移时停止；helper 不代替这些门禁。不绕仓库保护、自 approve 限制或用 admin override。
- Monorepo 不在本地直接 feature→main merge。按实际允许范围窄采用或正式 PR 保留目标侧其他模块；主干→长期功能线同步属于另一个方向，遵循功能线合同。
- 单任务清理绑定生命周期及精确 tip；长期分支与固定树不随子 PR 删除。已合并后的清理失败记录 `CLEANUP_PENDING`，不重放 push/merge；批量候选不等于删除授权。
- 依赖缺失、验证失败或网络结果不明时保留首失败及现场；先核真实结果再重试。缺工具不自动安装、不降级绕过门禁，环境安装沿用户及项目已有授权。

## 执行与收口

1. 固定范围和原现场，读取相应合同；普通短分支以最新远端目标为基准，长期线固定本波 OID。共享源 dirty 时保持原状。
2. 在允许范围执行，运行与产物匹配的验证，审完整 diff 和最终说明。候选变化后重跑受影响检查。
3. 进入提交、push、PR、合并等副作用前核相应授权和门禁；返回值不替代实际分支、PR 元数据或服务端合并回执。
4. 在项目既有任务源记录实际产物、退出状态、候选 OID、保留项及未验范围。分别报告本机采用、云端交付与清理状态，不把静态通过称为全流程稳定。

## 依赖

### 系统依赖

| 依赖 | 使用范围与安装方式 |
|---|---|
| Git | 全部 Git 操作；macOS 可用 Command Line Tools 提供的 Git，Linux 使用发行版包管理器 |
| Bash | `.sh` 门禁与审计；使用系统 Bash |
| Python 3.10+ | 隐私、PR、稀疏创建/审计脚本；macOS: `brew install python`，Linux: `apt install python3` |
| GitHub CLI（gh） | GitHub PR/CI 与远端状态查询，先核已有认证；macOS: `brew install gh`，Linux 按 GitHub CLI 官方安装说明 |

### Python 包

Python 入口只依赖标准库，不需要 pip 安装。稀疏审计的 `du` / `lsof` 与分支盘点的 gh 降级边界见各自合同；降级后的缺失证据必须显式保留，不能追认通过。

## 协作边界

`git-batch-commit` 负责用户明确要求的提交拆分与说明生成，沿本 Skill 的身份/隐私与 Issue 关闭规则；项目任务源维护状态，`multi-agent-orchestration` 负责 worker 派发和会话，继续引用同一稀疏合同；`release-workflow` 负责发版与资产，本 Skill 负责日常 Git/CI 治理。

项目文档体检只在项目已有流程及授权内衔接；Git Workflow 不规定其阈值、目录、任务状态或维护 PR 副作用，也不因当前请求自动派发或发布维护任务。
