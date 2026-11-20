# 多仓分支批量清理

当 Codex/Agent 在多个仓库沉淀大量一次性分支时，先按单仓生命周期合同判定，再使用同一份冻结清单、恢复包和后验回执执行。多仓只改变对象数量，不降低授权与证据门禁。

## 1. 范围与输入

先确定允许盘点的仓库来源，例如用户指定目录、既有项目列表或此前任务登记。不要为了“多仓”无限扫描用户磁盘；仓库路径、远端、默认分支和任务归属必须来自本轮授权或可复核记录。

每个仓库先读取项目规则、`git status`、`git worktree list`、本地/远端 refs 和完整开放 PR。该阶段只读，不 fetch/prune/remove。单仓日常入口仍是 `branch-audit.sh` 与 `worktree-audit.sh`；多仓流程只是汇总和统一收口，不绕过单仓证据。

## 2. 候选与证据分级

候选表至少包含仓库、根目录、分支、40 位 tip、声明基线/OID、证据类型、远端同名 tip、开放 PR、最后提交/本地 reflog 时间、检出 Worktree、生命周期和判定。默认 24 小时内有提交或 reflog 写入即保留。

只有下列证据可进入“确定安全”组：

1. `ancestor`：当前 tip 是冻结基线的祖先。
2. `merged-pr`：同仓、同 head 名、同 head OID、同 base 的 PR 已 `MERGED`，且 merge commit 是冻结基线祖先；squash/rebase 的不可达 tip 必须绑定这份证据。
3. `cached-remote`：无权威远端查询时，仅当用户明确接受“本机缓存远端 main”边界，且当前 tip 是该缓存 OID 的祖先。

树内容等价、patch-id、同 tip 别名、同名旧 PR、日期和分支名都只能形成待确认组，不能混入确定安全组。CLOSED、无 PR、有未推送提交、有 Worktree、活跃/未知、长期线或 integration target 一律保留。

GitHub 查询必须完整分页。主干前进时可接受“冻结基线仍是当前 main 祖先”；历史分叉、查询截断、TLS/权限失败使该仓库本轮退出，不用旧结果补判。

## 3. 报告与授权

生成机器可读候选清单和人类可读报告。报告按确定安全、内容等价、同 tip 别名、仅本地/无权威基准、仍绑定 Worktree 分组，并给出未纳入原因。用户确认必须绑定清单 SHA-256 和实际范围；“继续清理”“可以清掉”不能扩展到报告外分支、远端 refs 或现存 Worktree。

候选清单 schema：

```json
{
  "schema_version": 1,
  "repositories": [
    {
      "name": "fixture",
      "root": "/absolute/repository/path",
      "remote_repo": "owner/repository",
      "base_ref": "refs/remotes/origin/main",
      "base_oid": "40-digit-frozen-base",
      "pr_check": "github",
      "branches": [
        {
          "branch": "docs/delivered",
          "tip": "40-digit-branch-tip",
          "evidence": {
            "kind": "ancestor",
            "baseline_oid": "40-digit-frozen-base"
          }
        }
      ]
    }
  ]
}
```

`evidence.kind` 支持 `ancestor`、`merged-pr` 和 `cached-remote`。`merged-pr` 还必须提供 `pr`、与分支 tip 完全一致的 `head_oid`、`base_ref_name` 和 `merge_oid`；脚本会用 `gh pr view` 复查 `MERGED`、head/base/OID 与 merge commit。`pr_check` 为 `github` 时执行前用 `gh pr list` 重查开放 PR；无权威远端 PR 的仓库使用 `none`，并把该边界写入报告和授权。

`base_ref` 必须是完整 Git ref。`pr_check` 为 `github` 时必须提供 `remote_repo`，所有 `gh` 查询显式 `-R` 绑定该仓库，不依赖当前目录的远端推断。

## 4. 备份与执行

使用通用入口：

```bash
python3 scripts/multi_repo_branch_cleanup.py prepare \
  candidates.json /path/to/recovery --quiet-seconds 86400

python3 scripts/multi_repo_branch_cleanup.py apply \
  /path/to/recovery --approval approval.json

python3 scripts/multi_repo_branch_cleanup.py verify /path/to/recovery
```

`prepare` 逐仓复核基线、tip、reflog 活跃期、分支配置、Worktree 检出、开放 PR 和证据；保存 reflog、不可达 commit pack、manifest SHA-256 和恢复文件校验。若仓库是 partial clone 且 pack 因缺失对象失败，默认保留现场；只有在用户明确允许读远端补对象时加 `--fetch-missing`，不得借此顺手 fetch/prune 其他引用。

`apply` 需要单独的 approval JSON，其中 `manifest_sha256` 必须等于清单摘要，且有非空 `approved_by` 与授权说明。执行仍逐条重核后使用：

```bash
git update-ref --no-deref -d refs/heads/<branch> <expected-tip>
```

禁止 `git branch -D`、无 expected-tip 批量删除、远端删除和 Worktree 删除。单对象漂移只保留该对象；脚本可继续处理其他独立仓库，但最终报告必须列出全部 retained 原因。

## 5. 后验与收口

执行后运行 `verify`，核对回执、恢复 checksum、目标 ref 不存在、操作集合等于 prepared 集合。向用户报告删除数/仓库分布、跳过与原因、恢复目录、未触碰范围（远端分支、现存 Worktree、dirty/untracked 材料）以及 GitHub 查询失败等未验证边界。

恢复目录应保留在仓外并设置 `0700`。清理成功不触发 GC；对象是否回收按仓库膨胀合同另行评估和授权。
