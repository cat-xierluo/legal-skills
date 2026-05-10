# Skill Handoff 指南

本指南是 [SKILL-DEV-GUIDE.md](SKILL-DEV-GUIDE.md) 与 [SKILL-ORCHESTRATION-GUIDE.md](SKILL-ORCHESTRATION-GUIDE.md) 的补充文档。

- **SKILL-DEV-GUIDE.md**：单个 Skill 的开发规范
- **SKILL-ORCHESTRATION-GUIDE.md**：多个 Skill 的协作编排规范
- **SKILL-HANDOFF-GUIDE.md**：多个 Skill 之间的交接契约规范

---

## 1. 核心定义

### 1.1 什么是 Handoff？

在 Skill 编排中，**handoff** 指的是一个 Skill 将处理结果、判断结论和原始输入材料，按约定格式交给下一个 Skill 的过程。

它不是普通的“几条提示词补充”，而更接近：

- Skill 之间的接口契约
- AI 编排链路中的数据包
- 人和机器都能读的任务交接单

### 1.2 为什么 Handoff 很重要？

如果没有 handoff，Skill 之间只能靠模糊自然语言接力，会出现：

- 上下游边界不清，重复思考
- 关键原文材料在传递中丢失
- 下游只能消费结论，无法校验依据
- 很难做调试、回放、评估和自动化编排

有了 handoff，才可能实现：

- **解耦**：上游判断一次，下游多次复用
- **复用**：同一份 brief 交给不同 writer skill
- **可测**：能判断问题出在上游、交接还是下游执行
- **可编排**：后续可接 PM、控制台、自动化路由、回执系统

---

## 2. 推荐形态

### 2.1 不推荐的两种极端

**仅自然语言**：
- 人类好理解，但机器难稳定提取
- 字段容易漂移
- 原始材料容易被省略

**纯 JSON**：
- 机器好处理
- 但不适合承载长文章、热点事件原文、案例原文、聊天记录原文
- 人类排查成本高

### 2.2 推荐方案：Markdown Package

推荐使用 **Markdown 外壳 + YAML 头信息 + 分层正文**。

也就是：

1. 顶部一个机器可读的 YAML 信息块
2. 中间一个“上游判断摘要”区块
3. 底部一个“原始输入材料”区块
4. 必要时再加“交接备注 / 风险提醒”

这种格式同时满足：

- 人可读
- AI 可读
- 程序可提取
- 长文本可承载

---

## 3. 标准结构

### 3.1 推荐骨架

````markdown
## Handoff Package

```yaml
handoff_version: "1.0"
source_skill: lawyer-ip-os
target_skill: legal-video-creator
package_type: writer_brief
content_format: markdown
contains_original_materials: true
material_count: 1
```

### 1. 上游判断摘要
- brief 来源：lawyer-ip-os
- 业务 / 议题：
- 目标人群：
- 平台：
- 路径位置：
- 主任务：
- 建议角度：
- 建议创作自由度：
- 必须强调：
- 必须避免：
- CTA 轻重：

### 2. 原始输入材料
#### 材料 1
```yaml
material_id: material-01
material_type: hot_event | article | case | chat_log | question | note
title:
source:
file_path:
use_mode: primary
```

```text
[原文全文；若全文过长，至少给文件路径 / 来源 + 可定位摘录，并明确标注“全文未展开”]
```

### 3. 交接备注
- 缺失信息：
- 风险提醒：
````

### 3.2 头信息字段

| 字段 | 必填 | 说明 |
| :--- | :--- | :--- |
| `handoff_version` | 是 | 交接协议版本号 |
| `source_skill` | 是 | 上游 Skill 名称 |
| `target_skill` | 是 | 下游 Skill 名称 |
| `package_type` | 是 | 包类型，如 `writer_brief` |
| `content_format` | 是 | 当前建议固定为 `markdown` |
| `contains_original_materials` | 是 | 是否包含原始输入材料 |
| `material_count` | 是 | 原始材料数量 |

### 3.3 正文区块

**上游判断摘要**回答：
- 为什么值得做
- 写给谁
- 走哪个平台
- 这条内容承担什么任务
- 哪些边界不能碰

**原始输入材料**回答：
- 具体依据是什么
- 原文是什么
- 文件在哪
- 哪段是主要材料

**交接备注**回答：
- 哪些信息缺失
- 哪些地方有风险
- 下游执行时需要特别注意什么

---

## 4. 原始材料交付规则

### 4.1 原文必须随包走

在本项目中，以下材料默认都属于应交付的原始输入材料：

- 热门事件文件
- 文章原文
- 案例原文
- 聊天记录原文
- 用户问题原文
- 会议纪要 / 复盘记录 / 灵感草稿

不能只把上游结论传给下游，而不传原始材料。

### 4.2 全文与摘录规则

优先级如下：

1. **最佳**：附原文全文
2. **可接受**：给文件路径 / 来源 + 可定位摘录
3. **不可取**：只写“见上文”或“参考原文”

如果全文未展开，必须显式写：
- `file_path`
- `source`
- `全文未展开`

### 4.3 材料标识

每份材料都应有稳定标识：

- `material_id`
- `material_type`
- `title`
- `source`
- `file_path`
- `use_mode`

其中：

- `use_mode: primary` 表示主材料
- `use_mode: supplementary` 表示辅助材料

---

## 5. 强交接与弱交接

### 5.1 强交接

满足以下条件时，视为**强交接**：

- 有完整头信息
- 有明确的上游判断摘要
- 有至少 1 份原始输入材料
- 下游能直接开始执行

### 5.2 弱交接

满足以下情况时，视为**弱交接**：

- 只有上游结论，没有原始材料
- 没有版本信息
- 目标 skill 不明确
- 材料只有模糊一句“见上文”

弱交接可以继续执行，但下游必须明确提示：

- 判断精度会受影响
- 哪些信息是推定的
- 哪些结论缺少原文支撑

---

## 6. 上下游职责分工

### 6.1 上游负责什么

上游 Skill 负责：

- 做更重的判断
- 给出执行方向
- 明确边界条件
- 打包原始材料
- 输出结构稳定的 handoff package

### 6.2 下游负责什么

下游 Skill 负责：

- 消费 handoff package
- 在不重做上游大判断的前提下完成执行
- 只补最小必要判断
- 在缺包、弱交接时显式提示风险

### 6.3 不要做什么

- 上游不要只给结论不给原文
- 下游不要假装自己看过并不存在的原文
- 不要在不同 Skill 之间随意更改字段名
- 不要把长期稳定字段写成一次性自然语言

---

## 7. 在本项目中的典型用法

### 7.1 当前正式链路

本项目当前已经明确的一条正式链路是：

```text
lawyer-ip-os -> legal-video-creator
```

其中：

- `lawyer-ip-os` 负责定位、路径、主任务、平台角色判断
- `legal-video-creator` 负责消费 package 并产出短视频内容

### 7.2 未来可扩展链路

同一份 handoff package 未来还可以交给：

- 小红书 writer
- 公众号 writer
- 长文 writer
- 其他内容执行 skill

也就是说，handoff 的价值不是只服务某一个下游，而是给整个编排层提供统一接口。

---

## 8. 设计原则

### 8.1 统一字段命名

同一语义尽量固定字段名，不要混用：

- `target_skill`
- `main_task`
- `material_id`
- `material_type`
- `file_path`

### 8.2 先稳定，再扩展

先把最常用字段稳定下来，再考虑增加：

- 评分字段
- 优先级字段
- 回执字段
- 机器生成的 trace 字段

### 8.3 版本化

所有 handoff package 都应带：

- `handoff_version`

后续若字段有重大变化，通过版本号而不是自然语言备注来处理兼容问题。

---

## 9. 后续建议

如果编排复杂度继续上升，建议进一步补两类 package：

### 9.1 内容生成 package

适用于：

```text
writer -> video generator / editor
```

关注字段：

- 分镜时长
- TTS 文本
- 字幕文本
- 视觉锚点
- 转场说明

### 9.2 执行回执 package

适用于：

```text
downstream -> upstream
```

关注字段：

- 哪一步执行成功 / 失败
- 缺哪些字段
- 哪些镜头需要返修
- 哪些判断有歧义

---

## 变更历史

| 版本 | 日期 | 更新内容 |
| :--- | :--- | :--- |
| v1.0.0 | 2026-03-31 | 初始版本，定义 Skill 间 handoff package 的目标、结构、字段、原始材料交付规则与强弱交接标准 |
