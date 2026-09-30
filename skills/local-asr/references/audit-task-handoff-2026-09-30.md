# 独立审计任务交接（2026-09-30）

本文件只保存脱敏的待办交接。现有本地 TASKS.md 由忽略规则保护，接手者先核对并去重导入，不覆盖其历史。本次不修改运行源码，不表示问题已修复。基线 8c529516db1a5ad80c525593a0e162ef7a5751ad。

### L6 / P2：align_words 重跑失败保留旧 words，和 fail-closed 合同相反

证据：[align_words.py L276-L311](https://github.com/cat-xierluo/legal-skills/blob/8c529516db1a5ad80c525593a0e162ef7a5751ad/skills/local-asr/scripts/align_words.py#L276-L311)；[L329-L349](https://github.com/cat-xierluo/legal-skills/blob/8c529516db1a5ad80c525593a0e162ef7a5751ad/skills/local-asr/scripts/align_words.py#L329-L349)；[SKILL L687-L689](https://github.com/cat-xierluo/legal-skills/blob/8c529516db1a5ad80c525593a0e162ef7a5751ad/skills/local-asr/SKILL.md#L687-L689)

深拷贝输入后，识别失败/低相似度/无效时间等分支直接 continue，未清除已有 words。无模型合成入口测试：输入段1带旧 words、段2不带；stub识别使段1 sim=0、段2成功。输出 rc0、available=true、aligned_segments=1，警告声称段1“words 缺省”，但段1旧 words 原封不动保留。下游按 words 存在消费时会接收未通过本次对齐的旧精确边界。修复应明确替换/保留来源策略，默认失败段不提供当前可信 words，同时清理或更新旧告警。

### L7 / P2：承诺接受火山 utterances，实际把毫秒当秒切片

证据：[align_words.py L92-L109](https://github.com/cat-xierluo/legal-skills/blob/8c529516db1a5ad80c525593a0e162ef7a5751ad/skills/local-asr/scripts/align_words.py#L92-L109)；[切片 L291-L296](https://github.com/cat-xierluo/legal-skills/blob/8c529516db1a5ad80c525593a0e162ef7a5751ad/skills/local-asr/scripts/align_words.py#L291-L296)；[公开合同 L687](https://github.com/cat-xierluo/legal-skills/blob/8c529516db1a5ad80c525593a0e162ef7a5751ad/skills/local-asr/SKILL.md#L687)

Volcengine 官方定义 utterance start_time/end_time 为毫秒：[API 文档](https://docs.volcengine.com/docs/DoubaoVoice/LargemodelrecordingfilerecognitionstandardversionAPI?lang=en)。_iter_segments 对 result.utterances 与 cut segments 同样 float() 不做单位变换。实际函数输入 1000/2000 输出 1000.0/2000.0；应是1/2秒。write_wav_slice 会把它乘16000，短文件切出空音频，长文件错段；写回又声明秒制/normalized-audio。需用显式schema/unit适配，不能猜量级。该复现覆盖数据适配纯函数，无真实模型请求。

## 待导入任务

### TASK-2026-09-30-ASR-STALE-WORDS — 对齐失败不得沿用旧词级边界
- 状态：READY；优先级：P2；Owner：未领取；范围：scripts/align_words.py、tests/test_align_words.py、相关SKILL/CHANGELOG。
- 问题与证据：基线8c529516，align_words.py:276-311,329-349；深拷贝后continue保留旧words，警告却声称words缺省；部分成功使available=true更易被下游误用。
- 修复要求：定义重跑替换语义，失败/跳过段默认清除本次不可验证words或显式隔离旧来源；统计、告警、逐段产物相互一致。
- 验收：输入已有words，分别注入模型异常、低相似度、无timestamps、无效时间、空文本；失败段不可被当本次可信words，成功段保持estimated透传；混合成功/失败与全失败、第二次重跑后旧warnings也正确更新。使用main入口的无模型fixture，不能只测纯映射函数。
- 当前验证：既有12/12通过；main入口stub识别的2段反例已复现，非真实模型E2E；未修复。公共证据见L6。

### TASK-2026-09-30-ASR-INPUT-TIME-UNITS — 归一火山毫秒与cut秒制输入
- 状态：READY；优先级：P2；Owner：未领取；范围：scripts/align_words.py、tests/test_align_words.py、输入/输出时间轴说明。
- 问题与证据：基线8c529516，_iter_segments:92-109把两种schema都直接float；官方火山utterance start_time/end_time是毫秒，1000/2000被当1000/2000秒，再用来切片。
- 修复要求：按schema/显式单位解析并归一为内部秒制，输出逐层单位声明一致；模糊/矛盾/非有限时间拒绝或交审，不猜量级。
- 验收：等价cut segments start=1,end=2与火山result.utterances start_time=1000,end_time=2000切出同一音频并获得同一绝对时间；第一段0起点、跨分钟值、带pad、混合/矛盾单位、NaN/Infinity/反向时间与缺字段拒绝路径。检查输出不会在ms外层无说明地混入s词边界。
- 当前验证：真实适配函数已复现单位错误；未调用云服务或模型；未修复。公开合同与官方单位来源见L7。
