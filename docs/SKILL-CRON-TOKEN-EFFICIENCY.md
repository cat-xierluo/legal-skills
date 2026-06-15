# Skill 定时任务 Token Efficiency 策略

> 面向「批量任务类 Skill + MyAgents cron」场景的 LLM token 消耗优
> 化策略。本指南解决一个具体问题：**cron 任务用强模型 Agent 跑是
> 浪费——大部分时间 Agent 在 debug / 读源码 / 反思,真正干活的
> 是脚本**。把脚本鲁棒性本身当成「省 token 的杠杆」。

---

## 0. 为什么需要这份指南

2026-06-14 在 `private-skills/book-ocr-manager` 上线每日 03:00
OCR 跑批任务时,观察到一个反复出现的浪费模式:

| 跑批阶段 | Agent 实际在干啥 | 实际需要吗 |
|---|---|---|
| 跑 `scan` / `plan-daily` / `run_ocr.py` | 调 shell 命令 | ❌ 纯命令,零判断 |
| 写回 SQLite | skill 内部自动 | ❌ 0 agent |
| 读 SQLite 数字写汇报 | 读 5-10 个数字 + 组织文字 | ✅ 轻 |
| **Agent 额外干的** | "先检查工作区结构"、"让我查看后端配置"、"让我读 run_ocr.py 取段逻辑"、"这是已知 bug 值得记忆"... | ❌ **强模型 debug 本能** |

**结论**:cron 任务的智能需求量,只配得上**最弱的模型 + 最死板的 prompt**。
其它都是浪费。

**核心洞察**(用户原话精炼):**"能跑完优先于省 token,但脚本鲁棒性
本身就让省 token 成为可能"**——这两者不矛盾,反而一致:脚本越
鲁棒(自描述退出码、自带错误处理、失败不靠 agent 兜),agent
介入越少,token 自然省。

---

## 1. 介入度三档(从激进到温和)

按"agent 在跑批中的参与度"分三档。**默认建议 L2**。

### L3 · 强模型 + 自由 prompt(最浪费)
- cron prompt 写"按 skill 内部流程跑当日批次"
- agent 自己决定:看 SKILL.md、查配置文件、debug 异常、读源码
- token 消耗:**最高**(几小时跑批 × 多次 LLM 推理)
- 适用:**只适用于探索性原型阶段**,等跑批稳定了**必须降到 L1/L2**

### L2 · 弱模型 + 死板 prompt(推荐)
- cron prompt 写死板指令:"跑 scripts/cron_daily.sh,把退出码 + SQLite 数字报给我,不要 debug、不要读源码、不要调查"
- 强约束:`Don't debug / Don't read source / Don't investigate`
- 换 Haiku 4.5 等弱模型(成本约强模型 1/12)
- token 消耗:**降 70-80%**
- 适用:**所有稳定运行的批量任务**(本指南的默认目标)

### L1 · 包装脚本 + 弱模型 + 自描述退出码(最优)
- 写一个 `scripts/cron_*.sh`(或 .py)包装脚本,一口气跑完所有步骤
- 脚本带**自描述退出码语义**(0=全成功 / 1=部分失败 / 2=配置错 / 3=额度满正常停 / 4=工具链错 / 127=命令未找到 / 124=超时)
- cron prompt:**只跑脚本 + 读退出码 + 读 SQLite 数字**,零判断
- 换最弱模型
- token 消耗:**降 80-90%**(agent 中间几小时完全 off)
- 适用:**最成熟的批量任务**,前提是脚本本身经过 `SKILL-ROBUSTNESS-AUDIT-GUIDE.md` 审计

---

## 2. L1 决策树(何时值得做包装脚本)

```
跑批耗时是否 > 5 分钟?
├── 否(快任务)→ L3 强模型足够,别过度优化
└── 是(慢任务,几小时)↓
    跑批步骤是否都是确定性 shell 命令?
    ├── 否(需要 LLM 决策)→ 保持 L2,别硬包装
    └── 是(纯命令流)↓
        脚本是否已通过 SKILL-ROBUSTNESS-AUDIT-GUIDE.md §3-§5 审计?
        ├── 否→ 先审计,再包装(否则会把 bug 也包进去)
        └── 是→ 做 L1(包装脚本 + 弱模型)
```

---

## 3. 包装脚本设计规范

### 3.1 退出码语义(对外契约)

cron agent 看包装脚本的退出码就够了,**不必读 stderr**。约定:

| 退出码 | 含义 | agent 应采取的动作 |
|---|---|---|
| 0 | 全部成功 | 汇报"今日 OK" |
| 1 | 部分失败(有段失败,可重试) | 汇报数字,不打扰用户 |
| 2 | 配置错 | 提示用户修 config |
| 3 | 额度满正常停(明早自动续) | 汇报"额度满,明早 03:00 续" |
| 4 | 工具链错(uv/Python 缺) | 提示用户装依赖 |
| 124 | 单段超时 | 报告+让人决定调超时 |
| 127 | 命令未找到 | 报告 skill 目录结构变了 |

**关键**:agent **根据退出码**决定动作,**不要让 agent 读 stderr 分析**(那是强模型的浪费动作)。

### 3.2 步骤隔离

- 每步单独判退出码,记到 LOG,继续跑(避免"plan 失败 → run_ocr 跑不了"的级联)
- 但**严重错**(配置/工具)直接 exit,不级联
- 例:`scan` 失败 → WARN 继续;`plan-daily` 退出码 2 → FATAL 停止;`run_ocr` 部分失败 → 退出码 1(允许)

### 3.3 路径含空格(Mac 默认)

bash 命令传路径**必须用数组**:

```bash
# ❌ 错(路径含空格时会被截断)
CONFIG="/path/with space/config.json"
python3 script.py --config $CONFIG

# ✅ 对(用数组)
CONFIG_ARR=(--config "$CONFIG")
python3 script.py "${CONFIG_ARR[@]}"
```

### 3.4 不动 skill 内部代码

包装脚本**只调公开 CLI**,不改 skill 内部任何文件:

```bash
# ✅ 对
python3 scripts/library_ocr_manager.py scan
python3 scripts/library_ocr_manager.py plan-daily --config "$CONFIG"
python3 scripts/run_ocr.py --config "$CONFIG"

# ❌ 错(直接调内部 lib.py,跳过了 CLI 公开契约)
python3 -c "from scripts.lib import ..."
```

### 3.5 日志落盘

- `state/logs/cron-{YYYYMMDD-HHMMSS}.log`
- 包含:每步输出 + 退出码 + 最终汇总
- agent 失败时可让人/别的 Agent 离线查日志

### 3.6 不要 set -e

```bash
# ❌ 错(任何步失败就全停,失去隔离)
set -eu

# ✅ 对(每步单独判退出码,业务失败可继续)
set -u  # 只留 -u,避免静默 typo
```

---

## 4. Cron Prompt 模板(L1 / L2)

### 4.1 L1 prompt(包装脚本版,推荐)

```text
进入 skill `private-skills/<skill-name>/`,跑当日批量任务:

1. `cd <skill-root> && bash scripts/cron_daily.sh` 一口气跑完所有步骤
2. 读退出码 + state/logs/cron-*.log 末 30 行 + SQLite 今日 events 数字
3. 简要回报:
   - 退出码
   - 今日 ocr_completed / ocr_failed 段数
   - SQLite 最新状态
   - 任何非零退出码的解释

约束(硬性,违反视为浪费 token):
- 不要 debug,不要读源码,不要调查失败原因
- 不要修改 skill 内部任何文件
- 不要重试(包装脚本的退出码已是最终判定)
- 失败即跳过,明早 03:00 自动重试,不发 IM 通知
```

### 4.2 L2 prompt(无包装脚本,弱模型版)

```text
进入 skill `private-skills/<skill-name>/`,按以下顺序跑命令:

1. `cd <skill-root>`
2. `python3 scripts/X.py scan`
3. `python3 scripts/X.py plan-daily`
4. `python3 scripts/X.py run`
5. 读 SQLite 数字写汇报

约束(硬性):
- 不要 debug,不要读源码,不要调查
- 不要修改 skill 内部任何文件
- 每步只看退出码,退出码 0 继续,非 0 报告
- 失败即跳过,明早 03:00 自动重试
```

### 4.3 L3 prompt(不推荐,仅探索阶段)

```text
进入 skill `private-skills/<skill-name>/`,按 skill 内部流程跑当日批次。
```

---

## 5. 模型选择

| 场景 | 推荐模型 | 理由 |
|---|---|---|
| L1 包装脚本 + 自描述退出码 | **Haiku 4.5** | 纯命令+数字读取,无需思考 |
| L2 弱 prompt + 确定性命令流 | **Haiku 4.5** | 同上 |
| L3 自由 prompt + 探索性 | Sonnet 4.6(默认) | 需要 debug/调查能力 |

**成本对比**(每 1M token):
- Sonnet 4.6:~$3 / $15(输入/输出)
- Haiku 4.5:~$0.25 / $1.25(约 1/12)
- 跑批省下 80% token × 弱模型 1/12 = **总成本降到 1-2%**

切模型命令:

```bash
myagents cron update cron_c3be280926b6 --model haiku
```

---

## 6. 案例:book-ocr-manager 的演进

### 阶段 1(2026-06-14 早期)
- L3 + Sonnet 自由 prompt
- 单次跑批 agent token 消耗极高,agent 干一堆 debug
- 撞出 5 个 bug(proxy / path / uv / include_planned / mdls)

### 阶段 2(2026-06-14 修复 5 bug 后)
- 仍 L3 + Sonnet
- 跑批能跑完,但 Sonnet 仍会"让我看看配置文件"浪费 token
- 跑批 414 段几小时,agent 中间纯等

### 阶段 3(本指南落地)
- L1:写 `scripts/cron_daily.sh`(见 3.x 设计)
- L1 退出码语义:0/1/2/3/4/124/127
- 换 Haiku 4.5
- prompt:"跑 cron_daily.sh,报退出码 + SQLite 数字,不要 debug"
- 预期:token 消耗降 80%+,跑批耗时不变(瓶颈在 PaddleOCR 服务端)

---

## 7. 验证清单(切换到 L1/L2 前)

发布新包装脚本 / 新 cron prompt 前过一遍:

```text
□ 包装脚本
  □ bash -n 语法通过
  □ 含完整退出码语义(0/1/2/3/4/124/127)
  □ 步骤隔离(set -u 而非 set -eu)
  □ 路径用数组传(避免空格截断)
  □ 不动 skill 内部代码
  □ 日志落盘到 state/logs/cron-*.log
  □ 与 SKILL-ROBUSTNESS-AUDIT-GUIDE.md §3-§5 各项对齐

□ Cron prompt
  □ 明确禁止 debug / 读源码 / 调查(强约束)
  □ 明确禁止修改 skill 内部文件
  □ 失败即跳过,明早自动重试(不发 IM 通知)
  □ agent 应做的动作明确(读退出码 + 读 SQLite 数字 + 写汇报)

□ 模型
  □ 已切到弱模型(haiku)
  □ 用 `myagents cron update --model haiku` 验证

□ 验证
  □ 手动跑一次 `bash scripts/cron_daily.sh`,退出码符合预期
  □ 手动跑一次 `myagents cron run-now`,agent 行为符合 prompt 约束
  □ 观察 2-3 天 cron 自动跑批,稳定
```

---

## 8. 反模式(千万别这么干)

### 8.1 "agent 替我 debug"
> 跑批失败,让 agent 去看 stderr、查配置、读源码

agent 是 LLM 不是 IDE——它"看"得慢、花 token、结论不可靠。**让包装脚本自己给清晰退出码**。

### 8.2 "prompt 写得详细点"
> "请先扫描、再计划、然后执行 OCR,每步记录到日志,最后汇报今日处理了多少书/段..."

prompt 越长,agent 越可能"自由发挥"。**短而死的 prompt 才省 token**。

### 8.3 "用强模型 + 死 prompt"
> 模型是 Sonnet,prompt 是死的

强模型会**违抗**死 prompt 去做"该做"的事(它觉得 debug 是该做的)。**模型 + prompt 要配套**:死 prompt 必配弱模型。

### 8.4 "包装脚本直接 inline 在 cron prompt 里"
> cron prompt 写:`scan && plan && run_ocr.py --config ... && tee log`

Agent 读 cron 时会"理解"这条命令,然后**自作主张**拆开。**逻辑必须在脚本里**,不在 prompt 里。

### 8.5 "退出码靠 stderr 关键字判断"
> "如果 stderr 包含 '429' 就算额度满"

agent 用 LLM 读 stderr 判断不可靠。**让脚本自己 exit 准确码**,agent 读码不读文本。

---

## 9. 关联文档

- [SKILL-DEV-GUIDE.md](SKILL-DEV-GUIDE.md) — Skill 文档结构与编写规范
- [SKILL-ROBUSTNESS-AUDIT-GUIDE.md](SKILL-ROBUSTNESS-AUDIT-GUIDE.md) — **必读**:包装脚本必须过此审计(§3-§5 命令自描述、失败语义、工具链依赖)
- [SKILL-ORCHESTRATION-GUIDE.md](SKILL-ORCHESTRATION-GUIDE.md) — 多 Skill 协作协议
- 案例:`private-skills/book-ocr-manager/scripts/cron_daily.sh`(本指南 L1 第一个落地)

---

## 10. 变更记录

- 2026-06-14 初版。从 `book-ocr-manager` 跑批 token 浪费观察 + 用户原话"能跑完优先于省 token,但脚本鲁棒性本身就让省 token 成为可能"精炼出三档介入度(L3/L2/L1)+ 包装脚本设计规范 + 退出码语义表 + 4 个反模式。所有进入"cron + skill 自动调用"场景的项目应参考本指南优化 token 消耗。
