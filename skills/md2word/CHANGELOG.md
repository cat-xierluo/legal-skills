# 更新日志

本文件记录 md2word 技能的所有重要变更。

## [0.4.1] - 2026-02-11

### 修复

- **导入错误修复**: 修复模块化重构后导致的 `ImportError: cannot import name 'get_config' from 'config'`

  - 将 `get_config()` 和 `set_config()` 函数从 `md2word.py` 移至 `config.py`
  - 这些函数被所有子模块（formatter.py, table_handler.py, chart_handler.py）依赖，应属于配置管理模块
  - 修复了 v0.4.0 重构时引入的循环导入问题

## [0.4.0] - 2026-02-10

### 重构
- **脚本模块化拆分**: 将 1955 行的单文件脚本拆分为 4 个模块
  - `md2word.py`: 主入口 + 核心转换流程（800 行，减少 59%）
  - `formatter.py`: 文本/段落格式化模块（388 行）
  - `table_handler.py`: 表格处理模块（532 行）
  - `chart_handler.py`: 图表渲染模块（248 行）
  - 便于扩展新的图表类型支持

- **依赖清理**: 移除冗余导入
  - 移除未使用的 `sys`, `requests`, `base64`, `io` 等模块
  - 移除未使用的 `WD_TAB_ALIGNMENT` 等 docx 枚举
  - `BeautifulSoup` 移至 table_handler.py

## [0.3.0] - 2026-02-10

### 变更
- **Skill 结构重构**: 按照 Skill 开发指南最佳实践重构
  - 新增 `references/` 目录，实现渐进式披露
  - 新增 `references/config-reference.md`：配置架构快速参考
  - 新增 `references/examples.md`：使用示例和常见场景
  - 精简 SKILL.md（从 ~350 行减至 ~90 行）
  - 简化 `scripts/md2word.py` 头部注释
  - 移除 `scripts/requirements.txt`（依赖在 SKILL.md 中说明）

- **描述更新**: SKILL.md frontmatter description 更新为更通用的表述
  - 去除"法律文书"的限定性描述
  - 改为"符合中文排版标准的专业格式"
  - 强调适用于正式文档、论文、报告等多种场景

### 改进
- 配置参考文档指向 `assets/presets/*.yaml` 避免重复
- 参考文档与 SKILL.md 通过链接实现渐进式披露
- 文档结构更清晰，便于维护和扩展
- 移除 references 文档中的目录，保持简洁

## [0.2.1] - 2026-02-10

### 修复
- **引号转换修复**: 修复英文引号转中文引号的左右配对问题
  - 将"上下文感知"逻辑改为更可靠的"交替状态机"方法
  - 修复了连续引号都变成闭引号的bug
  - 修复了部分引号未被正确转换的问题
  - 使用Unicode转义序列避免Python语法警告

### 变更
- **文档中文化**: SKILL.md 和 CHANGELOG.md 完全中文化
  - frontmatter 的 name 和 description 改为中文
  - 版本记录标题翻译（Added → 新增，Changed → 变更等）

## [0.2.0] - 2026-01-29

### 新增
- **配置系统增强**: 添加完整的配置选项到 YAML 模板和预设文件
  - 代码块格式配置: 语言标签、内容字体、缩进、行距
  - 行内代码格式配置: 字体、字号、颜色
  - 引用块格式配置: 背景色、缩进、字号
  - 数学公式格式配置: 字体、字号、斜体、颜色
  - 图片设置配置: 显示比例、最大宽度、目标DPI
  - 分割线设置配置: 字符、重复次数、字体、颜色
  - 列表设置配置: 无序列表、有序列表、任务列表标记
  - 表格增强配置: 行高、单元格边距、垂直对齐、标题/正文格式

### 变更
- **md2word.py**: 重构所有格式化函数使用配置读取
  - `add_horizontal_line()`: 使用 `horizontal_rule` 配置
  - `add_code_block()`: 使用 `code_block` 配置
  - `add_quote()`: 使用 `quote` 配置
  - `add_bullet_list()`, `add_task_list()`: 使用 `lists` 配置
  - `set_run_format_with_styles()`: 使用 `inline_code` 和 `math` 配置
  - `set_table_run_format()`, `set_table_cell_format()`: 使用 `table` 配置
  - `create_word_table()`, `create_word_table_from_html()`: 使用 `table` 配置
  - `insert_image_to_word()`: 使用 `image` 配置
  - 新增 `hex_to_rgb()`: 十六进制颜色转换函数

- **所有预设文件**: 同步新增配置选项
  - `legal.yaml`: 法律文书格式预设（与原始脚本完全一致）
  - `academic.yaml`: 学术论文格式预设
  - `report.yaml`: 工作报告格式预设
  - `simple.yaml`: 简单文档格式预设

- **config-template.yaml**: 更新配置模板，包含所有新配置选项

## [0.1.0] - 2026-01-29

### 新增
- **初始版本**: md2word 技能 - Markdown转Word配置化工具
  - YAML 配置系统支持
  - 4 种内置预设格式 (legal/academic/report/simple)
  - 自定义配置文件支持
  - Word 模板文件支持 (.docx)
  - 命令行参数: `--preset`, `--config`, `--list-presets`, `--template`

### 功能特性
- 完整的 Markdown 到 Word 转换
- 页面格式设置 (A4, 页边距)
- 字体和字号配置
- 标题格式配置 (4 级标题)
- 段落格式配置 (行距、首行缩进、对齐)
- 页码自动生成 (支持 1/x 格式)
- 引号自动转换 (英文 → 中文)
- 表格转换支持 (Markdown 和 HTML 表格)
- 图片插入和优化
- Mermaid 图表本地渲染
- 格式支持: **加粗**、*斜体*、<u>下划线</u>、~~删除线~~
- 代码块和行内代码支持
- 数学公式支持 ($LaTeX$)
- 列表支持 (无序、有序、任务列表)
- 引用块支持

### 目录结构
```
md2word/
├── assets/
│   ├── presets/          # YAML 格式预设
│   ├── templates/        # Word .docx 模板文件
│   └── config-template.yaml
├── scripts/
│   ├── md2word.py       # 主转换脚本
│   └── config.py        # 配置管理模块
└── SKILL.md             # 技能文档
```
