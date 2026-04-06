---
name: yuandian-law-search
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.2.0"
license: MIT
description: 元典法条与案例检索。本技能应在需要查询中国法律法规条文、检索相关案例、为法律分析提供数据支撑时使用。
---

# 元典法条与案例检索

通过元典 API 检索中国法律法规条文和案例，支持法条语义/关键词/详情检索和案例关键词/向量语义检索共 5 种模式。

## 前置要求（每次调用前自动检测）

每次使用本技能前，**必须先执行以下检测流程**，确认 API Key 已就绪：

### 检测步骤

1. **检测 `.env` 文件**：检查 `scripts/.env` 是否存在
2. **检测 API Key**：读取文件中 `YD_API_KEY` 的值，确认非空且不是占位符 `your-api-key-here`
3. **若检测失败**，向用户提示以下引导信息并终止：

```
⚠️ 元典 API Key 未配置。请按以下步骤获取并配置：

1. 注册/登录：访问 https://passport.legalmind.cn/ ，使用手机号注册
2. 创建 API Key：登录后访问 https://passport.legalmind.cn/apiKey/manage ，点击「创建 Key」
3. 配置密钥：将 Key 填入以下文件

   scripts/.env
   ─────────────
   YD_API_KEY=sk-你的密钥
   ─────────────

API 覆盖范围：法条检索（语义/关键词/详情）+ 案例检索（关键词/向量语义），共 5 个端点，共用同一个 Key。
配置完成后重新发起检索即可。
```

4. **若检测通过**，继续执行用户请求的检索命令

### 检测命令

```bash
# 检测 .env 文件和 API Key
if [ -f "scripts/.env" ]; then
  KEY=$(grep '^YD_API_KEY=' scripts/.env | cut -d'=' -f2)
  if [ -n "$KEY" ] && [ "$KEY" != "your-api-key-here" ]; then
    echo "API Key 已就绪"
  else
    echo "API Key 未配置"
  fi
else
  echo ".env 文件不存在"
fi
```

## 五种检索模式

### 1. 法条语义检索（search）

用自然语言提问，找到最相关的法条。

```bash
python3 scripts/yd_search.py search "正当防卫的限度" --sxx 现行有效
```

### 2. 法条关键词检索（keyword）

用精确关键词检索法条，支持日期范围和效力级别筛选。

```bash
python3 scripts/yd_search.py keyword "人工智能 监管" \
  --effect1 法律 --sxx 现行有效 \
  --fbrq-start 2022-01-01 --fbrq-end 2026-03-01
```

### 3. 法条详情检索（detail）

按法规名称 + 条号精确获取某一条法条全文。

```bash
python3 scripts/yd_search.py detail "民法典" --ft-name "第十五条"
```

### 4. 案例关键词检索（case）

用关键词检索案例，支持案由、法院、省份等多维过滤。

```bash
python3 scripts/yd_search.py case "买卖合同纠纷" --province 广西 --authority-only
```

### 5. 案例语义检索（case-semantic）

用自然语言描述查找相似案例。

```bash
python3 scripts/yd_search.py case-semantic "正当防卫的限度" --jarq-start 2020-01-01
```

## 通用参数说明

### 法条检索通用筛选

| 参数 | 说明 | 可选值 |
|------|------|--------|
| `--effect1` | 效力级别（可多次指定） | 宪法、法律、司法解释、行政法规、部门规章、地方性法规 等 |
| `--sxx` | 时效性（可多次指定） | 现行有效、失效、已被修改、部分失效、尚未生效 |

### 案例检索通用筛选

| 参数 | 说明 |
|------|------|
| `--authority-only` | 仅检索权威/典型案例 |
| `--province` | 省份筛选 |
| `--jarq-start / --jarq-end` | 结案日期范围 |

完整参数说明见 [references/api-spec.md](references/api-spec.md)。

## 输出格式

脚本输出 Markdown 格式，包含法条全文、法规名称、发布机关、时效性等元信息，以及原文链接。可直接用于法律文书引用或 AI 分析。

## 调试

使用 `raw` 子命令查看原始 JSON 响应：

```bash
python3 scripts/yd_search.py raw /search "正当防卫" --extra '{"sxx":["现行有效"]}'
```

## 与其他技能配合

- **litigation-analysis**：分析判决书时，可先用本技能检索相关法条和类案
- **legal-proposal-generator**：生成法律意见书时引用精确法条
- **contract-review**：审查合同时检索相关法规验证合规性
- **trademark-assistant / patent-analysis**：查找相关法律依据

各技能独立运行，按需组合。
