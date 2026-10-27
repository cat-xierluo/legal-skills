# 升级提案：<skill-name> v<current-version> → v<target-version>

- Proposal ID：`<proposal-id>`
- Revision：`<revision-hash>`
- 机器处置：`candidate | duplicate | covered | recommended | filtered`
- 人工决定：`pending`
- 隐私状态：`passed`
- 产物内容哈希：`<sha256>`
- 证据 ID：`<evidence-id 列表>`

## 一、摘要

<用一句话说明可复用问题、建议变化和预期收益。>

## 二、当前能力与新颖性

- 当前已覆盖：<目标 Skill 当前行为>
- 未覆盖部分：<为什么不是已有功能的重复描述>
- 版本基线：<读取到的当前版本与时间>
- 继续观察项：<证据不足的部分>

## 三、原子化 Change Points

### CP-1：<标题>

- 建议文件：`<目标 Skill 内相对路径>`
- 建议变化：<可独立接受或拒绝的变化>
- 证据：`<evidence-id>`
- 风险：<低/中/高及理由>
- 验证：<行为断言与实操步骤>

### CP-2：<标题>

- 建议文件：`<相对路径>`
- 建议变化：<内容>
- 证据：`<evidence-id>`
- 风险：<说明>
- 验证：<说明>

## 四、边界

- 本文件不是目标 Skill 的修改。
- 不包含 transcript 原文、完整私有路径、案件身份信息或密钥。
- 机器处置不代表人工接受。
- 应用后登记 commit hash，再单独登记 verified/failed/inconclusive。

## 五、人工审提示

- 检查 privacy status 与 artifact hash。
- 检查目标版本是否仍匹配。
- 按 change point 选择全部接受、部分接受、拒绝或继续观察。
- 通过 localhost Review Inbox 或显式 CLI 写入规范决定，不编辑本模板伪造状态。
