# R1/R2 同输入稳定性比对（case-01）

> 比对者：编排会话（基于两份独立评分回执 judge/case-01-R1.md 与 judge/case-01-R2.md，以及两份独立产物）
> 比对日期：2026-08-23

## 逐约束判定矩阵

| 约束 | R1 | R2 | 一致？ |
|------|----|----|-------|
| C-01 | PASS | PASS | ✓ |
| C-02 | PASS（形式备注：question-set/v1 未进顶部 blockquote） | PASS（顶部 blockquote 两版本齐） | ✓ 判定一致（备注仅记录形式差异） |
| C-03 | PASS | PASS | ✓ |
| C-04 | FAIL（warning：client-legal） | FAIL（warning：client-legal / contract-review / operator 空格） | ✓ 两轮同约束 FAIL，且取值相互镜像 |
| C-05 | PASS | PASS | ✓ |
| C-06 | PASS | PASS | ✓ |
| C-07 | PASS | PASS | ✓ |
| C-08 | PASS | PASS | ✓ |
| C-09 | PASS | PASS | ✓ |
| C-10 | PASS | PASS | ✓ |
| C-11 | PASS | PASS | ✓ |
| C-12 | PASS | PASS | ✓ |
| C-13 | PASS | PASS | ✓ |
| C-14 | PASS | PASS | ✓ |

**14/14 判定完全一致，零漂移。**

## 状态判定比对

| 项 | R1 | R2 | 一致？ |
|----|----|----|-------|
| structurally_complete | true | true | ✓ |
| handoff_ready | false | false | ✓ |
| blocker 数 | 1 | 1 | ✓ |
| warning 数 | 10 | 9 | ≈（差 1：两轮对软性 warning 的切分粒度不同——R1 把「SOP 无版本号」并入 W10，R2 未单列；均为 warning 级，不影响任何硬判定与状态） |

## 关键行为比对（软性质量维度）

| 行为 | R1 | R2 |
|------|----|----|
| 交叉验证 SOP 与样本的阈值口径冲突（4 倍 vs 5 倍、年额 vs 总额） | ✅ 独立发现 | ✅ 独立发现（同一条，两轮互不知晓） |
| 发现「首付 50% 超阈值但样本未单列价款意见」 | ✅ | ✅ |
| 法源降级占位首行 | ✅（写成表格首数据行） | ✅（写成表格上方 blockquote） |
| 凭名称编造施行日 | 零 | 零 |
| 防错核对行（法务部→output_audience） | ✅ | ✅ |
| 个案数值禁止硬编码标注 | ✅ | ✅ |
| 脱敏提示（服务商名/金额待确认） | ✅ | ✅ |
| 素材 quality 分级 | ✅（silver/gold/gold） | ✅（silver/gold/gold，完全相同） |
| 下游去向提示（skill-creator / legal-skill-creator） | ✅ | ✅ |

## 结论

同一输入、两个互不知晓的独立实例：**14 项约束判定零漂移，状态判定零漂移，关键法律行为（阈值冲突发现、法源降级、防错核对、禁编造日期、禁个案固化）全部成对复现**。唯一差异是 warning 计数 10 vs 9（软性切分粒度）与占位行的排版形式——均不影响任何硬约束与交接判定。**稳定性判定：STABLE。**
