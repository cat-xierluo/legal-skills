# 本地 Worktree → PR → 合并 SOP

按当前 git-workflow 重建通用入口；旧文件为空，原宿主特定的 Node/Raycast 步骤未能确认。本页不声称恢复了未知历史步骤，项目已有构建、发布和设计规范仍优先。

## 1. 确认目标与现场

- 读取用户授权、项目规则与当前完整任务卡，固定允许路径、产物、验收和目标分支。
- 普通任务以最新默认主干为 base；有功能线时按[功能线合同](long-lived-integration-branch.md)固定目标、生命周期与本波 OID。
- 查看 Worktree 状态、占用与未推送成果，优先复用适合的干净隔离现场；主源 dirty 时不 stash/reset/checkout 清掉别人的工作，不在主源 `gh pr checkout`。
- 刷新所选远端 ref 后建短分支，核真实起点。Task/session/Worktree 名不能代替远端分支/base/OID。

## 2. 执行与实际验证

- 只改允许文件；共享版本、CHANGELOG、README、CI由指定集成者串行处理，保留双边有效内容。
- 运行匹配产物的真实消费者及必要测试，保留退出码、产物、错误路径和未验边界。需要 Node/Raycast 等宿主构建时，执行项目已明确的命令；缺依赖不自动安装，不猜未知历史步骤。
- 每项依赖操作核真实 exit；验证、版本或范围断言失败时，停止后续 add/commit/push并保留首失败。结果或源码变化使旧验收失效。
- 审完整 diff/新增文件、引用、版本索引和敏感内容；精确暂存文件，不 broad add 或整目录导入旧树。

## 3. 身份、提交与发布

- 按主 Skill `identity-audit.sh whoami` 核身份来源，以单次环境变量绑定 author/committer，不写共享 Git config；提交含正文与任务来源。
- 走 `safe-push.sh`，base为真实远端 PR 目标，核完整 range 的身份/隐私及不可变 OID。
- 准备最终标题/正文文件，用 `safe-pr.py create` 建唯一 draft，显式 head/base/expected-head；后验真实 PR 元数据，不用 `--fill`、自动拼接未检文本或盲目重试。
- GitHub 自 approve 受限时采用真实不同角色审查，继续满足仓库保护；无需 GitHub approval 不等于无需独审。

## 4. 受审候选与合并

- 绑定原工程/最终 head、独立 review、实际验证、最终 checks和完整允许范围；未知、失败、漂移或依赖未解决时不合。
- 有授权并完成验收后转 ready，用 `safe-pr.py squash` 核完整历史、当前及最终文本并绑定 head；后验 `MERGED/mergedAt/mergeCommit`，不自动删分支。
- Monorepo本地不能直接 feature→main merge；窄采用或正式 PR 保留当前全仓基线。主干→长期线同步读取功能线专页。

## 5. 本机采用与收口

- 源入口有在途改动时，只增量接回已验文件，核原字节后再写；保留源 index、别名和其它成果，不强行整树对齐。
- 回写既有任务/变更记录和实际证据。云端交付、本机安装、其它消费者采用分别核验，不以安装成功追认所有聊天已加载。
- 按[清理合同](branch-lifecycle-and-cleanup.md)核归属、精确 tip、dirty/占用及删除授权；清理失败不重放 PR 操作。长期线保留，在波次边界吸收主干后冻结下一波。
- 报告交付、保留/待办和清理实际状态，明确 `NOT_VERIFIED`。入口备份用 `.snapshot`，避免归档被再次发现为 Skill。
