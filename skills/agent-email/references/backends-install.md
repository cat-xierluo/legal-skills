# 后端 CLI 安装与基础配置

> 本 skill 支持「网易 ClawEmail」和「腾讯 Agent Mail」两家后端。**每家需要各自的后端 CLI**——本 skill 是封装层，不替代 CLI 本身。
> 用哪家就装哪家的 CLI；想两家都用就都装，凭据各自独立、互不干扰。
>
> 本文档是两家的"基础配置总入口"，详细的分步指南见各自 setup 文档。

## 一、两家后端对照

| 维度 | 网易 ClawEmail | 腾讯 Agent Mail |
|------|----------------|-----------------|
| 后端 CLI | `@clawemail/mail-cli` | `@tencent-qqmail/agently-cli` |
| 安装方式 | **npx 即用**（无需全局装） | **必须全局安装** |
| 安装命令 | 自动：`npx --yes @clawemail/mail-cli@latest` | `npm install -g @tencent-qqmail/agently-cli` |
| Node 版本 | 18+ | 18+ |
| 管理后台 | [claw.163.com](https://claw.163.com) | [agent.qq.com](https://agent.qq.com) |
| 认证模型 | API Key（`ck_live_xxx`，认证 URL 换取，30 分钟有效） | OAuth（浏览器授权） |
| 凭据存储 | macOS 钥匙串 + `~/.config/mail-cli/config.json` | agently-cli 自管本机 |
| 本 skill 配置入口 | `claw_init "t1/认证URL" "显示名"` | `MAIL_PROVIDER=agently mail_login` |
| `MAIL_PROVIDER` 值 | `claw` | `agently` |
| 详细配置指南 | `clawemail-setup-guide.md` | `agently-setup-guide.md` |

## 二、前置依赖（两家通用）

| 依赖 | 说明 |
|------|------|
| Node.js 18+ | macOS：`brew install node` |
| npm / npx | 随 Node.js 自带 |
| bash | macOS 自带（本 skill 函数库依赖） |
| curl | macOS 自带（`claw_init` 解析认证 URL 用） |
| `script` 命令 | macOS 自带（agently OAuth pty 用） |
| macOS 钥匙串 | claw 后端存 API Key 用（Linux 由 mail-cli 改用其他 backend） |

## 三、只配一家

### 只用网易 ClawEmail

1. 在 [claw.163.com](https://claw.163.com) 注册，获取认证 URL（`t1/xxxxxx`，**30 分钟有效**）
2. 后台配置**通信规则**（开放外部收发；新建子邮箱默认未开放）
3. 一键配置：
   ```bash
   source scripts/mail-ops.sh
   claw_init "t1/你的认证URL" "显示名称"
   ```
4. `.env` 默认 `MAIL_PROVIDER=claw`，直接用 `mail_*`

详见 `clawemail-setup-guide.md`。

### 只用腾讯 Agent Mail

1. 全局装 CLI：`npm install -g @tencent-qqmail/agently-cli`
2. 在 [agent.qq.com](https://agent.qq.com) 开通
3. OAuth 授权：
   ```bash
   source scripts/mail-ops.sh
   export MAIL_PROVIDER=agently
   mail_login
   ```
4. 浏览器完成授权，`+me` 返回邮箱地址

详见 `agently-setup-guide.md`。

## 四、两家都配（推荐）

凭据各自独立保存在本机，互不干扰。配好后用 `MAIL_PROVIDER` 切换：

```bash
# ── 一次性配置（两家各跑一次）──
source scripts/mail-ops.sh

# 配网易
claw_init "t1/你的163认证URL" "我的Agent（网易）"

# 配腾讯
export MAIL_PROVIDER=agently
mail_login        # 浏览器 OAuth 授权

# ── 日常使用：用 MAIL_PROVIDER 切换 ──
export MAIL_PROVIDER=claw        # 走网易
mail_list --fid 1

export MAIL_PROVIDER=agently     # 走腾讯
mail_list --dir inbox
```

`.env` 里设默认后端：`MAIL_PROVIDER=claw`（或 `agently`），这样不手动 export 也有默认。

## 五、常见问题

### 两家 CLI 都没装会怎样？

调 `mail_*` 时按 `MAIL_PROVIDER` 分派：
- claw：走 npx 自动拉取 mail-cli（首次会慢一点，后续有缓存）
- agently：未装会报"未找到 agently-cli，请先 `npm install -g @tencent-qqmail/agently-cli`"

### 怎么看当前用的是哪家？

```bash
echo "$MAIL_PROVIDER"     # claw 或 agently
mail_me                   # claw 打印 .env 邮箱地址；agently 调 +me 返回
```

### 两家邮箱地址不一样？

正常。claw 是 `xxx@claw.163.com`，agently 是 QQ 邮箱体系的独立地址。`.env` 的 `AGENT_EMAIL` 记录的是 claw 那个；agently 的地址由 `+me` 实时返回（可备忘记到 `.env` 的 `AGENTLY_EMAIL`）。

### npx 拉取 mail-cli 太慢？

可全局安装加速：`npm install -g @clawemail/mail-cli`。但本 skill 默认走 npx `@latest` 以保证最新版，全局装后 npx 会优先用全局版。

### 换电脑了怎么迁移？

- claw：重新走 `claw_init`（认证 URL 是一次性的，API Key 存在新机器钥匙串）
- agently：重新走 `mail_login`（OAuth 重新授权）
- `.env` 可直接复制（只含邮箱地址、显示名、联系人，无敏感凭据）
