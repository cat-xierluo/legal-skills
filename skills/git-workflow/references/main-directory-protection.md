# 主目录固定 main，Agent 开发使用独立 worktree

## 当前合同（2026-10-06 用户明确调整）

所有项目的 Agent 开发、编辑、测试和提交在各自独立 worktree 中完成。主目录保持 main，作为稳定加载入口；仅具名集成者可按已核清单串行采用成果。此要求替代 2026-10-05 的“主目录允许普通编辑及 add/commit”默认。仓库默认分支名称另有明确约定时沿用该名称，不擅自重命名；本脚本目前仅实现 main 保护。

共享的应是仓库对象库和成果，不是多个 Agent 同时编辑的主目录或索引。一个工作树只交给一个具名 writer；提交前核真实 cwd、根目录、分支、完整 HEAD 和允许路径。Skill/套件从创建开始稀疏检出，方法只在 [稀疏合同](sparse-worktree.md) 维护。

### 开始开发

先复用属于本任务且适用的树，否则创建独立树。不能为建树清理、stash、reset 或切换主目录。发现主目录不是 main 时保留现场并排查，不自行 switch/checkout 回 main；这种“修正”本身也会换掉共享文件。已有在途会话的材料保留，沿原 owner 的安全交接迁移，不能强停任务或把未回执者视为停写。

### 采用与交付

集成者在任务记录中绑定本人、候选 OID、来源、允许路径、主目录 HEAD 和原 index/dirty。完成差异与消费者验证后，仅采用已核增量；本机较新提交和他人未提交修改必须保留，任何目标文件、HEAD 或 index 的并发漂移都停止该次采用。禁止主目录 checkout/pull/reset、整枝合并或旧目录复制来“同步”，具体对账走 [改动集成](change-integration.md)。

在 worktree 提交只是候选完成，不等于共享 Skill 已更新。还要核实际安装链接、加载版本与候选哈希。共享入口指向经过采用的 main 或有来源记录的固定快照，不指向临时开发树。云端发表另按已有授权；不由本合同自动推送。

### 审查与试验隔离

审查任务交付完整候选 OID、允许范围、diff 和隔离 worktree，或交付能覆盖审查问题的只读副本。不要把共享主目录作为 reviewer 的执行目录。需要核对实际安装时由具名集成者只读导出版本/哈希，交回 reviewer；不让 reviewer 在主目录验证“某写命令会不会失败”。

不给 reviewer 主目录路径只是降低误触发面，不是强制隔离。Full Access reviewer 仍可能通过共享 workspace 的符号链接、`git worktree list`、`.git` 常见目录名或进程环境自行发现主目录。要强制阻止该类访问，必须另行接入 runtime 命令拦截或 OS/账号隔离，并实测拒绝前现场不变；未接入时按 NOT_VERIFIED 处理。

`read-tree`、`checkout-index`、直接写 index/ref 和文件 API 与 `reset/checkout` 同样可能覆盖现场；不能因为它们是底层命令、带 dry-run 字样、上一步失败或只想“恢复索引”就执行。Git 命令失败不证明文件未变；管道末端成功也不代表前端 Git 成功。实验只用一次性的隔离仓库。

### 具名采用前的可恢复快照

主目录只读 `status/diff/show` 不必每次复制仓库。具名采用或其他已授权的工作区/index 风险操作之前，先在仓库外保存**实际内容**并验证；只保存路径、状态行、index 或 commit 不足以恢复未暂存正文。

```bash
python3 "$git_workflow_dir/scripts/main-directory-snapshot.py" \
  --repo "$main_repo" --safety-root "$external_safety_root" \
  --label pre-main-adoption
python3 "$git_workflow_dir/scripts/main-directory-snapshot.py" \
  --verify "$actual_snapshot_dir" --ledger "$external_manifest_ledger"
```

保存已修改/新增/重命名/冲突路径的工作区版本、符号链接目标、删除状态、原 index bytes 与变化路径的 staged blobs，使用 NUL 分隔状态避免空格/中文/换行文件名被误读。文件改为目录时递归保存其内容；链接只保存目标字符串，不跟随到外部。经由符号链接目录的路径按真实内容保存，并在 `via_symlink` 记录链接链，恢复时才能还原同样的目录形状。ignored 默认不复制，先核其用途、大小和隐私；风险操作可能影响它们时加 `--include-ignored`，或按 owner 的独立备份清单保全，不能把排除项称为全量备份。

创建与复验都须退出 0 且结果为 PASS；失败、源漂移或 `INCOMPLETE.json` 均阻断后续采用。脚本另在快照目录外的 `MANIFESTS.jsonl` 登记摘要；复验缺少该账本时返回 NOT_VERIFIED、退出非零。采用记录保留账本及快照摘要；同权限程序仍可修改两者，这不是签名或 OS 安全边界。

快照身份、逐文件哈希与原现场绑定；快照后有写入须重新核对并重新保全变化。它不冻结并发 writer，也不自动恢复文件。`--max-bytes` 默认 2 GiB，超额失败并保留 INCOMPLETE，不把部分副本当完整快照。硬链接关系、稀疏文件布局不保留，按独立文件字节备份。

`--verify` 核快照相对于仓外摘要的一致性，不证明快照内容等于事故前的仓库状态；后者需要与事故前清单或采用记录逐项比对。submodule/嵌套仓库不复制内部状态，另作子仓快照；`skipped.json` 明确列出未覆盖范围。`skipped` 非空时不能称全量保全，主目录采用门禁拒绝继续。

大规模 dirty 主目录的快照有时间和磁盘成本；`add→commit` 两次 index 写入之间会要求新快照。若该成本开始诱使操作者绕开门禁，停止本次主目录采用，改为完整 PR/固定版本安装路径，或先收敛/迁移未提交现场。不用“成本高”作为跳过保全的理由。

恢复时先导出到仓外候选并逐文件核来源、字节/模式/链接与置信度，保留事故后有效新增；需要恢复同一文件的前后两版时合并并核实，不能仅因 status 行数相同宣称全文恢复。恢复执行遵循[事故恢复](accident-recovery.md)，不整体覆盖主目录。本机快照防覆盖误操作，不是异机备份；二进制和私有快照留在仓外，不自动入 Git 或上传。

## 命令入口门禁

`scripts/main-git-gate.py` 在 Git 执行前判断真实目录，默认只允许受管主目录的读取命令。具名采用必须显式给出 owner 和核验过的完整主目录 HEAD：

```bash
python3 "$git_workflow_dir/scripts/main-git-gate.py" \
  --repo "$main_repo" --git "$real_git_binary" -- status --short
python3 "$git_workflow_dir/scripts/main-git-gate.py" \
  --repo "$main_repo" --git "$real_git_binary" \
  --integration-owner "$verified_owner" --expected-head "$verified_main_sha" \
  --snapshot-dir "$actual_snapshot_dir" --snapshot-ledger "$external_manifest_ledger" \
  -- add -- "$reviewed_path"
```

`--check-only` 只检查、不执行 Git。具名 add/commit/取消暂存必须同时提供快照与账本；门禁复算快照，并核同仓库/HEAD、原 index、当前状态和实际文件内容。缺失、损坏、未保全部分或内容漂移均拒绝。每次 index 写入后（例如 add→commit）重新保全；每次提交改变 HEAD 后也重新核验并记录，不复用旧 expected HEAD。owner/HEAD 参数不证明用户授权、目标内容正确或独占锁已建立；检查与真实执行之间仍可能竞态，不能代替集成串行化。

| 经过入口的操作 | 行为 |
|---|---|
| 主目录 status/diff/log/show 等读取 | 放行，不锁 index/main 引用 |
| 主目录普通 add/commit/取消暂存 | 默认拒绝；具名且 HEAD 匹配的采用流程方可放行 |
| switch/checkout/工作区 restore/reset/clean/stash | 一律在执行前拒绝，集成参数也不豁免 |
| merge/pull/rebase/cherry-pick/revert/amend、底层 ref/index 覆写、未知 alias | 拒绝；维护另行绑定范围，不能当普通采用 |
| -C 路由、环境路由与配置覆写 | 核真实受管目录；不接受未知路由/配置绕过 |
| linked worktree 的 add/commit | 正常执行，仍受其任务允许路径与 owner 约束 |

具名 commit 只接受明确列出的普通选项（`-m/--message`、`-F/--file`、`-a/--all`、`-q/--quiet`、`-v/--verbose`、`-s/--signoff`、`--no-edit`、`--allow-empty`、`--allow-empty-message`、`--dry-run`）；不接受 Git 长选项缩写、历史改写或跳过 hooks。取消暂存只接受 `--staged/-S`、`--quiet/-q` 与路径；`--` 后按路径解释。其他形式拒绝后改用明确支持的写法，不能绕开门禁。

不修改系统 Git、全局 PATH，不覆盖原 commit hooks。只有经过此入口的命令受到这层保护。新 worker 启动时由其 runtime 接入并实测；不能只放脚本就记录“已接入”。旧 worker 不强制重启。全局 AGENTS 属协作规则，不能替代运行时执行控制。

## 验收与未覆盖边界

运行 `python3 scripts/test-main-git-gate.py`，使用临时真实 Git 仓库核：主目录开发命令拒绝后文件/HEAD/index 不变、具名采用、HEAD 漂移拒绝、check-only 不暂存、不同分支切换提前拒绝、独立稀疏 worktree 实际提交。

运行 `python3 scripts/test-main-directory-snapshot.py` 验证工作区与暂存双版本、冲突 stages、删除/目录/链接、特殊文件名、快照损坏、源漂移和复制失败；全部用隔离真实仓库，不拿主目录试恢复。脚本可用、规则已写、实际入口已加载、runtime 已接入、OS 权限隔离分别核验；缺哪一层就写 NOT_VERIFIED，不增加未执行的保护承诺。

这是命令入口护栏，不是文件系统安全边界。绝对路径 Git、未接入的 Agent、GUI 内置 Git/libgit2、直接文件 API 写入都可绕过；客户端未逐项实测为 `NOT_VERIFIED`。需要所有程序都不能切换时，必须另行做 runtime 强制策略或账号/沙箱隔离，不能由本脚本宣称达到。

不重装常驻 index.lock 或只锁 HEAD。仅锁 HEAD 的已知反例是 switch 虽退出 128，业务文件却已变成另一分支内容；post-checkout 是事后钩子，也不能实现事前拦截。现存锁先核 owner，不能自行删除。

## 历史四元数据模式（历史资料，不自动安装）

下文仅保留旧安装/解除合同用于核历史回执，不构成现行开发授权。现行规则见上文；不因为主目录改为加载/集成就自动重装锁。 旧 install 示例只适用于另有明确接受索引阻断授权的仓库，并必须补 `--allow-index-blocking`。


## 目标与边界

将稳定主目录作为 Skill 加载入口，保持 `HEAD -> refs/heads/main`。允许编辑、新建、删除该目录内的业务文件；Git 暂存、提交、分支开发在独立 worktree 完成。默认选择**分支保护**，不递归锁业务文件，不使用只读文件权限冒充分支保护。

仅适用于 macOS，使用标准库 `os.chflags(..., stat.UF_IMMUTABLE, follow_symlinks=False)`（等价于 `chflags uchg`）。同账号可以主动执行 `nouchg`，管理员也可解除；这是防常规误操作的护栏，不能宣称对任意程序绝对隔离。Linux/Windows 未实现，不能追认安装通过。

只锁主目录的四个元数据文件：

| 路径 | 作用 |
|---|---|
| `.git/index.lock` | 创建有具名 owner 的常驻锁标记，使 `switch/checkout/reset` 在取得索引锁时先拒绝，避免先改文件、最后才因 HEAD 不可写失败 |
| `.git/HEAD` | 拒绝直接更换符号 HEAD 或 detached 身份 |
| `.git/index` | 保护主目录索引，保留维护边界 |
| `.git/refs/heads/main` | 拒绝直接移动或删除 main 引用；要求真实 loose ref |

不锁共享 `objects`、其他分支引用、linked worktree 自有 HEAD/index，也不锁业务文件或符号链接外目标。因此独立 worktree 仍能检出、暂存和提交。主目录 `git status/diff/show` 可以读取，`git add/commit/pull` 会因索引或 main 引用保护被拒绝；不能承诺“主目录既可随意提交，又能拦截所有切换”。

常驻 `index.lock` 内含 `purpose: main-branch-guard`、owner 与外部清单指针。**不得将其当作遗留进程锁删除**。worker 不自动解除保护，不用 `GIT_INDEX_FILE`、另设 HEAD、改配置或替换元数据绕过。工具遇到其他已有锁会拒绝，先核持有者。

## 安装前

1. 核真人授权、真实仓库根、当前 main、固定 HEAD、Git/index 唯一维护 owner。原 Git writer 完成本批并交 `SAFE_STOPPED`；送达通知不是停写回执。文件编辑不等于 Git writer，不能为安装护栏强停独立业务。
2. 若涉及从其他分支恢复 main，先完整保全 tracked/index/untracked/ignored、原 refs 和任务来源；固定远端目标，核 main 已包含其交付。按[改动集成](change-integration.md)窄采用，不整枝 merge，不以旧本地 main 覆盖已交付远端内容。**本脚本不做恢复或保全，也不切分支。**
3. 根规则、Skill 发现入口、运行服务和正式 TASKS 来源须真实可达。迁移到 worktree 不代表旧符号链接自动有效；运行数据和 ignored 材料按原 owner 交接，不因缺少 tracked 文件认定丢失。
4. 证据清单放在仓库及 `.git` 外，权限 0600。真实 main ref 若被 packed，先在授权维护窗口具名处理并验证 loose ref；不让脚本擅自改 ref。

Git 停写回执格式（由维护 owner 填真实事实，不能从通知或任务文字自动生成）：

```json
{
  "state": "SAFE_STOPPED",
  "head": "完整当前main的40位SHA",
  "owner": "具名维护owner",
  "unknown_git_writers": false,
  "owners": [{"name": "原Git/index writer", "state": "SAFE_STOPPED"}]
}
```

## 安装与核验

先核远端固定基准；脚本只查询已核 `origin/main`，不自动 fetch。命令中的变量使用实际绝对路径与完整固定 SHA。

```bash
python3 "$git_workflow_dir/scripts/main-guard.py" install \
  --repo "$main_repo" --expected-head "$main_sha" --base "$verified_origin_sha" \
  --handoff "$external_handoff" --state "$external_guard_state"

python3 "$git_workflow_dir/scripts/main-guard.py" verify \
  --state "$external_guard_state" --probe
```

安装先独占创建 `.git/index.lock`，再锁元数据；保存原 flags、设备/inode、摘要与 HEAD。失败仅撤销本次新增 flags 和本次锁，保留首失败与清单；回滚异常不标完成。不会清场、改全局配置、创建后台监控、发表或复制凭证。`verify` 接受主目录正常业务文件变化，只核元数据身份、字节与 flags；不会把文件编辑误报成分支漂移。

验收必须同时包含：

- 在隔离仓库中新增、修改、删除普通 Skill 文件实际成功。
- 不同内容分支 `switch/checkout` 与相同内容 detached 切换均在索引准入时拒绝；文件和元数据前后不变。只锁 HEAD 而未测切换阶段不能算通过。
- 直接改 HEAD/main 引用失败；主目录暂存受限符合披露。
- 保护后，按[创建时稀疏合同](sparse-worktree.md)实际创建或复用独立树，修改并提交成功；不从对象库可写标记推断成功。
- 记录主目录 main 的 SHA、保护模式、实际拦截与未验边界；本机安装、业务验收、云端发表分别结算。

有界隔离回归入口：`python3 "$git_workflow_dir/scripts/test-main-guard.py"`。只使用临时 Git 仓库，macOS 外跳过并披露未验；不访问用户仓库。

## 维护与重新上锁

主目录采用新成果时，先具名维护 owner、原因、固定候选与允许范围；核当前 owner/HEAD/index 没漂移。保留主目录在维护期间可能新增的用户文件，不能因为之前装过保护就假定 dirty 为零。再显式解除：

```bash
python3 "$git_workflow_dir/scripts/main-guard.py" release \
  --state "$external_guard_state" --owner "$maintenance_owner" --reason "$maintenance_reason"
```

仅解除本工具新增的 flags，保留原有标记；最后移除本工具常驻锁。清单转为 `RELEASED`，不是安装完成态。中途失败保留 `RELEASING` 与首失败，同一 owner 可重新运行 release；续跑仍核 HEAD、文件身份/内容和原 flags，不删除已被替换的锁。状态原子保存，最后状态落盘失败也可在现场未漂移时收口。之后按范围集成，核 main 身份、完整材料/台账来源、最新基准与关键业务引用；用新 HEAD 停写回执、新清单路径重新 `install` 并 `verify --probe`，再实际核独立树提交。不能自动循环解锁/切回 main，不通过覆盖旧清单丢掉原 flags。

若此前安装了“整树不可写”保护，改为分支保护必须先建立常驻索引护栏，再按原安装清单解除**本次安装新增**的业务文件/目录标记，保留原有 flags；核文件写入与 Git 拦截后才更新模式。不得直接 `chflags -R nouchg` 抹掉用户原有保护，也不得将旧整树清单交给本脚本重复安装。

主目录文件编辑可以获得单独授权；并不转移 Git/index 维护权。现有原 PM 的 worktree TASKS、预算与人类门继续原合同，不能擅自把任务源改回主目录或从文件可写推断任何卡已验。
