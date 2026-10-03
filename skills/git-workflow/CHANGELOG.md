# 变更日志

## [1.12.0] - 2026-10-03 - 开 worktree 前 3 查脚本化、提 PR 前合并模拟与常见事故恢复入册

### 新增

- **scripts/pre-worktree-check.sh（新脚本，Task-001 落地）**——开 worktree 前 3 查只读判读：fetch 后把 §2 判读表机械化为四态输出——`IN_SYNC`（GO，直接以远端 ref 起点开）/ `AHEAD`（GO_WITH_NOTE，可开 worktree，独有提交按三选一另行处理，禁止 reset 丢弃）/ `BEHIND`（FIX_FIRST，先 `pull --no-rebase` 再开）/ `DIVERGED`（FIX_FIRST，隔离候选内对账，不重置共享主源）；附独有/已合 commit 清单与工作区现场简报（不参与判定）。绝不创建/删除/重置任何东西；fetch 失败降级按本地已有引用判定并显式标注；本地 base 分支缺失时提示直接以远端 ref 为显式起点。退出码 0=可开 / 1=先处理 / 2=用法或环境错误。
- **`--pre-pr <branch>` 模式（Task-002 评估结论的落地）**——「PR mergeable 前置」的原表述不可行：PR 创建后的 mergeable 检查搬不到开 worktree 前（PR 对象尚不存在）；能前置的是**提 PR 前**——用 `git merge-tree --write-tree` 在本地模拟 base+head 合并，不创建 PR、不触碰工作区与 index、不耗 GitHub API，冲突提前到 push 前暴露并直连 §4「base 落后 / 冲突处理决策表」。需 Git 2.38+；旧版本报错并给手动等价路径说明，不自动执行（手动路径触碰工作区，超出本脚本只读范畴）。
- **references/accident-recovery.md（新文档，Task-003 落地）**——六类常见事故恢复路径：误 amend（reflog 找 `commit (amend)` 上一条，`reset --soft` 回退；已 push=历史重写走授权边界）、误 stash（关键事实：`pop` 有冲突**不删条目**、`apply` 永不删、`-u` 的 untracked 在 `stash^3`；误 drop 用 fsck 找悬空提交 + `git stash store` 重登记）、误删本地分支（分支自身 reflog 删后仍可读，`git branch <name> <tip>` 新建引用恢复）、误删远端分支（本地重推 / PR 页 Restore branch / 无副本时如实报告）、误 reset --hard（已提交走 reflog；未提交 Git 层不可恢复，指向 IDE 本地历史与三层备份纪律）、误 commit 到错分支（交叉引用 §10 既定处理）。总纪律：先只读定位后恢复、恢复优先新建引用、事故后先不要 `git gc --prune=now`。
- **scripts/test-pre-worktree-check.sh**——bare + 双 clone 真实 Git 夹具，10 项故障注入测试（四态判定、pre-pr 干净/冲突+冲突文件清单、远端 base 不存在、待检分支不存在、本地 base 缺失），隔离全局配置，全绿。

### 改进

- SKILL.md §2 3 查节接入脚本入口，原有命令与判读表保留为透明判读依据与离线降级手动路径；§4 mergeable 检查节开头补前置边界说明（本地模拟干净不豁免 PR 创建后的 mergeable 后验）；§6 新增「常见事故恢复」小节与触发词；description 追加「amend 错了」「stash 找不到了」「分支误删了」「reset 丢了东西」口语触发场景；参考资源清单补三个入口。

### 技术优化

- 规避 macOS bash 3.2 多字节解析坑：`$VAR` 紧跟全角标点或中文字符时变量名解析出错（`unbound variable`），脚本内 10 处改为 `${VAR}` 花括号形式。

## [1.11.2] - 2026-10-03

### 改进
- 完善现有长期功能线合同：默认主干、具名功能线与worker短分支两层PR按功能边界选择，Monorepo采用最少必要功能线；增加PR池依赖审计、逐文件窄采用、共享文档单写者、原独审与最终head/组合行为关系及核心CI实际执行/SKIP分计。
- 明确无未决子PR的同步边界、双端完整OID冻结和里程碑后主干回合；记录已发布GitHub squash与本机身份不同的严格门拒绝及合法服务端同步的完整范围/message/parents/tree/竞态核验。机械身份回执支持仍属后续任务，不改变脚本或全局放行。

### 修复
- 移除长期线整树覆盖冲突、忽略merge失败继续发表及热路径裸push示例；旧PR取代关闭按实际集成目标和当前head完整采用关系核验，不将仅进功能线写成已进默认主干。
- 合并、关闭与清理分开核精确授权；批量清理绑定真实目标/当前head采用证据及本地、远端expected-tip条件，阻止分支确认后前进或复用被误删；纠正默认--delete-branch、无条件-D/force、冲突后重置同名分支及清理失败继续删关联ref的旧说明，长期线持续保留。
- 补齐现有空白local-worktree-sop，按当前合同给出隔离现场→实际验证→身份/隐私→唯一PR→精确合并→增量安装/收口入口；未知历史Node/Raycast步骤交项目规则，不编造恢复。

### 文档完善
- 修正README源码版本列长期落后（1.8.7），源码统一1.11.2；旧ZIP链接保留，因标签与URL版本不符且未核内容，展示标明待核。
- 同步主入口与gh速查，版本/README一致。详细规则在现有reference内维护，文件数量不增加；项目实录和原失败继续归既有任务/ignored archive。1.11.1身份/隐私脚本字节保持，未降低门禁；多轮Agent稳定性与全Skill安全仍NOT_VERIFIED。

### 验证
- 文档差异、引用、版本及README索引核验通过，references仍为8份，脚本与CI字节未改。隔离Git消费者验证主干回合保留其他模块、squash树等价/历史不同、merge-tree预期树与双边祖先、严格身份反例及safe-push真实本地远端；追加远端、本地tip并发前进拒删及精确tip成功的隔离消费者。
- 已发布helpers定向回归：身份门14/14、身份审计16/16、隐私29/29（本机Python3.13/PyYAML6.0.2）；首次稀疏依赖缺失与默认Python旧PyYAML失败保留。静态扫描原FAIL及全部命中与1.11.1基线相同，不签全Skill安全、多轮稳定或无旧上下文前向验收。

## [1.11.1] - 2026-10-03（重编号：分支原编 1.10.0 与 main 已合并的 worktree 审计版冲突）

### 新增

- 共享 `privacy_check.py`：暂存内容、完整提交说明、逐笔历史 message/patch/变更 blob 共用规则；案号待核对、带来源的精确人工审查、原始字节绑定的二进制审查凭据、本地黑名单不外传，诊断不回显敏感原文。
- `safe-pr.py`：创建 draft PR 和 squash 时检查最终标题/正文与完整范围；squash 使用服务端 head OID 条件；明确披露 PR 创建接口的非原子竞态与后验核对。
- 版本化 `commit-msg` 与 `pre-commit` 复用同一检查器；不自动安装 hook 或修改安全配置。新增隔离集成回归和专用 CI。

### 修复

- `safe-push.sh` 显式刷新 integration base ref，身份与隐私门禁绑定同一 base/head OID，逐笔检查而非只看净 diff；浅历史、缺对象、读失败和范围异常均停止。

### 验证

- 覆盖仅提交说明泄露、中间写入后删除、PR/squash 正文、所有分组预检、`--yes`、部分暂存、精确例外、普通 PR 编号、hook 改写和 HEAD 竞态；真实合并未执行。
## [1.11.0] - 2026-10-03 - 敏感文件历史重写与全量撤回 SOP 入册

### 新增

- **references/history-rewrite-and-removal.md（新文档，261003 legal-skills star 数据撤回实战全量沉淀）**——敏感/私有文件被误提交到远端后的全历史撤回完整 SOP，SKILL.md 同步新增 §12 触发节与路由，description 追加「私有数据被上传了」「从历史里删掉」「把这个提交撤回」等口语触发场景：
  - **§0-1 判定与只读排查**：revert ≠ 撤回（历史仍可访问）；凭证类先撤销平台侧 Key 再重写；泄露范围（`git log --all -- 路径`）、凭证是否曾入库、受影响分支面（`git branch -r --contains`）、fork 副本（gh api contents）、`git log --all` 未覆盖未 fetch 分支需 API 交叉验证；
  - **§2-3 隔离重写与推送**：全新 clone 绝不在主工作区跑、为全部远端分支建本地分支、`filter-repo --invert-paths`（会移除 origin、remotes 转本地分支、空提交被剪）、防复发 `.gitignore` 规则作为重写后 main 顶部提交、先 main 后逐分支 force push、三件套验证（SHA 对齐/API 404/分支抽查）；
  - **§4 残留边界**：GitHub dangling 提交仍可按 SHA 访问、fork 不跟随上游重写、其他本地分支各自 rebase、公开窗口时长——如实告知不催办，处置归用户；
  - **§5 主工作区深度分叉对齐剧本**（全量重写后 patch-id 失效不能常规 rebase）：三层备份（backup 分支 + **整个文件夹 rsync 全量备份**——.gitignore 排除的 untracked 本地特有文件 git 备份盖不住 + 反向 diff patch）；**实测坑：`git rm --cached` 的 staged deletion 会在 reset --hard + stash pop 时把磁盘数据文件删掉，reset 前必须单独 cp 出仓**；甄别 cherry-pick 必要性（提交涉及文件两侧树 diff 为 0 行 = 内容已在远端，零回放直接对齐）；stash 不带 -u；冲突语义表（Updated upstream=新 HEAD / Stashed changes=本地；单侧空批量解、不同条目两侧全保留、配套脚本改动必须同侧）；收尾五项验证；
  - **§6 源头排查**：定时任务 → skill 脚本 git 命令 → 三家会话记录按文件名 grep → 提交元数据指纹（**直推 main 无 PR 号 + 凌晨时段** = 自动任务典型特征），无果存档不猜；
  - **zsh refspec 大坑（实战返工一次）**：`"refs/heads/$b:refs/heads/$b"` 的 `$b:r` 被 zsh 解析为变量修饰符致 refspec 静默损坏，批量推分支一律用 `git push origin "$b"` 简单形式。

## [1.10.1] - 2026-10-02 - PR 验收合并与取代关闭执行 SOP 详细入册

### 文档完善

- **references/branch-lifecycle-and-cleanup.md 新增 §3.5「PR 验收合并与取代关闭的执行 SOP」**（六步详细流程，261002 六 PR 合并+两 PR 取代关闭实战全量沉淀）：
  - 第 1 步合并前复核（盘点→执行漂移；UNKNOWN 为 GitHub 重算暂态，等 10–15 秒重查勿当坏状态；对照型 PR「不合并供 PM 对照」即使 CLEAN 也不进名单）；
  - 第 2 步合并顺序（独立 PR 任意；同族窄采用 PR 必须逐个合并、每合一个重查下一个——前者合并会把后者甩成 CONFLICTING，实例 #339→#346）；
  - 第 3 步 squash 合并（--delete-branch 自动清双端 head；本地删除失败不影响合并；连续合并时 gh 偶发静默，以 state=MERGED 复核为准）；
  - 第 4 步连锁冲突处理（隔离 worktree 把 main **merge** 进 PR 分支而非 rebase（保留 PM 回写历史）；追加型文档冲突三原则——两侧记录全保留/按合并先后重排/语义重叠停下交用户；文档追加冲突可代解、语义冲突不能）；
  - 第 5 步关闭被取代旧 PR（close 不删分支须手动补；关闭评论四要素——取代者号与标题/已进 main 的内容范围/未采用部分的处置/决策依据与日期）；
  - 第 6 步收尾核对（fetch --prune、临时 worktree 清理、三段式汇报：合并清单+关闭清单+清理清单附盘点数与未处理项）。
- §3.4「PR 取代关系」小节补执行动作交叉引用（→ §3.5）。
- SKILL.md「GitHub PR 合并」段补批量验收合并与取代关闭入口指向 §3.5；版本号 1.10.1。

### 背景

- 261002 用户拍板「直接合并的帮我合并；合并新 PR 关闭旧 PR 也帮我操作」后的执行实录：#243/#275/#343/#349/#339/#346 六个 squash 合并、#290/#289 取代关闭、#346 连锁文档冲突隔离解冲突后合并。用户要求把该部分尽量详细地沉淀进 skill。

## [1.10.0] - 2026-10-02 - 过期/失效 worktree 审计与 patch-id 判死：worktree-audit.sh + branch-audit.sh 增强

### 新增

- **scripts/worktree-audit.sh**：worktree 冗余只读盘点——对每个挂载按四维（进程占用 lsof / dirty / 分支补丁 patch-id / PR 状态）输出 GONE、KEEP_ACTIVE、KEEP_DIRTY、KEEP_OPEN_PR、REMOVE_ALL、SKIP 分类。硬保护内置：有进程 cwd 占用绝不列删（lsof 用 `-F n` 全路径输出规避列宽截断，awk `index==1` 前缀匹配防路径空格/正则元字符）；dirty 需人工确认（untracked 可能是无备份的研究材料）；分支为 open PR head 或有补丁未交付时只删 worktree 保分支。gh/lsof 缺失自动降级并显式标注「未核对」，方向保守。脚本绝不执行删除。
- **references/branch-lifecycle-and-cleanup.md §3.4「patch-id 判死与 worktree 批量清理」**：git cherry patch-id 判死法（squash/cherry-pick 后 commit 不可达但补丁在 base；判定优先级 MERGED PR > patch-id > merge-base）；worktree 批量清理五步（prune 悬空 → 查占用 → dirty 分类 → 按分支死活定删除范围 → 逐个删）；已验证坑四条（orca 目录 Permission denied 留空壳勿重试、detached 先确认非工具自管、/tmp worktree、盘点-执行间仓库漂移）；PR 取代关系「窄采用入口」模式（新 PR 声明覆盖旧研究树+独立审计指纹时，合并新关旧是安全动作）；无 PR 有补丁分支的三选一处置（验收开 PR/过时删/归档，交用户不代决）。

### 改进

- **scripts/branch-audit.sh**：本地与远端分支判定链新增 patch-id 判死——原「未合并（N commits）」的 NEEDS_CONFIRM 中，`git cherry` 补丁计数为 0 的升级为 SAFE_DELETE（标注 patch-id 0），ahead 计数同步展示「其中 M 个补丁不在 base」；本地段补 MERGED PR 直接判死（与远端段对齐）。patch-id 边界写明：多 commit squash 成单个时不匹配仍归 NEEDS_CONFIRM（宁漏勿错）。
- SKILL.md §2「分支清理」补 patch-id 判死与优先级、「过期/失效 worktree 清理」入口段（worktree-audit.sh + references §3.4 五步 + 三条硬保护）；frontmatter description 补触发词（「清理 worktree」「过期 worktree」「失效 worktree」），版本号 1.10.0。
- §5 红线新增三条：不删有进程占用/占用未知的 worktree、不删 untracked 无备份未确认的 dirty worktree、不替用户处置无 PR 有补丁分支。

### 背景

- 261002 private-skills 实录（承接 260930 那轮）：多 Agent 派发沉淀 55 个 worktree、109 个本地分支、32 个 open PR。实战判死 22 个 worktree + 37 个本地分支 + 3 个远端分支，核心手法正是 patch-id（约半数死分支 merge-base 完全不可见）+ lsof 占用防护（7 个活跃 orca 会话靠它保住）+ PR 取代关系（#339/#346 窄采用 #290/#289）。用户要求把方法固化为可复用流程。

### 待办事项

- `references/local-worktree-sop.md` 为 0 字节空文件（历史版本亦空，2026-09-20 并入时内容未迁移成功），SKILL.md §「Worktree（工作树）」引用悬空——需按原独立 skill 语义重写或改引用，已登记 TASKS.md。
## [1.9.0] - 2026-09-30 - 提交身份自检与身份污染审计：identity-audit.sh（whoami/history）

### 新增

- **scripts/identity-audit.sh**：Git 提交身份只读审计，两个子命令，任一发现非 0 退出（0=无发现/1=有发现/2=用法错误）。
  - `whoami`（commit 前自检）：当前生效 user.name/email + 来源链（env → worktree → repo-local → global，`--show-origin` 给出具体文件）；四类风险告警——仓库级/工作树级 `user.*` 覆盖、`GIT_AUTHOR_*`/`GIT_COMMITTER_*` env 覆盖、可疑身份模式、`--expected-*` 不符。可疑模式据 260930 全仓实测归纳：邮箱 `*.local`/`*.invalid`/`*.test`/`@example.*`/`noreply@`（`users.noreply.github.com` 不误伤），姓名 hermes/openclaw/codex/claude/checkpointer/minimax/glm/bot/agent/worker/dashboard/assistant（大小写不敏感）；本人身份用 `--allow-email`/`--allow-name`/`--allow-local-override` 精确放行。
  - `history`（历史审计）：全部分支或 `--range A..B` 内 author/committer/Co-authored-by 尾注三张身份分布表，可疑项自动标注并输出 FINDINGS 计数；`--max-commits` 控制上限。
- **scripts/test-identity-audit.sh**：16 项故障注入测试（隔离 `GIT_CONFIG_GLOBAL` 夹具）：覆盖层/env/可疑模式/期望不符/worktree 覆盖/尾注标注/精确放行/范围收窄/`users.noreply.github.com` 误伤回归/用法与目录错误。

### 改进

- SKILL.md §1 新增「提交前身份自检与身份污染排查」：whoami 用法、四类风险、与 push 门禁的分工（whoami 管"提交前我是谁、身份哪来的"，门禁管"push 前 range 内每一笔是谁"）、排查入口表（陌生尾注→history 审计，根源在分支作者；作者非我→来源链定位后 unset 回落全局；全仓体检）。§10 共享检出小节补"分支对了还要核对人"交叉引用。frontmatter description 补「提交身份不对」「多出 coauthor」「陌生作者」触发词，版本号 1.9.0。参考资源清单补两脚本。

### 背景

- 260930 private-skills 实录：仓库级 `.git/config` 被写入 `Hermes(info-assistant) <info-assistant@hermes.local>`（不晚于 09-23 生效，190 个提交作者被污染），GitHub squash 合并自动把分支提交作者转成 Co-authored-by 尾注，全部合并 PR 带上陌生署名。既有 push 门禁只核验传入的期望身份，期望值取自被污染 config 时形同虚设，且尾注不在其检查范围——防线需前移到 commit 前，并补全仓审计入口。

## [1.8.9] - 2026-09-30 - 分支冗余巡检自动化：只读盘点脚本 + 批量删除执行坑入册

### 新增

- **scripts/branch-audit.sh**：分支冗余只读盘点——对远端与本地分支输出三档候选表：SAFE_DELETE（PR 已合并/已包含于 base）、NEEDS_CONFIRM（无 PR 未合并或本地同名分支有未推送提交，删=内容丢失）、KEEP（open PR head、worktree 检出、backup·snapshot 存档命名）。gh 缺失或未认证时自动降级为 merge-base+日期判定并显式标注「PR 状态未核对」（squash 分支漏判为 NEEDS_CONFIRM，宁漏勿错）。脚本绝不执行删除。内置三项防护：跳过 base 分支与裸 remote ref；本地复用保护（远端分支存在本地同名 ahead 分支时不列为候选）；输出尾部附执行须知。
- **references/branch-lifecycle-and-cleanup.md §3.3「批量删除的执行细节与已验证的坑」**：执行前重跑 open PR 防护（并行会话持续开分支）、squash 判死以 PR 状态为准、本地复用保护、批量 push --delete 遇缺 ref 整批失败须 fetch --prune 后补删、代理环境 `-c http.proxy=` 绕过、远端删除不影响本地检出。§3.1 补 `gh pr list --state merged --head` 单分支精查与脚本入口。

### 改进

- SKILL.md §2「分支清理」入口指向 branch-audit.sh 快路径（盘点→展示→确认→执行四步）；frontmatter description 补口语触发词（「分支有点多」「冗余分支」「清理一下分支」）。

### 缘由

- 实战沉淀（private-skills 260930 清理：53 远端+3 本地已合并死分支删除，9 个未合并老分支与 9 个 orca worktree 经确认保留）：技能内已有批量审计框架，但每次仍需用户从零口头发起、执行细节靠临场重踩；固化后「分支有点多」一句话即可触发完整核查清理流程。脚本已在 legal-skills 与 private-skills 双仓实测（三档分类与人工盘点结论一致）。

## [1.8.7] - 2026-09-19 - 外部 PR 分层审查：必要性 gate 先于代码审查

### 新增

- **SKILL.md §4「审查外部 PR：分层审查——必要性 gate 先于代码审查」**：审外部贡献者的 PR 先做项目契合度 gate——核对需求来源（issue / ROADMAP / TASKS / 项目规则）、无来源时对照 README 核心主张判断是贡献者个性化偏好还是真实需求、伪需求识别（issue 遗留场景在当前架构下是否仍存在，例：「打开文档替换当前内容」的确认场景在多标签架构下不适用）。gate 不通过直接礼貌关闭（留言模板：感谢→说明不在路线图且不评价代码质量→给重启路径），不进入代码审查。必要性依据是项目级答案，Skill 只约束流程顺序；答案缺失时问用户或查项目规则，不得用「代码看起来没问题」替代 gate 判断。

### 缘由

- 实战教训（Folia #165）：先做代码深审列出多个缺陷（单标签模式数据丢失链、「保存」按钮不兑现等），最终以「功能不在路线图、无用户诉求、伪需求」关闭——代码审查投入全部沉没。gate 前置切断这类沉没成本。

## [1.8.6] - 2026-09-19 - 外部 PR 本地验证的环境卫生

### 新增

- **SKILL.md §4「审查外部 PR：本地验证的环境卫生（防遗留状态污染结论）」**：审他人 PR 一律隔离 worktree 检出（`git fetch origin pull/<N>/head` + `git worktree add <path> FETCH_HEAD`），永不在主工作区 `gh pr checkout`；动手前主工作区体检（UU / MERGE_HEAD / 未提交变更先恢复干净）；会话内 merge / rebase / checkout 试验的收尾纪律（要么完成要么 `--abort`）；判读参照：typecheck / test 报错文件不在 `gh pr diff --name-only` 列表里 = 工作区污染信号，切干净 worktree 复跑后再写 review 结论。node_modules 可符号链接主仓库复用。

### 缘由

- 实战事故（Folia #165 审查）：主工作区残留审 #166 时中断的 merge（MERGE_HEAD 存在），`gh pr checkout 165` 把遗留变更叠加成混血工作区，typecheck 假阳性（tocAlwaysPinned 报错全属 #166），险些把别的 PR 的缺陷写进当前 PR 的 review 结论。

## [1.8.5] - 2026-09-17

### 修复

- `safe-push.sh` 接受裸分支名作为 `--base`：含 `/` 的值必须以 `$REMOTE/` 开头，其他 remote 前缀仍报 `SAFE_PUSH_BASE_REMOTE_MISMATCH`；不含 `/` 的裸分支名规范化为 `$REMOTE/<branch>`，与 `spawn-worker` 白名单生成的 `--base main` 调用形式一致，后续 `base_branch` 派生与 `git fetch $REMOTE $base_branch` 校验沿用规范化后的值。事故：旧实现只接受 `<remote>/<branch>`，`spawn-worker` 派发 worker 调用 `--base main` 一律 `SAFE_PUSH_BASE_REMOTE_MISMATCH`，worker 只能回落到普通裸 push（绕过身份门禁）。

### 验证

- `test-check-outgoing-identities.sh` 新增两个用例：`--base main` 与 `--base origin/main` 等价放行；`--base upstream/main`（remote≠`$REMOTE`）仍以 `SAFE_PUSH_BASE_REMOTE_MISMATCH` 拒绝。

## [1.8.4] - 2026-09-15 - GitHub Actions 额度治理入册（4 仓 7 workflow 停挂实战）

### 新增

- **SKILL.md §11 + `references/github-actions-quota-guard.md`**：账号级分钟额度诊断（billing API、逐仓 (workflow × event) 触发统计、push+PR 双计费识别）；停挂配方（`on:` 块 workflow_dispatch 化、本地等价命令入注释、被 uses 复用须保留 workflow_call、PR 分支自身不再计费）；仓级总闸 `actions/permissions enabled=false`；恢复手册即文件内注释。
- **事故备忘**：`gh pr merge` 网络中断 + 清理未以 merged 确认为门禁 → head 分支被删 PR 自动关闭；恢复 = 本地重建分支指向原 sha → push → reopen。壳层两坑（JSON 控制字符、管道退出码）一并入册。
- 触发词：GitHub Actions 额度 / CI 分钟耗尽 / workflow 停挂。
## [1.8.3] - 2026-09-07 - 长期分支 PR 实战三坑入册（custom-skills 拆分线实证）

### 改进

- **集成 PR 时机红线**（reference §7 新增"时机红线"）：base=默认主干的总 PR 只在里程碑达成时开；功能线推进期只开子 PR（base=长期分支）。提早开的总 PR 保持 open 仅作提醒，并在项目任务源注明。
- **GitHub 自动关闭 PR 的坑**（reference §7 新增）：head 分支 force-push 重置致与 base 无差异时，PR 被自动 CLOSED（无通知）；重开后 PR 号变化，须更新项目任务源与记忆中的旧号引用。
- **squash 重做断裂与树等价验证**（reference §4 新增）：同一树内容 squash 重做后与原 squash 无共同祖先，GitHub 判 CONFLICTING；给出本地解决流程（merge→以完成态树 checkout→`git diff <完成态> HEAD --stat` 必须为空才 push），树等价验证是 fail-closed 门。
- SKILL.md 长期集成分支小节补一行索引指向 §4/§7。

## [1.8.2] - 2026-09-05

### 改进

- **清理规则单一来源**：新增 `references/branch-lifecycle-and-cleanup.md`，集中承载一次性/长期分支生命周期、单 Worker delivery-bound 清理、squash/rebase expected-tip 删除、批量 stale 审计和长期功能线关闭。
- `SKILL.md` 的分支管理章节改为最短判定入口，删除与 reference 重复的命令、候选表和红线；长期集成分支 reference 继续负责建线/同步/里程碑，职责不混杂。

### 安全

- 保持 `long-lived`、integration target、24 小时活跃阈值、dirty Worktree、用户确认和 expected-tip 原子删除等既有边界；本次为结构优化，不放宽删除授权。

## [1.8.1] - 2026-09-05

### 修复

- 收窄“合并后清理”为仅清理 `ephemeral-worker` 一次性 head；长期功能/集成分支及其固定 Worktree 即使里程碑已合入默认主干，也不因单 Worker 验收自动删除。
- 分离 PR head 与 `integration_target`：短 Worker 合入长期分支时只清理 head，并要求 PR `baseRefName` 精确匹配；持久元数据声明 `long-lived` 后，调用方不得降级绕过保护。

### 关联

- 机械实现位于 `multi-agent-orchestration` v2.16.1；确定性回归覆盖长期目标保留、长期源分支全资源保留和生命周期防降级。

## [1.8.0] - 2026-09-05

### 新增

- 新增编排 worker 的验收后单任务清理协议：交付完成后默认收口远端分支、worktree 与本地分支，并统一输出 `CLEANED`、`RETAINED_WITH_REASON`、`CLEANUP_PENDING`。

### 安全

- 清理绑定 exact PR/head、40 位 worker tip、delivery commit、远端 tip、干净 worktree 和已结算 lifecycle；查询失败、未知状态或身份漂移一律失败关闭。
- squash/rebase merge 下不使用无条件 `git branch -D`，改为 worktree 移除后以 expected tip 为 old-value 精确删除本地 ref；清理失败作为独立债务，不重放已经确认的 merge/push。

### 关联

- 机械实现位于 `multi-agent-orchestration` v2.16.0 的 `pm-closeout.sh` 与 `pm-cleanup-worker.sh`；本 Skill 保持 Git 安全判据与批量清理授权边界。

## [1.7.1] - 2026-09-05

### 改进

- 「分支清理」的 24h 时间过滤段新增机械执行指引：PR 已 `MERGED` 且分支无消费者时的即时清理，由 `multi-agent-orchestration` 的 `scripts/post-merge-cleanup.sh` 按 git-workflow 删除资格真值机械化（唯一 MERGED PR + headRefOid 精确一致 + 无 stacked child + worktree 干净 + 非长期/默认分支 + 生命周期已结算，删除后强制零残留验证）。明确即时清理是「已合并且无消费者」对 24h 规则的显式例外，只针对显式指定的单个分支；批量审计仍必须走本节完整流程。本 Skill 未改脚本与规则本身。

## [1.7.0] - 2026-09-04

### 新增

- 新增长期集成分支模式：大型功能跨多个子 PR 或开发波次时，以具名长期分支作为功能线 `mini-main`，worker 从其最新远端基线创建短分支并显式向该分支提 PR。
- 新增 `references/long-lived-integration-branch.md`，固定建线合同、通用修复与功能专属修改的流向、波次同步冻结、里程碑集成 PR 和分支生命周期。

### 安全

- 长期集成分支按默认主干同等级门禁维护，禁止 rebase、force-push、无门禁堆积或随子 PR 删除；默认主干只在无待合并子 PR 的波次边界向长期分支同步。
- 明确 Monorepo 普通短分支的 rebase 建议不适用于长期集成主干，避免公开协作基线被改写。

### 改进

- 新建短分支不再一律假定以 `main` 为 base；项目声明 `integration_target` 时，从对应远端集成分支起步，并以该 ref 作为 safe-push 的完整 PR range 基线。

### 决策依据

- 来源：Badminton Lab 教学课程分析线需要跨多个独立 Worker/PR 长期推进，同时保持阶段成果可验收，并在具名里程碑后再集成回 `main`。
- 职责边界：分支拓扑、Worktree、PR base、同步与合并归 `git-workflow`；`git-batch-commit` 继续只负责提交拆分与提交信息生成。

## [1.6.0] - 2026-07-13

### 新增

- 新增只读 `scripts/check-outgoing-identities.sh`：仅接受当前 HEAD 与远端跟踪 PR base，逐 commit 核验 author 与 committer 的 name/email；同名 feature upstream 判为 ambiguous，拒绝用 `HEAD~1` / 本地 ref 缩窄范围。
- 新增 `scripts/safe-push.sh`：刷新 integration base 后运行身份门禁，确认 HEAD 未变化，只把已核验 immutable OID 推到目标远端分支，使检查证据绑定实际 push 对象。
- 新增 11 项故障注入，覆盖早期污染但 HEAD 正常、feature upstream 隐藏已 push 污染、非远端 base、committer 单独污染、空 range，以及 safe-push 远端 ref 与核验 OID 一致。

### 安全

- 固化 worktree 身份隔离边界：worker 禁止写 repo-local `git config user.*`，提交默认使用单次 `GIT_AUTHOR_*` / `GIT_COMMITTER_*`；禁止 raw push，必须通过 identity-bound safe-push 核验完整 PR range。

### 关联

- 来源：法律 AI 书项目 T158 / DEC-131 的并发 worktree 身份污染实战。

## [1.5.0] - 2026-07-11

### 新增

- **§2 Worktree 加"开 worktree 前必做 3 查"块**：本地 `main` 可能落后 `origin/main`（本地独有未 push / fetch 滞后 / 别的 session 在 origin 推了新内容）。基于"过期 main"开 worktree 提 PR 时 GitHub 报 `not mergeable: the merge commit cannot be cleanly created`，且 PR diff 不包含 origin/main 已合内容，DECISIONS 编号可能撞车、TASKS 已勾项要重做。3 查清单 = `git fetch origin` + `git rev-parse main/origin/main/merge-base` + `git log origin/main..main` 看独有 commit。判读规则表覆盖 4 种情况（无分叉 / 本地领先 / 本地落后 / 双向分叉）。**禁止**基于过期 main 开 worktree 后再补救。
- **§2 加"本地独有 commit 未 push 的处理"**：`git log origin/main..main` 显示本地独有时 3 选 1（push / merge origin/main 保留 / reset 放弃），明确禁止擅自 `git reset --hard` 丢弃独有 commit。
- **§4 PR 工作流加"自 PR 自 review 限制"子节**：GitHub 不允许 PR 作者自 approve（`gh pr review --approve` 报 `Review Can not approve your own pull request`）。自 PR 用 `gh pr merge --squash --delete-branch` 直接合（无需 review approval），前提是仓库无强制 review 的 branch protection。`gh pr merge --delete-branch` cleanup 阶段报 `'main' 已经被工作区使用` 是 warning，不影响合并本身（`mergedAt` 时间戳写入即成功）。
- **§10 新增「多 worktree 并行与 main worktree 占用」**：并行推进多个任务时，主仓库 attach 到 `main` 会导致 `gh pr merge` cleanup 报错。3 方案：方案 A（推荐）主仓库不 attach main / 方案 B `git worktree add` 给 main 单独 worktree / 方案 C 临时释放 main。附 `gh pr merge` cleanup warning 时的快速判断流程（state/mergedAt/mergeCommit 三查）。

### 决策依据

- 来源：vision-extract 模型池项目（PR #45）合并实战（2026-07-11）。
- 主要痛点：本地 main drift（12a97ee docs 未 push，origin 已合 PR #44）+ 多 worktree 并行（主仓库 + PR worktree + v0.9.1 端到端 worktree）时 main 被占用。
- 解法：文档级 3 查清单 + 3 个 main 占用解决方案，把实战教训沉淀进 git-workflow 主流程规范。

## [1.4.2] - 2026-06-30

### 新增
- **分支清理加 24h 时间过滤 + 陷阱 2(活跃分支误判)**:`--merged main` 两方向都不可靠(陷阱 1 squash 漏判 + 陷阱 2 活跃分支停在 main commit 误判已合并)。新增"最后提交 < 24h 一律保留"时间过滤(主活跃度信号),`git for-each-ref --sort=committerdate` 取日期。判定规则加时间行 + worktree-未提交行。红线加三条:删<24h 分支 / 盲 `--force` 删 worktree(先查 `git -C <wt> status`)/ 仅凭 `--merged` 删。来自 book repo 误删活跃 deai 分支的实战教训。

## [1.4.1] - 2026-06-06

### 改进
- 精简 `SKILL.md` frontmatter `description`：保留分支管理、Monorepo 安全合并、PR、冲突处理、cherry-pick、安全回退和 branch cleanup 等触发边界，删除具体命令细节和项目特定后置动作。
- 将 `doc-curator` 文档体检从默认动作调整为可选项目扩展：仅在当前项目明确配置 `doc-curator` subagent 或同等流程时执行；未配置时跳过，不影响 Git 工作流。

### 文档完善
- 同步 README 技能列表、最近更新区和 Marketplace 清单中的 `git-workflow` 描述与版本号。
- 为 `skills/git-workflow/DECISIONS.md` 和 `skills/git-workflow/TASKS.md` 增加 `.gitignore` 例外，使技能级决策与任务记录可随仓库追踪。
- 将最近版本记录中的 `Added` / `Reason` 标签调整为中文分类，符合本项目 CHANGELOG 规范。

## [1.4.0] - 2026-06-06

### 新增
- **§2 新增「批量审计：已合并分支清理」子节**：仓库累积一批已合并 PR 后做集中清理时，权威依据是 `gh pr list --state merged`，不能仅信 `git branch --merged`。
  - 核心陷阱：`git branch --merged` 只识别"提交可达"，对 **squash merge** / **rebase merge** 一律失效（main 上的合并 commit 是新生 SHA，原分支 tip 不在 main 历史里，分支被误判为未合并）。
  - 完整流程：snapshot → 列候选（参考用）→ `gh pr list --state merged --search "head:<branch>"` 交叉验证 → 候选表展示 → 用户确认 → 批量删除 → `git fetch --prune`。
  - 判定规则表（merge commit / squash-rebase merge / closed 非 merged / 未推送 WIP / stale ref）。
  - 辅助指纹：`git rev-list --left-right --count main...origin/<branch>` 返回 "ahead N, behind 1" 是 squash-merged 的典型形态，**仅是提示**，仍以 PR 状态为准。
  - 红线（fail-closed）：仅凭 `git branch --merged` 删 / 仅凭 ahead-behind 删 / 把 CLOSED 当 MERGED / 跳过确认就推删除 / `-D` 强删本地以"对齐远端"。
- **description / frontmatter 关键词扩充**："已合并分支审计""清理已合并的远程分支""branch cleanup""有没有分支没清理"加入自动触发词。
- **§6 速查**：`git remote prune origin` / `git push origin --delete` 两行下方加导引指针，指向 §2 完整流程。

### 决策依据
- 来源：Folia 2026-06-06 实操。4 个已 squash-merge 的远程分支（feat/statusbar-copy / fix/about-qr-align / fix/font-preview-live / fix/settings-flash）跑 `git branch --merged origin/main` 完全没有输出，Agent 第一时间没意识到 squash merge 会让这条检查失效，差点漏判。
- 现状：§2 原「分支清理」只列了 `git branch -d` / `git push origin --delete` 两条命令，没说明何时安全何时不安全；§6 速查的 `git remote prune origin` 注释只解决"远端已删，本地 ref 还在"的反向场景，不覆盖"本地/远端分支还在，但 PR 已合并"。
- 决策：在 §2 新增完整子流程，保留 §6 速查命令但加导引指针，避免速查表膨胀。

## [1.3.0] - 2026-06-03

### 新增
- **「PR 创建后立即跑 mergeable 检查（强制）」**：Agent 在 `gh pr create` 成功后立即跑 `gh pr view <N> --json state,mergeable,mergeStateStatus,baseRefName,headRefName,files`。`mergeable=CONFLICTING` 时**不要**直接 `gh pr update-branch`，先按决策表选方案。
- **「base 落后 / 冲突处理决策表」**：三选一方案：
  - 方案 A：冲突仅在 docs 同步文件 → 本地 rebase + 重新编号 + `--force-with-lease` push
  - 方案 B：冲突在共享代码 / 实质代码 → `gh pr close --delete-branch` + 重建分支 + cherry-pick 实质代码 + 重新写 docs + new PR
  - 方案 C：冲突极少 / 1-2 个文件 → GitHub PR UI 手动解决
  - **禁止** `git push --force`（不带 `--force-with-lease`）
- **「远端 stale ref 清理」**：合入后跑 `git remote prune origin` 清理不存在的远端 ref；手动删某个远端分支用 `git push origin --delete <name>`。

### 决策依据
- 来源：FaroPDF v0.1 Wave 1 真实合并 PR #18 / #19 前的根因复盘。
- 主要根因：提 PR 后没立即查 mergeable；本地 main 与 origin/main drift 后 push 报 non-fast-forward；squash merge 引入的"内容相同但 history 不同"被误判为冲突；多个 PR 共享 CHANGELOG 段、DEC 编号无 PM 收口。

## [1.2.0] - 2026-06-03

### 改进

- 描述部分中文化：PR body 模板的 `## Summary` / `## Test plan` 改为 `## 摘要` / `## 测试计划`，PR 正文最低要求表区块改为「摘要」「测试计划」「Agent 归属」「关联任务」「风险」。
- 表格与命令注释中文化：分支命名、Monorepo 合并、PR 合并、PR 状态检查等章节的表格与代码注释改为中文。
- `references/issue-pr-format.md` 表格和说明中的 `Multi-Skill` 改为「多 Skill」。

### 保留

- 英文类型前缀（`feat` / `fix` / `docs` / `chore` / `refactor` 等）以兼容 GitHub 标签和 Conventional Commit 工具链。
- 通用 Git 术语（`Rebase merge` / `Squash merge` / `Merge commit` / `cherry-pick` / `worktree` / `Monorepo` / `commit` / `PR` / `CI` / `checks` / `review` 等）保留英文，避免生硬翻译。

## [1.1.0] - 2026-05-17

### 新增

- PR 正文最低要求：`Summary`、`Test plan`、`Agent Attribution`、`Issue/Task` 和风险说明。
- Monorepo PR diff 检查清单：跨目录污染、大量删除、敏感配置、lockfile/schema/版本清单不一致时阻断合并。

### 改进

- `references/gh-cli-quickref.md` 增加 `gh pr diff --stat` 和 PR 模板缺失时的 fail-closed 提醒。

## [1.0.0] - 2026-05-17

### 新增

- 正式迁入 `legal-skills/skills/git-workflow/`，作为公开技能集合中的 Git 全流程工作流 Skill。
- 补齐正式发布元数据：`homepage`、MIT 许可证文件、README 技能列表和 Marketplace 条目。

### 改进

- 按正式发布版本规则将 Skill 版本设为 `1.0.0`，保留私有开发阶段 `0.3.0` 及以下历史记录。

## [0.3.0] - 2026-05-17

### 新增

- PR 合并前检查命令序列：读取 PR 状态、draft 状态、mergeable、reviewDecision、diff 文件列表和 checks。
- Cherry-pick 安全流程：工作区干净、先看 commit 范围、默认 `-x` 保留来源、回补后检查范围。
- Monorepo 场景下的目录级提取规则，避免 cherry-pick 整个 commit 带入无关文件。
- Issue / PR 命名参考增加边界说明：GitHub Issue 不作为项目常规任务状态源，项目任务仍以项目配置的任务源为准。

### 改进

- `references/gh-cli-quickref.md` 增加 fail-closed merge gate 速查。
- `TASKS.md` 同步标记 PR 合并检查和 Cherry-pick 规则已完成。

## [0.2.2] - 2026-05-17

### 新增

- 新增 `TASKS.md`，补齐 `git-workflow` 的维护任务上下文。

### 改进

- `SKILL.md` 参考资源增加 `TASKS.md`，方便后续代理查看当前关注和后续优化方向。

## [0.2.1] - 2026-05-17

### 改进

- 将提交规范内置到 `SKILL.md`，不再在主流程中引用其他 Skill 的提交规范文档。
- 保持职责边界：`git-workflow` 拥有 Git 流程中需要用到的提交格式要求，批量提交自动化仍由专门的提交工具负责。

## [0.2.0] - 2026-05-17

### 新增

- PR review / merge 默认 fail-closed：diff 不可读、CI/checks 未知、review 结论不明确时不得自动合并。
- 明确 `git-workflow` 只拥有 Git 安全规则；任务状态归 `cross-agent-collab`，本地 Agent 会话归 `parallel-agent-workflow`。

## [0.1.0] - 2026-05-15

### 新增

- 创建 git-workflow skill，覆盖 Git 全流程操作
- Git 安全协议：禁止操作清单和安全原则
- 分支管理：命名规范、创建/清理流程、Worktree 使用
- Monorepo 安全合并：目录级 checkout 规范（从 AGENTS.md v1.7.4 迁移）
- PR 工作流：创建/审查/合并（基于 gh CLI）
- 合并冲突解决：检测、解决原则、lock 文件处理
- Issue 与 PR 命名规范（从 git-batch-commit v1.2.5 迁移）
- 常用 Git 操作速查：撤销、暂存、cherry-pick、tag
- `references/gh-cli-quickref.md`：gh CLI 命令速查
- `references/issue-pr-format.md`：Issue 与 PR 命名详细规范

### 参考

- 整合自 github/awesome-copilot@git-commit（30.8K 安装）
- 整合自 github/awesome-copilot@gh-cli（21.3K 安装）
- 整合自 cursor/plugins@fix-merge-conflicts
- 整合自 cursor/plugins@new-branch-and-pr
