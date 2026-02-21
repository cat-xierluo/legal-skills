# 变更日志

## [0.7.0] - 2026-02-21

### 新增功能

- **配置文件支持**: 支持通过 YAML 配置文件自定义输出目录和其他设置
  - 新增 `assets/config.example.yaml` 示例配置文件
  - 支持 `output_dir` 自定义输出目录
  - 支持 `~` 展开、相对路径、绝对路径
  - 配置文件不存在或 `output_dir` 为空时使用默认值 `./research`

### 改进优化

- SKILL.md 添加"配置"章节，说明配置文件使用方法
- 工作流程 Step 1 增加配置读取逻辑
- 报告和目录结构支持自定义输出位置

### 文件变更

- 新增: `assets/config.example.yaml` - 配置文件示例
- 更新: `SKILL.md` - 添加配置章节和工作流程更新

---

## [0.6.0] - 2026-02-21

### 新增功能

- **提示词安全检测**: 专门针对 SKILL.md 和 Markdown 文件的安全分析
  - 检测 9 类提示词安全风险
  - **提示注入**: ignore instructions、DAN mode、jailbreak 等越狱尝试
  - **数据收集指令**: collect password、send to external、exfiltrate 等
  - **执行指令**: execute shell、download and run 等隐藏执行逻辑
  - **权限提升指令**: run with sudo、grant root access 等
  - **欺骗性描述**: harmless tool、for educational only 等可疑描述
  - **网络通信指令**: phone home、reverse shell、beacon 等外泄指令
  - **持久化指令**: cron job、startup、auto-run 等驻留机制
  - **隐藏指令**: 控制字符、Unicode 转义、零宽字符等
  - **社会工程学**: urgent update、verify account 等欺骗模式

### 改进优化

- 报告模板增加"提示词安全分析"章节
- 提示词发现与代码发现统一汇总到风险等级计算
- 所有 Markdown 文件均纳入提示词安全扫描范围

### 文件变更

- 更新: `scripts/security.py` - 添加 `PROMPT_SECURITY_PATTERNS` 和 `_analyze_prompt_security()` 方法
- 更新: `SKILL.md` - 添加提示词安全检测说明
- 更新: `CHANGELOG.md` - 记录 v0.6.0 变更

### 提示词安全检测能力

| 类别 | 检测内容 | 风险等级 |
|:-----|:---------|:---------|
| 提示注入 | ignore instructions、override、jailbreak、DAN mode | 🔴 critical |
| 数据收集指令 | collect password、send to external、exfiltrate data | 🔴 critical |
| 执行指令 | execute shell、download and run、spawn process | 🟠 high |
| 权限提升指令 | run with sudo、grant root、disable security | 🟠 high |
| 网络通信指令 | phone home、reverse shell、beacon、connect to server | 🟠 high |
| 持久化指令 | cron job、startup、auto-run、modify rc files | 🟠 high |
| 欺骗性描述 | harmless tool、educational only、hidden feature | 🟡 medium |
| 隐藏指令 | 控制字符、Unicode 转义、零宽字符 | 🟡 medium |
| 社会工程学 | urgent update、verify account、trust me | 🟡 medium |

---

## [0.5.0] - 2026-02-21

### 新增功能

- **安全分析模块**: 基于 OWASP Agentic AI Top 10 和常见漏洞模式设计
  - 新增 `scripts/security.py` 模块（约 700 行）
  - 检测 15+ 类安全风险：命令执行、敏感文件访问、网络外泄、代码混淆、权限提升、硬编码凭证、下载执行、持久化机制等
  - 识别 Skill 特有风险：安装钩子、MCP 服务器风险
  - 支持 4 级风险等级：critical / high / medium / low
  - 生成结构化安全分析报告

### 改进优化

- **报告命名格式优化**: 从 `REPORT.md` 改为 `YYYYMMDD-topic-slug-report.md`
  - 报告文件与目录同级，便于查找和管理
  - 示例：`20260221-douyin-batch-download-report.md`
- 更新报告模板，添加"安全评估"章节
- 报告中显示总体风险等级和安全建议

### 文件变更

- 新增: `scripts/security.py` - 安全分析核心模块
- 更新: `scripts/__init__.py` - 导出 SecurityAnalyzer
- 更新: `SKILL.md` - 添加安全分析文档 + 报告命名格式调整
- 更新: `assets/report-template.md` - 添加安全评估章节

### 安全检测能力

| 类别 | 检测内容 | 风险等级 |
|:-----|:---------|:---------|
| 命令执行 | `os.system`, `subprocess`, `eval()`, `exec()` | 🔴 高 |
| 敏感文件访问 | `~/.ssh/`, `~/.aws/`, `.env`, `.pem`, `.key` | 🔴 高 |
| 网络外泄 | HTTP POST、WebSocket、数据上传 | 🟡 中 |
| 代码混淆 | `base64`, `chr()` 拼接、hex escape | 🔴 高 |
| 权限提升 | `sudo`, `chmod 777`, `setuid` | 🔴 高 |
| 硬编码凭证 | API Key、Token、AWS/GitHub 凭证 | 🔴 高 |
| 下载执行 | `curl | bash`, `wget | sh` 模式 | 🔴 高 |
| Skill 特有 | 安装钩子、MCP 服务器风险 | 🟡 中 |

---

## [0.4.0] - 2026-02-14

### 新增功能

借鉴 Zread MCP 实现思路，增强本地分析能力：

- **代码语义搜索**: 支持搜索函数、类、导入、文档等多种模式
  - 新增 `scripts/search.py` 模块
  - 支持 Python, JavaScript, TypeScript, Go, Rust, Java
  - 使用 Grep 工具进行模式匹配

- **深度代码分析**: 超越基础分析，提供架构和质量层面的深度洞察
  - 新增 `scripts/analyzer/` 模块
  - **架构分析**: 目录结构、模块划分、入口文件、架构模式检测（MVC、微服务、插件、monorepo）
  - **质量分析**: 代码统计、注释覆盖率、技术债务检测（TODO、FIXME）、问题检测（硬编码密钥、console.log）

- **智能问答**: 利用 Claude Code 的 LLM 能力，回答关于仓库的自然语言问题
  - 新增 `scripts/qa.py` 模块
  - 问题意图分类: overview, architecture, usage, api, dependencies
  - 结构化回答模板

### 改进优化

- 更新 SKILL.md，添加高级功能章节
- 文档完善：详细说明各功能的使用方法和触发条件

### 文件变更

- 新增: `scripts/__init__.py`
- 新增: `scripts/search.py`
- 新增: `scripts/qa.py`
- 新增: `scripts/analyzer/__init__.py`
- 新增: `scripts/analyzer/architecture.py`
- 新增: `scripts/analyzer/quality.py`
- 更新: `SKILL.md`

---

## [0.3.0] - 2026-02-11

### 新增功能

- 主题驱动搜索研究模式：支持用户提供主题关键词，自动使用 find-skills 搜索相关 GitHub 仓库
- 依赖管理章节：说明核心功能无需前置技能，find-skills 仅在主题搜索模式下可选使用
- 新增主题研究报告模板：`assets/topic-research-template.md`

### 改进优化

- 更新模式选择表格，添加主题驱动搜索研究模式（第 4 种模式）
- 完善触发条件说明，包含主题搜索相关触发场景
- 添加主题研究模式的完整工作流程（Step 0-6）：依赖检查、搜索、筛选、克隆、分析、报告

### 文档完善

- 更新 Resources 章节，添加新模板文件引用
- 创建配套文档：DECISIONS.md、TASKS.md、LICENSE.txt
- 记录 3 个重要技术决策：主题搜索模式设计、目录结构设计、报告模板设计原则

---

## [0.2.0] - 2026-02-10

### 新增功能

- 对比启发模式：支持外部仓库与本地项目进行对比分析
- 启发式分析框架：差异分析框架 + 启发式问题清单
- 本地项目识别：自动识别常见本地项目类型（技能目录、测试项目等）

### 改进优化

- 扩展模式选择表格，添加对比启发模式（第 3 种模式）
- 新增多仓库对比报告模板：`assets/comparison-template.md`
- 完善报告结构，添加"对比分析"和"具体启发"章节

### 文档完善

- 添加对比启发模式的完整工作流程（Step 4）
- 定义启发式问题清单：功能、架构、实现、文档 4 个维度

---

## [0.1.0] - 2026-02-09

### 新增功能

- 基础研究框架：支持单个和多个 GitHub 仓库的深度研究
- 两种研究模式：
  - 单仓库深度研究：全面分析单个仓库的架构、功能、代码质量
  - 多仓库对比研究：对比多个仓库的共性、差异、优劣
- 基础分析流程：项目类型识别、核心文件阅读、项目结构分析、技术栈识别
- 单仓库报告模板：`assets/report-template.md`

### 功能特性

- 智能克隆：使用 `--depth 1` 浅克隆，节省时间和空间
- 目录结构设计：`research/YYYYMMDD/{repo-name|comparison}/` 模式化组织
- 项目类型识别：自动识别 Node.js、Python、Go、Rust、Claude Skill 等项目类型

### 文档完善

- 定义技能触发条件和使用场景
- 编写完整工作流程文档（Step 1-5）
- 创建报告模板和会话汇报格式
