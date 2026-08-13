# 经济型多模态审计协议

## 目录

- [定位](#定位)
- [准备审计包](#准备审计包)
- [视觉审计步骤](#视觉审计步骤)
- [输出合同](#输出合同)
- [应用审计结果](#应用审计结果)
- [失败边界](#失败边界)

## 定位

只在基础抽帧完成后使用视觉审计。不要把完整视频或全部候选帧提交给模型；先由 `prepare_vision_audit.py` 按风险与时间覆盖联合选出低置信、疑似拼接过渡、未加载风险或相邻过密的少量组。

纯文字模型必须停止在“审计包已准备但未审计”，不要根据文件名猜测图片内容，也不要生成伪造的 `_vision_review.json`。

## 准备审计包

```bash
uv run scripts/prepare_vision_audit.py \
  -i <基础输出目录> \
  --max-groups 8 \
  --max-images 24
```

输出：

- `_vision_audit/audit_manifest.json`：受预算约束的图片清单、SHA256、时间戳、分组关系和决策合同；
- `_vision_audit/contact_sheet_NNN.jpg`：同一风险组的前一张、目标张、后一张和可选丢弃候选；
- 原始图片仍位于基础输出目录，manifest 用相对路径引用，不复制整段视频。

manifest 的 `budget.covered_time_buckets` 记录已覆盖的 30 秒时间桶。脚本会给远离已选时间段的高风险组有限加分，避免多个近邻组重复消耗预算；风险仍是首要因素，时间多样性不改变基础帧。

## 视觉审计步骤

1. 读取 `audit_manifest.json`，确认 `status=prepared`，实际组数和图片数没有超过预算。
2. 按组查看联系表。不要孤立判断目标帧；同时比较 `previous / target / following / discarded_candidate`。优先处理 `loading_overlay`、`incomplete_page_risk`、`vertical_seam` 和 `mixed_transition_risk`。
3. 仅处理 manifest 内的 `audit_id`：
   - `keep`：承载新增信息，或虽相似但需要保持页面/证据连续性；
   - `drop`：明显切换中间态、视觉重复或语义重复，且相邻完整帧已经覆盖内容；
   - `replace`：目标帧应删除，但同组另一帧更完整清晰，用 `replacement_audit_id` 指向替代帧。
4. 对金额、身份、地址、承诺、关键对话、商品/账号主体和时间信息采取保守策略；不能确认已被相邻帧完整覆盖时使用 `keep`。
5. 只为需要改变基础结果或明确确认高风险帧的图片输出决策；没有决策的基础保留帧维持原状。
6. `discarded_candidate` 已不在基础结果中，只能用 `keep` 明确补回；不要对它使用无实际作用的 `drop` 或 `replace`。

## 输出合同

把结果保存为基础输出目录下的 `_vision_review.json`：

```json
{
  "schema_version": "1.0",
  "status": "completed",
  "source_manifest_sha256": "<audit_manifest.json 的 SHA256>",
  "decisions": [
    {
      "audit_id": "img-004",
      "decision": "drop",
      "reason_code": "transition",
      "reason": "左右各显示一部分页面，后一帧已完整显示目标页",
      "confidence": 0.97
    },
    {
      "audit_id": "img-009",
      "decision": "replace",
      "replacement_audit_id": "img-010",
      "reason_code": "clearer_replacement",
      "reason": "替代帧文字更清晰且覆盖同一页面全部内容",
      "confidence": 0.91
    }
  ]
}
```

`reason_code` 只允许：`transition`、`visual_duplicate`、`semantic_duplicate`、`new_evidence`、`clearer_replacement`、`other`。每条决策必须有具体理由和 0—1 置信度。

## 应用审计结果

```bash
python3 scripts/apply_vision_review.py \
  -i <基础输出目录> \
  -r <基础输出目录>/_vision_review.json
```

脚本先复算基础报告、manifest 和每张图片的 SHA256，再生成：

- `_curated/curated_NNN_MMmSSs.jpg`；
- `_curated/_curated_report.json`，记录基础报告、manifest、视觉结果的哈希以及每张精选帧的来源。

该步骤不删除、不改名、不覆盖基础 `frame_*.jpg`。

## 失败边界

出现以下任一情况时拒绝应用审计：

- 审计结果未绑定当前 manifest；
- 引用 manifest 外 `audit_id` 或非法相对路径；
- 图片与报告 SHA256 不一致；
- `replace` 未指向另一个 manifest 内图片；
- 决策缺少理由或置信度；
- 审计会产生空精选集；
- `_curated/` 中含非本工具文件，存在覆盖风险。
