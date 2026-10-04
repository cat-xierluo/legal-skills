# gh CLI 常用命令速查

按需查询 GitHub CLI (`gh`) 参数。只读命令可用于核查；review、Issue 写入、关闭、更新分支与远端操作须有对应授权。PR 与发布的安全规则由场景合同维护，速查不构成额外授权。

## 认证

```bash
gh auth login          # 交互式登录
gh auth status         # 查看认证状态
```

## Pull Request

### 创建

发布按主Skill身份/隐私门执行；先 safe-push.sh，再 safe-pr.py create，提供实际base/head、完整expected-head及最终标题/正文文件。默认draft，创建后核真实元数据。不要用裸gh pr create或--fill替代发表预检，完整命令见[隐私预检](privacy-preflight.md)。

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

读取[PR 合同](pr-workflow.md)满足范围、review、最终 checks 和授权后，按[隐私预检](privacy-preflight.md)使用 safe-pr.py，绑定完整受审 head 与最终说明；合并后核实际回执。不要裸 merge 或 admin override。

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

发版与上传资产读取 release-workflow，不由速查触发发布。只读查询：

```bash
gh release list
gh release view '<tag>'
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
