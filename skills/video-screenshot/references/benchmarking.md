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

填写 `corpus_kind`：`real` 表示人工声明真实材料，`synthetic` 表示合成回归，`unconfirmed` 表示来源未确认（模板默认值）。脚本不凭类别名称推断素材真实；即使声明 real 并跑齐也仍需人工复核。`must_keep` 与 `transitions` 不得重叠，`page_windows` 之间不得重叠或共用端点，所有区间不得超过视频时长。未标注的过渡/重复内容不在代理指标的检出范围内。

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

workspace 首次运行会写入所有权标记并绑定 manifest SHA256；state 另绑定实现/配置摘要与源视频、报告及实际帧哈希。标注、视频或实现变化时使用新 workspace，避免不同口径结果混算。仅重新计分也会复算真实帧；图片缺失、改动或 profile 不匹配时失败关闭，不复用旧分数。

OCR 环境缺失或抽帧器降级到纯视觉时，`ocr` profile 标记为 `failed_profile_downgrade`，不得冒充 OCR 基线。中断后可重跑，状态按 `CASE/profile` 原子写回。

每次运行写入独立的 case/profile 尝试目录，不覆盖旧基础帧；开始前写入 running 状态，中断不会冒用上一轮成功状态。单次子进程受 `max_runtime_seconds` 超时约束；损坏视频必须同时得到独立 ffprobe 拒绝与抽帧器明确的媒体探测错误，依赖异常不算预期成功。旧尝试保留在私有 workspace，需人工按保管要求清理；工具不自动删除。

同一 workspace 按串行使用，不支持多个进程同时写入；并行比较不同算法时分别指定独立 workspace。macOS/Linux 下抽帧器在独立进程组中运行，超时同时终止它及其 ffmpeg 子进程；异常尝试可能留下私有 staging，不能作为成功产物使用。

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

差值只计算两条路径都成功的配对样本，并列出配对匿名 ID；逐类汇总同时显示实际已计分数量，缺项不当作零误差。区间边界按闭区间计分，零保留帧的泄漏率按 0 记，但召回仍为 0，不能据此认为质量合格。

`baseline_complete` 只表示 manifest 自定的数量/profile 条件已跑齐，不表示质量通过。只有人工声明 real、小红书/微信聊天/商品作品/资质文书/长滚动五类齐备且全部 visual/OCR 跑齐，才标记 `real_baseline_status=recorded_requires_human_review`；不输出自动 verified。短视频与损坏视频用于额外的边界矩阵。`accuracy_improvement_claim_allowed` 始终为 false。后续候选算法必须复用同一 manifest 与标注，先证明召回不下降，再比较泄漏、重复、密度和耗时；这些是标注代理指标，不是法律证据价值、证明力或全面 precision。

默认汇总在自有 workspace 中更新。显式 `--public-report` 只允许在仓库和 workspace 外新建文件，不覆盖任何既有文件；视频/manifest/workspace/报告路径及其非系统父目录符号链接均拒绝。汇总仅适合人工复核后摘录，匿名样本组合、时长和指标仍可能构成元数据指纹，不应未经判断直接公开整份报告。

合成视频回归只能证明 CLI、计分公式和脱敏边界可运行；不能替代真实微信、小红书、商品/作品、资质/文书和长滚动样本。

开发验证：`python3 scripts/check_pipeline.py --case all` 运行不依赖 OCR 的 24 组回归；已配置 Pillow/RapidOCR 的同一解释器另运行 `python3 scripts/check_pipeline.py --case benchmark-ocr`。必须以实际 CLI 结果确认 OCR，而非仅检查包能否 import；旧 PyYAML 与新版 Python 的组合可能导入成功、初始化失败。缺依赖时使用上述 uv 安装入口，不在脚本中补装或全局修补第三方模块。
