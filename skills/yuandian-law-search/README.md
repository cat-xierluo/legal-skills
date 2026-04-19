# 元典法条与案例检索 (yuandian-law-search)

通过 [元典开放平台](https://open.chineselaw.com) 检索中国法律法规条文和案例，为法律分析和研究提供数据支撑。

## 快速开始

### 1. 获取 API Key

访问 [open.chineselaw.com](https://open.chineselaw.com)，用手机号注册后在个人中心创建 API Key。每次调用消耗 10 积分，需在平台充值。

### 2. 配置密钥

将 API Key 填入 `scripts/.env`：

```
YD_API_KEY=sk-你的密钥
```

### 3. 执行检索

```bash
python3 scripts/yd_search.py search "正当防卫的限度" --sxx 现行有效
```

## 设计理念：为什么这样设计这个 Skill

### 背景

元典开放平台提供 11 个 API 端点，覆盖法条、案例、法规、企业四个领域。**每次 API 调用消耗 10 积分**，这意味着一个"检索 5 个案例并逐一查看详情"的简单场景，实际消耗为 10 + 5×10 = 60 积分。

因此，整个 Skill 的设计围绕一个核心问题：**如何在保证正确性的前提下，用最少的 API 调用完成任务？**

### 原则一：正确性优先于积分节约

AI 的记忆可能存在幻觉或过时。涉及法律条文的精确引用时，宁可多查一次，不可引用错误法条。

**必须调用 API 的情况：**
- 需要引用具体法条文号（AI 可能记错条文内容或条号对应）
- 需要确认时效性（法律修订频繁，AI 训练数据可能已过时）
- 用户明确要求检索
- AI 对自身记忆不确定

**可以不调用的情况：**
- 纯概念解释（如"什么是善意取得"）
- 对话中已检索过相同内容
- 用户未要求查找

### 原则二：三级接口分层

不是所有接口都应该被同等对待。我们将 11 个端点分为三层：

| 层级 | 接口 | 设计意图 |
|------|------|----------|
| **核心层**（5 个） | `search` · `keyword` · `detail` · `case` · `case-semantic` | 覆盖 90% 的日常法律检索需求，默认直接使用 |
| **扩展层**（4 个） | `regulation` · `regulation-detail` · `case-detail` · `case --authority-only` | 非日常需求，调用前需告知用户额外积分消耗 |
| **附属层**（2 个） | `enterprise` · `enterprise-detail` | 仅在用户明确要求企业信息时才使用 |

这样设计是因为：法条语义检索（`search`）返回结果已包含法条全文，通常一次调用即可满足需求，无需再调 `detail`；而案例详情（`case-detail`）是额外消耗，必须让用户知情。

### 原则三：语义检索优先

每个领域提供语义和关键词两种检索模式，默认优先使用语义检索：

| 模式 | 适用场景 | 典型返回量 |
|------|----------|-----------|
| **语义检索**（`search` / `case-semantic`） | 自然语言问题，不确定用什么关键词 | 45 条 |
| **关键词检索**（`keyword` / `case`） | 明确关键词 + 需要精确筛选条件 | 10 条 |

语义检索覆盖面更广，一次调用往往足够。只有当用户提供了明确关键词或需要日期/法院/级别等筛选条件时，才切换到关键词检索。

### 原则四：本地缓存零成本

脚本内置归档缓存机制：每次 API 调用的查询和响应会自动存入 `archive/` 目录，以 SHA-256 指纹匹配。相同查询自动命中缓存，**不消耗积分**。

这意味着在同一个对话中多次讨论同一个法律问题时，只有第一次会产生积分消耗。

### 六条积分节省策略

这些策略写入了 SKILL.md，指导 AI 代理在调用时做出正确判断：

1. **一查多用** — 一次检索结果充分引用，避免重复检索同一问题
2. **优先语义检索** — `search` 返回最全面的结果，一次通常够用
3. **避免法条链式调用** — 不要先 `search` 再逐条 `detail`，语义检索已含全文
4. **案例详情谨慎调用** — 先用摘要筛选 1-2 个最相关案例，再调 `case-detail`
5. **善用筛选参数** — `--sxx 现行有效`、`--effect1 法律` 等缩小范围，避免无效结果
6. **信任归档缓存** — 相同查询自动命中本地归档，零积分消耗

## 接口概览

| 命令 | 用途 | 端点 | 层级 |
|------|------|------|------|
| `search` | 法条语义检索 | `/open/law_vector_search` | 核心 |
| `keyword` | 法条关键词检索 | `/open/rh_ft_search` | 核心 |
| `detail` | 法条详情 | `/open/rh_ft_detail` | 核心 |
| `case` | 案例关键词检索 | `/open/rh_ptal_search` | 核心 |
| `case --authority-only` | 权威案例检索 | `/open/rh_qwal_search` | 扩展 |
| `case-semantic` | 案例语义检索 | `/open/case_vector_search` | 核心 |
| `case-detail` | 案例详情 | `/open/rh_case_details` | 扩展 |
| `regulation` | 法规关键词检索 | `/open/rh_fg_search` | 扩展 |
| `regulation-detail` | 法规详情 | `/open/rh_fg_detail` | 扩展 |
| `enterprise` | 企业名称检索 | `/open/rh_company_info` | 附属 |
| `enterprise-detail` | 企业详情 | `/open/rh_company_detail` | 附属 |

每个端点的完整参数说明和响应结构见 `references/01~11-*.md`。

## 版本演进

| 版本 | 日期 | 关键变化 |
|------|------|----------|
| v0.1.0 | 2026-04-03 | 初始版本，封装 5 个 API 端点 |
| v0.2.0 | 2026-04-05 | 改名 `yuandian-law-search`，MIT 许可证，新增注册引导 |
| v1.0.0 | 2026-04-17 | **迁移至开放平台**，新增 6 个端点，引入归档缓存和三级分层 |
| v1.1.0 | 2026-04-17 | 策略抽取至 `references/00-*.md`，核心理念调整为"正确性优先" |

v1.0.0 是最重要的里程碑：API 从旧平台 `aiapi.ailaw.cn:8319` 整体迁移至开放平台 `open.chineselaw.com`，认证方式从 URL 参数改为 `X-API-Key` 请求头，同时新增了法规、案例详情、企业三大领域的端点。

## 自更新机制

Skill 内置了从 GitHub monorepo 自动检测和下载更新的能力，无需手动替换文件。

### 工作方式

1. **自动检测**：每次执行检索命令时，脚本会检查距上次版本检测是否超过 7 天。若超过，从 GitHub 读取远程 `SKILL.md` 的版本号，与本地对比
2. **版本比对**：基于语义版本号（semver）比较，远程版本更高时打印更新提示
3. **手动检查**：可随时执行 `python3 scripts/yd_search.py check-update`，显示当前版本、远程版本和最近提交记录
4. **执行更新**：`python3 scripts/yd_search.py do-update` 从 GitHub 下载 `scripts/MANIFEST.txt` 中列出的所有文件

### 安全边界

`do-update` 的设计遵循一个原则：**只更新 skill 自身的代码和文档，绝不触碰用户数据**。

具体来说：
- 更新范围由 `scripts/MANIFEST.txt` 控制，仅包含 SKILL.md、CHANGELOG.md、脚本和 reference 文档
- **不会覆盖** `.env`（用户的 API Key）和 `archive/`（归档缓存数据）
- 不依赖 GitHub API Token，仅使用公开的 `raw.githubusercontent.com` 和 Atom feed

### 检测状态记录

版本检测结果保存在 `archive/version_check.json`，记录上次检测时间、本地/远程版本号和状态。脚本据此判断是否需要重新检测。

## 许可证

MIT License — 详见 [LICENSE.txt](LICENSE.txt)。

## 作者

杨卫薪律师（微信 ywxlaw）
