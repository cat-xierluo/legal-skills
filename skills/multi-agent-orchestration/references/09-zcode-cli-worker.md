# ZCode CLI Worker（zcode backend）

> 补充参考：SKILL.md 的 zcode backend 深度说明。研究 2026-08-27（协议全链真机验证），
> 同日完成 spawn-worker 端到端转正验证（Task-077）。

## 1. 概述

zcode 是智谱 ZCode 桌面端内置的官方 CLI（GLM 官方 Harness，源码路径
`apps/zcode-cli/packages/cli/dist/zcode.cjs`，12MB node bundle）。作为 worker
backend 的价值：

- **额度经济**：与 ZCode GUI 同端点（`open.bigmodel.cn/api/anthropic`）同凭证，
  吃 GLM Coding Plan 套餐额度（官方活动期内 ZCode 渠道另有加成，2026-08-27
  核实为 1.5x 至 2026-08-31；archive 草稿记录的 0.66x 折扣以官方页面为准复核）。
- **多一个模型池**：GLM-5.3 / GLM-5.3-Flash 等与 Claude/Codex 系正交，额度
  受限时可分流。
- **合规面干净**：官方二进制 + 官方协议 + 本人 GUI 登录凭证，无逆向、无指纹
  伪造（对比网关类项目的灰色边界）。

与其他四家 backend 的本质差异：**zcode 无独立 TUI**（`@zcode/tui` 未随桌面端
打包，官方无独立 CLI 分发），因此 spawn 起的是本 skill 自带的
`scripts/zcode-worker-driver.py` 包装器（§6），不是裸 CLI。

## 2. 二进制位置与首次配置（ prerequisite 清单）

> **装了 ZCode.app ≠ 可派发**。CLI 不在 PATH、凭证不落 cli config——
> 首次使用必须走完下面 5 步。`check-dependencies.sh --backend zcode`
> 检测的正是这几项，任何一项缺失都有对应修复指引。

| 项 | 值 |
|---|---|
| bundle 脚本 | `/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs`（node 脚本，非原生二进制，不能假设 +x） |
| 推荐入口 | `~/.local/bin/zcode` → bundle 的 symlink（validator 按 basename `zcode` 识别） |
| 检测命令 | `check-dependencies.sh --backend zcode`（PATH + bundle + model config 三层检查） |
| 凭证文件 | `~/.zcode/cli/config.json`（**headless 会话的必须品**，见步骤 3） |

### 首次配置 5 步

```bash
# 1) 安装并登录 ZCode 桌面端（App Store/官网 dmg），GUI 内连接 BigModel
#    Coding Plan（左下角"连接使用"）。GUI 登录态写入 ~/.zcode/v2/。

# 2) 建 PATH symlink（官方不发布独立 CLI，CLI 藏在 App bundle 里）
ln -s /Applications/ZCode.app/Contents/Resources/glm/zcode.cjs ~/.local/bin/zcode

# 3) 兜底执行位：bundle 出厂通常带 +x 与 shebang，个别安装可能丢失
chmod +x /Applications/ZCode.app/Contents/Resources/glm/zcode.cjs

# 4) 同步凭证到 CLI config（见下方 JSON 模板；GUI 的 v2 config 与 CLI
#    config 是分离存储，不复制 CLI 无法对话）
# 5) 验证
~/.local/bin/zcode --version          # 应输出版本号（如 0.16.5）
bash <skill>/scripts/check-dependencies.sh --backend zcode   # 三层全 OK
```

### 凭证同步模板（步骤 4）

GUI 登录后 `~/.zcode/v2/config.json` 里有 provider 定义（含 baseURL + apiKey）；
把它抄进 `~/.zcode/cli/config.json`：

```json
{
  "model": "builtin:bigmodel-coding-plan/GLM-5.3",
  "provider": { "builtin:bigmodel-coding-plan": { "kind": "anthropic",
    "options": { "baseURL": "https://open.bigmodel.cn/api/anthropic",
                 "apiKey": "<从 v2 config 原样复制>" } } }
}
```

- 顶层 `model` 是字符串引用 `"provider键/模型ID"`；provider 表在顶层 `provider`
  键（单数），driver/CLI 从这里合并 baseURL/kind/apiKey。
- key 是快照：GUI 刷新凭证后 CLI 会 401，重抄 provider 段即可
  （症状：worker turn 秒级 `prompt_failed` / 401，重做步骤 4）。
- **任何真实 apiKey 不得进入 git / worktree / 日志**（SKILL §1 凭证边界）。
- `ZCODE_CLI_CONFIG` 环境变量可覆盖 config 路径（多装机器/测试用）。
- ZCode.app **升级后 bundle 路径不变**（版本号不进路径），symlink 无需重建；
  但升级可能重置 +x，回到步骤 3。

## 3. CLI 关键参数（0.16.5 实测）

```
zcode -p "<prompt>"            # headless 单发（positional；--prompt 同义）
  --cwd <dir>                  # 工作目录（默认当前目录）
  --mode yolo                  # 无人值守必需：build/plan 模式在 headless 下
                               # 无权限客户端，Write/Bash 全被拒
  --resume <sessionId>         # 续会话（session 存 ~/.zcode/cli/db/db.sqlite）
  --json                       # 收尾输出结构化汇总（sessionId/usage）
zcode app-server               # stdio JSON 协议长驻服务（driver 的底层）
zcode login --no-browser       # Z.ai OAuth（BigModel 登录走 GUI，不需要这条）
zcode doctor / version / plugins list / skills list
```

注意：`--allowed-tools` 在 0.16.5 未实现（`Unknown option`）；无 `--model` 参数
（模型由 config 决定）。

## 4. 可用模型

由 `~/.zcode/cli/config.json` 的 provider 决定；BigModel Coding Plan 常见：
`GLM-5.3`（1M 上下文）、`GLM-5.3-Flash`。切换模型 = 改 config 的 `model`
引用（worker prompt 内 `/model` 仅作用 TUI，headless 不可用）。

## 5. 关键限制

1. **无 TUI**：`zcode`/`zcode tui` 直接跑必报 `Cannot find package '@zcode/tui'`
   （bundle 内逻辑：非 SEA 单文件版直接 import 外部包，桌面端打包未携带）。
   worker 只能走 driver（长驻协议）或 headless（一次性）。
2. **headless 必须 yolo**：无人值守执行需用户授权（与 claude-code
   bypassPermissions 同级风险面）；install-guard 因此走 prompt-only 降级
   （同 codex，需显式 `--allow-prompt-only-install-guard`）。
3. **15 秒偏好应答窗口**：app-server 每个 turn 前发
   `session/requestRuntimePreferences` 服务端请求，客户端超时未答则该 turn
   `prompt_failed`。driver 已内置自动应答——**绕过 driver 自己写协议客户端
   必须处理这个**。
4. **并发 = 套餐路数**：同凭证多 worker 并发等同 GUI 多窗口；超出 Coding
   Plan 并发上限会 429。`orchestration-personal.json` 的
   `concurrency.per_backend.zcode` 应设为 ≤ 套餐路数。
5. **额度活动期限**：加成活动有截止（当前核实 2026-08-31），worker 池用量
   预算勿按加成期常量化。

## 6. tmux Worker 启动（driver 模式，标准路径）

```bash
bash scripts/spawn-worker.sh \
  --project "$PROJECT" --branch feat/w-zcode --session w-zcode \
  --worker-backend zcode \
  --allow-prompt-only-install-guard "<理由>" \
  --no-trust-auto --no-permission-auto --no-orca-mode
```

默认命令 = `python3 <skill>/scripts/zcode-worker-driver.py`（validator 的
trusted-driver 通道唯一放行的 python 形态）。driver 职责：

- 子进程方式长驻 `zcode app-server`（会话状态在内存，多轮零重启）；
- 自动应答 runtimePreferences（§5.3）；
- PM `send` 的纯文本 → `session/send`（**进程内注入**，纠偏不丢上下文）；
- 事件流渲染为可读行（`[session] running (prompt_started)` /
  `[driver] send ✓ accepted=True`）——tmux capture-pane / Orca terminal read
  直接可读；
- PM 侧本地命令：`/status`（session/read）、`/stop`（session/stop 软停当前
  轮，进程不死）、`/compact`、`/quit`。

headless 备选（render `--mode batch`）：
`zcode --mode yolo --prompt "$(cat PROMPT_FILE)"` ——一次性、无纠偏，仅适合
自包含短任务。

**协议参考**（自写客户端时）：stdio JSON 裸帧（**无 jsonrpc 信封**），
`{id, method, params}` / `{id, result|error}`；错误码沿用 JSON-RPC（-32601/
-32602/-32004 Session is not active）；服务端会反向发请求（偏好应答）。
`session/create` 响应的 sessionId 在 **`result.session.sessionId`**（嵌套，
非顶层——2026-08-27 真机踩坑记录）。

## 7. 适用场景

| 场景 | 推荐度 | 说明 |
|---|---|---|
| 中文法律/文书类批量任务 | 高 | GLM 中文能力 + Coding Plan 额度池 |
| 前端/常规代码 worker | 中 | 与 claude-code 池分流，额度互备 |
| 需要 TUI 交互巡查的任务 | 不适用 | 无 TUI，靠 driver 渲染 + /status |
| zcode 做 PM 宿主 | 不适用 | 见 G24：非 CLI harness 不做 PM；本 backend 仅 worker |

## 8. 与 Skill 框架的集成

- backend 标识 `zcode`（canonical 归一仅此拼写；不做 PM host，policy 无
  `hosts.zcode`）。
- 白名单：`claude-code` / `codex` PM 可派发；`codebuddy`/`qoderwork-cn` PM
  派 zcode 被拒（deny_by_default，测试矩阵覆盖）。
- 身份门禁三重门：policy JSON + `canonical_harness_backend` case +
  `validate-worker-command.py`（basename `zcode` 或 trusted-driver realpath）。
- install-guard：prompt_only_degraded（无 PreToolUse hook 机制）。
- trust/permission/external-imports dialog 自动化默认全关（无 TUI 无 dialog，
  避免空等）。
- Session Context（METADATA/STATUS/RESULT）照常：STATUS 由 worker prompt
  约定自写（driver 不代写）。
- **G24 边界辨析**：CHANGELOG G24 "ZCode 类非 CLI harness 不适用本 skill 做
  PM" 指 GUI 产品做 PM；zcode CLI 做 worker 是另一回事，两者并存不矛盾。

## 9. 权限与 scope 控制

- zcode 无项目级 settings/hook 机制（无 `.zcode/settings.local.json` 等价物）
  ——scope-guard 的 settings 写入分支对其自然跳过。
- 越界防护依赖：① worktree 物理隔离；② worker prompt 的 allowed/forbidden
  files 声明；③ yolo 模式下的 PM 巡检（driver 渲染 + `/status` + 产物 diff）。
- install 授权：`--allow-prompt-only-install-guard` + INSTALL_AUTHORIZATION
  照常生效（prompt 约束层）。

## 10. zcode spawn 实战坑（2026-08-27 真机记录）

1. **sessionId 嵌套**：`result.session.sessionId`，顶层取不到 → driver 早期
   版本 session 永不 ready、消息卡 queued（已修，stub 测试同步真实结构）。
2. **create 响应在偏好应答之后**：先发 create 也要等服务端偏好请求并应答
   才返回响应；PM 在 session ready 前 send 的文本由 driver 排队（queue +
   drain），不丢弃。
3. **clean-worktree 的 Orca 路径解析**：从 symlink 目录调用时 Orca 可能把
   PM 所在目录误判为删除目标而拒绝——在真身仓根目录执行清理可避开
   （记忆：spawn/clean 必须站项目根）。

## 版本记录

- 2026-08-27：协议全链真机验证（偏好应答/create/send/stop/注入）；backend
  转正（Task-077）：identity gate、driver、render、deps、测试矩阵、端到端
  两轮产物验收。
