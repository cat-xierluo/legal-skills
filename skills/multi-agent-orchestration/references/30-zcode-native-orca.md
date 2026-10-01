# 原生 ZCode CLI 接入 Orca

## 启动合同

仅在用户指定 `zcode-cli`，且 Orca runtime 为 1.4.218 或更新时，启用本路径。Orca 的 `worker-start --agent zcode` 等待真实首次 composer，再投递唯一 Task spec；它启动交互 CLI，不向 ZCode 传 `--prompt`。后续派发复用已结算且已证明空闲的原终端。

原生 worker-start 没有逐次设置 env/command 的接口。用 Orca 设置 → 智能体 → ZCode 的正式自定义命令配置启动桥，保留 MAO 已通过门禁后生成的环境、Session Context 与 authority 绑定。使用绝对路径：

```text
python3 /absolute/skill/scripts/zcode-orca-launcher.py launch --requests-root /private/launch-requests --default-zcode /absolute/bin/zcode --
```

请求目录必须是当前用户所有、0700、无符号链接的独立目录。保留用户原有默认智能体、模型、启动参数、权限和 hooks。普通工作区没有对应请求时沿用原生 ZCode 参数；存在匹配请求却无效、过期、冲突或已消费时拒绝，不自动改走裸 CLI。桥不读取私人账号库、不复制认证、不选择账号或耗卡。

## 派发与接续

在原有 spawn 参数中显式加入：

```text
--worker-backend zcode-cli --orca-supervised
--orca-zcode-native-requests /private/launch-requests
--allow-prompt-only-install-guard "用户已指定 ZCode CLI，此任务允许 prompt-only 安装边界"
```

继续提供完整 Task spec、verification contract、精确允许范围与 coordinator/runtime 身份。全部价值、额度、内存、provider lease、工作树隔离与 authority 门通过后才创建单次请求。请求绑定实际工作树、Session Context、启动脚本和 authority 摘要以及 runtime；启动桥原子消费并核对原生 terminal/worktree 身份，native start 回执必须与其相同。启动回执中的 `created` 只证明本轮创建。结算前重读 live ownership；原生用户接管后的 `user_owned/retained` 由 release 保护，不能靠旧 metadata 宣称仍可自动关闭。不得把 terminal close 当作 worker-release 的替代。

模型来自 ZCode 的原生配置；Orca 不接受 ZCode 的 `--model`。按 [BigModel 模型合同](28-zcode-cli-bigmodel-coding-plan.md) 在原生会话操作 `/model`，用真实请求证据确认模型和 provider。账户调度仍依 [本地 Skill 调用合同](29-local-account-routing-skill.md) 获取新鲜结果；启动校验不代表长期身份锁或持续预算控制。

收到合法 `worker_done` 后先验收真实结果。立即接续时，按当前 Orca 运行时指南把已证明的原终端移交给新 Dispatch；否则执行 worker-release，核对实际回执，再 ack 完整 Delivery。release 对用户接管终端返回 retained 时，记录保留原因；仅在用户明确授权精确终端后另行关闭并保留日志，不能绕过保护。STATUS、idle、commit、输入 accepted 均不能代替这条链。派发失败或结果不确定时保留 native receipt 和 residualResources，按原请求身份恢复，不自动重拉或双投。

## 验证状态

Orca 1.4.218 的真实 native 启动与两阶段只读任务已通过：同一 CLI/session/Dispatch 在 Flash 阶段完成35项测试，再经原生 `/model` 切至 GLM-5.3，消费正式指导、完成3项定向反例并发出唯一 `worker_done succeeded`；PM验收 Delivery、执行 release、再 ack。真实 release 返回 `retained/user_takeover`，保护当前 user_owned 终端；coordinator-owned 自动关闭仍 `NOT_VERIFIED`，精确清理尚待收口。启动 created、idle 或静态测试不能扩大此结论。以 TASKS 的 ZCODE-ORCA-NATIVE-INTEGRATION 卡维护最新结果，不类推其他后端。

## 官方依据

[Orca 1.4.218 发布记录](https://github.com/stablyai/orca/releases/tag/v1.4.218) 列入 `fix(zcode): wait for composer before first worker dispatch`。每次操作仍读取当前可执行文件 `orca skills get orchestration` 的匹配版本合同，不靠版本号类推其他后端或新的参数。
