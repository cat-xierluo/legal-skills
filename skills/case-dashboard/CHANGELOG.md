# Changelog

## [0.7.1] - 2026-08-16

- **M7-4 速览轻量化**（用户反馈：PDF 阅读器太重，只需查看）：PDF→首页 JPEG（pdftoppm + pdfinfo 页数头，多页注"首页速览"）；docx→文本摘录（textutil）；图片/文本直出；不再内嵌任何阅读器 iframe；弹窗收窄

## [0.7.0] - 2026-08-16

- **M7 导航架构与预览**（用户反馈驱动）：
  - 侧栏回归本职：四级视图导航轨（焦点/案件/待办/月历），待办项移出侧栏；顶部页签移除
  - 待办升级全宽四列看板（进行中/逾期/7 天内/更远与无日期）+ 已完成折叠网格；导航"待办"带红色角标（逾期+临期数）
  - 月历事件点击弹**预览小窗**：倒计时/案件/地点 + 关联文书内嵌预览（`/api/v1/preview` 新端点直出 PDF/图片，路径越界防护）+ 进入案件/打开原件
  - server：preview 端点；案件模型补 business 字段（诉讼/非诉区分预留）
  - 修复：preview 路由误入 do_POST；旧服务进程残留导致端口占用

## [0.6.0] - 2026-08-16

- **M6 UI/UX 深化（用户反馈：信息组织/收费缺失/文书关联/组件质感）**：
  - 信息组织：左侧三列看板 → **待办流**（进行中→待办按截止排序，截止/优先 chip，已完成折叠）；**费用（支出+索赔）进案件详情概览**
  - **文书关联**：任务 `关联文件`、期限 `来源文件`（schema 可选字段，增补二向后兼容）→ 待办流/详情任务/时间线/开庭表/月历事件 📄 一键打开；`/api/v1/open` 支持文件级（路径越界防护）
  - 组件设计系统：页签分段控件化、按钮统一动效（hover 抬升/按下 0.97）、focus-visible 金环、卡片 hover 统一、空态虚线盒、面板 fadeUp
  - 数据绑定示范：251202 四任务绑定真实文书（260813 起诉状/证据目录/TSA 证据 PDF）

## [0.5.1] - 2026-08-16

- **整体换装米金律所纸质感**（弃深色霓虹）：暖纸底/米白卡片/鎏金强调；语义色降饱和正装化（琥珀/青钢/松绿/砖红/赭橙）；去 glow 辉光、暖调浅影；调色全走 CSS 变量系统

## [0.5.0] - 2026-08-16

- **V2 信息架构**：三页签（今日焦点默认/案件/月历）；焦点页（红期限倒计时+60 天开庭+停滞案件芯片，`/api/v1/focus`）；案件页（阶段 chips+搜索+按最近期限排序+开庭/红期限/停滞徽章+已结案折叠组）；**详情页**（完整页五页签：概览/任务三列可点击/期限大数字卡+开庭表/竖向时间线/当事人与证据）

## [0.4.0] - 2026-08-16

- **月历视图 + 期限三级文案**：server 收集开庭与听证、`/api/v1/calendar`（按日分组）；前端月历（周一开头/今天高亮/开庭蓝标/期限红橙绿/翻月）；期限文案三级化（今天/明天/N天/逾期N天）

## [0.3.0] - 2026-08-15

- **M4 收尾：删除 A–D 遗留适配器**（849 → 553 行）——M4 已完成消费项目全量迁移，仅保留 V（case.yaml v4.0）数据源；toggle 写回唯一路径 = case_store CLI
- 删除：adapt_yaml_v21/v3/custom、adapt_info_md、adapt_none、find_info_md、patch_yaml_task_status、patch_md_checkbox、atomic_write（遗留 patch 专用）
- 验证：8 案件全部识别 v4.0；真实案件写回往返（done→todo）通过

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

## [0.1.0] - 2026-08-14

- 骨架创建：SKILL.md（职责边界、符号链接路径红线、端口与数据分离约束）、目录结构（scripts / assets / references）
- 设计依据：消费项目 SuitAgent《case-dashboard 与数据真值统一方案》v1.3（决策 #045），含 canonical case.yaml v4.0、case_store 单一写入引擎、17 类字段混乱点处置
- 经 skill-manager 符号链接安装到 SuitAgent（与 new-case 同模式）
- 尚未迁入：dashboard_server.py + dashboard.html（M1）；~~case_store.py（M2）~~ → 已随拆分移交 case-progress skill
