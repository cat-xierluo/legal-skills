# scripts 使用说明

本目录提供无第三方依赖的检测、内容校验、安全写入、恢复、分层验证与回归测试脚本。

| 脚本 | 用途 | 主要边界 |
|---|---|---|
| `lib_platforms.sh` | 8 个 harness 的平台权威表 | 被 detect/write 共同读取 |
| `detect.sh` | 输出 runtime 候选、安装痕迹和项目证据 | 只读路径/环境变量存在性，不读值或配置正文 |
| `validate-content.sh` | 拦截凭证、高敏身份号和不符合隐私模式的案件信息 | 只报告敏感类别，不回显命中值 |
| `write.sh` | 按实际路径去重并 upsert 受管区块 | 候选校验、diff、可验证备份、原子替换；原始备份异常时失败关闭 |
| `restore.sh` | 恢复首次写入前的原文、权限和哈希 | 拒绝符号链接、缺失哈希或损坏备份 |
| `verify.sh` | 区分写入、加载和行为验证 | 配置结构与新会话证据必须同时成立，否则不升级状态 |
| `record-init-env.sh` | append 一行 harness+model 元数据到 init-environment 受管区块 | 失败关闭；不臆造 model；残缺 marker 拒绝；不读环境变量值 |
| `probe-session-model.sh` | 从当前 harness session 反查 model（`--probe-from-session` 调用） | v0.5.2 支持 claude-code/qwenwork/qoderwork/myagents/codex/workbuddy；openclaw/orca not_found；不读正文 |
| `test.sh` | 在 `/tmp/legal-harness-init-test.*` 中执行无网络回归 | 退出时只清理自己创建的测试目录 |

## 典型顺序

```bash
bash scripts/detect.sh --runtime codex
bash scripts/validate-content.sh --file /tmp/module.md --privacy-mode strict
bash scripts/write.sh --content-file /tmp/module.md --level project \
  --platforms codex,openclaw --project-dir /path/to/project \
  --mode update --block-id legal-safety-baseline --privacy-mode strict --dry-run
# 确认 diff 后去掉 --dry-run
bash scripts/record-init-env.sh --target /path/to/project/AGENTS.md \
  --action init [--model <name>] [--note "quick 引导首跑"]
bash scripts/verify.sh --target /path/to/project/AGENTS.md \
  --block-id legal-safety-baseline --session-evidence /tmp/session-evidence.txt
bash scripts/test.sh
```

## 状态和退出码

- `detect.sh`：检测到至少一个已安装 harness 为 0，否则为 1；即使为 1 仍输出 JSON。
- `validate-content.sh`：校验通过为 0，拒绝为 1。
- `write.sh`：全部目标成功、无变化或待确认时为 0；校验/写入失败为 1。
- `restore.sh`：恢复或 dry-run 成功为 0，否则为 1。
- `verify.sh`：至少达到 `CONFIG_WRITTEN` 为 0；否则为 1；参数错误为 2。
- `record-init-env.sh`：成功 / unchanged / dry_run 为 0；写入失败为 1；参数错误为 1。
- `probe-session-model.sh`：找到为 0；找不到为 1；参数错误为 2。
- `test.sh`：全部回归通过为 0，否则为 1。

`write.sh` 的 `create`、`update`、`append` 都只操作指定受管区块，不覆盖区块外内容。`create` 遇到已有文件默认返回 `needs_confirmation`；`update`/`append` 表示用户已授权本次受管区块写入。

## 输出 schema

| 脚本 | `schema_version` | 关键字段 |
|---|---:|---|
| `detect.sh` | `3` | `runtime_candidates`、`current_runtime*`、`harnesses_detected`、`project_level` |
| `write.sh` | `2` | `level`、`mode`、`privacy_mode`、`block_id`、`targets[]` |
| `validate-content.sh` | `1` | `status`、`privacy_mode`、`bytes` |
| `restore.sh` | `1` | `status`、`target`、`mode`、`sha256` |
| `verify.sh` | `1` | `status`、三项布尔状态、`target`、`target_sha256`、`block_id`、`note` |
| `record-init-env.sh` | `1` | `status`（recorded / unchanged / dry_run）、`target`、`row`、`mode` |
| `probe-session-model.sh` | `1` | `status`（found / not_found）、`model`、`evidence`、`reason`、`harness`、`cwd`（仅 `--json`） |

字段发生不兼容变化时递增对应脚本的 schema 版本；下游应按脚本和 `schema_version` 解析，不要把不同脚本的版本混为一体。
