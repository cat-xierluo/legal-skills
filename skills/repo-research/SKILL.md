---
name: repo-research
description: GitHub 仓库深度研究与整合分析工具。支持单个/多个仓库研究、与本地项目对比分析、启发式整合建议。支持主题驱动搜索模式：自动搜索相关仓库、克隆、分析并生成报告。克隆远程仓库到本地 research/ 目录，进行深度代码分析、架构评估、依赖解析，并生成结构化研究报告。触发条件：用户提供 GitHub URL 请求研究/分析/整合/对比时，或提供主题关键词请求搜索并研究相关仓库时。
---

# Repo Research

GitHub 仓库深度研究工具，核心目标是从**外部项目中获取启发**，为用户自己的项目提供可操作的改进建议。

> **适用范围**：本技能适用于研究任何类型的 GitHub 仓库，不仅限于 Claude Skills。可用于研究开源项目、库、框架、工具等。

## 依赖管理

本技能的核心功能（单仓库/多仓库研究）**不需要**任何前置技能。

只有使用**主题驱动搜索模式**时，才需要以下可选依赖：

| 依赖技能 | 用途 | 安装源 | 必需性 |
|:---------|:-----|:-------|:-------|
| **find-skills** | 按主题搜索 GitHub 上的相关仓库 | `https://skills.sh/vercel-labs/skills/find-skills` | 可选 |

**使用说明**：
- 如果您直接提供 GitHub URL，本技能会直接使用现有的单/多仓库研究模式
- 如果您提供主题关键词（如"研究 OCR 相关项目"），本技能会：
  1. 首先检测 `find-skills` 是否已安装
  2. 如未安装，会提示您安装后再继续
  3. 安装后自动调用 `find-skills` 进行搜索

---

## 配置

本技能支持通过配置文件自定义输出目录和其他设置。

### 配置文件位置

```
skills/repo-research/assets/config.yaml
```

### 快速配置

1. 复制示例配置：
```bash
cp skills/repo-research/assets/config.example.yaml skills/repo-research/assets/config.yaml
```

2. 编辑 `config.yaml`，设置你的输出目录：
```yaml
research:
  output_dir: "~/Documents/研究笔记"  # 支持绝对路径、相对路径、~ 展开
```

### 配置项说明

| 配置项 | 说明 | 默认值 |
|:-------|:-----|:-------|
| `research.output_dir` | 研究报告输出目录 | `./research` |
| `research.report_format` | 报告格式 | `markdown` |
| `research.shallow_clone` | 使用浅克隆 | `true` |
| `security.enabled` | 启用安全分析 | `true` |
| `security.prompt_analysis` | 提示词安全检测 | `true` |

### 配置读取逻辑

```
1. 检查 skills/repo-research/assets/config.yaml 是否存在
2. 如果存在，读取配置
3. 如果 output_dir 为空或不存在，使用默认值 ./research
4. 支持路径展开：
   - `~` 展开为用户目录
   - 相对路径基于当前工作目录
```

### 默认行为（无配置文件）

如果没有配置文件或 `output_dir` 为空，将使用默认行为：
- **输出目录**：`./research`（当前工作目录下的 research 文件夹）
- **报告格式**：Markdown
- **安全分析**：启用

---

## 快速开始

```bash
# 单个仓库研究
/repo-research https://github.com/user/repo

# 多仓库对比研究
/repo-research https://github.com/user/repo-a https://github.com/user/repo-b

# 指定分析重点
/repo-research https://github.com/user/repo --focus=architecture

# 与现有技能整合
/repo-research https://github.com/user/repo --integrate-with=de-ai-polish
```

**对话中触发**：当用户提到"研究一下这个仓库"、"对比分析这些项目"、"对我项目有什么启发"等类似表述时自动激活。

---

## 配置

### 配置文件

本技能支持通过配置文件自定义输出目录等设置。

#### 配置文件位置

```
~/.openclaw/skills/repo-research/assets/config.yaml
```

#### 配置示例

```yaml
# 研究报告输出目录
# 支持绝对路径、相对路径和 ~ 展开
output_dir: "/Users/yourname/Desktop/Clawd/99 - 🦐 大虾研究/09 - 📋 研究报告"

# 报告格式：markdown 或 json
report_format: markdown

# 是否自动打开报告（生成后）
auto_open_report: false

# 克隆深度：1 = 浅克隆（更快），0 = 完整克隆
clone_depth: 1
```

#### 环境变量覆盖

配置也可通过环境变量设置（优先级高于配置文件）：

| 环境变量 | 说明 |
|:---------|:-----|
| `REPO_RESEARCH_OUTPUT_DIR` | 输出目录 |
| `REPO_RESEARCH_FORMAT` | 报告格式 |
| `REPO_RESEARCH_AUTO_OPEN` | 是否自动打开 |
| `REPO_RESEARCH_CLONE_DEPTH` | 克隆深度 |

#### 输出目录结构

```
output_dir/
└── research/
    └── YYYYMMDD-topic-slug/
        ├── repo-name/                    # 克隆的仓库
        ├── repo-name-2/                  # 多仓库时有多个
        └── topic-slug-report.md          # 研究报告（如：twitter-skills-report.md）
```

---

## 工作流程

### 模式选择

根据输入自动选择研究模式：

| 输入类型 | 研究模式 | 输出 |
|:---------|:---------|:-----|
| 单个 GitHub URL | **单仓库深度研究** | 单仓库分析报告 + 启发建议 |
| 多个 GitHub URL | **多仓库对比研究** | 对比分析报告 + 共性启发 |
| GitHub URL + 本地路径 | **对比启发模式** | 差异分析 + 改进建议 |
| 主题/关键词 | **主题驱动搜索研究** | 搜索结果 + 多仓库综合分析报告 |

---

## 主题驱动搜索研究模式

当用户提供主题关键词而非具体 GitHub URL 时，使用此模式。

### 触发条件

用户表达以下需求时自动激活：
- "帮我找关于 X 的相关项目"
- "搜索研究一下主题 X"
- "找一些关于 X 的开源项目"
- "主题 X 有什么值得研究的仓库"

### 工作流程

#### Step 0: 依赖检查

```bash
# 检查 find-skills 是否已安装
if ! /find-skills --help >/dev/null 2>&1; then
    echo "⚠️  主题驱动搜索模式需要 find-skills 技能"
    echo "正在为您安装..."
    /skill-manager install https://skills.sh/vercel-labs/skills/find-skills
fi
```

**对话提示**：
> "检测到您需要使用主题搜索功能。正在检查依赖..."

#### Step 1: 使用 find-skills 搜索相关仓库

调用 find-skills 技能进行搜索：

```bash
/find-skills <主题关键词>
```

示例：
- `/find-skills pdf converter` - 搜索 PDF 转换相关技能
- `/find-skills video transcription` - 搜索视频转录相关技能
- `/find-skills ocr` - 搜索 OCR 相关技能

#### Step 2: 整理搜索结果

从 find-skills 的返回中提取：
1. **仓库名称**
2. **GitHub URL**
3. **简要描述**
4. **相关度评分**

**搜索结果整理格式**：

| # | 仓库名 | URL | 描述 | 相关度 |
|:-|:-------|:----|:-----|:-------|
| 1 | [name] | [url] | [描述] | ⭐⭐⭐⭐⭐ |
| 2 | [name] | [url] | [描述] | ⭐⭐⭐⭐☆ |

#### Step 3: 用户确认筛选

**对话询问**：
> "找到 [N] 个相关仓库。请选择要深入研究的项目："
> "1. 研究全部 [N] 个仓库"
> "2. 选择特定编号（如：1,3,5）"
> "3. 只研究前 [K] 个最相关的"
> "4. 自定义选择"

根据用户选择确定最终研究列表。

#### Step 4: 批量克隆与并行分析

##### 4.1 创建研究目录

**⚠️ 重要**：优先使用配置文件中的 `output_dir`，如果未配置则使用当前工作目录。

**Python 方式（推荐）**：

```python
from scripts.config import get_research_dir

# 自动读取配置文件，返回研究目录路径
RESEARCH_DIR = get_research_dir(topic_slug)
```

**Bash 方式（向后兼容）**：

```bash
# 优先使用配置文件中的 output_dir，否则使用当前目录
SKILL_DIR="$HOME/.openclaw/skills/repo-research"
CONFIG_FILE="$SKILL_DIR/assets/config.yaml"

# 尝试从配置文件读取 output_dir
if [ -f "$CONFIG_FILE" ] && command -v python3 &> /dev/null; then
    OUTPUT_DIR=$(python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, '$SKILL_DIR/scripts')
from config import get_output_dir
print(get_output_dir())
" 2>/dev/null)
else
    OUTPUT_DIR="${PWD}"
fi

RESEARCH_DATE=$(date +%Y%m%d)
# 将主题转换为 slug 格式（小写、空格替换为连字符）
TOPIC_SLUG=$(echo "$TOPIC" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')

# 使用绝对路径确保在正确位置
RESEARCH_DIR="${OUTPUT_DIR}/research/${RESEARCH_DATE}-${TOPIC_SLUG}"
mkdir -p "${RESEARCH_DIR}"
cd "${RESEARCH_DIR}"
```

##### 4.2 批量克隆

```bash
for url in "${SELECTED_URLS[@]}"; do
    repo_name=$(basename "$url" .git)
    echo "正在克隆: $repo_name"
    git clone --depth 1 "$url" "$repo_name"
done
```

##### 4.3 并行分析

对每个克隆的仓库执行基础分析（参见"Step 2: 基础分析"）。

#### Step 5: 生成主题综合报告

使用 `assets/topic-research-template.md` 作为模板。

##### 报告结构

```markdown
# [主题] 综合研究报告

> **研究日期**：YYYY-MM-DD
> **搜索主题**：[主题关键词]
> **研究仓库数**：[N] 个
> **报告路径**：`./research/YYYYMMDD-[topic-slug]/[topic-slug]-report.md`

---

## 执行摘要

### 研究概述

[用一段话概括：基于主题搜索了哪些类型的仓库，主要发现了什么]

### 一句话总结

[用一句话概括最关键的发现]

### 核心指标

| 指标 | 数值 |
|:-----|:-----|
| 搜索结果总数 | [N] 个仓库 |
| 深度研究数量 | [M] 个仓库 |
| 相关技术栈 | [列举主要技术] |
| 活跃项目占比 | [X%] |

---

## 搜索结果概览

### 仓库清单

| # | 仓库名 | 描述 | 语言 | Stars | 活跃度 |
|:-|:-------|:-----|:-----|:-----|:-------|
| 1 | [name] | [描述] | [lang] | [★] | 🟢 活跃 |
| 2 | [name] | [描述] | [lang] | [★] | 🟡 中等 |

### 分类汇总

**按技术类型**：
- [技术1]: [数量] 个项目
- [技术2]: [数量] 个项目

**按功能类型**：
- [功能1]: [数量] 个项目
- [功能2]: [数量] 个项目

---

## 技术栈分析

### 主流技术选择

| 技术 | 使用项目数 | 占比 | 代表项目 |
|:-----|-----------|:-----|:---------|
| [技术1] | [N] | [X%] | [项目A, 项目B] |
| [技术2] | [N] | [X%] | [项目C] |

### 技术趋势洞察

- **趋势1**：[描述观察到的技术趋势]
- **趋势2**：[描述观察到的技术趋势]

---

## 共性模式识别

### 架构共性

多个项目共同采用的架构模式：
1. **[模式名称]**：[描述]
   - 采用项目：[列举]
   - 优势分析：[分析]

### 功能共性

多个项目都实现的核心功能：
1. **[功能名称]**：[描述]
   - 实现方式差异：[对比]

### 文档共性

文档编写的共同特点：
- [观察到的文档模式]

---

## 项目对比分析

### 功能对比矩阵

| 功能 | 项目1 | 项目2 | 项目3 | 最优实现 |
|:-----|:-----|:-----|:-----|:---------|
| [功能1] | ✅ | ✅ | ❌ | [分析] |
| [功能2] | ✅ | ❌ | ✅ | [分析] |

### 架构对比

| 维度 | 项目1 | 项目2 | 项目3 | 值得学习 |
|:-----|:-----|:-----|:-----|:---------|
| 目录结构 | [描述] | [描述] | [描述] | [推荐] |
| 模块化 | [描述] | [描述] | [描述] | [推荐] |

### 代码质量对比

| 项目 | 代码组织 | 文档 | 测试 | 综合评分 |
|:-----|:---------|:-----|:-----|:---------|
| 项目1 | ⭐⭐⭐⭐☆ | ⭐⭐⭐☆☆ | ⭐⭐☆☆☆ | B+ |
| 项目2 | ⭐⭐⭐☆☆ | ⭐⭐⭐⭐☆ | ⭐⭐⭐☆☆ | B |

---

## 深度剖析（精选项目）

### 项目 A: [仓库名]

#### 为什么值得深入研究

[说明选择这个项目进行深度剖析的原因]

#### 架构亮点

- [亮点1]
- [亮点2]

#### 可借鉴的设计

1. **[设计点1]**：[描述可借鉴之处]
2. **[设计点2]**：[描述可借鉴之处]

### 项目 B: [仓库名]

[同上结构]

---

## 启发与建议

### 对本地项目的启发

#### 可直接借鉴

1. **[方面1]**
   - **来源**：[项目A/项目B]
   - **做法**：[描述具体做法]
   - **本地应用**：[如何应用到本地项目]
   - **优先级**：🔴 高 / 🟡 中 / 🟢 低
   - **预计工作量**：[X 小时]

#### 需要进一步探索

1. **[技术/模式]**
   - **为什么**：[说明价值]
   - **调研方式**：[如何调研]
   - **预期收益**：[说明]

### 最佳实践总结

从多个项目中提炼的最佳实践：
1. **[实践1]**：[描述]
2. **[实践2]**：[描述]

---

## 项目推荐

### 不同场景推荐

| 场景 | 推荐项目 | 理由 |
|:-----|:---------|:-----|
| 学习参考 | [项目名] | [理由] |
| 生产使用 | [项目名] | [理由] |
| 二次开发 | [项目名] | [理由] |
| 特定需求 | [项目名] | [理由] |

### 快速决策指南

- **如果你需要 X** → 推荐 [项目A]
- **如果你需要 Y** → 推荐 [项目B]
- **如果你需要 Z** → 推荐 [项目C]

---

## 附录

### 完整仓库列表

#### 深度研究的项目

1. **[项目名]** - [GitHub URL]
   - 描述：[描述]
   - 技术栈：[列举]
   - 最后更新：[日期]

#### 仅浏览的项目

1. **[项目名]** - [GitHub URL]
   - 相关度：⭐⭐☆☆☆

### 参考资源

- [相关文档链接]
- [相关文章链接]

---

**报告生成时间**：YYYY-MM-DD HH:MM
**研究者**：Claude Code + repo-research skill
**搜索工具**：find-skills skill
```

#### Step 6: 会话汇报

```markdown
## 主题研究完成

**搜索主题**：[主题关键词]

**搜索结果**：找到 [N] 个相关仓库，深度分析了 [M] 个

**核心发现**：
1. [发现1]
2. [发现2]
3. [发现3]

**推荐项目**：
- 学习参考：[项目A]
- 生产使用：[项目B]

**详细报告已保存至**：`./research/YYYYMMDD-[topic-slug]/[topic-slug]-report.md`
```

---

## 原有研究模式

（以下保持原有内容不变...）

### Step 1: 准备研究环境

#### 1.0 读取配置文件

**⚠️ 重要**：首先读取配置文件确定输出目录。

```python
# 读取配置文件逻辑（在开始研究前执行）
import yaml
from pathlib import Path

def get_output_dir():
    """获取输出目录，优先使用配置文件中的设置"""

    # 默认输出目录
    default_output = "./research"

    # 配置文件路径
    skill_dir = Path(__file__).parent  # skill 所在目录
    config_path = skill_dir / "assets" / "config.yaml"

    if not config_path.exists():
        return default_output

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        output_dir = config.get('research', {}).get('output_dir', '')

        if not output_dir or output_dir.strip() == '':
            return default_output

        # 展开 ~ 和环境变量
        output_dir = Path(output_dir).expanduser()

        # 如果是相对路径，基于当前工作目录
        if not output_dir.is_absolute():
            output_dir = Path.cwd() / output_dir

        return str(output_dir)

    except Exception:
        return default_output
```

#### 1.1 创建研究目录

**统一目录结构**：

```bash
research/
└── YYYYMMDD-[topic]/    # 日期+主题目录
    ├── repo-name/       # 研究的仓库（即使是单个仓库也在子目录中）
    ├── repo-b/          # 多仓库时会有多个子目录
    └── [topic-slug]-report.md        # 研究报告

# 单仓库示例：
# ~/Documents/研究笔记/20260213-vibe-working-tutorial/
#     └── vibe-working-tutorial/   <- 仓库内容
#     └── [topic-slug]-report.md

# 多仓库示例：
# ./research/20260213-pdf-tools-comparison/
#     ├── pdf-lib/
#     └── pdfkit/
#     └── [topic-slug]-report.md
```

> **设计原则**：无论研究多少个仓库，都保持 `${OUTPUT_DIR}/日期-主题/仓库名/` 的统一结构，便于后续管理和扩展。

**命名格式**：`YYYYMMDD-[topic-slug]`
- `topic-slug`：主题关键词，用连字符连接，小写
- 示例：`20260211-pdf-ocr-comparison`、`20260212-transcription-study`

**主题来源**（优先级从高到低）：
1. **用户指定**：调用时通过 `--topic` 参数提供
2. **对话询问**：自动询问用户输入简短的主题描述
3. **自动推断**：从仓库名称或研究内容推断（备选）

使用 Bash 工具执行：

**⚠️ 重要**：
1. 首先读取 `skills/repo-research/assets/config.yaml` 获取 `output_dir`
2. 如果配置文件不存在或 `output_dir` 为空，使用默认值 `./research`
3. 路径支持 `~` 展开和相对路径

```bash
# Step 1: 读取配置文件获取输出目录
# 默认输出目录
OUTPUT_DIR="./research"

# 检查配置文件是否存在
CONFIG_FILE="skills/repo-research/assets/config.yaml"
if [ -f "$CONFIG_FILE" ]; then
    # 使用 grep 简单提取 output_dir（避免依赖 Python/yaml）
    CONFIG_OUTPUT=$(grep -E "^\s*output_dir:" "$CONFIG_FILE" | head -1 | sed 's/.*output_dir:[[:space:]]*//')
    # 移除引号
    CONFIG_OUTPUT=$(echo "$CONFIG_OUTPUT" | tr -d "\"'")
    # 如果非空，使用配置值
    if [ -n "$CONFIG_OUTPUT" ] && [ "$CONFIG_OUTPUT" != '""' ]; then
        # 展开 ~ 为用户目录
        OUTPUT_DIR="${CONFIG_OUTPUT/#\~/$HOME}"
    fi
fi

# Step 2: 如果是相对路径，基于当前工作目录
if [[ "$OUTPUT_DIR" != /* ]]; then
    OUTPUT_DIR="${PWD}/${OUTPUT_DIR}"
fi

# Step 3: 创建研究目录
REPO_DATE=$(date +%Y%m%d)
TOPIC_SLUG=$(echo "$TOPIC" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')

RESEARCH_DIR="${OUTPUT_DIR}/${REPO_DATE}-${TOPIC_SLUG}"
mkdir -p "${RESEARCH_DIR}"
cd "${RESEARCH_DIR}"

echo "研究目录已创建: ${RESEARCH_DIR}"
```

**对话询问主题**：
> "请为本次研究提供一个简短的主题描述（用于目录命名，如 `pdf-ocr`、`agent-framework`）："

#### 1.2 克隆仓库

**⚠️ 重要**：无论是单仓库还是多仓库，都统一克隆到子目录中，保持目录结构一致。

```bash
# 统一方式：所有仓库都克隆到子目录
# 这样可以保持 research/日期-主题/ 目录结构的一致性
# 单仓库和多仓库的区别只在于克隆的次数

for url in "${URLS[@]}"; do
    repo_name=$(basename "$url" .git)
    git clone --depth 1 "$url" "$repo_name"
done

# 单仓库示例（实际也是克隆到子目录）：
# research/20260213-vibe-working-tutorial/
#     └── vibe-working-tutorial/   <- 仓库内容
#     └── [topic-slug]-report.md                <- 研究报告

# 多仓库示例：
# research/20260213-pdf-tools-comparison/
#     └── pdf-lib/                 <- 仓库A
#     └── pdfkit/                  <- 仓库B
#     └── [topic-slug]-report.md                <- 研究报告
```

---

### Step 2: 基础分析（对每个仓库）

#### 2.1 识别项目类型

| 特征 | 项目类型 | 分析重点 |
|:-----|:---------|:---------|
| `package.json` | Node.js/前端 | 依赖、脚本、构建配置 |
| `requirements.txt`/`pyproject.toml` | Python | 虚拟环境、依赖管理 |
| `go.mod` | Go | 模块结构、依赖 |
| `Cargo.toml` | Rust | Edition、特性、依赖 |
| `SKILL.md` | Claude Skill | 技能定义、frontmatter |

#### 2.2 核心文件优先阅读

```bash
# 必读文件（按优先级）
README.md          # 项目说明、快速开始
LICENSE            # 许可证
package.json/pyproject.toml/go.mod  # 依赖元数据
```

#### 2.3 项目结构分析

使用 Glob 工具探索：

```bash
glob "**/*"           # 所有文件
glob "**/*.md"        # 文档
glob "src/**/*.ts"    # 源代码
glob "tests/**/*"     # 测试
```

#### 2.4 技术栈识别

- **前端**：React/Vue/Svelte/Next.js/Nuxt + 状态管理 + 样式方案
- **后端**：Node.js/Python/Go/Rust + 框架 + ORM
- **工具链**：Vite/Webpack + Jest/Pytest + ESLint/Prettier

---

### Step 3: 多仓库对比分析（多仓库模式）

#### 3.1 对比维度

| 维度 | 对比内容 | 启发点 |
|:-----|:---------|:-------|
| **架构设计** | 目录结构、模块划分 | 有哪些组织方式值得借鉴 |
| **功能实现** | 核心功能、API 设计 | 同类功能的不同实现方式 |
| **技术选型** | 框架、依赖、工具链 | 为什么选择这些技术 |
| **文档质量** | README、注释、API 文档 | 文档写法的差异 |
| **代码风格** | 命名、结构、模式 | 哪种风格更清晰 |

#### 3.2 共性提取

识别多个仓库的共同点：
- 共同的技术选择（如都用 Markdown 作为格式）
- 共同的设计模式（如都用插件架构）
- 共同的问题解决方式

#### 3.3 差异分析

识别关键差异及其原因：
- 为什么 A 用 Markdown 而 B 用 JSON
- 为什么 A 有测试而 B 没有
- 不同实现方式的优劣

---

### Step 4: 本地项目对比（启发模式）

#### 4.1 识别本地项目

**对话中询问**：
> "是否需要与本地项目进行对比？如果有，请提供项目路径（相对或绝对）。"

常见本地项目类型：
- `./test/de-ai-polish` - 本地技能
- `./skills/xxx` - 现有技能
- `./test/yyy` - 测试项目

#### 4.2 差异分析框架

| 分析项 | 外部仓库 | 本地项目 | 差异 | 启发 |
|:-------|:---------|:---------|:-----|:-----|
| **目录结构** | [描述] | [描述] | [差异点] | [可借鉴之处] |
| **核心功能** | [描述] | [描述] | [差异点] | [可补充之处] |
| **文档方式** | [描述] | [描述] | [差异点] | [可改进之处] |
| **检测规则** | [列举] | [列举] | [差异点] | [可学习之处] |

#### 4.3 启发式问题

在对比时回答以下问题：

1. **功能方面**
   - 外部仓库有哪些功能是我没有的？
   - 我有哪些功能是外部仓库没有的？
   - 哪些功能可以整合进来？

2. **架构方面**
   - 外部仓库的目录结构是否更清晰？
   - 模块划分方式是否值得借鉴？
   - 配置方式是否更灵活？

3. **实现方面**
   - 检测规则的组织方式有什么不同？
   - 报告生成的格式有什么优劣？
   - 用户交互方式有什么可学习之处？

4. **文档方面**
   - README 的结构是否更易理解？
   - 示例是否更丰富？
   - API 文档是否更完整？

---

### Step 5: 生成报告

#### 5.1 单仓库报告结构

使用 `assets/report-template.md` 作为模板。

#### 5.2 多仓库对比报告结构

使用 `assets/comparison-template.md` 作为模板。

#### 5.3 启发式报告结构

```markdown
# [研究主题] 启发式分析报告

> 研究日期：YYYY-MM-DD
> 研究仓库：[列出所有仓库]
> 对比项目：[本地项目路径]
> 报告路径：`./research/YYYYMMDD-[topic-slug]/[topic-slug]-report.md`

---

## 核心发现

### 一句话总结

[用一句话概括最关键的启发]

---

## 对比分析

### 功能对比

| 功能 | 仓库A | 仓库B | 本地项目 | 启发 |
|:-----|:------|:------|:---------|:-----|
| [功能1] | ✅ | ✅ | ❌ | [建议] |
| [功能2] | ✅ | ❌ | ✅ | [分析] |

### 架构对比

| 维度 | 仓库A | 仓库B | 本地项目 | 启发 |
|:-----|:------|:------|:---------|:-----|
| 目录结构 | [描述] | [描述] | [描述] | [建议] |
| 模块划分 | [描述] | [描述] | [描述] | [建议] |

### 规则/检测方式对比

| 检测项 | 仓库A | 仓库B | 本地项目 | 启发 |
|:-------|:------|:------|:---------|:-----|
| [规则1] | [实现] | [实现] | [实现] | [可学习] |

---

## 具体启发

### 可直接借鉴的方面

1. **[方面1]**
   - **外部做法**：[描述]
   - **本地现状**：[描述]
   - **改进建议**：[具体建议]
   - **优先级**：高/中/低

2. **[方面2]**
   - **外部做法**：[描述]
   - **本地现状**：[描述]
   - **改进建议**：[具体建议]
   - **优先级**：高/中/低

### 需要进一步探索的方面

1. **[方面1]**：[为什么值得探索]
2. **[方面2]**：[为什么值得探索]

---

## 行动建议

### 立即可做的改进

- [ ] [改进1] - 预计时间：[X小时]
- [ ] [改进2] - 预计时间：[X小时]

### 需要进一步调研的

- [ ] [调研项1] - 调研方式：[如何调研]
- [ ] [调研项2] - 调研方式：[如何调研]

---

## 附录

### 仓库详细信息

- **仓库A**：[名称](URL) - [一句话描述]
- **仓库B**：[名称](URL) - [一句话描述]

### 参考链接

- [相关文档]
- [相关文章]
```

#### 5.4 会话汇报格式

```markdown
## 研究完成

**研究仓库**：
- [仓库名A]：[一句话描述]
- [仓库名B]：[一句话描述]

**对比项目**：[本地项目路径]

**核心启发**：
1. [启发1]
2. [启发2]
3. [启发3]

**立即可做的改进**：
- [ ] [改进1]
- [ ] [改进2]

**详细报告已保存至**：`./research/YYYYMMDD-[topic-slug]/[topic-slug]-report.md`
```

---

## 最佳实践

### 研究策略

1. **启发优先**：研究的最终目的是"对我有什么帮助"
2. **对比驱动**：通过对比发现差异，通过差异获得启发
3. **具体可操作**：启发必须转化为具体的改进建议

### 启发提炼原则

1. **从差异中学习**：不同的实现方式往往有不同的考量
2. **从共性中总结**：多个仓库的共同选择往往有其原因
3. **从细节中洞察**：小细节可能反映设计理念

---

## Resources

### assets/

- **report-template.md**: 单仓库报告模板
- **comparison-template.md**: 多仓库对比报告模板
- **topic-research-template.md**: 主题驱动搜索研究报告模板（新增）

---

## 高级功能 (v0.4.0)

借鉴 Zread MCP 的实现思路，增强本地分析能力。

### 1. 代码语义搜索

利用本地已克隆的仓库，进行深度代码搜索。

#### 触发方式

用户表达以下需求时激活：
- "搜索函数 X"
- "查找类 Y"
- "看看这个项目怎么实现 Z 的"
- 直接使用 `--search` 参数

#### 使用方法

```bash
# 搜索函数定义
/repo-research https://github.com/user/repo --search="function:parse*"

# 搜索类定义
/repo-research https://github.com/user/repo --search="class:*Handler"

# 搜索导入
/repo-research https://github.com/user/repo --search="import:react"

# 搜索特定模式
/repo-research https://github.com/user/repo --search="pattern:console\.log"
```

#### 内部实现

调用 `scripts/search.py` 中的 `CodeSearcher` 类：
- 使用 Grep 工具进行模式匹配
- 支持多种语言：Python, JavaScript, TypeScript, Go, Rust, Java
- 支持多种模式：function, class, import, doc, pattern

---

### 2. 深度代码分析

超越基础分析，提供架构和质量层面的深度洞察。

#### 分析类型

| 类型 | 描述 | 触发参数 |
|:-----|:-----|:---------|
| **架构分析** | 目录结构、模块划分、入口文件、架构模式 | `--analyze=architecture` |
| **质量分析** | 代码统计、注释率、技术债务、潜在问题 | `--analyze=quality` |
| **完整分析** | 包含架构和质量两个维度 | `--analyze=full` |

#### 使用方法

```bash
# 架构分析
/repo-research https://github.com/user/repo --analyze=architecture

# 质量分析
/repo-research https://github.com/user/repo --analyze=quality

# 完整分析
/repo-research https://github.com/user/repo --analyze=full
```

#### 内部实现

- **架构分析器** (`scripts/analyzer/architecture.py`):
  - 目录结构分析
  - 入口文件识别
  - 模块/包结构识别
  - 配置文件检测
  - 架构模式检测（MVC、微服务、插件、monorepo）

- **质量分析器** (`scripts/analyzer/quality.py`):
  - 代码统计（行数、语言分布）
  - 注释覆盖率分析
  - 技术债务检测（TODO、FIXME、deprecated）
  - 问题检测（硬编码密钥、console.log、大文件）

---

### 3. 智能问答

利用 Claude Code 的 LLM 能力，回答关于仓库的自然语言问题。

#### 触发方式

用户表达以下需求时激活：
- "这个项目是做什么的？"
- "如何使用这个项目？"
- "架构是怎样的？"
- "有哪些主要模块？"
- 直接使用 `--ask` 参数

#### 使用方法

```bash
# 询问项目概述
/repo-research https://github.com/user/repo --ask="这个项目是做什么的？"

# 询问使用方法
/repo-research https://github.com/user/repo --ask="如何使用这个项目？"

# 询问架构
/repo-research https://github.com/user/repo --ask="架构是怎样的？"
```

#### 内部实现

1. **问题分类** (`scripts/qa.py` 中的 `QuestionClassifier`):
   - 意图识别：overview, architecture, usage, api, dependencies
   - 实体提取：功能名、组件名、文件名
   - 上下文确定：需要读取哪些文件

2. **回答生成**:
   - 使用 Grep/Glob 搜索相关代码
   - 使用 read_file 读取关键文件
   - 结合 Claude Code 的 LLM 能力生成自然语言回答

---

### 4. 组合使用

高级功能可以组合使用，实现更强大的分析能力：

```bash
# 搜索 + 分析
/repo-research https://github.com/user/repo --search="function:parse*" --analyze=architecture

# 问答 + 报告
/repo-research https://github.com/user/repo --ask="这个项目如何使用？" --output=report
```

---

### scripts/ 目录结构

```
scripts/
├── __init__.py           # 模块导出
├── search.py             # 语义搜索
├── qa.py                 # 智能问答
├── architecture.py       # 架构分析
├── quality.py            # 质量分析
└── security.py           # 安全分析 (v0.5.0 新增)
```

---

## 安全分析模块 (v0.5.0)

基于 OWASP Agentic AI Top 10 和常见漏洞模式设计，用于识别 skill 中可能存在的恶意代码或安全隐患。

### 触发方式

```bash
# 安全分析模式
/repo-research https://github.com/user/skill --analyze=security

# 完整分析（包含安全）
/repo-research https://github.com/user/skill --analyze=full
```

### 检测能力

| 类别 | 检测内容 | 风险等级 |
|:-----|:---------|:---------|
| **命令执行** | `os.system`, `subprocess`, `eval()`, `exec()` | 🔴 高 |
| **敏感文件访问** | 读写 `~/.ssh/`, `~/.aws/`, `.env` 等 | 🔴 高 |
| **网络外泄** | HTTP POST、WebSocket、数据上传 | 🟡 中 |
| **代码混淆** | `base64.b64decode`, `chr()` 拼接等 | 🔴 高 |
| **权限提升** | `sudo`, `chmod 777`, 修改 PATH | 🔴 高 |
| **硬编码凭证** | API Key、Token、Password | 🔴 高 |
| **下载执行** | `curl | bash`, `wget | sh` 模式 | 🔴 高 |
| **持久化** | crontab, systemd, LaunchAgents | 🟡 中 |
| **Skill 特有** | 安装钩子、MCP 服务器风险 | 🟡 中 |

### 风险等级

| 等级 | 条件 | 建议 |
|:-----|:-----|:-----|
| 🔴 **critical** | 存在命令执行、下载执行等 | 强烈不建议使用，需完整审计 |
| 🟠 **high** | 多个高危发现或硬编码凭证 | 审计后使用，限制权限 |
| 🟡 **medium** | 少量中危发现 | 使用前检查，测试环境验证 |
| 🟢 **low** | 仅低危或无发现 | 可安全使用 |

### 使用示例

```bash
# 分析一个 skill 的安全性
/repo-research https://github.com/example/skill --analyze=security

# 在研究报告对话框中，会自动包含安全分析章节
# 如果检测到高风险，会有明显的警告提示
```

### 未来计划

- [ ] 依赖分析模块 (dependency analysis)
- [ ] 性能分析模块 (performance analysis)
- [ ] 更智能的问答系统
