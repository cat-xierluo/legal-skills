# Git 隐私预检：检查真实提交与发布对象

## 依赖和职责

- `privacy_check.py` 仅依赖 Python 3.10+ 标准库和 Git；`safe-pr.py` 另需已认证的 GitHub CLI。
- `git-batch-commit` 通过同级 `git-workflow/scripts/privacy_check.py` 复用规则。单独安装 batch 技能时须同时安装同级 workflow 技能；缺失即停止，不回退到无检查提交。
- 这是一组本地工作流门禁，不是服务端安全策略；不安装 hook、不修改 `core.hooksPath`、账号权限或 Git 身份。既有身份、授权、review、CI 门禁仍需满足。
- 模式匹配只能发现已覆盖的结构与本地黑名单，不能判断所有人名、客户关系、案情组合或其他敏感语义；仍须人工检查公开内容。

## 检查时点与对象

| 时点 | 被检查对象 | 绑定方式 |
|---|---|---|
| batch commit | 全部分组最终完整说明（含 Markdown 提取和 `--local-ref`），全部变更路径、暂存 blob、完整 staged patch | 全部通过才预览/提交；原 index 的 tree 快照；临时 index 逐组提交；不重新 add 工作区 |
| pre-commit / commit-msg | staged 内容 / Git 传入的完整说明文件 | 仓库已启用 hook 时复用共享 checker；本次不自动启用 |
| safe-push | 最新 integration base 到待推送 HEAD 的每笔 message、patch、变更 blob | fetch 明确 base ref；固定 base/head OID；身份和隐私核验同一对象；push 使用该 head OID |
| 创建 PR | 已推送完整范围，最终标题、正文 | 文件只读一次，原字符串传给 gh；默认 draft；提交后复核 PR head、base、文本 |
| squash | 完整 PR 范围、当前 PR 标题正文、最终 squash 标题正文 | 明确 final text，不使用自动拼接；`--match-head-commit` 绑定核验的 head |

范围为空、缺少 revision/object、浅克隆、无祖先关系、graft、读失败或子模块均停止。非 UTF-8/二进制必须有独立格式审查凭据，否则停止。不会将这些情况当作“没有发现”。可读 patch 检查包含删除行，因此清理当前文件不能掩盖中间提交。二进制材料须先完成下述格式审查，当前脚本不提供跳过开关。

批量提交要求已有 HEAD；首次建库先完成经审查的初始化提交。预检失败不创建任何提交；执行期 hook 或 Git 失败则立即停止。已经成功的本地提交保留，不自动重写/回滚；原暂存快照与工作区保留。外部 hook 若改变提交树或说明，会在提交后检测并阻止继续，不得发布该提交。

## 推送与 PR 使用

从仓库根运行（技能安装在别处时调整脚本路径）：

```bash
bash skills/git-workflow/scripts/safe-push.sh \
  --base origin/main --remote origin --branch feat/example \
  --expected-name '<已确认作者>' --expected-email '<已确认邮箱>'

# final-title.txt 必须单行；正文必须明确写入文件，不能让 gh 自动汇总历史
python3 skills/git-workflow/scripts/safe-pr.py create \
  --base main --head feat/example --expected-head "$(git rev-parse HEAD)" \
  --title-file final-title.txt --body-file final-body.md

# 仅在用户已授权合并、review 和 CI 都通过后；标题含 (#PR编号)
python3 skills/git-workflow/scripts/safe-pr.py squash --number 227 \
  --expected-head '<完整已审核 head OID>' \
  --title-file squash-title.txt --body-file squash-body.md
```

准备文本文件时优先放在 Git 目录或仓库外，避免误暂存。`safe-pr.py --repo PATH --remote NAME` 可指定本地检出与远端；PR 的 GitHub 目标由该 remote URL 规范化为 `HOST/OWNER/REPO`（支持 HTTPS、`git@HOST:OWNER/REPO.git` 和 `ssh://git@HOST/OWNER/REPO.git`），不把 URL 内凭据传给 gh，避免默认仓库漂移。本地路径或无法核对的远端格式停止。

创建 PR 的 GitHub API 没有原子 head-OID 条件参数：helper 在发送前后均核对，但并行写同一远端分支仍有极短竞态窗口。使用独占 feature 分支；若后验失败，先查看已创建 PR，不得盲目再次创建。squash 使用服务端 head 条件，仍需事后查看 mergedAt / mergeCommit；本地成功退出不替代合并结果核对。网络失败可能已经产生远端效果，不自动重试。

直接使用 GitHub connector/API 时也必须检查同一组完整文本与准确提交范围，并将已检查的字符串/OID原样作为 API 参数；不得改成自动生成正文或只检查净 diff。普通 `git push`、`gh pr create --fill` 与自动 squash message 均不替代此流程。

## 待核对项与精确例外

手机号、身份证、座机、本机用户目录、法院案号、私钥标记与本地黑名单都会产生阻断式待核对项。案号命中不等于认定隐私泄露；公开裁判和虚构夹具在人工确认后可精确放行。普通 `(#227)` / `Refs #13` 与含 `XXXX` 的案号占位符不会仅因数字被拦截。

本地策略放在 `git rev-parse --git-common-dir` 指向的 Git 目录：

- `privacy-denylist`：每行一个需拦截的精确词，空行及 `#` 注释忽略。已有 `.githooks/local-denylist` 可兼容读取，但该文件一旦被跟踪或出现在待发布变更中立即停止。永远不要将真实黑名单提交到仓库、PR 或公开日志。
- `privacy-reviewed.json`：本地 JSON 数组，默认不存在；禁止目录忽略和通配例外。

每条审查记录必须包含以下所有字段：

```json
[
  {
    "rule": "case-number",
    "source_sha256": "<诊断中的 64 位 source_sha256>",
    "content_sha256": "<诊断中的 64 位 content_sha256>",
    "kind": "public-judgment",
    "reason": "<为何可公开；须人工核对>",
    "reviewed_by": "<实际审查者>",
    "evidence": "https://<确切公开裁判来源>"
  }
]
```

这是格式模板，不是可直接使用的授权。公开裁判例外仅适用于 `case-number`，必须附 HTTPS 来源；`synthetic` 例外必须记录虚构依据。脚本只验证记录结构与内容绑定，不会联网判定来源真实性，也不会自动生成或批准例外。`local-denylist` 不能被例外放行。

### 二进制与非 UTF-8 材料的人工审查路径

图片先查看实际像素，PDF/Office 文件须用对应格式的提取和渲染工具检查正文、批注、元数据及嵌入内容；非 UTF-8 文本先按确认的编码完整解码检查。仅看文件名、缩略图或文本提取失败不能批准。将具体审查结果保存为本地独立审查产物并计算 SHA-256。

记录仍用上述七字段，但限定 `rule: "binary-content"`、`kind: "reviewed-binary"`，`source_sha256` 与 `content_sha256` 取失败诊断（后者是原始字节 SHA-256）；`evidence` 必须为 `sha256:<独立审查产物的64位摘要>`，reason 说明格式、工具及审查范围，reviewed_by 写实际审查者。脚本不代替审查，不自动写凭据；凭据是审查者声明，不是真实性的密码学证明。换路径或任一字节改变都重新检查；原始字节无法读取时不接受任何例外。

例外绑定“规则 + 来源字符串摘要 + 完整内容摘要”。同案号换文件、正文多一个字、增加另一个敏感字段，都须重审。patch、blob、message 是不同上下文，不能以某个文件的审查记录自动放行提交说明。commit OID 改变时历史记录也需重审。

诊断仅输出规则、行号、两个摘要，不打印原文、文件名或黑名单词。定位来源时可本地计算下列来源字符串的 SHA-256 与诊断比对：`blob:<仓库相对路径>`、`path:<仓库相对路径>`、`staged-patch`、`commit:<完整OID>:message`、`commit:<完整OID>:patch`、`commit-message:<从1开始的排序分组号>`、hook 的 `commit-message`、`create:title/body`、`squash:title/body`、当前 PR 的 `pr:title/body`（title/body 表示两个独立字符串）。

## 回归验证

```bash
python3 -m unittest discover -s skills/git-workflow/scripts -p test_privacy_check.py -v
bash skills/git-workflow/scripts/test-check-outgoing-identities.sh
bash skills/git-workflow/scripts/test-identity-audit.sh
```

测试使用隔离临时仓库、运行时构造的虚构数据和假 gh，不连接真实案件，不执行真实 PR 合并。覆盖 message-only、先写后删、所有分组预检、`--yes`、Markdown/local-ref、部分暂存、PR/squash 文本、历史读失败、精确放行和普通 PR 编号。
