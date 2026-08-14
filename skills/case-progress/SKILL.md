---
name: case-progress
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.1.0"
license: CC-BY-NC
description: 案件进度与状态台账管理。案件 case.yaml 的唯一写入引擎（新增任务、推进任务、登记期限、更新案件阶段、校验、存量迁移），Agent 会话的进度加载与写回契约，以及案件进度监控对账。当用户或 Agent 需要"更新案件进度/推进任务/登记期限/更新案件阶段/同步案件状态/校验或迁移案件数据/查看案件结构化状态"时使用。不要用于：看板展示与周研判（用 case-dashboard）、案件建档初始化（用 new-case）。
---

# case-progress - 案件进度与状态管理（办案进度台账）

> **状态：v0.1.0 骨架**。设计真值见消费项目 SuitAgent `docs/case-dashboard与数据真值方案.md`（v1.5，决策 #045/#046）。

## 职责

| 功能 | 形式 |
| --- | --- |
| 状态写入 | `scripts/case_store.py` CLI：show / list / add-task / set-status / add-deadline / set-stage / audit / report / validate / migrate |
| 会话契约 | `references/contract.md`：Agent 会话开始 `show` 加载状态 + 按 context 指针读叙事文档；结束经 CLI 写回，**禁止手改 yaml** |
| 项目管理 | `/progress` 命令：自然语言驱动任务/期限/阶段操作，路由到本 CLI 或派发 case-sync subagent |
| 数据契约 | `references/schema.md`：case.yaml v4.0 字段字典——**唯一权威版本**，其他 skill 只引用不复制 |
| 监控对账 | M6（远期）：audit 子命令 + hooks 挂点（PostToolUse 记账 / Stop·SubagentStop 结账 / SessionStart 预警） |

## 开发红线

1. **路径解算禁止 `__file__.resolve()`**（符号链接安装会穿透回本仓库）：项目根用 cwd 向上发现（找到含 6 位数字开头案件目录的祖先）或 `--root` / `SUITAGENT_ROOT` 指定。
2. **单一写入实现**：一切对 case.yaml 的写入必须经本引擎——schema 校验 → 行级 source 保护（永不覆写 `source: user` 行；"已结案"仅手工标记，永不自动推断）→ flock → 临时文件 + `os.replace` 原子替换。
3. **schema 唯一权威**：字段字典只在本 skill 维护；case-dashboard 等消费方引用版本号，不复制内容。
4. **运行时数据绝不入 skill 目录**（本仓库公开）：case.yaml、`.audit.jsonl` 等全部落消费项目案件目录。
5. **被调方式**：其他 skill（如 case-dashboard 的 server）经 **subprocess 调用本 CLI**，禁止跨 skill Python import。

## 目录结构

```
scripts/      case_store.py（CLI + 库 + audit）—— M2 实现
references/   schema.md（v4.0 字段字典）、contract.md（会话契约）—— M3a 起充实
```

## 与周边的关系（案件生命周期接力）

- **new-case**：创建案件目录与初始 case.yaml（v4.0 模板），本 skill 的数据生产上游
- **case-dashboard**：视图层，经本 CLI 读写，只消费不另写
- **case-sync subagent**（消费项目 `.claude/agents/`）：本 skill 的 LLM 执行面，处理需语义判断的写回
- **DataRules.md**（消费项目 `.claude/rules/`）：会话契约的规则层，指向本 skill

## 路线图

M2 写入引擎 → M3a v4.0 数据模型 → M3b 轻量写回入口 → M4 存量迁移 → M6 hooks 监控（远期）。详见 TASKS.md 与消费项目方案。
