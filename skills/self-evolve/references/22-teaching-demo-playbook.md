# 现场演示脚本：三个场景

配合 [21-teaching-demo.md](21-teaching-demo.md) 讲义使用。所有数据来自 `scripts/teaching_demo.py` 生成的合成会话，不含真实业务材料。默认退出时清理临时目录；需要查看会话或报告时必须使用 `--keep`，展示结束后由讲师清理本次输出的演示目录。

## 课前准备

```bash
cd self-evolve/                      # 进入 Skill 目录
python3 scripts/teaching_demo.py --keep  # 保留合成数据、两轮扫描与示例分析报告
```

彩排输出会打印合成数据根中的 `home` 和 `state_root`、每轮 `stats`、`import-analysis` 结果和报告路径。打开 `import-analysis` 返回的 `report`，它包含合成示例分析；同目录 `report.html` 是扫描初筛快照，仍可能显示等待分析。示例分析由脚本固定生成，不能当作已完成真实 Agent 语义评估。

将输出中的两个绝对目录分别填入以下变量，用于本次演示的后续命令：

```bash
SE_DEMO_HOME="<输出中的 home>"
SE_DEMO_STATE_ROOT="<输出中的 state_root>"
```

`--home` 只选择读取来源，不会隔离写入账本。`teaching_demo.py` 的环境设置只对其子进程生效；后续 `scan`、`status` 和导入命令都要显式设置 `SELF_EVOLVE_DATA_ROOT`，不能依赖父 shell 继承。以下命令还通过 `env -u` 排除旧数据叶目录环境变量，避免继承旧部署路径；它不会修改父 shell 配置。仅做一次性命令检查、无需打开报告时，可以省略 `--keep`。

## 场景 A：多 Runtime 汇总（含 WorkBuddy/CodeBuddy 与 Claude/Codex 混合）

**讲稿要点**

- 一条 `scan` 同时发现 Claude Code、Codex、WorkBuddy、CodeBuddy、Gemini 的完整会话与 ZCode 的任务索引。
- 同事最常用的 WorkBuddy 走两条来源：`projects` JSONL（claude 方言）和 `traces/trace_*.json`（generation span 抽取）。
- 覆盖列表里 Qwen 等目录存在但格式未接入的 Runtime 显示 `unsupported`——这是**如实声明覆盖缺口**，不是错误。

**执行命令**

```bash
python3 scripts/teaching_demo.py --keep
```

**预期看到的字段**

- `stats.new >= 6`（六个 Runtime 各至少 1 个合成会话）、`stats.selected >= 3`。
- `runtimes_with_evidence` 包含 `claude`、`codex`、`workbuddy`、`codebuddy`、`gemini`、`zcode` 中的多个。
- `coverage` 中 `qwen` 一行 `status: unsupported`。
- `cumulative.unique_sessions` 与 `duplicate_views` 的关系：副本不增加独立会话数。

**HTML 页面**

- `report-coverage.html`：逐来源状态表，指出 WorkBuddy 两行（projects + traces）和 Qwen 的 unsupported 标记。
- `report-sessions.html`：每条证据标注 Runtime 和完整性；ZCode 证据显示"索引摘录 · 非完整对话"。

**降级说法（失败时）**

- 某个 Runtime 证据缺失：'"X 没进证据包，coverage 里能看到它的状态；我们看它实际是什么状态，不猜原因。"'
- 合成数据被初筛全部过滤：'"初筛是保守规则，不等于无价值；课堂用 selected 的几条演示即可。"'
- 报告打不开：'"报告是七页同前缀的文件组，确认整个目录都在；单复制 report.html 会缺页。"'

## 场景 B：增量账本第二轮未变跳过

**讲稿要点**

- 第二轮 `scan` 不改任何会话文件：已处理项按修订标记（JSONL 是 mtime+size，ZCode 是 updated_at）跳过，不重读正文。
- 这就是"每周跑一次也不重复消耗"的机制。

**执行命令**

```bash
env -u SELF_EVOLVE_REVIEW_ROOT -u SELF_EVOLVE_RUNTIME_ROOT \
  -u SELF_EVOLVE_STATE_ROOT -u SKILL_EVOLVE_STATE_ROOT \
  SELF_EVOLVE_DATA_ROOT="$SE_DEMO_STATE_ROOT" python3 scripts/public_workflow.py scan \
  --home "$SE_DEMO_HOME" --max-sessions 200
env -u SELF_EVOLVE_REVIEW_ROOT -u SELF_EVOLVE_RUNTIME_ROOT \
  -u SELF_EVOLVE_STATE_ROOT -u SKILL_EVOLVE_STATE_ROOT \
  SELF_EVOLVE_DATA_ROOT="$SE_DEMO_STATE_ROOT" python3 scripts/public_workflow.py status
```

（或直接看彩排输出的"第 2 轮 scan"段。）

**预期看到的字段**

- 第 2 轮 `stats.unchanged >= 6`（第一轮已处理的全部跳过）。
- `stats.new` 通常为 0；只有第一轮被单轮预算截断的项才会在这轮补齐（`pending_budget` 的正常回填）。
- `status` 的 `recent_runs` 有两行，`sessions` 计数与两轮合计一致。
- `analysis_count` 为 1（彩排导入过一次分析）。

**HTML 页面**

- `report-coverage.html`：进度条显示 unchanged 占比；"累计记录"行持续增长。
- `report.html`（总览）：如果无新证据且无待分析，`analysis_status` 为 `no_pending_evidence`，总览保持安静而不是重复分析。

**降级说法（失败时）**

- `unchanged` 不是 0 也不是全部：'"预算截断的那部分这轮补上了，这是 pending_budget 的正常回填。"'
- 账本报 `unsupported_ledger_schema`：'"账本损坏或版本不符时 fail-closed，不自动重建；这是保护历史，不是故障。"'

## 场景 C：失败与隐私边界

**讲稿要点**

- 两个故意放进合成数据的坏文件：一个 schema 不认识的 JSONL，一个载荷结构不认识的 message。两者都进 `stats.failed` 和 `failures`，不在报告里消失。
- ZCode 证据永远标注"索引摘录"，因为任务索引没有角色边界、可能截断。
- 含司法/诉讼关键词的材料被 `quarantined`，只存规则代号。

**执行命令**

```bash
# 复用场景 A 保留的演示目录，两个故意损坏的文件已经在其中
env -u SELF_EVOLVE_REVIEW_ROOT -u SELF_EVOLVE_RUNTIME_ROOT \
  -u SELF_EVOLVE_STATE_ROOT -u SKILL_EVOLVE_STATE_ROOT \
  SELF_EVOLVE_DATA_ROOT="$SE_DEMO_STATE_ROOT" python3 scripts/public_workflow.py status
```

**预期看到的字段**

- `stats.failed >= 1`（第 1 轮起就有），`failures` 数组每项含 `runtime`、`error`（`unsupported_jsonl_schema` 或 `unsupported_message_payload`）、截短的 `session_key`。
- `status` 的 `sessions.failed` 与 `failed` 计数一致；下轮 `scan` 自动重试失败项。
- ZCode 证据的 `completeness: index_excerpt`。

**HTML 页面**

- `report-coverage.html`：来源状态含 `partial`（部分读取失败）和 `unsupported`；"异常"栏列出错误代号。
- `report-sessions.html`：ZCode 卡片带"索引摘录 · 非完整对话"标记。
- `report-guide.html`：验证边界一节如实列出局限（不复制原文、单次成功不代表多轮稳定等）。

**降级说法（失败时）**

- 失败数比预期多：'"每个失败都有代号和 runtime，coverage 页能定位；失败不记成功，下轮自动重试，不阻塞其他来源。"'
- 有人问"能不能看原文"：'"账本只存脱敏摘要与哈希，原文留在各自 Runtime 里；这是隐私边界，不是功能缺失。"'

## 课堂节奏建议

1. 场景 A（约 10 分钟）：先看 coverage 页建立"多来源 ≠ 全覆盖"的直觉，再回到总览。
2. 场景 B（约 5 分钟）：只看两轮 `stats` 对比，重点讲 `unchanged`。
3. 场景 C（约 10 分钟）：failures + 索引摘录标记 + 隔离机制，回应隐私问题。
4. 收尾：`report-skills.html` 的建议卡，强调"建议 ≠ 采用"，人工审阅后才安装。

## 教学检查清单（讲师用）

- [ ] `python3 scripts/teaching_demo.py --keep` 彩排通过，输出的 home、state_root 和分析报告路径已记下。
- [ ] `--keep` 模式验证过 Finder 可见合成文件。
- [ ] 三页核心 HTML（coverage / sessions / skills）已在本机打开过一次。
- [ ] 场景 C 的 `failures` 字段值与讲义一致（`unsupported_jsonl_schema` / `unsupported_message_payload`）。
- [ ] 后续命令同时绑定合成 home 与 state_root，未向默认账本写入或读取真实状态。
- [ ] 未使用任何真实业务材料；演示结束后仅清理本轮保留的合成目录。
