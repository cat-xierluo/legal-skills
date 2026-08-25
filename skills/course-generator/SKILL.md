---
name: course-generator
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "2.8.0"
license: MIT
description: 从转录稿或文献生成可独立阅读、可溯源验收的结构化课程，也可在用户明确要求时归档既有课程或从已验证素材提取培训方案。本技能应在用户要“把长转录稿整理成课程”“生成总览和章节”“归档课程”“按受众定制课程方案”时使用。不要用于：仅做 ASR 纠错（用 transcription-corrector）、复盘讲课表现（用 lecture-review）、把多篇文章扩写成书（用 article2book）。
---

# Course Generator v2.8.0

## 选择模式

生成模式是主入口；归档和提取是显式后续动作，不因生成完成自动触发。

| 模式 | 何时进入 | 必需输入 | 主输出 |
|---|---|---|---|
| 生成 | 将转录稿、逐字稿或文献整理成课程 | 输入文件/目录、期望输出位置 | `00 + 章节 + course-manifest.json` |
| 归档 | 用户明确要求复制/移动到知识库 | 已生成课程、归档根目录、日期/课名 | 已验证的归档副本 |
| 提取 | 根据受众、时长和主题组合培训方案 | 需求描述、课程索引、既有课程素材 | 定制课程方案 |

若意图仍不明确，先根据输入判断；会改变文件位置、覆盖策略或课程边界时再追问。原始材料默认只读，生成模式不修改源文件。

## 共用边界

- **忠实可溯源**：数字、动作、后果、建议和专有名称可回到 `SRC-xxx` 定位；无法定位的内容不写成事实。
- **高价值素材不得净丢失**：案例、操作、踩坑、取舍和判断技巧要么进入章节，要么在 manifest 记录跳过理由；“去来源痕迹”只改叙述框架，不连带删素材。
- **读者成品与审计分离**：章节不显示原文区间、素材编号或生成来源；这些信息写入 `course-manifest.json` 和可选审计文件。
- **专名与图片保真**：英文产品名、Skill、命令、文件名保留原写法；正文图片使用 manifest 中的原始 Markdown。
- **客观项脚本验收，语义项人工复核**：验证器检查真实产物，不采信大纲或执行者自报；素材展开质量、跨章逻辑和事实忠实度仍由人工判断。

冲突时依次以忠实/可溯源、素材守恒、章节边界、书稿化表达、篇幅建议为准。篇幅只用于发现异常压缩，不作为硬性封顶或独立完成证据。

## 配置

- **生成模式**不要求 `config/paths.yaml`。优先使用用户指定输出目录；未指定时，在输入目录旁创建新课程目录，并在写入前说明位置。
- **用户词典**可选：复制 [user_dictionary.example.yaml](config/user_dictionary.example.yaml) 为本地 `config/user_dictionary.yaml`。只校正上下文明确的近似误转写，低置信内容保留原文。
- **归档/提取模式**需要路径时，复制 [paths.example.yaml](config/paths.example.yaml) 为本地 `config/paths.yaml`。本地配置由 `.gitignore` 排除。
- 目标目录已存在且含文件时，不静默覆盖；使用用户指定的新目录/版本目录，或先取得覆盖授权。

## 生成模式

流程：`盘点与索引 → 素材/图片登记 → 全局大纲 → 总览与章节 → manifest 定稿 → 确定性验收 → 人工复核 → 可选归档`

### 1. 盘点来源并选择读取策略

枚举用户指定范围内的 `.md` / `.txt` 文件，排除输出目录、隐藏缓存和明显重复副本。按稳定顺序分配 `SRC-001`、`SRC-002`……，记录相对输入根目录的路径。

- 材料能够在保留生成空间的前提下完整进入上下文时，可以直接整体分析。
- 多文件、超长转录或完整读取会挤压生成/复核空间时，使用索引化两遍流程：先按标题、时间段或稳定段落号分块并提取素材账本，再基于账本合并全局结构；不要强行一次性塞入全部原文。
- 分块边界不得切断一个连续问答、案例或三步以上操作链；确需切分时保留重叠上下文，并让相邻块引用同一稳定 source ref。

### 2. 建立素材账本与图片账本

逐段扫描材料。每个实质素材分配 `MAT-xxx`，记录类型、摘要、source ref、目标章节或跳过理由；每张 Markdown 图片跨文件连续分配 `IMG-xxx`，原样记录图片 Markdown、source ref、正文动作和目标文档。

素材分类、词典校正、图片价值判断和章节边界细则见 [outline_prompt.md](references/outline_prompt.md)。机器字段必须同步进入 [course-manifest.md](references/course-manifest.md) 定义的 manifest；`98 图片资产表.md`、`99 课程大纲.md` 只作为可选的人类审计视图，不是验证器的数据源。

### 3. 生成全局大纲

用完整来源索引、素材账本和必要原文片段生成大纲。按主题组织，不机械按文件切章；分流到其他章节的素材仍保留原 source ref 和目标章节。

通常组织为 3—8 章，但以真实主题与素材量为准。结构性薄章可以合并或明确标注素材偏少，不从其他章节复制内容凑篇幅。

### 4. 生成总览

读取 [overview_prompt.md](references/overview_prompt.md)，生成 `00 [课程名称] - 总览.md`。结构导览仅在材料确有流程、框架、能力模型或系统关系时加入。总览只插入 manifest 目标为 `OVERVIEW` 的图片。

### 5. 逐章生成

读取 [chapter_prompt.md](references/chapter_prompt.md)。每章只加载该章的 `material_ids`、`image_ids`、相关 source refs 和必要邻接上下文；长材料模式下不要再次读入全部原文。

每章完成后回扫对应 source refs：案例/操作/踩坑类不应只剩一句概述；正文中的数字、动作、结论和专名能定位；问答自然融入；不把讲者现场行为推广成材料没有的通用建议。

### 6. 保存规范产物

读者成品：

- `00 [课程名称] - 总览.md`
- `01 [主题].md`、`02 [主题].md`……

审计产物：

- `course-manifest.json`：强制，按 [course-manifest.md](references/course-manifest.md) 保存。
- `98 图片资产表.md`、`99 课程大纲.md`：可选；生成时在 manifest 的 `audit_files` 声明。

课程名称优先取自该项目的对外大纲或报价方案；没有正式课名时再基于素材拟名。生成目录日期不用冒充培训实际举办日期。

### 7. 运行确定性验收

保存全部产物后运行：

```bash
bash scripts/verify.sh <课程目录>
```

退出码 `0` 才表示客观门禁通过；`1` 表示产物不符合契约，按失败项修改后重跑；`2` 表示目录、运行环境或验证器异常，同样不得交付。脚本最后一行输出机器可读 JSON，并绑定 manifest 与读者文件 SHA-256。

验证器检查：manifest 结构、总览/章节存在且非空、未声明章节、素材双向映射、图片精确集合/目标/顺序、明显讲者转播口吻、来源框架词和可见审计元数据。旧版无 manifest 的课程不会被伪判通过；需要升级后再验收。

### 8. 完成人工语义复核

脚本通过后仍检查：

- **素材守恒**：抽查各章 `material_ids` 和跳过项；高价值素材未发生无理由净丢失。
- **忠实溯源**：抽查数字、动作链、建议、结果和专名；事实可回原文定位，推断有明显推论语气。
- **跨章一致性**：主题边界清楚、无大段重复、交叉引用章号正确。
- **图片语义价值**：图片位置确实支撑相邻论述，而非只满足数量。

向用户交付时分别报告“脚本验收结果”和“人工复核范围”，不得把客观 PASS 扩大为全量语义正确。

## 归档模式

仅在用户明确要求归档时执行：

1. 读取课程 manifest；旧课程无 manifest 时按旧命名盘点，并标注为 legacy/未通过 v2.8 验证。
2. 从用户材料确认培训实际日期、正式课名、归档根目录和主办方写法；不要用生成日期替代培训日期。
3. 默认复制，不默认移动；只有用户明确说“移动”时才移走源文件。
4. 目标已存在时不覆盖，先使用新版本目录或请求用户决定。
5. 复制后对目标目录重跑验证；源/目标文件集合或哈希不一致时归档失败。
6. 知识库已有索引且本次归档范围包含索引维护时，再更新索引。

## 提取模式

读取 [extract_prompt.md](references/extract_prompt.md)，按 `解析需求 → 匹配课程 → 定位已验证素材 → 提取重组 → 输出方案` 推进。

需求至少包含受众、基础水平、培训时长和重点方向。优先使用带 manifest 的课程，从 source refs 追踪素材；只有 raw 转录稿时先走生成模式。既有材料覆盖不了的主题必须标注“需补充素材”，不凭空补课。

## 权限与隐私

- 只读取用户指定的材料范围，只向用户指定或已说明的本地输出目录写文件。
- 验收会执行本 Skill 内的 `verify.sh` / `verify_course.py` 读取课程文件；脚本不联网、不安装依赖、不修改课程文件。`verify_selftest.py` 仅在开发验收时写入并自动清理系统临时目录。
- 本技能不需要网络、凭证或外部服务。
- 未脱敏转录稿、客户信息和课程材料按最小必要原则处理；公开示例、manifest 模板和变更记录不得写入真实客户信息或本机私有路径。

## 依赖

### 系统依赖

| 依赖 | 用途 | 安装方式 |
|---|---|---|
| `python3 >= 3.10` | 运行 manifest 领域验证器 | macOS: `brew install python`<br>Linux: `sudo apt-get install python3` |

### Python 包

无需第三方 Python 包，验证器仅使用标准库。

## 参考与脚本

- [outline_prompt.md](references/outline_prompt.md)：素材/图片账本与全局大纲。
- [overview_prompt.md](references/overview_prompt.md)：总览生成。
- [chapter_prompt.md](references/chapter_prompt.md)：章节书稿化生成与人工自检。
- [extract_prompt.md](references/extract_prompt.md)：提取模式。
- [course-manifest.md](references/course-manifest.md)：产物契约和最小示例。
- [course-manifest.schema.json](config/course-manifest.schema.json)：JSON Schema。
- [verify.sh](scripts/verify.sh)：验收入口。
- [verify_course.py](scripts/verify_course.py)：标准库领域验证器。
- [verify_selftest.py](scripts/verify_selftest.py)：故障注入回归套件。
