# 支持范围与一次完整初始化示例

## 如何理解支持

下表只说明 v0.5.3 的代码路径。模拟文件回归不等于现行客户端已实际加载；没有做过当前版本新会话测试的平台，生效情况仍为 `NOT_VERIFIED`。

| 平台 key | 环境检测 | 用户级 / 项目级写入 | 可选模型探测 |
|---|---|---|---|
| `claude-code` | 有 | `~/.claude/CLAUDE.md` / `CLAUDE.md` | 按项目目录唯一候选，或 `--session-file` |
| `codex` | 有 | `~/.codex/AGENTS.md` / `AGENTS.md` | 精确 cwd；并发时用 `--session-file` |
| `openclaw` | 有 | `~/.openclaw/AGENTS.md` / `AGENTS.md` | 不支持，显式 `--model` |
| `myagents` | 有 | `~/.myagents/CLAUDE.md` / `CLAUDE.md` | 显式 `--session-file` |
| `qoderwork` | 有 | 仅检测，不自动写入 | 按项目目录唯一候选，或 `--session-file` |
| `qwenwork` | 有 | 仅检测，不自动写入 | 按项目目录唯一候选，或 `--session-file` |
| `workbuddy` | 有 | 仅检测，不自动写入 | 显式 generation trace 文件 |
| `orca` | 有 | 仅检测，不自动写入 | 不支持，显式 `--model` |

上述路径是当前平台表映射；自定义目录或客户端格式变化应先核对。模型探测需要 Python 3.9+，默认不运行；没有 Python 时用已知的 `--model` 即可。`--model` 和环境变量属于调用方声明，session probe 属于会话文件观测；都不保证网关实际服务的底层模型，平台别名应照实保留。

## quick 模式的完整示例

以下资料完全虚构，用来说明产物与恢复路径；不是自动代填用户答案的预设。使用时由用户明确项目路径、权限与现有台账后再写入。

用户已回答：

> 我做民商事诉讼。这个演示项目代号是 LIT-DEMO-001，处于证据整理阶段，交付 Markdown 备忘录。只允许在指定项目目录内读写，不允许联网外发、删除、法院提交或支付。采用 strict 模式。现有 TASKS.md 记录期限和责任人，证据清单记录来源，决策暂在既有备忘录记录；不另建台账。初始化时的模型由用户明确声明为 example-model。

Agent 应先确认这些答案已覆盖五项必要问题，无须再次询问同一授权。生成最小规则到临时内容文件（文件不带外层 marker），例如：

```markdown
# LIT-DEMO-001 协作规则

- 角色与交付：协助整理证据，输出 Markdown 备忘录；最终法律判断由律师复核。
- 权限：只在指定项目目录内读写；外发、删除、法院提交与支付不在授权范围。授权范围内的常规工作可继续执行，确需新增权限时再确认。
- 保密：本文件只存项目代号、规则和入口，不存真实当事人、案号、金额、联系方式或凭证。
- 信息缺口：区分材料事实、推断与建议；主体、送达、日期或来源缺失时列出缺口，不补造事实。
- 溯源：重要判断保留材料路径、页码和核验时间；法律依据由律师复核来源、时点及适用范围。
- 回溯：期限和责任人写现有 TASKS.md；证据变化写既有证据清单；决策沿用已有备忘录，不创建空台账。
- 阶段：证据整理；关键时点待补充。
```

从 Skill 根目录依次运行：

```bash
cd /absolute/demo-project
SKILL_ROOT=/absolute/legal-harness-init
bash "$SKILL_ROOT/scripts/validate-content.sh" --file /tmp/demo-rules.md --privacy-mode strict
bash "$SKILL_ROOT/scripts/write.sh" --content-file /tmp/demo-rules.md \
  --level project --platforms codex --project-dir /absolute/demo-project \
  --mode update --block-id legal-safety-baseline --privacy-mode strict \
  --model example-model --dry-run
# 核对 diff 后以相同参数去掉 --dry-run；已有授权内无需重复索取许可。
```

`detect.sh` 用当前工作目录判断项目证据，先进入演示项目再检测；不要在原工作目录读一遍后再到目标项目写入。dry-run 是人工核对点：除非用户在同一指令中已经明确核准这份 diff，否则不得在同一轮自动去掉 `--dry-run` 继续写入。已知当前 harness 时，把 `--harness <key>` 传给记录脚本，避免隔离环境下把 harness 记成 `unknown`。

真实写入后，检查 JSON 回执中 `init_env_status=recorded`，并核对 `after_sha256` 与最终文件一致。`write.sh` 已自动记录环境，无须手动再追加一次。原文件有内容时，首次原文和权限保存在 `.bak.legal-harness-init` 及 `.meta` 中；可先用 `restore.sh --dry-run` 预览恢复。

没有已知模型时，配置可能已写入而环境记录失败：退出码非零，`status` 以 `_record_incomplete` 结尾。补齐 `--model` 后重跑相同写入命令会补记环境；再次执行同样内容保持零 diff。

接着按 [新会话核对](19-activation-verification.md) 记录加载来源和四项探针。手写证据最多得到 `BEHAVIOR_DECLARED`；本版本不自动授予 `BEHAVIOR_VERIFIED`。

“5 分钟”是上手设计目标。Agent 演练能检验流程，真实律师首次使用耗时仍需真人测试，不能用脚本执行时长替代。
