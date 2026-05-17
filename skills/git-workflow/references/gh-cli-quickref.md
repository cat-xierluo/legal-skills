# gh CLI 常用命令速查

基于 GitHub CLI (`gh`) 的常用操作参考。

## 认证

```bash
gh auth login          # 交互式登录
gh auth status         # 查看认证状态
```

## Pull Request

### 创建

```bash
gh pr create --title "feat(module): 描述" --body "正文"
gh pr create --draft   # 创建为草稿
```

### 查看

```bash
gh pr list                           # 列出 open PR
gh pr list --state all               # 所有状态
gh pr list --author @me              # 我创建的
gh pr view <number>                  # 查看详情
gh pr diff <number>                  # 查看 diff
gh pr checks <number>                # 查看 CI 状态
```

### 审查

```bash
gh pr review <number> --approve --body "通过"
gh pr review <number> --request-changes --body "建议"
gh pr review <number> --comment --body "评论"
```

### 合并

合并前先检查 PR 状态、diff 和 checks：

```bash
gh pr view <number> --json title,state,isDraft,mergeable,reviewDecision,headRefName,baseRefName
gh pr diff <number> --name-only
gh pr diff <number> --stat
gh pr checks <number>
```

diff 不可读、checks 未知、review 不明确、PR 是 draft、mergeable 不明确或 diff 超范围时，不要 merge。

PR 正文缺少 Summary、Test plan、Agent Attribution 或 Issue/Task 关联时，先要求补齐。Monorepo PR 如果出现跨目录污染、大量删除、敏感配置或版本清单不一致，不要 merge。

```bash
gh pr merge <number> --squash        # Squash merge
gh pr merge <number> --merge         # Merge commit
gh pr merge <number> --rebase        # Rebase merge
```

### 其他

```bash
gh pr update-branch <number>         # 同步最新 base
gh pr ready <number>                 # 草稿转为正式
gh pr close <number>                 # 关闭 PR
gh pr reopen <number>                # 重新打开
```

## Issue

### 创建

```bash
gh issue create --title "feat: 描述" --body "正文"
gh issue create --label "bug" --assignee @me
```

### 查看

```bash
gh issue list                         # 列出 open issue
gh issue list --state all             # 所有状态
gh issue list --label "bug"           # 按标签过滤
gh issue view <number>                # 查看详情
```

### 管理

```bash
gh issue close <number>
gh issue reopen <number>
gh issue edit <number> --title "新标题"
gh issue comment <number> --body "评论"
```

## Repository

```bash
gh repo view                          # 查看当前仓库
gh repo clone <owner>/<repo>          # 克隆
gh repo fork <owner>/<repo>           # Fork
```

## Release

```bash
gh release create v1.0.0 --title "v1.0.0" --notes "发布说明"
gh release list
gh release download v1.0.0
```

## Actions

```bash
gh run list                           # 列出 workflow 运行
gh run view <run-id>                  # 查看运行详情
gh run watch                          # 实时监控
gh workflow list                      # 列出 workflow
```

## 搜索

```bash
gh search repos "query"               # 搜索仓库
gh search issues "query"              # 搜索 issue
gh search code "query"                # 搜索代码
```

## API

```bash
gh api repos/:owner/:repo/pulls/123   # 调用 REST API
gh api graphql -f query='...'         # 调用 GraphQL
```
