# 指令稳定性与产出漂移审查标准

本文件定义 `skill-lint` 如何识别“规则写了很多，但执行时仍漏项、验收时仍放过错误”的 Skill。它补充 `harness-reliability-standards.md`：后者证明当前候选和 checker 的证据没有陈旧；本文件进一步证明关键约束在多轮真实执行中都被覆盖，并且验证方式与产物类型匹配。

## 一、要解决的失效

下列现象不能简单归因于“模型不听话”：

- 同一任务重复执行，某轮漏审一个维度，另一轮又漏掉另一项。
- Skill 明文禁止某种产物，但它自己的生成器或模板仍持续生成。
- checker 确实运行了，却只检查源文本，没有检查渲染结果或最终交付件。
- 每个局部脚本都显示 PASS，但没有证据证明全部硬约束都进入了检查范围。
- review 报告说“已修改”，实际源文件、任务状态或最终产物并未变化。
- 历史事故修完后没有变成固定反例，同类缺陷过一段时间再次出现。

共同根因是：自然语言要求没有形成“约束 → 验证器 → 真实产物 → 反例 → 多轮证据”的闭环。增加更多强调语通常只会增加上下文，并不能证明覆盖。

## 二、两阶段审查

### 1. 旧版 / 第三方静态识别

先运行：

```bash
python3 scripts/instruction_stability_gate.py assess \
  --candidate-root /path/to/skill
```

没有 `config/instruction-stability-contract.json` 时，工具不执行候选代码，只根据候选文件识别结构性风险，并返回退出码 2 和 `INSTRUCTION_STABILITY_NOT_VERIFIED`。常见 finding：

- `ISG-001`：没有机器可读约束追踪合同。
- `ISG-002`：出现视觉/几何要求，却没有 geometry/render/visual 模态证据。
- `ISG-003`：出现多维审阅/语义任务，却没有至少三轮逐约束覆盖证据。
- `ISG-004`：出现完成或验证声明，却没有多轮真实产物回执。
- `ISG-005`：候选虽然有脚本，但没有证明脚本覆盖了全部要求。
- `ISG-006`：候选已有合同，但没有候选外独立硬约束基线，不能证明合同未漏列规则。

静态识别的结论只能是 `NOT_VERIFIED`。它适合审查老版本和未知第三方 Skill，不冒险执行其中脚本。

### 2. 候选多轮正式验证

需要声称“指令遵循稳定”“多轮不漏项”或“产出没有关键漂移”时：

1. 为权威来源中的每条 hard constraint 分配稳定 ID，并在要求旁加入唯一锚点，例如 `<!-- skill-lint:constraint REPORT-COVERAGE -->`。
2. 复制 `config/instruction-stability-contract.example.json` 为目标 Skill 内的 `config/instruction-stability-contract.json`，用 `SKILL.md#REPORT-COVERAGE` 这类 source ref 双向绑定全部锚点、checker、产物阶段、正反例和历史回归。
3. 由候选外 evaluator 按 `config/instruction-stability-requirements-baseline.example.json` 形成硬约束基线；其 candidate SHA-256、`requirement_sources`、`requirement_exclusions`、hard constraint IDs 和 source refs 必须与当前候选、锚点及合同完全相同。门禁自动发现 `SKILL.md` 与 `references/**/*.md` 中含硬要求信号的文件；每一份都必须进入 sources，或由 evaluator 在签名 exclusions 中逐项说明理由，不能静默漏掉整份规范。sources 中任何含“必须 / 不得 / 禁止 / 应当 / 务必 / must / shall / never”的规范行，都必须在同一行或前一个非空行有唯一 marker。基线使用 evaluator 的 Ed25519 私钥在候选执行环境之外签名；正式门禁只取得受信公钥。合同存在但缺有效签名基线时仍是 `NOT_VERIFIED`。
4. 先按 `harness-reliability-standards.md` 生成并填写候选外 Harness review evidence。正式稳定性门禁只允许当前正在执行的受信 `skill-lint` 作为 policy root，并亲自复算该 evidence；候选不能替换门禁，仅在合同里自填 `independent_from_producer=true` 也不构成独立性证明。
5. 用相同任务、相同输入和相同配置至少独立运行三次。每轮使用唯一 execution nonce、独立 run 目录和 producer log，保留真实最终产物，不只保留 Agent 总结。不同 run 不得复用同一 artifact 或 producer log 路径。producer log 由 evaluator-controlled runner 在观察到本轮执行后形成，再交给不执行候选代码的离线签名步骤；Ed25519 私钥不得出现在运行 producer/checker 的进程树、工作目录或可读环境中。
6. 在候选外写运行证据 JSON：

   ```json
   {
     "schema_version": 1,
     "evaluation_id": "evaluation-20260723-001",
     "runs": [
       {
         "id": "r1",
         "execution_nonce": "execution-001",
         "input_sha256": "<same-input-sha256>",
         "config_sha256": "<same-config-sha256>",
         "producer_log": "r1/producer-log.json",
         "artifacts": [
           {"artifact_id": "final-report", "path": "r1/final-report.json"}
         ]
       },
       {
         "id": "r2",
         "execution_nonce": "execution-002",
         "input_sha256": "<same-input-sha256>",
         "config_sha256": "<same-config-sha256>",
         "producer_log": "r2/producer-log.json",
         "artifacts": [
           {"artifact_id": "final-report", "path": "r2/final-report.json"}
         ]
       },
       {
         "id": "r3",
         "execution_nonce": "execution-003",
         "input_sha256": "<same-input-sha256>",
         "config_sha256": "<same-config-sha256>",
         "producer_log": "r3/producer-log.json",
         "artifacts": [
           {"artifact_id": "final-report", "path": "r3/final-report.json"}
         ]
       }
     ]
   }
   ```

7. 每个 producer log 必须回写 evaluation ID、本轮 run ID、nonce、相同 input/config SHA-256、当前完整候选 SHA-256、合同中 producer ID 与实现清单 SHA-256，以及 artifact ID、路径和真实 SHA-256，并带 evaluator Ed25519 signature；门禁会复算并精确比对，旧候选或旧 producer 的日志不能重放。
8. evaluator 还必须按 `config/instruction-stability-held-out-cases.example.json` 准备候选外隐藏用例。每条 hard constraint 至少有一个隐藏正例和一个 mutation/historical 反例；manifest 绑定当前候选与 fixture SHA-256，并由同一 evaluator 私钥签名。门禁把公开 fixture、隐藏 fixture和真实 run artifact 都复制到同一种随机临时目录、随机文件名后再交给 checker，不向候选暴露 run/public/hidden 类别。
9. evaluator 在隔离环境生成 Ed25519 密钥；私钥使用最小文件权限并留在不执行候选代码的独立签名环境，验证端和候选端只分发公钥：

   ```bash
   openssl genpkey -algorithm Ed25519 \
     -out /secure/evaluator-private.pem
   chmod 600 /secure/evaluator-private.pem
   openssl pkey -in /secure/evaluator-private.pem -pubout \
     -out /path/to/review/evaluator-public.pem

   python3 scripts/instruction_stability_gate.py sign-evidence \
     --input /path/to/review/unsigned-baseline.json \
     --output /path/to/review/requirements-baseline.json \
     --private-key /secure/evaluator-private.pem
   ```

10. 完成静态安全审查、披露 checker 并确认候选为自有/可信代码后运行。此步骤执行候选 checker，只生成不可覆盖的 `EVIDENCE_READY` 草稿，不直接声称 VERIFIED：

   ```bash
   python3 scripts/instruction_stability_gate.py verify \
     --candidate-root /path/to/skill \
     --evaluator-public-key /path/to/review/evaluator-public.pem \
     --requirements-baseline /path/to/review/requirements-baseline.json \
     --harness-evidence /path/to/review/harness-review.json \
     --held-out-cases /path/to/review/held-out-cases.json \
     --held-out-root /path/to/review/held-out \
     --run-evidence /path/to/review/runs.json \
     --runs-root /path/to/review/runs \
     --receipt /path/to/review/instruction-stability-receipt-draft.json \
     --confirm-trusted-candidate
   ```

11. evaluator 在离线环境签名草稿；签名命令不执行候选：

    ```bash
    python3 scripts/instruction_stability_gate.py sign-evidence \
      --input /path/to/review/instruction-stability-receipt-draft.json \
      --output /path/to/review/instruction-stability-receipt-signed.json \
      --private-key /secure/evaluator-private.pem
    ```

12. 最后以公钥验签并重新绑定当前候选、合同、policy、外部基线、held-out、运行证据、producer logs 和真实产物：

    ```bash
    python3 scripts/instruction_stability_gate.py verify-receipt \
      --receipt /path/to/review/instruction-stability-receipt-signed.json \
      --candidate-root /path/to/skill \
      --evaluator-public-key /path/to/review/evaluator-public.pem \
      --requirements-baseline /path/to/review/requirements-baseline.json \
      --harness-evidence /path/to/review/harness-review.json \
      --held-out-cases /path/to/review/held-out-cases.json \
      --held-out-root /path/to/review/held-out \
      --run-evidence /path/to/review/runs.json \
      --runs-root /path/to/review/runs
    ```

13. 只有 `verify-receipt` 退出码为 0 并输出 `INSTRUCTION_STABILITY_VERIFIED`，才可声明关键约束在本次样本中稳定覆盖。`verify` 的 `INSTRUCTION_STABILITY_EVIDENCE_READY` 不能作为完成标记。

## 三、约束追踪合同

合同只保存可验证关系，不复制整份 SKILL.md。核心对象：

| 对象 | 必须回答的问题 |
|---|---|
| artifact | 真实输入、源文件、中间件、渲染件、最终件或状态文件是什么？ |
| producer | 哪些实现文件真实产生被验证产物，如何绑定其当前清单？ |
| checker | 谁检查、用什么模态、检查哪个阶段、是否独立于生产者？ |
| constraint | 哪条要求是一票否决，来源在哪，由哪些 checker 和 case 覆盖？ |
| case | 哪个正常样例应通过，哪个故障、变异或历史样例必须阻断？ |
| observable | 多轮执行中哪些关键集合、数值或协议结果应保持稳定？ |

### 每条硬约束的最低闭环

每条 `severity=hard` 的 constraint 必须同时满足：

- 权威要求旁有全局唯一 `<!-- skill-lint:constraint CONSTRAINT-ID -->` 锚点，`source_refs` 使用相同 ID；全部显式锚点与合同 hard constraints 必须精确双向映射。
- 候选外硬约束基线绑定当前候选聚合哈希，完整枚举门禁自动发现的 requirements sources/exclusions，并与合同的全部 hard constraint IDs 和 source refs 完全相同；evaluator Ed25519 signature 有效，且纳入的 requirement sources 中没有未加 marker 的规范行。
- 至少映射一个 `kind=active` checker；合同中的 `independent_from_producer=true` 只是声明，正式结论还必须复算当前候选的 Harness review evidence。
- constraint 要求的产物阶段包含在 checker 的 `artifact_stages`。
- requirement type 与 checker modality 匹配。
- 至少一个带候选内 fixture 的 positive case，并在正式 verify 中真实返回 0。
- 至少一个带候选内 fixture 的 fault 或 mutation case，并在正式 verify 中返回声明的具体非零退出码。
- `historical_failure_known=true` 时至少一个 historical fixture，且必须真实触发声明的阻断退出码。
- constraint 与 case 的双向映射完全一致，不能一边声明、一边漏记。
- 每个负向 case 只隔离一个 constraint 和一个 checker；失败输出必须精确报告该 constraint，不能用无关异常或另一个规则的失败冒充回归覆盖。
- 至少关联一个由其 checker 输出的 artifact-derived observable；不能让一个无关全局指标稳定就替其他硬约束得出“无漂移”。
- 至少关联一个合同化 measurement，声明 `value_type`、`condition` 和 `expected`；正例/真实 run 必须满足阈值，负例必须实际违反目标约束阈值。
- evaluator-signed held-out 清单为每条 hard constraint 提供候选外正例和反例，且 fixture SHA-256 与当前候选绑定。

人工审阅仍可评价语义质量，但不能冒充客观硬门禁。对于内容审稿 Skill，可以把“是否逐项输出全部审阅维度、是否引用真实来源位置、是否完成 finding 状态转换”做成 schema/coverage/state checker；具体意见是否专业继续由人工或独立语义评测判断。

## 四、验证模态必须匹配

文本 grep 不能证明几何正确，XML 合法也不能证明最终图像不重叠。门禁使用下列窄映射：

| requirement type | 可接受 checker modality | 典型对象 |
|---|---|---|
| `text` | text / schema / semantic | 禁用词、标题、引用 |
| `schema` | schema | JSON/YAML/报告结构 |
| `coverage` | schema / semantic / human | 必审维度、finding ID、任务覆盖 |
| `geometry` | geometry / render / visual | bbox、定位、重叠、越界 |
| `appearance` | render / visual | 颜色、透明度、实际视觉效果 |
| `semantic` | semantic / human | 论证质量、作者意图、判断合理性 |
| `interaction` | interaction / e2e | 点击、状态转换、真实用户路径 |
| `state` | state / integration | task/finding 关闭、合并后复算 |
| `security` | security / static / sandbox | 危险执行、外联、敏感访问 |

验证器可以比最低要求更强，但不能换成不相干的便宜检查。典型 Hard Fail：

- 用 text grep 验证 SVG 元素不重叠。
- 用 source checker 验证 final/rendered 产物。
- 只验证 review JSON 的 `status: pass`，不读被审文件。
- 只扫描 SKILL.md 禁止项，不执行生产器和模板。

## 五、真实产物阶段

constraint 必须声明它要求检查的阶段：

- `input`：用户输入或固定样本。
- `source`：Markdown、SVG 源码、配置等权威源。
- `intermediate`：转换或修订过程产物。
- `rendered`：浏览器、排版器、渲染器实际输出。
- `final`：用户最终拿到的文件或报告。
- `state`：task/finding/PR/交接状态。

阶段不能互相代替。书稿源文件验收应检查 canonical Markdown 和本地引用；SVG 的位置、遮挡和颜色应检查 rendered 产物；任务是否真正落地应检查 source/final/state，而不是只读 review 报告。

## 六、active checker 输出协议

`verify` 会在每一轮真实产物上亲自重跑合同中的全部 active checker。checker：

- 通过返回 0，失败返回非零。
- 可以输出普通日志，但 stdout 最后一行必须是 JSON。
- 最后一行只能包含：

  ```json
  {
    "passed_constraint_ids": ["REPORT-COVERAGE"],
    "artifact_sha256": {
      "final-report": "<sha256>"
    },
    "measurements": {
      "REPORT-COVERAGE": {
        "covered-count": 3
      }
    },
    "observables": {
      "covered-sections": ["structure", "content", "figures"]
    }
  }
  ```

- `passed_constraint_ids` 必须精确覆盖合同映射给该 checker 的全部约束；少一个即阻断。
- `artifact_sha256` 必须精确绑定 checker 实际收到的全部 artifact；门禁自行复算，不接受 checker 只声称“读过”。
- `measurements` 必须逐约束提供合同声明的完整 measurement IDs；门禁检查 integer / number / boolean / string / string_set 类型，以及 equals / gte / lte / contains_all 条件和 expected 阈值，不能只回显 constraint ID 或任意非空字典。
- `observables` 必须与合同映射完全一致；不能运行后临时增加或省略指标。
- checker 不得修改候选或运行产物。
- 合同中的 positive、fault/mutation 和 historical fixtures 也会被实际执行；只登记 case 名称而没有 fixture 和预期退出码不能通过。负向 checker 最后一行必须输出 `failed_constraint_ids`、fixture 的 `artifact_sha256` 和逐约束 `measurements`，且目标 ID 必须与该 case 精确相同。
- 动态执行使用 `shell=False`、最小环境和临时 HOME，但仍不是沙箱；未知第三方候选不得在普通环境执行。

## 七、什么叫漂移

不要比较整份自然语言输出的字节哈希。合理措辞变化不等于失败。只比较任务合同中的关键可观察不变量：

- `exact`：协议版本、verdict、必需 marker 等必须完全相同。
- `set_equal`：必审维度、finding ID 类别、处理对象集合等允许排序变化，但集合不得增减。
- `numeric_tolerance`：数量或度量允许在明确 tolerance 内波动。

每个 observable 必须显式列出它证明的 `constraint_ids`，且每条 hard constraint 至少有一个 artifact-derived observable。任何硬约束在任一轮未被 checker 报告、任一必需 artifact 缺失、checker 非零退出、集合漂移或数值越界，都不能生成稳定性回执。

## 八、历史回归样本

下列真实演化模式应作为 golden case 类型长期保留：

校准来源为公开 Git 历史中的最小失效结构：writing-reviewer v0.13.0（`ac40de7`）/ v0.14.0（`0be4361`），以及 svg-book-illustrator v1.8.4（`ad7aaed`）/ v1.8.8（`62148b1`）。版本号和短 SHA 只用于回溯 failure family；测试 fixture 必须去具体化，不复制真实书稿或用户材料。

### 内容审阅类

- `WR-TEXT-ONLY-CLOSURE`：报告和待办自称完成，但没有 active checker。
- `WR-EMPTY-ACTIVE-RULESET`：规则集为空或按 stage 过滤后为空，循环未执行却返回 0。
- `WR-READSET-FRESHNESS`：只修改 Markdown 引用的本地资源或只重命名文件，旧证据仍有效。
- `WR-STALE-STATUS`：candidate 已变化，status 仍展示旧 JSON 的 PASS。
- `WR-CLOSURE-TRANSITION`：blocking finding 未关闭，却把 task 标为 completed。

### SVG / 视觉生产类

- `SVG-GEOMETRY-MODALITY`：源码合法，但文本超出卡片或图例与标签 bbox 重叠。
- `SVG-PRODUCER-DOC-CONTRADICTION`：SKILL 禁止 `<style>`，自身 generator/template 仍输出 `<style>`。
- `SVG-NEGATIVE-FIXTURE-CANARY`：故意弱化 checker 后，历史坏样本必须让 checker 测试失败。
- `COMPOSITION-CONTRACT-CONFLICT`：producer 禁止某特性，reviewer 却声明允许。
- `REPEATABILITY-AND-MUTATION`：前两轮关键约束集合一致；任一 generator、template、引用资源或规则变化后，旧证据必须失效。

这些名称是失效类别，不要求把真实书稿、客户数据或大段历史产物复制进 Skill。fixture 应去具体化、最小化，同时保留能触发缺陷的结构。

## 九、结论分层

| 标记 | 证明什么 | 不证明什么 |
|---|---|---|
| `HARNESS_REVIEW_VERIFIED` | 当前候选、策略、checker 与故障用例的审查证据有效 | 多轮真实产物没有漏项 |
| `INSTRUCTION_STABILITY_EVIDENCE_READY` | 动态门禁刚刚完成候选 checker、公开/隐藏正反例和多轮产物复算，并生成待签草稿 | 尚未取得 evaluator 的离线签名，不能声明 VERIFIED |
| `INSTRUCTION_STABILITY_VERIFIED` | evaluator Ed25519 签名有效；当前候选先通过可复算 Harness 审查；外部约束基线和 held-out cases 有效；至少三份签名执行记录的真实产物逐约束通过，measurement/observables 未漂移 | 签名不证明 evaluator 的事实陈述必然真实；也不证明语义意见一定专业或业务结果绝对正确 |
| `DOMAIN_VERIFIED` | 目标 Skill 的领域验证器通过 | Harness 证据与多轮覆盖一定完整 |
| `NOT_VERIFIED` | 证据不足或只做了静态评议 | 不能反推 Skill 一定错误 |

声称“稳定完成”时，至少同时需要 `HARNESS_REVIEW_VERIFIED`、`INSTRUCTION_STABILITY_VERIFIED`，以及任务声称涉及的 `DOMAIN_VERIFIED`。三个标记分别解决证据完整性、重复执行覆盖和业务正确性，不能互相替代。

## 十、边界

- 三轮是最低诊断门槛，不代表统计上证明所有未来执行。Ed25519 签名证明证据由对应私钥持有者签发并未被篡改，不证明签发者没有错误陈述；高风险场景仍应使用受控 CI runner、审计日志或远程可信执行。
- active checker 证明可观察不变量；语义质量仍需要固定样本、独立审阅和必要的人类判断。
- evaluator 私钥必须由独立 reviewer/CI 的离线签名边界持有，不能交给候选作者、producer 或 checker；正式验证进程只读取公钥。如果私钥与候选执行共享主机、进程树或可读工作区，签名只能证明完整性，不能证明独立性。
- `skill-lint` 不自动生产目标 Skill 的 checker，也不替代 `agent-eval-lab` 的正式版本晋级评测。
- 草稿与签名回执均只允许新建，不允许覆盖或跟随目标符号链接；候选、合同、外部基线、Harness evidence、运行证据、producer log、producer 实现或产物变化后必须生成、签名并复验新回执。
- 没有合同不等于 Skill 一定不可用，只表示它不能证明自己具备稳定的指令遵循和产出闭环。
