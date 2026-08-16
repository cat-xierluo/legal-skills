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
| 状态写入 | `scripts/case_store.py` CLI：show / list / add-task / set-status / add-deadline / set-stage / set-fields / validate / migrate / render（audit / report 留 M6） |
| 视图渲染 | `render <短码>`：生成 `案件视图.md` + `案件视图.html`（00 目录，一页纸派生视图，勿手改）；**每次写入自动刷新已存在的视图文件**——无需 hooks 即保持新鲜 |
| 会话契约 | `references/contract.md`：Agent 会话开始 `show` 加载状态 + 按 context 指针读叙事文档；结束经 CLI 写回，**禁止手改 yaml** |
| 项目管理 | `/progress` 命令：自然语言驱动任务/期限/阶段操作，明确操作直路由本 CLI，语义复杂转入下方"工作流收尾状态同步"流程 |
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

## 工作流收尾状态同步（主 Agent 直执行，skill 间协作，不派 subagent）

消费项目复合工作流（被告应诉、证据质证等七场景）在 Reporter 之后、或用户说"同步案件进度/根据新文书更新案件"时，**主 Agent 按以下流程直接执行**：

1. **加载状态**：`show <案件短码>`
2. **盘点产出**：列出本次工作流涉及的 02–11 目录新文件；读关键文件（判决书/传票/新文书）提取事件要素
3. **映射判断**：产出 → 语义变更（新任务 / 任务完成 / 新期限 / 阶段推进 / 时间线事件）
4. **CLI 写回**：add-task / set-status / add-deadline / set-stage（AI 身份，不带 --actor user）
5. **工时记录（必做）**：`log-work <短码> <时长|?> <本次工作摘要> [--task] [--file 产出文书]`——**AI 协作完成的每项工作（文书起草/研究/分析/整理）都边完成边记录**：内容与关联文书/任务自动携带；时长取自上下文（用户提及）否则传 `?` 待律师补录，**不得臆造**
6. **校验与汇报**：`validate` 通过后输出变更清单与待确认项

**执行纪律**：永不手改 yaml；期限需含起算日与法律依据，不确定列入待确认项不臆造；人工覆盖保护（source=user 行只提示不改写、已结案永不设置、锁定阶段不改写）；输出简短 Markdown 变更清单，不产出文件。

## 与周边的关系（案件生命周期接力）

- **new-case**：创建案件目录与初始 case.yaml（v4.0 模板），本 skill 的数据生产上游
- **case-dashboard**：视图层，经本 CLI 读写，只消费不另写
- **主 Agent（skill 间协作）**：工作流收尾的状态同步由主 Agent 按上述流程直接执行，**不依赖 subagent**（架构决策：skill 协作为主，消费项目后续可能整体淘汰 subagent 派发）
- **DataRules.md**（消费项目 `.claude/rules/`）：会话契约的规则层，指向本 skill

## 路线图

M2 写入引擎 → M3a v4.0 数据模型 → M3b 轻量写回入口 → M4 存量迁移 → M6 hooks 监控（远期）。详见 TASKS.md 与消费项目方案。
