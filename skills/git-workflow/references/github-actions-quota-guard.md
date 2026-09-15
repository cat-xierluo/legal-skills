# GitHub Actions 额度治理（停挂止血）

> 2026-09-15 实战定谳：账号级分钟额度耗尽（4 仓 7 workflow、单月 500+ 次自动触发）。
> 原则：**能在本地跑的检查不烧云分钟**；发布/签名/跨平台构建保留云跑。
> 本 reference 承载诊断、停挂、恢复与红线；SKILL.md §11 是最短入口。

## 1. 诊断：谁在烧分钟

- 额度是**账号级**：公共仓 Actions 免费，只有私有仓计费（Linux 1x / Windows 2x / macOS 10x 倍率）。
  排查时先过滤掉公共仓，别浪费精力停挂免费流量。
- 账号用量：`gh api /users/<owner>/settings/billing/actions`
  （`total_minutes_used` / `included_minutes` / `included_quantity`）。
- 逐仓近 N 天触发计数：

```bash
gh api "repos/<owner>/<repo>/actions/runs?created=>YYYY-MM-DD&per_page=100" > /tmp/gha/<repo>.json
# 逐仓落盘后用 Python 统计 (workflow name × event)；API 每页 100 上限，计满即真实更多
```

- 双计费形态识别：`on: push` 与 `on: pull_request` 同时开启 → 每次分支更新跑两遍，
  是最常见的浪费源。
- 壳层陷阱（两次实锤）：JSON 经 shell 变量转手会被控制字符破坏（`Invalid control character`）
  ——一律落盘文件再 `json.loads(..., strict=False)`，或 `gh --jq` 内联统计；
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

3. **走 PR 合并**：停挂版 PR 分支上已无 `pull_request` 触发器 → 本次 PR 本身不再计费；
   合并进默认分支后 push 触发同步消失。
4. **脚本要点**：macOS 自带 bash 3.2 无 `declare -A`（用 case）；zsh 不切词（多文件参数
   逐个传，勿拼接变量）；改完用 PyYAML 校验 `on` keys 再提交。
5. **验证**：合并后逐文件 `gh api repos/<o>/<r>/contents/.github/workflows/<f> --jq .content
   | base64 -d` 复核远端 `on:` 只剩 workflow_dispatch（/ workflow_call）。

## 3. 强化与替代

- **仓级总闸**（立即止血、可逆、但不体现在 git 里）：
  `gh api -X PUT repos/<owner>/<repo>/actions/permissions -f enabled=false`；
  适合"纯个人仓 + 全部检查可本地跑"的一刀切，恢复改 `enabled=true`。
- 降低触发面：`paths:` 过滤只盯相关目录；`concurrency: group+cancel-in-progress` 取消
  旧跑；PR 只保留 `pull_request` 或只保留 `push`（单边，消双计费）。
- 自托管 runner 不计分钟（有闲置机器时可换）。

## 4. 红线与事故备忘

- 不停 release/deploy/签名类；公共仓不用停（免费）；改协作仓前先确认 owner。
- 停挂 PR 的 body/commit 必须写明恢复方法（文件内注释即恢复手册）。
- **网络抖动事故**（2026-09-15 实锤）：`gh pr merge` 被 TLS 超时打断而清理链未以"合并
  确认"为门禁就删分支 → PR 因 head 删除被自动 CLOSED。恢复：`git branch <name> <sha>`
  （提交对象仍在本地）→ push → `gh pr reopen`。清理分支前必须确认
  `gh api .../pulls/<n> --jq '.merged' == true`。
