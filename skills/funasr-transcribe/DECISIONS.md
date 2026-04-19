# FunASR Transcribe 决策记录

## 决策记录

### [DEC-001] - 2026-04-19 - 单人和多人默认均回归 Paraformer

**背景**
实测中，`SenseVoice-Small ONNX` 在单人 15 分钟讲课样本与多人微信通话样本上都未体现速度或质量优势；原生 `paraformer --no-diarize` 在单人场景下速度和质量都更稳定。

**决策**
`fast` 参数不再自动切到 `SenseVoice`，仅关闭 diarization；默认模型仍保持 `paraformer`。`sensevoice` / `sensevoice-onnx` 继续保留为显式实验选项。

**理由**
这样可以避免用户以为“fast 一定更快”，同时保留未来继续评估 SenseVoice 的空间。

**影响**
CLI、API 文档和服务端路由语义均同步为“fast = 不分轨”，而不是“fast = SenseVoice”。

### [DEC-002] - 2026-04-19 - 多人 ONNX 优先修后处理而非继续盲目换模型参数

**背景**
调试 90 秒多人样本时发现，`paraformer-onnx` 原始输出中 `raw_tokens` 与 token 级时间戳可用，但 `preds` 被逐字空格化，且服务端直接把整段 VAD 当作单句输出。

**决策**
先在服务端补做三层后处理：优先根据 `raw_tokens` 重建文本、调用标点模型恢复标点、按补完标点后的句子重新映射时间戳。

**理由**
该方案直接修复已定位的劣化来源，避免把后处理问题误判为模型本身不可用。

**影响**
多人 ONNX 输出质量明显提升；完整 18 分 07 秒样本耗时从此前粗糙路径约 `211.52s` 增至 `272.443s`，但相比原生多人 `551.59s` 仍有约 `2.02x` 速度优势。

### [DEC-003] - 2026-04-19 - ONNX 默认文本源使用清理后的 preds

**背景**
继续调参时对比了 VAD 静音阈值、VAD 合并、片段 padding、整段 ASR 窗口和 ONNX 文本源。VAD 变大、合并窗口、整段窗口、padding 都会不同程度降低 90 秒多人样本质量。

**决策**
默认保留原 VAD 切段策略，ONNX 文本源从 `raw_tokens` 调整为清理后的 `preds`，并通过 `FUNASR_ONNX_TEXT_SOURCE=raw_tokens` 保留回退能力。

**理由**
在 90 秒多人样本上，清理后的 `preds` 相对普通 `paraformer` 的文本相似度约 `0.9974`，高于 `raw_tokens` 的约 `0.9911`；同时不会重新引入逐字空格问题。

**影响**
完整 18 分 07 秒多人样本耗时约 `291.332s`，约 `3.73x realtime`；相对原生多人 `551.59s` 仍约 `1.89x` 更快。

### [DEC-004] - 2026-04-19 - 单人 Paraformer ONNX 也使用 VAD 分段 ASR

**背景**
排查 5 分钟单人讲课样本时发现，旧单人 `paraformer-onnx` 路径直接整段调用 ONNX ASR，而多人 `paraformer-onnx + diarize` 路径会先使用 ONNX VAD 切段，再逐段 ASR、清理文本、恢复标点并重建句子级时间戳。整段 ONNX 在长音频上质量塌缩明显，且速度没有优势。

**决策**
新增共享的 `transcribe_paraformer_onnx_segments()`，让单人 `paraformer-onnx` 与多人 `paraformer-onnx + diarize` 复用同一套 ONNX VAD 分段 ASR 后处理；多人路径仅额外执行 CAM++ 说话人聚类。

**理由**
同一 5 分钟样本上，旧整段 ONNX 耗时约 `37.489s`，相对原生 `paraformer` 文本相似度约 `0.6079`；VAD 分段 ONNX 稳态耗时约 `17.508s`，去除标点/空白后的相似度约 `0.9829`。这说明核心问题是单人路由参数和后处理不足，而不是 ONNX 模型本身不适合单人场景。

**影响**
显式指定 `model=paraformer-onnx, diarize=false` 或在 `server-onnx.py` 默认 ONNX 服务中使用 `fast=true` 时，单人路径会走 VAD 分段 ASR，不再整段转录。`sensevoice` / `sensevoice-onnx` 仍保留原直接 ONNX 路径。

## 工作日志

### 2026-04-19 13:16 (Codex)

- **目标:** 排查单人 `paraformer-onnx` 是否缺少多人 ONNX 的参数和后处理调优。
- **操作:** 对比单人整段 ONNX、单人 VAD 分段 ONNX 与原生 Paraformer；将 `paraformer-onnx` 非 diarization 路由改为共享 ONNX VAD 分段 ASR；同步 SKILL、API 文档、任务和变更记录。
- **结果:** 5 分钟样本旧整段 ONNX 耗时约 `37.489s` 且相似度约 `0.6079`；改后实际路由稳态耗时约 `17.508s`，去标点/空白相似度约 `0.9829`。
- **下一步:** 如继续优化单人 ONNX，可优先补领域词表/AI 校对；不建议回到整段 ONNX 作为默认方案。

### 2026-04-19 00:55 (Codex)

- **目标:** 继续通过参数调优提升多人 ONNX 质量。
- **操作:** 对 90 秒样本测试 VAD 静音阈值、VAD 合并、长窗口、padding、`raw_tokens`/`preds` 文本源；将默认文本源改为清理后的 `preds`。
- **结果:** `preds` 文本源质量最佳；完整 18 分 07 秒样本耗时 `291.332s`，约 `3.73x realtime`。
- **下一步:** 如需继续提升语义准确率，优先考虑转录后 AI 校对或领域词表纠错，不建议通过加长 ONNX ASR 窗口作为默认方案。

### 2026-04-19 00:20 (Codex)

- **目标:** 排查并调参 `paraformer-onnx + diarize` 输出质量问题。
- **操作:** 修复 ONNX 兼容导出、VAD `feats_len` 兼容、`raw_tokens` 文本重建、标点恢复、句子级时间戳映射和中文拼接逻辑。
- **结果:** 90 秒样本输出从逐字空格恢复为可读句子；18 分 07 秒多人样本耗时 `272.443s`，约 `3.99x realtime`。
- **下一步:** 提交前再跑 CLI help 与短样本回归，并确认 PR diff 不包含无关 skill 改动。
