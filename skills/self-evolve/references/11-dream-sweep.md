# Timeline Dream Sweep

Timeline Dream Sweep 分为每日确定性索引与每周可选深度分析。两层必须分开：索引负责可靠事实与聚类，深度分析只消费少量通过门控的 cluster。

## 输入适配器

分别实现并测试以下来源：

| 来源 | 范围 | 要点 |
|------|------|------|
| Claude Code | 主会话与归档 | 识别主会话、可选 subagent，并避免重复计数 |
| Codex active | 当前 sessions | 不等待归档才进入日常索引 |
| Codex archived | archived sessions | 与 active 按 session identity/指纹去重 |

每个 adapter 输出统一的 session descriptor：source、session ID、时间、文件指纹和逻辑项目标识。不要把完整私有路径写进 Review Inbox。

### Claude Code 会话存储与生命周期

CC 会话有**两套存储**，`discover_claude_paths` 的 roots 都覆盖，按目录标 `source_variant`：

| 存储位置 | 文件名格式 | 内容 | source_variant |
|---|---|---|---|
| `~/.claude/projects/<slug>/*.jsonl` | `<uuid>.jsonl`（+ `subagents/` 子树） | 主会话 | `claude_project` |
| `~/.claude/transcripts/*.jsonl` | `ses_<hash>.jsonl` | 另一套会话 | `claude_transcript` |

**CC 可能定期清理 projects 旧会话**，因此需要考虑两条约束：

- 摘要必须**及时生成并长期保留**——它是原文被清后的**唯一内容留存**（`session-summaries/` 即 CC 会话史的历史保育层）。已删会话的摘要不可因 `transcript_path` 失效而清理。
- index 的 `transcript_path` 会因原文被清而变「幽灵」，需用**三态标记**（原文在 / 仅摘要留存 / 真失）而非一律 `os.path.exists` 判幽灵，否则会把历史档案当死链误清。

**Recent 模式 cutoff 可能漏扫旧 mtime 会话**：需要周期性运行 backfill 并对账原始来源与索引；`~/.claude/sessions/`（PID 锁）、`tasks/session-*`（空目录）不是会话存储，扫描时排除。

**采集源清单**——扫描前先核对来源，避免漏扫：

**Codex 来源**：活动会话、归档会话与隔离会话分别发现。

| 存储位置 | 内容 | 当前采集 |
|---|---|---|
| `~/.codex/sessions/<年>/<月>/*.jsonl` | active 会话 | ✅ 已采 |
| `~/.codex/archived_sessions/*.jsonl` | 归档会话 | ✅ 已采 |
| `~/.codex/_quarantine/**/*.jsonl` | 隔离会话 | ✅ 已采 |

**CC 的 `~/.claude/history.jsonl`** 是全局用户输入历史，不包含完整 assistant 回复和工具调用；dream_sweep 当前不采集它。

**非会话目录（扫描排除）**：`~/.claude/` 下 `jobs/`、`backups/`、`file-history/`、`cache/`、`paste-cache/`、`plans/`、`teams/`、`telemetry/`、`session-env/`、`output-styles/`、`debug/`、`daemon/`、`ide/`、`skills/` 均非会话 transcript。项目级 `~/<project>/.claude/` 是项目配置目录，不含会话。

**会话与 Git**：会话存储未必由 Git 跟踪；在依赖 Git 恢复前应先核对实际版本库和忽略规则。

**覆盖率对账方法**：扫描完整性靠 `discover_source_transcripts(sources, None, include_subagents=False)`（cutoff=None 全量）对比 `build_existing_summary_index()`（已摘要的 transcript_path 集合），输出 `unindexed = discovered - indexed`。`unindexed > 0` 即漏采，应触发 backfill——不能依赖一次性 `completed` 标志（见 `scheduler_run.backfill_is_complete` 的 `_count_raw_source_files` 复核）。

### raw-backup 原文双保险（v0.9.1）

CC 的 `cleanupPeriodDays` 可能清理旧会话原文。为防原文再失，dream_sweep 在 `update_runtime_indexes` 写 session summary 的同一事务（lock 内）同步把原文 jsonl 复制到 `runtime/raw-sessions/<source_variant>/<YYMM>/<原文件名>`，与 `session-summaries/` 同根同级，成对存在。

四约束：

- **no-clobber**：目标已存在且与源同 size → 跳过（幂等，原文未变不重写）。
- **增量更新**：原文追加致 size 变 → 覆盖（保留最新字节）。
- **原子写**：`_copy_file_atomic`（tempfile + fsync 文件 + rename + fsync 目录），崩溃不残留半文件。
- **三源分目录**：`source_variant`（claude_project / claude_transcript / claude_subagent / codex_active / codex_archived）各占子目录，原文被删后按 `<原文件名>` 精确找回。

原文已被 CC 删除时 `archive_raw_session` 返回 `source_missing` 且**不删已有 raw 备份**——双保险核心：只要原文还在时跑过一次 dream_sweep，删了也找得回。统计写入 `source_index.raw_backup`（archived / skipped / updated / source_missing / error）。

分工（两道独立保险，存储翻倍可接受——数据最重要）：

- `~/.claude` git（v0.9.0）= 版本控制历史，可回溯每次变更。
- `DATA_ROOT/raw-sessions` = 当前快照，原文最新字节。

已知边界：raw-backup 保护所有有 summary 的 session 原文（含 subagent，v1.1.0 默认采集并补全 merged 集合）；来源已缺失时保留 summary，不声称原文仍可恢复。

### subagent 采集（v1.1.0）

CC subagent 会话存在 `~/.claude/projects/<slug>/subagents/agent-*.jsonl`。v0.9.0 之前默认排除（默认 False），v1.1.0 默认 `--include-subagents=True`，自动采集。

设计要点：

- **`source_variant=claude_subagent`**：`source_variant_for_path` 对 `subagents/` 路径返回此 variant。
- **dedupe 让位**：`priorities` 0（同 session_id 时让位 claude_project/claude_transcript）。subagent 与主会话 session_id 不同，实际 dedupe 罕见，但 priority 防御性低。
- **不进聚类**：`cluster_candidate` 对 `claude_subagent` 硬排除。subagent 是主会话子任务，内容重叠主会话，进聚类只会 flood/重复。仍索引 + raw-backup 原文。
- **merged 补全**：raw-backup 循环用 `merged`（existing + summaries）而非仅 `summaries`，no-clobber 幂等补全历史原文。下次跑一次性 cp skipped_existing session 的原文。

raw-backup 的 archived、source_missing 和 skipped 计数可用于检查来源覆盖。

### legacy 源码树清理与 marker 防御（v1.0.0）

源码树 `runtime/` 与 `review/output/` 是旧版活跃产出目录；迁移时必须核对外部权威数据与归档，不能仅凭目录存在就删除来源。

`legacy_state_files()` 只认"冻结 state"，排除活跃产出子树（dreaming/session-summaries/panel/logs/scheduler/learning-candidates + 顶层活跃日志 + review/output）——`is_legacy_active_artifact` 判定。即使路径 bug 把活跃产出写回 legacy，也不计入 migration marker sha256 校验，不触发 flaky。清空后 `legacy_state_files()=[]` → `migration_required=False` → marker 不再被 `assert_runtime_ready` 查询。

## 长会话读取

不要先读完整文件再截断，也不要只保留最前面的固定行数。对 JSONL 进行流式处理，并在预算内选取：

- 头部：任务目标和初始约束；
- 中部：关键转折、失败与决策；
- 尾部：最终修改、验证结果和未解决问题。

过滤或折叠：

- system/developer 消息；
- 工具 schema 与工具结果回显；
- 重复 message；
- 大段代码、目录树和日志；
- 与用户意图无关的机器上下文。

summary 应记录抽样策略、原始行数、保留行数和 transcript 指纹，让后续运行能判断是否需要重算。

## Recent 与 Backfill

Recent 每日扫描近期增量：

```bash
python3 scripts/dream_sweep.py \
  --index-mode recent \
  --since 14d \
  --sources claude,codex \
  --dry-run \
  --json
```

Backfill 分批补齐存量：

```bash
python3 scripts/dream_sweep.py \
  --index-mode backfill \
  --backfill-batch-size 200 \
  --backfill-order newest-first \
  --dry-run \
  --json
```

指纹未变化的 summary 应跳过。Backfill 完成后写入终态；外部 Cron 应据此停用或降频，调度器对完成状态保持幂等跳过。

## 归一化摘要

每个 session summary 至少包含：

- 稳定 session key 与 source；
- 开始/结束时间与文件指纹；
- 脱敏后的用户目标；
- 关键决定、失败模式、验证证据；
- 涉及的 Skill 候选；
- 主题 token/特征；
- 是否只应保留薄索引；
- 证据 ID，不含完整 transcript 原文。

## 一致性聚类

聚类不应仅依赖任意两个 session 的 token 交集。建议流程：

1. 按规范 token、目标 Skill、任务类型与时间邻近度计算候选相似度；
2. 使用 centroid 或 complete-link 约束，保证新成员与 cluster 整体一致；
3. 设置来源配额和 cluster 最大规模；
4. 对低一致性巨型 cluster 继续拆分；
5. 用核心语义特征计算稳定 `topic_key`，再用稳定谱系锚点区分同主题分片；成员全集只计算独立的 `member_digest` / `revision`，不得进入稳定 `cluster_id`；
6. 旧版包含成员摘要的 cluster ID 在下一次索引时迁入 `legacy_cluster_ids`，保留旧报告到新 ID 的可审计映射；
7. 输出 cohesion、共同特征和离群成员解释。

`related_skills` 等加权字段必须在聚类前完成，不能在成员分配后才填充。

## 确定性产物

`--generate` 仍只生成可审计的 timeline 与 cluster packet，不调用 LLM。产物应先经过隐私门控，并使用逻辑 evidence ID 指回外部 summary。

Daily 阶段允许：

- 更新 session summaries 与索引；
- 更新稳定 topic clusters；
- 生成脱敏 timeline/cluster packet；
- 登记 machine proposal。

Daily 阶段不允许：

- 自动修改目标 Skill；
- 写成人工接受；
- 生成无法回溯证据的深度结论；
- 保存原始敏感内容。

## 可选 Weekly Deep

先预览 packet：

```bash
python3 scripts/deep_dream.py --max-clusters 5
```

确认运行环境与预算后显式执行：

```bash
python3 scripts/deep_dream.py \
  --max-clusters 5 \
  --execute \
  --max-budget-usd 0.50 \
  --per-call-budget-usd 0.10 \
  --max-calls 5
```

Weekly 阶段只选择高价值、内部一致、跨 session 的 cluster，并设置数量、超时与输出上限。`--max-budget-usd` 是整批全局上限，每次调用按 `--per-call-budget-usd` 先预留并受 `--max-calls` 限制。候选目标必须使用 inventory 中稳定的 `skill_key`，并绑定目标版本与内容哈希；当前画像已覆盖或目标无法唯一解析时只记录门控结果，不生成可操作提案。LLM 返回内容必须再次通过隐私门控；显式执行后若全部分析不可用则非零退出，不用模板文本伪装成功。

`runtime/dreaming/deep-status/` 使用两层状态：`last_attempt` 记录本次 preview/失败/成功，`last_success` 保留最后一次可用分析及其产物、proposal 引用。无 `--execute` 的预览状态是 `prepared`；CLI 超时、缺失或隐私拦截不得抹掉既有 `last_success`。顶层兼容视图优先映射最后成功结果，调用方需要诊断本次运行时读取 `last_attempt`。
