# 提案评估闭环

## 状态模型

把机器处置、人工决定、实施记录和验证结果存为不同维度：

```text
machine_disposition
  filtered | candidate | duplicate | covered | recommended

human_decision
  pending | accepted | partially_accepted | rejected | observe

application
  not_applied | applied(commit)

outcome
  pending | verified | failed | inconclusive
```

不要把这些维度压成一个“状态”字段，否则机器重算会覆盖人工判断。

## 稳定身份与修订

使用以下稳定输入计算 proposal fingerprint：

- 目标 Skill；
- proposal 类型；
- 排序、去重并归一化后的 change points。

再用目标版本、目标内容哈希、目标解析状态、证据 ID、change points、当前唯一 Inbox 逻辑路径和产物内容哈希计算 revision hash。同一 fingerprint 的新证据应更新机器记录；`artifact_paths` 只保存当前修订绑定，不跨修订累加。revision 未变化时不得重复创建提案。接受前必须确认目标能在当前 inventory 中唯一解析且存在有效内容哈希，通过文件描述符重新读取当前产物核验 SHA-256，并把已核验字节发布为 revision-bound archive 快照。

## 新颖性判断

生成 `recommended` 前至少检查：

1. 目标 Skill 是否仍存在；
2. 当前版本是否已经覆盖建议；
3. 同 fingerprint 是否已有终态人工决定；
4. 同 revision 是否已经 applied/verified；
5. change points 是否具有跨 session 证据；
6. 产物是否通过隐私门控。

命中已有人工终态或验证结果时，机器可标记 `duplicate` 或 `covered`，不能新建“已接受”记录。

## 追加审计

人工决定、应用与验证都写入 append-only 事件流。审计日志只保留必要元数据，不复制正文或敏感 before/after 内容。

约束：

- 接受和部分接受需要通过隐私检查的当前唯一 artifact，在决定时重新核验 hash，并把决定证据固化为 no-clobber archive 快照；
- 部分接受必须列出具体条目；
- 拒绝与部分接受必须记录理由；
- applied 需要 commit hash，验证决定快照，并绑定当前 proposal revision；
- verified 只能发生在 applied 之后，提交时必须同时给出当前 revision 与被验证的 applied commit；
- 同一修订的终态决定和验证结果不可静默覆盖。

## 指标

分别统计：

- machine disposition 分布；
- human decision 分布；
- applied 数量；
- verified/failed/inconclusive 数量；
- 从 proposal 到决定、应用、验证的耗时。

不要用机器推荐数冒充接受率，也不要用文件生成数冒充有效迭代数。
