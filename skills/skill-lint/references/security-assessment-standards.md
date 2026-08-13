# Security Assessment Standards

本文件定义 Skill 安全性评估规则。它用于 `skill-lint` 的质量审查报告，不替代运行时沙箱、依赖漏洞扫描或人工代码审计。

## 定位

本文件是安全评估的**规则来源**；执行时应**先运行确定性扫描器** `scripts/security_scan.py`，再用本文件判断误报、定级与修正。

```bash
python3 scripts/security_scan.py audit --candidate-root /path/to/skill   # 单 Skill
python3 scripts/security_scan.py batch --root /path/to/skills            # 集合
```

扫描器输出 JSON 报告（schema_version=1，字段含 status/summary/findings），退出码：0=PASS、1=FAIL（存在 critical/high）、2=范围错误（未发现 SKILL.md）。`--online` 时额外查询 OSV API 已知 CVE（默认离线只做版本 pin 检查）。

### 扫描器覆盖模式与 SkillSpector 对应

| 扫描器 capability | 类别 | 对应 SkillSpector 模式 |
|---|---|---|
| `subprocess` / `dynamic_import` / `syntax_error` | Dangerous Code Execution | Behavioral AST: exec/eval |
| `network` | Data Exfiltration | External Transmission |
| `install` | Supply Chain | 自动安装 / External Script Fetching |
| `unpinned` / `cve` | Supply Chain | Unpinned Dependencies / Known Vulnerable Dependency |
| `secret` | Hardcoded Credential | Credential Access |
| `credential` | Credential Access | Env Variable Harvesting |
| `taint` | Taint Tracking | Direct Taint Flow / Variable-Mediated Taint Flow |
| `enumerate` | File System Enumeration | File System Enumeration |
| `unicode` | Unicode Deception | Hidden Instructions / Unicode Deception |
| `mcp_wildcard` | MCP Least Privilege | Wildcard Permission |
| `scope_creep` | Description-Behavior Mismatch | Context-Inappropriate Capability / Scope Creep |
| `disclosure` | Missing User Warnings | Missing User Warnings |
| `permission` | MCP Least Privilege | Underdeclared Capability / Missing Permission Declaration |
| `context_mismatch` | Context-Inappropriate Capability | 描述与行为不一致 |
| `prompt_injection` | Prompt Injection | Instruction Override / Hidden Instructions |

### 文档级 scope creep（Description-Behavior Mismatch）

> 对应 SkillSpector 的 *Scope Creep* / *Context-Inappropriate Capability* 文档类 finding。

扫描器检查 SKILL.md 与 references/*.md 是否引导执行**未在宣称用途中披露**的高风险动作：

| 类别 | 信号示例 | 默认级别 |
|------|----------|----------|
| publish | `clawhub publish`、`npm publish`、`发布到/执行发布` | High |
| repo_mutation | `sync-allowlist`、`force-push`、`filter-repo`、`重写历史` | Medium |

判定逻辑：先从 frontmatter `description` + 标题 + 正文开头提取技能宣称用途；若用途已提到该类别的披露词（发布/同步/白名单等）则不判 mismatch。只匹配"具体指令式动作"，不把依赖安装说明、安全文档中的概念性描述（如"webhook""外传"）当作 scope creep——依赖安装由 `install` 能力检测覆盖，网络外传由 `network` + disclosure 覆盖。

示例：git-batch-commit（宣称用途"Git 批量提交"）的 `references/skill-publish-sync-check.md` 引导 `clawhub publish` 与修改 `sync-allowlist.yaml` → 10 个 publish（High）+ 5 个 repo_mutation（Medium）finding，与 SkillSpector 结论一致。

### 已知局限（扫描器不覆盖，需人工审查）

- 跨文件数据流污点（如 env → subprocess 的命令拼接）只做单文件内流不敏感近似，不构建完整调用图；跨模块、动态导入后的调用需人工审查。
- scope creep 依赖宣称用途文本与动作模式的启发式匹配；技能宣称用途本身含糊时可能漏报，需人工判断。
- OSV CVE 查询依赖 `--online` 且依赖需 pin 版本；未 pin 时只报 Unpinned Dependencies。

## 审查范围

安全评估至少覆盖：

| 范围 | 检查重点 |
|------|----------|
| `SKILL.md` | 是否含提示注入、越权执行、敏感数据收集、隐藏指令或欺骗性描述 |
| `references/*.md` | 是否把高风险操作写成默认流程，是否绕过用户确认 |
| `scripts/*` | 命令执行、文件删除、网络外传、动态导入、混淆、敏感路径访问 |
| `config/*.example.*` | 是否出现真实凭证、真实 endpoint、真实 webhook 或本地路径 |
| `package.json` / 依赖文件 | 安装钩子、高风险依赖、可疑依赖、自动执行脚本 |
| MCP / agent 配置 | 是否声明权限、网络、文件系统、外部服务访问边界 |
| Git 历史辅助信息 | 是否出现过泄露凭证、删除后重加敏感文件、异常大文件或异常提交 |

## 风险类别

| 类别 | 说明 | 默认级别 |
|------|------|----------|
| 命令执行 | `subprocess`、`os.system`、shell 管道、Node 子进程等可执行任意命令的能力 | 严重 / 警告 |
| 下载并执行 | `curl | sh`、`wget | bash`、远程脚本下载后运行 | 严重 |
| 权限提升 | `sudo`、`chmod 777`、setuid、系统服务修改、绕过安全软件 | 严重 |
| 文件删除或破坏 | 递归删除、覆盖用户目录、无确认删除大量文件 | 严重 |
| 敏感文件访问 | `.env`、SSH/AWS/GPG 密钥、系统配置、用户 shell 配置 | 严重 / 警告 |
| 数据外传 | POST/PUT/PATCH、webhook、socket、WebSocket、未知外部 endpoint | 严重 / 警告 |
| 硬编码凭证 | API Key、Token、密码、私钥、Bearer token、真实 webhook URL | 严重 |
| 动态导入与混淆 | `eval`、`exec`、动态 require/import、base64 解码执行、隐藏字符 | 严重 / 警告 |
| 持久化行为 | cron、LaunchAgent、systemd、后台守护进程、自启动 | 严重 |
| 安装钩子 | `postinstall`、`preinstall`、自动安装脚本、静默后台安装 | 严重 / 警告 |
| MCP / 外部工具权限 | MCP 服务器、stdio/SSE transport、宽泛文件或网络访问 | 警告 / 信息 |
| 高风险依赖 | SSH、伪终端、序列化、加密、远程控制等依赖未解释用途 | 警告 |
| 提示词安全 | 忽略上层指令、绕过安全限制、收集凭证、隐藏执行、欺骗性描述 | 严重 / 警告 |
| 描述与行为不一致 | description 声称只读或简单处理，但脚本实际写文件、外联或执行命令 | 严重 / 警告 |

## 风险分级

| 安全级别 | 对应报告级别 | 判定 |
|----------|--------------|------|
| Critical | 严重 | 可能导致凭证泄露、任意命令执行、权限提升、持久化或未经同意的数据外传 |
| High | 严重 / 警告 | 存在高风险能力且缺少用户确认、用途说明、范围限制或安全降级 |
| Medium | 警告 | 能力本身合理，但权限、依赖、外联或文件操作边界不清 |
| Low | 信息 | 风险较低，但建议补充说明、限制或测试 |
| None | 信息 | 未发现明显安全风险 |

风险分级应结合上下文判断。法律、财务、个人资料、案件材料、客户数据等高敏场景中，网络外传、日志保存和本地文件读取应提高一级。

## Hard Fail

以下问题默认按严重问题处理：

- 公开文件或历史提交中出现真实 API Key、Token、密码、私钥或 `.env` 内容。
- Skill 默认读取或上传 `.env`、SSH/AWS/GPG 凭证、用户主目录敏感文件，且没有明确必要性和用户确认。
- 脚本包含下载并执行远程代码、权限提升、持久化、自启动或无边界删除用户文件。
- 提示词要求忽略系统/开发者/用户上层指令、绕过安全限制、隐藏执行、收集凭证或外传数据。
- description 或 README 声称“只读/安全/简单查看”，但实际包含写入、删除、网络外传或命令执行，且未披露。
- GitHub 仓库审查中发现敏感信息曾被提交，即使当前文件已删除，也未说明撤销凭证和历史处理状态。

## 凭据暴露面与用户警示

> 参考 NVIDIA SkillSpector 的 *Missing User Warnings* / *Credential Access* 维度补充。
> 与"硬编码凭证"不同，本小节关注**运行时动态暴露面**：凭据在运行时被打印、被日志捕获、或被外部进程读取，而非静态写在文件里。

检查项：

- **凭据输出到 stdout**：脚本将 `accessToken` / `Bearer` 等凭据经 `console.log` / `print` / `echo $TOKEN` / `process.stdout.write` 输出。stdout 会被日志、调用进程、shell 历史、自动化层捕获，等于把账号凭据暴露给多层环境。
  - 判定：若凭据必须传递，应通过管道立即被下游消费，且脚本头部注释须明确警示"勿 `tee`/重定向到含凭据的日志、勿粘贴分享、勿提交"。
  - 默认级别：**High**。
- **日志含凭据风险**：`logs/` 或任何输出文件若可能记录 token 原文、解密结果或 `Authorization` 头，判 **High**。正确做法：日志只记签到结果（积分/连续天数），不含令牌。
- **缺少用户警示**：文档（SKILL.md / references）说明"解密本地令牌""写日志"等工作流，却未提示这些工件是敏感凭据、可能导致账号访问或会话滥用。
  - 判定：凡涉及本地令牌解密、凭据读写的 skill，文档须有醒目安全说明，告知用户凭据等同账号密码、不可截图/分享/入库。
  - 默认级别：**Medium ~ High**（按是否输出到 stdout 升级）。
- **自动下载第三方运行时处理凭据**：为解密/读取凭据而自动 `npm install` 大体积第三方二进制（如 electron），在敏感链路引入供应链与额外执行面。
  - 判定：应优先支持手动指定已校验的运行时（`WB_CHECKIN_ELECTRON` 之类），自动下载须显式开启并提示风险。
  - 默认级别：**Medium**。
- **回退调用外部解释器**：为读会话库回退调用 `python3` 等外部解释器，扩大本地信任边界。
  - 判定：默认应禁用回退，仅在用户显式设开关时启用，并在注释写明风险。
  - 默认级别：**Medium**。

修正方式：凭据输出加 stderr 安全提示（不污染 stdout 管道）；日志过滤令牌；文档补"为何需要这些能力 + 凭据安全警示"；自动安装改为默认关闭或手动优先。

## 权限与能力声明

> 参考 NVIDIA SkillSpector 的 *MCP Least Privilege* / *Excessive Agency* 维度补充。
> 核心：Skill 要求本地代码执行、定时任务、环境变量读取、访问用户目录会话库等能力时，必须在文档显式声明所需权限边界，否则构成透明度与同意缺口。

检查项：

- **声明位置**：`SKILL.md` 须有"所需权限 / 能力声明 / 权限边界"类段落，列出 skill 实际需要的本地能力（代码执行、文件读、网络仅访问特定域名、定时等）。
- **声明与能力对应**：声明内容应覆盖脚本真实用到的能力信号：
  - 本地代码执行：`.sh` / `.ps1` / `child_process` / `subprocess` / `execFileSync`
  - 定时任务：`crontab` / `launchctl load` / `LaunchAgents` / `ScheduledTask` / `schtasks`
  - 环境变量读取：`process.env[` / `os.environ` / `WB_CHECKIN_*`
  - 本地会话库访问：`state.vscdb` / `ItemTable` / `globalStorage`
- **判定**：脚本用到上述任一能力但文档无对应声明 → 默认级别 **Medium**（透明度缺口）；若同时输出凭据到 stdout，叠加升级。
- **最小权限原则**：声明应写明网络仅访问官方域名、令牌仅内存使用不落盘、不访问其他用户数据。

修正方式：在 `SKILL.md` 顶部或「安全说明」节新增"所需权限"清单，逐项对应脚本真实能力。

## 描述-能力上下文匹配

> 参考 NVIDIA SkillSpector 的 *Context-Inappropriate Capability* 维度补充。
> 核心：Skill 自述轻量/简单（如"每日签到""积分"），却包含自动安装第三方二进制、调用额外解释器处理凭据等重型链路时，能力超出描述语境，需声明必要性或默认关闭。

检查项：

- **轻量描述信号**：description / 正文含"签到 / check-in / 简单 / 每日 / 积分 / credits"等轻量语义。
- **重型能力信号**：脚本自动 `npm install electron`、回退 `execFileSync("python3", ...)`、下载并执行第三方运行时。
- **判定**：轻量描述 + 重型凭据处理链路同时存在，且文档未解释必要性 → 默认级别 **Medium**。
  - 应在文档显式说明"为何需要 Electron / python3 回退"（解密本地令牌所必需、全本机运行），或将自动行为改为默认关闭、需显式开启。
- **与 Hard Fail 的关系**：若描述是"只读/安全/简单查看"却含写入/外传/命令执行且未披露，仍按 Hard Fail 处理（见上节）；本小节针对"轻量但必要"的灰色地带，强调声明与上下文自洽。

修正方式：在文档加"为何需要这些能力"小节，把重型链路讲清楚；或把自动安装/回退改为需用户确认/显式开关。

## 自更新、持久化与外传透明度

> 参考 NVIDIA SkillSpector 的 *MCP Tool Poisoning* / *Missing User Warnings* / *Context-Inappropriate Capability* 维度补充。
> 核心：检索类、综合类 Skill 往往**功能必需**地外传查询、落盘归档、提供多领域接口——这些能力本身合规。审计的真正抓手是**透明度**：用户是否被告知会发生什么、能否控制。本小节只查"说清没有"，不查"做了没有"。

检查项：

- **自更新 / 远程代码拉取**：文档或 `SKILL.md` 描述从 GitHub / `raw.githubusercontent.com` 等远程自动下载并替换本地代码（`do-update` / `check-update` / "自更新机制"）。
  - 这是供应链高危项：上游、manifest 或传输链路被篡改可拉取攻击者控制的代码。
  - 默认级别 **High**；若文档已明确"已移除 / 不执行自动更新 / 改由 git pull 等外部通道"则**不报**。
  - 历史记录文档（CHANGELOG / DECISIONS）中的功能变迁叙述不参与判定，避免"已移除"记录被误报。
- **静默持久化**：脚本自动 `write_text` / `open(..., 'w')` / `mkdir` 落盘归档或报告，但 `SKILL.md` 未明示"会写文件及其路径"。
  - 默认级别 **Medium**；若已明示但**未提供关闭开关**（如 `--no-report` / `--no-cwd-report`）则降为 **Low**。
  - 法律检索场景尤其敏感：落盘可能含案由、当事人、裁判文书正文，静默写入用户工作目录有泄露风险。
- **外传敏感文本无隐私警示**：脚本向外部平台 `requests.post` / `api_post` / `fetch` 发送用户查询或待检测文本，但 `SKILL.md` 未给脱敏 / 隐私 / "勿提交含客户信息"的提示。
  - 默认级别 **Medium**；检索类 Skill 提交案卷事实、合同、客户数据极常见，缺警示时外泄风险高。
- **判定原则**：本小节所有项均为"透明度缺口"，**不意味着功能违规**。外传检索、归档落盘、多领域接口对综合检索 Skill 是必要能力，补齐文档声明与开关即可合规。

修正方式：在 `SKILL.md` 顶部加「数据留存与隐私警示」「所需权限」两节，明示本地写盘路径与关闭开关、外部传输目的域名、敏感内容最小化建议；自更新能力若已删除，在文档明确"不执行自动更新"。

## 允许但需说明的能力

以下能力不自动判错，但必须在 `SKILL.md` 或相关 reference 中解释用途、输入边界、用户确认点和失败处理：

- 调用 `subprocess`、`ffmpeg`、OCR、转换器、浏览器自动化等外部工具。
- 访问用户指定文件、读取项目目录、生成或覆盖输出文件。
- 调用公开 API、上传用户明确指定的文件、同步到用户指定服务。
- 使用 MCP、数据库、浏览器、云服务、GitHub、飞书等外部系统。
- 需要 API Key 或 Token 的功能。

## 审查方法

1. 先按 `repository-skill-discovery-standards.md` 定位最小 Skill 单元。
2. 对纳入审查的每个单元列出脚本、配置、依赖、MCP、网络和文件操作入口。
3. 静态搜索危险模式，但不要只靠关键词；结合功能语义判断是否属于合理用途。
4. 对命中项记录文件、行号、类别、风险级别和上下文。
5. 检查 `description`、正文说明和脚本行为是否一致。
6. 对需要密钥、网络、删除、覆盖、外部命令的能力，检查是否有用户确认、范围限制和清晰失败提示。
7. 对 GitHub 仓库，辅助查看提交历史中是否有敏感信息泄露、异常删除重加、版本跳变或异常高频自动提交。

## 误报处理

安全审查允许标记误报，但必须写明理由：

- 例如 `subprocess.run(["ffmpeg", ...])` 只处理用户指定文件，命令参数不拼接未验证输入，可降为警告或信息。
- 例如 `requests.get` 只访问公开文档 URL，且不会上传用户数据，可降为信息。
- 例如 `.env.example` 只包含变量名和占位符，不属于泄露。

不要因为“工具类 Skill 必然要执行脚本”就跳过安全评估；也不要把所有脚本能力一律判为严重问题。

## 修正建议模板

发现安全风险时，报告应给出可执行修正方式：

- 删除硬编码凭证，改为环境变量或本地配置，并轮换已泄露凭证。
- 将真实 endpoint 改为占位符或用户配置项。
- 为删除、覆盖、上传、执行命令增加用户确认和路径限制。
- 避免 shell 字符串拼接，改用参数数组和白名单。
- 为外部网络请求说明目标、发送数据类型、失败处理和关闭方式。
- 删除安装钩子或改为用户显式运行的脚本。
- 为 MCP / 外部工具权限补充最小权限说明。
- 对历史泄露，记录撤销凭证、清理历史或风险告知状态。

## 报告输出

正式质量意见报告应包含“安全评估”维度，并在严重/警告问题中使用本模块作为依据：

```markdown
- 位置: `scripts/example.py:42`
- 所属模块: `security-assessment-standards.md`
- 风险类别: 数据外传 / 硬编码凭证 / 命令执行
- 安全级别: Critical / High / Medium / Low / None
- 问题说明: ...
- 影响: ...
- 修正方式: ...
- 复查标准: ...
```

## 设计理念（为什么这样要求）

安全类问题在报告里天然要讲清"影响"，但其背后的设计原理也值得点透，可直接引用以下表述。

- **正文/frontmatter 进系统提示，是提示词注入面**：SKILL.md 与 frontmatter 的内容会被注入系统提示，"忽略上层指令""绕过安全限制""隐藏执行""收集凭证"这类表述不是普通措辞问题，而是直接的指令注入载体——模型会把它们当成系统级指令执行。对应"提示词安全""描述与行为不一致"。
  - 报告话术：「正文或 frontmatter 含"忽略上层指令/隐藏执行"类表述——这些内容进系统提示后会被当作系统级指令，属于提示词注入，必须删除而非仅改写。」
