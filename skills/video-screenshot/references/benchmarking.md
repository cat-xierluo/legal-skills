# 私有语料基线评测

本流程用于比较 `video-screenshot` 的算法版本或参数，不是日常抽帧必经步骤。目标是先冻结候选外人工标注，再让纯视觉与 RapidOCR 两条路径使用同一份 manifest，避免用“帧数更少”冒充准确率提升。

## 隐私边界

- manifest、视频、基础帧、`_report.json` 和 workspace 必须放在 Git 仓库之外；CLI 会拒绝仓库内路径。
- manifest 只使用 `CASE-001` 这类匿名编号，不写主体名、平台账号、案号或材料标题。
- `benchmark_summary.json` 不保存源路径、OCR 原文、标注时间点或帧文件名，可以在人工复核后摘录其中的匿名指标。
- workspace 内的基础 `_report.json` 仍是私有运行产物，可能含本机源路径，不得提交或外发。

## 1. 生成并填写 manifest

```bash
uv run scripts/benchmark.py init \
  --output /绝对路径/私有评测/manifest.json
```

在观看原视频后、运行待评算法前，冻结以下候选外标注：

- `must_keep`：每个区间代表一张必须被基础层覆盖的独立页面或证据状态；命中任一帧即算覆盖。
- `transitions`：明显处于前后页切换、加载或拼接过程的区间；保留帧落入其中计为过渡泄漏。
- `page_windows`：同一稳定页面或同一可接受内容窗口；超过 `max_selected` 的部分计为重复超额。
- `budget`：每分钟最大帧数和单次最大耗时；它只是密度/成本上限，不能覆盖必须保留页召回。

成功样本至少要有一个 `must_keep`。损坏视频使用 `expected_outcome: failure`，用于检查失败路径；不要为它伪造内容标注。

支持的匿名类别为：`xiaohongshu`、`wechat_chat`、`product_work`、`qualification_document`、`long_scroll`、`short_video`、`damaged_video`。正式基线至少覆盖五种成功页面形态，并同时运行 `visual`、`ocr`。

```bash
uv run scripts/benchmark.py validate \
  --manifest /绝对路径/私有评测/manifest.json \
  --check-files
```

## 2. 运行双路径基线

```bash
uv run --with rapidocr-onnxruntime scripts/benchmark.py run \
  --manifest /绝对路径/私有评测/manifest.json \
  --workspace /绝对路径/私有评测/workspace \
  --profiles visual,ocr
```

workspace 首次运行会写入所有权标记并绑定 manifest SHA256。后续重跑仅接受同一 manifest；标注发生变化时使用新 workspace，避免把不同口径的结果混为一轮。

OCR 环境缺失或抽帧器降级到纯视觉时，`ocr` profile 标记为 `failed_profile_downgrade`，不得冒充 OCR 基线。中断后可重跑，状态按 `CASE/profile` 原子写回。

只重新计算已有结果时运行：

```bash
uv run scripts/benchmark.py score \
  --manifest /绝对路径/私有评测/manifest.json \
  --workspace /绝对路径/私有评测/workspace
```

## 3. 指标与结论边界

汇总指标包括：

- `must_keep_recall`：必须保留区间命中数 ÷ 必须保留区间总数，优先级最高；
- `transition_leakage_rate`：落入过渡区间的保留帧数 ÷ 保留帧总数；
- `duplicate_excess_rate`：超过同页 `max_selected` 的帧数 ÷ 保留帧总数；
- `frames_per_minute`、`runtime_seconds`：人工筛选密度和计算成本；
- `ocr_minus_visual`：OCR 相对纯视觉的同口径差值。

`real_baseline_status=verified` 只表示：类别数量、候选外标注、要求的 profile 和损坏视频合同均已跑齐。它不表示算法表现优秀，也不允许单独宣称准确率提升。后续候选算法必须使用相同 manifest 和标注，先证明 `must_keep_recall` 不下降，再比较过渡泄漏、重复、密度与耗时。

合成视频回归只能证明 CLI、计分公式和脱敏边界可运行；不能替代真实微信、小红书、商品/作品、资质/文书和长滚动样本。
