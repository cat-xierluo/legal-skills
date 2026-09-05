# 分层验证回执

当 build、unit、integration、e2e、runtime 等阶段已经由 Agent 或 CI **真实执行**后，使用本页的
`verification-gate-stage-report/v1` 输入契约，把阶段事实机械转换为
`production-engineering-completion-evidence/v1` staged receipt。转换器不运行输入里的命令，也不
裁定完成层级；最终结论由 `production-engineering-audit`（PEA）作出。

## 使用边界

- 先执行项目对应的验证阶段并保存脱敏日志，再写输入报告；不要把计划执行的命令写成已执行。
- 失败阶段也要保留。转换器会输出合法的 `failed` 阶段，PEA 随后将其判为 hard。
- 转换器只接受 `tested`、`reproduced`、`e2e_verified` 三种 `claimed_level`，并按输入原样转写；
  它不判断该层级是否被证据支持。
- live canary 与 release 还需要 PEA 的 `environment` / `release` 证据，不属于本转换器。
- 输出不是 READY、NOT READY 或 RELEASED 判决，不能代替 PEA 审计。

## 输入契约

从 [`assets/staged-receipt-input.example.json`](../assets/staged-receipt-input.example.json) 复制后替换
占位内容。顶层字段如下：

| 字段 | 约束 |
| --- | --- |
| `contract` | 固定为 `verification-gate-stage-report/v1` |
| `claim` | `id`、`type`、`statement`、`claimed_level`、带时区 `observed_at` |
| `candidate.git_commit` | 完整 Git object id，必须等于 `--repo` 的当前 `HEAD` |
| `target` | `type` 为 `application/service/workflow/skill`，`name` 为脱敏名称 |
| `stages` | 非空阶段数组；规则见下一节 |
| `consumer` | `name`、boolean `observed`；观察成功时还要有 `evidence` |
| `unsupported_claims` | 未覆盖范围的 string array；已全部覆盖时可为空 |
| `original_symptom` | `bugfix/performance` 必填：`status=reproduced/not_verified` + `evidence` |
| `negative_control` | `bugfix/performance` 必填：`status=proved/not_proved` + `evidence` |

`feature/refactor/release` 不写 `original_symptom` 和 `negative_control`。这里允许
`not_verified/not_proved`，是为了如实把未闭环事实交给 PEA 判 hard，而不是在转换时抹掉报告。

### 阶段字段

`kind` 只允许 `static`、`unit`、`build`、`integration`、`e2e`、`runtime`；`status` 只允许
`passed`、`failed`、`skipped`、`not_run`。

- `passed/failed`：必须记录非空 `command`、非负整数 `exit_code/failure_count` 和仓内
  `evidence`。`passed` 要求二者均为 0；`failed` 至少一项非 0。
- `skipped/not_run`：只能用于 `required=false`，必须有非空 `skip_reason`，且不能伪带命令、退出码
  或 evidence。
- `fresh_context` 只允许用于已执行的 `runtime` 阶段，而且必须是 boolean。该字段是执行器声明，
  PEA 仍要求人工抽查 Skill 前向测试证据。
- `id` 必须唯一。字段类型不做宽松转换：例如 JSON boolean 不能充当整数 0/1。

## 证据与安全

所有 evidence 必须是规范化仓内相对 POSIX 路径，生成时必须存在并解析为普通文件。绝对路径、
`..` 穿越、缺失文件和穿透仓外的符号链接都会拒绝。报告与回执不写凭证、Cookie、客户材料、
可复用 token 或本机绝对路径；发现常见 secret 形态时失败关闭，不做静默脱敏。

转换器只执行固定的 Git 元数据读取来绑定当前 `HEAD`；它从不执行 `stages[].command`，也不启动
后台进程。

## 生成并交给 PEA

先提交候选代码并完成各阶段，把日志放到项目既有的忽略证据目录。生成回执后不得再修改候选
HEAD；否则旧回执失效。

```bash
mkdir -p artifacts/production-engineering-audit

python3 <verification-gate-root>/scripts/build_staged_receipt.py \
  --repo . \
  --input artifacts/verification-gate/stage-report.json \
  --output artifacts/production-engineering-audit/completion-evidence.json

python3 <production-engineering-audit-root>/scripts/audit_project.py \
  --repo . \
  --config .production-engineering-audit.toml
```

`--output` 必须是仓内相对路径且父目录已存在；使用临时文件原子替换。PEA 配置需启用
`[completion]`，让 `evidence_file` 指向该输出，并令 `target_type` 与输入 `target.type` 一致。
读取 PEA 的 JSONL 结果和退出码后，才能报告当前证据真正支持的层级。

## 失败口径

输入结构、候选绑定或证据引用非法时，脚本返回 `65` 且不写回执；写文件失败返回 `74`。阶段本身
失败不是转换失败：只要阶段事实结构一致且 evidence 可用，脚本仍返回 `0` 并输出 `failed`，由
PEA 产生阻断 finding。
