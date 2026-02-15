# GitHub Token 配置指南

本 skill 需要 GitHub 认证才能执行 star 操作。以下是配置步骤：

## 方式一：使用 gh CLI（推荐）

1. 确保已安装 GitHub CLI：
   ```bash
   brew install gh
   ```

2. 登录 GitHub：
   ```bash
   gh auth login
   ```
   - 选择 `GitHub.com`
   - 选择 `HTTPS`
   - 登录方式选择 `Login with a web browser`
   - 复制提供的一次性验证码
   - 在浏览器中完成授权

3. 验证登录状态：
   ```bash
   gh auth status
   ```

## 方式二：使用 GitHub Personal Access Token

1. 创建 Personal Access Token：
   - 访问 https://github.com/settings/tokens
   - 点击 "Generate new token (classic)"
   - 勾选 `repo` 权限（完整控制私有仓库）

2. 设置环境变量：
   ```bash
   export GITHUB_TOKEN="你的_token_值"
   ```

## 验证配置

配置完成后，可以验证是否能正常访问 GitHub：

```bash
gh repo list 你的用户名
```

或使用 API：

```bash
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user
```

## 注意事项

- GitHub API 有请求频率限制（未认证每小时 60 次）
- 使用 `gh auth login` 登录后，频率限制提升到每小时 5000 次
- 如果需要高频 star 操作，建议使用 gh CLI 登录方式
