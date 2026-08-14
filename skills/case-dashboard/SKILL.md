---
name: case-dashboard
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.1.0"
license: CC-BY-NC
description: 律师案件看板。本地零依赖看板服务（案件总览、任务三态看板、期限预警、进度写回）＋周研判分析。当用户说"打开看板/dashboard/案件面板/看下案件进度/给我案件周报研判"时使用。案件状态写入与上下文管理用 case-progress（/progress 命令也归它）。不要用于：案件实体分析、文书起草、法律研究。
---

# case-dashboard - 案件看板与项目管理

> **状态：v0.1.0 骨架（M1 迁移进行中；数据层职责已移交 case-progress skill）**。设计真值见消费项目 SuitAgent `docs/case-dashboard与数据真值方案.md`（v1.4，决策 #045/#046）。

## 职责边界

| 功能 | 形式 |
| --- | --- |
| 看板生命周期 | `/dashboard`：健康检查 7879 → 未运行则启动 → 打开浏览器；端口占用 / PyYAML 缺失 / 扫描为空排障 |
| 进度分析 | `/dashboard --review`：周研判（停滞案件、期限叠加风险、下一步建议），护栏见 `references/manual.md` |

> 项目管理（`/progress`：新增任务、推进状态、登记期限、更新阶段）自 v0.1.1 起归 **case-progress** skill。

## 开发红线（符号链接安装的硬约束）

1. **路径解算禁止依赖 `__file__.resolve()`**：本 skill 以符号链接安装（如 SuitAgent `.claude/skills/case-dashboard` → 本目录），`resolve()` 会穿透链接回到本仓库。项目根一律通过 **cwd 向上发现**（找到含 6 位数字开头案件目录的祖先）或 `--root` 参数 / `SUITAGENT_ROOT` 环境变量指定。
2. **运行时数据绝不入 skill 目录**：本仓库公开，case.yaml、`.audit.jsonl`、看板产物等全部落消费项目案件目录；skill 目录仅代码与文档。
3. **端口参数化**：默认 7879（`DASHBOARD_PORT` 可覆盖），与 content-registry(8765)、idle-task-runner(7878) 互让。
4. **单一写入实现**：一切对 case.yaml 的写入经 **case-progress skill** 的 case_store CLI（本 skill 的 server 经 subprocess 调用，禁跨 skill import）——schema 校验 → 行级 source 保护 → flock → 原子替换。
5. **零构建**：前端为单文件 HTML，不引入 node_modules 构建链。

## 目录结构

```
scripts/     dashboard_server.py（薄 HTTP 路由，subprocess 调 case-progress 的 case_store CLI）—— M1 迁入
assets/      dashboard.html（前端单文件）—— M1 迁入
references/  API.md（/api/v1 契约）、manual.md（--review 说明书）；字段字典 schema.md 见 case-progress skill（唯一权威）
```

## 路线图

M1 搬迁成型 → M5 功能扩展；数据层 M2/M3a/M3b/M4/M6 见 **case-progress** skill。详见 TASKS.md 与消费项目方案文档（v1.4）。
