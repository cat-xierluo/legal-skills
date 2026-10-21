# PM 总管的 PR 合并与本地/云端一致性治理

适用于已获授权协调多个交付的 PM：从作者交回候选，到独审、云端合并、本机采用分别结算。接续 [40 页](40-codex-app-native-coordination.md) 的写域与 canonical owner，不另建任务源或 Git 流程。

本页事件来自 2026-10-21—22 的 PM 治理交接；调用与扫描语义另核 `git-workflow` 源码。事件是已记录现场，不代表本次文档维护重演了真实合并、主目录同步或网关故障。私有原始回执留原任务；没有可复查证据的当前状态记 `NOT_VERIFIED`。

**权威与授权**：[PR 合同](../../git-workflow/references/pr-workflow.md)、[隐私合同](../../git-workflow/references/privacy-preflight.md)、[主目录合同](../../git-workflow/references/main-directory-protection.md)与[采用合同](../../git-workflow/references/change-integration.md)仍归 `git-workflow`。本页只补 PM 如何判读事故与组织证据。合并、本机维护、删分支各核原授权；下列示例不自动授权执行，也不绕过 runtime 拒绝。

## A. 合并门禁：先分清本地路径与 GitHub 仓库标识

**事件 A1**：把 GitHub slug 传给 `safe-pr.py --repo`，其内部 `git -C <slug>` 失败，统一报 `PRIVACY_GIT_READ_FAILED`，容易被误判为瞬时 Git 故障。

| 什么情况 | 怎么判 | 做什么 | 不能做什么 |
|---|---|---|---|
| `PRIVACY_GIT_READ_FAILED` | 先核 `--repo` 是否为可读本地检出、真实根和 remote；错误文本不能区分传参错与真正 Git 读失败 | 用 `git -C "$REPO_DIR" rev-parse --show-toplevel` 核根；参数正确后再查对象、祖先链和权限 | 先归因瞬时故障、连续重试、把 slug 当本地路径 |
| PR 仍为 draft | 核同一 PR 的 number、head OID、base 名与 base OID | 原授权和验收满足后 `gh pr ready "$PR" --repo "$GH_REPO"`；回读 OPEN、非 draft、head/base 未变 | 关闭重建 PR；把 ready 当合并许可 |
| 准备合并 | OPEN、非 draft、明确可合并；真实不同角色独审有明确 verdict；最终 head checks 通过；当前 head/base 与实际验证候选一致 | 冻结完整 OID、审查读集、验证命令/结果、最终文本；逐门核证后才调用 helper | 作者自签、用旧 head 的绿灯、把未知/等待/读失败当通过 |

`REPO_DIR` 是本地路径，`GH_REPO` 是 `<owner>/<repo>`。helper 的全局选项放在子命令前；正确调用形态：

```bash
python3 "$GIT_WORKFLOW/scripts/safe-pr.py" --repo "$REPO_DIR" --remote origin \
  squash --number "$PR" --expected-head "$REVIEWED_HEAD" \
  --title-file "$TITLE_FILE" --body-file "$BODY_FILE"
```

helper 只守隐私和候选边界，不代 PM 判断 review、checks 或授权。无 GitHub approval 要求时，真实不同角色、绑定当前候选的独立审查可以作为 review；仓库要求他人 approval 时仍须满足保护规则。没有 checks 时先核项目与保护规则，不能自行判 PASS。合并后回读 `MERGED/mergedAt/mergeCommit` 及目标内容；网络结果不明先查原 PR，不重放 mutation。

## B. base 前移：证明服务端只做了预期合并

**事件 B1**：main 在 PR 期间前进，head 不再包含新 main；`scan_range(main, head)` 的祖先检查按设计 fail-closed，不是隐私配置坏了。

| 什么情况 | 怎么判 | 做什么 | 不能做什么 |
|---|---|---|---|
| base 前移、无内容冲突 | 固定旧受审 base `B0`、旧 head `H0`、新 main `B1`，核差异、owner、更新授权及同步策略 | 经授权走服务端 update-branch；回读新 head `H1` 与父提交，核原 `H0` 和本轮 `B1` 被纳入 | 状态不一致仍合并；force push/rebase 改写已发表历史来对齐 |
| 服务端返回新 merge commit | 仅 API 成功不足；要核精确父提交及自动合并结果 | 本地 `merge-tree` 推算树，与服务端树逐字节一致才承接下一门 | 把 CLEAN 或 MERGEABLE 当作没有人工改动的证明 |
| 希望沿用旧内容审查 | 旧/新净变更的路径、状态、文件模式和 blob 身份一致，删除也显式列出；独审允许承接 | 保存映射及比较证据；原 review 仅承接等价内容，最终 checks、隐私历史扫描重新运行 | 只比文件数/标题/树摘要就免审；把内容等价扩大为 CI/隐私通过 |

在独占候选固定变量后，示例为：

```bash
gh api -X PUT "repos/$GH_REPO/pulls/$PR/update-branch" -f expected_head_sha="$H0"
git merge-tree --write-tree "$B1" "$H0"
git rev-parse "$H1^{tree}"
```

先 fetch 精确对象再比较。`merge-tree` 必须退出 0，首行 tree OID 与 `H1^{tree}` 完全相同，并以树清单/实际 blob 字节复核；有冲突的输出不能当预期树。API 等待结果不明时先查同一 PR。若操作期间 main 又前移，重新冻结基线，旧比较不证明当前候选。

净变更用 `git diff --raw --no-abbrev --no-renames -z B0 H0` 和 `B1 H1` 形成可回查清单，解析完整路径、增删状态、模式及旧/新 blob（`--no-abbrev` 保留完整 OID），核 blob 集合与映射一致。有交叠、模式变化、删除歧义或任何差异就交独审重审，不硬凑等价。服务端新增 merge patch/message 仍属隐私检查对象，旧例外不得自动套用。

## C. 隐私例外：绑定内容，保留原脚本语义

**事件 C1**：当时 `landline` 使用 `(?<!\d)0\d{2,3}-\d{7,8}(?!\d)`，没有 `mobile` 的标识符前缀负向后顾 `(?<![A-Za-z0-9])`，使证据目录 ID `know-002-20261004`、`know-003-20261011` 的日期片段误中座机规则。规则快照须核当前源码，不据此声称所有带前缀的命中都安全。

**事件 C2**：本次交接中的 `local-user-path` 例外仅针对已确认的合成占位符 `/Users/你/` 与 `/Users/alice`。它们不是待放行的真实本机目录；名字看似普通也不能自动认定占位符。

**事件 C3**：为定位命中而 monkeypatch checker，会破坏 `scan_patch` 根据原 `findings` 切片抑制完整 hunk 内路径删除行的逻辑，造出原脚本不报的假命中。

| 什么情况 | 怎么判 | 做什么 | 不能做什么 |
|---|---|---|---|
| 疑似 ID 被识别为座机 | 由独立 reviewer 枚举全树所有命中，并核待发表历史的 message/patch/blob；逐条确认是标识符片段、零真实号码 | 留完整本地清单与 verdict，再按内容绑定登记本地例外 | 只查两个示例；按关键词/目录通配放行；为赶合并放宽正则 |
| 占位符路径命中 | 回读实际 blob/patch 原始字节，确认全部命中均为已审合成占位符，复算 `content_sha256` | 对原脚本诊断的每种来源分别绑定，不以行片段摘要代替完整内容摘要 | 放行真实用户名、只核渲染后的文本、复用另一上下文的例外 |
| 插桩多报命中 | 先判断诊断是否改变扫描器状态或删除行抑制 | 在未插桩、未修改的原脚本复核相同候选；以原诊断为准 | 把插桩输出直接登记成例外或当成真实泄露 |
| 要写本地例外 | 核独审记录、准确来源与内容摘要及写入归属；例外文件可能被多个树共享 | 写前私密快照，记录条目数/字节数/SHA；写后解析回读、核条目数与字节数、验证旧条目保留，仅预期条目增加，再重跑原 checker | 覆盖他人例外、盲目追加、把策略/快照或原始敏感命中提交公仓 |

例外只绑定 **规则 + 来源字符串 SHA-256 + 完整内容 SHA-256**。格式、七字段、可用 kind 与来源字符串以[隐私合同](../../git-workflow/references/privacy-preflight.md#待核对项与精确例外)为准。换文件、改正文或换 OID 都重审；即使 blob 未变，commit patch/message 来源改变也不能沿用旧记录。例外不替代独立内容审查，真实敏感信息不能靠 `synthetic` 自证安全。

## D. 本地/云端收敛：先保护现场，再推进引用

**事件 D1**：`update-ref + reset --mixed` 推进 main 后，PR 的纯新增文件没有落盘，status 出现 ` D`。只看 HEAD/index 会误以为已采用；直接恢复全部删除又可能覆盖他人真实删除。

本节是**另行获授权的具名维护窗口**中的受限方法，不是默认主目录操作许可。[主目录门禁](../../git-workflow/references/main-directory-protection.md#命令入口门禁)默认拒绝 reset、底层 ref/index 覆写；runtime 拒绝时记录具体原因、交原维护 owner，不绕过，不自行解锁。本次任务只有文档/PR 授权时，不执行下列维护命令。

| 什么情况 | 怎么判 | 做什么 | 不能做什么 |
|---|---|---|---|
| 希望本地 main 追上云端 | fetch 后核 `origin/main` 是 HEAD 后继；ahead=0、behind>0；核真实主目录仍在 main | 列 incoming 与 dirty（含 staged/unstaged/untracked/删除/rename 两端）的路径交集及文件/目录前缀冲突；交集为空只是必要条件 | 以落后为由 pull/checkout/reset --hard/stash/clean；分叉或本地领先时丢弃有效提交 |
| 主目录在他人分支上 | 实测分支与 owner，不按树名猜 | 登记待处理、保留现场交原 owner | 自行切 main、回退他人分支 |
| incoming 与 dirty 不重叠 | 还须核 index、HEAD、目标文件、锁及 writer；mixed reset 会替换 index | 具名集成者冻结 old/new OID、原 index 与工作区快照；存在他人 staged 状态或不明 writer 时停止，交原 owner 处理 | 把空交集当充分授权；冲掉暂存状态；遇锁删除解锁 |
| 精确新增文件呈 ` D` | 旧 HEAD 无该路径、新 HEAD 有该路径，且写前就不存在、当前仍无文件/链接/目录冲突；核 sparse 范围 | 仅对已证纯新增精确路径用 checkout-index 落盘；逐文件核新 blob 字节 | 对全部 ` D` 批量恢复；覆盖原有删除、untracked 或 ignored 材料 |

通过上述授权和准入后，由唯一维护 owner 顺序执行的形态为：

```bash
git update-ref refs/heads/main "$NEW_MAIN" "$OLD_MAIN"
git reset --mixed "$NEW_MAIN"
git checkout-index -f -- '<逐项核实的纯新增路径>'
```

`update-ref` 的 old OID 是比较交换条件；不能补救 index/工作区并发。两步间没有跨文件原子性：每步重核，任一步失败保留已发生状态，不自动回退或重放。`reset --mixed` 不动工作区字节，但会重建 index；只有原暂存状态可保留且维护 owner 独占 index 时才准入。`checkout-index -f` 可覆盖文件，故执行前再次核精确路径仍不存在，并由 owner 串行维护；出现竞态立即停，不能称它天然零覆盖。其他干净但已存在的 incoming 修改/删除也不会被 mixed reset 物化，须另按[采用合同](../../git-workflow/references/change-integration.md)逐项采用和核验，不能只补新增就宣布整个工作区同步。

**验收看字节**：写前/后保留他人 dirty 路径集合，以及其真实编辑的 staged/unstaged diff block（固定 Git 参数、禁外部 diff/textconv）的 SHA-256；核原 index 语义、untracked/ignored 与删除状态。incoming 产生的暂态差异单列，不能混入他人集合凑数量相等。集合和 diff block 摘要都一致，incoming 的实际文件/删除/加载版本也逐项核实，才签本机采用。现场漂移无法归属则交回，不回滚他人新编辑。

云端合并、本机 main/ref 同步、工作区落盘与实际加载分别结算。删远端分支是另一次资源处置，沿[生命周期合同](../../git-workflow/references/branch-lifecycle-and-cleanup.md)核授权和占用；合并成功不隐含删分支。

## E. 候选不一致：先看有效内容，再决定向哪边对齐

**事件 E1**：`safe-pr.py` 两次 fail-closed 后核出 PR head 与本地 worktree HEAD 不同；本地多出的提交是有效的第三轮复审回执，并非垃圾。该诊断来自现场对账，不表示当前 helper 会直接比较本地 HEAD（它绑定 `expected-head` 与远端 head，并扫描精确范围）。

| 什么情况 | 怎么判 | 做什么 | 不能做什么 |
|---|---|---|---|
| 本地/远端/受审 head 不一致 | 固定三方 OID、各自独有提交和实际 diff，核回执/正文归属与是否有效 | 有效新增内容需交作者 safe-push、更新同一 PR 并重新绑定审查；确属另一候选则保留成果，交 owner 明确采用方向 | 上来就 reset 本地、重建任务或把多出的提交当垃圾 |
| 看似重复交付 | 按 [40 页判重矩阵](40-codex-app-native-coordination.md#9-重复任务识别与-canonical-owner)交叉核 cwd、写域、任务卡 ID、分支/提交、PR、产物路径与 SHA | 达到证据门槛才指定唯一 canonical owner，保留其他会话成果与身份 | 按标题判重、擅自关闭/覆盖在途会话 |

## F. 断联与限流：恢复原任务，限制并发

**事件 F1**：交接现场的 `429`、`exceeded retry limit`、`stream disconnected`、`server busy` 经网关状态核对属于 provider 容量问题；不是业务任务失败。错误字符串本身仍只是线索，别处的断联还可能来自网络/宿主，须核当次证据。

**事件 F2**：宿主曾拒绝直接唤醒 multi-agent v2 sub-agent 或已归档会话。实际拒绝是边界，不能由 40 页的工具存在性推断这些对象可接续；本次未测试其他宿主/版本。

| 什么情况 | 怎么判 | 做什么 | 不能做什么 |
|---|---|---|---|
| provider/网关容量失败 | 对照 turn 错误、provider 状态、额度/并发观测和最后一次真实产物 | 有发送授权且通道可用时给原 owner 一次有界恢复指令；容量未恢复则保留等待，独立项继续 | 归为任务缺陷、重派整卡、反复发送“继续” |
| 恢复执行 | 先只读核 `git status`、分支/HEAD、PR 状态与入口实际状态，确认原进度 | 从中断点继续，记录已完成、阻塞和下一步，保留原任务/会话/材料 | 重做、reset、丢弃现场、以回合结束当交付完成 |
| 宿主拒绝发送/唤醒 | 留原错误、目标身份和未送达状态 | 跳过该动作，交原 owner 或用户的合法接续入口；原任务保持待恢复 | 绕工具约束、擅自取消归档或新造任务冒充续跑 |
| 要追加并行 | 核当前 provider 容量、运行数与排队数；本次 `workbuddy-ai` 现场为 `accountConcurrency=2`、`queueLimit=2` | 以当前配置为准压住在飞与队列上限，错峰提交；数字只作当次观测 | 将 2/2 固定为全局默认、为提速改 provider 配置、把队列额度当执行槽 |

恢复消息应自包含，例如：“原任务与 owner 保持；已完成的产物/候选为……；最后有效验证为……；当前阻塞为……；请先只读核现场，再从……继续；不重做、不 reset、不丢弃现场；下一回执绑定实际 head/产物和验证。”发送授权、收件回执与静默仍按 [40 页](40-codex-app-native-coordination.md#6-跨会话动作)；Orca 429 批量恢复走 [20 页](20-orca-rate-limit-recovery.md)，不把本模板变成新的自动唤醒器。
