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
