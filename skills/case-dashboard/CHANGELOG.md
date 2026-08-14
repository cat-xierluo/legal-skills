# Changelog

## [0.1.0] - 2026-08-14

- 骨架创建：SKILL.md（职责边界、符号链接路径红线、端口与数据分离约束）、目录结构（scripts / assets / references）
- 设计依据：消费项目 SuitAgent《case-dashboard 与数据真值统一方案》v1.3（决策 #045），含 canonical case.yaml v4.0、case_store 单一写入引擎、17 类字段混乱点处置
- 经 skill-manager 符号链接安装到 SuitAgent（与 new-case 同模式）
- 尚未迁入：dashboard_server.py + dashboard.html（M1）；~~case_store.py（M2）~~ → 已随拆分移交 case-progress skill

## [0.2.0] - 2026-08-14

- **M1 搬迁成型**：`dashboard_server.py` + `dashboard.html` 从消费项目迁入本 skill（scripts/ + assets/）
- **路径解算改造**：--root > SUITAGENT_ROOT > cwd 向上发现；前端资源取自 SKILL_DIR/assets（字符串级路径不 resolve，符号链接安全）
- **新增 V 数据源**：case.yaml v4.0（canonical）适配——任务/期限（三级告警+抵消过滤）/时间线/审级案号；写回经 subprocess 调 case-progress 的 case_store CLI（--actor user，行级 source 保护）；存量 A–D 适配器保留至 M4
- **API 版本化 /api/v1/***：overview / cases / case/<id> / project / task/toggle / open（前端同步升级）
- 消费项目配套：`/dashboard` 命令（含 --review 模式与排障流程）、README_dashboard 重写、旧根目录 server/html 移除
- 验收：fixture 双源全链路 + V 案件看板点击经引擎落盘留痕 + 真实项目根 8 案件只读冒烟一致

## [0.1.1] - 2026-08-14

- **数据层拆分（消费项目决策 #046）**：case_store.py 写入引擎、schema.md 字段字典、/progress 命令、M2–M4/M6 里程碑全部移交新建的 **case-progress** skill；本 skill 瘦身为视图层（看板生命周期 + --review），server 将以 subprocess 调 case-progress CLI
- SKILL.md 同步更新（description、职责边界、目录结构、红线 4、路线图）；TASKS.md 重写为视图层清单
