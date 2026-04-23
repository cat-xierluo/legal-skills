---
name: new-case
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
description: 将案件/咨询材料整理成标准化目录结构。支持诉讼案件（12目录）和潜在项目/咨询（3目录）两种预设。本技能应在用户需要创建新案件、初始化案件目录结构、整理咨询材料、或通过参数和自然语言指定案件编号、委托人、案件类型等信息快速创建案件时使用。不要用于：单独生成法律文书、进行法律研究、证据分析等非案件初始化任务。
license: CC BY-NC-SA 4.0 - 详见 LICENSE.txt
---

# New Case - 创建新案件/整理咨询材料

将案件原始材料或咨询材料整理成标准化目录结构。支持两种预设：
- **诉讼案件 (litigation)**：12层标准诉讼目录，生成案件信息看板、工时记录和期限管理文件
- **潜在项目/咨询 (consultation)**：3目录轻量结构，生成项目信息卡片和待办事项

## 适用场景

1. 新建诉讼案件档案，需要建立标准化目录结构
2. 已有诉讼案件材料，需要整理成统一格式
3. 整理潜在客户咨询材料，建立咨询档案
4. 接收新案件/新咨询，需要快速搭建框架

## 触发方式

### 自然语言触发
- "整理这个案件材料：/path/to/case-folder"
- "帮我建立案件结构：案件在 /path/to/case"
- "创建新案件"
- "新建案件"
- "整理咨询材料：/path/to/consultation-folder"
- "整理这个潜在项目的文件"

### 参数化触发
支持以下参数（通过自然语言或结构化方式传递）：

| 参数 | 必需 | 说明 | 示例 |
|------|------|------|------|
| `--case-id` | 是 | 案件/项目编号 | `[2025]京0105民初1234号` 或 `260323 张美金 咨询` |
| `--client-name` | 否 | 委托人姓名/公司名 | `北京科技有限公司` |
| `--case-type` | 否 | 案件类型 | `诉讼`/`咨询`/`民事`/`刑事`/`行政` |
| `--case-cause` | 否 | 案由 | `合同纠纷` |
| `--opposite-party` | 否 | 对方当事人 | `上海某某公司` |
| `--input-dir` | 否 | 案件材料目录 | `/path/to/materials` |

其中 `--case-type` 的 `诉讼` 或 `民事`/`刑事`/`行政` 对应 litigation 预设，`咨询` 对应 consultation 预设。

**使用示例**：
```
"创建新案件，案件编号 [2025]京0105民初1234号，委托人北京科技有限公司，案由合同纠纷，对方当事人上海某某公司"
"整理咨询材料 /path/to/folder，客户张美金"
```

## 工作流程

### 第零步：确定类型并加载预设

1. **读取 `--case-type` 参数**：
   - `诉讼`/`民事`/`刑事`/`行政` → 加载 `assets/litigation.yaml`
   - `咨询` → 加载 `assets/consultation.yaml`

2. **自动检测**（未指定类型时）：
   - 读取 `assets/` 下所有预设的 `detection` 配置
   - 检查输入目录路径是否匹配 `path_patterns`
   - 扫描文件名是否匹配 `material_hints`（正向）和 `negative_hints`（排除）
   - 若检测到诉讼材料（传票、起诉状等），即使路径含"咨询"也优先使用 litigation
   - 若无法确定，向用户确认

3. **加载对应预设**：读取选定的 YAML 配置文件，后续步骤均基于该预设执行

4. **默认回退**：若未指定且无法检测，默认使用 litigation 预设

### 第一步：分析输入材料

1. **扫描文件夹**，列出所有文件
2. **识别材料类型**：法律服务方案、聊天记录、证据材料、委托材料、身份证明、其他
3. **提取关键信息**：按 [references/extraction-rules.md](references/extraction-rules.md) 从不同材料类型中提取当事人、案由、金额等信息

### 第二步：建立目录结构

读取预设配置的 `directories` 部分，按 id 排序创建目录。

**诉讼案件**：创建12个标准目录（`00 - 📅 日程管理` 至 `11 - 📚 参考文件`）

**咨询项目**：创建3个目录：
```
├── 01 - 💬 咨询记录/    # 录音、转写、微信聊天、通话记录
├── 02 - 📎 证据材料/    # 合同、声明、鉴定报告、权属证明
└── 03 - 📝 工作文件/    # 法律服务方案、内部沟通、策略分析
```

### 第三步：材料分类整理

读取预设配置的 `classification` 规则，按顺序匹配关键词，将材料移入对应目录。详细分类决策逻辑见 [references/classification-guide.md](references/classification-guide.md)。

咨询项目额外规则：
- 名称匹配 `root_files` 配置的文件（法律服务方案、法律意见书、咨询报告）保留在根目录
- 转写文稿与对应音频放在同一目录

### 第四步：生成管理文件

根据预设配置的 `management_files` 逐项生成：

| 文件 | 诉讼 | 咨询 | 模板 |
|------|------|------|------|
| 案件/项目信息 | ✅ case-info.md | ✅ consultation-info.md | 按预设选用 |
| 工时记录 | ✅ | ❌ | timesheet.md |
| 期限管理 YAML | ✅ | ❌ | deadline-yaml.md |
| 待办事项 | ✅ | ✅ | task-list.md |

**诉讼案件**生成案件信息看板，详见 `templates/case-info.md`。

**咨询项目**生成项目信息卡片，详见 `templates/consultation-info.md`。

### 可选第五步：生成法律服务方案

如材料中包含初步沟通记录或客户需求描述，建议使用 legal-proposal-generator skill 生成法律服务方案。
- 诉讼案件：输出到 `{01}/` 目录
- 咨询项目：输出到根目录

## 参考文档

详细规则已外置到 `references/` 目录，按需读取：

| 文件 | 内容 |
|------|------|
| [references/naming-conventions.md](references/naming-conventions.md) | 案件编号、案件名称、文件命名规则 |
| [references/classification-guide.md](references/classification-guide.md) | 材料分类决策逻辑、模糊场景处理 |
| [references/extraction-rules.md](references/extraction-rules.md) | 从不同材料类型提取案件信息的规则 |

## 时间要求

使用系统当前时间（通过 `date "+%Y-%m-%d"` 获取），确保：
- 文档创建时间为当前日期
- 时间线逻辑正确（过去→现在→未来）
- 剩余天数计算准确

## 自定义配置

### 预设配置

目录结构和材料分类规则由 `assets/` 下的 YAML 文件定义。每个预设文件包含：

- **meta**：预设元信息（ID、名称、描述、编号格式）
- **directories**：目录定义（编号、图标、名称、描述）
- **management_files**：管理文件生成配置（启用/禁用、模板路径、输出路径）
- **detection**：自动检测规则（路径关键词、文件关键词、排除关键词）
- **classification**：材料分类规则（关键词→目标目录）
- **root_files**（可选）：根目录保留文件规则

现有预设：
- `assets/litigation.yaml` — 诉讼案件（12目录）
- `assets/consultation.yaml` — 潜在项目/咨询（3目录）

### 新增预设

如需支持新的案件类型（如公司法务、知产申请等），在 `assets/` 下新建 YAML 文件，按上述结构填写即可。SKILL.md 工作流无需改动。

### 向后兼容

原 `references/case-config.yaml` 已迁移到 `assets/litigation.yaml`，不再保留旧文件。

## 输出验证

完成整理后，确认：

- [ ] 目录结构已按预设配置创建
- [ ] 所有材料已分类移动到对应目录
- [ ] 管理文件已按预设的 management_files 配置生成
- [ ] 文件命名符合规范
- [ ] 时间逻辑正确

## 禁止事项

- 禁止在案件档案中记录项目自身的 SuitAgent 系统信息
- 禁止创建额外的说明文档或 README
- 禁止遗漏任何已有材料
- 禁止虚构案件信息
