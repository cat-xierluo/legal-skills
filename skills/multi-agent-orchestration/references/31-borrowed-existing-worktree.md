# 显式借用预建工作树首次接入

## 授权与适用边界

只在原工作树唯一 owner 已授权、原 writer 已结束且现场证明空闲时，首次接入已有 long-lived Git 工作树。保持原分支、路径、基线和已批准的脏资产，不创建第二工作树或 writer。入口仅支持 `zcode-cli` 的原生 Orca supervised 新 Session；已经存在 MAO Session 的任务仍走原恢复合同。

不传显式借用合同时，普通派发继续拒绝已占用 branch/path。`--worktree`、`--branch-lifecycle long-lived`、repo 注册或没有旧 METADATA 均不构成借用授权。不能伪造旧 authority/Dispatch，不能通过 raw terminal 创建绕过完整派发门。

`approved_by` 记录原 owner 的明确授权来源，并须与本次 `--allow-prompt-only-install-guard` 来源及冻结 authority receipt 的 `degradation_source` 精确一致；它不自动认证真人身份，也不能替代原任务的材料、写范围、账号、预算和完成授权。PM 必须回读原任务与授权，检查当前 owner；不能仅填一个非空字符串就认定已获同意。

## 现场合同

用当前 runtime 官方 inventory 取得精确 Orca worktree ID，运行只读 snapshot 生成短时合同。项目注册只沿既有受控入口，不推断 Orca 有 import/reuse 参数。依赖 Python 标准库、Git、匹配版本 Orca、可完整读取进程的 `ps` 与 `lsof`；缺工具、IPC或进程访问权限时停止，不安装或重启。

合同 schema 为 `multi-agent-orchestration.borrowed-worktree.v1`，绑定 canonical `project/common_dir/worktree`、精确 `branch/head`、内容及模式快照 `dirty_sha256`、`orca_worktree_id/runtime_id`、`approved_by` 与短时 `created_at`。不能手填 HEAD/摘要来掩盖漂移；每次失败后重新确认原 writer 和授权，不据陈旧合同重试。

先生成合同（先以 `umask 077` 设置私有文件模式，输出放在工作树外），不手工拼接摘要：

```bash
python3 "$MAO/scripts/borrowed-worktree.py" snapshot \
  --project "$APPROVED_PROJECT" --worktree "$APPROVED_WORKTREE" \
  --branch "$EXACT_BRANCH" --orca-bin "$ORCA_BIN" \
  --orca-worktree-id "$EXACT_ORCA_WORKTREE_ID" \
  --runtime-id "$CURRENT_RUNTIME_ID" --approved-by "$OWNER_AUTHORIZATION" \
  > "$PRIVATE_CONTRACT_FILE"
```

上述变量全部来自本轮批准任务、精确 Git/Orca inventory 和原 owner 授权。若有未被精确覆盖的 ignored 原资产，入口拒绝，不读取忽略的凭证内容、不当作干净空树；该情形不能直接消费本入口，应保留材料并补充明确资产覆盖合同后另行验收。不能为了通过此门删除原材料。

在完整已批准 spawn 参数中额外传：

```text
--borrow-existing-worktree /private/task/borrow-contract.json
--branch-lifecycle long-lived
--worker-backend zcode-cli --orca-supervised
--orca-zcode-native-requests /private/launch-requests
```

继续提供原生启动、真实 PM harness、scope、验证合同、provider/账号、额度/内存和 coordinator/runtime 等既有参数。借用入口建立真实的新 Session、authority、lease 与 Dispatch，不伪造历史连续性。

## 失败与保留

派发前复核 Git/Orca 身份、HEAD、已批准的 tracked/index/untracked 内容和模式、进程与终端库存，取得独占借用锁；在创建 Context/provider/Task 前持久化借用保护账本。原生 request prepare 与实际执行前再次检查，身份或内容漂移、锁冲突、活跃或未知 writer 均拒绝。不把 Orca 列表中没有终端当作本机没有独立 CLI writer。独占锁约束合作的编排入口，现场进程/终端检查和晚期复核不能提供任意非合作外部进程的机械写入沙箱。

只有初始已证不存在、本轮唯一创建的 Session 中三个直接 regular 文件 `METADATA.json`、`INSTALL_AUTHORIZATION.json`、`launch.sh` 可按精确范围排除启动前快照；Session 及祖先符号链接、额外文件/目录不能借此排除，其余原资产不能通过忽略整目录来逃过检查。该启动前门位于冻结 launch 的实际 exec 前；业务启动后的 bind 复核 receipt/身份/effects/authority，不把合法业务写入或 STATUS/RESULT 当作启动前快照漂移。失败时保留原树、原分支和原材料，仅按精确 owner/生命周期结算本轮自建资源；借用账本不随 release 删除，也不能把参数降为 ephemeral 取得删除权限。

MAO 的账本只保护读取它的编排清理路径。原生 Orca settlement 必须根据实际 resource/effects 和正式 retain/release 合同另外核对，不能以账本或新终端 created 推断原工作树可删。未知归属或生命周期保留并报告，完整真机行为以 TASKS 当前证据为准。

## 验收边界

隔离 Git/fake-CLI 用例证明准入、错误路径、并发和借用资源保留；不代表原业务工作树已可接入或模型已完成任务。真实消费者只有原唯一 owner 重新证实无 writer 后才可使用。原生启动与结算、未实际运行的账号/模型路径分别标记 `NOT_VERIFIED`，不继承新建工作树的成功结论。
