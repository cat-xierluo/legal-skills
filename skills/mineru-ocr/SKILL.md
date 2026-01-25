---
name: mineru-ocr
description: 将 PDF 文档转换为 Markdown 格式，使用 MinerU API 进行转换，支持 OCR、表格和公式识别。本技能应在用户需要转换 PDF、Word、PPT 或图片文档为 Markdown，或提到 PDF 转 Markdown、OCR、文字识别、表格识别、公式识别、文档转换、图片转文字、扫描件转换时使用。
license: Complete terms in LICENSE.txt
---
# MinerU PDF 转 Markdown

## 前置配置

> **⚠️ 重要**：使用前需要申请 MinerU API Token（有效期 14 天）

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

### Token 更新

Token 有效期 **14 天**，过期后转换失败（错误 `401` 或 `Unauthorized`）。

更新方法：告诉 AI "我的 MinerU Token 过期了，新的 Token 是：xxx"

---

## 功能说明

通过 MinerU API 将文档转换为 Markdown 格式，支持：

- PDF、DOC、DOCX、PPT、PPTX、PNG、JPG、JPEG
- OCR 文字识别
- 表格识别和保留
- 数学公式识别

## 使用方法

```bash
/usr/bin/osascript -l JavaScript .claude/skills/mineru-ocr/scripts/convert.js "/path/to/file.pdf"
```

## 配置选项

编辑 `.claude/skills/mineru-ocr/config/.env`：

| 选项                  | 默认值   | 说明            |
| --------------------- | -------- | --------------- |
| MINERU_API_TOKEN      | *必需* | MinerU API 令牌 |
| MINERU_ENABLE_OCR     | true     | 启用 OCR        |
| MINERU_ENABLE_TABLE   | true     | 启用表格识别    |
| MINERU_ENABLE_FORMULA | false    | 启用公式识别    |
| MINERU_LANGUAGE_CODE  | ch       | 语言代码        |
| MINERU_POLL_MAX       | 20       | 最大轮询次数    |
| MINERU_POLL_SLEEP     | 10       | 轮询间隔（秒）  |

## 输出

- **Markdown**：源文件同目录，同名 `.md` 扩展名
- **归档**：`.claude/skills/mineru-ocr/archive/日期_时间_文件名/`

## 故障排除

| 问题             | 解决方案                                       |
| ---------------- | ---------------------------------------------- |
| 配置不存在       | 复制 `.env.example` 到 `.env` 并填入 Token |
| 401/Unauthorized | Token 已过期，重新申请并更新                   |
| 转换超时         | 增加 `MINERU_POLL_MAX` 或检查文件大小        |
| 配额不足         | 检查 MinerU 账户余额                           |
