# ZCode legacy driver 兼容入口

本页保留旧文件路径及诊断指路。`zcode` 是兼容 app-server driver backend，`zcode-cli` 是独立原生 CLI；两者不能共用能力声明或默认启动配方。

## 1. 选择当前路径

- 用户选择独立CLI：读取 [28 模型与套餐](28-zcode-cli-bigmodel-coding-plan.md)、[30 原生Orca](30-zcode-native-orca.md)和 [32 派发profile](32-dispatch-profiles.md)。长程任务使用原生交互CLI。
- 明确维护legacy driver：读取 [24 driver操作与安全合同](24-zcode-driver-safety.md)。旧版本没有TUI的观察仅适用于当时bundle，不代表独立CLI现状。
- 用户选择GUI：读取 [34 GUI合同](34-zcode-desktop-remote.md)，不套用legacy driver的认证或权限流程。

## 2. 配置前置与旧诊断

依赖脚本的旧诊断仍可能提示检查共享 `~/.zcode/cli/config.json` 或“mirror provider entry”。这只是旧探测，不证明当前driver配置已经满足，也不应触发自动复制凭证。

当前driver要求显式、私有、0600的 `--settings` 文件，并要求所选子CLI实际接受该隔离参数；不读取或改写共享配置。曾实测官方0.16.5 `app-server`不支持此参数，会失败关闭为68。具体命令、就绪屏障与退出码统一见24；缺少兼容能力时保持拒绝，不改全局认证或退回裸CLI。

## 3. 模型与接续

legacy driver只有在实际create/model/read核验成功后才发送任务；setModel失败不回退全局模型。独立CLI的原生 `/model`、账号套餐及Orca桥继续按28/30执行，不能从旧driver实验推导。

## 6. 旧启动章节指路

历史脚本注释指向本页§6时，转读24的“调用与控制接口”。保持原任务、Session、scope与完成身份，不重放旧无配置driver命令或headless长程配方。

本页可在所有旧诊断和调用方完成迁移后退役；原文、版本研究与实测记录保存在本Skill维护任务的归档索引中。

## 11. 发行版全景与上游 TUI 建模研究（2026-09-07，历史研究保留）

> 证据来源：stablyai/orca 未合并 PR #13965/#16227/#16228（guanbear 系列，实现
> "ZCode as a first-class supported agent"，issue #10564）的完整 diff 阅读 +
> 本机实测（桌面端 0.16.5、npm registry 查询、`~/.zcode/cli/config.json`
> 结构、`ps` 进程观测）。上游设计**未合并、非既成事实**；标注"未本机验证"的
> 结论不得写成已验证能力。

### 11.1 官方捆绑版与社区非官方 TUI 客户端

| 维度 | 官方桌面捆绑版（本 skill 现用） | 社区非官方客户端 |
|---|---|---|
| 入口 | `~/.local/bin/zcode` → `/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs`（symlink） | `node_modules/zcode-app-cli/bin/zcode.js` |
| 归属 | 智谱官方（随 App 分发） | kingsword09 `zcode-app-cli`（npm，MIT，**非官方**，README 自述 not affiliated with Z.ai） |
| 版本线 | 0.16.x（随 App 演化，本机 0.16.5） | 3.11.2-21（客户端自有版本线） |
| `--version` 输出 | 裸版本号（如 `0.16.5`） | `zcode-app-cli X.Y.Z`（**发行版探测的特征位**） |
| 交互 TUI | ❌ 缺 `@zcode/tui`（§5.1） | ✅ 自带 TUI（`@earendil-works/pi-tui`）；**实现方式=从 ZCode Desktop 提取官方 `glm` 内核作 node 子进程**，凭证/agent/工具逻辑仍在官方内核，客户端只补 TUI 层 + macOS OAuth 回调桥 |
| 进程标题 | `zcode-cli`（+ 同伴 `zcode-host-local-1` 桥接进程，本机 `ps` 实测） | `zcode-cli`（上游 entrypoint-identity 识别规则） |
| 运行时形态 | App-Service 背书：CLI 连接桌面 App 的 host 桥 | 官方内核直跑（提取自桌面端安装） |
| 配置面 | `~/.zcode/cli/config.json` | 同路径但**不覆盖既有文件**；可从桌面端导入 provider 设置，凭证需重新登录 |

上游用 `zcode --version` 输出是否匹配 `^zcode-app-cli\s+\S+` 区分二者；
桌面捆绑版输出裸版本号不命中 → 一律走一次性 argv 注入。**该探测依赖版本
输出形状这一未承诺契约**——两发行版版本号独立演化，任何一侧改版式都会
静默改变分流结果（本 skill 若未来采用同类探测，须带失效兜底）。

### 11.2 上游的三层 TUI 建模（对独立发行版才生效）

1. **注入分流**：`agent-input`（等 TUI composer 就绪后粘贴 prompt）vs
   `startup-command`（argv 一次性）。远程会话、用户命令覆盖、交互失败后的
   10 分钟冷却期一律 fail-closed 落到 startup-command。
2. **就绪三重门**：进程 ready（entrypoint 识别为 `zcode-cli`）→ composer
   input-ready（draft-paste-ready 扫描器盯 bracketed-paste `?2004h` 等信号，
   区分 shell 光标与真正的 agent composer）→ hook 上报 provider session
   （`session_id`；10 秒等不到则警告"输出回退终端显示"）。
3. **状态不走 TUI 刮取**：生命周期事件走 Claude 兼容 hook（POST 到编排方
   本地端口）；会话记录直接读 ZCode 自己的 SQLite 会话库（同 §3
   `~/.zcode/cli/db`）。TUI 终端只是启动面与兜底显示面。

对本 skill 的含义：driver（app-server 长驻协议）+ headless 的双路径对桌面
捆绑发行版仍是正确设计，与上游对"签名桌面运行时"的降级处理一致；若未来
需要交互 TUI worker，前置条件是安装社区客户端 `zcode-app-cli`（非官方，
信任决策归用户；bin 名同为 `zcode`，安装后必须 `which -a zcode` 核对未遮蔽
官方软链——本 skill 的 zcode backend 与 credential-sync 均假设软链指向官方
bundle）并重验 §11.1 特征位。

### 11.3 ZCode hook 能力（上游证据，未本机验证）

上游 PR 向 `~/.zcode/cli/config.json` 的 `hooks.events` 写托管块，事件集为
`SessionStart / UserPromptSubmit / PreToolUse / PostToolUse / PostToolUseFailure /
PermissionRequest / Stop`，payload 为 Claude 兼容格式（`session_id` 等字段，
上游直接复用 kimi 的归一化器）。配置结构：顶层 `hooks: { enabled, events:
{<事件名>: [{matcher, hooks: [{type, command, enabled, timeoutMs}]}]} }`（JSON
对象树，非 TOML）。若本机验证成立，install-guard（§8）与 worker 状态观测
（PM 巡检可用 hook 事件替代/补充 driver 渲染行）都有升级空间。

**并发写风险（本机实证）**：`~/.zcode/cli/config.json` 是多写者文件——本机
存在 `.bak-pm` / `.bak-pm2` / `.bak-zcode-worker` 备份（本 skill 自己的
credential-sync 与 worker 流程产物），桌面端、CLI、编排方都可能改写它。
任何 hook 安装/凭证同步必须：改前备份、原子写（临时文件 + rename）、改后
校验；不得假设自己是唯一写者。

## 版本记录

- 2026-08-27：协议全链真机验证（偏好应答/create/send/stop/注入）；backend
  转正（Task-077）：identity gate、driver、render、deps、测试矩阵、端到端
  两轮产物验收。
- 2026-09-07：发行版全景修订（§1/§5.1/§8/§11）——发现社区**非官方**终端
  客户端 `zcode-app-cli`（kingsword09/zcode-cli，MIT，v3.11.2-21，`--version`
  带 `zcode-app-cli` 前缀、自带交互 TUI；实现=提取桌面端官方 glm 内核直跑，
  凭证逻辑留在官方内核），"无 TUI"改为按客户端区分、"官方无独立 CLI 分发"
  维持成立；上游 orca PR #13965/#16227/#16228 的 TUI 建模研究（注入分流/
  就绪三重门/hook+SQLite 状态通道——其交互路径特征位锚定的正是这个社区
  客户端）与 config.json 多写者并发风险入册。社区客户端与 hook 能力均未本机
  验证，验证项见 TASKS `TASK-2026-09-07-ZCODE-DISTRIBUTION-RESEARCH`。
