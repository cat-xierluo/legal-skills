# 清理后的恢复留底与 GC 门禁

分支、Worktree 或悬空登记清理完成不等于空间已回收。清理后的收口分为四个独立阶段：保留恢复留底、审计并执行 GC、后验对象库与现场、释放恢复留底。每一阶段单独授权，前一段成功不扩大后一段权限。

## 1. 阶段边界

1. **清理完成**：精确 ref 删除或 Worktree 移除已按生命周期合同后验，恢复目录仍在仓外。
2. **GC 审计**：冻结 refs、HEAD、Worktree 登记、pack 构成、`.git` 实占、fsck 结果和锁文件；只读生成 baseline。Git 同步器改名文件（如 `NSConflict-*`）、无 idx 的 `tmp_pack_*` 只按垃圾线索分类，不得按文件名直接删除。
3. **GC 执行**：绑定 baseline SHA-256 与用户授权后运行 `git gc --prune=now`。不要顺手执行全局 `git reflog expire`、fetch、prune、worktree remove 或远端删除。
4. **后验与释放**：refs、HEAD、Worktree 登记不变；fsck 无致命缺失；`git rev-list --objects --all` 可完整遍历；`.git` 与 pack 变化记录成账本。全部通过并获单独授权后，才释放对应 recovery。

如果用户同时要求“删除留底并跑 GC”，默认先执行 GC 与后验，再释放留底。确因磁盘不足必须先释放时，先为当前对象库另建并验证完整恢复包；不得把已删除分支的局部恢复包冒充整个对象库的 GC 兜底。

## 2. fsck 分类

GC 前后必须运行 `git fsck --no-progress --no-dangling`，并区分三类输出：

| 分类 | 例子 | 处置 |
|---|---|---|
| 致命对象问题 | `missing`、`broken`、非 index 元数据的 `error` | 停止 GC，先定位引用和可恢复字节 |
| 活跃 index 陈旧元数据 | `invalid sha1 pointer in resolve-undo of .git/worktrees/.../index` | 可记录并经 approval 确认后继续；不得重写活跃 index |
| 对象库垃圾线索 | `bad sha1 file`、`garbage found`、`NSConflict-*`、无 idx `tmp_pack_*` | 单独统计；不因 GC 或瘦身自动删除 |

活跃稀疏 Worktree 的 index 含有大量 skip-worktree 标记和未提交现场。禁止用 `read-tree HEAD`、`update-index --index-info` 或重写 index 的方式消除 resolve-undo 报错。若确需修复，先完整备份 index，使用能保留 cache-tree、REUC、sparse 标记和 stat 的专用工具，并以 status/标志前后不变为验收；否则保留报错。

## 3. 缺失对象修复

GC 或同步器清理后发现缺失对象时，先只读定位：

```bash
git ls-files -s                      # index 引用
git ls-tree -r HEAD                  # 当前提交引用
git rev-list --objects --all         # 全引用遍历
git cat-file -t <oid>                # 对象是否仍可读
```

可从工作区重建时，必须先写入并比较完整 OID，OID 不一致即停止：

```bash
git hash-object -w -- <file>
cd <directory> && git mktree < <entries>
```

标准空树只能用 `git mktree </dev/null` 恢复，期望 OID 固定为 `4b825dc642cb6eb9a060e54bf8d69288fbee4904`。不要手工拼 loose object 文件名或复制未知来源对象。修复后重跑 fsck 与全引用遍历，并向用户说明根因和未验证范围。

## 4. 空间账本

空间收益使用同一路径前后 `du` 计算，不用单次 `df` 差额替代。报告至少分四列：

| 字段 | 含义 |
|---|---|
| original_freed | 清理 worktree、登记元数据或可见材料的原位置释放 |
| recovery_added | 新增恢复包、隔离目录或备份 |
| git_freed | GC 后 `.git` / common object directory 实占减少 |
| net_freed | 前三项合计，负数如实报告 |

同时报告对象数、pack 数、garbage 数和 recovery 剩余体积。`df` 受系统写入、APFS 空间回收和并发任务影响，只能作辅助观测。

## 5. 通用入口

```bash
python3 scripts/repo_gc_gate.py audit <repository> \
  --output /path/to/gc-baseline.json

python3 scripts/repo_gc_gate.py gc <repository> \
  --baseline /path/to/gc-baseline.json \
  --approval /path/to/gc-approval.json \
  --receipt /path/to/gc-receipt.json

python3 scripts/repo_gc_gate.py verify <repository> \
  --baseline /path/to/gc-baseline.json \
  --receipt /path/to/gc-receipt.json

python3 scripts/repo_gc_gate.py release <recovery-directory> \
  --approval /path/to/release-approval.json \
  --receipt /path/to/recovery-release.json
```

`audit` 只读；`gc` 校验 baseline 摘要、授权、fsck 警告确认、HEAD/refs/Worktree 登记未漂移和无新增锁，再执行 GC 并写回 receipt。`verify` 复核当前仓库、对象遍历、refs、Worktree 登记和 fsck。`release` 仅接受 `multi_repo_branch_cleanup.py` 生成的完整恢复目录，核验 prepared/result/operations/checksum 和目标 ref 已不存在，再按单独授权删除。

GC approval 必须包含 `action: "git-gc"`、baseline SHA-256、仍可验证且覆盖当前仓库的 `cleanup_recovery_paths`、`accepted_fsck_warnings`、批准人和授权说明。release approval 必须包含 `action: "release-recovery"`、prepared SHA-256、覆盖全部恢复仓库的 `gc_receipts`、批准人和授权说明。缺失、摘要不匹配或范围扩大即停止。

## 6. 汇报

收口汇报分三段：逻辑清理对象数与保留原因；GC 前后对象库/磁盘账本；恢复目录释放状态。若仍有活跃 index 陈旧元数据、同步器冲突文件或无法验证的仓库，明确列 `NOT_VERIFIED` / `RETAINED_WITH_REASON`，不把 GC 成功扩大为所有历史可恢复或所有仓库健康。
