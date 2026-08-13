# 经济型多模态审计协议

## 目录

- [定位](#定位)
- [准备审计包](#准备审计包)
- [弱模型档位](#弱模型档位)
- [视觉审计步骤](#视觉审计步骤)
- [输出合同](#输出合同)
- [应用审计结果](#应用审计结果)
- [失败边界](#失败边界)

## 定位

只在基础抽帧完成后使用视觉审计。视觉层只能对基础帧做减法，不能补回基础层从未保留的内容。不要把完整视频或全部候选帧提交给模型；先由 `prepare_vision_audit.py` 校验同页覆盖资格，再按风险与时间覆盖选出少量可执行组。命令中的输入必须是同时含 `_report.json` 与基础 JPG 的实际输出目录；仅含元数据的 Skill `archive/` 不能使用。

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
- `_vision_audit/contact_sheet_NNN.jpg`：同一风险组的目标张、通过本地校验的基础覆盖帧和必要上下文；若出现丢弃候选，也只能作为风险背景；
- 原始图片仍位于基础输出目录，manifest 用相对路径引用，不复制整段视频。

manifest 的 `budget.covered_time_buckets` 记录已覆盖的 30 秒时间桶，`ineligible_or_restore_groups_skipped` 作为兼容字段记录因无可靠覆盖或属于旧恢复题而跳过的组。只有近像素一致或重叠差异极低的滚动关系能进入 `allowed_coverage_audit_ids`；相同 App 外壳、时间相邻和普通布局相似均不够。没有合格题时生成 0 组是正常安全结果。

## 弱模型档位

视觉能力较弱、长提示遵循不稳定或 JSON 输出容易出错时运行：

```bash
uv run scripts/prepare_vision_audit.py \
  -i <基础输出目录> \
  --profile weak
```

weak 默认最多 6 组、18 张唯一图片，并额外生成：

- `review_template.json`：预填 `group_id`、唯一目标、任务类型和允许选项；
- `MODEL_INSTRUCTIONS.md`：可直接交给模型的短说明；
- 2 列大图联系表：红框为唯一目标，蓝框只作覆盖上下文，使用 A/B/C/D 标记。

一次只给模型一张联系表。不要要求模型同时审完整个总览。基础目标使用 `keep/drop/replace`，视觉层不恢复丢弃候选。模型只填写模板中的空值，覆盖帧从 `allowed_coverage_audit_ids` 选择，理由码按结果从 `reason_codes_by_outcome` 选择，不修改 ID、哈希或选项。把 `status` 改为 `completed` 时必须填写全部组；未审完就保留 `in_progress`，不得伪装完成。

weak 与 balanced 对改变基础结果使用同一组门禁：`confidence >= 0.90`、`coverage_audit_id` 来自模板核准清单、目标组存在本地风险、应用器重算原图覆盖资格、覆盖帧在最终精选结果中存活。任何一项不足，或存在覆盖链/覆盖环时，应用器记录 `safe_noop` 并维持基础帧。模型自报置信度不能单独触发删除。

## 视觉审计步骤

1. 读取 `audit_manifest.json`，确认 `status=prepared`，实际组数和图片数没有超过预算。
2. 按组查看联系表。不要孤立判断目标帧；同时比较 `previous / target / following` 和模板列出的本地核准覆盖帧。若联系表出现 `discarded_candidate`，只能帮助理解风险，不得把它选为恢复结果。优先处理 `loading_overlay`、`incomplete_page_risk`、`vertical_seam` 和 `mixed_transition_risk`。
3. 仅处理 manifest 内的 `audit_id`：
   - `keep`：承载新增信息，或虽相似但需要保持页面/证据连续性；
   - `drop`：明显切换中间态、视觉重复或语义重复，且相邻完整帧已经覆盖内容；
   - `replace`：目标帧应删除，但同组另一帧更完整清晰，用 `replacement_audit_id` 指向替代帧。
4. 对金额、身份、地址、承诺、关键对话、商品/账号主体和时间信息采取保守策略；不能确认已被相邻帧完整覆盖时使用 `keep`。
5. 只为需要改变基础结果或明确确认高风险帧的图片输出决策；没有决策的基础保留帧维持原状。
6. 不对 `discarded_candidate` 输出决定，也不手工添加 `restore` 选项；基础层漏掉的内容需要回到参数或代码层重跑，不能由多模态层补造。

weak 档位不直接编写下述 1.0 合同；填写自动生成的 `review_template.json`，把 `status` 改为 `completed` 后另存为基础输出目录下 `_vision_review.json`。不要改变 `schema_version=1.1` 和 `profile=weak`。

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
      "coverage_audit_id": "img-005",
      "reason_code": "transition",
      "reason": "左右各显示一部分页面，后一帧已完整显示目标页",
      "confidence": 0.97
    },
    {
      "audit_id": "img-009",
      "decision": "replace",
      "replacement_audit_id": "img-010",
      "coverage_audit_id": "img-010",
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
- `drop/replace` 未引用模板核准且本地重算仍合格的覆盖帧；
- `replace` 的替代帧与覆盖帧不一致；
- 覆盖帧同轮被删除/替换，或形成覆盖链、覆盖环；
- 删除/替换未达到 0.90、缺少本地风险时不执行变更，并记录为 `safe_noop`；
- 决策缺少理由或置信度；
- 审计会产生空精选集；
- `_curated/` 中含非本工具文件，存在覆盖风险。
