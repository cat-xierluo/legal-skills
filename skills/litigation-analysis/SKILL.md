---
name: litigation-analysis
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.3.2"
license: CC-BY-NC
description: "诉讼分析工具，对起诉状、一审/二审判决书和庭审笔录进行结构化深度抽取，生成内部版、研究版、客户版三层递进分析报告，支持上诉/再审决策和庭审策略复盘。本技能应在用户需要分析法院判决书、评估上诉或再审可行性、复盘庭审笔录、或需要案件分析报告时使用。"
---

# litigation-analysis

## 功能概述

本技能支持三种诉讼文档分析场景：

### 场景一：起诉状与证据分析

针对案件初期的起诉状和证据材料，快速评估案件基础，识别风险和证据缺口，生成内部版和客户版报告。详见 [起诉状与证据分析](references/complaint-evidence-extraction.md)。

### 场景二：判决书分析（核心功能）

针对一审/二审判决书，生成三层递进输出：

- **内部版**：面向主办律师的全面深度分析报告
- **研究版**：识别法律问题，生成研究课题清单
- **客户版**：面向非法律专业人士的通俗呈现

辅助参考文件（起诉状、上诉状、答辩状）可同时提供以丰富分析。

### 场景三：庭审笔录分析

对庭审笔录进行结构化复盘，输出争议焦点、证据质证、法官提问分析、策略建议。详见 [庭审笔录处理](references/hearing-transcript-extraction.md)。

### 领域扩展

通用处理框架适用于所有诉讼案件。现有专用领域扩展：

- **知识产权与不正当竞争**（参见 [references/domains/01-ip-case-dimensions.md](references/domains/01-ip-case-dimensions.md)）

## 使用方式

### 基于文件

```
/litigation-analysis @判决书路径.md
```

### 同时提供辅助文件

```
/litigation-analysis @判决书路径.md
同时提供：起诉状、答辩状等辅助文件
```

### 直接粘贴

```
/litigation-analysis
[粘贴判决书内容]
```

## 输出结构

**生成顺序**: 内部版 → 研究版 → 客户版（按依赖关系递进）

```
[案件编号]/
├── [案件编号] 深度分析报告内部版.md  ← 判决书深度分析
├── [案件编号] 研究课题清单.md        ← 识别的法律问题
└── [案件编号] 案件概览客户版.md      ← 简化呈现
```

**内部版核心**:
- 📋 核心要点速览：2-3分钟快速掌握案件全貌
- 事实与证据：完整的事实认定链条
- 争议焦点与法院认定：逐一对应分析
- 判决结果详解：判决主文、诉讼费用、上诉权利
- 法律分析与策略建议：上诉/再审可行性评估
- 裁判要点与实务启示：关键裁判规则、实务启示

## 参考文档

### 核心处理文档

- [起诉状与证据分析](references/complaint-evidence-extraction.md) - 诉讼起点的快速评估
  - 识别特征、抽取规范、处理流程、输出侧重
- [一审判决书处理](references/judgment-first-instance-extraction.md) - 一审判决的完整处理流程
  - 识别特征、抽取规范、处理流程、输出侧重
- [二审判决书处理](references/judgment-second-instance-extraction.md) - 二审判决的完整处理流程
  - 识别特征、抽取规范、对比分析、输出侧重

### 庭审笔录处理文档

- [庭审笔录处理](references/hearing-transcript-extraction.md) - 庭审笔录的完整处理流程
  - 识别特征、抽取规范、处理流程、输出格式
  - 生成庭审复盘分析报告，包含争议焦点、证据质证、法官提问、策略建议等

### 输出文档

- [客户版模板](templates/template-client.md) - 非法律专业人士通俗呈现
- [研究版模板](templates/template-research.md) - 研究课题清单生成
- [内部版模板](templates/template-internal.md) - 专业深度分析报告

### 可视化

- [可视化指南](references/visualization.md) - Mermaid 图表生成规范与示例
  - 当事人关系图、案件时间轴、争议焦点关系图、上诉策略决策图、侵权比对图

### 领域扩展

- [领域扩展指南](references/domains/) - IP/不正当竞争等专用分析维度

---

诉讼分析工具 - 聚焦判决书，支持上诉/再审决策
