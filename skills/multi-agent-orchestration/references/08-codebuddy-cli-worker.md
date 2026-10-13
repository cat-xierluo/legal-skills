# CodeBuddy worker 操作指南

用户明确选择 `codebuddy` 时读取本页。它保留为可选 backend；日常选择与 PM host 权限以 [SKILL](../SKILL.md) 和 [policy](../config/harness-backend-policy.json) 为准。CodeBuddy PM 只可派自身，不从 CLI 产品能力表推导其他派发权限。

## 1. 检测实际入口

```bash
bash scripts/check-dependencies.sh --backend codebuddy --strict
```

检测先查 PATH，再查已知 WorkBuddy app bundle。renderer 的默认 bundle 路径为 `/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy`，也可用 `--bin` 指定本次已经核实的 CLI。

PATH 缺失不等于未安装。直接使用检测到的入口，不为消除警告修改 shell 配置、创建全局软链或重装应用。首次登录/信任问题按当前原生界面处理；已有桌面登录不能替代本轮 CLI 就绪与实际认证核验。

软件更新后用当前 CLI 帮助确认必要参数。认证和真实模型配置留在原私有配置中，不复制到公共任务文件或日志。

## 2. 生成启动命令

长程可交互任务先生成 interactive 命令，再交给正式 spawn：

```bash
bash scripts/render-runtime-profile.sh \
  --backend codebuddy --mode interactive \
  --bin /absolute/path/to/codebuddy \
  --model selected-model --output command
```

上述命令只渲染文本。完整派发仍消费本轮 project/branch/session、范围、验证、预算和原任务身份；使用 [dispatch profile](32-dispatch-profiles.md) 与 [Orca worker 合同](13-orca-cli-worker.md)，不要另建 native worktree/tmux 绕过这些准备步骤。

### 参数与当前行为

| renderer 参数 | 行为 |
|---|---|
| `--model` | 生成原生 `--model`；使用本轮明确选择且实际可用的模型 |
| `--permission-mode` | interactive 未指定时为 `acceptEdits`；显式值可透传，包括 `bypassPermissions` |
| `--no-skip-permissions` | 显式关闭默认附加的 `-y`，不是取消任务范围 |
| `--with-mcp` | 显式启用当前 MCP 配置；默认生成 strict 空 MCP 配置 |
| `--add-dir` | 可重复指定必要额外目录；spawn 侧相应登记允许访问的范围 |
| `--mode batch --prompt-file` | 当前代码支持生成 `-p --output-format stream-json`；默认权限值为 `bypassPermissions` |

renderer 默认附加 `-y`，除非显式选择 `--no-skip-permissions`。生成参数不证明某 CLI 版本的实际权限语义：在原任务会话读回权限与等待状态，区分工具许可、目录访问、信任、登录和用户问题。

历史文档曾称 batch 已移除，同时又推荐 batch；以当前代码可渲染为事实记录。长程任务继续 interactive，已经按任务合同选定的有界 batch 能力保留；本次文档整理不改变默认值、增加模型请求或宣称两种模式都完成了新的实测。

## 3. 模型、provider 与 MCP

模型选择沿用户指定及私有 profile；不要从旧静态模型表、免费假设或账户余量自行更换。用原生会话、请求/用量记录和真实产物核对实际 provider/model，模型自述不作证据。

当前 renderer 对 CodeBuddy 使用既有环境继承路线；不因本页的旧 `env -i` 实验重建认证环境。确认任务需要的配置和认证来源，避免把其他 backend 的 provider 配方直接移植进来。

默认空 MCP 适用于本轮不需要 MCP 的任务。确需 MCP 时显式 `--with-mcp`，保留对应安装、网络、工具和材料范围；MCP 存在不代表业务已获授权。

并发和额度消费正式 provider/预算合同。历史“同账号不超过三路”只是当时观察，不替代当前配置，也不据此改用已移除的 QoderWork 或其他未选 backend。

## 4. 范围与权限

优先把本轮必要任务文件放在授权工作树/Session Context 中。确需跨目录时列出精确目录，在 renderer 与 spawn 两侧一致登记；不要为省一次提示添加整个 `/tmp` 或用户目录作为默认范围。

CodeBuddy 的 hook 配置由正式 spawn 路径安装/绑定。参考 [依赖和安装授权](02-runtime-dependencies.md) 与 [验收合同](18-dispatch-acceptance-contracts.md)；不复制历史手写 settings JSON覆盖项目已有 hooks。

执行权限、机械 scope/install hook、任务允许范围是不同事实。`-y`/`bypassPermissions` 不扩大任务范围，也不证明 hook 生效；仅有 prompt-only 降级时明确限制并验真实 diff。reviewer 的默认写范围仍仅为自身 Session Context，修被审分支需原合同中的显式授权。

旧“PreToolUse必定不可绕过”或由其他产品推导优先级的说法不能替代当前 backend 的验证。需要依赖机械阻断时消费该入口的真实证据，证据不足保持未验证。

## 5. 观察、接续和收口

先核精确 terminal/session/cwd 与本轮 Task，再读当前输入、原生状态和产物。Orca 下使用正式状态/终端接口；tmux 回退使用既有观察与发送合同，不能凭静态 screen 或旧日志认定已工作。

| 现象 | 最小检查 | 合法下一步 |
|---|---|---|
| 找不到 `codebuddy` | PATH、依赖检测报告及实际 bundle | 使用核实入口，不自动重装/改全局 PATH |
| 进程在但画面空白 | 精确进程/终端、新鲜输出、启动退出码、已配置 hook 错误 | 保留原身份定位；不批量删除全局 hooks |
| 权限或信任等待 | 当前请求、实际高亮选项、原命令和范围 | 仅处理已授权请求；每次操作后重读，不固定按2或盲Enter |
| accepted 后没有业务进展 | 原生输入是否消费、是否退回 shell、当前任务状态 | 沿原输入查明；不自动重发整份prompt或重spawn |
| 跨目录访问被拒 | 本轮范围、实际目录、renderer/spawn add-dir是否一致 | 在原任务允许范围内修配置，不能靠扩大目录绕过 |
| STATUS done但未见交付 | 实际diff、测试、提交/PR或约定产物 | 按原交付合同纠偏；STATUS不代替PM验收 |
| 额度/429停滞 | 新鲜额度、原生活动时间、具体pending输入 | 按 [20 限流恢复](20-orca-rate-limit-recovery.md)，不按旧横幅重复投递 |

输入文本和提交键分开处理并核结果。原生等待可能在输入过程中改变；“再补一次Enter”不能成为固定重试策略。恢复只使用已经核实的原 session/任务路径，保留失败与未知状态。

收口按 [PM合同](14-pm-orchestrate.md) 与 [资源回收](37-worker-resource-closeout.md) 核业务、运行资源和Git保留；主终端关闭不代表后代、额外 shell、监听端口或lease已全部结算。

## 6. 维护边界

本页是当前操作入口。旧版本权限冲突、Ping Island 排查、评测数字、模型价格、HTTP服务及captcha项目个案的原文保存在维护任务的归档索引中；不作为未来worker自动执行的处方。

修改本页时核 renderer、policy、spawn hook/范围合同及当前原生证据。只读命令生成可以验证参数映射；登录、模型请求、持续交互、机械阻断和完整资源收尾需各自真实验证，不能由文档精简或脚本能生成命令推定通过。
