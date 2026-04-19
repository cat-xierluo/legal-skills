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

### [DEC-005] - 2026-04-19 - 单人 ONNX 使用全局标点恢复

**背景**
单人 `paraformer-onnx` 改为 VAD 分段后，剩余差异主要来自分段边界和标点恢复位置。逐段恢复标点会在短片段边界引入不自然断句，且每段都调用一次标点模型，速度也受影响。

**决策**
单人 `paraformer-onnx` 使用“VAD 分段 ASR + 文本拼接 + 全局标点恢复”的后处理；多人路径继续逐段标点恢复，以保留 speaker 对齐和句子到说话人的映射稳定性。

**理由**
5 分钟单人讲课样本上，全局标点恢复将实际路由稳态耗时从约 `17.508s` 降至约 `11.751s`，原始文本相似度从约 `0.9607` 提升至约 `0.9733`，去标点/空白相似度约 `0.9829`。继续测试 `max_end_sil=600/1000/1200` 和相邻 VAD 段合并均降低质量，默认 `800ms` 最稳。

**影响**
单人 ONNX 的输出格式更接近原生 `paraformer`，同时减少标点模型重复调用。多人 ONNX 行为不变。

### [DEC-006] - 2026-04-19 - ONNX 兼容导出依赖改为按需加载并显式校验私有 API

**背景**
PR #16 审查指出，`server.py` 模块级导入 `torch` 和 `funasr.utils.export_utils` 会让非 ONNX 路径也依赖 FunASR 内部导出模块；同时直接 patch `export_utils._onnx` 可能在 FunASR 内部 API 变化时静默失效。

**决策**
移除模块级导入，改为 `patch_funasr_onnx_export()` 首次执行时按需加载 `torch` 和 `funasr.utils.export_utils`；对 `_onnx` 做 `hasattr` 校验，不存在时直接抛出清晰错误。ONNX 兼容导出缓存增加 `compat_export_version`，导出逻辑变化时会重新生成缓存。

**理由**
这样可以隔离原生 `paraformer` 路径与 ONNX 导出内部依赖，避免非 ONNX 场景因 FunASR 内部模块路径变化失败；同时避免 monkey patch 静默失效。

**影响**
ONNX 首次兼容导出时会打印模型下载和缓存准备提示；已有旧 marker 的兼容缓存会因版本号缺失而重新导出一次。

## 工作日志

### 2026-04-19 15:39 (Codex)

- **目标:** 修复 PR #16 审查意见中的阻塞问题。
- **操作:** 将 `torch` / `funasr.utils.export_utils` 改为 ONNX 导出时按需加载；对 `export_utils._onnx` 增加存在性校验；补充模型下载提示、兼容缓存版本、VAD/token/time alignment 注释和文档说明；扩展中文标点切句。
- **结果:** 阻塞项 #1/#2 已修复，并处理 #3/#4/#6/#8/#9/#10 的低风险部分；#5 通过缓存版本与清理提示降低风险，未改为选择性复制模型文件以避免破坏 FunASR 导出依赖。
- **下一步:** 运行轻量检查后推送到 PR #16。

### 2026-04-19 15:20 (Codex)

- **目标:** 继续优化单人 `paraformer-onnx`，尽量接近多人 ONNX 已调优后的质量。
- **操作:** 对比 `preds`/`raw_tokens`、逐段/全局标点、padding、VAD 静音阈值和相邻段合并；实现单人路径全局标点恢复。
- **结果:** `preds + 全局标点 + VAD max_end_sil=800` 表现最佳；5 分钟样本稳态耗时约 `11.751s`，原始文本相似度约 `0.9733`，去标点/空白相似度约 `0.9829`。
- **下一步:** ONNX 剩余错字主要来自模型识别本身，后续更适合通过领域词表或转录后 AI 校对补强。

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
