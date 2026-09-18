# Skill 间合并/去重判定规则

本模块回答「两个及以上 skill 出现职责重叠时，分、合还是降级」。适用对象：同一体系内（如 `~/.hermes/skills/personal/`）的自沉淀 skill 群。消费方：① skill-lint 的「多 skill 重叠审查」入口；② 每周 cron `skill-merge-review`（消费 `skill-cluster-check.py` 聚类报告后按本规则判定）。

## 设计原则

- **触发场景是第一身份**：一个 skill 唯一正当的存在理由是"有一类用户意图能精确命中它"。判定分合先比对触发场景，其次才是内容。
- **渐进式披露优于平级繁殖**：小体量 SOP 优先降级为成熟大 skill 的 reference（正文一句路由 + reference 文件按需加载），而不是维持平级独立 skill——避免体系里手搓重复配件。
- **机械聚类只找候选，不判定**：`skill-cluster-check.py` 的词重叠/标签重叠只负责把对送到桌前；判定必须走本文件的判据表，由 agent（或人）逐簇执行。
- **一切合并走暂存审批**：判定产物是 `skill_manage` 暂存（create 合并体 + `absorbed_into` 标记被吸收者），由审批台终审，绝不直接写盘删除。

## 四判据

对每个候选簇，逐项计算/评估：

| 判据 | 怎么算 | 看什么 |
|------|--------|--------|
| **T 触发重叠率** | 互相代入对方的 description 描述场景：同一条用户意图会同时命中两者的比例 | 触发场景是否本质相同（如"git 提交"vs"git 分支管理"是不同场景，尽管都含 git） |
| **C 内容重复率** | 章节标题集合的交集 / 小者章节集；命令/路径等硬事实的重复条数 | 重复的是"规则正文"还是仅"领域词汇" |
| **S 体量差** | `max(size) / min(size)`（SKILL.md 字节数） | ≥5x 时"合并"会淹没小 skill 的精确触发，优先考虑降级 |
| **B 边界可声明性** | 能否用一句话说清"X 管场景A，Y 管场景B"且互不漏 | 边界清晰 → 保留独立是有正当性的 |

高频词（Use/when/或/排查/管理/使用/技能等）不算触发重叠证据——它们出现在几乎所有 description 里。`skill-cluster-check.py` 已内置停用词表，人工复核时同样适用。

## 处置判定表

按 T → S → B 顺序查表（C 作佐证）：

| 条件 | 处置 | 动作 |
|------|------|------|
| T 高（>70% 意图同命中）且 S < 5x | **合并** | 新建合并 skill：description 覆盖双方触发词（≤60 字符），正文吸收双方精华章节；旧 skill 用 `absorbed_into` 标记；被吸收者暂存删除 |
| T 高且 S ≥ 5x | **降级为 reference** | 小 skill 全文移入大 skill `references/<topic>-sop.md`；大 skill 正文加一句路由（"XX 具体 SOP 见 references/xx-sop.md"）；小 skill `absorbed_into` 大 skill；若小 skill 触发词未被大 skill description 覆盖，须补进大 skill description |
| T 中（部分意图重叠）且 B 高（边界一句话说得清） | **加边界声明** | 双方各加「职责边界」章节互指（先例：git-batch-commit ↔ git-workflow）；不改结构 |
| T 中且 B 低（边界说不清） | **拆分重构** | 说明两个 skill 的职责划分本身有问题：按触发场景重新划分各自正文，再回到本表判定 |
| T 低（仅词汇重叠，意图不同） | **保留独立** | 无动作；聚类报告里该簇标记为误报 |

任何一档拿不准 → 跳过并在输出中说明疑点，交人工判断。**判定不确定时永远选影响更小的处置**（保留独立 > 加边界声明 > 降级 > 合并）。

## 判定表反例（防误判）

- ❌ "都含 hermes" ≠ T 高：hermes-config（改 config.yaml）与 hermes-specialist-bot（建 bot/profile）触发完全不同 → 保留独立。
- ❌ "都处理 PDF" ≠ T 高：pdf-organizer（整理/拆分/重命名）与 pdf-processor（OCR/压缩/页码）是相邻不相同的意图 → 保留独立或加边界声明。
- ❌ S ≥ 5x 但 T 低 ≠ 降级：remote-air-terminal(2.3K) vs git-workflow(24.8K) 体量差 10x，但触发毫无重叠 → 各自独立。
- ✅ 降级正例：local-worktree-pr-workflow(1.5K，"对 maoscripts 仓库做 worktree→PR" SOP) vs git-workflow(24.8K 规则手册)——"开 worktree 提 PR"意图会同时命中两者（T 高），体量差 16x（S≥5x），且小者本质是大者场景的可执行序列 → 降级为 `git-workflow/references/local-worktree-sop.md`。

## Agent 执行流程（cron / 审查入口共用）

1. 读聚类报告（`~/.hermes/pending/skill-merge-suggestions.json`），逐簇进入步骤 2。
2. 对簇内每个成员读 SKILL.md 全文，计算 T/C/S/B 四判据（报告已预计算 S 与初步 T 信号，需人工/agent 复核触发语义）。
3. 查处置判定表得处置；拿不准 → 跳过并记录疑点。
4. 需要变更的：`skill_manage` stage（合并体 create + `absorbed_into`；降级时对大 skill 的 patch + 小 skill 的 absorbed 标记），一切走暂存。
5. 输出一行摘要：处理几簇 / 暂存几条 / 跳过几个（附理由）。

## 与 cron 的衔接

- 聚类脚本：`~/.hermes/scripts/skill-cluster-check.py`（停用词过滤 + 簇分裂 + 四判据预计算）。
- cron prompt 必须指向本文件路径，判定依据以本文件判定表为准，不得自由心证。
- 审批链路（stage → 审批台终审 → 落盘）不属于本模块管辖，保持原样。

## 设计理念

- **合并的代价是触发精度，分裂的代价是导航成本**：合错一个 skill，用户意图再也精确命中不了它；多留一个 skill，只多付一行目录的代价。所以判定不确定时偏向保留独立。
- **降级为 reference 是"渐进式披露"在 skill 间的应用**：skill 内部早已用 references/ 控制正文体积；skill 之间同理——小 SOP 作为大 skill 的按需加载层，触发由大 skill 的 description 承接，内容不丢、导航不繁殖。
- **机械层与语义层分工**：聚类脚本是确定性的、可回归测试的；判定是语义的、要 agent 按表执行。两者中间的接口是"簇 + 预计算判据"，让语义层不必从零读全部 skill。
