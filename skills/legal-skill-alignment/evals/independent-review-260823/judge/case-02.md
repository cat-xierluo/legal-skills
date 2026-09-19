# 评分回执：case-02

> 评分者：judge-case02 agent（全新上下文，与 worker 无共享会话；只见 SKILL.md + constraints-tracker + 素材 + Brief 产物）
> 评分日期：2026-08-23

判定依据：SKILL.md（v1.0.6）+ constraints-tracker.md（C-01~C-14）；辅助参照 references/standard-prompt-output.md（命名约定表、verified 证据门槛、模板填充示例）。行号均指 `worker-outputs/case-02-brief.md`。

## 约束核查表（C-01~C-14 逐条）

| ID | 判定 | 证据 |
|----|------|------|
| C-01 | PASS | L20（Brief 主体标题下首个 blockquote）："遵循 legal-skill-brief/v1 规范、question-set/v1 方法论"——`legal-skill-brief/v1` 位于 Brief 首部 |
| C-02 | PASS | 同一行（L20）含 `question-set/v1` |
| C-03 | PASS | L26 `skill_family：copyright-infringement-first-instance-agent-statement`，匹配 `^[a-z0-9]+(-[a-z0-9]+)+$` |
| C-04 | **FAIL（warning 级）** | L29 `operator：junior-lawyer`、L32 `doc_type：agent-statement` 用连字符，不匹配 `^[a-z]+(_[a-z]+)*$`；stage=`first_instance`（L28）、represented_party=`plaintiff`、output_audience=`judge` 合规。注意：standard-prompt-output.md 命名约定表明示"文书类型使用 snake_case"且示例即 `agent_statement`，此处应写 `agent_statement`——doc_type 是较明确的违规；operator 字段的规范模板示例自身混用 kebab（compliance-officer/ai-operator）与 snake（buyer_counsel），属规范内部张力，但按 tracker 正则仍判不过 |
| C-05 | PASS | 二.1（L37-52，必要/可选输入+信息来源）、二.2（L54-65，字数/引言/结尾/署名明确标"待补"）、二.3（L67-81，其他抗辩分支与异常路径标"待补"）、二.4（L83-91）、二.5（L93-112）五段均非空，缺口均标待补 |
| C-06 | PASS | L85-87 三子项齐全非空：operator=团队年轻律师、represented_party=原告方（影视公司等权利人）、output_audience=法官（合议庭） |
| C-07 | PASS | L99-108 法源表 8 行，effective_date 列每行均填 `unverified`（非空）。素材无法源原文，按 SKILL.md v1.0.6 降级规则恰是规定动作；全表无一行出现编造的具体施行日期 |
| C-08 | PASS | 8 行 verification_status 全为 `unverified`，无 verified 行——最小证据要求为条件性规则，无 verified 行则空真满足；且表已按模板附齐 4 个证据列（均填 unverified） |
| C-09 | PASS（warning 级） | L120 阈值行 source="sample-001 反推——个案酌定结果，禁止通用化，待团队确认"；L126 判断标准行 source="sample-001 反推（个案论证路径，待团队确认）"——均非空且如实标注单样本反推、禁止通用化 |
| C-10 | PASS（warning 级） | L132-134 三行 quality 依次 silver / silver / unrated（无对应素材，原因已注明），均非空 |
| C-11 | PASS | L140-152 三部分齐：敏感材料处理（识别案件金额未脱敏、状态"部分脱敏"、责任"AI 已提示+参数化"）；外传策略（未联网/未上传/一次性使用）；高风险结论复核（代理词为最终诉讼文书，"是，强制"律师复核） |
| C-12 | PASS（warning 级） | L162-172 分"阻塞交接缺口（blocker）"与"可带警告交接缺口（warning）"两组，每项带 `— type:` 标注 |
| C-13 | PASS | L157 `structurally_complete: true`，布尔值明确 |
| C-14 | PASS | 独立重算结果与自标注完全一致（见下方重算表）；且 L22 顶部按状态转换规则显式标注"含 1 项 blocker……不建议下游直接编译；是否强行交接由你决定"，顶部+清单双标注齐 |

## 状态重算过程

1. **五问字段面**：二.1~二.5 均有实质内容，无法确定处均标"待补"（二.2 字数/引言/结尾/署名、二.3 其他抗辩与异常路径）→ 五问条件满足。
2. **其余四项结构条件**：法源行均带 effective_date+verification_status（值 unverified）✓；素材溯源 quality 已填（silver/silver/unrated）✓；安全与脱敏段已填（含具体敏感项识别）✓；待确认清单按 blocker/warning 分组 ✓。→ **structurally_complete = true**。
3. **素材是否提供法源原文**：查 worker-inputs/case-02.md——素材仅有法条名称+条号（《著作权法》第 10/26/53/54 条等）、司法解释全称+条号、北高法指导意见全称（无条号）、脱敏案号"(2020)京 73 民终 XXXX 号"。**无任何 source_url/source_file，无一条条文原文文本** → 降级规则适用，Brief 的判断（L97）正确。
4. **是否产出具体法律建议**：Brief 的 Skill 是一审代理词撰写，代理词属含具体法条适用的诉讼文书，落在 SKILL.md"关键法源缺失的唯一判定"所列类型 → **必须登记 blocker、handoff_ready=false**。Brief L163 自认"属具体法律建议"并登记 blocker，定性正确。
5. **blocker 独立计数**：blocker 组仅 1 项（关键法源原文缺失，L163）。逐一核对是否漏登：operator 有明确推断依据（用户原话"团队里年轻律师也能照着写"），按规则"仅 warning 级标待补不算未确认"→ warning 正确，非漏登 blocker；represented_party/output_audience 同理有样本抬头/落款/立场依据 → warning 正确。无漏登、无多登。**blocker = 1**。
6. **handoff_ready** = structurally_complete && (blocker=0) = true && false = **false**。
7. **warning 独立计数**：L166-172 依次为三角色确认/案型范围/单样本局限/法源时效/赔偿酌定数值/金额脱敏/文书格式缺口，共 **7 项**，均属 warning 合理量级；"法源时效"系补齐原文后的版本核对残余事项，与 blocker 不构成重复计数。

**与自标注比对表**：

| 字段 | Brief 自标注 | 独立重算 | 一致? |
|------|------------|---------|-------|
| structurally_complete | true（L157） | true | ✓ |
| handoff_ready | false（L158） | false | ✓ |
| blocker 数 | 1（L159） | 1 | ✓ |
| warning 数 | 7（L160） | 7 | ✓ |

四项全部一致 → C-14 PASS。

## 三项特别核查

**1. 法源降级：合规。** 二.5 表格前有首行占位 blockquote（L97）："**法源原文缺失：以下条目均 `unverified`，待用户补充权威出处后升级。**（素材仅提供法条名称＋条号，未附任何原文或链接，不得凭名称填施行日）"——措辞与 SKILL.md 强制要求的占位语义一致。8 行 effective_date 一律 `unverified`，全表零编造日期；会产出具体法律建议 → 已登 blocker（L163）+ handoff_ready=false，链条完整。

**2. 空壳行：无违规空壳行。** 8 行中 6 行带具体条号（第 10 条第 1 款第（十二）项/第 26/53/54 条/司法解释第 3、4 条），属"可定位的具体法源"，非空壳。两处边界行按规则例外与转录口径处理正确：(a) 北高法指导意见行（L107）——素材给的是文件全称、无条号，Brief 按"名称足以定位法源范围可转录"例外转录，jurisdiction 标 CN（北京）、三列 unverified、说明列明"文件全称可定位、无条号"+北京地域适用限定，且未据此编任何法律结论，blocker 中列入待补；(b) 脱敏判例行（L108）——案号系素材原有引用（非编造），转录时明示"案号已脱敏、待补完整案号与文书原文"，归入 blocker 补充范围。全部 8 行均可溯源到素材原文的法律依据引用，无凭空新增法源。

**3. 防错核对：合规。** 二.4 末尾（L91）有专门防错核对行，逐项覆盖 (a) 三者均非空、(b) represented_party 未误填法官（明写"法官是 output_audience"）、(c) operator（年轻律师）与 output_audience（法官）未混淆，并如实声明"三角色均系推断，待用户确认"。本案最典型陷阱——把法官填进 represented_party——被正确避开（represented_party=原告权利人 L86）。

## 总判定

- **blocker 级 FAIL：0 / 14**（C-01/02/03/05/06/07/08/11/13/14 全 PASS）
- **warning 级 FAIL：1 / 4**（C-04：operator `junior-lawyer` 与 doc_type `agent-statement` 用连字符，应为 `junior_lawyer`/`agent_statement`）
- **一句话结论**：该 Brief 硬约束近乎全绿、状态四项自标注与独立重算完全一致（true/false/1/7）、三项特别核查（法源降级占位、无空壳行、防错核对）全部合规，唯一瑕疵是 C-04 两处枚举值命名用 kebab 未用 snake（warning 级，不阻塞交接）。

附两处非约束级小观察（不计 FAIL）：(1) L120 阈值行在 source 列保留了个案真实金额"15 万"，虽已在安全段声明并参数化为 N 万元、且列入 warning 待确认，但与"Brief 内金额建议脱敏表述"的取向略有出入；(2) 落款参数化 {管辖法院}（二.2 L58）作为推断要素只在文末问题 7 出现、未镜像进待确认清单，属清单覆盖面的轻微遗漏。
