# Monorepo 稀疏工作树

本页是稀疏检出规则与 Git 创建方法的唯一维护源。多 Agent 编排只引用本页，另维护 worker 的目录范围与启动合同。

## 1. 先决定检出范围

- 单 Skill、单套件迭代默认要求 cone 稀疏检出，只选目标目录与实际需要的共享依赖。全量例外分两类：任务本身需要全仓集成验证/跨模块迁移时，记录窄范围不足的依据及当前授权/预算；任务本可窄检出但仅因通道限制选择全量时，另须有用户/项目既有规则或本任务明确允许全量代价的选择来源、替代入口不适用原因与能力证据。缺少参数不是全量许可；用户禁止全量时任何例外都不适用，在创建前停止，不能省略选择后声称已经稀疏。
- 在既有任务卡写清所选 base ref 与完整 OID、目标目录、依赖目录及全量检出的原因。检出范围可包含只读依赖；它不扩大 allowed-files 写入授权。
- 先核当前已存在的适用工作树；复用和收拢已有树优先。未获对应授权时，不批量改 dirty、在途或其他 owner 的树。用户明确授权全面原地限缩时，终端存在不单独构成跳过理由；任务/依赖与本地材料必须有据，Git 持锁、身份或内容持续变化且无法核验时保留并复查，不停止业务进程。
- 按任务输入、相对引用与验证命令列出实际依赖，不将整个 `skills/` 当默认依赖。套件符号链接须核冻结提交中实际成员目录，不能只检出链接外壳或盲目跟随仓库外链接。写入授权与只读依赖分别记录。
- 刷新并核对明确的远端目标或集成分支；不为了开树去 reset、stash 或合并共享 dirty 主源。不自动带入主源未提交的变更。

## 2. 从创建开始避免全仓落盘

需要 Python 3 标准库和支持 `sparse-checkout set --cone --no-sparse-index` 的 Git，无额外 Python 包。缺依赖时报告缺失，不自动安装。脚本仅用于新建原生 Git 工作树，不启动 Agent，不赋予 push/PR/合并权限：

```sh
python3 "$GIT_WORKFLOW/scripts/scoped-worktree.py" \
  --repo "$PROJECT" --path "$NEW_WORKTREE" \
  --base origin/main --branch feat/target-skill \
  --scope 'skills/target-skill' \
  --scope 'shared/required-library'
```

`GIT_WORKFLOW`、`PROJECT`、`NEW_WORKTREE` 由当前已确认的安装路径和任务现场填写；目录是示例，只保留实际依赖。`--scope` 可重复，使用仓库相对目录，支持中文、空格。`--base` 必填，脚本解析并固定 OID，但不自动 fetch。已有目标或分支、非目录、父目录穿越、绝对 scope 均拒绝。

脚本先 `worktree add --no-checkout`，再设定 cone 模式与完整 index，最后首次按范围填充 index/文件；直接对未初始化 index 的新树只运行 `sparse-checkout set` 可能仍显示全仓删除。不得先检出全仓再缩小范围并称之为“创建时节省 IO”。失败保留新树与分支供排查，不强删现场。显式 `--existing-branch` 仅用于未占用的已有分支，要求其 tip 与冻结 base 完全一致；不 reset 分支，默认仍拒绝已有分支。Git 的 `set` 会启用共享 `extensions.worktreeConfig`，稀疏设置存于各工作树自身；不修改身份配置。共享 Git 历史与对象库不会缩小，使用完整 index 仍有独立元数据成本。

### 根规则与依赖

cone 模式保留根目录和所选目录祖先的直接文件，因此已跟踪 `AGENTS.md`、`CLAUDE.md`、`.gitignore` 等会保留。不存在或未跟踪的规则文件不会凭空复制；确认原任务需要的规则来源并在启动上下文中显式交接，不假定新 Agent 继承 PM 的聊天。

cone 不是“仅某一个文件”，也不是权限沙箱：选中目录内的全部已跟踪二进制仍会落盘，Git 命令仍可访问范围外的历史对象。缺依赖时先核授权，再追加最小目录：

```sh
git -C "$NEW_WORKTREE" sparse-checkout add -- 'shared/another-dependency'
git -C "$NEW_WORKTREE" sparse-checkout list
git -C "$NEW_WORKTREE" status --short
```

不要用全量 restore/reset、取消 sparse 或复制主源整目录来补依赖。合并/rebase 冲突可能临时带出范围外文件；解决具名冲突并核 dirty/材料后再决定 `reapply`，不得在别人的树上自动收缩。

## 3. Orca / Codex 创建能力

- 以本轮运行中指南、`--help` 和工具 schema 为准。2026-10-04 核对的 Orca 1.4.218 已安装包含 Sparse checkout 预设：仓库设置保存目录列表；新建工作区的高级设置选择预设。目录一行一个，中文空格不拆分，不添加 shell 引号。安装包能力已核对；本轮没有实际 GUI 创建验收。
- 同日 Orca CLI `worktree create --help` 没有 scope/sparse 选项；Codex `create_worktree` 工具 schema 也没有目录参数。不能虚构参数或把上述原生 Git 脚本产生的树冒充成宿主管理树。
- 编排路径必须保持安装/scope 门禁、Session Context、运行身份和监督完成链。不能为了稀疏改用立即启动 Agent 的入口，或用原生 Git 创建绕开原监督合同。当前入口无法保证首次检出范围时，先核第 1 节的全量例外；未成立就停在资源创建前，交 PM 选择已支持的入口。不能先复制再补救，也不能由 GUI 有预设推断 CLI 自动继承。
- 未获原地限缩授权时不改活跃旧树；已明确授权时按下节材料和现场保护逐树核验，不把宿主有终端等同于正在改范围外文件。改变新基准或取消文件跟踪不会自动回收旧树和历史对象。

## 4. 忽略规则、配置与体积分别治理

Git 默认检出提交中的全部跟踪文件，不复制真正未跟踪的 ignored 文件。已跟踪文件不受新增 `.gitignore` 影响；不同分支或未提交主源规则也不会自动传播。宿主可能通过 `.worktreeinclude`、symlink/sharedDirectories 或 setup 额外物化文件，需核实际配置与产物。

已有全量树可在保留路径、分支与 HEAD 的情况下转为 sparse，但先核原 owner、授权、任务范围、进程/监督生命周期与允许的现场基线。已授权的 dirty 树将全部修改/暂存/新增目录纳入保留，备份 index、补丁与本地材料，前后核实际内容和原 status，不 stash/reset 为干净。独立盘点 `git ls-files --others --exclude-standard -z` 与 `git ls-files --others --ignored --exclude-standard -z`，确认拟退盘目录内未跟踪/ignored 材料及链接实际归属，重要材料备份到仓库外并核可恢复，不打印配置内容。Git 在 cone 收缩时可能删除范围外仅含 ignored 文件的目录；`git status` 干净不保护这些文件，扩大 sparse 只恢复已跟踪文件，不恢复已删除的 ignored 材料。备份与归属不可证时不收缩，不能用 `clean` 或取消 sparse 处理遗留材料。Finder 缓存可能自行刷新：保留原备份，不覆盖更新后的缓存；业务/配置文件仍按实际字节核验。

稀疏检出减少每个 session 的物理检出；ignore 防止普通 add 新增文件；移出跟踪只影响未来提交；重写历史是另一个需明确授权的任务，不能混为已清理。不要按全仓后缀批量删除模板、fixture 或证据，不把未落盘文件视为仓库删除。

配置同步遵循该仓库的明确授权和发布范围。私仓是否允许 cookies、JSON、`.env` 由用户/项目选择，不在通用公开 Skill 写入一条适用于所有仓库的凭证放行策略，也不打印真实配置。二进制产物、原始浏览器 profile、可重建缓存与大型导出优先放仓库外，必要小模板/金样逐项留例外；大 HTML/JSON 也需体积审查，`.gitignore` 不能按字节阈值过滤。

## 5. 启动前验收

所有 Git 树均核实际仓库/路径/分支、HEAD 与冻结 OID 一致，目标/依赖/根规则实际存在。sparse 模式另核配置及 `sparse-checkout list` 对应目录、代表性范围外目录未落盘；合法 full 模式核具名全量选择、授权/预算及实际状态，不要求 sparse 列表或范围外目录缺席。新建树在写入脚手架前核 `git status --porcelain` 干净；后续只允许已声明的脚手架/配置增量。借用树依原合同核允许的现场基线，不为变干净覆盖或 stash 原成果。目标树身份不能由名字推断。独立记录文件占用与工作树元数据，不把共享对象库重复算作每树复制量。

运行 `python3 scripts/test-scoped-worktree.py`，以隔离 Git 仓库检查正反例；测试不改真实项目或运行中的工作树。脚本/本地 Git 行为通过不证明 Orca 监督派发或多轮 Agent 理解已验证。

## 6. 跨目录旧树治理

不要以某一个宿主目录作为仓库工作树全集。先从明确的仓库或已有树取得 Git common-dir 和 `git worktree list --porcelain -z`，覆盖 `.worktrees/`、`.claude/worktrees/`、Codex worktrees/visualizations、Orca 目录与临时目录中的实际登记；按 common-dir 去重。主工作区和已稀疏树单独保留，缺目录/坏登记另记，不自动 prune 或修复。未登记文件夹与其他机器需要独立的宿主/目录盘点，不能由 Git 登记空白推断不存在。

### 只读审计入口

使用 Python 3 标准库和 Git；`du` 用于目录占用，选用 `--with-cwd` 时以 `lsof` 观察本机 cwd。工具缺失或读取失败标为未验证，不自动安装；cwd 无命中不证明无 writer。宿主 owner、Session/终端和原任务范围仍须另核。

```sh
python3 "$GIT_WORKFLOW/scripts/sparse-worktree-audit.py" \
  --repo "$PROJECT" --repo "$OTHER_CONFIRMED_PROJECT" \
  --with-cwd --output "$PRIVATE_EVIDENCE/new-audit.json"
```

仓库参数可重复，跨目录已有树也可作为入口，同仓去重。仅给出摘要；完整清单以 0600 写到所有登记工作树和 Git 管理目录之外的新文件，拒绝覆盖和 Git 仓库/索引环境覆盖。不读取 ignored 配置内容，不发送 Session、终端输入或任何外部请求，不创建/收缩/删除树。Git 读取禁用 fsmonitor 辅助执行；只读核 clean/process 配置键和 tracked 文件实际 filter 属性，发现有效外部过滤器时不执行 status，dirty 标 `NOT_VERIFIED_EXTERNAL_FILTER`，由 PM 在原任务内核过滤器可信性、执行授权和材料后才可准入，不通过取消过滤器追认干净。仅配置未作用于 tracked 文件的过滤器不阻断状态观察。实际根路径/分支与登记不一致（例如链接冒充主源）标坏登记并保留。输出包含真实 sparse、目录占用、dirty/untracked/ignored 数量与登记异常；Skill 路径仅为存在性线索，不是任务范围或改造授权。运行 `python3 scripts/test-sparse-worktree-audit.py` 验证真实隔离 Git 正反例。

### 在原授权内逐树推进

1. 绑定原任务、owner、路径、common-dir、分支或 detached 身份、完整 HEAD、原 index 实体条目和 dirty 状态；核提交增量、原 Session 写范围、验证命令及实际读依赖。不按树名猜任务；主干桥接、读审树或空预留缺范围证据时保留并补查，不为了“全部绿”随便选目录。
2. 区分重复已跟踪检出、ignored 构建/依赖缓存、业务/配置与 Session 材料、Git 元数据和共享对象库。目录占用不是可回收量。稀疏不能自动清构建缓存；已授权收缩不等于授权删除缓存、树或分支。套件范围内的大二进制仍会保留。
3. 按第 4 节保留所有修改、暂存、新增与本地材料；冻结目标和逐项核实的依赖。仓库外备份 index、staged/unstaged 补丁、可能受影响的材料，记录类型/权限/链接与哈希。确认留在 scope 内的大缓存可以原位保留并做清单，不为备份复制整仓；可能退盘的重要材料须有可恢复副本。核备份卷和创建卷预算，清单/备份不公开提交。
4. 在实际操作前重新核身份、HEAD、Git 锁、dirty/index 和材料。用户已授权全面原地限缩时，不仅因终端存在而跳过；有 Git 锁、未解决的 index 冲突或现场持续变化而不能核验时保留、记录并在同任务重查。不停止业务进程，不 reset/stash/clean，不重建任务。单树失败保留账目与现场，不无边界重跑整批。
5. 仅对准入树原地设 cone 范围；前后比较路径、common-dir、分支/detached、HEAD、index 实体条目、原 dirty 状态、保留 tracked 字节和本地材料。正常 Session 日志更新分开记录，不能声称全部字节不变；Finder 缓存不覆盖新版本。回收以同树前后 `du` 实测，并单列新增备份成本，不能把历史对象也计入收益。
6. 逐树验收后核整个授权清单：converted、既有 sparse、范围待补、锁/并发重查、坏登记和主源保留都有去向。核代表性离线消费者；自然后续提交以实际 reflog 区分，不回滚活跃任务。只完成可证的范围，不把部分目录已处理宣称全仓或全机处理完。

此审计入口和上述合同不替代工作树删除/归档合同，也不签署宿主监督派发端到端通过。需要全仓集成的树沿第 1 节具名例外保留；Skill 新开发的默认仍是创建时稀疏，不以旧树治理为理由先全量创建。

## 参考

- [Git sparse-checkout](https://git-scm.com/docs/git-sparse-checkout)：cone、工作树配置、index 与追加目录。
- [Git worktree](https://git-scm.com/docs/git-worktree)：共享仓库与 `--no-checkout`。
- [gitignore](https://git-scm.com/docs/gitignore)：已跟踪文件不受忽略规则影响。
