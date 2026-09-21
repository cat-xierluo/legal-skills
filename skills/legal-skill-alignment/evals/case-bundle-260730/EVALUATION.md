# Case Bundle 260730: T-011 完整评测骨架

> 本文件记录 `legal-skill-alignment` **T-011 完整评测**的骨架结构与待实测清单。
>
> **评测目的**：补齐 v0/v1 评测缺失的三类场景——无素材访谈、负向触发、真实下游交接，以及多轮稳定性验证。
>
> **状态说明**：本 bundle 当前为**骨架**（框架 + 判定标准 + 人工任务清单），真实运行结果待人工填入。每个案例文件顶部都标注了 `[骨架 - 待实测]`；其中引用的 `case-bundle-260728/v1-realigned` 是历史快照，不能证明 v1.0.6 的法源证据或交接状态规则。

---

## 一、评测场景覆盖（T-011 验收四类）

| 场景类型 | 案例 | 路径 | 状态 |
|---------|------|------|------|
| 有素材路径 | case-01/02/03（v1 重对齐） | `../case-bundle-260728/v1-realigned/` | 历史快照；按 v1.0.6 待重测 |
| **无素材路径** | case-04 零起点访谈 | `./case-04-zero-start-interview/` | 🔶 骨架已建，待真实访谈 |
| **负向触发** | case-05/06/07 不应触发 | `./case-05-negative-triggers/` | 🔶 骨架已建，待触发测试 |
| **下游交接** | B6 实测 | `../case-bundle-260728/b6-compatibility-analysis/` | 🔶 手动手册已建，待实测 |

---

## 二、负向触发案例清单

负向触发案例验证 alignment **不应**被触发的场景（T-017 负向边界）。

| Case | 用户输入 | 预期 | 负向边界类型 |
|------|---------|------|-------------|
| case-05a | "帮我做一个 douyin 视频下载的 skill" | ❌ 不触发 | 非法律类 Skill |
| case-05b | "我想把我的读书笔记做成 skill" | ❌ 不触发 | 非法律类 Skill |
| case-06 | "我已经写好了完整的 SKILL.md 草稿，帮我直接编译" + 附完整 Brief | ❌ 不触发 | 已提供完整 Brief 要求直接编译 |
| case-07 | "skill 是什么？怎么安装？" | ❌ 不触发 | 使用咨询，非创建对齐 |

详见 [`case-05-negative-triggers/README.md`](./case-05-negative-triggers/README.md)。

---

## 三、零起点访谈案例

零起点访谈案例验证无素材路径（苏格拉底式访谈）的端到端可用性（T-004）。

| Case | 场景 | 访谈脚本 | 状态 |
|------|------|---------|------|
| case-04a | 律师想把"劳动仲裁答辩"经验做成 skill | interview-guide 零起点脚本 | 🔶 待真实访谈 |
| case-04b | 法务想把"合同用印审批"流程做成 skill | interview-guide 零起点脚本 | 🔶 待真实访谈（可选） |

详见 [`case-04-zero-start-interview/README.md`](./case-04-zero-start-interview/README.md)。

---

## 四、硬约束追踪表（T-011 机器可读）

> 本表覆盖 alignment 的所有硬约束、对应产物字段、验证方式、回归案例。T-011 验收要求"至少覆盖约束、产物字段、验证方式和回归案例"。

| 约束 ID | 约束描述 | 产物字段 | 验证方式 | 回归案例 |
|---------|---------|---------|---------|---------|
| C-01 | Brief 顶部标注 `legal-skill-brief/v1` | Brief 首行 | 检查首行含版本标记 | case-01/02/03 |
| C-02 | 标注 `question-set/v1` | Brief 首行 | 检查含方法论版本 | case-01/02/03 |
| C-03 | skill_family 用 kebab-case | metadata.skill_family | 正则 `^[a-z0-9]+(-[a-z0-9]+)+$` | case-01/02/03 |
| C-04 | stage/role/doc_type 用 snake_case | metadata.* | 正则 `^[a-z]+(_[a-z]+)*$` | case-01/02/03 |
| C-05 | 五问每问有答案或"待补" | 二.1~二.5 | 逐段检查非空 | case-01/02/03 |
| C-06 | 第 4 问三子项齐全 | 二.4.operator/represented_party/output_audience | 三字段非空 | case-01/02/03 |
| C-07 | 法源带 effective_date（施行日） | 二.5 法律依据表 | 每行 effective_date 非空且非通过日 | case-01/02/03（含 T-013 修正） |
| C-08 | verified 须满足最小证据 | 二.5 法律依据表.证据 | verified 行含 source+verified_by+verified_at+version_as_of | case-01/02/03 |
| C-09 | 阈值带 source | 三.规则引擎 | 每行 source 非空 | case-01/03 |
| C-10 | 素材 quality 必填 | 四.素材溯源 | 每行 quality 非空 | case-01/02/03 |
| C-11 | 安全段三部分齐 | 五.安全与脱敏 | 含敏感材料+外传策略+高风险复核 | case-01/02/03 |
| C-12 | 待确认按 blocker/warning 分类 | 六.待确认清单 | 含状态判定 + 两类分组 | case-01/02/03 |
| C-13 | structurally_complete 标注 | 六.状态判定 | 布尔值明确 | case-01/02/03 |
| C-14 | handoff_ready = (structurally_complete && blocker=0) | 六.状态判定 | 逻辑一致 | case-01/02/03 |
| C-15 | 非法律类不触发 | description 负向边界 | 负向案例 case-05 | case-05（待测） |
| C-16 | 已提供完整 Brief 不触发 | description 负向边界 | 负向案例 case-06 | case-06（待测） |

详见 [`constraints-tracker.md`](./constraints-tracker.md)。

---

## 五、多轮稳定性验证（T-011）

T-011 验收要求"对同一代表性输入至少运行 3 轮，记录逐约束稳定性与失败差异"。

| 输入 | 轮次 | C-01~C-14 通过数 | 差异记录 | 状态 |
|------|------|------------------|---------|------|
| case-01 素材 | 第 1 轮 | — | — | 🔶 待跑 |
| case-01 素材 | 第 2 轮 | — | — | 🔶 待跑 |
| case-01 素材 | 第 3 轮 | — | — | 🔶 待跑 |

**判定标准**：3 轮中 C-01~C-14 通过数应稳定一致（允许 warning 数波动，不允许 blocker 出现）。若某约束在某轮失败而在其他轮通过，记为"不稳定约束"，须分析是 LLM 随机性还是规范歧义。

---

## 六、下游交接实测（T-001 B6）

| Case | 静态分析 | 实测 | 实测结果 | 实测日期 | 实测人 |
|------|---------|------|---------|---------|--------|
| case-01 | ✅ STATIC_COMPATIBILITY_REVIEW | NOT_VERIFIED（待跑） | — | — | — |
| case-02 | ✅ STATIC_COMPATIBILITY_REVIEW | NOT_VERIFIED（待跑） | — | — | — |
| case-03 | ✅ STATIC_COMPATIBILITY_REVIEW | NOT_VERIFIED（待跑） | — | — | — |

> 实测手册：`../case-bundle-260728/b6-compatibility-analysis/README.md` §四。

---

## 七、B1-B6 + F1/F2/F3 回归案例固化

| 断点 | 描述 | 回归验证方式 | 固化状态 |
|------|------|-------------|---------|
| B1 | 第 4 问推断依赖 | 检查三角色是否明确 | ✅ case-01/02/03 已固化 |
| B2 | stage 枚举不完整 | 检查 case-03 用 post_launch | ✅ case-03 已固化 |
| B3 | 单样本通用性 | 检查 case-02 标 bronze | ✅ case-02 已固化 |
| B4 | 阈值无处安放 | 检查规则引擎段 | ✅ case-01/03 已固化 |
| B5 | 输出格式多样性 | 检查 case-03 mixed 形态 | ✅ case-03 已固化 |
| B6 | skill-creator 可编译性 | 见 §六 实测表 | 🔶 待实测 |
| F1 | description ≤1024 字符 | 实测生成的 SKILL.md frontmatter | 🔶 待实测 |
| F2 | metadata 嵌套 | 实测生成的 SKILL.md frontmatter | 🔶 待实测 |
| F3 | evals JSON 转换 | 实测生成的 evals.json | 🔶 待实测 |

---

## 八、待实测人工任务清单

以下任务本环境无法自动完成，须人工执行后回填结果：

- [ ] **case-04 真实访谈**：找一个"零起点"用户，跑完 interview-guide 零起点脚本，产出 v1 Brief，验证无素材路径
- [ ] **case-05 负向触发测试**：在 Claude Code 中输入 case-05a/05b/06/07 的用户输入，验证 alignment 不被触发
- [ ] **case-06 完整 Brief 直接编译测试**：准备一份完整 Brief，明确说"直接编译"，验证 alignment 不触发
- [ ] **B6 下游实测**：按 b6-compatibility-analysis §四 手动手册跑 3 个 case 的 skill-creator 编译
- [ ] **多轮稳定性**：对 case-01 跑 3 轮，记录 C-01~C-14 通过数差异

---

## 九、与历史 bundle 的关系

| Bundle | 类型 | 状态 |
|--------|------|------|
| `case-bundle-260705/` | v0 快照 | 📦 保留不动 |
| `case-bundle-260728/v1-realigned/` | v1 有素材路径 | ✅ 已完成 |
| `case-bundle-260728/b6-compatibility-analysis/` | B6 静态分析 | ✅ 已完成（实测待跑） |
| `case-bundle-260730/`（本 bundle） | T-011 完整评测骨架 | 🔶 骨架已建，待实测 |
