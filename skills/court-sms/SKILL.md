---
name: court-sms
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.1.2"
license: MIT
description: 本技能应在用户收到法院短信（文书送达、立案通知、开庭提醒等）时使用，自动提取案号、当事人、下载链接，下载文书并归档到对应案件目录。
---

# 法院短信识别与文书下载

## 功能概述

处理法院短信的完整流程：**粘贴短信 → 解析内容 → 匹配案件 → 下载文书 → 归档保存**。

直接粘贴短信原文即可触发，例如：

```text
收到法院短信，内容如下：
【xx市人民法院】张三，您好！您有（2025）苏0981民初1234号案件文书送达，请点击链接查收：https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=DEMO1&sdbh=DEMO2&sdsin=DEMO3
```

## 短信类型分类

| 类型 | 特征 | 含下载链接 | 处理方式 |
| --- | --- | --- | --- |
| 文书送达 | 含送达平台链接 + 案号 | 是 | 下载文书并归档到案件目录 |
| 立案通知 | 含"已立案"等关键词 | 可能有 | 展示解析结果 |
| 信息通知 | 无链接，纯信息 | 否 | 展示解析结果 |

**支持的送达平台**：`zxfw.court.gov.cn`（全国）、`sd.gdems.com`（广东）、`jysd.10102368.com`（集约送达）。详见 `references/sms-patterns.json`。

---

## 工作流（四步）

### 第一步：短信解析

1. 读取 `references/sms-patterns.json` 作为解析参考
2. 对用户粘贴的短信文本进行分析：

**a) 短信分类**：根据关键词判断类型
- 文书送达：包含 zxfw.court.gov.cn 链接
- 立案通知：包含"已立案"、"立案通知"等
- 信息通知：其他

**b) 案号提取**：使用正则 `[（(〔[]\d{4}[）)〕]]` 匹配标准案号格式

标准案号格式示例：
- `（2025）苏0981民初1234号`
- `(2024)粤0604执保5678号`
- `〔2025〕京0105民初901号`

**c) 当事人提取**：从短信文本初步识别，最终以文书内容为准
- **注意**：短信中的称呼（如"张三，您好"）仅为短信接收人，不作为案件当事人
- 公司名称：`xx有限责任公司`、`xx有限公司`、`xx股份有限公司`
- 诉讼对峙：`A与B`、`A诉B`、`原告A 被告B`
- 角色前缀：`原告：xxx`、`被告：xxx` 等
- 下载文书后，以起诉状、传票中的当事人信息为准，覆盖短信阶段的初步判断

**d) 下载链接提取**：识别短信中的送达平台链接并提取参数

| 平台 | 域名 | 下载方式 | 提取参数 |
|------|------|----------|----------|
| 全国法院统一送达平台 | `zxfw.court.gov.cn` | curl API 直连 | qdbh, sdbh, sdsin |
| 广东法院电子送达 | `sd.gdems.com` | 浏览器自动化 | 路径中的送达标识码 |
| 集约送达平台 | `jysd.10102368.com` | 浏览器自动化 | key |

> **排除列表**：法院名称、法官姓名、地名、法律术语等不应作为当事人提取。详见 `sms-patterns.json` → `party_extraction.exclude_keywords`。

**输出格式**（向用户展示）：

```text
📋 短信解析结果：
- 类型：文书送达
- 案号：（2025）苏0981民初1234号
- 当事人：张三、xx有限公司
- 下载链接：已提取（zxfw.court.gov.cn）
```

### 第二步：确定归档目录

1. **扫描当前工作目录**：识别目录结构，找到与短信案号或当事人匹配的案件目录
2. **查找归档子目录**：在匹配到的案件目录下，查找法院文书相关的子目录（如 `08*`、`法院送达`、`court` 等）
3. 如未找到匹配案件，询问用户选择归档位置或暂存

### 第三步：文书下载

> **平台判断**：根据第一步识别的链接域名，选择下载策略。
> - `zxfw.court.gov.cn` → Tier 1（curl API）→ Tier 2 → Tier 3
> - `sd.gdems.com` 或 `jysd.10102368.com` → 跳过 Tier 1，直接 Tier 2 → Tier 3
> - 未知域名 → 提示用户提供链接信息

#### 依赖

| 依赖 | 用途 | 层级 | 安装方式 |
|------|------|------|----------|
| `curl` | API 下载 | Tier 1 | macOS/Linux 预装 |
| `jq` | JSON 解析（可选） | Tier 1 | `brew install jq` |
| Playwright | 浏览器自动化 | Tier 2/3 | 见下方 |

**Playwright 安装指引**（仅 Tier 2/3 需要）：

```bash
# Tier 2: Playwright CLI
npm install -g playwright
npx playwright install chromium

# Tier 3: Playwright MCP（需在 Claude Code 设置中配置）
# 在 settings.json 的 mcpServers 中添加：
# "playwright": { "command": "npx", "args": ["@anthropic-ai/mcp-playwright"] }
```

> **大多数情况下不需要 Playwright**：zxfw 平台的 Tier 1 方案直接 curl 调用 API，无需浏览器。仅 gdems/jysd 平台或 Tier 1 失败时才需要。

#### Tier 1 — curl API 直连（优先）

完全无头，无需浏览器。直接调用 zxfw 后端 API 获取文书下载链接，再用 curl 下载 PDF。

**API 信息**：

- 端点：`POST https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew`
- Content-Type：`application/json`
- 请求体：`{ "qdbh": "xxx", "sdbh": "xxx", "sdsin": "xxx" }`（从短信 URL 提取）
- 响应字段：`data[].c_wsmc`（文书名称）、`data[].wjlj`（OSS 签名下载链接）、`data[].c_fymc`（法院名称）
- 无需认证、无需浏览器

```bash
# 1. 从短信 URL 提取参数（示例）
qdbh="DEMO_qdbh_value"
sdbh="DEMO_sdbh_value"
sdsin="DEMO_sdsin_value"

# 2. 调用 API 获取文书列表
mkdir -p /tmp/court-sms-staging/
resp=$(curl -s -X POST "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew" \
  -H "Content-Type: application/json" \
  -d "{\"qdbh\":\"$qdbh\",\"sdbh\":\"$sdbh\",\"sdsin\":\"$sdsin\"}")

# 3. 解析文书列表，逐个下载 PDF
echo "$resp" | jq -r '.data[] | "\(.c_wsmc)\t\(.wjlj)"' | while IFS=$'\t' read -r name url; do
  curl -sL -o "/tmp/court-sms-staging/${name}.pdf" "$url"
done

# 4. 验证下载结果
ls -lh /tmp/court-sms-staging/*.pdf
```

#### Tier 2 — Playwright CLI 脚本下载

当 Tier 1 API 不可用或链接过期时，用 Playwright CLI 无头模式打开页面，拦截网络请求获取下载链接。

```bash
# 需要先安装 playwright
npx playwright install chromium 2>/dev/null

# 无头模式运行（脚本需自行编写，拦截 getWsListBySdbhNew API 响应）
node scripts/download_court_docs.mjs --url "{短信链接}" --output /tmp/court-sms-staging/
```

#### Tier 3 — Playwright MCP 交互下载

当 CLI 不可用时（需要已配置 Playwright MCP）：

```text
1. browser_navigate → 打开短信中的 zxfw URL
2. 等待页面加载
3. browser_evaluate → 直接调用 fetch API 获取文书列表
4. browser_run_code → 下载 PDF 文件到 /tmp/court-sms-staging/
```

如 API 调用未成功，改用页面交互：

```text
1. browser_snapshot → 查看当前页面结构
2. 找到文书列表或 PDF 预览区域
3. 定位下载按钮（可能在 iframe 内）
4. browser_click → 点击下载
5. 等待下载完成，保存到临时目录
```

#### 失败兜底

当三级均失败时：

```text
⚠️ 自动下载失败，请手动访问以下链接下载：
{原始链接}

下载后请将文件放到对应案件目录中。

我将为您创建待处理记录。
```

### 第四步：归档保存

1. **确定目标目录**：根据当前项目环境自动判断，不询问用户
   - 扫描当前项目目录，匹配与案号或当事人相关的案件目录
   - 如找到匹配案件目录，查找法院文书子目录（如 `08*`、`法院送达`、`court` 等）
   - **如未找到匹配案件，自动在当前项目下新建**：`{案号} {当事人与案由}/08 - 🏛️ 法院送达/`
   - 如目标子目录不存在，自动创建
2. **获取当前日期**：`date "+%Y%m%d"`
3. **确定文书标题**：
   - 优先使用 API 返回的标题
   - 否则根据 `sms-patterns.json` 中的 `document_titles` 映射推断
   - 最后回退到 `未知文书`
4. **构建文件名**：`{title}（{case_name}）_{YYYYMMDD}收.pdf`
   - 示例：`受理通知书（张三与李四合同纠纷）_20260404收.pdf`
   - 清理非法字符：`< > : " | ? * \ /`
   - 如同名文件已存在，追加 `_2` 后缀
5. **移入目标目录**
6. **写入内部记录**：保存本次处理的完整信息到 `archive/` 目录（格式详见 [`references/archive-format.md`](references/archive-format.md)）
7. **基础文书解析**：法院 PDF 通常带文字层，提取首页文本，快速识别文书类型和关键信息
   - **传票**：提取开庭时间、地点、法庭、案号，向用户高亮提醒
   - **通知书/告知书**：提取缴费期限、举证期限等关键日期
   - **起诉状/答辩状**：提取案由、当事人、诉讼请求概要
   - **其他文书**：展示文书标题和法院名称
   - 如一次下载多份文书，逐一解析，汇总为一份报告

   > 深度分析（如判决书解读、合同审查）不在此技能范围内，请使用专用分析技能处理。

8. **向用户汇报**：按 [`references/report-format.md`](references/report-format.md) 输出结构化报告
   - 先确认归档完成（案号、法院、当事人、案由、文件数、位置）
   - 列出所有已归档的文书清单
   - 如含传票，⚠️ 高亮提醒开庭时间、地点、审理程序
   - 如部分失败，列出失败文书和原始链接

---

## 内部归档格式

每次处理完成后在 `archive/` 下创建 JSON 记录，格式详见 [`references/archive-format.md`](references/archive-format.md)。

---

## 常见法院短信格式参考

### 文书送达短信

```text
【xx市人民法院】张三，您好！您有（2025）苏0981民初1234号案件文书送达，
请点击链接查收：
https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=DEMO1&sdbh=DEMO2&sdsin=DEMO3
如非本人操作请联系法院。
```

### 立案通知短信

```text
【xx市xx区人民法院】您好，您提交的立案材料已审核通过。
案号：（2025）京0105民初54321号
请及时缴纳诉讼费用。
```

### 开庭提醒短信

```text
【xx市xx区人民法院】提醒：您有（2025）苏0508民初567号案件，
定于2025年3月15日上午9:30在第3法庭开庭，请准时到庭。
```

---

## 故障排除

| 问题 | 解决方案 |
| --- | --- |
| 短信无法识别类型 | 展示原文，请用户确认类型后继续 |
| 案号提取失败 | 手动输入案号 |
| 当事人识别不准 | 提示用户确认/修正当事人列表 |
| 无匹配案件 | 提供三个选项：选已有/新建/暂存 |
| Playwright 下载超时 | 检查网络连接，尝试刷新页面重试 |
| 页面需要验证码 | 通知用户，暂停等待手动处理 |
| 下载文件损坏 | 清理临时目录，重新尝试下载 |
| 目标目录不存在 | 自动创建对应目录 |

---

## 配置

无额外配置需求。解析规则参考 `references/sms-patterns.json`。

如需修改解析规则（添加新文书标题、调整正则等），编辑该 JSON 文件即可。

---

## 🔄 变更历史

完整变更日志见 [CHANGELOG.md](CHANGELOG.md)。归属声明见 [references/ATTRIBUTION.md](references/ATTRIBUTION.md)。
