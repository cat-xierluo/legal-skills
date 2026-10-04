# 仓库膨胀审计与瘦身 SOP

> 场景：仓库体积异常增长（「`.git` 太大」「仓库怎么这么大」「历史里有大文件」「瘦身」），典型受害者是每日 auto-commit 的配置同步仓（dotfile、工具配置仓库）——二进制运行时和 DB 每轮快照都被塞进历史。
> 实录：2026-10-04 `~/.hermes`（hermes-config-macbook-pro）：`.git` 2.6G→209M、目录 13G→7.6G；过程含一次 filter-repo 方向反转事故与完整恢复（§5）。
> 纪律：**先只读审计、后授权、再动手**；任何改写动作前先回答「哪里有完整备份」。

## 0. 适用与不适用

- 适用：本地/私有配置同步仓的膨胀排查、ignore 治理、历史瘦身；敏感文件泄露撤回走 [历史撤回合同](history-rewrite-and-removal.md)（本 SOP 是姊妹场景：目标是空间，不是泄露）。
- 不适用：公开/多人协作仓未经全部克隆所有者协调的历史重写；`.git` 正常增长（活跃开发的源码仓几百 M 属正常，别手痒）。

## 1. 本地只读审计与远端状态刷新

```bash
cd <仓库>
# ① 体积基线：.git 实占 + pack 构成
git rev-parse --git-common-dir
# .git 在附属树可能是文件；du/verify-pack 指向上项实际对象库路径
git count-objects -vH

# ② 历史最大 blob 定名（size 字节 + hash 反查路径）
git verify-pack -v .git/objects/pack/*.idx \
  | awk '$2=="blob" {print $3, $1}' | sort -rn | head -8 \
  | while read size hash; do
      name=$(git rev-list --objects --all | grep "^$hash" | head -1 | cut -d' ' -f2-)
      printf '%6.0fMB  %s\n' $((size/1048576)) "$name"
    done
# 路径为空仅是当前路径映射缺失；须核全部 refs/reflog/fsck 后才判不可达

# ③ 当前跟踪构成（顶层聚合 + 树内大文件）
git ls-files | awk -F/ '{print $1}' | sort | uniq -c | sort -rn | head -15
git ls-files -z | xargs -0 du -sk 2>/dev/null | sort -rn | head -15

# ④ 不可达对象
git fsck --unreachable --no-progress | head -5

# ⑤ 本地/远端分叉（配置同步仓高频病：远端早被别处重写，本地 push 一直静默失败，胖历史只活在本地）
# 本地只读阶段使用已缓存远端 ref，明确其可能陈旧
# 需最新远端时另行 git fetch origin；这会联网、写对象/ref/FETCH_HEAD，不称纯只读
git rev-list --left-right --count main...origin/main   # 左=本地独有 右=远端独有；右侧>0 且左侧也有 → 分叉
```

## 2. 归因判定（四类膨胀源 → 处置）

| 类型 | 特征 | 处置 |
|---|---|---|
| A. 活跃大文件 | ③里树内就有大二进制 | `git rm --cached` + `.gitignore`；历史无需动 |
| B. 历史大 blob（可达） | ②定名成功、路径是运行时/DB/附件 | ignore 治理 + filter-repo 剥离该路径全史 |
| C. 不可达对象 | fsck 与 refs/reflog 交叉核定 | 先核恢复点、其他 worktree/在途操作和完整备份；expire/gc 删除恢复依据，须独立精确回收授权，不能直接 prune=now |
| D. 分叉双线 | ⑤双侧均有独有提交 | 在隔离候选按内容/来源对账，保留双方有效成果；不能按提交日期决定丢弃哪条线 |

## 3. .gitignore 治理（配置同步仓白名单制）

原则（私有仓与公开仓一致——膨胀与隐私无关，别因为是私有仓就放松）：

- **默认只入库文本配置**：yaml/json/md/toml/源码/脚本；确有任务需要的二进制 fixture/金样须逐项核用途、体积、隐私、许可证与具名例外，不按扩展名一律剥离。
- **一律排除**：本仓任务不需要入库的二进制运行时（工具链、浏览器、node/python 发行版、venv）、DB 及其运行备份（`*.db`、`*.db-wal`、`*.db-shm`、`*.bak`、`*.retired-wal-*`）、缓存目录、会话附件、运行日志和临时锁；版本化依赖锁文件不因名称含 lock 就排除。
- **gitignore 对已跟踪文件无效**——老文件要么 `git rm --cached`，要么随历史重写一并剥离（§4）。
- ignore 规则提交时的信息里写明「曾致 pack 多少」的量级，给未来的自己留判据。
- 公开仓库另跑 [隐私预检](privacy-preflight.md)（完整提交、内容及说明）后再谈推送。

## 4. 历史重写安全门与执行

前置授权：私有单人仓经用户明示「可改写历史」；否则停。公开/多人仓见 [历史撤回合同](history-rewrite-and-removal.md) 的协调边界。

**安全门（按序，跳过任何一步都可能放大事故）：**

1. **先造兜底**：核实际全部远端/本地 refs、独有成果与文件材料；fetch 不证明远端是完整备份。先保存对象/refs 与整目录材料到私有仓外路径，并核可恢复——filter-repo 自带 `gc --prune=now`，跑完旧对象**立即不可恢复**。
2. **隔离与材料保护**：在[历史维护合同](history-rewrite-and-removal.md)规定的隔离副本内重写，不在共享源自动 commit/stash/reset。保留 index/原 dirty/ignored/untracked 与任务材料；只改被剥离路径的提交可能被 prune 成空提交，验收需核历史和最终树。
3. **方向门**：`--path X --invert-paths` 语义是「删 X」；**漏写 `--invert-paths` = 反转为「只留 X」**，配置全被剥掉、checkout 连带删工作区文件。重写后立即核对再继续：
   ```bash
   git ls-files | awk -F/ '{print $1}' | sort -u   # 构成对不对？
   git log --oneline | head -5                     # 提交数/信息对不对？
   ```
   方向不对马上停——此时尚未深埋、远端未动，恢复成本最低。
4. **预判连带删除**：被剥离路径的**原跟踪文件会被 checkout 从磁盘删掉**。是运行时目录（工具链/环境）时先确认可重装，或提前 `git archive origin/main -- <路径> | tar -x` 备出一份纯落盘副本。
5. **推送前全量验证**：fsck、构成、log、磁盘文件与保留材料核验后，按[历史维护合同](history-rewrite-and-removal.md)独立授权、冻结 refs 与精确 OID/lease 推送；漂移停止，后验逐 ref 核实际 SHA。

```bash
git filter-repo --force --invert-paths \
  --path <二进制目录> \
  --path-glob '*.db' --path-glob '*.db-wal' --path-glob '*.db-shm' \
  --path-glob '*.bak' --path-glob '*.retired-wal-*' \
  --path-glob '<附件目录>/*'
# 仅限已授权隔离副本；origin 可能被移除，恢复已核 URL 后按历史维护合同发表
```

推送遇到 SSL_ERROR_SYSCALL 等异常时，先核真实远端 refs 与已发表结果，再诊断网络。端口可连不证明隧道可用；不盲目重推、不自动修改代理或绕过既有通道。

## 5. 事故恢复路径（按优先级取用）

| 优先级 | 恢复源 | 能救什么 | 命令要点 |
|---|---|---|---|
| 1 | 远端 origin（未动时） | 全部历史 + 被 checkout 删掉的工作区文件 | 核远端真实 tree/refs，在隔离恢复目录导出已核文件，再按保留清单增量接回；reset 另核全部材料备份与具体授权，不在共享源直接执行 |
| 2 | 应用自备份 | 该应用的关键配置 | 逐处找：`backups/`、`*.good.*`、`state-snapshots/`、`.curator_backups/` |
| 3 | 运行中进程的环境 | .env 类键值 | 仅在用户明确授权恢复该进程凭证、其他备份不足时考虑；原始环境不输出到 stdout/日志，私有文件0700/0600，仅回填已核现有键；不能用通用管道抓取或按空格拆环境值 |
| 4 | APFS 快照 / Time Machine | 任意时点全量 | `tmutil listlocalsnapshots /`（注意快照可能恰好拍在事故后）；`tmutil destinationinfo` + 接上备份盘后 `tmutil listbackups` |

恢复动作**全部落盘核对后**才谈重推远端；私有临时材料按具名保留/删除授权处理，不能扩散密钥或自动删除唯一恢复源。

## 6. 残留如实告知

- 重写 + force push 后：GitHub dangling 提交仍可按 SHA 访问一段时间；其他机器的旧克隆全部深度分叉，各自按[历史撤回合同](history-rewrite-and-removal.md)对齐。
- 被 gc 掉的本地历史不可恢复——「哪些状态只存在于被销毁对象里」要向用户点明（实录中：skills 等 09-27→10-04 的演化回退到远端基线，等待 TM 盘接入再挖）。
- 静默 push 失败暴露出的分叉，修复合流后要观察下一轮自动同步是否恢复推送。
