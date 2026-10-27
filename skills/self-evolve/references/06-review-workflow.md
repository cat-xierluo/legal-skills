# Review Inbox 工作流

## 目标

把“机器发现值得关注”与“用户决定采用”明确分开。任何自动化阶段都不得代替人工决定。

## 数据流

```text
session summary / cluster
  → privacy gate
  ├─ fail → review/quarantine（仅规则、计数、哈希）
  └─ pass → review/inbox + artifact hash
               ↓
          machine proposal
               ↓
       localhost human decision
               ↓
       applied → verified outcome
```

## 审阅顺序

1. 检查隐私状态必须为 `passed`，并核对产物哈希。
2. 检查目标 Skill 当前版本与 proposal 目标版本。
3. 检查是否已被现有功能覆盖，是否只是同修订重复证据。
4. 逐条审查 change points，必要时选择部分接受。
5. 记录原因；拒绝和部分接受必须给出可理解理由。
6. 人工修改目标资产并提交后，登记 commit hash。
7. 用真实或 synthetic 场景复验，登记 `verified`、`failed` 或 `inconclusive`。

## 人工决定

| 状态 | 含义 |
|------|------|
| `pending` | 尚未作出人工判断 |
| `accepted` | 接受当前修订的全部 change points |
| `partially_accepted` | 只接受明确列出的部分 change points |
| `rejected` | 当前修订不采用 |
| `observe` | 证据不足，继续积累但不实施 |

人工决定通过 localhost 面板或显式 CLI 追加写入，并同时绑定 proposal `revision_hash`、当前唯一 `review/inbox/` 逻辑路径与产物哈希。Deep proposal 产物先按内容寻址并 no-clobber 发布。接受或部分接受时，服务端必须通过目录文件描述符无符号链接地读取常规文件、现场核验 SHA-256，并把已核验字节固化到 `review/archive/proposal-artifacts/` 的 revision-bound no-clobber 快照；人工事件追加保存原路径和快照路径。缺失、篡改、多路径、路径逃逸或符号链接一律拒绝。只允许对 inventory 中唯一解析且版本/内容状态明确的目标执行接受或部分接受；路径、内容或其他修订输入变化后必须重新审阅。机器后续 upsert 可以补充证据或改变机器处置，但不能覆盖人工事件；applied 验证决定快照，不依赖随后可能变化的 Inbox 文件。

## 安全边界

- 面板只绑定 loopback，并要求 nonce；
- 面板不修改外部 Cron 的启停或时间表；
- Review Inbox 不展示原始 transcript；
- quarantine 不保留命中原文；
- 不从 Markdown 勾选框推断规范状态；
- 不允许机器身份写入 human decision。
- JSONL 事件截断、坏行、重复事件 ID、冲突终态或非法生命周期顺序一律失败关闭，不用“跳过坏行”伪造健康状态。
