# 25 — 远程节点 Worker 派发（Remote Node Dispatch，M0：SSH 桥）

版本：v2.30.0（2026-09-29）｜决策：`DEC-2026-09-29-REMOTE-NODE-DISPATCH`｜作者决策：用户 2026-09-29 定稿（SSH 桥 + 节点本机 ORCA；federation 归 M1 实验 lane）

> 编号脚注：references 目录存在两个 `24-` 前缀文件的历史冲突（24-sub2api-quota-producer / 24-zcode-driver-safety），本页顺延取 25，不做历史重命名迁移。

## 0. 一句话

PM 在本机验证 harness 身份后，把 Worker 经 **ssh** 派到远程节点执行：**节点本机的** spawn-worker.sh 原样跑全套门禁（receipt → policy 交集 → quota → mem → lease → worktree → isolation），worker 读**节点自己的** env/key 配置；节点侧 ORCA 自动接管 worktree + terminal 管理。目的：双机双 key 池并发翻倍 + worker 的 CPU/内存落在节点、减轻 PM 本机。

## 1. 为什么是 SSH 桥而不是 ORCA federation（M0）

| 维度 | SSH 桥（M0 采用） | ORCA federation（M1 实验） |
|---|---|---|
| 节点侧门禁 | 节点本机 spawn-worker.sh 全套成立 | `worker-start --on` 不经过本 skill 门禁链 |
| 并发槽语义 | 节点本机 provider lease（fcntl）权威成立 | lease 留在 PM 本机，锁不住节点资源 |
| 结算 | STATUS.json + git push + PR 三证（复用 PR-first 收口） | federation 结算回执有已知缺口（TASK-2026-09-28-ORCA-SETTLEMENT-READBACK：camelCase 适配 + external 终端） |
| PM 管理面 | status/cleanup 子命令 + `orca terminal read/send --environment <节点>` 辅助 | 原生统一，但未验证 |

federation 转正条件：SETTLEMENT-READBACK 关闭 + worker_done 跨机语义实测（见 TASKS M1 卡）。

## 2. 数据流

```
PM 本机                                        远程节点
spawn-worker-remote.sh spawn --node N ...
  1 读 personal config remote_nodes.N
  2 remote-node-probe.py ──ssh──▶ 采集 load/mem/磁盘/git(fetch)/claude/会话数/副本版本/时钟
  3 PM 本机 detect_pm_harness + policy 交集预检（fail fast）
  4 基线门：PM origin/main SHA == 节点 origin/main SHA（fetch 后比对）
  5 一次性 receipt ──rsync──▶ <skill>/config/remote-dispatch-inbox/ (600)
  6 ssh 'zsh -lc "unset ANTHROPIC_*/CLAUDE_CODE_*; spawn-worker.sh
       --remote-dispatch-receipt <inbox>/… --base-ref origin/main
       --branch node-N/<branch> …"'
                                   ──▶ 节点全门禁照常；detect_orca_mode →
                                        节点本机 ORCA 建 worktree + terminal；
                                        worker 读节点自己的 settings json key
  7 PM 落软账 <git-common-dir>/orchestration/remote-dispatches/N/<session>.json
  8 status：ssh cat STATUS.json + 本机 gh pr list --head node-N/<branch>
  9 cleanup：PR/STATUS 终态校验 → 转发节点 pm-cleanup-worker.sh → 删软账
```

provision 子命令（节点首次接入）：路径检查 → clone（PM 的 origin URL）→ skill 随仓库校验 → 节点侧 `orca-register-project.py` 注册 → 复跑 probe。`spawn --provision` 在 probe 报 `REMOTE_NODE_ROOT_MISSING` 时自动补装并重探一次。

## 3. receipt 授权模型（安全论证）

问题：节点侧 `detect_pm_harness` 走 ps 祖先链，ssh 会话祖先是 sshd，无 harness 帧 → fail-closed 拒绝。**这是正确行为，不得削弱**。

方案：authority 从「进程链证据」换成「PM 本机已验证证据的一次性传输」：

- PM 侧 `remote_receipt_issue`：nonce=sha256(urandom 32B)、TTL 默认 300s（受 policy `remote_dispatch.max_ttl_seconds` 上限约束）、绑定 `node + pm_harness + pm_harness_chain + worker_backend + branch + session`。
- 节点侧 `remote_receipt_consume`（spawn-worker.sh `--remote-dispatch-receipt`）：flock 下单文件原子校验（schema/TTL/未消费/字段全匹配）→ 通过即写 `consumed_at_epoch` 并 chmod 400（不可逆）→ 载明的 harness/chain 进入**原版** `enforce_harness_backend_policy_chain` 交集检查。
- **authority 不放大**：不新增 policy host 键；交集函数复用；PM 白名单没有的后端 receipt 一样过不了交集。`remote_dispatch.enabled=false` 节点侧全局禁用。
- 命令身份不进 receipt：`validate_worker_command_backend` 门禁对远程派发同样生效，无需重复绑定。
- 与 `--pm-harness` 互斥（断言不能叠加在 receipt 上二次解释）。
- 重放/伪造面收敛到 inbox 目录写权限（700 目录 + 600 文件 + 一次性消费 + 短 TTL）。

## 4. 退出码契约（probe 与 spawn-worker-remote 一致）

| rc | 语义 | PM 动作 |
|---|---|---|
| 0 | ok | 继续 |
| 3 | precondition_failed：基线冲突 / skill 副本版本不一致 / claude 不可用 / 时钟偏差>120s / enabled=false | 修复后重试（push/pull/对时/`--provision`），修复前节点不接新派发 |
| 4 | capacity_denied：load15 / 活跃会话 / 内存 / 磁盘 | `PARKED_FOR_REMOTE_CAPACITY` 排队重试，**不回落本机**（回落=把过载转回 PM；wave 显式授权除外） |
| 65 | unreachable：ssh 不可达 / 采集崩 | 可回落本机（回落=全新本机 spawn，天然重走全套门禁）；连续 3 轮标记节点 disabled 并报告用户 |
| 75 | PM 软账自限：在途派发数 ≥ `remote_nodes.max_workers` | 等待结算或改派 |
| 64 | usage / fail-closed（receipt 拒绝、配置错） | 修配置，不回落 |

诊断行前缀区分：`PARKED_FOR_REMOTE_CAPACITY`（远程容量）vs `PARKED_FOR_MEMORY`（本机内存，§22）——两者同用 rc=4 但分流判据不同。

## 5. 两层并发（不做分布式锁）

- **硬限制（权威）**：节点本机 `provider-lease.py`，root=节点 `<git-common-dir>/orchestration/provider-leases/`，上限来自**节点的** `orchestration-personal.json`。节点上任何来源的会话同受约束；probe 的「活跃会话计数门」把用户手开会话也算进去，与 lease 取小。
- **软记账（PM 自限）**：PM `<git-common-dir>/orchestration/remote-dispatches/<node>/<session>.json`（schema `multi-agent-orchestration.remote-dispatch.v1`）。只收紧不放宽，不做跨机强一致——漂移最坏后果是多一次 probe 发现节点满 → rc=4 排队，无害。

## 6. 基线同步与隔离

- 强制 `--base-ref origin/main`（spawn-worker-remote 注入，不接受本地 main——节点是独立 clone，本地 main 可能落后）。
- 分支命名 `node-<节点名>/<原分支>`；session 名保持原样（PM 软账保证跨节点唯一）。
- 节点 skill 副本版本必须与 PM 一致（probe 版本门；落后即 rc=3 提示节点 `git pull origin main`）。

## 7. worker 读节点自己的 env（机械保证，非约定）

远程命令显式前置 unset `PROVIDER_ENV_KEYS` 全清单（现场从 `claude-provider-env.sh` 提取，防漂移）；ssh 不转发 env；随后节点侧 `claude-provider-env.sh` 注入**节点本机** `config/*.settings.json` 的 env。METADATA `remote_dispatch.key_source_node` 留痕 key 来源节点。PM 不得把本机 quota summary 路径传给节点（节点读自己的 personal config，其 `quota_aware_routing` 通常为 false 走静态路由）。

## 8. PATH 注意（ssh 非交互环境）

非交互 ssh 无登录 PATH：`claude`、`orca` 可能不在 PATH。规则：**远端命令一律 `zsh -lc` 包裹**（probe 对 `command -v claude` 的校验也在登录 shell 下做）；节点侧 spawn-worker.sh 的 orca CLI 解析自带 app-bundle 兜底。

## 9. PM 管理面

- 状态：`status` 子命令（ssh cat STATUS.json + gh pr list）｜`orca terminal read --environment <节点>` 实时读远程 worker 终端（可选辅助）｜GitHub PR 共享事实。
- 干预：`orca terminal send --environment <节点>` 向远程 worker 终端送追加指令（与本机 terminal send 同机制）。
- 收口：`cleanup` 子命令——前置（PR MERGED/CLOSED 或 STATUS 终态，否则要求 `--force-with-reason`）→ ssh 转发节点 `pm-cleanup-worker.sh`（dry-run → --execute，幂等）→ 删 PM 软账。
- 断线韧性：worker 常驻节点 ORCA terminal/tmux，PM ssh 中断不影响；恢复=凭软账重挂 status。

## 10. M0 已验证 / NOT_VERIFIED

已验证（mock + 本机 fixture）：receipt 六路径（issue/consume/重放/过期/不匹配/TTL 上限）、probe 十路径（ok/不可达/未配置/禁用/load/会话/基线/版本/缺 root/真实 fetch）、spawn-worker-remote 廿五断言（含 receipt 传输、远端命令构造、unset 前缀、软账生命周期、cleanup 前置、provision 转发）；四个既有回归全绿；skill-lint security 0 critical/0 high；HFA 仅剩 1 条 origin/main 既有项。

NOT_VERIFIED（等真机验收，见 TASKS M0 卡 checklist）：真实节点端到端（真 ssh + 节点本机 spawn + ORCA worktree/terminal + PR 回流 + lease 释放）、supervised 模式跑在远程（worker_done/Delivery 跨机不依赖也不承诺）、远程 429 自动恢复（M2）。

## 11. 配置参考

节点声明在 gitignored `config/orchestration-personal.json` 的 `remote_nodes` 段（模板见 `orchestration-personal.example.json`）：`enabled / ssh_alias / remote_root / skill_root / max_workers / load_threshold / active_session_cap / min_free_disk_gb / min_free_memory_percent / allowed_backends / connect_timeout_seconds`。公开仓只放占位符；真实节点名/别名/路径只进本地 gitignored 文件。

## 12. 分期

M0（本页）：单节点 SSH 桥全链。M1：多节点 fleet 视图（`pm-orchestrate fleet`）、ORCA federation 实验 lane（前置=SETTLEMENT-READBACK 关闭）。M2：远程 429 恢复、双 key 池统一选路（quota_aware_routing 集成远程 lane）、远程 sentinel、自动回落。
