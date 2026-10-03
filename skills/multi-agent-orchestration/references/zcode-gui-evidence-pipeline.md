# ZCode GUI Evidence Pipeline — 合成集成反例矩阵

## 目的

`test-zcode-gui-evidence-pipeline.py` 与 `zcode-gui-pipeline-fixtures.py`
构成一套**可移植、纯标准库**的组合回归资产：用合成 SQLite 反例矩阵驱动
**真实的 collector 与 adapter 子进程**，端到端检测两类组合缺陷：

1. **误判完成**：把未完成/失败/冲突的会话映射成 READY_FOR_PM_REVIEW
   等交付态，或让较早的成功覆盖最新的错误；
2. **泄漏**：reasoning、tool、status_reason 文本、其他会话（decoy）内容
   出现在 collector/adapter 的 stdout 中。

两者此前只有各自的单元测试；本套件覆盖真实组合路径（SQLite → 只读
collector 元数据文件 → adapter），且不镜像单元测试的构造方式。

## 冻结生产依赖（只读消费，不修改、不复制、不提交）

| 角色 | 脚本 | 冻结版本 |
|------|------|----------|
| collector | `skills/multi-agent-orchestration/scripts/zcode-session-evidence.py` | PR250 head `554a60c1ea27155ad03ec0e2b558d70a8fbb7c1f` |
| adapter | `skills/multi-agent-orchestration/scripts/zcode-gui-monitor-adapter.py` | PR253 head `9f77ef0d51cd7b240f512da5c7bfc8257490f98b` |
| negative control | 同 adapter 路径的历史 initial 版本 | commit `3ed567971a7c6c41612d2cd611aef25ef9f8117f` |

runner 按 **CLI 参数 > 环境变量 > 同目录兄弟文件** 的顺序解析依赖；
三者都不可用时整个套件输出 `SKIP` 并以 **exit 77** 结束，绝不静默通过。
negative control 所需的历史 adapter 由 runner 通过
`git cat-file blob 3ed5679...:<path>` 自动提取到私有 workdir（不可达时仅
跳过该一项控制，不影响其余 case）；也可用 `--legacy-adapter <path>`
显式指定，`off` 关闭。

## 用法

```bash
# 无依赖时的默认行为：SKIP, exit 77
python3 skills/multi-agent-orchestration/scripts/test-zcode-gui-evidence-pipeline.py

# 注入真实冻结依赖（CI 消费命令）
ZCODE_GUI_COLLECTOR=/path/to/zcode-session-evidence.py \
ZCODE_GUI_ADAPTER=/path/to/zcode-gui-monitor-adapter.py \
python3 skills/multi-agent-orchestration/scripts/test-zcode-gui-evidence-pipeline.py \
  --workdir /private/tmp/zcode-gui-pipeline-run

# 仅列出反例矩阵
python3 skills/multi-agent-orchestration/scripts/test-zcode-gui-evidence-pipeline.py --list-cases

# 单独物化一个合成库（人工检查用）
python3 skills/multi-agent-orchestration/scripts/zcode-gui-pipeline-fixtures.py \
  --case completed_latest_error_wins --out /tmp/case.sqlite
```

**退出码**：`0` 全部预期断言成立；`1` 存在真实失败；`77` 依赖缺失
（SKIP）。negative control 中旧 adapter 的预期拒绝记录为 negative
control，不计入候选失败；但若旧缺陷**未能复现**（旧 adapter 通过了
admitted/no-turn 反例），套件按真实失败处理。

**输出**：stdout 仅打印有界 summary（每 case 一行 PASS/FAIL/SKIP +
汇总）；逐条断言与全部进程输出写入 `<workdir>/detail.log` 与
`<workdir>/summary.json`（私有路径）。`--workdir` 缺省为新建临时目录。

## 反例矩阵（18 个具名 case）

每个 case 使用**独立合成 SQLite**（schema 含 collector 必需列；行内容
全部为合成值），并植入诱饵会话 `sess-decoy-other-session` 与
`CANARY-*` 令牌。统一断言：collector/adapter 输出精确 state 或精确
错误码 + exit、adapter flags 恒 false（`pmAccepted`/`orcaSupervised`/
`livenessAuthoritative`）、DB 运行前后 SHA-256 不变且无 journal/wal
残留文件、metadata 只携带绑定的合成 session、全部 canary/decoy 令牌
不外泄。

| Case | 构造 | 关键断言 |
|------|------|----------|
| `admitted_no_turn` | admitted、无 promoted、无 turn | adapter `INPUT_ACCEPTED`，provider/model=`unknown` |
| `promoted_no_turn` | promoted 但 turn 从未开始 | `TURN_UNKNOWN` |
| `turn_running` | running turn + 部分 assistant（仅 reasoning part） | `TURN_RUNNING`，turnId 回显 |
| `completed_ready_for_review` | completed + 完整无错 assistant | `READY_FOR_PM_REVIEW`；`--expected-evidence-sha256`（真摘要）+ provider/model 期望全部成立 |
| `completed_latest_error_wins` | 同 parent 两条 assistant，较早成功 seq=10，最新 error seq=20 | 精确选中 `msg-asst-latest`（errorFree=false），`DELIVERY_ERROR`；较早成功不覆盖 |
| `turn_cancelled` | 用户取消 turn | `TURN_CANCELLED` |
| `turn_error` | error turn、无 assistant | `TURN_ERROR` |
| `provider_missing_unknown_ok` | completed 但缺 providerId/modelId | 保持 `unknown` 且不阻塞 review gate |
| `expected_provider_mismatch` | 错误的 `--expected-provider` | exit 2 `PROVIDER_MISMATCH` |
| `collector_input_not_found` | 错误的 input 绑定查 collector | exit 1 `INPUT_NOT_FOUND` |
| `adapter_binding_mismatch` | 元数据与另一 session id 送 adapter | exit 2 `BINDING_MISMATCH` |
| `multi_turn_ambiguous` | 同一 promoted message 两条 turn_usage | exit 1 `TURN_AMBIGUOUS` |
| `assistant_sequence_ambiguous` | 两条 assistant 并列最大 sequence | exit 1 `ASSISTANT_AMBIGUOUS` |
| `bad_schema_missing_table` | 缺 `part` 表 | exit 1 `DB_SCHEMA_INVALID` |
| `bad_json_message_data` | assistant data 非法 JSON | exit 1 `JSON_MALFORMED` |
| `canary_containment` | status_reason/reasoning/tool part 植入 CANARY，诱饵文本 CANARY | 两次运行（含 `--include-final-text`）均零泄漏，仍 `READY_FOR_PM_REVIEW` |
| `digest_mismatch` | 过期期望摘要 | exit 2 `EVIDENCE_DIGEST_MISMATCH` |
| `legacy_nullable_negative_control` | 复用 admitted/no-turn 库 | 历史 initial adapter `3ed5679` 以 exit 2 `EVIDENCE_TYPE_INVALID` 拒绝 collector 合法 null turn 标量（旧缺陷复现）；固定 `9f77` 版本对同一证据返回 `INPUT_ACCEPTED` |

## 安全保证

- 合成库全部生成在 `--workdir` 下；runner 断言 db 路径不越出 workdir。
- collector 以 `mode=ro` + `PRAGMA query_only` 打开数据库；套件对每个
  case 断言库文件 SHA-256 与目录文件集合运行前后不变（无写入、无
  journal/wal 残留）。
- 不访问网络、不启动服务、不触碰真实用户数据库；所有进程均在 90s
  超时内本地运行。
- 泄漏扫描覆盖 collector/adapter 的 stdout 与 stderr（含
  `--include-final-text` 变体）。

## 依赖

纯 Python 3.9+ 标准库（`sqlite3`、`subprocess`、`hashlib`、`importlib`），
无需安装任何第三方包。negative control 的自动提取需要本 checkout 的
git 对象库可达（浅克隆时可改用 `--legacy-adapter` 显式提供历史脚本，
或接受该单项 SKIP）。
