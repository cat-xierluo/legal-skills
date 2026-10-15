# ZCode GUI 远端作者直发 PR 合同

用户明确指定由远端机器上的官方 ZCode GUI worker（"远端 GUI 作者"）自行完成文档或工程交付的 Git 发布（safe-push + 唯一 draft PR），PM 只做只读核验时，读取本页。本页不改变 CLI/Orca 派发门禁，不是 `spawn-worker.sh` 的 backend 枚举，也不是 Orca GUI 监督适配器：不要为 GUI 会话假造 Orca Run/Task/Dispatch，不要用 UI 卡片或回合完成冒充 `worker_done`/Delivery。

## 1. 通道与模型事实

- 官方 ZCode GUI（桌面与本地 Web）与开源 CLI 是不同发行物：GUI 使用自己的模型内核与账号通道。远端 GUI 作者在 GUI 内运行（本合同实测为 GLM-5.3、个人 Coding Plan、完全访问，由真人具名指定），不得默换 Flash、不得改走独立 CLI、不得切换账号或复制凭证。GUI 会话的授权、预算与文件范围独立核查，不因 GUI 可用而放宽 CLI 侧门禁。
- 连接选择 localhost 优先：同一宿主直接使用本地 Web 页面。跨机时使用官方远控连接目标宿主上已运行的同一会话页面，操作逻辑与本地相同——PM 在浏览器中对同一页面派发与回读，而项目文件、模型内核、额度上下文与原生记录都在目标宿主上；同名项目或同步目录不能证明目标机版本一致，派发前在目标机核工作区绝对路径、Skill 版本与资源预算。
- Start Plan 与 150% 权益分两类证据记录：真人确认事实（2026-10-02 用户明确确认本地 Web 可用全部桌面功能，含 Start Plan 及 150% 优惠，作为该用户选路依据）与运行 provider 实测（从实际回合的原生 provider 记录读取）。两类不混写；作者不得自行声称查过扣费账单或倍率，未复测不否定真人确认，也不阻塞已授权使用。

## 2. 发布链合同（顺序不可跳）

每步的证据要求如下，任一步失败停在原地对账，不盲重试 mutation：

1. **remote 作者自测**：作者在原会话内完成 scoped 验证（白名单 diff、链接可达、版本一致、敏感串检查等），真实执行命令并记录退出码；不跑全量、不安装新依赖。
2. **固定 head**：作者 commit 后取得 40 位不可变 head，后续所有审查、返修与发布都绑定该 head；返修产生新 head 时重新固定并重新独审。
3. **不同 SID 独审**：由另一个 GUI 会话身份（不同 SID）对内容与来源逐项独立审查。独审者不能是作者本人，不能自审自报；审查对象是内容正确性与事实来源，不以文件哈希代替语义审查。一次接收不等于交付：作者收到 ACCEPT 只是进入下一步的资格。
4. **原 session 返修**：审查发现问题（REJECT/整改项）时，作者在原会话沿原任务返修，不另开会话、不重派同题任务；返修后回到第 2 步重新固定 head。
5. **fresh 身份/唯一性核查**：发布前重新核 GUI worker 自己的 `gh` 认证（`gh auth status` 退出码）、目标仓库 push 权限（`gh repo view --json viewerPermission`）、Git 传输（默认 HTTPS）与分支唯一性（无同名远端分支、无既有开放 PR）。核查必须是发布时点的新鲜证据，不复用旧时点结论。
6. **safe-push**：按绑定的提交链校验后以不可变 OID 推送专属分支；不 force push、不 push 到 main、不改写他人工作树。
7. **唯一 draft PR**：作者用自己的 `gh pr create --draft` 创建指向 main 的唯一 PR；PR base、head、标题与交付内容一致。不创建第二个 PR，不让 PM 搬运 bundle 代发。
8. **PM 只读核验**：PM 从 GitHub（网页或 API）核对 PR 的 head 与独审 fixed head 一致、base=main、draft 状态、files 与白名单一致、checks 结果。PM 不代发布、不改分支；核验通过才进入人工 merge 决策。

## 3. 已验来源（具名）

- PR257：https://github.com/cat-xierluo/legal-skills/pull/257 ，head `5fd910593252186c4aeeb1328c969527971d827a`
- PR258：https://github.com/cat-xierluo/legal-skills/pull/258 ，head `f857365d9f3e0a0d0b7b9039584e82b02cb976ad`
- 两 PR 由两位不同 GUI SID 的远端作者交叉完成 R1 独审并互相 ACCEPT；PM 实际定向核验 11/11 与 8/8 及负例，角色/身份/postflight 检查 PASS。
- 两 PR 均为 OPEN、DRAFT、base=main，fixed head 与 runtime-settlement 检查 SUCCESS，未 merge。
- 发布动作由远端 GUI 作者自己的 safe-push 与 `gh pr create` 完成，PM 只读核验；原生工具实测 `SAFE_PUSH_OK` 与 `IDENTITY_GATE_OK`，GUI 自己的 `gh auth` 退出 0、仓库 push 权限为 true、Git 默认 HTTPS 推送成功。
- HOST_HEARTBEAT 证明监测在实际 tick，不证明长期稳定的自动闭环。

正式证据的权威在原技能 TASKS 中的两份完整任务卡；公开文档只保留上述 PR 链接与有限证据摘要，不堆私有 SID、连接参数、绝对私有 state 路径或账号配置。

## 4. 通道故障与认证边界

- PR 不可用（push 或 `gh` 失败）时，fresh 核 GUI worker 自己的 gh/Git/TLS/权限；PM 侧 helper 的认证失败（AUTH_UNAVAILABLE）或 TLS 失败（TLS_FAILURE）只是旧通道旧时点的事实，不能推出 GUI worker 同样失败，环境差异根因标 NOT_VERIFIED。
- 报告中出现过的无效 `http.tlsVersion` 配置不是成功配方，不得当作修复手段复制。
- 禁止向远端传凭证、复制凭证、改账号或关闭 TLS 验证来"修复"通道；官方登录若确需真人介入，保留已完成的工程成果并标注外部依赖，不伪造登录成功。

## 5. 合同更新与历史保真

- 本合同由初始"禁 push"版本沿原作者具名反馈演进为"作者直发"；历史记录不改写，演进以 CHANGELOG 与 DECISIONS 追加。
- 记录真实 SID/input/parent/turn/provider；字段缺失时明确"未提及/待补充"，不臆测补齐。
- completed 不等于验收：回合终态只是执行事实，业务验收由 PM 独立完成；模型预算与失败 episode 累计不清零，跨轮次继续计数。

## 6. 资源与预算收口

- 最大活跃 worker 与待验 PR 背压约束照旧适用；用户为特定卡授权的 GUI budget=0 遥测只对该卡有效，不能推广为一般放宽 CLI 门禁。
- helper 进程与浏览器 tab 按 owner/runtime/incarnation 归属专属收口：谁启动谁停止，操作后复核端口与子进程退出。宿主面板显示 closed 不证明 OS 进程已退出；无法核实的收口一律标 NOT_VERIFIED，不声称零残留。

## 7. 待验（NOT_VERIFIED）

- 浏览器 driver 脚本的真实自动新模型投递与长时全自动稳定性未验收；PM 实际浏览器派发→回合监控→独审→作者发布链已实测，两者不可互推。
- 本文档候选的无旧上下文前向运行未做，按 NOT_VERIFIED 记录；发布前仅完成 scoped 静态核验与不同 SID 内容独审。
