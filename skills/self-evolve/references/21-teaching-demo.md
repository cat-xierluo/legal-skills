# 讲义：从既有 Agent 会话做增量信息挖掘

面向首次接触 self-evolve 公开流程的同事。所有命令都可在本机直接照抄；演示数据一律来自 `scripts/teaching_demo.py` 生成的合成会话，不含真实业务材料。

## 为什么用历史会话，而不是重新问一遍

- 会话里沉淀的是**已经发生的工作**：当时的取舍、失败路径、验收口径，重新提问拿不到这些。
- 重新提问需要重新组织上下文，成本高；历史扫描是本地只读读取，不调用模型，不需要 API Key。
- 挖掘产出的不是"答案"，而是**可复用的模式、纠错点和 Skill 沉淀建议**——这些只在工作现场出现。

## 在 Qoder 等宿主中调用

使用同一份公开 Skill，先确认当前 Agent 能加载它、运行 Python 3.11+ 并访问会话目录。调用宿主与被扫描来源可以不同；Qoder 自身历史会话未接入，不妨碍它按环境条件尝试分析已支持的 WorkBuddy 来源。Qoder 的完整宿主实跑目前为 `NOT_VERIFIED`，课前应走完加载、扫描、分析、导入、打开报告和第二轮增量检查，再决定是否用于现场。

完成下文合成数据彩排后，学员处理自己的本机会话时可使用：

> 调用 self-evolve，确认当前环境可运行 Python 并访问本机会话目录。对 WorkBuddy 等已支持来源做有界增量扫描，读取本轮 packet，按分析合同区分工作行为观察、用户明确纠偏与 Agent 推断，输出引用证据的画像和 Skill 改进建议，导入并生成七页本地 HTML。说明扫描覆盖、失败和未验证项；后续沿同一数据根继续。

课堂彩排用 `teaching_demo.py` 的合成 home 与 state_root，后续命令继续绑定这两个值。该脚本自带固定合成分析，跑通它只证明演示脚本链路，不证明 Qoder 已真实完成语义分析；要验宿主，须由该宿主另读 packet、生成并导入分析。操作条件见 [调用宿主与会话来源](18-public-workflow.md#调用宿主与会话来源)。

## 三个入口命令

在本 Skill 目录（`self-evolve/`）内运行：

```bash
python3 scripts/public_workflow.py scan
python3 scripts/public_workflow.py import-analysis --packet <packet.json> --analysis <analysis.json>
python3 scripts/public_workflow.py status
```

`scan` 首次运行自动初始化专用数据根并记录 `initialized_at`；`import-analysis` 校验分析 JSON 并生成七页 HTML；`status` 显示账本概况。三者的完整 JSON 字段见下文。

## 增量账本：new / unchanged / failed / pending / budget

每次 `scan` 返回的 JSON 包含 `stats` 与 `cumulative`，字段口径如下：

| 字段 | 含义 | 教学要点 |
|---|---|---|
| `stats.new` | 本轮首次处理的文件或索引行 | 首轮里等于已发现的会话数 |
| `stats.unchanged` | 修订标记（mtime/size 或 ZCode updated_at）未变的已处理项 | 第二轮的核心数字：没有重读正文 |
| `stats.failed` | 读取失败、schema 不识别或载荷不认识的会话 | 失败**不记成功**，下轮自动重试 |
| `stats.pending_budget` | 因单轮预算未处理的新材料 | 留给下轮，不是丢失 |
| `stats.selected` / `stats.filtered` | 初筛通过 / 初筛未发现信号 | filtered 不是"无价值"，是"确定性初筛未命中" |
| `cumulative.stored_files_or_rows` | 账本累计登记数 | 持续增长，历史不删 |
| `cumulative.unique_sessions` / `duplicate_views` | 语义去重后的独立会话数 / 副本次数 | 同一内容复制到两个 Runtime 只算一次 |
| `pending_analysis`（顶层） | 本轮送审后仍未消费的证据数 | 跨轮保留，已分析的消费掉 |

**课堂演示点**：第一轮 `stats.new >= 6`、`selected` 与 `filtered` 合计等于 new；第二轮 `stats.unchanged >= 6`、`new` 通常为 0（只有第一轮被单轮预算截断的项才补齐）。这个对比就是"增量账本避免重复处理"的直接证据。

## 低价值初筛与"当前 Agent 判断"的分工

- **初筛是确定性规则**：关键词、会话分类、信号短语命中。它便宜、可重复，但只是**保守分流**，不是价值判断。
- **当前 Agent 是语义判断**：读取 `scan` 返回的 `agent packet`（每轮最多 80 条脱敏证据），按 `references/18-public-workflow.md` 的合同输出分析 JSON。
- 两者都不能跳过：只有初筛，报告里会出现"等待当前 Agent 分析"而不是结论；只有 Agent，没有账本去重和隐私门控。
- 每条证据可声明处置：`analyzed`（已提炼，不再送审）/ `dismissed`（低价值，跨轮保留）/ `insufficient_material`（材料不足，不再送审）。未声明的证据同样跨轮保留——**空分析绝不静默消费整包**。

## 七页 HTML 分别看什么

`import-analysis` 成功后，run 目录里有七页同前缀 HTML：

| 页面 | 文件名后缀 | 课堂关注点 |
|---|---|---|
| 总览 | `report.html` | 关键指标、`pending_budget` 提示、覆盖缺口提醒 |
| 个人画像 | `report-profile.html` | 观察、用户纠偏与 Agent 推断分层；覆盖口径与证据入口 |
| 深度分析 | `report-analysis.html` | 每条规律的 `evidence_ids` 链接，点击可跳回会话与证据页 |
| Skill 沉淀 | `report-skills.html` | 新建/升级/reference 分类、change_points、安装目录说明 |
| 会话与证据 | `report-sessions.html` | 逐条证据的 Runtime、完整性标记、脱敏摘录、初筛结果 |
| 扫描与覆盖 | `report-coverage.html` | 本轮进度条、逐来源状态（含 unsupported 与 read_failed） |
| 运行说明 | `report-guide.html` | 每周调用建议、数据保留、验证边界 |

移动或分享时**复制完整同前缀文件组**；只复制总览会丢失子页链接。

## 人工决定与"建议 ≠ 采用"

- 分析 JSON 里的 `skill_proposals` 只是建议卡：`action: create` 表示"建议新建，尚无安装包"，`upgrade` 表示"已有 Skill 的改进提案"。报告页会明确写"建议、采用与效果验证分开处理"。
- 安装说明由渲染器生成（Claude/`~/.claude/skills/`、Codex/`~/.codex/skills/`、WorkBuddy/`~/.workbuddy/skills/` 等），不会自动执行安装。
- 接受一条建议 = 人工审阅依据 → 准备真实文件 → 放入目标 Runtime 技能目录 → 重新加载确认 → 另行验证效果。任何一步跳过都不能由报告代签。

## 隐私与来源边界

- **ZCode 是索引摘录不是完整对话**：证据的 `completeness` 字段为 `index_excerpt`，报告里显示"索引摘录 · 非完整对话"。它可能截断、没有角色边界，不能当逐字记录引用。
- **失败必须可见**：读取失败、未知 schema、未知载荷都在 `stats.failed` 与 `failures`（`runtime` + `error` + 截短的 `session_key`）里呈现，不在报告里消失。`report-coverage.html` 的来源状态包含 `unsupported`（目录在但格式未接入）与 `read_failed`。
- **业务文书保守隔离**：标题含"司法鉴定/起诉状/判决书"等的材料被 `quarantined`，只存状态与规则代号，不进证据包。
- **不复制原文、不触网、不读凭证**：账本只存脱敏摘要与哈希；扫描只读；HTML 无远端资源。
- **无 API Key ≠ 离线或免费**：语义分析用的是"当前 Agent"（正在运行本 Skill 的 Codex/Claude/WorkBuddy 会话）自己的模型通道与额度。

## 三条命令的返回字段速查

**scan** 顶层：`status`（`scanned`/`partial`）、`run_id`、`stats`、`pending_analysis`、`packet`（路径）、`report`（路径）、`report_pages`（恒 7）、`next_action`。`packet.json` 内：`schema_version`（`self-evolve-agent-packet-v1`）、`packet_digest`、`coverage`（逐来源 `runtime`/`format`/`status`/`discovered`/`errors`）、`evidence`（≤80 条，含 `evidence_id`/`session_ref`/`runtime`/`title`/`completeness`/`excerpts`/`signals`/`decisions`）、`triage`、`inventory`、`limitations`、`analysis_status`（`awaiting_agent`/`no_pending_evidence`）、`failures`、`cumulative`。

**import-analysis** 顶层：`status: analysis_imported`、`analysis_id`、`report`、`report_pages`、`evidence_consumed`、`evidence_retained`、`remaining_action`（恒为"建议待人审阅；未接受、应用或安装 Skill"）。

**status** 顶层：`status`（`initialized`/`not_initialized`）、`meta`（含 `initialized_at`、`scan_profile`）、`sessions`（按状态计数）、`recent_runs`（最近 10 轮）、`analysis_count`。

## 现场演示

完整演示脚本（含 3 个场景的逐步命令与预期输出）见 [22-teaching-demo-playbook.md](22-teaching-demo-playbook.md)。课前彩排一条命令：

```bash
python3 scripts/teaching_demo.py --keep
```

`--keep` 保留输出供现场打开；不带它的命令只做一次性检查，退出后临时报告会被清理。后续命令须同时使用输出中的合成 home 和 state_root，具体步骤见演示脚本。
