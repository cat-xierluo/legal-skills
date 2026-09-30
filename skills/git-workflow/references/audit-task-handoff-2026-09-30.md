# 独立审计任务交接（2026-09-30）

本文件只保存脱敏的待办交接。现有本地 TASKS.md 由忽略规则保护，接手者先核对并去重导入，不覆盖其历史。本次不修改运行源码，不表示问题已修复。基线 8c529516db1a5ad80c525593a0e162ef7a5751ad。

### L4 / P2：whoami 忽略 Git author.* / committer.*，污染身份仍自检通过

证据：[identity-audit.sh L181-L199](https://github.com/cat-xierluo/legal-skills/blob/8c529516db1a5ad80c525593a0e162ef7a5751ad/skills/git-workflow/scripts/identity-audit.sh#L181-L199)；[比较 L229-L246](https://github.com/cat-xierluo/legal-skills/blob/8c529516db1a5ad80c525593a0e162ef7a5751ad/skills/git-workflow/scripts/identity-audit.sh#L229-L246)

脚本把 git config user.name/email 当最终生效身份，只审 user.* 来源。隔离全局 human user.*，本地设置 author.name/email=合成 agent、committer.name/email=合成 bot，带正确 human --expected-* 跑 whoami 得 rc0/IDENTITY_AUDIT_OK；同进程环境下 git var GIT_AUTHOR_IDENT/GIT_COMMITTER_IDENT 均为 agent。应分别核真实 author/committer，再展示所有影响身份的配置来源；后续 outgoing gate 能抓住污染提交，不抵消 commit 前自检错误 PASS。

### L5 / P2：branch-audit 依据旧 PR 分支名将新工作标为 SAFE_DELETE

证据：[branch-audit.sh L37-L40](https://github.com/cat-xierluo/legal-skills/blob/8c529516db1a5ad80c525593a0e162ef7a5751ad/skills/git-workflow/scripts/branch-audit.sh#L37-L40)；[L87-L107](https://github.com/cat-xierluo/legal-skills/blob/8c529516db1a5ad80c525593a0e162ef7a5751ad/skills/git-workflow/scripts/branch-audit.sh#L87-L107)；[L117-L125](https://github.com/cat-xierluo/legal-skills/blob/8c529516db1a5ad80c525593a0e162ef7a5751ad/skills/git-workflow/scripts/branch-audit.sh#L117-L125)

查询只拿 number/headRefName，既不核 PR base，也不核 merged PR head OID 等于当前 tip；已推送的新提交不会触发“本地 ahead”保护。合成 bare origin + mock gh 已复现：origin/reused 比 main 多一个新提交、本地与远端相同，历史 merged PR #42 同名，远端输出 SAFE_DELETE/内容已进 base。另同夹具当日 active-today 与 archive/snapshot 均为 SAFE_DELETE：年龄阈值没执行，archive 判断在可达性分支之后。脚本不会自行删除，风险是给用户/后续执行者错误安全证据。应按精确 repo/base/tip/生命周期分类，protected 条件先于 merged 推理，查询失败不得当无 open PR。

## 待导入任务

### TASK-2026-09-30-GIT-EFFECTIVE-IDENTITY — 按真实author/committer核验提交前身份
- 状态：READY；优先级：P2；Owner：未领取；范围：scripts/identity-audit.sh、test-identity-audit.sh、相关SKILL/CHANGELOG。
- 问题与证据：基线8c529516，identity-audit.sh:181-199,229-246只读user.*；合成author.*/committer.*覆盖时whoami带human expected仍rc0，但git var两种身份为agent。
- 修复要求：分别解析Git最终author/committer身份及覆盖来源，expected比较和可疑检测落到真实值；显示env/user/author/committer作用链，拒绝读回失败。
- 验收：local/worktree/global author.*/committer.*、GIT_AUTHOR_*/GIT_COMMITTER_*、合法GitHub noreply、无覆盖正例；每例对照git var结果；审计不改config、refs、worktree。既有16例保持，新反例不得再PASS。
- 当前验证：16/16既有测试通过；该新反例已复现；未修复。公共证据见L4。此记录是脱敏交接，待导入现有本地TASKS，不覆盖其历史。

### TASK-2026-09-30-BRANCH-AUDIT-EXACT-IDENTITY — 修复分支删除候选的身份与保护顺序
- 状态：READY；优先级：P2；Owner：未领取；范围：scripts/branch-audit.sh、新增对应合成测试、references/branch-lifecycle-and-cleanup.md。
- 问题与证据：基线8c529516，branch-audit.sh:37-40,87-107,117-125；历史同名merged PR使包含新未集成commit的remote tip被标SAFE_DELETE；当日分支和archive/snapshot也先被merged判定吞掉。
- 修复要求：PR匹配需canonical repo/base/current head OID与交付证据；保护条件先于SAFE_DELETE，包括活跃阈值、worktree/dirty或未知、长期/归档；API失败与空结果分开，不把不完整列表当作无open PR。
- 验收：旧PR后已推新commit、PR合到另一base、fork同名head、超过一页/查询失败、24小时内分支、archive/long-lived、dirty工作区均不能给SAFE_DELETE；真正旧且精确匹配的已交付分支仍可候选。仅输出，测试不得删除真实分支。
- 当前验证：本地bare origin+mock gh反例复现；未修复。脚本本身不删分支，风险为错误安全分类。公共证据见L5。
