# 法律 Skill 对齐与评测专家套件

> [下载完整专家套件](https://github.com/cat-xierluo/legal-skills/releases/latest/download/suite-legal-skill-design-evaluation-0.1.0.zip)
> 新增套件尚未发布；上方为下次 Release 的预留入口，发布前可下载通过 CI 后生成的 PR Preview 产物。成员独立下载以已发布资产为准，可能早于源码版本。

面向希望沉淀法律经验、改进已有法律 Skill 的法律专业人员。聚焦“要做什么”和“做出来后是否真正可用”，与通用工程开发及发布套件分工。

本套件仅策展与分发，不提供运行时编排或套件入口 Skill。

## 适用场景

- 把法律经验、范本或 SOP 梳理为结构化、可交接的 Brief；
- 检查已有法律 Skill 的目标、边界、输入输出和验收依据；
- 用脱敏材料评估真实法律产出，定位修复点并复测；

## 不适用场景

- 不承诺一键生成完整 Skill，不把 Brief 当作已经实现的 Skill；
- 不替代正式法律意见，不以静态 lint 通过证明业务质量或稳定性；
- 不把不同法律场景按总分排名，不用模拟产出冒充候选真实运行；

## 包含的 Skills

| Skill | 在本套件中的作用 | 单独下载 |
| :--- | :--- | :--- |
| [legal-skill-alignment](../../skills/legal-skill-alignment/) | 把法律经验、文书和 SOP 对齐成 Legal Skill Brief，明确输入输出与交接阻断项 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-skill-alignment-1.0.7.zip) |
| [skill-lint](../../skills/skill-lint/) | 审查通用结构、设计、Harness 与候选绑定质量证据 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/skill-lint-2.9.1.zip) |
| [legal-skill-evaluation](../../skills/legal-skill-evaluation/) | 消费通用质量结论，评测指定法律场景产出并定位最小修复单元 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-skill-evaluation-0.8.12.zip) |

## 建议使用方式

1. 从经验或素材开始时使用 `legal-skill-alignment`，明确五问及 operator / principal / audience 等角色，产出 Brief 和待确认清单；
2. 分别核对 `structurally_complete` 与 `handoff_ready`：结构齐全不代表可交接，存在 blocker 时先澄清；
3. 让 `skill-lint` 做设计预检；需要创建/修改 Skill 时，将可交接 Brief 交给宿主提供的 `skill-creator` 或用户指定实现者。该工具不在当前公开仓库及本套件内，须另行具备；
4. 实现后用 `skill-lint` 核对当前候选的通用质量证据；已有候选可以直接从这里进入，不必重复对齐；
5. 用 `legal-skill-evaluation` 锁定单一法律场景、候选快照和评测模式。标准模式准备熟悉、同类不熟悉、缺少背景三份脱敏材料，真实运行并保留产物和收据；
6. 依据通用门禁、法律六维度及律师判断定位最小修复单元；修改候选后重新绑定并复测。材料或证据不足时保持 `NOT_VERIFIED`，不得宣称正式验收通过；

## 安装方法

下载并解压套件 ZIP，把其中 `skills/*` 复制到 Agent 的 Skills 根目录；不要把套件外层目录当作单个 Skill 安装。发布前可下载通过 CI 后生成的 PR Preview 构建产物。也可按成员表单独安装。多个套件有同名成员时，先核对版本，避免旧包覆盖新版；源码符号链接不是跨平台安装包。

按各成员说明准备 Python、候选源码、真实运行环境与脱敏测试材料。自动门禁只核验其声明范围，脚本运行成功不等于法律业务效果通过。无需为对齐和评测默认配置多 Agent、邮件或 Git 发布工具。

## 人工复核与使用边界

套件只做策展与分发，不自动执行上述流程。`skill-creator` 是外部实现前提，不是隐藏成员；缺少实现工具时仍可完成 Brief 或评估已有候选。法律领域评测不能冲抵通用阻断项，快速模式保持 `NOT_VERIFIED`。正式/发布验收需相应模式的当前候选证据和人工判断，本套件本身不颁发全场景质量认证。

## 版本与许可证

当前套件版本为 `0.1.0`，尚未完成真实业务端到端验证。套件本身不设独立许可证；各成员 Skill 按其目录内 `LICENSE.txt` 分别授权，下载或使用套件不改变成员原有许可条件。含 CC BY-NC 成员，不得把整套宣传为全部 MIT 或可自由商用。
