# 任务、成果与效果复核

使用现有任务源记录输入版本、验收条件和任务ID。观察中的session_ref/project_ref是摘要标识，不能靠标题自动猜任务归属。必要时由用户或可信任务记录明确关联；一个任务可含多个会话，同一份请求不可分摊两次。

**以下命令在 Skill 目录内执行，`scripts/`、`config/`、`state/` 均相对该目录。**

## 输入

```json
{
  "schema": "magpie-outcomes.v1",
  "records": [{
    "task_id": "task-before-1",
    "comparison_key": "same-input-class-and-acceptance",
    "stage": "before",
    "observation": "<skill-dir>/state/observation.json",
    "sessions": ["session_ref_from_observation"],
    "artifact": "<skill-dir>/state/actual-output.md",
    "acceptance": "<skill-dir>/state/acceptance.json",
    "rework_count": 0,
    "human_minutes": 10
  }]
}
```

验收文件：

```json
{
  "schema": "magpie-acceptance.v1",
  "task_id": "task-before-1",
  "artifact_sha256": "hash-of-current-artifact",
  "accepted": true,
  "reviewed_by": "named-reviewer",
  "criteria": ["来源正确且关键项完整"]
}
```

具名评审负责内容质量；工具检查真实文件与验收哈希，不能把生产者随便写的accepted当独立语义证明。验收材料应来自已有审查/用户认可过程，不为凑对比自动签发。用户选择的comparison_key声明任务类别与验收可比性，脚本不证明任务同难度。

## 复核

```sh
python3 scripts/magpie_outcomes.py --manifest state/outcomes.json --output state/review.json
```

必须是完整分页观察且能匹配全部会话。实际文件变化、未绑定验收、重复请求分摊均拒绝。缺before/after或质量未通过输出INSUFFICIENT_EVIDENCE，不补默认“省钱”。before/after都有通过证据时，按每份验收成果比较调用数、非缓存输入、输出、缓存读取、累计请求耗时、返工、人工时间与完整已定价估算。价格缺失保持null，不把目录价当账单；累计请求耗时不等于并发任务墙钟时间。

输出DESCRIPTIVE_COMPARISON只描述观测差异，causal_improvement_proven始终为false。扩展多项任务、明确能力/质量底线，检查输入难度、人工介入、平台和模型变动等混杂因素后，才能形成有限个人建议；不自动推广成全局最佳模型。

现有经验库或任务账本保存结论及证据引用、适用任务、版本、窗口、样本量与重新评估条件。本Skill不另建竞争性任务数据库，不自动关闭业务任务。
