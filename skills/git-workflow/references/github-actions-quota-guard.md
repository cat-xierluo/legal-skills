# GitHub Actions 额度治理（停挂止血）

> 2026-09-15 实战定谳：账号级分钟额度耗尽（4 仓 7 workflow、单月 500+ 次自动触发）。
> 原则：**能在本地跑的检查不烧云分钟**；发布/签名/跨平台构建保留云跑。
> 本 reference 承载诊断、停挂、恢复与红线；[主入口](../SKILL.md#场景路由)按场景加载本页。

CI 治理与发版分开：日常停挂/恢复在本页；发版时读取 release-workflow 的发布门禁与 CI 故障流程。停挂会改变检查触发与权限，须核当前任务授权、required checks 和依赖调用，不因可本地执行自动取消必要 CI。

## 1. 诊断：谁在烧分钟

- 先核账户套餐、仓库可见性、runner 类型与存储用量；不要仅凭“公共仓”或旧费率推断费用。按现行[GitHub Actions 计费文档](https://docs.github.com/en/billing/concepts/product-billing/github-actions)，公共仓标准托管 runner 与 self-hosted 使用免费；larger runner 不享公共仓免费和套餐分钟抵扣，artifact/cache 存储另核。
- 旧 self-hosted 平台费计划已[宣布延期](https://github.com/resources/insights/2026-pricing-changes-for-github-actions)，不将 2025 年预告当成已生效费率。执行治理时重新核官方文档与账户实际账单。
- 账户用量通过当前 Billing and licensing 界面或受支持的 usage API 查询；旧 `/settings/billing/actions` 产品 API 已[退役](https://github.blog/changelog/2025-09-26-product-specific-billing-apis-are-closing-down/)，不能读不到便判用量为零。费用和权限缺失明确标未验。
- 逐仓近 N 天触发计数：

```bash
gh api "repos/<owner>/<repo>/actions/runs?created=>YYYY-MM-DD&per_page=100" > /tmp/gha/<repo>.json
# 逐仓落盘后用 Python 统计 (workflow name × event)；API 每页 100 上限，计满即真实更多
```

- 双计费形态识别：`on: push` 与 `on: pull_request` 同时开启 → 每次分支更新跑两遍，
  是最常见的浪费源。
- 壳层陷阱（两次实锤）：JSON 经 shell 变量转手会被控制字符破坏（`Invalid control character`）
  ——一律落盘文件再 严格 JSON 解析，或 `gh --jq` 内联统计；
  退出码在管道/for 循环里抓不到——单独一条命令取 `$?`。

## 2. 停挂配方（park）

1. **分类**：逐 workflow 判断——lint / unittest / py_compile / npm test / build 均可本地等价
   执行 → 停挂；release / deploy / 签名公证 / Windows 跨平台 → 保留。
2. **改写 `on:` 块**：保留 `workflow_dispatch:`；若被复用（如 `release.yml` 里
   `uses: ./.github/workflows/ci.yml`）则同时保留 `workflow_call:`，否则发布链断裂。
   原 `on:` 块整体注释保留在下方，并在注释里写明**本地等价命令**（从各 job 的 `run:` 步骤
   提取），形如：

```yaml
on:
  # ── <日期> 停挂（账号级 GitHub Actions 私有仓分钟额度耗尽）：本工作流改为仅手动触发，
  # 不再随 push / pull_request 自动运行。检查内容均可在本地等价执行——按本文件各 job 的
  # run: 步骤在仓根依次运行，例如：
  #   python3 -m unittest discover -s tests -t . -v
  # 恢复自动触发：删除本注释块并还原下方被注释的原 on: 触发器。
  # 原触发器：
  #   on:
  #     push:
  #       branches: [main]
  workflow_dispatch:
```

3. **走 PR 合并**：按[PR 合同](pr-workflow.md)核 diff、review 和最终 checks。改写不证明当次运行免计费；检查实际 event/base 工作流、既有运行与仓库保护，合并后核真实触发面。
4. **脚本要点**：macOS 自带 bash 3.2 无 `declare -A`（用 case）；zsh 不切词（多文件参数
   逐个传，勿拼接变量）；改完用项目已有 YAML 校验器按工作流语义核 `on` keys（避免 YAML 1.1 将 on 读成布尔值）再提交；缺工具不自动安装。
5. **验证**：合并后逐文件 `gh api repos/<o>/<r>/contents/.github/workflows/<f> --jq .content
   | base64 -d` 复核远端 `on:` 只剩 workflow_dispatch（/ workflow_call）。

## 3. 强化与替代

- **仓级总闸**（立即止血、可逆、但不体现在 git 里）：
  `gh api -X PUT repos/<owner>/<repo>/actions/permissions -F enabled=false`；
  适合"纯个人仓 + 全部检查可本地跑"的一刀切，恢复使用同一入口 `-F enabled=true`，两次均读取实际 permissions 后验，不把请求成功等同已生效。
- 降低触发面：`paths:` 过滤只盯相关目录；`concurrency: group+cancel-in-progress` 取消
  旧跑；PR 只保留 `pull_request` 或只保留 `push`（单边，消双计费）。
- 自托管 runner 不计分钟（有闲置机器时可换）。

## 4. 红线与事故备忘

- 不停 release/deploy/签名及必要 required checks；公共仓是否需治理取决于 runner/存储实际费用，不一律停挂。改协作仓前核 owner 和授权。
- 停挂 PR 的 body/commit 必须写明恢复方法（文件内注释即恢复手册）。
- **网络抖动事故**（2026-09-15 实锤）：`gh pr merge` 被 TLS 超时打断而清理链未以"合并
  确认"为门禁就删分支 → PR 因 head 删除被自动 CLOSED。恢复：`git branch <name> <sha>`
  （提交对象仍在本地）→ push → `gh pr reopen`。清理分支前必须确认
  `gh api .../pulls/<n> --jq '.merged' == true`。
