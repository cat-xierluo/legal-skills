# 15 · 交互式对话沉淀模式（Interactive On-Demand Sediment）

本文是 self-evolve 第二模式的 agent 契约。第一模式（外部 Cron 驱动的跨会话磁盘索引）见 `references/11-dream-sweep.md` 与 `references/12-self-evolve-scheduler.md`；本模式与之互补、不替代。脚本入口为 `scripts/interactive_sediment.py`，两个子命令：`map`（打印动态资产地图）、`commit`（脱敏落盘 + 登记 proposal）。

## 一、定位与触发

- **何时用：** 用户在某段对话接近尾声、主动要求复盘本次对话并把可复用的方法论/知识沉淀下来时（触发语如「复盘这次对话」「沉淀这次对话」「这次有什么能沉淀成 skill 的」「把刚才那套流程固化下来」）。
- **与维护模式消歧：** 触发语指向「本次对话、现在、可复用的东西」→ 进本模式；指向「跑索引 / 查提案 / 刷新库存 / 维护状态」→ 进现有维护模式（`dream_sweep` / `refresh_skill_inventory` / `proposal_store` / 面板）。拿不准时让用户明确。
- **输入：** agent 的 **live 对话上下文**（你就在对话里），不是磁盘 JSONL。当前会话可能尚未落盘，且本模式的价值正是「此刻、本对话」的即时复盘。
- **产出（已与用户确认）：** 在对话内呈现「资产地图 + 本轮发现 + 路由建议」，用户当场逐条确认；**接受的**才走 `commit` → 现有 privacy-gated Review Inbox + proposal 生命周期。不接受 / 观察的只口头记一笔，不写文件。

## 二、步骤 0：载入资产地图

先打印地图，让你（agent）和用户都看到「沉淀目的地全集」：

```bash
python3 scripts/interactive_sediment.py map
```

地图由三处动态拼出（**不预设固定分类**）：

1. 用户**实际安装**的 skill 全集（`runtime/skill-inventory.json`，由 `refresh_skill_inventory.py` 自动扫描生成）；
2. `config/core_skills.yaml`（高阶用户 curated 的重点关注 skill，含 `function` 与 `domain_keywords`，是 Branch A 精确匹配的主力）；
3. `config/asset_owners.yaml`（**可选，默认空**；高阶用户声明「哪类非 skill 资产归哪个 owning skill」）。

**自举：** 若 `map` 输出 `⚠️ inventory 缺失`（用户从未跑过库存刷新），先确定性、无副作用地补一刀：

```bash
python3 scripts/refresh_skill_inventory.py
python3 scripts/interactive_sediment.py map
```

`refresh_skill_inventory.py` 只读扫描 + 写两个库存文件，不调 LLM、不碰成熟 skill，安全。若输出 `⚠️ inventory 损坏`（文件在但 JSON 坏），同样重跑刷新；若刷新后仍损坏，按 `references/10-skill-inventory.md` 排查，不要把损坏当成缺失反复重跑。

## 二·五、步骤 0.5：验证回看（补 applied→verified 半圈）

载入地图后、扫描本次对话前，先查有没有「已应用但未验证」的历史提案：

```bash
python3 scripts/interactive_sediment.py verify-list
```

若返回非空：每个都是之前 `accepted` + `applied` 到某 skill、但还没 `verified` 的提案。若本次对话涉及那个 skill / 那个改进点，**主动回看**——「提案 X 已应用到 `<skill>`，这次用到 / 观察到效果了吗？」→ 用户判断后，复用 `proposal_store verify` 登记 `verified` / `failed` / `inconclusive`：

```bash
python3 scripts/proposal_store.py verify <proposal_id> \
  --outcome verified|failed|inconclusive \
  --reason "<本次观察到的依据>" \
  --actor interactive-user \
  --revision-hash <proposal 当前 revision_hash> \
  --applied-commit <applied 时登记的 commit>
```

这把 `verified` 从「靠人手动记、容易漏」变成「交互沉淀时主动浮现」。`verified` 数据积累后，它就是反哺的输入——哪些改进真有效、哪些总失败，反过来指导 curate 与路由。返回空就跳过，直接进步骤 1。

## 三、步骤 1：扫描本次对话

从 live 上下文里识别可沉淀信号（复用 `references/05-agent-prompt.md` §三 的分析要点）：

- 重复出现的方法论、命名规范、文件组织规范、工具链调用模式、判断流程、checklist、可复用 prompt；
- **严格区分**「通用方法论 / 可复用流程」与「案件/客户特定数据」（案号、原被告、具体产品、账号、价格……后者绝不沉淀）；
- 区分「这次第一次出现」与「跨多次对话反复出现」——后者优先级更高（但仍需用户判断是否够通用）。

## 四、步骤 2：自适应 2 分支路由（本模式核心）

对每个 finding，按用户**实际有的**东西路由，不硬塞：

### Branch A —— 有明确家（命中已安装 skill）

用 `core_skills.yaml` 的 `domain_keywords` + `function` 做精确匹配；未命中重点 skill 时，用 inventory 的 `description` 兜底匹配（`map` 只列 id 摘要，需要各 skill 的 description 时直接读 `runtime/skill-inventory.json` 或 `runtime/skill-inventory.md`）。

- 唯一命中 → **指名道姓**：「沉淀到 `<skill X>`，建议 change point：……」。
- 多候选命中 → 把候选列出，让用户选一个，不要替用户拍板。
- 路由目标既可以是「升级现有 skill」（写 `templates/upgrade-direction.md` 式提案），也可以是「作为某现有 skill 的 reference 补充」。

### Branch B —— 无明确家（无任何已装 skill 匹配）

进**顾问模式**，不强行塞进某个 skill。五步：

1. **原子化拆分**：把发现拆到最小可复用单元（复用 `templates/upgrade-direction.md` 的「原子化 Change Points」概念），别把一坨东西当一个资产。
2. **价值判定**：是否真的反复出现、跨任务可复用？不够通用就**建议不沉淀**——知识工作者最容易犯的错是把一次性内容也存成资产。
3. **资产形态建议**（软建议，不是固定 enum）：这是流程 / 域知识规则 / 模板 / checklist / 一句话 prompt / 候选新 skill？
4. **去向选项**：基于用户**实际有的**东西给 2–3 个，例如：
   - 「可考虑新建一个小 skill 起步」（若有 `five-question-distill` 可指向它帮你起步）；
   - 「作为某现有 skill 的 reference 补充」（指名那个 skill）；
   - 「先 observe，下次再判」（登记观察，不落盘）；
   - 「暂不沉淀」（一次性内容）。
5. **用户决定**：把去向决定权交还用户。可当场转成提案（若用户定了目标 skill），或记为 observe。

> 这样初学者（skill 少、没基建）会被教方法论、不被预设分类误导；高阶用户（基建全）走 Branch A 精准路由。同一套逻辑通吃。

## 五、步骤 3：交互呈现

在对话里给出（紧凑、可扫读）：

1. **地图摘要**：从 `map` 输出里摘重点 skill（core_skills 那几行）+ 全集总数。
2. **每个 finding**：是什么 → 落 Branch A 还是 B → 目标 skill / 建议去向 → 置信度 → 建议 change point。
3. 请用户逐条决定：`accept` / `partial` / `reject` / `observe`。

呈现时把「机器建议」与「事实证据」分开说清楚；不要把单次会话的局部结论包装成稳定方法论。

## 六、步骤 4：落盘（仅 accept 项）

对用户 accept 的 finding，按资产类型选模板写草稿（草稿是给人读的提案正文，**你负责先脱敏**——不要等隐私门控来拦）：

- skill 路由 / owning-skill 投递 → `templates/upgrade-direction.md` 结构；
- 方法论成文 → `templates/article.md` 结构。

然后调用 `commit`，它会自动跑隐私门控 + 落盘 + 登记：

```bash
# skill 升级（目标 skill 在 inventory 中唯一 resolved → 登记 candidate 后立即 decide accepted）
python3 scripts/interactive_sediment.py commit \
  --draft <草稿路径> \
  --proposal-type skill_upgrade \
  --summary "<一句话摘要>" \
  --target-skill <skill-id> \
  --change-points "<CP-1,CP-2>"

# 文章 / 无明确目标（登记 candidate，接受动作留到面板）
python3 scripts/interactive_sediment.py commit \
  --draft <草稿路径> \
  --proposal-type article \
  --summary "<一句话摘要>"
```

`commit` 行为与返回码（详见 `scripts/interactive_sediment.py` 的 `commit_proposal`）：

- **rc=0**：成功。`status=committed_accepted`（skill_upgrade 且目标在 inventory 唯一 resolved：登记 machine `candidate` 后立即登记 human `accepted`——因为人工决定已在对话里发生）；或 `status=committed_candidate`（article，或目标 missing/ambiguous：只登记 `candidate`，接受动作留待 localhost 面板，因为接受需要 resolved 目标）。
- **rc=2 `privacy_blocked`**：**fail-closed**，草稿被隐私门控拦下，**什么都没写**。按 `reason` 修订草稿脱敏后重试。
- **rc=3 `store_error`**：upsert/decide 拒绝了生命周期转换（如目标版本变了）；产物可能已在盘上，按 `error_type`/`error` 排查。
- **rc=4 `draft_unreadable`**：草稿读不出来，没写任何东西。
- **rc=5 `runtime_not_ready`**：仅 CLI `main` 入口产生——`assert_runtime_ready()` 拒绝（外部数据根未认领，或旧状态迁移未完成）；stderr 给出 JSON，**什么都没写**。`commit_proposal` 本身不产生此码；先按 `references/12-self-evolve-scheduler.md` 与 `scripts/migrate_state.py` 处理运行态再重试。

> `--disposition` 默认 `candidate`，且这是 in-chat accept 的唯一合适值——交互流程中**不要**传 `recommended`/`covered` 等（那些归 cron 深度分析路径）。`skill_upgrade` 必须传 `--target-skill`，否则按 unknown 目标降级为 `committed_candidate`。

`commit` 写入外部 `review/inbox/`（内容哈希文件名、原子 no-clobber、`0600`、目录 fsync），复用 `proposal_store` 既有完整性约束（artifact 重算 SHA-256、revision-bound 快照）。`accepted` 只绑定当前 revision；后续真正改 skill 时再分别登记 `applied(commit)` 与 `verified`（见 `references/08-evaluation-loop.md`）。

## 七、非 skill 资产边界（铁律）

self-evolve **只到「带载荷提案」为止**，不直接入库：

- 法律知识规则、问答知识等非 skill 资产，self-evolve 负责**识别 + 抽取 + 脱敏 + 组装成 ready-to-ingest 载荷 + 写提案**，提案里写清「交付给 `<owning skill>` 入库」；
- 真正入库由 **owning skill** 接手（如 `legal-knowledge-engine` 接规则包、`legal-qa-extractor` 接问答）。self-evolve 不直接写 owning skill 的规则包/知识库——那是「不自动改成熟 skill/资产」铁律的延伸。
- `config/asset_owners.yaml` 仅当用户声明了 owning skill 时，才让 Branch A 对非 skill finding 也能指名道姓；未声明就走 Branch B 顾问模式。

## 八、涌现新资产类型

发现反复出现、但不归任何已知类（既不是某个 skill 升级、也不在 asset_owners 里）的模式时，**不硬塞**：

- 标「疑似新资产类型：<你观察到的形态>，建议你定义它的家」；
- 把「这该是什么资产 / 放到哪里」的定义权交还用户；
- 用户定义清楚后再决定 accept（可能引出一次「新建小 skill」或「登记新 asset_owner」的后续动作）。

这防止知识工作者的非典型资产被强行塞进 skill，也防止 self-evolve 替用户下资产分类的决定。

## 九、边界清单

- 不自动修改任何成熟 skill、`AGENTS.md`、用户上下文或项目上下文（本模式只产提案）。
- 不保存 transcript 原文、未脱敏代码块或真实私有路径到可提交目录；落盘必经 `privacy_gate`（fail-closed）。
- 「机器/agent 推荐」≠ `applied`；`accepted`（in-chat 确认）≠ `verified`。
- 不碰外部 Cron、不改全局设置、不替用户决定资产分类。
- 不把单次会话局部结论包装成稳定方法论；跨 session 反复出现 + 用户判断后才沉淀。

## 十、验证要点

软件修改后，用 synthetic 草稿验证：

- `map` 在 inventory 缺失/损坏/正常三态下输出正确（缺失→提示、损坏→带错误提示、正常→地图）；
- `commit` 对敏感草稿（含电话/证件号等）**fail-closed**（rc=2、不写任何文件），对脱敏草稿写盘 + 登记；
- skill_upgrade 命中 resolved 目标时 `decide(accepted)` 真触发（查 proposal 事件流含 `human_decision/accepted`）；
- article / missing / ambiguous 目标只登记 `candidate`、不 decide；
- 同内容二次 `commit` no-clobber（同路径、不重复事件）。

详见 `tests/test_interactive_sediment.py`。
