# Desktop 装载与隔离实验（DSH Desktop 2.0.15 / 0.1.7-rc.2 实测）

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
| renderer 偶发 boot failed | 30s 健康超时；两种形态（compatibility-chrome.html ERR_FAILED / Unknown client plugin），五次实验两现 | Host 侧不受影响；GUI 级验收（截图/交互）前需定位；定性勿过度（非每次发生） |
| 全屏截图取证 | 会截到用户无关私人窗口 | **不用全屏截图做宿主证据**；Host 半体以宿主日志为权威 |

## 无 GUI 验证入口

`ELECTRON_RUN_AS_NODE=1 "<应用>" --expose-internals "<应用>/lib/desktop-cli.js" <dsh 参数>`（`DSH_HOME` 同样生效；`DSH_DESKTOP_DEFAULT_PROFILE` 注入默认 profile）——`--version` 冒烟、headless 任务等无窗口场景用它，绕开单例锁。

## 生产数据红线

不读 `~/.dsh/sessions`、`.credentials.yaml`、settings 文档、storages；状态比对只到 ls 级目录名元数据。关停生产实例前后向用户报备（授权流程）。
