# 仓库膨胀审计与瘦身 SOP

> 场景：仓库体积异常增长（「`.git` 太大」「仓库怎么这么大」「历史里有大文件」「瘦身」），典型受害者是每日 auto-commit 的配置同步仓（dotfile、工具配置仓库）——二进制运行时和 DB 每轮快照都被塞进历史。
> 实录：2026-10-04 `~/.hermes`（hermes-config-macbook-pro）：`.git` 2.6G→209M、目录 13G→7.6G；过程含一次 filter-repo 方向反转事故与完整恢复（§5）。
> 纪律：**先只读审计、后授权、再动手**；任何改写动作前先回答「哪里有完整备份」。

## 0. 适用与不适用

- 适用：本地/私有配置同步仓的膨胀排查、ignore 治理、历史瘦身；敏感文件泄露撤回走 SKILL.md §12（本 SOP 是姊妹场景：目标是空间，不是泄露）。
- 不适用：公开/多人协作仓未经全部克隆所有者协调的历史重写；`.git` 正常增长（活跃开发的源码仓几百 M 属正常，别手痒）。

## 1. 只读审计五步（不改任何东西）

```bash
cd <仓库>
# ① 体积基线：.git 实占 + pack 构成
du -sh .git; git count-objects -vH | grep -E 'count|size-pack'

# ② 历史最大 blob 定名（size 字节 + hash 反查路径）
git verify-pack -v .git/objects/pack/*.idx \
  | awk '$2=="blob" {print $3, $1}' | sort -rn | head -8 \
  | while read size hash; do
      name=$(git rev-list --objects --all | grep "^$hash" | head -1 | cut -d' ' -f2-)
      printf '%6.0fMB  %s\n' $((size/1048576)) "$name"
    done
# 路径为空 = 对象不可达（文件早已删除/改名，只剩尸体）→ 归入 §2-C

# ③ 当前跟踪构成（顶层聚合 + 树内大文件）
git ls-files | awk -F/ '{print $1}' | sort | uniq -c | sort -rn | head -15
git ls-files -z | xargs -0 du -sk 2>/dev/null | sort -rn | head -15

# ④ 不可达对象
git fsck --unreachable --no-progress | head -5

# ⑤ 本地/远端分叉（配置同步仓高频病：远端早被别处重写，本地 push 一直静默失败，胖历史只活在本地）
git fetch origin
git rev-list --left-right --count main...origin/main   # 左=本地独有 右=远端独有；右侧>0 且左侧也有 → 分叉
```

## 2. 归因判定（四类膨胀源 → 处置）

| 类型 | 特征 | 处置 |
|---|---|---|
| A. 活跃大文件 | ③里树内就有大二进制 | `git rm --cached` + `.gitignore`；历史无需动 |
| B. 历史大 blob（可达） | ②定名成功、路径是运行时/DB/附件 | ignore 治理 + filter-repo 剥离该路径全史 |
| C. 不可达尸体 | ②路径为空 / ④有输出 | `git reflog expire --expire=now --all && git gc --prune=now` 直接回收，无需重写 |
| D. 分叉双线 | ⑤双侧均有独有提交 | 先决定合流方向（谁的树新），重写必须在合流后的单线上做 |

## 3. .gitignore 治理（配置同步仓白名单制）

原则（私有仓与公开仓一致——膨胀与隐私无关，别因为是私有仓就放松）：

- **只入库文本配置**：yaml/json/md/toml/源码/脚本。
- **一律排除**：二进制运行时（工具链、浏览器、node/python 发行版、venv）、DB 及一切形态的备份（`*.db`、`*.db-wal`、`*.db-shm`、`*.bak`、`*.retired-wal-*`）、缓存目录、会话附件、日志、锁文件。
- **gitignore 对已跟踪文件无效**——老文件要么 `git rm --cached`，要么随历史重写一并剥离（§4）。
- ignore 规则提交时的信息里写明「曾致 pack 多少」的量级，给未来的自己留判据。
- 公开仓库另跑 `references/privacy-preflight.md`（token/密钥扫描）后再谈推送。

## 4. 历史重写安全门与执行

前置授权：私有单人仓经用户明示「可改写历史」；否则停。公开/多人仓见 SKILL.md §12 的协调边界。

**安全门（按序，跳过任何一步都可能放大事故）：**

1. **先造兜底**：确认远端是完整备份（§1-⑤ fetch 已做）；再整目录 `rsync -a` 一份到仓外——filter-repo 自带 `gc --prune=now`，跑完旧对象**立即不可恢复**。
2. **提交或储藏工作区改动**：重写的 checkout/reset 会丢未提交状态；只动被剥离路径的 chore 提交会被 prune 成空提交消失——别指望它留痕，重要说明写进最终的 sync 提交。
3. **方向门**：`--path X --invert-paths` 语义是「删 X」；**漏写 `--invert-paths` = 反转为「只留 X」**，配置全被剥掉、checkout 连带删工作区文件。重写后立即核对再继续：
   ```bash
   git ls-files | awk -F/ '{print $1}' | sort -u   # 构成对不对？
   git log --oneline | head -5                     # 提交数/信息对不对？
   ```
   方向不对马上停——此时尚未深埋、远端未动，恢复成本最低。
4. **预判连带删除**：被剥离路径的**原跟踪文件会被 checkout 从磁盘删掉**。是运行时目录（工具链/环境）时先确认可重装，或提前 `git archive origin/main -- <路径> | tar -x` 备出一份纯落盘副本。
5. **推送前全量验证**：fsck、构成、log、磁盘文件齐全，全过再 force push；push 后 `git ls-remote` 对 SHA。

```bash
git filter-repo --force --invert-paths \
  --path <二进制目录> \
  --path-glob '*.db' --path-glob '*.db-wal' --path-glob '*.db-shm' \
  --path-glob '*.bak' --path-glob '*.retired-wal-*' \
  --path-glob '<附件目录>/*'
# filter-repo 会摘掉 origin remote——重写验证通过后重新 add + force push
```

推送遇到 `SSL_ERROR_SYSCALL` 而走本地代理时：代理**端口活着 ≠ 隧道可用**，先试 `git -c http.proxy= -c https.proxy= push` 绕过直推。

## 5. 事故恢复路径（按优先级取用）

| 优先级 | 恢复源 | 能救什么 | 命令要点 |
|---|---|---|---|
| 1 | 远端 origin（未动时） | 全部历史 + 被 checkout 删掉的工作区文件 | `git fetch origin && git reset --hard origin/main`；纯落盘恢复用 `git archive origin/main -- <路径> \| tar -x`（不碰 index；先 `git ls-tree origin/main` 确认路径真的在远端树里） |
| 2 | 应用自备份 | 该应用的关键配置 | 逐处找：`backups/`、`*.good.*`、`state-snapshots/`、`.curator_backups/` |
| 3 | 运行中进程的环境 | .env 类键值 | `ps eww -p <PID> -o command= \| tr ' ' '\n' \| grep -E '^[A-Za-z_][A-Za-z0-9_]*='` → 只对**现有文件里已存在的键**静默回填，值一律不打印到会话输出 |
| 4 | APFS 快照 / Time Machine | 任意时点全量 | `tmutil listlocalsnapshots /`（注意快照可能恰好拍在事故后）；`tmutil destinationinfo` + 接上备份盘后 `tmutil listbackups` |

恢复动作**全部落盘核对后**才谈重推远端；过程中含密钥的临时文件（如从进程抽出的 env）用完即 `rm`。

## 6. 残留如实告知

- 重写 + force push 后：GitHub dangling 提交仍可按 SHA 访问一段时间；其他机器的旧克隆全部深度分叉，各自按 §12 对齐。
- 被 gc 掉的本地历史不可恢复——「哪些状态只存在于被销毁对象里」要向用户点明（实录中：skills 等 09-27→10-04 的演化回退到远端基线，等待 TM 盘接入再挖）。
- 静默 push 失败暴露出的分叉，修复合流后要观察下一轮自动同步是否恢复推送。
