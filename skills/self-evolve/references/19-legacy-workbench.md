# 历史工作台（显式兼容入口）

本页保留 v1.7.5 的详细合同供旧部署排障。公开版默认入口以 SKILL.md 和 18-public-workflow.md 为准。不要因运行本页提到的“首次引导”而配置 Key；first_run.py 已切到无独立 Key 的公开流程。旧 dream_sweep 会备份原文，deep/workmode 会调用独立模型通道；只有用户明确需要旧流程时才调用，不能作为公开版默认定时入口。


## 定位

把 Self Evolve 作为“可审的人在回路自进化工作台”使用。只自动完成采集、索引、聚类、脱敏、提案登记和状态展示；不要直接修改目标 Skill、长期上下文或其他成熟资产。

Review Inbox 是 Hermes 桌面插件化候选：可把提案、证据和当前 revision 带入 Agent 对话，支持人在回路审阅。尚未迁移；实现前按私有 `hermes-plugin-dev` 盘点面板认证、nonce、revision 与外置账本契约。插件只能调用本 Skill 既有决定入口，不能绕过隐私门控、自动接受提案或把“接受”误写为“已应用”。

历史部署采用以下运行链路：

```text
外部 Cron
  → scripts/scheduler_run.py（任务白名单、kill switch、锁、限额、日志）
  → daily deterministic index（Claude/Codex 采集、长会话抽样、摘要、聚类）
  → privacy gate
  → machine proposal（机器处置）
  → localhost Review Inbox（人工决定）
  → applied / verified（人工执行后登记结果）

可选 weekly deep
  → 只消费已索引且通过门控的少量 cluster
  → 显式授权后调用 LLM
  → 仍须经过隐私门控和人工决定
```

不要把源码树当作个人状态目录。`config/`、`scripts/`、`templates/` 和 `references/` 是可版本化资产；运行缓存、待审产物、提案、面板和审计数据统一写入外部数据根。

## 依赖

### 系统依赖

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| Python 3.11+ | 运行所有确定性脚本 | macOS 通常已提供 `python3`；也可运行 `brew install python` |
| Claude CLI（可选） | 每周深度分析与画像蒸馏 | 只在明确启用可选 LLM 阶段时配置 |

### Python 包

| 包名 | 用途 | 安装命令 |
|------|------|----------|
| `PyYAML` | 读取任务登记与核心 Skill 配置 | `python3 -m pip install pyyaml` |

首次使用调度器前，就近安装 PyYAML 并校验配置：

```bash
python3 -m pip install pyyaml
python3 scripts/scheduler_run.py --validate-config --json
```

隐私门控、提案存储、面板与测试只使用 Python 标准库；调度器及读取 YAML 配置的采集/库存流程需要 PyYAML。可选 LLM 不可用时必须明确降级并返回失败状态，不得生成伪深度结论。

## 外部数据根

默认数据根由 `scripts/self_evolve_paths.py` 计算,优先级:环境变量 `SELF_EVOLVE_DATA_ROOT` > `config/data_root.yaml` 的 `data_root` 字段 > 平台默认(macOS: `~/Library/Application Support/maoscripts/state/self-evolve`;Linux: `~/.local/state/self-evolve`)。三种改法任选其一,都不改则用平台默认:

```bash
# 改法一:环境变量(优先级最高)
export SELF_EVOLVE_DATA_ROOT="<external-data-root>"
# 改法二:在 config/data_root.yaml 填 data_root 字段(可视化、可入库)
#   data_root: "/your/path"
# 改法三:不填,用平台默认
```

新装用户首次配置见 `references/00-first-run-setup.md`。

数据布局如下：

```text
<data-root>/
├── .self-evolve-root.json
├── layout.json
├── runtime/
│   ├── session-summaries/<YYMM>/
│   ├── raw-sessions/<source_variant>/<YYMM>/
│   ├── dreaming/
│   ├── scheduler/
│   ├── skill-inventory.json
│   ├── skill-inventory.md
│   ├── skill-portraits.json
│   ├── skill-chain-graph.json
│   └── enhance-requests.jsonl
├── review/
│   ├── inbox/
│   ├── quarantine/
│   └── archive/
├── proposals/
├── panel/
├── audit/
└── migrations/
```

兼容变量 `SELF_EVOLVE_STATE_ROOT` 与 `SKILL_EVOLVE_STATE_ROOT` 继续表示 `runtime/` 叶目录，不把它们解释为新的总根，避免静默形成双层目录。新部署优先使用 `SELF_EVOLVE_DATA_ROOT`。

自定义数据根必须是专用叶目录：首次运行只认领不存在或空目录，并写入绑定规范路径的 `.self-evolve-root.json`；已有 v0.7 `layout.json` 可安全补领。拒绝 `/`、用户主目录、系统临时目录（如 `/tmp`）以及非空但未认领的目录，不修改共享目录权限。

发现旧版源码树内 `runtime/` 或 `review/` 时，先预览迁移：

```bash
python3 scripts/migrate_state.py --dry-run --json
```

确认无冲突后再显式复制：

```bash
python3 scripts/migrate_state.py --apply --json
```

迁移只复制并校验，不删除、覆盖或改写旧文件；存在冲突时保持失败关闭，由用户处理后再运行。旧 `review/output/` 和 `review-log.md` 只进入 `review/archive/legacy-output/` 与 archive 日志，不直接进入 Review Inbox。需要重新采用的历史材料必须再次运行隐私门控并登记 proposal，不能把迁移等同于已通过审阅。

v0.7 从源码树移除旧版已跟踪的 `review/output/` 与 `review-log.md`。合并或切换版本前，应先保留旧 Skill 根；使用两个 worktree 时，可从新版本脚本显式读取旧 worktree：

```bash
python3 scripts/migrate_state.py \
  --legacy-root "<old-worktree>/self-evolve" \
  --dry-run \
  --json
python3 scripts/migrate_state.py \
  --legacy-root "<old-worktree>/self-evolve" \
  --apply \
  --json
```

如果已经切换，先把升级前的 Git ref 建成临时 worktree，再把其中的 `self-evolve` 目录传给 `--legacy-root`；不要从当前已清理的源码树推断“没有旧数据”。

**v1.0.0**：运行数据迁至外部状态根；迁移或清理前应核对已有数据与归档。`legacy_state_files()` 只认"冻结 state"，排除活跃产出子树（dreaming/session-summaries/panel/logs/scheduler/learning-candidates + 顶层活跃日志 + review/output）——即使路径 bug 误写 legacy 也不触发 marker flaky。活跃产出只在 external。

## Cron-only 调度

把外部 Cron 系统视为任务是否启用、何时运行的唯一事实源。`config/scheduled_tasks.yaml` 为不入 Git 的本机配置，缺失表示未配置；需要旧调度时从默认关闭的示例复制并自行启用。它只承担：

- 登记固定脚本类型和参数白名单；
- 提供建议频率，供外部 Cron 配置参考；
- 用 `runner.enabled` 充当不可绕过的 kill switch；
- 用 `runner.external_only: true` 拒绝面板或普通手动入口执行任务；
- 定义重入、超时和每日次数上限。

让外部 Cron 统一调用：

```bash
python3 scripts/scheduler_run.py \
  --task nightly-dream-sweep \
  --run-now \
  --trigger external
```

不要把 `recommended_schedule` 当成已部署状态，也不要从面板修改任务计划或启停。外部 Cron 的创建、停用和时间表变更应在对应调度系统中完成。

升级已有外部定时任务时，逐条完成以下替换：

1. 把旧命令统一改为 `scheduler_run.py --task <task-id> --run-now --trigger external`；
2. 删除旧的 `--allow-disabled`，该参数已废弃且不能绕过 kill switch；
3. 为 `refresh-skill-inventory` 与 `nightly-skill-portrait-distill` 建立独立任务，先库存后画像；
4. 确认 `weekly-deep-dream` 在注册表中仍为 `runner.enabled: false`，只有完成预算和隐私评审后才修改代码侧 kill switch；
5. 先用 `scripts/legacy_hook.py status --json` 检查残留，再由用户决定是否执行 `remove --apply`。

缺少 `--trigger external`、任务被 kill switch 关闭、迁移未完成或超过每日限额时，调度器必须非零退出并给出 `next_action`；不要让外部 Cron 把这种失败当成成功。

建议分层：

| 层级 | 建议频率 | 任务 | 边界 |
|------|----------|------|------|
| 近期索引 | 每日 | `nightly-dream-sweep` | 纯确定性，不调用 LLM |
| 历史回填 | 阶段性每日 | `history-backfill-index` | 分批处理；完成后由外部 Cron 停止或降频 |
| 库存刷新 | 每日 | `refresh-skill-inventory` | canonical realpath 去重 |
| 画像蒸馏 | 每周 | `nightly-skill-portrait-distill` | 可选 LLM，失败不破坏索引 |
| 深度分析 | 每周可选 | `weekly-deep-dream` | 默认 kill switch 关闭；只处理高价值 cluster |
| 维护与面板快照 | 每周或按需 | `maintain-runtime`、`render-panel-snapshot` | 不删除原数据，不修改 Cron |

历史回填完成以外部状态中的 `runtime/dreaming/backfill-state.json` 为依据。完成状态应成为终态跳过，避免反复空跑和重复日志。回填用 `last_processed_mtime` 作 cursor lower-bound（newest-first 跳 mtime≥cursor、oldest-first 跳 mtime≤cursor），cursor 单调推进不重复吃头部。解析失败的 transcript 标 `failed_paths` 持久化并在下次 candidates 跳过（熔断，防死循环）；成功后自动从 `failed_paths` 移除（retry 闭环）。`completed` 不要求 `skipped_errors==0`——失败会话不阻塞完成；要重试 failed 用 `--reset-backfill`。

## 会话采集与确定性索引

让 `scripts/dream_sweep.py` 同时发现：

- Claude Code 主会话与归档会话；
- Codex active sessions 与 archived sessions；
- 可选子 Agent 会话，并与主会话去重。

读取长 JSONL 时采用流式、预算受控的头部/中部/尾部抽样，保留最近结论和错误修复，不把“前若干行”当作完整会话。过滤 system、工具回显、重复 message 和大段机器输出，只保留分析所需的用户意图、关键决策、失败与验证证据。

近期索引：

```bash
python3 scripts/dream_sweep.py \
  --index-mode recent \
  --since 14d \
  --sources claude,codex \
  --dry-run \
  --json
```

历史回填：

```bash
python3 scripts/dream_sweep.py \
  --index-mode backfill \
  --backfill-batch-size 200 \
  --backfill-order newest-first \
  --dry-run \
  --json
```

用 transcript 指纹判断未变化会话，按来源控制配额，并使用带内部一致性约束的稳定聚类。聚类必须能够解释成员间共同信号；不要仅凭宽泛 token 交集制造巨型主题簇。稳定 `cluster_id`/`topic_key` 表示主题谱系，成员变化只更新 `member_digest`/`revision`；旧成员绑定 ID 保存在 `legacy_cluster_ids` 供追溯。加簇循环后做簇间合并（`_merge_similar_clusters`：质心相似度≥0.55 合并，跳过纯泛词簇防桥接雪球、size cap 防超分片）；`choose_cluster_title` 泛词同名要求 ≥2 命中，避免异质簇被改名掩盖。采集层剥离 `<system-reminder>`/`<CRON_TASK>` 等框架注入（`strip_framework_injection` 挂 `extract_message_text` + 双 marker 兜底），不让噪声污染下游 signals/evidence。

写 summary 时同步把会话原文 jsonl cp 到 `runtime/raw-sessions/<source_variant>/<YYMM>/<原文件名>`（`archive_raw_session`：no-clobber + 增量更新 + 原子写 + 四源分目录 claude_project/claude_transcript/claude_subagent/codex），作为 CC 删除原文后的字节级无损双保险——summary 是结构化留存，raw 是无损留存，互为保险；详见 `references/11-dream-sweep.md`。

subagent 默认采集（`--include-subagents=True`，`source_variant=claude_subagent`）：不进聚类/dream（避免与主会话重叠 flood），但仍索引 + raw-backup 原文。raw-backup 循环对 merged（existing + summaries）全跑 + no-clobber 幂等，一次性补全所有有 summary 的 session 原文（v1.1.0 修复 v0.9.1 的 skipped_existing 漏备份 gap）。

`--generate` 只发布确定性的 timeline/cluster packet，不调用 LLM。需要深度分析时，单独使用可选阶段：

```bash
python3 scripts/deep_dream.py --max-clusters 5
python3 scripts/deep_dream.py \
  --max-clusters 5 \
  --execute \
  --max-budget-usd 0.50 \
  --per-call-budget-usd 0.10 \
  --max-calls 5
```

第一条只生成/预览受控 packet，并记录 `prepared` 尝试；第二条是明确的 LLM 授权。`--max-budget-usd` 是整次命令总上限，调用前按 `--per-call-budget-usd` 预留，且受 `--max-calls` 二次限制。显式执行时，如所有分析均不可用则非零退出；预览或暂时的 CLI/隐私失败只更新 `last_attempt`，不得覆盖既有 `last_success`、产物或 proposal 引用。深度输出仍须经过隐私门控，不得直接成为已接受提案。已由当前画像覆盖或无法唯一解析目标的候选只记录门控结果，不登记为可操作提案。

详细设计见 `references/11-dream-sweep.md` 与 `references/12-self-evolve-scheduler.md`。

## 向内容评估导出个人偏好证据

把 Self Evolve 用作跨会话证据生产者，不把它变成第二个内容评分器。只有 `quality_gate=deep_eligible`、至少包含两个不同 session 且每个候选证据可追溯的聚类，才可进入自动桥接。导出过程确定性运行，不调用模型：

```bash
python3 scripts/export_preference_evidence.py --json
python3 scripts/export_preference_evidence.py --verify-only --json
```

默认产物写入外部状态根的 `runtime/preference-bridge/evidence-packet.json`，单次最多导出 20 个合格聚类。产物只保留确定性哈希 cluster ID、evidence ID、稳定短 session 哈希与不超过 1200 字的脱敏摘要；所有字符串字段逐字段脱敏，不能先把整个 JSON 序列化后再对 JSON 语法做文本替换。不得包含完整 transcript、原始 session ID、绝对路径、客户信息或密钥。单会话发现继续使用交互式沉淀，由人工判断，不得为了满足自动门槛复制证据。

随后由 `info-evaluator/scripts/preference_ledger.py analyze --packet <path>` 显式调用受限分析模型。Self Evolve 不写评分配置、不决定最终分，也不把“经常处理某主题”推导为“该主题文章应高分”。跨 Skill 的唯一契约见 `../任务自动化/info-evaluator/references/personal-preference-bridge.md`。

## 工作模式偏好账本(self-evolve 内部)

上面是把 Self Evolve 当**证据生产者**,服务 info-evaluator 的**内容评分偏好**(scope=content_value/selection_capacity)。Self Evolve 自己还维护另一维度:**工作模式偏好**(scope=focus/correction/sediment/recurrence)——专注什么、反复纠正什么、什么该沉淀、哪些 skill 反复调用。两者维度不同、各自单一权威源,不互相替代。

```bash
python3 scripts/workmode_pipeline.py --since 14d            # 提炼 + 分析 + 入账(幂等,source_digest 未变则零模型调用)
python3 scripts/workmode_ledger.py list --decision pending   # 列待审候选
python3 scripts/workmode_ledger.py decide <id> --revision <r> --decision accepted
```

证据来自 session-summaries + dream_sweep 聚类(复用 iteration_report 的归因常量,不重构报告),按 (scope, sub_topic) 聚成跨 ≥2 session 的证据包;调 SiliconFlow DeepSeek-V3.2 结构化归纳,只产候选、不修改任何配置。候选账本四维状态机(机器判断 / 人工决定 / 应用 / 结果)照搬 info-evaluator preference_ledger,存外部数据根 `runtime/workmode-preference/{ledger.json,events.jsonl}`。人工决定是仅追加事件、绑定 revision;**accepted ≠ applied**,应用是离线人工门槛。

审阅入口是本地面板的「偏好审阅」tab(loopback + 一次性 token + Origin/nonce 校验,见 `references/13-panel-design.md`):卡片式展示候选(scope/polarity/置信度/跨会话证据数),接受/观察/拒绝。详细设计见 `references/16-workmode-preference.md`。

Self Evolve 维护工作模式偏好账本是本职(自我迭代);**内容评分偏好账本仍在 info-evaluator**,不在本 Skill 维护。两套账本 schema 同源(四维状态机 + 确定性 candidate_id/revision 哈希),为将来统一投影/工作台整合留接口。

## 沉淀报告(panel 沉淀报告 tab)

把 `review/inbox/` 下的脱敏 md 报告(迭代周报 / deep-analysis 等)在 panel 第 4 个 tab「沉淀报告」统一展示,卡片列表(标题 + kind + 时间 + 摘要)+ `<details>` 展开全文。解决「手动翻 md 审核」。来源:iteration_report.py / deep_dream.py / proposal_store(legacy 散落)。安全:write_review_artifact 脱敏 + 前端 `safe_text` 二次防护。这是**阅读视图,不做决定**——决定类用 Review Inbox(proposals) / 偏好审阅(workmode 偏好)。详细设计见 `references/17-sediment-reports.md`。

## Inventory、Portrait 与 Chain Graph

把 `config/core_skills.yaml` 作为“重点关注与优先级”配置，不把它当作候选全集。候选全集来自自动扫描的 inventory：

```bash
python3 scripts/refresh_skill_inventory.py
```

按 canonical realpath 合并符号链接或重复 source，给每个 Skill 保留稳定 key 与内容指纹。基础刷新只写：

- `runtime/skill-inventory.json`
- `runtime/skill-inventory.md`

画像与链路图单独持久化：

```bash
python3 scripts/distill_skill_portrait.py distill --no-llm
python3 scripts/distill_skill_portrait.py distill --limit 24
```

LLM 模式默认使用 `haiku`，单次上限 `$0.10`、整批最多 24 次、按上限预留的总预算不超过 `$2.40`。可用 `--model`、`--max-budget-usd`、`--max-calls` 和 `--max-total-budget-usd` 收紧；CLI 缺失、超时、输出损坏或预算耗尽时必须保留上次有效画像并非零退出。

- `runtime/skill-portraits.json`
- `runtime/skill-chain-graph.json`
- `runtime/enhance-requests.jsonl`

不要把 portrait 或 graph 写回 inventory；这样日常刷新不会覆盖低频蒸馏结果。机制见 `references/10-skill-inventory.md` 与 `references/14-skill-portrait.md`。

## 交互式对话沉淀模式

除外部 Cron 驱动的跨会话磁盘索引外，self-evolve 提供第二模式：用户在某段对话接近尾声时主动触发（「复盘/沉淀这次对话」），agent 用 **live 对话上下文**复盘可复用的方法论/知识，按**自适应 2 分支**路由——命中已安装 skill（Branch A：`core_skills.yaml` 的 `domain_keywords`/`function` 精确匹配，inventory `description` 兜底）则指名道姓写升级提案；无命中（Branch B）则进顾问模式，用「原子化拆分 + 资产沉淀理念 + 去向选项」给建议，决定权交用户。沉淀目的地**动态推导**（用户真实 inventory + 可选 `config/asset_owners.yaml`），不预设固定分类，故初学者（少 skill）走 Branch B 被教方法论、高阶用户走 Branch A 精准路由。

入口脚本 `scripts/interactive_sediment.py`：

```bash
# 打印动态资产地图（inventory + core_skills + 可选 asset_owners）
python3 scripts/interactive_sediment.py map

# 把 agent 写好的脱敏草稿落盘：隐私门控(fail-closed) → review/inbox → proposal 登记
python3 scripts/interactive_sediment.py commit \
  --draft <草稿> --proposal-type skill_upgrade|article \
  --summary <摘要> [--target-skill <id>] [--change-points <CP1,CP2>]
```

`commit` 仅在目标是 inventory 中唯一 resolved 的 skill 时，登记 machine `candidate` 后立即登记 human `accepted`（人工决定已在对话里发生）；文章/无目标/歧义目标只登记 `candidate`，接受动作留到 localhost 面板。非 skill 资产（法律知识规则、问答等）**只到带载荷提案为止**，由 owning skill（如 legal-knowledge-engine）接手入库，self-evolve 不直接改成熟资产。完整 agent 契约见 `references/15-interactive-sediment.md`。

## 隐私门控与提案生命周期

把 transcript 视为不可信输入。生成任何 Review Inbox 产物前：

1. 对路径、邮箱、电话、证件号、案号、组织名、URL 和超长代码块做脱敏或摘要；
2. 拦截提示注入、密钥材料和脱敏后残留的敏感模式；
3. 只把通过检查的产物写入 `review/inbox/`；
4. 把失败样本的规则名、计数和哈希写入 `review/quarantine/`，不要保存原始敏感文本；
5. 为通过产物保存内容哈希，供提案决定与后续应用校验。

可独立检查待审文件：

```bash
python3 scripts/privacy_gate.py <review-artifact> --json
```

提案的机器记录与人工事件分开保存。机器只能写：

- `filtered`
- `candidate`
- `duplicate`
- `covered`
- `recommended`

人工决定初始始终为 `pending`，只能由 localhost 面板或显式 CLI 追加写入：

- `accepted`
- `partially_accepted`
- `rejected`
- `observe`

接受或部分接受必须绑定当前 revision 的唯一 `review/inbox/` 逻辑路径。Deep proposal 产物使用内容哈希文件名和 no-clobber 发布；服务端在写入决定前通过目录文件描述符读取 Inbox 常规文件，不跟随符号链接，现场重算 SHA-256，并把已核验字节固化到 `review/archive/proposal-artifacts/` 的 revision-bound no-clobber 快照。人工事件同时保存原逻辑路径、快照路径和哈希；文件缺失、被篡改、使用符号链接逃逸或绑定多个产物时一律失败关闭。随后由人工实施目标改动，并依次登记：

```text
machine proposal
  → human decision
  → applied(commit hash)
  → verified(verified / failed / inconclusive)
```

人工决定必须同时绑定 proposal revision、原产物逻辑路径、决定快照与产物哈希；`applied` 验证该不可覆盖快照并绑定同一 revision 和目标 commit，不再依赖可能变化的 Inbox 文件；`verified` 再绑定同一 applied commit。示例：

```bash
python3 scripts/proposal_store.py applied <proposal-id> \
  --commit <commit> --actor <actor> --revision-hash <revision>
python3 scripts/proposal_store.py verify <proposal-id> \
  --outcome verified --actor <actor> --revision-hash <revision> \
  --applied-commit <commit>
```

机器重新分析同一 proposal 时可以更新机器证据，但不得覆盖既有人工事件。稳定 fingerprint 用目标 Skill、提案类型和归一化 change points 计算；同修订重复出现时应标为 duplicate/covered，而不是重复创建待审文件。事件流损坏或出现冲突终态时读取失败关闭，不从部分日志投影“已接受/已验证”。工作流见 `references/06-review-workflow.md` 与 `references/08-evaluation-loop.md`。

## Localhost Review Inbox

启动面板：

```bash
python3 scripts/panel.py --host 127.0.0.1 --port 8765 --open
```

只绑定 loopback 地址。启动时生成带 URL fragment 的一次性认证入口；使用 `--open` 自动打开，或手动打开终端输出的完整 URL，不要直接访问裸 origin。fragment 不进入 HTTP 请求或服务日志；交换成功后立即从地址栏清除并作废。会话只保存在当前 origin（包含端口）的 `sessionStorage`，所有状态 API 都显式携带 Authorization，不使用会跨端口发送的 Cookie；如会话丢失，重启面板获取新 URL。面板可查看状态、提案、隐私结果与运行日志，并在认证会话内继续通过 Origin + nonce 提交人工决定；面板不提供任何任务执行、启停或改期端点，外部 Cron 始终是唯一控制面。

生成静态快照：

```bash
python3 scripts/render_panel.py
```

静态文件写入外部 `panel/`，不得嵌入 transcript 原文、完整私有路径、密钥或未脱敏产物。面板契约见 `references/13-panel-design.md`。

## 旧 SessionEnd 残留

旧流程不属于正式架构。只提供状态检查和显式清理，不提供创建能力：

```bash
python3 scripts/legacy_hook.py status --json
python3 scripts/legacy_hook.py remove --json
python3 scripts/legacy_hook.py remove --apply --json
```

`remove` 默认只预览；只有带 `--apply` 时才在稳定锁和内容版本校验下备份设置并移除 Self Evolve 相关残留，同时保留其他项目的配置。读取后若设置被其他进程改动，清理会拒绝覆盖。不要让分支代码自动改写全局设置。

## 按需资源

只加载当前任务需要的资源：

- 首次拿到本 Skill(新用户 / 分发对象)先读 `references/00-first-run-setup.md` 走一遍初始化配置与扫描确认;诊断旧 Hook 时读取 `references/01-hook-config.md`;维护重点 Skill 配置时读取 `references/02-core-skills-yaml.md`。
- 生成升级或文章候选时分别读取 `references/03-sediment-template.md`、`references/04-article-template.md`，并按需使用 `templates/upgrade-direction.md`、`templates/article.md`。
- 审阅提案时读取 `references/06-review-workflow.md` 与 `references/08-evaluation-loop.md`；排查自动化门控时读取 `references/09-programmatic-gates.md`。
- 维护 inventory、索引、调度、面板或画像契约时，分别读取 `references/10-skill-inventory.md`、`references/11-dream-sweep.md`、`references/12-self-evolve-scheduler.md`、`references/13-panel-design.md`、`references/14-skill-portrait.md`。
- 进行交互式对话沉淀（对话末尾复盘、把发现路由到已有 skill 或建议新资产）时读取 `references/15-interactive-sediment.md`，使用 `scripts/interactive_sediment.py`（map/commit）与可选 `config/asset_owners.yaml`。
- 为内容评估系统准备个人偏好候选时，运行 `scripts/export_preference_evidence.py`；语义、账本和人工决定以 `info-evaluator/references/personal-preference-bridge.md` 为准，不在本 Skill 复制维护。
- 初始化新配置时复制 `config/core_skills.example.yaml`，不要把模板占位符当作真实路径。

## 历史工作台验证

在技能目录执行统一验证：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/export_preference_evidence.py --verify-only --json
python3 scripts/scheduler_run.py --validate-config --json
python3 scripts/legacy_hook.py status --json
python3 scripts/migrate_state.py --dry-run --json
```

软件修改完成前，还要实际启动 localhost 面板，检查一次性认证 URL、匿名 API 拒绝、页面、API、nonce 和人工决定写入，并用 synthetic Claude/Codex fixture 验证 active/archive 发现、长会话尾部保留、跨来源去重、聚类一致性、隐私隔离和 proposal 状态不可被机器覆盖。涉及交互式对话沉淀时，另用 synthetic 草稿验证 `interactive_sediment.py` 的 `map` 三态（inventory 缺失/损坏/正常）、`commit` fail-closed（敏感草稿不写盘）、skill_upgrade 命中 resolved 目标时 `decide(accepted)` 真触发、article/missing/ambiguous 只登记 candidate、同内容 no-clobber。把实操证据写入本技能的工作记录；不要仅凭语法检查或 `--help` 声称完成。

## 边界

- 不自动修改成熟 Skill、`AGENTS.md`、用户上下文或项目上下文。
- 不保存完整 transcript、未脱敏代码块或真实私有路径到可提交目录。
- 不从 YAML 拼接任意 shell 命令；只执行调度器内固定白名单。
- 不把机器推荐写成人工接受，也不把“已生成”写成“已验证有效”。
- 不自动删除旧状态、全局配置或外部 Cron。
- 不把单次会话局部结论包装成稳定方法论；需要跨 session 证据和人工判断。
- 不把会话活动频率当作内容价值偏好；不向偏好桥接包复制 transcript 或未经隐私门控的摘要。
