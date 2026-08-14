# Changelog

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
