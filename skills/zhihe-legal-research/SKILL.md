---
name: zhihe-legal-research
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.2.1"
license: MIT
description: >
  法律研究与咨询工具。连接智合AI法律大模型平台进行法律研究。当用户需要进行法律问题研究、
  查找相关法律法规、检索类似案例、或获取法律研究报告时使用。支持：发送验证码登录、
  会员状态查询、提交法律问题、获取文字分析结果和 docx 格式研究报告。需要用户拥有智合AI平台会员账号。

  也在用户发送"查看结果"、"研究好了吗"、"结果出来了吗"、"查看报告"、
  "法律研究结果"等查询已提交任务状态的消息时触发。

  触发关键词：法律研究、法律咨询、法律问题、案例检索、法律法规、法律报告、
  legal research、法律分析、合同纠纷、劳动争议、知识产权、
  查看结果、查看报告、研究好了吗、结果出来了吗、法律研究结果。
metadata:
  openclaw:
    requires:
      bins:
        - curl
---

# 智合法律研究 (Zhihe Legal Research)

连接智合AI法律大模型平台，提供专业的法律调研分析服务。

## ⚠️ 关键机制：两阶段交互（必须理解）

法律研究是**异步长任务**（3-10分钟）。**你无法在提交后自动轮询等待结果**。整个流程分两个阶段，由用户的两次消息分别触发：

**阶段一：用户提问 → 你提交问题 → 告知用户等待**
**阶段二：用户发"查看结果" → 你查询状态 → 返回结果**

两个阶段之间需要用户等待约 3.5 分钟后手动发送消息触发第二阶段。你必须在阶段一结束时**明确告诉用户这一点**。

**核心原则：**
- **不在每次消息前自动检查结果**——避免旧结果污染当前对话
- **仅在用户主动询问研究结果时**才查询状态和结果
- **每次查询完毕后立即归档**——确保状态干净，不留残留数据

---

## 工作流程

### 步骤 1：检查登录状态

```bash
./scripts/auth.sh check
```

- `is_vip: true` → 已登录，继续
- `code: 401` → 需要登录（执行步骤 2）

### 步骤 2：登录（如需）

```bash
# 发送验证码（如果已保存手机号，可省略手机号参数）
./scripts/auth.sh send-code [手机号]

# 验证登录（自动保存 Token 和手机号）
./scripts/auth.sh verify <手机号> <6位验证码>
```

**自动重登流程**：如果 `config` 中已保存 `LEGAL_RESEARCH_PHONE`，token 失效时可直接执行 `./scripts/auth.sh send-code`（无需传入手机号），系统自动使用保存的手机号发送验证码。用户只需提供验证码即可完成重登。

### 步骤 3：提交法律问题（阶段一）

```bash
# 提交问题
./scripts/research.sh submit "<用户的法律问题>"
```

**成功返回示例：**
```json
{
  "code": 200,
  "message": "已提交，正在进行法律调研分析",
  "data": {
    "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "estimated_completion": "14:35:30",
    "estimated_seconds": 210
  }
}
```

**提交成功后，记录 task_id 并告知用户（非常重要）：**

> ✅ 您的法律问题已提交，后台正在进行调研分析。
> ⏱️ 预计需要 3-4 分钟完成。
> 📋 任务 ID：`{task_id}`
>
> 👉 **请在大约 3 分半钟后，给我发送"查看结果"，我会为您获取分析结果和研究报告。**

**不要尝试自动等待或轮询。** 提交后你的工作就结束了，等用户再次发消息时再继续。

### 步骤 4：查询结果（阶段二 — 仅当用户主动询问时）

**触发条件：** 用户主动询问研究结果（如"查看结果"、"结果出来了吗"等）。

如果用户提供了 task_id，直接查询；如果未提供，先查历史获取最近任务：

```bash
# 如果没有 task_id，先查历史
./scripts/research.sh history 1 3
```

然后查询状态：

```bash
# 查询状态
./scripts/research.sh status <task_id>
```

**根据状态处理：**

| 状态 | 处理方式 |
|------|----------|
| `completed` | 获取结果 → 获取报告 → 归档 → 展示给用户 |
| `running` | 告知用户继续等待 1-2 分钟后再查询 |
| `pending` | 告知用户仍在排队中，稍后再查 |
| `failed` | 告知用户失败原因，建议重新提交 |
| `timeout` | 告知用户超时，建议简化问题重试 |

**当状态为 completed 时，依次执行：**

```bash
# 1. 获取文字结果
./scripts/research.sh result <task_id>

# 2. 获取报告下载链接
./scripts/research.sh report <task_id>

# 3. 自动归档（下载报告到 archive/ 目录，含 Markdown 转换）
./scripts/research.sh archive <task_id>
```

**展示结果时的模板：**

> 📋 **法律分析结果：**
>
> （这里展示 text_result 的内容）
>
> 📄 **详细报告：**
> [点击下载完整法律研究报告](<report_url>)
> 文件名：<filename>

如果只有文字结果没有报告（`has_report: false`），只展示文字部分即可。

---

## Claude Code 增强模式（可选）

**仅在 Claude Code 环境下可用。** 提供更好的异步体验，无需用户手动查询。

提交任务后，使用 `Bash` 工具的 `run_in_background: true` 启动后台监控：

```bash
command: "./scripts/monitor.sh monitor <task_id> 600 30"
run_in_background: true
timeout: 600000
```

**关键注意事项：**

1. **timeout 必须设为 600000**（10分钟），否则默认 2 分钟会超时
2. 后台监控完成后会自动收到通知，此时展示结果给用户
3. 监控脚本会自动归档到 `archive/` 目录

**OpenClaw 环境不支持此增强模式**，请使用标准流程（步骤 1-4）。

---

## 常用命令

### 认证
| 命令 | 用途 |
|------|------|
| `./scripts/auth.sh check` | 检查登录状态 |
| `./scripts/auth.sh send-code [phone]` | 发送验证码（省略手机号时使用已保存的号码） |
| `./scripts/auth.sh verify <phone> <code>` | 验证登录（自动保存 Token 和手机号） |
| `./scripts/auth.sh logout` | 清除凭证 |

### 研究操作
| 命令 | 用途 |
|------|------|
| `./scripts/research.sh submit "<query>"` | 提交问题 |
| `./scripts/research.sh status <task_id>` | 查询状态 |
| `./scripts/research.sh result <task_id>` | 获取结果 |
| `./scripts/research.sh report <task_id>` | 获取报告链接 |
| `./scripts/research.sh archive <task_id>` | 归档研究结果 |
| `./scripts/research.sh history [page] [size]` | 查看历史任务 |

### 监控管理（仅 Claude Code 增强模式）
| 命令 | 用途 |
|------|------|
| `./scripts/monitor.sh monitor <task_id> [timeout] [interval]` | 阻塞监控 |
| `./scripts/monitor.sh status` | 查看监控状态 |
| `./scripts/monitor.sh results` | 获取已完成待通知的结果 |
| `./scripts/monitor.sh clear <task_id>` | 标记为已通知 |

---

## 状态处理

| 状态 | 说明 | 处理 |
|------|------|------|
| `pending` | 排队中 | 告知用户等待 |
| `running` | 处理中 | 告知用户继续等待 |
| `completed` | 已完成 | 获取结果 → 归档 → 通知用户 |
| `failed` | 失败 | 通知用户失败原因 |
| `timeout` | 超时 | 通知用户超时 |

---

## 错误处理

| HTTP 状态码 | 含义 | 处理方式 |
|-------------|------|---------|
| 400 | 参数错误 | 检查输入格式 |
| 401 | 未认证/Token过期 | 引导重新登录 |
| 403 | 非会员/无权限 | 提示开通会员 |
| 404 | 任务不存在 | 通过 history 接口查最近任务 |
| 429 | 频率限制/任务进行中 | 告知用户稍后再试 |
| 502 | 上游服务错误 | 稍后重试 |

---

## 配置

所有配置文件自包含在 skill 内部：`assets/`

| 文件 | 用途 |
|------|------|
| `.env` | Token 和手机号配置（已加入 .gitignore） |
| `pending.json` | 待处理任务 |
| `completed.json` | 已完成待通知 |
| `notified.json` | 已通知历史 |

**注意**：`assets/.env` 已加入 `.gitignore`，敏感信息不会被提交到 git。

配置示例见 [assets/.env.example](assets/.env.example)

---

## 归档功能

### 自动归档

**任务完成时自动归档**：归档时会自动下载报告并保存到 `archive/` 目录。

**归档命名格式**：`YYMMDD 主题_法律研究报告`

示例：
```
archive/
├── 260326 美术作品著作权侵权纠纷_法律研究报告/
│   ├── result.md       # 研究结果摘要（Markdown）
│   ├── report.docx     # 详细报告（自动下载）
│   ├── report.md       # 报告 Markdown 版本（需安装 pandoc）
│   └── media/          # 报告中的图片（如有）
└── 260310 劳动合同解除赔偿_法律研究报告/
    └── result.md
```

### 手动归档

```bash
# 归档研究结果（自动下载报告并转换为 Markdown）
./scripts/research.sh archive <task_id>

# 列出所有归档
./scripts/research.sh list-archive
```

### Markdown 转换依赖

归档时会自动尝试将 docx 报告转换为 Markdown：
- **依赖**：需要安装 [pandoc](https://pandoc.org/)
- **格式**：使用 GitHub Flavored Markdown (GFM)，保留原始层级结构
- **图片**：自动提取到 `media/` 子目录

```bash
# macOS 安装 pandoc
brew install pandoc
```

---

## 详细文档

- [API 参考文档](references/api-reference.md) - 完整 API 说明
- [交互示例](references/interaction-examples.md) - 各种场景的完整流程（含两阶段流程、结果未就绪、首次登录、忘记 task_id 四种场景）

---

## 注意事项

1. **不要尝试自动轮询**：提交问题后，你无法自动等待结果。必须等用户再次发送消息才能继续。这是架构限制，不是 bug。
2. **必须明确引导用户**：提交后务必告诉用户"3分半钟后发送'查看结果'"，否则用户不知道怎么获取结果。这是最重要的一步。
3. **会员要求**：需要智合AI平台会员，非会员引导至 https://www.zhiexa.com
4. **Token 有效期**：72 小时，过期需重新登录
5. **频率限制**：每分钟仅可提交 1 个问题，同时只能有 1 个进行中任务
6. **报告链接**：有效期 7 天，过期后重新调用接口会自动刷新
7. **隐私保护**：手机号仅用于鉴权，展示时脱敏
8. **跨平台兼容**：核心流程仅依赖 bash 脚本（内含 curl），兼容所有 Agent 平台（Claude Code、OpenClaw）
