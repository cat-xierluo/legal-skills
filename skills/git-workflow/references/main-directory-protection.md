# 主目录固定 main，Agent 开发使用独立 worktree

## 当前合同（2026-10-06 用户明确调整）

所有项目的 Agent 开发、编辑、测试和提交在各自独立 worktree 中完成。主目录保持 main，作为稳定加载入口；仅具名集成者可按已核清单串行采用成果。此要求替代 2026-10-05 的“主目录允许普通编辑及 add/commit”默认。仓库默认分支名称另有明确约定时沿用该名称，不擅自重命名；本脚本目前仅实现 main 保护。

共享的应是仓库对象库和成果，不是多个 Agent 同时编辑的主目录或索引。一个工作树只交给一个具名 writer；提交前核真实 cwd、根目录、分支、完整 HEAD 和允许路径。Skill/套件从创建开始稀疏检出，方法只在 [稀疏合同](sparse-worktree.md) 维护。

### 开始开发

先复用属于本任务且适用的树，否则创建独立树。不能为建树清理、stash、reset 或切换主目录。发现主目录不是 main 时保留现场并排查，不自行 switch/checkout 回 main；这种“修正”本身也会换掉共享文件。已有在途会话的材料保留，沿原 owner 的安全交接迁移，不能强停任务或把未回执者视为停写。

### 采用与交付

集成者在任务记录中绑定本人、候选 OID、来源、允许路径、主目录 HEAD 和原 index/dirty。完成差异与消费者验证后，仅采用已核增量；本机较新提交和他人未提交修改必须保留，任何目标文件、HEAD 或 index 的并发漂移都停止该次采用。禁止主目录 checkout/pull/reset、整枝合并或旧目录复制来“同步”，具体对账走 [改动集成](change-integration.md)。

在 worktree 提交只是候选完成，不等于共享 Skill 已更新。还要核实际安装链接、加载版本与候选哈希。共享入口指向经过采用的 main 或有来源记录的固定快照，不指向临时开发树。云端发表另按已有授权；不由本合同自动推送。

## 命令入口门禁

`scripts/main-git-gate.py` 在 Git 执行前判断真实目录，默认只允许受管主目录的读取命令。具名采用必须显式给出 owner 和核验过的完整主目录 HEAD：

```bash
python3 "$git_workflow_dir/scripts/main-git-gate.py" \
  --repo "$main_repo" --git "$real_git_binary" -- status --short
python3 "$git_workflow_dir/scripts/main-git-gate.py" \
  --repo "$main_repo" --git "$real_git_binary" \
  --integration-owner "$verified_owner" --expected-head "$verified_main_sha" \
  -- add -- "$reviewed_path"
```

`--check-only` 只检查、不执行 Git。每次提交改变 HEAD 后重新核验并记录，不复用旧 expected HEAD。owner/HEAD 参数是调用者的具名意图与漂移检查，不证明用户授权、目标内容正确或独占锁已建立；调用方仍须完成上面的采用合同，不把这些参数当作普通开发开关。只检查模式与真实执行之间仍可能发生竞态，不能代替集成串行化。

| 经过入口的操作 | 行为 |
|---|---|
| 主目录 status/diff/log/show 等读取 | 放行，不锁 index/main 引用 |
| 主目录普通 add/commit/取消暂存 | 默认拒绝；具名且 HEAD 匹配的采用流程方可放行 |
| switch/checkout/工作区 restore/reset/clean/stash | 一律在执行前拒绝，集成参数也不豁免 |
| merge/pull/rebase/cherry-pick/revert/amend、底层 ref/index 覆写、未知 alias | 拒绝；维护另行绑定范围，不能当普通采用 |
| -C 路由、环境路由与配置覆写 | 核真实受管目录；不接受未知路由/配置绕过 |
| linked worktree 的 add/commit | 正常执行，仍受其任务允许路径与 owner 约束 |

不修改系统 Git、全局 PATH，不覆盖原 commit hooks。只有经过此入口的命令受到这层保护。新 worker 启动时由其 runtime 接入并实测；不能只放脚本就记录“已接入”。旧 worker 不强制重启。全局 AGENTS 属协作规则，不能替代运行时执行控制。

## 验收与未覆盖边界

运行 `python3 scripts/test-main-git-gate.py`，使用临时真实 Git 仓库核：主目录开发命令拒绝后文件/HEAD/index 不变、具名采用、HEAD 漂移拒绝、check-only 不暂存、不同分支切换提前拒绝、独立稀疏 worktree 实际提交。

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

仅解除本工具新增的 flags，保留原有标记；最后移除本工具常驻锁。清单转为 `RELEASED`，不是安装完成态。之后按范围集成，核 main 身份、完整材料/台账来源、最新基准与关键业务引用；用新 HEAD 停写回执、新清单路径重新 `install` 并 `verify --probe`，再实际核独立树提交。不能自动循环解锁/切回 main，不通过覆盖旧清单丢掉原 flags。

若此前安装了“整树不可写”保护，改为分支保护必须先建立常驻索引护栏，再按原安装清单解除**本次安装新增**的业务文件/目录标记，保留原有 flags；核文件写入与 Git 拦截后才更新模式。不得直接 `chflags -R nouchg` 抹掉用户原有保护，也不得将旧整树清单交给本脚本重复安装。

主目录文件编辑可以获得单独授权；并不转移 Git/index 维护权。现有原 PM 的 worktree TASKS、预算与人类门继续原合同，不能擅自把任务源改回主目录或从文件可写推断任何卡已验。
