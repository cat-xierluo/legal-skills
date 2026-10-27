# 变更日志

## [1.28.0] - 2026-10-27

### 公开化与修复

- 发行构建从指定 Git 提交读取完整通用文件允许清单，支持仓库根 `self-evolve/` 与 `skills/self-evolve/` 两种布局；未知新增文件、非法路径、符号链接和已有输出均拒绝。
- 自用与公开使用同一套完整代码、文档、示例和测试；仅排除个人配置、运行状态与内部维护材料，不裁剪功能或另做精简版本。
- `data_root.yaml`、`core_skills.yaml`、`asset_owners.yaml` 和 `scheduled_tasks.yaml` 均作为本机配置，不入 Git 或发行包；旧调度示例默认关闭，填写时区并显式启用后再使用。无配置时给出可执行引导。
- 通用文档与历史变更记录去除私人运行标识、会话规模及本机部署选择，保留功能机制、版本轨迹和验证边界。
- 修复课堂演示 `--keep` 的临时目录在函数返回后仍被清理的问题；需要打开报告的演示使用 `--keep`，后续命令显式绑定合成 home 和数据根。
- 工作方向分类迁入可选的本地 JSON 配置，周报与偏好提取共享通用默认；坏配置明确报错，不回显内容。
- 分别说明旧工作台的 SiliconFlow 请求、Claude CLI 模型通道与本机原文备份，以及启用旧周任务后的触发条件；默认扫描入口不调用这些能力。
- 可选 YAML 测试在缺依赖时明确跳过；需要 YAML 的隔离子进程保留父进程的依赖位置，兼容安装在用户目录的 PyYAML。

## [1.27.2] - 2026-10-27

### 修复

- Codex 附件头与未闭合宿主上下文标签进入扫描适配：只有 `## My request:` 之后的文本保留为用户原话，附件说明与宿主样板不进入 `user_excerpts`；未闭合、跨类型错配或嵌套的宿主标签使该轮保守拒绝。适配器版本升至 14，历史记录自动重读。

### 验证

- Python 3.13 全量 346 项通过；Python 3.11 workflow/report/adoption/dialect 119 项通过。新增成对回归：附件头+真人请求分离（含纠偏措辞的附件文案作为纠偏引文拒绝、真人原话通过）、未闭合/嵌套/跨类型宿主块+真人文本整轮拒绝；轮中出现的附件头也会分离。
- 隔离的多 Runtime 实际扫描用于检查已知宿主和框架标记过滤及附件分离；这一结果不代表对所有来源或注入形式的覆盖。

## [1.27.1] - 2026-10-26

### 修复

- 收紧“用户明确纠偏”的来源判定：扫描层只保留助手轮之后出现的用户轮，剔除 AGENTS 注入、命令包装、宿主提示、子代理/任务通知等框架噪声；真实 Codex `response_item` 用户轮保留并折叠相邻镜像，WorkBuddy/CodeBuddy `type=message` 顶层 `role` 正确映射。适配器版本升至 13，历史成功记录自动重读；旧 packet 即使 evidence_id 相同也不能回灌过期 user_excerpts。
- 同一用户轮中嵌入的 `<in-app-browser-context>` / `<external_codex_apps_open_page>` 宿主上下文整段剥离，`## My request:` 宿主分隔标记去除；宿主免责声明不能作为用户原话，同轮真实用户文本仍保留。
- `user_excerpts` 不再截断为 6 条；每条限长并由每会话字符预算显式标记截断，避免活跃会话的后续真实纠偏被静默丢弃。纠偏引文必须自身包含明确的纠正/否定语义且逐字匹配保留的用户轮；纯脱敏占位符不能作为用户原话。

### 验证

- 最终 R4 回归：Python 3.13 全量 340 项通过；Python 3.11 workflow/report/adoption/dialect 113 项通过。复合用户轮回归验证：两句宿主免责声明拒绝，同轮保留的纠偏文本仍可导入；真实 Codex 与 WorkBuddy 存储方言均有正例。
- 隔离的多 Runtime 实际扫描用于检查已知框架噪声过滤；读取失败保留待重试，角色归类与噪声过滤不认证真人身份。

## [1.27.0] - 2026-10-25

### 新增

- 分析合同新增可选 `profile`：按工作行为观察、用户明确纠偏、Agent 推断分层，绑定本轮证据、适用范围、置信度和复核条件；旧分析兼容，非法结构 fail-closed。
- 扫描层记录用户轮来源（`user_excerpts`），用户原话在会话页与画像条目中单独展示。“用户明确纠偏”必须引用用户原话摘录，且该摘录能在所引证据的用户轮里逐字找到——任务指令、Agent 自述与索引摘录都不能冒充用户偏好。
- 本地 HTML 报告由六页扩展为七页，新增个人画像页。总览与画像页明确本轮发现、处理、送审和累计覆盖口径；低信息证据在会话页默认折叠为“本轮上下文”，可展开核对，可见计数只统计主证据区。

### 验证

- Python 3.13 全量 334 项通过；Python 3.11 报告/流程/采用定向 108 项通过。Python 3.14 全量受本机旧 PyYAML `collections.Hashable` 问题影响，沿用既有环境边界。
- 完成多 Runtime 扫描、分析导入与七页报告检查。浏览器回归覆盖页面布局、画像证据往返、筛选重置、复制降级与无 JS 手动复制；系统剪贴板权限与 Linux/Windows 真机仍未验证。

## [1.26.0] - 2026-10-25

### 新增

- 为已导入建议登记稳定 ID、具体修订、接受/实施/验证结果与回执。采用记录独立保存，不迁移扫描 SQLite；报告生成新的只读快照，历史分析与 HTML 保留。
- Skill 页与复制工单展示采用状态和回执引用。“已登记验证通过”代表提交者登记的结果，不代表脚本执行过测试、安装或身份认证。

### 修复

- 跨会话声明要求至少两个独立会话引用，创建动作与创建层级保持一致；显式 null 和非法字段类型返回具名错误，省略可选字段仍兼容。
- 剪贴板与兼容复制抛出异常时也能展开手动工单；区分候选文件完成、安装识别和采用后的验证。
- 校正前轮任务状态及样例解释：产品画像需求单独追踪，不把无支持引用的产品想法包装成新 Skill 沉淀。

### 验证

- Python 3.13 全量 319 项通过；Python 3.11 采用链 18 项通过。独立审查补齐“旧分析已登记/未登记，展示升级后重放”反例，均拒绝旧修订恢复。
- 实际 CLI 登记、状态与六页快照通过，保留旧扫描库与历史产物；真实浏览器桌面/390px、DOM 筛选与重置通过。原生指针工具及系统剪贴板权限未验证，Linux/Windows 真机与真实目标 Skill 安装仍未验证。

## [1.25.0] - 2026-10-22

### 新增

- Skill 沉淀页每条建议新增“复制采纳工单”：本地静态 HTML 优先使用 Clipboard API，file:// 受限时回退 execCommand，再失败展开可全选复制的工单；无脚本时 details 内文本仍可手动复制。
- 工单包含目标、字段、理由、修改点、脱敏证据、实施边界、验证与回执要求；one-off-context 明确先补独立证据或人工复核。复制工单是提示词，不是安装命令，页面仍不自动修改或安装目标 Skill。

### 验证

- 新增渲染回归覆盖复制按钮/无脚本工单、旧分析默认值、HTML 转义、one-off-context 警示与无绝对路径。
- python3.13 全量 293 tests / OK。
- 浏览器验证 Clipboard API、execCommand 降级和手动全选路径，检查页面布局、无远端资源及复制控件。

## [1.24.0] - 2026-10-22

### 新增

- Skill 建议合同新增可选 proposal_layer（patch-existing / add-reference / add-template / add-script / create）与 evidence_strength（cross-session / single-session-correction / one-off-context）：旧分析兼容导入，非法枚举 fail-closed；create 缺失时报告仅按 action 保守推断新建。
- Skill 沉淀页为每条建议显示建议层级、证据强度、匹配依据（证据条数与 Runtime、目标 Skill 库存命中）、单次上下文待复核提示；低强度建议仍可搜索和访问，不自动应用。

### 验证

- 新增旧分析兼容、字段渲染与非法枚举拒绝回归；隔离的真实来源样本用于扫描与导入检查，覆盖补 reference、补已有 Skill、新建 Skill 及相应证据强度。
- python3.13 全量 291 tests / OK；Python 3.14 全量失败为本机旧版 PyYAML collections.Hashable 兼容问题，与本次变更无关。

## [1.23.1] - 2026-10-22

### 修复（由 dot 凌晨审计整理）

- 顶层 `type=message` + `role` 的对话恢复未知载荷校验；仅已知 usage-only 元数据豁免，避免格式不认识却被记为 transcript/filtered。
- ADAPTER_VERSION 8 → 9，未变化但由旧 adapter 误过滤的输入重新处理；保留历史记录。
- 合成反例在旧 main 下出现 8 次断言失败；修后定向 61 tests 通过（public workflow、方言、载荷守卫）。未跑全量、真实用户来源、安装或课堂效果验收。

## [1.23.0] - 2026-10-21

### 修复（真实来源抽样发现的读取失败）

- **推理块**：助手回合只含 `type=thinking` 块时被判为未知载荷，整个会话读取失败。提取器按设计丢弃该块，白名单同步承认这一形态（Claude Code 与 QwenWorkCN 常见）。
- **工具行误判**：WorkBuddy/CodeBuddy 的 `function_call` 行携带 `message={usage}`，此前被当成对话行判为未知载荷。
- **顶层 role 方言**：WorkBuddy/CodeBuddy 用 `type=message`、顶层 `role` 和顶层 `content` 承载对话；提取器扩展识别，避免加载成功但文本为空。

### 新增

- QwenWorkCN 接入来源表（`~/.qwenworkcn/projects`，与 Claude Code 同源信封）。此前登记为 unsupported。
- ADAPTER_VERSION 7 → 8：旧版误记的 failed/filtered 行在新版自动重读修正。
- 课堂讲义 `references/21-teaching-demo.md` 与演示脚本 `references/22-teaching-demo-playbook.md`；`scripts/teaching_demo.py` 合成 7 类来源 + 2 个坏文件，在临时 home 与隔离数据根跑真实 CLI，供课前彩排（不写真实数据根、不触网、不调模型）。

### 验证

- 对多种 Runtime 的真实来源抽样检查修复前后的解析行为；空会话保留单独分类。
- 对真实来源运行隔离数据根的端到端对照，检查失败、增量与送审结果。
- 全量回归 278 tests / OK（273 + 5 项方言回归）。

## [1.22.0] - 2026-10-21

### 修复

- 发行构建无条件排除 `config/data_root.yaml`、`config/core_skills.yaml`、`config/asset_owners.yaml` 三个本地覆盖文件；即使旧分支仍跟踪这些文件，公开包也不携带个人路径或重点 Skill 配置。
- 本地配置退出 Git 跟踪后保留在自用工作区；发行清单显式登记排除项。

### 验证

- 新增发行构建回归：绑定当前 OID 构建公开包，断言三个本地配置既不出现在文件列表，也进入 `excluded` 清单。

## [1.21.0] - 2026-10-16

### 变更（批次 C R1 返修收口）

- SKILL.md 移除 homepage frontmatter 字段（私仓链接不作为公开分发地址；公开地址确定后统一填写）；"Python 包（仅旧工作台）"标题改为"旧工作台 + 公开流程可选 YAML 配置"。
- 支持声明统一：SKILL.md 与 references/00 的 Python 版本统一为 3.11+（3.11 全量实测；3.10 未验证）。

### 验证（批次 C R1 收口）

- 中断恢复验证使用同步屏障和 SIGKILL，检查 interrupted 标记及剩余处理去重。
- 三安静条件实证：无变化+待分析=awaiting_agent 进包；全部处置后=no_pending_evidence 静默；坏会话=partial+failed 可见。
- 分析未完成重送审：dismissed 证据跨轮保留可再次进包。
- 最终报告浏览器回归（含处置状态+已核验候选展示）全 PASS（1455/390px、跨页证据、筛选、安装说明）。

## [1.20.0] - 2026-10-16

### 新增（批次 C 出口返修 C-F1～C-F4）

- `scripts/build_release.py`：发行物绑定工具——OID 绑定的 git archive、排除维护材料（TASKS/DECISIONS/RESULT 保留在维护源）、逐文件 sha256+manifest_sha256、homepage 显式覆盖（未传=保留并登记未公开）。
- SKILL.md 支持声明对齐实测：Python 改 3.11+（3.11 全量 272 tests 实测通过；3.10 未验证）；PyYAML 就近说明（自定义配置文件必需，缺=可执行报错）；新增"平台与验证边界"节（macOS 本机验证、Linux XDG 未真机、Windows 未验、跨宿主/签名稳定性未认证）。
- references/20 ADAPTER_VERSION 同步 v7 并补 v5-v7 沿革。

### 修复

- `public_report.py` 处置状态行的 f-string 嵌套引号为 Python 3.12+ 语法，3.11 SyntaxError——改辅助函数，全脚本 3.11 编译与回归通过。

### 验证（批次 C 出口）

- 在默认与个性化环境验证扫描、独立分析、导入、报告及后续接续；检查中断恢复和浏览器跨页证据、筛选与安装说明。

## [1.19.0] - 2026-10-16

### 修复（批次 B 第三轮返修 B-F3 调用证据/B-F4 三组缺口）

- B-F3（调用证据）：使用隔离上下文的独立消费者分析冻结输入，覆盖完整处置、部分处置与证据可靠性；包外引用不进入导入版。
- B-F4 缺口1（同名旧决定授权新内容）：候选生成改为提案身份绑定——target_skill 与内容指纹（proposal_fingerprint，与 store 同算法）双重匹配，同名不同内容的旧决定不授权新提案。
- B-F4 缺口2（结构合法但产物不存在）：candidate_file 真实性核验移到导入时服务端——原始路径先核验文件存在+sha256 一致，核验结论（verified 布尔）入库；报告不含原始本机路径（脱敏合同），虚构路径/哈希核验 False 并如实显示"真实性核验未通过"，保持"尚无安装包"。
- B-F4 缺口3（accepted 线端到端）：全链实证——消费者 C3 提案（同内容指纹）commit（in-chat auto-accept，committed_accepted）→ generate_candidate 生成候选草稿（sha256/来源分析/证据绑定）→ candidate_file 注入分析导入 → 六页 skills 页显示"候选草稿已生成（导入时已核验产物哈希一致）"+哈希前缀+无原始路径泄露。

### 技术优化

- 新增回归更新为 R2 终版合同（服务端核验 verified/虚构路径如实说明/无路径泄露/结构错误拒绝），全量 272 项通过。

## [1.18.0] - 2026-10-16

### 修复（批次 B 第二轮返修 B-F1 终版/B-F3 终版/B-F4 连通 + P2 随手修）

- B-F1（P1 终版）：处置冲突检查移到报告发布/JSON 写盘之前——拒绝导入零新增产物（拒绝后目录文件集合不变，回归锁定）；既有的一致修订行为保留。
- B-F3（P1 终版）：按裁定完成三轮真正独立消费者分析——冻结 fixture v3（原四场景+重复副本+提示注入样本，manifest 留盘），三个隔离数据根（隔离消费状态）各扫一轮（3 selected/3 filtered），三次无旧上下文消费者分析输出留盘：C1 全处置（含"用户自述连续三次=单会话自述非独立观察"表述修正+副本同源理由+注入 dismissed）、C2 部分处置（安全审查视角仅处置注入，业务证据保留待下一轮）、C3 证据可靠性视角（副本 insufficient_material 待第二独立来源+create 提案）。覆盖裁定点名的重复副本/敏感注入/部分处理场景与逐类理由。
- B-F4（P1 连通）：新增 `scripts/generate_candidate.py`——从已导入分析+proposal_store 决定记录生成外置候选（accepted→候选草稿含 sha256/来源/证据绑定；rejected/observe→决定说明 JSON；无决定记录不生成）；分析合同新增可选 `candidate_file`（path+sha256 结构校验 fail-closed）；Skill 沉淀页如实展示"候选草稿已生成（待人工审阅，非安装包）"或保持"尚无安装包"。端到端演示走通：C3 create 提案→commit→observe 决定→候选说明文件生成（隔离数据根）。
- P2 随手修（非阻断）：历史 sent 集合读取对顶层非映射/坏 JSON 的历史包跳过并结构诊断，不再让 AttributeError 冒泡。

### 技术优化

- 新增 2 项回归（冲突拒绝零新增产物/候选文件往返与校验），全量 272 项通过。

## [1.17.0] - 2026-10-16

### 修复（批次 B 审计返修 B-F1～B-F4 + P2 状态说明）

- B-F1（P1）：处置为追加式账本状态——已消费证据不可被后续分析修订撤销/改判，冲突修订以 `disposition_conflicts_reviewed` 拒绝（历史分析与消费记录保留）；导入返回值以账本现状（含历史消费）为准，与下轮送审队列一致。
- B-F2（P1）：送审轮转——曾在旧包中且未消费（dismissed/未处置）的证据在包选择中后移，新证据优先进入；dismissed 证据跨轮保留可见待人工，不再永久阻塞新证据（容量+1 跨轮推进回归锁定）。返修中连带抓获并修复 run_id 被历史 run 循环变量遮蔽导致报告写入旧 run 目录的实现 bug（spy 实证两轮同 run_id）。
- B-F3（P1 验收缺口）：冻结合成 fixture（四场景：有价值发现/低价值/单次偏好/证据不足）三轮扫描全绿（初筛分型正确、轮2/3 全 unchanged），无旧上下文消费者分析四份实际输出留盘（A=analyzed 消费对账、B=安静路径、C=一致修订、D=冲突修订拒绝），供上游对照保留/剔除理由与来源。
- B-F4（P1 交付缺口）：端到端资产闭环演示（全部合成、明确标注）——三份独立提案走 commit→decide→applied→verify 全生命周期：accepted（in-chat auto-accept 于 inventory resolved 后生效，applied+verified 后半圈入账）、rejected（理由入账）、observe（暂不决定）；resolved 门如实呈现（未 resolved 时接受 fail-closed）。
- P2 状态说明：处置状态节区分"已分析/待补证据/低价值待人工/未声明"四类计数，待补证据标注等待条件（材料补齐后新扫描生成新证据再送审）。

### 技术优化

- 新增 4 项回归（修订冲突拒绝/一致修订+账本现状对账/轮转容量+1 跨轮推进/dismissed 跨轮保留可见），全量 270 项通过。

## [1.16.0] - 2026-10-16

### 新增（批次 B：UP-03/UP-04）

- 逐证据处置合同：分析输出新增可选 `evidence_dispositions`（analyzed/dismissed/insufficient_material + 脱敏 note），只有 analyzed 与 insufficient_material 在导入后不再送审；dismissed 与未声明处置的证据跨轮保留待分析/待人工——空分析、部分分析绝不静默消耗整包证据；处置结构错误 fail-closed 拒绝导入。导入返回 `evidence_consumed`/`evidence_retained` 对账值。
- 深度分析页新增"证据处置状态"节：已处理/保留待分析计数、dismissed 与未处置证据逐条可见（含 note），仅带处置字段的分析显示（旧格式分析不受影响）。

### 技术优化

- 新增 5 项回归（全量处置消费/部分处置保留/dismissed 不消费/空处置不消耗+结构错误/处置状态页渲染含旧格式无节），全量 268 项通过；references/18 分析合同补处置字段文档。

## [1.15.1] - 2026-10-16

### 修复（R4 审计收尾 A-SQL-SRC-01-R4-DELETED/A-SQL-SRC-01-R4-REGTEST）

- 删除竞态（P2）：任务在发现后被软删/移除时，快照查询空结果从 `[0]` IndexError 改为具名 `source_changed_during_read`——整轮 partial、正常会话继续、失败对象入账（新增集成回归：discover-then-delete 场景三方断言）。
- WAL 回归测试严格化（P2）：显式启用 WAL、关闭自动 checkpoint、连接保持打开、checkpoint 后提交仅存 WAL 的哨兵记录；新增检测力证明（独立 immutable 连接确认主库看不到哨兵）；删除恒真断言。

### 技术优化

- R4 四项行为修复（快照查询/预检副本/孤立伴生/dict text）全部 ACCEPT 保持；全量 265 项通过。

## [1.15.0] - 2026-10-16

### 修复（第四轮审计返修 A-SQL-SRC-01-R3-WAL/A-F1-R1-R3-NOSIDECAR/A-SQL-SRC-01-R3-ORPHAN/A-F3-R5）

- A-SQL-SRC-01-R3-WAL（P1）：源库查询改为**临时副本即查询对象**的一致快照；immutable 直连可能漏掉仅存在于 WAL 的已提交数据，且跳过活动源库的锁与变化检测；快照后复核源文件指纹（size+mtime_ns），变化报 source_changed_during_read 可重试。
- A-F1-R1-R3-NOSIDECAR（P2）：无伴生的 WAL 模式主库在原地 ro 打开后仍会创建伴生——账本预检无例外全部走临时副本（副本内 WAL 最新内容仍可读到），拒绝路径对原件零字节动。
- A-SQL-SRC-01-R3-ORPHAN（P2）：孤立伴生（主库缺失+WAL/SHM 在）显式 read_failed，不再冒充"未发现"。
- A-F3-R5（P2）：字典 text message（`{'message':{'type':'text','text':…}}`）按提取器同套判定放行，不误拦；adapter 升至 v7。

### 技术优化

- 第四轮上游反例全部转合成回归（+4 项：WAL 独有提交可见/无伴生不变/孤立伴生失败/dict text 提取），全量 264 项通过。TOCTOU 边界：自家账本由 scan.lock 串行化协作写者，锁外替换未覆盖；生产源库以快照内一致性和变化检测覆盖。

## [1.14.0] - 2026-10-16

### 修复（第三轮审计返修 A-F1-R1 终版/A-F1-R2/A-SQL-SRC-01/A-F3-R1 终版/A-F3-R4）

- A-F1-R1（P2 收口）：非零主库预检改为**临时副本**校验（有伴生时）或原地只读连接（无伴生时，无法产生副作用）——拒绝路径对主库/WAL/SHM 字节与存在性零变化（探针实证）；正常 WAL 中最新已提交内容在预检副本中仍被读到。
- A-F1-R2（P1）：主库缺失但存在 WAL/SHM → 文件级拒绝"疑似崩溃现场，保留原文件不自动重建"（此前被当首次初始化、新建主库并删除原 WAL）；新用户定义收窄为相关数据库文件全部不存在。
- A-SQL-SRC-01（P1）：ZCode 源库读取统一走 `_sqlite_source_open`——危险形态（主库缺失/零字节+伴生）不打开，按来源失败记账；正常形态带伴生经临时副本预检后 immutable 直连。
- A-F3-R1（P2 终版）：载荷白名单与提取器逐分支对齐——未知 type 块（future_text/image 等，提取器实际静默丢弃）判未知载荷显式失败，不再"显示成功但内容看不见"。
- A-F3-R4（P2）：`message` 为字符串是可提取合法形态（提取器 message 优先规则），不再误拦；adapter 升至 v6 使 adapter 5 误记对象重读修正。

### 技术优化

- 第三轮上游反例转为合成回归（SHM 零副作用/主库缺失保留/ZCode 源库/future_text/string message）；全量 260 项通过。

## [1.13.0] - 2026-10-16

### 修复（第二轮审计返修 A-F1-R1/A-F2-R1/A-F3-R1/R2/R3）

- A-F1-R1（P1）：拒绝路径不再破坏伴生 WAL——实测 mode=ro SQLite 打开零字节主库也会触发恢复删 WAL，改为**任何 sqlite3 连接前**的文件级检查拒绝零字节主库+未合并 WAL/SHM；结构预核验全部经只读 URI 连接完成，全部六表列结构纳入核验（runs/run_sessions/analyses/reviewed_evidence 错列同样拒绝）。
- A-F2-R1（P2）：skill_sources 假值（false/0/[]/{}）类型检查先行，不再被空值跳过静默禁用来源。
- A-F3-R1（P2）：载荷白名单按提取器实际能力重写（`_content_extractable` 镜像 extract_message_text/extract_codex_text 可理解形态）——旧方言未知 list 项、嵌套 content dict、纯 type 行、Codex 未知 message 载荷均显式失败；带 type 键的已知/未知媒体块（如 image）与正常文本/工具块行为保留。
- A-F3-R2（P2）：adapter 升至 v5，旧版误记的 filtered 对象在新版重读并修正。
- A-F3-R3（P2）：共享读取器传播打开失败后，dream_sweep recent 与 backfill 两消费循环补逐会话 OSError 兜底——单对象失败可见（stderr+计数）、其余对象继续（legacy 对照重放实证）。

### 技术优化

- 第二轮上游反例全部转为合成回归（+5 项），全量 260 项通过；WAL 保留/假值拦截/升级重读/legacy 对照四组上游探针逐一重放实证。

## [1.12.0] - 2026-10-16

### 修复（上游审计返修 A-F1～A-F4）

- A-F1（P1）：既有账本零写入核验补齐——同版本但缺业务表、sessions 列结构不符一律拒绝（缺表/错列写入诊断）；零字节主库带伴生 WAL/SHM 不再被当作新用户初始化（崩溃未 checkpoint 场景）；此前"只有 meta 表"的库会被自动补建全部业务表的反例已封死。
- A-F2（P1）：存在但无法解释的配置绝不静默回退——data_root.yaml 损坏/顶层非映射/值非字符串/相对路径/缺 PyYAML 时 `assert_runtime_ready` 首先拦截并给可执行诊断，不再把账本静默切到平台默认根重扫；core_skills.yaml 的 skill_sources 结构错误（非映射、值非字符串）与 `python -S` 缺解析能力同样报错，不静默丢个人来源。修复中连带发现并纠正 `_DATA_ROOT_CONFIG_ERROR` 全局初始化晚于求值导致错误被覆盖为 None 的实现 bug。
- A-F3（P1）：JSONL 读取器打开失败（权限/IO）不再返回空统计，向上传播按 failed 分类（PermissionError 入账、恢复权限后按对象重试成功）；键形态认识但 content 为不可解析新结构时抛 `unsupported_message_payload` 显式暴露，不再静默过滤成 metadata_only。已知纯工具记录（tool_use/tool_result 块）的正确过滤保留。
- A-F4（P2）：空会话计数合同统一——首次处理记 new+empty+filtered 且与 run_sessions.outcome 对账，修订后记 updated，未变跳过 unchanged；本轮统计、对象账本、累计计数三方一致。

### 技术优化

- 上游探针转为可维护合成回归（+6 项：部分结构库、错列库、零字节+WAL、无读权限、未知载荷、空会话计数对账），全量 255 项通过。

## [1.11.0] - 2026-10-16

### 修复

- 账本打开顺序加固：既有 SQLite 文件在任何建表 DDL 之前完成 sqlite_master/meta/schema_version 三重核验（无版本行的外部库同样 fail-closed），未知/外部结构的账本字节不动、不被 `CREATE TABLE IF NOT EXISTS` 写入。

### 改进

- 补齐增量与恢复合同的对象级测试：三轮合成场景（未变/追加/新增/坏格式→修复）、同大小改写由 stat 修订捕获、ZCode 读取中修订变化 fail-closed、文件移动新对象+历史保留+session_ref 去重、来源目录消失与复现的行数守恒；references/18 补写未知库零写入保证与旧 session-summaries 的后续接续方式（对象级来源绑定、显式导入，未实现前并行保留不冒认）。

### 技术优化

- 新增 5 项回归，全量 249 项通过；全程隔离数据根验证，不依赖修改生产库。

## [1.10.0] - 2026-10-16

### 改进

- Runtime 适配升级为 v4：识别 Claude 历史顶层转录的 `role`+`content`、`type`+`content` 方言与纯 `tool_use` 会话（此前误报 unsupported_jsonl_schema）；零行 JSONL 与空 Gemini 会话分类为 `empty_session`（记账 filtered、报告显示"空会话"），不再污染失败统计或拉低来源状态。
- 新增 `references/20-runtime-support.md` 支持矩阵：各 Runtime 存储/消息结构/完整性标记/空会话与失败分类、ZCode 完整消息探测结论（cli/log 仅遥测、exec 仅工具输出、checkpoints 清单加密——授权范围内无完整源，保持索引摘录降级）、未接入平台的显式补充来源方法与去重口径；SKILL.md 增加引用。

### 技术优化

- adapter 版本升级使此前 failed 的历史会话在修复后自动重读，无需清账本；新增 4 项 adapter 回归（旧格式正例、纯工具回显反例、空 Gemini、零行文件），全量 244 项通过。

## [1.9.0] - 2026-10-16

### 改进

- 实际本地配置不再入 Git：`config/data_root.yaml`、`config/core_skills.yaml`、`config/asset_owners.yaml` 退出跟踪并加入忽略规则（本地副本保留）；`config/scheduled_tasks.yaml` 作为随 Skill 发布的任务注册表保持跟踪。新用户检出即用：缺省走平台默认数据根与默认 agent 目录来源，从 `.example.yaml` 复制填写即可恢复个性化。

### 修复

- 修正 `self_evolve_paths` 数据根文档字符串中的配置文件名笔误（core_skills.yaml → data_root.yaml）。

### 技术优化

- `refresh_skill_inventory` 对损坏的 core_skills.yaml 从静默返回空改为可执行报错（rc=2 提示修复方向），缺文件仍走默认来源；新增 6 项配置缺省/覆盖/损坏回归（数据根三层优先级、inventory 缺省与坏配置），全量 240 项通过。
- SKILL.md 与 `references/02-core-skills-yaml.md` 就近说明实际配置不入 Git、复制 `.example` 填写与缺省行为。

## [1.8.1] - 2026-10-16

### 改进

- 报告改为总览与五个专题二级页面：深度分析、Skill 沉淀、会话与证据、扫描与覆盖、运行说明；统一侧栏、面包屑、当前页状态和窄屏导航，首页突出关键结果与下一步。
- 分析和 Skill 建议可跨页定位并自动展开具体证据，会话页可返回原发现/建议；补充来源、完整性、建议类型和初筛筛选、搜索、空结果与重置。
- 全部页面保持同目录静态 HTML、相对链接和零远端资源；先写齐子页，再发布总览。重复导入校验完整文件组，缺页或内容变化时失败退出，旧报告继续保留。

### 验证

- 增加多页内部链接/锚点、搬移目录、内容边界、缺页/篡改拒绝与发布中断回归；增加可复用的真实浏览器脚本。执行结果见 TASKS.md。

### 文档完善

- 依据用户澄清将更新计划升为 r2：只维护同一 `self-evolve` 源码、功能与版本，新增先行个性化配置/忽略规则任务；分发改为同源产物，补配置兼容、双配置路径及已跟踪文件检查，执行尚未开始。
- 在 TASKS.md 建立公开适配下游更新计划 r1，固定 1.8.1 实现基线，按来源/状态、分析/资产、分发/周期/验收三批衔接；保留单一任务源和完整开工说明，计划本身不代替派发或发布授权。

## [1.8.0] - 2026-10-16

### 新增

- 增加公开版工作流：多 Runtime 只读发现与适配、SQLite 持久增量账本、当前 Agent 分析包及校验导入、自包含 HTML 报告；无需独立模型 API Key，核心仅依赖 Python 标准库。
- 支持 Claude/Codex JSONL、WorkBuddy/CodeBuddy JSONL 和 trace、Gemini JSON，以及 ZCode 只读任务搜索索引摘录；明确索引摘录与完整对话的差别，其他 Runtime 显示未接入格式或实际覆盖错误。
- 保留初始化时间、来源配置、扫描轮次、逐输入修订、失败与历史报告；未变跳过、追加重读、失败可重试、预算回填、中断识别、跨来源副本合并；已发现的存储根可跨 Runtime 环境复用。
- HTML 展示覆盖/初筛、Agent 全面分析、证据、Skill 升级/新建建议与人工安装指引；新 Skill 没有真实包时不生成下载链接。分析绑定当前包及本地轮次，拒绝篡改、未知引用和已被替代证据。

### 改进

- `first_run.py` 默认切换到无独立 Key 的公开版采集/报告入口，不再自动调用旧云端偏好分析；旧工作台与状态继续保留，详细合同移入兼容参考。
- 入口按公开扫描、当前对话沉淀和历史排障分层；补充首次初始化与每周定时 Agent 调用提示词，区分采集完成、分析完成、部署和真实周期触发。
- 具体业务文书标题保守隔离；默认不复制原文，脱敏后逐字段转义展示，报告没有外部资源或安装/执行按钮。

### 验证与边界

- 新路线验证包括增量、失败/中断恢复、来源记忆、去重、预算、隐私、证据绑定和 CLI；完成真实来源小批次试跑与网页交互检查，证据见 TASKS.md。
- 这是通往公开发布的首批候选：更多 Runtime、干净分发包、完整消息格式与多轮语义质量仍待后续验收；未公开发布，未部署每周任务。

## [1.7.5] - 2026-09-23

### 文档完善

- 更新 Review Inbox 候选所引用的 Hermes 桌面插件开发 Skill 名称；原账本和人工决定边界不变。


## [1.7.4] - 2026-09-23

### 文档完善

- 登记 Review Inbox 的 Hermes 插件化候选，并固定认证、隐私门控、revision 与人工决定账本的迁移边界。

## [1.7.3] - 2026-08-11

### 新增:首次一键引导 first_run.py

新人跑一条命令完成全部初始化 + 自动开 panel,解决「首次要跑 5 个命令才看到东西」的痛点。

- `scripts/first_run.py`:依次跑 refresh-skill-inventory → nightly-dream-sweep(索引 14d)→ weekly-iteration-report(周报)→ weekly-workmode-analyze(偏好)→ panel --open(浏览器自动开)
- 通过 `scheduler_run --task <id> --run-now --trigger external` 跑各 task(COMMAND_SPECS 白名单 + scheduled_tasks 参数,不重复维护、不绕过安全边界)
- workmode 需 `SILICONFLOW_API_KEY`,无则该阶段降级(extract 仍产 packet、returncode 0),其余阶段正常;末尾提示配 key 补全
- `--no-panel` 不自动开 panel;`--skip <task-id>` 跳过某阶段(可重复)
- `references/00` 第 6 步指向 first_run(替代散步骤)

## [1.7.2] - 2026-08-11

### 升级:panel sidebar 布局 + 全 dashboard 统一 + 暖灰赤陶配色

按 content-registry `dashboard.html` 完整重做 panel 视觉/信息架构,从顶部 tab 列升级为 sidebar 布局,所有 view 统一 dashboard 设计系统。

- **sidebar 布局**:左侧 238px 深色 sidebar(品牌 + 6 nav + 副信息 + 底部)+ 右侧主区;nav 切换 `.view` 带 reveal 动画 + history hash 持久
- **全 dashboard 统一**:总览/Review/偏好审阅/Cron/Logs 全部用 `.d-*` 组件(metric 卡 / paper-panel / d-table / d-badge / d-btn);沉淀报告沿用 `.sed-*`;旧蓝白 `.card/.grid/.tab` 弃用
- **暖灰 + 赤陶配色**(和 info-evaluator 米色+moss 区分):sidebar 深棕灰 `#3d3530` + 主区暖灰 `#efece8` + 主色赤陶 `#a24f36` + 琥珀/暖灰辅
- 完全自包含(CSS/JS 内联,CSP `default-src 'none'`),装 skill 跑 `panel.py` 即得同款 dashboard

## [1.7.1] - 2026-08-10

### 升级:沉淀报告 tab 完整 dashboard 设计系统(参照 info-evaluator)

按 content-registry `dashboard.html` 的视觉/信息架构完整重做沉淀报告 tab,从简陋卡片升级为成熟设计:

- **设计系统**(.sed-* 局部 CSS,不污染其他 tab):米色(`--sed-paper`/`--sed-surface`)+ moss 绿(`--sed-moss`)+ serif(`Songti SC`/`STSong`)+ 14px 圆角 + 阴影
- **Hero 顶部**:渐变米色 + serif 大字 + 右侧 3 metric(总数 / 本周新增 / 类别)
- **Subnav 子导航**:kind 切换 pill(全部 N / iteration N / deep-analysis N / ...)
- **Toolbar**:搜索框(标题/摘要)+ 显示计数 + sort 切换(最新 / 最早)
- **lib-card 报告卡片**:左侧 kind 缩写(moss 绿 serif)+ 右侧标题/2 行摘要/时间·大小
- **paper-panel 详情面板**:点击卡片展开完整 **md 渲染**(H1/H2/H3 + 列表 + blockquote + 表格 + 段落 + 粗体 + 代码 + pre)
- **简易 md→html 渲染器** `renderMd(text)`:前端 escape + pipe table + list + blockquote + 段落合并

iteration 周报 5 章节(专注度表格 + 归因 sample 列表)现在直接可读,不再 `<pre>` 源码。

## [1.7.0] - 2026-08-10

### 新增:沉淀报告统一到 panel(统一审阅工作台第一步)

`review/inbox/` 下的脱敏 md 报告(迭代周报 / deep-analysis / 根散落)在 panel 第 4 个 tab「沉淀报告」卡片式展示,解决「手动翻 md」痛点。参照 info-evaluator 运营布局(README 单一入口 + SKILL 权限边界 + dashboard metric/列表)。

- **`references/17-sediment-reports.md`**:沉淀报告运营说明(来源/安全/单一收集入口/与 workmode 边界)
- `render_panel.collect_review_documents(kind, sort, limit)`:加 metrics(total/this_week/by_kind)+ kind 过滤 + mtime sort;metrics 全集统计不受 limit/kind 影响
- `panel` GET `/api/review-documents`:加 query parsing(`?kind=...&sort=...`)
- JS `renderDocuments`:顶部 metric bar + kind 过滤按钮(内存即时切换)+ 卡片列表 + `<details>` 展开全文
- `DEC-050`:沉淀报告统一到 panel(单一权威入口 + 单一权威源原则)

### 边界

- 沉淀报告是**阅读视图,不做决定**;决定类用 Review Inbox / 偏好审阅
- 校准维度(报告标记提取准/不准 → 反馈进账本)留 1.7.x 第二步

## [1.6.0] - 2026-08-10

### 新增:工作模式偏好账本 + 可视化审阅前台

Self Evolve 内部新建工作模式偏好子系统(维度 = focus/correction/sediment/recurrence),和 info-evaluator 的内容评分偏好(content_value/selection_capacity)分家,各自单一权威源。详见 DEC-049。

- **`scripts/workmode_extract.py`**:从 session-summaries + dream_sweep 聚类提炼工作模式证据包(复用 iteration_report 归因常量,不重构报告),按 (scope, sub_topic) 聚成跨 ≥2 session 的 cluster,产出 `runtime/preference-bridge/workmode-packet.json`(schema 复用 self-evolve-preference-evidence-v1)。
- **`scripts/workmode_ledger.py`**:四维状态机账本(机器/人工/应用/结果)+ 确定性 candidate_id/revision + 仅追加 events.jsonl + fcntl.flock + chmod 600。照搬 info-evaluator preference_ledger 的 scope 无关部分,隐私门控复用 self-evolve 自己的 privacy_gate(比 FORBIDDEN_TEXT 更全)。模型 = SiliconFlow DeepSeek-V3.2(enable_thinking=False,temperature 0.0),薄客户端内置不跨 skill import。
- **`scripts/workmode_pipeline.py`**:提炼 + 分析 + 入账,source_digest 幂等短路(未变则零模型调用)+ pipeline.lock 互斥。extract 成功即 returncode 0,分析降级(如未配 key)不算失败。
- **panel「偏好审阅」tab**:卡片式展示候选(scope/polarity/置信度 CSS 条/跨会话证据数)+ 接受/观察/拒绝。GET `/api/workmode-candidates` + POST `/api/workmode-candidates/{id}/decision`(revision 绑定,陈旧 → 409)。认证全继承现有 authorize_write(Host+IP+session+Origin+nonce)。
- **调度**:`workmode_analyze` 注册到 COMMAND_SPECS;scheduled_tasks 加 `weekly-workmode-analyze`(外部计划由用户设置)。
- **`scripts/setup_platform_schedule.py`**:检测本机 WorkBuddy / QwenWork / MyAgents / **OpenClaw**,为每个 enabled 任务生成各平台的配置命令。OpenClaw 用 `openclaw cron add --command` 直接挂(无需 agent prompt);尊重「skill 不创建调度」边界,只给建议。

### 修复

- **panel 运行记录排序 bug**:`collect_scheduler` 合并多个日志文件后直接取 `[-limit:]`,旧 `task-runs.jsonl`(止于 2026-07)排在按月文件之后,把最新的按月记录(2026-08)挤掉 → 运行记录永远停在旧日期。改为合并后按时间戳排序再取最新。

### 契约变更

- 推翻 SKILL.md「Self Evolve 不维护偏好账本」的旧措辞——精确限定为「工作模式偏好」(新维度,本职);内容评分偏好仍在 info-evaluator(DEC-047 不变)。
- 与 info-evaluator 账本 schema 同源(四维状态机 + 哈希公式同构),为将来统一投影/工作台整合留接口。

### 验证

- 12 个账本单测全过(revision 滚动回 pending / 陈旧 revision fail-closed / decide 不改 ledger 主体 / reason 隐私拒绝 / corrupt 事件/identity 阻断 / unknown_scope 过滤)。
- 真实来源提炼和 packet schema 检查作为旧工作台的本地验证。
- test_panel 15 测试不回归;render_html 含 preferences nav/div/renderPreferences/decidePreference。

## [1.5.1] - 2026-08-10

### 修复:迭代报告 v2 校准

- **归因正则移除 `\b`**：避免英文词边界在中文场景失效，改善纠正短语及约束信号提取。
- **反复 Skill 自动/主动阈值**：从 `blob >= related//2` 调整为 `blob/related >= 0.20`，减少主动调用被误判为自动调度。
- **专注度关键词校准**:AI 提效 CLI 移除「脚本/CLI 工具/分发」(过宽,开发 skill 也写脚本误归),改用动作词(自动化/批处理/pipeline/cron/定时/批量/调度/流水线);skill 元工作加「进入 skill/skill 内部/skill 迭代/写 skill」。
- **_session_field_blob 加 evidence_snippets**:让纠正短语正则能扫到用户原话(「其实/应该是」主要出现在 evidence)。

### 已知限制(下版)

- 专注度统计可能被自动 cron 会话污染，后续按自动/主动区分过滤。
- 归因 sample 的 cid 引用是 session_id 前 12 位,下版可加会话主题回链。

## [1.5.0] - 2026-08-10

### 重构:迭代报告从「堆事实」转向「归因洞察」

`scripts/iteration_report.py` 将报告压缩为五章节并增加三层分析（纯正则，不依赖 LLM，也不新增 session-summaries 字段）：

- **§1 专注度占比**：按工作方向正则分类，多标签加权，并展示覆盖率与倾向总结。旧关键词分类具有特定领域倾向，不能视为通用画像。
- **§2 反复纠错归因**:三类归因正则(skill 边界 / 约束缺失 / 纠正短语),只在 `decisions` + `upgrade_signals` 字段内匹配避免上下文稀释,sample 3-5 条带 cid;问法问题信号稀薄,有信号才显示,无信号留 nudge。
- **§3 反复调用 skill + 自动 vs 主动区分**:`related_skills` × blob 提及共现,识别「自动 cron 调度」(相关× 高 / blob 低)vs「主动调用」,提示用户反思 skill 边界是否过宽。

新增函数:`_extract_focus_distribution` / `_extract_attribution_signals` / `_extract_recurring_skills` / `_extract_top_decisions` / `_snippet` / `_parse_session_ts`(兼容 epoch/字符串/毫秒)。

### 验证

- 端到端检查桌面报告的结构和可读性。
- 归因 sample 含 cid 引用；桌面写入经 `sanitize_structured_text` fail-closed 脱敏。

### 已知限制(下版迭代)

- 专注度正则偏宽(「script/skill-manager」命中过多),AI 提效 CLI 占比偏高,book-ocr 类被误归;待校准关键词。
- 反复 skill 自动/主动阈值偏严,de-ai-polish 等被全标「自动」;待调阈值。
- 纠正短语类目(sample 抽到 0),正则可放宽。

## [1.4.0] - 2026-08-09

### 新增:迭代报告(面向用户的每周脱敏 digest)

- 新增 `scripts/iteration_report.py`:从 timeline-index / topic-clusters / proposals / skill-inventory 拼一份**用户口吻** digest(本周扫描概览 / 高频主题 / 可沉淀资产建议 / 覆盖 skill / 下一步),区别于审阅者面向的 pending 报告。
- **双输出**:① review inbox(`review/inbox/iteration/`)走 `write_review_artifact` 隐私门控;② 桌面副本(`~/Desktop/self-evolve-周报-*.md`)用 `sanitize_structured_text` fail-closed 脱敏 + `assert_external_write_path` + 原子写。桌面副本离开 review inbox 受控环境,残留 blocker 就不写。
- scheduler 注册 `iteration_report` type(`COMMAND_SPECS`)+ scheduled_tasks 加 `weekly-iteration-report`(外部计划由用户设置)。平台无关:WorkBuddy/QwenWork 等用户把外部 Cron 入口配进各自平台调度器,self-evolve 不创建调度。
- 文档:`references/12` 任务分层表 + 「WorkBuddy/QwenWork 平台定时任务」说明;`references/00` 下一步提迭代报告。

### 验证

- `scheduler_run --task weekly-iteration-report --run-now --trigger external` 支持生成迭代报告并向 review inbox 和桌面输出。
- 隐私门控:review inbox `published`(blockers 空);桌面经 `sanitize_structured_text` 脱敏。

## [1.3.1] - 2026-08-09

### 重构(配置结构整理)

- **example 配置移到 config/**:`templates/core_skills.yaml` 与 `templates/scheduled_tasks.yaml` 移到 `config/core_skills.example.yaml` 与 `config/scheduled_tasks.example.yaml`。`templates/` 回归只放产出模板(article.md / upgrade-direction.md)。职责清晰:config/ 管配置(example + 实例),templates/ 管产出格式。
- **data_root 拆单独 YAML**:data_root 从 `core_skills.yaml` 拆到独立 `config/data_root.yaml`(+ example),职责分离——core_skills 只管 skill 清单与来源,data_root 只管外部数据根。`_data_root_from_config()` 改读 `config/data_root.yaml`,优先级不变(env > data_root.yaml > 默认)。
- **删源码树 review/**:真实 review 产出在外部 DATA_ROOT/review/,源码树 review/ 只剩 legacy 声明 README,无实际用途,删除。
- 更新 `references/00-first-run-setup.md`(复制三个 example + data_root 单独说明)与 SKILL.md(data_root 路径)。

### 验证

- data_root 三优先级测试通过(env > data_root.yaml > 默认,默认地址不变)。
- core_skills.yaml 与 core_skills.example.yaml 均已无 data_root 字段。
- inventory 支持合并本地配置与 Agent 默认来源。

## [1.3.0] - 2026-08-09

### 分发就绪

Self Evolve 改造为可分发版本：Skill 路径可迁移，首次配置说明见 `references/00-first-run-setup.md`。

- **inventory 默认扫多 agent skill 目录**:`refresh_skill_inventory.py` 的 DEFAULT_SOURCES 从固定目录改为收集 21 个常见 agent 的用户级 skill 目录(claude/codex/workbuddy/codebuddy/agents/qoder*/qwen*/opencode/openclaw/hermes/cursor/windsurf/gemini/copilot/trae/kimi*/deepseek/grok/minimax*),只收录实际存在的目录。fallback 由 `config or DEFAULT` 改为 merge——没有个人配置时扫默认 agent 目录,有个人配置时不强行覆盖只补充。
- **DATA_ROOT 可配**:`self_evolve_paths.py` 的 default_data_root() 增加从 `config/core_skills.yaml` 读 data_root 字段,优先级 env `SELF_EVOLVE_DATA_ROOT` > YAML `data_root` > 平台默认(默认地址不变,向后兼容,不挪已有数据)。config 与 templates 同步加 data_root 字段,example 内可视化展示默认地址。
- **配置 example 模板**:新增 `templates/scheduled_tasks.yaml`(timezone 占位 + sources 可选说明),配合既有 `templates/core_skills.yaml`。
- **首次配置引导**:新增 `references/00-first-run-setup.md`,引导新用户复制 example → 运行 inventory 扫描 → 确认覆盖自己 skill → 排查漏扫。

### 会话来源扩展(验证)

- 新增 `scripts/probe_workbuddy_trace.py` 与 `audit_workbuddy_traces.py`:验证 WorkBuddy 的 OTel span trace 可还原成会话流(处理 100KB toolInput 截断走正则兜底、累积历史 user 消息重发按内容去重、system 模板孤立 `<user_query>` 开标签中和三陷阱),为接入 WorkBuddy 作为第三会话来源做铺垫。Qoder/QwenWork 的 session 为 CC jsonl 克隆,零成本可接入。

### 清理

- 迁移旧版 review 产出时需先核实外部数据根和归档。

### 验证

- inventory 合并按 realpath 去重，支持多 Agent 来源。
- DATA_ROOT 三优先级测试通过(env > YAML > 默认,默认地址不变)。
- WorkBuddy trace 解析审计覆盖内容抽取、去重和异常处理。

## [1.2.1] - 2026-08-09

### 修复

- 将偏好证据包从“序列化整包后脱敏”改为字符串叶子逐字段脱敏，避免私有路径替换破坏 JSON 语法并把全部合格聚类误判为隐私失败。
- 桥接 cluster ID 改为确定性短哈希，满足下游 ASCII 标识契约且不泄露内部主题或路径片段。

### 验证

- 新增字段级私有路径与桥接 ID 回归；偏好证据专项 6 项测试通过。
- 隐私 fail-closed 规则保持不变；桥接包经结构与隐私验包后才可进入外部分析。

## [1.2.0] - 2026-08-09

### 新增

- 新增 `export_preference_evidence.py`，把跨会话明确表达导出为 `self-evolve-preference-evidence-v1` 脱敏证据包，供 Info Evaluator 生成可审偏好候选。
- 新增稳定 `source_digest`、离线 `--verify-only` 和跨 session/evidence 可追溯门槛。

### 安全

- 桥接包禁止完整 transcript、原始 session ID、绝对路径、敏感信息和提示注入；单会话与隐私失败聚类关闭处理。
- 明确 Self Evolve 只生产证据，不调用内容评分模型、不修改评分配置，也不把活动频率推导为内容价值偏好。

### 验证

- 新增 5 项合成回归，覆盖跨会话导出、单会话过滤、隐私关闭、摘要确定性和篡改拒绝。真实会话外部分析仍需显式授权，当前标记 `NOT_VERIFIED`。
- 真实试跑暴露旧隐私门控可能阻止导出；外部分析与原话材料仍须明确授权。
- 一次性原话包仅保存在仓库外 runtime，默认脱敏/fail-closed 逻辑未改变；已登记“受治理的用户授权原文模式”后续任务。

## [1.1.3] - 2026-08-08

### 采集覆盖 + 提取质量

- **Codex `_quarantine` 盲区补采**：`discover_codex_paths` 增加隔离目录；`source_variant_for_path` 增加 `codex_quarantine`，去重优先级为 1。
- **evidence_snippets 跨时段抽样**：命中 signal 的 texts 改等间距抽样（头/中/尾均匀取），limit 4→8，降低长 session 后期 evidence 缺失。
- **ARTICLE_PHRASES 加写作意图词**：加"设计手记/长文/写一篇/记录成文/分享出来/发出来"（明确写作意图，非泛技术词，保区分度）。

### 验证

- 191 测试绿（+2 `test_evidence_snippets_samples_across_session` / `test_source_variant_for_codex_quarantine`）。
- `discover_codex_paths(None)` 验证：codex total 1047→**1390**（+343 `_quarantine`）。
- 证据摘录覆盖会话的不同阶段。

## [1.1.2] - 2026-08-08

### 提取质量修复

- **sensitive_markers 剥离 MCP/系统提示**：`detect_sensitive_markers` 改用 `useful_user_texts`（用户消息）而非 `combined`（含 MCP 工具描述/系统提示），避免工具描述污染敏感检测及标题。
- **extract_decisions 排除对话碎片**：排除句首口语短句与模糊提问，移除易误匹配的 cue；长度门槛 6→12。

### 验证

- 189 测试绿（+1 `test_extract_decisions_excludes_conversational_and_vague`）。
- 检查标题、敏感状态、decisions 过滤与 transcript 大小更新。

## [1.1.1] - 2026-08-08

### 修复

- **summarize_records 空 texts 全 source 宽容**：v0.9.0 只对 `claude_transcript` 宽容（空 texts 产 placeholder 而非 None），v1.1.1 扩展到所有 source——`claude_subagent` workflow journal（非标准 schema）/ `claude_project` metadata-only（只有 ai-title 行）/ 老 codex schema（record_type 平铺，message 没被 record_text_events 提取）都救活。placeholder `summary_policy=index_only` 不进聚类，但保留索引可检索 + raw-backup 原文。
- backfill 支持无文本记录的 placeholder 索引，避免非标准或 metadata-only 会话阻断。

### 不做

- 老 codex schema 适配（识别 record_type 平铺结构）——空 texts 宽容已保住它们的 metadata（cwd/timestamp/session_id），message 内容虽丢但价值低（2025-08~10 早期会话），投入产出不值。

## [1.1.0] - 2026-08-08

### subagent 采集 + raw-backup 全集补全

- **subagent 采集支持**：`source_variant_for_path` 加 `claude_subagent`（`subagents/` 路径），`dedupe_session_summaries` priorities 加 `claude_subagent:0`（去重让位主会话），`cluster_candidate` 排除 `claude_subagent`（不进聚类/dream，但仍索引+raw-backup——subagent 是主会话子任务，内容重叠主会话，进聚类只会 flood）。CLI `--include-subagents` 默认改 `True`（`BooleanOptionalAction`），让 subagent 备份自动化。
- **raw-backup 扩展到 merged 全集**（v0.9.1 gap 修复）：原 `update_runtime_indexes` 的 raw-backup 循环只对本次新写的 `summaries` 跑，导致**有 summary 但原文未 cp**的 skipped_existing session 漏备份（CC cleanup 时丢）。改为对 `merged`（existing + summaries）全跑 + no-clobber 幂等，下次跑一次性补全历史原文。
- 原始来源缺失时保留已有摘要；raw-backup 对已归档条目保持幂等。
- raw-sessions 按来源及 subagent 分目录保存。

### 验证

- 188 测试绿（+3 SubagentCollectionTests：source_variant_for_path 分类 / cluster_candidate 排除 subagent / dedupe 优先级让位主会话）。
- backfill 端到端检查累计索引、完成状态和 subagent 原文归档。
- 推论：CC 默认 cleanupPeriodDays 30→365 + ~/.claude git + DATA_ROOT raw-backup（v0.9.0-1.0.0）+ subagent 纳入（v1.1.0）——会话史现在四道半防线。

## [1.0.0] - 2026-08-08

### marker flaky 根治 + 清 legacy 源码树

- **marker 防御改造**：`legacy_state_files()` 排除活跃产出子树（runtime 下 dreaming/session-summaries/panel/logs/scheduler/learning-candidates + 顶层 evaluation-log/hook-runs/skill-inventory/extraction_sessions + review/output），新增 `is_legacy_active_artifact` 判定。这些 v0.7.0 后应全部写 external，即使因路径 bug 残留 legacy 也不算"冻结 state"、不参与 `migration_marker_valid` sha256 校验——根治 marker flaky（v0.9.0 实测 legacy source-index 被一次 backfill 写入致 marker 反复失效、assert_runtime_ready 阻断）。改造即时收益：legacy 还在时 `legacy_state_files()=[]` → `migration_required=False`，flaky 立即止血。
- 源码树中的旧 runtime 和 review 产物迁入外部状态目录；历史迁移前需核对副本。
- 清后 `LEGACY_RUNTIME_ROOT` 不存在、`LEGACY_REVIEW_ROOT` 只剩 archive/README.md placeholder → `legacy_state_files()=[]` → `migration_required()=False` → marker 不再被查询，flaky 双重根治（改造防御 + 清空根除）。
- 历史产物支持归档备份；归档不能替代核验与回填。

### 验证

- 185 测试全绿（+5 LegacyActiveArtifactTests：活跃子树分类 / runtime 子树排除 / 顶层文件排除 / review/output+placeholder 空 / only-active 不 present）。
- assert_runtime_ready PASS（清 legacy 前后均无 migration_required）；dream_sweep recent dry-run 写 external 后 marker 仍稳定。
- raw-backup 生产路径检查 recent dry-run 和按来源分目录。


## [0.9.1] - 2026-08-08

### 新增

- **raw-backup 双保险**：dream_sweep 写 session summary 时同步把会话原文 jsonl 复制到 `DATA_ROOT/runtime/raw-sessions/<source_variant>/<YYMM>/<原文件名>`。来源可能清理旧原文；摘要提供结构化留存，raw 副本提供原文字节留存。
- 四约束：**no-clobber**（同 size 跳过，幂等）+ **增量更新**（原文追加致 size 变则覆盖）+ **原子写**（tempfile + fsync 文件 + rename + fsync 目录）+ **三源全覆盖**（claude_project / claude_transcript / codex_active / codex_archived 分目录）。
- 原文已被 CC 清理时返回 `source_missing`，**保留已有 raw 备份不删除**（双保险价值正在于此）。
- `archive_raw_session` 挂 `update_runtime_indexes` 的 summary 写入循环，统计写入 `source_index.raw_backup`（archived / skipped / updated / source_missing / error）。

### 分工

- 原始来源如果另有版本管理，应独立核实其覆盖范围；不得假设所有会话均已纳入。
- `DATA_ROOT/raw-sessions` = 当前快照（第二道，原文最新字节）。存储翻倍可接受——数据最重要。

### 测试

- 180 全绿（+6 RawBackupTests：首次归档 / no-clobber 幂等 / 原文变更覆盖 / 源缺失不抛错 / 三源分目录 / update_runtime_indexes stats 端到端）。

## [0.9.0] - 2026-08-08

### 采集层（让 self-evolve 真正能搜到所有 session）

- **backfill 解锁**：`backfill_is_complete` 加 `_count_raw_source_files` 复核，新源文件出现后自动重开，不因 `completed=true` 永久锁死。
- **transcripts 豁免 recent cutoff**：`discover_claude_paths` 让 `~/.claude/transcripts/` 的旧 mtime 会话也能进入扫描。
- **cursor lower-bound**：`build_backfill_summaries` 用 `last_processed_mtime` 过滤候选，避免重复处理已去重的前段。
- **retry 熔断 + 闭环**：解析失败 transcript 标 `failed_paths` 持久化并跳过，`completed` 不要求 `errors==0`；成功后自动从 `failed_paths` 移除。
- **summarize_records 宽容 transcripts**：`claude_transcript` 空 texts 返回 placeholder 而非 None；其他 source 仍 return None。
- **覆盖率对账**：`compute_coverage_metrics` 写 `source_index.coverage`（raw_total / unindexed_total / coverage_ratio），面板/调度可直接读"还差多少"。

### 提取层（让搜到的信号变准）

- **框架注入剥离**：`strip_framework_injection` 剥 `<system-reminder>`/`<CRON_TASK>`/`<observed_from_primary_session>`/`<what_happened>`/`<occurred_at>`，并挂接 `extract_message_text` 和双 marker 名单。
- **decisions 真抽取**：从 3 条硬编码分类模板 → `extract_decisions` 句子级抽取（决定/改为/因此/选定/采用X而非/放弃 等 cue）。
- **article_signals 守卫**：改用 `useful_user_texts`，避免把 assistant 的发布表述误判为用户意图。
- **marker 名单兜底**：`CONTEXT_NOISE_MARKERS` + `REPORT_NOISE_MARKERS` 都补入框架注入 tag。

### 聚类层（让聚类不假同质）

- **簇间合并步**：`_merge_similar_clusters` 在 `build_clusters` 加簇循环后做质心相似度合并（阈值 0.55），跳过纯泛词簇防桥接雪球、size cap 防超分片——填补 reference 11 设计承诺但缺失的合并步。
- **同名收紧**：`choose_cluster_title` 泛词同名分支要求 ≥2 命中，避免单泛词让异质簇改同名。

### 测试

- 174 全绿（+13 新增：transcripts 豁免 / 注入剥离 / decisions / 合并 / 同名收紧 / 熔断 / coverage / transcripts 宽容 / backfill recheck / 等）。
- 修 `test_refresh_cli_only_writes_inventory_outputs` 补 mock `assert_runtime_ready`（不再依赖本机迁移态）。

### 文档

- `references/11-dream-sweep.md` 新增「CC 会话存储与生命周期」+「完整采集源全景」：CC 两套存储 + Codex 三套（含 `_quarantine` 盲区）+ `history.jsonl` 命令源 + 非会话目录清单 + git 无历史 + 覆盖率对账方法。


### 运行边界

backfill 支持重试熔断、单调游标和失败重试闭环；实际来源覆盖按各次运行记录核对。

## [0.8.3] - 2026-08-06

### 新增

- 交互沉淀「验证回看」：`interactive_sediment` 加 `pending_verifications` + `verify-list` 子命令，列出 applied 但未 verified 的提案。`references/15` 加步骤 0.5——触发交互沉淀时先查待验证提案，若本次涉及则提示用户回看效果，登记 verified/failed/inconclusive（复用 `proposal_store verify`）。把 applied→verified 半圈从「靠人手动记、易漏」变成「交互沉淀时主动浮现」，为后续反哺（沉淀数据指导 curate/路由）铺数据。+3 单测。

## [0.8.2] - 2026-08-06

### 修复

- 排除 macOS `.DS_Store` 等 OS 元数据出 migration state 指纹（`self_evolve_paths.legacy_state_files` + `migrate_state.build_plan`）。原委：Finder 自动改写 `.DS_Store` → `migration_marker_valid` 持续 flaky 失效 → `assert_runtime_ready` 反复阻断（POST-03「自愈后又失败」的真根因）。新增 `is_ignored_state_file` + 3 个单测；修复后 marker 自动恢复有效，无需重新 apply。

### 增强

- `interactive_sediment.map` 加 inventory 过期检测：`generated_at` 超 7 天 → 输出警告提示先 `refresh_skill_inventory`，防止过期 inventory 导致 commit 误判 ambiguous 等 silent 降级。+2 单测。
- 旧核心 Skill 配置支持按领域维护重点关注项；实际配置留在本地，不作为发行默认值。

### 交互沉淀的可用性

- Branch B 的顾问模式需关注术语可理解性、可选去向、价值判断辅助和主动触发提示。

## [0.8.1] - 2026-08-06

### 修复

- 修复 `interactive_sediment.commit` 在目标 skill 被 inventory 多 source 重复登记时**静默降级**为 candidate 的问题（in-chat auto-accept 失效）。`_resolve_inventory_target` 原先只要 matches>1 就判 ambiguous；现改为多条 matches 若指向**同一 SKILL.md 文件**（inventory 重复登记/过期），折叠为一条走 `resolved`，仅指向不同文件或信息缺失时才判 `ambiguous`。新增 2 个单测覆盖（同文件→resolved、不同文件→仍 ambiguous）。
- inventory 多来源重复时需先核对目标文件身份，避免唯一目标降级为歧义。

### 运维

- 交互沉淀前应刷新过期 inventory，并对同一 Skill 多来源登记去重。

## [0.8.0] - 2026-08-05

### 新增

- 新增第二运行模式「交互式对话沉淀」：用户在对话末尾主动触发（「复盘/沉淀这次对话」），agent 用 **live 对话上下文**复盘可复用的方法论/知识，按**自适应 2 分支**路由——命中已安装 skill（Branch A：`core_skills.yaml` 的 `domain_keywords`/`function` 精确匹配，inventory `description` 兜底）则指名道姓写升级提案；无命中（Branch B）则进顾问模式（原子化拆分 + 资产沉淀理念 + 去向选项），决定权交用户。沉淀目的地**动态推导**（用户真实 inventory + 可选 `config/asset_owners.yaml`），不预设固定分类，故初学者（少 skill）走 Branch B 被教方法论、高阶用户（基建全）走 Branch A 精准路由。与外部 Cron 磁盘索引流程互补，不替代。
- 新增 `scripts/interactive_sediment.py`：`map` 子命令打印动态资产地图（区分 inventory 缺失/损坏/正常三态）；`commit` 子命令对 agent 草稿跑隐私门控（**fail-closed**，不写盘）、原子 no-clobber 落盘到 review/inbox（内容哈希文件名、目录 fsync），并经 `proposal_store` 登记——目标在 inventory 唯一 resolved 时登记 machine `candidate` 后立即 `decide(accepted)`（in-chat 确认即人工接受），文章/无目标/歧义目标只登记 `candidate` 留待 localhost 面板。
- 新增 `config/asset_owners.yaml`（可选，默认空）：高阶用户声明「哪类非 skill 资产归哪个 owning skill」，让 Branch A 对非 skill finding 也能指名道姓；初学者留空即走 Branch B。
- 新增 `references/15-interactive-sediment.md`：交互模式的 agent 契约（触发消歧、地图自举、2 分支路由、Branch B 五步顾问方法论、落盘 rc 语义、非 skill 边界、涌现新资产类型、验证要点）。
- 新增 `tests/test_interactive_sediment.py`：16 个 unittest 用例，覆盖 loader 边界、map 三态、commit 隐私门控 fail-closed、no-clobber、`decide(accepted)` 真触发（查 proposal 事件流）、article/missing/ambiguous 仅 candidate。

### 边界（不变）

- 非 skill 资产（法律知识规则、问答等）只到「带载荷提案」为止，由 owning skill（如 legal-knowledge-engine）接手入库；self-evolve 不直接改成熟资产。
- 不改 `privacy_gate.py`/`proposal_store.py`/`refresh_skill_inventory.py` 现有契约，只复用；不替换 Cron 磁盘索引流程；不动外部 Cron 与全局设置。

## [0.6.1] - 2026-07-18

### 修复

- Skill 链路图修正迁移后的节点引用。
## [0.7.0] - 2026-07-18

### 重大变更

- 将正式运行架构收敛为“外部 Cron → `scripts/scheduler_run.py`”单一路径：外部 Cron 负责真实启停与时间表，任务注册表只提供命令白名单、`runner.enabled` kill switch、`external_only`、重入锁、超时、每日限额和按月运行日志。
- 移除旧会话结束执行链与创建能力；新增 `scripts/legacy_hook.py`，只提供状态检查和显式清理。清理默认预览，只有 `--apply` 才备份并修改全局设置，且保留其他项目配置。
- 新增统一外部数据根 `SELF_EVOLVE_DATA_ROOT`，把 runtime、Review Inbox、quarantine、proposal、panel 和 audit 从源码树分离。旧 `SELF_EVOLVE_STATE_ROOT` / `SKILL_EVOLVE_STATE_ROOT` 继续解释为 runtime 叶目录。

### 新增

- 新增 `scripts/migrate_state.py`：默认 dry-run，显式 `--apply` 以源哈希快照和目标 `O_EXCL` 只复制并校验旧状态，不删除或覆盖源文件；存在冲突时失败关闭。`--legacy-root` 可从升级前 worktree/版本快照恢复已离开当前源码树的材料；旧 Review 输出只进入 `archive/legacy-output`，未经重新隐私门控不会进入 Inbox 或 proposal 生命周期。
- 新增 `scripts/privacy_gate.py`：在 Review Inbox 前脱敏主目录、系统临时目录、挂载卷路径、联系方式、身份/案件信息等，拦截提示注入、Bearer/JWT 与其他密钥材料；隔离记录只保存规则、计数与哈希。
- 新增 `scripts/proposal_store.py`：分离 machine disposition 与 human decision，以稳定 fingerprint/revision、append-only 人工事件、applied commit 和 verified outcome 建立提案生命周期。
- 新增 `scripts/deep_dream.py`：把每日确定性索引与每周可选 LLM 深度分析分层；深度调用需要显式授权并只消费受控 cluster packet。
- 新增状态根 ownership marker：只认领专用空叶目录或可验证的既有 v0.7 布局，拒绝 `/`、主目录、系统临时根和非空未认领目录，避免误改共享目录权限；首次并发启动以完整临时文件 + 原子 no-clobber 发布 marker，避免一个 Cron 读到另一个 Cron 的半写入状态。
- 新增标准库 `unittest` 测试与 synthetic fixture，覆盖调度配置/锁/崩溃配额、旧配置清理、状态迁移、隐私门控、proposal 生命周期、Claude/Codex 采集、长会话抽样、聚类、inventory/portrait、Deep last-good 和 localhost 面板关键契约。

### 改进

- Dream Sweep 同时发现 Claude Code 与 Codex 的 active/archived 会话，按 session identity 与指纹去重；长 JSONL 改用流式头/中/尾抽样，保留最终决策与验证信息。
- 主题聚类增加来源配额、内部一致性约束和稳定谱系：`cluster_id`/`topic_key` 不再包含完整成员摘要，成员变化独立写入 `member_digest`/`revision`，旧 ID 保留在 `legacy_cluster_ids`；每日 `--generate` 只发布确定性 timeline/cluster packet。
- inventory 按 canonical realpath 去重；`skill-inventory.json`、`skill-portraits.json` 与 `skill-chain-graph.json` 分文件持久化。画像任务先筛选缺失/过期项，再按最久未尝试优先排序并应用 `--limit`，避免 inventory 前缀已经新鲜或持续失败时后续目标长期饥饿。增强画像按字段绑定内容哈希并合并，旧增强数据不会混入新 core，增强失败不污染有效 core 新鲜度；直接 CLI 增加单次 `$5`、整批 `$100` 硬上限。
- Deep 状态拆分 `last_attempt` 与 `last_success`；预览、CLI 暂时失败或隐私失败不再覆盖最后成功产物及 proposal 引用。
- proposal schema 升至 `1.4`：当前 revision 只绑定唯一 Inbox 逻辑路径；Deep proposal 产物按内容寻址并以 no-clobber 方式发布。人工接受/部分接受时通过文件描述符拒绝符号链接并核验 SHA-256，再把已读字节固化为 revision-bound archive 快照；事件持久化原路径、快照路径与哈希，applied 只验证决定快照。缺失、篡改、多路径、路径逃逸、并发替换和历史路径丢失均失败关闭；事件流撕裂、未知事件或冲突终态继续失败关闭。
- localhost 面板聚焦状态观察和人工 proposal decision，并彻底移除任务执行按钮、API 和子进程代码；面板不修改外部 Cron。启动时的一次性访问令牌只存在于进程内存和 URL fragment，fragment 不进入 HTTP/日志，成功交换后立即从地址栏清除并作废。会话只保存在包含端口的 `sessionStorage`，状态 API 通过显式 Authorization 鉴权，不设置会跨回环端口发送的 Cookie；匿名根页只返回无数据 bootstrap，匿名 API 返回 401。服务继续校验精确 Host/Origin、请求 nonce 与 JSON Content-Type，使用 CSP nonce、移除 inline handler，并在 proposal store 损坏时失败关闭。
- 迁移复制、manifest、layout 与 completion marker 增加目录级 fsync 发布顺序；隐私门控补齐 `/root` 和运行时非标准 HOME；修正主页、资源可达性、portrait `content_hash` 示例与核心配置模板字段。
- 重写 `SKILL.md` 与现役 references/templates，统一外部数据根、隐私门控、提案闭环、Cron-only 调度和验证说明；删除不再参与现役链路的分析 prompt 与旧评估模板。

### 迁移

- 源码树不再保存个人运行产物；本版本移除旧版已跟踪的 `review/output/**`、`review/review-log.md` 和运行型脚本。切换/合并前应先迁移；切换后必须将升级前 Git ref 建为临时 worktree，并通过 `migrate_state.py --legacy-root <old-worktree>/self-evolve` 预览、复制和校验。当前源码树为空不能证明旧数据不存在。
- 迁移需核对旧状态副本及 manifest/marker；legacy hook 和外部 Cron 的实际部署操作应单独确认。

### 文档完善

- frontmatter 版本同步为 `0.7.0`，通用工具许可证调整为 MIT，并补齐标准 MIT 全文与统一版权信息。
- `config/core_skills.yaml` 明确 core skills 只控制重点关注和优先级，inventory 才是候选全集；去除重复 source 别名以及会与真实 Skill 漂移的 `version`/`upgrade_target` 副本。
- DEC-037 记录单一架构、安全边界、迁移原则和机器/人工状态分离；TASKS 已按 `RESULT.md` 勾选代码闭环，并把真实部署操作保留为 `SE-DEPLOY-*`。

### 验证入口

以下统一验证已通过：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/scheduler_run.py --validate-config --json
python3 scripts/legacy_hook.py status --json
python3 scripts/migrate_state.py --dry-run --json
```

- 标准库测试 134/134 通过；Schema v2 校验通过 7 个任务；相对链接、语法与 diff whitespace 检查通过。
- fresh 数据根下外部触发成功，缺少 `--trigger external` 非零拒绝；把数据根指向 `/tmp` 时非零拒绝且目录权限保持不变。
- localhost 面板完成真实浏览器交互：匿名 API 401、bootstrap 200 且无私有数据、一次性 fragment 交换后被清除、会话进入端口级 `sessionStorage`、Cookie 数量为 0、访问令牌重放 403；访问另一个回环端口时未携带 Authorization/Cookie。proposal 接受并重载持久化、错误 nonce 403、任务执行端点 404、Host/Origin/CSP 检查通过、无 inline handler、初始/最终控制台错误均为 0、IPv4/IPv6 loopback 可用。
- synthetic Claude/Codex fixture 覆盖 active/archive 发现、长会话尾部、跨来源去重、稳定聚类、画像新鲜度、隐私隔离和人工决定不可被机器覆盖。完整证据见 `RESULT.md`。

## [0.6.0] - 2026-07-03

### 新增:Skill 功能画像层 + 链路图(供 agent-eval-lab Step 0 组合 / 协同迭代消费)

- 新增 `scripts/distill_skill_portrait.py`:对全仓 skill 用 LLM 蒸馏核心层画像(`capability`/`inputs`/`outputs`/`depends_on`/`can_chain_to`/`not_for`),增量按 `SKILL.md` mtime,失败降级不破坏索引层;`fulfill` 子命令消费 `enhance-requests.jsonl` 蒸馏增强层。纯标准库 + `claude -p` headless。已验证:build_chain_graph 交叉对账、extract_json 容忍杂质、增量判定、--no-llm 降级全通过。
- 新增 `references/14-skill-portrait.md`:画像层机制(核心层 5 字段全仓 + 增强层 4 字段按需 + 顶层 `skill_chain_graph` DAG + 控制反转请求协议 + `portrait_schema_version` 字段版本演进)。
- `runtime/skill-inventory.json` 每个 entry 新增 `portrait` 字段,顶层新增 `portrait_schema_version` + `skill_chain_graph`;`refresh_skill_inventory.py` **不变**(扫描与蒸馏解耦)。
- `config/scheduled_tasks.yaml`:加 `nightly-skill-portrait-distill`(默认 disabled,外部 cron 直调脚本)。
- `references/10-skill-inventory.md` 补第七节"与功能画像层的关系";`SKILL.md` 读取顺序加 14、运行资源段补 portrait 说明。
- frontmatter version 0.4.5 → 0.6.0(顺带修正落后于 CHANGELOG 的版本号)。
- Skill 画像数据通过 `skill-inventory.json` 与 `enhance-requests.jsonl` 暴露给上游消费方，保持生产与消费分工。

## [0.5.0] - 2026-06-20

### 重大变更

- **SessionEnd hook 完全下线,沉淀与索引改由外部 Cron 定时任务驱动**。
- 背景:历史上 `~/.claude/settings.json` 注册了 self-evolve 的 SessionEnd hook(`sediment_guard.py`),会在每次会话结束时实时评分;评分通过(score>=阈值,action=generate_upgrade/article 等)就后台 Popen 一个 `claude -p --dangerously-skip-permissions` headless agent session 做沉淀分析。
- 问题:
  - 与 v0.4 设计意图冲突(11-dream-sweep.md / DEC-023/024 明确写"SessionEnd 只建轻量索引,跨 session 总结交给夜间脚本")
  - 每次会话触发 headless,无法控制资源消耗,无法选择大模型(hook 继承父会话 model)
  - 与旧版外部 Cron 任务的职责存在重叠。
- 处理:
  - 从旧设置中移除 self-evolve 的 SessionEnd hook，原有配置先备份。
  - 移除 self-evolve hook 时保留其他 hook，不改变其配置。
  - `SKILL.md` 加 v0.4.9+ 废弃说明,标注"不要再运行 install_session_end_hook.py"
- 不删 `sediment_guard.py` 与 `install_session_end_hook.py` 脚本本身(保留代码,以后想恢复随时装回);但默认不再触发。
- 旧运行选择定时索引与跨会话分析；当前公开流程按需由当前 Agent 分析，不依赖旧定时器。

## [0.4.9] - 2026-06-16

### 改进

- `scheduler_run.py` 给 `task-runs.jsonl` 的 `reason` 字段做结构化增强(方案 A):
  - `dream_sweep` 类型:解析脚本输出,提取 `sessions / clusters / mode / index_mode / backfill_processed / backfill_completed / timeline / dreams / upgrade_directions / articles / context_updates` 等指标;同时支持 plain-text fallback 解析 `- sessions: N / - clusters: M` 标记
  - `maintain_runtime` 类型:解析 JSON 输出,提取 `runtime 体积 / summaries 总数 + flat_files / recommendations 数量`;同时给 `maintain_runtime.py --report` 加上 `--json` 参数
- 修复:dream_sweep 在 dry-run 模式输出多行 JSON(顶层 `{` 和末尾 `}` 不在同一行),旧实现只读最后一行解析失败,改为读完整文本
- 通知渠道及事件由实际部署环境配置。




## [0.4.8] - 2026-06-16

### 运维

- MyAgents reload 可能改变 Cron 对象映射及名称；更新前核对调度系统中的对象。
- 后续操作教训:**不要在已注册 cron 之后随便 `myagents reload`**,会重置 sidecar 内存中的任务映射关系;若必须 reload,先记录当前 cron ID 清单,reload 后用持久化文件里的新 ID 重新 update name/prompt。
- Task Center 任务可分别维护名称、描述和标签。
- 流程:每条 task 走 `update-status stopped → update name/desc/tags → rerun`(`stopped` 不能直接转 `running`,需 `rerun` 走 todo→running)
- **架构发现**:MyAgents 有两个独立层,cron 任务(`~/.myagents/cron_tasks.json`)和 Task Center 任务(`/api/task/list`)是不同对象,各有独立的 name/description/tags 字段。`myagents cron update --name` 只改 cron 层的 name,**不会同步到 Task Center**;反之亦然。改 Task Center 用 `myagents task update <taskId> --name --description --tags`,但要求 status=stopped 才能改。

## [0.4.7] - 2026-06-16

### 新增

- 外部 Cron 可按需编排历史回填、运行时检查、面板刷新和深度梦境生成；实际是否安装、启用及时间由用户决定。





- YAML `config/scheduled_tasks.yaml` 新增 `weekly-deep-dream` 任务条目，默认关闭；当前版本的 kill switch 不可绕过。

### 改进

- `scripts/scheduler_run.py` 新增 backfill-state 完成检查 hook:`run_task()` 入口处对 `history-backfill-index` 任务读 `runtime/dreaming/backfill-state.json`,若 `completed=true` 直接返回 `skipped (backfill_already_completed:...)`,避免无效每日跑。这与 12 doc §九「完成即停」建议对齐。
- `RUNTIME_DREAMING = STATE_ROOT / "dreaming"` 常量新增,作为 backfill-state.json 路径的稳定来源。

### 验证

- 检查外部调度任务运行记录及对应产物。
- backfill hook 测试:模拟 `backfill-state.json.completed=true` → 任务 `skipped (backfill_already_completed:...)`;`completed=false` 或文件不存在 → 正常跑。
- `python3 -m py_compile scripts/scheduler_run.py` 通过。
- 旧版本曾支持手动触发深度梦境；当前 `runner.enabled` 为不可绕过的 kill switch。

## [0.4.6] - 2026-06-15

### 文档完善

- `TASKS.md` 与 12 doc 同步抽象：T-083 / T-077 / T-208 措辞从"launchd 首选/后置"加 v0.4.4+ 抽象注（launchd / MyAgents cron / OpenClaw cron / Hermes cron / Linux/Unix 系统 cron / Codex automation 6 个同级载体），方便后续读者一眼看到抽象不被历史措辞误导。
- 更新外部 Cron 调度抽象说明。
- 新增"v0.4.6 外部 Cron 定时任务抽象与 TASKS 措辞同步任务"已完成段（T-111/T-112）。
- 历史决策记录（DEC-024 标题、T-073 第 2 条、T-074 第 2 条）保持原样不覆写。

## [0.4.5] - 2026-06-14

### 新增

- `dream_sweep.py` 新增 `--index-mode recent|backfill`，默认保持 recent 行为，backfill 用于历史存量 session 回填索引。
- 新增 `runtime/dreaming/backfill-state.json`，记录历史回填批次、跳过数量、最后处理位置、完成状态和累计统计。
- `config/scheduled_tasks.yaml` 新增默认关闭的 `history-backfill-index` 任务，可由外部定时器或本 Skill 调度器按批触发。

### 改进

- Backfill 默认按 `newest-first` 从近期向更早 session 追溯，每批默认最多处理 200 条未索引或已变化 transcript。
- 已有 summary 且 transcript 指纹匹配时跳过；旧 summary 缺少指纹时默认按 legacy 已索引跳过，避免重跑全部历史。
- `scheduler_run.py` 继续只允许白名单任务，新增安全透传 `dream_sweep` 的 backfill 参数，不开放任意 shell 命令。

### 文档完善

- `SKILL.md` 升级到 v0.4.5，补充 recent / backfill / generate 三类运行方式和人工审边界。
- 同步 `config/core_skills.yaml`、`templates/core_skills.yaml` 与 `references/02-core-skills-yaml.md` 的版本、关键词和 notes。
- `references/11-dream-sweep.md` 增加历史回填架构、跳过规则和续跑状态说明。
- 补充外部定时任务交接建议：每日 recent scan、每日阶段性 history backfill、每周 deep dream；明确 daily 任务不启动 Agent Session，weekly deep dream 当前尚未正式登记。

### 验证

- `python3 -m py_compile scripts/dream_sweep.py scripts/scheduler_run.py` 通过。
- `config/scheduled_tasks.yaml` 可被 YAML 解析。
- `dream_sweep.py --index-mode backfill` 支持批量回填并更新 `backfill-state.json`。
- `python3 scripts/dream_sweep.py --since 1d --dry-run --max-sessions 2 --json` 成功运行，确认 recent 模式未被 backfill 改动破坏。
- 调度器支持 backfill 参数并记录处理状态。
- 面板和运行时维护命令支持展示 summary 分桶。

## [0.4.4] - 2026-06-14

### 新增

- 新增 `scripts/maintain_runtime.py`，用于检查和整理 `runtime/` 运行数据。
- 新增手动调度任务 `maintain-runtime`，通过调度器白名单执行只读 runtime report。

### 改进

- `dream_sweep.py` 新生成的 session summary 改为写入 `runtime/session-summaries/<YYMM>/`，避免所有 JSON 长期平铺在同一目录。
- `maintain_runtime.py --organize-session-summaries` 默认只预览整理动作；只有传入 `--apply` 时才移动旧 summary。
- Runtime 治理继续使用轻量文件系统方案，不引入 SQLite，不删除、不压缩、不改写原始 transcript。

### 文档完善

- `SKILL.md` 升级到 v0.4.4，补充 runtime 治理命令和月份分桶规则。
- `DECISIONS.md` 新增 DEC-033，记录不引入数据库、采用轻量分桶与维护脚本的决策。
- `TASKS.md` 新增 T-103 至 T-106，记录 runtime 治理任务。
- 同步核心清单、模板、schema 和 Dream Sweep 设计文档中的 session summary 路径。

### 验证

- `python3 -m py_compile scripts/maintain_runtime.py scripts/dream_sweep.py scripts/scheduler_run.py scripts/render_panel.py scripts/panel.py scripts/refresh_skill_inventory.py scripts/sediment_guard.py` 通过。
- `python3 scripts/maintain_runtime.py --report --json` 成功输出 runtime 体积、JSONL 行数和 summary 分桶状态。
- `--organize-session-summaries` 可预览迁移及冲突。
- `--organize-session-summaries --apply` 可将旧 summary 迁入月份目录。
- `python3 scripts/scheduler_run.py --task maintain-runtime --run-now --json` 成功执行只读 runtime report。
- `python3 scripts/dream_sweep.py --since 1d --dry-run --max-sessions 5 --json` 成功运行，确认新 summary 写入月份分桶路径。
- `python3 scripts/render_panel.py --quiet` 成功刷新面板。

## [0.4.3] - 2026-06-14

### 运维

- 可在外部定时器中注册 `nightly-dream-sweep`；调度时间和启用状态由用户配置。
- 当前版本中 `runner.enabled` 是不可绕过的 kill switch，不应依赖旧版 `--allow-disabled`。
- dry-run 索引与人工审阅区保持分离。

## [0.4.2] - 2026-06-13

### 改进

- Dream Report 新增“产物方向判定”表，明确每个 cluster 应优先落到升级方向、文章草稿、上下文洞察、质量门控、工具链摩擦聚合，还是继续观察。
- 升级方向建议新增“产物方向判定”表，方便人工审阅时判断该建议属于哪类 Self Evolve 成果。
- 修正 Dream Report 的旧文案，不再暗示需要另行生成升级建议或文章草稿；现在同批 `--generate` 会直接派生待审产物。

### 文档完善

- `SKILL.md` 升级到 v0.4.2，补充 Self Evolve 常规最终产物地图。
- `references/11-dream-sweep.md` 增加六类产物方向：Skill / 流程升级、文章草稿、工作方式/上下文洞察、评估与质量门控、工具链摩擦聚合、继续观察/薄索引。
- 同步 `config/core_skills.yaml`、`templates/core_skills.yaml` 和 `references/02-core-skills-yaml.md` 的版本、关键词和 notes。

### 验证

- `python3 -m py_compile scripts/dream_sweep.py scripts/render_panel.py scripts/scheduler_run.py scripts/panel.py scripts/refresh_skill_inventory.py scripts/sediment_guard.py` 通过。
- `dream_sweep.py --generate` 支持生成 Timeline、Dream、升级建议、文章草稿与上下文洞察。
- 新生成的 Dream Report 与 Upgrade Direction 均包含“产物方向判定”。
- 对生成的待审文件执行敏感模式扫描，避免原始路径、联系方式和案件标识泄露。
- `python3 scripts/render_panel.py --quiet` 成功刷新 `runtime/panel/self-evolve-panel.html`。

## [0.4.1] - 2026-06-13

### 新增

- Dream Sweep `--generate` 新增派生产物生成：`review/output/upgrade-direction/`、`review/output/articles/`、`review/output/context-updates/`。
- 新增工作方式洞察草稿，用于记录用户长期偏好、跨 Agent 协作方式、项目/用户上下文更新建议。
- 新增派生产物选择规则：稳定流程和 Skill 边界生成升级建议，公开叙事素材生成文章草稿，长期协作偏好生成上下文建议。

### 改进

- 明确 Dream Report 只是证据索引和聚类审计，不再作为 Dream Sweep 的最终产物。
- `dream_sweep.py` 命令行输出会列出派生的 upgrade/article/context 文件路径。
- `SKILL.md` 与 Dream Sweep 设计文档同步说明三类待审产物的用途和人工审边界。

### 验证

- `python3 -m py_compile scripts/dream_sweep.py` 通过。
- `python3 scripts/dream_sweep.py --since 2d --generate --max-sessions 40 --min-cluster-size 2 --json` 已验证可生成 Timeline、Dream、升级建议、文章草稿和上下文建议。

## [0.4.0] - 2026-06-13

### 新增

- 新增 `scripts/dream_sweep.py`，实现 Timeline Dream Sweep 的确定性版本。
- 支持扫描 Claude Code `~/.claude/projects/**/*.jsonl` 与 Codex `~/.codex/archived_sessions/*.jsonl`。
- 新增运行索引输出：`runtime/session-summaries/`、`runtime/dreaming/source-index.json`、`session-index.json`、`timeline-index.json`、`topic-clusters.json` 和 `runtime/dreaming/runs/`。
- 支持 `--dry-run` 只生成运行索引，支持 `--generate` 额外写入 `review/output/timeline/` 与 `review/output/dreams/`。

### 改进

- Dream Sweep 增加 session 分类、噪音门控、上下文噪音过滤、案件主体/链接/路径脱敏和主题聚类。
- `nightly-dream-sweep` 可通过 `scheduler_run.py --allow-disabled` 手动触发 dry-run，但默认仍保持 disabled，不安装系统定时器。
- 面板 Dream Timeline 视图支持读取 `review/output/dreams/` 与 `review/output/timeline/`。
- 调度器的 `max_runs_per_day` 不再把 `skipped` 记录计入每日执行次数。
- `dream_sweep.py --max-sessions` 改为对 Claude Code 与 Codex 合并后的全局 session 列表生效，并在 source index 中记录 `limited` 数量。
- 面板中的 Hook 设置文件路径压缩为 `~/.claude/settings.json`，减少本机用户路径外露。
- Dream 报告证据片段过滤目录列表、工具错误、代码摘录和大文件提示，避免把工具噪音误写成任务演进。

### 文档完善

- `SKILL.md` 升级到 v0.4.0，补充 Dream Sweep 命令、运行目录和外部调度边界。
- `TASKS.md` 标记 T-091/T-092 完成，并保留 `launchd` 安装器为后续任务。
- `DECISIONS.md` 新增 DEC-030，记录 Dream Sweep 首版实现范围和安全取舍。

### 验证

- `python3 -m py_compile scripts/dream_sweep.py scripts/render_panel.py scripts/scheduler_run.py scripts/panel.py scripts/refresh_skill_inventory.py scripts/sediment_guard.py` 通过。
- `python3 scripts/dream_sweep.py --since 2d --dry-run --max-sessions 40 --json` 成功生成运行索引。
- `python3 scripts/dream_sweep.py --since 2d --generate --max-sessions 40 --min-cluster-size 2 --json` 支持生成 Timeline 与 Dream 报告。
- `python3 scripts/scheduler_run.py --task nightly-dream-sweep --run-now --allow-disabled --json` 可调用 Dream Sweep dry-run。
- `python3 scripts/render_panel.py` 后，面板 HTML 可显示 Dream 报告入口，且不包含 `transcript_path` 或 Claude transcript 原始路径。

## [0.3.22] - 2026-06-13

### 新增

- 新增 `config/scheduled_tasks.yaml`，登记 `render-panel-snapshot`、`refresh-skill-inventory` 和 disabled 占位任务 `nightly-dream-sweep`。
- 新增 `scripts/scheduler_run.py`，支持对已登记任务执行 `run now`，并写入 `runtime/scheduler/task-runs.jsonl`、`task-state.json` 和任务日志。
- 新增 `scripts/panel.py`，提供本地 localhost 面板和有限 API：状态、待审产物、任务列表、运行记录、日志、任务启停和 `run now`。

### 改进

- 调度器只支持内置命令类型 `render_panel`、`refresh_inventory`、`dream_sweep`，不从 YAML 执行任意 shell 命令。
- 本地面板只允许绑定 `127.0.0.1`、`localhost` 或 `::1`；写接口必须携带 `X-Self-Evolve-Nonce`。
- 启用/停用任务前会自动备份 `config/scheduled_tasks.yaml`，备份文件通过 `.gitignore` 排除。
- `render_panel.py` 暴露可复用数据聚合与 HTML 渲染函数，供静态快照和 localhost 面板共用。

### 文档完善

- `TASKS.md` 将阶段 B localhost 面板与调度配置任务标记完成，并新增 Dream Sweep 与 launchd 后续任务。
- `DECISIONS.md` 新增 DEC-029，记录调度器和 localhost 面板的实现边界。
- 更新调度设计与面板设计文档，明确 v0.3.22 已完成阶段 A/B，后续重点转向 `dream_sweep.py` 与 `launchd` 安装器。

### 验证

- `python3 -m py_compile scripts/render_panel.py scripts/scheduler_run.py scripts/panel.py scripts/refresh_skill_inventory.py scripts/sediment_guard.py` 通过。
- `config/core_skills.yaml`、`templates/core_skills.yaml`、`config/scheduled_tasks.yaml` 可被 YAML 解析。
- `render-panel-snapshot` 与 `refresh-skill-inventory` 可通过 `scheduler_run.py --run-now` 成功执行。
- `nightly-dream-sweep` 在 disabled 状态下通过 `run now` 返回 `skipped`，不会误执行未实现的 Dream Sweep。
- 使用本地面板验证页面可渲染，`render-panel-snapshot` 的 `run now` 可通过 nonce 保护接口触发。

## [0.3.21] - 2026-06-13

### 新增

- 新增 `scripts/render_panel.py`，实现阶段 A 只读 HTML 快照面板。
- 新增 `review/output/context-updates/.gitkeep`，补齐上下文更新建议的待审入口。
- 生成面板默认输出到 `runtime/panel/self-evolve-panel.html`，包含 Overview、Review Inbox、Scheduler、Dream Timeline、Logs 五个视图。

### 改进

- 面板聚合 `runtime/hook-runs.jsonl`、`runtime/evaluation-log.jsonl`、`runtime/learning-candidates/`、`review/output/`、`config/scheduled_tasks.yaml` 和 `runtime/skill-inventory.json`。
- 面板日志数据采用摘要模型，不在 HTML 中嵌入 `transcript_path`、完整 transcript 路径或原始 cwd。
- Scheduler 视图在尚未配置 `scheduled_tasks.yaml` 时显示空状态，不创建假数据。
- `refresh_skill_inventory.py` 与面板脚本支持可迁移的 Skill 路径。

### 验证

- `python3 -m py_compile scripts/render_panel.py` 通过。
- `python3 scripts/render_panel.py` 可生成 HTML。
- 使用本机 Chrome + Playwright 打开静态 HTML，确认五个视图可渲染、Review 搜索过滤可工作、Scheduler 空状态可显示。
- 检查 HTML 中不包含外部 `http://` / `https://` 资源，也不包含 transcript 路径字段。

## [0.3.20] - 2026-06-13

### 文档完善

- 新增 `references/13-panel-design.md`，将轻量 HTML 面板规划拆为“只读 HTML 快照”和“本地 localhost 面板”两个阶段。
- 明确面板的 5 个视图：Overview、Review Inbox、Scheduler、Dream Timeline、Logs。
- 明确面板数据源只读取 Self Evolve 自包含目录，不读取完整 transcript，不依赖外网资源。
- 明确阶段 B 的本地接口和安全边界：只绑定 `127.0.0.1`，写操作需要 nonce，只允许触发已登记任务，不允许任意命令输入。
- 同步 `SKILL.md` 触发描述、核心清单、核心清单模板和 schema，使后续分析可识别轻量面板、Review Inbox 和面板设计文档。

## [0.3.19] - 2026-06-13

### 改进

- 将 Skill 目录与 frontmatter `name` 从 `skill-evolve` 迁移为 `self-evolve`，显示名统一为 `Self Evolve`。
- 更新 Claude Code `SessionEnd` hook 安装器：可识别旧 `skill-evolve/scripts/sediment_guard.py` hook，并原地更新为 `self-evolve/scripts/sediment_guard.py`。
- 新增 `SELF_EVOLVE_*` 环境变量命名，同时兼容旧 `SKILL_EVOLVE_*`，降低迁移风险。
- Headless 反递归同时设置并识别 `SELF_EVOLVE_HEADLESS` 与旧 `SKILL_EVOLVE_HEADLESS`。

### 文档完善

- 更新 `SKILL.md`、Hook 配置、核心清单 schema、模板与调度设计备忘中的当前名称和路径。
- 同步 `review/review-log.md` 的标题与说明为 `Self Evolve`。
- `DECISIONS.md` 新增 DEC-026，记录从 `skill-evolve` 正式迁移到 `self-evolve`。
- `TASKS.md` 新增 v0.3.19 改名任务记录。

## [0.3.18] - 2026-06-13

### 改进

- 将长期产品边界从单纯 `Skill Evolve` 扩展为 `self-evolve` 方向：除 Skill 升级建议外，纳入 Timeline Dream Sweep、定时自检、项目/用户上下文更新建议、高频工作流沉淀和文章草稿。
- 基于 MyAgents 定时任务实现，明确本 Skill 后续只借鉴任务登记、运行锁、运行 JSONL、run-now、结束条件和面板思路，不复制完整 Tauri/Rust/Sidecar 架构。
- 明确当前不立即改名、不迁移目录、不重装 hook；未来若迁移到 `self-evolve`，必须提供兼容安装和路径迁移方案。

### 文档完善

- 新增 `references/12-self-evolve-scheduler.md`，记录 MyAgents 调度系统研究、`self-evolve` 命名建议、轻量 `launchd` 调度方案、面板边界和上下文更新的人在回路规则。
- `DECISIONS.md` 新增 DEC-025，记录“扩展为 self-evolve，但暂不改名”的决策。
- `TASKS.md` 新增 v0.3.18 任务记录。
- 同步 `config/core_skills.yaml`、`templates/core_skills.yaml` 和 `references/02-core-skills-yaml.md` 中的版本、关键词与 reference。

## [0.3.17] - 2026-06-13

### 改进

- 为 Timeline Dream Sweep 增加 session 分类与去噪策略：维护、普通 git 提交、软件更新等 session 默认只保留薄索引，不进入 Dream 报告、升级建议或文章草稿。
- 增加三层记录模型：Raw session index 保留频率和偏好，Operational pattern 低频聚合工具链摩擦点，Substantive summary 只处理实质性方法论与文章素材。
- 明确工具链失败、hook 丢失、发布失败等 session 的升格规则：同类问题重复出现或形成可复用诊断流程时，才从 `index_only` 升格为 `tooling_fix`。
- 明确夜间调度最终采用“脚本优先、launchd 后置”：先手动运行 `scripts/dream_sweep.py`，稳定后由 macOS `launchd` 定时调用脚本。

### 文档完善

- `references/11-dream-sweep.md` 新增 `session_class`、`summary_policy`、`noise_reasons` 设计字段，以及噪音分类表和调度决策。
- `DECISIONS.md` 新增 DEC-024，记录噪音 session 只建薄索引与 `launchd` 调度边界。
- `TASKS.md` 增加 v0.3.17 完成记录，并把 v0.4 待办拆出 session classifier、noise gate、operational pattern 聚合和 `launchd` 安装器。

## [0.3.16] - 2026-06-13

### 改进

- 将 v0.4 方向正式收敛为 `Timeline Dream Sweep`：以 Claude Code 与 Codex 双来源 session 索引为基础，按时间线识别用户研究重点、法律工作重点和 agent 协作模式变化。
- 明确 `SessionEnd` hook 的边界：只为当前 Claude Code session 生成轻量索引，不扫描历史 session，不启动跨 session 长总结。
- 明确夜间脚本 / 定时任务的边界：补扫历史 Claude Code transcripts 与 Codex archived sessions，建立主题聚类，并只对高价值 cluster 启动独立 headless 总结 session。
- 新增 Timeline 报告层：跨主题说明一段时间内的工作重点迁移；Dream 报告继续作为单主题任务链的审计层。

### 文档完善

- `references/11-dream-sweep.md` 改为 Timeline Dream Sweep 跨 Agent 设计草案，补充 Claude Code + Codex 双来源、两阶段架构、统一摘要 schema、时间线维度和夜间调度边界。
- 更新 v0.4 升级建议，明确首版实现顺序为“索引优先、手动 dry-run 优先、夜间总结后置”。
- 同步 `config/core_skills.yaml`、`templates/core_skills.yaml` 和核心清单 schema 中的 `skill-evolve` 版本、关键词与 reference 描述。

### 待办事项

- 后续实现 `scripts/dream_sweep.py` 时，应先做 source adapters、normalized session summaries、timeline index 和 topic clusters，再接入 launchd / cron / Codex automation。

## [0.3.15] - 2026-06-13

### 新增

- 新增 `references/11-dream-sweep.md`，正式记录 v0.4 Dream Sweep 跨 Session 沉淀设计草案。
- 登记 Dream Sweep 的跨 session 设计草案，覆盖任务聚合、夜间扫描和报告。

### 改进

- `SKILL.md` 明确：当本次会话只是长周期 Skill 迭代任务的片段时，应标注“需跨 session 交叉验证”，不要把局部结论包装成完整方法论。
- `references/08-evaluation-loop.md` 增加“长周期任务的片段标注”，为后续 Dream Sweep 铺垫评估边界。
- `references/09-programmatic-gates.md` 补充单 session 评分不能替代跨 session 成熟度判断。
- `templates/evaluation-record.md` 增加“长周期片段”和“纳入 Dream Sweep”人工处理项。
- `config/core_skills.yaml` 和模板同步 `skill-evolve` 版本到 v0.3.15，并加入 Dream Sweep / 跨 session 关键词与 reference。

### 修复

- 修正 `install_session_end_hook.py` 在符号链接目录下运行时的路径识别问题。

### 待办事项

- v0.4 实现 per-session 轻量摘要、`scripts/dream_sweep.py`、Dream 报告输出和跨 session 聚类验收。

## [0.3.14] - 2026-06-13

### 修复

- 修复多个 `SessionEnd` hook 顺序触发时，Skill Evolve 的 headless `claude -p` 可能继承父 Claude Code 会话环境的问题。
- 启动 headless 分析前清理 `CLAUDECODE`、`CLAUDE_SESSION_ID` 等父会话变量，并固定 `cwd` 到 Skill Evolve 根目录，降低与 Legal Knowledge Engine 等其他 hook 的上下文串联风险。

### 文档完善

- 在 Hook 配置文档中补充多 hook 顺序触发时的隔离策略说明。

## [0.3.13] - 2026-06-13

### 改进

- 新增 `review/output/` 作为待用户查看的产物入口，升级建议写入 `review/output/upgrade-direction/`，文章草稿写入 `review/output/articles/`。
- 新增 `review/archive/` 作为审完后的内部存档区，避免新产物一生成就进入 archive 造成状态含义混乱。
- 更新脚本、headless prompt、核心清单 schema 和人工审流程，明确 output 是待审，archive 是已处理。

### 迁移

- 已将现有升级建议和文章草稿从 `review/upgrade-direction/`、`review/articles/` 迁入 `review/output/`。

## [0.3.12] - 2026-06-13

### 改进

- 将人工审材料统一收敛到 `review/`：升级建议写入 `review/output/upgrade-direction/`，文章草稿写入 `review/output/articles/`，纠正记录写入 `review/review-log.md`。
- 将候选记录归入 `runtime/learning-candidates/`，与 hook 记录、评估日志、库存缓存和运行日志同属机器运行产物。
- 明确 `config/core_skills.yaml` 是稳定配置源；`runtime/skill-inventory.json` 和 `runtime/skill-inventory.md` 只是按配置扫描生成的运行缓存。

### 迁移

- 已迁移现有文章草稿、升级建议、纠正记录和候选记录到 `review/` 与 `runtime/` 的新边界。

## [0.3.11] - 2026-06-13

### 改进

- 文章草稿目录改为扁平的 `articles/`，不再区分 `draft/` 与 `published/`。
- 纠正面板从 Skill 根目录迁入 `reviews/review-log.md`，避免根目录继续堆积运行沉淀文件。
- 新生成候选记录、升级方向清单和文章草稿统一使用 `YYMMDD_` 文件名前缀，例如 `260613_<topic>.md`。

### 迁移

- 已迁移现有文章草稿、升级方向清单、候选记录和 `review-log.md` 到新目录与新命名。

## [0.3.10] - 2026-06-12

### 改进

- 将核心 Skill 清单迁入本 Skill 目录的 `config/core_skills.yaml`，使 hook、运行状态、库存清单、沉淀材料和核心配置保持自包含。
- `sediment_guard.py` 默认读取 `config/core_skills.yaml`，并保留 `SKILL_EVOLVE_CORE_SKILLS` 作为高级覆盖入口。
- `templates/core_skills.yaml`、reference 文档和人工审模板统一改为 Skill 内部核心清单路径。

### 迁移

- Skill Evolve 不再使用 `~/.claude/core_skills.yaml` 或 `~/.claude/skill-evolve/`；`~/.claude/settings.json` 仅用于注册 Claude Code 的 `SessionEnd` hook。

## [0.3.9] - 2026-06-12

### 改进

- 将运行状态、hook 触发记录、评估日志、库存缓存和 headless 日志默认迁入本 Skill 目录的 `runtime/`。
- `~/.claude/` 仅保留 Claude Code 必需的 `settings.json` hook 配置和 `core_skills.yaml` 核心清单，不再新建 `~/.claude/skill-evolve/` 状态目录。
- `refresh_skill_inventory.py` 默认输出到 `<skill-evolve-root>/runtime/skill-inventory.json` 和 `skill-inventory.md`。

### 迁移

- 已将现有运行状态文件从 `~/.claude/skill-evolve/` 移入 `runtime/`，并清理旧状态目录。

## [0.3.8] - 2026-06-12

### 改进

- 移除脚本中的本机固定路径优先逻辑，默认从 `scripts/sediment_guard.py` 所在位置推导 Skill 根目录。
- `install_session_end_hook.py` 默认从自身所在目录推导 hook 脚本路径，便于其他用户安装到不同目录。
- 支持通过 `SKILL_EVOLVE_SKILL_ROOT`、`SKILL_EVOLVE_SEDIMENT_ROOT`、`SKILL_EVOLVE_STATE_ROOT` 覆盖路径。

### 文档完善

- `references/01-hook-config.md` 增加路径可迁移性说明。
- `templates/core_skills.yaml` 使用 `<skill-evolve-root>` 占位，不再写死本机路径。

## [0.3.7] - 2026-06-12

### 改进

- 将人工审沉淀材料输出目录迁移到本 Skill 目录：`learning-candidates/`、`upgrade-direction/`、`articles/`、`review-log.md`。
- `~/.claude/skill-evolve/` 仅保留运行状态、hook 触发记录、评估日志、库存缓存和 headless 日志。
- Headless prompt 新增 `{{SEDIMENT_ROOT}}`，明确区分运行时目录与沉淀输出目录。

### 迁移

- 已将现有候选记录、升级建议、文章草稿和 `review-log.md` 从 `~/.claude/skill-evolve/` 移入本 Skill 目录。

## [0.3.6] - 2026-06-12

### 修复

- 修复符号链接目录下 hook 与 headless prompt 的路径解析问题。
- 对外 Skill 路径随实际安装位置解析。

### 改进

- `install_session_end_hook.py` 默认使用统一路径；发现旧路径 hook 时会原地更新，不重复追加。
- `sediment_guard.py` 区分执行路径、对外 Skill 路径和备用资源路径，资源读取兼容符号链接与真实目录。

## [0.3.5] - 2026-06-12

### 改进

- 将 headless 分析 prompt 改为短启动器：只传 Skill 路径、本次 transcript、核心清单、库存清单、门控结果和候选记录，由独立 session 先读取 `SKILL.md` 再按 reference 执行。
- Headless prompt 继续保留 `SE_EXTRACTION` 标记，便于 transcript 侧识别总结 session。

### 技术优化

- 新增 `SKILL_EVOLVE_HEADLESS=1` 环境标记，作为 prompt 标记之外的第二层反递归防护。
- 扩大 transcript 头部标记扫描范围，降低 headless 总结会话未被识别的风险。

## [0.3.4] - 2026-06-12

### 新增

- 新增 `scripts/refresh_skill_inventory.py`，自动扫描用户常用的两套 Skill 来源目录。
- 新增运行时库存文件：`~/.claude/skill-evolve/skill-inventory.json` 与 `~/.claude/skill-evolve/skill-inventory.md`。
- 新增 `references/10-skill-inventory.md`，说明核心清单与库存清单的分工。

### 改进

- `sediment_guard.py` 在非排除目录的 `SessionEnd` 中最多每 1 小时自动刷新一次 Skill 库存。
- Headless 分析 prompt 增加 `{{SKILL_INVENTORY}}`，使独立分析 session 能读取当前 Skill 库存。
- `~/.claude/core_skills.yaml` 与模板增加两套常用 Skill source，并保留旧 `litigation-skills` 键用于兼容。

### 技术优化

- 明确库存清单只用于介绍、检索和候选判断，不替代人工维护的核心清单，也不自动触发成熟 Skill 修改。

## [0.3.3] - 2026-06-12

### 新增

- 新增文章机会门控：`article_opportunity` 单独计算文章评分、素材信号和是否应生成文章草稿。
- 新增文章素材信号识别：录屏、截图、视频证据、抽帧、多模态、能力边界、失败模式、可迁移场景等。

### 改进

- Headless prompt 明确文章不是升级建议的附属品；当文章机会明确时，即使 Skill 升级价值较弱，也可以生成文章草稿。
- `references/04-article-template.md` 和 `templates/article.md` 改为“实战复盘型文章”结构，贴近“从具体材料规模到结果”的写法。
- 候选记录和评估日志增加文章机会评分，便于后续人工审。

### 修复

- 修复 headless prompt 模板读取时被内层 Markdown 代码块截断的问题，确保 `article_opportunity` 等评估摘要能完整传给独立分析 session。

## [0.3.2] - 2026-06-12

### 新增

- 新增 `~/.claude/skill-evolve/hook-runs.jsonl`，记录每次 `SessionEnd` hook 调用状态。
- hook 触发记录包含跳过原因，如 `missing_session_id`、`transcript_not_found`、`excluded_project_path`、`core_skills_unavailable`、`no_text_extracted`、`not_considered`。

### 改进

- 区分 hook 触发记录与沉淀评估记录：`hook-runs.jsonl` 记录每次调用，`evaluation-log.jsonl` 只记录进入程序化评估的会话。
- 更新 `SKILL.md`、`references/01-hook-config.md`、`references/08-evaluation-loop.md` 和核心清单版本到 v0.3.2。

## [0.3.1] - 2026-06-12

### 新增

- 新增 `scripts/install_session_end_hook.py`，用于把 Skill Evolve 的 `SessionEnd` hook 安装到 `~/.claude/settings.json`。
- 安装器支持 `--dry-run`、重复安装检测、写入前备份、保留已有 hook。

### 改进

- `references/01-hook-config.md` 增加 hook 稳健性说明，并将安装脚本作为推荐安装方式。
- `SKILL.md` 增加内置安装器说明。
- 同步 `core_skills.yaml` 模板与运行时清单中的 `skill-evolve` 版本到 v0.3.1。

## [0.3.0] - 2026-06-12

### 新增

- 新增程序化沉淀门控：根据核心关键词、候选 Skill、用户显式沉淀信号、方法论信号、敏感信息、历史重复和拒绝记录计算评分。
- 新增三档动作：`skip`、`candidate_only`、`generate_upgrade`，避免一命中关键词就启动独立分析。
- 新增评估日志：`~/.claude/skill-evolve/evaluation-log.jsonl`。
- 新增候选记录目录：`~/.claude/skill-evolve/learning-candidates/`，用于人工审前排队。
- 新增 `references/08-evaluation-loop.md`、`references/09-programmatic-gates.md` 和 `templates/evaluation-record.md`。

### 改进

- `scripts/sediment_guard.py` 只在高置信或用户明确要求沉淀时启动 headless Claude；中置信只写候选记录。
- 候选记录只保存脱敏片段，不复制 transcript 原文。
- 将“不要直接改成熟 Skill”识别为人工审边界，而不是负向沉淀意图。
- Headless prompt 现在接收程序化评估摘要和候选记录路径，输出更保守。

### 技术优化

- 修正历史升级建议去重目录，从 Skill 源目录改为运行时目录 `~/.claude/skill-evolve/upgrade-direction/`。
- 同步 `SKILL.md`、`core_skills.yaml` 模板和运行时 `~/.claude/core_skills.yaml` 到 v0.3.0。

## [0.2.2] - 2026-06-12

### 改进

- 新增 `references/07-headless-analysis-prompt.md`，将启动独立 headless 分析 session 的完整提示词模板从脚本中外置。
- `scripts/sediment_guard.py` 改为读取 prompt reference，并替换日期、transcript 路径、核心清单路径、输出目录和模板路径等占位符。
- `SKILL.md` 与 `references/05-agent-prompt.md` 增加对 headless prompt reference 的说明。

### 技术优化

- 降低后续调 prompt 的成本：修改分析策略时优先改 reference，不需要改 Python 逻辑。
- 保留脚本内 fallback prompt，避免 reference 缺失时完全无法启动。

## [0.2.1] - 2026-06-12

### 修复

- 统一 hook 事件为 `SessionEnd`，删除 `Stop hook` 作为主流程的口径。
- 统一 Skill 目录名与 frontmatter `name` 为 `skill-evolve`，显示名保留 `Skill Evolve`。
- 统一 `core_skills.yaml` schema：文档和模板改为实际使用的 `skill_sources`、`core_skills[].id`、`source`、`references[].file`、`upgrade_target`、`priority`。
- 修正模板路径，移除错误的 `~/.claude/Library/...` 路径。
- 将 `sediment_guard.py` 纳入本 Skill 的 `scripts/` 目录，运行时输出仍写入 `~/.claude/skill-evolve/`。
- 脱敏示例中的具体案件线索、TSA 编号和账号。

### 改进

- 精简 `SKILL.md`，删除重复工作流，明确“只生成建议和草稿，不直接修改其他 Skill”。
- 保留 ClawHub 所需 frontmatter 字段：`version`、`license`、`author`、`homepage`。
- `sediment_guard.py` 支持优先读取 hook 输入中的 `transcript_path`，并兼容紧凑版核心清单 schema。

### 待办

- 端到端启用 `SessionEnd` hook 后，用真实会话验证沉淀质量。
- v0.3 再推进历史 session 扫描、用户配置和 Recurrence-Count 规则算法。

## [0.2.0] - 2026-06-12

### 新增

- **约束门控**（sediment_guard.py 升级）：借鉴 Hermes `skills_guard.py` 安全扫描 + self-improving-agent 质量门控设计
  - 文件大小检查：升级目标文件 ≤ 100KB（与 Hermes 一致）
  - 命名规范检查：references/ 文件名符合 `^\d{2}-[\w-]+\.md$`
  - 案件特定数据黑名单：升级内容不写案号/品牌名/原被告/具体产品名
  - 门控失败降级：输出 systemMessage 提示而不阻塞对话结束
- **纠正面板**（review-log.md 模板 + sediment_guard.py 辅助函数）：借鉴 self-improving-agent 严重程度分级
  - 3 档严重程度：Critical（⚠）/ Major（✦）/ Minor（·）
  - 关键词自动检测（"caught me" / "gotcha" / "doesn't work" 等）
  - 历史去重：agent 生成建议前先读 review-log.md 避免重复
- **历史去重**（agent prompt 升级）：先读 `~/.claude/skill-evolve/review-log.md` + 各 skill 的 `DECISIONS.md` + `archive/` 避免重复建议
- **创建新 skill 建议**（新增能力）：当优化超出当前 core_skills.yaml 范围时（如跨领域/跨类型），agent 应建议新建 skill 而非硬塞
- **改造版"定期自省"**（Hermes 借鉴）：Hermes 原本每 10 轮触发，我们改为 SessionEnd 一次性自省整个会话
- **`~/.claude/skill-evolve/review-log.md`** 初始化（纠正面板模板）
- **TASKS.md**（v0.2 增量任务 + v0.3+ 远期任务）
- **ChatGPT DR 研究的抽取算法借鉴**（写进 references/05-agent-prompt.md §v0.2 重要约束 5）

### 改进

- `SKILL.md` version 0.1.0 → 0.2.0
- `SKILL.md` description 强调 v0.2 借鉴 Hermes + 新增约束门控/纠正面板/创建新 skill 建议等
- `SKILL.md` 工作流加"约束门控"步骤
- `SKILL.md` 加"依赖"章节（PyYAML 硬依赖）
- `SKILL.md` 加"v0.3 远期规划"（扫描本地 session + 个性化上下文 + 自进化规则算法）
- `LICENSE.txt`: CC-BY-NC-SA-4.0 → CC BY-NC（按 AGENTS.md 法律专业应用规范）

### 待办

- agent hook 尚未在 `~/.claude/settings.json` 启用——本版本先提供文档 + 模板
- 缺真实案件端到端测试——agent 输出质量需根据第一次实际跑动调优
- 扫描本地 Codex/Claude Code 历史 session 能力（v0.3 远期）
- 个性化上下文驱动（v0.3 远期，需 `user-config.yaml`）
- Auto Evolve / Self-Improving Agents 规则引擎集成（v0.3 远期）

## [0.1.0] - 2026-06-11

### 新增

- `Skill Evolve` Skill v0.1.0 首次发布。
- 主文档 `SKILL.md`：定位"Skill 自迭代的执行者"，在每次 Claude Code 对话结束时（SessionEnd hook 触发）调用 agent 分析 transcript，输出两类产出（**不直接修改 skill 内部**）。
- `references/01-hook-config.md`：SessionEnd hook 配置示例。
- `references/02-core-skills-yaml.md`：核心 skill 清单 schema（`~/.claude/core_skills.yaml`）。
- `references/03-sediment-template.md`：升级方向清单 Markdown 模板。
- `references/04-article-template.md`：文章草稿 Markdown 模板。
- `references/05-agent-prompt.md`：agent prompt 模板（完整版 + 缩短版）。
- `references/06-review-workflow.md`：人工审工作流。
- `templates/core_skills.yaml`：核心 skill 清单 YAML 模板。
- `templates/upgrade-direction.md`：升级方向清单 Markdown 模板。
- `templates/article.md`：文章草稿 Markdown 模板。
- `examples/2026-06-11_video-infringement-comparator_v0.5_升级建议.md`：基于某著作权案的脱敏手动示例。

### 文档完善

- 文档总数 8 份（SKILL.md + 6 references + 3 templates + 1 example）。
- 设计灵感：`legal-knowledge-engine` 的"主动识别 + 检索 archive"机制。
- 飞轮结构：工作 → 优化工作（迭代 skill）→ 附带产出（写文章）→ 行业传播 → 反馈回流。

### 已知缺口

- agent hook 尚未在 `~/.claude/settings.json` 启用
- 缺真实案件端到端测试
