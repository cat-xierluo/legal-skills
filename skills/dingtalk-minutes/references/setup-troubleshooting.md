# 安装、授权与常见坑（他人部署必读）

本文件汇总从零部署本 skill 时必须跨过的几道门槛。钉钉 CLI（dws）读取 AI 听记依赖**三个独立前置条件**，任一步漏掉都会报错。按下面顺序操作。

## 1. 安装 dws（钉钉官方 Workspace CLI）

官方仓库：`https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli`

**注意安装脚本路径**：不是仓库根目录的 `install.sh`，而是 `scripts/install.sh`。

```bash
curl -fsSL https://raw.githubusercontent.com/DingTalk-Real-AI/dingtalk-workspace-cli/main/scripts/install.sh -o /tmp/dws-install.sh
sh /tmp/dws-install.sh
```

安装后 `dws` 位于 `~/.local/bin/dws`。**该路径默认不在 shell 的 PATH 中**，需手动写入：

```bash
# 写入 zsh（macOS 默认）
grep -q '.local/bin' ~/.zshrc || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
# 重新打开终端或 source ~/.zshrc
```

验证：`dws version` 应返回版本号（v1.0.x）。若报 `command not found`，先 `export PATH="$HOME/.local/bin:$PATH"`。

## 2. 开启组织「CLI 访问管理」开关（最易卡住）

即便 dws 装好、扫码成功，仍可能登录失败，原因是**钉钉组织默认禁止成员用 CLI 读取数据**。此开关**不在普通钉钉管理后台**，而在钉钉开放平台。

**位置**：
```
钉钉开放平台 (open-dev.dingtalk.com)
  → 开发者平台 → 更多 → 基本信息 → CLI 访问管理
```
或直接打开报错里给的链接：`https://open-dev.dingtalk.com/fe/old#/developerSettings`

**开关语义反直觉（高频坑）**：
- 该页面开关文案可能是「**禁止所有成员使用 CLI**」。
- 默认 `关闭` → 表示「未启用 CLI 访问」（登录会报 `CLI data access is not enabled for this organization`）。
- 把它 `打开` → 变成「已禁止所有成员使用 CLI」（登录会报「该组织已禁止所有成员使用 CLI」）。
- **正确状态是「关闭」该开关**（关闭=不禁止=允许成员使用 CLI）。

> 判断方法：看开关旁的说明文字。若写「禁止所有成员使用 CLI」→ 关掉它；若写「允许成员使用 CLI」→ 打开它。以说明文字为准，不要只看开关开关方向。

**权限要求**：此开关为组织级，需**主管理员**账号登录开放平台才能看到与修改。子管理员可能看不到该项。

## 3. 授权登录（必须后台运行，前台会截断）

使用设备码模式授权。**不要在前台直接跑 `dws auth login --device` 然后等**——前台进程在命令返回后即被截断，授权回调来不及落盘，会导致 `dws auth status` 仍显示 `authenticated: false`、`profile list` 为空。

正确做法（后台运行，等待回调完成）：

```bash
dws auth login --device > /tmp/dws-auth.log 2>&1 &
# 读取日志拿到 user_code 与链接
sleep 2; cat /tmp/dws-auth.log
```

日志会输出类似：
```
To authenticate, use the following code with your DingTalk app:
  User Code: XXXX-XXXX
  Verification URL: https://login.dingtalk.com/oauth2/device/verify.htm?user_code=XXXX-XXXX
```
用钉钉 App 扫码，或浏览器打开链接输入 `User Code`。**等待后台进程打印 `Authorization successful` 后再继续**——此时 token 才真正落盘。

验证：`dws auth status` 显示 `authenticated: true`，`dws profile list` 列出你的组织与用户。

## 4. 读取类命令的参数陷阱（高频幻觉）

| 陷阱 | 错误写法 | 正确写法 |
|------|----------|----------|
| `transcription` 不在顶层 | `dws minutes transcription --id ...` | `dws minutes get transcription --id ...` |
| 参数是 `--id` 不是 `--uuid`（顶层 list 用 uuid，get 下用 id） | `dws minutes get summary --uuid ...` | `dws minutes get summary --id <taskUuid>` |
| `list` 必须带 scope | `dws minutes list` | `dws minutes list all` / `mine` / `shared` |
| `--id` 只接受 taskUuid，不接受完整 URL | `--id https://...` | 先从 URL 提取 hex 串作为 taskUuid |
| 逐字稿需翻页 | 单次只返回前 50 段 | 用 `--next-token` 循环直到 `hasNext=false`（本 skill 的 `scripts/sync.py` 已封装） |

## 5. 自测清单

部署完成后，按顺序验证，任一步不过则说明上面对应环节没到位：

```bash
dws version                                          # 1. 安装 + PATH
dws auth status                                      # 3. 授权落盘（authenticated: true）
dws minutes list all --max 1 --format json           # 2+3. 组织开关 + 授权 + 读取权限
```

能列出至少一条听记，即代表三个前置条件全部就绪，本 skill 可用。

## 6. 其他注意

- 逐字稿里的「发言人 1 / 发言人 2」是钉钉默认编号，声纹匹配（speaker 写操作）不在本薄壳范围内；要人名需在钉钉 App 内手动匹配。
- 私有化/自建应用的 Access Token 方式不在本 skill 范围；本 skill 面向个人账号 OAuth（device 模式）。
- dws 自身通过 `dws skill setup` 会把官方 skill 装到 `~/.claude/skills/dws` 等目录；本 skill 是独立封装，不依赖那份官方 skill，只需 dws 二进制可用即可。
