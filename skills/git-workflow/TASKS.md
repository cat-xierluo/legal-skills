# 任务清单

> 最后更新：2026-06-06

## 已完成

- [x] 精简 `SKILL.md` frontmatter `description`，删除具体命令细节和项目特定后置动作；同步 README、Marketplace 和最近更新区到 v1.4.1；将 `doc-curator` 调整为可选项目扩展；为本 Skill 的 `DECISIONS.md` / `TASKS.md` 增加 Git 跟踪例外
- [x] 新增「批量审计：已合并分支清理」子流程，覆盖 squash/rebase merge 场景；权威依据为 `gh pr list --state merged`，配合 `git branch --merged` 仅作辅助；含判定规则表 + 候选确认表 + 5 条 fail-closed 红线（来源：Folia 2026-06-06）
- [x] 创建独立 `git-workflow` Skill，保持与提交生成工具的职责边界
- [x] 收纳 Git 安全协议：禁止破坏性操作、按文件暂存、hook 失败不跳过
- [x] 补充分支管理、worktree 使用、常规 Git 操作速查
- [x] 增加 Monorepo 安全合并规范：禁止直接 merge 旧 feature 分支，改用目录级 checkout
- [x] 增加 rebase 冲突恢复规范，防止误删目录被接受
- [x] 迁入 Issue / PR 命名规范，作为 Git 流程入口的一部分
- [x] 增加 PR review / merge fail-closed 门禁
- [x] 将提交规范内置到 `SKILL.md`，避免主流程依赖其他 Skill
- [x] 增加本任务清单，补齐 Skill 维护上下文
- [x] 补强 PR 合并前检查命令和判断规则
- [x] 补强 Cherry-pick 安全流程、目录级提取和冲突恢复规则
- [x] 在 `references/gh-cli-quickref.md` 补充 fail-closed merge gate 速查
- [x] 在 `references/issue-pr-format.md` 补充 `docs/TASKS.md` 主状态源边界说明
- [x] 正式迁入 `legal-skills/skills/git-workflow/`，并同步 README 与 Marketplace 清单
- [x] 增加 PR 模板检查规则，确保 Summary / Test plan / Agent Attribution 不缺失
- [x] 增加 Monorepo PR diff 检查清单，专门识别误删大量文件、跨 Skill 污染、敏感配置误提交
- [x] 描述部分中文化：PR body 模板、PR 正文最低要求表、命令注释、表格标题改为中文；保留英文类型前缀以兼容 GitHub 标签和 Conventional Commit 工具链；通用 Git 术语（Rebase merge / Squash merge / cherry-pick / PR / commit 等）保留英文

## 后续优化

- [ ] 为常见事故补充恢复路径：误 amend、误 stash、误删分支
- [ ] 评估是否需要轻量脚本化检查，但不要把本 Skill 扩张成提交生成器或任务状态系统
- [ ] 评估 `agent-worktree` 的 `wt sync` / 原子 `wt merge` 思路是否可转化为 Git 安全检查；在 Monorepo 中不得默认直接 merge feature 分支，必须保持目录级 checkout 或 PR diff 门禁

## 边界提醒

- 任务状态归 `cross-agent-coordination` / `docs/TASKS.md`
- 本地 Agent 会话归 `multi-agent-orchestration`
- 批量提交生成归专门的提交工具
- 本 Skill 只维护 Git 流程和安全规则
