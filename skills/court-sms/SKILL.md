---
name: court-sms
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.5.0"
license: MIT
description: 本技能应在用户收到法院短信（文书送达、立案通知、开庭提醒等）时使用，自动提取案号、当事人、下载链接，下载文书并归档到对应案件目录。
---

# 法院短信识别与文书下载

## 功能概述

处理法院短信的完整流程：**粘贴短信 → 解析内容 → 匹配案件 → 下载文书 → 归档保存**。

支持两种触发方式：

**方式一：粘贴短信原文**

```text
收到法院短信，内容如下：
【xx市人民法院】张三，您好！您有（2025）苏0981民初1234号案件文书送达，请点击链接查收：https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=DEMO1&sdbh=DEMO2&sdsin=DEMO3
```

**方式二：直接发送送达链接**

用户可能直接粘贴送达链接（非完整短信文本），此时跳过短信文本解析，直接从 URL 中提取 `qdbh`、`sdbh`、`sdsin` 参数，进入第三步下载流程。

```text
https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=xxx&sdbh=xxx&sdsin=xxx
```

## 短信类型分类

| 类型 | 特征 | 含下载链接 | 处理方式 |
| --- | --- | --- | --- |
| 文书送达 | 含送达平台链接 + 案号 | 是 | 下载文书并归档到案件目录 |
| 立案通知 | 含"已立案"等关键词 | 可能有 | 展示解析结果 |
| 信息通知 | 无链接，纯信息 | 否 | 展示解析结果 |

**支持的送达平台**：`zxfw.court.gov.cn`（全国）、`sd.gdems.com`（广东）、`jysd.10102368.com`（集约送达）、`dzsd.hbfy.gov.cn`（湖北）、`sfpt.cdfy12368.gov.cn`（司法送达网）。同一平台可能使用不同域名（同构异域名），通过 URL 路径特征识别平台。详见 `references/sms-patterns.json`。

---

## 工作流（四步）

### 第一步：输入解析

1. 读取 `references/sms-patterns.json` 作为解析参考
2. **判断输入类型**：
   - **完整短信**：包含法院签名（如 `【xx法院】`）+ 正文 + 链接 → 完整解析流程
   - **纯链接**：用户直接发送送达 URL（如 `https://zxfw.court.gov.cn/...?qdbh=xxx&sdbh=xxx&sdsin=xxx`）→ 跳过短信文本解析，直接从 URL 提取参数，进入第三步下载。案号、当事人等信息在下载文书后从文书内容中提取。
3. 对用户粘贴的短信文本进行分析（纯链接输入跳过此步）：

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
| 湖北电子送达 | `dzsd.hbfy.gov.cn` | HTTP API（免账号）/ 浏览器自动化（账号模式） | 免账号：msg；账号模式：账号+密码从正文提取 |
| 司法送达网 | `sfpt.cdfy12368.gov.cn` | 纯 Playwright（无 API） | 验证码（手机尾号后6位 / 短信验证码） |

**e) 发送时间提取（P0）**：从送达平台 API 响应中提取发送时间，用于后续上诉期限计算
- **优先来源**：zxfw API 响应中的 `dt_cjsj` 字段（送达记录创建时间，ISO 8601 格式）
- 短信网关时间：部分手机短信会显示发送时间，匹配 `发送：YYYY-MM-DD HH:mm` 格式
- 如果无法提取送达时间，展示"送达时间待确认"，不阻塞后续流程
- 记录到归档 JSON 的 `document.sent_at` 字段

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
3. 如未找到匹配案件，**自动在当前工作目录（项目根目录）下新建** `{案号} {当事人与案由}/`，不询问用户

### 第三步：文书下载

> **平台判断**：根据第一步识别的链接域名，选择下载策略。
> - `zxfw.court.gov.cn` → 方案一（API 直连）→ 方案二 → 方案三
> - `sd.gdems.com` 或 `jysd.10102368.com` → 跳过方案一，直接方案二 → 方案三
> - `dzsd.hbfy.gov.cn` → 湖北专属流程（见下方）
> - `sfpt.cdfy12368.gov.cn`（含广西实例 `171.106.48.55:28083`）→ SFDW 专属流程（见下方）
> - 未知域名但 URL 路径匹配已知平台特征 → 按路径识别平台（同构异域名支持）
> - 完全无法识别 → 提示用户提供链接信息
>
> **⛔ 降级铁律**：严格串行，禁止并行。当前方案成功即停止，绝不降级。禁止"双保险"并行尝试多个方案。

#### 依赖

| 依赖 | 用途 | 适用方案 | 安装方式 |
|------|------|----------|----------|
| `curl` | API 下载 | 方案一 | macOS/Linux 预装 |
| `jq` | JSON 解析（可选） | 方案一 | `brew install jq` |
| Playwright | 浏览器自动化 | 方案二/三 | 见下方 |

**Playwright 安装指引**（仅方案二/三需要）：

```bash
# 方案二: Playwright CLI
npm install -g playwright
npx playwright install chromium

# 方案三: Playwright MCP（需在 Claude Code 设置中配置）
# 在 settings.json 的 mcpServers 中添加：
# "playwright": { "command": "npx", "args": ["@anthropic-ai/mcp-playwright"] }
```

> **⛔ 大多数情况下不需要 Playwright**：zxfw 平台方案一直接 curl 调用 API，无需浏览器。仅 gdems/jysd 平台或**方案一失败后**才需要方案二/三。禁止在方案一执行期间同时打开浏览器。

#### 方案一 — API 直连（优先）

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

#### 方案二 — 无头浏览器（Playwright CLI）

当方案一 API 不可用或链接过期时，用 Playwright CLI 无头模式打开页面，拦截网络请求获取下载链接。

```bash
# 需要先安装 playwright
npx playwright install chromium 2>/dev/null

# 无头模式运行（脚本需自行编写，拦截 getWsListBySdbhNew API 响应）
node scripts/download_court_docs.mjs --url "{短信链接}" --output /tmp/court-sms-staging/
```

#### 方案三 — 交互式浏览器（Playwright MCP）

当方案二不可用时（需要已配置 Playwright MCP）：

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

#### 湖北平台下载流程（`dzsd.hbfy.gov.cn`）

湖北电子送达平台有两种链路，根据 URL 格式自动选择：

**链路一：免账号模式**（URL 含 `/hb/msg=xxx`）

1. 从 URL 提取 `msg` 参数值
2. 尝试 HTTP API 直连：

```bash
msg="从URL提取的msg值"
mkdir -p /tmp/court-sms-staging/

# 查询文书信息
resp=$(curl -s -X POST "http://dzsd.hbfy.gov.cn/delimobile/tDeliSms/findSmsInfo?t=$(date +%s%3N)" \
  -H "Content-Type: application/json" \
  -H "Referer: http://dzsd.hbfy.gov.cn/deli-mobile-ui/" \
  -d "{\"msg\":\"$msg\"}")

# 检查是否需要验证码（data.isNeedCaptcha == "Y"）
# 如需验证码或无可下载文书，降级到 Playwright MCP

# 逐个下载文书
echo "$resp" | jq -r '.data.docList[] | "\(.docName)\t\(.downloadPath)"' | while IFS=$'\t' read -r name path; do
  if [ -n "$path" ]; then
    curl -sL -o "/tmp/court-sms-staging/${name}.pdf" "http://dzsd.hbfy.gov.cn/delimobile${path}"
  fi
done
```

3. 如需验证码或 HTTP 失败，降级到 Playwright MCP（方案三）

**链路二：账号模式**（URL 含 `/sfsddz`）

1. 从短信正文提取凭证：
   - 账号：匹配 `账号\s*(\d{15,20})`
   - 默认密码：匹配 `默认密码[：:]\s*([0-9A-Za-z]+)`
2. 需要浏览器自动化（Playwright MCP），登录页包含验证码
3. 登录后遍历待签收/已签收/已过期文书列表，逐个下载

> **提示**：湖北平台两种模式都可能遇到验证码。免账号模式优先尝试 HTTP API，账号模式建议引导用户手动打开链接或使用 Playwright MCP。

#### 司法送达网下载流程（SFDW - `sfpt.cdfy12368.gov.cn`）

司法送达网所有 POST 请求使用 TDHCryptoUtil 加密，无法通过 HTTP API 下载，只能使用纯 Playwright 流程。

**广西实例**：`171.106.48.55:28083` 域名下的链接路由到同一 SFDW 平台，下载流程相同。

**验证码获取**（两种方式，按优先级尝试）：

1. **手机尾号后6位**（优先）：从案件分配信息中获取律师手机号，取后6位作为验证码输入
2. **短信验证码**：从短信正文中提取，匹配 `验证码[：:]\s*(\w{4,6})`

**Playwright MCP 流程**：

```text
1. browser_navigate → 打开短信中的 SFDW 链接
2. 等待页面自动重定向到 pc.html?tdhParams=xxx
3. browser_snapshot → 查看验证码输入页面（input#checkCode）
4. 输入验证码（优先手机尾号后6位，其次短信验证码）
5. browser_evaluate → 调用 Vue app.checkYzm() 触发验证
6. 验证通过后 browser_evaluate → 获取 app.$data.wsList（文书列表）
7. 遍历 wsList，逐个调用 downloadFile(app, ws) 下载文书
8. 保存到 /tmp/court-sms-staging/
```

> **提示**：如手机尾号验证失败，提示用户查看短信中的验证码并手动输入。wsList 每项包含 wjmc（文件名）、wjgs（格式）。

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
   - 如找到匹配案件目录，优先查找法院文书子目录（如 `08*`、`法院送达`、`court` 等）；如无子目录则直接归档到案件根目录
   - **如未找到匹配案件，自动在当前项目下新建**：`{案号} {当事人与案由}/`
   - 如目标目录不存在，自动创建
2. **获取当前日期**：`date "+%Y%m%d"`
3. **确定文书标题**：
   - 优先使用 API 返回的标题
   - 否则根据 `sms-patterns.json` 中的 `document_titles` 映射推断
   - 最后回退到原始文件名（去除扩展名），如仍无法确定则使用 `未知文书`
4. **构建文件名**：`{title}（{case_name}）_{YYYYMMDD}收.pdf`
   - 示例：`受理通知书（张三与李四合同纠纷）_20260404收.pdf`
   - 清理非法字符：`< > : " | ? * \ /`
   - 如同名文件已存在，追加 `_2` 后缀
5. **移入目标目录**
6. **写入内部记录**：保存本次处理的完整信息到 **skill 内部的 `archive/` 目录**（即 `.claude/skills/court-sms/archive/`），不是案件文件夹。格式详见 [`references/archive-format.md`](references/archive-format.md)
7. **基础文书解析**：法院 PDF 通常带文字层，提取首页文本，快速识别文书类型和关键信息
   - **传票**：提取开庭时间、地点、法庭、案号，向用户高亮提醒
   - **通知书/告知书**：提取缴费期限、举证期限等关键日期
   - **起诉状/答辩状**：提取案由、当事人、诉讼请求概要
   - **判决书**：识别为一审判决书，记录文书类型，触发上诉期限计算（P1）
   - **其他文书**：展示文书标题和法院名称
   - 如一次下载多份文书，逐一解析，汇总为一份报告

   > 深度分析（如判决书解读、合同审查）不在此技能范围内，请使用专用分析技能处理。

8. **上诉期限计算（P1）**：当识别到判决书/裁定书时自动计算
   - **适用条件**：文书类型为判决书/裁定书（包括一审判决书、民事判决书、裁定书等）
   - **不同案件类型的上诉期限**（详见 `sms-patterns.json` → `appeal_calculation`）：
     | 案件类型 | 上诉期限 |
     |---------|---------|
     | 民事一审判决 | 送达后15天 |
     | 民事裁定 | 送达后10天 |
     | 行政判决 | 送达后15天 |
     | 刑事判决 | 送达后10天 |
     | 刑事裁定 | 送达后5天 |
   - **计算公式**：`上诉截止日期 = 送达日期 + 上诉期限天数`
   - **送达日期来源**：
     - 优先使用 zxfw API 响应的 `dt_cjsj` 字段（送达记录创建时间）
     - 次选使用短信接收时间 `received_at`
     - 无法确定时，展示"送达时间待确认"
   - **归档 JSON 字段**：写入 `document.appeal_deadline` 和 `document.appeal_days_remaining`

9. **向用户汇报**：按 [`references/report-format.md`](references/report-format.md) 输出结构化报告
   - 先确认归档完成（案号、法院、当事人、案由、文件数、位置）
   - 列出所有已归档的文书清单
   - 如含传票，⚠️ 高亮提醒开庭时间、地点、审理程序
   - 如含判决书，⏰ 展示上诉期限信息
   - 如部分失败，列出失败文书和原始链接

### 第五步：PDF 后处理（可选）

> **不默认启用**。仅在检测到文件拆分时主动提示用户。

归档完成后，扫描目标目录中的 PDF 文件，检测是否有同一文书被拆分为多个文件的情况。

#### 读取用户偏好

读取 `config/user-preferences.json` 获取用户的合并和重命名偏好。如文件不存在，使用默认值（参考 `config/user-preferences.example.json`）。

关键偏好项：

| 偏好 | 默认值 | 说明 |
|------|--------|------|
| `merge_strategy` | `per_evidence` | 合并策略：`per_evidence`（按编号分别合并）或 `unified`（统一合并） |
| `merge_options.unified.bookmarks.enabled` | `true` | 统一合并时是否添加 PDF 书签 |
| `rename.enabled` | `true` | 是否精简文件名 |

#### 触发检测

读取 `references/sms-patterns.json` → `post_processing.trigger` 配置，按以下规则分组：

```text
分组规则：
1. 证据类：文件名以"证据"开头 → 按编号分组（证据1、证据2、证据3…）
2. 其他文书：按文书类型分组（传票、起诉状、应诉通知书…）
3. 如任一组内文件数 > 3（threshold），触发提示
```

**示例**：证据3 下有 10 个 PDF → 触发。

#### 用户确认

使用 AskUserQuestion 提示用户，列出检测到的拆分情况：

```text
检测到以下文书被拆分为多个 PDF：
- 证据3：10 个文件
- 证据5：4 个文件

是否执行 PDF 后处理（合并 + 重命名）？
  → 是，合并所有
  → 让我选择（逐个确认）
  → 跳过
```

#### 执行后处理

用户确认后，根据 `user-preferences.json` 中的 `merge_strategy` 执行：

**策略一：per_evidence（默认）**

按单个证据编号分别合并，每个证据独立保留：

```text
- 证据3 有 10 个拆分文件 → 合并为「证据3：打印截图.pdf」
- 证据5 有 4 个拆分文件 → 合并为「证据5：电脑截图.pdf」
- 未被拆分的证据（如证据1 只有 1 个文件）保持不动
```

**策略二：unified**

将证据目录 + 所有证据合并为一个「原告证据.pdf」，并添加 PDF 书签：

```text
合并顺序：证据目录 → 证据1 → 证据2 → … → 证据N
书签格式：
  📑 证据目录
  📑 证据1：仲裁申请书、不予受理通知书
  📑 证据2：劳动合同、保密协议
  📑 证据3：被告工资表
  📑 证据4：泄露账号密码的电脑截图
  📑 证据5：打印及拷贝资料的电脑截图
  📑 证据6：删除电脑操作痕迹的截图
```

书签名称使用简洁版：证据编号 + 冒号 + 证据标题（去除当事人和日期后缀）。使用 pypdf 的 `add_outline_item` 添加书签。

> 用户可随时修改 `user-preferences.json` 切换策略，无需改动 skill 本身。

#### 页面尺寸标准化

合并过程中同时标准化页面尺寸为 A4（210×297mm）。使用 pypdf 逐页处理：

```python
from pypdf import PdfReader, PdfWriter, Transformation

A4_W = 595.27  # 210mm in points
A4_H = 841.89  # 297mm in points

for page in reader.pages:
    pw, ph = float(page.mediabox.width), float(page.mediabox.height)
    is_landscape = pw > ph

    # 保持原始方向：纵向→A4纵向，横向→A4横向
    target_w = A4_H if is_landscape else A4_W
    target_h = A4_W if is_landscape else A4_H

    # 等比缩放并居中
    scale = min(target_w / pw, target_h / ph)
    offset_x = (target_w - pw * scale) / 2
    offset_y = (target_h - ph * scale) / 2

    new_page = writer.add_blank_page(width=target_w, height=target_h)
    page.add_transformation(Transformation().scale(scale).translate(offset_x, offset_y))
    new_page.merge_page(page)
```

**规则**：
- 纵向页面 → A4 纵向（210×297mm）
- 横向页面 → A4 横向（297×210mm），不强制旋转为纵向
- 等比缩放、居中放置，不裁剪、不拉伸

#### 精简文件名

根据 `user-preferences.json` → `rename` 配置对所有文件统一重命名：

```text
去除规则（strip_patterns）：
- 去掉括号内的当事人信息：（张三与李四合同纠纷）
- 去掉日期后缀：_20260405收
- 去掉平台标记：（合并）、（自贸法庭）、（素）-

特殊映射（special_mappings）：
- 起诉状（素）… → 起诉状（要素式）.pdf
- 开庭传票 → 传票.pdf
```

**重命名示例**：

| 原始 | 重命名后 |
|------|----------|
| `传票（张三与李四合同纠纷）_20260405收.pdf` | `传票.pdf` |
| `起诉状（合并）.pdf` | `起诉状.pdf` |
| `起诉状（素）-要素式起诉状（合并）.pdf` | `起诉状（要素式）.pdf` |
| `应诉通知书（自贸法庭）.pdf` | `应诉通知书.pdf` |
| `E法桥平台使用告知书（xxx）_20260405收.pdf` | `E法桥平台使用告知书.pdf` |

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

### 湖北电子送达短信（免账号）

```text
【xx人民法院】您有案件文书待查收，请点击链接查收：
http://dzsd.hbfy.gov.cn/hb/msg=XXXXXXX
如有疑问请联系法院。
```

### 湖北电子送达短信（账号模式）

```text
【xx人民法院】您有（2025）鄂xxxx民初xxxx号案件文书送达。
账号 420xxxxxxxxxxxxx
默认密码：xxxxxx
请登录 http://dzsd.hbfy.gov.cn/sfsddz 查收。
```

### 司法送达网短信

```text
【xx人民法院】您有（2025）川xxxx民初xxxx号案件文书送达。
验证码：A1B2C3
请点击链接查收：https://sfpt.cdfy12368.gov.cn/sfsdw//r/xxxxxxxxxxxx
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
| SFDW 验证码验证失败 | 尝试手机尾号后6位和短信验证码两种方式，均失败时提示用户联系法院 |

---

## 配置

无额外配置需求。解析规则参考 `references/sms-patterns.json`。

如需修改解析规则（添加新文书标题、调整正则等），编辑该 JSON 文件即可。

---

## 🔄 变更历史

完整变更日志见 [CHANGELOG.md](CHANGELOG.md)。归属声明见 [references/ATTRIBUTION.md](references/ATTRIBUTION.md)。
