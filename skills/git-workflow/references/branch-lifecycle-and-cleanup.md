# 分支生命周期与清理

> 在单 Worker 验收收口、长期功能线关闭，或批量审计 stale 分支时读取。删除动作必须先完成对应证据与授权门禁。

## 1. 先判定生命周期

`integration_target` 是接收子 PR 的默认主干或长期功能基线；`head` 是本次交付的源分支。两者必须分开建模。

| 生命周期 | 典型用途 | 单任务收口 |
|---|---|---|
| `ephemeral-worker` | 一个可独立验收的 Worker 任务 | 交付和身份均已证明后，默认清理 head、临时 Worktree 与本地 ref |
| `long-lived` | 单人跨轮开发/观察的里程碑线，或多人功能集成基线 | 活跃、观察中或明确续线时保留；整体交付后评估结案 |

普通 Worker 默认为 `ephemeral-worker`。只有项目任务合同明确指定集成者、固定 Worktree、里程碑和退出条件时，才把源分支标记为 `long-lived`。分支“已经合并”不是生命周期证据；调用方不得把持久 metadata 中的 `long-lived` 降级。

分支生命周期与阶段分开：等待真实使用验证的短分支仍可为 `ephemeral-worker`；需跨轮开发、观察和返修的里程碑线可为 `long-lived`。一周无提交不证明废弃，观察必须绑定固定候选、实际运行证据和下一复核时间，见 [观察验证](long-lived-integration-branch.md#观察验证固定正在测的版本)。缺元数据的旧分支先标待核，不凭名称、年龄、Skill 还会继续维护而批量升级长期或降级可删。

只读盘点应分别列：活跃短任务、开发/观察中的里程碑线、暂停有保留理由、已交付待清理、归属待核。短子分支交付即独立收尾，不必等父迭代线几周后结束；父线默认本轮达标后评估结案，续线须有具名下一里程碑。已有脚本没有这些阶段字段时人工在原任务源补核，不把本次文档约定说成清理器已经支持自动分类。批量既有分支迁移仍须逐个归属与授权核实。

`milestone/` 与类型前缀仅是 [命名合同](issue-pr-format.md) 的可读提示，清理器不得据此自动授权删除或改写持久生命周期。里程碑整体 PR、短子 PR 与未合并关闭的区别见 [PR 路径](pr-workflow.md#0-按分支角色确定-pr-路径)；旧名、同名新 tip 和未知归属仍须单独核验。

短 Worker 合入长期分支时，只清理 Worker head，绝不清理 integration target。长期分支是否最终删除属于功能线关闭决策，需要独立授权，不能由某个子任务验收推导。

## 2. 单 Worker 验收后的自动清理

PM 不等待批量审计，在交付成功的同一收口流程中处理一次性资源。授权只覆盖绑定到同一 canonical repo、PR、head branch、40 位 immutable tip、worktree、Session 与 delivery commit 的精确对象。

执行顺序：

1. 证明交付：远端合并要求 PR `state == MERGED`、`mergedAt` 非空、`mergeCommit.oid` 精确匹配；本地集成要求 delivery commit 已进入最新远端 integration target。
2. PR `headRefName`/OID 必须仍等于冻结值，`baseRefName` 必须等于声明的 `integration_target`。
3. 查询并核对远端 head tip；查询失败不能当作分支不存在。本地集成后 PR 仍 open 时保留远端 head，避免破坏活 PR。
4. 核对 Worktree 干净、worker lifecycle 已 settlement，再移除精确 Worktree。dirty、active、unknown、release pending 或身份漂移一律保留。
5. 确认没有 Worktree 检出该分支后删除本地 ref。普通 merge 可先用 `git branch -d`；squash/rebase 造成 `-d` 拒绝时，只能在上述证据齐全后执行 expected-tip 绑定的原子删除：

```bash
git update-ref -d refs/heads/<branch> <expected-tip>
```

不得升级为无条件 `git branch -D`。tip 漂移时删除失败，保留现场。

`multi-agent-orchestration` 的 `pm-closeout.sh` / `pm-cleanup-worker.sh` 实现该协议。结果必须归一为：

- `CLEANED`：本次一次性资源均已安全清理。
- `RETAINED_WITH_REASON`：按生命周期或具名理由保留。
- `CLEANUP_PENDING`：交付已确认，但资源清理仍有独立债务。

交付确认后的清理失败不得触发 merge/push 重放。只有 `CLEANED` 或有明确理由的 `RETAINED_WITH_REASON` 才能声称资源闭环。

## 3. 批量审计 stale 分支

批量清理不是单 Worker 自动清理的延伸，必须先展示候选并取得用户确认。不要只用 `git branch --merged main`：

- squash/rebase merge 会让原 tip 不可达 main，形成“已合并但显示未合并”的漏判。
- 刚创建、尚未 commit 的活跃分支仍停在 main，会形成“活跃但显示已合并”的误判。

权威组合是 PR 状态、最后提交时间、Worktree/未提交状态和分支身份；ahead/behind 只作辅助指纹。

### 3.1 快照与候选

```bash
git branch -vv
git branch -r
git worktree list

git for-each-ref --sort=committerdate refs/remotes/origin/ \
  --format='%(committerdate:short) %(refname:short)'

gh pr list --state all --limit 100 \
  --json number,state,headRefName,headRefOid,baseRefName,mergedAt,closedAt,mergeCommit
```

默认最后提交不足 24 小时的分支一律视为活跃并保留；项目可以把阈值调大。对每个候选检查对应 Worktree：

```bash
git -C <worktree> status --short
```

日常巡检可先跑只读盘点脚本生成三档候选表（脚本不 fetch/prune/删除；gh 缺失、失败或查询截断时保守 KEEP，PR 未核完整不输出可删除候选；patch-id 不证明当前 tip 已交付）：

```bash
scripts/branch-audit.sh [base-ref] [remote]   # 默认 origin/main origin
```

对单个分支精查其 PR 命运（squash 判死的核心实操）：

```bash
gh pr list --state merged --head <branch> --json number,headRefOid,baseRefName,mergedAt,mergeCommit
# MERGED只证明该PR当时交付；核声明目标与当前tip，不能凭任意旧记录判当前分支已交付
gh pr list --state open   --head <branch>                          # open = 活 PR，保留
```

冻结声明 integration_target、其当前远端完整OID、候选远端/本地完整tip及Worktree/生命周期。PR base必须等于声明目标；受审head及交付树须覆盖当前待删tip。旧MERGED PR的head与当前tip不同、仅合入另一功能线、当前head含未采用成果或采用映射不完整时保留。列表需完整分页，读取失败/范围不全不能当作无open PR或无远端ref。

### 3.2 判定

| 信号 | 处理 |
|---|---|
| PR 为 `MERGED`，真实目标、当前完整tip及交付/采用证据一致，超过活跃阈值，无 dirty/active Worktree | 可列为删除候选 |
| PR 为 `CLOSED` 且非 `MERGED` | 询问用户；废弃不等于允许删除 |
| 无远端 PR、仅本地存在或有未推送 commit | 询问用户；可能是 WIP |
| metadata 为 `long-lived` 或分支是 integration target | 排除，不进入常规 stale 清理 |
| 远端已无该 ref，只剩 remote-tracking ref | `git fetch --prune` 清理本地引用 |
| 最后提交不足阈值，或 Worktree dirty/状态未知 | 保留 |

候选表至少展示分支、声明目标/完整OID、本地/远端完整tip、PR及采用证据、最后提交时间、Worktree/dirty/占用、生命周期和判定。删除授权绑定该快照，不覆盖确认后前进或复用的新tip。取得确认后逐笔重核目标、open PR、归属和tip，再使用 expected-tip 条件；禁止裸批量按分支名删除。

```bash
# 此处仅为已授权的精确ref删除，不发表新提交或重写历史；变量来自候选快照
# 每条命令单独核exit，失败保留并停止该对象后续删除，不盲目重试
# remote lease把删除绑定到已核tip；不加无条件--force
git push --force-with-lease="refs/heads/$branch:$expected_remote_tip" \
  "$remote" ":refs/heads/$branch"
# 远端结果已核、无Worktree检出且本地tip仍匹配时，精确删除本地ref
git update-ref -d "refs/heads/$branch" "$expected_local_tip"
```

远端已不存在时核查询exit和结果，按实际状态记录，不把未知当缺失。事后核目标ref和交付树保留、被删ref确实不存在；`git fetch --prune`只清本地远端跟踪信息，不代替远端后验。

### 3.3 批量删除的执行细节与已验证的坑

盘点、确认、执行之间可能有并发写入；每个对象按同一合同处理：

- 重新读取全部open PR head，命中候选即保留；目标/base/head或归属漂移使旧快照失效。
- squash的原tip不可达不表示未交付，但任一历史MERGED记录也不表示当前tip已交付。核真实目标、原受审head与最终采用关系；patch-id/祖先/日期均不能单独授权删除。
- 本地同名分支ahead、有未推送内容、dirty/active Worktree或被新任务复用时保留；远端删除不授权本地删除。
- 逐笔expected-tip remote lease及本地update-ref阻止tip在复核后前进；失败保留实际原因，重新盘点取得新tip的授权后再考虑，不补发无条件删除或-D。
- 缺ref、权限或网络异常先只读对账；不批量重试、不sudo绕过、不默认改代理配置。单对象失败不继续删除其关联ref/Worktree。
- 不把guarded ref删除当作history force-push权限；新提交发表仍必须走safe-push/safe-pr，长期线和integration target继续硬保留。

### 3.4 patch-id 判死与 worktree 批量清理（261002 实战）

多 Agent 派发（PM→worker、Orca/Codex 并行会话）会沉淀大量一次性 worktree 与分支，其共同形态是「commit 对 base 不可达、但补丁内容已在 base」——squash 合并或 cherry-pick 后 merge-base 全部落空。判死与清理的手法：

#### patch-id 判死（git cherry）

```bash
git rev-list --count origin/main..<branch>                    # ahead N（squash 后虚高）
git cherry origin/main <branch> | grep -c '^+'                # 补丁不在 base 的条数
# '+' 为 0 仅为补丁等价线索，不证明当前 tip 已交付或允许删除
```

- MERGED 回执、patch-id 和祖先关系均是交付线索，必须绑定当前 tip、真实目标和实际采用关系，沿 §3.1/§3.3 核授权。历史 PR 已合不等于该分支后续新 tip 已交付；多 commit squash 后 patch-id 不匹配也不能证明未交付。
- PR 查询须覆盖有关状态、head OID 和目标，检查分页/截断，不以 `--limit 1` 作完整结论。CLOSED 不等于内容未进目标，可能被另一个 PR/窄采用取代；必须核覆盖与未采用处置，未知即保留。

#### worktree 批量清理五步（先展示后执行）

1. **核悬空登记**：先只读盘点路径、管理目录和归属；挂载暂不可用、locked 或坏登记不能直接当过期。prune 是登记写操作，只有本次授权和归属核定后才执行，失败保留原因。
2. **查进程占用（硬保护）**：`lsof -w -d cwd -F n | sed -n 's/^n//p'` 拿全量 cwd 路径，与 worktree 路径前缀匹配。有占用的（活跃 PM/agent 会话）**绝不删**——lsof 列宽截断用 `-F n` 全路径输出规避，路径匹配用 awk `index($0,p)==1`（防空格/正则元字符）。日常巡检直接跑 `scripts/worktree-audit.sh`（只读，含占用/dirty/patch/PR 四维分类）。
3. **dirty 分类**：`git -C <wt> status --porcelain`——modified/untracked 是**会话工作现场**：已终结会话仍须核完整已交付成果和精确删除授权；dirty/untracked须先保留备份并解决归属，不默认force删；untracked可能是无备份的研究材料（实战：R15 研究脚本只存在于 worktree 未提交区）——删除前确认正式版已入库，必要时拷出归档。
4. **分别定范围**：交付、生命周期与当前 tip 全部核定后分别检查工作树、本地/远端 ref 的授权。open PR 或未交付分支保留；只移除树亦须 owner、全部本地材料与业务生命周期已结算，不能认为分支存在便覆盖 ignored/untracked/Session。
5. **执行**：只对已授权、无占用且已处理dirty的精确Worktree执行普通remove；按§3.1/§3.3绑定expected tip删除允许的ref。不默认force、-D或扩大到integration target，失败记录CLEANUP_PENDING并保留现场。

#### 已验证的坑

- **orca 工作区目录 Permission denied**：worktree remove失败时停止后续关联删除，保留具名现场与错误；不得因目录权限失败继续删ref或用sudo绕过。
- **detached HEAD worktree**：先确认不是其他工具自管目录（eval-harness sources 等）再处置。
- **/tmp 下的 worktree**：系统清理可能已删目录，prune 后再处理。
- **删除与盘点间仓库在变**：并行会话持续新开分支/推 PR，执行前重跑 open PR 名单求交（§3.3 同款防护）。

#### PR 取代关系（窄采用入口模式）

研究/返修型工作常见结构：旧 PR（研究基线，head 停在旧 main）→ 新 PR（「固定已验候选窄采用入口」，基于最新 main 只导入已验部分，body 注明「不自动关闭旧 PR」）。判定：核新PR已合入声明目标、旧PR当前head逐文件覆盖关系及未采用处置，并有独立审计与关闭授权后，**关闭被完整取代旧PR**才是安全动作；「不自动关闭」是流程礼貌而非保留理由。反向坑：旧 PR 被 main 甩出冲突（CONFLICTING）不等于过时——先读 body 看它是否在等用户创意决策（实战：#273 等样张择优）。执行动作见 §3.5。

#### 无 PR、有补丁分支的分组处置

批量审计必然产出一批「有提交、没开 PR」的分支（PM 线的中间产物、当日未交付工作）。处置：**当日的保留**（可能还在写）；隔日的按体量与日期列成清单交给用户三选一——让对应 PM 线验收开 PR / 确认过时后删 / 指定归档。不要替用户处置这类分支（红线 §5）。

### 3.5 PR 验收合并与取代关闭的执行 SOP（261002 实战）

前置红线：**合并/关闭 PR 必须有用户显式指示**。AI 审阅的角色是把 open PR 池分成「建议直接合并 / 合并新关旧（取代）/ 活跃复验中勿动 / 冲突待拍板」四组交用户拍板；本节是拍板后的执行序列，单 PR 日常合并同样适用。

#### 第 1 步：合并前复核（盘点到执行之间状态会漂移）

从出审阅结论到用户拍板之间，PR 可能被作者推新提交、被评论、或因 main 前进而改变可合并性。执行前逐个重查：

```bash
gh pr view <n> --json mergeable,mergeStateStatus   # 期望 MERGEABLE + CLEAN
```

任何一项不符就从本轮名单剔除、单独报告原因。`UNKNOWN` 不能判为通过或冲突。核权限、服务端计算和候选变化，可有界等待重查；持续未知时保留未验，不进入合并。

同时复核合并方式仍然成立：squash 是本仓惯例（历史一致、main 每 PR 一提交）；有约在先的例外（如「不合并，供 PM 对照」的对照型 PR）即使 CLEAN 也不进名单。

#### 第 2 步：定合并顺序——独立 PR 任意，同族窄采用 PR 必须串行

- **独立 PR**（改动互不触碰）：顺序无所谓，可连续合并。
- **同族窄采用 PR**（同一 skill 的多个研究树导入，共享 CHANGELOG.md / TASKS.md 等追加型文档）：**逐个合并，每合一个重查下一个**。前一个进 main 后，GitHub 会把后一个甩成 CONFLICTING（实例：#339 合并后 #346 立即从 CLEAN 变 CONFLICTING，冲突仅在 code-video 的 CHANGELOG/TASKS 两文件）。此时走第 4 步解冲突，不要跳过或强行合并。

#### 第 3 步：绑定 head 的 squash 与独立清理

核当前state/draft、head/base、独立review、实际checks及范围，完成授权与验收后转ready。按[PR 合同](pr-workflow.md)使用 safe-pr.py squash，提供完整已审head OID及明确最终标题/正文文件；当前PR文本与每笔历史也需隐私复核。

事后读取 state=MERGED、mergedAt、mergeCommit 并核实际交付树；不只信命令exit或静默输出。合并默认不附 --delete-branch，后续清理按生命周期、精确tip、归属/占用及删除授权执行；长期线与固定Worktree保留。关闭旧PR、合并新PR的授权不自动包含删除所有相关分支。

#### 第 4 步：连锁冲突处理（同族 PR 的追加型文档冲突）

同族 PR 的冲突几乎都落在 CHANGELOG.md / TASKS.md 这类**追加型文档**——两边各自追加了版本记录/任务卡，语义上互不重复。解法是把 main merge 进 PR 分支（不是 rebase——分支可能有 PM 回写历史，merge 保留双方）：

先按[本地 SOP](local-worktree-sop.md)核原 PR head、归属和真实 base，复用适合的隔离树；需新树时，Skill/套件按[稀疏合同](sparse-worktree.md)在创建前固定目标与依赖，不先全量检出。仅在已核隔离 PR 分支内同步实际远端 base，不切换共享主源。

解冲突三原则：

1. **保留双边有效记录**——逐段辨明来源与当前状态，不整文件选一侧。过时或被取代内容保留追溯，当前事实和版本保持单一权威。
2. **依文件合同排序**：CHANGELOG最新版本/日期在前，任务按其当前权威顺序；版本冲突由集成者分配并同步SKILL/索引，不把不同版本历史机械拼到同一版本。
3. **先看清两侧内容再动手**：逐段确认两侧确实是不同主题的追加（实例：一侧是 R15 线全程记录、一侧是 R16 闭环），若发现真正的语义重叠（同一任务卡两边各写一版），停下来交用户/PM 判断——**文档追加冲突可以放心代解，语义冲突不能**。

```bash
# 解完（文件中无 <<<<<<< 残留）：
git add -- <已核冲突文件>
# 身份已核，最终说明亦须隐私检查；实际 base 未必是 main
git commit -m "merge: 解决 <PR#> 与目标基准的追加冲突" -m "保留双方有效记录；说明实际验证结果。"
bash "$git_workflow_dir/scripts/safe-push.sh" --base "origin/$actual_base" --branch "$pr_branch" \
  --expected-name "$expected_name" --expected-email "$expected_email"
```

push 后有界重查精确head、CI和MERGEABLE/CLEAN，再回第3步；任一依赖命令失败即停止后续Git步骤。临时Worktree保留/清理按归属、dirty/占用与精确授权核对，不因命令结束直接删除。

#### 第 5 步：关闭被取代的旧 PR

默认 `gh pr close` 不删除 head 分支；本合同不附带删除参数，清理按精确授权另行执行。关闭必须留取代评论，四要素齐全：

```bash
gh pr close <old-n> --comment "已被 #<new-n>（<新 PR 标题>，窄采用入口）取代，已合入 <实际目标分支>——<哪些旧head内容已实际采用及其证据>。<旧 head 上未被采用的后续提交的处置，如有>。研究基线可经本 PR 历史追溯。关闭属清理决策（<日期> 用户拍板：合并新 PR、关闭旧 PR）。"
```

四要素：① 取代者 PR 号与标题；② 旧PR当前head中哪些内容已进入实际目标（对应采用范围、文件/工程等价或差异证据）；③ 旧 head 上新 PR 未采用的部分如何处置（实例：#290 head 后来自行更新到新 commit，#339 验收记录明确"不属于本固定候选验收"——评论如实写明不整包采用）；④ 关闭的决策依据与日期（可溯）。

关闭后保留或清理旧分支另行核授权。只合功能线时不能声称已进默认主干；未采用部分明确后续处置。删除按§3.1/§3.3的精确tip与生命周期合同，不使用无条件-D；无授权时记录RETAINED_WITH_REASON。

#### 第 6 步：收尾核对与汇报

```bash
git fetch --prune origin        # 同步引用（自动删的 head 在此清掉 remote-tracking）
git worktree list               # 确认临时 worktree 已清
```

向用户报告三段结果：合并清单（PR 号+新 main 位置）、关闭清单（PR 号+取代关系）、清理清单（删除的本地/远端分支），附最终盘点数（远端分支数 / open PR 数 / 本地分支数），并点名本轮未处理项及原因（如"X PR 等创意拍板且冲突未解"）。

#### 本节已验证的坑

- **合并顺序敏感**：同族 PR 一次性连续合并，必然有一个被甩冲突；先合一个、重查下一个。
- **UNKNOWN 暂态**：主干更新可能触发异步重算；有界等待重查，持续 UNKNOWN 或不可读时保持未验，不能推断已可合并。
- **close与删除独立**：旧分支是否保留按实际采用范围、归属及删除授权决定；CLOSED不等于MERGED，也不自动成为可删候选。
- **gh 输出不可全信**：连续合并时命令静默但成功，`state=MERGED` 复核为准。
- **解冲突方向**：把 main merge 进 PR 分支（PR head 前进、包含 main），不要把 PR 分支 rebase 到 main（PM 回写历史会被重写）。

## 4. 长期功能线关闭

长期线不因某个子 PR 合并而关闭；完整里程碑已交付后必须作结束/续线判断，不默认永久保留。没有具名下一里程碑时进入结案评估。在完成以下检查前仍保留，不因到期或任务勾选自动删除：

- 功能线已明确完成或取消；
- open 子 PR、未推送 commit、dirty Worktree 与其他未决工作均已处置；
- 最终状态已写回项目任务源；
- 用户或项目规则对精确分支与 Worktree 给出删除授权。

关闭时仍执行 PR 状态、最后提交时间、Worktree dirty 与 exact tip 检查。删除的是明确关闭的功能线资源，不借机扩大到其他 stale 分支。

## 5. 红线

- 仅凭 `--merged`、ahead/behind、分支名或“已经合并”删除。
- 把 `CLOSED` 当 `MERGED`，或查询失败当“远端不存在”。
- 删除有进程 cwd 占用（lsof 检出或占用未知）的 worktree。
- 删除 untracked 材料无入库备份、且未向用户确认放弃的 dirty worktree。
- 替用户处置「无 PR、有补丁」的未交付分支（列清单交用户三选一：验收开 PR / 过时删 / 归档）。
- 跳过用户确认执行批量远端删除。
- 删除最后提交不足活跃阈值、dirty、active、unknown 或 `long-lived` 的分支/Worktree。
- 使用 `git worktree remove --force`、无条件 `git branch -D` 或未绑定 expected tip 的 ref 删除绕过证据。
- 清理一次性 Worker 时触碰 integration target，或把清理失败隐藏成完全闭环。
