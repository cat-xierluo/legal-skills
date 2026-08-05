# 质量评分与交付裁决

评分用于迫使执行者说明判断，不能把主观感觉变成“自动真值”。五维各 0—2 分，直接相加为 10 分；机器范围和阈值以 `config/quality-score-rubric.json` 为准。

## 五个维度

| 维度 | 2 分 | 1 分 | 0 分 |
|---|---|---|---|
| 自然度 | 句子直接，姿态和模板极少 | 仍有局部套话或替换感 | 大量模板、假转折、假排名 |
| 节奏感 | 信息推动句长和段落变化 | 偶有连续短段或机械断句 | 固定节拍、金句配额、隐藏列表明显 |
| 专业度 | 概念、条件、边界和必要结构准确 | 基本准确，局部被口语或删改削弱 | 改写改变原意或损坏专业结构 |
| 个性度 | 保住源稿声音；启用 voice 时匹配深层 profile | 表层接近但认识来源或段落动力偏离 | 人设注入、样本复刻或完全抹平源稿 |
| 精炼度 | 无重复姿态，必要解释完整 | 有少量可合并内容 | 大量同义循环或过度引导 |

“节奏感”不奖励长短句数量。“个性度”不奖励第一人称、比喻或口语密度。

## 硬门禁

以下任一情况出现时，不能靠高总分放行：

- 总分低于 7；
- 自然度低于 1.5；
- 个性度等于 0；
- 法律文书专业度低于 1.5；
- 功能性列举被改成隐藏列表或假排名；
- 分析型例证被逐项扩成同功能、同节拍的编号段，或为打散它而虚构关系；
- 关系层依赖源稿外的专业常识、新增审查变量或后果链，无法提供双端源稿锚点；
- 改稿把源稿的保留、可能性、条件或未知升级成更强裁断、频率或必然后果；
- 同一个“工具能力—限制—人的判断／责任”语义骨架跨段、跨节反复承担相同功能；
- 候选外的源稿、导航保护、材料不足、证据卡、扫描或交付说明泄漏进读者正文；
- 使用“先承认一个前提”等框架启动语替代直接陈述；
- 用宽泛同类项冒充分析例子之间的真实关系；
- 把重复能力边界压成短金句或结尾口号，而没有删除重复功能；
- 新增经历、感受、案例或立场变化没有作者材料；
- 强加默认人设、固定节奏、生活化比喻或短句金句；
- 复制作者样本或本机私有 anchor 的原句、高辨识短语或事实；
- Protected Spans 或 Markdown 图片整行发生变化。
- 新增、删除、改名、升降级或重排 Markdown 标题，把正文润色扩大成结构重写。

前三项和法律文书专业度由 `delivery_gate.py` 复算；标题行由 `heading_preservation_gate.py` 逐行核对；样本长连续重合由 `voice_anchor_copy_gate.py` 召回；能力—边界骨架由 `semantic_repetition_gate.py` 启发式召回；已知编辑过程泄漏和框架启动语由 `style_regression_gate.py` 阻断。分析型例证的功能判断和其余修复伪影仍需人工通读，必须在交付说明中给出处理结论。

## Voice 模式评分

### `cleanup_only`

- `个性度`看源稿已有声音是否被保存，而不是新增多少个人表达；
- `voice_profile_checks` 必须为 `null`；
- 技术说明、法律分析或正式报告不因缺少故事、幽默或第一人称扣分。

### `provided_sample` / `local_anchor`

评分回执必须把以下检查全部记为 `true`：

- `profile_matched`：匹配适用于目标场景的深层 profile；
- `no_sample_copy`：未复制样本原句或高辨识表达；
- `no_fact_leak`：未引入样本事实、人物、项目和私人信息；
- `no_counterexample_reuse`：未复现 profile 标记的反例；
- `no_repair_artifact`：未产生隐藏列表、假排名、强加口语、节奏配方或虚构经验。

任一项为 `false` 时回到改写步骤，不得通过提高其他分数抵消。

## 评分步骤

1. 对最终真实 Markdown 评分，不对草稿或脑内版本评分。
2. 每一维写一句证据，指出对应段落功能或残留问题。
3. 先执行修复伪影复扫，再计算总分。
4. 分数达到阈值但人工硬门禁失败时，结论仍是“需继续修订”。
5. 生成 `score-receipt.json`，绑定最终文件 SHA-256、scene、voice mode、anchor ID、五维分数与 voice checks。

## 回执示例

```json
{
  "schema_version": 2,
  "final_sha256": "<sha256>",
  "scene": "wechat_public_comment",
  "voice_mode": "local_anchor",
  "voice_anchor_id": "my-writing-anchor-v1",
  "dimensions": {
    "naturalness": 1.7,
    "rhythm": 1.6,
    "professionalism": 1.8,
    "individuality": 1.6,
    "conciseness": 1.5
  },
  "total": 8.2,
  "voice_profile_checks": {
    "profile_matched": true,
    "no_sample_copy": true,
    "no_fact_leak": true,
    "no_counterexample_reuse": true,
    "no_repair_artifact": true
  }
}
```

回执只能证明评分步骤和候选绑定已经执行。它不能证明文字客观上“像真人”，也不能替代作者本人对声音的判断。
