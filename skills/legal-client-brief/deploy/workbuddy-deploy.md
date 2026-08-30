# WorkBuddy 调度说明

## 能力前提

只有当自动化任务能够按期唤起具备以下能力的 Agent 时，才可以自动“跑一期”：

- 调用 `legal-client-brief` Skill；
- 联网检索并访问白名单来源；
- 读取三个本地配置；
- 在本地执行校验与 PDF 构建脚本。

如果任务只能运行 shell 命令，它不能自行完成选题、研究、核验和写作，只能打包已经存在的 Markdown。

## 推荐任务配置

| 字段 | 建议值 |
|---|---|
| 名称 | `<受众标签> 客户简报` |
| 时间 | 每周固定时间；预留人工复核窗口 |
| 通知 | 仅报告本地 `_DRAFT` 路径和失败原因，不附带外发动作 |

提示词模板：

```text
使用 legal-client-brief Skill 生成一期客户简报三件套。

受众配置、品牌配置和信源白名单均读取 Skill 目录内的本地配置。
本期窗口为 <开始日期> 至 <结束日期>，频率为 <daily/weekly/event>。
完成增量选题、白名单检索、案例核验、完整简报、朋友圈和公众号三个 Markdown 草稿后，
运行 validate_report.py 与 validate_channels.py，再使用 build_report.py 构建 HTML、A4 PDF、meta.json 和 checklist.md。
构建时显式传入 cadence、period-start 与 period-end，不从当前日期或历史文件猜测窗口。

必须停在 _DRAFT；不得发送邮件、微信、客户系统消息或外部频道附件。
完成后只返回本地文件路径、自动门禁结果和仍需人工复核的事项。
```

## 首次验收

1. 手动触发一次任务。
2. 确认产物文件名均含 `_DRAFT`。
3. 打开元数据，确认信源 URL、Markdown/PDF 哈希和 `status: DRAFT`。
4. 全页检查 PDF，并实际完成一次人工复核。
5. 第二次运行使用明确的新窗口，确认不会重复上一期旧内容。
