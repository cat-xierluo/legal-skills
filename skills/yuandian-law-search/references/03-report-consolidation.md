## 法律检索报告（consolidate）

多次检索之后，把 per-call 报告汇总成一份完整的法律检索报告。**这是律师/客户看的交付物**，per-call 报告是数据底稿。

### 7 节"结论先行"标准结构

报告骨架（7 节结构、设计动机、反例、节号逻辑）见：

[`00-report-design-notes.md`](00-report-design-notes.md)

调用 consolidate 时使用该骨架作为输出格式约定。

### 调用方式

```bash
scripts/yd-run consolidate \
    --title "张某买卖合同违约金调整" \
    --project "case-2024-zhangsan" \
    --case "案情：..." \
    --strategy "检索思路：..." \
    --analysis "分析与判断：..." \
    --conclusion "一句话结论：..." \
    --risks "主要风险：..." \
    --next-actions "后续行动：..." \
    --include "违约金,高空抛物"
```

- `--case` / `--strategy` / `--analysis` 必填：AI 显式传本次任务的案情/思路/判断
- `--include` 必填：逗号分隔的查询子串，明确指定"本次任务范围"（不取最近 N 条）
  - 匹配规则：CWD 中所有符合 `<8位时间戳>_<6位时间戳>_<查询>.md` 命名的 .md 文件，文件名包含任一子串即被纳入
- `--project` 可选：项目子目录名。默认从 `--title` slugify（如 "张某买卖合同违约金调整" → "张某买卖合同违约金调整"）。用于 `archive/<project>/` 归类
- `--title` / `--purpose` / `--conclusion` / `--risks` / `--next-actions` / `--output` 可选
  - `--purpose` 不传则基于检索词自动生成
  - `--conclusion` 强烈建议传入；不传会在 3.1 保留补写提示
  - `--risks` / `--next-actions` 不传会保留补写提示
  - `--output` 默认同时写 CWD 和 `archive/<project>/`；指定则只写到指定路径

### 项目子目录组织

consolidate 会把这次任务的所有文件归类到 `archive/<project>/` 子目录：

```
archive/
  case-2024-zhangsan/
    20260610_192031_货款逾期违约金_司法实践.json   ← 从 archive/ 根目录移入
    20260610_192031_货款逾期违约金_司法实践.md    ← 从 CWD 复制
    20260610_192032_逾期付款_违约金_调整.json
    20260610_192032_逾期付款_违约金_调整.md
    20260610_192058_法律检索报告.md                ← 主交付物
```

- **.md 复制**（CWD 保留工作副本）：用户的工作目录不被破坏
- **.json 移动**（archive 根目录已清理）：避免根目录重复积累，扁平区只放"in-flight 暂存"
- 重复运行 consolidate 同一项目：idempotent，文件已在子目录则跳过

### 与 per-call 报告的关系

```
多次 yd-run 检索（自动写 per-call .md 到 archive + CWD）
       ↓
AI 汇总判断后调 consolidate --project "case-x"
       ↓
创建 archive/case-x/，.md 复制进来，.json 移进来，法律检索报告写进去
       ↓
CWD 也有法律检索报告副本，per-call .md 仍在 CWD（工作副本）
       ↓
报告末尾的"检索明细表"链接回 archive/case-x/ 里的副本
```

per-call .md 是数据底稿，可独立查看；session 报告是主交付物，附案情/思路/判断；项目子目录是组织容器。

## 目标目录归档规范（强制）

**用户的目标目录（通常是案件文件夹 `02 - 案件分析` / `03 - 法律研究` 等）≠ AI 进程的 CWD**。AI 进程运行 `scripts/yd-run` 时所在的 CWD 是临时工作区，**不是**用户的案件文件夹。

### 目标目录只放什么

目标目录（用户指定的文件夹）只允许出现以下文件：

1. **整合后的法律检索报告**（`法律检索报告.md`，7 节标准结构）—— **唯一必需**
2. **外部素材**：用户单独提供的微信文章、PDF、链接笔记等
3. **基于整合报告再生成的下游文件**：证据清单、代理词大纲、抗辩应对清单、应诉策略等

### 目标目录不允许出现

- ❌ per-call 检索记录（`<ts>_<query>.md` × N 份）
- ❌ 检索明细 JSON
- ❌ 任何中间过程的临时文件
- ❌ AI 进程 CWD 下的 per-call 工作副本

### 标准工作流

```
Step 1：AI 在自己的 CWD 多次 yd-run 检索
        → archive/<ts>_<query>.json + .md（skill 内部）
        → <CWD>/<ts>_<query>.md（AI 进程工作副本，仅供 AI 读）

Step 2：AI 汇总判断后，**手动**写一份整合报告到目标目录
        → <用户目标目录>/<日期>_<主题>-法律检索报告.md

Step 3：清理 AI 进程 CWD 下的 per-call 工作副本
        → 不复制到目标目录
        → 仍可在 archive/<ts>_<query>.md 留底

Step 4：用户后续若要"基于检索结果生成证据清单/代理词"
        → 读取整合报告（含检索明细表），生成新文件
        → 新文件**也只放目标目录**，不污染 archive
```

### 反例（曾发生过的错误）

```bash
# ❌ 错误：把 8 份 per-call 工作副本复制到目标目录
cp /Users/.../yuandian-law-search/20260615_163256_*.md \
   "/案件文件夹/03 - 法律研究/"
# → 用户被迫手工清理，因为目标目录被检索底稿污染
```

正确做法：

```bash
# ✅ 正确：只把整合报告写到目标目录
# 整合报告由 AI 在对话中直接 Write 到目标目录
# per-call 工作副本留在 skill 内部 archive/
```

### 验证清单

AI 完成法律检索任务后，自查：

- [ ] 目标目录里**只有**整合报告 + 外部素材 + 下游生成文件
- [ ] 目标目录里**没有** per-call `<ts>_<query>.md` × N
- [ ] per-call 报告可在 `archive/` 里查到（不丢数据）
- [ ] 整合报告末尾的"检索明细表"指向 `archive/` 路径（而非 CWD 路径）
