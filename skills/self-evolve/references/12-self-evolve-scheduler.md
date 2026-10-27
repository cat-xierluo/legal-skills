# Cron-only 调度契约

## 单一事实源

外部 Cron 系统是任务是否部署、是否启用和何时运行的唯一事实源。`config/scheduled_tasks.yaml` 是本机私有任务注册表和运行防线，不入 Git 或发行包；缺失表示尚未配置，执行器不会运行任务。仅在使用旧调度时从 `config/scheduled_tasks.example.yaml` 复制并填写；示例中的任务默认关闭，用户可逐项启用。旧调度不是公开工作流的主入口。

外部 Cron 统一执行：

```bash
python3 scripts/scheduler_run.py \
  --task <task-id> \
  --run-now \
  --trigger external
```

## Schema v2

```yaml
schema_version: "2.0"
tasks:
  - id: nightly-dream-sweep
    name: 夜间 Timeline Dream Sweep
    runner:
      enabled: false
      external_only: true
    recommended_schedule:
      cron: "30 2 * * *"
      timezone: <your-timezone>
    command:
      type: dream_sweep
      args:
        since: 14d
        mode: dry-run
    run_policy:
      overlap: skip
      timeout_minutes: 60
      max_runs_per_day: 1
```

字段含义：

- `runner.enabled`：不可绕过的 kill switch；false 时任何触发都拒绝。
- `runner.external_only`：只接受 `--trigger external`，拒绝 localhost 面板或普通手动执行。
- `recommended_schedule`：供外部 Cron 配置参考，不代表已部署或已启用。
- `command.type`：只能命中 `scheduler_run.py` 内固定白名单。
- `command.args`：按每种命令的类型、范围和枚举白名单校验。
- `run_policy`：提供重入跳过、超时和每日运行上限。

校验配置：

```bash
python3 scripts/scheduler_run.py --validate-config --json
```

配置不合法时必须在创建锁或写运行日志前失败。

## 从旧任务迁移

逐条检查外部 Cron 的实际命令，不要仅修改本文件：

```text
旧：scheduler_run.py --task <id> --run-now --allow-disabled
新：scheduler_run.py --task <id> --run-now --trigger external
```

- 彻底删除 `--allow-disabled`；Schema v2 的 kill switch 不允许被任何入口绕过。
- 所有 `external_only` 任务都必须显式传入 `--trigger external`，缺失时非零退出。
- 补齐 `refresh-skill-inventory` 与 `nightly-skill-portrait-distill` 两条真实外部任务，并确保库存先于画像。
- `weekly-deep-dream` 默认保持 `runner.enabled: false`；外部任务即便存在，也不能绕过代码侧 kill switch。
- 先完成旧状态复制迁移，再切换命令；运行时返回 `migration_required` 时按 `next_action` 处理。
- 用 `legacy_hook.py status --json` 核对 SessionEnd 残留，只有用户明确决定后才执行清理。

本 Skill 不读取特定 Cron 产品的私有数据库来宣称“部署完成”。部署状态应在对应调度系统中核验，并至少观察一次真实非零/成功退出与外部运行记录。

## migrate_state 冲突裁决法

`scripts/migrate_state.py --apply` 遇 conflict 时 fail-closed（不写完成标记），脚本无裁决参数，需人工先把双方变成一致再 `--apply`。冲突指 source（legacy in-tree）与 destination（external `DATA_ROOT`）同名文件哈希不同。

诊断关键是看双方 mtime 与体积：

- legacy in-tree 状态在迁移启动后会冻结——多个文件呈现同一秒 mtime（当初一次性 copy 的产物）；
- external state（`DATA_ROOT`）是活跃真相——持续更新、体积更大、schema 字段更多。

故默认 **dst 是真相、legacy 是过时快照**。裁决步骤：

1. `migrate_state.py --dry-run --json` 列出所有 conflict；
2. 逐项核对双方 mtime 与体积，确认"dst 更新更大"成立——若某项双方都含有效、不重复数据，**不能套用本法**，需逐项人工裁决；
3. 备份 legacy 旧内容（`tar -czf` 到临时目录，可回滚）；
4. `cp dst→legacy` 使双方哈希一致 → conflict 归零（脚本靠让双方一致来清零，无裁决参数）；
5. `migrate_state.py --apply` 写完成标记（dry-run 复核 `conflict=0`）；
6. 回滚：解压备份覆盖 legacy + 删完成标记。

> `refresh_skill_inventory.build_inventory` 已按 realpath 去重同一物理 skill；`interactive_sediment._resolve_inventory_target` 对"同 SKILL.md 文件的重复登记"也折叠为 resolved（v0.8.1）。但 **state 文件的 conflict 仍需按上法人工裁决**，`migrate_state` 不自动合并 state。

## 安全执行

调度器必须：

1. 从固定 `COMMAND_SPECS` 选择脚本，不接受 shell 字符串；
2. 对所有参数进行类型、枚举、正则和上下界校验；
3. 使用每任务独立锁；锁与 `active_run` 同时绑定 PID、进程启动身份、boot identity 和 owner token，并以任务 timeout 加 grace 作为不可延长的硬过期边界，避免 PID 复用或遗留 reservation 永久阻塞；
4. 只由锁的真实 owner 删除锁；
5. 设置 timeout 与每日次数限制；每次执行必须在启动子进程前向月度 JSONL 追加并 fsync 一条 `attempt`，最终 `result` 复用同一 `run_id`，配额按唯一 `run_id` 计数，使启动后崩溃不能绕过配额；
6. 将 stdout/stderr 写入外部调度日志；
7. 将运行记录按月写入 JSONL，面板只读取有界尾部；当月日志出现坏行、截断行或无法读取时，配额检查必须 fail closed，拒绝启动且返回可执行的 `next_action`；
8. 对阶段性 backfill 完成状态做终态跳过，避免重复写无意义日志。

## 推荐任务分层

| 任务 | 层级 | 默认策略 |
|------|------|----------|
| `refresh-skill-inventory` | 每日确定性 | 默认关闭；显式启用后由外部 Cron 调用 |
| `nightly-dream-sweep` | 每日确定性 | 默认关闭；显式启用后由外部 Cron 调用 |
| `history-backfill-index` | 阶段性确定性 | 默认关闭；启用后完成可外部停用或降频 |
| `nightly-skill-portrait-distill` | 每周可选 LLM | 默认关闭；启用后按预算控制 |
| `weekly-deep-dream` | 每周可选 LLM | 默认 kill switch 关闭，明确授权后再启用 |
| `weekly-iteration-report` | 每周确定性 | 默认关闭；启用后输出脱敏 digest |
| `maintain-runtime` | 每周确定性 | 默认关闭；只报告或做显式、安全维护 |
| `render-panel-snapshot` | 按需/低频 | 默认关闭；只生成脱敏静态快照 |

不要让 Skill 代码创建、修改或删除外部 Cron。涉及调度系统状态的操作必须由用户在对应系统中决定。

### WorkBuddy / QwenWork 等平台定时任务

self-evolve **平台无关**:不管你用 launchd / cron / WorkBuddy 定时器 / QwenWork 调度,统一通过一个入口触发任务:

```bash
python3 scripts/scheduler_run.py --task weekly-iteration-report --run-now --trigger external
```

把这个命令配进你所用平台的定时任务 / automation(每周一次)。`weekly-iteration-report` 会生成一份面向用户的脱敏 digest——写一份到 review inbox(data_root 受控),一份到桌面(`~/Desktop/self-evolve-周报-*.md`),让你直接看到本周 self-evolve 帮你发现了什么。

self-evolve **不主动创建平台调度**:配置由你在平台侧确认导入(尊重「skill 不创建调度」边界)。检测到你用的是哪个平台、并给出该平台的配置建议,是 `setup_platform_schedule.py` 的工作,不在此处自动执行。

### 平台调度配置建议(setup_platform_schedule)

```bash
python3 scripts/setup_platform_schedule.py            # 检测本机平台 + 打印各平台配置建议
python3 scripts/setup_platform_schedule.py --json     # 结构化输出(检测到哪些平台)
```

检测 WorkBuddy / QwenWork / MyAgents / **OpenClaw**,为 `scheduled_tasks.yaml` 里每个 enabled 任务生成该平台的配置命令(可复制粘贴)。self-evolve 仍不主动写入调度——你确认后导入。

**OpenClaw**(macOS 推荐,经 Gateway 管理,系统睡眠唤醒后补跑,比裸 cron 可靠):用 `openclaw cron add --command` 直接跑 `scheduler_run`(无头,不需 agent prompt)。setup 工具会为每个任务生成形如:

```
openclaw cron add --cron "30 2 * * *" \
  --command 'python3 scripts/scheduler_run.py --task nightly-dream-sweep --run-now --trigger external' \
  --command-cwd "<self-evolve skill root>" \
  --name "self-evolve nightly-dream-sweep"
```

挂完后 `openclaw cron list` 查看、`openclaw cron run <job>` 试跑、`openclaw cron rm <job>` 删除。
