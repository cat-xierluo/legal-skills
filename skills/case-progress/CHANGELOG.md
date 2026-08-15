# Changelog

## [0.6.0] - 2026-08-15

- **新增 `render` 命令（视图渲染）**：case.yaml → `案件视图.md` + `案件视图.html`（一页纸派生视图：概览徽章/当事人/任务三态 checkbox/期限红橙绿/开庭/时间线/证据/费用/审级/关联案件/争议焦点；html 零依赖单文件可打印）
- **写入即刷新**：commit_write 后自动刷新已存在的视图文件（不主动创建）——视图永远与 case.yaml 同步，无需 hooks；`--stdout` 可在会话内直接输出 md
- 消费项目 8 案件已全量生成视图；自动刷新经往返测试（写入→[x]→还原）

## [0.5.1] - 2026-08-15

- 新增 `set-fields` 子命令：通用字段补充（@file 或内联 JSON 深合并；列表整体替换；已结案/锁定阶段保护；写入前校验）——补齐 migrate 无法覆盖的字段级事实
- 消费项目数据统一收尾完成：251202 表格任务全量转换（12 条含状态/负责人/备注）+ 当事人 + TSA 证据索引；250519 补审级记录（杨礼红/立案/判决日期）+ 两次质证一次开庭 + 第三人东台医保中心 + 双原告；251112 补开庭排期（2026-09-23 在线庭审，自传票 PDF 提取）；260127/260221/251229 当事人与案件名称规范化；260221 阶段修正为一审
- 遗留人工项缩减为：250519/251231 已结案律师确认（数据已据判决书/调解书核实）；251112 举证期限已逾期提示（2026-05-13）

## [0.5.0] - 2026-08-15

- **M4 存量迁移完成**：`migrate` 子命令（默认 dry-run / --apply / --enrich JSON 深合并）+ A/B/C/D/none 五种转换器；存量行一律 source=user（AI 不覆写）；生成档案先过 validate 不过即跳过
- 消费项目 8 案件全量迁移：B 直迁（阶段注释归一）、A 双 yaml 合并、C 富内容映射（证据/索赔/家属参与人）、D checkbox 转换（日期规范化 + 表格任务警告）、none 骨架 + 事实 enrich；原 yaml 归档 .legacy.yaml、叙事文档统一固定名 案件信息.md
- 修复：B 类带注释阶段值归一（一审（法院已立案）→一审）、时间线空日期/[待定] 行跳转叙事、D 类表格头误读防护

## [0.4.1] - 2026-08-15

- **决策 #047：skill 间协作为主，去除 subagent 依赖**——状态同步流程内化进 SKILL.md（"工作流收尾状态同步"节，主 Agent 直执行：加载状态 → 盘点产出 → 映射判断 → CLI 写回 → 校验汇报）；消费项目删除 CaseSync subagent，Workflow v2.1 / DataRules / AgentMapping / /progress 引用同步为 skill 协作路径

## [0.4.0] - 2026-08-15

- **M3b 轻量写回入口落地（消费项目规则层）**：
  - `DataRules.md` 会话契约规则（自动加载）：show 加载 / CLI 写回 / 人工覆盖保护 / 工作流收尾 / 文件分工速查
  - `case-sync` subagent（CaseSync.md，SubagentStandards 规范）：工作流收尾语义判断面，经本引擎写回，永不手改 yaml
  - `/progress` 命令：明确操作直路由 CLI、语义复杂派发 case-sync、查看类走 show/dashboard
  - Workflow v2.1 收尾强制原则（七场景 Reporter 后必派 case-sync）；AgentMapping v2.4 属主交接（case.yaml 写入=case_store，Scheduler 只计算）；Scheduler 工作流程同步改造

## [0.3.0] - 2026-08-14

- **M2 写入引擎落地** `scripts/case_store.py`（~470 行，stdlib + PyYAML）：
  - 子命令：show（阶段按 锁定>手填>推断 解析、期限告警三级+抵消过滤）/ list（存量案件标 unmigrated）/ add-task / set-status / add-deadline（类型按名称推断）/ set-stage（--lock/--unlock）/ validate（schema §5 六条规则）
  - `--actor user|ai` 操作者模型：source=user 行与锁定阶段仅接受 user；"已结案"不提供写命令
  - 并发安全：**旁车锁** `<case.yaml>.lock` 锁定读-改-写全周期（首版仅锁写入瞬间，并发测试 1/5 暴露丢失更新，修复后 5/5，见 DEC-008）
  - 每次写入自动追加 更新历史 + 刷新 同步.最后同步时间；写入前 schema 校验拦截
  - 路径解算：--root > SUITAGENT_ROOT > cwd 向上发现（符合红线，不依赖 `__file__`）
  - 测试：虚构 fixture 全链路验证（张三/李四民间借贷案，无真实案件数据）

## [0.2.1] - 2026-08-14

- **schema v4.0 同日增补**（8 案件材料盘点 + CaseBoard 字段对照驱动）：新增 关联案件 / 审级记录 / 开庭与听证 / 其他诉讼参与人 / 扩展信息 五节；meta.业务领域 路由键、刑事程序阶段（侦查/审查起诉）、律师费.计费方式、证据索引.取证方式；§1 总览表加层级列（core / 对抗性 / litigation，16 节）
- 新增 schema §7 类型档案（Profile）与非诉扩展机制：core 层通用 + profiles/<领域>.md 惰性立项 + new-case/case_store/dashboard 三方配套演进；§8 增补记录（含刻意不入库清单）

## [0.2.0] - 2026-08-14

- **M3a-1 契约定稿**：`references/schema.md` v4.0——13 顶层节字段字典 × 消费者、行键/source 规则、v3.0→v4.0 章节处置表、存量 5 格式映射要点、6 条校验规则、最小完整示例；`references/contract.md` v1.0——会话加载/写回流程、变更分流表、人工覆盖保护、工作流收尾（M3b 起）、异常处理
- 命名对齐 new-case DEC-011/012：上下文指针为常量路径（`../案件信息.md`、`工时记录.md`）
- 上游模板同步升级完成（new-case v1.4.0 / DEC-015 / Task-016）

## [0.1.0] - 2026-08-14

- 骨架创建：SKILL.md（职责、五条开发红线、与 new-case/case-dashboard 的生命周期接力）、目录结构（scripts / references）
- 由 case-dashboard skill 拆分而来（决策 #046）：数据层独立，承接 M2 写入引擎、M3a 数据模型、M3b 轻量写回入口、M4 存量迁移、M6 监控 hooks
- 设计依据：消费项目 SuitAgent《case-dashboard 与数据真值统一方案》v1.4
- 经 skill-manager 符号链接安装到 SuitAgent
- 尚未实现：case_store.py（M2）、schema.md / contract.md（M3a）
