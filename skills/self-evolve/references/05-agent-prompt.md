# Agent Prompt 模板

本文记录 `scripts/sediment_guard.py` 启动 headless Claude 时应传入的任务约束。当前不再把大段 prompt 直接写进 `~/.claude/settings.json`；settings 只配置 `SessionEnd` command hook。

实际启动独立分析 session 的完整 prompt 模板见 `references/07-headless-analysis-prompt.md`。修改触发提示词时优先改该文件，不改脚本。

## 一、输入

Headless Claude 应读取：

- 当前会话 transcript：由 hook 输入的 `transcript_path` 提供
- 核心 Skill 清单：`config/core_skills.yaml`（或脚本通过 `SELF_EVOLVE_CORE_SKILLS` 注入的路径；旧 `SKILL_EVOLVE_CORE_SKILLS` 仍兼容）
- 程序化评估结果：由 `sediment_guard.py` 注入 prompt
- 本次候选记录：`runtime/learning-candidates/*.md`
- 已有升级方向清单：`review/output/upgrade-direction/*.md`
- 已有文章草稿：`review/output/articles/*.md`
- 纠正面板：`review/review-log.md`

## 二、轻量过滤关键词

`sediment_guard.py` 优先使用 `config/core_skills.yaml` 中的 `domain_keywords`。常见关键词包括：

- 法律：侵权、TSA、取证、比对、实质性相似、权利基础、权利要求、原告、被告、著作权、商标权、专利权、不正当竞争、装潢、证据、开庭、举证、管辖
- 工作流：skill、references、模板、命名规范、checklist、DECISIONS、CHANGELOG
- 工具：ffmpeg、视觉模型、OCR、时间戳、抖音、达人、电商、PDF

命中不足时静默退出；中等置信度时只生成候选记录，不启动 headless Claude。

## 三、深度分析任务

进入沉淀后，headless Claude 需要：

1. 识别重复出现的方法论、命名规范、文件组织规范、工具链调用模式、判断流程。
2. 区分通用方法论与案件特定数据。
3. 对照已有升级方向、纠正面板和目标 Skill 的 `DECISIONS.md`，避免重复建议。
4. 判断应沉淀到现有 Skill，还是建议新建 Skill。
5. 生成升级方向清单，必要时生成文章草稿。
6. 如果程序化评估提示 `candidate_only`，不要扩写成成熟升级建议；等待人工审。

## 四、输出路径

```text
self-evolve/
├── review/output/upgrade-direction/<YYMMDD>_<skill-id>_升级建议.md
├── review/output/articles/<YYMMDD>_<topic>.md
└── runtime/logs/<session-id>.log
```

模板来自当前 Skill 目录：

```text
templates/upgrade-direction.md
templates/article.md
```

## 五、强约束

- 不直接修改任何 Skill 内部文件。
- 不把案号、品牌名、原被告、具体产品名、账号、电话、价格等案件特定数据写进升级内容。
- 不在 `systemMessage` 或日志摘要中暴露案件特定数据。
- 不重复已有升级建议或已被用户拒绝的建议。
- 重复出现三次以上、跨任务复用、已验证有效的方法论优先沉淀。
- 升级方向清单必须包含“待用户审清单”和风险说明。
- 文章草稿必须有具体方法论、可复用流程和脱敏风险提示，不生成空泛标题。
- “不要直接改成熟 Skill”是人工审边界，不是放弃沉淀；只能生成建议，不能修改目标 Skill。

## 六、失败兜底

任何读取、写入或 headless Claude 调用失败时，脚本只写日志并静默退出，不阻塞 SessionEnd。
