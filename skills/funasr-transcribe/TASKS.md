# FunASR Transcribe 任务清单

## 当前目标

- [x] 基于 issue 14 增加 `paraformer-onnx` 路由与 ONNX 服务入口
- [x] 修复 `auto_transcribe.py` 自动启动服务时的 API 地址传递问题
- [x] 验证单人场景下 `SenseVoice` 与 `paraformer` 的速度和质量差异
- [x] 将 `fast` 语义调整为仅关闭 diarization，默认保留 `paraformer`
- [x] 调参与修复多人 `paraformer-onnx + diarize` 输出质量，补齐文本重建、标点恢复和句子级时间戳
- [x] 对多人 ONNX 参数进行 90 秒样本对比，确定默认保留 VAD 切段并改用清理后的 `preds` 文本源

## 后续待办

- [ ] 如继续保留 `sensevoice`，需另找真正适配的短语音样本重新评估其使用边界
- [ ] 如需发布 PR，提交前再跑一次 `transcribe.py --help`、`auto_transcribe.py --help` 与短样本回归
