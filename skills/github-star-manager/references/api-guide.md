# GitHub API 使用指南

本文档说明 github-star-tracker 中使用的 GitHub API 端点。

## 基础信息

### API 基础 URL
```
https://api.github.com/
```

### 认证方式
```
Authorization: token GITHUB_PAT
```

## 使用的 API 端点

### 1. 获取用户 Star 的仓库
```
GET /users/{username}/starred
参数：per_page（默认 100，最大 100）
```

### 2. 获取仓库 README
```
GET /repos/{owner}/{repo}/readme
返回：JSON 包含 download_url
```

### 3. 获取最新 Release
```
GET /repos/{owner}/{repo}/releases/latest
返回：完整的 Release 信息
```

### 4. 获取仓库详情
```
GET /repos/{owner}/{repo}
返回：stargazers_count, forks_count, open_issues_count, language, topics 等
```

### 5. 获取 Commits
```
GET /repos/{owner}/{repo}/commits
参数：per_page, sha（分支）
```

## 使用限制

| 限制 | 无 Token | 有 Token |
|------|------------|-------------|
| 请求频率 | 60 次/小时 | 5000 次/小时 |
| 单页结果数 | 最大 100 | 最大 100 |

## 最佳实践

1. **缓存策略**：优先使用本地快照，减少 API 调用
2. **错误处理**：遇到 403/429 等待后重试
3. **增量更新**：只请求有变化的数据
