# 归属声明与致谢

## 参考项目

本技能（court-sms）在开发过程中，使用 AI 参考了以下开源项目的思路和规则：

### FachuanHybridSystem（法穿AI案件管理系统）

- **项目地址**：https://github.com/Lawyer-ray/FachuanHybridSystem
- **当前许可证**：PolyForm Noncommercial License 1.0.0；2026-11-04 已核对下述固定提交的 `LICENSE` 原文。历史上的许可证切换提交不作为当前许可证依据。
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

6. **一张网下载稳固性策略**（2026-10-27 上游更新）
   - `_zxfw_direct_api_mixin.py`：列表接口 30 秒超时、三次尝试、3 秒/8 秒间隔；业务错误不重试
   - `zxfw_scraper.py`：直接 API 失败后按需创建浏览器上下文，继续 API 拦截与页面点击降级
   - `court_document_service.py`：确认 `getWsListBySdbhNew` 响应可不含 `dt_cjsj`

   本仓库将上述行为改写为标准库脚本与 Agent 操作规则，不复制上游 Python/Django 实现。

7. **当前一张网签收与下载顺序**
   - `_zxfw_direct_api_mixin.py` 的 `_download_via_direct_api` 先调用 `updateSdxxBySdzt`，再调用 `getWsListBySdbhNew`；签收失败仍继续尝试列表。
   - 本 Skill 将签收写入设为明确授权后的可选步骤；签收回执响应不自动转成法律送达日期。

### 本次核对来源

- **法院官网新版核验**：`getSfhyKg/checkSdryxx`、手机号/证件后四位和可选 `mm` 来自2026-11-04法院公开静态资源，法穿当前下载器尚未实现；具体资源与字段见 [律师身份核验](lawyer-identity.md)。
- 截至2026-11-04上游主干固定为 [`ed14bafaf296723ab272f6a35c449573cc81d9e9`](https://github.com/Lawyer-ray/FachuanHybridSystem/commit/ed14bafaf296723ab272f6a35c449573cc81d9e9)（提交日期2026-11-03）。
- [当前直接API流程源码](https://github.com/Lawyer-ray/FachuanHybridSystem/blob/ed14bafaf296723ab272f6a35c449573cc81d9e9/backend/apps/automation/services/scraper/scrapers/court_document/_zxfw_direct_api_mixin.py)。
- [2026-10-27重试与浏览器降级更新](https://github.com/Lawyer-ray/FachuanHybridSystem/commit/6c49aa588a1d477a11dff56ae18d62d6a23fafb1)；次日北京时间的相关更新主要涉及日志整理，不能当成接口替换。
- [当前许可证原文](https://github.com/Lawyer-ray/FachuanHybridSystem/blob/ed14bafaf296723ab272f6a35c449573cc81d9e9/LICENSE)。

### 实现差异

本技能独立实现 Agent 指引、JSON 参考规则与标准库下载器，不移植上游服务代码：

- **原项目**：Python / Django 服务，使用 Ollama LLM + ddddocr + Playwright
- **本技能**：Agent 自然语言解析 + JSON 规则 + 标准库脚本，必要时使用宿主已有浏览器能力
- **参考范围**：公开接口名称、参数、观察到的行为与降级策略；未部署或复制上游 Django 服务

### 致谢

感谢法穿团队开源的法律科技实践成果，为社区提供了宝贵的设计参考。
