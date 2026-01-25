---
name: piclist-upload
description: 通过 PicList HTTP Server 将 Markdown 文件中的本地图片上传到图床，并替换为云端链接。本技能应在用户需要上传 Markdown 中的图片、处理包含本地图片引用的 Markdown、批量处理多个 Markdown 文件或目录、或替换本地路径为云端链接以实现跨设备访问时使用。
license: Complete terms in LICENSE.txt
---

# PicList 图片上传

将 Markdown 文件中的本地图片上传到配置的图床，并将本地路径替换为云端链接。

## 前置条件

- 已安装 PicList 并启用 HTTP Server
- 已在 PicList 中配置图床

**首次配置**: 请参阅 [references/setup.md](references/setup.md) 安装和配置指南。

## 工作流程

### 1. 确定处理范围

- **单个文件**: `file.md`
- **多个文件**: `file1.md file2.md`
- **目录**: 扫描目录中所有 `.md` 文件
- **多个目录**: 递归处理每个目录

### 2. 提取和过滤图片路径

解析 `![alt](path)` 模式：

- 提取相对路径和绝对路径
- **跳过已有 URL**: 忽略 `http://` 和 `https://` 链接
- 保留 alt 文本描述

### 3. 上传和替换

1. 将相对路径解析为绝对路径
2. 验证文件是否存在
3. 通过 PicList HTTP Server 上传
4. 将本地路径替换为云端 URL
5. **删除本地图片文件**（除非使用 `--keep-local`）
6. 直接修改原文件

## 使用方法

### 处理目录（默认删除本地图片）

```bash
scripts/process.sh --in-place docs/
```

直接修改 `docs/` 中的所有 Markdown 文件，上传成功后删除本地图片。

### 处理指定文件（保留本地图片）

```bash
scripts/process.sh --in-place --keep-local README.md docs/guide.md
```

直接修改指定的文件，但保留本地图片不删除。

### 预览模式（不修改文件）

```bash
scripts/process.sh --dry-run README.md
```

查看将要进行的替换，不实际修改文件。

## 命令选项

| 选项 | 说明 |
|------|------|
| `--in-place` | 直接修改原文件 |
| `--keep-local` | 保留本地图片文件（默认删除） |
| `--dry-run` | 预览模式，不修改文件 |

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
