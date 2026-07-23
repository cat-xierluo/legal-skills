# 独立视觉 Review 协议

## 目录

1. 角色隔离
2. 分批方式
3. 审查动作
4. JSON 交付
5. Reviewer prompt

## 1. 角色隔离

- 生产者只提交 candidate，不审自己的图或 DOCX 页面。
- reviewer 使用 fresh context；不要先读生产者的“已完成/已通过”结论。
- reviewer 只读 `combined-render-manifest-*.json`、`visual-review-*.template.json`、原尺寸 PNG 和项目规范。
- `reviewer_id` 必须不同于 `producer_id`；每个 reviewer 填真实 `reviewer_session_id`。

## 2. 分批方式

- SVG 每批最多 12 张；DOCX 页面每批最多 8 页。
- contact sheet 只用于定位，不能代替打开原尺寸 PNG。
- 多 reviewer 的 artifact 范围必须互不重叠；每人输出一个 JSON，统一放在独立 review 目录。
- 不抽样。manifest 中每个 artifact 都必须出现一次。

## 3. 审查动作

逐个 artifact 打开原尺寸 PNG，再按 template 已列维度填写：

- `content_matches_context`：图是否表达相邻正文真正要说的内容。
- `text_readable`：文字完整、字号可读、没有消失或乱码。
- `no_overlap_or_clipping`：文字、序号、图形、页面元素没有重叠或裁切。
- `arrows_correct`：方向、起终点、箭头头部、流程语义正确；无箭头时可 `NA` 并写理由。
- `spacing_and_density`：留白、密度、图与正文/图注的间距适合出版阅读。
- `caption_assignment`：图注属于正确图片；DOCX 页面没有图注串到上一图/下一图。
- `style_consistent`：配色、字色、表格类 SVG 与本书规范一致。
- `page_layout_and_pagination`：最终页面的页边距、分页、孤行/孤标题、超宽表格和图片位置正常。

任何维度拿不准都填 `FAIL` 并说明，不得用“整体看起来可以”覆盖单项缺陷。

## 4. JSON 交付

从 `visual-review-<sha>-prepare.template.json` 复制自己负责的 artifacts，填写：

- 顶层：`reviewer_id`、`reviewer_session_id`、`independent: true`、`reviewed_at`。
- artifact：`verdict` 只能填 `PASS` 或 `FAIL`。
- dimension：填 `PASS` / `FAIL`；仅模板允许的维度可填 `NA`，且 `note` 不得为空。
- 不改 `candidate_sha`、`render_manifest_sha`、`producer_id`、`artifact_id`、`png_sha256`。

Gate 会校验逐图覆盖、逐维度覆盖、哈希、身份隔离和重复条目。缺项、旧 PNG、自审或失败项都会阻断 release。

## 5. Reviewer prompt

```text
你是出版成品的独立视觉 reviewer。不要修改任何源文件，不要读取生产者的完成结论。

输入：
- 项目视觉/排版权威规范：<路径列表>
- combined render manifest：<路径>
- 你的 review template 分片：<路径>
- 原尺寸 PNG 根目录：<路径>

要求：
1. 按 template 顺序逐个打开原尺寸 PNG；contact sheet 只定位。
2. 对 template 已列的每个维度分别判 PASS/FAIL/允许时 NA，并写短 note。
3. 任一维度 FAIL，则 artifact 总 verdict=FAIL；全部通过才填 PASS。
4. 不抽样、不漏 artifact，不改任何 hash/id/producer 字段。
5. 填写独立 reviewer 身份、session 与时间，只输出完成后的 JSON。
```

