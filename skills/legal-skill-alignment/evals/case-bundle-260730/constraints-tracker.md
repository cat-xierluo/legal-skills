# 硬约束追踪表（T-011 机器可读）

> 本表覆盖 `legal-skill-alignment` 的所有硬约束、对应产物字段、验证方式、回归案例。
>
> **用途**：评测时逐约束打勾；规范变更时确认约束未被破坏；多轮稳定性测试时记录差异。
>
> **格式约定**：每行一个约束，可被脚本解析（`|` 分隔）。

---

## 约束总表

| 约束 ID | 约束描述 | 产物字段 | 验证方式 | 回归案例 | 严重度 |
|---------|---------|---------|---------|---------|--------|
| C-01 | Brief 顶部标注 `legal-skill-brief/v1` | Brief 首行 blockquote | grep `legal-skill-brief/v1` 首部 | case-01/02/03 | blocker |
| C-02 | 标注 `question-set/v1` | Brief 首行 blockquote | grep `question-set/v1` 首部 | case-01/02/03 | blocker |
| C-03 | skill_family 用 kebab-case | 一.metadata.skill_family | 正则 `^[a-z0-9]+(-[a-z0-9]+)+$` | case-01/02/03 | blocker |
| C-04 | stage/role/doc_type 用 snake_case | 一.metadata.* | 正则 `^[a-z]+(_[a-z]+)*$` | case-01/02/03 | warning |
| C-05 | 五问每问有答案或"待补" | 二.1~二.5 | 逐段检查非空 | case-01/02/03 | blocker |
| C-06 | 第 4 问三子项齐全 | 二.4.operator / .represented_party / .output_audience | 三字段非空 | case-01/02/03 | blocker |
| C-07 | 法源带 effective_date（施行日，非通过日） | 二.5 法律依据表 | 每行 effective_date 非空 | case-01/02/03 | blocker |
| C-08 | verified 须满足最小证据 | 二.5 法律依据表.证据列 | verified 行含 4 项证据字段 | case-01/02/03 | blocker |
| C-09 | 阈值带 source | 三.规则引擎.阈值配置 | 每行 source 非空 | case-01/03 | warning |
| C-10 | 素材 quality 必填 | 四.素材溯源 | 每行 quality 非空 | case-01/02/03 | warning |
| C-11 | 安全段三部分齐 | 五.安全与脱敏 | 含敏感材料+外传策略+高风险复核 | case-01/02/03 | blocker |
| C-12 | 待确认按 blocker/warning 分类 | 六.待确认清单 | 含两类分组 | case-01/02/03 | warning |
| C-13 | structurally_complete 标注 | 六.状态判定 | 布尔值明确 | case-01/02/03 | blocker |
| C-14 | handoff_ready 逻辑一致 | 六.状态判定 | = structurally_complete && blocker=0 | case-01/02/03 | blocker |
| C-15 | 非法律类 Skill 不触发 | SKILL.md description 负向边界 | 负向案例 case-05a/05b | case-05（待测） | blocker |
| C-16 | 已提供完整 Brief 不触发 | SKILL.md description 负向边界 | 负向案例 case-06 | case-06（待测） | blocker |
| C-17 | 使用咨询不触发 | SKILL.md description 负向边界 | 负向案例 case-07 | case-07（待测） | warning |

---

## 约束与断点的对应关系

| 历史断点 | 对应约束 | 修复版本 | 状态 |
|---------|---------|---------|------|
| B1（第 4 问推断依赖） | C-06 | v1.0.0（T-006 三角色拆分） | ✅ 已修复 |
| B2（stage 枚举不完整） | C-04 | v1.0.0（T-009 stage 扩展） | ✅ 已修复 |
| B3（单样本通用性） | C-10 | v1.0.0（quality 必填） | ✅ 已修复 |
| B4（阈值无处安放） | C-09 | v0.1.1（规则引擎段） | ✅ 已修复 |
| B5（输出格式多样性） | — | v0.1.1（输出格式指引） | ✅ 已修复 |
| B6（skill-creator 编译） | — | v1.0.0（中立契约） | 🔶 静态通过，实测待跑 |
| F1（description ≤1024） | — | v1.0.2（description 187 字） | 🔶 待实测 |
| F2（metadata 嵌套） | C-03/C-04 | v1.0.0（metadata 可选） | 🔶 待实测 |
| F3（evals JSON 转换） | — | — | 🔶 待实测（design by intent） |
| T-013（法源 verified 证据） | C-07/C-08 | v1.0.2 | ✅ 已修复 |
| T-014（状态判定歧义） | C-13/C-14 | v1.0.2 | ✅ 已修复 |

---

## 多轮稳定性记录模板

对同一输入运行 N 轮，记录每轮的约束通过情况：

| 输入 | 轮次 | C-01 | C-02 | C-03 | ... | C-14 | 差异 |
|------|------|------|------|------|-----|------|------|
| case-01 | R1 | ✅ | ✅ | ✅ | ... | ✅ | — |
| case-01 | R2 | ✅ | ✅ | ✅ | ... | ✅ | — |
| case-01 | R3 | ✅ | ✅ | ✅ | ... | ✅ | — |

**不稳定约束判定**：某约束在某轮 ❌ 而其他轮 ✅，记为不稳定，须分析原因（LLM 随机性 vs 规范歧义）。
