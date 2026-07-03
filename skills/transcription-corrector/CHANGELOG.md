# 变更日志

本项目的所有重要变更都将记录在此文件。

## [1.0.8] - 2026-07-01

### 变更

- **Step 4.5 摘要布局改为就地嵌入（v1.4）** — 取消"顶部聚合块 + `<!-- AI-SUMMARY:START/END -->` markers"的旧布局。改为：每个章节的"本章摘要 + 关键洞察"**直接写在对应 H2 标题之下、原话正文之前**；主标题单行置文首（H1 下、第一 H2 前）、关键词单行置文末（最后一章原话之后），不再把逐章摘要汇聚成独立区块。同步更新：Phase 4 表格行（Step 4.5）、Step 4.5 触发条件 / 核心原则 / 输出位置 / 就地嵌入格式示例 / 文首主标题与文末关键词 / 生成原则 / 严格不做 / 与 Step 4.4 边界表 / 幂等与验证 / 校对日志格式。**动机**：顶部聚合块使摘要与正文分离，读者在某章想看概要需回滚顶部；就地嵌入让摘要紧贴所概括原话、一章自洽，阅读和下游复用（如抽成课程章节）更顺。DEC-015 落地

### 元数据

- frontmatter version 1.0.7 → 1.0.8

---

## [1.0.7] - 2026-06-08

### 重构

- **references/skill_overview.md 拆分为两份** — 拆成 `references/scope.md`（概述 / 适用边界）与 `references/config-decoupling.md`（配置示例 / 配置解耦原则），单一职责更清晰。原 `skill_overview.md` 删除。SKILL.md "适用场景 / 不适用" 与 "配置示例 / 配置解耦原则" 两个跳转锚点分别指向对应文件；参考文档列表同步更新。DEC-013 落地
- **references/ 子文件无 frontmatter** — 删除 `references/skill_overview.md` 中冗余的 `name` / `description` frontmatter 块；`scope.md` / `config-decoupling.md` 新建时即不带 frontmatter（frontmatter 是 SKILL.md 唯一元数据来源）

### 文档清洁

- **公开文件清理外部 skill / 项目引用** — DECISIONS.md 中 6 处 "课程生成类工作流" 改为 "课程整理类工作流"；1 处 "借鉴 OCR 后处理中'基础空白清理'思路" 改为 "新增 Step 3.5 基础空白清理"（去除借鉴标注）；2 处 "agent 报告" 改为 "分析反馈"；DECISIONS.md "明确不放的" 列表去掉具体产品名（"Devonthink、Antigravity、Moltbook、Vibe Coding、Vibe Working、Manus、FunASR、MinerU 等" 改为 "仅本机使用的特定技术栈产品"）。CHANGELOG.md v1.0.0 段落 "听悟" 改为 "云端 ASR"。本条覆盖自检。
- **frontmatter description 重写（按"功能 / 触发 / 不触发"三段式）** — 从 369 字符（v1.0.6）压到约 116 字符（v1.0.7）："转录稿纠错与轻度优化。本技能应在用户需要按用户词典纠正 ASR 转录稿同音字与英文专有名称漂移时使用。不要用于：重写为课程章节、报告、总结，或完全空白的素材创作。" 归档策略 / 原始文件不动 / 内部步骤 / 默认行为 / 产物结构全部移除——这些应出现在 SKILL.md 正文，不应进入 description 触发指纹。对齐 skill-architect 5.17。

### 元数据

- frontmatter version 1.0.6 → 1.0.7

---

## [1.0.6] - 2026-06-08

### 文档

- **SKILL.md 拆分以达 skill-architect 500 行建议** — 把"概述 / 适用场景 / 不适用 / 配置示例 / 配置解耦原则 / 参考文档"6 个章节从 SKILL.md 拆到 `references/skill_overview.md`。SKILL.md 从 528 行降到 445 行（-83），聚焦"工作流骨架"。新增 `references/skill_overview.md` 121 行，明确三个 references 文件的职责分工：
  - `first_use.md` — 一次性配置引导
  - `correction_patterns.md` — 工作流判断准则
  - `skill_overview.md` — 概述/适用边界/配置示例/解耦原则

  SKILL.md 顶部 frontmatter description 仍 137 字符，未变（description 只描述触发场景，不重复概述）。
  references 内已有 frontmatter（name/description）便于未来的 skill-architect 审查

---

## [1.0.5] - 2026-06-08

### 行为规则

- **Step 体系重构为 5 个 Phase** — SKILL.md 工作流从 `Step 0/0.5/1/2/3/3.5/3.6/4/5` 整数小数混用重构为 5 个 Phase + 子步骤：
  - **Phase 1 准备**：Step 1.1 读取配置 / Step 1.2 TXT→MD 转换
  - **Phase 2 识别**：Step 2.1 识别文件结构 / Step 2.2 通读识别高置信误转写
  - **Phase 3 修正（默认开启）**：Step 3.1 词典统一替换（改字）/ Step 3.2 基础空白清理（改空白）/ Step 3.3 口语词精简（删字）
  - **Phase 4 润色（默认关闭）**：Step 4.1 发言人合并 / Step 4.2 标点规范 / Step 4.3 段落切分
  - **Phase 5 输出**：Step 5.1 主归档（必出）/ Step 5.2 源文件目录镜像（必出）

  重构理由：原"0.5/3.5/3.6"小数命名让人误以为是 Step 3 的子步骤，但实际和 Step 4（润色）同级。Phase 分组后"准备 / 识别 / 修正 / 润色 / 输出"五阶段性质分明，Phase 3 内部三个 Step 改的是三类不同对象（字 / 空白 / 填充词），各自独立可单独审计。DEC-009

- **Step 3.3 加段首/段中/段尾决策树** — SKILL.md Step 3.3 新增"段首 vs 段尾 vs 段中 决策树"表格，明确位置判定标准和处理（v2 激进版起）。配合 references/correction_patterns.md §11"段中并列停顿 啊 的识别模式"，把口语词判断从经验变成可查表

### 文档

- **SKILL.md frontmatter version 升 1.0.5**
- **references/correction_patterns.md 全面同步 step 引用**：从 `Step 0/3/3.5/3.6/4` 更新为 `Step 1.1/3.1/3.2/3.3/4.1/4.2/4.3` Phase-based 编号
- **SKILL.md Phase 3 顶部加导航说明**："改字 / 改空白 / 删字"三类操作性质独立可单独审计

---

## [1.0.4] - 2026-06-08

### 行为规则

- **Step 3.6 段首节奏标记默认删除**（v2 激进版起）— SKILL.md §3.6.2 保留规则从"段首/段尾的语气停顿——保留"改为"段尾的语气停顿——保留（标记说话节奏收束）"；references/correction_patterns.md §7.2 同步更新；典型案例表 L207 行的理由说明同步更新。理由：v1 → v2 → v3 三轮迭代中用户明确反馈"呃没删干净"——段首节奏标记保留的实用价值低于段尾收束语义。DEC-008 落地
- **Step 3.6 必检清单** — SKILL.md Step 3.6 末尾新增"必检"小节，要求 agent 在 correction_log.md 中必须包含"口语词精简"小节、按段首/段中/段尾三类分别计数。避免 v1.0.2 那种"漏跑整节无日志"的 bug 重现。DEC-008 复盘

### 知识沉淀

- **ASR 误转写高频模式（5th/6th 组踩坑沉淀）** — references/correction_patterns.md 新增 §8"AI 培训类转录稿高频 ASR 误转写模式"，枚举本轮命中 6 类：
  - 中文同音字误转写（阿尔法→Alpha、腾讯文宝→腾讯元宝）
  - 英文专有名词音节丢失（沃克巴里→WorkBuddy、work by→WorkBuddy）
  - 英文专有名词被中文重码替代（cloud code→Claude Code、deep sick→DeepSeek）
  - 大小写漂移（A I→AI、M C P→MCP、auto→Auto）
  - 复合错（断词 + 漏字）"让，如果 body 帮我们"→"让 WorkBuddy 帮我们"
  - 弱语义同音字（style/scale→skill、out style→out skill）
- **段中并列停顿 啊 的识别模式** — references/correction_patterns.md §7.5 增补：并列停顿 啊 在两个名词/动词短语之间充当连接，删除会破坏并列结构（如"证据啊，包括"、"合同啊、结算单啊"）。识别要点：前后都是可独立成义的名词/动名词 + 顿号/句中位置。区分于纯填充 段中独立 啊
- **多轮迭代处理流程** — SKILL.md §0 增加"多轮迭代"小节：第二轮起的 source file 是上一轮 _corrected.md（不是 raw）；Step 3 仅处理 v1 未替换的新项；Step 3.6 按当前规则（含激进版开关）跑全量

### 文档

- **"首次使用"小节下移到 references/first_use.md** — SKILL.md 主体聚焦工作流骨架；"复制 example.yaml、维护本地词典、跑一次试跑、多用户软链方案"等一次性配置引导放到独立 references 文件；SKILL.md 顶部加引用块指向该文件 + correction_patterns.md
- **SKILL.md 一级标题去掉版本号** — `# Transcription Corrector v1.0.3` → `# Transcription Corrector`；版本号仅保留在 frontmatter `version` 字段
- **"配置解耦原则"小节明确归类为"评价规范"** — 顶部加"本节是 skill 公开化时需要满足的评价规范的一部分，与工作流无关"的定位说明，并列出模板/实际配置/敏感数据三条核心约定；与 skill 公开化审查清单的配置文件规范对齐
- **references 目录新增 first_use.md** — 与 correction_patterns.md（工作流判断准则）分工清晰

## [1.0.3] - 2026-06-08

### 新增

- **Step 3.6 口语词精简（默认开启）** — 新增独立步骤，删除独立出现的纯填充词（"呃/啊/哦/哎"、"那个/就是说/然后呢/对吧/你知道吗/怎么说呢/这样子/其实呢/但是呢"）。与 Step 3.5 基础空白清理同级，**默认开启**（仅删白名单纯填充词、不改风格）。明确"表态类/逻辑连接/认知停顿后接完整内容/段首段尾"等保留规则，三重确认判断
- **example.yaml 扩展为"常见技术名词 + 常见法律术语"** — 公开模板新增 27 项：技术名词（Cursor、Anthropic、OpenAI、Coze、Ollama、Manus、Moltbook、DeepSeek、腾讯元宝、豆包、智和、Alpha、Obsidian、Flomo、Cubox、FunASR、MinerU、Discord、Slack、Docker、Playwright、MonoRepo、clawhub、GitHub、Markdown、MCP、AI）+ 法律术语（商标、著作权、合同、诉讼、仲裁、代理、律师、当事人）。遵守"换另一个用户 clone 也需要"的边界
- **references §7 口语词精简规则** — 白名单/保留规则/判断原则/严格不做/典型易误判案例 5 小节
- **references §6.4 步骤对照表扩展** — 把"Step 3 改字、Step 3.5 改空白、Step 4 改结构"扩为"Step 3 改字、Step 3.5 改空白、Step 3.6 删填充词、Step 4 改结构"

### 改进

- **本地词典采纳实战反馈** — `user_dictionary.yaml` 追加：DeepSeek、Auto、AI、MCP、腾讯元宝、豆包、智和、Alpha、supreme legal analyzer、C1-C6、六大矛盾、四大图表
- **配置解耦原则明确收纳范围** — SKILL.md"配置解耦原则"小节细化"换另一个用户 clone 也需要"的判定标准；明确 example.yaml 收纳常见技术名词 + 常见法律术语，但不放个人工作栈 / 个人身份 / 极通用词

## [1.0.2] - 2026-06-08

### 新增

- **基础空白清理（Step 3.5，默认开启）** — 独立于 Step 3 词典替换与 Step 4 润色，作为"无损格式化"步骤默认开启。覆盖行首/行尾多余空格、连续空行压缩、英文单词间全角空格、半角空格夹在中文之间、中文数字+空格+级/章/节合并、中文/英文标点周围空白标准化。专有名称内部断裂空格的合并仍走 Step 3 词典替换路径
- **源文件目录镜像（Step 5.2）** — 在保留 skill 内 archive/ 主归档的同时，向原始文件所在目录同步输出一份 `{原文件}_corrected.md` 易访问副本。冲突时用时间戳后缀区分，源文件目录只读 / 不可写时静默跳过并在 `meta.json` 记录 `source_mirror: "skipped"`

### 改进

- **公开文件不出现其他 skill 名称** — SKILL.md / CHANGELOG.md / DECISIONS.md / TASKS.md / references/correction_patterns.md / config/user_dictionary.example.yaml 中所有对外部 skill 名称的引用（课程生成类、通用转录引擎、其他工作流等）替换为通用描述；保留与 transcription-corrector 自身相关的工作流引用
- **本地用户词典扩展** — `config/user_dictionary.yaml` 追加个人工作栈常用术语（Devonthink、Cursor、Antigravity、Anthropic、OpenAI、Discord、Slack、Obsidian、Coze、Ollama、Flomo、Cubox、MinerU、FunASR、Docker、Playwright、MonoRepo、Manus、Moltbook 等）、工程概念术语（commit / push / pull / frontmatter 等）与业务领域术语（知识产权、专利）；保留"目标值+权重"原则

### 文档

- SKILL.md 新增"Step 3.5 基础空白清理"小节
- SKILL.md 重写"Step 5 输出"为双写策略（5.1 主归档 + 5.2 源文件目录镜像）
- references/correction_patterns.md 新增"§6 基础空白清理规则"小节
- DECISIONS.md 新增 [DEC-008] 基础空白清理作为独立步骤的决策
- DECISIONS.md 新增 [DEC-009] 双写输出策略的决策
- DECISIONS.md 修订 [DEC-001] [DEC-003] 等历史决策中所有对外部 skill 名称的引用为通用描述

## [1.0.1] - 2026-06-07

### 新增

- **TXT 输入支持** — 新增 Step 0.5：当输入是 `.txt` 文件时，先做格式转换（识别发言人+时间戳行转 Markdown 加粗、保留原始分块、输出 `_converted.md` 中间产物）再进入 Step 1
- **配置解耦原则** — SKILL.md 新增"配置解耦原则"小节，明确 example.yaml（入仓）与 user_dictionary.yaml（git ignore）的边界
- **首次使用提示** — SKILL.md 顶部加"首次使用"小节，引导用户复制 example → 改名为真实配置
- **skill 局部 .gitignore** — `config/.gitignore` 声明 user_dictionary.yaml 不入仓

### 改进

- **description 精简** — frontmatter description 从 4 句压缩到 1 句；"不适用场景"挪到正文"不适用"小节
- **公开文件不出现作者名** — CHANGELOG / TASKS / DECISIONS / references / example.yaml 中"作者本人姓名"作为描述示例的提及全部移除；保留 frontmatter 的 `author` 字段

## [1.0.0] - 2026-06-07

### 新增

- **转录稿纠错与轻度二次优化** — 读 raw 转录稿（本地转录引擎 / 云端 ASR 等输出），按用户词典纠正同音字、英文专有名称大小写与拼写（WorkBuddy、Claude Code 等）
- **用户词典机制** — `config/user_dictionary.yaml` 维护"目标值"，AI 通读全文后基于上下文判定是否替换
- **三重确认原则** — 替换前必须同时满足：词典里有目标值、上下文明确指向、形式漂移证据成立
- **校对对照日志** — 输出到 `archive/{date}_{file}/correction_log.md`，每条替换可追溯
- **轻度润色开关（默认关闭）** — 可选合并同发言人连续发言、规范标点、切分极长段
- **原始文件保持不动** — 所有结果自包含存储在 `archive/` 下
- **归档结构** — `archive/YYYYMMDD_HHMMSS_{原文件}/` 内含 corrected 副本、polished 副本（如启用）、correction_log.md、meta.json
- **公开的词典 YAML 格式** — `version` + `terms` 列表结构，可与外部场景软链复用同一份用户词典

### 文档

- `SKILL.md` — 完整工作流（Step 0~5）、边界、模式选择
- `references/correction_patterns.md` — 误转写识别判断准则（不是映射表）
- `config/user_dictionary.example.yaml` — 词典模板，含"目标值+权重"原则说明
