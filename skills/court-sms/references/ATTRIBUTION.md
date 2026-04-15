# 归属声明与致谢

## 参考项目

本技能（court-sms）在开发过程中，使用 AI 参考了以下开源项目的思路和规则：

### FachuanHybridSystem（法穿AI案件管理系统）

- **项目地址**：https://github.com/Lawyer-ray/FachuanHybridSystem
- **许可证**：PolyForm Noncommercial License 1.0.0 (附特别许可)
- **版权所有**：(C) 2025-2099 法穿

### 具体参考内容

本技能参考了 FachuanHybridSystem 中以下模块的**设计思路和解析规则**（非直接复制代码）：

1. **短信解析服务** (`backend/apps/automation/services/sms/sms_parser_service.py`)
   - 短信类型分类逻辑（文书送达 / 信息通知 / 立案通知）
   - zxfw.court.gov.cn 下载链接正则匹配规则
   - 同构异域名正则更新（从硬编码域名改为通用主机匹配，通过 URL 路径特征识别平台）
   - 案号提取正则模式
   - 当事人名称提取策略（公司名模式、对峙模式、角色前缀模式）
   - 当事人排除关键词列表
   - 司法送达网（SFDW）链接正则和验证码提取规则

2. **案件匹配算法** (`backend/apps/automation/services/sms/case_matcher.py`)
   - 三级匹配策略的设计思路（案号精确 → 当事人双向 → 特征筛选）

3. **文书重命名逻辑** (`backend/apps/automation/services/sms/document_renamer.py`)
   - 已知文书标题映射表
   - 文件命名格式：`{title}（{case_name}）_{YYYYMMDD}收.pdf`

4. **zxfw 下载策略** (`backend/apps/automation/services/scraper/scrapers/court_document/zxfw_scraper.py`)
   - 多级下载回退策略的架构设计
   - API 拦截与页面操作结合的思路

5. **司法送达网下载策略** (`backend/apps/automation/services/scraper/scrapers/court_document/sfdw_scraper.py`)
   - 纯 Playwright 下载流程（TDHCryptoUtil 加密导致无法使用 HTTP API）
   - 验证码双模式策略：手机尾号后6位优先 + 短信验证码回退
   - Vue app.checkYzm() → wsList → downloadFile() 页面交互流程

### 实现差异

本技能并未直接复制 FachuanHybridSystem 的代码，而是将其核心逻辑重新实现为 Claude Code Skill 格式：

- **原项目**：Python / Django 服务，使用 Ollama LLM + ddddocr + Playwright
- **本技能**：Claude Code Skill，利用 Claude NLP 能力 + Playwright MCP
- **无代码复用**：所有解析逻辑由 Claude 自然语言理解完成，配置规则以 JSON 参考

### 致谢

感谢法穿团队开源的法律科技实践成果，为社区提供了宝贵的设计参考。
