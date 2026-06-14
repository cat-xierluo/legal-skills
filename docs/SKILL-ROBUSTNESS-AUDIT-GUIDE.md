# Skill 鲁棒性审计指南

> 面向「将被定时任务（cron）或无头 Agent 自动调用的 Skill」编写
> 的鲁棒性验收标准。本指南解决一个具体问题：**Skill 作者本人
> 跑没问题，但 cron / Agent 一调就崩**。

---

## 0. 为什么需要这份指南

2026-06-14 在 `private-skills/book-ocr-manager` 上线每日 03:00
OCR 跑批任务时，连环撞出 5 个隐藏 bug：

| 序号 | bug | 作者手跑 | cron 跑 |
|---|---|---|---|
| 1 | `run_ocr.py` 路径基线不一致 | 凑巧走对路径 | 跑批 0 产出 |
| 2 | 缺 `ocr.legal_ocr_root` 配置 | 凑巧配过 | 全军覆没 |
| 3 | `run_ocr.py` 默认不取 `planned` 段 | 凑巧传 `--include-planned` | 0 段真跑 |
| 4 | 内部用 `uv` 调 Python | 凑巧本机有 `uv` | 调 OCR 直接失败 |
| 5 | `find_legal_ocr_root` 抛 `Invalid port` | 凑巧没走到探测 | 死循环 5891 条失败事件 |

**根因共性**：所有这些 bug 都是「**作者脑子里的隐性知识没写进 skill**」。
作者手跑时，碰到问题会本能地"绕一下"，但无头 Agent 只按字面执行，
**会一直撞同一个错误直到超时**。

本指南把这类隐性知识**显式化**为硬性检测项。任何 Skill 在被
cron / Agent 调之前，必须通过本指南的所有审计项。

---

## 1. 审计对象分级

| 等级 | 触发场景 | 审计强度 |
|---|---|---|
| **L0 · 文档类 Skill** | 仅读 reference，无副作用 | 跳过本指南 |
| **L1 · 交互式 Skill** | 用户在 Claude Code 里调用 | 本指南 §2、§3 |
| **L2 · 半自动 Skill** | Agent 调用 + 用户偶尔介入 | 本指南 §2–§5 |
| **L3 · 全自动 Skill** | cron / 定时 / 无头触发 | **全章节必过** |

判定方法：skill 文档/CHANGELOG 里出现过 `cron` / `每日` / `定时` / `无人值守`
任一关键词的，**强制按 L3 审计**。

---

## 2. 路径与目录基线（5 项）

作者手跑时 `cd` 一次就绕过的问题，Agent 不会绕。

### 2.1 工作目录假设必须在 SKILL.md 显式声明

❌ 隐式（常见错误）：
> 按以下顺序执行命令：`scan` → `plan-daily` → `run_ocr.py`

✅ 显式：
> ⚠️ **所有命令必须从 skill 根目录执行**（即包含 `SKILL.md` 的目录）。
> 如果从其他目录跑，相对路径解析会错。

### 2.2 路径解析基线必须单一来源

❌ 多处各取各的基线：
```python
# library_ocr_manager.py
expand_path("state/library_ocr.sqlite3", base=script_root())   # 基线=skill 根
# run_ocr.py
resolve_db_path(...)                                            # 基线=config/
```

✅ 抽到 `scripts/lib.py` 一处：
```python
def resolve_db_path() -> Path:
    return (SKILL_ROOT / "state" / "library_ocr.sqlite3").resolve()
```
**所有**脚本调同一个函数。

### 2.3 路径不存在的失败语义必须显式

❌ 静默建空库：
```python
db = sqlite3.connect(db_path)   # 路径不存在会自动建空库
```

✅ 主动检查 + 清晰报错：
```python
if not db_path.exists():
    sys.exit(f"FATAL: DB not found at {db_path}. Run scan first.")
```

### 2.4 机器特定路径必须放 config，禁止硬编码

❌ 脚本里写：
```python
LEGAL_OCR_ROOT = Path("/Users/maoking/Library/.../legal-ocr")
```

✅ config 注入：
```python
legal_ocr_root = config["ocr"]["legal_ocr_root"]   # 必须从 config 读
```

### 2.5 状态库/SQLite 必须 `.gitignore`

`state/*.sqlite3`、`config/config.json` 这类**机器特定 + 易膨胀**
的产物必须明确排除入仓。

---

## 3. 命令自描述（4 项）

`--help` 是 Agent 唯一可靠的信息源。

### 3.1 每个 CLI 入口必须有完整 `--help`

至少包括：
- 命令功能一句话说明
- 必填参数 + 选填参数 + 类型
- **前置条件**（依赖什么、路径在哪、配置项是什么）
- **典型调用示例**（2-3 个，从最简到完整）
- 退出码语义（0=成功 / 1=业务失败 / 2=配置错 / ...）

### 3.2 默认值必须和文档描述一致

❌ 注释说"默认包含 planned"，代码里 `default=False`：
```python
parser.add_argument("--include-planned", action="store_true", default=False,
                    help="Include planned segments (default: True)")
# help 写错，default 也错，Agent 看不到
```

✅ 三处对齐：
```python
parser.add_argument("--include-planned", action="store_true", default=True,
                    help="Include planned segments (default: True)")
```

### 3.3 跨命令配合关系必须文档化

如果 `A` 命令产出物是 `B` 命令的输入，**两处都要写**：

- `A --help` 末尾加：`See also: B(1)`
- `B --help` 开头加：`Reads: output of A(1)`
- SKILL.md 标准流程图里用箭头标依赖

### 3.4 失败模式必须可识别

每条命令的失败，**退出码 + stderr 文案**都要能让 Agent / 日志系统
区分清楚：

| 退出码 | 含义 | Agent 应采取的动作 |
|---|---|---|
| 0 | 成功 | 继续 |
| 1 | 业务失败（OCR 调通但有 page 错误） | 记事件 + 跳过 + 明早重试 |
| 2 | 配置缺失（`legal_ocr_root` 未设） | 记 FATAL + **立刻退出**，不重试 |
| 3 | 工具链缺失（`uv` 未装） | 记 FATAL + 立刻退出 |
| 4 | 路径异常（库 / 状态文件不在） | 提示用户跑 doctor |

**绝不要"失败也 exit 0"**——Agent 看到 0 就以为成功，会污染数据。

---

## 4. 工具链依赖（3 项）

### 4.1 所有外部命令必须在 README 列出

格式：
```markdown
## 先决条件

- Python 3.10+
- [uv](https://github.com/astral-sh/uv)（`brew install uv`）
- 合法 `OCR_API_KEY`（在 `config/config.json` 的 `ocr.api_key` 配）
```

### 4.2 可配置优先于硬编码

❌ 硬假设 `uv`：
```python
subprocess.run(["uv", "run", "legal_ocr", ...])
```

✅ 可配置 + 兜底：
```python
python_invoker = config.get("ocr", {}).get("python_invoker", "python3")
subprocess.run([python_invoker, "legal_ocr", ...])
```
默认值给最常见的（`python3`），不假设用户的工具链偏好。

### 4.3 提供 `doctor` / `preflight` 自检子命令

每个有副作用的 skill 都应有一个 `--doctor` / `--preflight` 子命令，
一次性把所有"必须先有 / 必须先配"的项目扫一遍，给明确报告：

```bash
$ python3 scripts/library_ocr_manager.py doctor
✓ Skill root: /path/to/skill
✓ Config: /path/to/config.json (legal_ocr_root: ✓ / python_invoker: python3)
✓ DB: /path/to/state/library_ocr.sqlite3 (size 12MB, last updated 2h ago)
✗ Python invoker: 'uv' not in PATH (config says python_invoker=uv)
  → Run `brew install uv` OR set config ocr.python_invoker=python3
✓ legal_ocr_root: /path/to/legal-ocr (legit, has SKILL.md)
```

**Agent 在 cron 里第一件事就是跑 `doctor`，失败就立刻退、不进主流程**。

---

## 5. 重试与失败语义（3 项）

### 5.1 失败必须分类，**绝不能无脑重试**

| 失败类型 | 是否计入重试 | 重试次数 | 升级路径 |
|---|---|---|---|
| 业务失败（API 返 4xx 内容错） | ✅ | 3 | dead_letter |
| 限流（API 返 429） | ✅ 不计次 | 退避后无限 | 持续退避 |
| 工具链缺失（`uv` 没装） | ❌ | 0 | 立刻退出，提示用户 |
| 配置缺失（`legal_ocr_root` 没配） | ❌ | 0 | 立刻退出，提示用户 |
| 路径异常（DB 找不到） | ❌ | 0 | 提示跑 doctor |
| 未知错误 | ✅ | 1 | 一次失败后升级到 review |

### 5.2 重试必须有上限 + dead_letter

无上限重试 = 死循环。**每次失败必留下可追溯记录**：
- `events` 表新增一条 `event_type='ocr_failed'`
- 累计次数达上限 → 状态转 `dead_letter`
- 永远不要再进 retry 队列

### 5.3 退出码与日志必须能事后诊断

- 每次跑批写一份 `{stamp}-run.json` 到 `state/runs/`，含：开始/结束时间、命令、参数、退出码、stderr 摘要、事件计数
- 失败时 stderr 文案必须**自描述**（含失败类型 + 建议动作），不要只输出堆栈

---

## 6. cron / Agent 提示词模板（2 项）

### 6.1 cron prompt 必须**显式**写出关键约束

不要假设 Agent 知道这些。把 skill 文档里的"必须"项**逐条**列在 prompt 里：

```text
进入 skill `private-skills/book-ocr-manager/`，按以下流程执行：

1. 工作目录必须是 skill 根目录（包含 SKILL.md 的目录）
2. 先跑 `python3 scripts/library_ocr_manager.py doctor`，失败立即退出
3. 然后按顺序：`scan` → `plan-daily` → `run_ocr.py --include-planned`
4. 失败语义：
   - 工具链缺失（uv 未装）→ 立刻退出，不重试
   - 单本 OCR 失败 → 记事件、跳过、明早重试
   - 配置缺失 → 立刻退出，提示用户
5. 不要改 skill 内部任何文件
6. 跑完简要回报：处理了几本、失败了几本、SQLite 最新状态
```

### 6.2 跑批结果必须可被自动验证

cron 任务要有**自动验证关**，不能光看"exit 0"：

```text
完成标准（Agent 自查）：
- [ ] 跑批 exit code = 0
- [ ] SQLite events 表今日新增 N 条（N > 0 且 < 计划段数）
- [ ] 今日 ocr_failed 数量 < 失败阈值（如 < 计划段数 × 20%）
- [ ] 没有死循环特征（单条 segment 失败次数 < 3）
- [ ] private-skills/ 目录 git 干净（无意外修改）
```

**任一条件不满足 → 任务标 blocked，触发告警**。

---

## 7. 审计执行清单（Skill 作者自查用）

发布 / 上 cron 前，过一遍这张表：

```text
□ 路径与目录
  □ §2.1 工作目录要求写在 SKILL.md 顶部
  □ §2.2 路径解析基线统一（抽到 lib.py）
  □ §2.3 关键路径不存在时退出码 = 2 + 清晰文案
  □ §2.4 机器绝对路径都从 config 读
  □ §2.5 state/ + config/config.json 已 .gitignore

□ 命令自描述
  □ §3.1 每个 CLI 入口 --help 完整
  □ §3.2 默认值与 help 文案一致
  □ §3.3 跨命令依赖在两处 --help 都标
  □ §3.4 退出码 0/1/2/3/4 语义清晰，失败不伪装 0

□ 工具链依赖
  □ §4.1 README 有「先决条件」段
  □ §4.2 python_invoker 等外部工具可配置
  □ §4.3 有 doctor/preflight 自检子命令

□ 重试与失败
  □ §5.1 失败分类明确，配置/工具链错不重试
  □ §5.2 有 dead_letter 终态
  □ §5.3 跑批日志落盘可追溯

□ cron 接入
  □ §6.1 prompt 显式列所有"必须"
  □ §6.2 有自动验证关卡
```

---

## 8. 反模式（千万别这么写）

### 8.1 "作者视角" 文档
> "像往常一样先跑 scan 然后 plan"

Agent 不知道"像往常一样"是什么意思。

### 8.2 "工具替我兜底" 假设
> "如果 Python 找不到 OCR 包就用 uv"

Agent 不会主动装工具，只会报错。

### 8.3 失败时"多试几次"
```python
for i in range(10):
    try:
        do_ocr(...)
    except:
        continue   # 永远不会记录失败原因
```

### 8.4 配置项藏在 README 角落
用户搜不到、Agent 看 `--help` 看不到、失败时只提示"未找到 OCR 入口"。

---

## 9. 关联文档

- [SKILL-DEV-GUIDE.md](SKILL-DEV-GUIDE.md) — Skill 文档结构与编写规范
- [SKILL-EVALUATION-GUIDE.md](SKILL-EVALUATION-GUIDE.md) — Skill 质量验收
- [SKILL-ORCHESTRATION-GUIDE.md](SKILL-ORCHESTRATION-GUIDE.md) — 多 Skill 协作协议
- 案例：`private-skills/book-ocr-manager/TASKS.md` 5 个 bug 的修复记录

---

## 10. 变更记录

- 2026-06-14 初版。从 `book-ocr-manager` 上线 cron 任务时连环撞出的
  5 个 bug 中抽象出 15 项硬性审计标准（§2-§6）+ 1 张自查清单（§7）
  + 4 个反模式（§8）。所有进入「定时 / Agent 自动调用」场景的
  Skill 在发布前必须通过本指南审计。
