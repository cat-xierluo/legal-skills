# 课程生成工作流

本文件规定从来源文本到课程成品的完整执行顺序。开始生成课程时完整读取；字段结构和 JSON 示例按需查询 [course-manifest.md](course-manifest.md)。

## 1. 建立来源索引

使用用户给出的单个文件或目录生成确定性索引：

```bash
python3 scripts/index_sources.py \
  --input <来源文件或目录> \
  --output <课程目录>/source-index.json \
  --authority-mode current

python3 scripts/ledger_tool.py init \
  --source-index <课程目录>/source-index.json \
  --source-root <同一个来源文件或目录> \
  --manifest <课程目录>/course-manifest.json \
  --title "<真实课程名称>" \
  --overview-file "00 <真实课程名称> - 总览.md"
```

默认使用 `current`。只有用户明确要求保留历史课堂口径时才使用 `historical`。控制文档缺失、同名不唯一或声明无法解析时停止，不得自行降级。

若存在 `config/user_dictionary.yaml`，先按其中词条对专名和固定术语做高置信纠正，再建立来源索引。词典不用于改写句意；无法从上下文确认的疑似误识别保持原样或在人工复核时标记。

索引器给每个来源和内容块分配稳定的 `SRC-xxx`、`BLK-xxxxx`，并记录哈希、行号、块类型和预览。平台摘要、关键词和自动生成的 Q&A 标为 `derived`，只帮助定位，不作为新事实来源。

## 2. 冻结章节计划

先读取 `ledger_tool.py init/status` 返回的权威声明、修订项和候选旧口径队列，再编制 chapter plan。

- 当前口径下，每个 `COR-xxx` 都要路由到一个已计划的二级标题。
- 按候选队列原顺序逐项判断 `superseded` 或 `retained_current`；每项提供逐字来自候选预览、至少 6 字的证据和专属理由。
- 不复制同一理由批量判断，不把整张高召回矩阵一律删除；预览不足时回读原文。
- 被确认替代的块只进入 `authority_superseded` 跳过项，不能成为正文证据。
- 默认规划 3—8 章。按主题组织，不把签到、致辞、设备准备、讲者履历机械拆成独立章。
- 每个二级标题至少预先绑定一个有效素材，结构性薄章优先合并。

运行：

```bash
python3 scripts/ledger_tool.py plan \
  <课程目录>/course-manifest.json \
  <临时目录>/chapter-plan.json
```

计划冻结后不边写正文边改章、节结构。若结构错误足以影响成品，保留当前候选为失败，在新目录重新执行 `init → plan → merge`。

## 3. 分批建立素材账本

按 `status` 给出的 `next_batch_content_block_ids` 读取下一批，通常每批 20—40 个内容块。批次文件只写素材语义、来源块、覆盖词和目标章、节；编号、source refs、图片登记和哈希由工具维护。

```bash
python3 scripts/ledger_tool.py merge \
  <课程目录>/course-manifest.json \
  <临时目录>/batch-001.json \
  --source-root <同一个来源文件或目录>

python3 scripts/ledger_tool.py status \
  <课程目录>/course-manifest.json \
  --next-batch-size 30
```

素材账本遵守以下边界：

- 每个有效内容块必须进入一个或多个素材，或使用受控理由跳过。
- 一项素材表达一个可独立讲清的观点、案例、操作阶段、踩坑、取舍或问题；通常合并 2—5 个相邻且属于同一教学点的来源块，最多合并 6 个。
- 整份账本不得超过工具返回的 `maximum_material_count`。预计超限时合并同一观点、连续操作阶段或相同跳过理由，不把独立教学点粗暴压在一起。
- `pure_repeat`、`no_course_value` 只用于真正重复或没有课程价值的片段，不能整体跳过案例、演示、错误修正、版本比较或产品效果。
- 每项 include 素材预先填写 1—3 个 `coverage_terms`。词语必须逐字存在于绑定原文，优先选择步骤、结果、数字、限制或专名，不使用“我觉得”“比如说”“做一个”等低信号或截断片段。
- 完全相同的批次因超时重试时，`merge` 会幂等跳过；不要重新分配编号或手改 manifest。

全部内容块处理完后运行：

```bash
python3 scripts/finalize_manifest.py \
  <课程目录>/course-manifest.json --phase ledger --write

python3 scripts/preflight_ledger.py \
  <课程目录>/course-manifest.json \
  --source-root <同一个来源文件或目录>
```

预检退出码为 `1` 时，只修正报告指出的素材划分、去向或覆盖词；退出码为 `2` 表示文件或运行异常。预检通过前不生成正文。

## 4. 选择图片并生成脚手架

从来源图片及其相邻内容中选择方法框架、关键界面、转折或结果代表图。只提交短选择清单，不重写完整图片数组。

```bash
python3 scripts/ledger_tool.py select-images \
  <课程目录>/course-manifest.json \
  <临时目录>/image-selection.json

python3 scripts/ledger_tool.py scaffold \
  <课程目录>/course-manifest.json
```

`select-images` 负责同步图片顺序和目标文档；`scaffold` 创建精确 H1/H2，并把现行修订句原样写入目标小节的“关键规则”引用块。生成者不得改写、删除或重复这些修订句。

## 5. 生成总览和章节

建立账本时读取 [outline_prompt.md](outline_prompt.md)，生成总览时读取 [overview_prompt.md](overview_prompt.md)，逐章写作时读取 [chapter_prompt.md](chapter_prompt.md)。

- 先写总览，再按 manifest 顺序逐章生成。
- 二级标题的文字和顺序必须与冻结计划完全一致，不新增无素材标题。
- 每章只加载本章素材、相关修订、source refs 和必要邻接原文，不再次把全部长转录稿塞入上下文。
- 把案例、操作、失败修正和判断过程写成完整正文；去掉直播、课堂和演示转播框架，但不删除其承载的实质内容。
- 来源带有“可能、好像、比如、畅想”等语气时保留同等不确定性；断裂 ASR 中无法确认的身份、数字或平台名不写成事实。
- 单个仓库、一次运行、一个团队或一张截图中的事实只描述该样本，来源没有同等范围判断时不得写成“常见规模”“普遍适用”或“行业惯例”。
- 不计算还差多少字，不用近义重复、通用建议或面向门禁的段落补篇幅。

每完成一章立即运行：

```bash
python3 scripts/ledger_tool.py check-chapter \
  <课程目录>/course-manifest.json \
  --document CH-01
```

当前章通过后才进入下一章。单章门禁不证明事实忠实；通过后仍要回扫对应来源，确认案例和操作没有只剩一句概述。

## 6. 收口与验收

全部正文完成后运行：

```bash
python3 scripts/finalize_manifest.py \
  <课程目录>/course-manifest.json --phase final --write

bash scripts/verify.sh \
  <课程目录> --source-root <同一个来源文件或目录>
```

finalizer 只从每项素材的目标小节提取正文证据并同步图片映射，不写正文、不创造事实。出现 `unresolved` 时，在对应小节补充来源已有的过程、结果、限制或修正，再重新收口；不得跨节借证据或写“正文证据补丁”。

`verify.sh` 退出码：`0` 表示客观门禁通过，`1` 表示产物不符合契约，`2` 表示输入或运行环境异常。修改正文、manifest 或来源后必须重新验收。

脚本通过后，独立复核以下语义项：

1. 高价值素材是否完整进入正文，跳过项是否合理。
2. 数字、动作链、建议、结果和专名能否回到原文。
3. 现行修订是否一致，旧口径是否通过同义改写回流。
4. 是否存在来源外能力、参数、标准流程、行业判断或绝对承诺。
5. 章节边界是否清楚，是否存在大段重复和无价值图片。

最终目录只保留总览、章节、`source-index.json`、`course-manifest.json`、manifest 声明的可选审计文件和必要图片。批次、计划、图片选择 JSON/YAML、辅助脚本和缓存全部移到目录外。

## 失败处理

- 配额、网络或平台故障：保留当前目录和运行证据，标记为外部失败，不评价 Skill 成败。
- 只有账本或部分章节：标记为不完整产物，不接受平台“成功”状态。
- 客观门禁失败：按精确失败项修复并重跑，不放宽规则、不删减有效素材换取通过。
- 人工语义复核失败：保留候选作为回归证据；只有失败可复现且属于新类别时，才修改 Skill 或验证器。
