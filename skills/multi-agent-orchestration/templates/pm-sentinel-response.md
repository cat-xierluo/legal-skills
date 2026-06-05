# PM 收到 Sentinel Task-Notification 后的标准响应

> 适用：当 PM 收到 `run_in_background=true` 启的 `sentinel.sh` exit 后的
> harness task-notification。Sentinel exit code 与语义：
>
> | Exit | 含义 | 触发原因 |
> |------|------|----------|
> | 0 | done | 工人写了 `STATUS.json.status=done`（或 RESULT.md/PATCH_SUMMARY.md 也写好）|
> | 2 | failed/blocked/stopped | 工人写终态但非 done；PM 需要读 STATUS.issues / blocker 决定下一步 |
> | 124 | timeout | Sentinel 等到 `--max-wait` 还没看到终态；工人可能卡死或 sentinel 启动太晚 |
> | 64 | usage error | Sentinel 自身参数错（PM 调用错误）|

## 1. 第一步：解析 task-notification

收到 notification 后立即：

1. 用 `Read` 工具读 sentinel 输出文件：`{session_context}/SENTINEL_OUT.log`
2. 解析 exit code：
   ```bash
   # 这段是 PM 自己的 turn 内联的，不调外部脚本
   SENTINEL_LOG={session_context}/SENTINEL_OUT.log
   STATUS_FILE={session_context}/STATUS.json
   tail -5 "$SENTINEL_LOG"
   ```
3. 读 `STATUS.json` 当前完整内容（不止 status 字段，也看 phase / current_action / next_action / git.last_commit_sha / git.commits_since_base）。

## 2. 按 exit code 分支处理

### 2.1 Exit 0（done）

工人完成。标准动作：

1. 读 `RESULT.md` 和 `PATCH_SUMMARY.md`（如果存在），获取工人自述的 Summary / Validation / Risks。
2. **范围检查**（防 worker scope 扩大，遵循 §8 收口标准）：
   ```bash
   git -C {worktree} diff --stat {base_ref}...HEAD
   git -C {worktree} log --oneline {base_ref}..HEAD
   ```
   确认改动只覆盖声明范围。如果超出，按 §8 review correction 流程给工人发纠偏，不直接接管实现。
3. 验证：跑 `METADATA.json` 里的 `verification.commands[]`：
   ```bash
   cd {worktree} && <verify-cmd>
   ```
4. 跑完后，按 `git-workflow` §8.1 收口标准：提 PR → 等 CI → 复核 → 合并。
5. 合并后用 `clean-worktree.sh --execute` 清理。

### 2.2 Exit 2（failed/blocked/stopped）

工人主动报告非 done 终态。标准动作：

1. 读 `STATUS.json.issues[]` 和 `STATUS.json.blocker`，确定失败/阻塞原因。
2. 决策：
   - **可恢复失败**（代码 review 发现问题、verify 失败）：用 tmux 给原 worker 发 review correction，让 worker 修。**不要 PM 直接接管实现**。
   - **needs_input = true**：`STATUS.json.needs_input` 是 true 时，PM 必须显式回应（重新设计 prompt、降范围、撤回 worker、问用户）。
   - **stopped**（PM 之前下令停的）：按 `git-workflow` 收口；如果不需要保留改动就 `clean-worktree.sh`。
3. 重启/降级：如果工人反复失败且范围收窄无望，按 §8.1 升级为"派 reviewer 或 PM 窄范围收口"。

### 2.3 Exit 124（timeout）

Sentinel 自身正常但没等到终态。两种可能：

1. **工人卡死**（最大可能）：tmux 还在但没写 STATUS.json
2. **工人写 STATUS 太慢**：sentinel 启动太晚或工人还在 bootstrap
3. **工人已退出但没写终态**：sentinel 没赶上，tmux 已无 session

诊断步骤：
```bash
# 工人 tmux 还活着吗？
tmux has-session -t {session}  # true = 还在；false = 已退出

# STATUS.json 是什么状态？
cat {session_context}/STATUS.json  # 看 status / updated_at

# 距离最近 STATUS 更新多久了？
# (current_epoch - updated_at_epoch) > 600s → 10 分钟没动 = 大概率卡死
```

决策：
- **tmux 还在 + STATUS 长时间没更新**（> 15 分钟）：用 tmux 截屏看 pane（参考 `tmux capture-pane`），判断工人是否在 idle / 死循环 / 等用户。优先发"刷新 STATUS 或提交当前阶段"纠偏（按 §7 介入规则）。5 分钟内无响应则升级。
- **tmux 还在 + STATUS 正常推进**：sentinel 可能启动得太早或 worker 启动晚。**保留 sentinel**（已退出），新启一个 sentinel 继续等。
- **tmux 已退出 + STATUS 没写终态**：sentinel 缺失覆盖，PM 必须用 `pm-monitor.sh --once` 拉一次状态补齐。后续是否补启 sentinel 由 PM 决定。

### 2.4 Exit 64（usage error）

PM 自己的脚本调用错误。检查：
- `--status-file` 和 `--tmux-session` 是否传对（必须和 `spawn-worker.sh --session` 一致）
- `--max-wait` 数字是否合法

重写调用并重新启 sentinel。

## 3. 范围检查（适用于所有非 usage error 情况）

不管 exit code 是什么，收口前都必须做一次范围检查，避免 worker 越权改文件：

```bash
# 列出本次任务的 allowed/forbidden files
jq -r '.scope.allowed_files[], .scope.forbidden_files[]' {session_context}/STATUS.json

# 实际改动
git -C {worktree} diff --name-only {base_ref}...HEAD

# 对比
diff <(jq -r '.scope.allowed_files[]' {session_context}/STATUS.json | sort) \
     <(git -C {worktree} diff --name-only {base_ref}...HEAD | sort)
```

越权文件需要：
1. 让 worker 撤回该文件（如果还在 worktree）
2. 评估该改动是否真的需要 → 升级为新 worker / 新任务，或接受为 DEC 留痕
3. 绝对不要 PM 自己改业务代码（除非 §2.1 PM 代理纪律明确允许的窄范围收口）

## 4. Sentinel 缺失 / 失败的降级

如果 sentinel 没启起来（auto mode 拒了 background 调用 / sentinel 进程被 SIGKILL / sentinel sh 写错），PM 回到旧行为：

- 单 worker：用 `wait-worker.sh --once` 手动查状态
- 多 worker：起 `pm-monitor.sh --log-file` 在独立 background process 持续写事件日志，PM 在每个 turn 末尾 `tail -50` 看

判断"sentinel 是否被拒"的特征：
- 启 sentinel 后 5 秒内没收到任何 sentinel 日志（`SENTINEL_START` 都没）
- 工人实际跑到 done 了，PM 没被 re-invoke

降级是 graceful 的，**不是失败**：原 Wave 4-5 行为就是这样工作的。
