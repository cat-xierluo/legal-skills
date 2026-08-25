# WorkBuddy 部署说明

## 三件套配置

在 WorkBuddy 创建"自动化任务"：

| 字段 | 值 |
|---|---|
| **名称** | `{audience} 法律周报`（如"科技型制造企业 法律周报"） |
| **工作时间** | 每周一 09:00（建议；可按 audience 调整） |
| **提示词** | 见下方 |

## 提示词模板

```text
你是定时法律研报生成助手。每周一上午跑一次 `{audience}` 客户的法律周报。

执行步骤：
1. 加载配置：读 `~/.claude/skills/weekly-legal-briefing/config/report-profile.md` 和 `config/audience-profile.md` 和 `config/sources-whitelist.txt`
2. 选题：基于 audience-profile.md 的"选题优先级"提取 3-5 条；或按 --industry-keywords 覆盖
3. 检索：仅检索白名单内信源,白名单外丢弃
4. 案例：入案例研究板块的必须含案号 + 审理法院 + 裁判日期,且案号可在 https://wenshu.court.gov.cn 检索
5. 生成：按 templates/briefing-skeleton.md 五段式填 md
6. 渲染：python3 ~/.claude/skills/weekly-legal-briefing/scripts/render.py \
   --input {本期 md 路径} \
   --output {本期 HTML 路径} \
   --profile ~/.claude/skills/weekly-legal-briefing/config/report-profile.md
7. PDF：python3 ~/.claude/skills/weekly-legal-briefing/scripts/pdf.py \
   --input {本期 HTML 路径} \
   --output archive/法律周报_{audience}_{YYYY}第{N}期_DRAFT.pdf \
   --profile ~/.claude/skills/weekly-legal-briefing/config/report-profile.md
8. 元数据：写 archive/法律周报_{audience}_{YYYY}第{N}期_DRAFT.meta.json
9. 自检：生成 archive/法律周报_..._DRAFT.checklist.md

硬约束：
- 输出文件一律带 `_DRAFT` 后缀,不得去掉
- 不做邮件/微信群发,不在频道推送可发布的版本
- 可在频道发"本期已生成 _DRAFT,请复核"提醒,但发布动作由人完成
- 信源必须 100% 来自白名单
- 案例必须 100% 案号可回查,查不到的剔除
```

## 期数自动递增

`scripts/render.py` 会读 `archive/_meta.jsonl`,自动判断下一个期数编号。如失败,提示用户手动指定 `--period-number N`。

## 监控

- 任务失败时,WorkBuddy 把错误日志投递到频道,人工介入
- 每周一 09:30 由人工检查本期 `_DRAFT.pdf` 是否正常生成
- 复核时长 > 15 分钟/期,提示该 skill 生成质量需要调白名单或选题
