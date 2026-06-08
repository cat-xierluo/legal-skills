---
name: mineru-ocr
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.2.0"
description: 将本地文档、远程文档 URL 或网页 URL 转换为 Markdown。默认使用免登录轻量接口开箱即用；若已配置 MinerU Token，则自动切换到标准 API。保留 archive 回溯能力，并支持 Token 自检与私有部署连接说明。本技能应在用户需要 PDF 转 Markdown、OCR、远程文档转换、网页内容提取、表格识别、公式识别、文档转换、图片转文字、扫描件转换时使用。
license: Complete terms in LICENSE.txt
---
# MinerU PDF 转 Markdown

## 前置配置

> **默认 Auto 模式**：未配置 Token 时，自动使用官方免登录轻量接口；配置 Token 后，自动切换到标准 API。

### 免配置快速使用

- 无需登录、无需创建 `.env`
- 适合快速转换本地小文件或远程文档 URL
- 受官方轻量接口限制影响：按 IP 限频、单文件 10 MB、最多 20 页

### 升级到标准 API（可选）

如遇到以下情况，建议配置 Token：

- 文件超过 10 MB
- 页数超过 20 页
- 轻量接口遇到 IP 限频
- 需要提取网页 URL
- 希望更稳定地使用标准 API 配额

### 申请 API Token

1. 访问 [https://mineru.net/apiManage/token](https://mineru.net/apiManage/token)
2. 注册/登录账号
3. 创建 API Token 并复制（格式：`eyJ0eXAiOiJKV1QiLCJhbGc...`）

### 配置 Token

**方式一：让 AI 配置**

> "帮我配置 MinerU，Token 是：`xxx`"

**方式二：手动配置**

```bash
cd .claude/skills/mineru-ocr/config
cp .env.example .env
nano .env  # 填入 MINERU_API_TOKEN
```

**方式三：复用官方 CLI 已保存的 Token**

如果你已经跑过官方 `mineru-open-api auth`，本 skill 也会尝试回退读取 `~/.mineru/config.yaml` 中保存的 Token。

当前读取优先级为：

1. 本 skill 的 `.claude/skills/mineru-ocr/config/.env` 中的 `MINERU_API_TOKEN`
2. 环境变量 `MINERU_API_TOKEN`
3. 环境变量 `MINERU_TOKEN`
4. 官方 CLI 配置 `~/.mineru/config.yaml`

### Token 更新

按当前规则，Token 有效期 **3 个月（约 90 天）**。过期后转换失败（错误 `401` 或 `Unauthorized`）。

更新方法：告诉 AI "我的 MinerU Token 过期了，新的 Token 是：xxx"

---

## 功能说明

通过 MinerU 将文档转换为 Markdown 格式，支持：

- Auto 模式：无 Token 走免登录轻量接口，有 Token 走标准 API
- PDF、DOC、DOCX、PPT、PPTX、PNG、JPG、JPEG
- 本地文件、远程文档 URL、网页 URL
- OCR 文字识别
- 表格识别和保留
- 数学公式识别
- 结果归档，保留 Markdown、接口响应和相关图片资源，便于回溯

## 能力边界

| 场景 | 免登录轻量接口 | 标准 Token API |
| ---- | -------------- | -------------- |
| 本地 PDF / 图片 / Docx / Pptx | 支持 | 支持 |
| 远程文档 URL（PDF、图片、Doc/Docx、PPT/PPTx） | 支持 | 支持 |
| 网页 URL / HTML | 不支持 | 支持 |
| 单文件大小 | 10 MB 内 | 200 MB 内 |
| 页数限制 | 20 页内 | 600 页内 |
| 表格识别 | 不支持，按官方口径需升级到标准模式 | 支持 |
| 公式识别 | 不支持，按官方口径需升级到标准模式 | 支持 |
| 输出 | Markdown | Zip 结果包 + Markdown / JSON / 额外格式 |

### 轻量模式适用

- 初次使用、快速试跑
- 本地小文件
- 远程 PDF / Doc / Ppt 链接
- 不要求表格识别、公式识别

### 标准 API 适用

- 大文件、长文档
- 对表格、公式、复杂版面更敏感的场景
- 网页 URL 提取
- 希望获得更完整的结果包并保留更多中间结果

## 使用方法

```bash
/usr/bin/osascript -l JavaScript .claude/skills/mineru-ocr/scripts/convert.js "/path/to/file.pdf"
/usr/bin/osascript -l JavaScript .claude/skills/mineru-ocr/scripts/convert.js "https://cdn-mineru.openxlab.org.cn/demo/example.pdf"
/usr/bin/osascript -l JavaScript .claude/skills/mineru-ocr/scripts/convert.js "https://example.com/article"
/usr/bin/osascript -l JavaScript .claude/skills/mineru-ocr/scripts/convert.js checktoken
```

## 配置选项

编辑 `.claude/skills/mineru-ocr/config/.env`：

| 选项                  | 默认值   | 说明            |
| --------------------- | -------- | --------------- |
| MINERU_API_TOKEN      | 空       | 可选；填写后强制走标准 Token API |
| MINERU_ENABLE_OCR     | true     | 启用 OCR        |
| MINERU_ENABLE_TABLE   | true     | 启用表格识别；主要对标准 Token API 生效 |
| MINERU_ENABLE_FORMULA | false    | 启用公式识别；主要对标准 Token API 生效 |
| MINERU_LANGUAGE_CODE  | ch       | 语言代码        |
| MINERU_API_BASE       | `https://mineru.net/api/v4` | 标准 API 地址 |
| MINERU_MODEL_VERSION  | `pipeline` | 标准 Token API 模型；法律文档建议默认 `pipeline`，复杂版面可改 `vlm` |
| MINERU_PAGE_RANGES    | 空       | 标准 Token API 页码范围，如 `1-20`、`2,4-6` |
| MINERU_POLL_MAX       | 20       | 最大轮询次数    |
| MINERU_POLL_SLEEP     | 10       | 轮询间隔（秒）  |
| MINERU_LOG_LEVEL      | medium   | 日志等级        |

## 输出

- **本地文件**：Markdown 保存到源文件同目录
- **远程文档 URL / 网页 URL**：Markdown 默认保存到执行命令时的当前目录
- **归档**：`.claude/skills/mineru-ocr/archive/日期_时间_文件名/`
- **归档内容**：转换得到的 Markdown、接口响应、原始输入文件，以及可下载的图片资源清单

## 法律文档建议

- 默认保持 `MINERU_MODEL_VERSION=pipeline`
- 对起诉状、证据目录、法院通知、传票这类正式材料，优先追求稳定和低幻觉风险，不建议默认改成 `vlm`
- 只有在扫描质量差、版面极复杂、表格密集时，再考虑切到 `vlm`
- 如果只需要先看卷宗前几页，可设置 `MINERU_PAGE_RANGES=1-20`

## Token 自检

当你想确认当前 Token 是否有效时，可运行：

```bash
/usr/bin/osascript -l JavaScript .claude/skills/mineru-ocr/scripts/convert.js checktoken
```

- 未配置 Token：会提示当前处于轻量模式
- Token 有效：会提示标准 API 可用
- Token 失效：会明确提示重新申请与更新

## 云端模式 / 自定义地址

当前 skill 仅面向 **官方云端 API**。

如需走你自己的云端转发网关，且该网关 **兼容官方 v4 API**，可在 `.env` 中修改：

```bash
MINERU_API_BASE=https://your-gateway.example.com/api/v4
```

当前脚本默认适配的是官方云端 v4 API 工作流。

如果你部署的是官方 `mineru-api` / `mineru-router` FastAPI 服务，它们主要暴露的是 `/tasks`、`/file_parse` 等接口，**不在本 skill 当前支持范围内**。这类场景建议：

- 优先使用官方 CLI / SDK 直连自建服务
- 本 skill 继续只维护云端模式，避免混入第二套协议

## 关于官方 Crawl

官方 skill 中的网页提取主要是通过 CLI 的 `mineru-open-api crawl <url>` 实现的，属于 **Token 模式能力**，不是轻量接口能力。

这里的 CLI 是 **官方提供的命令行封装层**。CLI 底层仍然会调用 MinerU 的云端 API；它不是本地离线解析器。

你当前这个 skill 现在也支持网页 URL，但仅在 **已配置 Token** 时启用；未配置 Token 时，网页 URL 会提示用户改用标准 API。

## 故障排除

| 问题             | 解决方案                                       |
| ---------------- | ---------------------------------------------- |
| 轻量接口限频     | 稍后重试，或配置 Token 切换到标准 API         |
| 文件过大 / 页数过多 | 配置 Token，改走标准 API                    |
| 网页 URL 无法轻量解析 | 轻量接口不支持 HTML，请配置 Token          |
| 401/Unauthorized | Token 已过期，重新申请并更新                   |
| 转换超时         | 增加 `MINERU_POLL_MAX` 或检查文件大小         |
| 配额不足         | 检查 MinerU 账户额度                           |
