# Skill Portrait 与 Chain Graph

## 文件分层

| 文件 | 生产者 | 内容 | 是否调用 LLM |
|------|--------|------|--------------|
| `runtime/skill-inventory.json` | `refresh_skill_inventory.py` | 规范 Skill 索引与内容指纹 | 否 |
| `runtime/skill-portraits.json` | `distill_skill_portrait.py` | core/enhanced 功能画像 | 可选 |
| `runtime/skill-chain-graph.json` | `distill_skill_portrait.py` | Skill 依赖与可衔接关系 | 可选 |
| `runtime/enhance-requests.jsonl` | 消费者追加 | 按需增强画像请求 | 否 |

基础 inventory 刷新不得写入或覆盖 portrait/graph。消费者按各文件的 schema version 和 stable skill key 连接数据。

## Portrait

核心画像建议字段：

```json
{
  "skill_key": "<stable-key>",
  "content_hash": "<sha256>",
  "core": {
    "capability": "动词 + 对象 + 产出",
    "inputs": [],
    "outputs": [],
    "depends_on": [],
    "can_chain_to": [],
    "not_for": []
  },
  "enhanced": {
    "distilled_at": 1719000000,
    "triggers": ["侵权比对", "实质性相似"],
    "field_metadata": {
      "triggers": {
        "content_hash": "<sha256>",
        "distilled_at": 1719000000
      }
    }
  }
}
```

只在 inventory 的内容指纹变化、画像缺失或显式 `--force` 时重蒸馏。失败时保留上次有效画像并记录失败状态，不写半成品。

## Enhanced Portrait

增强画像只对消费者明确请求的少量 Skill 生成，可包含：

- 可复用 references/templates/scripts；
- workflow/reference 完整度；
- 扩展点；
- 精确触发词。

请求按 stable skill key 去重，并记录 fulfilled/failed 状态。不要为了“全量完整”高成本重跑所有 Skill。

增强值继续使用扁平字段，`field_metadata` 为每个字段分别记录其来源 `content_hash` 与蒸馏时间。多个不相交请求逐字段合并，不覆盖未请求字段。消费者只读取 `content_hash` 与当前 inventory 一致且时间有效的字段；没有哈希元数据的旧字段保留在运行数据中，但不作为当前事实暴露。增强层调用失败只记录诊断，不改变仍有效的 core `stale` 状态。

## Chain Graph

链路图至少包含：

- schema version 与生成时间；
- 节点 stable skill key；
- 有方向的 `depends_on` / `can_chain_to` 边；
- 边的来源与置信度；
- 无法确认时的待观察状态。

```
lawyer-ip-positioning ──produces_for(positioning.yaml)──→ lawyer-ip-planner
lawyer-ip-os ──dispatches_to──→ lawyer-ip-planner / lawyer-ip-positioning
lawyer-video-script-writer ──produces_for(brief)──→ lawyer-video-production
```

edge `kind` 枚举:

| kind | 含义 | 例子 |
|---|---|---|
| `produces_for` | A 产出被 B 消费(契约文件/artifact) | positioning→planner via `positioning.yaml` |
| `dispatches_to` | A 调度/路由 B | lawyer-ip-os→lawyer-ip-planner |
| `depends_on` | A 运行依赖 B 的能力 | eval-harness→multi-agent-orchestration |
| `complements` | A 与 B 互补衔接,无强依赖 | legal-ocr→legal-text-format |

**交叉对账**:A 的 `core.can_chain_to` 含 B,但 B 的 `core.depends_on` 没声明被 A 消费——补一条 B→A 的反向 `complements` 边,`evidence` 标"单方声明,待核"。给协同迭代识别真实链路用。
只从明确正文或经过交叉核对的画像建立边，不凭名称相似臆测依赖。发现循环时标记并保留诊断，不把图伪装成 DAG。

## 命令

确定性降级检查：

```bash
python3 scripts/distill_skill_portrait.py distill --no-llm
```

低频增量蒸馏：

```bash
python3 scripts/distill_skill_portrait.py distill --limit 24
```

`--limit` 只在筛出画像缺失、内容哈希变化、标记 stale 或显式强制的目标后应用，并按 `last_attempt_at` 从最久未尝试到最近尝试排序；不要先截断 inventory，也不要让持续失败的固定前缀让后续待刷新 Skill 长期饥饿。

默认成本边界为：`haiku`、单次调用最多 `$0.10`、核心层与增强层合计最多 24 次、按单次上限预留的整批预算最多 `$2.40`。直接 CLI 同时限制单次预算硬上限 `$5.00`、整批预算硬上限 `$100.00`，且单次预算不得大于整批预算。需要更严格控制时显式传入：

```bash
python3 scripts/distill_skill_portrait.py distill \
  --limit 12 \
  --model haiku \
  --max-budget-usd 0.08 \
  --max-calls 12 \
  --max-total-budget-usd 0.96
```

预算按每次调用上限预留，而不是等调用结束后猜测实际费用。CLI 缺失、全部目标失败、锁冲突或预算耗尽时返回非零状态；core 蒸馏失败时保留上次有效画像并标记其内容新鲜度，enhanced/fulfill 失败只记录字段级诊断，不把仍与当前内容匹配的 core 标为 stale，也不用空对象覆盖既有字段。

消费增强请求：

```bash
python3 scripts/distill_skill_portrait.py fulfill
```

画像属于运行数据，统一写入外部数据根，不提交个人扫描结果。
