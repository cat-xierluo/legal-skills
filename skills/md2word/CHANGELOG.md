# Changelog

All notable changes to the md2word skill will be documented in this file.

## [0.2.0] - 2026-01-29

### Added
- **配置系统增强**: 添加完整的配置选项到 YAML 模板和预设文件
  - 代码块格式配置: 语言标签、内容字体、缩进、行距
  - 行内代码格式配置: 字体、字号、颜色
  - 引用块格式配置: 背景色、缩进、字号
  - 数学公式格式配置: 字体、字号、斜体、颜色
  - 图片设置配置: 显示比例、最大宽度、目标DPI
  - 分割线设置配置: 字符、重复次数、字体、颜色
  - 列表设置配置: 无序列表、有序列表、任务列表标记
  - 表格增强配置: 行高、单元格边距、垂直对齐、标题/正文格式

### Changed
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

### Added
- **初始版本**: md2word 技能 - Markdown转Word配置化工具
  - YAML 配置系统支持
  - 4 种内置预设格式 (legal/academic/report/simple)
  - 自定义配置文件支持
  - Word 模板文件支持 (.docx)
  - 命令行参数: `--preset`, `--config`, `--list-presets`, `--template`

### Features
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

### Directory Structure
```
md2word/
├── assets/
│   ├── presets/          # YAML 格式预设
│   ├── templates/        # Word .docx 模板文件
│   └── config-template.yaml
├── scripts/
│   ├── md2word.py       # 主转换脚本
│   ├── config.py        # 配置管理模块
│   └── requirements.txt
└── SKILL.md             # 技能文档
```
