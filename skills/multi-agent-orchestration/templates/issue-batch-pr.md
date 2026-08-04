# 多 Issue 合并 PR 描述模板

> 当一组 Issue 经 `references/11-issue-grouping.md` 判定为「维度① 同根因合并」时，用本模板撰写 PR 描述。
> 一个 worker 顺序修完组内所有 Issue，提交到一个 PR，合并时用 `Closes` 批量关闭。
> 与单 Issue PR 的区别：必须有一个**统一根因说明**，让 reviewer 一眼看清「为什么这几个要一起改」。

---

## PR 标题

格式：`<type>(<scope>): <统一主题> (<ISS-编号1>/<编号2>[/<编号3>])`

```text
fix(editor): 标题行内联标记与光标漂移修复 (ISS-75/76)
fix(export): 内置 Word 模板导出颜色与表格样式 (ISS-78/82)
feat(settings): 导出预设选择器与外观分组 (ISS-2/5)
```

约定：
- `<type>` 和 `<scope>` 遵循项目 `git-workflow` / Conventional Commits。
- 括号里只放**本 PR 实际关闭的 Issue 编号**，不带 `#`，用 `/` 分隔。
- 主题写**这组 Issue 的共同点**，不要罗列每个 Issue 的标题。

---

## PR 正文模板

```markdown
## 背景

本 PR 合并修复以下 {{issue_count}} 个 Issue，它们根因相近、改动位置重叠：

{{closes_line}}

## 统一根因

{{root_cause_summary}}

<!-- 为什么这几个 Issue 要放一起修：同一个模块 / 同一段代码 / 同一套机制的多个表现。
     reviewer 看完这段应能理解「不分 N 个 PR 的理由」。 -->

## 修复内容（按 Issue）

### {{issue_ref_1}} — {{issue_title_1}}

- 现象：{{symptom_1}}
- 根因：{{root_cause_1}}
- 改法：{{fix_summary_1}}
- 文件：{{files_1}}

### {{issue_ref_2}} — {{issue_title_2}}

- 现象：{{symptom_2}}
- 根因：{{root_cause_2}}
- 改法：{{fix_summary_2}}
- 文件：{{files_2}}

{{additional_issues_section}}

## 验证

- [ ] typecheck / lint 通过
- [ ] 每个 Issue 的复现步骤逐一手动验证（逐个勾，不要只验一个就声称全部修好）
- [ ] 回归：未引入新问题
- 验证证据：{{screenshots_or_dom_assertions}}

## 为什么合并到一个 PR

<!-- 一句话说明合并理由，指向 references/11 的判断。例：
     均发生在标题行 WYSIWYG，涉及同一套 heading 节点 IR/Selection 处理，
     改动位置高度重叠，合并后 diff {{total_diff_lines}} 行。 -->

{{merge_reason}}
```

---

## 字段说明

| 占位符 | 含义 | 示例 |
|--------|------|------|
| `{{issue_count}}` | 本 PR 关闭的 Issue 总数 | `2` |
| `{{closes_line}}` | 批量关闭行 | `Closes #75, #76` |
| `{{root_cause_summary}}` | 统一根因（1–3 句） | 「heading 节点 IR 处理中，内联格式标记与 Selection 校正共享同一套机制」 |
| `{{issue_ref_N}}` | 第 N 个 Issue 编号 | `#75` |
| `{{symptom_N}}` | 用户可见现象 | 「标题输入英文后出现多余 `****`」 |
| `{{root_cause_N}}` | 代码层根因 | 「加粗标记在 IR 序列化时被重复生成」 |
| `{{fix_summary_N}}` | 改法要点 | 「收窄 IR 序列化的加粗标记去重条件」 |
| `{{files_N}}` | 涉及文件 | `src/editor/heading.ts` |
| `{{total_diff_lines}}` | 合并后总 diff 行数 | `186` |
| `{{merge_reason}}` | 合并理由（1 句） | 指向 references/11 §2.1 的触发信号 |

---

## 使用纪律

- **每个 Issue 都要单独手动验证并勾选**：合并 PR 最容易踩的坑是「修了 A 漏了 B」。不要只验一个 Issue 就声称整个 PR 完成。
- **统一根因必须写清**：这是合并 PR 区别于普通 PR 的核心。如果写不出统一根因，说明它们可能不该合并——退回 `references/11` §4 决策树重新判断。
- **合并后 diff 控制在软阈值内**：参考 `references/11` §3，同根因合并建议 < ~300 行；超出应重新评估是否拆分。
- **`Closes` 行放在背景段**：GitHub 会按这行在合并时批量关闭 Issue。
- **不要把不同类型的 Issue 合并**：bugfix + feat + refactor 混在一个 PR 会让 review 评级和回滚都困难（`references/11` §6 反模式）。

---

## 与单 Issue PR 的区别速查

| 维度 | 单 Issue PR | 合并 PR（本模板） |
|------|------------|------------------|
| 标题 | `fix(editor): xxx (ISS-75)` | `fix(editor): <统一主题> (ISS-75/76)` |
| 背景段 | 直接描述该 Issue | 必须有「统一根因」段 |
| `Closes` | 单个 | 多个，逗号分隔 |
| 验证 | 验一个 Issue | 逐个 Issue 勾选验证 |
| Review 重点 | 改动是否解决该 Issue | 合并是否合理 + 每个 Issue 是否都修到位 |
