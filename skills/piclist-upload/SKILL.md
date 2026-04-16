---
name: piclist-upload
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.1.2"
description: 通过 PicList HTTP Server 将 Markdown 文件中的本地图片上传到图床，并替换为云端链接。本技能应在用户需要上传 Markdown 中的图片、处理包含本地图片引用的 Markdown、批量处理多个 Markdown 文件或目录、或替换本地路径为云端链接以实现跨设备访问时使用。
license: Complete terms in LICENSE.txt
---

# PicList 图片上传

将 Markdown 文件中的本地图片上传到配置的图床，并将本地路径替换为云端链接。

## 前置条件

- 已安装 PicList 并启用 HTTP Server
- 已在 PicList 中配置图床
- 已安装 `jq`
- 已安装 `curl`

**首次配置**: 请参阅 [references/setup.md](references/setup.md) 安装和配置指南。

## ⚠️ 强制规则：必须通过脚本执行

**禁止手动 curl 上传。所有操作必须通过 `scripts/process.sh` 脚本执行。** 脚本已内置上传、URL 替换和本地文件删除的完整逻辑，手动操作容易遗漏步骤。

**默认行为是上传成功后删除本地图片。** 只有当用户明确要求保留时，才可添加 `--keep-local`。不得擅自保留本地图片。

## 使用方法

### 处理文件或目录（默认删除本地图片）

```bash
bash scripts/process.sh --in-place <file.md|directory...>
```

### 保留本地图片（仅在用户明确要求时使用）

```bash
bash scripts/process.sh --in-place --keep-local <file.md|directory...>
```

### 预览模式（不修改文件）

```bash
bash scripts/process.sh --dry-run <file.md|directory...>
```

## 命令选项

| 选项 | 说明 |
|------|------|
| `--in-place` | 直接修改原文件（必须指定，否则仅输出到终端） |
| `--keep-local` | 保留本地图片文件。**仅在用户明确要求时使用** |
| `--dry-run` | 预览模式，不上传、不修改文件 |

## 响应格式

解析上传返回的 JSON：

```json
{"success":true,"result":["https://example.com/image.png"]}
```

## 统计报告

处理完成后显示：

```markdown
📊 Summary:
  Total uploaded: 5
  Total skipped: 3
  Total failed: 0
```

- **Uploaded**: 成功上传并替换（已删除本地图片）
- **Skipped**: 已是云端 URL（无需操作）
- **Failed**: 上传错误（保留原始路径）

## 错误处理

- **PicList Server 未运行**: 提示启动 PicList 应用
- **文件不存在**: 跳过并显示 ⚠️ 警告，继续处理
- **上传失败**: 保留原始路径，标记 ❌，继续
- **无效 JSON**: 视为上传失败

## 配置

PicList Server 默认地址为 `http://127.0.0.1:36677/upload`。可通过环境变量覆盖：

```bash
export PICLIST_SERVER=http://127.0.0.1:PORT
```

## 支持格式

png, jpg, jpeg, gif, webp, svg, bmp
