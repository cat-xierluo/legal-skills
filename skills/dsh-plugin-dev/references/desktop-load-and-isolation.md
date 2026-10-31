# Desktop 装载与隔离实验（DSH Desktop 2.0.15 / 0.1.7-rc.2 实测）

> **宿主现状（2026-10-20 更新）**：第三方外壳 `DSH Desktop.app` **已卸载**（用户决定，1.9G）。本文以下内容基于该外壳的**历史实测**保留（时点语义），其中 `/Applications/DSH Desktop.app/...` 路径**已不存在**，照抄会失败——当前宿主基准见文末「官方宿主对照」节。
>
> **宿主口径提示（2026-10-19 更正）**：本文以下全部内容基于**第三方外壳** `DSH Desktop.app`（`ai.deepseek.dsh.desktop`，个人证书 anywhere-labs）实测，**它不是官方应用**。官方应用是 `DeepSeek Harness.app`（`com.deepseek.dsh`，DeepSeek 公司证书 + `download.deepseek.com` nightly）。两者内嵌**同一**官方运行时版本（0.2.1-rc.2），故**插件面向运行时 API、外壳不参与**——本文多数宿主级结论可外推；但 **GUI 层、外壳专属 flag、`desktop-cli.js` 入口、profile-selection 机制不可外推**。
> 官方应用的等价入口与差异见文末「官方宿主对照（2026-10-19）」节。宿主基准已按用户决定切至官方应用（见 `config/dsh-upstream.json` 的 `hostPolicy`）。

出处：dsh-plugins 仓 DSH-002 与五次装载实验（docs/evidence/dsh-{env,002-gui-experiment,pilot-load,bizlink-load,consumer-selftest,slice3-load}-20260929）。

## 版本锚定（一切的前提）

- 本机安装的桌面 App 内嵌全部 `@deepseek-ai/dsh*` 运行时（`/Applications/DSH Desktop.app/Contents/Resources/app/node_modules/`）——**内嵌版本才是真实契约**（2.0.15 → 0.1.7-rc.2 = npm `latest`；`next` 是预发布线，没有任何桌面版内嵌）。
- 研究所依据的源码 tag 必须与内嵌版一致；错位研究（如按 0.2.0-rc.1）的接口结论必须按实物重核。
- 桌面仓库（anywhere-labs/deepseek-harness-desktop）release = 外壳版本线（2.0.x），与运行时 0.1.x 是两条线。

## 装载路径（profile 工作区）

- DSH home 默认 `~/.dsh`；profile 在 `~/.dsh/profiles/<名>/`：package.json（`dsh.profile.bundles` 数组 + dependencies）+ cordis.yml（空表）+ cordis.patch.yml（配置覆盖）+ pnpm-workspace.yaml。
- **GUI profile 必须直接包含 `@deepseek-ai/dsh-web-app`**（dsh-base 之后）——缺了 selectableProfile 直接拒绝启动（error: "must directly include dsh-base before dsh-web-app"）；headless/CLI profile 无此要求。
- **官方 bundle 从安装锚点解析**（桌面打包 node_modules）——profile 里**不需要**物化 @deepseek-ai 依赖；本地插件用 `link:` 依赖 + `node_modules/<scope>/` 符号链接即完成"零物化装载"（无网络拉包）。
- 组合层序：profile bundles → profile cordis.patch.yml → home 级 cordis.patch.yml → `--patch`。
- 桌面专属 flags：`--dsh-desktop-workspace=<路径>`、`--dsh-desktop-safe-mode`（一次性隔离环境）、`--dsh-desktop-recovery`；启动器 flags：`--profile`、`--patch`。

## 隔离实验标准流程（五次实测收敛）

1. **快照**：`~/.dsh` 顶层/profiles/sessions 目录列表 + 共享 userData 的 `profile-selection/state.json` 内容。
2. **退出生产**：`kill -TERM <pid>`（SIGTERM 触发内置关停协调器，干净退出的标准方式）→ **循环探测进程真正消失**（每次 sleep 3，最多 8 轮）→ 确认后才算退出。
3. **切 selection**：写 `~/Library/Application Support/DSH Desktop/profile-selection/state.json` 为实验 profile（version 2 格式）。
4. **隔离启动**：`DSH_HOME=<隔离目录> nohup "/Applications/DSH Desktop.app/Contents/MacOS/DSH Desktop" >> stderr.log 2>&1 &`——全新 home 自动自举默认 desktop profile 与模板凭据。
5. **验证**：宿主日志 `~/Library/Application Support/DSH Desktop/logs/host/dsh-<date>.log` grep 插件激活标记（`[<插件name>]`）；error log 查相关报错；依赖物化需网络时等待或观察 node_modules。
6. **分步退出**（同 2）→ **恢复 selection 原值** → `open -a "DSH Desktop"` 恢复生产 → 比对快照。

### 隔离盲点与坑（实测）

| 现象 | 根因 | 处置 |
|---|---|---|
| 实验后生产 profile 变了 | **profile-selection/profile-preferences 按共享 userData 存放**，`DSH_HOME` 隔离不了它；隔离 home 无 profile 时应用回退创建默认并改写选择 | 实验前后快照/恢复该文件（流程 1/6） |
| 每次启动重弹基础配置向导 | 向导完成态在 `userData/profile-setup/<homeHash>/state.json`；只有 `.pending` 就重弹 | 按完成态 schema 补种（7 字段按排序比较、profileHash 须与路径哈希一致、outcome=completed/skipped、version=2；解析器 profile-channel-admission） |
| `open -a` 恢复"没反应" | 单例锁把启动请求**转发给尚存活的实验实例**（ premature 恢复） | 退出验证与恢复命令**分步执行、逐门通过**——曾因此时序竞态二次 SIGTERM |
| renderer 偶发 boot failed | 30s 健康超时；两种形态（compatibility-chrome.html ERR_FAILED / Unknown client plugin），五次实验两现。**语义解码（2026-09-29 静态归因）：「Unknown client plugin」是显示伪影——插件列表为空时的占位文案，而主进程超时路径恰好构造空列表报告；真实含义 = 渲染器 30s 整体静默（未到插件枚举），与被测插件无关** | Host 侧不受影响；GUI 级验收（截图/交互）前需定位；三假设（资源竞态/首启路径/系统代理）与判别复跑方案见 dsh-plugins `docs/research/2026-09-29-renderer-static-diagnosis.md`；隔离 home 种子 cordis.patch.yml 只留本实验 insert 行（生产皮肤残留只警告但添噪）。**2026-10-11 内容工厂 W7 实证补充**：系统代理（scutil --proxy HTTPProxy:1082）瞬断时段该静默**稳定复现**（非偶发两现）——`--no-proxy-server` 不解除（静默在 Renderer boot health 上报层）；代理恢复后同 profile 正常。 **同日终轮补充（5 连败实测）**：坏窗口内 `--proxy-server='direct://'` 同样不解除；**单次 curl 经代理外网 200 不能预测窗口好坏**（窗口分钟级翻动，须直接试 boot）；坏窗口内挂死实例 **SIGTERM 可能无响应须 kill -9**；GUI 模式 stdout **不打印 token 行**（token:0 非故障信号）。处置=择机重试（好窗口内同配方一次成功），不盲改插件与配置。另两条新增前置坑：共享 userData profile-selection 指向隔离 home 不存在的 profile 必进恢复模式（恢复助手「切换 Profile」UI 可切）；profile 级 cordis.patch.yml **只有注释行会被拒**（须顶层数组，`[]` 即合法） |
| 全屏截图取证 | 会截到用户无关私人窗口 | **不用全屏截图做宿主证据**；Host 半体以宿主日志为权威 |

## 并行测试实例（不影响正在使用的 DSH，2026-10-11 双实例共存实证）

**问题**：Desktop 调试每次都要 SIGTERM 生产实例（单例锁 + 共享 userData 的 profile-selection 循环），打断正在使用的 DSH。

**解法**：`--user-data-dir=<隔离目录>` 开完全并行的第二实例——独立单例锁/独立 profile-selection/独立向导态/独立 Cookies，与生产实例**同时运行互不干扰**（实测双 pid 共存：并行实例侧栏=内容工厂，生产实例侧栏=常驻任务/合同审查各自插件集）。

```bash
# 1) 隔离 userData 预置（自带 selection + 向导完成态）
UD=<隔离userData>; mkdir -p "$UD/profile-selection"
echo '{"version":2,"active":"<测试profile>"}' > "$UD/profile-selection/state.json"
PH=$(python3 -c "import hashlib;print(hashlib.sha256('<DSH_HOME>/profiles/<测试profile>'.encode()).hexdigest())")
mkdir -p "$UD/profile-setup/$PH"
cat > "$UD/profile-setup/$PH/state.json" <<J
{"version":2,"profileHash":"$PH","outcome":"skipped","desktopVersion":"2.0.15","dshVersion":"0.1.7-rc.2","setupRevision":1,"recordedAt":"2026-10-11T15:30:00.000Z"}
J
chmod 700 "$UD/profile-setup" && chmod 700 "$UD/profile-setup/$PH" && chmod 600 "$UD/profile-setup/$PH/state.json"
# 2) 并行启动（生产实例保持运行）
DSH_HOME=<隔离home> CONTENT_FACTORY_SCAN_ROOT=<夹具> \
  "/Applications/DSH Desktop.app/Contents/MacOS/DSH Desktop" --user-data-dir="$UD"
```

**权限坑（实测）**：向导完成态校验要求 **state.json 600 且其父目录链 700**（`state directory permissions must be 700`——只 chmod 文件不够）。

**注意**：① 并行实例窗口出现在用户桌面前台——用户可能误当生产实例操作（实测撞见 textarea 出现用户输入），测试完及时关闭并行实例或提前告知；② 生产实例全程零接触（无需 SIGTERM/无需改共享 userData——那是旧配方）；③ `--profile` 参数在 GUI 模式被忽略，profile 由该实例自己 userData 里的 selection 决定。

## 无 GUI 验证入口

`ELECTRON_RUN_AS_NODE=1 "<应用>" --expose-internals "<应用>/lib/desktop-cli.js" <dsh 参数>`（`DSH_HOME` 同样生效；`DSH_DESKTOP_DEFAULT_PROFILE` 注入默认 profile）——`--version` 冒烟、headless 任务等无窗口场景用它，绕开单例锁。

## 生产数据红线

默认不读 `~/.dsh/sessions`、`.credentials.yaml`、settings 文档、storages；状态比对只到 ls 级目录名元数据。关停生产实例前后向用户报备（授权流程）。唯一例外是用户明确授权“隔离实例复用现有登录/API 配置”：只把最小必要账号记录、API 引用与 provider 配置快照到隔离 `DSH_HOME`，保留隔离实例自己的 `client-connection/browser-session` 记录；不输出明文、不提交凭据、不复制生产 sessions/storages/profile，不写生产配置。

## 官方宿主对照（2026-10-19 实测，基准宿主）

官方应用 `/Applications/DeepSeek Harness.app`（`com.deepseek.dsh`，公司证书 NAN929V4UM，`download.deepseek.com` nightly）与第三方外壳的差异**全在外壳层**，运行时同版本（`@deepseek-ai/dsh@0.2.1-rc.2`）。

| 维度 | 官方应用 | 第三方外壳 |
|---|---|---|
| 签名 / 更新源 | DeepSeek 公司证书 / 官方 nightly | 个人证书 / GitHub anywhere-labs |
| GUI 用的 profile | **硬编码** `~/.dsh/profiles/desktop` | `profile-selection` 指向 `web`（有 GUI 切换器） |
| profile 切换 GUI | **无**（启动器层 `dsh --profile`） | 有 |
| CLI 管该 profile | **拒绝**（`managed exclusively by the Electron application`） | 允许 |
| headless 入口 | asar 内 `dsh/node_modules/@deepseek-ai/dsh/lib/bin.js`（**无** `desktop-cli.js`） | `app/lib/desktop-cli.js` |
| 插件市场 | 官方 Discover（bundle 默认关）+ 社区 `dshmarket` 侧栏页 | `dsh-community-market` + `dshmarket` |

**官方应用已实测验证的宿主验证配方**（第三方外壳卸载后，仓内 8 个可复跑脚本已全部改指此路径并实测通过）：

```bash
APP="/Applications/DeepSeek Harness.app"
EXE="$APP/Contents/MacOS/DeepSeek Harness"
CLI="$APP/Contents/Resources/app.asar/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js"
# 官方 CLI 直接接受 --profile（无第三方外壳的 DSH_DESKTOP_DEFAULT_PROFILE 等价物）
DSH_HOME=<隔离目录> ELECTRON_RUN_AS_NODE=1 "$EXE" "$CLI" --profile <名> --no-open --port <端口>
```

**官方宿主的三个易踩点**（实测）：

| 现象 | 原因 | 处置 |
|---|---|---|
| `python: is_file()` 对 asar 内路径恒 false | asar 是打包文件，OS 层不可读其内路径（**Electron 运行时才可解析**） | 宿主工件锚定用 `app.asar` 本身（可读、可算 sha256）；版本取 `Info.plist` 的 `CFBundleShortVersionString`（官方应用与内嵌运行时同源同版本） |
| `dsh plugin install` 在 link 依赖场景抛 atomic-write 锁错误 | 官方 CLI 的 plugin 子命令对 link 场景不稳 | 改用**官方内嵌 pnpm** 在 profile 目录内 `CI=true node "$PNPM" install`（`app/Contents/Resources/runtime/primary-runtime/dependencies/pnpm/bin/pnpm.cjs`，11.28.5，store v11；`CI=true` 免去无 TTY 下拒绝清目录） |
| `dsh plugin --profile desktop ...` 报 `managed exclusively by the Electron application` | 官方 CLI 拒绝管理 GUI 硬编码的 desktop profile | 官方 GUI 装插件走「插件 → + 添加插件」；脚本侧用 pnpm 直装 |

**官方应用 headless 入口配方**（替代 `desktop-cli.js`）：

```bash
APP="/Applications/DeepSeek Harness.app/Contents/MacOS/DeepSeek Harness"
BIN="/Applications/DeepSeek Harness.app/Contents/Resources/app.asar/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js"
DSH_HOME=<隔离目录> ELECTRON_RUN_AS_NODE=1 "$APP" "$BIN" --profile <名> --no-open --port <端口>
# --version / --dump-config / --dump-config-schema / headless 任务 均可用
```

**官方 GUI 隔离实例**：官方应用无 `profile-selection`，但支持 `--user-data-dir=<隔离目录>` 起并行实例（独立单例锁/独立向导态）；`--profile` 在 GUI 模式被忽略（profile 由 profile 目录本身决定）。官方应用同样支持 `DSH_HOME` 隔离。

### 官方 rc.5 并行实例定位（2026-10-31 实测）

多个插件同时验收时，官方应用可以用两个真 Desktop 进程并行：日常实例继续使用生产 `DSH_HOME` 与生产 userData；测试实例同时提供 `DSH_HOME=<隔离目录>` 和 `--user-data-dir=<隔离目录>`。两者不要互相关闭，测试实例只允许操作本任务启动的 PID。

1. **实例归属**：先只读记录日常实例 PID，再启动测试实例并把 PID 写入仓外实验目录。后续所有关闭动作只匹配该 PID，并用 SIGTERM 分步等待主进程、Host 子进程和监听端口消失。
2. **避免原生 CUA 抢错实例**：同 bundle 多进程时，原生 CUA 的名称/路径/bundle ID 选择会命中日常实例；不要用它操作测试页面。测试实例启动时加 `--remote-debugging-port=<空闲端口> --remote-debugging-address=127.0.0.1`，通过 `http://127.0.0.1:<端口>/json/list` 精确连接本实例的 `dsh-app://app/` 目标；端口只绑定 loopback，URL/WebSocket 目标不写入公开日志或证据。
3. **授权配置复用**：默认仍不复用生产凭据。用户明确要求免登录时，按上文生产数据红线做最小快照；测试实例可能出现产品内一次性额度/设置提示，这只是 onboarding，可在可见 UI 中跳过，不得伪造完成态或绕过认证。
4. **rc.5 原生代理停滞判别**：若插件首开 RPC 停在 provisional/pending，而关闭重开插件页或页面内直接 `fetch('/api/<route>')` 能返回，优先怀疑官方 `dsh-app://` shell 转发层而非插件 `connection.fetch.register` 精确路由；插件侧可加有界 RPC transport 超时，不把上游 shell 问题说成已修复。
5. **证据边界**：整窗截图只截本 PID 拥有的窗口；凭据快照、启动 token、生产会话与真实客户材料不入库。合成材料验收通过不外推生产安装、跨用户/ACL 或 Windows。

**官方 GUI 装插件**：CLI 禁管 desktop profile ⇒ 走 GUI「插件 → + 添加插件」（支持包名 / GitHub 地址 / 本地目录路径），或直接用**官方内嵌 pnpm**（`app/Contents/Resources/runtime/primary-runtime/dependencies/pnpm/bin/pnpm.cjs`，11.28.5，store v11）——系统 pnpm 10 用 store v10 会报 `ERR_PNPM_UNEXPECTED_STORE`。

**跨宿主迁移纪律**：迁 profile 配置时**「定向禁用」条目必须一并迁**（它们同样是为兼容旧宿主而写的可移植配置），否则旧宿主专属的 client 工件会在新宿主的模块表上 import 失败，并因「1 个 client 条目失败即终止整个 web boot」而导致应用整体起不来。社区插件是**绑宿主**的，异常先查 peer 声明。

出处：`docs/evidence/official-app-hostverify-20261019/`（verification.md / official-market-and-profile-facts.md / migration/verification.md）。
